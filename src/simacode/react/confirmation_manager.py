"""
Confirmation Manager for Human-in-Loop Feature

This module provides the ConfirmationManager class that handles task confirmation
requests, user responses, and timeout management for the human-in-loop feature.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from ..api.models import TaskConfirmationRequest, TaskConfirmationResponse, ConfirmationStatus
from .planner import Task

logger = logging.getLogger(__name__)


class ConfirmationManager:
    """管理任务确认流程"""
    
    def __init__(self):
        self.pending_confirmations: Dict[str, ConfirmationStatus] = {}
        self.confirmation_callbacks: Dict[str, asyncio.Event] = {}
        logger.info("ConfirmationManager initialized")
    
    async def request_confirmation(
        self, 
        session_id: str, 
        tasks: List[Task],
        timeout_seconds: int = 300
    ) -> TaskConfirmationRequest:
        """发起确认请求"""
        
        logger.info(f"Requesting confirmation for session {session_id} with {len(tasks)} tasks")
        
        # 创建确认状态
        confirmation = ConfirmationStatus(
            session_id=session_id,
            status="pending",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=timeout_seconds)
        )
        
        self.pending_confirmations[session_id] = confirmation
        self.confirmation_callbacks[session_id] = asyncio.Event()
        
        # 返回确认请求
        return TaskConfirmationRequest(
            session_id=session_id,
            tasks=[task.to_dict() for task in tasks],
            timeout_seconds=timeout_seconds
        )
    
    async def wait_for_confirmation(
        self, 
        session_id: str, 
        timeout_seconds: int = 300
    ) -> TaskConfirmationResponse:
        """等待用户确认"""
        
        logger.info(f"Waiting for confirmation from session {session_id} (timeout: {timeout_seconds}s)")
        
        try:
            # 等待确认响应或超时
            await asyncio.wait_for(
                self.confirmation_callbacks[session_id].wait(),
                timeout=timeout_seconds
            )
            
            # 返回用户响应
            confirmation = self.pending_confirmations.get(session_id)
            if confirmation and confirmation.user_response:
                logger.info(f"Received confirmation response for session {session_id}: {confirmation.user_response.action}")
                return confirmation.user_response
            else:
                logger.warning(f"No user response found for session {session_id}")
                raise TimeoutError("Confirmation timeout")
                
        except asyncio.TimeoutError:
            # 超时处理
            logger.warning(f"Confirmation timeout for session {session_id}")
            self._handle_confirmation_timeout(session_id)
            raise TimeoutError("User confirmation timeout")
        
        finally:
            # 清理资源
            self._cleanup_confirmation(session_id)
    
    def submit_confirmation(
        self, 
        session_id: str, 
        response: TaskConfirmationResponse
    ) -> bool:
        """提交用户确认响应"""
        
        logger.info(f"Submitting confirmation response for session {session_id}: {response.action}")
        
        if session_id not in self.pending_confirmations:
            logger.warning(f"No pending confirmation found for session {session_id}")
            return False
        
        # 更新确认状态
        confirmation = self.pending_confirmations[session_id]
        confirmation.user_response = response
        confirmation.status = response.action
        
        # 触发等待的协程
        if session_id in self.confirmation_callbacks:
            self.confirmation_callbacks[session_id].set()
            logger.info(f"Confirmation callback triggered for session {session_id}")
        
        return True
    
    def get_pending_confirmation(self, session_id: str) -> Optional[ConfirmationStatus]:
        """获取待确认的状态"""
        return self.pending_confirmations.get(session_id)
    
    def cancel_confirmation(self, session_id: str) -> bool:
        """取消确认请求"""
        if session_id not in self.pending_confirmations:
            return False
        
        logger.info(f"Cancelling confirmation for session {session_id}")
        
        # 更新状态为取消
        self.pending_confirmations[session_id].status = "cancelled"
        
        # 触发回调
        if session_id in self.confirmation_callbacks:
            self.confirmation_callbacks[session_id].set()
        
        return True
    
    def _handle_confirmation_timeout(self, session_id: str):
        """处理确认超时"""
        if session_id in self.pending_confirmations:
            self.pending_confirmations[session_id].status = "timeout"
            logger.warning(f"Confirmation timeout for session {session_id}")
    
    def _cleanup_confirmation(self, session_id: str):
        """清理确认相关资源"""
        logger.debug(f"Cleaning up confirmation resources for session {session_id}")
        self.pending_confirmations.pop(session_id, None)
        self.confirmation_callbacks.pop(session_id, None)
    
    def get_active_confirmations(self) -> Dict[str, ConfirmationStatus]:
        """获取所有活跃的确认请求"""
        now = datetime.now()
        active = {}
        
        for session_id, confirmation in self.pending_confirmations.items():
            if confirmation.status == "pending" and confirmation.expires_at > now:
                active[session_id] = confirmation
        
        return active
    
    def cleanup_expired_confirmations(self):
        """清理过期的确认请求"""
        now = datetime.now()
        expired_sessions = []
        
        for session_id, confirmation in self.pending_confirmations.items():
            if confirmation.expires_at <= now and confirmation.status == "pending":
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            logger.info(f"Cleaning up expired confirmation for session {session_id}")
            self._handle_confirmation_timeout(session_id)
            self._cleanup_confirmation(session_id)