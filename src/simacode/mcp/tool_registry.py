"""
MCP Tool Registry for SimaCode Integration

This module provides a comprehensive registry system for managing MCP tools
within the SimaCode ecosystem, including automatic discovery, registration,
namespace management, and dynamic updates.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Set, Any, Callable, Tuple
from datetime import datetime
from pathlib import Path
import re

from ..tools.base import Tool
from ..permissions import PermissionManager
from .server_manager import MCPServerManager
from .tool_wrapper import MCPToolWrapper
from .discovery import MCPToolDiscovery, ToolMetadata
from .protocol import MCPTool
from .exceptions import MCPConfigurationError, MCPConnectionError

logger = logging.getLogger(__name__)


class NamespaceManager:
    """
    Manages tool namespaces to prevent naming conflicts.
    
    This class ensures that MCP tools from different servers
    don't conflict with each other or with built-in tools.
    """
    
    def __init__(self):
        self.namespaces: Dict[str, Set[str]] = {}
        self.tool_to_namespace: Dict[str, str] = {}
        self.reserved_names: Set[str] = {
            "file_read", "file_write", "bash", "python", "git",
            "help", "config", "status", "version"
        }
    
    def create_namespace(self, server_name: str, tools: List[MCPTool]) -> str:
        """
        Create a namespace for a server's tools.
        
        Args:
            server_name: Name of the MCP server
            tools: List of tools from the server
            
        Returns:
            str: Created namespace identifier
        """
        # Sanitize server name for namespace
        namespace = self._sanitize_namespace_name(server_name)
        
        # Ensure namespace is unique
        original_namespace = namespace
        counter = 1
        while namespace in self.namespaces:
            namespace = f"{original_namespace}_{counter}"
            counter += 1
        
        # Register namespace
        self.namespaces[namespace] = set()
        
        # Register tools in namespace
        for tool in tools:
            tool_full_name = f"{namespace}:{tool.name}"
            self.namespaces[namespace].add(tool_full_name)
            self.tool_to_namespace[tool_full_name] = namespace
        
        logger.info(f"Created namespace '{namespace}' for server '{server_name}' with {len(tools)} tools")
        return namespace
    
    def _sanitize_namespace_name(self, name: str) -> str:
        """
        Sanitize server name to create a valid namespace.
        
        Args:
            name: Original server name
            
        Returns:
            str: Sanitized namespace name
        """
        # Convert to lowercase and replace invalid characters
        sanitized = re.sub(r'[^a-z0-9_]', '_', name.lower())
        
        # Remove consecutive underscores
        sanitized = re.sub(r'_+', '_', sanitized)
        
        # Remove leading/trailing underscores
        sanitized = sanitized.strip('_')
        
        # Ensure it doesn't start with a number
        if sanitized and sanitized[0].isdigit():
            sanitized = f"mcp_{sanitized}"
        
        # Fallback if empty
        if not sanitized:
            sanitized = "mcp_server"
        
        return sanitized
    
    def is_name_available(self, tool_name: str, namespace: Optional[str] = None) -> bool:
        """
        Check if a tool name is available.
        
        Args:
            tool_name: Tool name to check
            namespace: Optional namespace context
            
        Returns:
            bool: True if name is available
        """
        # Check reserved names
        if tool_name in self.reserved_names:
            return False
        
        # Check within namespace
        if namespace:
            full_name = f"{namespace}:{tool_name}"
            return full_name not in self.tool_to_namespace
        
        # Check across all namespaces
        return tool_name not in [name.split(':', 1)[1] for name in self.tool_to_namespace.keys()]
    
    def get_namespace_for_tool(self, tool_name: str) -> Optional[str]:
        """Get namespace for a registered tool."""
        return self.tool_to_namespace.get(tool_name)
    
    def list_namespaces(self) -> List[str]:
        """Get list of all registered namespaces."""
        return list(self.namespaces.keys())
    
    def list_tools_in_namespace(self, namespace: str) -> List[str]:
        """Get list of tools in a specific namespace."""
        return list(self.namespaces.get(namespace, set()))
    
    def remove_namespace(self, namespace: str) -> bool:
        """
        Remove a namespace and all its tools.
        
        Args:
            namespace: Namespace to remove
            
        Returns:
            bool: True if namespace was removed
        """
        if namespace not in self.namespaces:
            return False
        
        # Remove tool mappings
        tools_to_remove = list(self.namespaces[namespace])
        for tool_name in tools_to_remove:
            if tool_name in self.tool_to_namespace:
                del self.tool_to_namespace[tool_name]
        
        # Remove namespace
        del self.namespaces[namespace]
        
        logger.info(f"Removed namespace '{namespace}' with {len(tools_to_remove)} tools")
        return True


class MCPToolRegistry:
    """
    Central registry for MCP tools in SimaCode.
    
    This class manages the lifecycle of MCP tools, including discovery,
    registration, updates, and integration with the SimaCode tool system.
    """
    
    def __init__(
        self,
        server_manager: MCPServerManager,
        permission_manager: Optional[PermissionManager] = None,
        auto_register: bool = True,
        session_manager=None
    ):
        """
        Initialize MCP tool registry.
        
        Args:
            server_manager: MCP server manager instance
            permission_manager: Optional permission manager
            auto_register: Whether to automatically register discovered tools
            session_manager: Optional session manager for tool session access
        """
        self.server_manager = server_manager
        self.permission_manager = permission_manager or PermissionManager()
        self.auto_register = auto_register
        self.session_manager = session_manager
        
        # Tool management
        self.registered_tools: Dict[str, MCPToolWrapper] = {}
        self.server_tools: Dict[str, List[str]] = {}  # server -> tool names
        self.namespace_manager = NamespaceManager()
        
        # Event callbacks
        self.registration_callbacks: List[Callable[[str, MCPToolWrapper], None]] = []
        self.unregistration_callbacks: List[Callable[[str], None]] = []
        self.update_callbacks: List[Callable[[str, MCPToolWrapper], None]] = []
        
        # Background tasks
        self.discovery_task: Optional[asyncio.Task] = None
        self.auto_update_enabled = True
        self.update_interval = 300  # 5 minutes
        
        # Statistics
        self.registration_stats = {
            "total_registered": 0,
            "successful_registrations": 0,
            "failed_registrations": 0,
            "auto_discoveries": 0,
            "manual_registrations": 0
        }
    
    async def start(self) -> None:
        """Start the MCP tool registry."""
        logger.info("Starting MCP tool registry")
        
        try:
            # Initial tool discovery and registration
            if self.auto_register:
                await self.discover_and_register_all_tools()
            
            # Start background discovery task
            if self.auto_update_enabled:
                self.discovery_task = asyncio.create_task(self._background_discovery_loop())
            
            logger.info("MCP tool registry started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start MCP tool registry: {str(e)}")
            raise
    
    async def stop(self) -> None:
        """Stop the MCP tool registry."""
        logger.info("Stopping MCP tool registry")
        
        # Stop background task
        if self.discovery_task:
            self.discovery_task.cancel()
            try:
                await self.discovery_task
            except asyncio.CancelledError:
                pass
        
        # Unregister all tools
        await self.unregister_all_tools()
        
        logger.info("MCP tool registry stopped")
    
    async def discover_and_register_all_tools(self) -> int:
        """
        Discover and register tools from all connected MCP servers.
        
        Returns:
            int: Number of tools registered
        """
        logger.info("Discovering and registering tools from all MCP servers")
        
        registered_count = 0
        
        # Get all tools from server manager
        try:
            all_tools = await self.server_manager.get_all_tools()
            
            for server_name, tools in all_tools.items():
                if tools:
                    count = await self.register_server_tools(server_name, tools)
                    registered_count += count
            
            self.registration_stats["auto_discoveries"] += 1
            logger.info(f"Auto-discovery registered {registered_count} tools from {len(all_tools)} servers")
            
        except Exception as e:
            logger.error(f"Failed to discover and register tools: {str(e)}")
            self.registration_stats["failed_registrations"] += 1
        
        return registered_count
    
    async def register_server_tools(self, server_name: str, tools: List[MCPTool]) -> int:
        """
        Register tools from a specific server.
        
        Args:
            server_name: Name of the MCP server
            tools: List of MCP tools to register
            
        Returns:
            int: Number of tools successfully registered
        """
        if not tools:
            return 0
        
        logger.info(f"Registering {len(tools)} tools from server '{server_name}'")
        
        # Create namespace for server tools
        namespace = self.namespace_manager.create_namespace(server_name, tools)
        
        registered_count = 0
        registered_tool_names = []
        
        for tool in tools:
            try:
                # Create tool wrapper
                wrapper = MCPToolWrapper(
                    mcp_tool=tool,
                    server_manager=self.server_manager,
                    permission_manager=self.permission_manager,
                    namespace=namespace,
                    session_manager=self.session_manager
                )
                
                # Register the wrapper
                if await self.register_tool(wrapper):
                    registered_count += 1
                    registered_tool_names.append(wrapper.name)
                
            except Exception as e:
                logger.error(f"Failed to register tool '{tool.name}' from server '{server_name}': {str(e)}")
                self.registration_stats["failed_registrations"] += 1
        
        # Track server tools
        self.server_tools[server_name] = registered_tool_names
        
        logger.info(f"Successfully registered {registered_count}/{len(tools)} tools from server '{server_name}'")
        return registered_count
    
    async def register_tool(self, tool_wrapper: MCPToolWrapper) -> bool:
        """
        Register a single MCP tool wrapper.
        
        Args:
            tool_wrapper: MCP tool wrapper to register
            
        Returns:
            bool: True if registration successful
        """
        tool_name = tool_wrapper.name
        
        try:
            # Check if tool is already registered
            if tool_name in self.registered_tools:
                logger.warning(f"Tool '{tool_name}' is already registered, skipping")
                return False
            
            # Validate tool
            if not await self._validate_tool_for_registration(tool_wrapper):
                logger.warning(f"Tool '{tool_name}' failed validation, skipping registration")
                return False
            
            # Register tool
            self.registered_tools[tool_name] = tool_wrapper
            
            # Update statistics
            self.registration_stats["total_registered"] += 1
            self.registration_stats["successful_registrations"] += 1
            
            # Notify callbacks
            for callback in self.registration_callbacks:
                try:
                    callback(tool_name, tool_wrapper)
                except Exception as e:
                    logger.error(f"Registration callback failed for '{tool_name}': {str(e)}")
            
            logger.debug(f"Successfully registered MCP tool: {tool_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register tool '{tool_name}': {str(e)}")
            self.registration_stats["failed_registrations"] += 1
            return False
    
    async def _validate_tool_for_registration(self, tool_wrapper: MCPToolWrapper) -> bool:
        """
        Validate a tool before registration.
        
        Args:
            tool_wrapper: Tool wrapper to validate
            
        Returns:
            bool: True if tool is valid for registration
        """
        # Check tool name format
        if not tool_wrapper.name or not isinstance(tool_wrapper.name, str):
            return False
        
        # Check if server is still connected
        server_health = self.server_manager.get_server_health(tool_wrapper.server_name)
        if not server_health or server_health.status.value in ["failed", "critical"]:
            logger.warning(f"Server '{tool_wrapper.server_name}' is unhealthy, skipping tool registration")
            return False
        
        # Check permissions
        try:
            # Basic permission check (tool-specific validation happens during execution)
            return True
        except Exception as e:
            logger.error(f"Permission validation failed for tool '{tool_wrapper.name}': {str(e)}")
            return False
    
    async def unregister_tool(self, tool_name: str) -> bool:
        """
        Unregister a specific tool.
        
        Args:
            tool_name: Name of tool to unregister
            
        Returns:
            bool: True if tool was unregistered
        """
        if tool_name not in self.registered_tools:
            return False
        
        try:
            # Remove from registry
            del self.registered_tools[tool_name]
            
            # Remove from server tools tracking
            for server_name, tool_names in self.server_tools.items():
                if tool_name in tool_names:
                    tool_names.remove(tool_name)
                    break
            
            # Notify callbacks
            for callback in self.unregistration_callbacks:
                try:
                    callback(tool_name)
                except Exception as e:
                    logger.error(f"Unregistration callback failed for '{tool_name}': {str(e)}")
            
            logger.debug(f"Successfully unregistered tool: {tool_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unregister tool '{tool_name}': {str(e)}")
            return False
    
    async def unregister_server_tools(self, server_name: str) -> int:
        """
        Unregister all tools from a specific server.
        
        Args:
            server_name: Name of the server
            
        Returns:
            int: Number of tools unregistered
        """
        if server_name not in self.server_tools:
            return 0
        
        tool_names = list(self.server_tools[server_name])
        unregistered_count = 0
        
        for tool_name in tool_names:
            if await self.unregister_tool(tool_name):
                unregistered_count += 1
        
        # Remove server from tracking
        if server_name in self.server_tools:
            del self.server_tools[server_name]
        
        # Remove namespace
        namespace = self.namespace_manager._sanitize_namespace_name(server_name)
        self.namespace_manager.remove_namespace(namespace)
        
        logger.info(f"Unregistered {unregistered_count} tools from server '{server_name}'")
        return unregistered_count
    
    async def unregister_all_tools(self) -> int:
        """
        Unregister all MCP tools.
        
        Returns:
            int: Number of tools unregistered
        """
        tool_names = list(self.registered_tools.keys())
        unregistered_count = 0
        
        for tool_name in tool_names:
            if await self.unregister_tool(tool_name):
                unregistered_count += 1
        
        # Clear tracking
        self.server_tools.clear()
        
        logger.info(f"Unregistered all {unregistered_count} MCP tools")
        return unregistered_count
    
    async def refresh_server_tools(self, server_name: str) -> Tuple[int, int]:
        """
        Refresh tools for a specific server.
        
        Args:
            server_name: Name of the server to refresh
            
        Returns:
            Tuple[int, int]: (unregistered_count, registered_count)
        """
        logger.info(f"Refreshing tools for server '{server_name}'")
        
        # Unregister existing tools
        unregistered_count = await self.unregister_server_tools(server_name)
        
        # Discover and register new tools
        try:
            all_tools = await self.server_manager.get_all_tools()
            server_tools = all_tools.get(server_name, [])
            registered_count = await self.register_server_tools(server_name, server_tools)
            
            logger.info(f"Refreshed server '{server_name}': unregistered {unregistered_count}, registered {registered_count}")
            return unregistered_count, registered_count
            
        except Exception as e:
            logger.error(f"Failed to refresh tools for server '{server_name}': {str(e)}")
            return unregistered_count, 0
    
    def get_registered_tool(self, tool_name: str) -> Optional[MCPToolWrapper]:
        """Get a registered tool by name."""
        return self.registered_tools.get(tool_name)
    
    def list_registered_tools(self) -> List[str]:
        """Get list of all registered tool names."""
        return list(self.registered_tools.keys())
    
    def list_server_tools(self, server_name: str) -> List[str]:
        """Get list of tools from a specific server."""
        return self.server_tools.get(server_name, [])
    
    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a registered tool.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Optional[Dict[str, Any]]: Tool information or None if not found
        """
        tool = self.registered_tools.get(tool_name)
        if not tool:
            return None
        
        return {
            **tool.get_mcp_info(),
            "registered_at": tool.created_at.isoformat(),
            "namespace": self.namespace_manager.get_namespace_for_tool(tool_name),
            "is_healthy": self._is_tool_healthy(tool)
        }
    
    def _is_tool_healthy(self, tool: MCPToolWrapper) -> bool:
        """Check if a tool's server is healthy."""
        health = self.server_manager.get_server_health(tool.server_name)
        return health is not None and health.status.value not in ["failed", "critical"]
    
    def add_registration_callback(self, callback: Callable[[str, MCPToolWrapper], None]) -> None:
        """Add a callback for tool registration events."""
        self.registration_callbacks.append(callback)
    
    def add_unregistration_callback(self, callback: Callable[[str], None]) -> None:
        """Add a callback for tool unregistration events."""
        self.unregistration_callbacks.append(callback)
    
    def add_update_callback(self, callback: Callable[[str, MCPToolWrapper], None]) -> None:
        """Add a callback for tool update events."""
        self.update_callbacks.append(callback)
    
    async def _background_discovery_loop(self) -> None:
        """Background loop for automatic tool discovery and updates."""
        logger.info("Starting background tool discovery loop")
        
        while True:
            try:
                await asyncio.sleep(self.update_interval)
                
                # Check for server changes
                await self._check_for_server_changes()
                
                # Discover new tools
                if self.auto_register:
                    await self.discover_and_register_all_tools()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in background discovery loop: {str(e)}")
                await asyncio.sleep(30)  # Wait before retrying
    
    async def _check_for_server_changes(self) -> None:
        """Check for changes in MCP servers and update tool registrations."""
        current_servers = set(self.server_manager.list_servers())
        registered_servers = set(self.server_tools.keys())
        
        # Check for removed servers
        removed_servers = registered_servers - current_servers
        for server_name in removed_servers:
            logger.info(f"Server '{server_name}' removed, unregistering tools")
            await self.unregister_server_tools(server_name)
        
        # Check for server health changes
        for server_name in current_servers.intersection(registered_servers):
            health = self.server_manager.get_server_health(server_name)
            if health and health.status.value in ["failed", "critical"]:
                # Server became unhealthy, consider unregistering tools
                logger.warning(f"Server '{server_name}' became unhealthy, tools may be unavailable")
    
    def get_registry_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        healthy_tools = sum(1 for tool in self.registered_tools.values() if self._is_tool_healthy(tool))
        
        return {
            **self.registration_stats,
            "currently_registered": len(self.registered_tools),
            "healthy_tools": healthy_tools,
            "unhealthy_tools": len(self.registered_tools) - healthy_tools,
            "servers_with_tools": len(self.server_tools),
            "namespaces": len(self.namespace_manager.list_namespaces()),
            "auto_update_enabled": self.auto_update_enabled,
            "update_interval": self.update_interval,
            "callbacks": {
                "registration": len(self.registration_callbacks),
                "unregistration": len(self.unregistration_callbacks),
                "update": len(self.update_callbacks)
            }
        }