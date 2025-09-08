# 修复确认请求 chunk_type 问题的方案

## 问题描述
在 simacode serve API 模式中，发送到客户端等待用户确认的消息的 chunk_type 为 `content`，应该是 `confirmation_request`。

## 根本原因
1. ReAct Engine 正确发送 `{"type": "confirmation_request", ...}` 
2. Service Layer (`service.py:358`) 在处理确认请求时，只返回 `content` 字符串，丢失了类型信息
3. Chat Route 的 `process_regular_chunk` 将所有常规内容默认设置为 `chunk_type="content"`

## 修改方案

### 方案一：修改 Service Layer 的确认请求处理（推荐）

在 `src/simacode/core/service.py` 的 `_stream_task_response` 方法中：

```python
async def _stream_task_response(self, react_request: ReActRequest) -> AsyncGenerator[str, None]:
    """生成任务性流式响应"""
    try:
        async for update in await self.process_react(react_request, stream=True):
            update_type = update.get("type", "")
            content = update.get("content", "")
            
            if update_type == "conversational_response":
                yield content
            elif update_type == "final_result":
                yield content
            elif update_type == "confirmation_request":
                # 🆕 保持确认请求的完整结构信息
                import json
                confirmation_data = {
                    "type": "confirmation_request",
                    "content": content,
                    "session_id": update.get("session_id"),
                    "confirmation_request": update.get("confirmation_request"),
                    "tasks_summary": update.get("tasks_summary"),
                    "confirmation_round": update.get("confirmation_round")
                }
                yield f"[confirmation_request]{json.dumps(confirmation_data)}"
            elif update_type == "task_init":
                yield f"[task_init] {content}"
            elif update_type in ["tool_execution", "status_update"]:
                yield f"[{update_type}] {content}"
            elif update_type == "error":
                yield f"❌ {content}"
                
    except Exception as e:
        logger.error(f"Error in task streaming: {str(e)}")
        yield f"Error: {str(e)}"
```

### 方案二：修改 Chat Route 的 chunk 处理（备选）

在 `src/simacode/api/routes/chat.py` 的 `process_regular_chunk` 方法中：

```python
def process_regular_chunk(chunk: str, session_id: str) -> StreamingChatChunk:
    """处理常规chunk - 按照设计文档规范实现"""
    
    # 🆕 检查是否为确认请求格式的chunk
    if chunk.startswith("[confirmation_request]{"):
        try:
            import json
            confirmation_data_str = chunk[len("[confirmation_request}"):]
            confirmation_data = json.loads(confirmation_data_str)
            
            return StreamingChatChunk(
                chunk=confirmation_data.get("content", ""),
                session_id=session_id,
                finished=False,
                chunk_type="confirmation_request",
                confirmation_data=confirmation_data.get("confirmation_request", {}),
                requires_response=True,
                stream_paused=True,
                metadata={
                    "tasks_summary": confirmation_data.get("tasks_summary", {}),
                    "confirmation_round": confirmation_data.get("confirmation_round", 1)
                }
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"Failed to parse confirmation request chunk: {e}")
            return create_chunk("error", f"确认请求格式错误: {chunk}", session_id)
    
    # 其他chunk类型的处理保持不变
    if chunk.startswith("[task_init]"):
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
        return create_chunk("content", chunk, session_id)
```

## 推荐方案
**推荐使用方案一**，因为：
1. 问题的根源在于 Service Layer 丢失了类型信息
2. 修改 Service Layer 更符合数据流向，保持各层职责清晰
3. 不需要在 Chat Route 中重新解析JSON结构

## 实施步骤
1. 修改 `src/simacode/core/service.py` 中的 `_stream_task_response` 方法
2. 测试确认请求的完整流程
3. 验证客户端收到的 chunk_type 为 `confirmation_request`

## 验证方法
使用提供的 JavaScript 客户端测试代码，确认：
1. 客户端收到的确认请求 chunk_type 为 `confirmation_request`
2. confirmation_data 字段包含完整的任务信息
3. 用户确认后流程能正常继续