# SimaCode 核心架构与主要流程分析 (Python版本)

## 项目概览

SimaCode 是基于 ClaudeX 架构设计的 Python 版本 AI 编程助手，使用 Textual 作为终端 UI 框架，主要支持 Deepseek 和 oneapi/newapi 等符合 OpenAI 接口标准的 AI 提供商。

## 技术栈映射与选择

### 从 Node.js 到 Python 的转换

| ClaudeX (Node.js) | SimaCode (Python) | 说明 |
|-------------------|-------------------|------|
| TypeScript | Python 3.10+ (Type Hints) | 静态类型支持 |
| Ink (React Terminal) | Textual | 现代 TUI 框架 |
| Commander.js | Click | CLI 参数解析 |
| Zod | Pydantic | 数据验证和序列化 |
| Lodash | itertools + stdlib | 工具函数库 |
| Anthropic SDK | OpenAI SDK | AI 服务集成 |
| npm/Bun | Poetry | 包管理工具 |
| ES Modules | Python Packages | 模块系统 |
| JSON Schema | Pydantic Models | 数据模式定义 |

### 核心技术栈

- **运行时**: Python 3.10+
- **包管理**: Poetry
- **UI 框架**: Textual (Python TUI)
- **CLI 框架**: Click
- **数据验证**: Pydantic
- **AI 集成**: OpenAI SDK (兼容 Deepseek/oneapi)
- **异步处理**: asyncio
- **配置管理**: YAML/TOML + Pydantic
- **HTTP 客户端**: httpx/aiohttp
- **MCP 协议**: mcp (Python SDK)

## 项目结构

```
simacode/
├── simacode/
│   ├── __init__.py
│   ├── main.py                    # 主入口点
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── commands.py            # Click 命令定义
│   │   ├── parsers.py             # 参数解析器
│   │   └── subcommands/           # 子命令实现
│   │       ├── config.py
│   │       ├── mcp.py
│   │       └── tools.py
│   ├── repl/
│   │   ├── __init__.py
│   │   ├── app.py                 # Textual REPL 应用
│   │   ├── widgets/               # UI 组件
│   │   │   ├── __init__.py
│   │   │   ├── message_list.py    # 消息列表组件
│   │   │   ├── input_widget.py    # 输入组件
│   │   │   ├── permission_dialog.py # 权限对话框
│   │   │   └── tool_status.py     # 工具状态显示
│   │   ├── handlers.py            # 事件处理器
│   │   └── themes.py              # UI 主题
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── base.py                # 工具基类和接口
│   │   ├── manager.py             # 工具管理器
│   │   ├── registry.py            # 工具注册表
│   │   └── implementations/       # 具体工具实现
│   │       ├── __init__.py
│   │       ├── bash_tool.py       # Bash 执行工具
│   │       ├── file_tools.py      # 文件操作工具
│   │       ├── search_tools.py    # 搜索工具
│   │       ├── agent_tool.py      # 代理工具
│   │       └── memory_tools.py    # 内存管理工具
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── providers/             # AI 提供商实现
│   │   │   ├── __init__.py
│   │   │   ├── base.py            # 提供商基类
│   │   │   ├── deepseek.py        # Deepseek 集成
│   │   │   ├── oneapi.py          # OneAPI 集成
│   │   │   └── factory.py         # 提供商工厂
│   │   ├── models.py              # AI 模型定义
│   │   ├── streaming.py           # 流式响应处理
│   │   └── cost_tracker.py        # 成本追踪
│   ├── config/
│   │   ├── __init__.py
│   │   ├── manager.py             # 配置管理器
│   │   ├── models.py              # 配置数据模型
│   │   ├── loaders.py             # 配置加载器
│   │   └── validators.py          # 配置验证器
│   ├── mcp/
│   │   ├── __init__.py
│   │   ├── client.py              # MCP 客户端
│   │   ├── server.py              # MCP 服务器
│   │   └── transports.py          # 传输层实现
│   ├── security/
│   │   ├── __init__.py
│   │   ├── permissions.py         # 权限管理
│   │   ├── sandbox.py             # 沙盒执行
│   │   └── validators.py          # 安全验证
│   └── utils/
│       ├── __init__.py
│       ├── logging.py             # 日志管理
│       ├── async_utils.py         # 异步工具
│       ├── file_utils.py          # 文件工具
│       ├── crypto_utils.py        # 加密工具
│       └── text_processing.py     # 文本处理
├── tests/
│   ├── __init__.py
│   ├── test_tools/
│   ├── test_ai/
│   ├── test_config/
│   └── test_repl/
├── pyproject.toml
├── README.md
├── CHANGELOG.md
└── docs/
    ├── api/
    ├── guides/
    └── examples/
```

## 核心架构组件

### 1. 入口点系统

#### 主入口点实现
```python
# simacode/main.py
import click
import asyncio
from pathlib import Path
from typing import Optional

from simacode.repl.app import SimacodeApp
from simacode.config.manager import ConfigManager
from simacode.utils.logging import setup_logging

@click.group(invoke_without_command=True)
@click.option('--cwd', type=click.Path(exists=True), default='.')
@click.option('--debug', is_flag=True, help='Enable debug mode')
@click.option('--print', 'print_mode', is_flag=True, help='Print response and exit')
@click.option('--dangerously-skip-permissions', is_flag=True)
@click.option('--verbose', is_flag=True, help='Verbose output')
@click.argument('prompt', required=False)
@click.pass_context
def main(ctx, cwd, debug, print_mode, dangerously_skip_permissions, verbose, prompt):
    """SimaCode - AI-powered terminal assistant with Deepseek and OneAPI support."""
    setup_logging(debug=debug, verbose=verbose)
    
    if ctx.invoked_subcommand is None:
        # 启动 REPL 模式或单次执行模式
        if print_mode and prompt:
            # 非交互模式：执行单次查询
            asyncio.run(execute_single_query(prompt, cwd, dangerously_skip_permissions))
        else:
            # 交互模式：启动 REPL
            app = SimacodeApp(
                cwd=Path(cwd),
                debug=debug,
                initial_prompt=prompt,
                dangerously_skip_permissions=dangerously_skip_permissions
            )
            app.run()

@main.group()
def config():
    """Configuration management commands."""
    pass

@main.group()
def tools():
    """Tool management commands."""
    pass

@main.group()
def mcp():
    """MCP (Model Context Protocol) server management."""
    pass
```

#### CLI 架构特点
- **Click 装饰器**: 替代 Commander.js 的命令定义
- **多层级子命令**: 保持 ClaudeX 的命令结构
- **类型安全**: 使用 Click 的类型检查
- **异步支持**: 完整的 asyncio 集成

### 2. REPL 交互系统

#### 核心应用类
```python
# simacode/repl/app.py
from textual.app import App, ComposeResult
from textual.widgets import Input, Header, Footer
from textual.containers import Vertical, Horizontal
from textual.reactive import reactive
from textual.binding import Binding

from simacode.repl.widgets import MessageList, StatusBar, ToolPanel
from simacode.tools.manager import ToolManager
from simacode.ai.providers import AIProviderFactory
from simacode.config.manager import ConfigManager

class SimacodeApp(App):
    """
    主 REPL 应用，对应 ClaudeX 的 REPL.tsx
    使用 Textual 实现现代终端用户界面
    """
    
    CSS_PATH = "simacode/repl/styles.css"
    
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+r", "clear_messages", "Clear"),
        Binding("f1", "toggle_help", "Help"),
        Binding("f2", "toggle_tools", "Tools"),
    ]
    
    # Reactive 变量（类似 React state）
    current_cost = reactive(0.0)
    is_processing = reactive(False)
    current_model = reactive("deepseek-chat")
    message_count = reactive(0)
    
    def __init__(self, cwd: Path, debug: bool = False, **kwargs):
        super().__init__()
        self.cwd = cwd
        self.debug = debug
        
        # 初始化核心组件
        self.config_manager = ConfigManager()
        self.tool_manager = ToolManager()
        self.ai_provider = AIProviderFactory.create_default()
        
        # 消息历史
        self.messages: List[ChatMessage] = []
        
    def compose(self) -> ComposeResult:
        """构建 UI 组件树"""
        yield Header(show_clock=True)
        
        with Vertical():
            # 主要内容区域
            with Horizontal():
                # 消息显示区域
                yield MessageList(id="messages")
                # 工具面板（可选显示）
                yield ToolPanel(id="tools", classes="hidden")
            
            # 状态栏
            yield StatusBar(id="status")
            
            # 输入区域
            yield Input(
                placeholder="Type your message or /help for commands...",
                id="input"
            )
        
        yield Footer()
    
    async def on_mount(self) -> None:
        """应用启动时的初始化"""
        await self.tool_manager.initialize()
        await self.ai_provider.initialize()
        
        # 设置输入焦点
        input_widget = self.query_one("#input", Input)
        input_widget.focus()
        
        # 显示欢迎消息
        await self.show_welcome_message()
    
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """处理用户输入提交"""
        message = event.value.strip()
        if not message:
            return
            
        # 清空输入框
        event.input.value = ""
        
        # 处理输入
        if message.startswith('/'):
            await self.handle_slash_command(message)
        else:
            await self.handle_chat_message(message)
    
    async def handle_chat_message(self, message: str) -> None:
        """处理普通聊天消息"""
        self.is_processing = True
        
        try:
            # 添加用户消息到显示
            await self.add_user_message(message)
            
            # 获取当前可用工具
            available_tools = await self.tool_manager.get_enabled_tools()
            
            # 流式处理 AI 响应
            assistant_message = ""
            async for chunk in self.ai_provider.stream_chat(
                messages=self.messages + [ChatMessage(role="user", content=message)],
                tools=available_tools,
                model=self.current_model
            ):
                if chunk.message.content:
                    assistant_message += chunk.message.content
                    await self.update_assistant_message(assistant_message)
                
                # 处理工具调用
                if chunk.message.tool_calls:
                    await self.handle_tool_calls(chunk.message.tool_calls)
                
                # 更新成本
                if chunk.cost_usd > 0:
                    self.current_cost += chunk.cost_usd
            
            # 保存消息到历史
            self.messages.extend([
                ChatMessage(role="user", content=message),
                ChatMessage(role="assistant", content=assistant_message)
            ])
            
        except Exception as e:
            await self.add_error_message(f"Error: {str(e)}")
        finally:
            self.is_processing = False
    
    async def handle_slash_command(self, command: str) -> None:
        """处理斜杠命令"""
        from simacode.cli.commands import CommandRegistry
        
        try:
            result = await CommandRegistry.execute_command(command[1:], self)
            if result:
                await self.add_system_message(result)
        except Exception as e:
            await self.add_error_message(f"Command error: {str(e)}")
```

#### Textual UI 组件系统

```python
# simacode/repl/widgets/message_list.py
from textual.widgets import RichLog
from textual.reactive import reactive
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from rich.console import Group

class MessageList(RichLog):
    """消息列表组件，负责显示对话历史"""
    
    message_count = reactive(0)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.auto_scroll = True
        self.highlight = True
        self.markup = True
    
    async def add_user_message(self, content: str) -> None:
        """添加用户消息"""
        panel = Panel(
            Text(content, style="white"),
            title="[bold blue]You[/]",
            border_style="blue",
            padding=(0, 1)
        )
        self.write(panel)
        self.message_count += 1
    
    async def add_assistant_message(self, content: str, streaming: bool = False) -> None:
        """添加 AI 助手消息"""
        if streaming:
            # 流式更新：更新最后一条消息
            # Textual 的实现需要特殊处理
            pass
        else:
            panel = Panel(
                Text(content, style="green"),
                title="[bold green]Assistant[/]",
                border_style="green",
                padding=(0, 1)
            )
            self.write(panel)
            self.message_count += 1
    
    async def add_tool_result(self, tool_name: str, result: str, success: bool = True) -> None:
        """添加工具执行结果"""
        style = "green" if success else "red"
        status = "✓" if success else "✗"
        
        # 代码高亮显示结果
        if result.strip():
            content = Group(
                Text(f"{status} Tool executed", style=f"bold {style}"),
                Syntax(result, "text", theme="monokai", line_numbers=False)
            )
        else:
            content = Text(f"{status} Tool executed (no output)", style=f"bold {style}")
        
        panel = Panel(
            content,
            title=f"[bold yellow]Tool: {tool_name}[/]",
            border_style=style,
            padding=(0, 1)
        )
        self.write(panel)
    
    async def add_error_message(self, error: str) -> None:
        """添加错误消息"""
        panel = Panel(
            Text(error, style="bold red"),
            title="[bold red]Error[/]",
            border_style="red",
            padding=(0, 1)
        )
        self.write(panel)
    
    async def add_system_message(self, message: str) -> None:
        """添加系统消息"""
        panel = Panel(
            Text(message, style="dim cyan"),
            title="[dim cyan]System[/]",
            border_style="dim cyan",
            padding=(0, 1)
        )
        self.write(panel)

# simacode/repl/widgets/status_bar.py
from textual.widgets import Static
from textual.reactive import reactive

class StatusBar(Static):
    """状态栏组件，显示当前状态信息"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cost = 0.0
        self.model = "deepseek-chat"
        self.is_processing = False
    
    def render(self) -> str:
        status = "🔄 Processing..." if self.is_processing else "💬 Ready"
        return f"{status} | Model: {self.model} | Cost: ${self.cost:.4f}"
    
    def update_status(self, cost: float, model: str, processing: bool) -> None:
        self.cost = cost
        self.model = model
        self.is_processing = processing
        self.refresh()
```

### 3. 工具系统架构

#### 工具基类和接口
```python
# simacode/tools/base.py
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Type, Optional, Dict, Any, List
from pydantic import BaseModel, ValidationError
from enum import Enum
import asyncio

class ToolResultType(str, Enum):
    PROGRESS = "progress"
    RESULT = "result"
    ERROR = "error"
    PERMISSION_REQUIRED = "permission_required"

class ToolResult(BaseModel):
    """工具执行结果"""
    type: ToolResultType
    content: Any
    metadata: Optional[Dict[str, Any]] = None
    tool_name: Optional[str] = None

class ToolContext(BaseModel):
    """工具执行上下文"""
    current_directory: str
    user_id: str
    session_id: str
    permissions: Dict[str, bool] = {}
    environment: Dict[str, str] = {}

class ValidationResult(BaseModel):
    """验证结果"""
    is_valid: bool
    message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class BaseTool(ABC):
    """
    工具基类，对应 ClaudeX 的 Tool interface
    使用 Python ABC 和 Pydantic 实现类型安全
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称，必须唯一"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述，用于 AI 理解工具功能"""
        pass
    
    @property
    @abstractmethod
    def input_schema(self) -> Type[BaseModel]:
        """输入参数的 Pydantic 模型"""
        pass
    
    @abstractmethod
    async def call(
        self, 
        input_data: BaseModel, 
        context: ToolContext
    ) -> AsyncGenerator[ToolResult, None]:
        """
        执行工具，返回异步生成器
        支持流式进度更新和结果返回
        """
        pass
    
    async def is_enabled(self) -> bool:
        """检查工具是否可用"""
        return True
    
    def is_read_only(self) -> bool:
        """是否为只读工具（不修改系统状态）"""
        return False
    
    async def needs_permissions(self, input_data: BaseModel) -> bool:
        """是否需要用户权限确认"""
        return not self.is_read_only()
    
    async def validate_input(self, input_data: BaseModel) -> ValidationResult:
        """
        自定义输入验证
        Pydantic 已经处理了基本的 schema 验证
        这里可以添加业务逻辑验证
        """
        return ValidationResult(is_valid=True)
    
    async def get_json_schema(self) -> Dict[str, Any]:
        """获取工具的 JSON Schema，用于 AI function calling"""
        schema = self.input_schema.model_json_schema()
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema
            }
        }
    
    async def get_prompt_description(self, dangerously_skip_permissions: bool = False) -> str:
        """获取工具的提示描述"""
        base_desc = f"Tool: {self.name}\nDescription: {self.description}"
        
        if not dangerously_skip_permissions and await self.needs_permissions(None):
            base_desc += "\nNote: This tool requires user permission."
        
        return base_desc

# 具体工具实现示例
class BashToolInput(BaseModel):
    """Bash 工具输入参数"""
    command: str
    timeout: Optional[int] = 30
    cwd: Optional[str] = None

class BashTool(BaseTool):
    """Bash 命令执行工具"""
    
    @property
    def name(self) -> str:
        return "bash"
    
    @property
    def description(self) -> str:
        return "Execute bash commands in the terminal"
    
    @property
    def input_schema(self) -> Type[BaseModel]:
        return BashToolInput
    
    def is_read_only(self) -> bool:
        return False  # Bash 命令可能修改系统状态
    
    async def validate_input(self, input_data: BashToolInput) -> ValidationResult:
        """验证 Bash 命令的安全性"""
        dangerous_commands = ['rm -rf', 'sudo', 'format', 'fdisk']
        
        if any(cmd in input_data.command.lower() for cmd in dangerous_commands):
            return ValidationResult(
                is_valid=False,
                message=f"Dangerous command detected: {input_data.command}"
            )
        
        return ValidationResult(is_valid=True)
    
    async def call(
        self, 
        input_data: BashToolInput, 
        context: ToolContext
    ) -> AsyncGenerator[ToolResult, None]:
        """执行 Bash 命令"""
        import subprocess
        import asyncio
        
        # 发送进度消息
        yield ToolResult(
            type=ToolResultType.PROGRESS,
            content=f"Executing: {input_data.command}",
            tool_name=self.name
        )
        
        try:
            # 异步执行命令
            process = await asyncio.create_subprocess_shell(
                input_data.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=input_data.cwd or context.current_directory
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), 
                timeout=input_data.timeout
            )
            
            # 返回结果
            result_content = {
                "stdout": stdout.decode('utf-8', errors='replace'),
                "stderr": stderr.decode('utf-8', errors='replace'),
                "return_code": process.returncode,
                "command": input_data.command
            }
            
            yield ToolResult(
                type=ToolResultType.RESULT,
                content=result_content,
                tool_name=self.name
            )
            
        except asyncio.TimeoutError:
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"Command timed out after {input_data.timeout} seconds",
                tool_name=self.name
            )
        except Exception as e:
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"Command execution failed: {str(e)}",
                tool_name=self.name
            )
```

#### 工具管理器
```python
# simacode/tools/manager.py
from typing import Dict, List, Type, Optional
from simacode.tools.base import BaseTool, ToolContext, ToolResult
from simacode.tools.registry import ToolRegistry
from simacode.security.permissions import PermissionManager

class ToolManager:
    """
    工具管理器，负责工具的注册、发现、执行和权限管理
    对应 ClaudeX 的工具管理逻辑
    """
    
    def __init__(self):
        self.registry = ToolRegistry()
        self.permission_manager = PermissionManager()
        self._enabled_tools: Optional[Dict[str, BaseTool]] = None
    
    async def initialize(self) -> None:
        """初始化工具管理器"""
        # 注册内置工具
        await self.registry.register_builtin_tools()
        
        # 加载 MCP 工具
        await self.registry.register_mcp_tools()
        
        # 缓存启用的工具
        self._enabled_tools = await self._get_enabled_tools()
    
    async def get_enabled_tools(self) -> List[BaseTool]:
        """获取当前启用的工具列表"""
        if self._enabled_tools is None:
            await self.initialize()
        
        return list(self._enabled_tools.values())
    
    async def get_tool_schemas(self) -> List[Dict]:
        """获取所有工具的 JSON Schema，用于 AI function calling"""
        tools = await self.get_enabled_tools()
        return [await tool.get_json_schema() for tool in tools]
    
    async def execute_tool(
        self, 
        tool_name: str, 
        input_data: Dict, 
        context: ToolContext,
        require_permission: bool = True
    ) -> AsyncGenerator[ToolResult, None]:
        """执行指定工具"""
        
        # 获取工具实例
        tool = self._enabled_tools.get(tool_name)
        if not tool:
            yield ToolResult(
                type="error",
                content=f"Tool '{tool_name}' not found",
                tool_name=tool_name
            )
            return
        
        try:
            # 验证输入数据
            validated_input = tool.input_schema(**input_data)
            
            # 自定义验证
            validation_result = await tool.validate_input(validated_input)
            if not validation_result.is_valid:
                yield ToolResult(
                    type="error",
                    content=f"Validation failed: {validation_result.message}",
                    tool_name=tool_name
                )
                return
            
            # 权限检查
            if require_permission and await tool.needs_permissions(validated_input):
                if not await self.permission_manager.check_permission(tool_name, input_data, context):
                    yield ToolResult(
                        type="permission_required",
                        content={
                            "tool_name": tool_name,
                            "input_data": input_data,
                            "description": tool.description
                        },
                        tool_name=tool_name
                    )
                    return
            
            # 执行工具
            async for result in tool.call(validated_input, context):
                yield result
                
        except ValidationError as e:
            yield ToolResult(
                type="error",
                content=f"Input validation failed: {e}",
                tool_name=tool_name
            )
        except Exception as e:
            yield ToolResult(
                type="error",
                content=f"Tool execution failed: {str(e)}",
                tool_name=tool_name
            )
```

### 4. AI 服务集成架构

#### AI 提供商抽象接口
```python
# simacode/ai/providers/base.py
from abc import ABC, abstractmethod
from typing import AsyncGenerator, List, Dict, Any, Optional
from pydantic import BaseModel
from enum import Enum

class ModelProvider(str, Enum):
    DEEPSEEK = "deepseek"
    ONEAPI = "oneapi"
    CUSTOM = "custom"

class ChatMessage(BaseModel):
    role: str  # "user", "assistant", "system", "tool"
    content: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None

class UsageInfo(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

class ChatResponse(BaseModel):
    message: ChatMessage
    usage: UsageInfo
    model: str
    cost_usd: float = 0.0
    finish_reason: Optional[str] = None

class AIProvider(ABC):
    """AI 提供商抽象基类"""
    
    @abstractmethod
    async def chat_completion(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict]] = None,
        model: Optional[str] = None,
        stream: bool = False,
        **kwargs
    ) -> AsyncGenerator[ChatResponse, None]:
        """聊天完成 API"""
        pass
    
    @abstractmethod
    async def get_available_models(self) -> List[str]:
        """获取可用模型列表"""
        pass
    
    @abstractmethod
    def calculate_cost(self, usage: UsageInfo, model: str) -> float:
        """计算 API 调用成本"""
        pass
    
    async def initialize(self) -> None:
        """初始化提供商"""
        pass
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            models = await self.get_available_models()
            return len(models) > 0
        except:
            return False
```

#### Deepseek 提供商实现
```python
# simacode/ai/providers/deepseek.py
import httpx
from openai import AsyncOpenAI
from typing import AsyncGenerator, List, Dict, Optional
from simacode.ai.providers.base import AIProvider, ChatMessage, ChatResponse, UsageInfo

class DeepSeekProvider(AIProvider):
    """
    Deepseek AI 提供商实现
    使用 OpenAI SDK 兼容 Deepseek API
    """
    
    def __init__(
        self, 
        api_key: str, 
        base_url: str = "https://api.deepseek.com/v1",
        default_model: str = "deepseek-chat"
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.default_model = default_model
        
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=httpx.Timeout(60.0, connect=10.0)
        )
        
        # Deepseek 模型和定价
        self.models = [
            "deepseek-chat",
            "deepseek-coder", 
            "deepseek-reasoner"
        ]
        
        self.pricing = {
            "deepseek-chat": {
                "input": 0.14 / 1_000_000,   # $0.14 per 1M input tokens
                "output": 0.28 / 1_000_000   # $0.28 per 1M output tokens
            },
            "deepseek-coder": {
                "input": 0.14 / 1_000_000,
                "output": 0.28 / 1_000_000
            },
            "deepseek-reasoner": {
                "input": 1.0 / 1_000_000,    # 推理模型价格更高
                "output": 2.0 / 1_000_000
            }
        }
    
    async def chat_completion(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict]] = None,
        model: Optional[str] = None,
        stream: bool = False,
        **kwargs
    ) -> AsyncGenerator[ChatResponse, None]:
        """实现聊天完成功能"""
        
        if model is None:
            model = self.default_model
        
        # 转换消息格式为 OpenAI 格式
        openai_messages = [
            {
                "role": msg.role,
                "content": msg.content,
                **({"tool_calls": msg.tool_calls} if msg.tool_calls else {}),
                **({"tool_call_id": msg.tool_call_id} if msg.tool_call_id else {})
            }
            for msg in messages
        ]
        
        # 构建请求参数
        request_params = {
            "model": model,
            "messages": openai_messages,
            "stream": stream,
            **kwargs
        }
        
        # 添加工具定义
        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = "auto"
        
        try:
            if stream:
                # 流式响应
                stream_response = await self.client.chat.completions.create(**request_params)
                
                async for chunk in stream_response:
                    if chunk.choices:
                        choice = chunk.choices[0]
                        delta = choice.delta
                        
                        if delta.content or delta.tool_calls:
                            yield ChatResponse(
                                message=ChatMessage(
                                    role="assistant",
                                    content=delta.content,
                                    tool_calls=delta.tool_calls
                                ),
                                usage=UsageInfo(),  # 流式响应中用量信息通常在最后
                                model=model,
                                finish_reason=choice.finish_reason
                            )
            else:
                # 非流式响应
                response = await self.client.chat.completions.create(**request_params)
                choice = response.choices[0]
                
                usage = UsageInfo(
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    total_tokens=response.usage.total_tokens
                ) if response.usage else UsageInfo()
                
                yield ChatResponse(
                    message=ChatMessage(
                        role=choice.message.role,
                        content=choice.message.content,
                        tool_calls=choice.message.tool_calls
                    ),
                    usage=usage,
                    model=model,
                    cost_usd=self.calculate_cost(usage, model),
                    finish_reason=choice.finish_reason
                )
                
        except Exception as e:
            # 错误处理
            yield ChatResponse(
                message=ChatMessage(
                    role="assistant",
                    content=f"API Error: {str(e)}"
                ),
                usage=UsageInfo(),
                model=model,
                cost_usd=0.0
            )
    
    async def get_available_models(self) -> List[str]:
        """获取可用模型"""
        try:
            # 尝试从 API 获取模型列表
            models_response = await self.client.models.list()
            return [model.id for model in models_response.data]
        except:
            # 如果 API 不支持，返回预定义列表
            return self.models
    
    def calculate_cost(self, usage: UsageInfo, model: str) -> float:
        """计算成本"""
        if model not in self.pricing:
            return 0.0
        
        pricing = self.pricing[model]
        input_cost = usage.prompt_tokens * pricing["input"]
        output_cost = usage.completion_tokens * pricing["output"]
        return input_cost + output_cost
```

#### OneAPI 提供商实现
```python
# simacode/ai/providers/oneapi.py
from typing import AsyncGenerator, List, Dict, Optional
from simacode.ai.providers.base import AIProvider, ChatMessage, ChatResponse, UsageInfo
from openai import AsyncOpenAI

class OneAPIProvider(AIProvider):
    """
    OneAPI/NewAPI 提供商实现
    支持多种后端模型的代理服务
    """
    
    def __init__(
        self, 
        api_key: str, 
        base_url: str,
        available_models: List[str],
        default_model: Optional[str] = None
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.available_models = available_models
        self.default_model = default_model or (available_models[0] if available_models else "gpt-3.5-turbo")
        
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url
        )
        
        # OneAPI 的默认定价（可以根据实际配置调整）
        self.default_pricing = {
            "input": 0.5 / 1_000_000,
            "output": 1.0 / 1_000_000
        }
    
    async def chat_completion(
        self,
        messages: List[ChatMessage],
        tools: Optional[List[Dict]] = None,
        model: Optional[str] = None,
        stream: bool = False,
        **kwargs
    ) -> AsyncGenerator[ChatResponse, None]:
        """实现聊天完成功能"""
        
        if model is None:
            model = self.default_model
        
        # 实现逻辑与 DeepSeek 类似，但可能需要处理不同的响应格式
        # 根据 OneAPI 的具体配置调整
        
        # 转换消息格式
        openai_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]
        
        request_params = {
            "model": model,
            "messages": openai_messages,
            "stream": stream,
            **kwargs
        }
        
        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = "auto"
        
        try:
            if stream:
                stream_response = await self.client.chat.completions.create(**request_params)
                async for chunk in stream_response:
                    if chunk.choices:
                        choice = chunk.choices[0]
                        delta = choice.delta
                        
                        yield ChatResponse(
                            message=ChatMessage(
                                role="assistant",
                                content=delta.content,
                                tool_calls=delta.tool_calls
                            ),
                            usage=UsageInfo(),
                            model=model,
                            finish_reason=choice.finish_reason
                        )
            else:
                response = await self.client.chat.completions.create(**request_params)
                choice = response.choices[0]
                
                usage = UsageInfo(
                    prompt_tokens=response.usage.prompt_tokens,
                    completion_tokens=response.usage.completion_tokens,
                    total_tokens=response.usage.total_tokens
                ) if response.usage else UsageInfo()
                
                yield ChatResponse(
                    message=ChatMessage(
                        role=choice.message.role,
                        content=choice.message.content,
                        tool_calls=choice.message.tool_calls
                    ),
                    usage=usage,
                    model=model,
                    cost_usd=self.calculate_cost(usage, model),
                    finish_reason=choice.finish_reason
                )
        except Exception as e:
            yield ChatResponse(
                message=ChatMessage(
                    role="assistant",
                    content=f"OneAPI Error: {str(e)}"
                ),
                usage=UsageInfo(),
                model=model
            )
    
    async def get_available_models(self) -> List[str]:
        """获取可用模型"""
        try:
            # 尝试从 OneAPI 获取模型列表
            models_response = await self.client.models.list()
            return [model.id for model in models_response.data]
        except:
            return self.available_models
    
    def calculate_cost(self, usage: UsageInfo, model: str) -> float:
        """计算成本（OneAPI 的成本计算可能需要查询实际配置）"""
        input_cost = usage.prompt_tokens * self.default_pricing["input"]
        output_cost = usage.completion_tokens * self.default_pricing["output"]
        return input_cost + output_cost
```

### 5. 配置管理系统

#### 配置数据模型
```python
# simacode/config/models.py
from pydantic import BaseModel, Field, validator
from typing import Dict, List, Optional, Union
from enum import Enum

class ThemeType(str, Enum):
    DARK = "dark"
    LIGHT = "light"
    AUTO = "auto"

class ModelProvider(str, Enum):
    DEEPSEEK = "deepseek"
    ONEAPI = "oneapi"

class AIProviderConfig(BaseModel):
    """AI 提供商配置"""
    provider: ModelProvider
    api_key: str
    base_url: Optional[str] = None
    default_model: Optional[str] = None
    max_tokens: Optional[int] = 4096
    temperature: Optional[float] = 0.7

class MCPServerConfig(BaseModel):
    """MCP 服务器配置"""
    name: str
    type: str = "stdio"  # "stdio" or "sse"
    command: Optional[str] = None
    args: Optional[List[str]] = None
    url: Optional[str] = None
    env: Optional[Dict[str, str]] = None

class SecurityConfig(BaseModel):
    """安全配置"""
    dangerously_skip_permissions: bool = False
    allowed_directories: List[str] = []
    blocked_commands: List[str] = []
    auto_approve_tools: List[str] = []

class GlobalConfig(BaseModel):
    """全局配置"""
    theme: ThemeType = ThemeType.DARK
    verbose: bool = False
    debug: bool = False
    
    # AI 配置
    ai_providers: Dict[str, AIProviderConfig] = {}
    default_provider: Optional[str] = None
    
    # 成本控制
    cost_threshold: float = 10.0  # USD
    cost_warning_threshold: float = 5.0
    
    # UI 配置
    show_token_count: bool = True
    auto_scroll: bool = True
    
    # 安全配置
    security: SecurityConfig = SecurityConfig()
    
    # MCP 服务器
    mcp_servers: Dict[str, MCPServerConfig] = {}
    
    # 用户信息
    user_id: Optional[str] = None
    has_completed_onboarding: bool = False

class ProjectConfig(BaseModel):
    """项目级配置"""
    # 工具配置
    enabled_tools: List[str] = []
    disabled_tools: List[str] = []
    
    # 项目特定的 AI 配置
    preferred_model: Optional[str] = None
    
    # 项目特定的 MCP 服务器
    mcp_servers: Dict[str, MCPServerConfig] = {}
    
    # 项目上下文
    project_context: Optional[str] = None
    coding_style: Optional[str] = None
```

#### 配置管理器
```python
# simacode/config/manager.py
from pathlib import Path
from typing import Optional, Any, Dict
import yaml
import json
from simacode.config.models import GlobalConfig, ProjectConfig
from simacode.utils.file_utils import ensure_directory

class ConfigManager:
    """
    配置管理器，处理全局和项目级配置
    对应 ClaudeX 的多层级配置系统
    """
    
    def __init__(self):
        self.global_config_dir = Path.home() / ".simacode"
        self.global_config_file = self.global_config_dir / "config.yaml"
        self.project_config_file = Path(".simacode") / "config.yaml"
        
        self._global_config: Optional[GlobalConfig] = None
        self._project_config: Optional[ProjectConfig] = None
    
    async def initialize(self) -> None:
        """初始化配置管理器"""
        ensure_directory(self.global_config_dir)
        await self.load_configs()
    
    async def load_configs(self) -> None:
        """加载配置文件"""
        # 加载全局配置
        if self.global_config_file.exists():
            with open(self.global_config_file, 'r') as f:
                global_data = yaml.safe_load(f) or {}
            self._global_config = GlobalConfig(**global_data)
        else:
            self._global_config = GlobalConfig()
            await self.save_global_config()
        
        # 加载项目配置
        if self.project_config_file.exists():
            with open(self.project_config_file, 'r') as f:
                project_data = yaml.safe_load(f) or {}
            self._project_config = ProjectConfig(**project_data)
        else:
            self._project_config = ProjectConfig()
    
    async def save_global_config(self) -> None:
        """保存全局配置"""
        ensure_directory(self.global_config_dir)
        with open(self.global_config_file, 'w') as f:
            yaml.dump(self._global_config.dict(), f, default_flow_style=False)
    
    async def save_project_config(self) -> None:
        """保存项目配置"""
        ensure_directory(self.project_config_file.parent)
        with open(self.project_config_file, 'w') as f:
            yaml.dump(self._project_config.dict(), f, default_flow_style=False)
    
    def get_global_config(self) -> GlobalConfig:
        """获取全局配置"""
        return self._global_config or GlobalConfig()
    
    def get_project_config(self) -> ProjectConfig:
        """获取项目配置"""
        return self._project_config or ProjectConfig()
    
    def get(self, key: str, global_scope: bool = False) -> Any:
        """获取配置值"""
        config = self.get_global_config() if global_scope else self.get_project_config()
        
        # 支持点分隔的键名
        keys = key.split('.')
        value = config.dict()
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return None
        
        return value
    
    def set(self, key: str, value: Any, global_scope: bool = False) -> None:
        """设置配置值"""
        config = self.get_global_config() if global_scope else self.get_project_config()
        config_dict = config.dict()
        
        # 支持点分隔的键名
        keys = key.split('.')
        current = config_dict
        
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        
        current[keys[-1]] = value
        
        # 更新配置对象
        if global_scope:
            self._global_config = GlobalConfig(**config_dict)
            asyncio.create_task(self.save_global_config())
        else:
            self._project_config = ProjectConfig(**config_dict)
            asyncio.create_task(self.save_project_config())
```

## 主要应用流程

### 1. 应用启动流程

```
main.py entry point
    ↓
Click command parsing
    ↓
ConfigManager.initialize() - 加载配置
    ↓
Setup logging and error handling
    ↓
Create SimacodeApp instance
    ↓
Initialize components:
    ├─ ToolManager.initialize()
    ├─ AIProviderFactory.create_default()
    └─ MCPClient.connect() (if configured)
    ↓
Textual App.run() - 启动 TUI
```

### 2. REPL 交互循环

```
SimacodeApp.compose() - 构建 UI
    ↓
User input via Input widget
    ↓
on_input_submitted() event handler
    ↓
Message routing:
    ├─ Slash command → handle_slash_command()
    └─ Chat message → handle_chat_message()
    ↓
AI service call with tool schemas
    ↓
Stream processing:
    ├─ Text content → update_assistant_message()
    ├─ Tool calls → handle_tool_calls()
    └─ Cost tracking → update_cost_display()
    ↓
Message display in MessageList widget
```

### 3. 工具执行流程

```
Tool call detection in AI response
    ↓
ToolManager.execute_tool()
    ↓
Input validation (Pydantic + custom)
    ↓
Permission check:
    ├─ needs_permissions() → True
    ├─ PermissionDialog.show()
    └─ User approval required
    ↓
Tool.call() async generator
    ↓
Progress updates via yield
    ↓
Result display in UI
    ↓
Continue AI conversation with tool result
```

### 4. AI 查询流程 (Deepseek/OneAPI)

```
User message input
    ↓
Message history compilation
    ↓
Tool schemas generation
    ↓
Provider selection (Deepseek/OneAPI)
    ↓
OpenAI SDK call with:
    ├─ Custom base_url
    ├─ Tool definitions
    └─ Streaming enabled
    ↓
Stream response processing:
    ├─ Content chunks → UI updates
    ├─ Tool calls → Tool execution
    └─ Usage tracking → Cost calculation
    ↓
Response completion and logging
```

## 安全和权限架构

### 权限层级
1. **全局权限**: 基于配置的权限设置
2. **工具权限**: 每个工具的独立权限检查
3. **文件系统权限**: 细粒度的文件访问控制
4. **沙盒执行**: 危险操作的隔离执行

### 安全特性
- **输入验证**: Pydantic 模型 + 自定义验证器
- **命令过滤**: 危险命令的检测和拦截
- **目录限制**: 防止访问项目外的敏感文件
- **权限对话框**: 用户主动确认危险操作
- **审计日志**: 所有工具执行的记录

## 扩展性设计

### 工具扩展
```python
# 自定义工具示例
class CustomTool(BaseTool):
    @property
    def name(self) -> str:
        return "custom_tool"
    
    @property 
    def input_schema(self) -> Type[BaseModel]:
        return CustomToolInput
    
    async def call(self, input_data, context):
        yield ToolResult(type="result", content="Custom tool result")

# 注册工具
ToolRegistry.register_tool(CustomTool())
```

### AI 提供商扩展
```python
# 自定义 AI 提供商
class CustomAIProvider(AIProvider):
    async def chat_completion(self, messages, tools=None, **kwargs):
        # 实现自定义 AI 服务集成
        pass

# 注册提供商
AIProviderFactory.register_provider("custom", CustomAIProvider)
```

### UI 组件扩展
```python
# 自定义 Textual 组件
class CustomWidget(Widget):
    def compose(self) -> ComposeResult:
        yield Label("Custom functionality")
    
    async def on_mount(self) -> None:
        # 组件初始化逻辑
        pass
```

## 性能优化

### 异步处理
- **全面 asyncio**: 所有 I/O 操作异步化
- **并发工具执行**: 支持多工具并行执行
- **流式响应**: 实时用户反馈
- **懒加载**: 按需加载工具和配置

### 内存管理
- **LRU 缓存**: 频繁访问数据的缓存
- **配置缓存**: 避免重复文件读取
- **消息历史管理**: 自动清理旧消息

### 用户体验
- **实时进度**: 工具执行的实时反馈
- **快捷键支持**: Textual 键盘绑定
- **主题系统**: 可定制的 UI 主题
- **错误恢复**: 优雅的错误处理和恢复

## 部署和分发

### 包管理
```toml
# pyproject.toml
[tool.poetry]
name = "simacode"
version = "0.1.0"
description = "AI-powered terminal assistant with Deepseek and OneAPI support"

[tool.poetry.dependencies]
python = "^3.10"
textual = "^0.40.0"
click = "^8.1.0"
pydantic = "^2.0.0"
openai = "^1.0.0"
httpx = "^0.25.0"
aiofiles = "^23.0.0"
pyyaml = "^6.0"

[tool.poetry.scripts]
simacode = "simacode.main:main"
```

### 安装方式
```bash
# PyPI 安装
pip install simacode

# 开发安装
git clone https://github.com/user/simacode
cd simacode
poetry install

# 运行
simacode
```

## 总结

SimaCode 作为 ClaudeX 的 Python 实现版本，通过以下核心特性提供强大的 AI 编程助手功能：

1. **Python 原生**: 充分利用 Python 生态系统的优势
2. **Textual TUI**: 现代化的终端用户界面
3. **Deepseek/OneAPI 集成**: 专注于经济实惠的 AI 服务
4. **类型安全**: Pydantic 模型确保数据一致性
5. **异步架构**: 高性能的并发处理
6. **模块化设计**: 易于扩展和维护
7. **安全第一**: 多层级的权限和安全控制

这种架构设计确保了 SimaCode 既保持了 ClaudeX 的核心功能和用户体验，又充分发挥了 Python 技术栈的优势，为开发者提供了一个强大、灵活且易于扩展的 AI 编程助手平台。