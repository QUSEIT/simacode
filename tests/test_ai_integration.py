"""
Integration tests for Phase 2: AI Integration functionality.

These tests verify the complete AI integration flow including:
- End-to-end conversation flows
- Configuration management
- File persistence
- Error handling scenarios
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

import pytest

from simacode.ai.base import Message, Role, AIResponse
from simacode.ai.conversation import Conversation, ConversationManager
from simacode.ai.openai_client import OpenAIClient
from simacode.ai.factory import AIClientFactory
from simacode.config import Config


class TestAIIntegration:
    """Test complete AI integration workflows."""
    
    def test_complete_conversation_flow(self):
        """Test complete conversation flow from creation to persistence."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage_path = Path(tmp_dir)
            manager = ConversationManager(storage_path)
            
            # Create conversation
            conversation = manager.create_conversation("Test Integration")
            assert conversation.title == "Test Integration"
            assert manager.current_conversation == conversation
            
            # Add messages
            user_msg = conversation.add_user_message("Hello, AI!")
            assert user_msg.role == Role.USER
            assert user_msg.content == "Hello, AI!"
            
            assistant_msg = conversation.add_assistant_message("Hello, human!")
            assert assistant_msg.role == Role.ASSISTANT
            assert len(conversation.messages) == 2
            
            # Test persistence
            manager.save_all_conversations()
            
            # Create new manager and verify persistence
            manager2 = ConversationManager(storage_path)
            loaded_conv = manager2.get_conversation(conversation.id)
            assert loaded_conv is not None
            assert loaded_conv.title == "Test Integration"
            assert len(loaded_conv.messages) == 2
            assert loaded_conv.messages[0].content == "Hello, AI!"
            assert loaded_conv.messages[1].content == "Hello, human!"
    
    def test_conversation_manager_multiple_conversations(self):
        """Test managing multiple conversations."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            manager = ConversationManager(Path(tmp_dir))
            
            # Create multiple conversations
            conv1 = manager.create_conversation("Conversation 1")
            conv1.add_user_message("Message in conv1")
            
            conv2 = manager.create_conversation("Conversation 2")
            conv2.add_user_message("Message in conv2")
            
            # Current should be the last created
            assert manager.current_conversation == conv2
            
            # List all conversations
            conversations = manager.list_conversations()
            assert len(conversations) == 2
            
            # Should be sorted by update time (newest first)
            assert conversations[0].title == "Conversation 2"
            assert conversations[1].title == "Conversation 1"
            
            # Switch current conversation
            assert manager.set_current_conversation(conv1.id)
            assert manager.current_conversation == conv1
    
    def test_conversation_persistence_edge_cases(self):
        """Test conversation persistence edge cases."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage_path = Path(tmp_dir)
            
            # Create conversation with special characters and metadata
            manager = ConversationManager(storage_path)
            conversation = manager.create_conversation(
                "Test with émojis 🤖 and special chars!",
                metadata={"custom": "data", "numbers": [1, 2, 3]}
            )
            
            # Add message with metadata
            conversation.add_user_message(
                "Message with émojis 🚀",
                metadata={"timestamp": datetime.now().isoformat()}
            )
            
            manager.save_all_conversations()
            
            # Load and verify
            manager2 = ConversationManager(storage_path)
            loaded = manager2.get_conversation(conversation.id)
            
            assert loaded.title == "Test with émojis 🤖 and special chars!"
            assert loaded.metadata["custom"] == "data"
            assert loaded.metadata["numbers"] == [1, 2, 3]
            assert "🚀" in loaded.messages[0].content
            assert loaded.messages[0].metadata["timestamp"] is not None
    
    def test_conversation_deletion(self):
        """Test conversation deletion functionality."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage_path = Path(tmp_dir)
            manager = ConversationManager(storage_path)
            
            # Create conversations
            conv1 = manager.create_conversation("Keep this")
            conv2 = manager.create_conversation("Delete this")
            
            # Verify both exist
            assert len(manager.conversations) == 2
            assert manager.current_conversation == conv2
            
            # Delete current conversation
            assert manager.delete_conversation(conv2.id)
            
            # Verify deletion
            assert len(manager.conversations) == 1
            assert conv2.id not in manager.conversations
            assert manager.current_conversation == conv1  # Should switch to remaining
            
            # Verify file is deleted
            conv2_file = storage_path / f"{conv2.id}.json"
            assert not conv2_file.exists()
    
    def test_openai_client_configuration_validation(self):
        """Test comprehensive OpenAI client configuration validation."""
        # Valid configuration
        valid_config = {
            "api_key": "sk-test123",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4",
            "max_tokens": 1000,
            "temperature": 0.7,
            "timeout": 30
        }
        client = OpenAIClient(valid_config)
        assert client.validate_config()
        
        # Test various invalid configurations
        invalid_configs = [
            # Missing API key
            {"model": "gpt-4"},
            # Empty API key
            {"api_key": "", "model": "gpt-4"},
            # Invalid temperature (too high)
            {"api_key": "test", "temperature": 3.0},
            # Invalid temperature (negative)
            {"api_key": "test", "temperature": -0.1},
            # Invalid max_tokens
            {"api_key": "test", "max_tokens": 0},
            # Invalid model (empty)
            {"api_key": "test", "model": ""},
            # Invalid base_url
            {"api_key": "test", "base_url": ""},
        ]
        
        for config in invalid_configs:
            if "api_key" not in config or not config.get("api_key"):
                with pytest.raises(ValueError, match="OpenAI API key is required"):
                    OpenAIClient(config)
            else:
                client = OpenAIClient(config)
                assert not client.validate_config()
    
    def test_ai_client_factory_integration(self):
        """Test AI client factory with different configurations."""
        # Test OpenAI client creation
        openai_config = {
            "provider": "openai",
            "api_key": "test-key",
            "model": "gpt-4",
            "temperature": 0.1
        }
        
        client = AIClientFactory.create_client(openai_config)
        assert isinstance(client, OpenAIClient)
        assert client.provider_name == "openai"
        assert client.model == "gpt-4"
        assert client.temperature == 0.1
        
        # Test invalid provider
        invalid_config = {"provider": "invalid-provider"}
        with pytest.raises(ValueError, match="Unsupported AI provider"):
            AIClientFactory.create_client(invalid_config)
        
        # Test default provider (should default to openai)
        default_config = {"api_key": "test-key"}
        client = AIClientFactory.create_client(default_config)
        assert isinstance(client, OpenAIClient)
    
    def test_message_serialization_edge_cases(self):
        """Test message serialization with various content types."""
        # Test with different message types and content
        test_cases = [
            {
                "role": Role.SYSTEM,
                "content": "You are a helpful assistant.",
                "metadata": {"system": True}
            },
            {
                "role": Role.USER,
                "content": "Hello with émojis 🤖 and\nmultiple lines\nof text!",
                "metadata": None
            },
            {
                "role": Role.ASSISTANT,
                "content": '{"json": "content", "numbers": [1, 2, 3]}',
                "metadata": {"tokens": 150, "finish_reason": "stop"}
            },
            {
                "role": Role.TOOL,
                "content": "Tool execution result",
                "metadata": {"tool_id": "file_read", "success": True}
            }
        ]
        
        for case in test_cases:
            # Create message
            message = Message(
                role=case["role"],
                content=case["content"],
                metadata=case["metadata"]
            )
            
            # Serialize to dict
            data = message.to_dict()
            assert data["role"] == case["role"].value
            assert data["content"] == case["content"]
            
            if case["metadata"]:
                assert data["metadata"] == case["metadata"]
            else:
                assert "metadata" not in data or data["metadata"] is None
            
            # Deserialize back
            restored = Message.from_dict(data)
            assert restored.role == case["role"]
            assert restored.content == case["content"]
            assert restored.metadata == case["metadata"]
    
    def test_conversation_get_last_n_messages(self):
        """Test retrieving last N messages from conversation."""
        conversation = Conversation("Test Conversation")
        
        # Add multiple messages
        messages_content = [
            "Message 1", "Message 2", "Message 3", 
            "Message 4", "Message 5"
        ]
        
        for i, content in enumerate(messages_content):
            if i % 2 == 0:
                conversation.add_user_message(content)
            else:
                conversation.add_assistant_message(content)
        
        # Test getting last N messages
        assert len(conversation.get_last_n_messages(3)) == 3
        assert len(conversation.get_last_n_messages(10)) == 5  # All messages
        assert len(conversation.get_last_n_messages(0)) == 0
        
        # Check content of last 2 messages
        last_2 = conversation.get_last_n_messages(2)
        assert last_2[0].content == "Message 4"
        assert last_2[1].content == "Message 5"
    
    def test_conversation_metadata_operations(self):
        """Test conversation metadata handling."""
        metadata = {
            "project": "test-project",
            "tags": ["ai", "chat"],
            "settings": {"temperature": 0.7}
        }
        
        conversation = Conversation(
            "Test Conversation",
            metadata=metadata
        )
        
        # Verify metadata is preserved
        assert conversation.metadata["project"] == "test-project"
        assert conversation.metadata["tags"] == ["ai", "chat"]
        assert conversation.metadata["settings"]["temperature"] == 0.7
        
        # Test serialization with metadata
        data = conversation.to_dict()
        assert data["metadata"] == metadata
        
        # Test deserialization
        restored = Conversation.from_dict(data)
        assert restored.metadata == metadata
    
    def test_conversation_manager_edge_cases(self):
        """Test conversation manager edge cases."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage_path = Path(tmp_dir)
            
            # Test with empty storage directory
            manager = ConversationManager(storage_path)
            assert len(manager.conversations) == 0
            assert manager.current_conversation is None
            
            # Get current conversation should create one
            current = manager.get_current_conversation()
            assert current is not None
            assert len(manager.conversations) == 1
            
            # Test deleting non-existent conversation
            assert not manager.delete_conversation("non-existent-id")
            
            # Test setting non-existent current conversation
            assert not manager.set_current_conversation("non-existent-id")
            
            # Test with invalid JSON files in storage
            invalid_json_file = storage_path / "invalid.json"
            invalid_json_file.write_text("invalid json content")
            
            # Should not crash when loading
            manager2 = ConversationManager(storage_path)
            # Should still have the valid conversation
            assert len(manager2.conversations) == 1


class TestAIResponseHandling:
    """Test AI response handling and processing."""
    
    def test_ai_response_creation(self):
        """Test AI response object creation and properties."""
        response = AIResponse(
            content="Hello, world!",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            model="gpt-4",
            finish_reason="stop",
            metadata={
                "response_id": "resp_123",
                "created": 1234567890,
                "system_fingerprint": "fp_abc123"
            }
        )
        
        assert response.content == "Hello, world!"
        assert response.usage["total_tokens"] == 15
        assert response.model == "gpt-4"
        assert response.finish_reason == "stop"
        assert response.metadata["response_id"] == "resp_123"
    
    def test_ai_response_minimal(self):
        """Test AI response with minimal required fields."""
        response = AIResponse(content="Simple response")
        
        assert response.content == "Simple response"
        assert response.usage is None
        assert response.model is None
        assert response.finish_reason is None
        assert response.metadata is None


class TestConfigurationIntegration:
    """Test configuration integration with AI components."""
    
    def test_config_with_ai_settings(self):
        """Test configuration loading with AI settings."""
        # Create temporary config with AI settings
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
                "level": "INFO"
            },
            "security": {
                "allowed_paths": ["./src", "./tests"]
            },
            "session": {
                "session_dir": "./.simacode/sessions"
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            import yaml
            yaml.dump(config_data, f)
            config_path = Path(f.name)
        
        try:
            # Load config
            config = Config.load(config_path=config_path)
            
            # Verify AI configuration
            assert config.ai.provider == "openai"
            assert config.ai.model == "gpt-4"
            assert config.ai.temperature == 0.1
            assert config.ai.max_tokens == 1000
            
            # Test creating AI client from config
            ai_config = config.ai.model_dump()
            client = AIClientFactory.create_client(ai_config)
            assert isinstance(client, OpenAIClient)
            assert client.model == "gpt-4"
            assert client.temperature == 0.1
            
        finally:
            config_path.unlink()


class TestErrorHandling:
    """Test error handling scenarios in AI integration."""
    
    def test_conversation_manager_with_corrupted_files(self):
        """Test conversation manager handling corrupted session files."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            storage_path = Path(tmp_dir)
            
            # Create corrupted JSON file
            corrupted_file = storage_path / "corrupted.json"
            corrupted_file.write_text("{ invalid json")
            
            # Create empty file
            empty_file = storage_path / "empty.json"
            empty_file.write_text("")
            
            # Create file with invalid conversation structure
            invalid_structure = storage_path / "invalid_structure.json"
            invalid_structure.write_text('{"not": "a conversation"}')
            
            # Manager should handle these gracefully
            manager = ConversationManager(storage_path)
            assert len(manager.conversations) == 0
            
            # Should still work normally
            conversation = manager.create_conversation("Test")
            assert len(manager.conversations) == 1
    
    def test_openai_client_missing_required_fields(self):
        """Test OpenAI client with missing required configuration fields."""
        with pytest.raises(ValueError, match="OpenAI API key is required"):
            OpenAIClient({})
        
        with pytest.raises(ValueError, match="OpenAI API key is required"):
            OpenAIClient({"model": "gpt-4"})
        
        with pytest.raises(ValueError, match="OpenAI API key is required"):
            OpenAIClient({"api_key": None})
    
    def test_message_creation_edge_cases(self):
        """Test message creation with edge cases."""
        # Test with very long content
        long_content = "A" * 10000
        message = Message(role=Role.USER, content=long_content)
        assert len(message.content) == 10000
        
        # Test with empty content
        empty_message = Message(role=Role.ASSISTANT, content="")
        assert empty_message.content == ""
        
        # Test with special characters
        special_content = "Content with\nlines\tand\r\nspecial chars: 🤖💻🚀"
        special_message = Message(role=Role.USER, content=special_content)
        assert special_message.content == special_content
        
        # Test serialization/deserialization of edge cases
        for msg in [message, empty_message, special_message]:
            data = msg.to_dict()
            restored = Message.from_dict(data)
            assert restored.content == msg.content
            assert restored.role == msg.role