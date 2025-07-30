"""
Chat endpoints for SimaCode API (with safe imports).

Provides REST and WebSocket endpoints for AI chat functionality.
"""

import logging
from typing import AsyncGenerator

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException
    from fastapi.responses import StreamingResponse
    
    from ..dependencies import get_simacode_service
    from ..models import ChatRequest, ChatResponse, ErrorResponse, StreamingChatChunk
    from ...core.service import SimaCodeService, ChatRequest as CoreChatRequest
    
    router = APIRouter()

    @router.post("/", response_model=ChatResponse)
    async def chat(
        request: ChatRequest,
        service: SimaCodeService = Depends(get_simacode_service)
    ) -> ChatResponse:
        """Process a chat message with the AI assistant."""
        try:
            # Convert API request to core request
            core_request = CoreChatRequest(
                message=request.message,
                session_id=request.session_id,
                context=request.context,
                stream=False
            )
            
            # Process through service
            response = await service.process_chat(core_request)
            
            if response.error:
                raise HTTPException(status_code=500, detail=response.error)
                
            return ChatResponse(
                content=response.content,
                session_id=response.session_id,
                metadata=response.metadata
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Chat processing error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @router.get("/health")
    async def chat_health():
        """Chat module health check."""
        return {"status": "healthy", "module": "chat"}

except ImportError:
    # FastAPI not available, create empty router placeholder
    router = None
    
    def chat(*args, **kwargs):
        raise ImportError("FastAPI is required for API mode")
    
    def chat_health(*args, **kwargs):
        raise ImportError("FastAPI is required for API mode")