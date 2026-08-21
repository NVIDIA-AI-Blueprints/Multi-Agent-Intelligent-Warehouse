# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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
import os
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
import json
from datetime import datetime, timedelta
import asyncio

from src.api.services.llm.nim_client import get_nim_client, LLMResponse
from src.api.services.model_gateway import (
    get_model_gateway,
    is_model_gateway_enabled,
    ModelRequest,
    ModelGatewayError,
)
from src.api.services.model_gateway.models import ReasoningLevel, RiskLevel
from src.retrieval.hybrid_retriever import get_hybrid_retriever, SearchContext
from src.memory.memory_manager import get_memory_manager
from src.api.services.agent_config import load_agent_config, AgentConfig
from .equipment_asset_tools import get_equipment_asset_tools, EquipmentAssetTools
from .action_executor import (
    ActionExecutor,
    ActionExecutionResult,
    EquipmentActionExecutor,
    NoOpActionExecutor,
)
from . import state_aware_ops

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

    State-aware paths (activated when MAIW_MCP_SERVER_EQUIPMENT_URL is set)
    -----------------------------------------------------------------------
    - Equipment status queries assemble WarehouseStateSnapshot before reasoning.
    - Equipment assignment goes through ActionProposal → DecisionEngine; the
      write capability is never invoked without an APPROVED decision.

    Dependency injection
    --------------------
    Pass ``state_provider``, ``decision_engine``, ``assignment_skill``, and/or
    ``action_executor`` at construction time for testability.  When omitted the
    agent wires them lazily in ``initialize()`` from process-level singletons.
    """

    def __init__(
        self,
        *,
        state_provider=None,   # StateProvider | None
        decision_engine=None,  # DecisionEngine | None
        assignment_skill=None, # EquipmentAssignmentSkill | None
        action_executor: Optional[ActionExecutor] = None,
    ):
        self.nim_client = None
        self.model_gateway = None
        self.hybrid_retriever = None
        self.asset_tools = None
        self.conversation_context = {}  # Maintain conversation context
        self.config: Optional[AgentConfig] = None  # Agent configuration
        # State-aware runtime components (injected or built in initialize())
        self._state_provider = state_provider
        self._decision_engine = decision_engine
        self._assignment_skill = assignment_skill
        self._action_executor: ActionExecutor = action_executor or NoOpActionExecutor()

    async def initialize(self) -> None:
        """Initialize the agent with required services."""
        try:
            # Load agent configuration
            self.config = load_agent_config("equipment")
            logger.info(f"Loaded agent configuration: {self.config.name}")

            if is_model_gateway_enabled():
                self.model_gateway = await get_model_gateway()
                self.nim_client = None
            else:
                # DEPRECATED: direct NIM path — remove after endpoint validation.
                self.nim_client = await get_nim_client()
            self.hybrid_retriever = await get_hybrid_retriever()
            self.asset_tools = await get_equipment_asset_tools()

            # Wire state-aware path when the equipment MCP server is configured.
            if os.environ.get("MAIW_MCP_SERVER_EQUIPMENT_URL"):
                await self._initialize_state_path()
            else:
                logger.info(
                    "MAIW_MCP_SERVER_EQUIPMENT_URL not set — "
                    "assignment will use legacy direct-write path"
                )

            logger.info("Equipment & Asset Operations Agent initialized successfully")
        except Exception as e:
            logger.error(
                f"Failed to initialize Equipment & Asset Operations Agent: {e}"
            )
            raise

    async def _initialize_state_path(self) -> None:
        """Wire WarehouseStateProvider, DecisionEngine, assignment skill, and executor."""
        try:
            from maiw_state import WarehouseStateProvider
            from maiw_decision import DecisionEngine
            from src.api.skills.equipment import (
                get_equipment_assignment_skill,
                get_equipment_status_skill,
                get_execute_equipment_assignment_skill,
                get_execute_equipment_release_skill,
                get_execute_equipment_maintenance_skill,
            )

            if self._state_provider is None:
                equipment_status_skill = await get_equipment_status_skill()
                self._state_provider = WarehouseStateProvider(
                    equipment_status_skill=equipment_status_skill
                )

            if self._decision_engine is None:
                self._decision_engine = DecisionEngine()

            if self._assignment_skill is None:
                self._assignment_skill = await get_equipment_assignment_skill()

            if isinstance(self._action_executor, NoOpActionExecutor):
                assign_exec = await get_execute_equipment_assignment_skill()
                release_exec = await get_execute_equipment_release_skill()
                maintenance_exec = await get_execute_equipment_maintenance_skill()
                self._action_executor = EquipmentActionExecutor(
                    assign_skill=assign_exec,
                    release_skill=release_exec,
                    maintenance_skill=maintenance_exec,
                    state_provider=self._state_provider,
                )

            logger.info("State-aware path initialized: DecisionEngine + EquipmentActionExecutor active")
        except Exception as exc:
            logger.warning(
                "Failed to initialize state-aware path; falling back to legacy: %s", exc
            )

    # ------------------------------------------------------------------
    # State-aware public API
    # ------------------------------------------------------------------

    async def propose_equipment_assignment(
        self,
        asset_id: str,
        assignee: str,
        assignment_type: str = "task",
        task_id: Optional[str] = None,
        duration_hours: Optional[float] = None,
        notes: Optional[str] = None,
        *,
        warehouse_id: str = "default",
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        State-aware equipment assignment — assembles state, builds ActionProposal,
        evaluates with DecisionEngine, and returns the decision result.

        The write capability (warehouse.equipment.assign) is NEVER called by this
        method.  No DB mutation occurs here.

        Returns a structured dict matching the API response shape:
            {
                "status": "requires_human_approval" | "approved" | "rejected" | ...,
                "action": "warehouse.equipment.assign",
                "proposal_id": "...",
                "decision_id": "...",
                "reason": "...",
                "executed": false,
                "snapshot_id": "...",
                "trace_id": "...",
            }

        Falls back to the legacy direct-write path if the state-aware path is
        not configured (MAIW_MCP_SERVER_EQUIPMENT_URL not set).
        """
        if not (self._state_provider and self._decision_engine and self._assignment_skill):
            logger.warning(
                "State-aware path not available for assignment of %s; using legacy path",
                asset_id,
            )
            return await self._legacy_assign(
                asset_id=asset_id,
                assignee=assignee,
                assignment_type=assignment_type,
                task_id=task_id,
                duration_hours=duration_hours,
                notes=notes,
            )

        return await state_aware_ops.propose_equipment_assignment(
            asset_id=asset_id,
            assignee=assignee,
            assignment_type=assignment_type,
            task_id=task_id,
            duration_hours=duration_hours,
            notes=notes,
            warehouse_id=warehouse_id,
            trace_id=trace_id,
            state_provider=self._state_provider,
            decision_engine=self._decision_engine,
            assignment_skill=self._assignment_skill,
            action_executor=self._action_executor,
        )

    async def propose_equipment_release(
        self,
        asset_id: str,
        released_by: str,
        notes: Optional[str] = None,
        *,
        warehouse_id: str = "default",
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        State-aware equipment release — state → ActionProposal → DecisionEngine → (optional) execute.

        LOW risk: auto-approved by DecisionEngine unless state is absent/stale or
        asset not found. When approved and an executor is wired, the release is
        executed immediately and ``executed: true`` is returned.

        Falls back to direct ``asset_tools.release_equipment()`` when the
        state-aware path is not configured.
        """
        if not (self._state_provider and self._decision_engine):
            logger.warning(
                "State-aware path not available for release of %s; using legacy path", asset_id
            )
            result = await self.asset_tools.release_equipment(
                asset_id=asset_id, released_by=released_by, notes=notes
            )
            return {
                "status": "executed" if result.get("success") else "error",
                "action": "warehouse.equipment.release",
                "reason": result.get("error", "legacy direct write"),
                "executed": result.get("success", False),
                "legacy_result": result,
            }

        return await state_aware_ops.propose_equipment_release(
            asset_id=asset_id,
            released_by=released_by,
            notes=notes,
            warehouse_id=warehouse_id,
            trace_id=trace_id,
            state_provider=self._state_provider,
            decision_engine=self._decision_engine,
            action_executor=self._action_executor,
        )

    async def propose_schedule_maintenance(
        self,
        asset_id: str,
        maintenance_type: str,
        description: str,
        scheduled_by: str,
        scheduled_for: str,
        estimated_duration_minutes: int = 60,
        priority: str = "medium",
        *,
        warehouse_id: str = "default",
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        State-aware maintenance scheduling — state → ActionProposal → DecisionEngine.

        MEDIUM risk: always returns ``requires_human_approval``. Falls back to
        direct ``asset_tools.schedule_maintenance()`` when the state-aware path
        is not configured.
        """
        if not (self._state_provider and self._decision_engine):
            logger.warning(
                "State-aware path not available for maintenance of %s; using legacy path", asset_id
            )
            from datetime import datetime as _dt
            try:
                sf_dt = _dt.fromisoformat(scheduled_for.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                sf_dt = _dt.now()
            result = await self.asset_tools.schedule_maintenance(
                asset_id=asset_id,
                maintenance_type=maintenance_type,
                description=description,
                scheduled_by=scheduled_by,
                scheduled_for=sf_dt,
                estimated_duration_minutes=estimated_duration_minutes,
                priority=priority,
            )
            return {
                "status": "executed" if result.get("success") else "error",
                "action": "warehouse.equipment.schedule_maintenance",
                "reason": result.get("error", "legacy direct write"),
                "executed": result.get("success", False),
                "legacy_result": result,
            }

        return await state_aware_ops.propose_schedule_maintenance(
            asset_id=asset_id,
            maintenance_type=maintenance_type,
            description=description,
            scheduled_by=scheduled_by,
            scheduled_for=scheduled_for,
            estimated_duration_minutes=estimated_duration_minutes,
            priority=priority,
            warehouse_id=warehouse_id,
            trace_id=trace_id,
            state_provider=self._state_provider,
            decision_engine=self._decision_engine,
        )

    async def get_equipment_state_snapshot(
        self,
        asset_id: Optional[str] = None,
        equipment_type: Optional[str] = None,
        zone: Optional[str] = None,
        *,
        warehouse_id: str = "default",
        trace_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Assemble a WarehouseStateSnapshot for equipment and return a structured
        summary suitable for agent reasoning context.

        Returns None when the state-aware path is not configured.
        """
        if not self._state_provider:
            return None

        return await state_aware_ops.get_equipment_state_snapshot(
            asset_id=asset_id,
            equipment_type=equipment_type,
            zone=zone,
            warehouse_id=warehouse_id,
            trace_id=trace_id,
            state_provider=self._state_provider,
        )

    async def _legacy_assign(
        self,
        *,
        asset_id: str,
        assignee: str,
        assignment_type: str,
        task_id: Optional[str],
        duration_hours: Optional[float],
        notes: Optional[str],
    ) -> Dict[str, Any]:
        """Legacy direct-write assignment — preserved for environments without MCP server."""
        if not self.asset_tools:
            await self.initialize()
        result = await self.asset_tools.assign_equipment(
            asset_id=asset_id,
            assignee=assignee,
            assignment_type=assignment_type,
            task_id=task_id,
            duration_hours=duration_hours,
            notes=notes,
        )
        # Wrap in the structured response shape so callers see a consistent schema
        return {
            "status": "approved" if result.get("success") else "error",
            "action": "warehouse.equipment.assign",
            "reason": result.get("error", "legacy direct write"),
            "executed": result.get("success", False),
            "legacy_result": result,
        }

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
            if not (self.model_gateway or self.nim_client) or not self.hybrid_retriever:
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

            # Load prompt from configuration
            if self.config is None:
                self.config = load_agent_config("equipment")
            
            understanding_prompt_template = self.config.persona.understanding_prompt
            
            # Format the understanding prompt with actual values
            prompt = understanding_prompt_template.format(
                query=query,
                context=context_str
            )

            if self.model_gateway:
                _gw = await self.model_gateway.generate(ModelRequest(
                    task="warehouse.equipment.understand_query",
                    messages=[{"role": "user", "content": prompt}],
                    reasoning=ReasoningLevel.LOW,
                    risk_level=RiskLevel.LOW,
                    temperature=0.1,
                ))
                response_content = _gw.content
            else:
                # DEPRECATED: direct NIM path — remove after endpoint validation.
                _llm = await self.nim_client.generate_response(
                    [{"role": "user", "content": prompt}], temperature=0.1
                )
                response_content = _llm.content

            # Parse JSON response
            try:
                parsed_response = json.loads(response_content.strip())
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
                # Route through state-aware proposal → DecisionEngine path.
                # Never calls asset_tools.assign_equipment() directly.
                decision_response = await self.propose_equipment_assignment(
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
                        "action": "propose_equipment_assignment",
                        "asset_id": asset_id,
                        "result": decision_response,
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

            # Load response prompt from configuration
            if self.config is None:
                self.config = load_agent_config("equipment")
            
            response_prompt_template = self.config.persona.response_prompt
            
            # Format the response prompt with actual values
            prompt = response_prompt_template.format(
                user_query=equipment_query.user_query,
                intent=equipment_query.intent,
                entities=equipment_query.entities,
                retrieved_data=context_str,
                actions_taken=json.dumps(actions_taken, indent=2, default=str)
            )

            # Maintenance scheduling and failure diagnosis are higher risk than status lookups.
            _is_high_risk = equipment_query.intent in {"maintenance", "assignment"}
            _reasoning = ReasoningLevel.HIGH if equipment_query.intent in {"utilization", "maintenance"} else ReasoningLevel.MEDIUM
            _risk = RiskLevel.HIGH if _is_high_risk else RiskLevel.LOW

            if self.model_gateway:
                _gw = await self.model_gateway.generate(ModelRequest(
                    task=f"warehouse.equipment.{equipment_query.intent}",
                    messages=[{"role": "user", "content": prompt}],
                    reasoning=_reasoning,
                    risk_level=_risk,
                    temperature=0.3,
                ))
                _response_text = _gw.content
            else:
                # DEPRECATED: direct NIM path — remove after endpoint validation.
                _llm = await self.nim_client.generate_response(
                    [{"role": "user", "content": prompt}], temperature=0.3
                )
                _response_text = _llm.content

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
            recommendations = self._extract_recommendations(_response_text)

            return EquipmentResponse(
                response_type=response_type,
                data=retrieved_data,
                natural_language=_response_text,
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
