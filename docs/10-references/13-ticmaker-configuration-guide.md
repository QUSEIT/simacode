# TICMaker 配置指南

## API 配置方式

TICMaker 支持灵活的 API 配置方式，按以下优先级读取配置：

### 1. 配置文件方式（推荐）

在 `.simacode/config.yaml` 中配置：

```yaml
# AI配置
ai:
  provider: "openai"
  api_key: "your-openai-api-key-here"           # 直接设置API密钥
  base_url: "https://openai.pgpt.cloud/v1"      # 自定义端点（可选）
  model: "gpt-4o-mini"                          # 使用的模型
  temperature: 0.1
  max_tokens: 2000
  timeout: 60
```

### 2. 环境变量方式

如果配置文件中没有设置 `api_key`，系统会自动读取环境变量：

```bash
# 方式1：使用SIMACODE_API_KEY
export SIMACODE_API_KEY="your-openai-api-key-here"

# 方式2：使用OPENAI_API_KEY  
export OPENAI_API_KEY="your-openai-api-key-here"
```

### 3. 自定义端点支持

TICMaker 完全支持自定义 API 端点，适用于：

- **代理服务器**：`https://your-proxy.com/v1`
- **私有部署**：`https://your-custom-endpoint.com/v1`
- **第三方兼容服务**：任何 OpenAI API 兼容的服务

```yaml
ai:
  base_url: "https://your-custom-endpoint.com/v1"  # 自定义端点
  api_key: "your-custom-api-key"                   # 对应的API密钥
```

## 使用方法

### CLI 模式

```bash
# 使用配置文件中的API设置
simacode chat --ticmaker "创建数学游戏页面"

# 显式指定scope
simacode chat --scope ticmaker "设计教学内容"

# 自动检测TICMaker关键词
simacode chat "制作TICMaker互动页面"
```

### API 模式

```bash
# 启动API服务器
simacode serve --port 8100

# 发送请求
curl -X POST http://localhost:8100/api/v1/chat/ \
  -H "Content-Type: application/json" \
  -d '{
    "message": "创建HTML页面",
    "context": {"scope": "ticmaker"}
  }'
```

## 配置验证

检查配置是否正确：

```bash
# 查看当前配置
simacode config --check

# 测试API连接
simacode chat --ticmaker "测试连接"
```

## 输出目录

生成的HTML文件保存在：
- **默认路径**：`./ticmaker_output/`
- **文件命名**：`ticmaker_page_YYYYMMDD_HHMMSS_<session>.html`

## 故障排除

### 常见问题

1. **"OpenAI API key is required"**
   - 检查 `.simacode/config.yaml` 中是否设置了 `ai.api_key`
   - 或确保设置了环境变量 `SIMACODE_API_KEY` 或 `OPENAI_API_KEY`

2. **"Connection error"**  
   - 检查 `base_url` 是否正确
   - 确认网络连接和代理设置

3. **"Invalid API key"**
   - 验证API密钥是否有效
   - 检查API密钥权限和额度

### 调试模式

启用详细日志：

```yaml
logging:
  level: "DEBUG"
  console_enabled: true
  file_enabled: true
  file_path: ".simacode/logs/debug.log"
```

## 安全建议

1. **保护API密钥**：不要将API密钥提交到版本控制系统
2. **使用环境变量**：在生产环境中优先使用环境变量
3. **定期轮换**：定期更换API密钥以提高安全性

## 示例配置

### 基本配置
```yaml
ai:
  provider: "openai"  
  api_key: "sk-your-key-here"
  model: "gpt-4o-mini"
```

### 高级配置
```yaml
ai:
  provider: "openai"
  api_key: "your-key-here"
  base_url: "https://openai.pgpt.cloud/v1"
  model: "gpt-4o-mini" 
  temperature: 0.1
  max_tokens: 2000
  timeout: 60

logging:
  level: "INFO"
  file_path: ".simacode/logs/ticmaker.log"

security:
  allowed_paths: ["."]
  require_permission_for_write: false
```

---

**TICMaker现已完全配置并可正常使用！** 🎉