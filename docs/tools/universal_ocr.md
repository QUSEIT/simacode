# Universal OCR 工具

## 概述

Universal OCR是SimaCode中的一个智能化**通用OCR识别工具**，采用模板驱动的可扩展架构设计。工具的核心理念是**通用性**和**可扩展性**，通过灵活的模板系统和智能场景识别，可以快速适配任何类型的文档识别需求。

### 核心优势
- **🎯 通用架构**: 不绑定特定业务场景，可适配任何文档类型
- **🔧 模板驱动**: 通过配置模板即可支持新文档类型，无需修改代码
- **🤖 智能引擎**: LLM视觉模型与传统OCR技术相结合的混合架构
- **📈 快速扩展**: 从样本文档快速生成模板，支持继承和自定义
- **⚡ 高性能**: 多级缓存、智能调度、并发处理

> **设计哲学**: 与传统专门针对特定场景的OCR工具不同，Universal OCR专注于提供一个通用的、可配置的OCR框架，让用户能够通过简单的模板配置就能处理各种复杂的文档识别需求。

## 主要特性

- 🌐 **通用性强**: 不局限于特定场景，可适配任何类型的结构化文档
- 🔧 **模板驱动**: 通过YAML配置即可支持新文档类型，支持模板继承和扩展
- 🤖 **智能识别**: 主要使用Claude-3.5 Sonnet等先进LLM视觉模型
- ⚖️ **混合引擎**: LLM + 传统OCR (PaddleOCR/Tesseract) 智能协作
- 🏗️ **五层架构**: 预处理→场景识别→模板匹配→OCR引擎→后处理
- 🚀 **高性能**: 多级缓存、并发处理、智能调度优化
- 📈 **易扩展**: AI辅助模板创建，从样本文档快速生成模板
- 🌐 **多格式**: JPG、PNG、PDF、GIF、WebP等格式支持

## 核心架构

### 五层智能架构
```
UniversalOCRTool
├── 预处理层 (Preprocessing)
│   ├── 图像格式检测与转换 (PDF→Image)
│   ├── 图像质量增强 (去噪、旋转矫正、对比度调整)
│   └── 文档类型初步识别
│
├── 场景识别层 (Scene Detection)  
│   ├── AI驱动的文档分类器 (基于Claude Vision)
│   ├── 规则引擎补充识别
│   └── 置信度评估机制
│
├── 模板匹配层 (Template Processing)
│   ├── 动态模板生成 (JSON Schema驱动)
│   ├── 字段提取规则引擎
│   └── 多版本模板兼容
│
├── OCR引擎层 (Multi-Engine OCR)
│   ├── 主引擎：Claude-3.5 Sonnet Vision
│   ├── 辅助引擎：GPT-4V、Qwen-VL
│   ├── 传统引擎：PaddleOCR、Tesseract
│   └── 智能调度器 (成本、精度、速度权衡)
│
└── 后处理层 (Post Processing)
    ├── 数据清洗与标准化
    ├── 置信度评估与质量检查
    ├── 结构化输出格式化
    └── 错误修正机制
```

## 应用场景

Universal OCR工具具有强大的通用性和可扩展能力，可适用于各种文档识别场景：

### 典型应用示例
- **电商发票**: 发票号、开票方、商品列表、税额、总额等结构化信息提取
- **学生成绩单**: 学生信息、课程成绩、GPA、学期等教育文档处理
- **金融票据**: 银行对账单、支付凭证等金融文档识别

### 扩展应用场景
- **政务文档**: 身份证、驾驶证、营业执照等证件识别
- **医疗单据**: 病历、检查报告、处方单等医疗文档
- **物流单据**: 快递单、提货单、装箱单等物流文档
- **合同文件**: 租赁合同、劳动合同等法律文档
- **表格数据**: 各类结构化表格数据提取
- **手写文档**: 手写表单、笔记等非标准格式文档

> **设计理念**: 本工具采用模板驱动架构，通过灵活的模板系统和智能场景识别，可以快速适配新的文档类型，无需修改核心代码。

## 安装依赖

```bash
# 核心依赖
pip install anthropic openai pillow opencv-python

# OCR引擎依赖
pip install paddlepaddle paddleocr tesseract

# 图像处理依赖  
pip install pdf2image PyMuPDF

# 可选依赖
pip install redis chardet  # 缓存和编码检测
```

## 环境配置

在项目根目录或用户主目录创建 `.simacode/config.yaml` 文件：

```yaml
# Claude AI OCR配置 (推荐)
ocr_claudeai:
  provider: "anthropic"
  api_key: "your-anthropic-api-key-here"
  base_url: "https://api.anthropic.com"
  model: "claude-3-5-sonnet-20241022"
  temperature: 0.1
  max_tokens: 4000
  timeout: 60

# OpenAI OCR配置 (备选)
ocr_openai:
  provider: "openai" 
  api_key: "your-openai-api-key-here"
  model: "gpt-4-vision-preview"
  temperature: 0.1
  max_tokens: 4000

# OCR 引擎配置
ocr_engines:
  claude:
    enabled: true
    priority: 1
  paddleocr:
    enabled: true
    priority: 2
    use_angle_cls: true
    lang: "ch"
  tesseract:
    enabled: true
    priority: 3
    lang: "chi_sim+eng"

# 缓存配置
cache:
  enabled: true
  backend: "memory"  # memory, redis
  ttl: 3600
  max_size: 1000

# 模板配置
templates:
  builtin_dir: "templates/builtin"
  user_dir: "templates/user"
  cache_dir: "templates/cache"
  auto_learning: true
```

## 使用方法

### 1. 通过工具注册系统使用

```python
from simacode.tools import execute_tool

# 基本使用
input_data = {
    "file_path": "/path/to/document.jpg",
    "output_format": "json",
    "confidence_threshold": 0.8
}

async for result in execute_tool("universal_ocr", input_data):
    if result.type.value == "success":
        print(result.content)
```

### 2. 场景提示使用

```python
# 指定场景提示以提高识别准确度
input_data = {
    "file_path": "/path/to/document.pdf", 
    "scene_hint": "invoice",  # 场景提示
    "output_format": "structured",
    "template_override": "custom_template"
}

async for result in execute_tool("universal_ocr", input_data):
    print(f"{result.type.value}: {result.content}")
```

### 3. 直接使用工具类

```python
from simacode.tools.universal_ocr import UniversalOCRTool

# 创建工具实例
tool = UniversalOCRTool()

# 准备输入
input_data = {
    "file_path": "/path/to/document.jpg",
    "scene_hint": "custom_scene",
    "engines": ["claude", "paddleocr"],  # 引擎优先级
    "use_cache": True
}

# 执行识别
validated_input = await tool.validate_input(input_data)
async for result in tool.execute(validated_input):
    print(f"{result.type.value}: {result.content}")
```

### 4. 批量处理

```python
# 批量处理多个文档
documents = [
    {"file_path": "invoice1.pdf", "scene_hint": "invoice"},
    {"file_path": "transcript1.jpg", "scene_hint": "transcript"},
    {"file_path": "statement1.png", "scene_hint": "bank_statement"}
]

results = []
for doc in documents:
    async for result in execute_tool("universal_ocr", doc):
        if result.type.value == "success":
            results.append(json.loads(result.content))
```

## 输入参数

### 必需参数

- **file_path** (str): 文档文件的路径

### 可选参数

- **scene_hint** (str, 默认: None): 场景提示
  - 支持值: `"invoice"`, `"transcript"`, `"bank_statement"` 等，或用户自定义场景标识
  
- **output_format** (str, 默认: "json"): 输出格式
  - `"json"`: JSON格式
  - `"structured"`: 结构化文本格式
  - `"raw"`: 原始提取文本

- **confidence_threshold** (float, 默认: 0.8): 置信度阈值 (0.0-1.0)

- **engines** (List[str], 默认: ["claude", "paddleocr"]): OCR引擎优先级列表

- **use_cache** (bool, 默认: true): 是否使用缓存

- **template_override** (str, 默认: None): 强制使用指定模板

- **quality_enhancement** (bool, 默认: true): 是否进行图像质量增强

- **extract_confidence** (bool, 默认: false): 是否返回字段级置信度

## 模板系统

### 内置模板

系统提供基础的内置模板作为参考和起点，用户可基于这些模板扩展创建自己的模板：

```
templates/builtin/
├── ecommerce/
│   └── invoice.yaml        # 通用发票模板
├── education/
│   └── transcript.yaml     # 成绩单模板
└── finance/
    └── bank_statement.yaml # 银行对账单模板
```

> **扩展性说明**: 内置模板仅提供最基础的示例，主要目的是展示模板结构和配置方法。用户应根据实际需求创建自定义模板，以获得最佳识别效果。

### 用户自定义模板

#### 创建自定义模板

```python
# 通过API创建自定义模板
from simacode.tools.universal_ocr import TemplateManager

template_config = {
    "template": {
        "meta": {
            "name": "自定义文档模板",
            "version": "1.0.0", 
            "author": "user@company.com",
            "description": "适用于特定业务文档格式",
            "extends": "builtin/ecommerce/invoice"  # 继承基础模板
        },
        "detection": {
            "keywords": ["关键词1", "关键词2", "特殊标识"],
            "confidence_threshold": 0.85
        },
        "fields": {
            "document_number": {
                "name": "文档编号",
                "type": "string", 
                "required": true,
                "patterns": ["DOC-\\d{4}-\\d{3}"]
            },
            "custom_field": {
                "name": "自定义字段",
                "type": "string",
                "required": true,
                "patterns": ["\\d{10,20}"],
                "validation": [
                    {"type": "length", "min": 10, "max": 20}
                ]
            }
        }
    }
}

template_manager = TemplateManager()
template_id = await template_manager.register_user_template(template_config, user_id="user123")
```

#### 模板继承和扩展

```yaml
# custom_document.yaml - 继承并扩展内置模板
template:
  meta:
    name: "定制文档模板"
    extends: "builtin/ecommerce/invoice"  # 继承基础模板
    
  fields:
    # 继承基础字段并扩展
    document_number:
      extends: "base.document_number"  # 继承基础配置
      patterns: ["COMP-\\d{8}"]       # 覆盖模式规则
      
    # 新增自定义字段
    reference_code:
      name: "参考编码"
      type: "string"
      required: false
      patterns: ["REF-\\d{4}"]
      
    custom_field:
      name: "业务特定字段"
      type: "string"
      extraction_hints:
        - "通常在文档底部"
        - "以特定前缀开头"
```

#### 交互式模板创建

```bash
# 命令行交互式创建
simacode ocr template create --interactive

# 从样本图像创建模板  
simacode ocr template create --from-sample "sample_document.jpg" --name "my_template"

# 克隆并修改现有模板
simacode ocr template clone "builtin/invoice" --name "custom_template" --modify-field "field_name=new_value"
```

### 模板管理命令

```bash
# 列出所有可用模板
simacode ocr template list

# 查看模板详情
simacode ocr template show "builtin/invoice"

# 测试模板效果
simacode ocr template test "user_template_v1" --images "test1.jpg,test2.jpg"

# 优化模板
simacode ocr template optimize "user_template_v1" --analyze-usage

# 删除用户模板
simacode ocr template delete "user_template_v1"
```

## 输出数据结构

### JSON格式输出

```json
{
  "meta": {
    "file_path": "/path/to/invoice.jpg",
    "scene_detected": "invoice",
    "template_used": "builtin/ecommerce/invoice",
    "processing_time": 2.34,
    "engines_used": ["claude", "paddleocr"],
    "confidence_score": 0.95
  },
  "document_info": {
    "type": "发票",
    "format": "标准增值税发票",
    "language": "zh-CN"
  },
  "extracted_data": {
    "invoice_number": "INV-2024-001",
    "issue_date": "2024-08-05",
    "vendor": {
      "name": "ABC科技有限公司",
      "address": "北京市朝阳区科技园1号",
      "tax_id": "91110000123456789X",
      "phone": "010-12345678"
    },
    "customer": {
      "name": "XYZ企业集团",
      "address": "上海市浦东新区商务区100号",
      "tax_id": "91310000987654321Y"
    },
    "items": [
      {
        "index": 1,
        "description": "软件开发服务",
        "specification": "项",
        "quantity": 1,
        "unit_price": 10000.00,
        "amount": 10000.00,
        "tax_rate": 0.06,
        "tax_amount": 600.00
      }
    ],
    "financial_summary": {
      "subtotal": 10000.00,
      "total_tax": 600.00,
      "total_amount": 10600.00,
      "currency": "CNY",
      "amount_in_words": "壹万零陆佰元整"
    },
    "payment_info": {
      "payment_terms": "30天内付款",
      "bank_account": "1234567890123456789",
      "bank_name": "中国银行北京分行"
    }
  },
  "quality_metrics": {
    "overall_confidence": 0.95,
    "field_confidence": {
      "invoice_number": 0.99,
      "vendor.name": 0.97,
      "total_amount": 0.93
    },
    "validation_results": {
      "amount_calculation": "passed",
      "tax_calculation": "passed",
      "format_validation": "passed"
    }
  }
}
```

### 结构化文本输出

```
=== 发票识别结果 ===

📋 基本信息:
  发票号码: INV-2024-001
  开票日期: 2024-08-05
  发票类型: 增值税专用发票

🏢 开票方信息:
  名称: ABC科技有限公司
  地址: 北京市朝阳区科技园1号
  税号: 91110000123456789X
  电话: 010-12345678

🏪 购买方信息:
  名称: XYZ企业集团
  地址: 上海市浦东新区商务区100号
  税号: 91310000987654321Y

📦 商品明细:
  1. 软件开发服务
     规格: 项 | 数量: 1 | 单价: ¥10,000.00
     金额: ¥10,000.00 | 税率: 6% | 税额: ¥600.00

💰 金额汇总:
  不含税金额: ¥10,000.00
  税额合计: ¥600.00
  价税合计: ¥10,600.00
  大写金额: 壹万零陆佰元整

💳 付款信息:
  付款条件: 30天内付款
  收款账户: 1234567890123456789
  开户银行: 中国银行北京分行

ℹ️ 处理信息:
  场景识别: 发票 (置信度: 95%)
  使用模板: builtin/ecommerce/invoice
  处理时间: 2.34秒
  使用引擎: Claude + PaddleOCR
```

## 高级功能

### 智能场景识别

```python
# 工具会自动分析文档特征
detection_result = {
    "detected_scene": "invoice",
    "confidence": 0.92,
    "alternative_scenes": [
        {"scene": "receipt", "confidence": 0.15},
        {"scene": "order", "confidence": 0.08}
    ],
    "detection_factors": {
        "keywords_matched": ["发票", "税号", "增值税"],
        "layout_features": ["table_structure", "header_logo"],
        "format_indicators": ["tax_calculation", "official_seal"]
    }
}
```

### 多引擎协作

```python
# 配置引擎协作策略
engine_config = {
    "primary_strategy": "quality_first",  # quality_first, speed_first, cost_first
    "engines": {
        "claude": {
            "use_for": ["complex_layout", "handwritten_text", "multi_language"],
            "confidence_threshold": 0.8
        },
        "paddleocr": {
            "use_for": ["table_extraction", "printed_text", "chinese_text"],
            "confidence_threshold": 0.9
        },
        "tesseract": {
            "use_for": ["fallback", "simple_text"],
            "confidence_threshold": 0.7
        }
    },
    "fusion_strategy": "weighted_average"  # majority_vote, highest_confidence, weighted_average
}
```

### 批量处理和监控

```python
from simacode.tools.universal_ocr import BatchProcessor

# 批量处理配置
batch_config = {
    "max_concurrent": 5,
    "retry_failed": True,
    "save_results": True,
    "progress_callback": lambda progress: print(f"进度: {progress}%")
}

processor = BatchProcessor(batch_config)

# 批量处理文档
documents = [
    "document1.pdf", "document2.jpg", "document3.png"
]

results = await processor.process_batch(documents, scene_hint="custom_scene")

# 获取处理统计
stats = processor.get_batch_stats()
print(f"成功: {stats.success_count}, 失败: {stats.failed_count}")
```

## 性能优化

### 缓存策略

```python
# 配置多级缓存
cache_config = {
    "file_hash_cache": {
        "enabled": True,
        "ttl": 7200,  # 2小时
        "max_size": 1000
    },
    "template_cache": {
        "enabled": True,
        "ttl": 3600,  # 1小时
        "preload_builtin": True
    },
    "result_cache": {
        "enabled": True,
        "ttl": 1800,  # 30分钟
        "compress": True
    }
}
```

### 并发处理

```python
# 并发处理配置
concurrency_config = {
    "max_workers": 3,
    "semaphore_limit": 5,
    "timeout_per_task": 120,
    "retry_attempts": 2
}
```

## 错误处理

### 常见错误类型

```python
# 处理各种异常情况
async for result in execute_tool("universal_ocr", input_data):
    if result.type.value == "error":
        error_type = result.metadata.get("error_type")
        
        if error_type == "FileNotFound":
            print(f"文件不存在: {result.content}")
        elif error_type == "UnsupportedFormat":
            print(f"不支持的文件格式: {result.content}")
        elif error_type == "LowQualityImage":
            print(f"图像质量过低: {result.content}")
        elif error_type == "APILimitExceeded":
            print(f"API调用超限: {result.content}")
        elif error_type == "TemplateNotFound":
            print(f"模板未找到: {result.content}")
        else:
            print(f"未知错误: {result.content}")
```

### 质量检查和降级策略

```python
# 质量检查配置
quality_config = {
    "minimum_confidence": 0.7,
    "required_fields": ["document_number", "key_field"],
    "validation_rules": ["data_format", "field_validation"],
    "fallback_strategy": "alternative_engine"  # retry, alternative_engine, manual_review
}
```

## 最佳实践

### 1. 图像质量优化

```python
# 图像预处理建议
preprocessing_tips = {
    "resolution": "建议至少300DPI",
    "format": "PDF优于图片格式",
    "lighting": "避免阴影和反光",
    "angle": "确保文档水平放置",
    "cropping": "裁剪去除无关边缘"
}
```

### 2. 模板选择策略

```python
# 最佳模板匹配
template_selection = {
    "use_scene_hint": "提供准确的场景提示",
    "custom_templates": "为特殊格式创建自定义模板", 
    "template_priority": "用户模板 > 学习模板 > 内置模板",
    "fallback_strategy": "多模板尝试机制"
}
```

### 3. 成本控制

```python
# 成本优化建议
cost_optimization = {
    "cache_usage": "充分利用缓存减少API调用",
    "engine_selection": "根据需求选择合适引擎",
    "batch_processing": "批量处理降低平均成本",
    "quality_threshold": "设置合理的质量阈值"
}
```

## API参考

### 工具类接口

```python
class UniversalOCRTool(Tool):
    """通用OCR工具主类"""
    
    async def extract_document(
        self, 
        file_path: str,
        scene_hint: Optional[str] = None,
        template_id: Optional[str] = None,
        engines: List[str] = None
    ) -> ExtractionResult:
        """提取文档内容"""
        
    async def detect_scene(self, file_path: str) -> SceneDetectionResult:
        """检测文档场景"""
        
    async def validate_extraction(
        self, 
        extraction_result: ExtractionResult,
        validation_rules: List[str] = None
    ) -> ValidationResult:
        """验证提取结果"""
```

### 模板管理接口

```python
class TemplateManager:
    """模板管理器"""
    
    async def create_template(
        self, 
        config: Dict,
        user_id: str
    ) -> str:
        """创建用户模板"""
        
    async def update_template(
        self,
        template_id: str,
        updates: Dict,
        user_id: str
    ) -> bool:
        """更新模板"""
        
    async def test_template(
        self,
        template_id: str,
        test_images: List[str]
    ) -> TemplateTestResult:
        """测试模板效果"""
```

## 监控和分析

### 使用统计

```python
# 获取使用统计
stats = await ocr_tool.get_usage_stats()
print(f"""
使用统计:
- 总处理数: {stats.total_processed}
- 成功率: {stats.success_rate:.1%}
- 平均处理时间: {stats.avg_processing_time:.2f}s
- 最常用场景: {stats.top_scenes}
- 引擎使用分布: {stats.engine_usage}
""")
```

### 质量监控

```python
# 质量监控仪表板
quality_metrics = await ocr_tool.get_quality_metrics()
print(f"""
质量指标:
- 平均置信度: {quality_metrics.avg_confidence:.2f}
- 验证通过率: {quality_metrics.validation_pass_rate:.1%}
- 字段提取完整度: {quality_metrics.field_completeness:.1%}
- 用户满意度: {quality_metrics.user_satisfaction:.1f}/5.0
""")
```

## 故障排除

### 常见问题

**Q: 识别准确率低怎么办？**
A: 
1. 检查图像质量和分辨率
2. 提供准确的scene_hint
3. 尝试不同的OCR引擎组合
4. 创建针对性的自定义模板
5. 调整confidence_threshold阈值

**Q: 处理速度慢怎么办？**
A:
1. 启用缓存功能
2. 使用更快的引擎组合
3. 减小图像文件大小
4. 启用并发处理
5. 检查网络连接状况

**Q: 模板匹配不准确？**
A:
1. 完善模板的detection规则
2. 增加更多关键词和模式
3. 调整模板优先级
4. 使用模板继承优化
5. 分析失败案例优化模板

**Q: API调用超限？**
A:
1. 启用缓存减少重复调用
2. 使用成本更低的引擎
3. 批量处理优化调用频率
4. 监控和控制调用量
5. 考虑升级API套餐

## 版本历史

- **v2.0.0**: 全新架构，支持多场景和用户自定义模板
- **v2.1.0**: 增加模板继承和AI学习功能  
- **v2.2.0**: 优化性能和缓存机制
- **v2.3.0**: 增加批量处理和监控功能

## 许可证

本工具遵循SimaCode项目的开源许可证。

## 支持

如需帮助或报告问题，请访问：
- 文档: https://docs.simacode.com/tools/universal-ocr
- 问题反馈: https://github.com/simacode/issues
- 社区讨论: https://community.simacode.com