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
import uuid
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
    """HTTP client for remote project analyzer REST service with async job support."""

    def __init__(self, config: ProjectAnalyzeConfig):
        """
        Initialize project analyzer executor.

        Args:
            config: project analyzer configuration containing base URL, timeout, etc.
        """
        self.config = config
        self.base_url = config.base_url.rstrip('/')
        self.session = None
        # Job tracking
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self._job_tasks: Dict[str, asyncio.Task] = {}
        
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
    
    async def analyze_project_from_zip(self, user_id: str, zip_content: str, project_name: Optional[str] = None, description: Optional[str] = None) -> str:
        """
        Submit project analysis job and return job ID immediately.

        Args:
            user_id: User identifier
            zip_content: Base64 encoded ZIP file content
            project_name: Optional project name
            description: Optional project description

        Returns:
            str: Job ID for tracking the analysis
        """
        job_id = str(uuid.uuid4())

        # Initialize job status
        self.jobs[job_id] = {
            "job_id": job_id,
            "status": "submitted",
            "user_id": user_id,
            "project_name": project_name,
            "description": description,
            "submit_time": datetime.now().isoformat(),
            "start_time": None,
            "complete_time": None,
            "progress": 0,
            "result": None,
            "error": None
        }

        logger.info(f"Submitted project analysis job {job_id} for user {user_id}, project: {project_name or 'unnamed'}")

        # Start background task
        task = asyncio.create_task(self._execute_analysis_job(job_id, user_id, zip_content, project_name, description))
        self._job_tasks[job_id] = task

        return job_id
    
    async def health_check(self) -> Dict[str, Any]:
        """Check health of remote project analyzer service."""
        try:
            result = await self._make_request("health", method="GET")
            return result
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}
    
    async def _execute_analysis_job(self, job_id: str, user_id: str, zip_content: str, project_name: Optional[str], description: Optional[str]) -> None:
        """Execute the actual project analysis in the background."""
        start_time = asyncio.get_event_loop().time()
        endpoint = "api/project-analyze/analyze-project"

        try:
            # Update job status
            self.jobs[job_id].update({
                "status": "running",
                "start_time": datetime.now().isoformat(),
                "progress": 10
            })

            logger.info(f"Starting analysis job {job_id}")

            # Decode base64 content to bytes
            try:
                zip_bytes = base64.b64decode(zip_content)
                self.jobs[job_id]["progress"] = 20
            except Exception as e:
                raise Exception(f"Invalid base64 ZIP content: {str(e)}")

            # Attempt analysis with retries
            for attempt in range(self.config.max_retries):
                try:
                    self.jobs[job_id]["progress"] = 30 + (attempt * 20)

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

                    # Update job completion
                    self.jobs[job_id].update({
                        "status": "completed" if result.get("success", False) else "failed",
                        "complete_time": datetime.now().isoformat(),
                        "progress": 100,
                        "result": {
                            "success": result.get("success", False),
                            "data": result,
                            "error": result.get("error"),
                            "execution_time": execution_time,
                            "operation": "analyze_project_from_zip"
                        }
                    })

                    logger.info(f"Job {job_id} completed successfully in {execution_time:.2f}s")
                    return

                except Exception as e:
                    logger.error(f"Job {job_id} attempt {attempt + 1} failed: {str(e)}")
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(self.config.retry_delay)
                    else:
                        raise e

        except Exception as e:
            execution_time = asyncio.get_event_loop().time() - start_time
            error_msg = f"Job {job_id} failed after all retries: {str(e)}"
            logger.error(error_msg)

            # Update job failure
            self.jobs[job_id].update({
                "status": "failed",
                "complete_time": datetime.now().isoformat(),
                "progress": 0,
                "error": error_msg,
                "result": {
                    "success": False,
                    "error": error_msg,
                    "execution_time": execution_time,
                    "operation": "analyze_project_from_zip"
                }
            })
        finally:
            # Cleanup task reference
            if job_id in self._job_tasks:
                del self._job_tasks[job_id]

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job status by ID."""
        return self.jobs.get(job_id)

    async def list_jobs(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all jobs, optionally filtered by user."""
        jobs = list(self.jobs.values())
        if user_id:
            jobs = [job for job in jobs if job.get("user_id") == user_id]
        return jobs

    async def cleanup_completed_jobs(self, max_age_hours: int = 24) -> int:
        """Clean up completed jobs older than max_age_hours."""
        cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)
        removed_count = 0

        job_ids_to_remove = []
        for job_id, job_info in self.jobs.items():
            if job_info["status"] in ["completed", "failed"]:
                if job_info.get("complete_time"):
                    complete_time = datetime.fromisoformat(job_info["complete_time"]).timestamp()
                    if complete_time < cutoff_time:
                        job_ids_to_remove.append(job_id)

        for job_id in job_ids_to_remove:
            del self.jobs[job_id]
            # Cancel task if still running
            if job_id in self._job_tasks:
                self._job_tasks[job_id].cancel()
                del self._job_tasks[job_id]
            removed_count += 1

        logger.info(f"Cleaned up {removed_count} old jobs")
        return removed_count

    async def close(self):
        """Close HTTP session and cancel all running jobs."""
        # Cancel all running tasks
        for task in self._job_tasks.values():
            task.cancel()

        # Wait for tasks to complete
        if self._job_tasks:
            await asyncio.gather(*self._job_tasks.values(), return_exceptions=True)

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
                "description": "Submit frontend project analysis job from ZIP file upload (returns job ID immediately)",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "description": "User identifier for the analysis",
                            "default": "default_user"
                        },
                        "zip_file_path": {
                            "type": "string",
                            "description": "Path to the ZIP file containing the frontend project"
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
                    "required": ["zip_file_path"]
                }
            },
            "get_job_status": {
                "name": "get_job_status",
                "description": "Get the status and result of a project analysis job",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "job_id": {
                            "type": "string",
                            "description": "Job ID returned from project_analyze_from_zip"
                        }
                    },
                    "required": ["job_id"]
                }
            },
            "list_jobs": {
                "name": "list_jobs",
                "description": "List all project analysis jobs, optionally filtered by user",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "user_id": {
                            "type": "string",
                            "description": "Optional user ID to filter jobs"
                        }
                    },
                    "required": []
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
                zip_file_path = arguments.get("zip_file_path", "")
                project_name = arguments.get("project_name")
                description = arguments.get("description")

                if not zip_file_path:
                    return MCPMessage(
                        id=message.id,
                        error={
                            "code": MCPErrorCodes.INVALID_PARAMS,
                            "message": "ZIP file path is required"
                        }
                    )

                # Read ZIP file and encode to base64
                try:
                    zip_path = Path(zip_file_path)
                    if not zip_path.exists():
                        return MCPMessage(
                            id=message.id,
                            error={
                                "code": MCPErrorCodes.INVALID_PARAMS,
                                "message": f"ZIP file not found: {zip_file_path}"
                            }
                        )

                    if not zip_path.is_file():
                        return MCPMessage(
                            id=message.id,
                            error={
                                "code": MCPErrorCodes.INVALID_PARAMS,
                                "message": f"Path is not a file: {zip_file_path}"
                            }
                        )

                    # Read file and encode to base64
                    with open(zip_path, 'rb') as f:
                        zip_bytes = f.read()
                    zip_content = base64.b64encode(zip_bytes).decode('utf-8')

                    logger.info(f"Successfully read ZIP file: {zip_file_path} ({len(zip_bytes)} bytes)")

                except Exception as e:
                    return MCPMessage(
                        id=message.id,
                        error={
                            "code": MCPErrorCodes.INTERNAL_ERROR,
                            "message": f"Failed to read ZIP file: {str(e)}"
                        }
                    )

                job_id = await self.project_analyzer.analyze_project_from_zip(
                    user_id, zip_content, project_name, description
                )

                # Format response with job ID
                response_data = {
                    "success": True,
                    "job_id": job_id,
                    "status": "submitted",
                    "message": f"Project analysis job {job_id} submitted successfully",
                    "user_id": user_id,
                    "project_name": project_name,
                    "zip_file_path": zip_file_path,
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
                        "isError": False
                    }
                )

            elif tool_name == "get_job_status":
                # Get job status
                job_id = arguments.get("job_id", "")

                if not job_id:
                    return MCPMessage(
                        id=message.id,
                        error={
                            "code": MCPErrorCodes.INVALID_PARAMS,
                            "message": "Job ID is required"
                        }
                    )

                job_status = await self.project_analyzer.get_job_status(job_id)

                if job_status is None:
                    return MCPMessage(
                        id=message.id,
                        error={
                            "code": MCPErrorCodes.INVALID_PARAMS,
                            "message": f"Job {job_id} not found"
                        }
                    )

                response_data = {
                    "success": True,
                    "job_status": job_status,
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
                        "isError": False
                    }
                )

            elif tool_name == "list_jobs":
                # List jobs
                user_id = arguments.get("user_id")

                jobs = await self.project_analyzer.list_jobs(user_id)

                response_data = {
                    "success": True,
                    "jobs": jobs,
                    "count": len(jobs),
                    "filter_user_id": user_id,
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
                        "isError": False
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

        # Clean up old jobs before shutdown
        await self.project_analyzer.cleanup_completed_jobs(max_age_hours=1)

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
