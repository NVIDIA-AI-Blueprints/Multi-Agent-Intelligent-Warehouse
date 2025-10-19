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

from chain_server.services.llm.nim_client import get_nim_client, LLMResponse
from inventory_retriever.hybrid_retriever import get_hybrid_retriever, SearchContext
from inventory_retriever.structured.inventory_queries import InventoryItem
from memory_retriever.memory_manager import get_memory_manager
from .equipment_asset_tools import get_equipment_asset_tools, EquipmentAssetTools

logger = logging.getLogger(__name__)


@dataclass
class EquipmentQuery:
    """Structured equipment query."""

    intent: str  # "equipment_lookup", "assignment", "utilization", "maintenance", "availability", "telemetry"
    entities: Dict[str, Any]  # Extracted entities like equipment_id, location, etc.
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
    Equipment & Asset Operations Agent (EAO) with NVIDIA NIM integration.

    Mission: Ensure equipment is available, safe, and optimally used for warehouse workflows.
    Owns: availability, assignments, telemetry, maintenance requests, compliance links.

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
        Process equipment and asset-related queries with full intelligence.

        Args:
            query: User's equipment query (e.g., "assign a forklift to lane B", "charger status for Truck-07")
            session_id: Session identifier for context
            context: Additional context

        Returns:
            EquipmentResponse with structured data and natural language
        """
        try:
            # Initialize if needed
            if not self.nim_client or not self.hybrid_retriever:
                await self.initialize()

            # Get memory manager for context
            memory_manager = await get_memory_manager()

            # Get context from memory manager
            memory_context = await memory_manager.get_context_for_query(
                session_id=session_id,
                user_id=(
                    context.get("user_id", "default_user")
                    if context
                    else "default_user"
                ),
                query=query,
            )

            # Step 1: Understand intent and extract entities using LLM
            equipment_query = await self._understand_query(query, session_id, context)

            # Step 2: Retrieve relevant data using hybrid retriever
            retrieved_data = await self._retrieve_data(equipment_query)

            # Step 3: Execute action tools if needed
            actions_taken = await self._execute_action_tools(equipment_query, context)

            # Step 4: Generate intelligent response using LLM
            response = await self._generate_response(
                equipment_query,
                retrieved_data,
                session_id,
                memory_context,
                actions_taken,
            )

            # Step 5: Store conversation in memory
            await memory_manager.store_conversation_turn(
                session_id=session_id,
                user_id=(
                    context.get("user_id", "default_user")
                    if context
                    else "default_user"
                ),
                user_query=query,
                agent_response=response.natural_language,
                intent=equipment_query.intent,
                entities=equipment_query.entities,
                metadata={
                    "response_type": response.response_type,
                    "confidence": response.confidence,
                    "structured_data": response.data,
                },
            )

            return response

        except Exception as e:
            logger.error(f"Failed to process inventory query: {e}")
            return EquipmentResponse(
                response_type="error",
                data={"error": str(e)},
                natural_language=f"I encountered an error processing your inventory query: {str(e)}",
                recommendations=[],
                confidence=0.0,
                actions_taken=[],
            )

    async def _understand_query(
        self, query: str, session_id: str, context: Optional[Dict[str, Any]]
    ) -> EquipmentQuery:
        """Use LLM to understand query intent and extract entities."""
        try:
            # Build context-aware prompt
            conversation_history = self.conversation_context.get(session_id, {}).get(
                "history", []
            )
            context_str = self._build_context_string(conversation_history, context)

            prompt = f"""
You are an inventory intelligence agent for warehouse operations. Analyze the user query and extract structured information.

User Query: "{query}"

Previous Context: {context_str}

Extract the following information:
1. Intent: One of ["equipment_lookup", "atp_lookup", "assignment", "utilization", "maintenance", "availability", "telemetry", "charger_status", "pm_schedule", "loto_request", "general"]
2. Entities: Extract equipment_id, location, assignment, maintenance_type, utilization_period, charger_id, etc.
3. Context: Any additional relevant context

Respond in JSON format:
{{
    "intent": "equipment_lookup",
    "entities": {{
        "equipment_id": "Forklift-001",
        "location": "Lane B",
        "assignment": "operator123"
    }},
    "context": {{
        "time_period": "last_week",
        "urgency": "high"
    }}
}}
"""

            messages = [
                {
                    "role": "system",
                    "content": "You are an expert inventory analyst. Respond ONLY with valid JSON, no markdown formatting or additional text.",
                },
                {"role": "user", "content": prompt},
            ]

            response = await self.nim_client.generate_response(
                messages, temperature=0.1
            )

            # Parse LLM response
            try:
                parsed_response = json.loads(response.content)
                return EquipmentQuery(
                    intent=parsed_response.get("intent", "general"),
                    entities=parsed_response.get("entities", {}),
                    context=parsed_response.get("context", {}),
                    user_query=query,
                )
            except json.JSONDecodeError:
                # Fallback to simple intent detection
                return self._fallback_intent_detection(query)

        except Exception as e:
            logger.error(f"Query understanding failed: {e}")
            return self._fallback_intent_detection(query)

    def _fallback_intent_detection(self, query: str) -> EquipmentQuery:
        """Fallback intent detection using keyword matching."""
        query_lower = query.lower()

        if any(
            word in query_lower
            for word in ["assign", "assignment", "allocate", "assign"]
        ):
            intent = "assignment"
        elif any(
            word in query_lower
            for word in ["utilization", "usage", "utilize", "performance"]
        ):
            intent = "utilization"
        elif any(
            word in query_lower
            for word in ["maintenance", "pm", "preventive", "repair", "service"]
        ):
            intent = "maintenance"
        elif any(
            word in query_lower
            for word in ["availability", "available", "status", "ready"]
        ):
            intent = "availability"
        elif any(
            word in query_lower
            for word in ["telemetry", "data", "monitoring", "sensors"]
        ):
            intent = "telemetry"
        elif any(
            word in query_lower for word in ["charger", "charging", "battery", "power"]
        ):
            intent = "charger_status"
        elif any(
            word in query_lower for word in ["loto", "lockout", "tagout", "lock out"]
        ):
            intent = "loto_request"
        elif any(
            word in query_lower
            for word in ["atp", "available to promise", "available_to_promise"]
        ):
            intent = "atp_lookup"
        elif any(
            word in query_lower
            for word in [
                "equipment",
                "forklift",
                "conveyor",
                "scanner",
                "amr",
                "agv",
                "sku",
                "stock",
                "inventory",
                "quantity",
                "available",
            ]
        ):
            intent = "equipment_lookup"
        elif any(
            word in query_lower for word in ["location", "where", "aisle", "zone"]
        ):
            intent = "equipment_lookup"
        else:
            intent = "general"

        return EquipmentQuery(intent=intent, entities={}, context={}, user_query=query)

    async def _retrieve_data(self, equipment_query: EquipmentQuery) -> Dict[str, Any]:
        """Retrieve relevant data using hybrid retriever."""
        try:
            # Create search context
            search_context = SearchContext(
                query=equipment_query.user_query,
                search_type="equipment",
                filters=equipment_query.entities,
                limit=20,
            )

            # Perform hybrid search
            search_results = await self.hybrid_retriever.search(search_context)

            # Get inventory summary for context
            inventory_summary = await self.hybrid_retriever.get_inventory_summary()

            return {
                "search_results": search_results,
                "inventory_summary": inventory_summary,
                "query_entities": equipment_query.entities,
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

            elif equipment_query.intent == "stock_lookup" and sku:
                # Check stock levels
                stock_info = await self.action_tools.check_stock(
                    sku=sku,
                    site=equipment_query.entities.get("site"),
                    locations=equipment_query.entities.get("locations"),
                )
                actions_taken.append(
                    {
                        "action": "check_stock",
                        "sku": sku,
                        "result": asdict(stock_info),
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif equipment_query.intent == "atp_lookup" and sku:
                # Check Available to Promise (ATP) - more sophisticated than basic stock lookup
                stock_info = await self.action_tools.check_stock(
                    sku=sku,
                    site=equipment_query.entities.get("site"),
                    locations=equipment_query.entities.get("locations"),
                )

                # Calculate ATP: Current stock - reserved quantities + incoming orders
                # For now, we'll simulate this with the basic stock info
                atp_data = {
                    "sku": sku,
                    "current_stock": stock_info.on_hand,
                    "reserved_quantity": 0,  # Would come from WMS in real implementation
                    "incoming_orders": 0,  # Would come from ERP in real implementation
                    "available_to_promise": stock_info.on_hand,  # Simplified calculation
                    "locations": stock_info.locations,
                    "last_updated": datetime.now().isoformat(),
                }

                actions_taken.append(
                    {
                        "action": "atp_lookup",
                        "sku": sku,
                        "result": atp_data,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif equipment_query.intent == "charger_status":
                # Extract equipment ID from query or entities
                equipment_id = equipment_query.entities.get("equipment_id")
                if not equipment_id and equipment_query.user_query:
                    import re

                    # Look for patterns like "Truck-07", "Forklift-01", etc.
                    equipment_match = re.search(
                        r"([A-Za-z]+-\d+)", equipment_query.user_query
                    )
                    if equipment_match:
                        equipment_id = equipment_match.group()
                        logger.info(
                            f"Extracted equipment ID from query: {equipment_id}"
                        )

                if equipment_id:
                    # Get charger status
                    charger_status = await self.action_tools.get_charger_status(
                        equipment_id
                    )
                    actions_taken.append(
                        {
                            "action": "get_charger_status",
                            "equipment_id": equipment_id,
                            "result": charger_status,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )
                else:
                    logger.warning("No equipment ID found for charger status query")

            elif equipment_query.intent == "equipment_status":
                # Extract equipment ID from query or entities
                equipment_id = equipment_query.entities.get("equipment_id")
                if not equipment_id and equipment_query.user_query:
                    import re

                    # Look for patterns like "Truck-07", "Forklift-01", etc.
                    equipment_match = re.search(
                        r"([A-Za-z]+-\d+)", equipment_query.user_query
                    )
                    if equipment_match:
                        equipment_id = equipment_match.group()
                        logger.info(
                            f"Extracted equipment ID from query: {equipment_id}"
                        )

                if equipment_id:
                    # Get equipment status
                    equipment_status = await self.action_tools.get_equipment_status(
                        equipment_id
                    )
                    actions_taken.append(
                        {
                            "action": "get_equipment_status",
                            "equipment_id": equipment_id,
                            "result": equipment_status,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )
                else:
                    logger.warning("No equipment ID found for equipment status query")

            elif (
                equipment_query.intent == "reserve_inventory"
                and sku
                and quantity
                and order_id
            ):
                # Reserve inventory
                reservation = await self.action_tools.reserve_inventory(
                    sku=sku,
                    qty=quantity,
                    order_id=order_id,
                    hold_until=equipment_query.entities.get("hold_until"),
                )
                actions_taken.append(
                    {
                        "action": "reserve_inventory",
                        "sku": sku,
                        "quantity": quantity,
                        "order_id": order_id,
                        "result": asdict(reservation),
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif equipment_query.intent == "replenishment" and sku and quantity:
                # Create replenishment task
                replenishment_task = await self.action_tools.create_replenishment_task(
                    sku=sku,
                    from_location=equipment_query.entities.get(
                        "from_location", "STAGING"
                    ),
                    to_location=location or "PICKING",
                    qty=quantity,
                    priority=equipment_query.entities.get("priority", "medium"),
                )
                actions_taken.append(
                    {
                        "action": "create_replenishment_task",
                        "sku": sku,
                        "quantity": quantity,
                        "result": asdict(replenishment_task),
                        "timestamp": datetime.now().isoformat(),
                    }
                )

                # Check if we need to generate a purchase requisition
                if quantity > 0:  # Only if we're actually replenishing
                    # Get current stock to determine if we need to order
                    stock_info = await self.action_tools.check_stock(sku=sku)
                    if stock_info.on_hand <= stock_info.reorder_point:
                        pr = await self.action_tools.generate_purchase_requisition(
                            sku=sku,
                            qty=quantity * 2,  # Order double the replenishment amount
                            supplier=equipment_query.entities.get("supplier"),
                            contract_id=equipment_query.entities.get("contract_id"),
                            need_by_date=equipment_query.entities.get("need_by_date"),
                            tier=1,  # Propose for approval
                            user_id=(
                                context.get("user_id", "system")
                                if context
                                else "system"
                            ),
                        )
                        actions_taken.append(
                            {
                                "action": "generate_purchase_requisition",
                                "sku": sku,
                                "quantity": quantity * 2,
                                "result": asdict(pr),
                                "timestamp": datetime.now().isoformat(),
                            }
                        )

            elif equipment_query.intent == "cycle_count" and (sku or location):
                # Start cycle count
                cycle_count_task = await self.action_tools.start_cycle_count(
                    sku=sku,
                    location=location,
                    class_name=equipment_query.entities.get("class_name"),
                    priority=equipment_query.entities.get("priority", "medium"),
                )
                actions_taken.append(
                    {
                        "action": "start_cycle_count",
                        "sku": sku,
                        "location": location,
                        "result": asdict(cycle_count_task),
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif (
                equipment_query.intent == "adjust_reorder_point"
                and sku
                and "new_rp" in equipment_query.entities
            ):
                # Adjust reorder point (requires planner role)
                adjustment = await self.action_tools.adjust_reorder_point(
                    sku=sku,
                    new_rp=equipment_query.entities["new_rp"],
                    rationale=equipment_query.entities.get(
                        "rationale", "User requested adjustment"
                    ),
                    user_id=context.get("user_id", "system") if context else "system",
                )
                actions_taken.append(
                    {
                        "action": "adjust_reorder_point",
                        "sku": sku,
                        "new_rp": equipment_query.entities["new_rp"],
                        "result": adjustment,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif equipment_query.intent == "reslotting" and sku:
                # Recommend reslotting
                reslotting = await self.action_tools.recommend_reslotting(
                    sku=sku,
                    peak_velocity_window=equipment_query.entities.get(
                        "peak_velocity_window", 30
                    ),
                )
                actions_taken.append(
                    {
                        "action": "recommend_reslotting",
                        "sku": sku,
                        "result": reslotting,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif (
                equipment_query.intent == "investigate_discrepancy"
                and sku
                and "expected_quantity" in equipment_query.entities
            ):
                # Investigate discrepancy
                investigation = await self.action_tools.investigate_discrepancy(
                    sku=sku,
                    location=location or "UNKNOWN",
                    expected_quantity=equipment_query.entities["expected_quantity"],
                    actual_quantity=equipment_query.entities.get("actual_quantity", 0),
                )
                actions_taken.append(
                    {
                        "action": "investigate_discrepancy",
                        "sku": sku,
                        "location": location,
                        "result": asdict(investigation),
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            return actions_taken

        except Exception as e:
            logger.error(f"Action tools execution failed: {e}")
            return [
                {
                    "action": "error",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
            ]

    async def _generate_response(
        self,
        equipment_query: EquipmentQuery,
        retrieved_data: Dict[str, Any],
        session_id: str,
        memory_context: Optional[Dict[str, Any]] = None,
        actions_taken: Optional[List[Dict[str, Any]]] = None,
    ) -> EquipmentResponse:
        """Generate intelligent response using LLM with retrieved context."""
        try:
            # Build context for LLM
            context_str = self._build_retrieved_context(retrieved_data)
            conversation_history = self.conversation_context.get(session_id, {}).get(
                "history", []
            )

            # Add actions taken to context
            actions_str = ""
            if actions_taken:
                actions_str = f"\nActions Taken:\n{json.dumps(actions_taken, indent=2, default=str)}"

            prompt = f"""
You are an inventory intelligence agent. Generate a comprehensive response based on the user query and retrieved data.

User Query: "{equipment_query.user_query}"
Intent: {equipment_query.intent}
Entities: {equipment_query.entities}

Retrieved Data:
{context_str}
{actions_str}

Conversation History: {conversation_history[-3:] if conversation_history else "None"}

Generate a response that includes:
1. Natural language answer to the user's question
2. Structured data in JSON format
3. Actionable recommendations
4. Confidence score (0.0 to 1.0)

Respond in JSON format:
{{
    "response_type": "stock_info",
    "data": {{
        "items": [...],
        "summary": {{...}}
    }},
    "natural_language": "Based on your query, here's what I found...",
    "recommendations": [
        "Recommendation 1",
        "Recommendation 2"
    ],
    "confidence": 0.95
}}
"""

            messages = [
                {
                    "role": "system",
                    "content": "You are an expert inventory analyst. Respond ONLY with valid JSON, no markdown formatting or additional text.",
                },
                {"role": "user", "content": prompt},
            ]

            response = await self.nim_client.generate_response(
                messages, temperature=0.2, max_retries=2
            )

            # Parse LLM response
            try:
                # Extract JSON from response (handle markdown code blocks)
                content = response.content.strip()
                if "```json" in content:
                    # Extract JSON from markdown code block
                    start = content.find("```json") + 7
                    end = content.find("```", start)
                    if end != -1:
                        content = content[start:end].strip()
                elif "```" in content:
                    # Extract JSON from generic code block
                    start = content.find("```") + 3
                    end = content.find("```", start)
                    if end != -1:
                        content = content[start:end].strip()

                parsed_response = json.loads(content)
                return EquipmentResponse(
                    response_type=parsed_response.get("response_type", "general"),
                    data=parsed_response.get("data", {}),
                    natural_language=parsed_response.get(
                        "natural_language", "I processed your inventory query."
                    ),
                    recommendations=parsed_response.get("recommendations", []),
                    confidence=parsed_response.get("confidence", 0.8),
                    actions_taken=actions_taken or [],
                )
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse LLM JSON response: {e}")
                logger.warning(f"Raw response: {response.content}")
                # Fallback response
                return self._generate_fallback_response(
                    equipment_query, retrieved_data, actions_taken
                )

        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            return self._generate_fallback_response(
                equipment_query, retrieved_data, actions_taken
            )

    def _generate_fallback_response(
        self,
        equipment_query: EquipmentQuery,
        retrieved_data: Dict[str, Any],
        actions_taken: Optional[List[Dict[str, Any]]] = None,
    ) -> EquipmentResponse:
        """Generate intelligent fallback response when LLM fails."""
        try:
            search_results = retrieved_data.get("search_results")
            items = []

            # Check if we have data from actions_taken first
            if actions_taken:
                for action in actions_taken:
                    if action.get("action") == "check_stock" and action.get("result"):
                        stock_data = action.get("result")
                        items.append(
                            {
                                "sku": stock_data.get("sku"),
                                "name": stock_data.get("name", "Unknown"),
                                "quantity": stock_data.get("on_hand", 0),
                                "location": (
                                    stock_data.get("locations", [{}])[0].get(
                                        "location", "Unknown"
                                    )
                                    if stock_data.get("locations")
                                    else "Unknown"
                                ),
                                "reorder_point": stock_data.get("reorder_point", 0),
                            }
                        )
                        break

            # Fallback to search results if no actions data
            if (
                not items
                and search_results
                and hasattr(search_results, "structured_results")
                and search_results.structured_results
            ):
                items = search_results.structured_results

            # Generate more intelligent response based on query intent
            if equipment_query.intent == "equipment_lookup":
                if items:
                    item = items[0]  # Take first item
                    natural_language = (
                        f"📦 Equipment Status for {item.get('sku', 'Unknown')}:\n"
                    )
                    natural_language += f"• Name: {item.get('name', 'Unknown')}\n"
                    natural_language += (
                        f"• Available Quantity: {item.get('quantity', 0)} units\n"
                    )
                    natural_language += (
                        f"• Location: {item.get('location', 'Unknown')}\n"
                    )
                    natural_language += (
                        f"• Reorder Point: {item.get('reorder_point', 0)} units\n"
                    )
                    if item.get("quantity", 0) <= item.get("reorder_point", 0):
                        natural_language += (
                            f"⚠️ This equipment is at or below reorder point!"
                        )
                    else:
                        natural_language += f"✅ Stock level is healthy."
                else:
                    natural_language = f"I couldn't find equipment data for your query."
            elif equipment_query.intent == "stock_lookup":
                if len(items) == 1:
                    item = items[0]
                    natural_language = f"Found {item.name} (SKU: {item.sku}) with {item.quantity} units in stock at {item.location}. "
                    if item.quantity <= item.reorder_point:
                        natural_language += f"⚠️ This item is at or below reorder point ({item.reorder_point} units)."
                    else:
                        natural_language += f"Stock level is healthy (reorder point: {item.reorder_point} units)."
                else:
                    natural_language = (
                        f"I found {len(items)} inventory items matching your query."
                    )
            elif equipment_query.intent == "atp_lookup":
                if len(items) == 1:
                    item = items[0]
                    # Get ATP data from actions taken
                    atp_data = None
                    for action in actions_taken or []:
                        if action.get("action") == "atp_lookup":
                            atp_data = action.get("result")
                            break

                    if atp_data:
                        natural_language = f"📊 Available to Promise (ATP) for {item.get('name', 'Unknown')} (SKU: {item.get('sku', 'Unknown')}):\n"
                        natural_language += (
                            f"• Current Stock: {atp_data['current_stock']} units\n"
                        )
                        natural_language += f"• Reserved Quantity: {atp_data['reserved_quantity']} units\n"
                        natural_language += (
                            f"• Incoming Orders: {atp_data['incoming_orders']} units\n"
                        )
                        natural_language += f"• Available to Promise: {atp_data['available_to_promise']} units\n"
                        natural_language += (
                            f"• Location: {item.get('location', 'Unknown')}"
                        )
                    else:
                        natural_language = f"Found {item.get('name', 'Unknown')} (SKU: {item.get('sku', 'Unknown')}) with {item.get('quantity', 0)} units available at {item.get('location', 'Unknown')}."
                else:
                    natural_language = (
                        f"I found {len(items)} inventory items matching your ATP query."
                    )

            elif equipment_query.intent == "charger_status":
                # Get charger status from actions taken
                charger_data = None
                for action in actions_taken or []:
                    if action.get("action") == "get_charger_status":
                        charger_data = action.get("result")
                        break

                if charger_data and charger_data.get("success"):
                    charger_status = charger_data.get("charger_status", {})
                    equipment_id = charger_status.get("equipment_id", "Unknown")
                    is_charging = charger_status.get("is_charging", False)
                    battery_level = charger_status.get("battery_level", 0)
                    temperature = charger_status.get("temperature", 0)
                    status = charger_status.get("status", "unknown")
                    estimated_time = charger_status.get(
                        "estimated_charge_time", "Unknown"
                    )
                    recommendations = charger_status.get("recommendations", [])

                    natural_language = f"🔋 **Charger Status for {equipment_id}**\n\n"
                    natural_language += (
                        f"**Status:** {status.replace('_', ' ').title()}\n"
                    )
                    natural_language += (
                        f"**Charging:** {'Yes' if is_charging else 'No'}\n"
                    )
                    natural_language += f"**Battery Level:** {battery_level}%\n"
                    natural_language += f"**Temperature:** {temperature}°C\n"

                    if is_charging:
                        natural_language += (
                            f"**Estimated Charge Time:** {estimated_time}\n"
                        )

                    if recommendations:
                        natural_language += f"\n**Recommendations:**\n"
                        for rec in recommendations:
                            natural_language += f"• {rec}\n"
                else:
                    natural_language = "I couldn't retrieve charger status information. Please check the equipment ID and try again."

            elif equipment_query.intent == "equipment_status":
                # Get equipment status from actions taken
                equipment_data = None
                for action in actions_taken or []:
                    if action.get("action") == "get_equipment_status":
                        equipment_data = action.get("result")
                        break

                if equipment_data and equipment_data.get("success"):
                    equipment_status = equipment_data.get("equipment_status", {})
                    equipment_id = equipment_status.get("equipment_id", "Unknown")
                    status = equipment_status.get("status", "unknown")
                    battery_level = equipment_status.get("battery_level", 0)
                    temperature = equipment_status.get("temperature", 0)
                    is_operational = equipment_status.get("is_operational", True)
                    recommendations = equipment_status.get("recommendations", [])

                    natural_language = f"🚛 **Equipment Status for {equipment_id}**\n\n"
                    natural_language += (
                        f"**Status:** {status.replace('_', ' ').title()}\n"
                    )
                    natural_language += (
                        f"**Operational:** {'Yes' if is_operational else 'No'}\n"
                    )
                    natural_language += f"**Battery Level:** {battery_level}%\n"
                    natural_language += f"**Temperature:** {temperature}°C\n"

                    if recommendations:
                        natural_language += f"\n**Recommendations:**\n"
                        for rec in recommendations:
                            natural_language += f"• {rec}\n"
                else:
                    natural_language = "I couldn't retrieve equipment status information. Please check the equipment ID and try again."

            else:
                natural_language = (
                    f"I found {len(items)} inventory items matching your query."
                )

            # Set recommendations based on intent
            if equipment_query.intent == "atp_lookup":
                recommendations = [
                    "Monitor ATP levels regularly",
                    "Consider safety stock for critical items",
                    "Review reserved quantities",
                ]
            else:
                recommendations = [
                    "Consider reviewing stock levels",
                    "Check reorder points",
                ]
            confidence = 0.8 if items else 0.6

            return EquipmentResponse(
                response_type="fallback",
                data={"items": items if items else []},
                natural_language=natural_language,
                recommendations=recommendations,
                confidence=confidence,
                actions_taken=actions_taken or [],
            )

        except Exception as e:
            logger.error(f"Fallback response generation failed: {e}")
            return EquipmentResponse(
                response_type="error",
                data={"error": str(e)},
                natural_language="I encountered an error processing your request.",
                recommendations=[],
                confidence=0.0,
                actions_taken=actions_taken or [],
            )

    def _build_context_string(
        self, conversation_history: List[Dict], context: Optional[Dict[str, Any]]
    ) -> str:
        """Build context string from conversation history."""
        if not conversation_history and not context:
            return "No previous context"

        context_parts = []

        if conversation_history:
            recent_history = conversation_history[-3:]  # Last 3 exchanges
            context_parts.append(f"Recent conversation: {recent_history}")

        if context:
            context_parts.append(f"Additional context: {context}")

        return "; ".join(context_parts)

    def _build_retrieved_context(self, retrieved_data: Dict[str, Any]) -> str:
        """Build context string from retrieved data."""
        try:
            context_parts = []

            # Add inventory summary
            inventory_summary = retrieved_data.get("inventory_summary", {})
            if inventory_summary:
                context_parts.append(f"Inventory Summary: {inventory_summary}")

            # Add search results
            search_results = retrieved_data.get("search_results")
            if search_results:
                if search_results.structured_results:
                    items = search_results.structured_results
                    context_parts.append(f"Found {len(items)} inventory items")
                    for item in items[:5]:  # Show first 5 items
                        context_parts.append(
                            f"- {item.sku}: {item.name} (Qty: {item.quantity}, Location: {item.location})"
                        )

                if search_results.vector_results:
                    docs = search_results.vector_results
                    context_parts.append(f"Found {len(docs)} relevant documents")

            return (
                "\n".join(context_parts) if context_parts else "No relevant data found"
            )

        except Exception as e:
            logger.error(f"Context building failed: {e}")
            return "Error building context"

    def _update_context(
        self,
        session_id: str,
        equipment_query: EquipmentQuery,
        response: EquipmentResponse,
    ) -> None:
        """Update conversation context."""
        try:
            if session_id not in self.conversation_context:
                self.conversation_context[session_id] = {
                    "history": [],
                    "current_focus": None,
                    "last_entities": {},
                }

            # Add to history
            self.conversation_context[session_id]["history"].append(
                {
                    "query": equipment_query.user_query,
                    "intent": equipment_query.intent,
                    "response_type": response.response_type,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            # Update current focus
            if equipment_query.intent != "general":
                self.conversation_context[session_id][
                    "current_focus"
                ] = equipment_query.intent

            # Update last entities
            if equipment_query.entities:
                self.conversation_context[session_id][
                    "last_entities"
                ] = equipment_query.entities

            # Keep history manageable
            if len(self.conversation_context[session_id]["history"]) > 10:
                self.conversation_context[session_id]["history"] = (
                    self.conversation_context[session_id]["history"][-10:]
                )

        except Exception as e:
            logger.error(f"Context update failed: {e}")

    async def get_conversation_context(self, session_id: str) -> Dict[str, Any]:
        """Get conversation context for a session."""
        return self.conversation_context.get(
            session_id, {"history": [], "current_focus": None, "last_entities": {}}
        )

    async def clear_conversation_context(self, session_id: str) -> None:
        """Clear conversation context for a session."""
        if session_id in self.conversation_context:
            del self.conversation_context[session_id]


# Global equipment agent instance
_equipment_agent: Optional[EquipmentAssetOperationsAgent] = None


async def get_equipment_agent() -> EquipmentAssetOperationsAgent:
    """Get or create the global equipment agent instance."""
    global _equipment_agent
    if _equipment_agent is None:
        _equipment_agent = EquipmentAssetOperationsAgent()
        await _equipment_agent.initialize()
    return _equipment_agent
