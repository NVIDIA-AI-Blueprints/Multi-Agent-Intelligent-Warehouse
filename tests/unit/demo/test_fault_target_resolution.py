# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Equipment fault-injection targets are resolved from the ACTIVE demo world.

Demo mode builds the world from the DC-47 DataPack (asset ids like
``agv-000``); the scenario YAMLs (``AGV-01`` …) are only the fallback when the
DataPack path is unavailable.  The UI used to hard-code ``AGV-01`` and every
equipment injection failed against the DataPack world.

Rule (DemoScenarioController.resolve_equipment_target), asset_id omitted:
    equipment_fault    eligible = status == "available"
    equipment_restore  eligible = status not in ("available", "assigned"),
                       assets with a fault_code first
    an ``equipment_type`` hint ranks matching assets first (never a filter);
    the lowest asset_id (plain string order) wins.
"""

from __future__ import annotations

import asyncio

import pytest

from maiw_api.demo.controller import (
    DemoScenarioController,
    InjectTargetError,
    reset_demo_controller,
)

SCENARIO = "labor_constraint_wave_risk"


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def reset_singleton():
    reset_demo_controller()
    yield
    reset_demo_controller()


@pytest.fixture
def datapack_ctrl():
    ctrl = DemoScenarioController()
    _run(ctrl.start(SCENARIO))
    assert ctrl.world._scenario_world is not None, "expected the DataPack path"
    return ctrl


@pytest.fixture
def yaml_ctrl(monkeypatch):
    """Force the legacy YAML fallback (DataPack path unavailable for SCENARIO)."""
    import maiw_api.demo.world_loader as world_loader

    monkeypatch.setattr(world_loader, "SCENARIO_OVERLAYS", {})
    ctrl = DemoScenarioController()
    _run(ctrl.start(SCENARIO))
    assert ctrl.world._scenario_world is None, "expected the YAML fallback"
    return ctrl


def _fault(ctrl, **payload):
    return _run(ctrl.inject("equipment_fault", payload))


def _restore(ctrl, **payload):
    return _run(ctrl.inject("equipment_restore", payload))


# ── equipment_fault on the DataPack world ─────────────────────────────────────


class TestFaultResolutionDataPack:
    def test_omitted_asset_resolves_to_lowest_available_datapack_asset(
        self, datapack_ctrl
    ):
        result = _fault(datapack_ctrl, fault_code="E_MOTOR_OVERTEMP")
        assert result["asset_id"] == "agv-000"
        assert result["target_resolution"] == "resolved"
        assert result["status"] == "offline"
        asset = datapack_ctrl.world.equipment["agv-000"]
        assert asset.status == "offline"
        assert asset.fault_code == "E_MOTOR_OVERTEMP"

    def test_resolution_is_deterministic_for_the_same_world(self):
        targets = []
        for _ in range(3):
            ctrl = DemoScenarioController()
            _run(ctrl.start(SCENARIO))
            targets.append(_fault(ctrl)["asset_id"])
        assert targets == ["agv-000"] * 3

    def test_resolution_is_stable_across_reset(self, datapack_ctrl):
        first = _fault(datapack_ctrl)["asset_id"]
        _run(datapack_ctrl.reset())
        assert _fault(datapack_ctrl)["asset_id"] == first

    def test_already_faulted_asset_is_skipped(self, datapack_ctrl):
        assert _fault(datapack_ctrl)["asset_id"] == "agv-000"
        assert _fault(datapack_ctrl)["asset_id"] == "agv-001"

    def test_type_hint_is_preferred(self, datapack_ctrl):
        result = _fault(datapack_ctrl, equipment_type="forklift")
        assert result["asset_id"] == "forklift-000"

    def test_type_hint_is_case_insensitive(self, datapack_ctrl):
        assert _fault(datapack_ctrl, equipment_type="Conveyor")["asset_id"] == (
            "conveyor-000"
        )

    def test_unmatched_type_hint_falls_back_to_any_available(self, datapack_ctrl):
        assert _fault(datapack_ctrl, equipment_type="crane")["asset_id"] == "agv-000"

    def test_explicit_valid_asset_is_used(self, datapack_ctrl):
        result = _fault(datapack_ctrl, asset_id="forklift-007")
        assert result["asset_id"] == "forklift-007"
        assert result["target_resolution"] == "explicit"
        assert datapack_ctrl.world.equipment["forklift-007"].status == "offline"

    def test_blank_asset_id_is_treated_as_omitted(self, datapack_ctrl):
        result = _fault(datapack_ctrl, asset_id="  ")
        assert result["asset_id"] == "agv-000"
        assert result["target_resolution"] == "resolved"

    def test_explicit_yaml_id_is_not_in_datapack_world(self, datapack_ctrl):
        before = {k: a.status for k, a in datapack_ctrl.world.equipment.items()}
        with pytest.raises(InjectTargetError) as ei:
            _fault(datapack_ctrl, asset_id="AGV-01")
        err = ei.value
        assert err.code == "ASSET_NOT_IN_ACTIVE_WORLD"
        assert err.status_code == 404
        assert err.extra == {"asset_id": "AGV-01", "world_source": "datapack"}
        assert "AGV-01" in err.message
        # nothing mutated, no disruption recorded
        after = {k: a.status for k, a in datapack_ctrl.world.equipment.items()}
        assert after == before
        assert datapack_ctrl.world._disruption_sim_time is None

    def test_no_eligible_asset_is_typed(self, datapack_ctrl):
        for asset in datapack_ctrl.world.equipment.values():
            asset.status = "offline"
        with pytest.raises(InjectTargetError) as ei:
            _fault(datapack_ctrl)
        assert ei.value.code == "NO_ELIGIBLE_ASSET"
        assert ei.value.status_code == 409
        assert ei.value.extra == {"world_source": "datapack"}

    def test_inject_event_carries_the_resolved_asset(self, datapack_ctrl):
        published = []

        async def record(**kwargs):
            published.append(kwargs)

        datapack_ctrl.bus.publish_inject = record
        _fault(datapack_ctrl)
        assert published[-1]["asset_id"] == "agv-000"
        assert "agv-000" in published[-1]["detail"]

    def test_inject_without_scenario_still_raises_runtime_error(self):
        ctrl = DemoScenarioController()
        with pytest.raises(RuntimeError, match="No active scenario"):
            _fault(ctrl)


# ── equipment_restore on the DataPack world ───────────────────────────────────


class TestRestoreResolutionDataPack:
    def test_restore_targets_the_faulted_asset(self, datapack_ctrl):
        faulted = _fault(datapack_ctrl)["asset_id"]
        result = _restore(datapack_ctrl)
        assert result["asset_id"] == faulted
        assert result["target_resolution"] == "resolved"
        asset = datapack_ctrl.world.equipment[faulted]
        assert asset.status == "available"
        assert asset.fault_code is None

    def test_restore_prefers_assets_with_a_fault_code(self, datapack_ctrl):
        world = datapack_ctrl.world.equipment
        world["agv-000"].status = "maintenance"  # not faulted
        _fault(datapack_ctrl, asset_id="forklift-003", fault_code="E_HYDRAULIC")
        assert _restore(datapack_ctrl)["asset_id"] == "forklift-003"
        # then the remaining non-available asset
        assert _restore(datapack_ctrl)["asset_id"] == "agv-000"

    def test_restore_never_targets_an_assigned_asset(self, datapack_ctrl):
        datapack_ctrl.world.equipment["agv-000"].status = "assigned"
        with pytest.raises(InjectTargetError) as ei:
            _restore(datapack_ctrl)
        assert ei.value.code == "NO_ELIGIBLE_ASSET"
        assert datapack_ctrl.world.equipment["agv-000"].status == "assigned"

    def test_restore_with_nothing_faulted_is_typed(self, datapack_ctrl):
        with pytest.raises(InjectTargetError) as ei:
            _restore(datapack_ctrl)
        assert ei.value.code == "NO_ELIGIBLE_ASSET"
        assert ei.value.status_code == 409

    def test_restore_explicit_unknown_asset_is_typed(self, datapack_ctrl):
        with pytest.raises(InjectTargetError) as ei:
            _restore(datapack_ctrl, asset_id="AGV-01")
        assert ei.value.code == "ASSET_NOT_IN_ACTIVE_WORLD"


# ── F06 arming ────────────────────────────────────────────────────────────────


class TestAmbiguousWriteArming:
    def test_f06_arms_a_one_shot_fault_scoped_to_the_resolved_asset(
        self, datapack_ctrl
    ):
        result = _fault(datapack_ctrl, simulate_ambiguous_write=True)
        target = result["asset_id"]
        assert target == "agv-000"
        assert result["ambiguous_write_armed"] is True
        # the fault is in the write path: the asset stays writable
        assert result["status"] == "available"
        assert datapack_ctrl.world.equipment[target].status == "available"
        provider = datapack_ctrl.providers.equipment
        assert provider._post_mutation_fault is not None
        assert provider._post_mutation_fault_asset_id == target
        assert provider._take_post_mutation_fault("agv-001") is None
        assert provider._take_post_mutation_fault(target) is not None
        assert provider._take_post_mutation_fault(target) is None  # one-shot

    def test_reset_disarms_f06(self, datapack_ctrl):
        _fault(datapack_ctrl, simulate_ambiguous_write=True)
        _run(datapack_ctrl.reset())
        assert datapack_ctrl.providers.equipment._post_mutation_fault is None

    def test_restart_on_yaml_path_disarms_f06(self, yaml_ctrl):
        _fault(yaml_ctrl, simulate_ambiguous_write=True)
        _run(yaml_ctrl.start(SCENARIO))
        assert yaml_ctrl.providers.equipment._post_mutation_fault is None

    def test_plain_fault_does_not_arm(self, datapack_ctrl):
        result = _fault(datapack_ctrl)
        assert "ambiguous_write_armed" not in result
        assert datapack_ctrl.providers.equipment._post_mutation_fault is None


# ── YAML fallback world ───────────────────────────────────────────────────────


class TestYamlFallbackWorld:
    def test_explicit_agv_01_still_works(self, yaml_ctrl):
        result = _fault(yaml_ctrl, asset_id="AGV-01", fault_code="E_STATE_DRIFT_SIM")
        assert result == {
            "asset_id": "AGV-01",
            "status": "offline",
            "target_resolution": "explicit",
        }
        result = _restore(yaml_ctrl, asset_id="AGV-01")
        assert result["asset_id"] == "AGV-01"
        assert yaml_ctrl.world.equipment["AGV-01"].status == "available"

    def test_omitted_asset_resolves_from_yaml_world(self, yaml_ctrl):
        assert _fault(yaml_ctrl)["asset_id"] == "AGV-01"
        assert _restore(yaml_ctrl)["asset_id"] == "AGV-01"

    def test_datapack_id_is_not_in_yaml_world(self, yaml_ctrl):
        with pytest.raises(InjectTargetError) as ei:
            _fault(yaml_ctrl, asset_id="agv-000")
        assert ei.value.code == "ASSET_NOT_IN_ACTIVE_WORLD"
        assert ei.value.extra["world_source"] == "yaml"
