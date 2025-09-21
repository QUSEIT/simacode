# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

SimaCode is a modern AI orchestration workflow framework built with Python, featuring intelligent ReAct (Reasoning and Acting) mechanisms and comprehensive workflow orchestration capabilities. It operates in dual modes: as an independent terminal AI Agent application for direct workflow execution, and as a backend API service providing RESTful API and WebSocket services for enterprise workflow integration and automation.

## Architecture

SimaCode follows a clean dual-mode architecture with distinct layers supporting both terminal and API operations:

### Dual-Mode Architecture
- **Terminal Workflow Agent Mode**: CLI interface with Click framework and Rich terminal UI for direct workflow execution
- **Backend Workflow Service Mode**: FastAPI-based RESTful and WebSocket services for enterprise workflow integration
- **Unified Workflow Engine**: Both modes share the same core workflow orchestration logic through `SimaCodeService`

### Core Components
- **Workflow Orchestration Engine** (`src/simacode/react/`): Intelligent workflow planning, execution, and coordination with MCP tool integration
- **MCP Integration** (`src/simacode/mcp/`): Complete Model Context Protocol support with auto-discovery and dynamic updates for workflow tools
- **Tool Ecosystem** (`src/simacode/tools/`): Extensible framework with built-in workflow tools (bash, file operations, data processing)
- **AI Integration** (`src/simacode/ai/`): Multi-provider AI support for intelligent workflow decision-making (OpenAI with planned Anthropic support)
- **Security Framework** (`src/simacode/permissions/`): Comprehensive permission-based access control for workflow execution

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

#### Terminal Workflow Agent Mode
```bash
# Basic workflow execution
simacode chat "Your workflow request here"

# Interactive workflow mode
simacode chat --interactive

# ReAct workflow orchestration
simacode chat --react "Create a complete Python project with tests and documentation"

# Interactive ReAct workflow mode
simacode chat --react --interactive

# Resume a workflow session
simacode chat --react --session-id <session_id>
```

#### Backend Workflow Service Mode
```bash
# Start workflow orchestration server
simacode serve --host 0.0.0.0 --port 8000

# Development mode with auto-reload
simacode serve --dev --reload

# With custom workflow configuration
simacode serve --config workflow_config.yaml --workers 4
```

### MCP Workflow Tool Integration
```bash
# Initialize MCP workflow tools
simacode mcp init

# List all available workflow tools
simacode mcp list

# Search for specific workflow tools
simacode mcp search "file"

# Execute workflow tools directly
simacode mcp run file_tools:read_file --param file_path=/path/to/file.txt

# Interactive workflow parameter input
simacode mcp run web_tools:fetch_url --interactive

# Show workflow system status
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

## API Endpoints (Workflow Service Mode)

Once the workflow orchestration server is running:
- `GET /health`: Health check
- `POST /api/v1/chat/`: Single workflow completion
- `POST /api/v1/chat/stream/`: Streaming workflow execution
- `WS /api/v1/chat/ws/`: WebSocket real-time workflow interaction
- `POST /api/v1/react/execute/`: ReAct workflow orchestration
- `WS /api/v1/react/ws/`: WebSocket ReAct workflow execution
- `GET /api/v1/sessions/`: List workflow sessions
- `GET /api/v1/sessions/{id}`: Workflow session details

## MCP Workflow Integration Notes

SimaCode provides comprehensive MCP (Model Context Protocol) support for workflow orchestration:
- **Two Usage Modes**: AI-assisted workflow orchestration (ReAct mode) and direct workflow tool execution
- **Auto-Discovery**: Automatically discover and register MCP workflow tools
- **Dynamic Updates**: Hot-reload workflow tool changes without restart
- **Namespace Management**: Avoid workflow tool conflicts with namespacing
- **Network Proxy Support**: Handle proxy configurations that may interfere with workflow WebSocket connections

## Workflow Development

1. **Dual-Mode Workflow Development**: Implement workflow features in core service layer first, then expose through both CLI and API interfaces
2. **Workflow Testing**: Use `./tests/run_all_tests.sh` for comprehensive workflow testing with coverage reports
3. **MCP Workflow Tools**: Use `simacode mcp init` to set up workflow tool integration
4. **Workflow Configuration**: Leverage hierarchical config system for different workflow environments
5. **Workflow Sessions**: Both modes support workflow session persistence and management

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