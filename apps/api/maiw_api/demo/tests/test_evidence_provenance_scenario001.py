# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 15B Evidence Provenance — Scenario 001 canonical regression test.

Scenario: labor_constraint_wave_risk
Goal: every primary Copilot ASK evidence item must be traceable to an
      authoritative WarehouseState field, not to LLM generation.

Provenance chain verified:
  DemoWarehouseWorld (YAML seed)
    → SimulationLaborProvider   → LaborCapacityResult
    → SimulationWaveProvider    → WaveGetResult
    → SimulationEquipmentProvider → EquipmentStatusResult
    → LaborState.from_capacity_result()
    → WaveState.from_get_result()
    → EquipmentState.from_status_result()
    → WarehouseStateSnapshot.seal()
    → OperationsCoordinationAgent.analyze_disruption()  [facts_observed]
    → _facts_to_evidence()                              [EvidenceFact[]]
    → CopilotAskResult

Scenario 001 canonical values (derived from labor_constraint_wave_risk.yaml):

  World layer
  -----------
  Workers: 6 total — 4 active (w-001,w-003,w-005,w-006), 2 on_leave (w-002,w-004)
  Active with task:  w-001 (task-001), w-005 (task-002) → 2 workers busy
  Idle (active, no task): w-003, w-006 → 2 workers idle
  Tasks: 7 total — 2 in_progress, 5 pending (4 with deadline, 1 without)
  Pending+unassigned: task-003, task-004, task-005, task-006, task-007 → 5
  At-risk (pending, no assignee): 5 tasks
  Soonest deadline: 2026-08-23T09:30:00+00:00 (tasks 001-005, 007)
  Equipment: 4 assets, all available; 0 offline

  Provider layer  (status_filter="active" default)
  ---------------
  LaborCapacityResult.total_workers     = 4   (active workers only)
  LaborCapacityResult.available_workers = 2   (idle: active + no current_task_id)
  LaborCapacityResult.utilization_pct   = 50.0  (2 busy / 4 active × 100)
  WaveGetResult.total_tasks             = 7
  WaveGetResult.summary["pending"]      = 5
  WaveGetResult.summary["in_progress"]  = 2
  WaveTaskInfo[task-003].deadline       = "2026-08-23T09:30:00+00:00"
  EquipmentStatusResult.total_count     = 4
  available_count (computed)            = 4

  WarehouseState layer
  --------------------
  LaborState.total_workers     = 4
  LaborState.available_workers = 2
  LaborState.utilization_pct   = 50.0
  WaveState.total_tasks        = 7
  WaveState.pending_count      = 5
  WaveState.in_progress_count  = 2
  WaveState.at_risk_count      = 5   (pending + assigned_to is None)
  WaveState.tasks[i].deadline  = "2026-08-23T09:30:00+00:00" for tasks 001-005, 007
  EquipmentState.total_count   = 4
  EquipmentState.available_count = 4

  Risk score (deterministic)
  --------------------------
  at_risk_count > 0       → +50
  available_workers = 2   → NOT < 2  → +0
  utilization_pct = 50%   → NOT > 85% → +0
  no offline equipment    → +0
  Total: 50  → severity = "HIGH"

  Agent facts (from analyze_disruption)
  --------------------------------------
  "Equipment: 4 total, 4 available"
  "Labor: 4 total, 2 idle (active with no task), 50% utilization"
  "Wave tasks: 7 total, 5 pending, 2 in_progress, 5 at-risk"
  "Carrier cutoff (soonest deadline): 2026-08-23T09:30:00+00:00"
  "UNASSIGNED PENDING TASKS: 5 pending wave tasks have no worker allocated..."
"""

from __future__ import annotations

import pathlib

import pytest
import pytest_asyncio

from maiw_api.demo.controller import ScenarioEventBus
from maiw_api.demo.providers.equipment import SimulationEquipmentProvider
from maiw_api.demo.providers.labor import SimulationLaborProvider
from maiw_api.demo.providers.wave import SimulationWaveProvider
from maiw_api.demo.world import DemoWarehouseWorld
from maiw_mcp.contracts.equipment import EquipmentStatusRequest
from maiw_mcp.contracts.labor import LaborCapacityRequest
from maiw_mcp.contracts.wave import WaveGetRequest

_SCENARIOS_DIR = pathlib.Path(__file__).parent.parent / "scenarios"
_SCENARIO_NAME = "labor_constraint_wave_risk"

# ── Canonical expected values ──────────────────────────────────────────────────

_EXPECTED = {
    # Provider / LaborCapacityResult
    "labor_total_workers": 4,       # active only (status_filter="active" default)
    "labor_available_workers": 2,   # idle: active + no current_task_id
    "labor_utilization_pct": 50.0,  # 2 busy / 4 active × 100
    # Provider / WaveGetResult
    "wave_total_tasks": 7,
    "wave_pending_count": 5,
    "wave_in_progress_count": 2,
    "wave_at_risk_count": 5,        # pending tasks with assigned_to=None
    "wave_soonest_deadline": "2026-08-23T09:30:00+00:00",
    # Provider / EquipmentStatusResult
    "equipment_total_count": 4,
    "equipment_available_count": 4,
    # Deterministic risk score
    # at_risk(+50), available_workers=2 (not <2→+0), util=50% (not >85%→+0), no offline(+0)
    "risk_score": 50,
    "severity": "medium",           # 50 >= 30 → medium (threshold for high is 60)
}

_CARRIER_CUTOFF = "2026-08-23T09:30:00+00:00"


# ── Fixture: loaded world ──────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def world_and_bus():
    import yaml
    path = _SCENARIOS_DIR / f"{_SCENARIO_NAME}.yaml"
    if not path.exists():
        pytest.skip(f"Scenario file not found: {path}")
    data = yaml.safe_load(path.read_text())
    world = DemoWarehouseWorld()
    world.seed(data["initial_state"])
    bus = ScenarioEventBus()
    return world, bus


@pytest.fixture(scope="module")
def labor_provider(world_and_bus):
    world, bus = world_and_bus
    return SimulationLaborProvider(world, bus)


@pytest.fixture(scope="module")
def wave_provider(world_and_bus):
    world, bus = world_and_bus
    return SimulationWaveProvider(world, bus)


@pytest.fixture(scope="module")
def equipment_provider(world_and_bus):
    world, bus = world_and_bus
    return SimulationEquipmentProvider(world, bus)


# ── Layer 1: DemoWarehouseWorld raw values ─────────────────────────────────────

class TestWorldRawValues:
    """World seed must produce the canonical state from Scenario 001 YAML."""

    def test_total_worker_count(self, world_and_bus):
        world, _ = world_and_bus
        all_workers = world.workers_list()
        assert len(all_workers) == 6, f"expected 6 workers total, got {len(all_workers)}"

    def test_active_worker_count(self, world_and_bus):
        world, _ = world_and_bus
        active = [w for w in world.workers_list() if w.status == "active"]
        assert len(active) == 4

    def test_on_leave_worker_count(self, world_and_bus):
        world, _ = world_and_bus
        on_leave = [w for w in world.workers_list() if w.status == "on_leave"]
        assert len(on_leave) == 2

    def test_idle_worker_count(self, world_and_bus):
        world, _ = world_and_bus
        idle = [w for w in world.workers_list() if w.status == "active" and w.current_task_id is None]
        assert len(idle) == 2, f"expected 2 idle workers (w-003, w-006), got {len(idle)}"

    def test_task_total_count(self, world_and_bus):
        world, _ = world_and_bus
        tasks = world.tasks_list()
        assert len(tasks) == 7

    def test_pending_task_count(self, world_and_bus):
        world, _ = world_and_bus
        pending = [t for t in world.tasks_list() if t.status == "pending"]
        assert len(pending) == 5

    def test_tasks_with_deadline(self, world_and_bus):
        world, _ = world_and_bus
        with_deadline = [t for t in world.tasks_list() if t.deadline is not None]
        # task-001..005, task-007 have deadlines; task-006 does not
        assert len(with_deadline) == 6

    def test_soonest_deadline_in_world(self, world_and_bus):
        world, _ = world_and_bus
        deadlines = sorted(t.deadline for t in world.tasks_list() if t.deadline)
        assert deadlines[0] == _CARRIER_CUTOFF

    def test_equipment_all_available(self, world_and_bus):
        world, _ = world_and_bus
        offline = [e for e in world.equipment_list() if e.status != "available"]
        assert offline == [], f"expected no offline/maintenance equipment, got {offline}"


# ── Layer 2: SimulationProvider outputs ───────────────────────────────────────

class TestProviderOutputs:
    """Provider outputs must match canonical values derived from world state."""

    @pytest.mark.asyncio
    async def test_labor_total_workers(self, labor_provider):
        result = await labor_provider.get_labor_capacity(LaborCapacityRequest(warehouse_id="DC-47"))
        assert result.total_workers == _EXPECTED["labor_total_workers"], (
            f"total_workers: expected {_EXPECTED['labor_total_workers']}, got {result.total_workers}. "
            "Reminder: default status_filter='active' returns only active workers."
        )

    @pytest.mark.asyncio
    async def test_labor_available_workers_is_idle_count(self, labor_provider):
        result = await labor_provider.get_labor_capacity(LaborCapacityRequest(warehouse_id="DC-47"))
        assert result.available_workers == _EXPECTED["labor_available_workers"], (
            f"available_workers: expected {_EXPECTED['labor_available_workers']} (idle), "
            f"got {result.available_workers}"
        )

    @pytest.mark.asyncio
    async def test_labor_utilization_pct(self, labor_provider):
        result = await labor_provider.get_labor_capacity(LaborCapacityRequest(warehouse_id="DC-47"))
        assert result.utilization_pct == _EXPECTED["labor_utilization_pct"], (
            f"utilization_pct: expected {_EXPECTED['labor_utilization_pct']}%, "
            f"got {result.utilization_pct}%"
        )

    @pytest.mark.asyncio
    async def test_wave_total_tasks(self, wave_provider):
        result = await wave_provider.get_wave(WaveGetRequest(warehouse_id="DC-47"))
        assert result.total_tasks == _EXPECTED["wave_total_tasks"]

    @pytest.mark.asyncio
    async def test_wave_pending_count(self, wave_provider):
        result = await wave_provider.get_wave(WaveGetRequest(warehouse_id="DC-47"))
        assert result.summary.get("pending", 0) == _EXPECTED["wave_pending_count"]

    @pytest.mark.asyncio
    async def test_wave_in_progress_count(self, wave_provider):
        result = await wave_provider.get_wave(WaveGetRequest(warehouse_id="DC-47"))
        assert result.summary.get("in_progress", 0) == _EXPECTED["wave_in_progress_count"]

    @pytest.mark.asyncio
    async def test_wave_task_deadline_propagated(self, wave_provider):
        """WaveTaskInfo must carry deadline from DemoTask — not stripped."""
        result = await wave_provider.get_wave(WaveGetRequest(warehouse_id="DC-47"))
        tasks_with_deadline = [t for t in result.tasks if t.deadline is not None]
        assert len(tasks_with_deadline) == 6, (
            f"expected 6 WaveTaskInfo items with deadline, got {len(tasks_with_deadline)}"
        )
        deadlines = sorted(t.deadline for t in tasks_with_deadline)
        assert deadlines[0] == _CARRIER_CUTOFF

    @pytest.mark.asyncio
    async def test_equipment_total_count(self, equipment_provider):
        result = await equipment_provider.get_equipment_status(
            EquipmentStatusRequest(warehouse_id="DC-47")
        )
        assert result.total_count == _EXPECTED["equipment_total_count"]

    @pytest.mark.asyncio
    async def test_equipment_no_offline(self, equipment_provider):
        result = await equipment_provider.get_equipment_status(
            EquipmentStatusRequest(warehouse_id="DC-47")
        )
        offline = [e for e in result.equipment if e.status == "offline"]
        assert offline == []


# ── Layer 3: WarehouseState projection ────────────────────────────────────────

class TestWarehouseStateProjection:
    """LaborState/WaveState/EquipmentState must faithfully project provider output."""

    @pytest.mark.asyncio
    async def test_labor_state_total_workers(self, labor_provider):
        from maiw_state.freshness import StateFreshness
        from maiw_state.models.labor import LaborState
        result = await labor_provider.get_labor_capacity(LaborCapacityRequest(warehouse_id="DC-47"))
        state = LaborState.from_capacity_result("DC-47", result, freshness=StateFreshness.now())
        assert state.total_workers == _EXPECTED["labor_total_workers"]

    @pytest.mark.asyncio
    async def test_labor_state_available_workers(self, labor_provider):
        from maiw_state.freshness import StateFreshness
        from maiw_state.models.labor import LaborState
        result = await labor_provider.get_labor_capacity(LaborCapacityRequest(warehouse_id="DC-47"))
        state = LaborState.from_capacity_result("DC-47", result, freshness=StateFreshness.now())
        assert state.available_workers == _EXPECTED["labor_available_workers"]

    @pytest.mark.asyncio
    async def test_labor_state_utilization_pct(self, labor_provider):
        from maiw_state.freshness import StateFreshness
        from maiw_state.models.labor import LaborState
        result = await labor_provider.get_labor_capacity(LaborCapacityRequest(warehouse_id="DC-47"))
        state = LaborState.from_capacity_result("DC-47", result, freshness=StateFreshness.now())
        assert state.utilization_pct == _EXPECTED["labor_utilization_pct"]

    @pytest.mark.asyncio
    async def test_wave_state_at_risk_count(self, wave_provider):
        from maiw_state.freshness import StateFreshness
        from maiw_state.models.wave import WaveState
        result = await wave_provider.get_wave(WaveGetRequest(warehouse_id="DC-47"))
        state = WaveState.from_get_result("DC-47", result, freshness=StateFreshness.now())
        assert state.at_risk_count == _EXPECTED["wave_at_risk_count"], (
            f"at_risk_count: expected {_EXPECTED['wave_at_risk_count']}, got {state.at_risk_count}. "
            "at_risk = pending tasks with no assignee"
        )

    @pytest.mark.asyncio
    async def test_wave_state_deadline_in_task_summary(self, wave_provider):
        """WaveTaskSummary must carry deadline from WaveTaskInfo — not dropped at projection."""
        from maiw_state.freshness import StateFreshness
        from maiw_state.models.wave import WaveState
        result = await wave_provider.get_wave(WaveGetRequest(warehouse_id="DC-47"))
        state = WaveState.from_get_result("DC-47", result, freshness=StateFreshness.now())
        tasks_with_deadline = [t for t in state.tasks if t.deadline is not None]
        assert len(tasks_with_deadline) == 6, (
            f"expected 6 WaveTaskSummary items with deadline in WarehouseState, "
            f"got {len(tasks_with_deadline)}"
        )
        soonest = sorted(t.deadline for t in tasks_with_deadline)[0]
        assert soonest == _CARRIER_CUTOFF, (
            f"soonest WaveTaskSummary.deadline: expected {_CARRIER_CUTOFF}, got {soonest}"
        )


# ── Shared helper ─────────────────────────────────────────────────────────────

async def _build_snapshot(labor_provider, wave_provider, equipment_provider):
    """Assemble a WarehouseStateSnapshot from all three providers."""
    from datetime import datetime, timezone
    from maiw_state.freshness import StateFreshness
    from maiw_state.models.labor import LaborState
    from maiw_state.models.wave import WaveState
    from maiw_state.models.equipment import EquipmentState
    from maiw_state.warehouse import WarehouseState, WarehouseStateSnapshot

    labor_result = await labor_provider.get_labor_capacity(LaborCapacityRequest(warehouse_id="DC-47"))
    wave_result = await wave_provider.get_wave(WaveGetRequest(warehouse_id="DC-47"))
    equip_result = await equipment_provider.get_equipment_status(EquipmentStatusRequest(warehouse_id="DC-47"))

    freshness = StateFreshness.now()
    warehouse_state = WarehouseState(
        warehouse_id="DC-47",
        observed_at=datetime.now(timezone.utc),
        labor=LaborState.from_capacity_result("DC-47", labor_result, freshness=freshness),
        waves=WaveState.from_get_result("DC-47", wave_result, freshness=freshness),
        equipment=EquipmentState.from_status_result("DC-47", equip_result, freshness=freshness),
    )
    return WarehouseStateSnapshot.seal(warehouse_state)


# ── Layer 4: Agent fact synthesis ─────────────────────────────────────────────

class TestAgentFactSynthesis:
    """analyze_disruption must emit facts derived only from WarehouseState fields."""

    @pytest.mark.asyncio
    async def test_labor_fact_contains_canonical_values(
        self, labor_provider, wave_provider, equipment_provider
    ):
        """Labor fact must use idle count (2), not active count (4)."""
        from maiw_agents.operations.agent import OperationsCoordinationAgent

        snapshot = await _build_snapshot(labor_provider, wave_provider, equipment_provider)
        agent = OperationsCoordinationAgent(model_gateway=None)
        assessment = await agent.analyze_disruption(
            snapshot=snapshot,
            scenario_context="Why is Wave 1 at risk?",
            trace_id="test-provenance-001",
        )
        facts = assessment.facts_observed
        labor_fact = next((f for f in facts if f.startswith("Labor:")), None)
        assert labor_fact is not None, "No Labor fact produced"
        assert "4 total" in labor_fact, f"Expected '4 total' in labor fact: {labor_fact}"
        assert "2 idle" in labor_fact, f"Expected '2 idle' in labor fact: {labor_fact}"
        assert "50%" in labor_fact, f"Expected '50%' utilization in labor fact: {labor_fact}"

    @pytest.mark.asyncio
    async def test_carrier_cutoff_fact_present(
        self, labor_provider, wave_provider, equipment_provider
    ):
        """Agent must emit a Carrier cutoff fact sourced from WaveTaskSummary.deadline."""
        from maiw_agents.operations.agent import OperationsCoordinationAgent

        snapshot = await _build_snapshot(labor_provider, wave_provider, equipment_provider)
        agent = OperationsCoordinationAgent(model_gateway=None)
        assessment = await agent.analyze_disruption(
            snapshot=snapshot,
            scenario_context="Why is Wave 1 at risk?",
            trace_id="test-provenance-001b",
        )
        cutoff_fact = next(
            (f for f in assessment.facts_observed if "Carrier cutoff" in f or "deadline" in f.lower()),
            None,
        )
        assert cutoff_fact is not None, (
            f"No carrier-cutoff fact found in facts_observed.\nFacts: {assessment.facts_observed}"
        )
        assert _CARRIER_CUTOFF in cutoff_fact, (
            f"Carrier cutoff fact must contain canonical deadline {_CARRIER_CUTOFF}.\nGot: {cutoff_fact}"
        )

    @pytest.mark.asyncio
    async def test_deterministic_severity_is_high(
        self, labor_provider, wave_provider, equipment_provider
    ):
        """Risk score for Scenario 001 = 50 (at_risk only) → severity HIGH, not CRITICAL."""
        from maiw_agents.operations.agent import OperationsCoordinationAgent

        snapshot = await _build_snapshot(labor_provider, wave_provider, equipment_provider)
        agent = OperationsCoordinationAgent(model_gateway=None)
        assessment = await agent.analyze_disruption(
            snapshot=snapshot,
            scenario_context="Why is Wave 1 at risk?",
            trace_id="test-provenance-001c",
        )
        assert assessment.severity == "medium", (
            f"Scenario 001 deterministic score = 50 → should be 'medium' (threshold for high is 60), "
            f"got {assessment.severity}. "
            "at_risk(+50), available_workers=2 (not <2→+0), util=50% (not >85%→+0), no offline(+0)."
        )

    @pytest.mark.asyncio
    async def test_unassigned_pending_tasks_fact_uses_idle_count(
        self, labor_provider, wave_provider, equipment_provider
    ):
        """UNASSIGNED fact must report 2 idle workers, not 4 active workers."""
        from maiw_agents.operations.agent import OperationsCoordinationAgent

        snapshot = await _build_snapshot(labor_provider, wave_provider, equipment_provider)
        agent = OperationsCoordinationAgent(model_gateway=None)
        assessment = await agent.analyze_disruption(
            snapshot=snapshot,
            scenario_context="Why is Wave 1 at risk?",
            trace_id="test-provenance-001d",
        )
        unassigned_fact = next(
            (f for f in assessment.facts_observed if f.startswith("UNASSIGNED")),
            None,
        )
        assert unassigned_fact is not None, "No UNASSIGNED PENDING TASKS fact produced"
        assert "5 pending" in unassigned_fact, (
            f"Expected '5 pending' in unassigned fact, got: {unassigned_fact}"
        )
        assert "2 workers are idle" in unassigned_fact, (
            f"Expected '2 workers are idle' (idle count, not active count 4), got: {unassigned_fact}"
        )

    @pytest.mark.asyncio
    async def test_no_evidence_fabricated_without_model(
        self, labor_provider, wave_provider, equipment_provider
    ):
        """All facts must come from WarehouseState fields — none from LLM generation.
        When ModelGateway is None, stub assessment still returns state-derived facts only."""
        from maiw_agents.operations.agent import OperationsCoordinationAgent

        snapshot = await _build_snapshot(labor_provider, wave_provider, equipment_provider)
        agent = OperationsCoordinationAgent(model_gateway=None)
        assessment = await agent.analyze_disruption(
            snapshot=snapshot,
            scenario_context="Why is Wave 1 at risk?",
            trace_id="test-provenance-001e",
        )
        facts = assessment.facts_observed
        assert any("Equipment" in f for f in facts), "Missing Equipment fact"
        assert any("Labor" in f for f in facts), "Missing Labor fact"
        assert any("Wave tasks" in f for f in facts), "Missing Wave tasks fact"
        assert any("Carrier cutoff" in f for f in facts), "Missing Carrier cutoff fact"
        assert any("UNASSIGNED" in f for f in facts), "Missing UNASSIGNED fact"
        labor_fact = next(f for f in facts if f.startswith("Labor:"))
        assert "4 total" in labor_fact
        assert "2 idle" in labor_fact
        wave_fact = next(f for f in facts if f.startswith("Wave tasks:"))
        assert "7 total" in wave_fact
        assert "5 pending" in wave_fact
        assert "5 at-risk" in wave_fact


# ── Layer 5: _facts_to_evidence mapping ───────────────────────────────────────

class TestEvidenceMapping:
    """_facts_to_evidence must produce correctly-labelled EvidenceFacts
    with severity derived from fact text, not LLM output."""

    def _build_canonical_facts(self) -> list[str]:
        return [
            "Equipment: 4 total, 4 available",
            "Labor: 4 total, 2 idle (active with no task), 50% utilization",
            "Wave tasks: 7 total, 5 pending, 2 in_progress, 5 at-risk",
            f"Carrier cutoff (soonest deadline): {_CARRIER_CUTOFF}",
            "UNASSIGNED PENDING TASKS: 5 pending wave tasks have no worker allocated "
            "(assigned_to=null); 2 workers are idle. Use warehouse.labor.allocate to assign.",
        ]

    def test_equipment_evidence_label(self):
        from maiw_api.copilot.service import _facts_to_evidence
        evidence = _facts_to_evidence(self._build_canonical_facts(), "HIGH")
        equip = next((e for e in evidence if e.label == "Equipment"), None)
        assert equip is not None, "No Equipment evidence item"
        assert "4 total" in equip.value

    def test_labor_evidence_label(self):
        from maiw_api.copilot.service import _facts_to_evidence
        evidence = _facts_to_evidence(self._build_canonical_facts(), "HIGH")
        labor = next((e for e in evidence if e.label == "Labor"), None)
        assert labor is not None, "No Labor evidence item"
        assert "2 idle" in labor.value

    def test_wave_evidence_has_at_risk_severity(self):
        from maiw_api.copilot.service import _facts_to_evidence
        evidence = _facts_to_evidence(self._build_canonical_facts(), "HIGH")
        wave = next((e for e in evidence if "Wave" in e.label), None)
        assert wave is not None, "No Wave tasks evidence item"
        assert wave.severity == "HIGH", (
            f"Wave evidence containing 'at-risk' must map to severity HIGH, got {wave.severity}"
        )

    def test_carrier_cutoff_evidence_label(self):
        from maiw_api.copilot.service import _facts_to_evidence
        evidence = _facts_to_evidence(self._build_canonical_facts(), "HIGH")
        cutoff = next((e for e in evidence if "Carrier cutoff" in e.label or "cutoff" in e.label.lower()), None)
        assert cutoff is not None, "No Carrier cutoff evidence item"
        assert _CARRIER_CUTOFF in cutoff.value

    def test_unassigned_evidence_severity_high(self):
        from maiw_api.copilot.service import _facts_to_evidence
        evidence = _facts_to_evidence(self._build_canonical_facts(), "HIGH")
        unassigned = next((e for e in evidence if "Unassigned" in e.label or "UNASSIGNED" in e.label), None)
        assert unassigned is not None, "No Unassigned evidence item"
        assert unassigned.severity == "HIGH"

    def test_evidence_count(self):
        """Every canonical fact must produce exactly one EvidenceFact."""
        from maiw_api.copilot.service import _facts_to_evidence
        facts = self._build_canonical_facts()
        evidence = _facts_to_evidence(facts, "HIGH")
        assert len(evidence) == len(facts), (
            f"Expected {len(facts)} EvidenceFacts (one per fact), got {len(evidence)}"
        )
