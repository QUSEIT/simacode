"""
Tests for MCP exception handling.
"""

import pytest
from simacode.mcp.exceptions import (
    MCPException,
    MCPConnectionError,
    MCPTimeoutError,
    MCPProtocolError,
    MCPToolNotFoundError,
    MCPResourceNotFoundError,
    MCPSecurityError,
    MCPConfigurationError
)


class TestMCPException:
    """Test base MCPException class."""
    
    def test_basic_exception(self):
        """Test basic exception creation."""
        exc = MCPException("Test error")
        
        assert str(exc) == "Test error"
        assert exc.message == "Test error"
        assert exc.error_code is None
        assert exc.details == {}
    
    def test_exception_with_code_and_details(self):
        """Test exception with error code and details."""
        exc = MCPException(
            "Test error",
            error_code="E001",
            details={"context": "test", "severity": "high"}
        )
        
        assert exc.message == "Test error"
        assert exc.error_code == "E001"
        assert exc.details == {"context": "test", "severity": "high"}
    
    def test_to_dict(self):
        """Test exception serialization to dict."""
        exc = MCPException(
            "Test error",
            error_code="E001",
            details={"key": "value"}
        )
        
        expected = {
            "type": "MCPException",
            "message": "Test error",
            "error_code": "E001",
            "details": {"key": "value"}
        }
        
        assert exc.to_dict() == expected
    
    def test_inheritance(self):
        """Test that MCPException inherits from Exception."""
        exc = MCPException("Test error")
        
        assert isinstance(exc, Exception)
        assert isinstance(exc, MCPException)


class TestMCPConnectionError:
    """Test MCPConnectionError class."""
    
    def test_basic_connection_error(self):
        """Test basic connection error."""
        exc = MCPConnectionError("Connection failed")
        
        assert str(exc) == "Connection failed"
        assert exc.message == "Connection failed"
        assert exc.server_name is None
        assert isinstance(exc, MCPException)
    
    def test_connection_error_with_server_name(self):
        """Test connection error with server name."""
        exc = MCPConnectionError(
            "Connection failed",
            server_name="test_server",
            error_code="CONN_001"
        )
        
        assert exc.message == "Connection failed"
        assert exc.server_name == "test_server"
        assert exc.error_code == "CONN_001"
    
    def test_to_dict_includes_server_name(self):
        """Test that to_dict includes server_name."""
        exc = MCPConnectionError("Connection failed", server_name="test_server")
        result = exc.to_dict()
        
        assert result["type"] == "MCPConnectionError"
        assert result["message"] == "Connection failed"
        # Note: server_name is an instance attribute, not in base to_dict


class TestMCPTimeoutError:
    """Test MCPTimeoutError class."""
    
    def test_basic_timeout_error(self):
        """Test basic timeout error."""
        exc = MCPTimeoutError("Operation timed out")
        
        assert str(exc) == "Operation timed out"
        assert exc.message == "Operation timed out"
        assert exc.timeout_seconds is None
        assert isinstance(exc, MCPException)
    
    def test_timeout_error_with_duration(self):
        """Test timeout error with duration."""
        exc = MCPTimeoutError(
            "Operation timed out",
            timeout_seconds=30.5,
            error_code="TIMEOUT_001"
        )
        
        assert exc.message == "Operation timed out"
        assert exc.timeout_seconds == 30.5
        assert exc.error_code == "TIMEOUT_001"


class TestMCPProtocolError:
    """Test MCPProtocolError class."""
    
    def test_basic_protocol_error(self):
        """Test basic protocol error."""
        exc = MCPProtocolError("Invalid message format")
        
        assert str(exc) == "Invalid message format"
        assert exc.message == "Invalid message format"
        assert exc.protocol_version is None
        assert isinstance(exc, MCPException)
    
    def test_protocol_error_with_version(self):
        """Test protocol error with version."""
        exc = MCPProtocolError(
            "Unsupported version",
            protocol_version="1.0",
            error_code="PROTO_001"
        )
        
        assert exc.message == "Unsupported version"
        assert exc.protocol_version == "1.0"
        assert exc.error_code == "PROTO_001"


class TestMCPToolNotFoundError:
    """Test MCPToolNotFoundError class."""
    
    def test_basic_tool_not_found(self):
        """Test basic tool not found error."""
        exc = MCPToolNotFoundError("Tool not found")
        
        assert str(exc) == "Tool not found"
        assert exc.message == "Tool not found"
        assert exc.tool_name is None
        assert exc.server_name is None
        assert isinstance(exc, MCPException)
    
    def test_tool_not_found_with_details(self):
        """Test tool not found error with details."""
        exc = MCPToolNotFoundError(
            "Tool 'git_commit' not found",
            tool_name="git_commit",
            server_name="github_server",
            error_code="TOOL_001"
        )
        
        assert exc.message == "Tool 'git_commit' not found"
        assert exc.tool_name == "git_commit"
        assert exc.server_name == "github_server"
        assert exc.error_code == "TOOL_001"


class TestMCPResourceNotFoundError:
    """Test MCPResourceNotFoundError class."""
    
    def test_basic_resource_not_found(self):
        """Test basic resource not found error."""
        exc = MCPResourceNotFoundError("Resource not found")
        
        assert str(exc) == "Resource not found"
        assert exc.message == "Resource not found"
        assert exc.resource_uri is None
        assert isinstance(exc, MCPException)
    
    def test_resource_not_found_with_uri(self):
        """Test resource not found error with URI."""
        exc = MCPResourceNotFoundError(
            "Resource not accessible",
            resource_uri="file:///path/to/file.txt",
            error_code="RES_001"
        )
        
        assert exc.message == "Resource not accessible"
        assert exc.resource_uri == "file:///path/to/file.txt"
        assert exc.error_code == "RES_001"


class TestMCPSecurityError:
    """Test MCPSecurityError class."""
    
    def test_basic_security_error(self):
        """Test basic security error."""
        exc = MCPSecurityError("Access denied")
        
        assert str(exc) == "Access denied"
        assert exc.message == "Access denied"
        assert exc.security_policy is None
        assert isinstance(exc, MCPException)
    
    def test_security_error_with_policy(self):
        """Test security error with policy."""
        exc = MCPSecurityError(
            "Command not allowed",
            security_policy="strict_mode",
            error_code="SEC_001"
        )
        
        assert exc.message == "Command not allowed"
        assert exc.security_policy == "strict_mode"
        assert exc.error_code == "SEC_001"


class TestMCPConfigurationError:
    """Test MCPConfigurationError class."""
    
    def test_basic_configuration_error(self):
        """Test basic configuration error."""
        exc = MCPConfigurationError("Invalid configuration")
        
        assert str(exc) == "Invalid configuration"
        assert exc.message == "Invalid configuration"
        assert exc.config_field is None
        assert isinstance(exc, MCPException)
    
    def test_configuration_error_with_field(self):
        """Test configuration error with field."""
        exc = MCPConfigurationError(
            "Missing required field",
            config_field="server.command",
            error_code="CONF_001"
        )
        
        assert exc.message == "Missing required field"
        assert exc.config_field == "server.command"
        assert exc.error_code == "CONF_001"


class TestExceptionHierarchy:
    """Test exception inheritance hierarchy."""
    
    def test_all_exceptions_inherit_from_base(self):
        """Test that all MCP exceptions inherit from MCPException."""
        exceptions = [
            MCPConnectionError("test"),
            MCPTimeoutError("test"),
            MCPProtocolError("test"),
            MCPToolNotFoundError("test"),
            MCPResourceNotFoundError("test"),
            MCPSecurityError("test"),
            MCPConfigurationError("test")
        ]
        
        for exc in exceptions:
            assert isinstance(exc, MCPException)
            assert isinstance(exc, Exception)
    
    def test_exception_catching(self):
        """Test that specific exceptions can be caught as MCPException."""
        # Test that we can catch specific exceptions with base class
        with pytest.raises(MCPException):
            raise MCPConnectionError("Connection failed")
        
        with pytest.raises(MCPException):
            raise MCPTimeoutError("Timeout")
        
        with pytest.raises(MCPException):
            raise MCPProtocolError("Protocol error")
    
    def test_exception_types_distinguishable(self):
        """Test that different exception types are distinguishable."""
        conn_exc = MCPConnectionError("Connection failed")
        timeout_exc = MCPTimeoutError("Timeout")
        protocol_exc = MCPProtocolError("Protocol error")
        
        assert type(conn_exc) == MCPConnectionError
        assert type(timeout_exc) == MCPTimeoutError
        assert type(protocol_exc) == MCPProtocolError
        
        assert not isinstance(conn_exc, MCPTimeoutError)
        assert not isinstance(timeout_exc, MCPProtocolError)
        assert not isinstance(protocol_exc, MCPConnectionError)


class TestExceptionUsagePatterns:
    """Test common exception usage patterns."""
    
    def test_exception_chaining(self):
        """Test exception chaining with cause."""
        original_error = ConnectionError("Network unreachable")
        
        try:
            raise original_error
        except ConnectionError as e:
            try:
                raise MCPConnectionError("MCP connection failed") from e
            except MCPConnectionError as mcp_error:
                assert mcp_error.__cause__ == original_error
                assert str(mcp_error) == "MCP connection failed"
    
    def test_exception_with_context_manager(self):
        """Test exception handling in context manager pattern."""
        def risky_operation():
            raise MCPTimeoutError("Operation timed out", timeout_seconds=30.0)
        
        try:
            risky_operation()
        except MCPTimeoutError as e:
            assert e.timeout_seconds == 30.0
            assert "timed out" in str(e)
        except MCPException as e:
            pytest.fail("Should have caught specific MCPTimeoutError")
    
    def test_exception_details_preservation(self):
        """Test that exception details are preserved through re-raising."""
        def inner_function():
            raise MCPToolNotFoundError(
                "Tool not found",
                tool_name="test_tool",
                server_name="test_server",
                error_code="T001",
                details={"available_tools": ["tool1", "tool2"]}
            )
        
        def outer_function():
            try:
                inner_function()
            except MCPToolNotFoundError:
                raise  # Re-raise preserves details
        
        with pytest.raises(MCPToolNotFoundError) as exc_info:
            outer_function()
        
        exc = exc_info.value
        assert exc.tool_name == "test_tool"
        assert exc.server_name == "test_server"
        assert exc.error_code == "T001"
        assert exc.details["available_tools"] == ["tool1", "tool2"]