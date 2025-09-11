"""
MCP Tools File Logger

A specialized logging utility for MCP tools that writes debug messages 
to the .simacode/logs directory. This is designed to help debug MCP tools
when their console output is not visible.

Features:
- Automatic log directory creation
- Thread-safe file operations
- Structured log format with timestamps
- Log rotation to prevent disk space issues
- Easy integration with MCP tools

Usage:
    from src.simacode.utils.mcp_logger import mcp_file_log
    
    # Simple logging
    mcp_file_log("debug", "My debug message")
    mcp_file_log("info", "Tool started", tool_name="ticmaker")
    
    # With structured data
    mcp_file_log("debug", "Session context received", {
        "session_id": "abc123",
        "tool_name": "ticmaker",
        "data": {"key": "value"}
    })
"""

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

# Thread lock for file operations
_log_lock = threading.Lock()

# Global log configuration
_mcp_log_config = {
    "log_dir": Path.cwd() / ".simacode" / "logs",
    "max_file_size": 10 * 1024 * 1024,  # 10MB
    "max_files": 5,
    "enable_console": False  # Since MCP tools run in stdio mode
}


def get_mcp_log_path(tool_name: str = "mcp_tools") -> Path:
    """
    Get the log file path for a specific MCP tool.
    
    Args:
        tool_name: Name of the MCP tool (used as log filename)
        
    Returns:
        Path: Full path to the log file
    """
    log_dir = _mcp_log_config["log_dir"]
    return log_dir / f"{tool_name}.log"


def setup_mcp_logger(
    log_dir: Optional[Union[str, Path]] = None,
    max_file_size: Optional[int] = None,
    max_files: Optional[int] = None,
    enable_console: bool = False
) -> None:
    """
    Setup MCP logger configuration.
    
    Args:
        log_dir: Custom log directory (defaults to .simacode/logs)
        max_file_size: Maximum size per log file in bytes
        max_files: Maximum number of log files to keep
        enable_console: Whether to also log to console (usually False for MCP tools)
    """
    global _mcp_log_config
    
    if log_dir:
        _mcp_log_config["log_dir"] = Path(log_dir)
    if max_file_size:
        _mcp_log_config["max_file_size"] = max_file_size
    if max_files:
        _mcp_log_config["max_files"] = max_files
    
    _mcp_log_config["enable_console"] = enable_console
    
    # Ensure log directory exists
    _mcp_log_config["log_dir"].mkdir(parents=True, exist_ok=True)


def _rotate_log_file(log_file: Path) -> None:
    """
    Rotate log file if it exceeds max size.
    
    Args:
        log_file: Path to the log file
    """
    if not log_file.exists():
        return
    
    # Check if rotation is needed
    if log_file.stat().st_size < _mcp_log_config["max_file_size"]:
        return
    
    # Rotate existing files
    max_files = _mcp_log_config["max_files"]
    
    # Remove the oldest file if it exists
    oldest_file = log_file.with_suffix(f".log.{max_files}")
    if oldest_file.exists():
        oldest_file.unlink()
    
    # Rotate numbered files
    for i in range(max_files - 1, 0, -1):
        current_file = log_file.with_suffix(f".log.{i}")
        next_file = log_file.with_suffix(f".log.{i + 1}")
        
        if current_file.exists():
            current_file.rename(next_file)
    
    # Move current log to .log.1
    if log_file.exists():
        backup_file = log_file.with_suffix(".log.1")
        log_file.rename(backup_file)


def mcp_file_log(
    level: str,
    message: str,
    data: Optional[Union[Dict[str, Any], str]] = None,
    tool_name: str = "mcp_tools",
    session_id: Optional[str] = None,
    **kwargs
) -> None:
    """
    Write a log entry to the MCP tools log file.
    
    Args:
        level: Log level (debug, info, warning, error, critical)
        message: Log message
        data: Additional data to include (dict or string)
        tool_name: Name of the MCP tool (used for log filename)
        session_id: Optional session ID for context
        **kwargs: Additional key-value pairs to include in log
        
    Example:
        mcp_file_log("info", "Tool started")
        mcp_file_log("debug", "Processing request", {"user_input": "test"})
        mcp_file_log("error", "Failed to process", tool_name="ticmaker", session_id="abc123")
    """
    # Ensure log directory exists
    log_dir = _mcp_log_config["log_dir"]
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # Get log file path
    log_file = get_mcp_log_path(tool_name)
    
    # Create log entry
    timestamp = datetime.now().isoformat()
    log_entry = {
        "timestamp": timestamp,
        "level": level.upper(),
        "tool_name": tool_name,
        "message": message
    }
    
    # Add session ID if provided
    if session_id:
        log_entry["session_id"] = session_id
    
    # Add data if provided
    if data is not None:
        if isinstance(data, dict):
            log_entry["data"] = data
        else:
            log_entry["data"] = str(data)
    
    # Add any additional kwargs
    for key, value in kwargs.items():
        if key not in log_entry:
            log_entry[key] = value
    
    # Format log line
    log_line = json.dumps(log_entry, ensure_ascii=False, separators=(',', ':'))
    
    # Write to file (thread-safe)
    with _log_lock:
        try:
            # Rotate if needed
            _rotate_log_file(log_file)
            
            # Write log entry
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(log_line + '\n')
                f.flush()  # Ensure immediate write
            
            # Also log to console if enabled
            if _mcp_log_config["enable_console"]:
                console_msg = f"[{timestamp}] {level.upper()} - {tool_name}: {message}"
                if data:
                    console_msg += f" | Data: {data}"
                print(console_msg)
                
        except Exception as e:
            # If logging fails, try to log the error to stderr
            # but don't raise an exception to avoid breaking the MCP tool
            error_msg = f"MCP Logger Error: Failed to write to {log_file}: {str(e)}"
            try:
                import sys
                print(error_msg, file=sys.stderr)
            except:
                pass  # If even stderr fails, silently continue


def mcp_debug(message: str, data: Optional[Any] = None, **kwargs) -> None:
    """Convenience function for debug logging."""
    mcp_file_log("debug", message, data, **kwargs)


def mcp_info(message: str, data: Optional[Any] = None, **kwargs) -> None:
    """Convenience function for info logging."""
    mcp_file_log("info", message, data, **kwargs)


def mcp_warning(message: str, data: Optional[Any] = None, **kwargs) -> None:
    """Convenience function for warning logging."""
    mcp_file_log("warning", message, data, **kwargs)


def mcp_error(message: str, data: Optional[Any] = None, **kwargs) -> None:
    """Convenience function for error logging."""
    mcp_file_log("error", message, data, **kwargs)


def mcp_critical(message: str, data: Optional[Any] = None, **kwargs) -> None:
    """Convenience function for critical logging."""
    mcp_file_log("critical", message, data, **kwargs)


def get_log_content(
    tool_name: str = "mcp_tools",
    lines: Optional[int] = None,
    level_filter: Optional[str] = None
) -> str:
    """
    Read and return log content for debugging.
    
    Args:
        tool_name: Name of the MCP tool
        lines: Number of recent lines to return (None for all)
        level_filter: Only return logs of this level (e.g., "error")
        
    Returns:
        str: Log content
    """
    log_file = get_mcp_log_path(tool_name)
    
    if not log_file.exists():
        return f"No log file found at {log_file}"
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
        
        # Filter by level if specified
        if level_filter:
            filtered_lines = []
            for line in all_lines:
                try:
                    log_data = json.loads(line.strip())
                    if log_data.get("level", "").lower() == level_filter.lower():
                        filtered_lines.append(line)
                except json.JSONDecodeError:
                    # Keep non-JSON lines as-is
                    filtered_lines.append(line)
            all_lines = filtered_lines
        
        # Limit number of lines if specified
        if lines and len(all_lines) > lines:
            all_lines = all_lines[-lines:]
        
        return ''.join(all_lines)
        
    except Exception as e:
        return f"Error reading log file {log_file}: {str(e)}"


def clear_logs(tool_name: Optional[str] = None) -> None:
    """
    Clear log files.
    
    Args:
        tool_name: Specific tool to clear logs for (None to clear all)
    """
    log_dir = _mcp_log_config["log_dir"]
    
    if not log_dir.exists():
        return
    
    if tool_name:
        # Clear specific tool logs
        log_file = get_mcp_log_path(tool_name)
        if log_file.exists():
            log_file.unlink()
        
        # Also clear rotated files
        for i in range(1, _mcp_log_config["max_files"] + 1):
            backup_file = log_file.with_suffix(f".log.{i}")
            if backup_file.exists():
                backup_file.unlink()
    else:
        # Clear all MCP log files
        for log_file in log_dir.glob("*.log*"):
            log_file.unlink()


# Initialize default configuration
setup_mcp_logger()