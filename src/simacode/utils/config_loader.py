"""
Configuration loader utilities for SimaCode.

This module provides utilities to load SimaCode configuration with proper
fallback handling and logging integration.
"""

from pathlib import Path
from typing import Optional
from ..config import Config
from .mcp_logger import mcp_info, mcp_warning


def load_simacode_config(config_path: Optional[Path] = None, tool_name: str = "config_loader") -> Config:
    """
    Load SimaCode configuration with fallback to environment variables.
    
    Args:
        config_path: Optional path to specific config file
        tool_name: Name of the tool requesting config (for logging)
    
    Returns:
        Config: Loaded SimaCode configuration object
    
    Example:
        >>> config = load_simacode_config()
        >>> smtp_config = SMTPConfig.from_simacode_config(config)
    """
    try:
        # Try to load SimaCode configuration
        config = Config.load(config_path=config_path)
        mcp_info("[CONFIG_LOAD] Successfully loaded SimaCode configuration", tool_name=tool_name)
        return config
    except Exception as e:
        mcp_warning(f"[CONFIG_LOAD] Failed to load SimaCode config: {e}", tool_name=tool_name)
        mcp_info("[CONFIG_LOAD] Falling back to environment variables and defaults", tool_name=tool_name)
        
        # Return default config - configuration will be populated from environment variables
        return Config.load()