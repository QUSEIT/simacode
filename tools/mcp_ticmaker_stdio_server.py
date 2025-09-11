#!/usr/bin/env python3
"""
TICMaker stdio MCP Server

A stdio-based MCP server that provides interactive teaching content creation capabilities.
It communicates with SimaCode via stdio protocol and provides HTML page creation and modification.

Features:
- stdio-based MCP server
- Interactive HTML page creation and modification
- AI-enhanced content generation (optional)
- Support for multiple template types
- Asynchronous file I/O operations
- Configuration via .simacode/config.yaml

Configuration:
This tool reads configuration from SimaCode's config system. Example config.yaml:

ticmaker:
  output_dir: "./ticmaker_output"
  default_template: "modern"
  ai_enhancement: false

Environment variables (fallback):
- TICMAKER_OUTPUT_DIR
- TICMAKER_TEMPLATE
"""

import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, AsyncGenerator
from dataclasses import dataclass

# Add parent directory to path for MCP imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# MCP Protocol imports (using our existing MCP implementation)
from src.simacode.mcp.protocol import MCPMessage, MCPMethods, MCPErrorCodes
from src.simacode.config import Config

# Import MCP file logging utility
try:
    from src.simacode.utils.mcp_logger import mcp_file_log, mcp_debug, mcp_info, mcp_warning, mcp_error
    MCP_LOGGING_AVAILABLE = True
except ImportError:
    # Fallback if logging utility is not available
    MCP_LOGGING_AVAILABLE = False
    def mcp_file_log(*args, **kwargs): pass
    def mcp_debug(*args, **kwargs): pass
    def mcp_info(*args, **kwargs): pass  
    def mcp_warning(*args, **kwargs): pass
    def mcp_error(*args, **kwargs): pass

# Configure logging to stderr to avoid interfering with stdio protocol
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)


@dataclass
class TICMakerConfig:
    """Configuration for TICMaker content creation."""
    output_dir: str = "./ticmaker_output"
    default_template: str = "modern"
    ai_enhancement: bool = False
    max_file_size: int = 1024 * 1024 * 10  # 10MB
    allowed_file_extensions: List[str] = None
    
    def __post_init__(self):
        """Set default values after initialization."""
        if self.allowed_file_extensions is None:
            self.allowed_file_extensions = [".html", ".htm"]


@dataclass
class TICMakerResult:
    """Result from TICMaker content creation operation."""
    success: bool
    message: str = ""
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Optional[Dict[str, Any]] = None


class TICMakerClient:
    """Client for TICMaker content creation operations."""
    
    def __init__(self, config: TICMakerConfig):
        """
        Initialize TICMaker client.
        
        Args:
            config: TICMaker configuration containing settings
        """
        self.config = config
        self.output_dir = Path(config.output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        logger.info(f"[TICMAKER_CONFIG] Output directory: {self.output_dir}")
        logger.info(f"[TICMAKER_CONFIG] Default template: {self.config.default_template}")
        logger.info(f"[TICMAKER_CONFIG] AI enhancement: {self.config.ai_enhancement}")
        
        # Log initialization to file
        mcp_info("TICMaker client initialized", {
            "output_dir": str(self.output_dir),
            "default_template": self.config.default_template,
            "ai_enhancement": self.config.ai_enhancement,
            "logging_available": MCP_LOGGING_AVAILABLE
        }, tool_name="ticmaker")
    
    async def create_interactive_course(
        self,
        user_input: str,
        course_title: Optional[str] = None,
        file_path: Optional[str] = None,
        template_style: Optional[str] = None,
        session_context: Optional[Dict[str, Any]] = None
    ) -> TICMakerResult:
        """Create interactive teaching content."""
        start_time = datetime.now()
        
        try:
            logger.info("🎯 ===== TICMaker Course Creation Started =====")
            logger.info(f"   💬 User Requirements: {user_input}")
            logger.info(f"   📄 Course Title: {course_title or 'Not specified'}")
            logger.info(f"   📁 File Path: {file_path or 'Auto-generate'}")
            if session_context:
                logger.info(f"   🔄 Session State: {session_context.get('session_state', 'Unknown')}")
                logger.info(f"   📋 Current Task: {session_context.get('current_task', 'Unknown')}")
                logger.info(f"   👤 Session User Input: {session_context.get('user_input', 'Unknown')[:50]}...")
            
            # Log course creation start to file
            mcp_info("Course creation started", {
                "user_input": user_input,
                "course_title": course_title,
                "file_path": str(file_path) if file_path else None,
                "template_style": template_style,
                "session_context": session_context
            }, tool_name="ticmaker", session_id=session_context.get('session_id') if session_context else None)
            
            # Validate input
            if not user_input or not user_input.strip():
                mcp_error("Course creation failed - empty user input", tool_name="ticmaker")
                return TICMakerResult(
                    success=False,
                    error="User input is required"
                )
            
            # Determine file path
            if not file_path:
                # Generate default filename
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                random_id = str(uuid.uuid4())[:8]
                filename = f"ticmaker_page_{timestamp}_{random_id}.html"
                file_path = self.output_dir / filename
                logger.info(f"📁 Generated filename: {filename}")
            else:
                original_path = file_path
                file_path = Path(file_path)
                # Ensure file is in safe directory
                if not str(file_path.resolve()).startswith(str(self.output_dir.resolve())):
                    file_path = self.output_dir / Path(file_path).name
                    logger.warning(f"⚠️ File path adjusted for security: {original_path} → {file_path}")
            
            logger.info(f"📄 Final file path: {file_path}")
            
            # Check if modifying existing file
            file_exists = file_path.exists()
            logger.info(f"📋 File exists: {file_exists}")
            
            if file_exists:
                logger.info("📖 Reading existing file content...")
                # Read existing content and modify
                existing_content = file_path.read_text(encoding='utf-8')
                logger.info(f"📏 Existing content length: {len(existing_content)} characters")
                
                logger.info("🔧 Modifying existing HTML content...")
                html_content = await self._modify_html_content(existing_content, user_input)
            else:
                logger.info("🆕 Creating new HTML content...")
                # Create new page
                html_content = await self._generate_html_content(
                    user_input, 
                    course_title,
                    template_style or self.config.default_template,
                    session_context
                )
            
            # Check content size
            if len(html_content.encode('utf-8')) > self.config.max_file_size:
                return TICMakerResult(
                    success=False,
                    error=f"Generated content too large ({len(html_content)} characters > {self.config.max_file_size} bytes)"
                )
            
            # Write file
            logger.info("💾 Writing HTML content to file...")
            file_path.write_text(html_content, encoding='utf-8')
            
            # Get file info
            file_size = file_path.stat().st_size
            action = "Modified" if file_exists else "Created"
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            logger.info(f"🎉 Interactive course {action.lower()} successfully")
            logger.info(f"📁 File path: {file_path}")
            logger.info(f"📏 File size: {file_size} bytes")
            logger.info(f"⏱️ Execution time: {execution_time:.2f}s")
            logger.info("🎯 ===== TICMaker Course Creation Completed =====")
            
            # Log successful completion to file
            mcp_info(f"Course creation completed successfully", {
                "action": action.lower(),
                "file_path": str(file_path),
                "file_size": file_size,
                "execution_time": execution_time,
                "content_length": len(html_content),
                "session_context_included": session_context is not None
            }, tool_name="ticmaker", session_id=session_context.get('session_id') if session_context else None)
            
            return TICMakerResult(
                success=True,
                message=f"Interactive course {action.lower()} successfully",
                execution_time=execution_time,
                metadata={
                    "file_path": str(file_path),
                    "file_size": file_size,
                    "action": action.lower(),
                    "user_input": user_input,
                    "course_title": course_title,
                    "template_style": template_style or self.config.default_template,
                    "session_context": session_context
                }
            )
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            error_msg = f"Interactive course creation failed: {str(e)}"
            logger.error(f"💥 {error_msg}")
            logger.error(f"⏱️ Execution time before error: {execution_time:.2f}s")
            logger.error("🎯 ===== TICMaker Course Creation Failed =====")
            
            # Log error to file with detailed context
            mcp_error("Course creation failed with exception", {
                "error_message": str(e),
                "error_type": type(e).__name__,
                "execution_time": execution_time,
                "user_input": user_input,
                "course_title": course_title,
                "file_path": str(file_path) if file_path else None,
                "session_context": session_context
            }, tool_name="ticmaker", session_id=session_context.get('session_id') if session_context else None)
            
            return TICMakerResult(
                success=False,
                error=error_msg,
                execution_time=execution_time
            )
    
    async def _generate_html_content(
        self, 
        user_input: str, 
        course_title: Optional[str] = None,
        template_style: str = "modern",
        session_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate HTML content for interactive course."""
        # Extract title from user input if not provided
        title = course_title if course_title else self._extract_title_from_user_input(user_input)
        
        # Generate interactive template
        html_content = self._generate_interactive_template(title, user_input, template_style, course_title, session_context)
        
        return html_content
    
    async def _modify_html_content(self, existing_content: str, user_input: str) -> str:
        """Modify existing course content."""
        # Simple modification logic - add modification note
        modification_note = f"\n<!-- Modification record: {datetime.now().isoformat()} - {user_input} -->\n"
        
        # Insert modification content before </body>
        if "</body>" in existing_content:
            insert_content = f'''<div class="modification-note" style="margin-top: 20px; padding: 10px; background-color: #f0f8ff; border: 1px solid #ccc;">
<strong>Latest modification:</strong> {user_input}
<small>Modification time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</small>
</div>
'''
            existing_content = existing_content.replace("</body>", f"{insert_content}</body>")
        
        # Add modification note
        existing_content += modification_note
        
        return existing_content
    
    def _extract_title_from_user_input(self, user_input: str) -> str:
        """Extract title from user input."""
        user_input_lower = user_input.lower()
        
        # Detect specific content types
        if any(keyword in user_input_lower for keyword in ["游戏", "小游戏", "互动游戏"]):
            return "Interactive Teaching Game"
        elif any(keyword in user_input_lower for keyword in ["活动", "练习", "训练"]):
            return "Teaching Activity Page"
        elif any(keyword in user_input_lower for keyword in ["课程", "教学", "学习"]):
            return "Interactive Course Content"
        elif any(keyword in user_input_lower for keyword in ["测验", "测试", "考试"]):
            return "Interactive Quiz Page"
        elif any(keyword in user_input_lower for keyword in ["讨论", "问答", "q&a"]):
            return "Discussion and Q&A Page"
        else:
            return "Interactive Teaching Content"
    
    def _generate_interactive_template(
        self, 
        title: str, 
        user_input: str, 
        template_style: str = "modern",
        course_title: Optional[str] = None,
        session_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate interactive HTML template."""
        
        # Modern template with comprehensive interactive features
        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: white;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(45deg, #f093fb 0%, #f5576c 100%);
            color: white;
            padding: 30px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}
        
        .header h2 {{
            font-size: 1.3em;
            opacity: 0.9;
            font-weight: 300;
        }}
        
        .content {{
            padding: 40px;
        }}
        
        .requirement-box {{
            background: #f8f9ff;
            padding: 20px;
            border-radius: 10px;
            border-left: 4px solid #667eea;
            margin-bottom: 30px;
        }}
        
        .requirement-box strong {{
            color: #667eea;
            font-size: 1.1em;
        }}
        
        .interaction-area {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }}
        
        .interactive-button {{
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
            border: none;
            padding: 15px 25px;
            border-radius: 25px;
            cursor: pointer;
            font-size: 1.1em;
            font-weight: 600;
            transition: all 0.3s ease;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        
        .interactive-button:hover {{
            transform: translateY(-3px);
            box-shadow: 0 5px 15px rgba(102, 126, 234, 0.4);
        }}
        
        .interactive-button:active {{
            transform: translateY(-1px);
        }}
        
        .content-area {{
            background: #f8f9ff;
            border-radius: 10px;
            padding: 20px;
            margin-top: 20px;
            min-height: 150px;
            border: 2px dashed #ddd;
            text-align: center;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        
        .quiz-container {{
            display: none;
            margin-top: 20px;
        }}
        
        .quiz-question {{
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 15px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        
        .quiz-options {{
            list-style: none;
            margin-top: 15px;
        }}
        
        .quiz-options li {{
            background: #f8f9ff;
            padding: 10px 15px;
            margin: 8px 0;
            border-radius: 5px;
            cursor: pointer;
            transition: all 0.3s ease;
        }}
        
        .quiz-options li:hover {{
            background: #667eea;
            color: white;
            transform: translateX(10px);
        }}
        
        .footer {{
            background: #f8f9ff;
            padding: 20px;
            text-align: center;
            color: #666;
            border-top: 1px solid #eee;
        }}
        
        .badge {{
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9em;
            margin: 5px;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(20px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        .fade-in {{
            animation: fadeIn 0.6s ease-out;
        }}
        
        .info-panel {{
            display: none;
            background: linear-gradient(135deg, #84fab0 0%, #8fd3f4 100%);
            padding: 20px;
            border-radius: 10px;
            margin-top: 20px;
            color: #2c3e50;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            {f'<h2>📚 Course: {course_title}</h2>' if course_title else ''}
        </div>
        
        <div class="content">
            <div class="requirement-box">
                <strong>用户需求:</strong> {user_input}
            </div>
            
            <div class="interaction-area">
                <button class="interactive-button" onclick="showMessage('🎉 太棒了！您正在体验由TICMaker创建的交互式内容！')">点击交互</button>
                <button class="interactive-button" onclick="showQuiz()">开始小测验</button>
                <button class="interactive-button" onclick="showInfo()">课程信息</button>
                <button class="interactive-button" onclick="showActivity()">互动活动</button>
                <button class="interactive-button" onclick="showSessionContext()">Session Context</button>
            </div>
            
            <div class="content-area" id="dynamic-content">
                <p>👆 点击上方按钮开始互动体验</p>
            </div>
            
            <div class="quiz-container" id="quiz-container">
                <div class="quiz-question">
                    <h3>📝 快速测验</h3>
                    <p>以下哪个是TICMaker的主要功能？</p>
                    <ul class="quiz-options">
                        <li onclick="checkAnswer(this, true)">创建交互式教学内容</li>
                        <li onclick="checkAnswer(this, false)">文档编辑</li>
                        <li onclick="checkAnswer(this, false)">数据分析</li>
                        <li onclick="checkAnswer(this, false)">图片处理</li>
                    </ul>
                </div>
            </div>
            
            <div class="info-panel" id="info-panel">
                <h3>📋 课程详细信息</h3>
                <div class="badge">互动教学</div>
                <div class="badge">HTML页面</div>
                <div class="badge">AI辅助</div>
                <div class="badge">响应式设计</div>
                <p><strong>创建时间:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
                <p><strong>用户需求:</strong> {user_input}</p>
                <p><strong>技术特点:</strong> 基于现代Web技术的交互式教学内容创建工具</p>
                {self._generate_session_info_html(session_context)}
            </div>
        </div>
        
        <div class="footer">
            <p>🚀 由 <strong>TICMaker</strong> 创建 | ⚡ 交互式教学内容生成器</p>
            <p><small>创建时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</small></p>
        </div>
    </div>
    
    <script>
        function showMessage(message) {{
            const contentArea = document.getElementById('dynamic-content');
            contentArea.innerHTML = `
                <div class="fade-in">
                    <h3>🎯 互动消息</h3>
                    <p style="font-size: 1.2em; margin: 20px 0;">${{message}}</p>
                    <button class="interactive-button" onclick="resetContent()" style="margin-top: 15px;">返回</button>
                </div>
            `;
            contentArea.className = 'content-area fade-in';
        }}
        
        function showQuiz() {{
            document.getElementById('quiz-container').style.display = 'block';
            document.getElementById('dynamic-content').innerHTML = `
                <div class="fade-in">
                    <h3>📚 测验模式已激活</h3>
                    <p>请查看下方的测验题目并选择答案</p>
                </div>
            `;
        }}
        
        function showInfo() {{
            const infoPanel = document.getElementById('info-panel');
            infoPanel.style.display = infoPanel.style.display === 'block' ? 'none' : 'block';
            infoPanel.className = 'info-panel fade-in';
            
            document.getElementById('dynamic-content').innerHTML = `
                <div class="fade-in">
                    <h3>ℹ️ 课程信息</h3>
                    <p>课程详细信息已在下方展示</p>
                </div>
            `;
        }}
        
        function showActivity() {{
            const activities = [
                "🎨 创意绘画练习",
                "🧩 逻辑思维训练", 
                "📖 阅读理解练习",
                "🔬 科学实验模拟",
                "🎵 音乐节拍练习"
            ];
            const randomActivity = activities[Math.floor(Math.random() * activities.length)];
            
            document.getElementById('dynamic-content').innerHTML = `
                <div class="fade-in">
                    <h3>🎯 今日推荐活动</h3>
                    <p style="font-size: 1.3em; margin: 20px 0; color: #667eea;">${{randomActivity}}</p>
                    <button class="interactive-button" onclick="showActivity()" style="margin: 5px;">换一个活动</button>
                    <button class="interactive-button" onclick="resetContent()" style="margin: 5px;">返回首页</button>
                </div>
            `;
        }}
        
        function checkAnswer(element, isCorrect) {{
            const options = document.querySelectorAll('.quiz-options li');
            options.forEach(opt => {{
                opt.style.pointerEvents = 'none';
                opt.style.opacity = '0.6';
            }});
            
            if (isCorrect) {{
                element.style.background = '#28a745';
                element.style.color = 'white';
                element.style.transform = 'scale(1.05)';
                setTimeout(() => {{
                    alert('🎉 恭喜！答案正确！');
                    resetQuiz();
                }}, 500);
            }} else {{
                element.style.background = '#dc3545';
                element.style.color = 'white';
                setTimeout(() => {{
                    alert('😅 答案错误，再试试吧！');
                    resetQuiz();
                }}, 500);
            }}
        }}
        
        function resetQuiz() {{
            const options = document.querySelectorAll('.quiz-options li');
            options.forEach(opt => {{
                opt.style.background = '#f8f9ff';
                opt.style.color = '#333';
                opt.style.pointerEvents = 'auto';
                opt.style.opacity = '1';
                opt.style.transform = 'scale(1)';
            }});
        }}
        
        function resetContent() {{
            document.getElementById('dynamic-content').innerHTML = `
                <p>👆 点击上方按钮开始互动体验</p>
            `;
            document.getElementById('quiz-container').style.display = 'none';
            document.getElementById('info-panel').style.display = 'none';
        }}
        
        function showSessionContext() {{
            const sessionInfo = {json.dumps(session_context, ensure_ascii=False) if session_context else 'null'};
            const contentArea = document.getElementById('dynamic-content');
            
            if (sessionInfo && sessionInfo !== null && Object.keys(sessionInfo).length > 0) {{
                // Display session context information
                contentArea.innerHTML = `
                    <div class="fade-in">
                        <h3>🔄 Session Context Details</h3>
                        <div style="background: #f8f9ff; padding: 20px; border-radius: 10px; margin: 20px 0; text-align: left;">
                            <h4>📊 Real-time Session Information:</h4>
                            <div style="font-family: monospace; background: #e9ecef; padding: 15px; border-radius: 5px; margin: 10px 0;">
                                <pre>${{JSON.stringify(sessionInfo, null, 2)}}</pre>
                            </div>
                            <p><strong>🔍 Session State:</strong> <span style="color: #667eea;">${{sessionInfo.session_state || 'Unknown'}}</span></p>
                            <p><strong>📋 Current Task:</strong> <span style="color: #764ba2;">${{sessionInfo.current_task || 'Unknown'}}</span></p>
                            <p><strong>👤 User Input:</strong> <span style="color: #f5576c;">${{(sessionInfo.user_input || 'Unknown').substring(0, 100)}}...</span></p>
                        </div>
                        <button class="interactive-button" onclick="resetContent()" style="margin-top: 15px;">返回</button>
                    </div>
                `;
            }} else {{
                // Display message when no session context is available
                contentArea.innerHTML = `
                    <div class="fade-in">
                        <h3>🔄 Session Context</h3>
                        <div style="background: #fff3cd; padding: 20px; border-radius: 10px; margin: 20px 0; text-align: center; border: 1px solid #ffeaa7;">
                            <h4 style="color: #856404;">📋 No Session Context Available</h4>
                            <p style="color: #856404; margin: 15px 0;">This content was created without active session context information.</p>
                            <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 15px 0;">
                                <p><strong>💡 Session Context Features:</strong></p>
                                <ul style="text-align: left; color: #495057;">
                                    <li>🔍 Current session state tracking</li>
                                    <li>📋 Active task information</li>
                                    <li>👤 User input history</li>
                                    <li>🔄 Real-time context updates</li>
                                </ul>
                            </div>
                            <p style="font-size: 0.9em; color: #6c757d; font-style: italic;">
                                To see session context, this tool needs to be called from within a SimaCode ReAct session.
                            </p>
                        </div>
                        <button class="interactive-button" onclick="resetContent()" style="margin-top: 15px;">返回</button>
                    </div>
                `;
            }}
            contentArea.className = 'content-area fade-in';
        }}
        
        // Add some entrance animations
        window.addEventListener('load', function() {{
            document.querySelector('.container').classList.add('fade-in');
        }});
    </script>
</body>
</html>"""
        
        return html_content
    
    def _generate_session_info_html(self, session_context: Optional[Dict[str, Any]]) -> str:
        """Generate HTML content for session context information."""
        if not session_context:
            return ""
        
        session_state = session_context.get("session_state", "Unknown")
        current_task = session_context.get("current_task", "Unknown")
        session_user_input = session_context.get("user_input", "Unknown")
        
        return f"""
                <hr style="margin: 20px 0; border: none; border-top: 1px solid #ddd;">
                <h4>🔄 Session Context Information</h4>
                <div style="background: #f0f8ff; padding: 15px; border-radius: 8px; margin: 10px 0;">
                    <p><strong>🔍 Session State:</strong> <span style="color: #667eea; font-weight: 600;">{session_state}</span></p>
                    <p><strong>📋 Current Task:</strong> <span style="color: #764ba2; font-weight: 600;">{current_task}</span></p>
                    <p><strong>👤 Session User Input:</strong> <span style="color: #f5576c; font-style: italic;">{session_user_input[:100]}{'...' if len(session_user_input) > 100 else ''}</span></p>
                </div>
                <div class="badge" style="background: #28a745;">Session-Aware</div>
                <div class="badge" style="background: #17a2b8;">Context-Enabled</div>"""


class TICMakerStdioMCPServer:
    """
    stdio-based MCP server for TICMaker interactive content creation.
    
    This server communicates via standard input/output (stdio) and provides
    interactive teaching content creation capabilities.
    """
    
    def __init__(self, ticmaker_config: Optional[TICMakerConfig] = None):
        """
        Initialize TICMaker stdio MCP server.
        
        Args:
            ticmaker_config: Configuration for TICMaker operations
        """
        # Initialize TICMaker client with configuration
        self.ticmaker_config = ticmaker_config or TICMakerConfig()
        self.ticmaker_client = TICMakerClient(self.ticmaker_config)
        
        # MCP server info
        self.server_info = {
            "name": "ticmaker-stdio-mcp-server",
            "version": "1.0.0",
            "description": "TICMaker stdio MCP Server for Interactive Teaching Content Creation"
        }
        
        # Available tools
        self.tools = {
            "create_interactive_course": {
                "name": "create_interactive_course",
                "description": "Create or modify interactive teaching content and HTML pages",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "user_input": {
                            "type": "string",
                            "description": "User's requirements for creating or modifying interactive teaching content"
                        },
                        "course_title": {
                            "type": "string",
                            "description": "Optional course title - will be auto-generated if not provided"
                        },
                        "file_path": {
                            "type": "string", 
                            "description": "Optional file path for the HTML output - will be auto-generated if not provided"
                        },
                        "template_style": {
                            "type": "string",
                            "enum": ["modern", "classic", "minimal"],
                            "description": "Template style for the generated content",
                            "default": "modern"
                        },
                        "_session_context": {
                            "type": "object",
                            "description": "Session context information from SimaCode ReAct engine",
                            "properties": {
                                "session_state": {"type": "string"},
                                "current_task": {"type": "string"},
                                "user_input": {"type": "string"}
                            }
                        }
                    },
                    "required": ["user_input"]
                }
            }
        }
    
    async def run(self):
        """Run the stdio MCP server."""
        logger.info("🚀 Starting TICMaker stdio MCP server...")
        logger.info(f"📂 Output directory: {self.ticmaker_config.output_dir}")
        logger.info(f"🎨 Default template: {self.ticmaker_config.default_template}")
        logger.info("📡 Ready to receive MCP messages via stdio")
        
        # Log server startup to file
        mcp_info("TICMaker MCP server started", {
            "server_version": self.server_info["version"],
            "output_dir": self.ticmaker_config.output_dir,
            "default_template": self.ticmaker_config.default_template,
            "ai_enhancement": self.ticmaker_config.ai_enhancement
        }, tool_name="ticmaker")
        
        try:
            while True:
                try:
                    # Read from stdin
                    line = await asyncio.to_thread(sys.stdin.readline)
                    if not line:
                        break
                    
                    line = line.strip()
                    if not line:
                        continue
                    
                    logger.debug(f"📥 Received: {line}")
                    
                    # Parse MCP message
                    try:
                        message_data = json.loads(line)
                        message = MCPMessage(**message_data)
                    except (json.JSONDecodeError, TypeError, ValueError) as e:
                        logger.error(f"❌ Invalid JSON message: {str(e)}")
                        continue
                    
                    # Process message
                    response = await self.handle_message(message)
                    
                    # Send response
                    if response:
                        response_json = response.to_dict()
                        response_line = json.dumps(response_json, ensure_ascii=False)
                        print(response_line, flush=True)
                        logger.debug(f"📤 Sent: {response_line}")
                    
                except Exception as e:
                    logger.error(f"💥 Error processing message: {str(e)}")
                    continue
                    
        except KeyboardInterrupt:
            logger.info("🛑 Server stopped by user")
        except Exception as e:
            logger.error(f"💥 Server error: {str(e)}")
        finally:
            logger.info("👋 TICMaker stdio MCP server shutting down")
    
    async def handle_message(self, message: MCPMessage) -> Optional[MCPMessage]:
        """Handle incoming MCP message."""
        logger.debug(f"🔄 Processing {message.method} message with id: {message.id}")
        
        if message.method == MCPMethods.INITIALIZE:
            # Initialization request
            logger.info("🔧 Processing INITIALIZE request")
            capabilities = {
                "tools": {
                    tool_name: tool_info["description"] 
                    for tool_name, tool_info in self.tools.items()
                }
            }
            response = MCPMessage(
                id=message.id,
                result={
                    "protocolVersion": "2024-11-05",
                    "capabilities": capabilities,
                    "serverInfo": self.server_info
                }
            )
            logger.info("✅ Server initialized successfully")
            return response
            
        elif message.method == MCPMethods.TOOLS_LIST:
            # List available tools
            logger.info("🛠️ Processing TOOLS_LIST request")
            tools_list = [
                {
                    "name": tool_name,
                    "description": tool_info["description"],
                    "inputSchema": tool_info["input_schema"]
                }
                for tool_name, tool_info in self.tools.items()
            ]
            response = MCPMessage(
                id=message.id,
                result={"tools": tools_list}
            )
            logger.debug(f"✅ TOOLS_LIST response: {len(tools_list)} tools")
            return response
            
        elif message.method == MCPMethods.TOOLS_CALL:
            # Execute tool
            logger.info("⚡ Processing TOOLS_CALL request")
            try:
                params = message.params or {}
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                
                logger.info(f"🔧 Executing tool: {tool_name}")
                logger.debug(f"📝 Tool arguments: {arguments}")
                
                if tool_name not in self.tools:
                    logger.error(f"❌ Tool '{tool_name}' not found")
                    return MCPMessage(
                        id=message.id,
                        error={
                            "code": MCPErrorCodes.TOOL_NOT_FOUND,
                            "message": f"Tool '{tool_name}' not found"
                        }
                    )
                
                if tool_name == "create_interactive_course":
                    # Log tool execution start to file
                    mcp_debug(f"Executing tool: {tool_name}", {
                        "arguments": arguments,
                        "message_id": message.id
                    }, tool_name="ticmaker")
                    
                    result = await self._create_interactive_course(arguments)
                else:
                    mcp_error(f"Unknown tool requested: {tool_name}", tool_name="ticmaker")
                    raise ValueError(f"Unknown tool: {tool_name}")
                
                logger.info(f"✅ Tool '{tool_name}' completed successfully")
                
                # Log tool execution completion to file
                mcp_debug(f"Tool execution completed: {tool_name}", {
                    "success": result.success,
                    "execution_time": result.execution_time,
                    "message_id": message.id
                }, tool_name="ticmaker")
                
                # Create response
                response_content = {
                    "success": result.success,
                    "message": result.message if result.success else result.error,
                    "execution_time": result.execution_time,
                    "timestamp": datetime.now().isoformat()
                }
                
                if result.metadata:
                    response_content["metadata"] = result.metadata
                
                # Serialize JSON
                try:
                    json_text = json.dumps(response_content, indent=2, ensure_ascii=False)
                except UnicodeEncodeError:
                    json_text = json.dumps(response_content, indent=2, ensure_ascii=True)
                
                return MCPMessage(
                    id=message.id,
                    result={
                        "content": [
                            {
                                "type": "text",
                                "text": json_text
                            }
                        ],
                        "isError": not result.success,
                        "metadata": {
                            "execution_time": result.execution_time,
                            "tool": tool_name,
                            "response_size_bytes": len(json_text.encode('utf-8'))
                        }
                    }
                )
                
            except Exception as e:
                logger.error(f"💥 Tool execution error: {str(e)}")
                
                return MCPMessage(
                    id=message.id,
                    error={
                        "code": MCPErrorCodes.INTERNAL_ERROR,
                        "message": str(e)
                    }
                )
        
        elif message.method == MCPMethods.PING:
            # Ping response
            logger.info("🏓 Processing PING request")
            response = MCPMessage(
                id=message.id,
                result={"pong": True}
            )
            logger.debug("✅ PING response: pong")
            return response
            
        elif message.method == MCPMethods.RESOURCES_LIST:
            # List available resources (none for TICMaker)
            logger.info("📚 Processing RESOURCES_LIST request")
            response = MCPMessage(
                id=message.id,
                result={"resources": []}
            )
            logger.debug("✅ RESOURCES_LIST response: empty list")
            return response
            
        elif message.method == MCPMethods.PROMPTS_LIST:
            # List available prompts (none for TICMaker)
            logger.info("💬 Processing PROMPTS_LIST request")
            response = MCPMessage(
                id=message.id,
                result={"prompts": []}
            )
            logger.debug("✅ PROMPTS_LIST response: empty list")
            return response
            
        else:
            # Unknown method
            logger.error(f"❌ Unknown method requested: {message.method}")
            return MCPMessage(
                id=message.id,
                error={
                    "code": MCPErrorCodes.METHOD_NOT_FOUND,
                    "message": f"Unknown method: {message.method}"
                }
            )
    
    async def _create_interactive_course(self, arguments: Dict[str, Any]) -> TICMakerResult:
        """Create interactive course with given arguments."""
        try:
            # Extract arguments with defaults
            user_input = arguments.get("user_input")
            course_title = arguments.get("course_title")
            file_path = arguments.get("file_path")
            template_style = arguments.get("template_style")
            session_context = arguments.get("_session_context")
            
            # Validate required fields
            if not user_input:
                return TICMakerResult(
                    success=False,
                    error="'user_input' field is required"
                )
            
            # Create interactive course
            return await self.ticmaker_client.create_interactive_course(
                user_input=user_input,
                course_title=course_title,
                file_path=file_path,
                template_style=template_style,
                session_context=session_context
            )
            
        except Exception as e:
            logger.error(f"💥 _create_interactive_course error: {str(e)}")
            return TICMakerResult(
                success=False,
                error=f"Course creation failed: {str(e)}"
            )


def load_config() -> TICMakerConfig:
    """Load TICMaker configuration from SimaCode config system."""
    try:
        # Load config from SimaCode
        config = Config.load()
        
        # Extract TICMaker settings
        output_dir = getattr(config, 'ticmaker', {}).get('output_dir', "./ticmaker_output")
        default_template = getattr(config, 'ticmaker', {}).get('default_template', "modern")
        ai_enhancement = getattr(config, 'ticmaker', {}).get('ai_enhancement', False)
        
        # Override with environment variables if present
        output_dir = os.getenv("TICMAKER_OUTPUT_DIR", output_dir)
        default_template = os.getenv("TICMAKER_TEMPLATE", default_template)
        
        return TICMakerConfig(
            output_dir=output_dir,
            default_template=default_template,
            ai_enhancement=ai_enhancement
        )
        
    except Exception as e:
        logger.warning(f"⚠️ Failed to load config from SimaCode: {str(e)}")
        logger.info("📋 Using default configuration")
        
        # Fallback to environment variables and defaults
        return TICMakerConfig(
            output_dir=os.getenv("TICMAKER_OUTPUT_DIR", "./ticmaker_output"),
            default_template=os.getenv("TICMAKER_TEMPLATE", "modern"),
            ai_enhancement=False
        )


async def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="TICMaker stdio MCP Server")
    parser.add_argument("--config", help="Configuration file path")
    parser.add_argument("--output-dir", help="Output directory for generated files")
    parser.add_argument("--template", help="Default template style", choices=["modern", "classic", "minimal"])
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("🐛 Debug logging enabled")
    
    # Load configuration
    ticmaker_config = load_config()
    
    # Override with command line arguments if provided
    if args.output_dir:
        ticmaker_config.output_dir = args.output_dir
    if args.template:
        ticmaker_config.default_template = args.template
    
    logger.info(f"📋 Configuration loaded:")
    logger.info(f"   📂 Output directory: {ticmaker_config.output_dir}")
    logger.info(f"   🎨 Default template: {ticmaker_config.default_template}")
    logger.info(f"   🤖 AI enhancement: {ticmaker_config.ai_enhancement}")
    
    # Create and run server
    server = TICMakerStdioMCPServer(ticmaker_config)
    await server.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped by user.", file=sys.stderr)
    except Exception as e:
        print(f"Server error: {str(e)}", file=sys.stderr)
        sys.exit(1)