"""
Universal Form Generator Module.

This module provides universal form generation capabilities including:
- Dynamic form building interface
- Form configuration management
- Form submission handling
- GET parameter pre-filling
"""

try:
    from .app import router
    UNIVERSALFORM_AVAILABLE = True
except ImportError:
    UNIVERSALFORM_AVAILABLE = False
    router = None

__all__ = ["router", "UNIVERSALFORM_AVAILABLE"]