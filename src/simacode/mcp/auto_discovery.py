"""
MCP Auto-Discovery and Registration System

This module provides intelligent automatic discovery, registration, and
management of MCP tools, with smart categorization, conflict resolution,
and dynamic updates.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Set, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

from .server_manager import MCPServerManager
from .tool_registry import MCPToolRegistry, NamespaceManager
from .discovery import MCPToolDiscovery, ToolMetadata
from .protocol import MCPTool
from .health import HealthStatus
from .exceptions import MCPConnectionError

logger = logging.getLogger(__name__)


class DiscoveryMode(Enum):
    """Discovery operation modes."""
    PASSIVE = "passive"      # Only discover when explicitly requested
    ACTIVE = "active"        # Periodically discover new tools
    REACTIVE = "reactive"    # Discover in response to server events


@dataclass
class DiscoveryPolicy:
    """Policy configuration for auto-discovery behavior."""
    
    mode: DiscoveryMode = DiscoveryMode.ACTIVE
    
    # Timing settings
    discovery_interval: int = 300  # 5 minutes
    initial_delay: int = 30        # 30 seconds after startup
    retry_delay: int = 60          # 1 minute retry delay
    
    # Discovery criteria
    min_server_health: HealthStatus = HealthStatus.DEGRADED
    auto_register_new_tools: bool = True
    auto_unregister_dead_tools: bool = True
    
    # Filtering settings
    tool_name_patterns: List[str] = field(default_factory=list)  # Regex patterns
    excluded_servers: Set[str] = field(default_factory=set)
    excluded_tools: Set[str] = field(default_factory=set)
    
    # Conflict resolution
    prefer_newer_tools: bool = True
    allow_tool_overrides: bool = False
    max_tools_per_server: Optional[int] = None
    
    # Categorization
    auto_categorize: bool = True
    custom_categories: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class DiscoveryEvent:
    """Represents a discovery event."""
    
    event_type: str  # 'discovered', 'registered', 'unregistered', 'updated', 'failed'
    tool_name: str
    server_name: str
    timestamp: datetime = field(default_factory=datetime.now)
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "event_type": self.event_type,
            "tool_name": self.tool_name,
            "server_name": self.server_name,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details
        }


class MCPAutoDiscovery:
    """
    Intelligent auto-discovery system for MCP tools.
    
    This class provides comprehensive automatic tool discovery, registration,
    and lifecycle management with configurable policies and smart features.
    """
    
    def __init__(
        self,
        server_manager: MCPServerManager,
        tool_registry: MCPToolRegistry,
        policy: Optional[DiscoveryPolicy] = None
    ):
        """
        Initialize auto-discovery system.
        
        Args:
            server_manager: MCP server manager
            tool_registry: MCP tool registry
            policy: Discovery policy configuration
        """
        self.server_manager = server_manager
        self.tool_registry = tool_registry
        self.policy = policy or DiscoveryPolicy()
        
        # Discovery state
        self.is_running = False
        self.discovery_task: Optional[asyncio.Task] = None
        self.last_discovery: Dict[str, datetime] = {}
        
        # Event tracking
        self.discovery_events: List[DiscoveryEvent] = []
        self.max_events = 1000  # Keep last 1000 events
        
        # Statistics
        self.stats = {
            "total_discoveries": 0,
            "successful_registrations": 0,
            "failed_registrations": 0,
            "tools_unregistered": 0,
            "servers_processed": 0,
            "discovery_cycles": 0,
            "last_discovery_time": None
        }
        
        # Callbacks
        self.event_callbacks: List[Callable[[DiscoveryEvent], None]] = []
        
        # Tool tracking for change detection
        self.known_tools: Dict[str, Set[str]] = {}  # server -> tool names
        self.tool_signatures: Dict[str, str] = {}   # tool_id -> signature
    
    async def start(self) -> None:
        """Start the auto-discovery system."""
        if self.is_running:
            logger.warning("Auto-discovery is already running")
            return
        
        logger.info(f"Starting MCP auto-discovery with mode: {self.policy.mode.value}")
        
        self.is_running = True
        
        try:
            # Initial discovery after delay
            if self.policy.initial_delay > 0:
                logger.info(f"Waiting {self.policy.initial_delay}s before initial discovery")
                await asyncio.sleep(self.policy.initial_delay)
            
            # Perform initial discovery
            await self.discover_all()
            
            # Start continuous discovery if in active mode
            if self.policy.mode == DiscoveryMode.ACTIVE:
                self.discovery_task = asyncio.create_task(self._discovery_loop())
            
            logger.info("MCP auto-discovery started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start auto-discovery: {str(e)}")
            self.is_running = False
            raise
    
    async def stop(self) -> None:
        """Stop the auto-discovery system."""
        if not self.is_running:
            return
        
        logger.info("Stopping MCP auto-discovery")
        
        self.is_running = False
        
        # Cancel discovery task
        if self.discovery_task:
            self.discovery_task.cancel()
            try:
                await self.discovery_task
            except asyncio.CancelledError:
                pass
        
        logger.info("MCP auto-discovery stopped")
    
    async def discover_all(self) -> Dict[str, int]:
        """
        Perform comprehensive discovery across all servers.
        
        Returns:
            Dict[str, int]: Discovery results per server
        """
        logger.info("Starting comprehensive tool discovery")
        
        start_time = datetime.now()
        results = {}
        
        try:
            # Get all connected servers
            servers = self.server_manager.list_servers()
            
            # Filter servers based on policy
            eligible_servers = await self._filter_eligible_servers(servers)
            
            logger.info(f"Discovering tools from {len(eligible_servers)} eligible servers")
            
            # Discover tools from each server
            for server_name in eligible_servers:
                try:
                    count = await self.discover_server(server_name)
                    results[server_name] = count
                    self.stats["servers_processed"] += 1
                    
                except Exception as e:
                    logger.error(f"Discovery failed for server '{server_name}': {str(e)}")
                    results[server_name] = 0
                    self._record_event(
                        "failed",
                        "discovery",
                        server_name,
                        {"error": str(e)}
                    )
            
            # Update statistics
            self.stats["discovery_cycles"] += 1
            self.stats["last_discovery_time"] = start_time.isoformat()
            
            total_discovered = sum(results.values())
            logger.info(f"Discovery completed: {total_discovered} tools from {len(eligible_servers)} servers")
            
            return results
            
        except Exception as e:
            logger.error(f"Comprehensive discovery failed: {str(e)}")
            raise
    
    async def discover_server(self, server_name: str) -> int:
        """
        Discover and process tools from a specific server.
        
        Args:
            server_name: Name of the server to discover
            
        Returns:
            int: Number of tools discovered and processed
        """
        logger.debug(f"Discovering tools from server '{server_name}'")
        
        try:
            # Check server health
            if not await self._is_server_eligible(server_name):
                logger.debug(f"Server '{server_name}' not eligible for discovery")
                return 0
            
            # Get current tools
            server_tools = await self.server_manager.get_all_tools()
            tools = server_tools.get(server_name, [])
            
            if not tools:
                logger.debug(f"No tools found on server '{server_name}'")
                return 0
            
            # Apply tool filtering
            filtered_tools = await self._filter_tools(tools, server_name)
            
            # Detect changes
            changes = await self._detect_tool_changes(server_name, filtered_tools)
            
            # Process changes
            processed_count = 0
            
            # Handle new tools
            for tool in changes["added"]:
                if await self._process_new_tool(server_name, tool):
                    processed_count += 1
            
            # Handle updated tools
            for tool in changes["updated"]:
                if await self._process_updated_tool(server_name, tool):
                    processed_count += 1
            
            # Handle removed tools
            for tool_name in changes["removed"]:
                if await self._process_removed_tool(server_name, tool_name):
                    processed_count += 1
            
            # Update known tools
            self._update_known_tools(server_name, filtered_tools)
            self.last_discovery[server_name] = datetime.now()
            
            if processed_count > 0:
                logger.info(f"Processed {processed_count} tool changes from server '{server_name}'")
            
            return processed_count
            
        except Exception as e:
            logger.error(f"Server discovery failed for '{server_name}': {str(e)}")
            raise
    
    async def _filter_eligible_servers(self, servers: List[str]) -> List[str]:
        """Filter servers based on discovery policy."""
        eligible = []
        
        for server_name in servers:
            # Check exclusions
            if server_name in self.policy.excluded_servers:
                continue
            
            # Check health
            if await self._is_server_eligible(server_name):
                eligible.append(server_name)
        
        return eligible
    
    async def _is_server_eligible(self, server_name: str) -> bool:
        """Check if a server is eligible for discovery."""
        # Check server health
        health = self.server_manager.get_server_health(server_name)
        if not health:
            return False
        
        # Check minimum health requirement
        health_order = {
            HealthStatus.HEALTHY: 5,
            HealthStatus.DEGRADED: 4,
            HealthStatus.CRITICAL: 3,
            HealthStatus.FAILED: 2,
            HealthStatus.UNKNOWN: 1
        }
        
        min_health_score = health_order.get(self.policy.min_server_health, 0)
        current_health_score = health_order.get(health.status, 0)
        
        return current_health_score >= min_health_score
    
    async def _filter_tools(self, tools: List[MCPTool], server_name: str) -> List[MCPTool]:
        """Filter tools based on discovery policy."""
        filtered = []
        
        for tool in tools:
            # Check tool exclusions
            if tool.name in self.policy.excluded_tools:
                continue
            
            # Check name patterns
            if self.policy.tool_name_patterns:
                import re
                matches_pattern = False
                for pattern in self.policy.tool_name_patterns:
                    if re.match(pattern, tool.name):
                        matches_pattern = True
                        break
                if not matches_pattern:
                    continue
            
            filtered.append(tool)
        
        # Apply max tools limit
        if self.policy.max_tools_per_server:
            filtered = filtered[:self.policy.max_tools_per_server]
        
        return filtered
    
    async def _detect_tool_changes(
        self,
        server_name: str,
        current_tools: List[MCPTool]
    ) -> Dict[str, List]:
        """Detect changes in server tools."""
        current_tool_names = {tool.name for tool in current_tools}
        current_signatures = {
            tool.name: self._calculate_tool_signature(tool)
            for tool in current_tools
        }
        
        known_tool_names = self.known_tools.get(server_name, set())
        
        changes = {
            "added": [],
            "updated": [], 
            "removed": list(known_tool_names - current_tool_names)
        }
        
        for tool in current_tools:
            if tool.name not in known_tool_names:
                # New tool
                changes["added"].append(tool)
            else:
                # Check if tool has been updated
                old_signature = self.tool_signatures.get(f"{server_name}:{tool.name}")
                new_signature = current_signatures[tool.name]
                
                if old_signature != new_signature:
                    changes["updated"].append(tool)
        
        return changes
    
    def _calculate_tool_signature(self, tool: MCPTool) -> str:
        """Calculate a signature for a tool to detect changes."""
        import hashlib
        import json
        
        signature_data = {
            "name": tool.name,
            "description": tool.description,
            "schema": tool.input_schema
        }
        
        signature_str = json.dumps(signature_data, sort_keys=True)
        return hashlib.md5(signature_str.encode()).hexdigest()
    
    async def _process_new_tool(self, server_name: str, tool: MCPTool) -> bool:
        """Process a newly discovered tool."""
        try:
            logger.debug(f"Processing new tool '{tool.name}' from server '{server_name}'")
            
            if self.policy.auto_register_new_tools:
                # Auto-register the tool
                success = await self.tool_registry.register_server_tools(server_name, [tool])
                
                if success > 0:
                    self.stats["successful_registrations"] += 1
                    self._record_event(
                        "registered",
                        tool.name,
                        server_name,
                        {"auto_registered": True}
                    )
                    return True
                else:
                    self.stats["failed_registrations"] += 1
                    self._record_event(
                        "failed",
                        tool.name,
                        server_name,
                        {"reason": "registration_failed"}
                    )
            else:
                # Just record discovery
                self._record_event(
                    "discovered",
                    tool.name,
                    server_name,
                    {"auto_registered": False}
                )
            
            self.stats["total_discoveries"] += 1
            return False
            
        except Exception as e:
            logger.error(f"Failed to process new tool '{tool.name}': {str(e)}")
            self._record_event(
                "failed",
                tool.name,
                server_name,
                {"error": str(e)}
            )
            return False
    
    async def _process_updated_tool(self, server_name: str, tool: MCPTool) -> bool:
        """Process an updated tool."""
        try:
            logger.debug(f"Processing updated tool '{tool.name}' from server '{server_name}'")
            
            # Update tool signature
            signature = self._calculate_tool_signature(tool)
            self.tool_signatures[f"{server_name}:{tool.name}"] = signature
            
            # Check if tool is currently registered
            namespace = self.tool_registry.namespace_manager._sanitize_namespace_name(server_name)
            tool_full_name = f"{namespace}:{tool.name}"
            
            if tool_full_name in self.tool_registry.registered_tools:
                # Re-register updated tool
                await self.tool_registry.unregister_tool(tool_full_name)
                success = await self.tool_registry.register_server_tools(server_name, [tool])
                
                if success > 0:
                    self._record_event(
                        "updated",
                        tool.name,
                        server_name,
                        {"signature": signature}
                    )
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to process updated tool '{tool.name}': {str(e)}")
            return False
    
    async def _process_removed_tool(self, server_name: str, tool_name: str) -> bool:
        """Process a removed tool."""
        try:
            logger.debug(f"Processing removed tool '{tool_name}' from server '{server_name}'")
            
            if self.policy.auto_unregister_dead_tools:
                # Find and unregister the tool
                namespace = self.tool_registry.namespace_manager._sanitize_namespace_name(server_name)
                tool_full_name = f"{namespace}:{tool_name}"
                
                if await self.tool_registry.unregister_tool(tool_full_name):
                    self.stats["tools_unregistered"] += 1
                    self._record_event(
                        "unregistered",
                        tool_name,
                        server_name,
                        {"reason": "tool_removed"}
                    )
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to process removed tool '{tool_name}': {str(e)}")
            return False
    
    def _update_known_tools(self, server_name: str, tools: List[MCPTool]) -> None:
        """Update the known tools for a server."""
        self.known_tools[server_name] = {tool.name for tool in tools}
        
        # Update tool signatures
        for tool in tools:
            signature = self._calculate_tool_signature(tool)
            self.tool_signatures[f"{server_name}:{tool.name}"] = signature
    
    def _record_event(
        self,
        event_type: str,
        tool_name: str,
        server_name: str,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Record a discovery event."""
        event = DiscoveryEvent(
            event_type=event_type,
            tool_name=tool_name,
            server_name=server_name,
            details=details or {}
        )
        
        self.discovery_events.append(event)
        
        # Maintain max events limit
        if len(self.discovery_events) > self.max_events:
            self.discovery_events = self.discovery_events[-self.max_events:]
        
        # Notify callbacks
        for callback in self.event_callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Event callback failed: {str(e)}")
    
    async def _discovery_loop(self) -> None:
        """Main discovery loop for active mode."""
        logger.info(f"Starting discovery loop with {self.policy.discovery_interval}s interval")
        
        while self.is_running:
            try:
                await self.discover_all()
                await asyncio.sleep(self.policy.discovery_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in discovery loop: {str(e)}")
                await asyncio.sleep(self.policy.retry_delay)
    
    def add_event_callback(self, callback: Callable[[DiscoveryEvent], None]) -> None:
        """Add a callback for discovery events."""
        self.event_callbacks.append(callback)
    
    def remove_event_callback(self, callback: Callable[[DiscoveryEvent], None]) -> None:
        """Remove an event callback."""
        if callback in self.event_callbacks:
            self.event_callbacks.remove(callback)
    
    def get_recent_events(self, limit: int = 50) -> List[DiscoveryEvent]:
        """Get recent discovery events."""
        return self.discovery_events[-limit:]
    
    def get_discovery_stats(self) -> Dict[str, Any]:
        """Get comprehensive discovery statistics."""
        return {
            **self.stats,
            "is_running": self.is_running,
            "policy": {
                "mode": self.policy.mode.value,
                "discovery_interval": self.policy.discovery_interval,
                "auto_register": self.policy.auto_register_new_tools,
                "auto_unregister": self.policy.auto_unregister_dead_tools
            },
            "servers_tracked": len(self.known_tools),
            "total_known_tools": sum(len(tools) for tools in self.known_tools.values()),
            "recent_events": len(self.discovery_events),
            "event_callbacks": len(self.event_callbacks)
        }