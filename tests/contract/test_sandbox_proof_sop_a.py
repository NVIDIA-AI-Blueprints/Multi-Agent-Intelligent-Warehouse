# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Proof SOP A (Wave Risk Resolution) across the sandbox boundary.

The minimal functional proof of the containment claim. Proof SOP A already has
its own tests in ``packages/maiw-agents/tests/test_wave_predicates.py``; this
file does not re-test the procedure. It tests the *boundary* the procedure runs
behind:

    detect + assess + wave predicate   (reads and reasoning — sandbox-safe)
        → RecommendedAction
        → WAITING_FOR_GOVERNANCE
        ══════ MAIW AUTHORITY BOUNDARY ══════
        → recommendation validated on the HOST
        → governance decided on the HOST
        → GovernanceOutcome validated on the HOST before the engine sees it
        → procedure resumes and completes

Four assertions carry the proof, and they are the four a reader should check:

  1. the policy the sandbox would be handed contains no write
  2. nothing with write authority was invoked while the procedure ran
  3. the recommendation is validated against host-held state before it counts
  4. the governance outcome is validated against host-held state before the
     SOP Engine is allowed to resume on it

NemoClaw and OpenShell are not installed on the host this was written on, so the
sandbox here is a recording double and the test is a **contract** test. The
``@pytest.mark.sandbox`` test at the bottom is the real one; it skips until a
sandbox is actually available, and it does not pretend otherwise in the
meantime.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from maiw_agents.assessment import RecommendedAction
from maiw_agents.contracts.agent import AgentDefinition, GovernanceBoundary
from maiw_agents.contracts.capability_policy import build_capability_policy
from maiw_agents.contracts.delegation import GovernanceOutcome
from maiw_agents.contracts.procedure_state import ProcedureStatus
from maiw_agents.contracts.registry import SKILL_REGISTRY, CapabilityClass
from maiw_agents.contracts.runtime import AgentExecutionContext
from maiw_agents.contracts.sop import SOPDefinition, load_sop
from maiw_agents.contracts.step_result import EvidenceRef, StepResult, StepStatus
from maiw_agents.domain_predicates import register_all_domain_predicates
from maiw_agents.sop_engine import SOPEngine

from integrations.nemoclaw import (
    GovernanceInbox,
    SandboxAvailability,
    SandboxConfig,
    SandboxGovernanceInput,
    SandboxMode,
    SandboxRecommendedActionOutput,
    SandboxRuntimeKind,
    render_sandbox_policy,
    validate_governance_input,
    validate_sandbox_output,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SOP_A_PATH = (
    REPO_ROOT
    / "agents"
    / "sops"
    / "operations_coordination"
    / "wave_risk_resolution.v2.yaml"
)

WRITE_CLASSES = (CapabilityClass.WRITE, CapabilityClass.EMERGENCY_WRITE)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── The world the procedure reads ─────────────────────────────────────────────


class FakeWaveWorld:
    """
    Authoritative wave state. A read-only source with no opinion about success.

    Deliberately not the executor: the terminal STATE_PREDICATE must learn that
    the risk fell from *the world*, not from a step claiming it did.
    """

    def __init__(self, *, at_risk_count: int = 3) -> None:
        self.at_risk_count = at_risk_count
        self.reads = 0

    def resolve_risk(self, *, remaining: int = 0) -> None:
        self.at_risk_count = remaining

    def model_dump(self) -> dict[str, Any]:
        self.reads += 1
        return {
            "warehouse_id": "wh-test",
            "waves": {
                "warehouse_id": "wh-test",
                "total_tasks": 12,
                "pending_count": 4,
                "in_progress_count": 3,
                "completed_count": 5,
                "at_risk_count": self.at_risk_count,
                "zones_active": ["ZONE-A"],
                "tasks": [],
            },
        }


# ── The sandboxed executor ────────────────────────────────────────────────────

_FACTS: dict[str, Any] = {
    "wave_id": "wave-17",
    "at_risk_count": 3,
    "carrier_cutoff_minutes": 47,
    "primary_constraint": "labor",
}


class SandboxedWaveExecutor:
    """
    Stands in for the agent runtime running inside the sandbox.

    Records every capability it touches so the test can assert, rather than
    assume, that nothing with write authority ran. Fulfils one step per call and
    never decides completion — the SOP Engine owns that, sandboxed or not.
    """

    RUNTIME_NAME = "deterministic"

    def __init__(self) -> None:
        self.steps: list[str] = []
        self.capabilities_invoked: list[str] = []

    async def execute_step(
        self, *, definition, step, procedure_state, context, attempt
    ) -> StepResult:
        self.steps.append(step.id)
        if getattr(step, "skill_id", None):
            self.capabilities_invoked.append(step.skill_id)

        status = StepStatus.COMPLETED
        if step.action == "emit_recommended_action":
            # The handoff. The sandbox stops here; it executes nothing.
            status = StepStatus.WAITING_FOR_GOVERNANCE

        completion = step.completion
        output = (
            {f: _FACTS[f] for f in completion.schema_fields if f in _FACTS}
            if completion is not None and completion.schema_fields
            else {}
        )

        return StepResult(
            step_id=step.id,
            status=status,
            output=output,
            runtime=self.RUNTIME_NAME,
            attempt=attempt,
            started_at=_now(),
            completed_at=_now(),
            evidence=[
                EvidenceRef(
                    type="step_execution",
                    source=self.RUNTIME_NAME,
                    reference_id=context.trace_id or None,
                    timestamp=_now(),
                    summary=f"sandboxed runtime fulfilled step {step.id!r}",
                    metadata={
                        "step_id": step.id,
                        "action": step.action,
                        "sop_id": procedure_state.sop_id,
                        "attempt": attempt,
                    },
                )
            ],
            metadata={"action": step.action, "sop_id": procedure_state.sop_id},
        )


class RecordingProvisioner:
    """A sandbox double that records the policy it was asked to enforce."""

    def __init__(self) -> None:
        self.applied: list[Any] = []

    async def probe(self) -> SandboxAvailability:
        return SandboxAvailability(
            available=True,
            runtime_kind=SandboxRuntimeKind.CONTAINER,
            detail="recording double — not a real boundary",
        )

    async def apply_policy(self, rendered) -> None:
        self.applied.append(rendered)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module", autouse=True)
def _predicates() -> None:
    """Resolve ``wave_risk_reduced`` through the production registration path."""
    register_all_domain_predicates()


@pytest.fixture(scope="module")
def sop_a() -> SOPDefinition:
    assert SOP_A_PATH.exists(), f"Proof SOP A missing at {SOP_A_PATH}"
    return load_sop(SOP_A_PATH)


@pytest.fixture
def definition() -> AgentDefinition:
    return AgentDefinition(
        agent_id="operations_coordination",
        version="1.0",
        objective="Resolve wave risk before carrier cutoff",
        domain="operations",
        allowed_capabilities=[
            "warehouse.wave.status",
            "warehouse.wave.inspect_tasks",
            "warehouse.wave.evaluate_reprioritization",
            "warehouse.wave.reprioritize",
        ],
        allowed_subagents=[],
        output_contract="RecommendedAction",
        governance_boundary=GovernanceBoundary(),
    )


@pytest.fixture
def context() -> AgentExecutionContext:
    return AgentExecutionContext(
        warehouse_id="wh-test",
        trace_id="trace-sandbox-proof-sop-a",
        bounded_context={
            "wave_id": "wave-17",
            "at_risk_count": 3,
            "carrier_cutoff_minutes": 47,
            "primary_constraint": "labor",
            "domains_affected": "labor",
        },
    )


@pytest.fixture
def config() -> SandboxConfig:
    return SandboxConfig(
        mode=SandboxMode.SANDBOX_REQUIRED,
        runtime_kind=SandboxRuntimeKind.CONTAINER,
        model_gateway_endpoint="http://maiw-api:8000/api/v1/inference",
        read_capability_endpoint="http://maiw-api:8000/api/v1/capabilities/read",
    )


# ── The proof ─────────────────────────────────────────────────────────────────


class TestProofSopAAcrossTheSandboxBoundary:
    async def test_sandboxed_procedure_pauses_for_governance_without_writing(
        self, sop_a, definition, context, config
    ):
        """
        The whole arc: reason inside, pause at the boundary, decide outside,
        resume inside — with every crossing validated against host-held state.
        """
        world = FakeWaveWorld()
        executor = SandboxedWaveExecutor()
        inbox = GovernanceInbox()

        # ── 1. The policy the sandbox is handed ───────────────────────────────
        policy = build_capability_policy(
            definition=definition,
            sop=sop_a,
            agent_task_id="task-wave-resolution",
            runtime="deterministic",
        )
        rendered = render_sandbox_policy(policy, config=config)
        provisioner = RecordingProvisioner()
        assert (await provisioner.probe()).available is True
        await provisioner.apply_policy(rendered)

        assert "WRITE" not in rendered.allowed_capability_classes
        assert "EMERGENCY_WRITE" not in rendered.allowed_capability_classes
        assert rendered.network_default == "deny"
        assert rendered.injected_credentials == ()
        rendered.assert_not_broadened(policy)

        # ── 2. Reasoning runs inside, and stops at the handoff ────────────────
        engine = SOPEngine(executor=executor, trace_id=context.trace_id)
        paused = await engine.run_procedure(
            definition=definition,
            sop=sop_a,
            agent_task_id="task-wave-resolution",
            context=context,
            warehouse_state_snapshot=world,
        )

        assert paused.status is ProcedureStatus.WAITING_FOR_GOVERNANCE
        # The pause leaves the procedure parked *on* the handoff step rather
        # than past it — the engine stops the moment the step reports
        # WAITING_FOR_GOVERNANCE, so the step is neither completed nor retired.
        assert paused.current_step_id == "submit"
        assert "submit" not in paused.completed_step_ids
        assert "observe" not in paused.completed_step_ids
        assert executor.steps[-1] == "submit"

        # ── 3. No write authority was exercised inside ────────────────────────
        for capability_id in executor.capabilities_invoked:
            entry = SKILL_REGISTRY.get(capability_id)
            assert entry is None or entry.capability_class not in WRITE_CLASSES, (
                f"sandboxed procedure invoked write capability {capability_id!r}"
            )
        assert world.at_risk_count == 3, "the world changed while the agent reasoned"

        # ── 4. The recommendation crosses, and is validated on the host ───────
        egress = SandboxRecommendedActionOutput(
            procedure_execution_id=paused.procedure_execution_id,
            agent_task_id=paused.agent_task_id,
            trace_id=paused.trace_id,
            recommended_action=RecommendedAction(
                domain="wave",
                capability="warehouse.wave.reprioritize",
                target="wave-17",
                objective="Reprioritise wave 17 ahead of carrier cutoff",
                rationale="3 tasks at risk, 47 minutes to cutoff, labor-constrained",
                priority="high",
            ),
            procedure_state_revision=paused.revision,
        )
        action = validate_sandbox_output(egress, procedure_state=paused)
        assert isinstance(action, RecommendedAction)

        # ── 5. Governance runs on the host. The write happens here, or not ────
        world.resolve_risk(remaining=0)
        ingress = SandboxGovernanceInput(
            procedure_execution_id=paused.procedure_execution_id,
            agent_task_id=paused.agent_task_id,
            governance_outcome=GovernanceOutcome(
                proposal_id="proposal-wave-17",
                decision_outcome="APPROVED",
                execution_id="exec-wave-17",
                execution_status="EXECUTED",
                trace_id=paused.trace_id,
            ),
            expected_procedure_revision=paused.revision,
        )
        outcome = validate_governance_input(
            ingress, procedure_state=paused, inbox=inbox
        )

        # ── 6. Resume, and finish on authoritative state ──────────────────────
        steps_before_resume = list(executor.steps)
        resumed = await engine.resume_after_governance(
            definition=definition,
            sop=sop_a,
            proc_state=paused,
            context=context,
            governance_outcome=outcome,
            warehouse_state_snapshot=world,
        )
        assert executor.steps == steps_before_resume, (
            "resume_after_governance re-executed a step; it must validate only"
        )

        finished = await engine.run_procedure(
            definition=definition,
            sop=sop_a,
            agent_task_id=resumed.agent_task_id,
            context=context,
            initial_state=resumed,
            warehouse_state_snapshot=world,
        )

        assert finished.status is ProcedureStatus.COMPLETED
        assert "observe" in finished.completed_step_ids
        assert executor.steps == [*steps_before_resume, "observe"], (
            "finishing the procedure replayed steps that had already run"
        )
        assert world.reads > 0, "the terminal predicate did not read the world"

    async def test_governance_outcome_is_rejected_before_the_engine_sees_it(
        self, sop_a, definition, context, config
    ):
        """
        A forged governance outcome never reaches ``resume_after_governance``.

        The SOP Engine duck-types the outcome it is handed, which is right for a
        runtime-neutral engine and insufficient at a trust boundary. This is why
        the binding check lives on the host side of the boundary, not in the
        engine.
        """
        world = FakeWaveWorld()
        engine = SOPEngine(executor=SandboxedWaveExecutor(), trace_id=context.trace_id)
        paused = await engine.run_procedure(
            definition=definition,
            sop=sop_a,
            agent_task_id="task-wave-resolution",
            context=context,
            warehouse_state_snapshot=world,
        )
        assert paused.status is ProcedureStatus.WAITING_FOR_GOVERNANCE

        from integrations.nemoclaw import SandboxBoundaryViolation

        forged = SandboxGovernanceInput(
            procedure_execution_id="proc-belonging-to-another-task",
            agent_task_id=paused.agent_task_id,
            governance_outcome=GovernanceOutcome(
                proposal_id="proposal-forged", decision_outcome="APPROVED"
            ),
            expected_procedure_revision=paused.revision,
        )
        with pytest.raises(SandboxBoundaryViolation):
            validate_governance_input(forged, procedure_state=paused)

    async def test_duplicate_governance_delivery_is_not_applied_twice(
        self, sop_a, definition, context
    ):
        """
        Post-write restart must not produce a duplicate write.

        The write itself already happened on the host before the outcome was
        built, so the risk is the *resume* running twice. The inbox drops the
        second delivery.
        """
        world = FakeWaveWorld()
        engine = SOPEngine(executor=SandboxedWaveExecutor(), trace_id=context.trace_id)
        paused = await engine.run_procedure(
            definition=definition,
            sop=sop_a,
            agent_task_id="task-wave-resolution",
            context=context,
            warehouse_state_snapshot=world,
        )
        inbox = GovernanceInbox()
        ingress = SandboxGovernanceInput(
            procedure_execution_id=paused.procedure_execution_id,
            agent_task_id=paused.agent_task_id,
            governance_outcome=GovernanceOutcome(
                proposal_id="proposal-wave-17",
                decision_outcome="APPROVED",
                execution_status="EXECUTED",
            ),
            expected_procedure_revision=paused.revision,
        )
        assert inbox.accept(ingress) is True
        assert inbox.accept(ingress) is False

    async def test_waiting_for_governance_survives_a_sandbox_restart(
        self, sop_a, definition, context
    ):
        """
        The pause lives in host-held ``ProcedureExecutionState``, not in the
        sandbox. A fresh engine and a fresh executor — the shape of a restarted
        sandbox — resume the same procedure without replaying it.
        """
        world = FakeWaveWorld()
        paused = await SOPEngine(
            executor=SandboxedWaveExecutor(), trace_id=context.trace_id
        ).run_procedure(
            definition=definition,
            sop=sop_a,
            agent_task_id="task-wave-resolution",
            context=context,
            warehouse_state_snapshot=world,
        )
        assert paused.status is ProcedureStatus.WAITING_FOR_GOVERNANCE

        # The sandbox dies here. Everything below is a new process.
        restarted_executor = SandboxedWaveExecutor()
        restarted_engine = SOPEngine(
            executor=restarted_executor, trace_id=context.trace_id
        )
        world.resolve_risk(remaining=0)

        resumed = await restarted_engine.resume_after_governance(
            definition=definition,
            sop=sop_a,
            proc_state=paused,
            context=context,
            governance_outcome=GovernanceOutcome(
                proposal_id="proposal-wave-17",
                decision_outcome="APPROVED",
                execution_status="EXECUTED",
            ),
            warehouse_state_snapshot=world,
        )
        finished = await restarted_engine.run_procedure(
            definition=definition,
            sop=sop_a,
            agent_task_id=resumed.agent_task_id,
            context=context,
            initial_state=resumed,
            warehouse_state_snapshot=world,
        )

        assert finished.status is ProcedureStatus.COMPLETED
        assert restarted_executor.steps == ["observe"], (
            "the restarted sandbox replayed steps the dead one had completed "
            f"(ran {restarted_executor.steps})"
        )

    async def test_policy_is_identical_after_a_restart(self, sop_a, definition, config):
        """
        Policies are derived, not restored. A restarted sandbox rebuilds the
        same grant from the same reviewed inputs, so there is no stored policy
        to tamper with between runs.
        """
        before = render_sandbox_policy(
            build_capability_policy(
                definition=definition,
                sop=sop_a,
                agent_task_id="task-wave-resolution",
                runtime="deterministic",
            ),
            config=config,
        )
        after = render_sandbox_policy(
            build_capability_policy(
                definition=definition,
                sop=sop_a,
                agent_task_id="task-wave-resolution",
                runtime="deterministic",
            ),
            config=config,
        )
        assert after.allowed_capability_ids == before.allowed_capability_ids
        assert after.allowed_capability_classes == before.allowed_capability_classes
        assert after.denied_capability_classes == before.denied_capability_classes


# ── The real thing, when there is one ─────────────────────────────────────────


@pytest.mark.sandbox
class TestProofSopAInARealSandbox:
    """
    Runtime qualification. Skipped until NemoClaw and OpenShell are installed.

    Kept as a skip rather than deleted so the gap between "architecture
    implemented" and "runtime qualified" is visible in the test report instead
    of living only in a document. Run with ``pytest -m sandbox``.
    """

    @pytest.fixture
    def openshell(self):
        pytest.importorskip(
            "openshell",
            reason="OpenShell is not installed; runtime qualification pending",
        )

    async def test_proof_sop_a_runs_inside_a_real_openshell_sandbox(self, openshell):
        pytest.skip(
            "Phase 20B: requires a qualified NemoClaw/OpenShell host. The "
            "adapter contract is implemented and tested; no runtime "
            "qualification has been performed."
        )
