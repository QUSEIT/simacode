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
import random
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, AsyncGenerator, Callable
from dataclasses import dataclass, field
from enum import Enum

# AI client dependencies
import httpx

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


class AsyncTaskProgress:
    """Progress tracking for async tasks"""

    def __init__(self, task_id: str, total_steps: int = 100):
        self.task_id = task_id
        self.total_steps = total_steps
        self.current_step = 0
        self.start_time = time.time()
        self.last_update = self.start_time
        self.message = "Starting task..."
        self.metadata = {}

    def update(self, step: int, message: str, metadata: Optional[Dict[str, Any]] = None):
        """Update progress information"""
        self.current_step = min(step, self.total_steps)
        self.message = message
        self.last_update = time.time()
        if metadata:
            self.metadata.update(metadata)

    def get_progress_data(self) -> Dict[str, Any]:
        """Get current progress data"""
        elapsed = time.time() - self.start_time
        progress_percent = (self.current_step / self.total_steps) * 100

        return {
            "task_id": self.task_id,
            "progress": progress_percent,
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "message": self.message,
            "elapsed_time": elapsed,
            "timestamp": time.time(),
            "metadata": self.metadata
        }


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

    def __init__(self, config: TICMakerAsyncConfig):
        """Initialize async AI client"""
        self.config = config
        self.client = None
        if config.ai_enabled and config.ai_api_key:
            self.client = httpx.AsyncClient(
                base_url=config.ai_base_url,
                headers={"Authorization": f"Bearer {config.ai_api_key}"},
                timeout=30.0
            )

    async def generate_course_intro_async(
        self,
        course_title: str,
        user_input: str,
        progress_callback: Optional[Callable] = None
    ) -> str:
        """Generate course introduction with async support and progress reporting"""

        mcp_debug(f"🤖 [AI_CALL_START] Starting AI course intro generation", {
            "course_title": course_title,
            "user_input_length": len(user_input),
            "user_input_preview": user_input[:100] + "..." if len(user_input) > 100 else user_input,
            "ai_client_available": self.client is not None,
            "ai_config": {
                "enabled": self.config.ai_enabled,
                "base_url": self.config.ai_base_url,
                "model": self.config.ai_model,
                "api_key_configured": bool(self.config.ai_api_key)
            }
        }, tool_name="ticmaker_async")

        if progress_callback:
            await progress_callback({
                "type": "progress",
                "progress": 10,
                "message": "Initializing AI course intro generation..."
            })

        if not self.client:
            # Debug log: AI client not available
            mcp_debug(f"AI client not available, using fallback content", {
                "ai_enabled": self.config.ai_enabled,
                "api_key_configured": bool(self.config.ai_api_key),
                "client_initialized": self.client is not None,
                "course_title": course_title,
                "fallback_reason": "no_client_instance"
            }, tool_name="ticmaker_async")

            if progress_callback:
                await progress_callback({
                    "type": "progress",
                    "progress": 50,
                    "message": "AI client unavailable, generating fallback content..."
                })

            # Simulate some processing time for realistic UX
            await asyncio.sleep(1)

            intros = [
                f"🎓 欢迎来到「{course_title}」课程！这是一门充满趣味性和互动性的学习体验。",
                f"📚 「{course_title}」将带你探索知识的奥秘，通过精心设计的互动内容让学习变得轻松愉快。",
                f"✨ 准备好开始「{course_title}」的学习之旅吧！我们将通过生动有趣的方式来掌握核心概念。",
                f"🌟 「{course_title}」课程采用创新的教学方法，让复杂的概念变得简单易懂。",
                f"🎯 在「{course_title}」中，你将通过互动练习和实践活动来深入理解每个知识点。"
            ]
            selected_intro = random.choice(intros)

            if progress_callback:
                await progress_callback({
                    "type": "progress",
                    "progress": 100,
                    "message": "Fallback content generation completed"
                })

            return selected_intro

        try:
            if progress_callback:
                await progress_callback({
                    "type": "progress",
                    "progress": 20,
                    "message": "Building AI prompt for course introduction..."
                })

            # Build AI prompt
            prompt = f"""请为课程「{course_title}」生成一段简洁而有吸引力的介绍文字。

用户输入: {user_input}

要求:
- 不超过80字
- 语言生动有趣
- 突出课程的互动性和趣味性
- 使用适当的emoji
- 直接返回介绍文字，不需要额外说明
- 避免使用特殊符号、数学公式、反斜杠等字符
- 使用简单的中文表达

格式示例: 🎓 欢迎来到xxx课程！这里将带你...
"""

            mcp_debug(f"📝 [AI_PROMPT_BUILT] AI prompt constructed", {
                "prompt_length": len(prompt),
                "course_title": course_title,
                "user_input_in_prompt": user_input in prompt,
                "prompt_preview": prompt[:200] + "..." if len(prompt) > 200 else prompt
            }, tool_name="ticmaker_async")

            if progress_callback:
                await progress_callback({
                    "type": "progress",
                    "progress": 40,
                    "message": "Sending request to AI service..."
                })

            # Debug log: AI request details
            request_data = {
                "model": self.config.ai_model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": self.config.ai_max_tokens,
                "temperature": self.config.ai_temperature
            }

            mcp_debug(f"🌐 [AI_REQUEST_PREPARE] Preparing HTTP request to AI service", {
                "endpoint": "/chat/completions",
                "method": "POST",
                "base_url": self.config.ai_base_url,
                "full_url": f"{self.config.ai_base_url}/chat/completions",
                "model": self.config.ai_model,
                "max_tokens": self.config.ai_max_tokens,
                "temperature": self.config.ai_temperature,
                "prompt_length": len(prompt),
                "course_title": course_title,
                "user_input_preview": user_input[:100] + "..." if len(user_input) > 100 else user_input,
                "api_key_configured": bool(self.config.ai_api_key),
                "request_payload_keys": list(request_data.keys()),
                "messages_count": len(request_data.get("messages", []))
            }, tool_name="ticmaker_async")

            if progress_callback:
                await progress_callback({
                    "type": "progress",
                    "progress": 60,
                    "message": "Processing AI response..."
                })

            # Record start time for HTTP request timing
            request_start_time = time.time()

            mcp_debug(f"🚀 [AI_HTTP_CALL] Sending HTTP request to TICMAKER_AI", {
                "timestamp": request_start_time,
                "request_url": f"{self.config.ai_base_url}/chat/completions",
                "request_method": "POST",
                "headers_sent": {"Content-Type": "application/json"},
                "payload_size_bytes": len(str(request_data))
            }, tool_name="ticmaker_async")

            response = await self.client.post(
                "/chat/completions",
                json=request_data
            )

            request_end_time = time.time()
            request_duration = request_end_time - request_start_time

            if progress_callback:
                await progress_callback({
                    "type": "progress",
                    "progress": 80,
                    "message": "Parsing and cleaning AI-generated content..."
                })

            # Debug log: AI client response status with timing
            mcp_debug(f"📡 [AI_HTTP_RESPONSE] HTTP response received from TICMAKER_AI", {
                "status_code": response.status_code,
                "request_duration_seconds": round(request_duration, 3),
                "request_duration_ms": round(request_duration * 1000, 1),
                "response_headers": dict(response.headers),
                "request_url": str(response.url),
                "request_method": "POST",
                "response_size_bytes": len(response.content) if hasattr(response, 'content') else 0,
                "timestamp": request_end_time
            }, tool_name="ticmaker_async")

            if response.status_code == 200:
                mcp_debug(f"✅ [AI_RESPONSE_SUCCESS] HTTP 200 OK - parsing JSON response", {
                    "content_type": response.headers.get("content-type", "unknown"),
                    "response_size": len(response.content),
                    "status_code": response.status_code
                }, tool_name="ticmaker_async")

                data = response.json()

                # Debug log: AI response data structure
                mcp_debug(f"📋 [AI_RESPONSE_PARSED] Successfully parsed AI service JSON response", {
                    "response_keys": list(data.keys()) if isinstance(data, dict) else "not_dict",
                    "has_choices": "choices" in data if isinstance(data, dict) else False,
                    "choices_count": len(data.get("choices", [])) if isinstance(data, dict) else 0,
                    "model_used": data.get("model", "unknown") if isinstance(data, dict) else "unknown",
                    "usage": data.get("usage", {}) if isinstance(data, dict) else {},
                    "object_type": data.get("object", "unknown") if isinstance(data, dict) else "unknown",
                    "created_timestamp": data.get("created", "unknown") if isinstance(data, dict) else "unknown"
                }, tool_name="ticmaker_async")

                if "choices" in data and len(data["choices"]) > 0:
                    mcp_debug(f"🎯 [AI_CONTENT_EXTRACT] Extracting content from AI response choices", {
                        "choice_index": 0,
                        "total_choices": len(data["choices"]),
                        "message_role": data["choices"][0]["message"].get("role", "unknown"),
                        "finish_reason": data["choices"][0].get("finish_reason", "unknown")
                    }, tool_name="ticmaker_async")

                    raw_content = data["choices"][0]["message"]["content"]
                    content = raw_content.strip()

                    mcp_debug(f"🧹 [AI_CONTENT_CLEAN] Processing and cleaning AI-generated content", {
                        "raw_content_length": len(raw_content),
                        "stripped_content_length": len(content),
                        "raw_content_preview": raw_content[:150] + "..." if len(raw_content) > 150 else raw_content,
                        "needs_cleaning": raw_content != content
                    }, tool_name="ticmaker_async")

                    # Clean content for JSON compatibility
                    content = self._clean_content_for_json(content)

                    if progress_callback:
                        await progress_callback({
                            "type": "progress",
                            "progress": 100,
                            "message": "AI content generation completed successfully"
                        })

                    # Debug log: Final AI generated content
                    mcp_debug(f"🎉 [AI_CONTENT_READY] AI content generation completed successfully", {
                        "final_content_length": len(content),
                        "content_preview": content[:100] + "..." if len(content) > 100 else content,
                        "finish_reason": data["choices"][0].get("finish_reason", "unknown"),
                        "choice_index": data["choices"][0].get("index", 0),
                        "model_used": data.get("model", "unknown"),
                        "total_tokens_used": data.get("usage", {}).get("total_tokens", "unknown"),
                        "request_duration_ms": round(request_duration * 1000, 1)
                    }, tool_name="ticmaker_async")

                    return content
                else:
                    # Debug log: Invalid response structure
                    mcp_debug(f"❌ [AI_RESPONSE_ERROR] AI response missing choices or empty choices", {
                        "has_choices_key": "choices" in data if isinstance(data, dict) else False,
                        "choices_data": data.get("choices", []) if isinstance(data, dict) else [],
                        "full_response": data if isinstance(data, dict) else str(data),
                        "response_type": type(data).__name__,
                        "response_size": len(str(data))
                    }, tool_name="ticmaker_async")
            else:
                # Debug log: Non-200 status code
                mcp_debug(f"🚨 [AI_HTTP_ERROR] HTTP error response from TICMAKER_AI", {
                    "status_code": response.status_code,
                    "status_reason": response.reason_phrase if hasattr(response, 'reason_phrase') else "unknown",
                    "request_duration_ms": round(request_duration * 1000, 1),
                    "response_headers": dict(response.headers),
                    "content_length": len(response.content) if hasattr(response, 'content') else 0
                }, tool_name="ticmaker_async")

                try:
                    error_data = response.json() if response.content else {}
                    mcp_debug(f"📝 [AI_ERROR_DETAILS] Parsed error response from AI service", {
                        "error_data": error_data,
                        "error_keys": list(error_data.keys()) if isinstance(error_data, dict) else [],
                        "error_message": error_data.get("error", {}).get("message", "no_message") if isinstance(error_data, dict) else "not_dict"
                    }, tool_name="ticmaker_async")
                except Exception as json_parse_error:
                    raw_text = response.text[:300] if hasattr(response, 'text') else "no_text"
                    mcp_debug(f"💥 [AI_ERROR_PARSE_FAIL] Failed to parse error response as JSON", {
                        "json_parse_error": str(json_parse_error),
                        "response_text_preview": raw_text,
                        "content_type": response.headers.get("content-type", "unknown")
                    }, tool_name="ticmaker_async")

        except Exception as e:
            # Debug log: Exception details with comprehensive context
            exception_context = {
                "exception_type": type(e).__name__,
                "exception_message": str(e),
                "exception_args": str(e.args) if hasattr(e, 'args') else "no_args",
                "ai_client_available": self.client is not None,
                "config_ai_enabled": self.config.ai_enabled,
                "config_api_key_set": bool(self.config.ai_api_key),
                "config_base_url": self.config.ai_base_url,
                "config_model": self.config.ai_model,
                "prompt_length": len(prompt) if 'prompt' in locals() else "unknown"
            }

            # Add timing info if available
            if 'request_start_time' in locals():
                exception_time = time.time()
                exception_context["request_duration_before_exception"] = round(exception_time - request_start_time, 3)

            mcp_debug(f"💥 [AI_REQUEST_EXCEPTION] Exception occurred during AI service request", exception_context, tool_name="ticmaker_async")

            mcp_warning(f"AI client error: {e}", tool_name="ticmaker_async")

        # If AI call failed, return fallback content
        mcp_debug(f"🔄 [AI_FALLBACK_START] AI request failed, generating fallback content", {
            "course_title": course_title,
            "fallback_reason": "ai_call_failed_or_invalid_response",
            "ai_enabled": self.config.ai_enabled,
            "client_available": self.client is not None
        }, tool_name="ticmaker_async")

        fallback_intros = [
            f"🎓 欢迎学习「{course_title}」！这是一门精心设计的互动式课程。",
            f"📚 「{course_title}」将通过丰富的互动内容带你掌握核心知识。",
            f"✨ 开始「{course_title}」的精彩学习之旅吧！"
        ]
        selected_fallback = random.choice(fallback_intros)

        if progress_callback:
            await progress_callback({
                "type": "progress",
                "progress": 100,
                "message": "Using fallback content after AI service issue"
            })

        # Debug log: Fallback content ready
        mcp_debug(f"🎯 [AI_FALLBACK_READY] Fallback content generated successfully", {
            "fallback_content": selected_fallback,
            "fallback_content_length": len(selected_fallback),
            "fallback_options_count": len(fallback_intros),
            "course_title": course_title,
            "selected_option_index": fallback_intros.index(selected_fallback)
        }, tool_name="ticmaker_async")

        return selected_fallback

    def _clean_content_for_json(self, content: str) -> str:
        """Clean content for JSON compatibility"""
        import re

        # Remove or replace LaTeX math formulas with backslashes
        content = re.sub(r'\\[()]', lambda m: m.group(0)[1:], content)  # \( -> (, \) -> )
        content = re.sub(r'\\[a-zA-Z]+', '', content)  # Remove LaTeX commands like \alpha, \beta

        # Remove other possible escape characters
        content = content.replace('\\n', ' ')
        content = content.replace('\\t', ' ')
        content = content.replace('\\r', ' ')
        content = content.replace('\\"', '"')
        content = content.replace("\\'", "'")

        # Clean up extra spaces
        content = re.sub(r'\s+', ' ', content)
        content = content.strip()

        # If content is too long, truncate to reasonable length
        if len(content) > 200:
            content = content[:197] + "..."

        return content

    async def close(self):
        """Close AI client"""
        if self.client:
            await self.client.aclose()


class TICMakerAsyncClient:
    """Enhanced TICMaker client with full async task support"""

    def __init__(self, config: TICMakerAsyncConfig):
        """Initialize TICMaker async client"""
        self.config = config
        self.output_dir = Path(config.output_dir)
        self.output_dir.mkdir(exist_ok=True)

        # Initialize AI client
        self.ai_client = TICMakerAsyncAIClient(config)

        # Initialize async task manager
        self.task_manager = get_global_task_manager()

        # Active tasks tracking
        self.active_tasks: Dict[str, AsyncTaskProgress] = {}

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

    def _classify_task_complexity(self, user_input: str, content_type: str = "course") -> TaskComplexity:
        """Classify task complexity based on input characteristics"""

        # Analyze user input length and complexity
        input_length = len(user_input)
        input_lower = user_input.lower()

        # Complex task indicators
        complex_keywords = [
            "详细", "复杂", "高级", "完整", "全面", "深入", "专业",
            "comprehensive", "detailed", "advanced", "complete", "complex"
        ]

        # Simple task indicators
        simple_keywords = [
            "简单", "基础", "快速", "基本", "简化", "simple", "basic", "quick", "minimal"
        ]

        # Long-running task indicators
        long_running_keywords = [
            "大型", "批量", "多个", "系列", "集合", "完整项目", "课程体系",
            "large", "bulk", "multiple", "series", "complete project", "full course"
        ]

        # Check for long-running indicators
        if any(keyword in input_lower for keyword in long_running_keywords):
            return TaskComplexity.LONG_RUNNING

        # Check for complex indicators
        if any(keyword in input_lower for keyword in complex_keywords) or input_length > 500:
            return TaskComplexity.STANDARD

        # Check for simple indicators
        if any(keyword in input_lower for keyword in simple_keywords) or input_length < 100:
            return TaskComplexity.SIMPLE

        # Content type based classification
        if content_type in ["presentation", "workshop", "complete_course"]:
            return TaskComplexity.STANDARD

        # Default classification based on input length
        if input_length > 300:
            return TaskComplexity.STANDARD
        else:
            return TaskComplexity.SIMPLE

    def _should_use_async_execution(self, complexity: TaskComplexity, user_input: str) -> bool:
        """Determine if async execution should be used"""

        if not self.config.enable_async_detection:
            return False

        # Always use async for long-running tasks
        if complexity == TaskComplexity.LONG_RUNNING:
            return True

        # Use async for standard tasks with AI enhancement
        if complexity == TaskComplexity.STANDARD and self.config.ai_enabled:
            return True

        # Check for specific async indicators in user input
        async_indicators = [
            "生成多个", "创建系列", "批量处理", "复杂内容", "AI增强",
            "generate multiple", "create series", "batch", "complex content", "ai enhanced"
        ]

        if any(indicator in user_input.lower() for indicator in async_indicators):
            return True

        return False

    async def create_interactive_course_async(
        self,
        user_input: str,
        course_title: Optional[str] = None,
        file_path: Optional[str] = None,
        content_type: Optional[str] = None,
        template_style: Optional[str] = None,
        session_context: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable] = None
    ) -> TICMakerAsyncResult:
        """Create interactive course with async support and progress reporting

        Note: Always generates new content regardless of existing file presence.
        If a file exists at the target path, it will be overwritten with new content.
        """

        start_time = time.time()
        task_id = f"create_course_{uuid.uuid4().hex[:8]}"

        # Classify task complexity
        complexity = self._classify_task_complexity(user_input, content_type or "course")
        should_async = self._should_use_async_execution(complexity, user_input)

        mcp_info(f"🎯 ===== TICMaker Async Content Creation Started =====", tool_name="ticmaker_async")
        mcp_info(f"   🆔 Task ID: {task_id}", tool_name="ticmaker_async")
        mcp_info(f"   💬 User Requirements: {user_input}", tool_name="ticmaker_async")
        mcp_info(f"   📄 Content Title: {course_title or 'Not specified'}", tool_name="ticmaker_async")
        mcp_info(f"   🎨 Content Type: {content_type or 'course'}", tool_name="ticmaker_async")
        mcp_info(f"   🧠 Task Complexity: {complexity.value}", tool_name="ticmaker_async")
        mcp_info(f"   ⚡ Async Execution: {should_async}", tool_name="ticmaker_async")

        # Initialize progress tracking
        progress_tracker = AsyncTaskProgress(task_id, total_steps=100)
        self.active_tasks[task_id] = progress_tracker

        async def report_progress(step: int, message: str, metadata: Optional[Dict[str, Any]] = None):
            """Helper function to report progress"""
            progress_tracker.update(step, message, metadata)
            progress_data = progress_tracker.get_progress_data()
            progress_data["type"] = "progress"

            if progress_callback:
                await progress_callback(progress_data)

            mcp_debug(f"Progress update: {step}/100 - {message}", {
                "task_id": task_id,
                "progress_percent": (step / 100) * 100,
                "elapsed_time": progress_data["elapsed_time"]
            }, tool_name="ticmaker_async")

        try:
            # Report initial progress
            await report_progress(5, "Initializing course creation task...")

            # Validate input
            if not user_input or not user_input.strip():
                await report_progress(100, "Task failed: empty user input", {"error": "validation_failed"})
                return TICMakerAsyncResult(
                    success=False,
                    error="User input is required",
                    task_id=task_id,
                    task_complexity=complexity,
                    was_async=should_async
                )

            await report_progress(10, "Input validation completed")

            # Determine file path
            if not file_path:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                random_id = str(uuid.uuid4())[:8]
                filename = f"ticmaker_async_page_{timestamp}_{random_id}.html"
                file_path = self.output_dir / filename
                await report_progress(15, f"Generated filename: {filename}")
            else:
                original_path = file_path
                file_path = Path(file_path)
                # Ensure file is in safe directory
                if not str(file_path.resolve()).startswith(str(self.output_dir.resolve())):
                    file_path = self.output_dir / Path(file_path).name
                    await report_progress(15, f"File path adjusted for security: {original_path} → {file_path}")

            # Always generate new content (file existence check removed)
            mcp_debug(f"📝 [CONTENT_STRATEGY] Always generating new content, file existence check disabled", {
                "file_path": str(file_path),
                "strategy": "always_generate_new",
                "modification_disabled": True
            }, tool_name="ticmaker_async")

            await report_progress(20, "Generating new HTML content...")

            # Create new page with async support
            html_content = await self._generate_html_content_async(
                user_input,
                course_title,
                template_style or self.config.default_template,
                content_type or "course",
                session_context,
                task_id,
                progress_callback=report_progress
            )

            await report_progress(90, "Validating and writing file...")

            # Check content size
            if len(html_content.encode('utf-8')) > self.config.max_file_size:
                await report_progress(100, "Task failed: content too large", {"error": "size_limit_exceeded"})
                return TICMakerAsyncResult(
                    success=False,
                    error=f"Generated content too large ({len(html_content)} characters > {self.config.max_file_size} bytes)",
                    task_id=task_id,
                    task_complexity=complexity,
                    was_async=should_async
                )

            # Write file
            file_path.write_text(html_content, encoding='utf-8')

            # Get file info
            file_size = file_path.stat().st_size
            action = "Created"  # Always creating new content
            execution_time = time.time() - start_time

            await report_progress(100, f"Interactive course {action.lower()} successfully")

            mcp_info(f"🎉 Interactive course {action.lower()} successfully", tool_name="ticmaker_async")
            mcp_info(f"📁 File path: {file_path}", tool_name="ticmaker_async")
            mcp_info(f"📏 File size: {file_size} bytes", tool_name="ticmaker_async")
            mcp_info(f"⏱️ Execution time: {execution_time:.2f}s", tool_name="ticmaker_async")
            mcp_info(f"🧠 Task complexity: {complexity.value}", tool_name="ticmaker_async")
            mcp_info(f"⚡ Was async: {should_async}", tool_name="ticmaker_async")
            mcp_info(f"🎯 ===== TICMaker Async Course Creation Completed =====", tool_name="ticmaker_async")

            # Log successful completion to file
            mcp_info(f"Course creation completed successfully", {
                "action": action.lower(),
                "file_path": str(file_path),
                "file_size": file_size,
                "execution_time": execution_time,
                "content_length": len(html_content),
                "task_complexity": complexity.value,
                "was_async": should_async,
                "progress_updates": progress_tracker.current_step,
                "session_context_included": session_context is not None
            }, tool_name="ticmaker_async", session_id=session_context.get('session_id') if session_context else None)

            return TICMakerAsyncResult(
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
                },
                task_id=task_id,
                task_complexity=complexity,
                was_async=should_async,
                progress_updates_count=progress_tracker.current_step
            )

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = f"Interactive course creation failed: {str(e)}"

            await report_progress(100, f"Task failed with error: {str(e)}", {"error": "execution_failed"})

            mcp_error(f"💥 {error_msg}", tool_name="ticmaker_async")
            mcp_error(f"⏱️ Execution time before error: {execution_time:.2f}s", tool_name="ticmaker_async")
            mcp_error(f"🎯 ===== TICMaker Async Course Creation Failed =====", tool_name="ticmaker_async")

            # Log error to file with detailed context
            mcp_error("Course creation failed with exception", {
                "error_message": str(e),
                "error_type": type(e).__name__,
                "execution_time": execution_time,
                "user_input": user_input,
                "course_title": course_title,
                "file_path": str(file_path) if file_path else None,
                "task_complexity": complexity.value,
                "was_async": should_async,
                "session_context": session_context
            }, tool_name="ticmaker_async", session_id=session_context.get('session_id') if session_context else None)

            return TICMakerAsyncResult(
                success=False,
                error=error_msg,
                execution_time=execution_time,
                task_id=task_id,
                task_complexity=complexity,
                was_async=should_async
            )

        finally:
            # Clean up progress tracking
            self.active_tasks.pop(task_id, None)

    async def _generate_html_content_async(
        self,
        user_input: str,
        course_title: Optional[str] = None,
        template_style: str = "modern",
        content_type: str = "course",
        session_context: Optional[Dict[str, Any]] = None,
        task_id: str = "",
        progress_callback: Optional[Callable] = None
    ) -> str:
        """Generate HTML content with async AI integration"""

        # Extract title from user input if not provided
        title = course_title if course_title else self._extract_title_from_user_input(user_input)

        if progress_callback:
            await progress_callback(30, "Generating AI-powered course introduction...")

        # Generate AI-powered course introduction with async support
        async def ai_progress_callback(ai_progress_data):
            # Map AI progress (0-100) to our progress range (30-70)
            mapped_progress = 30 + (ai_progress_data.get("progress", 0) * 0.4)
            if progress_callback:
                await progress_callback(int(mapped_progress), f"AI: {ai_progress_data.get('message', 'Processing...')}")

        ai_generated_intro = await self.ai_client.generate_course_intro_async(
            title, user_input, progress_callback=ai_progress_callback
        )

        # Debug log: Complete AI request flow summary
        mcp_debug(f"🎯 [AI_FLOW_COMPLETE] Complete AI request flow finished", {
            "user_input": user_input[:100] + "..." if len(user_input) > 100 else user_input,
            "course_title": title,
            "ai_intro_received": bool(ai_generated_intro),
            "ai_intro_length": len(ai_generated_intro) if ai_generated_intro else 0,
            "ai_intro_preview": ai_generated_intro[:80] + "..." if ai_generated_intro and len(ai_generated_intro) > 80 else ai_generated_intro,
            "ai_client_config": {
                "enabled": self.config.ai_enabled,
                "base_url": self.config.ai_base_url,
                "model": self.config.ai_model,
                "api_key_configured": bool(self.config.ai_api_key)
            },
            "flow_stage": "ai_content_generated_proceeding_to_html_template"
        }, tool_name="ticmaker_async")

        if progress_callback:
            await progress_callback(70, "Building interactive HTML template...")

        # Generate interactive template with AI content
        html_content = await self._generate_interactive_template_async(
            title, user_input, template_style, content_type, course_title,
            session_context, ai_generated_intro, task_id
        )

        if progress_callback:
            await progress_callback(85, "HTML content generation completed")

        return html_content

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

    def _extract_title_from_user_input(self, user_input: str) -> str:
        """Extract title from user input with enhanced detection"""
        user_input_lower = user_input.lower()

        # Detect specific content types with async indicators
        if any(keyword in user_input_lower for keyword in ["游戏", "小游戏", "互动游戏"]):
            return "Async Interactive Teaching Game"
        elif any(keyword in user_input_lower for keyword in ["活动", "练习", "训练"]):
            return "Async Teaching Activity Page"
        elif any(keyword in user_input_lower for keyword in ["课程", "教学", "学习"]):
            return "Async Interactive Course Content"
        elif any(keyword in user_input_lower for keyword in ["测验", "测试", "考试"]):
            return "Async Interactive Quiz Page"
        elif any(keyword in user_input_lower for keyword in ["讨论", "问答", "q&a"]):
            return "Async Discussion and Q&A Page"
        else:
            return "Async Interactive Teaching Content"

    async def _generate_interactive_template_async(
        self,
        title: str,
        user_input: str,
        template_style: str = "modern",
        content_type: str = "course",
        course_title: Optional[str] = None,
        session_context: Optional[Dict[str, Any]] = None,
        ai_generated_intro: Optional[str] = None,
        task_id: str = ""
    ) -> str:
        """Generate interactive HTML template with async enhancements"""

        # Ensure ai_generated_intro has a fallback value
        if ai_generated_intro is None:
            ai_generated_intro = "🎓 欢迎来到这个精心设计的异步互动内容！"

        # Set content-specific emoji and subtitle based on content_type
        content_emoji_map = {
            "course": "🎓",
            "slides": "📊",
            "presentation": "🎬",
            "tutorial": "📚",
            "lesson": "📖",
            "workshop": "🔧"
        }

        content_subtitle_map = {
            "course": "异步互动课程",
            "slides": "异步演示文稿",
            "presentation": "异步展示内容",
            "tutorial": "异步教程指南",
            "lesson": "异步学习课时",
            "workshop": "异步实践工坊"
        }

        content_emoji = content_emoji_map.get(content_type, "🎓")
        content_subtitle = content_subtitle_map.get(content_type, "异步互动内容")

        # Enhanced template with async task features
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
            max-width: 950px;
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
            position: relative;
        }}

        .async-badge {{
            position: absolute;
            top: 10px;
            right: 15px;
            background: rgba(255,255,255,0.2);
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.8em;
            backdrop-filter: blur(10px);
        }}

        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}

        .header .content-type {{
            font-size: 1.1em;
            opacity: 0.9;
            font-weight: normal;
        }}

        .task-info {{
            background: rgba(255,255,255,0.1);
            padding: 15px;
            margin-top: 15px;
            border-radius: 10px;
            backdrop-filter: blur(10px);
        }}

        .task-info .task-id {{
            font-family: monospace;
            font-size: 0.9em;
            opacity: 0.8;
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

        .async-features {{
            background: linear-gradient(135deg, #e8f5e8 0%, #c8e6c9 100%);
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
            border: 1px solid #4caf50;
        }}

        .async-features h3 {{
            color: #2e7d32;
            margin-bottom: 15px;
        }}

        .feature-list {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 10px;
        }}

        .feature-item {{
            background: rgba(255,255,255,0.7);
            padding: 10px;
            border-radius: 5px;
            font-size: 0.9em;
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

        .async-badge-special {{
            background: #4caf50;
        }}

        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(20px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}

        @keyframes pulse {{
            0% {{ opacity: 1; }}
            50% {{ opacity: 0.7; }}
            100% {{ opacity: 1; }}
        }}

        .fade-in {{
            animation: fadeIn 0.6s ease-out;
        }}

        .async-indicator {{
            animation: pulse 2s infinite;
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
            <div class="async-badge async-indicator">⚡ ASYNC ENHANCED</div>
            <h1>{content_emoji} {title}</h1>
            <div class="content-type">{content_subtitle}</div>
            {f'<h2>📚 {course_title}</h2>' if course_title else ''}
            <div class="task-info">
                <div class="task-id">🆔 Task ID: {task_id}</div>
                <div>🕒 Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</div>
            </div>
        </div>

        <div class="content">
            <div class="requirement-box">
                <strong>用户需求:</strong> {user_input}
            </div>

            <div class="async-features">
                <h3>🚀 异步任务增强特性</h3>
                <div class="feature-list">
                    <div class="feature-item">⚡ 智能任务复杂度检测</div>
                    <div class="feature-item">📊 实时进度回传</div>
                    <div class="feature-item">🔄 异步执行优化</div>
                    <div class="feature-item">🛡️ 错误恢复机制</div>
                    <div class="feature-item">📈 性能监控</div>
                    <div class="feature-item">🎯 智能资源管理</div>
                </div>
            </div>

            <div class="interaction-area">
                <button class="interactive-button" onclick="showAICourseIntro()">AI课程介绍</button>
                <button class="interactive-button" onclick="showQuiz()">开始小测验</button>
                <button class="interactive-button" onclick="showInfo()">课程信息</button>
                <button class="interactive-button" onclick="showActivity()">互动活动</button>
                <button class="interactive-button" onclick="showAsyncFeatures()">异步特性</button>
                <button class="interactive-button" onclick="showSessionContext()">Session Context</button>
            </div>

            <div class="content-area" id="dynamic-content">
                <p>👆 点击上方按钮开始异步增强的互动体验</p>
            </div>

            <div class="quiz-container" id="quiz-container">
                <div class="quiz-question">
                    <h3>📝 快速测验 - 异步任务特性</h3>
                    <p>以下哪个是TICMaker异步增强版的主要特性？</p>
                    <ul class="quiz-options">
                        <li onclick="checkAnswer(this, true)">智能任务复杂度检测和异步执行</li>
                        <li onclick="checkAnswer(this, false)">基础文档编辑</li>
                        <li onclick="checkAnswer(this, false)">简单数据分析</li>
                        <li onclick="checkAnswer(this, false)">静态图片处理</li>
                    </ul>
                </div>
            </div>

            <div class="info-panel" id="info-panel">
                <h3>📋 课程详细信息</h3>
                <div class="badge">异步互动教学</div>
                <div class="badge">HTML页面</div>
                <div class="badge">AI辅助</div>
                <div class="badge async-badge-special">异步任务增强</div>
                <div class="badge">响应式设计</div>
                <div class="badge">进度回传</div>
                <p><strong>创建时间:</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
                <p><strong>任务ID:</strong> {task_id}</p>
                <p><strong>用户需求:</strong> {user_input}</p>
                <p><strong>技术特点:</strong> 基于MCP异步任务增强架构的交互式教学内容创建工具</p>
                {self._generate_session_info_html(session_context)}
            </div>
        </div>

        <div class="footer">
            <p>🚀 由 <strong>TICMaker Async Enhanced</strong> 创建 | ⚡ 异步任务增强版交互式教学内容生成器</p>
            <p><small>创建时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | Task ID: {task_id}</small></p>
        </div>
    </div>

    <script>
        function showMessage(message) {{
            const contentArea = document.getElementById('dynamic-content');
            contentArea.innerHTML = `
                <div class="fade-in">
                    <h3>🎯 异步互动消息</h3>
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
                    <h3>📚 异步测验模式已激活</h3>
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
                    <h3>ℹ️ 异步课程信息</h3>
                    <p>课程详细信息已在下方展示</p>
                </div>
            `;
        }}

        function showActivity() {{
            const activities = [
                "🎨 异步创意绘画练习",
                "🧩 智能逻辑思维训练",
                "📖 AI增强阅读理解练习",
                "🔬 虚拟科学实验模拟",
                "🎵 互动音乐节拍练习",
                "⚡ 异步任务体验活动"
            ];
            const randomActivity = activities[Math.floor(Math.random() * activities.length)];

            document.getElementById('dynamic-content').innerHTML = `
                <div class="fade-in">
                    <h3>🎯 今日推荐异步活动</h3>
                    <p style="font-size: 1.3em; margin: 20px 0; color: #667eea;">${{randomActivity}}</p>
                    <button class="interactive-button" onclick="showActivity()" style="margin: 5px;">换一个活动</button>
                    <button class="interactive-button" onclick="resetContent()" style="margin: 5px;">返回首页</button>
                </div>
            `;
        }}

        function showAsyncFeatures() {{
            document.getElementById('dynamic-content').innerHTML = `
                <div class="fade-in">
                    <h3>⚡ 异步任务增强特性详解</h3>
                    <div style="background: #f8f9ff; padding: 20px; border-radius: 10px; margin: 20px 0; text-align: left;">
                        <h4>🚀 核心特性:</h4>
                        <ul style="margin: 15px 0; padding-left: 20px;">
                            <li><strong>智能任务检测:</strong> 自动分析任务复杂度并选择最佳执行模式</li>
                            <li><strong>实时进度回传:</strong> 提供详细的任务执行进度和状态更新</li>
                            <li><strong>异步执行优化:</strong> 长时间运行任务使用异步处理，提升用户体验</li>
                            <li><strong>错误恢复机制:</strong> 智能错误处理和自动回退功能</li>
                            <li><strong>资源管理:</strong> 优化的并发控制和资源分配</li>
                        </ul>
                        <h4>📊 性能优势:</h4>
                        <ul style="margin: 15px 0; padding-left: 20px;">
                            <li>支持最多3个并发任务</li>
                            <li>智能超时管理(默认5分钟)</li>
                            <li>2秒间隔的进度更新</li>
                            <li>自动任务复杂度分类</li>
                        </ul>
                    </div>
                    <button class="interactive-button" onclick="resetContent()" style="margin-top: 15px;">返回</button>
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
                    alert('🎉 恭喜！答案正确！您了解了异步任务增强特性！');
                    resetQuiz();
                }}, 500);
            }} else {{
                element.style.background = '#dc3545';
                element.style.color = 'white';
                setTimeout(() => {{
                    alert('😅 答案错误，建议了解一下异步任务增强特性！');
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
                <p>👆 点击上方按钮开始异步增强的互动体验</p>
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
                        <h3>🔄 Session Context Details (Async Enhanced)</h3>
                        <div style="background: #f8f9ff; padding: 20px; border-radius: 10px; margin: 20px 0; text-align: left;">
                            <h4>📊 Real-time Session Information:</h4>
                            <div style="font-family: monospace; background: #e9ecef; padding: 15px; border-radius: 5px; margin: 10px 0;">
                                <pre>${{JSON.stringify(sessionInfo, null, 2)}}</pre>
                            </div>
                            <p><strong>🔍 Session State:</strong> <span style="color: #667eea;">${{sessionInfo.session_state || 'Unknown'}}</span></p>
                            <p><strong>📋 Current Task:</strong> <span style="color: #764ba2;">${{sessionInfo.current_task || 'Unknown'}}</span></p>
                            <p><strong>👤 User Input:</strong> <span style="color: #f5576c;">${{(sessionInfo.user_input || 'Unknown').substring(0, 100)}}...</span></p>
                            <p><strong>⚡ Async Mode:</strong> <span style="color: #4caf50;">Enabled</span></p>
                        </div>
                        <button class="interactive-button" onclick="resetContent()" style="margin-top: 15px;">返回</button>
                    </div>
                `;
            }} else {{
                // Display message when no session context is available
                contentArea.innerHTML = `
                    <div class="fade-in">
                        <h3>🔄 Session Context (Async Enhanced)</h3>
                        <div style="background: #fff3cd; padding: 20px; border-radius: 10px; margin: 20px 0; text-align: center; border: 1px solid #ffeaa7;">
                            <h4 style="color: #856404;">📋 No Session Context Available</h4>
                            <p style="color: #856404; margin: 15px 0;">This content was created without active session context information.</p>
                            <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 15px 0;">
                                <p><strong>💡 Async Session Context Features:</strong></p>
                                <ul style="text-align: left; color: #495057;">
                                    <li>🔍 Real-time session state tracking</li>
                                    <li>📋 Async task information</li>
                                    <li>👤 User input history with async processing</li>
                                    <li>🔄 Real-time context updates</li>
                                    <li>⚡ Async task progress monitoring</li>
                                    <li>📊 Performance metrics tracking</li>
                                </ul>
                            </div>
                            <p style="font-size: 0.9em; color: #6c757d; font-style: italic;">
                                To see async session context, this tool needs to be called from within a SimaCode ReAct async session.
                            </p>
                        </div>
                        <button class="interactive-button" onclick="resetContent()" style="margin-top: 15px;">返回</button>
                    </div>
                `;
            }}
            contentArea.className = 'content-area fade-in';
        }}

        // AI-powered course introduction function with async support
        async function showAICourseIntro() {{
            const contentArea = document.getElementById('dynamic-content');

            // Show loading message with async indicators
            contentArea.innerHTML = `
                <div class="fade-in">
                    <h3>🤖 AI正在异步生成课程介绍...</h3>
                    <p style="font-size: 1.1em; margin: 20px 0; color: #6c757d;">使用异步任务增强架构，AI正在为您量身定制课程介绍内容...</p>
                    <div style="text-align: center; margin: 20px 0;">
                        <div style="display: inline-block; width: 20px; height: 20px; border: 2px solid #4caf50; border-radius: 50%; border-top-color: transparent; animation: spin 1s linear infinite;"></div>
                        <span style="margin-left: 10px; color: #4caf50;">异步处理中...</span>
                    </div>
                </div>
            `;
            contentArea.className = 'content-area fade-in';

            try {{
                // Get course title and user input from the page
                const titleElement = document.querySelector('h1');
                const courseTitle = titleElement ? titleElement.textContent.trim() : '异步课程';
                const userInput = '{user_input}';

                // Use real AI-generated course introduction
                await new Promise(resolve => setTimeout(resolve, 2000)); // Simulate async processing time

                // AI-generated course introduction from backend
                const aiGeneratedIntro = `{ai_generated_intro}`;

                const randomIntro = aiGeneratedIntro;

                // Display the AI-generated introduction
                contentArea.innerHTML = `
                    <div class="fade-in">
                        <h3>🤖 AI异步生成的课程介绍</h3>
                        <div style="background: linear-gradient(135deg, #f8f9ff 0%, #e8f4ff 100%); padding: 25px; border-radius: 15px; margin: 20px 0; border: 1px solid #e3f2fd;">
                            <p style="font-size: 1.2em; line-height: 1.8; color: #2c3e50; margin: 0;">${{randomIntro}}</p>
                        </div>
                        <div style="text-align: center; margin: 20px 0;">
                            <small style="color: #6c757d; font-style: italic;">💡 此内容由AI通过异步任务增强架构根据您的需求智能生成</small>
                        </div>
                        <button class="interactive-button" onclick="resetContent()" style="margin-top: 15px;">返回</button>
                    </div>
                `;
            }} catch (error) {{
                // Error handling - show fallback content
                contentArea.innerHTML = `
                    <div class="fade-in">
                        <h3>🎯 异步课程介绍</h3>
                        <div style="background: #fff3cd; padding: 20px; border-radius: 10px; margin: 20px 0; border: 1px solid #ffeaa7;">
                            <p style="font-size: 1.2em; margin: 0;">🎉 欢迎学习${{courseTitle || '本异步课程'}}！这是一个基于异步任务增强架构、根据您的需求定制的互动课程，让我们开始这段精彩的异步学习之旅吧！</p>
                        </div>
                        <button class="interactive-button" onclick="resetContent()" style="margin-top: 15px;">返回</button>
                    </div>
                `;
            }}

            contentArea.className = 'content-area fade-in';
        }}

        // Add some entrance animations with async effects
        window.addEventListener('load', function() {{
            document.querySelector('.container').classList.add('fade-in');
            // Add async indicator pulse effect
            setTimeout(() => {{
                const asyncBadge = document.querySelector('.async-badge');
                if (asyncBadge) {{
                    asyncBadge.style.animation = 'pulse 2s infinite';
                }}
            }}, 1000);
        }});
    </script>
</body>
</html>"""

        return html_content

    def _generate_session_info_html(self, session_context: Optional[Dict[str, Any]]) -> str:
        """Generate HTML content for async session context information"""
        if not session_context:
            return ""

        session_state = session_context.get("session_state", "Unknown")
        current_task = session_context.get("current_task", "Unknown")
        session_user_input = session_context.get("user_input", "Unknown")
        metadata_context = session_context.get("metadata_context", {})

        # Build metadata context display
        metadata_html = ""
        if metadata_context:
            metadata_html = f"""
                    <hr style="margin: 15px 0; border: none; border-top: 1px dashed #ccc;">
                    <h5>📊 Async Metadata Context</h5>
                    <div style="background: #f8f9fa; padding: 12px; border-radius: 6px; margin: 8px 0;">"""

            if "service_version" in metadata_context:
                metadata_html += f"""
                        <p><strong>🔧 Service Version:</strong> <span style="color: #6c757d;">{metadata_context['service_version']}</span></p>"""

            if "config" in metadata_context:
                config = metadata_context["config"]
                if "ai_provider" in config:
                    metadata_html += f"""
                        <p><strong>🤖 AI Provider:</strong> <span style="color: #007bff;">{config['ai_provider']}</span></p>"""
                if "ai_model" in config:
                    metadata_html += f"""
                        <p><strong>🧠 AI Model:</strong> <span style="color: #6f42c1;">{config['ai_model']}</span></p>"""

            # Show any additional context data
            for key, value in metadata_context.items():
                if key not in ["service_version", "config"]:
                    metadata_html += f"""
                        <p><strong>📝 {key.replace('_', ' ').title()}:</strong> <span style="color: #495057;">{str(value)[:80]}{'...' if len(str(value)) > 80 else ''}</span></p>"""

            metadata_html += """
                    </div>"""

        return f"""
                <hr style="margin: 20px 0; border: none; border-top: 1px solid #ddd;">
                <h4>🔄 Async Session Context Information</h4>
                <div style="background: #f0f8ff; padding: 15px; border-radius: 8px; margin: 10px 0;">
                    <p><strong>🔍 Session State:</strong> <span style="color: #667eea; font-weight: 600;">{session_state}</span></p>
                    <p><strong>📋 Current Task:</strong> <span style="color: #764ba2; font-weight: 600;">{current_task}</span></p>
                    <p><strong>👤 Session User Input:</strong> <span style="color: #f5576c; font-style: italic;">{session_user_input[:100]}{'...' if len(session_user_input) > 100 else ''}</span></p>
                    <p><strong>⚡ Async Mode:</strong> <span style="color: #4caf50; font-weight: 600;">Enhanced</span></p>
                    {metadata_html}
                </div>
                <div class="badge" style="background: #28a745;">Session-Aware</div>
                <div class="badge" style="background: #17a2b8;">Context-Enabled</div>
                <div class="badge async-badge-special">Async-Enhanced</div>"""


class TICMakerAsyncStdioMCPServer:
    """
    Enhanced stdio-based MCP server for TICMaker with async task support.

    This server automatically detects task complexity and uses async execution
    for long-running operations, providing real-time progress updates.
    """

    def __init__(self, ticmaker_config: Optional[TICMakerAsyncConfig] = None):
        """Initialize TICMaker async stdio MCP server"""
        # Initialize TICMaker client with configuration
        self.ticmaker_config = ticmaker_config or TICMakerAsyncConfig()
        self.ticmaker_client = TICMakerAsyncClient(self.ticmaker_config)

        # Initialize async task manager
        self.task_manager = get_global_task_manager()

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

    async def run(self):
        """Run the async stdio MCP server"""
        mcp_info("🚀 Starting TICMaker Async stdio MCP server...", tool_name="ticmaker_async")
        mcp_info(f"📂 Output directory: {self.ticmaker_config.output_dir}", tool_name="ticmaker_async")
        mcp_info(f"🎨 Default template: {self.ticmaker_config.default_template}", tool_name="ticmaker_async")
        mcp_info(f"⚡ Async detection enabled: {self.ticmaker_config.enable_async_detection}", tool_name="ticmaker_async")
        mcp_info(f"🧠 AI enhancement enabled: {self.ticmaker_config.ai_enabled}", tool_name="ticmaker_async")
        mcp_info("📡 Ready to receive MCP messages via stdio with async support", tool_name="ticmaker_async")

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
                    # Read from stdin
                    line = await asyncio.to_thread(sys.stdin.readline)
                    if not line:
                        break

                    line = line.strip()
                    if not line:
                        continue

                    mcp_debug(f"📥 Received: {line}", tool_name="ticmaker_async")

                    # Parse MCP message
                    try:
                        message_data = json.loads(line)
                        message = MCPMessage(**message_data)
                    except (json.JSONDecodeError, TypeError, ValueError) as e:
                        mcp_error(f"❌ Invalid JSON message: {str(e)}", tool_name="ticmaker_async")
                        continue

                    # Process message
                    response = await self.handle_message(message)

                    # Send response
                    if response:
                        response_json = response.to_dict()
                        response_line = json.dumps(response_json, ensure_ascii=False)
                        print(response_line, flush=True)
                        mcp_debug(f"📤 Sent: {response_line}", tool_name="ticmaker_async")

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

        # Log detailed message information
        if message.params:
            mcp_debug(f"📋 [REQUEST_PARAMS] Message parameters: {json.dumps(message.params, ensure_ascii=False, indent=2)}", tool_name="ticmaker_async")

        if message.method == "notifications/initialized":
            mcp_info("Received initialized notification", tool_name="ticmaker_async")
            return None

        if message.method == MCPMethods.INITIALIZE:
            # Initialization request with async capabilities
            mcp_info("🔧 Processing INITIALIZE request", tool_name="ticmaker_async")
            capabilities = {
                "tools": {
                    tool_name: tool_info["description"]
                    for tool_name, tool_info in self.tools.items()
                },
                "async_support": True,  # Indicate async task support
                "progress_reporting": True
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
            mcp_info("🛠️ Processing TOOLS_LIST request", tool_name="ticmaker_async")
            tools_list = [
                {
                    "name": tool_name,
                    "description": tool_info["description"],
                    "input_schema": tool_info["input_schema"]
                }
                for tool_name, tool_info in self.tools.items()
            ]
            response = MCPMessage(
                id=message.id,
                result={"tools": tools_list}
            )
            mcp_debug(f"✅ TOOLS_LIST response: {len(tools_list)} async tools", tool_name="ticmaker_async")
            return response

        elif message.method == MCPMethods.TOOLS_CALL:
            # Execute tool with async support
            return await self._handle_tool_call(message)

        elif message.method == MCPMethods.TOOLS_CALL_ASYNC:
            # Handle explicit async tool call
            return await self._handle_async_tool_call(message)

        elif message.method == MCPMethods.PING:
            # Ping response
            mcp_info("🏓 Processing PING request", tool_name="ticmaker_async")
            response = MCPMessage(
                id=message.id,
                result={"pong": True, "async_enabled": True}
            )
            mcp_debug("✅ PING response: pong with async support", tool_name="ticmaker_async")
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

        # For now, redirect to the same logic as regular tool call
        # In a full implementation, this would handle streaming progress updates
        return await self._handle_tool_call(message)

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
                mcp_debug(f"Progress update: {progress_data.get('message', 'Processing...')}", {
                    "request_id": request_id,
                    "progress": progress_data.get("progress", 0),
                    "step": progress_data.get("current_step", 0)
                }, tool_name="ticmaker_async")

            # Create interactive course with async support
            result = await self.ticmaker_client.create_interactive_course_async(
                user_input=user_input,
                course_title=course_title,
                file_path=file_path,
                content_type=content_type,
                template_style=template_style,
                session_context=session_context,
                progress_callback=progress_callback
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

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        mcp_debug("🐛 Debug logging enabled for async server", tool_name="ticmaker_async")

    # Load configuration
    config_path = Path(args.config) if args.config else None
    ticmaker_config = load_async_config(config_path=config_path)

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
    server = TICMakerAsyncStdioMCPServer(ticmaker_config)
    await server.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAsync server stopped by user.", file=sys.stderr)
    except Exception as e:
        print(f"Async server error: {str(e)}", file=sys.stderr)
        sys.exit(1)