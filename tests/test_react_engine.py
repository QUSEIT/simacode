"""
Tests for ReAct Engine Components

This module contains comprehensive tests for the ReAct engine,
including unit tests and integration tests.
"""

import asyncio
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from simacode.react.engine import ReActEngine, ReActSession, ReActState, ExecutionMode
from simacode.react.planner import TaskPlanner, Task, TaskType, TaskStatus, PlanningContext
from simacode.react.evaluator import ResultEvaluator, EvaluationResult, EvaluationOutcome, ConfidenceLevel
from simacode.react.exceptions import ReActError, PlanningError, ExecutionError
from simacode.ai.conversation import Message
from simacode.tools.base import ToolResult, ToolResultType


@pytest.fixture
def mock_ai_client():
    """Create a mock AI client for testing."""
    client = AsyncMock()
    client.chat = AsyncMock()
    return client


@pytest.fixture
def sample_planning_response():
    """Sample AI response for task planning."""
    return '''
    [
        {
            "type": "file_operation",
            "description": "Read the contents of test.txt",
            "tool_name": "file_read",
            "tool_input": {"file_path": "test.txt"},
            "expected_outcome": "File contents retrieved successfully",
            "dependencies": [],
            "priority": 1
        },
        {
            "type": "command_execution", 
            "description": "List directory contents",
            "tool_name": "bash",
            "tool_input": {"command": "ls -la"},
            "expected_outcome": "Directory listing displayed",
            "dependencies": [],
            "priority": 2
        }
    ]
    '''


@pytest.fixture
def sample_evaluation_response():
    """Sample AI response for result evaluation."""
    return '''
    {
        "outcome": "success",
        "confidence": "high",
        "success_score": 0.95,
        "reasoning": "Task completed successfully with expected output",
        "evidence": ["Tool executed without errors", "Output matches expectations"],
        "recommendations": ["Continue to next task"],
        "next_actions": ["Proceed with execution"]
    }
    '''


class TestTaskPlanner:
    """Test cases for TaskPlanner."""
    
    @pytest.mark.asyncio
    async def test_plan_tasks_success(self, mock_ai_client, sample_planning_response):
        """Test successful task planning."""
        # Setup
        mock_ai_client.chat.return_value = MagicMock(content=sample_planning_response)
        planner = TaskPlanner(mock_ai_client)
        
        context = PlanningContext(
            user_input="Read test.txt and list the current directory",
            available_tools=["file_read", "bash"]
        )
        
        # Execute
        with patch.object(planner.tool_registry, 'list_tools', return_value=["file_read", "bash"]):
            with patch.object(planner.tool_registry, 'get_tool') as mock_get_tool:
                # Mock tool validation
                mock_tool = AsyncMock()
                mock_tool.validate_input = AsyncMock()
                mock_get_tool.return_value = mock_tool
                
                tasks = await planner.plan_tasks(context)
        
        # Verify
        assert len(tasks) == 2
        assert tasks[0].type == TaskType.FILE_OPERATION
        assert tasks[0].tool_name == "file_read"
        assert tasks[0].tool_input == {"file_path": "test.txt"}
        assert tasks[1].type == TaskType.COMMAND_EXECUTION
        assert tasks[1].tool_name == "bash"
    
    @pytest.mark.asyncio
    async def test_plan_tasks_invalid_json(self, mock_ai_client):
        """Test planning with invalid JSON response."""
        # Setup
        mock_ai_client.chat.return_value = MagicMock(content="Invalid JSON response")
        planner = TaskPlanner(mock_ai_client)
        
        context = PlanningContext(user_input="Test input")
        
        # Execute & Verify
        with pytest.raises(PlanningError):
            await planner.plan_tasks(context)
    
    @pytest.mark.asyncio
    async def test_replan_task(self, mock_ai_client, sample_planning_response):
        """Test task replanning after failure."""
        # Setup
        mock_ai_client.chat.return_value = MagicMock(content=sample_planning_response)
        planner = TaskPlanner(mock_ai_client)
        
        failed_task = Task(
            type=TaskType.FILE_OPERATION,
            description="Read file",
            tool_name="file_read",
            tool_input={"file_path": "nonexistent.txt"}
        )
        
        error_info = {"error": "File not found"}
        context = PlanningContext(user_input="Read file")
        
        # Execute
        with patch.object(planner.tool_registry, 'list_tools', return_value=["file_read", "bash"]):
            with patch.object(planner.tool_registry, 'get_tool') as mock_get_tool:
                mock_tool = AsyncMock()
                mock_tool.validate_input = AsyncMock()
                mock_get_tool.return_value = mock_tool
                
                alternative_tasks = await planner.replan_task(failed_task, error_info, context)
        
        # Verify
        assert len(alternative_tasks) >= 1
        assert all(isinstance(task, Task) for task in alternative_tasks)


class TestResultEvaluator:
    """Test cases for ResultEvaluator."""
    
    @pytest.mark.asyncio
    async def test_rule_based_evaluation_success(self, mock_ai_client):
        """Test rule-based evaluation for successful task."""
        # Setup
        evaluator = ResultEvaluator(mock_ai_client)
        task = Task(
            description="Test task",
            expected_outcome="Success expected"
        )
        
        tool_results = [
            ToolResult(type=ToolResultType.SUCCESS, content="Task completed successfully")
        ]
        
        # Execute
        result = await evaluator.evaluate_task_result(task, tool_results)
        
        # Verify
        assert result.outcome == EvaluationOutcome.SUCCESS
        assert result.confidence == ConfidenceLevel.HIGH
        assert result.success_score == 1.0
    
    @pytest.mark.asyncio
    async def test_rule_based_evaluation_failure(self, mock_ai_client):
        """Test rule-based evaluation for failed task."""
        # Setup
        evaluator = ResultEvaluator(mock_ai_client)
        task = Task(description="Test task")
        
        tool_results = [
            ToolResult(type=ToolResultType.ERROR, content="Task failed with error")
        ]
        
        # Execute
        result = await evaluator.evaluate_task_result(task, tool_results)
        
        # Verify
        assert result.outcome == EvaluationOutcome.FAILURE
        assert result.confidence == ConfidenceLevel.HIGH
        assert result.success_score == 0.0
    
    @pytest.mark.asyncio
    async def test_ai_based_evaluation(self, mock_ai_client, sample_evaluation_response):
        """Test AI-based evaluation for complex cases."""
        # Setup
        mock_ai_client.chat.return_value = MagicMock(content=sample_evaluation_response)
        evaluator = ResultEvaluator(mock_ai_client)
        
        task = Task(description="Complex task")
        tool_results = [
            ToolResult(type=ToolResultType.OUTPUT, content="Some output")
        ]
        
        # Execute
        result = await evaluator.evaluate_task_result(task, tool_results)
        
        # Verify
        assert result.outcome == EvaluationOutcome.SUCCESS
        assert result.confidence == ConfidenceLevel.HIGH
        # Score should be combined: (0.95 AI + 0.5 rule-based) / 2 = 0.725
        assert result.success_score == 0.725


class TestReActSession:
    """Test cases for ReActSession."""
    
    def test_session_initialization(self):
        """Test session initialization."""
        session = ReActSession(user_input="Test input")
        
        assert session.user_input == "Test input"
        assert session.state == ReActState.IDLE
        assert len(session.tasks) == 0
        assert session.current_task_index == 0
        assert isinstance(session.id, str)
    
    def test_session_state_management(self):
        """Test session state management."""
        session = ReActSession()
        
        # Test state change
        session.update_state(ReActState.PLANNING)
        assert session.state == ReActState.PLANNING
        assert len(session.execution_log) > 0
    
    def test_session_task_navigation(self):
        """Test session task navigation."""
        session = ReActSession()
        session.tasks = [
            Task(description="Task 1"),
            Task(description="Task 2"),
            Task(description="Task 3")
        ]
        
        # Test current task
        current_task = session.get_current_task()
        assert current_task.description == "Task 1"
        
        # Test advancement
        has_more = session.advance_to_next_task()
        assert has_more is True
        assert session.current_task_index == 1
        
        current_task = session.get_current_task()
        assert current_task.description == "Task 2"
    
    def test_session_serialization(self):
        """Test session serialization."""
        session = ReActSession(user_input="Test")
        session.tasks = [Task(description="Test task")]
        
        # Test to_dict
        data = session.to_dict()
        assert data["user_input"] == "Test"
        assert data["state"] == "idle"
        assert len(data["tasks"]) == 1


class TestReActEngine:
    """Test cases for ReActEngine."""
    
    @pytest.fixture
    def mock_tool_registry(self):
        """Create a mock tool registry."""
        registry = MagicMock()
        registry.list_tools.return_value = ["file_read", "file_write", "bash"]
        return registry
    
    @pytest.mark.asyncio
    async def test_engine_initialization(self, mock_ai_client):
        """Test ReAct engine initialization."""
        engine = ReActEngine(mock_ai_client, ExecutionMode.SEQUENTIAL)
        
        assert engine.ai_client == mock_ai_client
        assert engine.execution_mode == ExecutionMode.SEQUENTIAL
        assert isinstance(engine.task_planner, TaskPlanner)
        assert isinstance(engine.result_evaluator, ResultEvaluator)
    
    @pytest.mark.asyncio
    async def test_process_user_input_flow(self, mock_ai_client, sample_planning_response):
        """Test complete user input processing flow."""
        # Setup
        mock_ai_client.chat.return_value = MagicMock(content=sample_planning_response)
        engine = ReActEngine(mock_ai_client, ExecutionMode.SEQUENTIAL)
        
        # Mock tool execution
        async def mock_execute_tool(tool_name, tool_input):
            yield ToolResult(type=ToolResultType.SUCCESS, content="Mocked result")
        
        with patch('simacode.react.engine.execute_tool', side_effect=mock_execute_tool):
            with patch.object(engine.tool_registry, 'list_tools', return_value=["file_read", "bash"]):
                with patch.object(engine.tool_registry, 'get_tool') as mock_get_tool:
                    mock_tool = AsyncMock()
                    mock_tool.validate_input = AsyncMock()
                    mock_get_tool.return_value = mock_tool
                    
                    # Execute
                    updates = []
                    async for update in engine.process_user_input("Test user input"):
                        updates.append(update)
                    
                    # Verify
                    assert len(updates) > 0
                    assert any(update.get("type") == "final_result" for update in updates)
    
    @pytest.mark.asyncio
    async def test_error_handling(self, mock_ai_client):
        """Test error handling in ReAct engine."""
        # Setup to cause planning error
        mock_ai_client.chat.side_effect = Exception("AI client error")
        engine = ReActEngine(mock_ai_client)
        
        # Execute
        updates = []
        async for update in engine.process_user_input("Test input"):
            updates.append(update)
        
        # Verify error handling
        error_updates = [update for update in updates if update.get("type") == "error"]
        assert len(error_updates) > 0


@pytest.mark.asyncio
async def test_integration_simple_workflow(mock_ai_client, sample_planning_response, sample_evaluation_response):
    """Test a simple end-to-end workflow."""
    # Setup responses
    responses = [
        MagicMock(content=sample_planning_response),  # Planning
        MagicMock(content=sample_evaluation_response),  # Evaluation 1
        MagicMock(content=sample_evaluation_response),  # Evaluation 2
        MagicMock(content=sample_evaluation_response),  # Overall evaluation
    ]
    mock_ai_client.chat.side_effect = responses
    
    # Create engine
    engine = ReActEngine(mock_ai_client, ExecutionMode.SEQUENTIAL)
    
    # Mock tool execution
    async def mock_execute_tool(tool_name, tool_input):
        yield ToolResult(type=ToolResultType.INFO, content="Starting tool")
        yield ToolResult(type=ToolResultType.OUTPUT, content="Tool output")
        yield ToolResult(type=ToolResultType.SUCCESS, content="Tool completed")
    
    # Execute integration test
    with patch('simacode.react.engine.execute_tool', side_effect=mock_execute_tool):
        with patch.object(engine.tool_registry, 'list_tools', return_value=["file_read", "bash"]):
            with patch.object(engine.tool_registry, 'get_tool') as mock_get_tool:
                mock_tool = AsyncMock()
                mock_tool.validate_input = AsyncMock()
                mock_get_tool.return_value = mock_tool
                
                updates = []
                async for update in engine.process_user_input("Read a file and list directory"):
                    updates.append(update)
                
                # Verify complete workflow
                update_types = [update.get("type") for update in updates]
                
                assert "status_update" in update_types
                assert "task_plan" in update_types
                assert "final_result" in update_types
                
                # Check final result
                final_updates = [u for u in updates if u.get("type") == "final_result"]
                assert len(final_updates) == 1
                
                final_result = final_updates[0]
                assert "session_data" in final_result
                assert "summary" in final_result



if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])