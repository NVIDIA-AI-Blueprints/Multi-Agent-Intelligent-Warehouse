# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.0.1 round 4 — NEW4-P1-01 unit coverage of the structured write-disposition
contract (``maiw_mcp.write_disposition``), the MCP client decoding of tool
error results, and the executor's outcome mapping.

The end-to-end proofs over real streamable HTTP through the canonical app are
in ``tests/api/test_round4_server_error_writes.py``; these tests pin the rules
exhaustively and fast.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from maiw_decision.models import DecisionOutcome, DecisionResult
from maiw_decision.proposal import ActionProposal
from maiw_execution import (
    EquipmentActionExecutor,
    ExecutionOutcome,
    ExecutionRegistry,
    classify_write_failure,
)
from maiw_mcp.errors import (
    MCPToolError,
    MCPToolErrorOutcomeUnknown,
    MCPToolNotApplied,
    WriteNotApplied,
)
from maiw_mcp.write_disposition import (
    NOT_APPLIED,
    certifies_not_applied,
    describe_disposition,
    not_applied_payload,
    not_applied_result,
)

# ── the contract ──────────────────────────────────────────────────────────────

NOT_CERTIFIED = [
    None,
    "NOT_APPLIED",
    ["NOT_APPLIED"],
    {},
    {"error": "x"},
    {"execution_disposition": None},
    {"execution_disposition": 0},
    {"execution_disposition": True},
    {"execution_disposition": ["NOT_APPLIED"]},
    {"execution_disposition": {"value": "NOT_APPLIED"}},
    {"execution_disposition": "not_applied"},
    {"execution_disposition": "Not_Applied"},
    {"execution_disposition": " NOT_APPLIED"},
    {"execution_disposition": "NOT_APPLIED "},
    {"execution_disposition": "NOT_APPLIED\n"},
    {"execution_disposition": "NOT-APPLIED"},
    {"execution_disposition": "APPLIED"},
    {"execution_disposition": "REJECTED_BEFORE_MUTATION"},
    {"execution_disposition": "NOT_STARTED"},
    {"execution_disposition": ""},
    {"disposition": "NOT_APPLIED"},
    {"mutation_status": "not_applied"},
]


class _Str(str):
    """A str subclass must not pass the exact-type check."""


@pytest.mark.parametrize("structured", NOT_CERTIFIED, ids=repr)
def test_only_the_exact_typed_field_certifies(structured):
    assert certifies_not_applied(structured) is False
    assert describe_disposition(structured) != NOT_APPLIED


def test_str_subclass_is_not_trusted():
    assert (
        certifies_not_applied({"execution_disposition": _Str("NOT_APPLIED")}) is False
    )


def test_exact_disposition_certifies():
    payload = not_applied_payload("asset not found", "NOT_FOUND")
    assert payload == {
        "execution_disposition": "NOT_APPLIED",
        "rejection_code": "NOT_FOUND",
        "message": "asset not found",
    }
    assert certifies_not_applied(payload) is True
    assert describe_disposition(payload) == NOT_APPLIED


def test_not_applied_result_is_an_error_result_with_structured_content():
    result = not_applied_result("bad", "INVALID_REQUEST")
    assert result.is_error is True
    assert certifies_not_applied(result.structured_content)
    assert "NOT_APPLIED" in result.content[0].text


# ── classification: isError alone can never mean executed=false ──────────────


@pytest.mark.parametrize("structured", NOT_CERTIFIED, ids=repr)
def test_tool_error_without_certification_is_unknown(structured):
    exc = MCPToolErrorOutcomeUnknown(
        "x", observed_disposition=describe_disposition(structured)
    )
    outcome, code, mutation = classify_write_failure(exc)
    assert (outcome, code, mutation) == (
        ExecutionOutcome.UNKNOWN,
        "MCP_TOOL_ERROR",
        None,
    )


def test_bare_tool_error_is_unknown():
    assert classify_write_failure(MCPToolError("x"))[0] == ExecutionOutcome.UNKNOWN


def test_certified_rejections_are_definite_failures():
    for exc, code in (
        (MCPToolNotApplied("x", rejection_code="NOT_FOUND"), "MCP_TOOL_NOT_APPLIED"),
        (WriteNotApplied("x"), "WRITE_NOT_APPLIED"),
    ):
        assert classify_write_failure(exc) == (ExecutionOutcome.FAILED, code, False)


def test_unclassified_exception_defaults_to_unknown():
    for exc in (RuntimeError("x"), ValueError("x"), KeyError("x"), OSError("x")):
        outcome, code, mutation = classify_write_failure(exc)
        assert outcome == ExecutionOutcome.UNKNOWN
        assert code == "EXECUTION_OUTCOME_UNKNOWN"
        assert mutation is None


# ── the real MCP client against the real equipment MCP server (in-memory) ───


class _ScriptedProvider:
    """Equipment provider whose release behaviour is set per call."""

    def __init__(self) -> None:
        from mcp_servers.equipment.provider import MockEquipmentProvider

        self._inner = MockEquipmentProvider()
        self.mode = ""
        self.writes = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    async def execute_equipment_release(self, request):
        if self.mode == "not_applied":
            raise WriteNotApplied(
                "no active assignment", rejection_code="PRECONDITION_FAILED"
            )
        self.writes += 1
        if self.mode == "error_after":
            raise RuntimeError("audit row insert failed after the update")
        return await self._inner.execute_equipment_release(request)


@pytest.fixture
def equipment_server():
    from mcp_servers.equipment import server as srv

    previous = srv._provider
    provider = _ScriptedProvider()
    srv.configure_server(provider)
    yield srv, provider
    srv._provider = previous


def _client(server):
    from maiw_mcp.client.client import MAIWMCPClient
    from maiw_mcp.registry.registry import CapabilityRegistry

    registry = CapabilityRegistry()
    registry.register_domain(
        ["warehouse.equipment.get_status", "warehouse.equipment.release"],
        server.mcp_server,
    )
    return MAIWMCPClient(registry)


_RELEASE = {
    "asset_id": "FL-01",
    "released_by": "t",
    "proposal_id": "p",
    "decision_id": "d",
    "execution_id": "e",
}


async def test_server_certified_rejection_decodes_as_not_applied(equipment_server):
    srv, provider = equipment_server
    provider.mode = "not_applied"
    with pytest.raises(MCPToolNotApplied) as info:
        await _client(srv).invoke("warehouse.equipment.release", dict(_RELEASE))
    assert info.value.rejection_code == "PRECONDITION_FAILED"
    assert provider.writes == 0


async def test_server_error_after_write_decodes_as_outcome_unknown(equipment_server):
    srv, provider = equipment_server
    provider.mode = "error_after"
    with pytest.raises(MCPToolErrorOutcomeUnknown) as info:
        await _client(srv).invoke("warehouse.equipment.release", dict(_RELEASE))
    assert info.value.observed_disposition == "absent:no_structured_content"
    assert provider.writes == 1


async def test_invalid_write_request_is_rejected_not_applied(equipment_server):
    srv, provider = equipment_server
    bad = {**_RELEASE, "asset_id": ""}
    with pytest.raises(MCPToolNotApplied) as info:
        await _client(srv).invoke("warehouse.equipment.release", bad)
    assert info.value.rejection_code == "INVALID_REQUEST"
    assert provider.writes == 0


# ── executor: non-error results ───────────────────────────────────────────────


class _ResultSkill:
    def __init__(self, **fields: Any) -> None:
        self.fields = fields
        self.calls = 0

    async def execute(self, req):
        from maiw_contracts.equipment import EquipmentExecuteReleaseResult

        self.calls += 1
        return EquipmentExecuteReleaseResult(
            proposal_id=req.proposal_id,
            decision_id=req.decision_id,
            source="test",
            **self.fields,
        )


def _approved_release(asset_id: str = "FL-01"):
    proposal = ActionProposal.for_equipment_release(
        asset_id=asset_id, released_by="operator-1"
    )
    decision = DecisionResult(
        request_id="r4",
        proposal_id=proposal.proposal_id,
        outcome=DecisionOutcome.APPROVED,
        evaluated_at=datetime.now(timezone.utc),
    )
    return proposal, decision


@pytest.mark.parametrize(
    "fields,expected,mutation,unresolved",
    [
        ({"success": True}, "executed", True, False),
        ({"success": True, "outcome": "no_op"}, "no_op", False, False),
        ({"success": False}, "unknown", None, True),  # contradictory default
        ({"success": False, "outcome": "executed"}, "unknown", None, True),
        ({"success": False, "outcome": "failed"}, "unknown", None, True),
        ({"success": False, "outcome": "conflict"}, "unknown", None, True),
        ({"success": False, "outcome": "deferred"}, "unknown", None, True),
        (
            {"success": False, "outcome": "failed", "execution_disposition": "nope"},
            "unknown",
            None,
            True,
        ),
        ({"success": True, "outcome": "unknown"}, "unknown", None, True),
        (
            {
                "success": False,
                "outcome": "failed",
                "execution_disposition": "NOT_APPLIED",
            },
            "failed",
            False,
            False,
        ),
        (
            {
                "success": False,
                "outcome": "conflict",
                "execution_disposition": "NOT_APPLIED",
            },
            "conflict",
            False,
            False,
        ),
    ],
)
async def test_result_outcome_mapping(fields, expected, mutation, unresolved):
    registry = ExecutionRegistry()
    skill = _ResultSkill(**fields)
    executor = EquipmentActionExecutor(
        assign_skill=None, release_skill=skill, registry=registry
    )
    proposal, decision = _approved_release()
    result = await executor.execute(proposal, decision)
    assert result.outcome.value == expected
    assert result.physical_mutation_occurred is mutation
    blocker = registry.unresolved_for_target("warehouse.equipment.release", "FL-01")
    assert (blocker is not None) is unresolved
    assert skill.calls == 1


async def test_unbuildable_request_is_not_dispatched():
    """Invalid parameters fail before the skill is called → definite FAILED."""
    skill = _ResultSkill(success=True)
    executor = EquipmentActionExecutor(
        assign_skill=None, release_skill=skill, registry=ExecutionRegistry()
    )
    proposal, decision = _approved_release()
    proposal.parameters["asset_id"] = None  # the request model rejects it
    result = await executor.execute(proposal, decision)
    assert result.outcome == ExecutionOutcome.FAILED
    assert result.error_code == "NOT_DISPATCHED"
    assert result.dispatch_status == "not_dispatched"
    assert skill.calls == 0


# ── idempotent replay (fourth re-audit NEW4-P2-01) ────────────────────────────


class _RaisingSkill:
    def __init__(self, exc: Exception) -> None:
        self.exc = exc
        self.calls = 0

    async def execute(self, req):
        self.calls += 1
        raise self.exc


async def test_replay_of_definite_failure_is_failed_not_no_op():
    registry = ExecutionRegistry()
    skill = _RaisingSkill(MCPToolNotApplied("rejected", rejection_code="NOT_FOUND"))
    executor = EquipmentActionExecutor(
        assign_skill=None, release_skill=skill, registry=registry
    )
    proposal, decision = _approved_release()
    proposal.idempotency_key = "k-1"
    first = await executor.execute(proposal, decision)
    second = await executor.execute(proposal, decision)
    assert first.outcome == ExecutionOutcome.FAILED
    assert second.outcome == ExecutionOutcome.FAILED
    assert second.outcome != ExecutionOutcome.NO_OP
    assert second.success is False
    assert second.execution_id == first.execution_id
    assert second.backend_response["replayed"] is True
    assert skill.calls == 1


async def test_replay_of_unresolved_unknown_never_becomes_no_op():
    registry = ExecutionRegistry()
    skill = _RaisingSkill(MCPToolErrorOutcomeUnknown("boom"))
    executor = EquipmentActionExecutor(
        assign_skill=None, release_skill=skill, registry=registry
    )
    proposal, decision = _approved_release()
    proposal.idempotency_key = "k-2"
    first = await executor.execute(proposal, decision)
    second = await executor.execute(proposal, decision)
    assert first.outcome == ExecutionOutcome.UNKNOWN
    assert second.outcome == ExecutionOutcome.UNKNOWN
    assert second.error_code == "RECONCILIATION_REQUIRED"
    assert skill.calls == 1
    # a different idempotency key for the same asset is blocked as well
    other, other_decision = _approved_release()
    other.idempotency_key = "k-3"
    third = await executor.execute(other, other_decision)
    assert third.error_code == "RECONCILIATION_REQUIRED"
    assert skill.calls == 1


# ── demo simulation providers certify only genuine pre-mutation rejections ──


async def test_demo_provider_not_found_is_certified_not_applied():
    from maiw_api.demo.providers.equipment import SimulationEquipmentProvider
    from maiw_api.demo.world import DemoWarehouseWorld
    from maiw_contracts.equipment import EquipmentExecuteReleaseRequest
    from unittest.mock import AsyncMock, MagicMock

    bus = MagicMock()
    bus.publish_equipment_write = AsyncMock()
    provider = SimulationEquipmentProvider(DemoWarehouseWorld(), bus)
    with pytest.raises(WriteNotApplied) as info:
        await provider.execute_equipment_release(
            EquipmentExecuteReleaseRequest(
                asset_id="NOPE", released_by="x", proposal_id="p", decision_id="d"
            )
        )
    assert info.value.rejection_code == "NOT_FOUND"
