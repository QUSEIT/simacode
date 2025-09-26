#!/usr/bin/env python3
"""
设置MCP环境变量

这个脚本通过设置环境变量来解决PyInstaller环境下的
Python解释器路径问题，避免修改核心代码。
"""

import sys
import os
import subprocess
from pathlib import Path

def setup_mcp_python_env():
    """设置MCP需要的Python环境变量"""

    # 获取当前Python解释器路径
    current_python = sys.executable
    print(f"当前Python解释器: {current_python}")

    # 设置环境变量
    os.environ['MCP_PYTHON_EXECUTABLE'] = current_python
    os.environ['PYTHONUNBUFFERED'] = '1'  # 防止输出缓冲

    print(f"✓ 设置环境变量 MCP_PYTHON_EXECUTABLE = {current_python}")
    print(f"✓ 设置环境变量 PYTHONUNBUFFERED = 1")

    return current_python

def create_python_symlink():
    """在当前目录创建python符号链接（仅限Unix系统）"""

    current_python = sys.executable

    # 检查是否是Unix系统
    if os.name != 'posix':
        print("⚠️  符号链接方案仅适用于Unix系统")
        return None

    # 创建符号链接
    python_link = Path('./python')

    try:
        # 如果已存在，先删除
        if python_link.exists() or python_link.is_symlink():
            python_link.unlink()

        # 创建符号链接
        python_link.symlink_to(current_python)
        print(f"✓ 创建Python符号链接: ./python -> {current_python}")

        # 测试符号链接
        result = subprocess.run(['./python', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✓ 符号链接测试成功: {result.stdout.strip()}")
            return str(python_link.resolve())
        else:
            print(f"✗ 符号链接测试失败")
            return None

    except Exception as e:
        print(f"✗ 创建符号链接失败: {e}")
        return None

def create_python_alias_config():
    """创建使用Python路径别名的MCP配置"""

    current_python = sys.executable

    # 尝试使用符号链接
    python_link = create_python_symlink()
    if python_link:
        python_command = './python'
    else:
        # 回退到完整路径
        python_command = current_python

    print(f"将在配置中使用: {python_command}")

    # 创建配置内容
    config_content = f"""
# PyInstaller环境MCP配置
mcp:
  enabled: true
  health_check_interval: 30
  servers:
    ticmaker:
      type: stdio
      command: ["{python_command}", "ticmaker_mcp_tool_ticmaker_stdio_server.py"]
      args: ["--config", ".simacode/config.yaml"]
      enabled: true
      timeout: 300
      max_retries: 3
      environment:
        PYTHONUNBUFFERED: "1"

    email_smtp:
      type: stdio
      command: ["{python_command}", "ticmaker_mcp_tool_send_email.py"]
      enabled: true
      timeout: 300
      max_retries: 3
      environment:
        PYTHONUNBUFFERED: "1"
"""

    return config_content.strip()

def test_mcp_server_startup():
    """测试MCP服务器启动"""

    print("\n=== 测试MCP服务器启动 ===")

    # 查找MCP服务器文件
    mcp_servers = [
        "ticmaker_mcp_tool_ticmaker_stdio_server.py",
        "ticmaker_mcp_tool_send_email.py"
    ]

    current_python = sys.executable

    for server_file in mcp_servers:
        if not os.path.exists(server_file):
            print(f"⚠️  服务器文件不存在: {server_file}")
            continue

        print(f"\n测试启动: {server_file}")

        try:
            # 启动服务器进程
            process = subprocess.Popen(
                [current_python, server_file, "--help"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # 等待短时间
            try:
                stdout, stderr = process.communicate(timeout=3)

                if process.returncode == 0 or "usage:" in stdout.lower() or "help" in stdout.lower():
                    print(f"✓ {server_file} 可以正常启动")
                else:
                    print(f"⚠️  {server_file} 启动返回码: {process.returncode}")
                    if stderr:
                        print(f"   错误: {stderr[:100]}...")

            except subprocess.TimeoutExpired:
                process.kill()
                print(f"⚠️  {server_file} 启动超时（可能正常，服务器在等待输入）")

        except Exception as e:
            print(f"✗ 测试 {server_file} 失败: {e}")

def main():
    """主函数"""

    print("=== MCP环境设置工具（PyInstaller兼容） ===")

    # 显示环境信息
    print(f"\n当前环境:")
    print(f"  工作目录: {os.getcwd()}")
    print(f"  Python版本: {sys.version}")
    print(f"  Python路径: {sys.executable}")
    print(f"  PyInstaller环境: {hasattr(sys, '_MEIPASS')}")
    print(f"  操作系统: {os.name}")

    # 设置环境变量
    print(f"\n=== 设置环境变量 ===")
    python_path = setup_mcp_python_env()

    # 测试MCP服务器
    test_mcp_server_startup()

    # 创建推荐配置
    print(f"\n=== 推荐配置 ===")
    config_content = create_python_alias_config()
    print("建议的MCP配置内容:")
    print("-" * 50)
    print(config_content)
    print("-" * 50)

    # 保存配置建议
    config_file = ".simacode/mcp_config_suggestion.yaml"
    os.makedirs(os.path.dirname(config_file), exist_ok=True)

    with open(config_file, 'w', encoding='utf-8') as f:
        f.write(config_content)

    print(f"\n✓ 配置建议已保存到: {config_file}")
    print("你可以将此内容复制到 .simacode/config.yaml 中")

    print(f"\n=== 总结 ===")
    print("解决方案优先级:")
    print(f"1. 使用完整Python路径: {python_path}")
    if os.name == 'posix' and Path('./python').exists():
        print("2. 使用符号链接: ./python")
    print("3. 设置环境变量: MCP_PYTHON_EXECUTABLE")
    print("\n重启应用程序后测试MCP连接状态")

if __name__ == "__main__":
    main()