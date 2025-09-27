import subprocess
import sys
import os
import json
import time
from pathlib import Path

print("=== PyInstaller环境MCP诊断 ===")

# 1. 分析当前Python环境
print("\n=== 当前Python环境分析 ===")
print(f"sys.executable: {sys.executable}")
print(f"Python版本: {sys.version}")
print(f"当前工作目录: {os.getcwd()}")
print(f"是否PyInstaller环境: {hasattr(sys, '_MEIPASS')}")

if hasattr(sys, '_MEIPASS'):
    print(f"PyInstaller临时目录: {sys._MEIPASS}")

print(f"sys.path前5项:")
for i, path in enumerate(sys.path[:5]):
    print(f"  {i}: {path}")

# 2. 检查python命令可用性
print("\n=== python命令检查 ===")
commands_to_test = ["python", "python3", sys.executable]

for cmd in commands_to_test:
    try:
        result = subprocess.run(
            [cmd, "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print(f"✓ {cmd}: {result.stdout.strip()}")
        else:
            print(f"✗ {cmd}: 返回码{result.returncode}, {result.stderr.strip()}")
    except FileNotFoundError:
        print(f"✗ {cmd}: 命令不存在")
    except subprocess.TimeoutExpired:
        print(f"✗ {cmd}: 超时")
    except Exception as e:
        print(f"✗ {cmd}: {e}")

# 3. 测试MCP工具服务器可执行性
print("\n=== MCP工具服务器可执行性测试 ===")

# 检查工具服务器文件
mcp_servers = [
    "ticmaker_mcp_tool_ticmaker_stdio_server.py",
    "ticmaker_mcp_tool_send_email.py"
]

for server_file in mcp_servers:
    print(f"\n--- 测试 {server_file} ---")

    if not os.path.exists(server_file):
        print(f"✗ 文件不存在: {server_file}")
        continue

    print(f"✓ 文件存在: {server_file}")
    print(f"  文件大小: {os.path.getsize(server_file)} bytes")
    print(f"  是否可读: {os.access(server_file, os.R_OK)}")

    # 测试不同Python命令执行
    for cmd in [sys.executable, "python"]:
        if cmd == "python":
            # 先检查python是否可用
            try:
                subprocess.run([cmd, "--version"], capture_output=True, timeout=2)
            except:
                print(f"✗ 跳过{cmd}测试 (命令不可用)")
                continue

        print(f"\n  使用 {cmd} 测试:")

        try:
            # 尝试启动但立即终止，观察错误
            process = subprocess.Popen(
                [cmd, server_file, "--help"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # 等待短时间
            try:
                stdout, stderr = process.communicate(timeout=3)
                print(f"    返回码: {process.returncode}")

                if stdout.strip():
                    print(f"    STDOUT: {stdout.strip()[:200]}...")
                if stderr.strip():
                    print(f"    STDERR: {stderr.strip()[:200]}...")

            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                print(f"    进程超时终止")
                if stderr.strip():
                    print(f"    STDERR: {stderr.strip()[:200]}...")

        except FileNotFoundError as e:
            print(f"    ✗ 文件未找到: {e}")
        except Exception as e:
            print(f"    ✗ 执行错误: {e}")

# 4. 测试基本导入
print("\n=== Python模块导入测试 ===")

test_imports = [
    "asyncio",
    "json",
    "logging",
    "sys",
    "os",
    "pathlib",
    "subprocess"
]

for module in test_imports:
    try:
        __import__(module)
        print(f"✓ {module}")
    except ImportError as e:
        print(f"✗ {module}: {e}")

# 5. 环境变量检查
print("\n=== 关键环境变量检查 ===")

important_env_vars = [
    "PYTHONPATH",
    "PATH",
    "HOME",
    "PWD",
    "TMPDIR"
]

for var in important_env_vars:
    value = os.environ.get(var, "未设置")
    print(f"{var}: {value}")

# 6. 模拟MCP服务器启动过程
print("\n=== 模拟MCP服务器启动 ===")

server_file = "ticmaker_mcp_tool_ticmaker_stdio_server.py"
if os.path.exists(server_file):
    print(f"测试启动: {server_file}")

    # 使用sys.executable（推荐方式）
    try:
        print("  使用sys.executable启动...")
        process = subprocess.Popen(
            [sys.executable, server_file],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # 发送测试消息
        test_msg = {
            "jsonrpc": "2.0",
            "id": "test-1",
            "method": "ping"
        }

        test_json = json.dumps(test_msg) + "\n"

        try:
            # 发送消息并等待响应
            stdout, stderr = process.communicate(input=test_json, timeout=5)

            print(f"    进程返回码: {process.returncode}")

            if stdout.strip():
                print(f"    STDOUT: {stdout.strip()}")

            if stderr.strip():
                print(f"    STDERR: {stderr.strip()}")

        except subprocess.TimeoutExpired:
            print("    ✗ 进程响应超时")
            process.kill()
            stdout, stderr = process.communicate()
            if stderr.strip():
                print(f"    终止后STDERR: {stderr.strip()}")

    except Exception as e:
        print(f"    ✗ 启动失败: {e}")

else:
    print(f"✗ 服务器文件不存在: {server_file}")

# 7. 文件权限和目录结构检查
print("\n=== 文件系统检查 ===")

print(f"当前目录权限:")
print(f"  可读: {os.access('.', os.R_OK)}")
print(f"  可写: {os.access('.', os.W_OK)}")
print(f"  可执行: {os.access('.', os.X_OK)}")

print(f"\n当前目录内容:")
for item in sorted(os.listdir('.')):
    if item.endswith('.py') or item.startswith('.simacode'):
        item_path = Path(item)
        print(f"  {item} ({'文件' if item_path.is_file() else '目录'})")

# 8. 配置文件检查
config_files = [".simacode/config.yaml", "config.yaml"]
print(f"\n配置文件检查:")
for config_file in config_files:
    if os.path.exists(config_file):
        print(f"✓ {config_file} (大小: {os.path.getsize(config_file)} bytes)")
    else:
        print(f"✗ {config_file} 不存在")

print("\n=== 诊断完成 ===")
print("\n推荐解决方案:")
print("1. 在MCP配置中使用sys.executable替代python命令")
print("2. 确保所有Python模块正确打包")
print("3. 检查环境变量和工作目录设置")
print("4. 验证配置文件路径正确性")