# Universal OCR Tool - 使用示例

## 通过 SimaCode Chat 调用 OCR 工具

### 1. 基本使用方式

启动 SimaCode 聊天模式：
```bash
simacode chat --react
```

然后在聊天中请求 OCR 识别：

#### 示例 1：基本文档识别
```
用户: 请帮我识别这个文档中的文字内容：test_invoice.png

AI 会自动：
1. 检测到这是文档识别任务
2. 调用 universal_ocr 工具
3. 处理图片文件
4. 返回提取的文字内容
```

#### 示例 2：指定输出格式
```
用户: 请用结构化格式识别这个发票：test_invoice.png，我需要提取发票号、日期、金额等信息

AI 会使用：
- scene_hint: "invoice" 
- output_format: "structured"
- 智能提取发票关键信息
```

#### 示例 3：PDF 文档处理
```
用户: 这个 PDF 文档有多页，请帮我提取所有页面的文字内容：document.pdf

AI 会自动：
1. 检测 PDF 格式
2. 转换每一页为图片
3. 逐页进行 OCR 识别
4. 合并所有页面结果
```

### 2. 详细使用场景

#### 场景 A：发票处理
```bash
# 启动聊天
simacode chat --react

# 用户输入
"我有一张发票图片 invoice_001.jpg，请帮我提取以下信息：
- 发票号码
- 开票日期  
- 供应商信息
- 商品明细
- 总金额
请用 JSON 格式返回结果。"
```

**AI 会自动执行：**
```python
# AI 内部调用流程
UniversalOCRInput(
    file_path="invoice_001.jpg",
    output_format="json",
    scene_hint="invoice",
    confidence_threshold=0.8
)
```

#### 场景 B：学术文档处理
```bash
# 用户输入
"请识别这个成绩单 transcript.pdf 中的所有课程信息，包括课程名称、学分、成绩等。"
```

**AI 会自动使用：**
- `scene_hint: "transcript"`
- 自动处理 PDF 多页
- 提取结构化学术信息

#### 场景 C：银行对账单
```bash
# 用户输入  
"这是我的银行对账单 statement.pdf，请帮我提取所有交易记录，包括日期、描述、金额、余额。"
```

### 3. 高级使用技巧

#### 自定义提取内容
```
用户: 请从这个合同文档中只提取以下信息：
1. 合同编号
2. 甲乙双方名称
3. 合同金额
4. 签署日期
5. 有效期

文件：contract.pdf
```

#### 批量处理建议
```
用户: 我有 5 张收据图片（receipt_1.jpg 到 receipt_5.jpg），请帮我提取每张收据的商家名称、购买日期、商品列表和总金额。
```

#### 质量问题处理
```
用户: 这个图片有些模糊：blurry_document.jpg，请尝试识别其中的文字，如果识别困难请告知置信度。
```

### 4. 完整示例对话

```bash
$ simacode chat --react

👤 用户: 请帮我识别这个发票图片中的内容：test_invoice.png

🤖 AI: 我来帮您识别这个发票图片中的内容。让我使用 OCR 工具来处理这个文件。

[工具调用] universal_ocr
- 文件路径: test_invoice.png
- 输出格式: structured  
- 场景类型: invoice
- 质量增强: 开启

正在处理图片...
正在提取文字内容...

识别结果：

=== OCR 提取结果 ===

📋 处理信息:
  文件: test_invoice.png
  引擎: claude
  处理时间: 2.34s
  置信度: 95.2%
  场景: invoice

📊 提取的发票信息:
  发票号码: INV-2024-12345
  开票日期: August 5, 2024
  客户信息: ABC Company Ltd.
           123 Business Street
           City, State 12345
  
  商品明细:
    1. OCR Testing Service    数量:1    单价:$299.99    小计:$299.99
    2. Data Processing Fee    数量:1    单价:$50.00     小计:$50.00
  
  费用汇总:
    小计: $349.99
    税费: $35.00
    总计: $384.99
  
  付款条件: Net 30 days
  到期日期: September 4, 2024

📝 原始提取文本:
INVOICE
Invoice Number: INV-2024-12345
Date: August 5, 2024
...

识别完成！发票信息已成功提取，置信度为 95.2%。您需要我进一步处理这些信息吗？

👤 用户: 请把这些信息整理成 JSON 格式

🤖 AI: 好的，我来将发票信息整理成 JSON 格式：

```json
{
  "invoice": {
    "number": "INV-2024-12345",
    "date": "August 5, 2024",
    "due_date": "September 4, 2024",
    "payment_terms": "Net 30 days"
  },
  "bill_to": {
    "company": "ABC Company Ltd.",
    "address": [
      "123 Business Street",
      "City, State 12345"
    ]
  },
  "items": [
    {
      "description": "OCR Testing Service",
      "quantity": 1,
      "unit_price": 299.99,
      "total": 299.99
    },
    {
      "description": "Data Processing Fee", 
      "quantity": 1,
      "unit_price": 50.00,
      "total": 50.00
    }
  ],
  "totals": {
    "subtotal": 349.99,
    "tax": 35.00,
    "total": 384.99
  },
  "processing_info": {
    "confidence": 0.952,
    "processing_time": 2.34,
    "engine": "claude"
  }
}
```

JSON 格式的发票数据已准备就绪！
```

### 5. 错误处理示例

```bash
👤 用户: 请识别这个文件：non_existent.jpg

🤖 AI: 我尝试识别文件时遇到了问题：

❌ 错误: 文件不存在: non_existent.jpg

请检查：
1. 文件路径是否正确
2. 文件是否存在于指定位置
3. 文件权限是否允许读取

请提供正确的文件路径，我将重新为您处理。
```

### 6. 支持的命令类型

在 `simacode chat --react` 中，以下类型的请求会自动触发 OCR 工具：

- "识别这个图片/文档中的文字"
- "提取这个发票的信息"
- "OCR 识别这个 PDF"
- "读取这个图片上的内容"
- "从这个文档中提取数据"
- "分析这个收据/合同/成绩单"

### 7. 最佳实践建议

1. **明确指定需求**：告诉 AI 您需要什么类型的信息
2. **提供文件上下文**：说明文档类型（发票、合同、收据等）
3. **指定输出格式**：如果需要特定格式（JSON、表格等）请明确说明
4. **处理模糊图片**：对于质量较差的图片，可以要求提供置信度信息

通过这种方式，您可以轻松地在 SimaCode 聊天界面中使用强大的 OCR 功能！