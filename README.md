# 思码 (SimaCode)

[English Version / 英文版本](README_EN.md)

基于 Python 构建的现代 AI 编排工作流框架，具备智能 ReAct（推理与行动）机制和全面的工作流编排能力。思码采用双模式运行：既可作为独立的终端工作流代理直接执行工作流，也可作为后端 API 服务，为企业工作流集成和自动化提供 RESTful API 和 WebSocket 服务。

## 🚀 特性

### 核心能力
- **智能工作流编排**：先进的 ReAct 框架，理解并执行复杂的工作流任务
- **多智能体工作流系统**：计划中的专业化智能体，用于不同工作流操作（文件、代码分析、系统命令、数据处理）
- **MCP 工作流集成**：完全支持模型上下文协议工具，提供无缝的 AI 驱动和直接命令行工作流访问
- **安全工作流执行**：全面的权限系统和工作流操作安全检查
- **可扩展工作流架构**：工具注册系统，支持自定义工作流能力和 MCP 工具插件
- **多提供商 AI 支持**：目前支持 OpenAI 进行工作流决策，计划支持 Anthropic 和其他提供商

### 双模式运行
- **终端工作流代理模式**：直接命令行交互，用于个人工作流执行和开发
- **后端工作流服务模式**：RESTful API 和 WebSocket 端点，用于企业工作流集成
- **DevGenius Agent 集成**：通过标准化工作流 API 与 DevGenius Agent 框架无缝集成

## 📦 安装

### 先决条件

- Python 3.10 或更高版本
- Poetry（用于依赖管理）

### 从源码安装

```bash
# 克隆仓库
git clone https://github.com/QUSEIT/simacode.git
cd simacode

# 安装依赖
poetry install

# 安装开发依赖（可选）
poetry install --with dev
```

### 快速开始

#### 终端工作流代理模式
```bash
# 初始化新的工作流项目
simacode init

# 启动交互式工作流模式
simacode chat --interactive

# 运行单个工作流命令
simacode chat "创建一个完整的 Python 项目，包含测试和文档"

# 检查工作流配置
simacode config
```

#### 后端工作流服务模式
```bash
# 启动工作流编排服务器
simacode serve --host 0.0.0.0 --port 8000

# 使用自定义工作流配置启动
simacode api --config workflow_config.yaml

# 检查工作流 API 状态
curl http://localhost:8000/health
```

## 🎯 使用方法

### 终端工作流代理模式

```bash
# 显示帮助
simacode --help

# 显示版本
simacode --version

# 初始化工作流项目
simacode init

# 启动工作流执行
simacode chat "您的工作流请求"

# 交互式工作流模式
simacode chat --interactive

# 使用 ReAct 引擎进行智能工作流编排
simacode chat --react "创建一个完整的 Python 项目，包含测试和文档"

# 交互式 ReAct 工作流模式
simacode chat --react --interactive

# 恢复工作流会话
simacode chat --react --session-id <session_id>

# 工作流配置管理
simacode config --check
```

### 后端工作流服务模式

```bash
# 启动工作流编排服务器
simacode serve --host 0.0.0.0 --port 8000

# 使用自定义工作流配置启动
simacode api --config workflow_config.yaml --workers 4

# 使用特定 AI 提供商启动工作流
simacode serve --ai-provider anthropic --model claude-3

# 启用开发模式并自动重载
simacode serve --dev --reload
```

#### 工作流 API 端点

工作流编排服务器运行后，您可以访问：

```bash
# 健康检查
GET /health

# 单次工作流完成
POST /api/v1/chat/
Content-Type: application/json
{
  "message": "创建一个完整的 Python 项目，包含测试和文档",
  "session_id": "可选的工作流会话ID"
}

# 流式工作流执行
POST /api/v1/chat/stream/

# ReAct 工作流编排
POST /api/v1/react/execute/
{
  "task": "创建一个包含 CI/CD 流水线的综合性 Python 项目",
  "context": {}
}

# WebSocket 实时工作流交互
WS /api/v1/chat/ws/

# WebSocket ReAct 工作流执行
WS /api/v1/react/ws/
```

## 🔧 MCP 工作流工具集成

思码为模型上下文协议（MCP）工具提供全面支持，既可以进行 AI 辅助的工作流编排，也可以直接命令行访问工作流工具。

### 使用 MCP 工具的两种方式

#### 1. AI 辅助工作流使用（ReAct 模式）
让 AI 基于您的自然语言工作流请求智能编排和使用 MCP 工作流工具：

```bash
# 启动带有 MCP 工具的交互式 ReAct 工作流模式
simacode chat --react --interactive

# 工作流对话示例：
> 创建一个数据处理工作流，读取 config.yaml，处理数据并生成报告
# AI 将自动编排文件工具、数据处理工具和报告工具

> 构建一个网页抓取工作流，从多个 URL 提取数据并整合结果
# AI 将编排网页抓取 MCP 工具和数据整合工作流

> 设置完整的项目工作流，包含测试、文档和部署
# AI 将编排文件管理、测试工具和部署工作流工具
```

#### 2. 直接工作流工具执行
精确控制特定 MCP 工作流工具的直接执行：

```bash
# 初始化 MCP 工作流集成
simacode mcp init

# 列出所有可用的工作流工具
simacode mcp list

# 搜索特定的工作流工具
simacode mcp search "file"
simacode mcp search "workflow" --fuzzy

# 获取详细的工作流工具信息
simacode mcp info file_tools:read_file

# 使用参数执行工作流工具
simacode mcp run file_tools:read_file --param file_path=/path/to/file.txt

# 交互式工作流参数输入
simacode mcp run web_tools:fetch_url --interactive

# 使用 JSON 工作流参数执行
simacode mcp run data_tools:process_json --params '{"data": {"key": "value"}, "operation": "filter"}'

# 试运行以查看将执行的工作流
simacode mcp run my_workflow_tool --param input=test --dry-run

# 显示工作流系统状态
simacode mcp status
```

### MCP 配置

创建 MCP 配置文件来定义您的工具服务器：

```yaml
# .simacode/mcp.yaml
servers:
  file_tools:
    command: ["python", "-m", "file_mcp_server"]
    args: ["--port", "3001"]
    env:
      SERVER_NAME: "file_tools"
    working_directory: "/tmp"

  web_tools:
    command: ["node", "web-mcp-server.js"]
    args: ["--config", "web-config.json"]
    env:
      NODE_ENV: "production"

  data_tools:
    command: ["./data-server"]
    args: ["--mode", "mcp"]

discovery:
  mode: "active"          # 自动发现新工具
  interval: 60            # 每 60 秒检查一次
  auto_register: true     # 自动注册新工具

updates:
  enable_hot_updates: true    # 热重载工具变更
  batch_updates: true         # 批量处理多个更新
  max_concurrent: 5           # 最大并发更新数

namespaces:
  require_namespaces: true       # 使用命名空间避免冲突
  conflict_resolution: "suffix"  # 名称冲突解决方式
  auto_create_aliases: true      # 为工具创建短别名
```

### MCP 故障排除

#### 网络代理问题

⚠️ **重要提示**：如果您使用网络代理（HTTP/HTTPS/SOCKS 代理），可能会干扰 MCP WebSocket 连接并导致初始化失败。

**常见错误症状：**
- `simacode mcp init` 因 WebSocket 连接错误失败
- 错误消息如 "python-socks is required to use a SOCKS proxy"
- MCP 服务在 `simacode mcp status` 中显示为 "Disabled"

**解决方案：**

1. **临时禁用代理**：如果可能，在 MCP 初始化期间临时禁用代理：
   ```bash
   # 临时禁用代理
   unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY

   # 初始化 MCP
   simacode mcp init

   # 如需要可重新启用代理
   export http_proxy=您的代理URL
   ```

2. **配置代理绕过**：将 localhost 和 MCP 服务端口添加到代理绕过列表：
   ```bash
   # 对于大多数代理工具，将这些添加到 no_proxy
   export no_proxy="localhost,127.0.0.1,*.local"
   ```

3. **安装代理依赖**：如果必须使用 SOCKS 代理，请安装所需依赖：
   ```bash
   pip install python-socks
   ```

4. **检查 MCP 服务状态**：解决代理问题后，验证 MCP 是否正常工作：
   ```bash
   simacode mcp status
   simacode chat --react "测试 MCP 功能"
   ```

**为什么会发生这种情况：**
- MCP 工具通过 WebSocket 连接与 localhost 通信
- 代理可能会拦截这些本地连接
- 某些代理配置需要额外的依赖，如 `python-socks`
- WebSocket 协议对代理干扰较为敏感

### MCP 工具示例

#### 文件操作
```bash
# 读取文件
simacode mcp run file_tools:read_file --param file_path=config.yaml

# 写入文件
simacode mcp run file_tools:write_file \
  --param file_path=output.txt \
  --param content="你好，世界！" \
  --param append=false
```

#### 网络操作
```bash
# 获取 URL 内容
simacode mcp run web_tools:fetch_url --param url=https://api.github.com/users/octocat

# 抓取网页
simacode mcp run web_tools:scrape_page \
  --param url=https://example.com \
  --param selector="h1" \
  --param extract=text
```

#### 数据处理
```bash
# 处理 JSON 数据
simacode mcp run data_tools:process_json \
  --params '{"data": [1,2,3,4,5], "operation": "filter", "parameters": {"min": 3}}'
```

#### 交互式使用
```bash
# 交互式模式引导您完成参数输入
simacode mcp run complex_tool --interactive

# 交互式会话示例：
Tool: complex_tool
Description: 具有多个参数的复杂工具

file_path (输入文件路径) [必需]: /path/to/input.txt
operation (要执行的操作) [可选]: process
options (其他选项，JSON 格式) [可选]: {"verbose": true}
```

### MCP 工具开发

要集成您自己的 MCP 工具：

1. **开发 MCP 服务器**：创建实现 MCP 协议的服务器
2. **添加到配置**：将服务器配置添加到您的 MCP 配置文件
3. **自动发现**：工具将被自动发现和注册
4. **AI 集成**：工具对 AI 和直接 CLI 使用均可用

最小 MCP 服务器配置示例：
```yaml
servers:
  my_custom_tools:
    command: ["python", "-m", "my_mcp_server"]
    args: ["--port", "3000"]
    env:
      DEBUG: "true"
```

### MCP 使用场景

#### 何时使用 AI 辅助模式（ReAct）
✅ **最适合：**
- 探索性任务，不确定使用哪些工具
- 需要多个工具的复杂工作流
- 自然语言问题描述
- 了解可用工具
- 需要智能规划和决策的任务

**示例：**
```bash
simacode chat --react --interactive
> "我需要分析 data.json 中的 JSON 数据，提取用户信息，并保存为 CSV 文件"
# AI 将自动：
# 1. 使用文件工具读取 data.json
# 2. 使用数据处理工具提取用户信息
# 3. 使用文件工具写入 CSV 输出
```

#### 何时使用直接执行
✅ **最适合：**
- 精确控制工具执行
- 脚本编写和自动化
- 已知工作流和特定参数
- 测试单个工具
- 与其他命令行工具集成

**示例：**
```bash
# 精确、可脚本化的工具执行
simacode mcp run file_tools:read_file --param file_path=data.json | \
simacode mcp run data_tools:extract_users --param format=csv | \
simacode mcp run file_tools:write_file --param file_path=users.csv
```

#### 对比表

| 方面 | AI 辅助（ReAct） | 直接执行 |
|--------|---------------------|------------------|
| **控制** | AI 决定工具和参数 | 用户完全控制 |
| **学习曲线** | 自然语言，易于开始 | 需要工具知识 |
| **灵活性** | 适应复杂场景 | 精确、可预测 |
| **自动化** | 交互式、对话式 | 可脚本化、管道友好 |
| **错误处理** | AI 可重试和适应 | 手动错误处理 |
| **使用场景** | 探索、复杂任务 | 自动化、精确工作流 |

### 配置

思码使用分层配置系统：

1. **运行时配置**（CLI 参数）
2. **项目配置**（`.simacode/config.yaml`）
3. **用户配置**（`~/.simacode/config.yaml`）
4. **默认配置**（内置）

#### 环境变量

- `SIMACODE_API_KEY`：您的 AI 提供商 API 密钥
- `OPENAI_API_KEY`：OpenAI 的替代密钥

#### 配置示例

```yaml
# .simacode/config.yaml
project_name: "我的超棒项目"

ai:
  provider: "openai"
  model: "gpt-4"
  temperature: 0.1

security:
  allowed_paths:
    - "./src"
    - "./tests"

logging:
  level: "DEBUG"
  file_path: ".simacode/logs/simacode.log"
```

## 🏗️ 架构

思码采用清晰的双模式架构，具有不同的层次，支持终端和 API 操作：

### 双模式架构

#### **核心服务层**
- **统一业务逻辑**：共享的 ReAct 引擎、工具系统和 AI 集成
- **配置管理**：基于 YAML 的配置，使用 Pydantic 验证
- **会话管理**：多用户会话处理和持久化
- **安全框架**：全面的基于权限的访问控制

#### **接口层**
- **CLI 层**：带有 Click 的命令行界面，用于终端 AI Agent 模式
- **API 层**：基于 FastAPI 的 RESTful 和 WebSocket 服务，用于后端集成
- **两种模式共享**：相同的核心能力，确保功能一致性

### 核心组件

#### ✅ **已实现组件**
- **CLI 层**：带有 Click 和 MCP 工具命令的命令行界面
- **配置**：基于 YAML 的配置，使用 Pydantic 验证
- **日志记录**：带有 Rich 格式化的结构化日志
- **ReAct 引擎**：智能任务规划和执行，集成 MCP 工具
- **工具系统**：可扩展框架，内置工具（bash、file_read、file_write）
- **MCP 集成**：完整的模型上下文协议支持，包括：
  - **工具包装器**：MCP 工具与思码的无缝集成
  - **工具注册表**：集中管理和命名空间处理
  - **自动发现**：智能工具发现和注册
  - **动态更新**：热重载和实时工具更新
  - **统一接口**：AI 辅助和直接 CLI 访问
- **AI 集成**：OpenAI 客户端，带有对话管理
- **安全**：全面的基于权限的访问控制
- **会话管理**：会话处理和持久化

#### 🚧 **计划组件**
- **API 层**：基于 FastAPI 的 RESTful 和 WebSocket 服务
- **多用户支持**：API 模式的并发会话处理
- **异步任务处理**：长时间运行操作的后台任务执行
- **多智能体系统**：针对不同操作的专业化智能体
- **多提供商 AI**：支持 Anthropic、Azure、Google AI 提供商
- **高级安全**：增强的沙盒执行和资源限制

### 技术栈

#### **核心技术**
- **运行时**：Python 3.10+
- **包管理**：Poetry
- **配置**：Pydantic + YAML
- **日志记录**：Rich + Python logging
- **测试**：pytest + pytest-asyncio
- **代码质量**：Black、isort、flake8、mypy

#### **终端 AI Agent 模式**
- **CLI 框架**：Click
- **交互界面**：Rich 用于增强终端显示

#### **后端 API 服务模式**
- **Web 框架**：FastAPI（计划中）
- **WebSocket**：原生 FastAPI WebSocket 支持
- **异步处理**：asyncio + async queues
- **API 文档**：OpenAPI/Swagger 自动生成

## 🧪 开发

### 设置开发环境

```bash
# 安装开发依赖
poetry install --with dev

# 设置 pre-commit 钩子
poetry run pre-commit install

# 运行测试
poetry run pytest

# 运行带覆盖率的测试
poetry run pytest --cov=simacode

# 格式化代码
poetry run black .
poetry run isort .

# 类型检查
poetry run mypy src/simacode

# 代码检查
poetry run flake8 src/simacode
```

### 项目结构

```
simacode/
├── src/simacode/           # 主包
│   ├── __init__.py        # 包初始化
│   ├── __main__.py        # CLI 入口点
│   ├── cli.py             # 命令行界面
│   ├── cli_mcp.py         # MCP 命令行界面
│   ├── config.py          # 配置管理
│   ├── logging_config.py  # 日志设置
│   ├── core/              # 核心服务层
│   │   ├── __init__.py    # 核心模块初始化
│   │   └── service.py     # 统一的 SimaCodeService
│   ├── ai/                # AI 客户端实现
│   │   ├── __init__.py    # AI 模块初始化
│   │   ├── base.py        # AI 客户端抽象
│   │   ├── factory.py     # AI 客户端工厂
│   │   ├── openai_client.py # OpenAI 集成
│   │   └── conversation.py  # 对话管理
│   ├── api/               # FastAPI Web 服务
│   │   ├── __init__.py    # API 模块初始化
│   │   ├── app.py         # FastAPI 应用
│   │   ├── models.py      # API 数据模型
│   │   ├── dependencies.py # 依赖注入
│   │   ├── chat_confirmation.py # 聊天确认处理
│   │   └── routes/        # API 路由处理器
│   │       ├── __init__.py # 路由初始化
│   │       ├── chat.py    # 聊天端点
│   │       ├── chat_safe.py # 安全聊天端点
│   │       ├── config.py  # 配置端点
│   │       ├── health.py  # 健康检查端点
│   │       ├── react.py   # ReAct 端点
│   │       ├── sessions.py # 会话端点
│   │       └── tasks.py   # 任务端点
│   ├── react/             # ReAct 工作流引擎
│   │   ├── __init__.py    # ReAct 模块初始化
│   │   ├── engine.py      # 主 ReAct 工作流引擎
│   │   ├── planner.py     # 任务规划
│   │   ├── evaluator.py   # 结果评估
│   │   ├── confirmation_manager.py # 用户确认处理
│   │   ├── exceptions.py  # ReAct 异常
│   │   └── mcp_integration.py # MCP 集成
│   ├── mcp/               # MCP（模型上下文协议）集成
│   │   ├── __init__.py    # MCP 模块初始化
│   │   ├── client.py      # MCP 客户端实现
│   │   ├── config.py      # MCP 配置
│   │   ├── connection.py  # 连接管理
│   │   ├── discovery.py   # 工具发现
│   │   ├── auto_discovery.py # 自动工具发现
│   │   ├── dynamic_updates.py # 动态工具更新
│   │   ├── exceptions.py  # MCP 异常
│   │   ├── health.py      # 健康监控
│   │   ├── integration.py # 集成工具
│   │   ├── namespace_manager.py # 命名空间管理
│   │   ├── protocol.py    # 协议实现
│   │   ├── server_manager.py # 服务器管理
│   │   ├── tool_registry.py # 工具注册表
│   │   ├── tool_wrapper.py # 工具包装器
│   │   └── async_integration.py # 异步集成
│   ├── tools/             # 内置工具系统
│   │   ├── __init__.py    # 工具模块初始化
│   │   ├── base.py        # 工具抽象
│   │   ├── bash.py        # Bash 执行工具
│   │   ├── file_read.py   # 文件读取工具
│   │   ├── file_write.py  # 文件写入工具
│   │   ├── smc_content_coder.py # 内容编码工具
│   │   └── universal_ocr/ # 通用 OCR 工具
│   │       ├── __init__.py # OCR 模块初始化
│   │       ├── config.py  # OCR 配置
│   │       ├── core.py    # OCR 核心功能
│   │       ├── file_processor.py # 文件处理
│   │       ├── input_models.py # 输入数据模型
│   │       ├── test_basic.py # 基础测试
│   │       └── engines/   # OCR 引擎
│   │           ├── __init__.py # 引擎初始化
│   │           ├── base.py # 基础引擎
│   │           └── claude_engine.py # Claude OCR 引擎
│   ├── permissions/       # 安全和权限
│   │   ├── __init__.py    # 权限模块初始化
│   │   ├── manager.py     # 权限管理
│   │   └── validators.py  # 安全验证器
│   ├── session/           # 会话管理
│   │   ├── __init__.py    # 会话模块初始化
│   │   └── manager.py     # 会话处理
│   ├── services/          # 应用服务
│   │   ├── __init__.py    # 服务模块初始化
│   │   └── react_service.py # ReAct 服务层
│   ├── utils/             # 工具模块
│   │   ├── __init__.py    # 工具模块初始化
│   │   ├── config_loader.py # 配置加载器
│   │   ├── mcp_logger.py  # MCP 日志工具
│   │   └── task_summary.py # 任务摘要工具
│   └── universalform/     # 通用表单处理
│       ├── __init__.py    # 通用表单初始化
│       └── app.py         # 表单应用
├── tests/                 # 测试套件
│   ├── integration/       # 集成测试
│   └── mcp/               # MCP 特定测试
├── tools/                 # 外部 MCP 工具
├── docs/                  # 文档（有组织的结构）
│   ├── README.md          # 文档导航
│   ├── 01-core/           # 核心项目文档
│   ├── 02-architecture/   # 架构设计文档
│   ├── 03-features/       # 功能规范
│   ├── 04-development/    # 开发指南
│   ├── 05-tools/          # 工具集成指南
│   ├── 06-api/            # API 文档
│   ├── 07-testing/        # 测试文档
│   ├── 08-deployment/     # 部署文档
│   ├── 09-troubleshooting/ # 问题解决指南
│   └── 10-references/     # 参考资料
├── website/               # 官方网站（MkDocs）
│   ├── mkdocs.yml         # 网站配置
│   └── docs/              # 网站内容
│       ├── index.md       # 主页
│       ├── assets/        # 网站资源
│       └── styles/        # 自定义样式
├── demo/                  # 演示脚本和示例
├── scripts/               # 构建和工具脚本
├── .simacode/             # 本地配置
│   ├── logs/              # 应用日志
│   ├── mcp/               # MCP 数据
│   └── sessions/          # 会话数据
└── pyproject.toml         # 项目配置
```

## 🧪 测试

运行测试套件：

```bash
# 运行所有测试
poetry run pytest

# 运行带覆盖率的测试
poetry run pytest --cov=simacode --cov-report=html

# 运行特定测试文件
poetry run pytest tests/test_cli.py

# 运行带详细输出的测试
poetry run pytest -v
```

## 📋 开发路线图

### 第 1 阶段：基础设施 ✅ **已完成**
- [x] 基于 Click 框架的基础 CLI 结构
- [x] 分层配置系统（YAML + 环境变量）
- [x] 带有结构化输出的 Rich 日志框架
- [x] 基于 Poetry 的项目设置和依赖管理

### 第 2 阶段：AI 集成 ✅ **已完成**
- [x] 带有异步支持的 OpenAI API 客户端
- [x] 带有上下文处理的对话管理
- [x] 消息历史和会话持久化
- [x] 实时交互的流式响应

### 第 3 阶段：工具系统 ✅ **已完成**
- [x] 带有权限的文件操作（读/写）
- [x] 带有安全控制的 Bash 执行
- [x] 全面的权限系统
- [x] 可扩展的工具注册框架

### 第 4 阶段：ReAct 工作流引擎 ✅ **已完成**
- [x] 智能任务规划和分解
- [x] 工具编排和执行协调
- [x] 强大的错误处理和恢复
- [x] 带有状态持久化的会话管理
- [x] 安全的用户确认机制

### 第 5 阶段：MCP 集成 ✅ **已完成**
- [x] **完整的 MCP 协议支持**：完整的模型上下文协议实现
- [x] **工具发现和注册**：自动发现和命名空间管理
- [x] **动态更新**：工具的热重载能力
- [x] **双访问模式**：AI 辅助和直接 CLI 工具执行
- [x] **健康监控**：连接状态和工具可用性跟踪
- [x] **异步集成**：后台任务处理和并发执行

### 第 6 阶段：双模式架构 ✅ **已完成**
- [x] **核心服务层**：统一的 SimaCodeService 抽象
- [x] **FastAPI 集成**：包含 13 个端点模块的完整 RESTful API
- [x] **WebSocket 支持**：聊天和 ReAct 的实时通信
- [x] **多用户会话管理**：并发会话处理
- [x] **OpenAPI 文档**：自动生成的 Swagger 文档
- [x] **可选依赖**：API 依赖不可用时的优雅降级

### 第 7 阶段：高级功能 ✅ **已完成**
- [x] **通用 OCR 工具**：带有多个引擎的高级 OCR（基于 Claude）
- [x] **内容处理**：智能内容编码和转换工具
- [x] **通用表单处理**：动态表单处理能力
- [x] **工具框架**：配置加载器、任务摘要和 MCP 日志工具
- [x] **全面测试**：39 个测试文件，包含集成和 MCP 特定测试

### 第 8 阶段：生产就绪功能 🎯 **当前重点**
- [x] **文档系统**：10 个分类部分的全面文档
- [x] **网站集成**：带有 Material 主题的官方 MkDocs 网站
- [x] **安全框架**：基于权限的访问控制和验证
- [x] **错误恢复**：所有模块的强大异常处理
- [ ] **性能优化**：内存使用和响应时间改进
- [ ] **增强监控**：高级日志记录和指标收集

### 第 9 阶段：企业和生态系统 🚀 **近期** (Q1-Q2 2025)
- [ ] **多提供商 AI 支持**：Anthropic Claude、Azure OpenAI、Google AI 集成
- [ ] **高级工作流功能**：条件分支、并行执行、工作流模板
- [ ] **企业安全**：RBAC、审计跟踪、合规功能
- [ ] **插件生态系统**：第三方插件市场和认证
- [ ] **云集成**：主要云平台的原生支持
- [ ] **团队协作**：共享工作流、团队管理和协作编辑

### 第 10 阶段：高级 AI 编排 🔮 **未来** (H2 2025)
- [ ] **多智能体协调**：带有通信协议的专业化智能体类型
- [ ] **工作流智能**：AI 驱动的工作流优化和建议
- [ ] **企业集成**：与流行企业工具的原生集成
- [ ] **分布式执行**：多节点工作流执行和负载均衡
- [ ] **高级分析**：工作流性能分析和优化洞察
- [ ] **自定义 AI 模型**：支持自定义和微调模型

## 📊 当前状态摘要

**🎉 重大里程碑实现**：思码已远超初始预期，具备全面的 MCP 集成、双模式架构和生产就绪功能。

**📈 项目成熟度**：
- **代码库**：8 个主要模块中的 77 个 Python 文件
- **MCP 集成**：16 个专业化模块，用于完整协议支持
- **API 层**：13 个端点模块，用于全面的 Web 服务
- **测试覆盖**：39 个测试文件确保可靠性
- **文档**：53 个有组织的文档文件

**🚀 生产就绪**：思码现在是一个功能齐全的 AI 编排工作流框架，适合个人开发者和企业部署。

## 🤝 贡献

我们欢迎贡献！请查看我们的[贡献指南](CONTRIBUTING.md)了解详情。

### 开发指南

1. 遵循 PEP 8 风格指南
2. 为所有公共 API 添加类型注释
3. 为新功能编写测试
4. 更新文档
5. 使用约定式提交消息

### 拉取请求流程

1. Fork 仓库
2. 创建功能分支（`git checkout -b feature/amazing-feature`）
3. 进行更改
4. 为更改添加测试
5. 确保所有测试通过（`poetry run pytest`）
6. 提交拉取请求

## 📄 许可证

本项目根据修改版 Apache 2.0 许可证授权，包含以下附加条件：

- **商业使用**：允许商业使用，但多租户服务需要获得授权
- **品牌保护**：不得移除或修改前端界面中的 LOGO 和版权信息
- **贡献条款**：贡献代码可能用于商业目的，包括云服务运营

查看 [LICENSE](LICENSE) 文件了解完整的许可证条款和详细信息。

## 🙏 致谢

- 由现代 Python async/await 模式驱动
- 受现代 AI 助手和开发工具启发
- 感谢 Python 社区提供优秀的工具

## 📞 支持

- **文档**：[simacode.quseit.com](https://simacode.quseit.com/)
- **问题**：[GitHub Issues](https://github.com/QUSEIT/simacode/issues)
- **讨论**：[GitHub Discussions](https://github.com/QUSEIT/simacode/discussions)
- **微信**：`yhc-startup`

## 📱 获得思码更新

<div align="center">
<img src="website/assets/gongzhonghao.jpg" alt="思码公众号二维码" width="200">
<br>
<em>关注公众号获取思码最新动态</em>
</div>