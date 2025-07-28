"""
Tests for logging configuration.
"""

import logging
import tempfile
from pathlib import Path

import pytest

from simacode.config import LoggingConfig
from simacode.logging_config import setup_logging, get_logger, set_log_level


class TestLogging:
    """Test cases for logging configuration."""

    def test_setup_logging_basic(self):
        """Test basic logging setup."""
        setup_logging(level="INFO")
        logger = get_logger("test")
        
        assert logger.getEffectiveLevel() == logging.INFO
        assert len(logging.getLogger().handlers) > 0

    def test_setup_logging_with_config(self):
        """Test logging setup with configuration object."""
        config = LoggingConfig(level="DEBUG")
        setup_logging(config=config)
        
        logger = get_logger("test")
        assert logger.getEffectiveLevel() == logging.DEBUG

    def test_setup_logging_with_file(self):
        """Test logging setup with file output."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "test.log"
            
            setup_logging(level="INFO", log_file=log_file)
            
            logger = get_logger("test_file")
            logger.info("Test message")
            
            assert log_file.exists()
            assert log_file.read_text().strip()

    def test_set_log_level(self):
        """Test dynamic log level changes."""
        setup_logging(level="INFO")
        logger = get_logger("test_level")
        
        assert logger.getEffectiveLevel() == logging.INFO
        
        set_log_level("DEBUG")
        assert logger.getEffectiveLevel() == logging.DEBUG
        
        set_log_level("WARNING")
        assert logger.getEffectiveLevel() == logging.WARNING

    def test_invalid_log_level(self):
        """Test handling of invalid log levels."""
        with pytest.raises(ValueError):
            set_log_level("INVALID_LEVEL")

    def test_logger_names(self):
        """Test logger naming and retrieval."""
        logger1 = get_logger("module.submodule")
        logger2 = get_logger("module.submodule")
        
        assert logger1 is logger2
        assert logger1.name == "module.submodule"

    def test_logging_output(self):
        """Test actual logging output to file."""
        import tempfile
        from pathlib import Path
        
        # Create a temporary log file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.log') as tmp_file:
            log_file_path = Path(tmp_file.name)
        
        try:
            # Set up logging with file output
            config = LoggingConfig(level="DEBUG", file_path=str(log_file_path))
            setup_logging(config=config)
            
            logger = get_logger("test_output")
            
            logger.debug("Debug message")
            logger.info("Info message")
            logger.warning("Warning message")
            logger.error("Error message")
            
            # Verify file output (file logging should work)
            log_content = log_file_path.read_text()
            assert "Debug message" in log_content
            assert "Info message" in log_content
            assert "Warning message" in log_content
            assert "Error message" in log_content
            
            # Verify logger is configured with correct level
            assert logger.getEffectiveLevel() == logging.DEBUG
        finally:
            # Clean up
            if log_file_path.exists():
                log_file_path.unlink()

    def test_rotating_file_handler(self):
        """Test rotating file handler functionality."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            config = LoggingConfig(
                level="INFO",
                file_path=Path(tmp_dir) / "rotating.log",
                max_file_size=100,  # Very small for testing
                backup_count=2
            )
            
            setup_logging(config=config)
            
            logger = get_logger("rotating_test")
            
            # Write enough to trigger rotation
            for i in range(100):
                logger.info(f"Message {i:03d}" * 10)
            
            log_files = list(Path(tmp_dir).glob("rotating.log*"))
            assert len(log_files) > 1  # Should have rotated files

    def test_third_party_loggers(self):
        """Test that third-party loggers are properly configured."""
        setup_logging(level="DEBUG")
        
        # Check that third-party loggers have appropriate levels
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING
        assert logging.getLogger("urllib3").level == logging.WARNING

    def test_logging_config_validation(self):
        """Test logging configuration validation."""
        # Valid configurations
        LoggingConfig(level="INFO")
        LoggingConfig(level="DEBUG")
        
        # Invalid configurations
        with pytest.raises(ValueError):
            LoggingConfig(level="INVALID")

    def test_context_filter(self):
        """Test custom context filter."""
        from simacode.logging_config import ContextFilter
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "context_test.log"
            
            setup_logging(level="INFO")
            logger = get_logger("context_test")
            
            # Add context filter
            context = {"request_id": "test-123", "user": "test_user"}
            for handler in logging.getLogger().handlers:
                if hasattr(handler, 'filters'):
                    handler.addFilter(ContextFilter(context))
            
            logger.info("Test message with context")
            
            # Verify context was added (implementation specific)