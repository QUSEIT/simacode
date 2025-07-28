"""
Tests for MCP connection management.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock

from simacode.mcp.connection import (
    StdioTransport, WebSocketTransport, MCPConnection, create_transport
)
from simacode.mcp.exceptions import MCPConnectionError, MCPTimeoutError


class TestStdioTransport:
    """Test StdioTransport class."""
    
    @pytest.fixture
    def transport(self):
        """Create StdioTransport instance."""
        return StdioTransport(
            command=["python", "-c", "print('test')"],
            args=["--version"],
            env={"TEST_VAR": "value"}
        )
    
    def test_init(self, transport):
        """Test transport initialization."""
        assert transport.command == ["python", "-c", "print('test')"]
        assert transport.args == ["--version"]
        assert transport.env == {"TEST_VAR": "value"}
        assert transport.process is None
        assert not transport._connected
    
    async def test_connect_success(self, transport):
        """Test successful connection."""
        # Mock subprocess creation
        mock_process = AsyncMock()
        mock_process.returncode = None  # Process is running
        mock_process.pid = 12345
        
        with patch('asyncio.create_subprocess_exec') as mock_create:
            mock_create.return_value = mock_process
            
            result = await transport.connect()
            
            assert result is True
            assert transport._connected is True
            assert transport.process == mock_process
            
            # Verify subprocess was created with correct parameters
            mock_create.assert_called_once_with(
                "python", "-c", "print('test')", "--version",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={"TEST_VAR": "value"}
            )
    
    async def test_connect_process_failed(self, transport):
        """Test connection when process fails to start."""
        mock_process = AsyncMock()
        mock_process.returncode = 1  # Process exited
        
        with patch('asyncio.create_subprocess_exec') as mock_create:
            mock_create.return_value = mock_process
            
            with pytest.raises(MCPConnectionError) as exc_info:
                await transport.connect()
            
            assert "Process failed to start" in str(exc_info.value)
    
    async def test_connect_exception(self, transport):
        """Test connection with subprocess creation exception."""
        with patch('asyncio.create_subprocess_exec') as mock_create:
            mock_create.side_effect = OSError("Command not found")
            
            with pytest.raises(MCPConnectionError) as exc_info:
                await transport.connect()
            
            assert "Failed to connect via stdio" in str(exc_info.value)
    
    async def test_disconnect_graceful(self, transport):
        """Test graceful disconnection."""
        # Setup connected transport
        mock_process = AsyncMock()
        mock_process.returncode = None
        mock_process.stdin = AsyncMock()
        mock_process.wait = AsyncMock(return_value=0)
        
        transport.process = mock_process
        transport._connected = True
        
        await transport.disconnect()
        
        # Verify graceful shutdown sequence
        mock_process.stdin.close.assert_called_once()
        mock_process.stdin.wait_closed.assert_called_once()
        mock_process.wait.assert_called_once()
        
        assert not transport._connected
        assert transport.process is None
    
    async def test_disconnect_force_terminate(self, transport):
        """Test forced termination on disconnect."""
        mock_process = AsyncMock()
        mock_process.stdin = AsyncMock()
        mock_process.wait = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_process.terminate = AsyncMock()
        
        transport.process = mock_process
        transport._connected = True
        
        with patch('asyncio.wait_for', side_effect=[asyncio.TimeoutError(), 0]):
            await transport.disconnect()
        
        # Should call terminate after timeout
        mock_process.terminate.assert_called_once()
    
    async def test_disconnect_force_kill(self, transport):
        """Test forced kill on disconnect."""
        mock_process = AsyncMock()
        mock_process.stdin = AsyncMock()
        mock_process.wait = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_process.terminate = AsyncMock()
        mock_process.kill = AsyncMock()
        
        transport.process = mock_process
        transport._connected = True
        
        # Mock both timeouts (graceful and terminate)
        with patch('asyncio.wait_for', side_effect=[asyncio.TimeoutError(), asyncio.TimeoutError(), 0]):
            await transport.disconnect()
        
        # Should call both terminate and kill
        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()
    
    async def test_send_success(self, transport):
        """Test successful message sending."""
        mock_process = AsyncMock()
        mock_stdin = AsyncMock()
        mock_process.stdin = mock_stdin
        
        transport.process = mock_process
        transport._connected = True
        
        message = b'{"jsonrpc": "2.0", "method": "test"}'
        await transport.send(message)
        
        # Verify message was written with newline
        mock_stdin.write.assert_called_once_with(message + b'\n')
        mock_stdin.drain.assert_called_once()
    
    async def test_send_not_connected(self, transport):
        """Test sending when not connected."""
        message = b'{"jsonrpc": "2.0", "method": "test"}'
        
        with pytest.raises(MCPConnectionError) as exc_info:
            await transport.send(message)
        
        assert "Transport not connected" in str(exc_info.value)
    
    async def test_send_no_stdin(self, transport):
        """Test sending when stdin not available."""
        mock_process = AsyncMock()
        mock_process.stdin = None
        
        transport.process = mock_process
        transport._connected = True
        
        message = b'{"jsonrpc": "2.0", "method": "test"}'
        
        with pytest.raises(MCPConnectionError) as exc_info:
            await transport.send(message)
        
        assert "Process stdin not available" in str(exc_info.value)
    
    async def test_receive_success(self, transport):
        """Test successful message receiving."""
        mock_process = AsyncMock()
        mock_stdout = AsyncMock()
        mock_stdout.readline = AsyncMock(return_value=b'{"result": "ok"}\n')
        mock_process.stdout = mock_stdout
        
        transport.process = mock_process
        transport._connected = True
        
        message = await transport.receive()
        
        assert message == b'{"result": "ok"}'
        mock_stdout.readline.assert_called_once()
    
    async def test_receive_eof(self, transport):
        """Test receiving when EOF reached."""
        mock_process = AsyncMock()
        mock_stdout = AsyncMock()
        mock_stdout.readline = AsyncMock(return_value=b'')  # EOF
        mock_process.stdout = mock_stdout
        
        transport.process = mock_process
        transport._connected = True
        
        with pytest.raises(MCPConnectionError) as exc_info:
            await transport.receive()
        
        assert "Process terminated unexpectedly" in str(exc_info.value)
        assert not transport._connected
    
    def test_is_connected_true(self, transport):
        """Test is_connected when connected."""
        mock_process = AsyncMock()
        mock_process.returncode = None
        
        transport.process = mock_process
        transport._connected = True
        
        assert transport.is_connected()
    
    def test_is_connected_false(self, transport):
        """Test is_connected when not connected."""
        assert not transport.is_connected()
        
        # Test with terminated process
        mock_process = AsyncMock()
        mock_process.returncode = 0  # Process terminated
        
        transport.process = mock_process
        transport._connected = True
        
        assert not transport.is_connected()
        assert not transport._connected  # Should update state


class TestWebSocketTransport:
    """Test WebSocketTransport class."""
    
    @pytest.fixture
    def transport(self):
        """Create WebSocketTransport instance."""
        return WebSocketTransport(
            url="ws://localhost:8080/mcp",
            headers={"Authorization": "Bearer token"}
        )
    
    def test_init(self, transport):
        """Test transport initialization."""
        assert transport.url == "ws://localhost:8080/mcp"
        assert transport.headers == {"Authorization": "Bearer token"}
        assert transport.websocket is None
        assert not transport._connected
    
    async def test_connect_success(self, transport):
        """Test successful WebSocket connection."""
        mock_websocket = AsyncMock()
        
        with patch('websockets.connect', return_value=mock_websocket) as mock_connect:
            result = await transport.connect()
            
            assert result is True
            assert transport._connected is True
            assert transport.websocket == mock_websocket
            
            mock_connect.assert_called_once_with(
                "ws://localhost:8080/mcp",
                extra_headers={"Authorization": "Bearer token"}
            )
    
    async def test_connect_websockets_not_installed(self, transport):
        """Test connection when websockets package not installed."""
        with patch('websockets.connect', side_effect=ImportError()):
            with pytest.raises(MCPConnectionError) as exc_info:
                await transport.connect()
            
            assert "websockets package not installed" in str(exc_info.value)
    
    async def test_connect_connection_error(self, transport):
        """Test connection error."""
        with patch('websockets.connect', side_effect=ConnectionError("Connection failed")):
            with pytest.raises(MCPConnectionError) as exc_info:
                await transport.connect()
            
            assert "Failed to connect via WebSocket" in str(exc_info.value)
    
    async def test_disconnect(self, transport):
        """Test WebSocket disconnection."""
        mock_websocket = AsyncMock()
        transport.websocket = mock_websocket
        transport._connected = True
        
        await transport.disconnect()
        
        mock_websocket.close.assert_called_once()
        assert not transport._connected
        assert transport.websocket is None
    
    async def test_send_success(self, transport):
        """Test successful message sending."""
        mock_websocket = AsyncMock()
        transport.websocket = mock_websocket
        transport._connected = True
        
        message = b'{"jsonrpc": "2.0", "method": "test"}'
        await transport.send(message)
        
        mock_websocket.send.assert_called_once_with('{"jsonrpc": "2.0", "method": "test"}')
    
    async def test_send_not_connected(self, transport):
        """Test sending when not connected."""
        message = b'{"jsonrpc": "2.0", "method": "test"}'
        
        with pytest.raises(MCPConnectionError) as exc_info:
            await transport.send(message)
        
        assert "WebSocket not connected" in str(exc_info.value)
    
    async def test_receive_success(self, transport):
        """Test successful message receiving."""
        mock_websocket = AsyncMock()
        mock_websocket.recv = AsyncMock(return_value='{"result": "ok"}')
        transport.websocket = mock_websocket
        transport._connected = True
        
        message = await transport.receive()
        
        assert message == b'{"result": "ok"}'
        mock_websocket.recv.assert_called_once()
    
    def test_is_connected_true(self, transport):
        """Test is_connected when connected."""
        mock_websocket = MagicMock()
        mock_websocket.closed = False
        
        transport.websocket = mock_websocket
        transport._connected = True
        
        assert transport.is_connected()
    
    def test_is_connected_false(self, transport):
        """Test is_connected when not connected."""
        assert not transport.is_connected()
        
        # Test with closed websocket
        mock_websocket = MagicMock()
        mock_websocket.closed = True
        
        transport.websocket = mock_websocket
        transport._connected = True
        
        assert not transport.is_connected()


class TestMCPConnection:
    """Test MCPConnection class."""
    
    @pytest.fixture
    def mock_transport(self):
        """Create mock transport."""
        transport = AsyncMock()
        transport.is_connected.return_value = True
        return transport
    
    @pytest.fixture
    def connection(self, mock_transport):
        """Create MCPConnection instance."""
        return MCPConnection(mock_transport, timeout=5.0)
    
    async def test_connect_success(self, connection, mock_transport):
        """Test successful connection."""
        mock_transport.connect.return_value = True
        
        result = await connection.connect()
        
        assert result is True
        mock_transport.connect.assert_called_once()
        assert connection._health_check_task is not None
    
    async def test_connect_timeout(self, connection, mock_transport):
        """Test connection timeout."""
        # Mock slow connect
        async def slow_connect():
            await asyncio.sleep(10)  # Longer than timeout
            return True
        
        mock_transport.connect = slow_connect
        
        with pytest.raises(MCPTimeoutError) as exc_info:
            await connection.connect()
        
        assert "Connection timeout after 5.0 seconds" in str(exc_info.value)
    
    async def test_disconnect(self, connection, mock_transport):
        """Test disconnection."""
        # Setup connected state
        connection._health_check_task = AsyncMock()
        
        await connection.disconnect()
        
        # Health check task should be cancelled
        connection._health_check_task.cancel.assert_called_once()
        mock_transport.disconnect.assert_called_once()
    
    async def test_send_with_timeout_success(self, connection, mock_transport):
        """Test successful send with timeout."""
        message = b'{"jsonrpc": "2.0", "method": "test"}'
        
        await connection.send_with_timeout(message)
        
        mock_transport.send.assert_called_once_with(message)
    
    async def test_send_with_timeout_timeout(self, connection, mock_transport):
        """Test send timeout."""
        # Mock slow send
        async def slow_send(msg):
            await asyncio.sleep(10)  # Longer than timeout
        
        mock_transport.send = slow_send
        message = b'{"jsonrpc": "2.0", "method": "test"}'
        
        with pytest.raises(MCPTimeoutError) as exc_info:
            await connection.send_with_timeout(message)
        
        assert "Send timeout after 5.0 seconds" in str(exc_info.value)
    
    async def test_receive_with_timeout_success(self, connection, mock_transport):
        """Test successful receive with timeout."""
        expected_message = b'{"result": "ok"}'
        mock_transport.receive.return_value = expected_message
        
        message = await connection.receive_with_timeout()
        
        assert message == expected_message
        mock_transport.receive.assert_called_once()
    
    async def test_receive_with_timeout_timeout(self, connection, mock_transport):
        """Test receive timeout."""
        # Mock slow receive
        async def slow_receive():
            await asyncio.sleep(10)  # Longer than timeout
            return b'{"result": "ok"}'
        
        mock_transport.receive = slow_receive
        
        with pytest.raises(MCPTimeoutError) as exc_info:
            await connection.receive_with_timeout()
        
        assert "Receive timeout after 5.0 seconds" in str(exc_info.value)


class TestTransportFactory:
    """Test transport factory function."""
    
    def test_create_stdio_transport(self):
        """Test creating stdio transport."""
        config = {
            "command": ["python", "-m", "test_server"],
            "args": ["--port", "8080"],
            "environment": {"TEST_VAR": "value"}
        }
        
        transport = create_transport("stdio", config)
        
        assert isinstance(transport, StdioTransport)
        assert transport.command == ["python", "-m", "test_server"]
        assert transport.args == ["--port", "8080"]
        assert transport.env == {"TEST_VAR": "value"}
    
    def test_create_websocket_transport(self):
        """Test creating websocket transport."""
        config = {
            "url": "ws://localhost:8080/mcp",
            "headers": {"Authorization": "Bearer token"}
        }
        
        transport = create_transport("websocket", config)
        
        assert isinstance(transport, WebSocketTransport)
        assert transport.url == "ws://localhost:8080/mcp"
        assert transport.headers == {"Authorization": "Bearer token"}
    
    def test_create_unsupported_transport(self):
        """Test creating unsupported transport type."""
        config = {"url": "http://localhost:8080"}
        
        with pytest.raises(ValueError) as exc_info:
            create_transport("http", config)
        
        assert "Unsupported transport type: http" in str(exc_info.value)