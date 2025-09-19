"""
SimaCode Unified Core Service

This module provides the unified service layer that supports both CLI and API modes.
It acts as a facade over the existing ReActService and other components, providing
a consistent interface for both interaction modes.
"""

import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, Union
from pathlib import Path

from ..config import Config
from ..services.react_service import ReActService
from ..session.manager import SessionManager
from ..ai.conversation import ConversationManager
from ..ai.factory import AIClientFactory
from ..tools.base import execute_tool
from ..mcp.async_integration import get_global_task_manager, TaskType

logger = logging.getLogger(__name__)


class ChatRequest:
    """Request model for chat operations."""
    
    def __init__(
        self,
        message: str,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        stream: bool = False,
        force_mode: Optional[str] = None
    ):
        self.message = message
        self.session_id = session_id
        self.context = context or {}
        self.stream = stream
        self.force_mode = force_mode  # "chat" to force conversational mode, "react" to force task mode


class ChatResponse:
    """Response model for chat operations."""
    
    def __init__(
        self,
        content: str,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ):
        self.content = content
        self.session_id = session_id
        self.metadata = metadata or {}
        self.error = error
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert response to dictionary format."""
        result = {
            "content": self.content,
            "session_id": self.session_id,
            "metadata": self.metadata
        }
        if self.error:
            result["error"] = self.error
        return result


class ReActRequest:
    """Request model for ReAct operations."""
    
    def __init__(
        self,
        task: str,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        execution_mode: Optional[str] = None,
        skip_confirmation: bool = False
    ):
        self.task = task
        self.session_id = session_id
        self.context = context or {}
        self.execution_mode = execution_mode
        self.skip_confirmation = skip_confirmation


class ReActResponse:
    """Response model for ReAct operations."""
    
    def __init__(
        self,
        result: str,
        session_id: str,
        steps: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ):
        self.result = result
        self.session_id = session_id
        self.steps = steps or []
        self.metadata = metadata or {}
        self.error = error
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert response to dictionary format."""
        result = {
            "result": self.result,
            "session_id": self.session_id,
            "steps": self.steps,
            "metadata": self.metadata
        }
        if self.error:
            result["error"] = self.error
        return result


class SimaCodeService:
    """
    Unified SimaCode service supporting both CLI and API modes.
    
    This service provides a consistent interface for both terminal AI Agent
    and backend API service modes, ensuring functional consistency across
    different interaction patterns.
    """
    
    def __init__(self, config: Config, api_mode: bool = True):
        """
        Initialize the SimaCode service.
        
        Args:
            config: Application configuration
            api_mode: Whether running in API mode (True) or CLI mode (False)
        """
        self.config = config
        self.api_mode = api_mode
        
        # Initialize core services (reuse existing components)
        # 根据运行模式初始化ReActService
        self.react_service = ReActService(config, api_mode=api_mode)
        
        # Initialize AI client for direct chat operations
        self.ai_client = AIClientFactory.create_client(config.ai.model_dump())
        
        # Initialize conversation manager for chat operations
        sessions_dir = Path.cwd() / ".simacode" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        self.conversation_manager = ConversationManager(sessions_dir)
        
        # Don't start ReAct service in __init__ - will be started in async context
        self._react_service_started = False

        # 异步任务管理
        self.task_manager = get_global_task_manager()

        logger.info("SimaCodeService initialized successfully (async startup pending)")
    
    async def start_async(self):
        """Start the service asynchronously in the current event loop."""
        if self._react_service_started:
            logger.debug("SimaCodeService already started")
            return
            
        try:
            logger.info("Starting SimaCodeService asynchronously...")
            await self.react_service.start()
            self._react_service_started = True
            logger.info("SimaCodeService started successfully")
        except Exception as e:
            logger.error(f"Failed to start SimaCodeService: {e}")
            raise
    
    async def stop_async(self):
        """Stop the service asynchronously."""
        if not self._react_service_started:
            logger.debug("SimaCodeService not started, nothing to stop")
            return
            
        try:
            logger.info("Stopping SimaCodeService...")
            await self.react_service.stop()
            self._react_service_started = False
            logger.info("SimaCodeService stopped successfully")
        except Exception as e:
            logger.error(f"Failed to stop SimaCodeService: {e}")
    
    async def _ensure_react_service_started(self):
        """Ensure ReAct service is started before processing requests."""
        if not self._react_service_started:
            logger.warning("ReAct service not started - this should not happen in API mode")
            await self.start_async()
        else:
            logger.debug("ReAct service already running")
    
    # 🗑️ 已删除 _is_conversational_input 方法
    # 现在统一使用 ReAct 引擎处理所有请求，让 TaskPlanner 内部进行分类
    
    async def process_chat(
        self, 
        request: Union[ChatRequest, str], 
        session_id: Optional[str] = None
    ) -> Union[ChatResponse, AsyncGenerator[str, None]]:
        """
        Enhanced chat processing with TICMaker detection and ReAct capabilities.
        
        This method detects TICMaker requests and routes them appropriately:
        - TICMaker requests: Force ReAct engine with TICMaker tool integration
        - Regular requests: Normal processing flow
        
        Args:
            request: Chat request or message string
            session_id: Optional session ID for CLI compatibility
            
        Returns:
            ChatResponse for regular chat, AsyncGenerator for streaming
        """
        # Handle both ChatRequest objects and simple strings (CLI compatibility)
        if isinstance(request, str):
            request = ChatRequest(
                message=request,
                session_id=session_id,
                stream=False
            )
        
        try:
            logger.info(f"Processing chat message for session: {request.session_id}")
            
            # Use session_id or generate new one
            if not request.session_id:
                import uuid
                request.session_id = str(uuid.uuid4())
            
            # 统一使用ReAct引擎处理所有请求（除非显式指定force_mode="chat"）
            
            if request.force_mode == "chat":
                # 强制纯对话模式：使用传统 chat 处理
                logger.debug("Force chat mode enabled - using traditional conversational processing")
                return await self._process_conversational_chat(request)
            else:
                # 默认使用 ReAct 引擎处理（包括对话和任务）
                # ReAct 引擎内部会通过 TaskPlanner 智能判断输入类型
                logger.debug(f"Processing with ReAct engine: {request.message[:50]}...")
                return await self._process_with_react_engine(request)
                
        except Exception as e:
            logger.error(f"Error processing chat: {str(e)}")
            return ChatResponse(
                content="抱歉，处理您的请求时出现了问题。",
                session_id=request.session_id or "unknown",
                error=str(e)
            )
    
    async def _process_conversational_chat(self, request: ChatRequest) -> Union[ChatResponse, AsyncGenerator[str, None]]:
        """处理对话性输入（使用传统chat逻辑）"""
        try:
            # Get or create current conversation
            conversation = self.conversation_manager.get_current_conversation()
            
            # Add message to conversation history
            conversation.add_user_message(request.message)
            
            if request.stream:
                # Return async generator for streaming
                return self._stream_conversational_response(request, conversation)
            else:
                # Regular chat response
                ai_response = await self.ai_client.chat(conversation.get_messages())
                
                # Add AI response to conversation history
                conversation.add_assistant_message(ai_response.content)
                
                # Save conversation
                self.conversation_manager._save_conversation(conversation)
                
                return ChatResponse(
                    content=ai_response.content,
                    session_id=request.session_id,
                    metadata={
                        "mode": "conversational", 
                        "input_type": "chat",
                        "processing_engine": "ai_client"
                    }
                )
                
        except Exception as e:
            logger.error(f"Error processing conversational chat: {str(e)}")
            return ChatResponse(
                content="抱歉，处理您的消息时出现了问题。",
                session_id=request.session_id or "unknown",
                error=str(e)
            )
    
    async def _process_with_react_engine(self, request: ChatRequest) -> Union[ChatResponse, AsyncGenerator[str, None]]:
        """使用ReAct引擎处理请求（完全复用 chat --react 模式的逻辑）"""
        try:
            # 确保ReAct服务已启动
            await self._ensure_react_service_started()
            
            # 🔄 完全复用 chat --react 模式的逻辑
            # 创建 ReActRequest（与 CLI 中 chat --react 模式完全相同）
            react_request = ReActRequest(
                task=request.message,
                session_id=request.session_id,
                context=request.context
            )
            
            if request.stream:
                # 流式处理 - 复用现有的流式逻辑
                return self._stream_task_response(react_request)
            else:
                # 非流式处理 - 复用 process_react 逻辑
                react_response = await self.process_react(react_request)
                
                return ChatResponse(
                    content=react_response.result,
                    session_id=react_response.session_id,
                    metadata={
                        "mode": "react_engine", 
                        "processing_engine": "react",
                        "steps": react_response.steps,
                        "tools_used": self._extract_tools_from_steps(react_response.steps)
                    }
                )
                
        except Exception as e:
            logger.error(f"Error processing with ReAct engine: {str(e)}")
            return ChatResponse(
                content="抱歉，处理您的请求时出现了问题。",
                session_id=request.session_id or "unknown",
                error=str(e)
            )
    
    def _extract_tools_from_steps(self, steps: List[Dict[str, Any]]) -> List[str]:
        """从执行步骤中提取使用的工具列表"""
        tools = set()
        for step in steps:
            if step.get("type") == "tool_execution" and "tool" in step:
                tools.add(step["tool"])
        return list(tools)
    
    async def _stream_conversational_response(
        self, 
        request: ChatRequest, 
        conversation
    ) -> AsyncGenerator[str, None]:
        """生成对话性流式响应"""
        try:
            response_chunks = []
            async for chunk in self.ai_client.chat_stream(conversation.get_messages()):
                response_chunks.append(chunk)
                yield chunk
            
            # After streaming, add complete response to conversation
            complete_response = "".join(response_chunks)
            conversation.add_assistant_message(complete_response)
            self.conversation_manager._save_conversation(conversation)
            
        except Exception as e:
            logger.error(f"Error in conversational streaming: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def _stream_task_response(self, react_request: ReActRequest) -> AsyncGenerator[str, None]:
        """生成任务性流式响应"""
        try:
            async for update in await self.process_react(react_request, stream=True):
                # 将 ReAct 更新转换为 Chat 流式格式
                update_type = update.get("type", "")
                content = update.get("content", "")
                
                if update_type == "conversational_response":
                    yield content
                #elif update_type == "final_result":
                #    yield f"[status_update] {content}"
                #elif update_type == "sub_task_result":
                #    yield content
                elif update_type == "confirmation_request":
                    # 🆕 保持确认请求的完整结构信息，但扁平化以匹配客户端期望
                    import json
                    
                    # 从嵌套结构中提取数据并创建扁平化结构
                    confirmation_request = update.get("confirmation_request", {})
                    tasks_summary = update.get("tasks_summary", {})
                    
                    logger.debug(f"[CONFIRM_DEBUG] Service processing confirmation_request update")
                    logger.debug(f"[CONFIRM_DEBUG] confirmation_request: {confirmation_request}")
                    logger.debug(f"[CONFIRM_DEBUG] tasks_summary: {tasks_summary}")
                    
                    confirmation_data = {
                        "type": "confirmation_request",
                        "content": content,
                        "session_id": update.get("session_id"),
                        # 扁平化：直接提供 tasks 和其他字段，匹配客户端期望
                        "tasks": confirmation_request.get("tasks", []),
                        "timeout_seconds": confirmation_request.get("timeout_seconds", 300),
                        "confirmation_round": update.get("confirmation_round", 1),
                        "risk_level": tasks_summary.get("risk_level", "unknown"),
                        # 保留原始结构供其他用途
                        "confirmation_request": confirmation_request,
                        "tasks_summary": tasks_summary
                    }
                    logger.debug(f"[CONFIRM_DEBUG] Final confirmation_data tasks count: {len(confirmation_data.get('tasks', []))}")
                    yield f"[confirmation_request]{json.dumps(confirmation_data)}"
                elif update_type == "task_init":
                    # 🆕 Handle task_init message type
                    yield f"[task_init] {content}"
                elif update_type == "confirmation_skipped":
                    # 🆕 Handle confirmation_skipped message type
                    yield f"[confirmation_skipped] {content}"
                elif update_type in ["tool_execution", "status_update"]:
                    # 为工具执行和状态更新添加前缀标识
                    yield f"[{update_type}] {content}"
                elif update_type == "error":
                    yield f"❌ {content}"
                # 过滤掉其他内部类型的更新
                
        except Exception as e:
            logger.error(f"Error in task streaming: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def _stream_chat_response(
        self, 
        request: ChatRequest, 
        conversation
    ) -> AsyncGenerator[str, None]:
        """Generate streaming chat response."""
        try:
            response_chunks = []
            async for chunk in self.ai_client.chat_stream(conversation.get_messages()):
                response_chunks.append(chunk)
                yield chunk
            
            # After streaming, add complete response to conversation
            complete_response = "".join(response_chunks)
            conversation.add_assistant_message(complete_response)
            self.conversation_manager._save_conversation(conversation)
            
        except Exception as e:
            logger.error(f"Error in streaming chat: {str(e)}")
            yield f"Error: {str(e)}"
    
    async def _stream_react_response(self, request: ReActRequest) -> AsyncGenerator[Dict[str, Any], None]:
        """Generate streaming ReAct response."""
        try:
            await self._ensure_react_service_started()
            
            async for result in self.react_service.process_user_request(
                request.task,
                session_id=request.session_id,  # Pass through session_id for continuity
                context=request.context,
                skip_confirmation=request.skip_confirmation  # Pass through skip_confirmation
            ):
                # Pass through the result with session info
                if isinstance(result, dict):
                    result["original_session_id"] = request.session_id
                    yield result
                else:
                    yield {
                        "type": result.type.value if hasattr(result, 'type') else "result",
                        "content": str(result),
                        "timestamp": result.timestamp if hasattr(result, 'timestamp') else None,
                        "original_session_id": request.session_id
                    }
                    
        except Exception as e:
            logger.error(f"Error in streaming ReAct: {str(e)}")
            yield {
                "type": "error",
                "content": f"Error: {str(e)}",
                "original_session_id": request.session_id
            }
    
    async def process_react(
        self,
        request: Union[ReActRequest, str],
        session_id: Optional[str] = None,
        stream: bool = False
    ) -> Union[ReActResponse, AsyncGenerator[Dict[str, Any], None]]:
        """
        增强的 ReAct 任务处理，支持异步任务检测和处理。

        Args:
            request: ReAct request or task string
            session_id: Optional session ID for CLI compatibility
            stream: If True, return AsyncGenerator for real-time updates

        Returns:
            ReActResponse with execution results, or AsyncGenerator for streaming
        """
        # Handle both ReActRequest objects and simple strings (CLI compatibility)
        if isinstance(request, str):
            request = ReActRequest(
                task=request,
                session_id=session_id
            )

        try:
            logger.info(f"Processing ReAct task for session: {request.session_id}")

            # Ensure ReAct service is started
            await self._ensure_react_service_started()

            # Use session_id or generate new one
            if not request.session_id:
                import uuid
                request.session_id = str(uuid.uuid4())

            # 检测是否为长时间运行任务
            if await self._requires_async_execution(request):
                return await self._process_react_async(request, stream)
            else:
                return await self._process_react_sync(request, stream)

        except Exception as e:
            logger.error(f"Error processing ReAct task: {str(e)}")
            return ReActResponse(
                result="",
                session_id=request.session_id or "unknown",
                error=str(e)
            )

    async def _requires_async_execution(self, request: ReActRequest) -> bool:
        """
        检测是否需要异步执行。

        Args:
            request: ReAct 请求

        Returns:
            bool: 是否需要异步执行
        """
        task_lower = request.task.lower()

        # 长时间运行任务的关键词
        long_running_indicators = [
            "analyze large", "process big", "download", "upload", "backup",
            "bulk", "batch", "mass", "crawl", "scrape", "generate report",
            "train model", "build", "compile", "migrate", "import data",
            "export data", "convert large", "archive", "extract large"
        ]

        # 检查任务描述
        if any(indicator in task_lower for indicator in long_running_indicators):
            return True

        # 检查任务长度（复杂任务通常描述较长）
        if len(request.task) > 200:
            return True

        # 检查上下文中的异步指示器
        if request.context:
            context_str = str(request.context).lower()
            if any(indicator in context_str for indicator in ["async", "background", "long"]):
                return True

        return False

    async def _requires_async_chat_processing(self, request: ChatRequest) -> bool:
        """
        检测聊天消息是否需要异步处理。

        Args:
            request: 聊天请求

        Returns:
            bool: 是否需要异步处理
        """
        message_lower = request.message.lower()

        # ReAct 模式触发词
        react_triggers = [
            "help me", "can you", "please", "create", "build", "generate",
            "analyze", "process", "download", "upload", "backup", "migrate",
            "convert", "extract", "compile", "train", "optimize"
        ]

        # 长时间运行任务的关键词
        long_running_indicators = [
            "large file", "big data", "multiple files", "batch process",
            "bulk operation", "mass", "crawl", "scrape", "backup",
            "analyze codebase", "process repository", "generate report"
        ]

        # 检查是否触发 ReAct 模式
        if any(trigger in message_lower for trigger in react_triggers):
            return True

        # 检查长时间运行指示器
        if any(indicator in message_lower for indicator in long_running_indicators):
            return True

        # 检查消息长度（复杂请求通常较长）
        if len(request.message) > 300:
            return True

        # 检查上下文中的异步指示器
        if request.context:
            context_str = str(request.context).lower()
            if any(indicator in context_str for indicator in ["async", "background", "react"]):
                return True

        return False

    async def _process_react_async(self, request: ReActRequest, stream: bool) -> ReActResponse:
        """
        异步 ReAct 处理。

        Args:
            request: ReAct 请求
            stream: 是否流式处理

        Returns:
            ReActResponse: 响应结果
        """
        # 创建异步任务
        task_id = await self.task_manager.submit_task(
            TaskType.REACT,
            request,
            progress_callback=self._handle_react_progress
        )

        # 在 CLI 模式下，等待任务完成并显示进度
        if self._is_cli_mode():
            logger.info(f"Executing ReAct task in async mode (CLI): {task_id}")

            final_result = None
            steps = []

            async for progress in self.task_manager.get_task_progress_stream(task_id):
                progress_type = progress.get('type', 'progress')

                if progress_type == 'progress':
                    logger.info(f"Progress: {progress.get('message', 'Processing...')}")

                elif progress_type == 'final_result':
                    final_result = progress.get('result')
                    steps = progress.get('steps', [])
                    break

                elif progress_type == 'error':
                    error_msg = progress.get('error', 'Unknown error')
                    logger.error(f"Async task failed: {error_msg}")
                    return ReActResponse(
                        result="",
                        session_id=request.session_id,
                        error=error_msg,
                        metadata={"async_task_id": task_id, "execution_mode": "async"}
                    )

            return ReActResponse(
                result=final_result or "Task completed",
                session_id=request.session_id,
                steps=steps,
                metadata={"async_task_id": task_id, "execution_mode": "async"}
            )

        else:
            # API 模式返回任务 ID，让客户端轮询或使用 WebSocket
            return ReActResponse(
                result=f"Task submitted for background execution: {task_id}",
                session_id=request.session_id,
                metadata={
                    "async_task_id": task_id,
                    "execution_mode": "async",
                    "task_type": "long_running"
                }
            )

    async def _process_react_sync(self, request: ReActRequest, stream: bool) -> Union[ReActResponse, AsyncGenerator[Dict[str, Any], None]]:
        """
        同步 ReAct 处理（原有逻辑）。

        Args:
            request: ReAct 请求
            stream: 是否流式处理

        Returns:
            ReActResponse 或 AsyncGenerator
        """
        if stream:
            # Return streaming generator directly
            return self._stream_react_response(request)
        else:
            # Execute ReAct task and collect results
            execution_results = []
            async for result in self.react_service.process_user_request(
                request.task,
                session_id=request.session_id,  # Pass through session_id for continuity
                context=request.context,
                skip_confirmation=request.skip_confirmation  # Pass through skip_confirmation
            ):
                # Handle different result formats from ReActService
                if isinstance(result, dict):
                    execution_results.append(result)
                else:
                    execution_results.append({
                        "type": result.type.value if hasattr(result, 'type') else "result",
                        "content": str(result),
                        "timestamp": result.timestamp if hasattr(result, 'timestamp') else None
                    })

            # Format final result
            if execution_results:
                final_result = execution_results[-1].get("content", "Task completed")
            else:
                final_result = "Task completed"

        return ReActResponse(
            result=final_result,
            session_id=request.session_id,
            steps=execution_results,
            metadata={"mode": "react", "execution_mode": "sync"}
        )

    async def _handle_react_progress(self, progress_data: Dict[str, Any]):
        """处理 ReAct 任务进度回调"""
        logger.debug(f"ReAct task progress: {progress_data}")
        # 这里可以添加更多的进度处理逻辑

    def _is_cli_mode(self) -> bool:
        """检查是否为 CLI 模式"""
        return not self.api_mode

    async def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取异步任务状态。

        Args:
            task_id: 任务ID

        Returns:
            Optional[Dict[str, Any]]: 任务状态信息
        """
        task = await self.task_manager.get_task_status(task_id)
        if not task:
            return None

        return {
            "task_id": task.task_id,
            "task_type": task.task_type.value,
            "status": task.status.value,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "error": task.error,
            "metadata": task.metadata
        }

    async def get_task_progress_stream(self, task_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        """
        获取任务进度流。

        Args:
            task_id: 任务ID

        Yields:
            Dict[str, Any]: 进度数据
        """
        async for progress in self.task_manager.get_task_progress_stream(task_id):
            yield progress

    async def cancel_task(self, task_id: str) -> bool:
        """
        取消异步任务。

        Args:
            task_id: 任务ID

        Returns:
            bool: 是否成功取消
        """
        return await self.task_manager.cancel_task(task_id)

    def get_task_manager_stats(self) -> Dict[str, Any]:
        """获取任务管理器统计信息"""
        return self.task_manager.get_stats()
    
    async def get_session_info(self, session_id: str) -> Dict[str, Any]:
        """
        Get session information.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Session information dictionary
        """
        try:
            session_info = await self.react_service.get_session_info(session_id)
            if session_info:
                return {
                    "session_id": session_id,
                    "created_at": session_info.get("created_at"),
                    "message_count": len(session_info.get("metadata", {}).get("conversation_history", [])),
                    "status": session_info.get("state", "active"),
                    "tasks": session_info.get("tasks", []),
                    "updated_at": session_info.get("updated_at"),
                    "evaluations": session_info.get("evaluations", {}),
                    "task_results": session_info.get("task_results", {})
                }
            else:
                return {"error": "Session not found"}
        except Exception as e:
            logger.error(f"Error getting session info: {str(e)}")
            return {"error": str(e)}
    
    async def list_sessions(self) -> List[Dict[str, Any]]:
        """
        List all active sessions.
        
        Returns:
            List of session information dictionaries
        """
        try:
            sessions = await self.react_service.list_sessions()
            return sessions
        except Exception as e:
            logger.error(f"Error listing sessions: {str(e)}")
            return []
    
    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            True if successful, False otherwise
        """
        try:
            return await self.react_service.delete_session(session_id)
        except Exception as e:
            logger.error(f"Error deleting session: {str(e)}")
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on the service and its components.
        
        Returns:
            Health status information
        """
        try:
            health_status = {
                "status": "healthy",
                "components": {
                    "react_service": "healthy",
                    "ai_client": "healthy",
                    "conversation_manager": "healthy"
                },
                "version": "1.0.0",  # This should come from package info
                "config": {
                    "ai_provider": self.config.ai.provider,
                    "ai_model": self.config.ai.model
                }
            }
            
            # Test AI client connectivity
            try:
                from ..ai.base import Message, Role
                test_messages = [Message(role=Role.USER, content="Health check test")]
                await self.ai_client.chat(test_messages)
                health_status["components"]["ai_client"] = "healthy"
            except Exception as e:
                health_status["components"]["ai_client"] = f"unhealthy: {str(e)}"
                health_status["status"] = "degraded"
            
            return health_status
            
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return {
                "status": "unhealthy",
                "error": str(e)
            }
    
    async def submit_confirmation(self, response) -> bool:
        """提交用户确认响应的便捷方法"""
        try:
            logger.debug(f"[CONFIRM_DEBUG] SimaCodeService.submit_confirmation called")
            logger.debug(f"[CONFIRM_DEBUG] Response: {response}, API mode: {self.api_mode}")
            
            if hasattr(self.react_service, 'react_engine') and self.react_service.react_engine:
                # 在CLI模式下，确认是同步处理的，不需要通过ConfirmationManager
                if not self.api_mode:
                    logger.info("CLI mode: confirmation handled synchronously")
                    return True
                else:
                    # API模式下才使用ConfirmationManager
                    logger.info("API mode: confirmation handled synchronously")
                    result = await self.react_service.react_engine.submit_confirmation(response)
                    logger.debug(f"[CONFIRM_DEBUG] Engine submit_confirmation result: {result}")
                    return result
            else:
                logger.warning("ReAct engine not available for confirmation submission")
                return False
        except Exception as e:
            logger.error(f"Error submitting confirmation: {e}")
            return False
