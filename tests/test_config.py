"""
Tests for configuration management.
"""

import os
import tempfile
from pathlib import Path

import pytest
import yaml

from simacode.config import Config, ConfigValidationError


class TestConfig:
    """Test cases for configuration management."""

    def test_default_config(self):
        """Test that default configuration loads correctly."""
        config = Config()
        
        assert config.project_name == "SimaCode Project"
        assert config.logging.level == "INFO"
        assert config.ai.provider == "openai"
        assert config.ai.model == "gpt-4"

    def test_config_from_dict(self):
        """Test configuration creation from dictionary."""
        config_data = {
            "project_name": "Test Project",
            "logging": {"level": "DEBUG"},
            "ai": {"model": "gpt-3.5-turbo", "temperature": 0.7}
        }
        
        config = Config(**config_data)
        assert config.project_name == "Test Project"
        assert config.logging.level == "DEBUG"
        assert config.ai.model == "gpt-3.5-turbo"
        assert config.ai.temperature == 0.7

    def test_invalid_log_level(self):
        """Test that invalid log levels raise validation errors."""
        with pytest.raises(ValueError, match="Invalid log level"):
            Config(logging={"level": "INVALID"})

    def test_invalid_temperature(self):
        """Test that invalid temperature values raise validation errors."""
        with pytest.raises(ValueError):
            Config(ai={"temperature": 3.0})

    def test_load_from_file(self, tmp_path):
        """Test loading configuration from YAML file."""
        config_file = tmp_path / "config.yaml"
        config_data = {
            "project_name": "File Test Project",
            "logging": {"level": "WARNING"},
            "ai": {"model": "claude-3"}
        }
        
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)
        
        config = Config.load(config_path=config_file)
        assert config.project_name == "File Test Project"
        assert config.logging.level == "WARNING"
        assert config.ai.model == "claude-3"

    def test_load_from_env_var(self, tmp_path):
        """Test loading API key from environment variable."""
        os.environ["SIMACODE_API_KEY"] = "test-api-key"
        config = Config()
        
        assert config.ai.api_key == "test-api-key"
        
        # Clean up
        del os.environ["SIMACODE_API_KEY"]

    def test_save_to_file(self, tmp_path):
        """Test saving configuration to file."""
        config = Config(project_name="Save Test")
        config_file = tmp_path / "saved_config.yaml"
        
        config.save_to_file(config_file)
        
        assert config_file.exists()
        
        # Load it back and verify
        loaded_config = Config.load(config_path=config_file)
        assert loaded_config.project_name == "Save Test"

    def test_config_validation(self):
        """Test configuration validation."""
        config = Config()
        config.validate()  # Should not raise

    def test_get_effective_value(self):
        """Test getting effective configuration values."""
        config = Config(
            ai={"model": "test-model", "temperature": 0.5}
        )
        
        assert config.get_effective_value("ai.model") == "test-model"
        assert config.get_effective_value("ai.temperature") == 0.5
        assert config.get_effective_value("nonexistent.key") is None

    def test_path_conversion(self):
        """Test that string paths are converted to Path objects."""
        config = Config(
            security={
                "allowed_paths": ["/tmp/test"],
                "forbidden_paths": ["/etc"]
            }
        )
        
        assert isinstance(config.security.allowed_paths[0], Path)
        assert isinstance(config.security.forbidden_paths[0], Path)
        assert config.security.allowed_paths[0] == Path("/tmp/test")

    def test_session_dir_creation(self, tmp_path):
        """Test that session directory is created automatically."""
        session_dir = tmp_path / "test_sessions"
        config = Config(session={"session_dir": session_dir})
        
        assert config.session.session_dir.exists()
        assert config.session.session_dir.is_dir()

    def test_load_nonexistent_file(self):
        """Test loading from non-existent file."""
        nonexistent = Path("/nonexistent/config.yaml")
        config = Config.load(config_path=nonexistent)
        
        # Should fall back to default configuration
        assert config.project_name == "SimaCode Project"