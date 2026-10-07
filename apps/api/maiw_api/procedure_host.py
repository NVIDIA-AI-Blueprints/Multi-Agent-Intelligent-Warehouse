# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Host-side procedure service for the shipped MAIW app (v2.0.1, P1-03).

``ProcedureHost`` is the composition-root object that binds the SOP Engine to
the runtime's durable ``ProcedureStateStore`` and ``GovernanceInbox``. It is
constructed once by ``maiw_api.bootstrap`` and exposed as
``MAIWRuntime.procedure_host``; there is no other place in the shipped app that
runs a procedure against persistent state.

It is the host half of the sandbox boundary described in
``integrations/nemoclaw/boundary_contracts.py``:

    start()                  run an SOP until it finishes or pauses at
                             WAITING_FOR_GOVERNANCE — every lifecycle
                             transition is checkpointed to the durable store
    accept_recommendation()  validate a sandbox RecommendedAction against the
                             *stored* procedure state (never against the sender)
    apply_governance()       validate a governance outcome against stored state,
                             record it in the durable inbox exactly once, then
                             resume (validation only — the engine never writes)
    resume()                 continue a restored, non-terminal procedure

Authority: this object holds NO ActionExecutor, NO DecisionEngine, NO MCP
client and NO credentials. A governance outcome reaching ``apply_governance``
describes a write that already happened on the host's governed path
(DecisionEngine → approval → ActionExecutor); this service only records it and
lets the SOP Engine prove the outcome against authoritative state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from maiw_agents.contracts.procedure_state import (
    ProcedureExecutionState,
    ProcedureStatus,
)
from maiw_agents.sop_engine import SOPEngine

logger = logging.getLogger(__name__)


class ProcedureNotFound(LookupError):
    """No stored procedure with the given id."""


@dataclass(frozen=True)
class GovernanceApplication:
    """Result of ``ProcedureHost.apply_governance``."""

    applied: bool
    """True if this delivery was newly accepted and the procedure resumed."""

    duplicate: bool
    """True if the durable inbox had already recorded this outcome."""

    state: ProcedureExecutionState


class ProcedureHost:
    """Runs and resumes SOP procedures against the runtime's durable stores."""

    def __init__(
        self,
        *,
        store: Any,
        inbox: Any,
        validator_registry: Any | None = None,
    ) -> None:
        if store is None or inbox is None:
            raise ValueError("ProcedureHost requires a procedure store and an inbox")
        self._store = store
        self._inbox = inbox
        self._validators = validator_registry

    @property
    def store(self) -> Any:
        return self._store

    @property
    def inbox(self) -> Any:
        return self._inbox

    def _engine(self, executor: Any, trace_id: str) -> SOPEngine:
        return SOPEngine(
            executor=executor,
            validator_registry=self._validators,
            trace_id=trace_id,
            store=self._store,
        )

    # ── Reads ─────────────────────────────────────────────────────────────────

    async def load(self, procedure_execution_id: str) -> ProcedureExecutionState | None:
        return await self._store.load(procedure_execution_id)

    async def _require(self, procedure_execution_id: str) -> ProcedureExecutionState:
        state = await self._store.load(procedure_execution_id)
        if state is None:
            raise ProcedureNotFound(procedure_execution_id)
        return state

    async def list_procedures(self) -> list[ProcedureExecutionState]:
        """Every stored procedure (restart recovery / operator visibility)."""
        out: list[ProcedureExecutionState] = []
        for pid in await self._store.list_ids():
            state = await self._store.load(pid)
            if state is not None:
                out.append(state)
        return out

    async def pending(self) -> list[ProcedureExecutionState]:
        """Stored procedures that are not terminal (running or awaiting governance)."""
        return [s for s in await self.list_procedures() if not s.is_terminal()]

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(
        self,
        *,
        definition: Any,
        sop: Any,
        agent_task_id: str,
        context: Any,
        executor: Any,
        warehouse_state_snapshot: Any | None = None,
    ) -> ProcedureExecutionState:
        """Run a new procedure; it is persisted at every lifecycle transition."""
        engine = self._engine(executor, getattr(context, "trace_id", "") or "")
        state = await engine.run_procedure(
            definition=definition,
            sop=sop,
            agent_task_id=agent_task_id,
            context=context,
            warehouse_state_snapshot=warehouse_state_snapshot,
        )
        logger.info(
            "ProcedureHost.start: procedure=%s sop=%s status=%s revision=%d",
            state.procedure_execution_id,
            state.sop_id,
            state.status.value,
            state.revision,
        )
        return state

    async def resume(
        self,
        procedure_execution_id: str,
        *,
        definition: Any,
        sop: Any,
        context: Any,
        executor: Any,
        warehouse_state_snapshot: Any | None = None,
    ) -> ProcedureExecutionState:
        """
        Continue a restored procedure from its stored state (no replay).

        A procedure parked at WAITING_FOR_GOVERNANCE is returned unchanged
        without touching the executor: it advances only through
        ``apply_governance``. Resuming it here would re-run the hand-off step
        and could emit the same recommendation twice after a restart.
        """
        state = await self._require(procedure_execution_id)
        if state.status is ProcedureStatus.WAITING_FOR_GOVERNANCE or state.is_terminal():
            return state
        engine = self._engine(executor, state.trace_id)
        return await engine.run_procedure(
            definition=definition,
            sop=sop,
            agent_task_id=state.agent_task_id,
            context=context,
            initial_state=state,
            warehouse_state_snapshot=warehouse_state_snapshot,
        )

    async def accept_recommendation(self, output: Any) -> Any:
        """Validate a sandbox recommendation against the stored procedure state."""
        from integrations.nemoclaw.boundary_contracts import validate_sandbox_output

        state = await self._require(output.procedure_execution_id)
        return validate_sandbox_output(output, procedure_state=state)

    async def apply_governance(
        self,
        governance_input: Any,
        *,
        definition: Any,
        sop: Any,
        context: Any,
        executor: Any,
        warehouse_state_snapshot: Any | None = None,
    ) -> GovernanceApplication:
        """
        Apply a host governance outcome exactly once.

        Order matters and is the restart-safety argument:
          1. a delivery the durable inbox has already seen is dropped — no
             validation error, no resume, no second execution;
          2. the outcome is bound to the *stored* procedure (id, task, status,
             revision) — a forged or stale outcome raises before anything runs;
          3. the idempotency key is fsynced to the inbox *before* the engine
             resumes, so a crash between (3) and (4) can never apply it twice;
          4. the engine resumes with validation only and checkpoints the result.
        """
        from integrations.nemoclaw.boundary_contracts import validate_governance_input

        state = await self._require(governance_input.procedure_execution_id)

        if self._inbox.has_seen(governance_input):
            logger.warning(
                "ProcedureHost.apply_governance: duplicate delivery dropped "
                "procedure=%s proposal=%s",
                governance_input.procedure_execution_id,
                governance_input.governance_outcome.proposal_id,
            )
            return GovernanceApplication(applied=False, duplicate=True, state=state)

        outcome = validate_governance_input(governance_input, procedure_state=state)

        if not self._inbox.accept(governance_input):  # pragma: no cover - raced
            return GovernanceApplication(applied=False, duplicate=True, state=state)

        engine = self._engine(executor, state.trace_id)
        resumed = await engine.resume_after_governance(
            definition=definition,
            sop=sop,
            proc_state=state,
            context=context,
            governance_outcome=outcome,
            warehouse_state_snapshot=warehouse_state_snapshot,
        )
        logger.info(
            "ProcedureHost.apply_governance: procedure=%s decision=%s status=%s "
            "revision=%d",
            resumed.procedure_execution_id,
            getattr(outcome, "decision_outcome", None),
            resumed.status.value,
            resumed.revision,
        )
        return GovernanceApplication(applied=True, duplicate=False, state=resumed)


def summarize(state: ProcedureExecutionState) -> dict[str, Any]:
    """
    Operator-safe summary of a stored procedure. Step outputs and evidence
    payloads are intentionally omitted (counts only).
    """
    return {
        "procedure_execution_id": state.procedure_execution_id,
        "agent_task_id": state.agent_task_id,
        "trace_id": state.trace_id,
        "sop_id": state.sop_id,
        "sop_version": state.sop_version,
        "status": state.status.value,
        "waiting_for_governance": state.status is ProcedureStatus.WAITING_FOR_GOVERNANCE,
        "current_step_id": state.current_step_id,
        "completed_step_ids": list(state.completed_step_ids),
        "attempt_by_step": dict(state.attempt_by_step),
        "loop_exhausted_step_ids": list(state.loop_exhausted_step_ids),
        "branch_history": list(state.branch_history),
        "evidence_count": len(state.evidence_refs),
        "revision": state.revision,
        "started_at": state.started_at.isoformat(),
        "last_updated_at": state.last_updated_at.isoformat(),
    }


__all__ = [
    "ProcedureHost",
    "ProcedureNotFound",
    "GovernanceApplication",
    "summarize",
]
