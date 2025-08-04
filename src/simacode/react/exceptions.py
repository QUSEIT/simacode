"""
ReAct Engine Exceptions

This module defines custom exceptions for the ReAct engine components,
providing specific error types for different failure modes.
"""

from typing import Any, Dict, Optional


class ReActError(Exception):
    """Base exception for all ReAct engine errors."""
    
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.context = context or {}


class PlanningError(ReActError):
    """Raised when task planning fails."""
    
    def __init__(self, message: str, user_input: str = "", context: Optional[Dict[str, Any]] = None):
        super().__init__(message, context)
        self.user_input = user_input


class ExecutionError(ReActError):
    """Raised when tool execution fails."""
    
    def __init__(self, message: str, tool_name: str = "", tool_input: Optional[Dict[str, Any]] = None, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, context)
        self.tool_name = tool_name
        self.tool_input = tool_input or {}


class EvaluationError(ReActError):
    """Raised when result evaluation fails."""
    
    def __init__(self, message: str, expected_outcome: str = "", actual_result: str = "", context: Optional[Dict[str, Any]] = None):
        super().__init__(message, context)
        self.expected_outcome = expected_outcome
        self.actual_result = actual_result


class ToolNotFoundError(ExecutionError):
    """Raised when a required tool is not found."""
    pass


class InvalidTaskError(PlanningError):
    """Raised when a task definition is invalid."""
    pass


class MaxRetriesExceededError(ReActError):
    """Raised when maximum retry attempts are exceeded."""
    
    def __init__(self, message: str, max_retries: int, attempts: int, context: Optional[Dict[str, Any]] = None):
        super().__init__(message, context)
        self.max_retries = max_retries
        self.attempts = attempts


class ReplanningRequiresConfirmationError(ReActError):
    """Raised when task replanning is complete and requires user confirmation again."""
    pass