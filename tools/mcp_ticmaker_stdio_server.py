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
  output_dir: ".simacode/mcp/ticmaker_output"
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
import random
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, AsyncGenerator
from dataclasses import dataclass

# AI client dependencies
import httpx

# Add parent directory to path for MCP imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# MCP Protocol imports (using our existing MCP implementation)
from src.simacode.mcp.protocol import MCPMessage, MCPMethods, MCPErrorCodes
from src.simacode.config import Config

# Import utilities
from src.simacode.utils.mcp_logger import mcp_file_log, mcp_debug, mcp_info, mcp_warning, mcp_error
from src.simacode.utils.config_loader import load_simacode_config

# Configure logging to stderr to avoid interfering with stdio protocol
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
# logger = logging.getLogger(__name__)  # 已替换为 mcp_logger


@dataclass
class TICMakerConfig:
    """Configuration for TICMaker content creation."""
    output_dir: str = ".simacode/mcp/ticmaker_output"
    default_template: str = "modern"
    ai_enhancement: bool = False
    max_file_size: int = 1024 * 1024 * 10  # 10MB
    allowed_file_extensions: List[str] = None
    # AI客户端配置
    ai_enabled: bool = True
    ai_base_url: str = "https://api.openai.com/v1"
    ai_api_key: str = ""
    ai_model: str = "gpt-3.5-turbo"
    ai_max_tokens: int = 500
    ai_temperature: float = 0.7
    
    def __post_init__(self):
        """Set default values after initialization."""
        if self.allowed_file_extensions is None:
            self.allowed_file_extensions = [".html", ".htm"]
    
    @classmethod
    def from_simacode_config(cls, config: Config) -> 'TICMakerConfig':
        """Create TICMakerConfig from SimaCode Config object."""
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
        
        # Override with environment variables (priority: env vars > config)
        output_dir = os.getenv("TICMAKER_OUTPUT_DIR", output_dir)
        default_template = os.getenv("TICMAKER_TEMPLATE", default_template)
        
        # AI configuration with environment override
        ai_enabled_env = os.getenv("TICMAKER_AI_ENABLED", str(ai_enabled_default))
        ai_enabled = ai_enabled_env.lower() == "true"
        
        ai_base_url = os.getenv("TICMAKER_AI_BASE_URL", ai_base_url_default)
        ai_api_key = os.getenv("TICMAKER_AI_API_KEY", ai_api_key_default)
        ai_model = os.getenv("TICMAKER_AI_MODEL", ai_model_default)
        
        try:
            ai_max_tokens = int(os.getenv("TICMAKER_AI_MAX_TOKENS", str(ai_max_tokens_default)))
        except ValueError:
            ai_max_tokens = ai_max_tokens_default
        
        try:
            ai_temperature = float(os.getenv("TICMAKER_AI_TEMPERATURE", str(ai_temperature_default)))
        except ValueError:
            ai_temperature = ai_temperature_default
        
        return cls(
            output_dir=output_dir,
            default_template=default_template,
            ai_enhancement=ai_enhancement,
            ai_enabled=ai_enabled,
            ai_base_url=ai_base_url,
            ai_api_key=ai_api_key,
            ai_model=ai_model,
            ai_max_tokens=ai_max_tokens,
            ai_temperature=ai_temperature
        )


@dataclass
class TICMakerResult:
    """Result from TICMaker content creation operation."""
    success: bool
    message: str = ""
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Optional[Dict[str, Any]] = None


class TICMakerAIClient:
    """OpenAI兼容的AI客户端用于内容生成."""
    
    def __init__(self, config: TICMakerConfig):
        """初始化AI客户端."""
        self.config = config
        self.client = None
        if config.ai_enabled and config.ai_api_key:
            self.client = httpx.AsyncClient(
                base_url=config.ai_base_url,
                headers={"Authorization": f"Bearer {config.ai_api_key}"},
                timeout=30.0
            )
    
    async def generate_course_intro(self, course_title: str, user_input: str) -> str:
        """生成课程介绍文本."""
        if not self.client:
            # Debug log: AI client not available
            mcp_debug(f"AI client not available, using fallback content", {
                "ai_enabled": self.config.ai_enabled,
                "api_key_configured": bool(self.config.ai_api_key),
                "client_initialized": self.client is not None,
                "course_title": course_title,
                "fallback_reason": "no_client_instance"
            }, tool_name="ticmaker")
            
            # 如果AI客户端不可用，返回随机生成的内容
            intros = [
                f"🎓 欢迎来到「{course_title}」课程！这是一门充满趣味性和互动性的学习体验。",
                f"📚 「{course_title}」将带你探索知识的奥秘，通过精心设计的互动内容让学习变得轻松愉快。",
                f"✨ 准备好开始「{course_title}」的学习之旅吧！我们将通过生动有趣的方式来掌握核心概念。",
                f"🌟 「{course_title}」课程采用创新的教学方法，让复杂的概念变得简单易懂。",
                f"🎯 在「{course_title}」中，你将通过互动练习和实践活动来深入理解每个知识点。"
            ]
            selected_intro = random.choice(intros)
            
            # Debug log: Fallback content selected
            mcp_debug(f"Fallback content selected", {
                "selected_intro": selected_intro,
                "available_options": len(intros)
            }, tool_name="ticmaker")
            
            return selected_intro
        
        try:
            # 构建AI提示
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

            # Debug log: AI request details
            request_data = {
                "model": self.config.ai_model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": self.config.ai_max_tokens,
                "temperature": self.config.ai_temperature
            }
            
            mcp_debug(f"Sending AI request for course intro generation", {
                "model": self.config.ai_model,
                "max_tokens": self.config.ai_max_tokens,
                "temperature": self.config.ai_temperature,
                "prompt_length": len(prompt),
                "prompt_preview": prompt[:150] + "..." if len(prompt) > 150 else prompt,
                "course_title": course_title,
                "user_input_preview": user_input[:100] + "..." if len(user_input) > 100 else user_input,
                "client_base_url": self.config.ai_base_url,
                "api_key_configured": bool(self.config.ai_api_key)
            }, tool_name="ticmaker")

            response = await self.client.post(
                "/chat/completions",
                json=request_data
            )
            
            # Debug log: AI client response status
            mcp_debug(f"AI client HTTP response received", {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "request_url": str(response.url),
                "request_method": "POST"
            }, tool_name="ticmaker")
            
            if response.status_code == 200:
                data = response.json()
                
                # Debug log: AI response data structure
                mcp_debug(f"AI client successful response data", {
                    "response_keys": list(data.keys()) if isinstance(data, dict) else "not_dict",
                    "has_choices": "choices" in data if isinstance(data, dict) else False,
                    "choices_count": len(data.get("choices", [])) if isinstance(data, dict) else 0,
                    "model_used": data.get("model", "unknown") if isinstance(data, dict) else "unknown",
                    "usage": data.get("usage", {}) if isinstance(data, dict) else {}
                }, tool_name="ticmaker")
                
                if "choices" in data and len(data["choices"]) > 0:
                    raw_content = data["choices"][0]["message"]["content"]
                    content = raw_content.strip()
                    
                    # Debug log: AI generated content details
                    mcp_debug(f"AI content generation successful", {
                        "raw_content_length": len(raw_content),
                        "cleaned_content_length": len(content),
                        "content_preview": content[:100] + "..." if len(content) > 100 else content,
                        "finish_reason": data["choices"][0].get("finish_reason", "unknown"),
                        "choice_index": data["choices"][0].get("index", 0)
                    }, tool_name="ticmaker")
                    
                    # 清理可能导致JSON解析问题的字符
                    content = self._clean_content_for_json(content)
                    
                    # Debug log: Final processed content
                    mcp_debug(f"AI content cleaned and ready", {
                        "final_content_length": len(content),
                        "final_content_preview": content[:100] + "..." if len(content) > 100 else content,
                        "cleaning_applied": raw_content != content
                    }, tool_name="ticmaker")
                    
                    return content
                else:
                    # Debug log: Invalid response structure
                    mcp_debug(f"AI response missing choices or empty choices", {
                        "has_choices_key": "choices" in data if isinstance(data, dict) else False,
                        "choices_data": data.get("choices", []) if isinstance(data, dict) else [],
                        "full_response": data if isinstance(data, dict) else str(data)
                    }, tool_name="ticmaker")
            else:
                # Debug log: Non-200 status code
                try:
                    error_data = response.json() if response.content else {}
                except:
                    error_data = {"raw_content": response.text[:200] if response.text else "empty"}
                
                mcp_debug(f"AI client HTTP error response", {
                    "status_code": response.status_code,
                    "error_data": error_data,
                    "response_text_preview": response.text[:200] if hasattr(response, 'text') else "no_text"
                }, tool_name="ticmaker")
                    
        except Exception as e:
            # Debug log: Exception details
            mcp_debug(f"AI client exception occurred", {
                "exception_type": type(e).__name__,
                "exception_message": str(e),
                "exception_args": str(e.args) if hasattr(e, 'args') else "no_args",
                "ai_client_available": self.client is not None,
                "config_ai_enabled": self.config.ai_enabled,
                "config_api_key_set": bool(self.config.ai_api_key)
            }, tool_name="ticmaker")
            
            mcp_warning(f"AI client error: {e}", tool_name="ticmaker")
        
        # 如果AI调用失败，返回fallback内容
        fallback_intros = [
            f"🎓 欢迎学习「{course_title}」！这是一门精心设计的互动式课程。",
            f"📚 「{course_title}」将通过丰富的互动内容带你掌握核心知识。",
            f"✨ 开始「{course_title}」的精彩学习之旅吧！"
        ]
        selected_fallback = random.choice(fallback_intros)
        
        # Debug log: Using fallback content after AI failure
        mcp_debug(f"AI call failed, using fallback content", {
            "fallback_content": selected_fallback,
            "fallback_options_count": len(fallback_intros),
            "course_title": course_title,
            "fallback_reason": "ai_call_failed_or_invalid_response"
        }, tool_name="ticmaker")
        
        return selected_fallback
    
    def _clean_content_for_json(self, content: str) -> str:
        """清理内容中可能导致JSON解析问题的字符."""
        import re
        
        # 移除或替换LaTeX数学公式中的反斜杠
        content = re.sub(r'\\[()]', lambda m: m.group(0)[1:], content)  # \( -> (, \) -> )
        content = re.sub(r'\\[a-zA-Z]+', '', content)  # 移除LaTeX命令如 \alpha, \beta
        
        # 移除其他可能的转义字符
        content = content.replace('\\n', ' ')
        content = content.replace('\\t', ' ')
        content = content.replace('\\r', ' ')
        content = content.replace('\\"', '"')
        content = content.replace("\\'", "'")
        
        # 清理多余的空格
        content = re.sub(r'\s+', ' ', content)
        content = content.strip()
        
        # 如果内容过长，截断到合理长度
        if len(content) > 200:
            content = content[:197] + "..."
            
        return content
    
    async def close(self):
        """关闭AI客户端."""
        if self.client:
            await self.client.aclose()


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
        
        # 初始化AI客户端
        self.ai_client = TICMakerAIClient(config)
        
        mcp_info(f"[TICMAKER_CONFIG] Output directory: {self.output_dir}", tool_name="ticmaker")
        mcp_info(f"[TICMAKER_CONFIG] Default template: {self.config.default_template}", tool_name="ticmaker")
        mcp_info(f"[TICMAKER_CONFIG] AI enhancement: {self.config.ai_enhancement}", tool_name="ticmaker")
        mcp_info(f"[TICMAKER_CONFIG] AI client enabled: {self.config.ai_enabled}", tool_name="ticmaker")
        mcp_info(f"[TICMAKER_CONFIG] AI model: {self.config.ai_model}", tool_name="ticmaker")
        mcp_info(f"[TICMAKER_CONFIG] AI ai_api_key: {self.config.ai_api_key}", tool_name="ticmaker")
        
        # Log initialization to file
        mcp_info("TICMaker client initialized", {
            "output_dir": str(self.output_dir),
            "default_template": self.config.default_template,
            "ai_enhancement": self.config.ai_enhancement,
            "ai_enabled": self.config.ai_enabled,
            "ai_model": self.config.ai_model,
            "logging_available": True
        }, tool_name="ticmaker")
    
    async def create_interactive_course(
        self,
        user_input: str,
        course_title: Optional[str] = None,
        file_path: Optional[str] = None,
        content_type: Optional[str] = None,
        template_style: Optional[str] = None,
        session_context: Optional[Dict[str, Any]] = None
    ) -> TICMakerResult:
        """Create interactive teaching content."""
        start_time = datetime.now()
        
        try:
            mcp_info("🎯 ===== TICMaker Content Creation Started =====", tool_name="ticmaker")
            mcp_info(f"   💬 User Requirements: {user_input}", tool_name="ticmaker")
            mcp_info(f"   📄 Content Title: {course_title or 'Not specified'}", tool_name="ticmaker")
            mcp_info(f"   🎨 Content Type: {content_type or 'course'}", tool_name="ticmaker")
            mcp_info(f"   📁 File Path: {file_path or 'Auto-generate'}", tool_name="ticmaker")
            if session_context:
                mcp_info(f"   🔄 Session State: {session_context.get('session_state', 'Unknown')}", tool_name="ticmaker")
                mcp_info(f"   📋 Current Task: {session_context.get('current_task', 'Unknown')}", tool_name="ticmaker")
                mcp_info(f"   👤 Session User Input: {session_context.get('user_input', 'Unknown')[:50]}...", tool_name="ticmaker")
            
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
                mcp_info(f"📁 Generated filename: {filename}", tool_name="ticmaker")
            else:
                original_path = file_path
                file_path = Path(file_path)
                # Ensure file is in safe directory
                if not str(file_path.resolve()).startswith(str(self.output_dir.resolve())):
                    file_path = self.output_dir / Path(file_path).name
                    mcp_warning(f"⚠️ File path adjusted for security: {original_path} → {file_path}", tool_name="ticmaker")
            
            mcp_info(f"📄 Final file path: {file_path}", tool_name="ticmaker")
            
            # Check if modifying existing file
            file_exists = file_path.exists()
            mcp_info(f"📋 File exists: {file_exists}", tool_name="ticmaker")
            
            if file_exists:
                mcp_info("📖 Reading existing file content...", tool_name="ticmaker")
                # Read existing content and modify
                existing_content = file_path.read_text(encoding='utf-8')
                mcp_info(f"📏 Existing content length: {len(existing_content)} characters", tool_name="ticmaker")
                
                mcp_info("🔧 Modifying existing HTML content...", tool_name="ticmaker")
                html_content = await self._modify_html_content(existing_content, user_input)
            else:
                mcp_info("🆕 Creating new HTML content...", tool_name="ticmaker")
                # Create new page
                html_content = await self._generate_html_content(
                    user_input, 
                    course_title,
                    template_style or self.config.default_template,
                    content_type or "course",
                    session_context
                )
            
            # Check content size
            if len(html_content.encode('utf-8')) > self.config.max_file_size:
                return TICMakerResult(
                    success=False,
                    error=f"Generated content too large ({len(html_content)} characters > {self.config.max_file_size} bytes)"
                )
            
            # Write file
            mcp_info("💾 Writing HTML content to file...", tool_name="ticmaker")
            file_path.write_text(html_content, encoding='utf-8')
            
            # Get file info
            file_size = file_path.stat().st_size
            action = "Modified" if file_exists else "Created"
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            mcp_info(f"🎉 Interactive course {action.lower()} successfully", tool_name="ticmaker")
            mcp_info(f"📁 File path: {file_path}", tool_name="ticmaker")
            mcp_info(f"📏 File size: {file_size} bytes", tool_name="ticmaker")
            mcp_info(f"⏱️ Execution time: {execution_time:.2f}s", tool_name="ticmaker")
            mcp_info("🎯 ===== TICMaker Course Creation Completed =====", tool_name="ticmaker")
            
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
            mcp_error(f"💥 {error_msg}", tool_name="ticmaker")
            mcp_error(f"⏱️ Execution time before error: {execution_time:.2f}s", tool_name="ticmaker")
            mcp_error("🎯 ===== TICMaker Course Creation Failed =====", tool_name="ticmaker")
            
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
    
    async def modify_interactive_course(
        self,
        user_input: str,
        file_path: str,
        session_context: Optional[Dict[str, Any]] = None
    ) -> TICMakerResult:
        """Modify existing interactive teaching content."""
        start_time = datetime.now()
        
        try:
            mcp_info("🔧 ===== TICMaker Course Modification Started =====", tool_name="ticmaker")
            mcp_info(f"   💬 Modification Requirements: {user_input}", tool_name="ticmaker")
            mcp_info(f"   📁 Target File: {file_path}", tool_name="ticmaker")
            if session_context:
                mcp_info(f"   🔄 Session State: {session_context.get('session_state', 'Unknown')}", tool_name="ticmaker")
            
            # Log modification start to file
            mcp_info("Course modification started", {
                "user_input": user_input,
                "file_path": file_path,
                "session_context": session_context
            }, tool_name="ticmaker", session_id=session_context.get('session_id') if session_context else None)
            
            # Validate input
            if not user_input or not user_input.strip():
                mcp_error("Course modification failed - empty user input", tool_name="ticmaker")
                return TICMakerResult(
                    success=False,
                    error="User input is required for modification"
                )
            
            if not file_path:
                mcp_error("Course modification failed - no file path specified", tool_name="ticmaker")
                return TICMakerResult(
                    success=False,
                    error="File path is required for modification"
                )
            
            # Resolve and validate file path
            target_file = Path(file_path)
            if not str(target_file.resolve()).startswith(str(self.output_dir.resolve())):
                target_file = self.output_dir / Path(file_path).name
                mcp_warning(f"⚠️ File path adjusted for security: {file_path} → {target_file}", tool_name="ticmaker")
            
            # Check if file exists
            if not target_file.exists():
                mcp_error(f"Target file does not exist: {target_file}", tool_name="ticmaker")
                return TICMakerResult(
                    success=False,
                    error=f"File not found: {target_file}"
                )
            
            mcp_info("📖 Reading existing file content...", tool_name="ticmaker")
            # Read existing content
            existing_content = target_file.read_text(encoding='utf-8')
            mcp_info(f"📏 Existing content length: {len(existing_content)} characters", tool_name="ticmaker")
            
            mcp_info("🔧 Modifying existing HTML content...", tool_name="ticmaker")
            # Modify content
            modified_content = await self._modify_html_content(existing_content, user_input)
            
            # Check content size
            if len(modified_content.encode('utf-8')) > self.config.max_file_size:
                return TICMakerResult(
                    success=False,
                    error=f"Modified content too large ({len(modified_content)} characters > {self.config.max_file_size} bytes)"
                )
            
            # Write modified file
            mcp_info("💾 Writing modified content to file...", tool_name="ticmaker")
            target_file.write_text(modified_content, encoding='utf-8')
            
            # Get file info
            file_size = target_file.stat().st_size
            execution_time = (datetime.now() - start_time).total_seconds()
            
            mcp_info(f"🎉 Interactive course modified successfully", tool_name="ticmaker")
            mcp_info(f"📁 File path: {target_file}", tool_name="ticmaker")
            mcp_info(f"📏 File size: {file_size} bytes", tool_name="ticmaker")
            mcp_info(f"⏱️ Execution time: {execution_time:.2f}s", tool_name="ticmaker")
            mcp_info("🔧 ===== TICMaker Course Modification Completed =====", tool_name="ticmaker")
            
            # Log successful modification to file
            mcp_info("Course modification completed successfully", {
                "file_path": str(target_file),
                "file_size": file_size,
                "execution_time": execution_time,
                "content_length": len(modified_content),
                "session_context_included": session_context is not None
            }, tool_name="ticmaker", session_id=session_context.get('session_id') if session_context else None)
            
            return TICMakerResult(
                success=True,
                message="Interactive course modified successfully",
                execution_time=execution_time,
                metadata={
                    "file_path": str(target_file),
                    "file_size": file_size,
                    "action": "modified",
                    "user_input": user_input,
                    "tool_name": "modify_interactive_course",
                    "session_context": session_context
                }
            )
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            error_msg = f"Interactive course modification failed: {str(e)}"
            mcp_error(f"💥 {error_msg}", tool_name="ticmaker")
            mcp_error(f"⏱️ Execution time before error: {execution_time:.2f}s", tool_name="ticmaker")
            mcp_error("🔧 ===== TICMaker Course Modification Failed =====", tool_name="ticmaker")
            
            # Log error to file with detailed context
            mcp_error("Course modification failed with exception", {
                "error_message": str(e),
                "error_type": type(e).__name__,
                "execution_time": execution_time,
                "user_input": user_input,
                "file_path": file_path,
                "session_context": session_context
            }, tool_name="ticmaker", session_id=session_context.get('session_id') if session_context else None)
            
            return TICMakerResult(
                success=False,
                error=error_msg,
                execution_time=execution_time
            )
    
    async def generate_ai_course_intro(self, course_title: str, user_input: str) -> str:
        """Generate AI-powered course introduction text."""
        try:
            return await self.ai_client.generate_course_intro(course_title, user_input)
        except Exception as e:
            mcp_error(f"Error generating AI course intro: {str(e)}", tool_name="ticmaker")
            # Fallback to default message
            return f"🎯 欢迎学习{course_title}！这是一个基于您的需求定制的互动课程。"
    
    async def _generate_html_content(
        self, 
        user_input: str, 
        course_title: Optional[str] = None,
        template_style: str = "modern",
        content_type: str = "course",
        session_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate HTML content for interactive course."""
        # Extract title from user input if not provided
        title = course_title if course_title else self._extract_title_from_user_input(user_input)
        
        # Generate AI-powered course introduction
        ai_generated_intro = await self.generate_ai_course_intro(title, user_input)
        
        # Generate interactive template with AI content
        html_content = await self._generate_interactive_template(title, user_input, template_style, content_type, course_title, session_context, ai_generated_intro)
        
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
    
    async def _generate_interactive_template(
        self, 
        title: str, 
        user_input: str, 
        template_style: str = "modern",
        content_type: str = "course",
        course_title: Optional[str] = None,
        session_context: Optional[Dict[str, Any]] = None,
        ai_generated_intro: Optional[str] = None
    ) -> str:
        """Generate interactive HTML template."""
        
        # Ensure ai_generated_intro has a fallback value
        if ai_generated_intro is None:
            ai_generated_intro = "🎓 欢迎来到这个精心设计的互动内容！"
        
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
            "course": "互动课程",
            "slides": "演示文稿",
            "presentation": "展示内容", 
            "tutorial": "教程指南",
            "lesson": "学习课时",
            "workshop": "实践工坊"
        }
        
        content_emoji = content_emoji_map.get(content_type, "🎓")
        content_subtitle = content_subtitle_map.get(content_type, "互动内容")
        
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
        
        .header .content-type {{
            font-size: 1.1em;
            opacity: 0.9;
            font-weight: normal;
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
        
        @keyframes spin {{
            from {{ transform: rotate(0deg); }}
            to {{ transform: rotate(360deg); }}
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
            <h1>{content_emoji} {title}</h1>
            <div class="content-type">{content_subtitle}</div>
            {f'<h2>📚 {course_title}</h2>' if course_title else ''}
        </div>
        
        <div class="content">
            <div class="requirement-box">
                <strong>用户需求:</strong> {user_input}
            </div>
            
            <div class="interaction-area">
                <button class="interactive-button" onclick="showAICourseIntro()">点击交互</button>
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
        
        // AI-powered course introduction function
        async function showAICourseIntro() {{
            const contentArea = document.getElementById('dynamic-content');
            
            // Show loading message
            contentArea.innerHTML = `
                <div class="fade-in">
                    <h3>🤖 AI正在生成课程介绍...</h3>
                    <p style="font-size: 1.1em; margin: 20px 0; color: #6c757d;">请稍候，AI正在为您量身定制课程介绍内容...</p>
                    <div style="text-align: center; margin: 20px 0;">
                        <div style="display: inline-block; width: 20px; height: 20px; border: 2px solid #667eea; border-radius: 50%; border-top-color: transparent; animation: spin 1s linear infinite;"></div>
                    </div>
                </div>
            `;
            contentArea.className = 'content-area fade-in';
            
            try {{
                // Get course title and user input from the page
                const titleElement = document.querySelector('h1');
                const courseTitle = titleElement ? titleElement.textContent.trim() : '课程';
                const userInput = '{user_input}';
                
                // Use real AI-generated course introduction
                await new Promise(resolve => setTimeout(resolve, 1500)); // Simulate processing time for UX
                
                // AI-generated course introduction from backend
                const aiGeneratedIntro = `{ai_generated_intro}`;
                
                const randomIntro = aiGeneratedIntro;
                
                // Display the AI-generated introduction
                contentArea.innerHTML = `
                    <div class="fade-in">
                        <h3>🤖 AI生成的课程介绍</h3>
                        <div style="background: linear-gradient(135deg, #f8f9ff 0%, #e8f4ff 100%); padding: 25px; border-radius: 15px; margin: 20px 0; border: 1px solid #e3f2fd;">
                            <p style="font-size: 1.2em; line-height: 1.8; color: #2c3e50; margin: 0;">${{randomIntro}}</p>
                        </div>
                        <div style="text-align: center; margin: 20px 0;">
                            <small style="color: #6c757d; font-style: italic;">💡 此内容由AI根据您的需求智能生成</small>
                        </div>
                        <button class="interactive-button" onclick="resetContent()" style="margin-top: 15px;">返回</button>
                    </div>
                `;
            }} catch (error) {{
                // Error handling - show fallback content
                contentArea.innerHTML = `
                    <div class="fade-in">
                        <h3>🎯 课程介绍</h3>
                        <div style="background: #fff3cd; padding: 20px; border-radius: 10px; margin: 20px 0; border: 1px solid #ffeaa7;">
                            <p style="font-size: 1.2em; margin: 0;">🎉 欢迎学习${{courseTitle || '本课程'}}！这是一个基于您的需求定制的互动课程，让我们开始这段精彩的学习之旅吧！</p>
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
        metadata_context = session_context.get("metadata_context", {})
        
        # Build metadata context display
        metadata_html = ""
        if metadata_context:
            metadata_html = f"""
                    <hr style="margin: 15px 0; border: none; border-top: 1px dashed #ccc;">
                    <h5>📊 Metadata Context</h5>
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
                <h4>🔄 Session Context Information</h4>
                <div style="background: #f0f8ff; padding: 15px; border-radius: 8px; margin: 10px 0;">
                    <p><strong>🔍 Session State:</strong> <span style="color: #667eea; font-weight: 600;">{session_state}</span></p>
                    <p><strong>📋 Current Task:</strong> <span style="color: #764ba2; font-weight: 600;">{current_task}</span></p>
                    <p><strong>👤 Session User Input:</strong> <span style="color: #f5576c; font-style: italic;">{session_user_input[:100]}{'...' if len(session_user_input) > 100 else ''}</span></p>
                    {metadata_html}
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
                "description": "Create interactive teaching content, including HTML pages, slides, PPT, courses, etc., and publish them in HTML format",
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
            "modify_interactive_course": {
                "name": "modify_interactive_course",
                "description": "Modify interactive teaching content published in HTML format, including HTML pages, slides, PPT, courses, etc.",
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
    
    async def run(self):
        """Run the stdio MCP server."""
        mcp_info("🚀 Starting TICMaker stdio MCP server...", tool_name="ticmaker")
        mcp_info(f"📂 Output directory: {self.ticmaker_config.output_dir}", tool_name="ticmaker")
        mcp_info(f"🎨 Default template: {self.ticmaker_config.default_template}", tool_name="ticmaker")
        mcp_info("📡 Ready to receive MCP messages via stdio", tool_name="ticmaker")
        
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
                    
                    mcp_debug(f"📥 Received: {line}", tool_name="ticmaker")
                    
                    # Parse MCP message
                    try:
                        message_data = json.loads(line)
                        message = MCPMessage(**message_data)
                    except (json.JSONDecodeError, TypeError, ValueError) as e:
                        mcp_error(f"❌ Invalid JSON message: {str(e)}", tool_name="ticmaker")
                        continue
                    
                    # Process message
                    response = await self.handle_message(message)
                    
                    # Send response
                    if response:
                        response_json = response.to_dict()
                        response_line = json.dumps(response_json, ensure_ascii=False)
                        print(response_line, flush=True)
                        mcp_debug(f"📤 Sent: {response_line}", tool_name="ticmaker")
                    
                except Exception as e:
                    mcp_error(f"💥 Error processing message: {str(e)}", tool_name="ticmaker")
                    continue
                    
        except KeyboardInterrupt:
            mcp_info("🛑 Server stopped by user", tool_name="ticmaker")
        except Exception as e:
            mcp_error(f"💥 Server error: {str(e)}")
        finally:
            mcp_info("👋 TICMaker stdio MCP server shutting down", tool_name="ticmaker")
    
    async def handle_message(self, message: MCPMessage) -> Optional[MCPMessage]:
        """Handle incoming MCP message."""
        mcp_debug(f"🔄 Processing {message.method} message with id: {message.id}", tool_name="ticmaker")
        
        if message.method == "notifications/initialized":
            mcp_info("Received initialized notification", tool_name="ticmaker")
            return None
        
        if message.method == MCPMethods.INITIALIZE:
            # Initialization request
            mcp_info("🔧 Processing INITIALIZE request", tool_name="ticmaker")
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
            mcp_info("✅ Server initialized successfully", tool_name="ticmaker")
            return response
            
        elif message.method == MCPMethods.TOOLS_LIST:
            # List available tools
            mcp_info("🛠️ Processing TOOLS_LIST request", tool_name="ticmaker")
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
            mcp_debug(f"✅ TOOLS_LIST response: {len(tools_list)} tools")
            return response
            
        elif message.method == MCPMethods.TOOLS_CALL:
            # Execute tool
            mcp_info("⚡ Processing TOOLS_CALL request", tool_name="ticmaker")
            try:
                params = message.params or {}
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                
                mcp_info(f"🔧 Executing tool: {tool_name}", tool_name="ticmaker")
                mcp_debug(f"📝 Tool arguments: {arguments}", tool_name="ticmaker")
                
                if tool_name not in self.tools:
                    mcp_error(f"❌ Tool '{tool_name}' not found", tool_name="ticmaker")
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
                elif tool_name == "modify_interactive_course":
                    # Log tool execution start to file
                    mcp_debug(f"Executing tool: {tool_name}", {
                        "arguments": arguments,
                        "message_id": message.id
                    }, tool_name="ticmaker")
                    
                    result = await self._modify_interactive_course(arguments)
                else:
                    mcp_error(f"Unknown tool requested: {tool_name}", tool_name="ticmaker")
                    raise ValueError(f"Unknown tool: {tool_name}")
                
                mcp_info(f"✅ Tool '{tool_name}' completed successfully", tool_name="ticmaker")
                
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
                mcp_error(f"💥 Tool execution error: {str(e)}")
                
                return MCPMessage(
                    id=message.id,
                    error={
                        "code": MCPErrorCodes.INTERNAL_ERROR,
                        "message": str(e)
                    }
                )
        
        elif message.method == MCPMethods.PING:
            # Ping response
            mcp_info("🏓 Processing PING request", tool_name="ticmaker")
            response = MCPMessage(
                id=message.id,
                result={"pong": True}
            )
            mcp_debug("✅ PING response: pong", tool_name="ticmaker")
            return response
            
        elif message.method == MCPMethods.RESOURCES_LIST:
            # List available resources (none for TICMaker)
            mcp_info("📚 Processing RESOURCES_LIST request", tool_name="ticmaker")
            response = MCPMessage(
                id=message.id,
                result={"resources": []}
            )
            mcp_debug("✅ RESOURCES_LIST response: empty list", tool_name="ticmaker")
            return response
            
        elif message.method == MCPMethods.PROMPTS_LIST:
            # List available prompts (none for TICMaker)
            mcp_info("💬 Processing PROMPTS_LIST request", tool_name="ticmaker")
            response = MCPMessage(
                id=message.id,
                result={"prompts": []}
            )
            mcp_debug("✅ PROMPTS_LIST response: empty list", tool_name="ticmaker")
            return response
            
        else:
            # Unknown method
            mcp_error(f"❌ Unknown method requested: {message.method}", tool_name="ticmaker")
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
            content_type = arguments.get("content_type")
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
                content_type=content_type,
                template_style=template_style,
                session_context=session_context
            )
            
        except Exception as e:
            mcp_error(f"💥 _create_interactive_course error: {str(e)}")
            return TICMakerResult(
                success=False,
                error=f"Course creation failed: {str(e)}"
            )
    
    async def _modify_interactive_course(self, arguments: Dict[str, Any]) -> TICMakerResult:
        """Modify interactive course with given arguments."""
        try:
            # Extract arguments with defaults
            user_input = arguments.get("user_input")
            file_path = arguments.get("file_path")
            session_context = arguments.get("_session_context")
            
            # Validate required fields
            if not user_input:
                return TICMakerResult(
                    success=False,
                    error="'user_input' field is required"
                )
            
            if not file_path:
                return TICMakerResult(
                    success=False,
                    error="'file_path' field is required"
                )
            
            # Modify interactive course
            return await self.ticmaker_client.modify_interactive_course(
                user_input=user_input,
                file_path=file_path,
                session_context=session_context
            )
            
        except Exception as e:
            mcp_error(f"💥 _modify_interactive_course error: {str(e)}")
            return TICMakerResult(
                success=False,
                error=f"Course modification failed: {str(e)}"
            )


def load_config(config_path: Optional[Path] = None) -> TICMakerConfig:
    """Load TICMaker configuration from SimaCode config system."""
    try:
        # Load SimaCode configuration
        config = load_simacode_config(config_path=config_path, tool_name="ticmaker")
        mcp_info("[CONFIG_LOAD] Successfully loaded SimaCode configuration", tool_name="ticmaker")
        
        # Create TICMaker configuration from SimaCode config
        ticmaker_config = TICMakerConfig.from_simacode_config(config)
        
        # Log configuration details
        mcp_info("TICMaker config loaded from SimaCode", {
            "config_source": "simacode_config",
            "output_dir": ticmaker_config.output_dir,
            "default_template": ticmaker_config.default_template,
            "ai_enabled": ticmaker_config.ai_enabled,
            "ai_model": ticmaker_config.ai_model,
            "ai_base_url": ticmaker_config.ai_base_url,
            "ai_api_key_configured": bool(ticmaker_config.ai_api_key)
        }, tool_name="ticmaker")
        
        return ticmaker_config
        
    except Exception as e:
        mcp_warning(f"⚠️ Failed to load config from SimaCode: {str(e)}", tool_name="ticmaker")
        mcp_info("📋 Using default configuration", tool_name="ticmaker")
        
        # Return default config - environment variables will be handled in from_simacode_config
        return TICMakerConfig()


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
        mcp_debug("🐛 Debug logging enabled", tool_name="ticmaker")
    
    # Load configuration
    config_path = Path(args.config) if args.config else None
    ticmaker_config = load_config(config_path=config_path)
    
    # Override with command line arguments if provided
    if args.output_dir:
        ticmaker_config.output_dir = args.output_dir
    if args.template:
        ticmaker_config.default_template = args.template
    
    mcp_info(f"📋 Configuration loaded:", tool_name="ticmaker")
    mcp_info(f"   📂 Output directory: {ticmaker_config.output_dir}", tool_name="ticmaker")
    mcp_info(f"   🎨 Default template: {ticmaker_config.default_template}", tool_name="ticmaker")
    mcp_info(f"   🤖 AI enhancement: {ticmaker_config.ai_enhancement}", tool_name="ticmaker")
    
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
