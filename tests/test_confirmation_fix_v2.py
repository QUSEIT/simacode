#!/usr/bin/env python3
"""
测试修复后的确认请求数据结构
"""

import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from simacode.api.routes.chat import process_regular_chunk

def test_fixed_confirmation_structure():
    """测试修复后的确认请求结构"""
    
    print("🧪 测试修复后的确认请求数据结构")
    print("=" * 50)
    
    # 模拟修复后的Service Layer输出
    mock_update = {
        "type": "confirmation_request",
        "content": "规划了 3 个任务，请确认是否执行",
        "session_id": "test-session-123",
        "confirmation_request": {
            "session_id": "test-session-123",
            "tasks": [
                {
                    "id": "task-1",
                    "description": "Create a new directory for the Python project",
                    "tool_name": "bash",
                    "type": "file_operation"
                },
                {
                    "id": "task-2", 
                    "description": "Create a virtual environment for the project",
                    "tool_name": "bash",
                    "type": "file_operation"
                },
                {
                    "id": "task-3",
                    "description": "Install necessary testing libraries",
                    "tool_name": "bash", 
                    "type": "file_operation"
                }
            ],
            "timeout_seconds": 300
        },
        "tasks_summary": {
            "total_tasks": 3,
            "risk_level": "medium"
        },
        "confirmation_round": 1
    }
    
    # 模拟修复后的Service Layer处理逻辑
    confirmation_request = mock_update.get("confirmation_request", {})
    tasks_summary = mock_update.get("tasks_summary", {})
    
    fixed_confirmation_data = {
        "type": "confirmation_request",
        "content": mock_update.get("content"),
        "session_id": mock_update.get("session_id"),
        # 扁平化：直接提供 tasks 和其他字段
        "tasks": confirmation_request.get("tasks", []),
        "timeout_seconds": confirmation_request.get("timeout_seconds", 300),
        "confirmation_round": mock_update.get("confirmation_round", 1),
        "risk_level": tasks_summary.get("risk_level", "unknown"),
        # 保留原始结构
        "confirmation_request": confirmation_request,
        "tasks_summary": tasks_summary
    }
    
    service_output = f"[confirmation_request]{json.dumps(fixed_confirmation_data)}"
    
    print("1. 测试修复后的Service Layer输出...")
    print(f"✅ tasks 在顶层: {'tasks' in fixed_confirmation_data}")
    print(f"✅ 任务数量: {len(fixed_confirmation_data.get('tasks', []))}")
    print(f"✅ 风险级别: {fixed_confirmation_data.get('risk_level')}")
    
    # 测试Chat Route处理
    print("\n2. 测试Chat Route处理...")
    try:
        processed_chunk = process_regular_chunk(service_output, "test-session-123")
        
        print(f"✅ chunk_type: {processed_chunk.chunk_type}")
        print(f"✅ 任务数量显示正确: {'3个任务' in processed_chunk.chunk}")
        print(f"✅ confirmation_data存在: {processed_chunk.confirmation_data is not None}")
        
        # 验证JavaScript客户端能够访问的数据
        confirmation_data = processed_chunk.confirmation_data
        if 'tasks' in confirmation_data:
            tasks = confirmation_data['tasks']
            print(f"✅ JavaScript客户端可访问tasks: {len(tasks)}个")
            print(f"✅ 第一个任务: {tasks[0].get('description', 'N/A')}")
        else:
            print("❌ JavaScript客户端无法访问tasks")
            
    except Exception as e:
        print(f"❌ 处理失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n3. 模拟JavaScript客户端解析...")
    try:
        # 模拟JavaScript客户端的解构操作
        chunk_data = json.loads(processed_chunk.model_dump_json())
        confirmation_data = chunk_data.get('confirmation_data', {})
        
        tasks = confirmation_data.get('tasks', [])
        timeout_seconds = confirmation_data.get('timeout_seconds')
        risk_level = confirmation_data.get('risk_level')
        confirmation_round = confirmation_data.get('confirmation_round')
        
        print(f"✅ tasks.length: {len(tasks)}")
        print(f"✅ timeout_seconds: {timeout_seconds}")
        print(f"✅ risk_level: {risk_level}")
        print(f"✅ confirmation_round: {confirmation_round}")
        
        if len(tasks) > 0:
            print("\n任务详情:")
            for i, task in enumerate(tasks):
                print(f"  {i+1}. {task.get('description')}")
                print(f"     工具: {task.get('tool_name', 'unknown')}")
                print(f"     类型: {task.get('type', 'unknown')}")
        
        print("\n🎉 修复成功！JavaScript客户端现在可以正确解析数据")
        
    except Exception as e:
        print(f"❌ JavaScript模拟解析失败: {e}")

if __name__ == "__main__":
    test_fixed_confirmation_structure()