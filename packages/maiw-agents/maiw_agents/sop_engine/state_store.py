# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW SOP Engine V2 — procedure state persistence.

The acceptance statement this module exists to satisfy:

    After a crash or restart, MAIW must know exactly which procedure version was
    running, which step and attempt were active, what evidence had been proven,
    what capabilities were permitted, and whether a warehouse write may already
    have occurred — without granting the sandbox any additional authority.

A store is a *record keeper*, not an actor. It holds ``ProcedureExecutionState``
and nothing else. Note what is absent from this module, deliberately and
permanently:

    no ActionExecutor          no DecisionEngine       no MCP client
    no warehouse credentials   no WRITE capability     no model gateway

Persisting a procedure does not move any authority into the SOP Engine. A
restored procedure that was waiting on governance is still waiting on
governance; a restored procedure whose write already landed still proves that by
re-reading authoritative state, never by re-issuing the write.

Two implementations are provided:

    InMemoryProcedureStateStore   canonical semantics; unit tests, demo, and
                                  in-process recovery. Does NOT survive the
                                  process exiting.
    JsonFileProcedureStateStore   the same semantics written to one JSON file
                                  per procedure, atomically. Survives process
                                  restart on a single node. Not a multi-replica
                                  or highly-available store — see the class
                                  docstring for the exact claim.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..contracts.procedure_state import ProcedureExecutionState

logger = logging.getLogger(__name__)


# ── Errors ────────────────────────────────────────────────────────────────────

class ProcedureStateStoreError(RuntimeError):
    """Base class for every store failure."""


class StaleRevisionError(ProcedureStateStoreError):
    """
    A save was attempted against a revision that is no longer current.

    This is the optimistic-concurrency failure: two writers read the same
    procedure state and both tried to advance it. The second one loses. For a
    procedure that may be governing a real warehouse write, losing loudly is the
    only safe outcome — a silent last-writer-wins would let one writer's notion
    of "the write already happened" be overwritten by another's.
    """

    def __init__(self, procedure_execution_id: str, expected: int | None, actual: int) -> None:
        self.procedure_execution_id = procedure_execution_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Stale revision for procedure {procedure_execution_id!r}: "
            f"caller expected revision {expected}, store holds {actual}."
        )


class TerminalStateError(ProcedureStateStoreError):
    """
    A save was attempted against a procedure that has already finished.

    COMPLETED, FAILED and ESCALATED are final. A restart must not be able to
    re-open a closed procedure and advance it a second time — that is precisely
    how a governed write gets repeated.
    """

    def __init__(self, procedure_execution_id: str, status: str) -> None:
        self.procedure_execution_id = procedure_execution_id
        self.status = status
        super().__init__(
            f"Procedure {procedure_execution_id!r} is terminal ({status}) and "
            "may not be overwritten."
        )


# ── Protocol ──────────────────────────────────────────────────────────────────

@runtime_checkable
class ProcedureStateStore(Protocol):
    """
    Durable record of procedure execution state.

    Implementations must honour three rules, all of which the SOP Engine relies
    on for restart safety:

      1. ``save`` returns the stored state with ``revision`` incremented. The
         caller is expected to adopt the returned value.
      2. ``save`` with ``expected_revision`` raises ``StaleRevisionError`` on a
         mismatch rather than overwriting.
      3. A terminal procedure may not be overwritten (``TerminalStateError``).
    """

    async def save(
        self,
        state: ProcedureExecutionState,
        *,
        expected_revision: int | None = None,
    ) -> ProcedureExecutionState:
        """Persist ``state``, returning it with the incremented revision."""
        ...

    async def load(
        self,
        procedure_execution_id: str,
    ) -> ProcedureExecutionState | None:
        """Return the stored state, or None if this procedure is unknown."""
        ...

    async def delete(
        self,
        procedure_execution_id: str,
    ) -> None:
        """Remove the stored state. Deleting an unknown id is not an error."""
        ...


# ── Shared write rules ────────────────────────────────────────────────────────

def _check_writable(
    existing: ProcedureExecutionState | None,
    incoming: ProcedureExecutionState,
    expected_revision: int | None,
) -> None:
    """
    Apply the terminal-immutability and optimistic-concurrency rules.

    Shared by every implementation so the two stores cannot drift apart on the
    semantics that restart safety depends on.
    """
    if existing is not None and existing.is_terminal():
        raise TerminalStateError(existing.procedure_execution_id, existing.status.value)

    if expected_revision is None:
        return

    actual = existing.revision if existing is not None else 0
    if expected_revision != actual:
        raise StaleRevisionError(incoming.procedure_execution_id, expected_revision, actual)


# ── In-memory implementation ──────────────────────────────────────────────────

class InMemoryProcedureStateStore:
    """
    Process-local procedure state store — canonical semantics.

    Durability claim, stated exactly: this store survives an *engine* restart
    within one process (the engine is reconstructed, the state is reloaded) and
    is the implementation used by the recovery tests, which simulate a crash by
    discarding the engine and building a new one against the same store. It does
    NOT survive the process exiting. For that, use
    ``JsonFileProcedureStateStore``.

    Thread/task safety: every mutation is serialised behind an asyncio.Lock, and
    values are deep-copied on the way in and out, so a caller holding a state
    object can never mutate what the store holds.
    """

    def __init__(self) -> None:
        self._states: dict[str, ProcedureExecutionState] = {}
        self._lock = asyncio.Lock()

    async def save(
        self,
        state: ProcedureExecutionState,
        *,
        expected_revision: int | None = None,
    ) -> ProcedureExecutionState:
        async with self._lock:
            existing = self._states.get(state.procedure_execution_id)
            _check_writable(existing, state, expected_revision)

            stored = state.model_copy(deep=True, update={"revision": state.revision + 1})
            self._states[state.procedure_execution_id] = stored
            logger.debug(
                "ProcedureStateStore.save: procedure=%s step=%s status=%s revision=%d",
                stored.procedure_execution_id,
                stored.current_step_id,
                stored.status.value,
                stored.revision,
            )
            return stored.model_copy(deep=True)

    async def load(
        self,
        procedure_execution_id: str,
    ) -> ProcedureExecutionState | None:
        async with self._lock:
            stored = self._states.get(procedure_execution_id)
            return stored.model_copy(deep=True) if stored is not None else None

    async def delete(self, procedure_execution_id: str) -> None:
        async with self._lock:
            self._states.pop(procedure_execution_id, None)

    async def list_ids(self) -> list[str]:
        """Every procedure id currently held (introspection / tests)."""
        async with self._lock:
            return sorted(self._states)


# ── JSON file implementation ──────────────────────────────────────────────────

class JsonFileProcedureStateStore:
    """
    Single-node durable store: one atomically-written JSON file per procedure.

    Durability claim, stated exactly — this is the honest scope, not a
    production-database claim:

        SURVIVES      process exit, crash, and restart on the same filesystem.
        SURVIVES      partial writes (temp file + os.replace is atomic on POSIX).
        DOES NOT      provide multi-replica coordination, failover, or HA.
        DOES NOT      provide cross-host locking — the revision check detects a
                      concurrent writer but two hosts on a shared mount can still
                      interleave between the read and the replace.

    MAIW has no Postgres/Redis persistence layer today (the existing
    ApprovalStore and CopilotStore are both in-memory), so there is no durable
    abstraction to adopt. This store exists so that "procedure state is
    recoverable across restart" is a demonstrable property rather than a
    notional one, while being explicit that single-node is its limit.
    """

    def __init__(self, directory: str | os.PathLike[str]) -> None:
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _path(self, procedure_execution_id: str) -> Path:
        # Procedure ids are engine-minted UUID4s, but never build a path from an
        # unvalidated id: a traversal component would escape the store directory.
        safe = procedure_execution_id.replace("/", "_").replace("\\", "_").replace("..", "_")
        return self._dir / f"{safe}.json"

    def _read(self, procedure_execution_id: str) -> ProcedureExecutionState | None:
        path = self._path(procedure_execution_id)
        if not path.exists():
            return None
        return ProcedureExecutionState.model_validate_json(path.read_text(encoding="utf-8"))

    async def save(
        self,
        state: ProcedureExecutionState,
        *,
        expected_revision: int | None = None,
    ) -> ProcedureExecutionState:
        async with self._lock:
            existing = self._read(state.procedure_execution_id)
            _check_writable(existing, state, expected_revision)

            stored = state.model_copy(deep=True, update={"revision": state.revision + 1})
            payload = stored.model_dump_json()

            # Atomic replace: a crash mid-write leaves the previous revision
            # intact rather than a truncated file the engine would fail to load.
            path = self._path(stored.procedure_execution_id)
            fd, tmp_name = tempfile.mkstemp(dir=str(self._dir), suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp_name, path)
            except BaseException:
                Path(tmp_name).unlink(missing_ok=True)
                raise

            logger.debug(
                "JsonFileProcedureStateStore.save: procedure=%s revision=%d path=%s",
                stored.procedure_execution_id, stored.revision, path,
            )
            return stored

    async def load(
        self,
        procedure_execution_id: str,
    ) -> ProcedureExecutionState | None:
        async with self._lock:
            return self._read(procedure_execution_id)

    async def delete(self, procedure_execution_id: str) -> None:
        async with self._lock:
            self._path(procedure_execution_id).unlink(missing_ok=True)


__all__ = [
    "ProcedureStateStore",
    "ProcedureStateStoreError",
    "StaleRevisionError",
    "TerminalStateError",
    "InMemoryProcedureStateStore",
    "JsonFileProcedureStateStore",
]
