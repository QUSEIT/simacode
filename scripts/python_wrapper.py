#!/usr/bin/env python3
"""
Python包装器脚本

这个脚本作为'python'命令的替代品，在PyInstaller环境中
自动使用正确的Python解释器来启动MCP工具服务器。
"""

import sys
import subprocess
import os

def main():
    """主函数：转发参数到正确的Python解释器"""

    # 获取真实的Python解释器路径
    real_python = sys.executable

    # 获取传递给这个脚本的参数（跳过脚本名本身）
    args = sys.argv[1:]

    print(f"Python包装器: 使用 {real_python} 执行: {' '.join(args)}", file=sys.stderr)

    try:
        # 使用真实的Python解释器执行命令
        result = subprocess.run([real_python] + args, check=False)
        sys.exit(result.returncode)

    except Exception as e:
        print(f"Python包装器错误: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()