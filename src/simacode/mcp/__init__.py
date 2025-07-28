"""
MCP (Model Context Protocol) integration for SimaCode.

This module provides MCP client implementation for integrating third-party
MCP servers and tools into the SimaCode ecosystem.
"""

from .exceptions import (
    MCPException,
    MCPConnectionError,
    MCPTimeoutError,
    MCPToolNotFoundError,
    MCPProtocolError
)

__all__ = [
    'MCPException',
    'MCPConnectionError', 
    'MCPTimeoutError',
    'MCPToolNotFoundError',
    'MCPProtocolError'
]