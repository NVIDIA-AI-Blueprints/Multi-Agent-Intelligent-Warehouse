# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.0.1 round 2 — targeted P2-02: crash between governance acceptance and
procedure resume (spec §38/§39), on the canonical shipped app's durable stores.

    A  crash BEFORE governance accepted     → nothing applied; normal delivery later
    B  crash AFTER accept fsync, BEFORE resume
                                            → restart recovery resumes exactly once
    C  crash AFTER resume checkpoint, BEFORE applied marker
                                            → restart recovery does NOT re-run it
    D  duplicate governance delivery        → dropped (idempotent)

A "crash" is simulated by abandoning the process-level objects at the exact
point (the real JsonFile stores are fsynced at each step) and building a new
canonical app over the same MAIW_PERSISTENCE_ROOT.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.api.canonical_harness import (
    FakeNIM,
    FakeWaveWorld,
    ProofSopAExecutor,
    canonical_env,
    governance_input_for,
    install_gateway,
    proof_sop_a_inputs,
    running_canonical_app,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def canonical(monkeypatch, tmp_path):
    fake = FakeNIM()
    canonical_env(monkeypatch, tmp_path, fake)
    install_gateway(fake)
    yield tmp_path / "maiw"
    fake.close()
    from maiw_models import reset_model_gateway

    reset_model_gateway()


def _ledger(root: Path) -> list[dict]:
    path = root / "governance" / "governance_inbox.jsonl"
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text().splitlines() if ln.strip()]


async def _paused_procedure():
    definition, sop, context = proof_sop_a_inputs(REPO_ROOT)
    async with running_canonical_app() as (app, _):
        paused = await app.state.runtime.procedure_host.start(
            definition=definition,
            sop=sop,
            agent_task_id="task-crash",
            context=context,
            executor=ProofSopAExecutor(),
            warehouse_state_snapshot=FakeWaveWorld(),
        )
    assert paused.status.value == "waiting_for_governance"
    return paused, (definition, sop, context)


def _resolved_world():
    world = FakeWaveWorld()
    world.resolve_risk(remaining=0)
    return world


def _inputs_factory(inputs, world, calls):
    from maiw_api.procedure_host import RecoveryInputs

    definition, sop, context = inputs

    async def _inputs_for(state):
        calls.append(state.procedure_execution_id)
        return RecoveryInputs(
            definition=definition,
            sop=sop,
            context=context,
            warehouse_state_snapshot=world,
        )

    return _inputs_for


async def test_a_crash_before_accept_applies_nothing(canonical):
    paused, inputs = await _paused_procedure()
    # "crash" before inbox.accept: nothing recorded
    async with running_canonical_app() as (app, client):
        host = app.state.runtime.procedure_host
        assert host.unapplied_governance() == []
        calls: list[str] = []
        report = await host.recover_accepted_governance(
            _inputs_factory(inputs, _resolved_world(), calls)
        )
        assert report.resumed == [] and report.already_applied == [] and calls == []
        state = await host.load(paused.procedure_execution_id)
        assert state.status.value == "waiting_for_governance"
        assert state.revision == paused.revision
        ready = (await client.get("/api/v1/ready")).json()
        assert ready["components"]["persistence"]["unapplied_governance"] == 0
        # the governance outcome is then delivered normally, exactly once
        definition, sop, context = inputs
        executor = ProofSopAExecutor()
        applied = await host.apply_governance(
            governance_input_for(paused),
            definition=definition,
            sop=sop,
            context=context,
            executor=executor,
            warehouse_state_snapshot=_resolved_world(),
        )
        assert applied.applied and executor.steps == []
    assert [e["event"] for e in _ledger(canonical)] == ["accepted", "applied"]


async def test_b_crash_after_accept_before_resume_recovers_exactly_once(canonical):
    paused, inputs = await _paused_procedure()
    gov = governance_input_for(paused)

    # process 2: accept is fsynced, then the process dies before the resume
    async with running_canonical_app() as (app, _):
        assert app.state.runtime.governance_inbox.accept(gov) is True
    assert [e["event"] for e in _ledger(canonical)] == ["accepted"]

    # process 3: restart — the accepted-but-unapplied outcome is detected
    async with running_canonical_app() as (app, client):
        host = app.state.runtime.procedure_host
        pending = host.unapplied_governance()
        assert [g.procedure_execution_id for g in pending] == [
            paused.procedure_execution_id
        ]
        ready = (await client.get("/api/v1/ready")).json()
        assert ready["components"]["persistence"]["unapplied_governance"] == 1
        stuck = await host.load(paused.procedure_execution_id)
        assert stuck.status.value == "waiting_for_governance"

        calls: list[str] = []
        report = await host.recover_accepted_governance(
            _inputs_factory(inputs, _resolved_world(), calls)
        )
        assert report.resumed == [paused.procedure_execution_id]
        assert calls == [paused.procedure_execution_id]
        resumed = await host.load(paused.procedure_execution_id)
        assert resumed.status.value != "waiting_for_governance"
        assert resumed.revision > paused.revision
        after_first = resumed.revision

        # recovery is idempotent: a second pass does nothing
        again = await host.recover_accepted_governance(
            _inputs_factory(inputs, _resolved_world(), calls)
        )
        assert again.resumed == [] and again.already_applied == []
        assert (await host.load(paused.procedure_execution_id)).revision == after_first

        # and a redelivery of the same outcome is a dropped duplicate
        definition, sop, context = inputs
        executor = ProofSopAExecutor()
        dup = await host.apply_governance(
            gov,
            definition=definition,
            sop=sop,
            context=context,
            executor=executor,
            warehouse_state_snapshot=_resolved_world(),
        )
        assert dup.duplicate and not dup.applied and executor.steps == []

    # process 4: nothing left to recover
    async with running_canonical_app() as (app, _):
        assert app.state.runtime.procedure_host.unapplied_governance() == []
        assert (
            await app.state.runtime.procedure_host.load(paused.procedure_execution_id)
        ).revision == after_first
    assert [e["event"] for e in _ledger(canonical)] == ["accepted", "applied"]


async def test_c_crash_after_resume_before_applied_marker_does_not_duplicate(
    canonical, monkeypatch
):
    paused, inputs = await _paused_procedure()
    gov = governance_input_for(paused)
    definition, sop, context = inputs

    # process 2: accept + resume checkpoint complete, crash before the marker
    async with running_canonical_app() as (app, _):
        inbox = app.state.runtime.governance_inbox
        monkeypatch.setattr(inbox, "mark_applied", lambda _g: None)
        first = await app.state.runtime.procedure_host.apply_governance(
            gov,
            definition=definition,
            sop=sop,
            context=context,
            executor=ProofSopAExecutor(),
            warehouse_state_snapshot=_resolved_world(),
        )
        assert first.applied
    resumed_revision = first.state.revision
    assert [e["event"] for e in _ledger(canonical)] == ["accepted"]

    # process 3: recovery sees the procedure already moved on → mark only
    async with running_canonical_app() as (app, _):
        host = app.state.runtime.procedure_host
        assert len(host.unapplied_governance()) == 1
        calls: list[str] = []
        report = await host.recover_accepted_governance(
            _inputs_factory(inputs, _resolved_world(), calls)
        )
        assert report.already_applied == [paused.procedure_execution_id]
        assert report.resumed == [] and calls == []  # engine not re-run
        state = await host.load(paused.procedure_execution_id)
        assert state.revision == resumed_revision
        assert host.unapplied_governance() == []
    assert [e["event"] for e in _ledger(canonical)] == ["accepted", "applied"]


async def test_d_duplicate_delivery_is_dropped(canonical):
    paused, inputs = await _paused_procedure()
    gov = governance_input_for(paused)
    definition, sop, context = inputs
    async with running_canonical_app() as (app, _):
        host = app.state.runtime.procedure_host
        first = await host.apply_governance(
            gov,
            definition=definition,
            sop=sop,
            context=context,
            executor=ProofSopAExecutor(),
            warehouse_state_snapshot=_resolved_world(),
        )
        second = await host.apply_governance(
            gov,
            definition=definition,
            sop=sop,
            context=context,
            executor=ProofSopAExecutor(),
            warehouse_state_snapshot=_resolved_world(),
        )
    assert first.applied and not first.duplicate
    assert second.duplicate and not second.applied
    assert second.state.revision == first.state.revision
    assert [e["event"] for e in _ledger(canonical)] == ["accepted", "applied"]


async def test_recovery_without_inputs_leaves_outcome_unapplied(canonical):
    paused, _ = await _paused_procedure()
    async with running_canonical_app() as (app, _):
        app.state.runtime.governance_inbox.accept(governance_input_for(paused))
    async with running_canonical_app() as (app, _):
        host = app.state.runtime.procedure_host

        async def _none(_state):
            return None

        report = await host.recover_accepted_governance(_none)
        assert report.skipped == [paused.procedure_execution_id]
        assert len(host.unapplied_governance()) == 1


def test_pre_round2_ledger_entries_are_not_replayed(tmp_path):
    """Entries written before round 2 carry no payload: treated as applied."""
    from integrations.nemoclaw.boundary_contracts import JsonFileGovernanceInbox

    (tmp_path / "governance_inbox.jsonl").write_text(
        json.dumps(
            {"procedure_execution_id": "p", "proposal_id": "x", "expected_revision": 3}
        )
        + "\n"
    )
    inbox = JsonFileGovernanceInbox(tmp_path)
    assert inbox.accepted_unapplied() == []
