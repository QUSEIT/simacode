# SimaCode MCP 长时间运行任务和进度回传增强方案

## 概述

本文档详细描述了 SimaCode MCP 集成架构针对长时间运行任务的问题分析和解决方案，包括异步任务处理、进度回传机制以及与现有 CLI 和 API 接口的集成方案。

## 问题分析

### 当前架构限制

1. **同步执行模型导致的超时问题**
   - `MCPToolWrapper.execute()` 方法使用同步执行模型
   - protocol.py:284 中硬编码 300 秒超时
   - config.py:59 中服务器配置默认 30 秒超时
   - 长时间运行的 MCP 工具会触发超时异常

2. **缺乏进度回传机制**
   - 当前架构只在工具开始和结束时产生结果
   - tool_wrapper.py:375-380 只有简单的开始进度指示器
   - 中间过程无进度反馈

3. **连接管理限制**
   - WebSocket 和 stdio 连接没有针对长时间运行任务的优化
   - 长时间静默可能导致连接断开

## 解决方案架构

### 1. 协议层扩展 - 直接增强 MCPProtocol

基于现有 MCPProtocol 的良好异步基础，直接在 protocol.py 中添加异步工具调用支持：

```python
# src/simacode/mcp/protocol.py 扩展
class MCPProtocol:
    def __init__(self, transport: MCPTransport):
        # 现有初始化代码...

        # 新增：长时间运行任务支持
        self._long_running_tasks: Dict[str, asyncio.Task] = {}
        self._progress_callbacks: Dict[str, List[Callable]] = {}

    async def call_tool_async(
        self,
        tool_name: str,
        arguments: Dict,
        progress_callback: Optional[Callable] = None,
        timeout: Optional[float] = None
    ) -> AsyncGenerator[MCPResult, None]:
        """扩展：异步工具调用，支持进度回传"""

        request_id = self._generate_request_id()

        # 检查服务器是否支持异步调用
        if await self._server_supports_async():
            # 使用新的异步协议
            async for result in self._call_tool_async_protocol(
                request_id, tool_name, arguments, progress_callback, timeout
            ):
                yield result
        else:
            # 回退到标准同步调用
            result = await self.call_method("tools/call", {
                "name": tool_name,
                "arguments": arguments
            })
            yield MCPResult(success=True, content=result)

    async def _call_tool_async_protocol(
        self,
        request_id: str,
        tool_name: str,
        arguments: Dict,
        progress_callback: Optional[Callable],
        timeout: Optional[float]
    ) -> AsyncGenerator[MCPResult, None]:
        """实现异步协议扩展"""

        # 注册进度回调
        if progress_callback:
            if request_id not in self._progress_callbacks:
                self._progress_callbacks[request_id] = []
            self._progress_callbacks[request_id].append(progress_callback)

        try:
            # 发送异步工具调用请求
            request = MCPMessage(
                id=request_id,
                method="tools/call_async",  # 新方法
                params={
                    "name": tool_name,
                    "arguments": arguments,
                    "enable_progress": True,
                    "timeout": timeout or 3600  # 默认1小时
                }
            )

            await self.send_message(request)

            # 等待响应流
            async for message in self._wait_for_async_responses(request_id):
                if message.method == "tools/progress":
                    # 进度通知
                    progress_data = message.params

                    # 调用进度回调
                    if request_id in self._progress_callbacks:
                        for callback in self._progress_callbacks[request_id]:
                            await callback(progress_data)

                    yield MCPResult(
                        success=True,
                        content=progress_data,
                        metadata={"type": "progress", "request_id": request_id}
                    )

                elif message.method == "tools/result":
                    # 最终结果
                    result_data = message.params
                    yield MCPResult(
                        success=True,
                        content=result_data.get("result"),
                        metadata={"type": "final_result", "request_id": request_id}
                    )
                    break

        finally:
            # 清理
            self._progress_callbacks.pop(request_id, None)
```

### 2. 任务管理层 - 统一异步任务管理器

```python
# src/simacode/mcp/async_integration.py
class MCPAsyncTaskManager:
    """统一的异步任务管理器"""

    def __init__(self):
        self.active_tasks: Dict[str, MCPAsyncTask] = {}
        self.task_queues: Dict[str, asyncio.Queue] = {}
        self.executor_pool = asyncio.Semaphore(5)  # 限制并发数

    async def submit_task(
        self,
        task_type: str,
        request: Union[ReActRequest, ChatRequest],
        progress_callback: Optional[Callable] = None
    ) -> str:
        """提交异步任务"""

        task_id = f"{task_type}_{uuid.uuid4().hex[:8]}"

        task = MCPAsyncTask(
            task_id=task_id,
            task_type=task_type,
            request=request,
            progress_callback=progress_callback
        )

        self.active_tasks[task_id] = task
        self.task_queues[task_id] = asyncio.Queue()

        # 启动后台执行
        asyncio.create_task(self._execute_task(task))

        return task_id

    async def get_task_progress_stream(self, task_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        """获取任务进度流"""
        if task_id not in self.task_queues:
            raise ValueError(f"Task {task_id} not found")

        queue = self.task_queues[task_id]

        while True:
            try:
                progress = await asyncio.wait_for(queue.get(), timeout=1.0)
                yield progress

                if progress.get('type') == 'final_result':
                    break

            except asyncio.TimeoutError:
                # 检查任务是否仍在运行
                if task_id not in self.active_tasks:
                    break
                continue
```

### 3. 工具包装器增强 - 智能任务分类

```python
# src/simacode/mcp/tool_wrapper.py 增强
class MCPToolWrapper(Tool):
    async def execute(self, input_data: ToolInput) -> AsyncGenerator[ToolResult, None]:
        """增强的执行方法，自动选择同步/异步模式"""

        # 检测任务特征
        task_classification = self._classify_task_complexity(input_data)

        if task_classification == "long_running":
            # 使用异步执行
            async for result in self._execute_async(input_data):
                yield result
        else:
            # 现有同步执行
            async for result in self._execute_sync(input_data):
                yield result

    def _classify_task_complexity(self, input_data: ToolInput) -> str:
        """智能分类任务复杂度"""

        # 基于工具名称判断
        tool_name_lower = self.original_name.lower()
        long_running_keywords = [
            "download", "upload", "backup", "sync", "process", "analyze",
            "generate", "compile", "build", "train", "convert"
        ]

        if any(keyword in tool_name_lower for keyword in long_running_keywords):
            return "long_running"

        # 基于参数判断
        args_dict = input_data.dict()
        for key, value in args_dict.items():
            if isinstance(value, str):
                # 大文件路径
                if "path" in key.lower() and len(value) > 100:
                    return "long_running"
                # URL 下载
                if "url" in key.lower() and value.startswith(("http://", "https://")):
                    return "long_running"

        return "standard"

    async def _execute_async(self, input_data: ToolInput) -> AsyncGenerator[ToolResult, None]:
        """异步执行模式"""

        # 通过增强的协议调用
        mcp_arguments = self._convert_input_to_mcp_args(input_data)

        async for mcp_result in self.server_manager.call_tool_async(
            self.server_name,
            self.original_name,
            mcp_arguments,
            progress_callback=self._handle_progress_update
        ):
            async for result in self._convert_mcp_result_to_tool_result(
                mcp_result, input_data.execution_id, 0
            ):
                yield result
```

### 4. 服务层集成 - SimaCodeService 扩展

```python
# src/simacode/core/service.py 扩展
class SimaCodeService:
    def __init__(self, config: Config):
        # 现有初始化...
        self.async_task_manager = MCPAsyncTaskManager()

    async def process_react(self, request: ReActRequest) -> ReActResponse:
        """增强 ReAct 处理以支持长时间运行任务"""

        # 检测是否为长时间运行任务
        if self._requires_async_execution(request):
            return await self._process_react_async(request)
        else:
            # 现有同步处理逻辑
            return await self._process_react_sync(request)

    async def _process_react_async(self, request: ReActRequest) -> ReActResponse:
        """异步 ReAct 处理"""

        # 创建异步任务
        task_id = await self.async_task_manager.submit_task(
            task_type="react",
            request=request,
            progress_callback=self._handle_react_progress
        )

        # 在 CLI 模式下，等待任务完成并显示进度
        if self._is_cli_mode():
            async for progress in self.async_task_manager.get_task_stream(task_id):
                # CLI 进度显示
                console.print(f"[blue]Progress:[/blue] {progress.get('message', 'Processing...')}")

                if progress.get('type') == 'final_result':
                    return ReActResponse(
                        result=progress.get('result'),
                        session_id=request.session_id,
                        steps=progress.get('steps', []),
                        metadata=progress.get('metadata', {})
                    )
        else:
            # API 模式返回任务 ID
            return ReActResponse(
                result=f"Task submitted: {task_id}",
                session_id=request.session_id,
                metadata={"async_task_id": task_id, "task_type": "long_running"}
            )
```

## CLI 和 API 接口集成

### CLI 支持 (`simacode chat --react`)

CLI 通过 `SimaCodeService` 自动处理异步任务，在检测到长时间运行任务时显示实时进度：

```bash
$ simacode chat --react "Process large dataset with analysis tool"

🔄 Detected long-running task, switching to async mode...
🚀 Task submitted: react_a1b2c3d4
📈 Progress: Starting analysis... (0%)
📈 Progress: Loading dataset... (20%)
📈 Progress: Processing records... (60%)
📈 Progress: Generating report... (90%)
✅ Task completed successfully!
```

### API 支持

#### 现有端点增强

1. **`/api/v1/react/execute`** - 自动检测并处理长时间运行任务
2. **`/api/v1/chat/stream`** - 支持工具执行进度流式回传

#### 新增端点

```python
# 明确的异步端点
@router.post("/api/v1/react/execute/async")
async def execute_react_task_async(request: ReActRequest) -> AsyncTaskResponse

# 异步任务状态查询
@router.get("/api/v1/tasks/{task_id}")
async def get_task_status(task_id: str) -> TaskStatusResponse

# WebSocket 进度流
@router.websocket("/api/v1/react/ws/async")
async def react_websocket_async(websocket: WebSocket)
```

## 配置增强

### MCP 服务器配置扩展

```yaml
# config/mcp_servers.yaml
servers:
  example_server:
    name: "example_server"
    timeout: 30  # 标准操作超时

    # 长时间运行任务配置
    long_running_tasks:
      enabled: true
      max_execution_time: 3600  # 1小时
      progress_interval: 5      # 每5秒报告进度
      heartbeat_interval: 30    # 保活间隔

    # 任务分类
    task_classifications:
      quick: { max_time: 30 }
      medium: { max_time: 300 }
      long: { max_time: 3600 }
```

## 实施路径

### 阶段 1：协议层扩展（1-2 周）
1. ✅ 直接在 `MCPProtocol` 中添加 `call_tool_async` 方法
2. ✅ 扩展消息路由以支持进度通知
3. ✅ 保持现有 API 完全兼容

**具体任务：**
- [ ] 在 `protocol.py` 中实现 `call_tool_async` 方法
- [ ] 增强 `_message_receiver_loop` 支持进度通知路由
- [ ] 添加服务器异步能力检测机制
- [ ] 编写协议层单元测试

### 阶段 2：服务层集成（1 周）
1. ✅ 在 `SimaCodeService` 中集成异步任务管理器
2. ✅ 添加智能任务分类逻辑
3. ✅ 更新 CLI 和 API 路由

**具体任务：**
- [ ] 实现 `MCPAsyncTaskManager` 类
- [ ] 在 `MCPToolWrapper` 中添加智能任务分类
- [ ] 扩展 `SimaCodeService` 支持异步模式检测
- [ ] 更新 API 路由支持异步任务

### 阶段 3：用户体验优化（1 周）
1. ✅ CLI 进度显示优化
2. ✅ WebSocket 实时进度流
3. ✅ 任务状态查询接口

**具体任务：**
- [ ] 实现 CLI 富文本进度显示
- [ ] 添加 WebSocket 异步端点
- [ ] 实现任务状态查询和管理接口
- [ ] 添加任务取消和恢复功能

## 向后兼容性保证

1. **现有 API 零变更**：所有现有接口保持完全兼容
2. **渐进式增强**：智能检测任务类型，无需手动配置
3. **配置向下兼容**：新配置项都有合理默认值
4. **错误回退**：异步模式失败时自动回退到同步模式

## 性能和监控

### 性能优化
- 并发任务数量限制（默认 5 个）
- 任务队列管理和内存回收
- 连接池优化和重用

### 监控指标
- 任务执行时间分布
- 异步/同步模式使用比例
- 进度回传频率和效率
- 连接稳定性统计

## 测试策略

1. **单元测试**：协议层和任务管理器核心逻辑
2. **集成测试**：CLI 和 API 端到端流程
3. **压力测试**：多任务并发和长时间运行场景
4. **兼容性测试**：确保现有功能不受影响

## 总结

本方案通过直接扩展现有 `MCPProtocol` 类，实现了对长时间运行任务的完整支持，包括：

- **无缝集成**：基于现有架构进行最小化扩展
- **智能检测**：自动识别任务类型并选择最佳执行模式
- **实时反馈**：完整的进度回传和状态监控
- **向后兼容**：现有代码和接口零变更
- **统一体验**：CLI 和 API 使用相同的底层机制

该方案为 SimaCode 的 MCP 集成提供了强大的异步任务处理能力，显著改善了用户体验，特别是在处理大型文件、网络操作和复杂计算任务时。