#!/usr/bin/env python3
"""
SimaCode Phase 4 ReAct Engine 演示

演示Phase 4开发的ReAct引擎功能，包括：
- 智能任务规划
- 工具编排执行
- 结果评估反馈
- 会话管理
- 错误恢复机制
"""

import asyncio
import os
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from simacode.config import Config
from simacode.services.react_service import ReActService
from simacode.react.engine import ExecutionMode
from simacode.tools import ToolRegistry


async def demo_basic_react_workflow():
    """演示基本的ReAct工作流程"""
    print("=== SimaCode Phase 4 ReAct Engine 基础演示 ===\n")
    
    # 1. 创建配置
    print("1. 初始化配置和服务...")
    config = Config()
    
    # 创建ReAct服务
    react_service = ReActService(config)
    
    try:
        await react_service.start()
        print("✅ ReAct服务启动成功\n")
        
        # 2. 展示服务状态
        print("2. 服务状态信息:")
        status = await react_service.get_service_status()
        print(f"   - 服务运行: {status.get('service_running', False)}")
        print(f"   - AI客户端: {status.get('ai_client_type', 'Unknown')}")
        print(f"   - 执行模式: {status.get('execution_mode', 'Unknown')}")
        print(f"   - 可用工具: {len(status.get('available_tools', []))}")
        
        # 列出可用工具
        tools = status.get('available_tools', [])
        print(f"   - 工具列表: {', '.join(tools)}")
        print()
        
        # 3. 演示简单任务处理
        print("3. 演示任务处理流程:")
        
        # 模拟用户请求
        test_requests = [
            "创建一个test.txt文件并写入'Hello ReAct Engine'",
            "读取刚才创建的test.txt文件内容",
            "列出当前目录的文件",
        ]
        
        for i, request in enumerate(test_requests):
            print(f"\n--- 测试请求 {i+1}: {request} ---")
            
            try:
                async for update in react_service.process_user_request(request):
                    display_update(update)
                    
                print("✅ 请求处理完成\n")
                
            except Exception as e:
                print(f"❌ 请求处理失败: {str(e)}\n")
                
        # 4. 会话管理演示
        print("4. 会话管理演示:")
        sessions = await react_service.list_sessions(limit=5)
        print(f"   当前会话数量: {len(sessions)}")
        
        if sessions:
            print("   最近的会话:")
            for session in sessions[:3]:
                print(f"     - {session['id'][:8]}... : {session['user_input'][:50]}...")
        
        print()
        
    except Exception as e:
        print(f"❌ 演示过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
        
    finally:
        await react_service.stop()
        print("🛑 ReAct服务已停止")


def display_update(update: dict) -> None:
    """显示ReAct更新信息"""
    update_type = update.get("type", "unknown")
    content = update.get("content", "")
    
    if update_type == "status_update":
        print(f"   ℹ️  {content}")
    
    elif update_type == "task_plan":
        print(f"   📋 任务计划已创建:")
        tasks = update.get("tasks", [])
        for i, task in enumerate(tasks):
            print(f"     {i+1}. {task.get('description', 'Unknown task')}")
    
    elif update_type == "tool_progress":
        result_type = update.get("result_type", "info")
        if result_type == "error":
            print(f"     ❌ {content}")
        elif result_type == "success":
            print(f"     ✅ {content}")
        else:
            print(f"     ⚙️  {content}")
    
    elif update_type == "sub_task_result":
        task_status = update.get("status", "unknown")
        if task_status == "completed":
            print(f"   ✅ {content}")
        else:
            print(f"   ⚠️  {content}")
    
    elif update_type == "final_result":
        print(f"   🎉 {content}")
        summary = update.get("summary", {})
        if summary:
            print(f"     任务统计: {summary.get('successful_tasks', 0)}/{summary.get('total_tasks', 0)} 成功")
    
    elif update_type == "error":
        print(f"   ❌ 错误: {content}")
    
    elif update_type == "overall_assessment":
        print(f"   📊 整体评估: {content}")


async def demo_advanced_features():
    """演示高级功能"""
    print("\n=== Phase 4 高级功能演示 ===\n")
    
    config = Config()
    react_service = ReActService(config)
    
    try:
        await react_service.start()
        
        # 1. 复杂任务分解演示
        print("1. 复杂任务分解演示:")
        complex_request = "分析当前项目结构，找到所有Python文件，并统计代码行数"
        
        print(f"   请求: {complex_request}")
        print("   处理过程:")
        
        async for update in react_service.process_user_request(complex_request):
            display_update(update)
        
        print()
        
        # 2. 错误恢复演示
        print("2. 错误恢复机制演示:")
        error_request = "读取一个不存在的文件 nonexistent.txt"
        
        print(f"   请求: {error_request}")
        print("   处理过程:")
        
        async for update in react_service.process_user_request(error_request):
            display_update(update)
        
        print()
        
        # 3. 并行执行演示
        print("3. 并行执行能力演示:")
        parallel_request = "同时创建三个文件：file1.txt、file2.txt、file3.txt，内容分别为'File 1'、'File 2'、'File 3'"
        
        print(f"   请求: {parallel_request}")
        print("   处理过程:")
        
        async for update in react_service.process_user_request(parallel_request):
            display_update(update)
        
        print()
        
    except Exception as e:
        print(f"❌ 高级功能演示失败: {str(e)}")
        import traceback
        traceback.print_exc()
        
    finally:
        await react_service.stop()


def demo_tool_system():
    """演示工具系统"""
    print("\n=== 工具系统演示 ===\n")
    
    # 1. 工具注册和发现
    print("1. 已注册的工具:")
    registry = ToolRegistry()
    tools = registry.get_all_tools()
    
    for tool_name, tool in tools.items():
        print(f"   - {tool_name}: {tool.description}")
    
    # 2. 工具统计
    print("\n2. 工具统计信息:")
    stats = registry.get_registry_stats()
    print(f"   - 工具总数: {stats['total_tools']}")
    print(f"   - 总执行次数: {stats['total_executions']}")
    print(f"   - 平均执行时间: {stats['average_execution_time']:.3f}秒")
    
    print()


def demo_architecture_overview():
    """展示架构概览"""
    print("\n=== Phase 4 架构概览 ===\n")
    
    print("🏗️ ReAct引擎架构组件:")
    print("   ├── 📋 TaskPlanner - 智能任务规划器")
    print("   │   ├── 理解用户意图")
    print("   │   ├── 分解复杂任务")
    print("   │   └── 生成执行计划")
    print("   │")
    print("   ├── ⚙️ ReActEngine - 核心执行引擎")
    print("   │   ├── 推理-行动循环")
    print("   │   ├── 工具编排执行")
    print("   │   └── 状态管理")
    print("   │")
    print("   ├── 📊 ResultEvaluator - 结果评估器")
    print("   │   ├── 规则评估")
    print("   │   ├── AI评估")
    print("   │   └── 反馈生成")
    print("   │")
    print("   ├── 💾 SessionManager - 会话管理器")
    print("   │   ├── 会话持久化")
    print("   │   ├── 状态恢复")
    print("   │   └── 自动清理")
    print("   │")
    print("   └── 🔧 ToolRegistry - 工具注册表")
    print("       ├── 工具发现")
    print("       ├── 权限管理")
    print("       └── 执行监控")
    
    print("\n🎯 核心特性:")
    print("   ✅ 智能任务理解和分解")
    print("   ✅ 自适应执行策略")
    print("   ✅ 多工具协同编排")
    print("   ✅ 实时结果评估")
    print("   ✅ 错误恢复机制")
    print("   ✅ 会话持久化")
    print("   ✅ 安全权限控制")
    
    print("\n📈 验收标准完成情况:")
    print("   ✅ 正确解析'读取文件A并执行B'类任务")
    print("   ✅ 单步工具链执行成功")
    print("   ✅ 基本错误处理")
    print("   ✅ 会话状态保持")
    
    print()


async def cleanup_demo_files():
    """清理演示文件"""
    print("🧹 清理演示文件...")
    
    demo_files = [
        "test.txt",
        "file1.txt", 
        "file2.txt",
        "file3.txt",
        "nonexistent.txt"
    ]
    
    for file_name in demo_files:
        if os.path.exists(file_name):
            try:
                os.remove(file_name)
                print(f"   已删除: {file_name}")
            except Exception as e:
                print(f"   删除失败 {file_name}: {str(e)}")


async def main():
    """主演示函数"""
    print("🚀 SimaCode Phase 4: ReAct Engine 完整演示")
    print("=" * 60)
    
    # 架构概览
    demo_architecture_overview()
    
    # 工具系统演示
    demo_tool_system()
    
    # 基础功能演示
    await demo_basic_react_workflow()
    
    # 高级功能演示
    await demo_advanced_features()
    
    # 清理
    await cleanup_demo_files()
    
    print("\n📚 使用说明:")
    print("1. 使用 'simacode chat --react' 启用ReAct模式")
    print("2. 使用 'simacode chat --react --interactive' 进入交互模式")
    print("3. 使用 'simacode chat --react --session-id <id>' 恢复会话")
    print("4. ReAct模式支持自然语言任务描述和自动工具选择")
    print("5. 支持复杂任务分解和多步骤执行")
    
    print("\n✨ Phase 4 开发完成！")
    print("   - ReAct引擎核心功能实现")
    print("   - 智能任务规划和执行")
    print("   - 工具编排和结果评估")
    print("   - 会话管理和持久化")
    print("   - CLI集成和用户界面")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 演示被中断，再见！")
    except Exception as e:
        print(f"\n❌ 演示失败: {str(e)}")
        import traceback
        traceback.print_exc()