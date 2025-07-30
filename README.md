# SimaCode

A modern AI programming assistant built with Python, featuring intelligent ReAct (Reasoning and Acting) mechanisms and a sophisticated multi-agent system. SimaCode operates in dual modes: as an independent terminal AI Agent application for direct use, and as a backend API service providing RESTful API and WebSocket services for integration with frameworks like DevGenius Agent.

## 🚀 Features

### Core Capabilities
- **Intelligent Task Planning**: Advanced ReAct framework for understanding and executing complex programming tasks
- **Multi-Agent System**: Planned specialized agents for different operations (files, code analysis, system commands)
- **MCP Integration**: Full support for Model Context Protocol tools with seamless AI and direct command-line access
- **Secure by Design**: Comprehensive permission system and safety checks
- **Extensible Architecture**: Tool registry system with plugin support for custom capabilities and MCP tools
- **Multi-Provider AI Support**: Currently supports OpenAI, with planned support for Anthropic and other providers

### Dual-Mode Operation
- **Terminal AI Agent Mode**: Direct command-line interaction for individual developers
- **Backend API Service Mode**: RESTful API and WebSocket endpoints for enterprise integration
- **DevGenius Agent Integration**: Seamless integration with DevGenius Agent framework through standardized APIs

## 📦 Installation

### Prerequisites

- Python 3.10 or higher
- Poetry (for dependency management)

### Install from Source

```bash
# Clone the repository
git clone https://github.com/simacode/simacode.git
cd simacode

# Install dependencies
poetry install

# Install development dependencies (optional)
poetry install --with dev
```

### Quick Start

#### Terminal AI Agent Mode
```bash
# Initialize a new project
simacode init

# Start interactive mode
simacode chat --interactive

# Run a single command
simacode chat "Create a Python function to calculate fibonacci numbers"

# Check configuration
simacode config
```

#### Backend API Service Mode
```bash
# Start API server
simacode serve --host 0.0.0.0 --port 8000

# Start with custom configuration
simacode api --config api_config.yaml

# Check API status
curl http://localhost:8000/health
```

## 🎯 Usage

### Terminal AI Agent Mode

```bash
# Display help
simacode --help

# Show version
simacode --version

# Initialize project
simacode init

# Start chat
simacode chat "Your message here"

# Interactive chat mode
simacode chat --interactive

# Use ReAct engine for intelligent task planning
simacode chat --react "Create a Python function to calculate fibonacci numbers"

# Interactive ReAct mode
simacode chat --react --interactive

# Resume a session
simacode chat --react --session-id <session_id>

# Configuration management
simacode config --check
```

### Backend API Service Mode

```bash
# Start API server
simacode serve --host 0.0.0.0 --port 8000

# Start with custom configuration
simacode api --config api_config.yaml --workers 4

# Start with specific AI provider
simacode serve --ai-provider anthropic --model claude-3

# Enable development mode with auto-reload
simacode serve --dev --reload
```

#### API Endpoints

Once the API server is running, you can access:

```bash
# Health check
GET /health

# Single chat completion
POST /api/v1/chat/
Content-Type: application/json
{
  "message": "Create a Python function to calculate fibonacci numbers",
  "session_id": "optional-session-id"
}

# Streaming chat
POST /api/v1/chat/stream/

# ReAct task execution
POST /api/v1/react/execute/
{
  "task": "Create a Python project with tests",
  "context": {}
}

# WebSocket real-time chat
WS /api/v1/chat/ws/

# WebSocket ReAct execution
WS /api/v1/react/ws/
```

## 🔧 MCP Tool Integration

SimaCode provides comprehensive support for Model Context Protocol (MCP) tools, enabling both AI-assisted and direct command-line access to external tools.

### Two Ways to Use MCP Tools

#### 1. AI-Assisted Usage (ReAct Mode)
Let the AI intelligently choose and use MCP tools based on your natural language requests:

```bash
# Start interactive ReAct mode with MCP tools
simacode chat --react --interactive

# Example conversation:
> Please read the contents of my config.yaml file
# AI will automatically discover and use the appropriate MCP file tool

> Help me scrape the title from https://example.com
# AI will use web scraping MCP tools if available

> Process this JSON data and extract the user information
# AI will use data processing MCP tools
```

#### 2. Direct Tool Execution
Execute specific MCP tools directly with precise control:

```bash
# Initialize MCP integration
simacode mcp init

# List all available tools
simacode mcp list

# Search for specific tools
simacode mcp search "file"
simacode mcp search "web" --fuzzy

# Get detailed tool information
simacode mcp info file_tools:read_file

# Execute tools with parameters
simacode mcp run file_tools:read_file --param file_path=/path/to/file.txt

# Interactive parameter input
simacode mcp run web_tools:fetch_url --interactive

# Execute with JSON parameters
simacode mcp run data_tools:process_json --params '{"data": {"key": "value"}, "operation": "filter"}'

# Dry run to see what would be executed
simacode mcp run my_tool --param input=test --dry-run

# Show system status
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
│   ├── cli.py             # Command-line interface
│   ├── config.py          # Configuration management
│   ├── logging_config.py  # Logging setup
│   ├── ai/                # AI client implementations
│   │   ├── base.py        # AI client abstractions
│   │   ├── factory.py     # AI client factory
│   │   ├── openai_client.py # OpenAI integration
│   │   └── conversation.py  # Conversation management
│   ├── react/             # ReAct engine implementation
│   │   ├── engine.py      # Main ReAct engine
│   │   ├── planner.py     # Task planning
│   │   └── evaluator.py   # Result evaluation
│   ├── tools/             # Tool system
│   │   ├── base.py        # Tool abstractions
│   │   ├── bash.py        # Bash execution tool
│   │   ├── file_read.py   # File reading tool
│   │   └── file_write.py  # File writing tool
│   ├── permissions/       # Security and permissions
│   │   ├── manager.py     # Permission management
│   │   └── validators.py  # Security validators
│   ├── session/           # Session management
│   │   └── manager.py     # Session handling
│   └── services/          # Application services
│       └── react_service.py # ReAct service layer
├── config/                # Configuration files
│   └── default.yaml       # Default configuration
├── tests/                 # Test suite
├── docs/                  # Documentation
│   └── plans/             # Development plans
└── pyproject.toml        # Project configuration
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

### Phase 1: Foundation ✅
- [x] Basic CLI structure
- [x] Configuration system
- [x] Logging framework
- [x] Project setup

### Phase 2: AI Integration ✅
- [x] OpenAI API client
- [x] Basic conversation management
- [x] Message history
- [x] Streaming responses

### Phase 3: Tool System ✅
- [x] File operations
- [x] Bash execution
- [x] Permission system
- [x] Tool registration

### Phase 4: ReAct Engine ✅
- [x] Task planning
- [x] Tool orchestration
- [x] Error handling
- [x] Session management

### Phase 5: Dual-Mode Architecture 🚧 **High Priority**
- [ ] **Core Service Layer Abstraction**: Extract unified business logic
- [ ] **FastAPI Integration**: RESTful API endpoints
- [ ] **WebSocket Support**: Real-time communication
- [ ] **Multi-User Session Management**: Concurrent session handling
- [ ] **Async Task Processing**: Background task execution
- [ ] **API Documentation**: OpenAPI/Swagger integration

### Phase 6: Enhanced Tool System 🚧
- [ ] Code analysis tools (AST parsing, syntax checking)
- [ ] Git integration tools (commit, branch, merge)
- [ ] Project management tools (dependency management)
- [ ] Testing tools (unit test, integration test)
- [ ] Build system integration
- [ ] Documentation generation tools

### Phase 7: Plugin System 🚧
- [ ] Dynamic plugin loading mechanism
- [ ] Plugin configuration management
- [ ] Plugin dependency resolution
- [ ] Plugin lifecycle management
- [ ] Third-party plugin registry
- [ ] MCP (Model Context Protocol) integration

### Phase 8: Multi-Provider AI Support 🚧
- [ ] Anthropic Claude client integration
- [ ] Azure OpenAI client
- [ ] Google Vertex AI client
- [ ] Unified AI client interface
- [ ] Provider-specific configuration
- [ ] Fallback and load balancing

### Phase 9: Multi-Agent System 🚧
- [ ] Agent abstraction framework
- [ ] Specialized agents (FileAgent, CodeAgent, SystemAgent)
- [ ] Inter-agent communication protocol
- [ ] Task allocation and load balancing
- [ ] Agent coordination strategies
- [ ] Distributed execution support

### Phase 10: Production & Security
- [ ] Sandboxed execution environment
- [ ] Resource limits (CPU, memory, network)
- [ ] Audit logging and monitoring
- [ ] Threat detection and prevention
- [ ] Enhanced session persistence
- [ ] Performance optimization

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

- **Documentation**: [simacode.readthedocs.io](https://simacode.readthedocs.io)
- **Issues**: [GitHub Issues](https://github.com/simacode/simacode/issues)
- **Discussions**: [GitHub Discussions](https://github.com/simacode/simacode/discussions)