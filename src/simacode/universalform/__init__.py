"""
Universal Form Generator Module.

This module provides universal form generation capabilities including:
- Dynamic form building interface
- Form configuration management
- Form submission handling
- GET parameter pre-filling
"""

from .app import router

UNIVERSALFORM_AVAILABLE = True

__all__ = ["router", "UNIVERSALFORM_AVAILABLE"]