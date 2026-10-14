# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Demo API router — scenario control and SSE event stream.

All endpoints are prefixed /api/v1/demo and are only active when the
DemoScenarioController has been initialised (MAIW_DEMO_MODE=true).

Endpoints
---------
GET  /api/v1/demo/scenarios                — list available scenarios
POST /api/v1/demo/scenario/{name}/start    — load and activate a scenario
POST /api/v1/demo/scenario/pause           — freeze clock progression
POST /api/v1/demo/scenario/resume          — resume clock progression
POST /api/v1/demo/scenario/reset           — restore initial scenario state
POST /api/v1/demo/tick                     — advance clock N seconds
POST /api/v1/demo/inject                   — inject a fault/event
GET  /api/v1/demo/status                   — current simulation status
GET  /api/v1/events/stream                 — SSE live event stream
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from maiw_api.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["demo"])

# ── Dependency: controller ─────────────────────────────────────────────────────


def _get_controller():
    """Retrieve the demo controller; 503 if demo mode is not active."""
    try:
        from maiw_api.demo.controller import get_demo_controller

        return get_demo_controller()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Demo mode not active: {exc}",
        ) from exc


def _active_warehouse_id(ctrl: Any) -> str:
    """
    The warehouse the ACTIVE demo world represents — the single authoritative
    warehouse binding for the demo governance routes.

    /demo/analyze assembles state for it, every proposal it builds carries it
    in ``parameters.warehouse_id``, the approval record is bound to it, and
    /demo/approve re-reads state for it.  ``authorize_with_approval`` rejects a
    proposal whose warehouse differs from its approval's
    (``approval.warehouse_mismatch``), so all of them must agree.

    DataPack world → ``DC-47`` (the canonical DataPack warehouse); the YAML
    fallback world reports its own ``WAREHOUSE_ID``.
    """
    warehouse_id = getattr(getattr(ctrl, "world", None), "WAREHOUSE_ID", None)
    if not isinstance(warehouse_id, str) or not warehouse_id:
        raise HTTPException(
            status_code=503, detail="Active demo world has no warehouse id"
        )
    return warehouse_id


# ── Pydantic models ────────────────────────────────────────────────────────────


class TickRequest(BaseModel):
    seconds: int = Field(default=60, ge=1, le=86400, description="Seconds to advance")


class InjectRequest(BaseModel):
    event_type: str = Field(
        ...,
        description=(
            "equipment_fault | equipment_restore | low_stock | "
            "worker_absence | worker_return | task_deadline | wave_delay"
        ),
    )
    payload: dict[str, Any] = Field(default_factory=dict)


# ── Scenario listing ──────────────────────────────────────────────────────────


@router.get("/demo/scenarios")
async def list_scenarios():
    """List all available scenario definitions."""
    ctrl = _get_controller()
    return {"scenarios": ctrl.list_scenarios()}


# ── Lifecycle ─────────────────────────────────────────────────────────────────


@router.post("/demo/scenario/{name}/start")
async def start_scenario(name: str):
    """Load and activate a named scenario.  Replaces any active scenario."""
    ctrl = _get_controller()
    try:
        await ctrl.start(name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"ok": True, "scenario": name, "status": ctrl.status()}


@router.post("/demo/scenario/pause")
async def pause_scenario():
    """Pause the active scenario (freeze clock + timed event processing)."""
    ctrl = _get_controller()
    try:
        await ctrl.pause()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "paused": True}


@router.post("/demo/scenario/resume")
async def resume_scenario():
    """Resume a paused scenario."""
    ctrl = _get_controller()
    try:
        await ctrl.resume()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "paused": False}


@router.post("/demo/scenario/reset")
async def reset_scenario():
    """Restore the scenario to its initial seeded state."""
    ctrl = _get_controller()
    try:
        await ctrl.reset()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "scenario": ctrl.scenario_name, "status": ctrl.status()}


# ── Clock control ─────────────────────────────────────────────────────────────


@router.post("/demo/tick")
async def tick(request: TickRequest):
    """Advance the simulation clock and fire any due timed events."""
    ctrl = _get_controller()
    try:
        await ctrl.tick(request.seconds)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "ok": True,
        "ticked_seconds": request.seconds,
        "clock_iso": ctrl.world.clock.now().isoformat(),
        "elapsed_seconds": ctrl.world.clock.elapsed_seconds,
    }


# ── Fault injection ───────────────────────────────────────────────────────────


@router.post("/demo/inject")
async def inject_event(request: InjectRequest):
    """
    Inject a fault or scenario event into the running simulation.

    Examples
    --------
    Equipment fault (target resolved from the active world; see
    ``DemoScenarioController.resolve_equipment_target``):
        {"event_type": "equipment_fault", "payload": {"fault_code": "E_MOTOR_OVERTEMP"}}

    Equipment fault on an explicit asset of the active world:
        {"event_type": "equipment_fault", "payload": {"asset_id": "agv-000"}}

    Equipment targeting errors (typed body ``{"error", "code", "message", ...}``):
        404 ASSET_NOT_IN_ACTIVE_WORLD — explicit asset_id not in the active world
        409 NO_ELIGIBLE_ASSET         — asset_id omitted and nothing is eligible

    Low stock:
        {"event_type": "low_stock", "payload": {"sku": "SKU-1001", "quantity_available": 50}}

    Worker absence:
        {"event_type": "worker_absence", "payload": {"worker_id": "w-002"}}
    """
    from maiw_api.demo.controller import InjectTargetError
    from maiw_api.write_auth import TypedHTTPError

    ctrl = _get_controller()
    try:
        result = await ctrl.inject(request.event_type, request.payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except InjectTargetError as exc:
        raise TypedHTTPError(
            exc.status_code, exc.code, exc.message, **exc.extra
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "event_type": request.event_type, "result": result}


# ── Status ────────────────────────────────────────────────────────────────────


@router.get("/demo/status")
async def demo_status():
    """Return current simulation status: active scenario, clock, world summary."""
    ctrl = _get_controller()
    return ctrl.status()


# ── Typed failure → HTTP mapping ─────────────────────────────────────────────


def _raise_typed_http(exc: BaseException, context: str) -> None:
    """
    Map typed runtime failures to the correct HTTP status code.

    RequestDeadlineExceeded → 504 (deadline exhausted at ingress)
    ModelTimeout            → 504 (NIM did not respond in time)
    MCPTimeout              → 504 (MCP server did not respond in time)
    ModelUnavailable        → 503 (no enabled model can serve the request)
    MCPUnavailable          → 503 (transport-level MCP failure)

    ExecutionOutcome.UNKNOWN is NOT raised as an exception — callers preserve it
    as a structured operational outcome in the response body (never 500/504).
    """
    from maiw_mcp.deadline import RequestDeadlineExceeded  # noqa: PLC0415
    from maiw_mcp.errors import MCPTimeout, MCPUnavailable  # noqa: PLC0415
    from maiw_models.errors import ModelTimeout, ModelUnavailable  # noqa: PLC0415

    if isinstance(exc, RequestDeadlineExceeded):
        raise HTTPException(
            status_code=504,
            detail={
                "error": "REQUEST DEADLINE",
                "message": f"{context}: request deadline exceeded",
                "expired_by_ms": exc.expired_by_ms,
            },
        ) from exc
    if isinstance(exc, ModelTimeout):
        raise HTTPException(
            status_code=504,
            detail={
                "error": "MODEL TIMEOUT",
                "message": f"{context}: NIM model did not respond in time",
                "model_id": exc.model_id,
            },
        ) from exc
    if isinstance(exc, MCPTimeout):
        raise HTTPException(
            status_code=504,
            detail={
                "error": "CAPABILITY TIMEOUT",
                "message": f"{context}: MCP capability did not respond in time",
            },
        ) from exc
    if isinstance(exc, ModelUnavailable):
        raise HTTPException(
            status_code=503,
            detail={
                "error": "MODEL UNAVAILABLE",
                "message": f"{context}: no enabled model can serve the request",
                "model_id": exc.model_id,
            },
        ) from exc
    if isinstance(exc, MCPUnavailable):
        raise HTTPException(
            status_code=503,
            detail={
                "error": "MCP UNAVAILABLE",
                "message": f"{context}: MCP transport failure",
            },
        ) from exc


# ── MAIW Analysis ─────────────────────────────────────────────────────────────


@router.post("/demo/analyze")
async def analyze_disruption():
    """
    Run the MAIW Analysis workflow against the active scenario.

    Flow
    ----
    1. Assemble full 4-domain WarehouseStateSnapshot via state_provider.
    2. Call OperationsCoordinationAgent.analyze_disruption() → OperationalAssessment.
    3. For each RecommendedAction (ordered, sequential):
       a. Build ActionProposal via canonical proposal skill.
       b. Evaluate with DecisionEngine.
       c. If APPROVED, execute via domain ActionExecutor (fresh execution deadline).
    4. Refresh state post-execution.
    5. Return full lifecycle record + assessment.

    SSE lifecycle events are published at each phase:
        OBSERVE → REASON → SKILL / PROPOSE → DECIDE → EXECUTE → OBSERVE_OUTCOME

    Typed failure mapping (Phase 10E Checkpoint D):
        RequestDeadlineExceeded → 504
        ModelTimeout            → 504
        MCPTimeout              → 504
        ModelUnavailable        → 503
        MCPUnavailable          → 503
        ExecutionOutcome.UNKNOWN → preserved as structured body (never 500/504)
    """
    import time as _time
    from datetime import datetime, timezone
    from maiw_api.demo.kpi import DemoKPIEngine
    from maiw_mcp.deadline import RequestDeadline

    analyze_wall_start = _time.perf_counter()
    pre_kpis_dict: dict = {}
    post_kpis_dict: dict = {}

    ctrl = _get_controller()
    bus = ctrl.bus

    try:
        from maiw_api.bootstrap import get_runtime

        runtime = await get_runtime()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Runtime unavailable: {exc}"
        ) from exc

    if runtime.state_provider is None:
        raise HTTPException(
            status_code=503, detail="WarehouseStateProvider not initialized"
        )
    if runtime.operations_agent is None:
        raise HTTPException(
            status_code=503, detail="OperationsCoordinationAgent not initialized"
        )
    if runtime.decision_engine is None:
        raise HTTPException(status_code=503, detail="DecisionEngine not initialized")
    if not ctrl.active:
        raise HTTPException(
            status_code=409, detail="No active scenario — start a scenario first"
        )

    # Originate the analyze deadline at request ingress (after pre-flight checks).
    analyze_deadline = RequestDeadline.from_timeout(settings.analyze_timeout_seconds)

    # Capture pre-analysis KPIs
    pre_kpi = DemoKPIEngine(ctrl.world, ctrl._last_analyze_wall_time).compute()
    pre_kpis_dict = pre_kpi.to_dict()
    # Record that analyze is starting
    ctrl._last_analyze_wall_time = datetime.now(tz=timezone.utc)

    trace_id = str(uuid.uuid4())
    scenario_context = (
        f"{ctrl.scenario_name} scenario active" if ctrl.scenario_name else ""
    )
    lifecycle: list[dict[str, Any]] = []

    # ── OBSERVE: assemble 4-domain state ──────────────────────────────────────
    await bus.publish_observe(
        "Assembling warehouse state snapshot",
        f"scenario={ctrl.scenario_name or 'none'}",
        trace_id=trace_id,
        sim_time_seconds=ctrl.world.clock.elapsed_seconds,
    )
    lifecycle.append(
        {"phase": "OBSERVE", "message": "State assembly started", "trace_id": trace_id}
    )

    try:
        from maiw_state import StateRequirements, WarehouseStateSnapshot

        requirements = StateRequirements(equipment=True, labor=True, waves=True)
        warehouse_id = _active_warehouse_id(ctrl)
        state = await runtime.state_provider.get_state(
            warehouse_id,
            requirements,
            trace_id=trace_id,
            deadline=analyze_deadline,
        )
        snapshot = WarehouseStateSnapshot.seal(state)
    except Exception as exc:
        await bus.publish_observe("State assembly failed", str(exc), trace_id=trace_id)
        _raise_typed_http(exc, "state assembly")
        raise HTTPException(
            status_code=500, detail=f"State assembly failed: {exc}"
        ) from exc

    lifecycle.append(
        {
            "phase": "OBSERVE",
            "snapshot_id": snapshot.snapshot_id,
            "warehouse_id": snapshot.warehouse_id,
            "equipment_total": state.equipment.total_count if state.equipment else 0,
            "labor_total": state.labor.total_workers if state.labor else 0,
            "wave_tasks": state.waves.total_tasks if state.waves else 0,
            "trace_id": trace_id,
        }
    )
    await bus.publish_observe(
        f"Snapshot sealed — {state.equipment.total_count if state.equipment else 0} assets, "
        f"{state.labor.total_workers if state.labor else 0} workers",
        f"snapshot={snapshot.snapshot_id[:8]}",
        trace_id=trace_id,
        sim_time_seconds=ctrl.world.clock.elapsed_seconds,
    )

    # ── REASON: agent analyzes snapshot ──────────────────────────────────────
    await bus.publish_reason(
        "pending",
        "routing",
        "Invoking OperationsCoordinationAgent.analyze_disruption()",
        trace_id=trace_id,
        sim_time_seconds=ctrl.world.clock.elapsed_seconds,
    )
    lifecycle.append(
        {
            "phase": "REASON",
            "message": "ModelGateway call started",
            "trace_id": trace_id,
        }
    )

    try:
        assessment = await runtime.operations_agent.analyze_disruption(
            snapshot=snapshot,
            scenario_context=scenario_context,
            trace_id=trace_id,
            deadline=analyze_deadline,
        )
    except Exception as exc:
        _raise_typed_http(exc, "agent analysis")
        raise HTTPException(
            status_code=500, detail=f"Agent analysis failed: {exc}"
        ) from exc

    lifecycle.append(
        {
            "phase": "REASON",
            "summary": assessment.summary,
            "severity": assessment.severity,
            "model_id": assessment.model_id,
            "routing_rule": assessment.routing_rule,
            "routing_reason": assessment.routing_reason,
            "latency_ms": assessment.latency_ms,
            "recommendations_count": len(assessment.recommendations),
            "trace_id": trace_id,
        }
    )
    await bus.publish_reason(
        assessment.model_id,
        assessment.routing_rule,
        assessment.summary,
        trace_id=trace_id,
        sim_time_seconds=ctrl.world.clock.elapsed_seconds,
    )

    # ── SKILL / PROPOSE / DECIDE / EXECUTE for each recommendation ────────────
    proposal_results: list[dict[str, Any]] = []

    for i, rec in enumerate(assessment.recommendations):
        label = f"rec[{i}] {rec.capability} → {rec.target}"

        # SKILL event
        await bus.publish_skill(rec.capability, rec.target, trace_id=trace_id)
        lifecycle.append(
            {
                "phase": "SKILL",
                "index": i,
                "capability": rec.capability,
                "target": rec.target,
                "domain": rec.domain,
                "priority": rec.priority,
                "objective": rec.objective,
                "trace_id": trace_id,
            }
        )

        # Build proposal via canonical proposal skill
        proposal_result = await _build_and_execute_proposal(
            rec=rec,
            snapshot=snapshot,
            runtime=runtime,
            trace_id=trace_id,
            bus=bus,
            lifecycle=lifecycle,
            index=i,
            ctrl=ctrl,
            execution_timeout_seconds=settings.execution_timeout_seconds,
            warehouse_id=warehouse_id,
        )
        proposal_results.append(proposal_result)

        # Stop if we hit an error that should abort further processing
        if proposal_result.get("status") == "error":
            logger.warning(
                "analyze_disruption: aborting at rec[%d] due to build error", i
            )
            break

    # Track time to decision (after DECIDE phase completes, before EXECUTE)
    decide_wall_elapsed = _time.perf_counter() - analyze_wall_start

    # ── OBSERVE_OUTCOME: refresh state ────────────────────────────────────────
    await bus.publish_observe_outcome(
        "Refreshing warehouse state post-execution",
        trace_id=trace_id,
        sim_time_seconds=ctrl.world.clock.elapsed_seconds,
    )
    try:
        post_state = await runtime.state_provider.get_state(
            snapshot.warehouse_id,
            StateRequirements(equipment=True, labor=True, waves=True),
            trace_id=trace_id,
        )
        outcome_summary = (
            f"{post_state.equipment.available_count if post_state.equipment else '?'} assets available, "
            f"{post_state.labor.available_workers if post_state.labor else '?'} workers available"
        )
    except Exception as exc:
        outcome_summary = f"State refresh failed: {exc}"

    lifecycle.append(
        {"phase": "OBSERVE_OUTCOME", "summary": outcome_summary, "trace_id": trace_id}
    )
    await bus.publish_observe_outcome(
        outcome_summary,
        trace_id=trace_id,
        sim_time_seconds=ctrl.world.clock.elapsed_seconds,
    )

    execute_wall_elapsed = _time.perf_counter() - analyze_wall_start

    # Post-execution KPIs
    post_kpi = DemoKPIEngine(ctrl.world, ctrl._last_analyze_wall_time).compute()
    post_kpis_dict = post_kpi.to_dict()

    # Append to KPI history
    ctrl._kpi_history.append(post_kpis_dict)
    if len(ctrl._kpi_history) > ctrl._MAX_KPI_HISTORY:
        ctrl._kpi_history = ctrl._kpi_history[-ctrl._MAX_KPI_HISTORY :]

    # Publish KPI SSE event
    await ctrl.bus.publish_kpi(post_kpis_dict, ctrl.world.clock.elapsed_seconds)

    # Timing metrics
    time_to_detect_ms: float | None = None
    if ctrl._last_inject_wall_time is not None:
        inject_to_analyze_secs = (
            ctrl._last_analyze_wall_time - ctrl._last_inject_wall_time
        ).total_seconds()
        time_to_detect_ms = round(inject_to_analyze_secs * 1000, 1)

    time_to_decision_ms = round(decide_wall_elapsed * 1000, 1)
    time_to_execution_ms = round((execute_wall_elapsed - decide_wall_elapsed) * 1000, 1)

    return {
        "ok": True,
        "trace_id": trace_id,
        "assessment": {
            "snapshot_id": assessment.snapshot_id,
            "warehouse_id": assessment.warehouse_id,
            "assessed_at": assessment.assessed_at.isoformat(),
            "summary": assessment.summary,
            "severity": assessment.severity,
            "domains_affected": assessment.domains_affected,
            "facts_observed": assessment.facts_observed,
            "recommendations": [r.model_dump() for r in assessment.recommendations],
            "model_id": assessment.model_id,
            "routing_rule": assessment.routing_rule,
            "routing_reason": assessment.routing_reason,
            "latency_ms": assessment.latency_ms,
        },
        "proposal_results": proposal_results,
        "lifecycle": lifecycle,
        "pre_kpis": pre_kpis_dict,
        "post_kpis": post_kpis_dict,
        "kpi_delta": pre_kpi.delta_to(post_kpi),
        "timing": {
            "time_to_detect_ms": time_to_detect_ms,
            "time_to_decision_ms": time_to_decision_ms,
            "time_to_execution_ms": time_to_execution_ms,
        },
    }


async def _build_and_execute_proposal(
    *,
    rec: Any,
    snapshot: Any,
    runtime: Any,
    trace_id: str,
    bus: Any,
    lifecycle: list,
    index: int,
    ctrl: Any,
    execution_timeout_seconds: float = 30.0,
    warehouse_id: str | None = None,
) -> dict[str, Any]:
    """
    Translate one RecommendedAction into a proposal + decision + optional execution.

    ``warehouse_id`` is the active world's warehouse (see
    ``_active_warehouse_id``); the proposal and, when human approval is
    required, the approval record are both bound to it.  Defaults to the
    snapshot's warehouse, which analyze assembled for that same id.
    """
    from maiw_decision.models import DecisionOutcome, DecisionRequest

    if warehouse_id is None:
        warehouse_id = snapshot.warehouse_id

    # Select proposal skill based on capability
    try:
        proposal = await _build_proposal(
            rec, trace_id, runtime, warehouse_id=warehouse_id
        )
    except Exception as exc:
        lifecycle.append(
            {
                "phase": "PROPOSE",
                "index": index,
                "status": "error",
                "capability": rec.capability,
                "reason": str(exc),
                "trace_id": trace_id,
            }
        )
        return {"status": "error", "capability": rec.capability, "reason": str(exc)}

    # PROPOSE event
    await bus.publish_propose(proposal.action, proposal.proposal_id, trace_id=trace_id)
    lifecycle.append(
        {
            "phase": "PROPOSE",
            "index": index,
            "action": proposal.action,
            "proposal_id": proposal.proposal_id,
            "risk_level": (
                proposal.risk_level.value
                if hasattr(proposal.risk_level, "value")
                else str(proposal.risk_level)
            ),
            "trace_id": trace_id,
        }
    )

    # DECIDE
    decision_request = DecisionRequest(
        proposal=proposal,
        state=snapshot,
        requested_by="operations-agent",
        trace_id=trace_id,
    )
    result, _audit = runtime.decision_engine.evaluate(decision_request)
    result.trace_id = trace_id

    await bus.publish_decide(
        result.outcome.value, proposal.proposal_id, result.result_id, trace_id=trace_id
    )
    lifecycle.append(
        {
            "phase": "DECIDE",
            "index": index,
            "outcome": result.outcome.value,
            "proposal_id": proposal.proposal_id,
            "decision_id": result.result_id,
            "violations": [v.model_dump() for v in result.violations],
            "trace_id": trace_id,
        }
    )

    if result.outcome != DecisionOutcome.APPROVED:
        # Store in pending approvals if human approval is needed
        if result.outcome == DecisionOutcome.REQUIRES_HUMAN_APPROVAL:
            # Same warehouse the proposal was built for — never a fallback
            # literal (approval.warehouse_mismatch would block /demo/approve).
            ctrl.add_pending_approval(
                proposal_id=proposal.proposal_id,
                decision_id=result.result_id,
                trace_id=trace_id,
                capability=rec.capability,
                target=str(rec.target),
                domain=str(rec.domain),
                priority=str(rec.priority),
                objective=str(rec.objective),
                rationale=str(rec.rationale) if hasattr(rec, "rationale") else "",
                risk_level=(
                    proposal.risk_level.value
                    if hasattr(proposal.risk_level, "value")
                    else str(proposal.risk_level)
                ),
                warehouse_id=warehouse_id,
                proposal_data=proposal.model_dump(mode="json"),
            )
        return {
            "status": result.outcome.value,
            "capability": rec.capability,
            "proposal_id": proposal.proposal_id,
            "decision_id": result.result_id,
            "violations": [v.model_dump() for v in result.violations],
        }

    # EXECUTE
    executor = _get_executor(rec.domain, runtime)
    if executor is None:
        lifecycle.append(
            {
                "phase": "EXECUTE",
                "index": index,
                "status": "no_executor",
                "capability": rec.capability,
                "trace_id": trace_id,
            }
        )
        return {
            "status": "approved_no_executor",
            "capability": rec.capability,
            "proposal_id": proposal.proposal_id,
            "decision_id": result.result_id,
        }

    # Fresh execution deadline — independent budget from the analyze deadline.
    from maiw_mcp.deadline import RequestDeadline as _RequestDeadline  # noqa: PLC0415

    exec_deadline = _RequestDeadline.from_timeout(execution_timeout_seconds)

    try:
        exec_result = await executor.execute(proposal, result, deadline=exec_deadline)
        exec_result.trace_id = trace_id

        # Preserve ExecutionOutcome.UNKNOWN as a structured operational outcome —
        # never convert it to a generic 500/504.  The caller can reconcile it.
        from maiw_execution.outcome import ExecutionOutcome as _EO  # noqa: PLC0415

        outcome_label = _outcome_label(exec_result)
        lifecycle.append(
            {
                "phase": "EXECUTE",
                "index": index,
                "status": outcome_label,
                "action": exec_result.action,
                "execution_id": exec_result.execution_id,
                "success": exec_result.success,
                "trace_id": trace_id,
            }
        )
        unknown = outcome_label == _EO.UNKNOWN.value
        if unknown and _error_code(exec_result) not in _BLOCKED_ERROR_CODES:
            await _publish_reconciliation_required(
                ctrl,
                execution_id=exec_result.execution_id,
                domain=str(rec.domain),
                capability=rec.capability,
                target=_proposal_target(proposal, rec),
                proposal_id=proposal.proposal_id,
                decision_id=result.result_id,
                approval_id=None,
                trace_id=trace_id,
                error_code=_error_code(exec_result),
            )
        return {
            "status": outcome_label,
            "capability": rec.capability,
            "proposal_id": proposal.proposal_id,
            "decision_id": result.result_id,
            "execution_id": exec_result.execution_id,
            "success": exec_result.success,
            "outcome": outcome_label,
            # Never report an ambiguous write as executed or as not executed.
            "executed": None if unknown else bool(exec_result.executed),
            "reconciliation_required": unknown,
        }
    except Exception as exc:
        lifecycle.append(
            {
                "phase": "EXECUTE",
                "index": index,
                "status": "execution_error",
                "capability": rec.capability,
                "reason": str(exc),
                "trace_id": trace_id,
            }
        )
        return {
            "status": "execution_error",
            "capability": rec.capability,
            "proposal_id": proposal.proposal_id,
            "decision_id": result.result_id,
            "reason": str(exc),
        }


_WAVE_TASK_TYPES = frozenset({"PICK", "PACK", "SHIP", "RECEIVE", "PUTAWAY", "TRANSFER"})


def _resolve_labor_allocation_target(rec: Any) -> tuple[str, list[str]]:
    """
    Resolve a semantic labor target to a concrete (task_id, [worker_id]) pair.

    The MAIW agent recommends at the semantic level ("wave_pending_tasks", "zone_A").
    In production a task planner would supply concrete IDs. In the demo we ground
    the recommendation against the current world state: pick the highest-priority
    pending wave task and the first available worker, matched by zone when possible.

    Raises ValueError when no valid (task, worker) pair can be found — this causes
    _build_proposal to fail loudly rather than silently queuing a phantom proposal
    that would execute as a no-op and return success=True with no warehouse mutation.
    """
    from maiw_api.demo.controller import get_demo_controller as _get_ctrl

    ctrl = _get_ctrl()
    world = ctrl.world

    pending = sorted(
        [
            t
            for t in world.tasks.values()
            if t.status == "pending" and t.task_type in _WAVE_TASK_TYPES
        ],
        key=lambda t: (
            0 if t.priority == "high" else 1 if t.priority == "medium" else 2,
            t.deadline or "9999",
            t.task_id,
        ),
    )
    available = [
        w
        for w in world.workers.values()
        if w.status == "active" and w.current_task_id is None
    ]
    logger.debug(
        "_resolve_labor_allocation_target: pending=%d available=%d",
        len(pending),
        len(available),
    )

    if not pending:
        raise ValueError("CAPACITY_UNAVAILABLE: no pending wave tasks to allocate")
    if not available:
        raise ValueError(
            f"CAPACITY_UNAVAILABLE: no idle workers available "
            f"({sum(1 for w in world.workers.values() if w.status == 'active')} active workers all occupied)"
        )

    task = pending[0]
    same_zone = [w for w in available if w.zone == task.zone]
    worker = same_zone[0] if same_zone else available[0]
    return task.task_id, [worker.worker_id]


async def _build_proposal(
    rec: Any, trace_id: str, runtime: Any, *, warehouse_id: str
) -> Any:
    """
    Translate a RecommendedAction into an ActionProposal using the correct skill.

    Every proposal is bound to ``warehouse_id`` (the active world's warehouse —
    the one its approval record is bound to).
    """
    cap = rec.capability

    if cap == "warehouse.equipment.assign":
        from maiw_skills.equipment.skills import (
            EquipmentAssignmentSkill,
            EquipmentAssignmentRequest,
        )

        skill = EquipmentAssignmentSkill()
        req = EquipmentAssignmentRequest(
            asset_id=rec.target,
            assignee="operations-agent",
            assignment_type=rec.subtype or "task",
            reason=rec.rationale,
            requested_by="operations-agent",
        )
        return await skill.execute(req, trace_id=trace_id, warehouse_id=warehouse_id)

    if cap == "warehouse.equipment.release":
        from maiw_decision.proposal import ActionProposal

        return ActionProposal.for_equipment_release(
            asset_id=rec.target,
            released_by="operations-agent",
            reason=rec.rationale,
            requested_by="operations-agent",
            warehouse_id=warehouse_id,
            trace_id=trace_id,
        )

    if cap == "warehouse.equipment.schedule_maintenance":
        from maiw_decision.proposal import ActionProposal

        return ActionProposal.for_schedule_maintenance(
            asset_id=rec.target,
            maintenance_type=rec.subtype or "unscheduled",
            description=rec.objective,
            scheduled_by="operations-agent",
            priority=rec.priority,
            reason=rec.rationale,
            requested_by="operations-agent",
            warehouse_id=warehouse_id,
            trace_id=trace_id,
        )

    if cap == "warehouse.labor.allocate":
        from maiw_skills.labor.skills import ProposeLaborAllocationSkill

        # Resolve semantic targets (e.g. "wave_pending_tasks", "zone_A") to real IDs.
        # The agent recommends at the semantic level; the demo router grounds it in
        # the current world state. Production would receive grounded IDs from a planner.
        task_id, worker_ids = _resolve_labor_allocation_target(rec)
        skill = ProposeLaborAllocationSkill()
        return await skill.execute(
            task_id=task_id,
            task_type=rec.subtype or "pick",
            worker_ids=worker_ids,
            priority=rec.priority,
            reason=rec.rationale,
            requested_by="operations-agent",
            warehouse_id=warehouse_id,
            trace_id=trace_id,
        )

    if cap == "warehouse.wave.reprioritize":
        from maiw_skills.wave.skills import ProposeWaveReprioritizationSkill

        skill = ProposeWaveReprioritizationSkill()
        return await skill.execute(
            zone=(
                rec.target
                if rec.target.startswith("zone") or len(rec.target) <= 3
                else None
            ),
            wave_id=(
                rec.target
                if not (rec.target.startswith("zone") or len(rec.target) <= 3)
                else None
            ),
            new_priority=rec.priority,
            reason=rec.rationale,
            requested_by="operations-agent",
            warehouse_id=warehouse_id,
            trace_id=trace_id,
        )

    raise ValueError(f"Unknown capability: {cap!r}")


def _get_executor(domain: str, runtime: Any) -> Any:
    """Return the domain executor, or None if not wired."""
    if domain == "equipment":
        return runtime.equipment_executor
    if domain == "labor":
        return runtime.labor_executor
    if domain == "wave":
        return runtime.wave_executor
    return None


# ── Execution outcome reporting ──────────────────────────────────────────────
#
# The demo governance routes report execution outcomes exactly like the
# canonical write routes (routers/equipment.py ``_execute_if_approved``):
#
#   status/outcome  the canonical ExecutionOutcome value
#                   executed | no_op | deferred | conflict | unknown | failed
#   executed        true / false — or null when the outcome is UNKNOWN (the
#                   write may have landed; never reported as executed NOR as
#                   not executed)
#   reconciliation_required  true only for UNKNOWN; the operator reconciles
#                   (POST /api/v1/demo/reconcile) — nothing is retried
#
# A write refused because an earlier write to the same target is still
# unresolved (executor error_code RECONCILIATION_REQUIRED / DUPLICATE_IN_FLIGHT)
# is answered 409 RECONCILIATION_REQUIRED — nothing was dispatched.

# Executor error codes meaning "refused before any write: the target has an
# unresolved (UNKNOWN / in-flight) execution".  The UNKNOWN they carry is the
# EARLIER execution's, not a new ambiguous write.
_BLOCKED_ERROR_CODES = frozenset({"RECONCILIATION_REQUIRED", "DUPLICATE_IN_FLIGHT"})

_DEMO_RECONCILE_PATH = "/api/v1/demo/reconcile"

# ReconciliationOutcome value → SSE category the Reliability UI listens for.
_RECONCILIATION_EVENT_CATEGORY = {
    "confirmed_executed": "CONFIRMED_EXECUTED",
    "confirmed_not_executed": "CONFIRMED_NOT_EXECUTED",
    "indeterminate": "INDETERMINATE",
}


def _outcome_label(exec_result: Any) -> str:
    outcome = getattr(exec_result, "outcome", None)
    value = getattr(outcome, "value", outcome)
    if isinstance(value, str) and value:
        return value
    return "executed" if getattr(exec_result, "success", False) else "failed"


def _error_code(exec_result: Any) -> str | None:
    code = getattr(exec_result, "error_code", None)
    return code if isinstance(code, str) and code else None


def _proposal_target(proposal: Any, rec_or_pending: Any = None) -> str | None:
    """The domain target of a proposal (asset_id / task_id / zone / wave_id)."""
    params = getattr(proposal, "parameters", None)
    if isinstance(params, dict):
        for key in ("asset_id", "task_id", "zone", "wave_id"):
            value = params.get(key)
            if isinstance(value, str) and value:
                return value
    if isinstance(rec_or_pending, dict):
        target = rec_or_pending.get("target")
    else:
        target = getattr(rec_or_pending, "target", None)
    return target if isinstance(target, str) and target else None


def _reconcile_hint(execution_id: str, domain: str) -> dict[str, Any]:
    return {
        "method": "POST",
        "path": _DEMO_RECONCILE_PATH,
        "body": {"execution_id": execution_id, "domain": domain},
    }


async def _publish_reconciliation_required(
    ctrl: Any,
    *,
    execution_id: str,
    domain: str,
    capability: str,
    target: str | None,
    proposal_id: str | None,
    decision_id: str | None,
    approval_id: str | None,
    trace_id: str | None,
    error_code: str | None,
) -> bool:
    """
    Publish RECONCILIATION_REQUIRED for an UNKNOWN execution — exactly once
    per execution_id.  Returns True when the event was published.

    The Reliability panel enables RECONCILE NOW from this event: it reads
    ``execution_id`` / ``domain`` from the top-level SSE fields and from the
    JSON ``detail``.  Publishing never changes the reported outcome — a bus
    failure is logged, not raised.
    """
    from maiw_api.demo.events import ScenarioEvent

    try:
        if ctrl.claim_reconciliation_required(execution_id) is not True:
            return False
        detail = {
            "execution_id": execution_id,
            "domain": domain,
            "capability": capability,
            "target": target,
            "proposal_id": proposal_id,
            "decision_id": decision_id,
            "approval_id": approval_id,
            "trace_id": trace_id,
            "outcome": "unknown",
            "executed": None,
            "error_code": error_code,
            "retried": False,
            "reconcile": _reconcile_hint(execution_id, domain),
        }
        await ctrl.bus.publish(
            ScenarioEvent(
                category="RECONCILIATION_REQUIRED",
                message=f"reconciliation_required:{capability}",
                detail=json.dumps(detail, sort_keys=True),
                asset_id=target if domain == "equipment" else None,
                task_id=target if domain == "labor" else None,
                sim_time_seconds=ctrl.world.clock.elapsed_seconds,
                execution_id=execution_id,
                domain=domain,
            )
        )
        return True
    except Exception as exc:  # noqa: BLE001 — observability must not mask outcome
        logger.warning(
            "RECONCILIATION_REQUIRED publish failed for execution_id=%s: %s",
            execution_id,
            exc,
        )
        return False


# ── Approval governance ───────────────────────────────────────────────────────


class ApproveRequest(BaseModel):
    pending_id: str
    approved_by: str = "operator"


@router.post("/demo/approve")
async def approve_proposal(request: ApproveRequest):
    """
    Approve a pending proposal and execute it through the canonical pipeline.

    Phase 10E Batch 2:
    - Deserializes the original ActionProposal (same proposal_id, audit chain intact).
    - Transitions the pre-created ApprovalRecord from PENDING → APPROVED via store.
    - Consumes the approval after successful execution (APPROVED → CONSUMED).
    - No post-construction trace injection.
    """
    from maiw_decision.models import DecisionOutcome, DecisionRequest
    from maiw_decision.approval import ApprovalAlreadyDecided, ApprovalExpired, ApprovalNotFound
    from maiw_decision.proposal import ActionProposal
    from maiw_api.demo.events import ScenarioEvent

    ctrl = _get_controller()

    pending = ctrl.remove_pending_approval(request.pending_id)
    if pending is None:
        raise HTTPException(
            status_code=404,
            detail=f"No pending approval for pending_id={request.pending_id}",
        )

    bus = ctrl.bus
    try:
        from maiw_api.bootstrap import get_runtime

        runtime = await get_runtime()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Runtime unavailable: {exc}"
        ) from exc

    trace_id = pending["trace_id"]
    sim_t = ctrl.world.clock.elapsed_seconds
    approval_id = pending["approval_id"]

    # Transition ApprovalRecord PENDING → APPROVED via store (single-use guarantee begins here)
    try:
        approval = ctrl.approval_store.approve(
            approval_id, approved_by=request.approved_by
        )
    except ApprovalExpired as exc:
        ctrl.record_approval_outcome(request.pending_id, "expired")
        raise HTTPException(
            status_code=410,
            detail=f"Approval expired — the TTL elapsed before the operator acted: {exc}",
        ) from exc
    except ApprovalAlreadyDecided as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ApprovalNotFound:
        raise HTTPException(
            status_code=404,
            detail=f"Approval record not found: approval_id={approval_id}",
        )

    # Restore the original ActionProposal (fixes audit chain — same proposal_id throughout)
    proposal_data = pending.get("proposal_data")
    if proposal_data is None:
        raise HTTPException(
            status_code=500,
            detail="Pending record missing proposal_data (pre-Batch2 record?)",
        )
    try:
        proposal = ActionProposal.model_validate(proposal_data)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to restore proposal: {exc}"
        ) from exc

    # Fetch fresh state snapshot
    from maiw_state.requirements import StateRequirements
    from maiw_state import WarehouseStateSnapshot

    try:
        fresh_state = await runtime.state_provider.get_state(
            _active_warehouse_id(ctrl),
            StateRequirements(equipment=True, labor=True, waves=True),
            trace_id=trace_id,
        )
        fresh_snapshot = WarehouseStateSnapshot.seal(fresh_state)
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"State unavailable: {exc}"
        ) from exc

    # Authorize with approval evidence (decision_id binding enforced)
    decision_request = DecisionRequest(
        proposal=proposal,
        state=fresh_snapshot,
        requested_by=request.approved_by,
        trace_id=trace_id,
    )
    auth_result, _audit = runtime.decision_engine.authorize_with_approval(
        decision_request,
        approval,
        expected_decision_id=pending["decision_id"],
    )

    # Publish APPROVE SSE event
    await bus.publish_approve(
        pending["capability"],
        proposal.proposal_id,
        request.approved_by,
        trace_id=trace_id,
        sim_time_seconds=sim_t,
    )

    if auth_result.outcome != DecisionOutcome.APPROVED:
        return {
            "ok": False,
            "status": auth_result.outcome.value,
            "proposal_id": proposal.proposal_id,
            "approval_id": approval_id,
            "original_decision_id": pending["decision_id"],
            "violations": [v.model_dump() for v in auth_result.violations],
        }

    # EXECUTE via canonical executor
    executor = _get_executor(pending["domain"], runtime)
    if executor is None:
        return {
            "ok": True,
            "status": "approved_no_executor",
            "proposal_id": proposal.proposal_id,
            "approval_id": approval_id,
        }

    # Capture pre-execution KPI snapshot for WORLD LIVE projection
    from maiw_api.demo.kpi import DemoKPIEngine
    from datetime import datetime, timezone as _tz

    _pre_kpi = DemoKPIEngine(ctrl.world, ctrl._last_analyze_wall_time).compute()
    _pre_kpi_dict = _pre_kpi.to_dict()

    try:
        exec_result = await executor.execute(proposal, auth_result, trace_id=trace_id)
    except Exception as exc:
        return {"ok": False, "status": "execution_error", "reason": str(exc)}

    # Consume the approval after the execution attempt — APPROVED → CONSUMED
    # (single-use guarantee closes, whatever the outcome).
    ctrl.approval_store.consume(approval_id)

    outcome = _outcome_label(exec_result)
    error_code = _error_code(exec_result)
    domain = pending["domain"]
    target = _proposal_target(proposal, pending)

    if error_code in _BLOCKED_ERROR_CODES:
        # Refused before any write: an earlier write to this target is still
        # unresolved.  Not a new ambiguous write — no event, no retry.
        from maiw_api.write_auth import TypedHTTPError

        ctrl.record_approval_outcome(request.pending_id, "blocked")
        blocking_id = exec_result.execution_id
        raise TypedHTTPError(
            409,
            "RECONCILIATION_REQUIRED",
            (
                f"a previous write to {target!r} has an unresolved outcome "
                f"(execution_id={blocking_id}); reconcile it before writing again"
            ),
            execution_id=blocking_id,
            domain=domain,
            reconcile=_reconcile_hint(blocking_id, domain),
        )

    ctrl.record_approval_outcome(request.pending_id, outcome)
    unknown = outcome == "unknown"

    # Publish EXECUTE SSE
    await bus.publish(
        ScenarioEvent(
            category="EXECUTE",
            message=f"execute:{pending['capability']}",
            detail=(
                f"outcome={outcome} success={exec_result.success} "
                f"exec_id={exec_result.execution_id}"
            ),
            sim_time_seconds=sim_t,
        )
    )
    if unknown:
        await _publish_reconciliation_required(
            ctrl,
            execution_id=exec_result.execution_id,
            domain=domain,
            capability=pending["capability"],
            target=target,
            proposal_id=proposal.proposal_id,
            decision_id=pending["decision_id"],
            approval_id=approval_id,
            trace_id=trace_id,
            error_code=error_code,
        )

    # Compute and publish fresh KPI
    kpi = DemoKPIEngine(ctrl.world, ctrl._last_analyze_wall_time).compute()
    kpi_dict = kpi.to_dict()
    ctrl._kpi_history.append(kpi_dict)
    if len(ctrl._kpi_history) > ctrl._MAX_KPI_HISTORY:
        ctrl._kpi_history = ctrl._kpi_history[-ctrl._MAX_KPI_HISTORY :]
    await bus.publish_kpi(kpi_dict, sim_t)

    # Store LiveExecutionRecord for WORLD LIVE projection
    _kpi_delta: dict = {}
    for _k in _pre_kpi_dict:
        if _k in kpi_dict:
            _pv, _qv = _pre_kpi_dict[_k], kpi_dict[_k]
            if isinstance(_pv, (int, float)) and isinstance(_qv, (int, float)):
                _kpi_delta[_k] = round(_qv - _pv, 2)
    ctrl.set_execution_record({
        "proposal_id": proposal.proposal_id,
        "decision_id": pending["decision_id"],
        "execution_id": exec_result.execution_id,
        "trace_id": trace_id,
        "capability": pending["capability"],
        "target": pending.get("target", ""),
        "domain": domain,
        "outcome": outcome,
        "execution_confirmed": None if unknown else bool(exec_result.executed),
        "pre_kpi": _pre_kpi_dict,
        "post_kpi": kpi_dict,
        "kpi_delta": _kpi_delta,
        "executed_at": datetime.now(_tz.utc).isoformat(),
        "pending_id": request.pending_id,
    })

    # Same outcome semantics as the canonical write routes: ``status`` is the
    # real ExecutionOutcome; UNKNOWN is 202 with executed=null — never a
    # success, never a failure, never retried.
    body: dict[str, Any] = {
        "ok": bool(exec_result.success),
        "status": outcome,
        "outcome": outcome,
        "executed": None if unknown else bool(exec_result.executed),
        "success": bool(exec_result.success),
        "reconciliation_required": unknown,
        "capability": pending["capability"],
        "domain": domain,
        "target": target,
        "proposal_id": proposal.proposal_id,
        "original_decision_id": pending["decision_id"],
        "approval_id": approval_id,
        "execution_id": exec_result.execution_id,
        "trace_id": trace_id,
    }
    if error_code:
        body["error_code"] = error_code
    for field_name in ("dispatch_status", "server_disposition", "uncertainty_reason"):
        value = getattr(exec_result, field_name, None)
        if isinstance(value, str):
            body[field_name] = value
    if unknown:
        body["retried"] = False
        body["reconcile"] = _reconcile_hint(exec_result.execution_id, domain)
        return JSONResponse(status_code=202, content=body)
    return body


@router.post("/demo/reject")
async def reject_proposal(request: ApproveRequest):
    """Reject a pending proposal."""
    from maiw_decision.approval import ApprovalAlreadyDecided

    ctrl = _get_controller()
    pending = ctrl.remove_pending_approval(request.pending_id)
    if pending is None:
        raise HTTPException(
            status_code=404,
            detail=f"No pending approval for pending_id={request.pending_id}",
        )

    approval_id = pending.get("approval_id")
    if approval_id:
        try:
            ctrl.approval_store.reject(approval_id, rejected_by=request.approved_by)
        except ApprovalAlreadyDecided:
            pass  # Already decided — rejection is still the right outcome for the queue entry

    ctrl.record_approval_outcome(request.pending_id, "rejected")

    await ctrl.bus.publish_reject(
        pending["capability"],
        pending["proposal_id"],
        request.approved_by,
        trace_id=pending["trace_id"],
        sim_time_seconds=ctrl.world.clock.elapsed_seconds,
    )

    return {
        "ok": True,
        "status": "rejected",
        "pending_id": request.pending_id,
        "approval_id": approval_id,
        "capability": pending["capability"],
    }


# ── Reconciliation ────────────────────────────────────────────────────────────


class ReconcileRequest(BaseModel):
    execution_id: str
    domain: str = Field(..., description="equipment | labor | wave")
    trace_id: str | None = None


@router.post("/demo/reconcile")
async def reconcile_execution(request: ReconcileRequest):
    """
    Reconcile an UNKNOWN execution against current authoritative warehouse state.

    Phase 10E Batch 3: reads authoritative state through canonical MCP read
    skills, compares against the ExecutionIntent snapshot stored at begin() time,
    and stores a ReconciliationRecord alongside the original UNKNOWN outcome.

    Architecture invariants enforced:
    - Reads through canonical MCP read skills only (never DemoWarehouseWorld directly)
    - ExecutionOutcome.UNKNOWN is preserved — not overwritten
    - No automatic retry — CONFIRMED_NOT_EXECUTED is safe for higher-level re-evaluation

    Returns the reconciliation outcome and effective_status of the record.
    """
    from maiw_execution import ReconciliationService, ReconciliationOutcome
    from maiw_execution.outcome import ExecutionOutcome
    from maiw_api.demo.events import ScenarioEvent

    ctrl = _get_controller()
    try:
        from maiw_api.bootstrap import get_runtime

        runtime = await get_runtime()
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Runtime unavailable: {exc}"
        ) from exc

    # Resolve registry for the requested domain
    registry = _get_registry(request.domain, runtime)
    if registry is None:
        raise HTTPException(
            status_code=503,
            detail=f"No ExecutionRegistry wired for domain={request.domain!r}",
        )

    rec = registry.get_by_execution_id(request.execution_id)
    if rec is None:
        raise HTTPException(
            status_code=404,
            detail=f"No execution record found for execution_id={request.execution_id!r}",
        )

    if rec.outcome != ExecutionOutcome.UNKNOWN:
        raise HTTPException(
            status_code=409,
            detail=(
                f"execution_id={request.execution_id!r} has outcome={rec.outcome!r}; "
                "reconciliation requires UNKNOWN outcome"
            ),
        )

    trace_id = request.trace_id or str(uuid.uuid4())
    strategy = _build_reconciliation_strategy(request.domain, runtime)
    if strategy is None:
        raise HTTPException(
            status_code=503,
            detail=f"No reconciliation strategy available for domain={request.domain!r}",
        )

    from maiw_mcp.deadline import RequestDeadline as _RD  # noqa: PLC0415

    reconcile_deadline = _RD.from_timeout(settings.reconciliation_timeout_seconds)

    service = ReconciliationService()
    try:
        reconciliation_record = await service.reconcile(
            rec, strategy=strategy, trace_id=trace_id, deadline=reconcile_deadline
        )
    except Exception as exc:
        _raise_typed_http(exc, "reconciliation")
        raise HTTPException(
            status_code=500, detail=f"Reconciliation failed: {exc}"
        ) from exc
    registry.set_reconciliation(request.execution_id, reconciliation_record)

    sim_t = ctrl.world.clock.elapsed_seconds
    await ctrl.bus.publish(
        ScenarioEvent(
            category="RECONCILE",
            message=f"reconciliation.{reconciliation_record.outcome.value}",
            detail=(
                f"execution_id={request.execution_id} "
                f"domain={request.domain} "
                f"effective_status={rec.effective_status} "
                f"trace_id={trace_id}"
            ),
            sim_time_seconds=sim_t,
        )
    )
    # Outcome event the Reliability UI resolves on (CONFIRMED_EXECUTED /
    # CONFIRMED_NOT_EXECUTED / INDETERMINATE), carrying the same ids as the
    # RECONCILIATION_REQUIRED event it answers.
    outcome_value = reconciliation_record.outcome.value
    outcome_category = _RECONCILIATION_EVENT_CATEGORY.get(outcome_value)
    if outcome_category is not None:
        target = rec.intent.target if rec.intent else None
        await ctrl.bus.publish(
            ScenarioEvent(
                category=outcome_category,
                message=f"reconciliation.{outcome_value}",
                detail=json.dumps(
                    {
                        "execution_id": request.execution_id,
                        "domain": request.domain,
                        "target": target,
                        "reconciliation_id": reconciliation_record.reconciliation_id,
                        "reconciliation_outcome": outcome_value,
                        "effective_status": rec.effective_status,
                        "trace_id": trace_id,
                    },
                    sort_keys=True,
                ),
                asset_id=target if request.domain == "equipment" else None,
                sim_time_seconds=sim_t,
                execution_id=request.execution_id,
                domain=request.domain,
            )
        )

    return {
        "ok": True,
        "execution_id": request.execution_id,
        "domain": request.domain,
        "reconciliation_id": reconciliation_record.reconciliation_id,
        "reconciliation_outcome": reconciliation_record.outcome.value,
        "effective_status": rec.effective_status,
        "proposal_id": rec.intent.proposal_id if rec.intent else None,
        "decision_id": rec.intent.decision_id if rec.intent else None,
        "approval_id": rec.intent.approval_id if rec.intent else None,
        "trace_id": trace_id,
        "error": reconciliation_record.error,
    }


def _get_registry(domain: str, runtime: Any) -> Any:
    """Return the ExecutionRegistry for a domain, or None."""
    if domain == "equipment":
        return runtime.equipment_registry
    if domain == "labor":
        return runtime.labor_registry
    if domain == "wave":
        return runtime.wave_registry
    return None


def _build_reconciliation_strategy(domain: str, runtime: Any) -> Any:
    """
    Build a concrete ReconciliationStrategy for the requested domain.

    v2.0.1 round 3: the strategies live in ``maiw_api.reconciliation`` and are
    shared with the operator-authenticated production route
    ``POST /api/v1/executions/{execution_id}/reconcile`` (no demo dependency).
    They read authoritative state through canonical MCP read skills only —
    DemoWarehouseWorld is never accessed directly.

    Returns None if the required skills are not wired.
    """
    from maiw_api.reconciliation import build_reconciliation_strategy

    return build_reconciliation_strategy(domain, getattr(runtime, "mcp_client", None))


# ── Counterfactual artifact ───────────────────────────────────────────────────


@router.get("/demo/counterfactual/result")
async def counterfactual_result():
    """Serve the last counterfactual evaluation artifact (run scripts/counterfactual_eval.py)."""
    import json as _json
    from pathlib import Path as _Path
    from fastapi.responses import JSONResponse as _JSONResponse

    artifact = (
        _Path(__file__).parent.parent.parent.parent.parent
        / "artifacts"
        / "demo"
        / "labor_wave_control_vs_maiw.json"
    )
    if not artifact.exists():
        raise HTTPException(
            status_code=404,
            detail="No counterfactual result found. Run: python scripts/counterfactual_eval.py",
        )
    return _JSONResponse(content=_json.loads(artifact.read_text()))


# ── SSE event stream ──────────────────────────────────────────────────────────


@router.get("/events/stream")
async def events_stream(request: Request):
    """
    Server-Sent Events stream of simulation activity.

    Streams ``ScenarioEvent`` objects as JSON lines in SSE format.
    Clients connect and receive all events while the connection is open.
    Disconnects cleanly unsubscribe the queue.

    Format per event:
        data: {"ts": "...", "category": "...", "message": "...", "detail": null}
    """
    ctrl = _get_controller()
    bus = ctrl.bus
    queue = bus.subscribe()

    async def generate():
        # Send a comment heartbeat first so the browser sees the connection open
        yield ": connected\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    # Heartbeat keepalive
                    yield ": keepalive\n\n"
                    continue
                if event is None:
                    # Sentinel — bus evicted this subscriber
                    break
                try:
                    payload = json.dumps(event.to_sse_dict(), default=str)
                    yield f"data: {payload}\n\n"
                except Exception as exc:
                    logger.warning("SSE serialization error: %s", exc)
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
