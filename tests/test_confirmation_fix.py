#!/usr/bin/env python3
"""
测试确认请求chunk_type修复效果
"""

import asyncio
import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from simacode.core.service import SimaCodeService
from simacode.api.routes.chat import process_regular_chunk

async def test_confirmation_chunk_processing():
    """测试确认请求chunk的处理"""
    
    print("🧪 测试确认请求chunk_type修复")
    print("=" * 50)
    
    # 模拟ReAct引擎发送的确认请求数据
    mock_update = {
        "type": "confirmation_request",
        "content": "规划了 3 个任务，请确认是否执行",
        "session_id": "test-session-123",
        "confirmation_request": {
            "session_id": "test-session-123",
            "tasks": [
                {"index": 1, "description": "创建备份脚本", "tool": "file_write"},
                {"index": 2, "description": "配置定时任务", "tool": "bash"},
                {"index": 3, "description": "测试备份功能", "tool": "bash"}
            ],
            "timeout_seconds": 300
        },
        "tasks_summary": {
            "total_tasks": 3,
            "tasks": [
                {"index": 1, "description": "创建备份脚本", "tool": "file_write"},
                {"index": 2, "description": "配置定时任务", "tool": "bash"},
                {"index": 3, "description": "测试备份功能", "tool": "bash"}
            ]
        },
        "confirmation_round": 1
    }
    
    # 测试Service Layer的处理
    print("1. 测试Service Layer的确认请求处理...")
    
    # 模拟_stream_task_response中的处理逻辑
    update_type = mock_update.get("type", "")
    content = mock_update.get("content", "")
    
    if update_type == "confirmation_request":
        confirmation_data = {
            "type": "confirmation_request",
            "content": content,
            "session_id": mock_update.get("session_id"),
            "confirmation_request": mock_update.get("confirmation_request"),
            "tasks_summary": mock_update.get("tasks_summary"),
            "confirmation_round": mock_update.get("confirmation_round")
        }
        service_output = f"[confirmation_request]{json.dumps(confirmation_data)}"
        
        print(f"✅ Service Layer输出格式: [confirmation_request]{{...}}")
        print(f"   长度: {len(service_output)} 字符")
        print(f"   前缀检查: {service_output.startswith('[confirmation_request]{')}")
    
    # 测试Chat Route的处理
    print("\n2. 测试Chat Route的chunk处理...")
    
    try:
        processed_chunk = process_regular_chunk(service_output, "test-session-123")
        
        print(f"✅ 处理成功!")
        print(f"   chunk_type: {processed_chunk.chunk_type}")
        print(f"   requires_response: {processed_chunk.requires_response}")
        print(f"   stream_paused: {processed_chunk.stream_paused}")
        print(f"   content: {processed_chunk.chunk[:50]}...")
        
        if hasattr(processed_chunk, 'confirmation_data'):
            print(f"   confirmation_data存在: {processed_chunk.confirmation_data is not None}")
        
        if hasattr(processed_chunk, 'metadata'):
            print(f"   metadata: {processed_chunk.metadata}")
            
        # 验证关键字段
        success = True
        if processed_chunk.chunk_type != "confirmation_request":
            print(f"❌ chunk_type应该是'confirmation_request'，实际是'{processed_chunk.chunk_type}'")
            success = False
            
        if not processed_chunk.requires_response:
            print("❌ requires_response应该是True")
            success = False
            
        if not processed_chunk.stream_paused:
            print("❌ stream_paused应该是True")
            success = False
            
        if success:
            print("\n🎉 测试通过! 确认请求现在会正确设置chunk_type为'confirmation_request'")
        else:
            print("\n❌ 测试失败，仍需要进一步调试")
            
    except Exception as e:
        print(f"❌ Chat Route处理失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n3. 测试JSON序列化输出...")
    
    try:
        # 测试完整的JSON输出
        chunk_json = processed_chunk.model_dump_json()
        chunk_dict = json.loads(chunk_json)
        
        print(f"✅ JSON序列化成功")
        print(f"   chunk_type: {chunk_dict.get('chunk_type')}")
        print(f"   confirmation_data存在: {'confirmation_data' in chunk_dict}")
        print(f"   完整JSON长度: {len(chunk_json)} 字符")
        
        # 显示给客户端的最终格式
        print(f"\n📤 发送给客户端的最终格式:")
        print(f"data: {chunk_json}")
        
    except Exception as e:
        print(f"❌ JSON序列化失败: {e}")

if __name__ == "__main__":
    asyncio.run(test_confirmation_chunk_processing())