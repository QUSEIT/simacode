"""
Session Manager for ReAct Engine

This module provides comprehensive session management capabilities including
session persistence, state management, and recovery operations.
"""

import json
import asyncio
import aiofiles
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..react.engine import ReActSession, ReActState
from ..react.planner import Task, TaskStatus

logger = logging.getLogger(__name__)


class SessionConfig(BaseModel):
    """Configuration for session management."""
    sessions_directory: Path = Field(default=Path(".simacode/sessions"))
    auto_save_interval: int = Field(default=30, description="Auto-save interval in seconds")
    max_session_age: int = Field(default=7, description="Maximum session age in days")
    compression_enabled: bool = Field(default=True)
    max_sessions_to_keep: int = Field(default=100)


class SessionManager:
    """
    Manages ReAct sessions including persistence, state management, and recovery.
    
    The SessionManager handles:
    - Session creation and initialization
    - Automatic and manual session saving
    - Session loading and restoration
    - Session cleanup and archival
    - Session state monitoring
    """
    
    def __init__(self, config: SessionConfig):
        """
        Initialize the session manager.
        
        Args:
            config: Session management configuration
        """
        self.config = config
        self.active_sessions: Dict[str, ReActSession] = {}
        self.auto_save_task: Optional[asyncio.Task] = None
        
        # Directory will be created only when needed (on first session creation)
        logger.info(f"Session manager initialized with directory: {self.config.sessions_directory}")
    
    def _ensure_sessions_directory(self) -> None:
        """Ensure sessions directory exists (create only when needed)."""
        if not self.config.sessions_directory.exists():
            self.config.sessions_directory.mkdir(parents=True, exist_ok=True)
            logger.info(f"Created sessions directory: {self.config.sessions_directory}")
    
    async def create_session(self, user_input: str, context: Optional[Dict[str, Any]] = None, session_id: Optional[str] = None) -> ReActSession:
        """
        Create a new ReAct session.
        
        Args:
            user_input: Initial user input for the session
            context: Additional context information
            session_id: Optional specific session ID to use
            
        Returns:
            ReActSession: Newly created session
        """
        session = session_id and ReActSession(id=session_id, user_input=user_input) or ReActSession(user_input=user_input)
        
        if context:
            session.metadata.update({"context":context})
        
        # Add session metadata
        session.metadata.update({
            "session_manager_version": "1.0.0",
            "created_by": "session_manager",
            "session_type": "react"
        })
        
        # Register session
        self.active_sessions[session.id] = session
        
        # Ensure directory exists before saving
        self._ensure_sessions_directory()
        
        # Save initial session state
        await self.save_session(session.id)
        
        logger.info(f"Created new session: {session.id}")
        return session
    
    async def get_session(self, session_id: str) -> Optional[ReActSession]:
        """
        Get a session by ID, loading from disk if necessary.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Optional[ReActSession]: Session if found, None otherwise
        """
        # Check active sessions first
        if session_id in self.active_sessions:
            return self.active_sessions[session_id]
        
        # Try to load from disk
        session = await self.load_session(session_id)
        if session:
            self.active_sessions[session_id] = session
            logger.info(f"Loaded session from disk: {session_id}")
        
        return session
    
    async def save_session(self, session_id: str) -> bool:
        """
        Save a session to disk.
        
        Args:
            session_id: Session identifier
            
        Returns:
            bool: True if saved successfully, False otherwise
        """
        session = self.active_sessions.get(session_id)
        if not session:
            logger.warning(f"Session not found for saving: {session_id}")
            return False
        
        try:
            # Ensure directory exists before saving
            self._ensure_sessions_directory()
            
            session_file = self.config.sessions_directory / f"{session_id}.json"
            
            # Save session data
            session_data = session.to_dict()
            
            async with aiofiles.open(session_file, 'w', encoding='utf-8') as f:
                await f.write(json.dumps(session_data, indent=2, ensure_ascii=False))
            
            session.add_log_entry(f"Session saved to {session_file}")
            logger.debug(f"Session saved: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save session {session_id}: {str(e)}")
            return False
    
    async def load_session(self, session_id: str) -> Optional[ReActSession]:
        """
        Load a session from disk.
        
        Args:
            session_id: Session identifier
            
        Returns:
            Optional[ReActSession]: Loaded session or None if not found
        """
        try:
            session_file = self.config.sessions_directory / f"{session_id}.json"
            
            if not session_file.exists():
                return None
            
            async with aiofiles.open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.loads(await f.read())
            
            # Reconstruct session from data
            session = await self._reconstruct_session_from_data(session_data)
            
            logger.debug(f"Session loaded: {session_id}")
            return session
            
        except Exception as e:
            logger.error(f"Failed to load session {session_id}: {str(e)}")
            return None
    
    async def _reconstruct_session_from_data(self, session_data: Dict[str, Any]) -> ReActSession:
        """Reconstruct a ReActSession from serialized data."""
        session = ReActSession()
        
        # Basic properties
        session.id = session_data.get("id", session.id)
        session.user_input = session_data.get("user_input", "")
        session.state = ReActState(session_data.get("state", "idle"))
        session.current_task_index = session_data.get("current_task_index", 0)
        session.execution_log = session_data.get("execution_log", [])
        session.metadata = session_data.get("metadata", {})
        session.retry_count = session_data.get("retry_count", 0)
        session.max_retries = session_data.get("max_retries", 3)
        
        # Timestamps
        if "created_at" in session_data:
            session.created_at = datetime.fromisoformat(session_data["created_at"])
        if "updated_at" in session_data:
            session.updated_at = datetime.fromisoformat(session_data["updated_at"])
        
        # Reconstruct tasks
        tasks_data = session_data.get("tasks", [])
        session.tasks = [Task.from_dict(task_data) for task_data in tasks_data]
        
        # Reconstruct conversation history for continuous context
        from ..ai.conversation import Message
        conversation_data = session_data.get("conversation_history", [])
        session.conversation_history = []
        for msg_data in conversation_data:
            if isinstance(msg_data, dict):
                message = Message(
                    role=msg_data.get("role", "user"),
                    content=msg_data.get("content", "")
                )
                session.conversation_history.append(message)
        
        # Note: tool_results and evaluations are not reconstructed as they
        # would require importing and reconstructing complex objects
        # They can be rebuilt by re-executing if needed
        
        return session
    
    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session from memory and disk.
        
        Args:
            session_id: Session identifier
            
        Returns:
            bool: True if deleted successfully, False otherwise
        """
        try:
            # Remove from active sessions
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
            
            # Delete from disk
            session_file = self.config.sessions_directory / f"{session_id}.json"
            if session_file.exists():
                session_file.unlink()
            
            logger.debug(f"Session deleted: {session_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {str(e)}")
            return False
    
    async def list_sessions(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        List available sessions with metadata.
        
        Args:
            limit: Maximum number of sessions to return
            
        Returns:
            List[Dict[str, Any]]: List of session metadata
        """
        sessions = []
        
        # If directory doesn't exist, return empty list (no sessions)
        if not self.config.sessions_directory.exists():
            return sessions
        
        try:
            session_files = list(self.config.sessions_directory.glob("*.json"))
            
            # Sort by modification time (newest first)
            session_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            
            if limit:
                session_files = session_files[:limit]
            
            for session_file in session_files:
                try:
                    async with aiofiles.open(session_file, 'r', encoding='utf-8') as f:
                        session_data = json.loads(await f.read())
                    
                    sessions.append({
                        "id": session_data.get("id", session_file.stem),
                        "user_input": session_data.get("user_input", "")[:100],
                        "state": session_data.get("state", "unknown"),
                        "created_at": session_data.get("created_at"),
                        "updated_at": session_data.get("updated_at"),
                        "task_count": len(session_data.get("tasks", [])),
                        "file_size": session_file.stat().st_size
                    })
                    
                except Exception as e:
                    logger.warning(f"Failed to read session metadata from {session_file}: {str(e)}")
                    continue
            
        except Exception as e:
            logger.error(f"Failed to list sessions: {str(e)}")
        
        return sessions
    
    async def cleanup_old_sessions(self) -> int:
        """
        Clean up old sessions based on configuration.
        
        Returns:
            int: Number of sessions cleaned up
        """
        cleanup_count = 0
        cutoff_date = datetime.now() - timedelta(days=self.config.max_session_age)
        
        try:
            sessions = await self.list_sessions()
            
            for session_info in sessions:
                try:
                    if session_info.get("updated_at"):
                        updated_at = datetime.fromisoformat(session_info["updated_at"])
                        if updated_at < cutoff_date:
                            await self.delete_session(session_info["id"])
                            cleanup_count += 1
                except Exception as e:
                    logger.warning(f"Failed to cleanup session {session_info['id']}: {str(e)}")
            
            # Also enforce max session limit
            if len(sessions) > self.config.max_sessions_to_keep:
                sessions_to_delete = sessions[self.config.max_sessions_to_keep:]
                for session_info in sessions_to_delete:
                    try:
                        await self.delete_session(session_info["id"])
                        cleanup_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete excess session {session_info['id']}: {str(e)}")
            
            if cleanup_count > 0:
                logger.debug(f"Cleaned up {cleanup_count} old sessions")
            
        except Exception as e:
            logger.error(f"Failed to cleanup old sessions: {str(e)}")
        
        return cleanup_count
    
    async def start_auto_save(self):
        """Start automatic session saving."""
        if self.auto_save_task and not self.auto_save_task.done():
            return
        
        self.auto_save_task = asyncio.create_task(self._auto_save_loop())
        logger.info("Auto-save started")
    
    async def stop_auto_save(self):
        """Stop automatic session saving."""
        if self.auto_save_task and not self.auto_save_task.done():
            self.auto_save_task.cancel()
            try:
                await self.auto_save_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Auto-save stopped")
    
    async def _auto_save_loop(self):
        """Auto-save loop for active sessions."""
        while True:
            try:
                await asyncio.sleep(self.config.auto_save_interval)
                
                # Save all active sessions
                for session_id in list(self.active_sessions.keys()):
                    await self.save_session(session_id)
                
                # Periodic cleanup
                if datetime.now().hour == 2:  # Run cleanup at 2 AM
                    await self.cleanup_old_sessions()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in auto-save loop: {str(e)}")
                await asyncio.sleep(5)  # Wait before retrying
    
    async def get_session_statistics(self) -> Dict[str, Any]:
        """Get session management statistics."""
        try:
            sessions = await self.list_sessions()
            
            # Calculate statistics
            total_sessions = len(sessions)
            active_sessions = len(self.active_sessions)
            
            states = {}
            for session_info in sessions:
                state = session_info.get("state", "unknown")
                states[state] = states.get(state, 0) + 1
            
            # Disk usage
            total_size = sum(session_info.get("file_size", 0) for session_info in sessions)
            
            return {
                "total_sessions": total_sessions,
                "active_sessions": active_sessions,
                "state_distribution": states,
                "total_disk_usage": total_size,
                "sessions_directory": str(self.config.sessions_directory),
                "auto_save_enabled": self.auto_save_task is not None and not self.auto_save_task.done()
            }
            
        except Exception as e:
            logger.error(f"Failed to get session statistics: {str(e)}")
            return {}