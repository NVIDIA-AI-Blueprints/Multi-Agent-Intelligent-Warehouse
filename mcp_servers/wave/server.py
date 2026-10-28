# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW Wave MCP Server — official MCP Python SDK v2 (mcp 2.0.0).

Exposes vendor-neutral warehouse wave capabilities as MCP tools:

    warehouse.wave.get              — current wave task context (READ)
    warehouse.wave.get_risk         — OTIF risk assessment (READ/COMPUTATION)
    warehouse.wave.reprioritize     — execute approved reprioritization write (WRITE)

Architecture invariant
----------------------
MCP tools expose EXECUTABLE operations only.
Proposal generation (ActionProposal.for_wave_reprioritize) is built locally
in the agent/skill layer — no MCP round-trip is required.

Write tools are called ONLY after WaveActionExecutor verifies a bound
APPROVED DecisionResult.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from mcp.server import MCPServer

from maiw_contracts.wave import (
    WAVE_GET_METADATA,
    WAVE_GET_RISK_METADATA,
    WAVE_REPRIORITIZE_METADATA,
    WaveGetRequest,
    WaveReprioritizeRequest,
    WaveRiskRequest,
)
from maiw_mcp.errors import BackendUnavailable, WriteNotApplied
from maiw_mcp.write_disposition import not_applied_result

logger = logging.getLogger(__name__)

# ── Server instance ───────────────────────────────────────────────────────────

mcp_server = MCPServer(
    "MAIW Wave Server",
    instructions=(
        "Provides vendor-neutral warehouse wave management capabilities. "
        "Use warehouse.wave.get to query current wave/pick task status. "
        "Use warehouse.wave.get_risk to assess OTIF risk for a wave. "
        "Write tools (reprioritize) execute APPROVED operations only — "
        "they require both proposal_id and decision_id bound to an APPROVED DecisionResult."
    ),
)

# ── Provider registry ─────────────────────────────────────────────────────────

_provider = None  # type: Any


def configure_server(provider: Any) -> None:
    """Set the backend provider used by this server."""
    global _provider
    _provider = provider
    logger.info("WaveMCPServer: configured with provider %s", type(provider).__name__)


def _get_provider() -> Any:
    global _provider
    if _provider is None:
        _provider = _build_default_provider()
    return _provider


def _build_default_provider() -> Any:
    from mcp_servers.wave.adapters.maiw_backend import MAIWWaveAdapter
    logger.info("WaveMCPServer: using MAIWWaveAdapter (WMS backend)")
    return MAIWWaveAdapter()


# ── Tools ─────────────────────────────────────────────────────────────────────


@mcp_server.tool(
    name=WAVE_GET_METADATA.name,
    description=WAVE_GET_METADATA.description,
)
async def warehouse_wave_get(
    warehouse_id: str = "default",
    wave_id: str | None = None,
    zone: str | None = None,
    status_filter: str | None = None,
    task_type: str | None = None,
) -> str:
    provider = _get_provider()
    req = WaveGetRequest(
        warehouse_id=warehouse_id,
        wave_id=wave_id,
        zone=zone,
        status_filter=status_filter,
        task_type=task_type,
    )
    try:
        result = await provider.get_wave(req)
    except Exception as exc:
        raise BackendUnavailable(f"Wave fetch failed: {exc}") from exc
    return json.dumps(result.model_dump())


@mcp_server.tool(
    name=WAVE_GET_RISK_METADATA.name,
    description=WAVE_GET_RISK_METADATA.description,
)
async def warehouse_wave_get_risk(
    warehouse_id: str = "default",
    wave_id: str | None = None,
    zone: str | None = None,
    cutoff_minutes: int = 60,
) -> str:
    provider = _get_provider()
    req = WaveRiskRequest(
        warehouse_id=warehouse_id,
        wave_id=wave_id,
        zone=zone,
        cutoff_minutes=cutoff_minutes,
    )
    try:
        result = await provider.get_wave_risk(req)
    except Exception as exc:
        raise BackendUnavailable(f"Wave risk assessment failed: {exc}") from exc
    return json.dumps(result.model_dump())


@mcp_server.tool(
    name=WAVE_REPRIORITIZE_METADATA.name,
    description=WAVE_REPRIORITIZE_METADATA.description,
)
async def warehouse_wave_reprioritize(
    warehouse_id: str,
    new_priority: str,
    proposal_id: str,
    decision_id: str,
    wave_id: str | None = None,
    zone: str | None = None,
    reason: str = "",
    execution_id: str | None = None,
) -> str:
    provider = _get_provider()
    req = WaveReprioritizeRequest(
        warehouse_id=warehouse_id,
        wave_id=wave_id,
        zone=zone,
        new_priority=new_priority,
        reason=reason,
        proposal_id=proposal_id,
        decision_id=decision_id,
        execution_id=execution_id,
    )
    try:
        result = await provider.execute_wave_reprioritize(req)
    except WriteNotApplied as exc:
        # v2.0.1 round 4: the provider certified no mutation → typed NOT_APPLIED
        return not_applied_result(str(exc), exc.rejection_code)
    except Exception as exc:
        raise BackendUnavailable(f"Wave reprioritization write failed: {exc}") from exc
    return json.dumps(result.model_dump())


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Dockerfile.mcp runs ``python -m mcp_servers.wave.server``; without this
    # block the module only imported, exited 0 and the container restart-looped.
    transport = os.getenv("MAIW_MCP_TRANSPORT", "stdio")
    port = int(os.getenv("MAIW_MCP_WAVE_PORT", "8768"))
    host = os.getenv("MAIW_MCP_WAVE_HOST", "0.0.0.0")

    if transport == "streamable-http":
        mcp_server.run("streamable-http", host=host, port=port, stateless_http=True)
    elif transport == "sse":
        mcp_server.run("sse", host=host, port=port)
    else:
        mcp_server.run("stdio")
