# SimaCode 邮件发送工具 (email_send)

## 概述

`email_send` 工具为 SimaCode AI 助手提供了安全、可配置的邮件发送功能。该工具完全集成到 SimaCode 的工具系统中，支持从配置文件读取 SMTP 设置，并提供全面的安全控制和权限管理。

## 功能特性

### 核心功能
- ✅ **多格式邮件**：支持纯文本和 HTML 邮件
- ✅ **多收件人**：支持 to、cc、bcc 多种收件人类型
- ✅ **附件支持**：安全的文件附件上传
- ✅ **配置驱动**：从 `.simacode/config.yaml` 读取 SMTP 配置
- ✅ **环境变量**：支持环境变量存储敏感信息
- ✅ **延迟发送**：支持定时延迟发送

### 安全特性
- 🔒 **邮箱验证**：严格的邮箱地址格式验证
- 🔒 **域名控制**：支持域名白名单和黑名单
- 🔒 **HTML 过滤**：自动清理 HTML 内容，防止 XSS 攻击
- 🔒 **附件检查**：文件类型、大小和路径安全验证
- 🔒 **权限控制**：基于 SimaCode 权限系统的访问控制
- 🔒 **频率限制**：防止邮件滥用的发送频率限制

## 配置设置

### 1. 默认配置 (config/default.yaml)

```yaml
email:
  smtp:
    server: null  # SMTP server address (e.g., smtp.gmail.com)
    port: 587  # SMTP port (587 for TLS, 465 for SSL, 25 for plain)
    use_tls: true  # Use TLS encryption
    use_ssl: false  # Use SSL encryption
    timeout: 30  # Connection timeout in seconds
    username: null  # SMTP username (will be loaded from SIMACODE_SMTP_USER env var)
    password: null  # SMTP password (will be loaded from SIMACODE_SMTP_PASS env var)
  security:
    max_recipients: 50  # Maximum number of recipients per email
    max_attachment_size: 26214400  # 25MB in bytes
    max_body_size: 1048576  # 1MB in bytes
    allowed_domains: []  # Allowed recipient domains (empty = allow all)
    blocked_domains: []  # Blocked recipient domains
    allowed_attachment_types: [".txt", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".jpeg", ".png", ".gif"]
  rate_limiting:
    max_emails_per_hour: 100  # Maximum emails per hour
    max_emails_per_day: 1000  # Maximum emails per day
  defaults:
    from_name: "SimaCode Assistant"  # Default sender name
    from_email: null  # Default sender email (will use username if not set)
```

### 2. 项目配置 (.simacode/config.yaml)

```yaml
email:
  smtp:
    server: "smtp.gmail.com"  # Gmail SMTP server
    port: 587
    use_tls: true
    use_ssl: false
    timeout: 30
    username: null  # Set your email or use SIMACODE_SMTP_USER env var
    password: null  # Set your password or use SIMACODE_SMTP_PASS env var
  security:
    max_recipients: 20  # Limit recipients for this project
    allowed_domains: ["gmail.com", "company.com"]  # Only allow these domains
    blocked_domains: ["spam.com"]
  defaults:
    from_name: "DevGenius Assistant"
    from_email: null  # Will use username if not set
```

### 3. 环境变量

推荐使用环境变量存储敏感信息：

```bash
export SIMACODE_SMTP_USER="your-email@gmail.com"
export SIMACODE_SMTP_PASS="your-app-password"
```

## 使用方法

### 1. 基础文本邮件

```python
email_data = {
    "to": "recipient@example.com",
    "subject": "测试邮件",
    "body": "这是一封测试邮件。",
    "content_type": "text"
}

async for result in execute_tool("email_send", email_data):
    print(f"[{result.type.value}] {result.content}")
```

### 2. HTML 邮件

```python
email_data = {
    "to": "recipient@example.com",
    "subject": "HTML 邮件",
    "body": "<h1>标题</h1><p>这是 <strong>HTML</strong> 邮件。</p>",
    "content_type": "html"
}
```

### 3. 多收件人邮件

```python
email_data = {
    "to": ["user1@example.com", "user2@example.com"],
    "cc": "manager@example.com",
    "bcc": "archive@example.com",
    "subject": "团队通知",
    "body": "这是发给团队的通知。"
}
```

### 4. 带附件邮件

```python
email_data = {
    "to": "recipient@example.com",
    "subject": "报告（含附件）",
    "body": "请查看附件中的报告。",
    "attachments": ["/path/to/report.pdf", "/path/to/data.xlsx"]
}
```

### 5. 延迟发送

```python
email_data = {
    "to": "recipient@example.com",
    "subject": "延迟邮件",
    "body": "这封邮件将延迟 30 秒发送。",
    "send_delay": 30  # 延迟 30 秒
}
```

### 6. 在 ReAct 任务中使用

直接通过自然语言描述：

```
发送邮件给 user@example.com，主题是"项目更新"，内容是"项目已完成第一阶段开发"
```

```
发送HTML邮件给团队成员 team@company.com，抄送给 manager@company.com，主题是"周报"，包含项目进度表格
```

```
发送邮件给客户 client@example.com，附上最新的 PDF 报告文件 /Users/data/report.pdf
```

## 输入参数

### 必需参数

| 参数 | 类型 | 描述 |
|------|------|------|
| `to` | `str` 或 `List[str]` | 收件人邮箱地址 |
| `subject` | `str` | 邮件主题（最大 500 字符） |
| `body` | `str` | 邮件正文内容 |

### 可选参数

| 参数 | 类型 | 默认值 | 描述 |
|------|------|-------|------|
| `cc` | `str` 或 `List[str]` | `None` | 抄送邮箱地址 |
| `bcc` | `str` 或 `List[str]` | `None` | 密送邮箱地址 |
| `reply_to` | `str` | `None` | 回复地址 |
| `content_type` | `str` | `"text"` | 邮件类型：`"text"` 或 `"html"` |
| `encoding` | `str` | `"utf-8"` | 字符编码 |
| `attachments` | `List[str]` | `None` | 附件文件路径列表 |
| `priority` | `str` | `"normal"` | 优先级：`"low"`, `"normal"`, `"high"` |
| `send_delay` | `int` | `None` | 延迟发送秒数（0-86400） |
| `from_name` | `str` | `None` | 覆盖默认发件人姓名 |
| `from_email` | `str` | `None` | 覆盖默认发件人邮箱 |

## 错误处理

工具会自动处理各种错误情况：

### 1. 配置错误
- SMTP 服务器未配置
- 认证信息缺失
- 连接超时

### 2. 输入验证错误
- 邮箱地址格式错误
- 主题或内容为空
- 超出收件人数量限制

### 3. 安全限制
- 域名不在允许列表中
- 附件类型不被允许
- 文件大小超出限制
- 超出发送频率限制

### 4. 附件错误
- 文件不存在
- 文件权限不足
- 文件过大

## 依赖要求

工具需要以下 Python 包：

```bash
pip install aiosmtplib email-validator bleach
```

- `aiosmtplib`: 异步 SMTP 客户端
- `email-validator`: 邮箱地址验证
- `bleach`: HTML 内容清理

## 常见配置示例

### Gmail 配置

```yaml
email:
  smtp:
    server: "smtp.gmail.com"
    port: 587
    use_tls: true
    username: "your-email@gmail.com"
    # 使用应用专用密码，不是账户密码
```

### Outlook 配置

```yaml
email:
  smtp:
    server: "smtp-mail.outlook.com"
    port: 587
    use_tls: true
    username: "your-email@outlook.com"
```

### 企业邮箱配置

```yaml
email:
  smtp:
    server: "mail.company.com"
    port: 465
    use_ssl: true
    username: "your-email@company.com"
```

## 安全最佳实践

1. **使用环境变量**：永远不要在配置文件中硬编码密码
2. **应用专用密码**：对于 Gmail，使用应用专用密码而不是主密码
3. **域名限制**：设置 `allowed_domains` 限制收件人域名
4. **附件检查**：限制附件类型和大小
5. **频率限制**：设置合理的发送频率限制
6. **权限控制**：利用 SimaCode 的权限系统

## 故障排除

### 1. 连接问题
- 检查 SMTP 服务器地址和端口
- 确认 TLS/SSL 设置正确
- 检查网络连接和防火墙

### 2. 认证问题
- 验证用户名和密码
- 对于 Gmail，确保使用应用专用密码
- 检查账户是否启用了 SMTP 访问

### 3. 发送失败
- 检查收件人邮箱地址格式
- 确认域名在允许列表中
- 检查是否超出发送频率限制

### 4. 附件问题
- 确认文件存在且可读
- 检查文件类型是否被允许
- 验证文件大小未超出限制

## 测试和验证

运行测试脚本验证配置：

```bash
python tests/test_email_tool.py
```

运行示例脚本查看使用方法：

```bash
python demo/email_tool_example.py
```

## 版本历史

- **v1.0.0**: 初始版本
  - 基础邮件发送功能
  - 配置文件集成
  - 安全控制和权限管理
  - 附件支持
  - HTML 内容过滤
  - 频率限制