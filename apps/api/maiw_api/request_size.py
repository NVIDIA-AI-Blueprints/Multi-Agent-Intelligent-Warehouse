# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Request body size limit — pure ASGI middleware.

The previous ``@app.middleware("http")`` check only looked at the declared
``Content-Length`` header, so a chunked/streamed body (no Content-Length) was
never measured, and it raised ``HTTPException(413)`` from an HTTP middleware,
which FastAPI's exception handlers never see (clients got a 500).

This middleware:

* rejects early with 413 when the declared ``Content-Length`` exceeds the
  limit (fast path — the app is never called);
* wraps ``receive`` and counts the body bytes actually received, so a
  streamed body is cut off as soon as it crosses the limit; the app's body
  read raises :class:`RequestBodyTooLarge` and whatever it would have
  answered is replaced by a 413 JSON response;
* touches only the request side — ``http.disconnect`` and every response
  message pass through unchanged, so SSE / streaming responses are unaffected.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable, MutableMapping

from fastapi import HTTPException

logger = logging.getLogger(__name__)

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

UPLOAD_PATH_MARKER = "/upload"


class RequestBodyTooLarge(HTTPException):
    """Raised from the wrapped ``receive`` once the body exceeds the limit.

    An ``HTTPException`` so FastAPI's body parsing re-raises it unchanged
    instead of turning it into a 400 "error parsing the body".
    """

    def __init__(self, limit: int) -> None:
        super().__init__(
            status_code=413,
            detail=f"Request too large: body exceeds {limit} bytes",
        )
        self.limit = limit


def _declared_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers") or ():
        if name.lower() == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


async def _send_413(send: Send, message: str) -> None:
    body = json.dumps({"error": True, "message": message, "status_code": 413}).encode(
        "utf-8"
    )
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
                (b"connection", b"close"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body, "more_body": False})


class RequestBodySizeLimitMiddleware:
    """Enforce a maximum request body size on every HTTP request.

    Paths containing ``/upload`` use ``max_upload_size``; all others use
    ``max_request_size``.
    """

    def __init__(
        self, app: ASGIApp, *, max_request_size: int, max_upload_size: int
    ) -> None:
        self.app = app
        self.max_request_size = max_request_size
        self.max_upload_size = max_upload_size

    def limit_for(self, path: str) -> int:
        if UPLOAD_PATH_MARKER in path:
            return self.max_upload_size
        return self.max_request_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        limit = self.limit_for(scope.get("path", ""))
        declared = _declared_length(scope)
        if declared is not None and declared > limit:
            await _send_413(send, f"Request too large: {declared} bytes (max {limit})")
            return

        received = 0
        exceeded = False
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            if exceeded:
                raise RequestBodyTooLarge(limit)
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise RequestBodyTooLarge(limit)
            return message

        async def guarded_send(message: Message) -> None:
            nonlocal response_started
            if exceeded and not response_started:
                # The 413 below replaces whatever the app answers to a
                # truncated body (its error response, or a 500).
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except Exception:
            if not exceeded or response_started:
                raise
            logger.debug("request body exceeded %d bytes; answering 413", limit)

        if exceeded and not response_started:
            await _send_413(send, f"Request too large: body exceeds {limit} bytes")
