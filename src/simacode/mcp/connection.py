"""
MCP connection management and transport implementations.

This module provides different transport mechanisms for MCP communication,
including stdio, WebSocket, and HTTP transports.
"""

import asyncio
import contextlib
import logging
import os
import sys
import importlib.util
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod
import websockets

from .protocol import MCPTransport
from .exceptions import MCPConnectionError, MCPTimeoutError

logger = logging.getLogger(__name__)


class StdioTransport(MCPTransport):
    """
    Standard input/output transport for MCP communication.
    
    This transport communicates with MCP servers through subprocess
    stdin/stdout pipes, which is the most common MCP transport method.
    """
    
    def __init__(self, command: list, args: list = None, env: Dict[str, str] = None):
        self.command = command
        self.args = args or []
        self.env = env
        self.process: Optional[asyncio.subprocess.Process] = None
        self._connected = False
        self._read_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        
    async def connect(self) -> bool:
        """Start subprocess and establish stdio connection."""
        try:
            logger.info(f"Starting MCP server: {' '.join(self.command + self.args)}")
            
            # Start subprocess
            # Use shared environment preparation method
            process_env = self._prepare_environment()
            
            # Set larger limit for MCP communication to handle large responses
            # Default asyncio readline limit is 64KB, increase to 10MB for large email attachments
            limit = 10 * 1024 * 1024  # 10MB
            
            self.process = await asyncio.create_subprocess_exec(
                *self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=process_env,
                limit=limit
            )
            
            # Check if process started successfully
            if self.process.returncode is not None:
                raise MCPConnectionError(f"Process failed to start: {self.command[0]}")
            
            self._connected = True
            logger.info(f"MCP server started successfully (PID: {self.process.pid})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start MCP server: {str(e)}")
            raise MCPConnectionError(f"Failed to connect via stdio: {str(e)}")
    
    async def disconnect(self) -> None:
        """Terminate subprocess and cleanup."""
        if self.process and self._connected:
            try:
                logger.info("Shutting down MCP server...")
                
                # Close stdin to signal shutdown
                if self.process.stdin and not self.process.stdin.is_closing():
                    self.process.stdin.close()
                    await self.process.stdin.wait_closed()
                
                # Wait for graceful shutdown
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    # Force terminate if graceful shutdown fails
                    logger.warning("Graceful shutdown timeout, terminating process")
                    self.process.terminate()
                    try:
                        await asyncio.wait_for(self.process.wait(), timeout=2.0)
                    except asyncio.TimeoutError:
                        # Kill if terminate doesn't work
                        logger.warning("Terminate timeout, killing process")
                        self.process.kill()
                        await self.process.wait()
                
                logger.info("MCP server shutdown complete")
                
            except Exception as e:
                logger.error(f"Error during MCP server shutdown: {str(e)}")
            finally:
                self._connected = False
                self.process = None
    
    async def send(self, message: bytes) -> None:
        """Send message to subprocess stdin."""
        if not self.is_connected():
            raise MCPConnectionError("Transport not connected")
        
        if not self.process or not self.process.stdin:
            raise MCPConnectionError("Process stdin not available")
        
        async with self._write_lock:
            try:
                # Add newline separator for line-based communication
                self.process.stdin.write(message + b'\n')
                await self.process.stdin.drain()
                
            except Exception as e:
                logger.error(f"Failed to send message: {str(e)}")
                raise MCPConnectionError(f"Failed to send message: {str(e)}")
    
    async def receive(self) -> bytes:
        """Receive message from subprocess stdout."""
        if not self.is_connected():
            raise MCPConnectionError("Transport not connected")
        
        if not self.process or not self.process.stdout:
            raise MCPConnectionError("Process stdout not available")
        
        async with self._read_lock:
            try:
                # Read line from stdout
                line = await self.process.stdout.readline()
                
                if not line:
                    # EOF reached - process likely terminated
                    self._connected = False
                    raise MCPConnectionError("Process terminated unexpectedly")
                
                # Remove trailing newline
                return line.rstrip(b'\n')
                
            except Exception as e:
                logger.error(f"Failed to receive message: {str(e)}")
                raise MCPConnectionError(f"Failed to receive message: {str(e)}")
    
    def is_connected(self) -> bool:
        """Check if transport is connected."""
        if not self._connected or not self.process:
            return False
        
        # Check if process is still running
        if self.process.returncode is not None:
            self._connected = False
            return False
            
        return True


class WebSocketTransport(MCPTransport):
    """
    WebSocket transport for MCP communication.
    
    This transport is useful for MCP servers that provide WebSocket endpoints.
    Can optionally start a server process before connecting.
    """
    
    def __init__(self, url: str, headers: Dict[str, str] = None, command: list = None, args: list = None, env: Dict[str, str] = None):
        self.url = url
        self.headers = headers or {}
        self.websocket = None
        self._connected = False
        
        # Concurrency control for WebSocket operations
        self._send_lock = asyncio.Lock()
        self._receive_lock = asyncio.Lock()
        
        # Optional server process management
        self.command = command
        self.args = args or []
        self.env = env
        self.process: Optional[asyncio.subprocess.Process] = None
    
    async def connect(self) -> bool:
        """Establish WebSocket connection."""
        try:
            # Start server process if command is provided
            if self.command:
                await self._start_server_process()
                # Wait for server to start
                await asyncio.sleep(2)
            
            logger.info(f"Connecting to MCP server via WebSocket: {self.url}")
            
            # Try connecting with retries
            max_retries = 5
            for attempt in range(max_retries):
                try:
                    # Connect to WebSocket with headers if supported
                    if self.headers:
                        try:
                            # Try with additional_headers first (websockets >= 10.0)
                            self.websocket = await websockets.connect(
                                self.url,
                                additional_headers=self.headers
                            )
                        except TypeError:
                            # Fall back to extra_headers for older versions
                            try:
                                self.websocket = await websockets.connect(
                                    self.url,
                                    extra_headers=self.headers
                                )
                            except TypeError:
                                # Fall back to connection without headers
                                logger.warning("WebSocket headers not supported in this websockets version, connecting without headers")
                                self.websocket = await websockets.connect(self.url)
                    else:
                        self.websocket = await websockets.connect(self.url)
                    self._connected = True
                    logger.info("WebSocket connection established")
                    return True
                except Exception as e:
                    if attempt < max_retries - 1:
                        logger.info(f"WebSocket connection attempt {attempt + 1} failed, retrying...")
                        await asyncio.sleep(1)
                    else:
                        raise e
            
        except Exception as e:
            logger.error(f"WebSocket connection failed: {str(e)}")
            raise MCPConnectionError(f"Failed to connect via WebSocket: {str(e)}")
            
    async def _start_server_process(self) -> None:
        """Start the server process if command is provided."""
        if not self.command:
            return
            
        try:
            logger.info(f"Starting MCP WebSocket server: {' '.join(self.command + self.args)}")

            # Use shared environment preparation method
            process_env = self._prepare_environment()
            
            # Set larger limit for MCP communication to handle large responses
            # Default asyncio readline limit is 64KB, increase to 10MB for large email attachments
            limit = 10 * 1024 * 1024  # 10MB
            
            self.process = await asyncio.create_subprocess_exec(
                *self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=process_env,
                limit=limit
            )
            
            # Check if process started successfully
            if self.process.returncode is not None:
                raise MCPConnectionError(f"WebSocket server process failed to start: {self.command[0]}")
            
            logger.info(f"MCP WebSocket server started successfully (PID: {self.process.pid})")
            
        except Exception as e:
            logger.error(f"Failed to start MCP WebSocket server: {str(e)}")
            raise MCPConnectionError(f"Failed to start WebSocket server: {str(e)}")
    
    async def disconnect(self) -> None:
        """Close WebSocket connection and terminate server process if needed."""
        # Close WebSocket connection
        if self.websocket and self._connected:
            try:
                await self.websocket.close()
                logger.info("WebSocket connection closed")
            except Exception as e:
                logger.error(f"Error closing WebSocket: {str(e)}")
            finally:
                self._connected = False
                self.websocket = None
        
        # Terminate server process if we started it
        if self.process:
            try:
                logger.info("Shutting down MCP WebSocket server...")
                
                # Terminate the process
                self.process.terminate()
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    # Force kill if terminate doesn't work
                    logger.warning("Graceful shutdown timeout, killing process")
                    self.process.kill()
                    await self.process.wait()
                
                logger.info("MCP WebSocket server shutdown complete")
                
            except Exception as e:
                logger.error(f"Error during MCP WebSocket server shutdown: {str(e)}")
            finally:
                self.process = None
    
    async def send(self, message: bytes) -> None:
        """Send message via WebSocket."""
        if not self.is_connected():
            raise MCPConnectionError("WebSocket not connected")
        
        async with self._send_lock:
            try:
                await self.websocket.send(message.decode('utf-8'))
            except Exception as e:
                logger.error(f"Failed to send WebSocket message: {str(e)}")
                raise MCPConnectionError(f"Failed to send message: {str(e)}")
    
    async def receive(self) -> bytes:
        """Receive message from WebSocket."""
        if not self.is_connected():
            raise MCPConnectionError("WebSocket not connected")
        
        async with self._receive_lock:
            try:
                message = await self.websocket.recv()
                return message.encode('utf-8')
            except Exception as e:
                logger.error(f"Failed to receive WebSocket message: {str(e)}")
                raise MCPConnectionError(f"Failed to receive message: {str(e)}")
    
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        if not self._connected or not self.websocket:
            return False
        
        # Handle compatibility between different websockets versions
        if hasattr(self.websocket, 'closed'):
            return not self.websocket.closed
        elif hasattr(self.websocket, 'state'):
            # websockets 15.0+ uses state enum
            return self.websocket.state.name == 'OPEN'
        else:
            # Fallback
            return True


class MCPConnection:
    """
    High-level MCP connection manager.
    
    This class manages MCP connections with automatic reconnection,
    health monitoring, and error recovery.
    """
    
    def __init__(self, transport: MCPTransport, timeout: float = 300.0):
        self.transport = transport
        self.timeout = timeout
        self._health_check_task: Optional[asyncio.Task] = None
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 3
        
    async def connect(self) -> bool:
        """Establish connection with timeout."""
        try:
            success = await asyncio.wait_for(
                self.transport.connect(),
                timeout=self.timeout
            )
            
            if success:
                self._reconnect_attempts = 0
                # Start health monitoring
                self._health_check_task = asyncio.create_task(
                    self._health_check_loop()
                )
            
            return success
            
        except asyncio.TimeoutError:
            raise MCPTimeoutError(f"Connection timeout after {self.timeout} seconds")
    
    async def disconnect(self) -> None:
        """Disconnect and cleanup."""
        # Stop health monitoring
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None
        
        # Disconnect transport
        await self.transport.disconnect()
    
    async def send_with_timeout(self, message: bytes) -> None:
        """Send message with timeout."""
        try:
            await asyncio.wait_for(
                self.transport.send(message),
                timeout=self.timeout
            )
        except asyncio.TimeoutError:
            raise MCPTimeoutError(f"Send timeout after {self.timeout} seconds")
    
    async def receive_with_timeout(self) -> bytes:
        """Receive message with timeout."""
        try:
            return await asyncio.wait_for(
                self.transport.receive(),
                timeout=self.timeout
            )
        except asyncio.TimeoutError:
            raise MCPTimeoutError(f"Receive timeout after {self.timeout} seconds")
    
    def is_connected(self) -> bool:
        """Check if connection is healthy."""
        return self.transport.is_connected()
    
    async def _health_check_loop(self) -> None:
        """Background health monitoring."""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                
                if not self.transport.is_connected():
                    logger.warning("Connection lost, attempting reconnection")
                    await self._attempt_reconnect()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check error: {str(e)}")
    
    async def _attempt_reconnect(self) -> None:
        """Attempt to reconnect with exponential backoff."""
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error("Max reconnection attempts reached")
            return
        
        self._reconnect_attempts += 1
        backoff_delay = 2 ** self._reconnect_attempts
        
        logger.info(f"Reconnection attempt {self._reconnect_attempts} in {backoff_delay}s")
        await asyncio.sleep(backoff_delay)
        
        try:
            await self.transport.disconnect()
            success = await self.transport.connect()
            
            if success:
                logger.info("Reconnection successful")
                self._reconnect_attempts = 0
            else:
                logger.warning("Reconnection failed")
                
        except Exception as e:
            logger.error(f"Reconnection error: {str(e)}")


class EmbeddedTransport(MCPTransport):
    """
    Universal embedded MCP server transport that runs in the same process.

    This transport supports all stdio-based MCP tools by dynamically detecting
    their protocol type and adapting accordingly. Perfect for PyInstaller
    environments where subprocess creation fails.

    Supports two common stdio MCP patterns:
    1. Custom stdio protocol with _process_mcp_message() method
    2. Standard MCP library with Server() class and stdio_server()
    """

    def __init__(self, module_path: str, main_function: str = "main", args: list = None, env: Dict[str, str] = None):
        """
        Initialize universal embedded transport.

        Args:
            module_path: Path to the MCP server module (e.g., "tools.mcp_smtp_send_email")
            main_function: Name of the main function to call (default: "main")
            args: Command line arguments that would be passed to the server
            env: Environment variables
        """
        self.module_path = module_path
        self.main_function = main_function
        self.args = args or []
        self.env = env or {}
        self.module = None
        self.server_instance = None
        self._connected = False
        self._server_type = None  # Will be detected: 'custom' or 'standard'

        # Message queues for custom protocol servers
        self._message_queue = asyncio.Queue()
        self._response_queue = asyncio.Queue()

        # PyInstaller compatibility
        if hasattr(sys, '_MEIPASS'):
            logger.info(f"PyInstaller environment detected - using embedded mode for {module_path}")

    async def connect(self) -> bool:
        """Initialize the embedded MCP server by calling its main function."""
        try:
            logger.info(f"Starting embedded MCP server: {self.module_path}")

            # Load the module
            self.module = self._load_module()

            # Detect server type and initialize accordingly
            await self._detect_and_initialize_server()

            self._connected = True
            logger.info(f"Embedded MCP server started successfully: {self.module_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to start embedded MCP server: {str(e)}")
            raise MCPConnectionError(f"Failed to connect via embedded mode: {str(e)}")

    async def disconnect(self) -> None:
        """Cleanup embedded server."""
        if self._connected:
            try:
                logger.info("Shutting down embedded MCP server...")

                # Call cleanup methods if available
                if self.server_instance:
                    if hasattr(self.server_instance, 'cleanup'):
                        await self.server_instance.cleanup()
                    elif hasattr(self.server_instance, 'close'):
                        await self.server_instance.close()

                self.server_instance = None
                self.module = None
                self._connected = False
                logger.info("Embedded MCP server shutdown complete")
            except Exception as e:
                logger.error(f"Error during embedded server shutdown: {str(e)}")

    async def send(self, message: bytes) -> None:
        """Send message to embedded server (not used in direct mode)."""
        raise NotImplementedError("Use send_message() for embedded transport")

    async def receive(self) -> bytes:
        """Receive message from embedded server (not used in direct mode)."""
        raise NotImplementedError("Use send_message() for embedded transport")

    def is_connected(self) -> bool:
        """Check if embedded server is ready."""
        return self._connected and (self.server_instance is not None or self.module is not None)

    async def send_message(self, message) -> Optional[Any]:
        """
        Send MCP message directly to embedded server using detected protocol.

        Args:
            message: MCPMessage instance

        Returns:
            Response from embedded server
        """
        if not self.is_connected():
            raise MCPConnectionError("Embedded server not connected")

        try:
            if self._server_type == 'custom':
                # Custom protocol: call _process_mcp_message directly
                return await self.server_instance._process_mcp_message(message)
            elif self._server_type == 'standard':
                # Standard MCP library: use message queues (would need more complex implementation)
                raise NotImplementedError("Standard MCP library support not yet implemented")
            else:
                raise MCPConnectionError("Unknown server type")
        except Exception as e:
            logger.error(f"Error processing message in embedded server: {str(e)}")
            raise MCPConnectionError(f"Embedded server error: {str(e)}")

    def _load_module(self):
        """Load MCP server module dynamically."""
        try:
            import importlib

            # Add current working directory to Python path if not already present
            current_dir = os.getcwd()
            if current_dir not in sys.path:
                sys.path.insert(0, current_dir)
                logger.debug(f"Added current directory to sys.path: {current_dir}")

            # Set up environment variables before importing
            old_env = {}
            for key, value in self.env.items():
                old_env[key] = os.environ.get(key)
                os.environ[key] = value

            try:
                # Handle tools modules specially for PyInstaller
                if self.module_path.startswith('tools.'):
                    if hasattr(sys, '_MEIPASS'):
                        # PyInstaller environment - try direct import first
                        try:
                            module = importlib.import_module(self.module_path)
                        except ImportError:
                            # Fallback: load from file path
                            module_name = self.module_path.split('.')[-1]
                            file_path = os.path.join('tools', f'{module_name}.py')
                            if os.path.exists(file_path):
                                spec = importlib.util.spec_from_file_location(module_name, file_path)
                                module = importlib.util.module_from_spec(spec)
                                sys.modules[self.module_path] = module
                                spec.loader.exec_module(module)
                            else:
                                raise ImportError(f"Cannot find module {self.module_path}")
                    else:
                        # Normal environment
                        module = importlib.import_module(self.module_path)
                else:
                    # Standard import
                    module = importlib.import_module(self.module_path)

                logger.info(f"Successfully loaded module: {self.module_path}")
                return module

            finally:
                # Restore environment
                for key, old_value in old_env.items():
                    if old_value is None:
                        os.environ.pop(key, None)
                    else:
                        os.environ[key] = old_value

        except Exception as e:
            logger.error(f"Failed to load module {self.module_path}: {str(e)}")
            raise

    async def _detect_and_initialize_server(self):
        """Detect server type and initialize appropriately."""

        # Check if it's a custom protocol server (has classes with _process_mcp_message)
        custom_server_class = self._find_custom_server_class()
        if custom_server_class:
            logger.info(f"Detected custom protocol server: {custom_server_class.__name__}")
            self._server_type = 'custom'
            self.server_instance = await self._initialize_custom_server(custom_server_class)
            return

        # Check if it's a standard MCP library server
        if hasattr(self.module, self.main_function):
            logger.info("Detected standard MCP library server")
            self._server_type = 'standard'
            # For standard servers, we would need to override their stdio handling
            # This is more complex and would require intercepting their stdio_server calls
            raise NotImplementedError("Standard MCP library embedded support coming soon")

        raise MCPConnectionError(f"Could not detect server type in module {self.module_path}")

    def _find_custom_server_class(self):
        """Find MCP server class with _process_mcp_message method."""
        for name in dir(self.module):
            obj = getattr(self.module, name)
            if (isinstance(obj, type) and
                hasattr(obj, '_process_mcp_message') and
                name.endswith('MCPServer')):
                return obj
        return None

    @contextlib.contextmanager
    def _with_environment(self):
        """
        Context manager to temporarily set environment variables.

        Uses the same environment preparation logic as StdioTransport
        to ensure consistency across all transport types.
        """
        process_env = self._prepare_environment()
        original_env = {}

        try:
            # Set environment variables that differ from current environment
            for key, value in process_env.items():
                current_value = os.environ.get(key)
                if current_value != str(value):
                    original_env[key] = current_value
                    os.environ[key] = str(value)

            if original_env:
                logger.debug(f"Temporarily set {len(original_env)} environment variables for embedded server")

            yield

        finally:
            # Restore original environment
            for key, original_value in original_env.items():
                if original_value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = original_value

    async def _initialize_custom_server(self, server_class):
        """Initialize custom protocol server with configuration inference."""
        # Use environment context manager like StdioTransport
        with self._with_environment():
            # Try to create instance with various configuration strategies

            # Strategy 1: No arguments (simplest)
            try:
                return server_class()
            except TypeError as e:
                pass

            # Strategy 2: Pass environment as config dict
            try:
                return server_class(config=self.env)
            except TypeError:
                pass

            # Strategy 3: Let server handle its own configuration loading
            # This allows servers to implement their own config loading logic

            # Strategy 4: Pass command line args if available
            if self.args:
                try:
                    # Mock sys.argv for argparse-based servers
                    old_argv = sys.argv
                    sys.argv = [self.module_path] + self.args
                    try:
                        return server_class()
                    finally:
                        sys.argv = old_argv
                except Exception:
                    pass

            # Fallback: try with empty dict
            return server_class({})


# Transport factory
def create_transport(transport_type: str, config: Dict[str, Any]) -> MCPTransport:
    """
    Create transport instance based on configuration.

    Args:
        transport_type: Type of transport ('stdio', 'websocket', 'embedded')
        config: Transport configuration

    Returns:
        MCPTransport instance

    Raises:
        ValueError: If transport type is not supported
    """
    # Log transport creation request with key configuration info
    command_info = f"command={config.get('command', 'N/A')}" if 'command' in config else ""
    url_info = f"url={config.get('url', 'N/A')}" if 'url' in config else ""
    module_info = f"module={config.get('module_path', 'N/A')}" if 'module_path' in config else ""
    config_summary = " ".join(filter(None, [command_info, url_info, module_info]))

    logger.debug(f"Creating transport: type={transport_type}, {config_summary}")

    if transport_type == "stdio":
        # Detailed environment detection logging
        is_pyinstaller = hasattr(sys, '_MEIPASS')
        command = config.get("command", [])
        uses_python_cmd = command and len(command) > 0 and command[0] in ["python", "python3"]

        logger.debug(f"Environment detection: PyInstaller={is_pyinstaller}, "
                    f"command={command}, uses_python={uses_python_cmd}")

        # Auto-detect PyInstaller environment and switch to embedded mode
        if is_pyinstaller and uses_python_cmd:
            logger.info(f"PyInstaller detected: auto-switching stdio to embedded mode "
                       f"(command: {' '.join(command)})")
            return create_embedded_transport_from_stdio_config(config)
        else:
            # Log why we're using standard stdio transport
            if not is_pyinstaller:
                logger.debug("Using standard stdio transport (not in PyInstaller environment)")
            elif not uses_python_cmd:
                logger.debug(f"Using standard stdio transport (command '{command[0] if command else 'empty'}' "
                           f"is not python)")
            else:
                logger.debug("Using standard stdio transport (conditions not met for embedded mode)")

            logger.info(f"Creating stdio transport: {' '.join(command) if command else 'no command'}")
            return StdioTransport(
                command=config["command"],
                args=config.get("args", []),
                env=config.get("environment")
            )
    elif transport_type == "websocket":
        websocket_url = config.get("url", "unknown")
        logger.info(f"Creating WebSocket transport: {websocket_url}")
        return WebSocketTransport(
            url=config["url"],
            headers=config.get("headers", {}),
            command=config.get("command"),
            args=config.get("args", []),
            env=config.get("environment")
        )
    elif transport_type == "embedded":
        module_path = config.get("module_path", "unknown")
        logger.info(f"Creating embedded transport: {module_path}")
        return EmbeddedTransport(
            module_path=config["module_path"],
            main_function=config.get("main_function", "main"),
            args=config.get("args", []),
            env=config.get("environment", {})
        )
    else:
        logger.error(f"Unsupported transport type: {transport_type}")
        raise ValueError(f"Unsupported transport type: {transport_type}")


def create_embedded_transport_from_stdio_config(stdio_config: Dict[str, Any]) -> EmbeddedTransport:
    """
    Convert stdio configuration to embedded transport configuration.

    This helper function automatically converts stdio MCP tool configurations
    to embedded mode, making PyInstaller compatibility seamless.

    Args:
        stdio_config: Original stdio transport configuration

    Returns:
        EmbeddedTransport instance
    """
    command = stdio_config.get("command", [])
    logger.debug(f"Converting stdio config to embedded mode: original_command={command}")

    if not command or len(command) < 2:
        error_msg = f"Invalid stdio command for embedded conversion: {command}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # Extract module path from command
    # Expect format: ["python", "tools/mcp_xxx.py", ...]
    script_path = command[1]  # e.g., "tools/mcp_smtp_send_email.py"
    logger.debug(f"Extracting script path: {script_path}")

    # Convert file path to module path
    if script_path.endswith('.py'):
        module_path = script_path[:-3].replace('/', '.')  # "tools.mcp_smtp_send_email"
    else:
        module_path = script_path.replace('/', '.')

    # Extract additional arguments (everything after the script path)
    command_args = command[2:] if len(command) > 2 else []
    config_args = stdio_config.get("args", [])
    args = command_args + config_args

    # Log conversion details
    env_count = len(stdio_config.get("environment", {}))
    logger.info(f"Converting stdio config to embedded: {script_path} -> {module_path}")
    logger.debug(f"Conversion details: args={args}, env_vars={env_count}")

    # Create the embedded transport
    transport = EmbeddedTransport(
        module_path=module_path,
        main_function="main",
        args=args,
        env=stdio_config.get("environment", {})
    )

    logger.info(f"Successfully created embedded transport for {module_path}")
    return transport