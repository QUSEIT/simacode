"""
Configuration management for Universal OCR Tool.

This module handles loading and managing configuration from .simacode/config.yaml
including Claude AI, OpenAI, and other OCR engine configurations.
"""

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class ClaudeConfig:
    """Claude AI configuration"""
    provider: str = "anthropic"
    api_key: Optional[str] = None
    base_url: str = "https://api.anthropic.com"
    model: str = "claude-3-5-sonnet-20241022"
    temperature: float = 0.1
    max_tokens: int = 4000
    timeout: int = 60


@dataclass
class OpenAIConfig:
    """OpenAI configuration"""
    provider: str = "openai"
    api_key: Optional[str] = None
    model: str = "gpt-4-vision-preview"
    temperature: float = 0.1
    max_tokens: int = 4000
    timeout: int = 60


@dataclass
class OCREngineConfig:
    """OCR engine configuration"""
    enabled: bool = True
    priority: int = 1
    config: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CacheConfig:
    """Cache configuration"""
    enabled: bool = True
    backend: str = "memory"  # memory, redis
    ttl: int = 3600
    max_size: int = 1000


@dataclass
class TemplateConfig:
    """Template configuration"""
    builtin_dir: str = "templates/builtin"
    user_dir: str = "templates/user"
    cache_dir: str = "templates/cache"
    auto_learning: bool = True


@dataclass
class OCRConfig:
    """Main OCR configuration class"""
    claude: ClaudeConfig = field(default_factory=ClaudeConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    engines: Dict[str, OCREngineConfig] = field(default_factory=dict)
    cache: CacheConfig = field(default_factory=CacheConfig)
    templates: TemplateConfig = field(default_factory=TemplateConfig)
    
    # File processing limits
    supported_formats: list = field(default_factory=lambda: ['.jpg', '.jpeg', '.png', '.pdf', '.gif', '.webp'])
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    
    def __post_init__(self):
        """Initialize default engine configurations"""
        if not self.engines:
            self.engines = {
                "claude": OCREngineConfig(enabled=True, priority=1),
                "paddleocr": OCREngineConfig(
                    enabled=True, 
                    priority=2,
                    config={"use_angle_cls": True, "lang": "ch"}
                ),
                "tesseract": OCREngineConfig(
                    enabled=True,
                    priority=3,
                    config={"lang": "chi_sim+eng"}
                )
            }


class ConfigManager:
    """Configuration manager for Universal OCR"""
    
    def __init__(self):
        self.config: Optional[OCRConfig] = None

        # Determine default config path - prioritize existing files
        default_config_primary = Path(__file__).parent.parent.parent / "default_config" / "default.yaml"
        default_config_secondary = Path.cwd() / ".simacode" / "default.yaml"

        if default_config_primary.exists():
            default_config = default_config_primary
        elif default_config_secondary.exists():
            default_config = default_config_secondary
        else:
            default_config = default_config_primary

        self._config_paths = [
            default_config,  # Default config
            Path.cwd() / ".simacode" / "config.yaml"  # Project config (overrides default)
        ]
    
    def load_config(self) -> OCRConfig:
        """Load configuration from files and environment variables"""
        if self.config is not None:
            return self.config
        
        # Start with defaults
        config_data = {}
        
        # Load from config files (default first, then project overrides)
        for config_path in self._config_paths:
            if config_path.exists():
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        file_config = yaml.safe_load(f) or {}
                        config_data.update(file_config)
                except Exception as e:
                    print(f"Warning: Failed to load config from {config_path}: {e}")
        
        # Override with environment variables
        env_config = self._load_from_env()
        if env_config:
            config_data.update(env_config)
        
        self.config = self._parse_config(config_data)
        return self.config
    
    def _load_from_env(self) -> Dict[str, Any]:
        """Load configuration from environment variables"""
        env_config = {}
        
        # Claude configuration
        if os.getenv("ANTHROPIC_API_KEY"):
            env_config["ocr_claudeai"] = {
                "api_key": os.getenv("ANTHROPIC_API_KEY"),
                "base_url": os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com"),
                "model": os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
            }
        
        # OpenAI configuration
        if os.getenv("OPENAI_API_KEY"):
            env_config["ocr_openai"] = {
                "api_key": os.getenv("OPENAI_API_KEY"),
                "model": os.getenv("OPENAI_MODEL", "gpt-4-vision-preview")
            }
        
        # Cache configuration
        if os.getenv("REDIS_URL"):
            env_config["cache"] = {
                "backend": "redis",
                "url": os.getenv("REDIS_URL"),
                "ttl": int(os.getenv("OCR_CACHE_TTL", "3600"))
            }
        
        return env_config
    
    def _parse_config(self, config_data: Dict[str, Any]) -> OCRConfig:
        """Parse configuration data into OCRConfig object"""
        config = OCRConfig()
        
        # Parse Claude configuration
        if "ocr_claudeai" in config_data:
            claude_data = config_data["ocr_claudeai"]
            config.claude = ClaudeConfig(
                api_key=claude_data.get("api_key"),
                base_url=claude_data.get("base_url", "https://api.anthropic.com"),
                model=claude_data.get("model", "claude-3-5-sonnet-20241022"),
                temperature=claude_data.get("temperature", 0.1),
                max_tokens=claude_data.get("max_tokens", 4000),
                timeout=claude_data.get("timeout", 60)
            )
        
        # Parse OpenAI configuration
        if "ocr_openai" in config_data:
            openai_data = config_data["ocr_openai"]
            config.openai = OpenAIConfig(
                api_key=openai_data.get("api_key"),
                model=openai_data.get("model", "gpt-4-vision-preview"),
                temperature=openai_data.get("temperature", 0.1),
                max_tokens=openai_data.get("max_tokens", 4000),
                timeout=openai_data.get("timeout", 60)
            )
        
        # Parse engine configurations
        if "ocr_engines" in config_data:
            engines_data = config_data["ocr_engines"]
            for engine_name, engine_config in engines_data.items():
                config.engines[engine_name] = OCREngineConfig(
                    enabled=engine_config.get("enabled", True),
                    priority=engine_config.get("priority", 1),
                    config={k: v for k, v in engine_config.items() 
                           if k not in ["enabled", "priority"]}
                )
        
        # Parse cache configuration
        if "cache" in config_data:
            cache_data = config_data["cache"]
            config.cache = CacheConfig(
                enabled=cache_data.get("enabled", True),
                backend=cache_data.get("backend", "memory"),
                ttl=cache_data.get("ttl", 3600),
                max_size=cache_data.get("max_size", 1000)
            )
        
        # Parse template configuration
        if "templates" in config_data:
            template_data = config_data["templates"]
            config.templates = TemplateConfig(
                builtin_dir=template_data.get("builtin_dir", "templates/builtin"),
                user_dir=template_data.get("user_dir", "templates/user"),
                cache_dir=template_data.get("cache_dir", "templates/cache"),
                auto_learning=template_data.get("auto_learning", True)
            )
        
        return config
    
    def get_claude_config(self) -> ClaudeConfig:
        """Get Claude configuration"""
        config = self.load_config()
        return config.claude
    
    def get_openai_config(self) -> OpenAIConfig:
        """Get OpenAI configuration"""
        config = self.load_config()
        return config.openai
    
    def get_engine_config(self, engine_name: str) -> Optional[OCREngineConfig]:
        """Get specific engine configuration"""
        config = self.load_config()
        return config.engines.get(engine_name)
    
    def is_engine_enabled(self, engine_name: str) -> bool:
        """Check if an engine is enabled"""
        engine_config = self.get_engine_config(engine_name)
        return engine_config.enabled if engine_config else False
    
    def get_enabled_engines(self) -> Dict[str, OCREngineConfig]:
        """Get all enabled engines sorted by priority"""
        config = self.load_config()
        enabled_engines = {
            name: engine_config 
            for name, engine_config in config.engines.items() 
            if engine_config.enabled
        }
        
        # Sort by priority (lower number = higher priority)
        return dict(sorted(
            enabled_engines.items(), 
            key=lambda x: x[1].priority
        ))


# Global configuration manager instance
config_manager = ConfigManager()


def get_config() -> OCRConfig:
    """Get the global OCR configuration"""
    return config_manager.load_config()


def get_claude_config() -> ClaudeConfig:
    """Get Claude configuration"""
    return config_manager.get_claude_config()


def get_openai_config() -> OpenAIConfig:
    """Get OpenAI configuration"""
    return config_manager.get_openai_config()