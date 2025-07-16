"""
Logging configuration for SimaCode.

This module provides comprehensive logging setup with support for both
console and file logging, including rotation and formatting.
"""

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional, Union

from rich.console import Console
from rich.logging import RichHandler
from rich.traceback import install

from .config import LoggingConfig

# Install rich traceback handler for better error display
install(show_locals=True)

# Global console instance for rich logging
console = Console()


def setup_logging(
    level: str = "INFO",
    config: Optional[LoggingConfig] = None,
    log_file: Optional[Union[str, Path]] = None,
) -> None:
    """
    Set up logging configuration for the application.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        config: Logging configuration object
        log_file: Optional path to log file
    """
    if config is None:
        config = LoggingConfig(level=level, file_path=log_file)
    
    # Clear existing handlers
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    
    # Set root logger level
    root_logger.setLevel(getattr(logging, config.level.upper()))
    
    # Create formatter
    formatter = logging.Formatter(config.format)
    
    # Console handler with rich formatting
    console_handler = RichHandler(
        console=console,
        show_time=True,
        show_path=True,
        markup=True,
        rich_tracebacks=True,
        tracebacks_show_locals=True,
    )
    console_handler.setLevel(getattr(logging, config.level.upper()))
    
    # File handler if specified
    file_handler = None
    if config.file_path:
        log_path = Path(config.file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Use rotating file handler
        file_handler = logging.handlers.RotatingFileHandler(
            log_path,
            maxBytes=config.max_file_size,
            backupCount=config.backup_count,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(getattr(logging, config.level.upper()))
    
    # Add handlers to root logger
    root_logger.addHandler(console_handler)
    if file_handler:
        root_logger.addHandler(file_handler)
    
    # Configure specific loggers
    _configure_third_party_loggers()


def _configure_third_party_loggers() -> None:
    """Configure log levels for third-party libraries."""
    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the specified name.
    
    Args:
        name: Logger name
        
    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


class ContextFilter(logging.Filter):
    """Custom filter to add context to log records."""
    
    def __init__(self, context: dict):
        super().__init__()
        self.context = context
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add context data to log record."""
        for key, value in self.context.items():
            setattr(record, key, value)
        return True


class StructuredFormatter(logging.Formatter):
    """Structured JSON formatter for machine-readable logs."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        import json
        
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in log_data and not key.startswith("_"):
                log_data[key] = str(value)
        
        return json.dumps(log_data, ensure_ascii=False)


def set_log_level(level: str) -> None:
    """
    Dynamically change the log level.
    
    Args:
        level: New log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    root_logger = logging.getLogger()
    level_num = getattr(logging, level.upper(), None)
    
    if level_num is None:
        raise ValueError(f"Invalid log level: {level}")
    
    root_logger.setLevel(level_num)
    
    for handler in root_logger.handlers:
        handler.setLevel(level_num)


def add_file_handler(
    filepath: Union[str, Path],
    level: str = "INFO",
    formatter: Optional[logging.Formatter] = None,
) -> None:
    """
    Add a file handler to the root logger.
    
    Args:
        filepath: Path to the log file
        level: Log level for the file handler
        formatter: Optional custom formatter
    """
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    
    file_handler = logging.FileHandler(filepath, encoding="utf-8")
    file_handler.setLevel(getattr(logging, level.upper()))
    
    if formatter is None:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    
    file_handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)


# Convenience function for quick setup
def configure_default_logging(level: str = "INFO") -> None:
    """Configure default logging for development/testing."""
    setup_logging(level=level)


# Module-level logger
logger = get_logger(__name__)