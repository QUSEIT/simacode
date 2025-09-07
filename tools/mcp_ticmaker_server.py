#!/usr/bin/env python3
"""
TICMaker MCP Server for SimaCode
专门处理HTML网页创建和修改的MCP服务器
支持CLI和API双模式
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
    """TICMaker专用MCP服务器 - 处理HTML网页创建和修改"""
    
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
                    name="create_html_page",
                    description="创建或修改HTML网页文件",
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
                                    "scope": {"type": "string"},
                                    "file_path": {"type": "string", "description": "可选的文件路径"},
                                    "template": {"type": "string", "description": "可选的HTML模板"},
                                    "style": {"type": "string", "description": "可选的样式要求"}
                                }
                            },
                            "session_id": {"type": "string", "description": "会话标识符"},
                            "source": {"type": "string", "description": "请求来源: CLI或API"},
                            "operation": {
                                "type": "string", 
                                "description": "操作类型: create（创建新页面）或modify（修改现有页面）",
                                "enum": ["create", "modify"]
                            }
                        },
                        "required": ["message"]
                    }
                ),
                types.Tool(
                    name="list_html_pages",
                    description="列出已创建的HTML页面",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "pattern": {"type": "string", "description": "可选的文件名匹配模式"}
                        }
                    }
                )
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[types.TextContent]:
            if name == "create_html_page":
                return await self._create_html_page(arguments)
            elif name == "list_html_pages":
                return await self._list_html_pages(arguments)
            raise ValueError(f"Unknown tool: {name}")
    
    async def _create_html_page(self, args: Dict[str, Any]) -> List[types.TextContent]:
        """创建或修改HTML网页"""
        message = args.get("message", "")
        context = args.get("context", {})
        session_id = args.get("session_id", "unknown")
        source = args.get("source", "unknown")
        operation = args.get("operation", "create")
        
        # 日志记录到stderr
        logger.info("=" * 80)
        logger.info("🎯 TICMaker - HTML页面处理请求")
        logger.info(f"操作类型: {operation}")
        logger.info(f"来源: {source}")
        logger.info(f"会话ID: {session_id}")
        logger.info(f"用户需求: {message}")
        logger.info(f"上下文: {json.dumps(context, indent=2, ensure_ascii=False)}")
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
            result_msg = f"✅ HTML页面已{'修改' if operation == 'modify' else '创建'}成功"
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
            error_msg = f"❌ HTML页面处理失败: {str(e)}"
            logger.error(f"\n{error_msg}")
            logger.error(f"HTML creation error: {e}")
            
            return [
                types.TextContent(
                    type="text",
                    text=error_msg
                )
            ]
    
    async def _generate_html_content(self, message: str, context: Dict[str, Any]) -> str:
        """根据用户需求生成HTML内容"""
        title = self._extract_title_from_message(message)
        style = context.get("style", "modern")
        template = context.get("template", "basic")
        
        # 基础HTML模板
        if template == "interactive":
            html_content = self._generate_interactive_template(title, message, style)
        elif template == "educational":
            html_content = self._generate_educational_template(title, message, style)
        else:
            html_content = self._generate_basic_template(title, message, style)
        
        return html_content
    
    async def _modify_html_content(self, existing_content: str, message: str, context: Dict[str, Any]) -> str:
        """修改现有HTML内容"""
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
        # 简单的标题提取逻辑
        if "创建" in message or "制作" in message:
            if "游戏" in message:
                return "互动教学游戏"
            elif "活动" in message:
                return "教学活动页面"
            elif "课程" in message:
                return "课程内容页面"
        
        return "TICMaker生成页面"
    
    def _generate_basic_template(self, title: str, message: str, style: str) -> str:
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
            <p><strong>用户需求:</strong> {message}</p>
            <p>这是由TICMaker生成的HTML页面，专为互动教学设计。</p>
        </div>
        <div class="timestamp">
            生成时间: {datetime.now().strftime("%Y年%m月%d日 %H:%M:%S")}
        </div>
    </div>
</body>
</html>"""
    
    def _generate_interactive_template(self, title: str, message: str, style: str) -> str:
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
    
    def _generate_educational_template(self, title: str, message: str, style: str) -> str:
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
    
    async def _list_html_pages(self, args: Dict[str, Any]) -> List[types.TextContent]:
        """列出已创建的HTML页面"""
        pattern = args.get("pattern", "*.html")
        
        try:
            # 获取HTML文件列表
            html_files = list(self.output_dir.glob(pattern))
            
            if not html_files:
                return [
                    types.TextContent(
                        type="text",
                        text="📁 暂无HTML页面文件"
                    )
                ]
            
            # 构建文件列表
            file_list = []
            for file_path in sorted(html_files, key=lambda f: f.stat().st_mtime, reverse=True):
                stat = file_path.stat()
                size = stat.st_size
                modified = datetime.fromtimestamp(stat.st_mtime)
                
                file_list.append(f"📄 {file_path.name}")
                file_list.append(f"   大小: {size} bytes")
                file_list.append(f"   修改时间: {modified.strftime('%Y-%m-%d %H:%M:%S')}")
                file_list.append("")
            
            return [
                types.TextContent(
                    type="text",
                    text=f"📁 HTML页面列表 (共{len(html_files)}个文件):\n\n" + "\n".join(file_list)
                )
            ]
            
        except Exception as e:
            return [
                types.TextContent(
                    type="text",
                    text=f"❌ 列出文件失败: {str(e)}"
                )
            ]


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