"""
ReAct Service Integration

This module provides a high-level service interface that integrates the
ReAct engine with session management, configuration, and other system
components to provide a complete ReAct-based assistant service.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from ..ai.factory import AIClientFactory
from ..config import Config
from ..react.engine import ReActEngine, ExecutionMode
from ..session.manager import SessionManager, SessionConfig
from ..react.engine import ReActSession
from ..react.exceptions import ReActError
from ..react.mcp_integration import setup_mcp_integration_for_react, MCPReActIntegration

logger = logging.getLogger(__name__)


class ReActService:
    """
    High-level ReAct service that integrates all components.
    
    The ReActService provides a unified interface for:
    - Processing user requests through the ReAct engine
    - Managing sessions and persistence
    - Handling configuration and AI client management
    - Providing service-level error handling and logging
    """
    
    def __init__(self, config: Config, api_mode: bool = False):
        """
        Initialize the ReAct service.
        
        Args:
            config: Application configuration
            api_mode: Whether running in API mode
        """
        self.config = config
        self.api_mode = api_mode
        
        # Initialize AI client
        self.ai_client = AIClientFactory.create_client(config.ai.model_dump())
        
        # Initialize ReAct engine
        execution_mode = ExecutionMode.ADAPTIVE  # Default to adaptive mode
        logger.info(f"Initializing ReAct engine with api_mode={self.api_mode}")
        self.react_engine = ReActEngine(self.ai_client, execution_mode, config, self.api_mode)
        
        # Initialize session manager
        sessions_dir = Path.cwd() / ".simacode" / "sessions"
        session_config = SessionConfig(
            sessions_directory=sessions_dir,
            auto_save_interval=30,
            max_session_age=7,
            max_sessions_to_keep=100
        )
        self.session_manager = SessionManager(session_config)
        
        # Service state
        self.is_running = False
        
        # MCP integration
        self.mcp_integration: Optional[MCPReActIntegration] = None
        
        logger.info("ReAct service initialized")
    
    async def start(self):
        """Start the ReAct service."""
        if self.is_running:
            return
        
        try:
            # Start session manager auto-save
            await self.session_manager.start_auto_save()
            
            # Cleanup old sessions
            cleanup_count = await self.session_manager.cleanup_old_sessions()
            if cleanup_count > 0:
                logger.debug(f"Cleaned up {cleanup_count} old sessions on startup")
            
            # Initialize MCP integration
            await self._initialize_mcp_integration()
            
            self.is_running = True
            logger.info("ReAct service started")
            
        except Exception as e:
            logger.error(f"Failed to start ReAct service: {str(e)}")
            raise
    
    async def stop(self):
        """Stop the ReAct service."""
        if not self.is_running:
            return
        
        try:
            # Stop session manager auto-save
            await self.session_manager.stop_auto_save()
            
            # Save all active sessions
            active_sessions = list(self.session_manager.active_sessions.keys())
            for session_id in active_sessions:
                await self.session_manager.save_session(session_id)
            
            self.is_running = False
            logger.info("ReAct service stopped")
            
        except Exception as e:
            logger.error(f"Error stopping ReAct service: {str(e)}")
    
    async def process_user_request(
        self, 
        user_input: str, 
        session_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process a user request through the ReAct engine.
        
        Args:
            user_input: User's natural language input
            session_id: Optional existing session ID
            context: Additional context information
            
        Yields:
            Dict[str, Any]: Status updates and results from ReAct processing
        """
        if not self.is_running:
            # Lazy start if not running instead of raising error
            await self.start()
        
        try:
            # Get or create session
            if session_id:
                session = await self.session_manager.get_session(session_id)
                if not session:
                    # Session doesn't exist, create a new one with the specified ID
                    session = await self.session_manager.create_session(user_input, context)
                    # Override the generated ID with the requested one
                    session.id = session_id
                    # Register the session with the correct ID
                    self.session_manager.active_sessions[session_id] = session
                    # Save with the correct ID
                    await self.session_manager.save_session(session_id)
                else:
                    # Update existing session with new input
                    session.user_input = user_input
                    if context:
                        session.metadata.update(context)
            else:
                session = await self.session_manager.create_session(user_input, context)
            
            # Add service context
            service_context = {
                "service_version": "1.0.0",
                "config": {
                    "ai_provider": self.config.ai.provider,
                    "ai_model": self.config.ai.model
                }
            }
            if context:
                service_context.update(context)
            
            # Process through ReAct engine with existing session
            async for update in self.react_engine.process_user_input(user_input, service_context, session):
                # Add session information to updates
                update["session_id"] = session.id
                
                # Auto-save session on significant updates
                if update.get("type") in ["task_plan", "sub_task_result", "final_result"]:
                    await self.session_manager.save_session(session.id)
                
                yield update
            
            # Final save
            await self.session_manager.save_session(session.id)
            
        except Exception as e:
            logger.error(f"Error processing user request: {str(e)}")
            
            # Yield error information
            yield {
                "type": "service_error",
                "content": f"Service error: {str(e)}",
                "error_type": type(e).__name__,
                "session_id": session_id if session_id else "unknown"
            }
    
    async def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Optional[Dict[str, Any]]: Session information or None if not found
        """
        try:
            session = await self.session_manager.get_session(session_id)
            if session:
                return session.to_dict()
            return None
            
        except Exception as e:
            logger.error(f"Error getting session info: {str(e)}")
            return None
    
    async def generate_task_summary_content(self, session_id: str) -> str:
        """
        Generate task execution summary content for completion messages.
        
        Args:
            session_id: Session identifier
            
        Returns:
            str: Task summary content
        """
        try:
            session = await self.session_manager.get_session(session_id)
            if not session:
                return "🔍 执行摘要：\n\n📊 最终结果：\n🎉 任务执行完成"
            
            from ..react.engine import TaskStatus
            
            successful_tasks = sum(1 for task in session.tasks if task.status == TaskStatus.COMPLETED)
            failed_tasks = sum(1 for task in session.tasks if task.status == TaskStatus.FAILED)
            total_tasks = len(session.tasks)
            
            # Handle conversational inputs with no tasks
            if total_tasks == 0:
                return "Conversational interaction completed successfully"
            
            # Generate detailed task breakdown
            content_lines = ["🔍 执行摘要：", ""]
            
            for i, task in enumerate(session.tasks, 1):
                # Get task status and evaluation
                evaluation = session.evaluations.get(task.id)
                status_emoji = "✅" if task.status == TaskStatus.COMPLETED else "❌"
                status_text = "成功" if task.status == TaskStatus.COMPLETED else "失败"
                
                # Get tools used
                tools_used = [task.tool_name] if task.tool_name else []
                tools_text = f"使用工具: {tools_used}" if tools_used else "无工具使用"
                
                # Add task summary
                task_line = f"{status_emoji} 任务 {i}: {task.description} - {status_text}"
                content_lines.append(task_line)
                content_lines.append(f"   {tools_text}")
                
                # Add evaluation details if available
                if evaluation:
                    if evaluation.reasoning:
                        # Truncate long reasoning for readability
                        reasoning = evaluation.reasoning[:100] + "..." if len(evaluation.reasoning) > 100 else evaluation.reasoning
                        content_lines.append(f"   评估: {reasoning}")
                    
                    # Show detailed error information for failed tasks
                    if task.status == TaskStatus.FAILED and evaluation.evidence:
                        for evidence in evaluation.evidence[:2]:  # Show up to 2 error messages
                            error_text = evidence[:120] + "..." if len(evidence) > 120 else evidence
                            content_lines.append(f"   错误: {error_text}")
                    
                    if evaluation.recommendations:
                        # Show first recommendation if any
                        first_rec = evaluation.recommendations[0] if evaluation.recommendations else ""
                        if first_rec:
                            rec_text = first_rec[:80] + "..." if len(first_rec) > 80 else first_rec
                            content_lines.append(f"   建议: {rec_text}")
                
                # Fallback: Extract error info directly from task results if no evaluation available
                elif task.status == TaskStatus.FAILED and task.id in session.task_results:
                    from ..react.engine import ToolResultType
                    error_results = [r for r in session.task_results[task.id] if r.type == ToolResultType.ERROR]
                    for error_result in error_results[:2]:  # Show up to 2 error messages
                        error_text = error_result.content[:120] + "..." if len(error_result.content) > 120 else error_result.content
                        content_lines.append(f"   错误: {error_text}")
                
                content_lines.append("")  # Empty line for spacing
            
            # Overall result
            overall_success = failed_tasks == 0 and successful_tasks > 0
            if overall_success:
                overall_emoji = "🎉"
                overall_text = f"所有任务执行成功！共完成 {successful_tasks} 个任务"
            elif successful_tasks > 0:
                overall_emoji = "⚠️"
                overall_text = f"部分任务完成：{successful_tasks} 个成功，{failed_tasks} 个失败"
            else:
                overall_emoji = "❌"
                overall_text = f"所有任务都失败了：共 {failed_tasks} 个任务失败"
            
            content_lines.extend([
                "📊 最终结果：",
                f"{overall_emoji} {overall_text}",
                f"⏱️ 总耗时: {(session.updated_at - session.created_at).total_seconds():.1f} 秒"
            ])
            
            return "\n".join(content_lines)
            
        except Exception as e:
            logger.error(f"Error generating task summary: {str(e)}")
            return "🔍 执行摘要：\n\n📊 最终结果：\n🎉 任务执行完成"
    
    async def list_sessions(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        List available sessions.
        
        Args:
            limit: Maximum number of sessions to return
            
        Returns:
            List[Dict[str, Any]]: List of session metadata
        """
        try:
            return await self.session_manager.list_sessions(limit)
        except Exception as e:
            logger.error(f"Error listing sessions: {str(e)}")
            return []
    
    async def _initialize_mcp_integration(self) -> None:
        """Initialize MCP integration for the ReAct engine."""
        # Skip if already initialized
        if self.mcp_integration is not None:
            logger.debug("MCP integration already initialized, skipping")
            return
            
        try:
            logger.info("Initializing MCP integration for ReAct engine...")
            
            # Look for MCP configuration in standard locations
            mcp_config_paths = [
                Path.cwd() / ".simacode" / "mcp.yaml",
                Path.cwd() / "mcp.yaml",
                Path.home() / ".config" / "simacode" / "mcp.yaml"
            ]
            
            mcp_config_path = None
            for path in mcp_config_paths:
                if path.exists():
                    mcp_config_path = path
                    logger.info(f"Found MCP configuration at: {path}")
                    break
            
            # Set up MCP integration
            self.mcp_integration = await setup_mcp_integration_for_react(
                self.react_engine, 
                mcp_config_path
            )
            
            if self.mcp_integration:
                stats = self.mcp_integration.get_registry_stats()
                logger.info(f"MCP integration initialized with {stats['total_tools']} tools")
            else:
                logger.warning("MCP integration failed to initialize, continuing without MCP tools")
                
        except Exception as e:
            logger.warning(f"Could not initialize MCP integration: {str(e)}")
            logger.info("ReAct service will continue without MCP tools")
    
    async def refresh_mcp_tools(self) -> bool:
        """
        Refresh MCP tools in the ReAct engine.
        
        Returns:
            bool: True if refresh successful
        """
        try:
            if self.mcp_integration:
                tool_count = await self.mcp_integration.refresh_tools()
                logger.info(f"Refreshed {tool_count} MCP tools")
                return True
            else:
                logger.warning("MCP integration not available")
                return False
                
        except Exception as e:
            logger.error(f"Failed to refresh MCP tools: {str(e)}")
            return False
    
    def get_mcp_status(self) -> Dict[str, Any]:
        """
        Get MCP integration status.
        
        Returns:
            Dict[str, Any]: MCP status information
        """
        if self.mcp_integration:
            return {
                "enabled": True,
                "initialized": self.mcp_integration.is_initialized,
                "stats": self.mcp_integration.get_registry_stats()
            }
        else:
            return {
                "enabled": False,
                "initialized": False,
                "stats": {}
            }
    
    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            bool: True if deleted successfully, False otherwise
        """
        try:
            return await self.session_manager.delete_session(session_id)
        except Exception as e:
            logger.error(f"Error deleting session: {str(e)}")
            return False
    
    async def get_service_status(self) -> Dict[str, Any]:
        """
        Get comprehensive service status information.
        
        Returns:
            Dict[str, Any]: Service status and statistics
        """
        try:
            # Get session statistics
            session_stats = await self.session_manager.get_session_statistics()
            
            # Get tool registry information
            available_tools = self.react_engine.tool_registry.list_tools()
            tool_stats = self.react_engine.tool_registry.get_registry_stats()
            
            return {
                "service_running": self.is_running,
                "ai_client_type": type(self.ai_client).__name__,
                "execution_mode": self.react_engine.execution_mode.value,
                "available_tools": available_tools,
                "tool_statistics": tool_stats,
                "session_statistics": session_stats,
                "configuration": {
                    "ai_provider": self.config.ai.provider,
                    "ai_model": self.config.ai.model,
                    "logging_level": self.config.logging.level
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting service status: {str(e)}")
            return {
                "service_running": self.is_running,
                "error": str(e)
            }
    
    async def resume_session(self, session_id: str, new_input: Optional[str] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Resume a previous session, optionally with new input.
        
        Args:
            session_id: Session identifier to resume
            new_input: Optional new user input to process
            
        Yields:
            Dict[str, Any]: Status updates and results
        """
        try:
            session = await self.session_manager.get_session(session_id)
            if not session:
                yield {
                    "type": "error",
                    "content": f"Session not found: {session_id}",
                    "session_id": session_id
                }
                return
            
            # Determine what to do based on session state and input
            if new_input:
                # Process new input in the context of the existing session
                async for update in self.process_user_request(new_input, session_id):
                    yield update
            else:
                # Resume existing session where it left off
                if session.state.value in ["completed", "failed"]:
                    yield {
                        "type": "info",
                        "content": f"Session {session_id} was already {session.state.value}",
                        "session_id": session_id,
                        "session_data": session.to_dict()
                    }
                else:
                    yield {
                        "type": "info", 
                        "content": f"Resuming session {session_id} from state: {session.state.value}",
                        "session_id": session_id,
                        "session_data": session.to_dict()
                    }
                    
                    # TODO: Implement resumption logic for interrupted sessions
                    # This would involve continuing from where the session left off
            
        except Exception as e:
            logger.error(f"Error resuming session: {str(e)}")
            yield {
                "type": "error",
                "content": f"Failed to resume session: {str(e)}",
                "session_id": session_id,
                "error_type": type(e).__name__
            }
    
    async def configure_execution_mode(self, mode: str) -> bool:
        """
        Configure the execution mode for the ReAct engine.
        
        Args:
            mode: Execution mode ("sequential", "parallel", "adaptive")
            
        Returns:
            bool: True if configured successfully, False otherwise
        """
        try:
            execution_mode = ExecutionMode(mode.lower())
            self.react_engine.execution_mode = execution_mode
            logger.info(f"Execution mode changed to: {mode}")
            return True
            
        except ValueError:
            logger.error(f"Invalid execution mode: {mode}")
            return False
        except Exception as e:
            logger.error(f"Error configuring execution mode: {str(e)}")
            return False