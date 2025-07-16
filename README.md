# SimaCode

A modern AI programming assistant built with Python, featuring intelligent ReAct (Reasoning and Acting) mechanisms and a sophisticated multi-agent system.

## 🚀 Features

- **Intelligent Task Planning**: Advanced ReAct framework for understanding and executing complex programming tasks
- **Multi-Agent System**: Specialized agents for different operations (files, code analysis, system commands)
- **Secure by Design**: Comprehensive permission system and safety checks
- **Modern Terminal UI**: Rich, responsive interface built with Textual
- **Extensible Architecture**: Plugin system for custom tools and capabilities
- **Multi-Provider AI Support**: Integrates with OpenAI, Anthropic, and other AI providers

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

- **CLI Layer**: Command-line interface with Click
- **Configuration**: YAML-based configuration with Pydantic validation
- **Logging**: Structured logging with Rich formatting
- **ReAct Engine**: Intelligent task planning and execution
- **Tool System**: Extensible framework for operations
- **Agent System**: Multi-agent coordination
- **Security**: Permission-based access control

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
│   └── ...
├── config/                # Configuration files
│   └── default.yaml       # Default configuration
├── tests/                 # Test suite
│   ├── test_cli.py       # CLI tests
│   ├── test_config.py    # Config tests
│   └── test_logging.py   # Logging tests
├── docs/                  # Documentation
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

### Phase 2: AI Integration (Next)
- [ ] OpenAI API client
- [ ] Basic conversation management
- [ ] Message history
- [ ] Streaming responses

### Phase 3: Tool System
- [ ] File operations
- [ ] Bash execution
- [ ] Permission system
- [ ] Tool registration

### Phase 4: ReAct Engine
- [ ] Task planning
- [ ] Tool orchestration
- [ ] Error handling
- [ ] Session management

### Phase 5: Terminal UI
- [ ] Textual interface
- [ ] Interactive chat
- [ ] Progress indicators
- [ ] Theme support

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

- Built with [Textual](https://github.com/Textualize/textual) for the terminal UI
- Inspired by modern AI assistants and development tools
- Thanks to the Python community for excellent tooling

## 📞 Support

- **Documentation**: [simacode.readthedocs.io](https://simacode.readthedocs.io)
- **Issues**: [GitHub Issues](https://github.com/simacode/simacode/issues)
- **Discussions**: [GitHub Discussions](https://github.com/simacode/simacode/discussions)