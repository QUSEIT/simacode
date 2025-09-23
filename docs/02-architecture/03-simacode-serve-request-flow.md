# SimaCode Serve 模式：用户请求到MCP工具调用流程

本文档详细描述了 SimaCode serve 模式下，从接收用户HTTP请求到调用MCP工具的完整工作流程。

## 概述

SimaCode serve 模式提供HTTP API服务，支持流式响应。当用户提交会触发MCP工具执行的请求时，系统会经过16个主要步骤，涉及API路由、服务层、ReAct引擎、工具执行等多个层次的处理。

## 完整流程图

```
HTTP Request → API Router → Core Service → ReAct Engine → MCP Tool
     ↓              ↓            ↓            ↓            ↓
 chat.py      service.py   react_service.py  engine.py  tool_wrapper.py
```

## 详细流程分析

### 1. HTTP请求接收
📍 **文件**: `src/simacode/api/routes/chat.py`
- **函数**: `chat_stream()` (L81-180)
- **作用**: 接收POST请求到 `/api/v1/chat/stream`
- **处理**: 解析`ChatRequest`，提取用户消息和context参数

### 2. API路由处理
📍 **文件**: `src/simacode/api/routes/chat.py`
- **函数**: `generate_chunks()` (L109-180) - 异步生成器
- **作用**: 创建`CoreChatRequest`对象
- **调用**: `service.process_chat(core_request)` (L112)

### 3. 核心服务层
📍 **文件**: `src/simacode/core/service.py`
- **函数**: `process_chat()` (L198-251)
- **作用**: 检查处理模式，默认使用ReAct引擎
- **调用**: `_process_with_react_engine(request)` (L243)

### 4. ReAct引擎路由
📍 **文件**: `src/simacode/core/service.py`
- **函数**: `_process_with_react_engine()` (L293-331)
- **作用**: 创建`ReActRequest`对象
- **调用**: 流式处理时调用`_stream_task_response(react_request)` (L309)

### 5. 任务流式响应
📍 **文件**: `src/simacode/core/service.py`
- **函数**: `_stream_task_response()` (L362-418)
- **调用**: `process_react(react_request, stream=True)` (L365)

### 6. ReAct核心处理
📍 **文件**: `src/simacode/core/service.py`
- **函数**: `process_react()` (L472-519)
- **作用**: 检查是否需要异步执行
- **调用**: 同步处理时调用`_process_react_sync(request, stream)` (L511)

### 7. ReAct同步流处理
📍 **文件**: `src/simacode/core/service.py`
- **函数**: `_process_react_sync()` (L668-720)
- **调用**: 流式模式时调用`_stream_react_response(request)` (L681)

### 8. ReAct流式响应生成
📍 **文件**: `src/simacode/core/service.py`
- **函数**: `_stream_react_response()` (L441-470)
- **调用**: `react_service.process_user_request()` (L446-451)

### 9. ReAct服务处理
📍 **文件**: `src/simacode/services/react_service.py`
- **函数**: `process_user_request()` (L119-204)
- **作用**: 获取或创建会话，合并context参数
- **调用**: `react_engine.process_user_input()` (L179)

### 10. ReAct引擎主流程
📍 **文件**: `src/simacode/react/engine.py`
- **函数**: `process_user_input()` (L184-283)
- **作用**: 执行ReAct三个阶段：推理规划 → 执行评估 → 最终评估
- **调用**: `_execution_and_evaluation_phase(session)` (L232)

### 11. 执行评估阶段
📍 **文件**: `src/simacode/react/engine.py`
- **函数**: `_execution_and_evaluation_phase()` (L388-444)
- **作用**: 根据执行模式选择任务执行策略
- **调用**: `_execute_single_task(session, task)` (L473, L504, L523)

### 12. 单任务执行 ⭐ **MCP工具调用点**
📍 **文件**: `src/simacode/react/engine.py`
- **函数**: `_execute_single_task()` (L913-1070)
- **关键点**:
  - **L915**: `logger.info("EXECUTESINGLETASK {task}")`
  - **L948-958**: 调用`execute_tool()` - **MCP工具在这里被调用**
  - **L962-972**: `🔄 [ENGINE_TOOL_RESULT]` DEBUG日志记录所有ToolResult
  - **L975-977**: MCP progress检测条件
  - **L980-989**: `🔍 [ENGINE_MCP_DETECT]` DEBUG日志 + MCP progress处理

### 13. 工具执行层
📍 **文件**: `src/simacode/tools/base.py`
- **函数**: `execute_tool()` (L471-530)
- **作用**: 解析工具命名空间，路由到MCP工具
- **调用**: MCP Tool Wrapper

### 14. MCP工具包装层
📍 **文件**: `src/simacode/mcp/tool_wrapper.py`
- **函数**: `execute()` (L517-577)
- **关键处理**:
  - **L773-807**: MCP progress消息转换 + `🔄 [MCP_PROGRESS_CONVERT]` DEBUG日志
  - **L813-836**: MCP成功结果转换 + `✅ [MCP_SUCCESS_CONVERT]` DEBUG日志

### 15. MCP协议层
📍 **文件**: `src/simacode/mcp/protocol.py`
- **函数**: `call_tool_async()` (L384-493)
- **关键处理**:
  - **L448-461**: 处理`tools/progress`消息 + `🔄 [TOOLS_PROGRESS]` DEBUG日志

### 16. 最终MCP工具执行
📍 **文件**: `tools/mcp_ticmaker_async_stdio_server.py`
- **函数**: 具体的MCP工具函数 (如`create_interactive_course_async`)
- **关键功能**:
  - **L221-248**: `_send_mcp_progress()` - 发送progress消息的起始点

## Context参数传递

在整个流程中，用户提交的`context`参数经过以下传递：

1. **HTTP请求** → `ChatRequest.context`
2. **核心服务** → `CoreChatRequest.context` → `ReActRequest.context`
3. **ReAct服务** → `session.metadata["context"]`
4. **ReAct引擎** → `session_context.metadata_context`
5. **MCP工具** → `_session_context` (如果工具支持)

## 关键调试日志标记

| 标记 | 位置 | 作用 |
|------|------|------|
| `"EXECUTESINGLETASK {task}"` | engine.py:915 | 任务执行开始 |
| `🔄 [ENGINE_TOOL_RESULT]` | engine.py:962 | 所有ToolResult记录 |
| `🔍 [ENGINE_MCP_DETECT]` | engine.py:980 | MCP progress检测 |
| `🔄 [MCP_PROGRESS_CONVERT]` | tool_wrapper.py:780 | MCP progress转换 |
| `🔄 [TOOLS_PROGRESS]` | protocol.py:428 | MCP协议层progress处理 |

## 流程特点

1. **异步流式处理**: 整个流程支持实时流式响应
2. **分层架构**: API → 服务 → 引擎 → 工具的清晰分层
3. **上下文传递**: context参数在每一层都被正确传递
4. **错误处理**: 每一层都有相应的错误处理机制
5. **调试支持**: 关键节点都有详细的DEBUG日志

这个流程确保了从HTTP API到MCP工具的完整数据传递，支持上下文参数和进度消息的实时处理。