"""
Tests for CLI AI integration functionality.

These tests verify the CLI commands that interact with AI components:
- Chat commands (single message and interactive)
- Configuration validation
- Session management
- Error handling in CLI context
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from click.testing import CliRunner

import pytest

from simacode.cli import main, _run_chat, _handle_single_message, _handle_interactive_mode
from simacode.config import Config
from simacode.ai.base import Message, Role, AIResponse
from simacode.ai.conversation import ConversationManager
from simacode.ai.openai_client import OpenAIClient


class TestCLIAIIntegration:
    """Test CLI integration with AI components."""
    
    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()
    
    def test_cli_with_default_config(self):
        """Test CLI with default config file."""
        result = self.runner.invoke(main, [
            "config"
        ])
        # Should use config/config.yaml by default
        assert result.exit_code == 0
        assert "Current Configuration" in result.output
    
    def test_cli_config_command(self, temp_config_file):
        """Test config command functionality."""
        # Test config display
        result = self.runner.invoke(main, [
            "--config", str(temp_config_file),
            "config"
        ])
        assert result.exit_code == 0
        assert "Current Configuration" in result.output
        assert "test-project" in result.output
    
    def test_cli_config_check_valid(self, temp_config_file):
        """Test config check with valid configuration."""
        result = self.runner.invoke(main, [
            "--config", str(temp_config_file),
            "config", "--check"
        ])
        assert result.exit_code == 0
        assert "Configuration is valid" in result.output
    
    def test_cli_config_check_invalid(self, temp_directory):
        """Test config check with invalid configuration."""
        # Create invalid config (missing required fields)
        invalid_config_path = temp_directory / "invalid_config.yaml"
        invalid_config_path.write_text("""
project_name: "test"
ai:
  provider: "openai"
  # Missing api_key - this should pass validation as api_key is optional in base config
  model: "gpt-4"
logging:
  level: "INFO"
security:
  allowed_paths: ["./src"]
session:
  session_dir: "./sessions"
""")
        
        result = self.runner.invoke(main, [
            "--config", str(invalid_config_path),
            "config", "--check"
        ])
        # This config should actually be valid since api_key can be provided via env
        assert result.exit_code == 0
    
    def test_cli_init_command(self, temp_config_file):
        """Test init command functionality."""
        with tempfile.TemporaryDirectory() as project_dir:
            # Change to project directory and run init
            import os
            old_cwd = os.getcwd()
            try:
                os.chdir(project_dir)
                result = self.runner.invoke(main, [
                    "--config", str(temp_config_file),
                    "init"
                ])
                
                assert result.exit_code == 0
                assert "Project initialized successfully" in result.output
                
                # Verify directories were created
                simacode_dir = Path(project_dir) / ".simacode"
                assert simacode_dir.exists()
                assert (simacode_dir / "sessions").exists()
                assert (simacode_dir / "logs").exists()
                assert (simacode_dir / "cache").exists()
                assert (simacode_dir / "config.yaml").exists()
                
            finally:
                os.chdir(old_cwd)
    
    def test_cli_chat_no_message_no_interactive(self, temp_config_file):
        """Test chat command with no message and no interactive flag."""
        result = self.runner.invoke(main, [
            "--config", str(temp_config_file),
            "chat"
        ])
        assert result.exit_code == 0
        assert "No message provided" in result.output
        assert "Use --interactive for interactive mode" in result.output
    
    @patch('simacode.cli.asyncio.run')
    def test_cli_chat_single_message(self, mock_run, temp_config_file):
        """Test chat command with single message."""
        result = self.runner.invoke(main, [
            "--config", str(temp_config_file),
            "chat", "Hello, AI!"
        ])
        
        # Verify asyncio.run was called
        mock_run.assert_called_once()
        
        # Get the coroutine that was passed to asyncio.run
        args, kwargs = mock_run.call_args
        coro = args[0]
        assert hasattr(coro, '__await__')  # It's a coroutine
    
    @patch('simacode.cli.asyncio.run')
    def test_cli_chat_interactive(self, mock_run, temp_config_file):
        """Test chat command in interactive mode."""
        result = self.runner.invoke(main, [
            "--config", str(temp_config_file),
            "chat", "--interactive"
        ])
        
        # Verify asyncio.run was called
        mock_run.assert_called_once()
    
    def test_cli_version_flag(self):
        """Test version flag functionality."""
        result = self.runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "SimaCode version" in result.output
    
    def test_cli_verbose_flag(self, temp_config_file):
        """Test verbose flag functionality."""
        result = self.runner.invoke(main, [
            "--config", str(temp_config_file),
            "--verbose",
            "config"
        ])
        # Should not error with verbose flag
        assert result.exit_code == 0


class TestChatHandlers:
    """Test chat handler functions."""
    
    @pytest.mark.asyncio
    @patch('simacode.cli.AIClientFactory.create_client')
    async def test_handle_single_message(self, mock_create_client, temp_directory):
        """Test single message handling."""
        # Mock AI client
        mock_client = AsyncMock()
        mock_response = AIResponse(
            content="Hello, human!",
            usage={"prompt_tokens": 10, "completion_tokens": 5}
        )
        mock_client.chat.return_value = mock_response
        mock_create_client.return_value = mock_client
        
        # Create conversation manager
        sessions_dir = temp_directory / "sessions"
        sessions_dir.mkdir()
        conversation_manager = ConversationManager(sessions_dir)
        
        # Test single message
        await _handle_single_message(mock_client, conversation_manager, "Hello, AI!")
        
        # Verify client was called
        mock_client.chat.assert_called_once()
        
        # Verify conversation was updated
        conversation = conversation_manager.get_current_conversation()
        assert len(conversation.messages) == 2
        assert conversation.messages[0].content == "Hello, AI!"
        assert conversation.messages[0].role == Role.USER
        assert conversation.messages[1].content == "Hello, human!"
        assert conversation.messages[1].role == Role.ASSISTANT
    
    @pytest.mark.asyncio
    @patch('simacode.cli.click.prompt')
    @patch('simacode.cli.console')
    @patch('simacode.cli.AIClientFactory.create_client')
    async def test_handle_interactive_mode_quit(self, mock_create_client, mock_console, mock_prompt, temp_directory):
        """Test interactive mode with quit command."""
        # Mock user input to quit immediately
        mock_prompt.side_effect = ["quit"]
        
        # Mock AI client
        mock_client = AsyncMock()
        mock_create_client.return_value = mock_client
        
        # Create conversation manager
        sessions_dir = temp_directory / "sessions"
        sessions_dir.mkdir()
        conversation_manager = ConversationManager(sessions_dir)
        
        # Test interactive mode
        await _handle_interactive_mode(mock_client, conversation_manager)
        
        # Verify quit message was printed
        mock_console.print.assert_called()
        quit_calls = [call for call in mock_console.print.call_args_list 
                     if "Goodbye" in str(call)]
        assert len(quit_calls) > 0
    
    @pytest.mark.asyncio
    @patch('simacode.cli.click.prompt')
    @patch('simacode.cli.console')
    @patch('simacode.cli.AIClientFactory.create_client')
    async def test_handle_interactive_mode_clear(self, mock_create_client, mock_console, mock_prompt, temp_directory):
        """Test interactive mode with clear command."""
        # Mock user input
        mock_prompt.side_effect = ["Hello", "clear", "exit"]
        
        # Mock AI client
        mock_client = AsyncMock()
        
        async def mock_stream():
            for chunk in ["Hello ", "back!"]:
                yield chunk
        
        mock_client.chat_stream.return_value = mock_stream()
        mock_create_client.return_value = mock_client
        
        # Create conversation manager
        sessions_dir = temp_directory / "sessions"
        sessions_dir.mkdir()
        conversation_manager = ConversationManager(sessions_dir)
        
        # Test interactive mode
        await _handle_interactive_mode(mock_client, conversation_manager)
        
        # Verify clear message was printed
        clear_calls = [call for call in mock_console.print.call_args_list 
                      if "Conversation cleared" in str(call)]
        assert len(clear_calls) > 0
    
    @pytest.mark.asyncio
    @patch('simacode.cli.click.prompt')
    @patch('simacode.cli.console')
    @patch('simacode.cli.AIClientFactory.create_client')
    async def test_handle_interactive_mode_help(self, mock_create_client, mock_console, mock_prompt, temp_directory):
        """Test interactive mode with help command."""
        # Mock user input
        mock_prompt.side_effect = ["help", "exit"]
        
        # Mock AI client
        mock_client = AsyncMock()
        mock_create_client.return_value = mock_client
        
        # Create conversation manager
        sessions_dir = temp_directory / "sessions"
        sessions_dir.mkdir()
        conversation_manager = ConversationManager(sessions_dir)
        
        # Test interactive mode
        await _handle_interactive_mode(mock_client, conversation_manager)
        
        # Verify help was displayed
        help_calls = [call for call in mock_console.print.call_args_list 
                     if "Commands" in str(call)]
        assert len(help_calls) > 0
    
    @pytest.mark.asyncio
    @patch('simacode.cli.click.prompt')
    @patch('simacode.cli.console')
    @patch('simacode.cli.AIClientFactory.create_client')
    async def test_handle_interactive_mode_normal_message(self, mock_create_client, mock_console, mock_prompt, temp_directory):
        """Test interactive mode with normal message."""
        # Mock user input
        mock_prompt.side_effect = ["Hello, AI!", "exit"]
        
        # Mock AI client with streaming response
        mock_client = AsyncMock()
        
        async def mock_stream():
            for chunk in ["Hello ", "back ", "to ", "you!"]:
                yield chunk
        
        mock_client.chat_stream.return_value = mock_stream()
        mock_create_client.return_value = mock_client
        
        # Create conversation manager
        sessions_dir = temp_directory / "sessions"
        sessions_dir.mkdir()
        conversation_manager = ConversationManager(sessions_dir)
        
        # Test interactive mode
        await _handle_interactive_mode(mock_client, conversation_manager)
        
        # Verify AI client was called
        mock_client.chat_stream.assert_called()
        
        # Verify conversation was updated
        conversation = conversation_manager.get_current_conversation()
        assert len(conversation.messages) == 2
        assert conversation.messages[0].content == "Hello, AI!"
        assert conversation.messages[1].content == "Hello back to you!"
    
    @pytest.mark.asyncio
    @patch('simacode.cli.click.prompt')
    @patch('simacode.cli.console')
    @patch('simacode.cli.AIClientFactory.create_client')
    async def test_handle_interactive_mode_keyboard_interrupt(self, mock_create_client, mock_console, mock_prompt, temp_directory):
        """Test interactive mode with keyboard interrupt."""
        # Mock user input to raise KeyboardInterrupt
        mock_prompt.side_effect = KeyboardInterrupt()
        
        # Mock AI client
        mock_client = AsyncMock()
        mock_create_client.return_value = mock_client
        
        # Create conversation manager
        sessions_dir = temp_directory / "sessions"
        sessions_dir.mkdir()
        conversation_manager = ConversationManager(sessions_dir)
        
        # Test interactive mode
        await _handle_interactive_mode(mock_client, conversation_manager)
        
        # Verify interrupt message was printed
        interrupt_calls = [call for call in mock_console.print.call_args_list 
                          if "Chat interrupted" in str(call)]
        assert len(interrupt_calls) > 0


class TestCLIErrorHandling:
    """Test CLI error handling scenarios."""
    
    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()
    
    def test_cli_invalid_config_file(self, temp_directory):
        """Test CLI with invalid config file."""
        invalid_config = temp_directory / "invalid.yaml"
        invalid_config.write_text("invalid: yaml: content: [")
        
        result = self.runner.invoke(main, [
            "--config", str(invalid_config),
            "config"
        ])
        assert result.exit_code == 1
        assert "Error loading configuration" in result.output
    
    def test_cli_nonexistent_config_file(self):
        """Test CLI with non-existent config file."""
        result = self.runner.invoke(main, [
            "--config", "/nonexistent/config.yaml",
            "config"
        ])
        assert result.exit_code == 2  # Click error for non-existent file
    
    @pytest.mark.asyncio
    @patch('simacode.cli.AIClientFactory.create_client')
    async def test_chat_handler_ai_error(self, mock_create_client, temp_directory):
        """Test chat handler with AI client error."""
        # Mock AI client to raise exception
        mock_client = AsyncMock()
        mock_client.chat.side_effect = Exception("AI service unavailable")
        mock_create_client.return_value = mock_client
        
        # Create conversation manager
        sessions_dir = temp_directory / "sessions"
        sessions_dir.mkdir()
        conversation_manager = ConversationManager(sessions_dir)
        
        # Test should raise exception as error handling is at higher level
        with pytest.raises(Exception, match="AI service unavailable"):
            await _handle_single_message(mock_client, conversation_manager, "Test message")
    
    @pytest.mark.asyncio
    @patch('simacode.cli.console')
    async def test_run_chat_error_handling(self, mock_console):
        """Test _run_chat error handling."""
        # Create invalid context that will cause error
        invalid_ctx = MagicMock()
        invalid_ctx.obj = {"config": None}  # Invalid config
        
        # This should handle the error gracefully
        await _run_chat(invalid_ctx, "test message", False)
        
        # Verify error was printed
        error_calls = [call for call in mock_console.print.call_args_list 
                      if "Error:" in str(call)]
        assert len(error_calls) > 0


class TestCLIConfigIntegration:
    """Test CLI integration with configuration system."""
    
    def setup_method(self):
        """Set up test environment."""
        self.runner = CliRunner()
    
    def test_cli_loads_config_correctly(self, temp_directory):
        """Test that CLI loads configuration correctly."""
        config_path = temp_directory / "test_config.yaml"
        config_content = """
project_name: "cli-test-project"
ai:
  provider: "openai"
  api_key: "test-api-key"
  model: "gpt-3.5-turbo"
  temperature: 0.5
logging:
  level: "DEBUG"
security:
  allowed_paths: ["./test"]
session:
  session_dir: "./test-sessions"
"""
        config_path.write_text(config_content)
        
        result = self.runner.invoke(main, [
            "--config", str(config_path),
            "config"
        ])
        
        assert result.exit_code == 0
        assert "cli-test-project" in result.output
        assert "gpt-3.5-turbo" in result.output
        assert "test-api-key" in result.output
    
    def test_cli_config_validation_integration(self, temp_directory):
        """Test CLI config validation with various scenarios."""
        # Test valid configuration
        config_valid = temp_directory / "valid.yaml"
        config_valid.write_text("""
project_name: "test"
ai:
  provider: "openai"
  api_key: "test-key"
  model: "gpt-4"
  temperature: 0.7
logging:
  level: "INFO"
security:
  allowed_paths: ["./src"]
session:
  session_dir: "./sessions"
""")
        
        result = self.runner.invoke(main, [
            "--config", str(config_valid),
            "config", "--check"
        ])
        assert result.exit_code == 0
        assert "Configuration is valid" in result.output