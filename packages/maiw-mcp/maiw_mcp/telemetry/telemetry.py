# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Structured telemetry for MCP capability calls (MCP SDK v2, protocol 2026-07-28).

Emits a single JSON log line per call, compatible with the existing MAIW
structured logging convention.  Propagates the ModelGateway correlation ID
(trace_id) so the full trace can be assembled:

    User/Event → Agent → ModelGateway → Skill → MCP → Backend
    (all with the same trace_id)
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from importlib.metadata import version as pkg_version

logger = logging.getLogger("maiw_mcp.telemetry")

# Resolved once at import time — avoids per-call overhead
_MCP_SDK_VERSION = pkg_version("mcp")
_MCP_PROTOCOL_VERSION = "2026-07-28"


@dataclass
class CapabilityCallRecord:
    """One MCP capability call — successful or failed."""

    trace_id: str | None
    capability_name: str
    capability_version: int
    mcp_server: str
    transport: str
    latency_ms: float
    success: bool
    backend: str | None
    error_class: str | None
    error_message: str | None
    mcp_sdk_version: str = _MCP_SDK_VERSION
    mcp_protocol_version: str = _MCP_PROTOCOL_VERSION


class CapabilityTelemetry:
    """Emit structured telemetry for MCP capability calls."""

    def record(self, record: CapabilityCallRecord) -> None:
        level = logging.INFO if record.success else logging.ERROR
        logger.log(level, "%s", json.dumps(asdict(record), default=str))

    def record_success(
        self,
        *,
        capability: str,
        version: int = 1,
        server_url: str,
        transport: str = "streamable-http",
        latency_ms: float,
        backend: str | None = None,
        trace_id: str | None = None,
    ) -> None:
        self.record(
            CapabilityCallRecord(
                trace_id=trace_id,
                capability_name=capability,
                capability_version=version,
                mcp_server=server_url,
                transport=transport,
                latency_ms=latency_ms,
                success=True,
                backend=backend,
                error_class=None,
                error_message=None,
            )
        )

    def record_failure(
        self,
        *,
        capability: str,
        version: int = 1,
        server_url: str,
        transport: str = "streamable-http",
        latency_ms: float,
        error: Exception,
        trace_id: str | None = None,
    ) -> None:
        self.record(
            CapabilityCallRecord(
                trace_id=trace_id,
                capability_name=capability,
                capability_version=version,
                mcp_server=server_url,
                transport=transport,
                latency_ms=latency_ms,
                success=False,
                backend=None,
                error_class=type(error).__name__,
                error_message=str(error),
            )
        )
