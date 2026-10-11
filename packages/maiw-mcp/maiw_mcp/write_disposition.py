# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Structured write-disposition contract (v2.0.1 round 4, NEW4-P1-01).

Problem
-------
MCP ``isError`` says a tool reported an error.  It does NOT say the tool made
no side effects: a server can apply a mutation and fail afterwards (the fourth
independent re-audit reproduced exactly that, and the operator retry wrote a
second time).  Once ``tools/call`` has reached the server, a generic error is
therefore treated as "may have executed" (``ExecutionOutcome.UNKNOWN``).

Contract
--------
A server may certify that it rejected a write BEFORE any mutation by answering
with an error result whose ``structuredContent`` carries the typed field::

    CallToolResult(
        isError=true,
        content=[TextContent(<same JSON as text>)],
        structuredContent={
            "execution_disposition": "NOT_APPLIED",       # required, exact
            "rejection_code": "INVALID_REQUEST" | "NOT_FOUND" | "PRECONDITION_FAILED",
            "message": "<human readable>",
        },
    )

Client rule (``certifies_not_applied``): the disposition is read ONLY from
``structuredContent`` — never from the text content, an exception name, an
HTTP status or ``isError`` alone — and it must be exactly the string
``"NOT_APPLIED"``.  Anything else (no structuredContent, not an object, field
absent, null, wrong type, other case, padded, unknown value) is not a
certification → UNKNOWN.  This is the only signal that lets a write that
reached the server become a definite ``FAILED / executed=false``.

Server rule: emit it only from code paths that provably ran no mutation —
argument / request validation, and precondition or state checks performed
before any write statement (providers raise
``maiw_mcp.errors.WriteNotApplied`` there).  Every other failure after the
request reached the server is left as a generic tool error (→ UNKNOWN).
"""

from __future__ import annotations

import json
from typing import Any

EXECUTION_DISPOSITION_FIELD = "execution_disposition"
NOT_APPLIED = "NOT_APPLIED"

REJECTION_INVALID_REQUEST = "INVALID_REQUEST"
REJECTION_NOT_FOUND = "NOT_FOUND"
REJECTION_PRECONDITION_FAILED = "PRECONDITION_FAILED"


def certifies_not_applied(structured: Any) -> bool:
    """True only for a dict whose ``execution_disposition`` is exactly ``"NOT_APPLIED"``."""
    if not isinstance(structured, dict):
        return False
    value = structured.get(EXECUTION_DISPOSITION_FIELD)
    return type(value) is str and value == NOT_APPLIED


def describe_disposition(structured: Any) -> str:
    """Short, log-safe description of what the server sent (for the journal)."""
    if structured is None:
        return "absent:no_structured_content"
    if not isinstance(structured, dict):
        return f"malformed:structured_content_{type(structured).__name__}"
    if EXECUTION_DISPOSITION_FIELD not in structured:
        return "absent:no_execution_disposition"
    value = structured[EXECUTION_DISPOSITION_FIELD]
    if type(value) is not str:
        return f"malformed:{type(value).__name__}"
    if value == NOT_APPLIED:
        return NOT_APPLIED
    return f"unrecognised:{value[:32]!r}"


def not_applied_payload(message: str, rejection_code: str) -> dict[str, Any]:
    """The structured payload of a NOT_APPLIED rejection."""
    return {
        EXECUTION_DISPOSITION_FIELD: NOT_APPLIED,
        "rejection_code": rejection_code,
        "message": message,
    }


def not_applied_result(message: str, rejection_code: str) -> Any:
    """
    Server side: the ``CallToolResult`` for a write rejected before any
    mutation.  Return it from an MCP tool (``isError=True`` results are passed
    through by the SDK without output-schema validation).
    """
    from mcp.types import CallToolResult, TextContent

    payload = not_applied_payload(message, rejection_code)
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payload))],
        structured_content=payload,
        is_error=True,
    )


__all__ = [
    "EXECUTION_DISPOSITION_FIELD",
    "NOT_APPLIED",
    "REJECTION_INVALID_REQUEST",
    "REJECTION_NOT_FOUND",
    "REJECTION_PRECONDITION_FAILED",
    "certifies_not_applied",
    "describe_disposition",
    "not_applied_payload",
    "not_applied_result",
]
