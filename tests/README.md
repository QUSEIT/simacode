# SimaCode Test Suite

This directory contains comprehensive tests for the SimaCode project, covering all phases of development with a focus on AI integration functionality.

## 🏃‍♂️ Quick Start

### Run All Tests
```bash
# From project root (uses config/config.yaml by default)
./tests/run_all_tests.sh

# With specific config file
./tests/run_all_tests.sh -c config/test.yaml
```

### Run Specific Test Categories
```bash
# AI functionality tests
./tests/run_all_tests.sh -t test_ai.py

# Integration tests
./tests/run_all_tests.sh -t test_ai_integration.py

# CLI tests with specific config
./tests/run_all_tests.sh -t test_cli_ai.py -c config/config.yaml

# Error handling tests
./tests/run_all_tests.sh -t test_ai_error_handling.py
```

### Advanced Options
```bash
# Verbose output with HTML coverage report
./tests/run_all_tests.sh -v --html

# Fail fast (stop on first failure)
./tests/run_all_tests.sh -f

# Parallel execution (faster)
./tests/run_all_tests.sh -p

# Quiet mode with custom config
./tests/run_all_tests.sh -q -c config/dev.yaml
```

## 📁 Test Structure

### Core AI Tests
- **`test_ai.py`** - Basic AI functionality (messages, conversations, clients)
- **`test_ai_integration.py`** - End-to-end AI integration workflows
- **`test_ai_factory_extended.py`** - AI client factory and multi-provider support
- **`test_ai_error_handling.py`** - Comprehensive error scenarios and recovery
- **`test_ai_streaming.py`** - Async streaming and real-time responses

### CLI Integration Tests  
- **`test_cli_ai.py`** - CLI commands with AI functionality
- **`test_cli.py`** - Core CLI functionality

### Infrastructure Tests
- **`test_config.py`** - Configuration management
- **`test_logging.py`** - Logging functionality

## 🎯 Test Categories

### Phase 1: Foundation Tests ✅
- [x] Configuration system
- [x] Logging framework  
- [x] CLI structure
- [x] Project setup

### Phase 2: AI Integration Tests ✅
- [x] OpenAI API client
- [x] Conversation management
- [x] Message history
- [x] Streaming responses
- [x] Factory pattern
- [x] Error handling
- [x] CLI integration

### Phase 3: Tool System Tests 🔄
- [ ] File operations
- [ ] Bash execution
- [ ] Permission system
- [ ] Tool registration

## 📊 Coverage Goals

| Module | Target Coverage | Current Status |
|--------|----------------|----------------|
| AI Core | 90%+ | ✅ 91-100% |
| Conversation | 95%+ | ✅ 99% |
| Factory | 95%+ | ✅ 100% |
| CLI Integration | 80%+ | ✅ 78% |
| Overall | 85%+ | ✅ 78% |

## 🧪 Test Types

### Unit Tests
- Individual component functionality
- Isolated behavior verification
- Mock dependencies

### Integration Tests  
- Component interaction
- End-to-end workflows
- Real-world scenarios

### Error Handling Tests
- Network failures
- Invalid configurations
- Resource exhaustion
- Data corruption
- Recovery scenarios

### Performance Tests
- Memory efficiency
- Concurrent operations
- Large data handling
- Streaming performance

## 🛠️ Test Utilities

### Mock Clients
- `MockAIClient` - Configurable AI client for testing
- `AnthropicMockClient` - Anthropic-specific mock
- `LocalMockClient` - Local model mock

### Test Helpers
- Temporary directory management
- Configuration fixtures
- Async test utilities
- Error simulation

## 🚀 Running Tests

### Prerequisites
```bash
# Install dependencies
poetry install --with dev

# Activate environment (optional, script uses Poetry)
poetry shell
```

### Manual Test Execution
```bash
# All tests with coverage
poetry run pytest tests/ --cov=src/simacode --cov-report=html

# Specific test file
poetry run pytest tests/test_ai.py -v

# Specific test function
poetry run pytest tests/test_ai.py::TestMessage::test_message_creation -v

# Run only failed tests
poetry run pytest --lf

# Run tests matching pattern
poetry run pytest -k "test_streaming"
```

### Environment Variables
```bash
# Debug mode
export PYTEST_CURRENT_TEST=1

# Async debugging
export PYTHONASYNCIODEBUG=1

# Coverage configuration
export COVERAGE_CORE=sysmon

# Test configuration file (set by test runner)
export SIMACODE_TEST_CONFIG=config/config.yaml
```

## 📈 Continuous Integration

### GitHub Actions (Recommended)
```yaml
- name: Run tests
  run: ./tests/run_all_tests.sh --no-cov -q -c config/config.yaml
  
- name: Generate coverage
  run: ./tests/run_all_tests.sh --html -c config/ci.yaml
```

### Local Pre-commit
```bash
# Install pre-commit hook
echo "./tests/run_all_tests.sh -f -q" > .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

## 🐛 Debugging Tests

### Failed Test Investigation
```bash
# Run with maximum verbosity
./tests/run_all_tests.sh -v -f

# Debug specific test
poetry run pytest tests/test_ai.py::TestMessage::test_message_creation -v -s --pdb

# Show local variables on failure
poetry run pytest --tb=long --showlocals
```

### Common Issues
1. **Import Errors**: Check PYTHONPATH and package structure
2. **Async Errors**: Verify event loop handling in async tests
3. **Mock Issues**: Ensure proper mock setup and cleanup
4. **Temp File Errors**: Check temp directory cleanup

## 📚 Writing New Tests

### Test Naming Convention
- Test files: `test_<module>.py`
- Test classes: `Test<Component>`
- Test methods: `test_<functionality>`

### Test Structure
```python
class TestComponent:
    """Test <component> functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        pass
    
    def teardown_method(self):
        """Clean up test environment."""
        pass
    
    def test_basic_functionality(self):
        """Test basic component behavior."""
        # Arrange
        # Act  
        # Assert
        pass
    
    @pytest.mark.asyncio
    async def test_async_functionality(self):
        """Test async component behavior."""
        pass
```

### Best Practices
- Use descriptive test names
- Follow AAA pattern (Arrange, Act, Assert)
- Test edge cases and error conditions
- Mock external dependencies
- Clean up resources in teardown
- Use fixtures for common setup
- Add docstrings for complex tests

## 🔧 Test Configuration

### pytest.ini
```ini
[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    --strict-markers
    --disable-warnings
    --asyncio-mode=auto
markers =
    slow: marks tests as slow
    integration: marks tests as integration tests
    unit: marks tests as unit tests
```

### Coverage Configuration
```ini
[tool:coverage:run]
source = src/simacode
omit = 
    */tests/*
    */venv/*
    */virtualenvs/*

[tool:coverage:report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
```

## 📞 Support

For test-related issues:
1. Check this README
2. Review test logs and error messages
3. Run individual tests for debugging
4. Check GitHub Issues for known problems
5. Create new issue with test failure details

---

**Happy Testing! 🧪✨**