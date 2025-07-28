#!/usr/bin/env python3
"""
MCP Phase 2 综合测试脚本

这个脚本提供了多种测试方法来验证 Phase 2 开发成果：
1. 基础导入测试
2. 组件实例化测试
3. 配置管理测试
4. 工具发现系统测试
5. 健康监控系统测试
6. 服务器管理器集成测试
7. 错误处理测试
8. 性能基准测试
"""

import asyncio
import logging
import sys
import time
import tempfile
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import AsyncMock, MagicMock
import traceback

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Phase2TestRunner:
    """Phase 2 测试运行器"""
    
    def __init__(self):
        self.test_results = {}
        self.total_tests = 0
        self.passed_tests = 0
        self.failed_tests = 0
        
    def print_header(self, title: str):
        """打印测试标题"""
        print(f"\n{'='*60}")
        print(f"🧪 {title}")
        print(f"{'='*60}")
    
    def print_test(self, name: str, status: str, details: str = ""):
        """打印测试结果"""
        status_emoji = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
        print(f"{status_emoji} {name}: {status}")
        if details:
            print(f"   {details}")
        
        self.total_tests += 1
        if status == "PASS":
            self.passed_tests += 1
        else:
            self.failed_tests += 1
        
        self.test_results[name] = {"status": status, "details": details}
    
    async def test_basic_imports(self):
        """测试 1: 基础导入测试"""
        self.print_header("基础导入测试")
        
        imports = [
            ("MCPServerManager", "simacode.mcp.server_manager"),
            ("MCPToolDiscovery", "simacode.mcp.discovery"),
            ("MCPHealthMonitor", "simacode.mcp.health"),
            ("MCPConfig", "simacode.mcp.config"),
            ("MCPClient", "simacode.mcp.client"),
        ]
        
        for class_name, module_name in imports:
            try:
                module = __import__(module_name, fromlist=[class_name])
                getattr(module, class_name)
                self.print_test(f"Import {class_name}", "PASS")
            except Exception as e:
                self.print_test(f"Import {class_name}", "FAIL", str(e))
    
    async def test_component_instantiation(self):
        """测试 2: 组件实例化测试"""
        self.print_header("组件实例化测试")
        
        try:
            from simacode.mcp.server_manager import MCPServerManager
            from simacode.mcp.discovery import MCPToolDiscovery
            from simacode.mcp.health import MCPHealthMonitor
            from simacode.mcp.config import MCPConfigManager
            
            # 测试服务器管理器
            try:
                manager = MCPServerManager()
                self.print_test("MCPServerManager创建", "PASS", 
                               f"工具发现: {type(manager.tool_discovery).__name__}, "
                               f"健康监控: {type(manager.health_monitor).__name__}")
            except Exception as e:
                self.print_test("MCPServerManager创建", "FAIL", str(e))
            
            # 测试工具发现系统
            try:
                discovery = MCPToolDiscovery(cache_ttl=60)
                stats = discovery.get_discovery_stats()
                self.print_test("MCPToolDiscovery创建", "PASS", 
                               f"统计信息: {len(stats)} 个字段")
            except Exception as e:
                self.print_test("MCPToolDiscovery创建", "FAIL", str(e))
            
            # 测试健康监控系统
            try:
                health_monitor = MCPHealthMonitor(check_interval=10)
                monitoring_stats = health_monitor.get_monitoring_stats()
                self.print_test("MCPHealthMonitor创建", "PASS",
                               f"监控统计: {len(monitoring_stats)} 个字段")
            except Exception as e:
                self.print_test("MCPHealthMonitor创建", "FAIL", str(e))
            
            # 测试配置管理器
            try:
                with tempfile.TemporaryDirectory() as temp_dir:
                    config_manager = MCPConfigManager(Path(temp_dir) / "test.yaml")
                    self.print_test("MCPConfigManager创建", "PASS")
            except Exception as e:
                self.print_test("MCPConfigManager创建", "FAIL", str(e))
                
        except ImportError as e:
            self.print_test("组件导入", "FAIL", f"无法导入必要模块: {e}")
    
    async def test_configuration_management(self):
        """测试 3: 配置管理测试"""
        self.print_header("配置管理测试")
        
        try:
            from simacode.mcp.config import (
                MCPConfig, MCPGlobalConfig, MCPServerConfig, 
                MCPSecurityConfig, MCPConfigManager
            )
            
            # 测试配置模型创建
            try:
                security_config = MCPSecurityConfig(
                    allowed_operations=["read", "write"],
                    allowed_paths=["/tmp"],
                    forbidden_paths=["/etc"],
                    max_execution_time=30
                )
                self.print_test("MCPSecurityConfig创建", "PASS")
            except Exception as e:
                self.print_test("MCPSecurityConfig创建", "FAIL", str(e))
            
            # 测试服务器配置
            try:
                server_config = MCPServerConfig(
                    name="test_server",
                    enabled=True,
                    command=["echo", "test"],
                    security=security_config
                )
                self.print_test("MCPServerConfig创建", "PASS")
            except Exception as e:
                self.print_test("MCPServerConfig创建", "FAIL", str(e))
            
            # 测试全局配置
            try:
                global_config = MCPGlobalConfig(
                    enabled=True,
                    timeout=30,
                    max_concurrent=5
                )
                self.print_test("MCPGlobalConfig创建", "PASS")
            except Exception as e:
                self.print_test("MCPGlobalConfig创建", "FAIL", str(e))
            
            # 测试完整配置
            try:
                full_config = MCPConfig(
                    mcp=global_config,
                    servers={"test": server_config}
                )
                enabled_servers = full_config.get_enabled_servers()
                self.print_test("MCPConfig创建和过滤", "PASS", 
                               f"启用的服务器数量: {len(enabled_servers)}")
            except Exception as e:
                self.print_test("MCPConfig创建和过滤", "FAIL", str(e))
                
        except ImportError as e:
            self.print_test("配置模块导入", "FAIL", str(e))
    
    async def test_tool_discovery_system(self):
        """测试 4: 工具发现系统测试"""
        self.print_header("工具发现系统测试")
        
        try:
            from simacode.mcp.discovery import MCPToolDiscovery, ToolMetadata
            from simacode.mcp.protocol import MCPTool
            from datetime import datetime
            
            discovery = MCPToolDiscovery(cache_ttl=60)
            
            # 创建模拟工具
            mock_tools = [
                MCPTool(name="file_read", description="Read file contents", server_name="fs"),
                MCPTool(name="git_status", description="Check git repository status", server_name="git"),
                MCPTool(name="db_query", description="Execute database query", server_name="db"),
            ]
            
            # 测试工具索引更新
            try:
                await discovery._update_tools_index("test_server", mock_tools)
                stats = discovery.get_discovery_stats()
                self.print_test("工具索引更新", "PASS", 
                               f"索引了 {stats['total_tools']} 个工具")
            except Exception as e:
                self.print_test("工具索引更新", "FAIL", str(e))
            
            # 测试名称搜索
            try:
                results = await discovery.find_tools_by_name("file_read")
                self.print_test("精确名称搜索", "PASS" if results else "FAIL",
                               f"找到 {len(results)} 个结果")
            except Exception as e:
                self.print_test("精确名称搜索", "FAIL", str(e))
            
            # 测试模糊搜索
            try:
                fuzzy_results = await discovery.find_tools_by_name("file", fuzzy=True)
                self.print_test("模糊名称搜索", "PASS" if fuzzy_results else "FAIL",
                               f"找到 {len(fuzzy_results)} 个结果")
            except Exception as e:
                self.print_test("模糊名称搜索", "FAIL", str(e))
            
            # 测试描述搜索
            try:
                desc_results = await discovery.find_tools_by_description(["read", "file"])
                self.print_test("描述关键词搜索", "PASS" if desc_results else "FAIL",
                               f"找到 {len(desc_results)} 个结果")
            except Exception as e:
                self.print_test("描述关键词搜索", "FAIL", str(e))
            
            # 测试分类搜索
            try:
                category_results = await discovery.find_tools_by_category("file")
                self.print_test("分类搜索", "PASS",
                               f"文件分类找到 {len(category_results)} 个工具")
            except Exception as e:
                self.print_test("分类搜索", "FAIL", str(e))
            
            # 测试使用统计
            try:
                discovery.record_tool_usage("file_read", True, 0.5)
                discovery.record_tool_usage("file_read", False, 1.0)
                self.print_test("使用统计记录", "PASS", "记录了成功和失败的调用")
            except Exception as e:
                self.print_test("使用统计记录", "FAIL", str(e))
                
        except ImportError as e:
            self.print_test("工具发现模块导入", "FAIL", str(e))
    
    async def test_health_monitoring_system(self):
        """测试 5: 健康监控系统测试"""
        self.print_header("健康监控系统测试")
        
        try:
            from simacode.mcp.health import MCPHealthMonitor, HealthMetrics, HealthStatus
            from simacode.mcp.client import MCPClient
            from datetime import datetime
            
            monitor = MCPHealthMonitor(check_interval=5, recovery_enabled=True)
            
            # 测试健康指标
            try:
                metrics = HealthMetrics("test_server")
                
                # 模拟健康检查结果
                metrics.update_check_result(True, 0.5)  # 成功
                metrics.update_check_result(False, 2.0, "Connection timeout")  # 失败
                metrics.update_check_result(True, 0.3)  # 恢复
                
                self.print_test("健康指标更新", "PASS", 
                               f"状态: {metrics.status.value}, 成功率: {metrics.success_rate:.2f}")
            except Exception as e:
                self.print_test("健康指标更新", "FAIL", str(e))
            
            # 测试监控统计
            try:
                stats = monitor.get_monitoring_stats()
                expected_fields = ["total_servers", "active_monitors", "check_interval"]
                has_all_fields = all(field in stats for field in expected_fields)
                self.print_test("监控统计信息", "PASS" if has_all_fields else "FAIL",
                               f"包含 {len(stats)} 个统计字段")
            except Exception as e:
                self.print_test("监控统计信息", "FAIL", str(e))
            
            # 测试告警回调
            try:
                alert_received = []
                
                def alert_callback(alert_data):
                    alert_received.append(alert_data)
                
                monitor.add_alert_callback(alert_callback)
                self.print_test("告警回调注册", "PASS", "成功注册告警回调函数")
            except Exception as e:
                self.print_test("告警回调注册", "FAIL", str(e))
            
            # 测试监控启动和停止
            try:
                await monitor.start_monitoring()
                await asyncio.sleep(0.1)  # 短暂等待
                await monitor.stop_monitoring()
                self.print_test("监控启动停止", "PASS", "监控系统正常启动和停止")
            except Exception as e:
                self.print_test("监控启动停止", "FAIL", str(e))
                
        except ImportError as e:
            self.print_test("健康监控模块导入", "FAIL", str(e))
    
    async def test_server_manager_integration(self):
        """测试 6: 服务器管理器集成测试"""
        self.print_header("服务器管理器集成测试")
        
        try:
            from simacode.mcp.server_manager import MCPServerManager
            from simacode.mcp.config import MCPServerConfig, MCPSecurityConfig
            
            manager = MCPServerManager()
            
            # 测试管理器初始化
            try:
                # 检查内部组件
                has_discovery = hasattr(manager, 'tool_discovery')
                has_health = hasattr(manager, 'health_monitor')
                has_config = hasattr(manager, 'config_manager')
                
                all_components = has_discovery and has_health and has_config
                self.print_test("管理器组件初始化", "PASS" if all_components else "FAIL",
                               f"工具发现: {has_discovery}, 健康监控: {has_health}, 配置: {has_config}")
            except Exception as e:
                self.print_test("管理器组件初始化", "FAIL", str(e))
            
            # 测试服务器列表
            try:
                servers = manager.list_servers()
                self.print_test("服务器列表获取", "PASS", f"当前服务器数量: {len(servers)}")
            except Exception as e:
                self.print_test("服务器列表获取", "FAIL", str(e))
            
            # 测试统计信息
            try:
                stats = manager.get_manager_stats()
                required_fields = ["total_servers", "connected_servers", "discovery", "health_monitoring"]
                has_required = all(field in stats for field in required_fields)
                self.print_test("管理器统计信息", "PASS" if has_required else "FAIL",
                               f"统计字段: {list(stats.keys())}")
            except Exception as e:
                self.print_test("管理器统计信息", "FAIL", str(e))
            
            # 测试搜索功能（无实际服务器）
            try:
                search_results = await manager.search_tools("test_query")
                self.print_test("工具搜索功能", "PASS", f"搜索返回 {len(search_results)} 个结果")
            except Exception as e:
                self.print_test("工具搜索功能", "FAIL", str(e))
            
            # 测试健康监控集成
            try:
                health_metrics = manager.get_all_health_metrics()
                unhealthy_servers = manager.get_unhealthy_servers()
                self.print_test("健康监控集成", "PASS",
                               f"健康指标: {len(health_metrics)}, 不健康服务器: {len(unhealthy_servers)}")
            except Exception as e:
                self.print_test("健康监控集成", "FAIL", str(e))
                
        except ImportError as e:
            self.print_test("服务器管理器模块导入", "FAIL", str(e))
    
    async def test_error_handling(self):
        """测试 7: 错误处理测试"""
        self.print_header("错误处理测试")
        
        try:
            from simacode.mcp.server_manager import MCPServerManager
            from simacode.mcp.config import MCPServerConfig
            from simacode.mcp.exceptions import MCPConnectionError, MCPToolNotFoundError
            
            manager = MCPServerManager()
            
            # 测试不存在的服务器操作
            try:
                result = await manager.remove_server("non_existent_server")
                self.print_test("不存在服务器移除", "PASS" if not result else "FAIL",
                               "正确返回 False")
            except Exception as e:
                self.print_test("不存在服务器移除", "FAIL", str(e))
            
            # 测试不存在的工具查找
            try:
                tool_result = await manager.find_tool("non_existent_tool")
                self.print_test("不存在工具查找", "PASS" if tool_result is None else "FAIL",
                               "正确返回 None")
            except Exception as e:
                self.print_test("不存在工具查找", "FAIL", str(e))
            
            # 测试健康监控错误处理
            try:
                health = manager.get_server_health("non_existent_server")
                self.print_test("不存在服务器健康检查", "PASS" if health is None else "FAIL",
                               "正确返回 None")
            except Exception as e:
                self.print_test("不存在服务器健康检查", "FAIL", str(e))
            
            # 测试配置验证错误
            try:
                from pydantic import ValidationError
                validation_passed = False
                try:
                    # 测试空命令列表（应该失败）
                    invalid_config = MCPServerConfig(
                        name="test_server",
                        command=[]  # 空命令应该失败
                    )
                    validation_passed = True
                except (ValidationError, ValueError):
                    self.print_test("无效配置验证", "PASS", "正确抛出验证错误")
                
                if validation_passed:
                    self.print_test("无效配置验证", "FAIL", "应该抛出验证错误但没有")
                    
            except Exception as e:
                self.print_test("无效配置验证", "FAIL", str(e))
                
        except ImportError as e:
            self.print_test("错误处理模块导入", "FAIL", str(e))
    
    async def test_performance_benchmarks(self):
        """测试 8: 性能基准测试"""
        self.print_header("性能基准测试")
        
        try:
            from simacode.mcp.discovery import MCPToolDiscovery
            from simacode.mcp.protocol import MCPTool
            
            discovery = MCPToolDiscovery(cache_ttl=300)
            
            # 创建大量模拟工具进行性能测试
            num_tools = 100
            mock_tools = []
            for i in range(num_tools):
                tool = MCPTool(
                    name=f"tool_{i}",
                    description=f"Test tool number {i} for performance testing",
                    server_name=f"server_{i % 10}"
                )
                mock_tools.append(tool)
            
            # 测试索引性能
            try:
                start_time = time.time()
                await discovery._update_tools_index("perf_test_server", mock_tools)
                index_time = time.time() - start_time
                
                self.print_test("工具索引性能", "PASS" if index_time < 1.0 else "WARN",
                               f"索引 {num_tools} 个工具耗时: {index_time:.3f}s")
            except Exception as e:
                self.print_test("工具索引性能", "FAIL", str(e))
            
            # 测试搜索性能
            try:
                start_time = time.time()
                for i in range(10):
                    await discovery.find_tools_by_name(f"tool_{i}")
                search_time = time.time() - start_time
                
                self.print_test("搜索性能", "PASS" if search_time < 0.1 else "WARN",
                               f"10次精确搜索耗时: {search_time:.3f}s")
            except Exception as e:
                self.print_test("搜索性能", "FAIL", str(e))
            
            # 测试统计计算性能
            try:
                start_time = time.time()
                for i in range(100):
                    discovery.get_discovery_stats()
                stats_time = time.time() - start_time
                
                self.print_test("统计计算性能", "PASS" if stats_time < 0.5 else "WARN",
                               f"100次统计计算耗时: {stats_time:.3f}s")
            except Exception as e:
                self.print_test("统计计算性能", "FAIL", str(e))
                
        except ImportError as e:
            self.print_test("性能测试模块导入", "FAIL", str(e))
    
    def print_summary(self):
        """打印测试总结"""
        print(f"\n{'='*60}")
        print(f"📊 Phase 2 测试总结")
        print(f"{'='*60}")
        
        success_rate = (self.passed_tests / self.total_tests * 100) if self.total_tests > 0 else 0
        
        print(f"总测试数: {self.total_tests}")
        print(f"通过测试: {self.passed_tests} ✅")
        print(f"失败测试: {self.failed_tests} ❌")
        print(f"成功率: {success_rate:.1f}%")
        
        # 按状态分组显示结果
        passed = [name for name, result in self.test_results.items() if result["status"] == "PASS"]
        failed = [name for name, result in self.test_results.items() if result["status"] == "FAIL"]
        warned = [name for name, result in self.test_results.items() if result["status"] == "WARN"]
        
        if passed:
            print(f"\n✅ 通过的测试 ({len(passed)}):")
            for test in passed:
                print(f"   • {test}")
        
        if warned:
            print(f"\n⚠️  警告的测试 ({len(warned)}):")
            for test in warned:
                print(f"   • {test}")
                if self.test_results[test]["details"]:
                    print(f"     {self.test_results[test]['details']}")
        
        if failed:
            print(f"\n❌ 失败的测试 ({len(failed)}):")
            for test in failed:
                print(f"   • {test}")
                if self.test_results[test]["details"]:
                    print(f"     {self.test_results[test]['details']}")
        
        # 整体评估
        print(f"\n🎯 Phase 2 开发成果评估:")
        if success_rate >= 90:
            print("🟢 优秀 - Phase 2 实现质量很高，可以进入 Phase 3")
        elif success_rate >= 75:
            print("🟡 良好 - Phase 2 基本完成，建议修复失败测试后进入 Phase 3")
        elif success_rate >= 50:
            print("🟠 一般 - Phase 2 部分完成，需要解决主要问题")
        else:
            print("🔴 需要改进 - Phase 2 存在严重问题，需要重新检查实现")


async def main():
    """主测试函数"""
    print("🚀 启动 MCP Phase 2 综合测试")
    print(f"Python 版本: {sys.version}")
    print(f"工作目录: {Path.cwd()}")
    
    runner = Phase2TestRunner()
    
    try:
        # 运行所有测试
        await runner.test_basic_imports()
        await runner.test_component_instantiation()
        await runner.test_configuration_management()
        await runner.test_tool_discovery_system()
        await runner.test_health_monitoring_system()
        await runner.test_server_manager_integration()
        await runner.test_error_handling()
        await runner.test_performance_benchmarks()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试运行器出现错误: {e}")
        traceback.print_exc()
    
    finally:
        # 打印测试总结
        runner.print_summary()
    
    return 0 if runner.failed_tests == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))