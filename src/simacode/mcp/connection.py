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
        
    async def connect(self) -> bool:
        """Start subprocess and establish stdio connection."""
        try:
            logger.info(f"Starting MCP server: {' '.join(self.command + self.args)}")
            
            # Start subprocess
            # Merge custom env with current environment to ensure Python can run properly
            process_env = dict(os.environ) if self.env else None
            if self.env:
                process_env.update(self.env)
            
            self.process = await asyncio.create_subprocess_exec(
                *self.command,
                *self.args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=process_env
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
    """
    
    def __init__(self, url: str, headers: Dict[str, str] = None):
        self.url = url
        self.headers = headers or {}
        self.websocket = None
        self._connected = False
    
    async def connect(self) -> bool:
        """Establish WebSocket connection."""
        try:
            import websockets
            
            logger.info(f"Connecting to MCP server via WebSocket: {self.url}")
            
            self.websocket = await websockets.connect(
                self.url,
                extra_headers=self.headers
            )
            
            self._connected = True
            logger.info("WebSocket connection established")
            return True
            
        except ImportError:
            raise MCPConnectionError("websockets package not installed")
        except Exception as e:
            logger.error(f"WebSocket connection failed: {str(e)}")
            raise MCPConnectionError(f"Failed to connect via WebSocket: {str(e)}")
    
    async def disconnect(self) -> None:
        """Close WebSocket connection."""
        if self.websocket and self._connected:
            try:
                await self.websocket.close()
                logger.info("WebSocket connection closed")
            except Exception as e:
                logger.error(f"Error closing WebSocket: {str(e)}")
            finally:
                self._connected = False
                self.websocket = None
    
    async def send(self, message: bytes) -> None:
        """Send message via WebSocket."""
        if not self.is_connected():
            raise MCPConnectionError("WebSocket not connected")
        
        try:
            await self.websocket.send(message.decode('utf-8'))
        except Exception as e:
            logger.error(f"Failed to send WebSocket message: {str(e)}")
            raise MCPConnectionError(f"Failed to send message: {str(e)}")
    
    async def receive(self) -> bytes:
        """Receive message from WebSocket."""
        if not self.is_connected():
            raise MCPConnectionError("WebSocket not connected")
        
        try:
            message = await self.websocket.recv()
            return message.encode('utf-8')
        except Exception as e:
            logger.error(f"Failed to receive WebSocket message: {str(e)}")
            raise MCPConnectionError(f"Failed to receive message: {str(e)}")
    
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._connected and self.websocket and not self.websocket.closed


class MCPConnection:
    """
    High-level MCP connection manager.
    
    This class manages MCP connections with automatic reconnection,
    health monitoring, and error recovery.
    """
    
    def __init__(self, transport: MCPTransport, timeout: float = 30.0):
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
            headers=config.get("headers", {})
        )
    else:
        raise ValueError(f"Unsupported transport type: {transport_type}")