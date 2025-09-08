"""
SimaCode Tool System

This module provides a comprehensive tool framework for the SimaCode AI assistant,
enabling secure and controlled execution of various operations including file
operations, system commands, and custom tools.

The tool system is built around a plugin architecture with:
- Base tool abstractions
- Input validation and output formatting
- Permission-based access control
- Tool registration and discovery
- Execution monitoring and logging
"""

from .base import Tool, ToolResult, ToolInput, ToolRegistry, ToolResultType, execute_tool
from .bash import BashTool
from .file_read import FileReadTool
from .file_write import FileWriteTool
from .universal_ocr import UniversalOCRTool
# EmailSendTool has been migrated to MCP server: tools/mcp_smtp_send_email.py
# from .email_send import EmailSendTool
from .smc_content_coder import MCPContentExtraction, ContentForwardURL

__all__ = [
    "Tool",
    "ToolResult", 
    "ToolInput",
    "ToolRegistry",
    "ToolResultType",
    "execute_tool",
    "BashTool",
    "FileReadTool",
    "FileWriteTool",
    "UniversalOCRTool",
    # "EmailSendTool",  # Migrated to MCP server: tools/mcp_smtp_send_email.py
    "MCPContentExtraction",
    "ContentForwardURL",
]