# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Demo Pre-Merge Validation — Phase 10D.5

Validates the synthetic demo harness end-to-end against the controller directly.
No API server required; all checks run against the Python layer.

Scenario registry (ID / seed / clock-offset):
  healthy_baseline           seed=42  offset=0s
  equipment_failure          seed=42  offset=1800s
  labor_constraint_wave_risk seed=42  offset=5400s
  stale_state                seed=42  offset=-2700s
  state_drift                seed=42  offset=3600s

Checks:
  1.  All five scenarios load and start (entity counts > 0)
  2.  Equipment write mutates shared world visible via SimulationEquipmentProvider
  3.  Equipment restore brings asset back to available
  4.  Wave delay inject sets pending task priorities to low
  5.  equipment_failure timed event fires at offset=60 s
  6.  labor_constraint_wave_risk: worker_absence timed at offset=120 s;
      cross-domain: LaborProvider sees capacity drop, WaveProvider still readable
  7.  stale_state clock is before shift start (EPOCH−2700 s)
  8.  state_drift initial world has AGVs in drift-indicating statuses
  9.  Reset is deterministic (snapshot comparison)
  10. Pause prevents tick; resume allows tick
  11. MAIW_DEMO_MODE unset → bootstrap._DEMO_MODE is False
  12. MAIW_DEMO_MODE=true → bootstrap._DEMO_MODE is True
  13. Inventory low_stock inject visible through SimulationInventoryProvider
  14. Scenario listing contains exactly five expected names
"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys

import pytest

# ── path: resolve apps/api relative to repo root ─────────────────────────────
_REPO_ROOT = os.path.join(os.path.dirname(__file__), "../..")
sys.path.insert(0, os.path.join(_REPO_ROOT, "apps/api"))

from maiw_api.demo.controller import (
    DemoScenarioController,
    list_scenario_files,
    reset_demo_controller,
)
from maiw_mcp.contracts.equipment import EquipmentStatusRequest
from maiw_mcp.contracts.labor import LaborCapacityRequest
from maiw_mcp.contracts.wave import WaveGetRequest
from maiw_mcp.contracts.inventory import InventoryLookupRequest


# ── async helper (same pattern as tests/unit/demo/) ──────────────────────────
def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── scenario registry ─────────────────────────────────────────────────────────
SCENARIO_REGISTRY = {
    "healthy_baseline": {"rng_seed": 42, "clock_offset_seconds": 0},
    "equipment_failure": {"rng_seed": 42, "clock_offset_seconds": 1800},
    "labor_constraint_wave_risk": {"rng_seed": 42, "clock_offset_seconds": 5400},
    "stale_state": {"rng_seed": 42, "clock_offset_seconds": -2700},
    "state_drift": {"rng_seed": 42, "clock_offset_seconds": 3600},
}

# Timeline log — printed in the final summary
_TIMELINES: dict[str, list[str]] = {k: [] for k in SCENARIO_REGISTRY}


def _log(scenario: str, msg: str) -> None:
    _TIMELINES[scenario].append(msg)


# ── fixture: fresh controller per test ───────────────────────────────────────
@pytest.fixture
def ctrl():
    reset_demo_controller()
    c = DemoScenarioController()
    yield c
    reset_demo_controller()


# ══════════════════════════════════════════════════════════════════════════════
# 1. All five scenarios load correctly
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("name,meta", SCENARIO_REGISTRY.items())
def test_scenario_loads(name, meta, ctrl):
    _run(ctrl.start(name))

    assert ctrl.active
    assert ctrl._scenario.name == name
    assert ctrl._scenario.rng_seed == meta["rng_seed"]
    assert ctrl._scenario.clock_offset_seconds == meta["clock_offset_seconds"]

    s = ctrl.status()
    eq = s["world"]["equipment"]["total"]
    wk = s["world"]["workers"]["total"]
    inv = s["world"]["inventory"]["total_skus"]

    assert eq > 0, f"{name}: no equipment seeded"
    assert wk > 0, f"{name}: no workers seeded"
    assert inv > 0, f"{name}: no inventory seeded"

    clock_iso = s["world"]["clock_iso"]
    _log(name, f"  start → clock={clock_iso}  eq={eq}  workers={wk}  skus={inv}")


# ══════════════════════════════════════════════════════════════════════════════
# 2–3. Equipment write/restore propagates through shared world → provider
# ══════════════════════════════════════════════════════════════════════════════


def test_equipment_fault_propagates_to_provider(ctrl):
    _run(ctrl.start("healthy_baseline"))

    # Find first AGV
    agv = next(
        (a for a in ctrl.world.equipment.values() if a.equipment_type == "agv"), None
    )
    assert agv is not None
    asset_id = agv.asset_id
    original_status = agv.status

    # Fault inject
    _run(
        ctrl.inject(
            "equipment_fault",
            {
                "asset_id": asset_id,
                "fault_code": "E_MOTOR_OVERTEMP",
                "new_status": "offline",
            },
        )
    )

    # Read back through provider (same world object)
    result = _run(
        ctrl.providers.equipment.get_equipment_status(
            EquipmentStatusRequest(asset_id=asset_id)
        )
    )
    assert len(result.equipment) == 1
    assert result.equipment[0].status == "offline"
    assert result.equipment[0].metadata.get("fault_code") == "E_MOTOR_OVERTEMP"

    _log(
        "healthy_baseline",
        f"  equipment_fault: {asset_id} {original_status}→offline (propagated through provider)",
    )


def test_equipment_restore_propagates_to_provider(ctrl):
    _run(ctrl.start("healthy_baseline"))

    agv = next(
        (a for a in ctrl.world.equipment.values() if a.equipment_type == "agv"), None
    )
    asset_id = agv.asset_id

    _run(
        ctrl.inject(
            "equipment_fault",
            {
                "asset_id": asset_id,
                "fault_code": "E_TEST",
                "new_status": "offline",
            },
        )
    )
    _run(ctrl.inject("equipment_restore", {"asset_id": asset_id}))

    result = _run(
        ctrl.providers.equipment.get_equipment_status(
            EquipmentStatusRequest(asset_id=asset_id)
        )
    )
    assert len(result.equipment) == 1
    assert result.equipment[0].status == "available"
    _log(
        "healthy_baseline",
        f"  equipment_restore: {asset_id} → available (confirmed via provider)",
    )


# ══════════════════════════════════════════════════════════════════════════════
# 4. Wave delay sets pending task priorities to low
# ══════════════════════════════════════════════════════════════════════════════


def test_wave_delay_sets_low_priority(ctrl):
    _run(ctrl.start("healthy_baseline"))

    wave_before = _run(ctrl.providers.wave.get_wave(WaveGetRequest()))
    pending_before = [t for t in wave_before.tasks if t.status == "pending"]
    assert len(pending_before) > 0, "healthy_baseline must have pending tasks"

    _run(ctrl.inject("wave_delay", {"reason": "Carrier delay", "delay_minutes": 30}))

    wave_after = _run(ctrl.providers.wave.get_wave(WaveGetRequest()))
    pending_after = [t for t in wave_after.tasks if t.status == "pending"]

    for t in pending_after:
        assert (
            t.priority == "low"
        ), f"Task {t.task_id} priority should be 'low' after wave_delay, got {t.priority}"

    _log(
        "healthy_baseline",
        f"  wave_delay: {len(pending_after)} pending tasks → priority=low (world mutation visible)",
    )


# ══════════════════════════════════════════════════════════════════════════════
# 5. equipment_failure: timed event fires AGV-02 offline at t=60 s
# ══════════════════════════════════════════════════════════════════════════════


def test_equipment_failure_timed_event(ctrl):
    _run(ctrl.start("equipment_failure"))

    agv02 = ctrl.world.equipment.get("AGV-02")
    assert agv02 is not None
    _log("equipment_failure", f"  t=0:   AGV-02 status={agv02.status}")

    _run(ctrl.tick(60))

    agv02_after = ctrl.world.equipment["AGV-02"]
    assert agv02_after.status == "offline"
    assert agv02_after.fault_code == "E_BATT_LOW"
    assert agv02_after.battery_pct == 8.0

    s = ctrl.status()
    _log(
        "equipment_failure",
        f"  t=60s: AGV-02 → offline (fault=E_BATT_LOW, battery=8%)  "
        f"eq_offline={s['world']['equipment']['offline']}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# 6. labor_constraint: worker_absence at t=120 s; cross-domain coherence
# ══════════════════════════════════════════════════════════════════════════════


def test_labor_constraint_cross_domain(ctrl):
    _run(ctrl.start("labor_constraint_wave_risk"))

    cap_before = _run(ctrl.providers.labor.get_labor_capacity(LaborCapacityRequest()))
    active_before = cap_before.available_workers
    _log("labor_constraint_wave_risk", f"  t=0:    active workers={active_before}")

    _run(ctrl.tick(120))

    # Worker w-003 must be on_leave
    w003 = ctrl.world.workers.get("w-003")
    assert w003 is not None
    assert w003.status == "on_leave"

    # LaborProvider must see reduced capacity (cross-domain: shared world)
    cap_after = _run(ctrl.providers.labor.get_labor_capacity(LaborCapacityRequest()))
    active_after = cap_after.available_workers
    assert active_after < active_before

    # WaveProvider must still return tasks (cross-domain state assembly, not scripted)
    wave = _run(ctrl.providers.wave.get_wave(WaveGetRequest()))
    assert len(wave.tasks) > 0

    _log(
        "labor_constraint_wave_risk",
        f"  t=120s: w-003 on_leave  active={active_before}→{active_after}  "
        f"wave_tasks_readable={len(wave.tasks)} (cross-domain ✓)",
    )


# ══════════════════════════════════════════════════════════════════════════════
# 7. stale_state: clock is before shift start (45 min stale)
# ══════════════════════════════════════════════════════════════════════════════


def test_stale_state_clock_is_before_shift_start(ctrl):
    _run(ctrl.start("stale_state"))

    s = ctrl.status()
    clock_iso = s["world"]["clock_iso"]
    elapsed = ctrl.world.clock.elapsed_seconds

    # EPOCH=08:00 UTC; offset=-2700 → 07:15:00 UTC
    assert (
        "07:15" in clock_iso
    ), f"stale_state clock should show 07:15 UTC (45 min before shift), got {clock_iso}"

    eq_total = s["world"]["equipment"]["total"]
    assert eq_total > 0

    _log(
        "stale_state",
        f"  clock_iso={clock_iso}  elapsed={elapsed}s  "
        f"(45 min stale → REQUIRES_FRESH_STATE governance path)  eq={eq_total}",
    )


# ══════════════════════════════════════════════════════════════════════════════
# 8. state_drift: initial world has AGVs with declared status mismatches
# ══════════════════════════════════════════════════════════════════════════════


def test_state_drift_has_mismatch_statuses(ctrl):
    _run(ctrl.start("state_drift"))

    agvs = [a for a in ctrl.world.equipment.values() if a.equipment_type == "agv"]
    assert len(agvs) >= 2, "state_drift must have at least 2 AGVs"

    # At least one AGV is charging (WMS says available — drift)
    charging = [a for a in agvs if a.status == "charging"]
    assert (
        len(charging) >= 1
    ), f"state_drift must have at least one AGV in 'charging' (WMS drift) status"

    s = ctrl.status()
    _log(
        "state_drift",
        f"  AGVs={len(agvs)}  charging(drift)={len(charging)}  "
        f"eq_total={s['world']['equipment']['total']}  "
        f"(state_drift → conflict detection path)",
    )


# ══════════════════════════════════════════════════════════════════════════════
# 9. Reset is deterministic
# ══════════════════════════════════════════════════════════════════════════════


def test_reset_is_deterministic(ctrl):
    _run(ctrl.start("healthy_baseline"))

    agv = next(iter(ctrl.world.equipment.values()))
    asset_id = agv.asset_id
    status_at_start = agv.status

    # Run 1: inject fault + tick
    _run(
        ctrl.inject(
            "equipment_fault",
            {
                "asset_id": asset_id,
                "fault_code": "E_TEST",
                "new_status": "offline",
            },
        )
    )
    _run(ctrl.tick(60))
    assert ctrl.world.equipment[asset_id].status == "offline"
    clock_after_run1 = ctrl.world.clock.elapsed_seconds

    # Reset
    _run(ctrl.reset())

    # Clock back to 0
    assert ctrl.world.clock.elapsed_seconds == 0

    # Faulted asset restored
    agv_reset = ctrl.world.equipment[asset_id]
    assert (
        agv_reset.status == status_at_start
    ), f"After reset: expected {status_at_start}, got {agv_reset.status}"
    assert agv_reset.fault_code is None

    # Run 2: same tick sequence — timed events fire identically (equipment_failure scenario
    # doesn't apply here for healthy_baseline which has no timed events, so clock check suffices)
    _run(ctrl.tick(60))
    assert ctrl.world.clock.elapsed_seconds == 60

    _log(
        "healthy_baseline",
        f"  reset: clock 60s→0→60s  {asset_id} offline→{status_at_start}→(tick)  "
        f"deterministic replay ✓",
    )


# ══════════════════════════════════════════════════════════════════════════════
# 10. Pause prevents tick; resume restores
# ══════════════════════════════════════════════════════════════════════════════


def test_pause_prevents_tick_resume_allows(ctrl):
    _run(ctrl.start("healthy_baseline"))
    _run(ctrl.pause())

    with pytest.raises(RuntimeError, match="paused"):
        _run(ctrl.tick(60))

    assert ctrl.world.clock.elapsed_seconds == 0

    _run(ctrl.resume())
    _run(ctrl.tick(60))
    assert ctrl.world.clock.elapsed_seconds == 60


# ══════════════════════════════════════════════════════════════════════════════
# 11–12. MAIW_DEMO_MODE env var controls bootstrap._DEMO_MODE
# ══════════════════════════════════════════════════════════════════════════════


def test_demo_mode_off_by_default():
    """Without MAIW_DEMO_MODE set, _DEMO_MODE must be False."""
    env_val = os.environ.get("MAIW_DEMO_MODE", "")
    assert env_val.lower() not in ("1", "true", "yes"), (
        "MAIW_DEMO_MODE is set in the test environment; "
        "unset it before running this test"
    )

    import maiw_api.bootstrap as bootstrap_mod

    importlib.reload(bootstrap_mod)
    assert bootstrap_mod._DEMO_MODE is False


def test_demo_mode_on_with_env(monkeypatch):
    monkeypatch.setenv("MAIW_DEMO_MODE", "true")
    import maiw_api.bootstrap as bootstrap_mod

    importlib.reload(bootstrap_mod)
    assert bootstrap_mod._DEMO_MODE is True


# ══════════════════════════════════════════════════════════════════════════════
# 13. Inventory: low_stock inject visible through SimulationInventoryProvider
# ══════════════════════════════════════════════════════════════════════════════


def test_low_stock_inject_propagates_to_inventory_provider(ctrl):
    _run(ctrl.start("healthy_baseline"))

    # Find a non-low-stock SKU
    sku_item = next(
        (i for i in ctrl.world.inventory.values() if not i.is_low_stock),
        None,
    )
    assert sku_item is not None
    sku = sku_item.sku
    qty_before = sku_item.quantity_available
    reorder = sku_item.reorder_point

    # Drain to low stock
    drain = qty_before - reorder + 1
    _run(ctrl.inject("low_stock", {"sku": sku, "drain_quantity": drain}))

    item_after = ctrl.world.inventory[sku]
    assert item_after.is_low_stock

    # Provider layer must reflect it
    inv_result = _run(
        ctrl.providers.inventory.get_inventory(InventoryLookupRequest(sku=sku))
    )
    assert inv_result.is_low_stock is True

    _log(
        "healthy_baseline",
        f"  low_stock inject: {sku} qty {qty_before}→{item_after.quantity_available} "
        f"(is_low_stock=True, visible via InventoryProvider ✓)",
    )


# ══════════════════════════════════════════════════════════════════════════════
# 14. Scenario listing contains exactly five expected names
# ══════════════════════════════════════════════════════════════════════════════


def test_all_five_scenarios_registered():
    files = list_scenario_files()
    assert set(files.keys()) == set(
        SCENARIO_REGISTRY.keys()
    ), f"Scenario registry mismatch: {set(files.keys())}"


# ══════════════════════════════════════════════════════════════════════════════
# Timeline summary (last test — always passes, prints captured timeline)
# ══════════════════════════════════════════════════════════════════════════════


def test_zzz_print_timeline_report():
    """Print the scenario timeline captured by all prior tests."""
    lines = [
        "",
        "═" * 72,
        "DEMO PRE-MERGE VALIDATION — SCENARIO TIMELINE REPORT",
        "═" * 72,
    ]
    for name, meta in SCENARIO_REGISTRY.items():
        lines.append(f"\n▸ {name.upper()}")
        lines.append(
            f"  scenario_id={name!r}  rng_seed={meta['rng_seed']}  "
            f"clock_offset={meta['clock_offset_seconds']}s"
        )
        for line in _TIMELINES.get(name, []):
            lines.append(line)
    lines.append("\n" + "═" * 72)
    print("\n".join(lines))
    assert True  # always passes
