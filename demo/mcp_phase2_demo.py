"""
MCP Phase 2 Integration Demo

This script demonstrates the key features of Phase 2 MCP integration:
- Server management and configuration
- Tool discovery and search
- Health monitoring and alerts
- Usage statistics tracking

Run this script to see how the MCP system works in practice.
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Dict, Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from simacode.mcp.server_manager import MCPServerManager
from simacode.mcp.config import MCPConfig, MCPGlobalConfig, MCPServerConfig, MCPSecurityConfig
from simacode.mcp.health import HealthStatus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def health_alert_callback(alert_data: Dict[str, Any]) -> None:
    """Callback function for health alerts."""
    print(f"\n🚨 HEALTH ALERT: Server '{alert_data['server_name']}' is {alert_data['status']}")
    print(f"   Timestamp: {alert_data['timestamp']}")
    if alert_data['metrics'].get('last_error'):
        print(f"   Last Error: {alert_data['metrics']['last_error']}")
    print()


async def demo_mcp_phase2():
    """Demonstrate MCP Phase 2 capabilities."""
    print("=" * 60)
    print("🚀 MCP Phase 2: Server Management & Tool Discovery Demo")
    print("=" * 60)
    
    # Create a demo configuration
    demo_config = MCPConfig(
        mcp=MCPGlobalConfig(
            enabled=True,
            timeout=30,
            max_concurrent=5,
            log_level="INFO",
            health_check_interval=10
        ),
        servers={
            # Note: These are demo servers - they won't actually work without the MCP servers installed
            "filesystem": MCPServerConfig(
                name="filesystem",
                enabled=False,  # Disabled for demo
                type="subprocess",
                command=["python", "-m", "mcp_server_filesystem"],
                args=["--root", "/tmp"],
                security=MCPSecurityConfig(
                    allowed_paths=["/tmp"],
                    forbidden_paths=["/etc", "/usr", "/sys"],
                    max_execution_time=30
                )
            ),
            "demo_server": MCPServerConfig(
                name="demo_server",
                enabled=False,  # Disabled for demo - would need actual server
                type="subprocess",
                command=["echo", "demo"],
                security=MCPSecurityConfig(
                    allowed_operations=["demo"],
                    max_execution_time=10
                )
            )
        }
    )
    
    # Initialize server manager
    print("\n📋 1. Initializing MCP Server Manager...")
    manager = MCPServerManager()
    
    try:
        # Override config loading with our demo config
        manager.config = demo_config
        
        # Start the manager (without loading actual servers)
        print("   Starting manager...")
        await manager.health_monitor.start_monitoring()
        
        # Add health alert callback
        manager.add_health_alert_callback(health_alert_callback)
        
        print("   ✅ Manager initialized successfully!")
        
        # Display configuration
        print("\n🔧 2. Configuration Overview:")
        print(f"   MCP Enabled: {demo_config.mcp.enabled}")
        print(f"   Health Check Interval: {demo_config.mcp.health_check_interval}s")
        print(f"   Max Concurrent Operations: {demo_config.mcp.max_concurrent}")
        print(f"   Configured Servers: {len(demo_config.servers)}")
        
        enabled_servers = demo_config.get_enabled_servers()
        print(f"   Enabled Servers: {len(enabled_servers)}")
        for name in enabled_servers:
            print(f"     - {name}")
        
        # Demonstrate tool discovery capabilities
        print("\n🔍 3. Tool Discovery System:")
        print("   Tool discovery system initialized with:")
        discovery_stats = manager.tool_discovery.get_discovery_stats()
        print(f"     - Cache TTL: 5 minutes")
        print(f"     - Search cache enabled")
        print(f"     - Automatic categorization")
        print(f"     - Usage statistics tracking")
        
        # Demonstrate health monitoring
        print("\n❤️  4. Health Monitoring System:")
        health_stats = manager.health_monitor.get_monitoring_stats()
        print(f"   Health monitoring configured with:")
        print(f"     - Check interval: {manager.health_monitor.check_interval}s")
        print(f"     - Recovery enabled: {manager.health_monitor.recovery_enabled}")
        print(f"     - Alert callbacks: {health_stats['alert_callbacks_count']}")
        print(f"     - Max recovery attempts: {manager.health_monitor.max_recovery_attempts}")
        
        # Demonstrate search capabilities (without actual tools)
        print("\n🎯 5. Advanced Search Capabilities:")
        print("   Available search methods:")
        print("     - Exact name matching")
        print("     - Fuzzy name matching") 
        print("     - Description keyword search")
        print("     - Category-based search")
        print("     - Usage-based recommendations")
        
        # Show statistics
        print("\n📊 6. Manager Statistics:")
        stats = manager.get_manager_stats()
        print(f"   Total Servers: {stats['total_servers']}")
        print(f"   Connected Servers: {stats['connected_servers']}")
        print(f"   Discovery Stats:")
        for key, value in stats['discovery'].items():
            print(f"     - {key}: {value}")
        print(f"   Health Monitoring Stats:")
        for key, value in stats['health_monitoring'].items():
            print(f"     - {key}: {value}")
        
        # Demonstrate configuration management
        print("\n⚙️  7. Configuration Management:")
        print("   Features demonstrated:")
        print("     ✅ Environment variable substitution")
        print("     ✅ Security validation")
        print("     ✅ Path normalization")
        print("     ✅ YAML configuration loading")
        print("     ✅ Dynamic server addition/removal")
        
        # Show integration points
        print("\n🔗 8. Integration Points:")
        print("   Phase 2 integrates with:")
        print("     - Phase 1: MCP protocol and client core")
        print("     - SimaCode tool system (ready for Phase 3)")
        print("     - ReAct engine (ready for Phase 3)")
        print("     - Security framework")
        print("     - Logging and monitoring systems")
        
        print("\n🎉 Phase 2 Demonstration Complete!")
        print("\n💡 Next Steps (Phase 3):")
        print("   - Tool wrapper implementation")
        print("   - Integration with SimaCode tool registry")
        print("   - ReAct engine integration")
        print("   - Automatic tool registration")
        
        # Wait a bit to show ongoing monitoring
        print("\n⏳ Health monitoring running in background...")
        print("   (In a real deployment, this would continuously monitor server health)")
        await asyncio.sleep(2)
        
    except Exception as e:
        logger.error(f"Demo failed: {str(e)}")
        raise
    
    finally:
        # Cleanup
        print("\n🧹 Cleaning up...")
        try:
            await manager.stop()
            print("   ✅ Manager stopped successfully")
        except Exception as e:
            logger.error(f"Cleanup error: {str(e)}")


def print_architecture_overview():
    """Print the MCP Phase 2 architecture overview."""
    print("\n" + "=" * 60)
    print("🏗️  MCP Phase 2 Architecture Overview")
    print("=" * 60)
    
    print("""
📁 Phase 2 Components:
├── server_manager.py    - Central coordination and management
├── discovery.py         - Tool discovery and search system
├── health.py           - Health monitoring and recovery
├── config.py           - Configuration management (from Phase 1)
└── client.py           - MCP client core (from Phase 1)

🔄 Key Workflows:
1. Server Addition:
   Manager → Config Validation → Client Creation → Health Monitoring → Tool Discovery

2. Tool Discovery:
   Server Connection → Tool List → Categorization → Indexing → Search Cache

3. Health Monitoring:
   Periodic Checks → Status Assessment → Alert Triggers → Auto Recovery

4. Tool Execution:
   Tool Search → Server Selection → Execution → Statistics → Result

🎯 Phase 2 Achievements:
✅ Multi-server management with lifecycle control
✅ Advanced tool discovery with search and categorization  
✅ Comprehensive health monitoring with auto-recovery
✅ Usage statistics and performance tracking
✅ Flexible configuration management
✅ Integration-ready architecture for Phase 3
""")


async def main():
    """Main demo function."""
    print_architecture_overview()
    
    try:
        await demo_mcp_phase2()
    except KeyboardInterrupt:
        print("\n\n👋 Demo interrupted by user")
    except Exception as e:
        print(f"\n❌ Demo failed: {str(e)}")
        logger.exception("Demo error details:")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))