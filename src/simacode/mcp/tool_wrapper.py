"""
MCP Tool Wrapper for SimaCode Integration

This module provides a wrapper that converts MCP tools into SimaCode-compatible tools,
enabling seamless integration of MCP servers into the SimaCode tool ecosystem.
"""

import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Type, Union
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field, create_model

from ..tools.base import Tool, ToolInput, ToolResult, ToolResultType
from ..permissions import PermissionManager
from .protocol import MCPTool, MCPResult
from .server_manager import MCPServerManager
from .exceptions import MCPConnectionError, MCPToolNotFoundError

logger = logging.getLogger(__name__)


class MCPToolInput(ToolInput):
    """
    Dynamic input model for MCP tools.
    
    This class serves as a base for dynamically created input models
    based on MCP tool schemas.
    """
    
    # Allow any additional fields based on MCP tool schema
    class Config:
        extra = "allow"
        arbitrary_types_allowed = True


class MCPToolWrapper(Tool):
    """
    Wrapper that adapts MCP tools to the SimaCode tool interface.
    
    This class bridges the gap between MCP protocol tools and SimaCode's
    tool framework, providing seamless integration while maintaining
    all SimaCode tool features like permissions, validation, and monitoring.
    """
    
    def __init__(
        self,
        mcp_tool: MCPTool,
        server_manager: MCPServerManager,
        permission_manager: Optional[PermissionManager] = None,
        namespace: Optional[str] = None,
        session_manager=None
    ):
        """
        Initialize MCP tool wrapper.
        
        Args:
            mcp_tool: The MCP tool to wrap
            server_manager: Manager for MCP server operations
            permission_manager: Optional permission manager
            namespace: Optional namespace prefix for tool name
        """
        # Create namespaced tool name
        tool_name = f"{namespace}:{mcp_tool.name}" if namespace else f"mcp_{mcp_tool.server_name}_{mcp_tool.name}"
        
        super().__init__(
            name=tool_name,
            description=f"[MCP:{mcp_tool.server_name}] {mcp_tool.description}",
            version="1.0.0",
            session_manager=session_manager
        )
        
        self.mcp_tool = mcp_tool
        self.server_manager = server_manager
        self.permission_manager = permission_manager or PermissionManager()
        self.namespace = namespace
        
        # Create dynamic input schema
        self._input_schema = self._create_input_schema()
        
        # MCP-specific metadata
        self.server_name = mcp_tool.server_name
        self.original_name = mcp_tool.name
        self.mcp_schema = mcp_tool.input_schema
    
    def _create_input_schema(self) -> Type[MCPToolInput]:
        """
        Create a dynamic Pydantic model based on the MCP tool's input schema.
        
        Returns:
            Type[MCPToolInput]: Dynamic input schema class
        """
        try:
            if not self.mcp_tool.input_schema:
                # No schema provided, use base input
                return MCPToolInput
            
            schema = self.mcp_tool.input_schema
            if not isinstance(schema, dict):
                logger.warning(f"Invalid schema for tool {self.mcp_tool.name}, using base input")
                return MCPToolInput
            
            # Extract properties from JSON schema
            properties = schema.get("properties", {})
            required_fields = schema.get("required", [])
            
            # Build field definitions
            field_definitions = {}
            
            for field_name, field_schema in properties.items():
                field_type = self._json_schema_to_python_type(field_schema)
                field_description = field_schema.get("description", "")
                
                # Determine if field is required
                if field_name in required_fields:
                    field_definitions[field_name] = (field_type, Field(..., description=field_description))
                else:
                    default_value = field_schema.get("default")
                    field_definitions[field_name] = (
                        Optional[field_type], 
                        Field(default=default_value, description=field_description)
                    )
            
            # Create dynamic model class
            dynamic_class_name = f"{self.mcp_tool.name.title()}Input"
            
            return create_model(
                dynamic_class_name,
                __base__=MCPToolInput,
                **field_definitions
            )
            
        except Exception as e:
            logger.warning(f"Failed to create schema for tool {self.mcp_tool.name}: {str(e)}")
            return MCPToolInput
    
    def _json_schema_to_python_type(self, field_schema: Dict[str, Any]) -> Type:
        """
        Convert JSON schema field type to Python type.
        
        Args:
            field_schema: JSON schema field definition
            
        Returns:
            Type: Corresponding Python type
        """
        schema_type = field_schema.get("type", "string")
        
        type_mapping = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        
        return type_mapping.get(schema_type, str)
    
    def get_input_schema(self) -> Type[ToolInput]:
        """Return the dynamic input schema for this MCP tool."""
        return self._input_schema
    
    async def validate_input(self, input_data: Dict[str, Any]) -> ToolInput:
        """
        Validate input data using the dynamic schema.
        
        Args:
            input_data: Raw input data
            
        Returns:
            ToolInput: Validated input object
        """
        try:
            schema_class = self.get_input_schema()
            return schema_class(**input_data)
        except Exception as e:
            logger.error(f"Input validation failed for MCP tool {self.name}: {str(e)}")
            raise ValueError(f"Invalid input for {self.name}: {str(e)}")
    
    async def check_permissions(self, input_data: ToolInput) -> bool:
        """
        Check permissions for MCP tool execution.
        
        Args:
            input_data: Validated input data
            
        Returns:
            bool: True if execution is permitted
        """
        try:
            # Check general tool execution permission
            if not await self.permission_manager.check_tool_permission(
                self.name,
                input_data.dict()
            ):
                return False
            
            # Check MCP-specific permissions
            return await self._check_mcp_permissions(input_data)
            
        except Exception as e:
            logger.error(f"Permission check failed for {self.name}: {str(e)}")
            return False
    
    async def _check_mcp_permissions(self, input_data: ToolInput) -> bool:
        """
        Check MCP-specific permissions.
        
        Args:
            input_data: Validated input data
            
        Returns:
            bool: True if MCP permissions are satisfied
        """
        # Get server configuration for security settings
        server_config = None
        if hasattr(self.server_manager, 'config') and self.server_manager.config:
            server_config = self.server_manager.config.get_server_config(self.server_name)
        
        if not server_config:
            logger.warning(f"No server config found for {self.server_name}")
            return True  # Default to allow if no config
        
        security_config = server_config.security
        
        # Check allowed operations
        if security_config.allowed_operations:
            # If the tool has a specific operation type, check it
            operation = self._extract_operation_type(input_data)
            if operation and operation not in security_config.allowed_operations:
                logger.warning(f"Operation '{operation}' not allowed for server {self.server_name}")
                return False
        
        # Check path restrictions if input contains paths
        if await self._has_path_restrictions(input_data, security_config):
            return False
        
        return True
    
    def _extract_operation_type(self, input_data: ToolInput) -> Optional[str]:
        """
        Extract operation type from input data.
        
        This method attempts to determine what type of operation
        the tool will perform based on its name and input.
        
        Args:
            input_data: Tool input data
            
        Returns:
            Optional[str]: Operation type if determinable
        """
        tool_name_lower = self.original_name.lower()
        
        # Common operation patterns
        if any(word in tool_name_lower for word in ["read", "get", "list", "show"]):
            return "read"
        elif any(word in tool_name_lower for word in ["write", "create", "update", "edit"]):
            return "write"
        elif any(word in tool_name_lower for word in ["delete", "remove", "rm"]):
            return "delete"
        elif any(word in tool_name_lower for word in ["execute", "run", "exec"]):
            return "execute"
        
        return None
    
    async def _has_path_restrictions(self, input_data: ToolInput, security_config) -> bool:
        """
        Check if input contains paths that violate security restrictions.
        
        Args:
            input_data: Tool input data
            security_config: Security configuration
            
        Returns:
            bool: True if there are violations
        """
        from pathlib import Path
        
        # Extract potential paths from input
        input_dict = input_data.dict()
        potential_paths = []
        
        for key, value in input_dict.items():
            if isinstance(value, str) and ("path" in key.lower() or "file" in key.lower()):
                potential_paths.append(value)
        
        # Check against forbidden paths
        for path_str in potential_paths:
            try:
                path = Path(path_str).resolve()
                
                # Check if path is in forbidden list
                for forbidden in security_config.forbidden_paths:
                    forbidden_path = Path(forbidden).resolve()
                    if self._is_path_under(path, forbidden_path):
                        logger.warning(f"Path {path} is forbidden (under {forbidden_path})")
                        return True
                
                # Check if path is in allowed list (if specified)
                if security_config.allowed_paths:
                    allowed = False
                    for allowed_path_str in security_config.allowed_paths:
                        allowed_path = Path(allowed_path_str).resolve()
                        if self._is_path_under(path, allowed_path):
                            allowed = True
                            break
                    
                    if not allowed:
                        logger.warning(f"Path {path} is not in allowed paths")
                        return True
                        
            except Exception as e:
                logger.warning(f"Error checking path restrictions for {path_str}: {str(e)}")
                continue
        
        return False
    
    def _is_path_under(self, path: Path, parent: Path) -> bool:
        """
        Check if a path is under a parent directory.
        
        Args:
            path: Path to check
            parent: Parent directory path
            
        Returns:
            bool: True if path is under parent
        """
        try:
            path.relative_to(parent)
            return True
        except ValueError:
            return False
    
    async def execute(self, input_data: ToolInput) -> AsyncGenerator[ToolResult, None]:
        """
        Execute the MCP tool.
        
        Args:
            input_data: Validated input data
            
        Yields:
            ToolResult: Execution results
        """
        execution_start = time.time()
        
        # Access session information if available
        session = await self.get_session(input_data)
        if session:
            # Log MCP tool execution to session
            session.add_log_entry(f"Executing MCP tool '{self.original_name}' on server '{self.server_name}'")
            
            # Yield session-aware progress indicator
            yield ToolResult(
                type=ToolResultType.INFO,
                content=f"Executing MCP tool in session {session.id} (state: {session.state.value})",
                tool_name=self.name,
                execution_id=input_data.execution_id,
                metadata={
                    "session_id": session.id,
                    "session_state": session.state.value,
                    "mcp_server": self.server_name,
                    "mcp_tool": self.original_name
                }
            )
        
        try:
            # Progress indicator
            yield ToolResult(
                type=ToolResultType.PROGRESS,
                content=f"Executing MCP tool '{self.original_name}' on server '{self.server_name}'",
                tool_name=self.name,
                execution_id=input_data.execution_id
            )
            
            # Convert input to MCP arguments
            mcp_arguments = self._convert_input_to_mcp_args(input_data)
            
            # Call MCP tool through server manager
            mcp_result = await self.server_manager.call_tool(
                self.server_name,
                self.original_name,
                mcp_arguments
            )
            
            # Convert MCP result to SimaCode result
            execution_time = time.time() - execution_start
            async for result in self._convert_mcp_result_to_tool_result(
                mcp_result, input_data.execution_id, execution_time
            ):
                yield result
                
        except MCPConnectionError as e:
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"MCP connection error: {str(e)}",
                tool_name=self.name,
                execution_id=input_data.execution_id,
                metadata={"error_type": "connection_error", "server_name": self.server_name}
            )
            
        except MCPToolNotFoundError as e:
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"MCP tool not found: {str(e)}",
                tool_name=self.name,
                execution_id=input_data.execution_id,
                metadata={"error_type": "tool_not_found", "server_name": self.server_name}
            )
            
        except Exception as e:
            logger.error(f"MCP tool execution failed for {self.name}: {str(e)}")
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"Tool execution failed: {str(e)}",
                tool_name=self.name,
                execution_id=input_data.execution_id,
                metadata={"error_type": "execution_error", "server_name": self.server_name}
            )
    
    def _convert_input_to_mcp_args(self, input_data: ToolInput) -> Dict[str, Any]:
        """
        Convert SimaCode tool input to MCP arguments.
        
        Args:
            input_data: Validated SimaCode tool input
            
        Returns:
            Dict[str, Any]: MCP-compatible arguments
        """
        # Get input as dictionary
        input_dict = input_data.dict()
        
        # Remove SimaCode-specific fields
        mcp_args = {
            key: value
            for key, value in input_dict.items()
            if key not in {"execution_id", "metadata", "session_id", "session_context"}
        }
        
        # Optionally include session context for MCP tools that support it
        # This allows MCP tools to access session information if they're designed to use it
        if hasattr(input_data, 'session_context') and input_data.session_context:
            # Log session context availability for debugging
            logger.debug(f"Session context available for tool {self.original_name}: {list(input_data.session_context.keys())}")
            
            # Check if the MCP tool schema suggests it can handle session context
            supports_session = self._mcp_tool_supports_session_context()
            logger.debug(f"Session context support check for {self.original_name}: supports={supports_session}")
            
            if supports_session:
                mcp_args["_session_context"] = input_data.session_context
                logger.debug(f"Added session context to MCP args for {self.original_name}")
            else:
                logger.warning(f"Session context not supported by {self.original_name} (schema check failed)")
        else:
            logger.debug(f"No session context available for tool {self.original_name}")
        
        return mcp_args
    
    def _mcp_tool_supports_session_context(self) -> bool:
        """
        Check if the MCP tool supports session context based on its schema.
        
        Returns:
            bool: True if the tool appears to support session context
        """
        if not self.mcp_schema:
            logger.debug(f"No MCP schema available for {self.original_name}")
            return False
        
        # Check if the schema has fields that suggest session context support
        schema_str = str(self.mcp_schema).lower()
        session_keywords = ["session", "context", "_session_context"]
        
        # Log schema analysis for debugging
        schema_found = {}
        for keyword in session_keywords:
            found = keyword in schema_str
            schema_found[keyword] = found
        
        logger.debug(f"Schema analysis for {self.original_name}: length={len(schema_str)}, keywords={schema_found}")
        
        # More specific check for _session_context parameter
        if "_session_context" in schema_str:
            logger.debug(f"Found explicit _session_context support in schema for {self.original_name}")
            return True
        
        # Check for any session-related keywords
        for keyword in session_keywords:
            if keyword in schema_str:
                logger.debug(f"Found session keyword '{keyword}' in schema for {self.original_name}")
                return True
        
        logger.debug(f"No session support detected for {self.original_name}")
        return False
    
    async def _convert_mcp_result_to_tool_result(
        self,
        mcp_result: MCPResult,
        execution_id: str,
        execution_time: float
    ) -> AsyncGenerator[ToolResult, None]:
        """
        Convert MCP result to SimaCode tool results.
        
        Args:
            mcp_result: Result from MCP tool execution
            execution_id: Execution ID for tracking
            execution_time: Total execution time
            
        Yields:
            ToolResult: Converted tool results
        """
        if mcp_result.success:
            # Success result
            content = self._format_mcp_content(mcp_result.content)
            
            yield ToolResult(
                type=ToolResultType.SUCCESS,
                content=content,
                tool_name=self.name,
                execution_id=execution_id,
                metadata={
                    "mcp_metadata": mcp_result.metadata,
                    "server_name": self.server_name,
                    "original_tool_name": self.original_name,
                    "execution_time": execution_time,
                    "mcp_success": True
                }
            )
        else:
            # Error result
            error_content = mcp_result.error or "Unknown MCP error"
            
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"MCP tool error: {error_content}",
                tool_name=self.name,
                execution_id=execution_id,
                metadata={
                    "mcp_metadata": mcp_result.metadata,
                    "server_name": self.server_name,
                    "original_tool_name": self.original_name,
                    "execution_time": execution_time,
                    "mcp_success": False,
                    "error_type": "mcp_tool_error"
                }
            )
    
    def _format_mcp_content(self, content: Any) -> str:
        """
        Format MCP content for display in SimaCode.
        
        Args:
            content: Raw MCP content
            
        Returns:
            str: Formatted content string
        """
        if isinstance(content, str):
            return content
        elif isinstance(content, dict):
            return json.dumps(content, indent=2, ensure_ascii=False)
        elif isinstance(content, list):
            return json.dumps(content, indent=2, ensure_ascii=False)
        else:
            return str(content)
    
    @property
    def metadata(self) -> Dict[str, Any]:
        """Get enhanced metadata including MCP-specific information."""
        base_metadata = super().metadata
        
        # Add MCP-specific metadata
        mcp_metadata = {
            "mcp_tool": True,
            "server_name": self.server_name,
            "original_name": self.original_name,
            "namespace": self.namespace,
            "mcp_schema": self.mcp_schema,
            "server_capabilities": getattr(self.mcp_tool, 'capabilities', None)
        }
        
        # Merge metadata
        base_metadata.update(mcp_metadata)
        return base_metadata
    
    def get_mcp_info(self) -> Dict[str, Any]:
        """
        Get detailed MCP tool information.
        
        Returns:
            Dict[str, Any]: MCP tool information
        """
        return {
            "mcp_tool_name": self.original_name,
            "server_name": self.server_name,
            "server_description": f"MCP Server: {self.server_name}",
            "input_schema": self.mcp_schema,
            "wrapper_name": self.name,
            "namespace": self.namespace,
            "created_at": self.created_at.isoformat(),
            "execution_stats": {
                "total_executions": self._execution_count,
                "average_execution_time": (
                    self._total_execution_time / self._execution_count
                    if self._execution_count > 0 else 0.0
                )
            }
        }