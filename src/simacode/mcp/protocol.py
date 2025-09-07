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
from typing import Any, Dict, List, Optional, Union

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
                response = await asyncio.wait_for(future, timeout=30.0)
                
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
                        # For now, just log notifications
                        pass
                        
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