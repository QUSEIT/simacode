"""
Conversation and message history management.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from .base import Message, Role


class Conversation:
    """Represents a single conversation with message history."""
    
    def __init__(self, conversation_id: Optional[str] = None, 
                 title: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None):
        """Initialize a new conversation."""
        self.id = conversation_id or str(uuid.uuid4())
        self.title = title or f"Conversation {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        self.messages: List[Message] = []
        self.metadata = metadata or {}
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
    
    def add_message(self, role: Role, content: str, metadata: Optional[Dict[str, Any]] = None) -> Message:
        """Add a new message to the conversation."""
        message = Message(
            role=role,
            content=content,
            metadata=metadata
        )
        self.messages.append(message)
        self.updated_at = datetime.now()
        return message
    
    def add_system_message(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Message:
        """Add a system message."""
        return self.add_message(Role.SYSTEM, content, metadata)
    
    def add_user_message(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Message:
        """Add a user message."""
        return self.add_message(Role.USER, content, metadata)
    
    def add_assistant_message(self, content: str, metadata: Optional[Dict[str, Any]] = None) -> Message:
        """Add an assistant message."""
        return self.add_message(Role.ASSISTANT, content, metadata)
    
    def get_messages(self) -> List[Message]:
        """Get all messages in the conversation."""
        return self.messages.copy()
    
    def get_last_n_messages(self, n: int) -> List[Message]:
        """Get the last n messages."""
        if n <= 0:
            return []
        return self.messages[-n:] if len(self.messages) >= n else self.messages
    
    def clear_messages(self) -> None:
        """Clear all messages from the conversation."""
        self.messages.clear()
        self.updated_at = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert conversation to dictionary format."""
        return {
            "id": self.id,
            "title": self.title,
            "messages": [msg.to_dict() for msg in self.messages],
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Conversation":
        """Create conversation from dictionary."""
        conv = cls(
            conversation_id=data["id"],
            title=data["title"],
            metadata=data.get("metadata", {})
        )
        conv.messages = [Message.from_dict(msg_data) for msg_data in data.get("messages", [])]
        conv.created_at = datetime.fromisoformat(data["created_at"])
        conv.updated_at = datetime.fromisoformat(data["updated_at"])
        return conv


class ConversationManager:
    """Manages multiple conversations and persists them to disk."""
    
    def __init__(self, storage_dir: Path):
        """Initialize conversation manager."""
        self.storage_dir = storage_dir
        self.conversations: Dict[str, Conversation] = {}
        self.current_conversation: Optional[Conversation] = None
        
        # Ensure storage directory exists
        try:
            if self.storage_dir.is_file():
                # If it's a file, use its parent directory
                self.storage_dir = self.storage_dir.parent / f"{self.storage_dir.name}_conversations"
            self.storage_dir.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            # If we can't create the directory, use a temporary location
            import tempfile
            self.storage_dir = Path(tempfile.mkdtemp(prefix="simacode_conversations_"))
        
        # Load existing conversations
        self._load_conversations()
    
    def create_conversation(self, title: Optional[str] = None, 
                          metadata: Optional[Dict[str, Any]] = None) -> Conversation:
        """Create a new conversation."""
        conversation = Conversation(title=title, metadata=metadata)
        self.conversations[conversation.id] = conversation
        self.current_conversation = conversation
        self._save_conversation(conversation)
        return conversation
    
    def get_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Get conversation by ID."""
        return self.conversations.get(conversation_id)
    
    def list_conversations(self) -> List[Conversation]:
        """List all conversations sorted by updated time."""
        return sorted(
            self.conversations.values(),
            key=lambda x: x.updated_at,
            reverse=True
        )
    
    def set_current_conversation(self, conversation_id: str) -> bool:
        """Set the current conversation."""
        if conversation_id in self.conversations:
            self.current_conversation = self.conversations[conversation_id]
            return True
        return False
    
    def get_current_conversation(self) -> Optional[Conversation]:
        """Get the current conversation."""
        if self.current_conversation is None:
            # Create a new conversation if none exists
            self.current_conversation = self.create_conversation()
        return self.current_conversation
    
    def delete_conversation(self, conversation_id: str) -> bool:
        """Delete a conversation."""
        if conversation_id in self.conversations:
            # Remove from memory
            del self.conversations[conversation_id]
            
            # Remove from disk
            file_path = self._get_conversation_file_path(conversation_id)
            if file_path.exists():
                file_path.unlink()
            
            # Update current conversation if needed
            if self.current_conversation and self.current_conversation.id == conversation_id:
                conversations = list(self.conversations.values())
                self.current_conversation = conversations[0] if conversations else None
            
            return True
        return False
    
    def _get_conversation_file_path(self, conversation_id: str) -> Path:
        """Get the file path for a conversation."""
        return self.storage_dir / f"{conversation_id}.json"
    
    def _save_conversation(self, conversation: Conversation) -> None:
        """Save conversation to disk."""
        try:
            file_path = self._get_conversation_file_path(conversation.id)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(conversation.to_dict(), f, ensure_ascii=False, indent=2)
        except (OSError, PermissionError):
            # If we can't save, just skip (conversation remains in memory)
            pass
    
    def _load_conversations(self) -> None:
        """Load conversations from disk."""
        if not self.storage_dir.exists():
            return
        
        for file_path in self.storage_dir.glob("*.json"):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    conversation = Conversation.from_dict(data)
                    self.conversations[conversation.id] = conversation
            except (json.JSONDecodeError, KeyError, TypeError, OSError, ValueError):
                # Skip invalid conversation files
                continue
    
    def save_all_conversations(self) -> None:
        """Save all conversations to disk."""
        for conversation in self.conversations.values():
            self._save_conversation(conversation)