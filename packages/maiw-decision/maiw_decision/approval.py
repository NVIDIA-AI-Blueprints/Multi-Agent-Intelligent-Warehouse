# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Approval store for Phase 10E Batch 2 — single-use approval governance.

ApprovalState lifecycle:
    PENDING → APPROVED → CONSUMED  (happy path)
    PENDING → REJECTED             (human declines)
    PENDING → EXPIRED              (TTL elapsed before decision)
    APPROVED → EXPIRED             (TTL elapsed before consumption)

SINGLE-PROCESS SAFETY: InMemoryApprovalStore uses no distributed locks.
All state transitions are synchronous (no await between check and write)
and are therefore safe under asyncio cooperative multitasking within one
replica. Multi-replica exactly-once is out of scope for Phase 10E.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable

from .models import ApprovalRecord, ApprovalState, AuthorityType

logger = logging.getLogger(__name__)

_DEFAULT_TTL_SECONDS = 3600  # 1 hour — appropriate for live demo sessions


class ApprovalAlreadyDecided(RuntimeError):
    """Raised when approve() or reject() is called on a non-PENDING record."""


class ApprovalExpired(RuntimeError):
    """Raised when approve() is called after the record's expires_at wall-clock TTL."""


class ApprovalNotFound(KeyError):
    """Raised when an approval_id does not exist in the store."""


@runtime_checkable
class ApprovalStore(Protocol):
    def create(
        self,
        *,
        proposal_id: str,
        decision_id: str,
        warehouse_id: str | None = None,
        trace_id: str | None = None,
        authority_type: AuthorityType = AuthorityType.HUMAN,
        ttl_seconds: int | None = None,
    ) -> ApprovalRecord: ...

    def get(self, approval_id: str) -> ApprovalRecord | None: ...

    def approve(self, approval_id: str, *, approved_by: str) -> ApprovalRecord: ...

    def reject(self, approval_id: str, *, rejected_by: str) -> ApprovalRecord: ...

    def consume(self, approval_id: str) -> ApprovalRecord | None: ...

    def reset(self) -> None: ...


class InMemoryApprovalStore:
    """
    In-process approval store with single-use consume semantics.

    SINGLE-PROCESS SAFETY: state transitions are synchronous (no await
    between check and write). Safe for asyncio cooperative multitasking.
    Multi-replica exactly-once is out of scope for Phase 10E.
    """

    def __init__(self, *, default_ttl_seconds: int = _DEFAULT_TTL_SECONDS) -> None:
        self._default_ttl = default_ttl_seconds
        self._store: dict[str, ApprovalRecord] = {}

    def create(
        self,
        *,
        proposal_id: str,
        decision_id: str,
        warehouse_id: str | None = None,
        trace_id: str | None = None,
        authority_type: AuthorityType = AuthorityType.HUMAN,
        ttl_seconds: int | None = None,
    ) -> ApprovalRecord:
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        record = ApprovalRecord(
            proposal_id=proposal_id,
            decision_id=decision_id,
            warehouse_id=warehouse_id,
            trace_id=trace_id,
            authority_type=authority_type,
            state=ApprovalState.PENDING,
            expires_at=expires_at,
        )
        self._store[record.approval_id] = record
        logger.info(
            "ApprovalStore.create: approval_id=%s proposal_id=%s decision_id=%s expires_at=%s",
            record.approval_id,
            proposal_id,
            decision_id,
            expires_at.isoformat(),
        )
        return record

    def get(self, approval_id: str) -> ApprovalRecord | None:
        return self._store.get(approval_id)

    def approve(self, approval_id: str, *, approved_by: str) -> ApprovalRecord:
        record = self._store.get(approval_id)
        if record is None:
            raise ApprovalNotFound(approval_id)
        if record.state != ApprovalState.PENDING:
            raise ApprovalAlreadyDecided(
                f"Cannot approve approval_id={approval_id!r}: "
                f"current state={record.state.value!r}"
            )
        if record.expires_at and datetime.now(timezone.utc) > record.expires_at:
            record.state = ApprovalState.EXPIRED
            raise ApprovalExpired(
                f"approval_id={approval_id!r} expired at {record.expires_at.isoformat()}"
            )
        record.state = ApprovalState.APPROVED
        record.approved_by = approved_by
        record.approved_at = datetime.now(timezone.utc)
        logger.info(
            "ApprovalStore.approve: approval_id=%s approved_by=%r",
            approval_id,
            approved_by,
        )
        return record

    def reject(self, approval_id: str, *, rejected_by: str) -> ApprovalRecord:
        record = self._store.get(approval_id)
        if record is None:
            raise ApprovalNotFound(approval_id)
        if record.state != ApprovalState.PENDING:
            raise ApprovalAlreadyDecided(
                f"Cannot reject approval_id={approval_id!r}: "
                f"current state={record.state.value!r}"
            )
        record.state = ApprovalState.REJECTED
        record.approved_by = rejected_by
        record.approved_at = datetime.now(timezone.utc)
        logger.info(
            "ApprovalStore.reject: approval_id=%s rejected_by=%r",
            approval_id,
            rejected_by,
        )
        return record

    def consume(self, approval_id: str) -> ApprovalRecord | None:
        """
        Atomic APPROVED → CONSUMED transition.

        Returns the record if the transition succeeded; None if the record
        was not in APPROVED state (already consumed, rejected, expired, or
        not found). Never raises — callers must check the return value.

        SINGLE-PROCESS SAFETY: no await between check and state assignment.
        """
        record = self._store.get(approval_id)
        if record is None or record.state != ApprovalState.APPROVED:
            return None
        record.state = ApprovalState.CONSUMED
        logger.info("ApprovalStore.consume: approval_id=%s → CONSUMED", approval_id)
        return record

    def reset(self) -> None:
        self._store.clear()
