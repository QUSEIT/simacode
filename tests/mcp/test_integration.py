"""
Integration tests for MCP protocol implementation.

These tests use a mock MCP server to test the full protocol flow.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from simacode.mcp.protocol import MCPMessage, MCPProtocol, MCPMethods
from simacode.mcp.connection import StdioTransport, MCPConnection
from simacode.mcp.exceptions import MCPConnectionError, MCPProtocolError


class MockMCPServer:
    """
    Mock MCP server for testing.
    
    This simulates a real MCP server by handling standard MCP methods
    and providing predictable responses for testing.
    """
    
    def __init__(self):
        self.tools = [
            {
                "name": "echo",
                "description": "Echo input back",
                "input_schema": {
                    "type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"]
                }
            },
            {
                "name": "add",
                "description": "Add two numbers",
                "input_schema": {
                    "type": "object", 
                    "properties": {
                        "a": {"type": "number"},
                        "b": {"type": "number"}
                    },
                    "required": ["a", "b"]
                }
            }
        ]
        
        self.resources = [
            {
                "uri": "file:///test.txt",
                "name": "test.txt",
                "description": "Test file",
                "mime_type": "text/plain"
            }
        ]
        
        self.initialized = False
    
    async def handle_message(self, message: MCPMessage) -> MCPMessage:
        """Handle incoming MCP message and return response."""
        if message.is_request():
            return await self._handle_request(message)
        elif message.is_notification():
            await self._handle_notification(message)
            return None  # Notifications don't get responses
        else:
            raise MCPProtocolError("Invalid message type")
    
    async def _handle_request(self, message: MCPMessage) -> MCPMessage:
        """Handle request message."""
        method = message.method
        params = message.params or {}
        
        try:
            if method == MCPMethods.INITIALIZE:
                result = await self._handle_initialize(params)
            elif method == MCPMethods.PING:
                result = await self._handle_ping(params)
            elif method == MCPMethods.TOOLS_LIST:
                result = await self._handle_tools_list(params)
            elif method == MCPMethods.TOOLS_CALL:
                result = await self._handle_tools_call(params)
            elif method == MCPMethods.RESOURCES_LIST:
                result = await self._handle_resources_list(params)
            elif method == MCPMethods.RESOURCES_READ:
                result = await self._handle_resources_read(params)
            else:
                # Method not found
                error = {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
                return MCPMessage(id=message.id, error=error)
            
            return MCPMessage(id=message.id, result=result)
            
        except Exception as e:
            error = {
                "code": -32603,
                "message": f"Internal error: {str(e)}"
            }
            return MCPMessage(id=message.id, error=error)
    
    async def _handle_notification(self, message: MCPMessage) -> None:
        """Handle notification message."""
        if message.method == MCPMethods.NOTIFICATIONS_INITIALIZED:
            self.initialized = True
    
    async def _handle_initialize(self, params: dict) -> dict:
        """Handle initialize request."""
        return {
            "protocol_version": "2024-11-05",
            "capabilities": {
                "tools": {"list_changed": True},
                "resources": {"subscribe": True, "list_changed": True}
            },
            "server_info": {
                "name": "mock-mcp-server",
                "version": "1.0.0"
            }
        }
    
    async def _handle_ping(self, params: dict) -> dict:
        """Handle ping request."""
        return {"pong": True}
    
    async def _handle_tools_list(self, params: dict) -> dict:
        """Handle tools/list request."""
        return {"tools": self.tools}
    
    async def _handle_tools_call(self, params: dict) -> dict:
        """Handle tools/call request."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if tool_name == "echo":
            message = arguments.get("message", "")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Echo: {message}"
                    }
                ]
            }
        elif tool_name == "add":
            a = arguments.get("a", 0)
            b = arguments.get("b", 0)
            result = a + b
            return {
                "content": [
                    {
                        "type": "text", 
                        "text": f"Result: {result}"
                    }
                ]
            }
        else:
            raise Exception(f"Unknown tool: {tool_name}")
    
    async def _handle_resources_list(self, params: dict) -> dict:
        """Handle resources/list request."""
        return {"resources": self.resources}
    
    async def _handle_resources_read(self, params: dict) -> dict:
        """Handle resources/read request."""
        uri = params.get("uri")
        
        if uri == "file:///test.txt":
            return {
                "contents": [
                    {
                        "uri": uri,
                        "mime_type": "text/plain",
                        "text": "Hello, World!"
                    }
                ]
            }
        else:
            raise Exception(f"Resource not found: {uri}")


class MockTransport:
    """Mock transport that communicates with MockMCPServer."""
    
    def __init__(self, server: MockMCPServer):
        self.server = server
        self._connected = False
        self.message_queue = asyncio.Queue()
    
    async def connect(self) -> bool:
        """Connect to mock server."""
        self._connected = True
        return True
    
    async def disconnect(self) -> None:
        """Disconnect from mock server."""
        self._connected = False
    
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected
    
    async def send(self, message: bytes) -> None:
        """Send message to server and queue response."""
        if not self._connected:
            raise MCPConnectionError("Not connected")
        
        # Parse message
        json_str = message.decode('utf-8')
        data = json.loads(json_str)
        msg = MCPMessage.from_dict(data)
        
        # Get response from server
        response = await self.server.handle_message(msg)
        
        # Queue response if there is one
        if response:
            await self.message_queue.put(response.to_json().encode('utf-8'))
    
    async def receive(self) -> bytes:
        """Receive message from queue."""
        if not self._connected:
            raise MCPConnectionError("Not connected")
        
        # Wait for message in queue
        message = await self.message_queue.get()
        return message


class TestMCPIntegration:
    """Integration tests using mock server."""
    
    @pytest.fixture
    def mock_server(self):
        """Create mock MCP server."""
        return MockMCPServer()
    
    @pytest.fixture
    def mock_transport(self, mock_server):
        """Create mock transport."""
        return MockTransport(mock_server)
    
    @pytest.fixture
    async def protocol(self, mock_transport):
        """Create connected MCP protocol."""
        await mock_transport.connect()
        return MCPProtocol(mock_transport)
    
    async def test_initialize_flow(self, protocol):
        """Test complete initialization flow."""
        # Send initialize request
        result = await protocol.call_method(MCPMethods.INITIALIZE, {
            "protocol_version": "2024-11-05",
            "capabilities": {"tools": {}},
            "client_info": {"name": "test-client", "version": "1.0.0"}
        })
        
        # Verify response
        assert "protocol_version" in result
        assert "capabilities" in result
        assert "server_info" in result
        assert result["server_info"]["name"] == "mock-mcp-server"
        
        # Send initialized notification
        await protocol.send_notification(MCPMethods.NOTIFICATIONS_INITIALIZED)
    
    async def test_ping_pong(self, protocol):
        """Test ping/pong communication."""
        result = await protocol.call_method(MCPMethods.PING)
        
        assert result == {"pong": True}
    
    async def test_list_tools(self, protocol):
        """Test listing available tools."""
        result = await protocol.call_method(MCPMethods.TOOLS_LIST)
        
        assert "tools" in result
        tools = result["tools"]
        assert len(tools) == 2
        
        # Check echo tool
        echo_tool = next(t for t in tools if t["name"] == "echo")
        assert echo_tool["description"] == "Echo input back"
        assert "input_schema" in echo_tool
        
        # Check add tool
        add_tool = next(t for t in tools if t["name"] == "add")
        assert add_tool["description"] == "Add two numbers"
    
    async def test_call_echo_tool(self, protocol):
        """Test calling echo tool."""
        result = await protocol.call_method(MCPMethods.TOOLS_CALL, {
            "name": "echo",
            "arguments": {"message": "Hello, MCP!"}
        })
        
        assert "content" in result
        content = result["content"]
        assert len(content) == 1
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "Echo: Hello, MCP!"
    
    async def test_call_add_tool(self, protocol):
        """Test calling add tool.""" 
        result = await protocol.call_method(MCPMethods.TOOLS_CALL, {
            "name": "add",
            "arguments": {"a": 5, "b": 3}
        })
        
        assert "content" in result
        content = result["content"]
        assert len(content) == 1
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "Result: 8"
    
    async def test_call_unknown_tool(self, protocol):
        """Test calling unknown tool."""
        with pytest.raises(MCPProtocolError) as exc_info:
            await protocol.call_method(MCPMethods.TOOLS_CALL, {
                "name": "unknown_tool",
                "arguments": {}
            })
        
        assert "Internal error" in str(exc_info.value)
    
    async def test_list_resources(self, protocol):
        """Test listing available resources."""
        result = await protocol.call_method(MCPMethods.RESOURCES_LIST)
        
        assert "resources" in result
        resources = result["resources"]
        assert len(resources) == 1
        
        resource = resources[0]
        assert resource["uri"] == "file:///test.txt"
        assert resource["name"] == "test.txt"
        assert resource["mime_type"] == "text/plain"
    
    async def test_read_resource(self, protocol):
        """Test reading a resource."""
        result = await protocol.call_method(MCPMethods.RESOURCES_READ, {
            "uri": "file:///test.txt"
        })
        
        assert "contents" in result
        contents = result["contents"]
        assert len(contents) == 1
        
        content = contents[0]
        assert content["uri"] == "file:///test.txt"
        assert content["mime_type"] == "text/plain"
        assert content["text"] == "Hello, World!"
    
    async def test_read_unknown_resource(self, protocol):
        """Test reading unknown resource."""
        with pytest.raises(MCPProtocolError) as exc_info:
            await protocol.call_method(MCPMethods.RESOURCES_READ, {
                "uri": "file:///nonexistent.txt"
            })
        
        assert "Internal error" in str(exc_info.value)
    
    async def test_unknown_method(self, protocol):
        """Test calling unknown method."""
        with pytest.raises(MCPProtocolError) as exc_info:
            await protocol.call_method("unknown/method")
        
        assert "Method not found" in str(exc_info.value)
    
    async def test_full_session_flow(self, protocol, mock_server):
        """Test complete session flow."""
        # 1. Initialize
        init_result = await protocol.call_method(MCPMethods.INITIALIZE, {
            "protocol_version": "2024-11-05",
            "capabilities": {"tools": {}},
            "client_info": {"name": "test-client", "version": "1.0.0"}
        })
        assert "protocol_version" in init_result
        
        # 2. Send initialized notification
        await protocol.send_notification(MCPMethods.NOTIFICATIONS_INITIALIZED)
        assert mock_server.initialized
        
        # 3. List tools
        tools_result = await protocol.call_method(MCPMethods.TOOLS_LIST)
        assert len(tools_result["tools"]) == 2
        
        # 4. Call a tool
        call_result = await protocol.call_method(MCPMethods.TOOLS_CALL, {
            "name": "echo",
            "arguments": {"message": "Session test"}
        })
        assert "Echo: Session test" in call_result["content"][0]["text"]
        
        # 5. List resources
        resources_result = await protocol.call_method(MCPMethods.RESOURCES_LIST)
        assert len(resources_result["resources"]) == 1
        
        # 6. Read resource
        read_result = await protocol.call_method(MCPMethods.RESOURCES_READ, {
            "uri": "file:///test.txt"
        })
        assert read_result["contents"][0]["text"] == "Hello, World!"
        
        # 7. Ping
        ping_result = await protocol.call_method(MCPMethods.PING)
        assert ping_result["pong"] is True


class TestMCPConnectionIntegration:
    """Integration tests using MCPConnection."""
    
    @pytest.fixture
    def mock_server(self):
        """Create mock MCP server."""
        return MockMCPServer()
    
    async def test_connection_with_timeout(self, mock_server):
        """Test connection with timeout handling."""
        transport = MockTransport(mock_server)
        connection = MCPConnection(transport, timeout=1.0)
        
        # Test connection
        result = await connection.connect()
        assert result is True
        assert connection.is_connected()
        
        # Test message exchange
        protocol = MCPProtocol(transport)
        ping_msg = MCPMessage(method=MCPMethods.PING)
        
        await connection.send_with_timeout(ping_msg.to_json().encode('utf-8'))
        response_data = await connection.receive_with_timeout()
        
        response = MCPMessage.from_json(response_data.decode('utf-8'))
        assert response.result == {"pong": True}
        
        # Test disconnection
        await connection.disconnect()


class TestErrorHandling:
    """Test error handling in integration scenarios."""
    
    async def test_malformed_json(self):
        """Test handling of malformed JSON."""
        server = MockMCPServer()
        transport = MockTransport(server)
        await transport.connect()
        
        # Send malformed JSON
        with pytest.raises(json.JSONDecodeError):
            await transport.send(b'{"invalid": json}')
    
    async def test_invalid_message_structure(self):
        """Test handling of invalid message structure."""
        server = MockMCPServer()
        transport = MockTransport(server)
        await transport.connect()
        
        # Send message with invalid JSON-RPC version
        invalid_msg = {"jsonrpc": "1.0", "method": "test"}
        
        with pytest.raises(MCPProtocolError):
            await transport.send(json.dumps(invalid_msg).encode('utf-8'))