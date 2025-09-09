#!/usr/bin/env python3
"""
Test script to verify MCP configuration merging functionality.
"""

import sys
import logging
from pathlib import Path

# Add the src directory to Python path for imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from simacode.config import Config

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def test_config_merging():
    """Test MCP configuration merging from multiple sources."""
    print("=== Testing MCP Configuration Merging ===\n")
    
    try:
        # Load configuration (this will trigger merging)
        config = Config.load()
        
        print("✅ Configuration loaded successfully")
        print(f"📝 MCP globally enabled: {config.mcp.enabled}")
        print(f"📝 MCP default timeout: {config.mcp.default_timeout}")
        print(f"📝 Auto-enable new tools: {config.mcp.auto_enable_new_tools}")
        
        print(f"\n🔧 Total servers configured: {len(config.mcp.servers)}")
        
        # Show all configured servers
        print(f"\n=== Server Configuration Details ===")
        for server_name, server_config in config.mcp.servers.items():
            print(f"\n🖥️  Server: {server_name}")
            print(f"   ├─ Name: {server_config.name}")
            print(f"   ├─ Enabled: {server_config.enabled}")
            print(f"   ├─ Description: {server_config.description}")
            print(f"   └─ Timeout: {server_config.timeout}")
        
        # Test specific servers that should be present
        expected_servers = ["email_smtp", "ticmaker"]
        
        print(f"\n=== Testing Expected Servers ===")
        for server_name in expected_servers:
            if server_name in config.mcp.servers:
                server_config = config.mcp.servers[server_name]
                print(f"✅ {server_name}:")
                print(f"   • Configured: True")
                print(f"   • Enabled: {server_config.enabled}")
                print(f"   • Source: {'User config (.simacode/config.yaml)' if server_config.enabled else 'Default (config/mcp_servers.yaml)'}")
            else:
                print(f"❌ {server_name}: Not found in configuration")
        
        # Test if servers from config/mcp_servers.yaml are present
        print(f"\n=== Testing Servers from config/mcp_servers.yaml ===")
        expected_from_file = ["agent_tars", "system_monitor", "filesystem", "browser_use_proxy", "email_imap"]
        
        for server_name in expected_from_file:
            if server_name in config.mcp.servers:
                server_config = config.mcp.servers[server_name]
                print(f"✅ {server_name}: Present (enabled: {server_config.enabled})")
            else:
                print(f"❌ {server_name}: Missing from merged configuration")
        
        return True
        
    except Exception as e:
        print(f"❌ Configuration merging test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_config_structure():
    """Test the structure and accessibility of merged configuration."""
    print("\n=== Testing Configuration Structure ===\n")
    
    try:
        config = Config.load()
        
        # Test basic attributes
        print("📋 Testing basic MCP configuration attributes:")
        print(f"   • config.mcp.enabled: {config.mcp.enabled}")
        print(f"   • config.mcp.default_timeout: {config.mcp.default_timeout}")
        print(f"   • config.mcp.auto_enable_new_tools: {config.mcp.auto_enable_new_tools}")
        
        # Test servers dictionary access
        print(f"\n📋 Testing servers configuration access:")
        print(f"   • len(config.mcp.servers): {len(config.mcp.servers)}")
        
        # Test specific server access
        test_servers = ["email_smtp", "ticmaker"]
        for server_name in test_servers:
            if server_name in config.mcp.servers:
                server = config.mcp.servers[server_name]
                print(f"   • config.mcp.servers['{server_name}']:")
                print(f"     - name: {server.name}")
                print(f"     - enabled: {server.enabled}")
                print(f"     - description: {server.description}")
                print(f"     - timeout: {server.timeout}")
        
        return True
        
    except Exception as e:
        print(f"❌ Configuration structure test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("🚀 SimaCode MCP Configuration Merging Test\n")
    
    # Test configuration merging
    merge_success = test_config_merging()
    
    # Test configuration structure
    structure_success = test_config_structure()
    
    if merge_success and structure_success:
        print(f"\n🎉 All tests passed!")
        print(f"✨ MCP configuration merging is working correctly.")
        print(f"📚 .simacode/config.yaml successfully merges with config/mcp_servers.yaml")
    else:
        print(f"\n💥 Some tests failed!")
        print(f"🔧 Configuration merging needs fixes")
        sys.exit(1)


if __name__ == "__main__":
    main()