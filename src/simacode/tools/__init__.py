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

def initialize_tools_with_session_manager(session_manager=None):
    """
    Initialize or re-register tools with SessionManager dependency.
    
    Args:
        session_manager: SessionManager instance to inject into tools
    """
    # Clear existing tools to re-register with session manager
    ToolRegistry.clear()
    
    # Register tools with session manager
    tools = [
        BashTool(session_manager=session_manager),
        FileReadTool(session_manager=session_manager),
        FileWriteTool(session_manager=session_manager),
        MCPContentExtraction(session_manager=session_manager),
        ContentForwardURL(session_manager=session_manager),
    ]
    
    # Try to register UniversalOCRTool if available
    try:
        ocr_tool = UniversalOCRTool(session_manager=session_manager)
        tools.append(ocr_tool)
    except Exception:
        # OCR tool may have additional dependencies
        pass
    
    # Register all tools
    for tool in tools:
        ToolRegistry.register(tool)
    
    return tools


__all__ = [
    "Tool",
    "ToolResult", 
    "ToolInput",
    "ToolRegistry",
    "ToolResultType",
    "execute_tool",
    "initialize_tools_with_session_manager",
    "BashTool",
    "FileReadTool",
    "FileWriteTool",
    "UniversalOCRTool",
    # "EmailSendTool",  # Migrated to MCP server: tools/mcp_smtp_send_email.py
    "MCPContentExtraction",
    "ContentForwardURL",
]