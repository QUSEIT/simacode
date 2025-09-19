"""
Async task management endpoints for SimaCode API.

Provides centralized task status and management endpoints
for all async operations.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from ..dependencies import get_simacode_service
from ..models import TaskStatusResponse, TaskManagerStatsResponse, TaskProgressUpdate
from ...core.service import SimaCodeService
from ...mcp.async_integration import get_global_task_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/status", response_model=TaskManagerStatsResponse)
async def get_task_manager_status(
    service: SimaCodeService = Depends(get_simacode_service)
) -> TaskManagerStatsResponse:
    """
    Get overall task manager status and statistics.

    Returns:
        Current task manager statistics including active tasks and breakdown
    """
    try:
        task_manager = get_global_task_manager()
        stats = task_manager.get_stats()

        return TaskManagerStatsResponse(
            active_tasks=stats["active_tasks"],
            task_breakdown=stats["task_breakdown"]
        )

    except Exception as e:
        logger.error(f"Task manager status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_any_task_status(
    task_id: str,
    service: SimaCodeService = Depends(get_simacode_service)
) -> TaskStatusResponse:
    """
    Get the status of any async task (chat, react, or mcp_tool).

    Args:
        task_id: The task identifier
        service: SimaCode service instance

    Returns:
        Current task status and metadata
    """
    try:
        # Handle sync task IDs (fake async responses)
        if task_id.startswith("sync_"):
            task_type = "unknown"
            if task_id.startswith("sync_chat_"):
                task_type = "chat"
            elif task_id.startswith("sync_react_"):
                task_type = "react"

            return TaskStatusResponse(
                task_id=task_id,
                task_type=task_type,
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


@router.delete("/{task_id}")
async def cancel_task(
    task_id: str,
    service: SimaCodeService = Depends(get_simacode_service)
):
    """
    Cancel an async task.

    Args:
        task_id: The task identifier
        service: SimaCode service instance

    Returns:
        Cancellation confirmation
    """
    try:
        # Handle sync task IDs (cannot be cancelled)
        if task_id.startswith("sync_"):
            raise HTTPException(
                status_code=400,
                detail="Synchronous tasks cannot be cancelled"
            )

        task_manager = get_global_task_manager()
        success = await task_manager.cancel_task(task_id)

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"Task {task_id} not found or cannot be cancelled"
            )

        return {"message": f"Task {task_id} cancelled successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Task cancellation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/restart")
async def restart_task(
    task_id: str,
    service: SimaCodeService = Depends(get_simacode_service)
):
    """
    Restart a failed or cancelled task.

    Args:
        task_id: The task identifier to restart
        service: SimaCode service instance

    Returns:
        New task information
    """
    try:
        # Handle sync task IDs (cannot be restarted)
        if task_id.startswith("sync_"):
            raise HTTPException(
                status_code=400,
                detail="Synchronous tasks cannot be restarted"
            )

        task_manager = get_global_task_manager()
        new_task_id = await task_manager.restart_task(task_id)

        if not new_task_id:
            # Check if task exists and why it can't be restarted
            task = await task_manager.get_task_status(task_id)
            if not task:
                raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Task {task_id} cannot be restarted (status: {task.status.value})"
                )

        return {
            "message": f"Task {task_id} restarted successfully",
            "original_task_id": task_id,
            "new_task_id": new_task_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Task restart error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}/progress")
async def get_task_progress_stream(
    task_id: str,
    service: SimaCodeService = Depends(get_simacode_service)
):
    """
    Get real-time progress updates for any async task via SSE.

    Args:
        task_id: The task identifier
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
                yield f"data: {progress.model_dump_json()}\\n\\n"

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
                    yield f"data: {progress.model_dump_json()}\\n\\n"

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
                yield f"data: {error_progress.model_dump_json()}\\n\\n"

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


@router.websocket("/ws")
async def tasks_websocket(
    websocket: WebSocket,
    service: SimaCodeService = Depends(get_simacode_service)
):
    """
    WebSocket endpoint for real-time task monitoring and management.

    Protocol:
    - Client sends: {"action": "monitor", "task_id": "..."}
    - Client sends: {"action": "cancel", "task_id": "..."}
    - Client sends: {"action": "stats"}
    - Server responds with real-time updates

    Args:
        websocket: WebSocket connection
        service: SimaCode service instance
    """
    await websocket.accept()
    logger.info("WebSocket task management connection established")

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()

            try:
                action = data.get("action")

                if action == "monitor":
                    # Monitor specific task progress
                    task_id = data.get("task_id")
                    if not task_id:
                        await websocket.send_json({
                            "error": "Missing 'task_id' field for monitor action",
                            "type": "error"
                        })
                        continue

                    # Handle sync task IDs
                    if task_id.startswith("sync_"):
                        await websocket.send_json({
                            "type": "progress_update",
                            "task_id": task_id,
                            "progress": {
                                "type": "final_result",
                                "message": "Synchronous task already completed",
                                "progress": 100.0,
                                "data": {"sync_task": True}
                            }
                        })
                        continue

                    task_manager = get_global_task_manager()

                    # Check if task exists
                    task = await task_manager.get_task_status(task_id)
                    if not task:
                        await websocket.send_json({
                            "error": f"Task {task_id} not found",
                            "type": "error"
                        })
                        continue

                    # Send initial task status
                    await websocket.send_json({
                        "type": "task_status",
                        "task_id": task_id,
                        "status": task.status.value,
                        "created_at": task.created_at,
                        "started_at": task.started_at
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
                        logger.error(f"Task monitoring error: {e}")
                        await websocket.send_json({
                            "type": "monitor_error",
                            "task_id": task_id,
                            "error": str(e)
                        })

                elif action == "restart":
                    # Restart specific task
                    task_id = data.get("task_id")
                    if not task_id:
                        await websocket.send_json({
                            "error": "Missing 'task_id' field for restart action",
                            "type": "error"
                        })
                        continue

                    if task_id.startswith("sync_"):
                        await websocket.send_json({
                            "error": "Synchronous tasks cannot be restarted",
                            "type": "error"
                        })
                        continue

                    task_manager = get_global_task_manager()
                    new_task_id = await task_manager.restart_task(task_id)

                    if new_task_id:
                        await websocket.send_json({
                            "type": "restart_result",
                            "original_task_id": task_id,
                            "new_task_id": new_task_id,
                            "success": True,
                            "message": f"Task {task_id} restarted as {new_task_id}"
                        })
                    else:
                        # Check why restart failed
                        task = await task_manager.get_task_status(task_id)
                        if not task:
                            error_msg = f"Task {task_id} not found"
                        else:
                            error_msg = f"Task {task_id} cannot be restarted (status: {task.status.value})"

                        await websocket.send_json({
                            "type": "restart_result",
                            "task_id": task_id,
                            "success": False,
                            "error": error_msg
                        })

                elif action == "cancel":
                    # Cancel specific task
                    task_id = data.get("task_id")
                    if not task_id:
                        await websocket.send_json({
                            "error": "Missing 'task_id' field for cancel action",
                            "type": "error"
                        })
                        continue

                    if task_id.startswith("sync_"):
                        await websocket.send_json({
                            "error": "Synchronous tasks cannot be cancelled",
                            "type": "error"
                        })
                        continue

                    task_manager = get_global_task_manager()
                    success = await task_manager.cancel_task(task_id)

                    await websocket.send_json({
                        "type": "cancel_result",
                        "task_id": task_id,
                        "success": success,
                        "message": f"Task {task_id} {'cancelled' if success else 'could not be cancelled'}"
                    })

                elif action == "stats":
                    # Get task manager statistics
                    task_manager = get_global_task_manager()
                    stats = task_manager.get_stats()

                    await websocket.send_json({
                        "type": "stats",
                        "stats": stats
                    })

                else:
                    await websocket.send_json({
                        "error": f"Unknown action: {action}",
                        "type": "error"
                    })

            except Exception as e:
                logger.error(f"WebSocket task management processing error: {e}")
                await websocket.send_json({
                    "error": str(e),
                    "type": "error"
                })

    except WebSocketDisconnect:
        logger.info("WebSocket task management connection closed")
    except Exception as e:
        logger.error(f"WebSocket task management error: {e}")
        try:
            await websocket.close()
        except:
            pass