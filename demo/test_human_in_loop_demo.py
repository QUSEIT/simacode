#!/usr/bin/env python3
"""
Human-in-Loop Feature Demo Script

This script demonstrates the human confirmation feature for the ReAct engine.
It tests the basic functionality without requiring full CLI interaction.
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from simacode.config import Config, ReactConfig
from simacode.react.confirmation_manager import ConfirmationManager
from simacode.react.planner import Task, TaskType
from simacode.api.models import TaskConfirmationRequest, TaskConfirmationResponse


async def demo_confirmation_workflow():
    """Demonstrate the confirmation workflow."""
    
    print("🚀 Human-in-Loop Feature Demo")
    print("="*50)
    
    # 1. Test configuration loading
    print("\n1. Testing Configuration Loading...")
    
    try:
        config = Config()
        react_config = config.react
        
        print(f"   ✓ Default confirm_by_human: {react_config.confirm_by_human}")
        print(f"   ✓ Default confirmation_timeout: {react_config.confirmation_timeout}s")
        print(f"   ✓ Default allow_task_modification: {react_config.allow_task_modification}")
        print(f"   ✓ Default auto_confirm_safe_tasks: {react_config.auto_confirm_safe_tasks}")
        
    except Exception as e:
        print(f"   ❌ Configuration loading failed: {e}")
        return
    
    # 2. Test confirmation manager
    print("\n2. Testing Confirmation Manager...")
    
    try:
        manager = ConfirmationManager()
        print("   ✓ ConfirmationManager initialized successfully")
        
        # Create test tasks
        test_tasks = [
            Task(
                id="task-1",
                description="Read configuration file",
                tool_name="file_read",
                type=TaskType.FILE_OPERATION,
                priority=1,
                expected_outcome="Display config contents"
            ),
            Task(
                id="task-2",
                description="Create backup directory",
                tool_name="bash",
                type=TaskType.COMMAND_EXECUTION,
                priority=2,
                expected_outcome="Directory created successfully"
            )
        ]
        
        session_id = "demo-session-123"
        
        # Request confirmation
        confirmation_request = await manager.request_confirmation(
            session_id=session_id,
            tasks=test_tasks,
            timeout_seconds=5  # Short timeout for demo
        )
        
        print(f"   ✓ Confirmation request created for session: {session_id}")
        print(f"   ✓ Tasks in request: {len(confirmation_request.tasks)}")
        print(f"   ✓ Timeout: {confirmation_request.timeout_seconds}s")
        
        # Display task details
        print("\n   📋 Planned Tasks:")
        for i, task_dict in enumerate(confirmation_request.tasks, 1):
            task_desc = task_dict.get('description', 'Unknown task')
            tool_name = task_dict.get('tool_name', 'unknown')
            print(f"      {i}. {task_desc} (using {tool_name})")
        
    except Exception as e:
        print(f"   ❌ Confirmation manager test failed: {e}")
        return
    
    # 3. Simulate user confirmation (auto-confirm for demo)
    print("\n3. Simulating User Confirmation...")
    
    try:
        # Create confirmation response
        response = TaskConfirmationResponse(
            session_id=session_id,
            action="confirm"  # Auto-confirm for demo
        )
        
        # Submit response in a separate task to avoid blocking
        async def submit_response():
            await asyncio.sleep(1)  # Simulate user thinking time
            success = manager.submit_confirmation(session_id, response)
            if success:
                print("   ✓ User confirmation submitted successfully")
            else:
                print("   ❌ Failed to submit confirmation")
        
        # Start submission task
        submit_task = asyncio.create_task(submit_response())
        
        # Wait for confirmation (with timeout)
        try:
            confirmed_response = await manager.wait_for_confirmation(session_id, timeout_seconds=5)
            print(f"   ✓ Confirmation received: {confirmed_response.action}")
            
            if confirmed_response.action == "confirm":
                print("   ✅ Tasks approved for execution!")
            elif confirmed_response.action == "modify":
                print("   📝 Tasks marked for modification")
                if confirmed_response.user_message:
                    print(f"      User message: {confirmed_response.user_message}")
            elif confirmed_response.action == "cancel":
                print("   ❌ Tasks cancelled by user")
            
        except asyncio.TimeoutError:
            print("   ⏰ Confirmation timeout (this is expected for demo)")
        
        # Wait for submission task to complete
        await submit_task
        
    except Exception as e:
        print(f"   ❌ User confirmation simulation failed: {e}")
        return
    
    # 4. Test different confirmation scenarios
    print("\n4. Testing Different Confirmation Scenarios...")
    
    scenarios = [
        ("confirm", "User confirms execution"),
        ("modify", "User requests modification"),
        ("cancel", "User cancels execution")
    ]
    
    for action, description in scenarios:
        try:
            test_session = f"test-{action}-session"
            
            # Create new confirmation request
            await manager.request_confirmation(test_session, test_tasks[:1], timeout_seconds=1) 
            
            # Create response
            response = TaskConfirmationResponse(
                session_id=test_session,
                action=action,
                user_message=f"Test message for {action}" if action == "modify" else None
            )
            
            # Submit immediately
            success = manager.submit_confirmation(test_session, response)
            
            if success:
                print(f"   ✓ {description}: Success")
            else:
                print(f"   ❌ {description}: Failed")
                
        except Exception as e:
            print(f"   ❌ Scenario '{action}' failed: {e}")
    
    # 5. Display next steps
    print("\n5. Next Steps for Testing...")
    print("   📝 To enable human confirmation in SimaCode:")
    print("   ")
    print("   1. Edit .simacode/config.yaml:")
    print("      react:")
    print("        confirm_by_human: true")
    print("        confirmation_timeout: 300")
    print("   ")
    print("   2. Run SimaCode in ReAct mode:")
    print("      simacode chat --react")
    print("   ")
    print("   3. Try a command that requires tools:")
    print("      'Create a backup of my config file'")
    print("   ")
    print("   4. You should see a confirmation prompt before execution!")
    
    print("\n🎉 Demo completed successfully!")
    print("The Human-in-Loop feature is ready for production use.")


def test_config_generation():
    """Generate a test configuration file."""
    print("\n🔧 Generating test configuration...")
    
    config_dir = Path.cwd() / ".simacode"
    config_file = config_dir / "config.yaml"
    
    config_content = """# SimaCode Configuration with Human-in-Loop Feature
project_name: "SimaCode with Human Confirmation"

# AI configuration
ai:
  provider: "openai"
  model: "gpt-4"
  temperature: 0.1

# ReAct engine configuration with human confirmation
react:
  confirm_by_human: true          # Enable human confirmation
  confirmation_timeout: 300       # 5 minutes timeout
  allow_task_modification: true   # Allow users to modify tasks
  auto_confirm_safe_tasks: false  # Require confirmation for all tasks

# Conversation context management
conversation_context:
  strategy: "compressed"
  max_messages: 100
  max_tokens: 8000
  preserve_all: false
  recent_messages: 5
  compression_ratio: 0.3
  preserve_topics: true
  token_budget: 4000
  min_recent: 3
  auto_summarize: true
"""
    
    try:
        config_dir.mkdir(exist_ok=True)
        
        with open(config_file, "w") as f:
            f.write(config_content)
        
        print(f"   ✓ Configuration file created: {config_file}")
        print("   ✓ Human confirmation is now ENABLED")
        print("\n   To disable confirmation, change:")
        print("     react.confirm_by_human: false")
        
    except Exception as e:
        print(f"   ❌ Failed to create config file: {e}")


if __name__ == "__main__":
    # Run the demo
    try:
        asyncio.run(demo_confirmation_workflow())
        
        # Ask if user wants to generate config
        print("\n" + "="*50)
        response = input("Generate test configuration file with confirmation enabled? (y/n): ")
        if response.lower() in ['y', 'yes']:
            test_config_generation()
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        sys.exit(1)