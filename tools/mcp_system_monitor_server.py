#!/usr/bin/env python3
"""
System Monitor WebSocket MCP Server for SimaCode
Provides system monitoring tools (CPU, memory, disk usage) through WebSocket MCP protocol.
"""

import asyncio
import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# System monitoring
import psutil

# WebSocket support
try:
    import websockets
    from websockets.server import WebSocketServerProtocol
except ImportError:
    print("Error: websockets package not available. Please install with: pip install websockets", file=sys.stderr)
    sys.exit(1)

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
    """System monitoring MCP server with WebSocket support."""
    
    def __init__(self, host: str = "localhost", port: int = 8080):
        self.host = host
        self.port = port
        self.server = Server("system-monitor-server")
        self.websocket_server = None
        self.connected_clients = set()
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
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
                ),
                types.Tool(
                    name="start_monitoring",
                    description="Start real-time system monitoring (WebSocket stream)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "interval": {
                                "type": "number",
                                "description": "Update interval in seconds",
                                "default": 5.0
                            }
                        }
                    }
                ),
                types.Tool(
                    name="stop_monitoring",
                    description="Stop real-time system monitoring",
                    inputSchema={
                        "type": "object",
                        "properties": {}
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
                elif name == "start_monitoring":
                    return await self._start_monitoring(arguments)
                elif name == "stop_monitoring":
                    return await self._stop_monitoring(arguments)
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
        
        # Get CPU usage over the specified interval
        cpu_percent = psutil.cpu_percent(interval=interval)
        cpu_count = psutil.cpu_count()
        cpu_count_logical = psutil.cpu_count(logical=True)
        
        # Get per-CPU usage
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
        # Virtual memory
        vmem = psutil.virtual_memory()
        
        # Swap memory
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
            # Get disk usage for the specified path
            disk_usage = psutil.disk_usage(path)
            
            # Get all disk partitions
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
                    # Skip partitions we can't access
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
        
        # Get basic system info
        boot_time = psutil.boot_time()
        uptime = time.time() - boot_time
        
        # CPU info
        cpu_percent = psutil.cpu_percent(interval=1.0)
        
        # Memory info
        vmem = psutil.virtual_memory()
        
        # Disk info (root partition)
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
        
        # Add top processes if requested
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
            
            # Sort by CPU usage and take top 10
            processes.sort(key=lambda x: x['cpu_percent'] or 0, reverse=True)
            result["top_processes"] = processes[:10]
        
        return [types.TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    
    async def _start_monitoring(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Start real-time monitoring."""
        interval = arguments.get("interval", 5.0)
        
        # This would start the WebSocket server for real-time updates
        if not self.websocket_server:
            asyncio.create_task(self._start_websocket_server())
        
        return [types.TextContent(
            type="text",
            text=f"Real-time monitoring started with {interval}s interval. Connect to ws://{self.host}:{self.port}/monitor"
        )]
    
    async def _stop_monitoring(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Stop real-time monitoring."""
        if self.websocket_server:
            self.websocket_server.close()
            await self.websocket_server.wait_closed()
            self.websocket_server = None
        
        return [types.TextContent(
            type="text",
            text="Real-time monitoring stopped"
        )]
    
    async def _start_websocket_server(self):
        """Start WebSocket server for real-time monitoring."""
        async def handle_client(websocket):
            self.connected_clients.add(websocket)
            self.logger.info(f"Client connected: {websocket.remote_address}")
            
            try:
                # Send periodic system updates
                while True:
                    # Get current system stats
                    cpu_percent = psutil.cpu_percent(interval=1.0)
                    vmem = psutil.virtual_memory()
                    
                    try:
                        disk_usage = psutil.disk_usage("/")
                        disk_percent = round((disk_usage.used / disk_usage.total) * 100, 1)
                    except:
                        disk_percent = 0
                    
                    data = {
                        "type": "system_stats",
                        "cpu_usage": cpu_percent,
                        "memory_usage": vmem.percent,
                        "disk_usage": disk_percent,
                        "timestamp": time.time()
                    }
                    
                    await websocket.send(json.dumps(data))
                    await asyncio.sleep(5)  # Update every 5 seconds
                    
            except websockets.exceptions.ConnectionClosed:
                pass
            except Exception as e:
                self.logger.error(f"Error in WebSocket handler: {e}")
            finally:
                self.connected_clients.discard(websocket)
                self.logger.info(f"Client disconnected")
        
        self.websocket_server = await websockets.serve(
            handle_client, 
            self.host, 
            self.port
        )
        self.logger.info(f"WebSocket server started on ws://{self.host}:{self.port}")
    
    async def run(self):
        """Run the MCP server."""
        # Start WebSocket server for real-time monitoring
        await self._start_websocket_server()
        
        # Keep the server running
        self.logger.info(f"System Monitor MCP Server running on {self.host}:{self.port}")
        try:
            await asyncio.Future()  # Run forever
        except KeyboardInterrupt:
            self.logger.info("Shutting down server...")
            if self.websocket_server:
                self.websocket_server.close()
                await self.websocket_server.wait_closed()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="System Monitor WebSocket MCP Server")
    parser.add_argument(
        "--host",
        default="localhost",
        help="Host to bind to (default: localhost)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to bind to (default: 8080)"
    )
    
    args = parser.parse_args()
    
    # Create and run server
    server = SystemMonitorMCPServer(host=args.host, port=args.port)
    
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        print("\nShutting down server...")


if __name__ == "__main__":
    main()