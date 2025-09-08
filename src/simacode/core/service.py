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
from ..mcp.loop_safe_client import safe_call_mcp_tool
from .ticmaker_detector import TICMakerDetector

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
            logger.debug("Starting ReAct service on demand")
            await self.react_service.start()
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
            
            # 🎯 TICMaker检测 - 穿透对话检测机制的关键
            is_ticmaker, reason, enhanced_context = TICMakerDetector.detect_ticmaker_request(
                request.message, request.context
            )
            
            if is_ticmaker:
                logger.info(f"🎯 TICMaker请求检测成功: {reason}")
                # 更新请求的context为增强后的context
                request.context = enhanced_context
                # TICMaker请求强制使用ReAct引擎处理（除非显式指定force_mode="chat"）
                if request.force_mode != "chat":
                    logger.info("TICMaker请求将使用ReAct引擎处理")
                    return await self._process_ticmaker_with_react(request, reason)
            
            # 原有的处理逻辑
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
    
    async def _process_ticmaker_with_react(
        self, 
        request: ChatRequest, 
        trigger_reason: str
    ) -> Union[ChatResponse, AsyncGenerator[str, None]]:
        """
        专门处理TICMaker请求的方法
        
        该方法将先调用TICMaker工具进行预处理，然后继续ReAct处理
        确保TICMaker相关的HTML创建和修改功能正确执行
        
        Args:
            request: TICMaker聊天请求
            trigger_reason: 触发TICMaker的原因
            
        Returns:
            ChatResponse或AsyncGenerator
        """
        try:
            logger.info(f"🎯 开始处理TICMaker请求，触发原因: {trigger_reason}")
            
            # 先调用TICMaker工具进行预处理
            await self._call_ticmaker_tool(request, trigger_reason)
            
            # 然后继续使用ReAct引擎处理（让ReAct引擎协调其他可能的工具调用）
            logger.info("TICMaker工具调用完成，继续ReAct引擎处理...")
            return await self._process_with_react_engine(request)
            
        except Exception as e:
            logger.error(f"TICMaker processing failed: {e}")
            # 失败时回退到正常ReAct处理，确保系统稳定性
            logger.info("TICMaker处理失败，回退到正常ReAct处理")
            return await self._process_with_react_engine(request)
    
    async def _call_ticmaker_tool(
        self, 
        request: ChatRequest, 
        trigger_reason: str
    ):
        """
        调用TICMaker工具进行HTML页面处理
        
        Args:
            request: 聊天请求
            trigger_reason: 触发原因
        """
        try:
            # 确保ReAct服务已启动（因为需要使用其工具注册表）
            await self._ensure_react_service_started()
            
            # 确定请求来源
            source = "API" if getattr(request, '_from_api', False) else "CLI"
            if request.context and request.context.get("cli_mode"):
                source = "CLI"
            
            # 确定操作类型
            operation = "modify" if TICMakerDetector.is_modification_request(
                request.message, request.context
            ) else "create"
            
            # 准备工具输入
            tool_input = TICMakerDetector.prepare_ticmaker_tool_input(
                message=request.message,
                context=request.context or {},
                session_id=request.session_id,
                source=source,
                trigger_reason=trigger_reason,
                operation=operation
            )
            
            # 使用事件循环安全的 MCP 工具调用
            logger.info(f"🎯 调用TICMaker工具: operation={operation}, source={source}")
            logger.debug(f"🔧 工具输入参数: {tool_input}")
            
            # 获取当前事件循环信息用于调试
            try:
                current_loop = asyncio.get_running_loop()
                logger.debug(f"🌐 当前事件循环: {current_loop}")
            except RuntimeError:
                logger.debug("🌐 没有运行中的事件循环")
            
            # 使用事件循环安全的调用方式
            result = await safe_call_mcp_tool("ticmaker:create_interactive_course", tool_input)
            
            if result.success:
                logger.info(f"✅ TICMaker工具执行成功: {str(result.content)[:200]}...")
            else:
                logger.error(f"❌ TICMaker工具执行失败: {result.error}")
                # 记录更多调试信息
                logger.debug(f"🔍 失败的工具元数据: {result.metadata}")
            
            return result
            
        except Exception as e:
            logger.error(f"TICMaker工具调用失败: {e}")
            # 工具调用失败不应该阻止后续处理
            raise
    
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
                session_id=request.session_id
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
