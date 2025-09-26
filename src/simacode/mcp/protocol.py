"""
MCP protocol implementation based on JSON-RPC 2.0.

This module implements the Model Context Protocol message structures,
protocol handling, and communication patterns.
"""

import asyncio
import json
import logging
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union, AsyncGenerator, Callable

from .exceptions import MCPProtocolError

logger = logging.getLogger(__name__)


@dataclass
class MCPMessage:
    """
    Base MCP message structure following JSON-RPC 2.0 specification.
    """
    jsonrpc: str = "2.0"
    id: Optional[Union[str, int]] = None
    method: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Validate message structure after initialization."""
        # Auto-generate ID for requests if not provided
        # This is done when creating requests programmatically
        pass
    
    def is_request(self) -> bool:
        """Check if message is a request."""
        return self.method is not None and self.id is not None
    
    def is_notification(self) -> bool:
        """Check if message is a notification."""
        return self.method is not None and self.id is None
    
    def is_response(self) -> bool:
        """Check if message is a response."""
        return self.method is None and self.id is not None
    
    def is_error(self) -> bool:
        """Check if message contains an error."""
        return self.error is not None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary format."""
        data = {"jsonrpc": self.jsonrpc}
        
        if self.id is not None:
            data["id"] = self.id
        
        if self.method is not None:
            data["method"] = self.method
            
        if self.params is not None:
            data["params"] = self.params
            
        if self.result is not None:
            data["result"] = self.result
            
        if self.error is not None:
            data["error"] = self.error
            
        return data
    
    def to_json(self) -> str:
        """Convert message to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MCPMessage":
        """Create message from dictionary."""
        if data.get("jsonrpc") != "2.0":
            raise MCPProtocolError(f"Invalid JSON-RPC version: {data.get('jsonrpc')}")
        
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            id=data.get("id"),
            method=data.get("method"),
            params=data.get("params"),
            result=data.get("result"),
            error=data.get("error")
        )
    
    @classmethod
    def from_json(cls, json_str: str) -> "MCPMessage":
        """Create message from JSON string."""
        try:
            data = json.loads(json_str)
            return cls.from_dict(data)
        except json.JSONDecodeError as e:
            raise MCPProtocolError(f"Invalid JSON: {str(e)}")


@dataclass
class MCPTool:
    """MCP tool definition."""
    name: str
    description: str
    server_name: str
    input_schema: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert tool to dictionary format."""
        return {
            "name": self.name,
            "description": self.description,
            "server_name": self.server_name,
            "input_schema": self.input_schema
        }


@dataclass 
class MCPResource:
    """MCP resource definition."""
    uri: str
    name: str
    description: Optional[str] = None
    mime_type: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert resource to dictionary format."""
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mime_type": self.mime_type
        }


@dataclass
class MCPPrompt:
    """MCP prompt template definition."""
    name: str
    description: str
    arguments: Optional[List[Dict[str, Any]]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert prompt to dictionary format.""" 
        return {
            "name": self.name,
            "description": self.description,
            "arguments": self.arguments or []
        }


@dataclass
class MCPResult:
    """MCP operation result."""
    success: bool
    content: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary format."""
        return {
            "success": self.success,
            "content": self.content,
            "error": self.error,
            "metadata": self.metadata
        }


class MCPTransport(ABC):
    """Abstract base class for MCP transport mechanisms."""
    
    @abstractmethod
    async def send(self, message: bytes) -> None:
        """Send message through transport."""
        pass
    
    @abstractmethod
    async def receive(self) -> bytes:
        """Receive message from transport."""
        pass
    
    @abstractmethod
    async def connect(self) -> bool:
        """Establish transport connection."""
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """Close transport connection."""
        pass
    
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if transport is connected."""
        pass

    def _prepare_environment(self) -> Dict[str, str]:
        """
        Prepare environment variables by merging custom env with current environment.

        This method provides a consistent way for all transport types to handle
        environment variables, following the same pattern as StdioTransport.

        Returns:
            Dict containing merged environment variables
        """
        import os
        process_env = dict(os.environ) if hasattr(self, 'env') and self.env else os.environ.copy()
        if hasattr(self, 'env') and self.env:
            process_env.update(self.env)
        return process_env


class MCPProtocol:
    """
    MCP protocol handler implementing JSON-RPC 2.0 over various transports.
    """
    
    def __init__(self, transport: MCPTransport):
        self.transport = transport
        self._request_id_counter = 0
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._receive_task: Optional[asyncio.Task] = None
        self._protocol_lock = asyncio.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # 新增：异步任务和进度回传支持
        self._long_running_tasks: Dict[str, asyncio.Task] = {}
        self._progress_callbacks: Dict[str, List[Callable]] = {}
        self._async_response_queues: Dict[str, asyncio.Queue] = {}
        self._server_capabilities: Optional[Dict[str, Any]] = None
        
    async def send_message(self, message: MCPMessage) -> None:
        """Send MCP message through transport."""
        if not self.transport.is_connected():
            raise MCPProtocolError("Transport not connected")
        
        json_data = message.to_json()
        await self.transport.send(json_data.encode('utf-8'))
    
    async def receive_message(self) -> MCPMessage:
        """Receive MCP message from transport."""
        if not self.transport.is_connected():
            raise MCPProtocolError("Transport not connected")
        
        data = await self.transport.receive()
        json_str = data.decode('utf-8')
        return MCPMessage.from_json(json_str)
    
    async def call_method(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """
        Call MCP method and wait for response.
        
        Args:
            method: Method name to call
            params: Method parameters
            
        Returns:
            Method result
            
        Raises:
            MCPProtocolError: If method call fails
        """
        async with self._protocol_lock:
            # Initialize loop reference on first call
            current_loop = asyncio.get_running_loop()
            if self._loop is None:
                self._loop = current_loop
            elif self._loop != current_loop:
                # Event loop has changed, reset everything
                logger.warning("Event loop changed, reinitializing MCP protocol")
                self._pending_requests.clear()
                if self._receive_task and not self._receive_task.done():
                    self._receive_task.cancel()
                self._receive_task = None
                self._loop = current_loop
                
            # Start message receiver if not already running
            if self._receive_task is None or self._receive_task.done():
                self._receive_task = self._loop.create_task(self._message_receiver_loop())
            
            # Generate unique request ID
            request_id = self._generate_request_id()
            
            # Create future for response (use the protocol's loop)
            future = self._loop.create_future()
            self._pending_requests[request_id] = future
            
            try:
                # Create and send request message
                request = MCPMessage(
                    id=request_id,
                    method=method,
                    params=params
                )
                
                await self.send_message(request)
                
                # Wait for response with timeout
                response = await asyncio.wait_for(future, timeout=300.0)
                
                # Validate response
                if response.is_error():
                    error_info = response.error or {}
                    raise MCPProtocolError(
                        f"Method call failed: {error_info.get('message', 'Unknown error')}",
                        error_code=str(error_info.get('code', -1))
                    )
                
                return response.result
                
            except asyncio.TimeoutError:
                raise MCPProtocolError(f"Method call timeout: {method}")
            finally:
                # Clean up pending request
                self._pending_requests.pop(request_id, None)
    
    async def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        """
        Send MCP notification (no response expected).
        
        Args:
            method: Method name
            params: Method parameters
        """
        notification = MCPMessage(
            method=method,
            params=params
        )
        
        await self.send_message(notification)

    async def call_tool_async(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        progress_callback: Optional[Callable] = None,
        timeout: Optional[float] = None
    ) -> AsyncGenerator[MCPResult, None]:
        """
        异步工具调用，支持进度回传和长时间运行任务。

        Args:
            tool_name: 工具名称
            arguments: 工具参数
            progress_callback: 进度回调函数
            timeout: 超时时间（秒），默认为1小时

        Yields:
            MCPResult: 进度更新和最终结果
        """
        # 检查服务器是否支持异步调用
        if await self._server_supports_async():
            # 使用新的异步协议
            async for result in self._call_tool_async_protocol(
                tool_name, arguments, progress_callback, timeout or 600
            ):
                yield result
        else:
            # 回退到标准同步调用
            logger.debug(f"Server doesn't support async, falling back to sync call for tool '{tool_name}'")
            async for result in self._call_tool_sync_fallback(tool_name, arguments, {"fallback_mode": True}):
                yield result

    async def _call_tool_sync_fallback(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        metadata_extra: Dict[str, Any] = None
    ) -> AsyncGenerator[MCPResult, None]:
        """
        公用的同步工具调用回退逻辑。

        Args:
            tool_name: 工具名称
            arguments: 工具参数
            metadata_extra: 额外的元数据

        Yields:
            MCPResult: 调用结果
        """
        try:
            result = await self.call_method(MCPMethods.TOOLS_CALL, {
                "name": tool_name,
                "arguments": arguments
            })

            metadata = {"type": "final_result"}
            if metadata_extra:
                metadata.update(metadata_extra)

            yield MCPResult(
                success=True,
                content=result,
                metadata=metadata
            )
        except Exception as e:
            metadata = {"type": "error"}
            if metadata_extra:
                metadata.update(metadata_extra)

            yield MCPResult(
                success=False,
                error=str(e),
                metadata=metadata
            )

    async def _server_supports_async(self) -> bool:
        """检查服务器是否支持异步扩展"""
        if self._server_capabilities is None:
            return False

        # 检查服务器能力中是否包含异步工具支持
        tools_capabilities = self._server_capabilities.get("tools", {})
        async_support = tools_capabilities.get("async_support", False)
        return async_support

    async def _call_tool_async_protocol(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        progress_callback: Optional[Callable],
        timeout: float
    ) -> AsyncGenerator[MCPResult, None]:
        """实现异步协议扩展"""

        request_id = self._generate_request_id()

        # 注册进度回调
        if progress_callback:
            if request_id not in self._progress_callbacks:
                self._progress_callbacks[request_id] = []
            self._progress_callbacks[request_id].append(progress_callback)

        # 创建响应队列
        response_queue = asyncio.Queue()
        self._async_response_queues[request_id] = response_queue

        try:
            # 发送异步工具调用请求
            request = MCPMessage(
                id=request_id,
                method="tools/call_async",  # 新的异步方法
                params={
                    "name": tool_name,
                    "arguments": arguments,
                    "enable_progress": True,
                    "timeout": timeout
                }
            )

            await self.send_message(request)
            # Keep essential MCP async flow logging
            logger.debug(f"Sent async tool call request for '{tool_name}' with ID {request_id}")

            # 等待响应流
            async for message in self._wait_for_async_responses(request_id, timeout):
                # Essential MCP async flow logging
                logger.debug(f"MCP async message: method='{message.method}', request_id='{request_id}'")

                if message.method == "tools/progress":
                    # 进度通知
                    progress_data = message.params
                    # Essential MCP progress logging
                    logger.debug(f"MCP tools/progress: request_id={request_id}")

                    # 调用进度回调
                    if request_id in self._progress_callbacks:
                        for callback in self._progress_callbacks[request_id]:
                            try:
                                await callback(progress_data)
                            except Exception as e:
                                logger.warning(f"Progress callback error: {e}")

                    yield MCPResult(
                        success=True,
                        content=progress_data,
                        metadata={"type": "progress", "request_id": request_id}
                    )

                elif message.method == "tools/result":
                    # 最终结果
                    result_data = message.params
                    logger.debug(f"MCP tools/result: request_id='{request_id}'")
                    yield MCPResult(
                        success=True,
                        content=result_data.get("result"),
                        metadata={"type": "final_result", "request_id": request_id}
                    )
                    break

                elif message.method == "tools/error":
                    # 错误结果
                    error_data = message.params
                    yield MCPResult(
                        success=False,
                        error=error_data.get("error", "Unknown error"),
                        metadata={"type": "error", "request_id": request_id}
                    )
                    break

        except asyncio.TimeoutError:
            logger.error(f"Async tool call timeout for '{tool_name}' (request_id: {request_id})")
            yield MCPResult(
                success=False,
                error=f"Tool call timeout after {timeout} seconds",
                metadata={"type": "timeout_error", "request_id": request_id}
            )

        except Exception as e:
            logger.error(f"Async tool call error for '{tool_name}': {e}")
            yield MCPResult(
                success=False,
                error=str(e),
                metadata={"type": "protocol_error", "request_id": request_id}
            )

        finally:
            # 清理资源
            self._progress_callbacks.pop(request_id, None)
            self._async_response_queues.pop(request_id, None)

    async def _wait_for_async_responses(self, request_id: str, timeout: float) -> AsyncGenerator[MCPMessage, None]:
        """等待异步响应流"""
        response_queue = self._async_response_queues.get(request_id)
        if not response_queue:
            raise ValueError(f"No response queue found for request {request_id}")
        start_time = asyncio.get_event_loop().time()

        while True:
            try:
                # 计算剩余超时时间
                elapsed = asyncio.get_event_loop().time() - start_time
                remaining_timeout = max(0, timeout - elapsed)

                if remaining_timeout <= 0:
                    raise asyncio.TimeoutError()

                # 等待下一个响应，使用较短的超时以便定期检查
                message = await asyncio.wait_for(
                    response_queue.get(),
                    timeout=min(remaining_timeout, 5.0)
                )

                # Essential MCP async response logging
                logger.debug(f"MCP async response: method={message.method}, request_id={request_id}")
                yield message

                # 如果是最终结果或错误，停止等待
                if message.method in ["tools/result", "tools/error"]:
                    break

            except asyncio.TimeoutError:
                # 检查是否真的超时了
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= timeout:
                    raise
                # 否则继续等待
                continue

    async def _handle_notification(self, message: MCPMessage):
        """处理服务器通知"""
        if message.method in ["tools/progress", "tools/result", "tools/error"]:
            # 异步任务相关通知，路由到对应的响应队列
            request_id = message.params.get("request_id") if message.params else None

            if request_id and request_id in self._async_response_queues:
                try:
                    await self._async_response_queues[request_id].put(message)
                    # Essential MCP routing logging for debugging
                    logger.debug(f"MCP routed {message.method} to queue {request_id}")
                except Exception as e:
                    logger.error(f"Failed to route notification for request {request_id}: {e}")
            else:
                logger.debug(f"MCP {message.method} notification without request queue (request_id: {request_id})")
        else:
            # 其他通知类型，记录日志
            logger.debug(f"Received notification: {message.method}")

    def set_server_capabilities(self, capabilities: Dict[str, Any]):
        """设置服务器能力信息（通常在初始化时调用）"""
        self._server_capabilities = capabilities
        # Keep server capabilities logging for MCP debugging
        logger.debug(f"MCP server capabilities updated: {capabilities.keys() if capabilities else None}")

    def _generate_request_id(self) -> str:
        """Generate unique request ID."""
        self._request_id_counter += 1
        return f"req_{self._request_id_counter}"
    
    async def _message_receiver_loop(self):
        """Background task to receive and route messages."""
        try:
            while self.transport.is_connected():
                try:
                    message = await self.receive_message()
                    
                    # Handle responses to pending requests
                    if message.is_response() and message.id in self._pending_requests:
                        future = self._pending_requests[message.id]
                        if not future.done():
                            future.set_result(message)
                    
                    # Handle notifications (could be logged or processed)
                    elif message.is_notification():
                        # 处理异步任务相关通知
                        await self._handle_notification(message)
                        
                except Exception as e:
                    # If there's an error, complete all pending requests with the error
                    for future in self._pending_requests.values():
                        if not future.done():
                            future.set_exception(MCPProtocolError(f"Message receiver error: {str(e)}"))
                    break
                    
        except Exception:
            # Clean up on exit
            pass
    
    async def shutdown(self):
        """Shutdown the protocol and clean up resources."""
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        
        # Complete any remaining pending requests with cancellation
        for future in self._pending_requests.values():
            if not future.done():
                future.cancel()
        
        self._pending_requests.clear()


# MCP standard method constants
class MCPMethods:
    """Standard MCP method names."""
    
    # Core protocol methods
    INITIALIZE = "initialize"
    PING = "ping"
    
    # Tool methods
    TOOLS_LIST = "tools/list"
    TOOLS_CALL = "tools/call"
    TOOLS_CALL_ASYNC = "tools/call_async"  # 新增：异步工具调用
    TOOLS_PROGRESS = "tools/progress"      # 新增：工具执行进度通知
    TOOLS_RESULT = "tools/result"          # 新增：异步工具结果通知
    TOOLS_ERROR = "tools/error"            # 新增：异步工具错误通知
    
    # Resource methods  
    RESOURCES_LIST = "resources/list"
    RESOURCES_READ = "resources/read"
    
    # Prompt methods
    PROMPTS_LIST = "prompts/list"
    PROMPTS_GET = "prompts/get"
    
    # Notification methods
    NOTIFICATIONS_INITIALIZED = "notifications/initialized"
    NOTIFICATIONS_CANCELLED = "notifications/cancelled"


# MCP error codes (following JSON-RPC 2.0 specification)
class MCPErrorCodes:
    """Standard MCP error codes."""
    
    # JSON-RPC 2.0 standard errors
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    
    # MCP-specific errors
    TOOL_NOT_FOUND = -32000
    RESOURCE_NOT_FOUND = -32001
    SECURITY_ERROR = -32002
    TIMEOUT_ERROR = -32003


class EmbeddedProtocol:
    """
    Special MCP protocol handler for embedded transports.

    Unlike standard MCPProtocol, this uses direct send_message() calls
    to the embedded server without async message queues.
    """

    def __init__(self, transport):
        """Initialize embedded protocol with embedded transport."""
        from .connection import EmbeddedTransport
        if not isinstance(transport, EmbeddedTransport):
            raise ValueError("EmbeddedProtocol requires EmbeddedTransport")

        self.transport = transport
        self._request_id_counter = 0
        self._server_capabilities: Optional[Dict[str, Any]] = None

    def _generate_request_id(self) -> str:
        """Generate unique request ID."""
        self._request_id_counter += 1
        return str(self._request_id_counter)

    async def call_method(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """
        Call MCP method directly on embedded server.

        Args:
            method: Method name to call
            params: Method parameters

        Returns:
            Method result

        Raises:
            MCPProtocolError: If method call fails
        """
        if not self.transport.is_connected():
            raise MCPProtocolError("Embedded transport not connected")

        # Create request message
        request = MCPMessage(
            id=self._generate_request_id(),
            method=method,
            params=params
        )

        try:
            # Send message directly to embedded server
            response = await self.transport.send_message(request)

            # Handle direct response from embedded server
            if isinstance(response, dict):
                # Convert dict response to MCPMessage for consistency
                response_msg = MCPMessage.from_dict(response)
            elif hasattr(response, 'is_error'):
                # Already an MCPMessage
                response_msg = response
            else:
                # Wrap raw response
                response_msg = MCPMessage(
                    id=request.id,
                    result=response
                )

            # Validate response
            if response_msg.is_error():
                error_info = response_msg.error or {}
                raise MCPProtocolError(
                    f"Method call failed: {error_info.get('message', 'Unknown error')}",
                    error_code=str(error_info.get('code', -1))
                )

            return response_msg.result

        except Exception as e:
            if isinstance(e, MCPProtocolError):
                raise
            raise MCPProtocolError(f"Embedded method call error: {str(e)}")

    async def send_notification(self, method: str, params: Optional[Dict[str, Any]] = None) -> None:
        """
        Send notification to embedded server.

        Args:
            method: Method name
            params: Method parameters
        """
        if not self.transport.is_connected():
            raise MCPProtocolError("Embedded transport not connected")

        # Create notification message (no ID)
        notification = MCPMessage(
            method=method,
            params=params
        )

        try:
            # Send notification to embedded server
            await self.transport.send_message(notification)
        except Exception as e:
            raise MCPProtocolError(f"Embedded notification error: {str(e)}")

    def set_server_capabilities(self, capabilities: Dict[str, Any]) -> None:
        """Set server capabilities for async capability detection."""
        self._server_capabilities = capabilities

    async def call_tool_async(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        progress_callback: Optional[Callable] = None,
        timeout: Optional[float] = None
    ) -> AsyncGenerator[MCPResult, None]:
        """
        异步工具调用，兼容 MCPProtocol 的 call_tool_async 方法。

        For embedded servers, this wraps the synchronous tool call to match
        the async generator interface expected by the MCP client.

        Args:
            tool_name: 工具名称
            arguments: 工具参数
            progress_callback: 进度回调函数（embedded 模式下不使用）
            timeout: 超时时间（embedded 模式下不使用）

        Yields:
            MCPResult: 最终结果
        """
        # Reuse the sync fallback logic from MCPProtocol with embedded mode metadata
        async for result in self._call_tool_sync_fallback(tool_name, arguments, {"embedded_mode": True}):
            yield result

    async def _call_tool_sync_fallback(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        metadata_extra: Dict[str, Any] = None
    ) -> AsyncGenerator[MCPResult, None]:
        """
        公用的同步工具调用回退逻辑（从 MCPProtocol 复用）。

        Args:
            tool_name: 工具名称
            arguments: 工具参数
            metadata_extra: 额外的元数据

        Yields:
            MCPResult: 调用结果
        """
        try:
            result = await self.call_method(MCPMethods.TOOLS_CALL, {
                "name": tool_name,
                "arguments": arguments
            })

            metadata = {"type": "final_result"}
            if metadata_extra:
                metadata.update(metadata_extra)

            yield MCPResult(
                success=True,
                content=result,
                metadata=metadata
            )
        except Exception as e:
            metadata = {"type": "error"}
            if metadata_extra:
                metadata.update(metadata_extra)

            yield MCPResult(
                success=False,
                error=str(e),
                metadata=metadata
            )