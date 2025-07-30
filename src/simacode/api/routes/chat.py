"""
Chat endpoints for SimaCode API.

Provides REST and WebSocket endpoints for AI chat functionality.
"""

import logging
from typing import AsyncGenerator

try:
    from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException
    from fastapi.responses import StreamingResponse
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = None

from ..dependencies import get_simacode_service
from ..models import ChatRequest, ChatResponse, ErrorResponse, StreamingChatChunk
from ...core.service import SimaCodeService, ChatRequest as CoreChatRequest

logger = logging.getLogger(__name__)

if FASTAPI_AVAILABLE:
    router = APIRouter()
else:
    router = None


@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    service: SimaCodeService = Depends(get_simacode_service)
) -> ChatResponse:
    """
    Process a chat message with the AI assistant.
    
    Args:
        request: Chat request containing message and optional session ID
        service: SimaCode service instance
        
    Returns:
        AI response
    """
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


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    service: SimaCodeService = Depends(get_simacode_service)
):
    """
    Process a chat message with streaming response.
    
    Args:
        request: Chat request containing message and optional session ID
        service: SimaCode service instance
        
    Returns:
        Streaming response with chat chunks
    """
    try:
        # Convert API request to core request
        core_request = CoreChatRequest(
            message=request.message,
            session_id=request.session_id,
            context=request.context,
            stream=True
        )
        
        async def generate_chunks():
            try:
                # Get streaming response from service
                response_gen = await service.process_chat(core_request)
                
                if hasattr(response_gen, '__aiter__'):
                    # Streaming response
                    session_id = request.session_id or "new"
                    async for chunk in response_gen:
                        chunk_data = StreamingChatChunk(
                            chunk=chunk,
                            session_id=session_id,
                            finished=False
                        )
                        yield f"data: {chunk_data.model_dump_json()}\n\n"
                    
                    # Send finished signal
                    final_chunk = StreamingChatChunk(
                        chunk="",
                        session_id=session_id,
                        finished=True
                    )
                    yield f"data: {final_chunk.model_dump_json()}\n\n"
                else:
                    # Non-streaming response (fallback)
                    chunk_data = StreamingChatChunk(
                        chunk=response_gen.content,
                        session_id=response_gen.session_id,
                        finished=True
                    )
                    yield f"data: {chunk_data.model_dump_json()}\n\n"
                    
            except Exception as e:
                logger.error(f"Streaming error: {e}")
                error_chunk = StreamingChatChunk(
                    chunk=f"Error: {str(e)}",
                    session_id=request.session_id or "error",
                    finished=True
                )
                yield f"data: {error_chunk.model_dump_json()}\n\n"
        
        return StreamingResponse(
            generate_chunks(),
            media_type="text/plain",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
        
    except Exception as e:
        logger.error(f"Chat streaming setup error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/ws")
async def chat_websocket(
    websocket: WebSocket,
    service: SimaCodeService = Depends(get_simacode_service)
):
    """
    WebSocket endpoint for real-time chat.
    
    Args:
        websocket: WebSocket connection
        service: SimaCode service instance
    """
    await websocket.accept()
    logger.info("WebSocket chat connection established")
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            
            try:
                # Validate message format
                if "message" not in data:
                    await websocket.send_json({
                        "error": "Missing 'message' field",
                        "type": "error"
                    })
                    continue
                
                # Create core request
                core_request = CoreChatRequest(
                    message=data["message"],
                    session_id=data.get("session_id"),
                    context=data.get("context", {}),
                    stream=False
                )
                
                # Process chat request
                response = await service.process_chat(core_request)
                
                if response.error:
                    await websocket.send_json({
                        "error": response.error,
                        "type": "error",
                        "session_id": response.session_id
                    })
                else:
                    await websocket.send_json({
                        "content": response.content,
                        "session_id": response.session_id,
                        "metadata": response.metadata,
                        "type": "response"
                    })
                    
            except Exception as e:
                logger.error(f"WebSocket message processing error: {e}")
                await websocket.send_json({
                    "error": str(e),
                    "type": "error"
                })
                
    except WebSocketDisconnect:
        logger.info("WebSocket chat connection closed")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.close()
        except:
            pass