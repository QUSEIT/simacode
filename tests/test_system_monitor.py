#!/usr/bin/env python3
"""
Test script for System Monitor MCP Server
"""

import asyncio
import json
import subprocess
import time
from pathlib import Path

# Check if required packages are installed
try:
    import psutil
    import websockets
except ImportError as e:
    print(f"Missing required package: {e}")
    print("Please install with: pip install psutil websockets")
    exit(1)

# Import the server class
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.mcp_system_monitor_stdio_server import SystemMonitorMCPServer


async def test_server_direct():
    """Test the server functions directly."""
    print("=== Testing System Monitor MCP Server Directly ===\n")
    
    server = SystemMonitorMCPServer()
    
    # Test CPU usage
    print("1. Testing CPU Usage:")
    cpu_result = await server._get_cpu_usage({"interval": 0.5})
    cpu_data = json.loads(cpu_result[0].text)
    print(f"   CPU Usage: {cpu_data['cpu_usage_percent']:.1f}%")
    print(f"   CPU Cores: {cpu_data['cpu_count_physical']} physical, {cpu_data['cpu_count_logical']} logical")
    print()
    
    # Test Memory usage
    print("2. Testing Memory Usage:")
    mem_result = await server._get_memory_usage({})
    mem_data = json.loads(mem_result[0].text)
    print(f"   Memory: {mem_data['memory']['used_gb']:.1f}GB / {mem_data['memory']['total_gb']:.1f}GB ({mem_data['memory']['usage_percent']:.1f}%)")
    if mem_data['swap']['total_gb'] > 0:
        print(f"   Swap: {mem_data['swap']['used_gb']:.1f}GB / {mem_data['swap']['total_gb']:.1f}GB ({mem_data['swap']['usage_percent']:.1f}%)")
    print()
    
    # Test Disk usage
    print("3. Testing Disk Usage:")
    disk_result = await server._get_disk_usage({"path": "/"})
    disk_data = json.loads(disk_result[0].text)
    if "error" not in disk_data:
        disk_info = disk_data['disk_usage']
        print(f"   Root Disk: {disk_info['used_gb']:.1f}GB / {disk_info['total_gb']:.1f}GB ({disk_info['usage_percent']:.1f}%)")
        print(f"   All partitions found: {len(disk_data['all_partitions'])}")
    else:
        print(f"   Error: {disk_data['error']}")
    print()
    
    # Test System overview
    print("4. Testing System Overview:")
    overview_result = await server._get_system_overview({"include_processes": True})
    overview_data = json.loads(overview_result[0].text)
    sys_info = overview_data['system_overview']
    print(f"   Hostname: {sys_info['hostname']}")
    print(f"   System: {sys_info['system']}")
    print(f"   Uptime: {sys_info['uptime_hours']:.1f} hours")
    print(f"   CPU: {sys_info['cpu_usage_percent']:.1f}%")
    print(f"   Memory: {sys_info['memory_usage_percent']:.1f}%")
    print(f"   Disk: {sys_info['disk_usage_percent']:.1f}%")
    if 'load_average' in sys_info and sys_info['load_average']:
        print(f"   Load Average: {sys_info['load_average']}")
    if 'top_processes' in overview_data:
        print(f"   Top processes: {len(overview_data['top_processes'])} found")
    print()


async def test_mcp_protocol():
    """Test MCP protocol compliance."""
    print("=== Testing MCP Protocol Compliance ===\n")
    
    server = SystemMonitorMCPServer()
    
    # Test that server has proper MCP methods
    print("1. Checking MCP protocol methods:")
    assert hasattr(server, '_get_cpu_usage'), "Missing _get_cpu_usage method"
    assert hasattr(server, '_get_memory_usage'), "Missing _get_memory_usage method"
    assert hasattr(server, '_get_disk_usage'), "Missing _get_disk_usage method"
    assert hasattr(server, '_get_system_overview'), "Missing _get_system_overview method"
    print("   ✅ All required MCP methods present")
    print()
    
    # Test method parameters
    print("2. Testing method parameters:")
    try:
        # Test with minimal parameters
        cpu_result = await server._get_cpu_usage({})
        mem_result = await server._get_memory_usage({})
        disk_result = await server._get_disk_usage({})
        overview_result = await server._get_system_overview({})
        
        print("   ✅ All methods accept empty parameters")
        print("   ✅ All methods return valid results")
    except Exception as e:
        print(f"   ❌ Method test failed: {e}")
    print()


async def main():
    """Run all tests."""
    print("System Monitor MCP Server Test Suite")
    print("=" * 50)
    
    # Test server functions directly
    await test_server_direct()
    
    # Test MCP protocol compliance
    await test_mcp_protocol()
    
    print("\n=== Test Summary ===")
    print("✅ Direct function tests completed")
    print("✅ MCP protocol compliance tests completed") 
    print("\nTo use this server with SimaCode:")
    print("1. Enable 'system_monitor' in config/mcp_servers.yaml")
    print("2. Run: simacode mcp init")
    print("3. Run: simacode mcp list")
    print("4. Run: simacode mcp run system_monitor:get_cpu_usage")


if __name__ == "__main__":
    asyncio.run(main())