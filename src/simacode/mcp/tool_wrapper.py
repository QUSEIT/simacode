"""
MCP Tool Wrapper for SimaCode Integration

This module provides a wrapper that converts MCP tools into SimaCode-compatible tools,
enabling seamless integration of MCP servers into the SimaCode tool ecosystem.
"""

import asyncio
import json
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Type, Union, Callable
from datetime import datetime
from pathlib import Path
from enum import Enum

from pydantic import BaseModel, Field, create_model

from ..tools.base import Tool, ToolInput, ToolResult, ToolResultType
from ..permissions import PermissionManager
from .protocol import MCPTool, MCPResult
from .server_manager import MCPServerManager
from .exceptions import MCPConnectionError, MCPToolNotFoundError

logger = logging.getLogger(__name__)


class TaskComplexity(Enum):
    """任务复杂度枚举"""
    SIMPLE = "simple"           # 简单任务，快速完成
    STANDARD = "standard"       # 标准任务，正常处理
    LONG_RUNNING = "long_running"  # 长时间运行任务，需要异步处理


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

    def _classify_task_complexity(self, input_data: ToolInput) -> TaskComplexity:
        """
        智能分类任务复杂度。

        Args:
            input_data: 工具输入数据

        Returns:
            TaskComplexity: 任务复杂度级别
        """
        # 基于工具名称的分类
        tool_name_lower = self.original_name.lower()

        # 长时间运行任务的关键词
        long_running_keywords = [
            "download", "upload", "backup", "sync", "process", "analyze",
            "generate", "compile", "build", "train", "convert", "import",
            "export", "migrate", "crawl", "spider", "scrape", "batch",
            "bulk", "mass", "large", "archive", "extract", "compress"
        ]

        # 简单任务的关键词
        simple_keywords = [
            "get", "read", "list", "show", "view", "check", "test",
            "ping", "status", "info", "count", "exists", "validate"
        ]

        # 检查工具名称
        if any(keyword in tool_name_lower for keyword in long_running_keywords):
            return TaskComplexity.LONG_RUNNING

        if any(keyword in tool_name_lower for keyword in simple_keywords):
            return TaskComplexity.SIMPLE

        # 基于输入参数的分析
        args_dict = input_data.dict()

        # 检查文件路径大小指示器
        for key, value in args_dict.items():
            if isinstance(value, str):
                key_lower = key.lower()

                # 大文件路径
                if "path" in key_lower and len(value) > 100:
                    return TaskComplexity.LONG_RUNNING

                # URL 下载
                if "url" in key_lower and value.startswith(("http://", "https://")):
                    return TaskComplexity.LONG_RUNNING

                # 批量操作指示器
                if any(batch_key in key_lower for batch_key in ["batch", "bulk", "multiple", "array"]):
                    return TaskComplexity.LONG_RUNNING

            elif isinstance(value, (list, dict)):
                # 大量数据处理
                if len(str(value)) > 1000:  # 大型数据结构
                    return TaskComplexity.LONG_RUNNING

        # 基于服务器类型的推断
        server_name_lower = self.server_name.lower()
        if any(keyword in server_name_lower for keyword in ["ai", "ml", "model", "llm"]):
            # AI/ML 相关工具通常需要更多时间
            return TaskComplexity.STANDARD

        # 检查特定参数模式
        for key, value in args_dict.items():
            if isinstance(value, (int, float)):
                # 大数值可能表示批量操作
                if value > 1000:
                    return TaskComplexity.LONG_RUNNING

        # 默认为标准任务
        return TaskComplexity.STANDARD

    async def _should_use_async_execution(self, input_data: ToolInput) -> bool:
        """
        判断是否应该使用异步执行。

        Args:
            input_data: 工具输入数据

        Returns:
            bool: 是否使用异步执行
        """
        complexity = self._classify_task_complexity(input_data)

        # 长时间运行任务总是使用异步执行
        if complexity == TaskComplexity.LONG_RUNNING:
            return True

        # 检查服务器是否支持异步
        # 这里可以检查服务器能力或配置
        # 暂时对所有非简单任务尝试异步
        return complexity != TaskComplexity.SIMPLE

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
        增强的 MCP 工具执行方法，支持智能异步执行。

        Args:
            input_data: 验证过的输入数据

        Yields:
            ToolResult: 执行结果
        """
        execution_start = time.time()

        # 分析任务复杂度
        complexity = self._classify_task_complexity(input_data)
        should_use_async = await self._should_use_async_execution(input_data)

        # 访问会话信息
        session = await self.get_session(input_data)
        if session:
            session.add_log_entry(
                f"Executing MCP tool '{self.original_name}' on server '{self.server_name}' "
                f"(complexity: {complexity.value}, async: {should_use_async})"
            )

            yield ToolResult(
                type=ToolResultType.INFO,
                content=f"Executing MCP tool in session {session.id} (complexity: {complexity.value})",
                tool_name=self.name,
                execution_id=input_data.execution_id,
                metadata={
                    "session_id": session.id,
                    "session_state": session.state.value,
                    "mcp_server": self.server_name,
                    "mcp_tool": self.original_name,
                    "task_complexity": complexity.value,
                    "async_execution": should_use_async
                }
            )

        # 选择执行模式
        if should_use_async and complexity == TaskComplexity.LONG_RUNNING:
            # 使用异步执行
            async for result in self._execute_async(input_data, complexity):
                yield result
        else:
            # 使用同步执行
            async for result in self._execute_sync(input_data, complexity):
                yield result

    async def _execute_async(self, input_data: ToolInput, complexity: TaskComplexity) -> AsyncGenerator[ToolResult, None]:
        """
        异步执行模式，适用于长时间运行任务。

        Args:
            input_data: 工具输入数据
            complexity: 任务复杂度

        Yields:
            ToolResult: 执行结果
        """
        try:
            # 检查服务器是否支持异步调用
            if hasattr(self.server_manager, 'call_tool_async'):
                # 使用服务器管理器的异步调用
                async for result in self._execute_with_server_async(input_data):
                    yield result
            else:
                # 服务器不支持异步调用，回退到同步执行
                async for result in self._execute_sync(input_data, TaskComplexity.LOW):
                    yield result

        except Exception as e:
            logger.error(f"Async execution failed for {self.name}: {str(e)}")
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"Async execution failed: {str(e)}",
                tool_name=self.name,
                execution_id=input_data.execution_id,
                metadata={"error_type": "async_execution_error", "complexity": complexity.value}
            )

    async def _execute_with_server_async(self, input_data: ToolInput) -> AsyncGenerator[ToolResult, None]:
        """使用服务器管理器的异步调用"""

        # 进度回调函数
        async def progress_callback(progress_data: Dict[str, Any]):
            # 这里可以进一步处理进度数据
            logger.debug(f"Tool {self.name} progress: {progress_data}")

        # 转换输入参数
        mcp_arguments = self._convert_input_to_mcp_args(input_data)

        # Essential MCP async call logging
        logger.debug(f"MCP async call: tool='{self.original_name}', server='{self.server_name}'")
        async for mcp_result in self.server_manager.call_tool_async(
            self.server_name,
            self.original_name,
            mcp_arguments,
            progress_callback=progress_callback
        ):
            # Convert MCP result to tool result
            async for tool_result in self._convert_mcp_result_to_tool_result(
                mcp_result, input_data.execution_id, 0
            ):
                yield tool_result


    async def _execute_sync(self, input_data: ToolInput, complexity: TaskComplexity) -> AsyncGenerator[ToolResult, None]:
        """
        同步执行模式，适用于快速任务。

        Args:
            input_data: 工具输入数据
            complexity: 任务复杂度

        Yields:
            ToolResult: 执行结果
        """
        execution_start = time.time()

        try:
            # 进度指示器
            yield ToolResult(
                type=ToolResultType.PROGRESS,
                content=f"Executing MCP tool '{self.original_name}' on server '{self.server_name}'",
                tool_name=self.name,
                execution_id=input_data.execution_id,
                metadata={"execution_mode": "sync", "complexity": complexity.value}
            )

            # 转换输入为 MCP 参数
            mcp_arguments = self._convert_input_to_mcp_args(input_data)

            # 通过服务器管理器调用 MCP 工具
            mcp_result = await self.server_manager.call_tool(
                self.server_name,
                self.original_name,
                mcp_arguments
            )

            # 转换 MCP 结果为 SimaCode 结果
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
            # Check if the MCP tool schema suggests it can handle session context
            supports_session = self._mcp_tool_supports_session_context()

            if supports_session:
                mcp_args["_session_context"] = input_data.session_context
                logger.debug(f"Added session context to MCP args for {self.original_name}")
        
        return mcp_args
    
    def _mcp_tool_supports_session_context(self) -> bool:
        """
        Check if the MCP tool supports session context based on its schema.
        
        Returns:
            bool: True if the tool appears to support session context
        """
        if not self.mcp_schema:
            return False

        # Check if the schema has fields that suggest session context support
        schema_str = str(self.mcp_schema).lower()
        session_keywords = ["session", "context", "_session_context"]

        # More specific check for _session_context parameter
        if "_session_context" in schema_str:
            return True

        # Check for any session-related keywords
        for keyword in session_keywords:
            if keyword in schema_str:
                return True

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
        # Essential MCP result conversion logging
        logger.debug(f"Converting MCP result for tool '{self.name}': success={mcp_result.success}")

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