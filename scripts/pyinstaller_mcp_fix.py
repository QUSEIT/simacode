"""
PyInstaller环境下MCP连接修复补丁

这个脚本提供了两种方式修复PyInstaller环境下MCP工具服务器启动失败的问题：
1. 修改StdioTransport类以自动检测PyInstaller环境
2. 提供运行时补丁功能
"""

import sys
import os
from typing import List, Dict

def detect_pyinstaller_environment() -> bool:
    """检测是否在PyInstaller环境中运行"""
    return hasattr(sys, '_MEIPASS')

def fix_python_command_for_pyinstaller(command: List[str]) -> List[str]:
    """为PyInstaller环境修复Python命令"""

    if not detect_pyinstaller_environment():
        return command

    # 如果命令以'python'开始，替换为当前解释器
    if command and command[0] in ['python', 'python3']:
        fixed_command = [sys.executable] + command[1:]
        print(f"PyInstaller环境检测: 替换 {command[0]} -> {sys.executable}")
        return fixed_command

    return command

def patch_stdio_transport():
    """运行时补丁StdioTransport类"""

    try:
        from src.simacode.mcp.connection import StdioTransport

        # 保存原始的__init__方法
        original_init = StdioTransport.__init__

        def patched_init(self, command: list, args: list = None, env: Dict[str, str] = None):
            """补丁版本的__init__方法"""

            # 修复PyInstaller环境下的命令
            fixed_command = fix_python_command_for_pyinstaller(command)

            # 调用原始初始化
            original_init(self, fixed_command, args, env)

            print(f"MCP StdioTransport 已补丁: {' '.join(fixed_command)}")

        # 应用补丁
        StdioTransport.__init__ = patched_init
        print("✓ StdioTransport 补丁应用成功")

        return True

    except ImportError as e:
        print(f"✗ 无法导入StdioTransport: {e}")
        return False
    except Exception as e:
        print(f"✗ 补丁应用失败: {e}")
        return False

def create_fixed_stdio_transport():
    """创建修复版本的StdioTransport类代码"""

    fixed_code = '''
# 修复版本的StdioTransport类
# 添加到 src/simacode/mcp/connection.py 的 StdioTransport.__init__ 方法中

def __init__(self, command: list, args: list = None, env: Dict[str, str] = None):
    # PyInstaller环境检测和修复
    if hasattr(sys, '_MEIPASS') and command and command[0] in ['python', 'python3']:
        # 在PyInstaller环境中，使用当前解释器而不是'python'命令
        command = [sys.executable] + command[1:]
        logger.info(f"PyInstaller环境检测: 使用 {sys.executable} 替代 python 命令")

    self.command = command
    self.args = args or []
    self.env = env
    self.process: Optional[asyncio.subprocess.Process] = None
    self._connected = False
    self._read_lock = asyncio.Lock()
    self._write_lock = asyncio.Lock()
'''

    return fixed_code

def test_python_commands():
    """测试不同Python命令的可用性"""

    print("=== Python命令可用性测试 ===")

    commands = ["python", "python3", sys.executable]
    results = {}

    for cmd in commands:
        try:
            import subprocess
            result = subprocess.run(
                [cmd, "-c", "print('OK')"],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                results[cmd] = "✓ 可用"
                print(f"{cmd}: ✓ 可用")
            else:
                results[cmd] = f"✗ 错误码{result.returncode}"
                print(f"{cmd}: ✗ 错误码{result.returncode}")

        except FileNotFoundError:
            results[cmd] = "✗ 未找到"
            print(f"{cmd}: ✗ 未找到")
        except subprocess.TimeoutExpired:
            results[cmd] = "✗ 超时"
            print(f"{cmd}: ✗ 超时")
        except Exception as e:
            results[cmd] = f"✗ 异常: {e}"
            print(f"{cmd}: ✗ 异常: {e}")

    return results

def diagnose_mcp_startup_issue():
    """诊断MCP启动问题"""

    print("=== MCP启动问题诊断 ===")

    # 1. 环境检测
    is_pyinstaller = detect_pyinstaller_environment()
    print(f"PyInstaller环境: {is_pyinstaller}")
    print(f"当前Python: {sys.executable}")
    print(f"工作目录: {os.getcwd()}")

    # 2. Python命令测试
    python_results = test_python_commands()

    # 3. 分析结果
    print("\n=== 问题分析 ===")

    if is_pyinstaller:
        python_available = python_results.get("python", "").startswith("✓")

        if not python_available:
            print("🎯 问题原因: PyInstaller环境中'python'命令不可用")
            print("📝 解决方案: 使用sys.executable替代python命令")
        else:
            print("⚠️  python命令可用，但可能版本或环境不匹配")

    # 4. 提供修复建议
    print("\n=== 修复建议 ===")
    print("1. 应用StdioTransport补丁:")
    print("   - 运行: patch_stdio_transport()")
    print()
    print("2. 手动修改配置:")
    print(f"   - 将配置中的'python'替换为'{sys.executable}'")
    print()
    print("3. 代码修改:")
    print("   - 在StdioTransport.__init__中添加PyInstaller检测")

    return {
        'is_pyinstaller': is_pyinstaller,
        'python_results': python_results,
        'recommended_python': sys.executable
    }

if __name__ == "__main__":
    print("=== PyInstaller MCP修复工具 ===")

    # 执行诊断
    diagnosis = diagnose_mcp_startup_issue()

    # 如果在PyInstaller环境中，尝试应用补丁
    if diagnosis['is_pyinstaller']:
        print(f"\n正在尝试应用运行时补丁...")
        if patch_stdio_transport():
            print("✓ 补丁应用成功，可以尝试重启MCP服务器")
        else:
            print("✗ 运行时补丁失败，需要手动修改代码")
            print("\n手动修改代码:")
            print(create_fixed_stdio_transport())

    print("\n=== 修复完成 ===")