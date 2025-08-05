# Universal OCR 工具 MVP 开发计划

## 🎯 开发策略概述

基于 [Universal OCR 工具设计文档](./tools/universal_ocr.md)，本开发计划采用MVP迭代开发方式，以**最快出可识别版本**为目标，先实现核心识别功能，再逐步完善架构和扩展性。

### 核心原则
- **功能优先**: 先实现能用的基础功能
- **快速迭代**: 每个阶段都有可交付的成果
- **用户反馈驱动**: 基于实际使用反馈调整开发优先级
- **架构演进**: 逐步向完整设计架构演进

## 📅 分阶段开发计划

### Phase 1: 核心OCR功能实现 (1-2周)
**目标**: 实现基本的文档识别能力，让用户能够使用基础OCR功能

#### 🎯 核心交付物
```
src/simacode/tools/universal_ocr/
├── __init__.py                 # 工具注册和导出
├── core.py                     # UniversalOCRTool主类
├── input_models.py             # 输入参数Pydantic模型
├── config.py                   # 配置管理
└── engines/
    ├── __init__.py
    ├── base.py                 # OCR引擎抽象基类
    └── claude_engine.py        # Claude Vision引擎实现
```

#### ✅ 实现重点

**1. 基础Tool类框架**
```python
class UniversalOCRInput(ToolInput):
    """Universal OCR输入参数模型"""
    file_path: str = Field(..., description="文档文件路径")
    output_format: str = Field("json", description="输出格式")
    confidence_threshold: float = Field(0.8, ge=0.0, le=1.0)
    scene_hint: Optional[str] = Field(None, description="场景提示")

class UniversalOCRTool(Tool):
    """通用OCR工具主类"""
    def __init__(self):
        super().__init__(
            name="universal_ocr",
            description="通用OCR识别工具",
            version="1.0.0"
        )
        self.claude_engine = ClaudeEngine()
```

**2. Claude Vision集成**
- 支持图像文件上传和处理
- 实现结构化数据提取prompt
- 处理API调用异常和重试机制
- 支持多种图像格式(JPG/PNG/PDF)

**3. 文件处理能力**
- 图像文件验证和格式检测
- PDF转图像处理(使用pdf2image)
- 文件大小和格式限制检查
- 基础图像预处理(可选)

**4. 输出格式化**
- JSON格式结构化输出
- 包含元数据(处理时间、置信度等)
- 错误信息标准化处理
- 支持原始文本输出模式

#### 🔧 技术实现要点

**配置管理**
```python
class OCRConfig:
    """OCR配置管理"""
    def __init__(self):
        self.claude_config = self._load_claude_config()
        self.supported_formats = ['.jpg', '.jpeg', '.png', '.pdf']
        self.max_file_size = 10 * 1024 * 1024  # 10MB
    
    def _load_claude_config(self):
        # 从.simacode/config.yaml加载ocr_claudeai配置
        pass
```

**引擎抽象**
```python
class OCREngine(ABC):
    """OCR引擎抽象基类"""
    @abstractmethod
    async def extract_text(self, image_path: str, prompt: str) -> Dict:
        pass
    
    @abstractmethod
    def get_engine_info(self) -> Dict:
        pass
```

#### 📋 开发任务清单
- [ ] 项目结构搭建和基础文件创建
- [ ] 输入参数模型定义和验证
- [ ] Claude Engine基础实现
- [ ] 文件处理和格式转换
- [ ] UniversalOCRTool主类实现
- [ ] 工具注册和集成测试
- [ ] 基础错误处理和日志记录
- [ ] 单元测试和集成测试

#### 🎮 验收标准
```python
# 测试用例示例
async def test_basic_ocr():
    tool = UniversalOCRTool()
    input_data = {
        "file_path": "test_documents/sample_invoice.jpg",
        "output_format": "json",
        "confidence_threshold": 0.8
    }
    
    async for result in tool.run(input_data):
        if result.type == ToolResultType.SUCCESS:
            data = json.loads(result.content)
            assert "meta" in data
            assert "extracted_data" in data
            assert data["meta"]["confidence_score"] >= 0.8
```

---

### Phase 2: 基础模板系统 (1周)
**目标**: 支持最简单的模板配置，提高识别的结构化程度

#### 🎯 核心交付物
```
src/simacode/tools/universal_ocr/
├── templates/
│   ├── __init__.py
│   ├── manager.py              # 模板管理器
│   ├── loader.py               # 模板加载器
│   ├── schema.py               # 模板数据模型
│   └── builtin/
│       ├── invoice.yaml        # 发票模板
│       ├── transcript.yaml     # 成绩单模板
│       └── bank_statement.yaml # 银行对账单模板
└── processors/
    ├── __init__.py
    └── template_processor.py   # 模板处理器
```

#### ✅ 实现重点

**1. 简化模板格式**
```yaml
# templates/builtin/invoice.yaml
template:
  name: "通用发票模板"
  version: "1.0.0"
  description: "适用于标准发票格式"
  
  fields:
    invoice_number:
      name: "发票号码"
      type: "string"
      required: true
      description: "发票的唯一编号"
      
    issue_date:
      name: "开票日期"
      type: "date"
      required: true
      format: "YYYY-MM-DD"
      
    vendor_name:
      name: "开票方名称"
      type: "string"
      required: true
      
    total_amount:
      name: "总金额"
      type: "number"
      required: true
      description: "发票总金额"
  
  extraction_prompt: |
    请仔细识别这张发票图片中的以下信息：
    1. 发票号码 - 通常在发票右上角
    2. 开票日期 - 格式为YYYY-MM-DD
    3. 开票方名称 - 销售方或服务提供方名称
    4. 总金额 - 发票的总计金额
    
    请以JSON格式返回结果，确保字段名与要求完全一致。
```

**2. 模板管理系统**
```python
class TemplateManager:
    """模板管理器"""
    def __init__(self):
        self.builtin_templates = {}
        self.template_loader = TemplateLoader()
    
    async def load_builtin_templates(self):
        """加载内置模板"""
        template_dir = Path(__file__).parent / "builtin"
        for template_file in template_dir.glob("*.yaml"):
            template = await self.template_loader.load_template(template_file)
            self.builtin_templates[template.name] = template
    
    def get_template(self, template_name: str) -> Optional[Template]:
        """获取指定模板"""
        return self.builtin_templates.get(template_name)
    
    def list_templates(self) -> List[str]:
        """列出所有可用模板"""
        return list(self.builtin_templates.keys())
```

**3. 模板数据模型**
```python
class TemplateField(BaseModel):
    """模板字段定义"""
    name: str
    type: str
    required: bool = False
    description: Optional[str] = None
    format: Optional[str] = None

class Template(BaseModel):
    """模板定义"""
    name: str
    version: str
    description: str
    fields: Dict[str, TemplateField]
    extraction_prompt: str
```

**4. 三个基础内置模板**
- **发票模板**: 发票号、开票日期、开票方、总金额
- **成绩单模板**: 学生姓名、学号、课程成绩、GPA
- **银行对账单模板**: 账户信息、交易记录、余额

#### 📋 开发任务清单
- [ ] 模板数据模型设计和实现
- [ ] YAML模板加载器实现
- [ ] 模板管理器核心功能
- [ ] 三个内置模板配置文件
- [ ] 模板驱动的提取逻辑
- [ ] 模板验证和错误处理
- [ ] 模板系统集成测试

#### 🎮 验收标准
```python
async def test_template_system():
    template_manager = TemplateManager()
    await template_manager.load_builtin_templates()
    
    # 测试模板加载
    invoice_template = template_manager.get_template("invoice")
    assert invoice_template is not None
    assert "invoice_number" in invoice_template.fields
    
    # 测试模板驱动识别
    tool = UniversalOCRTool()
    result = await tool.run({
        "file_path": "test_invoice.jpg",
        "scene_hint": "invoice"
    })
    
    data = json.loads(result.content)
    assert "invoice_number" in data["extracted_data"]
    assert "total_amount" in data["extracted_data"]
```

---

### Phase 3: 简单场景识别 (3-5天)
**目标**: 自动识别文档类型并选择合适的模板

#### 🎯 核心交付物
```
src/simacode/tools/universal_ocr/
├── scene_detection/
│   ├── __init__.py
│   ├── detector.py             # 场景识别器
│   ├── rules.py                # 识别规则
│   └── keywords.py             # 关键词配置
└── utils/
    ├── __init__.py
    └── text_analyzer.py        # 文本分析工具
```

#### ✅ 实现重点

**1. 关键词匹配识别**
```python
class SceneDetector:
    """场景识别器"""
    def __init__(self):
        self.keyword_rules = {
            "invoice": {
                "keywords": ["发票", "invoice", "税号", "增值税", "开票方", "购买方"],
                "weight": {"发票": 3, "invoice": 3, "税号": 2, "增值税": 2},
                "threshold": 0.6
            },
            "transcript": {
                "keywords": ["成绩单", "transcript", "GPA", "学期", "课程", "学分"],
                "weight": {"成绩单": 3, "transcript": 3, "GPA": 2},
                "threshold": 0.6
            },
            "bank_statement": {
                "keywords": ["对账单", "银行", "余额", "交易", "账户", "statement"],
                "weight": {"对账单": 3, "银行": 2, "余额": 2},
                "threshold": 0.6
            }
        }
    
    async def detect_scene(self, image_path: str) -> SceneDetectionResult:
        """检测文档场景"""
        # 1. 快速文本提取
        preview_text = await self._extract_text_preview(image_path)
        
        # 2. 关键词匹配和评分
        scene_scores = self._calculate_scene_scores(preview_text)
        
        # 3. 选择最佳匹配
        best_scene = max(scene_scores.items(), key=lambda x: x[1])
        
        return SceneDetectionResult(
            detected_scene=best_scene[0],
            confidence=best_scene[1],
            alternative_scenes=sorted(
                [(k, v) for k, v in scene_scores.items() if k != best_scene[0]],
                key=lambda x: x[1], reverse=True
            )
        )
```

**2. 文本预处理和分析**
```python
class TextAnalyzer:
    """文本分析工具"""
    def __init__(self):
        self.stop_words = {"的", "是", "在", "有", "和", "与"}
    
    def extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        # 简单的关键词提取逻辑
        words = self._tokenize(text)
        keywords = [w for w in words if w not in self.stop_words]
        return keywords
    
    def calculate_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度"""
        # 基于关键词重叠度的相似度计算
        keywords1 = set(self.extract_keywords(text1))
        keywords2 = set(self.extract_keywords(text2))
        
        if not keywords1 or not keywords2:
            return 0.0
            
        intersection = keywords1.intersection(keywords2)
        union = keywords1.union(keywords2)
        
        return len(intersection) / len(union)
```

**3. 场景检测结果模型**
```python
class SceneDetectionResult(BaseModel):
    """场景检测结果"""
    detected_scene: str
    confidence: float
    alternative_scenes: List[Tuple[str, float]]
    detection_factors: Dict[str, Any] = Field(default_factory=dict)
```

#### 📋 开发任务清单
- [ ] 场景检测器核心算法实现
- [ ] 关键词规则配置和管理
- [ ] 文本分析工具开发
- [ ] 快速文本预览功能
- [ ] 场景检测结果模型
- [ ] 与模板系统集成
- [ ] 场景检测准确性测试

#### 🎮 验收标准
```python
async def test_scene_detection():
    detector = SceneDetector()
    
    # 测试发票识别
    result = await detector.detect_scene("test_invoice.jpg")
    assert result.detected_scene == "invoice"
    assert result.confidence > 0.6
    
    # 测试成绩单识别
    result = await detector.detect_scene("test_transcript.jpg")
    assert result.detected_scene == "transcript"
    assert result.confidence > 0.6
```

---

### Phase 4: 用户自定义模板 (1周)
**目标**: 支持用户创建和管理自定义模板

#### 🎯 核心交付物
```
src/simacode/tools/universal_ocr/
├── templates/
│   ├── user_manager.py         # 用户模板管理
│   ├── validator.py            # 模板验证器
│   └── user/                   # 用户模板存储目录
└── commands/
    ├── __init__.py
    └── template_commands.py    # 模板管理命令
```

#### ✅ 实现重点

**1. 用户模板管理API**
```python
class UserTemplateManager:
    """用户模板管理器"""
    def __init__(self, user_templates_dir: Path):
        self.user_templates_dir = user_templates_dir
        self.validator = TemplateValidator()
    
    async def create_template(self, config: Dict, user_id: str) -> str:
        """创建用户模板"""
        # 1. 验证模板配置
        validation_result = self.validator.validate(config)
        if not validation_result.is_valid:
            raise TemplateValidationError(validation_result.errors)
        
        # 2. 生成模板ID
        template_id = f"user_{user_id}_{uuid.uuid4().hex[:8]}"
        
        # 3. 保存模板文件
        template_file = self.user_templates_dir / f"{template_id}.yaml"
        await self._save_template(config, template_file)
        
        return template_id
    
    async def update_template(self, template_id: str, updates: Dict, user_id: str) -> bool:
        """更新用户模板"""
        template_file = self._get_template_file(template_id, user_id)
        if not template_file.exists():
            return False
        
        # 加载现有配置
        current_config = await self._load_template(template_file)
        
        # 合并更新
        updated_config = self._merge_config(current_config, updates)
        
        # 验证更新后的配置
        validation_result = self.validator.validate(updated_config)
        if not validation_result.is_valid:
            raise TemplateValidationError(validation_result.errors)
        
        # 保存更新
        await self._save_template(updated_config, template_file)
        return True
    
    async def delete_template(self, template_id: str, user_id: str) -> bool:
        """删除用户模板"""
        template_file = self._get_template_file(template_id, user_id)
        if template_file.exists():
            template_file.unlink()
            return True
        return False
    
    async def list_user_templates(self, user_id: str) -> List[Dict]:
        """列出用户的所有模板"""
        user_dir = self.user_templates_dir / user_id
        if not user_dir.exists():
            return []
        
        templates = []
        for template_file in user_dir.glob("*.yaml"):
            template_config = await self._load_template(template_file)
            templates.append({
                "id": template_file.stem,
                "name": template_config["template"]["name"],
                "description": template_config["template"].get("description", ""),
                "created_at": template_file.stat().st_ctime
            })
        
        return templates
```

**2. 模板验证器**
```python
class TemplateValidator:
    """模板配置验证器"""
    def validate(self, config: Dict) -> ValidationResult:
        """验证模板配置"""
        errors = []
        
        # 检查必需字段
        if "template" not in config:
            errors.append("Missing 'template' section")
            return ValidationResult(False, errors)
        
        template_config = config["template"]
        
        # 检查模板元数据
        required_meta = ["name", "fields"]
        for field in required_meta:
            if field not in template_config:
                errors.append(f"Missing required field: {field}")
        
        # 验证字段定义
        if "fields" in template_config:
            field_errors = self._validate_fields(template_config["fields"])
            errors.extend(field_errors)
        
        # 验证提取prompt
        if "extraction_prompt" in template_config:
            prompt_errors = self._validate_prompt(template_config["extraction_prompt"])
            errors.extend(prompt_errors)
        
        return ValidationResult(len(errors) == 0, errors)
    
    def _validate_fields(self, fields: Dict) -> List[str]:
        """验证字段定义"""
        errors = []
        valid_types = ["string", "number", "date", "boolean", "array", "object"]
        
        for field_name, field_config in fields.items():
            if not isinstance(field_config, dict):
                errors.append(f"Field '{field_name}' must be a dictionary")
                continue
            
            # 检查字段类型
            if "type" not in field_config:
                errors.append(f"Field '{field_name}' missing type")
            elif field_config["type"] not in valid_types:
                errors.append(f"Field '{field_name}' has invalid type: {field_config['type']}")
        
        return errors
```

**3. 命令行接口**
```python
class TemplateCommands:
    """模板管理命令"""
    def __init__(self):
        self.user_manager = UserTemplateManager()
    
    async def create_template_interactive(self, user_id: str):
        """交互式创建模板"""
        print("🎯 创建自定义OCR模板")
        
        # 收集基本信息
        name = input("模板名称: ")
        description = input("模板描述: ")
        
        # 字段定义
        fields = {}
        print("\n请定义需要提取的字段:")
        while True:
            field_name = input("字段名称 (回车结束): ")
            if not field_name:
                break
            
            field_type = input(f"字段类型 [string/number/date]: ") or "string"
            required = input(f"是否必需 [y/N]: ").lower() == 'y'
            field_description = input(f"字段描述: ") or ""
            
            fields[field_name] = {
                "name": field_name,
                "type": field_type,
                "required": required,
                "description": field_description
            }
        
        # 生成提取prompt
        prompt = self._generate_extraction_prompt(fields)
        print(f"\n生成的提取prompt:\n{prompt}")
        
        custom_prompt = input("\n是否自定义prompt? [y/N]: ")
        if custom_prompt.lower() == 'y':
            prompt = input("请输入自定义prompt: ")
        
        # 构建模板配置
        template_config = {
            "template": {
                "name": name,
                "description": description,
                "version": "1.0.0",
                "fields": fields,
                "extraction_prompt": prompt
            }
        }
        
        # 创建模板
        try:
            template_id = await self.user_manager.create_template(template_config, user_id)
            print(f"✅ 模板创建成功! ID: {template_id}")
        except TemplateValidationError as e:
            print(f"❌ 模板验证失败: {', '.join(e.errors)}")
    
    async def list_templates(self, user_id: str):
        """列出用户模板"""
        templates = await self.user_manager.list_user_templates(user_id)
        
        if not templates:
            print("📋 暂无自定义模板")
            return
        
        print("📋 您的模板列表:")
        for template in templates:
            print(f"- {template['name']} ({template['id']})")
            print(f"  描述: {template['description']}")
            print()
```

#### 📋 开发任务清单
- [ ] 用户模板管理API实现
- [ ] 模板验证器开发
- [ ] 用户模板存储机制
- [ ] 命令行交互界面
- [ ] 模板CRUD操作测试
- [ ] 用户权限和隔离机制
- [ ] 模板使用统计和分析

#### 🎮 验收标准
```python
async def test_user_templates():
    user_manager = UserTemplateManager()
    user_id = "test_user"
    
    # 测试创建模板
    template_config = {
        "template": {
            "name": "测试模板",
            "fields": {
                "test_field": {"name": "测试字段", "type": "string", "required": True}
            },
            "extraction_prompt": "请提取测试字段"
        }
    }
    
    template_id = await user_manager.create_template(template_config, user_id)
    assert template_id is not None
    
    # 测试列出模板
    templates = await user_manager.list_user_templates(user_id)
    assert len(templates) == 1
    assert templates[0]["name"] == "测试模板"
    
    # 测试删除模板
    success = await user_manager.delete_template(template_id, user_id)
    assert success == True
```

---

### Phase 5: 性能优化和扩展 (持续迭代)
**目标**: 优化性能，增加高级功能，完善系统架构

#### 🎯 核心交付物
```
src/simacode/tools/universal_ocr/
├── cache/
│   ├── __init__.py
│   ├── manager.py              # 缓存管理器
│   └── backends/
│       ├── memory.py           # 内存缓存
│       └── redis.py            # Redis缓存
├── engines/
│   ├── paddleocr_engine.py     # PaddleOCR引擎
│   ├── tesseract_engine.py     # Tesseract引擎
│   └── scheduler.py            # 引擎调度器
├── batch/
│   ├── __init__.py
│   └── processor.py            # 批量处理器
└── monitoring/
    ├── __init__.py
    ├── metrics.py              # 性能指标
    └── stats.py                # 使用统计
```

#### ✅ 实现重点

**1. 缓存机制**
```python
class OCRCacheManager:
    """OCR结果缓存管理器"""
    def __init__(self, backend="memory"):
        if backend == "memory":
            self.cache = MemoryCache()
        elif backend == "redis":
            self.cache = RedisCache()
        else:
            raise ValueError(f"Unsupported cache backend: {backend}")
    
    async def get_cached_result(self, file_path: str) -> Optional[Dict]:
        """获取缓存的OCR结果"""
        file_hash = self._calculate_file_hash(file_path)
        return await self.cache.get(f"ocr:{file_hash}")
    
    async def cache_result(self, file_path: str, result: Dict, ttl: int = 3600):
        """缓存OCR结果"""
        file_hash = self._calculate_file_hash(file_path)
        await self.cache.set(f"ocr:{file_hash}", result, ttl)
    
    def _calculate_file_hash(self, file_path: str) -> str:
        """计算文件哈希值"""
        with open(file_path, 'rb') as f:
            content = f.read()
            return hashlib.md5(content).hexdigest()
```

**2. 多引擎支持**
```python
class EngineScheduler:
    """OCR引擎调度器"""
    def __init__(self):
        self.engines = {
            "claude": ClaudeEngine(),
            "paddleocr": PaddleOCREngine(),
            "tesseract": TesseractEngine()
        }
        self.default_strategy = "quality_first"
    
    async def extract_with_strategy(
        self, 
        file_path: str, 
        template: Template,
        strategy: str = None
    ) -> ExtractionResult:
        """根据策略选择引擎进行提取"""
        strategy = strategy or self.default_strategy
        
        if strategy == "quality_first":
            return await self._quality_first_extraction(file_path, template)
        elif strategy == "speed_first":
            return await self._speed_first_extraction(file_path, template)
        elif strategy == "cost_first":
            return await self._cost_first_extraction(file_path, template)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
    
    async def _quality_first_extraction(self, file_path: str, template: Template):
        """质量优先策略"""
        # 优先使用Claude，失败时降级到其他引擎
        try:
            return await self.engines["claude"].extract(file_path, template)
        except Exception:
            return await self.engines["paddleocr"].extract(file_path, template)
```

**3. 批量处理**
```python
class BatchProcessor:
    """批量处理器"""
    def __init__(self, max_concurrent: int = 5):
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.stats = BatchStats()
    
    async def process_batch(
        self, 
        documents: List[Dict],
        progress_callback: Optional[Callable] = None
    ) -> List[ExtractionResult]:
        """批量处理文档"""
        tasks = []
        for i, doc in enumerate(documents):
            task = self._process_single_document(doc, i, len(documents), progress_callback)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 统计结果
        self.stats.update_batch_results(results)
        
        return [r for r in results if not isinstance(r, Exception)]
    
    async def _process_single_document(
        self, 
        doc: Dict, 
        index: int, 
        total: int,
        progress_callback: Optional[Callable]
    ) -> ExtractionResult:
        """处理单个文档"""
        async with self.semaphore:
            try:
                # 执行OCR
                tool = UniversalOCRTool()
                result = await tool.extract_document(**doc)
                
                # 更新进度
                if progress_callback:
                    progress = int((index + 1) / total * 100)
                    progress_callback(progress)
                
                return result
            except Exception as e:
                self.stats.record_error(str(e))
                raise
```

**4. 性能监控**
```python
class PerformanceMonitor:
    """性能监控器"""
    def __init__(self):
        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "average_processing_time": 0.0,
            "engine_usage": {},
            "template_usage": {},
            "error_types": {}
        }
    
    def record_request(
        self, 
        success: bool, 
        processing_time: float,
        engine: str,
        template: str,
        error_type: Optional[str] = None
    ):
        """记录请求指标"""
        self.metrics["total_requests"] += 1
        
        if success:
            self.metrics["successful_requests"] += 1
        else:
            self.metrics["failed_requests"] += 1
            if error_type:
                self.metrics["error_types"][error_type] = \
                    self.metrics["error_types"].get(error_type, 0) + 1
        
        # 更新平均处理时间
        current_avg = self.metrics["average_processing_time"]
        total_requests = self.metrics["total_requests"]
        self.metrics["average_processing_time"] = \
            (current_avg * (total_requests - 1) + processing_time) / total_requests
        
        # 记录引擎使用
        self.metrics["engine_usage"][engine] = \
            self.metrics["engine_usage"].get(engine, 0) + 1
        
        # 记录模板使用
        self.metrics["template_usage"][template] = \
            self.metrics["template_usage"].get(template, 0) + 1
    
    def get_performance_report(self) -> Dict:
        """获取性能报告"""
        total = self.metrics["total_requests"]
        if total == 0:
            return {"message": "No requests recorded"}
        
        success_rate = self.metrics["successful_requests"] / total
        
        return {
            "total_requests": total,
            "success_rate": f"{success_rate:.1%}",
            "average_processing_time": f"{self.metrics['average_processing_time']:.2f}s",
            "most_used_engine": max(self.metrics["engine_usage"].items(), key=lambda x: x[1])[0],
            "most_used_template": max(self.metrics["template_usage"].items(), key=lambda x: x[1])[0],
            "top_errors": sorted(self.metrics["error_types"].items(), key=lambda x: x[1], reverse=True)[:5]
        }
```

#### 📋 开发任务清单
- [ ] 缓存系统设计和实现
- [ ] PaddleOCR引擎集成
- [ ] Tesseract引擎集成
- [ ] 引擎调度策略实现
- [ ] 批量处理功能开发
- [ ] 性能监控系统
- [ ] 使用统计和分析
- [ ] 系统优化和调优

---

## 🚀 快速启动指南

### 开发环境准备
```bash
# 1. 创建项目结构
mkdir -p src/simacode/tools/universal_ocr/{engines,templates/builtin,commands,cache,batch}

# 2. 安装开发依赖
pip install anthropic pillow pdf2image pyyaml pydantic

# 3. 创建核心文件
touch src/simacode/tools/universal_ocr/{__init__.py,core.py,input_models.py,config.py}
touch src/simacode/tools/universal_ocr/engines/{__init__.py,base.py,claude_engine.py}
```

### 第一周开发重点
1. **Day 1-2**: 项目结构搭建 + Claude引擎基础实现
2. **Day 3-4**: UniversalOCRTool主类 + 文件处理逻辑
3. **Day 5**: 工具注册 + 基础测试 + 错误处理
4. **Day 6-7**: 集成测试 + 文档更新 + 优化调试

### 验证里程碑
```python
# Phase 1 验收测试
async def validate_phase1():
    """验证Phase 1核心功能"""
    tool = UniversalOCRTool()
    
    test_cases = [
        {"file_path": "test_invoice.jpg", "expected_fields": ["invoice_number", "total_amount"]},
        {"file_path": "test_transcript.pdf", "expected_fields": ["student_name", "gpa"]},
        {"file_path": "test_statement.png", "expected_fields": ["account_number", "balance"]}
    ]
    
    for case in test_cases:
        result = await tool.run({"file_path": case["file_path"]})
        assert result.type == ToolResultType.SUCCESS
        
        data = json.loads(result.content)
        assert "extracted_data" in data
        assert "meta" in data
        assert data["meta"]["confidence_score"] > 0.5
        
        print(f"✅ {case['file_path']} 测试通过")
```

## 📊 成功指标定义

### Phase 1 成功标准
- [ ] 能够处理JPG/PNG/PDF格式文件
- [ ] Claude API集成成功率 > 95%
- [ ] 基础文本提取准确率 > 80%
- [ ] 处理时间 < 10秒/文档
- [ ] 错误处理覆盖主要异常场景

### Phase 2 成功标准
- [ ] 三个内置模板识别准确率 > 85%
- [ ] 模板加载和切换功能正常
- [ ] 结构化数据提取完整性 > 90%
- [ ] 模板配置验证机制完善

### Phase 3 成功标准
- [ ] 场景自动识别准确率 > 80%
- [ ] 支持fallback到手动指定场景
- [ ] 识别速度 < 2秒
- [ ] 支持新场景快速扩展

### Phase 4 成功标准
- [ ] 用户模板创建和管理功能完整
- [ ] 模板配置验证准确率 > 95%
- [ ] 支持模板测试和优化建议
- [ ] 用户界面友好易用

### Phase 5 成功标准
- [ ] 缓存命中率 > 60%
- [ ] 批量处理性能提升 > 50%
- [ ] 系统整体稳定性 > 99%
- [ ] 支持并发处理 > 10个文档

## 🔄 持续改进策略

### 用户反馈循环
1. **快速发布**: 每个Phase完成后立即发布alpha版本
2. **收集反馈**: 通过使用日志和用户调研收集反馈
3. **优先级调整**: 根据实际使用情况调整后续开发重点
4. **快速迭代**: 保持2周一个小版本的发布节奏

### 质量保证
1. **自动化测试**: 每个Phase都要有完整的单元测试和集成测试
2. **性能基准**: 建立性能基准线，持续监控性能指标
3. **代码审查**: 关键功能代码必须经过同行审查
4. **文档同步**: 代码更新必须同步更新文档

### 技术债务管理
1. **重构计划**: 每个Phase结束后评估技术债务并制定重构计划
2. **架构演进**: 逐步向最终设计架构迁移，避免大爆炸式重构
3. **依赖管理**: 控制外部依赖，优先使用稳定可靠的库
4. **安全考虑**: 每个阶段都要考虑安全性，特别是用户数据处理

---

## 📈 项目里程碑时间线

```
Week 1-2: Phase 1 - 核心OCR功能
├── Day 1-2: 环境搭建 + Claude集成
├── Day 3-4: 工具类实现 + 文件处理
├── Day 5-7: 测试优化 + bug修复
└── 🎯 里程碑: 基础OCR功能可用

Week 3: Phase 2 - 模板系统
├── Day 1-2: 模板框架 + 内置模板
├── Day 3-4: 模板管理器 + 验证器
├── Day 5: 集成测试 + 优化
└── 🎯 里程碑: 结构化提取能力

Week 4: Phase 3-4 - 场景识别 + 用户模板
├── Day 1-2: 场景识别算法
├── Day 3-5: 用户模板管理系统
└── 🎯 里程碑: 完整的模板生态

Week 5+: Phase 5 - 性能优化
├── 缓存系统实现
├── 多引擎支持
├── 批量处理功能
└── 🎯 里程碑: 生产就绪版本
```

通过这个MVP开发计划，我们可以在最短时间内(1-2周)交付一个可用的Universal OCR工具，然后通过快速迭代不断完善功能。重点是**先让用户用起来**，再基于实际使用推翻假设和完善功能。