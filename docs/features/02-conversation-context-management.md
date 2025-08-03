# 对话上下文管理完整方案

## 📋 概述

本文档详细描述了为确保session中的对话能带上完整上下文的改进方案。这些方案旨在解决对话连续性问题，确保AI能够获得足够的历史信息来进行有效的交互。

## 🎯 问题背景

当前系统已实现了基础的对话上下文功能，但存在以下改进空间：
- 需要更灵活的上下文保留策略
- 用户需要能够选择不同的上下文处理方式
- 需要平衡完整性与性能的需求
- 需要智能的上下文压缩和保留机制

## 🔧 改进方案

### 1. 配置驱动的上下文策略

#### 1.1 配置文件扩展

在 `.simacode/config.yaml` 中添加专门的对话上下文配置：

```yaml
# 对话上下文配置
conversation_context:
  # 上下文策略: "full", "compressed", "adaptive"
  strategy: "full"
  
  # 完整模式设置
  full_context:
    max_messages: 100        # 最大保留消息数
    max_tokens: 8000         # 最大token限制
    preserve_all: true       # 是否保留所有消息
  
  # 压缩模式设置  
  compressed_context:
    recent_messages: 5       # 最近消息完整保留数量
    medium_recent: 10        # 中等最近消息数量
    compression_ratio: 0.3   # 压缩比例
    preserve_topics: true    # 是否保留话题摘要
  
  # 自适应模式设置
  adaptive_context:
    token_budget: 4000       # token预算
    min_recent: 3           # 最少保留的最近消息
    auto_summarize: true    # 自动摘要老旧对话
```

#### 1.2 配置模型定义

在 `src/simacode/config.py` 中添加：

```python
class ConversationContextConfig(BaseModel):
    """Conversation context configuration model."""
    
    strategy: str = Field(
        default="adaptive",
        description="Context strategy: full, compressed, adaptive"
    )
    
    # Full context settings
    max_messages: int = Field(default=100, description="Maximum messages to preserve")
    max_tokens: int = Field(default=8000, description="Maximum tokens limit")
    preserve_all: bool = Field(default=False, description="Preserve all messages")
    
    # Compressed context settings
    recent_messages: int = Field(default=5, description="Recent messages to preserve fully")
    medium_recent: int = Field(default=10, description="Medium recent messages count")
    compression_ratio: float = Field(default=0.3, ge=0.1, le=1.0, description="Compression ratio")
    preserve_topics: bool = Field(default=True, description="Preserve topic summaries")
    
    # Adaptive context settings
    token_budget: int = Field(default=4000, description="Token budget for adaptive mode")
    min_recent: int = Field(default=3, description="Minimum recent messages to preserve")
    auto_summarize: bool = Field(default=True, description="Auto-summarize old conversations")
    
    @validator('strategy')
    def validate_strategy(cls, v: str) -> str:
        valid_strategies = {'full', 'compressed', 'adaptive'}
        if v.lower() not in valid_strategies:
            raise ValueError(f"Invalid strategy: {v}. Must be one of {valid_strategies}")
        return v.lower()
```

### 2. 实施方案详解

#### 方案A: 完整上下文保留（推荐用于重要对话）

**适用场景**: 重要的项目讨论、复杂的技术决策、需要完整历史的长期对话

```python
def _get_full_conversation_context(self, history: List[Message], config) -> str:
    """保留完整对话上下文，只在必要时截断"""
    if not history:
        return "No prior conversation"
    
    # 根据配置决定保留策略
    if config.preserve_all:
        # 保留所有消息
        return self._format_all_messages(history)
    
    # 按token限制截断
    if len(history) > config.max_messages:
        # 保留最近的N条消息
        recent_history = history[-config.max_messages:]
        truncated_count = len(history) - config.max_messages
        context = f"[Earlier conversation truncated: {truncated_count} messages]\\n\\n"
        context += self._format_all_messages(recent_history)
        return context
    
    return self._format_all_messages(history)

def _format_all_messages(self, messages: List[Message]) -> str:
    """格式化所有消息为完整上下文"""
    formatted = []
    for i, msg in enumerate(messages, 1):
        role_label = "User" if msg.role == "user" else "Assistant"
        formatted.append(f"[{i}] {role_label}: {msg.content}")
    return "\\n".join(formatted)
```

**优点**: 
- 保留完整信息，不丢失任何细节
- 适合需要完整历史的复杂对话
- 实现简单，逻辑清晰

**缺点**: 
- Token消耗较大
- 可能影响响应速度
- 需要更大的模型上下文窗口

#### 方案B: 智能分层压缩

**适用场景**: 平衡完整性和性能的日常对话

```python
def _adaptive_context_compression(self, history: List[Message], config) -> str:
    """自适应上下文压缩，根据token预算智能分层"""
    
    # 按重要性分层
    layers = self._categorize_messages_by_importance(history)
    
    context_parts = []
    used_tokens = 0
    
    # 优先级1: 最近3条消息（完整保留）
    for msg in layers['critical'][-3:]:
        if used_tokens < config.token_budget * 0.6:  # 60%预算给最近消息
            context_parts.append(f"{msg.role}: {msg.content}")
            used_tokens += len(msg.content) // 4  # 粗略token估算
    
    # 优先级2: 重要决策点和关键信息
    for msg in layers['important']:
        if used_tokens < config.token_budget * 0.9:  # 90%预算
            compressed = self._compress_message(msg, compression_level=0.5)
            context_parts.append(compressed)
            used_tokens += len(compressed) // 4
    
    # 优先级3: 话题摘要
    if used_tokens < config.token_budget:
        topic_summary = self._extract_topic_summary(layers['background'])
        context_parts.insert(0, f"[Session Summary]: {topic_summary}")
    
    return "\\n".join(context_parts)

def _categorize_messages_by_importance(self, history: List[Message]) -> Dict[str, List[Message]]:
    """按重要性对消息分层"""
    layers = {
        'critical': [],    # 最近的消息
        'important': [],   # 包含关键决策的消息
        'background': []   # 背景信息
    }
    
    for i, msg in enumerate(history):
        # 最近的消息标记为关键
        if i >= len(history) - 5:
            layers['critical'].append(msg)
        # 包含特定关键词的消息标记为重要
        elif any(keyword in msg.content.lower() for keyword in [
            'decision', 'important', 'error', 'problem', 'solution', 
            '决定', '重要', '错误', '问题', '解决'
        ]):
            layers['important'].append(msg)
        else:
            layers['background'].append(msg)
    
    return layers
```

**优点**: 
- 智能平衡完整性和性能
- 保留关键信息的同时控制token使用
- 可配置的压缩策略

**缺点**: 
- 实现复杂度较高
- 需要调优重要性判断逻辑
- 可能错误分类某些消息

#### 方案C: 语义相关性保留

**适用场景**: 聚焦于当前讨论主题的对话

```python
def _semantic_context_retention(self, history: List[Message], current_input: str) -> str:
    """根据与当前输入的语义相关性保留上下文"""
    
    # 计算每条消息与当前输入的相关性
    relevance_scores = []
    for msg in history:
        score = self._calculate_semantic_similarity(msg.content, current_input)
        relevance_scores.append((msg, score))
    
    # 按相关性排序
    relevance_scores.sort(key=lambda x: x[1], reverse=True)
    
    # 构建上下文
    context_parts = []
    
    # 1. 始终包含最近的3条消息
    recent_messages = history[-3:]
    for msg in recent_messages:
        context_parts.append(f"{msg.role}: {msg.content}")
    
    # 2. 添加高相关性的历史消息
    for msg, score in relevance_scores:
        if score > 0.7 and msg not in recent_messages:  # 高相关性阈值
            context_parts.insert(-3, f"[Relevant context]: {msg.role}: {msg.content[:200]}...")
    
    return "\\n".join(context_parts)

def _calculate_semantic_similarity(self, text1: str, text2: str) -> float:
    """计算两段文本的语义相似性（简化版本）"""
    # 简化实现：基于关键词重叠
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    
    # 移除停用词
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', '的', '是', '在', '和', '或', '但是', '如果', '那么'}
    words1 = words1 - stop_words
    words2 = words2 - stop_words
    
    if not words1 or not words2:
        return 0.0
    
    # 计算Jaccard相似性
    intersection = len(words1.intersection(words2))
    union = len(words1.union(words2))
    
    return intersection / union if union > 0 else 0.0
```

**优点**: 
- 聚焦于相关内容
- 减少噪音信息
- 适合主题跳跃的对话

**缺点**: 
- 可能丢失重要的上下文连接
- 语义相似性计算的准确性有限
- 需要更复杂的NLP技术支持

### 3. 实施建议优先级

#### 立即实施 (高优先级)

1. **完整上下文模式**: 
   - 设置 `strategy: "full"` 在配置中
   - 实现基础的完整消息保留
   - 添加token限制保护

2. **配置基础架构**:
   - 扩展Config类支持conversation_context
   - 更新配置文件模板
   - 添加配置验证逻辑

3. **消息优先级处理**:
   - 最近消息 > 关键决策 > 话题摘要
   - 实现简单的重要性判断

#### 短期实施 (中优先级)

4. **智能截断机制**:
   - 基于重要性而非时间顺序截断
   - 保留关键决策点和错误处理信息
   - 实现渐进式压缩

5. **话题连续性保持**:
   - 识别并保留关键话题转折点
   - 维护对话的逻辑连贯性
   - 添加话题变化检测

6. **用户配置选项**:
   - 提供多种上下文策略选择
   - 支持运行时切换策略
   - 添加配置预设模板

#### 长期优化 (低优先级)

7. **语义搜索增强**:
   - 基于当前问题检索相关历史对话
   - 实现向量化搜索
   - 添加语义相似性缓存

8. **AI驱动的摘要**:
   - 使用AI自动生成高质量的对话摘要
   - 实现渐进式摘要更新
   - 添加摘要质量评估

9. **动态策略调整**:
   - 根据对话类型自动调整上下文策略
   - 学习用户偏好
   - 实现自适应token管理

### 4. 快速实施方案

如果需要立即获得完整上下文支持，推荐以下最简实施路径：

#### 步骤1: 修改配置
```yaml
conversation_context:
  strategy: "full"
  max_messages: 50
  max_tokens: 6000
  preserve_all: false
```

#### 步骤2: 更新Planner
在 `planner.py` 中修改 `_summarize_conversation_history` 方法：

```python
def _summarize_conversation_history(self, history: List[Message]) -> str:
    """使用配置驱动的上下文策略"""
    if not history:
        return "No prior conversation"
    
    # 获取配置
    config = self.config.conversation_context if hasattr(self, 'config') else None
    
    if config and config.strategy == "full":
        return self._get_full_conversation_context(history, config)
    else:
        # 回退到现有的压缩策略
        return self._compact_conversation_with_recency_bias(history)
```

#### 步骤3: 添加安全检查
```python
def _ensure_token_limit(self, context: str, max_tokens: int) -> str:
    """确保上下文不超过token限制"""
    estimated_tokens = len(context) // 4  # 粗略估算
    
    if estimated_tokens <= max_tokens:
        return context
    
    # 截断到安全长度
    safe_length = max_tokens * 4 * 0.9  # 90%安全边际
    return context[:int(safe_length)] + "\\n[Context truncated due to length limit]"
```

## 🔄 实施时间线

### 第1周: 基础架构
- [ ] 扩展配置模型
- [ ] 实现完整上下文模式
- [ ] 添加基础的token限制

### 第2周: 智能压缩
- [ ] 实现分层压缩策略
- [ ] 添加重要性判断逻辑
- [ ] 测试不同压缩比例

### 第3周: 用户配置
- [ ] 添加运行时配置切换
- [ ] 实现配置预设
- [ ] 添加配置验证

### 第4周: 优化与测试
- [ ] 性能优化
- [ ] 全面测试各种场景
- [ ] 文档完善

## 📊 效果预期

### 性能指标
- **上下文完整性**: 95%+ (完整模式)
- **Token效率**: 60%+ 节省 (压缩模式)
- **响应延迟**: <200ms 增加
- **准确性提升**: 30%+ (基于历史上下文的回答)

### 用户体验
- AI能够准确引用之前的对话内容
- 减少重复解释和背景介绍
- 提高多轮对话的连贯性
- 支持复杂项目的长期讨论

## 🚨 注意事项

### 技术限制
- 模型上下文窗口限制
- Token成本考虑
- 内存使用优化
- 处理大量历史数据的性能

### 安全考虑
- 敏感信息的自动过滤
- 上下文数据的安全存储
- 用户隐私保护
- 会话数据的生命周期管理

### 维护考虑
- 配置复杂性管理
- 不同策略的测试覆盖
- 性能监控和调优
- 用户反馈收集和改进

## 📚 相关文档

- [会话管理架构](./session-management.md)
- [AI客户端配置](./ai-client-config.md)
- [性能优化指南](./performance-optimization.md)
- [安全最佳实践](./security-best-practices.md)