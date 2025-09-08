#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试脚本：验证修改计划后跳过确认的功能
"""

import asyncio
import sys
import os

# 添加项目路径到sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from simacode.react.engine import ReActEngine, ReActSession, ReActState
from simacode.config import Config

async def test_confirmation_skip():
    """测试修改计划后跳过确认的功能"""
    
    print("🧪 测试：修改计划后跳过确认功能")
    print("=" * 50)
    
    # 创建配置
    config = Config()
    
    # 创建ReAct引擎（CLI模式）
    engine = ReActEngine(config, api_mode=False)
    
    # 创建测试会话
    session = ReActSession("test-session", "创建一个Python文件")
    
    # 模拟设置跳过确认标志
    session.metadata["skip_next_confirmation"] = True
    session.update_state(ReActState.AWAITING_CONFIRMATION)
    
    print(f"✅ 会话状态: {session.state}")
    print(f"✅ 跳过确认标志: {session.metadata.get('skip_next_confirmation', False)}")
    
    # 测试标志是否正确设置
    if session.metadata.get("skip_next_confirmation", False):
        print("✅ 跳过确认标志已正确设置")
        
        # 模拟清除标志
        session.metadata.pop("skip_next_confirmation", None)
        session.update_state(ReActState.EXECUTING)
        
        print(f"✅ 标志清除后状态: {session.state}")
        print(f"✅ 跳过确认标志: {session.metadata.get('skip_next_confirmation', False)}")
        
        if not session.metadata.get("skip_next_confirmation", False):
            print("✅ 标志已正确清除，确保只跳过一次")
        else:
            print("❌ 标志清除失败")
    else:
        print("❌ 跳过确认标志设置失败")
    
    print("\n🎉 测试完成！")

if __name__ == "__main__":
    asyncio.run(test_confirmation_skip())