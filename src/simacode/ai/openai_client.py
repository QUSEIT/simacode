"""
OpenAI API client implementation.
"""

import asyncio
from typing import List, Dict, Any, AsyncIterator
import aiohttp
from .base import AIClient, AIResponse, Message


class OpenAIClient(AIClient):
    """OpenAI API client implementation."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize OpenAI client."""
        super().__init__(config)
        self.api_key = config.get("api_key")
        self.base_url = config.get("base_url", "https://api.openai.com/v1")
        self.model = config.get("model", "gpt-4")
        self.max_tokens = config.get("max_tokens", 4000)
        self.temperature = config.get("temperature", 0.1)
        self.timeout = config.get("timeout", 60)
        
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
    
    @property
    def provider_name(self) -> str:
        """Get the provider name."""
        return "openai"
    
    def validate_config(self) -> bool:
        """Validate OpenAI configuration."""
        if not self.api_key or not isinstance(self.api_key, str):
            return False
        
        if not self.base_url or not isinstance(self.base_url, str):
            return False
            
        if not isinstance(self.model, str) or not self.model.strip():
            return False
            
        if not isinstance(self.max_tokens, int) or self.max_tokens <= 0:
            return False
            
        if not isinstance(self.temperature, (int, float)) or not 0 <= self.temperature <= 2:
            return False
            
        return True
    
    async def chat(self, messages: List[Message]) -> AIResponse:
        """Send chat request to OpenAI API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature
        }
        
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        ) as session:
            async with session.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"OpenAI API error: {response.status} - {error_text}")
                
                data = await response.json()
                
                choice = data["choices"][0]
                return AIResponse(
                    content=choice["message"]["content"],
                    usage=data.get("usage"),
                    model=self.model,
                    finish_reason=choice.get("finish_reason"),
                    metadata={
                        "response_id": data.get("id"),
                        "created": data.get("created"),
                        "system_fingerprint": data.get("system_fingerprint")
                    }
                )
    
    async def chat_stream(self, messages: List[Message]) -> AsyncIterator[str]:
        """Send streaming chat request to OpenAI API."""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [msg.to_dict() for msg in messages],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": True
        }
        
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        ) as session:
            async with session.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"OpenAI API error: {response.status} - {error_text}")
                
                async for line in response.content:
                    line = line.decode('utf-8').strip()
                    if line.startswith('data: '):
                        data_str = line[6:]
                        
                        if data_str == '[DONE]':
                            break
                            
                        try:
                            import json
                            data = json.loads(data_str)
                            if "choices" in data and data["choices"]:
                                delta = data["choices"][0].get("delta", {})
                                if "content" in delta:
                                    yield delta["content"]
                        except json.JSONDecodeError:
                            continue