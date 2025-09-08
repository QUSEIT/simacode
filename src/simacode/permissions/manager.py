"""
Permission management system for SimaCode.

This module implements a comprehensive permission system that controls
access to files, system commands, and other resources.
"""

import os
import re
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set

from ..config import Config


class PermissionLevel(Enum):
    """Permission level enumeration."""
    DENIED = "denied"
    RESTRICTED = "restricted"
    ALLOWED = "allowed"
    FULL = "full"


@dataclass
class PermissionResult:
    """Result of a permission check."""
    granted: bool
    level: PermissionLevel
    reason: str = ""
    restrictions: List[str] = None
    
    def __post_init__(self):
        if self.restrictions is None:
            self.restrictions = []


class PermissionManager:
    """
    Manages permissions for tool operations.
    
    This class provides centralized permission management for all tools,
    implementing various security policies and access controls.
    """
    
    def __init__(self, config: Optional[Config] = None):
        """Initialize permission manager with configuration."""
        if config is None:
            from ..config import Config
            self.config = Config.load()
        else:
            self.config = config
        self._permission_cache: Dict[str, PermissionResult] = {}
        self._cache_timeout = 300  # 5 minutes
        self._cache_timestamps: Dict[str, float] = {}
        
        # Load security configuration
        self._load_security_config()
    
    def _load_security_config(self) -> None:
        """Load security configuration from config."""
        # Get security config, handling both dict and Pydantic model cases
        if hasattr(self.config, 'security') and self.config.security:
            security_config = self.config.security
            
            # Extract allowed paths from Pydantic model
            if hasattr(security_config, 'allowed_paths'):
                self.allowed_paths: List[str] = [str(path) for path in security_config.allowed_paths]
            else:
                self.allowed_paths: List[str] = [str(Path.cwd())]
            
            # Extract forbidden paths from Pydantic model
            if hasattr(security_config, 'forbidden_paths'):
                self.forbidden_paths: List[str] = [str(path) for path in security_config.forbidden_paths]
            else:
                self.forbidden_paths: List[str] = [
                    "/etc", "/sys", "/proc", "/dev", "/boot", "/root",
                    "C:\\Windows", "C:\\System32", "C:\\Program Files"
                ]
            
            # Command timeout
            self.command_timeout = getattr(security_config, 'max_command_execution_time', 30)
        else:
            # Default values when no security config is available
            self.allowed_paths: List[str] = [
                str(Path.cwd()),  # Current working directory
                str(Path.home() / "tmp"),  # User temp directory
                str(Path.home() / "Desktop"),  # User Desktop for development
                "/tmp",  # System temp directory
            ]
            
            self.forbidden_paths: List[str] = [
                "/etc", "/sys", "/proc", "/dev", "/boot", "/root",
                "C:\\Windows", "C:\\System32", "C:\\Program Files"
            ]
            
            self.command_timeout = 30
        
        # Dangerous command patterns (hardcoded for security)
        self.dangerous_commands: List[str] = [
            r'rm\s+-rf\s*/',
            r'sudo\s+rm',
            r'format\s+[a-z]:',
            r'>\s*/dev/',
            r'dd\s+if=',
            r'mkfs\.',
            r'fdisk',
            r'chmod\s+777',
            r'chown\s+.*root',
            r'delpart',
            r'diskpart'
        ]
        
        # Permission level for different operations
        self.default_permission_level = PermissionLevel.RESTRICTED
        
        # File size limits (in bytes)
        self.max_file_size = 10 * 1024 * 1024  # 10MB
    
    def _get_cache_key(self, operation: str, target: str, **kwargs) -> str:
        """Generate cache key for permission check."""
        key_parts = [operation, target]
        for k, v in sorted(kwargs.items()):
            key_parts.append(f"{k}={v}")
        return "|".join(key_parts)
    
    def _get_cached_permission(self, cache_key: str) -> Optional[PermissionResult]:
        """Get cached permission result if still valid."""
        if cache_key in self._permission_cache:
            timestamp = self._cache_timestamps.get(cache_key, 0)
            if time.time() - timestamp < self._cache_timeout:
                return self._permission_cache[cache_key]
            else:
                # Cache expired
                del self._permission_cache[cache_key]
                del self._cache_timestamps[cache_key]
        return None
    
    def _cache_permission(self, cache_key: str, result: PermissionResult) -> None:
        """Cache permission result."""
        self._permission_cache[cache_key] = result
        self._cache_timestamps[cache_key] = time.time()
    
    def check_file_permission(
        self, 
        file_path: str, 
        operation: str = "read"
    ) -> PermissionResult:
        """
        Check permission for file operations.
        
        Args:
            file_path: Path to the file
            operation: Type of operation (read, write, delete, etc.)
            
        Returns:
            PermissionResult: Permission check result
        """
        # Development mode: allow all file operations for development
        development_mode = hasattr(self.config, 'development') and hasattr(self.config.development, 'debug_mode') and self.config.development.debug_mode
        
        if development_mode:
            return PermissionResult(
                granted=True,
                level=PermissionLevel.ALLOWED,
                reason="Development mode - permissions granted"
            )
        
        cache_key = self._get_cache_key("file", file_path, op=operation)
        cached_result = self._get_cached_permission(cache_key)
        if cached_result:
            return cached_result
        
        # Normalize path
        try:
            normalized_path = os.path.abspath(file_path)
        except (OSError, ValueError) as e:
            result = PermissionResult(
                granted=False,
                level=PermissionLevel.DENIED,
                reason=f"Invalid path: {str(e)}"
            )
            self._cache_permission(cache_key, result)
            return result
        
        # Check against forbidden paths
        for forbidden in self.forbidden_paths:
            if normalized_path.startswith(forbidden):
                result = PermissionResult(
                    granted=False,
                    level=PermissionLevel.DENIED,
                    reason=f"Access to {forbidden} is forbidden"
                )
                self._cache_permission(cache_key, result)
                return result
        
        # Check against allowed paths
        path_allowed = False
        for allowed in self.allowed_paths:
            # Expand user path and normalize
            expanded_allowed = os.path.abspath(os.path.expanduser(allowed))
            if normalized_path.startswith(expanded_allowed):
                path_allowed = True
                break
        
        if not path_allowed:
            result = PermissionResult(
                granted=False,
                level=PermissionLevel.DENIED,
                reason=f"Path {normalized_path} is not in allowed paths"
            )
            self._cache_permission(cache_key, result)
            return result
        
        # Check file size for read operations
        if operation == "read" and os.path.exists(normalized_path):
            try:
                file_size = os.path.getsize(normalized_path)
                if file_size > self.max_file_size:
                    result = PermissionResult(
                        granted=False,
                        level=PermissionLevel.DENIED,
                        reason=f"File size ({file_size} bytes) exceeds limit ({self.max_file_size} bytes)"
                    )
                    self._cache_permission(cache_key, result)
                    return result
            except OSError:
                pass  # File might not exist, that's ok for write operations
        
        # Determine permission level based on operation
        restrictions = []
        if operation == "write":
            # Check if we're writing to a potentially dangerous location
            if any(pattern in normalized_path.lower() for pattern in [
                "config", "settings", ".env", "password", "secret", "key"
            ]):
                restrictions.append("Writing to configuration/sensitive files")
        
        elif operation == "delete":
            restrictions.append("Deletion operations require extra caution")
        
        # Grant permission with appropriate level
        level = PermissionLevel.RESTRICTED if restrictions else PermissionLevel.ALLOWED
        result = PermissionResult(
            granted=True,
            level=level,
            reason=f"File {operation} operation permitted",
            restrictions=restrictions
        )
        
        self._cache_permission(cache_key, result)
        return result
    
    def check_command_permission(self, command: str) -> PermissionResult:
        """
        Check permission for command execution.
        
        Args:
            command: Command to execute
            
        Returns:
            PermissionResult: Permission check result
        """
        cache_key = self._get_cache_key("command", command)
        cached_result = self._get_cached_permission(cache_key)
        if cached_result:
            return cached_result
        
        # Check against dangerous command patterns
        for pattern in self.dangerous_commands:
            if re.search(pattern, command, re.IGNORECASE):
                result = PermissionResult(
                    granted=False,
                    level=PermissionLevel.DENIED,
                    reason=f"Command matches dangerous pattern: {pattern}"
                )
                self._cache_permission(cache_key, result)
                return result
        
        # Check for potentially risky commands
        risky_keywords = [
            "sudo", "su", "chmod", "chown", "mount", "umount",
            "iptables", "ufw", "firewall", "passwd", "useradd",
            "usermod", "userdel", "groupadd", "groupmod", "groupdel"
        ]
        
        restrictions = []
        for keyword in risky_keywords:
            if keyword in command.lower():
                restrictions.append(f"Command contains potentially risky keyword: {keyword}")
        
        # Check for network operations
        network_keywords = ["curl", "wget", "nc", "netcat", "ssh", "scp", "rsync"]
        for keyword in network_keywords:
            if keyword in command.lower():
                restrictions.append(f"Command involves network operations: {keyword}")
        
        # Determine permission level
        if restrictions:
            level = PermissionLevel.RESTRICTED
            reason = "Command permitted with restrictions"
        else:
            level = PermissionLevel.ALLOWED
            reason = "Command execution permitted"
        
        result = PermissionResult(
            granted=True,
            level=level,
            reason=reason,
            restrictions=restrictions
        )
        
        self._cache_permission(cache_key, result)
        return result
    
    def check_path_access(self, path: str, operation: str = "access") -> PermissionResult:
        """
        Check permission for path access.
        
        Args:
            path: Path to check
            operation: Type of access (access, list, create, etc.)
            
        Returns:
            PermissionResult: Permission check result
        """
        cache_key = self._get_cache_key("path", path, op=operation)
        cached_result = self._get_cached_permission(cache_key)
        if cached_result:
            return cached_result
        
        try:
            normalized_path = os.path.abspath(path)
        except (OSError, ValueError) as e:
            result = PermissionResult(
                granted=False,
                level=PermissionLevel.DENIED,
                reason=f"Invalid path: {str(e)}"
            )
            self._cache_permission(cache_key, result)
            return result
        
        # Check against forbidden paths
        for forbidden in self.forbidden_paths:
            if normalized_path.startswith(forbidden):
                result = PermissionResult(
                    granted=False,
                    level=PermissionLevel.DENIED,
                    reason=f"Access to {forbidden} is forbidden"
                )
                self._cache_permission(cache_key, result)
                return result
        
        # Check against allowed paths
        path_allowed = False
        for allowed in self.allowed_paths:
            # Expand user path and normalize
            expanded_allowed = os.path.abspath(os.path.expanduser(allowed))
            if normalized_path.startswith(expanded_allowed):
                path_allowed = True
                break
        
        if not path_allowed:
            result = PermissionResult(
                granted=False,
                level=PermissionLevel.DENIED,
                reason=f"Path {normalized_path} is not in allowed paths"
            )
            self._cache_permission(cache_key, result)
            return result
        
        # Grant permission
        result = PermissionResult(
            granted=True,
            level=PermissionLevel.ALLOWED,
            reason=f"Path {operation} operation permitted"
        )
        
        self._cache_permission(cache_key, result)
        return result
    
    async def check_tool_permission(self, tool_name: str, input_data: Dict) -> bool:
        """
        Check if tool execution is permitted.
        
        Args:
            tool_name: Name of the tool to execute
            input_data: Input data for the tool
            
        Returns:
            bool: True if tool execution is permitted
        """
        # For now, allow all tool executions
        # This can be extended with more sophisticated permission logic
        # based on tool_name, input_data, etc.
        
        # Check if there are any path-related restrictions
        for key, value in input_data.items():
            if isinstance(value, str) and ("path" in key.lower() or "file" in key.lower()):
                # Check path permission
                result = self.check_path_access(value, "access")
                if not result.granted:
                    return False
        
        return True
    
    def get_allowed_paths(self) -> List[str]:
        """Get list of allowed paths."""
        return self.allowed_paths.copy()
    
    def get_forbidden_paths(self) -> List[str]:
        """Get list of forbidden paths."""
        return self.forbidden_paths.copy()
    
    def clear_cache(self) -> None:
        """Clear permission cache."""
        self._permission_cache.clear()
        self._cache_timestamps.clear()
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        current_time = time.time()
        valid_entries = sum(
            1 for timestamp in self._cache_timestamps.values()
            if current_time - timestamp < self._cache_timeout
        )
        
        return {
            "total_entries": len(self._permission_cache),
            "valid_entries": valid_entries,
            "expired_entries": len(self._permission_cache) - valid_entries
        }