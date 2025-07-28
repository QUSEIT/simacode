"""
MCP tool discovery and management.

This module provides comprehensive tool discovery mechanisms for MCP servers,
including tool indexing, searching, and metadata management.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Set, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import time

from .protocol import MCPTool, MCPResource, MCPPrompt
from .exceptions import MCPConnectionError, MCPToolNotFoundError

logger = logging.getLogger(__name__)


@dataclass
class ToolMetadata:
    """Extended metadata for discovered tools."""
    
    tool: MCPTool
    server_name: str
    discovered_at: datetime
    last_used: Optional[datetime] = None
    usage_count: int = 0
    success_rate: float = 1.0
    average_execution_time: float = 0.0
    tags: Set[str] = field(default_factory=set)
    capabilities: Dict[str, Any] = field(default_factory=dict)
    
    def update_usage_stats(self, success: bool, execution_time: float) -> None:
        """Update tool usage statistics."""
        self.last_used = datetime.now()
        self.usage_count += 1
        
        # Update success rate (exponential moving average)
        alpha = 0.1
        if success:
            self.success_rate = (1 - alpha) * self.success_rate + alpha * 1.0
        else:
            self.success_rate = (1 - alpha) * self.success_rate + alpha * 0.0
        
        # Update average execution time (exponential moving average)
        if execution_time > 0:
            self.average_execution_time = (
                (1 - alpha) * self.average_execution_time + alpha * execution_time
            )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "tool": {
                "name": self.tool.name,
                "description": self.tool.description,
                "server_name": self.tool.server_name,
                "input_schema": self.tool.input_schema
            },
            "server_name": self.server_name,
            "discovered_at": self.discovered_at.isoformat(),
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "usage_count": self.usage_count,
            "success_rate": self.success_rate,
            "average_execution_time": self.average_execution_time,
            "tags": list(self.tags),
            "capabilities": self.capabilities
        }


class MCPToolDiscovery:
    """
    Tool discovery and management system for MCP servers.
    
    This class provides comprehensive tool discovery, indexing, searching,
    and metadata management across multiple MCP servers.
    """
    
    def __init__(self, cache_ttl: int = 300):
        self.cache_ttl = cache_ttl  # 5 minutes default
        
        # Tool discovery and indexing
        self.tools_index: Dict[str, ToolMetadata] = {}  # tool_name -> metadata
        self.server_tools: Dict[str, Set[str]] = {}  # server_name -> set of tool names
        self.category_tools: Dict[str, Set[str]] = {}  # category -> set of tool names
        
        # Resource and prompt discovery
        self.resources_index: Dict[str, Dict[str, MCPResource]] = {}  # server_name -> resources
        self.prompts_index: Dict[str, Dict[str, MCPPrompt]] = {}  # server_name -> prompts
        
        # Discovery tracking
        self.last_discovery: Dict[str, float] = {}  # server_name -> timestamp
        self.discovery_locks: Dict[str, asyncio.Lock] = {}
        self.discovery_in_progress: Set[str] = set()
        
        # Performance optimization
        self.search_cache: Dict[str, Tuple[List[ToolMetadata], float]] = {}
        self.search_cache_ttl = 60  # 1 minute for search results
    
    async def discover_server_tools(self, server_name: str, client) -> List[MCPTool]:
        """
        Discover all tools from a specific MCP server.
        
        Args:
            server_name: Name of the MCP server
            client: MCPClient instance for the server
            
        Returns:
            List[MCPTool]: List of discovered tools
        """
        if server_name in self.discovery_locks:
            lock = self.discovery_locks[server_name]
        else:
            lock = asyncio.Lock()
            self.discovery_locks[server_name] = lock
        
        async with lock:
            # Check if discovery is needed
            if self._is_discovery_fresh(server_name):
                # Return cached tools
                return [
                    metadata.tool for tool_name in self.server_tools.get(server_name, set())
                    for metadata in [self.tools_index.get(tool_name)]
                    if metadata
                ]
            
            try:
                self.discovery_in_progress.add(server_name)
                logger.info(f"Discovering tools from server '{server_name}'")
                
                # Get tools from server
                tools = await client.list_tools()
                
                # Update index
                await self._update_tools_index(server_name, tools)
                
                # Mark discovery as complete
                self.last_discovery[server_name] = time.time()
                
                logger.info(f"Discovered {len(tools)} tools from server '{server_name}'")
                return tools
                
            except Exception as e:
                logger.error(f"Failed to discover tools from server '{server_name}': {str(e)}")
                raise MCPConnectionError(f"Tool discovery failed for server '{server_name}': {str(e)}")
            
            finally:
                self.discovery_in_progress.discard(server_name)
    
    async def discover_all_tools(self, server_manager) -> Dict[str, List[MCPTool]]:
        """
        Discover tools from all connected MCP servers.
        
        Args:
            server_manager: MCPServerManager instance
            
        Returns:
            Dict[str, List[MCPTool]]: Mapping of server names to their tools
        """
        all_tools = {}
        discovery_tasks = []
        
        # Create discovery tasks for all servers
        for server_name, client in server_manager.servers.items():
            if client.is_connected():
                task = asyncio.create_task(
                    self.discover_server_tools(server_name, client),
                    name=f"discover_{server_name}"
                )
                discovery_tasks.append((server_name, task))
        
        # Wait for all discoveries to complete
        if discovery_tasks:
            results = await asyncio.gather(
                *[task for _, task in discovery_tasks],
                return_exceptions=True
            )
            
            for (server_name, task), result in zip(discovery_tasks, results):
                if isinstance(result, Exception):
                    logger.error(f"Tool discovery failed for '{server_name}': {str(result)}")
                    all_tools[server_name] = []
                else:
                    all_tools[server_name] = result
        
        return all_tools
    
    async def find_tools_by_name(self, tool_name: str, fuzzy: bool = False) -> List[ToolMetadata]:
        """
        Find tools by name (exact or fuzzy match).
        
        Args:
            tool_name: Name of the tool to find
            fuzzy: Whether to perform fuzzy matching
            
        Returns:
            List[ToolMetadata]: List of matching tool metadata
        """
        # Check search cache first
        cache_key = f"name:{tool_name}:fuzzy:{fuzzy}"
        if cache_key in self.search_cache:
            cached_result, cache_time = self.search_cache[cache_key]
            if time.time() - cache_time < self.search_cache_ttl:
                return cached_result
        
        matches = []
        
        if fuzzy:
            # Fuzzy matching using simple similarity
            for name, metadata in self.tools_index.items():
                if self._calculate_similarity(tool_name.lower(), name.lower()) > 0.6:
                    matches.append(metadata)
        else:
            # Exact match
            if tool_name in self.tools_index:
                matches.append(self.tools_index[tool_name])
        
        # Sort by usage statistics and success rate
        matches.sort(key=lambda m: (m.success_rate, m.usage_count), reverse=True)
        
        # Cache results
        self.search_cache[cache_key] = (matches, time.time())
        
        return matches
    
    async def find_tools_by_description(self, keywords: List[str]) -> List[ToolMetadata]:
        """
        Find tools by description keywords.
        
        Args:
            keywords: List of keywords to search for
            
        Returns:
            List[ToolMetadata]: List of matching tool metadata
        """
        cache_key = f"desc:{':'.join(sorted(keywords))}"
        if cache_key in self.search_cache:
            cached_result, cache_time = self.search_cache[cache_key]
            if time.time() - cache_time < self.search_cache_ttl:
                return cached_result
        
        matches = []
        keywords_lower = [k.lower() for k in keywords]
        
        for metadata in self.tools_index.values():
            description = metadata.tool.description.lower()
            tool_name = metadata.tool.name.lower()
            
            # Calculate match score
            score = 0
            for keyword in keywords_lower:
                if keyword in description:
                    score += 2  # Description match worth more
                elif keyword in tool_name:
                    score += 1  # Name match
                
                # Check tags
                for tag in metadata.tags:
                    if keyword in tag.lower():
                        score += 1
            
            if score > 0:
                matches.append((metadata, score))
        
        # Sort by score, then by usage statistics
        matches.sort(key=lambda x: (x[1], x[0].success_rate, x[0].usage_count), reverse=True)
        result = [metadata for metadata, _ in matches]
        
        # Cache results
        self.search_cache[cache_key] = (result, time.time())
        
        return result
    
    async def find_tools_by_category(self, category: str) -> List[ToolMetadata]:
        """
        Find tools by category.
        
        Args:
            category: Category name
            
        Returns:
            List[ToolMetadata]: List of tools in the category
        """
        tool_names = self.category_tools.get(category, set())
        return [
            self.tools_index[name] for name in tool_names
            if name in self.tools_index
        ]
    
    async def get_tool_recommendations(self, context: Dict[str, Any]) -> List[ToolMetadata]:
        """
        Get tool recommendations based on context.
        
        Args:
            context: Context information for recommendations
            
        Returns:
            List[ToolMetadata]: Recommended tools
        """
        recommendations = []
        
        # Get recently used tools
        recent_tools = [
            metadata for metadata in self.tools_index.values()
            if metadata.last_used and 
            datetime.now() - metadata.last_used < timedelta(hours=1)
        ]
        recent_tools.sort(key=lambda m: m.last_used, reverse=True)
        recommendations.extend(recent_tools[:5])
        
        # Get high success rate tools
        successful_tools = [
            metadata for metadata in self.tools_index.values()
            if metadata.success_rate > 0.8 and metadata.usage_count >= 3
        ]
        successful_tools.sort(key=lambda m: m.success_rate, reverse=True)
        recommendations.extend(successful_tools[:5])
        
        # Remove duplicates while preserving order
        seen = set()
        unique_recommendations = []
        for tool in recommendations:
            if tool.tool.name not in seen:
                seen.add(tool.tool.name)
                unique_recommendations.append(tool)
        
        return unique_recommendations[:10]  # Return top 10
    
    def get_discovery_stats(self) -> Dict[str, Any]:
        """Get tool discovery statistics."""
        total_tools = len(self.tools_index)
        
        # Calculate server distribution
        server_distribution = {}
        for server_name, tool_names in self.server_tools.items():
            server_distribution[server_name] = len(tool_names)
        
        # Calculate category distribution
        category_distribution = {}
        for category, tool_names in self.category_tools.items():
            category_distribution[category] = len(tool_names)
        
        # Calculate usage statistics
        used_tools = [m for m in self.tools_index.values() if m.usage_count > 0]
        avg_success_rate = sum(m.success_rate for m in used_tools) / len(used_tools) if used_tools else 0
        
        return {
            "total_tools": total_tools,
            "total_servers": len(self.server_tools),
            "server_distribution": server_distribution,
            "category_distribution": category_distribution,
            "used_tools_count": len(used_tools),
            "average_success_rate": avg_success_rate,
            "cache_entries": len(self.search_cache),
            "discovery_in_progress": list(self.discovery_in_progress)
        }
    
    async def refresh_tool_cache(self, server_name: Optional[str] = None) -> None:
        """
        Refresh tool cache for specific server or all servers.
        
        Args:
            server_name: Server to refresh, or None for all servers
        """
        if server_name:
            # Refresh specific server
            if server_name in self.last_discovery:
                del self.last_discovery[server_name]
            # Clear related cache entries
            self._clear_search_cache()
        else:
            # Refresh all servers
            self.last_discovery.clear()
            self._clear_search_cache()
    
    def record_tool_usage(self, tool_name: str, success: bool, execution_time: float) -> None:
        """
        Record tool usage statistics.
        
        Args:
            tool_name: Name of the tool used
            success: Whether the tool execution was successful
            execution_time: Tool execution time in seconds
        """
        if tool_name in self.tools_index:
            self.tools_index[tool_name].update_usage_stats(success, execution_time)
    
    def _is_discovery_fresh(self, server_name: str) -> bool:
        """Check if discovery data is still fresh for a server."""
        if server_name not in self.last_discovery:
            return False
        
        last_time = self.last_discovery[server_name]
        return time.time() - last_time < self.cache_ttl
    
    async def _update_tools_index(self, server_name: str, tools: List[MCPTool]) -> None:
        """Update the tools index with discovered tools."""
        # Remove old tools for this server
        old_tool_names = self.server_tools.get(server_name, set())
        for old_tool_name in old_tool_names:
            if old_tool_name in self.tools_index:
                old_metadata = self.tools_index[old_tool_name]
                # Remove from category index
                for category, category_tools in self.category_tools.items():
                    category_tools.discard(old_tool_name)
                # Remove from main index
                del self.tools_index[old_tool_name]
        
        # Add new tools
        new_tool_names = set()
        for tool in tools:
            # Create or update metadata
            if tool.name in self.tools_index:
                # Update existing tool metadata
                metadata = self.tools_index[tool.name]
                metadata.tool = tool
                metadata.discovered_at = datetime.now()
            else:
                # Create new metadata
                metadata = ToolMetadata(
                    tool=tool,
                    server_name=server_name,
                    discovered_at=datetime.now()
                )
                self.tools_index[tool.name] = metadata
            
            # Categorize tool
            await self._categorize_tool(metadata)
            new_tool_names.add(tool.name)
        
        # Update server tools mapping
        self.server_tools[server_name] = new_tool_names
        
        # Clear search cache as it may be outdated
        self._clear_search_cache()
    
    async def _categorize_tool(self, metadata: ToolMetadata) -> None:
        """Automatically categorize a tool based on its name and description."""
        tool_name = metadata.tool.name.lower()
        description = metadata.tool.description.lower()
        
        # Category mappings
        categories = {
            "file": ["file", "read", "write", "directory", "folder", "path"],
            "git": ["git", "repository", "commit", "branch", "merge"],
            "database": ["db", "database", "sql", "query", "table"],
            "network": ["http", "api", "request", "url", "web", "fetch"],
            "system": ["system", "process", "command", "shell", "exec"],
            "text": ["text", "string", "format", "parse", "regex"],
            "analysis": ["analyze", "check", "validate", "inspect", "audit"],
            "development": ["code", "build", "compile", "test", "debug"]
        }
        
        tool_tags = set()
        
        # Categorize based on keywords
        for category, keywords in categories.items():
            for keyword in keywords:
                if keyword in tool_name or keyword in description:
                    tool_tags.add(category)
                    
                    # Add to category index
                    if category not in self.category_tools:
                        self.category_tools[category] = set()
                    self.category_tools[category].add(metadata.tool.name)
        
        # Update tool tags
        metadata.tags.update(tool_tags)
    
    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate simple string similarity using substring matching."""
        if not str1 or not str2:
            return 0.0
        
        str1_lower = str1.lower()
        str2_lower = str2.lower()
        
        # Check for substring matches
        if str1_lower in str2_lower or str2_lower in str1_lower:
            return 0.8
        
        # Fallback to Jaccard similarity for word-based matching
        set1 = set(str1_lower.split())
        set2 = set(str2_lower.split())
        
        intersection = len(set1.intersection(set2))
        union = len(set1.union(set2))
        
        return intersection / union if union > 0 else 0.0
    
    def _clear_search_cache(self) -> None:
        """Clear the search results cache."""
        self.search_cache.clear()