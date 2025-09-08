#!/usr/bin/env python3
"""
TICMaker MCP Server for SimaCode
专门处理互动教学HTML页面创建和修改的MCP服务器
支持多种模板类型和智能内容生成
"""

import asyncio
import json
import logging
import os
import sys
import uuid
import yaml
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# AI client imports
try:
    import openai
except ImportError:
    openai = None
    
try:
    import anthropic
except ImportError:
    anthropic = None

TICMAKER_PROMPT = """
TICMaker是一个基于AI技术来设计教学互动项目（比如提问与回答，投票与选择题，简单题与词云，随堂测试，小组讨论，头脑风暴，短周期项目模块，基础模拟实验，编程与代码运行，游戏化学习徽章，学生展示与互评，虚拟画廊漫步）与教学多模态内容生成（HTML互动游戏，AI生成视频，AI生成图片，AI生成代码，AI语音合成，AI音频生成，脑图生成，流程图生成，科学计算器，3D模型可视化，智能问答助手，多语言翻译，个性化学习路径，自适应题库，情境化案例）结合输出的项目。

## 互动项目与多模态内容的协同关系

TICMaker的核心价值在于将**互动项目**和**多模态内容**有机结合，而不是独立生成两者：

### 协同设计理念
- **互动项目**提供交互框架和教学逻辑，是"容器"
- **多模态内容**作为教学素材填充到互动项目中，是"内容"
- **两者协同**创造完整的沉浸式教学体验，是"效果"

### 集成应用示例
```
🎯 随堂测试互动项目 + AI生成题目配图 + 语音播报 = 多感官测试体验
🖼️ 虚拟画廊漫步 + AI生成3D模型 + 环境音效 = 沉浸式学习空间  
☁️ 词云生成互动 + AI生成背景图片 + 动态效果 = 视觉化概念展示
🎮 HTML互动游戏 + AI生成角色图像 + 背景音乐 = 游戏化学习体验
```

### 统一输出产物
TICMaker最终交付给老师的是：
- ✅ **集成式互动组件**：每个互动项目都已整合相应的多模态素材
- ✅ **即用型HTML包**：包含完整的代码、素材和配置文件
- ✅ **使用指南文档**：详细的集成说明和自定义指引
- ✅ **在线演示预览**：教师可直接体验最终效果

## 协同应用实例

以下实例展示了多模态内容如何与教学互动项目深度融合，创造完整的教学体验：

### 1. **脑图 + 教学互动项目的结合**

#### **脑图 + 头脑风暴互动项目**
```
📚 教学内容：生物课"生态系统"
🧠 AI生成脑图：生态系统概念图（生产者→消费者→分解者→非生物因子）
💡 集成到头脑风暴互动：
   • 学生在脑图各节点上添加具体例子
   • 实时协作完善生态系统关系图  
   • 最终生成班级共同的知识脑图
🎯 教学效果：理论框架可视化 + 学生主动构建知识
```

#### **脑图 + 随堂测试互动项目**
```
📚 教学内容：历史课"辛亥革命"
🧠 AI生成脑图：辛亥革命时间线和关键人物关系图
📝 集成到随堂测试：
   • 测试题目以"在脑图中找到..."的形式出现
   • 学生点击脑图相应节点来回答问题
   • 答题过程中脑图节点会高亮显示相关信息
🎯 教学效果：知识检测 + 视觉化学习强化
```

### 2. **科学计算器+公式 + 教学互动项目的结合**

#### **计算器+公式 + 基础模拟实验**
```
📚 教学内容：物理课"自由落体运动"
🔬 AI生成工具：
   • 自由落体公式渲染 (h = ½gt²)
   • 物理计算器（支持重力加速度计算）
⚗️ 集成到模拟实验：
   • 虚拟实验：调整物体高度，观察下落时间
   • 实时计算器显示当前参数下的理论值
   • 学生对比实验结果与公式计算结果
   • 公式动态展示参数变化对结果的影响
🎯 教学效果：理论公式 + 实验验证 + 数据分析
```

#### **计算器+公式 + 小组讨论**
```
📚 教学内容：数学课"二次函数"
📊 AI生成工具：
   • 二次函数公式组 (y=ax²+bx+c, 顶点公式, 判别式等)
   • 图形计算器（实时绘制函数图像）
👥 集成到小组讨论：
   • 各小组分配不同的a,b,c参数
   • 使用计算器工具分析函数性质
   • 小组间分享发现的规律
   • 公式工具帮助验证和解释现象
🎯 教学效果：数学建模 + 协作探究 + 规律发现
```

### 3. **流程图 + 教学互动项目的结合**

#### **流程图 + 编程与代码运行**
```
📚 教学内容：信息技术课"算法设计"  
📋 AI生成流程图：排序算法步骤图（冒泡排序）
💻 集成到编程互动：
   • 学生根据流程图编写代码
   • 代码运行时，流程图对应步骤会高亮
   • 调试时可以逐步跟踪流程图执行路径
   • 理论（流程图）与实践（代码）对照学习
🎯 教学效果：算法理解 + 编程实践 + 调试思维
```

#### **流程图 + 虚拟画廊漫步**
```
📚 教学内容：化学课"制取氧气实验"
📋 AI生成流程图：完整实验步骤流程
🏛️ 集成到虚拟画廊：
   • 3D虚拟实验室场景
   • 学生按流程图指示"漫步"到不同实验台
   • 每个步骤对应虚拟空间中的操作点
   • 流程图作为导航地图引导实验进程
🎯 教学效果：沉浸式体验 + 程序化操作 + 安全实验
```

### 4. **AI音频 + 教学互动项目的结合**

#### **AI音频 + 学生展示与互评**
```
📚 教学内容：英语课"诗歌朗诵"
🎵 AI生成音频：标准发音示范 + 背景音乐
🎭 集成到展示互评：
   • 学生录制自己的朗诵音频
   • AI示范音频作为参考标准播放
   • 同学们对比评价发音准确性
   • 背景音乐增强朗诵的感染力
🎯 教学效果：标准示范 + 同伴评议 + 艺术感染
```

#### **AI音频 + 虚拟画廊漫步**
```
📚 教学内容：历史课"古代文明"
🎵 AI生成音频：古典音乐风格的背景音 + 文明介绍旁白
🏛️ 集成到虚拟画廊：
   • 学生"漫步"在古文明虚拟博物馆中
   • 不同区域播放相应的背景音乐
   • 点击文物时播放AI生成的介绍旁白
   • 沉浸式的多感官学习体验
🎯 教学效果：情境营造 + 多感官刺激 + 文化体验
```

### 5. **多种多模态内容的组合应用**

#### **综合案例：数学课"三角函数"**
```
📚 教学内容：高中数学"三角函数"
🎁 AI生成多模态内容包：
   • 脑图：三角函数关系图
   • 科学计算器：三角函数计算器
   • 流程图：求解三角方程步骤
   • AI音频：重点概念语音解释

📋 集成到互动项目组合：

1️⃣ 课堂导入 (提问与回答 + 脑图)
   • 展示三角函数概念脑图
   • 学生回答各函数间的关系

2️⃣ 概念学习 (基础模拟实验 + 计算器)
   • 虚拟单位圆实验
   • 实时计算器显示函数值变化

3️⃣ 练习巩固 (随堂测试 + 流程图)
   • 解题步骤跟随流程图指导
   • 测试题目结合具体解题流程

4️⃣ 总结回顾 (词云生成 + AI音频)
   • 学生输入学习心得生成词云
   • AI音频播放重点知识总结

🎯 教学效果：完整学习闭环 + 多维度互动 + 个性化体验
```

## 协同价值体现

### 🚀 **教学效果增强**
- **理论与实践结合**：公式理论 + 计算器实践验证
- **多感官刺激学习**：视觉脑图 + 听觉音频 + 操作互动
- **适应学习差异**：不同类型素材满足不同学习风格

### 💡 **互动深度提升**
- **从被动到主动**：不再是简单查看，而是操作和探索  
- **从单一到综合**：多种素材类型协同支持复杂互动
- **从静态到动态**：实时计算、动态图表、交互式内容

### ⚙️ **技术实现优势**
- **一体化集成**：所有素材自动适配到互动项目中
- **智能关联匹配**：AI分析教学内容，智能匹配最优素材组合
- **开箱即用**：教师获得完整可用的互动组件，而非零散素材

结合用户（老师）输入的一段教学内容及教学目标，TICMaker会按照以下GenAI驱动的6步优化流程来整合原来的教学内容、结合多模态互动内容的教学互动项目设计后产生一个全新的教材。

## TICMaker教材生成流程

### Step 1: 知识点GenAI智能解析（3分钟）
**流程**：输入内容 → GenAI深度理解 → 知识结构分析 → 教学要素提取

**GenAI分析能力：**
- **多模态内容理解**：处理文本、图片、表格、公式中的信息
- **上下文推理**：基于大语言模型的深度语义理解，准确识别隐含的教学意图
- **知识图谱构建**：自动生成知识点之间的关联关系和依赖结构
- **教学场景适配**：理解不同学科的教学特点和认知规律

**分析维度：**
- 抽象程度（具体↔抽象）
- 逻辑复杂性（简单↔复杂）
- 应用场景（理论↔实践）
- 记忆负荷（低↔高）

### Step 2: 教学策略GenAI智能推荐（2分钟）
**流程**：GenAI策略分析 → 个性化推荐 → 互动方案生成 → 时间分配优化

**推荐逻辑：**
- **概念类知识**：概念图+词云+问答 → 理解巩固
- **程序类知识**：步骤演示+模拟操作+练习 → 技能掌握
- **事实类知识**：图像记忆+游戏化+测试 → 记忆强化
- **原理类知识**：案例分析+实验模拟+讨论 → 深度理解

**时间分配模型：**
导入(5min) + 核心学习(20min) + 互动强化(15min) + 总结评估(5min)

### Step 3: 多模态内容GenAI创作（5分钟）
**流程**：GenAI内容理解 → 多模态协同生成 → 教育适配优化 → 质量智能筛选

**生成策略优先级：**

**高优先级（必生成）：**
- 📊 知识点概念图：帮助建立知识结构
- 🎨 关键信息可视化：图表、流程图、示意图
- ❓ 3-5个核心问题：检测理解程度
- 📝 互动练习题：即时反馈和巩固

**中优先级（条件生成）：**
- 🎮 简单互动游戏：适合记忆性内容
- 🎬 解释性微视频：复杂概念的动态演示
- 🗣️ 语音讲解：重点内容的音频解释
- 📱 移动端适配：响应式界面优化

**低优先级（可选生成）：**
- 🥽 3D模型展示：空间结构相关内容
- 🤝 小组协作任务：需要深度思考的内容
- 🏆 成就徽章系统：长期激励机制

### Step 4: 教学流程GenAI智能编排（3分钟）
**流程**：GenAI流程规划 → 认知负荷分析 → 学习路径优化 → 个性化调整

**编排原则：**
- **7±2规律**：每次呈现信息不超过9个要点
- **互动频次**：每3-5分钟安排一次互动
- **难易搭配**：简单→复杂→简单的波浪式难度
- **多感官刺激**：视觉、听觉、触觉的合理搭配

**智能排序算法：**
开场激发兴趣 → 概念建立 → 理解深化 → 应用练习 → 总结强化

### Step 5: GenAI个性化适配与调整（2分钟）
**流程**：GenAI用户画像分析 → 智能适配策略 → 内容风格调优 → 交互模式选择

**适配维度：**
- **学段适配**：小学生(游戏化) → 初中生(探究式) → 高中生(问题导向) → 大学生(案例分析)
- **学科特点**：理科(逻辑推理) → 文科(情感共鸣) → 艺术(审美体验)
- **教师偏好**：传统型 → 创新型 → 技术型
- **设备条件**：基础版 → 标准版 → 高级版

### Step 6: GenAI质量检测与优化输出（5分钟）
**流程**：GenAI多维度评估 → 智能问题发现 → 自动优化迭代 → 最终版本生成

**质量检测清单：**
- ✅ 知识准确性（GenAI+人工双重验证）
- ✅ 教学目标对齐性
- ✅ 互动逻辑合理性
- ✅ 技术实现可行性
- ✅ 用户体验友好性

**输出格式：**
标准化HTML5教学页面 + 教师使用指南 + 学生操作说明

## 教学互动项目详细说明

### 1. 提问与回答
**功能描述**：师生间的实时问答互动，支持开放性问题和封闭性问题。
**应用场景**：课堂导入、知识点讲解、课堂总结
**实例**：
- 数学课：老师提问"圆的周长公式是什么？"，学生可以文字或语音回答
- 历史课：老师问"你们对秦始皇统一六国有什么看法？"，学生发表观点并互相讨论
**技术框架**：Socket.io（实时通信）、WebRTC（语音传输）、React/Vue（前端UI）

### 2. 投票与选择题
**功能描述**：快速收集学生意见和答案，实时显示统计结果。
**应用场景**：概念测试、意见征集、课堂决策
**实例**：
- 英语课：选择题"Which is correct? A) He go to school B) He goes to school"
- 物理课：投票选择"光是波还是粒子？"，引出波粒二象性讨论
**技术框架**：Kahoot API、Poll.ly SDK、Chart.js（数据可视化）、WebSocket

### 3. 简单题与词云
**功能描述**：学生提交关键词，系统生成词云图展示高频概念。
**应用场景**：概念总结、头脑风暴、知识回顾
**实例**：
- 化学课：让学生输入"化学反应"相关词汇，生成词云突出"催化剂"、"能量"等高频词
- 语文课：诗歌赏析后，学生输入感受词汇，形成情感词云
**技术框架**：WordCloud.js、D3.js、Python-wordcloud、ECharts

### 4. 随堂测试
**功能描述**：即时生成小测验，快速检验学习效果。
**应用场景**：课中检测、知识巩固、学习评估
**实例**：
- 生物课：DNA结构学习后，5道选择题测试，系统实时显示正确率
- 地理课：世界各国首都快速问答，限时回答增加趣味性
**技术框架**：Quizlet API、Google Forms API、H5P Framework、Moodle Quiz API

### 5. 小组讨论
**功能描述**：将学生分组进行主题讨论，支持在线协作和成果分享。
**应用场景**：合作学习、问题探讨、观点交流
**实例**：
- 道德与法治课：分组讨论"网络隐私保护"，各组分别从个人、企业、政府角度分析
- 科学课：小组讨论"如何减少塑料污染"，制定行动计划并展示
**技术框架**：Discord.js、Slack API、Microsoft Teams SDK、BigBlueButton

### 6. 头脑风暴
**功能描述**：快速收集学生的创意想法，无评判地展示所有观点。
**应用场景**：创新思考、问题解决、创意激发
**实例**：
- 美术课：为学校设计新的校徽，学生提交各种创意元素和设计理念
- 信息技术课：头脑风暴"未来智能家居功能"，收集天马行空的创意
**技术框架**：Miro API、Jamboard API、Padlet SDK、MindMeister API

### 7. 短周期项目模块
**功能描述**：将复杂项目分解为多个短期任务模块，便于管理和完成。
**应用场景**：项目式学习、技能培养、综合实践
**实例**：
- 语文课：制作"我的家乡"数字故事，分为素材收集、脚本编写、录制制作三个模块
- 数学课：设计学校商店经营方案，分为市场调研、成本核算、方案展示三个阶段
**技术框架**：Trello API、Asana SDK、Monday.com API、Notion API

### 8. 基础模拟实验
**功能描述**：通过简化的虚拟实验环境，让学生体验实验过程。
**应用场景**：科学探究、实验教学、安全演练
**实例**：
- 化学课：虚拟酸碱中和反应实验，调整试剂浓度观察pH变化
- 物理课：模拟单摆运动实验，改变摆长和重量观察周期变化
**技术框架**：PhET Simulations、LabXchange、ChemSketch、Three.js（自定义仿真）

### 9. 编程与代码运行
**功能描述**：提供在线编程环境，学生可以编写和运行代码。
**应用场景**：计算机课程、逻辑思维训练、问题解决
**实例**：
- 信息技术课：用Scratch制作简单动画，学习循环和条件语句
- 数学课：用Python画几何图形，理解坐标系和函数概念
**技术框架**：CodePen API、Repl.it SDK、CodeSandbox API、Jupyter Notebooks

### 10. 游戏化学习徽章
**功能描述**：设置学习成就徽章系统，激励学生持续学习。
**应用场景**：学习激励、进度追踪、能力认证
**实例**：
- 英语课：设置"词汇达人"、"语法专家"、"口语流利"等徽章
- 数学课：解题速度、正确率、创新解法分别对应不同徽章等级
**技术框架**：ClassBadges、Mozilla Open Badges、Credly API、Badgr API

### 11. 学生展示与互评
**功能描述**：学生展示学习成果，同伴之间进行评价和反馈。
**应用场景**：成果展示、同伴学习、能力培养
**实例**：
- 科学课：学生制作环保小发明视频，其他同学从创新性、实用性、表达清晰度评分
- 文学课：诗歌朗诵展示，同学们投票选出"最佳情感表达奖"
**技术框架**：Flipgrid API、Seesaw SDK、ClassDojo API、Padlet SDK

### 12. 虚拟画廊漫步
**功能描述**：创建虚拟展示空间，学生可以在线"参观"学习成果。
**应用场景**：作品展示、文化学习、艺术欣赏
**实例**：
- 历史课：创建"古代文明虚拟博物馆"，学生制作文物介绍并在虚拟空间展示
- 美术课：举办"学生数字画展"，观众可以点击作品查看创作过程和理念
**技术框架**：A-Frame（VR网站）、Mozilla Hubs、Spatial.io API、无现成技术框架（复杂虚拟空间）

## 教学多模态内容详细说明

### 1. HTML互动游戏
**功能描述**：基于Web技术创建的交互式教学游戏，支持点击、拖拽、输入等多种交互方式。
**技术特点**：跨平台兼容、实时反馈、数据追踪、可定制化
**应用场景**：知识巩固、技能训练、趣味学习
**实例**：
- 数学课：制作"数字配对"游戏，学生拖拽数字与对应的图形匹配，学习数的概念
- 英语课：开发"单词拼写冒险"，学生在虚拟场景中收集字母组成单词，通关获得奖励
**技术框架**：Phaser.js、Unity WebGL、Construct 3、GameMaker Studio

### 2. AI生成视频
**功能描述**：利用AI技术自动生成教学视频内容，包括解说、动画、字幕等元素。
**技术特点**：快速生成、个性化内容、多语言支持、自动配音
**应用场景**：概念讲解、过程演示、情景模拟
**实例**：
- 历史课：AI生成"丝绸之路贸易"动画视频，展示商队行进路线和文化交流过程
- 物理课：自动创建"光的折射实验"演示视频，可调节入射角度观察不同折射效果
**技术框架**：Runway ML、Synthesia、D-ID、无现成技术框架（定制教学视频生成）

### 3. AI生成图片
**功能描述**：根据教学内容自动生成相关的图像、插画、图表等视觉素材。
**技术特点**：高质量输出、风格可控、批量生成、版权友好
**应用场景**：概念解释、场景描述、数据可视化
**实例**：
- 生物课：生成各种细胞结构的高清示意图，标注细胞壁、细胞核、线粒体等组织
- 地理课：创建不同气候带的景观图片，直观展示热带雨林、温带草原、极地冰川
**技术框架**：Midjourney API、DALL-E 2 API、Stable Diffusion、Adobe Firefly

### 4. AI生成代码
**功能描述**：自动生成教学用的程序代码示例，支持多种编程语言和复杂度级别。
**技术特点**：语法正确、注释完整、可运行验证、难度分层
**应用场景**：编程教学、算法演示、项目开发
**实例**：
- 信息技术课：生成Python绘制几何图形代码，学生运行后可看到三角形、圆形等图案
- 数学课：创建计算器程序代码，演示四则运算逻辑和用户界面设计
**技术框架**：GitHub Copilot API、OpenAI Codex、CodeT5、Replit Ghostwriter

### 5. AI语音合成
**功能描述**：将文本内容转换为自然流畅的语音，支持多种音色、语言和情感表达。
**技术特点**：多语言支持、情感调节、语速控制、音色选择
**应用场景**：听力训练、朗读示范、多语言学习
**实例**：
- 语文课：AI朗读古诗词，可选择不同的音色和情感，帮助学生理解诗歌意境
- 英语课：生成标准发音的对话练习，学生可以跟读并获得发音评分反馈
**技术框架**：ElevenLabs、Microsoft Azure Speech、Google Cloud Text-to-Speech、Amazon Polly

### 6. 3D模型可视化
**功能描述**：创建三维立体模型，学生可以360度旋转查看，理解复杂的空间结构。
**技术特点**：立体展示、交互操作、细节放大、动画演示
**应用场景**：空间认知、结构分析、立体几何
**实例**：
- 化学课：制作分子结构3D模型，学生可以旋转观察原子间的键合关系和空间排列
- 地理课：创建地球内部结构模型，剖面展示地壳、地幔、地核的层次分布
**技术框架**：Three.js、Blender（导出网页）、A-Frame、Sketchfab API

### 7. 智能问答助手
**功能描述**：AI驱动的虚拟助教，能够回答学生问题、提供学习指导和个性化建议。
**技术特点**：自然语言理解、知识库检索、个性化回复、学习跟踪
**应用场景**：答疑解惑、学习指导、作业辅助
**实例**：
- 数学课：学生问"为什么要学三角函数？"，AI助手结合实际应用场景解释其重要性
- 科学课：当学生对实验结果困惑时，AI助手引导学生分析可能的影响因素
**技术框架**：OpenAI GPT API、Anthropic Claude API、Google Dialogflow、Microsoft Bot Framework

### 8. 多语言翻译
**功能描述**：实时翻译教学内容为不同语言，支持文本、语音、图片中的文字翻译。
**技术特点**：多语言支持、实时翻译、上下文理解、专业术语识别
**应用场景**：国际化教学、语言学习、文化交流
**实例**：
- 英语课：中英对照阅读材料，学生可以点击任意词汇查看释义和发音
- 历史课：将古代文献自动翻译成现代语言，帮助学生理解历史文献内容
**技术框架**：Google Translate API、Microsoft Translator、DeepL API、Baidu Translate API

### 9. 个性化学习路径
**功能描述**：基于学生学习数据和能力评估，动态调整学习内容和进度安排。
**技术特点**：数据驱动、自适应调整、能力评估、进度追踪
**应用场景**：因材施教、补弱提优、学习规划
**实例**：
- 数学课：根据学生在几何题目上的表现，系统推荐额外的空间想象力训练内容
- 英语课：分析学生语法错误类型，定制针对性的语法练习和讲解内容
**技术框架**：Adaptive Learning Platforms（Knewton、Smart Sparrow）、无现成技术框架（定制学习路径）

### 10. 自适应题库
**功能描述**：智能题库系统根据学生答题情况动态调整题目难度和类型。
**技术特点**：难度自适应、知识点覆盖、错误分析、智能推荐
**应用场景**：练习测试、能力评估、查缺补漏
**实例**：
- 物理课：学生在力学题目中错误率高时，系统自动推送相关基础概念题和应用题
- 化学课：根据学生对不同反应类型的掌握程度，智能匹配对应难度的化学方程式题目
**技术框架**：CAT（Computer Adaptive Testing）系统、Khan Academy API、无现成技术框架（学科适应性题库）

### 11. AI音频生成
**功能描述**：利用AI技术生成各种类型的教学音频内容，包括背景音乐、环境音效、教学旁白等。
**技术特点**：风格多样、情感表达、无版权风险、可定制化
**应用场景**：氛围营造、听力训练、多感官学习
**实例**：
- 历史课：生成古典音乐风格的背景音，营造历史氛围，配合朝代学习
- 英语课：生成不同口音的对话音频，让学生接触多元化的语音环境
**技术框架**：Suno AI、AIVA、Mubert API、udio.ai

### 12. 脑图生成
**功能描述**：智能分析教学内容，自动生成结构化的思维导图和知识脑图。
**技术特点**：层级结构、关联展示、可视化思维、交互编辑
**应用场景**：知识梳理、概念关联、复习总结
**实例**：
- 生物课：生成"细胞结构"脑图，展示各组成部分及其功能关系
- 文学课：创建"诗歌要素"思维导图，串联韵律、意象、情感等要素
**技术框架**：XMind SDK、MindMeister API、Lucidchart API、ProcessOn API

### 13. 流程图生成
**功能描述**：根据教学内容自动创建各种类型的流程图，展示过程、步骤和逻辑关系。
**技术特点**：自动布局、逻辑清晰、步骤可视、交互操作
**应用场景**：过程教学、逻辑分析、步骤指导
**实例**：
- 化学课：生成"化学实验流程图"，详细展示实验步骤和注意事项
- 数学课：创建"解题思路流程图"，引导学生掌握解题方法和逻辑
**技术框架**：Draw.io API、Lucidchart、Visio Online、Mermaid.js

### 14. 科学计算器与公式生成
**功能描述**：智能生成专业的科学计算器界面和数理化公式渲染，支持复杂数学运算、公式推导、方程求解和函数图像绘制。
**技术特点**：高精度计算、LaTeX公式渲染、图形化显示、步骤展示、公式推导
**应用场景**：数学计算、物理建模、化学反应、工程应用、公式教学
**实例**：
- 数学课：生成"二次方程求解器"，显示完整的求根公式和图像，展示判别式计算过程
- 物理课：创建"牛顿运动定律计算器"，集成F=ma等公式，自动单位转换和矢量计算
- 化学课：生成"化学方程式配平器"，自动配平反应方程并计算摩尔比例
**技术框架**：Math.js、MathJax、KaTeX、D3.js、Desmos API、GeoGebra API、ChemDoodle

### 15. 情境化案例
**功能描述**：基于真实场景创建贴近学生生活的教学案例，提高学习的相关性和趣味性。
**技术特点**：生活化场景、问题驱动、跨学科整合、实践应用
**应用场景**：案例教学、问题解决、应用实践
**实例**：
- 数学课：以"校园商店经营"为背景，学习利润计算、图表分析等数学概念
- 环境科学课：模拟"社区垃圾分类推广"项目，学习环保知识和社会实践技能
**技术框架**：无现成技术框架（定制情境化教学平台）

## 大学教学特色功能补充

### 针对大学教学的互动项目补充

#### 1. 学术讨论与辩论
**功能描述**：结构化的学术争论和深度讨论平台，支持批判性思维培养。
**应用场景**：学术争辩、观点碰撞、理论探讨
**实例**：
- 法学课：模拟法庭辩论，学生分别担任原告、被告律师，基于真实案例进行论辩
- 哲学课：苏格拉底式对话，围绕"人工智能是否具有道德责任"展开思辨讨论
**技术框架**：Kialo（辩论平台）、Discourse Forum、无现成技术框架（结构化学术辩论）

#### 2. 研究项目协作
**功能描述**：支持长期研究项目的协作管理、进度跟踪和成果展示。
**应用场景**：学术研究、团队协作、项目管理
**实例**：
- 心理学课：小组进行"社交媒体对大学生心理健康影响"的实证研究项目
- 工程课：跨专业团队设计智能校园系统，涉及硬件、软件、用户体验等领域
**技术框架**：GitHub Projects、GitLab Issues、Zenhub API、Linear API

#### 3. 案例分析工坊
**功能描述**：基于真实复杂案例的深度分析和解决方案设计平台。
**应用场景**：理论应用、多维分析、创新思维
**实例**：
- 商学院：分析Netflix的商业模式转型，从DVD租赁到流媒体巨头的战略演进
- 医学院：疑难病例会诊，学生提出诊断假设和个性化治疗方案
**技术框架**：Harvard Business School Case Studies、Ivey Cases、无现成技术框架（定制案例平台）

#### 4. 学术会议模拟
**功能描述**：模拟真实学术会议的论文发表、同行评议和学术交流过程。
**应用场景**：学术写作、同行评议、国际交流
**实例**：
- 计算机科学：学生提交AI算法研究，进行peer review和conference presentation
- 文学研究：举办"当代文学批评研讨会"，学生发表论文并接受专业质疑
**技术框架**：EasyChair（会议管理）、OpenReview（同行评议）、Zoom Webinar SDK

### 针对大学教学的多模态内容补充

#### 1. 学术论文智能解析
**功能描述**：AI辅助分析和解读复杂学术文献，提供研究脉络和知识图谱。
**技术特点**：文献挖掘、知识图谱、引用分析、趋势预测
**应用场景**：文献综述、研究前沿、学术写作
**实例**：
- 生物医学：自动提取Nature论文的关键发现，生成可视化的研究脉络图
- 社会学：分析近20年性别研究论文，展示理论演进和研究热点变化趋势
**技术框架**：Semantic Scholar API、Web of Science API、OpenAlex API、Connected Papers

#### 2. 虚拟实验室与仿真
**功能描述**：高精度的专业实验环境和复杂系统仿真，支持无限次重复实验。
**技术特点**：物理建模、数据分析、风险零成本、参数可调节
**应用场景**：科学实验、系统设计、风险分析
**实例**：
- 化学工程：虚拟化工厂反应器设计，学生调整参数观察产量和安全指标变化
- 经济学：宏观经济模型仿真，研究货币政策对通胀和就业的长期动态影响
**技术框架**：LabVIEW、MATLAB Simulink、AnyLogic、NetLogo

#### 3. 专业数据库集成
**功能描述**：整合学科专业数据库，提供实时数据分析和可视化功能。
**技术特点**：大数据处理、实时更新、可视化分析、API接口集成
**应用场景**：数据分析、实证研究、市场调研
**实例**：
- 金融学：集成Bloomberg终端数据，学生分析股票市场波动和投资组合优化
- 新闻传播：整合全球媒体数据库，研究舆情传播规律和媒体影响力测量
**技术框架**：NewsAPI、GDELT Project、Twitter API、无现成技术框架（定制媒体数据平台）

#### 4. 跨文化学习支持
**功能描述**：支持国际学生和跨文化学术交流的多元化内容生成系统。
**技术特点**：文化适应、多时区协作、国际标准、本地化定制
**应用场景**：国际合作、文化交流、全球视野培养
**实例**：
- 国际关系：多国学生合作分析地缘政治事件，AI提供不同文化视角的背景信息
- 比较文学：中外学生共同研读莎士比亚作品，AI生成跨文化注释和历史背景解析
**技术框架**：Google Translate API、Microsoft Translator、DeepL API、无现成技术框架（跨文化学习平台）
"""

try:
    from mcp.server import Server
    from mcp.server.models import InitializationOptions
    from mcp.server.stdio import stdio_server
    from mcp import types
except ImportError:
    print("Warning: MCP library not available. Please install with: pip install mcp", file=sys.stderr)
    Server = None
    stdio_server = None
    types = None
    InitializationOptions = None

# 设置日志输出到stderr以避免干扰stdio通信
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)


class AIClient:
    """统一的AI客户端，支持多个AI提供商"""
    
    def __init__(self, config: Dict[str, Any]):
        self.provider = config.get('provider', 'openai').lower()
        self.api_key = config.get('api_key')
        self.model = config.get('model', 'gpt-4o-mini')
        self.temperature = config.get('temperature', 0.7)
        self.max_tokens = config.get('max_tokens', 2000)
        self.base_url = config.get('base_url')
        
        # 初始化客户端
        if self.provider == 'openai':
            if openai is None:
                raise ImportError("OpenAI library not available. Please install: pip install openai")
            self.client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.base_url
            )
        elif self.provider == 'anthropic':
            if anthropic is None:
                raise ImportError("Anthropic library not available. Please install: pip install anthropic")
            self.client = anthropic.Anthropic(
                api_key=self.api_key,
                base_url=self.base_url
            )
        else:
            raise ValueError(f"Unsupported AI provider: {self.provider}")
    
    async def chat_completion(self, messages: List[Dict[str, str]], system_prompt: str = None) -> str:
        """统一的聊天完成接口"""
        try:
            if self.provider == 'openai':
                # OpenAI API 调用
                chat_messages = []
                if system_prompt:
                    chat_messages.append({"role": "system", "content": system_prompt})
                chat_messages.extend(messages)
                
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=chat_messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens
                )
                return response.choices[0].message.content
                
            elif self.provider == 'anthropic':
                # Anthropic API 调用
                user_message = "\n\n".join([msg["content"] for msg in messages if msg["role"] == "user"])
                
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=system_prompt or "",
                    messages=[{"role": "user", "content": user_message}]
                )
                return response.content[0].text
                
        except Exception as e:
            logger.error(f"AI API call failed: {e}")
            raise
    
    def is_available(self) -> bool:
        """检查AI客户端是否可用"""
        return self.api_key is not None and (
            (self.provider == 'openai' and openai is not None) or
            (self.provider == 'anthropic' and anthropic is not None)
        )


class TICMakerIntentDetector:
    """TICMaker意图检测器"""
    
    INTENT_DETECTION_PROMPT = """
你是TICMaker的智能助手，专门检测用户对话是否涉及创作或修改互动教学课程的意图。

TICMaker是专门用于创建教育内容的工具。请仔细分析用户的输入，判断是否符合以下任一情况：
1. 明确要求创建教学内容、课程、页面或互动活动
2. 描述了教学场景、学习目标或教学需求  
3. 提到了特定的学科内容、知识点需要制作成互动形式
4. 要求修改或优化现有的教学内容
5. 询问如何设计教学活动或课程
6. 包含任何学科领域的专业概念或知识点

请直接回答 "YES" 或 "NO"，然后在新行简要说明判断理由（不超过50字）。

正面示例（应该回答YES）：
用户输入："帮我创建一个数学课的互动游戏"
回答：YES
用户明确要求创建数学学科的互动教学游戏

用户输入："制作关于化学反应的教学内容"
回答：YES
用户要求制作化学学科的教学内容

用户输入："创建一个机器人三大定律的互动课程"
回答：YES
用户要求创建关于机器人学/人工智能的教学课程

用户输入："设计一个关于DNA结构的学习页面"
回答：YES
用户要求设计生物学科的教学内容

用户输入："如何制作英语单词记忆训练"
回答：YES
用户询问制作英语教学活动的方法

负面示例（应该回答NO）：
用户输入："今天天气怎么样？"
回答：NO
这是关于天气的一般询问，与教学内容创作无关

用户输入："你好，请自我介绍"
回答：NO
这是一般性问候和询问，不涉及教学内容

用户输入："帮我写一份工作报告"
回答：NO
这是工作文档写作需求，不是教学内容创作
"""
    
    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client
    
    async def detect_intent(self, user_message: str) -> tuple[bool, str]:
        """检测用户意图
        
        Returns:
            tuple[bool, str]: (是否为创作意图, 判断理由)
        """
        try:
            messages = [{
                "role": "user",
                "content": f"用户输入：\"{user_message}\""
            }]
            
            response = await self.ai_client.chat_completion(
                messages=messages,
                system_prompt=self.INTENT_DETECTION_PROMPT
            )
            
            lines = response.strip().split('\n', 1)
            is_intent = lines[0].strip().upper() == 'YES'
            reason = lines[1].strip() if len(lines) > 1 else "未提供理由"
            
            logger.info(f"意图检测结果: {is_intent}, 理由: {reason}")
            return is_intent, reason
            
        except Exception as e:
            logger.error(f"意图检测失败: {e}")
            # 默认认为是创作意图，避免阻断用户请求
            return True, "意图检测服务不可用，默认处理"


class TICMakerContentGenerator:
    """TICMaker内容生成器"""
    
    def __init__(self, ai_client: AIClient):
        self.ai_client = ai_client
    
    async def analyze_requirements(self, user_message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """分析用户需求并生成方案"""
        
        analysis_prompt = f"""
基于用户的教学需求，请分析并推荐最佳的互动课程方案。

用户需求：{user_message}
上下文信息：{json.dumps(context, ensure_ascii=False, indent=2)}

请以JSON格式返回分析结果，包含以下字段：
{{
    "subject": "学科领域",
    "topic": "具体主题",
    "learning_objectives": ["学习目标1", "学习目标2"],
    "target_audience": "目标受众（如：小学生、初中生等）",
    "recommended_template": "推荐模板类型（basic/interactive/educational）",
    "recommended_style": "推荐样式（modern/classic/colorful）",
    "interactive_elements": ["互动元素1", "互动元素2"],
    "content_suggestions": "具体内容建议",
    "course_title": "推荐的课程标题"
}}

请确保返回有效的JSON格式。
"""
        
        try:
            messages = [{"role": "user", "content": analysis_prompt}]
            response = await self.ai_client.chat_completion(
                messages=messages,
                system_prompt=TICMAKER_PROMPT
            )
            
            # 解析JSON响应 - 提取可能的JSON内容
            try:
                # 尝试直接解析
                analysis = json.loads(response.strip())
            except json.JSONDecodeError:
                # 如果直接解析失败，尝试从响应中提取JSON
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    try:
                        analysis = json.loads(json_match.group(0))
                    except json.JSONDecodeError:
                        raise ValueError("无法从AI响应中提取有效JSON")
                else:
                    raise ValueError("AI响应中未找到JSON内容")
            
            logger.info(f"需求分析完成: {analysis.get('topic', '未知')} - {analysis.get('recommended_template', 'basic')}模板")
            return analysis
            
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"AI响应解析失败: {e}")
            logger.debug(f"原始AI响应: {response[:500]}...")
            # 返回默认分析结果
            return {
                "subject": "通用",
                "topic": "互动学习",
                "learning_objectives": ["提升学习兴趣", "加强知识理解"],
                "target_audience": "学生",
                "recommended_template": "basic",
                "recommended_style": "modern",
                "interactive_elements": ["问答互动", "点击交互"],
                "content_suggestions": user_message,
                "course_title": "互动学习课程"
            }
        except Exception as e:
            logger.error(f"需求分析失败: {e}")
            raise


class TICMakerMCPServer:
    """
    TICMaker专用MCP服务器 - 处理互动教学HTML页面创建和修改
    
    功能特性：
    - 智能模板选择（基础、互动、教育类型）
    - 多种样式风格支持
    - 安全的文件路径管理
    - 详细的操作日志记录
    """
    
    def __init__(self):
        if Server is None:
            raise ImportError("MCP library not available")
            
        self.server = Server("ticmaker-server")
        self.output_dir = Path("./ticmaker_output")
        self.output_dir.mkdir(exist_ok=True)
        
        # 加载配置和初始化AI客户端
        self._load_config()
        self._setup_ai_components()
        self._setup_tools()
    
    def _load_config(self):
        """从.simacode/config.yaml加载配置"""
        config_path = Path(".simacode/config.yaml")
        self.config = {}
        
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    self.config = yaml.safe_load(f)
                logger.info(f"配置加载成功: {config_path}")
            except Exception as e:
                logger.warning(f"配置加载失败: {e}, 使用默认配置")
        else:
            logger.warning(f"配置文件不存在: {config_path}, 使用默认配置")
    
    def _setup_ai_components(self):
        """设置AI组件"""
        ai_config = self.config.get('ai', {})
        
        try:
            # 初始化AI客户端
            self.ai_client = AIClient(ai_config)
            
            if self.ai_client.is_available():
                # 初始化意图检测器和内容生成器
                self.intent_detector = TICMakerIntentDetector(self.ai_client)
                self.content_generator = TICMakerContentGenerator(self.ai_client)
                logger.info(f"AI组件初始化成功: {self.ai_client.provider} - {self.ai_client.model}")
                self.ai_enabled = True
            else:
                logger.warning("AI客户端配置不完整，将使用传统模式")
                self.ai_enabled = False
                
        except Exception as e:
            logger.error(f"AI组件初始化失败: {e}")
            logger.warning("将使用传统模式运行")
            self.ai_enabled = False
    
    def _setup_tools(self):
        @self.server.list_tools()
        async def list_tools(params: Optional[types.PaginatedRequestParams] = None) -> List[types.Tool]:
            return [
                types.Tool(
                    name="create_interactive_course",
                    description="创建或修改互动教学课程",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "message": {
                                "type": "string", 
                                "description": "用户需求描述"
                            },
                            "context": {
                                "type": "object", 
                                "description": "请求上下文信息",
                                "properties": {
                                    "scope": {"type": "string", "description": "作用域，通常为'ticmaker'"},
                                    "courseTitle": {"type": "string", "description": "课程标题"},
                                    "file_path": {"type": "string", "description": "可选的文件路径"},
                                    "template": {"type": "string", "description": "模板类型: basic, interactive, educational", "enum": ["basic", "interactive", "educational"]},
                                    "style": {"type": "string", "description": "样式风格: modern, classic, colorful", "enum": ["modern", "classic", "colorful"]}
                                }
                            },
                            "session_id": {"type": "string", "description": "会话标识符"},
                            "source": {"type": "string", "description": "请求来源: CLI, API, ReAct"},
                            "operation": {
                                "type": "string", 
                                "description": "操作类型: create（创建新页面）或modify（修改现有页面）",
                                "enum": ["create", "modify"]
                            }
                        },
                        "required": ["message"]
                    }
                )
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[types.TextContent]:
            if name == "create_interactive_course":
                return await self._create_interactive_course(arguments)
            else:
                raise ValueError(f"Unknown tool: {name}")
    
    async def _create_interactive_course(self, args: Dict[str, Any]) -> List[types.TextContent]:
        """创建或修改互动教学课程"""
        message = args.get("message", "")
        context = args.get("context", {})
        session_id = args.get("session_id", "unknown")
        source = args.get("source", "unknown")
        operation = args.get("operation", "create")
        
        # 详细的请求日志记录
        logger.info("=" * 80)
        logger.info("🎯 TICMaker - 互动教学课程创建请求")
        logger.info(f"📋 操作类型: {operation}")
        logger.info(f"🌐 请求来源: {source}")
        logger.info(f"🔗 会话ID: {session_id}")
        logger.info(f"💬 用户需求: {message}")
        logger.info(f"📄 课程标题: {context.get('courseTitle', '未指定')}")
        logger.info(f"🎨 模板类型: {context.get('template', '智能选择')}")
        logger.info(f"✨ 样式风格: {context.get('style', 'modern')}")
        logger.info("=" * 80)
        
        # 确定文件路径
        file_path = context.get("file_path")
        if not file_path:
            # 生成默认文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"ticmaker_page_{timestamp}_{session_id[:8]}.html"
            file_path = self.output_dir / filename
        else:
            file_path = Path(file_path)
            # 确保文件在安全目录内
            if not str(file_path).startswith(str(self.output_dir)):
                file_path = self.output_dir / Path(file_path).name
        
        try:
            # AI意图检测（如果启用）
            if self.ai_enabled:
                is_creation_intent, reason = await self.intent_detector.detect_intent(message)
                logger.info(f"🤖 AI意图检测: {is_creation_intent}, 原因: {reason}")
                
                if not is_creation_intent:
                    return [
                        types.TextContent(
                            type="text",
                            text=f"❌ 检测到非课程创作请求\n"
                                 f"原因: {reason}\n\n"
                                 f"TICMaker专门用于创建和修改互动教学课程。\n"
                                 f"请描述您想要创建的教学内容、课程或互动活动。"
                        )
                    ]
            
            # 检查是否为修改操作
            if operation == "modify" and file_path.exists():
                # 读取现有内容
                existing_content = file_path.read_text(encoding='utf-8')
                html_content = await self._modify_html_content(existing_content, message, context)
            else:
                # 创建新页面 - 使用AI增强生成
                html_content = await self._generate_html_content_ai_enhanced(message, context)
            
            # 写入文件
            file_path.write_text(html_content, encoding='utf-8')
            
            # 记录成功
            result_msg = f"✅ 互动课程已{'修改' if operation == 'modify' else '创建'}成功"
            logger.info(f"\n{result_msg}")
            logger.info(f"文件路径: {file_path}")
            logger.info(f"文件大小: {file_path.stat().st_size} bytes")
            
            return [
                types.TextContent(
                    type="text",
                    text=f"{result_msg}\n"
                         f"文件路径: {file_path}\n"
                         f"文件大小: {file_path.stat().st_size} bytes\n"
                         f"用户需求: {message}\n"
                         f"处理来源: {source}模式"
                )
            ]
            
        except Exception as e:
            error_msg = f"❌ 互动课程创建失败: {str(e)}"
            logger.error(f"\n{error_msg}")
            logger.error(f"Interactive course creation error: {e}")
            
            return [
                types.TextContent(
                    type="text",
                    text=error_msg
                )
            ]
    
    async def _generate_html_content_ai_enhanced(self, message: str, context: Dict[str, Any]) -> str:
        """使用AI增强的方式生成互动课程内容"""
        if self.ai_enabled:
            try:
                # 使用AI分析用户需求
                logger.info("🤖 正在使用AI分析用户需求...")
                analysis = await self.content_generator.analyze_requirements(message, context)
                
                # 合并AI分析结果到context
                enhanced_context = context.copy()
                enhanced_context.update({
                    "courseTitle": analysis.get("course_title", context.get("courseTitle", "")),
                    "template": context.get("template") or analysis.get("recommended_template", "basic"),
                    "style": context.get("style") or analysis.get("recommended_style", "modern"),
                    "ai_analysis": analysis
                })
                
                logger.info(f"🎯 AI推荐方案: {analysis['recommended_template']}模板 + {analysis['recommended_style']}风格")
                
                # 使用AI增强的context生成内容
                return await self._generate_html_content(message, enhanced_context)
                
            except Exception as e:
                logger.error(f"AI增强生成失败，回退到传统模式: {e}")
                return await self._generate_html_content(message, context)
        else:
            # AI未启用，使用传统方式
            return await self._generate_html_content(message, context)
    
    async def _generate_html_content(self, message: str, context: Dict[str, Any]) -> str:
        """根据用户需求生成互动课程内容"""
        # 优先使用AI分析结果，否则使用传统提取方法
        ai_analysis = context.get("ai_analysis", {})
        title = ai_analysis.get("course_title") or self._extract_title_from_message(message)
        style = context.get("style", "modern")
        template = context.get("template", "basic")
        course_title = context.get("courseTitle", "")
        
        # 根据模板类型生成相应的HTML内容
        if template == "interactive":
            html_content = self._generate_interactive_template(title, message, style, course_title, ai_analysis)
        elif template == "educational":
            html_content = self._generate_educational_template(title, message, style, course_title, ai_analysis)
        else:
            # 默认使用基础模板，但根据消息内容智能选择
            if any(keyword in message.lower() for keyword in ["互动", "游戏", "点击", "按钮"]):
                html_content = self._generate_interactive_template(title, message, style, course_title, ai_analysis)
            elif any(keyword in message.lower() for keyword in ["学习", "教学", "课程", "练习"]):
                html_content = self._generate_educational_template(title, message, style, course_title, ai_analysis)
            else:
                html_content = self._generate_basic_template(title, message, style, course_title, ai_analysis)
        
        return html_content
    
    async def _modify_html_content(self, existing_content: str, message: str, context: Dict[str, Any]) -> str:
        """修改现有课程内容"""
        # 简单的修改逻辑 - 在实际应用中可以更复杂
        modification_note = f"\n<!-- 修改记录: {datetime.now().isoformat()} - {message} -->\n"
        
        # 在</body>前插入修改内容
        if "</body>" in existing_content:
            insert_content = f'<div class="modification-note" style="margin-top: 20px; padding: 10px; background-color: #f0f8ff; border: 1px solid #ccc;">\n<strong>最新修改:</strong> {message}\n<small>修改时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</small>\n</div>\n'
            existing_content = existing_content.replace("</body>", f"{insert_content}</body>")
        
        # 添加修改注释
        existing_content += modification_note
        
        return existing_content
    
    def _extract_title_from_message(self, message: str) -> str:
        """从用户消息中提取标题"""
        # 智能标题提取逻辑
        message_lower = message.lower()
        
        # 检测特定类型内容
        if any(keyword in message_lower for keyword in ["游戏", "小游戏", "互动游戏"]):
            return "互动教学游戏"
        elif any(keyword in message_lower for keyword in ["活动", "练习", "训练"]):
            return "教学活动页面"
        elif any(keyword in message_lower for keyword in ["课程", "课堂", "教学"]):
            return "课程内容页面"
        elif any(keyword in message_lower for keyword in ["测验", "考试", "测试"]):
            return "在线测验页面"
        elif any(keyword in message_lower for keyword in ["演示", "展示", "介绍"]):
            return "内容展示页面"
        
        # 默认标题
        return "TICMaker互动页面"
    
    def _generate_ai_analysis_section(self, ai_analysis: Dict[str, Any]) -> str:
        """生成AI分析结果的HTML展示部分"""
        if not ai_analysis:
            return ""
        
        analysis_html = '<div class="ai-analysis" style="background: #e8f5e8; padding: 15px; margin: 15px 0; border-radius: 8px; border-left: 4px solid #4caf50;">'
        analysis_html += '<h3 style="color: #2e7d32; margin-top: 0;">🤖 AI智能分析</h3>'
        
        if ai_analysis.get("subject"):
            analysis_html += f'<p><strong>学科领域:</strong> {ai_analysis["subject"]}</p>'
        
        if ai_analysis.get("topic"):
            analysis_html += f'<p><strong>教学主题:</strong> {ai_analysis["topic"]}</p>'
        
        if ai_analysis.get("target_audience"):
            analysis_html += f'<p><strong>目标受众:</strong> {ai_analysis["target_audience"]}</p>'
        
        if ai_analysis.get("learning_objectives"):
            analysis_html += '<p><strong>学习目标:</strong></p><ul>'
            for obj in ai_analysis["learning_objectives"]:
                analysis_html += f'<li>{obj}</li>'
            analysis_html += '</ul>'
        
        if ai_analysis.get("interactive_elements"):
            analysis_html += '<p><strong>推荐互动元素:</strong></p><ul>'
            for element in ai_analysis["interactive_elements"]:
                analysis_html += f'<li>{element}</li>'
            analysis_html += '</ul>'
        
        if ai_analysis.get("content_suggestions"):
            analysis_html += f'<p><strong>内容建议:</strong> {ai_analysis["content_suggestions"]}</p>'
        
        analysis_html += '</div>'
        return analysis_html
    
    def _generate_basic_template(self, title: str, message: str, style: str, course_title: str = "", ai_analysis: Dict[str, Any] = None) -> str:
        """生成基础HTML模板"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
        }}
        .container {{
            max-width: 800px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
        }}
        h1 {{
            color: #4a5568;
            text-align: center;
            border-bottom: 3px solid #667eea;
            padding-bottom: 10px;
        }}
        .content {{
            margin-top: 20px;
            padding: 20px;
            background: #f7fafc;
            border-radius: 8px;
        }}
        .timestamp {{
            text-align: center;
            color: #666;
            font-size: 0.9em;
            margin-top: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        <div class="content">
            {f'<p><strong>课程:</strong> {course_title}</p>' if course_title else ''}
            <p><strong>用户需求:</strong> {message}</p>
            {self._generate_ai_analysis_section(ai_analysis) if ai_analysis else ''}
            <p>这是由TICMaker生成的互动教学课程，专为现代化课堂教学设计。</p>
        </div>
        <div class="timestamp">
            生成时间: {datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")}
        </div>
    </div>
</body>
</html>"""
    
    def _generate_interactive_template(self, title: str, message: str, style: str, course_title: str = "", ai_analysis: Dict[str, Any] = None) -> str:
        """生成互动HTML模板"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: 'Arial', sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(45deg, #ff6b6b, #4ecdc4);
            min-height: 100vh;
        }}
        .game-container {{
            max-width: 900px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            padding: 30px;
            box-shadow: 0 15px 35px rgba(0,0,0,0.1);
        }}
        h1 {{
            text-align: center;
            color: #2c3e50;
            font-size: 2.5em;
            margin-bottom: 30px;
        }}
        .interactive-button {{
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
            border: none;
            padding: 15px 30px;
            font-size: 1.1em;
            border-radius: 25px;
            cursor: pointer;
            margin: 10px;
            transition: transform 0.2s;
        }}
        .interactive-button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }}
        .result-area {{
            margin-top: 20px;
            padding: 20px;
            background: #ecf0f1;
            border-radius: 10px;
            min-height: 100px;
        }}
    </style>
</head>
<body>
    <div class="game-container">
        <h1>{title}</h1>
        {f'<h2>📚 课程: {course_title}</h2>' if course_title else ''}
        <p><strong>用户需求:</strong> {message}</p>
        {self._generate_ai_analysis_section(ai_analysis) if ai_analysis else ''}
        
        <div class="interaction-area">
            <button class="interactive-button" onclick="showMessage('太棒了！你正在体验TICMaker创建的互动内容！')">点击互动</button>
            <button class="interactive-button" onclick="changeColor()">改变颜色</button>
            <button class="interactive-button" onclick="addContent()">添加内容</button>
        </div>
        
        <div id="result" class="result-area">
            点击上面的按钮开始互动体验！
        </div>
        
        <div class="timestamp">
            创建时间: {datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")}
        </div>
    </div>
    
    <script>
        function showMessage(msg) {{
            document.getElementById('result').innerHTML = '<h3>' + msg + '</h3>';
        }}
        
        function changeColor() {{
            const colors = ['#ff6b6b', '#4ecdc4', '#45b7d1', '#f9ca24', '#f0932b'];
            const randomColor = colors[Math.floor(Math.random() * colors.length)];
            document.querySelector('.game-container').style.background = randomColor;
            document.getElementById('result').innerHTML = '<h3>背景颜色已改变为: ' + randomColor + '</h3>';
        }}
        
        function addContent() {{
            const content = document.getElementById('result');
            content.innerHTML += '<p>新添加的互动内容 - ' + new Date().toLocaleTimeString() + '</p>';
        }}
    </script>
</body>
</html>"""
    
    def _generate_educational_template(self, title: str, message: str, style: str, course_title: str = "", ai_analysis: Dict[str, Any] = None) -> str:
        """生成教育类HTML模板"""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: 'Microsoft YaHei', sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #74b9ff 0%, #0984e3 100%);
            color: #2d3436;
        }}
        .edu-container {{
            max-width: 1000px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            overflow: hidden;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
        }}
        .header {{
            background: linear-gradient(135deg, #fdcb6e, #e17055);
            padding: 30px;
            text-align: center;
            color: white;
        }}
        .content-area {{
            padding: 40px;
        }}
        .lesson-section {{
            margin-bottom: 30px;
            padding: 20px;
            border-left: 5px solid #74b9ff;
            background: #f8f9fa;
            border-radius: 0 10px 10px 0;
        }}
        .quiz-button {{
            background: #00b894;
            color: white;
            border: none;
            padding: 12px 25px;
            border-radius: 20px;
            cursor: pointer;
            font-size: 1em;
            margin: 10px 5px;
        }}
        .quiz-button:hover {{
            background: #00a085;
            transform: translateY(-1px);
        }}
    </style>
</head>
<body>
    <div class="edu-container">
        <div class="header">
            <h1>{title}</h1>
            {f'<h2>{course_title}</h2>' if course_title else ''}
            <p>互动教学内容平台</p>
        </div>
        
        <div class="content-area">
            <div class="lesson-section">
                <h2>📚 学习目标</h2>
                <p><strong>用户需求:</strong> {message}</p>
                {self._generate_ai_analysis_section(ai_analysis) if ai_analysis else ''}
                <p>本课程旨在通过互动方式提升学习体验和效果。</p>
            </div>
            
            <div class="lesson-section">
                <h2>🎯 互动练习</h2>
                <p>点击下面的按钮进行互动学习：</p>
                <button class="quiz-button" onclick="startQuiz()">开始测验</button>
                <button class="quiz-button" onclick="showTip()">学习提示</button>
                <button class="quiz-button" onclick="showProgress()">学习进度</button>
            </div>
            
            <div id="interactive-area" class="lesson-section">
                <h2>💡 互动区域</h2>
                <p>点击上方按钮开始互动学习...</p>
            </div>
            
            <div class="lesson-section">
                <small>创建时间: {datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")}</small>
            </div>
        </div>
    </div>
    
    <script>
        function startQuiz() {{
            document.getElementById('interactive-area').innerHTML = 
                '<h2>📝 快速测验</h2>' +
                '<p>1. TICMaker是什么？</p>' +
                '<button class="quiz-button" onclick="showAnswer()">互动教学工具</button>' +
                '<button class="quiz-button" onclick="showAnswer()">普通软件</button>';
        }}
        
        function showTip() {{
            document.getElementById('interactive-area').innerHTML = 
                '<h2>💡 学习提示</h2>' +
                '<p>• 互动学习比被动接受更有效</p>' +
                '<p>• 及时反馈有助于知识巩固</p>' +
                '<p>• 多感官参与提升记忆效果</p>';
        }}
        
        function showProgress() {{
            document.getElementById('interactive-area').innerHTML = 
                '<h2>📊 学习进度</h2>' +
                '<div style="background: #ddd; border-radius: 10px; padding: 3px;">' +
                '<div style="background: #00b894; height: 20px; width: 75%; border-radius: 8px; text-align: center; line-height: 20px; color: white;">75% 完成</div>' +
                '</div>';
        }}
        
        function showAnswer() {{
            document.getElementById('interactive-area').innerHTML = 
                '<h2>✅ 正确答案</h2>' +
                '<p>TICMaker是专门用于创建互动教学内容的AI工具！</p>';
        }}
    </script>
</body>
</html>"""
    

    async def run(self):
        """运行MCP服务器使用stdio传输"""
        logger.info("🚀 启动TICMaker MCP服务器 (stdio)")
        logger.info(f"📁 输出目录: {self.output_dir}")
        
        # 使用stdio服务器
        async with stdio_server() as (read_stream, write_stream):
            init_options = InitializationOptions(
                server_name="ticmaker-server",
                server_version="1.0.0",
                capabilities=types.ServerCapabilities(
                    tools=types.ToolsCapability(),
                    logging={}
                )
            )
            
            await self.server.run(
                read_stream, 
                write_stream, 
                init_options
            )


def main():
    """主入口点"""
    try:
        server_instance = TICMakerMCPServer()
        logger.info("Starting TICMaker MCP server")
        
        asyncio.run(server_instance.run())
        
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
