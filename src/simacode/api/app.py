"""
FastAPI application factory for SimaCode API service mode.

This module creates and configures the FastAPI application with all
necessary routes, middleware, and dependencies.
"""

import logging
from contextlib import asynccontextmanager
from typing import Dict, Any

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    FastAPI = None

from ..config import Config
from ..core.service import SimaCodeService

logger = logging.getLogger(__name__)

if FASTAPI_AVAILABLE:
    from .routes import chat, react, health, sessions
    from .models import ErrorResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting SimaCode API server...")
    yield
    logger.info("Shutting down SimaCode API server...")


def create_app(config: Config):
    """
    Create and configure FastAPI application.
    
    Args:
        config: SimaCode configuration object
        
    Returns:
        Configured FastAPI application
        
    Raises:
        ImportError: If FastAPI is not installed
    """
    if not FASTAPI_AVAILABLE:
        raise ImportError(
            "FastAPI is required for API mode. "
            "Install with: pip install 'simacode[api]'"
        )
    
    app = FastAPI(
        title="SimaCode API",
        description="AI programming assistant with ReAct capabilities",
        version="1.0.0",
        lifespan=lifespan
    )
    
    # Add CORS middleware for local development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:8080"],  # Add your frontend URLs
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Store config and service in app state
    app.state.config = config
    app.state.simacode_service = SimaCodeService(config)
    
    # Add exception handlers
    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc):
        logger.error(f"Unhandled exception: {exc}")
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error="Internal server error",
                detail=str(exc) if config.logging.level == "DEBUG" else "An unexpected error occurred"
            ).model_dump()
        )
    
    # Include routers
    app.include_router(health.router, prefix="/health", tags=["health"])
    app.include_router(chat.router, prefix="/api/v1/chat", tags=["chat"])
    app.include_router(react.router, prefix="/api/v1/react", tags=["react"])
    app.include_router(sessions.router, prefix="/api/v1/sessions", tags=["sessions"])
    
    return app