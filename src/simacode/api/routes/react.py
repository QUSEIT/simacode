"""
ReAct endpoints for SimaCode API.

Provides REST and WebSocket endpoints for ReAct task execution.
"""

import logging
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException

from ..dependencies import get_simacode_service
from ..models import ReActRequest, ReActResponse, ErrorResponse
from ...core.service import SimaCodeService, ReActRequest as CoreReActRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/execute", response_model=ReActResponse)
async def execute_react_task(
    request: ReActRequest,
    service: SimaCodeService = Depends(get_simacode_service)
) -> ReActResponse:
    """
    Execute a task using the ReAct engine.
    
    Args:
        request: ReAct request containing task and optional session ID
        service: SimaCode service instance
        
    Returns:
        Task execution result
    """
    try:
        # Convert API request to core request
        core_request = CoreReActRequest(
            task=request.task,
            session_id=request.session_id,
            context=request.context,
            execution_mode=request.execution_mode
        )
        
        # Process through service
        response = await service.process_react(core_request)
        
        if response.error:
            raise HTTPException(status_code=500, detail=response.error)
            
        return ReActResponse(
            result=response.result,
            session_id=response.session_id,
            steps=response.steps,
            metadata=response.metadata
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ReAct processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/ws")
async def react_websocket(
    websocket: WebSocket,
    service: SimaCodeService = Depends(get_simacode_service)
):
    """
    WebSocket endpoint for real-time ReAct task execution.
    
    Args:
        websocket: WebSocket connection
        service: SimaCode service instance
    """
    await websocket.accept()
    logger.info("WebSocket ReAct connection established")
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            
            try:
                # Validate message format
                if "task" not in data:
                    await websocket.send_json({
                        "error": "Missing 'task' field",
                        "type": "error"
                    })
                    continue
                
                # Create core request
                core_request = CoreReActRequest(
                    task=data["task"],
                    session_id=data.get("session_id"),
                    context=data.get("context", {}),
                    execution_mode=data.get("execution_mode")
                )
                
                # Send start notification
                await websocket.send_json({
                    "type": "task_started",
                    "task": data["task"],
                    "session_id": core_request.session_id
                })
                
                # Process ReAct request
                response = await service.process_react(core_request)
                
                if response.error:
                    await websocket.send_json({
                        "error": response.error,
                        "type": "error",
                        "session_id": response.session_id
                    })
                else:
                    # Send step-by-step updates if available
                    for step in response.steps:
                        await websocket.send_json({
                            "type": "step_update",
                            "step": step,
                            "session_id": response.session_id
                        })
                    
                    # Send final result
                    await websocket.send_json({
                        "result": response.result,
                        "session_id": response.session_id,
                        "steps": response.steps,
                        "metadata": response.metadata,
                        "type": "task_completed"
                    })
                    
            except Exception as e:
                logger.error(f"WebSocket ReAct processing error: {e}")
                await websocket.send_json({
                    "error": str(e),
                    "type": "error"
                })
                
    except WebSocketDisconnect:
        logger.info("WebSocket ReAct connection closed")
    except Exception as e:
        logger.error(f"WebSocket ReAct error: {e}")
        try:
            await websocket.close()
        except:
            pass