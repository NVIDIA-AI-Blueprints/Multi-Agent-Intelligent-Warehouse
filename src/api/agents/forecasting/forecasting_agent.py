"""
MCP-Enabled Forecasting Agent

This agent integrates with the Model Context Protocol (MCP) system to provide
dynamic tool discovery and execution for demand forecasting operations.
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import json
from datetime import datetime

from src.api.services.llm.nim_client import get_nim_client, LLMResponse
from src.retrieval.hybrid_retriever import get_hybrid_retriever, SearchContext
from src.memory.memory_manager import get_memory_manager
from src.api.services.mcp.tool_discovery import (
    ToolDiscoveryService,
    DiscoveredTool,
    ToolCategory,
)
from src.api.services.mcp.base import MCPManager
from src.api.services.reasoning import (
    get_reasoning_engine,
    ReasoningType,
    ReasoningChain,
)
from src.api.utils.log_utils import sanitize_prompt_input
from src.api.services.agent_config import load_agent_config, AgentConfig
from .forecasting_action_tools import get_forecasting_action_tools

logger = logging.getLogger(__name__)


@dataclass
class MCPForecastingQuery:
    """MCP-enabled forecasting query."""

    intent: str
    entities: Dict[str, Any]
    context: Dict[str, Any]
    user_query: str
    mcp_tools: List[str] = None
    tool_execution_plan: List[Dict[str, Any]] = None


@dataclass
class MCPForecastingResponse:
    """MCP-enabled forecasting response."""

    response_type: str
    data: Dict[str, Any]
    natural_language: str
    recommendations: List[str]
    confidence: float
    actions_taken: List[Dict[str, Any]]
    mcp_tools_used: List[str] = None
    tool_execution_results: Dict[str, Any] = None
    reasoning_chain: Optional[ReasoningChain] = None  # Advanced reasoning chain
    reasoning_steps: Optional[List[Dict[str, Any]]] = None  # Individual reasoning steps


class ForecastingAgent:
    """
    MCP-enabled Forecasting Agent.

    This agent integrates with the Model Context Protocol (MCP) system to provide:
    - Dynamic tool discovery and execution for forecasting operations
    - MCP-based tool binding and routing
    - Enhanced tool selection and validation
    - Comprehensive error handling and fallback mechanisms
    """

    def __init__(self):
        self.nim_client = None
        self.hybrid_retriever = None
        self.forecasting_tools = None
        self.mcp_manager = None
        self.tool_discovery = None
        self.reasoning_engine = None
        self.conversation_context = {}
        self.mcp_tools_cache = {}
        self.tool_execution_history = []
        self.config: Optional[AgentConfig] = None  # Agent configuration

    async def initialize(self) -> None:
        """Initialize the agent with required services including MCP."""
        try:
            # Load agent configuration
            self.config = load_agent_config("forecasting")
            logger.info(f"Loaded agent configuration: {self.config.name}")
            
            self.nim_client = await get_nim_client()
            self.hybrid_retriever = await get_hybrid_retriever()
            self.forecasting_tools = await get_forecasting_action_tools()

            # Initialize MCP components
            self.mcp_manager = MCPManager()
            self.tool_discovery = ToolDiscoveryService()

            # Start tool discovery
            await self.tool_discovery.start_discovery()

            # Initialize reasoning engine
            self.reasoning_engine = await get_reasoning_engine()

            # Register MCP sources
            await self._register_mcp_sources()

            logger.info("MCP-enabled Forecasting Agent initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize MCP Forecasting Agent: {e}")
            raise

    async def _register_mcp_sources(self) -> None:
        """Register MCP sources for tool discovery."""
        try:
            # Import and register the forecasting MCP adapter (if it exists)
            try:
                from src.api.services.mcp.adapters.forecasting_adapter import (
                    get_forecasting_adapter,
                )

                forecasting_adapter = await get_forecasting_adapter()
                await self.tool_discovery.register_discovery_source(
                    "forecasting_tools", forecasting_adapter, "mcp_adapter"
                )
            except ImportError:
                logger.info("Forecasting MCP adapter not found, using direct tools")

            logger.info("MCP sources registered successfully")
        except Exception as e:
            logger.error(f"Failed to register MCP sources: {e}")

    async def process_query(
        self,
        query: str,
        session_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
        mcp_results: Optional[Any] = None,
        enable_reasoning: bool = False,
        reasoning_types: Optional[List[str]] = None,
    ) -> MCPForecastingResponse:
        """
        Process a forecasting query with MCP integration.

        Args:
            query: User's forecasting query
            session_id: Session identifier for context
            context: Additional context
            mcp_results: Optional MCP execution results from planner graph

        Returns:
            MCPForecastingResponse with MCP tool execution results
        """
        try:
            # Initialize if needed
            if (
                not self.nim_client
                or not self.hybrid_retriever
                or not self.tool_discovery
            ):
                await self.initialize()

            # Step 1: Advanced Reasoning Analysis (if enabled and query is complex)
            reasoning_chain = None
            if enable_reasoning and self.reasoning_engine and self._is_complex_query(query):
                try:
                    # Convert string reasoning types to ReasoningType enum if provided
                    reasoning_type_enums = None
                    if reasoning_types:
                        reasoning_type_enums = []
                        for rt_str in reasoning_types:
                            try:
                                rt_enum = ReasoningType(rt_str)
                                reasoning_type_enums.append(rt_enum)
                            except ValueError:
                                logger.warning(f"Invalid reasoning type: {rt_str}, skipping")
                    
                    # Determine reasoning types if not provided
                    if reasoning_type_enums is None:
                        reasoning_type_enums = self._determine_reasoning_types(query, context)

                    reasoning_chain = await self.reasoning_engine.process_with_reasoning(
                        query=query,
                        context=context or {},
                        reasoning_types=reasoning_type_enums,
                        session_id=session_id,
                    )
                    logger.info(f"Advanced reasoning completed: {len(reasoning_chain.steps)} steps")
                except Exception as e:
                    logger.warning(f"Advanced reasoning failed, continuing with standard processing: {e}")
            else:
                logger.info("Skipping advanced reasoning for simple query or reasoning disabled")

            # Parse query to extract intent and entities
            parsed_query = await self._parse_query(query, context)

            # Discover available tools
            available_tools = await self._discover_tools(parsed_query)

            # Execute tools based on query intent
            tool_results = await self._execute_forecasting_tools(
                parsed_query, available_tools
            )

            # Generate natural language response (include reasoning chain)
            response = await self._generate_response(
                query, parsed_query, tool_results, context, reasoning_chain
            )

            return response

        except Exception as e:
            logger.error(f"Error processing forecasting query: {e}")
            return MCPForecastingResponse(
                response_type="error",
                data={"error": str(e)},
                natural_language=f"I encountered an error processing your forecasting query: {str(e)}",
                recommendations=[],
                confidence=0.0,
                actions_taken=[],
            )

    async def _parse_query(
        self, query: str, context: Optional[Dict[str, Any]]
    ) -> MCPForecastingQuery:
        """Parse the user query to extract intent and entities."""
        try:
            # Load prompt from configuration
            if self.config is None:
                self.config = load_agent_config("forecasting")
            
            understanding_prompt_template = self.config.persona.understanding_prompt
            system_prompt = self.config.persona.system_prompt
            
            # Format the understanding prompt with actual values
            formatted_prompt = understanding_prompt_template.format(
                query=query,
                context=context or {}
            )
            
            # Use LLM to extract intent and entities
            parse_prompt = [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": formatted_prompt,
                },
            ]

            llm_response = await self.nim_client.generate_response(parse_prompt)
            parsed = json.loads(llm_response.content)

            return MCPForecastingQuery(
                intent=parsed.get("intent", "forecast"),
                entities=parsed.get("entities", {}),
                context=context or {},
                user_query=query,
            )

        except Exception as e:
            logger.warning(f"Failed to parse query with LLM, using simple extraction: {e}")
            # Simple fallback parsing
            query_lower = query.lower()
            entities = {}
            
            # Extract SKU if mentioned
            import re
            sku_match = re.search(r'\b([A-Z]{3}\d{3})\b', query)
            if sku_match:
                entities["sku"] = sku_match.group(1)
            
            # Extract horizon days
            # Use bounded quantifiers to prevent ReDoS in regex pattern
            # Pattern: digits (1-5) + optional whitespace (0-5) + "day" or "days"
            # Days are unlikely to exceed 5 digits (99999 days = ~274 years)
            days_match = re.search(r'(\d{1,5})\s{0,5}days?', query)
            if days_match:
                entities["horizon_days"] = int(days_match.group(1))
            
            # Determine intent
            if "reorder" in query_lower or "recommendation" in query_lower:
                intent = "reorder_recommendation"
            elif "model" in query_lower or "performance" in query_lower:
                intent = "model_performance"
            elif "dashboard" in query_lower or "summary" in query_lower:
                intent = "dashboard"
            elif "business intelligence" in query_lower or "bi" in query_lower:
                intent = "business_intelligence"
            else:
                intent = "forecast"

            return MCPForecastingQuery(
                intent=intent,
                entities=entities,
                context=context or {},
                user_query=query,
            )

    async def _discover_tools(
        self, query: MCPForecastingQuery
    ) -> List[DiscoveredTool]:
        """Discover available forecasting tools."""
        try:
            # Get tools from MCP discovery by category
            discovered_tools = await self.tool_discovery.get_tools_by_category(
                ToolCategory.FORECASTING
            )
            
            # Also search by query keywords
            if query.user_query:
                keyword_tools = await self.tool_discovery.search_tools(query.user_query)
                discovered_tools.extend(keyword_tools)

            # Add direct tools if MCP doesn't have them
            if not discovered_tools:
                discovered_tools = [
                    DiscoveredTool(
                        name="get_forecast",
                        description="Get demand forecast for a specific SKU",
                        category=ToolCategory.FORECASTING,
                        parameters={"sku": "string", "horizon_days": "integer"},
                    ),
                    DiscoveredTool(
                        name="get_batch_forecast",
                        description="Get demand forecasts for multiple SKUs",
                        category=ToolCategory.FORECASTING,
                        parameters={"skus": "list", "horizon_days": "integer"},
                    ),
                    DiscoveredTool(
                        name="get_reorder_recommendations",
                        description="Get automated reorder recommendations",
                        category=ToolCategory.FORECASTING,
                        parameters={},
                    ),
                    DiscoveredTool(
                        name="get_model_performance",
                        description="Get model performance metrics",
                        category=ToolCategory.FORECASTING,
                        parameters={},
                    ),
                    DiscoveredTool(
                        name="get_forecast_dashboard",
                        description="Get comprehensive forecasting dashboard",
                        category=ToolCategory.FORECASTING,
                        parameters={},
                    ),
                ]

            return discovered_tools

        except Exception as e:
            logger.error(f"Failed to discover tools: {e}")
            return []

    async def _execute_forecasting_tools(
        self, query: MCPForecastingQuery, tools: List[DiscoveredTool]
    ) -> Dict[str, Any]:
        """Execute forecasting tools based on query intent."""
        tool_results = {}
        actions_taken = []

        try:
            intent = query.intent
            entities = query.entities

            if intent == "forecast":
                # Single SKU forecast
                sku = entities.get("sku")
                if sku:
                    forecast = await self.forecasting_tools.get_forecast(
                        sku, entities.get("horizon_days", 30)
                    )
                    tool_results["forecast"] = forecast
                    actions_taken.append(
                        {
                            "action": "get_forecast",
                            "sku": sku,
                            "horizon_days": entities.get("horizon_days", 30),
                        }
                    )
                else:
                    # Batch forecast for multiple SKUs or all
                    skus = entities.get("skus", [])
                    if not skus:
                        # Get all SKUs from inventory
                        from src.retrieval.structured.sql_retriever import SQLRetriever
                        sql_retriever = SQLRetriever()
                        sku_results = await sql_retriever.fetch_all(
                            "SELECT DISTINCT sku FROM inventory_items ORDER BY sku LIMIT 10"
                        )
                        skus = [row["sku"] for row in sku_results]

                    forecast = await self.forecasting_tools.get_batch_forecast(
                        skus, entities.get("horizon_days", 30)
                    )
                    tool_results["batch_forecast"] = forecast
                    actions_taken.append(
                        {
                            "action": "get_batch_forecast",
                            "skus": skus,
                            "horizon_days": entities.get("horizon_days", 30),
                        }
                    )

            elif intent == "reorder_recommendation":
                recommendations = await self.forecasting_tools.get_reorder_recommendations()
                tool_results["reorder_recommendations"] = recommendations
                actions_taken.append({"action": "get_reorder_recommendations"})

            elif intent == "model_performance":
                performance = await self.forecasting_tools.get_model_performance()
                tool_results["model_performance"] = performance
                actions_taken.append({"action": "get_model_performance"})

            elif intent == "dashboard":
                dashboard = await self.forecasting_tools.get_forecast_dashboard()
                tool_results["dashboard"] = dashboard
                actions_taken.append({"action": "get_forecast_dashboard"})

            elif intent == "business_intelligence":
                bi = await self.forecasting_tools.get_business_intelligence()
                tool_results["business_intelligence"] = bi
                actions_taken.append({"action": "get_business_intelligence"})

            else:
                # Default: get dashboard
                dashboard = await self.forecasting_tools.get_forecast_dashboard()
                tool_results["dashboard"] = dashboard
                actions_taken.append({"action": "get_forecast_dashboard"})

        except Exception as e:
            logger.error(f"Error executing forecasting tools: {e}")
            tool_results["error"] = str(e)

        return tool_results

    async def _generate_response(
        self,
        original_query: str,
        parsed_query: MCPForecastingQuery,
        tool_results: Dict[str, Any],
        context: Optional[Dict[str, Any]],
        reasoning_chain: Optional[ReasoningChain] = None,
    ) -> MCPForecastingResponse:
        """Generate natural language response from tool results."""
        try:
            # Format tool results for LLM
            results_summary = json.dumps(tool_results, default=str, indent=2)

            # Load response prompt from configuration
            if self.config is None:
                self.config = load_agent_config("forecasting")
            
            response_prompt_template = self.config.persona.response_prompt
            system_prompt = self.config.persona.system_prompt
            
            # Format the response prompt with actual values
            formatted_response_prompt = response_prompt_template.format(
                user_query=sanitize_prompt_input(original_query),
                intent=sanitize_prompt_input(parsed_query.intent),
                entities=parsed_query.entities,
                retrieved_data=results_summary,
                tool_results=results_summary,
                reasoning_analysis="",
                conversation_history=""
            )
            
            response_prompt = [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": formatted_response_prompt,
                },
            ]

            llm_response = await self.nim_client.generate_response(response_prompt)
            natural_language = llm_response.content

            # Extract recommendations
            recommendations = []
            if "reorder_recommendations" in tool_results:
                for rec in tool_results["reorder_recommendations"]:
                    if rec.get("urgency_level") in ["CRITICAL", "HIGH"]:
                        recommendations.append(
                            f"Reorder {rec['sku']}: {rec['recommended_order_quantity']} units ({rec['urgency_level']})"
                        )

            # Calculate confidence based on data availability
            confidence = 0.8 if tool_results and "error" not in tool_results else 0.3

            # Convert reasoning chain to dict for response
            reasoning_steps = None
            if reasoning_chain:
                reasoning_steps = [
                    {
                        "step_id": step.step_id,
                        "step_type": step.step_type,
                        "description": step.description,
                        "reasoning": step.reasoning,
                        "confidence": step.confidence,
                    }
                    for step in reasoning_chain.steps
                ]

            return MCPForecastingResponse(
                response_type=parsed_query.intent,
                data=tool_results,
                natural_language=natural_language,
                recommendations=recommendations,
                confidence=confidence,
                actions_taken=parsed_query.tool_execution_plan or [],
                mcp_tools_used=[tool.name for tool in await self._discover_tools(parsed_query)],
                tool_execution_results=tool_results,
                reasoning_chain=reasoning_chain,
                reasoning_steps=reasoning_steps,
            )

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return MCPForecastingResponse(
                response_type="error",
                data={"error": str(e)},
                natural_language=f"I encountered an error: {str(e)}",
                recommendations=[],
                confidence=0.0,
                actions_taken=[],
                mcp_tools_used=[],
                tool_execution_results={},
                reasoning_chain=None,
                reasoning_steps=None,
            )


    def _is_complex_query(self, query: str) -> bool:
        """Determine if a query is complex enough to require reasoning."""
        query_lower = query.lower()
        complex_keywords = [
            "analyze",
            "compare",
            "relationship",
            "why",
            "how",
            "explain",
            "investigate",
            "evaluate",
            "optimize",
            "improve",
            "what if",
            "scenario",
            "pattern",
            "trend",
            "cause",
            "effect",
            "because",
            "result",
            "consequence",
            "due to",
            "leads to",
            "recommendation",
            "suggestion",
            "strategy",
            "plan",
            "alternative",
            "option",
        ]
        return any(keyword in query_lower for keyword in complex_keywords)
    
    def _determine_reasoning_types(
        self, query: str, context: Optional[Dict[str, Any]]
    ) -> List[ReasoningType]:
        """Determine appropriate reasoning types based on query complexity and context."""
        reasoning_types = [ReasoningType.CHAIN_OF_THOUGHT]  # Always include chain-of-thought
        
        query_lower = query.lower()
        
        # Multi-hop reasoning for complex queries
        if any(
            keyword in query_lower
            for keyword in [
                "analyze",
                "compare",
                "relationship",
                "connection",
                "across",
                "multiple",
            ]
        ):
            reasoning_types.append(ReasoningType.MULTI_HOP)
        
        # Scenario analysis for what-if questions (very important for forecasting)
        if any(
            keyword in query_lower
            for keyword in [
                "what if",
                "scenario",
                "alternative",
                "option",
                "if",
                "when",
                "suppose",
            ]
        ):
            reasoning_types.append(ReasoningType.SCENARIO_ANALYSIS)
        
        # Causal reasoning for cause-effect questions
        if any(
            keyword in query_lower
            for keyword in [
                "why",
                "cause",
                "effect",
                "because",
                "result",
                "consequence",
                "due to",
                "leads to",
            ]
        ):
            reasoning_types.append(ReasoningType.CAUSAL)
        
        # Pattern recognition for learning queries (very important for forecasting)
        if any(
            keyword in query_lower
            for keyword in [
                "pattern",
                "trend",
                "learn",
                "insight",
                "recommendation",
                "optimize",
                "improve",
            ]
        ):
            reasoning_types.append(ReasoningType.PATTERN_RECOGNITION)
        
        # For forecasting queries, always include scenario analysis and pattern recognition
        if any(
            keyword in query_lower
            for keyword in ["forecast", "prediction", "trend", "demand", "sales"]
        ):
            if ReasoningType.SCENARIO_ANALYSIS not in reasoning_types:
                reasoning_types.append(ReasoningType.SCENARIO_ANALYSIS)
            if ReasoningType.PATTERN_RECOGNITION not in reasoning_types:
                reasoning_types.append(ReasoningType.PATTERN_RECOGNITION)
        
        return reasoning_types


# Global instance
_forecasting_agent: Optional[ForecastingAgent] = None


async def get_forecasting_agent() -> ForecastingAgent:
    """Get or create the global forecasting agent instance."""
    global _forecasting_agent
    if _forecasting_agent is None:
        _forecasting_agent = ForecastingAgent()
        await _forecasting_agent.initialize()
    return _forecasting_agent

