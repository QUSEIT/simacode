"""
Validation utilities for permission system.

This module provides specialized validators for different types of operations
and resources.
"""

import os
import re
from pathlib import Path
from typing import List, Optional, Set


class PathValidator:
    """Validator for file system paths."""
    
    # Common dangerous path patterns
    DANGEROUS_PATH_PATTERNS = [
        # System directories
        r'^/etc(/.*)?$',
        r'^/sys(/.*)?$', 
        r'^/proc(/.*)?$',
        r'^/dev(/.*)?$',
        r'^/boot(/.*)?$',
        r'^/root(/.*)?$',
        
        # Windows system directories
        r'^[A-Za-z]:\\Windows\\.*$',
        r'^[A-Za-z]:\\System32\\.*$',
        r'^[A-Za-z]:\\Program Files\\.*$',
        
        # Hidden/config files that could be dangerous
        r'.*/\.ssh/.*',
        r'.*/\.aws/.*',
        r'.*/\.docker/.*',
        r'.*\.key$',
        r'.*\.pem$',
    ]
    
    # File extensions that might be risky to modify
    RISKY_EXTENSIONS = {
        '.exe', '.msi', '.deb', '.rpm', '.dmg', '.pkg',
        '.bat', '.cmd', '.ps1', '.vbs', '.sh', '.bash',
        '.dll', '.so', '.dylib'
    }
    
    def __init__(self, allowed_paths: Optional[List[str]] = None):
        """Initialize path validator with allowed paths."""
        self.allowed_paths = allowed_paths or [str(Path.cwd())]
        self._compiled_patterns = [
            re.compile(pattern, re.IGNORECASE) 
            for pattern in self.DANGEROUS_PATH_PATTERNS
        ]
    
    def is_path_safe(self, path: str) -> bool:
        """
        Check if a path is safe to access.
        
        Args:
            path: Path to validate
            
        Returns:
            bool: True if path is safe, False otherwise
        """
        try:
            normalized_path = os.path.abspath(path)
        except (OSError, ValueError):
            return False
        
        # Check against dangerous patterns
        for pattern in self._compiled_patterns:
            if pattern.match(normalized_path):
                return False
        
        return True
    
    def is_path_allowed(self, path: str) -> bool:
        """
        Check if a path is within allowed directories.
        
        Args:
            path: Path to validate
            
        Returns:
            bool: True if path is allowed, False otherwise
        """
        try:
            normalized_path = os.path.abspath(path)
        except (OSError, ValueError):
            return False
        
        for allowed in self.allowed_paths:
            allowed_abs = os.path.abspath(allowed)
            if normalized_path.startswith(allowed_abs):
                return True
        
        return False
    
    def is_extension_risky(self, path: str) -> bool:
        """
        Check if file extension is potentially risky.
        
        Args:
            path: File path to check
            
        Returns:
            bool: True if extension is risky, False otherwise
        """
        _, ext = os.path.splitext(path.lower())
        return ext in self.RISKY_EXTENSIONS
    
    def validate_path(self, path: str, operation: str = "read") -> tuple[bool, str]:
        """
        Comprehensive path validation.
        
        Args:
            path: Path to validate
            operation: Operation type (read, write, delete, etc.)
            
        Returns:
            tuple[bool, str]: (is_valid, reason)
        """
        # Basic safety check
        if not self.is_path_safe(path):
            return False, "Path is in a dangerous system location"
        
        # Allowed path check
        if not self.is_path_allowed(path):
            return False, "Path is not in allowed directories"
        
        # Extension check for write operations
        if operation in ("write", "create") and self.is_extension_risky(path):
            return False, f"File extension is potentially risky for {operation} operations"
        
        # Check for path traversal attempts
        if ".." in path or path.startswith("/"):
            normalized = os.path.normpath(path)
            if ".." in normalized:
                return False, "Path contains directory traversal sequences"
        
        return True, "Path validation passed"


class CommandValidator:
    """Validator for system commands."""
    
    # Commands that are generally safe to run
    SAFE_COMMANDS = {
        'ls', 'dir', 'pwd', 'cd', 'echo', 'cat', 'head', 'tail',
        'grep', 'find', 'which', 'whoami', 'date', 'uptime',
        'ps', 'top', 'df', 'du', 'free', 'uname', 'hostname',
        'git', 'python', 'pip', 'npm', 'yarn', 'poetry',
        'docker', 'kubectl', 'curl', 'wget'
    }
    
    # Commands that require extra caution
    RESTRICTED_COMMANDS = {
        'sudo', 'su', 'chmod', 'chown', 'mount', 'umount',
        'iptables', 'ufw', 'systemctl', 'service', 'crontab'
    }
    
    # Commands that should generally be blocked
    DANGEROUS_COMMANDS = {
        'rm', 'del', 'format', 'fdisk', 'mkfs', 'dd',
        'passwd', 'useradd', 'userdel', 'groupadd', 'groupdel'
    }
    
    # Dangerous command patterns
    DANGEROUS_PATTERNS = [
        r'rm\s+-rf\s*/',
        r'sudo\s+rm',
        r'format\s+[a-z]:',
        r'>\s*/dev/',
        r'dd\s+if=.*of=',
        r'mkfs\.',
        r'chmod\s+777',
        r'chown\s+.*root',
        r':(){ :|:& };:',  # Fork bomb
        r'curl.*\|\s*sh',  # Pipe to shell
        r'wget.*-O\s*-.*\|\s*sh'  # Pipe to shell
    ]
    
    def __init__(self):
        """Initialize command validator."""
        self._compiled_patterns = [
            re.compile(pattern, re.IGNORECASE) 
            for pattern in self.DANGEROUS_PATTERNS
        ]
    
    def get_command_base(self, command: str) -> str:
        """
        Extract the base command from a command string.
        
        Args:
            command: Full command string
            
        Returns:
            str: Base command name
        """
        # Remove leading/trailing whitespace
        command = command.strip()
        
        # Handle commands with sudo
        if command.startswith('sudo '):
            command = command[5:].strip()
        
        # Get first word (the actual command)
        parts = command.split()
        return parts[0] if parts else ""
    
    def is_command_safe(self, command: str) -> bool:
        """
        Check if a command is generally safe to run.
        
        Args:
            command: Command to validate
            
        Returns:
            bool: True if command is safe, False otherwise
        """
        base_command = self.get_command_base(command)
        
        # Check if base command is in safe list
        if base_command in self.SAFE_COMMANDS:
            return True
        
        # Check if base command is dangerous
        if base_command in self.DANGEROUS_COMMANDS:
            return False
        
        # Check against dangerous patterns
        for pattern in self._compiled_patterns:
            if pattern.search(command):
                return False
        
        return True
    
    def is_command_restricted(self, command: str) -> bool:
        """
        Check if a command requires restricted access.
        
        Args:
            command: Command to validate
            
        Returns:
            bool: True if command is restricted, False otherwise
        """
        base_command = self.get_command_base(command)
        return base_command in self.RESTRICTED_COMMANDS
    
    def has_dangerous_flags(self, command: str) -> bool:
        """
        Check if command has potentially dangerous flags.
        
        Args:
            command: Command to validate
            
        Returns:
            bool: True if dangerous flags detected, False otherwise
        """
        dangerous_flags = [
            '-rf', '--recursive --force',
            '--no-preserve-root',
            '--force',
            '/dev/',
            '2>&1',
            '>/dev/null'
        ]
        
        command_lower = command.lower()
        return any(flag in command_lower for flag in dangerous_flags)
    
    def validate_command(self, command: str) -> tuple[bool, str, List[str]]:
        """
        Comprehensive command validation.
        
        Args:
            command: Command to validate
            
        Returns:
            tuple[bool, str, List[str]]: (is_valid, risk_level, warnings)
        """
        warnings = []
        
        # Check if command is empty
        if not command.strip():
            return False, "high", ["Empty command"]
        
        base_command = self.get_command_base(command)
        
        # Check if command is explicitly dangerous
        if base_command in self.DANGEROUS_COMMANDS:
            return False, "high", [f"Command '{base_command}' is in dangerous commands list"]
        
        # Check against dangerous patterns
        for pattern in self._compiled_patterns:
            if pattern.search(command):
                return False, "high", [f"Command matches dangerous pattern"]
        
        # Check for dangerous flags
        if self.has_dangerous_flags(command):
            warnings.append("Command contains potentially dangerous flags")
        
        # Check if command is restricted
        if self.is_command_restricted(command):
            warnings.append(f"Command '{base_command}' requires elevated privileges")
            return True, "medium", warnings
        
        # Check if command is safe
        if self.is_command_safe(command):
            return True, "low", warnings
        
        # Unknown command - treat with caution
        warnings.append(f"Unknown command '{base_command}' - proceed with caution")
        return True, "medium", warnings
    
    def sanitize_command(self, command: str) -> str:
        """
        Sanitize a command by removing potentially dangerous elements.
        
        Args:
            command: Command to sanitize
            
        Returns:
            str: Sanitized command
        """
        # Remove dangerous redirections
        command = re.sub(r'>\s*/dev/\w+', '', command)
        
        # Remove pipe to shell commands
        command = re.sub(r'\|\s*(sh|bash|zsh|fish)', '', command)
        
        # Remove background execution
        command = re.sub(r'\s*&\s*$', '', command)
        
        # Remove command chaining with dangerous commands
        command = re.sub(r';\s*(rm|del|format)', '', command, flags=re.IGNORECASE)
        
        return command.strip()