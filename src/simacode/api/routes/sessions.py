"""
Session management endpoints for SimaCode API.

Provides endpoints for managing user sessions across chat and ReAct interactions.
"""

import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_simacode_service
from ..models import SessionInfo, ErrorResponse
from ...core.service import SimaCodeService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=List[SessionInfo])
async def list_sessions(
    limit: int = 10,
    service: SimaCodeService = Depends(get_simacode_service)
) -> List[SessionInfo]:
    """
    List active sessions.
    
    Args:
        limit: Maximum number of sessions to return
        service: SimaCode service instance
        
    Returns:
        List of session information
    """
    try:
        sessions_data = await service.list_sessions()
        sessions = []
        
        for session_data in sessions_data[:limit]:
            sessions.append(SessionInfo(**session_data))
            
        return sessions
        
    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}", response_model=SessionInfo)
async def get_session(
    session_id: str,
    service: SimaCodeService = Depends(get_simacode_service)
) -> SessionInfo:
    """
    Get information about a specific session.
    
    Args:
        session_id: Session identifier
        service: SimaCode service instance
        
    Returns:
        Session information
    """
    try:
        session_data = await service.get_session_info(session_id)
        
        if "error" in session_data:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
            
        return SessionInfo(**session_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    service: SimaCodeService = Depends(get_simacode_service)
) -> dict:
    """
    Delete a session.
    
    Args:
        session_id: Session identifier
        service: SimaCode service instance
        
    Returns:
        Deletion confirmation
    """
    try:
        success = await service.delete_session(session_id)
        
        if not success:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
            
        return {
            "message": f"Session {session_id} deleted successfully",
            "session_id": session_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))