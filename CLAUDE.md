# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SimaCode is a modern AI programming assistant built with Python featuring intelligent ReAct (Reasoning and Acting) mechanisms and a sophisticated multi-agent system. It operates in dual modes: as an independent terminal AI Agent application for direct use, and as a backend API service providing RESTful API and WebSocket services for integration with frameworks like DevGenius Agent.

## Architecture

SimaCode follows a clean dual-mode architecture with distinct layers supporting both terminal and API operations:

### Dual-Mode Architecture
- **Terminal AI Agent Mode**: CLI interface with Click framework and Rich terminal UI
- **Backend API Service Mode**: FastAPI-based RESTful and WebSocket services for enterprise integration
- **Unified Core Service**: Both modes share the same core business logic through `SimaCodeService`

### Core Components
- **ReAct Engine** (`src/simacode/react/`): Intelligent task planning and execution with MCP tool integration
- **MCP Integration** (`src/simacode/mcp/`): Complete Model Context Protocol support with auto-discovery and dynamic updates
- **Tool System** (`src/simacode/tools/`): Extensible framework with built-in tools (bash, file operations)
- **AI Integration** (`src/simacode/ai/`): Multi-provider AI support (OpenAI with planned Anthropic support)
- **Security Framework** (`src/simacode/permissions/`): Comprehensive permission-based access control

## Development Commands

### Environment Setup
```bash
# Install dependencies
poetry install

# Install with API support (optional)
poetry install --extras api

# Install development dependencies
poetry install --with dev

# Setup pre-commit hooks
poetry run pre-commit install
```

### Running SimaCode

#### Terminal AI Agent Mode
```bash
# Basic chat
simacode chat "Your message here"

# Interactive chat mode
simacode chat --interactive

# ReAct task execution
simacode chat --react "Create a Python function to calculate fibonacci numbers"

# Interactive ReAct mode
simacode chat --react --interactive

# Resume a session
simacode chat --react --session-id <session_id>
```

#### Backend API Service Mode
```bash
# Start API server
simacode serve --host 0.0.0.0 --port 8000

# Development mode with auto-reload
simacode serve --dev --reload

# With custom configuration
simacode serve --config api_config.yaml --workers 4
```

### MCP Tool Integration
```bash
# Initialize MCP integration
simacode mcp init

# List all available tools
simacode mcp list

# Search for specific tools
simacode mcp search "file"

# Execute tools directly
simacode mcp run file_tools:read_file --param file_path=/path/to/file.txt

# Interactive parameter input
simacode mcp run web_tools:fetch_url --interactive

# Show system status
simacode mcp status
```

### Testing
```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=simacode --cov-report=html

# Run specific test file
poetry run pytest tests/test_cli.py

# Use comprehensive test runner
./tests/run_all_tests.sh

# Run with options
./tests/run_all_tests.sh -v --html
./tests/run_all_tests.sh -t test_ai.py
```

### Code Quality
```bash
# Format code
poetry run black .
poetry run isort .

# Type checking
poetry run mypy src/simacode

# Linting
poetry run flake8 src/simacode
```

## Configuration

SimaCode uses a hierarchical configuration system with YAML files and environment variables:

1. **Runtime configuration** (CLI arguments)
2. **Project configuration** (`.simacode/config.yaml`)
3. **User configuration** (`~/.simacode/config.yaml`) 
4. **Default configuration** (`config/default.yaml`)

### Key Configuration Files
- `config/default.yaml`: Default application settings
- `config/mcp_servers.yaml`: MCP server configurations
- `.simacode/config.yaml`: Project-specific settings

### Environment Variables
- `SIMACODE_API_KEY` or `OPENAI_API_KEY`: AI provider API key
- `SIMACODE_TEST_CONFIG`: Config file for testing

## Key Directories

### Source Code (`src/simacode/`)
- `cli.py`: Command-line interface entry point
- `core/service.py`: Unified service layer for dual-mode architecture
- `react/`: ReAct engine implementation (planning, execution, evaluation)
- `mcp/`: Model Context Protocol integration
- `tools/`: Built-in tool implementations
- `ai/`: AI client implementations and conversation management
- `api/`: FastAPI-based API service (routes, models, dependencies)
- `services/`: Application services layer
- `permissions/`: Security and permission management
- `session/`: Session handling and persistence

### Configuration (`config/`)
- Contains default YAML configuration files
- MCP server definitions
- Security and AI provider settings

### Documentation (`docs/`)
- Architecture documentation
- Development plans and progress reports
- API usage examples and feature documentation

### Tests (`tests/`)
- Comprehensive test suite with integration and unit tests
- `run_all_tests.sh`: Comprehensive test runner with options
- MCP integration tests
- AI functionality tests

## API Endpoints (Service Mode)

Once the API server is running:
- `GET /health`: Health check
- `POST /api/v1/chat/`: Single chat completion  
- `POST /api/v1/chat/stream/`: Streaming chat
- `WS /api/v1/chat/ws/`: WebSocket real-time chat
- `POST /api/v1/react/execute/`: ReAct task execution
- `WS /api/v1/react/ws/`: WebSocket ReAct execution
- `GET /api/v1/sessions/`: List sessions
- `GET /api/v1/sessions/{id}`: Session details

## MCP Integration Notes

SimaCode provides comprehensive MCP (Model Context Protocol) support:
- **Two Usage Modes**: AI-assisted (ReAct mode) and direct tool execution
- **Auto-Discovery**: Automatically discover and register MCP tools
- **Dynamic Updates**: Hot-reload tool changes without restart
- **Namespace Management**: Avoid tool conflicts with namespacing
- **Network Proxy Support**: Handle proxy configurations that may interfere with WebSocket connections

## Development Workflow

1. **Dual-Mode Development**: Implement features in core service layer first, then expose through both CLI and API interfaces
2. **Testing**: Use `./tests/run_all_tests.sh` for comprehensive testing with coverage reports
3. **MCP Tools**: Use `simacode mcp init` to set up tool integration
4. **Configuration**: Leverage hierarchical config system for different environments
5. **Sessions**: Both modes support session persistence and management

## Technology Stack

- **Runtime**: Python 3.10+
- **Package Management**: Poetry
- **CLI Framework**: Click
- **API Framework**: FastAPI (optional dependency)
- **Configuration**: Pydantic + YAML
- **Testing**: pytest + pytest-asyncio
- **Code Quality**: Black, isort, flake8, mypy

## Troubleshooting

### MCP Connection Issues
If MCP tools fail to initialize due to proxy issues:
```bash
# Temporarily disable proxy
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
simacode mcp init

# Or add localhost to proxy bypass
export no_proxy="localhost,127.0.0.1,*.local"
```

### Common Commands
```bash
# Check configuration
simacode config --check

# View MCP status
simacode mcp status

# Health check API
curl http://localhost:8000/health

# Check Poetry environment
poetry env info
```