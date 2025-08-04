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
        """Create conversation summary using configurable strategy."""
        if not history:
            return "No prior conversation"
        
        # 获取配置，使用安全的默认值处理
        context_config = self._get_safe_context_config()
        
        # 统一使用智能压缩作为默认策略
        if context_config.strategy == "full":
            return self._get_full_conversation_context(history, context_config)
        else:  # compressed, adaptive, 或任何其他值都使用智能压缩
            return self._get_compressed_conversation_context(history, context_config)
    
    def _get_safe_context_config(self):
        """安全获取配置，确保总是有有效的默认值"""
        try:
            from ..config import Config
            config = Config.load()
            context_config = config.conversation_context
            
            # 确保 strategy 有有效值
            if not hasattr(context_config, 'strategy') or not context_config.strategy:
                context_config.strategy = "compressed"  # 默认使用智能压缩
            
            # 记录使用的策略
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"Using conversation context strategy: {context_config.strategy}")
            
            return context_config
        except Exception as e:
            # 创建最小可用配置
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to load conversation context config: {e}, using default compressed strategy")
            
            from ..config import ConversationContextConfig
            return ConversationContextConfig(strategy="compressed")
    
    def _get_full_conversation_context(self, history: List[Message], config) -> str:
        """保留完整对话上下文，只在必要时截断"""
        if not history:
            return "No prior conversation"
        
        # 根据配置决定保留策略
        if config.preserve_all:
            # 保留所有消息
            return self._format_all_messages(history)
        
        # 按消息数量限制截断
        if len(history) > config.max_messages:
            # 保留最近的N条消息
            recent_history = history[-config.max_messages:]
            truncated_count = len(history) - config.max_messages
            context = f"[Earlier conversation truncated: {truncated_count} messages]\n\n"
            context += self._format_all_messages(recent_history)
            
            # 检查token限制
            return self._ensure_token_limit(context, config.max_tokens)
        
        formatted_context = self._format_all_messages(history)
        return self._ensure_token_limit(formatted_context, config.max_tokens)
    
    def _get_compressed_conversation_context(self, history: List[Message], config) -> str:
        """智能分层压缩：根据重要性和token预算智能分层处理对话历史"""
        if not history:
            return "No prior conversation"
        
        if len(history) <= config.recent_messages:
            # 消息较少时保留所有
            return self._format_all_messages(history)
        
        # 使用精简的智能分层压缩算法
        return self._adaptive_context_compression(history, config)
    
    def _adaptive_context_compression(self, history: List[Message], config) -> str:
        """自适应上下文压缩，根据token预算智能分层"""
        
        # 按重要性分层
        layers = self._categorize_messages_by_importance(history)
        
        context_parts = []
        used_tokens = 0
        token_budget = getattr(config, 'token_budget', 4000)  # 默认4000
        
        # 优先级1: 最近3条消息（完整保留）
        for msg in layers['critical'][-3:]:
            if used_tokens < token_budget * 0.6:  # 60%预算给最近消息
                role_label = "User" if msg.role == "user" else "Assistant"
                formatted_msg = f"{role_label}: {msg.content}"
                context_parts.append(formatted_msg)
                used_tokens += len(msg.content) // 4  # 粗略token估算
        
        # 优先级2: 重要决策点和关键信息
        for msg in layers['important']:
            if used_tokens < token_budget * 0.9:  # 90%预算
                compressed = self._compress_message(msg, compression_level=0.5)
                context_parts.append(compressed)
                used_tokens += len(compressed) // 4
        
        # 优先级3: 话题摘要
        if used_tokens < token_budget:
            topic_summary = self._extract_topic_summary(layers['background'])
            if topic_summary:
                context_parts.insert(0, f"[Session Summary]: {topic_summary}")
        
        return "\n".join(context_parts)
    
    def _categorize_messages_by_importance(self, history: List[Message]) -> Dict[str, List[Message]]:
        """按重要性对消息分层"""
        layers = {
            'critical': [],    # 最近的消息
            'important': [],   # 包含关键决策的消息
            'background': []   # 背景信息
        }
        
        for i, msg in enumerate(history):
            # 最近的消息标记为关键
            if i >= len(history) - 5:
                layers['critical'].append(msg)
            # 包含特定关键词的消息标记为重要
            elif any(keyword in msg.content.lower() for keyword in [
                'decision', 'important', 'error', 'problem', 'solution', 
                '决定', '重要', '错误', '问题', '解决'
            ]):
                layers['important'].append(msg)
            else:
                layers['background'].append(msg)
        
        return layers
    
    def _compress_message(self, msg: Message, compression_level: float) -> str:
        """压缩单条消息"""
        role_label = "User" if msg.role == "user" else "Assistant"
        max_length = int(len(msg.content) * compression_level)
        
        if len(msg.content) <= max_length:
            return f"{role_label}: {msg.content}"
        
        # 简单截断并添加省略号
        content = msg.content[:max_length] + "..."
        return f"{role_label}: {content}"
    
    def _extract_topic_summary(self, messages: List[Message]) -> str:
        """提取话题摘要"""
        if not messages:
            return ""
        
        # 提取关键主题词汇
        topics = self._extract_topics_from_messages(messages)
        
        if not topics:
            return ""
        
        # 构建简洁的话题摘要
        topic_list = list(topics)[:3]  # 最多3个话题
        return f"Discussion topics: {', '.join(topic_list)}"
    
    def _extract_topics_from_messages(self, messages: List[Message]) -> set:
        """从消息中提取关键话题（精简版）"""
        topics = set()
        
        for msg in messages:
            content = msg.content.lower()
            
            # 简化的话题识别
            if any(keyword in content for keyword in ["code", "function", "class", "代码", "函数"]):
                topics.add("代码开发")
            if any(keyword in content for keyword in ["error", "problem", "fix", "错误", "问题", "修复"]):
                topics.add("问题解决")
            if any(keyword in content for keyword in ["create", "build", "implement", "创建", "构建", "实现"]):
                topics.add("功能实现")
            if any(keyword in content for keyword in ["config", "setup", "install", "配置", "设置", "安装"]):
                topics.add("系统配置")
        
        return topics
    
    def _format_all_messages(self, messages: List[Message]) -> str:
        """格式化所有消息为完整上下文"""
        formatted = []
        for i, msg in enumerate(messages, 1):
            role_label = "User" if msg.role == "user" else "Assistant"
            # 添加消息序号以便追踪
            formatted.append(f"[{i}] {role_label}: {msg.content}")
        return "\n".join(formatted)
    
    def _ensure_token_limit(self, context: str, max_tokens: int) -> str:
        """确保上下文不超过token限制"""
        # 粗略估算：1 token ≈ 4 characters
        estimated_tokens = len(context) // 4
        
        if estimated_tokens <= max_tokens:
            return context
        
        # 截断到安全长度（保留90%安全边际）
        safe_length = int(max_tokens * 4 * 0.9)
        truncated_context = context[:safe_length]
        
        # 在合适的位置截断（避免在消息中间截断）
        last_newline = truncated_context.rfind('\n')
        if last_newline > safe_length * 0.8:  # 如果最后一个换行符位置合理
            truncated_context = truncated_context[:last_newline]
        
        return truncated_context + "\n[Context truncated due to token limit]"
    
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
    
