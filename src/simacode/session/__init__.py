"""
Session Management Module

This module provides session management capabilities for the SimaCode
ReAct engine, including session persistence, state management, and
session lifecycle operations.
"""

from .manager import SessionManager, SessionConfig

__all__ = [
    "SessionManager",
    "SessionConfig",
]