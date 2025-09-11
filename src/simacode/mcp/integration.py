"""
MCP Integration with SimaCode Tool System

This module provides seamless integration between MCP tools and the core
SimaCode tool system, enabling unified tool management and execution.
"""

import asyncio
import logging
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any, AsyncGenerator, Type
from pathlib import Path

from ..tools.base import Tool, ToolInput, ToolResult
from ..permissions import PermissionManager
from .server_manager import MCPServerManager
from .tool_registry import MCPToolRegistry
from .tool_wrapper import MCPToolWrapper
from .config import MCPConfigManager

logger = logging.getLogger(__name__)


class MCPStateManager:
    """
    Manages MCP initialization state persistence across CLI commands.
    """
    
    def __init__(self, state_dir: Optional[Path] = None):
        """Initialize state manager with optional custom state directory."""
        if state_dir is None:
            # Use project-local .simacode directory instead of user config
            self.state_dir = Path.cwd() / '.simacode' / 'mcp'
        else:
            self.state_dir = state_dir
        
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / 'initialization_state.json'
    
    def save_initialization_state(self, config_path: Optional[Path] = None) -> None:
        """Save MCP initialization state to disk."""
        try:
            state = {
                'initialized': True,
                'config_path': str(config_path) if config_path else None,
                'timestamp': datetime.now().isoformat()
            }
            
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
                
            logger.debug(f"Saved MCP initialization state to {self.state_file}")
            
        except Exception as e:
            logger.error(f"Failed to save MCP initialization state: {str(e)}")
    
    def load_initialization_state(self) -> Dict[str, Any]:
        """Load MCP initialization state from disk."""
        try:
            if not self.state_file.exists():
                return {'initialized': False}
            
            with open(self.state_file, 'r') as f:
                state = json.load(f)
            
            logger.debug(f"Loaded MCP initialization state from {self.state_file}")
            return state
            
        except Exception as e:
            logger.error(f"Failed to load MCP initialization state: {str(e)}")
            return {'initialized': False}
    
    def clear_initialization_state(self) -> None:
        """Clear MCP initialization state."""
        try:
            if self.state_file.exists():
                self.state_file.unlink()
                logger.debug("Cleared MCP initialization state")
        except Exception as e:
            logger.error(f"Failed to clear MCP initialization state: {str(e)}")
    
    def is_initialized(self) -> bool:
        """Check if MCP is initialized based on saved state."""
        state = self.load_initialization_state()
        return state.get('initialized', False)
    
    def get_config_path(self) -> Optional[Path]:
        """Get the config path from saved state."""
        state = self.load_initialization_state()
        config_path_str = state.get('config_path')
        return Path(config_path_str) if config_path_str else None


class SimaCodeToolRegistry:
    """
    Extended tool registry that includes both built-in and MCP tools.
    
    This class serves as a unified interface for all tools in SimaCode,
    regardless of whether they are built-in or come from MCP servers.
    """
    
    def __init__(self, permission_manager: Optional[PermissionManager] = None, session_manager=None):
        """Initialize the unified tool registry."""
        self.permission_manager = permission_manager or PermissionManager()
        self.session_manager = session_manager
        
        # Built-in tools registry
        self.builtin_tools: Dict[str, Tool] = {}
        
        # MCP components (initialized later)
        self.mcp_server_manager: Optional[MCPServerManager] = None
        self.mcp_tool_registry: Optional[MCPToolRegistry] = None
        self.mcp_enabled = False
        
        # Combined tool index
        self._tool_cache: Dict[str, Tool] = {}
        self._cache_dirty = True
        
        # State management
        self.state_manager = MCPStateManager()
        
        # Auto-initialize MCP if previously initialized
        self._auto_initialize_from_state()
    
    def _auto_initialize_from_state(self) -> None:
        """Mark that MCP should be auto-initialized based on saved state."""
        if self.state_manager.is_initialized():
            logger.debug("Detected previous MCP initialization, will auto-initialize on first access")
            # Don't initialize immediately, just mark for lazy loading
    
    async def _ensure_mcp_initialized(self) -> bool:
        """Ensure MCP is initialized, auto-initializing if needed."""
        if self.mcp_enabled:
            return True
        
        # Prevent duplicate initialization attempts
        if hasattr(self, '_initializing_mcp') and self._initializing_mcp:
            logger.debug("MCP initialization already in progress, skipping")
            return False
        
        # Check if we should auto-initialize
        if self.state_manager.is_initialized():
            logger.debug("Auto-initializing MCP from saved state...")
            config_path = self.state_manager.get_config_path()
            self._initializing_mcp = True
            try:
                result = await self.initialize_mcp(config_path)
                return result
            finally:
                self._initializing_mcp = False
        
        return False
    
    async def initialize_mcp(self, config_path: Optional[Path] = None) -> bool:
        """
        Initialize MCP integration.
        
        Args:
            config_path: Optional path to MCP configuration file
            
        Returns:
            bool: True if MCP was successfully initialized
        """
        # Skip if already enabled
        if self.mcp_enabled:
            logger.debug("MCP integration already initialized, skipping")
            return True
            
        try:
            logger.info("Initializing MCP integration")
            
            # Initialize MCP server manager
            self.mcp_server_manager = MCPServerManager(config_path)
            await self.mcp_server_manager.start()
            
            # Initialize MCP tool registry
            self.mcp_tool_registry = MCPToolRegistry(
                self.mcp_server_manager,
                self.permission_manager,
                auto_register=True,
                session_manager=self.session_manager
            )
            
            # Set up callbacks for cache management
            self.mcp_tool_registry.add_registration_callback(self._on_mcp_tool_registered)
            self.mcp_tool_registry.add_unregistration_callback(self._on_mcp_tool_unregistered)
            
            # Start MCP tool registry
            await self.mcp_tool_registry.start()
            
            self.mcp_enabled = True
            self._invalidate_cache()
            
            # Save initialization state
            self.state_manager.save_initialization_state(config_path)
            
            logger.info("MCP integration initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize MCP integration: {str(e)}")
            await self._cleanup_mcp()
            return False
    
    async def shutdown_mcp(self) -> None:
        """Shutdown MCP integration."""
        if self.mcp_enabled:
            logger.info("Shutting down MCP integration")
            await self._cleanup_mcp()
    
    async def _cleanup_mcp(self) -> None:
        """Clean up MCP resources."""
        try:
            if self.mcp_tool_registry:
                await self.mcp_tool_registry.stop()
                self.mcp_tool_registry = None
            
            if self.mcp_server_manager:
                await self.mcp_server_manager.stop()
                self.mcp_server_manager = None
            
            self.mcp_enabled = False
            self._invalidate_cache()
            
            # Clear initialization state
            self.state_manager.clear_initialization_state()
            
        except Exception as e:
            logger.error(f"Error during MCP cleanup: {str(e)}")
    
    def register_builtin_tool(self, tool: Tool) -> bool:
        """
        Register a built-in SimaCode tool.
        
        Args:
            tool: Tool instance to register
            
        Returns:
            bool: True if registration successful
        """
        if tool.name in self.builtin_tools:
            logger.warning(f"Built-in tool '{tool.name}' already registered")
            return False
        
        self.builtin_tools[tool.name] = tool
        self._invalidate_cache()
        
        logger.debug(f"Registered built-in tool: {tool.name}")
        return True
    
    def unregister_builtin_tool(self, tool_name: str) -> bool:
        """
        Unregister a built-in tool.
        
        Args:
            tool_name: Name of tool to unregister
            
        Returns:
            bool: True if tool was unregistered
        """
        if tool_name not in self.builtin_tools:
            return False
        
        del self.builtin_tools[tool_name]
        self._invalidate_cache()
        
        logger.debug(f"Unregistered built-in tool: {tool_name}")
        return True
    
    def get_tool(self, tool_name: str) -> Optional[Tool]:
        """
        Get a tool by name (built-in or MCP).
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Optional[Tool]: Tool instance if found
        """
        self._refresh_cache_if_needed()
        return self._tool_cache.get(tool_name)
    
    async def list_tools(self, include_mcp: bool = True, include_builtin: bool = True) -> List[str]:
        """
        List all available tools.
        
        Args:
            include_mcp: Whether to include MCP tools
            include_builtin: Whether to include built-in tools
            
        Returns:
            List[str]: List of tool names
        """
        tools = []
        
        if include_builtin:
            tools.extend(self.builtin_tools.keys())
        
        if include_mcp:
            # Ensure MCP is initialized if needed
            await self._ensure_mcp_initialized()
            
            if self.mcp_enabled and self.mcp_tool_registry:
                tools.extend(self.mcp_tool_registry.list_registered_tools())
        
        return sorted(tools)
    
    def list_tools_by_category(self, category: str) -> List[str]:
        """
        List tools by category.
        
        Args:
            category: Tool category (e.g. 'file', 'git', 'database')
            
        Returns:
            List[str]: List of tool names in the category
        """
        tools = []
        
        # Check built-in tools (basic categorization by name)
        for tool_name in self.builtin_tools.keys():
            if self._tool_matches_category(tool_name, category):
                tools.append(tool_name)
        
        # Check MCP tools using discovery system
        if self.mcp_enabled and self.mcp_server_manager:
            try:
                mcp_tools = asyncio.create_task(
                    self.mcp_server_manager.get_tools_by_category(category)
                )
                # Note: This is a sync method, so we can't await here
                # In practice, this would need to be an async method
            except Exception as e:
                logger.warning(f"Failed to get MCP tools by category '{category}': {str(e)}")
        
        return sorted(tools)
    
    def _tool_matches_category(self, tool_name: str, category: str) -> bool:
        """Simple category matching for built-in tools."""
        category_keywords = {
            "file": ["file", "read", "write"],
            "git": ["git"],
            "system": ["bash", "shell", "system"],
            "network": ["http", "api", "web"],
        }
        
        keywords = category_keywords.get(category.lower(), [])
        return any(keyword in tool_name.lower() for keyword in keywords)
    
    async def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a tool.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Optional[Dict[str, Any]]: Tool information
        """
        # Check built-in tools
        if tool_name in self.builtin_tools:
            tool = self.builtin_tools[tool_name]
            return {
                "name": tool.name,
                "description": tool.description,
                "version": tool.version,
                "type": "builtin",
                "metadata": tool.metadata
            }
        
        # Ensure MCP is initialized for tool info lookup
        await self._ensure_mcp_initialized()
        
        # Check MCP tools
        if self.mcp_enabled and self.mcp_tool_registry:
            mcp_info = self.mcp_tool_registry.get_tool_info(tool_name)
            if mcp_info:
                return {
                    **mcp_info,
                    "type": "mcp"
                }
        
        return None
    
    async def execute_tool(
        self,
        tool_name: str,
        input_data: Dict[str, Any]
    ) -> AsyncGenerator[ToolResult, None]:
        """
        Execute a tool with given input.
        
        Args:
            tool_name: Name of tool to execute
            input_data: Input parameters for the tool
            
        Yields:
            ToolResult: Execution results
        """
        # Ensure MCP is initialized before looking up tools
        await self._ensure_mcp_initialized()
        
        tool = self.get_tool(tool_name)
        if not tool:
            yield ToolResult(
                type="error",
                content=f"Tool '{tool_name}' not found",
                tool_name=tool_name
            )
            return
        
        try:
            async for result in tool.run(input_data):
                yield result
        except Exception as e:
            logger.error(f"Tool execution failed for '{tool_name}': {str(e)}")
            yield ToolResult(
                type="error",
                content=f"Tool execution failed: {str(e)}",
                tool_name=tool_name
            )
    
    def search_tools(self, query: str, fuzzy: bool = True) -> List[Dict[str, Any]]:
        """
        Search for tools by name or description.
        
        Args:
            query: Search query
            fuzzy: Whether to use fuzzy matching
            
        Returns:
            List[Dict[str, Any]]: List of matching tools with relevance scores
        """
        results = []
        query_lower = query.lower()
        
        # Search built-in tools
        for tool_name, tool in self.builtin_tools.items():
            score = 0
            
            # Exact name match
            if tool_name.lower() == query_lower:
                score = 100
            elif query_lower in tool_name.lower():
                score = 80
            elif fuzzy and self._fuzzy_match(query_lower, tool_name.lower()):
                score = 60
            
            # Description match
            if query_lower in tool.description.lower():
                score += 20
            
            if score > 0:
                results.append({
                    "tool_name": tool_name,
                    "description": tool.description,
                    "type": "builtin",
                    "score": score
                })
        
        # Search MCP tools using discovery system
        if self.mcp_enabled and self.mcp_server_manager:
            try:
                # This would be async in a real implementation
                # For now, we'll skip MCP search in this sync method
                pass
            except Exception as e:
                logger.warning(f"Failed to search MCP tools: {str(e)}")
        
        # Sort by relevance score
        results.sort(key=lambda x: x["score"], reverse=True)
        return results
    
    def _fuzzy_match(self, query: str, target: str) -> bool:
        """Simple fuzzy matching algorithm."""
        if not query or not target:
            return False
        
        # Check if all characters in query appear in target in order
        query_idx = 0
        for char in target:
            if query_idx < len(query) and char == query[query_idx]:
                query_idx += 1
        
        return query_idx == len(query)
    
    def _on_mcp_tool_registered(self, tool_name: str, tool: MCPToolWrapper) -> None:
        """Callback for when an MCP tool is registered."""
        self._invalidate_cache()
        logger.debug(f"MCP tool registered: {tool_name}")
    
    def _on_mcp_tool_unregistered(self, tool_name: str) -> None:
        """Callback for when an MCP tool is unregistered."""
        self._invalidate_cache()
        logger.debug(f"MCP tool unregistered: {tool_name}")
    
    def _invalidate_cache(self) -> None:
        """Mark the tool cache as dirty."""
        self._cache_dirty = True
    
    def _refresh_cache_if_needed(self) -> None:
        """Refresh the tool cache if it's dirty."""
        if not self._cache_dirty:
            return
        
        self._tool_cache.clear()
        
        # Add built-in tools
        self._tool_cache.update(self.builtin_tools)
        
        # Add MCP tools
        if self.mcp_enabled and self.mcp_tool_registry:
            mcp_tools = self.mcp_tool_registry.registered_tools
            self._tool_cache.update(mcp_tools)
        
        self._cache_dirty = False
    
    def get_registry_stats(self) -> Dict[str, Any]:
        """Get comprehensive registry statistics."""
        # Calculate total tools without async call
        total_tools = len(self.builtin_tools)
        if self.mcp_enabled and self.mcp_tool_registry:
            total_tools += len(self.mcp_tool_registry.registered_tools)
        
        stats = {
            "builtin_tools": len(self.builtin_tools),
            "mcp_enabled": self.mcp_enabled,
            "total_tools": total_tools
        }
        
        if self.mcp_enabled and self.mcp_tool_registry:
            mcp_stats = self.mcp_tool_registry.get_registry_stats()
            stats.update({
                "mcp_tools": mcp_stats["currently_registered"],
                "mcp_servers": mcp_stats["servers_with_tools"],
                "mcp_namespaces": mcp_stats["namespaces"],
                "mcp_stats": mcp_stats
            })
        else:
            stats.update({
                "mcp_tools": 0,
                "mcp_servers": 0,
                "mcp_namespaces": 0
            })
        
        return stats


# Global registry instance (singleton pattern)
_global_registry: Optional[SimaCodeToolRegistry] = None


def get_tool_registry() -> SimaCodeToolRegistry:
    """Get the global tool registry instance."""
    global _global_registry
    if _global_registry is None:
        _global_registry = SimaCodeToolRegistry()
    return _global_registry


async def initialize_mcp_integration(config_path: Optional[Path] = None) -> bool:
    """
    Initialize MCP integration for the global tool registry.
    
    Args:
        config_path: Optional path to MCP configuration file
        
    Returns:
        bool: True if initialization successful
    """
    registry = get_tool_registry()
    return await registry.initialize_mcp(config_path)


async def shutdown_mcp_integration() -> None:
    """Shutdown MCP integration for the global tool registry."""
    registry = get_tool_registry()
    await registry.shutdown_mcp()


def register_builtin_tool(tool: Tool) -> bool:
    """Register a built-in tool with the global registry."""
    registry = get_tool_registry()
    return registry.register_builtin_tool(tool)


def get_tool(tool_name: str) -> Optional[Tool]:
    """Get a tool from the global registry."""
    registry = get_tool_registry()
    return registry.get_tool(tool_name)


async def list_tools(**kwargs) -> List[str]:
    """List all tools from the global registry."""
    registry = get_tool_registry()
    return await registry.list_tools(**kwargs)


async def execute_tool(tool_name: str, input_data: Dict[str, Any]) -> AsyncGenerator[ToolResult, None]:
    """Execute a tool from the global registry."""
    registry = get_tool_registry()
    async for result in registry.execute_tool(tool_name, input_data):
        yield result