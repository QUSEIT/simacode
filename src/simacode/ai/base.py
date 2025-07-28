"""
Base interfaces for AI clients.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional, List, Dict, Any, AsyncIterator


class Role(str, Enum):
    """Message roles in a conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    """A single message in a conversation."""
    role: Role
    content: str
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        """Validate message fields after initialization."""
        if not isinstance(self.role, Role):
            if isinstance(self.role, str):
                try:
                    self.role = Role(self.role)
                except ValueError:
                    raise ValueError(f"Invalid role: {self.role}. Must be one of {list(Role)}")
            else:
                raise TypeError(f"Role must be a Role enum or string, got {type(self.role)}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary format."""
        result = {
            "role": self.role.value,
            "content": self.content
        }
        if self.metadata:
            result["metadata"] = self.metadata
        return result
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """Create message from dictionary."""
        return cls(
            role=Role(data["role"]),
            content=data["content"],
            metadata=data.get("metadata")
        )


@dataclass
class AIResponse:
    """Response from AI provider."""
    content: str
    usage: Optional[Dict[str, int]] = None
    model: Optional[str] = None
    finish_reason: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AIClient(ABC):
    """Abstract base class for AI clients."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize AI client with configuration."""
        self.config = config
    
    @abstractmethod
    async def chat(self, messages: List[Message]) -> AIResponse:
        """Send chat request and get response."""
        pass
    
    @abstractmethod
    async def chat_stream(self, messages: List[Message]) -> AsyncIterator[str]:
        """Send chat request and get streaming response."""
        pass
    
    @abstractmethod
    def validate_config(self) -> bool:
        """Validate client configuration."""
        pass
    
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Get the provider name."""
        pass