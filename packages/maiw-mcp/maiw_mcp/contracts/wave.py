# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Wave Management domain contracts — typed request/result schemas and capability metadata.

Capabilities implemented:
    warehouse.wave.get              — READ      — current wave task context
    warehouse.wave.get_risk         — READ/COMP — OTIF risk assessment for a wave
    warehouse.wave.reprioritize     — WRITE     — reprioritize wave tasks (MEDIUM risk)

Backed by WMSIntegrationService.get_tasks() / update_task_status() and
OperationsActionTools.generate_pick_wave().
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .common import CapabilityMetadata

# ── Shared types ───────────────────────────────────────────────────────────────


class WaveTaskInfo(BaseModel):
    """Operational summary for one wave task."""

    task_id: str
    task_type: str = Field(
        description="PICK | PACK | SHIP | RECEIVE | PUTAWAY | CYCLE_COUNT | TRANSFER"
    )
    zone: str | None = None
    status: str = Field(
        description="pending | in_progress | completed | failed | cancelled"
    )
    assigned_to: str | None = None
    priority: str = "medium"
    deadline: str | None = None


class WaveRiskFactor(BaseModel):
    """One risk contributor for a wave."""

    factor: str
    severity: str = Field(description="low | medium | high")
    detail: str = ""


# ── Get Wave ───────────────────────────────────────────────────────────────────


class WaveGetRequest(BaseModel):
    """Request current wave task context."""

    warehouse_id: str = "default"
    wave_id: str | None = None
    zone: str | None = None
    status_filter: str | None = None
    task_type: str | None = None


class WaveGetResult(BaseModel):
    """Current wave / pick task context."""

    tasks: list[WaveTaskInfo] = Field(default_factory=list)
    total_tasks: int = 0
    zones_active: list[str] = Field(default_factory=list)
    summary: dict[str, int] = Field(
        default_factory=dict,
        description="summary[status] = count",
    )
    wave_id: str | None = None
    source: str = "mock"


WAVE_GET_METADATA = CapabilityMetadata(
    name="warehouse.wave.get",
    version=1,
    domain="wave",
    side_effect="read",
    risk="read_only",
    idempotent=True,
    timeout_seconds=10,
    required_permission="wave:read",
    description=(
        "Return current wave/pick task status for a warehouse zone. "
        "Aggregates WMS task data into a wave-level operational view. "
        "Read-only; no state mutation."
    ),
)


# ── Get Risk ───────────────────────────────────────────────────────────────────


class WaveRiskRequest(BaseModel):
    """Request OTIF risk assessment for a wave."""

    warehouse_id: str = "default"
    wave_id: str | None = None
    zone: str | None = None
    cutoff_minutes: int = Field(
        default=60,
        description="Minutes until carrier cutoff (for OTIF calculation)",
    )


class WaveRiskResult(BaseModel):
    """OTIF risk assessment for a wave."""

    otif_at_risk: bool = False
    risk_level: str = Field(description="none | low | medium | high | critical")
    at_risk_task_count: int = 0
    total_task_count: int = 0
    risk_factors: list[WaveRiskFactor] = Field(default_factory=list)
    recommendation: str = ""
    wave_id: str | None = None
    source: str = "mock"


WAVE_GET_RISK_METADATA = CapabilityMetadata(
    name="warehouse.wave.get_risk",
    version=1,
    domain="wave",
    side_effect="read",
    risk="read_only",
    idempotent=True,
    timeout_seconds=10,
    required_permission="wave:read",
    description=(
        "Compute OTIF risk for a wave: which tasks are at risk of missing "
        "carrier cutoff, and the severity. Read-only computation over WMS state; "
        "no mutations."
    ),
)


# ── Reprioritize (WRITE) ───────────────────────────────────────────────────────


class WaveReprioritizeRequest(BaseModel):
    """Execute an approved wave reprioritization."""

    warehouse_id: str
    wave_id: str | None = None
    zone: str | None = None
    new_priority: str = Field(description="low | medium | high | critical")
    reason: str = ""
    proposal_id: str = Field(..., description="Bound ActionProposal.proposal_id")
    decision_id: str = Field(..., description="Bound DecisionResult.result_id")
    execution_id: str | None = Field(
        default=None,
        description="MAIW execution identity, propagated from BaseActionExecutor",
    )


class WaveReprioritizeResult(BaseModel):
    """Result of a wave reprioritization write."""

    success: bool
    tasks_updated: int = 0
    wave_id: str | None = None
    new_priority: str
    proposal_id: str
    decision_id: str
    execution_id: str | None = None
    outcome: str = "executed"
    source: str = "mock"
    message: str = ""


WAVE_REPRIORITIZE_METADATA = CapabilityMetadata(
    name="warehouse.wave.reprioritize",
    version=1,
    domain="wave",
    side_effect="write",
    risk="medium",
    idempotent=False,
    timeout_seconds=15,
    required_permission="wave:execute",
    description=(
        "Execute an approved wave reprioritization. "
        "Updates task priority for all tasks in a wave/zone to address OTIF risk. "
        "Must be called only with a bound APPROVED DecisionResult (proposal_id + decision_id). "
        "Writes to the WMS task table via update_task_status."
    ),
)
