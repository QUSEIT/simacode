"""
API layer for SimaCode dual-mode architecture.

This module provides FastAPI-based REST and WebSocket endpoints
for the backend API service mode.
"""

try:
    from .app import create_app
    __all__ = ['create_app']
except ImportError:
    # FastAPI not installed, API mode not available
    __all__ = []