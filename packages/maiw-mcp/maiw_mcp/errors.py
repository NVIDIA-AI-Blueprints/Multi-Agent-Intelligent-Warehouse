# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Typed error hierarchy for MCP capability calls.

All errors raised by MAIWMCPClient and InventoryLookupSkill are subclasses of
MAIWMCPError.  Agents catch these typed errors instead of bare exceptions.
"""

from __future__ import annotations


class MAIWMCPError(Exception):
    """Base class for all MAIW MCP errors."""


class MCPUnavailable(MAIWMCPError):
    """MCP server is unreachable or transport-level connection failed."""


class MCPTimeout(MAIWMCPError):
    """MCP call timed out before the server responded."""


class MCPToolError(MAIWMCPError):
    """Server returned a tool-level error (isError=True in CallToolResult)."""


class MCPContractError(MAIWMCPError):
    """Response could not be validated against the expected capability contract."""


class CapabilityNotFound(MAIWMCPError):
    """No MCP server is registered for the requested capability name."""


class CapabilityPermissionDenied(MAIWMCPError):
    """Caller lacks the required permission for the capability."""


class BackendUnavailable(MAIWMCPError):
    """The warehouse backend (DB, WMS, ERP) is unavailable or returned an error."""


# ── Dispatch-phase classification (v2.0.1 round 3, NEW3-P1-02) ───────────────
#
# A failed MCP call is only a *definite* non-execution when MAIW can prove the
# tool request never left the client.  Once ``tools/call`` has been dispatched,
# a lost response (server crash, connection reset, read timeout, transport
# interruption) says nothing about whether the server applied the write.
# ``MAIWMCPClient`` tags every transport failure with the phase it happened in:
#
#   MCPNotDispatched           the request was provably never sent (connect /
#                              session handshake failed, circuit open)
#   MCPDispatchOutcomeUnknown  the request was (or may have been) sent and no
#                              usable response arrived — for a write this is
#                              ExecutionOutcome.UNKNOWN, never FAILED
#
# Both are marker bases mixed into the existing transport errors, so callers
# that catch ``MCPUnavailable`` / ``MCPTimeout`` keep working unchanged.


class MCPNotDispatched(MAIWMCPError):
    """Marker: the tool request was provably never sent to the server."""

    dispatched = False


class MCPDispatchOutcomeUnknown(MAIWMCPError):
    """Marker: the tool request was (or may have been) sent; response lost."""

    dispatched = True


class MCPConnectFailed(MCPUnavailable, MCPNotDispatched):
    """Connection / session handshake failed before ``tools/call`` was sent."""


class MCPConnectTimeout(MCPTimeout, MCPNotDispatched):
    """Timed out connecting / handshaking, before ``tools/call`` was sent."""


class MCPCircuitOpen(MCPUnavailable, MCPNotDispatched):
    """The domain circuit breaker refused the call; nothing was sent."""


class MCPResponseLost(MCPUnavailable, MCPDispatchOutcomeUnknown):
    """Transport failed after ``tools/call`` was dispatched (reset, crash, EOF)."""


class MCPTimeoutAfterDispatch(MCPTimeout, MCPDispatchOutcomeUnknown):
    """No response within the read timeout after ``tools/call`` was dispatched."""
