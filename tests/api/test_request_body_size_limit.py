# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Request body size limit (maiw_api.request_size.RequestBodySizeLimitMiddleware).

The previous HTTP middleware only checked the declared ``Content-Length``, so
a chunked/streamed body (no Content-Length) bypassed the limit — the fourth
audit pushed a 60 MB chunked upload past the 50 MB limit — and it raised
``HTTPException(413)`` from an ``@app.middleware("http")`` function, which
FastAPI's exception handlers never see (clients got a 500).
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from maiw_api.request_size import RequestBodySizeLimitMiddleware
from tests.api.canonical_harness import (
    FakeNIM,
    canonical_env,
    install_gateway,
    running_canonical_app,
)

REQUEST_LIMIT = 1_000
UPLOAD_LIMIT = 5_000
CHUNK = 100


class _ChunkedBody:
    """Async chunk source with no Content-Length; records how far it was read."""

    def __init__(self, total: int, chunk: int = CHUNK) -> None:
        self.total = total
        self.chunk = chunk
        self.sent = 0

    async def __aiter__(self):
        while self.sent < self.total:
            size = min(self.chunk, self.total - self.sent)
            self.sent += size
            yield b"x" * size

    @property
    def exhausted(self) -> bool:
        return self.sent >= self.total


def _small_app():
    """A tiny app behind the middleware; records what its handlers consumed."""
    app = FastAPI()
    seen = {"persisted": 0, "completed": 0, "calls": 0, "swallowed": 0}

    @app.post("/echo")
    async def echo(request: Request):
        seen["calls"] += 1
        async for part in request.stream():
            seen["persisted"] += len(part)  # stands in for writing to storage
        seen["completed"] += 1
        return {"received": seen["persisted"]}

    @app.post("/json")
    async def json_body(payload: dict):
        seen["calls"] += 1
        return {"keys": len(payload)}

    @app.post("/swallow")
    async def swallow(request: Request):
        # A handler that catches body errors and answers 200 anyway must not
        # turn an over-limit body into a success.
        seen["calls"] += 1
        try:
            await request.body()
        except Exception:
            seen["swallowed"] += 1  # deliberately ignored; recorded for the test
        return {"ok": True}

    @app.post("/api/v1/document/upload")
    async def upload(request: Request):
        body = await request.body()
        return {"received": len(body)}

    @app.get("/events")
    async def events():
        async def gen():
            for i in range(50):
                yield f"data: {'y' * 100} {i}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/events")
    async def events_post(request: Request):
        await request.body()

        async def gen():
            for i in range(50):
                yield f"data: {'y' * 100} {i}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    app.add_middleware(
        RequestBodySizeLimitMiddleware,
        max_request_size=REQUEST_LIMIT,
        max_upload_size=UPLOAD_LIMIT,
    )
    return app, seen


def _client(app) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://limits"
    )


def _assert_413(resp: httpx.Response) -> None:
    assert resp.status_code == 413, resp.text
    body = resp.json()
    assert body["status_code"] == 413
    assert body["message"].startswith("Request too large")


# ── Declared Content-Length fast path ─────────────────────────────────────────


async def test_declared_content_length_over_limit_is_413_without_calling_app():
    app, seen = _small_app()
    async with _client(app) as client:
        resp = await client.post("/echo", content=b"x" * (REQUEST_LIMIT + 1))
    _assert_413(resp)
    assert f"{REQUEST_LIMIT + 1} bytes" in resp.json()["message"]
    assert seen["calls"] == 0


# ── Streamed / chunked bodies (no Content-Length) ─────────────────────────────


async def test_chunked_body_over_limit_is_413_and_not_fully_consumed():
    app, seen = _small_app()
    body = _ChunkedBody(total=REQUEST_LIMIT * 20)
    async with _client(app) as client:
        resp = await client.post("/echo", content=body)
    _assert_413(resp)
    assert "content-length" not in {
        k.lower() for k in resp.request.headers.keys()
    }, "test must exercise a body without Content-Length"
    # The handler started, was cut off at the limit and never completed.
    assert seen["calls"] == 1
    assert seen["completed"] == 0
    assert seen["persisted"] <= REQUEST_LIMIT
    # The client body was not read to the end.
    assert not body.exhausted
    assert body.sent <= REQUEST_LIMIT + CHUNK


async def test_chunked_body_over_limit_for_fastapi_body_param_is_413():
    app, seen = _small_app()
    async with _client(app) as client:
        resp = await client.post(
            "/json",
            content=_ChunkedBody(total=REQUEST_LIMIT * 5),
            headers={"content-type": "application/json"},
        )
    _assert_413(resp)
    assert seen["calls"] == 0


async def test_handler_that_swallows_the_error_still_answers_413():
    app, seen = _small_app()
    async with _client(app) as client:
        resp = await client.post("/swallow", content=_ChunkedBody(REQUEST_LIMIT * 5))
    _assert_413(resp)
    assert seen["calls"] == 1
    assert seen["swallowed"] == 1


# ── Under-limit requests still work ───────────────────────────────────────────


async def test_chunked_body_under_limit_succeeds():
    app, seen = _small_app()
    body = _ChunkedBody(total=REQUEST_LIMIT)  # exactly at the limit
    async with _client(app) as client:
        resp = await client.post("/echo", content=body)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"received": REQUEST_LIMIT}
    assert body.exhausted and seen["completed"] == 1


async def test_normal_requests_under_limit_succeed():
    app, _ = _small_app()
    async with _client(app) as client:
        echo = await client.post("/echo", content=b"x" * 10)
        js = await client.post("/json", json={"a": 1, "b": 2})
    assert echo.status_code == 200 and echo.json() == {"received": 10}
    assert js.status_code == 200 and js.json() == {"keys": 2}


# ── Upload paths use the upload limit ─────────────────────────────────────────


async def test_upload_path_uses_upload_limit():
    app, _ = _small_app()
    between = REQUEST_LIMIT * 3  # over the request limit, under the upload one
    async with _client(app) as client:
        ok = await client.post(
            "/api/v1/document/upload", content=_ChunkedBody(total=between)
        )
        too_big = await client.post(
            "/api/v1/document/upload", content=_ChunkedBody(total=UPLOAD_LIMIT * 2)
        )
        declared = await client.post(
            "/api/v1/document/upload", content=b"x" * (UPLOAD_LIMIT + 1)
        )
        non_upload = await client.post("/echo", content=_ChunkedBody(total=between))
    assert ok.status_code == 200 and ok.json() == {"received": between}
    _assert_413(too_big)
    _assert_413(declared)
    _assert_413(non_upload)


def test_limit_for_path_selection():
    mw = RequestBodySizeLimitMiddleware(
        app=None, max_request_size=REQUEST_LIMIT, max_upload_size=UPLOAD_LIMIT
    )
    assert mw.limit_for("/api/v1/document/upload") == UPLOAD_LIMIT
    assert mw.limit_for("/api/v1/copilot/turn") == REQUEST_LIMIT


# ── Responses are untouched (request-side only) ───────────────────────────────


async def test_streaming_sse_responses_are_unaffected():
    app, _ = _small_app()
    async with _client(app) as client:
        get = await client.get("/events")
        post = await client.post("/events", content=_ChunkedBody(total=10))
    for resp in (get, post):
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        # The response is far larger than the request limit.
        assert len(resp.content) > REQUEST_LIMIT
        assert resp.text.count("data: ") == 50


# ── The shipped app ───────────────────────────────────────────────────────────


@pytest.fixture
def canonical(monkeypatch, tmp_path):
    fake = FakeNIM()
    canonical_env(monkeypatch, tmp_path, fake)
    install_gateway(fake)
    yield
    fake.close()
    from maiw_models import reset_model_gateway

    reset_model_gateway()


def _shipped_limits():
    import maiw_api.app as app_module

    return app_module._MAX_REQUEST_SIZE, app_module._MAX_UPLOAD_SIZE


def test_shipped_app_installs_the_size_middleware_with_env_limits():
    from maiw_api.app import app

    request_limit, upload_limit = _shipped_limits()
    entries = [
        m for m in app.user_middleware if m.cls is RequestBodySizeLimitMiddleware
    ]
    assert len(entries) == 1
    assert entries[0].kwargs == {
        "max_request_size": request_limit,
        "max_upload_size": upload_limit,
    }


async def test_shipped_app_rejects_chunked_oversize_post(canonical):
    request_limit, _ = _shipped_limits()
    body = _ChunkedBody(total=request_limit + 1_000_000, chunk=256 * 1024)
    async with running_canonical_app() as (_, client):
        resp = await client.post(
            "/api/v1/copilot/turn",
            content=body,
            headers={"content-type": "application/json"},
        )
        live = await client.get("/api/v1/live")
    _assert_413(resp)
    assert not body.exhausted
    assert live.status_code == 200


async def test_shipped_app_rejects_declared_oversize_post(canonical):
    request_limit, _ = _shipped_limits()
    async with running_canonical_app() as (_, client):
        resp = await client.post(
            "/api/v1/copilot/turn",
            content=b"x" * (request_limit + 1),
            headers={"content-type": "application/json"},
        )
    _assert_413(resp)


def _no_document_tools():
    """Dependency override: the upload handler must never run in this test."""
    return None


async def test_shipped_upload_path_allows_bodies_between_the_limits(canonical):
    """An 11 MB chunked multipart upload is over the request limit but under
    the upload limit: it is parsed (422 for the missing form field) — not 413.
    The handler never runs, so nothing is persisted."""
    from src.api.routers.document import get_document_tools

    request_limit, upload_limit = _shipped_limits()
    size = request_limit + 1_000_000
    assert size < upload_limit
    boundary = "maiwlimitboundary"
    head = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="a.pdf"\r\n'
        "Content-Type: application/pdf\r\n\r\n"
    ).encode()
    tail = f"\r\n--{boundary}--\r\n".encode()

    async def multipart():
        yield head
        sent = 0
        while sent < size:
            step = min(256 * 1024, size - sent)
            sent += step
            yield b"x" * step
        yield tail

    async with running_canonical_app() as (app, client):
        app.dependency_overrides[get_document_tools] = _no_document_tools
        try:
            resp = await client.post(
                "/api/v1/document/upload",
                content=multipart(),
                headers={"content-type": f"multipart/form-data; boundary={boundary}"},
            )
        finally:
            app.dependency_overrides.pop(get_document_tools, None)
    assert resp.status_code == 422, resp.text
