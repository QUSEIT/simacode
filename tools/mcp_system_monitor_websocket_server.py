#!/usr/bin/env python3
"""
System Monitor WebSocket MCP Server for SimaCode
Provides system monitoring tools through MCP over WebSocket with real-time data streaming.
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
import uuid

# System monitoring
import psutil

# WebSocket support
try:
    import websockets
    from websockets.server import serve
except ImportError:
    print("Error: websockets package not available. Please install with: pip install websockets", file=sys.stderr)
    sys.exit(1)


class MCPWebSocketServer:
    """MCP WebSocket server implementation."""
    
    def __init__(self, host: str = "localhost", port: int = 8080):
        self.host = host
        self.port = port
        self.clients = {}  # client_id -> client_info
        self.monitoring_clients = set()  # clients that want real-time monitoring
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        
        # Monitoring task
        self.monitoring_task = None
        
        # MCP tool definitions
        self.tools = {
            "get_cpu_usage": {
                "name": "get_cpu_usage",
                "description": "Get current CPU usage percentage",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "interval": {
                            "type": "number",
                            "description": "Measurement interval in seconds (default: 1.0)",
                            "default": 1.0
                        }
                    }
                }
            },
            "get_memory_usage": {
                "name": "get_memory_usage",
                "description": "Get current memory usage statistics",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            },
            "get_disk_usage": {
                "name": "get_disk_usage",
                "description": "Get disk usage statistics for specified path",
                "inputSchema": {
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
            },
            "get_system_overview": {
                "name": "get_system_overview",
                "description": "Get comprehensive system resource overview",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "include_processes": {
                            "type": "boolean",
                            "description": "Include top processes information",
                            "default": False
                        }
                    }
                }
            },
            "start_monitoring": {
                "name": "start_monitoring",
                "description": "Start real-time system monitoring stream",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "interval": {
                            "type": "number",
                            "description": "Update interval in seconds",
                            "default": 5.0
                        }
                    }
                }
            },
            "stop_monitoring": {
                "name": "stop_monitoring",
                "description": "Stop real-time system monitoring stream",
                "inputSchema": {
                    "type": "object",
                    "properties": {}
                }
            }
        }
    
    async def _get_cpu_usage(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
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
        
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2)
                }
            ]
        }
    
    async def _get_memory_usage(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
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
        
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2)
                }
            ]
        }
    
    async def _get_disk_usage(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
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
        
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2)
                }
            ]
        }
    
    async def _get_system_overview(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
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
        
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(result, indent=2)
                }
            ]
        }
    
    async def _start_monitoring(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Start real-time monitoring for the current client."""
        interval = arguments.get("interval", 5.0)
        
        # Note: We would need client context to identify which client requested this
        # For now, we'll start monitoring for all connected clients
        if not self.monitoring_task:
            self.monitoring_task = asyncio.create_task(self._monitoring_loop(interval))
        
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Real-time monitoring started with {interval}s interval"
                }
            ]
        }
    
    async def _stop_monitoring(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Stop real-time monitoring."""
        if self.monitoring_task:
            self.monitoring_task.cancel()
            self.monitoring_task = None
        
        return {
            "content": [
                {
                    "type": "text",
                    "text": "Real-time monitoring stopped"
                }
            ]
        }
    
    async def _monitoring_loop(self, interval: float):
        """Background loop for sending monitoring data."""
        while True:
            try:
                # Get current system stats
                cpu_percent = psutil.cpu_percent(interval=1.0)
                vmem = psutil.virtual_memory()
                
                try:
                    disk_usage = psutil.disk_usage("/")
                    disk_percent = round((disk_usage.used / disk_usage.total) * 100, 1)
                except:
                    disk_percent = 0
                
                data = {
                    "type": "monitoring_update",
                    "cpu_usage": cpu_percent,
                    "memory_usage": vmem.percent,
                    "disk_usage": disk_percent,
                    "timestamp": time.time()
                }
                
                # Send to all monitoring clients
                # Note: This is a simplified implementation
                # In a real implementation, we'd send MCP notifications
                self.logger.debug(f"Monitoring data: {data}")
                
                await asyncio.sleep(interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(interval)
    
    async def handle_mcp_message(self, websocket, message):
        """Handle incoming MCP message."""
        try:
            data = json.loads(message)
            
            # Handle MCP initialize
            if data.get("method") == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": data.get("id"),
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {},
                            "notifications": {}
                        },
                        "serverInfo": {
                            "name": "system-monitor-server",
                            "version": "1.0.0"
                        }
                    }
                }
                await websocket.send(json.dumps(response))
                return
            
            # Handle tools/list
            if data.get("method") == "tools/list":
                tool_list = list(self.tools.values())
                
                response = {
                    "jsonrpc": "2.0",
                    "id": data.get("id"),
                    "result": {
                        "tools": tool_list
                    }
                }
                await websocket.send(json.dumps(response))
                return
            
            # Handle tools/call
            if data.get("method") == "tools/call":
                params = data.get("params", {})
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                
                # Call the tool
                if tool_name == "get_cpu_usage":
                    result = await self._get_cpu_usage(arguments)
                elif tool_name == "get_memory_usage":
                    result = await self._get_memory_usage(arguments)
                elif tool_name == "get_disk_usage":
                    result = await self._get_disk_usage(arguments)
                elif tool_name == "get_system_overview":
                    result = await self._get_system_overview(arguments)
                elif tool_name == "start_monitoring":
                    result = await self._start_monitoring(arguments)
                elif tool_name == "stop_monitoring":
                    result = await self._stop_monitoring(arguments)
                else:
                    raise ValueError(f"Unknown tool: {tool_name}")
                
                response = {
                    "jsonrpc": "2.0",
                    "id": data.get("id"),
                    "result": result
                }
                await websocket.send(json.dumps(response))
                return
            
            # Handle notifications/initialized
            if data.get("method") == "notifications/initialized":
                # Client is ready
                self.logger.info("Client initialized successfully")
                return
            
            # Unknown method
            if "id" in data:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": data.get("id"),
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {data.get('method')}"
                    }
                }
                await websocket.send(json.dumps(error_response))
        
        except Exception as e:
            self.logger.error(f"Error handling MCP message: {e}")
            if "id" in data:
                error_response = {
                    "jsonrpc": "2.0",
                    "id": data.get("id"),
                    "error": {
                        "code": -32603,
                        "message": f"Internal error: {str(e)}"
                    }
                }
                await websocket.send(json.dumps(error_response))
    
    async def handle_client(self, websocket, path):
        """Handle WebSocket client connection."""
        client_id = str(uuid.uuid4())
        self.clients[client_id] = {
            "websocket": websocket,
            "connected_at": time.time()
        }
        
        self.logger.info(f"Client {client_id} connected from {websocket.remote_address}")
        
        try:
            async for message in websocket:
                await self.handle_mcp_message(websocket, message)
        
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            self.logger.error(f"Error handling client {client_id}: {e}")
        finally:
            if client_id in self.clients:
                del self.clients[client_id]
            self.logger.info(f"Client {client_id} disconnected")
    
    async def run(self):
        """Run the MCP WebSocket server."""
        self.logger.info(f"Starting MCP WebSocket server on {self.host}:{self.port}")
        
        async with serve(self.handle_client, self.host, self.port):
            self.logger.info(f"MCP WebSocket server listening on ws://{self.host}:{self.port}")
            
            # Keep server running
            try:
                await asyncio.Future()  # Run forever
            except KeyboardInterrupt:
                self.logger.info("Shutting down server...")
                if self.monitoring_task:
                    self.monitoring_task.cancel()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="System Monitor MCP WebSocket Server")
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
    server = MCPWebSocketServer(host=args.host, port=args.port)
    
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        print("\nShutting down server...")


if __name__ == "__main__":
    main()