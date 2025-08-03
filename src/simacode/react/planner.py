"""
Task Planning Module for ReAct Engine

This module implements task planning capabilities, including task decomposition,
tool selection, and execution plan generation.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, AsyncGenerator

from pydantic import BaseModel, Field

from ..ai.base import AIClient, Role
from ..ai.conversation import Message
from ..tools import ToolRegistry
from .exceptions import PlanningError, InvalidTaskError


class TaskType(Enum):
    """Task type enumeration."""
    FILE_OPERATION = "file_operation"
    COMMAND_EXECUTION = "command_execution"
    CODE_ANALYSIS = "code_analysis"
    SEARCH_QUERY = "search_query"
    COMPOSITE = "composite"


class TaskStatus(Enum):
    """Task execution status."""
    PENDING = "pending"
    PLANNING = "planning"
    READY = "ready"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """
    Represents a single task in the ReAct engine.
    
    A task encapsulates all information needed to execute a specific operation,
    including the required tool, input parameters, and expected outcomes.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: TaskType = TaskType.FILE_OPERATION
    description: str = ""
    tool_name: str = ""
    tool_input: Dict[str, Any] = field(default_factory=dict)
    expected_outcome: str = ""
    dependencies: List[str] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    priority: int = 1  # 1 = highest, 5 = lowest
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary format."""
        return {
            "id": self.id,
            "type": self.type.value,
            "description": self.description,
            "tool_name": self.tool_name,
            "tool_input": self.tool_input,
            "expected_outcome": self.expected_outcome,
            "dependencies": self.dependencies,
            "status": self.status.value,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """Create task from dictionary."""
        task = cls()
        task.id = data.get("id", task.id)
        task.type = TaskType(data.get("type", task.type.value))
        task.description = data.get("description", "")
        task.tool_name = data.get("tool_name", "")
        task.tool_input = data.get("tool_input", {})
        task.expected_outcome = data.get("expected_outcome", "")
        task.dependencies = data.get("dependencies", [])
        task.status = TaskStatus(data.get("status", task.status.value))
        task.priority = data.get("priority", 1)
        task.metadata = data.get("metadata", {})
        
        if "created_at" in data:
            task.created_at = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data:
            task.updated_at = datetime.fromisoformat(data["updated_at"])
            
        return task
    
    def update_status(self, status: TaskStatus):
        """Update task status and timestamp."""
        self.status = status
        self.updated_at = datetime.now()


class PlanningContext(BaseModel):
    """Context information for task planning."""
    user_input: str = ""
    conversation_history: List[Message] = Field(default_factory=list)
    available_tools: List[str] = Field(default_factory=list)
    project_context: Dict[str, Any] = Field(default_factory=dict)
    constraints: Dict[str, Any] = Field(default_factory=dict)


class TaskPlanner:
    """
    Task planner for the ReAct engine.
    
    The TaskPlanner is responsible for analyzing user input, understanding intent,
    and creating executable task plans using available tools.
    """
    
    def __init__(self, ai_client: AIClient):
        """Initialize the task planner."""
        self.ai_client = ai_client
        self.tool_registry = ToolRegistry()
        
        # Planning prompts
        self.PLANNING_SYSTEM_PROMPT = """
You are a task planning expert for an AI programming assistant. Your role is to:

1. FIRST: Determine if the user input is conversational or task-oriented
2. If conversational: Respond directly with helpful conversation
3. If task-oriented: Break down into executable tasks with appropriate tools

## INPUT CLASSIFICATION ##

CONVERSATIONAL inputs include:
- Greetings: "你好", "hello", "hi", "嗨"
- Gratitude: "谢谢", "thanks", "thank you", "感谢"
- Simple confirmations: "好的", "可以", "ok", "yes", "no", "确认", "取消"
- Social pleasantries: "怎么样", "如何", "最近好吗"
- General questions without specific tasks: "什么", "why", "how"
- Small talk or casual conversation

TASK-ORIENTED inputs include:
- File operations: "读取文件", "创建文件", "修改代码"
- System commands: "运行测试", "启动服务", "检查状态"
- Code analysis: "分析代码", "查找函数", "检查错误"
- Search operations: "搜索", "查找", "定位"
- Any request requiring tool execution

## RESPONSE FORMAT ##

For CONVERSATIONAL inputs, respond with:
{{
  "type": "conversational_response",
  "content": "Your natural, helpful response to the user"
}}

For TASK-ORIENTED inputs, respond with:
{{
  "type": "task_plan",
  "tasks": [
    {{
      "type": "file_operation",
      "description": "Read the contents of config.py", 
      "tool_name": "file_read",
      "tool_input": {{"file_path": "config.py"}},
      "expected_outcome": "File contents successfully retrieved",
      "dependencies": [],
      "priority": 1
    }}
  ]
}}

Available tools:
{available_tools}

For tasks, specify:
- Task type (file_operation, command_execution, code_analysis, search_query, composite)
- Tool name from available tools
- Tool input parameters  
- Expected outcome description
- Dependencies on other tasks (if any)
- Priority level (1-5, where 1 is highest)

Be specific and actionable. Consider edge cases and error handling.
Always classify the input type first, then respond appropriately.
"""
    
    async def plan_tasks(self, context: PlanningContext) -> List[Task]:
        """
        Create a task plan based on user input and context.
        
        Args:
            context: Planning context containing user input and environment info
            
        Returns:
            List[Task]: Ordered list of tasks to execute. Empty list for conversational inputs.
            
        Raises:
            PlanningError: If task planning fails
        """
        try:
            # Get available tools
            available_tools = self._get_available_tools_description()
            
            # Prepare planning prompt
            system_prompt = self.PLANNING_SYSTEM_PROMPT.format(
                available_tools=available_tools
            )
            
            # Create planning messages
            messages = [
                Message(role=Role.SYSTEM, content=system_prompt),
                Message(role=Role.USER, content=f"User request: {context.user_input}")
            ]
            
            # Add conversation history if available
            if context.conversation_history:
                history_summary = self._summarize_conversation_history(context.conversation_history)
                messages.append(Message(role=Role.USER, content=f"Conversation context: {history_summary}"))
            
            # Get AI response
            response = await self.ai_client.chat(messages)
            
            # Parse response - could be tasks or conversational
            result = await self._parse_planning_response(response.content)
            
            if result["type"] == "conversational_response":
                # Store conversational response in context for the engine to use
                context.constraints["conversational_response"] = result["content"]
                return []  # Return empty task list for conversational inputs
            
            # Parse and validate tasks for task-oriented inputs
            tasks = result["tasks"]
            validated_tasks = await self._validate_and_enhance_tasks(tasks, context)
            
            return validated_tasks
            
        except Exception as e:
            raise PlanningError(
                f"Failed to plan tasks: {str(e)}",
                user_input=context.user_input,
                context={"error_type": type(e).__name__}
            )
    
    async def replan_task(self, failed_task: Task, error_info: Dict[str, Any], context: PlanningContext) -> List[Task]:
        """
        Create alternative tasks when a task fails.
        
        Args:
            failed_task: The task that failed
            error_info: Information about the failure
            context: Current planning context
            
        Returns:
            List[Task]: Alternative tasks to try
        """
        try:
            replan_prompt = f"""
The following task failed:
Task: {failed_task.description}
Tool: {failed_task.tool_name}
Error: {error_info.get('error', 'Unknown error')}

Please suggest alternative approaches to accomplish the same goal.
Consider:
1. Different tools that might work
2. Breaking down the task into smaller steps
3. Working around the specific error

Respond with a JSON array of alternative task objects.
"""
            
            messages = [
                Message(role=Role.SYSTEM, content=self.PLANNING_SYSTEM_PROMPT.format(
                    available_tools=self._get_available_tools_description()
                )),
                Message(role=Role.USER, content=replan_prompt)
            ]
            
            response = await self.ai_client.chat(messages)
            alternative_tasks = await self._parse_tasks_from_response(response.content)
            
            return await self._validate_and_enhance_tasks(alternative_tasks, context)
            
        except Exception as e:
            raise PlanningError(
                f"Failed to replan task: {str(e)}",
                context={"failed_task_id": failed_task.id, "error_info": error_info}
            )
    
    def _get_available_tools_description(self) -> str:
        """Get formatted description of available tools."""
        tools = self.tool_registry.get_all_tools()
        descriptions = []
        
        for tool_name, tool in tools.items():
            descriptions.append(f"- {tool_name}: {tool.description}")
        
        return "\n".join(descriptions)
    
    def _summarize_conversation_history(self, history: List[Message]) -> str:
        """Create a concise summary of conversation history."""
        if not history:
            return "No prior conversation"
        
        # Take last few messages for context
        recent_messages = history[-5:] if len(history) > 5 else history
        summary_parts = []
        
        for msg in recent_messages:
            role_label = "User" if msg.role == "user" else "Assistant"
            content_preview = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
            summary_parts.append(f"{role_label}: {content_preview}")
        
        return "\n".join(summary_parts)
    
    async def _parse_planning_response(self, response_content: str) -> Dict[str, Any]:
        """Parse planning response that can be either conversational or task-oriented."""
        try:
            # Extract JSON from response
            response_content = response_content.strip()
            
            # Handle markdown code blocks
            if "```json" in response_content:
                start = response_content.find("```json") + 7
                end = response_content.find("```", start)
                response_content = response_content[start:end].strip()
            elif "```" in response_content:
                start = response_content.find("```") + 3
                end = response_content.find("```", start)
                response_content = response_content[start:end].strip()
            
            # Parse JSON
            parsed_data = json.loads(response_content)
            
            if parsed_data.get("type") == "conversational_response":
                return {
                    "type": "conversational_response",
                    "content": parsed_data.get("content", "")
                }
            elif parsed_data.get("type") == "task_plan":
                # Parse task list
                task_data = parsed_data.get("tasks", [])
                tasks = await self._parse_task_list(task_data)
                return {
                    "type": "task_plan", 
                    "tasks": tasks
                }
            else:
                # Legacy format - assume it's a task list
                if isinstance(parsed_data, list):
                    tasks = await self._parse_task_list(parsed_data)
                    return {
                        "type": "task_plan",
                        "tasks": tasks
                    }
                else:
                    raise ValueError("Invalid response format")
            
        except json.JSONDecodeError as e:
            raise PlanningError(f"Failed to parse JSON response: {str(e)}")
        except Exception as e:
            raise PlanningError(f"Failed to parse planning response: {str(e)}")
    
    async def _parse_task_list(self, task_data: List[Dict[str, Any]]) -> List[Task]:
        """Parse a list of task dictionaries into Task objects."""
        if not isinstance(task_data, list):
            raise ValueError("Task data must be a JSON array")
        
        tasks = []
        for i, task_dict in enumerate(task_data):
            try:
                task = Task()
                task.type = TaskType(task_dict.get("type", "file_operation"))
                task.description = task_dict.get("description", f"Task {i+1}")
                task.tool_name = task_dict.get("tool_name", "")
                task.tool_input = task_dict.get("tool_input", {})
                task.expected_outcome = task_dict.get("expected_outcome", "")
                task.dependencies = task_dict.get("dependencies", [])
                task.priority = task_dict.get("priority", 1)
                task.status = TaskStatus.READY
                
                tasks.append(task)
                
            except Exception as e:
                raise InvalidTaskError(f"Invalid task definition at index {i}: {str(e)}")
        
        return tasks

    async def _parse_tasks_from_response(self, response_content: str) -> List[Task]:
        """Parse task list from AI response (legacy method for compatibility)."""
        result = await self._parse_planning_response(response_content)
        if result["type"] == "conversational_response":
            return []  # No tasks for conversational responses
        return result["tasks"]
    
    async def _validate_and_enhance_tasks(self, tasks: List[Task], context: PlanningContext) -> List[Task]:
        """Validate task definitions and enhance with additional information."""
        validated_tasks = []
        available_tools = self.tool_registry.list_tools()
        
        for task in tasks:
            # Validate tool exists
            if task.tool_name not in available_tools:
                raise InvalidTaskError(f"Tool '{task.tool_name}' not found in registry")
            
            # Validate tool input schema
            tool = self.tool_registry.get_tool(task.tool_name)
            if tool:
                try:
                    # This will raise ValidationError if input is invalid
                    await tool.validate_input(task.tool_input)
                except Exception as e:
                    raise InvalidTaskError(f"Invalid input for tool '{task.tool_name}': {str(e)}")
            
            # Add metadata
            task.metadata.update({
                "planner_version": "1.0.0",
                "context_user_input": context.user_input,
                "available_tools_count": len(available_tools)
            })
            
            validated_tasks.append(task)
        
        # Sort by priority and dependencies
        return self._sort_tasks_by_execution_order(validated_tasks)
    
    def _sort_tasks_by_execution_order(self, tasks: List[Task]) -> List[Task]:
        """Sort tasks based on dependencies and priority."""
        # Create a dependency graph
        task_map = {task.id: task for task in tasks}
        sorted_tasks = []
        visited = set()
        
        def visit_task(task_id: str):
            if task_id in visited:
                return
            
            task = task_map.get(task_id)
            if not task:
                return
            
            # Visit dependencies first
            for dep_id in task.dependencies:
                visit_task(dep_id)
            
            visited.add(task_id)
            sorted_tasks.append(task)
        
        # Visit all tasks
        for task in sorted(tasks, key=lambda t: t.priority):
            visit_task(task.id)
        
        return sorted_tasks