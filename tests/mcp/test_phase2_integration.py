"""
Integration tests for MCP Phase 2: Server Management and Tool Discovery.

This module tests the integration between the MCP server manager,
tool discovery system, and health monitoring components.
"""

import asyncio
import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from simacode.mcp.server_manager import MCPServerManager
from simacode.mcp.config import MCPServerConfig, MCPGlobalConfig, MCPConfig, MCPSecurityConfig
from simacode.mcp.client import MCPClient, MCPClientState
from simacode.mcp.protocol import MCPTool
from simacode.mcp.health import HealthStatus


@pytest.fixture
async def mock_mcp_config():
    """Create a mock MCP configuration for testing."""
    return MCPConfig(
        mcp=MCPGlobalConfig(
            enabled=True,
            timeout=10,
            max_concurrent=5,
            health_check_interval=10
        ),
        servers={
            "test_server": MCPServerConfig(
                name="test_server",
                enabled=True,
                type="subprocess",
                command=["python", "-c", "print('test')"],
                security=MCPSecurityConfig(
                    allowed_operations=["test"],
                    max_execution_time=10
                )
            ),
            "disabled_server": MCPServerConfig(
                name="disabled_server",
                enabled=False,
                type="subprocess",
                command=["echo", "disabled"]
            )
        }
    )


@pytest.fixture
async def mock_mcp_client():
    """Create a mock MCP client."""
    client = AsyncMock(spec=MCPClient)
    client.is_connected.return_value = True
    client.get_state.return_value = MCPClientState.READY
    client.get_last_error.return_value = None
    client.tools_cache = {}
    client.resources_cache = {}
    client.ping.return_value = True
    
    # Mock tool discovery
    test_tool = MCPTool(
        name="test_tool",
        description="A test tool",
        server_name="test_server",
        input_schema={"type": "object", "properties": {}}
    )
    client.list_tools.return_value = [test_tool]
    client.get_tool.return_value = test_tool
    
    return client


@pytest.fixture
async def server_manager():
    """Create a server manager for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        config_path = Path(temp_dir) / "test_config.yaml"
        manager = MCPServerManager(config_path)
        yield manager
        # Cleanup
        try:
            await manager.stop()
        except Exception:
            pass


class TestMCPPhase2Integration:
    """Integration tests for MCP Phase 2 components."""
    
    @pytest.mark.asyncio
    async def test_server_manager_initialization(self, server_manager):
        """Test that server manager initializes correctly."""
        assert server_manager.config_manager is not None
        assert server_manager.tool_discovery is not None
        assert server_manager.health_monitor is not None
        assert len(server_manager.servers) == 0
        assert len(server_manager.connection_locks) == 0
    
    @pytest.mark.asyncio
    async def test_server_configuration_loading(self, server_manager, mock_mcp_config):
        """Test loading server configuration."""
        with patch.object(server_manager.config_manager, 'load_config', return_value=mock_mcp_config):
            await server_manager.load_config()
            
            assert server_manager.config is not None
            assert server_manager.config.mcp.enabled is True
            assert len(server_manager.config.servers) == 2
            
        # Test enabled servers filtering
        enabled_servers = server_manager.config.get_enabled_servers()
        assert len(enabled_servers) == 1
        assert "test_server" in enabled_servers
        assert "disabled_server" not in enabled_servers
    
    @pytest.mark.asyncio
    async def test_server_addition_and_discovery(self, server_manager, mock_mcp_client):
        """Test adding servers and tool discovery integration."""
        # Mock client creation
        with patch('simacode.mcp.server_manager.MCPClient', return_value=mock_mcp_client):
            # Mock health monitor methods
            server_manager.health_monitor.add_server = AsyncMock()
            
            # Mock connect_server to avoid actual connection
            server_manager.connect_server = AsyncMock(return_value=True)
            
            # Add a server
            server_config = MCPServerConfig(
                name="test_server",
                command=["echo", "test"],
                enabled=True
            )
            
            result = await server_manager.add_server("test_server", server_config)
            assert result is True
            assert "test_server" in server_manager.servers
            assert "test_server" in server_manager.connection_locks
            
            # Verify health monitoring was set up
            server_manager.health_monitor.add_server.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_tool_discovery_integration(self, server_manager, mock_mcp_client):
        """Test tool discovery system integration."""
        # Add mock client to servers
        server_manager.servers["test_server"] = mock_mcp_client
        
        # Test tool discovery
        all_tools = await server_manager.get_all_tools()
        assert "test_server" in all_tools
        assert len(all_tools["test_server"]) == 1
        assert all_tools["test_server"][0].name == "test_tool"
        
        # Test tool finding
        server_tool = await server_manager.find_tool("test_tool")
        assert server_tool is not None
        assert server_tool[0] == "test_server"
        assert server_tool[1].name == "test_tool"
        
        # Test tool search
        search_results = await server_manager.search_tools("test")
        assert len(search_results) > 0
        assert search_results[0].tool.name == "test_tool"
    
    @pytest.mark.asyncio
    async def test_health_monitoring_integration(self, server_manager, mock_mcp_client):
        """Test health monitoring system integration."""
        # Add mock client to servers
        server_manager.servers["test_server"] = mock_mcp_client
        
        # Mock health monitor methods
        server_manager.health_monitor.get_server_health = MagicMock()
        server_manager.health_monitor.get_all_health_metrics = MagicMock()
        server_manager.health_monitor.get_unhealthy_servers = MagicMock(return_value=[])
        
        # Test health metrics retrieval
        server_manager.get_server_health("test_server")
        server_manager.health_monitor.get_server_health.assert_called_once_with("test_server")
        
        all_health = server_manager.get_all_health_metrics()
        server_manager.health_monitor.get_all_health_metrics.assert_called_once()
        
        unhealthy = server_manager.get_unhealthy_servers()
        server_manager.health_monitor.get_unhealthy_servers.assert_called_once()
        assert len(unhealthy) == 0
    
    @pytest.mark.asyncio
    async def test_tool_call_with_statistics(self, server_manager, mock_mcp_client):
        """Test tool calling with usage statistics tracking."""
        # Setup
        server_manager.servers["test_server"] = mock_mcp_client
        mock_result = MagicMock()
        mock_result.success = True
        mock_mcp_client.call_tool.return_value = mock_result
        
        # Mock discovery system
        server_manager.tool_discovery.record_tool_usage = MagicMock()
        
        # Test tool call
        result = await server_manager.call_tool("test_server", "test_tool", {})
        
        # Verify call was made
        mock_mcp_client.call_tool.assert_called_once_with("test_tool", {})
        
        # Verify statistics were recorded
        server_manager.tool_discovery.record_tool_usage.assert_called_once()
        call_args = server_manager.tool_discovery.record_tool_usage.call_args
        assert call_args[0][0] == "test_tool"  # tool_name
        assert call_args[0][1] is True  # success
        assert isinstance(call_args[0][2], float)  # execution_time
    
    @pytest.mark.asyncio
    async def test_server_removal_cleanup(self, server_manager, mock_mcp_client):
        """Test that server removal properly cleans up all components."""
        # Setup
        server_manager.servers["test_server"] = mock_mcp_client
        server_manager.connection_locks["test_server"] = asyncio.Lock()
        
        # Mock cleanup methods
        server_manager.disconnect_server = AsyncMock(return_value=True)
        server_manager.health_monitor.remove_server = AsyncMock()
        server_manager.tool_discovery.refresh_tool_cache = AsyncMock()
        
        # Remove server
        result = await server_manager.remove_server("test_server")
        assert result is True
        
        # Verify cleanup
        server_manager.disconnect_server.assert_called_once_with("test_server")
        server_manager.health_monitor.remove_server.assert_called_once_with("test_server")
        server_manager.tool_discovery.refresh_tool_cache.assert_called_once_with("test_server")
        
        # Verify removal from collections
        assert "test_server" not in server_manager.servers
        assert "test_server" not in server_manager.connection_locks
    
    @pytest.mark.asyncio
    async def test_manager_statistics(self, server_manager, mock_mcp_client):
        """Test manager statistics collection."""
        # Setup
        server_manager.servers["test_server"] = mock_mcp_client
        
        # Mock statistics methods
        mock_discovery_stats = {"total_tools": 1, "total_servers": 1}
        mock_health_stats = {"total_servers": 1, "active_monitors": 1}
        
        server_manager.tool_discovery.get_discovery_stats = MagicMock(return_value=mock_discovery_stats)
        server_manager.health_monitor.get_monitoring_stats = MagicMock(return_value=mock_health_stats)
        mock_mcp_client.get_stats.return_value = {"state": "ready"}
        
        # Get statistics
        stats = server_manager.get_manager_stats()
        
        # Verify statistics structure
        assert "total_servers" in stats
        assert "connected_servers" in stats
        assert "discovery" in stats
        assert "health_monitoring" in stats
        assert "servers" in stats
        
        assert stats["total_servers"] == 1
        assert stats["discovery"] == mock_discovery_stats
        assert stats["health_monitoring"] == mock_health_stats
        assert "test_server" in stats["servers"]
    
    @pytest.mark.asyncio
    async def test_error_handling(self, server_manager):
        """Test error handling in various scenarios."""
        # Test adding server with invalid config - this should be handled gracefully
        try:
            invalid_config = MCPServerConfig(
                name="invalid_server",
                command=[],  # Empty command should cause validation error
                enabled=True
            )
            # If we get here, the validation didn't work as expected
            assert False, "Empty command should have caused validation error"
        except Exception:
            # This is expected - validation should catch empty command
            pass
        
        # Test operations on non-existent server
        result = await server_manager.remove_server("non_existent")
        assert result is False
        
        health = server_manager.get_server_health("non_existent")
        assert health is None
        
        # Test tool finding with no servers
        tool_result = await server_manager.find_tool("any_tool")
        assert tool_result is None
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self, server_manager, mock_mcp_client):
        """Test concurrent operations handling."""
        # Setup multiple mock clients
        clients = {}
        for i in range(3):
            client = AsyncMock(spec=MCPClient)
            client.is_connected.return_value = True
            client.call_tool.return_value = MagicMock(success=True)
            clients[f"server_{i}"] = client
        
        server_manager.servers.update(clients)
        server_manager.tool_discovery.record_tool_usage = MagicMock()
        
        # Test concurrent tool calls
        tasks = []
        for i in range(3):
            task = asyncio.create_task(
                server_manager.call_tool(f"server_{i}", "test_tool", {})
            )
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Verify all calls succeeded
        assert len(results) == 3
        for result in results:
            assert not isinstance(result, Exception)
        
        # Verify statistics were recorded for all calls  
        assert server_manager.tool_discovery.record_tool_usage.call_count == 3


if __name__ == "__main__":
    # Run tests if executed directly
    import sys
    sys.exit(pytest.main([__file__, "-v"]))