# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Procedures read-only router (v2.0.1, P1-03).

Operator/status visibility into the runtime's durable ProcedureStateStore.

    GET /api/v1/procedures                     — summaries of stored procedures
    GET /api/v1/procedures/{procedure_id}      — one procedure summary

Read-only: there is no POST/PUT/DELETE. Procedures are started and resumed
only by host-side code through ``MAIWRuntime.procedure_host``; governance
outcomes reach a procedure only through ``ProcedureHost.apply_governance``.
Summaries carry status, step position, revision and counts — never step
outputs, evidence payloads, prompts or model reasoning.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from maiw_api.procedure_host import summarize

router = APIRouter(prefix="/api/v1/procedures", tags=["procedures"])


def _host(request: Request):
    rt = getattr(request.app.state, "runtime", None)
    host = getattr(rt, "procedure_host", None) if rt is not None else None
    if host is None:
        raise HTTPException(
            status_code=503,
            detail="Procedure state store unavailable (see /api/v1/ready)",
        )
    return host


@router.get("")
async def list_procedures(request: Request) -> dict:
    host = _host(request)
    states = await host.list_procedures()
    summaries = [summarize(s) for s in states]
    counts: dict[str, int] = {}
    for s in summaries:
        counts[s["status"]] = counts.get(s["status"], 0) + 1
    return {"count": len(summaries), "by_status": counts, "procedures": summaries}


@router.get("/{procedure_id}")
async def get_procedure(procedure_id: str, request: Request) -> dict:
    host = _host(request)
    state = await host.load(procedure_id)
    if state is None:
        raise HTTPException(status_code=404, detail="procedure not found")
    return summarize(state)
