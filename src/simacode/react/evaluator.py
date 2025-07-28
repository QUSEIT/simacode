"""
Result Evaluation Module for ReAct Engine

This module implements result evaluation capabilities for assessing task
execution outcomes and determining next actions.
"""

import asyncio
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from ..ai.base import AIClient, Role
from ..ai.conversation import Message
from ..tools.base import ToolResult, ToolResultType
from .exceptions import EvaluationError
from .planner import Task, TaskStatus


class EvaluationOutcome(Enum):
    """Evaluation outcome enumeration."""
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE = "failure"
    NEEDS_RETRY = "needs_retry"
    NEEDS_REPLANNING = "needs_replanning"


class ConfidenceLevel(Enum):
    """Confidence level for evaluation results."""
    HIGH = "high"      # 90-100% confident
    MEDIUM = "medium"  # 70-89% confident
    LOW = "low"        # 50-69% confident
    VERY_LOW = "very_low"  # Below 50%


@dataclass
class EvaluationResult:
    """
    Result of task execution evaluation.
    
    Contains assessment of whether the task was successful, reasoning
    behind the evaluation, and recommendations for next actions.
    """
    outcome: EvaluationOutcome
    confidence: ConfidenceLevel
    success_score: float  # 0.0 to 1.0
    reasoning: str = ""
    evidence: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    next_actions: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    evaluated_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert evaluation result to dictionary."""
        return {
            "outcome": self.outcome.value,
            "confidence": self.confidence.value,
            "success_score": self.success_score,
            "reasoning": self.reasoning,
            "evidence": self.evidence,
            "recommendations": self.recommendations,
            "next_actions": self.next_actions,
            "metadata": self.metadata,
            "evaluated_at": self.evaluated_at.isoformat()
        }


class EvaluationContext(BaseModel):
    """Context information for result evaluation."""
    task: Dict[str, Any]  # Task being evaluated
    tool_results: List[Dict[str, Any]]  # Results from tool execution
    expected_outcome: str = ""
    user_intent: str = ""
    project_context: Dict[str, Any] = {}


class ResultEvaluator:
    """
    Result evaluator for the ReAct engine.
    
    The ResultEvaluator analyzes tool execution results to determine if tasks
    were completed successfully and what actions should be taken next.
    """
    
    def __init__(self, ai_client: AIClient):
        """Initialize the result evaluator."""
        self.ai_client = ai_client
        
        # Evaluation prompts
        self.EVALUATION_SYSTEM_PROMPT = """
You are a result evaluation expert for an AI programming assistant. Your role is to:

1. Analyze tool execution results against expected outcomes
2. Determine if tasks were completed successfully
3. Identify partial successes and areas for improvement
4. Recommend next actions or alternative approaches

For each evaluation, consider:
- Did the tool execution complete without errors?
- Does the output match the expected outcome?
- Are there any quality issues with the result?
- What is the confidence level of this assessment?

Respond with a JSON object in the following format:
{{
  "outcome": "success|partial_success|failure|needs_retry|needs_replanning",
  "confidence": "high|medium|low|very_low",
  "success_score": 0.85,
  "reasoning": "Detailed explanation of the evaluation",
  "evidence": ["Evidence point 1", "Evidence point 2"],
  "recommendations": ["Recommendation 1", "Recommendation 2"],
  "next_actions": ["Action 1", "Action 2"]
}}

Be thorough, objective, and provide actionable insights.
"""
    
    async def evaluate_task_result(self, task: Task, tool_results: List[ToolResult], context: Optional[EvaluationContext] = None) -> EvaluationResult:
        """
        Evaluate the results of a task execution.
        
        Args:
            task: The task that was executed
            tool_results: Results from tool execution
            context: Additional evaluation context
            
        Returns:
            EvaluationResult: Detailed evaluation of the task execution
            
        Raises:
            EvaluationError: If evaluation fails
        """
        try:
            # First, perform rule-based evaluation
            rule_based_result = await self._rule_based_evaluation(task, tool_results)
            
            # If rule-based evaluation is conclusive, return it
            if rule_based_result.confidence in [ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM]:
                return rule_based_result
            
            # Otherwise, use AI-based evaluation for complex cases
            ai_based_result = await self._ai_based_evaluation(task, tool_results, context)
            
            # Combine insights from both approaches
            return await self._combine_evaluations(rule_based_result, ai_based_result)
            
        except Exception as e:
            raise EvaluationError(
                f"Failed to evaluate task result: {str(e)}",
                expected_outcome=task.expected_outcome,
                context={"task_id": task.id, "error_type": type(e).__name__}
            )
    
    async def _rule_based_evaluation(self, task: Task, tool_results: List[ToolResult]) -> EvaluationResult:
        """Perform rule-based evaluation of task results."""
        try:
            # Analyze tool results
            has_errors = any(result.type == ToolResultType.ERROR for result in tool_results)
            has_success = any(result.type == ToolResultType.SUCCESS for result in tool_results)
            has_output = any(result.type == ToolResultType.OUTPUT for result in tool_results)
            
            evidence = []
            recommendations = []
            next_actions = []
            
            # Determine outcome based on results
            if has_errors and not has_success:
                outcome = EvaluationOutcome.FAILURE
                confidence = ConfidenceLevel.HIGH
                success_score = 0.0
                reasoning = "Task failed with errors and no successful completion"
                
                # Extract error information
                error_results = [r for r in tool_results if r.type == ToolResultType.ERROR]
                evidence.extend([f"Error: {r.content}" for r in error_results])
                recommendations.append("Review error messages and fix underlying issues")
                next_actions.append("Replan task with error handling")
                
            elif has_success and not has_errors:
                outcome = EvaluationOutcome.SUCCESS
                confidence = ConfidenceLevel.HIGH
                success_score = 1.0
                reasoning = "Task completed successfully without errors"
                
                success_results = [r for r in tool_results if r.type == ToolResultType.SUCCESS]
                evidence.extend([f"Success: {r.content}" for r in success_results])
                next_actions.append("Proceed to next task")
                
            elif has_success and has_errors:
                outcome = EvaluationOutcome.PARTIAL_SUCCESS
                confidence = ConfidenceLevel.MEDIUM
                success_score = 0.6
                reasoning = "Task partially completed with some errors"
                
                evidence.append("Mixed results with both successes and errors")
                recommendations.append("Review errors to determine if they are critical")
                next_actions.append("Evaluate if partial result is acceptable")
                
            elif has_output and not has_errors:
                # Need AI evaluation to determine if output meets expectations
                outcome = EvaluationOutcome.PARTIAL_SUCCESS
                confidence = ConfidenceLevel.LOW
                success_score = 0.5
                reasoning = "Task produced output but unclear if expectations are met"
                
                evidence.append("Tool produced output without explicit success/error indicators")
                next_actions.append("Requires detailed output analysis")
                
            else:
                outcome = EvaluationOutcome.FAILURE
                confidence = ConfidenceLevel.MEDIUM
                success_score = 0.1
                reasoning = "No clear success indicators or meaningful output"
                
                evidence.append("No success indicators or meaningful output detected")
                recommendations.append("Check tool configuration and input parameters")
                next_actions.append("Retry with revised parameters")
            
            return EvaluationResult(
                outcome=outcome,
                confidence=confidence,
                success_score=success_score,
                reasoning=reasoning,
                evidence=evidence,
                recommendations=recommendations,
                next_actions=next_actions,
                metadata={
                    "evaluation_method": "rule_based",
                    "result_counts": {
                        "errors": len([r for r in tool_results if r.type == ToolResultType.ERROR]),
                        "successes": len([r for r in tool_results if r.type == ToolResultType.SUCCESS]),
                        "outputs": len([r for r in tool_results if r.type == ToolResultType.OUTPUT])
                    }
                }
            )
            
        except Exception as e:
            # Fallback evaluation
            return EvaluationResult(
                outcome=EvaluationOutcome.FAILURE,
                confidence=ConfidenceLevel.VERY_LOW,
                success_score=0.0,
                reasoning=f"Rule-based evaluation failed: {str(e)}",
                evidence=[f"Evaluation error: {str(e)}"],
                next_actions=["Requires manual review"]
            )
    
    async def _ai_based_evaluation(self, task: Task, tool_results: List[ToolResult], context: Optional[EvaluationContext] = None) -> EvaluationResult:
        """Perform AI-based evaluation of task results."""
        try:
            # Prepare evaluation context
            evaluation_prompt = self._create_evaluation_prompt(task, tool_results, context)
            
            # Create messages for AI evaluation
            messages = [
                Message(role=Role.SYSTEM, content=self.EVALUATION_SYSTEM_PROMPT),
                Message(role=Role.USER, content=evaluation_prompt)
            ]
            
            # Get AI evaluation
            response = await self.ai_client.chat(messages)
            
            # Parse evaluation result
            result = await self._parse_evaluation_response(response.content)
            
            # Add metadata
            result.metadata.update({
                "evaluation_method": "ai_based",
                "ai_response_length": len(response.content)
            })
            
            return result
            
        except Exception as e:
            raise EvaluationError(f"AI-based evaluation failed: {str(e)}")
    
    def _create_evaluation_prompt(self, task: Task, tool_results: List[ToolResult], context: Optional[EvaluationContext] = None) -> str:
        """Create detailed evaluation prompt for AI analysis."""
        prompt_parts = []
        
        # Task information
        prompt_parts.append(f"Task to evaluate:")
        prompt_parts.append(f"- Description: {task.description}")
        prompt_parts.append(f"- Tool used: {task.tool_name}")
        prompt_parts.append(f"- Expected outcome: {task.expected_outcome}")
        prompt_parts.append(f"- Tool input: {json.dumps(task.tool_input, indent=2)}")
        
        # Tool results
        prompt_parts.append(f"\nTool execution results:")
        for i, result in enumerate(tool_results):
            prompt_parts.append(f"Result {i+1}:")
            prompt_parts.append(f"  Type: {result.type.value}")
            prompt_parts.append(f"  Content: {result.content}")
            prompt_parts.append(f"  Timestamp: {result.timestamp}")
            if result.metadata:
                prompt_parts.append(f"  Metadata: {json.dumps(result.metadata, indent=4)}")
        
        # Additional context
        if context:
            if context.user_intent:
                prompt_parts.append(f"\nUser intent: {context.user_intent}")
            if context.project_context:
                prompt_parts.append(f"\nProject context: {json.dumps(context.project_context, indent=2)}")
        
        prompt_parts.append(f"\nPlease evaluate if this task execution was successful and provide detailed analysis.")
        
        return "\n".join(prompt_parts)
    
    async def _parse_evaluation_response(self, response_content: str) -> EvaluationResult:
        """Parse evaluation result from AI response."""
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
            eval_data = json.loads(response_content)
            
            return EvaluationResult(
                outcome=EvaluationOutcome(eval_data.get("outcome", "failure")),
                confidence=ConfidenceLevel(eval_data.get("confidence", "low")),
                success_score=float(eval_data.get("success_score", 0.0)),
                reasoning=eval_data.get("reasoning", ""),
                evidence=eval_data.get("evidence", []),
                recommendations=eval_data.get("recommendations", []),
                next_actions=eval_data.get("next_actions", [])
            )
            
        except Exception as e:
            raise EvaluationError(f"Failed to parse evaluation response: {str(e)}")
    
    async def _combine_evaluations(self, rule_based: EvaluationResult, ai_based: EvaluationResult) -> EvaluationResult:
        """Combine rule-based and AI-based evaluation results."""
        # Use rule-based outcome if it's more confident
        if rule_based.confidence.value in ["high", "medium"] and ai_based.confidence.value in ["low", "very_low"]:
            primary_result = rule_based
            secondary_result = ai_based
        else:
            primary_result = ai_based
            secondary_result = rule_based
        
        # Combine evidence and recommendations
        combined_evidence = primary_result.evidence + secondary_result.evidence
        combined_recommendations = primary_result.recommendations + secondary_result.recommendations
        combined_next_actions = primary_result.next_actions + secondary_result.next_actions
        
        # Average success scores
        combined_score = (primary_result.success_score + secondary_result.success_score) / 2
        
        # Create combined reasoning
        combined_reasoning = f"{primary_result.reasoning} (Combined with secondary evaluation: {secondary_result.reasoning})"
        
        return EvaluationResult(
            outcome=primary_result.outcome,
            confidence=primary_result.confidence,
            success_score=combined_score,
            reasoning=combined_reasoning,
            evidence=list(set(combined_evidence)),  # Remove duplicates
            recommendations=list(set(combined_recommendations)),
            next_actions=list(set(combined_next_actions)),
            metadata={
                "evaluation_method": "combined",
                "primary_method": primary_result.metadata.get("evaluation_method", "unknown"),
                "secondary_method": secondary_result.metadata.get("evaluation_method", "unknown")
            }
        )
    
    async def evaluate_overall_progress(self, tasks: List[Task], task_results: Dict[str, EvaluationResult]) -> EvaluationResult:
        """
        Evaluate overall progress across multiple tasks.
        
        Args:
            tasks: List of all tasks in the plan
            task_results: Evaluation results for completed tasks
            
        Returns:
            EvaluationResult: Overall progress evaluation
        """
        try:
            completed_tasks = len(task_results)
            total_tasks = len(tasks)
            
            if total_tasks == 0:
                return EvaluationResult(
                    outcome=EvaluationOutcome.FAILURE,
                    confidence=ConfidenceLevel.HIGH,
                    success_score=0.0,
                    reasoning="No tasks defined",
                    evidence=["Task list is empty"]
                )
            
            # Calculate success metrics
            successful_tasks = sum(1 for result in task_results.values() 
                                 if result.outcome == EvaluationOutcome.SUCCESS)
            failed_tasks = sum(1 for result in task_results.values() 
                             if result.outcome == EvaluationOutcome.FAILURE)
            
            completion_rate = completed_tasks / total_tasks
            success_rate = successful_tasks / completed_tasks if completed_tasks > 0 else 0
            
            # Determine overall outcome
            if completion_rate == 1.0 and success_rate >= 0.8:
                outcome = EvaluationOutcome.SUCCESS
                confidence = ConfidenceLevel.HIGH
            elif completion_rate >= 0.5 and success_rate >= 0.6:
                outcome = EvaluationOutcome.PARTIAL_SUCCESS
                confidence = ConfidenceLevel.MEDIUM
            elif failed_tasks > successful_tasks:
                outcome = EvaluationOutcome.FAILURE
                confidence = ConfidenceLevel.HIGH
            else:
                outcome = EvaluationOutcome.NEEDS_RETRY
                confidence = ConfidenceLevel.MEDIUM
            
            success_score = (completion_rate * 0.5) + (success_rate * 0.5)
            
            evidence = [
                f"Completed {completed_tasks}/{total_tasks} tasks",
                f"Success rate: {success_rate:.1%}",
                f"Successful tasks: {successful_tasks}",
                f"Failed tasks: {failed_tasks}"
            ]
            
            return EvaluationResult(
                outcome=outcome,
                confidence=confidence,
                success_score=success_score,
                reasoning=f"Overall progress evaluation: {completion_rate:.1%} completion, {success_rate:.1%} success rate",
                evidence=evidence,
                metadata={
                    "evaluation_method": "overall_progress",
                    "completion_rate": completion_rate,
                    "success_rate": success_rate,
                    "total_tasks": total_tasks,
                    "completed_tasks": completed_tasks,
                    "successful_tasks": successful_tasks,
                    "failed_tasks": failed_tasks
                }
            )
            
        except Exception as e:
            raise EvaluationError(f"Failed to evaluate overall progress: {str(e)}")