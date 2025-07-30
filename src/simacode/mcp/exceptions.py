"""
MCP-specific exceptions for error handling.

This module defines exception classes for different types of MCP-related errors,
providing structured error handling throughout the MCP integration.
"""


class MCPException(Exception):
    """Base exception for all MCP-related errors."""
    
    def __init__(self, message: str, error_code: str = None, details: dict = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
    
    def to_dict(self) -> dict:
        """Convert exception to dictionary format."""
        return {
            "type": self.__class__.__name__,
            "message": self.message,
            "error_code": self.error_code,
            "details": self.details
        }


class MCPConnectionError(MCPException):
    """Exception raised when MCP server connection fails."""
    
    def __init__(self, message: str, server_name: str = None, **kwargs):
        super().__init__(message, **kwargs)
        self.server_name = server_name


class MCPTimeoutError(MCPException):
    """Exception raised when MCP operation times out."""
    
    def __init__(self, message: str, timeout_seconds: float = None, **kwargs):
        super().__init__(message, **kwargs)
        self.timeout_seconds = timeout_seconds


class MCPProtocolError(MCPException):
    """Exception raised when MCP protocol violation occurs."""
    
    def __init__(self, message: str, protocol_version: str = None, **kwargs):
        super().__init__(message, **kwargs)
        self.protocol_version = protocol_version


class MCPToolNotFoundError(MCPException):
    """Exception raised when requested MCP tool is not found."""
    
    def __init__(self, message: str, tool_name: str = None, server_name: str = None, **kwargs):
        super().__init__(message, **kwargs)
        self.tool_name = tool_name
        self.server_name = server_name


class MCPResourceNotFoundError(MCPException):
    """Exception raised when requested MCP resource is not found."""
    
    def __init__(self, message: str, resource_uri: str = None, **kwargs):
        super().__init__(message, **kwargs)
        self.resource_uri = resource_uri


class MCPSecurityError(MCPException):
    """Exception raised when MCP security validation fails."""
    
    def __init__(self, message: str, security_policy: str = None, **kwargs):
        super().__init__(message, **kwargs)
        self.security_policy = security_policy


class MCPConfigurationError(MCPException):
    """Exception raised when MCP configuration is invalid."""
    
    def __init__(self, message: str, config_field: str = None, **kwargs):
        super().__init__(message, **kwargs)
        self.config_field = config_field