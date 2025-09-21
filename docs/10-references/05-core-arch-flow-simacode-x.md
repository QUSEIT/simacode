# SimaCode 核心架构与主要流程分析

## 项目概览

SimaCode 是一个现代化的 AI 编程助手，采用 Python 技术栈构建，使用 Textual 作为终端 UI 框架，主要支持 Deepseek 和 oneapi/newapi 等符合 OpenAI 接口标准的 AI 提供商，为开发者提供强大的智能编程辅助能力。

## 核心技术栈

- **运行时**: Python 3.10+
- **包管理**: Poetry
- **UI 框架**: Textual (现代 TUI 框架)
- **CLI 框架**: Click (命令行参数解析)
- **数据验证**: Pydantic (类型安全数据模型)
- **AI 集成**: OpenAI SDK (兼容 Deepseek/oneapi)
- **异步处理**: asyncio (Python 原生异步)
- **配置管理**: YAML/TOML + Pydantic
- **HTTP 客户端**: httpx/aiohttp
- **MCP 协议**: mcp (Python SDK)
- **测试框架**: pytest + pytest-asyncio

## 项目架构

### 整体目录结构

```
simacode/
├── simacode/                      # 主包目录
│   ├── __init__.py
│   ├── main.py                    # 应用主入口点
│   ├── cli/                       # 命令行接口层
│   │   ├── __init__.py
│   │   ├── commands.py            # Click 命令定义
│   │   ├── parsers.py             # 参数解析器
│   │   └── subcommands/           # 子命令实现
│   │       ├── __init__.py
│   │       ├── config.py          # 配置管理命令
│   │       ├── mcp.py             # MCP 服务器管理
│   │       ├── tools.py           # 工具管理命令
│   │       └── session.py         # 会话管理命令
│   ├── repl/                      # REPL 交互系统
│   │   ├── __init__.py
│   │   ├── app.py                 # Textual 主应用
│   │   ├── screens/               # 应用屏幕
│   │   │   ├── __init__.py
│   │   │   ├── main_screen.py     # 主交互屏幕
│   │   │   ├── config_screen.py   # 配置界面
│   │   │   └── help_screen.py     # 帮助界面
│   │   ├── widgets/               # UI 组件
│   │   │   ├── __init__.py
│   │   │   ├── message_list.py    # 消息列表组件
│   │   │   ├── input_widget.py    # 输入组件
│   │   │   ├── permission_dialog.py # 权限对话框
│   │   │   ├── tool_status.py     # 工具状态显示
│   │   │   ├── cost_tracker.py    # 成本追踪显示
│   │   │   └── progress_bar.py    # 进度条组件
│   │   ├── handlers/              # 事件处理器
│   │   │   ├── __init__.py
│   │   │   ├── input_handler.py   # 输入处理
│   │   │   ├── command_handler.py # 命令处理
│   │   │   └── tool_handler.py    # 工具调用处理
│   │   ├── themes/                # UI 主题
│   │   │   ├── __init__.py
│   │   │   ├── dark.py            # 暗色主题
│   │   │   ├── light.py           # 亮色主题
│   │   │   └── base.py            # 基础主题类
│   │   └── styles.css             # Textual CSS 样式
│   ├── tools/                     # 工具系统
│   │   ├── __init__.py
│   │   ├── base.py                # 工具基类和接口
│   │   ├── manager.py             # 工具管理器
│   │   ├── registry.py            # 工具注册表
│   │   ├── executor.py            # 工具执行器
│   │   └── implementations/       # 具体工具实现
│   │       ├── __init__.py
│   │       ├── bash_tool.py       # Bash 执行工具
│   │       ├── file_tools.py      # 文件操作工具集
│   │       ├── search_tools.py    # 搜索工具集
│   │       ├── agent_tool.py      # 代理工具
│   │       ├── memory_tools.py    # 内存管理工具
│   │       ├── notebook_tools.py  # Jupyter 笔记本工具
│   │       └── git_tools.py       # Git 操作工具
│   ├── ai/                        # AI 服务层
│   │   ├── __init__.py
│   │   ├── providers/             # AI 提供商实现
│   │   │   ├── __init__.py
│   │   │   ├── base.py            # 提供商基类
│   │   │   ├── deepseek.py        # Deepseek 集成
│   │   │   ├── oneapi.py          # OneAPI 集成
│   │   │   ├── factory.py         # 提供商工厂
│   │   │   └── router.py          # 多提供商路由
│   │   ├── models.py              # AI 模型定义
│   │   ├── streaming.py           # 流式响应处理
│   │   ├── context.py             # 上下文管理
│   │   ├── cost_tracker.py        # 成本追踪
│   │   └── function_calling.py    # 函数调用处理
│   ├── config/                    # 配置管理系统
│   │   ├── __init__.py
│   │   ├── manager.py             # 配置管理器
│   │   ├── models.py              # 配置数据模型
│   │   ├── loaders.py             # 配置加载器
│   │   ├── validators.py          # 配置验证器
│   │   ├── defaults.py            # 默认配置
│   │   └── migrations.py          # 配置迁移
│   ├── mcp/                       # MCP 协议支持
│   │   ├── __init__.py
│   │   ├── client.py              # MCP 客户端
│   │   ├── server.py              # MCP 服务器
│   │   ├── transports.py          # 传输层实现
│   │   ├── handlers.py            # 消息处理器
│   │   └── registry.py            # MCP 工具注册
│   ├── security/                  # 安全管理
│   │   ├── __init__.py
│   │   ├── permissions.py         # 权限管理
│   │   ├── sandbox.py             # 沙盒执行
│   │   ├── validators.py          # 安全验证
│   │   ├── audit.py               # 审计日志
│   │   └── encryption.py          # 加密工具
│   ├── session/                   # 会话管理
│   │   ├── __init__.py
│   │   ├── manager.py             # 会话管理器
│   │   ├── storage.py             # 会话存储
│   │   ├── recovery.py            # 会话恢复
│   │   └── history.py             # 历史记录
│   └── utils/                     # 工具函数
│       ├── __init__.py
│       ├── logging.py             # 日志管理
│       ├── async_utils.py         # 异步工具
│       ├── file_utils.py          # 文件工具
│       ├── crypto_utils.py        # 加密工具
│       ├── text_processing.py     # 文本处理
│       ├── retry.py               # 重试机制
│       └── decorators.py          # 装饰器工具
├── tests/                         # 测试套件
│   ├── __init__.py
│   ├── conftest.py                # pytest 配置
│   ├── test_tools/                # 工具测试
│   ├── test_ai/                   # AI 服务测试
│   ├── test_config/               # 配置测试
│   ├── test_repl/                 # REPL 测试
│   └── integration/               # 集成测试
├── docs/                          # 文档
│   ├── api/                       # API 文档
│   ├── guides/                    # 使用指南
│   ├── examples/                  # 示例代码
│   └── architecture/              # 架构文档
├── pyproject.toml                 # Poetry 配置
├── README.md                      # 项目说明
├── CHANGELOG.md                   # 变更日志
└── LICENSE                        # 许可证
```

## 核心架构组件

### 1. 应用入口系统

#### 主入口点设计
```python
# simacode/main.py
import asyncio
import click
from pathlib import Path
from typing import Optional

from simacode.repl.app import SimacodeApp
from simacode.config.manager import ConfigManager
from simacode.utils.logging import setup_logging
from simacode.ai.providers.factory import AIProviderFactory

@click.group(invoke_without_command=True)
@click.option('--cwd', type=click.Path(exists=True), default='.')
@click.option('--debug', is_flag=True, help='启用调试模式')
@click.option('--print', 'print_mode', is_flag=True, help='打印响应并退出')
@click.option('--dangerously-skip-permissions', is_flag=True, help='跳过权限检查')
@click.option('--verbose', is_flag=True, help='详细输出')
@click.option('--model', help='指定AI模型')
@click.option('--provider', help='指定AI提供商')
@click.argument('prompt', required=False)
@click.pass_context
def main(ctx, cwd, debug, print_mode, dangerously_skip_permissions, 
         verbose, model, provider, prompt):
    """SimaCode - 基于AI的智能编程助手"""
    
    # 设置日志
    setup_logging(debug=debug, verbose=verbose)
    
    if ctx.invoked_subcommand is None:
        if print_mode and prompt:
            # 非交互模式：执行单次查询
            asyncio.run(execute_single_query(
                prompt=prompt,
                cwd=Path(cwd),
                model=model,
                provider=provider,
                skip_permissions=dangerously_skip_permissions
            ))
        else:
            # 交互模式：启动REPL
            app = SimacodeApp(
                cwd=Path(cwd),
                debug=debug,
                initial_prompt=prompt,
                preferred_model=model,
                preferred_provider=provider,
                skip_permissions=dangerously_skip_permissions
            )
            app.run()

async def execute_single_query(
    prompt: str, 
    cwd: Path, 
    model: Optional[str] = None,
    provider: Optional[str] = None,
    skip_permissions: bool = False
) -> None:
    """执行单次AI查询"""
    from simacode.ai.providers.factory import AIProviderFactory
    from simacode.tools.manager import ToolManager
    
    # 初始化组件
    config_manager = ConfigManager()
    await config_manager.initialize()
    
    tool_manager = ToolManager(skip_permissions=skip_permissions)
    await tool_manager.initialize()
    
    ai_provider = AIProviderFactory.create_provider(
        provider_name=provider,
        model=model
    )
    await ai_provider.initialize()
    
    # 执行查询
    tools = await tool_manager.get_tool_schemas()
    
    async for response in ai_provider.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        tools=tools,
        stream=True
    ):
        if response.message.content:
            print(response.message.content, end='', flush=True)
        
        # 处理工具调用
        if response.message.tool_calls:
            for tool_call in response.message.tool_calls:
                tool_result = await tool_manager.execute_tool(
                    tool_name=tool_call.function.name,
                    input_data=tool_call.function.arguments,
                    require_permission=not skip_permissions
                )
                # 在非交互模式下处理工具结果
                print(f"\n[Tool: {tool_call.function.name}]")
                async for result in tool_result:
                    if result.type == "result":
                        print(result.content)
    
    print()  # 换行

# 子命令定义
@main.group()
def config():
    """配置管理"""
    pass

@main.group()
def tools():
    """工具管理"""
    pass

@main.group()
def session():
    """会话管理"""
    pass

@main.group()
def mcp():
    """MCP服务器管理"""
    pass

if __name__ == "__main__":
    main()
```

### 2. REPL 交互系统

#### Textual 应用核心
```python
# simacode/repl/app.py
from textual.app import App, ComposeResult
from textual.reactive import reactive
from textual.binding import Binding
from textual.screen import Screen

from simacode.repl.screens.main_screen import MainScreen
from simacode.repl.screens.config_screen import ConfigScreen
from simacode.repl.screens.help_screen import HelpScreen
from simacode.config.manager import ConfigManager
from simacode.tools.manager import ToolManager
from simacode.ai.providers.factory import AIProviderFactory

class SimacodeApp(App):
    """SimaCode 主应用程序"""
    
    CSS_PATH = "simacode/repl/styles.css"
    
    BINDINGS = [
        Binding("ctrl+c", "quit", "退出"),
        Binding("ctrl+r", "clear_session", "清空会话"),
        Binding("f1", "show_help", "帮助"),
        Binding("f2", "show_config", "配置"),
        Binding("ctrl+n", "new_session", "新会话"),
        Binding("ctrl+o", "open_session", "打开会话"),
        Binding("ctrl+s", "save_session", "保存会话"),
    ]
    
    # 响应式状态
    current_cost = reactive(0.0)
    is_processing = reactive(False)
    current_model = reactive("deepseek-chat")
    message_count = reactive(0)
    session_name = reactive("default")
    
    def __init__(
        self, 
        cwd: Path, 
        debug: bool = False,
        initial_prompt: Optional[str] = None,
        preferred_model: Optional[str] = None,
        preferred_provider: Optional[str] = None,
        skip_permissions: bool = False
    ):
        super().__init__()
        self.cwd = cwd
        self.debug = debug
        self.initial_prompt = initial_prompt
        self.skip_permissions = skip_permissions
        
        # 核心组件
        self.config_manager = ConfigManager()
        self.tool_manager = ToolManager(skip_permissions=skip_permissions)
        self.ai_provider = None
        
        # 首选配置
        self.preferred_model = preferred_model
        self.preferred_provider = preferred_provider
        
        # 应用状态
        self.current_session_id = None
        self.message_history = []
    
    async def on_mount(self) -> None:
        """应用启动时的初始化"""
        await self.initialize_components()
        await self.load_or_create_session()
        
        # 推送主屏幕
        await self.push_screen(MainScreen(self))
        
        # 如果有初始提示，自动发送
        if self.initial_prompt:
            main_screen = self.screen
            if hasattr(main_screen, 'send_message'):
                await main_screen.send_message(self.initial_prompt)
    
    async def initialize_components(self) -> None:
        """初始化核心组件"""
        # 初始化配置管理器
        await self.config_manager.initialize()
        
        # 初始化工具管理器
        await self.tool_manager.initialize()
        
        # 创建AI提供商
        self.ai_provider = AIProviderFactory.create_provider(
            provider_name=self.preferred_provider,
            model=self.preferred_model,
            config_manager=self.config_manager
        )
        await self.ai_provider.initialize()
        
        # 更新状态
        self.current_model = self.ai_provider.current_model
    
    async def load_or_create_session(self) -> None:
        """加载或创建会话"""
        from simacode.session.manager import SessionManager
        
        session_manager = SessionManager(self.config_manager)
        
        # 尝试加载最近的会话，否则创建新会话
        try:
            session = await session_manager.load_recent_session()
            if session:
                self.current_session_id = session.id
                self.session_name = session.name
                self.message_history = session.messages
            else:
                session = await session_manager.create_session("default")
                self.current_session_id = session.id
                self.session_name = session.name
        except Exception as e:
            self.log.error(f"会话加载失败: {e}")
            # 创建默认会话
            session = await session_manager.create_session("default")
            self.current_session_id = session.id
    
    # 动作处理器
    async def action_show_help(self) -> None:
        """显示帮助屏幕"""
        await self.push_screen(HelpScreen())
    
    async def action_show_config(self) -> None:
        """显示配置屏幕"""
        await self.push_screen(ConfigScreen(self.config_manager))
    
    async def action_clear_session(self) -> None:
        """清空当前会话"""
        self.message_history.clear()
        self.message_count = 0
        self.current_cost = 0.0
        
        # 通知主屏幕更新
        if hasattr(self.screen, 'clear_messages'):
            await self.screen.clear_messages()
    
    async def action_new_session(self) -> None:
        """创建新会话"""
        from simacode.session.manager import SessionManager
        
        session_manager = SessionManager(self.config_manager)
        session = await session_manager.create_session()
        
        self.current_session_id = session.id
        self.session_name = session.name
        await self.action_clear_session()
    
    # 消息处理方法
    async def process_user_message(self, message: str) -> None:
        """处理用户消息"""
        self.is_processing = True
        
        try:
            # 检查是否为斜杠命令
            if message.startswith('/'):
                await self.handle_slash_command(message)
            else:
                await self.handle_chat_message(message)
        except Exception as e:
            self.log.error(f"消息处理失败: {e}")
            await self.add_error_message(f"处理消息时出错: {str(e)}")
        finally:
            self.is_processing = False
    
    async def handle_chat_message(self, message: str) -> None:
        """处理聊天消息"""
        # 获取工具定义
        tools = await self.tool_manager.get_tool_schemas()
        
        # 构建消息历史
        messages = self.message_history + [
            {"role": "user", "content": message}
        ]
        
        # 流式处理AI响应
        assistant_message = ""
        tool_results = []
        
        async for response in self.ai_provider.chat_completion(
            messages=messages,
            tools=tools,
            stream=True
        ):
            # 处理文本内容
            if response.message.content:
                assistant_message += response.message.content
                await self.update_assistant_message(assistant_message)
            
            # 处理工具调用
            if response.message.tool_calls:
                for tool_call in response.message.tool_calls:
                    tool_result = await self.execute_tool_call(tool_call)
                    tool_results.append(tool_result)
            
            # 更新成本
            if response.cost_usd > 0:
                self.current_cost += response.cost_usd
        
        # 保存到会话历史
        self.message_history.extend([
            {"role": "user", "content": message},
            {"role": "assistant", "content": assistant_message}
        ])
        
        self.message_count = len(self.message_history)
        
        # 保存会话
        await self.save_current_session()
    
    async def execute_tool_call(self, tool_call) -> dict:
        """执行工具调用"""
        tool_name = tool_call.function.name
        tool_args = tool_call.function.arguments
        
        # 显示工具执行状态
        await self.show_tool_execution(tool_name, "开始执行")
        
        try:
            tool_result = None
            async for result in self.tool_manager.execute_tool(
                tool_name=tool_name,
                input_data=tool_args,
                require_permission=not self.skip_permissions
            ):
                if result.type == "progress":
                    await self.show_tool_progress(tool_name, result.content)
                elif result.type == "result":
                    tool_result = result.content
                    await self.show_tool_result(tool_name, result.content, True)
                elif result.type == "error":
                    await self.show_tool_result(tool_name, result.content, False)
                elif result.type == "permission_required":
                    # 显示权限对话框
                    permission_granted = await self.request_permission(
                        tool_name, result.content
                    )
                    if not permission_granted:
                        return {
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "content": "权限被拒绝，工具执行取消"
                        }
            
            return {
                "tool_call_id": tool_call.id,
                "role": "tool", 
                "content": str(tool_result) if tool_result else "执行完成"
            }
            
        except Exception as e:
            error_msg = f"工具执行失败: {str(e)}"
            await self.show_tool_result(tool_name, error_msg, False)
            return {
                "tool_call_id": tool_call.id,
                "role": "tool",
                "content": error_msg
            }
```

#### 主交互屏幕
```python
# simacode/repl/screens/main_screen.py
from textual.screen import Screen
from textual.containers import Vertical, Horizontal
from textual.widgets import Header, Footer, Input

from simacode.repl.widgets.message_list import MessageList
from simacode.repl.widgets.tool_status import ToolStatusPanel
from simacode.repl.widgets.cost_tracker import CostTracker

class MainScreen(Screen):
    """主交互屏幕"""
    
    def __init__(self, app_instance):
        super().__init__()
        self.app_instance = app_instance
    
    def compose(self) -> ComposeResult:
        """构建UI组件"""
        yield Header(show_clock=True)
        
        with Vertical():
            # 主内容区域
            with Horizontal():
                # 消息显示区域 (主要区域)
                yield MessageList(id="messages", classes="main-content")
                
                # 侧边栏 (工具状态和成本追踪)
                with Vertical(classes="sidebar"):
                    yield ToolStatusPanel(id="tool-status")
                    yield CostTracker(id="cost-tracker")
            
            # 输入区域
            yield Input(
                placeholder="输入您的消息或 /help 查看命令...",
                id="input"
            )
        
        yield Footer()
    
    async def on_mount(self) -> None:
        """屏幕挂载时的初始化"""
        # 设置输入焦点
        input_widget = self.query_one("#input", Input)
        input_widget.focus()
        
        # 显示欢迎消息
        message_list = self.query_one("#messages", MessageList)
        await message_list.add_system_message(
            "欢迎使用 SimaCode！输入消息开始对话，或使用 /help 查看可用命令。"
        )
        
        # 如果有历史消息，恢复显示
        if self.app_instance.message_history:
            await self.restore_message_history()
    
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """处理用户输入提交"""
        message = event.value.strip()
        if not message:
            return
        
        # 清空输入框
        event.input.value = ""
        
        # 添加用户消息到显示
        message_list = self.query_one("#messages", MessageList)
        await message_list.add_user_message(message)
        
        # 处理消息
        await self.app_instance.process_user_message(message)
    
    async def send_message(self, message: str) -> None:
        """程序化发送消息"""
        message_list = self.query_one("#messages", MessageList)
        await message_list.add_user_message(message)
        await self.app_instance.process_user_message(message)
    
    async def clear_messages(self) -> None:
        """清空消息显示"""
        message_list = self.query_one("#messages", MessageList)
        await message_list.clear()
    
    async def restore_message_history(self) -> None:
        """恢复消息历史显示"""
        message_list = self.query_one("#messages", MessageList)
        
        for msg in self.app_instance.message_history:
            if msg["role"] == "user":
                await message_list.add_user_message(msg["content"])
            elif msg["role"] == "assistant":
                await message_list.add_assistant_message(msg["content"])
```

### 3. 工具系统架构

#### 工具基类设计
```python
# simacode/tools/base.py
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Type, Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum
import asyncio
import logging

class ToolResultType(str, Enum):
    """工具结果类型枚举"""
    PROGRESS = "progress"
    RESULT = "result"
    ERROR = "error"
    PERMISSION_REQUIRED = "permission_required"
    WARNING = "warning"
    INFO = "info"

class ToolResult(BaseModel):
    """工具执行结果"""
    type: ToolResultType
    content: Any
    metadata: Optional[Dict[str, Any]] = None
    tool_name: Optional[str] = None
    timestamp: Optional[str] = None

class ToolContext(BaseModel):
    """工具执行上下文"""
    current_directory: str = Field(description="当前工作目录")
    user_id: str = Field(description="用户ID")
    session_id: str = Field(description="会话ID")
    permissions: Dict[str, bool] = Field(default_factory=dict, description="权限设置")
    environment: Dict[str, str] = Field(default_factory=dict, description="环境变量")
    tool_history: List[str] = Field(default_factory=list, description="工具执行历史")

class ValidationResult(BaseModel):
    """验证结果"""
    is_valid: bool
    message: Optional[str] = None
    suggestions: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

class BaseTool(ABC):
    """
    工具基类，定义了所有工具必须实现的接口
    支持异步执行、权限管理、进度反馈等特性
    """
    
    def __init__(self):
        self.logger = logging.getLogger(f"simacode.tools.{self.name}")
    
    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称，必须唯一"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """工具功能描述"""
        pass
    
    @property
    @abstractmethod
    def input_schema(self) -> Type[BaseModel]:
        """输入参数的 Pydantic 模型"""
        pass
    
    @property
    def version(self) -> str:
        """工具版本"""
        return "1.0.0"
    
    @property
    def category(self) -> str:
        """工具分类"""
        return "general"
    
    @property
    def tags(self) -> List[str]:
        """工具标签"""
        return []
    
    @abstractmethod
    async def execute(
        self, 
        input_data: BaseModel, 
        context: ToolContext
    ) -> AsyncGenerator[ToolResult, None]:
        """
        执行工具核心逻辑
        使用异步生成器支持流式进度更新
        """
        pass
    
    # 生命周期钩子
    async def before_execute(
        self, 
        input_data: BaseModel, 
        context: ToolContext
    ) -> Optional[ToolResult]:
        """执行前钩子，可以进行预处理或权限检查"""
        return None
    
    async def after_execute(
        self, 
        input_data: BaseModel, 
        context: ToolContext,
        results: List[ToolResult]
    ) -> None:
        """执行后钩子，可以进行清理或后处理"""
        pass
    
    async def on_error(
        self, 
        error: Exception, 
        input_data: BaseModel, 
        context: ToolContext
    ) -> Optional[ToolResult]:
        """错误处理钩子"""
        self.logger.error(f"工具执行出错: {error}")
        return ToolResult(
            type=ToolResultType.ERROR,
            content=f"工具执行失败: {str(error)}",
            tool_name=self.name
        )
    
    # 能力检查
    async def is_enabled(self) -> bool:
        """检查工具是否可用"""
        return True
    
    def is_read_only(self) -> bool:
        """是否为只读工具"""
        return False
    
    def requires_internet(self) -> bool:
        """是否需要网络连接"""
        return False
    
    def is_dangerous(self) -> bool:
        """是否为危险操作工具"""
        return not self.is_read_only()
    
    # 权限管理
    async def needs_permissions(self, input_data: BaseModel) -> bool:
        """检查是否需要用户权限确认"""
        return self.is_dangerous()
    
    async def check_permissions(
        self, 
        input_data: BaseModel, 
        context: ToolContext
    ) -> bool:
        """检查是否有执行权限"""
        if not await self.needs_permissions(input_data):
            return True
        
        permission_key = f"tool.{self.name}"
        return context.permissions.get(permission_key, False)
    
    # 输入验证
    async def validate_input(self, input_data: BaseModel) -> ValidationResult:
        """
        自定义输入验证
        Pydantic 模式验证之外的业务逻辑验证
        """
        return ValidationResult(is_valid=True)
    
    # JSON Schema 生成
    async def get_json_schema(self) -> Dict[str, Any]:
        """生成工具的 JSON Schema，用于 AI function calling"""
        schema = self.input_schema.model_json_schema()
        
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema
            }
        }
    
    # 帮助和文档
    def get_help_text(self) -> str:
        """获取工具帮助文本"""
        return f"""
工具名称: {self.name}
描述: {self.description}
分类: {self.category}
版本: {self.version}
只读: {'是' if self.is_read_only() else '否'}
需要网络: {'是' if self.requires_internet() else '否'}
标签: {', '.join(self.tags)}

参数模式:
{self.input_schema.model_json_schema()}
        """.strip()
    
    def get_examples(self) -> List[Dict[str, Any]]:
        """获取使用示例"""
        return []
    
    # 工具统计和监控
    async def get_usage_stats(self) -> Dict[str, Any]:
        """获取工具使用统计"""
        return {
            "name": self.name,
            "version": self.version,
            "category": self.category,
            "enabled": await self.is_enabled()
        }

# 具体工具实现示例
class BashToolInput(BaseModel):
    """Bash 工具输入参数"""
    command: str = Field(description="要执行的bash命令")
    timeout: Optional[int] = Field(default=30, description="超时时间(秒)")
    working_directory: Optional[str] = Field(default=None, description="工作目录")
    capture_output: bool = Field(default=True, description="是否捕获输出")
    environment: Optional[Dict[str, str]] = Field(default=None, description="环境变量")

class BashTool(BaseTool):
    """Bash 命令执行工具"""
    
    @property
    def name(self) -> str:
        return "bash"
    
    @property
    def description(self) -> str:
        return "在终端中执行bash命令，支持超时控制和输出捕获"
    
    @property
    def input_schema(self) -> Type[BaseModel]:
        return BashToolInput
    
    @property
    def category(self) -> str:
        return "system"
    
    @property
    def tags(self) -> List[str]:
        return ["terminal", "shell", "system", "command"]
    
    def is_read_only(self) -> bool:
        return False  # Bash 命令可能修改系统状态
    
    def is_dangerous(self) -> bool:
        return True
    
    async def validate_input(self, input_data: BashToolInput) -> ValidationResult:
        """验证 Bash 命令的安全性"""
        dangerous_patterns = [
            'rm -rf /',
            'sudo rm',
            'format',
            'fdisk',
            'mkfs',
            '> /dev/',
            'dd if=',
            'kill -9',
            'pkill -9'
        ]
        
        command_lower = input_data.command.lower()
        
        for pattern in dangerous_patterns:
            if pattern in command_lower:
                return ValidationResult(
                    is_valid=False,
                    message=f"检测到危险命令模式: {pattern}",
                    suggestions=[
                        "请检查命令是否正确",
                        "避免使用可能损坏系统的命令",
                        "考虑使用更安全的替代方案"
                    ]
                )
        
        # 检查命令长度
        if len(input_data.command) > 1000:
            return ValidationResult(
                is_valid=False,
                message="命令过长，可能存在安全风险"
            )
        
        return ValidationResult(is_valid=True)
    
    async def execute(
        self, 
        input_data: BashToolInput, 
        context: ToolContext
    ) -> AsyncGenerator[ToolResult, None]:
        """执行 Bash 命令"""
        import subprocess
        import shlex
        from pathlib import Path
        
        # 发送开始执行的进度消息
        yield ToolResult(
            type=ToolResultType.PROGRESS,
            content=f"正在执行命令: {input_data.command}",
            tool_name=self.name
        )
        
        # 准备执行环境
        work_dir = input_data.working_directory or context.current_directory
        env = dict(context.environment)
        if input_data.environment:
            env.update(input_data.environment)
        
        try:
            # 创建子进程
            process = await asyncio.create_subprocess_shell(
                input_data.command,
                stdout=subprocess.PIPE if input_data.capture_output else None,
                stderr=subprocess.PIPE if input_data.capture_output else None,
                cwd=work_dir,
                env=env
            )
            
            # 等待完成或超时
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=input_data.timeout
                )
                
                # 解码输出
                stdout_text = stdout.decode('utf-8', errors='replace') if stdout else ""
                stderr_text = stderr.decode('utf-8', errors='replace') if stderr else ""
                
                # 构建结果
                result_data = {
                    "command": input_data.command,
                    "return_code": process.returncode,
                    "stdout": stdout_text,
                    "stderr": stderr_text,
                    "working_directory": work_dir,
                    "execution_time": f"{input_data.timeout}s内完成"
                }
                
                # 根据返回码确定结果类型
                if process.returncode == 0:
                    yield ToolResult(
                        type=ToolResultType.RESULT,
                        content=result_data,
                        tool_name=self.name,
                        metadata={"success": True}
                    )
                else:
                    yield ToolResult(
                        type=ToolResultType.ERROR,
                        content=f"命令执行失败 (返回码: {process.returncode})\n错误输出: {stderr_text}",
                        tool_name=self.name,
                        metadata={"return_code": process.returncode}
                    )
                
            except asyncio.TimeoutError:
                # 超时处理
                process.kill()
                yield ToolResult(
                    type=ToolResultType.ERROR,
                    content=f"命令执行超时 ({input_data.timeout}秒)",
                    tool_name=self.name,
                    metadata={"timeout": True}
                )
                
        except Exception as e:
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"命令执行异常: {str(e)}",
                tool_name=self.name,
                metadata={"exception": str(type(e).__name__)}
            )
    
    def get_examples(self) -> List[Dict[str, Any]]:
        """获取使用示例"""
        return [
            {
                "description": "列出当前目录文件",
                "input": {
                    "command": "ls -la",
                    "timeout": 10
                }
            },
            {
                "description": "检查系统信息", 
                "input": {
                    "command": "uname -a && whoami",
                    "timeout": 15
                }
            },
            {
                "description": "在特定目录执行命令",
                "input": {
                    "command": "pwd && ls",
                    "working_directory": "/tmp",
                    "timeout": 10
                }
            }
        ]
```

#### 工具管理器
```python
# simacode/tools/manager.py
from typing import Dict, List, Type, Optional, Set
import importlib
import pkgutil
from pathlib import Path

from simacode.tools.base import BaseTool, ToolContext, ToolResult, ToolResultType
from simacode.tools.registry import ToolRegistry
from simacode.security.permissions import PermissionManager
from simacode.utils.logging import get_logger

logger = get_logger(__name__)

class ToolManager:
    """
    工具管理器
    负责工具的注册、发现、执行和权限管理
    """
    
    def __init__(self, skip_permissions: bool = False):
        self.registry = ToolRegistry()
        self.permission_manager = PermissionManager()
        self.skip_permissions = skip_permissions
        self._enabled_tools: Optional[Dict[str, BaseTool]] = None
        self._tool_stats: Dict[str, Dict] = {}
    
    async def initialize(self) -> None:
        """初始化工具管理器"""
        try:
            # 注册内置工具
            await self._register_builtin_tools()
            
            # 注册MCP工具
            await self._register_mcp_tools()
            
            # 注册插件工具
            await self._register_plugin_tools()
            
            # 缓存启用的工具
            self._enabled_tools = await self._build_enabled_tools()
            
            logger.info(f"工具管理器初始化完成，共注册 {len(self._enabled_tools)} 个工具")
            
        except Exception as e:
            logger.error(f"工具管理器初始化失败: {e}")
            raise
    
    async def _register_builtin_tools(self) -> None:
        """注册内置工具"""
        from simacode.tools.implementations import (
            BashTool,
            FileReadTool,
            FileWriteTool,
            FileEditTool,
            SearchTool,
            AgentTool,
            MemoryTool
        )
        
        builtin_tools = [
            BashTool(),
            FileReadTool(),
            FileWriteTool(), 
            FileEditTool(),
            SearchTool(),
            AgentTool(),
            MemoryTool()
        ]
        
        for tool in builtin_tools:
            if await tool.is_enabled():
                await self.registry.register_tool(tool)
                logger.debug(f"注册内置工具: {tool.name}")
    
    async def _register_mcp_tools(self) -> None:
        """注册MCP工具"""
        try:
            from simacode.mcp.client import MCPClient
            
            mcp_client = MCPClient()
            mcp_tools = await mcp_client.get_available_tools()
            
            for tool in mcp_tools:
                await self.registry.register_tool(tool)
                logger.debug(f"注册MCP工具: {tool.name}")
                
        except ImportError:
            logger.warning("MCP 支持未启用")
        except Exception as e:
            logger.error(f"MCP 工具注册失败: {e}")
    
    async def _register_plugin_tools(self) -> None:
        """注册插件工具"""
        plugins_dir = Path("plugins")
        if not plugins_dir.exists():
            return
        
        # 动态加载插件工具
        for plugin_file in plugins_dir.glob("*.py"):
            try:
                spec = importlib.util.spec_from_file_location(
                    plugin_file.stem, plugin_file
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # 查找工具类
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and 
                        issubclass(attr, BaseTool) and 
                        attr != BaseTool):
                        tool = attr()
                        if await tool.is_enabled():
                            await self.registry.register_tool(tool)
                            logger.debug(f"注册插件工具: {tool.name}")
                            
            except Exception as e:
                logger.error(f"加载插件 {plugin_file} 失败: {e}")
    
    async def _build_enabled_tools(self) -> Dict[str, BaseTool]:
        """构建启用工具字典"""
        enabled_tools = {}
        
        for tool_name in self.registry.list_tools():
            tool = self.registry.get_tool(tool_name)
            if tool and await tool.is_enabled():
                enabled_tools[tool_name] = tool
        
        return enabled_tools
    
    # 公共接口
    async def get_enabled_tools(self) -> List[BaseTool]:
        """获取启用的工具列表"""
        if self._enabled_tools is None:
            await self.initialize()
        
        return list(self._enabled_tools.values())
    
    async def get_tool_schemas(self) -> List[Dict]:
        """获取工具JSON Schema，用于AI function calling"""
        tools = await self.get_enabled_tools()
        schemas = []
        
        for tool in tools:
            try:
                schema = await tool.get_json_schema()
                schemas.append(schema)
            except Exception as e:
                logger.error(f"获取工具 {tool.name} 的schema失败: {e}")
        
        return schemas
    
    async def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """根据名称获取工具"""
        if self._enabled_tools is None:
            await self.initialize()
        
        return self._enabled_tools.get(tool_name)
    
    async def execute_tool(
        self,
        tool_name: str,
        input_data: Dict,
        context: Optional[ToolContext] = None,
        require_permission: bool = True
    ) -> AsyncGenerator[ToolResult, None]:
        """执行指定工具"""
        
        # 获取工具实例
        tool = await self.get_tool(tool_name)
        if not tool:
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"工具 '{tool_name}' 未找到",
                tool_name=tool_name
            )
            return
        
        # 创建默认上下文
        if context is None:
            context = ToolContext(
                current_directory=".",
                user_id="default",
                session_id="default"
            )
        
        try:
            # 验证输入数据
            validated_input = tool.input_schema(**input_data)
            
            # 自定义验证
            validation_result = await tool.validate_input(validated_input)
            if not validation_result.is_valid:
                yield ToolResult(
                    type=ToolResultType.ERROR,
                    content=f"输入验证失败: {validation_result.message}",
                    tool_name=tool_name,
                    metadata={
                        "suggestions": validation_result.suggestions,
                        "validation_metadata": validation_result.metadata
                    }
                )
                return
            
            # 权限检查
            if (require_permission and 
                not self.skip_permissions and 
                await tool.needs_permissions(validated_input)):
                
                has_permission = await tool.check_permissions(validated_input, context)
                if not has_permission:
                    yield ToolResult(
                        type=ToolResultType.PERMISSION_REQUIRED,
                        content={
                            "tool_name": tool_name,
                            "input_data": input_data,
                            "description": tool.description,
                            "is_dangerous": tool.is_dangerous(),
                            "category": tool.category
                        },
                        tool_name=tool_name
                    )
                    return
            
            # 执行前钩子
            pre_result = await tool.before_execute(validated_input, context)
            if pre_result and pre_result.type == ToolResultType.ERROR:
                yield pre_result
                return
            
            # 执行工具并收集结果
            results = []
            try:
                async for result in tool.execute(validated_input, context):
                    results.append(result)
                    yield result
                    
                    # 更新统计
                    await self._update_tool_stats(tool_name, result)
                    
            except Exception as e:
                # 调用错误处理钩子
                error_result = await tool.on_error(e, validated_input, context)
                if error_result:
                    yield error_result
                else:
                    yield ToolResult(
                        type=ToolResultType.ERROR,
                        content=f"工具执行异常: {str(e)}",
                        tool_name=tool_name
                    )
                return
            
            # 执行后钩子
            await tool.after_execute(validated_input, context, results)
            
        except Exception as e:
            logger.error(f"工具 {tool_name} 执行失败: {e}")
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"工具执行失败: {str(e)}",
                tool_name=tool_name
            )
    
    async def _update_tool_stats(self, tool_name: str, result: ToolResult) -> None:
        """更新工具使用统计"""
        if tool_name not in self._tool_stats:
            self._tool_stats[tool_name] = {
                "usage_count": 0,
                "success_count": 0,
                "error_count": 0,
                "last_used": None
            }
        
        stats = self._tool_stats[tool_name]
        stats["usage_count"] += 1
        stats["last_used"] = datetime.now().isoformat()
        
        if result.type == ToolResultType.RESULT:
            stats["success_count"] += 1
        elif result.type == ToolResultType.ERROR:
            stats["error_count"] += 1
    
    # 管理功能
    async def get_tool_info(self, tool_name: str) -> Optional[Dict]:
        """获取工具详细信息"""
        tool = await self.get_tool(tool_name)
        if not tool:
            return None
        
        return {
            "name": tool.name,
            "description": tool.description,
            "version": tool.version,
            "category": tool.category,
            "tags": tool.tags,
            "is_read_only": tool.is_read_only(),
            "requires_internet": tool.requires_internet(),
            "is_dangerous": tool.is_dangerous(),
            "help_text": tool.get_help_text(),
            "examples": tool.get_examples(),
            "stats": self._tool_stats.get(tool_name, {}),
            "schema": await tool.get_json_schema()
        }
    
    async def list_tools_by_category(self) -> Dict[str, List[str]]:
        """按分类列出工具"""
        tools = await self.get_enabled_tools()
        categories = {}
        
        for tool in tools:
            category = tool.category
            if category not in categories:
                categories[category] = []
            categories[category].append(tool.name)
        
        return categories
    
    async def search_tools(self, query: str) -> List[str]:
        """搜索工具"""
        tools = await self.get_enabled_tools()
        matches = []
        
        query_lower = query.lower()
        
        for tool in tools:
            # 搜索名称、描述和标签
            if (query_lower in tool.name.lower() or
                query_lower in tool.description.lower() or
                any(query_lower in tag.lower() for tag in tool.tags)):
                matches.append(tool.name)
        
        return matches
    
    async def get_usage_statistics(self) -> Dict[str, Any]:
        """获取使用统计"""
        return {
            "total_tools": len(self._enabled_tools) if self._enabled_tools else 0,
            "tool_stats": self._tool_stats,
            "categories": await self.list_tools_by_category()
        }
```

### 4. AI 服务集成架构

#### AI 提供商抽象基类
```python
# simacode/ai/providers/base.py
from abc import ABC, abstractmethod
from typing import AsyncGenerator, List, Dict, Any, Optional
from pydantic import BaseModel, Field
from enum import Enum
import time

class ChatRole(str, Enum):
    """聊天角色枚举"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"

class ChatMessage(BaseModel):
    """聊天消息模型"""
    role: ChatRole
    content: Optional[str] = None
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None

class TokenUsage(BaseModel):
    """Token使用统计"""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: Optional[int] = None  # 推理tokens (如 o1 模型)

class ChatResponse(BaseModel):
    """聊天响应模型"""
    message: ChatMessage
    usage: TokenUsage = TokenUsage()
    model: str
    cost_usd: float = 0.0
    finish_reason: Optional[str] = None
    response_time_ms: Optional[int] = None

class ModelInfo(BaseModel):
    """模型信息"""
    id: str
    name: str
    provider: str
    context_length: int
    supports_tools: bool = True
    supports_streaming: bool = True
    cost_per_input_token: float = 0.0
    cost_per_output_token: float = 0.0

class AIProvider(ABC):
    """AI提供商抽象基类"""
    
    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        max_retries: int = 3,
        timeout: int = 60
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.default_model = default_model
        self.max_retries = max_retries
        self.timeout = timeout
        self.current_model = default_model
        
        # 统计信息
        self.total_requests = 0
        self.total_cost = 0.0
        self.total_tokens = 0
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """提供商名称"""
        pass
    
    @abstractmethod
    async def chat_completion(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = "auto",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs
    ) -> AsyncGenerator[ChatResponse, None]:
        """聊天完成API"""
        pass
    
    @abstractmethod
    async def get_available_models(self) -> List[ModelInfo]:
        """获取可用模型列表"""
        pass
    
    @abstractmethod
    def calculate_cost(self, usage: TokenUsage, model: str) -> float:
        """计算API调用成本"""
        pass
    
    async def initialize(self) -> None:
        """初始化提供商"""
        pass
    
    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            models = await self.get_available_models()
            return {
                "status": "healthy",
                "provider": self.provider_name,
                "available_models": len(models),
                "base_url": self.base_url
            }
        except Exception as e:
            return {
                "status": "unhealthy", 
                "provider": self.provider_name,
                "error": str(e)
            }
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取使用统计"""
        return {
            "provider": self.provider_name,
            "total_requests": self.total_requests,
            "total_cost": self.total_cost,
            "total_tokens": self.total_tokens,
            "current_model": self.current_model
        }
    
    def _update_statistics(self, response: ChatResponse) -> None:
        """更新统计信息"""
        self.total_requests += 1
        self.total_cost += response.cost_usd
        self.total_tokens += response.usage.total_tokens
```

#### Deepseek 提供商实现
```python
# simacode/ai/providers/deepseek.py
import httpx
from openai import AsyncOpenAI
from typing import AsyncGenerator, List, Dict, Optional
import time
import json

from simacode.ai.providers.base import (
    AIProvider, ChatMessage, ChatResponse, TokenUsage, ModelInfo, ChatRole
)
from simacode.utils.retry import retry_with_backoff
from simacode.utils.logging import get_logger

logger = get_logger(__name__)

class DeepSeekProvider(AIProvider):
    """
    Deepseek AI 提供商实现
    支持 Deepseek 的各种模型，包括推理模型
    """
    
    def __init__(
        self, 
        api_key: str, 
        base_url: str = "https://api.deepseek.com/v1",
        default_model: str = "deepseek-chat",
        **kwargs
    ):
        super().__init__(api_key, base_url, default_model, **kwargs)
        
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=httpx.Timeout(self.timeout, connect=10.0),
            max_retries=self.max_retries
        )
        
        # Deepseek 模型定义
        self.models = {
            "deepseek-chat": ModelInfo(
                id="deepseek-chat",
                name="DeepSeek Chat",
                provider="deepseek",
                context_length=64000,
                supports_tools=True,
                supports_streaming=True,
                cost_per_input_token=0.14 / 1_000_000,
                cost_per_output_token=0.28 / 1_000_000
            ),
            "deepseek-coder": ModelInfo(
                id="deepseek-coder",
                name="DeepSeek Coder",
                provider="deepseek",
                context_length=64000,
                supports_tools=True,
                supports_streaming=True,
                cost_per_input_token=0.14 / 1_000_000,
                cost_per_output_token=0.28 / 1_000_000
            ),
            "deepseek-reasoner": ModelInfo(
                id="deepseek-reasoner",
                name="DeepSeek Reasoner",
                provider="deepseek",
                context_length=64000,
                supports_tools=False,  # 推理模型通常不支持工具
                supports_streaming=True,
                cost_per_input_token=1.0 / 1_000_000,
                cost_per_output_token=2.0 / 1_000_000
            )
        }
    
    @property
    def provider_name(self) -> str:
        return "deepseek"
    
    @retry_with_backoff(max_retries=3)
    async def chat_completion(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = "auto",
        temperature: Optional[float] = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs
    ) -> AsyncGenerator[ChatResponse, None]:
        """实现聊天完成功能"""
        
        start_time = time.time()
        model = model or self.current_model or self.default_model
        
        # 转换消息格式
        openai_messages = self._convert_messages(messages)
        
        # 构建请求参数
        request_params = {
            "model": model,
            "messages": openai_messages,
            "stream": stream,
            "temperature": temperature,
            **kwargs
        }
        
        if max_tokens:
            request_params["max_tokens"] = max_tokens
        
        # 添加工具定义（如果模型支持）
        model_info = self.models.get(model)
        if tools and model_info and model_info.supports_tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = tool_choice
        
        try:
            if stream:
                # 流式响应处理
                async for response in self._handle_streaming_response(
                    request_params, model, start_time
                ):
                    yield response
            else:
                # 非流式响应处理
                response = await self.client.chat.completions.create(**request_params)
                chat_response = self._convert_response(response, model, start_time)
                self._update_statistics(chat_response)
                yield chat_response
                
        except Exception as e:
            logger.error(f"Deepseek API 调用失败: {e}")
            error_response = ChatResponse(
                message=ChatMessage(
                    role=ChatRole.ASSISTANT,
                    content=f"API调用失败: {str(e)}"
                ),
                usage=TokenUsage(),
                model=model,
                cost_usd=0.0,
                response_time_ms=int((time.time() - start_time) * 1000)
            )
            yield error_response
    
    async def _handle_streaming_response(
        self, 
        request_params: Dict, 
        model: str, 
        start_time: float
    ) -> AsyncGenerator[ChatResponse, None]:
        """处理流式响应"""
        
        accumulated_content = ""
        accumulated_tool_calls = []
        total_usage = TokenUsage()
        
        try:
            stream = await self.client.chat.completions.create(**request_params)
            
            async for chunk in stream:
                if not chunk.choices:
                    continue
                    
                choice = chunk.choices[0]
                delta = choice.delta
                
                # 处理内容增量
                if delta.content:
                    accumulated_content += delta.content
                    
                    yield ChatResponse(
                        message=ChatMessage(
                            role=ChatRole.ASSISTANT,
                            content=delta.content
                        ),
                        usage=TokenUsage(),
                        model=model,
                        response_time_ms=int((time.time() - start_time) * 1000)
                    )
                
                # 处理工具调用
                if delta.tool_calls:
                    accumulated_tool_calls.extend(delta.tool_calls)
                    
                    yield ChatResponse(
                        message=ChatMessage(
                            role=ChatRole.ASSISTANT,
                            tool_calls=delta.tool_calls
                        ),
                        usage=TokenUsage(),
                        model=model,
                        response_time_ms=int((time.time() - start_time) * 1000)
                    )
                
                # 处理使用统计（通常在最后一个chunk）
                if chunk.usage:
                    total_usage = TokenUsage(
                        prompt_tokens=chunk.usage.prompt_tokens,
                        completion_tokens=chunk.usage.completion_tokens,
                        total_tokens=chunk.usage.total_tokens
                    )
                
                # 如果是最后一个chunk，发送完整响应
                if choice.finish_reason:
                    final_response = ChatResponse(
                        message=ChatMessage(
                            role=ChatRole.ASSISTANT,
                            content=accumulated_content,
                            tool_calls=accumulated_tool_calls if accumulated_tool_calls else None
                        ),
                        usage=total_usage,
                        model=model,
                        cost_usd=self.calculate_cost(total_usage, model),
                        finish_reason=choice.finish_reason,
                        response_time_ms=int((time.time() - start_time) * 1000)
                    )
                    
                    self._update_statistics(final_response)
                    yield final_response
                    
        except Exception as e:
            logger.error(f"流式响应处理失败: {e}")
            raise
    
    def _convert_messages(self, messages: List[ChatMessage]) -> List[Dict]:
        """转换消息格式为OpenAI格式"""
        openai_messages = []
        
        for msg in messages:
            openai_msg = {"role": msg.role.value}
            
            if msg.content:
                openai_msg["content"] = msg.content
            
            if msg.tool_calls:
                openai_msg["tool_calls"] = msg.tool_calls
                
            if msg.tool_call_id:
                openai_msg["tool_call_id"] = msg.tool_call_id
                
            if msg.name:
                openai_msg["name"] = msg.name
            
            openai_messages.append(openai_msg)
        
        return openai_messages
    
    def _convert_response(self, response, model: str, start_time: float) -> ChatResponse:
        """转换API响应为标准格式"""
        choice = response.choices[0]
        message = choice.message
        
        usage = TokenUsage()
        if response.usage:
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens
            )
        
        return ChatResponse(
            message=ChatMessage(
                role=ChatRole.ASSISTANT,
                content=message.content,
                tool_calls=message.tool_calls
            ),
            usage=usage,
            model=model,
            cost_usd=self.calculate_cost(usage, model),
            finish_reason=choice.finish_reason,
            response_time_ms=int((time.time() - start_time) * 1000)
        )
    
    async def get_available_models(self) -> List[ModelInfo]:
        """获取可用模型"""
        try:
            # 尝试从API获取模型列表
            models_response = await self.client.models.list()
            api_models = [model.id for model in models_response.data]
            
            # 返回我们支持的模型的交集
            available_models = []
            for model_id, model_info in self.models.items():
                if model_id in api_models:
                    available_models.append(model_info)
            
            return available_models
            
        except Exception as e:
            logger.warning(f"无法从API获取模型列表: {e}，使用预定义列表")
            return list(self.models.values())
    
    def calculate_cost(self, usage: TokenUsage, model: str) -> float:
        """计算成本"""
        model_info = self.models.get(model)
        if not model_info:
            return 0.0
        
        input_cost = usage.prompt_tokens * model_info.cost_per_input_token
        output_cost = usage.completion_tokens * model_info.cost_per_output_token
        
        return input_cost + output_cost
```

#### OneAPI 提供商实现
```python
# simacode/ai/providers/oneapi.py
from typing import AsyncGenerator, List, Dict, Optional
from openai import AsyncOpenAI
import time

from simacode.ai.providers.base import (
    AIProvider, ChatMessage, ChatResponse, TokenUsage, ModelInfo, ChatRole
)
from simacode.utils.retry import retry_with_backoff
from simacode.utils.logging import get_logger

logger = get_logger(__name__)

class OneAPIProvider(AIProvider):
    """
    OneAPI/NewAPI 提供商实现
    支持通过代理访问多种AI模型
    """
    
    def __init__(
        self, 
        api_key: str, 
        base_url: str,
        available_models: Optional[List[str]] = None,
        model_mapping: Optional[Dict[str, Dict]] = None,
        **kwargs
    ):
        super().__init__(api_key, base_url, **kwargs)
        
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=self.timeout,
            max_retries=self.max_retries
        )
        
        # 可用模型列表
        self.available_model_names = available_models or []
        
        # 模型映射配置（模型名 -> 模型信息）
        self.model_mapping = model_mapping or {}
        
        # 默认定价（当无法获取具体定价时使用）
        self.default_pricing = {
            "input": 0.5 / 1_000_000,
            "output": 1.0 / 1_000_000
        }
    
    @property
    def provider_name(self) -> str:
        return "oneapi"
    
    async def initialize(self) -> None:
        """初始化OneAPI提供商"""
        try:
            # 尝试获取可用模型
            models = await self.get_available_models()
            if models and not self.current_model:
                self.current_model = models[0].id
                
            logger.info(f"OneAPI初始化完成，可用模型: {len(models)}")
            
        except Exception as e:
            logger.warning(f"OneAPI初始化失败: {e}")
    
    @retry_with_backoff(max_retries=3)
    async def chat_completion(
        self,
        messages: List[ChatMessage],
        model: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        tool_choice: Optional[str] = "auto",
        temperature: Optional[float] = 0.7,
        max_tokens: Optional[int] = None,
        stream: bool = False,
        **kwargs
    ) -> AsyncGenerator[ChatResponse, None]:
        """实现聊天完成功能"""
        
        start_time = time.time()
        model = model or self.current_model or self.default_model
        
        if not model:
            error_response = ChatResponse(
                message=ChatMessage(
                    role=ChatRole.ASSISTANT,
                    content="错误: 未指定模型"
                ),
                usage=TokenUsage(),
                model="unknown",
                cost_usd=0.0
            )
            yield error_response
            return
        
        # 转换消息格式
        openai_messages = self._convert_messages(messages)
        
        # 构建请求参数
        request_params = {
            "model": model,
            "messages": openai_messages,
            "stream": stream,
            "temperature": temperature,
            **kwargs
        }
        
        if max_tokens:
            request_params["max_tokens"] = max_tokens
        
        # 添加工具定义（假设大多数模型支持）
        if tools:
            request_params["tools"] = tools
            request_params["tool_choice"] = tool_choice
        
        try:
            if stream:
                async for response in self._handle_streaming_response(
                    request_params, model, start_time
                ):
                    yield response
            else:
                response = await self.client.chat.completions.create(**request_params)
                chat_response = self._convert_response(response, model, start_time)
                self._update_statistics(chat_response)
                yield chat_response
                
        except Exception as e:
            logger.error(f"OneAPI 调用失败: {e}")
            error_response = ChatResponse(
                message=ChatMessage(
                    role=ChatRole.ASSISTANT,
                    content=f"OneAPI调用失败: {str(e)}"
                ),
                usage=TokenUsage(),
                model=model,
                cost_usd=0.0,
                response_time_ms=int((time.time() - start_time) * 1000)
            )
            yield error_response
    
    async def _handle_streaming_response(
        self, 
        request_params: Dict, 
        model: str, 
        start_time: float
    ) -> AsyncGenerator[ChatResponse, None]:
        """处理流式响应"""
        
        accumulated_content = ""
        accumulated_tool_calls = []
        total_usage = TokenUsage()
        
        try:
            stream = await self.client.chat.completions.create(**request_params)
            
            async for chunk in stream:
                if not chunk.choices:
                    continue
                    
                choice = chunk.choices[0]
                delta = choice.delta
                
                # 处理内容增量
                if delta.content:
                    accumulated_content += delta.content
                    
                    yield ChatResponse(
                        message=ChatMessage(
                            role=ChatRole.ASSISTANT,
                            content=delta.content
                        ),
                        usage=TokenUsage(),
                        model=model,
                        response_time_ms=int((time.time() - start_time) * 1000)
                    )
                
                # 处理工具调用
                if delta.tool_calls:
                    accumulated_tool_calls.extend(delta.tool_calls)
                    
                    yield ChatResponse(
                        message=ChatMessage(
                            role=ChatRole.ASSISTANT,
                            tool_calls=delta.tool_calls
                        ),
                        usage=TokenUsage(),
                        model=model,
                        response_time_ms=int((time.time() - start_time) * 1000)
                    )
                
                # 处理使用统计
                if chunk.usage:
                    total_usage = TokenUsage(
                        prompt_tokens=chunk.usage.prompt_tokens,
                        completion_tokens=chunk.usage.completion_tokens,
                        total_tokens=chunk.usage.total_tokens
                    )
                
                # 完成响应
                if choice.finish_reason:
                    final_response = ChatResponse(
                        message=ChatMessage(
                            role=ChatRole.ASSISTANT,
                            content=accumulated_content,
                            tool_calls=accumulated_tool_calls if accumulated_tool_calls else None
                        ),
                        usage=total_usage,
                        model=model,
                        cost_usd=self.calculate_cost(total_usage, model),
                        finish_reason=choice.finish_reason,
                        response_time_ms=int((time.time() - start_time) * 1000)
                    )
                    
                    self._update_statistics(final_response)
                    yield final_response
                    
        except Exception as e:
            logger.error(f"OneAPI流式响应处理失败: {e}")
            raise
    
    def _convert_messages(self, messages: List[ChatMessage]) -> List[Dict]:
        """转换消息格式"""
        openai_messages = []
        
        for msg in messages:
            openai_msg = {"role": msg.role.value}
            
            if msg.content:
                openai_msg["content"] = msg.content
            
            if msg.tool_calls:
                openai_msg["tool_calls"] = msg.tool_calls
                
            if msg.tool_call_id:
                openai_msg["tool_call_id"] = msg.tool_call_id
                
            if msg.name:
                openai_msg["name"] = msg.name
            
            openai_messages.append(openai_msg)
        
        return openai_messages
    
    def _convert_response(self, response, model: str, start_time: float) -> ChatResponse:
        """转换API响应"""
        choice = response.choices[0]
        message = choice.message
        
        usage = TokenUsage()
        if response.usage:
            usage = TokenUsage(
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                total_tokens=response.usage.total_tokens
            )
        
        return ChatResponse(
            message=ChatMessage(
                role=ChatRole.ASSISTANT,
                content=message.content,
                tool_calls=message.tool_calls
            ),
            usage=usage,
            model=model,
            cost_usd=self.calculate_cost(usage, model),
            finish_reason=choice.finish_reason,
            response_time_ms=int((time.time() - start_time) * 1000)
        )
    
    async def get_available_models(self) -> List[ModelInfo]:
        """获取可用模型"""
        try:
            # 从API获取模型列表
            models_response = await self.client.models.list()
            models = []
            
            for model in models_response.data:
                # 使用配置的模型映射或默认值
                model_config = self.model_mapping.get(model.id, {})
                
                model_info = ModelInfo(
                    id=model.id,
                    name=model_config.get("name", model.id),
                    provider="oneapi",
                    context_length=model_config.get("context_length", 4096),
                    supports_tools=model_config.get("supports_tools", True),
                    supports_streaming=model_config.get("supports_streaming", True),
                    cost_per_input_token=model_config.get(
                        "cost_per_input_token", 
                        self.default_pricing["input"]
                    ),
                    cost_per_output_token=model_config.get(
                        "cost_per_output_token", 
                        self.default_pricing["output"]
                    )
                )
                models.append(model_info)
            
            return models
            
        except Exception as e:
            logger.error(f"获取OneAPI模型列表失败: {e}")
            
            # 返回预配置的模型
            fallback_models = []
            for model_name in self.available_model_names:
                model_config = self.model_mapping.get(model_name, {})
                model_info = ModelInfo(
                    id=model_name,
                    name=model_config.get("name", model_name),
                    provider="oneapi",
                    context_length=model_config.get("context_length", 4096),
                    supports_tools=model_config.get("supports_tools", True),
                    supports_streaming=model_config.get("supports_streaming", True),
                    cost_per_input_token=model_config.get(
                        "cost_per_input_token", 
                        self.default_pricing["input"]
                    ),
                    cost_per_output_token=model_config.get(
                        "cost_per_output_token", 
                        self.default_pricing["output"]
                    )
                )
                fallback_models.append(model_info)
            
            return fallback_models
    
    def calculate_cost(self, usage: TokenUsage, model: str) -> float:
        """计算成本"""
        model_config = self.model_mapping.get(model, {})
        
        input_rate = model_config.get(
            "cost_per_input_token", 
            self.default_pricing["input"]
        )
        output_rate = model_config.get(
            "cost_per_output_token", 
            self.default_pricing["output"]
        )
        
        input_cost = usage.prompt_tokens * input_rate
        output_cost = usage.completion_tokens * output_rate
        
        return input_cost + output_cost
```

#### AI 提供商工厂
```python
# simacode/ai/providers/factory.py
from typing import Optional, Dict, Any
from simacode.ai.providers.base import AIProvider
from simacode.ai.providers.deepseek import DeepSeekProvider
from simacode.ai.providers.oneapi import OneAPIProvider
from simacode.config.manager import ConfigManager
from simacode.utils.logging import get_logger

logger = get_logger(__name__)

class AIProviderFactory:
    """AI提供商工厂类"""
    
    _providers = {
        "deepseek": DeepSeekProvider,
        "oneapi": OneAPIProvider
    }
    
    @classmethod
    def register_provider(cls, name: str, provider_class: type) -> None:
        """注册新的提供商"""
        cls._providers[name] = provider_class
        logger.info(f"注册AI提供商: {name}")
    
    @classmethod
    def get_available_providers(cls) -> List[str]:
        """获取可用提供商列表"""
        return list(cls._providers.keys())
    
    @classmethod
    def create_provider(
        cls,
        provider_name: Optional[str] = None,
        model: Optional[str] = None,
        config_manager: Optional[ConfigManager] = None,
        **kwargs
    ) -> AIProvider:
        """创建AI提供商实例"""
        
        # 获取配置
        if config_manager:
            global_config = config_manager.get_global_config()
            
            # 确定使用的提供商
            if not provider_name:
                provider_name = global_config.default_provider or "deepseek"
            
            # 获取提供商配置
            provider_config = global_config.ai_providers.get(provider_name)
            if not provider_config:
                raise ValueError(f"未找到提供商 '{provider_name}' 的配置")
            
            # 合并参数
            provider_kwargs = {
                "api_key": provider_config.api_key,
                "base_url": provider_config.base_url,
                "default_model": model or provider_config.default_model,
                "max_tokens": provider_config.max_tokens,
                "temperature": provider_config.temperature,
                **kwargs
            }
        else:
            # 使用传入的参数
            provider_name = provider_name or "deepseek"
            provider_kwargs = kwargs
        
        # 创建提供商实例
        provider_class = cls._providers.get(provider_name)
        if not provider_class:
            raise ValueError(f"不支持的提供商: {provider_name}")
        
        # 特殊处理不同提供商的参数
        if provider_name == "oneapi":
            # OneAPI 需要额外的配置
            if config_manager:
                # 从配置中获取模型映射等信息
                oneapi_config = global_config.ai_providers.get("oneapi", {})
                provider_kwargs.update({
                    "available_models": oneapi_config.get("available_models", []),
                    "model_mapping": oneapi_config.get("model_mapping", {})
                })
        
        try:
            provider = provider_class(**provider_kwargs)
            logger.info(f"创建AI提供商成功: {provider_name}")
            return provider
            
        except Exception as e:
            logger.error(f"创建AI提供商失败: {e}")
            raise
    
    @classmethod
    def create_default(cls, config_manager: Optional[ConfigManager] = None) -> AIProvider:
        """创建默认提供商"""
        return cls.create_provider(config_manager=config_manager)
```

## 主要应用流程

### 1. 应用启动流程

```
main() 入口函数
    ↓
Click 参数解析和验证
    ↓
setup_logging() - 配置日志系统
    ↓
判断执行模式:
    ├─ 非交互模式 → execute_single_query()
    └─ 交互模式 → SimacodeApp.run()
    ↓
组件初始化:
    ├─ ConfigManager.initialize()
    ├─ ToolManager.initialize() 
    ├─ AIProviderFactory.create_provider()
    └─ MCPClient.initialize() (可选)
    ↓
Textual 应用启动
```

### 2. REPL 交互循环

```
SimacodeApp.on_mount()
    ↓
MainScreen 组件渲染
    ↓
用户输入事件 (Input.Submitted)
    ↓
消息路由:
    ├─ 斜杠命令 → handle_slash_command()
    └─ 聊天消息 → handle_chat_message()
    ↓
AI 流式查询:
    ├─ 构建消息历史
    ├─ 获取工具定义
    ├─ 调用 AI 提供商
    └─ 处理流式响应
    ↓
UI 实时更新:
    ├─ MessageList 显示消息
    ├─ CostTracker 更新成本
    └─ ToolStatus 显示工具状态
```

### 3. 工具执行流程

```
AI 响应中检测工具调用
    ↓
ToolManager.execute_tool()
    ↓
输入验证:
    ├─ Pydantic 模型验证
    └─ 自定义业务逻辑验证
    ↓
权限检查:
    ├─ tool.needs_permissions()
    ├─ PermissionDialog 显示 (如需要)
    └─ 用户确认
    ↓
工具执行:
    ├─ tool.before_execute() 钩子
    ├─ tool.execute() 异步生成器
    ├─ 进度更新 (yield progress)
    ├─ 结果生成 (yield result)
    └─ tool.after_execute() 钩子
    ↓
结果处理和显示
```

### 4. AI 查询流程

```
用户消息输入
    ↓
消息历史构建 (ChatMessage 列表)
    ↓
工具模式生成 (JSON Schema)
    ↓
AI 提供商选择 (Deepseek/OneAPI)
    ↓
API 调用:
    ├─ 流式请求 (stream=True)
    ├─ 重试机制 (retry_with_backoff)
    └─ 超时控制
    ↓
流式响应处理:
    ├─ 内容块 → 实时显示
    ├─ 工具调用 → 工具执行
    ├─ Token 统计 → 成本计算
    └─ 完成信号 → 保存历史
    ↓
会话持久化
```

### 5. 配置管理流程

```
应用启动
    ↓
ConfigManager.initialize()
    ↓
配置文件发现:
    ├─ 全局配置 (~/.simacode/config.yaml)
    └─ 项目配置 (.simacode/config.yaml)
    ↓
配置加载和验证:
    ├─ YAML 解析
    ├─ Pydantic 模型验证
    └─ 默认值填充
    ↓
配置合并 (项目配置覆盖全局配置)
    ↓
组件初始化时使用配置
```

## 安全和权限架构

### 多层级安全控制

1. **输入验证层**
   - Pydantic 模型自动验证
   - 自定义业务逻辑验证
   - 危险命令模式检测
   - 输入长度和格式限制

2. **权限管理层**
   - 工具级权限控制
   - 用户确认对话框
   - 权限缓存机制
   - 审计日志记录

3. **执行隔离层**
   - 工作目录限制
   - 环境变量控制
   - 超时保护机制
   - 错误异常捕获

4. **数据保护层**
   - 敏感信息过滤
   - 配置文件加密
   - 会话数据保护
   - 网络通信加密

### 安全特性实现

```python
# 权限管理示例
class PermissionManager:
    async def check_permission(
        self, 
        tool_name: str, 
        input_data: Dict, 
        context: ToolContext
    ) -> bool:
        # 检查全局权限设置
        if context.permissions.get("global.dangerously_skip_permissions"):
            return True
        
        # 检查工具特定权限
        permission_key = f"tool.{tool_name}"
        if permission_key in context.permissions:
            return context.permissions[permission_key]
        
        # 检查自动批准列表
        auto_approve = context.permissions.get("auto_approve_tools", [])
        if tool_name in auto_approve:
            return True
        
        # 需要用户确认
        return False

# 输入验证示例
class SecurityValidator:
    DANGEROUS_PATTERNS = [
        r'rm\s+-rf\s+/',
        r'sudo\s+rm',
        r'format\s+[a-z]:',
        r'>\s*/dev/',
        r'dd\s+if='
    ]
    
    def validate_command(self, command: str) -> ValidationResult:
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                return ValidationResult(
                    is_valid=False,
                    message=f"检测到危险命令模式: {pattern}"
                )
        return ValidationResult(is_valid=True)
```

## 扩展性设计

### 1. 工具扩展机制

```python
# 自定义工具开发
class CustomTool(BaseTool):
    @property
    def name(self) -> str:
        return "custom_tool"
    
    @property
    def input_schema(self) -> Type[BaseModel]:
        return CustomToolInput
    
    async def execute(self, input_data, context):
        yield ToolResult(
            type=ToolResultType.RESULT,
            content="Custom tool executed successfully"
        )

# 工具注册
ToolRegistry.register_tool(CustomTool())
```

### 2. AI 提供商扩展

```python
# 自定义AI提供商
class CustomAIProvider(AIProvider):
    @property
    def provider_name(self) -> str:
        return "custom_ai"
    
    async def chat_completion(self, messages, **kwargs):
        # 实现自定义AI服务集成
        pass

# 提供商注册
AIProviderFactory.register_provider("custom_ai", CustomAIProvider)
```

### 3. UI 组件扩展

```python
# 自定义Textual组件
class CustomWidget(Widget):
    def compose(self) -> ComposeResult:
        yield Label("Custom Widget")
        yield Button("Action")
    
    async def on_button_pressed(self, event):
        # 处理自定义逻辑
        pass
```

### 4. 命令扩展

```python
# 自定义CLI命令
@main.command()
@click.argument('target')
def custom_command(target):
    """自定义命令描述"""
    # 实现自定义功能
    pass
```

## 性能优化策略

### 1. 异步处理优化

- **全异步架构**: 所有I/O操作使用asyncio
- **并发工具执行**: 支持多工具并行处理  
- **流式响应**: 实时用户反馈和渐进式渲染
- **连接池**: HTTP客户端连接复用

### 2. 缓存策略

- **配置缓存**: 减少文件系统访问
- **工具注册缓存**: 避免重复扫描和注册
- **AI响应缓存**: 相同查询的结果缓存
- **模型信息缓存**: 减少API调用

### 3. 内存管理

- **消息历史限制**: 自动清理过期消息
- **大对象流式处理**: 避免内存溢出
- **弱引用**: 避免循环引用导致的内存泄漏
- **定期垃圾回收**: 主动内存清理

### 4. 用户体验优化

- **快速启动**: 延迟加载非核心组件
- **智能预测**: 基于历史的工具推荐
- **快捷键支持**: 提高操作效率
- **主题切换**: 个性化用户界面

## 部署和分发

### 包管理配置

```toml
# pyproject.toml
[tool.poetry]
name = "simacode"
version = "1.0.0"
description = "Modern AI-powered programming assistant"
authors = ["SimaCode Team"]
license = "MIT"
readme = "README.md"
homepage = "https://github.com/QUSEIT/simacode"
repository = "https://github.com/QUSEIT/simacode"
keywords = ["ai", "programming", "assistant", "deepseek", "oneapi"]

[tool.poetry.dependencies]
python = "^3.10"
textual = "^0.40.0"
click = "^8.1.0"
pydantic = "^2.0.0"
openai = "^1.0.0"
httpx = "^0.25.0"
aiofiles = "^23.0.0"
pyyaml = "^6.0"
mcp = "^1.0.0"

[tool.poetry.group.dev.dependencies]
pytest = "^7.0.0"
pytest-asyncio = "^0.21.0"
black = "^23.0.0"
flake8 = "^6.0.0"
mypy = "^1.0.0"

[tool.poetry.scripts]
simacode = "simacode.main:main"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

### 安装和使用

```bash
# 从PyPI安装
pip install simacode

# 开发模式安装
git clone https://github.com/QUSEIT/simacode.git
cd simacode
poetry install

# 启动应用
simacode

# 查看帮助
simacode --help

# 配置AI提供商
simacode config set ai_providers.deepseek.api_key "your-key"
simacode config set ai_providers.deepseek.base_url "https://api.deepseek.com/v1"

# 单次查询模式
simacode --print "帮我创建一个Python HTTP服务器"
```

## 总结

SimaCode 作为现代化的 AI 编程助手，通过精心设计的 Python 架构实现了以下核心价值：

### 🎯 核心优势

1. **现代化技术栈**: 基于 Python 3.10+ 和 Textual，提供优秀的开发体验
2. **灵活的 AI 集成**: 支持 Deepseek、OneAPI 等多种经济实惠的 AI 服务
3. **强大的工具系统**: 可扩展的工具架构，支持复杂的编程任务
4. **安全优先设计**: 多层级权限控制和安全验证机制
5. **优秀的用户体验**: 响应式 TUI 界面和实时反馈系统

### 🚀 技术特色

- **全异步架构**: 高性能的并发处理能力
- **类型安全**: Pydantic 模型确保数据一致性和安全性
- **模块化设计**: 清晰的分层架构，易于维护和扩展
- **流式处理**: 实时的用户反馈和渐进式响应
- **配置驱动**: 灵活的多层级配置管理

### 🔧 扩展能力

- **工具插件**: 简单的工具开发和注册机制
- **AI 提供商**: 标准化的 AI 服务集成接口
- **UI 组件**: 基于 Textual 的自定义组件开发
- **MCP 协议**: 与其他 AI 工具的标准化集成

SimaCode 为 Python 开发者提供了一个功能完整、架构清晰、易于扩展的 AI 编程助手平台，充分发挥了 Python 生态系统的优势，同时保持了出色的性能和用户体验。
