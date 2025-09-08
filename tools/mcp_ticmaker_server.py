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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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
        self._setup_tools()
    
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
            # 检查是否为修改操作
            if operation == "modify" and file_path.exists():
                # 读取现有内容
                existing_content = file_path.read_text(encoding='utf-8')
                html_content = await self._modify_html_content(existing_content, message, context)
            else:
                # 创建新页面
                html_content = await self._generate_html_content(message, context)
            
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
    
    async def _generate_html_content(self, message: str, context: Dict[str, Any]) -> str:
        """根据用户需求生成互动课程内容"""
        title = self._extract_title_from_message(message)
        style = context.get("style", "modern")
        template = context.get("template", "basic")
        course_title = context.get("courseTitle", "")
        
        # 根据模板类型生成相应的HTML内容
        if template == "interactive":
            html_content = self._generate_interactive_template(title, message, style, course_title)
        elif template == "educational":
            html_content = self._generate_educational_template(title, message, style, course_title)
        else:
            # 默认使用基础模板，但根据消息内容智能选择
            if any(keyword in message.lower() for keyword in ["互动", "游戏", "点击", "按钮"]):
                html_content = self._generate_interactive_template(title, message, style, course_title)
            elif any(keyword in message.lower() for keyword in ["学习", "教学", "课程", "练习"]):
                html_content = self._generate_educational_template(title, message, style, course_title)
            else:
                html_content = self._generate_basic_template(title, message, style, course_title)
        
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
    
    def _generate_basic_template(self, title: str, message: str, style: str, course_title: str = "") -> str:
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
            <p><strong>课程需求:</strong> {message}</p>
            <p>这是由TICMaker生成的互动教学课程，专为现代化课堂教学设计。</p>
        </div>
        <div class="timestamp">
            生成时间: {datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")}
        </div>
    </div>
</body>
</html>"""
    
    def _generate_interactive_template(self, title: str, message: str, style: str, course_title: str = "") -> str:
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
        <p><strong>需求描述:</strong> {message}</p>
        
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
    
    def _generate_educational_template(self, title: str, message: str, style: str, course_title: str = "") -> str:
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
                <p>根据需求: {message}</p>
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
