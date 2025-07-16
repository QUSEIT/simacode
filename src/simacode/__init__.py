"""
SimaCode: A modern AI programming assistant with intelligent ReAct mechanisms.

This package provides a comprehensive AI-powered development assistant that combines
natural language understanding with practical programming capabilities through
a sophisticated ReAct (Reasoning and Acting) framework.

Key Features:
- Intelligent task planning and execution
- Multi-agent system for specialized operations
- Secure file system access with permission management
- Modern terminal-based user interface
- Extensible tool system for custom operations
"""

__version__ = "0.1.0"
__author__ = "SimaCode Team"
__email__ = "team@simacode.com"

from .cli import main
from .config import Config
from .logging_config import setup_logging

__all__ = ["main", "Config", "setup_logging"]