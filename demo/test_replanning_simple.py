#!/usr/bin/env python3
"""
Simple Task Replanning Test

This script tests just the task replanning functionality to verify
that user modification requests actually result in replanned tasks.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from simacode.config import Config, ReactConfig
from simacode.react.engine import ReActEngine, ReActSession, ExecutionMode
from simacode.react.planner import Task, TaskType
from simacode.api.models import TaskConfirmationResponse


async def test_replanning_logic():
    """Test the core replanning logic directly."""
    
    print("🧪 Testing Task Replanning Logic")
    print("="*40)
    
    # Create a minimal configuration
    config = Config()
    config.react = ReactConfig(confirm_by_human=True)
    
    # Create engine (we'll mock the necessary parts)
    from unittest.mock import AsyncMock, MagicMock
    
    mock_ai_client = MagicMock()
    engine = ReActEngine(mock_ai_client, ExecutionMode.SEQUENTIAL, config)
    
    # Create test session with original tasks
    session = ReActSession(user_input="Create backup script")
    session.tasks = [
        Task(
            id="task-1",
            description="Create simple backup script",
            tool_name="file_write",
            type=TaskType.FILE_OPERATION,
            priority=1,
            expected_outcome="Script created"
        )
    ]
    
    print(f"Original tasks: {len(session.tasks)}")
    for i, task in enumerate(session.tasks, 1):
        print(f"  {i}. {task.description}")
    
    # Mock the task planner to return modified tasks
    mock_planner = AsyncMock()
    mock_planner.plan_tasks.return_value = [
        Task(
            id="task-1-modified",
            description="Create advanced backup script with compression",
            tool_name="file_write", 
            type=TaskType.FILE_OPERATION,
            priority=1,
            expected_outcome="Advanced script created"
        ),
        Task(
            id="task-2-modified",
            description="Schedule backup as cron job",
            tool_name="bash",
            type=TaskType.COMMAND_EXECUTION,
            priority=2,
            expected_outcome="Backup scheduled"
        )
    ]
    
    engine.task_planner = mock_planner
    
    # Test the replanning method directly
    print("\n🔄 Testing _replan_tasks_with_user_feedback...")
    
    user_feedback = "Make it more advanced with compression and scheduling"
    
    try:
        await engine._replan_tasks_with_user_feedback(session, user_feedback)
        
        print(f"After replanning: {len(session.tasks)} tasks")
        for i, task in enumerate(session.tasks, 1):
            print(f"  {i}. {task.description}")
        
        # Verify replanning worked
        assert len(session.tasks) == 2, f"Expected 2 tasks, got {len(session.tasks)}"
        assert "advanced" in session.tasks[0].description.lower(), "First task should be advanced"
        assert "cron" in session.tasks[1].description.lower(), "Second task should be cron job"
        
        print("✅ Replanning logic works correctly!")
        
        # Test the confirmation response processing
        print("\n🔄 Testing _process_confirmation_response with modify action...")
        
        # Reset tasks to original
        session.tasks = [
            Task(
                id="task-orig",
                description="Original task",
                tool_name="file_write",
                type=TaskType.FILE_OPERATION,
                priority=1,
                expected_outcome="Original result"
            )
        ]
        
        print(f"Before modify response: {len(session.tasks)} tasks")
        
        # Create modification response  
        modify_response = TaskConfirmationResponse(
            session_id=session.id,
            action="modify",
            user_message="Please make this better with more features"
        )
        
        # This should trigger replanning and raise ReplanningRequiresConfirmationError
        try:
            await engine._process_confirmation_response(session, modify_response)
            print("❌ Expected ReplanningRequiresConfirmationError but got none")
            return False
        except Exception as e:
            if "replanned" in str(e).lower() or "confirmation" in str(e).lower():
                print(f"✅ Correctly raised exception: {type(e).__name__}")
                print(f"After replanning: {len(session.tasks)} tasks")
                
                # Verify tasks were replanned
                if len(session.tasks) == 2:
                    print("✅ Tasks were correctly replanned!")
                    return True
                else:
                    print(f"❌ Expected 2 replanned tasks, got {len(session.tasks)}")
                    return False
            else:
                print(f"❌ Unexpected exception: {e}")
                return False
        
    except Exception as e:
        print(f"❌ Replanning test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_cli_integration():
    """Test CLI integration separately."""
    
    print("\n🖥️  Testing CLI Integration")
    print("="*30)
    
    # Test the confirmation request handler 
    from simacode.cli import _handle_confirmation_request
    from simacode.core.service import SimaCodeService
    
    # Mock update with confirmation request
    update = {
        "type": "confirmation_request",
        "session_id": "test-session",
        "confirmation_request": {},
        "tasks_summary": {
            "total_tasks": 2,
            "risk_level": "low", 
            "tasks": [
                {
                    "index": 1,
                    "description": "Create backup script",
                    "tool": "file_write",
                    "priority": 1,
                    "expected_outcome": "Script created"
                },
                {
                    "index": 2,
                    "description": "Run backup script", 
                    "tool": "bash",
                    "priority": 2,
                    "expected_outcome": "Backup completed"
                }
            ]
        },
        "confirmation_round": 1
    }
    
    print("✅ CLI integration test structure is ready")
    print("   (Manual testing required for user interaction)")


if __name__ == "__main__":
    async def main():
        try:
            success = await test_replanning_logic()
            
            if success:
                await test_cli_integration()
                print("\n🎉 Core replanning logic is working!")
                print("\nNext steps:")
                print("1. The replanning logic itself works correctly")
                print("2. The issue may be in the full workflow integration")
                print("3. Try testing with actual CLI: `simacode chat --react`")
                print("4. Enable confirmation: set react.confirm_by_human: true")
            else:
                print("\n❌ Core replanning logic needs fixes")
                sys.exit(1)
                
        except KeyboardInterrupt:
            print("\n⏹️  Test interrupted")
        except Exception as e:
            print(f"\n💥 Test failed: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    asyncio.run(main())