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
    
    
    async def process_user_input(self, user_input: str, context: Optional[Dict[str, Any]] = None, session: Optional[ReActSession] = None) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Process user input through the complete ReAct cycle.
        
        Args:
            user_input: User's natural language input
            context: Additional context information
            session: Existing session to continue, or None to create new one
            
        Yields:
            Dict[str, Any]: Status updates and results from each phase
        """
        # Use existing session or create new one
        if session is None:
            session = ReActSession(user_input=user_input)
            # Add initial user input to conversation history for new sessions
            from ..ai.conversation import Message
            session.conversation_history.append(Message(role="user", content=user_input))
        else:
            # Update existing session with new input
            session.user_input = user_input
            session.updated_at = datetime.now()
            
            # Add new user input to conversation history for context continuity
            from ..ai.conversation import Message
            session.conversation_history.append(Message(role="user", content=user_input))
        
        if context:
            session.metadata.update(context)
        
        try:
            session.add_log_entry(f"Starting ReAct processing for input: {user_input[:100]}...")
            yield {
                "type": "task_init",
                "content": f"任务已接受并开始启动：{user_input}",
                "session_id": session.id,
                "state": session.state.value,
                "timestamp": datetime.now().isoformat()
            }
            #yield self._create_status_update(session, "ReAct processing started")
            
            
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
            final_result = self._create_final_result(session)
            
            # Add AI response to conversation history for context continuity
            if session.conversation_history and len(session.conversation_history) > 0:
                from ..ai.conversation import Message
                ai_response_content = final_result.get("content", "Task completed")
                session.conversation_history.append(Message(role="assistant", content=ai_response_content))
            
            yield final_result
            
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
                
                # Store planning context in session metadata for later use
                session.metadata["planning_context"] = {
                    "constraints": planning_context.constraints
                }
                
                session.add_log_entry(f"Successfully planned {len(tasks)} tasks")
                
                # Create detailed task summary or conversational indication
                if tasks:
                    task_descriptions = [f"任务{i+1}: {task.description}" for i, task in enumerate(tasks)]
                    task_summary = "\n".join(task_descriptions)
                    yield self._create_status_update(session, f"任务规划完成，共{len(tasks)}个任务:\n{task_summary}")
                else:
                    # Check if it's a conversational response
                    if planning_context.constraints.get("conversational_response"):
                        yield self._create_status_update(session, "识别为对话性输入，将直接回复")
                    else:
                        yield self._create_status_update(session, "未识别出具体任务，将提供对话式回复")
                
                # Yield task plan details
                if tasks:
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
                            "type": "sub_task_init",
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
                else:
                    # For conversational inputs, yield a conversational plan indicator
                    yield {
                        "type": "conversational_plan",
                        "content": "Conversational input detected",
                        "session_id": session.id,
                        "tasks": []
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
            
            # Check if planner provided a conversational response
            conversational_response = session.metadata.get("planning_context", {}).get("constraints", {}).get("conversational_response")
            
            if conversational_response:
                # Use the conversational response from the planner
                response = conversational_response
                session.add_log_entry("Using conversational response from planner")
            else:
                # Fallback: Create a conversational response using the AI client
                response = await self._generate_conversational_response(session)
                session.add_log_entry("Generated fallback conversational response")
            
            # Add conversational response to conversation history
            if session.conversation_history:
                from ..ai.conversation import Message
                session.conversation_history.append(Message(role="assistant", content=response))
            
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
                
                # Show detailed error information for failed tasks
                if task.status == TaskStatus.FAILED and evaluation.evidence:
                    for evidence in evaluation.evidence[:2]:  # Show up to 2 error messages
                        error_text = evidence[:120] + "..." if len(evidence) > 120 else evidence
                        content_lines.append(f"   错误: {error_text}")
                
                if evaluation.recommendations:
                    # Show first recommendation if any
                    first_rec = evaluation.recommendations[0] if evaluation.recommendations else ""
                    if first_rec:
                        rec_text = first_rec[:80] + "..." if len(first_rec) > 80 else first_rec
                        content_lines.append(f"   建议: {rec_text}")
            
            # Fallback: Extract error info directly from task results if no evaluation available
            elif task.status == TaskStatus.FAILED and task.id in session.task_results:
                error_results = [r for r in session.task_results[task.id] if r.type == ToolResultType.ERROR]
                for error_result in error_results[:2]:  # Show up to 2 error messages
                    error_text = error_result.content[:120] + "..." if len(error_result.content) > 120 else error_result.content
                    content_lines.append(f"   错误: {error_text}")
            
            content_lines.append("")  # Empty line for spacing
            
            # Store structured task result
            error_details = []
            if task.status == TaskStatus.FAILED:
                if evaluation and evaluation.evidence:
                    error_details.extend(evaluation.evidence[:2])
                elif task.id in session.task_results:
                    error_results = [r for r in session.task_results[task.id] if r.type == ToolResultType.ERROR]
                    error_details.extend([r.content for r in error_results[:2]])
            
            task_results.append({
                "task_index": i,
                "task_id": task.id,
                "description": task.description,
                "status": task.status.value,
                "success": task.status == TaskStatus.COMPLETED,
                "tools_used": tools_used,
                "evaluation": evaluation.to_dict() if evaluation else None,
                "error_details": error_details
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