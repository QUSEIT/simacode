"""
Phase 3 Integration Tests for MCP Tool System

This module provides comprehensive integration tests for Phase 3 MCP development,
covering tool wrapper functionality, registry system, unified integration,
auto-discovery, namespace management, and dynamic updates.
"""

import asyncio
import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta
from typing import Dict, List, Any

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from simacode.mcp.tool_wrapper import MCPToolWrapper, MCPToolInput
from simacode.mcp.tool_registry import MCPToolRegistry, NamespaceManager
from simacode.mcp.integration import SimaCodeToolRegistry
from simacode.mcp.auto_discovery import MCPAutoDiscovery, DiscoveryPolicy, DiscoveryMode
from simacode.mcp.namespace_manager import EnhancedNamespaceManager, NamespacePolicy, ConflictResolution
from simacode.mcp.dynamic_updates import DynamicUpdateManager, UpdatePolicy, UpdateType, UpdatePriority, ToolUpdate
from simacode.mcp.protocol import MCPTool
from simacode.mcp.health import HealthStatus, HealthMetrics
from simacode.tools.base import Tool, ToolInput, ToolResult
from simacode.permissions import PermissionManager


# Test fixtures and helpers
@pytest.fixture
def mock_server_manager():
    """Mock MCP server manager for testing."""
    manager = Mock()
    manager.list_servers.return_value = ["test_server_1", "test_server_2"]
    manager.get_server_health.return_value = HealthMetrics(
        server_name="test_server",
        status=HealthStatus.HEALTHY,
        last_check=datetime.now()
    )
    manager.get_all_tools = AsyncMock(return_value={
        "test_server_1": [
            MCPTool(
                name="file_reader",
                description="Read files from filesystem",
                server_name="test_server_1",
                input_schema={
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"}
                    },
                    "required": ["file_path"]
                }
            ),
            MCPTool(
                name="data_processor",
                description="Process data with various algorithms",
                server_name="test_server_1",
                input_schema={
                    "type": "object",
                    "properties": {
                        "data": {"type": "array"},
                        "algorithm": {"type": "string"}
                    },
                    "required": ["data"]
                }
            )
        ],
        "test_server_2": [
            MCPTool(
                name="web_scraper",
                description="Scrape web pages for content",
                server_name="test_server_2",
                input_schema={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "selector": {"type": "string"}
                    },
                    "required": ["url"]
                }
            )
        ]
    })
    manager.call_tool = AsyncMock(return_value={"success": True, "result": "test_result"})
    return manager


@pytest.fixture
def mock_permission_manager():
    """Mock permission manager for testing."""
    manager = Mock(spec=PermissionManager)
    manager.check_permission = AsyncMock(return_value=True)
    manager.request_permission = AsyncMock(return_value=True)
    return manager


@pytest.fixture
def sample_mcp_tool():
    """Sample MCP tool for testing."""
    return MCPTool(
        name="test_tool",
        description="A test tool for unit testing",
        server_name="test_server",
        input_schema={
            "type": "object",
            "properties": {
                "input_text": {"type": "string", "description": "Text to process"},
                "options": {"type": "object", "description": "Processing options"}
            },
            "required": ["input_text"]
        }
    )


class TestMCPToolWrapper:
    """Test suite for MCP Tool Wrapper functionality."""
    
    @pytest.mark.asyncio
    async def test_tool_wrapper_creation(self, sample_mcp_tool, mock_server_manager, mock_permission_manager):
        """Test MCP tool wrapper creation and initialization."""
        wrapper = MCPToolWrapper(
            mcp_tool=sample_mcp_tool,
            server_manager=mock_server_manager,
            permission_manager=mock_permission_manager,
            namespace="test_namespace"
        )
        
        assert wrapper.name == "test_namespace:test_tool"
        assert wrapper.description == "A test tool for unit testing"
        assert wrapper.server_name == "test_server"
        assert wrapper.namespace == "test_namespace"
        assert wrapper.version == "1.0.0"
    
    @pytest.mark.asyncio
    async def test_tool_wrapper_execution(self, sample_mcp_tool, mock_server_manager, mock_permission_manager):
        """Test MCP tool wrapper execution."""
        wrapper = MCPToolWrapper(
            mcp_tool=sample_mcp_tool,
            server_manager=mock_server_manager,
            permission_manager=mock_permission_manager
        )
        
        # Mock successful execution
        mock_server_manager.call_tool.return_value = {
            "type": "success",
            "content": "Tool executed successfully",
            "metadata": {"execution_time": 0.1}
        }
        
        input_data = MCPToolInput(input_text="Hello, world!")
        results = []
        
        async for result in wrapper.execute(input_data):
            results.append(result)
        
        assert len(results) == 1
        assert results[0].type == "success"
        assert "Tool executed successfully" in results[0].content
        
        # Verify server manager was called correctly
        mock_server_manager.call_tool.assert_called_once_with(
            "test_server",
            "test_tool", 
            {"input_text": "Hello, world!"}
        )
    
    @pytest.mark.asyncio
    async def test_tool_wrapper_permission_check(self, sample_mcp_tool, mock_server_manager, mock_permission_manager):
        """Test permission checking in tool wrapper."""
        wrapper = MCPToolWrapper(
            mcp_tool=sample_mcp_tool,
            server_manager=mock_server_manager,
            permission_manager=mock_permission_manager
        )
        
        input_data = MCPToolInput(input_text="test")
        
        # Test permission granted
        mock_permission_manager.check_permission.return_value = True
        has_permission = await wrapper.check_permissions(input_data)
        assert has_permission is True
        
        # Test permission denied
        mock_permission_manager.check_permission.return_value = False
        has_permission = await wrapper.check_permissions(input_data)
        assert has_permission is False
    
    @pytest.mark.asyncio
    async def test_tool_wrapper_error_handling(self, sample_mcp_tool, mock_server_manager, mock_permission_manager):
        """Test error handling in tool wrapper."""
        wrapper = MCPToolWrapper(
            mcp_tool=sample_mcp_tool,
            server_manager=mock_server_manager,
            permission_manager=mock_permission_manager
        )
        
        # Mock server error
        mock_server_manager.call_tool.side_effect = Exception("Server connection failed")
        
        input_data = MCPToolInput(input_text="test")
        results = []
        
        async for result in wrapper.execute(input_data):
            results.append(result)
        
        assert len(results) == 1
        assert results[0].type == "error"
        assert "Server connection failed" in results[0].content


class TestMCPToolRegistry:
    """Test suite for MCP Tool Registry functionality."""
    
    @pytest.mark.asyncio
    async def test_registry_initialization(self, mock_server_manager, mock_permission_manager):
        """Test MCP tool registry initialization."""
        registry = MCPToolRegistry(
            server_manager=mock_server_manager,
            permission_manager=mock_permission_manager,
            auto_register=True
        )
        
        assert registry.server_manager == mock_server_manager
        assert registry.permission_manager == mock_permission_manager
        assert registry.auto_register is True
        assert len(registry.registered_tools) == 0
        assert isinstance(registry.namespace_manager, NamespaceManager)
    
    @pytest.mark.asyncio
    async def test_tool_registration(self, mock_server_manager, mock_permission_manager):
        """Test tool registration process."""
        registry = MCPToolRegistry(
            server_manager=mock_server_manager,
            permission_manager=mock_permission_manager
        )
        
        # Register tools from server
        tools = await mock_server_manager.get_all_tools()
        server1_tools = tools["test_server_1"]
        
        registered_count = await registry.register_server_tools("test_server_1", server1_tools)
        
        assert registered_count == 2
        assert len(registry.registered_tools) == 2
        assert "test_server_1" in registry.server_tools
        assert len(registry.server_tools["test_server_1"]) == 2
    
    @pytest.mark.asyncio
    async def test_namespace_management(self, mock_server_manager, mock_permission_manager):
        """Test namespace management in registry."""
        registry = MCPToolRegistry(
            server_manager=mock_server_manager,
            permission_manager=mock_permission_manager
        )
        
        tools = await mock_server_manager.get_all_tools()
        await registry.register_server_tools("test_server_1", tools["test_server_1"])
        
        # Check namespace creation
        namespaces = registry.namespace_manager.list_namespaces()
        assert len(namespaces) >= 1
        assert any("test_server_1" in ns for ns in namespaces)
        
        # Check tool naming
        registered_names = registry.list_registered_tools()
        assert any(":" in name for name in registered_names)  # Should have namespace prefixes
    
    @pytest.mark.asyncio
    async def test_tool_unregistration(self, mock_server_manager, mock_permission_manager):
        """Test tool unregistration process."""
        registry = MCPToolRegistry(
            server_manager=mock_server_manager,
            permission_manager=mock_permission_manager
        )
        
        # Register tools first
        tools = await mock_server_manager.get_all_tools()
        await registry.register_server_tools("test_server_1", tools["test_server_1"])
        
        initial_count = len(registry.registered_tools)
        assert initial_count == 2
        
        # Unregister server tools
        unregistered_count = await registry.unregister_server_tools("test_server_1")
        
        assert unregistered_count == 2
        assert len(registry.registered_tools) == 0
        assert "test_server_1" not in registry.server_tools
    
    @pytest.mark.asyncio
    async def test_auto_discovery_and_registration(self, mock_server_manager, mock_permission_manager):
        """Test automatic discovery and registration."""
        registry = MCPToolRegistry(
            server_manager=mock_server_manager,
            permission_manager=mock_permission_manager,
            auto_register=True
        )
        
        registered_count = await registry.discover_and_register_all_tools()
        
        assert registered_count == 3  # 2 from server1 + 1 from server2
        assert len(registry.registered_tools) == 3
        assert len(registry.server_tools) == 2


class TestSimaCodeToolRegistry:
    """Test suite for SimaCode Tool Registry Integration."""
    
    def test_registry_initialization(self, mock_permission_manager):
        """Test unified tool registry initialization."""
        registry = SimaCodeToolRegistry(permission_manager=mock_permission_manager)
        
        assert registry.permission_manager == mock_permission_manager
        assert len(registry.builtin_tools) == 0
        assert registry.mcp_enabled is False
        assert registry.mcp_server_manager is None
        assert registry.mcp_tool_registry is None
    
    def test_builtin_tool_registration(self, mock_permission_manager):
        """Test built-in tool registration."""
        registry = SimaCodeToolRegistry(permission_manager=mock_permission_manager)
        
        # Create mock built-in tool
        builtin_tool = Mock(spec=Tool)
        builtin_tool.name = "test_builtin_tool"
        builtin_tool.description = "Test built-in tool"
        builtin_tool.version = "1.0.0"
        builtin_tool.metadata = {}
        
        # Register tool
        success = registry.register_builtin_tool(builtin_tool)
        
        assert success is True
        assert "test_builtin_tool" in registry.builtin_tools
        assert registry.get_tool("test_builtin_tool") == builtin_tool
    
    @pytest.mark.asyncio
    async def test_mcp_integration_initialization(self, mock_permission_manager):
        """Test MCP integration initialization."""
        registry = SimaCodeToolRegistry(permission_manager=mock_permission_manager)
        
        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            config_content = """
servers:
  test_server:
    command: ["python", "-m", "test_mcp_server"]
    args: ["--port", "3000"]
    env:
      TEST_ENV: "value"
    working_directory: "/tmp"
"""
            f.write(config_content)
            config_path = Path(f.name)
        
        try:
            # Mock the MCP components
            with patch('simacode.mcp.integration.MCPServerManager') as mock_server_manager_class, \
                 patch('simacode.mcp.integration.MCPToolRegistry') as mock_tool_registry_class:
                
                mock_server_manager = Mock()
                mock_server_manager.start = AsyncMock()
                mock_server_manager_class.return_value = mock_server_manager
                
                mock_tool_registry = Mock()
                mock_tool_registry.start = AsyncMock()
                mock_tool_registry.add_registration_callback = Mock()
                mock_tool_registry.add_unregistration_callback = Mock()
                mock_tool_registry_class.return_value = mock_tool_registry
                
                # Test initialization
                success = await registry.initialize_mcp(config_path)
                
                assert success is True
                assert registry.mcp_enabled is True
                assert registry.mcp_server_manager is not None
                assert registry.mcp_tool_registry is not None
        
        finally:
            config_path.unlink()
    
    def test_tool_search_functionality(self, mock_permission_manager):
        """Test tool search across built-in and MCP tools."""
        registry = SimaCodeToolRegistry(permission_manager=mock_permission_manager)
        
        # Add some built-in tools
        builtin_tool1 = Mock(spec=Tool)
        builtin_tool1.name = "file_reader"
        builtin_tool1.description = "Read files from filesystem"
        
        builtin_tool2 = Mock(spec=Tool)
        builtin_tool2.name = "data_processor"
        builtin_tool2.description = "Process data with algorithms"
        
        registry.register_builtin_tool(builtin_tool1)
        registry.register_builtin_tool(builtin_tool2)
        
        # Test search
        results = registry.search_tools("file", fuzzy=False)
        
        assert len(results) >= 1
        assert any(r["tool_name"] == "file_reader" for r in results)
        
        # Test fuzzy search
        results = registry.search_tools("reader", fuzzy=True)
        assert len(results) >= 1


class TestAutoDiscovery:
    """Test suite for Auto Discovery functionality."""
    
    @pytest.mark.asyncio
    async def test_auto_discovery_initialization(self, mock_server_manager, mock_permission_manager):
        """Test auto discovery system initialization."""
        registry = MCPToolRegistry(mock_server_manager, mock_permission_manager)
        
        policy = DiscoveryPolicy(
            mode=DiscoveryMode.ACTIVE,
            discovery_interval=60,
            auto_register_new_tools=True
        )
        
        auto_discovery = MCPAutoDiscovery(mock_server_manager, registry, policy)
        
        assert auto_discovery.policy.mode == DiscoveryMode.ACTIVE
        assert auto_discovery.policy.discovery_interval == 60
        assert auto_discovery.policy.auto_register_new_tools is True
        assert auto_discovery.is_running is False
    
    @pytest.mark.asyncio
    async def test_tool_change_detection(self, mock_server_manager, mock_permission_manager):
        """Test detection of tool changes."""
        registry = MCPToolRegistry(mock_server_manager, mock_permission_manager)
        auto_discovery = MCPAutoDiscovery(mock_server_manager, registry)
        
        # Initial tools
        tools = await mock_server_manager.get_all_tools()
        initial_tools = tools["test_server_1"]
        
        # Simulate change detection
        changes = await auto_discovery._detect_tool_changes("test_server_1", initial_tools)
        
        # Should detect as all new tools
        assert len(changes["added"]) == len(initial_tools)
        assert len(changes["removed"]) == 0
        assert len(changes["updated"]) == 0
    
    @pytest.mark.asyncio
    async def test_discovery_events(self, mock_server_manager, mock_permission_manager):
        """Test discovery event recording and callbacks."""
        registry = MCPToolRegistry(mock_server_manager, mock_permission_manager)
        auto_discovery = MCPAutoDiscovery(mock_server_manager, registry)
        
        # Add event callback
        events_received = []
        
        def event_callback(event):
            events_received.append(event)
        
        auto_discovery.add_event_callback(event_callback)
        
        # Record an event
        auto_discovery._record_event("discovered", "test_tool", "test_server", {"details": "test"})
        
        assert len(events_received) == 1
        assert events_received[0].event_type == "discovered"
        assert events_received[0].tool_name == "test_tool"
        assert events_received[0].server_name == "test_server"


class TestEnhancedNamespaceManager:
    """Test suite for Enhanced Namespace Management."""
    
    def test_namespace_creation(self):
        """Test namespace creation and validation."""
        policy = NamespacePolicy(
            require_namespaces=True,
            max_namespace_depth=3
        )
        manager = EnhancedNamespaceManager(policy)
        
        # Create root namespace
        success = manager.create_namespace(
            "test_namespace",
            description="Test namespace for tools",
            server_name="test_server"
        )
        
        assert success is True
        assert "test_namespace" in manager.namespaces
        assert manager.namespaces["test_namespace"].server_name == "test_server"
    
    def test_tool_name_registration(self):
        """Test tool name registration with conflict resolution."""
        policy = NamespacePolicy(
            conflict_resolution=ConflictResolution.SUFFIX,
            auto_create_aliases=True
        )
        manager = EnhancedNamespaceManager(policy)
        
        # Register first tool
        tool_info1 = manager.register_tool_name(
            "file_reader",
            "server1",
            namespace="tools"
        )
        
        assert tool_info1 is not None
        assert tool_info1.full_name == "tools:file_reader"
        
        # Register conflicting tool
        tool_info2 = manager.register_tool_name(
            "file_reader", 
            "server2",
            namespace="tools"
        )
        
        assert tool_info2 is not None
        assert tool_info2.full_name != tool_info1.full_name  # Should be different due to conflict resolution
    
    def test_namespace_hierarchy(self):
        """Test hierarchical namespace management."""
        manager = EnhancedNamespaceManager()
        
        # Create parent namespace
        manager.create_namespace("parent", description="Parent namespace")
        
        # Create child namespace
        success = manager.create_namespace(
            "child",
            description="Child namespace",
            parent="parent"
        )
        
        assert success is True
        assert "child" in manager.namespaces["parent"].children
        assert manager.namespaces["child"].parent == "parent"
        
        # Test hierarchy retrieval
        hierarchy = manager.get_namespace_hierarchy("parent")
        assert hierarchy["name"] == "parent"
        assert "child" in hierarchy["children"]


class TestDynamicUpdates:
    """Test suite for Dynamic Update Management."""
    
    @pytest.mark.asyncio
    async def test_update_manager_initialization(self, mock_server_manager, mock_permission_manager):
        """Test dynamic update manager initialization."""
        registry = MCPToolRegistry(mock_server_manager, mock_permission_manager)
        
        policy = UpdatePolicy(
            enable_hot_updates=True,
            batch_updates=True,
            max_concurrent_updates=3
        )
        
        update_manager = DynamicUpdateManager(mock_server_manager, registry, policy)
        
        assert update_manager.policy.enable_hot_updates is True
        assert update_manager.policy.batch_updates is True
        assert update_manager.policy.max_concurrent_updates == 3
        assert update_manager.is_running is False
    
    @pytest.mark.asyncio
    async def test_update_detection(self, mock_server_manager, mock_permission_manager):
        """Test update detection and processing."""
        registry = MCPToolRegistry(mock_server_manager, mock_permission_manager)
        update_manager = DynamicUpdateManager(mock_server_manager, registry)
        
        # Initialize version tracking
        await update_manager._initialize_version_tracking()
        
        # Check for updates
        updates = await update_manager.check_for_updates()
        
        # Should detect some changes (depending on mock setup)
        assert isinstance(updates, list)
    
    @pytest.mark.asyncio
    async def test_update_queue_and_processing(self, mock_server_manager, mock_permission_manager):
        """Test update queuing and processing."""
        registry = MCPToolRegistry(mock_server_manager, mock_permission_manager)
        update_manager = DynamicUpdateManager(mock_server_manager, registry)
        
        # Create test update
        update = ToolUpdate(
            update_type=UpdateType.ADDITION,
            tool_name="new_tool",
            server_name="test_server",
            priority=UpdatePriority.NORMAL,
            new_version={"name": "new_tool", "description": "A new tool"}
        )
        
        # Queue update
        update_id = await update_manager.queue_update(update)
        
        assert update_id is not None
        assert update_id in update_manager.pending_updates
        assert update_manager.pending_updates[update_id] == update


class TestEndToEndIntegration:
    """End-to-end integration tests for the complete MCP system."""
    
    @pytest.mark.asyncio
    async def test_complete_mcp_lifecycle(self, mock_server_manager, mock_permission_manager):
        """Test complete MCP tool lifecycle from discovery to execution."""
        # Initialize unified registry
        unified_registry = SimaCodeToolRegistry(mock_permission_manager)
        
        # Mock MCP initialization (simplified for testing)
        unified_registry.mcp_enabled = True
        unified_registry.mcp_server_manager = mock_server_manager
        
        # Create and initialize MCP tool registry
        mcp_registry = MCPToolRegistry(mock_server_manager, mock_permission_manager, auto_register=True)
        unified_registry.mcp_tool_registry = mcp_registry
        
        # Discover and register tools
        registered_count = await mcp_registry.discover_and_register_all_tools()
        
        assert registered_count > 0
        
        # List all tools
        all_tools = unified_registry.list_tools()
        assert len(all_tools) > 0
        
        # Get tool info
        first_tool = all_tools[0]
        tool_info = unified_registry.get_tool_info(first_tool)
        assert tool_info is not None
        assert "type" in tool_info
        
        # Test tool search
        search_results = unified_registry.search_tools("file")
        assert len(search_results) >= 0
    
    @pytest.mark.asyncio
    async def test_namespace_and_conflict_management(self, mock_server_manager, mock_permission_manager):
        """Test namespace management and conflict resolution in integrated system."""
        # Create two registries with same tool names
        registry1 = MCPToolRegistry(mock_server_manager, mock_permission_manager)
        
        # Simulate tools with same names from different servers
        tools_server1 = [
            MCPTool(
                name="common_tool",
                description="Tool from server 1",
                server_name="server1",
                input_schema={"type": "object"}
            )
        ]
        
        tools_server2 = [
            MCPTool(
                name="common_tool",
                description="Tool from server 2", 
                server_name="server2",
                input_schema={"type": "object"}
            )
        ]
        
        # Register tools from both servers
        count1 = await registry1.register_server_tools("server1", tools_server1)
        count2 = await registry1.register_server_tools("server2", tools_server2)
        
        assert count1 == 1
        assert count2 == 1
        
        # Verify tools are registered with different namespaced names
        registered_tools = registry1.list_registered_tools()
        assert len(registered_tools) == 2
        
        # Both tools should have namespace prefixes
        namespaced_tools = [name for name in registered_tools if ":" in name]
        assert len(namespaced_tools) == 2
    
    @pytest.mark.asyncio
    async def test_auto_discovery_with_dynamic_updates(self, mock_server_manager, mock_permission_manager):
        """Test auto-discovery integration with dynamic updates."""
        # Set up components
        registry = MCPToolRegistry(mock_server_manager, mock_permission_manager)
        auto_discovery = MCPAutoDiscovery(mock_server_manager, registry)
        update_manager = DynamicUpdateManager(mock_server_manager, registry)
        
        # Start systems
        await registry.start()
        await auto_discovery.start()
        await update_manager.start()
        
        try:
            # Wait for initial discovery
            await asyncio.sleep(0.1)
            
            # Check that tools were discovered
            assert len(registry.registered_tools) > 0
            
            # Get stats
            discovery_stats = auto_discovery.get_discovery_stats()
            update_stats = update_manager.get_update_stats()
            registry_stats = registry.get_registry_stats()
            
            assert discovery_stats["is_running"] is True
            assert update_stats["is_running"] is True
            assert registry_stats["currently_registered"] > 0
            
        finally:
            # Clean up
            await update_manager.stop()
            await auto_discovery.stop()
            await registry.stop()


# Performance and stress tests
class TestPerformanceAndStress:
    """Performance and stress tests for MCP system."""
    
    @pytest.mark.asyncio
    async def test_large_scale_tool_registration(self, mock_server_manager, mock_permission_manager):
        """Test registration of large number of tools."""
        # Create mock server with many tools
        large_tool_set = []
        for i in range(100):
            tool = MCPTool(
                name=f"tool_{i}",
                description=f"Test tool number {i}",
                server_name="large_server",
                input_schema={"type": "object", "properties": {"param": {"type": "string"}}}
            )
            large_tool_set.append(tool)
        
        mock_server_manager.get_all_tools.return_value = {"large_server": large_tool_set}
        
        registry = MCPToolRegistry(mock_server_manager, mock_permission_manager)
        
        # Measure registration time
        start_time = datetime.now()
        registered_count = await registry.register_server_tools("large_server", large_tool_set)
        end_time = datetime.now()
        
        assert registered_count == 100
        assert len(registry.registered_tools) == 100
        
        # Should complete within reasonable time (less than 5 seconds)
        duration = (end_time - start_time).total_seconds()
        assert duration < 5.0
    
    @pytest.mark.asyncio
    async def test_concurrent_tool_operations(self, mock_server_manager, mock_permission_manager):
        """Test concurrent tool operations."""
        registry = MCPToolRegistry(mock_server_manager, mock_permission_manager)
        
        # Register initial tools
        tools = await mock_server_manager.get_all_tools()
        await registry.register_server_tools("test_server_1", tools["test_server_1"])
        
        # Perform concurrent operations
        tasks = []
        
        # Concurrent registrations
        for i in range(5):
            task = registry.register_server_tools(f"concurrent_server_{i}", tools["test_server_1"])
            tasks.append(task)
        
        # Concurrent unregistrations  
        for i in range(2):
            task = registry.unregister_server_tools("test_server_1")
            tasks.append(task)
        
        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Should handle concurrent operations without errors
        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0


if __name__ == "__main__":
    # Run tests with pytest
    import subprocess
    subprocess.run(["python", "-m", "pytest", __file__, "-v", "--tb=short"])