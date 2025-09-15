#!/usr/bin/env python3
"""
MMmaker stdio MCP Server

A stdio-based MCP server that provides voice generation capabilities.
It communicates with SimaCode via stdio protocol and provides text-to-speech conversion.

Features:
- stdio-based MCP server
- Text-to-speech voice generation
- OpenAI compatible API support
- Support for multiple voice models
- Asynchronous audio file generation
- Configuration via .simacode/config.yaml

Configuration:
This tool reads configuration from SimaCode's config system. Example config.yaml:

mmmaker:
  output_dir: ".simacode/mcp/mmmaker_output"
  default_voice: "alloy"
  ai_enabled: true
  ai_base_url: "https://openai.pgpt.cloud/v1"
  ai_api_key: "your_api_key_here"
  ai_model: "tts-1"

Environment variables (fallback):
- MMMAKER_OUTPUT_DIR
- MMMAKER_VOICE
- MMMAKER_AI_API_KEY
"""

import asyncio
import json
import logging
import os
import sys
import uuid
import base64
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


@dataclass
class MMmakerConfig:
    """Configuration for MMmaker voice generation."""
    output_dir: str = ".simacode/mcp/mmmaker_output"
    default_voice: str = "alloy"
    max_file_size: int = 1024 * 1024 * 25  # 25MB
    allowed_audio_formats: List[str] = None
    # AI客户端配置
    ai_enabled: bool = True
    ai_base_url: str = "https://openai.pgpt.cloud/v1"
    ai_api_key: str = ""
    ai_model: str = "tts-1"
    ai_voice: str = "alloy"
    ai_speed: float = 1.0
    ai_response_format: str = "mp3"

    def __post_init__(self):
        """Set default values after initialization."""
        if self.allowed_audio_formats is None:
            self.allowed_audio_formats = [".mp3", ".wav", ".opus", ".aac", ".flac"]

    @classmethod
    def from_simacode_config(cls, config: Config) -> 'MMmakerConfig':
        """Create MMmakerConfig from SimaCode Config object."""
        # Try to get mmmaker config section, fallback to empty dict
        try:
            mmmaker_config = getattr(config, 'mmmaker', {})
        except AttributeError:
            mmmaker_config = {}

        # Extract basic settings with fallbacks
        output_dir = mmmaker_config.get('output_dir', ".simacode/mcp/mmmaker_output")
        default_voice = mmmaker_config.get('default_voice', "alloy")

        # Extract AI settings from mmmaker config with fallbacks
        ai_config = mmmaker_config.get('ai', {})
        ai_enabled_default = ai_config.get('enabled', True)
        ai_base_url_default = ai_config.get('base_url', "https://openai.pgpt.cloud/v1")
        ai_api_key_default = ai_config.get('api_key', "")
        ai_model_default = ai_config.get('model', "tts-1")
        ai_voice_default = ai_config.get('voice', "alloy")
        ai_speed_default = ai_config.get('speed', 1.0)
        ai_response_format_default = ai_config.get('response_format', "mp3")

        # Override with environment variables (priority: env vars > config)
        output_dir = os.getenv("MMMAKER_OUTPUT_DIR", output_dir)
        default_voice = os.getenv("MMMAKER_VOICE", default_voice)

        # AI configuration with environment override
        ai_enabled_env = os.getenv("MMMAKER_AI_ENABLED", str(ai_enabled_default))
        ai_enabled = ai_enabled_env.lower() == "true"

        ai_base_url = os.getenv("MMMAKER_AI_BASE_URL", ai_base_url_default)
        ai_api_key = os.getenv("MMMAKER_AI_API_KEY", ai_api_key_default)
        ai_model = os.getenv("MMMAKER_AI_MODEL", ai_model_default)
        ai_voice = os.getenv("MMMAKER_AI_VOICE", ai_voice_default)

        try:
            ai_speed = float(os.getenv("MMMAKER_AI_SPEED", str(ai_speed_default)))
        except ValueError:
            ai_speed = ai_speed_default

        ai_response_format = os.getenv("MMMAKER_AI_RESPONSE_FORMAT", ai_response_format_default)

        return cls(
            output_dir=output_dir,
            default_voice=default_voice,
            ai_enabled=ai_enabled,
            ai_base_url=ai_base_url,
            ai_api_key=ai_api_key,
            ai_model=ai_model,
            ai_voice=ai_voice,
            ai_speed=ai_speed,
            ai_response_format=ai_response_format
        )


@dataclass
class MMmakerResult:
    """Result from MMmaker voice generation operation."""
    success: bool
    message: str = ""
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Optional[Dict[str, Any]] = None


class MMmakerAIClient:
    """OpenAI兼容的AI客户端用于语音生成."""

    def __init__(self, config: MMmakerConfig):
        """初始化AI客户端."""
        self.config = config
        self.client = None
        if config.ai_enabled and config.ai_api_key:
            self.client = httpx.AsyncClient(
                base_url=config.ai_base_url,
                headers={"Authorization": f"Bearer {config.ai_api_key}"},
                timeout=60.0  # Longer timeout for audio generation
            )

    async def generate_speech(self, text: str, voice: Optional[str] = None, speed: Optional[float] = None) -> Optional[bytes]:
        """生成语音音频数据."""
        if not self.client:
            # Debug log: AI client not available
            mcp_debug(f"AI client not available for speech generation", {
                "ai_enabled": self.config.ai_enabled,
                "api_key_configured": bool(self.config.ai_api_key),
                "client_initialized": self.client is not None,
                "text_length": len(text),
                "fallback_reason": "no_client_instance"
            }, tool_name="mmmaker")

            return None

        try:
            # 使用提供的参数或默认值
            voice_to_use = voice or self.config.ai_voice
            speed_to_use = speed or self.config.ai_speed

            # 构建请求数据
            request_data = {
                "model": self.config.ai_model,
                "input": text,
                "voice": voice_to_use,
                "response_format": self.config.ai_response_format,
                "speed": speed_to_use
            }

            # Debug log: AI request details
            mcp_debug(f"Sending AI speech generation request", {
                "model": self.config.ai_model,
                "voice": voice_to_use,
                "speed": speed_to_use,
                "response_format": self.config.ai_response_format,
                "text_length": len(text),
                "text_preview": text[:100] + "..." if len(text) > 100 else text,
                "client_base_url": self.config.ai_base_url,
                "api_key_configured": bool(self.config.ai_api_key)
            }, tool_name="mmmaker")

            response = await self.client.post(
                "/audio/speech",
                json=request_data
            )

            # Debug log: AI client response status
            mcp_debug(f"AI client HTTP response received", {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "content_type": response.headers.get("content-type", "unknown"),
                "content_length": response.headers.get("content-length", "unknown"),
                "request_url": str(response.url),
                "request_method": "POST"
            }, tool_name="mmmaker")

            if response.status_code == 200:
                audio_data = response.content

                # Debug log: AI response data details
                mcp_debug(f"AI speech generation successful", {
                    "audio_data_size": len(audio_data),
                    "content_type": response.headers.get("content-type", "unknown"),
                    "voice_used": voice_to_use,
                    "model_used": self.config.ai_model,
                    "speed_used": speed_to_use,
                    "format_used": self.config.ai_response_format
                }, tool_name="mmmaker")

                return audio_data
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
                }, tool_name="mmmaker")

        except Exception as e:
            # Debug log: Exception details
            mcp_debug(f"AI client exception occurred", {
                "exception_type": type(e).__name__,
                "exception_message": str(e),
                "exception_args": str(e.args) if hasattr(e, 'args') else "no_args",
                "ai_client_available": self.client is not None,
                "config_ai_enabled": self.config.ai_enabled,
                "config_api_key_set": bool(self.config.ai_api_key)
            }, tool_name="mmmaker")

            mcp_warning(f"AI speech generation error: {e}", tool_name="mmmaker")

        return None

    async def close(self):
        """关闭AI客户端."""
        if self.client:
            await self.client.aclose()


class MMmakerClient:
    """Client for MMmaker voice generation operations."""

    def __init__(self, config: MMmakerConfig):
        """
        Initialize MMmaker client.

        Args:
            config: MMmaker configuration containing settings
        """
        self.config = config
        self.output_dir = Path(config.output_dir)
        self.output_dir.mkdir(exist_ok=True)

        # 初始化AI客户端
        self.ai_client = MMmakerAIClient(config)

        mcp_info(f"[MMMAKER_CONFIG] Output directory: {self.output_dir}", tool_name="mmmaker")
        mcp_info(f"[MMMAKER_CONFIG] Default voice: {self.config.default_voice}", tool_name="mmmaker")
        mcp_info(f"[MMMAKER_CONFIG] AI client enabled: {self.config.ai_enabled}", tool_name="mmmaker")
        mcp_info(f"[MMMAKER_CONFIG] AI model: {self.config.ai_model}", tool_name="mmmaker")
        mcp_info(f"[MMMAKER_CONFIG] AI voice: {self.config.ai_voice}", tool_name="mmmaker")

        # Log initialization to file
        mcp_info("MMmaker client initialized", {
            "output_dir": str(self.output_dir),
            "default_voice": self.config.default_voice,
            "ai_enabled": self.config.ai_enabled,
            "ai_model": self.config.ai_model,
            "ai_voice": self.config.ai_voice,
            "logging_available": True
        }, tool_name="mmmaker")

    async def generate_voice(
        self,
        text: str,
        voice: Optional[str] = None,
        speed: Optional[float] = None,
        file_path: Optional[str] = None,
        session_context: Optional[Dict[str, Any]] = None
    ) -> MMmakerResult:
        """Generate voice audio from text."""
        start_time = datetime.now()

        try:
            mcp_info("🎯 ===== MMmaker Voice Generation Started =====", tool_name="mmmaker")
            mcp_info(f"   🗣️ Text Input: {text[:100]}{'...' if len(text) > 100 else ''}", tool_name="mmmaker")
            mcp_info(f"   🎵 Voice: {voice or self.config.ai_voice}", tool_name="mmmaker")
            mcp_info(f"   ⚡ Speed: {speed or self.config.ai_speed}", tool_name="mmmaker")
            mcp_info(f"   📁 File Path: {file_path or 'Auto-generate'}", tool_name="mmmaker")
            if session_context:
                mcp_info(f"   🔄 Session State: {session_context.get('session_state', 'Unknown')}", tool_name="mmmaker")
                mcp_info(f"   📋 Current Task: {session_context.get('current_task', 'Unknown')}", tool_name="mmmaker")

            # Log voice generation start to file
            mcp_info("Voice generation started", {
                "text_length": len(text),
                "text_preview": text[:100] + "..." if len(text) > 100 else text,
                "voice": voice or self.config.ai_voice,
                "speed": speed or self.config.ai_speed,
                "file_path": str(file_path) if file_path else None,
                "session_context": session_context
            }, tool_name="mmmaker", session_id=session_context.get('session_id') if session_context else None)

            # Validate input
            if not text or not text.strip():
                mcp_error("Voice generation failed - empty text input", tool_name="mmmaker")
                return MMmakerResult(
                    success=False,
                    error="Text input is required for voice generation"
                )

            # Determine file path
            if not file_path:
                # Generate default filename
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                random_id = str(uuid.uuid4())[:8]
                filename = f"mmmaker_voice_{timestamp}_{random_id}.{self.config.ai_response_format}"
                file_path = self.output_dir / filename
                mcp_info(f"📁 Generated filename: {filename}", tool_name="mmmaker")
            else:
                original_path = file_path
                file_path = Path(file_path)
                # Ensure file is in safe directory
                if not str(file_path.resolve()).startswith(str(self.output_dir.resolve())):
                    file_path = self.output_dir / Path(file_path).name
                    mcp_warning(f"⚠️ File path adjusted for security: {original_path} → {file_path}", tool_name="mmmaker")

            mcp_info(f"📄 Final file path: {file_path}", tool_name="mmmaker")

            # Generate voice audio
            mcp_info("🤖 Generating voice audio with AI...", tool_name="mmmaker")
            audio_data = await self.ai_client.generate_speech(
                text=text,
                voice=voice,
                speed=speed
            )

            if not audio_data:
                mcp_error("AI voice generation failed - no audio data returned", tool_name="mmmaker")
                return MMmakerResult(
                    success=False,
                    error="Failed to generate voice audio. Please check AI client configuration."
                )

            # Check audio data size
            if len(audio_data) > self.config.max_file_size:
                return MMmakerResult(
                    success=False,
                    error=f"Generated audio too large ({len(audio_data)} bytes > {self.config.max_file_size} bytes)"
                )

            # Write audio file
            mcp_info("💾 Writing audio data to file...", tool_name="mmmaker")
            file_path.write_bytes(audio_data)

            # Get file info
            file_size = file_path.stat().st_size
            execution_time = (datetime.now() - start_time).total_seconds()

            mcp_info(f"🎉 Voice generation completed successfully", tool_name="mmmaker")
            mcp_info(f"📁 File path: {file_path}", tool_name="mmmaker")
            mcp_info(f"📏 File size: {file_size} bytes", tool_name="mmmaker")
            mcp_info(f"⏱️ Execution time: {execution_time:.2f}s", tool_name="mmmaker")
            mcp_info("🎯 ===== MMmaker Voice Generation Completed =====", tool_name="mmmaker")

            # Log successful completion to file
            mcp_info(f"Voice generation completed successfully", {
                "file_path": str(file_path),
                "file_size": file_size,
                "execution_time": execution_time,
                "audio_duration_estimate": f"{len(text) * 0.1:.1f}s",
                "voice_used": voice or self.config.ai_voice,
                "speed_used": speed or self.config.ai_speed,
                "session_context_included": session_context is not None
            }, tool_name="mmmaker", session_id=session_context.get('session_id') if session_context else None)

            return MMmakerResult(
                success=True,
                message="Voice generation completed successfully",
                execution_time=execution_time,
                metadata={
                    "file_path": str(file_path),
                    "file_size": file_size,
                    "voice": voice or self.config.ai_voice,
                    "speed": speed or self.config.ai_speed,
                    "text_length": len(text),
                    "audio_format": self.config.ai_response_format,
                    "session_context": session_context
                }
            )

        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            error_msg = f"Voice generation failed: {str(e)}"
            mcp_error(f"💥 {error_msg}", tool_name="mmmaker")
            mcp_error(f"⏱️ Execution time before error: {execution_time:.2f}s", tool_name="mmmaker")
            mcp_error("🎯 ===== MMmaker Voice Generation Failed =====", tool_name="mmmaker")

            # Log error to file with detailed context
            mcp_error("Voice generation failed with exception", {
                "error_message": str(e),
                "error_type": type(e).__name__,
                "execution_time": execution_time,
                "text_length": len(text) if text else 0,
                "voice": voice or self.config.ai_voice,
                "speed": speed or self.config.ai_speed,
                "file_path": str(file_path) if file_path else None,
                "session_context": session_context
            }, tool_name="mmmaker", session_id=session_context.get('session_id') if session_context else None)

            return MMmakerResult(
                success=False,
                error=error_msg,
                execution_time=execution_time
            )


class MMmakerStdioMCPServer:
    """
    stdio-based MCP server for MMmaker voice generation.

    This server communicates via standard input/output (stdio) and provides
    text-to-speech voice generation capabilities.
    """

    def __init__(self, mmmaker_config: Optional[MMmakerConfig] = None):
        """
        Initialize MMmaker stdio MCP server.

        Args:
            mmmaker_config: Configuration for MMmaker operations
        """
        # Initialize MMmaker client with configuration
        self.mmmaker_config = mmmaker_config or MMmakerConfig()
        self.mmmaker_client = MMmakerClient(self.mmmaker_config)

        # MCP server info
        self.server_info = {
            "name": "mmmaker-stdio-mcp-server",
            "version": "1.0.0",
            "description": "MMmaker stdio MCP Server for Text-to-Speech Voice Generation"
        }

        # Available tools
        self.tools = {
            "generate_voice": {
                "name": "generate_voice",
                "description": "Generate speech audio from text using AI voice synthesis. Converts text to natural-sounding voice audio files.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Text content to convert to speech audio"
                        },
                        "voice": {
                            "type": "string",
                            "enum": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
                            "description": "Voice model to use for speech generation. Options: alloy, echo, fable, onyx, nova, shimmer",
                            "default": "alloy"
                        },
                        "speed": {
                            "type": "number",
                            "minimum": 0.25,
                            "maximum": 4.0,
                            "description": "Speed of speech generation (0.25 to 4.0, default: 1.0)",
                            "default": 1.0
                        },
                        "file_path": {
                            "type": "string",
                            "description": "Optional file path for the audio output - will be auto-generated if not provided"
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
                    "required": ["text"]
                }
            }
        }

    async def run(self):
        """Run the stdio MCP server."""
        mcp_info("🚀 Starting MMmaker stdio MCP server...", tool_name="mmmaker")
        mcp_info(f"📂 Output directory: {self.mmmaker_config.output_dir}", tool_name="mmmaker")
        mcp_info(f"🎵 Default voice: {self.mmmaker_config.default_voice}", tool_name="mmmaker")
        mcp_info("📡 Ready to receive MCP messages via stdio", tool_name="mmmaker")

        # Log server startup to file
        mcp_info("MMmaker MCP server started", {
            "server_version": self.server_info["version"],
            "output_dir": self.mmmaker_config.output_dir,
            "default_voice": self.mmmaker_config.default_voice,
            "ai_enabled": self.mmmaker_config.ai_enabled
        }, tool_name="mmmaker")

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

                    mcp_debug(f"📥 Received: {line}", tool_name="mmmaker")

                    # Parse MCP message
                    try:
                        message_data = json.loads(line)
                        message = MCPMessage(**message_data)
                    except (json.JSONDecodeError, TypeError, ValueError) as e:
                        mcp_error(f"❌ Invalid JSON message: {str(e)}", tool_name="mmmaker")
                        continue

                    # Process message
                    response = await self.handle_message(message)

                    # Send response
                    if response:
                        response_json = response.to_dict()
                        response_line = json.dumps(response_json, ensure_ascii=False)
                        print(response_line, flush=True)
                        mcp_debug(f"📤 Sent: {response_line}", tool_name="mmmaker")

                except Exception as e:
                    mcp_error(f"💥 Error processing message: {str(e)}", tool_name="mmmaker")
                    continue

        except KeyboardInterrupt:
            mcp_info("🛑 Server stopped by user", tool_name="mmmaker")
        except Exception as e:
            mcp_error(f"💥 Server error: {str(e)}")
        finally:
            mcp_info("👋 MMmaker stdio MCP server shutting down", tool_name="mmmaker")
            await self.mmmaker_client.ai_client.close()

    async def handle_message(self, message: MCPMessage) -> Optional[MCPMessage]:
        """Handle incoming MCP message."""
        mcp_debug(f"🔄 Processing {message.method} message with id: {message.id}", tool_name="mmmaker")

        if message.method == "notifications/initialized":
            mcp_info("Received initialized notification", tool_name="mmmaker")
            return None

        if message.method == MCPMethods.INITIALIZE:
            # Initialization request
            mcp_info("🔧 Processing INITIALIZE request", tool_name="mmmaker")
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
            mcp_info("✅ Server initialized successfully", tool_name="mmmaker")
            return response

        elif message.method == MCPMethods.TOOLS_LIST:
            # List available tools
            mcp_info("🛠️ Processing TOOLS_LIST request", tool_name="mmmaker")
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
            mcp_info("⚡ Processing TOOLS_CALL request", tool_name="mmmaker")
            try:
                params = message.params or {}
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                mcp_info(f"🔧 Executing tool: {tool_name}", tool_name="mmmaker")
                mcp_debug(f"📝 Tool arguments: {arguments}", tool_name="mmmaker")

                if tool_name not in self.tools:
                    mcp_error(f"❌ Tool '{tool_name}' not found", tool_name="mmmaker")
                    return MCPMessage(
                        id=message.id,
                        error={
                            "code": MCPErrorCodes.TOOL_NOT_FOUND,
                            "message": f"Tool '{tool_name}' not found"
                        }
                    )

                if tool_name == "generate_voice":
                    # Log tool execution start to file
                    mcp_debug(f"Executing tool: {tool_name}", {
                        "arguments": arguments,
                        "message_id": message.id
                    }, tool_name="mmmaker")

                    result = await self._generate_voice(arguments)
                else:
                    mcp_error(f"Unknown tool requested: {tool_name}", tool_name="mmmaker")
                    raise ValueError(f"Unknown tool: {tool_name}")

                mcp_info(f"✅ Tool '{tool_name}' completed successfully", tool_name="mmmaker")

                # Log tool execution completion to file
                mcp_debug(f"Tool execution completed: {tool_name}", {
                    "success": result.success,
                    "execution_time": result.execution_time,
                    "message_id": message.id
                }, tool_name="mmmaker")

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
            mcp_info("🏓 Processing PING request", tool_name="mmmaker")
            response = MCPMessage(
                id=message.id,
                result={"pong": True}
            )
            mcp_debug("✅ PING response: pong", tool_name="mmmaker")
            return response

        elif message.method == MCPMethods.RESOURCES_LIST:
            # List available resources (none for MMmaker)
            mcp_info("📚 Processing RESOURCES_LIST request", tool_name="mmmaker")
            response = MCPMessage(
                id=message.id,
                result={"resources": []}
            )
            mcp_debug("✅ RESOURCES_LIST response: empty list", tool_name="mmmaker")
            return response

        elif message.method == MCPMethods.PROMPTS_LIST:
            # List available prompts (none for MMmaker)
            mcp_info("💬 Processing PROMPTS_LIST request", tool_name="mmmaker")
            response = MCPMessage(
                id=message.id,
                result={"prompts": []}
            )
            mcp_debug("✅ PROMPTS_LIST response: empty list", tool_name="mmmaker")
            return response

        else:
            # Unknown method
            mcp_error(f"❌ Unknown method requested: {message.method}", tool_name="mmmaker")
            return MCPMessage(
                id=message.id,
                error={
                    "code": MCPErrorCodes.METHOD_NOT_FOUND,
                    "message": f"Unknown method: {message.method}"
                }
            )

    async def _generate_voice(self, arguments: Dict[str, Any]) -> MMmakerResult:
        """Generate voice with given arguments."""
        try:
            # Extract arguments with defaults
            text = arguments.get("text")
            voice = arguments.get("voice")
            speed = arguments.get("speed")
            file_path = arguments.get("file_path")
            session_context = arguments.get("_session_context")

            # Validate required fields
            if not text:
                return MMmakerResult(
                    success=False,
                    error="'text' field is required"
                )

            # Generate voice
            return await self.mmmaker_client.generate_voice(
                text=text,
                voice=voice,
                speed=speed,
                file_path=file_path,
                session_context=session_context
            )

        except Exception as e:
            mcp_error(f"💥 _generate_voice error: {str(e)}")
            return MMmakerResult(
                success=False,
                error=f"Voice generation failed: {str(e)}"
            )


def load_config(config_path: Optional[Path] = None) -> MMmakerConfig:
    """Load MMmaker configuration from SimaCode config system."""
    try:
        # Load SimaCode configuration
        config = load_simacode_config(config_path=config_path, tool_name="mmmaker")
        mcp_info("[CONFIG_LOAD] Successfully loaded SimaCode configuration", tool_name="mmmaker")

        # Create MMmaker configuration from SimaCode config
        mmmaker_config = MMmakerConfig.from_simacode_config(config)

        # Log configuration details
        mcp_info("MMmaker config loaded from SimaCode", {
            "config_source": "simacode_config",
            "output_dir": mmmaker_config.output_dir,
            "default_voice": mmmaker_config.default_voice,
            "ai_enabled": mmmaker_config.ai_enabled,
            "ai_model": mmmaker_config.ai_model,
            "ai_base_url": mmmaker_config.ai_base_url,
            "ai_api_key_configured": bool(mmmaker_config.ai_api_key)
        }, tool_name="mmmaker")

        return mmmaker_config

    except Exception as e:
        mcp_warning(f"⚠️ Failed to load config from SimaCode: {str(e)}", tool_name="mmmaker")
        mcp_info("📋 Using default configuration", tool_name="mmmaker")

        # Return default config - environment variables will be handled in from_simacode_config
        return MMmakerConfig()


async def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="MMmaker stdio MCP Server")
    parser.add_argument("--config", help="Configuration file path")
    parser.add_argument("--output-dir", help="Output directory for generated audio files")
    parser.add_argument("--voice", help="Default voice model", choices=["alloy", "echo", "fable", "onyx", "nova", "shimmer"])
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        mcp_debug("🐛 Debug logging enabled", tool_name="mmmaker")

    # Load configuration
    config_path = Path(args.config) if args.config else None
    mmmaker_config = load_config(config_path=config_path)

    # Override with command line arguments if provided
    if args.output_dir:
        mmmaker_config.output_dir = args.output_dir
    if args.voice:
        mmmaker_config.default_voice = args.voice
        mmmaker_config.ai_voice = args.voice

    mcp_info(f"📋 Configuration loaded:", tool_name="mmmaker")
    mcp_info(f"   📂 Output directory: {mmmaker_config.output_dir}", tool_name="mmmaker")
    mcp_info(f"   🎵 Default voice: {mmmaker_config.default_voice}", tool_name="mmmaker")
    mcp_info(f"   🤖 AI enabled: {mmmaker_config.ai_enabled}", tool_name="mmmaker")

    # Create and run server
    server = MMmakerStdioMCPServer(mmmaker_config)
    await server.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped by user.", file=sys.stderr)
    except Exception as e:
        print(f"Server error: {str(e)}", file=sys.stderr)
        sys.exit(1)
