"""
MCP client implementation.

This module provides the core MCP client that handles communication with
MCP servers, tool discovery, and method invocation.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, AsyncGenerator, Callable
from cachetools import TTLCache

from .protocol import (
    MCPProtocol, MCPTool, MCPResource, MCPPrompt, MCPResult, 
    MCPMethods, MCPErrorCodes
)
from .connection import create_transport, MCPConnection
from .config import MCPServerConfig
from .exceptions import (
    MCPConnectionError, MCPTimeoutError, MCPToolNotFoundError,
    MCPProtocolError, MCPResourceNotFoundError
)

logger = logging.getLogger(__name__)


class MCPClientState:
    """Enumeration of MCP client states."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    INITIALIZING = "initializing"
    READY = "ready"
    ERROR = "error"


class MCPClient:
    """
    MCP protocol client for communicating with MCP servers.
    
    This client handles the complete MCP lifecycle including connection,
    initialization, tool discovery, and method invocation.
    """
    
    def __init__(self, server_config: MCPServerConfig):
        self.server_config = server_config
        self.server_name = server_config.name
        
        # Connection management
        self.connection: Optional[MCPConnection] = None
        self.protocol: Optional[MCPProtocol] = None
        self.state = MCPClientState.DISCONNECTED
        
        # Caching
        self.tools_cache: Dict[str, MCPTool] = {}
        self.resources_cache: Dict[str, MCPResource] = {}
        self.prompts_cache: Dict[str, MCPPrompt] = {}
        
        # Server capabilities and info
        self.server_info: Optional[Dict[str, Any]] = None
        self.server_capabilities: Optional[Dict[str, Any]] = None
        
        # Performance optimization
        self.result_cache = TTLCache(maxsize=100, ttl=300)  # 5 minutes
        
        # Error handling
        self.last_error: Optional[Exception] = None
        self.connection_attempts = 0
        self.max_connection_attempts = self.server_config.max_retries
    
    async def connect(self) -> bool:
        """
        Connect to the MCP server and initialize the session.
        
        Returns:
            bool: True if connection and initialization successful
        """
        if self.state in [MCPClientState.CONNECTED, MCPClientState.READY]:
            return True
        
        try:
            self.state = MCPClientState.CONNECTING
            self.connection_attempts += 1
            
            logger.info(f"Connecting to MCP server '{self.server_name}' (attempt {self.connection_attempts})")
            
            # Create transport and connection
            transport_config = {
                "command": self.server_config.command,
                "args": self.server_config.args,
                "environment": self.server_config.environment,
                "working_directory": self.server_config.working_directory
            }

            # Add WebSocket-specific configuration
            if hasattr(self.server_config, 'url'):
                transport_config["url"] = self.server_config.url
            if hasattr(self.server_config, 'headers'):
                transport_config["headers"] = self.server_config.headers

            # Add Embedded-specific configuration
            if hasattr(self.server_config, 'module_path'):
                transport_config["module_path"] = self.server_config.module_path
            if hasattr(self.server_config, 'main_function'):
                transport_config["main_function"] = self.server_config.main_function
            
            transport = create_transport(self.server_config.type, transport_config)
            
            self.connection = MCPConnection(transport, timeout=self.server_config.timeout)
            await self.connection.connect()
            
            # Create appropriate protocol handler based on transport type
            from .connection import EmbeddedTransport
            from .protocol import EmbeddedProtocol

            if isinstance(transport, EmbeddedTransport):
                self.protocol = EmbeddedProtocol(transport)
                logger.debug(f"Using EmbeddedProtocol for embedded transport")
            else:
                self.protocol = MCPProtocol(transport)
                logger.debug(f"Using standard MCPProtocol for {transport.__class__.__name__}")
            
            self.state = MCPClientState.CONNECTED
            logger.info(f"Connected to MCP server '{self.server_name}'")
            
            # Initialize MCP session
            await self._initialize_session()
            
            self.state = MCPClientState.READY
            self.connection_attempts = 0  # Reset on success
            
            logger.info(f"MCP server '{self.server_name}' is ready")
            return True
            
        except Exception as e:
            self.last_error = e
            self.state = MCPClientState.ERROR
            
            logger.error(f"Failed to connect to MCP server '{self.server_name}': {str(e)}")
            
            if self.connection:
                await self.connection.disconnect()
                self.connection = None
                self.protocol = None
            
            return False
    
    async def disconnect(self) -> None:
        """Disconnect from the MCP server."""
        if self.connection:
            try:
                logger.info(f"Disconnecting from MCP server '{self.server_name}'")
                
                # Shutdown protocol first
                if self.protocol:
                    await self.protocol.shutdown()
                
                await self.connection.disconnect()
            except Exception as e:
                logger.warning(f"Error during disconnect from '{self.server_name}': {str(e)}")
            finally:
                self.connection = None
                self.protocol = None
                self.state = MCPClientState.DISCONNECTED
                
                # Clear caches
                self.tools_cache.clear()
                self.resources_cache.clear()
                self.prompts_cache.clear()
                self.result_cache.clear()
    
    def is_connected(self) -> bool:
        """Check if client is connected and ready."""
        return (
            self.state == MCPClientState.READY and 
            self.connection and 
            self.connection.is_connected()
        )
    
    async def _initialize_session(self) -> None:
        """Initialize MCP session with the server."""
        if not self.protocol:
            raise MCPConnectionError("Protocol not available")
        
        self.state = MCPClientState.INITIALIZING
        
        try:
            # Send initialize request
            init_params = {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False}
                },
                "clientInfo": {
                    "name": "simacode-mcp-client",
                    "version": "1.0.0"
                }
            }
            
            result = await self.protocol.call_method(MCPMethods.INITIALIZE, init_params)
            
            # Store server info and capabilities
            self.server_info = result.get("serverInfo", {})
            self.server_capabilities = result.get("capabilities", {})

            # 设置协议层的服务器能力信息，用于异步能力检测
            self.protocol.set_server_capabilities(self.server_capabilities)

            logger.info(f"Initialized session with server '{self.server_name}': {self.server_info}")

            # Send initialized notification
            await self.protocol.send_notification(MCPMethods.NOTIFICATIONS_INITIALIZED)
            
            # Discover available tools and resources
            await self._discover_capabilities()
            
        except Exception as e:
            raise MCPConnectionError(f"Failed to initialize session: {str(e)}")
    
    async def _discover_capabilities(self) -> None:
        """Discover tools, resources, and prompts from the server."""
        try:
            # Discover tools
            if self.server_capabilities and self.server_capabilities.get("tools"):
                await self._discover_tools()
            
            # Discover resources
            if self.server_capabilities and self.server_capabilities.get("resources"):
                await self._discover_resources()
            
            # Discover prompts
            if self.server_capabilities and self.server_capabilities.get("prompts"):
                await self._discover_prompts()
                
        except Exception as e:
            logger.warning(f"Error discovering capabilities for '{self.server_name}': {str(e)}")
    
    async def _discover_tools(self) -> None:
        """Discover available tools from the server."""
        try:
            result = await self.protocol.call_method(MCPMethods.TOOLS_LIST)
            tools_data = result.get("tools", [])
            
            self.tools_cache.clear()
            for tool_data in tools_data:
                tool = MCPTool(
                    name=tool_data["name"],
                    description=tool_data.get("description", ""),
                    server_name=self.server_name,
                    input_schema=tool_data.get("input_schema")
                )
                self.tools_cache[tool.name] = tool
            
            logger.info(f"Discovered {len(self.tools_cache)} tools from '{self.server_name}'")
            
        except Exception as e:
            logger.warning(f"Failed to discover tools from '{self.server_name}': {str(e)}")
    
    async def _discover_resources(self) -> None:
        """Discover available resources from the server."""
        try:
            result = await self.protocol.call_method(MCPMethods.RESOURCES_LIST)
            resources_data = result.get("resources", [])
            
            self.resources_cache.clear()
            for resource_data in resources_data:
                resource = MCPResource(
                    uri=resource_data["uri"],
                    name=resource_data.get("name", ""),
                    description=resource_data.get("description"),
                    mime_type=resource_data.get("mime_type")
                )
                self.resources_cache[resource.uri] = resource
            
            logger.info(f"Discovered {len(self.resources_cache)} resources from '{self.server_name}'")
            
        except Exception as e:
            logger.warning(f"Failed to discover resources from '{self.server_name}': {str(e)}")
    
    async def _discover_prompts(self) -> None:
        """Discover available prompts from the server."""
        try:
            result = await self.protocol.call_method(MCPMethods.PROMPTS_LIST)
            prompts_data = result.get("prompts", [])
            
            self.prompts_cache.clear()
            for prompt_data in prompts_data:
                prompt = MCPPrompt(
                    name=prompt_data["name"],
                    description=prompt_data.get("description", ""),
                    arguments=prompt_data.get("arguments", [])
                )
                self.prompts_cache[prompt.name] = prompt
            
            logger.info(f"Discovered {len(self.prompts_cache)} prompts from '{self.server_name}'")
            
        except Exception as e:
            logger.warning(f"Failed to discover prompts from '{self.server_name}': {str(e)}")
    
    async def list_tools(self) -> List[MCPTool]:
        """
        Get list of available tools from the server.
        
        Returns:
            List[MCPTool]: List of available tools
        """
        if not self.is_connected():
            raise MCPConnectionError(f"Not connected to server '{self.server_name}'")
        
        # Return cached tools if available
        if self.tools_cache:
            return list(self.tools_cache.values())
        
        # Refresh tools if cache is empty
        await self._discover_tools()
        return list(self.tools_cache.values())
    
    async def get_tool(self, tool_name: str) -> Optional[MCPTool]:
        """
        Get a specific tool by name.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Optional[MCPTool]: Tool if found, None otherwise
        """
        if not self.is_connected():
            raise MCPConnectionError(f"Not connected to server '{self.server_name}'")
        
        # Check cache first
        if tool_name in self.tools_cache:
            return self.tools_cache[tool_name]
        
        # Refresh tools and check again
        await self._discover_tools()
        return self.tools_cache.get(tool_name)
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> MCPResult:
        """
        Call a tool on the MCP server.
        
        Args:
            tool_name: Name of the tool to call
            arguments: Arguments to pass to the tool
            
        Returns:
            MCPResult: Result of tool execution
            
        Raises:
            MCPToolNotFoundError: If tool is not found
            MCPConnectionError: If not connected
        """
        if not self.is_connected():
            raise MCPConnectionError(f"Not connected to server '{self.server_name}'")
        
        # Check if tool exists
        tool = await self.get_tool(tool_name)
        if not tool:
            raise MCPToolNotFoundError(
                f"Tool '{tool_name}' not found",
                tool_name=tool_name,
                server_name=self.server_name
            )
        
        try:
            # Event loop consistency check
            current_loop = asyncio.get_running_loop()
            if hasattr(self, '_creation_loop_id'):
                if id(current_loop) != self._creation_loop_id:
                    logger.warning(
                        f"Event loop changed for MCP client '{self.server_name}': "
                        f"creation_loop={self._creation_loop_id}, current_loop={id(current_loop)}. "
                        f"This may cause issues with async operations."
                    )
            else:
                # Store the current loop ID for future checks
                self._creation_loop_id = id(current_loop)
            
            # Generate cache key for result caching
            import hashlib
            import json
            cache_key = hashlib.md5(
                f"{tool_name}:{json.dumps(arguments, sort_keys=True)}".encode()
            ).hexdigest()
            
            # Check cache first
            if cache_key in self.result_cache:
                logger.debug(f"Returning cached result for tool '{tool_name}'")
                return self.result_cache[cache_key]
            
            # Call the tool
            logger.info(f"Calling tool '{tool_name}' on server '{self.server_name}'")
            result = await self.protocol.call_method(MCPMethods.TOOLS_CALL, {
                "name": tool_name,
                "arguments": arguments
            })
            
            # Convert to MCPResult
            mcp_result = MCPResult(
                success=True,
                content=result,
                metadata={
                    "server_name": self.server_name,
                    "tool_name": tool_name,
                    "execution_time": 0  # TODO: Track execution time
                }
            )
            
            # Cache successful results
            self.result_cache[cache_key] = mcp_result
            
            return mcp_result

        except Exception as e:
            logger.error(f"Tool call failed for '{tool_name}' on '{self.server_name}': {str(e)}")
            return MCPResult(
                success=False,
                error=str(e),
                metadata={
                    "server_name": self.server_name,
                    "tool_name": tool_name,
                    "error_type": type(e).__name__
                }
            )

    async def call_tool_async(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        progress_callback: Optional[Callable] = None,
        timeout: Optional[float] = None
    ) -> AsyncGenerator[MCPResult, None]:
        """
        异步调用工具，支持进度回传和长时间运行任务。

        Args:
            tool_name: 工具名称
            arguments: 工具参数
            progress_callback: 进度回调函数
            timeout: 超时时间（秒）

        Yields:
            MCPResult: 进度更新和最终结果

        Raises:
            MCPToolNotFoundError: 如果工具不存在
            MCPConnectionError: 如果连接断开
        """
        if not self.is_connected():
            raise MCPConnectionError(f"Not connected to server '{self.server_name}'")

        # 检查工具是否存在
        tool = await self.get_tool(tool_name)
        if not tool:
            raise MCPToolNotFoundError(
                f"Tool '{tool_name}' not found",
                tool_name=tool_name,
                server_name=self.server_name
            )

        try:
            logger.info(f"Starting async call for tool '{tool_name}' on server '{self.server_name}'")

            # 使用协议层的异步调用
            async for mcp_result in self.protocol.call_tool_async(
                tool_name=tool_name,
                arguments=arguments,
                progress_callback=progress_callback,
                timeout=timeout
            ):
                # 为结果添加客户端元数据
                if mcp_result.metadata is None:
                    mcp_result.metadata = {}

                mcp_result.metadata.update({
                    "server_name": self.server_name,
                    "tool_name": tool_name,
                    "client_version": "1.0.0"
                })

                yield mcp_result

        except Exception as e:
            logger.error(f"Async tool call failed for '{tool_name}' on '{self.server_name}': {str(e)}")
            yield MCPResult(
                success=False,
                error=str(e),
                metadata={
                    "server_name": self.server_name,
                    "tool_name": tool_name,
                    "error_type": type(e).__name__,
                    "async_call": True
                }
            )

    async def list_resources(self) -> List[MCPResource]:
        """
        Get list of available resources from the server.
        
        Returns:
            List[MCPResource]: List of available resources
        """
        if not self.is_connected():
            raise MCPConnectionError(f"Not connected to server '{self.server_name}'")
        
        # Return cached resources if available
        if self.resources_cache:
            return list(self.resources_cache.values())
        
        # Refresh resources if cache is empty
        await self._discover_resources()
        return list(self.resources_cache.values())
    
    async def read_resource(self, uri: str) -> Dict[str, Any]:
        """
        Read a resource from the MCP server.
        
        Args:
            uri: Resource URI to read
            
        Returns:
            Dict[str, Any]: Resource content
            
        Raises:
            MCPResourceNotFoundError: If resource is not found
        """
        if not self.is_connected():
            raise MCPConnectionError(f"Not connected to server '{self.server_name}'")
        
        try:
            result = await self.protocol.call_method(MCPMethods.RESOURCES_READ, {
                "uri": uri
            })
            
            return result
            
        except Exception as e:
            if "not found" in str(e).lower():
                raise MCPResourceNotFoundError(
                    f"Resource '{uri}' not found",
                    resource_uri=uri
                )
            else:
                raise MCPConnectionError(f"Failed to read resource '{uri}': {str(e)}")
    
    async def ping(self) -> bool:
        """
        Ping the MCP server to check if it's responsive.
        
        Returns:
            bool: True if server responds
        """
        if not self.is_connected():
            return False
        
        try:
            result = await self.protocol.call_method(MCPMethods.PING)
            return result.get("pong", False)
        except Exception:
            return False
    
    def get_server_info(self) -> Optional[Dict[str, Any]]:
        """Get server information."""
        return self.server_info
    
    def get_server_capabilities(self) -> Optional[Dict[str, Any]]:
        """Get server capabilities."""
        return self.server_capabilities
    
    def get_state(self) -> str:
        """Get current client state."""
        return self.state
    
    def get_last_error(self) -> Optional[Exception]:
        """Get last error that occurred."""
        return self.last_error
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        return {
            "server_name": self.server_name,
            "state": self.state,
            "connection_attempts": self.connection_attempts,
            "cached_tools": len(self.tools_cache),
            "cached_resources": len(self.resources_cache),
            "cached_results": len(self.result_cache),
            "last_error": str(self.last_error) if self.last_error else None,
            "server_info": self.server_info,
            "server_capabilities": self.server_capabilities
        }