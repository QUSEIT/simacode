"""
Health check endpoints for SimaCode API.

Provides health status and readiness checks for the API service.
"""

import logging
from fastapi import APIRouter, Depends

from ..dependencies import get_simacode_service
from ..models import HealthResponse
from ...core.service import SimaCodeService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=HealthResponse)
async def health_check(
    service: SimaCodeService = Depends(get_simacode_service)
) -> HealthResponse:
    """
    Perform health check on the API service.
    
    Returns:
        Health status information
    """
    try:
        health_data = await service.health_check()
        return HealthResponse(**health_data)
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return HealthResponse(
            status="unhealthy",
            components={"error": str(e)},
            version="1.0.0",
            config={}
        )


@router.get("/ready")
async def readiness_check(
    service: SimaCodeService = Depends(get_simacode_service)
) -> dict:
    """
    Check if the service is ready to handle requests.
    
    Returns:
        Readiness status
    """
    try:
        health_data = await service.health_check()
        ready = health_data.get("status") == "healthy"
        return {
            "ready": ready,
            "status": health_data.get("status", "unknown")
        }
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        return {
            "ready": False,
            "status": "error",
            "error": str(e)
        }


@router.get("/live")
async def liveness_check() -> dict:
    """
    Basic liveness check - just confirms the service is running.
    
    Returns:
        Liveness status
    """
    return {
        "alive": True,
        "timestamp": "2025-01-30T00:00:00Z"  # This would be actual timestamp
    }