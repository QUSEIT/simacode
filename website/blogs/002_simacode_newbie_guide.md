# SimaCode 新手上路指南：从零开始，10分钟搞定AI编程助手

大家好！我是River。看到不少朋友对思码（SimaCode）很感兴趣，但不知道怎么开始？今天就来写一份超简单的新手指南，专门为编程新手准备，保证看完就能上手！

前几天有个编程新手朋友问我："River，你这个思码看起来很酷，但我刚学Python不久，能不能教我最简单的安装方法？"

我想了想，确实需要一个零门槛的入门教程。让我们用最简单的方式开始！

## 准备工作：检查你的Python

### 第一步：确认Python版本
```bash
# 检查Python版本（需要3.10或更高）
python --version
# 如果上面不行，试试这个
python3 --version
```

如果显示类似 `Python 3.10.x` 或更高版本，就可以继续了！

如果版本太低或没有Python，去 [python.org](https://python.org) 下载安装最新版本。

## 第一步：最简单的安装方法

对于新手来说，直接用pip安装是最简单的方式：

```bash
# 从GitHub直接安装最新版本
pip install git+https://github.com/QUSEIT/simacode.git

# 或者如果有发布到PyPI的版本（更简单）
# pip install simacode
```

安装完成后验证一下：
```bash
# 检查是否安装成功
simacode --version

# 看看帮助信息
simacode --help
```

如果看到版本信息和帮助信息，恭喜！安装成功了！

## 第二步：初始化项目配置

在你想要使用SimaCode的目录下：

```bash
# 初始化SimaCode项目（这会创建配置文件和目录结构）
simacode init
```

这个命令会自动创建：
- `.simacode/` 目录
- `.simacode/config.yaml` 配置文件
- `.simacode/logs/` 日志目录
- `.simacode/sessions/` 会话目录

## 第三步：配置AI服务——关键步骤

### 获取AI API密钥

**推荐：使用PGPT Cloud服务（对新手更友好）**

1. 访问 https://user.pgpt.cloud
2. 注册并登录账户
3. 在控制台中点击"新建AI集成"
4. 选择你需要的AI模型（如GPT-4）
5. 复制获得的API密钥

### 编辑配置文件

现在编辑刚刚创建的配置文件：

```bash
# 编辑配置文件（用你喜欢的编辑器）
nano .simacode/config.yaml
# 或者
vim .simacode/config.yaml
# 或者用记事本等图形界面编辑器打开
```

将配置文件内容修改为：

```yaml
# SimaCode配置文件

# 项目名称
project_name: "我的第一个AI编程项目"

# AI服务配置（最重要的部分）
ai:
  provider: "openai"                    # AI服务商
  model: "gpt-4o-mini"                  # 模型选择
  api_key: "把你的API密钥粘贴在这里"    # 替换成真实密钥
  base_url: "https://openai.pgpt.cloud/v1" # PGPT Cloud服务地址
  temperature: 0.1                      # 创造性参数(0-1)
  max_tokens: 2000                      # 最大回复长度
  timeout: 30                           # 超时时间

# 安全设置
security:
  allowed_paths:
    - "./"          # 当前目录
    - "./src"       # 源码目录
    - "./projects"  # 项目目录

# 日志设置
logging:
  level: "INFO"
  file_path: ".simacode/logs/simacode.log"
```

### 用环境变量（更安全）

如果你担心把密钥写在文件里不安全，可以用环境变量：

```bash
# Windows用户在命令行中：
set OPENAI_API_KEY=你的密钥
set OPENAI_BASE_URL=https://api.pgpt.cloud/v1

# Mac/Linux用户：
export OPENAI_API_KEY="你的密钥"
export OPENAI_BASE_URL="https://api.pgpt.cloud/v1"
```

## 第四步：测试配置

```bash
# 测试配置是否正确
simacode config --check

# 简单测试AI连接
simacode chat "你好，请回复Hello World"
```

如果看到AI的回复，说明一切就绪！

## 第五步：你的第一个程序——HelloWorld

现在开始最激动人心的部分：让AI帮你写程序！

### 方法一：命令行使用

```bash
# 让SimaCode告诉我该如何创建HelloWorld程序
simacode chat "帮我创建一个Python的HelloWorld程序，保存为hello.py文件"


# 让SimaCode直接帮我创建一个HelloWorld程序
simacode chat --react "帮我创建一个Python的HelloWorld程序，保存为hello.py文件"
```

### 方法二：在Python代码中使用SimaCode

这是重点！你可以在Python代码中直接导入和使用simacode：

创建一个文件 `use_ai_helper.py`：

```python
# 导入simacode模块
import simacode

# 方式1：最简单的对话方式
def create_hello_world():
    """让AI告诉我该如何创建HelloWorld程序"""
    response = simacode.chat("创建一个Python HelloWorld程序，保存为hello.py文件")
    print("AI回复：", response)

# 方式2：使用ReAct模式（智能规划执行）
def create_and_run_program():
    """创建程序并运行"""
    response = simacode.react("创建一个Python HelloWorld程序，保存为hello.py，然后运行它显示结果")
    print("AI完成的任务：", response)

# 方式3：更复杂的需求
def create_calculator():
    """让AI创建计算器程序"""
    task = """
    创建一个简单的Python计算器程序：
    1. 支持加减乘除
    2. 有错误处理
    3. 用户友好的界面
    4. 保存为calculator.py
    5. 创建完后运行测试
    """
    response = simacode.react(task)
    print("计算器创建完成：", response)

# 运行示例
if __name__ == "__main__":
    print("=== 创建HelloWorld程序 ===")
    create_hello_world()

    print("\n=== 创建并运行程序 ===")
    create_and_run_program()

    print("\n=== 创建计算器程序 ===")
    create_calculator()
```

运行这个程序：
```bash
python use_ai_helper.py
```

### 方法三：交互式使用

你还可以在Python代码中实现交互式AI助手：

```python
import simacode

def my_ai_assistant():
    """创建你自己的AI编程助手"""

    print("🤖 你好！我是你的AI编程助手。告诉我你想创建什么程序？")

    while True:
        user_input = input("\n你想要什么？(输入'quit'退出): ")

        if user_input.lower() in ['quit', 'exit', '退出']:
            print("再见！")
            break

        try:
            # 使用simacode处理用户需求
            response = simacode.react(user_input)
            print(f"\n🤖 AI助手完成了任务：\n{response}")

        except Exception as e:
            print(f"❌ 出现错误：{e}")

if __name__ == "__main__":
    my_ai_assistant()
```

运行后你可以这样使用：
```
🤖 你好！我是你的AI编程助手。告诉我你想创建什么程序？

你想要什么？(输入'quit'退出): 创建一个猜数字游戏
🤖 AI助手完成了任务：
已创建guess_game.py文件，包含1-100猜数字游戏...

你想要什么？(输入'quit'退出): 给刚才的游戏加上计分功能
🤖 AI助手完成了任务：
已更新guess_game.py，添加了计分系统...
```

## 第六步：更多实用的Python集成示例

### 示例1：自动代码生成器

```python
import simacode

class CodeGenerator:
    """代码生成器类"""

    def __init__(self):
        self.generated_files = []

    def create_web_scraper(self, url, output_file):
        """创建网页抓取器"""
        task = f"""
        创建一个Python网页抓取器：
        1. 抓取网址：{url}
        2. 提取主要文本内容
        3. 保存结果到：{output_file}
        4. 包含错误处理
        5. 使用requests和BeautifulSoup库
        """
        result = simacode.react(task)
        self.generated_files.append(output_file)
        return result

    def create_data_analyzer(self, data_file):
        """创建数据分析器"""
        task = f"""
        创建一个数据分析程序：
        1. 读取文件：{data_file}
        2. 进行基本统计分析
        3. 生成图表
        4. 保存结果为analyze_data.py
        """
        result = simacode.react(task)
        self.generated_files.append("analyze_data.py")
        return result

    def list_generated_files(self):
        """列出已生成的文件"""
        return self.generated_files

# 使用示例
generator = CodeGenerator()

# 创建网页抓取器
print("创建网页抓取器...")
result1 = generator.create_web_scraper("https://example.com", "scraped_data.txt")

# 创建数据分析器
print("创建数据分析器...")
result2 = generator.create_data_analyzer("data.csv")

# 查看生成的文件
print("已生成的文件：", generator.list_generated_files())
```

### 示例2：智能项目初始化器

```python
import simacode
import os

def init_python_project(project_name, project_type="basic"):
    """智能初始化Python项目"""

    # 创建项目目录
    os.makedirs(project_name, exist_ok=True)
    os.chdir(project_name)

    # 在新项目目录中初始化SimaCode
    os.system("simacode init")

    if project_type == "basic":
        task = f"""
        为项目'{project_name}'创建基本Python项目结构：
        1. 创建main.py作为主程序
        2. 创建requirements.txt文件
        3. 创建README.md说明文档
        4. 创建.gitignore文件
        5. 创建tests/目录和基本测试文件
        """

    elif project_type == "web":
        task = f"""
        为项目'{project_name}'创建Flask Web项目：
        1. 创建app.py作为Flask应用
        2. 创建templates/目录和基本HTML模板
        3. 创建static/目录用于CSS/JS
        4. 创建requirements.txt（包含Flask）
        5. 创建README.md和使用说明
        """

    elif project_type == "data":
        task = f"""
        为项目'{project_name}'创建数据科学项目：
        1. 创建data_analysis.py主程序
        2. 创建data/目录存放数据文件
        3. 创建notebooks/目录存放Jupyter笔记本
        4. 创建requirements.txt（包含pandas, numpy, matplotlib）
        5. 创建README.md说明数据分析流程
        """

    # 让AI创建项目结构
    result = simacode.react(task)

    print(f"✅ 项目 '{project_name}' 创建完成！")
    print("📁 项目结构：")
    os.system("find . -type f -name '*.py' -o -name '*.md' -o -name '*.txt' | head -10")

    return result

# 使用示例
if __name__ == "__main__":
    # 创建不同类型的项目
    print("创建基础Python项目...")
    init_python_project("my_basic_app", "basic")

    print("\n创建Web应用项目...")
    init_python_project("my_web_app", "web")

    print("\n创建数据科学项目...")
    init_python_project("my_data_project", "data")
```

### 示例3：智能代码修复器

```python
import simacode

class CodeFixer:
    """智能代码修复器"""

    def fix_syntax_error(self, file_path, error_message):
        """修复语法错误"""
        task = f"""
        修复文件 {file_path} 中的语法错误：
        错误信息：{error_message}

        请：
        1. 读取文件内容
        2. 分析错误原因
        3. 修复语法错误
        4. 保存修复后的文件
        5. 解释修复了什么问题
        """
        return simacode.react(task)

    def optimize_code(self, file_path):
        """优化代码"""
        task = f"""
        优化文件 {file_path} 中的代码：
        1. 提高代码效率
        2. 改进代码可读性
        3. 添加必要的注释
        4. 遵循Python最佳实践
        5. 保存优化后的代码
        """
        return simacode.react(task)

    def add_error_handling(self, file_path):
        """添加错误处理"""
        task = f"""
        为文件 {file_path} 添加完善的错误处理：
        1. 识别可能出错的地方
        2. 添加try-except语句
        3. 添加适当的错误信息
        4. 确保程序健壮性
        """
        return simacode.react(task)

# 使用示例
fixer = CodeFixer()

# 修复语法错误
print("修复语法错误...")
result = fixer.fix_syntax_error("buggy_code.py", "SyntaxError: invalid syntax")

# 优化代码
print("优化代码...")
result = fixer.optimize_code("my_script.py")

# 添加错误处理
print("添加错误处理...")
result = fixer.add_error_handling("my_script.py")
```

## 重要的simacode方法说明

### 基础方法

```python
import simacode

# 1. chat() - 简单对话，适合问答和简单任务
response = simacode.chat("你的问题或请求")

# 2. react() - 智能规划执行，适合复杂任务
response = simacode.react("复杂的编程任务描述")
```

### 高级用法

```python
# 如果你需要更多控制，可以这样使用：
from simacode.core.service import SimaCodeService, ChatRequest, ReActRequest
import asyncio

async def advanced_usage():
    service = SimaCodeService()

    # 普通聊天请求
    chat_request = ChatRequest(message="创建hello world程序")
    chat_response = await service.chat(chat_request)

    # ReAct请求（带规划的智能执行）
    react_request = ReActRequest(task="创建完整的Web应用")
    react_response = await service.react(react_request)

    return chat_response, react_response

# 运行异步函数
if __name__ == "__main__":
    asyncio.run(advanced_usage())
```

## 新手常见问题解答

### Q1: `simacode init` 后如何检查配置？

```bash
# 检查初始化是否成功
ls -la .simacode/

# 应该看到：
# config.yaml  - 配置文件
# logs/        - 日志目录
# sessions/    - 会话目录

# 检查配置文件内容
cat .simacode/config.yaml
```

### Q2: 导入simacode时出错？
```python
# 确保安装正确
import sys
print(sys.path)  # 检查Python路径

# 重新安装
# pip install git+https://github.com/QUSEIT/simacode.git
```

### Q3: AI连接失败？
```python
import simacode

# 测试连接
try:
    response = simacode.chat("hello")
    print("连接成功：", response)
except Exception as e:
    print("连接失败：", e)
    print("请检查API密钥和配置文件")
```

### Q4: 如何在代码中处理错误？
```python
import simacode

def safe_ai_call(task):
    """安全的AI调用，带错误处理"""
    try:
        response = simacode.react(task)
        return {"success": True, "result": response}
    except Exception as e:
        return {"success": False, "error": str(e)}

# 使用示例
result = safe_ai_call("创建一个计算器程序")
if result["success"]:
    print("AI任务完成：", result["result"])
else:
    print("AI任务失败：", result["error"])
```

## 给新手的最佳实践

### 1. 项目目录结构建议
```
my_ai_project/
├── .simacode/           # SimaCode配置(simacode init创建)
│   ├── config.yaml     # 配置文件
│   ├── logs/           # 日志目录
│   └── sessions/       # 会话目录
├── src/                # 源码目录
├── tests/              # 测试目录
├── data/               # 数据目录
└── my_ai_helper.py     # 你的AI助手脚本
```

### 2. 从简单任务开始
```python
import simacode

# 先试试简单的任务
print(simacode.chat("解释什么是变量"))
print(simacode.chat("创建一个打印hello world的函数"))
```

### 3. 逐步增加复杂度
```python
# 基础版本
simacode.chat("创建一个加法函数")

# 增强版本
simacode.react("创建一个计算器类，支持四则运算，包含错误处理")

# 完整版本
simacode.react("创建一个图形界面计算器，使用tkinter，保存为calculator_gui.py")
```

### 4. 清楚地描述需求
```python
# 不好的描述
simacode.chat("写个程序")

# 好的描述
simacode.react("""
创建一个学生成绩管理程序：
1. 可以添加学生和成绩
2. 可以计算平均分
3. 可以查看所有学生
4. 数据保存到JSON文件
5. 包含输入验证
""")
```

## 完整的入门流程总结

```bash
# 1. 安装SimaCode
pip install git+https://github.com/QUSEIT/simacode.git

# 2. 创建项目目录
mkdir my_first_ai_project
cd my_first_ai_project

# 3. 初始化配置
simacode init

# 4. 编辑配置文件，添加API密钥
nano .simacode/config.yaml

# 5. 测试配置
simacode config --check

# 6. 开始使用
simacode chat "创建一个HelloWorld程序"
```

然后在Python代码中：
```python
import simacode

# 开始你的AI编程之旅！
response = simacode.chat("你好，AI助手！")
print(response)
```

## 总结

通过这个指南，你已经学会了：

- ✅ 安装SimaCode并使用 `simacode init` 初始化项目
- ✅ 正确配置AI服务和API密钥
- ✅ 在Python代码中导入和使用simacode
- ✅ 使用 `simacode.chat()` 进行简单AI对话
- ✅ 使用 `simacode.react()` 执行复杂编程任务
- ✅ 创建自己的AI编程助手
- ✅ 处理错误和异常情况

**simacode的核心价值**：把AI集成到你的Python代码中，让你的程序具备AI能力！

无论是创建工具脚本、自动化任务、还是构建复杂应用，simacode都能成为你的编程伙伴。

从今天开始，试着在你的Python项目中：
1. 运行 `simacode init`
2. 配置API密钥
3. 加入 `import simacode`
4. 让AI帮你写代码、修复bug、优化性能！

---

*觉得有用的话，记得给SimaCode项目点个Star⭐️支持一下！*

**快速链接：**
- 项目地址：https://github.com/QUSEIT/simacode
- AI服务申请：https://user.pgpt.cloud
- 遇到问题：https://github.com/QUSEIT/simacode/issues

*下一期我们会讲解simacode的高级功能和企业级应用，敬请期待！*
