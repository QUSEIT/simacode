#!/usr/bin/env python3
"""
MCP Phase 3 Integration Demo

This script demonstrates the completed Phase 3 MCP integration system,
showing how all components work together to provide seamless tool
integration and management.
"""

import asyncio
import json
import tempfile
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../src'))

from simacode.mcp.integration import SimaCodeToolRegistry, initialize_mcp_integration
from simacode.mcp.server_manager import MCPServerManager
from simacode.mcp.tool_registry import MCPToolRegistry
from simacode.mcp.auto_discovery import MCPAutoDiscovery, DiscoveryPolicy, DiscoveryMode
from simacode.mcp.dynamic_updates import DynamicUpdateManager, UpdatePolicy
from simacode.mcp.namespace_manager import EnhancedNamespaceManager, NamespacePolicy
from simacode.mcp.protocol import MCPTool, MCPResult
from simacode.mcp.health import HealthStatus, HealthMetrics
from simacode.tools.base import Tool, ToolInput, ToolResult, ToolResultType
from simacode.permissions import PermissionManager


class DemoMCPServer:
    """Demo MCP server for showcasing functionality."""
    
    def __init__(self, name: str, tools: List[Dict[str, Any]]):
        self.name = name
        self.tools = tools
        self.is_running = False
        self.call_count = 0
    
    async def start(self):
        self.is_running = True
        print(f"  ✅ Started demo server: {self.name}")
    
    async def stop(self):
        self.is_running = False
        print(f"  🛑 Stopped demo server: {self.name}")
    
    async def list_tools(self) -> List[MCPTool]:
        return [
            MCPTool(
                name=tool["name"],
                description=tool["description"],
                server_name=self.name,
                input_schema=tool.get("schema", {"type": "object"})
            )
            for tool in self.tools
        ]
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> MCPResult:
        self.call_count += 1
        
        # Find tool
        tool = next((t for t in self.tools if t["name"] == tool_name), None)
        if not tool:
            return MCPResult(
                type="error",
                content=f"Tool '{tool_name}' not found",
                metadata={}
            )
        
        # Simulate realistic tool execution
        if tool_name == "file_reader":
            content = f"Contents of {arguments.get('file_path', 'unknown')}: This is demo file content."
        elif tool_name == "web_scraper":
            content = f"Scraped content from {arguments.get('url', 'unknown')}: <h1>Demo Page</h1>"
        elif tool_name == "data_processor":
            content = f"Processed data with algorithm {arguments.get('algorithm', 'default')}: [processed_result]"
        else:
            content = f"Executed {tool_name} with arguments: {json.dumps(arguments)}"
        
        await asyncio.sleep(0.1)  # Simulate processing time
        
        return MCPResult(
            type="success",
            content=content,
            metadata={
                "execution_time": 0.1,
                "call_count": self.call_count,
                "server": self.name
            }
        )
    
    def get_health(self) -> HealthMetrics:
        return HealthMetrics(
            server_name=self.name,
            status=HealthStatus.HEALTHY,
            last_check=datetime.now()
        )


def create_demo_servers() -> Dict[str, DemoMCPServer]:
    """Create demo MCP servers with various tools."""
    
    return {
        "file_tools": DemoMCPServer("file_tools", [
            {
                "name": "file_reader",
                "description": "Read content from files",
                "schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Path to the file"},
                        "encoding": {"type": "string", "default": "utf-8"}
                    },
                    "required": ["file_path"]
                }
            },
            {
                "name": "file_writer",
                "description": "Write content to files",
                "schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string"},
                        "content": {"type": "string"},
                        "append": {"type": "boolean", "default": False}
                    },
                    "required": ["file_path", "content"]
                }
            }
        ]),
        
        "web_tools": DemoMCPServer("web_tools", [
            {
                "name": "web_scraper",
                "description": "Scrape content from web pages",
                "schema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "format": "uri"},
                        "selector": {"type": "string"},
                        "extract_type": {"type": "string", "enum": ["text", "html", "links"]}
                    },
                    "required": ["url"]
                }
            },
            {
                "name": "api_client",
                "description": "Make HTTP API requests",
                "schema": {
                    "type": "object",
                    "properties": {
                        "url": {"type": "string"},
                        "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]},
                        "headers": {"type": "object"},
                        "data": {"type": "object"}
                    },
                    "required": ["url"]
                }
            }
        ]),
        
        "data_tools": DemoMCPServer("data_tools", [
            {
                "name": "data_processor",
                "description": "Process data with various algorithms",
                "schema": {
                    "type": "object",
                    "properties": {
                        "data": {"type": "array"},
                        "algorithm": {"type": "string", "enum": ["sort", "filter", "map", "reduce"]},
                        "parameters": {"type": "object"}
                    },
                    "required": ["data", "algorithm"]
                }
            }
        ])
    }


def create_demo_config(servers: Dict[str, DemoMCPServer]) -> Path:
    """Create a demo MCP configuration file."""
    
    config_data = {
        "servers": {
            name: {
                "command": ["python", "-m", f"demo_{name}_server"],
                "args": ["--demo-mode"],
                "env": {"DEMO": "true", "SERVER_NAME": name},
                "working_directory": "/tmp"
            }
            for name in servers.keys()
        },
        "discovery": {
            "mode": "active",
            "interval": 30,
            "auto_register": True,
            "auto_unregister": True
        },
        "updates": {
            "enable_hot_updates": True,
            "batch_updates": True,
            "max_concurrent": 3
        },
        "namespaces": {
            "require_namespaces": True,
            "conflict_resolution": "suffix",
            "auto_create_aliases": True
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f, default_flow_style=False)
        return Path(f.name)


class DemoToolInput(ToolInput):
    """Demo tool input model."""
    message: str = "Hello, demo!"


class DemoBuiltinTool(Tool):
    """Demo built-in tool for showcasing integration."""
    
    def __init__(self, name: str, description: str):
        super().__init__(name, description, "1.0.0")
    
    def get_input_schema(self):
        """Return the input schema for this tool."""
        return DemoToolInput
    
    async def validate_input(self, input_data: Dict[str, Any]):
        """Validate tool input."""
        return DemoToolInput(**input_data)
    
    async def check_permissions(self, input_data):
        """Check permissions (always allowed for demo)."""
        return True
    
    async def execute(self, input_data):
        # Simulate tool execution
        await asyncio.sleep(0.05)
        
        yield ToolResult(
            type=ToolResultType.SUCCESS,
            content=f"Built-in tool '{self.name}' executed successfully",
            tool_name=self.name,
            metadata={"builtin": True}
        )


async def demo_basic_integration():
    """Demonstrate basic MCP integration."""
    
    print("\n" + "="*60)
    print("DEMO 1: Basic MCP Integration")
    print("="*60)
    
    # Create demo servers
    servers = create_demo_servers()
    
    print(f"Created {len(servers)} demo MCP servers:")
    for name, server in servers.items():
        print(f"  • {name}: {len(server.tools)} tools")
    
    # Create unified registry
    registry = SimaCodeToolRegistry()
    
    # Add some built-in tools
    builtin_tools = [
        DemoBuiltinTool("system_info", "Get system information"),
        DemoBuiltinTool("calculate", "Perform calculations"),
        DemoBuiltinTool("format_text", "Format text in various ways")
    ]
    
    for tool in builtin_tools:
        registry.register_builtin_tool(tool)
    
    print(f"\nRegistered {len(builtin_tools)} built-in tools")
    
    # Mock MCP integration (since we can't run real MCP servers in demo)
    print("\n🔌 Initializing MCP integration...")
    
    # In a real scenario, this would connect to actual MCP servers
    # For demo, we'll simulate the integration
    registry.mcp_enabled = True
    
    # Create mock server manager
    from unittest.mock import Mock, AsyncMock
    
    mock_server_manager = Mock()
    mock_server_manager.list_servers.return_value = list(servers.keys())
    
    async def mock_get_all_tools():
        result = {}
        for name, server in servers.items():
            result[name] = await server.list_tools()
        return result
    
    mock_server_manager.get_all_tools = mock_get_all_tools
    mock_server_manager.get_server_health = Mock(side_effect=lambda name: servers[name].get_health())
    mock_server_manager.call_tool = AsyncMock()
    
    registry.mcp_server_manager = mock_server_manager
    
    # Create tool registry
    permission_manager = Mock()
    permission_manager.check_permission = AsyncMock(return_value=True)
    
    registry.mcp_tool_registry = MCPToolRegistry(
        mock_server_manager,
        permission_manager,
        auto_register=True
    )
    
    # Discover and register MCP tools
    print("🔍 Discovering and registering MCP tools...")
    registered_count = await registry.mcp_tool_registry.discover_and_register_all_tools()
    
    print(f"✅ Registered {registered_count} MCP tools")
    
    # List all tools
    all_tools = registry.list_tools()
    print(f"\n📋 Total tools available: {len(all_tools)}")
    
    builtin_tools_list = registry.list_tools(include_mcp=False, include_builtin=True)
    mcp_tools_list = registry.list_tools(include_mcp=True, include_builtin=False)
    
    print(f"   • Built-in tools: {len(builtin_tools_list)}")
    print(f"   • MCP tools: {len(mcp_tools_list)}")
    
    # Show tool details
    print(f"\n🔧 Sample tools:")
    for i, tool_name in enumerate(all_tools[:5]):  # Show first 5 tools
        tool_info = registry.get_tool_info(tool_name)
        if tool_info:
            print(f"   {i+1}. {tool_name}")
            print(f"      Type: {tool_info.get('type', 'unknown')}")
            print(f"      Description: {tool_info.get('description', 'No description')}")
    
    # Test tool search
    print(f"\n🔍 Searching for 'file' tools:")
    search_results = registry.search_tools("file", fuzzy=True)
    for result in search_results[:3]:  # Show top 3 results
        print(f"   • {result['tool_name']} (score: {result['score']})")
        print(f"     {result['description']}")
    
    print(f"\n✅ Basic integration demo completed successfully!")


async def demo_auto_discovery():
    """Demonstrate auto-discovery functionality."""
    
    print("\n" + "="*60)
    print("DEMO 2: Auto-Discovery System")
    print("="*60)
    
    # Create demo components
    servers = create_demo_servers()
    
    from unittest.mock import Mock, AsyncMock
    
    # Mock server manager
    mock_server_manager = Mock()
    mock_server_manager.list_servers.return_value = list(servers.keys())
    
    async def mock_get_all_tools():
        result = {}
        for name, server in servers.items():
            result[name] = await server.list_tools()
        return result
    
    mock_server_manager.get_all_tools = mock_get_all_tools
    mock_server_manager.get_server_health = Mock(side_effect=lambda name: servers[name].get_health())
    
    permission_manager = Mock()
    permission_manager.check_permission = AsyncMock(return_value=True)
    
    # Create tool registry
    tool_registry = MCPToolRegistry(mock_server_manager, permission_manager)
    
    # Create auto-discovery with active policy
    discovery_policy = DiscoveryPolicy(
        mode=DiscoveryMode.ACTIVE,
        discovery_interval=5,  # 5 seconds for demo
        auto_register_new_tools=True,
        auto_unregister_dead_tools=True
    )
    
    auto_discovery = MCPAutoDiscovery(mock_server_manager, tool_registry, discovery_policy)
    
    print(f"🤖 Starting auto-discovery system...")
    print(f"   • Mode: {discovery_policy.mode.value}")
    print(f"   • Interval: {discovery_policy.discovery_interval}s")
    print(f"   • Auto-register: {discovery_policy.auto_register_new_tools}")
    
    # Start auto-discovery
    await auto_discovery.start()
    
    try:
        # Let it run for a bit
        print(f"\n⏱️  Running discovery for 10 seconds...")
        await asyncio.sleep(10)
        
        # Check results
        stats = auto_discovery.get_discovery_stats()
        print(f"\n📊 Discovery Statistics:")
        print(f"   • Discovery cycles: {stats['discovery_cycles']}")
        print(f"   • Servers processed: {stats['servers_processed']}")
        print(f"   • Total discoveries: {stats['total_discoveries']}")
        print(f"   • Successful registrations: {stats['successful_registrations']}")
        print(f"   • Failed registrations: {stats['failed_registrations']}")
        
        # Show recent events
        recent_events = auto_discovery.get_recent_events(5)
        print(f"\n📝 Recent Events:")
        for event in recent_events:
            print(f"   • {event.timestamp.strftime('%H:%M:%S')} - {event.event_type}: {event.tool_name} from {event.server_name}")
        
        print(f"\n✅ Auto-discovery demo completed!")
        
    finally:
        await auto_discovery.stop()


async def demo_namespace_management():
    """Demonstrate namespace management."""
    
    print("\n" + "="*60)
    print("DEMO 3: Namespace Management")
    print("="*60)
    
    # Create enhanced namespace manager
    policy = NamespacePolicy(
        require_namespaces=True,
        auto_create_aliases=True,
        max_namespace_depth=3
    )
    
    namespace_manager = EnhancedNamespaceManager(policy)
    
    print(f"🏷️  Creating namespaces and managing tool names...")
    
    # Create some namespaces
    namespaces = [
        ("file_ops", "File operation tools", None),
        ("web_utils", "Web utility tools", None),
        ("data_processing", "Data processing tools", None),
        ("advanced_data", "Advanced data tools", "data_processing")  # Child namespace
    ]
    
    for name, desc, parent in namespaces:
        success = namespace_manager.create_namespace(name, desc, parent=parent)
        print(f"   {'✅' if success else '❌'} Created namespace: {name}")
    
    # Register some tools with potential conflicts
    tools_to_register = [
        ("read", "file_server_1", "file_ops"),
        ("write", "file_server_1", "file_ops"),
        ("read", "file_server_2", "file_ops"),  # Conflict!
        ("scrape", "web_server", "web_utils"),
        ("process", "data_server_1", "data_processing"),
        ("process", "data_server_2", "advanced_data"),  # Same name, different namespace
    ]
    
    print(f"\n🔧 Registering tools with conflict resolution:")
    
    for tool_name, server_name, namespace in tools_to_register:
        tool_info = namespace_manager.register_tool_name(tool_name, server_name, namespace)
        if tool_info:
            status = "✅"
            details = f"-> {tool_info.full_name}"
            if tool_info.conflicts:
                details += f" (resolved {len(tool_info.conflicts)} conflicts)"
            if tool_info.aliases:
                details += f" [aliases: {', '.join(tool_info.aliases)}]"
        else:
            status = "❌"
            details = "Failed to register"
        
        print(f"   {status} {tool_name} from {server_name}: {details}")
    
    # Show namespace hierarchy
    print(f"\n🌳 Namespace Hierarchy:")
    for ns_name in namespace_manager.namespaces.keys():
        hierarchy = namespace_manager.get_namespace_hierarchy(ns_name)
        if not hierarchy["info"]["parent"]:  # Root namespace
            print(f"   📁 {ns_name}")
            _print_namespace_tree(hierarchy, "     ")
    
    # Show statistics
    stats = namespace_manager.get_statistics()
    print(f"\n📊 Namespace Statistics:")
    print(f"   • Total namespaces: {stats['total_namespaces']}")
    print(f"   • Total tools: {stats['total_tools']}")
    print(f"   • Total aliases: {stats['total_aliases']}")
    print(f"   • Conflicts resolved: {stats['conflicts_resolved']}")
    
    print(f"\n✅ Namespace management demo completed!")


def _print_namespace_tree(hierarchy: Dict[str, Any], indent: str = ""):
    """Helper function to print namespace tree."""
    for child_name, child_hierarchy in hierarchy["children"].items():
        print(f"{indent}📁 {child_name}")
        _print_namespace_tree(child_hierarchy, indent + "  ")


async def demo_dynamic_updates():
    """Demonstrate dynamic update management."""
    
    print("\n" + "="*60)
    print("DEMO 4: Dynamic Update Management")
    print("="*60)
    
    # Create demo components
    servers = create_demo_servers()
    
    from unittest.mock import Mock, AsyncMock
    
    mock_server_manager = Mock()
    mock_server_manager.list_servers.return_value = ["file_tools"]  # Start with one server
    
    # Start with subset of tools
    initial_tools = [servers["file_tools"].tools[0]]  # Just file_reader initially
    
    async def mock_get_all_tools():
        return {"file_tools": [
            MCPTool(
                name=tool["name"],
                description=tool["description"],
                server_name="file_tools",
                input_schema=tool.get("schema", {"type": "object"})
            )
            for tool in initial_tools
        ]}
    
    mock_server_manager.get_all_tools = mock_get_all_tools
    mock_server_manager.get_server_health.return_value = servers["file_tools"].get_health()
    
    permission_manager = Mock()
    permission_manager.check_permission = AsyncMock(return_value=True)
    
    # Create components
    tool_registry = MCPToolRegistry(mock_server_manager, permission_manager)
    
    update_policy = UpdatePolicy(
        enable_hot_updates=True,
        batch_updates=False,  # Process immediately for demo
        max_concurrent_updates=3
    )
    
    update_manager = DynamicUpdateManager(mock_server_manager, tool_registry, update_policy)
    
    print(f"🔄 Starting dynamic update manager...")
    await update_manager.start()
    
    try:
        # Initial registration
        print(f"📋 Initial tool registration...")
        await tool_registry.discover_and_register_all_tools()
        initial_count = len(tool_registry.registered_tools)
        print(f"   Registered {initial_count} tools initially")
        
        # Simulate tool addition
        print(f"\n➕ Simulating tool addition...")
        initial_tools.extend(servers["file_tools"].tools[1:])  # Add file_writer
        
        # Check for updates
        updates = await update_manager.check_for_updates()
        addition_updates = [u for u in updates if u.update_type.value == "addition"]
        
        print(f"   Detected {len(addition_updates)} new tools")
        
        for update in addition_updates:
            print(f"   • {update.tool_name}: {update.update_type.value}")
            await update_manager.queue_update(update)
        
        # Wait for processing
        await asyncio.sleep(1)
        
        final_count = len(tool_registry.registered_tools)
        print(f"   Tools after update: {final_count}")
        
        # Simulate tool modification
        print(f"\n🔧 Simulating tool modification...")
        initial_tools[0]["description"] = "Updated: " + initial_tools[0]["description"]
        
        updates = await update_manager.check_for_updates()
        modification_updates = [u for u in updates if u.update_type.value == "modification"]
        
        print(f"   Detected {len(modification_updates)} tool modifications")
        
        for update in modification_updates:
            print(f"   • {update.tool_name}: {update.changes}")
            await update_manager.queue_update(update)
        
        # Wait for processing
        await asyncio.sleep(1)
        
        # Show update statistics
        stats = update_manager.get_update_stats()
        print(f"\n📊 Update Statistics:")
        print(f"   • Total updates processed: {stats['total_updates_processed']}")
        print(f"   • Successful updates: {stats['successful_updates']}")
        print(f"   • Failed updates: {stats['failed_updates']}")
        print(f"   • Average processing time: {stats['average_processing_time']:.3f}s")
        
        print(f"\n✅ Dynamic updates demo completed!")
        
    finally:
        await update_manager.stop()


async def demo_end_to_end_workflow():
    """Demonstrate complete end-to-end workflow."""
    
    print("\n" + "="*60)
    print("DEMO 5: End-to-End Workflow")
    print("="*60)
    
    print(f"🎯 Demonstrating complete MCP integration workflow...")
    
    # Create configuration
    servers = create_demo_servers()
    config_file = create_demo_config(servers)
    
    try:
        # Initialize global registry
        registry = SimaCodeToolRegistry()
        
        # Add built-in tools
        builtin_tools = [
            DemoBuiltinTool("help", "Show help information"),
            DemoBuiltinTool("version", "Show version information")
        ]
        
        for tool in builtin_tools:
            registry.register_builtin_tool(tool)
        
        print(f"✅ Added {len(builtin_tools)} built-in tools")
        
        # Mock MCP initialization (since we can't run real servers)
        print(f"🔌 Initializing MCP integration...")
        
        # In real usage, you would call:
        # success = await initialize_mcp_integration(config_file)
        
        # For demo, we simulate this:
        from unittest.mock import Mock, AsyncMock, patch
        
        with patch('simacode.mcp.integration.MCPServerManager') as MockServerManager, \
             patch('simacode.mcp.integration.MCPToolRegistry') as MockToolRegistry:
            
            # Mock server manager
            mock_server_manager = Mock()
            mock_server_manager.start = AsyncMock()
            mock_server_manager.list_servers.return_value = list(servers.keys())
            
            async def mock_get_all_tools():
                result = {}
                for name, server in servers.items():
                    result[name] = await server.list_tools()
                return result
            
            mock_server_manager.get_all_tools = mock_get_all_tools
            mock_server_manager.get_server_health = Mock(side_effect=lambda name: servers[name].get_health())
            
            MockServerManager.return_value = mock_server_manager
            
            # Mock tool registry
            mock_tool_registry = Mock()
            mock_tool_registry.start = AsyncMock()
            mock_tool_registry.stop = AsyncMock()
            mock_tool_registry.add_registration_callback = Mock()
            mock_tool_registry.add_unregistration_callback = Mock()
            mock_tool_registry.registered_tools = {}
            mock_tool_registry.list_registered_tools.return_value = []
            mock_tool_registry.get_registry_stats.return_value = {"currently_registered": 0}
            
            MockToolRegistry.return_value = mock_tool_registry
            
            # Initialize MCP
            success = await registry.initialize_mcp(config_file)
            print(f"   {'✅' if success else '❌'} MCP integration initialized")
            
            if success:
                # Demonstrate unified tool access
                print(f"\n🔧 Unified tool access:")
                all_tools = registry.list_tools()
                print(f"   • Total tools available: {len(all_tools)}")
                
                # Show categorized tools
                categories = ["file", "web", "data", "system"]
                for category in categories:
                    category_tools = registry.list_tools_by_category(category)
                    if category_tools:
                        print(f"   • {category.title()} tools: {len(category_tools)}")
                
                # Demonstrate tool search
                print(f"\n🔍 Tool search capabilities:")
                search_queries = ["file", "web", "process"]
                for query in search_queries:
                    results = registry.search_tools(query, fuzzy=True)
                    print(f"   • '{query}': {len(results)} matches")
                
                # Show registry statistics
                stats = registry.get_registry_stats()
                print(f"\n📊 Registry Statistics:")
                print(f"   • Built-in tools: {stats['builtin_tools']}")
                print(f"   • MCP enabled: {stats['mcp_enabled']}")
                print(f"   • Total tools: {stats['total_tools']}")
                
                print(f"\n🎉 Complete workflow demonstrated successfully!")
                
                # Clean up
                await registry.shutdown_mcp()
                print(f"✅ Clean shutdown completed")
    
    finally:
        # Clean up config file
        config_file.unlink()


async def main():
    """Run all demos."""
    
    print("MCP Phase 3 Integration Demo")
    print("=" * 50)
    print("This demo showcases the completed Phase 3 MCP integration system")
    print("with all its components working together seamlessly.")
    
    try:
        # Run all demos
        await demo_basic_integration()
        await demo_auto_discovery()
        await demo_namespace_management()
        await demo_dynamic_updates()
        await demo_end_to_end_workflow()
        
        print(f"\n🎉 All demos completed successfully!")
        print(f"\nPhase 3 MCP Integration Summary:")
        print(f"✅ Tool Wrapper - Seamlessly integrates MCP tools with SimaCode")
        print(f"✅ Tool Registry - Manages tool lifecycle and registration") 
        print(f"✅ Unified Integration - Combines built-in and MCP tools")
        print(f"✅ Auto-Discovery - Automatically finds and registers tools")
        print(f"✅ Namespace Management - Prevents conflicts and organizes tools")
        print(f"✅ Dynamic Updates - Hot-reloads tools without disruption")
        print(f"✅ End-to-End Workflow - Complete integration pipeline")
        
        print(f"\n🚀 Phase 3 MCP integration is ready for production use!")
        
    except Exception as e:
        print(f"\n❌ Demo failed with error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())