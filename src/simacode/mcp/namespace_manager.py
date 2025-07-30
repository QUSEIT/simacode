"""
Enhanced Namespace Management for MCP Tools

This module provides advanced namespace management capabilities for MCP tools,
including hierarchical namespaces, alias management, conflict resolution,
and namespace policies.
"""

import logging
import re
from typing import Dict, List, Set, Optional, Tuple, Any
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ConflictResolution(Enum):
    """Namespace conflict resolution strategies."""
    REJECT = "reject"           # Reject conflicting tool
    SUFFIX = "suffix"           # Add numeric suffix
    PREFIX = "prefix"           # Add server prefix
    NAMESPACE = "namespace"     # Force into namespace
    OVERWRITE = "overwrite"     # Replace existing tool


@dataclass
class NamespacePolicy:
    """Policy configuration for namespace management."""
    
    # Conflict resolution
    conflict_resolution: ConflictResolution = ConflictResolution.SUFFIX
    
    # Naming rules
    allow_global_names: bool = False  # Allow tools in global namespace
    require_namespaces: bool = True   # Always use namespaces
    max_namespace_depth: int = 3      # Maximum namespace hierarchy depth
    
    # Naming patterns
    valid_name_pattern: str = r'^[a-z][a-z0-9_]*$'
    reserved_names: Set[str] = field(default_factory=lambda: {
        'help', 'version', 'config', 'status', 'exit', 'quit'
    })
    
    # Auto-naming
    auto_create_aliases: bool = True
    preferred_alias_length: int = 8
    
    # Deprecation
    allow_deprecated_names: bool = False
    deprecation_warning_threshold: int = 30  # days


@dataclass
class NamespaceInfo:
    """Information about a namespace."""
    
    name: str
    description: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    server_name: Optional[str] = None
    parent: Optional[str] = None
    children: Set[str] = field(default_factory=set)
    tools: Set[str] = field(default_factory=set)
    aliases: Dict[str, str] = field(default_factory=dict)  # alias -> full_name
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
            "server_name": self.server_name,
            "parent": self.parent,
            "children": list(self.children),
            "tools": list(self.tools),
            "aliases": self.aliases,
            "metadata": self.metadata
        }


@dataclass
class ToolNameInfo:
    """Information about a tool name and its namespace placement."""
    
    original_name: str
    full_name: str
    namespace: Optional[str]
    server_name: str
    aliases: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    is_deprecated: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "original_name": self.original_name,
            "full_name": self.full_name,
            "namespace": self.namespace,
            "server_name": self.server_name,
            "aliases": self.aliases,
            "conflicts": self.conflicts,
            "created_at": self.created_at.isoformat(),
            "is_deprecated": self.is_deprecated
        }


class EnhancedNamespaceManager:
    """
    Advanced namespace manager for MCP tools.
    
    This class provides sophisticated namespace management including
    hierarchical namespaces, alias management, conflict resolution,
    and policy enforcement.
    """
    
    def __init__(self, policy: Optional[NamespacePolicy] = None):
        """
        Initialize the enhanced namespace manager.
        
        Args:
            policy: Namespace policy configuration
        """
        self.policy = policy or NamespacePolicy()
        
        # Namespace registry
        self.namespaces: Dict[str, NamespaceInfo] = {}
        
        # Tool name registry
        self.tool_names: Dict[str, ToolNameInfo] = {}  # full_name -> info
        self.name_to_full: Dict[str, str] = {}        # any_name -> full_name
        self.server_namespaces: Dict[str, str] = {}   # server -> namespace
        
        # Conflict tracking
        self.name_conflicts: Dict[str, List[str]] = {}  # name -> conflicting_full_names
        
        # Statistics
        self.stats = {
            "namespaces_created": 0,
            "tools_registered": 0,
            "conflicts_resolved": 0,
            "aliases_created": 0
        }
    
    def create_namespace(
        self,
        name: str,
        description: str = "",
        parent: Optional[str] = None,
        server_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Create a new namespace.
        
        Args:
            name: Namespace name
            description: Optional description
            parent: Optional parent namespace
            server_name: Associated server name
            metadata: Optional metadata
            
        Returns:
            bool: True if namespace was created
        """
        try:
            # Validate namespace name
            if not self._is_valid_namespace_name(name):
                logger.error(f"Invalid namespace name: {name}")
                return False
            
            # Check if namespace already exists
            if name in self.namespaces:
                logger.warning(f"Namespace '{name}' already exists")
                return False
            
            # Validate parent namespace
            if parent and parent not in self.namespaces:
                logger.error(f"Parent namespace '{parent}' does not exist")
                return False
            
            # Check hierarchy depth
            if parent:
                depth = self._calculate_namespace_depth(parent) + 1
                if depth > self.policy.max_namespace_depth:
                    logger.error(f"Namespace depth limit exceeded: {depth} > {self.policy.max_namespace_depth}")
                    return False
            
            # Create namespace
            namespace_info = NamespaceInfo(
                name=name,
                description=description,
                parent=parent,
                server_name=server_name,
                metadata=metadata or {}
            )
            
            self.namespaces[name] = namespace_info
            
            # Update parent-child relationships
            if parent:
                self.namespaces[parent].children.add(name)
            
            # Track server namespace mapping
            if server_name:
                self.server_namespaces[server_name] = name
            
            self.stats["namespaces_created"] += 1
            logger.info(f"Created namespace '{name}'" + (f" under '{parent}'" if parent else ""))
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to create namespace '{name}': {str(e)}")
            return False
    
    def register_tool_name(
        self,
        original_name: str,
        server_name: str,
        namespace: Optional[str] = None,
        preferred_name: Optional[str] = None
    ) -> Optional[ToolNameInfo]:
        """
        Register a tool name with conflict resolution.
        
        Args:
            original_name: Original tool name from MCP server
            server_name: Name of the MCP server
            namespace: Optional explicit namespace
            preferred_name: Optional preferred full name
            
        Returns:
            Optional[ToolNameInfo]: Tool name info if successful
        """
        try:
            # Determine namespace
            if namespace is None:
                namespace = self._determine_namespace_for_server(server_name)
            
            # Generate candidate names
            candidates = self._generate_name_candidates(
                original_name, server_name, namespace, preferred_name
            )
            
            # Find available name
            chosen_name, conflicts = self._resolve_name_conflicts(candidates)
            
            if not chosen_name:
                logger.error(f"Could not resolve name conflicts for tool '{original_name}' from server '{server_name}'")
                return None
            
            # Create tool name info
            tool_info = ToolNameInfo(
                original_name=original_name,
                full_name=chosen_name,
                namespace=namespace,
                server_name=server_name,
                conflicts=conflicts
            )
            
            # Register the name
            self.tool_names[chosen_name] = tool_info
            self.name_to_full[chosen_name] = chosen_name
            
            # Update namespace
            if namespace and namespace in self.namespaces:
                self.namespaces[namespace].tools.add(chosen_name)
            
            # Create aliases if policy allows
            if self.policy.auto_create_aliases:
                aliases = self._create_aliases(tool_info)
                tool_info.aliases = aliases
                
                # Register aliases
                for alias in aliases:
                    if alias not in self.name_to_full:
                        self.name_to_full[alias] = chosen_name
                        if namespace and namespace in self.namespaces:
                            self.namespaces[namespace].aliases[alias] = chosen_name
                        self.stats["aliases_created"] += 1
            
            if conflicts:
                self.stats["conflicts_resolved"] += 1
                logger.info(f"Resolved naming conflicts for '{original_name}' -> '{chosen_name}'")
            
            self.stats["tools_registered"] += 1
            logger.debug(f"Registered tool name: {original_name} -> {chosen_name}")
            
            return tool_info
            
        except Exception as e:
            logger.error(f"Failed to register tool name '{original_name}': {str(e)}")
            return None
    
    def _determine_namespace_for_server(self, server_name: str) -> Optional[str]:
        """Determine the appropriate namespace for a server."""
        # Check if server already has a namespace
        if server_name in self.server_namespaces:
            return self.server_namespaces[server_name]
        
        # Auto-create namespace if required
        if self.policy.require_namespaces:
            namespace_name = self._sanitize_namespace_name(server_name)
            
            if self.create_namespace(
                namespace_name,
                description=f"Namespace for MCP server: {server_name}",
                server_name=server_name
            ):
                return namespace_name
        
        return None
    
    def _generate_name_candidates(
        self,
        original_name: str,
        server_name: str,
        namespace: Optional[str],
        preferred_name: Optional[str]
    ) -> List[str]:
        """Generate candidate names for a tool."""
        candidates = []
        
        # Preferred name first
        if preferred_name:
            candidates.append(preferred_name)
        
        # Original name in namespace
        if namespace:
            candidates.append(f"{namespace}:{original_name}")
        
        # Original name with server prefix
        server_prefix = self._sanitize_name(server_name)
        candidates.extend([
            f"{server_prefix}_{original_name}",
            f"{server_prefix}.{original_name}"
        ])
        
        # Global name (if allowed)
        if self.policy.allow_global_names:
            candidates.append(original_name)
        
        # Numbered variants
        for i in range(2, 10):
            base_name = f"{namespace}:{original_name}" if namespace else original_name
            candidates.append(f"{base_name}_{i}")
        
        return candidates
    
    def _resolve_name_conflicts(self, candidates: List[str]) -> Tuple[Optional[str], List[str]]:
        """
        Resolve naming conflicts using the configured strategy.
        
        Args:
            candidates: List of candidate names
            
        Returns:
            Tuple[Optional[str], List[str]]: (chosen_name, conflicts)
        """
        conflicts = []
        
        for candidate in candidates:
            if candidate not in self.name_to_full:
                # Name is available
                return candidate, conflicts
            else:
                # Name is taken
                conflicts.append(candidate)
                
                if self.policy.conflict_resolution == ConflictResolution.OVERWRITE:
                    # Allow overwriting
                    return candidate, conflicts
        
        # No available name found
        if self.policy.conflict_resolution == ConflictResolution.REJECT:
            return None, conflicts
        
        # Generate new name based on strategy
        if self.policy.conflict_resolution == ConflictResolution.SUFFIX:
            base_name = candidates[0] if candidates else "unknown_tool"
            for i in range(2, 100):
                candidate = f"{base_name}_{i}"
                if candidate not in self.name_to_full:
                    return candidate, conflicts
        
        return None, conflicts
    
    def _create_aliases(self, tool_info: ToolNameInfo) -> List[str]:
        """Create aliases for a tool."""
        aliases = []
        
        # Short alias based on original name
        short_name = tool_info.original_name
        if len(short_name) <= self.policy.preferred_alias_length and short_name not in self.name_to_full:
            aliases.append(short_name)
        
        # Abbreviated aliases
        if len(tool_info.original_name) > self.policy.preferred_alias_length:
            # First letters of words
            words = re.findall(r'[a-zA-Z]+', tool_info.original_name)
            if len(words) > 1:
                abbreviation = ''.join(word[0].lower() for word in words)
                if abbreviation not in self.name_to_full and len(abbreviation) >= 2:
                    aliases.append(abbreviation)
        
        return aliases
    
    def _is_valid_namespace_name(self, name: str) -> bool:
        """Check if a namespace name is valid."""
        if not name or not isinstance(name, str):
            return False
        
        # Check pattern
        if not re.match(self.policy.valid_name_pattern, name):
            return False
        
        # Check reserved names
        if name in self.policy.reserved_names:
            return False
        
        return True
    
    def _sanitize_namespace_name(self, name: str) -> str:
        """Sanitize a name to create a valid namespace."""
        # Convert to lowercase and replace invalid characters
        sanitized = re.sub(r'[^a-z0-9_]', '_', name.lower())
        
        # Remove consecutive underscores
        sanitized = re.sub(r'_+', '_', sanitized)
        
        # Remove leading/trailing underscores
        sanitized = sanitized.strip('_')
        
        # Ensure it doesn't start with a number
        if sanitized and sanitized[0].isdigit():
            sanitized = f"ns_{sanitized}"
        
        # Fallback if empty
        if not sanitized:
            sanitized = "mcp_namespace"
        
        return sanitized
    
    def _sanitize_name(self, name: str) -> str:
        """Sanitize a general name."""
        return re.sub(r'[^a-zA-Z0-9_]', '_', name)
    
    def _calculate_namespace_depth(self, namespace: str) -> int:
        """Calculate the depth of a namespace in the hierarchy."""
        if namespace not in self.namespaces:
            return 0
        
        info = self.namespaces[namespace]
        if not info.parent:
            return 1
        
        return 1 + self._calculate_namespace_depth(info.parent)
    
    def resolve_name(self, name: str) -> Optional[str]:
        """
        Resolve any name (full name, alias, etc.) to its full name.
        
        Args:
            name: Name to resolve
            
        Returns:
            Optional[str]: Full name if found
        """
        return self.name_to_full.get(name)
    
    def get_tool_info(self, name: str) -> Optional[ToolNameInfo]:
        """Get tool information by any name."""
        full_name = self.resolve_name(name)
        if full_name:
            return self.tool_names.get(full_name)
        return None
    
    def list_namespace_tools(self, namespace: str) -> List[str]:
        """List all tools in a namespace."""
        if namespace not in self.namespaces:
            return []
        
        return list(self.namespaces[namespace].tools)
    
    def list_namespace_aliases(self, namespace: str) -> Dict[str, str]:
        """List all aliases in a namespace."""
        if namespace not in self.namespaces:
            return {}
        
        return dict(self.namespaces[namespace].aliases)
    
    def get_namespace_hierarchy(self, namespace: str) -> Dict[str, Any]:
        """Get the complete hierarchy for a namespace."""
        if namespace not in self.namespaces:
            return {}
        
        info = self.namespaces[namespace]
        
        hierarchy = {
            "name": namespace,
            "info": info.to_dict(),
            "children": {}
        }
        
        # Add children recursively
        for child_name in info.children:
            hierarchy["children"][child_name] = self.get_namespace_hierarchy(child_name)
        
        return hierarchy
    
    def remove_tool(self, name: str) -> bool:
        """Remove a tool from all registries."""
        full_name = self.resolve_name(name)
        if not full_name or full_name not in self.tool_names:
            return False
        
        tool_info = self.tool_names[full_name]
        
        # Remove from namespace
        if tool_info.namespace and tool_info.namespace in self.namespaces:
            self.namespaces[tool_info.namespace].tools.discard(full_name)
            
            # Remove aliases from namespace
            namespace_info = self.namespaces[tool_info.namespace]
            aliases_to_remove = [
                alias for alias, target in namespace_info.aliases.items()
                if target == full_name
            ]
            for alias in aliases_to_remove:
                del namespace_info.aliases[alias]
        
        # Remove from name mappings
        names_to_remove = [
            n for n, fn in self.name_to_full.items()
            if fn == full_name
        ]
        for name_to_remove in names_to_remove:
            del self.name_to_full[name_to_remove]
        
        # Remove tool info
        del self.tool_names[full_name]
        
        logger.debug(f"Removed tool: {full_name}")
        return True
    
    def remove_namespace(self, namespace: str) -> bool:
        """Remove a namespace and all its tools."""
        if namespace not in self.namespaces:
            return False
        
        info = self.namespaces[namespace]
        
        # Remove all tools in the namespace
        tools_to_remove = list(info.tools)
        for tool_name in tools_to_remove:
            self.remove_tool(tool_name)
        
        # Remove from parent's children
        if info.parent and info.parent in self.namespaces:
            self.namespaces[info.parent].children.discard(namespace)
        
        # Update server mapping
        if info.server_name and info.server_name in self.server_namespaces:
            if self.server_namespaces[info.server_name] == namespace:
                del self.server_namespaces[info.server_name]
        
        # Remove namespace
        del self.namespaces[namespace]
        
        logger.info(f"Removed namespace: {namespace}")
        return True
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get namespace management statistics."""
        return {
            **self.stats,
            "total_namespaces": len(self.namespaces),
            "total_tools": len(self.tool_names),
            "total_aliases": sum(len(ns.aliases) for ns in self.namespaces.values()),
            "servers_mapped": len(self.server_namespaces),
            "active_conflicts": len(self.name_conflicts),
            "policy": {
                "conflict_resolution": self.policy.conflict_resolution.value,
                "allow_global_names": self.policy.allow_global_names,
                "require_namespaces": self.policy.require_namespaces,
                "auto_create_aliases": self.policy.auto_create_aliases
            }
        }