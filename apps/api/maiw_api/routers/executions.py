# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Execution journal + reconciliation for every profile (v2.0.1 round 3, NEW3-P1-02).

Third independent re-audit: on the real MCP transport an ambiguous write was
reported FAILED, the only reconciliation route (``/api/v1/demo/reconcile``)
answered 503 outside demo mode, and an identical retry executed a second write.

This router is the production owner of UNKNOWN executions:

``GET  /api/v1/executions``                       journal (``?status=unresolved``)
``GET  /api/v1/executions/{execution_id}``        one record
``POST /api/v1/executions/{execution_id}/reconcile``
    authoritative re-read through the canonical MCP read skill for the
    record's domain → CONFIRMED_EXECUTED / CONFIRMED_NOT_EXECUTED /
    INDETERMINATE, stored with the ORIGINAL execution_id, proposal_id,
    decision_id and trace_id.  The original UNKNOWN outcome is never
    rewritten, nothing is retried, and no proposal, decision or approval is
    created.  CONFIRMED_* lifts the block on the target; INDETERMINATE keeps
    it (operator investigation required).

Every route requires the operator write credential (same dependency as the
governed write routes) — reconciliation decides whether further writes to a
target are allowed, so it is part of the write authority boundary.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from maiw_api.dependencies import get_runtime
from maiw_api.write_auth import require_operator_write

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1",
    tags=["Executions"],
    dependencies=[Depends(require_operator_write)],
)

_DOMAINS = ("equipment", "labor", "wave")


class ReconcileBody(BaseModel):
    trace_id: str | None = None


def _registries(runtime: Any) -> dict[str, Any]:
    out = {}
    for domain in _DOMAINS:
        registry = getattr(runtime, f"{domain}_registry", None)
        if registry is not None:
            out[domain] = registry
    return out


def _find(runtime: Any, execution_id: str) -> tuple[str, Any, Any]:
    for domain, registry in _registries(runtime).items():
        record = registry.get_by_execution_id(execution_id)
        if record is not None:
            return domain, registry, record
    raise HTTPException(
        status_code=404,
        detail=f"No execution record found for execution_id={execution_id!r}",
    )


def record_view(domain: str, record: Any) -> dict[str, Any]:
    """JSON view of an ExecutionRecord (no secrets; identity chain included)."""
    intent = record.intent
    rec = record.reconciliation
    result = record.result
    return {
        "execution_id": record.execution_id,
        "domain": domain,
        "capability": record.capability,
        "target": intent.target if intent else None,
        "proposal_id": record.proposal_id,
        "decision_id": intent.decision_id if intent else None,
        "approval_id": intent.approval_id if intent else None,
        "idempotency_key": record.idempotency_key,
        "trace_id": intent.trace_id if intent else None,
        "outcome": record.outcome.value if record.outcome is not None else None,
        "effective_status": record.effective_status,
        "unresolved": record.unresolved,
        "recovered_after_restart": record.recovered_after_restart,
        "error_code": getattr(result, "error_code", None),
        "started_at": record.started_at.isoformat(),
        "completed_at": (
            record.completed_at.isoformat() if record.completed_at else None
        ),
        "expected_effect": dict(intent.expected_effect) if intent else {},
        "reconciliation": (
            {
                "reconciliation_id": rec.reconciliation_id,
                "outcome": rec.outcome.value,
                "reconciled_at": rec.reconciled_at.isoformat(),
                "error": rec.error,
                "trace_id": rec.trace_id,
            }
            if rec is not None
            else None
        ),
    }


@router.get("/executions")
async def list_executions(status: str = "unresolved", runtime=Depends(get_runtime)):
    """Execution journal across write domains (``status``: unresolved | all)."""
    if status not in ("unresolved", "all"):
        raise HTTPException(status_code=422, detail="status must be unresolved|all")
    items = []
    for domain, registry in _registries(runtime).items():
        records = registry.unresolved() if status == "unresolved" else registry.records()
        items.extend(record_view(domain, r) for r in records)
    items.sort(key=lambda r: r["started_at"])
    return {"status": status, "count": len(items), "executions": items}


@router.get("/executions/{execution_id}")
async def get_execution(execution_id: str, runtime=Depends(get_runtime)):
    domain, _, record = _find(runtime, execution_id)
    return record_view(domain, record)


@router.post("/executions/{execution_id}/reconcile")
async def reconcile_execution(
    execution_id: str,
    body: ReconcileBody | None = None,
    runtime=Depends(get_runtime),
):
    """
    Reconcile an UNKNOWN execution against authoritative warehouse state.

    409 if the record is not UNKNOWN; 503 if no reconciliation strategy / MCP
    read path is available.  A read failure is not an HTTP error: it is
    recorded as INDETERMINATE (the target stays blocked).
    """
    from maiw_api.config import settings
    from maiw_api.reconciliation import build_reconciliation_strategy
    from maiw_execution import ExecutionOutcome, ReconciliationService
    from maiw_mcp.deadline import RequestDeadline

    domain, registry, record = _find(runtime, execution_id)
    if record.outcome != ExecutionOutcome.UNKNOWN:
        raise HTTPException(
            status_code=409,
            detail=(
                f"execution_id={execution_id!r} has outcome="
                f"{record.outcome.value if record.outcome else None!r}; "
                "reconciliation applies to UNKNOWN executions only"
            ),
        )
    strategy = build_reconciliation_strategy(
        domain, getattr(runtime, "mcp_client", None)
    )
    if strategy is None:
        raise HTTPException(
            status_code=503,
            detail=f"No reconciliation read path available for domain={domain!r}",
        )
    trace_id = (body.trace_id if body else None) or (
        record.intent.trace_id if record.intent and record.intent.trace_id else None
    )
    trace_id = trace_id or str(uuid.uuid4())
    deadline = RequestDeadline.from_timeout(settings.reconciliation_timeout_seconds)
    reconciliation = await ReconciliationService().reconcile(
        record, strategy=strategy, trace_id=trace_id, deadline=deadline
    )
    registry.set_reconciliation(execution_id, reconciliation)
    logger.info(
        "executions: reconciled execution_id=%s domain=%s outcome=%s "
        "effective_status=%s",
        execution_id,
        domain,
        reconciliation.outcome.value,
        record.effective_status,
    )
    view = record_view(domain, record)
    view["reconciliation_outcome"] = reconciliation.outcome.value
    view["retried"] = False  # reconciliation never re-executes
    return view


__all__ = ["router", "record_view"]
