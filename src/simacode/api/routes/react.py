"""
ReAct endpoints for SimaCode API.

Provides REST and WebSocket endpoints for ReAct task execution.
"""

import logging
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import StreamingResponse

from ..dependencies import get_simacode_service
from ..models import (
    ReActRequest, ReActResponse, ErrorResponse,
    AsyncTaskResponse, TaskStatusResponse, TaskProgressUpdate
)
from ...core.service import SimaCodeService, ReActRequest as CoreReActRequest
from ...mcp.async_integration import get_global_task_manager, TaskType

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


@router.post("/execute/async", response_model=AsyncTaskResponse)
async def execute_react_task_async(
    request: ReActRequest,
    service: SimaCodeService = Depends(get_simacode_service)
) -> AsyncTaskResponse:
    """
    Submit a ReAct task for asynchronous execution.

    This endpoint is designed for long-running tasks that may take
    several minutes to complete. Returns immediately with a task ID
    that can be used to track progress and retrieve results.

    Args:
        request: ReAct request containing task and optional session ID
        service: SimaCode service instance

    Returns:
        Task submission confirmation with task ID
    """
    try:
        # Convert API request to core request
        core_request = CoreReActRequest(
            task=request.task,
            session_id=request.session_id,
            context=request.context,
            execution_mode=request.execution_mode
        )

        # Check if task requires async execution
        if not await service._requires_async_execution(core_request):
            # For simple tasks, redirect to synchronous execution
            response = await service.process_react(core_request)
            if response.error:
                raise HTTPException(status_code=500, detail=response.error)

            # Return a "completed" async response for consistency
            return AsyncTaskResponse(
                task_id=f"sync_{response.session_id}",
                status="completed",
                session_id=response.session_id
            )

        # Submit task to async task manager
        task_manager = get_global_task_manager()
        task_id = await task_manager.submit_task(
            task_type=TaskType.REACT,
            request=core_request
        )

        logger.info(f"Async ReAct task {task_id} submitted for session {core_request.session_id}")

        return AsyncTaskResponse(
            task_id=task_id,
            status="pending",
            session_id=core_request.session_id
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Async ReAct task submission error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(
    task_id: str,
    service: SimaCodeService = Depends(get_simacode_service)
) -> TaskStatusResponse:
    """
    Get the status of an async ReAct task.

    Args:
        task_id: The task identifier returned from /execute/async
        service: SimaCode service instance

    Returns:
        Current task status and metadata
    """
    try:
        # Handle sync task IDs (fake async responses)
        if task_id.startswith("sync_"):
            return TaskStatusResponse(
                task_id=task_id,
                task_type="react",
                status="completed",
                created_at=0,
                completed_at=0,
                metadata={"sync_task": True}
            )

        task_manager = get_global_task_manager()
        task = await task_manager.get_task_status(task_id)

        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        return TaskStatusResponse(
            task_id=task.task_id,
            task_type=task.task_type.value,
            status=task.status.value,
            created_at=task.created_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
            error=task.error,
            metadata=task.metadata or {}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Task status query error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}/progress")
async def get_task_progress_stream(
    task_id: str,
    service: SimaCodeService = Depends(get_simacode_service)
):
    """
    Get real-time progress updates for an async ReAct task.

    This endpoint provides Server-Sent Events (SSE) streaming of task progress.

    Args:
        task_id: The task identifier returned from /execute/async
        service: SimaCode service instance

    Returns:
        SSE stream of progress updates
    """
    try:
        # Handle sync task IDs
        if task_id.startswith("sync_"):
            async def sync_response():
                progress = TaskProgressUpdate(
                    task_id=task_id,
                    type="final_result",
                    message="Synchronous task already completed",
                    progress=100.0,
                    timestamp=0,
                    data={"sync_task": True}
                )
                yield f"data: {progress.model_dump_json()}\n\n"

            return StreamingResponse(
                sync_response(),
                media_type="text/plain",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
            )

        task_manager = get_global_task_manager()

        # Check if task exists
        task = await task_manager.get_task_status(task_id)
        if not task:
            raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

        async def generate_progress():
            try:
                async for progress_data in task_manager.get_task_progress_stream(task_id):
                    progress = TaskProgressUpdate(
                        task_id=task_id,
                        type=progress_data.get("type", "progress"),
                        message=progress_data.get("message"),
                        progress=progress_data.get("progress"),
                        timestamp=progress_data.get("timestamp", 0),
                        data=progress_data
                    )
                    yield f"data: {progress.model_dump_json()}\n\n"

                    # Stop streaming after final result
                    if progress_data.get("type") == "final_result":
                        break

            except Exception as e:
                logger.error(f"Progress stream error: {e}")
                error_progress = TaskProgressUpdate(
                    task_id=task_id,
                    type="error",
                    message=f"Progress stream error: {str(e)}",
                    progress=0,
                    timestamp=0,
                    data={"error": str(e)}
                )
                yield f"data: {error_progress.model_dump_json()}\n\n"

        return StreamingResponse(
            generate_progress(),
            media_type="text/plain",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Progress stream setup error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/ws/async")
async def react_async_websocket(
    websocket: WebSocket,
    service: SimaCodeService = Depends(get_simacode_service)
):
    """
    WebSocket endpoint for real-time async ReAct task execution with progress updates.

    Protocol:
    - Client sends: {"task": "...", "session_id": "...", "context": {...}}
    - Server responds with task_id and then streams progress updates
    - Final message contains the complete result

    Args:
        websocket: WebSocket connection
        service: SimaCode service instance
    """
    await websocket.accept()
    logger.info("WebSocket async ReAct connection established")

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

                # Check if task requires async execution
                if not await service._requires_async_execution(core_request):
                    # Execute synchronously for simple tasks
                    await websocket.send_json({
                        "type": "sync_execution",
                        "message": "Executing simple task synchronously"
                    })

                    response = await service.process_react(core_request)

                    if response.error:
                        await websocket.send_json({
                            "error": response.error,
                            "type": "error",
                            "session_id": response.session_id
                        })
                    else:
                        await websocket.send_json({
                            "result": response.result,
                            "session_id": response.session_id,
                            "steps": response.steps,
                            "metadata": response.metadata,
                            "type": "task_completed"
                        })
                    continue

                # Submit async task
                task_manager = get_global_task_manager()
                task_id = await task_manager.submit_task(
                    task_type=TaskType.REACT,
                    request=core_request
                )

                # Send task submission confirmation
                await websocket.send_json({
                    "type": "task_submitted",
                    "task_id": task_id,
                    "session_id": core_request.session_id,
                    "message": "Task submitted for async execution"
                })

                # Stream progress updates
                try:
                    async for progress_data in task_manager.get_task_progress_stream(task_id):
                        await websocket.send_json({
                            "type": "progress_update",
                            "task_id": task_id,
                            "progress": progress_data
                        })

                        # Stop streaming after final result
                        if progress_data.get("type") == "final_result":
                            break

                except Exception as e:
                    logger.error(f"Progress streaming error: {e}")
                    await websocket.send_json({
                        "type": "stream_error",
                        "task_id": task_id,
                        "error": str(e)
                    })

            except Exception as e:
                logger.error(f"WebSocket async ReAct processing error: {e}")
                await websocket.send_json({
                    "error": str(e),
                    "type": "error"
                })

    except WebSocketDisconnect:
        logger.info("WebSocket async ReAct connection closed")
    except Exception as e:
        logger.error(f"WebSocket async ReAct error: {e}")
        try:
            await websocket.close()
        except:
            pass