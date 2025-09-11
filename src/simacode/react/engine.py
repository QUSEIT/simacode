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
from .exceptions import ReActError, ExecutionError, MaxRetriesExceededError, ReplanningRequiresConfirmationError

logger = logging.getLogger(__name__)


class ReActState(Enum):
    """ReAct engine execution state."""
    IDLE = "idle"
    REASONING = "reasoning"
    PLANNING = "planning"
    AWAITING_CONFIRMATION = "awaiting_confirmation"  # 🆕 新增状态
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
    
    def __init__(self, ai_client: AIClient, execution_mode: ExecutionMode = ExecutionMode.ADAPTIVE, config: Optional[Any] = None, api_mode: bool = False, session_manager=None):
        """
        Initialize the ReAct engine.
        
        Args:
            ai_client: AI client for reasoning and evaluation
            execution_mode: How to execute tasks (sequential, parallel, adaptive)
            config: Configuration object with ReAct settings
            api_mode: Whether running in API mode (uses chat stream confirmation)
            session_manager: Optional SessionManager for tool session access
        """
        self.ai_client = ai_client
        self.execution_mode = execution_mode
        self.task_planner = TaskPlanner(ai_client)
        self.result_evaluator = ResultEvaluator(ai_client)
        self.tool_registry = ToolRegistry()
        self.config = config
        self.api_mode = api_mode  # 🆕 明确的模式标识
        self.session_manager = session_manager
        
        # Initialize tools with session manager if provided
        if session_manager:
            from ..tools import initialize_tools_with_session_manager
            initialize_tools_with_session_manager(session_manager)
        
        # Engine configuration
        self.max_planning_retries = 3
        self.max_execution_retries = 3
        self.parallel_task_limit = 5
        
        # Confirmation manager (lazy initialization)
        self._confirmation_manager = None
        
        logger.info(f"ReAct engine initialized with {execution_mode.value} execution mode")
    
    @property
    def confirmation_manager(self):
        """Lazy initialization of confirmation manager"""
        if self._confirmation_manager is None:
            if self.api_mode:
                # API模式下使用API层的确认管理器
                from ..api.chat_confirmation import chat_confirmation_manager
                self._confirmation_manager = chat_confirmation_manager
            else:
                # CLI模式下使用内部确认管理器
                from .confirmation_manager import ConfirmationManager
                self._confirmation_manager = ConfirmationManager()
        return self._confirmation_manager
    
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
            session.metadata.update({"context":context})
        
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
            logger.debug(f"[CONFIRM_DEBUG] Starting execution phase for session {session.id}, state: {session.state}")
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
            # 检查是否是用户取消的异常，如果是则不设置为FAILED状态
            if isinstance(e, ReActError) and ("User cancelled" in str(e) or "cancelled" in str(e).lower()):
                session.add_log_entry(f"ReAct processing cancelled by user: {str(e)}", "INFO")
                
                yield {
                    "type": "user_cancelled",
                    "content": f"任务已被用户取消: {str(e)}",
                    "session_id": session.id,
                    "error_type": type(e).__name__,
                    "session_state": session.state.value,
                    "retry_count": session.retry_count
                }
                
                logger.info(f"ReAct processing cancelled by user: {str(e)}")
            else:
                session.update_state(ReActState.FAILED)
                session.add_log_entry(f"ReAct processing failed: {str(e)}", "ERROR")
                
                # 检查是否是超时相关的错误，如果是则提供重置信息
                error_content = f"ReAct processing failed: {str(e)}"
                if "Failed to create task plan after" in str(e) or "Failed to plan tasks" in str(e):
                    error_content += " 会话已重置，您可以重新发送请求。"
                
                yield {
                    "type": "error",
                    "content": error_content,
                    "session_id": session.id,
                    "error_type": type(e).__name__,
                    "session_state": session.state.value,
                    "retry_count": session.retry_count
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
                
                # 🆕 检查是否需要人工确认
                if tasks and self._should_request_confirmation(session, tasks):
                    async for confirmation_update in self._handle_human_confirmation(session, tasks):
                        yield confirmation_update
                
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
                # 检查是否是用户取消的异常，如果是则直接传播，不进行重试
                if isinstance(e, ReActError) and ("User cancelled" in str(e) or "cancelled" in str(e).lower()):
                    session.add_log_entry(f"User cancelled task execution: {str(e)}", "INFO")
                    # 用户取消时重置会话状态，但不抛出新的异常
                    session.retry_count = 0  # 重置重试计数
                    session.tasks = []  # 清空任务列表
                    session.current_task_index = 0  # 重置任务索引
                    session.update_state(ReActState.IDLE)  # 重置状态
                    
                    yield {
                        "type": "user_cancelled_reset",
                        "content": "任务已被用户取消，会话状态已重置。您可以重新发送请求。",
                        "session_id": session.id,
                        "retry_count": session.retry_count,
                        "state": session.state.value
                    }
                    
                    # 直接重新抛出原始的用户取消异常，不包装
                    raise e
                
                planning_attempts += 1
                session.add_log_entry(f"Planning attempt {planning_attempts} failed: {str(e)}", "WARNING")
                
                if planning_attempts >= self.max_planning_retries:
                    # 在规划超时3次后，取消任务并重置会话状态
                    session.retry_count = 0  # 重置重试计数
                    session.tasks = []  # 清空任务列表
                    session.current_task_index = 0  # 重置任务索引
                    session.update_state(ReActState.IDLE)  # 重置状态
                    session.add_log_entry(f"Planning failed after {self.max_planning_retries} attempts. Tasks cancelled and session reset.", "ERROR")
                    
                    yield {
                        "type": "planning_timeout_reset",
                        "content": f"任务规划连续失败{self.max_planning_retries}次，可能是由于AI返回的JSON格式不正确。已自动重置会话状态，请重新发送您的请求。\n\n错误详情: {str(e)}",
                        "session_id": session.id,
                        "retry_count": session.retry_count,
                        "state": session.state.value
                    }
                    
                    # 不抛出异常，而是正常结束规划阶段
                    return
                
                # Wait before retry
                await asyncio.sleep(1)
    
    async def _execution_and_evaluation_phase(self, session: ReActSession) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute tasks and evaluate results."""
        logger.debug(f"[CONFIRM_DEBUG] Execution phase started for session {session.id}")
        logger.debug(f"[CONFIRM_DEBUG] Session state: {session.state}, tasks count: {len(session.tasks) if session.tasks else 0}")
        
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
            
            # Execute single task and collect all updates
            task_updates = []
            async for update in self._execute_single_task(session, task):
                task_updates.append(update)
                yield update
            
            # 🔧 方案1: 增强任务完成验证 - 确保任务完全完成包括结果存储
            await self._ensure_task_fully_completed(session, task)
            
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
        
        # Check if any task contains placeholders that suggest dependency on previous results
        has_placeholders = any(
            self._task_contains_placeholders(task) for task in session.tasks
        )
        
        if not has_dependencies and not has_placeholders and len(session.tasks) > 1:
            # Use parallel execution for truly independent tasks
            session.add_log_entry("Using parallel execution for independent tasks", "INFO")
            async for update in self._execute_tasks_in_parallel(session):
                yield update
        else:
            # Use sequential execution for dependent tasks or tasks with placeholders
            reason = "task dependencies" if has_dependencies else "placeholder dependencies"
            session.add_log_entry(f"Using sequential execution due to {reason}", "INFO")
            async for update in self._execute_tasks_sequentially(session):
                yield update
    
    def _task_contains_placeholders(self, task) -> bool:
        """Check if a task contains placeholders that suggest dependency on previous results."""
        import re
        
        def check_value(value):
            if isinstance(value, str):
                # Look for common placeholder patterns
                patterns = [
                    r'<[^>]*(?:result|content|data|output|text|extracted)[^>]*>',
                    r'<[^>]*_from_[^>]*>',
                    r'<[^>]*previous[^>]*>',
                ]
                return any(re.search(pattern, value, re.IGNORECASE) for pattern in patterns)
            elif isinstance(value, dict):
                return any(check_value(v) for v in value.values())
            elif isinstance(value, list):
                return any(check_value(item) for item in value)
            return False
        
        # Check task input for placeholders
        return check_value(task.tool_input)
    
    def _substitute_task_placeholders(self, session: ReActSession, task: Task) -> Task:
        """Replace placeholders in task input with results from previous tasks."""
        import re
        import json
        
        # Early exit: if task has no dependencies and no placeholders, skip substitution
        if not task.dependencies and not self._task_contains_placeholders(task):
            session.add_log_entry(f"DEBUG: Task {task.id} has no dependencies and no placeholders, skipping substitution", "DEBUG")
            return task
        
        # 🔍 DEBUG: 添加详细日志分析占位符替换过程
        session.add_log_entry(f"DEBUG: Starting placeholder substitution for task {task.id}", "DEBUG")
        session.add_log_entry(f"DEBUG: Task tool_input before substitution: {task.tool_input}", "DEBUG")
        session.add_log_entry(f"DEBUG: Available task_results keys: {list(session.task_results.keys())}", "DEBUG")
        
        # Create a copy of the task to avoid modifying the original
        updated_task = Task(
            id=task.id,
            type=task.type,
            description=task.description,
            tool_name=task.tool_name,
            tool_input=task.tool_input.copy(),
            expected_outcome=task.expected_outcome,
            dependencies=task.dependencies.copy(),
            status=task.status,
            priority=task.priority,
            created_at=task.created_at,
            updated_at=task.updated_at,
            metadata=task.metadata.copy()
        )
        
        # Look for results from previous tasks that can be substituted
        task_results_text = ""
        
        # 🔍 DEBUG: 详细分析结果收集过程
        session.add_log_entry(f"DEBUG: Task dependencies: {task.dependencies}", "DEBUG")
        
        # If task has dependencies, try to get results from those specific tasks
        if task.dependencies:
            dependency_results = []
            
            # Dependencies might be task descriptions or task IDs
            # Enhanced matching: try multiple strategies to find the right task
            for dep_description in task.dependencies:
                matching_task_id = None
                
                session.add_log_entry(f"DEBUG: Looking for dependency: '{str(dep_description)}'", "DEBUG")
                
                # Strategy 1: Direct task ID match (if dependency is already a task ID)
                if str(dep_description) in session.task_results:
                    matching_task_id = str(dep_description)
                    session.add_log_entry(f"DEBUG: Direct task ID match: {matching_task_id}", "DEBUG")
                else:
                    # Strategy 2: Find task by description matching
                    dep_str = str(dep_description) if dep_description is not None else ""
                    
                    # Look through all tasks with results
                    for task_id, results in session.task_results.items():
                        # Find the corresponding task object
                        matching_session_task = None
                        for session_task in session.tasks:
                            if session_task.id == task_id:
                                matching_session_task = session_task
                                break
                        
                        if matching_session_task:
                            task_desc = str(matching_session_task.description) if matching_session_task.description else ""
                            session.add_log_entry(f"DEBUG: Comparing '{dep_str}' with task '{task_desc}'", "DEBUG")
                            
                            # Enhanced matching logic
                            if (task_desc == dep_str or  # Exact match
                                (dep_str and dep_str in task_desc) or  # Substring match
                                (dep_str and task_desc.startswith(dep_str)) or  # Prefix match
                                (task_desc and dep_str in task_desc.lower()) or  # Case-insensitive substring
                                # Handle common OCR description patterns
                                (dep_str and "识别" in dep_str and "识别" in task_desc) or
                                (dep_str and "ocr" in dep_str.lower() and matching_session_task.tool_name == "universal_ocr")):
                                matching_task_id = task_id
                                session.add_log_entry(f"DEBUG: Found matching task ID: {matching_task_id}", "DEBUG")
                                break
                    
                    # Strategy 3: Fallback - if only one OCR task exists and dependency mentions OCR/识别
                    if not matching_task_id and ("识别" in dep_str or "ocr" in dep_str.lower()):
                        ocr_tasks = [(tid, task) for tid, task in [(tid, next((t for t in session.tasks if t.id == tid), None)) 
                                                                   for tid in session.task_results.keys()]
                                    if task and task.tool_name == "universal_ocr"]
                        if len(ocr_tasks) == 1:
                            matching_task_id = ocr_tasks[0][0]
                            session.add_log_entry(f"DEBUG: Fallback OCR task match: {matching_task_id}", "DEBUG")
                
                if matching_task_id and matching_task_id in session.task_results:
                    results = session.task_results[matching_task_id]
                    
                    # Prioritize OUTPUT results as they contain the main content
                    output_results = []
                    other_results = []
                    
                    for result in results:
                        if result.content:
                            if result.type.value == 'output':
                                output_results.append(result.content)
                            elif result.type.value in ['success', 'info']:
                                other_results.append(result.content)
                    
                    # Use OUTPUT results if available, otherwise fall back to other results
                    if output_results:
                        dependency_results.extend(output_results)
                    else:
                        dependency_results.extend(other_results)
            
            task_results_text = "\n".join(dependency_results)
        else:
            # If no explicit dependencies, use results from all previous successful tasks
            # Prioritize OUTPUT results as they contain the main content
            output_results = []
            other_results = []
            
            for task_id, results in session.task_results.items():
                for result in results:
                    if result.content:
                        if result.type.value == 'output':
                            output_results.append(result.content)
                        elif result.type.value in ['success', 'info']:
                            other_results.append(result.content)
            
            # Use OUTPUT results if available, otherwise fall back to other results
            if output_results:
                task_results_text = "\n".join(output_results)
                session.add_log_entry(f"DEBUG: Using OUTPUT results (count: {len(output_results)})", "DEBUG")
            else:
                task_results_text = "\n".join(other_results)
                session.add_log_entry(f"DEBUG: Using OTHER results (count: {len(other_results)})", "DEBUG")
        
        # 🔍 DEBUG: 显示收集到的结果文本
        session.add_log_entry(f"DEBUG: Collected task_results_text length: {len(task_results_text)}", "DEBUG")
        if task_results_text:
            session.add_log_entry(f"DEBUG: First 200 chars of task_results_text: {task_results_text[:200]}...", "DEBUG")
        
        # Function to substitute placeholders in a value (string, dict, or list)
        def substitute_value(value):
            if isinstance(value, str):
                replacement_text = task_results_text.strip()
                
                # Only proceed with substitution if we have actual content to substitute
                if replacement_text:
                    session.add_log_entry(f"DEBUG: Replacement text available for substitution", "DEBUG")
                    
                    # Try to extract raw text from JSON if it's OCR output
                    original_replacement = replacement_text
                    try:
                        import json
                        parsed_json = json.loads(replacement_text)
                        if isinstance(parsed_json, dict) and 'raw_text' in parsed_json:
                            # Use raw_text from OCR JSON output
                            replacement_text = parsed_json['raw_text'] or ''
                            session.add_log_entry(f"DEBUG: Extracted raw_text from JSON: {len(replacement_text)} chars", "DEBUG")
                        elif isinstance(parsed_json, dict) and 'extracted_data' in parsed_json:
                            # Fallback: try to get text from extracted_data
                            extracted_data = parsed_json['extracted_data']
                            if isinstance(extracted_data, dict) and 'raw_text' in extracted_data:
                                replacement_text = extracted_data['raw_text'] or ''
                                session.add_log_entry(f"DEBUG: Extracted raw_text from extracted_data: {len(replacement_text)} chars", "DEBUG")
                    except (json.JSONDecodeError, KeyError, TypeError):
                        # If it's not JSON or doesn't have expected structure, use as is
                        session.add_log_entry(f"DEBUG: Using replacement text as-is (not JSON)", "DEBUG")
                        pass
                    
                    # 🔍 DEBUG: 记录替换前后状态
                    original_value = value
                    session.add_log_entry(f"DEBUG: Before substitution - value: {value}", "DEBUG")
                    session.add_log_entry(f"DEBUG: Replacement text to use: {replacement_text[:100]}...", "DEBUG")
                    
                    # Replace specific, known placeholder patterns only
                    original_value = value
                    
                    # First check if there are any placeholders to replace
                    placeholder_patterns = [
                        r'<extracted_text_here>',
                        r'<previous_result>', 
                        r'<task_result>',
                        r'<content_from_previous_task>',
                        r'<retrieved_content>',
                        r'<retrieved_content_here>',
                        r'<file_content>',  # file content placeholder
                        r'<content_from_[^>]+>',  # file-specific content
                        r'<[^>]*_from_previous_task>',
                        r'<[^>]*previous_task[^>]*>'
                    ]
                    
                    # Only perform substitution if value contains actual placeholders
                    has_placeholder = any(re.search(pattern, value, re.IGNORECASE) for pattern in placeholder_patterns)
                    
                    if has_placeholder:
                        # Replace specific placeholder patterns
                        value = re.sub(r'<extracted_text_here>', replacement_text, value, flags=re.IGNORECASE)
                        value = re.sub(r'<previous_result>', replacement_text, value, flags=re.IGNORECASE)
                        value = re.sub(r'<task_result>', replacement_text, value, flags=re.IGNORECASE)
                        value = re.sub(r'<content_from_previous_task>', replacement_text, value, flags=re.IGNORECASE)
                        value = re.sub(r'<retrieved_content>', replacement_text, value, flags=re.IGNORECASE)
                        value = re.sub(r'<retrieved_content_here>', replacement_text, value, flags=re.IGNORECASE)
                        value = re.sub(r'<file_content>', replacement_text, value, flags=re.IGNORECASE)
                        # Handle file-specific content placeholders like <content_from_test.txt>
                        value = re.sub(r'<content_from_[^>]+>', replacement_text, value, flags=re.IGNORECASE)
                        # Handle various forms of previous task references
                        value = re.sub(r'<[^>]*_from_previous_task>', replacement_text, value, flags=re.IGNORECASE)
                        value = re.sub(r'<[^>]*previous_task[^>]*>', replacement_text, value, flags=re.IGNORECASE)
                        
                        session.add_log_entry(f"DEBUG: Placeholder replacement performed", "DEBUG")
                    else:
                        session.add_log_entry(f"DEBUG: No placeholder patterns found, skipping replacement", "DEBUG")
                    
                    # 🔍 DEBUG: 记录替换结果
                    if original_value != value:
                        session.add_log_entry(f"DEBUG: Substitution SUCCESS - value changed", "DEBUG")
                    else:
                        session.add_log_entry(f"DEBUG: Substitution FAILED - value unchanged", "DEBUG")
                    
                    session.add_log_entry(f"DEBUG: After substitution - value: {value[:200]}...", "DEBUG")
                else:
                    session.add_log_entry(f"DEBUG: No replacement text available for substitution", "DEBUG")
                    
                return value
            elif isinstance(value, dict):
                return {k: substitute_value(v) for k, v in value.items()}
            elif isinstance(value, list):
                return [substitute_value(item) for item in value]
            else:
                return value
        
        # Apply substitutions to tool_input
        session.add_log_entry(f"DEBUG: Applying substitutions to tool_input", "DEBUG")
        updated_task.tool_input = substitute_value(updated_task.tool_input)
        session.add_log_entry(f"DEBUG: Final tool_input after substitution: {updated_task.tool_input}", "DEBUG")
        
        return updated_task

    async def _ensure_task_fully_completed(self, session: ReActSession, task: Task) -> None:
        """
        方案1: 增强任务完成验证
        确保任务完全完成，包括结果存储和评估，特别是OUTPUT类型结果
        """
        max_wait = 5.0  # 最大等待5秒
        wait_interval = 0.1  # 100ms检查间隔
        elapsed = 0.0
        
        session.add_log_entry(f"Verifying task {task.id} completion", "DEBUG")
        
        while elapsed < max_wait:
            # 检查三个关键完成条件
            has_results = task.id in session.task_results
            has_evaluation = task.id in session.evaluations
            has_output_result = False
            
            if has_results:
                results = session.task_results[task.id]
                # 检查是否有OUTPUT类型的结果且内容不为空
                has_output_result = any(
                    r.type.value == 'output' and r.content and r.content.strip()
                    for r in results
                )
            
            if has_results and has_evaluation and has_output_result:
                session.add_log_entry(f"Task {task.id} fully completed with all required data", "DEBUG")
                return
                
            await asyncio.sleep(wait_interval)
            elapsed += wait_interval
        
        # 超时警告但不阻塞执行
        session.add_log_entry(f"Warning: Task {task.id} completion verification timeout after {max_wait}s", "WARNING")
        if task.id not in session.task_results:
            session.add_log_entry(f"Critical: Task {task.id} has no stored results", "ERROR")

    async def _substitute_task_placeholders_with_wait(self, session: ReActSession, task: Task) -> Task:
        """
        方案2: 延迟占位符替换
        如果任务包含占位符，等待依赖的任务完成后再进行替换
        """
        # 先尝试正常替换
        processed_task = self._substitute_task_placeholders(session, task)
        
        # 检查是否仍有未替换的占位符
        if self._still_has_placeholders(processed_task):
            session.add_log_entry(f"Task {task.id} still has placeholders, waiting for dependencies", "DEBUG")
            
            # 等待前序任务的OUTPUT结果可用
            await self._wait_for_output_results(session, task)
            
            # 重新替换占位符
            processed_task = self._substitute_task_placeholders(session, task)
            
            # 最终检查
            if self._still_has_placeholders(processed_task):
                session.add_log_entry(f"Warning: Task {task.id} still has unresolved placeholders after waiting", "WARNING")
        
        return processed_task
    
    def _still_has_placeholders(self, task: Task) -> bool:
        """检查任务是否仍包含未替换的占位符"""
        import re
        
        def check_value(value):
            if isinstance(value, str):
                # 检查常见的占位符模式
                patterns = [
                    r'<extracted_text_here>',
                    r'<previous_result>',
                    r'<task_result>',
                    r'<content_from_previous_task>',
                    r'<[^>]*(?:result|content|data|output|text|extracted)[^>]*>',
                ]
                return any(re.search(pattern, value, re.IGNORECASE) for pattern in patterns)
            elif isinstance(value, dict):
                return any(check_value(v) for v in value.values())
            elif isinstance(value, list):
                return any(check_value(item) for item in value)
            return False
        
        return check_value(task.tool_input)
    
    async def _wait_for_output_results(self, session: ReActSession, task: Task) -> None:
        """等待前序任务产生OUTPUT类型的结果"""
        max_wait = 3.0  # 最大等待3秒
        wait_interval = 0.05  # 50ms检查间隔
        elapsed = 0.0
        
        while elapsed < max_wait:
            # 检查是否有任何任务产生了OUTPUT结果
            has_output = False
            for task_id, results in session.task_results.items():
                if any(r.type.value == 'output' and r.content and r.content.strip() for r in results):
                    has_output = True
                    break
            
            if has_output:
                session.add_log_entry(f"OUTPUT results available for task {task.id} placeholder substitution", "DEBUG")
                return
                
            await asyncio.sleep(wait_interval)
            elapsed += wait_interval
        
        session.add_log_entry(f"Timeout waiting for OUTPUT results for task {task.id}", "WARNING")

    async def _execute_single_task(self, session: ReActSession, task: Task) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute a single task with error handling and evaluation."""
        
        # 🔍 DEBUG: 记录任务执行前的状态
        if task.tool_name == "email_smtp:send_email":
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"=== EXECUTE DEBUG: Before processing task {task.id} ===")
            logger.warning(f"Task description: {task.description}")
            logger.warning(f"Tool name: {task.tool_name}")
            logger.warning(f"Dependencies: {task.dependencies}")
            logger.warning(f"Original tool_input: {task.tool_input}")
            if 'body' in task.tool_input:
                logger.warning(f"*** ORIGINAL EMAIL BODY: '{task.tool_input['body']}' ***")
            logger.warning("=== END EXECUTE DEBUG ===")
        
        # 🔧 方案2: 延迟占位符替换 - 等待依赖任务完成后再替换
        processed_task = await self._substitute_task_placeholders_with_wait(session, task)
        
        # 🔍 DEBUG: 记录占位符替换后的状态
        if processed_task.tool_name == "email_smtp:send_email":
            logger.warning(f"=== EXECUTE DEBUG: After placeholder substitution ===")
            logger.warning(f"Processed tool_input: {processed_task.tool_input}")
            if 'body' in processed_task.tool_input:
                logger.warning(f"*** PROCESSED EMAIL BODY: '{processed_task.tool_input['body']}' ***")
            logger.warning("=== END SUBSTITUTION DEBUG ===")
        
        processed_task.update_status(TaskStatus.EXECUTING)
        session.add_log_entry(f"Starting execution of task {processed_task.id}: {processed_task.description}")
        
        execution_attempts = 0
        while execution_attempts < self.max_execution_retries:
            try:
                # Execute tool
                tool_results = []
                async for result in execute_tool(
                    processed_task.tool_name, 
                    processed_task.tool_input,
                    session_id=session.id,
                    session_context={
                        "session_state": session.state.value,
                        "current_task": processed_task.id,
                        "user_input": session.user_input,
                        "metadata_context": session.metadata.get("context", {})
                    }
                ):
                    tool_results.append(result)
                    
                    # Yield progress updates
                    yield {
                        "type": "tool_progress",
                        "content": result.content,
                        "session_id": session.id,
                        "task_id": processed_task.id,
                        "result_type": result.type.value
                    }
                
                # Store results
                session.task_results[processed_task.id] = tool_results
                
                # Evaluate results
                session.update_state(ReActState.EVALUATING)
                evaluation_context = EvaluationContext(
                    task=processed_task.to_dict(),
                    tool_results=[result.to_dict() for result in tool_results],
                    expected_outcome=processed_task.expected_outcome,
                    user_intent=session.user_input,
                    project_context=session.metadata.get("project_context", {})
                )
                
                evaluation = await self.result_evaluator.evaluate_task_result(processed_task, tool_results, evaluation_context)
                session.evaluations[processed_task.id] = evaluation
                
                # Update task status based on evaluation - also update the original task in session
                if evaluation.outcome == EvaluationOutcome.SUCCESS:
                    processed_task.update_status(TaskStatus.COMPLETED)
                    # Find and update the original task in session.tasks
                    for session_task in session.tasks:
                        if session_task.id == processed_task.id:
                            session_task.update_status(TaskStatus.COMPLETED)
                            break
                    session.add_log_entry(f"Task {processed_task.id} completed successfully")
                elif evaluation.outcome == EvaluationOutcome.NEEDS_RETRY:
                    execution_attempts += 1
                    if execution_attempts < self.max_execution_retries:
                        session.add_log_entry(f"Retrying task {processed_task.id} (attempt {execution_attempts + 1})")
                        await asyncio.sleep(1)
                        continue
                    else:
                        processed_task.update_status(TaskStatus.FAILED)
                        # Find and update the original task in session.tasks
                        for session_task in session.tasks:
                            if session_task.id == processed_task.id:
                                session_task.update_status(TaskStatus.FAILED)
                                break
                        session.add_log_entry(f"Task {processed_task.id} failed after {self.max_execution_retries} attempts")
                else:
                    processed_task.update_status(TaskStatus.FAILED)
                    # Find and update the original task in session.tasks
                    for session_task in session.tasks:
                        if session_task.id == processed_task.id:
                            session_task.update_status(TaskStatus.FAILED)
                            break
                    session.add_log_entry(f"Task {processed_task.id} failed: {evaluation.reasoning}")
                
                # Yield sub-task completion
                yield {
                    "type": "sub_task_result",
                    "content": f"Task completed: {processed_task.description}",
                    "session_id": session.id,
                    "task_id": processed_task.id,
                    "status": processed_task.status.value,
                    "evaluation": evaluation.to_dict()
                }
                
                break
                
            except Exception as e:
                execution_attempts += 1
                session.add_log_entry(f"Task {processed_task.id} execution attempt {execution_attempts} failed: {str(e)}", "ERROR")
                
                if execution_attempts >= self.max_execution_retries:
                    processed_task.update_status(TaskStatus.FAILED)
                    # Find and update the original task in session.tasks
                    for session_task in session.tasks:
                        if session_task.id == processed_task.id:
                            session_task.update_status(TaskStatus.FAILED)
                            break
                    
                    # 在任务执行超时后，检查是否需要重置会话
                    session.retry_count += 1
                    session.add_log_entry(f"Task execution failed after {self.max_execution_retries} attempts. Session retry count: {session.retry_count}", "ERROR")
                    
                    # 如果会话整体重试次数达到限制，重置会话
                    if session.retry_count >= session.max_retries:
                        session.retry_count = 0  # 重置重试计数
                        session.update_state(ReActState.IDLE)  # 重置状态
                        session.add_log_entry(f"Session retry limit reached. Session reset.", "ERROR")
                        
                        yield {
                            "type": "execution_timeout_reset",
                            "content": f"任务执行超时{session.max_retries}次，已重置会话状态。您可以重新发送请求。",
                            "session_id": session.id,
                            "retry_count": session.retry_count,
                            "state": session.state.value
                        }
                    
                    raise ExecutionError(
                        f"Task execution failed after {self.max_execution_retries} attempts: {str(e)}",
                        tool_name=processed_task.tool_name,
                        tool_input=processed_task.tool_input,
                        context={"task_id": processed_task.id}
                    )
                
                await asyncio.sleep(1)
    
    async def _final_assessment_phase(self, session: ReActSession) -> AsyncGenerator[Dict[str, Any], None]:
        """Perform final assessment of overall execution."""
        # Skip assessment if no tasks were executed (conversational input)
        if not session.tasks:
            session.add_log_entry("Skipping final assessment - no tasks were executed")
            yield self._create_status_update(session, "Skipping final assessment - no tasks were executed")
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
    
    def _create_status_confirmation(self, session: ReActSession, message: str) -> Dict[str, Any]:
        """Create a status confirmation message (not a confirmation request)"""
        return {
            "type": "status",
            "content": message,
            "session_id": session.id,
            "state": session.state.value,
            "timestamp": datetime.now().isoformat()
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
            from ..utils.task_summary import generate_task_summary_content
            return {
                "type": "final_result",
                "content": generate_task_summary_content(session),
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
        
        # Generate detailed task breakdown for structured data
        task_results = []
        for i, task in enumerate(session.tasks, 1):
            # Get task status and evaluation
            evaluation = session.evaluations.get(task.id)
            
            # Get tools used
            tools_used = [task.tool_name] if task.tool_name else []
            
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
        
        # Overall result for metadata
        overall_success = failed_tasks == 0 and successful_tasks > 0
        
        from ..utils.task_summary import generate_task_summary_content
        return {
            "type": "final_result",
            "content": generate_task_summary_content(session),
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
    
    def _should_request_confirmation(self, session: ReActSession, tasks: List[Task]) -> bool:
        """判断是否需要请求人工确认"""
        
        # 🆕 检查会话状态 - 如果已经在执行状态，不需要再次确认
        if session.state in [ReActState.EXECUTING, ReActState.COMPLETED, ReActState.FAILED]:
            logger.debug(f"Session {session.id} is in state {session.state.value}, skipping confirmation")
            return False
        
        # 🆕 检查是否强制跳过确认 (programmatic usage)
        if session.metadata.get("skip_confirmation", False):
            logger.debug(f"Session {session.id} has skip_confirmation flag set, skipping confirmation")
            return False
        
        # 检查配置
        if not self.config or not hasattr(self.config, 'react'):
            return False
        
        react_config = self.config.react
        if not react_config.confirm_by_human:
            return False
        
        # 检查是否有需要确认的任务
        if not tasks:
            return False
        
        # 检查是否有危险任务（可选的智能判断）
        if react_config.auto_confirm_safe_tasks:
            dangerous_tasks = self._identify_dangerous_tasks(tasks)
            return len(dangerous_tasks) > 0
        
        return True

    async def _handle_human_confirmation(
        self, 
        session: ReActSession, 
        tasks: List[Task]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """处理人工确认流程"""
        
        session.update_state(ReActState.AWAITING_CONFIRMATION)
        
        # 获取配置的超时时间
        timeout = getattr(self.config.react, 'confirmation_timeout', 300) if self.config else 300
        
        try:
            # 🆕 允许多轮确认以支持任务修改
            max_confirmation_rounds = 3  # 防止无限循环
            confirmation_round = 0
            
            while confirmation_round < max_confirmation_rounds:
                confirmation_round += 1
                current_tasks = session.tasks  # 使用当前的任务列表
                
                logger.debug(f"[CONFIRM_DEBUG] Starting confirmation round {confirmation_round}, session: {session.id}")
                logger.debug(f"[CONFIRM_DEBUG] Current session state: {session.state}")
                
                # 🆕 检查是否需要跳过确认（修改计划后的情况）
                if session.metadata.get("skip_next_confirmation", False):
                    session.metadata.pop("skip_next_confirmation", None)  # 清除标志，确保只跳过一次
                    session.add_log_entry(f"Skipping confirmation for replanned tasks (round {confirmation_round})")
                    session.update_state(ReActState.EXECUTING)
                    
                    logger.info(f"Skipping confirmation round {confirmation_round} after task replanning")
                    
                    yield {
                        "type": "confirmation_skipped",
                        "content": f"✅ 任务已根据您的要求重新规划完成，直接开始执行（跳过第{confirmation_round}轮确认）",
                        "session_id": session.id,
                        "task_count": len(current_tasks),
                        "confirmation_round": confirmation_round
                    }
                    
                    # 发送确认完成的状态更新
                    yield {
                        "type": "confirmation_completed",
                        "content": f"确认流程完成，准备执行任务",
                        "session_id": session.id,
                        "session_state": session.state.value
                    }
                    break
                
                try:
                    round_info = f" (第{confirmation_round}轮)" if confirmation_round > 1 else ""
                    tasks_summary = self._create_tasks_summary(current_tasks)
                    
                    if self.api_mode:
                        # API模式：使用异步确认流程
                        logger.debug(f"[CONFIRM_DEBUG] API mode: Starting confirmation request for session {session.id}")
                        logger.debug(f"[CONFIRM_DEBUG] Tasks to confirm: {len(current_tasks)} tasks")
                        
                        # 发起确认请求
                        confirmation_request = await self.confirmation_manager.request_confirmation(
                            session.id, current_tasks, timeout
                        )
                        logger.debug(f"[CONFIRM_DEBUG] Confirmation request created: {type(confirmation_request)}")
                        
                        # 发送确认请求给客户端
                        # 处理不同确认管理器的返回值类型
                        if hasattr(confirmation_request, 'model_dump'):
                            # TaskConfirmationRequest (Pydantic model)
                            confirmation_data = confirmation_request.model_dump()
                        else:
                            # Dict[str, Any] from ChatStreamConfirmationManager
                            confirmation_data = confirmation_request
                        
                        yield {
                            "type": "confirmation_request",
                            "content": f"规划了 {len(current_tasks)} 个任务{round_info}，请确认是否执行",
                            "session_id": session.id,
                            "confirmation_request": confirmation_data,
                            "tasks_summary": tasks_summary,
                            "confirmation_round": confirmation_round
                        }
                        
                        # 等待用户确认
                        yield self._create_status_confirmation(session, f"等待用户确认执行计划{round_info}（超时：{timeout}秒）")
                        
                        logger.debug(f"[CONFIRM_DEBUG] Waiting for confirmation from session {session.id}, timeout: {timeout}s")
                        confirmation_response = await self.confirmation_manager.wait_for_confirmation(
                            session.id
                        )
                        logger.debug(f"[CONFIRM_DEBUG] Received confirmation response: {confirmation_response}")
                        logger.debug(f"[CONFIRM_DEBUG] Response type: {type(confirmation_response)}")
                        if confirmation_response:
                            logger.debug(f"[CONFIRM_DEBUG] Response action: {getattr(confirmation_response, 'action', 'NO_ACTION')}")
                        
                        # 处理用户响应
                        logger.debug(f"[CONFIRM_DEBUG] Processing confirmation response...")
                        await self._process_confirmation_response(session, confirmation_response)
                        logger.debug(f"[CONFIRM_DEBUG] Confirmation response processed, session state: {session.state}")
                        
                        # 发送确认接收的消息给流式输出
                        if confirmation_response and confirmation_response.action == "confirm":
                            yield {
                                "type": "confirmation_received",
                                "content": f"✅ 用户确认执行任务，开始执行...",
                                "session_id": session.id,
                                "confirmed_tasks": len(current_tasks)
                            }
                        
                    else:
                        # CLI模式：直接使用同步确认界面
                        yield self._create_status_update(session, f"请确认执行计划{round_info}")
                        
                        # 直接调用CLI确认界面
                        confirmation_response = self.handle_cli_confirmation(
                            session.id, tasks_summary, confirmation_round
                        )
                        
                        # 在CLI模式下直接处理用户响应，不通过ConfirmationManager
                        await self._process_confirmation_response(session, confirmation_response)
                    
                    # 如果到这里没有异常，说明确认完成，退出循环
                    logger.debug(f"[CONFIRM_DEBUG] Confirmation round {confirmation_round} completed successfully, breaking loop")
                    
                    # 发送确认完成的状态更新
                    yield {
                        "type": "confirmation_completed",
                        "content": f"确认流程完成，准备执行任务",
                        "session_id": session.id,
                        "session_state": session.state.value
                    }
                    break
                    
                except ReplanningRequiresConfirmationError as e:
                    # 🆕 用户请求了修改，需要继续下一轮确认
                    logger.debug(f"[CONFIRM_DEBUG] Replanning required: {e}")
                    yield {
                        "type": "task_replanned",
                        "content": f"任务已根据用户建议重新规划，共{len(session.tasks)}个任务",
                        "session_id": session.id,
                        "new_task_count": len(session.tasks)
                    }
                    continue  # 继续下一轮确认
                except Exception as e:
                    logger.error(f"[CONFIRM_DEBUG] Unexpected error in confirmation round {confirmation_round}: {e}")
                    logger.error(f"[CONFIRM_DEBUG] Exception type: {type(e)}")
                    raise  # 重新抛出异常
                    
            if confirmation_round >= max_confirmation_rounds:
                yield {
                    "type": "confirmation_error",
                    "content": "达到最大确认轮数限制，使用当前任务计划继续执行",
                    "session_id": session.id
                }
                
        except TimeoutError:
            yield {
                "type": "confirmation_timeout",
                "content": "用户确认超时，取消任务执行",
                "session_id": session.id
            }
            session.update_state(ReActState.FAILED)
            from .exceptions import ReActError
            raise ReActError("User confirmation timeout")
        except Exception as e:
            yield {
                "type": "confirmation_error", 
                "content": f"确认过程出现错误：{str(e)}",
                "session_id": session.id
            }
            raise

    async def _process_confirmation_response(
        self, 
        session: ReActSession, 
        response
    ):
        """处理确认响应"""
        
        logger.debug(f"[CONFIRM_DEBUG] _process_confirmation_response called with response: {response}")
        
        if not response:
            logger.error(f"[CONFIRM_DEBUG] No confirmation response received, cannot process")
            session.update_state(ReActState.FAILED)
            from .exceptions import ReActError
            raise ReActError("No confirmation response received")
        
        if response.action == "cancel":
            session.update_state(ReActState.FAILED)
            from .exceptions import ReActError
            raise ReActError("User cancelled task execution")
        
        elif response.action == "modify":
            if response.modified_tasks:
                # 用户直接提供了修改后的任务
                modified_tasks = []
                for task_dict in response.modified_tasks:
                    task = Task.from_dict(task_dict)
                    modified_tasks.append(task)
                session.tasks = modified_tasks
                session.add_log_entry(f"Tasks modified by user: {len(modified_tasks)} tasks")
            elif response.user_message:
                # 🆕 用户提供了修改建议，需要重新规划任务
                session.add_log_entry(f"User requested task modification: {response.user_message}")
                await self._replan_tasks_with_user_feedback(session, response.user_message)
                
                # 🆕 重新规划后，需要再次请求用户确认新计划
                if session.tasks:  # 如果重新规划成功产生了新任务
                    session.add_log_entry("Requesting confirmation for replanned tasks")
                    # 将状态重置为等待确认，以便再次请求确认
                    session.update_state(ReActState.AWAITING_CONFIRMATION)
                    # 🆕 设置跳过下次确认的标志，修改计划后直接执行
                    session.metadata["skip_next_confirmation"] = True
                    raise ReplanningRequiresConfirmationError("Tasks replanned, confirmation required for new plan")
            else:
                session.add_log_entry("User requested modification but no modification details provided")
        
        elif response.action == "confirm":
            logger.debug(f"[CONFIRM_DEBUG] User confirmed tasks for session {session.id}")
            session.add_log_entry("Tasks confirmed by user")
            # 用户确认后，直接进入执行状态，而不是重新规划
            session.update_state(ReActState.EXECUTING)
            logger.debug(f"[CONFIRM_DEBUG] Session state updated to EXECUTING: {session.state}")
            return  # 直接返回，不需要设置其他状态

    def _create_tasks_summary(self, tasks: List[Task]) -> Dict[str, Any]:
        """创建任务摘要用于确认界面"""
        
        return {
            "total_tasks": len(tasks),
            "tasks": [
                {
                    "index": i + 1,
                    "description": task.description,
                    "tool": task.tool_name,
                    "type": task.type.value,
                    "priority": task.priority,
                    "expected_outcome": task.expected_outcome
                }
                for i, task in enumerate(tasks)
            ],
            "estimated_duration": "未知",  # 可以后续添加估算逻辑
            "risk_level": self._assess_task_risk_level(tasks)
        }

    def _assess_task_risk_level(self, tasks: List[Task]) -> str:
        """评估任务风险等级"""
        
        # 简单的风险评估逻辑
        dangerous_tools = {"file_write", "bash", "system_command"}
        
        for task in tasks:
            if task.tool_name in dangerous_tools:
                return "high"
        
        return "low"
    
    def _identify_dangerous_tasks(self, tasks: List[Task]) -> List[Task]:
        """识别危险任务"""
        dangerous_tools = {"file_write", "bash", "system_command", "delete", "execute"}
        dangerous_tasks = []
        
        for task in tasks:
            if task.tool_name in dangerous_tools:
                dangerous_tasks.append(task)
        
        return dangerous_tasks
    
    async def submit_confirmation(self, response) -> bool:
        """提交用户确认响应的便捷方法"""
        # 在CLI模式下，确认是同步处理的，不需要通过ConfirmationManager
        if not self.api_mode:
            logger.info("CLI mode: confirmation handled synchronously")
            return True
        else:
            # API模式下才使用ConfirmationManager
            logger.info("API mode: confirmation handled synchronously")
            # 检查确认管理器的接口类型
            if hasattr(self.confirmation_manager, 'submit_confirmation'):
                # 检查是否为ChatStreamConfirmationManager (async方法)
                import inspect
                if inspect.iscoroutinefunction(self.confirmation_manager.submit_confirmation):
                    # ChatStreamConfirmationManager - 异步调用和不同参数
                    try:
                        return await self.confirmation_manager.submit_confirmation(
                            response.session_id, 
                            response.action, 
                            getattr(response, 'user_message', None)
                        )
                    except Exception as e:
                        logger.error(f"Failed to submit confirmation: {e}")
                        return False
                else:
                    # ConfirmationManager - 同步调用
                    return self.confirmation_manager.submit_confirmation(response)
            return False
    
    def handle_cli_confirmation(self, session_id: str, tasks_summary: Dict[str, Any], confirmation_round: int = 1):
        """
        处理CLI模式的确认界面交互
        
        Args:
            session_id: 会话ID
            tasks_summary: 任务摘要信息
            confirmation_round: 确认轮数
            
        Returns:
            TaskConfirmationResponse: 用户的确认响应
        """
        from rich.console import Console
        from ..api.models import TaskConfirmationResponse
        
        console = Console()
        
        # 显示任务详情
        tasks = tasks_summary.get("tasks", [])
        for task in tasks:
            console.print(f"[cyan]{task['index']}.[/cyan] {task['description']}")
            console.print(f"   工具: {task['tool']} | 优先级: {task['priority']}")
            console.print(f"   预期结果: {task['expected_outcome']}")
            console.print()
        
        # 用户选择循环
        while True:
            try:
                console.print("[bold blue]请选择操作:[/bold blue]")
                console.print("1. 确认执行")
                console.print("2. 修改计划")
                console.print("3. 取消执行")
                
                choice = console.input("请输入选择 [1-3]: ").strip()
                
                if choice in ["1", "2", "3"]:
                    break
                else:
                    console.print("[red]无效选择，请输入 1、2 或 3[/red]")
            except (KeyboardInterrupt, EOFError):
                choice = "3"  # Default to cancel
                break
        
        # 构建响应
        if choice == "1":
            response = TaskConfirmationResponse(
                session_id=session_id,
                action="confirm"
            )
            console.print("[green]✅ 已确认执行计划[/green]\n")
            
        elif choice == "2":
            # 获取用户修改建议
            try:
                user_message = console.input("请描述需要如何修改计划: ")
            except (KeyboardInterrupt, EOFError):
                user_message = ""
            
            response = TaskConfirmationResponse(
                session_id=session_id,
                action="modify",
                user_message=user_message
            )
            console.print("[yellow]📝 已请求修改计划[/yellow]\n")
            
        else:  # choice == "3"
            response = TaskConfirmationResponse(
                session_id=session_id,
                action="cancel"
            )
            console.print("[red]❌ 已取消执行[/red]\n")
        
        # CLI模式下不需要通过ConfirmationManager提交，直接返回响应
        return response
    
    async def _replan_tasks_with_user_feedback(self, session: ReActSession, user_feedback: str):
        """根据用户反馈重新规划任务"""
        
        logger.info(f"Replanning tasks based on user feedback: {user_feedback}")
        
        try:
            # 构建包含用户反馈的规划上下文
            original_tasks_summary = "\n".join([
                f"- {task.description} (using {task.tool_name})"
                for task in session.tasks
            ])
            
            # 创建增强的规划上下文，包含原始任务和用户反馈
            enhanced_user_input = f"""
原始请求: {session.user_input}

原始规划的任务:
{original_tasks_summary}

用户修改要求: {user_feedback}

请根据用户的修改要求，重新规划任务列表。
"""
            
            from .planner import PlanningContext
            planning_context = PlanningContext(
                user_input=enhanced_user_input,
                conversation_history=session.conversation_history,
                available_tools=self.tool_registry.list_tools(),
                project_context=session.metadata.get("project_context", {}),
                constraints=session.metadata.get("planning_context", {}).get("constraints", {})
            )
            
            # 重新规划任务
            session.update_state(ReActState.PLANNING)
            session.add_log_entry("Replanning tasks based on user feedback")
            
            new_tasks = await self.task_planner.plan_tasks(planning_context)
            
            if new_tasks:
                # 更新任务列表
                old_task_count = len(session.tasks)
                session.tasks = new_tasks
                session.add_log_entry(f"Tasks replanned: {old_task_count} -> {len(new_tasks)} tasks")
                
                logger.info(f"Successfully replanned tasks: {len(new_tasks)} new tasks generated")
            else:
                # 如果重新规划失败，保留原任务但记录警告
                session.add_log_entry("Task replanning produced no tasks, keeping original plan")
                logger.warning("Task replanning produced no tasks, keeping original plan")
                
        except Exception as e:
            # 重新规划失败时的错误处理
            session.add_log_entry(f"Task replanning failed: {str(e)}, keeping original plan")
            logger.error(f"Task replanning failed: {str(e)}")
            # 不抛出异常，继续使用原始任务计划