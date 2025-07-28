"""
Pytest configuration and fixtures for SimaCode tests.

This file provides shared fixtures and configuration for all tests,
including configuration file handling and common test utilities.
"""

import os
import tempfile
from pathlib import Path
from typing import Dict, Any

import pytest
import yaml

from simacode.config import Config


@pytest.fixture(scope="session")
def test_config_file():
    """Get the test configuration file path from environment or use default."""
    config_file = os.environ.get('SIMACODE_TEST_CONFIG', 'config/config.yaml')
    config_path = Path(config_file)
    
    if not config_path.exists():
        pytest.skip(f"Config file {config_file} not found")
    
    return config_path


@pytest.fixture(scope="session")
def test_config(test_config_file):
    """Load the test configuration."""
    try:
        return Config.load(config_path=test_config_file)
    except Exception as e:
        pytest.skip(f"Failed to load config file {test_config_file}: {e}")


@pytest.fixture
def temp_config_file():
    """Create a temporary config file for testing."""
    config_data = {
        "project_name": "test-project",
        "ai": {
            "provider": "openai",
            "api_key": "test-key",
            "model": "gpt-4",
            "temperature": 0.1,
            "max_tokens": 1000
        },
        "logging": {
            "level": "INFO",
            "file_path": "test.log"
        },
        "security": {
            "allowed_paths": ["./src", "./tests"]
        },
        "session": {
            "session_dir": "./.simacode/sessions"
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        temp_path = Path(f.name)
    
    yield temp_path
    
    # Cleanup
    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def temp_directory():
    """Create a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def mock_ai_config():
    """Mock AI configuration for testing."""
    return {
        "provider": "openai",
        "api_key": "test-key",
        "model": "gpt-4",
        "temperature": 0.1,
        "max_tokens": 1000,
        "timeout": 60
    }


@pytest.fixture
def sample_conversation_data():
    """Sample conversation data for testing."""
    return {
        "id": "test-conversation-id",
        "title": "Test Conversation",
        "messages": [
            {
                "role": "user",
                "content": "Hello, AI!",
                "metadata": {"timestamp": "2024-01-01T00:00:00"}
            },
            {
                "role": "assistant", 
                "content": "Hello, human!",
                "metadata": {"tokens": 10}
            }
        ],
        "metadata": {
            "created_by": "test",
            "tags": ["test", "sample"]
        },
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:01:00"
    }


@pytest.fixture(autouse=True)
def cleanup_test_environment():
    """Clean up test environment after each test."""
    yield
    
    # Clean up any test files that might have been created
    test_files = [
        "test.log",
        "coverage.xml",
    ]
    
    for file_path in test_files:
        path = Path(file_path)
        if path.exists():
            try:
                path.unlink()
            except (OSError, PermissionError):
                pass  # Ignore cleanup errors


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "unit: mark test as unit test"
    )
    config.addinivalue_line(
        "markers", "cli: mark test as CLI-related"
    )
    config.addinivalue_line(
        "markers", "ai: mark test as AI-related"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on test location."""
    for item in items:
        # Add markers based on test file names
        if "test_cli" in item.nodeid:
            item.add_marker(pytest.mark.cli)
        if "test_ai" in item.nodeid:
            item.add_marker(pytest.mark.ai)
        if "integration" in item.nodeid:
            item.add_marker(pytest.mark.integration)
        if "error_handling" in item.nodeid or "streaming" in item.nodeid:
            item.add_marker(pytest.mark.slow)


@pytest.fixture
def no_requests(monkeypatch):
    """Prevent actual HTTP requests during tests."""
    def mock_request(*args, **kwargs):
        raise RuntimeError("Network requests are not allowed in tests!")
    
    monkeypatch.setattr("requests.get", mock_request)
    monkeypatch.setattr("requests.post", mock_request)
    monkeypatch.setattr("aiohttp.ClientSession", mock_request)