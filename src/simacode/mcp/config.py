"""
MCP configuration management.

This module handles loading, validating, and managing MCP server configurations
from YAML files and environment variables.
"""

import logging
import os
import string
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml
from pydantic import BaseModel, Field, field_validator

from .exceptions import MCPConfigurationError
from ..utils.path_resolver import resolve_mcp_config_path

logger = logging.getLogger(__name__)


class MCPSecurityConfig(BaseModel):
    """Security configuration for MCP servers."""
    
    allowed_operations: List[str] = Field(default_factory=list)
    allowed_paths: List[str] = Field(default_factory=list)
    forbidden_paths: List[str] = Field(default_factory=list)
    max_execution_time: int = Field(default=300)  # 5 minutes
    network_access: bool = Field(default=True)
    
    @field_validator('allowed_paths', 'forbidden_paths')
    @classmethod
    def validate_paths(cls, v: List[str]) -> List[str]:
        """Validate and normalize paths."""
        normalized_paths = []
        for path in v:
            try:
                # Expand user and environment variables
                expanded_path = os.path.expanduser(os.path.expandvars(path))
                normalized_path = os.path.abspath(expanded_path)
                normalized_paths.append(normalized_path)
            except Exception as e:
                raise ValueError(f"Invalid path '{path}': {str(e)}")
        return normalized_paths


class MCPServerConfig(BaseModel):
    """Configuration for a single MCP server."""
    
    name: str = Field(..., description="Unique server name")
    enabled: bool = Field(default=True)
    type: str = Field(default="stdio", description="Transport type: stdio, websocket, or embedded")
    command: List[str] = Field(default_factory=list, description="Command to start server (for stdio/websocket)")
    args: List[str] = Field(default_factory=list)
    url: Optional[str] = Field(default=None, description="WebSocket URL for websocket type")
    headers: Dict[str, str] = Field(default_factory=dict, description="HTTP headers for websocket connection")
    module_path: Optional[str] = Field(default=None, description="Module path for embedded servers (e.g., tools.mcp_smtp_send_email)")
    main_function: Optional[str] = Field(default="main", description="Main function name for embedded servers")
    environment: Dict[str, str] = Field(default_factory=dict)
    working_directory: Optional[str] = None
    timeout: int = Field(default=30, ge=1, le=300)
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_delay: float = Field(default=1.0, ge=0.1, le=60.0)
    security: MCPSecurityConfig = Field(default_factory=MCPSecurityConfig)
    
    @field_validator('command')
    @classmethod
    def validate_command(cls, v: List[str], info) -> List[str]:
        """Validate command list."""
        server_type = info.data.get('type', 'stdio')

        # For websocket and embedded servers, command can be empty
        if server_type in ['websocket', 'embedded']:
            return v

        # For stdio servers, command is required
        if server_type == 'stdio':
            if not v:
                raise ValueError("Command cannot be empty for stdio servers")

            # Check if first element (executable) exists
            executable = v[0]
            if not executable:
                raise ValueError("Executable name cannot be empty")

        return v

    @field_validator('module_path')
    @classmethod
    def validate_module_path(cls, v: Optional[str], info) -> Optional[str]:
        """Validate module path for embedded servers."""
        server_type = info.data.get('type', 'stdio')

        # For embedded servers, module_path is required
        if server_type == 'embedded':
            if not v:
                raise ValueError("module_path is required for embedded servers")

        return v

    @field_validator('environment')
    @classmethod
    def validate_environment(cls, v: Dict[str, str]) -> Dict[str, str]:
        """Validate and expand environment variables."""
        expanded_env = {}
        for key, value in v.items():
            try:
                # Expand environment variables in values
                expanded_value = os.path.expandvars(value)
                expanded_env[key] = expanded_value
            except Exception as e:
                raise ValueError(f"Invalid environment variable '{key}={value}': {str(e)}")
        return expanded_env
    
    @field_validator('working_directory')
    @classmethod
    def validate_working_directory(cls, v: Optional[str]) -> Optional[str]:
        """Validate working directory."""
        if v is not None:
            expanded_path = os.path.expanduser(os.path.expandvars(v))
            if not os.path.isdir(expanded_path):
                raise ValueError(f"Working directory does not exist: {expanded_path}")
            return os.path.abspath(expanded_path)
        return v


class MCPGlobalConfig(BaseModel):
    """Global MCP configuration."""
    
    enabled: bool = Field(default=True)
    timeout: int = Field(default=30, ge=1, le=300)
    max_concurrent: int = Field(default=10, ge=1, le=100)
    log_level: str = Field(default="INFO")
    cache_ttl: int = Field(default=300, ge=0)  # 5 minutes
    health_check_interval: int = Field(default=30, ge=10)  # 30 seconds
    
    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level. Must be one of: {valid_levels}")
        return v.upper()


class MCPConfig(BaseModel):
    """Complete MCP configuration."""
    
    mcp: MCPGlobalConfig = Field(default_factory=MCPGlobalConfig)
    servers: Dict[str, MCPServerConfig] = Field(default_factory=dict)
    
    def get_enabled_servers(self) -> Dict[str, MCPServerConfig]:
        """Get only enabled servers."""
        return {
            name: config for name, config in self.servers.items()
            if config.enabled and self.mcp.enabled
        }
    
    def get_server_config(self, server_name: str) -> Optional[MCPServerConfig]:
        """Get configuration for a specific server."""
        return self.servers.get(server_name)
    
    def add_server(self, server_config: MCPServerConfig) -> None:
        """Add a new server configuration."""
        if server_config.name in self.servers:
            raise MCPConfigurationError(
                f"Server '{server_config.name}' already exists",
                config_field="servers"
            )
        self.servers[server_config.name] = server_config
    
    def remove_server(self, server_name: str) -> bool:
        """Remove a server configuration."""
        if server_name in self.servers:
            del self.servers[server_name]
            return True
        return False


class MCPConfigManager:
    """Manager for loading and managing MCP configurations."""
    
    def __init__(self, config_path: Optional[Union[str, Path]] = None):
        self.config_path = self._resolve_config_path(config_path)
        self.config: Optional[MCPConfig] = None
        self._template_engine = EnvironmentTemplateEngine()
    
    def _resolve_config_path(self, config_path: Optional[Union[str, Path]]) -> Path:
        """
        Resolve MCP configuration file path.

        Args:
            config_path: Optional explicit path to config file

        Returns:
            Path: Resolved path to mcp_servers.yaml
        """
        return resolve_mcp_config_path(config_path)
    
    def _resolve_user_config_path(self) -> Path:
        """Resolve project configuration file path (.simacode/config.yaml)."""
        # Only use project-level config
        project_config = Path.cwd() / ".simacode" / "config.yaml"
        return project_config
    
    def _merge_config_data(self, default_data: Dict[str, Any], user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Merge user configuration data with default data."""
        merged_data = default_data.copy()
        
        # Handle MCP global settings merge
        if "mcp" in user_data:
            if "mcp" in merged_data:
                merged_data["mcp"].update(user_data["mcp"])
            else:
                merged_data["mcp"] = user_data["mcp"]
        
        # Handle server-specific configurations
        if "servers" in user_data:
            if "servers" not in merged_data:
                merged_data["servers"] = {}
            
            for server_name, user_server_config in user_data["servers"].items():
                if server_name in merged_data["servers"]:
                    # Merge with existing server config
                    merged_server_config = merged_data["servers"][server_name].copy()
                    
                    # Handle nested dictionaries like environment and security
                    for key, value in user_server_config.items():
                        if key == "environment" and isinstance(value, dict):
                            if "environment" in merged_server_config:
                                merged_server_config["environment"].update(value)
                            else:
                                merged_server_config["environment"] = value
                        elif key == "security" and isinstance(value, dict):
                            if "security" in merged_server_config:
                                merged_server_config["security"].update(value)
                            else:
                                merged_server_config["security"] = value
                        elif key == "headers" and isinstance(value, dict):
                            if "headers" in merged_server_config:
                                merged_server_config["headers"].update(value)
                            else:
                                merged_server_config["headers"] = value
                        else:
                            # Direct override for simple values
                            merged_server_config[key] = value
                    
                    merged_data["servers"][server_name] = merged_server_config
                else:
                    # Add new server configuration
                    merged_data["servers"][server_name] = user_server_config
        
        return merged_data
    
    async def load_config(self) -> MCPConfig:
        """Load MCP configuration from file with user config merging."""
        try:
            # Load default configuration first
            default_config_data = {}
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    raw_data = f.read()
                
                # Process templates (environment variables)
                processed_data = self._template_engine.process(raw_data)
                default_config_data = yaml.safe_load(processed_data) or {}
            else:
                # Create default configuration if it doesn't exist
                self.config = MCPConfig()
                await self.save_config()
                return self.config
            
            # Load user configuration for overrides
            user_config_path = self._resolve_user_config_path()
            logger.info(f"User config path: {user_config_path}")
            user_config_data = {}
            
            if user_config_path.exists():
                try:
                    with open(user_config_path, 'r', encoding='utf-8') as f:
                        raw_user_data = f.read()
                    
                    # Process templates in user config too
                    processed_user_data = self._template_engine.process(raw_user_data)
                    loaded_user_data = yaml.safe_load(processed_user_data) or {}
                    
                    # Extract MCP-related configuration from user config
                    if "mcp" in loaded_user_data:
                        user_config_data["mcp"] = loaded_user_data["mcp"]
                    
                    # Look for MCP server configurations in user config
                    if "mcp_servers" in loaded_user_data:
                        user_config_data["servers"] = loaded_user_data["mcp_servers"]
                    
                    # Also check for servers section directly
                    if "servers" in loaded_user_data:
                        if "servers" not in user_config_data:
                            user_config_data["servers"] = loaded_user_data["servers"]
                        else:
                            # Merge both servers sections if they exist
                            user_config_data["servers"].update(loaded_user_data["servers"])
                            
                except Exception as e:
                    # Log warning but don't fail - continue with default config only
                    logger.warning(f"Failed to load user config from {user_config_path}: {str(e)}")
            
            # Merge configurations
            final_config_data = self._merge_config_data(default_config_data, user_config_data)
            
            # Parse and validate configuration
            self.config = MCPConfig(**final_config_data)
            return self.config
            
        except yaml.YAMLError as e:
            raise MCPConfigurationError(
                f"Invalid YAML in configuration file: {str(e)}",
                config_field="yaml_syntax"
            )
        except Exception as e:
            raise MCPConfigurationError(
                f"Failed to load configuration: {str(e)}"
            )
    
    async def save_config(self, config: Optional[MCPConfig] = None) -> None:
        """Save MCP configuration to file."""
        config_to_save = config or self.config
        if not config_to_save:
            raise MCPConfigurationError("No configuration to save")
        
        try:
            # Ensure directory exists
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert to dict and save
            config_dict = config_to_save.model_dump(exclude_unset=False)
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(
                    config_dict,
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                    indent=2
                )
            
            self.config = config_to_save
            
        except Exception as e:
            raise MCPConfigurationError(
                f"Failed to save configuration to {self.config_path}: {str(e)}"
            )
    
    def get_config(self) -> Optional[MCPConfig]:
        """Get current configuration."""
        return self.config
    
    def create_default_config(self) -> MCPConfig:
        """Create a default configuration with example servers."""
        config = MCPConfig(
            mcp=MCPGlobalConfig(
                enabled=True,
                timeout=30,
                max_concurrent=5,
                log_level="INFO"
            ),
            servers={
                "filesystem": MCPServerConfig(
                    name="filesystem",
                    enabled=False,  # Disabled by default
                    type="stdio",
                    command=["python", "-m", "mcp_server_filesystem"],
                    args=["--root", "${WORKSPACE_ROOT:-/tmp}"],
                    environment={
                        "WORKSPACE_ROOT": "${WORKSPACE_ROOT:-/tmp}"
                    },
                    security=MCPSecurityConfig(
                        allowed_paths=["${WORKSPACE_ROOT:-/tmp}", "/tmp"],
                        forbidden_paths=["/etc", "/usr", "/sys", "/proc"],
                        max_execution_time=60
                    )
                ),
                "github": MCPServerConfig(
                    name="github",
                    enabled=False,  # Disabled by default
                    type="stdio", 
                    command=["npx", "@modelcontextprotocol/server-github"],
                    args=["--token", "${GITHUB_TOKEN}"],
                    environment={
                        "GITHUB_TOKEN": "${GITHUB_TOKEN}"
                    },
                    security=MCPSecurityConfig(
                        allowed_operations=[
                            "read_repository", "list_issues", "list_pull_requests"
                        ],
                        network_access=True,
                        max_execution_time=120
                    )
                )
            }
        )
        return config


class EnvironmentTemplateEngine:
    """Simple template engine for environment variable substitution with default values."""
    
    def process(self, template_text: str) -> str:
        """Process template text and substitute environment variables with default value support."""
        try:
            import re
            
            # Pattern to match ${VAR:-default} or ${VAR}
            pattern = r'\$\{([^}]+)\}'
            
            def substitute_var(match):
                var_expr = match.group(1)
                
                # Check if it has a default value (VAR:-default)
                if ':-' in var_expr:
                    var_name, default_value = var_expr.split(':-', 1)
                    return os.getenv(var_name.strip(), default_value.strip())
                else:
                    # Simple variable substitution
                    return os.getenv(var_expr.strip(), match.group(0))  # Keep original if not found
            
            # Replace all variable expressions
            result = re.sub(pattern, substitute_var, template_text)
            
            # Also handle simple $VAR syntax
            template = string.Template(result)
            env_vars = dict(os.environ)
            return template.safe_substitute(env_vars)
            
        except Exception as e:
            raise MCPConfigurationError(
                f"Template processing failed: {str(e)}",
                config_field="template"
            )


# Utility functions for configuration management
async def load_mcp_config(config_path: Optional[Union[str, Path]] = None) -> MCPConfig:
    """Load MCP configuration from file."""
    manager = MCPConfigManager(config_path)
    return await manager.load_config()


def validate_server_config(config_dict: Dict[str, Any]) -> MCPServerConfig:
    """Validate a server configuration dictionary."""
    try:
        return MCPServerConfig(**config_dict)
    except Exception as e:
        raise MCPConfigurationError(
            f"Invalid server configuration: {str(e)}",
            config_field="server_config"
        )