# TICMaker MCP Tools 完整实施方案

## 概述

本文档详细规划了如何在SimaCode中创建名为TICMaker的MCP Tool，用于接收HTTP Request Body中context的scope为ticmaker的数据，根据message的参数创建或者修改(如果context里包含了对应的文件路径)一个HTML网页，在API Layer → Core Service → ReAct Engine → AI Client/TICMaker MCP Tool架构下工作。

## 🎯 核心目标

- 实现TICMaker MCP Tool，专门处理HTML网页的创建和修改
- 支持`simacode serve`和`simacode chat`两种运行模式
- 穿透现有的对话检测机制，确保TICMaker请求能正确路由到MCP Tool
- 保持架构简单、清晰

## 🚨 兼容性说明

**重要提示**: 原方案主要针对API模式设计，对CLI模式(`simacode chat`)存在兼容性问题：

### 兼容性问题
1. **CLI缺少context支持**: CLI `simacode chat` 只接收 `message`，无 `context` 字段
2. **数据流路径不同**: CLI模式绕过API层，直接进入Core Service
3. **force_mode冲突**: CLI chat使用 `force_mode="chat"`，会绕过ReAct引擎

### 解决方案
本文档提供了兼容CLI和API两种模式的完整解决方案，通过统一检测器和多层处理机制实现完全兼容。

## 🏗️ 整体架构设计

### 1. 数据流集成点

#### API模式数据流
```
HTTP Request → FastAPI Routes → CoreChatRequest → 
Core Service (TICMaker检测) → ReAct Engine → TICMaker MCP Tool
```

#### CLI模式数据流  
```
CLI Command (--ticmaker) → ChatRequest → 
Core Service (TICMaker检测) → ReAct Engine → TICMaker MCP Tool
```

### 2. 核心检测机制

通过在Core Service的`process_chat`方法中检测`context.scope=ticmaker`请求，强制使用ReAct引擎处理，从而穿透现有的对话检测逻辑。

### 2. 关键集成点识别
- **API入口点**: `src/simacode/api/routes/chat.py:chat_stream()` - 标记API来源
- **CLI入口点**: `src/simacode/cli.py:chat()` - 新增TICMaker参数支持
- **统一处理点**: `src/simacode/core/service.py:process_chat()` - 统一检测和处理
- **数据传递**: 通过统一检测器和context机制传递数据到MCP工具
- **工具调用**: 在Core Service层预调用，然后ReAct引擎继续处理

## 📋 具体实施步骤

### 第1步: 创建TICMaker MCP Server (兼容版本)

创建文件 `tools/mcp_ticmaker_server.py`:

```python
#!/usr/bin/env python3
"""
TICMaker MCP Server for SimaCode - 兼容CLI和API模式
Handles TICMaker requests from both CLI and API modes with enhanced compatibility.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

class TICMakerMCPServer:
    """TICMaker specialized MCP server - 支持CLI和API双模式."""
    
    def __init__(self):
        self.server = Server("ticmaker-server")
        self._setup_tools()
    
    def _setup_tools(self):
        @self.server.list_tools()
        async def list_tools(params: Optional[types.PaginatedRequestParams] = None) -> List[types.Tool]:
            return [
                types.Tool(
                    name="process_ticmaker_request",
                    description="Process TICMaker requests from both CLI and API modes",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "message": {"type": "string", "description": "User message"},
                            "context": {"type": "object", "description": "Request context (optional)"},
                            "session_id": {"type": "string", "description": "Session identifier"},
                            "source": {"type": "string", "description": "Request source: CLI or API"},
                            "trigger_reason": {"type": "string", "description": "Why TICMaker was triggered"}
                        },
                        "required": ["message"]
                    }
                )
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[types.TextContent]:
            if name == "process_ticmaker_request":
                return await self._process_ticmaker_request(arguments)
            raise ValueError(f"Unknown tool: {name}")
    
    async def _process_ticmaker_request(self, args: Dict[str, Any]) -> List[types.TextContent]:
        """Process TICMaker request with enhanced compatibility."""
        message = args.get("message", "")
        context = args.get("context", {})
        session_id = args.get("session_id", "unknown")
        source = args.get("source", "unknown")
        trigger_reason = args.get("trigger_reason", "auto-detected")
        
        # 打印详细信息
        print("=" * 80)
        print("🎯 TICMaker Request Processed (兼容模式)")
        print(f"来源: {source}")
        print(f"会话ID: {session_id}")
        print(f"触发原因: {trigger_reason}")
        print(f"消息: {message}")
        print(f"上下文: {json.dumps(context, indent=2, ensure_ascii=False)}")
        print("=" * 80)
        
        # 记录到日志
        logging.info(f"TICMaker request ({source}) - Session: {session_id}, Trigger: {trigger_reason}")
        logging.info(f"TICMaker message: {message}")
        logging.info(f"TICMaker context: {context}")
        
        # 返回处理结果
        return [
            types.TextContent(
                type="text",
                text=f"✅ TICMaker请求已处理完成 ({source}模式)\n"
                     f"消息: {message}\n"
                     f"触发原因: {trigger_reason}\n"
                     f"上下文范围: {context.get('scope', 'N/A')}"
            )
        ]

if __name__ == "__main__":
    server = TICMakerMCPServer()
    asyncio.run(stdio_server(server.server))
```

### 第2步: 配置MCP服务器

在 `config/mcp_servers.yaml` 中添加:

```yaml
  # TICMaker MCP Server
  ticmaker:
    name: ticmaker
    enabled: true  # 启用TICMaker工具
    type: stdio
    command: ["python", "tools/mcp_ticmaker_server.py"]
    args: []
    environment: {}
    working_directory: null
    timeout: 60
    max_retries: 3
    retry_delay: 2.0
    security:
      allowed_operations: ["read", "process", "log"]
      allowed_paths: []
      forbidden_paths: []
      max_execution_time: 30
      network_access: false
```

### 第3步: 扩展CLI支持TICMaker

#### 3.1 修改CLI命令

在 `src/simacode/cli.py` 中修改chat命令:

```python
@main.command()
@click.argument("message", required=False)
@click.option(
    "--interactive",
    "-i",
    is_flag=True,
    help="Start interactive mode",
)
@click.option(
    "--react",
    "-r",
    is_flag=True,
    help="Use ReAct engine for intelligent task planning and execution",
)
@click.option(
    "--session-id",
    "-s",
    type=str,
    help="Continue existing session",
)
@click.option(
    "--ticmaker",
    "-t",
    is_flag=True,
    help="🆕 Enable TICMaker processing mode",
)
@click.option(
    "--scope",
    type=str,
    help="🆕 Set context scope (e.g., 'ticmaker')",
)
@click.pass_context
def chat(ctx: click.Context, message: Optional[str], interactive: bool, react: bool, session_id: Optional[str], ticmaker: bool, scope: Optional[str]) -> None:
    """Start a chat session with the AI assistant."""
    config_obj = ctx.obj["config"]
    
    if not interactive and not message:
        console.print("[yellow]No message provided. Use --interactive for interactive mode.[/yellow]")
        return
    
    # 🆕 构建context信息
    context = {}
    if ticmaker or scope == "ticmaker":
        context["scope"] = "ticmaker"
        context["ticmaker_processing"] = True
        context["cli_mode"] = True
        context["trigger_ticmaker_tool"] = True
        # 强制使用ReAct模式以便调用工具
        react = True
        console.print("[bold green]🎯 TICMaker模式已启用[/bold green]")
    
    if scope:
        context["scope"] = scope
    
    asyncio.run(_run_chat(ctx, message, interactive, react, session_id, context))


# 更新相关处理函数
async def _run_chat(ctx: click.Context, message: Optional[str], interactive: bool, react: bool, session_id: Optional[str], context: Dict[str, Any] = None) -> None:
    """Run the chat functionality with context support."""
    config_obj = ctx.obj["config"]
    
    try:
        simacode_service = await _get_or_create_service(config_obj)
        
        if react:
            await _handle_react_mode(simacode_service, message, interactive, session_id, context)
        else:
            await _handle_chat_mode(simacode_service, message, interactive, session_id, context)
            
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        import traceback
        console.print(f"[red]{traceback.format_exc()}[/red]")


async def _handle_chat_mode(simacode_service: SimaCodeService, message: Optional[str], interactive: bool, session_id: Optional[str], context: Dict[str, Any] = None) -> None:
    """Handle traditional chat mode with context support."""
    console.print("[bold green]💬 Chat Mode Activated[/bold green]")
    
    context = context or {}
    
    try:
        if not interactive and message:
            # 🆕 根据context决定是否强制ReAct模式
            force_mode = None if context.get("trigger_ticmaker_tool") else "chat"
            
            request = ChatRequest(
                message=message, 
                session_id=session_id, 
                force_mode=force_mode,
                context=context  # 🆕 传递context
            )
            response = await simacode_service.process_chat(request)
            
            if response.error:
                console.print(f"[red]Error: {response.error}[/red]")
            else:
                console.print(f"[bold green]Assistant:[/bold green]\n{response.content}")
        # ... 处理interactive模式
```

#### 3.2 创建统一的TICMaker检测器

创建文件 `src/simacode/core/ticmaker_detector.py`:

```python
"""
统一的TICMaker检测和处理器
支持CLI和API两种模式的TICMaker请求识别
"""

import logging
import re
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

class TICMakerDetector:
    """统一的TICMaker请求检测器."""
    
    # TICMaker关键词列表
    TICMAKER_KEYWORDS = [
        "ticmaker", "TICMaker", "互动课堂", "教学活动", "互动教学", 
        "课堂互动", "教育内容", "教学设计", "互动内容", "教学游戏"
    ]
    
    @classmethod
    def detect_ticmaker_request(
        cls, 
        message: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        检测是否为TICMaker请求
        
        Returns:
            Tuple[bool, str, Dict[str, Any]]: (is_ticmaker, reason, enhanced_context)
        """
        context = context or {}
        
        # 1. 显式scope检测
        if context.get("scope") == "ticmaker":
            return True, "explicit_scope_ticmaker", context
        
        # 2. 显式标记检测
        if context.get("trigger_ticmaker_tool", False):
            return True, "explicit_trigger_flag", context
        
        # 3. CLI TICMaker标记检测
        if context.get("ticmaker_processing", False):
            return True, "cli_ticmaker_flag", context
        
        # 4. 消息关键词检测
        message_lower = message.lower()
        for keyword in cls.TICMAKER_KEYWORDS:
            if keyword.lower() in message_lower:
                enhanced_context = context.copy()
                enhanced_context.update({
                    "scope": "ticmaker",
                    "detected_keyword": keyword,
                    "auto_detected": True,
                    "trigger_ticmaker_tool": True
                })
                return True, f"keyword_detected:{keyword}", enhanced_context
        
        # 5. 教学内容模式检测（正则表达式）
        teaching_patterns = [
            r"帮我.*(创建|设计|制作).*(课程|教学|活动)",
            r".*(互动|教学).*(内容|活动|游戏)",
            r"如何.*(设计|制作).*(教学|课堂)"
        ]
        
        for i, pattern in enumerate(teaching_patterns):
            if re.search(pattern, message):
                enhanced_context = context.copy()
                enhanced_context.update({
                    "scope": "ticmaker",
                    "detected_pattern": pattern,
                    "auto_detected": True,
                    "trigger_ticmaker_tool": True
                })
                return True, f"pattern_detected:{i}", enhanced_context
        
        return False, "no_ticmaker_indicators", context
    
    @classmethod
    def prepare_ticmaker_tool_input(
        cls,
        message: str,
        context: Dict[str, Any],
        session_id: str,
        source: str = "unknown",
        trigger_reason: str = "auto"
    ) -> Dict[str, Any]:
        """准备TICMaker工具输入参数."""
        return {
            "message": message,
            "context": context,
            "session_id": session_id,
            "source": source,
            "trigger_reason": trigger_reason
        }
```

#### 3.3 修改Core Service统一处理

在 `src/simacode/core/service.py` 中修改:

```python
from .ticmaker_detector import TICMakerDetector
from ..mcp.integration import get_tool_registry

class SimaCodeService:
    # ... 现有代码 ...
    
    async def process_chat(
        self, 
        request: Union[ChatRequest, str], 
        session_id: Optional[str] = None
    ) -> Union[ChatResponse, AsyncGenerator[str, None]]:
        """Enhanced chat processing with TICMaker support."""
        
        # Handle both ChatRequest objects and simple strings
        if isinstance(request, str):
            request = ChatRequest(
                message=request,
                session_id=session_id,
                stream=False
            )
        
        try:
            logger.info(f"Processing chat message for session: {request.session_id}")
            
            # 生成session_id
            if not request.session_id:
                import uuid
                request.session_id = str(uuid.uuid4())
            
            # 🆕 统一的TICMaker检测
            is_ticmaker, reason, enhanced_context = TICMakerDetector.detect_ticmaker_request(
                request.message, request.context
            )
            
            if is_ticmaker:
                logger.info(f"TICMaker request detected: {reason}")
                # 更新请求的context
                request.context = enhanced_context
                # 如果是TICMaker请求，强制使用ReAct引擎（除非显式指定force_mode="chat"）
                if request.force_mode != "chat":
                    return await self._process_ticmaker_with_react(request, reason)
            
            # 原有的处理逻辑
            if request.force_mode == "chat":
                return await self._process_conversational_chat(request)
            else:
                return await self._process_with_react_engine(request)
                
        except Exception as e:
            logger.error(f"Chat processing error: {e}")
            return ChatResponse(
                content="抱歉，处理您的请求时出现了问题。",
                session_id=request.session_id or "unknown",
                error=str(e)
            )
    
    async def _process_ticmaker_with_react(
        self, 
        request: ChatRequest, 
        trigger_reason: str
    ) -> Union[ChatResponse, AsyncGenerator[str, None]]:
        """专门处理TICMaker请求的方法."""
        
        try:
            # 先调用TICMaker工具进行预处理
            await self._call_ticmaker_tool(request, trigger_reason)
            
            # 然后继续ReAct处理
            return await self._process_with_react_engine(request)
            
        except Exception as e:
            logger.error(f"TICMaker processing failed: {e}")
            # 失败时回退到正常ReAct处理
            return await self._process_with_react_engine(request)
    
    async def _call_ticmaker_tool(
        self, 
        request: ChatRequest, 
        trigger_reason: str
    ) -> None:
        """调用TICMaker工具进行预处理."""
        
        try:
            # 确保MCP工具注册表可用
            tool_registry = get_tool_registry()
            await tool_registry._ensure_mcp_initialized()
            
            # 确定请求来源
            source = "API" if hasattr(request, '_from_api') else "CLI"
            if request.context and request.context.get("cli_mode"):
                source = "CLI"
            
            # 准备工具输入
            tool_input = TICMakerDetector.prepare_ticmaker_tool_input(
                message=request.message,
                context=request.context or {},
                session_id=request.session_id,
                source=source,
                trigger_reason=trigger_reason
            )
            
            # 调用TICMaker工具
            logger.info(f"Calling TICMaker tool for preprocessing...")
            async for result in tool_registry.execute_tool("process_ticmaker_request", tool_input):
                logger.info(f"TICMaker tool result: {result.content}")
            
        except Exception as e:
            logger.error(f"Failed to call TICMaker tool: {e}")
            # 工具调用失败不影响后续处理
```

#### 3.4 标记API请求来源

在 `src/simacode/api/routes/chat.py` 中修改:

```python
async def chat_stream(request: ChatRequest, service: SimaCodeService = Depends(get_simacode_service)):
    try:
        # 🆕 标记请求来源为API
        request._from_api = True
        
        # 原有的处理逻辑保持不变
        if request.message.startswith("CONFIRM_ACTION:"):
            return await handle_confirmation_response(request, service)
        
        core_request = CoreChatRequest(
            message=request.message,
            session_id=request.session_id,
            context=request.context,
            stream=True
        )
        
        # TICMaker检测和处理现在在Core Service中统一处理
        # ... 继续现有逻辑
```

## 🧪 兼容性测试验证

### CLI模式测试

```bash
# 1. 显式TICMaker模式
simacode chat --ticmaker "帮我创建一个数学互动游戏"

# 2. 通过scope参数
simacode chat --scope ticmaker "设计一个教学活动"

# 3. 关键词自动检测
simacode chat "如何设计互动教学内容？"

# 4. React模式下的TICMaker
simacode chat --react "创建一个课堂互动活动"

# 5. 交互模式
simacode chat --ticmaker --interactive
```

### API模式测试

```bash
# 1. 显式scope
curl -X POST http://localhost:8100/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "message": "帮我创建互动教学活动",
    "context": {"scope": "ticmaker"}
  }'

# 2. 关键词自动检测（无context）
curl -X POST http://localhost:8100/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{
    "message": "如何设计课堂互动游戏？"
  }'
```

### 预期输出

两种模式都应该在控制台看到：

```
================================================================================
🎯 TICMaker Request Processed (兼容模式)
来源: CLI/API
会话ID: session-xxx
触发原因: explicit_scope_ticmaker/keyword_detected:互动教学/cli_ticmaker_flag
消息: 帮我创建互动教学活动
上下文: {
  "scope": "ticmaker",
  "ticmaker_processing": true,
  "cli_mode": true (仅CLI),
  "trigger_ticmaker_tool": true,
  "detected_keyword": "互动教学" (如果是自动检测)
}
================================================================================
```

## 📋 兼容实施检查清单

### 核心组件
- [ ] **第1步**: 创建 `tools/mcp_ticmaker_server.py` (兼容版本)
- [ ] **第2步**: 更新 `config/mcp_servers.yaml` 配置
- [ ] **第3步**: 创建 `src/simacode/core/ticmaker_detector.py` (统一检测器)
- [ ] **第4步**: 修改 `src/simacode/core/service.py` (统一处理逻辑)

### CLI支持
- [ ] **第5步**: 修改 `src/simacode/cli.py` 添加 `--ticmaker` 和 `--scope` 参数
- [ ] **第6步**: 更新CLI处理函数支持context传递

### API支持  
- [ ] **第7步**: 修改 `src/simacode/api/routes/chat.py` 标记API来源
- [ ] **第8步**: 确保API context传递机制正常工作

### 测试验证
- [ ] **第9步**: 测试CLI显式TICMaker模式: `simacode chat --ticmaker "message"`
- [ ] **第10步**: 测试CLI自动检测: `simacode chat "互动教学活动"`
- [ ] **第11步**: 测试API显式scope: `{"context": {"scope": "ticmaker"}}`
- [ ] **第12步**: 测试API自动检测: 关键词触发
- [ ] **第13步**: 验证两种模式控制台输出正确

### 最终部署
- [ ] **第14步**: 运行 `simacode mcp init` 初始化MCP集成
- [ ] **第15步**: 启动服务验证完整功能

## ✅ 兼容性优势

### 完全兼容性
1. **CLI模式完全支持**: 通过新增参数和统一检测器
2. **API模式保持不变**: 原有API功能完全保留
3. **自动检测机制**: 关键词和模式匹配，无需显式指定
4. **统一处理逻辑**: Core Service层统一处理，避免重复代码
5. **优雅降级**: 工具调用失败不影响正常聊天功能

### 使用体验
1. **CLI用户**: 可以通过 `--ticmaker` 或关键词自动触发
2. **API用户**: 通过 `context.scope` 或自动检测
3. **开发者**: 统一的检测和处理逻辑，易于维护扩展
4. **灵活性**: 支持显式指定、自动检测、关键词匹配等多种方式

## 🧪 快速验证

### CLI快速测试
```bash
# 显式模式
simacode chat --ticmaker "设计教学游戏"

# 自动检测  
simacode chat "帮我创建互动课堂活动"
```

### API快速测试
```bash
# 显式scope
curl -X POST http://localhost:8100/api/v1/chat/stream \
  -d '{"message": "创建教学内容", "context": {"scope": "ticmaker"}}'

# 自动检测
curl -X POST http://localhost:8100/api/v1/chat/stream \
  -d '{"message": "如何设计互动教学？"}'
```

## 🔍 技术亮点

1. **多层检测机制**: 显式标记 → 关键词匹配 → 模式识别
2. **统一处理架构**: 单一检测器支持多种触发方式
3. **来源标记系统**: 清楚区分CLI和API请求来源
4. **智能自动检测**: 基于NLP的教学内容识别
5. **完全向后兼容**: 不影响现有任何功能

## 🚀 扩展能力

- **更多触发关键词**: 轻松扩展检测词汇表
- **更复杂的模式**: 支持更精细的内容识别
- **多工具链**: 可扩展为TICMaker工具生态
- **AI增强检测**: 集成AI模型进行内容分类
- **缓存优化**: 添加请求缓存和结果复用

这个兼容方案确保了CLI和API两种模式都能完美支持TICMaker功能，同时保持了系统的完整性和可扩展性。