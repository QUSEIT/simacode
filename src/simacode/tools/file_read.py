"""
File reading tool for SimaCode.

This tool provides secure file reading capabilities with comprehensive
safety checks, encoding detection, and permission validation.
"""

import os
import mimetypes
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional, Type, Union

import aiofiles
from pydantic import BaseModel, Field, validator

from .base import Tool, ToolInput, ToolResult, ToolResultType, ToolRegistry
from ..permissions import PermissionManager, PathValidator


class FileReadInput(ToolInput):
    """Input model for FileRead tool."""
    
    file_path: str = Field(..., description="Path to the file to read")
    encoding: Optional[str] = Field(
        None,
        description="File encoding (auto-detected if not specified)"
    )
    max_size: Optional[int] = Field(
        10 * 1024 * 1024,  # 10MB default
        description="Maximum file size to read in bytes",
        ge=1,
        le=100 * 1024 * 1024  # 100MB max
    )
    start_line: Optional[int] = Field(
        None,
        description="Starting line number (1-based)",
        ge=1
    )
    end_line: Optional[int] = Field(
        None,
        description="Ending line number (1-based)",
        ge=1
    )
    max_lines: Optional[int] = Field(
        None,
        description="Maximum number of lines to read",
        ge=1,
        le=100000
    )
    binary_mode: bool = Field(
        False,
        description="Read file in binary mode"
    )
    
    @validator('file_path')
    def validate_file_path(cls, v):
        """Validate file path."""
        if not v or not v.strip():
            raise ValueError("File path cannot be empty")
        return v.strip()
    
    @validator('end_line')
    def validate_line_range(cls, v, values):
        """Validate line range."""
        if v is not None and 'start_line' in values and values['start_line'] is not None:
            if v < values['start_line']:
                raise ValueError("End line must be greater than or equal to start line")
        return v
    
    @validator('encoding')
    def validate_encoding(cls, v):
        """Validate encoding."""
        if v is not None:
            v = v.strip().lower()
            if not v:
                return None
            # Test if encoding is valid
            try:
                "test".encode(v)
            except LookupError:
                raise ValueError(f"Unknown encoding: {v}")
        return v


class FileReadTool(Tool):
    """
    Tool for reading files safely.
    
    This tool provides secure file reading with automatic encoding detection,
    permission checking, and various reading modes (full, partial, binary).
    """
    
    def __init__(self, permission_manager: Optional[PermissionManager] = None, session_manager=None):
        """Initialize FileRead tool."""
        super().__init__(
            name="file_read",
            description="Read file contents safely with permission controls and encoding detection",
            version="1.0.0",
            session_manager=session_manager
        )
        self.permission_manager = permission_manager or PermissionManager()
        self.path_validator = PathValidator(self.permission_manager.get_allowed_paths())
        
        # Common text encodings to try
        self.common_encodings = [
            'utf-8', 'utf-8-sig', 'ascii', 'latin1', 'cp1252',
            'utf-16', 'utf-16le', 'utf-16be', 'utf-32'
        ]
    
    def get_input_schema(self) -> Type[ToolInput]:
        """Return the input schema for this tool."""
        return FileReadInput
    
    async def validate_input(self, input_data: Dict[str, Any]) -> FileReadInput:
        """Validate and parse tool input data."""
        return FileReadInput(**input_data)
    
    async def check_permissions(self, input_data: FileReadInput) -> bool:
        """Check if the tool has permission to read the file."""
        # Check file permission
        permission_result = self.permission_manager.check_file_permission(
            input_data.file_path, "read"
        )
        
        if not permission_result.granted:
            return False
        
        # Validate path safety
        is_safe, _ = self.path_validator.validate_path(
            input_data.file_path, "read"
        )
        
        return is_safe
    
    async def execute(self, input_data: FileReadInput) -> AsyncGenerator[ToolResult, None]:
        """Execute file reading operation."""
        execution_id = input_data.execution_id
        file_path = input_data.file_path
        
        # Access session information if available
        session = await self.get_session(input_data)
        if session:
            # Log file read operation to session
            session.add_log_entry(f"Reading file: {file_path}")
            yield ToolResult(
                type=ToolResultType.INFO,
                content=f"Reading file in session {session.id}",
                execution_id=execution_id,
                metadata={
                    "session_id": session.id,
                    "file_path": file_path
                }
            )
        
        try:
            # Normalize and validate path
            normalized_path = os.path.abspath(file_path)
            
            yield ToolResult(
                type=ToolResultType.INFO,
                content=f"Reading file: {normalized_path}",
                execution_id=execution_id,
                metadata={"file_path": normalized_path}
            )
            
            # Check if file exists
            if not os.path.exists(normalized_path):
                yield ToolResult(
                    type=ToolResultType.ERROR,
                    content=f"File not found: {normalized_path}",
                    execution_id=execution_id
                )
                return
            
            # Check if it's a file (not directory)
            if not os.path.isfile(normalized_path):
                yield ToolResult(
                    type=ToolResultType.ERROR,
                    content=f"Path is not a file: {normalized_path}",
                    execution_id=execution_id
                )
                return
            
            # Check file size
            file_size = os.path.getsize(normalized_path)
            if input_data.max_size and file_size > input_data.max_size:
                yield ToolResult(
                    type=ToolResultType.ERROR,
                    content=f"File size ({file_size} bytes) exceeds maximum ({input_data.max_size} bytes)",
                    execution_id=execution_id,
                    metadata={"file_size": file_size, "max_size": input_data.max_size}
                )
                return
            
            # Get file info
            file_stat = os.stat(normalized_path)
            mime_type, _ = mimetypes.guess_type(normalized_path)
            
            yield ToolResult(
                type=ToolResultType.INFO,
                content=f"File info - Size: {file_size} bytes, Type: {mime_type or 'unknown'}",
                execution_id=execution_id,
                metadata={
                    "file_size": file_size,
                    "mime_type": mime_type,
                    "modified_time": file_stat.st_mtime,
                    "permissions": oct(file_stat.st_mode)[-3:]
                }
            )
            
            # Read file content
            if input_data.binary_mode:
                async for result in self._read_binary_file(normalized_path, input_data, execution_id):
                    yield result
            else:
                async for result in self._read_text_file(normalized_path, input_data, execution_id):
                    yield result
            
            yield ToolResult(
                type=ToolResultType.SUCCESS,
                content=f"Successfully read file: {normalized_path}",
                execution_id=execution_id
            )
            
        except PermissionError:
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"Permission denied reading file: {file_path}",
                execution_id=execution_id
            )
            
        except UnicodeDecodeError as e:
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"Unicode decode error: {str(e)}",
                execution_id=execution_id,
                metadata={"encoding_tried": getattr(e, 'encoding', 'unknown')}
            )
            
        except Exception as e:
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"Error reading file: {str(e)}",
                execution_id=execution_id,
                metadata={"error_type": type(e).__name__}
            )
    
    async def _read_text_file(
        self, 
        file_path: str, 
        input_data: FileReadInput, 
        execution_id: str
    ) -> AsyncGenerator[ToolResult, None]:
        """Read text file with encoding detection."""
        encoding = input_data.encoding
        
        # If encoding not specified, try to detect it
        if not encoding:
            encoding = await self._detect_encoding(file_path)
            yield ToolResult(
                type=ToolResultType.INFO,
                content=f"Detected encoding: {encoding}",
                execution_id=execution_id,
                metadata={"detected_encoding": encoding}
            )
        
        try:
            async with aiofiles.open(file_path, 'r', encoding=encoding) as f:
                if input_data.start_line or input_data.end_line or input_data.max_lines:
                    # Read specific lines
                    async for result in self._read_lines_range(f, input_data, execution_id):
                        yield result
                else:
                    # Read entire file
                    content = await f.read()
                    
                    # Check if content is too large to output at once
                    if len(content) > 50000:  # 50KB
                        # Split into chunks
                        chunk_size = 10000
                        for i in range(0, len(content), chunk_size):
                            chunk = content[i:i + chunk_size]
                            yield ToolResult(
                                type=ToolResultType.OUTPUT,
                                content=chunk,
                                execution_id=execution_id,
                                metadata={
                                    "chunk_number": i // chunk_size + 1,
                                    "chunk_start": i,
                                    "chunk_end": min(i + chunk_size, len(content))
                                }
                            )
                    else:
                        yield ToolResult(
                            type=ToolResultType.OUTPUT,
                            content=content,
                            execution_id=execution_id,
                            metadata={"content_length": len(content)}
                        )
        
        except UnicodeDecodeError:
            # Try alternative encodings
            for alt_encoding in self.common_encodings:
                if alt_encoding != encoding:
                    try:
                        async with aiofiles.open(file_path, 'r', encoding=alt_encoding) as f:
                            content = await f.read()
                            yield ToolResult(
                                type=ToolResultType.WARNING,
                                content=f"Fallback to encoding: {alt_encoding}",
                                execution_id=execution_id
                            )
                            yield ToolResult(
                                type=ToolResultType.OUTPUT,
                                content=content,
                                execution_id=execution_id,
                                metadata={
                                    "fallback_encoding": alt_encoding,
                                    "content_length": len(content)
                                }
                            )
                            return
                    except UnicodeDecodeError:
                        continue
            
            # If all encodings fail, try binary mode
            yield ToolResult(
                type=ToolResultType.WARNING,
                content="Text decoding failed, attempting binary read",
                execution_id=execution_id
            )
            async for result in self._read_binary_file(file_path, input_data, execution_id):
                yield result
    
    async def _read_binary_file(
        self, 
        file_path: str, 
        input_data: FileReadInput, 
        execution_id: str
    ) -> AsyncGenerator[ToolResult, None]:
        """Read binary file."""
        try:
            async with aiofiles.open(file_path, 'rb') as f:
                content = await f.read()
                
                # Convert to hex representation for display
                hex_content = content.hex()
                
                # Add formatting for readability
                formatted_hex = ' '.join(hex_content[i:i+2] for i in range(0, len(hex_content), 2))
                
                # Split into lines of 32 bytes (64 hex chars + spaces)
                line_length = 96  # 32 bytes * 3 chars per byte (2 hex + 1 space) - 1 space
                formatted_lines = []
                for i in range(0, len(formatted_hex), line_length):
                    line = formatted_hex[i:i+line_length]
                    byte_offset = i // 3
                    formatted_lines.append(f"{byte_offset:08x}: {line}")
                
                yield ToolResult(
                    type=ToolResultType.OUTPUT,
                    content='\n'.join(formatted_lines),
                    execution_id=execution_id,
                    metadata={
                        "binary_size": len(content),
                        "format": "hexdump"
                    }
                )
                
        except Exception as e:
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"Error reading binary file: {str(e)}",
                execution_id=execution_id
            )
    
    async def _read_lines_range(
        self, 
        file_handle, 
        input_data: FileReadInput, 
        execution_id: str
    ) -> AsyncGenerator[ToolResult, None]:
        """Read specific range of lines from file."""
        start_line = input_data.start_line or 1
        end_line = input_data.end_line
        max_lines = input_data.max_lines
        
        line_number = 0
        lines_read = 0
        
        async for line in file_handle:
            line_number += 1
            
            # Skip lines before start_line
            if line_number < start_line:
                continue
            
            # Stop if we've reached end_line
            if end_line and line_number > end_line:
                break
            
            # Stop if we've read max_lines
            if max_lines and lines_read >= max_lines:
                break
            
            # Output the line
            yield ToolResult(
                type=ToolResultType.OUTPUT,
                content=f"{line_number:6d}: {line.rstrip()}",
                execution_id=execution_id,
                metadata={"line_number": line_number}
            )
            
            lines_read += 1
        
        yield ToolResult(
            type=ToolResultType.INFO,
            content=f"Read {lines_read} lines (from line {start_line})",
            execution_id=execution_id,
            metadata={
                "lines_read": lines_read,
                "start_line": start_line,
                "end_line": line_number
            }
        )
    
    async def _detect_encoding(self, file_path: str) -> str:
        """Detect file encoding."""
        try:
            # Import chardet for better detection
            import chardet
            
            # Read a sample of the file
            with open(file_path, 'rb') as f:
                raw_data = f.read(10000)  # Read first 10KB
            
            detection = chardet.detect(raw_data)
            if detection and detection['encoding'] and detection['confidence'] > 0.7:
                return detection['encoding'].lower()
        except Exception:
            pass
        
        # Fallback: try common encodings
        for encoding in self.common_encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    f.read(1000)  # Try to read first 1KB
                return encoding
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        # Last resort
        return 'utf-8'


# Register the tool
file_read_tool = FileReadTool()
ToolRegistry.register(file_read_tool)