# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
StateProvider Protocol and WarehouseStateProvider.

Architecture
------------
``WarehouseStateProvider`` assembles ``WarehouseState`` by calling
existing Skills.  It does NOT import concrete skill classes — instead it
declares ``_EquipmentStatusSkillProto`` and ``_InventorySkillProto``
Protocols so that the app-layer Skills satisfy the contract through
structural duck-typing without creating an import cycle:

    maiw-mcp ← maiw-state ← maiw-decision
    src/api/skills/     (app layer — imports maiw-state, NOT vice-versa)

The concrete ``EquipmentStatusSkill`` and the inventory skill objects are
injected at construction time.  ``WarehouseStateProvider`` never imports
``src.api.*``.

Usage
-----
    from maiw_state import WarehouseStateProvider, StateRequirements

    provider = WarehouseStateProvider(
        equipment_status_skill=equipment_status_skill_instance,
    )
    state = await provider.get_state("warehouse-001", StateRequirements(equipment=True))
    snapshot = WarehouseStateSnapshot.seal(state)
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from maiw_mcp.deadline import RequestDeadline, RequestDeadlineExceeded

from .errors import StateAssemblyError
from .freshness import StateFreshness
from .models.equipment import EquipmentState
from .models.inventory import InventoryState
from .models.labor import LaborState
from .models.wave import WaveState
from .provenance import StateProvenance, StateSource
from .requirements import StateRequirements
from .warehouse import WarehouseState

# ---------------------------------------------------------------------------
# Skill protocols — structural typing; no import of concrete skill classes
# ---------------------------------------------------------------------------


@runtime_checkable
class _EquipmentStatusSkillProto(Protocol):
    """Structural protocol matching EquipmentStatusSkill.execute."""

    async def execute(self, request: Any, *, trace_id: str | None = None) -> Any: ...


@runtime_checkable
class _InventorySkillProto(Protocol):
    """Structural protocol matching InventoryLookupSkill.execute."""

    async def execute(self, request: Any, *, trace_id: str | None = None) -> Any: ...


# ---------------------------------------------------------------------------
# StateProvider Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class StateProvider(Protocol):
    """
    Structural protocol for state assembly.

    Any class with a matching ``get_state`` signature satisfies this
    protocol — including ``WarehouseStateProvider`` and test doubles.
    """

    async def get_state(
        self,
        warehouse_id: str,
        requirements: StateRequirements,
        *,
        trace_id: str | None = None,
        deadline: RequestDeadline | None = None,
    ) -> WarehouseState: ...


# ---------------------------------------------------------------------------
# WarehouseStateProvider
# ---------------------------------------------------------------------------


class WarehouseStateProvider:
    """
    Assembles WarehouseState from injected Skills.

    Each domain is populated only when the corresponding
    ``StateRequirements`` flag is set.  A failure in one domain raises
    ``StateAssemblyError`` immediately — partial state is not silently
    returned.  Callers that want resilient partial assembly should catch
    ``StateAssemblyError`` per-domain.

    Parameters
    ----------
    equipment_status_skill:
        Object satisfying ``_EquipmentStatusSkillProto``.  Required to
        populate the equipment domain.
    inventory_skill:
        Object satisfying ``_InventorySkillProto``.  Required to populate
        the inventory domain.
    """

    def __init__(
        self,
        *,
        equipment_status_skill: _EquipmentStatusSkillProto | None = None,
        inventory_skill: _InventorySkillProto | None = None,
        labor_capacity_skill: _EquipmentStatusSkillProto | None = None,
        wave_get_skill: _EquipmentStatusSkillProto | None = None,
    ) -> None:
        self._equipment_skill = equipment_status_skill
        self._inventory_skill = inventory_skill
        self._labor_skill = labor_capacity_skill
        self._wave_skill = wave_get_skill

    async def get_state(
        self,
        warehouse_id: str,
        requirements: StateRequirements,
        *,
        trace_id: str | None = None,
        deadline: RequestDeadline | None = None,
    ) -> WarehouseState:
        """
        Assemble WarehouseState for *warehouse_id* per *requirements*.

        The same *deadline* object is passed to all domain reads — they share
        the parent budget rather than each getting a fresh timeout.

        Raises
        ------
        RequestDeadlineExceeded
            Parent deadline expired before or during state assembly.
        StateAssemblyError
            When a required skill is not configured or a capability call fails.
        """
        inventory_state: InventoryState | None = None
        equipment_state: EquipmentState | None = None
        labor_state: LaborState | None = None
        wave_state: WaveState | None = None
        provenance: list[StateProvenance] = []
        now = datetime.now(timezone.utc)

        if requirements.inventory:
            inventory_state, prov = await self._assemble_inventory(
                warehouse_id, requirements, trace_id=trace_id, deadline=deadline
            )
            provenance.append(prov)

        if requirements.equipment:
            equipment_state, prov = await self._assemble_equipment(
                warehouse_id, requirements, trace_id=trace_id, deadline=deadline
            )
            provenance.append(prov)

        if requirements.labor:
            labor_state, prov = await self._assemble_labor(
                warehouse_id, requirements, trace_id=trace_id, deadline=deadline
            )
            provenance.append(prov)

        if requirements.waves:
            wave_state, prov = await self._assemble_waves(
                warehouse_id, requirements, trace_id=trace_id, deadline=deadline
            )
            provenance.append(prov)

        return WarehouseState(
            warehouse_id=warehouse_id,
            observed_at=now,
            inventory=inventory_state,
            equipment=equipment_state,
            labor=labor_state,
            waves=wave_state,
            provenance=provenance,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _assemble_equipment(
        self,
        warehouse_id: str,
        requirements: StateRequirements,
        *,
        trace_id: str | None,
        deadline: RequestDeadline | None = None,
    ) -> tuple[EquipmentState, StateProvenance]:
        if self._equipment_skill is None:
            raise StateAssemblyError(
                "equipment",
                "EquipmentStatusSkill not configured — pass equipment_status_skill to WarehouseStateProvider",
            )

        if deadline is not None and deadline.expired:
            raise RequestDeadlineExceeded(expired_by_ms=(deadline._clock() - deadline.deadline_at) * 1000.0)  # type: ignore[operator]

        from maiw_mcp.contracts.equipment import EquipmentStatusRequest  # noqa: PLC0415

        req = EquipmentStatusRequest(
            asset_id=requirements.equipment_asset_id,
            equipment_type=requirements.equipment_type,
            zone=requirements.equipment_zone,
            status_filter=requirements.equipment_status_filter,
        )

        t0 = time.monotonic()
        try:
            coro = self._equipment_skill.execute(req, trace_id=trace_id)
            if deadline is not None:
                remaining = deadline.remaining_seconds
                try:
                    result = await asyncio.wait_for(coro, timeout=remaining)
                except asyncio.TimeoutError:
                    raise RequestDeadlineExceeded(expired_by_ms=0.0)
            else:
                result = await coro
        except RequestDeadlineExceeded:
            raise
        except Exception as exc:
            raise StateAssemblyError("equipment", str(exc), cause=exc) from exc
        latency_ms = (time.monotonic() - t0) * 1000

        freshness = StateFreshness.now(stale_after_ms=requirements.max_age_ms)
        state = EquipmentState.from_status_result(
            warehouse_id, result, freshness=freshness
        )

        prov = StateProvenance(
            domain="equipment",
            capability="warehouse.equipment.get_status",
            server="equipment-mcp",
            provider=type(self._equipment_skill).__name__,
            source=StateSource.MCP,
            observed_at=freshness.observed_at,
            latency_ms=latency_ms,
        )
        return state, prov

    async def _assemble_inventory(
        self,
        warehouse_id: str,
        requirements: StateRequirements,
        *,
        trace_id: str | None,
        deadline: RequestDeadline | None = None,
    ) -> tuple[InventoryState, StateProvenance]:
        if self._inventory_skill is None:
            raise StateAssemblyError(
                "inventory",
                "InventorySkill not configured — pass inventory_skill to WarehouseStateProvider",
            )

        if deadline is not None and deadline.expired:
            raise RequestDeadlineExceeded(expired_by_ms=(deadline._clock() - deadline.deadline_at) * 1000.0)  # type: ignore[operator]

        from maiw_mcp.contracts.inventory import InventoryLookupRequest  # noqa: PLC0415

        req = InventoryLookupRequest(
            sku=requirements.inventory_sku or "",
            warehouse_id=requirements.inventory_warehouse_id,
        )

        t0 = time.monotonic()
        try:
            coro = self._inventory_skill.execute(req, trace_id=trace_id)
            if deadline is not None:
                remaining = deadline.remaining_seconds
                try:
                    result = await asyncio.wait_for(coro, timeout=remaining)
                except asyncio.TimeoutError:
                    raise RequestDeadlineExceeded(expired_by_ms=0.0)
            else:
                result = await coro
        except RequestDeadlineExceeded:
            raise
        except Exception as exc:
            raise StateAssemblyError("inventory", str(exc), cause=exc) from exc
        latency_ms = (time.monotonic() - t0) * 1000

        freshness = StateFreshness.now(stale_after_ms=requirements.max_age_ms)
        state = InventoryState.from_lookup_result(
            warehouse_id, result, freshness=freshness
        )

        prov = StateProvenance(
            domain="inventory",
            capability="warehouse.inventory.get",
            server="inventory-mcp",
            provider=type(self._inventory_skill).__name__,
            source=StateSource.MCP,
            observed_at=freshness.observed_at,
            latency_ms=latency_ms,
        )
        return state, prov

    async def _assemble_labor(
        self,
        warehouse_id: str,
        requirements: StateRequirements,
        *,
        trace_id: str | None,
        deadline: RequestDeadline | None = None,
    ) -> tuple[LaborState, StateProvenance]:
        if self._labor_skill is None:
            raise StateAssemblyError(
                "labor",
                "LaborCapacitySkill not configured — pass labor_capacity_skill to WarehouseStateProvider",
            )

        if deadline is not None and deadline.expired:
            raise RequestDeadlineExceeded(expired_by_ms=(deadline._clock() - deadline.deadline_at) * 1000.0)  # type: ignore[operator]

        from maiw_mcp.contracts.labor import LaborCapacityRequest  # noqa: PLC0415

        req = LaborCapacityRequest(
            warehouse_id=warehouse_id,
            zone=requirements.labor_zone,
            shift=requirements.labor_shift,
            status_filter=requirements.labor_status_filter,
        )

        t0 = time.monotonic()
        try:
            coro = self._labor_skill.execute(req, trace_id=trace_id)
            if deadline is not None:
                remaining = deadline.remaining_seconds
                try:
                    result = await asyncio.wait_for(coro, timeout=remaining)
                except asyncio.TimeoutError:
                    raise RequestDeadlineExceeded(expired_by_ms=0.0)
            else:
                result = await coro
        except RequestDeadlineExceeded:
            raise
        except Exception as exc:
            raise StateAssemblyError("labor", str(exc), cause=exc) from exc
        latency_ms = (time.monotonic() - t0) * 1000

        freshness = StateFreshness.now(stale_after_ms=requirements.max_age_ms)
        state = LaborState.from_capacity_result(
            warehouse_id, result, freshness=freshness
        )

        prov = StateProvenance(
            domain="labor",
            capability="warehouse.labor.get_capacity",
            server="labor-mcp",
            provider=type(self._labor_skill).__name__,
            source=StateSource.MCP,
            observed_at=freshness.observed_at,
            latency_ms=latency_ms,
        )
        return state, prov

    async def _assemble_waves(
        self,
        warehouse_id: str,
        requirements: StateRequirements,
        *,
        trace_id: str | None,
        deadline: RequestDeadline | None = None,
    ) -> tuple[WaveState, StateProvenance]:
        if self._wave_skill is None:
            raise StateAssemblyError(
                "waves",
                "WaveGetSkill not configured — pass wave_get_skill to WarehouseStateProvider",
            )

        if deadline is not None and deadline.expired:
            raise RequestDeadlineExceeded(expired_by_ms=(deadline._clock() - deadline.deadline_at) * 1000.0)  # type: ignore[operator]

        from maiw_mcp.contracts.wave import WaveGetRequest  # noqa: PLC0415

        req = WaveGetRequest(
            warehouse_id=warehouse_id,
            zone=requirements.waves_zone,
            status_filter=requirements.waves_status_filter,
            task_type=requirements.waves_task_type,
        )

        t0 = time.monotonic()
        try:
            coro = self._wave_skill.execute(req, trace_id=trace_id)
            if deadline is not None:
                remaining = deadline.remaining_seconds
                try:
                    result = await asyncio.wait_for(coro, timeout=remaining)
                except asyncio.TimeoutError:
                    raise RequestDeadlineExceeded(expired_by_ms=0.0)
            else:
                result = await coro
        except RequestDeadlineExceeded:
            raise
        except Exception as exc:
            raise StateAssemblyError("waves", str(exc), cause=exc) from exc
        latency_ms = (time.monotonic() - t0) * 1000

        freshness = StateFreshness.now(stale_after_ms=requirements.max_age_ms)
        state = WaveState.from_get_result(warehouse_id, result, freshness=freshness)

        prov = StateProvenance(
            domain="waves",
            capability="warehouse.wave.get",
            server="wave-mcp",
            provider=type(self._wave_skill).__name__,
            source=StateSource.MCP,
            observed_at=freshness.observed_at,
            latency_ms=latency_ms,
        )
        return state, prov
