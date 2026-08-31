# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Copilot API router — Phase 15B (ASK only).

Endpoint
--------
POST /api/v1/copilot/turn

Explicitly absent (trust boundary):
    /copilot/approve  — MUST NOT exist
    /copilot/execute  — MUST NOT exist
    /copilot/force-action — MUST NOT exist

These paths are validated by architecture invariant tests.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from maiw_api.copilot.models import (
    CopilotTurnRequest,
    CopilotTurnResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/copilot", tags=["copilot"])


def _get_copilot_service(request: Request):
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="MAIW runtime not available.")
    svc = getattr(runtime, "copilot_service", None)
    if svc is None:
        raise HTTPException(
            status_code=503,
            detail="Copilot service not available. Ensure MAIW_DEMO_MODE=true and the runtime is initialized.",
        )
    return svc


@router.post("/turn", response_model=CopilotTurnResponse)
async def copilot_turn(body: CopilotTurnRequest, request: Request):
    """
    Process one Copilot operator turn.

    Phase 15B: ASK intent only. ANALYZE and ACT will be enabled in 15C/15D.

    The response contains zero ActionProposals, zero DecisionEngine evaluations,
    and zero warehouse mutations for ASK turns.
    """
    svc = _get_copilot_service(request)

    try:
        result, turn = await svc.ask(
            message=body.message,
            conversation_id=body.conversation_id,
            warehouse_id=body.warehouse_id,
            scenario_name=body.scenario_name,
        )
    except Exception as exc:
        logger.error("copilot_turn: unexpected error — %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return CopilotTurnResponse(
        conversation_id=turn.conversation_id,
        turn_id=turn.turn_id,
        trace_id=turn.trace_id,
        intent=turn.intent.value,
        status="degraded" if result.degraded else "complete",
        answer=result.answer,
        evidence=[
            {"label": e.label, "value": e.value, "severity": e.severity}
            for e in result.evidence
        ],
        neighborhood={
            "focus_entity_id": result.neighborhood.focus_entity_id,
            "focus_entity_label": result.neighborhood.focus_entity_label,
            "entity_count": len(result.neighborhood.entity_ids),
            "relationship_summary": result.neighborhood.relationship_summary,
            "graph_available": result.neighborhood.graph_available,
        },
        agent=result.agent,
        skills_used=result.skills_used,
        model_id=result.model_id,
        reasoning_level=result.reasoning_level,
        routing_rule=result.routing_rule,
        routing_reason=result.routing_reason,
        latency_ms=result.latency_ms,
        degraded=result.degraded,
        degradation_reason=result.degradation_reason,
        related_artifacts={},
    )
