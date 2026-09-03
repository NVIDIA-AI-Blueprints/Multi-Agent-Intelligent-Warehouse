# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Operations Coordination Agent — maiw-agents package.

Migration notes (Phase 9A)
--------------------------
- All src.* imports removed; dependencies are injected at construction time.
- NIM fallback branches removed; only the ModelGateway path is retained.
- task_queries, telemetry_queries injected as Optional[Any].
- sanitize_prompt_input sourced from maiw_agents.common.utils.
- Bootstrap (apps/api/maiw_api/bootstrap.py) creates concrete instances and injects them.

Provides intelligent workforce scheduling, task management, equipment allocation,
and operational KPI tracking for warehouse operations.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..common.utils import sanitize_prompt_input

logger = logging.getLogger(__name__)


@dataclass
class OperationsQuery:
    """Structured operations query."""

    intent: str
    entities: Dict[str, Any]
    context: Dict[str, Any]
    user_query: str


@dataclass
class OperationsResponse:
    """Structured operations response."""

    response_type: str
    data: Dict[str, Any]
    natural_language: str
    recommendations: List[str]
    confidence: float
    actions_taken: List[Dict[str, Any]]


@dataclass
class WorkforceInfo:
    """Workforce information structure."""

    shift: str
    employees: List[Dict[str, Any]]
    total_count: int
    active_tasks: int
    productivity_score: float


@dataclass
class TaskAssignment:
    """Task assignment structure."""

    task_id: int
    assignee: str
    priority: str
    estimated_duration: int
    dependencies: List[str]
    status: str


class OperationsCoordinationAgent:
    """
    Operations Coordination Agent — ModelGateway-only, no src.* imports.

    All heavy runtime dependencies are injected at construction time.
    Bootstrap is responsible for creating and wiring them.
    """

    def __init__(
        self,
        *,
        model_gateway: Optional[Any] = None,
        hybrid_retriever: Optional[Any] = None,
        task_queries: Optional[Any] = None,
        telemetry_queries: Optional[Any] = None,
        action_tools: Optional[Any] = None,
        inventory_skill: Optional[Any] = None,
        equipment_status_skill: Optional[Any] = None,
        equipment_telemetry_skill: Optional[Any] = None,
        config: Optional[Any] = None,
    ) -> None:
        self.model_gateway = model_gateway
        self.hybrid_retriever = hybrid_retriever
        self.task_queries = task_queries
        self.telemetry_queries = telemetry_queries
        self.action_tools = action_tools
        self.inventory_skill = inventory_skill
        self.equipment_status_skill = equipment_status_skill
        self.equipment_telemetry_skill = equipment_telemetry_skill
        self.config = config
        self.conversation_context: Dict[str, Any] = {}

    async def initialize(self) -> None:
        """No-op: all dependencies are injected at construction time."""
        logger.info(
            "OperationsCoordinationAgent.initialize() called — all deps pre-injected."
        )

    async def process_query(
        self,
        query: str,
        session_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
    ) -> OperationsResponse:
        try:
            if session_id not in self.conversation_context:
                self.conversation_context[session_id] = {
                    "history": [],
                    "current_focus": None,
                    "last_entities": {},
                }

            operations_query = await self._understand_query(query, session_id, context)
            retrieved_data = await self._retrieve_operations_data(operations_query)
            actions_taken = await self._execute_action_tools(operations_query, context)
            response = await self._generate_operations_response(
                operations_query, retrieved_data, session_id, actions_taken
            )
            self._update_context(session_id, operations_query, response)
            return response

        except Exception as e:
            logger.error("Failed to process operations query: %s", e)
            return OperationsResponse(
                response_type="error",
                data={"error": str(e)},
                natural_language=f"I encountered an error processing your operations query: {e}",
                recommendations=[],
                confidence=0.0,
                actions_taken=[],
            )

    async def _lookup_inventory_sku(
        self,
        sku: str,
        warehouse_id: str = "default",
        trace_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if self.inventory_skill is None:
            return None
        try:
            from maiw_mcp.contracts.inventory import InventoryLookupRequest

            result = await self.inventory_skill.execute(
                InventoryLookupRequest(warehouse_id=warehouse_id, sku=sku),
                trace_id=trace_id,
            )
            return {
                "sku": result.sku,
                "name": result.name,
                "total_available": result.total_available,
                "is_low_stock": result.is_low_stock,
                "locations": [
                    {
                        "location_id": loc.location_id,
                        "quantity_available": loc.quantity_available,
                        "reorder_point": loc.reorder_point,
                    }
                    for loc in result.locations
                ],
                "observed_at": result.observed_at.isoformat(),
            }
        except Exception as exc:
            logger.warning(
                "OperationsAgent: inventory skill call failed for SKU=%s: %s", sku, exc
            )
            return None

    async def _get_equipment_status(
        self,
        asset_id: Optional[str] = None,
        equipment_type: Optional[str] = None,
        zone: Optional[str] = None,
        status_filter: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if self.equipment_status_skill is None:
            return None
        try:
            from maiw_mcp.contracts.equipment import EquipmentStatusRequest

            result = await self.equipment_status_skill.execute(
                EquipmentStatusRequest(
                    asset_id=asset_id,
                    equipment_type=equipment_type,
                    zone=zone,
                    status_filter=status_filter,
                ),
                trace_id=trace_id,
            )
            return {
                "equipment": [
                    {
                        "asset_id": a.asset_id,
                        "equipment_type": a.equipment_type,
                        "model": a.model,
                        "zone": a.zone,
                        "status": a.status,
                        "owner_user": a.owner_user,
                    }
                    for a in result.equipment
                ],
                "summary": result.summary,
                "total_count": result.total_count,
            }
        except Exception as exc:
            logger.warning(
                "OperationsAgent: equipment status skill call failed: %s", exc
            )
            return None

    async def _get_equipment_telemetry(
        self,
        asset_id: str,
        metric: Optional[str] = None,
        hours_back: int = 24,
        trace_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if self.equipment_telemetry_skill is None:
            return None
        try:
            from maiw_mcp.contracts.equipment import EquipmentTelemetryRequest

            result = await self.equipment_telemetry_skill.execute(
                EquipmentTelemetryRequest(
                    asset_id=asset_id,
                    metric=metric,
                    hours_back=hours_back,
                ),
                trace_id=trace_id,
            )
            return {
                "asset_id": result.asset_id,
                "data_points": result.data_points,
                "hours_back": result.hours_back,
                "telemetry_data": [
                    {
                        "timestamp": p.timestamp.isoformat(),
                        "metric": p.metric,
                        "value": p.value,
                        "unit": p.unit,
                    }
                    for p in result.telemetry_data
                ],
                "available_metrics": [
                    {"metric": m.metric, "unit": m.unit}
                    for m in result.available_metrics
                ],
            }
        except Exception as exc:
            logger.warning(
                "OperationsAgent: equipment telemetry skill call failed for %s: %s",
                asset_id,
                exc,
            )
            return None

    async def _understand_query(
        self, query: str, session_id: str, context: Optional[Dict[str, Any]]
    ) -> OperationsQuery:
        try:
            conversation_history = self.conversation_context.get(session_id, {}).get(
                "history", []
            )
            context_str = self._build_context_string(conversation_history, context)

            safe_query = sanitize_prompt_input(query)
            safe_context = sanitize_prompt_input(context_str)

            understanding_prompt_template = self.config.persona.understanding_prompt
            system_prompt = self.config.persona.system_prompt
            prompt = understanding_prompt_template.format(
                query=safe_query, context=safe_context
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]

            from maiw_models import ModelRequest, ReasoningLevel, RiskLevel

            gw_resp = await self.model_gateway.generate(
                ModelRequest(
                    task="warehouse.operations.understand_query",
                    messages=messages,
                    reasoning=ReasoningLevel.LOW,
                    risk_level=RiskLevel.LOW,
                    temperature=0.1,
                )
            )
            response_content = gw_resp.content

            try:
                parsed_response = json.loads(response_content)
                return OperationsQuery(
                    intent=parsed_response.get("intent", "general"),
                    entities=parsed_response.get("entities", {}),
                    context=parsed_response.get("context", {}),
                    user_query=query,
                )
            except json.JSONDecodeError:
                return self._fallback_intent_detection(query)

        except Exception as e:
            logger.error("Query understanding failed: %s", e)
            return self._fallback_intent_detection(query)

    def _fallback_intent_detection(self, query: str) -> OperationsQuery:
        query_lower = query.lower()

        if any(
            word in query_lower
            for word in [
                "shift",
                "workforce",
                "employee",
                "staff",
                "team",
                "worker",
                "workers",
                "active workers",
                "how many",
            ]
        ):
            intent = "workforce"
        elif any(
            word in query_lower for word in ["assign", "task assignment", "assign task"]
        ):
            intent = "task_assignment"
        elif any(word in query_lower for word in ["rebalance", "workload", "balance"]):
            intent = "workload_rebalance"
        elif any(
            word in query_lower for word in ["wave", "pick wave", "generate wave"]
        ):
            intent = "pick_wave"
        elif any(
            word in query_lower for word in ["optimize", "path", "route", "efficiency"]
        ):
            intent = "optimize_paths"
        elif any(
            word in query_lower
            for word in ["shift management", "manage shift", "schedule shift"]
        ):
            intent = "shift_management"
        elif any(word in query_lower for word in ["dock", "appointment", "scheduling"]):
            intent = "dock_scheduling"
        elif any(
            word in query_lower
            for word in ["dispatch", "equipment dispatch", "send equipment"]
        ):
            intent = "equipment_dispatch"
        elif any(
            word in query_lower for word in ["publish", "kpi", "metrics", "dashboard"]
        ):
            intent = "publish_kpis"
        elif any(
            word in query_lower
            for word in [
                "task",
                "tasks",
                "work",
                "job",
                "pick",
                "pack",
                "latest",
                "pending",
                "in progress",
                "assignment",
                "assignments",
            ]
        ):
            intent = "task_management"
        elif any(
            word in query_lower
            for word in ["equipment", "forklift", "conveyor", "machine"]
        ):
            intent = "equipment"
        elif any(word in query_lower for word in ["performance", "productivity"]):
            intent = "kpi"
        elif any(word in query_lower for word in ["schedule", "planning", "roster"]):
            intent = "scheduling"
        else:
            intent = "general"

        return OperationsQuery(intent=intent, entities={}, context={}, user_query=query)

    async def _retrieve_operations_data(
        self, operations_query: OperationsQuery
    ) -> Dict[str, Any]:
        try:
            data: Dict[str, Any] = {}

            if self.task_queries:
                task_summary = await self.task_queries.get_task_summary()
                data["task_summary"] = task_summary

            if operations_query.intent == "task_management" and self.task_queries:
                pending_tasks = await self.task_queries.get_tasks_by_status(
                    "pending", limit=20
                )
                in_progress_tasks = await self.task_queries.get_tasks_by_status(
                    "in_progress", limit=20
                )
                data["pending_tasks"] = [asdict(task) for task in pending_tasks]
                data["in_progress_tasks"] = [asdict(task) for task in in_progress_tasks]

            if operations_query.intent == "equipment" and self.telemetry_queries:
                equipment_health = (
                    await self.telemetry_queries.get_equipment_health_status()
                )
                data["equipment_health"] = equipment_health

            if operations_query.intent == "workforce":
                data["workforce_info"] = self._simulate_workforce_data()

            return data

        except Exception as e:
            logger.error("Operations data retrieval failed: %s", e)
            return {"error": str(e)}

    async def _execute_action_tools(
        self, operations_query: OperationsQuery, context: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        actions_taken: List[Dict[str, Any]] = []

        try:
            if not self.action_tools:
                return actions_taken

            task_type = operations_query.entities.get("task_type")
            quantity = operations_query.entities.get("quantity", 0)
            constraints = operations_query.entities.get("constraints", {})
            assignees = operations_query.entities.get("assignees")
            order_ids = operations_query.entities.get("order_ids", [])
            wave_strategy = operations_query.entities.get("wave_strategy", "zone_based")
            shift_id = operations_query.entities.get("shift_id")
            action = operations_query.entities.get("action")
            workers = operations_query.entities.get("workers")
            equipment_id = operations_query.entities.get("equipment_id")
            task_id = operations_query.entities.get("task_id")

            if operations_query.intent == "task_assignment":
                if not task_type:
                    if "pick" in operations_query.user_query.lower():
                        task_type = "pick"
                    elif "pack" in operations_query.user_query.lower():
                        task_type = "pack"
                    elif "receive" in operations_query.user_query.lower():
                        task_type = "receive"
                    else:
                        task_type = "general"

                if not quantity:
                    qty_matches = re.findall(r"\b(\d+)\b", operations_query.user_query)
                    quantity = int(qty_matches[0]) if qty_matches else 1

                if task_type and quantity:
                    assignment = await self.action_tools.assign_tasks(
                        task_type=task_type,
                        quantity=quantity,
                        constraints=constraints,
                        assignees=assignees,
                    )
                    actions_taken.append(
                        {
                            "action": "assign_tasks",
                            "task_type": task_type,
                            "quantity": quantity,
                            "result": asdict(assignment),
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

            elif operations_query.intent == "workload_rebalance":
                rebalance = await self.action_tools.rebalance_workload(
                    sla_rules=operations_query.entities.get("sla_rules")
                )
                actions_taken.append(
                    {
                        "action": "rebalance_workload",
                        "result": asdict(rebalance),
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif operations_query.intent == "pick_wave":
                if not order_ids:
                    order_matches = re.findall(r"ORD\d+", operations_query.user_query)
                    if order_matches:
                        order_ids = order_matches
                    else:
                        line_count_match = re.search(
                            r"(\d{1,5})-line order", operations_query.user_query
                        )
                        zone_match = re.search(
                            r"Zone ([A-Z])", operations_query.user_query
                        )
                        if line_count_match and zone_match:
                            order_id = f"ORD_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                            order_ids = [order_id]
                        else:
                            order_ids = [
                                f"ORD_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                            ]

                if order_ids:
                    pick_wave = await self.action_tools.generate_pick_wave(
                        order_ids=order_ids, wave_strategy=wave_strategy
                    )
                    actions_taken.append(
                        {
                            "action": "generate_pick_wave",
                            "order_ids": order_ids,
                            "result": asdict(pick_wave),
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

            elif (
                operations_query.intent == "optimize_paths"
                and operations_query.entities.get("picker_id")
            ):
                optimization = await self.action_tools.optimize_pick_paths(
                    picker_id=operations_query.entities.get("picker_id"),
                    wave_id=operations_query.entities.get("wave_id"),
                )
                actions_taken.append(
                    {
                        "action": "optimize_pick_paths",
                        "picker_id": operations_query.entities.get("picker_id"),
                        "result": asdict(optimization),
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif operations_query.intent == "shift_management" and shift_id and action:
                shift_schedule = await self.action_tools.manage_shift_schedule(
                    shift_id=shift_id,
                    action=action,
                    workers=workers,
                    swaps=operations_query.entities.get("swaps"),
                )
                actions_taken.append(
                    {
                        "action": "manage_shift_schedule",
                        "shift_id": shift_id,
                        "result": asdict(shift_schedule),
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif (
                operations_query.intent == "dock_scheduling"
                and operations_query.entities.get("appointments")
            ):
                appointments = await self.action_tools.dock_scheduling(
                    appointments=operations_query.entities.get("appointments", []),
                    capacity=operations_query.entities.get("capacity", {}),
                )
                actions_taken.append(
                    {
                        "action": "dock_scheduling",
                        "appointments_count": len(appointments),
                        "result": [asdict(apt) for apt in appointments],
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif operations_query.intent == "equipment_dispatch" and equipment_id:
                if not task_id:
                    task_id = f"TASK_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                dispatch = await self.action_tools.dispatch_equipment(
                    equipment_id=equipment_id,
                    task_id=task_id,
                    operator=operations_query.entities.get("operator"),
                )
                actions_taken.append(
                    {
                        "action": "dispatch_equipment",
                        "equipment_id": equipment_id,
                        "task_id": task_id,
                        "result": asdict(dispatch),
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif operations_query.intent == "publish_kpis":
                kpi_result = await self.action_tools.publish_kpis(
                    metrics=operations_query.entities.get("metrics")
                )
                actions_taken.append(
                    {
                        "action": "publish_kpis",
                        "result": kpi_result,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            return actions_taken

        except Exception as e:
            logger.error("Action tools execution failed: %s", e)
            return [
                {
                    "action": "error",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
            ]

    def _simulate_workforce_data(self) -> Dict[str, Any]:
        return {
            "shifts": {
                "morning": {
                    "start_time": "06:00",
                    "end_time": "14:00",
                    "employees": [
                        {"name": "John Smith", "role": "Picker", "status": "active"},
                        {"name": "Sarah Johnson", "role": "Packer", "status": "active"},
                        {
                            "name": "Mike Wilson",
                            "role": "Forklift Operator",
                            "status": "active",
                        },
                    ],
                    "total_count": 3,
                    "active_tasks": 8,
                },
                "afternoon": {
                    "start_time": "14:00",
                    "end_time": "22:00",
                    "employees": [
                        {"name": "Lisa Brown", "role": "Picker", "status": "active"},
                        {"name": "David Lee", "role": "Packer", "status": "active"},
                        {"name": "Amy Chen", "role": "Supervisor", "status": "active"},
                    ],
                    "total_count": 3,
                    "active_tasks": 6,
                },
            },
            "productivity_metrics": {
                "picks_per_hour": 45.2,
                "packages_per_hour": 38.7,
                "accuracy_rate": 98.5,
            },
        }

    async def _generate_operations_response(
        self,
        operations_query: OperationsQuery,
        retrieved_data: Dict[str, Any],
        session_id: str,
        actions_taken: Optional[List[Dict[str, Any]]] = None,
    ) -> OperationsResponse:
        try:
            context_str = self._build_retrieved_context(retrieved_data)
            conversation_history = self.conversation_context.get(session_id, {}).get(
                "history", []
            )

            actions_str = ""
            if actions_taken:
                actions_str = f"\nActions Taken:\n{json.dumps(actions_taken, indent=2, default=str)}"

            safe_user_query = sanitize_prompt_input(operations_query.user_query)
            safe_intent = sanitize_prompt_input(operations_query.intent)
            safe_entities = sanitize_prompt_input(operations_query.entities)

            dispatch_instructions = ""
            if safe_intent == "equipment_dispatch":
                dispatch_instructions = (
                    "\nIMPORTANT FOR EQUIPMENT DISPATCH:\n"
                    "- If the dispatch status is 'dispatched' or 'pending', the operation was SUCCESSFUL\n"
                    "- Only report errors if the dispatch status is 'error' AND there's an explicit error message\n"
                    "- When dispatch is successful, provide a positive confirmation message\n"
                    "- Include equipment ID, destination zone, and operation type in the response\n"
                    "- If task was created and equipment assigned, confirm both actions were successful\n"
                )

            response_prompt_template = self.config.persona.response_prompt
            system_prompt = self.config.persona.system_prompt

            prompt = response_prompt_template.format(
                user_query=safe_user_query,
                intent=safe_intent,
                entities=safe_entities,
                retrieved_data=context_str,
                actions_taken=actions_str,
                conversation_history=(
                    conversation_history[-3:] if conversation_history else "None"
                ),
                dispatch_instructions=dispatch_instructions,
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]

            from maiw_models import ModelRequest, ReasoningLevel, RiskLevel

            _is_high_risk = operations_query.intent in {
                "pick_wave",
                "workload_rebalance",
                "shift_management",
            }
            _risk = RiskLevel.HIGH if _is_high_risk else RiskLevel.LOW

            gw_resp = await self.model_gateway.generate(
                ModelRequest(
                    task="warehouse.operations.generate_response",
                    messages=messages,
                    reasoning=ReasoningLevel.MEDIUM,
                    risk_level=_risk,
                    temperature=0.2,
                )
            )
            response_content = gw_resp.content

            try:
                parsed_response = json.loads(response_content)
                return OperationsResponse(
                    response_type=parsed_response.get("response_type", "general"),
                    data=parsed_response.get("data", {}),
                    natural_language=parsed_response.get(
                        "natural_language", "I processed your operations query."
                    ),
                    recommendations=parsed_response.get("recommendations", []),
                    confidence=parsed_response.get("confidence", 0.8),
                    actions_taken=actions_taken or [],
                )
            except json.JSONDecodeError:
                return self._generate_fallback_response(
                    operations_query, retrieved_data, actions_taken
                )

        except Exception as e:
            logger.error("Response generation failed: %s", e)
            return self._generate_fallback_response(
                operations_query, retrieved_data, actions_taken
            )

    def _generate_fallback_response(
        self,
        operations_query: OperationsQuery,
        retrieved_data: Dict[str, Any],
        actions_taken: Optional[List[Dict[str, Any]]] = None,
    ) -> OperationsResponse:
        try:
            intent = operations_query.intent
            data = retrieved_data

            if intent == "workforce":
                workforce_info = data.get("workforce_info", {})
                shifts = workforce_info.get("shifts", {})
                total_workers = 0
                shift_details = []
                for shift_name, shift_data in shifts.items():
                    shift_count = shift_data.get("total_count", 0)
                    total_workers += shift_count
                    shift_details.append(
                        f"{shift_name.title()} shift: {shift_count} workers"
                    )
                natural_language = (
                    f"Currently, we have **{total_workers} active workers** across all shifts:\n\n"
                    + "\n".join(shift_details)
                )
                if workforce_info.get("productivity_metrics"):
                    metrics = workforce_info["productivity_metrics"]
                    natural_language += (
                        f"\n\n**Productivity Metrics:**\n"
                        f"- Picks per hour: {metrics.get('picks_per_hour', 0)}\n"
                        f"- Packages per hour: {metrics.get('packages_per_hour', 0)}\n"
                        f"- Accuracy rate: {metrics.get('accuracy_rate', 0)}%"
                    )
                recommendations = [
                    "Monitor shift productivity metrics",
                    "Consider cross-training employees for flexibility",
                    "Ensure adequate coverage during peak hours",
                ]
                response_data = {
                    "total_active_workers": total_workers,
                    "shifts": shifts,
                    "productivity_metrics": workforce_info.get(
                        "productivity_metrics", {}
                    ),
                }

            elif intent == "task_management":
                task_summary = data.get("task_summary", {})
                pending_tasks = data.get("pending_tasks", [])
                in_progress_tasks = data.get("in_progress_tasks", [])

                natural_language = "Here's the current task status and assignments:\n\n"
                if task_summary:
                    natural_language += (
                        f"**Task Summary:**\n"
                        f"- Total Tasks: {task_summary.get('total_tasks', 0)}\n"
                        f"- Pending: {task_summary.get('pending_tasks', 0)}\n"
                        f"- In Progress: {task_summary.get('in_progress_tasks', 0)}\n"
                        f"- Completed: {task_summary.get('completed_tasks', 0)}\n\n"
                    )
                    tasks_by_kind = task_summary.get("tasks_by_kind", [])
                    if tasks_by_kind:
                        natural_language += "**Tasks by Type:**\n"
                        for task_kind in tasks_by_kind:
                            natural_language += f"- {task_kind.get('kind', 'Unknown').title()}: {task_kind.get('count', 0)}\n"
                        natural_language += "\n"

                if pending_tasks:
                    natural_language += f"**Pending Tasks ({len(pending_tasks)}):**\n"
                    for i, task in enumerate(pending_tasks[:5], 1):
                        task_id = task.get("id", "N/A")
                        task_kind = task.get("kind", "Unknown")
                        priority = (
                            task.get("payload", {}).get("priority", "medium")
                            if isinstance(task.get("payload"), dict)
                            else "medium"
                        )
                        zone = (
                            task.get("payload", {}).get("zone", "N/A")
                            if isinstance(task.get("payload"), dict)
                            else "N/A"
                        )
                        natural_language += f"{i}. {task_kind.title()} (ID: {task_id}, Priority: {priority}, Zone: {zone})\n"
                    if len(pending_tasks) > 5:
                        natural_language += (
                            f"... and {len(pending_tasks) - 5} more pending tasks\n"
                        )
                    natural_language += "\n"

                if in_progress_tasks:
                    natural_language += (
                        f"**In Progress Tasks ({len(in_progress_tasks)}):**\n"
                    )
                    for i, task in enumerate(in_progress_tasks[:5], 1):
                        task_id = task.get("id", "N/A")
                        task_kind = task.get("kind", "Unknown")
                        assignee = task.get("assignee", "Unassigned")
                        priority = (
                            task.get("payload", {}).get("priority", "medium")
                            if isinstance(task.get("payload"), dict)
                            else "medium"
                        )
                        zone = (
                            task.get("payload", {}).get("zone", "N/A")
                            if isinstance(task.get("payload"), dict)
                            else "N/A"
                        )
                        natural_language += f"{i}. {task_kind.title()} (ID: {task_id}, Assigned to: {assignee}, Priority: {priority}, Zone: {zone})\n"
                    if len(in_progress_tasks) > 5:
                        natural_language += f"... and {len(in_progress_tasks) - 5} more in-progress tasks\n"

                recommendations = [
                    "Prioritize urgent tasks",
                    "Balance workload across team members",
                    "Monitor task completion rates",
                    "Review task assignments for efficiency",
                ]
                response_data = {
                    "task_summary": task_summary,
                    "pending_tasks": pending_tasks,
                    "in_progress_tasks": in_progress_tasks,
                    "total_pending": len(pending_tasks),
                    "total_in_progress": len(in_progress_tasks),
                }

            elif intent == "pick_wave":
                natural_language = "Pick wave generation completed successfully!\n\n"
                pick_wave_data = None
                for action in actions_taken or []:
                    if action.get("action") == "generate_pick_wave":
                        pick_wave_data = action.get("result")
                        break

                if pick_wave_data:
                    wave_id = pick_wave_data.get("wave_id", "Unknown")
                    order_ids_list = pick_wave_data.get("order_ids", [])
                    total_lines = pick_wave_data.get("total_lines", 0)
                    zones = pick_wave_data.get("zones", [])
                    assigned_pickers = pick_wave_data.get("assigned_pickers", [])
                    estimated_duration = pick_wave_data.get(
                        "estimated_duration", "Unknown"
                    )
                    natural_language += (
                        f"**Wave Details:**\n"
                        f"- Wave ID: {wave_id}\n"
                        f"- Orders: {', '.join(order_ids_list)}\n"
                        f"- Total Lines: {total_lines}\n"
                        f"- Zones: {', '.join(zones) if zones else 'All zones'}\n"
                        f"- Assigned Pickers: {len(assigned_pickers)} pickers\n"
                        f"- Estimated Duration: {estimated_duration}\n"
                    )
                    natural_language += (
                        f"\n**Status:** {pick_wave_data.get('status', 'Generated')}\n"
                    )
                    recommendations = [
                        "Monitor pick wave progress",
                        "Ensure all pickers have necessary equipment",
                        "Track completion against estimated duration",
                    ]
                    response_data = {
                        "wave_id": wave_id,
                        "total_lines": total_lines,
                        "zones": zones,
                        "estimated_duration": estimated_duration,
                        "status": pick_wave_data.get("status", "Generated"),
                    }
                else:
                    natural_language += "Pick wave generation is in progress."
                    recommendations = ["Monitor wave generation progress"]
                    response_data = {"status": "in_progress"}

            elif intent == "equipment_dispatch":
                natural_language = ""
                dispatch_data = None
                for action in actions_taken or []:
                    if action.get("action") == "dispatch_equipment":
                        dispatch_data = action.get("result", {})
                        break

                if dispatch_data:
                    equipment_id = dispatch_data.get("equipment_id", "Unknown")
                    task_id = dispatch_data.get("task_id", "Unknown")
                    status = dispatch_data.get("status", "unknown")
                    location = dispatch_data.get("location", "Unknown")
                    operator = dispatch_data.get("assigned_operator", "Unknown")
                    if status in ["dispatched", "pending"]:
                        natural_language = (
                            f"Forklift {equipment_id} has been successfully dispatched to {location} for pick operations. "
                            f"The task has been created (Task ID: {task_id}) and assigned to operator {operator}."
                        )
                        recommendations = [
                            f"Monitor forklift {equipment_id} progress in {location}",
                            "Track task completion status",
                        ]
                    elif status == "error":
                        natural_language = f"The system encountered an error dispatching forklift {equipment_id} to {location}."
                        recommendations = [
                            f"Verify equipment {equipment_id} is available"
                        ]
                    else:
                        natural_language = f"Forklift {equipment_id} dispatch to {location} is being processed (status: {status})."
                        recommendations = [
                            f"Monitor dispatch status for {equipment_id}"
                        ]
                    response_data = {
                        "equipment_id": equipment_id,
                        "task_id": task_id,
                        "zone": location,
                        "status": status,
                        "operator": operator,
                    }
                else:
                    natural_language = (
                        "Equipment dispatch request received. Processing..."
                    )
                    recommendations = ["Monitor dispatch progress"]
                    response_data = {"status": "processing"}

            elif intent == "equipment":
                natural_language = (
                    "Here's the current equipment status and health information."
                )
                recommendations = [
                    "Schedule preventive maintenance",
                    "Monitor equipment performance",
                ]
                response_data = data
            elif intent == "kpi":
                natural_language = (
                    "Here are the current operational KPIs and performance metrics."
                )
                recommendations = [
                    "Focus on accuracy improvements",
                    "Optimize workflow efficiency",
                ]
                response_data = data
            else:
                natural_language = "I processed your operations query and retrieved relevant information."
                recommendations = [
                    "Review operational procedures",
                    "Monitor performance metrics",
                ]
                response_data = data

            return OperationsResponse(
                response_type="fallback",
                data=response_data,
                natural_language=natural_language,
                recommendations=recommendations,
                confidence=0.6,
                actions_taken=actions_taken or [],
            )

        except Exception as e:
            logger.error("Fallback response generation failed: %s", e)
            return OperationsResponse(
                response_type="error",
                data={"error": str(e)},
                natural_language="I encountered an error processing your request.",
                recommendations=[],
                confidence=0.0,
                actions_taken=actions_taken or [],
            )

    def _build_context_string(
        self,
        conversation_history: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
    ) -> str:
        if not conversation_history and not context:
            return "No previous context"
        context_parts = []
        if conversation_history:
            context_parts.append(f"Recent conversation: {conversation_history[-3:]}")
        if context:
            context_parts.append(f"Additional context: {context}")
        return "; ".join(context_parts)

    def _build_retrieved_context(self, retrieved_data: Dict[str, Any]) -> str:
        try:
            context_parts = []

            if "task_summary" in retrieved_data:
                ts = retrieved_data["task_summary"]
                ctx = (
                    f"Task Summary:\n"
                    f"- Total Tasks: {ts.get('total_tasks', 0)}\n"
                    f"- Pending: {ts.get('pending_tasks', 0)}\n"
                    f"- In Progress: {ts.get('in_progress_tasks', 0)}\n"
                    f"- Completed: {ts.get('completed_tasks', 0)}\n"
                )
                for tk in ts.get("tasks_by_kind", []):
                    ctx += f"  - {tk.get('kind', 'Unknown').title()}: {tk.get('count', 0)}\n"
                context_parts.append(ctx)

            if "pending_tasks" in retrieved_data:
                pending = retrieved_data["pending_tasks"]
                if pending:
                    ctx = f"Pending Tasks ({len(pending)}):\n"
                    for i, task in enumerate(pending[:3], 1):
                        task_id = task.get("id", "N/A")
                        priority = (
                            task.get("payload", {}).get("priority", "medium")
                            if isinstance(task.get("payload"), dict)
                            else "medium"
                        )
                        ctx += f"{i}. {task.get('kind', 'Unknown').title()} (ID: {task_id}, Priority: {priority})\n"
                    if len(pending) > 3:
                        ctx += f"... and {len(pending) - 3} more\n"
                    context_parts.append(ctx)

            if "in_progress_tasks" in retrieved_data:
                in_prog = retrieved_data["in_progress_tasks"]
                if in_prog:
                    ctx = f"In Progress Tasks ({len(in_prog)}):\n"
                    for i, task in enumerate(in_prog[:3], 1):
                        task_id = task.get("id", "N/A")
                        assignee = task.get("assignee", "Unassigned")
                        ctx += f"{i}. {task.get('kind', 'Unknown').title()} (ID: {task_id}, Assigned to: {assignee})\n"
                    if len(in_prog) > 3:
                        ctx += f"... and {len(in_prog) - 3} more\n"
                    context_parts.append(ctx)

            if "workforce_info" in retrieved_data:
                wf = retrieved_data["workforce_info"]
                shifts = wf.get("shifts", {})
                total = sum(s.get("total_count", 0) for s in shifts.values())
                ctx = f"Workforce Info:\n- Total Active Workers: {total}\n"
                for shift_name, shift_data in shifts.items():
                    ctx += f"- {shift_name.title()} Shift: {shift_data.get('total_count', 0)} workers\n"
                context_parts.append(ctx)

            if "equipment_health" in retrieved_data:
                context_parts.append(
                    f"Equipment Health: {retrieved_data['equipment_health']}"
                )

            return (
                "\n".join(context_parts) if context_parts else "No relevant data found"
            )

        except Exception as e:
            logger.error("Context building failed: %s", e)
            return "Error building context"

    def _update_context(
        self,
        session_id: str,
        operations_query: OperationsQuery,
        response: OperationsResponse,
    ) -> None:
        try:
            if session_id not in self.conversation_context:
                self.conversation_context[session_id] = {
                    "history": [],
                    "current_focus": None,
                    "last_entities": {},
                }

            self.conversation_context[session_id]["history"].append(
                {
                    "query": operations_query.user_query,
                    "intent": operations_query.intent,
                    "response_type": response.response_type,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            if operations_query.intent != "general":
                self.conversation_context[session_id][
                    "current_focus"
                ] = operations_query.intent

            if operations_query.entities:
                self.conversation_context[session_id][
                    "last_entities"
                ] = operations_query.entities

            if len(self.conversation_context[session_id]["history"]) > 10:
                self.conversation_context[session_id]["history"] = (
                    self.conversation_context[session_id]["history"][-10:]
                )

        except Exception as e:
            logger.error("Context update failed: %s", e)

    async def get_conversation_context(self, session_id: str) -> Dict[str, Any]:
        return self.conversation_context.get(
            session_id, {"history": [], "current_focus": None, "last_entities": {}}
        )

    async def clear_conversation_context(self, session_id: str) -> None:
        if session_id in self.conversation_context:
            del self.conversation_context[session_id]

    async def analyze_disruption(
        self,
        *,
        snapshot: Any,
        scenario_context: str = "",
        trace_id: str,
        deadline: Any = None,
        reasoning_level: Any = None,
        risk_level: Any = None,
    ) -> Any:
        """
        Observe warehouse state and produce an OperationalAssessment.

        Parameters
        ----------
        snapshot:
            Sealed WarehouseStateSnapshot — the ONLY source of truth for this call.
            This method never accesses DemoWarehouseWorld or SimulationProviders.
        scenario_context:
            One-sentence human hint (e.g. "equipment_failure scenario active").
        trace_id:
            Caller-supplied correlation ID propagated through the full lifecycle.

        Returns
        -------
        OperationalAssessment
        """
        from maiw_models import ModelRequest, ReasoningLevel, RiskLevel
        from .assessment_prompt import build_analyze_disruption_prompt
        from ..assessment import OperationalAssessment, RecommendedAction

        state = snapshot.state
        warehouse_id = snapshot.warehouse_id
        snapshot_id = snapshot.snapshot_id

        # Build structured facts from the sealed snapshot
        facts: list[str] = []
        domains_affected: list[str] = []

        if state.equipment is not None:
            eq = state.equipment
            facts.append(
                f"Equipment: {eq.total_count} total, {eq.available_count} available"
            )
            offline = [a for a in eq.assets if a.status == "offline"]
            maintenance = [a for a in eq.assets if a.status == "maintenance"]
            if offline:
                facts.append(
                    f"OFFLINE assets: {', '.join(a.asset_id for a in offline)}"
                )
                domains_affected.append("equipment")
            if maintenance:
                facts.append(
                    f"MAINTENANCE assets: {', '.join(a.asset_id for a in maintenance)}"
                )
                if "equipment" not in domains_affected:
                    domains_affected.append("equipment")

        if state.labor is not None:
            lb = state.labor
            # available_workers = idle (active + no current task) per LaborCapacityResult
            facts.append(
                f"Labor: {lb.total_workers} total, {lb.available_workers} idle (active with no task), "
                f"{lb.utilization_pct:.0f}% utilization"
            )
            if lb.utilization_pct > 85 or lb.available_workers < 2:
                domains_affected.append("labor")

        if state.waves is not None:
            wv = state.waves
            facts.append(
                f"Wave tasks: {wv.total_tasks} total, {wv.pending_count} pending, "
                f"{wv.in_progress_count} in_progress, {wv.at_risk_count} at-risk"
            )
            if wv.at_risk_count > 0:
                domains_affected.append("wave")

            # Surface the soonest carrier cutoff so the model knows deadline pressure.
            deadlines = sorted(
                t.deadline for t in wv.tasks if getattr(t, "deadline", None)
            )
            if deadlines:
                facts.append(f"Carrier cutoff (soonest deadline): {deadlines[0]}")

            # Explicitly surface unassigned pending tasks so the model knows
            # labor.allocate (not wave.reprioritize) is the correct remedy.
            unassigned = [
                t for t in wv.tasks if t.status == "pending" and t.assigned_to is None
            ]
            if unassigned:
                # available_workers here is the corrected idle count from the labor provider
                idle_workers = state.labor.available_workers if state.labor else 0
                facts.append(
                    f"UNASSIGNED PENDING TASKS: {len(unassigned)} pending wave tasks have no worker "
                    f"allocated (assigned_to=null); {idle_workers} workers are idle. "
                    f"Use warehouse.labor.allocate to assign workers to these tasks."
                )
                if "labor" not in domains_affected:
                    domains_affected.append("labor")

        # Deterministic severity from observable state — computed here so both
        # the stub path (no ModelGateway) and the real path use the same score.
        _risk_score = 0
        if state.waves is not None and state.waves.at_risk_count > 0:
            _risk_score += 50
        if state.labor is not None and state.labor.available_workers < 2:
            _risk_score += 30
        elif state.labor is not None and state.labor.utilization_pct > 85:
            _risk_score += 20
        if state.equipment is not None and any(
            a.status == "offline" for a in state.equipment.assets
        ):
            _risk_score += 25
        # Labor allocation failure: high pending backlog + idle workers is a HIGH
        # operational risk even when at_risk_count==0 (no tasks formally flagged).
        if state.waves is not None and state.labor is not None:
            _pending = getattr(state.waves, "pending_count", 0) or 0
            _idle = state.labor.available_workers
            if _pending >= 10 and _idle > 0:
                _risk_score += 60
            elif _pending > 0 and _idle > 0:
                _risk_score += 30
        if _risk_score >= 90:
            _deterministic_severity = "critical"
        elif _risk_score >= 60:
            _deterministic_severity = "high"
        elif _risk_score >= 30:
            _deterministic_severity = "medium"
        else:
            _deterministic_severity = "low"

        # Build system + user messages
        system_msg, user_msg = build_analyze_disruption_prompt(
            facts=facts,
            scenario_context=scenario_context,
            snapshot_id=snapshot_id,
            warehouse_id=warehouse_id,
        )

        if self.model_gateway is None:
            logger.warning(
                "analyze_disruption: ModelGateway not available; returning stub assessment"
            )
            return OperationalAssessment(
                trace_id=trace_id,
                snapshot_id=snapshot_id,
                warehouse_id=warehouse_id,
                summary="ModelGateway unavailable — assessment skipped.",
                severity=_deterministic_severity,
                domains_affected=domains_affected,
                facts_observed=facts,
                skills_consulted=[],
                recommendations=[],
                model_id="none",
                routing_rule="none",
                routing_reason="ModelGateway not wired",
                latency_ms=0.0,
            )

        _reasoning = reasoning_level if reasoning_level is not None else ReasoningLevel.HIGH
        _risk = risk_level if risk_level is not None else RiskLevel.HIGH

        response = await self.model_gateway.generate(
            ModelRequest(
                task="warehouse.operations.analyze_disruption",
                messages=[
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                reasoning=_reasoning,
                risk_level=_risk,
                trace_id=trace_id,
                deadline=deadline,
            )
        )

        # Parse structured response — expect JSON
        import json as _json

        parsed: dict = {}
        try:
            parsed = _json.loads(response.content)
        except Exception:
            # Attempt to extract JSON block if wrapped in markdown
            import re as _re

            m = _re.search(
                r"```(?:json)?\s*(\{.*?\})\s*```", response.content, _re.DOTALL
            )
            if m:
                try:
                    parsed = _json.loads(m.group(1))
                except Exception:
                    pass

        summary = parsed.get("summary", "Assessment produced — see facts_observed.")
        # Use the deterministic severity computed before the model call.
        severity = _deterministic_severity
        raw_recs = parsed.get("recommendations", [])

        recommendations: list[RecommendedAction] = []
        for r in raw_recs:
            try:
                recommendations.append(RecommendedAction(**r))
            except Exception as exc:
                logger.warning(
                    "analyze_disruption: skipping malformed recommendation %s: %s",
                    r,
                    exc,
                )

        rd = response.route_decision
        return OperationalAssessment(
            trace_id=trace_id,
            snapshot_id=snapshot_id,
            warehouse_id=warehouse_id,
            summary=summary,
            severity=severity,
            domains_affected=domains_affected or parsed.get("domains_affected", []),
            facts_observed=facts,
            skills_consulted=parsed.get("skills_consulted", []),
            recommendations=recommendations,
            model_id=response.model_id,
            routing_rule=rd.routing_rule,
            routing_reason=rd.routing_reason,
            requested_role=rd.requested_role,
            selected_role=rd.selected_role,
            fallback_from=rd.fallback_from,
            fallback_reason=rd.fallback_reason,
            latency_ms=response.latency_ms,
        )
