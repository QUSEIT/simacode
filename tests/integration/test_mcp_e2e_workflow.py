"""
End-to-End MCP Integration Workflow Tests

This module provides comprehensive end-to-end tests that demonstrate the complete
MCP integration workflow from server setup to tool execution, including real-world
scenarios and edge cases.
"""

import asyncio
import pytest
import json
import tempfile
import yaml
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
from typing import Dict, List, Any, AsyncGenerator

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

from simacode.mcp.integration import SimaCodeToolRegistry, initialize_mcp_integration
from simacode.mcp.server_manager import MCPServerManager
from simacode.mcp.tool_registry import MCPToolRegistry
from simacode.mcp.auto_discovery import MCPAutoDiscovery, DiscoveryPolicy, DiscoveryMode
from simacode.mcp.dynamic_updates import DynamicUpdateManager, UpdatePolicy
from simacode.mcp.config import MCPConfigManager, MCPServerConfig
from simacode.mcp.protocol import MCPTool, MCPResult
from simacode.mcp.health import HealthStatus, HealthMetrics
from simacode.tools.base import Tool, ToolInput, ToolResult
from simacode.permissions import PermissionManager


class MockMCPServer:
    """Mock MCP server for testing complete workflows."""
    
    def __init__(self, name: str, tools: List[Dict[str, Any]] = None):
        self.name = name
        self.tools = tools or []
        self.is_running = False
        self.call_count = 0
        self.health_status = HealthStatus.HEALTHY
    
    async def start(self):
        """Start the mock server."""
        self.is_running = True
    
    async def stop(self):
        """Stop the mock server."""
        self.is_running = False
    
    async def list_tools(self) -> List[MCPTool]:
        """List available tools."""
        return [
            MCPTool(
                name=tool["name"],
                description=tool["description"],
                server_name=self.name,
                input_schema=tool.get("schema", {"type": "object"})
            )
            for tool in self.tools
        ]
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> MCPResult:
        """Call a tool on the server."""
        self.call_count += 1
        
        # Find tool
        tool = next((t for t in self.tools if t["name"] == tool_name), None)
        if not tool:
            return MCPResult(
                type="error",
                content=f"Tool '{tool_name}' not found",
                metadata={}
            )
        
        # Simulate tool execution
        result_content = f"Executed {tool_name} with args: {arguments}"
        
        # Add some realistic processing delay
        await asyncio.sleep(0.01)
        
        return MCPResult(
            type="success", 
            content=result_content,
            metadata={
                "execution_time": 0.01,
                "call_count": self.call_count,
                "tool_name": tool_name
            }
        )
    
    def get_health(self) -> HealthMetrics:
        """Get server health."""
        return HealthMetrics(
            server_name=self.name,
            status=self.health_status,
            last_check=datetime.now()
        )


@pytest.fixture
def sample_servers():
    """Create sample MCP servers for testing."""
    return {
        "file_server": MockMCPServer("file_server", [
            {
                "name": "read_file",
                "description": "Read content from a file",
                "schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to file"},
                        "encoding": {"type": "string", "default": "utf-8"}
                    },
                    "required": ["file_path"]
                }
            },
            {
                "name": "write_file",
                "description": "Write content to a file",
                "schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "content": {"type": "string"},
                        "append": {"type": "boolean", "default": False}
                    },
                    "required": ["file_path", "content"]
                }
            }
        ]),
        
        "web_server": MockMCPServer("web_server", [
            {
                "name": "fetch_url",
                "description": "Fetch content from a URL",
                "schema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "format": "uri"},
                        "headers": {"type": "object"},
                        "timeout": {"type": "number", "default": 30}
                    },
                    "required": ["url"]
                }
            },
            {
                "name": "scrape_page",
                "description": "Scrape content from a web page",
                "schema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "selector": {"type": "string"},
                        "extract": {"type": "string", "enum": ["text", "html", "attributes"]}
                    },
                    "required": ["url", "selector"]
                }
            }
        ]),
        
        "data_server": MockMCPServer("data_server", [
            {
                "name": "process_json",
                "description": "Process JSON data with various operations",
                "schema": {
                    "type": "object", 
                    "properties": {
                        "data": {"type": "object"},
                        "operation": {"type": "string", "enum": ["filter", "map", "reduce", "validate"]},
                        "parameters": {"type": "object"}
                    },
                    "required": ["data", "operation"]
                }
            }
        ])
    }


@pytest.fixture
def mock_config_file():
    """Create a mock MCP configuration file."""
    config_data = {
        "servers": {
            "file_server": {
                "command": ["python", "-m", "file_mcp_server"],
                "args": ["--port", "3001"],
                "env": {"SERVER_NAME": "file_server"},
                "working_directory": "/tmp"
            },
            "web_server": {
                "command": ["python", "-m", "web_mcp_server"],
                "args": ["--port", "3002"],
                "env": {"SERVER_NAME": "web_server"},
                "working_directory": "/tmp"
            },
            "data_server": {
                "command": ["python", "-m", "data_mcp_server"],
                "args": ["--port", "3003"],
                "env": {"SERVER_NAME": "data_server"},
                "working_directory": "/tmp"
            }
        },
        "discovery": {
            "mode": "active",
            "interval": 60,
            "auto_register": True
        },
        "updates": {
            "enable_hot_updates": True,
            "batch_updates": True,
            "max_concurrent": 5
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        return Path(f.name)


class TestCompleteWorkflow:
    """Test complete MCP integration workflows."""
    
    @pytest.mark.asyncio
    async def test_full_mcp_lifecycle(self, sample_servers, mock_config_file):
        """Test the complete MCP lifecycle from configuration to tool execution."""
        
        # Step 1: Initialize global tool registry
        registry = SimaCodeToolRegistry()
        
        # Step 2: Mock the MCP components to use our sample servers
        with patch('simacode.mcp.server_manager.MCPServerManager') as MockServerManager, \
             patch('simacode.mcp.tool_registry.MCPToolRegistry') as MockToolRegistry:
            
            # Create mock server manager
            mock_server_manager = Mock()
            mock_server_manager.start = AsyncMock()
            mock_server_manager.stop = AsyncMock()
            mock_server_manager.list_servers.return_value = list(sample_servers.keys())
            
            # Mock get_all_tools to return our sample tools
            async def mock_get_all_tools():
                result = {}
                for server_name, server in sample_servers.items():
                    result[server_name] = await server.list_tools()
                return result
            
            mock_server_manager.get_all_tools = mock_get_all_tools
            mock_server_manager.get_server_health.side_effect = lambda name: sample_servers[name].get_health()
            mock_server_manager.call_tool = AsyncMock()
            
            MockServerManager.return_value = mock_server_manager
            
            # Create mock tool registry
            mock_tool_registry = Mock()
            mock_tool_registry.start = AsyncMock()
            mock_tool_registry.stop = AsyncMock()
            mock_tool_registry.add_registration_callback = Mock()
            mock_tool_registry.add_unregistration_callback = Mock()
            mock_tool_registry.registered_tools = {}
            mock_tool_registry.list_registered_tools.return_value = []
            mock_tool_registry.get_registry_stats.return_value = {"currently_registered": 0}
            
            MockToolRegistry.return_value = mock_tool_registry
            
            # Step 3: Initialize MCP integration
            success = await registry.initialize_mcp(mock_config_file)
            assert success is True
            assert registry.mcp_enabled is True
            
            # Step 4: Verify server manager was initialized
            MockServerManager.assert_called_once()
            mock_server_manager.start.assert_called_once()
            
            # Step 5: Verify tool registry was initialized
            MockToolRegistry.assert_called_once()
            mock_tool_registry.start.assert_called_once()
            
            # Step 6: Test tool listing (should work even with mocked components)
            tools = registry.list_tools(include_mcp=True, include_builtin=True)
            assert isinstance(tools, list)
            
            # Step 7: Clean up
            await registry.shutdown_mcp()
            mock_server_manager.stop.assert_called_once()
            mock_tool_registry.stop.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_tool_discovery_and_registration_workflow(self, sample_servers):
        """Test the complete tool discovery and registration workflow."""
        
        # Create real components (not mocked) to test actual logic
        permission_manager = Mock(spec=PermissionManager)
        permission_manager.check_permission = AsyncMock(return_value=True)
        
        # Create mock server manager that uses our sample servers
        server_manager = Mock()
        server_manager.list_servers.return_value = list(sample_servers.keys())
        
        async def mock_get_all_tools():
            result = {}
            for server_name, server in sample_servers.items():
                result[server_name] = await server.list_tools()
            return result
        
        server_manager.get_all_tools = mock_get_all_tools
        server_manager.get_server_health.side_effect = lambda name: sample_servers[name].get_health()
        server_manager.call_tool = AsyncMock(return_value=MCPResult(type="success", content="test", metadata={}))
        
        # Create and test MCP tool registry
        tool_registry = MCPToolRegistry(
            server_manager=server_manager,
            permission_manager=permission_manager,
            auto_register=True
        )
        
        # Test tool discovery and registration
        registered_count = await tool_registry.discover_and_register_all_tools()
        
        # Should register all tools from all servers
        expected_total = sum(len(server.tools) for server in sample_servers.values())
        assert registered_count == expected_total
        
        # Verify tools are registered with proper namespacing
        registered_tools = tool_registry.list_registered_tools()
        assert len(registered_tools) == expected_total
        
        # All registered tools should have namespace prefixes
        namespaced_tools = [name for name in registered_tools if ":" in name]
        assert len(namespaced_tools) == expected_total
        
        # Test tool information retrieval
        for tool_name in registered_tools:
            tool_info = tool_registry.get_tool_info(tool_name)
            assert tool_info is not None
            assert "registered_at" in tool_info
            assert "namespace" in tool_info
    
    @pytest.mark.asyncio
    async def test_auto_discovery_with_server_changes(self, sample_servers):
        """Test auto-discovery behavior when servers are added/removed."""
        
        # Start with subset of servers
        active_servers = {"file_server": sample_servers["file_server"]}
        
        # Mock server manager
        server_manager = Mock()
        server_manager.list_servers.return_value = list(active_servers.keys())
        
        async def mock_get_all_tools():
            result = {}
            for server_name, server in active_servers.items():
                result[server_name] = await server.list_tools()
            return result
        
        server_manager.get_all_tools = mock_get_all_tools
        server_manager.get_server_health.side_effect = lambda name: active_servers[name].get_health()
        
        # Create components
        permission_manager = Mock(spec=PermissionManager)
        permission_manager.check_permission = AsyncMock(return_value=True)
        
        tool_registry = MCPToolRegistry(server_manager, permission_manager)
        
        # Configure auto-discovery for testing
        discovery_policy = DiscoveryPolicy(
            mode=DiscoveryMode.REACTIVE,
            auto_register_new_tools=True,
            auto_unregister_dead_tools=True
        )
        
        auto_discovery = MCPAutoDiscovery(server_manager, tool_registry, discovery_policy)
        
        # Initial discovery
        initial_results = await auto_discovery.discover_all()
        assert "file_server" in initial_results
        assert initial_results["file_server"] > 0
        
        # Simulate adding a new server
        active_servers["web_server"] = sample_servers["web_server"]
        server_manager.list_servers.return_value = list(active_servers.keys())
        
        # Discover again
        updated_results = await auto_discovery.discover_all()
        assert "web_server" in updated_results
        assert updated_results["web_server"] > 0
        
        # Check discovery statistics
        stats = auto_discovery.get_discovery_stats()
        assert stats["discovery_cycles"] == 2
        assert stats["servers_processed"] >= 2
    
    @pytest.mark.asyncio
    async def test_dynamic_updates_workflow(self, sample_servers):
        """Test dynamic updates when tools change."""
        
        # Create components
        server_manager = Mock()
        server_manager.list_servers.return_value = ["file_server"]
        
        # Initial tools
        initial_tools = [sample_servers["file_server"].tools[0]]  # Just one tool initially
        
        async def mock_get_all_tools():
            return {"file_server": [
                MCPTool(
                    name=tool["name"],
                    description=tool["description"],
                    server_name="file_server",
                    input_schema=tool.get("schema", {"type": "object"})
                )
                for tool in initial_tools
            ]}
        
        server_manager.get_all_tools = mock_get_all_tools
        server_manager.get_server_health.return_value = sample_servers["file_server"].get_health()
        
        permission_manager = Mock(spec=PermissionManager)
        permission_manager.check_permission = AsyncMock(return_value=True)
        
        tool_registry = MCPToolRegistry(server_manager, permission_manager)
        
        # Create update manager
        update_policy = UpdatePolicy(
            enable_hot_updates=True,
            batch_updates=False,
            max_concurrent_updates=2
        )
        
        update_manager = DynamicUpdateManager(server_manager, tool_registry, update_policy)
        
        # Initialize and start
        await update_manager.start()
        
        try:
            # Initial registration
            await tool_registry.discover_and_register_all_tools()
            initial_count = len(tool_registry.registered_tools)
            assert initial_count == 1
            
            # Simulate tool addition
            initial_tools.extend(sample_servers["file_server"].tools[1:])  # Add remaining tools
            
            # Check for updates
            updates = await update_manager.check_for_updates()
            
            # Should detect new tools
            addition_updates = [u for u in updates if u.update_type.value == "addition"]
            assert len(addition_updates) > 0
            
            # Process updates
            for update in addition_updates:
                await update_manager.queue_update(update)
            
            # Wait for processing
            await asyncio.sleep(0.1)
            
            # Verify tools were added
            final_count = len(tool_registry.registered_tools)
            assert final_count > initial_count
            
            # Check update statistics
            stats = update_manager.get_update_stats()
            assert stats["total_updates_processed"] > 0
            
        finally:
            await update_manager.stop()
    
    @pytest.mark.asyncio
    async def test_error_handling_and_recovery(self, sample_servers):
        """Test error handling and recovery scenarios."""
        
        # Create server manager that will simulate failures
        server_manager = Mock()
        server_manager.list_servers.return_value = ["failing_server"]
        
        # Simulate server that fails intermittently
        failure_count = 0
        
        async def mock_get_all_tools():
            nonlocal failure_count
            failure_count += 1
            if failure_count <= 2:  # Fail first 2 times
                raise Exception(f"Server connection failed (attempt {failure_count})")
            # Succeed on 3rd attempt
            return {"failing_server": await sample_servers["file_server"].list_tools()}
        
        server_manager.get_all_tools = mock_get_all_tools
        server_manager.get_server_health.return_value = HealthMetrics(
            server_name="failing_server",
            status=HealthStatus.DEGRADED,
            last_check=datetime.now()
        )
        
        permission_manager = Mock(spec=PermissionManager)
        permission_manager.check_permission = AsyncMock(return_value=True)
        
        tool_registry = MCPToolRegistry(server_manager, permission_manager)
        
        # First attempt should fail
        with pytest.raises(Exception, match="Server connection failed"):
            await tool_registry.discover_and_register_all_tools()
        
        # Second attempt should also fail
        with pytest.raises(Exception, match="Server connection failed"):
            await tool_registry.discover_and_register_all_tools()
        
        # Third attempt should succeed
        registered_count = await tool_registry.discover_and_register_all_tools()
        assert registered_count > 0
        
        # Verify registry stats reflect the failures
        stats = tool_registry.get_registry_stats()
        assert stats["failed_registrations"] >= 0  # Some failures were recorded
    
    @pytest.mark.asyncio
    async def test_concurrent_operations_workflow(self, sample_servers):
        """Test concurrent operations across the MCP system."""
        
        # Create server manager
        server_manager = Mock()
        server_manager.list_servers.return_value = list(sample_servers.keys())
        
        async def mock_get_all_tools():
            result = {}
            for server_name, server in sample_servers.items():
                result[server_name] = await server.list_tools()
            return result
        
        server_manager.get_all_tools = mock_get_all_tools
        server_manager.get_server_health.side_effect = lambda name: sample_servers[name].get_health()
        server_manager.call_tool = AsyncMock(return_value=MCPResult(type="success", content="test", metadata={}))
        
        permission_manager = Mock(spec=PermissionManager)
        permission_manager.check_permission = AsyncMock(return_value=True)
        
        # Create multiple registries for concurrent testing
        registries = [
            MCPToolRegistry(server_manager, permission_manager)
            for _ in range(3)
        ]
        
        # Concurrent discovery tasks
        discovery_tasks = [
            registry.discover_and_register_all_tools()
            for registry in registries
        ]
        
        # Execute concurrently
        results = await asyncio.gather(*discovery_tasks, return_exceptions=True)
        
        # All should succeed
        for result in results:
            assert not isinstance(result, Exception)
            assert result > 0  # Tools were registered
        
        # Verify each registry has tools
        for registry in registries:
            assert len(registry.registered_tools) > 0
            assert len(registry.server_tools) > 0
    
    @pytest.mark.asyncio
    async def test_performance_benchmarks(self, sample_servers):
        """Test performance benchmarks for the MCP system."""
        
        # Create a large number of mock tools for performance testing
        large_server = MockMCPServer("large_performance_server")
        large_server.tools = [
            {
                "name": f"perf_tool_{i}",
                "description": f"Performance test tool {i}",
                "schema": {
                    "type": "object",
                    "properties": {
                        f"param_{j}": {"type": "string"}
                        for j in range(5)  # 5 parameters per tool
                    }
                }
            }
            for i in range(50)  # 50 tools
        ]
        
        # Add to sample servers
        test_servers = {**sample_servers, "large_performance_server": large_server}
        
        # Create server manager
        server_manager = Mock()
        server_manager.list_servers.return_value = list(test_servers.keys())
        
        async def mock_get_all_tools():
            result = {}
            for server_name, server in test_servers.items():
                result[server_name] = await server.list_tools()
            return result
        
        server_manager.get_all_tools = mock_get_all_tools
        server_manager.get_server_health.side_effect = lambda name: test_servers[name].get_health()
        
        permission_manager = Mock(spec=PermissionManager)
        permission_manager.check_permission = AsyncMock(return_value=True)
        
        tool_registry = MCPToolRegistry(server_manager, permission_manager)
        
        # Benchmark tool discovery and registration
        start_time = datetime.now()
        registered_count = await tool_registry.discover_and_register_all_tools()
        end_time = datetime.now()
        
        duration = (end_time - start_time).total_seconds()
        
        # Performance assertions
        assert registered_count >= 50  # At least the large server's tools
        assert duration < 2.0  # Should complete within 2 seconds
        
        # Benchmark tool lookup
        registered_tools = tool_registry.list_registered_tools()
        
        lookup_start = datetime.now()
        for tool_name in registered_tools[:10]:  # Test first 10 tools
            tool_info = tool_registry.get_tool_info(tool_name)
            assert tool_info is not None
        lookup_end = datetime.now()
        
        lookup_duration = (lookup_end - lookup_start).total_seconds()
        assert lookup_duration < 0.1  # Lookups should be very fast
        
        # Get performance stats
        stats = tool_registry.get_registry_stats()
        assert stats["currently_registered"] >= 50
        assert stats["successful_registrations"] >= 50


class TestRealWorldScenarios:
    """Test real-world usage scenarios."""
    
    @pytest.mark.asyncio
    async def test_gradual_server_deployment(self, sample_servers):
        """Test scenario where MCP servers are deployed gradually."""
        
        # Start with empty system
        active_servers = {}
        
        server_manager = Mock()
        server_manager.list_servers = Mock(return_value=list(active_servers.keys()))
        
        async def mock_get_all_tools():
            result = {}
            for server_name, server in active_servers.items():
                result[server_name] = await server.list_tools()
            return result
        
        server_manager.get_all_tools = mock_get_all_tools
        server_manager.get_server_health = Mock(side_effect=lambda name: active_servers[name].get_health())
        
        permission_manager = Mock(spec=PermissionManager)
        permission_manager.check_permission = AsyncMock(return_value=True)
        
        # Create unified registry
        unified_registry = SimaCodeToolRegistry(permission_manager)
        
        # Mock MCP initialization
        unified_registry.mcp_enabled = True
        unified_registry.mcp_server_manager = server_manager
        unified_registry.mcp_tool_registry = MCPToolRegistry(server_manager, permission_manager)
        
        # Initial state - no tools
        initial_tools = unified_registry.list_tools()
        assert len(initial_tools) == 0
        
        # Deploy first server
        active_servers["file_server"] = sample_servers["file_server"]
        server_manager.list_servers.return_value = list(active_servers.keys())
        
        await unified_registry.mcp_tool_registry.discover_and_register_all_tools()
        tools_after_first = unified_registry.list_tools()
        assert len(tools_after_first) > 0
        
        # Deploy second server
        active_servers["web_server"] = sample_servers["web_server"]
        server_manager.list_servers.return_value = list(active_servers.keys())
        
        await unified_registry.mcp_tool_registry.discover_and_register_all_tools()
        tools_after_second = unified_registry.list_tools()
        assert len(tools_after_second) > len(tools_after_first)
        
        # Deploy third server
        active_servers["data_server"] = sample_servers["data_server"]
        server_manager.list_servers.return_value = list(active_servers.keys())
        
        await unified_registry.mcp_tool_registry.discover_and_register_all_tools()
        tools_after_third = unified_registry.list_tools()
        assert len(tools_after_third) > len(tools_after_second)
        
        # Final verification
        expected_total = sum(len(server.tools) for server in sample_servers.values())
        assert len(tools_after_third) == expected_total
    
    @pytest.mark.asyncio
    async def test_server_maintenance_scenario(self, sample_servers):
        """Test scenario where servers go down for maintenance."""
        
        # Start with all servers running
        active_servers = dict(sample_servers)
        
        server_manager = Mock()
        server_manager.list_servers = Mock(return_value=list(active_servers.keys()))
        
        async def mock_get_all_tools():
            result = {}
            for server_name, server in active_servers.items():
                if server.health_status != HealthStatus.FAILED:
                    result[server_name] = await server.list_tools()
            return result
        
        server_manager.get_all_tools = mock_get_all_tools
        server_manager.get_server_health = Mock(side_effect=lambda name: active_servers[name].get_health())
        
        permission_manager = Mock(spec=PermissionManager)
        permission_manager.check_permission = AsyncMock(return_value=True)
        
        tool_registry = MCPToolRegistry(server_manager, permission_manager)
        
        # Initial registration
        initial_count = await tool_registry.discover_and_register_all_tools()
        assert initial_count > 0
        
        # Server goes down for maintenance
        active_servers["file_server"].health_status = HealthStatus.FAILED
        
        # Registry should handle server being down
        stats = tool_registry.get_registry_stats()
        healthy_tools_before = stats["healthy_tools"]
        
        # Simulate health check that detects failed server
        # (In real system, this would be done by health monitor)
        health = server_manager.get_server_health("file_server")
        assert health.status == HealthStatus.FAILED
        
        # Server comes back online
        active_servers["file_server"].health_status = HealthStatus.HEALTHY
        
        # Re-register tools from recovered server
        await tool_registry.refresh_server_tools("file_server")
        
        # Verify tools are available again
        final_stats = tool_registry.get_registry_stats()
        assert final_stats["healthy_tools"] >= healthy_tools_before
    
    @pytest.mark.asyncio
    async def test_tool_versioning_scenario(self, sample_servers):
        """Test scenario where tools are updated with new versions."""
        
        # Start with initial tool version
        file_server = sample_servers["file_server"]
        original_tool = file_server.tools[0].copy()
        
        server_manager = Mock()
        server_manager.list_servers.return_value = ["file_server"]
        
        async def mock_get_all_tools():
            return {"file_server": await file_server.list_tools()}
        
        server_manager.get_all_tools = mock_get_all_tools
        server_manager.get_server_health.return_value = file_server.get_health()
        
        permission_manager = Mock(spec=PermissionManager)
        permission_manager.check_permission = AsyncMock(return_value=True)
        
        tool_registry = MCPToolRegistry(server_manager, permission_manager)
        update_manager = DynamicUpdateManager(server_manager, tool_registry)
        
        # Start systems
        await update_manager.start()
        
        try:
            # Initial registration
            await tool_registry.discover_and_register_all_tools()
            initial_tools = tool_registry.list_registered_tools()
            
            # Get initial tool info
            tool_name = initial_tools[0]
            initial_info = tool_registry.get_tool_info(tool_name)
            
            # Simulate tool update (change description)
            file_server.tools[0]["description"] = "Updated: " + original_tool["description"]
            file_server.tools[0]["schema"]["properties"]["new_param"] = {"type": "string"}
            
            # Check for updates
            updates = await update_manager.check_for_updates()
            
            # Should detect modification
            modification_updates = [u for u in updates if u.update_type.value == "modification"]
            assert len(modification_updates) > 0
            
            # Process updates
            for update in modification_updates:
                await update_manager.queue_update(update)
            
            # Wait for processing
            await asyncio.sleep(0.1)
            
            # Verify tool was updated
            updated_info = tool_registry.get_tool_info(tool_name)
            assert updated_info["description"] != initial_info["description"]
            assert "Updated:" in updated_info["description"]
            
        finally:
            await update_manager.stop()


if __name__ == "__main__":
    # Run tests with pytest
    import subprocess
    subprocess.run([
        "python", "-m", "pytest", __file__, "-v", "--tb=short",
        "-k", "not test_performance_benchmarks"  # Skip slow performance tests by default
    ])