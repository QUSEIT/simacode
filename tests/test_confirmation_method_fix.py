#!/usr/bin/env python3
"""
测试确认方法修复
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_service_methods():
    """测试Service中的确认相关方法"""
    
    print("🧪 测试确认方法修复")
    print("=" * 50)
    
    try:
        from simacode.core.service import SimaCodeService
        
        # 检查方法存在性
        print("1. 检查SimaCodeService方法...")
        service_methods = dir(SimaCodeService)
        
        has_submit_confirmation = 'submit_confirmation' in service_methods
        has_submit_chat_confirmation = 'submit_chat_confirmation' in service_methods
        
        print(f"✅ submit_confirmation: {has_submit_confirmation}")
        print(f"❌ submit_chat_confirmation: {has_submit_chat_confirmation}")
        
        if has_submit_confirmation and not has_submit_chat_confirmation:
            print("✅ 修复正确：使用 submit_confirmation 而不是 submit_chat_confirmation")
        else:
            print("❌ 修复有问题")
            
    except Exception as e:
        print(f"❌ 导入失败: {e}")
    
    try:
        from simacode.api.models import TaskConfirmationResponse
        print("\n2. 测试TaskConfirmationResponse...")
        
        # 创建测试响应
        test_response = TaskConfirmationResponse(
            session_id="test-123",
            action="modify",
            user_message="请添加错误处理"
        )
        
        print(f"✅ 创建TaskConfirmationResponse: {test_response.action}")
        print(f"✅ session_id: {test_response.session_id}")
        print(f"✅ user_message: {test_response.user_message}")
        
    except Exception as e:
        print(f"❌ TaskConfirmationResponse测试失败: {e}")
    
    print("\n🎉 确认方法修复测试完成")

if __name__ == "__main__":
    test_service_methods()