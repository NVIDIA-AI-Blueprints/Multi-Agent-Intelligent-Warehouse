# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Structured write-disposition contract (v2.0.1 round 4, NEW4-P1-01; strict
trust rules: v2.0.1 final pre-merge, NEW5-P2-01).

Problem
-------
MCP ``isError`` says a tool reported an error.  It does NOT say the tool made
no side effects: a server can apply a mutation and fail afterwards (the fourth
independent re-audit reproduced exactly that, and the operator retry wrote a
second time).  Once ``tools/call`` has reached the server, a generic error is
therefore treated as "may have executed" (``ExecutionOutcome.UNKNOWN``).

The fifth re-audit (NEW5-P2-01) then showed that the *claim* alone was still
trusted: a payload saying ``execution_disposition = NOT_APPLIED`` next to
``outcome=executed`` / ``mutation_status=applied`` / an unknown
``rejection_code`` (error result), or next to ``success=true`` (non-error
result), was certified as non-execution and the operator retry wrote twice.

Contract
--------
A server may certify that it rejected a write BEFORE any mutation in one of
two canonical shapes.

1. Error result (``isError = true``) — ``structuredContent`` is exactly::

       {
           "execution_disposition": "NOT_APPLIED",      # required, exact
           "rejection_code": "INVALID_REQUEST" | "NOT_FOUND" | "PRECONDITION_FAILED",
           "message": "<human readable>",               # optional, a string
       }

   (built by ``not_applied_result``).  ``certifies_not_applied`` is True only
   when ALL of these hold:

   * it is a JSON object;
   * ``execution_disposition`` is exactly the string ``"NOT_APPLIED"``;
   * ``rejection_code`` is present, a string, and one of
     ``KNOWN_REJECTION_CODES`` (exact; no case folding, no padding);
   * ``message``, if present, is a string;
   * there is NO other key.  Any other key — ``outcome``, ``success``,
     ``executed``, ``mutation_status``, ``rows_affected``, ``post_state``,
     ``result`` or anything unrecognised — is a field that could imply
     execution, mutation, success, affected rows or post-state, or an unknown
     field that undermines certainty, so the certification is refused.

2. Non-error result (a canonical write-result contract,
   ``maiw_contracts.*Execute*Result`` / ``LaborAllocateResult`` /
   ``WaveReprioritizeResult``) — ``certifies_not_applied_result`` is True only
   when ALL of these hold:

   * it is a JSON object;
   * ``execution_disposition`` is exactly ``"NOT_APPLIED"``;
   * ``success`` is present and is exactly the boolean ``False``;
   * ``outcome`` is present and exactly one of ``"failed"``, ``"conflict"``,
     ``"deferred"`` — the explicit, typed rejection type of this shape;
   * ``rejection_code``, if present, is a string in ``KNOWN_REJECTION_CODES``;
   * every mutation reference (``assignment_id``, ``maintenance_id``,
     ``allocation_id``) present is ``null``, and every mutation count
     (``tasks_updated``) present is the integer ``0``;
   * request echoes (``proposal_id``, ``decision_id``, ``execution_id``,
     ``source``, ``message``, ``task_id``, ``wave_id``, ``new_priority``) are
     strings or ``null``; ``worker_ids`` is a list of strings;
   * there is NO other key (same reasoning as above).

Everything else — no structuredContent, not an object, field absent, null,
wrong type, other case, padded, unknown value, or a NOT_APPLIED claim that is
contradicted or carries unknown fields — is not a certification → UNKNOWN →
unresolved journal → retry blocked → authoritative reconciliation.  The
disposition is never read from text content, an exception name, an HTTP
status or ``isError`` alone.

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

KNOWN_REJECTION_CODES = frozenset(
    {REJECTION_INVALID_REQUEST, REJECTION_NOT_FOUND, REJECTION_PRECONDITION_FAILED}
)

# Error-result shape: exactly these keys (rejection_code required, message optional).
_ERROR_RESULT_KEYS = frozenset({EXECUTION_DISPOSITION_FIELD, "rejection_code", "message"})

# Non-error result shape (canonical write-result contracts).
NON_EXECUTION_RESULT_OUTCOMES = frozenset({"failed", "conflict", "deferred"})
_RESULT_REQUIRED_KEYS = frozenset({EXECUTION_DISPOSITION_FIELD, "success", "outcome"})
_RESULT_MUTATION_REFERENCES = frozenset({"assignment_id", "maintenance_id", "allocation_id"})
_RESULT_MUTATION_COUNTS = frozenset({"tasks_updated"})
_RESULT_STRING_ECHOES = frozenset(
    {
        "proposal_id",
        "decision_id",
        "execution_id",
        "source",
        "message",
        "task_id",
        "wave_id",
        "new_priority",
    }
)
_RESULT_LIST_ECHOES = frozenset({"worker_ids"})
_RESULT_KEYS = (
    _RESULT_REQUIRED_KEYS
    | {"rejection_code"}
    | _RESULT_MUTATION_REFERENCES
    | _RESULT_MUTATION_COUNTS
    | _RESULT_STRING_ECHOES
    | _RESULT_LIST_ECHOES
)

_MAX_REPORTED_VIOLATIONS = 4


def _key_label(key: Any) -> str:
    return repr(key)[:32] if isinstance(key, str) else f"<{type(key).__name__}>"


def claims_not_applied(payload: Any) -> bool:
    """True when ``payload`` CLAIMS ``execution_disposition == "NOT_APPLIED"``.

    A claim is not a certification — use ``certifies_not_applied`` (error
    result) or ``certifies_not_applied_result`` (non-error result).
    """
    if not isinstance(payload, dict):
        return False
    value = payload.get(EXECUTION_DISPOSITION_FIELD)
    return type(value) is str and value == NOT_APPLIED


def _rejection_code_violation(payload: dict, *, required: bool) -> str | None:
    if "rejection_code" not in payload:
        return "rejection_code_missing" if required else None
    code = payload["rejection_code"]
    if type(code) is not str:
        return f"rejection_code_malformed:{type(code).__name__}"
    if code not in KNOWN_REJECTION_CODES:
        return "rejection_code_unknown"
    return None


def not_applied_violations(payload: Any, *, error_result: bool) -> list[str]:
    """
    Why ``payload`` is NOT a trusted NOT_APPLIED certification (empty list =
    trusted).  ``error_result`` selects the shape: the ``structuredContent``
    of an ``isError`` result, or a non-error write result.  The labels are
    log-safe (key names truncated, values never echoed).
    """
    if not isinstance(payload, dict):
        return [f"not_an_object:{type(payload).__name__}"]
    if not claims_not_applied(payload):
        return ["no_not_applied_disposition"]

    violations: list[str] = []
    allowed = _ERROR_RESULT_KEYS if error_result else _RESULT_KEYS
    for key in payload:
        if key not in allowed:
            violations.append(f"unexpected_field:{_key_label(key)}")

    code_problem = _rejection_code_violation(payload, required=error_result)
    if code_problem:
        violations.append(code_problem)

    if error_result:
        if "message" in payload and type(payload["message"]) is not str:
            violations.append("message_malformed")
        return violations

    if payload.get("success") is not False:
        violations.append("success_not_false")
    outcome = payload.get("outcome")
    if type(outcome) is not str or outcome not in NON_EXECUTION_RESULT_OUTCOMES:
        violations.append("outcome_not_a_rejection")
    for key in _RESULT_MUTATION_REFERENCES:
        if key in payload and payload[key] is not None:
            violations.append(f"mutation_reference_set:{key}")
    for key in _RESULT_MUTATION_COUNTS:
        if key in payload and not (type(payload[key]) is int and payload[key] == 0):
            violations.append(f"mutation_count_nonzero:{key}")
    for key in _RESULT_STRING_ECHOES:
        if key in payload and not (
            payload[key] is None or type(payload[key]) is str
        ):
            violations.append(f"field_malformed:{key}")
    for key in _RESULT_LIST_ECHOES:
        if key in payload and not (
            type(payload[key]) is list
            and all(type(item) is str for item in payload[key])
        ):
            violations.append(f"field_malformed:{key}")
    return violations


def certifies_not_applied(structured: Any) -> bool:
    """Strict: the ``structuredContent`` of an ``isError`` result certifies
    NOT_APPLIED (see the module docstring, shape 1)."""
    return not not_applied_violations(structured, error_result=True)


def certifies_not_applied_result(result: Any) -> bool:
    """Strict: a non-error write result certifies NOT_APPLIED (module
    docstring, shape 2)."""
    return not not_applied_violations(result, error_result=False)


def describe_disposition(structured: Any, *, error_result: bool = True) -> str:
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
        violations = not_applied_violations(structured, error_result=error_result)
        if not violations:
            return NOT_APPLIED
        shown = ",".join(violations[:_MAX_REPORTED_VIOLATIONS])
        more = len(violations) - _MAX_REPORTED_VIOLATIONS
        return f"untrusted_not_applied:{shown}" + (f",+{more}" if more > 0 else "")
    return f"unrecognised:{value[:32]!r}"


def not_applied_payload(message: str, rejection_code: str) -> dict[str, Any]:
    """The structured payload of a NOT_APPLIED rejection."""
    if rejection_code not in KNOWN_REJECTION_CODES:
        raise ValueError(f"unknown NOT_APPLIED rejection_code {rejection_code!r}")
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
    "KNOWN_REJECTION_CODES",
    "NON_EXECUTION_RESULT_OUTCOMES",
    "NOT_APPLIED",
    "REJECTION_INVALID_REQUEST",
    "REJECTION_NOT_FOUND",
    "REJECTION_PRECONDITION_FAILED",
    "certifies_not_applied",
    "certifies_not_applied_result",
    "claims_not_applied",
    "describe_disposition",
    "not_applied_payload",
    "not_applied_result",
    "not_applied_violations",
]
