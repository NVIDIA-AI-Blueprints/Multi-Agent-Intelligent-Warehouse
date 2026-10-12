# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.0.1 final pre-merge — NEW5-P2-01 unit coverage: ``NOT_APPLIED`` is trusted
only when the whole response is internally consistent and explicitly proves a
rejection before any mutation (``maiw_mcp.write_disposition``).

* the strict predicates for both shapes (``isError`` structuredContent and
  non-error write results), case by case (spec §4 A–E);
* the executor's non-error path (in-process skills, so the contract-typed
  results are exercised without the MCP client's own check);
* the shipped equipment / labor / wave MCP servers' genuine pre-mutation
  rejections still pass the strict check through the real ``MAIWMCPClient``
  (in-memory transport, real tool functions, demo simulation providers).

The end-to-end proofs over real streamable HTTP through the canonical app are
in ``tests/api/test_final_contradictory_not_applied.py``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from maiw_decision.models import DecisionOutcome, DecisionResult
from maiw_decision.proposal import ActionProposal
from maiw_execution import (
    EquipmentActionExecutor,
    ExecutionOutcome,
    ExecutionRegistry,
    LaborActionExecutor,
    WaveActionExecutor,
    classify_write_failure,
)
from maiw_mcp.errors import (
    MCPContractError,
    MCPDispatchOutcomeUnknown,
    MCPResultOutcomeUnknown,
    MCPToolError,
    MCPToolNotApplied,
)
from maiw_mcp.write_disposition import (
    KNOWN_REJECTION_CODES,
    NOT_APPLIED,
    certifies_not_applied,
    certifies_not_applied_result,
    claims_not_applied,
    describe_disposition,
    not_applied_payload,
    not_applied_result,
    not_applied_violations,
)

CLEAN_ERROR = {
    "execution_disposition": "NOT_APPLIED",
    "rejection_code": "PRECONDITION_FAILED",
    "message": "no active assignment",
}

CLEAN_RESULT = {
    "success": False,
    "proposal_id": "p",
    "decision_id": "d",
    "execution_id": "e",
    "outcome": "conflict",
    "execution_disposition": "NOT_APPLIED",
    "source": "test",
    "message": "already assigned to another task",
}

# ── error-result shape (isError structuredContent) ────────────────────────────


@pytest.mark.parametrize("code", sorted(KNOWN_REJECTION_CODES))
def test_E_clean_error_payload_is_trusted(code):
    payload = not_applied_payload("rejected", code)
    assert certifies_not_applied(payload) is True
    assert describe_disposition(payload) == NOT_APPLIED
    assert not_applied_violations(payload, error_result=True) == []
    # the message is optional
    assert certifies_not_applied({k: v for k, v in payload.items() if k != "message"})


def test_shipped_not_applied_result_is_trusted_and_rejects_unknown_codes():
    result = not_applied_result("rejected", "NOT_FOUND")
    assert result.is_error is True
    assert certifies_not_applied(result.structured_content)
    assert json.loads(result.content[0].text) == result.structured_content
    with pytest.raises(ValueError):
        not_applied_payload("rejected", "BOGUS")


ERROR_CONTRADICTIONS = {
    # A — executed=true
    "A_executed_true": {**CLEAN_ERROR, "executed": True},
    "A_executed_false_is_still_an_unknown_field": {**CLEAN_ERROR, "executed": False},
    # B — mutation / affected-row count
    "B_rows_affected": {**CLEAN_ERROR, "rows_affected": 1},
    "B_mutation_count": {**CLEAN_ERROR, "mutation_count": 2},
    "B_rows_affected_zero_is_still_unknown": {**CLEAN_ERROR, "rows_affected": 0},
    # C — success payload / applied outcome / post-state
    "C_success_true": {**CLEAN_ERROR, "success": True},
    "C_outcome_executed": {**CLEAN_ERROR, "outcome": "executed"},
    "C_mutation_status_applied": {**CLEAN_ERROR, "mutation_status": "applied"},
    "C_post_state": {**CLEAN_ERROR, "post_state": {"status": "available"}},
    "C_result": {**CLEAN_ERROR, "result": {"assignment_id": 7}},
    "C_fifth_audit_exact": {
        "execution_disposition": "NOT_APPLIED",
        "mutation_status": "applied",
        "outcome": "executed",
        "rejection_code": "BOGUS",
    },
    # D — malformed rejection metadata / unknown fields
    "D_code_missing": {"execution_disposition": "NOT_APPLIED", "message": "x"},
    "D_code_unknown": {**CLEAN_ERROR, "rejection_code": "BOGUS"},
    "D_code_lowercase": {**CLEAN_ERROR, "rejection_code": "not_found"},
    "D_code_padded": {**CLEAN_ERROR, "rejection_code": "NOT_FOUND "},
    "D_code_none": {**CLEAN_ERROR, "rejection_code": None},
    "D_code_int": {**CLEAN_ERROR, "rejection_code": 404},
    "D_code_list": {**CLEAN_ERROR, "rejection_code": ["NOT_FOUND"]},
    "D_message_not_string": {**CLEAN_ERROR, "message": {"x": 1}},
    "D_unknown_field": {**CLEAN_ERROR, "detail": "x"},
    "D_non_string_key": {**CLEAN_ERROR, 1: "x"},
}


@pytest.mark.parametrize("name", sorted(ERROR_CONTRADICTIONS))
def test_A_to_D_contradicted_error_payload_is_not_trusted(name):
    payload = ERROR_CONTRADICTIONS[name]
    assert claims_not_applied(payload) is True  # it claims …
    assert certifies_not_applied(payload) is False  # … but does not certify
    assert not_applied_violations(payload, error_result=True)
    observed = describe_disposition(payload)
    assert observed.startswith("untrusted_not_applied:")
    assert "BOGUS" not in observed and "applied'" not in observed  # no values echoed


def test_str_subclass_rejection_code_is_not_trusted():
    class _Str(str):
        pass

    assert not certifies_not_applied(
        {**CLEAN_ERROR, "rejection_code": _Str("NOT_FOUND")}
    )


def test_violation_report_is_bounded():
    payload = {**CLEAN_ERROR, **{f"k{i}": i for i in range(20)}}
    observed = describe_disposition(payload)
    assert observed.endswith(",+16")
    assert len(observed) < 200


# ── non-error result shape ────────────────────────────────────────────────────


@pytest.mark.parametrize("outcome", ["failed", "conflict", "deferred"])
def test_E_clean_result_is_trusted(outcome):
    result = {**CLEAN_RESULT, "outcome": outcome}
    assert certifies_not_applied_result(result) is True
    assert describe_disposition(result, error_result=False) == NOT_APPLIED
    # optional, consistent extras
    assert certifies_not_applied_result({**result, "rejection_code": "NOT_FOUND"})
    assert certifies_not_applied_result({**result, "assignment_id": None})
    assert certifies_not_applied_result({**result, "tasks_updated": 0})
    assert certifies_not_applied_result({**result, "worker_ids": ["W-1"]})


RESULT_CONTRADICTIONS = {
    "A_executed_true": {**CLEAN_RESULT, "executed": True},
    "B_rows_affected": {**CLEAN_RESULT, "rows_affected": 3},
    "B_tasks_updated": {**CLEAN_RESULT, "tasks_updated": 2},
    "B_tasks_updated_bool": {**CLEAN_RESULT, "tasks_updated": False},
    "B_assignment_id": {**CLEAN_RESULT, "assignment_id": 41},
    "B_maintenance_id": {**CLEAN_RESULT, "maintenance_id": 9},
    "B_allocation_id": {**CLEAN_RESULT, "allocation_id": "A-1"},
    "C_fifth_audit_success_true_failed": {
        **CLEAN_RESULT,
        "success": True,
        "outcome": "failed",
    },
    "C_success_true_executed": {**CLEAN_RESULT, "success": True, "outcome": "executed"},
    "C_outcome_no_op": {**CLEAN_RESULT, "outcome": "no_op"},
    "C_outcome_unknown": {**CLEAN_RESULT, "outcome": "unknown"},
    "C_post_state": {**CLEAN_RESULT, "post_state": {"status": "available"}},
    "C_mutation_status_applied": {**CLEAN_RESULT, "mutation_status": "applied"},
    "D_success_missing": {k: v for k, v in CLEAN_RESULT.items() if k != "success"},
    "D_success_string": {**CLEAN_RESULT, "success": "false"},
    "D_success_zero": {**CLEAN_RESULT, "success": 0},
    "D_outcome_missing": {k: v for k, v in CLEAN_RESULT.items() if k != "outcome"},
    "D_outcome_padded": {**CLEAN_RESULT, "outcome": "failed "},
    "D_outcome_upper": {**CLEAN_RESULT, "outcome": "FAILED"},
    "D_code_unknown": {**CLEAN_RESULT, "rejection_code": "BOGUS"},
    "D_code_int": {**CLEAN_RESULT, "rejection_code": 1},
    "D_echo_malformed": {**CLEAN_RESULT, "proposal_id": {"x": 1}},
    "D_worker_ids_malformed": {**CLEAN_RESULT, "worker_ids": "W-1"},
    "D_unknown_field": {**CLEAN_RESULT, "note": "x"},
}


@pytest.mark.parametrize("name", sorted(RESULT_CONTRADICTIONS))
def test_A_to_D_contradicted_result_is_not_trusted(name):
    result = RESULT_CONTRADICTIONS[name]
    assert claims_not_applied(result) is True
    assert certifies_not_applied_result(result) is False
    assert describe_disposition(result, error_result=False).startswith(
        "untrusted_not_applied:"
    )


def test_shapes_are_not_interchangeable():
    # the error-result payload is not a write result, and vice versa
    assert not certifies_not_applied_result(CLEAN_ERROR)
    assert not certifies_not_applied(CLEAN_RESULT)


@pytest.mark.parametrize(
    "payload", [None, "NOT_APPLIED", [], {}, {"execution_disposition": "not_applied"}]
)
def test_no_claim_is_never_a_certification(payload):
    assert certifies_not_applied(payload) is False
    assert certifies_not_applied_result(payload) is False


def test_shipped_contract_rejection_results_are_trusted():
    """Every canonical write-result contract, as the shipped providers build a
    NOT_APPLIED rejection, passes the strict non-error predicate."""
    from maiw_contracts.equipment import (
        EquipmentExecuteAssignResult,
        EquipmentExecuteMaintenanceResult,
        EquipmentExecuteReleaseResult,
    )
    from maiw_contracts.labor import LaborAllocateResult
    from maiw_contracts.wave import WaveReprioritizeResult

    common = {
        "success": False,
        "proposal_id": "p",
        "decision_id": "d",
        "execution_id": "e",
        "execution_disposition": "NOT_APPLIED",
        "source": "simulation",
        "message": "rejected",
    }
    results = [
        EquipmentExecuteAssignResult(assignment_id=None, outcome="conflict", **common),
        EquipmentExecuteReleaseResult(outcome="conflict", **common),
        EquipmentExecuteMaintenanceResult(
            maintenance_id=None, outcome="failed", **common
        ),
        LaborAllocateResult(
            allocation_id=None,
            task_id="T-1",
            worker_ids=[],
            outcome="deferred",
            **common,
        ),
        WaveReprioritizeResult(
            tasks_updated=0,
            wave_id="W-1",
            new_priority="high",
            outcome="failed",
            **common,
        ),
    ]
    for result in results:
        dumped = result.model_dump()
        assert certifies_not_applied_result(dumped), type(result).__name__
        # … and after the JSON round trip the MCP servers perform
        assert certifies_not_applied_result(json.loads(json.dumps(dumped)))


# ── failure classification ────────────────────────────────────────────────────


def test_contradictory_result_exception_is_unknown():
    exc = MCPResultOutcomeUnknown("x", observed_disposition="untrusted_not_applied:y")
    assert isinstance(exc, MCPContractError)
    assert isinstance(exc, MCPDispatchOutcomeUnknown)
    assert not isinstance(exc, MCPToolError)
    assert classify_write_failure(exc) == (
        ExecutionOutcome.UNKNOWN,
        "SERVER_RESULT_CONTRADICTORY",
        None,
    )


# ── executor: non-error path (in-process skills) ──────────────────────────────


def _approved(proposal: ActionProposal) -> DecisionResult:
    return DecisionResult(
        request_id="r5",
        proposal_id=proposal.proposal_id,
        outcome=DecisionOutcome.APPROVED,
        evaluated_at=datetime.now(timezone.utc),
    )


class _Dumped:
    """A skill result whose ``model_dump`` is exactly ``fields`` (defence in
    depth: the executor applies the strict predicate itself)."""

    def __init__(self, fields: dict[str, Any]) -> None:
        self._fields = fields
        self.success = fields.get("success")

    def model_dump(self) -> dict[str, Any]:
        return dict(self._fields)


class _Skill:
    def __init__(self, fields: dict[str, Any]) -> None:
        self.fields = fields
        self.calls = 0

    async def execute(self, req):
        self.calls += 1
        return _Dumped(
            {
                **self.fields,
                "proposal_id": req.proposal_id,
                "decision_id": req.decision_id,
                "execution_id": req.execution_id,
            }
        )


@pytest.mark.parametrize(
    "name,fields,expected,error_code",
    [
        ("E", dict(CLEAN_RESULT), "conflict", None),
        ("E_failed", {**CLEAN_RESULT, "outcome": "failed"}, "failed", None),
        (
            "A",
            {**CLEAN_RESULT, "executed": True},
            "unknown",
            "SERVER_RESULT_CONTRADICTORY",
        ),
        (
            "B",
            {**CLEAN_RESULT, "assignment_id": 9},
            "unknown",
            "SERVER_RESULT_CONTRADICTORY",
        ),
        (
            "C",
            {**CLEAN_RESULT, "success": True, "outcome": "failed"},
            "unknown",
            "SERVER_RESULT_CONTRADICTORY",
        ),
        (
            "C_executed",
            {**CLEAN_RESULT, "success": True, "outcome": "executed"},
            "unknown",
            "SERVER_RESULT_CONTRADICTORY",
        ),
        (
            "D",
            {**CLEAN_RESULT, "rejection_code": "BOGUS"},
            "unknown",
            "SERVER_RESULT_CONTRADICTORY",
        ),
        (
            "D_disposition_on_success",
            {
                "success": True,
                "outcome": "executed",
                "execution_disposition": "APPLIED",
            },
            "unknown",
            "SERVER_RESULT_CONTRADICTORY",
        ),
    ],
)
async def test_executor_non_error_path(name, fields, expected, error_code):
    registry = ExecutionRegistry()
    skill = _Skill(fields)
    executor = EquipmentActionExecutor(
        assign_skill=None, release_skill=skill, registry=registry
    )
    proposal = ActionProposal.for_equipment_release(asset_id="FL-01", released_by="op")
    result = await executor.execute(proposal, _approved(proposal))
    assert result.outcome.value == expected, name
    assert result.error_code == error_code
    blocker = registry.unresolved_for_target("warehouse.equipment.release", "FL-01")
    if expected == "unknown":
        assert result.physical_mutation_occurred is None
        assert result.server_disposition.startswith(
            ("untrusted_not_applied:", "unrecognised:")
        )
        assert "NOT_APPLIED certification" in result.uncertainty_reason
        assert blocker is not None
        # the identical retry never reaches the skill again
        again = await executor.execute(proposal, _approved(proposal))
        assert again.outcome == ExecutionOutcome.UNKNOWN
        other = ActionProposal.for_equipment_release(asset_id="FL-01", released_by="op")
        third = await executor.execute(other, _approved(other))
        assert third.error_code == "RECONCILIATION_REQUIRED"
        assert skill.calls == 1
    else:
        assert result.physical_mutation_occurred is False
        assert result.server_disposition == NOT_APPLIED
        assert blocker is None


async def test_executor_labor_and_wave_contract_results():
    """Contract-typed results (unknown fields dropped by validation) — the
    strict predicate still sees success / references / counts."""
    from maiw_contracts.labor import LaborAllocateResult
    from maiw_contracts.wave import WaveReprioritizeResult

    class _Typed:
        def __init__(self, result):
            self.result = result
            self.calls = 0

        async def execute(self, req):
            self.calls += 1
            return self.result.model_copy(
                update={"proposal_id": req.proposal_id, "decision_id": req.decision_id}
            )

    base = {
        "proposal_id": "p",
        "decision_id": "d",
        "execution_disposition": "NOT_APPLIED",
        "source": "t",
    }
    cases = [
        (
            LaborAllocateResult(
                success=False, task_id="T", worker_ids=[], outcome="deferred", **base
            ),
            "deferred",
        ),
        (
            LaborAllocateResult(
                success=False,
                allocation_id="A-1",
                task_id="T",
                worker_ids=["W"],
                outcome="deferred",
                **base,
            ),
            "unknown",
        ),
        (
            LaborAllocateResult(
                success=True, task_id="T", worker_ids=[], outcome="failed", **base
            ),
            "unknown",
        ),
    ]
    for result, expected in cases:
        executor = LaborActionExecutor(
            allocate_skill=_Typed(result), registry=ExecutionRegistry()
        )
        proposal = ActionProposal.for_labor_allocate(
            task_id="T", task_type="PICK", worker_ids=["W"]
        )
        out = await executor.execute(proposal, _approved(proposal))
        assert out.outcome.value == expected

    wave_cases = [
        (
            WaveReprioritizeResult(
                success=False,
                tasks_updated=0,
                new_priority="high",
                outcome="failed",
                **base,
            ),
            "failed",
        ),
        (
            WaveReprioritizeResult(
                success=False,
                tasks_updated=4,
                new_priority="high",
                outcome="failed",
                **base,
            ),
            "unknown",
        ),
    ]
    for result, expected in wave_cases:
        executor = WaveActionExecutor(
            reprioritize_skill=_Typed(result), registry=ExecutionRegistry()
        )
        proposal = ActionProposal.for_wave_reprioritize(zone="A", new_priority="high")
        out = await executor.execute(proposal, _approved(proposal))
        assert out.outcome.value == expected


# ── shipped MCP servers: genuine pre-mutation rejections still certify ───────


@pytest.fixture
def demo_world():
    from maiw_api.demo.world import DemoWarehouseWorld

    world = DemoWarehouseWorld()
    world.seed(
        {
            "clock_offset_seconds": 0,
            "inventory": [],
            "equipment": [
                {
                    "asset_id": "AGV-01",
                    "equipment_type": "agv",
                    "model": "TestAGV",
                    "zone": "A1",
                    "status": "available",
                    "battery_pct": 90.0,
                }
            ],
            "workers": [
                {
                    "worker_id": "w-001",
                    "username": "alice",
                    "full_name": "Alice",
                    "role": "operator",
                    "status": "active",
                    "zone": "A1",
                }
            ],
            "tasks": [
                {
                    "task_id": "t-001",
                    "task_type": "PICK",
                    "zone": "A1",
                    "status": "pending",
                    "priority": "high",
                }
            ],
        }
    )
    bus = MagicMock()
    for name in (
        "publish_equipment_write",
        "publish_labor_write",
        "publish_wave_write",
    ):
        setattr(bus, name, AsyncMock())
    return world, bus


@pytest.fixture
def shipped_servers(demo_world):
    from maiw_api.demo.providers.equipment import SimulationEquipmentProvider
    from maiw_api.demo.providers.labor import SimulationLaborProvider
    from maiw_api.demo.providers.wave import SimulationWaveProvider
    from mcp_servers.equipment import server as equipment
    from mcp_servers.labor import server as labor
    from mcp_servers.wave import server as wave

    world, bus = demo_world
    previous = (equipment._provider, labor._provider, wave._provider)
    equipment.configure_server(SimulationEquipmentProvider(world, bus))
    labor.configure_server(SimulationLaborProvider(world, bus))
    wave.configure_server(SimulationWaveProvider(world, bus))
    yield world, equipment, labor, wave
    equipment._provider, labor._provider, wave._provider = previous


def _client(caps: list[str], server) -> Any:
    from maiw_mcp.client.client import MAIWMCPClient
    from maiw_mcp.registry.registry import CapabilityRegistry

    registry = CapabilityRegistry()
    registry.register_domain(caps, server.mcp_server)
    return MAIWMCPClient(registry)


_IDS = {"proposal_id": "p", "decision_id": "d", "execution_id": "e"}


async def test_shipped_equipment_server_rejections_still_certify(shipped_servers):
    world, equipment, _, _ = shipped_servers
    caps = [
        "warehouse.equipment.assign",
        "warehouse.equipment.release",
        "warehouse.equipment.schedule_maintenance",
    ]
    client = _client(caps, equipment)
    before = {k: (a.status, a.owner_user) for k, a in world.equipment.items()}
    calls = [
        (
            "warehouse.equipment.assign",
            {"asset_id": "NOPE", "assignee": "x"},
            "NOT_FOUND",
        ),
        (
            "warehouse.equipment.release",
            {"asset_id": "NOPE", "released_by": "x"},
            "NOT_FOUND",
        ),
        (
            "warehouse.equipment.schedule_maintenance",
            {
                "asset_id": "NOPE",
                "maintenance_type": "preventive",
                "description": "d",
                "scheduled_by": "x",
                "scheduled_for": "2026-10-13T00:00:00Z",
            },
            "NOT_FOUND",
        ),
        (
            "warehouse.equipment.release",
            {"asset_id": "", "released_by": "x"},
            "INVALID_REQUEST",
        ),
    ]
    for capability, args, code in calls:
        with pytest.raises(MCPToolNotApplied) as info:
            await client.invoke(capability, {**args, **_IDS})
        assert info.value.rejection_code == code
    assert {k: (a.status, a.owner_user) for k, a in world.equipment.items()} == before

    # non-error CONFLICT certified NOT_APPLIED: returned (not raised) and trusted
    asset_id, asset = next(iter(world.equipment.items()))
    asset.status = "assigned"
    asset.metadata["current_task_id"] = "T-OTHER"
    result = await client.invoke(
        "warehouse.equipment.assign",
        {"asset_id": asset_id, "assignee": "y", "task_id": "T-NEW", **_IDS},
    )
    assert result["outcome"] == "conflict"
    assert certifies_not_applied_result(result)
    assert asset.metadata["current_task_id"] == "T-OTHER"


async def test_shipped_labor_and_wave_server_rejections_still_certify(shipped_servers):
    world, _, labor, wave = shipped_servers
    labor_client = _client(["warehouse.labor.allocate"], labor)
    with pytest.raises(MCPToolNotApplied) as info:
        await labor_client.invoke(
            "warehouse.labor.allocate",
            {
                "warehouse_id": "default",
                "task_id": "NOPE",
                "task_type": "PICK",
                "worker_ids": [],
                **_IDS,
            },
        )
    assert info.value.rejection_code == "NOT_FOUND"

    # DEFERRED: no worker available → non-error result, certified NOT_APPLIED
    for worker in world.workers.values():
        worker.status = "off_shift"
    task_id = next(iter(world.tasks))
    result = await labor_client.invoke(
        "warehouse.labor.allocate",
        {
            "warehouse_id": "default",
            "task_id": task_id,
            "task_type": "PICK",
            "worker_ids": [],
            **_IDS,
        },
    )
    assert result["outcome"] == "deferred"
    assert certifies_not_applied_result(result)

    wave_client = _client(["warehouse.wave.reprioritize"], wave)
    with pytest.raises(MCPToolNotApplied) as info:
        await wave_client.invoke(
            "warehouse.wave.reprioritize",
            {
                "warehouse_id": "default",
                "zone": "NO-SUCH-ZONE",
                "new_priority": "high",
                **_IDS,
            },
        )
    assert info.value.rejection_code == "NOT_FOUND"
