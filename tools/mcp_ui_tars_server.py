#!/usr/bin/env python3
"""
UI-TARS-MCP Server

A MCP server that runs on a third-party server and communicates with SimaCode 
via streamable HTTP protocol. It provides UI automation capabilities by calling
UI-TARS with natural language instructions.

Features:
- HTTP-based MCP server
- UI-TARS command execution with full parameters
- Natural language UI automation
- Website opening and auto-verification
"""

import asyncio
import json
import logging
import subprocess
import sys
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, AsyncGenerator
from dataclasses import dataclass
from datetime import datetime

# Environment configuration support
try:
    from dotenv import load_dotenv
    DOTENV_AVAILABLE = True
except ImportError:
    DOTENV_AVAILABLE = False
    print("Warning: python-dotenv not available. Consider installing with: pip install python-dotenv", file=sys.stderr)

# HTTP server support
try:
    from aiohttp import web, WSMsgType
    from aiohttp.web import Request, Response, WebSocketResponse
except ImportError:
    print("Error: aiohttp package not available. Please install with: pip install aiohttp", file=sys.stderr)
    sys.exit(1)

# Add parent directory to path for MCP imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# MCP Protocol imports (using our existing MCP implementation)
from src.simacode.mcp.protocol import MCPMessage, MCPMethods, MCPErrorCodes


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class UITARSResult:
    """Result from UI-TARS command execution."""
    success: bool
    output: str
    error: Optional[str] = None
    execution_time: float = 0.0
    command: str = ""


@dataclass
class UITARSConfig:
    """Configuration for UI-TARS execution."""
    provider: str = "volcengine"
    model: str = "doubao-1-5-thinking-vision-pro-250428"
    api_key: str = ""
    command: str = "agent-tars"


class UITARSExecutor:
    """
    Executor for UI-TARS commands.
    
    This class handles the execution of UI-TARS commands with full parameter specification.
    Command format: agent-tars run --provider volcengine --model doubao-1-5-thinking-vision-pro-250428 --apiKey {apiKey} --input "指令"
    """
    
    def __init__(self, config: UITARSConfig):
        """
        Initialize UI-TARS executor.
        
        Args:
            config: UI-TARS configuration containing provider, model, API key, etc.
        """
        self.config = config
        self.execution_timeout = 300  # 5 minutes default timeout
        
    async def execute_instruction(self, instruction: str, timeout: Optional[float] = None) -> UITARSResult:
        """
        Execute a UI-TARS instruction.
        
        Args:
            instruction: Natural language instruction for UI-TARS
            timeout: Optional timeout in seconds
            
        Returns:
            UITARSResult: Execution result
        """
        start_time = asyncio.get_event_loop().time()
        
        # Prepare command with full parameters as per documentation:
        # agent-tars run --provider volcengine --model doubao-1-5-thinking-vision-pro-250428 --apiKey {apiKey} --input "指令"
        command = [
            self.config.command, 
            "run",
            "--provider", self.config.provider,
            "--model", self.config.model,
            "--apiKey", self.config.api_key,
            "--input", instruction
        ]
        command_str = " ".join([
            self.config.command, 
            "run",
            "--provider", self.config.provider,
            "--model", self.config.model,
            "--apiKey", self.config.api_key,
            "--input", f'"{instruction}"'
        ])
        
        logger.info(f"Executing UI-TARS command: {command_str}")
        
        try:
            # Execute command with timeout
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.getcwd()
            )
            
            # Wait for completion with timeout
            timeout_value = timeout or self.execution_timeout
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_value
            )
            
            execution_time = asyncio.get_event_loop().time() - start_time
            
            # Process results
            output = stdout.decode('utf-8') if stdout else ""
            error_output = stderr.decode('utf-8') if stderr else ""
            
            success = process.returncode == 0
            
            result = UITARSResult(
                success=success,
                output=output,
                error=error_output if not success else None,
                execution_time=execution_time,
                command=command_str
            )
            
            logger.info(f"UI-TARS execution completed in {execution_time:.2f}s, success: {success}")
            
            return result
            
        except asyncio.TimeoutError:
            execution_time = asyncio.get_event_loop().time() - start_time
            logger.error(f"UI-TARS command timed out after {timeout_value}s")
            
            return UITARSResult(
                success=False,
                output="",
                error=f"Command timed out after {timeout_value} seconds",
                execution_time=execution_time,
                command=command_str
            )
            
        except Exception as e:
            execution_time = asyncio.get_event_loop().time() - start_time
            logger.error(f"UI-TARS command failed: {str(e)}")
            
            return UITARSResult(
                success=False,
                output="",
                error=str(e),
                execution_time=execution_time,
                command=command_str
            )


class UITARSMCPServer:
    """
    HTTP-based MCP server for UI-TARS integration.
    
    This server provides MCP protocol compliance over HTTP and integrates
    with UI-TARS for UI automation tasks.
    """
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8080, ui_tars_config: Optional[UITARSConfig] = None):
        """
        Initialize UI-TARS MCP server.
        
        Args:
            host: Server host address
            port: Server port number
            ui_tars_config: UI-TARS configuration
        """
        self.host = host
        self.port = port
        self.app = web.Application()
        
        # Initialize UI-TARS executor with configuration
        self.ui_tars_config = ui_tars_config or UITARSConfig()
        self.ui_tars = UITARSExecutor(self.ui_tars_config)
        
        # Setup routes
        self._setup_routes()
        
        # MCP server info
        self.server_info = {
            "name": "ui-tars-mcp-server",
            "version": "1.0.0",
            "description": "UI-TARS MCP Server for UI Automation"
        }
        
        # Available tools
        self.tools = {
            "open_website_with_verification": {
                "name": "open_website_with_verification",
                "description": "Open a website and automatically handle verification processes",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The website URL to open"
                        },
                        "verification_instructions": {
                            "type": "string",
                            "description": "Natural language instructions for handling verification (e.g., 'complete captcha', 'click verify button')",
                            "default": "automatically handle any verification challenges"
                        },
                        "timeout": {
                            "type": "number",
                            "description": "Timeout in seconds for the operation",
                            "default": 300
                        }
                    },
                    "required": ["url"]
                }
            }
        }
        
        logger.info(f"UI-TARS MCP Server initialized on {host}:{port}")
    
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
            "ui_tars_config": {
                "provider": self.ui_tars_config.provider,
                "model": self.ui_tars_config.model,
                "api_key_configured": bool(self.ui_tars_config.api_key)
            },
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
            return await self._execute_tool(message)
            
        elif message.method == MCPMethods.PING:
            # Ping response
            return MCPMessage(
                id=message.id,
                result={"pong": True}
            )
            
        elif message.method == MCPMethods.RESOURCES_LIST:
            # List available resources (none for UI TARS)
            return MCPMessage(
                id=message.id,
                result={"resources": []}
            )
            
        elif message.method == MCPMethods.PROMPTS_LIST:
            # List available prompts (none for UI TARS)
            return MCPMessage(
                id=message.id,
                result={"prompts": []}
            )
            
        else:
            # Method not found
            return MCPMessage(
                id=message.id,
                error={
                    "code": MCPErrorCodes.METHOD_NOT_FOUND,
                    "message": f"Method '{message.method}' not found"
                }
            )
    
    async def _execute_tool(self, message: MCPMessage) -> MCPMessage:
        """Execute a tool and return the result."""
        try:
            params = message.params or {}
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            if tool_name not in self.tools:
                return MCPMessage(
                    id=message.id,
                    error={
                        "code": MCPErrorCodes.TOOL_NOT_FOUND,
                        "message": f"Tool '{tool_name}' not found"
                    }
                )
            
            # Execute the appropriate tool
            if tool_name == "open_website_with_verification":
                result = await self._open_website_with_verification(arguments)
            else:
                raise ValueError(f"Unknown tool: {tool_name}")
            
            return MCPMessage(
                id=message.id,
                result={
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2, ensure_ascii=False)
                        }
                    ],
                    "isError": not result.get("success", False)
                }
            )
            
        except Exception as e:
            logger.error(f"Tool execution error: {str(e)}")
            
            return MCPMessage(
                id=message.id,
                error={
                    "code": MCPErrorCodes.INTERNAL_ERROR,
                    "message": str(e)
                }
            )
    
    async def _open_website_with_verification(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Open a website and automatically handle verification processes.
        
        Args:
            arguments: Tool arguments containing url, verification_instructions, timeout
            
        Returns:
            Dict containing execution results
        """
        url = arguments.get("url")
        verification_instructions = arguments.get("verification_instructions", "automatically handle any verification challenges")
        timeout = arguments.get("timeout", 300)
        
        if not url:
            return {
                "success": False,
                "error": "URL parameter is required",
                "timestamp": datetime.now().isoformat()
            }
        
        # Construct UI-TARS instruction
        instruction = f"Open the website {url} and {verification_instructions}. Wait for the page to fully load and handle any security checks, captchas, or verification dialogs that appear."
        
        logger.info(f"Opening website with verification: {url}")
        
        # Execute UI-TARS command
        result = await self.ui_tars.execute_instruction(instruction, timeout)
        
        return {
            "success": result.success,
            "url": url,
            "verification_instructions": verification_instructions,
            "output": result.output,
            "error": result.error,
            "execution_time": result.execution_time,
            "command_executed": result.command,
            "timestamp": datetime.now().isoformat()
        }
    
    
    async def start_server(self):
        """Start the HTTP server."""
        logger.info(f"Starting UI-TARS MCP Server on {self.host}:{self.port}")
        
        # Log UI-TARS configuration status
        if self.ui_tars_config.api_key:
            logger.info(f"UI-TARS configured: {self.ui_tars_config.provider} / {self.ui_tars_config.model}")
        else:
            logger.warning("UI-TARS API key not configured - functionality will be limited")
        
        runner = web.AppRunner(self.app)
        await runner.setup()
        
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        
        logger.info(f"UI-TARS MCP Server started successfully")
        logger.info(f"Health check: http://{self.host}:{self.port}/health")
        logger.info(f"MCP HTTP endpoint: http://{self.host}:{self.port}/mcp")
        logger.info(f"MCP WebSocket endpoint: ws://{self.host}:{self.port}/mcp/ws")
        
        return runner
    
    async def stop_server(self, runner):
        """Stop the HTTP server."""
        logger.info("Shutting down UI-TARS MCP Server...")
        
        # Stop HTTP server
        await runner.cleanup()
        logger.info("UI-TARS MCP Server stopped")


def load_env_config():
    """Load environment configuration from .env.mcp file."""
    env_file = Path(__file__).parent.parent / ".env.mcp"
    
    if DOTENV_AVAILABLE and env_file.exists():
        logger.info(f"Loading environment from: {env_file}")
        load_dotenv(env_file)
    elif env_file.exists():
        logger.warning(f"Found {env_file} but python-dotenv not available. Install with: pip install python-dotenv")
    else:
        logger.info(f"No .env.mcp file found at: {env_file}")


async def main():
    """Main entry point."""
    import argparse
    
    # Load environment configuration first
    load_env_config()
    
    parser = argparse.ArgumentParser(description="UI-TARS MCP Server")
    parser.add_argument("--host", default=os.getenv("UI_TARS_HOST", "0.0.0.0"), help="Server host address")
    parser.add_argument("--port", type=int, default=int(os.getenv("UI_TARS_PORT", "8080")), help="Server port number")
    parser.add_argument("--tars-command", default=os.getenv("TARS_COMMAND", "agent-tars"), help="UI-TARS base command (default: agent-tars)")
    
    # UI-TARS configuration (read from environment by default)
    parser.add_argument("--provider", default=os.getenv("AGENT_PROVIDER", "volcengine"), help="UI-TARS provider (default: volcengine)")
    parser.add_argument("--model", default=os.getenv("AGENT_MODEL", "doubao-1-5-thinking-vision-pro-250428"), help="UI-TARS model")
    parser.add_argument("--api-key", default=os.getenv("AGENT_API_KEY"), help="UI-TARS API key (required for functionality)")
    
    args = parser.parse_args()
    
    # Configuration from command line (overrides environment)
    provider = args.provider
    model = args.model
    api_key = args.api_key
    
    # Create UI-TARS configuration
    ui_tars_config = UITARSConfig(
        provider=provider,
        model=model,
        api_key=api_key or "",
        command=args.tars_command
    )
    
    if not api_key:
        logger.warning("No API key provided - UI-TARS functionality will be limited")
        logger.info("Use --api-key to provide API key for full functionality")
    
    # Create and start server
    server = UITARSMCPServer(host=args.host, port=args.port, ui_tars_config=ui_tars_config)
    
    runner = await server.start_server()
    
    try:
        # Keep server running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
    except asyncio.CancelledError:
        logger.info("Server cancelled, shutting down...")
    finally:
        await server.stop_server(runner)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped by user.")
    except Exception as e:
        print(f"Server error: {e}")
        sys.exit(1)