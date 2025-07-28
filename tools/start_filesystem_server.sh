#!/bin/bash
# Simple wrapper script to start MCP filesystem server
cd "$(dirname "$0")/.."
exec python tools/mcp_filesystem_server.py --root .