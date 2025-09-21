# SimaCode

[中文版本 / Chinese Version](README_CN.md)

A modern AI orchestration workflow framework built with Python, featuring intelligent ReAct (Reasoning and Acting) mechanisms and comprehensive workflow orchestration capabilities. SimaCode operates in dual modes: as an independent terminal workflow agent for direct workflow execution, and as a backend API service providing RESTful API and WebSocket services for enterprise workflow integration and automation.

## 🚀 Features

### Core Capabilities
- **Intelligent Workflow Orchestration**: Advanced ReAct framework for understanding and executing complex workflow tasks
- **Multi-Agent Workflow System**: Planned specialized agents for different workflow operations (files, code analysis, system commands, data processing)
- **MCP Workflow Integration**: Full support for Model Context Protocol tools with seamless AI-driven and direct command-line workflow access
- **Secure Workflow Execution**: Comprehensive permission system and safety checks for workflow operations
- **Extensible Workflow Architecture**: Tool registry system with plugin support for custom workflow capabilities and MCP tools
- **Multi-Provider AI Support**: Currently supports OpenAI for workflow decision-making, with planned support for Anthropic and other providers

### Dual-Mode Operation
- **Terminal Workflow Agent Mode**: Direct command-line interaction for individual workflow execution and development
- **Backend Workflow Service Mode**: RESTful API and WebSocket endpoints for enterprise workflow integration
- **DevGenius Agent Integration**: Seamless integration with DevGenius Agent framework through standardized workflow APIs

## 📦 Installation

### Prerequisites

- Python 3.10 or higher
- Poetry (for dependency management)

### Install from Source

```bash
# Clone the repository
git clone https://github.com/QUSEIT/simacode.git
cd simacode

# Install dependencies
poetry install

# Install development dependencies (optional)
poetry install --with dev
```

### Quick Start

#### Terminal Workflow Agent Mode
```bash
# Initialize a new workflow project
simacode init

# Start interactive workflow mode
simacode chat --interactive

# Run a single workflow command
simacode chat "Create a complete Python project with tests and documentation"

# Check workflow configuration
simacode config
```

#### Backend Workflow Service Mode
```bash
# Start workflow orchestration server
simacode serve --host 0.0.0.0 --port 8000

# Start with custom workflow configuration
simacode api --config workflow_config.yaml

# Check workflow API status
curl http://localhost:8000/health
```

## 🎯 Usage

### Terminal Workflow Agent Mode

```bash
# Display help
simacode --help

# Show version
simacode --version

# Initialize workflow project
simacode init

# Start workflow execution
simacode chat "Your workflow request here"

# Interactive workflow mode
simacode chat --interactive

# Use ReAct engine for intelligent workflow orchestration
simacode chat --react "Create a complete Python project with tests and documentation"

# Interactive ReAct workflow mode
simacode chat --react --interactive

# Resume a workflow session
simacode chat --react --session-id <session_id>

# Workflow configuration management
simacode config --check
```

### Backend Workflow Service Mode

```bash
# Start workflow orchestration server
simacode serve --host 0.0.0.0 --port 8000

# Start with custom workflow configuration
simacode api --config workflow_config.yaml --workers 4

# Start with specific AI provider for workflows
simacode serve --ai-provider anthropic --model claude-3

# Enable development mode with auto-reload
simacode serve --dev --reload
```

#### Workflow API Endpoints

Once the workflow orchestration server is running, you can access:

```bash
# Health check
GET /health

# Single workflow completion
POST /api/v1/chat/
Content-Type: application/json
{
  "message": "Create a complete Python project with tests and documentation",
  "session_id": "optional-workflow-session-id"
}

# Streaming workflow execution
POST /api/v1/chat/stream/

# ReAct workflow orchestration
POST /api/v1/react/execute/
{
  "task": "Create a comprehensive Python project with CI/CD pipeline",
  "context": {}
}

# WebSocket real-time workflow interaction
WS /api/v1/chat/ws/

# WebSocket ReAct workflow execution
WS /api/v1/react/ws/
```

## 🔧 MCP Workflow Tool Integration

SimaCode provides comprehensive support for Model Context Protocol (MCP) tools, enabling both AI-assisted workflow orchestration and direct command-line access to workflow tools.

### Two Ways to Use MCP Tools

#### 1. AI-Assisted Workflow Usage (ReAct Mode)
Let the AI intelligently orchestrate and use MCP workflow tools based on your natural language workflow requests:

```bash
# Start interactive ReAct workflow mode with MCP tools
simacode chat --react --interactive

# Example workflow conversations:
> Create a data processing workflow that reads config.yaml, processes the data, and generates a report
# AI will automatically orchestrate file tools, data processing tools, and reporting tools

> Build a web scraping workflow that extracts data from multiple URLs and consolidates results
# AI will orchestrate web scraping MCP tools and data consolidation workflows

> Set up a complete project workflow with testing, documentation, and deployment
# AI will orchestrate file management, testing tools, and deployment workflow tools
```

#### 2. Direct Workflow Tool Execution
Execute specific MCP workflow tools directly with precise control:

```bash
# Initialize MCP workflow integration
simacode mcp init

# List all available workflow tools
simacode mcp list

# Search for specific workflow tools
simacode mcp search "file"
simacode mcp search "workflow" --fuzzy

# Get detailed workflow tool information
simacode mcp info file_tools:read_file

# Execute workflow tools with parameters
simacode mcp run file_tools:read_file --param file_path=/path/to/file.txt

# Interactive workflow parameter input
simacode mcp run web_tools:fetch_url --interactive

# Execute with JSON workflow parameters
simacode mcp run data_tools:process_json --params '{"data": {"key": "value"}, "operation": "filter"}'

# Dry run to see what workflow would be executed
simacode mcp run my_workflow_tool --param input=test --dry-run

# Show workflow system status
simacode mcp status
```

### MCP Configuration

Create an MCP configuration file to define your tool servers:

```yaml
# .simacode/mcp.yaml or mcp.yaml
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
  mode: "active"          # auto-discover new tools
  interval: 60            # check every 60 seconds
  auto_register: true     # automatically register new tools

updates:
  enable_hot_updates: true    # hot-reload tool changes
  batch_updates: true         # batch multiple updates
  max_concurrent: 5           # max concurrent updates

namespaces:
  require_namespaces: true       # use namespaces to avoid conflicts
  conflict_resolution: "suffix"  # how to resolve name conflicts
  auto_create_aliases: true      # create short aliases for tools
```

### MCP Troubleshooting

#### Network Proxy Issues

⚠️ **Important Notice**: If you're using a network proxy (HTTP/HTTPS/SOCKS proxy), it may interfere with MCP WebSocket connections and cause initialization failures.

**Common Error Symptoms:**
- `simacode mcp init` fails with WebSocket connection errors
- Error messages like "python-socks is required to use a SOCKS proxy"
- MCP services show as "Disabled" in `simacode mcp status`

**Solutions:**

1. **Temporary Disable Proxy**: If possible, temporarily disable your proxy during MCP initialization:
   ```bash
   # Disable proxy temporarily
   unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
   
   # Initialize MCP
   simacode mcp init
   
   # Re-enable proxy if needed
   export http_proxy=your_proxy_url
   ```

2. **Configure Proxy Bypass**: Add localhost and MCP service ports to your proxy bypass list:
   ```bash
   # For most proxy tools, add these to no_proxy
   export no_proxy="localhost,127.0.0.1,*.local"
   ```

3. **Install Proxy Dependencies**: If you must use a SOCKS proxy, install the required dependency:
   ```bash
   pip install python-socks
   ```

4. **Check MCP Service Status**: After resolving proxy issues, verify MCP is working:
   ```bash
   simacode mcp status
   simacode chat --react "Test MCP functionality"
   ```

**Why This Happens:**
- MCP tools communicate via WebSocket connections to localhost
- Proxies may intercept these local connections
- Some proxy configurations require additional dependencies like `python-socks`
- WebSocket protocols can be sensitive to proxy interference

### MCP Tool Examples

#### File Operations
```bash
# Read a file
simacode mcp run file_tools:read_file --param file_path=config.yaml

# Write to a file
simacode mcp run file_tools:write_file \
  --param file_path=output.txt \
  --param content="Hello, world!" \
  --param append=false
```

#### Web Operations  
```bash
# Fetch URL content
simacode mcp run web_tools:fetch_url --param url=https://api.github.com/users/octocat

# Scrape web page
simacode mcp run web_tools:scrape_page \
  --param url=https://example.com \
  --param selector="h1" \
  --param extract=text
```

#### Data Processing
```bash
# Process JSON data
simacode mcp run data_tools:process_json \
  --params '{"data": [1,2,3,4,5], "operation": "filter", "parameters": {"min": 3}}'
```

#### Interactive Usage
```bash
# Interactive mode guides you through parameter input
simacode mcp run complex_tool --interactive

# Example interactive session:
Tool: complex_tool
Description: A complex tool with multiple parameters

file_path (Path to input file) [required]: /path/to/input.txt
operation (Operation to perform) [optional]: process
options (Additional options as JSON) [optional]: {"verbose": true}
```

### MCP Tool Development

To integrate your own MCP tools:

1. **Develop MCP Server**: Create a server that implements the MCP protocol
2. **Add to Configuration**: Add server configuration to your MCP config file
3. **Auto-Discovery**: Tools will be automatically discovered and registered
4. **AI Integration**: Tools become available to both AI and direct CLI usage

Example minimal MCP server configuration:
```yaml
servers:
  my_custom_tools:
    command: ["python", "-m", "my_mcp_server"]
    args: ["--port", "3000"]
    env:
      DEBUG: "true"
```

### MCP Usage Scenarios

#### When to Use AI-Assisted Mode (ReAct)
✅ **Best for:**
- Exploratory tasks where you're not sure which tools to use
- Complex workflows requiring multiple tools
- Natural language problem description
- Learning what tools are available
- Tasks requiring intelligent planning and decision-making

**Example:**
```bash
simacode chat --react --interactive
> "I need to analyze the JSON data in data.json, extract user information, and save it to a CSV file"
# AI will automatically:
# 1. Use file tool to read data.json
# 2. Use data processing tool to extract user info  
# 3. Use file tool to write CSV output
```

#### When to Use Direct Execution
✅ **Best for:**
- Precise control over tool execution
- Scripting and automation
- Known workflows with specific parameters
- Testing individual tools
- Integration with other command-line tools

**Example:**
```bash
# Precise, scriptable tool execution
simacode mcp run file_tools:read_file --param file_path=data.json | \
simacode mcp run data_tools:extract_users --param format=csv | \
simacode mcp run file_tools:write_file --param file_path=users.csv
```

#### Comparison Table

| Aspect | AI-Assisted (ReAct) | Direct Execution |
|--------|---------------------|------------------|
| **Control** | AI decides tools and parameters | Full user control |
| **Learning Curve** | Natural language, easy to start | Requires tool knowledge |
| **Flexibility** | Adapts to complex scenarios | Precise, predictable |
| **Automation** | Interactive, conversational | Scriptable, pipeline-friendly |
| **Error Handling** | AI can retry and adapt | Manual error handling |
| **Use Case** | Exploration, complex tasks | Automation, precise workflows |

### Configuration

SimaCode uses a hierarchical configuration system:

1. **Runtime configuration** (CLI arguments)
2. **Project configuration** (`.simacode/config.yaml`)
3. **User configuration** (`~/.simacode/config.yaml`)
4. **Default configuration** (built-in)

#### Environment Variables

- `SIMACODE_API_KEY`: Your AI provider API key
- `OPENAI_API_KEY`: Alternative for OpenAI

#### Example Configuration

```yaml
# .simacode/config.yaml
project_name: "My Awesome Project"

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

## 🏗️ Architecture

SimaCode follows a clean dual-mode architecture with distinct layers supporting both terminal and API operations:

### Dual-Mode Architecture

#### **Core Service Layer**
- **Unified Business Logic**: Shared ReAct engine, tool system, and AI integration
- **Configuration Management**: YAML-based configuration with Pydantic validation
- **Session Management**: Multi-user session handling and persistence
- **Security Framework**: Comprehensive permission-based access control

#### **Interface Layers**
- **CLI Layer**: Command-line interface with Click for terminal AI Agent mode
- **API Layer**: FastAPI-based RESTful and WebSocket services for backend integration
- **Both Modes Share**: Same core capabilities, ensuring functional consistency

### Core Components

#### ✅ **Implemented Components**
- **CLI Layer**: Command-line interface with Click and MCP tool commands
- **Configuration**: YAML-based configuration with Pydantic validation
- **Logging**: Structured logging with Rich formatting
- **ReAct Engine**: Intelligent task planning and execution with MCP tool integration
- **Tool System**: Extensible framework with built-in tools (bash, file_read, file_write)
- **MCP Integration**: Complete Model Context Protocol support with:
  - **Tool Wrapper**: Seamless integration of MCP tools with SimaCode
  - **Tool Registry**: Centralized management and namespace handling
  - **Auto-Discovery**: Intelligent tool discovery and registration
  - **Dynamic Updates**: Hot-reload and real-time tool updates
  - **Unified Interface**: Both AI-assisted and direct CLI access
- **AI Integration**: OpenAI client with conversation management
- **Security**: Comprehensive permission-based access control
- **Session Management**: Session handling and persistence

#### 🚧 **Planned Components**
- **API Layer**: FastAPI-based RESTful and WebSocket services
- **Multi-User Support**: Concurrent session handling for API mode
- **Async Task Processing**: Background task execution for long-running operations
- **Multi-Agent System**: Specialized agents for different operations
- **Multi-Provider AI**: Support for Anthropic, Azure, Google AI providers
- **Advanced Security**: Enhanced sandboxed execution and resource limits

### Technology Stack

#### **Core Technologies**
- **Runtime**: Python 3.10+
- **Package Management**: Poetry
- **Configuration**: Pydantic + YAML
- **Logging**: Rich + Python logging
- **Testing**: pytest + pytest-asyncio
- **Code Quality**: Black, isort, flake8, mypy

#### **Terminal AI Agent Mode**
- **CLI Framework**: Click
- **Interactive UI**: Rich for enhanced terminal display

#### **Backend API Service Mode**
- **Web Framework**: FastAPI (planned)
- **WebSocket**: Native FastAPI WebSocket support
- **Async Processing**: asyncio + async queues
- **API Documentation**: OpenAPI/Swagger auto-generation

## 🧪 Development

### Setup Development Environment

```bash
# Install development dependencies
poetry install --with dev

# Setup pre-commit hooks
poetry run pre-commit install

# Run tests
poetry run pytest

# Run tests with coverage
poetry run pytest --cov=simacode

# Format code
poetry run black .
poetry run isort .

# Type checking
poetry run mypy src/simacode

# Linting
poetry run flake8 src/simacode
```

### Project Structure

```
simacode/
├── src/simacode/           # Main package
│   ├── __init__.py        # Package initialization
│   ├── __main__.py        # CLI entry point
│   ├── cli.py             # Command-line interface
│   ├── cli_mcp.py         # MCP command-line interface
│   ├── config.py          # Configuration management
│   ├── logging_config.py  # Logging setup
│   ├── core/              # Core service layer
│   │   ├── __init__.py    # Core module initialization
│   │   └── service.py     # Unified SimaCodeService
│   ├── ai/                # AI client implementations
│   │   ├── __init__.py    # AI module initialization
│   │   ├── base.py        # AI client abstractions
│   │   ├── factory.py     # AI client factory
│   │   ├── openai_client.py # OpenAI integration
│   │   └── conversation.py  # Conversation management
│   ├── api/               # FastAPI web service
│   │   ├── __init__.py    # API module initialization
│   │   ├── app.py         # FastAPI application
│   │   ├── models.py      # API data models
│   │   ├── dependencies.py # Dependency injection
│   │   ├── chat_confirmation.py # Chat confirmation handling
│   │   └── routes/        # API route handlers
│   │       ├── __init__.py # Routes initialization
│   │       ├── chat.py    # Chat endpoints
│   │       ├── chat_safe.py # Safe chat endpoints
│   │       ├── config.py  # Configuration endpoints
│   │       ├── health.py  # Health check endpoints
│   │       ├── react.py   # ReAct endpoints
│   │       ├── sessions.py # Session endpoints
│   │       └── tasks.py   # Task endpoints
│   ├── react/             # ReAct workflow engine
│   │   ├── __init__.py    # ReAct module initialization
│   │   ├── engine.py      # Main ReAct workflow engine
│   │   ├── planner.py     # Task planning
│   │   ├── evaluator.py   # Result evaluation
│   │   ├── confirmation_manager.py # User confirmation handling
│   │   ├── exceptions.py  # ReAct exceptions
│   │   └── mcp_integration.py # MCP integration
│   ├── mcp/               # MCP (Model Context Protocol) integration
│   │   ├── __init__.py    # MCP module initialization
│   │   ├── client.py      # MCP client implementation
│   │   ├── config.py      # MCP configuration
│   │   ├── connection.py  # Connection management
│   │   ├── discovery.py   # Tool discovery
│   │   ├── auto_discovery.py # Automatic tool discovery
│   │   ├── dynamic_updates.py # Dynamic tool updates
│   │   ├── exceptions.py  # MCP exceptions
│   │   ├── health.py      # Health monitoring
│   │   ├── integration.py # Integration utilities
│   │   ├── namespace_manager.py # Namespace management
│   │   ├── protocol.py    # Protocol implementation
│   │   ├── server_manager.py # Server management
│   │   ├── tool_registry.py # Tool registry
│   │   ├── tool_wrapper.py # Tool wrapper
│   │   └── async_integration.py # Async integration
│   ├── tools/             # Built-in tool system
│   │   ├── __init__.py    # Tools module initialization
│   │   ├── base.py        # Tool abstractions
│   │   ├── bash.py        # Bash execution tool
│   │   ├── file_read.py   # File reading tool
│   │   ├── file_write.py  # File writing tool
│   │   ├── smc_content_coder.py # Content coding tool
│   │   └── universal_ocr/ # Universal OCR tool
│   │       ├── __init__.py # OCR module initialization
│   │       ├── config.py  # OCR configuration
│   │       ├── core.py    # OCR core functionality
│   │       ├── file_processor.py # File processing
│   │       ├── input_models.py # Input data models
│   │       ├── test_basic.py # Basic tests
│   │       └── engines/   # OCR engines
│   │           ├── __init__.py # Engines initialization
│   │           ├── base.py # Base engine
│   │           └── claude_engine.py # Claude OCR engine
│   ├── permissions/       # Security and permissions
│   │   ├── __init__.py    # Permissions module initialization
│   │   ├── manager.py     # Permission management
│   │   └── validators.py  # Security validators
│   ├── session/           # Session management
│   │   ├── __init__.py    # Session module initialization
│   │   └── manager.py     # Session handling
│   ├── services/          # Application services
│   │   ├── __init__.py    # Services module initialization
│   │   └── react_service.py # ReAct service layer
│   ├── utils/             # Utility modules
│   │   ├── __init__.py    # Utils module initialization
│   │   ├── config_loader.py # Configuration loader
│   │   ├── mcp_logger.py  # MCP logging utilities
│   │   └── task_summary.py # Task summary utilities
│   └── universalform/     # Universal form handling
│       ├── __init__.py    # Universal form initialization
│       └── app.py         # Form application
├── tests/                 # Test suite
│   ├── integration/       # Integration tests
│   └── mcp/               # MCP-specific tests
├── tools/                 # External MCP tools
├── docs/                  # Documentation (organized structure)
│   ├── README.md          # Documentation navigation
│   ├── 01-core/           # Core project documentation
│   ├── 02-architecture/   # Architecture design documents
│   ├── 03-features/       # Feature specifications
│   ├── 04-development/    # Development guides
│   ├── 05-tools/          # Tool integration guides
│   ├── 06-api/            # API documentation
│   ├── 07-testing/        # Test documentation
│   ├── 08-deployment/     # Deployment documentation
│   ├── 09-troubleshooting/ # Problem resolution guides
│   └── 10-references/     # Reference materials
├── website/               # Official website (MkDocs)
│   ├── mkdocs.yml         # Website configuration
│   └── docs/              # Website content
│       ├── index.md       # Homepage
│       ├── assets/        # Website assets
│       └── styles/        # Custom styles
├── demo/                  # Demo scripts and examples
├── scripts/               # Build and utility scripts
├── .simacode/             # Local configuration
│   ├── logs/              # Application logs
│   ├── mcp/               # MCP data
│   └── sessions/          # Session data
└── pyproject.toml         # Project configuration
```

## 🧪 Testing

Run the test suite:

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=simacode --cov-report=html

# Run specific test file
poetry run pytest tests/test_cli.py

# Run with verbose output
poetry run pytest -v
```

## 📋 Development Roadmap

### Phase 1: Foundation ✅ **COMPLETED**
- [x] Basic CLI structure with Click framework
- [x] Hierarchical configuration system (YAML + env vars)
- [x] Rich logging framework with structured output
- [x] Poetry-based project setup and dependency management

### Phase 2: AI Integration ✅ **COMPLETED**
- [x] OpenAI API client with async support
- [x] Conversation management with context handling
- [x] Message history and session persistence
- [x] Streaming responses for real-time interaction

### Phase 3: Tool System ✅ **COMPLETED**
- [x] File operations (read/write with permissions)
- [x] Bash execution with security controls
- [x] Comprehensive permission system
- [x] Extensible tool registration framework

### Phase 4: ReAct Workflow Engine ✅ **COMPLETED**
- [x] Intelligent task planning and decomposition
- [x] Tool orchestration and execution coordination
- [x] Robust error handling and recovery
- [x] Session management with state persistence
- [x] User confirmation mechanisms for safety

### Phase 5: MCP Integration ✅ **COMPLETED**
- [x] **Complete MCP Protocol Support**: Full Model Context Protocol implementation
- [x] **Tool Discovery & Registration**: Auto-discovery and namespace management
- [x] **Dynamic Updates**: Hot-reload capabilities for tools
- [x] **Dual Access Modes**: AI-assisted and direct CLI tool execution
- [x] **Health Monitoring**: Connection status and tool availability tracking
- [x] **Async Integration**: Background task processing and concurrent execution

### Phase 6: Dual-Mode Architecture ✅ **COMPLETED**
- [x] **Core Service Layer**: Unified SimaCodeService abstraction
- [x] **FastAPI Integration**: Complete RESTful API with 13 endpoint modules
- [x] **WebSocket Support**: Real-time communication for both chat and ReAct
- [x] **Multi-User Session Management**: Concurrent session handling
- [x] **OpenAPI Documentation**: Auto-generated Swagger documentation
- [x] **Optional Dependencies**: Graceful degradation when API dependencies unavailable

### Phase 7: Advanced Features ✅ **COMPLETED**
- [x] **Universal OCR Tool**: Advanced OCR with multiple engines (Claude-based)
- [x] **Content Processing**: Smart content coding and transformation tools
- [x] **Universal Form Handling**: Dynamic form processing capabilities
- [x] **Utility Framework**: Config loader, task summary, and MCP logging utilities
- [x] **Comprehensive Testing**: 39 test files with integration and MCP-specific tests

### Phase 8: Production Ready Features 🎯 **CURRENT FOCUS**
- [x] **Documentation System**: Comprehensive docs with 10 categorized sections
- [x] **Website Integration**: Official MkDocs website with Material theme
- [x] **Security Framework**: Permission-based access control and validation
- [x] **Error Recovery**: Robust exception handling across all modules
- [ ] **Performance Optimization**: Memory usage and response time improvements
- [ ] **Enhanced Monitoring**: Advanced logging and metrics collection

### Phase 9: Enterprise & Ecosystem 🚀 **NEAR TERM** (Q1-Q2 2025)
- [ ] **Multi-Provider AI Support**: Anthropic Claude, Azure OpenAI, Google AI integration
- [ ] **Advanced Workflow Features**: Conditional branching, parallel execution, workflow templates
- [ ] **Enterprise Security**: RBAC, audit trails, compliance features
- [ ] **Plugin Ecosystem**: Third-party plugin marketplace and certification
- [ ] **Cloud Integration**: Native support for major cloud platforms
- [ ] **Team Collaboration**: Shared workflows, team management, and collaborative editing

### Phase 10: Advanced AI Orchestration 🔮 **FUTURE** (H2 2025)
- [ ] **Multi-Agent Coordination**: Specialized agent types with communication protocols
- [ ] **Workflow Intelligence**: AI-powered workflow optimization and recommendations
- [ ] **Enterprise Integration**: Native integrations with popular enterprise tools
- [ ] **Distributed Execution**: Multi-node workflow execution and load balancing
- [ ] **Advanced Analytics**: Workflow performance analysis and optimization insights
- [ ] **Custom AI Models**: Support for custom and fine-tuned models

## 📊 Current Status Summary

**🎉 Major Milestone Achieved**: SimaCode has evolved far beyond initial expectations, with comprehensive MCP integration, dual-mode architecture, and production-ready features already implemented.

**📈 Project Maturity**:
- **Code Base**: 77 Python files across 8 major modules
- **MCP Integration**: 16 specialized modules for complete protocol support
- **API Layer**: 13 endpoint modules for comprehensive web service
- **Testing Coverage**: 39 test files ensuring reliability
- **Documentation**: 53 organized documentation files

**🚀 Ready for Production**: SimaCode is now a fully-featured AI orchestration workflow framework suitable for both individual developers and enterprise deployment.

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Guidelines

1. Follow PEP 8 style guidelines
2. Add type annotations to all public APIs
3. Write tests for new features
4. Update documentation
5. Use conventional commit messages

### Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for your changes
5. Ensure all tests pass (`poetry run pytest`)
6. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Powered by modern Python async/await patterns
- Inspired by modern AI assistants and development tools
- Thanks to the Python community for excellent tooling

## 📞 Support

- **Documentation**: [simacode.quseit.com](https://simacode.quseit.com/)
- **Issues**: [GitHub Issues](https://github.com/QUSEIT/simacode/issues)
- **Discussions**: [GitHub Discussions](https://github.com/QUSEIT/simacode/discussions)
