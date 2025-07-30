"""
Core services for SimaCode dual-mode architecture.

This module provides the unified service layer that supports both
CLI and API modes with consistent functionality.
"""

from .service import SimaCodeService

__all__ = ['SimaCodeService']