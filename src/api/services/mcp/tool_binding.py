"""
Dynamic Tool Binding and Execution Framework

This module provides dynamic tool binding and execution capabilities for the MCP system,
enabling agents to dynamically discover, bind, and execute tools at runtime.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Callable, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json
import uuid
import inspect
from functools import wraps

from .tool_discovery import ToolDiscoveryService, DiscoveredTool, ToolCategory
from .base import MCPAdapter, MCPToolBase, MCPManager

logger = logging.getLogger(__name__)


class BindingStrategy(Enum):
    """Tool binding strategies."""

    EXACT_MATCH = "exact_match"
    FUZZY_MATCH = "fuzzy_match"
    SEMANTIC_MATCH = "semantic_match"
    CATEGORY_MATCH = "category_match"
    PERFORMANCE_BASED = "performance_based"


class ExecutionMode(Enum):
    """Tool execution modes."""

    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    PIPELINE = "pipeline"
    CONDITIONAL = "conditional"


@dataclass
class ToolBinding:
    """Represents a tool binding."""

    binding_id: str
    tool_id: str
    agent_id: str
    binding_strategy: BindingStrategy
    binding_confidence: float
    created_at: datetime
    last_used: Optional[datetime] = None
    usage_count: int = 0
    success_rate: float = 0.0
    average_response_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionContext:
    """Context for tool execution."""

    session_id: str
    agent_id: str
    query: str
    intent: str
    entities: Dict[str, Any]
    context: Dict[str, Any]
    execution_mode: ExecutionMode = ExecutionMode.SEQUENTIAL
    timeout: int = 30
    retry_attempts: int = 3
    fallback_enabled: bool = True


@dataclass
class ExecutionResult:
    """Result of tool execution."""

    tool_id: str
    tool_name: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    execution_time: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionPlan:
    """Plan for tool execution."""

    plan_id: str
    context: ExecutionContext
    steps: List[Dict[str, Any]]
    dependencies: Dict[str, List[str]] = field(default_factory=dict)
    fallback_steps: List[Dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)


class ToolBindingService:
    """
    Service for dynamic tool binding and execution.

    This service provides:
    - Dynamic tool binding based on various strategies
    - Tool execution planning and orchestration
    - Performance monitoring and optimization
    - Fallback mechanisms and error handling
    - Tool composition and chaining
    """

    def __init__(self, tool_discovery: ToolDiscoveryService):
        self.tool_discovery = tool_discovery
        self.bindings: Dict[str, ToolBinding] = {}
        self.execution_history: List[Dict[str, Any]] = []
        self.performance_metrics: Dict[str, Dict[str, Any]] = {}
        self.binding_strategies: Dict[BindingStrategy, Callable] = {
            BindingStrategy.EXACT_MATCH: self._exact_match_binding,
            BindingStrategy.FUZZY_MATCH: self._fuzzy_match_binding,
            BindingStrategy.SEMANTIC_MATCH: self._semantic_match_binding,
            BindingStrategy.CATEGORY_MATCH: self._category_match_binding,
            BindingStrategy.PERFORMANCE_BASED: self._performance_based_binding,
        }
        self._execution_lock = asyncio.Lock()

    async def bind_tools(
        self,
        agent_id: str,
        query: str,
        intent: str,
        entities: Dict[str, Any],
        context: Dict[str, Any],
        strategy: BindingStrategy = BindingStrategy.SEMANTIC_MATCH,
        max_tools: int = 5,
    ) -> List[ToolBinding]:
        """
        Bind tools to an agent based on query and context.

        Args:
            agent_id: ID of the agent requesting tools
            query: User query
            intent: Query intent
            entities: Extracted entities
            context: Additional context
            strategy: Binding strategy to use
            max_tools: Maximum number of tools to bind

        Returns:
            List of tool bindings
        """
        try:
            # Get binding function for strategy
            binding_func = self.binding_strategies.get(strategy)
            if not binding_func:
                raise ValueError(f"Unknown binding strategy: {strategy}")

            # Discover relevant tools
            relevant_tools = await self._discover_relevant_tools(
                query, intent, entities, context
            )

            # Apply binding strategy
            bindings = await binding_func(agent_id, relevant_tools, max_tools)

            # Store bindings
            for binding in bindings:
                self.bindings[binding.binding_id] = binding

            logger.info(
                f"Bound {len(bindings)} tools to agent {agent_id} using {strategy.value} strategy"
            )
            return bindings

        except Exception as e:
            logger.error(f"Error binding tools for agent {agent_id}: {e}")
            return []

    async def _exact_match_binding(
        self, agent_id: str, tools: List[DiscoveredTool], max_tools: int
    ) -> List[ToolBinding]:
        """Exact match binding strategy."""
        bindings = []

        for tool in tools[:max_tools]:
            binding = ToolBinding(
                binding_id=str(uuid.uuid4()),
                tool_id=tool.tool_id,
                agent_id=agent_id,
                binding_strategy=BindingStrategy.EXACT_MATCH,
                binding_confidence=1.0,
                created_at=datetime.utcnow(),
            )
            bindings.append(binding)

        return bindings

    async def _fuzzy_match_binding(
        self, agent_id: str, tools: List[DiscoveredTool], max_tools: int
    ) -> List[ToolBinding]:
        """Fuzzy match binding strategy."""
        bindings = []

        # Sort tools by usage count and success rate
        sorted_tools = sorted(
            tools, key=lambda t: (t.usage_count, t.success_rate), reverse=True
        )

        for tool in sorted_tools[:max_tools]:
            confidence = min(0.9, tool.success_rate + (tool.usage_count * 0.1))

            binding = ToolBinding(
                binding_id=str(uuid.uuid4()),
                tool_id=tool.tool_id,
                agent_id=agent_id,
                binding_strategy=BindingStrategy.FUZZY_MATCH,
                binding_confidence=confidence,
                created_at=datetime.utcnow(),
            )
            bindings.append(binding)

        return bindings

    async def _semantic_match_binding(
        self, agent_id: str, tools: List[DiscoveredTool], max_tools: int
    ) -> List[ToolBinding]:
        """Semantic match binding strategy."""
        bindings = []

        # This would use semantic similarity matching
        # For now, we'll use a simple scoring system
        for tool in tools[:max_tools]:
            # Calculate semantic confidence based on tool description and capabilities
            confidence = 0.7  # Base confidence
            if "equipment" in tool.description.lower():
                confidence += 0.1
            if "asset" in tool.description.lower():
                confidence += 0.1
            if tool.category in [ToolCategory.EQUIPMENT, ToolCategory.OPERATIONS]:
                confidence += 0.1

            confidence = min(0.95, confidence)

            binding = ToolBinding(
                binding_id=str(uuid.uuid4()),
                tool_id=tool.tool_id,
                agent_id=agent_id,
                binding_strategy=BindingStrategy.SEMANTIC_MATCH,
                binding_confidence=confidence,
                created_at=datetime.utcnow(),
            )
            bindings.append(binding)

        return bindings

    async def _category_match_binding(
        self, agent_id: str, tools: List[DiscoveredTool], max_tools: int
    ) -> List[ToolBinding]:
        """Category match binding strategy."""
        bindings = []

        # Group tools by category and select best from each
        category_tools = {}
        for tool in tools:
            if tool.category not in category_tools:
                category_tools[tool.category] = []
            category_tools[tool.category].append(tool)

        for category, category_tool_list in category_tools.items():
            if len(bindings) >= max_tools:
                break

            # Select best tool from category
            best_tool = max(category_tool_list, key=lambda t: t.success_rate)

            binding = ToolBinding(
                binding_id=str(uuid.uuid4()),
                tool_id=best_tool.tool_id,
                agent_id=agent_id,
                binding_strategy=BindingStrategy.CATEGORY_MATCH,
                binding_confidence=0.8,
                created_at=datetime.utcnow(),
            )
            bindings.append(binding)

        return bindings

    async def _performance_based_binding(
        self, agent_id: str, tools: List[DiscoveredTool], max_tools: int
    ) -> List[ToolBinding]:
        """Performance-based binding strategy."""
        bindings = []

        # Sort by performance metrics
        sorted_tools = sorted(
            tools,
            key=lambda t: (t.success_rate, -t.average_response_time, t.usage_count),
            reverse=True,
        )

        for tool in sorted_tools[:max_tools]:
            confidence = (
                tool.success_rate * 0.8
                + (1.0 - min(tool.average_response_time / 10.0, 1.0)) * 0.2
            )

            binding = ToolBinding(
                binding_id=str(uuid.uuid4()),
                tool_id=tool.tool_id,
                agent_id=agent_id,
                binding_strategy=BindingStrategy.PERFORMANCE_BASED,
                binding_confidence=confidence,
                created_at=datetime.utcnow(),
            )
            bindings.append(binding)

        return bindings

    async def _discover_relevant_tools(
        self, query: str, intent: str, entities: Dict[str, Any], context: Dict[str, Any]
    ) -> List[DiscoveredTool]:
        """Discover tools relevant to the query."""
        try:
            # Search for tools based on intent
            intent_tools = await self.tool_discovery.search_tools(intent)

            # Search for tools based on entities
            entity_tools = []
            for entity_type, entity_value in entities.items():
                entity_search = f"{entity_type} {entity_value}"
                tools = await self.tool_discovery.search_tools(entity_search)
                entity_tools.extend(tools)

            # Search for tools based on query
            query_tools = await self.tool_discovery.search_tools(query)

            # Combine and deduplicate
            all_tools = intent_tools + entity_tools + query_tools
            unique_tools = {}
            for tool in all_tools:
                if tool.tool_id not in unique_tools:
                    unique_tools[tool.tool_id] = tool

            return list(unique_tools.values())

        except Exception as e:
            logger.error(f"Error discovering relevant tools: {e}")
            return []

    async def create_execution_plan(
        self,
        context: ExecutionContext,
        bindings: List[ToolBinding],
        execution_mode: ExecutionMode = ExecutionMode.SEQUENTIAL,
    ) -> ExecutionPlan:
        """
        Create an execution plan for bound tools.

        Args:
            context: Execution context
            bindings: Tool bindings to execute
            execution_mode: Execution mode

        Returns:
            Execution plan
        """
        try:
            plan_id = str(uuid.uuid4())
            steps = []

            # Create execution steps based on mode
            if execution_mode == ExecutionMode.SEQUENTIAL:
                steps = self._create_sequential_steps(bindings, context)
            elif execution_mode == ExecutionMode.PARALLEL:
                steps = self._create_parallel_steps(bindings, context)
            elif execution_mode == ExecutionMode.PIPELINE:
                steps = self._create_pipeline_steps(bindings, context)
            elif execution_mode == ExecutionMode.CONDITIONAL:
                steps = self._create_conditional_steps(bindings, context)

            # Create fallback steps
            fallback_steps = self._create_fallback_steps(bindings, context)

            plan = ExecutionPlan(
                plan_id=plan_id,
                context=context,
                steps=steps,
                fallback_steps=fallback_steps,
            )

            logger.info(f"Created execution plan {plan_id} with {len(steps)} steps")
            return plan

        except Exception as e:
            logger.error(f"Error creating execution plan: {e}")
            raise

    def _create_sequential_steps(
        self, bindings: List[ToolBinding], context: ExecutionContext
    ) -> List[Dict[str, Any]]:
        """Create sequential execution steps."""
        steps = []

        for i, binding in enumerate(bindings):
            step = {
                "step_id": f"step_{i+1}",
                "binding_id": binding.binding_id,
                "tool_id": binding.tool_id,
                "order": i + 1,
                "dependencies": [f"step_{i}"] if i > 0 else [],
                "arguments": self._prepare_arguments(binding, context),
                "timeout": context.timeout,
                "retry_attempts": context.retry_attempts,
            }
            steps.append(step)

        return steps

    def _create_parallel_steps(
        self, bindings: List[ToolBinding], context: ExecutionContext
    ) -> List[Dict[str, Any]]:
        """Create parallel execution steps."""
        steps = []

        for i, binding in enumerate(bindings):
            step = {
                "step_id": f"step_{i+1}",
                "binding_id": binding.binding_id,
                "tool_id": binding.tool_id,
                "order": 1,  # All parallel
                "dependencies": [],
                "arguments": self._prepare_arguments(binding, context),
                "timeout": context.timeout,
                "retry_attempts": context.retry_attempts,
            }
            steps.append(step)

        return steps

    def _create_pipeline_steps(
        self, bindings: List[ToolBinding], context: ExecutionContext
    ) -> List[Dict[str, Any]]:
        """Create pipeline execution steps."""
        steps = []

        for i, binding in enumerate(bindings):
            step = {
                "step_id": f"step_{i+1}",
                "binding_id": binding.binding_id,
                "tool_id": binding.tool_id,
                "order": i + 1,
                "dependencies": [f"step_{i}"] if i > 0 else [],
                "arguments": self._prepare_arguments(binding, context),
                "timeout": context.timeout,
                "retry_attempts": context.retry_attempts,
                "pipeline_mode": True,
                "input_from_previous": i > 0,
            }
            steps.append(step)

        return steps

    def _create_conditional_steps(
        self, bindings: List[ToolBinding], context: ExecutionContext
    ) -> List[Dict[str, Any]]:
        """Create conditional execution steps."""
        steps = []

        # First step is always executed
        if bindings:
            first_binding = bindings[0]
            step = {
                "step_id": "step_1",
                "binding_id": first_binding.binding_id,
                "tool_id": first_binding.tool_id,
                "order": 1,
                "dependencies": [],
                "arguments": self._prepare_arguments(first_binding, context),
                "timeout": context.timeout,
                "retry_attempts": context.retry_attempts,
                "conditional": False,
            }
            steps.append(step)

        # Remaining steps are conditional
        for i, binding in enumerate(bindings[1:], 1):
            step = {
                "step_id": f"step_{i+1}",
                "binding_id": binding.binding_id,
                "tool_id": binding.tool_id,
                "order": i + 1,
                "dependencies": [f"step_{i}"],
                "arguments": self._prepare_arguments(binding, context),
                "timeout": context.timeout,
                "retry_attempts": context.retry_attempts,
                "conditional": True,
                "condition": f"step_{i}.success == true",
            }
            steps.append(step)

        return steps

    def _create_fallback_steps(
        self, bindings: List[ToolBinding], context: ExecutionContext
    ) -> List[Dict[str, Any]]:
        """Create fallback execution steps."""
        fallback_steps = []

        # Create fallback steps for high-priority tools
        high_priority_bindings = [b for b in bindings if b.binding_confidence > 0.8]

        for i, binding in enumerate(high_priority_bindings):
            step = {
                "step_id": f"fallback_{i+1}",
                "binding_id": binding.binding_id,
                "tool_id": binding.tool_id,
                "order": i + 1,
                "dependencies": [],
                "arguments": self._prepare_arguments(binding, context),
                "timeout": context.timeout,
                "retry_attempts": context.retry_attempts,
                "fallback": True,
            }
            fallback_steps.append(step)

        return fallback_steps

    def _prepare_arguments(
        self, binding: ToolBinding, context: ExecutionContext
    ) -> Dict[str, Any]:
        """Prepare arguments for tool execution."""
        # Get tool details
        tool = self.tool_discovery.discovered_tools.get(binding.tool_id)
        if not tool:
            return {}

        arguments = {}

        # Map context to tool parameters
        for param_name, param_schema in tool.parameters.items():
            if param_name in context.entities:
                arguments[param_name] = context.entities[param_name]
            elif param_name == "query":
                arguments[param_name] = context.query
            elif param_name == "intent":
                arguments[param_name] = context.intent
            elif param_name == "context":
                arguments[param_name] = context.context
            elif param_name == "session_id":
                arguments[param_name] = context.session_id

        return arguments

    async def execute_plan(self, plan: ExecutionPlan) -> List[ExecutionResult]:
        """
        Execute an execution plan.

        Args:
            plan: Execution plan to execute

        Returns:
            List of execution results
        """
        try:
            async with self._execution_lock:
                results = []

                if plan.context.execution_mode == ExecutionMode.SEQUENTIAL:
                    results = await self._execute_sequential(plan)
                elif plan.context.execution_mode == ExecutionMode.PARALLEL:
                    results = await self._execute_parallel(plan)
                elif plan.context.execution_mode == ExecutionMode.PIPELINE:
                    results = await self._execute_pipeline(plan)
                elif plan.context.execution_mode == ExecutionMode.CONDITIONAL:
                    results = await self._execute_conditional(plan)

                # Record execution history
                self.execution_history.append(
                    {
                        "plan_id": plan.plan_id,
                        "context": plan.context,
                        "results": results,
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                )

                return results

        except Exception as e:
            logger.error(f"Error executing plan {plan.plan_id}: {e}")
            return []

    async def _execute_sequential(self, plan: ExecutionPlan) -> List[ExecutionResult]:
        """Execute steps sequentially."""
        results = []

        for step in plan.steps:
            try:
                result = await self._execute_step(step, plan.context)
                results.append(result)

                # Stop if step failed and no fallback
                if not result.success and not plan.context.fallback_enabled:
                    break

            except Exception as e:
                logger.error(f"Error executing step {step['step_id']}: {e}")
                results.append(
                    ExecutionResult(
                        tool_id=step["tool_id"],
                        tool_name="unknown",
                        success=False,
                        error=str(e),
                    )
                )

        return results

    async def _execute_parallel(self, plan: ExecutionPlan) -> List[ExecutionResult]:
        """Execute steps in parallel."""
        tasks = []

        for step in plan.steps:
            task = asyncio.create_task(self._execute_step(step, plan.context))
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to failed results
        execution_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                step = plan.steps[i]
                execution_results.append(
                    ExecutionResult(
                        tool_id=step["tool_id"],
                        tool_name="unknown",
                        success=False,
                        error=str(result),
                    )
                )
            else:
                execution_results.append(result)

        return execution_results

    async def _execute_pipeline(self, plan: ExecutionPlan) -> List[ExecutionResult]:
        """Execute steps in pipeline mode."""
        results = []
        pipeline_data = {}

        for step in plan.steps:
            try:
                # Add pipeline data to arguments
                if step.get("input_from_previous") and results:
                    step["arguments"]["pipeline_data"] = pipeline_data

                result = await self._execute_step(step, plan.context)
                results.append(result)

                # Update pipeline data with result
                if result.success:
                    pipeline_data[step["tool_id"]] = result.result

            except Exception as e:
                logger.error(f"Error executing pipeline step {step['step_id']}: {e}")
                results.append(
                    ExecutionResult(
                        tool_id=step["tool_id"],
                        tool_name="unknown",
                        success=False,
                        error=str(e),
                    )
                )

        return results

    async def _execute_conditional(self, plan: ExecutionPlan) -> List[ExecutionResult]:
        """Execute steps conditionally."""
        results = []

        for step in plan.steps:
            try:
                # Check condition
                if step.get("conditional", False):
                    condition = step.get("condition", "")
                    if not self._evaluate_condition(condition, results):
                        continue

                result = await self._execute_step(step, plan.context)
                results.append(result)

            except Exception as e:
                logger.error(f"Error executing conditional step {step['step_id']}: {e}")
                results.append(
                    ExecutionResult(
                        tool_id=step["tool_id"],
                        tool_name="unknown",
                        success=False,
                        error=str(e),
                    )
                )

        return results

    def _evaluate_condition(
        self, condition: str, results: List[ExecutionResult]
    ) -> bool:
        """Evaluate a condition string."""
        try:
            # Simple condition evaluation
            # This would be expanded for more complex conditions
            if "success == true" in condition:
                return any(r.success for r in results)
            return True
        except Exception:
            return True

    async def _execute_step(
        self, step: Dict[str, Any], context: ExecutionContext
    ) -> ExecutionResult:
        """Execute a single step."""
        start_time = datetime.utcnow()

        try:
            tool_id = step["tool_id"]
            arguments = step["arguments"]
            timeout = step.get("timeout", context.timeout)

            # Execute tool with timeout
            result = await asyncio.wait_for(
                self.tool_discovery.execute_tool(tool_id, arguments), timeout=timeout
            )

            execution_time = (datetime.utcnow() - start_time).total_seconds()

            return ExecutionResult(
                tool_id=tool_id,
                tool_name=step.get("tool_name", "unknown"),
                success=True,
                result=result,
                execution_time=execution_time,
            )

        except asyncio.TimeoutError:
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            return ExecutionResult(
                tool_id=step["tool_id"],
                tool_name=step.get("tool_name", "unknown"),
                success=False,
                error="Execution timeout",
                execution_time=execution_time,
            )
        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            return ExecutionResult(
                tool_id=step["tool_id"],
                tool_name=step.get("tool_name", "unknown"),
                success=False,
                error=str(e),
                execution_time=execution_time,
            )

    async def get_bindings_for_agent(self, agent_id: str) -> List[ToolBinding]:
        """Get all bindings for an agent."""
        return [
            binding
            for binding in self.bindings.values()
            if binding.agent_id == agent_id
        ]

    async def get_binding_statistics(self) -> Dict[str, Any]:
        """Get binding statistics."""
        total_bindings = len(self.bindings)
        active_bindings = len(
            [
                b
                for b in self.bindings.values()
                if b.last_used and (datetime.utcnow() - b.last_used).days < 7
            ]
        )

        return {
            "total_bindings": total_bindings,
            "active_bindings": active_bindings,
            "execution_history_count": len(self.execution_history),
            "average_confidence": (
                sum(b.binding_confidence for b in self.bindings.values())
                / total_bindings
                if total_bindings > 0
                else 0.0
            ),
        }
