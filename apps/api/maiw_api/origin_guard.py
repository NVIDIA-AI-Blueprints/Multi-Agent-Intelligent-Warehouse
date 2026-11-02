# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Cross-origin write guard — pure ASGI middleware.

The supported deployment is a single trusted host with every port bound to
127.0.0.1. That keeps other machines out, but not a web page that someone on
the host (or at the end of an SSH tunnel) opens in a browser: the browser can
send requests to ``localhost`` on that page's behalf. CORS only controls
whether the page may READ the response. A "simple" request — a multipart
form, ``text/plain``, or a body with no Content-Type, which FastAPI parses as
JSON — is sent without a preflight and runs the route anyway. Without this
guard such a page could upload a document (starting the model pipeline) or,
through ``npm start`` with ``MAIW_UI_OPERATOR_WRITE_TOKEN`` set, send a
governed equipment write that the dev proxy adds the operator credential to.

Browsers send ``Origin`` on every cross-origin POST/PUT/PATCH/DELETE. This
middleware refuses such a request with 403 before any route runs unless its
``Origin`` is

* one of the configured browser origins (``CORS_ORIGINS`` — the same list
  CORS uses), or
* the API's own origin on a loopback host (the ``/docs`` page). The loopback
  restriction matters: under DNS rebinding the attacker's name resolves to
  127.0.0.1, so ``Origin`` and ``Host`` agree, but the host is not loopback.

Requests without ``Origin`` (curl, scripts, MCP clients, server-side proxies)
and safe methods pass unchanged. ``CORS_ORIGINS=*`` disables the guard, as it
disables CORS.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable, Iterable, MutableMapping
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
ERROR_CODE = "CROSS_ORIGIN_REQUEST_FORBIDDEN"


def _header(scope: Scope, name: bytes) -> str | None:
    for key, value in scope.get("headers") or ():
        if key.lower() == name:
            return value.decode("latin-1")
    return None


def _normalize(origin: str) -> str:
    return origin.strip().rstrip("/").lower()


def _is_loopback_self(origin: str, host: str | None) -> bool:
    """True when ``origin`` is this server's own origin on a loopback name."""
    if not host:
        return False
    parts = urlsplit(origin)
    if parts.scheme not in ("http", "https") or parts.netloc != host.lower():
        return False
    return (parts.hostname or "") in LOOPBACK_HOSTS


async def _send_403(send: Send, origin: str) -> None:
    body = json.dumps(
        {
            "error": ERROR_CODE,
            "message": (
                f"Requests from origin {origin!r} may not change state. "
                "Serve the UI from an origin listed in CORS_ORIGINS."
            ),
            "status_code": 403,
        }
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 403,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class CrossOriginWriteGuardMiddleware:
    """Refuse state-changing browser requests from origins outside ``allowed_origins``."""

    def __init__(self, app: ASGIApp, allowed_origins: Iterable[str]) -> None:
        self.app = app
        origins = {_normalize(o) for o in allowed_origins if o.strip()}
        self.allow_any = "*" in origins
        self.allowed_origins = frozenset(origins - {"*"})

    def allows(self, origin: str, host: str | None) -> bool:
        if self.allow_any:
            return True
        normalized = _normalize(origin)
        return normalized in self.allowed_origins or _is_loopback_self(
            normalized, host
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method", "GET") in SAFE_METHODS:
            await self.app(scope, receive, send)
            return

        origin = _header(scope, b"origin")
        if origin is None or self.allows(origin, _header(scope, b"host")):
            await self.app(scope, receive, send)
            return

        logger.warning(
            "Refused cross-origin %s %s from origin %r",
            scope.get("method"),
            scope.get("path"),
            origin,
        )
        await _send_403(send, origin)
