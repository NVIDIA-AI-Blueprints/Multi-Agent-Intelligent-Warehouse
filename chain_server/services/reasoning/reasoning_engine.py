"""
Advanced Reasoning Engine for Warehouse Operational Assistant

Provides comprehensive reasoning capabilities including:
- Chain-of-Thought Reasoning
- Multi-Hop Reasoning
- Scenario Analysis
- Causal Reasoning
- Pattern Recognition
"""

import logging
import json
import asyncio
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import re
from collections import defaultdict, Counter

from chain_server.services.llm.nim_client import get_nim_client, LLMResponse
from inventory_retriever.hybrid_retriever import get_hybrid_retriever
from inventory_retriever.structured.sql_retriever import get_sql_retriever

logger = logging.getLogger(__name__)


class ReasoningType(Enum):
    """Types of reasoning capabilities."""

    CHAIN_OF_THOUGHT = "chain_of_thought"
    MULTI_HOP = "multi_hop"
    SCENARIO_ANALYSIS = "scenario_analysis"
    CAUSAL = "causal"
    PATTERN_RECOGNITION = "pattern_recognition"


@dataclass
class ReasoningStep:
    """Individual step in reasoning process."""

    step_id: str
    step_type: str
    description: str
    input_data: Dict[str, Any]
    reasoning: str
    output_data: Dict[str, Any]
    confidence: float
    timestamp: datetime
    dependencies: List[str] = None


@dataclass
class ReasoningChain:
    """Complete reasoning chain for a query."""

    chain_id: str
    query: str
    reasoning_type: ReasoningType
    steps: List[ReasoningStep]
    final_conclusion: str
    overall_confidence: float
    created_at: datetime
    execution_time: float


@dataclass
class PatternInsight:
    """Pattern recognition insight."""

    pattern_id: str
    pattern_type: str
    description: str
    frequency: int
    confidence: float
    examples: List[str]
    recommendations: List[str]
    created_at: datetime


@dataclass
class CausalRelationship:
    """Causal relationship between events."""

    cause: str
    effect: str
    strength: float
    evidence: List[str]
    confidence: float
    context: Dict[str, Any]


class AdvancedReasoningEngine:
    """
    Advanced reasoning engine with multiple reasoning capabilities.

    Provides:
    - Chain-of-Thought Reasoning
    - Multi-Hop Reasoning
    - Scenario Analysis
    - Causal Reasoning
    - Pattern Recognition
    """

    def __init__(self):
        self.nim_client = None
        self.hybrid_retriever = None
        self.sql_retriever = None
        self.pattern_store = defaultdict(list)
        self.reasoning_chains = {}
        self.causal_relationships = []
        self.query_patterns = Counter()
        self.user_behavior_patterns = defaultdict(dict)

    async def initialize(self) -> None:
        """Initialize the reasoning engine with required services."""
        try:
            self.nim_client = await get_nim_client()
            self.hybrid_retriever = await get_hybrid_retriever()
            self.sql_retriever = await get_sql_retriever()
            logger.info("Advanced Reasoning Engine initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Advanced Reasoning Engine: {e}")
            raise

    async def process_with_reasoning(
        self,
        query: str,
        context: Dict[str, Any],
        reasoning_types: List[ReasoningType] = None,
        session_id: str = "default",
    ) -> ReasoningChain:
        """
        Process query with advanced reasoning capabilities.

        Args:
            query: User query
            context: Additional context
            reasoning_types: Types of reasoning to apply
            session_id: Session identifier

        Returns:
            ReasoningChain with complete reasoning process
        """
        try:
            if not self.nim_client:
                await self.initialize()

            # Default to all reasoning types if none specified
            if not reasoning_types:
                reasoning_types = list(ReasoningType)

            chain_id = f"REASON_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            start_time = datetime.now()

            # Initialize reasoning chain
            reasoning_chain = ReasoningChain(
                chain_id=chain_id,
                query=query,
                reasoning_type=(
                    reasoning_types[0]
                    if len(reasoning_types) == 1
                    else ReasoningType.MULTI_HOP
                ),
                steps=[],
                final_conclusion="",
                overall_confidence=0.0,
                created_at=start_time,
                execution_time=0.0,
            )

            # Step 1: Chain-of-Thought Analysis
            if ReasoningType.CHAIN_OF_THOUGHT in reasoning_types:
                cot_steps = await self._chain_of_thought_reasoning(
                    query, context, session_id
                )
                reasoning_chain.steps.extend(cot_steps)

            # Step 2: Multi-Hop Reasoning
            if ReasoningType.MULTI_HOP in reasoning_types:
                multi_hop_steps = await self._multi_hop_reasoning(
                    query, context, session_id
                )
                reasoning_chain.steps.extend(multi_hop_steps)

            # Step 3: Scenario Analysis
            if ReasoningType.SCENARIO_ANALYSIS in reasoning_types:
                scenario_steps = await self._scenario_analysis(
                    query, context, session_id
                )
                reasoning_chain.steps.extend(scenario_steps)

            # Step 4: Causal Reasoning
            if ReasoningType.CAUSAL in reasoning_types:
                causal_steps = await self._causal_reasoning(query, context, session_id)
                reasoning_chain.steps.extend(causal_steps)

            # Step 5: Pattern Recognition
            if ReasoningType.PATTERN_RECOGNITION in reasoning_types:
                pattern_steps = await self._pattern_recognition(
                    query, context, session_id
                )
                reasoning_chain.steps.extend(pattern_steps)

            # Generate final conclusion
            final_conclusion = await self._generate_final_conclusion(
                reasoning_chain, context
            )
            reasoning_chain.final_conclusion = final_conclusion

            # Calculate overall confidence
            reasoning_chain.overall_confidence = self._calculate_overall_confidence(
                reasoning_chain.steps
            )

            # Calculate execution time
            reasoning_chain.execution_time = (
                datetime.now() - start_time
            ).total_seconds()

            # Store reasoning chain
            self.reasoning_chains[chain_id] = reasoning_chain

            # Update pattern recognition
            await self._update_pattern_recognition(query, reasoning_chain, session_id)

            return reasoning_chain

        except Exception as e:
            logger.error(f"Reasoning processing failed: {e}")
            raise

    async def _chain_of_thought_reasoning(
        self, query: str, context: Dict[str, Any], session_id: str
    ) -> List[ReasoningStep]:
        """Perform chain-of-thought reasoning."""
        try:
            steps = []

            # Step 1: Query Analysis
            analysis_prompt = f"""
            Analyze this warehouse operations query step by step:
            
            Query: "{query}"
            Context: {json.dumps(context, default=str)}
            
            Break down your analysis into clear reasoning steps:
            1. What is the user asking for?
            2. What information do I need to answer this?
            3. What are the key entities and relationships?
            4. What are the potential approaches to solve this?
            5. What are the constraints and considerations?
            
            Respond in JSON format with detailed reasoning for each step.
            """

            response = await self.nim_client.generate_response(
                [
                    {
                        "role": "system",
                        "content": "You are an expert warehouse operations analyst. Break down queries into clear reasoning steps.",
                    },
                    {"role": "user", "content": analysis_prompt},
                ],
                temperature=0.1,
            )

            # Parse reasoning steps
            try:
                reasoning_data = json.loads(response.content)
                for i, step_data in enumerate(reasoning_data.get("steps", [])):
                    step = ReasoningStep(
                        step_id=f"COT_{i+1}",
                        step_type="query_analysis",
                        description=step_data.get("description", ""),
                        input_data={"query": query, "context": context},
                        reasoning=step_data.get("reasoning", ""),
                        output_data=step_data.get("output", {}),
                        confidence=step_data.get("confidence", 0.8),
                        timestamp=datetime.now(),
                        dependencies=[],
                    )
                    steps.append(step)
            except json.JSONDecodeError:
                # Fallback to simple reasoning
                step = ReasoningStep(
                    step_id="COT_1",
                    step_type="query_analysis",
                    description="Query analysis",
                    input_data={"query": query, "context": context},
                    reasoning=response.content,
                    output_data={},
                    confidence=0.7,
                    timestamp=datetime.now(),
                    dependencies=[],
                )
                steps.append(step)

            return steps

        except Exception as e:
            logger.error(f"Chain-of-thought reasoning failed: {e}")
            return []

    async def _multi_hop_reasoning(
        self, query: str, context: Dict[str, Any], session_id: str
    ) -> List[ReasoningStep]:
        """Perform multi-hop reasoning across different data sources."""
        try:
            steps = []

            # Step 1: Identify information needs
            info_needs_prompt = f"""
            For this warehouse query, identify what information I need from different sources:
            
            Query: "{query}"
            
            Consider these data sources:
            - Equipment status and telemetry
            - Workforce and task data
            - Safety incidents and procedures
            - Inventory and stock levels
            - Operations metrics and KPIs
            
            List the specific information needed from each source and how they connect.
            """

            response = await self.nim_client.generate_response(
                [
                    {
                        "role": "system",
                        "content": "You are a data integration expert. Identify information needs across multiple sources.",
                    },
                    {"role": "user", "content": info_needs_prompt},
                ],
                temperature=0.1,
            )

            step1 = ReasoningStep(
                step_id="MH_1",
                step_type="information_identification",
                description="Identify information needs across sources",
                input_data={"query": query},
                reasoning=response.content,
                output_data={"information_needs": response.content},
                confidence=0.8,
                timestamp=datetime.now(),
                dependencies=[],
            )
            steps.append(step1)

            # Step 2: Gather information from multiple sources
            if self.hybrid_retriever:
                # Query multiple data sources
                equipment_data = await self._query_equipment_data(query)
                workforce_data = await self._query_workforce_data(query)
                safety_data = await self._query_safety_data(query)
                inventory_data = await self._query_inventory_data(query)

                step2 = ReasoningStep(
                    step_id="MH_2",
                    step_type="multi_source_data_gathering",
                    description="Gather data from multiple sources",
                    input_data={"query": query},
                    reasoning="Retrieved data from equipment, workforce, safety, and inventory sources",
                    output_data={
                        "equipment": equipment_data,
                        "workforce": workforce_data,
                        "safety": safety_data,
                        "inventory": inventory_data,
                    },
                    confidence=0.9,
                    timestamp=datetime.now(),
                    dependencies=["MH_1"],
                )
                steps.append(step2)

            # Step 3: Connect information across sources
            connection_prompt = f"""
            Connect the information from different sources to answer the query:
            
            Query: "{query}"
            
            Equipment Data: {json.dumps(equipment_data, default=str)}
            Workforce Data: {json.dumps(workforce_data, default=str)}
            Safety Data: {json.dumps(safety_data, default=str)}
            Inventory Data: {json.dumps(inventory_data, default=str)}
            
            How do these data sources relate to each other and the query?
            What patterns or relationships do you see?
            """

            response = await self.nim_client.generate_response(
                [
                    {
                        "role": "system",
                        "content": "You are a data analyst. Connect information across multiple sources.",
                    },
                    {"role": "user", "content": connection_prompt},
                ],
                temperature=0.1,
            )

            step3 = ReasoningStep(
                step_id="MH_3",
                step_type="information_connection",
                description="Connect information across sources",
                input_data={
                    "query": query,
                    "sources": ["equipment", "workforce", "safety", "inventory"],
                },
                reasoning=response.content,
                output_data={"connections": response.content},
                confidence=0.8,
                timestamp=datetime.now(),
                dependencies=["MH_2"],
            )
            steps.append(step3)

            return steps

        except Exception as e:
            logger.error(f"Multi-hop reasoning failed: {e}")
            return []

    async def _scenario_analysis(
        self, query: str, context: Dict[str, Any], session_id: str
    ) -> List[ReasoningStep]:
        """Perform scenario analysis and what-if reasoning."""
        try:
            steps = []

            # Step 1: Identify scenarios
            scenario_prompt = f"""
            Analyze this warehouse query for different scenarios:
            
            Query: "{query}"
            Context: {json.dumps(context, default=str)}
            
            Consider these scenarios:
            1. Best case scenario
            2. Worst case scenario
            3. Most likely scenario
            4. Alternative approaches
            5. Risk factors and mitigation
            
            For each scenario, analyze:
            - What would happen?
            - What are the implications?
            - What actions would be needed?
            - What are the risks and benefits?
            """

            response = await self.nim_client.generate_response(
                [
                    {
                        "role": "system",
                        "content": "You are a scenario planning expert. Analyze different scenarios for warehouse operations.",
                    },
                    {"role": "user", "content": scenario_prompt},
                ],
                temperature=0.2,
            )

            step1 = ReasoningStep(
                step_id="SA_1",
                step_type="scenario_identification",
                description="Identify different scenarios",
                input_data={"query": query, "context": context},
                reasoning=response.content,
                output_data={"scenarios": response.content},
                confidence=0.8,
                timestamp=datetime.now(),
                dependencies=[],
            )
            steps.append(step1)

            # Step 2: Analyze each scenario
            scenarios = [
                "best_case",
                "worst_case",
                "most_likely",
                "alternatives",
                "risks",
            ]
            for i, scenario in enumerate(scenarios):
                analysis_prompt = f"""
                Analyze the {scenario} scenario for this query:
                
                Query: "{query}"
                Scenario: {scenario}
                
                Provide detailed analysis including:
                - What would happen in this scenario?
                - What are the key factors?
                - What actions would be required?
                - What are the expected outcomes?
                - What are the success metrics?
                """

                response = await self.nim_client.generate_response(
                    [
                        {
                            "role": "system",
                            "content": f"You are a {scenario} scenario analyst.",
                        },
                        {"role": "user", "content": analysis_prompt},
                    ],
                    temperature=0.2,
                )

                step = ReasoningStep(
                    step_id=f"SA_{i+2}",
                    step_type="scenario_analysis",
                    description=f"Analyze {scenario} scenario",
                    input_data={"query": query, "scenario": scenario},
                    reasoning=response.content,
                    output_data={"scenario_analysis": response.content},
                    confidence=0.8,
                    timestamp=datetime.now(),
                    dependencies=["SA_1"],
                )
                steps.append(step)

            return steps

        except Exception as e:
            logger.error(f"Scenario analysis failed: {e}")
            return []

    async def _causal_reasoning(
        self, query: str, context: Dict[str, Any], session_id: str
    ) -> List[ReasoningStep]:
        """Perform causal reasoning and cause-and-effect analysis."""
        try:
            steps = []

            # Step 1: Identify potential causes and effects
            causal_prompt = f"""
            Analyze the causal relationships in this warehouse query:
            
            Query: "{query}"
            Context: {json.dumps(context, default=str)}
            
            Identify:
            1. What are the potential causes of the situation described?
            2. What are the potential effects or consequences?
            3. What are the intermediate factors?
            4. What are the confounding variables?
            5. What evidence supports each causal relationship?
            
            Consider both direct and indirect causal relationships.
            """

            response = await self.nim_client.generate_response(
                [
                    {
                        "role": "system",
                        "content": "You are a causal analysis expert. Identify cause-and-effect relationships.",
                    },
                    {"role": "user", "content": causal_prompt},
                ],
                temperature=0.1,
            )

            step1 = ReasoningStep(
                step_id="CR_1",
                step_type="causal_identification",
                description="Identify causes and effects",
                input_data={"query": query, "context": context},
                reasoning=response.content,
                output_data={"causal_analysis": response.content},
                confidence=0.8,
                timestamp=datetime.now(),
                dependencies=[],
            )
            steps.append(step1)

            # Step 2: Analyze causal strength and evidence
            evidence_prompt = f"""
            Evaluate the strength of causal relationships for this query:
            
            Query: "{query}"
            Causal Analysis: {response.content}
            
            For each causal relationship, assess:
            1. Strength of the relationship (weak, moderate, strong)
            2. Quality of evidence
            3. Temporal relationship
            4. Alternative explanations
            5. Confidence level
            """

            response = await self.nim_client.generate_response(
                [
                    {
                        "role": "system",
                        "content": "You are a causal inference expert. Evaluate causal relationship strength.",
                    },
                    {"role": "user", "content": evidence_prompt},
                ],
                temperature=0.1,
            )

            step2 = ReasoningStep(
                step_id="CR_2",
                step_type="causal_evaluation",
                description="Evaluate causal relationships",
                input_data={"query": query, "causal_analysis": step1.output_data},
                reasoning=response.content,
                output_data={"causal_evaluation": response.content},
                confidence=0.8,
                timestamp=datetime.now(),
                dependencies=["CR_1"],
            )
            steps.append(step2)

            return steps

        except Exception as e:
            logger.error(f"Causal reasoning failed: {e}")
            return []

    async def _pattern_recognition(
        self, query: str, context: Dict[str, Any], session_id: str
    ) -> List[ReasoningStep]:
        """Perform pattern recognition and learning from query patterns."""
        try:
            steps = []

            # Step 1: Analyze current query patterns
            pattern_prompt = f"""
            Analyze patterns in this warehouse query:
            
            Query: "{query}"
            Session ID: {session_id}
            Context: {json.dumps(context, default=str)}
            
            Identify:
            1. Query type and category
            2. Key entities and relationships
            3. User intent and goals
            4. Information needs
            5. Expected response format
            
            Compare with similar queries if available.
            """

            response = await self.nim_client.generate_response(
                [
                    {
                        "role": "system",
                        "content": "You are a pattern recognition expert. Analyze query patterns and user behavior.",
                    },
                    {"role": "user", "content": pattern_prompt},
                ],
                temperature=0.1,
            )

            step1 = ReasoningStep(
                step_id="PR_1",
                step_type="pattern_analysis",
                description="Analyze current query patterns",
                input_data={
                    "query": query,
                    "session_id": session_id,
                    "context": context,
                },
                reasoning=response.content,
                output_data={"pattern_analysis": response.content},
                confidence=0.8,
                timestamp=datetime.now(),
                dependencies=[],
            )
            steps.append(step1)

            # Step 2: Learn from historical patterns
            historical_patterns = await self._get_historical_patterns(session_id)

            step2 = ReasoningStep(
                step_id="PR_2",
                step_type="historical_pattern_learning",
                description="Learn from historical patterns",
                input_data={"query": query, "session_id": session_id},
                reasoning=f"Analyzed {len(historical_patterns)} historical patterns",
                output_data={"historical_patterns": historical_patterns},
                confidence=0.7,
                timestamp=datetime.now(),
                dependencies=["PR_1"],
            )
            steps.append(step2)

            # Step 3: Generate insights and recommendations
            insights_prompt = f"""
            Generate insights and recommendations based on pattern analysis:
            
            Current Query: "{query}"
            Pattern Analysis: {response.content}
            Historical Patterns: {json.dumps(historical_patterns, default=str)}
            
            Provide:
            1. Key insights about user behavior
            2. Recommendations for improving responses
            3. Predicted follow-up questions
            4. Optimization suggestions
            5. Learning opportunities
            """

            response = await self.nim_client.generate_response(
                [
                    {
                        "role": "system",
                        "content": "You are a behavioral analyst. Generate insights from pattern analysis.",
                    },
                    {"role": "user", "content": insights_prompt},
                ],
                temperature=0.2,
            )

            step3 = ReasoningStep(
                step_id="PR_3",
                step_type="insight_generation",
                description="Generate insights and recommendations",
                input_data={
                    "query": query,
                    "patterns": step1.output_data,
                    "historical": step2.output_data,
                },
                reasoning=response.content,
                output_data={"insights": response.content},
                confidence=0.8,
                timestamp=datetime.now(),
                dependencies=["PR_1", "PR_2"],
            )
            steps.append(step3)

            return steps

        except Exception as e:
            logger.error(f"Pattern recognition failed: {e}")
            return []

    async def _generate_final_conclusion(
        self, reasoning_chain: ReasoningChain, context: Dict[str, Any]
    ) -> str:
        """Generate final conclusion from reasoning chain."""
        try:
            # Summarize all reasoning steps
            steps_summary = []
            for step in reasoning_chain.steps:
                steps_summary.append(
                    f"Step {step.step_id}: {step.description}\n{step.reasoning}"
                )

            conclusion_prompt = f"""
            Based on the comprehensive reasoning analysis, provide a final conclusion:
            
            Original Query: "{reasoning_chain.query}"
            
            Reasoning Steps:
            {chr(10).join(steps_summary)}
            
            Generate a clear, actionable conclusion that:
            1. Directly answers the user's query
            2. Incorporates insights from all reasoning steps
            3. Provides specific recommendations
            4. Indicates confidence level
            5. Suggests next steps if applicable
            """

            response = await self.nim_client.generate_response(
                [
                    {
                        "role": "system",
                        "content": "You are an expert analyst. Provide clear, actionable conclusions.",
                    },
                    {"role": "user", "content": conclusion_prompt},
                ],
                temperature=0.1,
            )

            return response.content

        except Exception as e:
            logger.error(f"Final conclusion generation failed: {e}")
            return "Based on the analysis, I can provide insights about your query, though some reasoning steps encountered issues."

    def _calculate_overall_confidence(self, steps: List[ReasoningStep]) -> float:
        """Calculate overall confidence from reasoning steps."""
        if not steps:
            return 0.0

        # Weighted average of step confidences
        total_confidence = sum(step.confidence for step in steps)
        return total_confidence / len(steps)

    async def _update_pattern_recognition(
        self, query: str, reasoning_chain: ReasoningChain, session_id: str
    ) -> None:
        """Update pattern recognition with new query data."""
        try:
            # Extract query patterns
            query_lower = query.lower()
            words = re.findall(r"\b\w+\b", query_lower)

            # Update word frequency
            for word in words:
                self.query_patterns[word] += 1

            # Update session patterns
            if session_id not in self.user_behavior_patterns:
                self.user_behavior_patterns[session_id] = {
                    "query_count": 0,
                    "reasoning_types": Counter(),
                    "query_categories": Counter(),
                    "response_times": [],
                }

            session_data = self.user_behavior_patterns[session_id]
            session_data["query_count"] += 1
            session_data["reasoning_types"][reasoning_chain.reasoning_type.value] += 1
            session_data["response_times"].append(reasoning_chain.execution_time)

            # Store reasoning chain for pattern analysis
            self.pattern_store[session_id].append(reasoning_chain)

        except Exception as e:
            logger.error(f"Pattern recognition update failed: {e}")

    async def _get_historical_patterns(self, session_id: str) -> List[Dict[str, Any]]:
        """Get historical patterns for a session."""
        try:
            patterns = []
            if session_id in self.pattern_store:
                for chain in self.pattern_store[session_id][-10:]:  # Last 10 queries
                    patterns.append(
                        {
                            "query": chain.query,
                            "reasoning_type": chain.reasoning_type.value,
                            "confidence": chain.overall_confidence,
                            "execution_time": chain.execution_time,
                            "created_at": chain.created_at.isoformat(),
                        }
                    )
            return patterns
        except Exception as e:
            logger.error(f"Historical patterns retrieval failed: {e}")
            return []

    # Helper methods for multi-hop reasoning
    async def _query_equipment_data(self, query: str) -> Dict[str, Any]:
        """Query equipment data."""
        try:
            if self.sql_retriever:
                await self.sql_retriever.initialize()
                equipment_query = """
                SELECT equipment_id, status, battery_level, location, last_maintenance
                FROM equipment_status 
                ORDER BY last_updated DESC 
                LIMIT 10
                """
                results = await self.sql_retriever.fetch_all(equipment_query)
                return {"equipment_status": results}
            return {}
        except Exception as e:
            logger.error(f"Equipment data query failed: {e}")
            return {}

    async def _query_workforce_data(self, query: str) -> Dict[str, Any]:
        """Query workforce data."""
        try:
            if self.sql_retriever:
                await self.sql_retriever.initialize()
                workforce_query = """
                SELECT worker_id, name, role, status, current_task, shift
                FROM workforce_status 
                ORDER BY last_updated DESC 
                LIMIT 10
                """
                results = await self.sql_retriever.fetch_all(workforce_query)
                return {"workforce_status": results}
            return {}
        except Exception as e:
            logger.error(f"Workforce data query failed: {e}")
            return {}

    async def _query_safety_data(self, query: str) -> Dict[str, Any]:
        """Query safety data."""
        try:
            if self.sql_retriever:
                await self.sql_retriever.initialize()
                safety_query = """
                SELECT incident_id, severity, description, location, occurred_at
                FROM safety_incidents 
                ORDER BY occurred_at DESC 
                LIMIT 10
                """
                results = await self.sql_retriever.fetch_all(safety_query)
                return {"safety_incidents": results}
            return {}
        except Exception as e:
            logger.error(f"Safety data query failed: {e}")
            return {}

    async def _query_inventory_data(self, query: str) -> Dict[str, Any]:
        """Query inventory data."""
        try:
            if self.sql_retriever:
                await self.sql_retriever.initialize()
                inventory_query = """
                SELECT sku, description, quantity_on_hand, location, last_count
                FROM inventory_items 
                ORDER BY last_updated DESC 
                LIMIT 10
                """
                results = await self.sql_retriever.fetch_all(inventory_query)
                return {"inventory_items": results}
            return {}
        except Exception as e:
            logger.error(f"Inventory data query failed: {e}")
            return {}

    async def get_reasoning_insights(self, session_id: str) -> Dict[str, Any]:
        """Get reasoning insights for a session."""
        try:
            insights = {
                "total_queries": len(self.pattern_store.get(session_id, [])),
                "reasoning_types": dict(
                    self.user_behavior_patterns.get(session_id, {}).get(
                        "reasoning_types", Counter()
                    )
                ),
                "average_confidence": 0.0,
                "average_execution_time": 0.0,
                "common_patterns": dict(self.query_patterns.most_common(10)),
                "recommendations": [],
            }

            if session_id in self.pattern_store:
                chains = self.pattern_store[session_id]
                if chains:
                    insights["average_confidence"] = sum(
                        chain.overall_confidence for chain in chains
                    ) / len(chains)
                    insights["average_execution_time"] = sum(
                        chain.execution_time for chain in chains
                    ) / len(chains)

            return insights
        except Exception as e:
            logger.error(f"Reasoning insights retrieval failed: {e}")
            return {}


# Global reasoning engine instance
_reasoning_engine: Optional[AdvancedReasoningEngine] = None


async def get_reasoning_engine() -> AdvancedReasoningEngine:
    """Get or create the global reasoning engine instance."""
    global _reasoning_engine
    if _reasoning_engine is None:
        _reasoning_engine = AdvancedReasoningEngine()
        await _reasoning_engine.initialize()
    return _reasoning_engine
