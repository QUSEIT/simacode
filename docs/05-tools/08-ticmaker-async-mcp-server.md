# TICMaker Async MCP Server

基于 MCP 异步任务增强特性的 TICMaker 互动教学内容创建服务器。

## 概述

`TICMaker Async MCP Server` 是原有 `mcp_ticmaker_stdio_server.py` 的增强版本，完全集成了 SimaCode 的 MCP 异步任务增强特性。该服务器能够智能检测任务复杂度，自动选择最佳执行模式，并提供实时进度回传。

## 核心特性

### 🚀 异步任务增强

- **智能任务复杂度检测**：自动分析用户输入和任务要求，分类为简单、标准或长时间运行任务
- **自动异步执行**：长时间运行和复杂任务自动使用异步执行模式
- **实时进度回传**：提供详细的任务执行进度和状态更新
- **错误恢复机制**：智能错误处理和自动回退功能

### 📊 性能优化

- **并发任务管理**：支持最多3个并发任务
- **智能超时管理**：默认5分钟超时，可配置
- **资源管理**：优化的内存使用和任务清理
- **网络优化**：异步 AI API 调用

### 🎯 增强功能

- **AI 增强内容生成**：异步 AI 课程介绍生成
- **Session Context 支持**：完整的会话上下文集成
- **进度监控**：每2秒间隔的进度更新
- **任务分类**：简单(10s)、标准(60s)、长时间运行(300s)

## 文件结构

```
tools/
├── mcp_ticmaker_async_stdio_server.py     # 异步增强版 MCP 服务器
├── mcp_ticmaker_stdio_server.py           # 原版 MCP 服务器
└── test_ticmaker_async.py                 # 异步功能测试脚本

src/simacode/default_config/
└── mcp_servers.yaml                       # 增加了 ticmaker_async 配置

docs/
└── ticmaker-async-mcp-server.md          # 本文档
```

## 配置说明

### MCP 服务器配置

在 `mcp_servers.yaml` 中新增了 `ticmaker_async` 配置：

```yaml
ticmaker_async:
  name: ticmaker_async
  enabled: false  # 启用异步版本时设置为 true
  type: stdio
  command: ["python", "tools/mcp_ticmaker_async_stdio_server.py"]
  args: ["--config", ".simacode/config.yaml"]
  environment:
    # 基础配置
    TICMAKER_OUTPUT_DIR: "${TICMAKER_OUTPUT_DIR:-.simacode/mcp/ticmaker_output}"
    TICMAKER_TEMPLATE: "${TICMAKER_TEMPLATE:-modern}"

    # AI 配置
    TICMAKER_AI_ENABLED: "${TICMAKER_AI_ENABLED:-true}"
    TICMAKER_AI_BASE_URL: "${TICMAKER_AI_BASE_URL:-https://openai.pgpt.cloud/v1}"
    TICMAKER_AI_API_KEY: "${TICMAKER_AI_API_KEY:-${OPENAI_API_KEY}}"
    TICMAKER_AI_MODEL: "${TICMAKER_AI_MODEL:-gpt-4o-mini}"

    # 异步任务配置
    TICMAKER_ASYNC_ENABLED: "${TICMAKER_ASYNC_ENABLED:-true}"
    TICMAKER_ASYNC_THRESHOLD: "${TICMAKER_ASYNC_THRESHOLD:-30.0}"
    TICMAKER_TASK_TIMEOUT: "${TICMAKER_TASK_TIMEOUT:-300.0}"

  # 异步任务增强配置
  long_running_tasks:
    enabled: true
    max_execution_time: 300
    progress_interval: 2
    heartbeat_interval: 30

  # 任务复杂度分类
  task_classifications:
    simple: { max_time: 10 }
    standard: { max_time: 60 }
    long: { max_time: 300 }
```

### 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `TICMAKER_ASYNC_ENABLED` | `true` | 启用异步任务检测 |
| `TICMAKER_ASYNC_THRESHOLD` | `30.0` | 异步执行阈值（秒） |
| `TICMAKER_TASK_TIMEOUT` | `300.0` | 任务超时时间（秒） |

## 工具接口

### create_interactive_course_async

创建交互式教学内容（异步增强版）

**参数：**
```json
{
  "user_input": "用户需求描述",
  "course_title": "课程标题（可选）",
  "file_path": "输出文件路径（可选）",
  "content_type": "course|slides|presentation|tutorial|lesson|workshop",
  "template_style": "modern|classic|minimal",
  "force_async": false,
  "_session_context": {
    "session_state": "会话状态",
    "current_task": "当前任务",
    "user_input": "用户输入"
  }
}
```

**响应示例：**
```json
{
  "success": true,
  "message": "Interactive course created successfully",
  "execution_time": 45.67,
  "async_enhanced": true,
  "task_complexity": "standard",
  "was_async_execution": true,
  "progress_updates_count": 15,
  "task_id": "create_course_a1b2c3d4",
  "metadata": {
    "file_path": "/path/to/output.html",
    "file_size": 125840,
    "action": "created"
  }
}
```

### modify_interactive_course_async

修改现有交互式教学内容（异步增强版）

**参数：**
```json
{
  "user_input": "修改需求描述",
  "file_path": "目标文件路径",
  "force_async": false,
  "_session_context": {
    "session_state": "content_modification",
    "current_task": "async_enhancement_demo"
  }
}
```

## 任务复杂度分类

### 简单任务 (Simple)
- **特征**：输入长度 < 100字符，包含"简单"、"基础"等关键词
- **执行模式**：同步执行
- **预期时间**：< 10秒

### 标准任务 (Standard)
- **特征**：输入长度 100-500字符，或包含"详细"、"复杂"关键词
- **执行模式**：根据 AI 启用状态决定
- **预期时间**：10-60秒

### 长时间运行任务 (Long Running)
- **特征**：输入长度 > 500字符，包含"大型"、"批量"、"完整项目"等关键词
- **执行模式**：强制异步执行
- **预期时间**：> 60秒

## 使用示例

### 启动服务器

```bash
# 直接启动
python tools/mcp_ticmaker_async_stdio_server.py --debug

# 或通过 SimaCode MCP 集成
# 在 mcp_servers.yaml 中启用 ticmaker_async
```

### 简单任务示例

```bash
# 通过 SimaCode CLI
simacode chat --react "使用 TICMaker 创建一个简单的数学基础介绍页面"
```

**预期行为**：
- 自动检测为简单任务
- 使用同步执行
- 快速完成（< 10秒）

### 复杂任务示例

```bash
# 通过 SimaCode CLI
simacode chat --react "使用 TICMaker 创建一个详细的高级数据科学课程，包含多个交互式练习、AI增强内容、完整课程结构、实战项目案例"
```

**预期行为**：
- 自动检测为长时间运行任务
- 使用异步执行
- 提供实时进度更新
- 执行时间 60-300秒

## 测试

### 运行测试脚本

```bash
python tools/test_ticmaker_async.py
```

**测试覆盖：**
- ✅ 服务器初始化
- ✅ 工具列表获取
- ✅ 简单任务执行
- ✅ 复杂任务执行
- ✅ 内容修改功能
- ✅ 异步检测准确性
- ✅ 进度回传机制

### 预期测试结果

```
📊 Test Results Summary:
==================================================
Initialization       | ✅ PASS
Tools List           | ✅ PASS
Simple Task          | ✅ PASS
Complex Task         | ✅ PASS
Modification Task    | ✅ PASS
==================================================
Total: 5/5 tests passed
🎉 All tests passed! TICMaker Async MCP Server is working correctly.
```

## 与原版对比

| 特性 | 原版 | 异步增强版 |
|------|------|------------|
| 任务检测 | 无 | ✅ 智能复杂度检测 |
| 异步执行 | 无 | ✅ 自动异步优化 |
| 进度回传 | 无 | ✅ 实时进度更新 |
| 并发管理 | 无 | ✅ 3任务并发限制 |
| 错误恢复 | 基础 | ✅ 智能回退机制 |
| 性能监控 | 无 | ✅ 详细执行统计 |
| 超时管理 | 固定 | ✅ 智能动态超时 |

## 监控和日志

### 日志级别

- **INFO**：任务开始/完成、配置信息
- **DEBUG**：详细执行步骤、进度更新
- **WARNING**：非致命错误、配置问题
- **ERROR**：执行失败、系统错误

### 关键指标

- **执行时间分布**：simple/standard/long 任务时间统计
- **异步使用率**：异步 vs 同步执行比例
- **进度更新频率**：平均进度回传次数
- **成功率**：任务完成成功率

## 故障排除

### 常见问题

1. **服务器启动失败**
   ```bash
   # 检查 Python 路径和依赖
   python tools/mcp_ticmaker_async_stdio_server.py --debug
   ```

2. **AI 调用失败**
   ```bash
   # 检查 API 密钥配置
   export TICMAKER_AI_API_KEY="your-api-key"
   ```

3. **异步检测不准确**
   ```bash
   # 调整检测阈值
   export TICMAKER_ASYNC_THRESHOLD="20.0"
   ```

### 调试模式

```bash
# 启用详细日志
python tools/mcp_ticmaker_async_stdio_server.py --debug

# 查看配置
python -c "from tools.mcp_ticmaker_async_stdio_server import load_async_config; print(load_async_config())"
```

## 集成指南

### 在 SimaCode 中使用

1. **启用异步版本**：
   ```yaml
   # mcp_servers.yaml
   ticmaker_async:
     enabled: true
   ```

2. **禁用原版**（可选）：
   ```yaml
   # mcp_servers.yaml
   ticmaker:
     enabled: false
   ```

3. **测试集成**：
   ```bash
   simacode mcp list | grep ticmaker
   simacode chat --react "创建复杂课程内容"
   ```

### 与 ReAct 引擎集成

异步版本完全兼容 SimaCode 的 ReAct 引擎，支持：

- ✅ Session Context 传递
- ✅ 任务状态跟踪
- ✅ 进度实时显示
- ✅ 错误自动处理

## 版本历史

### v2.0.0 (Current)
- ✅ 完整 MCP 异步任务增强集成
- ✅ 智能任务复杂度检测
- ✅ 实时进度回传机制
- ✅ 异步 AI 内容生成
- ✅ 增强的错误处理

### v1.0.0 (Original)
- 基础 stdio MCP 服务器
- 同步执行模式
- 基本内容生成功能

## 贡献

该项目是 SimaCode MCP 异步任务增强特性的完整实现示例。如需改进或扩展功能，请参考：

- `docs/05-tools/06-mcp-async-task-enhancement.md` - 异步任务增强架构文档
- `src/simacode/mcp/async_integration.py` - 异步任务管理器
- `src/simacode/mcp/protocol.py` - MCP 协议异步扩展

## 许可证

本项目遵循 SimaCode 项目的许可证条款。