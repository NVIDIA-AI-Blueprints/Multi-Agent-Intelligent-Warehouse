# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
The two messages that cross the sandbox boundary, and the host-side checks on them.

Exactly two things move between a sandboxed agent runtime and the MAIW host:

    sandbox → host    SandboxRecommendedActionOutput   "here is what I think
                                                        should happen"
    host → sandbox    SandboxGovernanceInput           "here is what governance
                                                        decided"

Nothing else. No proposal, no execution result, no credential, no tool call. A
third message type would be a change to the authority model, not an addition to
this file.

**The asymmetry is deliberate.** The sandbox's message is a *recommendation* and
is treated as untrusted input: the host validates its binding to a live
procedure before it is allowed to influence anything. The host's message is a
*decision* and is the only thing that can advance a procedure past
``WAITING_FOR_GOVERNANCE``.

A note on what a ``RecommendedAction`` contains. Its ``capability`` field names
a PROPOSAL-class capability such as ``warehouse.wave.reprioritize``. That is not
a write and not a leak: PROPOSAL capabilities build an ``ActionProposal``
locally, and the actual write capabilities (``warehouse.*.reprioritize_direct``
and friends) are WRITE-class, never on any policy, and never reachable from the
sandbox. The sandbox may *name* an intervention. Only the host may perform one.

Threat model for this module: assume the sandbox is compromised and is sending
whatever it likes. Every validator below is written to be correct under that
assumption — which is why none of them trusts a field to identify itself and
all of them compare against host-held state.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from maiw_agents.assessment import RecommendedAction
from maiw_agents.contracts.delegation import GovernanceOutcome
from maiw_agents.contracts.procedure_state import (
    ProcedureExecutionState,
    ProcedureStatus,
)

logger = logging.getLogger(__name__)


# ── Errors ────────────────────────────────────────────────────────────────────


class SandboxBoundaryViolation(ValueError):
    """
    A message crossing the sandbox boundary failed host-side validation.

    Deliberately one error type for every rejection reason. A caller does not
    get to branch on *why* a boundary message was rejected and retry a narrower
    way — a rejected message is discarded, and the reason is for the log and the
    operator, not for control flow.
    """

    def __init__(
        self, *, reason: str, procedure_execution_id: str | None = None
    ) -> None:
        self.reason = reason
        self.procedure_execution_id = procedure_execution_id
        super().__init__(
            "sandbox boundary violation"
            + (
                f" (procedure={procedure_execution_id})"
                if procedure_execution_id
                else ""
            )
            + f": {reason}"
        )


# ── sandbox → host ────────────────────────────────────────────────────────────


class SandboxRecommendedActionOutput(BaseModel):
    """
    The serialised form of a ``RecommendedAction`` leaving the sandbox.

    The wrapper fields exist so the host can answer "does this belong to the
    procedure I am actually running, at the point I am actually at?" without
    asking the sender. A bare ``RecommendedAction`` carries no binding to a
    procedure, and an unbound recommendation from an untrusted process is not
    something a host should act on.
    """

    model_config = ConfigDict(frozen=True)

    procedure_execution_id: str
    agent_task_id: str
    trace_id: str
    recommended_action: RecommendedAction
    procedure_state_revision: int = Field(ge=0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def validate_sandbox_output(
    output: SandboxRecommendedActionOutput,
    *,
    procedure_state: ProcedureExecutionState,
) -> RecommendedAction:
    """
    Accept a recommendation from the sandbox, or reject it.

    Checked against ``procedure_state``, which the **host** holds — never
    against anything else the sandbox sent. The four checks, and what each one
    is actually for:

    ``procedure_execution_id``
        The recommendation belongs to this procedure. Stops a recommendation
        produced for one procedure from being replayed into another.

    ``agent_task_id``
        The procedure belongs to this task. Stops a stale sandbox that
        outlived its task from steering a newer one.

    ``procedure_state_revision``
        The sandbox reasoned from the state the host currently has. A
        recommendation computed against an older revision is stale: the world it
        describes has already moved. Rejecting it is what stops a restarted or
        lagging sandbox from re-recommending something already decided.

    ``status``
        The procedure is still live. A terminal procedure accepts no further
        recommendations, so a late message cannot reopen a closed decision.

    Returns the unwrapped ``RecommendedAction`` on success — the caller gets the
    MAIW contract, not the transport envelope, so downstream governance code has
    no sandbox-shaped types in it.
    """
    if output.procedure_execution_id != procedure_state.procedure_execution_id:
        raise SandboxBoundaryViolation(
            procedure_execution_id=output.procedure_execution_id,
            reason=(
                "procedure_execution_id does not match the active procedure "
                f"({procedure_state.procedure_execution_id!r})"
            ),
        )

    if output.agent_task_id != procedure_state.agent_task_id:
        raise SandboxBoundaryViolation(
            procedure_execution_id=output.procedure_execution_id,
            reason=(
                "agent_task_id does not match the active procedure "
                f"({procedure_state.agent_task_id!r})"
            ),
        )

    if procedure_state.is_terminal():
        raise SandboxBoundaryViolation(
            procedure_execution_id=output.procedure_execution_id,
            reason=(
                f"procedure is terminal ({procedure_state.status.value}); it "
                "accepts no further recommendations"
            ),
        )

    if output.procedure_state_revision != procedure_state.revision:
        raise SandboxBoundaryViolation(
            procedure_execution_id=output.procedure_execution_id,
            reason=(
                "stale procedure_state_revision "
                f"{output.procedure_state_revision} (host holds "
                f"{procedure_state.revision})"
            ),
        )

    logger.info(
        "sandbox recommendation accepted: procedure=%s task=%s trace=%s "
        "domain=%s capability=%s revision=%d",
        output.procedure_execution_id,
        output.agent_task_id,
        output.trace_id,
        output.recommended_action.domain,
        output.recommended_action.capability,
        output.procedure_state_revision,
    )
    return output.recommended_action


# ── host → sandbox ────────────────────────────────────────────────────────────


class SandboxGovernanceInput(BaseModel):
    """
    The serialised form of a ``GovernanceOutcome`` returning to a procedure.

    Produced on the host after the full governance path has run
    (``DecisionEngine`` → approval → ``ActionExecutor`` → MCP). By the time this
    exists, any write has already happened, on the host, outside the sandbox.
    This message reports that; it does not authorise it.
    """

    model_config = ConfigDict(frozen=True)

    procedure_execution_id: str
    agent_task_id: str
    governance_outcome: GovernanceOutcome
    expected_procedure_revision: int = Field(ge=0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def idempotency_key(self) -> tuple[str, str, int]:
        """
        What makes two deliveries of this outcome "the same delivery".

        Keyed on the proposal rather than on the message, so a retransmission
        with a fresh timestamp still collides. A proposal is decided once; a
        second arrival of that decision is a duplicate however it is packaged.
        """
        return (
            self.procedure_execution_id,
            self.governance_outcome.proposal_id,
            self.expected_procedure_revision,
        )


class GovernanceInbox:
    """
    Host-side dedupe ledger for governance outcomes.

    Exists because the dangerous restart is not the one that loses a message —
    it is the one that delivers a message twice. A procedure that applies the
    same APPROVED outcome twice can re-run its post-governance steps against a
    world that already moved.

    ``accept`` is idempotent rather than strict: a duplicate returns ``False``
    and is dropped, it does not raise. A retry that is *correctly* retrying
    should not be punished for it — only a *mismatched* message is an error, and
    that is ``validate_governance_input``'s job, not this one's.

    In-memory and per-process. A multi-process host needs the same ledger backed
    by the store that already holds ``ProcedureExecutionState``; see
    ``docs/architecture/NEMOCLAW_OPENSHELL_INTEGRATION.md`` § Deferred work.
    """

    def __init__(self) -> None:
        self._seen: set[tuple[str, str, int]] = set()
        self._applied: set[tuple[str, str, int]] = set()
        self._accepted: dict[tuple[str, str, int], SandboxGovernanceInput] = {}

    def accept(self, governance_input: SandboxGovernanceInput) -> bool:
        """Return True if newly accepted, False if already applied."""
        key = governance_input.idempotency_key
        if key in self._seen:
            logger.warning(
                "duplicate governance outcome dropped: procedure=%s proposal=%s "
                "revision=%d",
                *key,
            )
            return False
        self._seen.add(key)
        self._accepted[key] = governance_input
        return True

    def has_seen(self, governance_input: SandboxGovernanceInput) -> bool:
        return governance_input.idempotency_key in self._seen

    def mark_applied(self, governance_input: SandboxGovernanceInput) -> None:
        """Record that the accepted outcome's resume transition completed."""
        self._applied.add(governance_input.idempotency_key)

    def is_applied(self, governance_input: SandboxGovernanceInput) -> bool:
        return governance_input.idempotency_key in self._applied

    def accepted_unapplied(self) -> list[SandboxGovernanceInput]:
        """Accepted outcomes whose resume was never marked applied."""
        return [v for k, v in self._accepted.items() if k not in self._applied]


class JsonFileGovernanceInbox:
    """
    Host-restart-safe dedupe ledger for governance outcomes.

    Identical semantics to ``GovernanceInbox`` but backed by an append-only
    JSON-lines file on the host filesystem. Each accepted idempotency key is
    flushed to disk before ``accept`` returns, so a process restart that
    interrupts delivery after the key was written but before the SOP Engine
    processed the outcome will correctly recognise the re-delivery as a
    duplicate rather than applying the governance decision a second time.

    Durability claim (single-node, same as JsonFileProcedureStateStore):
        SURVIVES      process exit, crash, and restart on the same filesystem.
        SURVIVES      partial writes (entries are line-delimited JSON; a
                      truncated tail line is skipped on load with a warning).
        DOES NOT      provide multi-replica coordination or HA.

    File format: one JSON object per line, each with keys
        ``procedure_execution_id``, ``proposal_id``, ``expected_revision``.
    The file grows monotonically — entries are never removed. Keys are
    re-loaded into an in-memory set on construction, so lookup is O(1).

    v2.0.1 round 2 (crash between accept and resume): an ``accepted`` entry
    also carries the full ``governance_input`` payload, and a second
    ``applied`` entry is appended once the resume transition has been
    checkpointed.  On restart ``accepted_unapplied()`` returns every outcome
    that was accepted but never applied, so ``ProcedureHost`` can replay the
    resume exactly once.  Entries written before round 2 (no ``event`` field)
    are treated as accepted *and* applied — they carry no payload to replay.

    The inbox directory is the same root as ``JsonFileProcedureStateStore``
    when the caller uses the shared persistence root; the two stores do not
    share files.
    """

    _FILENAME = "governance_inbox.jsonl"

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / self._FILENAME
        self._seen: set[tuple[str, str, int]] = set()
        self._applied: set[tuple[str, str, int]] = set()
        self._accepted: dict[tuple[str, str, int], dict] = {}
        self._load()

    def _load(self) -> None:
        """Replay the persisted log into ``_seen`` on startup."""
        if not self._path.exists():
            return
        with self._path.open(encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, start=1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    entry = json.loads(raw)
                    key = (
                        str(entry["procedure_execution_id"]),
                        str(entry["proposal_id"]),
                        int(entry["expected_revision"]),
                    )
                    event = entry.get("event")
                    if event == "applied":
                        self._applied.add(key)
                        continue
                    self._seen.add(key)
                    if event == "accepted" and isinstance(
                        entry.get("governance_input"), dict
                    ):
                        self._accepted[key] = entry["governance_input"]
                    else:
                        # Pre-round-2 entry: no payload, cannot be replayed.
                        self._applied.add(key)
                except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
                    logger.warning(
                        "JsonFileGovernanceInbox: skipping malformed entry at "
                        "line %d in %s: %s",
                        lineno,
                        self._path,
                        exc,
                    )

    def _persist(
        self,
        key: tuple[str, str, int],
        *,
        event: str = "accepted",
        payload: dict | None = None,
    ) -> None:
        """Atomically append one entry to the on-disk log."""
        record: dict = {
            "procedure_execution_id": key[0],
            "proposal_id": key[1],
            "expected_revision": key[2],
            "event": event,
        }
        if payload is not None:
            record["governance_input"] = payload
        entry = json.dumps(record) + "\n"
        # Open in append mode then fsync so the entry survives a crash.
        # We do NOT use tempfile+replace for append-only logs — the file grows
        # monotonically and atomicity at the line level is sufficient.
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(entry)
            fh.flush()
            os.fsync(fh.fileno())

    def accept(self, governance_input: SandboxGovernanceInput) -> bool:
        """Return True if newly accepted, False if already applied."""
        key = governance_input.idempotency_key
        if key in self._seen:
            logger.warning(
                "duplicate governance outcome dropped: procedure=%s proposal=%s "
                "revision=%d",
                *key,
            )
            return False
        payload = governance_input.model_dump(mode="json")
        self._persist(key, event="accepted", payload=payload)
        self._seen.add(key)
        self._accepted[key] = payload
        return True

    def has_seen(self, governance_input: SandboxGovernanceInput) -> bool:
        return governance_input.idempotency_key in self._seen

    def mark_applied(self, governance_input: SandboxGovernanceInput) -> None:
        """
        Durably record that the accepted outcome's resume transition has been
        checkpointed.  Idempotent.
        """
        key = governance_input.idempotency_key
        if key in self._applied:
            return
        self._persist(key, event="applied")
        self._applied.add(key)

    def is_applied(self, governance_input: SandboxGovernanceInput) -> bool:
        return governance_input.idempotency_key in self._applied

    def accepted_unapplied(self) -> list[SandboxGovernanceInput]:
        """Accepted outcomes whose resume was never marked applied (replayable)."""
        out: list[SandboxGovernanceInput] = []
        for key, payload in self._accepted.items():
            if key in self._applied:
                continue
            try:
                out.append(SandboxGovernanceInput.model_validate(payload))
            except Exception as exc:  # noqa: BLE001 - corrupt payload: report, skip
                logger.error(
                    "JsonFileGovernanceInbox: accepted entry %s cannot be "
                    "replayed (%s)",
                    key,
                    exc,
                )
        return out


def validate_governance_input(
    governance_input: SandboxGovernanceInput,
    *,
    procedure_state: ProcedureExecutionState,
    inbox: GovernanceInbox | None = None,
) -> GovernanceOutcome:
    """
    Validate a governance outcome before the SOP Engine is allowed to see it.

    Runs on the host, before ``SOPEngine.resume_after_governance``. The engine
    duck-types the outcome it is handed, which is the right call for a
    runtime-neutral engine and the wrong thing to rely on at a trust boundary —
    so the binding checks happen here, where the types are known.

    Rejects, in order: a mismatched procedure, a mismatched task, a procedure
    that was not waiting for governance, and a revision that moved underneath
    the decision. Then, if an ``inbox`` is supplied, drops duplicates.

    Raises ``SandboxBoundaryViolation`` on mismatch. A duplicate is not a
    mismatch and does not raise: the outcome is returned unchanged after the
    inbox records the drop. A caller that needs to distinguish "newly applied"
    from "already applied" calls ``inbox.accept`` itself and branches on that.
    """
    if (
        governance_input.procedure_execution_id
        != procedure_state.procedure_execution_id
    ):
        raise SandboxBoundaryViolation(
            procedure_execution_id=governance_input.procedure_execution_id,
            reason=(
                "procedure_execution_id does not match the stored procedure "
                f"({procedure_state.procedure_execution_id!r})"
            ),
        )

    if governance_input.agent_task_id != procedure_state.agent_task_id:
        raise SandboxBoundaryViolation(
            procedure_execution_id=governance_input.procedure_execution_id,
            reason=(
                "agent_task_id does not match the stored procedure "
                f"({procedure_state.agent_task_id!r})"
            ),
        )

    if procedure_state.status is not ProcedureStatus.WAITING_FOR_GOVERNANCE:
        raise SandboxBoundaryViolation(
            procedure_execution_id=governance_input.procedure_execution_id,
            reason=(
                f"procedure is {procedure_state.status.value}, not "
                "waiting_for_governance; a governance outcome has nothing to "
                "resume"
            ),
        )

    if governance_input.expected_procedure_revision != procedure_state.revision:
        raise SandboxBoundaryViolation(
            procedure_execution_id=governance_input.procedure_execution_id,
            reason=(
                "governance outcome expects revision "
                f"{governance_input.expected_procedure_revision} but the host "
                f"holds {procedure_state.revision}"
            ),
        )

    if inbox is not None and not inbox.accept(governance_input):
        logger.info(
            "governance outcome already applied; resume suppressed: "
            "procedure=%s proposal=%s",
            governance_input.procedure_execution_id,
            governance_input.governance_outcome.proposal_id,
        )

    return governance_input.governance_outcome


__all__ = [
    "GovernanceInbox",
    "JsonFileGovernanceInbox",
    "SandboxBoundaryViolation",
    "SandboxGovernanceInput",
    "SandboxRecommendedActionOutput",
    "validate_governance_input",
    "validate_sandbox_output",
]
