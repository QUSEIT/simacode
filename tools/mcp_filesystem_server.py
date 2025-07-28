#!/usr/bin/env python3
"""
Simple MCP Filesystem Server for SimaCode
Provides basic file operations through MCP protocol.
"""

import asyncio
import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add the parent directory to the path to import mcp
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from mcp.server import Server
    from mcp.server.models import InitializationOptions
    from mcp import types
    from mcp.server.stdio import stdio_server
except ImportError:
    print("Error: MCP package not available. Please install with: pip install mcp", file=sys.stderr)
    sys.exit(1)


class FilesystemMCPServer:
    """Simple filesystem operations MCP server."""
    
    def __init__(self, root_path: str = "/tmp"):
        self.root_path = Path(root_path).resolve()
        self.server = Server("filesystem-server")
        
        # Ensure root path exists and is accessible
        if not self.root_path.exists():
            raise ValueError(f"Root path does not exist: {self.root_path}")
        if not self.root_path.is_dir():
            raise ValueError(f"Root path is not a directory: {self.root_path}")
        
        self._setup_tools()
    
    def _setup_tools(self):
        """Set up MCP tools."""
        
        @self.server.list_tools()
        async def list_tools(params: Optional[types.PaginatedRequestParams] = None) -> List[types.Tool]:
            """List available filesystem tools."""
            return [
                types.Tool(
                    name="read_file",
                    description="Read contents of a file",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the file to read"
                            }
                        },
                        "required": ["file_path"]
                    }
                ),
                types.Tool(
                    name="write_file", 
                    description="Write content to a file",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Path to the file to write"
                            },
                            "content": {
                                "type": "string",
                                "description": "Content to write to the file"
                            }
                        },
                        "required": ["file_path", "content"]
                    }
                ),
                types.Tool(
                    name="list_directory",
                    description="List contents of a directory",
                    inputSchema={
                        "type": "object", 
                        "properties": {
                            "directory_path": {
                                "type": "string",
                                "description": "Path to the directory to list"
                            }
                        },
                        "required": ["directory_path"]
                    }
                ),
                types.Tool(
                    name="create_directory",
                    description="Create a new directory",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "directory_path": {
                                "type": "string", 
                                "description": "Path to the directory to create"
                            }
                        },
                        "required": ["directory_path"]
                    }
                )
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[types.TextContent]:
            """Handle tool calls."""
            
            if name == "read_file":
                return await self._read_file(arguments["file_path"])
            elif name == "write_file":
                return await self._write_file(arguments["file_path"], arguments["content"])
            elif name == "list_directory":
                return await self._list_directory(arguments["directory_path"])
            elif name == "create_directory":
                return await self._create_directory(arguments["directory_path"])
            else:
                raise ValueError(f"Unknown tool: {name}")
    
    def _validate_path(self, path: str) -> Path:
        """Validate that path is within allowed root directory."""
        try:
            full_path = Path(path)
            if not full_path.is_absolute():
                full_path = self.root_path / path
            
            full_path = full_path.resolve()
            
            # Check if path is within root directory
            try:
                full_path.relative_to(self.root_path)
            except ValueError:
                raise ValueError(f"Path is outside allowed root directory: {path}")
                
            return full_path
            
        except Exception as e:
            raise ValueError(f"Invalid path: {path} - {str(e)}")
    
    async def _read_file(self, file_path: str) -> List[types.TextContent]:
        """Read file contents."""
        try:
            path = self._validate_path(file_path)
            
            if not path.exists():
                return [types.TextContent(
                    type="text",
                    text=f"Error: File does not exist: {file_path}"
                )]
            
            if not path.is_file():
                return [types.TextContent(
                    type="text", 
                    text=f"Error: Path is not a file: {file_path}"
                )]
            
            # Check file size (limit to 1MB)
            if path.stat().st_size > 1024 * 1024:
                return [types.TextContent(
                    type="text",
                    text=f"Error: File too large (>1MB): {file_path}"
                )]
            
            content = path.read_text(encoding='utf-8')
            return [types.TextContent(
                type="text",
                text=f"File contents of {file_path}:\n\n{content}"
            )]
            
        except UnicodeDecodeError:
            return [types.TextContent(
                type="text",
                text=f"Error: File contains binary data or invalid encoding: {file_path}"
            )]
        except Exception as e:
            return [types.TextContent(
                type="text",
                text=f"Error reading file {file_path}: {str(e)}"
            )]
    
    async def _write_file(self, file_path: str, content: str) -> List[types.TextContent]:
        """Write content to file."""
        try:
            path = self._validate_path(file_path)
            
            # Create parent directories if they don't exist
            path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write content
            path.write_text(content, encoding='utf-8')
            
            return [types.TextContent(
                type="text",
                text=f"Successfully wrote {len(content)} characters to {file_path}"
            )]
            
        except Exception as e:
            return [types.TextContent(
                type="text",
                text=f"Error writing file {file_path}: {str(e)}"
            )]
    
    async def _list_directory(self, directory_path: str) -> List[types.TextContent]:
        """List directory contents."""
        try:
            path = self._validate_path(directory_path)
            
            if not path.exists():
                return [types.TextContent(
                    type="text",
                    text=f"Error: Directory does not exist: {directory_path}"
                )]
            
            if not path.is_dir():
                return [types.TextContent(
                    type="text",
                    text=f"Error: Path is not a directory: {directory_path}"
                )]
            
            # List directory contents
            items = []
            for item in sorted(path.iterdir()):
                if item.is_file():
                    size = item.stat().st_size
                    items.append(f"  📄 {item.name} ({size} bytes)")
                elif item.is_dir():
                    items.append(f"  📁 {item.name}/")
                else:
                    items.append(f"  ❓ {item.name}")
            
            content = f"Contents of {directory_path}:\n\n" + "\n".join(items)
            if not items:
                content += "(directory is empty)"
            
            return [types.TextContent(
                type="text",
                text=content
            )]
            
        except Exception as e:
            return [types.TextContent(
                type="text",
                text=f"Error listing directory {directory_path}: {str(e)}"
            )]
    
    async def _create_directory(self, directory_path: str) -> List[types.TextContent]:
        """Create directory."""
        try:
            path = self._validate_path(directory_path)
            
            if path.exists():
                return [types.TextContent(
                    type="text",
                    text=f"Directory already exists: {directory_path}"
                )]
            
            path.mkdir(parents=True, exist_ok=True)
            
            return [types.TextContent(
                type="text",
                text=f"Successfully created directory: {directory_path}"
            )]
            
        except Exception as e:
            return [types.TextContent(
                type="text",
                text=f"Error creating directory {directory_path}: {str(e)}"
            )]
    
async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Simple MCP Filesystem Server")
    parser.add_argument(
        "--root",
        default="/tmp",
        help="Root directory for filesystem operations (default: /tmp)"
    )
    
    args = parser.parse_args()
    
    try:
        server_instance = FilesystemMCPServer(args.root)
        print(f"Starting MCP filesystem server with root: {server_instance.root_path}", file=sys.stderr)
        
        # Use stdio_server to run with proper streams
        async with stdio_server() as (read_stream, write_stream):
            init_options = InitializationOptions(
                server_name="filesystem-server",
                server_version="1.0.0",
                capabilities=types.ServerCapabilities(
                    tools=types.ToolsCapability(),
                    logging={}
                )
            )
            
            # Keep the server running
            await server_instance.server.run(
                read_stream, 
                write_stream, 
                init_options
            )
            
    except KeyboardInterrupt:
        print("Server stopped by user", file=sys.stderr)
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())