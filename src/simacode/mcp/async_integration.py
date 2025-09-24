"""
MCP 异步任务集成模块。

提供统一的异步任务管理器，支持长时间运行任务的执行、进度跟踪和结果回传。
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Dict, Any, Optional, Callable, AsyncGenerator, Union
from enum import Enum

# Avoid circular imports - use TYPE_CHECKING for type hints
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.service import ChatRequest, ReActRequest

logger = logging.getLogger(__name__)


class TaskType(Enum):
    """任务类型枚举"""
    REACT = "react"
    CHAT = "chat"


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class MCPAsyncTask:
    """异步任务数据结构"""
    task_id: str
    task_type: TaskType
    request: Union[Any, Dict[str, Any]]  # ReActRequest, ChatRequest, or Dict
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    progress_callback: Optional[Callable] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
        if self.metadata is None:
            self.metadata = {}


class MCPAsyncTaskManager:
    """统一的异步任务管理器"""

    def __init__(self, max_concurrent_tasks: int = 5):
        """
        初始化异步任务管理器。

        Args:
            max_concurrent_tasks: 最大并发任务数
        """
        self.active_tasks: Dict[str, MCPAsyncTask] = {}
        self.task_queues: Dict[str, asyncio.Queue] = {}
        self.executor_pool = asyncio.Semaphore(max_concurrent_tasks)
        self._shutdown = False

        logger.info(f"MCPAsyncTaskManager initialized with max_concurrent_tasks={max_concurrent_tasks}")

    async def submit_task(
        self,
        task_type: TaskType,
        request: Union[Any, Dict[str, Any]],  # ReActRequest, ChatRequest, or Dict
        progress_callback: Optional[Callable] = None
    ) -> str:
        """
        提交异步任务。

        Args:
            task_type: 任务类型
            request: 任务请求数据
            progress_callback: 进度回调函数

        Returns:
            str: 任务ID
        """
        if self._shutdown:
            raise RuntimeError("Task manager is shutting down")

        task_id = f"{task_type.value}_{uuid.uuid4().hex[:8]}"

        task = MCPAsyncTask(
            task_id=task_id,
            task_type=task_type,
            request=request,
            progress_callback=progress_callback
        )

        self.active_tasks[task_id] = task
        self.task_queues[task_id] = asyncio.Queue()

        # 启动后台执行
        asyncio.create_task(self._execute_task(task))

        logger.info(f"Task {task_id} submitted for async execution")
        return task_id

    async def get_task_status(self, task_id: str) -> Optional[MCPAsyncTask]:
        """获取任务状态"""
        return self.active_tasks.get(task_id)

    async def get_task_progress_stream(self, task_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        获取任务进度流。

        Args:
            task_id: 任务ID

        Yields:
            Dict[str, Any]: 进度数据
        """
        if task_id not in self.task_queues:
            raise ValueError(f"Task {task_id} not found")

        queue = self.task_queues[task_id]
        task = self.active_tasks.get(task_id)

        if not task:
            return

        while True:
            try:
                # 等待进度更新，使用短超时以便定期检查任务状态
                progress = await asyncio.wait_for(queue.get(), timeout=1.0)
                yield progress

                # 如果是最终结果，停止流式传输
                if progress.get('type') == 'final_result':
                    break

            except asyncio.TimeoutError:
                # 检查任务是否仍在运行
                current_task = self.active_tasks.get(task_id)
                if not current_task or current_task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
                    break
                continue

    async def restart_task(self, task_id: str) -> Optional[str]:
        """
        重启失败或取消的任务。

        Args:
            task_id: 任务ID

        Returns:
            str: 新任务ID，如果无法重启则返回None
        """
        task = self.active_tasks.get(task_id)
        if not task:
            return None

        # 只能重启失败或取消的任务
        if task.status not in [TaskStatus.FAILED, TaskStatus.CANCELLED]:
            return None

        # 创建新任务（复制原任务配置）
        new_task_id = await self.submit_task(
            task_type=task.task_type,
            request=task.request,
            progress_callback=task.progress_callback
        )

        logger.info(f"Task {task_id} restarted as {new_task_id}")
        return new_task_id

    async def cancel_task(self, task_id: str) -> bool:
        """
        取消任务。

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否成功取消
        """
        task = self.active_tasks.get(task_id)
        if not task:
            return False

        if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            return False

        task.status = TaskStatus.CANCELLED

        # 发送取消通知
        await self._report_progress(task_id, {
            "type": "cancelled",
            "message": "Task was cancelled",
            "timestamp": time.time()
        })

        logger.info(f"Task {task_id} cancelled")
        return True

    async def _execute_task(self, task: MCPAsyncTask):
        """执行异步任务"""
        async with self.executor_pool:
            try:
                task.status = TaskStatus.RUNNING
                task.started_at = time.time()

                # 报告开始
                await self._report_progress(task.task_id, {
                    "type": "started",
                    "message": f"Starting {task.task_type.value} task",
                    "timestamp": task.started_at
                })

                # 根据任务类型执行
                if task.task_type == TaskType.REACT:
                    await self._execute_react_task(task)
                elif task.task_type == TaskType.CHAT:
                    await self._execute_chat_task(task)
                else:
                    raise ValueError(f"Unknown task type: {task.task_type}")

                # 如果任务没有被取消，标记为完成
                if task.status != TaskStatus.CANCELLED:
                    task.status = TaskStatus.COMPLETED
                    task.completed_at = time.time()

                    await self._report_progress(task.task_id, {
                        "type": "final_result",
                        "result": task.result,
                        "timestamp": task.completed_at,
                        "execution_time": task.completed_at - task.started_at
                    })

            except Exception as e:
                task.status = TaskStatus.FAILED
                task.completed_at = time.time()
                task.error = str(e)

                logger.error(f"Task {task.task_id} failed: {e}")

                await self._report_progress(task.task_id, {
                    "type": "error",
                    "error": str(e),
                    "timestamp": task.completed_at
                })

            finally:
                # 清理资源（延迟清理以允许客户端获取最终状态）
                asyncio.create_task(self._cleanup_task(task.task_id, delay=300))  # 5分钟后清理

    async def _execute_react_task(self, task: MCPAsyncTask):
        """执行 ReAct 异步任务"""
        request = task.request

        # 模拟 ReAct 任务执行过程
        # TODO: 这里需要与实际的 ReAct 引擎集成

        # 模拟多阶段执行
        stages = ["Planning", "Tool Selection", "Execution", "Evaluation"]

        for i, stage in enumerate(stages):
            # 检查是否被取消
            if task.status == TaskStatus.CANCELLED:
                return

            await asyncio.sleep(1)  # 模拟处理时间

            progress = (i + 1) / len(stages) * 100
            await self._report_progress(task.task_id, {
                "type": "progress",
                "stage": stage,
                "progress": progress,
                "message": f"Processing {stage}...",
                "timestamp": time.time()
            })

        # 设置模拟结果
        task.result = {
            "task": getattr(request, 'task', 'Unknown task'),
            "status": "completed",
            "steps": len(stages),
            "session_id": getattr(request, 'session_id', None)
        }

    async def _execute_chat_task(self, task: MCPAsyncTask):
        """执行聊天异步任务"""
        request = task.request

        # 模拟聊天处理
        # TODO: 这里需要与实际的聊天引擎集成

        await asyncio.sleep(2)  # 模拟处理时间

        await self._report_progress(task.task_id, {
            "type": "progress",
            "progress": 50,
            "message": "Processing chat message...",
            "timestamp": time.time()
        })

        await asyncio.sleep(2)  # 模拟更多处理

        # 设置模拟结果
        task.result = {
            "content": f"Response to: {getattr(request, 'message', 'Unknown message')}",
            "session_id": getattr(request, 'session_id', None)
        }


    async def _report_progress(self, task_id: str, progress_data: Dict[str, Any]):
        """报告任务进度"""
        if task_id in self.task_queues:
            try:
                await self.task_queues[task_id].put(progress_data)
            except Exception as e:
                logger.error(f"Failed to report progress for task {task_id}: {e}")

        # 调用任务的进度回调
        task = self.active_tasks.get(task_id)
        if task and task.progress_callback:
            try:
                await task.progress_callback(progress_data)
            except Exception as e:
                logger.warning(f"Progress callback error for task {task_id}: {e}")

    async def _cleanup_task(self, task_id: str, delay: float = 0):
        """清理任务资源"""
        if delay > 0:
            await asyncio.sleep(delay)

        self.active_tasks.pop(task_id, None)
        self.task_queues.pop(task_id, None)

        logger.debug(f"Task {task_id} resources cleaned up")

    async def shutdown(self):
        """关闭任务管理器"""
        self._shutdown = True

        # 取消所有活动任务
        for task_id in list(self.active_tasks.keys()):
            await self.cancel_task(task_id)

        # 等待所有任务完成
        while self.active_tasks:
            await asyncio.sleep(0.1)

        logger.info("MCPAsyncTaskManager shutdown completed")

    def get_stats(self) -> Dict[str, Any]:
        """获取任务管理器统计信息"""
        stats = {
            "active_tasks": len(self.active_tasks),
            "task_breakdown": {}
        }

        for task in self.active_tasks.values():
            status = task.status.value
            if status not in stats["task_breakdown"]:
                stats["task_breakdown"][status] = 0
            stats["task_breakdown"][status] += 1

        return stats


# 全局任务管理器实例
_global_task_manager: Optional[MCPAsyncTaskManager] = None


def get_global_task_manager() -> MCPAsyncTaskManager:
    """获取全局任务管理器实例"""
    global _global_task_manager
    if _global_task_manager is None:
        _global_task_manager = MCPAsyncTaskManager()
    return _global_task_manager


async def shutdown_global_task_manager():
    """关闭全局任务管理器"""
    global _global_task_manager
    if _global_task_manager:
        await _global_task_manager.shutdown()
        _global_task_manager = None