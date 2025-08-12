"""
Chat endpoints for SimaCode API.

Provides REST and WebSocket endpoints for AI chat functionality,
including support for human-in-loop confirmation via chat stream.
"""

import json
import logging
from typing import AsyncGenerator

try:
    from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, HTTPException
    from fastapi.responses import StreamingResponse
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = None

from ..dependencies import get_simacode_service
from ..models import ChatRequest, ChatResponse, ErrorResponse, StreamingChatChunk
from ..chat_confirmation import chat_confirmation_manager
from ...core.service import SimaCodeService, ChatRequest as CoreChatRequest

logger = logging.getLogger(__name__)

if FASTAPI_AVAILABLE:
    router = APIRouter()
else:
    router = None


@router.post("/", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    service: SimaCodeService = Depends(get_simacode_service)
) -> ChatResponse:
    """
    Process a chat message with the AI assistant.
    
    Args:
        request: Chat request containing message and optional session ID
        service: SimaCode service instance
        
    Returns:
        AI response
    """
    try:
        # Convert API request to core request
        core_request = CoreChatRequest(
            message=request.message,
            session_id=request.session_id,
            context=request.context,
            stream=False
        )
        
        # Process through service
        response = await service.process_chat(core_request)
        
        if response.error:
            raise HTTPException(status_code=500, detail=response.error)
            
        return ChatResponse(
            content=response.content,
            session_id=response.session_id,
            metadata=response.metadata
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat processing error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    service: SimaCodeService = Depends(get_simacode_service)
):
    """
    处理聊天流请求，支持确认流程
    按照设计文档实现统一的确认交互体验
    
    Args:
        request: Chat request containing message and optional session ID
        service: SimaCode service instance
        
    Returns:
        Streaming response with chat chunks
    """
    try:
        # 检查是否为确认响应
        if request.message.startswith("CONFIRM_ACTION:"):
            return await handle_confirmation_response(request, service)
        
        # 正常聊天流程
        core_request = CoreChatRequest(
            message=request.message,
            session_id=request.session_id,
            context=request.context,
            stream=True
        )
        
        async def generate_chunks():
            try:
                # 获取流式响应
                response_gen = await service.process_chat(core_request)
                
                if hasattr(response_gen, '__aiter__'):
                    # 流式响应处理
                    session_id = request.session_id or "new"
                    async for chunk in response_gen:
                        # 处理确认请求
                        if chunk.startswith("[confirmation_request]"):
                            confirmation_chunk = await handle_confirmation_request(
                                request.session_id, chunk, service
                            )
                            yield f"data: {confirmation_chunk.model_dump_json()}\n\n"
                            
                            # 注意：不需要在这里等待确认，ReAct引擎会处理等待确认的逻辑
                            # 这里只负责发送确认请求给客户端
                            # confirmation_response = await chat_confirmation_manager.wait_for_confirmation(
                            #     request.session_id
                            # )
                            
                            # 不需要处理确认响应，让ReAct引擎处理
                            # if confirmation_response and confirmation_response.action != "cancel":
                            #     # 发送确认接收消息
                            #     received_chunk = create_confirmation_received_chunk(
                            #         session_id, confirmation_response
                            #     )
                            #     yield f"data: {received_chunk.model_dump_json()}\n\n"
                            #     
                            #     # 注意：不需要再次提交确认，因为ReAct引擎的wait_for_confirmation已经处理了
                            #     # await service.submit_confirmation(confirmation_response)
                            #     
                            #     # 不用continue，让流继续处理后续的数据
                            # else:
                            #     # 取消或超时
                            #     cancel_reason = "用户取消" if confirmation_response and confirmation_response.action == "cancel" else "确认超时"
                            #     cancel_chunk = create_error_chunk(f"任务已取消：{cancel_reason}", session_id, cancel_reason)
                            #     yield f"data: {cancel_chunk.model_dump_json()}\n\n"
                            #     return
                        
                        # 处理常规chunks
                        else:
                            chunk_data = process_regular_chunk(chunk, session_id)
                            yield f"data: {chunk_data.model_dump_json()}\n\n"
                    
                    # 发送完成信号
                    # 尝试获取session信息以生成详细摘要
                    session_info = None
                    try:
                        if session_id and session_id != "new":
                            session_info = await service.get_session_info(session_id)
                    except Exception:
                        pass  # 忽略获取session失败的情况
                    
                    final_chunk = await create_completion_chunk(session_id, session_info, service)
                    yield f"data: {final_chunk.model_dump_json()}\n\n"
                else:
                    # 非流式响应（回退）
                    fallback_chunk = create_content_chunk(
                        response_gen.content, 
                        response_gen.session_id, 
                        finished=True,
                        metadata=response_gen.metadata
                    )
                    yield f"data: {fallback_chunk.model_dump_json()}\n\n"
                    
            except Exception as e:
                logger.error(f"流式处理错误: {e}")
                error_chunk = create_error_chunk(str(e), request.session_id or "error")
                yield f"data: {error_chunk.model_dump_json()}\n\n"
        
        return StreamingResponse(
            generate_chunks(),
            media_type="text/plain",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
        
    except Exception as e:
        logger.error(f"Chat streaming setup error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.websocket("/ws")
async def chat_websocket(
    websocket: WebSocket,
    service: SimaCodeService = Depends(get_simacode_service)
):
    """
    WebSocket endpoint for real-time chat.
    
    Args:
        websocket: WebSocket connection
        service: SimaCode service instance
    """
    await websocket.accept()
    logger.info("WebSocket chat connection established")
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_json()
            
            try:
                # Validate message format
                if "message" not in data:
                    await websocket.send_json({
                        "error": "Missing 'message' field",
                        "type": "error"
                    })
                    continue
                
                # Create core request
                core_request = CoreChatRequest(
                    message=data["message"],
                    session_id=data.get("session_id"),
                    context=data.get("context", {}),
                    stream=False
                )
                
                # Process chat request
                response = await service.process_chat(core_request)
                
                if response.error:
                    await websocket.send_json({
                        "error": response.error,
                        "type": "error",
                        "session_id": response.session_id
                    })
                else:
                    await websocket.send_json({
                        "content": response.content,
                        "session_id": response.session_id,
                        "metadata": response.metadata,
                        "type": "response"
                    })
                    
            except Exception as e:
                logger.error(f"WebSocket message processing error: {e}")
                await websocket.send_json({
                    "error": str(e),
                    "type": "error"
                })
                
    except WebSocketDisconnect:
        logger.info("WebSocket chat connection closed")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.close()
        except:
            pass


# ==================== 确认流程辅助函数 ====================
# 按照设计文档规范实现

async def handle_confirmation_request(
    session_id: str, 
    chunk: str, 
    service: SimaCodeService
) -> StreamingChatChunk:
    """
    处理确认请求chunk - 按照设计文档规范实现
    
    Args:
        session_id: 会话ID
        chunk: 确认请求chunk内容 格式: [confirmation_request]{json_data}
        service: 服务实例
        
    Returns:
        标准化的确认请求StreamingChatChunk
    """
    try:
        # 解析确认请求数据
        confirmation_data_str = chunk[len("[confirmation_request]"):].strip()
        confirmation_data = json.loads(confirmation_data_str)
        
        # 注意：不要重复创建确认请求，因为ReAct引擎已经创建过了
        # 这里只需要格式化确认消息给客户端
        # await chat_confirmation_manager.request_confirmation(
        #     session_id=session_id,
        #     tasks=confirmation_data.get("tasks", []),
        #     timeout_seconds=confirmation_data.get("timeout_seconds", 300)
        # )
        
        # 按照设计文档格式化确认消息
        tasks = confirmation_data.get("tasks", [])
        task_descriptions = []
        for task in tasks:
            task_descriptions.append(f"{task.get('index', '-')} {task.get('description', '未知任务')}")
        
        confirmation_message = f"请确认执行以下{len(tasks)}个任务：\n" + "\n".join(task_descriptions)
        
        # 创建标准化的确认请求chunk
        return StreamingChatChunk(
            chunk=confirmation_message,
            session_id=session_id,
            finished=False,
            chunk_type="confirmation_request",
            confirmation_data=confirmation_data,
            requires_response=True,
            stream_paused=True,
            metadata={
                "total_tasks": len(tasks),
                "risk_level": confirmation_data.get("risk_level", "unknown"),
                "timeout_seconds": confirmation_data.get("timeout_seconds", 300),
                "confirmation_round": confirmation_data.get("confirmation_round", 1)
            }
        )
        
    except Exception as e:
        logger.error(f"Error handling confirmation request: {e}")
        return create_error_chunk(f"确认请求处理错误: {str(e)}", session_id)


async def handle_confirmation_response(
    request: ChatRequest, 
    service: SimaCodeService
) -> StreamingResponse:
    """
    处理确认响应 - 按照设计文档规范实现
    
    Args:
        request: 包含确认响应的聊天请求
        service: 服务实例
        
    Returns:
        流式响应
    """
    try:
        # 解析确认动作 - 按照设计文档格式 CONFIRM_ACTION:action:message
        action_part = request.message[len("CONFIRM_ACTION:"):].strip()
        parts = action_part.split(":", 1)
        action = parts[0].strip()
        user_message = parts[1].strip() if len(parts) > 1 else None
        
        session_id = request.session_id or "unknown"
        
        # 验证动作
        if action not in ["confirm", "modify", "cancel"]:
            raise ValueError(f"无效的确认动作: {action}")
        
        # 提交确认响应
        success = await chat_confirmation_manager.submit_confirmation(
            session_id, action, user_message
        )
        
        async def generate_response():
            if success:
                # 成功响应
                response_chunk = create_confirmation_received_chunk(session_id, action, user_message)
            else:
                # 失败响应
                response_chunk = create_error_chunk(
                    "确认提交失败，可能会话已过期或不存在待确认的请求", 
                    session_id
                )
            
            yield f"data: {response_chunk.model_dump_json()}\n\n"
        
        return StreamingResponse(
            generate_response(),
            media_type="text/plain",
            headers={"Cache-Control": "no-cache"}
        )
        
    except Exception as e:
        logger.error(f"确认响应处理错误: {e}")
        
        async def error_response():
            error_chunk = create_error_chunk(f"确认格式错误: {str(e)}", request.session_id or "error")
            yield f"data: {error_chunk.model_dump_json()}\n\n"
        
        return StreamingResponse(
            error_response(),
            media_type="text/plain",
            headers={"Cache-Control": "no-cache"}
        )


def process_regular_chunk(chunk: str, session_id: str) -> StreamingChatChunk:
    """
    处理常规chunk - 按照设计文档规范实现
    
    Args:
        chunk: chunk内容
        session_id: 会话ID
        
    Returns:
        处理后的StreamingChatChunk
    """
    # 识别chunk类型（基于内容前缀）
    if chunk.startswith("[confirmation_request]"):
        # 🆕 处理确认请求格式的chunk
        try:
            import json
            confirmation_data_str = chunk[len("[confirmation_request]"):]
            confirmation_data = json.loads(confirmation_data_str)
            
            # 创建正确的确认消息，显示实际任务数量
            tasks = confirmation_data.get("tasks", [])
            task_descriptions = []
            for i, task in enumerate(tasks):
                task_descriptions.append(f"{i+1}. {task.get('description', '未知任务')}")
            
            confirmation_message = f"请确认执行以下{len(tasks)}个任务：\n" + "\n".join(task_descriptions)
            
            return StreamingChatChunk(
                chunk=confirmation_message,
                session_id=session_id,
                finished=False,
                chunk_type="confirmation_request",
                confirmation_data=confirmation_data,  # 传递完整的扁平化数据
                requires_response=True,
                stream_paused=True,
                metadata={
                    "total_tasks": len(tasks),
                    "risk_level": confirmation_data.get("risk_level", "unknown"),
                    "timeout_seconds": confirmation_data.get("timeout_seconds", 300),
                    "confirmation_round": confirmation_data.get("confirmation_round", 1)
                }
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse confirmation request chunk: {e}")
            return create_chunk("error", f"确认请求格式错误: {chunk}", session_id)
    elif chunk.startswith("[task_init]"):
        return create_chunk("task_init", chunk[11:].strip(), session_id)
    elif chunk.startswith("[tool_execution]"):
        return create_chunk("tool_output", chunk[16:].strip(), session_id)
    elif chunk.startswith("[status_update]"):
        return create_chunk("status", chunk[15:].strip(), session_id)
    elif chunk.startswith("[task_replanned]"):
        return create_chunk("task_replanned", chunk[16:].strip(), session_id)
    elif chunk.startswith("❌"):
        return create_chunk("error", chunk, session_id)
    else:
        # 默认内容类型
        return create_chunk("content", chunk, session_id)


# ==================== Chunk创建辅助函数 ====================

def create_chunk(chunk_type: str, content: str, session_id: str, **kwargs) -> StreamingChatChunk:
    """创建标准化的StreamingChatChunk"""
    return StreamingChatChunk(
        chunk=content,
        session_id=session_id,
        finished=kwargs.get('finished', False),
        chunk_type=chunk_type,
        metadata=kwargs.get('metadata', {}),
        confirmation_data=kwargs.get('confirmation_data'),
        requires_response=kwargs.get('requires_response', False),
        stream_paused=kwargs.get('stream_paused', False)
    )


def create_content_chunk(content: str, session_id: str, finished: bool = False, metadata: dict = None) -> StreamingChatChunk:
    """创建内容chunk"""
    return create_chunk("content", content, session_id, finished=finished, metadata=metadata or {})


def create_error_chunk(error_message: str, session_id: str, reason: str = None) -> StreamingChatChunk:
    """创建错误chunk"""
    metadata = {"error": True}
    if reason:
        metadata["reason"] = reason
    return create_chunk("error", f"❌ {error_message}", session_id, finished=True, metadata=metadata)


async def create_completion_chunk(session_id: str, session=None, service=None) -> StreamingChatChunk:
    """创建完成chunk"""
    # 如果有session信息，尝试生成详细的任务摘要
    completion_content = "🔍 执行摘要：\n\n📊 最终结果：\n🎉 任务执行完成"
    
    if session and service:
        try:
            # 尝试从react_service生成摘要
            if hasattr(service, 'react_service'):
                completion_content = await service.react_service.generate_task_summary_content(session_id)
        except Exception:
            # 如果生成摘要失败，使用默认消息
            pass
    
    return create_chunk(
        "completion", 
        completion_content, 
        session_id, 
        finished=True, 
        metadata={"stream_completed": True}
    )


def create_confirmation_received_chunk(session_id: str, action: str, user_message: str = None) -> StreamingChatChunk:
    """创建确认接收chunk"""
    message = f"✅ 收到您的反馈: {action}"
    if user_message:
        message += f" - {user_message}"
    
    return create_chunk(
        "confirmation_received",
        message,
        session_id,
        finished=True,
        metadata={
            "action": action,
            "user_message": user_message
        }
    )