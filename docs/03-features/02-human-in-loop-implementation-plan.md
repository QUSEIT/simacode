# Human in Loop 特性实现方案

## 📋 概述

基于 `docs/features/01-human-in-loop.md` 的设计需求，本文档详细描述了在 SimaCode ReAct 引擎中实现人工确认机制的完整方案。该特性允许用户在 AI 执行任务前预览、确认或修改执行计划，提高系统的可控性和安全性。

## 🎯 需求分析

### 核心需求
- 在 `.simacode/config.yaml` 中添加 `react.confirm_by_human` 配置项，默认为 `false`
- 当启用时，在 ReAct 引擎规划出子任务后（`engine.py:266` 行开始），暂停执行并等待用户确认
- 支持用户查看任务详情、确认执行、修改计划或取消执行
- 保持与现有流程的兼容性

### 技术挑战
- **异步流程控制**：需要暂停 AsyncGenerator，等待外部输入
- **多客户端支持**：CLI 直接交互 vs API 请求-响应模式
- **状态持久化**：会话状态需要保存等待确认的信息
- **超时机制**：避免无限等待导致资源泄漏

## 🔧 技术方案

### 方案A：渐进式实施（推荐） ⭐

采用分阶段实施策略，确保每个阶段都能独立工作并带来用户价值。

#### 阶段1：基础架构（MVP）

**1. 配置扩展**

在 `src/simacode/config.py` 中扩展配置结构：

```python
class ReactConfig(BaseModel):
    """ReAct 引擎配置模型"""
    
    confirm_by_human: bool = Field(
        default=False, 
        description="Enable human confirmation before task execution"
    )
    confirmation_timeout: int = Field(
        default=300, 
        description="Confirmation timeout in seconds"
    )
    allow_task_modification: bool = Field(
        default=True, 
        description="Allow users to modify tasks during confirmation"
    )
    auto_confirm_safe_tasks: bool = Field(
        default=False,
        description="Auto-confirm tasks that are considered safe"
    )

# 集成到主配置
class Config(BaseModel):
    # ... 现有字段 ...
    react: ReactConfig = Field(
        default_factory=ReactConfig,
        description="ReAct engine configuration"
    )
```

**2. 数据结构定义**

在 `src/simacode/api/models.py` 中添加确认相关模型：

```python
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
```

**3. 引擎状态扩展**

在 `src/simacode/react/engine.py` 中扩展状态枚举：

```python
class ReActState(Enum):
    """ReAct engine execution state."""
    IDLE = "idle"
    REASONING = "reasoning"
    PLANNING = "planning"
    AWAITING_CONFIRMATION = "awaiting_confirmation"  # 🆕 新增状态
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    REPLANNING = "replanning"
    COMPLETED = "completed"
    FAILED = "failed"
```

**4. 确认管理器**

创建 `src/simacode/react/confirmation_manager.py`：

```python
class ConfirmationManager:
    """管理任务确认流程"""
    
    def __init__(self):
        self.pending_confirmations: Dict[str, ConfirmationStatus] = {}
        self.confirmation_callbacks: Dict[str, asyncio.Event] = {}
    
    async def request_confirmation(
        self, 
        session_id: str, 
        tasks: List[Task],
        timeout_seconds: int = 300
    ) -> TaskConfirmationRequest:
        """发起确认请求"""
        
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
        
        try:
            # 等待确认响应或超时
            await asyncio.wait_for(
                self.confirmation_callbacks[session_id].wait(),
                timeout=timeout_seconds
            )
            
            # 返回用户响应
            confirmation = self.pending_confirmations.get(session_id)
            if confirmation and confirmation.user_response:
                return confirmation.user_response
            else:
                raise TimeoutError("Confirmation timeout")
                
        except asyncio.TimeoutError:
            # 超时处理
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
        
        if session_id not in self.pending_confirmations:
            return False
        
        # 更新确认状态
        confirmation = self.pending_confirmations[session_id]
        confirmation.user_response = response
        confirmation.status = response.action
        
        # 触发等待的协程
        if session_id in self.confirmation_callbacks:
            self.confirmation_callbacks[session_id].set()
        
        return True
    
    def _handle_confirmation_timeout(self, session_id: str):
        """处理确认超时"""
        if session_id in self.pending_confirmations:
            self.pending_confirmations[session_id].status = "timeout"
    
    def _cleanup_confirmation(self, session_id: str):
        """清理确认相关资源"""
        self.pending_confirmations.pop(session_id, None)
        self.confirmation_callbacks.pop(session_id, None)
```

**5. 引擎逻辑修改**

修改 `src/simacode/react/engine.py` 中的 `_reasoning_and_planning_phase` 方法：

```python
async def _reasoning_and_planning_phase(self, session: ReActSession) -> AsyncGenerator[Dict[str, Any], None]:
    """Execute the reasoning and planning phase."""
    session.update_state(ReActState.REASONING)
    yield self._create_status_update(session, "Analyzing user input and reasoning about approach")
    
    # ... 现有规划逻辑 ...
    
    # Plan tasks
    tasks = await self.task_planner.plan_tasks(planning_context)
    session.tasks = tasks
    
    # ... 现有任务摘要逻辑 ...
    
    if tasks:
        # 🆕 检查是否需要人工确认
        if self._should_request_confirmation(session, tasks):
            yield from self._handle_human_confirmation(session, tasks)
        
        # 原有的任务计划输出
        yield {
            "type": "task_plan",
            "content": "Task plan created",
            "session_id": session.id,
            "tasks": [task.to_dict() for task in tasks]
        }
        
        # ... 现有 task_init 逻辑 ...

def _should_request_confirmation(self, session: ReActSession, tasks: List[Task]) -> bool:
    """判断是否需要请求人工确认"""
    
    # 检查配置
    config = getattr(self, 'config', None)
    if not config or not getattr(config, 'react', None):
        return False
    
    react_config = config.react
    if not react_config.confirm_by_human:
        return False
    
    # 检查是否有需要确认的任务
    if not tasks:
        return False
    
    # 检查是否有危险任务（可选的智能判断）
    if react_config.auto_confirm_safe_tasks:
        dangerous_tasks = self._identify_dangerous_tasks(tasks)
        return len(dangerous_tasks) > 0
    
    return True

async def _handle_human_confirmation(
    self, 
    session: ReActSession, 
    tasks: List[Task]
) -> AsyncGenerator[Dict[str, Any], None]:
    """处理人工确认流程"""
    
    session.update_state(ReActState.AWAITING_CONFIRMATION)
    
    # 获取配置的超时时间
    config = getattr(self, 'config', None)
    timeout = getattr(config.react, 'confirmation_timeout', 300) if config else 300
    
    # 创建确认管理器（如果不存在）
    if not hasattr(self, 'confirmation_manager'):
        from .confirmation_manager import ConfirmationManager
        self.confirmation_manager = ConfirmationManager()
    
    try:
        # 发起确认请求
        confirmation_request = await self.confirmation_manager.request_confirmation(
            session.id, tasks, timeout
        )
        
        # 发送确认请求给客户端
        yield {
            "type": "confirmation_request",
            "content": f"规划了 {len(tasks)} 个任务，请确认是否执行",
            "session_id": session.id,
            "confirmation_request": confirmation_request.model_dump(),
            "tasks_summary": self._create_tasks_summary(tasks)
        }
        
        # 等待用户确认
        yield self._create_status_update(session, f"等待用户确认执行计划（超时：{timeout}秒）")
        
        confirmation_response = await self.confirmation_manager.wait_for_confirmation(
            session.id, timeout
        )
        
        # 处理用户响应
        await self._process_confirmation_response(session, confirmation_response)
        
    except TimeoutError:
        yield {
            "type": "confirmation_timeout",
            "content": "用户确认超时，取消任务执行",
            "session_id": session.id
        }
        session.update_state(ReActState.FAILED)
        raise ReActError("User confirmation timeout")
    except Exception as e:
        yield {
            "type": "confirmation_error", 
            "content": f"确认过程出现错误：{str(e)}",
            "session_id": session.id
        }
        raise

async def _process_confirmation_response(
    self, 
    session: ReActSession, 
    response: TaskConfirmationResponse
):
    """处理确认响应"""
    
    if response.action == "cancel":
        session.update_state(ReActState.FAILED)
        raise ReActError("User cancelled task execution")
    
    elif response.action == "modify":
        if response.modified_tasks:
            # 用户修改了任务，更新session中的任务列表
            modified_tasks = []
            for task_dict in response.modified_tasks:
                task = Task.from_dict(task_dict)
                modified_tasks.append(task)
            session.tasks = modified_tasks
            session.add_log_entry(f"Tasks modified by user: {len(modified_tasks)} tasks")
        else:
            session.add_log_entry("User requested modification but no modified tasks provided")
    
    elif response.action == "confirm":
        session.add_log_entry("Tasks confirmed by user")
    
    # 恢复执行状态
    session.update_state(ReActState.PLANNING)

def _create_tasks_summary(self, tasks: List[Task]) -> Dict[str, Any]:
    """创建任务摘要用于确认界面"""
    
    return {
        "total_tasks": len(tasks),
        "tasks": [
            {
                "index": i + 1,
                "description": task.description,
                "tool": task.tool_name,
                "type": task.type.value,
                "priority": task.priority,
                "expected_outcome": task.expected_outcome
            }
            for i, task in enumerate(tasks)
        ],
        "estimated_duration": "未知",  # 可以后续添加估算逻辑
        "risk_level": self._assess_task_risk_level(tasks)
    }

def _assess_task_risk_level(self, tasks: List[Task]) -> str:
    """评估任务风险等级"""
    
    # 简单的风险评估逻辑
    dangerous_tools = {"file_write", "bash", "system_command"}
    
    for task in tasks:
        if task.tool_name in dangerous_tools:
            return "high"
    
    return "low"
```

**6. CLI 集成**

修改 `src/simacode/cli.py` 中的 ReAct 处理逻辑：

```python
async def _handle_react_mode(simacode_service: SimaCodeService, message: Optional[str], interactive: bool, session_id: Optional[str]) -> None:
    """Handle ReAct mode for intelligent task planning and execution."""
    console.print("[bold green]🤖 ReAct Engine Activated[/bold green]")
    console.print("[dim]Intelligent task planning and execution enabled[/dim]\n")
    
    try:
        if not interactive and message:
            # Single message mode with ReAct - use streaming for better UX
            request = ReActRequest(task=message, session_id=session_id)
            
            console.print(f"[bold yellow]🔄 Processing:[/bold yellow] {message}\n")
            
            final_result = None
            step_count = 0
            
            async for update in await simacode_service.process_react(request, stream=True):
                step_count += 1
                update_type = update.get("type", "unknown")
                content = update.get("content", "")
                
                if update_type == "status_update":
                    console.print(f"[dim]• {content}[/dim]")
                elif update_type == "confirmation_request":
                    # 🆕 处理确认请求
                    await _handle_confirmation_request(update, simacode_service)
                elif update_type == "confirmation_timeout":
                    console.print(f"[red]⏰ {content}[/red]")
                elif update_type == "conversational_response":
                    # 对话性回复，直接显示内容
                    console.print(f"[white]{content}[/white]")
                    final_result = content
                elif update_type == "sub_task_result" or update_type == "final_result":
                    final_result = content
                    console.print(f"[bold green]✅ {content}[/bold green]")
                elif update_type == "error":
                    console.print(f"[red]❌ {content}[/red]")
                    break
                    
            if final_result:
                console.print(f"\n[bold green]🎉 Final Result:[/bold green]\n{final_result}")
        else:
            # Interactive mode with confirmation support
            # ... 现有交互模式逻辑 + 确认处理 ...

async def _handle_confirmation_request(update: Dict[str, Any], simacode_service: SimaCodeService):
    """处理确认请求"""
    
    confirmation_request = update.get("confirmation_request", {})
    tasks_summary = update.get("tasks_summary", {})
    session_id = update.get("session_id")
    
    # 显示任务计划
    console.print(f"\n[bold yellow]📋 任务执行计划确认[/bold yellow]")
    console.print(f"会话ID: {session_id}")
    console.print(f"计划任务数: {tasks_summary.get('total_tasks', 0)}")
    console.print(f"风险等级: {tasks_summary.get('risk_level', 'unknown')}")
    console.print()
    
    # 显示任务详情
    tasks = tasks_summary.get("tasks", [])
    for task in tasks:
        console.print(f"[cyan]{task['index']}.[/cyan] {task['description']}")
        console.print(f"   工具: {task['tool']} | 优先级: {task['priority']}")
        console.print(f"   预期结果: {task['expected_outcome']}")
        console.print()
    
    # 用户选择
    choices = ["确认执行", "修改计划", "取消执行"]
    choice = Prompt.ask(
        "请选择操作",
        choices=["1", "2", "3"],
        default="1"
    )
    
    # 构建响应
    if choice == "1":
        response = TaskConfirmationResponse(
            session_id=session_id,
            action="confirm"
        )
    elif choice == "2":
        # 简化版修改 - 可以后续扩展为更复杂的交互
        user_message = Prompt.ask("请描述需要如何修改计划", default="")
        response = TaskConfirmationResponse(
            session_id=session_id,
            action="modify",
            user_message=user_message
        )
    else:  # choice == "3"
        response = TaskConfirmationResponse(
            session_id=session_id,
            action="cancel"
        )
    
    # 提交确认响应
    if hasattr(simacode_service, 'submit_confirmation'):
        simacode_service.submit_confirmation(response)
    else:
        # 通过引擎的确认管理器提交
        if hasattr(simacode_service.react_service.react_engine, 'confirmation_manager'):
            simacode_service.react_service.react_engine.confirmation_manager.submit_confirmation(
                session_id, response
            )
```

**7. 配置文件更新**

更新 `config/default.yaml`：

```yaml
# ... 现有配置 ...

# ReAct 引擎配置
react:
  confirm_by_human: false  # 默认禁用人工确认
  confirmation_timeout: 300  # 确认超时时间（秒）
  allow_task_modification: true  # 允许用户修改任务
  auto_confirm_safe_tasks: false  # 自动确认安全任务
```

#### 阶段2：交互增强（后续实施）

- API 模式下的确认支持
- Web UI 确认界面
- 任务修改的图形化界面
- 更智能的风险评估

#### 阶段3：高级功能（长期规划）

- 执行过程中的人工干预
- 逐任务确认模式
- 基于历史的智能推荐
- 确认模板和预设

### 方案B：简化实施

如果时间和资源有限，可以采用简化方案：

1. **仅支持 CLI 模式**：API 模式暂时跳过人工确认
2. **固定确认选项**：只支持"确认"和"取消"，不支持修改
3. **简化配置**：只保留 `confirm_by_human` 开关

## 🎯 实施计划

### 推荐实施顺序

1. **配置层** (30min)
   - 扩展配置模型
   - 更新 `default.yaml`

2. **数据结构** (45min)
   - 定义确认相关的 Pydantic 模型
   - 扩展 `ReActState` 枚举

3. **确认管理器** (60min)
   - 实现 `ConfirmationManager` 类
   - 处理确认状态和超时

4. **引擎逻辑** (90min)
   - 修改 `_reasoning_and_planning_phase` 方法
   - 添加确认判断和处理逻辑

5. **CLI 集成** (60min)
   - 实现确认请求的命令行交互
   - 友好的任务展示界面

6. **测试验证** (45min)
   - 创建测试用例
   - 验证不同配置下的行为

**总预估时间**: 5.5 小时

### 测试用例

```python
# 测试用例示例
async def test_human_confirmation_enabled():
    """测试启用人工确认时的流程"""
    config = Config(react=ReactConfig(confirm_by_human=True))
    # ... 测试逻辑

async def test_confirmation_timeout():
    """测试确认超时场景"""
    # ... 测试逻辑

async def test_task_modification():
    """测试用户修改任务场景"""
    # ... 测试逻辑
```

## 📊 预期效果

### 功能效果
- ✅ 用户可以在任务执行前预览和确认计划
- ✅ 支持取消危险操作
- ✅ 可配置启用/禁用
- ✅ 保持现有功能的完全兼容性

### 性能影响
- 🟢 **禁用时无影响**：默认配置下性能无变化
- 🟡 **启用时轻微延迟**：增加确认交互时间
- 🟢 **资源消耗低**：确认管理器内存占用很小

### 用户体验
- 🎯 **透明度提升**：用户清楚了解AI要执行的操作
- 🛡️ **安全性增强**：避免意外的危险操作
- 🎨 **灵活性提高**：支持用户自定义修改计划

## ⚠️ 风险评估

### 技术风险
- 🟡 **中等复杂度**：涉及异步流程控制，需要仔细测试
- 🟢 **向后兼容**：默认禁用，不影响现有功能
- 🟡 **状态管理**：需要正确处理会话状态和超时

### 维护风险
- 🟢 **代码隔离性好**：确认逻辑相对独立
- 🟢 **配置驱动**：可以快速禁用功能
- 🟡 **多模式支持**：CLI 和 API 模式需要不同处理

### 用户体验风险
- 🟡 **学习成本**：用户需要理解新的确认流程
- 🟡 **操作中断**：可能降低自动化程度
- 🟢 **可选功能**：用户可以选择是否启用

## 🔄 后续扩展

### 短期扩展（1-2月）
- API 模式的确认支持
- 更丰富的任务修改界面
- 基于任务类型的风险评估

### 中期扩展（3-6月）
- Web UI 确认界面
- 执行过程中的人工干预
- 确认历史和统计

### 长期扩展（6月+）
- 智能推荐修改
- 基于机器学习的风险评估
- 多用户协作确认

## 📚 相关文档

- [ReAct 引擎架构文档](../architectures/)
- [配置管理文档](./02-conversation-context-management.md)
- [API 设计文档](../api-usage-examples.md)
- [测试指南](../tests/)

---

**文档版本**: 1.0  
**创建时间**: 2025-08-04  
**最后更新**: 2025-08-04  
**作者**: Claude Code Assistant