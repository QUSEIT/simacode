"""
Path resolution utilities for SimaCode.

This module provides utilities for resolving configuration file paths
with fallback handling.
"""

from pathlib import Path
from typing import Optional, Union


def resolve_mcp_config_path(config_path: Optional[Union[str, Path]] = None) -> Path:
    """
    Resolve MCP configuration file path with fallback priority.

    Priority order:
    1. Explicit path (if provided)
    2. Project-specific .simacode/mcp_servers.yaml (if exists)
    3. Default default_config/mcp_servers.yaml (fallback)

    Args:
        config_path: Optional explicit path to config file

    Returns:
        Path: Resolved path to mcp_servers.yaml
    """
    # Use explicit path if provided
    if config_path:
        return Path(config_path).resolve()

    # Check for project-specific MCP configuration first
    project_config_path = Path.cwd() / ".simacode" / "mcp_servers.yaml"
    if project_config_path.exists():
        return project_config_path

    # Fallback to default built-in configuration
    default_config_path = Path(__file__).parent.parent / "default_config" / "mcp_servers.yaml"
    return default_config_path