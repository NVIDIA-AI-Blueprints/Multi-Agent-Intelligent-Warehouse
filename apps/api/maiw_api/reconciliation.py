# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Production reconciliation strategies (v2.0.1 round 3, NEW3-P1-02).

An UNKNOWN execution (the write may have been applied; the response was lost)
is resolved by reading AUTHORITATIVE state through the canonical MCP read
skills and comparing it with the immutable ``ExecutionIntent`` recorded before
the write.  These strategies were previously defined inside the demo router
(usable only with ``MAIW_DEMO_MODE``); they now serve both the demo route and
the operator-authenticated ``POST /api/v1/executions/{id}/reconcile`` route of
every profile.

Rules (equipment, the path the third re-audit exercised):

    asset not found / read failed                → INDETERMINATE
    status (and assignee) == intended postcondition → CONFIRMED_EXECUTED
    status == pre-write status (recorded)        → CONFIRMED_NOT_EXECUTED
    status changed to anything else              → INDETERMINATE
    no pre-write status recorded, status differs → CONFIRMED_NOT_EXECUTED
                                                   (pre-round-3 behaviour)

No strategy ever writes, retries, or creates a new proposal / decision.
"""

from __future__ import annotations

from typing import Any

from maiw_execution import ReconciliationOutcome


class EquipmentReconciliationStrategy:
    """Reads ``warehouse.equipment.get_status`` for the intent's asset."""

    def __init__(self, mcp_client: Any) -> None:
        self._mcp_client = mcp_client

    async def read_current_state(self, intent: Any) -> dict:
        from maiw_contracts.equipment import EquipmentStatusRequest
        from maiw_skills.equipment.skills import EquipmentStatusSkill

        skill = EquipmentStatusSkill(self._mcp_client)
        result = await skill.execute(
            EquipmentStatusRequest(asset_id=intent.target),
            trace_id=intent.trace_id,
        )
        return result.model_dump(mode="json")

    def check_postcondition(self, intent: Any, current_state: dict) -> Any:
        effect = intent.expected_effect or {}
        expected_status = effect.get("expected_status")
        expected_assignee = effect.get("expected_assignee")
        pre_status = effect.get("pre_status")
        asset_id = intent.target
        if not expected_status or not asset_id:
            return ReconciliationOutcome.INDETERMINATE
        asset = next(
            (
                a
                for a in current_state.get("equipment", []) or []
                if a.get("asset_id") == asset_id
            ),
            None,
        )
        if asset is None:
            return ReconciliationOutcome.INDETERMINATE
        actual = asset.get("status")
        if actual == expected_status and (
            not expected_assignee or asset.get("owner_user") == expected_assignee
        ):
            return ReconciliationOutcome.CONFIRMED_EXECUTED
        if pre_status is not None:
            if actual == pre_status:
                return ReconciliationOutcome.CONFIRMED_NOT_EXECUTED
            return ReconciliationOutcome.INDETERMINATE
        return ReconciliationOutcome.CONFIRMED_NOT_EXECUTED


class LaborReconciliationStrategy:
    """Reads ``warehouse.labor.get_allocation`` for the intent's warehouse."""

    def __init__(self, mcp_client: Any) -> None:
        self._mcp_client = mcp_client

    async def read_current_state(self, intent: Any) -> dict:
        from maiw_contracts.labor import LaborAllocationRequest
        from maiw_skills.labor.skills import LaborAllocationSkill

        skill = LaborAllocationSkill(self._mcp_client)
        result = await skill.execute(
            LaborAllocationRequest(warehouse_id=intent.warehouse_id or "default")
        )
        return result.model_dump()

    def check_postcondition(self, intent: Any, current_state: dict) -> Any:
        expected_task_id = intent.expected_effect.get("task_id")
        if not expected_task_id:
            return ReconciliationOutcome.INDETERMINATE
        for alloc in current_state.get("allocations", []):
            if alloc.get("task_id") == expected_task_id:
                if alloc.get("status") == "in_progress":
                    return ReconciliationOutcome.CONFIRMED_EXECUTED
                return ReconciliationOutcome.CONFIRMED_NOT_EXECUTED
        return ReconciliationOutcome.CONFIRMED_NOT_EXECUTED


class WaveReconciliationStrategy:
    """Reads ``warehouse.wave.get`` for the intent's wave / zone."""

    def __init__(self, mcp_client: Any) -> None:
        self._mcp_client = mcp_client

    async def read_current_state(self, intent: Any) -> dict:
        from maiw_contracts.wave import WaveGetRequest
        from maiw_skills.wave.skills import WaveGetSkill

        skill = WaveGetSkill(self._mcp_client)
        result = await skill.execute(
            WaveGetRequest(
                warehouse_id=intent.warehouse_id or "default",
                wave_id=intent.expected_effect.get("wave_id"),
                zone=intent.expected_effect.get("zone"),
            )
        )
        return result.model_dump()

    def check_postcondition(self, intent: Any, current_state: dict) -> Any:
        expected_priority = intent.expected_effect.get("expected_priority")
        zone = intent.expected_effect.get("zone")
        if not expected_priority:
            return ReconciliationOutcome.INDETERMINATE
        relevant = [
            t
            for t in current_state.get("tasks", [])
            if (not zone or t.get("zone") == zone)
            and t.get("status") not in ("completed", "failed", "cancelled")
        ]
        if not relevant:
            return ReconciliationOutcome.INDETERMINATE
        if any(t.get("priority") == expected_priority for t in relevant):
            return ReconciliationOutcome.CONFIRMED_EXECUTED
        return ReconciliationOutcome.CONFIRMED_NOT_EXECUTED


_STRATEGIES = {
    "equipment": EquipmentReconciliationStrategy,
    "labor": LaborReconciliationStrategy,
    "wave": WaveReconciliationStrategy,
}


def build_reconciliation_strategy(domain: str, mcp_client: Any) -> Any:
    """Strategy for ``domain`` reading through ``mcp_client``; None if unavailable."""
    if mcp_client is None or domain not in _STRATEGIES:
        return None
    return _STRATEGIES[domain](mcp_client)


__all__ = [
    "EquipmentReconciliationStrategy",
    "LaborReconciliationStrategy",
    "WaveReconciliationStrategy",
    "build_reconciliation_strategy",
]
