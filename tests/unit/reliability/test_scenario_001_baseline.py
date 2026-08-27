# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 10E Batch 6 — Scenario 001 normal baseline assertions.

Verifies that the canonical `labor_constraint_wave_risk` scenario configuration
is frozen and matches the established reliability reference. This test does NOT
run the full simulation (which requires NIM + MCP infrastructure) — it validates
the structural invariants of the scenario definition.

Published baseline (established in Phase 10D / Batch 5):
  Scenario:   labor_constraint_wave_risk
  Seed:       42
  Offset:     5400s (shift 1.5h in)
  CONTROL:    no recovery within 1800 simulated seconds
  MAIW:       recovery ~300 simulated seconds
              backlog reduction ~92%
              wave-risk reduction ~86.7%

Any deviation from the frozen scenario config invalidates the published metrics.
"""

from __future__ import annotations

import os
import sys

import pytest
import yaml

# Ensure apps/api is importable
_REPO_ROOT = os.path.join(os.path.dirname(__file__), "../../..")
sys.path.insert(0, os.path.join(_REPO_ROOT, "apps/api"))

_SCENARIOS_DIR = os.path.join(_REPO_ROOT, "apps/api/maiw_api/demo/scenarios")
_SCENARIO_FILE = os.path.join(_SCENARIOS_DIR, "labor_constraint_wave_risk.yaml")

# ---------------------------------------------------------------------------
# Frozen scenario invariants (established baseline — do not change these)
# ---------------------------------------------------------------------------

FROZEN_SEED = 42
FROZEN_CLOCK_OFFSET = 5400
FROZEN_SCENARIO_NAME = "labor_constraint_wave_risk"
FROZEN_DISRUPTION_EVENT_TYPES = {"worker_absence"}

# Published reliability baseline metrics (for documentation / artifact generation)
BASELINE_METRICS = {
    "control_recovery_reached": False,
    "control_time_limit_s": 1800,
    "maiw_time_to_recovery_s": 300,
    "backlog_reduction_pct": 92.0,
    "wave_risk_reduction_pct": 86.7,
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def scenario_yaml():
    with open(_SCENARIO_FILE, "r") as f:
        return yaml.safe_load(f)


def test_scenario_file_exists():
    """Scenario 001 YAML must exist at the canonical path."""
    assert os.path.exists(_SCENARIO_FILE), (
        f"Scenario file not found: {_SCENARIO_FILE}"
    )


def test_scenario_name_frozen(scenario_yaml):
    """Scenario name is frozen — any rename breaks the published baseline."""
    assert scenario_yaml["name"] == FROZEN_SCENARIO_NAME


def test_scenario_seed_frozen(scenario_yaml):
    """RNG seed must be 42 — changing it invalidates all published metrics."""
    assert scenario_yaml["rng_seed"] == FROZEN_SEED


def test_scenario_clock_offset_frozen(scenario_yaml):
    """Clock offset must be 5400s — changes initial disruption timing."""
    assert scenario_yaml["clock_offset_seconds"] == FROZEN_CLOCK_OFFSET


def test_scenario_has_timed_events(scenario_yaml):
    """Scenario must have timed_events (the labor disruption)."""
    events = scenario_yaml.get("timed_events", [])
    assert len(events) > 0, "Scenario has no timed events"


def test_scenario_has_worker_absence_event(scenario_yaml):
    """worker_absence event must be present (primary disruption for Scenario 001)."""
    event_types = {e["type"] for e in scenario_yaml.get("timed_events", [])}
    assert "worker_absence" in event_types, (
        f"worker_absence event not found. Event types: {event_types}"
    )


def test_scenario_has_recovery_conditions(scenario_yaml):
    """Recovery conditions must be defined (used to compute time_to_recovery)."""
    recovery = scenario_yaml.get("recovery", {})
    assert recovery, "Scenario must define recovery conditions"


def test_scenario_has_initial_state(scenario_yaml):
    """Initial state must be defined with expected entity counts."""
    init = scenario_yaml.get("initial_state", {})
    assert init, "Scenario must define initial_state"


def test_scenario_has_labor_workers(scenario_yaml):
    """Labor constraint scenario must define workers."""
    init = scenario_yaml.get("initial_state", {})
    workers = init.get("workers", [])
    assert len(workers) > 0, "Scenario must have workers defined"


def test_scenario_has_wave_tasks(scenario_yaml):
    """Wave-risk scenario must define tasks (stored under 'tasks' key in initial_state)."""
    init = scenario_yaml.get("initial_state", {})
    # tasks may be keyed as 'tasks' or 'wave_tasks'
    tasks = init.get("tasks", init.get("wave_tasks", []))
    assert len(tasks) > 0, "Scenario must have tasks defined in initial_state"


def test_baseline_metrics_documented():
    """Baseline metrics must be defined (documentation invariant)."""
    assert BASELINE_METRICS["maiw_time_to_recovery_s"] == 300
    assert BASELINE_METRICS["backlog_reduction_pct"] == 92.0
    assert BASELINE_METRICS["wave_risk_reduction_pct"] == 86.7
    assert BASELINE_METRICS["control_recovery_reached"] is False


def test_scenario_registry_contains_five_scenarios():
    """Exactly five scenarios must be registered (frozen scenario registry)."""
    import glob
    scenario_files = glob.glob(os.path.join(_SCENARIOS_DIR, "*.yaml"))
    assert len(scenario_files) == 5, (
        f"Expected 5 scenario files, found {len(scenario_files)}: {scenario_files}"
    )


def test_golden_invariant_checker():
    """ReliabilityResult golden invariant checker works correctly."""
    from fault_framework.models import ReliabilityResult, check_golden_invariants, GoldenInvariantViolation

    # Clean result — should pass
    result = ReliabilityResult(fault_id=None)
    check_golden_invariants(result)  # should not raise
    assert result.safety_pass is True

    # Invariant A violation
    bad = ReliabilityResult(fault_id="TEST", unauthorized_writes=1)
    with pytest.raises(GoldenInvariantViolation) as exc_info:
        check_golden_invariants(bad)
    assert "INVARIANT A" in str(exc_info.value)
    assert bad.safety_pass is False

    # Invariant B violation
    bad2 = ReliabilityResult(fault_id="TEST", duplicate_writes=2)
    with pytest.raises(GoldenInvariantViolation):
        check_golden_invariants(bad2)

    # Invariant C violation
    bad3 = ReliabilityResult(fault_id="TEST", false_successes=1)
    with pytest.raises(GoldenInvariantViolation):
        check_golden_invariants(bad3)
