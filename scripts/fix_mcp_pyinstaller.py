import sys
import os

def fix_mcp_config_for_pyinstaller():
    """修复PyInstaller环境下的MCP配置"""

    # 获取当前Python解释器路径
    current_python = sys.executable
    print(f"当前Python解释器: {current_python}")

    # 检查.simacode/config.yaml是否存在
    config_path = ".simacode/config.yaml"

    if not os.path.exists(config_path):
        print(f"配置文件不存在: {config_path}")
        return

    # 读取配置文件
    with open(config_path, 'r', encoding='utf-8') as f:
        content = f.read()

    print("原始配置文件内容:")
    print("-" * 50)
    print(content)
    print("-" * 50)

    # 替换python命令为当前解释器路径
    # 处理各种可能的配置格式
    replacements = [
        ('command: ["python"', f'command: ["{current_python}"'),
        ('command: [python', f'command: ["{current_python}"'),
        ('- python\n', f'- "{current_python}"\n'),
        ('command:\n      - python', f'command:\n      - "{current_python}"'),
    ]

    new_content = content
    changes_made = False

    for old, new in replacements:
        if old in new_content:
            new_content = new_content.replace(old, new)
            changes_made = True
            print(f"替换: {old} -> {new}")

    if changes_made:
        # 备份原文件
        backup_path = f"{config_path}.backup"
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"原文件已备份至: {backup_path}")

        # 写入修改后的配置
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        print("\n修改后配置文件内容:")
        print("-" * 50)
        print(new_content)
        print("-" * 50)
        print("✓ 配置文件已修改")
    else:
        print("未找到需要修改的python命令配置")

if __name__ == "__main__":
    fix_mcp_config_for_pyinstaller()