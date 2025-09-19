"""
Tests for MCP protocol implementation.
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from simacode.mcp.protocol import (
    MCPMessage, MCPTool, MCPResource, MCPPrompt, MCPResult,
    MCPProtocol, MCPMethods, MCPErrorCodes
)
from simacode.mcp.exceptions import MCPProtocolError


class TestMCPMessage:
    """Test MCPMessage class."""
    
    def test_create_request_message(self):
        """Test creating a request message."""
        msg = MCPMessage(method="test_method", params={"arg": "value"})
        
        assert msg.jsonrpc == "2.0"
        assert msg.method == "test_method"
        assert msg.params == {"arg": "value"}
        assert msg.id is not None  # Auto-generated
        assert msg.is_request()
        assert not msg.is_notification()
        assert not msg.is_response()
        assert not msg.is_error()
    
    def test_create_notification_message(self):
        """Test creating a notification message."""
        msg = MCPMessage(method="test_notification", id=None)
        
        assert msg.method == "test_notification"
        assert msg.id is None
        assert not msg.is_request()
        assert msg.is_notification()
        assert not msg.is_response()
        assert not msg.is_error()
    
    def test_create_response_message(self):
        """Test creating a response message."""
        msg = MCPMessage(id="123", result={"status": "success"})
        
        assert msg.id == "123"
        assert msg.result == {"status": "success"}
        assert msg.method is None
        assert not msg.is_request()
        assert not msg.is_notification()
        assert msg.is_response()
        assert not msg.is_error()
    
    def test_create_error_message(self):
        """Test creating an error message."""
        error_info = {"code": -32000, "message": "Test error"}
        msg = MCPMessage(id="123", error=error_info)
        
        assert msg.id == "123"
        assert msg.error == error_info
        assert msg.is_error()
        assert msg.is_response()
    
    def test_to_dict(self):
        """Test message serialization to dict."""
        msg = MCPMessage(
            id="test_id",
            method="test_method",
            params={"key": "value"}
        )
        
        data = msg.to_dict()
        expected = {
            "jsonrpc": "2.0",
            "id": "test_id",
            "method": "test_method",
            "params": {"key": "value"}
        }
        
        assert data == expected
    
    def test_to_json(self):
        """Test message serialization to JSON."""
        msg = MCPMessage(id="123", result="success")
        json_str = msg.to_json()
        
        # Should be valid JSON
        data = json.loads(json_str)
        assert data["jsonrpc"] == "2.0"
        assert data["id"] == "123"
        assert data["result"] == "success"
    
    def test_from_dict_valid(self):
        """Test creating message from valid dict."""
        data = {
            "jsonrpc": "2.0",
            "id": "test_id",
            "method": "test_method",
            "params": {"arg": "value"}
        }
        
        msg = MCPMessage.from_dict(data)
        assert msg.jsonrpc == "2.0"
        assert msg.id == "test_id"
        assert msg.method == "test_method"
        assert msg.params == {"arg": "value"}
    
    def test_from_dict_invalid_version(self):
        """Test creating message from dict with invalid JSON-RPC version."""
        data = {"jsonrpc": "1.0", "method": "test"}
        
        with pytest.raises(MCPProtocolError) as exc_info:
            MCPMessage.from_dict(data)
        
        assert "Invalid JSON-RPC version" in str(exc_info.value)
    
    def test_from_json_valid(self):
        """Test creating message from valid JSON."""
        json_str = '{"jsonrpc": "2.0", "id": "123", "result": "ok"}'
        msg = MCPMessage.from_json(json_str)
        
        assert msg.jsonrpc == "2.0"
        assert msg.id == "123"
        assert msg.result == "ok"
    
    def test_from_json_invalid(self):
        """Test creating message from invalid JSON."""
        invalid_json = '{"jsonrpc": "2.0", "id": 123, invalid}'
        
        with pytest.raises(MCPProtocolError) as exc_info:
            MCPMessage.from_json(invalid_json)
        
        assert "Invalid JSON" in str(exc_info.value)


class TestMCPDataModels:
    """Test MCP data model classes."""
    
    def test_mcp_tool(self):
        """Test MCPTool data model."""
        tool = MCPTool(
            name="test_tool",
            description="A test tool",
            server_name="test_server",
            input_schema={"type": "object", "properties": {"arg": {"type": "string"}}}
        )
        
        assert tool.name == "test_tool"
        assert tool.description == "A test tool"
        assert tool.server_name == "test_server"
        assert tool.input_schema["type"] == "object"
        
        data = tool.to_dict()
        assert data["name"] == "test_tool"
        assert data["server_name"] == "test_server"
    
    def test_mcp_resource(self):
        """Test MCPResource data model."""
        resource = MCPResource(
            uri="file:///test.txt",
            name="test.txt",
            description="Test file",
            mime_type="text/plain"
        )
        
        assert resource.uri == "file:///test.txt"
        assert resource.name == "test.txt"
        assert resource.mime_type == "text/plain"
        
        data = resource.to_dict()
        assert data["uri"] == "file:///test.txt"
        assert data["mime_type"] == "text/plain"
    
    def test_mcp_prompt(self):
        """Test MCPPrompt data model."""
        prompt = MCPPrompt(
            name="test_prompt",
            description="A test prompt",
            arguments=[{"name": "input", "type": "string"}]
        )
        
        assert prompt.name == "test_prompt"
        assert prompt.description == "A test prompt"
        assert len(prompt.arguments) == 1
        
        data = prompt.to_dict()
        assert data["name"] == "test_prompt"
        assert data["arguments"][0]["name"] == "input"
    
    def test_mcp_result(self):
        """Test MCPResult data model."""
        # Success result
        success_result = MCPResult(
            success=True,
            content="Operation completed",
            metadata={"duration": 1.5}
        )
        
        assert success_result.success is True
        assert success_result.content == "Operation completed"
        assert success_result.error is None
        assert success_result.metadata["duration"] == 1.5
        
        # Error result
        error_result = MCPResult(
            success=False,
            error="Something went wrong"
        )
        
        assert error_result.success is False
        assert error_result.error == "Something went wrong"
        assert error_result.content is None


class TestMCPProtocol:
    """Test MCPProtocol class."""
    
    @pytest.fixture
    def mock_transport(self):
        """Create a mock transport."""
        transport = AsyncMock()
        transport.is_connected.return_value = True
        return transport
    
    @pytest.fixture
    def protocol(self, mock_transport):
        """Create MCPProtocol instance with mock transport."""
        return MCPProtocol(mock_transport)
    
    async def test_send_message(self, protocol, mock_transport):
        """Test sending a message."""
        msg = MCPMessage(method="test", params={"arg": "value"})
        
        await protocol.send_message(msg)
        
        # Verify transport.send was called with correct data
        mock_transport.send.assert_called_once()
        sent_data = mock_transport.send.call_args[0][0]
        
        # Should be valid JSON bytes
        json_data = json.loads(sent_data.decode('utf-8'))
        assert json_data["method"] == "test"
        assert json_data["params"] == {"arg": "value"}
    
    async def test_send_message_not_connected(self, protocol, mock_transport):
        """Test sending message when transport not connected."""
        mock_transport.is_connected.return_value = False
        msg = MCPMessage(method="test")
        
        with pytest.raises(MCPProtocolError) as exc_info:
            await protocol.send_message(msg)
        
        assert "Transport not connected" in str(exc_info.value)
    
    async def test_receive_message(self, protocol, mock_transport):
        """Test receiving a message."""
        # Mock received data
        response_data = MCPMessage(id="123", result="success")
        json_bytes = response_data.to_json().encode('utf-8')
        mock_transport.receive.return_value = json_bytes
        
        received_msg = await protocol.receive_message()
        
        assert received_msg.id == "123"
        assert received_msg.result == "success"
        mock_transport.receive.assert_called_once()
    
    async def test_call_method_success(self, protocol, mock_transport):
        """Test successful method call."""
        # Mock transport to return a success response
        request_id = None
        
        def capture_send(data):
            nonlocal request_id
            msg_data = json.loads(data.decode('utf-8'))
            request_id = msg_data["id"]
        
        mock_transport.send.side_effect = capture_send
        
        # Mock successful response
        def mock_receive():
            response = MCPMessage(id=request_id, result={"status": "ok"})
            return response.to_json().encode('utf-8')
        
        mock_transport.receive.side_effect = mock_receive
        
        result = await protocol.call_method("test_method", {"arg": "value"})
        
        assert result == {"status": "ok"}
        mock_transport.send.assert_called_once()
        mock_transport.receive.assert_called_once()
    
    async def test_call_method_error_response(self, protocol, mock_transport):
        """Test method call with error response."""
        request_id = None
        
        def capture_send(data):
            nonlocal request_id
            msg_data = json.loads(data.decode('utf-8'))
            request_id = msg_data["id"]
        
        mock_transport.send.side_effect = capture_send
        
        # Mock error response
        def mock_receive():
            error_info = {"code": -32000, "message": "Method failed"}
            response = MCPMessage(id=request_id, error=error_info)
            return response.to_json().encode('utf-8')
        
        mock_transport.receive.side_effect = mock_receive
        
        with pytest.raises(MCPProtocolError) as exc_info:
            await protocol.call_method("failing_method")
        
        assert "Method call failed: Method failed" in str(exc_info.value)
        assert exc_info.value.error_code == "-32000"
    
    async def test_call_method_id_mismatch(self, protocol, mock_transport):
        """Test method call with response ID mismatch."""
        def capture_send(data):
            pass  # Don't need to capture for this test
        
        mock_transport.send.side_effect = capture_send
        
        # Mock response with wrong ID
        def mock_receive():
            response = MCPMessage(id="wrong_id", result="ok")
            return response.to_json().encode('utf-8')
        
        mock_transport.receive.side_effect = mock_receive
        
        with pytest.raises(MCPProtocolError) as exc_info:
            await protocol.call_method("test_method")
        
        assert "Response ID mismatch" in str(exc_info.value)
    
    async def test_send_notification(self, protocol, mock_transport):
        """Test sending a notification."""
        await protocol.send_notification("test_notification", {"data": "value"})
        
        # Verify notification was sent
        mock_transport.send.assert_called_once()
        sent_data = mock_transport.send.call_args[0][0]
        
        json_data = json.loads(sent_data.decode('utf-8'))
        assert json_data["method"] == "test_notification"
        assert json_data["params"] == {"data": "value"}
        assert "id" not in json_data  # Notifications don't have IDs
    
    def test_generate_request_id(self, protocol):
        """Test request ID generation."""
        id1 = protocol._generate_request_id()
        id2 = protocol._generate_request_id()
        
        assert id1 != id2
        assert id1.startswith("req_")
        assert id2.startswith("req_")


class TestMCPConstants:
    """Test MCP constants."""
    
    def test_mcp_methods(self):
        """Test MCPMethods constants."""
        assert MCPMethods.INITIALIZE == "initialize"
        assert MCPMethods.TOOLS_LIST == "tools/list"
        assert MCPMethods.TOOLS_CALL == "tools/call"
        assert MCPMethods.RESOURCES_LIST == "resources/list"
        assert MCPMethods.RESOURCES_READ == "resources/read"
    
    def test_mcp_error_codes(self):
        """Test MCPErrorCodes constants."""
        assert MCPErrorCodes.PARSE_ERROR == -32700
        assert MCPErrorCodes.INVALID_REQUEST == -32600
        assert MCPErrorCodes.METHOD_NOT_FOUND == -32601
        assert MCPErrorCodes.TOOL_NOT_FOUND == -32000
        assert MCPErrorCodes.SECURITY_ERROR == -32002


class TestMCPProtocolAsync:
    """Test MCPProtocol async functionality."""

    @pytest.fixture
    def mock_transport(self):
        """Create a mock transport for async tests."""
        transport = AsyncMock()
        transport.is_connected.return_value = True
        return transport

    @pytest.fixture
    def protocol(self, mock_transport):
        """Create MCPProtocol instance with mock transport."""
        protocol = MCPProtocol(mock_transport)
        # Set mock server capabilities to support async
        protocol.set_server_capabilities({
            "tools": {"async_support": True}
        })
        return protocol

    async def test_call_tool_async_with_progress(self, protocol, mock_transport):
        """Test async tool call with progress updates."""
        request_id = None

        def capture_send(data):
            nonlocal request_id
            msg_data = json.loads(data.decode('utf-8'))
            request_id = msg_data["id"]

        mock_transport.send.side_effect = capture_send

        # Mock progress and result notifications
        progress_responses = [
            MCPMessage(method="tools/progress", params={
                "request_id": None,  # Will be set dynamically
                "progress": 50,
                "message": "Processing..."
            }),
            MCPMessage(method="tools/result", params={
                "request_id": None,  # Will be set dynamically
                "result": "Task completed"
            })
        ]

        # Progress callback to capture progress updates
        progress_updates = []

        async def progress_callback(data):
            progress_updates.append(data)

        # Create a task to simulate async responses
        async def send_async_responses():
            await asyncio.sleep(0.1)  # Small delay to ensure request is sent first

            for response in progress_responses:
                # Set the request_id that was captured
                response.params["request_id"] = request_id

                # Put response in the queue
                if request_id in protocol._async_response_queues:
                    await protocol._async_response_queues[request_id].put(response)

        # Start the background task
        response_task = asyncio.create_task(send_async_responses())

        # Collect results
        results = []
        async for result in protocol.call_tool_async(
            tool_name="test_tool",
            arguments={"param": "value"},
            progress_callback=progress_callback
        ):
            results.append(result)

        # Wait for response task to complete
        await response_task

        # Verify results
        assert len(results) == 2

        # First result should be progress
        progress_result = results[0]
        assert progress_result.success is True
        assert progress_result.metadata["type"] == "progress"
        assert progress_result.content["progress"] == 50

        # Second result should be final result
        final_result = results[1]
        assert final_result.success is True
        assert final_result.metadata["type"] == "final_result"
        assert final_result.content == "Task completed"

        # Verify progress callback was called
        assert len(progress_updates) == 1
        assert progress_updates[0]["progress"] == 50

    async def test_call_tool_async_server_no_support(self, mock_transport):
        """Test async tool call fallback when server doesn't support async."""
        protocol = MCPProtocol(mock_transport)
        # Set server capabilities without async support
        protocol.set_server_capabilities({
            "tools": {"async_support": False}
        })

        request_id = None

        def capture_send(data):
            nonlocal request_id
            msg_data = json.loads(data.decode('utf-8'))
            request_id = msg_data["id"]

        mock_transport.send.side_effect = capture_send

        # Mock standard tool call response
        def mock_receive():
            response = MCPMessage(id=request_id, result="Standard result")
            return response.to_json().encode('utf-8')

        mock_transport.receive.side_effect = mock_receive

        # Collect results
        results = []
        async for result in protocol.call_tool_async(
            tool_name="test_tool",
            arguments={"param": "value"}
        ):
            results.append(result)

        # Should get one result from fallback
        assert len(results) == 1
        result = results[0]
        assert result.success is True
        assert result.content == "Standard result"
        assert result.metadata.get("fallback_mode") is True

    async def test_call_tool_async_error(self, protocol, mock_transport):
        """Test async tool call with error response."""
        request_id = None

        def capture_send(data):
            nonlocal request_id
            msg_data = json.loads(data.decode('utf-8'))
            request_id = msg_data["id"]

        mock_transport.send.side_effect = capture_send

        # Mock error response
        error_response = MCPMessage(method="tools/error", params={
            "request_id": None,  # Will be set dynamically
            "error": "Tool execution failed"
        })

        # Create a task to simulate async error response
        async def send_error_response():
            await asyncio.sleep(0.1)
            error_response.params["request_id"] = request_id

            if request_id in protocol._async_response_queues:
                await protocol._async_response_queues[request_id].put(error_response)

        response_task = asyncio.create_task(send_error_response())

        # Collect results
        results = []
        async for result in protocol.call_tool_async(
            tool_name="failing_tool",
            arguments={"param": "value"}
        ):
            results.append(result)

        await response_task

        # Should get one error result
        assert len(results) == 1
        result = results[0]
        assert result.success is False
        assert result.error == "Tool execution failed"
        assert result.metadata["type"] == "error"

    async def test_call_tool_async_timeout(self, protocol, mock_transport):
        """Test async tool call timeout."""
        mock_transport.send.side_effect = lambda data: None

        # No responses will be sent, should timeout
        results = []
        async for result in protocol.call_tool_async(
            tool_name="slow_tool",
            arguments={"param": "value"},
            timeout=0.1  # Very short timeout
        ):
            results.append(result)

        # Should get one timeout error result
        assert len(results) == 1
        result = results[0]
        assert result.success is False
        assert "timeout" in result.error.lower()
        assert result.metadata["type"] == "timeout_error"

    async def test_handle_notification_routing(self, protocol):
        """Test notification routing to async response queues."""
        # Create a mock async response queue
        request_id = "test_req_123"
        protocol._async_response_queues[request_id] = asyncio.Queue()

        # Create a progress notification
        notification = MCPMessage(
            method="tools/progress",
            params={
                "request_id": request_id,
                "progress": 75,
                "message": "Almost done..."
            }
        )

        # Handle the notification
        await protocol._handle_notification(notification)

        # Verify it was routed to the correct queue
        queue = protocol._async_response_queues[request_id]
        assert not queue.empty()

        routed_message = await queue.get()
        assert routed_message.method == "tools/progress"
        assert routed_message.params["progress"] == 75

    async def test_handle_notification_no_queue(self, protocol):
        """Test notification handling when no matching queue exists."""
        # Create a notification for non-existent request
        notification = MCPMessage(
            method="tools/progress",
            params={
                "request_id": "nonexistent_req",
                "progress": 50
            }
        )

        # Should handle gracefully without error
        await protocol._handle_notification(notification)
        # No assertion needed, just verify it doesn't raise an exception

    def test_set_server_capabilities(self, protocol):
        """Test setting server capabilities."""
        capabilities = {
            "tools": {"async_support": True, "streaming": False},
            "resources": {"subscribe": True}
        }

        protocol.set_server_capabilities(capabilities)

        assert protocol._server_capabilities == capabilities

    async def test_server_supports_async_detection(self, protocol):
        """Test server async support detection."""
        # Test with async support
        protocol.set_server_capabilities({
            "tools": {"async_support": True}
        })

        assert await protocol._server_supports_async() is True

        # Test without async support
        protocol.set_server_capabilities({
            "tools": {"async_support": False}
        })

        assert await protocol._server_supports_async() is False

        # Test with no capabilities
        protocol._server_capabilities = None
        assert await protocol._server_supports_async() is True  # Default behavior


class TestAsyncMethodConstants:
    """Test new async method constants."""

    def test_async_methods(self):
        """Test new async method constants."""
        assert MCPMethods.TOOLS_CALL_ASYNC == "tools/call_async"
        assert MCPMethods.TOOLS_PROGRESS == "tools/progress"
        assert MCPMethods.TOOLS_RESULT == "tools/result"
        assert MCPMethods.TOOLS_ERROR == "tools/error"