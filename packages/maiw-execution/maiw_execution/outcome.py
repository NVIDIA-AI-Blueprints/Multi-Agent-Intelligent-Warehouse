# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Canonical execution outcome model for all warehouse write operations.

Phase 10E Batch 1 — Execution Semantics
"""

from __future__ import annotations

from enum import Enum


class ExecutionOutcome(str, Enum):
    """
    Canonical outcome for a single warehouse write execution attempt.

    Semantics
    ---------
    EXECUTED
        MAIW has sufficient evidence that the intended warehouse mutation occurred.
        The provider responded with success and the result is consistent with
        the requested desired state.

    NO_OP
        The requested desired state already existed; no new physical or logical
        mutation was required. The warehouse is in the correct state.

    DEFERRED
        The request is valid but cannot execute now because a required operational
        condition or resource is unavailable. The same request may succeed later.

    CONFLICT
        Current warehouse state makes the approved action invalid. A conflicting
        state (e.g. asset already assigned to a different task) must be resolved
        before this action can proceed.

    UNKNOWN
        The execution may have mutated warehouse state, but MAIW cannot currently
        determine the outcome (e.g. provider mutated state then response was lost).
        Do NOT automatically retry. Reconciliation is required before re-execution.

    FAILED
        MAIW has sufficient evidence that the requested mutation did not occur.
        The provider was not reached, or the provider rejected the request before
        any mutation was applied.

    Compatibility mapping (for legacy boolean callers)
    --------------------------------------------------
    EXECUTED  → executed=True,  success=True
    NO_OP     → executed=False, success=True   (state is correct, no new mutation)
    DEFERRED  → executed=False, success=False
    CONFLICT  → executed=False, success=False
    UNKNOWN   → executed=False, success=False  (do NOT treat as FAILED)
    FAILED    → executed=False, success=False
    """

    EXECUTED = "executed"
    NO_OP = "no_op"
    DEFERRED = "deferred"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"
    FAILED = "failed"


class AmbiguousWriteError(RuntimeError):
    """
    Raised by a provider or skill when it KNOWS a mutation occurred but cannot
    confirm the response (post-mutation network failure / timeout).

    Catching AmbiguousWriteError in BaseActionExecutor produces outcome=UNKNOWN.

    IMPORTANT: Only raise this when the mutation is known to have been committed.
    For pre-mutation failures (provider not reached, rejected before write),
    raise a regular exception — the executor will classify those as FAILED.
    """
