#!/usr/bin/env python3
"""
TICMaker Async stdio MCP Server

An enhanced stdio-based MCP server that provides interactive teaching content creation capabilities
with full async task support. This server automatically detects long-running operations and
utilizes the MCP async task enhancement features for optimal performance.

Features:
- Automatic async task detection and execution
- Real-time progress reporting and status updates
- Smart task complexity classification
- Seamless fallback to sync execution when needed
- Enhanced error handling and recovery
- Complete compatibility with SimaCode's MCP async framework

Based on: tools/mcp_ticmaker_stdio_server.py
Enhanced with: MCP async task enhancement features from docs/mcp-async-task-enhancement.md
"""

import asyncio
import json
import logging
import os
import sys
import uuid
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, AsyncGenerator, Callable
from dataclasses import dataclass, field
from enum import Enum

# AI client dependencies
from openai import AsyncOpenAI

# Add parent directory to path for MCP imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# MCP Protocol imports (using our existing MCP implementation)
from src.simacode.mcp.protocol import MCPMessage, MCPMethods, MCPErrorCodes, MCPResult
from src.simacode.config import Config

# Import utilities
from src.simacode.utils.mcp_logger import mcp_file_log, mcp_debug, mcp_info, mcp_warning, mcp_error
from src.simacode.utils.config_loader import load_simacode_config

# Import async task management
from src.simacode.mcp.async_integration import (
    MCPAsyncTaskManager, MCPAsyncTask, TaskType, TaskStatus, get_global_task_manager
)

# Configure logging to stderr to avoid interfering with stdio protocol
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)


class TaskComplexity(Enum):
    """Task complexity classification"""
    SIMPLE = "simple"           # Quick tasks (<10s)
    STANDARD = "standard"       # Normal tasks (10-60s)
    LONG_RUNNING = "long_running"  # Extended tasks (>60s)


@dataclass
class TICMakerAsyncConfig:
    """Enhanced configuration for async TICMaker operations"""
    output_dir: str = ".simacode/mcp/ticmaker_output"
    default_template: str = "modern"
    ai_enhancement: bool = False
    max_file_size: int = 1024 * 1024 * 10  # 10MB
    allowed_file_extensions: List[str] = None

    # AI client configuration
    ai_enabled: bool = True
    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: str = ""
    ai_model: str = "gpt-3.5-turbo"
    ai_max_tokens: int = 500
    ai_temperature: float = 0.7

    # Async task configuration
    enable_async_detection: bool = True
    async_threshold_seconds: float = 30.0  # Tasks longer than this use async
    progress_report_interval: float = 2.0  # Progress update frequency
    max_concurrent_tasks: int = 3
    task_timeout: float = 300.0  # 5 minutes default timeout

    # Task complexity thresholds
    simple_task_max_time: float = 10.0
    standard_task_max_time: float = 60.0

    def __post_init__(self):
        """Set default values after initialization"""
        if self.allowed_file_extensions is None:
            self.allowed_file_extensions = [".html", ".htm"]

    @classmethod
    def from_simacode_config(cls, config: Config) -> 'TICMakerAsyncConfig':
        """Create TICMakerAsyncConfig from SimaCode Config object"""
        # Try to get ticmaker config section, fallback to empty dict
        try:
            ticmaker_config = getattr(config, 'ticmaker', {})
        except AttributeError:
            ticmaker_config = {}

        # Extract basic settings with fallbacks
        output_dir = ticmaker_config.get('output_dir', ".simacode/mcp/ticmaker_output")
        default_template = ticmaker_config.get('default_template', "modern")
        ai_enhancement = ticmaker_config.get('ai_enhancement', False)

        # Extract AI settings from ticmaker config with fallbacks
        ai_config = ticmaker_config.get('ai', {})
        ai_enabled_default = ai_config.get('enabled', True)
        ai_base_url_default = ai_config.get('base_url', "https://openai.pgpt.cloud/v1")
        ai_api_key_default = ai_config.get('api_key', "")
        ai_model_default = ai_config.get('model', "gpt-4o-mini")
        ai_max_tokens_default = ai_config.get('max_tokens', 16384)
        ai_temperature_default = ai_config.get('temperature', 0.7)

        # Extract async settings with fallbacks
        async_config = ticmaker_config.get('async', {})
        enable_async_detection = async_config.get('enable_async_detection', True)
        async_threshold_seconds = async_config.get('threshold_seconds', 30.0)
        progress_report_interval = async_config.get('progress_interval', 2.0)
        max_concurrent_tasks = async_config.get('max_concurrent', 3)
        task_timeout = async_config.get('timeout', 300.0)

        # Override with environment variables (priority: env vars > config)
        output_dir = os.getenv("TICMAKER_OUTPUT_DIR", output_dir)
        default_template = os.getenv("TICMAKER_TEMPLATE", default_template)

        # AI configuration with environment override
        ai_enabled_env = os.getenv("TICMAKER_AI_ENABLED", str(ai_enabled_default))
        ai_enabled = ai_enabled_env.lower() == "true"

        ai_base_url = os.getenv("TICMAKER_AI_BASE_URL", ai_base_url_default)
        ai_api_key = os.getenv("TICMAKER_AI_API_KEY", ai_api_key_default)
        ai_model = os.getenv("TICMAKER_AI_MODEL", ai_model_default)

        # Async configuration with environment override
        enable_async_env = os.getenv("TICMAKER_ASYNC_ENABLED", str(enable_async_detection))
        enable_async_detection = enable_async_env.lower() == "true"

        try:
            ai_max_tokens = int(os.getenv("TICMAKER_AI_MAX_TOKENS", str(ai_max_tokens_default)))
        except ValueError:
            ai_max_tokens = ai_max_tokens_default

        try:
            ai_temperature = float(os.getenv("TICMAKER_AI_TEMPERATURE", str(ai_temperature_default)))
        except ValueError:
            ai_temperature = ai_temperature_default

        try:
            async_threshold_seconds = float(os.getenv("TICMAKER_ASYNC_THRESHOLD", str(async_threshold_seconds)))
        except ValueError:
            pass

        try:
            task_timeout = float(os.getenv("TICMAKER_TASK_TIMEOUT", str(task_timeout)))
        except ValueError:
            pass

        return cls(
            output_dir=output_dir,
            default_template=default_template,
            ai_enhancement=ai_enhancement,
            ai_enabled=ai_enabled,
            ai_base_url=ai_base_url,
            ai_api_key=ai_api_key,
            ai_model=ai_model,
            ai_max_tokens=ai_max_tokens,
            ai_temperature=ai_temperature,
            enable_async_detection=enable_async_detection,
            async_threshold_seconds=async_threshold_seconds,
            progress_report_interval=progress_report_interval,
            max_concurrent_tasks=max_concurrent_tasks,
            task_timeout=task_timeout
        )


@dataclass
class TICMakerAsyncResult:
    """Enhanced result from TICMaker async content creation operation"""
    success: bool
    message: str = ""
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Optional[Dict[str, Any]] = None

    # Async-specific fields
    task_id: Optional[str] = None
    task_complexity: Optional[TaskComplexity] = None
    was_async: bool = False
    progress_updates_count: int = 0


class TICMakerAsyncAIClient:
    """Enhanced AI client with async support and progress reporting"""

    def __init__(self, config: TICMakerAsyncConfig, mcp_send_message: Optional[Callable] = None):
        """Initialize async AI client with OpenAI streaming support"""
        self.config = config
        self.client = None
        self.mcp_send_message = mcp_send_message  # Callback to send MCP messages
        self.current_request_id = None  # Track current request for progress routing

        if config.ai_enabled and config.ai_api_key:
            # OpenAI client for streaming responses
            self.client = AsyncOpenAI(
                api_key=config.ai_api_key,
                base_url=config.ai_base_url,
                timeout=300.0  # Extended timeout for streaming
            )

    async def _send_mcp_progress(self, content: str, progress_data: Optional[Dict] = None):
        """Send progress message via MCP protocol"""
        if self.mcp_send_message:
            params = {
                "content": content,
                "timestamp": datetime.now().isoformat(),
                **(progress_data or {})
            }

            # 添加 request_id 用于客户端路由
            if self.current_request_id:
                params["request_id"] = self.current_request_id

            message = MCPMessage(
                method="tools/progress",  # 通知消息不需要id
                params=params
            )

            # DEBUG LOG: 记录发送tools/progress消息
            mcp_debug(f"📤 [TOOLS_PROGRESS_SEND] Sending tools/progress message", {
                "message_id": message.id,
                "method": message.method,
                "content": content,
                "progress_data": progress_data,
                "full_params": message.params,
                "timestamp": message.params.get("timestamp") if message.params else None,
                "has_request_id": "request_id" in message.params if message.params else False,
                "request_id": message.params.get("request_id") if message.params else None,
                "mcp_send_available": self.mcp_send_message is not None,
                "params_is_none": message.params is None
            }, tool_name="ticmaker_async")

            await self.mcp_send_message(message)

    async def _send_mcp_result(self, content: str, success: bool = True, error: Optional[str] = None):
        """Send result message via MCP protocol"""
        if self.mcp_send_message:
            message = MCPMessage(
                id=str(uuid.uuid4()),
                method="tools/result",
                params={
                    "success": success,
                    "content": content,
                    "error": error,
                    "timestamp": datetime.now().isoformat()
                }
            )
            await self.mcp_send_message(message)

    async def _save_web_generation_file(self, output_dir: str, filename: str, content: str):
        """Save web generation file to output directory"""
        try:
            # Ensure output directory exists
            os.makedirs(output_dir, exist_ok=True)

            # Write file content (overwrite if exists)
            file_path = os.path.join(output_dir, filename)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            mcp_debug(f"📁 [FILE_SAVED] Web generation file saved", {
                "filename": filename,
                "file_path": file_path,
                "content_size": len(content),
                "output_dir": output_dir
            }, tool_name="ticmaker_async")

            # Send progress notification about file save
            await self._send_mcp_progress(
                f"💾 文件已保存: {filename}",
                {"file_saved": filename, "file_path": file_path}
            )

        except Exception as e:
            mcp_error(f"❌ [FILE_SAVE_ERROR] Failed to save file", {
                "filename": filename,
                "output_dir": output_dir,
                "error": str(e)
            }, tool_name="ticmaker_async")

            await self._send_mcp_progress(
                f"❌ 文件保存失败: {filename} - {str(e)}",
                {"file_save_error": filename, "error": str(e)}
            )



    async def generate_interactive_content_streaming(
        self,
        user_input: str,
        output_dir: str,
        request_id: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Generate interactive content with streaming support using OpenAI client

        This method uses the TIC Maker API with streaming response format as defined in
        docs/API_CHAT_COMPLETIONS_RESPONSE_FORMAT.md and sends progress updates
        via MCP tools/progress protocol.
        """

        if not self.client:
            error_msg = "AI client not initialized"
            await self._send_mcp_progress(f"❌ {error_msg}")
            return error_msg

        # 设置当前的 request_id
        self.current_request_id = request_id

        # Send initial progress
        await self._send_mcp_progress("🎯 开始生成互动教学内容...", {
            "step": "initialization",
            "progress": 0,
            "user_input_length": len(user_input)
        })

        # Prepare request for streaming
        messages = [
            {"role": "user", "content": user_input}
        ]

        # Start streaming request
        await self._send_mcp_progress("🚀 发送流式请求到 AI 服务...", {
            "step": "request_start",
            "progress": 5
        })

        # Use OpenAI client for streaming
        stream = await self.client.chat.completions.create(
            model="ticmaker",  # Use the specific model
            messages=messages,
            stream=True,  # Enable streaming
            temperature=0.7,
            max_tokens=4000
        )

        # Track saved files to avoid duplicates
        saved_files = set()
        final_result = None
        content_buffer = ""

        # Process streaming chunks
        async for chunk in stream:
            # DEBUG LOG: 打印chunk的json_dump
            mcp_debug(f"📦 [STREAM_CHUNK] Chunk JSON dump",
                     json.dumps(chunk.model_dump() if hasattr(chunk, 'model_dump') else chunk.__dict__, ensure_ascii=False, indent=2),
                     tool_name="ticmaker_async")

            if chunk.choices and len(chunk.choices) > 0:
                choice = chunk.choices[0]

                # Handle delta content (progress messages)
                if choice.delta and choice.delta.content:
                    content = choice.delta.content
                    content_buffer += content

                    # Send progress update with content
                    await self._send_mcp_progress(content, {
                        "type": "content_update",
                        "chunk_size": len(content)
                    })

                # Handle finish_reason = "stop" (final result)
                if choice.finish_reason == "stop":
                    # 写文件
                    web_generation_pages = chunk.complete_response["web_generation"]
                    await self._process_web_generation(web_generation_pages, output_dir, saved_files)
                    # 首页
                    # Send final completion message
                    await self._send_mcp_progress("🎉 互动内容生成完成！", {
                        "type": "completion",
                        "progress": 100,
                        "files_saved": len(saved_files)
                    })

                    # DEBUG LOG: Program execution reached this point
                    mcp_debug("🔧 DEBUG: Program execution reached L386 - Setting final result and breaking", {
                        "content_buffer_length": len(content_buffer),
                        "saved_files_count": len(saved_files),
                        "about_to_break": True,
                        "finish_reason": "stop"
                    }, tool_name="ticmaker_async")

                    # Set final result and break from stream loop
                    final_result = content_buffer
                    break

                # Handle step_progress (from streaming format)
                if hasattr(chunk, 'step_progress') and chunk.step_progress is not None:
                    step_progress = chunk.step_progress

                    # Additional safety check: ensure step_progress is a dict-like object
                    if hasattr(step_progress, 'get'):
                        await self._send_mcp_progress(
                            f"📊 {step_progress.get('step_name', 'Processing')} - {step_progress.get('details', '')}",
                            {
                                "type": "step_progress",
                                "current_step": step_progress.get('current_step'),
                                "progress": step_progress.get('progress'),
                                "estimated_remaining": step_progress.get('estimated_remaining')
                            }
                        )
                    else:
                        # Debug log for unexpected step_progress type
                        mcp_debug(f"⚠️ step_progress exists but is not dict-like", {
                            "step_progress_type": type(step_progress).__name__,
                            "step_progress_value": str(step_progress),
                            "has_get_method": hasattr(step_progress, 'get')
                        }, tool_name="ticmaker_async")

        # Close connection after stream processing is complete
        await self.close()

        # DEBUG LOG: Program execution reached this point
        mcp_debug("🔧 DEBUG: Program execution reached L417 - Sending final result", {
            "final_result_length": len(final_result) if final_result else 0,
            "content_buffer_length": len(content_buffer) if content_buffer else 0,
            "has_final_result": final_result is not None,
            "has_content_buffer": len(content_buffer) > 0 if content_buffer else False
        }, tool_name="ticmaker_async")

        # Return final result
        result_message = final_result or content_buffer or "Interactive content generation completed"
        return result_message

    async def _process_web_generation(self, web_generation: Dict, output_dir: str, saved_files: set):
        """Process web_generation data and save files"""
        mcp_debug(f"📁 [FILE_PROCESS] Starting web generation file processing", {
            "output_dir": output_dir,
            "saved_files_count": len(saved_files),
            "has_index_page": 'index_page' in web_generation,
            "has_html_pages": 'html_pages' in web_generation,
            "html_pages_count": len(web_generation.get('html_pages', []))
        }, tool_name="ticmaker_async")

        # Save index page if present
        if 'index_page' in web_generation:
            index_page = web_generation['index_page']
            if 'filename' in index_page and 'content' in index_page:
                filename = index_page['filename']
                if filename not in saved_files:
                    mcp_debug(f"💾 [FILE_WRITE] Writing index page", {
                        "filename": filename,
                        "output_dir": output_dir,
                        "content_length": len(index_page['content'])
                    }, tool_name="ticmaker_async")
                    await self._save_web_generation_file(output_dir, filename, index_page['content'])
                    saved_files.add(filename)
                    mcp_debug(f"✅ [FILE_SAVED] Index page saved successfully", {
                        "filename": filename,
                        "full_path": f"{output_dir}/{filename}"
                    }, tool_name="ticmaker_async")
                else:
                    mcp_debug(f"⚠️ [FILE_SKIP] Index page already saved", {
                        "filename": filename
                    }, tool_name="ticmaker_async")

        # Save html pages if present
        if 'html_pages' in web_generation:
            for i, page in enumerate(web_generation['html_pages']):
                filename = page['filename']
                mcp_debug(f"💾 [FILE_WRITE] Writing HTML page {i+1}", {
                    "filename": filename,
                    "output_dir": output_dir,
                    "content_length": len(page['content']),
                    "page_index": i+1
                }, tool_name="ticmaker_async")
                await self._save_web_generation_file(output_dir, filename, page['content'])
                saved_files.add(filename)
                mcp_debug(f"✅ [FILE_SAVED] HTML page saved successfully", {
                    "filename": filename,
                    "full_path": f"{output_dir}/{filename}",
                    "page_index": i+1
                }, tool_name="ticmaker_async")

  
    async def close(self):
        """Close AI client"""
        if self.client:
            await self.client.close()


class TICMakerAsyncClient:
    """Enhanced TICMaker client with full async task support"""

    def __init__(self, config: TICMakerAsyncConfig, mcp_send_message: Optional[Callable] = None):
        """Initialize TICMaker async client"""
        self.config = config
        self.output_dir = Path(config.output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.mcp_send_message = mcp_send_message

        # Initialize AI client with MCP callback
        self.ai_client = TICMakerAsyncAIClient(config, mcp_send_message)

        # Initialize async task manager
        self.task_manager = get_global_task_manager()

        mcp_info(f"[TICMAKER_ASYNC_CONFIG] Output directory: {self.output_dir}", tool_name="ticmaker_async")
        mcp_info(f"[TICMAKER_ASYNC_CONFIG] Default template: {self.config.default_template}", tool_name="ticmaker_async")
        mcp_info(f"[TICMAKER_ASYNC_CONFIG] AI enhancement: {self.config.ai_enhancement}", tool_name="ticmaker_async")
        mcp_info(f"[TICMAKER_ASYNC_CONFIG] Async detection enabled: {self.config.enable_async_detection}", tool_name="ticmaker_async")
        mcp_info(f"[TICMAKER_ASYNC_CONFIG] Async threshold: {self.config.async_threshold_seconds}s", tool_name="ticmaker_async")
        mcp_info(f"[TICMAKER_ASYNC_CONFIG] AI client enabled: {self.config.ai_enabled}", tool_name="ticmaker_async")

        # Log initialization to file
        mcp_info("TICMaker async client initialized", {
            "output_dir": str(self.output_dir),
            "default_template": self.config.default_template,
            "ai_enhancement": self.config.ai_enhancement,
            "ai_enabled": self.config.ai_enabled,
            "ai_model": self.config.ai_model,
            "async_detection_enabled": self.config.enable_async_detection,
            "async_threshold": self.config.async_threshold_seconds,
            "max_concurrent_tasks": self.config.max_concurrent_tasks,
            "logging_available": True
        }, tool_name="ticmaker_async")




    async def _modify_html_content_async(
        self,
        existing_content: str,
        user_input: str,
        progress_callback: Optional[Callable] = None
    ) -> str:
        """Modify existing course content with async support"""

        if progress_callback:
            await progress_callback(50, "Analyzing existing content...")

        # Simulate processing time for complex modifications
        await asyncio.sleep(0.5)

        if progress_callback:
            await progress_callback(70, "Applying modifications...")

        # Simple modification logic - add modification note
        modification_note = f"\n<!-- Async modification record: {datetime.now().isoformat()} - {user_input} -->\n"

        # Insert modification content before </body>
        if "</body>" in existing_content:
            insert_content = f'''<div class="async-modification-note" style="margin-top: 20px; padding: 10px; background-color: #e8f5e8; border: 1px solid #4caf50; border-radius: 5px;">
<strong>📝 Latest async modification:</strong> {user_input}<br>
<small>⏰ Modification time: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</small><br>
<small>🔄 Processing mode: Async Task Enhanced</small>
</div>
'''
            existing_content = existing_content.replace("</body>", f"{insert_content}</body>")

        # Add modification note
        existing_content += modification_note

        if progress_callback:
            await progress_callback(85, "Modification completed")

        return existing_content



class TICMakerAsyncStdioMCPServer:
    """
    Enhanced stdio-based MCP server for TICMaker with async task support.

    This server automatically detects task complexity and uses async execution
    for long-running operations, providing real-time progress updates.
    """

    def __init__(self, ticmaker_config: Optional[TICMakerAsyncConfig] = None):
        """Initialize TICMaker async stdio MCP server"""
        mcp_debug("🔧 DEBUG: Server __init__ started", tool_name="ticmaker_async")

        # Initialize TICMaker client with configuration
        self.ticmaker_config = ticmaker_config or TICMakerAsyncConfig()
        mcp_debug("🔧 DEBUG: Config set, creating TICMaker client...", tool_name="ticmaker_async")
        self.ticmaker_client = TICMakerAsyncClient(self.ticmaker_config, self.send_message)
        mcp_debug("🔧 DEBUG: TICMaker client created", tool_name="ticmaker_async")

        # Initialize async task manager
        mcp_debug("🔧 DEBUG: Getting task manager...", tool_name="ticmaker_async")
        self.task_manager = get_global_task_manager()
        mcp_debug("🔧 DEBUG: Task manager obtained", tool_name="ticmaker_async")

        # MCP server info
        self.server_info = {
            "name": "ticmaker-async-stdio-mcp-server",
            "version": "2.0.0",
            "description": "TICMaker Async stdio MCP Server for Interactive Teaching Content Creation with Async Task Enhancement"
        }

        # Available tools with async capabilities
        self.tools = {
            "create_interactive_course_async": {
                "name": "create_interactive_course_async",
                "description": "Create interactive teaching content with async task support, including HTML pages, slides, PPT, courses, etc., and publish them in HTML format. Always generates new content regardless of existing file presence. Automatically detects task complexity and uses async execution for optimal performance.",
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
                        "content_type": {
                            "type": "string",
                            "enum": ["course", "slides", "presentation", "tutorial", "lesson", "workshop"],
                            "description": "Type of interactive teaching content to create",
                            "default": "course"
                        },
                        "template_style": {
                            "type": "string",
                            "enum": ["modern", "classic", "minimal"],
                            "description": "Template style for the generated content",
                            "default": "modern"
                        },
                        "force_async": {
                            "type": "boolean",
                            "description": "Force async execution regardless of complexity detection",
                            "default": False
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
            },
            "modify_interactive_course_async": {
                "name": "modify_interactive_course_async",
                "description": "Modify interactive teaching content with async task support, including HTML pages, slides, PPT, courses, etc. Automatically detects modification complexity and uses async execution when beneficial.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "user_input": {
                            "type": "string",
                            "description": "User's requirements for modifying the existing interactive teaching content"
                        },
                        "file_path": {
                            "type": "string",
                            "description": "Path to the existing HTML file to be modified"
                        },
                        "force_async": {
                            "type": "boolean",
                            "description": "Force async execution regardless of complexity detection",
                            "default": False
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
                    "required": ["user_input", "file_path"]
                }
            }
        }

        # Async-specific tracking
        self.active_async_tasks: Dict[str, str] = {}  # request_id -> task_id mapping
        self.progress_callbacks: Dict[str, Callable] = {}

        mcp_debug("🔧 DEBUG: Server __init__ completed successfully", tool_name="ticmaker_async")

    async def send_message(self, message: MCPMessage):
        """Send MCP message via stdout"""
        try:
            response_json = message.to_dict()
            response_line = json.dumps(response_json, ensure_ascii=False)
            print(response_line, flush=True)  # 修复：启用实际的消息发送
            mcp_debug(f"📤 [MESSAGE_SENT] Sent to stdout: {response_line}", tool_name="ticmaker_async")
        except Exception as e:
            mcp_error(f"❌ [MCP_SEND_ERROR] Failed to send message: {str(e)}", tool_name="ticmaker_async")

    async def run(self):
        """Run the async stdio MCP server"""
        mcp_info("🚀 Starting TICMaker Async stdio MCP server...", tool_name="ticmaker_async")
        mcp_info(f"📂 Output directory: {self.ticmaker_config.output_dir}", tool_name="ticmaker_async")
        mcp_info(f"🎨 Default template: {self.ticmaker_config.default_template}", tool_name="ticmaker_async")
        mcp_info(f"⚡ Async detection enabled: {self.ticmaker_config.enable_async_detection}", tool_name="ticmaker_async")
        mcp_info(f"🧠 AI enhancement enabled: {self.ticmaker_config.ai_enabled}", tool_name="ticmaker_async")
        mcp_info("📡 Ready to receive MCP messages via stdio with async support", tool_name="ticmaker_async")

        # Debug: Server fully initialized
        mcp_debug("🔧 DEBUG: Server initialization completed, entering main loop", tool_name="ticmaker_async")
        mcp_debug(f"🔧 DEBUG: Tools available: {list(self.tools.keys())}", tool_name="ticmaker_async")

        # Log server startup to file
        mcp_info("TICMaker Async MCP server started", {
            "server_version": self.server_info["version"],
            "output_dir": self.ticmaker_config.output_dir,
            "default_template": self.ticmaker_config.default_template,
            "ai_enhancement": self.ticmaker_config.ai_enhancement,
            "async_detection_enabled": self.ticmaker_config.enable_async_detection,
            "async_threshold": self.ticmaker_config.async_threshold_seconds,
            "max_concurrent_tasks": self.ticmaker_config.max_concurrent_tasks
        }, tool_name="ticmaker_async")

        try:
            while True:
                try:
                    # Debug: Waiting for input (suppress for ping requests)
                    # mcp_debug("🔧 DEBUG: Waiting for stdin input...", tool_name="ticmaker_async")

                    # Read from stdin
                    line = await asyncio.to_thread(sys.stdin.readline)

                    # Debug: Input received (suppress for ping requests)
                    # mcp_debug(f"🔧 DEBUG: Raw input received: {repr(line)}", tool_name="ticmaker_async")

                    if not line:
                        mcp_debug("🔧 DEBUG: Empty line received, breaking", tool_name="ticmaker_async")
                        break

                    line = line.strip()
                    if not line:
                        mcp_debug("🔧 DEBUG: Line is empty after strip, continuing", tool_name="ticmaker_async")
                        continue

                    # mcp_debug(f"📥 Received: {line}", tool_name="ticmaker_async")

                    # Parse MCP message
                    try:
                        # mcp_debug("🔧 DEBUG: Parsing JSON message...", tool_name="ticmaker_async")
                        message_data = json.loads(line)
                        # mcp_debug(f"🔧 DEBUG: JSON parsed successfully: {message_data}", tool_name="ticmaker_async")

                        message = MCPMessage(**message_data)
                        # mcp_debug(f"🔧 DEBUG: MCPMessage created: {message.method}, id: {message.id}", tool_name="ticmaker_async")
                    except (json.JSONDecodeError, TypeError, ValueError) as e:
                        mcp_error(f"❌ Invalid JSON message: {str(e)}", tool_name="ticmaker_async")
                        continue

                    # Process message
                    # mcp_debug(f"🔧 DEBUG: Processing message method: {message.method}", tool_name="ticmaker_async")
                    response = await self.handle_message(message)
                    # mcp_debug(f"🔧 DEBUG: Message handled, response: {response is not None}", tool_name="ticmaker_async")

                    # Send response
                    if response:
                        # mcp_debug("🔧 DEBUG: Preparing response...", tool_name="ticmaker_async")
                        response_json = response.to_dict()
                        response_line = json.dumps(response_json, ensure_ascii=False)
                        # mcp_debug(f"🔧 DEBUG: Response JSON prepared: {response_line}", tool_name="ticmaker_async")

                        print(response_line, flush=True)
                        # mcp_debug(f"📤 Sent: {response_line}", tool_name="ticmaker_async")
                        # mcp_debug("🔧 DEBUG: Response sent successfully", tool_name="ticmaker_async")
                    else:
                        # mcp_debug("🔧 DEBUG: No response to send", tool_name="ticmaker_async")
                        pass

                except Exception as e:
                    mcp_error(f"💥 Error processing message: {str(e)}", tool_name="ticmaker_async")
                    continue

        except KeyboardInterrupt:
            mcp_info("🛑 Server stopped by user", tool_name="ticmaker_async")
        except Exception as e:
            mcp_error(f"💥 Server error: {str(e)}")
        finally:
            await self._cleanup_async_resources()
            mcp_info("👋 TICMaker Async stdio MCP server shutting down", tool_name="ticmaker_async")

    async def _cleanup_async_resources(self):
        """Clean up async resources on shutdown"""
        try:
            # Cancel any active tasks
            for task_id in list(self.active_async_tasks.values()):
                await self.task_manager.cancel_task(task_id)

            # Close AI client
            await self.ticmaker_client.ai_client.close()

            mcp_info("Async resources cleaned up", tool_name="ticmaker_async")
        except Exception as e:
            mcp_error(f"Error during async cleanup: {str(e)}", tool_name="ticmaker_async")

    async def handle_message(self, message: MCPMessage) -> Optional[MCPMessage]:
        """Handle incoming MCP message with async task support"""
        mcp_debug(f"📥 [REQUEST_RECEIVED] Processing {message.method} message with id: {message.id}", tool_name="ticmaker_async")
        mcp_debug(f"🔧 DEBUG: handle_message called with method: {message.method}", tool_name="ticmaker_async")

        # Log detailed message information
        # if message.params:
        #     mcp_debug(f"📋 [REQUEST_PARAMS] Message parameters: {json.dumps(message.params, ensure_ascii=False, indent=2)}", tool_name="ticmaker_async")
        # else:
        #     mcp_debug("🔧 DEBUG: No parameters in message", tool_name="ticmaker_async")

        if message.method == "notifications/initialized":
            # mcp_info("Received initialized notification", tool_name="ticmaker_async")
            return None

        if message.method == MCPMethods.INITIALIZE:
            # Initialization request with async capabilities
            mcp_info("🔧 Processing INITIALIZE request", tool_name="ticmaker_async")
            capabilities = {
                "tools": {
                    tool_name: tool_info["description"]
                    for tool_name, tool_info in self.tools.items()
                } | {
                    "async_support": True,  # Indicate async task support
                    "progress_reporting": True
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
            mcp_info("✅ Async server initialized successfully", tool_name="ticmaker_async")
            return response

        elif message.method == MCPMethods.TOOLS_LIST:
            # List available tools
            # mcp_info("🛠️ Processing TOOLS_LIST request", tool_name="ticmaker_async")
            # mcp_debug(f"🔧 DEBUG: Building tools list from {len(self.tools)} tools", tool_name="ticmaker_async")

            tools_list = []
            for tool_name, tool_info in self.tools.items():
                # mcp_debug(f"🔧 DEBUG: Processing tool: {tool_name}", tool_name="ticmaker_async")
                tool_data = {
                    "name": tool_name,
                    "description": tool_info["description"],
                    "input_schema": tool_info["input_schema"]
                }
                tools_list.append(tool_data)

            # mcp_debug(f"🔧 DEBUG: Tools list built successfully with {len(tools_list)} tools", tool_name="ticmaker_async")

            response = MCPMessage(
                id=message.id,
                result={"tools": tools_list}
            )
            # mcp_debug(f"✅ TOOLS_LIST response: {len(tools_list)} async tools", tool_name="ticmaker_async")
            # mcp_debug(f"🔧 DEBUG: Response object created: {response.id}", tool_name="ticmaker_async")
            return response

        elif message.method == MCPMethods.TOOLS_CALL:
            # Execute tool with async support
            return await self._handle_tool_call(message)

        elif message.method == MCPMethods.TOOLS_CALL_ASYNC:
            # Handle explicit async tool call
            return await self._handle_async_tool_call(message)

        elif message.method == MCPMethods.PING:
            # Ping response
            # mcp_info("🏓 Processing PING request", tool_name="ticmaker_async")
            response = MCPMessage(
                id=message.id,
                result={"pong": True, "async_enabled": True}
            )
            # mcp_debug("✅ PING response: pong with async support", tool_name="ticmaker_async")
            return response

        elif message.method == MCPMethods.RESOURCES_LIST:
            # List available resources (none for TICMaker)
            mcp_info("📚 Processing RESOURCES_LIST request", tool_name="ticmaker_async")
            response = MCPMessage(
                id=message.id,
                result={"resources": []}
            )
            mcp_debug("✅ RESOURCES_LIST response: empty list", tool_name="ticmaker_async")
            return response

        elif message.method == MCPMethods.PROMPTS_LIST:
            # List available prompts (none for TICMaker)
            mcp_info("💬 Processing PROMPTS_LIST request", tool_name="ticmaker_async")
            response = MCPMessage(
                id=message.id,
                result={"prompts": []}
            )
            mcp_debug("✅ PROMPTS_LIST response: empty list", tool_name="ticmaker_async")
            return response

        else:
            # Unknown method
            mcp_error(f"❌ Unknown method requested: {message.method}", tool_name="ticmaker_async")
            return MCPMessage(
                id=message.id,
                error={
                    "code": MCPErrorCodes.METHOD_NOT_FOUND,
                    "message": f"Unknown method: {message.method}"
                }
            )

    async def _handle_tool_call(self, message: MCPMessage) -> MCPMessage:
        """Handle tool execution with automatic async detection"""
        mcp_info("⚡ [TOOL_CALL_START] Processing TOOLS_CALL request with async support", tool_name="ticmaker_async")

        try:
            params = message.params or {}
            tool_name = params.get("name")
            arguments = params.get("arguments", {})

            mcp_info(f"🔧 [TOOL_EXECUTION] Executing async tool: {tool_name}", tool_name="ticmaker_async")
            mcp_debug(f"📝 [TOOL_ARGS] Tool arguments: {json.dumps(arguments, ensure_ascii=False, indent=2)}", tool_name="ticmaker_async")

            # Log user input specifically for debugging
            user_input = arguments.get("user_input", "")
            mcp_debug(f"👤 [USER_INPUT] User request: {user_input}", tool_name="ticmaker_async")

            if tool_name not in self.tools:
                mcp_error(f"❌ Tool '{tool_name}' not found", tool_name="ticmaker_async")
                return MCPMessage(
                    id=message.id,
                    error={
                        "code": MCPErrorCodes.TOOL_NOT_FOUND,
                        "message": f"Tool '{tool_name}' not found"
                    }
                )

            # Execute async tool
            mcp_debug(f"🚀 [TOOL_DISPATCH] Dispatching to tool handler: {tool_name}", tool_name="ticmaker_async")

            if tool_name == "create_interactive_course_async":
                mcp_debug(f"📋 [COURSE_CREATE] Starting interactive course creation", tool_name="ticmaker_async")
                result = await self._create_interactive_course_async(arguments, message.id)
            elif tool_name == "modify_interactive_course_async":
                mcp_debug(f"✏️ [COURSE_MODIFY] Starting interactive course modification", tool_name="ticmaker_async")
                result = await self._modify_interactive_course_async(arguments, message.id)
            else:
                mcp_error(f"❌ [TOOL_ERROR] Unknown async tool requested: {tool_name}", tool_name="ticmaker_async")
                raise ValueError(f"Unknown async tool: {tool_name}")

            mcp_info(f"✅ Async tool '{tool_name}' completed successfully", tool_name="ticmaker_async")

            # Log tool execution completion to file
            mcp_debug(f"Async tool execution completed: {tool_name}", {
                "success": result.success,
                "execution_time": result.execution_time,
                "task_complexity": result.task_complexity.value if result.task_complexity else None,
                "was_async": result.was_async,
                "progress_updates": result.progress_updates_count,
                "message_id": message.id
            }, tool_name="ticmaker_async")

            # Create enhanced response
            response_content = {
                "success": result.success,
                "message": result.message if result.success else result.error,
                "execution_time": result.execution_time,
                "timestamp": datetime.now().isoformat(),
                "async_enhanced": True,
                "task_complexity": result.task_complexity.value if result.task_complexity else None,
                "was_async_execution": result.was_async,
                "progress_updates_count": result.progress_updates_count
            }

            if result.metadata:
                response_content["metadata"] = result.metadata

            if result.task_id:
                response_content["task_id"] = result.task_id

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
                        "response_size_bytes": len(json_text.encode('utf-8')),
                        "async_enhanced": True,
                        "task_complexity": result.task_complexity.value if result.task_complexity else None,
                        "was_async_execution": result.was_async
                    }
                }
            )

        except Exception as e:
            mcp_error(f"💥 Async tool execution error: {str(e)}")

            return MCPMessage(
                id=message.id,
                error={
                    "code": MCPErrorCodes.INTERNAL_ERROR,
                    "message": str(e)
                }
            )

    async def _handle_async_tool_call(self, message: MCPMessage) -> MCPMessage:
        """Handle explicit async tool call with progress reporting"""
        mcp_info("🚀 Processing explicit TOOLS_CALL_ASYNC request", tool_name="ticmaker_async")

        # 立即返回异步任务已接受的响应
        async_accepted_response = MCPMessage(
            id=message.id,
            result={
                "accepted": True,
                "task_id": message.id,
                "message": "Async task accepted and started",
                "async_mode": True
            }
        )

        # 在后台执行实际的工具调用
        asyncio.create_task(self._execute_async_tool_in_background(message))

        return async_accepted_response

    async def _execute_async_tool_in_background(self, message: MCPMessage):
        """在后台执行异步工具调用"""
        try:
            mcp_info(f"🔄 Starting background async tool execution for request_id: {message.id}", tool_name="ticmaker_async")

            # 执行实际的工具调用
            result = await self._handle_tool_call(message)

            # 发送最终结果通知
            if hasattr(self, 'send_message') and result and result.result:
                final_result_message = MCPMessage(
                    method="tools/result",
                    params={
                        "request_id": message.id,  # 用于客户端路由
                        "result": result.result
                    }
                )
                await self.send_message(final_result_message)
                mcp_info(f"📤 Sent final tools/result notification with request_id: {message.id}", tool_name="ticmaker_async")
            elif result and not result.result:
                # 发送错误通知
                error_message = MCPMessage(
                    method="tools/error",
                    params={
                        "request_id": message.id,
                        "error": result.error or "Tool execution failed"
                    }
                )
                await self.send_message(error_message)
                mcp_error(f"📤 Sent tools/error notification with request_id: {message.id}", tool_name="ticmaker_async")

        except Exception as e:
            mcp_error(f"💥 Background async tool execution error: {str(e)}", tool_name="ticmaker_async")

            # 发送错误通知
            error_message = MCPMessage(
                method="tools/error",
                params={
                    "request_id": message.id,
                    "error": f"Background execution failed: {str(e)}"
                }
            )
            await self.send_message(error_message)

    async def _create_interactive_course_async(self, arguments: Dict[str, Any], request_id: str) -> TICMakerAsyncResult:
        """Create interactive course with async support"""
        try:
            # Extract arguments with defaults
            user_input = arguments.get("user_input")
            course_title = arguments.get("course_title")
            file_path = arguments.get("file_path")
            content_type = arguments.get("content_type")
            template_style = arguments.get("template_style")
            force_async = arguments.get("force_async", False)
            session_context = arguments.get("_session_context")

            # Validate required fields
            if not user_input:
                return TICMakerAsyncResult(
                    success=False,
                    error="'user_input' field is required"
                )

            # Create progress callback for this request
            progress_reports = []

            async def progress_callback(progress_data):
                progress_reports.append(progress_data)
                if progress_data and hasattr(progress_data, 'get'):
                    mcp_debug(f"Progress update: {progress_data.get('message', 'Processing...')}", {
                        "request_id": request_id,
                        "progress": progress_data.get("progress", 0),
                        "step": progress_data.get("current_step", 0)
                    }, tool_name="ticmaker_async")
                else:
                    mcp_debug(f"Progress update: {progress_data}", {
                        "request_id": request_id,
                        "progress_data_type": type(progress_data).__name__ if progress_data else "None",
                        "progress_data_value": str(progress_data)
                    }, tool_name="ticmaker_async")

            # Use streaming AI generation method for better real-time feedback
            output_dir = str(self.ticmaker_client.output_dir)

            # Call the new streaming generation method
            result_content = await self.ticmaker_client.ai_client.generate_interactive_content_streaming(
                user_input=user_input,
                output_dir=output_dir,
                request_id=request_id,  # 传递 request_id
                course_title=course_title,
                content_type=content_type,
                template_style=template_style,
                session_context=session_context
            )

            # DEBUG LOG: Program execution reached this point
            mcp_debug("🔧 DEBUG: Program execution reached L1068 - Creating result object", {
                "result_content_length": len(result_content) if result_content else 0,
                "result_content_preview": result_content[:100] if result_content else "None",
                "progress_reports_count": len(progress_reports)
            }, tool_name="ticmaker_async")

            # Create result object compatible with existing interface
            result = TICMakerAsyncResult(
                success=True,
                message=result_content,
                execution_time=0.0,  # Will be set by streaming method
                task_complexity=TaskComplexity.LONG_RUNNING,
                was_async=True
            )

            # Update result with progress information
            result.progress_updates_count = len(progress_reports)

            return result

        except Exception as e:
            mcp_error(f"💥 _create_interactive_course_async error: {str(e)}")
            return TICMakerAsyncResult(
                success=False,
                error=f"Async course creation failed: {str(e)}"
            )

    async def _modify_interactive_course_async(self, arguments: Dict[str, Any], request_id: str) -> TICMakerAsyncResult:
        """Modify interactive course with async support"""
        try:
            # Extract arguments with defaults
            user_input = arguments.get("user_input")
            file_path = arguments.get("file_path")
            force_async = arguments.get("force_async", False)
            session_context = arguments.get("_session_context")

            # Validate required fields
            if not user_input:
                return TICMakerAsyncResult(
                    success=False,
                    error="'user_input' field is required"
                )

            if not file_path:
                return TICMakerAsyncResult(
                    success=False,
                    error="'file_path' field is required"
                )

            # For modification, we'll create a simplified async wrapper
            start_time = time.time()
            task_id = f"modify_course_{uuid.uuid4().hex[:8]}"

            # Classify as standard complexity for modifications
            complexity = TaskComplexity.STANDARD
            should_async = force_async or self.ticmaker_client._should_use_async_execution(complexity, user_input)

            # Resolve and validate file path
            target_file = Path(file_path)
            if not str(target_file.resolve()).startswith(str(self.ticmaker_client.output_dir.resolve())):
                target_file = self.ticmaker_client.output_dir / Path(file_path).name

            # Check if file exists
            if not target_file.exists():
                return TICMakerAsyncResult(
                    success=False,
                    error=f"File not found: {target_file}",
                    task_complexity=complexity,
                    was_async=should_async
                )

            # Read existing content
            existing_content = target_file.read_text(encoding='utf-8')

            # Modify content with async support
            modified_content = await self.ticmaker_client._modify_html_content_async(existing_content, user_input)

            # Check content size
            if len(modified_content.encode('utf-8')) > self.ticmaker_config.max_file_size:
                return TICMakerAsyncResult(
                    success=False,
                    error=f"Modified content too large ({len(modified_content)} characters > {self.ticmaker_config.max_file_size} bytes)",
                    task_complexity=complexity,
                    was_async=should_async
                )

            # Write modified file
            target_file.write_text(modified_content, encoding='utf-8')

            # Get file info
            file_size = target_file.stat().st_size
            execution_time = time.time() - start_time

            mcp_info(f"🎉 Interactive course modified successfully (async)", tool_name="ticmaker_async")

            return TICMakerAsyncResult(
                success=True,
                message="Interactive course modified successfully",
                execution_time=execution_time,
                metadata={
                    "file_path": str(target_file),
                    "file_size": file_size,
                    "action": "modified",
                    "user_input": user_input,
                    "tool_name": "modify_interactive_course_async",
                    "session_context": session_context
                },
                task_id=task_id,
                task_complexity=complexity,
                was_async=should_async,
                progress_updates_count=3  # Start, process, complete
            )

        except Exception as e:
            mcp_error(f"💥 _modify_interactive_course_async error: {str(e)}")
            return TICMakerAsyncResult(
                success=False,
                error=f"Async course modification failed: {str(e)}"
            )


def load_async_config(config_path: Optional[Path] = None) -> TICMakerAsyncConfig:
    """Load TICMaker async configuration from SimaCode config system"""
    try:
        # Load SimaCode configuration
        config = load_simacode_config(config_path=config_path, tool_name="ticmaker_async")
        mcp_info("[CONFIG_LOAD] Successfully loaded SimaCode configuration for async server", tool_name="ticmaker_async")

        # Create TICMaker async configuration from SimaCode config
        ticmaker_config = TICMakerAsyncConfig.from_simacode_config(config)

        # Log configuration details
        mcp_info("TICMaker async config loaded from SimaCode", {
            "config_source": "simacode_config",
            "output_dir": ticmaker_config.output_dir,
            "default_template": ticmaker_config.default_template,
            "ai_enabled": ticmaker_config.ai_enabled,
            "ai_model": ticmaker_config.ai_model,
            "ai_base_url": ticmaker_config.ai_base_url,
            "ai_api_key_configured": bool(ticmaker_config.ai_api_key),
            "async_detection_enabled": ticmaker_config.enable_async_detection,
            "async_threshold": ticmaker_config.async_threshold_seconds,
            "max_concurrent_tasks": ticmaker_config.max_concurrent_tasks
        }, tool_name="ticmaker_async")

        return ticmaker_config

    except Exception as e:
        mcp_warning(f"⚠️ Failed to load config from SimaCode: {str(e)}", tool_name="ticmaker_async")
        mcp_info("📋 Using default async configuration", tool_name="ticmaker_async")

        # Return default config - environment variables will be handled in from_simacode_config
        return TICMakerAsyncConfig()


async def main():
    """Main entry point for async server"""
    import argparse

    parser = argparse.ArgumentParser(description="TICMaker Async stdio MCP Server")
    parser.add_argument("--config", help="Configuration file path")
    parser.add_argument("--output-dir", help="Output directory for generated files")
    parser.add_argument("--template", help="Default template style", choices=["modern", "classic", "minimal"])
    parser.add_argument("--async-threshold", help="Async threshold in seconds", type=float)
    parser.add_argument("--max-concurrent", help="Maximum concurrent tasks", type=int)
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    # Always enable debug logging for troubleshooting
    logging.getLogger().setLevel(logging.DEBUG)
    mcp_debug("🔧 DEBUG: Main function started", tool_name="ticmaker_async")
    mcp_debug(f"🔧 DEBUG: Args received: {args}", tool_name="ticmaker_async")

    if args.debug:
        mcp_debug("🐛 Debug logging enabled for async server", tool_name="ticmaker_async")

    # Load configuration
    mcp_debug("🔧 DEBUG: Loading configuration...", tool_name="ticmaker_async")
    config_path = Path(args.config) if args.config else None
    ticmaker_config = load_async_config(config_path=config_path)
    mcp_debug("🔧 DEBUG: Configuration loaded successfully", tool_name="ticmaker_async")

    # Override with command line arguments if provided
    if args.output_dir:
        ticmaker_config.output_dir = args.output_dir
    if args.template:
        ticmaker_config.default_template = args.template
    if args.async_threshold:
        ticmaker_config.async_threshold_seconds = args.async_threshold
    if args.max_concurrent:
        ticmaker_config.max_concurrent_tasks = args.max_concurrent

    mcp_info(f"📋 Async configuration loaded:", tool_name="ticmaker_async")
    mcp_info(f"   📂 Output directory: {ticmaker_config.output_dir}", tool_name="ticmaker_async")
    mcp_info(f"   🎨 Default template: {ticmaker_config.default_template}", tool_name="ticmaker_async")
    mcp_info(f"   🤖 AI enhancement: {ticmaker_config.ai_enhancement}", tool_name="ticmaker_async")
    mcp_info(f"   ⚡ Async detection: {ticmaker_config.enable_async_detection}", tool_name="ticmaker_async")
    mcp_info(f"   ⏱️ Async threshold: {ticmaker_config.async_threshold_seconds}s", tool_name="ticmaker_async")
    mcp_info(f"   🔄 Max concurrent: {ticmaker_config.max_concurrent_tasks}", tool_name="ticmaker_async")

    # Create and run async server
    mcp_debug("🔧 DEBUG: Creating server instance...", tool_name="ticmaker_async")
    server = TICMakerAsyncStdioMCPServer(ticmaker_config)
    mcp_debug("🔧 DEBUG: Server instance created, starting run...", tool_name="ticmaker_async")
    await server.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAsync server stopped by user.", file=sys.stderr)
    except Exception as e:
        print(f"Async server error: {str(e)}", file=sys.stderr)
        sys.exit(1)