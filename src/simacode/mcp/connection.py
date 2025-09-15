"""
MCP connection management and transport implementations.

This module provides different transport mechanisms for MCP communication,
including stdio, WebSocket, and HTTP transports.
"""

import asyncio
import logging
import os
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
            # Merge custom env with current environment to ensure Python can run properly
            process_env = dict(os.environ) if self.env else None
            if self.env:
                process_env.update(self.env)
            
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
            
            # Merge custom env with current environment
            process_env = dict(os.environ) if self.env else None
            if self.env:
                process_env.update(self.env)
            
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


# Transport factory
def create_transport(transport_type: str, config: Dict[str, Any]) -> MCPTransport:
    """
    Create transport instance based on configuration.
    
    Args:
        transport_type: Type of transport ('stdio', 'websocket')
        config: Transport configuration
        
    Returns:
        MCPTransport instance
        
    Raises:
        ValueError: If transport type is not supported
    """
    if transport_type == "stdio":
        return StdioTransport(
            command=config["command"],
            args=config.get("args", []),
            env=config.get("environment")
        )
    elif transport_type == "websocket":
        return WebSocketTransport(
            url=config["url"],
            headers=config.get("headers", {}),
            command=config.get("command"),
            args=config.get("args", []),
            env=config.get("environment")
        )
    else:
        raise ValueError(f"Unsupported transport type: {transport_type}")