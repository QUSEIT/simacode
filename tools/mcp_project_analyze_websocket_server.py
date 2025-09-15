#!/usr/bin/env python3
"""
Project Analyzer MCP Proxy Server

A MCP server that proxies requests to a remote project analyzer REST service.
This server runs locally on SimaCode and communicates with a remote
project analyzer REST service via HTTP.

Features:
- HTTP-based MCP server with WebSocket support
- Proxy requests to remote project analyzer REST service
- Frontend project analysis capabilities from ZIP files
- Health monitoring and error handling
"""

import asyncio
import json
import logging
import sys
import os
import aiohttp
import base64
from pathlib import Path
from typing import Any, Dict, List, Optional
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

# MCP Protocol imports
from src.simacode.mcp.protocol import MCPMessage, MCPMethods, MCPErrorCodes

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class ProjectAnalyzeResult:
    """Result from project analyzer operation execution."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    execution_time: float = 0.0
    operation: str = ""


@dataclass
class ProjectAnalyzeConfig:
    """Configuration for project analyzer REST service connection."""
    base_url: str = "http://localhost:8002"
    timeout: int = 300  # Project analysis can take longer
    max_retries: int = 3
    retry_delay: float = 2.0


class ProjectAnalyzeExecutor:
    """HTTP client for remote project analyzer REST service."""
    
    def __init__(self, config: ProjectAnalyzeConfig):
        """
        Initialize project analyzer executor.
        
        Args:
            config: project analyzer configuration containing base URL, timeout, etc.
        """
        self.config = config
        self.base_url = config.base_url.rstrip('/')
        self.session = None
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.timeout)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session
    
    async def _make_request(self, endpoint: str, method: str = "POST", data: Optional[Dict[str, Any]] = None, form_data: Optional[aiohttp.FormData] = None) -> Dict[str, Any]:
        """Make HTTP request to project analyzer REST service."""
        session = await self._get_session()
        url = f"{self.base_url}/{endpoint}"
        
        logger.info(f"Making {method} request to: {url}")
        if data:
            logger.debug(f"Request data: {data}")
        
        try:
            if method.upper() == "GET":
                async with session.get(url) as response:
                    result = await response.json()
                    logger.debug(f"Response: {result}")
                    return result
            else:
                # POST with form data or JSON
                if form_data:
                    async with session.post(url, data=form_data) as response:
                        result = await response.json()
                        logger.debug(f"Response: {result}")
                        return result
                else:
                    async with session.post(url, json=data) as response:
                        result = await response.json()
                        logger.debug(f"Response: {result}")
                        return result
        except aiohttp.ClientError as e:
            logger.error(f"HTTP request failed: {str(e)}")
            return {"success": False, "error": f"HTTP request failed: {str(e)}"}
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return {"success": False, "error": f"Unexpected error: {str(e)}"}
    
    async def analyze_project_from_zip(self, user_id: str, zip_content: str, project_name: Optional[str] = None, description: Optional[str] = None) -> ProjectAnalyzeResult:
        """
        Analyze project from ZIP file via HTTP.
        
        Args:
            user_id: User identifier
            zip_content: Base64 encoded ZIP file content
            project_name: Optional project name
            description: Optional project description
            
        Returns:
            ProjectAnalyzeResult: Execution result
        """
        start_time = asyncio.get_event_loop().time()
        endpoint = "api/project-analyze/analyze-project"
        
        logger.info(f"Analyzing project for user {user_id}, project: {project_name or 'unnamed'}")
        
        # Decode base64 content to bytes
        try:
            zip_bytes = base64.b64decode(zip_content)
        except Exception as e:
            execution_time = asyncio.get_event_loop().time() - start_time
            return ProjectAnalyzeResult(
                success=False,
                error=f"Invalid base64 ZIP content: {str(e)}",
                execution_time=execution_time,
                operation="analyze_project_from_zip"
            )
        
        for attempt in range(self.config.max_retries):
            try:
                # Create form data
                form_data = aiohttp.FormData()
                form_data.add_field('file', zip_bytes, filename=f'{project_name or "project"}.zip', content_type='application/zip')
                form_data.add_field('user_id', user_id)
                if project_name:
                    form_data.add_field('project_name', project_name)
                if description:
                    form_data.add_field('description', description)
                
                result = await self._make_request(endpoint, method="POST", form_data=form_data)
                execution_time = asyncio.get_event_loop().time() - start_time
                
                return ProjectAnalyzeResult(
                    success=result.get("success", False),
                    data=result,
                    error=result.get("error"),
                    execution_time=execution_time,
                    operation="analyze_project_from_zip"
                )
                
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(self.config.retry_delay)
                else:
                    execution_time = asyncio.get_event_loop().time() - start_time
                    return ProjectAnalyzeResult(
                        success=False,
                        error=f"All {self.config.max_retries} attempts failed. Last error: {str(e)}",
                        execution_time=execution_time,
                        operation="analyze_project_from_zip"
                    )
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of remote project analyzer service."""
        try:
            result = await self._make_request("health", method="GET")
            return result
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def close(self):
        """Close HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()


class ProjectAnalyzeMCPServer:
    """
    HTTP-based MCP server for project analyzer integration.
    
    This server provides MCP protocol compliance over HTTP and proxies
    requests to a remote project analyzer REST service.
    """
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8083, project_analyzer_config: Optional[ProjectAnalyzeConfig] = None):
        """
        Initialize project analyzer MCP server.
        
        Args:
            host: Server host address
            port: Server port number
            project_analyzer_config: project analyzer configuration
        """
        self.host = host
        self.port = port
        self.app = web.Application()
        
        # Initialize project analyzer executor
        self.project_analyzer_config = project_analyzer_config or ProjectAnalyzeConfig()
        self.project_analyzer = ProjectAnalyzeExecutor(self.project_analyzer_config)
        
        # Setup routes
        self._setup_routes()
        
        # MCP server info
        self.server_info = {
            "name": "project_analyzer_proxy_mcp_server",
            "version": "1.0.0",
            "description": "Project Analyzer MCP Proxy Server for Frontend Project Analysis"
        }
        
        # Available tools
        self.tools = {
            "project_analyze_from_zip": {
                "name": "project_analyze_from_zip",
                "description": "Analyze frontend project structure and routes from ZIP file upload",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "description": "User identifier for the analysis",
                            "default": "default_user"
                        },
                        "zip_content": {
                            "type": "string",
                            "description": "Base64 encoded ZIP file content of the frontend project"
                        },
                        "project_name": {
                            "type": "string",
                            "description": "Optional name for the project being analyzed"
                        },
                        "description": {
                            "type": "string",
                            "description": "Optional description of the project"
                        }
                    },
                    "required": ["zip_content"]
                }
            }
        }
        
        logger.info(f"Project Analyzer MCP Proxy Server initialized on {host}:{port}")
        logger.info(f"Remote project analyzer service: {self.project_analyzer_config.base_url}")
    
    def _setup_routes(self):
        """Setup HTTP routes for MCP protocol."""
        self.app.router.add_get('/health', self._health_check)
        self.app.router.add_post('/mcp', self._handle_mcp_request)
        self.app.router.add_get('/mcp/ws', self._handle_websocket)
        
    async def _health_check(self, request: Request) -> Response:
        """Health check endpoint."""
        # Check remote project analyzer service health
        remote_health = await self.project_analyzer.health_check()
        
        health_data = {
            "status": "healthy" if remote_health.get("status") == "healthy" else "degraded",
            "server": self.server_info,
            "remote_project_analyzer": remote_health,
            "config": {
                "base_url": self.project_analyzer_config.base_url,
                "timeout": self.project_analyzer_config.timeout,
                "max_retries": self.project_analyzer_config.max_retries
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
            # List available resources (none for project analyzer)
            return MCPMessage(
                id=message.id,
                result={"resources": []}
            )

        elif message.method == MCPMethods.PROMPTS_LIST:
            # List available prompts (none for project analyzer)
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
            
            if tool_name == "project_analyze_from_zip":
                # Execute project analysis from ZIP
                user_id = arguments.get("user_id", "default_user")
                zip_content = arguments.get("zip_content", "")
                project_name = arguments.get("project_name")
                description = arguments.get("description")
                
                if not zip_content:
                    return MCPMessage(
                        id=message.id,
                        error={
                            "code": MCPErrorCodes.INVALID_PARAMS,
                            "message": "ZIP content is required"
                        }
                    )
                
                result = await self.project_analyzer.analyze_project_from_zip(
                    user_id, zip_content, project_name, description
                )
                
                # Format response
                response_data = {
                    "success": result.success,
                    "operation": result.operation,
                    "data": result.data,
                    "error": result.error,
                    "execution_time": result.execution_time,
                    "user_id": user_id,
                    "project_name": project_name,
                    "timestamp": datetime.now().isoformat()
                }
                
                return MCPMessage(
                    id=message.id,
                    result={
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(response_data, indent=2, ensure_ascii=False)
                            }
                        ],
                        "isError": not result.success
                    }
                )
            else:
                return MCPMessage(
                    id=message.id,
                    error={
                        "code": MCPErrorCodes.TOOL_NOT_FOUND,
                        "message": f"Unknown tool: {tool_name}"
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
    
    async def start_server(self):
        """Start the HTTP server."""
        logger.info(f"Starting Project Analyzer MCP Proxy Server on {self.host}:{self.port}")
        
        # Log configuration
        logger.info(f"Remote project analyzer service: {self.project_analyzer_config.base_url}")
        logger.info(f"Timeout: {self.project_analyzer_config.timeout}s")
        logger.info(f"Max retries: {self.project_analyzer_config.max_retries}")
        
        # Check remote service health
        health = await self.project_analyzer.health_check()
        if health.get("status") == "healthy":
            logger.info("Remote project analyzer service is healthy")
        else:
            logger.warning(f"Remote project analyzer service health check failed: {health}")
        
        runner = web.AppRunner(self.app)
        await runner.setup()
        
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        
        logger.info(f"Project Analyzer MCP Proxy Server started successfully")
        logger.info(f"Health check: http://{self.host}:{self.port}/health")
        logger.info(f"MCP HTTP endpoint: http://{self.host}:{self.port}/mcp")
        logger.info(f"MCP WebSocket endpoint: ws://{self.host}:{self.port}/mcp/ws")
        
        return runner
    
    async def stop_server(self, runner):
        """Stop the HTTP server."""
        logger.info("Shutting down Project Analyzer MCP Proxy Server...")
        
        # Close project analyzer executor
        await self.project_analyzer.close()
        
        # Stop HTTP server
        await runner.cleanup()
        logger.info("Project Analyzer MCP Proxy Server stopped")


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
    
    parser = argparse.ArgumentParser(description="Project Analyzer MCP Proxy Server")
    parser.add_argument("--host", default=os.getenv("PROJECT_ANALYZER_PROXY_HOST", "0.0.0.0"), help="Server host address")
    parser.add_argument("--port", type=int, default=int(os.getenv("PROJECT_ANALYZER_PROXY_PORT", "8083")), help="Server port number")
    
    # project analyzer configuration
    parser.add_argument("--project-analyzer-url", default=os.getenv("PROJECT_ANALYZER_REST_URL", "http://localhost:8002"), help="Project analyzer REST service URL")
    parser.add_argument("--timeout", type=int, default=int(os.getenv("PROJECT_ANALYZER_TIMEOUT", "300")), help="Request timeout in seconds")
    parser.add_argument("--max-retries", type=int, default=int(os.getenv("PROJECT_ANALYZER_MAX_RETRIES", "3")), help="Maximum retry attempts")
    parser.add_argument("--retry-delay", type=float, default=float(os.getenv("PROJECT_ANALYZER_RETRY_DELAY", "2.0")), help="Delay between retries")
    
    args = parser.parse_args()
    
    # Create project analyzer configuration
    project_analyzer_config = ProjectAnalyzeConfig(
        base_url=args.project_analyzer_url,
        timeout=args.timeout,
        max_retries=args.max_retries,
        retry_delay=args.retry_delay
    )
    
    # Create and start server
    server = ProjectAnalyzeMCPServer(host=args.host, port=args.port, project_analyzer_config=project_analyzer_config)
    
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
