# simacode mcp ui_tars:open_website_with_verification 使用示范

## 工具介绍

`ui_tars:open_website_with_verification` 是一个通过 MCP (Model Context Protocol) 提供的 UI 自动化工具，用于打开网站并处理验证挑战（如验证码、登录验证等）。

## 工具参数

根据 `simacode mcp info ui_tars:open_website_with_verification` 的输出，该工具支持以下参数：

- **url** (必需): 要打开的网站URL
- **verification_instructions** (可选): 处理验证挑战的自然语言指令，默认为 "automatically handle any verification challenges"
- **timeout** (可选): 操作超时时间（秒），默认为 300 秒

## 使用方式

### 1. 基础使用 - 仅指定URL

```bash
# 打开网站（使用默认验证处理）
simacode mcp run ui_tars:open_website_with_verification --param url="https://example.com"
```

### 2. 使用JSON参数格式

```bash
# 使用JSON格式传递参数
simacode mcp run ui_tars:open_website_with_verification -p '{"url": "https://example.com"}'
```

### 3. 指定自定义验证指令

```bash
# 指定自定义的验证处理指令
simacode mcp run ui_tars:open_website_with_verification \
  --param url="https://login.example.com" \
  --param verification_instructions="fill in username and password if prompted, solve any captcha"
```

### 4. 设置自定义超时时间

```bash
# 设置60秒超时
simacode mcp run ui_tars:open_website_with_verification \
  --param url="https://slow-loading-site.com" \
  --param timeout="60"
```

### 5. 完整参数示例

```bash
# 完整参数示例
simacode mcp run ui_tars:open_website_with_verification \
  --param url="https://secure.example.com/login" \
  --param verification_instructions="handle login form, solve captcha if present, click continue button" \
  --param timeout="120"
```

### 6. 使用JSON格式的完整示例

```bash
# JSON格式的完整参数
simacode mcp run ui_tars:open_website_with_verification -p '{
  "url": "https://secure.example.com/login",
  "verification_instructions": "handle login form, solve captcha if present, click continue button",
  "timeout": 120
}'
```

## 实际使用场景示例

### 场景1: 打开普通网站
```bash
simacode mcp run ui_tars:open_website_with_verification --param url="https://www.google.com"
```

### 场景2: 访问需要登录的网站
```bash
simacode mcp run ui_tars:open_website_with_verification \
  --param url="https://github.com/login" \
  --param verification_instructions="fill in login credentials if available, handle any 2FA prompts"
```

### 场景3: 处理复杂验证的网站
```bash
simacode mcp run ui_tars:open_website_with_verification -p '{
  "url": "https://complex-site.com",
  "verification_instructions": "wait for page to load completely, handle any cookie banners, solve captcha if present, click accept terms",
  "timeout": 180
}'
```

### 场景4: 访问电商网站
```bash
simacode mcp run ui_tars:open_website_with_verification \
  --param url="https://www.amazon.com" \
  --param verification_instructions="handle location prompts, dismiss any promotional popups"
```

## 交互式使用

如果您希望交互式地输入参数：

```bash
# 交互式输入参数
simacode mcp run ui_tars:open_website_with_verification --interactive
```

## 干运行（测试）

在实际执行之前，您可以使用 `--dry-run` 选项来查看将要执行的操作：

```bash
# 查看将要执行的操作，但不实际执行
simacode mcp run ui_tars:open_website_with_verification \
  --param url="https://example.com" \
  --dry-run
```

## 注意事项

1. **URL格式**: 确保URL包含协议前缀（http:// 或 https://）
2. **验证指令**: 使用自然语言描述您希望工具如何处理验证挑战
3. **超时设置**: 根据网站的加载速度调整超时时间
4. **权限**: 确保运行环境有足够的权限进行UI自动化操作
5. **依赖**: 确保 ui_tars MCP 服务器正在运行并且可访问

## 故障排除

如果工具无法正常工作，请检查：

1. MCP 服务器状态：
   ```bash
   simacode mcp status
   ```

2. 工具列表：
   ```bash
   simacode mcp list | grep ui_tars
   ```

3. 详细信息：
   ```bash
   simacode mcp info ui_tars:open_website_with_verification
   ```

这个示范展示了 `ui_tars:open_website_with_verification` 工具的各种使用方法，您可以根据具体需求选择合适的参数组合。