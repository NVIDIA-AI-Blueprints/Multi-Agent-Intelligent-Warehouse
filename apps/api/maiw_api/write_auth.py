# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Operational write authentication (v2.0.1 round 3, third re-audit NEW3-P1-01).

The third independent re-audit showed that the sandbox — which may reach the
MAIW API host:port to call ``POST /api/v1/inference`` — could also call the
governed equipment write routes with no credential at all.  The DecisionEngine
then auto-approved a LOW-risk release and the MCP write executed.  Governance
is an *authority* decision; it is not *caller authentication*.

This module is the separate credential boundary for consequential operational
writes.  There are two credentials and they are different authority domains:

``MAIW_INFERENCE_INTERNAL_TOKEN`` (header ``X-Maiw-Internal-Token``)
    Held by the sandbox.  Authorises ONLY ``POST /api/v1/inference``.

``MAIW_OPERATOR_WRITE_TOKEN`` (header ``X-Maiw-Operator-Token``)
    Held by the host operator (CLI, automation, or an authenticated operator
    proxy in front of the UI).  Required for every route that can lead to an
    operational warehouse mutation.  NEVER injected into the sandbox, never put
    in the browser bundle.

``require_operator_write`` runs as a route-level dependency, so it is resolved
before the request body is read and before any agent, DecisionEngine,
ActionExecutor or MCP call:

    no ``X-Maiw-Operator-Token``                  → 403 OPERATOR_WRITE_CREDENTIAL_REQUIRED
    wrong value (incl. the inference token)       → 401 INVALID_OPERATOR_WRITE_CREDENTIAL
    server has no usable write token configured   → 503 OPERATOR_WRITE_AUTH_NOT_CONFIGURED
    (unset, < 32 chars, the .env.example placeholder, or equal to the
    inference token)

A missing header is 403 rather than 401 so that a logged-in UI session (JWT in
``Authorization``) is told "not authorised for operational writes" instead of
being logged out by the UI's 401 handler.  A JWT alone never authorises an
operational write.

``require_governed_writes_offered`` then refuses (503
GOVERNED_WRITES_NOT_OFFERED) in a profile that does not offer governed writes,
so ``/api/v1/ready`` (``governed_write_path: not_offered``) and behaviour agree.
"""

from __future__ import annotations

import hmac
import logging
import os
from dataclasses import dataclass
from typing import Mapping

from fastapi import Header, HTTPException

logger = logging.getLogger(__name__)

OPERATOR_WRITE_TOKEN_ENV = "MAIW_OPERATOR_WRITE_TOKEN"
OPERATOR_WRITE_HEADER = "X-Maiw-Operator-Token"
INFERENCE_TOKEN_ENV = "MAIW_INFERENCE_INTERNAL_TOKEN"
MIN_TOKEN_LENGTH = 32
PLACEHOLDER_VALUES = frozenset(
    {
        "your-strong-random-operator-write-token-min-32-chars",
        "your-strong-random-token-min-32-chars",
    }
)


class OperatorWriteAuthError(HTTPException):
    """Typed denial raised before any governed-write logic runs."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(status_code=status_code, detail=f"{code}: {message}")
        self.code = code
        self.message = message

    def as_body(self) -> dict:
        return {
            "error": True,
            "code": self.code,
            "message": self.message,
            "status_code": self.status_code,
        }


@dataclass(frozen=True)
class OperatorWriteAuthStatus:
    configured: bool
    reason: str | None = None

    def as_dict(self) -> dict:
        out: dict = {"configured": self.configured, "header": OPERATOR_WRITE_HEADER}
        if self.reason:
            out["reason"] = self.reason
        return out


def operator_write_auth_status(
    env: Mapping[str, str] | None = None,
) -> OperatorWriteAuthStatus:
    """Is a usable operator write credential configured?  Never returns the value."""
    env = os.environ if env is None else env
    token = env.get(OPERATOR_WRITE_TOKEN_ENV) or ""
    if not token:
        return OperatorWriteAuthStatus(False, f"{OPERATOR_WRITE_TOKEN_ENV} is not set")
    if token in PLACEHOLDER_VALUES:
        return OperatorWriteAuthStatus(
            False, f"{OPERATOR_WRITE_TOKEN_ENV} is the .env.example placeholder"
        )
    if len(token) < MIN_TOKEN_LENGTH:
        return OperatorWriteAuthStatus(
            False, f"{OPERATOR_WRITE_TOKEN_ENV} is shorter than {MIN_TOKEN_LENGTH} chars"
        )
    inference = env.get(INFERENCE_TOKEN_ENV) or ""
    if inference and hmac.compare_digest(
        token.encode("utf-8"), inference.encode("utf-8")
    ):
        return OperatorWriteAuthStatus(
            False,
            f"{OPERATOR_WRITE_TOKEN_ENV} equals {INFERENCE_TOKEN_ENV}; the sandbox "
            "inference credential must never authorise operational writes",
        )
    return OperatorWriteAuthStatus(True)


async def require_operator_write(
    x_maiw_operator_token: str | None = Header(default=None),
) -> str:
    """
    FastAPI dependency: authenticate the caller for an operational write.

    Returns the principal label ``"operator"``.  Raises
    ``OperatorWriteAuthError`` (401 / 403 / 503) otherwise.  The token value is
    never logged or echoed.
    """
    status = operator_write_auth_status()
    if not status.configured:
        logger.error("operational write refused: %s", status.reason)
        raise OperatorWriteAuthError(
            503,
            "OPERATOR_WRITE_AUTH_NOT_CONFIGURED",
            "operational writes are disabled: no usable operator write credential "
            f"is configured ({status.reason})",
        )
    if not x_maiw_operator_token:
        logger.warning("operational write refused: no %s header", OPERATOR_WRITE_HEADER)
        raise OperatorWriteAuthError(
            403,
            "OPERATOR_WRITE_CREDENTIAL_REQUIRED",
            f"operational writes require the {OPERATOR_WRITE_HEADER} credential; "
            "the inference credential and user sessions do not authorise writes",
        )
    expected = os.environ[OPERATOR_WRITE_TOKEN_ENV]
    if not hmac.compare_digest(
        x_maiw_operator_token.encode("utf-8"), expected.encode("utf-8")
    ):
        logger.warning("operational write refused: invalid %s", OPERATOR_WRITE_HEADER)
        raise OperatorWriteAuthError(
            401,
            "INVALID_OPERATOR_WRITE_CREDENTIAL",
            f"invalid {OPERATOR_WRITE_HEADER} credential",
        )
    return "operator"


async def require_governed_writes_offered() -> None:
    """FastAPI dependency: the active profile must offer governed writes."""
    from maiw_api.profile import resolve_profile

    profile = resolve_profile()
    if not profile.valid or not profile.governed_writes:
        raise OperatorWriteAuthError(
            503,
            "GOVERNED_WRITES_NOT_OFFERED",
            f"deployment profile {profile.name!r} does not offer governed "
            "operational writes (use MAIW_DEPLOYMENT_PROFILE=reference_governed)",
        )


__all__ = [
    "OPERATOR_WRITE_TOKEN_ENV",
    "OPERATOR_WRITE_HEADER",
    "MIN_TOKEN_LENGTH",
    "OperatorWriteAuthError",
    "OperatorWriteAuthStatus",
    "operator_write_auth_status",
    "require_operator_write",
    "require_governed_writes_offered",
]
