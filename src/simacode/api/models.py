"""
API request/response models for SimaCode API service.

This module defines Pydantic models for API requests and responses,
ensuring proper validation and documentation.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# Request Models
class ChatRequest(BaseModel):
    """Enhanced chat request model with ReAct support."""
    message: str = Field(..., description="The user's message")
    session_id: Optional[str] = Field(None, description="Optional session ID")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional context")
    stream: Optional[bool] = Field(False, description="Enable streaming response")
    
    # 🆕 新增字段（可选，用于高级控制）
    force_mode: Optional[str] = Field(None, description="Force processing mode: 'chat' or 'react'")
    react_config: Optional[Dict[str, Any]] = Field(default_factory=dict, description="ReAct engine configuration")


class ReActRequest(BaseModel):
    """Request model for ReAct operations."""
    task: str = Field(..., description="The task to execute")
    session_id: Optional[str] = Field(None, description="Optional session ID")
    context: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional context")
    execution_mode: Optional[str] = Field(None, description="Execution mode (adaptive, conservative, aggressive)")


# Response Models
class ChatResponse(BaseModel):
    """Response model for chat operations."""
    content: str = Field(..., description="The AI's response")
    session_id: str = Field(..., description="Session identifier")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class ReActResponse(BaseModel):
    """Response model for ReAct operations."""
    result: str = Field(..., description="The execution result")
    session_id: str = Field(..., description="Session identifier")
    steps: List[Dict[str, Any]] = Field(default_factory=list, description="Execution steps")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class SessionInfo(BaseModel):
    """Session information model."""
    session_id: str = Field(..., description="Session identifier")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    message_count: int = Field(0, description="Number of messages in session")
    status: str = Field("active", description="Session status")


class HealthResponse(BaseModel):
    """Health check response model."""
    status: str = Field(..., description="Service status")
    components: Dict[str, str] = Field(default_factory=dict, description="Component statuses")
    version: str = Field(..., description="API version")
    config: Dict[str, Any] = Field(default_factory=dict, description="Configuration info")


class ErrorResponse(BaseModel):
    """Error response model."""
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Detailed error information")
    code: Optional[str] = Field(None, description="Error code")


# WebSocket Models
class WebSocketMessage(BaseModel):
    """WebSocket message model."""
    type: str = Field(..., description="Message type")
    data: Dict[str, Any] = Field(default_factory=dict, description="Message data")
    session_id: Optional[str] = Field(None, description="Session identifier")


class StreamingChatChunk(BaseModel):
    """扩展的流式聊天块模型 - 支持确认功能"""
    chunk: str = Field(..., description="文本内容")
    session_id: str = Field(..., description="会话标识")
    finished: bool = Field(False, description="是否为最终块")
    
    # 扩展字段
    chunk_type: Optional[str] = Field(
        "content", 
        description="块类型: 'content', 'status', 'tool_output', 'task_init', 'error', 'completion', 'confirmation_request', 'confirmation_received'"
    )
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="元数据")
    
    # 🆕 确认相关字段
    confirmation_data: Optional[Dict[str, Any]] = Field(None, description="确认请求数据")
    requires_response: Optional[bool] = Field(False, description="是否需要用户响应")
    stream_paused: Optional[bool] = Field(False, description="流是否暂停等待响应")


# Human in Loop Confirmation Models
class TaskConfirmationRequest(BaseModel):
    """任务确认请求模型"""
    
    session_id: str = Field(description="Session identifier")
    tasks: List[Dict[str, Any]] = Field(description="Planned tasks for confirmation")
    message: str = Field(default="请确认执行计划", description="Confirmation message")
    options: List[str] = Field(
        default=["confirm", "modify", "cancel"],
        description="Available confirmation options"
    )
    timeout_seconds: int = Field(default=300, description="Confirmation timeout")


class TaskConfirmationResponse(BaseModel):
    """任务确认响应模型"""
    
    session_id: str = Field(description="Session identifier")
    action: str = Field(description="User action: confirm, modify, cancel")
    modified_tasks: Optional[List[Dict[str, Any]]] = Field(
        None, 
        description="Modified task list if action is 'modify'"
    )
    user_message: Optional[str] = Field(
        None, 
        description="Additional user message or modification instructions"
    )


class ConfirmationStatus(BaseModel):
    """确认状态模型"""
    
    session_id: str
    status: str  # "pending", "confirmed", "modified", "cancelled", "timeout"
    created_at: datetime
    expires_at: datetime
    user_response: Optional[TaskConfirmationResponse] = None