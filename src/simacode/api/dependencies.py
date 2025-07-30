"""
FastAPI dependencies for SimaCode API.

Provides dependency injection for common services and configurations.
"""

from fastapi import Request
from ..core.service import SimaCodeService
from ..config import Config


def get_config(request: Request) -> Config:
    """
    Get the application configuration from request state.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Configuration object
    """
    return request.app.state.config


def get_simacode_service(request: Request) -> SimaCodeService:
    """
    Get the SimaCode service instance from request state.
    
    Args:
        request: FastAPI request object
        
    Returns:
        SimaCode service instance
    """
    return request.app.state.simacode_service