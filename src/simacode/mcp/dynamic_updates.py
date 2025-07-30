"""
Dynamic Tool Update Management for MCP Integration

This module provides real-time monitoring and updating of MCP tools,
including hot-reloading, version management, and graceful transitions.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Set, Any, Callable, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json

from .server_manager import MCPServerManager
from .tool_registry import MCPToolRegistry
from .tool_wrapper import MCPToolWrapper
from .protocol import MCPTool
from .health import HealthStatus
from .exceptions import MCPConnectionError

logger = logging.getLogger(__name__)


class UpdateType(Enum):
    """Types of tool updates."""
    ADDITION = "addition"         # New tool added
    REMOVAL = "removal"           # Tool removed
    MODIFICATION = "modification" # Tool schema/description changed
    HEALTH_CHANGE = "health_change"  # Server health changed
    SERVER_RESTART = "server_restart"  # Server restarted


class UpdatePriority(Enum):
    """Update priority levels."""
    LOW = "low"           # Background updates
    NORMAL = "normal"     # Standard updates
    HIGH = "high"         # Important updates
    CRITICAL = "critical" # Immediate updates required


@dataclass
class ToolUpdate:
    """Represents a tool update event."""
    
    update_type: UpdateType
    tool_name: str
    server_name: str
    priority: UpdatePriority = UpdatePriority.NORMAL
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Update details
    old_version: Optional[Dict[str, Any]] = None
    new_version: Optional[Dict[str, Any]] = None
    changes: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Processing status
    processed: bool = False
    processing_time: Optional[datetime] = None
    success: bool = False
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "update_type": self.update_type.value,
            "tool_name": self.tool_name,
            "server_name": self.server_name,
            "priority": self.priority.value,
            "timestamp": self.timestamp.isoformat(),
            "old_version": self.old_version,
            "new_version": self.new_version,
            "changes": self.changes,
            "metadata": self.metadata,
            "processed": self.processed,
            "processing_time": self.processing_time.isoformat() if self.processing_time else None,
            "success": self.success,
            "error_message": self.error_message
        }


@dataclass
class UpdatePolicy:
    """Policy configuration for dynamic updates."""
    
    # Update scheduling
    enable_hot_updates: bool = True
    batch_updates: bool = True
    batch_size: int = 10
    batch_timeout: int = 30  # seconds
    
    # Update priorities
    immediate_priorities: Set[UpdatePriority] = field(
        default_factory=lambda: {UpdatePriority.CRITICAL}
    )
    
    # Safety controls
    max_concurrent_updates: int = 5
    update_timeout: int = 60  # seconds
    rollback_on_failure: bool = True
    
    # Monitoring
    health_check_after_update: bool = True
    verify_tool_functionality: bool = True
    
    # Rate limiting
    max_updates_per_minute: int = 30
    backoff_on_failures: bool = True
    
    # Notification
    notify_on_updates: bool = True
    notify_on_failures: bool = True


class DynamicUpdateManager:
    """
    Manages dynamic updates of MCP tools.
    
    This class provides real-time monitoring and updating capabilities
    for MCP tools, ensuring smooth transitions and minimal disruption.
    """
    
    def __init__(
        self,
        server_manager: MCPServerManager,
        tool_registry: MCPToolRegistry,
        policy: Optional[UpdatePolicy] = None
    ):
        """
        Initialize the dynamic update manager.
        
        Args:
            server_manager: MCP server manager
            tool_registry: MCP tool registry
            policy: Update policy configuration
        """
        self.server_manager = server_manager
        self.tool_registry = tool_registry
        self.policy = policy or UpdatePolicy()
        
        # Update tracking
        self.pending_updates: Dict[str, ToolUpdate] = {}  # update_id -> update
        self.update_queue: asyncio.Queue = asyncio.Queue()
        self.processing_updates: Dict[str, ToolUpdate] = {}
        
        # Version tracking
        self.tool_versions: Dict[str, str] = {}  # tool_full_name -> version_hash
        self.server_snapshots: Dict[str, Dict[str, Any]] = {}  # server -> snapshot
        
        # Processing control
        self.is_running = False
        self.update_workers: List[asyncio.Task] = []
        self.monitor_task: Optional[asyncio.Task] = None
        
        # Rate limiting
        self.update_timestamps: List[datetime] = []
        self.semaphore = asyncio.Semaphore(self.policy.max_concurrent_updates)
        
        # Statistics
        self.stats = {
            "total_updates_processed": 0,
            "successful_updates": 0,
            "failed_updates": 0,
            "updates_by_type": {t.value: 0 for t in UpdateType},
            "updates_by_priority": {p.value: 0 for p in UpdatePriority},
            "average_processing_time": 0.0,
            "last_update_time": None
        }
        
        # Callbacks
        self.update_callbacks: List[Callable[[ToolUpdate], None]] = []
        self.failure_callbacks: List[Callable[[ToolUpdate], None]] = []
    
    async def start(self) -> None:
        """Start the dynamic update manager."""
        if self.is_running:
            logger.warning("Dynamic update manager is already running")
            return
        
        logger.info("Starting dynamic update manager")
        
        self.is_running = True
        
        try:
            # Initialize version tracking
            await self._initialize_version_tracking()
            
            # Start update workers
            worker_count = min(self.policy.max_concurrent_updates, 3)
            for i in range(worker_count):
                worker = asyncio.create_task(
                    self._update_worker(f"worker_{i}"),
                    name=f"update_worker_{i}"
                )
                self.update_workers.append(worker)
            
            # Start monitoring task
            self.monitor_task = asyncio.create_task(
                self._monitoring_loop(),
                name="update_monitor"
            )
            
            logger.info(f"Dynamic update manager started with {worker_count} workers")
            
        except Exception as e:
            logger.error(f"Failed to start dynamic update manager: {str(e)}")
            await self.stop()
            raise
    
    async def stop(self) -> None:
        """Stop the dynamic update manager."""
        if not self.is_running:
            return
        
        logger.info("Stopping dynamic update manager")
        
        self.is_running = False
        
        # Cancel monitoring task
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        
        # Cancel all workers
        for worker in self.update_workers:
            worker.cancel()
        
        if self.update_workers:
            await asyncio.gather(*self.update_workers, return_exceptions=True)
        
        self.update_workers.clear()
        
        logger.info("Dynamic update manager stopped")
    
    async def _initialize_version_tracking(self) -> None:
        """Initialize version tracking for existing tools."""
        logger.info("Initializing version tracking")
        
        try:
            # Get current tool states
            all_tools = await self.server_manager.get_all_tools()
            
            for server_name, tools in all_tools.items():
                # Create server snapshot
                server_snapshot = {
                    "tools": {tool.name: self._create_tool_snapshot(tool) for tool in tools},
                    "timestamp": datetime.now().isoformat(),
                    "health": self.server_manager.get_server_health(server_name)
                }
                self.server_snapshots[server_name] = server_snapshot
                
                # Track tool versions
                for tool in tools:
                    full_name = self._get_tool_full_name(server_name, tool.name)
                    version_hash = self._calculate_tool_version(tool)
                    self.tool_versions[full_name] = version_hash
            
            logger.info(f"Initialized version tracking for {len(self.tool_versions)} tools")
            
        except Exception as e:
            logger.error(f"Failed to initialize version tracking: {str(e)}")
            raise
    
    async def check_for_updates(self) -> List[ToolUpdate]:
        """
        Check for updates across all servers.
        
        Returns:
            List[ToolUpdate]: List of detected updates
        """
        updates = []
        
        try:
            # Get current state
            current_tools = await self.server_manager.get_all_tools()
            
            for server_name, tools in current_tools.items():
                server_updates = await self._check_server_updates(server_name, tools)
                updates.extend(server_updates)
        
        except Exception as e:
            logger.error(f"Failed to check for updates: {str(e)}")
        
        return updates
    
    async def _check_server_updates(
        self,
        server_name: str,
        current_tools: List[MCPTool]
    ) -> List[ToolUpdate]:
        """Check for updates on a specific server."""
        updates = []
        
        try:
            # Get previous snapshot
            old_snapshot = self.server_snapshots.get(server_name, {})
            old_tools = {t["name"]: t for t in old_snapshot.get("tools", {}).values()}
            
            # Create current tool mapping
            current_tool_map = {tool.name: tool for tool in current_tools}
            
            # Check for additions
            for tool_name, tool in current_tool_map.items():
                if tool_name not in old_tools:
                    update = ToolUpdate(
                        update_type=UpdateType.ADDITION,
                        tool_name=tool_name,
                        server_name=server_name,
                        new_version=self._create_tool_snapshot(tool),
                        changes=["Tool added"],
                        priority=UpdatePriority.NORMAL
                    )
                    updates.append(update)
            
            # Check for removals
            for old_tool_name in old_tools:
                if old_tool_name not in current_tool_map:
                    update = ToolUpdate(
                        update_type=UpdateType.REMOVAL,
                        tool_name=old_tool_name,
                        server_name=server_name,
                        old_version=old_tools[old_tool_name],
                        changes=["Tool removed"],
                        priority=UpdatePriority.HIGH
                    )
                    updates.append(update)
            
            # Check for modifications
            for tool_name, tool in current_tool_map.items():
                if tool_name in old_tools:
                    old_version = old_tools[tool_name]
                    new_version = self._create_tool_snapshot(tool)
                    
                    changes = self._detect_tool_changes(old_version, new_version)
                    if changes:
                        priority = self._determine_update_priority(changes)
                        
                        update = ToolUpdate(
                            update_type=UpdateType.MODIFICATION,
                            tool_name=tool_name,
                            server_name=server_name,
                            old_version=old_version,
                            new_version=new_version,
                            changes=changes,
                            priority=priority
                        )
                        updates.append(update)
            
            # Check for health changes
            current_health = self.server_manager.get_server_health(server_name)
            old_health = old_snapshot.get("health")
            
            if old_health and current_health:
                if current_health.status != old_health.status:
                    for tool_name in current_tool_map:
                        update = ToolUpdate(
                            update_type=UpdateType.HEALTH_CHANGE,
                            tool_name=tool_name,
                            server_name=server_name,
                            changes=[f"Server health: {old_health.status.value} -> {current_health.status.value}"],
                            priority=UpdatePriority.HIGH if current_health.status == HealthStatus.FAILED else UpdatePriority.NORMAL,
                            metadata={"old_health": old_health.status.value, "new_health": current_health.status.value}
                        )
                        updates.append(update)
            
            # Update snapshot
            self.server_snapshots[server_name] = {
                "tools": {tool.name: self._create_tool_snapshot(tool) for tool in current_tools},
                "timestamp": datetime.now().isoformat(),
                "health": current_health
            }
            
        except Exception as e:
            logger.error(f"Failed to check updates for server '{server_name}': {str(e)}")
        
        return updates
    
    def _create_tool_snapshot(self, tool: MCPTool) -> Dict[str, Any]:
        """Create a snapshot of a tool's current state."""
        return {
            "name": tool.name,
            "description": tool.description,
            "server_name": tool.server_name,
            "input_schema": tool.input_schema,
            "version_hash": self._calculate_tool_version(tool),
            "timestamp": datetime.now().isoformat()
        }
    
    def _calculate_tool_version(self, tool: MCPTool) -> str:
        """Calculate a version hash for a tool."""
        version_data = {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema
        }
        
        version_str = json.dumps(version_data, sort_keys=True)
        return hashlib.sha256(version_str.encode()).hexdigest()[:16]
    
    def _detect_tool_changes(
        self,
        old_version: Dict[str, Any],
        new_version: Dict[str, Any]
    ) -> List[str]:
        """Detect specific changes between tool versions."""
        changes = []
        
        # Description changes
        if old_version.get("description") != new_version.get("description"):
            changes.append("Description updated")
        
        # Schema changes
        old_schema = old_version.get("input_schema")
        new_schema = new_version.get("input_schema")
        
        if old_schema != new_schema:
            # Detect specific schema changes
            if self._is_breaking_schema_change(old_schema, new_schema):
                changes.append("Breaking schema change")
            else:
                changes.append("Schema updated")
        
        return changes
    
    def _is_breaking_schema_change(
        self,
        old_schema: Optional[Dict[str, Any]],
        new_schema: Optional[Dict[str, Any]]
    ) -> bool:
        """Determine if a schema change is breaking."""
        if not old_schema or not new_schema:
            return old_schema != new_schema
        
        # Check for removed required fields
        old_required = set(old_schema.get("required", []))
        new_required = set(new_schema.get("required", []))
        
        if old_required - new_required:  # Required fields removed
            return False  # Less restrictive, not breaking
        
        if new_required - old_required:  # New required fields added
            return True   # More restrictive, potentially breaking
        
        # Check for removed properties
        old_props = set(old_schema.get("properties", {}).keys())
        new_props = set(new_schema.get("properties", {}).keys())
        
        if old_props - new_props:  # Properties removed
            return True
        
        return False
    
    def _determine_update_priority(self, changes: List[str]) -> UpdatePriority:
        """Determine the priority of an update based on changes."""
        for change in changes:
            if "breaking" in change.lower():
                return UpdatePriority.CRITICAL
            elif "schema" in change.lower():
                return UpdatePriority.HIGH
        
        return UpdatePriority.NORMAL
    
    def _get_tool_full_name(self, server_name: str, tool_name: str) -> str:
        """Get the full name of a tool."""
        # This should match the naming logic in the tool registry
        namespace = self.tool_registry.namespace_manager._sanitize_namespace_name(server_name)
        return f"{namespace}:{tool_name}"
    
    async def queue_update(self, update: ToolUpdate) -> str:
        """
        Queue an update for processing.
        
        Args:
            update: Update to queue
            
        Returns:
            str: Update ID
        """
        update_id = f"{update.server_name}:{update.tool_name}:{update.timestamp.timestamp()}"
        
        # Check rate limiting
        if not self._check_rate_limit():
            logger.warning(f"Rate limit exceeded, queuing update {update_id}")
            update.priority = UpdatePriority.LOW
        
        self.pending_updates[update_id] = update
        
        # Queue immediately for critical updates
        if update.priority in self.policy.immediate_priorities:
            await self.update_queue.put((update_id, update))
        elif self.policy.batch_updates:
            # Will be picked up by batch processing
            pass
        else:
            await self.update_queue.put((update_id, update))
        
        logger.debug(f"Queued update {update_id}: {update.update_type.value} for {update.tool_name}")
        return update_id
    
    def _check_rate_limit(self) -> bool:
        """Check if we're within rate limits."""
        now = datetime.now()
        cutoff = now - timedelta(minutes=1)
        
        # Remove old timestamps
        self.update_timestamps = [ts for ts in self.update_timestamps if ts > cutoff]
        
        # Check limit
        if len(self.update_timestamps) >= self.policy.max_updates_per_minute:
            return False
        
        self.update_timestamps.append(now)
        return True
    
    async def _monitoring_loop(self) -> None:
        """Main monitoring loop for detecting updates."""
        logger.info("Starting update monitoring loop")
        
        while self.is_running:
            try:
                # Check for updates
                updates = await self.check_for_updates()
                
                # Queue detected updates
                for update in updates:
                    await self.queue_update(update)
                
                # Process batched updates
                if self.policy.batch_updates:
                    await self._process_batched_updates()
                
                # Wait before next check
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {str(e)}")
                await asyncio.sleep(60)  # Wait longer on error
    
    async def _process_batched_updates(self) -> None:
        """Process updates in batches."""
        batch = []
        
        # Collect pending updates
        for update_id, update in list(self.pending_updates.items()):
            if not update.processed and update.priority not in self.policy.immediate_priorities:
                batch.append((update_id, update))
                
                if len(batch) >= self.policy.batch_size:
                    break
        
        # Process batch
        if batch:
            for update_id, update in batch:
                await self.update_queue.put((update_id, update))
    
    async def _update_worker(self, worker_name: str) -> None:
        """Update processing worker."""
        logger.debug(f"Starting update worker: {worker_name}")
        
        while self.is_running:
            try:
                # Get next update
                try:
                    update_id, update = await asyncio.wait_for(
                        self.update_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Process update
                async with self.semaphore:
                    await self._process_update(update_id, update)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in update worker {worker_name}: {str(e)}")
    
    async def _process_update(self, update_id: str, update: ToolUpdate) -> None:
        """Process a single update."""
        start_time = datetime.now()
        
        try:
            logger.info(f"Processing update {update_id}: {update.update_type.value} for {update.tool_name}")
            
            update.processing_time = start_time
            self.processing_updates[update_id] = update
            
            # Process based on update type
            if update.update_type == UpdateType.ADDITION:
                success = await self._process_tool_addition(update)
            elif update.update_type == UpdateType.REMOVAL:
                success = await self._process_tool_removal(update)
            elif update.update_type == UpdateType.MODIFICATION:
                success = await self._process_tool_modification(update)
            elif update.update_type == UpdateType.HEALTH_CHANGE:
                success = await self._process_health_change(update)
            else:
                success = True  # Unknown type, mark as processed
            
            # Update statistics
            processing_time = (datetime.now() - start_time).total_seconds()
            
            update.processed = True
            update.success = success
            
            if success:
                self.stats["successful_updates"] += 1
            else:
                self.stats["failed_updates"] += 1
            
            self.stats["total_updates_processed"] += 1
            self.stats["updates_by_type"][update.update_type.value] += 1
            self.stats["updates_by_priority"][update.priority.value] += 1
            
            # Update average processing time
            total_time = self.stats["average_processing_time"] * (self.stats["total_updates_processed"] - 1)
            self.stats["average_processing_time"] = (total_time + processing_time) / self.stats["total_updates_processed"]
            self.stats["last_update_time"] = datetime.now().isoformat()
            
            # Notify callbacks
            if success and self.policy.notify_on_updates:
                for callback in self.update_callbacks:
                    try:
                        callback(update)
                    except Exception as e:
                        logger.error(f"Update callback failed: {str(e)}")
            elif not success and self.policy.notify_on_failures:
                for callback in self.failure_callbacks:
                    try:
                        callback(update)
                    except Exception as e:
                        logger.error(f"Failure callback failed: {str(e)}")
            
            logger.info(f"Update {update_id} processed successfully: {success}")
            
        except Exception as e:
            update.processed = True
            update.success = False
            update.error_message = str(e)
            
            logger.error(f"Failed to process update {update_id}: {str(e)}")
        
        finally:
            # Clean up
            if update_id in self.processing_updates:
                del self.processing_updates[update_id]
            if update_id in self.pending_updates:
                del self.pending_updates[update_id]
    
    async def _process_tool_addition(self, update: ToolUpdate) -> bool:
        """Process a tool addition update."""
        try:
            # Refresh server tools (this will auto-register new tools)
            await self.tool_registry.refresh_server_tools(update.server_name)
            return True
        except Exception as e:
            update.error_message = f"Failed to add tool: {str(e)}"
            return False
    
    async def _process_tool_removal(self, update: ToolUpdate) -> bool:
        """Process a tool removal update."""
        try:
            # Unregister the specific tool
            full_name = self._get_tool_full_name(update.server_name, update.tool_name)
            await self.tool_registry.unregister_tool(full_name)
            return True
        except Exception as e:
            update.error_message = f"Failed to remove tool: {str(e)}"
            return False
    
    async def _process_tool_modification(self, update: ToolUpdate) -> bool:
        """Process a tool modification update."""
        try:
            # For modifications, we need to refresh the specific tool
            full_name = self._get_tool_full_name(update.server_name, update.tool_name)
            
            # Unregister old version
            await self.tool_registry.unregister_tool(full_name)
            
            # Re-register new version
            await self.tool_registry.refresh_server_tools(update.server_name)
            
            return True
        except Exception as e:
            update.error_message = f"Failed to modify tool: {str(e)}"
            return False
    
    async def _process_health_change(self, update: ToolUpdate) -> bool:
        """Process a server health change update."""
        try:
            # For health changes, we mainly log and potentially adjust tool availability
            health = self.server_manager.get_server_health(update.server_name)
            
            if health and health.status == HealthStatus.FAILED:
                # Server failed, might want to temporarily disable tools
                logger.warning(f"Server '{update.server_name}' failed, tools may be unavailable")
            elif health and health.status == HealthStatus.HEALTHY:
                # Server recovered, ensure tools are available
                logger.info(f"Server '{update.server_name}' recovered")
            
            return True
        except Exception as e:
            update.error_message = f"Failed to process health change: {str(e)}"
            return False
    
    def add_update_callback(self, callback: Callable[[ToolUpdate], None]) -> None:
        """Add a callback for successful updates."""
        self.update_callbacks.append(callback)
    
    def add_failure_callback(self, callback: Callable[[ToolUpdate], None]) -> None:
        """Add a callback for failed updates."""
        self.failure_callbacks.append(callback)
    
    def get_update_stats(self) -> Dict[str, Any]:
        """Get update processing statistics."""
        return {
            **self.stats,
            "is_running": self.is_running,
            "pending_updates": len(self.pending_updates),
            "processing_updates": len(self.processing_updates),
            "queue_size": self.update_queue.qsize(),
            "worker_count": len(self.update_workers),
            "policy": {
                "enable_hot_updates": self.policy.enable_hot_updates,
                "batch_updates": self.policy.batch_updates,
                "max_concurrent_updates": self.policy.max_concurrent_updates,
                "max_updates_per_minute": self.policy.max_updates_per_minute
            }
        }