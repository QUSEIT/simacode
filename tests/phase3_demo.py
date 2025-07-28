#!/usr/bin/env python3
"""
SimaCode Phase 3 工具系统使用演示

演示如何使用第三阶段开发的工具系统，包括：
- 工具注册和发现
- 文件读写操作 
- 命令执行
- 权限管理
"""

import asyncio
import os
from simacode.tools import ToolRegistry, execute_tool, ToolResultType
from simacode.permissions import PermissionManager


async def demo_basic_usage():
    """基本使用演示"""
    print("=== SimaCode Phase 3 工具系统使用演示 ===\n")
    
    # 1. 工具发现
    print("1. 已注册的工具:")
    tools = ToolRegistry.list_tools()
    for tool_name in tools:
        tool = ToolRegistry.get_tool(tool_name)
        print(f"   - {tool_name}: {tool.description}")
    
    # 2. 文件写入演示
    print("\n2. 文件写入演示:")
    demo_file = os.path.join(os.getcwd(), "phase3_test.txt")
    
    async for result in execute_tool('file_write', {
        'file_path': demo_file,
        'content': 'Hello from SimaCode Phase 3 Tool System!\n这是一个测试文件。',
        'encoding': 'utf-8'
    }):
        if result.type == ToolResultType.SUCCESS:
            print(f"   ✅ {result.content}")
            break
        elif result.type == ToolResultType.ERROR:
            print(f"   ❌ {result.content}")
            return
        elif result.type == ToolResultType.INFO:
            print(f"   ℹ️  {result.content}")
    
    # 3. 权限系统演示
    print("\n3. 权限系统演示:")
    pm = PermissionManager()
    
    # 允许的路径
    result = pm.check_file_permission(demo_file, "read")
    print(f"   当前目录文件权限: {'✅ 允许' if result.granted else '❌ 拒绝'}")
    
    # 禁止的路径
    result = pm.check_file_permission("/etc/passwd", "read")
    print(f"   系统文件权限: {'✅ 允许' if result.granted else '❌ 拒绝'} - {result.reason}")
    
    # 命令权限
    result = pm.check_command_permission("ls -la")
    print(f"   安全命令权限: {'✅ 允许' if result.granted else '❌ 拒绝'}")
    
    result = pm.check_command_permission("rm -rf /usr/local")
    print(f"   危险命令权限: {'✅ 允许' if result.granted else '❌ 拒绝'} - {result.reason}")
    
    # 4. 清理
    if os.path.exists(demo_file):
        os.remove(demo_file)
        print(f"\n🧹 清理文件: {demo_file}")


def demo_sync_usage():
    """同步使用演示"""
    print("\n=== 同步使用方式 ===")
    
    # 工具发现
    tools = ToolRegistry.list_tools()
    print(f"总共注册了 {len(tools)} 个工具")
    
    # 工具统计
    stats = ToolRegistry.get_registry_stats()
    print(f"工具统计: {stats['total_tools']} 个工具, {stats['total_executions']} 次执行")
    
    # 权限管理器使用
    pm = PermissionManager()
    
    # 检查路径权限
    current_dir = os.getcwd()
    result = pm.check_path_access(current_dir, "access")
    print(f"当前目录访问: {'✅ 允许' if result.granted else '❌ 拒绝'}")
    
    # 获取配置信息
    allowed_paths = pm.get_allowed_paths()
    print(f"允许访问 {len(allowed_paths)} 个路径")


if __name__ == "__main__":
    print("🚀 SimaCode Phase 3 工具系统演示")
    print("=" * 50)
    
    # 异步演示
    asyncio.run(demo_basic_usage())
    
    # 同步演示
    demo_sync_usage()
    
    print("\n📚 使用说明:")
    print("1. 工具通过 ToolRegistry 进行注册和发现")
    print("2. 使用 execute_tool(tool_name, params) 执行工具")
    print("3. 所有操作都经过权限系统验证")
    print("4. 支持异步流式执行和结果处理")
    print("5. 输入参数通过 Pydantic 进行验证")
    
    print("\n🔧 核心组件:")
    print("- BashTool: 安全的命令执行")
    print("- FileReadTool: 安全的文件读取") 
    print("- FileWriteTool: 安全的文件写入")
    print("- PermissionManager: 权限控制系统")
    print("- ToolRegistry: 工具注册和管理")
    
    print("\n✨ 演示完成！")