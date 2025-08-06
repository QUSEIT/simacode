"""
Chat Stream Confirmation Manager

Manages confirmation workflows within the chat/stream interface.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from ..api.models import TaskConfirmationResponse

logger = logging.getLogger(__name__)


@dataclass
class ConfirmationState:
    """确认状态数据类"""
    session_id: str
    status: str  # "pending", "confirmed", "modified", "cancelled", "timeout"
    created_at: datetime
    confirmation_data: Dict[str, Any]
    user_response: Optional[TaskConfirmationResponse] = None
    timeout_seconds: int = 300
    confirmation_round: int = 1

    @property
    def expires_at(self) -> datetime:
        return self.created_at + timedelta(seconds=self.timeout_seconds)

    @property
    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at


class ChatStreamConfirmationManager:
    """聊天流确认管理器"""
    
    def __init__(self):
        self.pending_confirmations: Dict[str, ConfirmationState] = {}
        self.stream_events: Dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()
        self._confirmation_rounds: Dict[str, int] = {}
    
    async def request_confirmation(
        self, 
        session_id: str, 
        tasks: List[Any], 
        timeout_seconds: int = 300
    ) -> Dict[str, Any]:
        """
        创建确认请求并暂停流
        
        Args:
            session_id: 会话ID
            tasks: 待确认的任务列表
            timeout_seconds: 确认超时时间
            
        Returns:
            确认数据字典
        """
        async with self._lock:
            # 增加确认轮次
            self._confirmation_rounds[session_id] = self._confirmation_rounds.get(session_id, 0) + 1
            confirmation_round = self._confirmation_rounds[session_id]
            
            # 统一转换tasks为字典格式
            normalized_tasks = self._normalize_tasks(tasks)
            
            confirmation_data = {
                "tasks": normalized_tasks,
                "total_tasks": len(normalized_tasks),
                "options": ["confirm", "modify", "cancel"],
                "timeout_seconds": timeout_seconds,
                "confirmation_round": confirmation_round,
                "risk_level": self._assess_risk_level(normalized_tasks)
            }
            
            # 创建暂停事件
            self.stream_events[session_id] = asyncio.Event()
            
            # 记录等待状态
            self.pending_confirmations[session_id] = ConfirmationState(
                session_id=session_id,
                status="pending",
                created_at=datetime.now(),
                confirmation_data=confirmation_data,
                timeout_seconds=timeout_seconds,
                confirmation_round=confirmation_round
            )
            
            logger.info(f"Created confirmation request for session {session_id}, round {confirmation_round}")
            return confirmation_data
    
    async def submit_confirmation(
        self, 
        session_id: str, 
        action: str, 
        user_message: Optional[str] = None
    ) -> bool:
        """
        提交确认响应并恢复流
        
        Args:
            session_id: 会话ID
            action: 用户动作 (confirm, modify, cancel)
            user_message: 用户消息（修改建议等）
            
        Returns:
            是否成功提交
        """
        async with self._lock:
            logger.debug(f"[CONFIRM_DEBUG] ChatStreamConfirmationManager.submit_confirmation called")
            logger.debug(f"[CONFIRM_DEBUG] Session: {session_id}, Action: {action}")
            logger.debug(f"[CONFIRM_DEBUG] Pending confirmations: {list(self.pending_confirmations.keys())}")
            
            if session_id not in self.pending_confirmations:
                logger.warning(f"No pending confirmation for session {session_id}")
                return False
            
            confirmation = self.pending_confirmations[session_id]
            
            # 检查是否已超时
            if confirmation.is_expired:
                logger.warning(f"Confirmation for session {session_id} has expired")
                confirmation.status = "timeout"
                self._cleanup_confirmation(session_id)
                return False
            
            # 创建用户响应
            confirmation.user_response = TaskConfirmationResponse(
                session_id=session_id,
                action=action,
                user_message=user_message
            )
            confirmation.status = action
            
            # 恢复流式响应
            if session_id in self.stream_events:
                self.stream_events[session_id].set()
                logger.info(f"Resumed stream for session {session_id} with action: {action}")
            
            return True
    
    async def wait_for_confirmation(
        self, 
        session_id: str
    ) -> Optional[TaskConfirmationResponse]:
        """
        等待确认响应
        
        Args:
            session_id: 会话ID
            
        Returns:
            用户确认响应，超时返回None
        """
        logger.debug(f"[CONFIRM_DEBUG] ChatStreamConfirmationManager.wait_for_confirmation called for {session_id}")
        logger.debug(f"[CONFIRM_DEBUG] Stream events: {list(self.stream_events.keys())}")
        logger.debug(f"[CONFIRM_DEBUG] Pending confirmations: {list(self.pending_confirmations.keys())}")
        
        if session_id not in self.stream_events or session_id not in self.pending_confirmations:
            logger.warning(f"No confirmation setup for session {session_id}")
            return None
        
        confirmation = self.pending_confirmations[session_id]
        timeout_seconds = confirmation.timeout_seconds
        
        try:
            # 等待确认响应
            logger.debug(f"[CONFIRM_DEBUG] Starting to wait for event, timeout: {timeout_seconds}s")
            await asyncio.wait_for(
                self.stream_events[session_id].wait(), 
                timeout=timeout_seconds
            )
            logger.debug(f"[CONFIRM_DEBUG] Event received, processing response")
            
            # 返回用户响应
            response = confirmation.user_response
            logger.info(f"Received confirmation for session {session_id}: {response.action if response else 'None'}")
            logger.debug(f"[CONFIRM_DEBUG] Returning response: {response}")
            
            return response
        
        except asyncio.TimeoutError:
            # 超时处理 - 默认取消任务
            logger.warning(f"Confirmation timeout for session {session_id}")
            confirmation.status = "timeout"
            
            # 创建超时响应
            timeout_response = TaskConfirmationResponse(
                session_id=session_id,
                action="cancel",
                user_message="确认超时，自动取消任务"
            )
            confirmation.user_response = timeout_response
            

            return timeout_response
        
        finally:
            # 清理状态
            logger.debug(f"[CONFIRM_DEBUG] Cleaning up confirmation for session {session_id}")
            self._cleanup_confirmation(session_id)
    
    def get_confirmation_status(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        获取确认状态
        
        Args:
            session_id: 会话ID
            
        Returns:
            确认状态信息
        """
        if session_id not in self.pending_confirmations:
            return None
        
        confirmation = self.pending_confirmations[session_id]
        return {
            "session_id": session_id,
            "status": confirmation.status,
            "created_at": confirmation.created_at.isoformat(),
            "expires_at": confirmation.expires_at.isoformat(),
            "confirmation_round": confirmation.confirmation_round,
            "is_expired": confirmation.is_expired,
            "has_response": confirmation.user_response is not None
        }
    
    def _normalize_tasks(self, tasks: List[Any]) -> List[Dict[str, Any]]:
        """
        统一转换tasks为字典格式
        
        Args:
            tasks: 任务列表，可能是Task对象或字典
            
        Returns:
            字典格式的任务列表
        """
        normalized = []
        for task in tasks:
            if hasattr(task, 'to_dict'):
                # Task对象，转换为字典
                normalized.append(task.to_dict())
            elif isinstance(task, dict):
                # 已经是字典
                normalized.append(task)
            else:
                # 其他类型，尝试转换为字典
                try:
                    if hasattr(task, '__dict__'):
                        normalized.append(task.__dict__)
                    else:
                        # 最后的回退，创建一个基本的任务描述
                        normalized.append({
                            "id": getattr(task, 'id', 'unknown'),
                            "description": str(task),
                            "type": "unknown",
                            "tool": "unknown"
                        })
                except Exception as e:
                    logger.warning(f"Failed to normalize task {task}: {e}")
                    normalized.append({
                        "id": "unknown",
                        "description": str(task),
                        "type": "unknown",
                        "tool": "unknown"
                    })
        return normalized
    
    def _assess_risk_level(self, tasks: List[Dict[str, Any]]) -> str:
        """
        评估任务风险级别
        
        Args:
            tasks: 任务列表
            
        Returns:
            风险级别: low, medium, high
        """
        high_risk_tools = {"bash", "shell", "file_delete", "git_push"}
        medium_risk_tools = {"file_write", "file_edit", "network_request"}
        
        has_high_risk = any(
            task.get("tool") in high_risk_tools 
            for task in tasks
        )
        has_medium_risk = any(
            task.get("tool") in medium_risk_tools 
            for task in tasks
        )
        
        if has_high_risk:
            return "high"
        elif has_medium_risk:
            return "medium"
        else:
            return "low"
    
    def _cleanup_confirmation(self, session_id: str):
        """清理确认状态"""
        if session_id in self.pending_confirmations:
            del self.pending_confirmations[session_id]
        if session_id in self.stream_events:
            del self.stream_events[session_id]
        logger.debug(f"Cleaned up confirmation for session {session_id}")
    
    async def cleanup_expired_confirmations(self):
        """清理过期的确认请求"""
        expired_sessions = []
        
        async with self._lock:
            for session_id, confirmation in self.pending_confirmations.items():
                if confirmation.is_expired:
                    expired_sessions.append(session_id)
            
            for session_id in expired_sessions:
                logger.info(f"Cleaning up expired confirmation for session {session_id}")
                self._cleanup_confirmation(session_id)
    
    def get_all_pending_confirmations(self) -> Dict[str, Dict[str, Any]]:
        """获取所有待处理的确认请求"""
        return {
            session_id: {
                "status": conf.status,
                "created_at": conf.created_at.isoformat(),
                "expires_at": conf.expires_at.isoformat(),
                "confirmation_round": conf.confirmation_round,
                "is_expired": conf.is_expired
            }
            for session_id, conf in self.pending_confirmations.items()
        }


# 全局确认管理器实例
chat_confirmation_manager = ChatStreamConfirmationManager()