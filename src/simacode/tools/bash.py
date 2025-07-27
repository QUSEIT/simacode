"""
Bash execution tool for SimaCode.

This tool provides secure execution of system commands with comprehensive
safety checks, output streaming, and permission validation.
"""

import asyncio
import shlex
import signal
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Type

from pydantic import BaseModel, Field, validator

from .base import Tool, ToolInput, ToolResult, ToolResultType, ToolRegistry
from ..permissions import PermissionManager, CommandValidator


class BashInput(ToolInput):
    """Input model for Bash tool."""
    
    command: str = Field(..., description="Command to execute")
    working_directory: Optional[str] = Field(
        None, 
        description="Working directory for command execution"
    )
    timeout: Optional[int] = Field(
        30, 
        description="Command timeout in seconds",
        ge=1,
        le=300
    )
    capture_output: bool = Field(
        True,
        description="Whether to capture command output"
    )
    shell: bool = Field(
        True,
        description="Whether to execute command through shell"
    )
    environment: Optional[Dict[str, str]] = Field(
        None,
        description="Additional environment variables"
    )
    
    @validator('command')
    def validate_command(cls, v):
        """Validate command string."""
        if not v or not v.strip():
            raise ValueError("Command cannot be empty")
        
        # Basic sanitization
        v = v.strip()
        
        # Check for null bytes
        if '\0' in v:
            raise ValueError("Command contains null bytes")
        
        return v
    
    @validator('working_directory')
    def validate_working_directory(cls, v):
        """Validate working directory."""
        if v is not None:
            v = v.strip()
            if not v:
                return None
        return v


class BashTool(Tool):
    """
    Tool for executing system commands safely.
    
    This tool provides a secure interface for running bash commands with
    comprehensive permission checking, output streaming, and error handling.
    """
    
    def __init__(self, permission_manager: Optional[PermissionManager] = None):
        """Initialize Bash tool."""
        super().__init__(
            name="bash",
            description="Execute system commands safely with permission controls",
            version="1.0.0"
        )
        self.permission_manager = permission_manager or PermissionManager()
        self.command_validator = CommandValidator()
        self._active_processes: Dict[str, asyncio.subprocess.Process] = {}
    
    def get_input_schema(self) -> Type[ToolInput]:
        """Return the input schema for this tool."""
        return BashInput
    
    async def validate_input(self, input_data: Dict[str, Any]) -> BashInput:
        """Validate and parse tool input data."""
        return BashInput(**input_data)
    
    async def check_permissions(self, input_data: BashInput) -> bool:
        """Check if the tool has permission to execute with given input."""
        # Validate command through permission system
        permission_result = self.permission_manager.check_command_permission(
            input_data.command
        )
        
        if not permission_result.granted:
            return False
        
        # Validate working directory if specified
        if input_data.working_directory:
            path_permission = self.permission_manager.check_path_access(
                input_data.working_directory, "access"
            )
            if not path_permission.granted:
                return False
        
        # Additional command validation
        is_valid, risk_level, warnings = self.command_validator.validate_command(
            input_data.command
        )
        
        # Reject high-risk commands
        if risk_level == "high":
            return False
        
        return is_valid
    
    async def execute(self, input_data: BashInput) -> AsyncGenerator[ToolResult, None]:
        """Execute the bash command."""
        execution_id = input_data.execution_id
        command = input_data.command
        
        try:
            # Yield command validation info
            is_valid, risk_level, warnings = self.command_validator.validate_command(command)
            
            if warnings:
                yield ToolResult(
                    type=ToolResultType.WARNING,
                    content=f"Command warnings: {'; '.join(warnings)}",
                    execution_id=execution_id,
                    metadata={"risk_level": risk_level, "warnings": warnings}
                )
            
            # Prepare command execution
            if input_data.shell:
                # Use shell for complex commands
                cmd_args = command
                shell = True
            else:
                # Split command for direct execution
                cmd_args = shlex.split(command)
                shell = False
            
            # Prepare environment
            env = None
            if input_data.environment:
                import os
                env = os.environ.copy()
                env.update(input_data.environment)
            
            # Start process
            yield ToolResult(
                type=ToolResultType.INFO,
                content=f"Starting command: {command}",
                execution_id=execution_id,
                metadata={
                    "working_directory": input_data.working_directory,
                    "timeout": input_data.timeout,
                    "shell": shell
                }
            )
            
            start_time = time.time()
            
            # Create subprocess
            process = await asyncio.create_subprocess_shell(
                cmd_args if shell else ' '.join(cmd_args),
                stdout=asyncio.subprocess.PIPE if input_data.capture_output else None,
                stderr=asyncio.subprocess.PIPE if input_data.capture_output else None,
                cwd=input_data.working_directory,
                env=env,
                shell=shell
            )
            
            # Store process for potential cancellation
            self._active_processes[execution_id] = process
            
            try:
                # Stream output if capturing
                if input_data.capture_output:
                    async for output_result in self._stream_process_output(process, execution_id):
                        yield output_result
                
                # Wait for process completion with timeout
                try:
                    await asyncio.wait_for(
                        process.wait(), 
                        timeout=input_data.timeout
                    )
                except asyncio.TimeoutError:
                    # Kill process on timeout
                    process.terminate()
                    try:
                        await asyncio.wait_for(process.wait(), timeout=5)
                    except asyncio.TimeoutError:
                        process.kill()
                        await process.wait()
                    
                    yield ToolResult(
                        type=ToolResultType.ERROR,
                        content=f"Command timed out after {input_data.timeout} seconds",
                        execution_id=execution_id,
                        metadata={"timeout": input_data.timeout}
                    )
                    return
                
                execution_time = time.time() - start_time
                
                # Report final status
                if process.returncode == 0:
                    yield ToolResult(
                        type=ToolResultType.SUCCESS,
                        content=f"Command completed successfully (exit code: 0)",
                        execution_id=execution_id,
                        metadata={
                            "exit_code": process.returncode,
                            "execution_time": execution_time
                        }
                    )
                else:
                    yield ToolResult(
                        type=ToolResultType.ERROR,
                        content=f"Command failed with exit code: {process.returncode}",
                        execution_id=execution_id,
                        metadata={
                            "exit_code": process.returncode,
                            "execution_time": execution_time
                        }
                    )
                
            finally:
                # Clean up process reference
                if execution_id in self._active_processes:
                    del self._active_processes[execution_id]
                
        except FileNotFoundError:
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"Command not found: {command.split()[0] if command.split() else command}",
                execution_id=execution_id
            )
            
        except PermissionError:
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"Permission denied for command: {command}",
                execution_id=execution_id
            )
            
        except Exception as e:
            yield ToolResult(
                type=ToolResultType.ERROR,
                content=f"Unexpected error executing command: {str(e)}",
                execution_id=execution_id,
                metadata={"error_type": type(e).__name__}
            )
    
    async def _stream_process_output(
        self, 
        process: asyncio.subprocess.Process, 
        execution_id: str
    ) -> AsyncGenerator[ToolResult, None]:
        """Stream process output in real-time."""
        async def read_stream(stream, stream_name):
            """Read from a stream and yield results."""
            if stream is None:
                return
            
            try:
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    
                    line_text = line.decode('utf-8', errors='replace').rstrip()
                    if line_text:
                        yield ToolResult(
                            type=ToolResultType.OUTPUT,
                            content=line_text,
                            execution_id=execution_id,
                            metadata={"stream": stream_name}
                        )
            except Exception as e:
                yield ToolResult(
                    type=ToolResultType.WARNING,
                    content=f"Error reading {stream_name}: {str(e)}",
                    execution_id=execution_id
                )
        
        # Create tasks for both stdout and stderr
        tasks = []
        
        if process.stdout:
            tasks.append(read_stream(process.stdout, "stdout"))
        
        if process.stderr:
            tasks.append(read_stream(process.stderr, "stderr"))
        
        # Process all streams concurrently
        if tasks:
            async for result in self._merge_async_generators(*tasks):
                yield result
    
    async def _merge_async_generators(self, *generators):
        """Merge multiple async generators into one."""
        queue = asyncio.Queue()
        tasks = []
        
        async def pump_generator(gen):
            """Pump generator items into queue."""
            try:
                async for item in gen:
                    await queue.put(item)
            except Exception as e:
                await queue.put(ToolResult(
                    type=ToolResultType.ERROR,
                    content=f"Generator error: {str(e)}"
                ))
            finally:
                await queue.put(None)  # Sentinel
        
        # Start all generator tasks
        for gen in generators:
            task = asyncio.create_task(pump_generator(gen))
            tasks.append(task)
        
        # Read from queue until all generators are done
        finished_count = 0
        while finished_count < len(generators):
            try:
                item = await asyncio.wait_for(queue.get(), timeout=1.0)
                if item is None:
                    finished_count += 1
                else:
                    yield item
            except asyncio.TimeoutError:
                # Check if any tasks are still running
                if all(task.done() for task in tasks):
                    break
        
        # Cancel any remaining tasks
        for task in tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    
    async def cancel_execution(self, execution_id: str) -> bool:
        """
        Cancel a running command execution.
        
        Args:
            execution_id: ID of the execution to cancel
            
        Returns:
            bool: True if cancellation was successful
        """
        if execution_id in self._active_processes:
            process = self._active_processes[execution_id]
            try:
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5)
                return True
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return True
            except Exception:
                return False
        return False
    
    def get_active_executions(self) -> List[str]:
        """Get list of active execution IDs."""
        return list(self._active_processes.keys())


# Register the tool
bash_tool = BashTool()
ToolRegistry.register(bash_tool)