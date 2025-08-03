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
        
        # Try to get configuration (fallback to default if not available)
        try:
            from ..config import Config
            config = Config.load()
            context_config = config.conversation_context
        except Exception:
            # Fallback to default behavior if config loading fails
            return self._compact_conversation_with_recency_bias(history)
        
        # Apply strategy based on configuration
        if context_config.strategy == "full":
            return self._get_full_conversation_context(history, context_config)
        elif context_config.strategy == "compressed":
            return self._get_compressed_conversation_context(history, context_config)
        else:  # adaptive
            return self._compact_conversation_with_recency_bias(history)
    
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
        """使用配置的压缩策略处理上下文"""
        if len(history) <= config.recent_messages:
            # 消息较少时保留所有
            return self._format_all_messages(history)
        
        context_parts = []
        
        # 最近消息完整保留
        recent_messages = history[-config.recent_messages:]
        for msg in recent_messages:
            role_label = "User" if msg.role == "user" else "Assistant"
            context_parts.append(f"{role_label}: {msg.content}")
        
        # 中等最近消息压缩处理
        if len(history) > config.recent_messages:
            medium_start = max(0, len(history) - config.medium_recent)
            medium_end = len(history) - config.recent_messages
            medium_messages = history[medium_start:medium_end]
            
            if medium_messages:
                for msg in medium_messages:
                    role_label = "User" if msg.role == "user" else "Assistant"
                    # 按压缩比例截断内容
                    max_length = int(len(msg.content) * config.compression_ratio)
                    content = msg.content[:max_length] + "..." if len(msg.content) > max_length else msg.content
                    context_parts.insert(-config.recent_messages, f"{role_label}: {content}")
        
        # 更老的消息生成话题摘要
        if config.preserve_topics and len(history) > config.medium_recent:
            older_messages = history[:-config.medium_recent]
            topic_summary = self._compress_older_messages(older_messages)
            if topic_summary:
                context_parts.insert(0, f"[Earlier conversation summary]: {topic_summary}")
        
        formatted_context = "\n".join(context_parts)
        return self._ensure_token_limit(formatted_context, config.max_tokens)
    
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
    
    def _categorize_messages_by_importance(self, messages: List[Message]) -> Dict[str, List[Message]]:
        """
        按重要性对消息分层：
        - critical: 包含错误、决策、问题解决的消息
        - important: 包含关键操作、功能实现的消息  
        - background: 一般性对话和背景信息
        """
        categories = {
            'critical': [],
            'important': [],
            'background': []
        }
        
        for msg in messages:
            content = msg.content.lower()
            importance_score = self._calculate_message_importance(content)
            
            if importance_score >= 0.8:
                categories['critical'].append(msg)
            elif importance_score >= 0.5:
                categories['important'].append(msg)
            else:
                categories['background'].append(msg)
        
        return categories
    
    def _calculate_message_importance(self, content: str) -> float:
        """
        计算消息的重要性得分 (0.0 - 1.0)
        基于关键词、消息类型和内容特征
        """
        importance_score = 0.0
        
        # 高重要性关键词 (+0.4)
        critical_keywords = [
            'error', 'failed', 'problem', 'issue', 'bug', 'critical', 'urgent',
            'decision', 'important', 'solution', 'fix', 'resolve',
            '错误', '失败', '问题', '故障', '关键', '重要', '决定', '解决'
        ]
        for keyword in critical_keywords:
            if keyword in content:
                importance_score += 0.4
                break
        
        # 中等重要性关键词 (+0.3)
        important_keywords = [
            'implement', 'create', 'modify', 'update', 'configure', 'setup',
            'function', 'class', 'method', 'api', 'database', 'deploy',
            '实现', '创建', '修改', '更新', '配置', '设置', '部署'
        ]
        for keyword in important_keywords:
            if keyword in content:
                importance_score += 0.3
                break
        
        # 任务导向关键词 (+0.2)
        task_keywords = [
            'task', 'todo', 'need to', 'should', 'must', 'will', 'plan',
            '任务', '需要', '应该', '必须', '计划', '打算'
        ]
        for keyword in task_keywords:
            if keyword in content:
                importance_score += 0.2
                break
        
        # 问题提问模式 (+0.2)
        question_patterns = ['how to', 'what is', 'why', 'where', '如何', '什么是', '为什么', '在哪里']
        if any(pattern in content for pattern in question_patterns):
            importance_score += 0.2
        
        # 代码相关内容 (+0.15)
        code_indicators = ['function', 'class', 'def ', 'import', 'from ', '```', 'code']
        if any(indicator in content for indicator in code_indicators):
            importance_score += 0.15
        
        # 长消息通常更重要 (+0.1 for >200 chars)
        if len(content) > 200:
            importance_score += 0.1
        
        return min(importance_score, 1.0)  # 确保不超过1.0
    
    def _extract_topics_from_messages(self, messages: List[Message]) -> set:
        """从消息中提取关键话题"""
        topics = set()
        
        for msg in messages:
            content = msg.content.lower()
            
            # 技术话题识别
            if any(keyword in content for keyword in ["file", "code", "function", "class", "variable", "代码", "文件", "函数"]):
                topics.add("代码开发")
            if any(keyword in content for keyword in ["test", "debug", "error", "fix", "测试", "调试", "错误", "修复"]):
                topics.add("测试调试")
            if any(keyword in content for keyword in ["search", "find", "locate", "grep", "搜索", "查找", "定位"]):
                topics.add("搜索操作")
            if any(keyword in content for keyword in ["create", "write", "add", "new", "创建", "写入", "添加", "新建"]):
                topics.add("创建操作")
            if any(keyword in content for keyword in ["config", "setup", "install", "deploy", "配置", "设置", "安装", "部署"]):
                topics.add("系统配置")
            if any(keyword in content for keyword in ["api", "service", "server", "client", "服务", "接口"]):
                topics.add("服务开发")
            if any(keyword in content for keyword in ["database", "data", "sql", "query", "数据库", "数据", "查询"]):
                topics.add("数据处理")
        
        return topics
    
    def _compress_older_messages(self, older_messages: List[Message]) -> str:
        """
        Compress older messages to key themes and topics with priority handling.
        
        Args:
            older_messages: Messages from earlier in conversation
            
        Returns:
            str: Compressed summary of key themes with priority
        """
        if not older_messages:
            return ""
        
        # Categorize messages by importance
        categorized = self._categorize_messages_by_importance(older_messages)
        
        # Build compressed summary prioritizing important information
        summary_parts = []
        
        # High priority: Critical decisions and errors
        critical_messages = categorized['critical']
        if critical_messages:
            critical_summary = []
            for msg in critical_messages[-2:]:  # Last 2 critical messages
                if msg.role == "user":
                    summary = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
                    critical_summary.append(f"Critical: {summary}")
            if critical_summary:
                summary_parts.extend(critical_summary)
        
        # Medium priority: Important topics and actions
        important_messages = categorized['important']
        if important_messages:
            topics = self._extract_topics_from_messages(important_messages)
            if topics:
                summary_parts.append(f"Key topics: {', '.join(sorted(topics))}")
        
        # Low priority: General conversation themes
        if categorized['background']:
            general_topics = self._extract_topics_from_messages(categorized['background'])
            if general_topics and len(summary_parts) < 3:  # Only if we have space
                summary_parts.append(f"Background: {', '.join(list(general_topics)[:3])}")
        
        return " | ".join(summary_parts) if summary_parts else "General conversation"