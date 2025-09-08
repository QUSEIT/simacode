# browser_use_proxy 工具未找到问题解决方案

## 问题诊断

根据错误信息和检查结果，问题是：

```
Tool 'browser_use_proxy' not found in registry
```

**根本原因**：
1. MCP 系统中只有 `ui_tars:open_website_with_verification` 工具可用
2. 没有 `browser_use_proxy` 工具注册在系统中
3. AI 规划器尝试使用不存在的工具

## 解决方案

### 方案1: 启用 browser_use_proxy MCP 服务器（推荐）

如果您有 browser_use_proxy MCP 服务器，需要先启用它：

```bash
# 1. 初始化 browser_use_proxy MCP 服务器
simacode mcp init

# 2. 检查服务器配置
simacode mcp status

# 3. 确认工具已注册
simacode mcp list | grep browser_use_proxy
```

### 方案2: 使用现有的 ui_tars 工具

目前系统中有 `ui_tars:open_website_with_verification` 工具可用，您可以：

```bash
# 直接使用ui_tars工具打开百度
simacode mcp run ui_tars:open_website_with_verification --param url="https://www.baidu.com"
```

### 方案3: 强制使用特定工具

在命令中明确指定使用 ui_tars 工具：

```bash
# 使用 simacode chat 并指定工具
simacode chat --react "使用ui_tars:open_website_with_verification工具打开百度网站"
```

### 方案4: 临时禁用工具验证（不推荐）

如果需要临时绕过工具验证，可以修改规划器的工具检查逻辑。

## 立即解决步骤

### 步骤1: 检查可用工具
```bash
simacode mcp list
```

### 步骤2: 使用正确的工具名称
当前可用的浏览器相关工具：
- `ui_tars:open_website_with_verification`

### 步骤3: 重新执行任务
使用正确的工具名称重新执行：

```bash
# 方式1: 直接使用MCP工具
simacode mcp run ui_tars:open_website_with_verification --param url="https://www.baidu.com"

# 方式2: 使用ReAct引擎，明确指定工具
simacode chat --react "请使用ui_tars:open_website_with_verification工具打开百度网站"
```

## 预防措施

### 1. 工具名称映射

可以在规划器中添加工具名称映射，将 `browser_use_proxy` 映射到 `ui_tars:open_website_with_verification`。

### 2. 工具发现增强

改进工具发现机制，当找不到特定工具时，建议相似的替代工具。

### 3. 错误处理改进

在规划阶段提供更好的错误提示，建议用户使用可用的替代工具。

## 代码修复建议

如果需要在代码层面修复这个问题，可以考虑：

### 修改规划器工具验证逻辑

在 `src/simacode/react/planner.py` 中添加工具名称映射：

```python
# 工具名称映射
TOOL_NAME_MAPPING = {
    'browser_use_proxy': 'ui_tars:open_website_with_verification',
    # 添加其他映射...
}

def validate_tool_exists(self, tool_name: str) -> str:
    """验证工具是否存在，并提供映射"""
    # 先检查直接映射
    if tool_name in TOOL_NAME_MAPPING:
        mapped_tool = TOOL_NAME_MAPPING[tool_name]
        if self.tool_registry.has_tool(mapped_tool):
            return mapped_tool
    
    # 检查原始工具名
    if self.tool_registry.has_tool(tool_name):
        return tool_name
        
    # 查找相似工具
    similar_tools = self.find_similar_tools(tool_name)
    if similar_tools:
        raise PlanningError(f"Tool '{tool_name}' not found. Did you mean: {similar_tools}?")
    
    raise PlanningError(f"Tool '{tool_name}' not found in registry")
```

## 测试验证

完成修复后，测试验证：

```bash
# 1. 检查工具状态
simacode mcp status

# 2. 列出所有工具
simacode mcp list

# 3. 测试浏览器功能
simacode chat --react "打开百度"

# 4. 直接测试工具
simacode mcp run ui_tars:open_website_with_verification --param url="https://www.baidu.com"
```

## 总结

当前问题的最快解决方案是使用现有的 `ui_tars:open_website_with_verification` 工具来替代 `browser_use_proxy`。长期解决方案是完善工具映射和错误处理机制。