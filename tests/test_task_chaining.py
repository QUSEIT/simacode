#!/usr/bin/env python3
"""
Test script for task chaining functionality
"""

import asyncio
import sys
import os
from pathlib import Path

# Add simacode to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from simacode.react.engine import ReActEngine, ReActSession
from simacode.react.planner import Task, TaskType, TaskStatus, PlanningContext
from simacode.tools.base import ToolResult, ToolResultType

async def test_task_chaining():
    """Test that task chaining and placeholder substitution works correctly."""
    print("Testing task chaining functionality...")
    
    # Create ReAct engine with None for AI client (we only need the substitution method)
    engine = ReActEngine(None)
    
    # Create a test session
    session = ReActSession(
        user_input="Test task chaining with placeholders"
    )
    
    # Create mock tasks
    task1 = Task(
        id="task1",
        type=TaskType.FILE_OPERATION,
        description="Mock OCR task",
        tool_name="mock_ocr",
        tool_input={"file_path": "/test/image.png"},
        expected_outcome="Text extracted successfully"
    )
    
    task2 = Task(
        id="task2", 
        type=TaskType.FILE_OPERATION,
        description="Save extracted text",
        tool_name="file_write",
        tool_input={
            "file_path": "output.json",
            "content": "<extracted_text_here>"  # This should be replaced
        },
        expected_outcome="Text saved successfully",
        dependencies=["task1"]
    )
    
    session.tasks = [task1, task2]
    
    # Mock some results for task1
    mock_results = [
        ToolResult(
            type=ToolResultType.SUCCESS,
            content="This is the extracted text from the image",
            execution_id="test"
        )
    ]
    
    # Store mock results as if task1 completed
    session.task_results["task1"] = mock_results
    
    # Now test the placeholder substitution on task2
    processed_task2 = engine._substitute_task_placeholders(session, task2)
    
    # Check if the placeholder was replaced
    expected_content = "This is the extracted text from the image"
    actual_content = processed_task2.tool_input.get("content", "")
    
    print(f"Original content: {task2.tool_input.get('content', '')}")
    print(f"Processed content: {actual_content}")
    print(f"Expected content: {expected_content}")
    
    # Verify the substitution worked
    if actual_content == expected_content:
        print("✅ Task chaining test PASSED - placeholder was correctly replaced!")
        return True
    else:
        print("❌ Task chaining test FAILED - placeholder was not replaced correctly")
        return False

async def main():
    """Run the test."""
    try:
        success = await test_task_chaining()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())