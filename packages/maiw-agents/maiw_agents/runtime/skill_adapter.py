# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW Skill → Deep Agents tool adapter — Phase 19A.

Maps MAIW skills from SKILL_REGISTRY to "tool" objects that the
DeepAgentsRuntime can call. Enforces the MAIW skill access policy:

    ALLOWED for Deep Agents:
        READ            — reads operational state, no mutation
        ANALYTICAL      — analysis over read data, no mutation

    CONDITIONAL (not exposed by default — must be explicitly opted in):
        PROPOSAL        — builds ActionProposal (governance-required output)

    NEVER EXPOSED to Deep Agents:
        WRITE           — must flow through MAIW governance boundary
        EMERGENCY_WRITE — must flow through MAIW governance boundary

Architecture:
    SKILL_REGISTRY → MAIWSkillAdapter → callable tools → DeepAgentsRuntime
                                         ↑
                              Blocked: WRITE, EMERGENCY_WRITE

Each tool is a simple callable that:
    - Invokes the real skill implementation (if registered)
    - Returns mock data in test mode
    - Preserves trace metadata
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from ..contracts.registry import CapabilityClass, SKILL_REGISTRY, SkillRegistryEntry

logger = logging.getLogger(__name__)

# Default: READ and ANALYTICAL are always safe to expose
_DEFAULT_ALLOWED_CLASSES = frozenset({CapabilityClass.READ, CapabilityClass.ANALYTICAL})

# PROPOSAL is allowed for recommendation building but not for write execution
_PROPOSAL_ALLOWED = frozenset({CapabilityClass.PROPOSAL})

# These are NEVER exposed to any external runtime
_BLOCKED_CLASSES = frozenset({CapabilityClass.WRITE, CapabilityClass.EMERGENCY_WRITE})


class MAIWAgentTool:
    """
    A single MAIW skill exposed as a callable tool for the DeepAgentsRuntime.

    Wraps a SkillRegistryEntry with a callable interface.
    Does NOT implement WRITE or EMERGENCY_WRITE tools — those are blocked.
    """

    def __init__(
        self,
        entry: SkillRegistryEntry,
        *,
        real_impl: Callable[..., Any] | None = None,
        trace_id: str = "",
    ) -> None:
        self._entry = entry
        self._real_impl = real_impl
        self._trace_id = trace_id

    @property
    def skill_id(self) -> str:
        return self._entry.skill_id

    @property
    def description(self) -> str:
        return self._entry.description

    @property
    def capability_class(self) -> CapabilityClass:
        return self._entry.capability_class

    @property
    def input_schema(self) -> str:
        return self._entry.input_schema

    @property
    def output_schema(self) -> str:
        return self._entry.output_schema

    @property
    def domain(self) -> str:
        return self._entry.domain

    @property
    def is_write(self) -> bool:
        return self._entry.is_write

    def to_tool_spec(self) -> dict[str, Any]:
        """Return a tool specification dict for the Deep Agents planner."""
        return {
            "tool_id": self.skill_id,
            "description": self.description,
            "capability_class": self.capability_class.value,
            "domain": self.domain,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "is_write": self.is_write,
        }

    async def __call__(
        self,
        inputs: dict[str, Any] | None = None,
        *,
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Invoke this tool.

        In test mode (real_impl is None), returns mock data.
        In production, routes to the real skill implementation.
        """
        effective_trace = trace_id or self._trace_id

        logger.debug(
            "MAIWAgentTool: invoking skill=%s trace=%s",
            self.skill_id, effective_trace,
        )

        if self._real_impl is not None:
            try:
                result = await self._real_impl(inputs or {}, trace_id=effective_trace)
                return {
                    "skill_id": self.skill_id,
                    "outcome": "success",
                    "result": result,
                    "trace_id": effective_trace,
                }
            except Exception as exc:
                logger.error(
                    "MAIWAgentTool: skill %s failed: %s trace=%s",
                    self.skill_id, exc, effective_trace,
                )
                return {
                    "skill_id": self.skill_id,
                    "outcome": "error",
                    "error": str(exc),
                    "trace_id": effective_trace,
                }

        # Test mode: return realistic mock
        return self._mock_result(inputs or {}, trace_id=effective_trace)

    def _mock_result(
        self,
        inputs: dict[str, Any],
        *,
        trace_id: str,
    ) -> dict[str, Any]:
        """Deterministic mock result for test mode."""
        domain = self.domain
        skill_id = self.skill_id

        if "labor.capacity" in skill_id or "labor.inspect" in skill_id:
            data = {
                "total_workers": 20,
                "idle_workers": 5,
                "active_workers": 15,
                "zone_a_workers": 8,
                "zone_b_workers": 12,
                "pending_task_count": 12,
                "constraint": "capacity_deficit_zone_a",
            }
        elif "labor.evaluate" in skill_id:
            data = {
                "reallocation_feasible": True,
                "recommended_workers": 2,
                "from_zone": "B",
                "to_zone": "A",
                "estimated_completion_minutes": 35,
            }
        elif "wave.status" in skill_id or "wave.inspect" in skill_id:
            data = {
                "wave_id": "wave-17",
                "at_risk_count": 3,
                "pending_count": 12,
                "completed_count": 45,
                "carrier_cutoff_minutes": 47,
                "primary_risk": "labor_shortage",
            }
        elif "wave.evaluate_critical" in skill_id:
            data = {
                "critical_path_tasks": ["task-001", "task-002", "task-003"],
                "slack_minutes": 12,
                "blocking_resource": "zone_a_labor",
            }
        elif "wave.evaluate_reprio" in skill_id:
            data = {
                "reprioritization_options": [
                    {"option": "bump_priority_tier_1", "impact": "high", "risk": "low"},
                ],
            }
        elif "equipment.status" in skill_id:
            data = {
                "equipment_count": 15,
                "available": 12,
                "in_use": 3,
                "offline": 0,
                "bottleneck": None,
            }
        elif "inventory.lookup" in skill_id:
            data = {
                "sku_count": 50,
                "locations_resolved": 48,
                "stock_issues": [],
            }
        else:
            data = {
                "domain": domain,
                "skill_id": skill_id,
                "mock_result": "success",
            }

        return {
            "skill_id": skill_id,
            "outcome": "success",
            "result": data,
            "trace_id": trace_id,
            "mock": True,
        }


class MAIWSkillAdapter:
    """
    Adapter that maps the MAIW SKILL_REGISTRY to callable tools for
    the DeepAgentsRuntime.

    Policy enforcement:
        - WRITE and EMERGENCY_WRITE skills are NEVER exposed
        - READ and ANALYTICAL are always exposed
        - PROPOSAL skills are exposed only when include_proposal=True

    Usage:
        adapter = MAIWSkillAdapter()
        tools = adapter.get_agent_callable_tools()  # READ + ANALYTICAL only
        all_tools = adapter.get_agent_callable_tools(
            allowed_capability_classes={CapabilityClass.READ,
                                       CapabilityClass.ANALYTICAL,
                                       CapabilityClass.PROPOSAL}
        )
    """

    def __init__(
        self,
        *,
        skill_registry: dict[str, SkillRegistryEntry] | None = None,
        trace_id: str = "",
    ) -> None:
        self._registry = skill_registry or SKILL_REGISTRY
        self._trace_id = trace_id

    def get_agent_callable_tools(
        self,
        allowed_capability_classes: frozenset[CapabilityClass] | set[CapabilityClass] | None = None,
    ) -> list[MAIWAgentTool]:
        """
        Return callable tools for the given capability classes.

        Defaults to READ and ANALYTICAL only (safe for any agent).
        WRITE and EMERGENCY_WRITE are ALWAYS blocked regardless of input.

        Args:
            allowed_capability_classes: Which capability classes to include.
                Defaults to {READ, ANALYTICAL}.
                WRITE/EMERGENCY_WRITE are silently removed if included.

        Returns:
            List of MAIWAgentTool instances for allowed, non-write skills.
        """
        if allowed_capability_classes is None:
            effective_classes = _DEFAULT_ALLOWED_CLASSES
        else:
            # Strip any write classes — they are never allowed
            effective_classes = frozenset(allowed_capability_classes) - _BLOCKED_CLASSES

        tools = []
        for entry in self._registry.values():
            if entry.capability_class in _BLOCKED_CLASSES:
                # Hard block — log at debug to avoid noise
                logger.debug(
                    "MAIWSkillAdapter: blocking write skill %s (class=%s)",
                    entry.skill_id, entry.capability_class,
                )
                continue

            if entry.capability_class not in effective_classes:
                continue

            tools.append(
                MAIWAgentTool(
                    entry,
                    real_impl=None,  # test mode; production wires real impl
                    trace_id=self._trace_id,
                )
            )

        return tools

    def get_tool(self, skill_id: str) -> MAIWAgentTool | None:
        """Look up a specific tool by skill_id. Returns None if not found or write-blocked."""
        entry = self._registry.get(skill_id)
        if entry is None:
            return None
        if entry.capability_class in _BLOCKED_CLASSES:
            logger.warning(
                "MAIWSkillAdapter: attempted access to blocked skill %s (class=%s)",
                skill_id, entry.capability_class,
            )
            return None
        return MAIWAgentTool(entry, real_impl=None, trace_id=self._trace_id)

    def list_available_tool_specs(
        self,
        allowed_capability_classes: frozenset[CapabilityClass] | set[CapabilityClass] | None = None,
    ) -> list[dict[str, Any]]:
        """Return tool specification dicts for the Deep Agents planner."""
        return [
            tool.to_tool_spec()
            for tool in self.get_agent_callable_tools(allowed_capability_classes)
        ]

    def is_blocked(self, skill_id: str) -> bool:
        """Return True if this skill is blocked (WRITE or EMERGENCY_WRITE)."""
        entry = self._registry.get(skill_id)
        if entry is None:
            return False
        return entry.capability_class in _BLOCKED_CLASSES
