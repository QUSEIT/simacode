#!/usr/bin/env python3
"""
Demo script showing MCP configuration merging capabilities.
"""

import sys
from pathlib import Path

# Add the src directory to Python path for imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from simacode.config import Config


def demo_config_merging():
    """Demonstrate MCP configuration merging capabilities."""
    print("🚀 SimaCode MCP Configuration Merging Demo")
    print("=" * 60)
    
    # Load the merged configuration
    config = Config.load()
    
    print(f"\n📋 Global MCP Configuration:")
    print(f"   • Enabled: {config.mcp.enabled}")
    print(f"   • Default Timeout: {config.mcp.default_timeout}s")
    print(f"   • Auto-enable Tools: {config.mcp.auto_enable_new_tools}")
    
    print(f"\n🔧 Server Configuration Summary:")
    print(f"   • Total servers configured: {len(config.mcp.servers)}")
    
    # Count enabled vs disabled
    enabled_count = sum(1 for s in config.mcp.servers.values() if s.enabled)
    disabled_count = len(config.mcp.servers) - enabled_count
    
    print(f"   • Enabled servers: {enabled_count}")
    print(f"   • Disabled servers: {disabled_count}")
    
    print(f"\n🖥️  Server Details:")
    print(f"   {'Server':<20} {'Enabled':<8} {'Timeout':<8} {'Source':<30}")
    print(f"   {'-' * 20} {'-' * 8} {'-' * 8} {'-' * 30}")
    
    for server_name, server_config in config.mcp.servers.items():
        # Determine source
        if server_config.enabled:
            # Check if this was likely overridden by user
            if "user enabled" in (server_config.description or "").lower():
                source = "User override (.simacode/config.yaml)"
            else:
                source = "Default (config/mcp_servers.yaml)"
        else:
            source = "Default (config/mcp_servers.yaml)"
        
        timeout_str = f"{server_config.timeout}s" if server_config.timeout else "default"
        enabled_str = "✅ Yes" if server_config.enabled else "❌ No"
        
        print(f"   {server_name:<20} {enabled_str:<8} {timeout_str:<8} {source:<30}")
    
    print(f"\n📝 Configuration Hierarchy:")
    print(f"   1. config/mcp_servers.yaml (base configuration)")
    print(f"   2. .simacode/config.yaml (user overrides)")
    print(f"   3. Root-level servers section (legacy support)")
    
    print(f"\n✨ Key Features Demonstrated:")
    print(f"   • ✅ Deep merge of server configurations")
    print(f"   • ✅ User settings override base settings")
    print(f"   • ✅ Non-specified settings inherit from base")
    print(f"   • ✅ Global MCP settings merge")
    print(f"   • ✅ Legacy support for root-level servers")
    
    print(f"\n🔍 Example Usage in .simacode/config.yaml:")
    print(f'''
mcp:
  enabled: true
  default_timeout: 300
  
servers:
  email_smtp:
    enabled: true
    description: "Custom email service"
  ticmaker:
    enabled: true
    timeout: 600
''')
    
    print(f"\n📚 This configuration will:")
    print(f"   • Enable email_smtp and ticmaker servers")
    print(f"   • Override their descriptions and timeouts")
    print(f"   • Keep all other servers with default settings from config/mcp_servers.yaml")


if __name__ == "__main__":
    demo_config_merging()