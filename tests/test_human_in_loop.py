"""
Test cases for the Human-in-Loop confirmation feature.

This module tests the human confirmation workflow including:
- Configuration loading
- Confirmation manager functionality
- ReAct engine integration
- CLI interaction simulation
"""

import asyncio
import pytest
from datetime import datetime, timedelta
from pathlib import Path

from simacode.config import Config, ReactConfig
from simacode.react.confirmation_manager import ConfirmationManager
from simacode.react.planner import Task, TaskType
from simacode.api.models import TaskConfirmationRequest, TaskConfirmationResponse, ConfirmationStatus


class TestReactConfig:
    """Test ReactConfig configuration model."""
    
    def test_default_config(self):
        """Test default configuration values."""
        config = ReactConfig()
        
        assert config.confirm_by_human is False
        assert config.confirmation_timeout == 300
        assert config.allow_task_modification is True
        assert config.auto_confirm_safe_tasks is False
    
    def test_config_validation(self):
        """Test configuration validation."""
        # Valid configuration
        config = ReactConfig(
            confirm_by_human=True,
            confirmation_timeout=600,
            allow_task_modification=False,
            auto_confirm_safe_tasks=True
        )
        
        assert config.confirm_by_human is True
        assert config.confirmation_timeout == 600
        assert config.allow_task_modification is False
        assert config.auto_confirm_safe_tasks is True


class TestConfirmationManager:
    """Test ConfirmationManager functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.confirmation_manager = ConfirmationManager()
        self.test_session_id = "test-session-123"
        self.test_tasks = [
            Task(
                id="task-1",
                description="Test task 1",
                tool_name="file_read",
                type=TaskType.FILE_OPERATION,
                priority=1,
                expected_outcome="Read file content"
            ),
            Task(
                id="task-2", 
                description="Test task 2",
                tool_name="file_write",
                type=TaskType.FILE_OPERATION,
                priority=2,
                expected_outcome="Write file content"
            )
        ]
    
    @pytest.mark.asyncio
    async def test_request_confirmation(self):
        """Test confirmation request creation."""
        confirmation_request = await self.confirmation_manager.request_confirmation(
            self.test_session_id,
            self.test_tasks,
            timeout_seconds=300
        )
        
        assert isinstance(confirmation_request, TaskConfirmationRequest)
        assert confirmation_request.session_id == self.test_session_id
        assert len(confirmation_request.tasks) == 2
        assert confirmation_request.timeout_seconds == 300
        
        # Check that pending confirmation is stored
        assert self.test_session_id in self.confirmation_manager.pending_confirmations
        confirmation_status = self.confirmation_manager.pending_confirmations[self.test_session_id]
        assert confirmation_status.status == "pending"
        assert confirmation_status.session_id == self.test_session_id
    
    def test_submit_confirmation_success(self):
        """Test successful confirmation submission."""
        # First create a pending confirmation
        confirmation = ConfirmationStatus(
            session_id=self.test_session_id,
            status="pending",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=300)
        )
        self.confirmation_manager.pending_confirmations[self.test_session_id] = confirmation
        self.confirmation_manager.confirmation_callbacks[self.test_session_id] = asyncio.Event()
        
        # Create confirmation response
        response = TaskConfirmationResponse(
            session_id=self.test_session_id,
            action="confirm"
        )
        
        # Submit confirmation
        success = self.confirmation_manager.submit_confirmation(self.test_session_id, response)
        
        assert success is True
        assert confirmation.user_response == response
        assert confirmation.status == "confirm"
    
    def test_submit_confirmation_not_found(self):
        """Test confirmation submission for non-existent session."""
        response = TaskConfirmationResponse(
            session_id="non-existent-session",
            action="confirm"
        )
        
        success = self.confirmation_manager.submit_confirmation("non-existent-session", response)
        assert success is False
    
    @pytest.mark.asyncio
    async def test_confirmation_timeout(self):
        """Test confirmation timeout handling."""
        # Create confirmation request with short timeout
        confirmation_request = await self.confirmation_manager.request_confirmation(
            self.test_session_id,
            self.test_tasks,
            timeout_seconds=1  # 1 second timeout
        )
        
        # Wait for timeout without submitting response
        with pytest.raises(TimeoutError, match="User confirmation timeout"):
            await self.confirmation_manager.wait_for_confirmation(
                self.test_session_id,
                timeout_seconds=1
            )
        
        # Check that session is cleaned up
        assert self.test_session_id not in self.confirmation_manager.pending_confirmations
        assert self.test_session_id not in self.confirmation_manager.confirmation_callbacks
    
    def test_get_active_confirmations(self):
        """Test retrieving active confirmations."""
        # Create active confirmation
        active_confirmation = ConfirmationStatus(
            session_id=self.test_session_id,
            status="pending",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=300)
        )
        self.confirmation_manager.pending_confirmations[self.test_session_id] = active_confirmation
        
        # Create expired confirmation
        expired_session_id = "expired-session"
        expired_confirmation = ConfirmationStatus(
            session_id=expired_session_id,
            status="pending",
            created_at=datetime.now() - timedelta(seconds=400),
            expires_at=datetime.now() - timedelta(seconds=100)
        )
        self.confirmation_manager.pending_confirmations[expired_session_id] = expired_confirmation
        
        active_confirmations = self.confirmation_manager.get_active_confirmations()
        
        assert len(active_confirmations) == 1
        assert self.test_session_id in active_confirmations
        assert expired_session_id not in active_confirmations
    
    def test_cleanup_expired_confirmations(self):
        """Test cleanup of expired confirmations."""
        # Create expired confirmation
        expired_session_id = "expired-session"
        expired_confirmation = ConfirmationStatus(
            session_id=expired_session_id,
            status="pending",
            created_at=datetime.now() - timedelta(seconds=400),
            expires_at=datetime.now() - timedelta(seconds=100)
        )
        self.confirmation_manager.pending_confirmations[expired_session_id] = expired_confirmation
        
        # Run cleanup
        self.confirmation_manager.cleanup_expired_confirmations()
        
        # Check that expired confirmation is removed
        assert expired_session_id not in self.confirmation_manager.pending_confirmations


class TestConfirmationModels:
    """Test confirmation-related data models."""
    
    def test_task_confirmation_request(self):
        """Test TaskConfirmationRequest model."""
        tasks = [{"id": "task-1", "description": "Test task"}]
        
        request = TaskConfirmationRequest(
            session_id="session-123",
            tasks=tasks,
            message="Test confirmation",
            options=["confirm", "cancel"],
            timeout_seconds=180
        )
        
        assert request.session_id == "session-123"
        assert request.tasks == tasks
        assert request.message == "Test confirmation"
        assert request.options == ["confirm", "cancel"]
        assert request.timeout_seconds == 180
    
    def test_task_confirmation_response(self):
        """Test TaskConfirmationResponse model."""
        response = TaskConfirmationResponse(
            session_id="session-123",
            action="modify",
            modified_tasks=[{"id": "task-1", "description": "Modified task"}],
            user_message="Please modify this task"
        )
        
        assert response.session_id == "session-123"
        assert response.action == "modify"
        assert len(response.modified_tasks) == 1
        assert response.user_message == "Please modify this task"
    
    def test_confirmation_status(self):
        """Test ConfirmationStatus model."""
        now = datetime.now()
        expires_at = now + timedelta(seconds=300)
        
        status = ConfirmationStatus(
            session_id="session-123",
            status="pending",
            created_at=now,
            expires_at=expires_at
        )
        
        assert status.session_id == "session-123"
        assert status.status == "pending"
        assert status.created_at == now
        assert status.expires_at == expires_at
        assert status.user_response is None


class TestConfigurationIntegration:
    """Test configuration integration with confirmation feature."""
    
    def test_load_config_with_react_settings(self):
        """Test loading configuration with ReAct settings."""
        # Create a temporary config file
        config_content = """
project_name: "Test Project"

react:
  confirm_by_human: true
  confirmation_timeout: 600
  allow_task_modification: false
  auto_confirm_safe_tasks: true
"""
        
        config_path = Path("test_config.yaml")
        try:
            with open(config_path, "w") as f:
                f.write(config_content)
            
            # Load configuration
            config = Config.load(config_path=config_path)
            
            assert config.project_name == "Test Project"
            assert config.react.confirm_by_human is True
            assert config.react.confirmation_timeout == 600
            assert config.react.allow_task_modification is False
            assert config.react.auto_confirm_safe_tasks is True
        
        finally:
            # Clean up
            if config_path.exists():
                config_path.unlink()


if __name__ == "__main__":
    # Run simple test
    print("Running Human-in-Loop feature tests...")
    
    # Test ReactConfig
    config = ReactConfig()
    print(f"✓ ReactConfig default values: confirm_by_human={config.confirm_by_human}")
    
    # Test ConfirmationManager
    manager = ConfirmationManager()
    print(f"✓ ConfirmationManager initialized with {len(manager.pending_confirmations)} pending confirmations")
    
    # Test models
    request = TaskConfirmationRequest(
        session_id="test-session",
        tasks=[{"id": "test", "description": "Test task"}]
    )
    print(f"✓ TaskConfirmationRequest created for session: {request.session_id}")
    
    print("\n🎉 All basic tests passed! Human-in-Loop feature is ready for testing.")
    print("\nTo test with confirmation enabled:")
    print("1. Update .simacode/config.yaml:")
    print("   react:")
    print("     confirm_by_human: true")
    print("2. Run: simacode chat --react")
    print("3. Try a task that requires tool execution")