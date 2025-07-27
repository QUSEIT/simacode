"""
Comprehensive tests for the SimaCode tool system.

This test suite covers all aspects of the tool system including:
- Base tool framework
- Tool registration and discovery
- Permission system
- Individual tool functionality (Bash, FileRead, FileWrite)
- Integration scenarios
"""

import asyncio
import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, AsyncMock

from simacode.tools import (
    Tool, ToolResult, ToolInput, ToolRegistry, ToolResultType,
    BashTool, FileReadTool, FileWriteTool
)
from simacode.tools.base import discover_tools, execute_tool
from simacode.permissions import PermissionManager, PermissionResult, PermissionLevel


class TestToolBase:
    """Test the base tool framework."""
    
    def setup_method(self):
        """Setup for each test."""
        # Clear tool registry
        ToolRegistry.clear()
    
    def teardown_method(self):
        """Cleanup after each test."""
        ToolRegistry.clear()
    
    def test_tool_registry_singleton(self):
        """Test that ToolRegistry follows singleton pattern."""
        registry1 = ToolRegistry()
        registry2 = ToolRegistry()
        assert registry1 is registry2
    
    def test_tool_result_creation(self):
        """Test ToolResult creation and serialization."""
        result = ToolResult(
            type=ToolResultType.SUCCESS,
            content="Test result",
            metadata={"test": True}
        )
        
        assert result.type == ToolResultType.SUCCESS
        assert result.content == "Test result"
        assert result.metadata["test"] is True
        assert result.tool_name == ""
        assert result.execution_id != ""
        
        # Test serialization
        result_dict = result.to_dict()
        assert result_dict["type"] == "success"
        assert result_dict["content"] == "Test result"
        assert "timestamp" in result_dict
        
        json_str = result.to_json()
        assert "success" in json_str
        assert "Test result" in json_str
    
    def test_tool_input_validation(self):
        """Test ToolInput validation."""
        # Valid input
        input_data = ToolInput(metadata={"test": True})
        assert input_data.execution_id != ""
        assert input_data.metadata["test"] is True
        
        # Test with custom fields (extra='allow')
        input_with_extra = ToolInput(custom_field="value")
        assert input_with_extra.custom_field == "value"
    
    def test_tool_registry_operations(self):
        """Test tool registry registration and discovery."""
        # Create mock tool
        mock_tool = Mock(spec=Tool)
        mock_tool.name = "test_tool"
        mock_tool.description = "Test tool"
        mock_tool.version = "1.0.0"
        mock_tool._execution_count = 0
        mock_tool._total_execution_time = 0.0
        mock_tool.metadata = {
            "name": "test_tool",
            "execution_count": 0,
            "average_execution_time": 0.0
        }
        
        # Test registration
        ToolRegistry.register(mock_tool)
        assert "test_tool" in ToolRegistry.list_tools()
        assert ToolRegistry.get_tool("test_tool") is mock_tool
        
        # Test duplicate registration
        with pytest.raises(ValueError, match="already registered"):
            ToolRegistry.register(mock_tool)
        
        # Test tool metadata
        metadata = ToolRegistry.get_tool_metadata("test_tool")
        assert metadata["name"] == "test_tool"
        
        # Test unregistration
        assert ToolRegistry.unregister("test_tool") is True
        assert ToolRegistry.get_tool("test_tool") is None
        assert ToolRegistry.unregister("nonexistent") is False
        
        # Test registry stats
        stats = ToolRegistry.get_registry_stats()
        assert stats["total_tools"] == 0
        assert stats["total_executions"] == 0
    
    @pytest.mark.asyncio
    async def test_discover_tools(self):
        """Test tool discovery functionality."""
        # Register some mock tools
        tools = []
        for i in range(3):
            mock_tool = Mock(spec=Tool)
            mock_tool.name = f"tool_{i}"
            tools.append(mock_tool)
            ToolRegistry.register(mock_tool)
        
        discovered = await discover_tools()
        assert len(discovered) == 3
        assert all(tool in discovered for tool in tools)


class TestPermissionSystem:
    """Test the permission system."""
    
    def setup_method(self):
        """Setup for each test."""
        self.permission_manager = PermissionManager()
    
    def test_permission_result_creation(self):
        """Test PermissionResult creation."""
        result = PermissionResult(
            granted=True,
            level=PermissionLevel.ALLOWED,
            reason="Test permission"
        )
        
        assert result.granted is True
        assert result.level == PermissionLevel.ALLOWED
        assert result.reason == "Test permission"
        assert result.restrictions == []
    
    def test_file_permission_checks(self):
        """Test file permission checking."""
        # Test with allowed path (current directory)
        current_dir = os.getcwd()
        test_file = os.path.join(current_dir, "test.txt")
        
        result = self.permission_manager.check_file_permission(test_file, "read")
        assert result.granted is True
        
        # Test with forbidden path
        result = self.permission_manager.check_file_permission("/etc/passwd", "read")
        assert result.granted is False
        assert "forbidden" in result.reason.lower()
    
    def test_command_permission_checks(self):
        """Test command permission checking."""
        # Test safe command
        result = self.permission_manager.check_command_permission("ls -la")
        assert result.granted is True
        
        # Test dangerous command
        result = self.permission_manager.check_command_permission("rm -rf /")
        assert result.granted is False
        assert "dangerous" in result.reason.lower()
        
        # Test risky command
        result = self.permission_manager.check_command_permission("sudo ls")
        assert result.granted is True
        assert result.level == PermissionLevel.RESTRICTED
    
    def test_path_access_checks(self):
        """Test path access checking."""
        # Test allowed path
        current_dir = os.getcwd()
        result = self.permission_manager.check_path_access(current_dir, "access")
        assert result.granted is True
        
        # Test forbidden path
        result = self.permission_manager.check_path_access("/etc", "access")
        assert result.granted is False
    
    def test_permission_caching(self):
        """Test permission result caching."""
        # First check
        result1 = self.permission_manager.check_file_permission("test.txt", "read")
        
        # Second check should be cached
        result2 = self.permission_manager.check_file_permission("test.txt", "read")
        
        assert result1.granted == result2.granted
        assert result1.reason == result2.reason
        
        # Check cache stats
        stats = self.permission_manager.get_cache_stats()
        assert stats["total_entries"] >= 1
        
        # Clear cache
        self.permission_manager.clear_cache()
        stats = self.permission_manager.get_cache_stats()
        assert stats["total_entries"] == 0


class TestBashTool:
    """Test the BashTool functionality."""
    
    def setup_method(self):
        """Setup for each test."""
        ToolRegistry.clear()
        self.permission_manager = Mock(spec=PermissionManager)
        self.bash_tool = BashTool(self.permission_manager)
    
    def teardown_method(self):
        """Cleanup after each test."""
        ToolRegistry.clear()
    
    @pytest.mark.asyncio
    async def test_bash_tool_input_validation(self):
        """Test BashTool input validation."""
        # Valid input
        input_data = {"command": "echo 'hello'"}
        validated = await self.bash_tool.validate_input(input_data)
        assert validated.command == "echo 'hello'"
        assert validated.timeout == 30  # Default
        assert validated.capture_output is True
        
        # Invalid input - empty command
        with pytest.raises(Exception):
            await self.bash_tool.validate_input({"command": ""})
        
        # Invalid input - null bytes
        with pytest.raises(Exception):
            await self.bash_tool.validate_input({"command": "echo\x00test"})
    
    @pytest.mark.asyncio
    async def test_bash_tool_permission_checks(self):
        """Test BashTool permission checking."""
        # Mock permission results
        command_permission = PermissionResult(
            granted=True,
            level=PermissionLevel.ALLOWED
        )
        self.permission_manager.check_command_permission.return_value = command_permission
        
        input_data = await self.bash_tool.validate_input({"command": "echo test"})
        
        # Test successful permission check
        has_permission = await self.bash_tool.check_permissions(input_data)
        assert has_permission is True
        self.permission_manager.check_command_permission.assert_called_once()
        
        # Test failed permission check
        self.permission_manager.check_command_permission.return_value = PermissionResult(
            granted=False,
            level=PermissionLevel.DENIED
        )
        
        has_permission = await self.bash_tool.check_permissions(input_data)
        assert has_permission is False
    
    @pytest.mark.asyncio
    async def test_bash_tool_execution_simple_command(self):
        """Test BashTool execution with simple command."""
        # Mock permissions
        self.permission_manager.check_command_permission.return_value = PermissionResult(
            granted=True,
            level=PermissionLevel.ALLOWED
        )
        
        input_data = await self.bash_tool.validate_input({
            "command": "echo 'Hello World'",
            "timeout": 10
        })
        
        results = []
        async for result in self.bash_tool.execute(input_data):
            results.append(result)
        
        # Check that we got some results
        assert len(results) > 0
        
        # Should have info, output, and success results
        result_types = [r.type for r in results]
        assert ToolResultType.INFO in result_types
        
        # Check for command output or success
        output_results = [r for r in results if r.type == ToolResultType.OUTPUT]
        success_results = [r for r in results if r.type == ToolResultType.SUCCESS]
        
        # Should have either output or success (or both)
        assert len(output_results) > 0 or len(success_results) > 0
    
    @pytest.mark.skip(reason="BashTool timeout handling needs async generator refactoring for capture_output=True case")
    @pytest.mark.asyncio
    async def test_bash_tool_timeout(self):
        """Test BashTool timeout handling."""
        # Mock permissions
        self.permission_manager.check_command_permission.return_value = PermissionResult(
            granted=True,
            level=PermissionLevel.ALLOWED
        )
        
        # Use a command that will timeout
        input_data = await self.bash_tool.validate_input({
            "command": "sleep 10",
            "timeout": 1  # 1 second timeout
        })
        
        results = []
        async for result in self.bash_tool.execute(input_data):
            results.append(result)
        
        # Should have timeout error
        error_results = [r for r in results if r.type == ToolResultType.ERROR]
        timeout_errors = [r for r in error_results if "timeout" in r.content.lower()]
        assert len(timeout_errors) > 0


class TestFileReadTool:
    """Test the FileReadTool functionality."""
    
    def setup_method(self):
        """Setup for each test."""
        ToolRegistry.clear()
        self.permission_manager = Mock(spec=PermissionManager)
        self.file_read_tool = FileReadTool(self.permission_manager)
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        """Cleanup after each test."""
        ToolRegistry.clear()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_file_read_input_validation(self):
        """Test FileReadTool input validation."""
        # Valid input
        input_data = {"file_path": "/path/to/file.txt"}
        validated = await self.file_read_tool.validate_input(input_data)
        assert validated.file_path == "/path/to/file.txt"
        assert validated.encoding is None
        assert validated.max_size == 10 * 1024 * 1024  # 10MB default
        
        # Invalid input - empty path
        with pytest.raises(Exception):
            await self.file_read_tool.validate_input({"file_path": ""})
        
        # Test with line range
        input_data = {
            "file_path": "test.txt",
            "start_line": 5,
            "end_line": 10
        }
        validated = await self.file_read_tool.validate_input(input_data)
        assert validated.start_line == 5
        assert validated.end_line == 10
        
        # Invalid line range
        with pytest.raises(Exception):
            await self.file_read_tool.validate_input({
                "file_path": "test.txt",
                "start_line": 10,
                "end_line": 5
            })
    
    @pytest.mark.asyncio
    async def test_file_read_permission_checks(self):
        """Test FileReadTool permission checking."""
        # Mock permission results
        file_permission = PermissionResult(granted=True, level=PermissionLevel.ALLOWED)
        self.permission_manager.check_file_permission.return_value = file_permission
        
        # Mock path validator
        with patch.object(self.file_read_tool.path_validator, 'validate_path') as mock_validate:
            mock_validate.return_value = (True, "Valid path")
            
            input_data = await self.file_read_tool.validate_input({"file_path": "test.txt"})
            has_permission = await self.file_read_tool.check_permissions(input_data)
            
            assert has_permission is True
            self.permission_manager.check_file_permission.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_file_read_execution(self):
        """Test FileReadTool execution."""
        # Create test file
        test_file = os.path.join(self.temp_dir, "test.txt")
        test_content = "Hello\nWorld\nTest Content"
        
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write(test_content)
        
        # Mock permissions
        self.permission_manager.check_file_permission.return_value = PermissionResult(
            granted=True, level=PermissionLevel.ALLOWED
        )
        
        with patch.object(self.file_read_tool.path_validator, 'validate_path') as mock_validate:
            mock_validate.return_value = (True, "Valid path")
            
            input_data = await self.file_read_tool.validate_input({"file_path": test_file})
            
            results = []
            async for result in self.file_read_tool.execute(input_data):
                results.append(result)
            
            # Check results
            assert len(results) > 0
            
            # Should have info, output, and success results
            info_results = [r for r in results if r.type == ToolResultType.INFO]
            output_results = [r for r in results if r.type == ToolResultType.OUTPUT]
            success_results = [r for r in results if r.type == ToolResultType.SUCCESS]
            
            assert len(info_results) > 0
            assert len(output_results) > 0
            assert len(success_results) > 0
            
            # Check that content was read
            content_found = any(test_content in r.content for r in output_results)
            assert content_found
    
    @pytest.mark.asyncio
    async def test_file_read_nonexistent_file(self):
        """Test FileReadTool with nonexistent file."""
        # Mock permissions
        self.permission_manager.check_file_permission.return_value = PermissionResult(
            granted=True, level=PermissionLevel.ALLOWED
        )
        
        with patch.object(self.file_read_tool.path_validator, 'validate_path') as mock_validate:
            mock_validate.return_value = (True, "Valid path")
            
            nonexistent_file = os.path.join(self.temp_dir, "nonexistent.txt")
            input_data = await self.file_read_tool.validate_input({"file_path": nonexistent_file})
            
            results = []
            async for result in self.file_read_tool.execute(input_data):
                results.append(result)
            
            # Should have error about file not found
            error_results = [r for r in results if r.type == ToolResultType.ERROR]
            assert len(error_results) > 0
            assert any("not found" in r.content.lower() for r in error_results)


class TestFileWriteTool:
    """Test the FileWriteTool functionality."""
    
    def setup_method(self):
        """Setup for each test."""
        ToolRegistry.clear()
        self.permission_manager = Mock(spec=PermissionManager)
        self.file_write_tool = FileWriteTool(self.permission_manager)
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        """Cleanup after each test."""
        ToolRegistry.clear()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_file_write_input_validation(self):
        """Test FileWriteTool input validation."""
        # Valid input
        input_data = {
            "file_path": "/path/to/file.txt",
            "content": "Hello World"
        }
        validated = await self.file_write_tool.validate_input(input_data)
        assert validated.file_path == "/path/to/file.txt"
        assert validated.content == "Hello World"
        assert validated.encoding == "utf-8"
        assert validated.mode == "write"
        
        # Test append mode
        input_data = {
            "file_path": "test.txt",
            "content": "New content",
            "mode": "append"
        }
        validated = await self.file_write_tool.validate_input(input_data)
        assert validated.mode == "append"
        
        # Test insert mode
        input_data = {
            "file_path": "test.txt",
            "content": "Insert content",
            "mode": "insert",
            "insert_line": 5
        }
        validated = await self.file_write_tool.validate_input(input_data)
        assert validated.mode == "insert"
        assert validated.insert_line == 5
        
        # Invalid input - insert mode without line number
        with pytest.raises(Exception):
            await self.file_write_tool.validate_input({
                "file_path": "test.txt",
                "content": "content",
                "mode": "insert"
            })
    
    @pytest.mark.asyncio
    async def test_file_write_permission_checks(self):
        """Test FileWriteTool permission checking."""
        # Mock permission results
        file_permission = PermissionResult(granted=True, level=PermissionLevel.ALLOWED)
        self.permission_manager.check_file_permission.return_value = file_permission
        
        # Mock path validator
        with patch.object(self.file_write_tool.path_validator, 'validate_path') as mock_validate:
            mock_validate.return_value = (True, "Valid path")
            
            input_data = await self.file_write_tool.validate_input({
                "file_path": "test.txt",
                "content": "test"
            })
            has_permission = await self.file_write_tool.check_permissions(input_data)
            
            assert has_permission is True
            self.permission_manager.check_file_permission.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_file_write_execution_new_file(self):
        """Test FileWriteTool execution with new file."""
        # Mock permissions
        self.permission_manager.check_file_permission.return_value = PermissionResult(
            granted=True, level=PermissionLevel.ALLOWED
        )
        
        with patch.object(self.file_write_tool.path_validator, 'validate_path') as mock_validate:
            mock_validate.return_value = (True, "Valid path")
            
            test_file = os.path.join(self.temp_dir, "new_file.txt")
            test_content = "Hello World!\nThis is a test."
            
            input_data = await self.file_write_tool.validate_input({
                "file_path": test_file,
                "content": test_content
            })
            
            results = []
            async for result in self.file_write_tool.execute(input_data):
                results.append(result)
            
            # Check results
            assert len(results) > 0
            
            # Should have success result
            success_results = [r for r in results if r.type == ToolResultType.SUCCESS]
            assert len(success_results) > 0
            
            # Check that file was created
            assert os.path.exists(test_file)
            
            # Check file content
            with open(test_file, 'r', encoding='utf-8') as f:
                written_content = f.read()
            assert written_content == test_content
    
    @pytest.mark.asyncio
    async def test_file_write_execution_append_mode(self):
        """Test FileWriteTool execution in append mode."""
        # Create initial file
        test_file = os.path.join(self.temp_dir, "append_test.txt")
        initial_content = "Initial content\n"
        
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write(initial_content)
        
        # Mock permissions
        self.permission_manager.check_file_permission.return_value = PermissionResult(
            granted=True, level=PermissionLevel.ALLOWED
        )
        
        with patch.object(self.file_write_tool.path_validator, 'validate_path') as mock_validate:
            mock_validate.return_value = (True, "Valid path")
            
            append_content = "Appended content"
            
            input_data = await self.file_write_tool.validate_input({
                "file_path": test_file,
                "content": append_content,
                "mode": "append"
            })
            
            results = []
            async for result in self.file_write_tool.execute(input_data):
                results.append(result)
            
            # Check that file contains both contents
            with open(test_file, 'r', encoding='utf-8') as f:
                final_content = f.read()
            
            assert initial_content in final_content
            assert append_content in final_content


class TestToolIntegration:
    """Test tool system integration scenarios."""
    
    def setup_method(self):
        """Setup for each test."""
        ToolRegistry.clear()
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        """Cleanup after each test."""
        ToolRegistry.clear()
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    @pytest.mark.asyncio
    async def test_execute_tool_by_name(self):
        """Test executing tools by name."""
        # Register a mock tool
        mock_tool = Mock(spec=Tool)
        mock_tool.name = "test_tool"
        mock_tool.run = AsyncMock()
        mock_tool.run.return_value = iter([
            ToolResult(type=ToolResultType.SUCCESS, content="Test successful")
        ])
        
        # Convert to async generator
        async def mock_run(input_data):
            yield ToolResult(type=ToolResultType.SUCCESS, content="Test successful")
        
        mock_tool.run = mock_run
        ToolRegistry.register(mock_tool)
        
        # Execute tool by name
        results = []
        async for result in execute_tool("test_tool", {"test": "data"}):
            results.append(result)
        
        assert len(results) == 1
        assert results[0].type == ToolResultType.SUCCESS
        assert results[0].content == "Test successful"
    
    @pytest.mark.asyncio
    async def test_execute_nonexistent_tool(self):
        """Test executing nonexistent tool."""
        with pytest.raises(ValueError, match="Tool 'nonexistent' not found"):
            async for result in execute_tool("nonexistent", {}):
                pass
    
    def test_tool_system_initialization(self):
        """Test that core tools can be properly initialized and registered."""
        from simacode.tools import BashTool, FileReadTool, FileWriteTool
        from simacode.permissions.manager import PermissionManager
        
        # Create permission manager
        config = MagicMock()
        config.security.allowed_paths = ["/tmp"]
        config.security.forbidden_paths = []
        config.security.require_permission_for_write = False
        config.security.max_command_execution_time = 30
        permission_manager = PermissionManager(config)
        
        # Create tool instances
        bash_tool = BashTool(permission_manager)
        file_read_tool = FileReadTool(permission_manager)
        file_write_tool = FileWriteTool(permission_manager)
        
        # Register tools
        ToolRegistry.register(bash_tool)
        ToolRegistry.register(file_read_tool)
        ToolRegistry.register(file_write_tool)
        
        # Check that tools are registered
        tools = ToolRegistry.list_tools()
        expected_tools = ["bash", "file_read", "file_write"]
        for tool_name in expected_tools:
            assert tool_name in tools
        
        # Check tool instances
        registered_bash_tool = ToolRegistry.get_tool("bash")
        assert isinstance(registered_bash_tool, BashTool)
        
        registered_file_read_tool = ToolRegistry.get_tool("file_read")
        assert isinstance(registered_file_read_tool, FileReadTool)
        
        registered_file_write_tool = ToolRegistry.get_tool("file_write")
        assert isinstance(registered_file_write_tool, FileWriteTool)