"""
MCP Phase 2 单元测试

这个模块包含 Phase 2 各个组件的详细单元测试。
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
import tempfile
from pathlib import Path

# 导入被测试的模块
from simacode.mcp.discovery import MCPToolDiscovery, ToolMetadata
from simacode.mcp.health import MCPHealthMonitor, HealthMetrics, HealthStatus
from simacode.mcp.config import MCPConfigManager, MCPConfig, MCPServerConfig
from simacode.mcp.protocol import MCPTool


class TestMCPToolDiscovery:
    """工具发现系统单元测试"""
    
    @pytest.fixture
    def discovery(self):
        return MCPToolDiscovery(cache_ttl=60)
    
    @pytest.fixture
    def sample_tools(self):
        return [
            MCPTool(name="file_read", description="Read file contents", server_name="fs"),
            MCPTool(name="file_write", description="Write file contents", server_name="fs"),
            MCPTool(name="git_status", description="Check git repository status", server_name="git"),
            MCPTool(name="git_commit", description="Commit changes to repository", server_name="git"),
            MCPTool(name="db_query", description="Execute database query", server_name="db"),
        ]
    
    @pytest.mark.asyncio
    async def test_tool_indexing(self, discovery, sample_tools):
        """测试工具索引功能"""
        await discovery._update_tools_index("test_server", sample_tools)
        
        stats = discovery.get_discovery_stats()
        assert stats["total_tools"] == len(sample_tools)
        assert "test_server" in stats["server_distribution"]
        assert stats["server_distribution"]["test_server"] == len(sample_tools)
    
    @pytest.mark.asyncio
    async def test_exact_name_search(self, discovery, sample_tools):
        """测试精确名称搜索"""
        await discovery._update_tools_index("test_server", sample_tools)
        
        results = await discovery.find_tools_by_name("file_read", fuzzy=False)
        assert len(results) == 1
        assert results[0].tool.name == "file_read"
    
    @pytest.mark.asyncio
    async def test_fuzzy_name_search(self, discovery, sample_tools):
        """测试模糊名称搜索"""
        await discovery._update_tools_index("test_server", sample_tools)
        
        results = await discovery.find_tools_by_name("file", fuzzy=True)
        assert len(results) >= 2  # Should match file_read and file_write
        tool_names = [r.tool.name for r in results]
        assert "file_read" in tool_names
        assert "file_write" in tool_names
    
    @pytest.mark.asyncio
    async def test_description_search(self, discovery, sample_tools):
        """测试描述搜索"""
        await discovery._update_tools_index("test_server", sample_tools)
        
        results = await discovery.find_tools_by_description(["git", "repository"])
        assert len(results) >= 2  # Should match git_status and git_commit
        
        # 检查结果按相关性排序
        assert results[0].tool.name in ["git_status", "git_commit"]
    
    @pytest.mark.asyncio
    async def test_category_search(self, discovery, sample_tools):
        """测试分类搜索"""
        await discovery._update_tools_index("test_server", sample_tools)
        
        # 应该自动分类为 "file" 分类
        file_tools = await discovery.find_tools_by_category("file")
        assert len(file_tools) >= 2
        
        # Git 工具应该分类为 "git"
        git_tools = await discovery.find_tools_by_category("git")
        assert len(git_tools) >= 2
    
    def test_usage_statistics(self, discovery):
        """测试使用统计功能"""
        discovery.tools_index["test_tool"] = ToolMetadata(
            tool=MCPTool(name="test_tool", description="Test", server_name="test"),
            server_name="test"
        )
        
        # 记录成功使用
        discovery.record_tool_usage("test_tool", True, 0.5)
        metadata = discovery.tools_index["test_tool"]
        
        assert metadata.usage_count == 1
        assert metadata.success_rate > 0.9
        assert metadata.last_used is not None
        
        # 记录失败使用
        discovery.record_tool_usage("test_tool", False, 1.0)
        assert metadata.usage_count == 2
        assert metadata.success_rate < 1.0
    
    @pytest.mark.asyncio
    async def test_cache_refresh(self, discovery, sample_tools):
        """测试缓存刷新"""
        await discovery._update_tools_index("test_server", sample_tools)
        
        # 清除缓存
        await discovery.refresh_tool_cache("test_server")
        
        # 检查缓存是否被清除（通过内部状态）
        assert "test_server" not in discovery.last_discovery
    
    @pytest.mark.asyncio
    async def test_tool_recommendations(self, discovery, sample_tools):
        """测试工具推荐"""
        await discovery._update_tools_index("test_server", sample_tools)
        
        # 模拟使用记录
        for tool in sample_tools[:2]:
            metadata = discovery.tools_index[tool.name]
            metadata.last_used = datetime.now()
            metadata.usage_count = 5
            metadata.success_rate = 0.9
        
        recommendations = await discovery.get_tool_recommendations({})
        assert len(recommendations) > 0
        
        # 推荐应该包含使用频率高的工具
        recommended_names = [r.tool.name for r in recommendations]
        assert any(name in recommended_names for name in [tool.name for tool in sample_tools[:2]])


class TestMCPHealthMonitor:
    """健康监控系统单元测试"""
    
    @pytest.fixture
    def health_monitor(self):
        return MCPHealthMonitor(check_interval=1, recovery_enabled=True)
    
    @pytest.fixture
    def mock_client(self):
        client = AsyncMock()
        client.is_connected.return_value = True
        client.ping.return_value = True
        return client
    
    def test_health_metrics_creation(self):
        """测试健康指标创建"""
        metrics = HealthMetrics("test_server")
        
        assert metrics.server_name == "test_server"
        assert metrics.status == HealthStatus.UNKNOWN
        assert metrics.total_checks == 0
        assert metrics.success_rate == 1.0
    
    def test_health_metrics_update(self):
        """测试健康指标更新"""
        metrics = HealthMetrics("test_server")
        
        # 成功检查
        metrics.update_check_result(True, 0.5)
        assert metrics.total_checks == 1
        assert metrics.successful_checks == 1
        assert metrics.consecutive_failures == 0
        assert metrics.success_rate == 1.0
        
        # 失败检查
        metrics.update_check_result(False, 2.0, "Connection failed")
        assert metrics.total_checks == 2
        assert metrics.consecutive_failures == 1
        assert metrics.last_error == "Connection failed"
        assert metrics.success_rate < 1.0
    
    def test_health_status_calculation(self):
        """测试健康状态计算"""
        metrics = HealthMetrics("test_server")
        
        # 健康状态
        for _ in range(5):
            metrics.update_check_result(True, 0.5)
        assert metrics.status == HealthStatus.HEALTHY
        
        # 降级状态（高延迟）
        metrics.update_check_result(True, 15.0)
        assert metrics.status == HealthStatus.DEGRADED
        
        # 重置为健康状态
        for _ in range(10):
            metrics.update_check_result(True, 0.5)
        assert metrics.status == HealthStatus.HEALTHY
        
        # 关键状态（连续失败）
        for _ in range(3):
            metrics.update_check_result(False, 1.0, "Failed")
        assert metrics.status == HealthStatus.CRITICAL
        
        # 失败状态（更多连续失败）
        for _ in range(3):
            metrics.update_check_result(False, 1.0, "Failed")
        assert metrics.status == HealthStatus.FAILED
    
    @pytest.mark.asyncio
    async def test_monitor_start_stop(self, health_monitor):
        """测试监控启动和停止"""
        await health_monitor.start_monitoring()
        assert health_monitor.monitor_task is not None
        
        await health_monitor.stop_monitoring()
        assert health_monitor.shutdown_event.is_set()
    
    @pytest.mark.asyncio
    async def test_server_addition_removal(self, health_monitor, mock_client):
        """测试服务器添加和移除"""
        # 添加服务器
        await health_monitor.add_server("test_server", mock_client)
        assert "test_server" in health_monitor.health_metrics
        assert "test_server" in health_monitor.monitoring_tasks
        
        # 移除服务器
        await health_monitor.remove_server("test_server")
        assert "test_server" not in health_monitor.health_metrics
        assert "test_server" not in health_monitor.monitoring_tasks
    
    def test_alert_callback_management(self, health_monitor):
        """测试告警回调管理"""
        callback = Mock()
        
        # 添加回调
        health_monitor.add_alert_callback(callback)
        assert callback in health_monitor.alert_callbacks
        
        # 移除回调
        health_monitor.remove_alert_callback(callback)
        assert callback not in health_monitor.alert_callbacks
    
    def test_monitoring_statistics(self, health_monitor):
        """测试监控统计"""
        stats = health_monitor.get_monitoring_stats()
        
        required_fields = [
            "total_servers", "active_monitors", "check_interval",
            "recovery_enabled", "status_distribution"
        ]
        
        for field in required_fields:
            assert field in stats
        
        assert isinstance(stats["total_servers"], int)
        assert isinstance(stats["check_interval"], int)
        assert isinstance(stats["recovery_enabled"], bool)


class TestMCPConfigManager:
    """配置管理器单元测试"""
    
    @pytest.fixture
    def temp_config_file(self):
        """创建临时配置文件"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            config_content = """
mcp:
  enabled: true
  timeout: 30
  max_concurrent: 5

servers:
  test_server:
    name: test_server
    enabled: true
    type: subprocess
    command: ["echo", "test"]
    security:
      allowed_operations: ["test"]
      max_execution_time: 10
"""
            f.write(config_content)
            yield Path(f.name)
        
        # 清理
        Path(f.name).unlink(missing_ok=True)
    
    @pytest.mark.asyncio
    async def test_config_loading(self, temp_config_file):
        """测试配置加载"""
        manager = MCPConfigManager(temp_config_file)
        config = await manager.load_config()
        
        assert config.mcp.enabled is True
        assert config.mcp.timeout == 30
        assert config.mcp.max_concurrent == 5
        assert "test_server" in config.servers
        assert config.servers["test_server"].enabled is True
    
    @pytest.mark.asyncio
    async def test_config_saving(self):
        """测试配置保存"""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "test_config.yaml"
            manager = MCPConfigManager(config_path)
            
            # 创建默认配置
            config = manager.create_default_config()
            await manager.save_config(config)
            
            assert config_path.exists()
            
            # 重新加载验证
            loaded_config = await manager.load_config()
            assert loaded_config.mcp.enabled == config.mcp.enabled
    
    def test_environment_template_processing(self):
        """测试环境变量模板处理"""
        from simacode.mcp.config import EnvironmentTemplateEngine
        import os
        
        engine = EnvironmentTemplateEngine()
        
        # 设置测试环境变量
        os.environ["TEST_VAR"] = "test_value"
        
        template = "command: ['echo', '${TEST_VAR}']"
        result = engine.process(template)
        
        assert "test_value" in result
        
        # 清理
        del os.environ["TEST_VAR"]
    
    def test_server_config_validation(self):
        """测试服务器配置验证"""
        from simacode.mcp.config import validate_server_config
        from pydantic import ValidationError
        
        # 有效配置
        valid_config = {
            "name": "test_server",
            "enabled": True,
            "command": ["echo", "test"]
        }
        
        server_config = validate_server_config(valid_config)
        assert server_config.name == "test_server"
        
        # 无效配置（空命令）
        invalid_config = {
            "name": "test_server",
            "command": []
        }
        
        with pytest.raises(Exception):  # ValidationError or MCPConfigurationError
            validate_server_config(invalid_config)


class TestIntegrationScenarios:
    """集成场景测试"""
    
    @pytest.mark.asyncio
    async def test_discovery_health_integration(self):
        """测试工具发现和健康监控的集成"""
        discovery = MCPToolDiscovery(cache_ttl=60)
        health_monitor = MCPHealthMonitor(check_interval=1, recovery_enabled=False)
        
        # 模拟工具发现
        tools = [
            MCPTool(name="test_tool", description="Test tool", server_name="test_server")
        ]
        await discovery._update_tools_index("test_server", tools)
        
        # 模拟健康监控
        mock_client = AsyncMock()
        mock_client.is_connected.return_value = True
        mock_client.ping.return_value = True
        
        await health_monitor.add_server("test_server", mock_client)
        
        # 验证集成状态
        discovery_stats = discovery.get_discovery_stats()
        health_stats = health_monitor.get_monitoring_stats()
        
        assert discovery_stats["total_tools"] == 1
        assert health_stats["total_servers"] == 1
        
        # 清理
        await health_monitor.remove_server("test_server")
    
    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """测试并发操作"""
        discovery = MCPToolDiscovery(cache_ttl=60)
        
        # 创建多个工具用于并发测试
        tools = [
            MCPTool(name=f"tool_{i}", description=f"Tool {i}", server_name="test_server")
            for i in range(10)
        ]
        
        # 并发更新索引
        await discovery._update_tools_index("test_server", tools)
        
        # 并发搜索
        search_tasks = [
            discovery.find_tools_by_name(f"tool_{i}", fuzzy=False)
            for i in range(5)
        ]
        
        results = await asyncio.gather(*search_tasks)
        
        # 验证所有搜索都返回了结果
        for result in results:
            assert len(result) == 1
    
    def test_error_recovery_scenarios(self):
        """测试错误恢复场景"""
        metrics = HealthMetrics("test_server")
        
        # 模拟间歇性失败
        for i in range(10):
            success = i % 3 != 0  # 每3次中失败1次
            metrics.update_check_result(success, 0.5 if success else 2.0, 
                                      None if success else "Intermittent failure")
        
        # 应该是降级状态，但不是失败状态
        assert metrics.status in [HealthStatus.DEGRADED, HealthStatus.HEALTHY]
        assert metrics.success_rate > 0.5
        
        # 模拟恢复
        for _ in range(5):
            metrics.update_check_result(True, 0.3)
        
        # 应该转为健康状态
        assert metrics.status == HealthStatus.HEALTHY


if __name__ == "__main__":
    pytest.main([__file__, "-v"])