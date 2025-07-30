#!/usr/bin/env python3
"""
MCP Phase 1 测试脚本

这个脚本演示如何测试MCP协议基础实现的核心功能。
"""

import asyncio
import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from simacode.mcp.protocol import MCPMessage, MCPProtocol, MCPMethods
from simacode.mcp.connection import create_transport
from simacode.mcp.exceptions import MCPConnectionError, MCPProtocolError


async def test_message_creation():
    """测试MCP消息创建和序列化"""
    print("🧪 测试MCP消息创建...")
    
    # 测试请求消息
    request = MCPMessage(method="tools/list", params={"filter": "active"}, id="test_123")
    print(f"✅ 请求消息: {request.to_json()}")
    assert request.is_request()
    assert not request.is_notification()
    
    # 测试响应消息
    response = MCPMessage(id="123", result={"tools": []})
    print(f"✅ 响应消息: {response.to_json()}")
    assert response.is_response()
    assert not request.is_error()
    
    # 测试通知消息
    notification = MCPMessage(method="tools/changed", id=None)
    print(f"✅ 通知消息: {notification.to_json()}")
    assert notification.is_notification()
    
    # 测试错误消息
    error_msg = MCPMessage(id="456", error={"code": -32000, "message": "Tool not found"})
    print(f"✅ 错误消息: {error_msg.to_json()}")
    assert error_msg.is_error()
    
    print("✅ 消息创建测试通过\n")


async def test_protocol_serialization():
    """测试协议序列化和反序列化"""
    print("🧪 测试协议序列化...")
    
    original = MCPMessage(id="test_123", method="ping", params={"timestamp": 1234567890})
    
    # 序列化到JSON
    json_str = original.to_json()
    print(f"✅ 序列化JSON: {json_str}")
    
    # 从JSON反序列化
    deserialized = MCPMessage.from_json(json_str)
    print(f"✅ 反序列化成功: method={deserialized.method}, id={deserialized.id}")
    
    # 验证数据完整性
    assert deserialized.id == original.id
    assert deserialized.method == original.method
    assert deserialized.params == original.params
    
    print("✅ 协议序列化测试通过\n")


async def test_error_handling():
    """测试错误处理"""
    print("🧪 测试错误处理...")
    
    # 测试无效JSON
    try:
        MCPMessage.from_json('{"invalid": json}')
        assert False, "应该抛出异常"
    except MCPProtocolError as e:
        print(f"✅ 捕获无效JSON错误: {e}")
    
    # 测试无效JSON-RPC版本
    try:
        MCPMessage.from_dict({"jsonrpc": "1.0", "method": "test"})
        assert False, "应该抛出异常"
    except MCPProtocolError as e:
        print(f"✅ 捕获版本错误: {e}")
    
    print("✅ 错误处理测试通过\n")


class MockTransport:
    """用于测试的模拟传输层"""
    
    def __init__(self):
        self._connected = False
        self.sent_messages = []
        self.response_queue = []
    
    async def connect(self):
        self._connected = True
        return True
    
    async def disconnect(self):
        self._connected = False
    
    def is_connected(self):
        return self._connected
    
    async def send(self, data: bytes):
        if not self._connected:
            raise MCPConnectionError("Not connected")
        
        message_str = data.decode('utf-8')
        self.sent_messages.append(message_str)
        print(f"📤 发送消息: {message_str}")
    
    async def receive(self) -> bytes:
        if not self._connected:
            raise MCPConnectionError("Not connected")
        
        if self.response_queue:
            response = self.response_queue.pop(0)
            print(f"📥 接收消息: {response}")
            return response.encode('utf-8')
        
        # 默认响应
        response = MCPMessage(id="default", result={"status": "ok"})
        return response.to_json().encode('utf-8')
    
    def queue_response(self, response: MCPMessage):
        """队列一个响应消息"""
        self.response_queue.append(response.to_json())


async def test_protocol_communication():
    """测试协议通信"""
    print("🧪 测试协议通信...")
    
    # 创建模拟传输和协议
    transport = MockTransport()
    protocol = MCPProtocol(transport)
    
    # 连接
    await transport.connect()
    print("✅ 传输连接成功")
    
    # 测试发送消息
    test_msg = MCPMessage(method="ping", params={"test": True})
    await protocol.send_message(test_msg)
    print("✅ 消息发送成功")
    
    # 验证消息被发送
    assert len(transport.sent_messages) == 1
    sent_data = json.loads(transport.sent_messages[0])
    assert sent_data["method"] == "ping"
    assert sent_data["params"]["test"] is True
    
    # 测试接收消息
    received_msg = await protocol.receive_message()
    print(f"✅ 消息接收成功: {received_msg.result}")
    
    # 断开连接
    await transport.disconnect()
    print("✅ 传输断开成功")
    
    print("✅ 协议通信测试通过\n")


async def test_method_call():
    """测试方法调用"""
    print("🧪 测试方法调用...")
    
    transport = MockTransport()
    protocol = MCPProtocol(transport)
    await transport.connect()
    
    # 准备响应
    expected_result = {"tools": [{"name": "echo", "description": "Echo tool"}]}
    response = MCPMessage(id=None, result=expected_result)  # ID will be set by queue_response
    
    # 需要模拟正确的ID匹配
    async def mock_receive():
        # 获取最后发送的消息ID
        if transport.sent_messages:
            sent_msg = json.loads(transport.sent_messages[-1])
            response_with_id = MCPMessage(id=sent_msg["id"], result=expected_result)
            return response_with_id.to_json().encode('utf-8')
        return b'{"jsonrpc": "2.0", "id": "default", "result": {}}'
    
    transport.receive = mock_receive
    
    # 调用方法
    result = await protocol.call_method(MCPMethods.TOOLS_LIST)
    print(f"✅ 方法调用成功: {result}")
    
    # 验证结果
    assert result == expected_result
    
    print("✅ 方法调用测试通过\n")


async def test_notification():
    """测试通知发送"""
    print("🧪 测试通知发送...")
    
    transport = MockTransport()
    protocol = MCPProtocol(transport)
    await transport.connect()
    
    # 发送通知
    await protocol.send_notification("tools/changed", {"added": ["new_tool"]})
    print("✅ 通知发送成功")
    
    # 验证通知格式
    sent_data = json.loads(transport.sent_messages[0])
    assert sent_data["method"] == "tools/changed"
    assert sent_data["params"]["added"] == ["new_tool"]
    assert "id" not in sent_data  # 通知不应该有ID
    
    print("✅ 通知测试通过\n")


async def test_constants():
    """测试MCP常量"""
    print("🧪 测试MCP常量...")
    
    # 测试方法名常量
    assert MCPMethods.INITIALIZE == "initialize"
    assert MCPMethods.TOOLS_LIST == "tools/list"
    assert MCPMethods.TOOLS_CALL == "tools/call"
    assert MCPMethods.RESOURCES_LIST == "resources/list"
    print("✅ 方法名常量正确")
    
    # 测试错误码常量
    from simacode.mcp.protocol import MCPErrorCodes
    assert MCPErrorCodes.PARSE_ERROR == -32700
    assert MCPErrorCodes.METHOD_NOT_FOUND == -32601
    assert MCPErrorCodes.TOOL_NOT_FOUND == -32000
    print("✅ 错误码常量正确")
    
    print("✅ 常量测试通过\n")


async def main():
    """运行所有测试"""
    print("🚀 MCP Phase 1 协议基础测试开始\n")
    print("=" * 60)
    
    try:
        await test_message_creation()
        await test_protocol_serialization()
        await test_error_handling()
        await test_protocol_communication()
        await test_method_call()
        await test_notification()
        await test_constants()
        
        print("=" * 60)
        print("🎉 所有测试通过！MCP协议基础实现正常工作")
        print("\n📋 测试覆盖的功能:")
        print("  ✅ MCP消息创建和序列化")
        print("  ✅ JSON-RPC 2.0协议遵循")
        print("  ✅ 请求/响应/通知/错误消息类型")
        print("  ✅ 协议通信流程")
        print("  ✅ 方法调用机制")
        print("  ✅ 通知发送")
        print("  ✅ 错误处理")
        print("  ✅ 常量定义")
        
        print("\n🔄 下一步:")
        print("  - 实现MCP客户端核心 (client.py)")
        print("  - 与真实MCP服务器集成测试")
        print("  - 实现服务器管理和工具发现")
        
        return True
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)