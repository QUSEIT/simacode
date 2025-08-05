#!/usr/bin/env python3
"""
标准客户端示例 - 按照设计文档规范实现

展示如何正确使用 /api/v1/chat/stream 接口进行确认交互
"""

import asyncio
import json
import sys
from pathlib import Path
import logging
import requests
import time
from typing import Dict, Any, Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StandardChatStreamClient:
    """
    标准chat stream客户端 - 按照设计文档实现
    支持完整的确认交互流程
    """
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        
    def send_task_with_confirmation(self, task: str, session_id: str) -> bool:
        """
        发送任务并处理确认流程
        
        Args:
            task: 要执行的任务
            session_id: 会话ID
            
        Returns:
            是否成功完成
        """
        logger.info(f"发送任务: {task}")
        logger.info(f"会话ID: {session_id}")
        
        try:
            # 发送初始任务
            response = requests.post(
                f'{self.base_url}/api/v1/chat/stream',
                json={
                    'message': task,
                    'session_id': session_id
                },
                stream=True,
                timeout=300
            )
            
            if response.status_code != 200:
                logger.error(f"请求失败: {response.status_code} - {response.text}")
                return False
            
            # 处理流式响应
            return self._process_stream_response(response, session_id)
            
        except Exception as e:
            logger.error(f"任务执行失败: {e}")
            return False
    
    def _process_stream_response(self, response, session_id: str) -> bool:
        """处理流式响应"""
        
        for line in response.iter_lines(decode_unicode=True):
            if not line.startswith('data: '):
                continue
                
            try:
                chunk_data = json.loads(line[6:])
                chunk_type = chunk_data.get('chunk_type', 'content')
                
                logger.info(f"收到chunk: {chunk_type}")
                
                if chunk_type == 'confirmation_request':
                    # 处理确认请求
                    if not self._handle_confirmation_request(chunk_data, session_id):
                        return False
                        
                elif chunk_type == 'confirmation_received':
                    logger.info(f"✅ {chunk_data.get('chunk', '')}")
                    
                elif chunk_type == 'task_replanned':
                    logger.info(f"🔄 {chunk_data.get('chunk', '')}")
                    
                elif chunk_type == 'error':
                    logger.error(f"❌ {chunk_data.get('chunk', '')}")
                    return False
                    
                elif chunk_type == 'completion':
                    logger.info("🎉 任务完成!")
                    return True
                    
                else:
                    # 其他类型的chunk
                    content = chunk_data.get('chunk', '')
                    if content.strip():
                        logger.info(f"[{chunk_type}] {content}")
                
                # 检查是否完成
                if chunk_data.get('finished', False):
                    break
                    
            except json.JSONDecodeError as e:
                logger.warning(f"解析chunk失败: {e} - {line}")
                continue
        
        return True
    
    def _handle_confirmation_request(self, chunk_data: Dict[str, Any], session_id: str) -> bool:
        """
        处理确认请求
        
        Args:
            chunk_data: 确认请求数据
            session_id: 会话ID
            
        Returns:
            是否成功处理
        """
        confirmation_data = chunk_data.get('confirmation_data', {})
        tasks = confirmation_data.get('tasks', [])
        
        logger.info("🔔 收到确认请求:")
        logger.info(f"   会话: {session_id}")
        logger.info(f"   任务数量: {len(tasks)}")
        logger.info(f"   风险级别: {confirmation_data.get('risk_level', 'unknown')}")
        logger.info(f"   超时时间: {confirmation_data.get('timeout_seconds', 300)}秒")
        
        # 显示任务列表
        logger.info("   任务详情:")
        for task in tasks:
            logger.info(f"     {task.get('index', '?')}. {task.get('description', '未知任务')}")
            logger.info(f"        工具: {task.get('tool', 'unknown')}")
        
        # 获取用户输入
        print("\\n🤔 请选择操作:")
        print("   1. 确认执行 (confirm)")
        print("   2. 修改任务 (modify)")
        print("   3. 取消执行 (cancel)")
        
        try:
            choice = input("请输入选择 (1/2/3): ").strip()
            
            if choice == '1':
                return self._send_confirmation(session_id, 'confirm')
            elif choice == '2':
                modification = input("请输入修改建议: ").strip()
                return self._send_confirmation(session_id, 'modify', modification)
            elif choice == '3':
                return self._send_confirmation(session_id, 'cancel')
            else:
                logger.warning("无效选择，取消任务")
                return self._send_confirmation(session_id, 'cancel')
                
        except (KeyboardInterrupt, EOFError):
            logger.info("\n用户中断，取消任务")
            return self._send_confirmation(session_id, 'cancel')
    
    def _send_confirmation(self, session_id: str, action: str, user_message: str = None) -> bool:
        """
        发送确认响应
        
        Args:
            session_id: 会话ID
            action: 确认动作 (confirm, modify, cancel)
            user_message: 用户消息（修改建议等）
            
        Returns:
            是否成功发送
        """
        # 按照设计文档格式构造确认消息
        message = f"CONFIRM_ACTION:{action}"
        if user_message:
            message += f":{user_message}"
        
        logger.info(f"发送确认响应: {message}")
        
        try:
            response = requests.post(
                f'{self.base_url}/api/v1/chat/stream',
                json={
                    'message': message,
                    'session_id': session_id
                },
                stream=True,
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"确认响应失败: {response.status_code} - {response.text}")
                return False
            
            # 处理确认响应
            for line in response.iter_lines(decode_unicode=True):
                if line.startswith('data: '):
                    try:
                        chunk_data = json.loads(line[6:])
                        chunk_type = chunk_data.get('chunk_type', 'content')
                        
                        if chunk_type == 'confirmation_received':
                            logger.info(f"✅ 确认已接收: {chunk_data.get('chunk', '')}")
                            return True
                        elif chunk_type == 'error':
                            logger.error(f"❌ 确认失败: {chunk_data.get('chunk', '')}")
                            return False
                            
                    except json.JSONDecodeError:
                        continue
            
            return True
            
        except Exception as e:
            logger.error(f"发送确认响应失败: {e}")
            return False


def demonstrate_standard_workflow():
    """演示标准工作流程"""
    
    print("🚀 标准Chat Stream确认客户端演示")
    print("=" * 50)
    
    client = StandardChatStreamClient()
    
    # 检查服务器连接
    try:
        health_response = requests.get(f"{client.base_url}/health", timeout=5)
        if health_response.status_code == 200:
            print("✅ 服务器连接正常")
        else:
            print(f"⚠️  服务器状态异常: {health_response.status_code}")
    except Exception as e:
        print(f"❌ 无法连接到服务器: {e}")
        print("   请确保SimaCode API服务器正在运行:")
        print("   simacode serve --host 0.0.0.0 --port 8000")
        return
    
    # 测试任务列表
    test_tasks = [
        "创建一个Python项目的自动化测试框架",
        "实现文件备份和同步系统",
        "开发用户认证和权限管理模块",
        "构建数据分析和可视化工具"
    ]
    
    print(f"\n📋 可用测试任务:")
    for i, task in enumerate(test_tasks, 1):
        print(f"   {i}. {task}")
    
    try:
        choice = input(f"\n请选择任务 (1-{len(test_tasks)}) 或输入自定义任务: ").strip()
        
        if choice.isdigit() and 1 <= int(choice) <= len(test_tasks):
            selected_task = test_tasks[int(choice) - 1]
        else:
            selected_task = choice if choice else test_tasks[0]
        
        session_id = f"demo-{int(time.time())}"
        
        print(f"\n🎯 执行任务: {selected_task}")
        print(f"📋 会话ID: {session_id}")
        print("\n开始执行...\n")
        
        # 执行任务
        success = client.send_task_with_confirmation(selected_task, session_id)
        
        if success:
            print("\n🎉 任务执行成功完成!")
        else:
            print("\n❌ 任务执行失败或被取消")
            
    except (KeyboardInterrupt, EOFError):
        print("\n👋 演示被用户中断")
    except Exception as e:
        print(f"\n💥 演示过程中出现错误: {e}")


def demonstrate_message_formats():
    """演示消息格式"""
    
    print("\n📨 标准消息格式演示")
    print("=" * 30)
    
    # 确认请求格式示例
    confirmation_request_example = {
        "chunk": "请确认执行以下3个任务:\n1. 创建备份脚本\n2. 配置定时任务\n3. 测试备份功能",
        "session_id": "sess-123",
        "finished": False,
        "chunk_type": "confirmation_request",
        "confirmation_data": {
            "tasks": [
                {"index": 1, "description": "创建备份脚本", "tool": "file_write"},
                {"index": 2, "description": "配置定时任务", "tool": "bash"},
                {"index": 3, "description": "测试备份功能", "tool": "bash"}
            ],
            "options": ["confirm", "modify", "cancel"],
            "timeout_seconds": 300,
            "confirmation_round": 1,
            "risk_level": "medium"
        },
        "requires_response": True,
        "stream_paused": True
    }
    
    print("📥 确认请求格式 (服务器 -> 客户端):")
    print(json.dumps(confirmation_request_example, indent=2, ensure_ascii=False))
    
    # 确认响应格式示例
    confirmation_responses = [
        {"message": "CONFIRM_ACTION:confirm", "session_id": "sess-123"},
        {"message": "CONFIRM_ACTION:modify:请添加错误处理和日志记录", "session_id": "sess-123"},
        {"message": "CONFIRM_ACTION:cancel", "session_id": "sess-123"}
    ]
    
    print("\n📤 确认响应格式 (客户端 -> 服务器):")
    for i, response in enumerate(confirmation_responses, 1):
        print(f"   {i}. {json.dumps(response, ensure_ascii=False)}")


if __name__ == "__main__":
    try:
        demonstrate_message_formats()
        demonstrate_standard_workflow()
        
    except KeyboardInterrupt:
        print("\n👋 程序被用户中断")
    except Exception as e:
        print(f"\n💥 程序执行失败: {e}")
        sys.exit(1)