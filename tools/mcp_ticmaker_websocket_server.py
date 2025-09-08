#!/usr/bin/env python3
"""
TICMaker WebSocket MCP Server

A WebSocket-based MCP server that provides interactive teaching content creation capabilities.
This server runs independently and communicates with SimaCode via WebSocket protocol.

Features:
- WebSocket-based MCP server
- Interactive HTML page creation and modification
- AI-enhanced content generation (optional)
- Support for multiple template types
- Asynchronous file I/O operations
"""

import asyncio
import json
import logging
import sys
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

# WebSocket server support
try:
    from aiohttp import web, WSMsgType
    from aiohttp.web import Request, Response, WebSocketResponse
except ImportError:
    print("Error: aiohttp package not available. Please install with: pip install aiohttp", file=sys.stderr)
    sys.exit(1)

# Add parent directory to path for MCP imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# MCP Protocol imports
from src.simacode.mcp.protocol import MCPMessage, MCPMethods, MCPErrorCodes

# AI client imports (optional)
try:
    import openai
except ImportError:
    openai = None
    
try:
    import anthropic
except ImportError:
    anthropic = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger(__name__)


class TICMakerWebSocketServer:
    """WebSocket-based TICMaker MCP Server for interactive teaching content creation."""
    
    def __init__(self, host: str = "localhost", port: int = 10002, output_dir: str = "./ticmaker_output"):
        """
        Initialize TICMaker WebSocket MCP server.
        
        Args:
            host: Server host address
            port: Server port number
            output_dir: Directory for generated HTML files
        """
        self.host = host
        self.port = port
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        self.app = web.Application()
        
        # Setup routes
        self._setup_routes()
        
        # MCP server info
        self.server_info = {
            "name": "ticmaker-websocket-server",
            "version": "1.0.0",
            "description": "TICMaker WebSocket MCP Server for Interactive Teaching Content Creation"
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
                            "description": "Title of the course or lesson (optional)"
                        },
                        "file_path": {
                            "type": "string",
                            "description": "Optional file path for the output HTML file"
                        }
                    },
                    "required": ["user_input"]
                }
            }
        }
        
        logger.info(f"TICMaker WebSocket MCP Server initialized on {host}:{port}")
        logger.info(f"Output directory: {self.output_dir}")
    
    def _setup_routes(self):
        """Setup HTTP routes for MCP protocol."""
        self.app.router.add_get('/health', self._health_check)
        self.app.router.add_post('/mcp', self._handle_mcp_request)
        self.app.router.add_get('/mcp/ws', self._handle_websocket)
        
    async def _health_check(self, request: Request) -> Response:
        """Health check endpoint."""
        health_data = {
            "status": "healthy",
            "server": self.server_info,
            "output_directory": str(self.output_dir),
            "timestamp": datetime.now().isoformat()
        }
        return web.json_response(health_data)
    
    async def _handle_mcp_request(self, request: Request) -> Response:
        """Handle HTTP-based MCP requests."""
        try:
            # Parse request
            request_data = await request.json()
            mcp_message = MCPMessage.from_dict(request_data)
            
            logger.info(f"Received MCP request: {mcp_message.method}")
            
            # Process MCP message
            response = await self._process_mcp_message(mcp_message)
            
            # Handle notifications (no response needed)
            if response is None:
                return web.Response(status=204)  # No Content
            
            return web.json_response(response.to_dict())
            
        except Exception as e:
            logger.error(f"Error handling MCP request: {str(e)}")
            
            error_response = MCPMessage(
                id=request_data.get("id") if 'request_data' in locals() else None,
                error={
                    "code": MCPErrorCodes.INTERNAL_ERROR,
                    "message": str(e)
                }
            )
            
            return web.json_response(error_response.to_dict())
    
    async def _handle_websocket(self, request: Request) -> WebSocketResponse:
        """Handle WebSocket-based MCP connections."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        logger.info("WebSocket connection established")
        
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        # Parse MCP message
                        request_data = json.loads(msg.data)
                        mcp_message = MCPMessage.from_dict(request_data)
                        
                        # Process message
                        response = await self._process_mcp_message(mcp_message)
                        
                        # Send response (only if not None - notifications don't need responses)
                        if response is not None:
                            await ws.send_str(response.to_json())
                        
                    except Exception as e:
                        logger.error(f"Error processing WebSocket message: {str(e)}")
                        
                        # Try to extract request ID for error response
                        request_id = None
                        try:
                            if 'request_data' in locals():
                                request_id = request_data.get("id")
                        except:
                            pass
                        
                        error_response = MCPMessage(
                            id=request_id,
                            error={
                                "code": MCPErrorCodes.INTERNAL_ERROR,
                                "message": str(e)
                            }
                        )
                        
                        await ws.send_str(error_response.to_json())
                        
                elif msg.type == WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {ws.exception()}")
                    break
                    
        except Exception as e:
            logger.error(f"WebSocket connection error: {str(e)}")
        finally:
            logger.info("WebSocket connection closed")
        
        return ws
    
    async def _process_mcp_message(self, message: MCPMessage) -> Optional[MCPMessage]:
        """Process an MCP message and return response (None for notifications)."""
        
        # Handle notifications (no response needed)
        if message.method == "notifications/initialized":
            logger.info("Received initialized notification")
            return None
        
        if message.method == MCPMethods.INITIALIZE:
            # Handle initialization
            return MCPMessage(
                id=message.id,
                result={
                    "serverInfo": self.server_info,
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"subscribe": False, "listChanged": False}
                    }
                }
            )
            
        elif message.method == MCPMethods.TOOLS_LIST:
            # List available tools
            tools_list = list(self.tools.values())
            return MCPMessage(
                id=message.id,
                result={"tools": tools_list}
            )
            
        elif message.method == MCPMethods.TOOLS_CALL:
            # Execute tool
            tool_name = message.params.get("name")
            arguments = message.params.get("arguments", {})
            
            logger.info(f"Calling tool: {tool_name}")
            
            try:
                if tool_name == "create_interactive_course":
                    result = await self._create_interactive_course(arguments)
                    return MCPMessage(
                        id=message.id,
                        result={"content": result}
                    )
                else:
                    return MCPMessage(
                        id=message.id,
                        error={
                            "code": MCPErrorCodes.METHOD_NOT_FOUND,
                            "message": f"Unknown tool: {tool_name}"
                        }
                    )
                    
            except Exception as e:
                logger.error(f"Tool execution error: {str(e)}")
                return MCPMessage(
                    id=message.id,
                    error={
                        "code": MCPErrorCodes.INTERNAL_ERROR,
                        "message": f"Tool execution failed: {str(e)}"
                    }
                )
        else:
            # Unknown method
            return MCPMessage(
                id=message.id,
                error={
                    "code": MCPErrorCodes.METHOD_NOT_FOUND,
                    "message": f"Unknown method: {message.method}"
                }
            )
    
    async def _create_interactive_course(self, args: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Create interactive teaching content."""
        user_input = args.get("user_input", "")
        course_title = args.get("course_title", "")
        file_path = args.get("file_path")
        
        # Log request details
        logger.info("=" * 80)
        logger.info("🎯 TICMaker - Interactive Teaching Course Creation Request")
        logger.info(f"💬 User Requirements: {user_input}")
        logger.info(f"📄 Course Title: {course_title or 'Not specified'}")
        logger.info(f"📁 File Path: {file_path or 'Auto-generate'}")
        logger.info("=" * 80)
        
        if not file_path:
            # Generate default filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            random_id = str(uuid.uuid4())[:8]
            filename = f"ticmaker_page_{timestamp}_{random_id}.html"
            file_path = self.output_dir / filename
        else:
            file_path = Path(file_path)
            # Ensure file is in safe directory
            if not str(file_path).startswith(str(self.output_dir)):
                file_path = self.output_dir / Path(file_path).name
        
        try:
            # Check if modifying existing file
            loop = asyncio.get_event_loop()
            file_exists = await loop.run_in_executor(None, lambda: file_path.exists())
            
            if file_exists:
                # Read existing content and modify
                existing_content = await loop.run_in_executor(None, lambda: file_path.read_text(encoding='utf-8'))
                html_content = await self._modify_html_content(existing_content, user_input)
            else:
                # Create new page
                html_content = await self._generate_html_content(user_input, course_title)
            
            # Determine operation type
            action = "Modified" if file_exists else "Created"
            
            # Write file using executor to avoid blocking event loop
            await loop.run_in_executor(None, lambda: file_path.write_text(html_content, encoding='utf-8'))
            
            # Get file size
            file_size = await loop.run_in_executor(None, lambda: file_path.stat().st_size)
            
            # Log success
            result_msg = f"✅ Interactive course {action.lower()} successfully"
            logger.info(f"\n{result_msg}")
            logger.info(f"File path: {file_path}")
            logger.info(f"File size: {file_size} bytes")
            
            return [
                {
                    "type": "text",
                    "text": f"{result_msg}\n"
                           f"File path: {file_path}\n"
                           f"File size: {file_size} bytes\n"
                           f"User requirements: {user_input}"
                }
            ]
            
        except Exception as e:
            error_msg = f"❌ Interactive course creation failed: {str(e)}"
            logger.error(f"\n{error_msg}")
            logger.error(f"Interactive course creation error: {e}")
            
            return [
                {
                    "type": "text", 
                    "text": error_msg
                }
            ]
    
    async def _generate_html_content(self, user_input: str, course_title: str = "") -> str:
        """Generate HTML content for interactive course."""
        # Extract title from user input if not provided
        title = course_title if course_title else self._extract_title_from_user_input(user_input)
        
        # Generate interactive template
        html_content = self._generate_interactive_template(title, user_input, "modern", course_title)
        
        return html_content
    
    async def _modify_html_content(self, existing_content: str, user_input: str) -> str:
        """Modify existing course content."""
        # Simple modification logic - add modification note
        modification_note = f"\n<!-- Modification record: {datetime.now().isoformat()} - {user_input} -->\n"
        
        # Insert modification content before </body>
        if "</body>" in existing_content:
            insert_content = f'<div class="modification-note" style="margin-top: 20px; padding: 10px; background-color: #f0f8ff; border: 1px solid #ccc;">\n<strong>Latest modification:</strong> {user_input}\n<small>Modification time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</small>\n</div>\n'
            existing_content = existing_content.replace("</body>", f"{insert_content}</body>")
        
        # Add modification note
        existing_content += modification_note
        
        return existing_content
    
    def _extract_title_from_user_input(self, user_input: str) -> str:
        """Extract title from user input."""
        # Smart title extraction logic
        user_input_lower = user_input.lower()
        
        # Detect specific content types
        if any(keyword in user_input_lower for keyword in ["游戏", "小游戏", "互动游戏"]):
            return "Interactive Teaching Game"
        elif any(keyword in user_input_lower for keyword in ["活动", "练习", "训练"]):
            return "Teaching Activity Page"
        elif any(keyword in user_input_lower for keyword in ["课程", "课堂", "教学"]):
            return "Course Content Page"
        elif any(keyword in user_input_lower for keyword in ["测验", "考试", "测试"]):
            return "Online Quiz Page"
        elif any(keyword in user_input_lower for keyword in ["演示", "展示", "介绍"]):
            return "Content Display Page"
        
        return "Interactive Learning Page"
    
    def _generate_interactive_template(self, title: str, user_input: str, style: str, course_title: str = "") -> str:
        """Generate interactive HTML template."""
        return f"""<!DOCTYPE html>
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
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }}
        
        .game-container {{
            background: white;
            border-radius: 20px;
            padding: 40px;
            max-width: 800px;
            width: 100%;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            text-align: center;
        }}
        
        h1 {{
            color: #333;
            margin-bottom: 10px;
            font-size: 2.5em;
        }}
        
        h2 {{
            color: #666;
            margin-bottom: 30px;
            font-weight: normal;
        }}
        
        .interaction-area {{
            margin: 40px 0;
        }}
        
        .interactive-button {{
            background: linear-gradient(45deg, #ff6b6b, #4ecdc4);
            color: white;
            border: none;
            padding: 15px 30px;
            font-size: 18px;
            border-radius: 25px;
            cursor: pointer;
            transition: transform 0.3s ease;
            margin: 10px;
        }}
        
        .interactive-button:hover {{
            transform: translateY(-3px);
            box-shadow: 0 10px 20px rgba(0, 0, 0, 0.2);
        }}
        
        .content-area {{
            margin: 30px 0;
            padding: 20px;
            background-color: #f8f9ff;
            border-radius: 10px;
            border-left: 5px solid #4ecdc4;
        }}
        
        .footer {{
            margin-top: 40px;
            color: #888;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="game-container">
        <h1>{title}</h1>
        {f'<h2>📚 Course: {course_title}</h2>' if course_title else ''}
        <p><strong>User Requirements:</strong> {user_input}</p>
        
        <div class="interaction-area">
            <button class="interactive-button" onclick="showMessage('Great! You are experiencing interactive content created by TICMaker!')">Click to Interact</button>
            <button class="interactive-button" onclick="showQuiz()">Start Quiz</button>
            <button class="interactive-button" onclick="showInfo()">Course Info</button>
        </div>
        
        <div class="content-area" id="dynamic-content">
            <p>🎯 Welcome to the TICMaker interactive learning platform!</p>
            <p>This content was automatically generated based on your requirements and can be further customized.</p>
        </div>
        
        <div class="footer">
            <p>Generated by TICMaker - Interactive Teaching Content Creator</p>
            <p>Creation time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
    </div>

    <script>
        function showMessage(message) {{
            const contentArea = document.getElementById('dynamic-content');
            contentArea.innerHTML = `
                <h3>🎉 Interactive Response</h3>
                <p>${{message}}</p>
                <p>Click other buttons to explore more features!</p>
            `;
            contentArea.style.background = '#e8f5e8';
        }}
        
        function showQuiz() {{
            const contentArea = document.getElementById('dynamic-content');
            contentArea.innerHTML = `
                <h3>📝 Quick Quiz</h3>
                <p><strong>Question:</strong> What is the main purpose of TICMaker?</p>
                <div style="margin: 20px 0;">
                    <button onclick="checkAnswer(true)" style="margin: 5px; padding: 10px 15px;">Creating interactive teaching content</button>
                    <button onclick="checkAnswer(false)" style="margin: 5px; padding: 10px 15px;">Playing games</button>
                    <button onclick="checkAnswer(false)" style="margin: 5px; padding: 10px 15px;">Writing documents</button>
                </div>
            `;
            contentArea.style.background = '#fff3cd';
        }}
        
        function checkAnswer(correct) {{
            const contentArea = document.getElementById('dynamic-content');
            if (correct) {{
                contentArea.innerHTML = `
                    <h3>✅ Correct!</h3>
                    <p>TICMaker is indeed designed for creating interactive teaching content!</p>
                    <p>You can use it to generate various types of educational materials.</p>
                `;
                contentArea.style.background = '#d4edda';
            }} else {{
                contentArea.innerHTML = `
                    <h3>❌ Not quite right</h3>
                    <p>TICMaker is specifically designed for creating interactive teaching content.</p>
                    <p>Try again to learn more!</p>
                    <button onclick="showQuiz()" style="margin-top: 10px; padding: 8px 15px;">Try Again</button>
                `;
                contentArea.style.background = '#f8d7da';
            }}
        }}
        
        function showInfo() {{
            const contentArea = document.getElementById('dynamic-content');
            contentArea.innerHTML = `
                <h3>ℹ️ Course Information</h3>
                <p><strong>Course Requirements:</strong> {user_input}</p>
                <p><strong>Generated Template:</strong> Interactive Template</p>
                <p><strong>Features:</strong></p>
                <ul style="text-align: left; margin: 10px 0;">
                    <li>Interactive buttons and responses</li>
                    <li>Quiz functionality</li>
                    <li>Dynamic content updates</li>
                    <li>Modern responsive design</li>
                </ul>
            `;
            contentArea.style.background = '#cce7ff';
        }}
    </script>
</body>
</html>"""
    
    async def start_server(self):
        """Start the WebSocket server."""
        logger.info(f"Starting TICMaker WebSocket MCP Server on {self.host}:{self.port}")
        
        try:
            runner = web.AppRunner(self.app)
            await runner.setup()
            
            site = web.TCPSite(runner, self.host, self.port)
            await site.start()
            
            logger.info(f"✅ TICMaker WebSocket MCP Server started successfully")
            logger.info(f"🔗 WebSocket endpoint: ws://{self.host}:{self.port}/mcp/ws")
            logger.info(f"🏥 Health check: http://{self.host}:{self.port}/health")
            
            # Keep the server running
            while True:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Failed to start server: {str(e)}")
            raise


async def main():
    """Main entry point for the server."""
    import argparse
    
    parser = argparse.ArgumentParser(description="TICMaker WebSocket MCP Server")
    parser.add_argument("--host", default="localhost", help="Server host (default: localhost)")
    parser.add_argument("--port", type=int, default=10002, help="Server port (default: 10002)")
    parser.add_argument("--output-dir", default="./ticmaker_output", help="Output directory for generated files")
    
    args = parser.parse_args()
    
    # Create and start server
    server = TICMakerWebSocketServer(
        host=args.host,
        port=args.port,
        output_dir=args.output_dir
    )
    
    try:
        await server.start_server()
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())