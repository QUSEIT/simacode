"""
AI client factory for creating appropriate AI clients based on configuration.
"""

from typing import Dict, Any
from .base import AIClient
from .openai_client import OpenAIClient


class AIClientFactory:
    """Factory for creating AI clients."""
    
    _providers = {
        "openai": OpenAIClient,
        "deepseek": OpenAIClient,
    }
    
    @classmethod
    def create_client(cls, config: Dict[str, Any]) -> AIClient:
        """Create an AI client based on configuration."""
        provider = config.get("provider", "openai")
        
        if provider not in cls._providers:
            raise ValueError(f"Unsupported AI provider: {provider}")
        
        client_class = cls._providers[provider]
        client_config = config.copy()
        
        return client_class(client_config)
    
    @classmethod
    def register_provider(cls, name: str, client_class: type) -> None:
        """Register a new AI provider."""
        if not isinstance(client_class, type) or not issubclass(client_class, AIClient):
            raise ValueError("Client class must inherit from AIClient")
        
        cls._providers[name] = client_class
    
    @classmethod
    def list_providers(cls) -> list:
        """List available providers."""
        return list(cls._providers.keys())
