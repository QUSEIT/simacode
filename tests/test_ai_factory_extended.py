"""
Extended tests for AI client factory and provider management.

These tests focus on:
- Factory pattern implementation
- Multiple provider support
- Provider registration and discovery
- Configuration handling for different providers
- Extensibility and plugin architecture
"""

import pytest
from unittest.mock import AsyncMock
from typing import Dict, Any, List, AsyncIterator

from simacode.ai.base import AIClient, AIResponse, Message, Role
from simacode.ai.factory import AIClientFactory
from simacode.ai.openai_client import OpenAIClient


class MockAIClient(AIClient):
    """Mock AI client for testing factory pattern."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key")  # No default, should be None if missing
        self.model = config.get("model")  # No default, should be None if missing  
        self.provider = config.get("provider", "mock")
        self._should_fail = config.get("should_fail", False)
    
    @property
    def provider_name(self) -> str:
        return self.provider
    
    async def chat(self, messages: List[Message]) -> AIResponse:
        if self._should_fail:
            raise Exception("Mock client configured to fail")
        
        return AIResponse(
            content=f"Mock response from {self.model}",
            model=self.model,
            usage={"prompt_tokens": 10, "completion_tokens": 5}
        )
    
    async def chat_stream(self, messages: List[Message]) -> AsyncIterator[str]:
        if self._should_fail:
            raise Exception("Mock client configured to fail")
        
        response_chunks = ["Mock ", "streaming ", "response"]
        for chunk in response_chunks:
            yield chunk
    
    def validate_config(self) -> bool:
        return bool(self.api_key and self.model)


class AnthropicMockClient(AIClient):
    """Mock Anthropic client for testing multiple providers."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config.get("api_key")
        self.model = config.get("model")  # No default, should be None if missing
        self.max_tokens = config.get("max_tokens", 4000)
    
    @property
    def provider_name(self) -> str:
        return "anthropic"
    
    async def chat(self, messages: List[Message]) -> AIResponse:
        if not self.api_key:
            raise ValueError("Anthropic API key required")
        
        return AIResponse(
            content="Hello from Claude!",
            model=self.model,
            usage={"input_tokens": 15, "output_tokens": 8}
        )
    
    async def chat_stream(self, messages: List[Message]) -> AsyncIterator[str]:
        chunks = ["Hello ", "from ", "Claude!"]
        for chunk in chunks:
            yield chunk
    
    def validate_config(self) -> bool:
        return bool(self.api_key and self.model)


class LocalMockClient(AIClient):
    """Mock local AI client for testing."""
    
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.model_path = config.get("model_path")  # No default, should be None if missing
        self.context_length = config.get("context_length", 2048)
    
    @property
    def provider_name(self) -> str:
        return "local"
    
    async def chat(self, messages: List[Message]) -> AIResponse:
        return AIResponse(
            content="Local model response",
            model=self.model_path,
            metadata={"context_length": self.context_length}
        )
    
    async def chat_stream(self, messages: List[Message]) -> AsyncIterator[str]:
        chunks = ["Local ", "model ", "streaming"]
        for chunk in chunks:
            yield chunk
    
    def validate_config(self) -> bool:
        return bool(self.model_path)


class TestAIClientFactory:
    """Test AI client factory functionality."""
    
    def setup_method(self):
        """Set up test environment."""
        # Store original providers to restore later
        self._original_providers = AIClientFactory._providers.copy()
    
    def teardown_method(self):
        """Clean up test environment."""
        # Restore original providers
        AIClientFactory._providers = self._original_providers
    
    def test_factory_create_openai_client(self):
        """Test creating OpenAI client through factory."""
        config = {
            "provider": "openai",
            "api_key": "test-key",
            "model": "gpt-4",
            "temperature": 0.1
        }
        
        client = AIClientFactory.create_client(config)
        assert isinstance(client, OpenAIClient)
        assert client.provider_name == "openai"
        assert client.api_key == "test-key"
        assert client.model == "gpt-4"
        assert client.temperature == 0.1
    
    def test_factory_default_provider(self):
        """Test factory with default provider (should be OpenAI)."""
        config = {
            "api_key": "test-key",
            "model": "gpt-3.5-turbo"
        }
        
        client = AIClientFactory.create_client(config)
        assert isinstance(client, OpenAIClient)
        assert client.provider_name == "openai"
    
    def test_factory_register_new_provider(self):
        """Test registering a new provider."""
        # Register mock provider
        AIClientFactory.register_provider("mock", MockAIClient)
        
        # Verify it's in the list
        providers = AIClientFactory.list_providers()
        assert "mock" in providers
        
        # Test creating client with new provider
        config = {
            "provider": "mock",
            "api_key": "mock-key",
            "model": "mock-model-v1"
        }
        
        client = AIClientFactory.create_client(config)
        assert isinstance(client, MockAIClient)
        assert client.provider_name == "mock"
        assert client.api_key == "mock-key"
        assert client.model == "mock-model-v1"
    
    def test_factory_register_multiple_providers(self):
        """Test registering multiple providers."""
        # Register multiple providers
        AIClientFactory.register_provider("anthropic", AnthropicMockClient)
        AIClientFactory.register_provider("local", LocalMockClient)
        
        providers = AIClientFactory.list_providers()
        assert "anthropic" in providers
        assert "local" in providers
        assert "openai" in providers  # Original provider should still be there
        
        # Test creating clients for each provider
        anthropic_config = {
            "provider": "anthropic",
            "api_key": "claude-key",
            "model": "claude-3-sonnet"
        }
        
        local_config = {
            "provider": "local",
            "model_path": "/path/to/llama",
            "context_length": 4096
        }
        
        anthropic_client = AIClientFactory.create_client(anthropic_config)
        local_client = AIClientFactory.create_client(local_config)
        
        assert isinstance(anthropic_client, AnthropicMockClient)
        assert isinstance(local_client, LocalMockClient)
        assert anthropic_client.provider_name == "anthropic"
        assert local_client.provider_name == "local"
    
    def test_factory_invalid_provider(self):
        """Test factory with invalid provider."""
        config = {"provider": "nonexistent"}
        
        with pytest.raises(ValueError, match="Unsupported AI provider"):
            AIClientFactory.create_client(config)
    
    def test_factory_register_invalid_client_class(self):
        """Test registering invalid client class."""
        class InvalidClient:
            pass
        
        with pytest.raises(ValueError, match="Client class must inherit from AIClient"):
            AIClientFactory.register_provider("invalid", InvalidClient)
    
    def test_factory_provider_configuration_isolation(self):
        """Test that provider configurations are isolated."""
        AIClientFactory.register_provider("mock1", MockAIClient)
        AIClientFactory.register_provider("mock2", MockAIClient)
        
        config1 = {
            "provider": "mock1",
            "api_key": "key1",
            "model": "model1"
        }
        
        config2 = {
            "provider": "mock2",
            "api_key": "key2",
            "model": "model2"
        }
        
        client1 = AIClientFactory.create_client(config1)
        client2 = AIClientFactory.create_client(config2)
        
        # Verify isolation
        assert client1.api_key == "key1"
        assert client2.api_key == "key2"
        assert client1.model == "model1"
        assert client2.model == "model2"
        assert client1.provider == "mock1"
        assert client2.provider == "mock2"


class TestProviderFunctionality:
    """Test functionality of different AI providers."""
    
    def setup_method(self):
        """Set up test environment."""
        self._original_providers = AIClientFactory._providers.copy()
        AIClientFactory.register_provider("mock", MockAIClient)
        AIClientFactory.register_provider("anthropic", AnthropicMockClient)
        AIClientFactory.register_provider("local", LocalMockClient)
    
    def teardown_method(self):
        """Clean up test environment."""
        AIClientFactory._providers = self._original_providers
    
    @pytest.mark.asyncio
    async def test_mock_provider_functionality(self):
        """Test mock provider functionality."""
        config = {
            "provider": "mock",
            "api_key": "test-key",
            "model": "mock-gpt"
        }
        
        client = AIClientFactory.create_client(config)
        assert client.validate_config()
        
        # Test chat
        messages = [Message(role=Role.USER, content="Hello")]
        response = await client.chat(messages)
        
        assert response.content == "Mock response from mock-gpt"
        assert response.model == "mock-gpt"
        assert response.usage["prompt_tokens"] == 10
        
        # Test streaming
        chunks = []
        async for chunk in client.chat_stream(messages):
            chunks.append(chunk)
        
        assert chunks == ["Mock ", "streaming ", "response"]
    
    @pytest.mark.asyncio
    async def test_anthropic_provider_functionality(self):
        """Test Anthropic provider functionality."""
        config = {
            "provider": "anthropic",
            "api_key": "claude-key",
            "model": "claude-3-sonnet",
            "max_tokens": 8000
        }
        
        client = AIClientFactory.create_client(config)
        assert client.validate_config()
        assert client.max_tokens == 8000
        
        # Test chat
        messages = [Message(role=Role.USER, content="Hello Claude")]
        response = await client.chat(messages)
        
        assert response.content == "Hello from Claude!"
        assert response.model == "claude-3-sonnet"
        assert "input_tokens" in response.usage
        
        # Test streaming
        chunks = []
        async for chunk in client.chat_stream(messages):
            chunks.append(chunk)
        
        assert chunks == ["Hello ", "from ", "Claude!"]
    
    @pytest.mark.asyncio
    async def test_local_provider_functionality(self):
        """Test local provider functionality."""
        config = {
            "provider": "local",
            "model_path": "/path/to/llama-7b",
            "context_length": 8192
        }
        
        client = AIClientFactory.create_client(config)
        assert client.validate_config()
        assert client.context_length == 8192
        
        # Test chat
        messages = [Message(role=Role.USER, content="Hello local model")]
        response = await client.chat(messages)
        
        assert response.content == "Local model response"
        assert response.model == "/path/to/llama-7b"
        assert response.metadata["context_length"] == 8192
        
        # Test streaming
        chunks = []
        async for chunk in client.chat_stream(messages):
            chunks.append(chunk)
        
        assert chunks == ["Local ", "model ", "streaming"]
    
    @pytest.mark.asyncio
    async def test_provider_error_handling(self):
        """Test error handling in different providers."""
        # Test mock provider with failure configuration
        failing_config = {
            "provider": "mock",
            "api_key": "test-key",
            "model": "mock-model",
            "should_fail": True
        }
        
        client = AIClientFactory.create_client(failing_config)
        messages = [Message(role=Role.USER, content="Hello")]
        
        with pytest.raises(Exception, match="Mock client configured to fail"):
            await client.chat(messages)
        
        with pytest.raises(Exception, match="Mock client configured to fail"):
            async for chunk in client.chat_stream(messages):
                pass
        
        # Test Anthropic provider without API key
        no_key_config = {
            "provider": "anthropic",
            "model": "claude-3"
        }
        
        client = AIClientFactory.create_client(no_key_config)
        assert not client.validate_config()
        
        with pytest.raises(ValueError, match="Anthropic API key required"):
            await client.chat(messages)
    
    def test_provider_configuration_validation(self):
        """Test configuration validation for different providers."""
        # Valid configurations
        valid_configs = [
            {
                "provider": "mock",
                "api_key": "key",
                "model": "model"
            },
            {
                "provider": "anthropic",
                "api_key": "claude-key",
                "model": "claude-3"
            },
            {
                "provider": "local",
                "model_path": "/path/to/model"
            }
        ]
        
        for config in valid_configs:
            client = AIClientFactory.create_client(config)
            assert client.validate_config(), f"Config should be valid: {config}"
        
        # Invalid configurations
        invalid_configs = [
            {
                "provider": "mock",
                "model": "model"  # Missing api_key
            },
            {
                "provider": "anthropic",
                "api_key": "key"  # Missing model
            },
            {
                "provider": "local"  # Missing model_path
            }
        ]
        
        for config in invalid_configs:
            client = AIClientFactory.create_client(config)
            assert not client.validate_config(), f"Config should be invalid: {config}"


class TestFactoryExtensibility:
    """Test factory extensibility and plugin architecture."""
    
    def setup_method(self):
        """Set up test environment."""
        self._original_providers = AIClientFactory._providers.copy()
    
    def teardown_method(self):
        """Clean up test environment."""
        AIClientFactory._providers = self._original_providers
    
    def test_dynamic_provider_registration(self):
        """Test dynamic provider registration at runtime."""
        # Initially only OpenAI provider should exist
        initial_providers = AIClientFactory.list_providers()
        assert "openai" in initial_providers
        assert "custom" not in initial_providers
        
        # Register custom provider
        class CustomClient(AIClient):
            def __init__(self, config):
                super().__init__(config)
                self.custom_param = config.get("custom_param", "default")
            
            @property
            def provider_name(self):
                return "custom"
            
            async def chat(self, messages):
                return AIResponse(content="Custom response")
            
            async def chat_stream(self, messages):
                yield "Custom stream"
            
            def validate_config(self):
                return True
        
        AIClientFactory.register_provider("custom", CustomClient)
        
        # Verify registration
        updated_providers = AIClientFactory.list_providers()
        assert "custom" in updated_providers
        
        # Test using the custom provider
        config = {
            "provider": "custom",
            "custom_param": "test_value"
        }
        
        client = AIClientFactory.create_client(config)
        assert isinstance(client, CustomClient)
        assert client.custom_param == "test_value"
    
    def test_provider_override(self):
        """Test overriding existing providers."""
        # Create custom OpenAI implementation
        class CustomOpenAIClient(AIClient):
            def __init__(self, config):
                super().__init__(config)
                self.custom_feature = True
            
            @property
            def provider_name(self):
                return "openai"
            
            async def chat(self, messages):
                return AIResponse(content="Custom OpenAI response")
            
            async def chat_stream(self, messages):
                yield "Custom OpenAI stream"
            
            def validate_config(self):
                return True
        
        # Override the existing OpenAI provider
        AIClientFactory.register_provider("openai", CustomOpenAIClient)
        
        # Create client - should use custom implementation
        config = {"provider": "openai", "api_key": "test"}
        client = AIClientFactory.create_client(config)
        
        assert isinstance(client, CustomOpenAIClient)
        assert hasattr(client, 'custom_feature')
        assert client.custom_feature is True
    
    def test_provider_plugin_pattern(self):
        """Test provider as plugin pattern."""
        # Simulate loading providers from plugins
        plugin_providers = [
            ("huggingface", MockAIClient),
            ("cohere", MockAIClient),
            ("palm", MockAIClient)
        ]
        
        # Register all plugin providers
        for name, client_class in plugin_providers:
            AIClientFactory.register_provider(name, client_class)
        
        # Verify all providers are available
        providers = AIClientFactory.list_providers()
        for name, _ in plugin_providers:
            assert name in providers
        
        # Test creating clients for each plugin provider
        for name, _ in plugin_providers:
            config = {
                "provider": name,
                "api_key": f"{name}-key",
                "model": f"{name}-model"
            }
            
            client = AIClientFactory.create_client(config)
            assert client.provider_name == name
    
    def test_provider_capability_detection(self):
        """Test detecting provider capabilities."""
        # Register providers with different capabilities
        class StreamingOnlyClient(AIClient):
            @property
            def provider_name(self):
                return "streaming_only"
            
            async def chat(self, messages):
                raise NotImplementedError("Only streaming supported")
            
            async def chat_stream(self, messages):
                yield "Streaming only"
            
            def validate_config(self):
                return True
        
        class BasicClient(AIClient):
            @property
            def provider_name(self):
                return "basic"
            
            async def chat(self, messages):
                return AIResponse(content="Basic response")
            
            async def chat_stream(self, messages):
                raise NotImplementedError("Streaming not supported")
            
            def validate_config(self):
                return True
        
        AIClientFactory.register_provider("streaming_only", StreamingOnlyClient)
        AIClientFactory.register_provider("basic", BasicClient)
        
        # Test capability detection (would be implemented in real usage)
        streaming_client = AIClientFactory.create_client({"provider": "streaming_only"})
        basic_client = AIClientFactory.create_client({"provider": "basic"})
        
        # In real implementation, you might have methods to check capabilities
        assert streaming_client.provider_name == "streaming_only"
        assert basic_client.provider_name == "basic"