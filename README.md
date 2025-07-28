# SimaCode

A modern AI programming assistant built with Python, featuring intelligent ReAct (Reasoning and Acting) mechanisms and a sophisticated multi-agent system.

## 🚀 Features

- **Intelligent Task Planning**: Advanced ReAct framework for understanding and executing complex programming tasks
- **Multi-Agent System**: Planned specialized agents for different operations (files, code analysis, system commands)
- **Secure by Design**: Comprehensive permission system and safety checks
- **Extensible Architecture**: Tool registry system with planned plugin support for custom capabilities
- **Multi-Provider AI Support**: Currently supports OpenAI, with planned support for Anthropic and other providers

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

## 🎯 Usage

### Basic Commands

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

SimaCode follows a clean architecture with distinct layers:

### Core Components

#### ✅ **Implemented Components**
- **CLI Layer**: Command-line interface with Click
- **Configuration**: YAML-based configuration with Pydantic validation
- **Logging**: Structured logging with Rich formatting
- **ReAct Engine**: Intelligent task planning and execution
- **Tool System**: Extensible framework for operations (bash, file_read, file_write)
- **AI Integration**: OpenAI client with conversation management
- **Security**: Basic permission-based access control
- **Session Management**: Basic session handling and persistence

#### 🚧 **Planned Components**
- **Multi-Agent System**: Specialized agents for different operations
- **Plugin System**: Dynamic plugin loading and management
- **Multi-Provider AI**: Support for Anthropic, Azure, Google AI providers
- **Advanced Security**: Sandboxed execution and resource limits

### Technology Stack

- **Runtime**: Python 3.10+
- **Package Management**: Poetry
- **CLI Framework**: Click
- **Configuration**: Pydantic + YAML
- **Logging**: Rich + Python logging
- **Testing**: pytest + pytest-asyncio
- **Code Quality**: Black, isort, flake8, mypy

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

### Phase 5: Multi-Provider AI Support 🚧
- [ ] Anthropic Claude client integration
- [ ] Azure OpenAI client
- [ ] Google Vertex AI client
- [ ] Unified AI client interface
- [ ] Provider-specific configuration
- [ ] Fallback and load balancing

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

### Phase 8: Multi-Agent System 🚧
- [ ] Agent abstraction framework
- [ ] Specialized agents (FileAgent, CodeAgent, SystemAgent)
- [ ] Inter-agent communication protocol
- [ ] Task allocation and load balancing
- [ ] Agent coordination strategies
- [ ] Distributed execution support

### Phase 9: Advanced Security & Production
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