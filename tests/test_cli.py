"""
Tests for CLI functionality.
"""

import pytest
from click.testing import CliRunner

from simacode.cli import main


class TestCLI:
    """Test cases for CLI commands."""

    def test_main_help(self):
        """Test that help command works."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        
        assert result.exit_code == 0
        assert "SimaCode:" in result.output
        assert "--help" in result.output
        assert "--version" in result.output

    def test_version(self):
        """Test version display."""
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        
        # Version is handled by the main command, not standalone
        assert result.exit_code == 0

    def test_config_command(self):
        """Test config command."""
        runner = CliRunner()
        result = runner.invoke(main, ["config", "--check"])
        
        assert result.exit_code == 0
        assert "Configuration is valid" in result.output

    def test_config_show(self):
        """Test config show command."""
        runner = CliRunner()
        result = runner.invoke(main, ["config"])
        
        assert result.exit_code == 0
        assert "Current Configuration:" in result.output

    def test_init_command(self):
        """Test init command."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["init"])
            
            assert result.exit_code == 0
            assert "Created directory:" in result.output
            assert "Project initialized successfully!" in result.output

    def test_chat_command_no_message(self):
        """Test chat command without message."""
        runner = CliRunner()
        result = runner.invoke(main, ["chat"])
        
        assert result.exit_code == 0
        assert "No message provided" in result.output

    def test_chat_command_with_message(self):
        """Test chat command with message."""
        runner = CliRunner()
        result = runner.invoke(main, ["chat", "Hello AI"])
        
        assert result.exit_code == 0
        assert "You: Hello AI" in result.output
        assert "AI: Chat functionality coming soon..." in result.output

    def test_chat_interactive_flag(self):
        """Test chat command with interactive flag."""
        runner = CliRunner()
        result = runner.invoke(main, ["chat", "--interactive"])
        
        assert result.exit_code == 0
        assert "Chat functionality" in result.output

    def test_verbose_flag(self):
        """Test verbose flag functionality."""
        runner = CliRunner()
        result = runner.invoke(main, ["--verbose", "config", "--check"])
        
        assert result.exit_code == 0
        assert "Configuration is valid" in result.output

    def test_config_file_option(self):
        """Test custom config file option."""
        runner = CliRunner()
        
        # Create a temporary config file
        config_content = """
project_name: "Test Project"
logging:
  level: "DEBUG"
"""
        
        with runner.isolated_filesystem():
            with open("test_config.yaml", "w") as f:
                f.write(config_content)
            
            result = runner.invoke(main, ["-c", "test_config.yaml", "config"])
            
            assert result.exit_code == 0
            assert "Test Project" in result.output

    def test_invalid_config_file(self):
        """Test handling of invalid config file."""
        runner = CliRunner()
        
        with runner.isolated_filesystem():
            with open("invalid_config.yaml", "w") as f:
                f.write("invalid: yaml: content: [")
            
            result = runner.invoke(main, ["-c", "invalid_config.yaml", "config"])
            
            # Should exit with error due to invalid YAML
            assert result.exit_code != 0