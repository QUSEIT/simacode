"""
MCP Integration for ReAct Engine

This module provides integration between the ReAct engine and MCP tools,
allowing the AI to automatically discover and use MCP tools during reasoning
and task execution.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, AsyncGenerator
from pathlib import Path

from ..mcp.integration import SimaCodeToolRegistry, initialize_mcp_integration
from ..tools.base import Tool, ToolResult, ToolResultType
from ..react.engine import ReActEngine

logger = logging.getLogger(__name__)


class MCPReActIntegration:
    """
    Integration layer between MCP tools and ReAct engine.
    
    This class manages the registration of MCP tools with the ReAct engine,
    providing a bridge between the MCP tool system and the AI reasoning system.
    """
    
    def __init__(self, react_engine: ReActEngine, mcp_config_path: Optional[Path] = None):
        """
        Initialize MCP-ReAct integration.
        
        Args:
            react_engine: The ReAct engine instance
            mcp_config_path: Optional path to MCP configuration file
        """
        self.react_engine = react_engine
        self.mcp_config_path = mcp_config_path
        # Pass session_manager from react_engine to MCP tool registry
        session_manager = getattr(react_engine, 'session_manager', None)
        self.tool_registry = SimaCodeToolRegistry(session_manager=session_manager)
        self.is_initialized = False
        
        logger.info("MCP-ReAct integration initialized")
    
    async def initialize(self) -> bool:
        """
        Initialize MCP integration and register tools with ReAct engine.
        
        Returns:
            bool: True if initialization successful
        """
        try:
            logger.info("Initializing MCP integration for ReAct engine...")
            
            # Initialize MCP integration
            success = await initialize_mcp_integration(self.mcp_config_path)
            
            if not success:
                logger.warning("MCP integration failed to initialize")
                return False
            
            # Register MCP tools with ReAct engine
            await self._register_mcp_tools_with_react()
            
            self.is_initialized = True
            logger.info("MCP integration successfully initialized for ReAct engine")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize MCP integration: {str(e)}")
            return False
    
    async def _register_mcp_tools_with_react(self) -> None:
        """Register all available MCP tools with the ReAct engine."""
        
        try:
            # Get all available tools (both built-in and MCP)
            all_tools = await self.tool_registry.list_tools()
            
            logger.debug(f"Registering {len(all_tools)} tools with ReAct engine")
            
            registered_count = 0
            
            for tool_name in all_tools:
                tool = self.tool_registry.get_tool(tool_name)
                
                if tool:
                    # Register directly with ReAct engine's tool registry
                    # The ToolRegistry uses class methods, so we register the original tool
                    if hasattr(self.react_engine, 'tool_registry'):
                        # Check if tool is already registered to avoid duplicates
                        if tool_name not in self.react_engine.tool_registry._tools:
                            self.react_engine.tool_registry.register(tool)
                            registered_count += 1
                            logger.debug(f"Registered tool '{tool_name}' with ReAct engine")
                        else:
                            logger.debug(f"Tool '{tool_name}' already registered, skipping")
            
            logger.debug(f"Successfully registered {registered_count} tools with ReAct engine")
            
        except Exception as e:
            logger.error(f"Failed to register MCP tools with ReAct: {str(e)}")
            raise
    
    
    async def refresh_tools(self) -> int:
        """
        Refresh available tools and re-register with ReAct engine.
        
        Returns:
            int: Number of tools refreshed
        """
        try:
            logger.info("Refreshing MCP tools in ReAct engine...")
            
            # Re-register tools
            await self._register_mcp_tools_with_react()
            
            # Get updated count
            all_tools = await self.tool_registry.list_tools()
            
            logger.info(f"Refreshed {len(all_tools)} tools in ReAct engine")
            return len(all_tools)
            
        except Exception as e:
            logger.error(f"Failed to refresh tools: {str(e)}")
            return 0
    
    async def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific tool."""
        return await self.tool_registry.get_tool_info(tool_name)
    
    def search_tools(self, query: str, fuzzy: bool = True) -> List[Dict[str, Any]]:
        """Search for tools by name or description."""
        return self.tool_registry.search_tools(query, fuzzy)
    
    def get_registry_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        return self.tool_registry.get_registry_stats()




async def setup_mcp_integration_for_react(react_engine: ReActEngine, mcp_config_path: Optional[Path] = None) -> Optional[MCPReActIntegration]:
    """
    Set up MCP integration for a ReAct engine instance.
    
    Args:
        react_engine: ReAct engine to integrate with
        mcp_config_path: Optional path to MCP configuration
        
    Returns:
        Optional[MCPReActIntegration]: Integration instance if successful
    """
    try:
        integration = MCPReActIntegration(react_engine, mcp_config_path)
        
        success = await integration.initialize()
        
        if success:
            logger.info("MCP integration setup completed for ReAct engine")
            return integration
        else:
            logger.warning("MCP integration setup failed")
            return None
            
    except Exception as e:
        logger.error(f"Failed to setup MCP integration: {str(e)}")
        return None


def create_tool_description_for_ai(tool_name: str, tool_info: Dict[str, Any]) -> str:
    """
    Create a natural language description of a tool for the AI.
    
    Args:
        tool_name: Name of the tool
        tool_info: Tool information dictionary
        
    Returns:
        str: Natural language description
    """
    description = f"Tool: {tool_name}\n"
    description += f"Description: {tool_info.get('description', 'No description available')}\n"
    
    if tool_info.get('type') == 'mcp':
        description += f"Type: MCP tool from server '{tool_info.get('server_name', 'unknown')}'\n"
    else:
        description += f"Type: {tool_info.get('type', 'built-in')} tool\n"
    
    # Add schema information if available
    if 'input_schema' in tool_info:
        schema = tool_info['input_schema']
        
        if 'properties' in schema:
            description += "Parameters:\n"
            
            for param_name, param_info in schema['properties'].items():
                param_desc = param_info.get('description', 'No description')
                param_type = param_info.get('type', 'unknown')
                is_required = param_name in schema.get('required', [])
                
                required_marker = " (required)" if is_required else " (optional)"
                description += f"  - {param_name} ({param_type}){required_marker}: {param_desc}\n"
    
    return description