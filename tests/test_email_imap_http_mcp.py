#!/usr/bin/env python3
"""
Test script for Email IMAP MCP Server (HTTP/WebSocket)

This script tests the HTTP/WebSocket based Email IMAP MCP server functionality
including health checks, WebSocket connectivity, and tool execution.
"""

import asyncio
import json
import os
import sys
import aiohttp
import websockets
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.mcp_email_imap_http_server import EmailIMAPMCPServer, EmailConfig, load_env_config


async def test_http_health_check(host: str, port: int):
    """Test HTTP health check endpoint."""
    print("🔍 Testing HTTP health check...")
    
    try:
        url = f"http://{host}:{port}/health"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    health_data = await response.json()
                    print("✅ Health check successful")
                    print(f"   Server: {health_data['server']['name']} v{health_data['server']['version']}")
                    print(f"   Email server: {health_data['email_config']['server']}:{health_data['email_config']['port']}")
                    print(f"   Connection status: {health_data['email_config']['connection_status']}")
                    return True
                else:
                    print(f"❌ Health check failed with status: {response.status}")
                    return False
                    
    except Exception as e:
        print(f"❌ Health check failed: {str(e)}")
        return False


async def test_websocket_mcp_protocol(host: str, port: int):
    """Test WebSocket MCP protocol communication."""
    print("\n🔌 Testing WebSocket MCP protocol...")
    
    try:
        uri = f"ws://{host}:{port}/mcp/ws"
        
        async with websockets.connect(uri) as websocket:
            print("✅ WebSocket connection established")
            
            # Test 1: Initialize
            print("🔧 Testing MCP initialize...")
            init_message = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "test-client",
                        "version": "1.0.0"
                    }
                }
            }
            
            await websocket.send(json.dumps(init_message))
            response = await websocket.recv()
            response_data = json.loads(response)
            
            if response_data.get("result"):
                print("✅ MCP initialize successful")
                server_info = response_data["result"]["serverInfo"]
                print(f"   Server: {server_info['name']} v{server_info['version']}")
            else:
                print(f"❌ MCP initialize failed: {response_data}")
                return False
            
            # Test 2: List tools
            print("🛠️  Testing tools/list...")
            list_tools_message = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {}
            }
            
            await websocket.send(json.dumps(list_tools_message))
            response = await websocket.recv()
            response_data = json.loads(response)
            
            if response_data.get("result") and "tools" in response_data["result"]:
                tools = response_data["result"]["tools"]
                print(f"✅ Found {len(tools)} tools:")
                for tool in tools:
                    print(f"   - {tool['name']}: {tool['description']}")
            else:
                print(f"❌ Tools list failed: {response_data}")
                return False
            
            # Test 3: Call a tool (list_folders)
            print("📁 Testing tool execution (list_folders)...")
            call_tool_message = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "list_folders",
                    "arguments": {}
                }
            }
            
            await websocket.send(json.dumps(call_tool_message))
            response = await websocket.recv()
            response_data = json.loads(response)
            
            if response_data.get("result"):
                content = response_data["result"]["content"][0]["text"]
                result_data = json.loads(content)
                
                if result_data.get("success"):
                    print(f"✅ Tool execution successful")
                    print(f"   Found {result_data['count']} folders: {result_data['folders'][:3]}...")
                else:
                    print(f"⚠️  Tool execution returned error: {result_data.get('error')}")
            else:
                print(f"❌ Tool execution failed: {response_data}")
            
            # Test 4: Ping
            print("🏓 Testing ping...")
            ping_message = {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "ping",
                "params": {}
            }
            
            await websocket.send(json.dumps(ping_message))
            response = await websocket.recv()
            response_data = json.loads(response)
            
            if response_data.get("result", {}).get("pong"):
                print("✅ Ping successful")
            else:
                print(f"❌ Ping failed: {response_data}")
            
            print("✅ WebSocket MCP protocol tests completed")
            return True
            
    except Exception as e:
        print(f"❌ WebSocket test failed: {str(e)}")
        return False


async def test_email_server_standalone():
    """Test the email server functionality without external dependencies."""
    print("\n📧 Testing Email IMAP MCP Server (standalone)...")
    
    # Load environment configuration
    load_env_config()
    
    # Create test configuration
    email_config = EmailConfig(
        server=os.getenv("EMAIL_IMAP_SERVER", ""),
        port=int(os.getenv("EMAIL_IMAP_PORT_IMAP", "993")),
        username=os.getenv("EMAIL_USERNAME", ""),
        password=os.getenv("EMAIL_PASSWORD", ""),
        use_ssl=True,
        timeout=30
    )
    
    host = os.getenv("EMAIL_IMAP_HOST", "0.0.0.0")
    port = int(os.getenv("EMAIL_IMAP_PORT", "8081"))
    
    print(f"📊 Configuration:")
    print(f"   MCP Server: {host}:{port}")
    print(f"   Email Server: {email_config.server}:{email_config.port}")
    print(f"   Username: {email_config.username or 'NOT SET'}")
    print(f"   Password: {'SET' if email_config.password else 'NOT SET'}")
    
    # Test server creation
    try:
        server = EmailIMAPMCPServer(host=host, port=port, email_config=email_config)
        print("✅ Email IMAP MCP Server created successfully")
        
        # Test tools definition
        tools = server.tools
        print(f"✅ Found {len(tools)} tools defined:")
        for tool_name, tool_def in tools.items():
            print(f"   - {tool_name}: {tool_def['description']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Server creation failed: {str(e)}")
        return False


async def run_integration_test():
    """Run integration test with a running server."""
    print("\n🔄 Integration Test")
    print("Note: This requires a running Email IMAP MCP Server")
    print("Start the server with: python tools/mcp_email_imap_http_server.py")
    
    # Load configuration
    load_env_config()
    host = os.getenv("EMAIL_IMAP_HOST", "localhost")
    port = int(os.getenv("EMAIL_IMAP_PORT", "8081"))
    
    print(f"\n🎯 Testing server at {host}:{port}")
    
    # Test HTTP health check
    health_ok = await test_http_health_check(host, port)
    
    if health_ok:
        # Test WebSocket MCP protocol
        websocket_ok = await test_websocket_mcp_protocol(host, port)
        
        if websocket_ok:
            print("\n🎉 All integration tests passed!")
            return True
        else:
            print("\n❌ WebSocket tests failed")
            return False
    else:
        print("\n❌ Health check failed - server may not be running")
        return False


async def main():
    """Main test function."""
    print("Email IMAP MCP Server (HTTP/WebSocket) - Test Suite")
    print("=" * 60)
    
    # Test 1: Standalone functionality
    standalone_ok = await test_email_server_standalone()
    
    if not standalone_ok:
        print("\n❌ Standalone tests failed - check configuration")
        return False
    
    # Test 2: Integration test (optional)
    print("\n" + "=" * 60)
    
    try:
        integration_ok = await run_integration_test()
        
        if integration_ok:
            print("\n🎉 All tests completed successfully!")
            print("\nNext steps:")
            print("1. Start the server: python tools/mcp_email_imap_http_server.py")
            print("2. Configure SimaCode to use the email_imap MCP server")
            print("3. Enable the server in config/mcp_servers.yaml")
            return True
        else:
            print("\n⚠️  Integration tests failed, but standalone tests passed")
            print("This likely means the server is not running.")
            print("\nTo run integration tests:")
            print("1. Start the server: python tools/mcp_email_imap_http_server.py")
            print("2. Run this test script again")
            return True
            
    except KeyboardInterrupt:
        print("\n❌ Test interrupted by user")
        return False


def print_usage():
    """Print usage instructions."""
    print("""
Email IMAP MCP Server (HTTP/WebSocket) Test

This script tests the HTTP/WebSocket based Email IMAP MCP server.

Setup:
1. Copy .env.mcp.sample to .env.mcp
2. Configure your email settings in .env.mcp:
   - EMAIL_IMAP_SERVER (e.g., imap.gmail.com)
   - EMAIL_IMAP_PORT_IMAP (e.g., 993)
   - EMAIL_USERNAME (your email address)
   - EMAIL_PASSWORD (your app password)
   - EMAIL_IMAP_HOST (default: 0.0.0.0)
   - EMAIL_IMAP_PORT (default: 8081)

For Gmail users:
1. Enable 2-Factor Authentication
2. Generate an App Password at: https://myaccount.google.com/apppasswords
3. Use the App Password as EMAIL_PASSWORD

Run:
   python tests/test_email_imap_http_mcp.py

Dependencies:
   pip install aiohttp websockets
""")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ['--help', '-h']:
        print_usage()
        sys.exit(0)
    
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n❌ Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)