"""
Equipment & Asset Operations Agent (EAO) for Warehouse Operations

Mission: Ensure equipment is available, safe, and optimally used for warehouse workflows.
Owns: availability, assignments, telemetry, maintenance requests, compliance links.
Collaborates: with Operations Coordination Agent for task/route planning and equipment allocation,
with Safety & Compliance Agent for pre-op checks, incidents, LOTO.

Provides intelligent equipment and asset management capabilities including:
- Equipment availability and assignment tracking
- Asset utilization and performance monitoring
- Maintenance scheduling and work order management
- Equipment telemetry and status monitoring
- Compliance and safety integration
"""

import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
import json
from datetime import datetime, timedelta
import asyncio

from src.api.services.llm.nim_client import get_nim_client, LLMResponse
from src.retrieval.hybrid_retriever import get_hybrid_retriever, SearchContext
from src.memory.memory_manager import get_memory_manager
from .equipment_asset_tools import get_equipment_asset_tools, EquipmentAssetTools

logger = logging.getLogger(__name__)


@dataclass
class EquipmentQuery:
    """Structured equipment query."""

    intent: str  # "equipment_lookup", "assignment", "utilization", "maintenance", "availability", "telemetry"
    entities: Dict[
        str, Any
    ]  # Extracted entities like asset_id, equipment_type, zone, etc.
    context: Dict[str, Any]  # Additional context
    user_query: str  # Original user query


@dataclass
class EquipmentResponse:
    """Structured equipment response."""

    response_type: str  # "equipment_info", "assignment_status", "utilization_report", "maintenance_plan", "availability_status"
    data: Dict[str, Any]  # Structured data
    natural_language: str  # Natural language response
    recommendations: List[str]  # Actionable recommendations
    confidence: float  # Confidence score (0.0 to 1.0)
    actions_taken: List[Dict[str, Any]]  # Actions performed by the agent


class EquipmentAssetOperationsAgent:
    """
    Equipment & Asset Operations Agent with NVIDIA NIM integration.

    Provides comprehensive equipment and asset management capabilities including:
    - Equipment availability and assignment tracking
    - Asset utilization and performance monitoring
    - Maintenance scheduling and work order management
    - Equipment telemetry and status monitoring
    - Compliance and safety integration
    """

    def __init__(self):
        self.nim_client = None
        self.hybrid_retriever = None
        self.asset_tools = None
        self.conversation_context = {}  # Maintain conversation context

    async def initialize(self) -> None:
        """Initialize the agent with required services."""
        try:
            self.nim_client = await get_nim_client()
            self.hybrid_retriever = await get_hybrid_retriever()
            self.asset_tools = await get_equipment_asset_tools()
            logger.info("Equipment & Asset Operations Agent initialized successfully")
        except Exception as e:
            logger.error(
                f"Failed to initialize Equipment & Asset Operations Agent: {e}"
            )
            raise

    async def process_query(
        self,
        query: str,
        session_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
    ) -> EquipmentResponse:
        """
        Process an equipment/asset operations query.

        Args:
            query: User's equipment/asset query
            session_id: Session identifier for context
            context: Additional context

        Returns:
            EquipmentResponse with structured data, natural language, and recommendations
        """
        try:
            # Initialize if needed
            if not self.nim_client or not self.hybrid_retriever:
                await self.initialize()

            # Update conversation context
            if session_id not in self.conversation_context:
                self.conversation_context[session_id] = {
                    "history": [],
                    "current_focus": None,
                    "last_entities": {},
                }

            # Step 1: Understand intent and extract entities using LLM
            equipment_query = await self._understand_query(query, session_id, context)

            # Step 2: Retrieve relevant data using hybrid retriever
            retrieved_data = await self._retrieve_equipment_data(equipment_query)

            # Step 3: Execute action tools if needed
            actions_taken = await self._execute_action_tools(equipment_query, context)

            # Step 4: Generate response using LLM
            response = await self._generate_equipment_response(
                equipment_query, retrieved_data, session_id, actions_taken
            )

            # Update conversation context
            self.conversation_context[session_id]["history"].append(
                {
                    "query": query,
                    "intent": equipment_query.intent,
                    "entities": equipment_query.entities,
                    "response_type": response.response_type,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            return response

        except Exception as e:
            logger.error(f"Error processing equipment query: {e}")
            return await self._generate_fallback_response(query, session_id, str(e))

    async def _understand_query(
        self, query: str, session_id: str, context: Optional[Dict[str, Any]]
    ) -> EquipmentQuery:
        """Understand the user's equipment query and extract entities."""
        try:
            # Build context for LLM
            conversation_history = self.conversation_context.get(session_id, {}).get(
                "history", []
            )
            context_str = self._build_context_string(conversation_history, context)

            prompt = f"""
            You are an Equipment & Asset Operations Agent. Analyze the user's query and extract relevant information.

            Query: "{query}"
            
            Context: {context_str}
            
            Extract the following information:
            1. Intent: One of [equipment_lookup, assignment, utilization, maintenance, availability, telemetry, release]
            2. Entities: Extract asset_id (e.g., FL-01, AMR-001, CHG-05), equipment_type (forklift, amr, agv, scanner, charger, etc.), zone, assignee, status, etc.
            3. Context: Any additional relevant context
            
            Respond with a JSON object containing:
            {{
                "intent": "equipment_lookup",
                "entities": {{
                    "asset_id": "FL-01",
                    "equipment_type": "forklift",
                    "zone": "Zone A",
                    "status": "available"
                }},
                "context": {{
                    "urgency": "normal",
                    "priority": "medium"
                }}
            }}
            """

            response = await self.nim_client.generate_response(
                [{"role": "user", "content": prompt}], temperature=0.1
            )

            # Parse JSON response
            try:
                parsed_response = json.loads(response.content.strip())
                return EquipmentQuery(
                    intent=parsed_response.get("intent", "equipment_lookup"),
                    entities=parsed_response.get("entities", {}),
                    context=parsed_response.get("context", {}),
                    user_query=query,
                )
            except json.JSONDecodeError:
                logger.warning("Failed to parse LLM response as JSON, using fallback")
                return EquipmentQuery(
                    intent="equipment_lookup", entities={}, context={}, user_query=query
                )

        except Exception as e:
            logger.error(f"Error understanding query: {e}")
            return EquipmentQuery(
                intent="equipment_lookup", entities={}, context={}, user_query=query
            )

    async def _retrieve_equipment_data(
        self, equipment_query: EquipmentQuery
    ) -> Dict[str, Any]:
        """Retrieve relevant equipment data using hybrid retriever."""
        try:
            # Build search context
            search_context = SearchContext(
                query=equipment_query.user_query,
                filters={
                    "asset_id": equipment_query.entities.get("asset_id"),
                    "equipment_type": equipment_query.entities.get("equipment_type"),
                    "zone": equipment_query.entities.get("zone"),
                    "status": equipment_query.entities.get("status"),
                },
                limit=10,
            )

            # Perform hybrid search
            search_results = await self.hybrid_retriever.search(search_context)

            return {
                "search_results": search_results,
                "query_filters": search_context.filters,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Data retrieval failed: {e}")
            return {"error": str(e)}

    async def _execute_action_tools(
        self, equipment_query: EquipmentQuery, context: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Execute action tools based on query intent and entities."""
        actions_taken = []

        try:
            if not self.asset_tools:
                return actions_taken

            # Extract entities for action execution
            asset_id = equipment_query.entities.get("asset_id")
            equipment_type = equipment_query.entities.get("equipment_type")
            zone = equipment_query.entities.get("zone")
            assignee = equipment_query.entities.get("assignee")

            # If no asset_id in entities, try to extract from query text
            if not asset_id and equipment_query.user_query:
                import re

                # Look for patterns like FL-01, AMR-001, CHG-05, etc.
                asset_match = re.search(
                    r"[A-Z]{2,3}-\d+", equipment_query.user_query.upper()
                )
                if asset_match:
                    asset_id = asset_match.group()
                    logger.info(f"Extracted asset_id from query: {asset_id}")

            # Execute actions based on intent
            if equipment_query.intent == "equipment_lookup":
                # Get equipment status
                equipment_status = await self.asset_tools.get_equipment_status(
                    asset_id=asset_id,
                    equipment_type=equipment_type,
                    zone=zone,
                    status=equipment_query.entities.get("status"),
                )
                actions_taken.append(
                    {
                        "action": "get_equipment_status",
                        "asset_id": asset_id,
                        "result": equipment_status,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif equipment_query.intent == "assignment" and asset_id and assignee:
                # Assign equipment
                assignment_result = await self.asset_tools.assign_equipment(
                    asset_id=asset_id,
                    assignee=assignee,
                    assignment_type=equipment_query.entities.get(
                        "assignment_type", "task"
                    ),
                    task_id=equipment_query.entities.get("task_id"),
                    duration_hours=equipment_query.entities.get("duration_hours"),
                    notes=equipment_query.entities.get("notes"),
                )
                actions_taken.append(
                    {
                        "action": "assign_equipment",
                        "asset_id": asset_id,
                        "result": assignment_result,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif equipment_query.intent == "utilization" and asset_id:
                # Get equipment telemetry
                telemetry_data = await self.asset_tools.get_equipment_telemetry(
                    asset_id=asset_id,
                    metric=equipment_query.entities.get("metric"),
                    hours_back=equipment_query.entities.get("hours_back", 24),
                )
                actions_taken.append(
                    {
                        "action": "get_equipment_telemetry",
                        "asset_id": asset_id,
                        "result": telemetry_data,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif equipment_query.intent == "maintenance" and asset_id:
                # Schedule maintenance
                maintenance_result = await self.asset_tools.schedule_maintenance(
                    asset_id=asset_id,
                    maintenance_type=equipment_query.entities.get(
                        "maintenance_type", "preventive"
                    ),
                    description=equipment_query.entities.get(
                        "description", "Scheduled maintenance"
                    ),
                    scheduled_by=equipment_query.entities.get("scheduled_by", "system"),
                    scheduled_for=equipment_query.entities.get(
                        "scheduled_for", datetime.now()
                    ),
                    estimated_duration_minutes=equipment_query.entities.get(
                        "duration_minutes", 60
                    ),
                    priority=equipment_query.entities.get("priority", "medium"),
                )
                actions_taken.append(
                    {
                        "action": "schedule_maintenance",
                        "asset_id": asset_id,
                        "result": maintenance_result,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif equipment_query.intent == "release" and asset_id:
                # Release equipment
                release_result = await self.asset_tools.release_equipment(
                    asset_id=asset_id,
                    released_by=equipment_query.entities.get("released_by", "system"),
                    notes=equipment_query.entities.get("notes"),
                )
                actions_taken.append(
                    {
                        "action": "release_equipment",
                        "asset_id": asset_id,
                        "result": release_result,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif equipment_query.intent == "telemetry" and asset_id:
                # Get equipment telemetry
                telemetry_data = await self.asset_tools.get_equipment_telemetry(
                    asset_id=asset_id,
                    metric=equipment_query.entities.get("metric"),
                    hours_back=equipment_query.entities.get("hours_back", 24),
                )
                actions_taken.append(
                    {
                        "action": "get_equipment_telemetry",
                        "asset_id": asset_id,
                        "result": telemetry_data,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

        except Exception as e:
            logger.error(f"Error executing action tools: {e}")
            actions_taken.append(
                {
                    "action": "error",
                    "result": {"error": str(e)},
                    "timestamp": datetime.now().isoformat(),
                }
            )

        return actions_taken

    async def _generate_equipment_response(
        self,
        equipment_query: EquipmentQuery,
        retrieved_data: Dict[str, Any],
        session_id: str,
        actions_taken: List[Dict[str, Any]],
    ) -> EquipmentResponse:
        """Generate a comprehensive equipment response using LLM."""
        try:
            # Build context for response generation
            context_str = self._build_retrieved_context(retrieved_data, actions_taken)

            prompt = f"""
            You are an Equipment & Asset Operations Agent. Generate a comprehensive response based on the query and retrieved data.

            Query: "{equipment_query.user_query}"
            Intent: {equipment_query.intent}
            Entities: {equipment_query.entities}
            
            Retrieved Data:
            {context_str}
            
            Actions Taken:
            {json.dumps(actions_taken, indent=2, default=str)}
            
            Generate a response that includes:
            1. Direct answer to the user's question
            2. Relevant equipment information
            3. Actionable recommendations
            4. Next steps if applicable
            
            Be specific about asset IDs, equipment types, zones, and status information.
            Provide clear, actionable recommendations for equipment management.
            """

            response = await self.nim_client.generate_response(
                [{"role": "user", "content": prompt}], temperature=0.3
            )

            # Determine response type based on intent
            response_type_map = {
                "equipment_lookup": "equipment_info",
                "assignment": "assignment_status",
                "utilization": "utilization_report",
                "maintenance": "maintenance_plan",
                "availability": "availability_status",
                "release": "release_status",
                "telemetry": "telemetry_data",
            }

            response_type = response_type_map.get(
                equipment_query.intent, "equipment_info"
            )

            # Extract recommendations from response
            recommendations = self._extract_recommendations(response.content)

            return EquipmentResponse(
                response_type=response_type,
                data=retrieved_data,
                natural_language=response.content,
                recommendations=recommendations,
                confidence=0.85,  # High confidence for equipment queries
                actions_taken=actions_taken,
            )

        except Exception as e:
            logger.error(f"Error generating equipment response: {e}")
            return await self._generate_fallback_response(
                equipment_query.user_query, session_id, str(e)
            )

    def _build_context_string(
        self, conversation_history: List[Dict], context: Optional[Dict[str, Any]]
    ) -> str:
        """Build context string from conversation history and additional context."""
        context_parts = []

        if conversation_history:
            recent_history = conversation_history[-3:]  # Last 3 exchanges
            history_str = "\n".join(
                [
                    f"Q: {h['query']}\nA: {h.get('response_type', 'equipment_info')}"
                    for h in recent_history
                ]
            )
            context_parts.append(f"Recent conversation:\n{history_str}")

        if context:
            context_parts.append(f"Additional context: {json.dumps(context, indent=2)}")

        return "\n\n".join(context_parts) if context_parts else "No additional context"

    def _build_retrieved_context(
        self, retrieved_data: Dict[str, Any], actions_taken: List[Dict[str, Any]]
    ) -> str:
        """Build context string from retrieved data and actions."""
        context_parts = []

        if "search_results" in retrieved_data:
            context_parts.append(
                f"Search results: {json.dumps(retrieved_data['search_results'], indent=2, default=str)}"
            )

        if "query_filters" in retrieved_data:
            context_parts.append(
                f"Query filters: {json.dumps(retrieved_data['query_filters'], indent=2)}"
            )

        if actions_taken:
            context_parts.append(
                f"Actions taken: {json.dumps(actions_taken, indent=2, default=str)}"
            )

        return "\n\n".join(context_parts) if context_parts else "No retrieved data"

    def _extract_recommendations(self, response_text: str) -> List[str]:
        """Extract actionable recommendations from response text."""
        recommendations = []

        # Simple extraction of bullet points or numbered lists
        lines = response_text.split("\n")
        for line in lines:
            line = line.strip()
            if (
                line.startswith(("•", "-", "*", "1.", "2.", "3."))
                or "recommend" in line.lower()
            ):
                # Clean up the line
                clean_line = line.lstrip("•-*123456789. ").strip()
                if clean_line and len(clean_line) > 10:  # Filter out very short items
                    recommendations.append(clean_line)

        return recommendations[:5]  # Limit to 5 recommendations

    async def _generate_fallback_response(
        self, query: str, session_id: str, error: str
    ) -> EquipmentResponse:
        """Generate a fallback response when normal processing fails."""
        return EquipmentResponse(
            response_type="error",
            data={"error": error},
            natural_language=f"I encountered an error while processing your equipment query: '{query}'. Please try rephrasing your question or contact support if the issue persists.",
            recommendations=[
                "Try rephrasing your question",
                "Check if the asset ID is correct",
                "Contact support if the issue persists",
            ],
            confidence=0.0,
            actions_taken=[],
        )

    async def clear_conversation_context(self, session_id: str) -> None:
        """Clear conversation context for a session."""
        if session_id in self.conversation_context:
            del self.conversation_context[session_id]


# Global instance
_equipment_agent: Optional[EquipmentAssetOperationsAgent] = None


async def get_equipment_agent() -> EquipmentAssetOperationsAgent:
    """Get the global equipment agent instance."""
    global _equipment_agent
    if _equipment_agent is None:
        _equipment_agent = EquipmentAssetOperationsAgent()
        await _equipment_agent.initialize()
    return _equipment_agent
