"""
MCP server manager for handling multiple MCP server connections.

This module provides centralized management of multiple MCP servers,
including connection management, health monitoring, and tool discovery.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Set, AsyncGenerator, Callable
from pathlib import Path
import time

from .client import MCPClient, MCPClientState
from .config import MCPConfigManager, MCPConfig, MCPServerConfig
from .protocol import MCPTool, MCPResource, MCPResult
from .discovery import MCPToolDiscovery, ToolMetadata
from .health import MCPHealthMonitor, HealthMetrics, HealthStatus
from .exceptions import (
    MCPConnectionError, MCPConfigurationError, MCPToolNotFoundError
)

logger = logging.getLogger(__name__)


class MCPServerStatus:
    """Status information for an MCP server."""
    
    def __init__(self, name: str, client: MCPClient):
        self.name = name
        self.client = client
        self.connected = client.is_connected()
        self.state = client.get_state()
        self.last_error = client.get_last_error()
        self.tools_count = len(client.tools_cache)
        self.resources_count = len(client.resources_cache)
        self.server_info = client.get_server_info()
        self.server_capabilities = client.get_server_capabilities()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert status to dictionary."""
        return {
            "name": self.name,
            "connected": self.connected,
            "state": self.state,
            "last_error": str(self.last_error) if self.last_error else None,
            "tools_count": self.tools_count,
            "resources_count": self.resources_count,
            "server_info": self.server_info,
            "server_capabilities": self.server_capabilities
        }


class MCPServerManager:
    """
    Manager for multiple MCP server connections.
    
    This class provides centralized management of MCP servers including:
    - Configuration loading and management
    - Connection lifecycle management
    - Health monitoring and auto-reconnection
    - Tool discovery and routing
    - Concurrent operations coordination
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        self.config_manager = MCPConfigManager(config_path)
        self.config: Optional[MCPConfig] = None
        
        # Server management
        self.servers: Dict[str, MCPClient] = {}
        self.connection_locks: Dict[str, asyncio.Lock] = {}
        
        # Concurrency control
        self.executor = asyncio.Semaphore(10)  # Limit concurrent operations
        
        # Health monitoring system
        self.health_monitor = MCPHealthMonitor(check_interval=30, recovery_enabled=True)
        self._shutdown_event = asyncio.Event()
        
        # Tool discovery system
        self.tool_discovery = MCPToolDiscovery(cache_ttl=300)  # 5 minutes
    
    async def start(self) -> None:
        """Start the server manager and load configuration."""
        logger.info("Starting MCP server manager")
        
        try:
            # Load configuration
            await self.load_config()
            
            # Start health monitoring
            await self.health_monitor.start_monitoring()
            
            logger.info("MCP server manager started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start MCP server manager: {str(e)}")
            raise
    
    async def stop(self) -> None:
        """Stop the server manager and disconnect all servers."""
        logger.info("Stopping MCP server manager")
        
        # Signal shutdown
        self._shutdown_event.set()
        
        # Stop health monitoring
        await self.health_monitor.stop_monitoring()
        
        # Disconnect all servers
        await self.disconnect_all_servers()
        
        logger.info("MCP server manager stopped")
    
    async def load_config(self) -> None:
        """Load MCP configuration from file."""
        try:
            self.config = await self.config_manager.load_config()
            
            if self.config.mcp.enabled:
                # Update health monitor configuration
                self.health_monitor.check_interval = self.config.mcp.health_check_interval
                
                # Load enabled servers
                await self.load_servers_from_config()
            else:
                logger.info("MCP is disabled in configuration")
                
        except Exception as e:
            raise MCPConfigurationError(f"Failed to load MCP configuration: {str(e)}")
    
    async def load_servers_from_config(self) -> None:
        """Load MCP servers from configuration."""
        if not self.config:
            raise MCPConfigurationError("No configuration loaded")
        
        enabled_servers = self.config.get_enabled_servers()
        logger.info(f"Loading {len(enabled_servers)} enabled servers from configuration")
        
        # Add servers
        for server_name, server_config in enabled_servers.items():
            try:
                await self.add_server(server_name, server_config)
            except Exception as e:
                logger.error(f"Failed to add server '{server_name}': {str(e)}")
    
    async def add_server(self, name: str, config: MCPServerConfig) -> bool:
        """
        Add a new MCP server.
        
        Args:
            name: Server name
            config: Server configuration
            
        Returns:
            bool: True if server was added successfully
        """
        if name in self.servers:
            logger.warning(f"Server '{name}' already exists")
            return False
        
        try:
            # Create client
            client = MCPClient(config)
            
            # Create connection lock
            self.connection_locks[name] = asyncio.Lock()
            
            # Store client
            self.servers[name] = client
            
            logger.info(f"Added MCP server '{name}'")
            
            # Try to connect
            await self.connect_server(name)
            
            # Add to health monitoring
            await self.health_monitor.add_server(name, client)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to add server '{name}': {str(e)}")
            
            # Cleanup on failure
            if name in self.servers:
                del self.servers[name]
            if name in self.connection_locks:
                del self.connection_locks[name]
            
            return False
    
    async def remove_server(self, name: str) -> bool:
        """
        Remove an MCP server.
        
        Args:
            name: Server name
            
        Returns:
            bool: True if server was removed
        """
        if name not in self.servers:
            return False
        
        try:
            # Disconnect server
            await self.disconnect_server(name)
            
            # Remove from health monitoring
            await self.health_monitor.remove_server(name)
            
            # Remove from collections
            del self.servers[name]
            del self.connection_locks[name]
            
            # Clear discovery data
            await self.tool_discovery.refresh_tool_cache(name)
            
            logger.info(f"Removed MCP server '{name}'")
            return True
            
        except Exception as e:
            logger.error(f"Failed to remove server '{name}': {str(e)}")
            return False
    
    async def connect_server(self, name: str) -> bool:
        """
        Connect to a specific MCP server.
        
        Args:
            name: Server name
            
        Returns:
            bool: True if connection successful
        """
        if name not in self.servers:
            raise MCPConnectionError(f"Server '{name}' not found")
        
        client = self.servers[name]
        lock = self.connection_locks[name]
        
        async with lock:
            try:
                logger.info(f"Connecting to server '{name}'")
                success = await client.connect()
                
                if success:
                    logger.info(f"Successfully connected to server '{name}'")
                    # Discover tools from the newly connected server
                    try:
                        await self.tool_discovery.discover_server_tools(name, client)
                    except Exception as e:
                        logger.warning(f"Failed to discover tools from server '{name}': {str(e)}")
                else:
                    logger.warning(f"Failed to connect to server '{name}'")
                
                return success
                
            except Exception as e:
                logger.error(f"Error connecting to server '{name}': {str(e)}")
                return False
    
    async def disconnect_server(self, name: str) -> bool:
        """
        Disconnect from a specific MCP server.
        
        Args:
            name: Server name
            
        Returns:
            bool: True if disconnection successful
        """
        if name not in self.servers:
            return False
        
        client = self.servers[name]
        lock = self.connection_locks[name]
        
        async with lock:
            try:
                await client.disconnect()
                logger.info(f"Disconnected from server '{name}'")
                return True
            except Exception as e:
                logger.error(f"Error disconnecting from server '{name}': {str(e)}")
                return False
    
    async def disconnect_all_servers(self) -> None:
        """Disconnect from all MCP servers."""
        logger.info("Disconnecting from all servers")
        
        disconnect_tasks = []
        for server_name in list(self.servers.keys()):
            task = asyncio.create_task(self.disconnect_server(server_name))
            disconnect_tasks.append(task)
        
        if disconnect_tasks:
            await asyncio.gather(*disconnect_tasks, return_exceptions=True)
    
    async def restart_server(self, name: str) -> bool:
        """
        Restart a specific MCP server.
        
        Args:
            name: Server name
            
        Returns:
            bool: True if restart successful
        """
        logger.info(f"Restarting server '{name}'")
        
        # Disconnect first
        await self.disconnect_server(name)
        
        # Wait a bit before reconnecting
        await asyncio.sleep(1)
        
        # Reconnect
        return await self.connect_server(name)
    
    def list_servers(self) -> List[str]:
        """
        Get list of all server names.
        
        Returns:
            List[str]: List of server names
        """
        return list(self.servers.keys())
    
    def get_server_status(self, name: str) -> Optional[MCPServerStatus]:
        """
        Get status of a specific server.
        
        Args:
            name: Server name
            
        Returns:
            Optional[MCPServerStatus]: Server status or None if not found
        """
        if name not in self.servers:
            return None
        
        client = self.servers[name]
        return MCPServerStatus(name, client)
    
    def get_all_server_status(self) -> Dict[str, MCPServerStatus]:
        """
        Get status of all servers.
        
        Returns:
            Dict[str, MCPServerStatus]: Mapping of server names to status
        """
        return {
            name: MCPServerStatus(name, client)
            for name, client in self.servers.items()
        }
    
    async def get_all_tools(self) -> Dict[str, List[MCPTool]]:
        """
        Get all tools from all connected servers.
        
        Returns:
            Dict[str, List[MCPTool]]: Mapping of server names to their tools
        """
        return await self.tool_discovery.discover_all_tools(self)
    
    async def find_tool(self, tool_name: str) -> Optional[tuple[str, MCPTool]]:
        """
        Find a tool by name across all servers.
        
        Args:
            tool_name: Name of the tool to find
            
        Returns:
            Optional[tuple[str, MCPTool]]: Tuple of (server_name, tool) or None
        """
        # Use tool discovery system for better search
        matches = await self.tool_discovery.find_tools_by_name(tool_name, fuzzy=False)
        if matches:
            metadata = matches[0]  # Get the best match
            return (metadata.server_name, metadata.tool)
        
        return None
    
    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> MCPResult:
        """
        Call a tool on a specific server.
        
        Args:
            server_name: Name of the server
            tool_name: Name of the tool
            arguments: Tool arguments
            
        Returns:
            MCPResult: Tool execution result
            
        Raises:
            MCPConnectionError: If server not found or not connected
            MCPToolNotFoundError: If tool not found
        """
        if server_name not in self.servers:
            raise MCPConnectionError(f"Server '{server_name}' not found")
        
        client = self.servers[server_name]
        
        if not client.is_connected():
            # Try to reconnect
            success = await self.connect_server(server_name)
            if not success:
                raise MCPConnectionError(f"Server '{server_name}' is not connected and reconnection failed")
        
        # Use semaphore to limit concurrent calls
        async with self.executor:
            start_time = time.time()
            try:
                # Call tool directly using standard MCP client
                result = await client.call_tool(tool_name, arguments)
                
                execution_time = time.time() - start_time
                
                # Record tool usage statistics
                self.tool_discovery.record_tool_usage(tool_name, result.success, execution_time)
                
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                # Record failed usage
                self.tool_discovery.record_tool_usage(tool_name, False, execution_time)
                raise

    async def call_tool_async(
        self,
        server_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
        progress_callback: Optional[Callable] = None,
        timeout: Optional[float] = None
    ) -> AsyncGenerator[MCPResult, None]:
        """
        异步调用工具，支持进度回传和长时间运行任务。

        Args:
            server_name: 服务器名称
            tool_name: 工具名称
            arguments: 工具参数
            progress_callback: 进度回调函数
            timeout: 超时时间（秒）

        Yields:
            MCPResult: 进度更新和最终结果

        Raises:
            MCPConnectionError: 如果服务器未找到或未连接
            MCPToolNotFoundError: 如果工具未找到
        """
        if server_name not in self.servers:
            raise MCPConnectionError(f"Server '{server_name}' not found")

        client = self.servers[server_name]

        if not client.is_connected():
            # 尝试重连
            success = await self.connect_server(server_name)
            if not success:
                raise MCPConnectionError(f"Server '{server_name}' is not connected and reconnection failed")

        # 使用信号量限制并发调用
        async with self.executor:
            start_time = time.time()
            success = False
            try:
                logger.info(f"Starting async tool call '{tool_name}' on server '{server_name}'")

                # 使用客户端的异步调用
                async for result in client.call_tool_async(
                    tool_name=tool_name,
                    arguments=arguments,
                    progress_callback=progress_callback,
                    timeout=timeout
                ):
                    # 记录成功状态（在最终结果时）
                    if result.metadata and result.metadata.get("type") == "final_result":
                        success = result.success
                        execution_time = time.time() - start_time
                        self.tool_discovery.record_tool_usage(tool_name, success, execution_time)

                    yield result

            except Exception as e:
                execution_time = time.time() - start_time
                # 记录失败的使用情况
                self.tool_discovery.record_tool_usage(tool_name, False, execution_time)
                logger.error(f"Async tool call failed for '{tool_name}' on '{server_name}': {str(e)}")

                # 返回错误结果
                yield MCPResult(
                    success=False,
                    error=str(e),
                    metadata={
                        "server_name": server_name,
                        "tool_name": tool_name,
                        "error_type": type(e).__name__,
                        "execution_time": execution_time,
                        "async_call": True
                    }
                )

    async def call_tool_any_server(self, tool_name: str, arguments: Dict[str, Any]) -> MCPResult:
        """
        Call a tool on any server that has it.
        
        Args:
            tool_name: Name of the tool
            arguments: Tool arguments
            
        Returns:
            MCPResult: Tool execution result
            
        Raises:
            MCPToolNotFoundError: If tool not found on any server
        """
        # Find the tool
        server_tool = await self.find_tool(tool_name)
        if not server_tool:
            raise MCPToolNotFoundError(f"Tool '{tool_name}' not found on any server")
        
        server_name, _ = server_tool
        return await self.call_tool(server_name, tool_name, arguments)
    
    async def search_tools(self, query: str, fuzzy: bool = True) -> List[ToolMetadata]:
        """
        Search for tools using various strategies.
        
        Args:
            query: Search query
            fuzzy: Whether to use fuzzy matching
            
        Returns:
            List[ToolMetadata]: List of matching tools
        """
        # Try exact name match first
        name_matches = await self.tool_discovery.find_tools_by_name(query, fuzzy=False)
        if name_matches:
            return name_matches
        
        # Try fuzzy name match
        if fuzzy:
            fuzzy_matches = await self.tool_discovery.find_tools_by_name(query, fuzzy=True)
            if fuzzy_matches:
                return fuzzy_matches
        
        # Try description search
        keywords = query.lower().split()
        description_matches = await self.tool_discovery.find_tools_by_description(keywords)
        return description_matches
    
    async def get_tool_recommendations(self, context: Dict[str, Any] = None) -> List[ToolMetadata]:
        """
        Get tool recommendations based on usage patterns and context.
        
        Args:
            context: Optional context for recommendations
            
        Returns:
            List[ToolMetadata]: Recommended tools
        """
        return await self.tool_discovery.get_tool_recommendations(context or {})
    
    async def get_tools_by_category(self, category: str) -> List[ToolMetadata]:
        """
        Get tools by category.
        
        Args:
            category: Category name (e.g., 'file', 'git', 'database')
            
        Returns:
            List[ToolMetadata]: Tools in the category
        """
        return await self.tool_discovery.find_tools_by_category(category)
    
    async def refresh_tool_discovery(self, server_name: Optional[str] = None) -> None:
        """
        Refresh tool discovery cache.
        
        Args:
            server_name: Specific server to refresh, or None for all
        """
        await self.tool_discovery.refresh_tool_cache(server_name)
    
    def get_server_health(self, server_name: str) -> Optional[HealthMetrics]:
        """
        Get health metrics for a specific server.
        
        Args:
            server_name: Name of the server
            
        Returns:
            Optional[HealthMetrics]: Health metrics or None if not found
        """
        return self.health_monitor.get_server_health(server_name)
    
    def get_all_health_metrics(self) -> Dict[str, HealthMetrics]:
        """
        Get health metrics for all servers.
        
        Returns:
            Dict[str, HealthMetrics]: Mapping of server names to health metrics
        """
        return self.health_monitor.get_all_health_metrics()
    
    def get_unhealthy_servers(self) -> List[str]:
        """
        Get list of unhealthy server names.
        
        Returns:
            List[str]: List of server names with health issues
        """
        return self.health_monitor.get_unhealthy_servers()
    
    def add_health_alert_callback(self, callback: callable) -> None:
        """
        Add a callback for health alerts.
        
        Args:
            callback: Function to call when health alerts are triggered
        """
        self.health_monitor.add_alert_callback(callback)
    
    def remove_health_alert_callback(self, callback: callable) -> None:
        """
        Remove a health alert callback.
        
        Args:
            callback: Callback function to remove
        """
        self.health_monitor.remove_alert_callback(callback)

    def get_manager_stats(self) -> Dict[str, Any]:
        """Get manager statistics."""
        connected_count = sum(1 for client in self.servers.values() if client.is_connected())
        discovery_stats = self.tool_discovery.get_discovery_stats()
        health_stats = self.health_monitor.get_monitoring_stats()
        
        return {
            "total_servers": len(self.servers),
            "connected_servers": connected_count,
            "discovery": discovery_stats,
            "health_monitoring": health_stats,
            "servers": {
                name: client.get_stats()
                for name, client in self.servers.items()
            }
        }