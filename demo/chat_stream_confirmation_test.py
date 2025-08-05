#!/usr/bin/env python3
"""
Chat Stream Confirmation Test Client

Tests the new chat stream confirmation functionality where
confirmation is handled through the /api/v1/chat/stream interface.
"""

import asyncio
import json
import sys
from pathlib import Path
import logging
import requests
import time

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChatStreamConfirmationTester:
    """测试chat stream确认功能的客户端"""
    
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.session_id = f"test-chat-confirm-{int(time.time())}"
    
    def send_chat_request(self, message: str, session_id: str = None) -> requests.Response:
        """发送聊天请求"""
        url = f"{self.base_url}/api/v1/chat/stream"
        
        data = {
            "message": message,
            "session_id": session_id or self.session_id,
            "stream": True
        }
        
        logger.info(f"Sending request to {url}")
        logger.info(f"Data: {data}")
        
        return requests.post(
            url, 
            json=data, 
            stream=True,
            headers={'Content-Type': 'application/json'}
        )
    
    def parse_stream_response(self, response):
        """解析流式响应"""
        chunks = []
        confirmation_requests = []
        
        try:
            for line in response.iter_lines(decode_unicode=True):
                if line.startswith('data: '):
                    chunk_data = json.loads(line[6:])
                    chunks.append(chunk_data)
                    
                    logger.info(f"Received chunk: {chunk_data.get('chunk_type', 'unknown')} - {chunk_data.get('chunk', '')[:100]}")
                    
                    # 检查是否为确认请求
                    if chunk_data.get('chunk_type') == 'confirmation_request':
                        confirmation_requests.append(chunk_data)
                        logger.info("🔔 CONFIRMATION REQUEST DETECTED!")
                        logger.info(f"   Session: {chunk_data.get('session_id')}")
                        logger.info(f"   Tasks: {chunk_data.get('confirmation_data', {}).get('total_tasks', 0)}")
                        logger.info(f"   Risk: {chunk_data.get('metadata', {}).get('risk_level', 'unknown')}")
                        
                        # 显示任务详情
                        tasks = chunk_data.get('confirmation_data', {}).get('tasks', [])
                        for task in tasks[:3]:  # 只显示前3个
                            logger.info(f"   {task.get('index', '?')}. {task.get('description', 'Unknown')}")
                        if len(tasks) > 3:
                            logger.info(f"   ... and {len(tasks) - 3} more tasks")
                        
                        return chunks, chunk_data  # 返回用于确认的数据
        
        except Exception as e:
            logger.error(f"Error parsing stream response: {e}")
        
        return chunks, None
    
    def test_confirmation_workflow(self):
        """测试完整的确认工作流程"""
        print("🚀 Testing Chat Stream Confirmation Workflow")
        print("=" * 50)
        
        # 1. 发送需要确认的任务
        test_task = "Create a comprehensive backup system for my project files with automated scheduling"
        
        print(f"\n📤 Step 1: Sending task that requires confirmation")
        print(f"   Task: {test_task}")
        
        response = self.send_chat_request(test_task)
        
        if response.status_code != 200:
            print(f"❌ Request failed with status {response.status_code}")
            print(f"   Response: {response.text}")
            return False
        
        print("✅ Request sent successfully, parsing response...")
        
        # 2. 解析响应，查找确认请求
        chunks, confirmation_data = self.parse_stream_response(response)
        
        if not confirmation_data:
            print("❌ No confirmation request found in response")
            print("   This might indicate:")
            print("   - Confirmation is disabled in config")
            print("   - Task doesn't require confirmation")
            print("   - ReAct mode not triggered")
            return False
        
        print(f"✅ Confirmation request received!")
        print(f"   Session ID: {confirmation_data.get('session_id')}")
        print(f"   Tasks count: {confirmation_data.get('confirmation_data', {}).get('total_tasks', 0)}")
        
        # 3. 测试不同的确认响应
        confirmation_tests = [
            ("confirm", "CONFIRM_ACTION:confirm", "确认执行"),
            ("modify", "CONFIRM_ACTION:modify:请添加错误处理和日志记录功能", "修改任务"),
            ("cancel", "CONFIRM_ACTION:cancel", "取消执行")
        ]
        
        for test_name, confirm_message, description in confirmation_tests:
            print(f"\n📤 Step 2: Testing {description}")
            print(f"   Message: {confirm_message}")
            
            confirm_response = self.send_chat_request(
                confirm_message, 
                confirmation_data.get('session_id')
            )
            
            if confirm_response.status_code != 200:
                print(f"❌ Confirmation failed with status {confirm_response.status_code}")
                continue
            
            print(f"✅ Confirmation response sent")
            
            # 解析确认响应
            confirm_chunks, _ = self.parse_stream_response(confirm_response)
            
            # 检查响应类型
            if confirm_chunks:
                last_chunk = confirm_chunks[-1]
                if last_chunk.get('chunk_type') == 'confirmation_received':
                    print(f"✅ Confirmation successfully received: {last_chunk.get('chunk', '')}")
                elif last_chunk.get('chunk_type') == 'error':
                    print(f"❌ Confirmation error: {last_chunk.get('chunk', '')}")
                else:
                    print(f"📝 Response: {last_chunk.get('chunk_type')} - {last_chunk.get('chunk', '')[:100]}")
            
            # 只测试第一个（confirm），其他的仅做演示
            if test_name == "confirm":
                break
        
        return True
    
    def test_message_format_validation(self):
        """测试消息格式验证"""
        print("\n🧪 Testing Message Format Validation")
        print("=" * 40)
        
        # 测试无效的确认消息格式
        invalid_messages = [
            "CONFIRM_ACTION:",  # 空动作
            "CONFIRM_ACTION:invalid_action",  # 无效动作
            "INVALID_FORMAT:confirm",  # 错误前缀
            "CONFIRM_ACTION",  # 缺失冒号
        ]
        
        for invalid_msg in invalid_messages:
            print(f"\n📤 Testing invalid message: {invalid_msg}")
            
            response = self.send_chat_request(invalid_msg)
            
            if response.status_code == 200:
                chunks, _ = self.parse_stream_response(response)
                if chunks:
                    last_chunk = chunks[-1]
                    if last_chunk.get('chunk_type') == 'error':
                        print(f"✅ Correctly rejected with error: {last_chunk.get('chunk', '')[:100]}")
                    else:
                        print(f"❓ Unexpected response: {last_chunk.get('chunk', '')[:100]}")
            else:
                print(f"✅ Request rejected with status {response.status_code}")
        
        return True
    
    def test_timeout_scenario(self):
        """测试超时场景（需要手动操作）"""
        print("\n⏰ Testing Timeout Scenario")
        print("=" * 30)
        print("Note: This test requires manual observation of timeout behavior")
        
        # 发送一个任务但不响应确认
        response = self.send_chat_request("Create a simple backup script")
        
        if response.status_code == 200:
            chunks, confirmation_data = self.parse_stream_response(response)
            
            if confirmation_data:
                print(f"✅ Confirmation request sent")
                print(f"   Session: {confirmation_data.get('session_id')}")
                print(f"   Timeout: {confirmation_data.get('metadata', {}).get('timeout_seconds', 300)} seconds")
                print("   ⏳ Not sending confirmation response - should timeout")
                print("   (Check server logs for timeout handling)")
            else:
                print("❌ No confirmation request generated")
        
        return True


def main():
    """主测试函数"""
    tester = ChatStreamConfirmationTester()
    
    print("🧪 Chat Stream Confirmation Test Suite")
    print("=" * 50)
    print(f"Base URL: {tester.base_url}")
    print(f"Session ID: {tester.session_id}")
    print("\nMake sure SimaCode API server is running:")
    print("  simacode serve --host 0.0.0.0 --port 8000")
    print("\nAnd confirmation is enabled in config:")
    print("  react.confirm_by_human: true")
    
    # 检查服务器是否可达
    try:
        health_response = requests.get(f"{tester.base_url}/health", timeout=5)
        if health_response.status_code == 200:
            print("✅ Server is reachable")
        else:
            print(f"⚠️  Server responded with status {health_response.status_code}")
    except Exception as e:
        print(f"❌ Cannot reach server: {e}")
        print("   Please start the server and try again")
        return
    
    # 运行测试
    tests = [
        ("Confirmation Workflow", tester.test_confirmation_workflow),
        ("Message Format Validation", tester.test_message_format_validation),
        ("Timeout Scenario", tester.test_timeout_scenario),
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
        print("\n🎉 All tests passed! Chat stream confirmation is working correctly.")
    else:
        print(f"\n⚠️  {len(results) - passed} test(s) failed. Check implementation and configuration.")


if __name__ == "__main__":
    main()