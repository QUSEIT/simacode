"""
ReAct Engine Core Implementation

This module implements the core ReAct (Reasoning and Acting) engine that
orchestrates the complete cycle of task understanding, planning, execution,
and evaluation.
"""

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional

from ..ai.base import AIClient, Role
from ..ai.conversation import Message
from ..tools import ToolRegistry, execute_tool, ToolResult, ToolResultType
from .planner import TaskPlanner, Task, TaskStatus, PlanningContext
from .evaluator import ResultEvaluator, EvaluationResult, EvaluationOutcome, EvaluationContext
from .exceptions import ReActError, ExecutionError, MaxRetriesExceededError

logger = logging.getLogger(__name__)


class ReActState(Enum):
    """ReAct engine execution state."""
    IDLE = "idle"
    REASONING = "reasoning"
    PLANNING = "planning"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    REPLANNING = "replanning"
    COMPLETED = "completed"
    FAILED = "failed"


class ExecutionMode(Enum):
    """Execution mode for the ReAct engine."""
    SEQUENTIAL = "sequential"  # Execute tasks one by one
    PARALLEL = "parallel"      # Execute independent tasks in parallel
    ADAPTIVE = "adaptive"      # Automatically choose based on dependencies


@dataclass
class ReActSession:
    """
    Represents a ReAct execution session.
    
    Contains all state and context information for a single ReAct cycle,
    including user input, tasks, results, and execution history.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_input: str = ""
    state: ReActState = ReActState.IDLE
    tasks: List[Task] = field(default_factory=list)
    current_task_index: int = 0
    task_results: Dict[str, List[ToolResult]] = field(default_factory=dict)
    evaluations: Dict[str, EvaluationResult] = field(default_factory=dict)
    conversation_history: List[Message] = field(default_factory=list)
    execution_log: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    retry_count: int = 0
    max_retries: int = 3
    
    def add_log_entry(self, message: str, level: str = "INFO"):
        """Add entry to execution log."""
        timestamp = datetime.now().isoformat()
        log_entry = f"[{timestamp}] {level}: {message}"
        self.execution_log.append(log_entry)
        self.updated_at = datetime.now()
    
    def update_state(self, new_state: ReActState):
        """Update session state and log the change."""
        old_state = self.state
        self.state = new_state
        self.updated_at = datetime.now()
        self.add_log_entry(f"State changed from {old_state.value} to {new_state.value}")
    
    def get_current_task(self) -> Optional[Task]:
        """Get the current task being executed."""
        if 0 <= self.current_task_index < len(self.tasks):
            return self.tasks[self.current_task_index]
        return None
    
    def advance_to_next_task(self) -> bool:
        """Advance to the next task. Returns True if there are more tasks."""
        self.current_task_index += 1
        return self.current_task_index < len(self.tasks)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary format."""
        return {
            "id": self.id,
            "user_input": self.user_input,
            "state": self.state.value,
            "tasks": [task.to_dict() for task in self.tasks],
            "current_task_index": self.current_task_index,
            "task_results": {
                task_id: [result.to_dict() for result in results]
                for task_id, results in self.task_results.items()
            },
            "evaluations": {
                task_id: eval_result.to_dict()
                for task_id, eval_result in self.evaluations.items()
            },
            "conversation_history": [msg.to_dict() for msg in self.conversation_history],
            "execution_log": self.execution_log,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "retry_count": self.retry_count,
            "max_retries": self.max_retries
        }


class ReActEngine:
    """
    Core ReAct (Reasoning and Acting) Engine.
    
    The ReActEngine orchestrates the complete cycle of:
    1. Reasoning: Understanding user input and context
    2. Planning: Creating executable task plans
    3. Acting: Executing tools and operations
    4. Evaluating: Assessing results and determining next actions
    5. Replanning: Adjusting plans based on results
    """
    
    def __init__(self, ai_client: AIClient, execution_mode: ExecutionMode = ExecutionMode.ADAPTIVE):
        """
        Initialize the ReAct engine.
        
        Args:
            ai_client: AI client for reasoning and evaluation
            execution_mode: How to execute tasks (sequential, parallel, adaptive)
        """
        self.ai_client = ai_client
        self.execution_mode = execution_mode
        self.task_planner = TaskPlanner(ai_client)
        self.result_evaluator = ResultEvaluator(ai_client)
        self.tool_registry = ToolRegistry()
        
        # Engine configuration
        self.max_planning_retries = 3
        self.max_execution_retries = 3
        self.parallel_task_limit = 5
        
        logger.info(f"ReAct engine initialized with {execution_mode.value} execution mode")
    
    async def _is_conversational_input(self, user_input: str) -> bool:
        """
        判断输入是否为对话性输入（问候、感谢等），不需要工具执行。
        
        Args:
            user_input: 用户输入文本
            
        Returns:
            bool: True if input is conversational, False if it requires task execution
        """
        user_input_clean = user_input.strip()
        
        # 快速模式匹配常见对话性输入
        conversational_patterns = [
            # 中文问候
            r'^(你好|您好|嗨|嗯|哦|啊)([！!。.]*)$',
            # 英文问候  
            r'^(hi|hello|hey|hm|oh|ah)([！!。.]*)$',
            # 感谢表达
            r'^(谢谢|感谢|thanks?|thank you)([！!。.]*)$',
            # 简单确认/回应
            r'^(好的|可以|行|ok|okay|yes|no|是的|不是)([！!。.]*)$',
            # 简单疑问
            r'^(什么|why|how|怎么样|如何)([？?。.]*)$',
        ]
        
        # 检查是否匹配常见模式
        for pattern in conversational_patterns:
            if re.match(pattern, user_input_clean, re.IGNORECASE):
                logger.debug(f"Input '{user_input}' matched conversational pattern: {pattern}")
                return True
        
        # 对于不匹配模式的输入，使用AI进行智能判断
        try:
            classification_prompt = f"""判断以下用户输入是否为纯对话性内容还是需要执行具体任务的请求。

对话性内容包括：问候、感谢、简单确认、闲聊等，不需要使用任何工具。
任务性内容包括：文件操作、搜索查询、代码分析、网站操作等，需要使用工具完成。

用户输入："{user_input}"

请只回复以下之一：
- CONVERSATIONAL (如果是对话性内容)
- TASK (如果需要执行任务)"""
            
            messages = [Message(role=Role.USER, content=classification_prompt)]
            response = await self.ai_client.chat(messages)
            
            is_conversational = "CONVERSATIONAL" in response.content.upper()
            logger.debug(f"AI classification for '{user_input}': {'CONVERSATIONAL' if is_conversational else 'TASK'}")
            return is_conversational
            
        except Exception as e:
            logger.warning(f"Failed to classify input with AI: {str(e)}, defaulting to task mode")
            return False  # 默认为任务模式，避免遗漏需要处理的任务
    
    async def process_user_input(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process user input through the complete ReAct cycle.
        
        Args:
            user_input: User's natural language input
            context: Additional context information
            
        Yields:
            Dict[str, Any]: Status updates and results from each phase
        """
        session = ReActSession(user_input=user_input)
        
        if context:
            session.metadata.update(context)
        
        try:
            session.add_log_entry(f"Starting ReAct processing for input: {user_input[:100]}...")
            yield self._create_status_update(session, "ReAct processing started")
            
            # 预判断：检查是否为对话性输入
            if await self._is_conversational_input(user_input):
                session.add_log_entry("Input identified as conversational, providing direct response")
                yield self._create_status_update(session, "Providing conversational response")
                
                # 直接使用AI客户端回复，不进入任务规划
                try:
                    conversational_messages = [
                        Message(role=Role.SYSTEM, content="你是一个友好的AI助手。用自然、简洁的方式回复用户的问候、感谢或简单对话。"),
                        Message(role=Role.USER, content=user_input)
                    ]
                    response = await self.ai_client.chat(conversational_messages)
                    
                    session.update_state(ReActState.COMPLETED)
                    session.add_log_entry("Conversational response completed")
                    
                    # 返回对话性回复结果
                    yield {
                        "type": "conversational_response",
                        "content": response.content,
                        "session_id": session.id,
                        "is_final": True,
                        "metadata": {
                            "input_type": "conversational",
                            "response_time": (datetime.now() - session.created_at).total_seconds()
                        }
                    }
                    return
                    
                except Exception as e:
                    logger.error(f"Failed to generate conversational response: {str(e)}")
                    # 如果对话回复失败，继续正常的ReAct流程
                    session.add_log_entry(f"Conversational response failed: {str(e)}, falling back to task mode", "WARNING")
            
            # Phase 1: Reasoning and Planning
            async for update in self._reasoning_and_planning_phase(session):
                yield update
            
            # Phase 2: Execution and Evaluation
            async for update in self._execution_and_evaluation_phase(session):
                yield update
            
            # Phase 3: Final Assessment
            async for update in self._final_assessment_phase(session):
                yield update
            
            session.update_state(ReActState.COMPLETED)
            yield self._create_final_result(session)
            
        except Exception as e:
            session.update_state(ReActState.FAILED)
            session.add_log_entry(f"ReAct processing failed: {str(e)}", "ERROR")
            
            yield {
                "type": "error",
                "content": f"ReAct processing failed: {str(e)}",
                "session_id": session.id,
                "error_type": type(e).__name__
            }
            
            logger.error(f"ReAct processing failed: {str(e)}", exc_info=True)
    
    async def _reasoning_and_planning_phase(self, session: ReActSession) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute the reasoning and planning phase."""
        session.update_state(ReActState.REASONING)
        yield self._create_status_update(session, "Analyzing user input and reasoning about approach")
        
        # Create planning context
        planning_context = PlanningContext(
            user_input=session.user_input,
            conversation_history=session.conversation_history,
            available_tools=self.tool_registry.list_tools(),
            project_context=session.metadata.get("project_context", {}),
            constraints=session.metadata.get("constraints", {})
        )
        
        # Attempt task planning with retries
        planning_attempts = 0
        while planning_attempts < self.max_planning_retries:
            try:
                session.update_state(ReActState.PLANNING)
                yield self._create_status_update(session, f"Creating task plan (attempt {planning_attempts + 1})")
                
                # Plan tasks
                tasks = await self.task_planner.plan_tasks(planning_context)
                session.tasks = tasks
                
                session.add_log_entry(f"Successfully planned {len(tasks)} tasks")
                yield self._create_status_update(session, f"Task plan created with {len(tasks)} tasks")
                
                # Yield task plan details
                yield {
                    "type": "task_plan",
                    "content": "Task plan created",
                    "session_id": session.id,
                    "tasks": [task.to_dict() for task in tasks]
                }
                
                # 🆕 Add task_init message for each task
                for task_index, task in enumerate(tasks, 1):
                    tools_list = [task.tool_name] if task.tool_name else []
                    task_init_content = f"Task {task_index} initialized: {task.description} 将会通过调用 {tools_list} 来完成"
                    
                    yield {
                        "type": "task_init",
                        "content": task_init_content,
                        "session_id": session.id,
                        "task_id": task.id,
                        "task_description": task.description,
                        "task_index": task_index,
                        "tools": tools_list,
                        "metadata": {
                            "task_type": "react_task",
                            "initialization": True
                        }
                    }
                
                break
                
            except Exception as e:
                planning_attempts += 1
                session.add_log_entry(f"Planning attempt {planning_attempts} failed: {str(e)}", "WARNING")
                
                if planning_attempts >= self.max_planning_retries:
                    raise ReActError(f"Failed to create task plan after {self.max_planning_retries} attempts: {str(e)}")
                
                # Wait before retry
                await asyncio.sleep(1)
    
    async def _execution_and_evaluation_phase(self, session: ReActSession) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute tasks and evaluate results."""
        if not session.tasks:
            # Handle conversational inputs that don't require task execution
            session.add_log_entry("No tasks to execute - treating as conversational input")
            yield self._create_status_update(session, "No specific tasks identified - providing conversational response")
            
            # Create a conversational response using the AI client
            response = await self._generate_conversational_response(session)
            yield {
                "type": "conversational_response",
                "content": response,
                "session_id": session.id
            }
            return
        
        session.update_state(ReActState.EXECUTING)
        
        if self.execution_mode == ExecutionMode.SEQUENTIAL:
            async for update in self._execute_tasks_sequentially(session):
                yield update
        elif self.execution_mode == ExecutionMode.PARALLEL:
            async for update in self._execute_tasks_in_parallel(session):
                yield update
        else:  # ADAPTIVE
            async for update in self._execute_tasks_adaptively(session):
                yield update
    
    async def _execute_tasks_sequentially(self, session: ReActSession) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute tasks one by one in sequence."""
        for i, task in enumerate(session.tasks):
            session.current_task_index = i
            
            yield self._create_status_update(session, f"Executing task {i+1}/{len(session.tasks)}: {task.description}")
            
            # Execute single task
            async for update in self._execute_single_task(session, task):
                yield update
            
            # Check if we should stop due to critical failure
            evaluation = session.evaluations.get(task.id)
            if evaluation and evaluation.outcome == EvaluationOutcome.FAILURE:
                critical_failure = any("critical" in rec.lower() for rec in evaluation.recommendations)
                if critical_failure:
                    session.add_log_entry(f"Stopping execution due to critical failure in task {task.id}", "WARNING")
                    break
    
    async def _execute_tasks_in_parallel(self, session: ReActSession) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute independent tasks in parallel."""
        # Group tasks by dependencies
        independent_tasks = [task for task in session.tasks if not task.dependencies]
        dependent_tasks = [task for task in session.tasks if task.dependencies]
        
        # Execute independent tasks in parallel
        if independent_tasks:
            yield self._create_status_update(session, f"Executing {len(independent_tasks)} independent tasks in parallel")
            
            # Limit concurrent tasks
            semaphore = asyncio.Semaphore(self.parallel_task_limit)
            
            async def execute_with_semaphore(task: Task):
                async with semaphore:
                    task_results = []
                    async for update in self._execute_single_task(session, task):
                        if update.get("type") == "sub_task_result":
                            task_results.append(update)
                    return task_results
            
            # Execute tasks concurrently
            task_coroutines = [execute_with_semaphore(task) for task in independent_tasks]
            results = await asyncio.gather(*task_coroutines, return_exceptions=True)
            
            # Process results
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    session.add_log_entry(f"Parallel task {independent_tasks[i].id} failed: {str(result)}", "ERROR")
                else:
                    yield self._create_status_update(session, f"Parallel task {independent_tasks[i].id} completed")
        
        # Execute dependent tasks sequentially
        for task in dependent_tasks:
            yield self._create_status_update(session, f"Executing dependent task: {task.description}")
            async for update in self._execute_single_task(session, task):
                yield update
    
    async def _execute_tasks_adaptively(self, session: ReActSession) -> AsyncGenerator[Dict[str, Any], None]:
        """Adaptively choose execution strategy based on task dependencies."""
        # Analyze task dependencies to determine best execution strategy
        has_dependencies = any(task.dependencies for task in session.tasks)
        
        if not has_dependencies and len(session.tasks) > 1:
            # Use parallel execution for independent tasks
            session.add_log_entry("Using parallel execution for independent tasks", "INFO")
            async for update in self._execute_tasks_in_parallel(session):
                yield update
        else:
            # Use sequential execution for dependent tasks
            session.add_log_entry("Using sequential execution due to task dependencies", "INFO")
            async for update in self._execute_tasks_sequentially(session):
                yield update
    
    async def _execute_single_task(self, session: ReActSession, task: Task) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute a single task with error handling and evaluation."""
        task.update_status(TaskStatus.EXECUTING)
        session.add_log_entry(f"Starting execution of task {task.id}: {task.description}")
        
        execution_attempts = 0
        while execution_attempts < self.max_execution_retries:
            try:
                # Execute tool
                tool_results = []
                async for result in execute_tool(task.tool_name, task.tool_input):
                    tool_results.append(result)
                    
                    # Yield progress updates
                    yield {
                        "type": "tool_progress",
                        "content": result.content,
                        "session_id": session.id,
                        "task_id": task.id,
                        "result_type": result.type.value
                    }
                
                # Store results
                session.task_results[task.id] = tool_results
                
                # Evaluate results
                session.update_state(ReActState.EVALUATING)
                evaluation_context = EvaluationContext(
                    task=task.to_dict(),
                    tool_results=[result.to_dict() for result in tool_results],
                    expected_outcome=task.expected_outcome,
                    user_intent=session.user_input,
                    project_context=session.metadata.get("project_context", {})
                )
                
                evaluation = await self.result_evaluator.evaluate_task_result(task, tool_results, evaluation_context)
                session.evaluations[task.id] = evaluation
                
                # Update task status based on evaluation
                if evaluation.outcome == EvaluationOutcome.SUCCESS:
                    task.update_status(TaskStatus.COMPLETED)
                    session.add_log_entry(f"Task {task.id} completed successfully")
                elif evaluation.outcome == EvaluationOutcome.NEEDS_RETRY:
                    execution_attempts += 1
                    if execution_attempts < self.max_execution_retries:
                        session.add_log_entry(f"Retrying task {task.id} (attempt {execution_attempts + 1})")
                        await asyncio.sleep(1)
                        continue
                    else:
                        task.update_status(TaskStatus.FAILED)
                        session.add_log_entry(f"Task {task.id} failed after {self.max_execution_retries} attempts")
                else:
                    task.update_status(TaskStatus.FAILED)
                    session.add_log_entry(f"Task {task.id} failed: {evaluation.reasoning}")
                
                # Yield sub-task completion
                yield {
                    "type": "sub_task_result",
                    "content": f"Task completed: {task.description}",
                    "session_id": session.id,
                    "task_id": task.id,
                    "status": task.status.value,
                    "evaluation": evaluation.to_dict()
                }
                
                break
                
            except Exception as e:
                execution_attempts += 1
                session.add_log_entry(f"Task {task.id} execution attempt {execution_attempts} failed: {str(e)}", "ERROR")
                
                if execution_attempts >= self.max_execution_retries:
                    task.update_status(TaskStatus.FAILED)
                    raise ExecutionError(
                        f"Task execution failed after {self.max_execution_retries} attempts: {str(e)}",
                        tool_name=task.tool_name,
                        tool_input=task.tool_input,
                        context={"task_id": task.id}
                    )
                
                await asyncio.sleep(1)
    
    async def _final_assessment_phase(self, session: ReActSession) -> AsyncGenerator[Dict[str, Any], None]:
        """Perform final assessment of overall execution."""
        # Skip assessment if no tasks were executed (conversational input)
        if not session.tasks:
            session.add_log_entry("Skipping final assessment - no tasks were executed")
            yield self._create_status_update(session, "Conversational interaction completed")
            return
            
        session.update_state(ReActState.EVALUATING)
        yield self._create_status_update(session, "Performing final assessment")
        
        # Evaluate overall progress
        overall_evaluation = await self.result_evaluator.evaluate_overall_progress(
            session.tasks, session.evaluations
        )
        
        session.metadata["overall_evaluation"] = overall_evaluation.to_dict()
        session.add_log_entry(f"Overall assessment: {overall_evaluation.outcome.value} with {overall_evaluation.confidence.value} confidence")
        
        yield {
            "type": "overall_assessment",
            "content": overall_evaluation.reasoning,
            "session_id": session.id,
            "evaluation": overall_evaluation.to_dict()
        }
    
    def _create_status_update(self, session: ReActSession, message: str) -> Dict[str, Any]:
        """Create a status update dictionary."""
        return {
            "type": "status_update",
            "content": message,
            "session_id": session.id,
            "state": session.state.value,
            "timestamp": datetime.now().isoformat()
        }
    
    def _create_final_result(self, session: ReActSession) -> Dict[str, Any]:
        """Create detailed final result summary with task-by-task breakdown."""
        successful_tasks = sum(1 for task in session.tasks if task.status == TaskStatus.COMPLETED)
        failed_tasks = sum(1 for task in session.tasks if task.status == TaskStatus.FAILED)
        total_tasks = len(session.tasks)
        
        # Handle conversational inputs with no tasks
        if total_tasks == 0:
            return {
                "type": "final_result",
                "content": "Conversational interaction completed successfully",
                "session_id": session.id,
                "session_data": session.to_dict(),
                "summary": {
                    "total_tasks": 0,
                    "successful_tasks": 0,
                    "failed_tasks": 0,
                    "execution_time": (session.updated_at - session.created_at).total_seconds(),
                    "interaction_type": "conversational"
                }
            }
        
        # Generate detailed task breakdown
        task_results = []
        content_lines = ["🔍 执行摘要：", ""]
        
        for i, task in enumerate(session.tasks, 1):
            # Get task status and evaluation
            evaluation = session.evaluations.get(task.id)
            status_emoji = "✅" if task.status == TaskStatus.COMPLETED else "❌"
            status_text = "成功" if task.status == TaskStatus.COMPLETED else "失败"
            
            # Get tools used
            tools_used = [task.tool_name] if task.tool_name else []
            tools_text = f"使用工具: {tools_used}" if tools_used else "无工具使用"
            
            # Add task summary
            task_line = f"{status_emoji} 任务 {i}: {task.description} - {status_text}"
            content_lines.append(task_line)
            content_lines.append(f"   {tools_text}")
            
            # Add evaluation details if available
            if evaluation:
                if evaluation.reasoning:
                    # Truncate long reasoning for readability
                    reasoning = evaluation.reasoning[:100] + "..." if len(evaluation.reasoning) > 100 else evaluation.reasoning
                    content_lines.append(f"   评估: {reasoning}")
                
                if evaluation.recommendations:
                    # Show first recommendation if any
                    first_rec = evaluation.recommendations[0] if evaluation.recommendations else ""
                    if first_rec:
                        rec_text = first_rec[:80] + "..." if len(first_rec) > 80 else first_rec
                        content_lines.append(f"   建议: {rec_text}")
            
            content_lines.append("")  # Empty line for spacing
            
            # Store structured task result
            task_results.append({
                "task_index": i,
                "task_id": task.id,
                "description": task.description,
                "status": task.status.value,
                "success": task.status == TaskStatus.COMPLETED,
                "tools_used": tools_used,
                "evaluation": evaluation.to_dict() if evaluation else None
            })
        
        # Overall result
        overall_success = failed_tasks == 0 and successful_tasks > 0
        if overall_success:
            overall_emoji = "🎉"
            overall_text = f"所有任务执行成功！共完成 {successful_tasks} 个任务"
        elif successful_tasks > 0:
            overall_emoji = "⚠️"
            overall_text = f"部分任务完成：{successful_tasks} 个成功，{failed_tasks} 个失败"
        else:
            overall_emoji = "❌"
            overall_text = f"所有任务都失败了：共 {failed_tasks} 个任务失败"
        
        content_lines.extend([
            "📊 最终结果：",
            f"{overall_emoji} {overall_text}",
            f"⏱️ 总耗时: {(session.updated_at - session.created_at).total_seconds():.1f} 秒"
        ])
        
        return {
            "type": "final_result",
            "content": "\n".join(content_lines),
            "session_id": session.id,
            "session_data": session.to_dict(),
            "summary": {
                "total_tasks": total_tasks,
                "successful_tasks": successful_tasks,
                "failed_tasks": failed_tasks,
                "execution_time": (session.updated_at - session.created_at).total_seconds(),
                "overall_success": overall_success,
                "task_results": task_results
            }
        }
    
    async def _generate_conversational_response(self, session: ReActSession) -> str:
        """Generate a conversational response when no tasks are identified."""
        try:
            # Create a simple conversational message using the AI client
            conversation = [
                Message(
                    role="system",
                    content="You are a helpful assistant. The user has sent a message that doesn't require any specific task execution. Provide a friendly, helpful response."
                ),
                Message(
                    role="user", 
                    content=session.user_input
                )
            ]
            
            response = await self.ai_client.chat(conversation)
            return response.content
            
        except Exception as e:
            logger.warning(f"Failed to generate conversational response: {str(e)}")
            # Fallback response
            return f"I understand you said: '{session.user_input}'. How can I help you with your development tasks?"