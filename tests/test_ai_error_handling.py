"""
Comprehensive error handling tests for Phase 2: AI Integration.

These tests focus on:
- Network and API error scenarios
- Configuration error handling
- Resource exhaustion scenarios
- Recovery and retry mechanisms
- Graceful degradation
- Data corruption handling
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime
import aiohttp

import pytest

from simacode.ai.base import Message, Role, AIResponse
from simacode.ai.conversation import Conversation, ConversationManager
from simacode.ai.openai_client import OpenAIClient
from simacode.ai.factory import AIClientFactory


class TestNetworkErrorHandling:
    """Test network and API error scenarios."""
    
    @pytest.mark.asyncio
    async def test_openai_client_network_timeout(self):
        """Test OpenAI client handling network timeout."""
        config = {
            "api_key": "test-key",
            "model": "gpt-4",
            "timeout": 1  # Very short timeout
        }
        client = OpenAIClient(config)
        messages = [Message(role=Role.USER, content="Hello")]
        
        # Create a proper mock that returns an async context manager
        class MockPost:
            def __call__(self, *args, **kwargs):
                return MockResponseContext()
        
        class MockResponseContext:
            async def __aenter__(self):
                raise asyncio.TimeoutError("Request timed out")
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None
        
        with patch.object(aiohttp.ClientSession, 'post', MockPost()):
            with pytest.raises(asyncio.TimeoutError):
                await client.chat(messages)
    
    @pytest.mark.asyncio
    async def test_openai_client_connection_error(self):
        """Test OpenAI client handling connection errors."""
        config = {"api_key": "test-key", "model": "gpt-4"}
        client = OpenAIClient(config)
        messages = [Message(role=Role.USER, content="Hello")]
        
        # Create a proper mock that returns an async context manager
        class MockPost:
            def __call__(self, *args, **kwargs):
                return MockResponseContext()
        
        class MockResponseContext:
            async def __aenter__(self):
                raise aiohttp.ClientConnectionError("Connection failed")
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None
        
        with patch.object(aiohttp.ClientSession, 'post', MockPost()):
            with pytest.raises(aiohttp.ClientConnectionError):
                await client.chat(messages)
    
    @pytest.mark.asyncio
    async def test_openai_client_http_error_responses(self):
        """Test OpenAI client handling various HTTP error responses."""
        config = {"api_key": "test-key", "model": "gpt-4"}
        client = OpenAIClient(config)
        messages = [Message(role=Role.USER, content="Hello")]
        
        error_scenarios = [
            (400, "Bad Request", "Invalid request format"),
            (401, "Unauthorized", "Invalid API key"),
            (403, "Forbidden", "Access denied"),
            (404, "Not Found", "Model not found"),
            (429, "Too Many Requests", "Rate limit exceeded"),
            (500, "Internal Server Error", "Server error"),
            (502, "Bad Gateway", "Gateway error"),
            (503, "Service Unavailable", "Service temporarily unavailable")
        ]
        
        for status_code, status_text, error_message in error_scenarios:
            # Create a proper mock that returns an async context manager
            class MockPost:
                def __call__(self, *args, **kwargs):
                    return MockResponseContext()
            
            class MockResponseContext:
                async def __aenter__(self):
                    mock_response = AsyncMock()
                    mock_response.status = status_code
                    mock_response.text = AsyncMock(return_value=error_message)
                    return mock_response
                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return None
            
            with patch.object(aiohttp.ClientSession, 'post', MockPost()):
                with pytest.raises(Exception, match="OpenAI API error"):
                    await client.chat(messages)
    
    @pytest.mark.asyncio
    async def test_openai_client_malformed_response(self):
        """Test OpenAI client handling malformed API responses."""
        config = {"api_key": "test-key", "model": "gpt-4"}
        client = OpenAIClient(config)
        messages = [Message(role=Role.USER, content="Hello")]
        
        malformed_responses = [
            {},  # Empty response
            {"choices": []},  # No choices
            {"choices": [{}]},  # Choice without message
            {"choices": [{"message": {}}]},  # Message without content
            {"invalid": "structure"},  # Completely wrong structure
        ]
        
        for malformed_response in malformed_responses:
            # Create a proper mock that returns an async context manager
            class MockPost:
                def __call__(self, *args, **kwargs):
                    return MockResponseContext()
            
            class MockResponseContext:
                async def __aenter__(self):
                    mock_response = AsyncMock()
                    mock_response.status = 200
                    mock_response.json = AsyncMock(return_value=malformed_response)
                    return mock_response
                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    return None
            
            with patch.object(aiohttp.ClientSession, 'post', MockPost()):
                with pytest.raises((KeyError, IndexError)):
                    await client.chat(messages)
    
    @pytest.mark.asyncio
    async def test_openai_client_streaming_errors(self):
        """Test OpenAI client handling streaming errors."""
        config = {"api_key": "test-key", "model": "gpt-4"}
        client = OpenAIClient(config)
        messages = [Message(role=Role.USER, content="Hello")]
        
        # Create a proper mock that returns an async context manager
        class MockPost:
            def __call__(self, *args, **kwargs):
                return MockResponseContext()
        
        class MockResponseContext:
            async def __aenter__(self):
                mock_response = AsyncMock()
                mock_response.status = 200
                
                # Mock content that raises an exception during iteration
                async def failing_content():
                    yield b'data: {"choices": [{"delta": {"content": "Hello"}}]}\n\n'
                    raise aiohttp.ClientPayloadError("Stream interrupted")
                
                mock_response.content = failing_content()
                return mock_response
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                return None
        
        with patch.object(aiohttp.ClientSession, 'post', MockPost()):
            with pytest.raises(aiohttp.ClientPayloadError):
                async for chunk in client.chat_stream(messages):
                    pass


class TestConfigurationErrorHandling:
    """Test configuration error handling scenarios."""
    
    def test_openai_client_missing_api_key(self):
        """Test OpenAI client with missing API key."""
        configs = [
            {},
            {"model": "gpt-4"},
            {"api_key": None, "model": "gpt-4"},
            {"api_key": "", "model": "gpt-4"},
        ]
        
        for config in configs:
            with pytest.raises(ValueError, match="OpenAI API key is required"):
                OpenAIClient(config)
    
    def test_openai_client_invalid_configuration_values(self):
        """Test OpenAI client with invalid configuration values."""
        base_config = {"api_key": "test-key"}
        
        invalid_configs = [
            # Invalid temperature values
            {**base_config, "temperature": -0.1},
            {**base_config, "temperature": 2.1},
            {**base_config, "temperature": "invalid"},
            
            # Invalid max_tokens values
            {**base_config, "max_tokens": 0},
            {**base_config, "max_tokens": -100},
            {**base_config, "max_tokens": "invalid"},
            
            # Invalid model values
            {**base_config, "model": ""},
            {**base_config, "model": None},
            {**base_config, "model": 123},
            
            # Invalid base_url values
            {**base_config, "base_url": ""},
            {**base_config, "base_url": None},
            {**base_config, "base_url": 123},
        ]
        
        for config in invalid_configs:
            client = OpenAIClient(config)
            assert not client.validate_config()
    
    def test_factory_invalid_provider_handling(self):
        """Test factory handling of invalid providers."""
        invalid_configs = [
            {"provider": "nonexistent"},
            {"provider": ""},
            {"provider": None},
            {"provider": 123},
        ]
        
        for config in invalid_configs:
            with pytest.raises(ValueError, match="Unsupported AI provider"):
                AIClientFactory.create_client(config)
    
    def test_factory_register_invalid_client_classes(self):
        """Test factory registration with invalid client classes."""
        invalid_classes = [
            str,  # Built-in type
            dict,  # Built-in type
            object,  # Base object
            None,  # None value
        ]
        
        for invalid_class in invalid_classes:
            with pytest.raises(ValueError, match="Client class must inherit from AIClient"):
                AIClientFactory.register_provider("invalid", invalid_class)


class TestConversationErrorHandling:
    """Test conversation and persistence error handling."""
    
    def test_conversation_manager_invalid_storage_path(self):
        """Test conversation manager with invalid storage paths."""
        # Test with file instead of directory
        with tempfile.NamedTemporaryFile() as temp_file:
            file_path = Path(temp_file.name)
            
            # Should handle gracefully (might create new directory)
            manager = ConversationManager(file_path)
            assert isinstance(manager, ConversationManager)
    
    def test_conversation_manager_permission_errors(self):
        """Test conversation manager handling permission errors."""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_path = Path(temp_dir) / "restricted"
            storage_path.mkdir()
            
            # Make directory read-only (simulate permission error)
            import os
            try:
                os.chmod(storage_path, 0o444)
                
                manager = ConversationManager(storage_path)
                conversation = manager.create_conversation("Test")
                
                # This might fail on some systems, but should be handled gracefully
                try:
                    manager.save_all_conversations()
                except PermissionError:
                    # Expected on some systems
                    pass
                
            finally:
                # Restore permissions for cleanup
                os.chmod(storage_path, 0o755)
    
    def test_conversation_corrupted_json_handling(self):
        """Test conversation manager handling corrupted JSON files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_path = Path(temp_dir)
            
            # Create various corrupted files
            corrupted_files = [
                ("invalid.json", "{ invalid json"),
                ("empty.json", ""),
                ("partial.json", '{"id": "test", "title"'),
                ("wrong_type.json", '"just a string"'),
                ("array.json", '["array", "instead", "of", "object"]'),
                ("null.json", "null"),
            ]
            
            for filename, content in corrupted_files:
                (storage_path / filename).write_text(content)
            
            # Manager should handle all corrupted files gracefully
            manager = ConversationManager(storage_path)
            assert len(manager.conversations) == 0
            
            # Should still be able to create new conversations
            conversation = manager.create_conversation("Test")
            assert len(manager.conversations) == 1
    
    def test_conversation_large_content_handling(self):
        """Test conversation handling very large content."""
        conversation = Conversation("Large Content Test")
        
        # Test with very large message content
        large_content = "A" * 1000000  # 1MB of text
        message = conversation.add_user_message(large_content)
        
        assert message.content == large_content
        assert len(conversation.messages) == 1
        
        # Test serialization of large content
        data = conversation.to_dict()
        assert len(data["messages"][0]["content"]) == 1000000
        
        # Test deserialization
        restored = Conversation.from_dict(data)
        assert len(restored.messages[0].content) == 1000000
    
    def test_conversation_special_characters_handling(self):
        """Test conversation handling special characters and encodings."""
        conversation = Conversation("Special Characters Test")
        
        special_contents = [
            "Unicode: 🤖🚀💻🎉",
            "Chinese: 你好世界",
            "Arabic: مرحبا بالعالم",
            "Russian: Привет мир",
            "Japanese: こんにちは世界",
            "Control chars: \n\t\r\x00\x1f",
            "Null bytes: \x00\x00\x00",
            "High Unicode: 𝕌𝕟𝕚𝕔𝕠𝕕𝕖",
        ]
        
        for content in special_contents:
            message = conversation.add_user_message(content)
            assert message.content == content
        
        # Test serialization and deserialization
        data = conversation.to_dict()
        restored = Conversation.from_dict(data)
        
        for i, content in enumerate(special_contents):
            assert restored.messages[i].content == content
    
    def test_message_edge_cases(self):
        """Test message creation with edge cases."""
        # Test with invalid role
        with pytest.raises((ValueError, TypeError)):
            Message(role="invalid_role", content="test")
        
        # Test role type conversion
        message = Message(role=Role.USER, content="test")
        data = message.to_dict()
        assert data["role"] == "user"
        
        # Test from_dict with invalid role
        with pytest.raises(ValueError):
            Message.from_dict({"role": "invalid_role", "content": "test"})


class TestResourceExhaustionScenarios:
    """Test resource exhaustion and limits."""
    
    def test_conversation_manager_many_conversations(self):
        """Test conversation manager with many conversations."""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_path = Path(temp_dir)
            manager = ConversationManager(storage_path)
            
            # Create many conversations
            num_conversations = 1000
            for i in range(num_conversations):
                conversation = manager.create_conversation(f"Conversation {i}")
                conversation.add_user_message(f"Message {i}")
            
            assert len(manager.conversations) == num_conversations
            
            # Test listing (should handle large numbers)
            conversations = manager.list_conversations()
            assert len(conversations) == num_conversations
            
            # Test persistence
            manager.save_all_conversations()
            
            # Test loading
            manager2 = ConversationManager(storage_path)
            assert len(manager2.conversations) == num_conversations
    
    def test_conversation_many_messages(self):
        """Test conversation with many messages."""
        conversation = Conversation("Many Messages Test")
        
        # Add many messages
        num_messages = 10000
        for i in range(num_messages):
            if i % 2 == 0:
                conversation.add_user_message(f"User message {i}")
            else:
                conversation.add_assistant_message(f"Assistant message {i}")
        
        assert len(conversation.messages) == num_messages
        
        # Test getting last N messages with large conversation
        last_10 = conversation.get_last_n_messages(10)
        assert len(last_10) == 10
        assert last_10[-1].content == f"Assistant message {num_messages - 1}"
        
        # Test serialization (might be slow but should work)
        data = conversation.to_dict()
        assert len(data["messages"]) == num_messages
    
    @pytest.mark.asyncio
    async def test_concurrent_conversation_operations(self):
        """Test concurrent operations on conversations."""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_path = Path(temp_dir)
            manager = ConversationManager(storage_path)
            
            async def create_and_modify_conversation(i):
                conversation = manager.create_conversation(f"Concurrent {i}")
                for j in range(100):
                    conversation.add_user_message(f"Message {i}-{j}")
                return conversation
            
            # Run concurrent operations
            tasks = [create_and_modify_conversation(i) for i in range(10)]
            conversations = await asyncio.gather(*tasks)
            
            # Verify all conversations were created
            assert len(conversations) == 10
            for i, conv in enumerate(conversations):
                assert len(conv.messages) == 100


class TestRecoveryAndResilience:
    """Test recovery and resilience mechanisms."""
    
    def test_conversation_manager_partial_file_corruption(self):
        """Test recovery from partial file corruption."""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_path = Path(temp_dir)
            
            # Create some valid conversations
            manager = ConversationManager(storage_path)
            conv1 = manager.create_conversation("Valid 1")
            conv1.add_user_message("Hello 1")
            conv2 = manager.create_conversation("Valid 2")
            conv2.add_user_message("Hello 2")
            manager.save_all_conversations()
            
            # Corrupt one file
            files = list(storage_path.glob("*.json"))
            if files:
                files[0].write_text("{ corrupted content")
            
            # Create another valid file
            conv3_data = {
                "id": "valid-3",
                "title": "Valid 3",
                "messages": [{"role": "user", "content": "Hello 3"}],
                "metadata": {},
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            (storage_path / "valid-3.json").write_text(json.dumps(conv3_data))
            
            # New manager should load valid conversations and skip corrupted ones
            manager2 = ConversationManager(storage_path)
            valid_conversations = [conv for conv in manager2.conversations.values() 
                                 if conv.title.startswith("Valid")]
            
            # Should have at least the valid conversations
            assert len(valid_conversations) >= 2
    
    def test_conversation_manager_storage_recovery(self):
        """Test storage directory recovery."""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage_path = Path(temp_dir) / "conversations"
            
            # Storage directory doesn't exist initially
            assert not storage_path.exists()
            
            # Manager should create it
            manager = ConversationManager(storage_path)
            assert storage_path.exists()
            
            # Should be able to create conversations
            conversation = manager.create_conversation("Recovery Test")
            assert len(manager.conversations) == 1
    
    @pytest.mark.asyncio
    async def test_openai_client_retry_behavior(self):
        """Test OpenAI client behavior that could support retry mechanisms."""
        config = {"api_key": "test-key", "model": "gpt-4"}
        client = OpenAIClient(config)
        messages = [Message(role=Role.USER, content="Hello")]
        
        # Test that client properly raises exceptions that could be caught for retry
        with patch('aiohttp.ClientSession') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 429  # Rate limit
            mock_response.text.return_value = "Rate limit exceeded"
            
            mock_session.return_value.__aenter__.return_value.post.return_value.__aenter__.return_value = mock_response
            
            # Should raise exception that retry logic could catch
            with pytest.raises(Exception, match="OpenAI API error"):
                await client.chat(messages)
    
    def test_message_validation_recovery(self):
        """Test message validation and recovery from invalid data."""
        # Test invalid message data that might come from corrupted storage
        invalid_message_data = [
            {"role": "user"},  # Missing content
            {"content": "hello"},  # Missing role
            {"role": "invalid", "content": "hello"},  # Invalid role
            {},  # Empty
            None,  # None value
        ]
        
        valid_count = 0
        for data in invalid_message_data:
            try:
                if data is not None:
                    message = Message.from_dict(data)
                    valid_count += 1
            except (ValueError, TypeError, KeyError):
                # Expected for invalid data
                pass
        
        # Most should fail validation
        assert valid_count == 0
        
        # Test valid message still works
        valid_data = {"role": "user", "content": "hello"}
        message = Message.from_dict(valid_data)
        assert message.role == Role.USER
        assert message.content == "hello"