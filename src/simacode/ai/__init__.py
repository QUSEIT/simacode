"""
AI integration module for SimaCode.

This module provides the core AI functionality including:
- AI client interfaces and implementations
- Message and conversation management
- Streaming response handling
"""

from .base import AIClient, AIResponse, Message, Role
from .openai_client import OpenAIClient
from .conversation import Conversation, ConversationManager

__all__ = [
    "AIClient",
    "AIResponse", 
    "Message",
    "Role",
    "OpenAIClient",
    "Conversation",
    "ConversationManager",
]