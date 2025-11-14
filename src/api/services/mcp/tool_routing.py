"""
MCP-based Routing and Tool Selection Logic

This module provides intelligent routing and tool selection capabilities for the MCP system,
enabling optimal tool selection based on query characteristics, performance metrics, and context.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Tuple, Union, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json
import math
from collections import defaultdict

from .tool_discovery import ToolDiscoveryService, DiscoveredTool, ToolCategory
from .tool_binding import ToolBindingService, BindingStrategy, ExecutionMode

logger = logging.getLogger(__name__)


class RoutingStrategy(Enum):
    """Tool routing strategies."""

    PERFORMANCE_OPTIMIZED = "performance_optimized"
    ACCURACY_OPTIMIZED = "accuracy_optimized"
    BALANCED = "balanced"
    COST_OPTIMIZED = "cost_optimized"
    LATENCY_OPTIMIZED = "latency_optimized"


class QueryComplexity(Enum):
    """Query complexity levels."""

    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"
    VERY_COMPLEX = "very_complex"


@dataclass
class RoutingContext:
    """Context for tool routing."""

    query: str
    intent: str
    entities: Dict[str, Any]
    user_context: Dict[str, Any]
    session_id: str
    agent_id: str
    priority: int = 1  # 1-5, 5 being highest
    complexity: QueryComplexity = QueryComplexity.MODERATE
    required_capabilities: List[str] = field(default_factory=list)
    performance_requirements: Dict[str, Any] = field(default_factory=dict)
    cost_constraints: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolScore:
    """Score for a tool in routing context."""

    tool_id: str
    tool_name: str
    overall_score: float
    performance_score: float
    accuracy_score: float
    cost_score: float
    latency_score: float
    capability_match_score: float
    context_relevance_score: float
    confidence: float
    reasoning: str


@dataclass
class RoutingDecision:
    """Routing decision result."""

    selected_tools: List[DiscoveredTool]
    tool_scores: List[ToolScore]
    routing_strategy: RoutingStrategy
    execution_mode: ExecutionMode
    confidence: float
    reasoning: str
    fallback_tools: List[DiscoveredTool] = field(default_factory=list)
    estimated_execution_time: float = 0.0
    estimated_cost: float = 0.0


class ToolRoutingService:
    """
    Service for MCP-based tool routing and selection.

    This service provides:
    - Intelligent tool selection based on query characteristics
    - Performance-optimized routing strategies
    - Context-aware tool matching
    - Multi-criteria optimization for tool selection
    - Fallback and redundancy mechanisms
    """

    def __init__(
        self, tool_discovery: ToolDiscoveryService, tool_binding: ToolBindingService
    ):
        self.tool_discovery = tool_discovery
        self.tool_binding = tool_binding
        self.routing_history: List[Dict[str, Any]] = []
        self.performance_tracking: Dict[str, Dict[str, Any]] = {}
        self.complexity_analyzer = QueryComplexityAnalyzer()
        self.capability_matcher = CapabilityMatcher()
        self.context_analyzer = ContextAnalyzer()

        # Initialize routing strategies after methods are defined
        self._setup_routing_strategies()

    async def route_tools(
        self,
        context: RoutingContext,
        strategy: RoutingStrategy = RoutingStrategy.BALANCED,
        max_tools: int = 5,
    ) -> RoutingDecision:
        """
        Route tools based on context and strategy.

        Args:
            context: Routing context
            strategy: Routing strategy to use
            max_tools: Maximum number of tools to select

        Returns:
            Routing decision with selected tools and reasoning
        """
        try:
            # Analyze query complexity
            context.complexity = await self.complexity_analyzer.analyze_complexity(
                context.query
            )

            # Discover candidate tools
            candidate_tools = await self._discover_candidate_tools(context)

            # Score tools based on strategy
            tool_scores = await self._score_tools(candidate_tools, context, strategy)

            # Select tools based on scores
            selected_tools, fallback_tools = self._select_tools(tool_scores, max_tools)

            # Determine execution mode
            execution_mode = self._determine_execution_mode(selected_tools, context)

            # Calculate estimates
            estimated_time = self._estimate_execution_time(selected_tools)
            estimated_cost = self._estimate_cost(selected_tools)

            # Create routing decision
            decision = RoutingDecision(
                selected_tools=selected_tools,
                tool_scores=tool_scores,
                routing_strategy=strategy,
                execution_mode=execution_mode,
                confidence=self._calculate_confidence(tool_scores),
                reasoning=self._generate_reasoning(tool_scores, strategy),
                fallback_tools=fallback_tools,
                estimated_execution_time=estimated_time,
                estimated_cost=estimated_cost,
            )

            # Record routing decision
            self._record_routing_decision(decision, context)

            logger.info(
                f"Routed {len(selected_tools)} tools using {strategy.value} strategy"
            )
            return decision

        except Exception as e:
            logger.error(f"Error routing tools: {e}")
            return RoutingDecision(
                selected_tools=[],
                tool_scores=[],
                routing_strategy=strategy,
                execution_mode=ExecutionMode.SEQUENTIAL,
                confidence=0.0,
                reasoning=f"Error in routing: {str(e)}",
            )

    async def _discover_candidate_tools(
        self, context: RoutingContext
    ) -> List[DiscoveredTool]:
        """Discover candidate tools for routing."""
        try:
            candidate_tools = []

            # Search by intent
            intent_tools = await self.tool_discovery.search_tools(context.intent)
            candidate_tools.extend(intent_tools)

            # Search by entities
            for entity_type, entity_value in context.entities.items():
                entity_tools = await self.tool_discovery.search_tools(
                    f"{entity_type} {entity_value}"
                )
                candidate_tools.extend(entity_tools)

            # Search by query keywords
            query_tools = await self.tool_discovery.search_tools(context.query)
            candidate_tools.extend(query_tools)

            # Search by required capabilities
            for capability in context.required_capabilities:
                capability_tools = await self.tool_discovery.search_tools(capability)
                candidate_tools.extend(capability_tools)

            # Remove duplicates
            unique_tools = {}
            for tool in candidate_tools:
                if tool.tool_id not in unique_tools:
                    unique_tools[tool.tool_id] = tool

            return list(unique_tools.values())

        except Exception as e:
            logger.error(f"Error discovering candidate tools: {e}")
            return []

    async def _score_tools(
        self,
        tools: List[DiscoveredTool],
        context: RoutingContext,
        strategy: RoutingStrategy,
    ) -> List[ToolScore]:
        """Score tools based on strategy and context."""
        try:
            # Use the appropriate routing strategy
            if strategy in self.routing_strategies:
                return await self.routing_strategies[strategy](tools, context)
            else:
                # Fallback to balanced strategy
                return await self._balanced_routing(tools, context)

        except Exception as e:
            logger.error(f"Error scoring tools: {e}")
            return []

    def _calculate_performance_score(self, tool: DiscoveredTool) -> float:
        """Calculate performance score for a tool."""
        # Base score on success rate and response time
        success_rate = tool.success_rate
        response_time = tool.average_response_time

        # Normalize response time (assume 10 seconds is max acceptable)
        normalized_response_time = max(0, 1.0 - (response_time / 10.0))

        # Weighted combination
        performance_score = (success_rate * 0.7) + (normalized_response_time * 0.3)

        return min(1.0, max(0.0, performance_score))

    def _calculate_accuracy_score(self, tool: DiscoveredTool) -> float:
        """Calculate accuracy score for a tool."""
        # Base score on success rate and usage count
        success_rate = tool.success_rate
        usage_count = tool.usage_count

        # Normalize usage count (assume 100 is high usage)
        normalized_usage = min(1.0, usage_count / 100.0)

        # Weighted combination
        accuracy_score = (success_rate * 0.8) + (normalized_usage * 0.2)

        return min(1.0, max(0.0, accuracy_score))

    def _calculate_cost_score(self, tool: DiscoveredTool) -> float:
        """Calculate cost score for a tool."""
        # For now, assume all tools have similar cost
        # This would be expanded based on actual cost data
        return 1.0

    def _calculate_latency_score(self, tool: DiscoveredTool) -> float:
        """Calculate latency score for a tool."""
        response_time = tool.average_response_time

        # Normalize response time (assume 5 seconds is max acceptable)
        latency_score = max(0, 1.0 - (response_time / 5.0))

        return min(1.0, max(0.0, latency_score))

    def _calculate_overall_score(
        self,
        performance_score: float,
        accuracy_score: float,
        cost_score: float,
        latency_score: float,
        capability_score: float,
        context_score: float,
        strategy: RoutingStrategy,
    ) -> float:
        """Calculate overall score based on strategy."""
        if strategy == RoutingStrategy.PERFORMANCE_OPTIMIZED:
            return (
                (performance_score * 0.4)
                + (accuracy_score * 0.3)
                + (latency_score * 0.3)
            )
        elif strategy == RoutingStrategy.ACCURACY_OPTIMIZED:
            return (
                (accuracy_score * 0.5)
                + (capability_score * 0.3)
                + (context_score * 0.2)
            )
        elif strategy == RoutingStrategy.BALANCED:
            return (
                (performance_score * 0.25)
                + (accuracy_score * 0.25)
                + (capability_score * 0.25)
                + (context_score * 0.25)
            )
        elif strategy == RoutingStrategy.COST_OPTIMIZED:
            return (
                (cost_score * 0.4) + (performance_score * 0.3) + (accuracy_score * 0.3)
            )
        elif strategy == RoutingStrategy.LATENCY_OPTIMIZED:
            return (
                (latency_score * 0.5)
                + (performance_score * 0.3)
                + (accuracy_score * 0.2)
            )
        else:
            return (
                performance_score + accuracy_score + capability_score + context_score
            ) / 4.0

    def _calculate_tool_confidence(
        self, tool: DiscoveredTool, context: RoutingContext
    ) -> float:
        """Calculate confidence in tool selection."""
        # Base confidence on tool metrics
        base_confidence = tool.success_rate * 0.6 + (tool.usage_count / 100.0) * 0.4

        # Adjust based on context match
        context_match = 0.8  # This would be calculated based on context analysis

        # Adjust based on priority
        priority_factor = context.priority / 5.0

        confidence = base_confidence * context_match * priority_factor

        return min(1.0, max(0.0, confidence))

    def _generate_tool_reasoning(
        self,
        tool: DiscoveredTool,
        performance_score: float,
        accuracy_score: float,
        cost_score: float,
        latency_score: float,
        capability_score: float,
        context_score: float,
        overall_score: float,
    ) -> str:
        """Generate reasoning for tool selection."""
        reasons = []

        if performance_score > 0.8:
            reasons.append("high performance")
        if accuracy_score > 0.8:
            reasons.append("high accuracy")
        if capability_score > 0.8:
            reasons.append("good capability match")
        if context_score > 0.8:
            reasons.append("high context relevance")
        if tool.usage_count > 50:
            reasons.append("frequently used")

        if not reasons:
            reasons.append("moderate suitability")

        return f"Selected due to: {', '.join(reasons)} (score: {overall_score:.2f})"

    def _select_tools(
        self, tool_scores: List[ToolScore], max_tools: int
    ) -> Tuple[List[DiscoveredTool], List[DiscoveredTool]]:
        """Select tools based on scores."""
        selected_tools = []
        fallback_tools = []

        # Select top tools
        for score in tool_scores[:max_tools]:
            tool = self.tool_discovery.discovered_tools.get(score.tool_id)
            if tool:
                selected_tools.append(tool)

        # Select fallback tools
        for score in tool_scores[max_tools : max_tools + 3]:
            tool = self.tool_discovery.discovered_tools.get(score.tool_id)
            if tool:
                fallback_tools.append(tool)

        return selected_tools, fallback_tools

    def _determine_execution_mode(
        self, tools: List[DiscoveredTool], context: RoutingContext
    ) -> ExecutionMode:
        """Determine execution mode based on tools and context."""
        if len(tools) <= 1:
            return ExecutionMode.SEQUENTIAL

        if context.complexity == QueryComplexity.SIMPLE:
            return ExecutionMode.PARALLEL
        elif context.complexity == QueryComplexity.MODERATE:
            return ExecutionMode.SEQUENTIAL
        elif context.complexity == QueryComplexity.COMPLEX:
            return ExecutionMode.PIPELINE
        else:
            return ExecutionMode.CONDITIONAL

    def _estimate_execution_time(self, tools: List[DiscoveredTool]) -> float:
        """Estimate total execution time."""
        total_time = 0.0
        for tool in tools:
            total_time += tool.average_response_time
        return total_time

    def _estimate_cost(self, tools: List[DiscoveredTool]) -> float:
        """Estimate total cost."""
        # For now, assume fixed cost per tool
        return len(tools) * 0.1

    def _calculate_confidence(self, tool_scores: List[ToolScore]) -> float:
        """Calculate overall confidence in routing decision."""
        if not tool_scores:
            return 0.0

        # Average confidence of selected tools
        avg_confidence = sum(score.confidence for score in tool_scores) / len(
            tool_scores
        )

        # Adjust based on score distribution
        score_variance = self._calculate_score_variance(tool_scores)
        variance_factor = max(0.5, 1.0 - score_variance)

        return avg_confidence * variance_factor

    def _calculate_score_variance(self, tool_scores: List[ToolScore]) -> float:
        """Calculate variance in tool scores."""
        if len(tool_scores) <= 1:
            return 0.0

        scores = [s.overall_score for s in tool_scores]
        mean_score = sum(scores) / len(scores)
        variance = sum((s - mean_score) ** 2 for s in scores) / len(scores)

        return variance

    def _generate_reasoning(
        self, tool_scores: List[ToolScore], strategy: RoutingStrategy
    ) -> str:
        """Generate reasoning for routing decision."""
        if not tool_scores:
            return "No suitable tools found"

        top_tool = tool_scores[0]
        strategy_name = strategy.value.replace("_", " ").title()

        return f"Selected {len(tool_scores)} tools using {strategy_name} strategy. Top tool: {top_tool.tool_name} (score: {top_tool.overall_score:.2f})"

    def _record_routing_decision(
        self, decision: RoutingDecision, context: RoutingContext
    ) -> None:
        """Record routing decision for analysis."""
        self.routing_history.append(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "context": context,
                "decision": decision,
                "strategy": decision.routing_strategy.value,
            }
        )

        # Keep only last 1000 decisions
        if len(self.routing_history) > 1000:
            self.routing_history = self.routing_history[-1000:]

    async def get_routing_statistics(self) -> Dict[str, Any]:
        """Get routing statistics."""
        if not self.routing_history:
            return {"total_decisions": 0}

        # Calculate statistics
        total_decisions = len(self.routing_history)
        avg_confidence = (
            sum(d["decision"].confidence for d in self.routing_history)
            / total_decisions
        )
        avg_tools_selected = (
            sum(len(d["decision"].selected_tools) for d in self.routing_history)
            / total_decisions
        )

        # Strategy usage
        strategy_usage = defaultdict(int)
        for decision in self.routing_history:
            strategy_usage[decision["strategy"]] += 1

        return {
            "total_decisions": total_decisions,
            "average_confidence": avg_confidence,
            "average_tools_selected": avg_tools_selected,
            "strategy_usage": dict(strategy_usage),
        }


class QueryComplexityAnalyzer:
    """Analyzes query complexity for routing decisions."""

    async def analyze_complexity(self, query: str) -> QueryComplexity:
        """Analyze query complexity."""
        # Simple heuristics for complexity analysis
        query_lower = query.lower()

        # Count complexity indicators
        complexity_indicators = 0

        # Multiple entities
        if len(query.split()) > 10:
            complexity_indicators += 1

        # Complex operations
        complex_ops = ["analyze", "compare", "evaluate", "optimize", "calculate"]
        if any(op in query_lower for op in complex_ops):
            complexity_indicators += 1

        # Multiple intents
        intent_indicators = ["and", "or", "also", "additionally", "furthermore"]
        if any(indicator in query_lower for indicator in intent_indicators):
            complexity_indicators += 1

        # Conditional logic
        conditional_indicators = ["if", "when", "unless", "provided that"]
        if any(indicator in query_lower for indicator in conditional_indicators):
            complexity_indicators += 1

        # Determine complexity level
        if complexity_indicators == 0:
            return QueryComplexity.SIMPLE
        elif complexity_indicators == 1:
            return QueryComplexity.MODERATE
        elif complexity_indicators == 2:
            return QueryComplexity.COMPLEX
        else:
            return QueryComplexity.VERY_COMPLEX


class CapabilityMatcher:
    """Matches tool capabilities to requirements."""

    async def match_capabilities(
        self, tool: DiscoveredTool, context: RoutingContext
    ) -> float:
        """Match tool capabilities to context requirements."""
        if not context.required_capabilities:
            return 0.8  # Default score if no requirements

        matches = 0
        for capability in context.required_capabilities:
            if capability.lower() in tool.description.lower():
                matches += 1
            elif capability.lower() in tool.name.lower():
                matches += 1
            elif any(capability.lower() in cap.lower() for cap in tool.capabilities):
                matches += 1

        return matches / len(context.required_capabilities)


class ContextAnalyzer:
    """Analyzes context relevance for tool selection."""

    async def analyze_context_relevance(
        self, tool: DiscoveredTool, context: RoutingContext
    ) -> float:
        """Analyze context relevance of a tool."""
        relevance_score = 0.0

        # Intent relevance
        if context.intent.lower() in tool.description.lower():
            relevance_score += 0.3

        # Entity relevance
        for entity_type, entity_value in context.entities.items():
            if entity_value.lower() in tool.description.lower():
                relevance_score += 0.2

        # Query relevance
        query_words = context.query.lower().split()
        tool_words = tool.description.lower().split()
        common_words = set(query_words) & set(tool_words)
        if common_words:
            relevance_score += 0.3 * (len(common_words) / len(query_words))

        # Category relevance
        if tool.category.value in context.user_context.get("preferred_categories", []):
            relevance_score += 0.2

        return min(1.0, relevance_score)

    async def _performance_optimized_routing(
        self, tools: List[DiscoveredTool], context: RoutingContext
    ) -> List[ToolScore]:
        """Performance-optimized routing strategy."""
        scores = []
        for tool in tools:
            performance_score = self._calculate_performance_score(tool)
            accuracy_score = self._calculate_accuracy_score(tool) * 0.3  # Lower weight
            cost_score = self._calculate_cost_score(tool) * 0.2  # Lower weight
            latency_score = self._calculate_latency_score(tool) * 0.1  # Lower weight

            overall_score = (
                performance_score * 0.7 + accuracy_score + cost_score + latency_score
            )
            confidence = self._calculate_tool_confidence(tool, context)
            reasoning = (
                f"Performance-optimized: {tool.name} (perf: {performance_score:.2f})"
            )

            scores.append(
                ToolScore(
                    tool_id=tool.tool_id,
                    tool_name=tool.name,
                    overall_score=overall_score,
                    performance_score=performance_score,
                    accuracy_score=accuracy_score,
                    cost_score=cost_score,
                    latency_score=latency_score,
                    capability_match_score=0.0,  # Not used in strategy-based routing
                    context_relevance_score=0.0,  # Not used in strategy-based routing
                    confidence=confidence,
                    reasoning=reasoning,
                )
            )

        return sorted(scores, key=lambda x: x.overall_score, reverse=True)

    async def _accuracy_optimized_routing(
        self, tools: List[DiscoveredTool], context: RoutingContext
    ) -> List[ToolScore]:
        """Accuracy-optimized routing strategy."""
        scores = []
        for tool in tools:
            performance_score = (
                self._calculate_performance_score(tool) * 0.2
            )  # Lower weight
            accuracy_score = self._calculate_accuracy_score(tool)
            cost_score = self._calculate_cost_score(tool) * 0.1  # Lower weight
            latency_score = self._calculate_latency_score(tool) * 0.1  # Lower weight

            overall_score = (
                performance_score + accuracy_score * 0.7 + cost_score + latency_score
            )
            confidence = self._calculate_tool_confidence(tool, context)
            reasoning = f"Accuracy-optimized: {tool.name} (acc: {accuracy_score:.2f})"

            scores.append(
                ToolScore(
                    tool_id=tool.tool_id,
                    tool_name=tool.name,
                    overall_score=overall_score,
                    performance_score=performance_score,
                    accuracy_score=accuracy_score,
                    cost_score=cost_score,
                    latency_score=latency_score,
                    capability_match_score=0.0,  # Not used in strategy-based routing
                    context_relevance_score=0.0,  # Not used in strategy-based routing
                    confidence=confidence,
                    reasoning=reasoning,
                )
            )

        return sorted(scores, key=lambda x: x.overall_score, reverse=True)

    async def _balanced_routing(
        self, tools: List[DiscoveredTool], context: RoutingContext
    ) -> List[ToolScore]:
        """Balanced routing strategy."""
        scores = []
        for tool in tools:
            performance_score = self._calculate_performance_score(tool)
            accuracy_score = self._calculate_accuracy_score(tool)
            cost_score = self._calculate_cost_score(tool)
            latency_score = self._calculate_latency_score(tool)

            overall_score = (
                performance_score + accuracy_score + cost_score + latency_score
            ) / 4
            confidence = self._calculate_tool_confidence(tool, context)
            reasoning = f"Balanced: {tool.name} (overall: {overall_score:.2f})"

            scores.append(
                ToolScore(
                    tool_id=tool.tool_id,
                    tool_name=tool.name,
                    overall_score=overall_score,
                    performance_score=performance_score,
                    accuracy_score=accuracy_score,
                    cost_score=cost_score,
                    latency_score=latency_score,
                    capability_match_score=0.0,  # Not used in strategy-based routing
                    context_relevance_score=0.0,  # Not used in strategy-based routing
                    confidence=confidence,
                    reasoning=reasoning,
                )
            )

        return sorted(scores, key=lambda x: x.overall_score, reverse=True)

    async def _cost_optimized_routing(
        self, tools: List[DiscoveredTool], context: RoutingContext
    ) -> List[ToolScore]:
        """Cost-optimized routing strategy."""
        scores = []
        for tool in tools:
            performance_score = (
                self._calculate_performance_score(tool) * 0.1
            )  # Lower weight
            accuracy_score = self._calculate_accuracy_score(tool) * 0.2  # Lower weight
            cost_score = self._calculate_cost_score(tool)
            latency_score = self._calculate_latency_score(tool) * 0.1  # Lower weight

            overall_score = (
                performance_score + accuracy_score + cost_score * 0.7 + latency_score
            )
            confidence = self._calculate_tool_confidence(tool, context)
            reasoning = f"Cost-optimized: {tool.name} (cost: {cost_score:.2f})"

            scores.append(
                ToolScore(
                    tool_id=tool.tool_id,
                    tool_name=tool.name,
                    overall_score=overall_score,
                    performance_score=performance_score,
                    accuracy_score=accuracy_score,
                    cost_score=cost_score,
                    latency_score=latency_score,
                    capability_match_score=0.0,  # Not used in strategy-based routing
                    context_relevance_score=0.0,  # Not used in strategy-based routing
                    confidence=confidence,
                    reasoning=reasoning,
                )
            )

        return sorted(scores, key=lambda x: x.overall_score, reverse=True)

    async def _latency_optimized_routing(
        self, tools: List[DiscoveredTool], context: RoutingContext
    ) -> List[ToolScore]:
        """Latency-optimized routing strategy."""
        scores = []
        for tool in tools:
            performance_score = (
                self._calculate_performance_score(tool) * 0.1
            )  # Lower weight
            accuracy_score = self._calculate_accuracy_score(tool) * 0.2  # Lower weight
            cost_score = self._calculate_cost_score(tool) * 0.1  # Lower weight
            latency_score = self._calculate_latency_score(tool)

            overall_score = (
                performance_score + accuracy_score + cost_score + latency_score * 0.7
            )
            confidence = self._calculate_tool_confidence(tool, context)
            reasoning = f"Latency-optimized: {tool.name} (latency: {latency_score:.2f})"

            scores.append(
                ToolScore(
                    tool_id=tool.tool_id,
                    tool_name=tool.name,
                    overall_score=overall_score,
                    performance_score=performance_score,
                    accuracy_score=accuracy_score,
                    cost_score=cost_score,
                    latency_score=latency_score,
                    capability_match_score=0.0,  # Not used in strategy-based routing
                    context_relevance_score=0.0,  # Not used in strategy-based routing
                    confidence=confidence,
                    reasoning=reasoning,
                )
            )

        return sorted(scores, key=lambda x: x.overall_score, reverse=True)

    def _setup_routing_strategies(self):
        """Setup routing strategies after methods are defined."""
        self.routing_strategies: Dict[RoutingStrategy, Callable] = {
            RoutingStrategy.PERFORMANCE_OPTIMIZED: self._performance_optimized_routing,
            RoutingStrategy.ACCURACY_OPTIMIZED: self._accuracy_optimized_routing,
            RoutingStrategy.BALANCED: self._balanced_routing,
            RoutingStrategy.COST_OPTIMIZED: self._cost_optimized_routing,
            RoutingStrategy.LATENCY_OPTIMIZED: self._latency_optimized_routing,
        }
