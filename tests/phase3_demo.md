# SimaCode Phase 3 工具系统使用指南

## 概述

Phase 3 完成了一个完整的工具系统，包括三个核心工具和完善的权限管理系统。

## 核心组件

### 1. 可用工具

- **BashTool** (`bash`): 安全的系统命令执行
- **FileReadTool** (`file_read`): 安全的文件读取
- **FileWriteTool** (`file_write`): 安全的文件写入

### 2. 核心类

- **ToolRegistry**: 工具注册和管理
- **PermissionManager**: 权限控制系统
- **Tool**: 工具基类
- **ToolResult**: 执行结果封装

## 基本使用方法

### 1. 工具发现和注册

```python
from simacode.tools import ToolRegistry

# 获取所有已注册的工具
tools = ToolRegistry.list_tools()
print(f"可用工具: {tools}")  # ['bash', 'file_read', 'file_write']

# 获取特定工具
file_writer = ToolRegistry.get_tool('file_write')
print(f"工具描述: {file_writer.description}")
```

### 2. 通过名称执行工具

```python
import asyncio
from simacode.tools import execute_tool, ToolResultType

async def demo():
    # 文件写入
    async for result in execute_tool('file_write', {
        'file_path': './test.txt',
        'content': 'Hello World!',
        'encoding': 'utf-8'
    }):
        if result.type == ToolResultType.SUCCESS:
            print(f"成功: {result.content}")
        elif result.type == ToolResultType.ERROR:
            print(f"错误: {result.content}")

asyncio.run(demo())
```

### 3. 直接使用工具实例

```python
async def direct_tool_usage():
    # 获取工具实例
    tool = ToolRegistry.get_tool('file_write')
    
    # 准备输入数据
    input_data = {
        'file_path': './example.txt',
        'content': '直接使用工具示例'
    }
    
    # 验证输入
    validated_input = await tool.validate_input(input_data)
    
    # 检查权限
    has_permission = await tool.check_permissions(validated_input)
    
    if has_permission:
        # 执行工具
        async for result in tool.execute(validated_input):
            print(f"{result.type.value}: {result.content}")
```

## 权限系统使用

### 1. 权限检查

```python
from simacode.permissions import PermissionManager

pm = PermissionManager()

# 文件权限检查
result = pm.check_file_permission("/path/to/file.txt", "write")
if result.granted:
    print("权限允许")
else:
    print(f"权限拒绝: {result.reason}")

# 命令权限检查
result = pm.check_command_permission("ls -la")
print(f"命令权限: {'允许' if result.granted else '拒绝'}")
```

### 2. 路径权限

```python
# 检查路径访问权限
result = pm.check_path_access("/etc", "access")
print(f"路径权限: {result.level.value}")

# 获取配置信息
allowed_paths = pm.get_allowed_paths()
forbidden_paths = pm.get_forbidden_paths()
```

## 工具参数说明

### BashTool 参数

```python
{
    'command': 'ls -la',           # 要执行的命令
    'timeout': 30,                 # 超时时间（秒）
    'working_directory': '/path',  # 工作目录
    'capture_output': True,        # 是否捕获输出
    'shell': True,                 # 是否使用shell
    'environment': {'VAR': 'val'}  # 环境变量
}
```

### FileReadTool 参数

```python
{
    'file_path': '/path/to/file.txt',  # 文件路径
    'encoding': 'utf-8',               # 文件编码
    'max_size': 10485760,              # 最大文件大小（字节）
    'start_line': 1,                   # 起始行号
    'end_line': 100,                   # 结束行号
    'max_lines': 50,                   # 最大行数
    'binary_mode': False               # 是否二进制模式
}
```

### FileWriteTool 参数

```python
{
    'file_path': '/path/to/file.txt',  # 文件路径
    'content': 'file content',         # 文件内容
    'encoding': 'utf-8',               # 编码格式
    'mode': 'write',                   # 写入模式: write/append/insert
    'insert_line': 5,                  # 插入行号（insert模式）
    'create_backup': True,             # 是否创建备份
    'create_directories': False,       # 是否创建目录
    'preserve_permissions': True,      # 是否保持权限
    'line_ending': 'auto'              # 行结束符: auto/unix/windows/mac
}
```

## 结果处理

### ToolResult 类型

```python
from simacode.tools import ToolResultType

# 结果类型
ToolResultType.INFO      # 信息
ToolResultType.OUTPUT    # 输出内容
ToolResultType.SUCCESS   # 成功
ToolResultType.ERROR     # 错误
ToolResultType.WARNING   # 警告
ToolResultType.PROGRESS  # 进度
```

### 结果处理示例

```python
async for result in execute_tool('bash', {'command': 'ls -la'}):
    if result.type == ToolResultType.OUTPUT:
        print(f"命令输出: {result.content}")
    elif result.type == ToolResultType.ERROR:
        print(f"执行错误: {result.content}")
        break
    elif result.type == ToolResultType.SUCCESS:
        print("命令执行成功")
        break
```

## 安全特性

### 1. 权限控制

- **路径限制**: 只能访问配置中允许的路径
- **命令过滤**: 自动拦截危险命令
- **权限缓存**: 提高重复检查的性能

### 2. 输入验证

- **Pydantic 验证**: 所有输入参数都经过严格验证
- **类型检查**: 确保参数类型正确
- **范围检查**: 验证数值范围和字符串格式

### 3. 执行保护

- **超时控制**: 防止长时间运行的命令
- **资源限制**: 文件大小和行数限制
- **原子操作**: 文件写入使用临时文件确保原子性

## 扩展开发

### 创建自定义工具

```python
from simacode.tools.base import Tool, ToolInput, ToolResult, ToolResultType
from typing import AsyncGenerator, Dict, Any, Type

class CustomInput(ToolInput):
    message: str

class CustomTool(Tool):
    def __init__(self):
        super().__init__(
            name="custom",
            description="自定义工具示例",
            version="1.0.0"
        )
    
    def get_input_schema(self) -> Type[ToolInput]:
        return CustomInput
    
    async def validate_input(self, input_data: Dict[str, Any]) -> CustomInput:
        return CustomInput(**input_data)
    
    async def check_permissions(self, input_data: CustomInput) -> bool:
        return True  # 根据需要实现权限检查
    
    async def execute(self, input_data: CustomInput) -> AsyncGenerator[ToolResult, None]:
        yield ToolResult(
            type=ToolResultType.SUCCESS,
            content=f"处理消息: {input_data.message}"
        )

# 注册自定义工具
from simacode.tools import ToolRegistry
custom_tool = CustomTool()
ToolRegistry.register(custom_tool)
```

## 运行演示

```bash
# 运行完整演示
python tests/phase3_demo.py

# 运行工具系统测试
python -m pytest tests/test_tool_system.py -v
```

## 常见问题

### Q: 为什么文件操作被拒绝？
A: 检查文件路径是否在允许的路径列表中，默认只允许当前工作目录。

### Q: 如何修改权限配置？
A: 通过修改配置文件或创建自定义的 PermissionManager 实例。

### Q: 工具执行异常如何处理？
A: 所有异常都会通过 ToolResult 返回，类型为 ERROR，包含详细错误信息。

### Q: 如何添加新的工具？
A: 继承 Tool 基类，实现必要的方法，然后通过 ToolRegistry.register() 注册。

---

更多详细信息请参考：
- 源码文档: `src/simacode/tools/`
- 测试用例: `tests/test_tool_system.py`
- 权限配置: `src/simacode/permissions/`