"""
Configuration management for SimaCode.

This module provides comprehensive configuration management using Pydantic models
for type safety and validation. Supports multiple configuration layers and
environment variable overrides.
"""

import os
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import yaml
from pydantic import BaseModel, Field, validator
from pydantic import ValidationError as PydanticValidationError

logger = logging.getLogger(__name__)


class LoggingConfig(BaseModel):
    """Logging configuration model."""
    
    level: str = Field(default="INFO", description="Log level")
    format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Log format string"
    )
    file_path: Optional[Path] = Field(
        default=None,
        description="Optional log file path"
    )
    max_file_size: int = Field(
        default=10 * 1024 * 1024,  # 10MB
        description="Maximum log file size in bytes"
    )
    backup_count: int = Field(
        default=5,
        description="Number of backup log files to keep"
    )
    
    @validator('level')
    def validate_log_level(cls, v: str) -> str:
        valid_levels = {'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'}
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v.upper()


class SecurityConfig(BaseModel):
    """Security configuration model."""
    
    allowed_paths: list[Path] = Field(
        default_factory=lambda: [Path.cwd()],
        description="List of allowed file system paths"
    )
    
    forbidden_paths: list[Path] = Field(
        default_factory=lambda: [
            Path("/etc"),
            Path("/sys"),
            Path("/proc"),
            Path("/dev"),
            Path.home() / ".ssh",
            Path.home() / ".gnupg"
        ],
        description="List of forbidden file system paths"
    )
    require_permission_for_write: bool = Field(
        default=True,
        description="Require explicit permission for file write operations"
    )
    max_command_execution_time: int = Field(
        default=300,
        description="Maximum time in seconds for command execution"
    )
    
    @validator('allowed_paths', 'forbidden_paths', pre=True)
    def convert_to_path_objects(cls, v: Union[str, list[str]]) -> list[Path]:
        if isinstance(v, str):
            return [Path(v).expanduser()]
        elif isinstance(v, list):
            return [Path(item).expanduser() if isinstance(item, str) else (item.expanduser() if hasattr(item, 'expanduser') else item) for item in v]
        return v


class AIConfig(BaseModel):
    """AI provider configuration model."""
    
    provider: str = Field(
        default="openai",
        description="AI provider name (openai, anthropic, etc.)"
    )
    api_key: Optional[str] = Field(
        default=None,
        description="API key for the AI provider"
    )
    base_url: Optional[str] = Field(
        default=None,
        description="Base URL for the AI API"
    )
    model: str = Field(
        default="gpt-4",
        description="AI model to use"
    )
    temperature: float = Field(
        default=0.1,
        ge=0.0,
        le=2.0,
        description="Model temperature parameter"
    )
    max_tokens: int = Field(
        default=4000,
        ge=1,
        le=128000,
        description="Maximum tokens for model response"
    )
    timeout: int = Field(
        default=60,
        ge=1,
        description="API timeout in seconds"
    )
    
    @validator('api_key', pre=True, always=True)
    def load_from_env(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return os.getenv("SIMACODE_API_KEY") or os.getenv("OPENAI_API_KEY")
        return v


class SessionConfig(BaseModel):
    """Session management configuration model."""
    
    save_sessions: bool = Field(
        default=True,
        description="Whether to save session history"
    )
    session_dir: Path = Field(
        default_factory=lambda: Path.home() / ".simacode" / "sessions",
        description="Directory to store session data"
    )
    max_sessions: int = Field(
        default=100,
        description="Maximum number of sessions to keep"
    )
    auto_cleanup: bool = Field(
        default=True,
        description="Automatically clean up old sessions"
    )
    
    @validator('session_dir', pre=True)
    def ensure_session_dir(cls, v: Union[str, Path]) -> Path:
        # Convert string to Path and expand ~ to user home directory
        if isinstance(v, str):
            path = Path(v).expanduser()
        else:
            path = v.expanduser() if hasattr(v, 'expanduser') else v
        path.mkdir(parents=True, exist_ok=True)
        return path


class ReactConfig(BaseModel):
    """ReAct 引擎配置模型"""
    
    confirm_by_human: bool = Field(
        default=False, 
        description="Enable human confirmation before task execution"
    )
    confirmation_timeout: int = Field(
        default=300, 
        description="Confirmation timeout in seconds"
    )
    allow_task_modification: bool = Field(
        default=True, 
        description="Allow users to modify tasks during confirmation"
    )
    auto_confirm_safe_tasks: bool = Field(
        default=False,
        description="Auto-confirm tasks that are considered safe"
    )


class DevelopmentConfig(BaseModel):
    """Development configuration model."""
    
    debug_mode: bool = Field(
        default=False,
        description="Enable debug mode for development"
    )
    profiling_enabled: bool = Field(
        default=False,
        description="Enable profiling for performance analysis"
    )
    test_mode: bool = Field(
        default=False,
        description="Enable test mode"
    )
    mock_ai_responses: bool = Field(
        default=False,
        description="Use mock AI responses for testing"
    )


class EmailSMTPConfig(BaseModel):
    """SMTP server configuration model."""
    
    server: Optional[str] = Field(
        default=None,
        description="SMTP server address"
    )
    port: int = Field(
        default=587,
        ge=1,
        le=65535,
        description="SMTP server port"
    )
    use_tls: bool = Field(
        default=True,
        description="Use TLS encryption"
    )
    use_ssl: bool = Field(
        default=False,
        description="Use SSL encryption"
    )
    timeout: int = Field(
        default=30,
        ge=1,
        le=300,
        description="Connection timeout in seconds"
    )
    username: Optional[str] = Field(
        default=None,
        description="SMTP username"
    )
    password: Optional[str] = Field(
        default=None,
        description="SMTP password"
    )
    
    @validator('username', pre=True, always=True)
    def load_username_from_env(cls, v: Optional[str]) -> Optional[str]:
        """Load SMTP username from environment variables if not provided."""
        if v is None:
            return os.getenv("SIMACODE_SMTP_USER")
        return v
    
    @validator('password', pre=True, always=True)
    def load_password_from_env(cls, v: Optional[str]) -> Optional[str]:
        """Load SMTP password from environment variables if not provided."""
        if v is None:
            return os.getenv("SIMACODE_SMTP_PASS")
        return v


class EmailIMAPConfig(BaseModel):
    """IMAP server configuration model."""
    
    server: Optional[str] = Field(
        default=None,
        description="IMAP server address"
    )
    port: int = Field(
        default=993,
        ge=1,
        le=65535,
        description="IMAP server port"
    )
    use_ssl: bool = Field(
        default=True,
        description="Use SSL encryption for IMAP"
    )
    timeout: int = Field(
        default=60,
        ge=1,
        le=300,
        description="Connection timeout in seconds"
    )
    username: Optional[str] = Field(
        default=None,
        description="IMAP username"
    )
    password: Optional[str] = Field(
        default=None,
        description="IMAP password"
    )


class EmailSecurityConfig(BaseModel):
    """Email security configuration model."""
    
    max_recipients: int = Field(
        default=50,
        ge=1,
        le=1000,
        description="Maximum number of recipients per email"
    )
    max_attachment_size: int = Field(
        default=26214400,  # 25MB
        ge=1024,  # 1KB minimum
        le=104857600,  # 100MB maximum
        description="Maximum attachment size in bytes"
    )
    max_body_size: int = Field(
        default=1048576,  # 1MB
        ge=1024,  # 1KB minimum
        le=10485760,  # 10MB maximum
        description="Maximum email body size in bytes"
    )
    allowed_domains: List[str] = Field(
        default_factory=list,
        description="Allowed recipient domains (empty = allow all)"
    )
    blocked_domains: List[str] = Field(
        default_factory=list,
        description="Blocked recipient domains"
    )
    allowed_attachment_types: List[str] = Field(
        default_factory=lambda: [".txt", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".jpeg", ".png", ".gif", ".json", ".csv", ".xml", ".zip"],
        description="Allowed attachment file types"
    )


class EmailRateLimitConfig(BaseModel):
    """Email rate limiting configuration model."""
    
    max_emails_per_hour: int = Field(
        default=100,
        ge=1,
        le=10000,
        description="Maximum emails per hour"
    )
    max_emails_per_day: int = Field(
        default=1000,
        ge=1,
        le=100000,
        description="Maximum emails per day"
    )


class EmailDefaultsConfig(BaseModel):
    """Email default settings configuration model."""
    
    from_name: str = Field(
        default="SimaCode Assistant",
        description="Default sender name"
    )
    from_email: Optional[str] = Field(
        default=None,
        description="Default sender email (will use username if not set)"
    )


class EmailConfig(BaseModel):
    """Email configuration model."""
    
    smtp: EmailSMTPConfig = Field(
        default_factory=EmailSMTPConfig,
        description="SMTP server configuration"
    )
    imap: EmailIMAPConfig = Field(
        default_factory=EmailIMAPConfig,
        description="IMAP server configuration"
    )
    security: EmailSecurityConfig = Field(
        default_factory=EmailSecurityConfig,
        description="Email security settings"
    )
    rate_limiting: EmailRateLimitConfig = Field(
        default_factory=EmailRateLimitConfig,
        description="Email rate limiting settings"
    )
    defaults: EmailDefaultsConfig = Field(
        default_factory=EmailDefaultsConfig,
        description="Email default settings"
    )


class MCPServerConfig(BaseModel):
    """MCP server configuration model matching .simacode/config.yaml structure."""
    
    name: Optional[str] = Field(default=None, description="Server name")
    enabled: bool = Field(default=True, description="Whether this server is enabled")
    description: Optional[str] = Field(default=None, description="Server description")
    timeout: Optional[int] = Field(default=None, description="Server timeout override")


class MCPConfig(BaseModel):
    """MCP (Model Context Protocol) configuration model."""
    
    enabled: bool = Field(default=True, description="Whether MCP integration is enabled")
    default_timeout: int = Field(default=300, description="Default timeout for MCP operations")
    auto_enable_new_tools: bool = Field(default=True, description="Auto-enable discovered tools")
    
    # This will hold merged server configurations
    servers: Dict[str, MCPServerConfig] = Field(
        default_factory=dict,
        description="Server configurations"
    )


class ConversationContextConfig(BaseModel):
    """Conversation context configuration model."""
    
    strategy: str = Field(
        default="compressed",
        description="Context strategy: full, compressed, adaptive"
    )
    
    # Full context settings
    max_messages: int = Field(default=100, description="Maximum messages to preserve")
    max_tokens: int = Field(default=8000, description="Maximum tokens limit")
    preserve_all: bool = Field(default=False, description="Preserve all messages")
    
    # Compressed context settings
    recent_messages: int = Field(default=5, description="Recent messages to preserve fully")
    medium_recent: int = Field(default=10, description="Medium recent messages count")
    compression_ratio: float = Field(default=0.3, ge=0.1, le=1.0, description="Compression ratio")
    preserve_topics: bool = Field(default=True, description="Preserve topic summaries")
    
    # Adaptive context settings
    token_budget: int = Field(default=4000, description="Token budget for adaptive mode")
    min_recent: int = Field(default=3, description="Minimum recent messages to preserve")
    auto_summarize: bool = Field(default=True, description="Auto-summarize old conversations")
    
    @validator('strategy', pre=True, always=True)
    def validate_strategy(cls, v: str) -> str:
        """确保策略值总是有效的"""
        if v is None or v == "":
            return "compressed"  # 默认策略
        if v.lower() not in {'full', 'compressed', 'adaptive'}:
            return "compressed"  # 未知策略回退到压缩模式
        return v.lower()


class Config(BaseModel):
    """Main configuration model for SimaCode."""
    
    
    project_name: str = Field(
        default="SimaCode Project",
        description="Project name for display purposes"
    )
    logging: LoggingConfig = Field(
        default_factory=LoggingConfig,
        description="Logging configuration"
    )
    security: SecurityConfig = Field(
        default_factory=SecurityConfig,
        description="Security and permission configuration"
    )
    ai: AIConfig = Field(
        default_factory=AIConfig,
        description="AI provider configuration"
    )
    session: SessionConfig = Field(
        default_factory=SessionConfig,
        description="Session management configuration"
    )
    conversation_context: ConversationContextConfig = Field(
        default_factory=ConversationContextConfig,
        description="Conversation context management configuration"
    )
    react: ReactConfig = Field(
        default_factory=ReactConfig,
        description="ReAct engine configuration"
    )
    development: DevelopmentConfig = Field(
        default_factory=DevelopmentConfig,
        description="Development configuration"
    )
    email: EmailConfig = Field(
        default_factory=EmailConfig,
        description="Email configuration"
    )
    mcp: MCPConfig = Field(
        default_factory=MCPConfig,
        description="MCP (Model Context Protocol) configuration"
    )
    
    @classmethod
    def load(
        cls,
        config_path: Optional[Path] = None,
        project_root: Optional[Path] = None
    ) -> "Config":
        """
        Load configuration from multiple sources in order of precedence:
        1. Provided config_path
        2. Project config file (.simacode/config.yaml)
        3. Default configuration
        
        Args:
            config_path: Optional explicit path to config file
            project_root: Optional project root directory
            
        Returns:
            Loaded configuration instance
        """
        if project_root is None:
            project_root = Path.cwd()
            
        # Load configuration from various sources in order of precedence
        config_data = {}
        
        # 1. First load default config as base
        default_config_primary = Path(__file__).parent / "default_config" / "default.yaml"
        default_config_secondary = Path.cwd() / ".simacode" / "default.yaml"

        if default_config_primary.exists():
            default_config = default_config_primary
        elif default_config_secondary.exists():
            default_config = default_config_secondary
        else:
            default_config = default_config_primary
        if not default_config.exists():
            logger.debug(f"No {default_config} found, skipping default configuration found")
        else:
            with open(default_config, encoding='utf-8') as f:
                default_data = yaml.safe_load(f) or {}
                config_data.update(default_data)
        
        # 2. Load from project config (overrides default)
        project_config = project_root / ".simacode" / "config.yaml"
        if not project_config.exists():
             logger.debug(f"No {project_config} found, skipping project configuration found")
        else:
            with open(project_config, encoding='utf-8') as f:
                project_data = yaml.safe_load(f) or {}
                config_data.update(project_data)
        
        # 3. Load from provided path (highest precedence)
        if config_path and config_path.exists():
            logger.debug(f"{config_path} found, load configuration")
            with open(config_path, encoding='utf-8') as f:
                config_data.update(yaml.safe_load(f) or {})
        
        # 5. Merge MCP server configuration
        config_data = cls._merge_mcp_configuration(config_data, project_root)
        
        try:
            return cls(**config_data)
        except PydanticValidationError as e:
            raise ValueError(f"Invalid configuration: {e}")
    
    @classmethod
    def _merge_mcp_configuration(cls, config_data: Dict[str, Any], project_root: Path) -> Dict[str, Any]:
        """
        Merge MCP configuration from default_config/mcp_servers.yaml with user configuration.
        
        Args:
            config_data: Current configuration data
            project_root: Project root directory
            
        Returns:
            Updated configuration data with merged MCP settings
        """
        try:
            # Check for project-specific MCP configuration first
            project_mcp_file = Path.cwd() / ".simacode" / "mcp_servers.yaml"
            if project_mcp_file.exists():
                mcp_servers_file = project_mcp_file
            else:
                # Fallback to default built-in configuration
                mcp_servers_file = Path(__file__).parent / "default_config" / "mcp_servers.yaml"
                if not mcp_servers_file.exists():
                    logger.debug(f"No {mcp_servers_file} found, skipping MCP server configuration merge")
                    return config_data
            
            with open(mcp_servers_file, encoding='utf-8') as f:
                mcp_servers_data = yaml.safe_load(f) or {}
            
            #logger.debug(f"Loaded MCP servers configuration from {mcp_servers_file}")
            
            # Initialize MCP config structure if not present
            if "mcp" not in config_data:
                config_data["mcp"] = {}
            
            user_mcp_config = config_data["mcp"]
            
            # Merge global MCP settings (from default_config/mcp_servers.yaml)
            if "mcp" in mcp_servers_data:
                server_global_config = mcp_servers_data["mcp"]
                for key, value in server_global_config.items():
                    if key not in user_mcp_config:
                        user_mcp_config[key] = value
                        #logger.debug(f"Added MCP global setting: {key} = {value}")
            
            # Initialize servers dict in user MCP config if not present
            if "servers" not in user_mcp_config:
                user_mcp_config["servers"] = {}
            
            # Process server definitions from default_config/mcp_servers.yaml
            if "servers" in mcp_servers_data:
                servers_from_file = mcp_servers_data["servers"]
                user_servers = user_mcp_config["servers"]
                
                for server_name, server_def in servers_from_file.items():
                    # Create base server config from mcp_servers.yaml
                    base_server_config = {
                        "name": server_def.get("name", server_name),
                        "enabled": server_def.get("enabled", False),  # Default to disabled
                        "description": f"{server_def.get('name', server_name)} server",
                        "timeout": server_def.get("timeout")
                    }
                    
                    # Check if user has specific configuration for this server
                    if server_name in user_servers:
                        # Deep merge user config over base config
                        user_server_config = user_servers[server_name]
                        merged_config = {**base_server_config}
                        
                        # Override with user settings
                        for key, value in user_server_config.items():
                            if value is not None:  # Only override non-None values
                                merged_config[key] = value
                                logger.debug(f"User override for {server_name}.{key}: {value}")
                        
                        user_servers[server_name] = merged_config
                    else:
                        # No user config for this server, use base config
                        user_servers[server_name] = base_server_config
                        #logger.debug(f"Added server from default_config/mcp_servers.yaml: {server_name}")
            
            # Also handle servers section at root level (legacy support)
            if "servers" in config_data:
                root_servers = config_data["servers"]
                user_mcp_servers = user_mcp_config["servers"]
                
                # Merge root-level servers into mcp.servers
                for server_name, server_config in root_servers.items():
                    if server_name in user_mcp_servers:
                        # Deep merge
                        existing_config = user_mcp_servers[server_name]
                        for key, value in server_config.items():
                            if value is not None:
                                existing_config[key] = value
                        #logger.debug(f"Merged root-level server config for {server_name}")
                    else:
                        user_mcp_servers[server_name] = server_config
                        logger.debug(f"Added root-level server config: {server_name}")
                
                # Remove root-level servers section after merging
                del config_data["servers"]
            
            logger.info(f"MCP configuration merged: {len(user_mcp_config['servers'])} servers configured")
            
            return config_data
            
        except Exception as e:
            logger.warning(f"Failed to merge MCP configuration: {str(e)}")
            return config_data
    
    def save_to_file(self, path: Path) -> None:
        """Save configuration to a YAML file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w") as f:
            yaml.safe_dump(
                self.model_dump(mode="json"),
                f,
                default_flow_style=False,
                indent=2,
                sort_keys=True
            )
    
    def validate(self) -> None:
        """Validate the entire configuration."""
        # Pydantic already validates on creation, but this provides explicit validation
        try:
            Config(**self.model_dump())
        except PydanticValidationError as e:
            raise ValueError(f"Configuration validation failed: {e}")
    
    def get_effective_value(self, key: str) -> Any:
        """
        Get effective value for a configuration key, considering environment overrides.
        
        Args:
            key: Configuration key path (e.g., "ai.api_key")
            
        Returns:
            Effective value for the key
        """
        parts = key.split(".")
        value = self
        
        try:
            for part in parts:
                if hasattr(value, part):
                    value = getattr(value, part)
                else:
                    return None
            return value
        except AttributeError:
            return None


class ConfigError(Exception):
    """Base exception for configuration-related errors."""
    pass


class ConfigValidationError(ConfigError):
    """Exception raised when configuration validation fails."""
    pass


class ConfigNotFoundError(ConfigError):
    """Exception raised when configuration file is not found."""
    pass
