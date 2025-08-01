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

logger = logging.getLogger(__name__)


class ChatRequest:
    """Request model for chat operations."""
    
    def __init__(
        self,
        message: str,
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        stream: bool = False
    ):
        self.message = message
        self.session_id = session_id
        self.context = context or {}
        self.stream = stream


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
        execution_mode: Optional[str] = None
    ):
        self.task = task
        self.session_id = session_id
        self.context = context or {}
        self.execution_mode = execution_mode


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
    
    def __init__(self, config: Config):
        """
        Initialize the SimaCode service.
        
        Args:
            config: Application configuration
        """
        self.config = config
        
        # Initialize core services (reuse existing components)
        self.react_service = ReActService(config)
        
        # Initialize AI client for direct chat operations
        self.ai_client = AIClientFactory.create_client(config.ai.model_dump())
        
        # Initialize conversation manager for chat operations
        sessions_dir = Path.home() / ".simacode" / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        self.conversation_manager = ConversationManager(sessions_dir)
        
        # Start ReAct service asynchronously
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If we're in an event loop, schedule the start for later
                asyncio.create_task(self._start_react_service())
            else:
                # If no event loop is running, run synchronously
                asyncio.run(self.react_service.start())
        except Exception as e:
            logger.warning(f"Could not start ReAct service during initialization: {e}")
            logger.info("ReAct service will be started lazily on first use")
        
        logger.info("SimaCodeService initialized successfully")
    
    async def _start_react_service(self):
        """Start the ReAct service asynchronously."""
        try:
            await self.react_service.start()
            logger.info("ReAct service started successfully")
        except Exception as e:
            logger.error(f"Failed to start ReAct service: {e}")
    
    async def _ensure_react_service_started(self):
        """Ensure ReAct service is started before processing requests."""
        if not self.react_service.is_running:
            await self.react_service.start()
    
    async def _is_conversational_input(self, user_input: str) -> bool:
        """
        判断输入是否为对话性输入，复用ReAct引擎的预判断逻辑。
        
        Args:
            user_input: 用户输入文本
            
        Returns:
            bool: True if input is conversational, False if it requires task execution
        """
        try:
            # 确保ReAct服务已启动
            await self._ensure_react_service_started()
            
            # 复用ReAct引擎的输入预判断逻辑
            return await self.react_service.react_engine._is_conversational_input(user_input)
            
        except Exception as e:
            logger.warning(f"Failed to classify input with ReAct: {str(e)}, defaulting to task mode")
            return False  # 默认为任务模式，避免遗漏
    
    async def process_chat(
        self, 
        request: Union[ChatRequest, str], 
        session_id: Optional[str] = None
    ) -> Union[ChatResponse, AsyncGenerator[str, None]]:
        """
        Enhanced chat processing with ReAct capabilities.
        
        This method now automatically detects if the input requires task execution
        and routes it appropriately:
        - Conversational inputs: Traditional chat processing
        - Task inputs: ReAct engine processing with tool execution
        
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
            logger.info(f"Processing enhanced chat message for session: {request.session_id}")
            
            # Use session_id or generate new one
            if not request.session_id:
                import uuid
                request.session_id = str(uuid.uuid4())
            
            # 🆕 智能输入预判断
            # 检查是否强制指定模式
            if hasattr(request, 'force_mode') and request.force_mode:
                if request.force_mode == "chat":
                    is_conversational = True
                elif request.force_mode == "react":
                    is_conversational = False
                else:
                    # 默认智能判断
                    is_conversational = await self._is_conversational_input(request.message)
            else:
                is_conversational = await self._is_conversational_input(request.message)
            
            if is_conversational:
                # 对话性输入：使用传统 chat 处理
                logger.debug(f"Processing as conversational input: {request.message[:50]}...")
                return await self._process_conversational_chat(request)
            else:
                # 任务性输入：使用 ReAct 引擎处理
                logger.debug(f"Processing as task input: {request.message[:50]}...")
                return await self._process_task_chat(request)
                
        except Exception as e:
            logger.error(f"Error processing enhanced chat: {str(e)}")
            return ChatResponse(
                content="",
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
    
    async def _process_task_chat(self, request: ChatRequest) -> Union[ChatResponse, AsyncGenerator[str, None]]:
        """处理任务性输入（使用ReAct引擎）"""
        try:
            # 确保ReAct服务已启动
            await self._ensure_react_service_started()
            
            # 将 ChatRequest 转换为 ReActRequest
            react_request = ReActRequest(
                task=request.message,
                session_id=request.session_id,
                context=request.context
            )
            
            if request.stream:
                # 流式任务处理
                return self._stream_task_response(react_request)
            else:
                # 常规任务处理
                react_response = await self.process_react(react_request)
                
                return ChatResponse(
                    content=react_response.result,
                    session_id=react_response.session_id,
                    metadata={
                        "mode": "task_execution", 
                        "input_type": "task",
                        "processing_engine": "react",
                        "steps": react_response.steps,
                        "tools_used": self._extract_tools_from_steps(react_response.steps)
                    }
                )
                
        except Exception as e:
            logger.error(f"Error processing task chat: {str(e)}")
            return ChatResponse(
                content="抱歉，执行您的任务时出现了问题。",
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
                elif update_type == "final_result":
                    yield content
                elif update_type == "task_result":
                    yield content
                elif update_type == "task_init":
                    # 🆕 Handle task_init message type
                    yield f"[task_init] {content}"
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
                session_id=None,  # Let ReActService create new session
                context=request.context
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
        Process ReAct task execution.
        
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
            
            if stream:
                # Return streaming generator directly
                return self._stream_react_response(request)
            else:
                # Execute ReAct task and collect results
                execution_results = []
                async for result in self.react_service.process_user_request(
                    request.task,
                    session_id=None,  # Let ReActService create new session
                    context=request.context
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
                metadata={"mode": "react", "execution_mode": request.execution_mode}
            )
            
        except Exception as e:
            logger.error(f"Error processing ReAct task: {str(e)}")
            return ReActResponse(
                result="",
                session_id=request.session_id or "unknown",
                error=str(e)
            )
    
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
                    "status": session_info.get("state", "active")
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