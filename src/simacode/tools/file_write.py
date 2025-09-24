"""
File writing tool for SimaCode.

This tool provides secure file writing capabilities with comprehensive
safety checks and permission validation.
"""

import os
import tempfile
import shutil
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, Optional, Type

import aiofiles
from pydantic import BaseModel, Field, validator

from .base import Tool, ToolInput, ToolResult, ToolResultType, ToolRegistry
from ..permissions import PermissionManager, PathValidator


class FileWriteInput(ToolInput):
    """Input model for FileWrite tool."""
    
    file_path: str = Field(..., description="Path to the file to write")
    content: str = Field(..., description="Content to write to the file")
    encoding: str = Field(
        "utf-8",
        description="File encoding for writing (always utf-8 for cross-platform compatibility)"
    )
    mode: str = Field(
        "write",
        description="Write mode: 'write' (overwrite), 'append', or 'insert'",
        pattern="^(write|append|insert)$"
    )
    insert_line: Optional[int] = Field(
        None,
        description="Line number for insert mode (1-based)",
        ge=1
    )
    create_directories: bool = Field(
        False,
        description="Create parent directories if they don't exist"
    )
    preserve_permissions: bool = Field(
        True,
        description="Preserve original file permissions"
    )
    line_ending: str = Field(
        "auto",
        description="Line ending style: 'auto', 'unix' (\\n), 'windows' (\\r\\n), or 'mac' (\\r)",
        pattern="^(auto|unix|windows|mac)$"
    )
    
    @validator('file_path')
    def validate_file_path(cls, v):
        """Validate file path."""
        if not v or not v.strip():
            raise ValueError("File path cannot be empty")
        return v.strip()
    
    @validator('content')
    def validate_content(cls, v):
        """Validate content."""
        if v is None:
            return ""
        return v
    
    @validator('encoding')
    def validate_encoding(cls, v):
        """Force UTF-8 encoding for cross-platform compatibility."""
        # Always use UTF-8 regardless of input
        return "utf-8"
    
    @validator('insert_line', always=True)
    def validate_insert_line(cls, v, values):
        """Validate insert line number."""
        if v is not None and values.get('mode') != 'insert':
            raise ValueError("insert_line is only valid with mode='insert'")
        if values.get('mode') == 'insert' and v is None:
            raise ValueError("insert_line is required with mode='insert'")
        return v


class FileWriteTool(Tool):
    """
    Tool for writing files safely.
    
    This tool provides secure file writing with permission checking 
    and various writing modes (overwrite, append, insert).
    """
    
    def __init__(self, permission_manager: Optional[PermissionManager] = None, session_manager=None):
        """Initialize FileWrite tool."""
        super().__init__(
            name="file_write",
            description="Write file contents safely with permission controls",
            version="1.0.0",
            session_manager=session_manager
        )
        self.permission_manager = permission_manager or PermissionManager()
        # Initialize PathValidator with the allowed paths from permission manager
        self.path_validator = PathValidator(self.permission_manager.get_allowed_paths())
    
    def get_input_schema(self) -> Type[ToolInput]:
        """Return the input schema for this tool."""
        return FileWriteInput
    
    async def validate_input(self, input_data: Dict[str, Any]) -> FileWriteInput:
        """Validate and parse tool input data."""
        return FileWriteInput(**input_data)
    
    async def check_permissions(self, input_data: FileWriteInput) -> bool:
        """Check if the tool has permission to write the file."""
        # Check file write permission
        permission_result = self.permission_manager.check_file_permission(
            input_data.file_path, "write"
        )
        
        if not permission_result.granted:
            return False
        
        # Validate path safety
        is_safe, _ = self.path_validator.validate_path(
            input_data.file_path, "write"
        )
        
        if not is_safe:
            return False
        
        # Check parent directory permission if creating directories
        if input_data.create_directories:
            parent_dir = os.path.dirname(os.path.abspath(input_data.file_path))
            path_permission = self.permission_manager.check_path_access(
                parent_dir, "create"
            )
            if not path_permission.granted:
                return False
        
        return True
    
    async def execute(self, input_data: FileWriteInput) -> AsyncGenerator[ToolResult, None]:
        """Execute file writing operation."""
        execution_id = input_data.execution_id
        file_path = input_data.file_path
        
        try:
            # Normalize path
            normalized_path = os.path.abspath(file_path)
            
            yield ToolResult(
                type=ToolResultType.INFO,
                content=f"Writing to file: {normalized_path}",
                execution_id=execution_id,
                metadata={
                    "file_path": normalized_path,
                    "mode": input_data.mode,
                    "encoding": input_data.encoding
                }
            )
            
            # Create parent directories if requested
            if input_data.create_directories:
                parent_dir = os.path.dirname(normalized_path)
                if not os.path.exists(parent_dir):
                    os.makedirs(parent_dir, exist_ok=True)
                    yield ToolResult(
                        type=ToolResultType.INFO,
                        content=f"Created parent directories: {parent_dir}",
                        execution_id=execution_id
                    )
            
            # Check if file exists
            file_exists = os.path.exists(normalized_path)
            original_size = 0
            original_permissions = None
            
            if file_exists:
                original_size = os.path.getsize(normalized_path)
                original_stat = os.stat(normalized_path)
                original_permissions = original_stat.st_mode
            
            # Prepare content based on mode
            final_content = await self._prepare_content(
                normalized_path, input_data, execution_id
            )

            # Force UTF-8 encoding
            input_data.encoding = "utf-8"

            # Write the file
            await self._write_file(
                normalized_path, final_content, input_data, execution_id
            )
            
            # Restore permissions if requested
            if input_data.preserve_permissions and original_permissions:
                os.chmod(normalized_path, original_permissions)
            
            # Report final status
            new_size = os.path.getsize(normalized_path)
            
            yield ToolResult(
                type=ToolResultType.SUCCESS,
                content=f"Successfully wrote file: {normalized_path}",
                execution_id=execution_id,
                metadata={
                    "original_size": original_size if file_exists else 0,
                    "new_size": new_size,
                    "size_change": new_size - (original_size if file_exists else 0),
                    "backup_created": False
                }
            )
            
        except PermissionError:
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"Permission denied writing to file: {file_path}",
                execution_id=execution_id
            )
            
        except UnicodeEncodeError as e:
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"Unicode encode error: {str(e)}",
                execution_id=execution_id,
                metadata={"encoding": input_data.encoding}
            )
            
        except Exception as e:
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"Error writing file: {str(e)}",
                execution_id=execution_id,
                metadata={"error_type": type(e).__name__}
            )
    
    async def _prepare_content(
        self, 
        file_path: str, 
        input_data: FileWriteInput, 
        execution_id: str
    ) -> str:
        """Prepare content based on write mode."""
        content = input_data.content
        
        # Normalize line endings
        content = await self._normalize_line_endings(content, input_data.line_ending)
        
        if input_data.mode == "write":
            # Simple overwrite
            return content
            
        elif input_data.mode == "append":
            # Append to existing content
            if os.path.exists(file_path):
                async with aiofiles.open(file_path, 'r', encoding=input_data.encoding, errors='replace') as f:
                    existing_content = await f.read()
                
                # Add newline if the existing content doesn't end with one
                if existing_content and not existing_content.endswith('\n'):
                    existing_content += '\n'
                
                return existing_content + content
            else:
                return content
                
        elif input_data.mode == "insert":
            # Insert at specific line
            if os.path.exists(file_path):
                async with aiofiles.open(file_path, 'r', encoding=input_data.encoding, errors='replace') as f:
                    lines = await f.readlines()
                
                insert_line = input_data.insert_line
                
                # Insert content at specified line
                if insert_line <= len(lines) + 1:
                    # Split content into lines
                    content_lines = content.split('\n')
                    
                    # Insert each line
                    for i, line in enumerate(content_lines):
                        lines.insert(insert_line - 1 + i, line + '\n')
                    
                    return ''.join(lines)
                else:
                    # Insert line is beyond file length, append instead
                    return ''.join(lines) + '\n' + content
            else:
                return content
        
        return content
    
    async def _normalize_line_endings(self, content: str, line_ending: str) -> str:
        """Normalize line endings in content."""
        if line_ending == "auto":
            # Keep existing line endings
            return content
        elif line_ending == "unix":
            return content.replace('\r\n', '\n').replace('\r', '\n')
        elif line_ending == "windows":
            # First normalize to unix, then convert to windows
            normalized = content.replace('\r\n', '\n').replace('\r', '\n')
            return normalized.replace('\n', '\r\n')
        elif line_ending == "mac":
            return content.replace('\r\n', '\r').replace('\n', '\r')
        
        return content
    
    async def _write_file(
        self,
        file_path: str,
        content: str,
        input_data: FileWriteInput,
        execution_id: str
    ) -> None:
        """Write content to file atomically with UTF-8 encoding."""
        # Use temporary file for atomic write
        temp_fd = None
        temp_path = None

        try:
            # Create temporary file in the same directory
            parent_dir = os.path.dirname(file_path)
            temp_fd, temp_path = tempfile.mkstemp(
                dir=parent_dir,
                prefix=f".tmp_{os.path.basename(file_path)}_",
                text=True
            )

            # Close the file descriptor immediately
            os.close(temp_fd)
            temp_fd = None

            # Write to temporary file with UTF-8 encoding and error handling
            async with aiofiles.open(
                temp_path,
                'w',
                encoding=input_data.encoding,  # This is now always 'utf-8'
                errors='replace',  # Replace problematic characters instead of failing
                newline='' if input_data.line_ending != 'auto' else None
            ) as f:
                await f.write(content)
                await f.flush()

            # Atomic move to final location
            shutil.move(temp_path, file_path)
            temp_path = None  # Don't delete it in finally block

        finally:
            # Clean up temporary file if something went wrong
            if temp_fd is not None:
                try:
                    os.close(temp_fd)
                except:
                    pass
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except:
                    pass
    
    async def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """Get information about a file."""
        try:
            normalized_path = os.path.abspath(file_path)
            
            if not os.path.exists(normalized_path):
                return {"exists": False, "path": normalized_path}
            
            stat = os.stat(normalized_path)
            
            return {
                "exists": True,
                "path": normalized_path,
                "size": stat.st_size,
                "permissions": oct(stat.st_mode)[-3:],
                "modified_time": stat.st_mtime,
                "is_file": os.path.isfile(normalized_path),
                "is_directory": os.path.isdir(normalized_path),
                "is_readable": os.access(normalized_path, os.R_OK),
                "is_writable": os.access(normalized_path, os.W_OK)
            }
            
        except Exception as e:
            return {
                "exists": False,
                "error": str(e),
                "error_type": type(e).__name__
            }


# Register the tool
file_write_tool = FileWriteTool()
ToolRegistry.register(file_write_tool)