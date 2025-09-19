"""
FastAPI application factory for SimaCode API service mode.

This module creates and configures the FastAPI application with all
necessary routes, middleware, and dependencies.
"""

import logging
import time
import json
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import Config
from ..core.service import SimaCodeService

logger = logging.getLogger(__name__)

from .routes import chat, react, health, sessions, tasks
from .routes import config as config_routes
from ..universalform import router as universalform_router, UNIVERSALFORM_AVAILABLE
from .models import ErrorResponse

class DebugLoggingMiddleware(BaseHTTPMiddleware):
        """中间件用于记录HTTP请求和响应的DEBUG信息"""
        
        async def dispatch(self, request: Request, call_next):
            # 记录请求开始时间
            start_time = time.time()
            
            # 获取请求信息
            method = request.method
            url = str(request.url)
            headers = dict(request.headers)
            client_ip = request.client.host if request.client else "unknown"
            
            # 安全地尝试读取请求体
            request_body = None
            if method in ["POST", "PUT", "PATCH"]:
                try:
                    # 使用内置方法读取JSON，这样比较安全
                    if headers.get("content-type", "").startswith("application/json"):
                        try:
                            request_body = await request.json()
                        except Exception:
                            # 如果JSON解析失败，尝试读取原始文本
                            try:
                                body_bytes = await request.body()
                                request_body = body_bytes.decode("utf-8", errors="replace")[:500]  # 限制长度
                            except Exception:
                                request_body = "<Failed to read body>"
                except Exception:
                    request_body = "<Failed to read body>"
            
            # 记录请求信息
            logger.debug("="*80)
            logger.debug(f"🔵 HTTP REQUEST | {method} {url}")
            logger.debug(f"   Client IP: {client_ip}")
            logger.debug(f"   Headers: {json.dumps(headers, indent=2, ensure_ascii=False)}")
            if request_body is not None:
                if isinstance(request_body, dict):
                    logger.debug(f"   Request Body: {json.dumps(request_body, indent=2, ensure_ascii=False)}")
                else:
                    logger.debug(f"   Request Body: {request_body}")
            logger.debug("-"*80)
            
            try:
                # 处理请求
                response = await call_next(request)
                
                # 计算处理时间
                process_time = time.time() - start_time
                
                # 获取响应信息
                status_code = response.status_code
                response_headers = dict(response.headers)
                
                # 记录响应信息
                logger.debug(f"🔴 HTTP RESPONSE | {method} {url}")
                logger.debug(f"   Status: {status_code}")
                logger.debug(f"   Process Time: {process_time:.3f}s")
                logger.debug(f"   Response Headers: {json.dumps(response_headers, indent=2, ensure_ascii=False)}")
                
                # 对于非流式响应，尝试记录响应体
                content_type = response_headers.get("content-type", "").lower()
                if not content_type.startswith("text/plain") and hasattr(response, 'body'):
                    try:
                        # 只对JSON响应尝试读取body
                        if "application/json" in content_type:
                            logger.debug(f"   Response Body: <JSON response, {response_headers.get('content-length', 'unknown')} bytes>")
                        elif content_type.startswith("text/"):
                            logger.debug(f"   Response Body: <Text response>")
                        else:
                            logger.debug(f"   Response Body: <{content_type} response>")
                    except Exception:
                        logger.debug(f"   Response Body: <Unable to read>")
                else:
                    logger.debug(f"   Response Body: <Streaming response or other>")
                
                logger.debug("="*80)
                
                return response
                
            except Exception as e:
                # 记录异常
                process_time = time.time() - start_time
                logger.debug(f"🔴 HTTP RESPONSE | {method} {url}")
                logger.debug(f"   Status: ERROR")
                logger.debug(f"   Process Time: {process_time:.3f}s")
                logger.debug(f"   Exception: {str(e)}")
                logger.debug("="*80)
                raise


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    logger.info("Starting SimaCode API server...")

    # Get the SimaCode service from app state (set during app creation)
    simacode_service = getattr(app.state, 'simacode_service', None)
    if simacode_service is None:
        logger.error("SimaCode service not found in app state")
        raise RuntimeError("SimaCode service not properly initialized")

    try:
        await simacode_service.start_async()
        logger.info("SimaCode service started in application lifespan")
    except Exception as e:
        logger.error(f"Failed to start SimaCode service: {e}")
        raise

    yield

    # Stop the service when shutting down
    try:
        await simacode_service.stop_async()
        logger.info("SimaCode service stopped")
    except Exception as e:
        logger.error(f"Error stopping SimaCode service: {e}")

    logger.info("Shutting down SimaCode API server...")


def create_app(config: Config):
    """
    Create and configure FastAPI application.
    
    Args:
        config: SimaCode configuration object
        
    Returns:
        Configured FastAPI application
    """
    
    app = FastAPI(
        title="SimaCode API",
        description="AI programming assistant with ReAct capabilities",
        version="1.0.0",
        lifespan=lifespan
    )
    
    # Add debug logging middleware if in DEBUG mode
    if config.logging.level.upper() == "DEBUG":
        app.add_middleware(DebugLoggingMiddleware)
        logger.info("🐛 DEBUG logging middleware enabled - HTTP requests/responses will be logged")
    
    # Add CORS middleware for local development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:8080", "http://127.0.0.1:8100"],  # Add your frontend URLs
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
    app.include_router(config_routes.router, prefix="/api/v1/config", tags=["config"])
    app.include_router(tasks.router, prefix="/api/v1/tasks", tags=["tasks"])
    
    # Include universal form router if available
    if UNIVERSALFORM_AVAILABLE and universalform_router:
        app.include_router(universalform_router, prefix="/universalform", tags=["universalform"])
        app.include_router(universalform_router, prefix="/api/universalform", tags=["universalform-api"])
    
    return app
