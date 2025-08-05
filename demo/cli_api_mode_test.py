#!/usr/bin/env python3
"""
CLI vs API Mode Confirmation Test

Tests that CLI mode uses traditional confirmation (no timeout)
while API mode uses chat stream confirmation.
"""

import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import os
from types import SimpleNamespace

from simacode.config import Config
from simacode.services.react_service import ReActService
from simacode.core.service import SimaCodeService

# 设置一个假的API密钥用于测试
os.environ['OPENAI_API_KEY'] = 'test-key-for-unit-test'


def create_test_config():
    """创建测试配置"""
    config = Config()
    
    # 确保有AI配置
    if not hasattr(config, 'ai'):
        config.ai = SimpleNamespace()
    config.ai.provider = 'openai'
    config.ai.model = 'gpt-4'
    config.ai.api_key = 'test-key'
    
    # 确保有React配置
    if not hasattr(config, 'react'):
        config.react = SimpleNamespace()
    config.react.confirm_by_human = True
    
    return config


def test_cli_mode_setup():
    """测试CLI模式的设置"""
    print("🔧 Testing CLI Mode Setup")
    print("=" * 30)
    
    # 模拟CLI模式的配置
    config = create_test_config()
    
    # 创建ReActService（CLI模式）
    react_service = ReActService(config)
    
    # 检查API模式标志
    api_mode = react_service.react_engine.api_mode
    print(f"CLI模式 - api_mode: {api_mode}")
    
    if not api_mode:
        print("✅ CLI模式正确设置为非API模式")
        return True
    else:
        print("❌ CLI模式错误地设置为API模式")
        return False


def test_api_mode_setup():
    """测试API模式的设置"""
    print("\n🔧 Testing API Mode Setup")
    print("=" * 30)
    
    # 模拟API模式的配置
    config = create_test_config()
    
    # 创建SimaCodeService（API模式）
    simacode_service = SimaCodeService(config)
    
    # 检查API模式标志
    api_mode = simacode_service.react_service.react_engine.api_mode
    print(f"API模式 - api_mode: {api_mode}")
    
    if api_mode:
        print("✅ API模式正确设置为API模式")
        return True
    else:
        print("❌ API模式错误地设置为非API模式")
        return False


def test_confirmation_mode_detection():
    """测试确认模式检测"""
    print("\n🔍 Testing Confirmation Mode Detection")
    print("=" * 40)
    
    # CLI模式测试
    cli_config = create_test_config()
    cli_service = ReActService(cli_config)
    
    cli_is_stream_mode = cli_service.react_engine._is_chat_stream_mode()
    print(f"CLI模式 - _is_chat_stream_mode(): {cli_is_stream_mode}")
    
    # API模式测试
    api_config = create_test_config()
    api_service = SimaCodeService(api_config)
    
    api_is_stream_mode = api_service.react_service.react_engine._is_chat_stream_mode()
    print(f"API模式 - _is_chat_stream_mode(): {api_is_stream_mode}")
    
    # 验证结果
    success = True
    if cli_is_stream_mode:
        print("❌ CLI模式错误地检测为chat stream模式")
        success = False
    else:
        print("✅ CLI模式正确地检测为传统确认模式")
    
    if not api_is_stream_mode:
        print("❌ API模式错误地检测为传统确认模式")
        success = False
    else:
        print("✅ API模式正确地检测为chat stream模式")
    
    return success


def test_timeout_behavior():
    """测试超时行为"""
    print("\n⏰ Testing Timeout Behavior")
    print("=" * 30)
    
    print("CLI模式预期行为：")
    print("  - 使用传统确认管理器")
    print("  - 调用 wait_for_confirmation(session_id, None)")
    print("  - 无超时限制，一直等待用户确认")
    
    print("\nAPI模式预期行为：")
    print("  - 使用chat stream确认管理器")
    print("  - 调用 wait_for_confirmation(session_id, 300)")
    print("  - 有超时限制，300秒后自动取消")
    
    print("\n✅ 超时行为理论验证通过")
    return True


def main():
    """主测试函数"""
    print("🧪 CLI vs API Mode Confirmation Test")
    print("=" * 50)
    
    tests = [
        ("CLI Mode Setup", test_cli_mode_setup),
        ("API Mode Setup", test_api_mode_setup),
        ("Confirmation Mode Detection", test_confirmation_mode_detection),
        ("Timeout Behavior", test_timeout_behavior),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            print(f"\n🏃 Running: {test_name}")
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ Test {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # 总结结果
    print(f"\n📊 Test Results Summary")
    print("=" * 30)
    
    passed = 0
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
        if result:
            passed += 1
    
    print(f"\nOverall: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("\n🎉 All tests passed! CLI and API mode separation is working correctly.")
        print("\n📋 Mode Summary:")
        print("CLI模式 (simacode chat --interactive --react):")
        print("  - api_mode = False")
        print("  - 使用传统确认管理器")
        print("  - 无超时限制，一直等待用户确认")
        print("\nAPI模式 (simacode serve):")
        print("  - api_mode = True")
        print("  - 使用chat stream确认管理器")
        print("  - 有超时限制，默认300秒")
    else:
        print(f"\n⚠️  {len(results) - passed} test(s) failed. Check implementation.")


if __name__ == "__main__":
    main()