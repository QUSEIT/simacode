# MCP Tools 文件日志系统使用指南

## 概述

为了解决 MCP tools 中 logger 信息不可见的问题，我们创建了一个专门的文件日志系统，将 MCP tools 的调试消息写入 `.simacode/logs` 目录。

## 特性

- **自动目录创建**: 自动创建 `.simacode/logs` 目录
- **结构化日志**: JSON 格式的日志记录，便于解析和分析
- **线程安全**: 支持多线程环境下的安全文件操作
- **日志轮换**: 自动管理日志文件大小，防止磁盘空间问题
- **Session 上下文**: 支持记录 session ID 和相关上下文信息
- **便捷函数**: 提供多个日志级别的便捷函数

## 快速开始

### 导入模块

```python
from src.simacode.utils.mcp_logger import (
    mcp_file_log, 
    mcp_debug, 
    mcp_info, 
    mcp_warning, 
    mcp_error
)
```

### 基本使用

```python
# 基本日志记录
mcp_info("Tool started", tool_name="my_tool")

# 带数据的日志记录
mcp_debug("Processing request", {
    "user_input": "create a course",
    "template": "modern"
}, tool_name="my_tool")

# 带 session 上下文的日志记录
mcp_info("Session context received", {
    "session_state": "executing",
    "current_task": "create_content"
}, tool_name="my_tool", session_id="session_123")

# 错误日志记录
try:
    # some operation
    pass
except Exception as e:
    mcp_error("Operation failed", {
        "error_type": type(e).__name__,
        "error_message": str(e)
    }, tool_name="my_tool")
```

## API 参考

### 主要函数

#### `mcp_file_log(level, message, data=None, tool_name="mcp_tools", session_id=None, **kwargs)`

主要的日志记录函数。

**参数:**
- `level`: 日志级别 ("debug", "info", "warning", "error", "critical")
- `message`: 日志消息
- `data`: 附加数据 (dict 或 string)
- `tool_name`: MCP 工具名称 (用作日志文件名)
- `session_id`: 可选的 session ID
- `**kwargs`: 其他键值对

#### 便捷函数

```python
mcp_debug(message, data=None, **kwargs)
mcp_info(message, data=None, **kwargs)
mcp_warning(message, data=None, **kwargs)
mcp_error(message, data=None, **kwargs)
mcp_critical(message, data=None, **kwargs)
```

### 配置函数

#### `setup_mcp_logger(log_dir=None, max_file_size=None, max_files=None, enable_console=False)`

配置 MCP 日志系统。

**参数:**
- `log_dir`: 自定义日志目录 (默认: `.simacode/logs`)
- `max_file_size`: 单个日志文件最大大小 (默认: 10MB)
- `max_files`: 保留的日志文件数量 (默认: 5)
- `enable_console`: 是否同时输出到控制台 (默认: False)

### 工具函数

#### `get_log_content(tool_name="mcp_tools", lines=None, level_filter=None)`

读取日志内容。

#### `clear_logs(tool_name=None)`

清理日志文件。

#### `get_mcp_log_path(tool_name="mcp_tools")`

获取日志文件路径。

## 日志格式

日志以 JSON 格式存储，每行一个 JSON 对象：

```json
{
  "timestamp": "2025-09-11T11:57:49.887346",
  "level": "INFO",
  "tool_name": "ticmaker",
  "message": "Course creation started",
  "session_id": "session_456",
  "data": {
    "user_input": "Create a test course",
    "course_title": "Test Course",
    "session_context": {
      "session_state": "executing",
      "current_task": "create_content"
    }
  }
}
```

## 在 MCP Tools 中的集成

### TICMaker 示例

在 `mcp_ticmaker_stdio_server.py` 中的集成示例：

```python
# 导入日志模块
try:
    from src.simacode.utils.mcp_logger import mcp_file_log, mcp_debug, mcp_info, mcp_warning, mcp_error
    MCP_LOGGING_AVAILABLE = True
except ImportError:
    # 提供回退函数
    MCP_LOGGING_AVAILABLE = False
    def mcp_file_log(*args, **kwargs): pass
    # ... 其他回退函数

# 在关键操作中添加日志
class TICMakerClient:
    def __init__(self, config):
        # ... 初始化代码
        
        # 记录初始化日志
        mcp_info("TICMaker client initialized", {
            "output_dir": str(self.output_dir),
            "default_template": self.config.default_template
        }, tool_name="ticmaker")
    
    async def create_interactive_course(self, user_input, **kwargs):
        # 记录开始
        mcp_info("Course creation started", {
            "user_input": user_input,
            "session_context": session_context
        }, tool_name="ticmaker", session_id=session_context.get('session_id'))
        
        try:
            # ... 处理逻辑
            
            # 记录成功
            mcp_info("Course creation completed", {
                "file_path": str(file_path),
                "execution_time": execution_time
            }, tool_name="ticmaker")
            
        except Exception as e:
            # 记录错误
            mcp_error("Course creation failed", {
                "error_type": type(e).__name__,
                "error_message": str(e)
            }, tool_name="ticmaker")
            raise
```

## 调试和监控

### 查看日志

```bash
# 查看 TICMaker 日志
cat .simacode/logs/ticmaker.log

# 使用 jq 格式化显示
cat .simacode/logs/ticmaker.log | jq .

# 过滤错误日志
grep '"level":"ERROR"' .simacode/logs/ticmaker.log

# 实时监控日志
tail -f .simacode/logs/ticmaker.log
```

### 日志分析

```bash
# 统计日志条目数
wc -l .simacode/logs/ticmaker.log

# 统计不同级别的日志
grep -o '"level":"[^"]*"' .simacode/logs/ticmaker.log | sort | uniq -c

# 查找特定 session 的日志
grep '"session_id":"session_123"' .simacode/logs/ticmaker.log
```

## 最佳实践

1. **工具名称**: 为每个 MCP 工具使用唯一的 `tool_name`
2. **Session 上下文**: 在可用时始终包含 `session_id`
3. **结构化数据**: 使用 `data` 参数传递结构化信息
4. **错误处理**: 在异常处理中记录详细的错误信息
5. **性能考虑**: 避免在高频操作中记录过多调试信息

## 故障排除

### 日志文件未创建

- 检查 `.simacode/logs` 目录权限
- 确认 `mcp_logger` 模块正确导入
- 查看控制台错误信息

### 日志内容缺失

- 确认日志函数调用正确
- 检查 `tool_name` 参数
- 验证日志级别设置

### 性能问题

- 调整 `max_file_size` 和 `max_files` 参数
- 减少调试级别日志的频率
- 考虑异步日志记录 (未来功能)

## 扩展建议

未来可以考虑添加的功能：

- 异步日志写入
- 日志聚合和分析工具
- Web 界面查看日志
- 日志告警系统
- 集成到 SimaCode 主界面

---

这个日志系统为 MCP tools 提供了强大的调试能力，帮助开发者更好地理解和调试 MCP 工具的行为。