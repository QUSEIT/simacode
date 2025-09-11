"""
SimaCode: A modern AI programming assistant with intelligent ReAct mechanisms.

This package provides a comprehensive AI-powered development assistant that combines
natural language understanding with practical programming capabilities through
a sophisticated ReAct (Reasoning and Acting) framework.

Key Features:
- Intelligent task planning and execution
- Multi-agent system for specialized operations
- Secure file system access with permission management
- Modern terminal-based user interface
- Extensible tool system for custom operations
"""

__version__ = "0.1.0"
__author__ = "SimaCode Team"
__email__ = "sima@quseit.com"

import asyncio
import logging
from typing import Optional, Dict, Any, Union
from pathlib import Path

from .cli import main
from .config import Config
from .logging_config import setup_logging

# Global service instance for programmatic usage
_global_service_instance = None
_service_lock = asyncio.Lock()

logger = logging.getLogger(__name__)


def react(task: str, session_id: Optional[str] = None, config_path: Optional[Union[str, Path]] = None) -> str:
    """
    Execute a ReAct task programmatically.
    
    This function provides a simple synchronous interface to SimaCode's ReAct engine,
    equivalent to running `simacode chat --react "task"` from the command line.
    
    Args:
        task: The task or instruction to execute
        session_id: Optional session ID for conversation continuity
        config_path: Optional path to custom configuration file
        
    Returns:
        str: The result of task execution
        
    Raises:
        Exception: If task execution fails
        
    Example:
        import simacode
        result = simacode.react("List all Python files in the current directory")
        print(result)
    """
    return asyncio.run(_async_react(task, session_id, config_path))


async def _async_react(task: str, session_id: Optional[str] = None, config_path: Optional[Union[str, Path]] = None) -> str:
    """Async implementation of react function."""
    global _global_service_instance
    
    try:
        # Get or create service instance
        async with _service_lock:
            if _global_service_instance is None:
                # Load configuration
                config = Config.load(config_path=Path(config_path) if config_path else None)
                
                # Enable auto-confirmation for programmatic usage
                config.react.auto_confirm_safe_tasks = True
                
                # Setup minimal logging to prevent noise
                setup_logging(level="WARNING", config=config.logging)
                
                # Import here to avoid circular imports
                from .core.service import SimaCodeService
                
                # Create service in CLI mode (api_mode=False)
                _global_service_instance = SimaCodeService(config, api_mode=False)
                logger.debug("Created global SimaCodeService instance for programmatic usage")
        
        # Import request class
        from .core.service import ReActRequest
        
        # Create request with skip_confirmation=True for programmatic usage
        request = ReActRequest(task=task, session_id=session_id, skip_confirmation=True)
        
        # Execute task
        response = await _global_service_instance.process_react(request)
        
        # Return result
        if response.error:
            raise Exception(f"Task execution failed: {response.error}")
        
        return response.result
        
    except Exception as e:
        logger.error(f"Error in programmatic react execution: {str(e)}")
        raise


def chat(message: str, session_id: Optional[str] = None, config_path: Optional[Union[str, Path]] = None) -> str:
    """
    Start a conversational chat session programmatically.
    
    This function provides a simple synchronous interface to SimaCode's chat engine,
    equivalent to running `simacode chat "message"` from the command line.
    
    Args:
        message: The message to send to the AI assistant
        session_id: Optional session ID for conversation continuity
        config_path: Optional path to custom configuration file
        
    Returns:
        str: The AI assistant's response
        
    Raises:
        Exception: If chat processing fails
        
    Example:
        import simacode
        response = simacode.chat("Hello, how are you?")
        print(response)
    """
    return asyncio.run(_async_chat(message, session_id, config_path))


async def _async_chat(message: str, session_id: Optional[str] = None, config_path: Optional[Union[str, Path]] = None) -> str:
    """Async implementation of chat function."""
    global _global_service_instance
    
    try:
        # Get or create service instance (same logic as react)
        async with _service_lock:
            if _global_service_instance is None:
                # Load configuration
                config = Config.load(config_path=Path(config_path) if config_path else None)
                
                # Enable auto-confirmation for programmatic usage
                config.react.auto_confirm_safe_tasks = True
                
                # Setup minimal logging to prevent noise
                setup_logging(level="WARNING", config=config.logging)
                
                # Import here to avoid circular imports
                from .core.service import SimaCodeService
                
                # Create service in CLI mode (api_mode=False)
                _global_service_instance = SimaCodeService(config, api_mode=False)
                logger.debug("Created global SimaCodeService instance for programmatic usage")
        
        # Import request class
        from .core.service import ChatRequest
        
        # Create request with force chat mode
        request = ChatRequest(message=message, session_id=session_id, force_mode="chat")
        
        # Process chat
        response = await _global_service_instance.process_chat(request)
        
        # Return result
        if response.error:
            raise Exception(f"Chat processing failed: {response.error}")
        
        return response.content
        
    except Exception as e:
        logger.error(f"Error in programmatic chat execution: {str(e)}")
        raise


__all__ = ["main", "Config", "setup_logging", "react", "chat"]