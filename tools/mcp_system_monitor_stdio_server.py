#!/usr/bin/env python3
"""
System Monitor MCP Server (stdio) for SimaCode
Provides system monitoring tools through MCP using stdio transport.
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# System monitoring
import psutil

# Add the parent directory to the path to import mcp
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from mcp.server import Server
    from mcp.server.models import InitializationOptions
    from mcp import types
except ImportError:
    print("Error: MCP package not available. Please install with: pip install mcp", file=sys.stderr)
    sys.exit(1)


class SystemMonitorMCPServer:
    """System monitoring MCP server with stdio transport."""
    
    def __init__(self):
        self.server = Server("system-monitor-server")
        
        # Setup logging to stderr to avoid interfering with stdio communication
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            stream=sys.stderr
        )
        self.logger = logging.getLogger(__name__)
        
        self._setup_tools()
    
    def _setup_tools(self):
        """Set up MCP tools for system monitoring."""
        
        @self.server.list_tools()
        async def list_tools(params: Optional[types.PaginatedRequestParams] = None) -> List[types.Tool]:
            """List available system monitoring tools."""
            return [
                types.Tool(
                    name="get_cpu_usage",
                    description="Get current CPU usage percentage",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "interval": {
                                "type": "number",
                                "description": "Measurement interval in seconds (default: 1.0)",
                                "default": 1.0
                            }
                        }
                    }
                ),
                types.Tool(
                    name="get_memory_usage",
                    description="Get current memory usage statistics",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                types.Tool(
                    name="get_disk_usage",
                    description="Get disk usage statistics for specified path",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path to check disk usage (default: /)",
                                "default": "/"
                            }
                        },
                        "required": []
                    }
                ),
                types.Tool(
                    name="get_system_overview",
                    description="Get comprehensive system resource overview",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "include_processes": {
                                "type": "boolean",
                                "description": "Include top processes information",
                                "default": False
                            }
                        }
                    }
                )
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[types.TextContent]:
            """Handle tool calls."""
            
            try:
                if name == "get_cpu_usage":
                    return await self._get_cpu_usage(arguments)
                elif name == "get_memory_usage":
                    return await self._get_memory_usage(arguments)
                elif name == "get_disk_usage":
                    return await self._get_disk_usage(arguments)
                elif name == "get_system_overview":
                    return await self._get_system_overview(arguments)
                else:
                    raise ValueError(f"Unknown tool: {name}")
                    
            except Exception as e:
                self.logger.error(f"Error executing tool {name}: {str(e)}")
                return [types.TextContent(
                    type="text",
                    text=f"Error: {str(e)}"
                )]
    
    async def _get_cpu_usage(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Get CPU usage percentage."""
        interval = arguments.get("interval", 1.0)
        
        cpu_percent = psutil.cpu_percent(interval=interval)
        cpu_count = psutil.cpu_count()
        cpu_count_logical = psutil.cpu_count(logical=True)
        per_cpu = psutil.cpu_percent(interval=0.1, percpu=True)
        
        result = {
            "cpu_usage_percent": cpu_percent,
            "cpu_count_physical": cpu_count,
            "cpu_count_logical": cpu_count_logical,
            "per_cpu_usage": per_cpu,
            "timestamp": time.time()
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    
    async def _get_memory_usage(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Get memory usage statistics."""
        vmem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        result = {
            "memory": {
                "total_gb": round(vmem.total / (1024**3), 2),
                "available_gb": round(vmem.available / (1024**3), 2),
                "used_gb": round(vmem.used / (1024**3), 2),
                "usage_percent": vmem.percent,
                "free_gb": round(vmem.free / (1024**3), 2)
            },
            "swap": {
                "total_gb": round(swap.total / (1024**3), 2),
                "used_gb": round(swap.used / (1024**3), 2),
                "free_gb": round(swap.free / (1024**3), 2),
                "usage_percent": swap.percent
            },
            "timestamp": time.time()
        }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    
    async def _get_disk_usage(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Get disk usage statistics."""
        path = arguments.get("path", "/")
        
        try:
            disk_usage = psutil.disk_usage(path)
            
            partitions = []
            for partition in psutil.disk_partitions():
                try:
                    partition_usage = psutil.disk_usage(partition.mountpoint)
                    partitions.append({
                        "device": partition.device,
                        "mountpoint": partition.mountpoint,
                        "fstype": partition.fstype,
                        "total_gb": round(partition_usage.total / (1024**3), 2),
                        "used_gb": round(partition_usage.used / (1024**3), 2),
                        "free_gb": round(partition_usage.free / (1024**3), 2),
                        "usage_percent": round((partition_usage.used / partition_usage.total) * 100, 1)
                    })
                except PermissionError:
                    continue
            
            result = {
                "queried_path": path,
                "disk_usage": {
                    "total_gb": round(disk_usage.total / (1024**3), 2),
                    "used_gb": round(disk_usage.used / (1024**3), 2),
                    "free_gb": round(disk_usage.free / (1024**3), 2),
                    "usage_percent": round((disk_usage.used / disk_usage.total) * 100, 1)
                },
                "all_partitions": partitions,
                "timestamp": time.time()
            }
            
        except FileNotFoundError:
            result = {
                "error": f"Path not found: {path}",
                "timestamp": time.time()
            }
        
        return [types.TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    
    async def _get_system_overview(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Get comprehensive system overview."""
        include_processes = arguments.get("include_processes", False)
        
        boot_time = psutil.boot_time()
        uptime = time.time() - boot_time
        
        cpu_percent = psutil.cpu_percent(interval=1.0)
        vmem = psutil.virtual_memory()
        
        try:
            disk_usage = psutil.disk_usage("/")
            disk_percent = round((disk_usage.used / disk_usage.total) * 100, 1)
        except:
            disk_percent = 0
        
        result = {
            "system_overview": {
                "hostname": os.uname().nodename,
                "system": f"{os.uname().sysname} {os.uname().release}",
                "uptime_hours": round(uptime / 3600, 1),
                "cpu_usage_percent": cpu_percent,
                "memory_usage_percent": vmem.percent,
                "disk_usage_percent": disk_percent,
                "load_average": list(os.getloadavg()) if hasattr(os, 'getloadavg') else None
            },
            "timestamp": time.time()
        }
        
        if include_processes:
            processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    proc_info = proc.info
                    cpu_pct = proc_info.get('cpu_percent') or 0
                    mem_pct = proc_info.get('memory_percent') or 0
                    if cpu_pct > 0 or mem_pct > 1:
                        processes.append(proc_info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            processes.sort(key=lambda x: x['cpu_percent'] or 0, reverse=True)
            result["top_processes"] = processes[:10]
        
        return [types.TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    
    async def run(self):
        """Run the MCP server using stdio transport."""
        self.logger.info("Starting System Monitor MCP Server (stdio)")
        
        # Run the MCP server with stdio transport
        import mcp.server.stdio
        from mcp.server.stdio import stdio_server
        
        async with stdio_server() as (read_stream, write_stream):
            init_options = InitializationOptions(
                server_name="system-monitor-server",
                server_version="1.0.0",
                capabilities=types.ServerCapabilities(
                    tools=types.ToolsCapability(),
                    logging={}
                )
            )
            
            await self.server.run(
                read_stream,
                write_stream,
                init_options
            )


def main():
    """Main entry point."""
    try:
        server_instance = SystemMonitorMCPServer()
        print("Starting MCP system monitor server", file=sys.stderr)
        
        asyncio.run(server_instance.run())
        
    except KeyboardInterrupt:
        print("Server stopped by user", file=sys.stderr)
    except Exception as e:
        print(f"Server error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()