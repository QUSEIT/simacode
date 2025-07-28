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
        self.tool_registry = SimaCodeToolRegistry()
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
            all_tools = self.tool_registry.list_tools()
            
            logger.info(f"Registering {len(all_tools)} tools with ReAct engine")
            
            registered_count = 0
            
            for tool_name in all_tools:
                tool = self.tool_registry.get_tool(tool_name)
                
                if tool:
                    # Create a ReAct-compatible tool wrapper
                    react_tool = self._create_react_tool_wrapper(tool_name, tool)
                    
                    # Register with ReAct engine's tool registry
                    if hasattr(self.react_engine, 'tool_registry'):
                        self.react_engine.tool_registry.register_tool(react_tool)
                        registered_count += 1
                        logger.debug(f"Registered tool '{tool_name}' with ReAct engine")
            
            logger.info(f"Successfully registered {registered_count} tools with ReAct engine")
            
        except Exception as e:
            logger.error(f"Failed to register MCP tools with ReAct: {str(e)}")
            raise
    
    def _create_react_tool_wrapper(self, tool_name: str, tool: Tool) -> 'ReActTool':
        """
        Create a ReAct-compatible wrapper for a tool.
        
        Args:
            tool_name: Name of the tool
            tool: Tool instance
            
        Returns:
            ReActTool: ReAct-compatible tool wrapper
        """
        return ReActTool(
            name=tool_name,
            description=tool.description,
            tool_instance=tool,
            registry=self.tool_registry
        )
    
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
            all_tools = self.tool_registry.list_tools()
            
            logger.info(f"Refreshed {len(all_tools)} tools in ReAct engine")
            return len(all_tools)
            
        except Exception as e:
            logger.error(f"Failed to refresh tools: {str(e)}")
            return 0
    
    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific tool."""
        return self.tool_registry.get_tool_info(tool_name)
    
    def search_tools(self, query: str, fuzzy: bool = True) -> List[Dict[str, Any]]:
        """Search for tools by name or description."""
        return self.tool_registry.search_tools(query, fuzzy)
    
    def get_registry_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        return self.tool_registry.get_registry_stats()


class ReActTool:
    """
    ReAct-compatible tool wrapper that integrates with the unified tool registry.
    
    This class provides the interface expected by the ReAct engine while
    delegating actual tool execution to the unified tool registry.
    """
    
    def __init__(self, name: str, description: str, tool_instance: Tool, registry: SimaCodeToolRegistry):
        """
        Initialize ReAct tool wrapper.
        
        Args:
            name: Tool name
            description: Tool description
            tool_instance: Underlying tool instance
            registry: Unified tool registry
        """
        self.name = name
        self.description = description
        self.tool_instance = tool_instance
        self.registry = registry
    
    async def execute(self, parameters: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute the tool with given parameters.
        
        Args:
            parameters: Tool execution parameters
            
        Yields:
            Dict[str, Any]: Execution updates in ReAct format
        """
        try:
            # Yield start notification
            yield {
                "type": "tool_start",
                "tool_name": self.name,
                "parameters": parameters,
                "message": f"Starting execution of {self.name}"
            }
            
            # Execute tool through registry
            results = []
            async for result in self.registry.execute_tool(self.name, parameters):
                results.append(result)
                
                # Convert ToolResult to ReAct format
                react_update = self._convert_tool_result_to_react(result)
                yield react_update
            
            # Yield completion notification
            yield {
                "type": "tool_complete",
                "tool_name": self.name,
                "results_count": len(results),
                "message": f"Completed execution of {self.name}"
            }
            
        except Exception as e:
            logger.error(f"Tool execution failed for '{self.name}': {str(e)}")
            
            yield {
                "type": "tool_error",
                "tool_name": self.name,
                "error": str(e),
                "message": f"Tool {self.name} failed: {str(e)}"
            }
    
    def _convert_tool_result_to_react(self, result: ToolResult) -> Dict[str, Any]:
        """
        Convert ToolResult to ReAct engine format.
        
        Args:
            result: Tool execution result
            
        Returns:
            Dict[str, Any]: ReAct-formatted update
        """
        react_type_mapping = {
            ToolResultType.SUCCESS: "tool_success",
            ToolResultType.ERROR: "tool_error",
            ToolResultType.WARNING: "tool_warning",
            ToolResultType.INFO: "tool_info",
            ToolResultType.PROGRESS: "tool_progress",
            ToolResultType.OUTPUT: "tool_output"
        }
        
        return {
            "type": react_type_mapping.get(result.type, "tool_output"),
            "tool_name": self.name,
            "content": result.content,
            "metadata": result.metadata,
            "timestamp": result.timestamp.isoformat(),
            "execution_id": result.execution_id
        }
    
    def get_schema(self) -> Dict[str, Any]:
        """Get the tool's input schema."""
        try:
            # Get schema from tool instance
            input_schema_class = self.tool_instance.get_input_schema()
            
            if hasattr(input_schema_class, 'schema'):
                return input_schema_class.schema()
            elif hasattr(input_schema_class, 'model_json_schema'):
                return input_schema_class.model_json_schema()
            else:
                # Fallback for basic schema
                return {
                    "type": "object",
                    "properties": {},
                    "description": f"Schema for {self.name}"
                }
                
        except Exception as e:
            logger.warning(f"Could not get schema for tool '{self.name}': {str(e)}")
            return {
                "type": "object",
                "properties": {},
                "description": f"Schema unavailable for {self.name}"
            }
    
    def __str__(self) -> str:
        return f"ReActTool({self.name})"
    
    def __repr__(self) -> str:
        return f"ReActTool(name='{self.name}', description='{self.description}')"


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