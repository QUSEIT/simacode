"""
Simplified AI tests that avoid complex async mocking issues.

These tests focus on core functionality without complex network mocking
which often causes issues in test environments.
"""

import pytest
from unittest.mock import MagicMock

from simacode.ai.base import Message, Role, AIResponse
from simacode.ai.conversation import Conversation
from simacode.ai.factory import AIClientFactory
from simacode.ai.openai_client import OpenAIClient


class TestBasicAIFunctionality:
    """Test basic AI functionality without complex mocking."""
    
    def test_message_roles_and_content(self):
        """Test message creation with different roles."""
        user_msg = Message(role=Role.USER, content="Hello")
        assistant_msg = Message(role=Role.ASSISTANT, content="Hi there")
        system_msg = Message(role=Role.SYSTEM, content="You are helpful")
        
        assert user_msg.role == Role.USER
        assert assistant_msg.role == Role.ASSISTANT
        assert system_msg.role == Role.SYSTEM
        
        # Test serialization
        user_dict = user_msg.to_dict()
        assert user_dict["role"] == "user"
        assert user_dict["content"] == "Hello"
        
        # Test deserialization
        restored = Message.from_dict(user_dict)
        assert restored.role == Role.USER
        assert restored.content == "Hello"
    
    def test_conversation_basic_operations(self):
        """Test basic conversation operations."""
        conv = Conversation("Test Conversation")
        
        # Test adding messages
        conv.add_user_message("Question 1")
        conv.add_assistant_message("Answer 1")
        conv.add_user_message("Question 2")
        
        assert len(conv.messages) == 3
        assert conv.messages[0].role == Role.USER
        assert conv.messages[1].role == Role.ASSISTANT
        assert conv.messages[2].role == Role.USER
        
        # Test get_last_n_messages with various inputs
        assert len(conv.get_last_n_messages(0)) == 0
        assert len(conv.get_last_n_messages(1)) == 1
        assert len(conv.get_last_n_messages(2)) == 2
        assert len(conv.get_last_n_messages(10)) == 3  # All messages
        
        # Test clearing
        conv.clear_messages()
        assert len(conv.messages) == 0
    
    def test_ai_response_creation(self):
        """Test AI response object creation."""
        response = AIResponse(
            content="Test response",
            usage={"prompt_tokens": 5, "completion_tokens": 3},
            model="test-model",
            finish_reason="stop"
        )
        
        assert response.content == "Test response"
        assert response.usage["prompt_tokens"] == 5
        assert response.model == "test-model"
        assert response.finish_reason == "stop"
    
    def test_openai_client_config_validation(self):
        """Test OpenAI client configuration validation without network calls."""
        # Valid config
        valid_config = {
            "api_key": "test-key",
            "model": "gpt-4",
            "temperature": 0.7,
            "max_tokens": 1000
        }
        client = OpenAIClient(valid_config)
        assert client.validate_config()
        assert client.provider_name == "openai"
        
        # Invalid configs
        invalid_configs = [
            {"api_key": "test", "temperature": 3.0},  # Invalid temperature
            {"api_key": "test", "max_tokens": -1},    # Invalid max_tokens
            {"api_key": "test", "model": ""},         # Invalid model
        ]
        
        for config in invalid_configs:
            client = OpenAIClient(config)
            assert not client.validate_config()
    
    def test_factory_basic_operations(self):
        """Test factory operations without network calls."""
        # Test provider listing
        providers = AIClientFactory.list_providers()
        assert "openai" in providers
        
        # Test client creation
        config = {
            "provider": "openai",
            "api_key": "test-key",
            "model": "gpt-4"
        }
        client = AIClientFactory.create_client(config)
        assert isinstance(client, OpenAIClient)
        assert client.provider_name == "openai"
        
        # Test invalid provider
        with pytest.raises(ValueError, match="Unsupported AI provider"):
            AIClientFactory.create_client({"provider": "invalid"})
    
    def test_conversation_serialization(self):
        """Test conversation serialization and deserialization."""
        # Create conversation with messages
        conv = Conversation(title="Serialization Test")
        conv.add_user_message("Hello", metadata={"test": True})
        conv.add_assistant_message("Hi there!")
        
        # Serialize
        data = conv.to_dict()
        assert data["title"] == "Serialization Test"
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][0]["metadata"]["test"] is True
        
        # Deserialize
        restored = Conversation.from_dict(data)
        assert restored.title == "Serialization Test"
        assert len(restored.messages) == 2
        assert restored.messages[0].role == Role.USER
        assert restored.messages[0].metadata["test"] is True
    
    def test_message_edge_cases(self):
        """Test message handling with edge cases."""
        # Test with empty content
        empty_msg = Message(role=Role.USER, content="")
        assert empty_msg.content == ""
        
        # Test with long content
        long_content = "A" * 10000
        long_msg = Message(role=Role.ASSISTANT, content=long_content)
        assert len(long_msg.content) == 10000
        
        # Test with special characters
        special_content = "Unicode: 🤖 Newlines:\nTabs:\t End"
        special_msg = Message(role=Role.USER, content=special_content)
        
        # Test serialization preserves special characters
        data = special_msg.to_dict()
        restored = Message.from_dict(data)
        assert restored.content == special_content
    
    def test_conversation_metadata_handling(self):
        """Test conversation metadata operations."""
        metadata = {
            "project": "test",
            "tags": ["ai", "test"],
            "config": {"temperature": 0.5}
        }
        
        conv = Conversation("Metadata Test", metadata=metadata)
        assert conv.metadata["project"] == "test"
        assert conv.metadata["tags"] == ["ai", "test"]
        
        # Test serialization preserves metadata
        data = conv.to_dict()
        restored = Conversation.from_dict(data)
        assert restored.metadata == metadata


class TestFactoryExtensions:
    """Test factory extensions without complex async operations."""
    
    def setup_method(self):
        """Store original providers to restore later."""
        self._original_providers = AIClientFactory._providers.copy()
    
    def teardown_method(self):
        """Restore original providers."""
        AIClientFactory._providers = self._original_providers
    
    def test_custom_provider_registration(self):
        """Test registering custom providers."""
        from simacode.ai.base import AIClient
        
        # Create mock provider class that properly inherits from AIClient
        class MockProvider(AIClient):
            def __init__(self, config):
                super().__init__(config)
                self._provider_name = "mock"
            
            @property
            def provider_name(self):
                return self._provider_name
            
            async def chat(self, messages):
                return AIResponse(content="Mock response")
            
            async def chat_stream(self, messages):
                yield "Mock stream"
            
            def validate_config(self):
                return True
        
        # Test registration
        AIClientFactory.register_provider("mock", MockProvider)
        
        # Verify it's registered
        providers = AIClientFactory.list_providers()
        assert "mock" in providers
        
        # Test creating client
        config = {"provider": "mock", "api_key": "test"}
        client = AIClientFactory.create_client(config)
        assert client.provider_name == "mock"
    
    def test_invalid_provider_registration(self):
        """Test registering invalid provider classes."""
        # Test with non-class object
        with pytest.raises(ValueError, match="Client class must inherit from AIClient"):
            AIClientFactory.register_provider("invalid", str)
        
        # Test with wrong class hierarchy
        class WrongClass:
            pass
        
        with pytest.raises(ValueError, match="Client class must inherit from AIClient"):
            AIClientFactory.register_provider("wrong", WrongClass)


class TestConfigurationValidation:
    """Test configuration validation scenarios."""
    
    def test_openai_config_edge_cases(self):
        """Test OpenAI configuration with edge cases."""
        base_config = {"api_key": "test-key"}
        
        # Test boundary values
        edge_cases = [
            # Temperature boundaries
            {**base_config, "temperature": 0.0},    # Valid minimum
            {**base_config, "temperature": 2.0},    # Valid maximum
            {**base_config, "temperature": -0.1},   # Invalid (too low)
            {**base_config, "temperature": 2.1},    # Invalid (too high)
            
            # Max tokens boundaries
            {**base_config, "max_tokens": 1},       # Valid minimum
            {**base_config, "max_tokens": 0},       # Invalid
            {**base_config, "max_tokens": -1},      # Invalid
            
            # Model validation
            {**base_config, "model": "gpt-4"},      # Valid
            {**base_config, "model": ""},           # Invalid
            {**base_config, "model": None},         # Invalid
        ]
        
        expected_valid = [True, True, False, False, True, False, False, True, False, False]
        
        for i, config in enumerate(edge_cases):
            try:
                client = OpenAIClient(config)
                is_valid = client.validate_config()
                assert is_valid == expected_valid[i], f"Config {i} validation mismatch: {config}"
            except (ValueError, TypeError):
                # Some configs might raise exceptions during creation
                assert not expected_valid[i], f"Config {i} should be invalid but raised exception: {config}"