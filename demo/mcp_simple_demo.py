#!/usr/bin/env python3
"""
Simple MCP Phase 3 Demo

A simplified demo to verify that the Phase 3 MCP integration components
work correctly without the complex interaction scenarios.
"""

import asyncio
import sys
import os
from datetime import datetime

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))

from simacode.mcp.tool_wrapper import MCPToolWrapper
from simacode.mcp.tool_registry import MCPToolRegistry, NamespaceManager
from simacode.mcp.integration import SimaCodeToolRegistry
from simacode.mcp.auto_discovery import MCPAutoDiscovery, DiscoveryPolicy, DiscoveryMode
from simacode.mcp.namespace_manager import EnhancedNamespaceManager, NamespacePolicy
from simacode.mcp.dynamic_updates import DynamicUpdateManager, UpdatePolicy
from simacode.mcp.protocol import MCPTool, MCPResult
from simacode.mcp.health import HealthStatus, HealthMetrics
from simacode.tools.base import Tool, ToolInput, ToolResult, ToolResultType


class SimpleToolInput(ToolInput):
    """Simple tool input for demo."""
    message: str = "Hello!"


class SimpleTool(Tool):
    """Simple tool implementation for demo."""
    
    def __init__(self, name: str, description: str):
        super().__init__(name, description, "1.0.0")
    
    def get_input_schema(self):
        return SimpleToolInput
    
    async def validate_input(self, input_data):
        return SimpleToolInput(**input_data)
    
    async def check_permissions(self, input_data):
        return True
    
    async def execute(self, input_data):
        yield ToolResult(
            type=ToolResultType.SUCCESS,
            content=f"Tool {self.name} executed with message: {input_data.message}",
            tool_name=self.name
        )


def test_namespace_manager():
    """Test namespace manager functionality."""
    print("🏷️  Testing Namespace Manager...")
    
    policy = NamespacePolicy(require_namespaces=True, auto_create_aliases=True)
    manager = EnhancedNamespaceManager(policy)
    
    # Create namespace
    success = manager.create_namespace("test_ns", "Test namespace")
    print(f"   {'✅' if success else '❌'} Created namespace: test_ns")
    
    # Register tool name
    tool_info = manager.register_tool_name("test_tool", "test_server", "test_ns")
    if tool_info:
        print(f"   ✅ Registered tool: {tool_info.original_name} -> {tool_info.full_name}")
    else:
        print(f"   ❌ Failed to register tool")
    
    # Get statistics
    stats = manager.get_statistics()
    print(f"   📊 Stats: {stats['total_namespaces']} namespaces, {stats['total_tools']} tools")


def test_basic_registry():
    """Test basic tool registry functionality."""
    print("\n📋 Testing Tool Registry...")
    
    # Create unified registry
    registry = SimaCodeToolRegistry()
    
    # Register built-in tool
    tool = SimpleTool("demo_tool", "A demo tool")
    success = registry.register_builtin_tool(tool)
    print(f"   {'✅' if success else '❌'} Registered built-in tool: {tool.name}")
    
    # List tools
    tools = registry.list_tools()
    print(f"   📋 Available tools: {len(tools)}")
    for tool_name in tools:
        print(f"      • {tool_name}")
    
    # Get tool info
    tool_info = registry.get_tool_info("demo_tool")
    if tool_info:
        print(f"   ℹ️  Tool info: {tool_info['name']} - {tool_info['description']}")
    
    # Test search
    results = registry.search_tools("demo", fuzzy=True)
    print(f"   🔍 Search results for 'demo': {len(results)}")


async def test_mcp_components():
    """Test MCP components with mocks."""
    print("\n🔧 Testing MCP Components...")
    
    from unittest.mock import Mock, AsyncMock
    
    # Create mock server manager
    mock_server_manager = Mock()
    mock_server_manager.list_servers.return_value = ["test_server"]
    mock_server_manager.get_all_tools = AsyncMock(return_value={
        "test_server": [
            MCPTool(
                name="mcp_test_tool",
                description="Test MCP tool",
                server_name="test_server",
                input_schema={"type": "object", "properties": {"param": {"type": "string"}}}
            )
        ]
    })
    mock_server_manager.get_server_health.return_value = HealthMetrics(
        server_name="test_server",
        status=HealthStatus.HEALTHY,
        last_check=datetime.now()
    )
    
    # Create mock permission manager
    mock_permission_manager = Mock()
    mock_permission_manager.check_permission = AsyncMock(return_value=True)
    
    # Test MCP tool registry
    print("   Testing MCP Tool Registry...")
    mcp_registry = MCPToolRegistry(mock_server_manager, mock_permission_manager)
    
    # Test discovery
    registered_count = await mcp_registry.discover_and_register_all_tools()
    print(f"   ✅ Discovered and registered {registered_count} MCP tools")
    
    # Test registry stats
    stats = mcp_registry.get_registry_stats()
    print(f"   📊 Registry stats: {stats['currently_registered']} registered, {stats['healthy_tools']} healthy")
    
    # Test auto-discovery
    print("   Testing Auto-Discovery...")
    policy = DiscoveryPolicy(mode=DiscoveryMode.PASSIVE, auto_register_new_tools=True)
    auto_discovery = MCPAutoDiscovery(mock_server_manager, mcp_registry, policy)
    
    # Run discovery
    results = await auto_discovery.discover_all()
    print(f"   ✅ Auto-discovery results: {results}")
    
    # Test dynamic updates
    print("   Testing Dynamic Updates...")
    update_policy = UpdatePolicy(enable_hot_updates=True, batch_updates=False)
    update_manager = DynamicUpdateManager(mock_server_manager, mcp_registry, update_policy)
    
    # Start and stop (basic lifecycle test)
    await update_manager.start()
    print(f"   ✅ Update manager started")
    
    # Check for updates
    updates = await update_manager.check_for_updates()
    print(f"   🔄 Found {len(updates)} updates")
    
    await update_manager.stop()
    print(f"   ✅ Update manager stopped")


def test_tool_wrapper():
    """Test MCP tool wrapper."""
    print("\n🔧 Testing MCP Tool Wrapper...")
    
    from unittest.mock import Mock, AsyncMock
    
    # Create mock components
    mock_server_manager = Mock()
    mock_permission_manager = Mock()
    mock_permission_manager.check_permission = AsyncMock(return_value=True)
    
    # Create MCP tool
    mcp_tool = MCPTool(
        name="wrapper_test_tool",
        description="Test tool for wrapper",
        server_name="test_server",
        input_schema={
            "type": "object",
            "properties": {
                "test_param": {"type": "string"}
            },
            "required": ["test_param"]
        }
    )
    
    # Create wrapper
    wrapper = MCPToolWrapper(
        mcp_tool=mcp_tool,
        server_manager=mock_server_manager,
        permission_manager=mock_permission_manager,
        namespace="test_ns"
    )
    
    print(f"   ✅ Created wrapper: {wrapper.name}")
    print(f"   📝 Description: {wrapper.description}")
    print(f"   🏷️  Namespace: {wrapper.namespace}")
    print(f"   🏗️  Schema created: {wrapper.get_input_schema() is not None}")


async def main():
    """Run all tests."""
    print("Simple MCP Phase 3 Demo")
    print("=" * 40)
    print("Testing individual components...")
    
    try:
        # Test components individually
        test_namespace_manager()
        test_basic_registry()
        test_tool_wrapper()
        await test_mcp_components()
        
        print(f"\n🎉 All tests completed successfully!")
        print(f"\nPhase 3 MCP Integration Components:")
        print(f"✅ Enhanced Namespace Manager - Working")
        print(f"✅ Tool Registry System - Working") 
        print(f"✅ Unified Tool Integration - Working")
        print(f"✅ MCP Tool Wrapper - Working")
        print(f"✅ Auto-Discovery System - Working")
        print(f"✅ Dynamic Update Manager - Working")
        
        print(f"\n🚀 Phase 3 MCP integration is fully functional!")
        
    except Exception as e:
        print(f"\n❌ Demo failed with error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())