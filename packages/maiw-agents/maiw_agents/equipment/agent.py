# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Equipment & Asset Operations Agent (EAO) — maiw-agents package.

Migration notes (Phase 9A)
--------------------------
- All src.* imports removed; dependencies are injected at construction time.
- NIM fallback branches removed; only the ModelGateway path is retained.
- SearchContext sourced from maiw_agents.common.types (no retrieval.* import).
- ActionExecutor / ActionExecutionResult / NoOpActionExecutor sourced from maiw_execution.
- Bootstrap (apps/api/maiw_api/bootstrap.py) creates concrete instances and injects them.

Mission: Ensure equipment is available, safe, and optimally used for warehouse workflows.
Owns: availability, assignments, telemetry, maintenance requests, compliance links.
Collaborates: with Operations Coordination Agent for task/route planning and equipment
allocation, with Safety & Compliance Agent for pre-op checks, incidents, LOTO.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from maiw_execution import ActionExecutor, NoOpActionExecutor

from ..common.types import SearchContext
from . import state_aware_ops

logger = logging.getLogger(__name__)


@dataclass
class EquipmentQuery:
    """Structured equipment query."""

    intent: str  # "equipment_lookup", "assignment", "utilization", "maintenance", "availability", "telemetry"
    entities: Dict[str, Any]
    context: Dict[str, Any]
    user_query: str


@dataclass
class EquipmentResponse:
    """Structured equipment response."""

    response_type: str
    data: Dict[str, Any]
    natural_language: str
    recommendations: List[str]
    confidence: float
    actions_taken: List[Dict[str, Any]]


class EquipmentAssetOperationsAgent:
    """
    Equipment & Asset Operations Agent — ModelGateway-only, no src.* imports.

    All heavy runtime dependencies (model_gateway, hybrid_retriever, asset_tools,
    config) are injected at construction time. Bootstrap is responsible for
    creating concrete instances and wiring them here.

    State-aware paths (activated when state_provider is injected)
    -------------------------------------------------------------
    - Equipment status queries assemble WarehouseStateSnapshot before reasoning.
    - Equipment assignment goes through ActionProposal → DecisionEngine; the
      write capability is never invoked without an APPROVED decision.
    """

    def __init__(
        self,
        *,
        # ModelGateway for LLM calls (required for process_query)
        model_gateway: Optional[Any] = None,
        # Hybrid retriever for semantic search
        hybrid_retriever: Optional[Any] = None,
        # EquipmentAssetTools for direct MCP reads
        asset_tools: Optional[Any] = None,
        # AgentConfig (from src.api.services.agent_config) — duck-typed
        config: Optional[Any] = None,
        # State-aware components
        state_provider: Optional[Any] = None,
        decision_engine: Optional[Any] = None,
        assignment_skill: Optional[Any] = None,
        action_executor: Optional[ActionExecutor] = None,
    ) -> None:
        self.model_gateway = model_gateway
        self.hybrid_retriever = hybrid_retriever
        self.asset_tools = asset_tools
        self.config = config
        self.conversation_context: Dict[str, Any] = {}

        self._state_provider = state_provider
        self._decision_engine = decision_engine
        self._assignment_skill = assignment_skill
        self._action_executor: ActionExecutor = action_executor or NoOpActionExecutor()

    async def initialize(self) -> None:
        """
        No-op: all dependencies are injected at construction time.
        Kept for backward-compatibility with callers that call initialize() on startup.
        """
        logger.info("EquipmentAssetOperationsAgent.initialize() called — all deps pre-injected.")

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

        Falls back to the legacy direct-write path if the state-aware path is
        not configured (state_provider not injected).
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
        asset not found. Falls back to direct asset_tools.release_equipment() when
        the state-aware path is not configured.
        """
        if not (self._state_provider and self._decision_engine):
            logger.warning(
                "State-aware path not available for release of %s; using legacy path", asset_id
            )
            if self.asset_tools:
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
            return {
                "status": "error",
                "action": "warehouse.equipment.release",
                "reason": "no state_provider or asset_tools configured",
                "executed": False,
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

        MEDIUM risk: always returns requires_human_approval. Falls back to
        direct asset_tools.schedule_maintenance() when state-aware path is not configured.
        """
        if not (self._state_provider and self._decision_engine):
            logger.warning(
                "State-aware path not available for maintenance of %s; using legacy path", asset_id
            )
            if self.asset_tools:
                try:
                    sf_dt = datetime.fromisoformat(scheduled_for.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    sf_dt = datetime.now()
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
            return {
                "status": "error",
                "action": "warehouse.equipment.schedule_maintenance",
                "reason": "no state_provider or asset_tools configured",
                "executed": False,
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
        """Return a WarehouseStateSnapshot summary for agent reasoning context, or None."""
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
            return {
                "status": "error",
                "action": "warehouse.equipment.assign",
                "reason": "no asset_tools configured",
                "executed": False,
            }
        result = await self.asset_tools.assign_equipment(
            asset_id=asset_id,
            assignee=assignee,
            assignment_type=assignment_type,
            task_id=task_id,
            duration_hours=duration_hours,
            notes=notes,
        )
        return {
            "status": "approved" if result.get("success") else "error",
            "action": "warehouse.equipment.assign",
            "reason": result.get("error", "legacy direct write"),
            "executed": result.get("success", False),
            "legacy_result": result,
        }

    # ------------------------------------------------------------------
    # Reasoning loop (process_query)
    # ------------------------------------------------------------------

    async def process_query(
        self,
        query: str,
        session_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
    ) -> EquipmentResponse:
        """
        Process an equipment/asset operations query.

        Requires model_gateway and hybrid_retriever to be injected.
        """
        try:
            if session_id not in self.conversation_context:
                self.conversation_context[session_id] = {
                    "history": [],
                    "current_focus": None,
                    "last_entities": {},
                }

            equipment_query = await self._understand_query(query, session_id, context)
            retrieved_data = await self._retrieve_equipment_data(equipment_query)
            actions_taken = await self._execute_action_tools(equipment_query, context)
            response = await self._generate_equipment_response(
                equipment_query, retrieved_data, session_id, actions_taken
            )

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
            logger.error("Error processing equipment query: %s", e)
            return await self._generate_fallback_response(query, session_id, str(e))

    async def _understand_query(
        self, query: str, session_id: str, context: Optional[Dict[str, Any]]
    ) -> EquipmentQuery:
        try:
            conversation_history = self.conversation_context.get(session_id, {}).get("history", [])
            context_str = self._build_context_string(conversation_history, context)

            understanding_prompt_template = self.config.persona.understanding_prompt
            prompt = understanding_prompt_template.format(query=query, context=context_str)

            from maiw_models import ModelRequest, ReasoningLevel, RiskLevel

            gw_resp = await self.model_gateway.generate(ModelRequest(
                task="warehouse.equipment.understand_query",
                messages=[{"role": "user", "content": prompt}],
                reasoning=ReasoningLevel.LOW,
                risk_level=RiskLevel.LOW,
                temperature=0.1,
            ))
            response_content = gw_resp.content

            try:
                parsed = json.loads(response_content.strip())
                return EquipmentQuery(
                    intent=parsed.get("intent", "equipment_lookup"),
                    entities=parsed.get("entities", {}),
                    context=parsed.get("context", {}),
                    user_query=query,
                )
            except json.JSONDecodeError:
                logger.warning("Failed to parse LLM response as JSON, using fallback")
                return EquipmentQuery(intent="equipment_lookup", entities={}, context={}, user_query=query)

        except Exception as e:
            logger.error("Error understanding query: %s", e)
            return EquipmentQuery(intent="equipment_lookup", entities={}, context={}, user_query=query)

    async def _retrieve_equipment_data(self, equipment_query: EquipmentQuery) -> Dict[str, Any]:
        try:
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
            search_results = await self.hybrid_retriever.search(search_context)
            return {
                "search_results": search_results,
                "query_filters": search_context.filters,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            logger.error("Data retrieval failed: %s", e)
            return {"error": str(e)}

    async def _execute_action_tools(
        self, equipment_query: EquipmentQuery, context: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        actions_taken: List[Dict[str, Any]] = []
        try:
            if not self.asset_tools:
                return actions_taken

            asset_id = equipment_query.entities.get("asset_id")
            equipment_type = equipment_query.entities.get("equipment_type")
            zone = equipment_query.entities.get("zone")
            assignee = equipment_query.entities.get("assignee")

            if not asset_id and equipment_query.user_query:
                asset_match = re.search(r"[A-Z]{2,3}-\d+", equipment_query.user_query.upper())
                if asset_match:
                    asset_id = asset_match.group()
                    logger.info("Extracted asset_id from query: %s", asset_id)

            if equipment_query.intent == "equipment_lookup":
                equipment_status = await self.asset_tools.get_equipment_status(
                    asset_id=asset_id,
                    equipment_type=equipment_type,
                    zone=zone,
                    status=equipment_query.entities.get("status"),
                )
                actions_taken.append({
                    "action": "get_equipment_status",
                    "asset_id": asset_id,
                    "result": equipment_status,
                    "timestamp": datetime.now().isoformat(),
                })

            elif equipment_query.intent == "assignment" and asset_id and assignee:
                decision_response = await self.propose_equipment_assignment(
                    asset_id=asset_id,
                    assignee=assignee,
                    assignment_type=equipment_query.entities.get("assignment_type", "task"),
                    task_id=equipment_query.entities.get("task_id"),
                    duration_hours=equipment_query.entities.get("duration_hours"),
                    notes=equipment_query.entities.get("notes"),
                )
                actions_taken.append({
                    "action": "propose_equipment_assignment",
                    "asset_id": asset_id,
                    "result": decision_response,
                    "timestamp": datetime.now().isoformat(),
                })

            elif equipment_query.intent == "utilization" and asset_id:
                telemetry_data = await self.asset_tools.get_equipment_telemetry(
                    asset_id=asset_id,
                    metric=equipment_query.entities.get("metric"),
                    hours_back=equipment_query.entities.get("hours_back", 24),
                )
                actions_taken.append({
                    "action": "get_equipment_telemetry",
                    "asset_id": asset_id,
                    "result": telemetry_data,
                    "timestamp": datetime.now().isoformat(),
                })

            elif equipment_query.intent == "maintenance" and asset_id:
                maintenance_result = await self.asset_tools.schedule_maintenance(
                    asset_id=asset_id,
                    maintenance_type=equipment_query.entities.get("maintenance_type", "preventive"),
                    description=equipment_query.entities.get("description", "Scheduled maintenance"),
                    scheduled_by=equipment_query.entities.get("scheduled_by", "system"),
                    scheduled_for=equipment_query.entities.get("scheduled_for", datetime.now()),
                    estimated_duration_minutes=equipment_query.entities.get("duration_minutes", 60),
                    priority=equipment_query.entities.get("priority", "medium"),
                )
                actions_taken.append({
                    "action": "schedule_maintenance",
                    "asset_id": asset_id,
                    "result": maintenance_result,
                    "timestamp": datetime.now().isoformat(),
                })

            elif equipment_query.intent == "release" and asset_id:
                release_result = await self.asset_tools.release_equipment(
                    asset_id=asset_id,
                    released_by=equipment_query.entities.get("released_by", "system"),
                    notes=equipment_query.entities.get("notes"),
                )
                actions_taken.append({
                    "action": "release_equipment",
                    "asset_id": asset_id,
                    "result": release_result,
                    "timestamp": datetime.now().isoformat(),
                })

            elif equipment_query.intent == "telemetry" and asset_id:
                telemetry_data = await self.asset_tools.get_equipment_telemetry(
                    asset_id=asset_id,
                    metric=equipment_query.entities.get("metric"),
                    hours_back=equipment_query.entities.get("hours_back", 24),
                )
                actions_taken.append({
                    "action": "get_equipment_telemetry",
                    "asset_id": asset_id,
                    "result": telemetry_data,
                    "timestamp": datetime.now().isoformat(),
                })

        except Exception as e:
            logger.error("Error executing action tools: %s", e)
            actions_taken.append({
                "action": "error",
                "result": {"error": str(e)},
                "timestamp": datetime.now().isoformat(),
            })

        return actions_taken

    async def _generate_equipment_response(
        self,
        equipment_query: EquipmentQuery,
        retrieved_data: Dict[str, Any],
        session_id: str,
        actions_taken: List[Dict[str, Any]],
    ) -> EquipmentResponse:
        try:
            context_str = self._build_retrieved_context(retrieved_data, actions_taken)
            response_prompt_template = self.config.persona.response_prompt
            prompt = response_prompt_template.format(
                user_query=equipment_query.user_query,
                intent=equipment_query.intent,
                entities=equipment_query.entities,
                retrieved_data=context_str,
                actions_taken=json.dumps(actions_taken, indent=2, default=str),
            )

            from maiw_models import ModelRequest, ReasoningLevel, RiskLevel

            _reasoning = (
                ReasoningLevel.HIGH
                if equipment_query.intent in {"utilization", "maintenance"}
                else ReasoningLevel.MEDIUM
            )
            _risk = (
                RiskLevel.HIGH
                if equipment_query.intent in {"maintenance", "assignment"}
                else RiskLevel.LOW
            )

            gw_resp = await self.model_gateway.generate(ModelRequest(
                task=f"warehouse.equipment.{equipment_query.intent}",
                messages=[{"role": "user", "content": prompt}],
                reasoning=_reasoning,
                risk_level=_risk,
                temperature=0.3,
            ))
            _response_text = gw_resp.content

            response_type_map = {
                "equipment_lookup": "equipment_info",
                "assignment": "assignment_status",
                "utilization": "utilization_report",
                "maintenance": "maintenance_plan",
                "availability": "availability_status",
                "release": "release_status",
                "telemetry": "telemetry_data",
            }
            response_type = response_type_map.get(equipment_query.intent, "equipment_info")
            recommendations = self._extract_recommendations(_response_text)

            return EquipmentResponse(
                response_type=response_type,
                data=retrieved_data,
                natural_language=_response_text,
                recommendations=recommendations,
                confidence=0.85,
                actions_taken=actions_taken,
            )

        except Exception as e:
            logger.error("Error generating equipment response: %s", e)
            return await self._generate_fallback_response(
                equipment_query.user_query, session_id, str(e)
            )

    def _build_context_string(
        self, conversation_history: List[Dict[str, Any]], context: Optional[Dict[str, Any]]
    ) -> str:
        context_parts = []
        if conversation_history:
            recent = conversation_history[-3:]
            history_str = "\n".join(
                f"Q: {h['query']}\nA: {h.get('response_type', 'equipment_info')}"
                for h in recent
            )
            context_parts.append(f"Recent conversation:\n{history_str}")
        if context:
            context_parts.append(f"Additional context: {json.dumps(context, indent=2)}")
        return "\n\n".join(context_parts) if context_parts else "No additional context"

    def _build_retrieved_context(
        self, retrieved_data: Dict[str, Any], actions_taken: List[Dict[str, Any]]
    ) -> str:
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
        recommendations = []
        for line in response_text.split("\n"):
            line = line.strip()
            if line.startswith(("•", "-", "*", "1.", "2.", "3.")) or "recommend" in line.lower():
                clean_line = line.lstrip("•-*123456789. ").strip()
                if clean_line and len(clean_line) > 10:
                    recommendations.append(clean_line)
        return recommendations[:5]

    async def _generate_fallback_response(
        self, query: str, session_id: str, error: str
    ) -> EquipmentResponse:
        return EquipmentResponse(
            response_type="error",
            data={"error": error},
            natural_language=(
                f"I encountered an error while processing your equipment query: '{query}'. "
                "Please try rephrasing your question or contact support if the issue persists."
            ),
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
