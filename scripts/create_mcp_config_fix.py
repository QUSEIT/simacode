#!/usr/bin/env python3
"""
为PyInstaller环境创建正确的MCP配置文件

这个脚本会创建一个适用于PyInstaller环境的MCP配置文件，
使用当前Python解释器的完整路径，避免"python"命令问题。
"""

import sys
import os
import yaml
from pathlib import Path

def create_pyinstaller_mcp_config():
    """为PyInstaller环境创建MCP配置"""

    # 获取当前Python解释器的完整路径
    current_python = sys.executable
    print(f"当前Python解释器: {current_python}")

    # 检测是否在PyInstaller环境
    is_pyinstaller = hasattr(sys, '_MEIPASS')
    print(f"PyInstaller环境: {is_pyinstaller}")

    # 配置模板
    mcp_config = {
        'mcp': {
            'enabled': True,
            'health_check_interval': 30,
            'servers': {
                'ticmaker': {
                    'type': 'stdio',
                    'command': [current_python, 'ticmaker_mcp_tool_ticmaker_stdio_server.py'],
                    'args': ['--config', '.simacode/config.yaml'],
                    'enabled': True,
                    'timeout': 300,
                    'max_retries': 3,
                    'environment': {
                        'PYTHONPATH': 'src' if not is_pyinstaller else None,
                        'PYTHONUNBUFFERED': '1'  # 确保输出不被缓冲
                    }
                },
                'email_smtp': {
                    'type': 'stdio',
                    'command': [current_python, 'ticmaker_mcp_tool_send_email.py'],
                    'enabled': True,
                    'timeout': 300,
                    'max_retries': 3,
                    'environment': {
                        'PYTHONPATH': 'src' if not is_pyinstaller else None,
                        'PYTHONUNBUFFERED': '1'
                    }
                }
            }
        }
    }

    # 清理None值
    def clean_none_values(obj):
        if isinstance(obj, dict):
            return {k: clean_none_values(v) for k, v in obj.items() if v is not None}
        elif isinstance(obj, list):
            return [clean_none_values(item) for item in obj if item is not None]
        return obj

    mcp_config = clean_none_values(mcp_config)

    # 确保.simacode目录存在
    config_dir = Path('.simacode')
    config_dir.mkdir(exist_ok=True)

    # 保存配置文件
    config_file = config_dir / 'config.yaml'

    # 备份现有配置
    if config_file.exists():
        backup_file = config_dir / 'config.yaml.backup'
        print(f"备份现有配置到: {backup_file}")
        with open(config_file, 'r', encoding='utf-8') as f:
            with open(backup_file, 'w', encoding='utf-8') as bf:
                bf.write(f.read())

    # 写入新配置
    with open(config_file, 'w', encoding='utf-8') as f:
        yaml.dump(mcp_config, f, default_flow_style=False, allow_unicode=True, indent=2)

    print(f"✓ MCP配置已保存到: {config_file}")
    print(f"✓ 使用Python解释器: {current_python}")

    return str(config_file)

def verify_config_file(config_path):
    """验证配置文件格式"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        print("\n=== 配置文件验证 ===")

        # 检查MCP配置
        if 'mcp' in config:
            mcp_config = config['mcp']
            print(f"MCP启用: {mcp_config.get('enabled', False)}")

            if 'servers' in mcp_config:
                servers = mcp_config['servers']
                print(f"配置的服务器数量: {len(servers)}")

                for name, server_config in servers.items():
                    command = server_config.get('command', [])
                    if command:
                        print(f"  {name}: {' '.join(command)}")

            print("✓ 配置文件格式正确")
            return True
        else:
            print("✗ 配置文件中缺少MCP配置")
            return False

    except yaml.YAMLError as e:
        print(f"✗ YAML格式错误: {e}")
        return False
    except Exception as e:
        print(f"✗ 配置文件验证失败: {e}")
        return False

if __name__ == "__main__":
    print("=== PyInstaller MCP配置修复工具 ===")

    # 显示当前环境信息
    print(f"\n当前工作目录: {os.getcwd()}")
    print(f"Python版本: {sys.version}")
    print(f"Python解释器: {sys.executable}")
    print(f"PyInstaller环境: {hasattr(sys, '_MEIPASS')}")

    try:
        # 创建配置文件
        config_path = create_pyinstaller_mcp_config()

        # 验证配置文件
        if verify_config_file(config_path):
            print(f"\n✅ 配置修复完成!")
            print(f"现在可以重启应用程序测试MCP连接")
        else:
            print(f"\n❌ 配置文件验证失败，请检查生成的配置")

    except Exception as e:
        print(f"\n❌ 配置修复失败: {e}")

    print("\n=== 使用说明 ===")
    print("1. 重启你的TICMaker应用")
    print("2. 观察日志中的MCP连接状态")
    print("3. 如果仍有问题，检查MCP工具服务器文件是否存在且可执行")