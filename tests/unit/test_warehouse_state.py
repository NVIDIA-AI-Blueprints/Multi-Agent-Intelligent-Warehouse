# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for maiw-state package.

Covers:
  - StateFreshness: now(), from_observed_at(), stale flag
  - StateProvenance: construction and fields
  - StateRequirements: defaults and field access
  - EquipmentAssetSummary / EquipmentState: construction, find_asset, from_status_result
  - InventoryItemSummary / InventoryState: construction, from_lookup_result
  - WarehouseState: composition, is_empty, provenance list
  - WarehouseStateSnapshot: seal(), snapshot_id uniqueness, equipment_age_ms, is_equipment_stale
  - StateAssemblyError / StateFreshnessError: construction and message
  - WarehouseStateProvider: equipment assembly, inventory assembly, missing skill raises

All tests use asyncio.run() (no pytest-asyncio required).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from maiw_state import (
    EquipmentAssetSummary,
    EquipmentState,
    InventoryItemSummary,
    InventoryState,
    StateAssemblyError,
    StateFreshness,
    StateFreshnessError,
    StateProvenance,
    StateRequirements,
    StateSource,
    WarehouseState,
    WarehouseStateProvider,
    WarehouseStateSnapshot,
)


# ---------------------------------------------------------------------------
# StateFreshness
# ---------------------------------------------------------------------------


class TestStateFreshness:
    def test_now_produces_fresh_state(self):
        f = StateFreshness.now()
        assert f.age_ms == 0
        assert f.stale is False
        assert f.stale_after_ms == 30_000

    def test_now_custom_stale_after(self):
        f = StateFreshness.now(stale_after_ms=5_000)
        assert f.stale_after_ms == 5_000

    def test_from_observed_at_recent_not_stale(self):
        observed = datetime.now(timezone.utc) - timedelta(seconds=5)
        f = StateFreshness.from_observed_at(observed, stale_after_ms=30_000)
        assert f.stale is False
        assert 4_000 <= f.age_ms <= 10_000

    def test_from_observed_at_old_is_stale(self):
        observed = datetime.now(timezone.utc) - timedelta(seconds=60)
        f = StateFreshness.from_observed_at(observed, stale_after_ms=30_000)
        assert f.stale is True
        assert f.age_ms > 30_000

    def test_from_observed_at_naive_datetime_treated_as_utc(self):
        # naive dt should be accepted without raising
        observed = datetime.utcnow() - timedelta(seconds=5)
        f = StateFreshness.from_observed_at(observed)
        assert f.stale is False


# ---------------------------------------------------------------------------
# StateProvenance
# ---------------------------------------------------------------------------


class TestStateProvenance:
    def test_construction(self):
        p = StateProvenance(
            domain="equipment",
            capability="warehouse.equipment.get_status",
            server="equipment-mcp",
            provider="MockEquipmentProvider",
            source=StateSource.MCP,
            observed_at=datetime.now(timezone.utc),
            latency_ms=12.5,
        )
        assert p.domain == "equipment"
        assert p.source == StateSource.MCP
        assert p.latency_ms == 12.5

    def test_default_source_is_mcp(self):
        p = StateProvenance(
            domain="inventory",
            capability="warehouse.inventory.get",
            server="inventory-mcp",
            provider="SomeProvider",
            observed_at=datetime.now(timezone.utc),
        )
        assert p.source == StateSource.MCP

    def test_mock_source(self):
        p = StateProvenance(
            domain="equipment",
            capability="warehouse.equipment.get_status",
            server="mock",
            provider="MockEquipmentProvider",
            source=StateSource.MOCK,
            observed_at=datetime.now(timezone.utc),
        )
        assert p.source == StateSource.MOCK


# ---------------------------------------------------------------------------
# StateRequirements
# ---------------------------------------------------------------------------


class TestStateRequirements:
    def test_defaults_nothing_requested(self):
        r = StateRequirements()
        assert r.inventory is False
        assert r.equipment is False
        assert r.max_age_ms == 30_000

    def test_equipment_only(self):
        r = StateRequirements(equipment=True, equipment_type="forklift")
        assert r.equipment is True
        assert r.equipment_type == "forklift"
        assert r.inventory is False

    def test_custom_max_age(self):
        r = StateRequirements(equipment=True, max_age_ms=5_000)
        assert r.max_age_ms == 5_000


# ---------------------------------------------------------------------------
# EquipmentState
# ---------------------------------------------------------------------------


class TestEquipmentState:
    def _freshness(self) -> StateFreshness:
        return StateFreshness.now()

    def test_empty_state(self):
        s = EquipmentState(warehouse_id="wh-1", freshness=self._freshness())
        assert s.total_count == 0
        assert s.available_count == 0
        assert s.assets == []

    def test_find_asset_present(self):
        asset = EquipmentAssetSummary(
            asset_id="FL-001",
            equipment_type="forklift",
            model="Model-X",
            zone="A",
            status="available",
        )
        s = EquipmentState(
            warehouse_id="wh-1",
            assets=[asset],
            total_count=1,
            freshness=self._freshness(),
        )
        found = s.find_asset("FL-001")
        assert found is not None
        assert found.asset_id == "FL-001"

    def test_find_asset_missing_returns_none(self):
        s = EquipmentState(warehouse_id="wh-1", freshness=self._freshness())
        assert s.find_asset("MISSING") is None

    def test_from_status_result_projection(self):
        mock_asset = MagicMock()
        mock_asset.asset_id = "FL-002"
        mock_asset.equipment_type = "forklift"
        mock_asset.model = "Model-Y"
        mock_asset.zone = "B"
        mock_asset.status = "available"
        mock_asset.owner_user = None

        result = MagicMock()
        result.equipment = [mock_asset]
        result.total_count = 1
        result.summary = {"forklift": {"available": 1}}

        state = EquipmentState.from_status_result(
            "wh-1", result, freshness=self._freshness()
        )
        assert state.total_count == 1
        assert state.available_count == 1
        assert len(state.assets) == 1
        assert state.assets[0].asset_id == "FL-002"

    def test_from_status_result_available_count(self):
        def _mk_asset(asset_id, status):
            m = MagicMock()
            m.asset_id = asset_id
            m.equipment_type = "forklift"
            m.model = "M"
            m.zone = "A"
            m.status = status
            m.owner_user = None
            return m

        result = MagicMock()
        result.equipment = [
            _mk_asset("A", "available"),
            _mk_asset("B", "assigned"),
            _mk_asset("C", "available"),
        ]
        result.total_count = 3
        result.summary = {}

        state = EquipmentState.from_status_result(
            "wh-1", result, freshness=self._freshness()
        )
        assert state.available_count == 2


# ---------------------------------------------------------------------------
# InventoryState
# ---------------------------------------------------------------------------


class TestInventoryState:
    def test_from_lookup_result(self):
        result = MagicMock()
        result.sku = "SKU-001"
        result.name = "Widget A"
        result.total_available = 100
        result.is_low_stock = False
        result.locations = ["loc1", "loc2"]

        state = InventoryState.from_lookup_result(
            "wh-1", result, freshness=StateFreshness.now()
        )
        assert state.total_items == 1
        assert state.low_stock_count == 0
        assert state.items[0].sku == "SKU-001"
        assert state.items[0].location_count == 2

    def test_low_stock_flag(self):
        result = MagicMock()
        result.sku = "SKU-002"
        result.name = "Widget B"
        result.total_available = 3
        result.is_low_stock = True
        result.locations = ["loc1"]

        state = InventoryState.from_lookup_result(
            "wh-1", result, freshness=StateFreshness.now()
        )
        assert state.low_stock_count == 1


# ---------------------------------------------------------------------------
# WarehouseState and WarehouseStateSnapshot
# ---------------------------------------------------------------------------


class TestWarehouseState:
    def _make_equipment_state(self, stale=False) -> EquipmentState:
        if stale:
            old_ts = datetime.now(timezone.utc) - timedelta(seconds=60)
            freshness = StateFreshness.from_observed_at(old_ts, stale_after_ms=30_000)
        else:
            freshness = StateFreshness.now()
        return EquipmentState(
            warehouse_id="wh-1",
            freshness=freshness,
        )

    def test_is_empty_when_no_domains(self):
        state = WarehouseState(
            warehouse_id="wh-1",
            observed_at=datetime.now(timezone.utc),
        )
        assert state.is_empty() is True

    def test_is_not_empty_with_equipment(self):
        state = WarehouseState(
            warehouse_id="wh-1",
            observed_at=datetime.now(timezone.utc),
            equipment=self._make_equipment_state(),
        )
        assert state.is_empty() is False

    def test_provenance_list(self):
        prov = StateProvenance(
            domain="equipment",
            capability="warehouse.equipment.get_status",
            server="equipment-mcp",
            provider="Mock",
            observed_at=datetime.now(timezone.utc),
        )
        state = WarehouseState(
            warehouse_id="wh-1",
            observed_at=datetime.now(timezone.utc),
            equipment=self._make_equipment_state(),
            provenance=[prov],
        )
        assert len(state.provenance) == 1
        assert state.provenance[0].domain == "equipment"


class TestWarehouseStateSnapshot:
    def _make_state(self) -> WarehouseState:
        return WarehouseState(
            warehouse_id="wh-1",
            observed_at=datetime.now(timezone.utc),
        )

    def test_seal_assigns_unique_ids(self):
        s1 = WarehouseStateSnapshot.seal(self._make_state())
        s2 = WarehouseStateSnapshot.seal(self._make_state())
        assert s1.snapshot_id != s2.snapshot_id

    def test_seal_sets_warehouse_id(self):
        snap = WarehouseStateSnapshot.seal(self._make_state())
        assert snap.warehouse_id == "wh-1"

    def test_equipment_age_ms_absent(self):
        snap = WarehouseStateSnapshot.seal(self._make_state())
        assert snap.equipment_age_ms() is None

    def test_equipment_age_ms_present(self):
        eq = EquipmentState(
            warehouse_id="wh-1",
            freshness=StateFreshness.now(),
        )
        state = WarehouseState(
            warehouse_id="wh-1",
            observed_at=datetime.now(timezone.utc),
            equipment=eq,
        )
        snap = WarehouseStateSnapshot.seal(state)
        assert snap.equipment_age_ms() == 0

    def test_is_equipment_stale_absent(self):
        snap = WarehouseStateSnapshot.seal(self._make_state())
        assert snap.is_equipment_stale() is False

    def test_is_equipment_stale_fresh(self):
        eq = EquipmentState(
            warehouse_id="wh-1",
            freshness=StateFreshness.now(),
        )
        state = WarehouseState(
            warehouse_id="wh-1",
            observed_at=datetime.now(timezone.utc),
            equipment=eq,
        )
        snap = WarehouseStateSnapshot.seal(state)
        assert snap.is_equipment_stale() is False

    def test_is_equipment_stale_stale(self):
        old_ts = datetime.now(timezone.utc) - timedelta(seconds=60)
        eq = EquipmentState(
            warehouse_id="wh-1",
            freshness=StateFreshness.from_observed_at(old_ts, stale_after_ms=30_000),
        )
        state = WarehouseState(
            warehouse_id="wh-1",
            observed_at=datetime.now(timezone.utc),
            equipment=eq,
        )
        snap = WarehouseStateSnapshot.seal(state)
        assert snap.is_equipment_stale() is True


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TestErrors:
    def test_state_assembly_error(self):
        err = StateAssemblyError("equipment", "skill not configured")
        assert "equipment" in str(err)
        assert err.domain == "equipment"
        assert err.cause is None

    def test_state_assembly_error_with_cause(self):
        cause = ValueError("boom")
        err = StateAssemblyError("inventory", "failed", cause=cause)
        assert err.cause is cause

    def test_state_freshness_error(self):
        err = StateFreshnessError("equipment", age_ms=60_000, max_age_ms=30_000)
        assert err.domain == "equipment"
        assert err.age_ms == 60_000
        assert err.max_age_ms == 30_000
        assert "stale" in str(err).lower()


# ---------------------------------------------------------------------------
# WarehouseStateProvider
# ---------------------------------------------------------------------------


class TestWarehouseStateProvider:
    def _make_mock_equipment_skill(self, assets=None):
        mock_result = MagicMock()
        mock_result.total_count = len(assets or [])
        mock_result.summary = {}
        mock_result.equipment = []
        skill = MagicMock()
        skill.execute = AsyncMock(return_value=mock_result)
        return skill

    def test_raises_when_equipment_skill_not_configured(self):
        provider = WarehouseStateProvider()
        req = StateRequirements(equipment=True)

        async def run():
            return await provider.get_state("wh-1", req)

        with pytest.raises(StateAssemblyError) as exc_info:
            asyncio.run(run())
        assert "equipment" in exc_info.value.domain

    def test_raises_when_inventory_skill_not_configured(self):
        provider = WarehouseStateProvider()
        req = StateRequirements(inventory=True, inventory_sku="SKU-001")

        async def run():
            return await provider.get_state("wh-1", req)

        with pytest.raises(StateAssemblyError) as exc_info:
            asyncio.run(run())
        assert "inventory" in exc_info.value.domain

    def test_assembles_equipment_state(self):
        skill = self._make_mock_equipment_skill()
        provider = WarehouseStateProvider(equipment_status_skill=skill)
        req = StateRequirements(equipment=True)

        async def run():
            return await provider.get_state("wh-1", req)

        state = asyncio.run(run())
        assert state.warehouse_id == "wh-1"
        assert state.equipment is not None
        assert state.inventory is None
        assert len(state.provenance) == 1
        assert state.provenance[0].domain == "equipment"

    def test_skill_called_once(self):
        skill = self._make_mock_equipment_skill()
        provider = WarehouseStateProvider(equipment_status_skill=skill)
        req = StateRequirements(equipment=True)

        async def run():
            return await provider.get_state("wh-1", req)

        asyncio.run(run())
        skill.execute.assert_called_once()

    def test_nothing_populated_when_no_requirements(self):
        provider = WarehouseStateProvider()
        req = StateRequirements()

        async def run():
            return await provider.get_state("wh-1", req)

        state = asyncio.run(run())
        assert state.is_empty() is True
        assert state.provenance == []

    def test_skill_exception_raises_state_assembly_error(self):
        skill = MagicMock()
        skill.execute = AsyncMock(side_effect=RuntimeError("network down"))
        provider = WarehouseStateProvider(equipment_status_skill=skill)
        req = StateRequirements(equipment=True)

        async def run():
            return await provider.get_state("wh-1", req)

        with pytest.raises(StateAssemblyError) as exc_info:
            asyncio.run(run())
        assert "equipment" in exc_info.value.domain
        assert isinstance(exc_info.value.cause, RuntimeError)
