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
    """Marker: the tool request was (or may have been) sent; the outcome is not
    known (response lost, or — round 4 — the server answered with an error
    that does not certify non-execution)."""

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


# ── Server-reported tool errors (v2.0.1 round 4, NEW4-P1-01) ─────────────────
#
# MCP ``isError`` reports that a tool failed; it does NOT say the tool made no
# side effects (a server can apply a mutation and fail afterwards).  Once
# ``tools/call`` reached the server, only the explicit structured disposition
# ``execution_disposition == "NOT_APPLIED"`` (see ``maiw_mcp.write_disposition``)
# proves non-execution.  ``MAIWMCPClient`` raises exactly one of:
#
#   MCPToolNotApplied           isError + structuredContent certifies NOT_APPLIED
#                               → the server rejected the request before any
#                                 mutation (definite non-execution)
#   MCPToolErrorOutcomeUnknown  isError without a valid NOT_APPLIED disposition
#                               (absent / malformed / unknown) → for a write the
#                               outcome is UNKNOWN
#
# Both subclass ``MCPToolError`` so read-path callers are unchanged.


class MCPToolNotApplied(MCPToolError):
    """The server certified (``execution_disposition = NOT_APPLIED``) that it
    rejected the tool request before any mutation."""

    dispatched = True
    execution_disposition = "NOT_APPLIED"

    def __init__(self, message: str, *, rejection_code: str | None = None) -> None:
        super().__init__(message)
        self.rejection_code = rejection_code


class MCPToolErrorOutcomeUnknown(MCPToolError, MCPDispatchOutcomeUnknown):
    """The server answered ``isError`` after ``tools/call`` was dispatched and
    did not certify non-execution — the mutation may have been applied."""

    def __init__(self, message: str, *, observed_disposition: str = "absent") -> None:
        super().__init__(message)
        self.observed_disposition = observed_disposition


class WriteNotApplied(BackendUnavailable):
    """
    Raised by a warehouse backend / MCP provider ONLY on a code path that
    provably performed no mutation (request validation, a precondition or
    state check before any write statement).  The MCP server tools turn it into
    the structured ``NOT_APPLIED`` tool error.  Never raise it after a write
    may have been issued — raise any other exception (→ UNKNOWN) instead.
    """

    def __init__(self, message: str, *, rejection_code: str = "PRECONDITION_FAILED") -> None:
        super().__init__(message)
        self.rejection_code = rejection_code
