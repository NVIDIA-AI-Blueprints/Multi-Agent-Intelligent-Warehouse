# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Copilot API router — Phase 15C (ASK + ANALYZE; ACT gated to 15D).

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

from maiw_api.copilot import intent as intent_classifier
from maiw_api.copilot.models import (
    CopilotIntent,
    CopilotTurnRequest,
    CopilotTurnResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/copilot", tags=["copilot"])

_SAFETY_NOTE = "No warehouse changes have been made."


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

    Phase 15C: ASK and ANALYZE intents. ACT detected but not executed.

    The response for ASK/ANALYZE contains zero ActionProposals, zero
    DecisionEngine evaluations, and zero warehouse mutations.
    """
    svc = _get_copilot_service(request)

    # ── Classify intent ───────────────────────────────────────────────────────
    detected_intent = intent_classifier.classify(body.message)

    # ACT is gated — not implemented in 15C. Return safe refusal.
    if detected_intent == CopilotIntent.ACT:
        return CopilotTurnResponse(
            conversation_id=body.conversation_id or "none",
            turn_id="none",
            trace_id="none",
            intent="act",
            status="not_implemented",
            answer=(
                "Governed action handling is not yet available in this build. "
                "I can explain the situation (ASK) or recommend actions (ANALYZE), "
                "but executing warehouse operations requires Phase 15D."
            ),
            safety_note=_SAFETY_NOTE,
        )

    try:
        if detected_intent == CopilotIntent.ANALYZE:
            result, turn = await svc.analyze(
                message=body.message,
                conversation_id=body.conversation_id,
                warehouse_id=body.warehouse_id,
                scenario_name=body.scenario_name,
            )
            return _analyze_response(result, turn)

        else:
            # Default: ASK
            result, turn = await svc.ask(
                message=body.message,
                conversation_id=body.conversation_id,
                warehouse_id=body.warehouse_id,
                scenario_name=body.scenario_name,
            )
            return _ask_response(result, turn)

    except Exception as exc:
        logger.error("copilot_turn: unexpected error — %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _ask_response(result, turn) -> CopilotTurnResponse:
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
        skills_available=result.skills_available,
        model_id=result.model_id,
        reasoning_level=result.reasoning_level,
        routing_rule=result.routing_rule,
        routing_reason=result.routing_reason,
        requested_role=result.requested_role,
        selected_role=result.selected_role,
        fallback_from=result.fallback_from,
        fallback_reason=result.fallback_reason,
        latency_ms=result.latency_ms,
        degraded=result.degraded,
        degradation_reason=result.degradation_reason,
        answerability=result.answerability,
        missing_context=result.missing_context,
        timing=result.timing,
        related_artifacts={},
    )


def _analyze_response(result, turn) -> CopilotTurnResponse:
    return CopilotTurnResponse(
        conversation_id=turn.conversation_id,
        turn_id=turn.turn_id,
        trace_id=turn.trace_id,
        intent=turn.intent.value,
        status="degraded" if result.degraded else "complete",
        # ASK-style answer field carries the summary for ANALYZE too
        answer=result.summary,
        summary=result.summary,
        severity=result.severity,
        evidence=[
            {"label": e.label, "value": e.value, "severity": e.severity}
            for e in result.evidence
        ],
        recommendations=[
            {
                "recommendation_id": r.recommendation_id,
                "domain": r.domain,
                "capability": r.capability,
                "target": r.target,
                "objective": r.objective,
                "rationale": r.rationale,
                "priority": r.priority,
                "subtype": r.subtype,
                "focus_entity_id": r.focus_entity_id,
                "snapshot_id": r.snapshot_id,
                "trace_id": r.trace_id,
                "conversation_id": r.conversation_id,
                "turn_id": r.turn_id,
            }
            for r in result.recommendations
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
        skills_available=result.skills_available,
        model_id=result.model_id,
        reasoning_level=result.reasoning_level,
        routing_rule=result.routing_rule,
        routing_reason=result.routing_reason,
        requested_role=result.requested_role,
        selected_role=result.selected_role,
        fallback_from=result.fallback_from,
        fallback_reason=result.fallback_reason,
        latency_ms=result.latency_ms,
        degraded=result.degraded,
        degradation_reason=result.degradation_reason,
        answerability=result.answerability,
        missing_context=result.missing_context,
        timing=result.timing,
        focus_entity_id=result.focus_entity_id,
        focus_entity_label=result.focus_entity_label,
        safety_note=_SAFETY_NOTE,
        related_artifacts={},
    )
