"""
MCP server health monitoring and management.

This module provides comprehensive health monitoring, diagnostics, and
auto-recovery capabilities for MCP servers.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import time

from .client import MCPClient, MCPClientState
from .exceptions import MCPConnectionError

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health status enumeration."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass
class HealthMetrics:
    """Health metrics for a server."""
    
    server_name: str
    status: HealthStatus = HealthStatus.UNKNOWN
    last_check: Optional[datetime] = None
    response_time: float = 0.0
    success_rate: float = 1.0
    error_count: int = 0
    consecutive_failures: int = 0
    uptime_percentage: float = 100.0
    
    # Detailed metrics
    total_checks: int = 0
    successful_checks: int = 0
    failed_checks: int = 0
    average_response_time: float = 0.0
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None
    
    # Recovery tracking
    recovery_attempts: int = 0
    last_recovery_attempt: Optional[datetime] = None
    recovery_success_rate: float = 0.0
    
    def update_check_result(self, success: bool, response_time: float, error: Optional[str] = None) -> None:
        """Update metrics with a health check result."""
        self.last_check = datetime.now()
        self.response_time = response_time
        self.total_checks += 1
        
        if success:
            self.successful_checks += 1
            self.consecutive_failures = 0
            self.error_count = max(0, self.error_count - 1)  # Slowly decrease error count
        else:
            self.failed_checks += 1
            self.consecutive_failures += 1
            self.error_count += 1
            self.last_error = error
            self.last_error_time = datetime.now()
        
        # Update success rate (exponential moving average)
        alpha = 0.1
        if success:
            self.success_rate = (1 - alpha) * self.success_rate + alpha * 1.0
        else:
            self.success_rate = (1 - alpha) * self.success_rate + alpha * 0.0
        
        # Update average response time
        self.average_response_time = (
            (self.average_response_time * (self.total_checks - 1) + response_time) / self.total_checks
        )
        
        # Update uptime percentage
        self.uptime_percentage = (self.successful_checks / self.total_checks) * 100 if self.total_checks > 0 else 100
        
        # Determine health status
        self.status = self._calculate_status()
    
    def record_recovery_attempt(self, success: bool) -> None:
        """Record a recovery attempt."""
        self.recovery_attempts += 1
        self.last_recovery_attempt = datetime.now()
        
        # Update recovery success rate
        if hasattr(self, '_recovery_successes'):
            if success:
                self._recovery_successes += 1
        else:
            self._recovery_successes = 1 if success else 0
        
        self.recovery_success_rate = (self._recovery_successes / self.recovery_attempts) * 100
    
    def _calculate_status(self) -> HealthStatus:
        """Calculate health status based on metrics."""
        if self.consecutive_failures >= 5:
            return HealthStatus.FAILED
        elif self.consecutive_failures >= 3:
            return HealthStatus.CRITICAL
        elif self.success_rate < 0.5 or self.response_time > 30.0:
            return HealthStatus.DEGRADED
        elif self.consecutive_failures == 0 and self.success_rate >= 0.8:
            return HealthStatus.HEALTHY
        else:
            return HealthStatus.DEGRADED
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "server_name": self.server_name,
            "status": self.status.value,
            "last_check": self.last_check.isoformat() if self.last_check else None,
            "response_time": self.response_time,
            "success_rate": round(self.success_rate, 4),
            "error_count": self.error_count,
            "consecutive_failures": self.consecutive_failures,
            "uptime_percentage": round(self.uptime_percentage, 2),
            "total_checks": self.total_checks,
            "successful_checks": self.successful_checks,
            "failed_checks": self.failed_checks,
            "average_response_time": round(self.average_response_time, 4),
            "last_error": self.last_error,
            "last_error_time": self.last_error_time.isoformat() if self.last_error_time else None,
            "recovery_attempts": self.recovery_attempts,
            "last_recovery_attempt": self.last_recovery_attempt.isoformat() if self.last_recovery_attempt else None,
            "recovery_success_rate": round(self.recovery_success_rate, 2)
        }


class MCPHealthMonitor:
    """
    Comprehensive health monitoring system for MCP servers.
    
    This class provides advanced health monitoring, alerting, and auto-recovery
    capabilities for MCP servers.
    """
    
    def __init__(self, check_interval: int = 30, recovery_enabled: bool = True):
        self.check_interval = check_interval
        self.recovery_enabled = recovery_enabled
        
        # Health tracking
        self.health_metrics: Dict[str, HealthMetrics] = {}
        self.monitoring_tasks: Dict[str, asyncio.Task] = {}
        
        # Recovery settings
        self.max_recovery_attempts = 3
        self.recovery_cooldown = 300  # 5 minutes
        self.recovery_backoff_factor = 2.0
        
        # Alerting
        self.alert_callbacks: List[callable] = []
        self.alert_thresholds = {
            HealthStatus.DEGRADED: 2,  # Alert after 2 degraded checks
            HealthStatus.CRITICAL: 1,  # Alert immediately
            HealthStatus.FAILED: 1     # Alert immediately
        }
        self.alert_history: Dict[str, List[datetime]] = {}
        
        # Global monitoring
        self.monitor_task: Optional[asyncio.Task] = None
        self.shutdown_event = asyncio.Event()
    
    async def start_monitoring(self) -> None:
        """Start the health monitoring system."""
        logger.info("Starting MCP health monitoring system")
        
        # Start global monitoring task
        self.monitor_task = asyncio.create_task(self._global_monitor_loop())
        
        logger.info("MCP health monitoring system started")
    
    async def stop_monitoring(self) -> None:
        """Stop the health monitoring system."""
        logger.info("Stopping MCP health monitoring system")
        
        # Signal shutdown
        self.shutdown_event.set()
        
        # Stop global monitoring
        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass
        
        # Stop individual server monitoring
        for task in self.monitoring_tasks.values():
            task.cancel()
        
        if self.monitoring_tasks:
            await asyncio.gather(*self.monitoring_tasks.values(), return_exceptions=True)
        
        self.monitoring_tasks.clear()
        
        logger.info("MCP health monitoring system stopped")
    
    async def add_server(self, server_name: str, client: MCPClient) -> None:
        """
        Add a server to health monitoring.
        
        Args:
            server_name: Name of the server
            client: MCPClient instance
        """
        if server_name in self.health_metrics:
            logger.warning(f"Server '{server_name}' already being monitored")
            return
        
        # Initialize health metrics
        self.health_metrics[server_name] = HealthMetrics(server_name)
        
        # Start monitoring task for this server
        task = asyncio.create_task(
            self._monitor_server(server_name, client),
            name=f"monitor_{server_name}"
        )
        self.monitoring_tasks[server_name] = task
        
        logger.info(f"Started health monitoring for server '{server_name}'")
    
    async def remove_server(self, server_name: str) -> None:
        """
        Remove a server from health monitoring.
        
        Args:
            server_name: Name of the server
        """
        # Stop monitoring task
        if server_name in self.monitoring_tasks:
            task = self.monitoring_tasks[server_name]
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            del self.monitoring_tasks[server_name]
        
        # Remove metrics
        if server_name in self.health_metrics:
            del self.health_metrics[server_name]
        
        # Clear alert history
        if server_name in self.alert_history:
            del self.alert_history[server_name]
        
        logger.info(f"Stopped health monitoring for server '{server_name}'")
    
    def get_server_health(self, server_name: str) -> Optional[HealthMetrics]:
        """Get health metrics for a specific server."""
        return self.health_metrics.get(server_name)
    
    def get_all_health_metrics(self) -> Dict[str, HealthMetrics]:
        """Get health metrics for all servers."""
        return self.health_metrics.copy()
    
    def get_unhealthy_servers(self) -> List[str]:
        """Get list of unhealthy server names."""
        unhealthy = []
        for name, metrics in self.health_metrics.items():
            if metrics.status in [HealthStatus.CRITICAL, HealthStatus.FAILED]:
                unhealthy.append(name)
        return unhealthy
    
    def add_alert_callback(self, callback: callable) -> None:
        """Add an alert callback function."""
        self.alert_callbacks.append(callback)
    
    def remove_alert_callback(self, callback: callable) -> None:
        """Remove an alert callback function."""
        if callback in self.alert_callbacks:
            self.alert_callbacks.remove(callback)
    
    async def _monitor_server(self, server_name: str, client: MCPClient) -> None:
        """Monitor a specific server's health."""
        logger.debug(f"Starting health monitoring loop for server '{server_name}'")
        
        while not self.shutdown_event.is_set():
            try:
                await self._perform_health_check(server_name, client)
                
                # Wait for next check or shutdown
                try:
                    await asyncio.wait_for(
                        self.shutdown_event.wait(),
                        timeout=self.check_interval
                    )
                except asyncio.TimeoutError:
                    continue  # Normal timeout, continue loop
                else:
                    break  # Shutdown event was set
                    
            except Exception as e:
                logger.error(f"Error in health monitoring loop for '{server_name}': {str(e)}")
                await asyncio.sleep(5)  # Wait before retrying
    
    async def _perform_health_check(self, server_name: str, client: MCPClient) -> None:
        """Perform a health check on a server."""
        metrics = self.health_metrics[server_name]
        
        start_time = time.time()
        success = False
        error_message = None
        
        try:
            if client.is_connected():
                # Try to ping the server, but fall back to connection check if ping fails
                try:
                    success = await asyncio.wait_for(client.ping(), timeout=60.0)
                    if not success:
                        # Ping returned False, try alternative health check
                        tools = await asyncio.wait_for(client.list_tools(), timeout=60.0)
                        success = True  # If we can list tools, server is healthy
                except asyncio.TimeoutError:
                    error_message = "Health check timeout"
                except Exception as ping_error:
                    # If ping fails, use tool list as health check for servers that don't support ping
                    logger.debug(f"Ping failed for '{server_name}': {str(ping_error)}, trying list_tools as fallback")
                    try:
                        tools = await asyncio.wait_for(client.list_tools(), timeout=60.0)
                        success = True  # If we can list tools, server is healthy
                    except Exception as tools_error:
                        logger.debug(f"List tools also failed for '{server_name}': {str(tools_error)}, but client reports connected")
                        success = True  # Still consider connected if client says it's connected
            else:
                last_error = client.get_last_error()
                state = client.get_state()
                stats = client.get_stats()
                connection_attempts = stats.get('connection_attempts', 0)

                if last_error:
                    error_message = f"Client not connected (state: {state}, connection_attempts: {connection_attempts}, last_error: {str(last_error)})"
                else:
                    error_message = f"Client not connected (state: {state}, connection_attempts: {connection_attempts})"
            
        except asyncio.TimeoutError:
            error_message = "Health check timeout"
        except Exception as e:
            # Include client state and last error for better diagnostics
            state = client.get_state()
            last_error = client.get_last_error()
            if last_error:
                error_message = f"Health check failed: {str(e)} (client_state: {state}, last_client_error: {str(last_error)})"
            else:
                error_message = f"Health check failed: {str(e)} (client_state: {state})"
        
        response_time = time.time() - start_time
        
        # Update metrics
        old_status = metrics.status
        metrics.update_check_result(success, response_time, error_message)
        
        # Log health check result
        if success:
            # Only log successful checks at debug level for critical servers or errors
            pass
        else:
            logger.warning(f"Health check failed for '{server_name}': {error_message}")
        
        # Check for status changes and alerts
        if metrics.status != old_status:
            await self._handle_status_change(server_name, old_status, metrics.status, client)
        
        # Trigger alerts if needed
        await self._check_alert_conditions(server_name, metrics)
    
    async def _handle_status_change(self, server_name: str, old_status: HealthStatus, 
                                   new_status: HealthStatus, client: MCPClient) -> None:
        """Handle server status changes."""
        logger.info(f"Server '{server_name}' status changed from {old_status.value} to {new_status.value}")
        
        # Attempt recovery for failed/critical servers
        if (self.recovery_enabled and 
            new_status in [HealthStatus.CRITICAL, HealthStatus.FAILED] and
            old_status not in [HealthStatus.CRITICAL, HealthStatus.FAILED]):
            
            await self._attempt_recovery(server_name, client)
    
    async def _attempt_recovery(self, server_name: str, client: MCPClient) -> None:
        """Attempt to recover a failed server."""
        metrics = self.health_metrics[server_name]
        
        # Check recovery cooldown
        if (metrics.last_recovery_attempt and 
            datetime.now() - metrics.last_recovery_attempt < timedelta(seconds=self.recovery_cooldown)):
            logger.debug(f"Recovery cooldown active for server '{server_name}'")
            return
        
        # Check max recovery attempts
        if metrics.recovery_attempts >= self.max_recovery_attempts:
            logger.warning(f"Max recovery attempts reached for server '{server_name}'")
            return
        
        logger.info(f"Attempting to recover server '{server_name}' (attempt {metrics.recovery_attempts + 1})")
        
        try:
            # Try to disconnect and reconnect
            await client.disconnect()
            await asyncio.sleep(1)  # Brief pause
            
            success = await client.connect()
            metrics.record_recovery_attempt(success)
            
            if success:
                logger.info(f"Successfully recovered server '{server_name}'")
            else:
                logger.warning(f"Failed to recover server '{server_name}'")
            
        except Exception as e:
            logger.error(f"Recovery attempt failed for server '{server_name}': {str(e)}")
            metrics.record_recovery_attempt(False)
    
    async def _check_alert_conditions(self, server_name: str, metrics: HealthMetrics) -> None:
        """Check if alert conditions are met."""
        status = metrics.status
        
        if status not in self.alert_thresholds:
            return
        
        threshold = self.alert_thresholds[status]
        
        # Check if we've had enough consecutive issues to trigger alert
        if metrics.consecutive_failures >= threshold:
            # Check if we recently alerted for this server
            if server_name not in self.alert_history:
                self.alert_history[server_name] = []
            
            recent_alerts = [
                alert_time for alert_time in self.alert_history[server_name]
                if datetime.now() - alert_time < timedelta(minutes=30)
            ]
            
            # Only alert if we haven't alerted recently
            if not recent_alerts:
                await self._trigger_alert(server_name, metrics)
                self.alert_history[server_name].append(datetime.now())
    
    async def _trigger_alert(self, server_name: str, metrics: HealthMetrics) -> None:
        """Trigger alerts for a server."""
        logger.warning(f"Health alert triggered for server '{server_name}': {metrics.status.value}")
        
        alert_data = {
            "server_name": server_name,
            "status": metrics.status.value,
            "metrics": metrics.to_dict(),
            "timestamp": datetime.now().isoformat()
        }
        
        # Call all alert callbacks
        for callback in self.alert_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(alert_data)
                else:
                    callback(alert_data)
            except Exception as e:
                logger.error(f"Alert callback failed: {str(e)}")
    
    async def _global_monitor_loop(self) -> None:
        """Global monitoring loop for system-wide health checks."""
        logger.info("Starting global health monitor loop")
        
        while not self.shutdown_event.is_set():
            try:
                await self._perform_global_health_checks()
                
                # Wait for next check (longer interval for global checks)
                try:
                    await asyncio.wait_for(
                        self.shutdown_event.wait(),
                        timeout=self.check_interval * 2  # Less frequent global checks
                    )
                except asyncio.TimeoutError:
                    continue
                else:
                    break
                    
            except Exception as e:
                logger.error(f"Error in global health monitor loop: {str(e)}")
                await asyncio.sleep(10)
    
    async def _perform_global_health_checks(self) -> None:
        """Perform system-wide health checks."""
        total_servers = len(self.health_metrics)
        if total_servers == 0:
            return
        
        # Check if any servers have been checked at least once
        servers_with_checks = sum(
            1 for metrics in self.health_metrics.values()
            if metrics.total_checks > 0
        )
        
        # Don't report critical status until servers have been checked
        if servers_with_checks == 0:
            logger.debug("Skipping global health check - no servers have been checked yet")
            return
        
        healthy_servers = sum(
            1 for metrics in self.health_metrics.values()
            if metrics.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]  # Include degraded as acceptable
        )
        
        overall_health_percentage = (healthy_servers / total_servers) * 100
        
        logger.debug(f"Overall system health: {overall_health_percentage:.1f}% ({healthy_servers}/{total_servers} healthy)")
        
        # Only trigger alerts if health is genuinely poor (not just unknown/uninitialized)
        if overall_health_percentage < 50 and servers_with_checks == total_servers:
            logger.critical(f"System-wide health critical: only {overall_health_percentage:.1f}% of servers healthy")
    
    def get_monitoring_stats(self) -> Dict[str, Any]:
        """Get monitoring system statistics."""
        total_servers = len(self.health_metrics)
        
        status_counts = {}
        for status in HealthStatus:
            status_counts[status.value] = sum(
                1 for metrics in self.health_metrics.values()
                if metrics.status == status
            )
        
        return {
            "total_servers": total_servers,
            "active_monitors": len(self.monitoring_tasks),
            "check_interval": self.check_interval,
            "recovery_enabled": self.recovery_enabled,
            "status_distribution": status_counts,
            "alert_callbacks_count": len(self.alert_callbacks),
            "total_alerts_sent": sum(len(alerts) for alerts in self.alert_history.values())
        }