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
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

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
    Equipment fault:
        {"event_type": "equipment_fault", "payload": {"asset_id": "AGV-01", "fault_code": "E_MOTOR_OVERTEMP"}}

    Low stock:
        {"event_type": "low_stock", "payload": {"sku": "SKU-1001", "quantity_available": 50}}

    Worker absence:
        {"event_type": "worker_absence", "payload": {"worker_id": "w-002"}}
    """
    ctrl = _get_controller()
    try:
        result = await ctrl.inject(request.event_type, request.payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "event_type": request.event_type, "result": result}


# ── Status ────────────────────────────────────────────────────────────────────


@router.get("/demo/status")
async def demo_status():
    """Return current simulation status: active scenario, clock, world summary."""
    ctrl = _get_controller()
    return ctrl.status()


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
