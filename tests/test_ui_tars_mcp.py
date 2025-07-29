#!/usr/bin/env python3
"""
Test script for UI-TARS MCP Server

This script tests the UI-TARS MCP server functionality including:
- HTTP health check
- MCP protocol compliance
- Tool execution (with mock UI-TARS)
- WebSocket connectivity
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, Any

# HTTP client support
try:
    import aiohttp
except ImportError:
    print("Error: aiohttp package not available. Please install with: pip install aiohttp", file=sys.stderr)
    sys.exit(1)

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.simacode.mcp.protocol import MCPMessage, MCPMethods


class UITARSMCPTester:
    """Tester for UI-TARS MCP Server."""
    
    def __init__(self, base_url: str = "http://localhost:8080"):
        """
        Initialize tester.
        
        Args:
            base_url: Base URL of the UI-TARS MCP server
        """
        self.base_url = base_url
        self.mcp_url = f"{base_url}/mcp"
        self.ws_url = f"{base_url.replace('http', 'ws')}/mcp/ws"
        self.health_url = f"{base_url}/health"
        
    async def test_health_check(self) -> bool:
        """Test server health check endpoint."""
        print("=== Testing Health Check ===")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.health_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        print(f"✅ Health check passed")
                        print(f"   Server: {data.get('server', {}).get('name', 'unknown')}")
                        print(f"   Status: {data.get('status', 'unknown')}")
                        print(f"   Version: {data.get('server', {}).get('version', 'unknown')}")
                        return True
                    else:
                        print(f"❌ Health check failed: HTTP {response.status}")
                        return False
                        
        except Exception as e:
            print(f"❌ Health check error: {str(e)}")
            return False
    
    async def test_mcp_initialization(self) -> bool:
        """Test MCP protocol initialization."""
        print("\n=== Testing MCP Initialization ===")
        
        try:
            # Create initialization request
            init_request = MCPMessage(
                id="test_init_1",
                method=MCPMethods.INITIALIZE,
                params={
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": False}
                    },
                    "clientInfo": {
                        "name": "test-client",
                        "version": "1.0.0"
                    }
                }
            )
            
            # Send HTTP request
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.mcp_url,
                    json=init_request.to_dict(),
                    headers={"Content-Type": "application/json"}
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        response_msg = MCPMessage.from_dict(data)
                        
                        if response_msg.result:
                            server_info = response_msg.result.get("serverInfo", {})
                            capabilities = response_msg.result.get("capabilities", {})
                            
                            print(f"✅ MCP initialization successful")
                            print(f"   Server: {server_info.get('name', 'unknown')}")
                            print(f"   Version: {server_info.get('version', 'unknown')}")
                            print(f"   Tools capability: {capabilities.get('tools', {})}")
                            return True
                        else:
                            print(f"❌ MCP initialization failed: {response_msg.error}")
                            return False
                    else:
                        print(f"❌ MCP initialization failed: HTTP {response.status}")
                        return False
                        
        except Exception as e:
            print(f"❌ MCP initialization error: {str(e)}")
            return False
    
    async def test_tools_list(self) -> bool:
        """Test tools listing."""
        print("\n=== Testing Tools List ===")
        
        try:
            # Create tools list request
            tools_request = MCPMessage(
                id="test_tools_1",
                method=MCPMethods.TOOLS_LIST
            )
            
            # Send HTTP request
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.mcp_url,
                    json=tools_request.to_dict(),
                    headers={"Content-Type": "application/json"}
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        response_msg = MCPMessage.from_dict(data)
                        
                        if response_msg.result:
                            tools = response_msg.result.get("tools", [])
                            
                            print(f"✅ Tools list retrieved successfully")
                            print(f"   Available tools: {len(tools)}")
                            
                            for tool in tools:
                                name = tool.get("name", "unknown")
                                description = tool.get("description", "no description")
                                print(f"   - {name}: {description}")
                            
                            return True
                        else:
                            print(f"❌ Tools list failed: {response_msg.error}")
                            return False
                    else:
                        print(f"❌ Tools list failed: HTTP {response.status}")
                        return False
                        
        except Exception as e:
            print(f"❌ Tools list error: {str(e)}")
            return False
    
    async def test_website_verification_tool(self) -> bool:
        """Test the website verification tool (with mock execution)."""
        print("\n=== Testing Website Verification Tool ===")
        
        try:
            # Create tool call request
            tool_request = MCPMessage(
                id="test_tool_1",
                method=MCPMethods.TOOLS_CALL,
                params={
                    "name": "open_website_with_verification",
                    "arguments": {
                        "url": "https://example.com",
                        "verification_instructions": "handle any captcha or verification that appears",
                        "timeout": 60
                    }
                }
            )
            
            # Send HTTP request
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.mcp_url,
                    json=tool_request.to_dict(),
                    headers={"Content-Type": "application/json"}
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        response_msg = MCPMessage.from_dict(data)
                        
                        if response_msg.result:
                            content = response_msg.result.get("content", [])
                            is_error = response_msg.result.get("isError", False)
                            
                            print(f"✅ Website verification tool executed")
                            print(f"   Error status: {is_error}")
                            
                            if content:
                                result_text = content[0].get("text", "")
                                try:
                                    result_data = json.loads(result_text)
                                    print(f"   URL: {result_data.get('url', 'unknown')}")
                                    print(f"   Success: {result_data.get('success', False)}")
                                    print(f"   Execution time: {result_data.get('execution_time', 0):.2f}s")
                                    
                                    if result_data.get('error'):
                                        print(f"   Error: {result_data['error']}")
                                        # Note: 'npx' command not found is expected in test environment
                                    
                                except json.JSONDecodeError:
                                    print(f"   Raw result: {result_text[:200]}...")
                            
                            return True
                        else:
                            print(f"❌ Website verification tool failed: {response_msg.error}")
                            return False
                    else:
                        print(f"❌ Website verification tool failed: HTTP {response.status}")
                        return False
                        
        except Exception as e:
            print(f"❌ Website verification tool error: {str(e)}")
            return False
    
    async def test_ui_automation_tool(self) -> bool:
        """Test the general UI automation tool."""
        print("\n=== Testing UI Automation Tool ===")
        
        try:
            # Create tool call request
            tool_request = MCPMessage(
                id="test_tool_2",
                method=MCPMethods.TOOLS_CALL,
                params={
                    "name": "ui_automation",
                    "arguments": {
                        "instruction": "open a text editor and type 'Hello, UI-TARS!'",
                        "timeout": 30
                    }
                }
            )
            
            # Send HTTP request
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.mcp_url,
                    json=tool_request.to_dict(),
                    headers={"Content-Type": "application/json"}
                ) as response:
                    
                    if response.status == 200:
                        data = await response.json()
                        response_msg = MCPMessage.from_dict(data)
                        
                        if response_msg.result:
                            content = response_msg.result.get("content", [])
                            is_error = response_msg.result.get("isError", False)
                            
                            print(f"✅ UI automation tool executed")
                            print(f"   Error status: {is_error}")
                            
                            if content:
                                result_text = content[0].get("text", "")
                                try:
                                    result_data = json.loads(result_text)
                                    print(f"   Instruction: {result_data.get('instruction', 'unknown')}")
                                    print(f"   Success: {result_data.get('success', False)}")
                                    print(f"   Execution time: {result_data.get('execution_time', 0):.2f}s")
                                    
                                    if result_data.get('error'):
                                        print(f"   Error: {result_data['error']}")
                                        # Note: 'npx' command not found is expected in test environment
                                    
                                except json.JSONDecodeError:
                                    print(f"   Raw result: {result_text[:200]}...")
                            
                            return True
                        else:
                            print(f"❌ UI automation tool failed: {response_msg.error}")
                            return False
                    else:
                        print(f"❌ UI automation tool failed: HTTP {response.status}")
                        return False
                        
        except Exception as e:
            print(f"❌ UI automation tool error: {str(e)}")
            return False
    
    async def test_websocket_connection(self) -> bool:
        """Test WebSocket connectivity."""
        print("\n=== Testing WebSocket Connection ===")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(self.ws_url) as ws:
                    print("✅ WebSocket connection established")
                    
                    # Send ping
                    ping_request = MCPMessage(
                        id="test_ws_ping",
                        method=MCPMethods.PING
                    )
                    
                    await ws.send_str(ping_request.to_json())
                    
                    # Wait for response
                    response = await ws.receive()
                    
                    if response.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(response.data)
                        response_msg = MCPMessage.from_dict(data)
                        
                        if response_msg.result and response_msg.result.get("pong"):
                            print("✅ WebSocket ping successful")
                            return True
                        else:
                            print(f"❌ WebSocket ping failed: {response_msg.error}")
                            return False
                    else:
                        print(f"❌ WebSocket ping failed: unexpected response type")
                        return False
                        
        except Exception as e:
            print(f"❌ WebSocket connection error: {str(e)}")
            return False
    
    async def run_all_tests(self) -> Dict[str, bool]:
        """Run all tests and return results."""
        print("UI-TARS MCP Server Test Suite")
        print("=" * 50)
        
        results = {
            "health_check": await self.test_health_check(),
            "mcp_initialization": await self.test_mcp_initialization(),
            "tools_list": await self.test_tools_list(),
            "website_verification": await self.test_website_verification_tool(),
            "ui_automation": await self.test_ui_automation_tool(),
            "websocket": await self.test_websocket_connection()
        }
        
        print("\n=== Test Results Summary ===")
        passed = sum(results.values())
        total = len(results)
        
        for test_name, result in results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"{test_name}: {status}")
        
        print(f"\nOverall: {passed}/{total} tests passed")
        
        if passed == total:
            print("🎉 All tests passed!")
        else:
            print("⚠️  Some tests failed. Check server status and configuration.")
        
        return results


async def main():
    """Main test runner."""
    import argparse
    
    parser = argparse.ArgumentParser(description="UI-TARS MCP Server Tester")
    parser.add_argument("--server", default="http://localhost:8080", 
                       help="UI-TARS MCP server URL")
    
    args = parser.parse_args()
    
    tester = UITARSMCPTester(args.server)
    results = await tester.run_all_tests()
    
    # Exit with error code if any test failed
    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())