# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
The shipped API on its supported deployment: a single trusted host.

Binding to 127.0.0.1 keeps other machines out, but not a web page that an
operator on that host opens in a browser. CORS stops such a page from READING
API responses; it does not stop the browser from SENDING a "simple" request
(multipart form, text/plain, or a body with no Content-Type, which FastAPI
parses as JSON). These tests drive the shipped app the way a browser on
another origin would, and check that:

- a cross-origin write is refused before it reaches any route, while the UI's
  own origins, same-origin loopback pages (/docs) and non-browser clients
  (no Origin header) still work;
- the Copilot route and the other shipped 5xx paths do not return raw
  exception text.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.api.canonical_harness import (
    FakeNIM,
    canonical_env,
    install_gateway,
    running_canonical_app,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

UPLOAD = "/api/v1/document/upload"
ASSIGN = "/api/v1/equipment/assign"


@pytest.fixture
def canonical(monkeypatch, tmp_path):
    fake = FakeNIM()
    canonical_env(monkeypatch, tmp_path, fake)
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    install_gateway(fake)
    # The upload route writes to data/uploads relative to the working dir.
    monkeypatch.chdir(tmp_path)
    yield
    fake.close()
    from maiw_models import reset_model_gateway

    reset_model_gateway()


class _RecordingDocumentTools:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.processing: list[str] = []

    async def upload_document(self, **kwargs):
        self.calls.append(kwargs)
        return {"success": True, "document_id": "doc-1"}


@pytest.fixture
def document_tools(monkeypatch):
    """Record uploads and the processing they start, instead of running the pipeline."""
    import src.api.routers.document as document_router
    import src.api.services.document as document_services
    from maiw_api.app import app

    tools = _RecordingDocumentTools()

    async def no_job_queue():
        raise RuntimeError("job queue disabled in this test")

    async def record_processing(document_id, *_):
        tools.processing.append(document_id)

    monkeypatch.setattr(document_services, "get_job_queue", no_job_queue)
    monkeypatch.setattr(
        document_router, "process_document_background", record_processing
    )
    app.dependency_overrides[document_router.get_document_tools] = lambda: tools
    yield tools
    app.dependency_overrides.pop(document_router.get_document_tools, None)


def _upload_form():
    return {
        "files": {"file": ("invoice.pdf", b"%PDF-1.4 test", "application/pdf")},
        "data": {"document_type": "invoice"},
    }


def _assert_cross_origin_refused(resp):
    assert resp.status_code == 403, resp.text
    assert resp.json()["error"] == "CROSS_ORIGIN_REQUEST_FORBIDDEN"


# ── Cross-origin writes ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "origin",
    [
        "http://evil.example",
        "https://localhost.evil.example",
        "http://localhost:4000",  # loopback, but not the UI and not this host
        "null",  # sandboxed iframe, file:// page, opaque redirect
    ],
)
async def test_cross_origin_upload_is_refused_before_the_route(
    canonical, document_tools, origin
):
    async with running_canonical_app() as (_, client):
        resp = await client.post(UPLOAD, headers={"Origin": origin}, **_upload_form())
    _assert_cross_origin_refused(resp)
    assert document_tools.calls == []
    assert document_tools.processing == []
    assert not Path("data/uploads").exists()


@pytest.mark.parametrize(
    "headers",
    [
        {},  # curl, scripts, tests: no Origin header
        {"Origin": "http://localhost:3001"},  # npm start UI (and SSH tunnel)
        {"Origin": "http://127.0.0.1:3000"},  # nginx in Compose
    ],
)
async def test_upload_from_ui_or_non_browser_client_is_accepted(
    canonical, document_tools, headers
):
    async with running_canonical_app() as (_, client):
        resp = await client.post(UPLOAD, headers=headers, **_upload_form())
    assert resp.status_code == 200, resp.text
    assert len(document_tools.calls) == 1
    assert document_tools.processing == [resp.json()["document_id"]]


async def test_same_origin_loopback_page_is_accepted(canonical, document_tools):
    # The API's own /docs page posts with Origin == its own origin.
    async with running_canonical_app() as (_, client):
        resp = await client.post(
            UPLOAD,
            headers={"Origin": "http://localhost:8001", "Host": "localhost:8001"},
            **_upload_form(),
        )
    assert resp.status_code == 200, resp.text


async def test_dns_rebinding_same_origin_is_refused(canonical, document_tools):
    # A rebound name makes Origin and Host agree, but the host is not loopback.
    async with running_canonical_app() as (_, client):
        resp = await client.post(
            UPLOAD,
            headers={
                "Origin": "http://rebind.evil.example:8001",
                "Host": "rebind.evil.example:8001",
            },
            **_upload_form(),
        )
    _assert_cross_origin_refused(resp)
    assert document_tools.calls == []


def _guarded_app(allowed_origins):
    from fastapi import FastAPI

    from maiw_api.origin_guard import CrossOriginWriteGuardMiddleware

    app = FastAPI()

    @app.post("/write")
    async def write():
        return {"ok": True}

    app.add_middleware(CrossOriginWriteGuardMiddleware, allowed_origins=allowed_origins)
    return app


async def _post_write(app, origin):
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://localhost:8001"
    ) as client:
        return await client.post("/write", headers={"Origin": origin})


async def test_operator_configured_origin_is_accepted():
    # The shipped app passes its CORS_ORIGINS list; setting it replaces the
    # localhost defaults for this check exactly as it does for CORS.
    app = _guarded_app(["https://console.internal.example/"])
    ok = await _post_write(app, "https://Console.Internal.Example")
    default_ui = await _post_write(app, "http://localhost:3001")
    assert ok.status_code == 200, ok.text
    _assert_cross_origin_refused(default_ui)


async def test_wildcard_cors_origins_disables_the_guard():
    app = _guarded_app(["*"])
    assert (await _post_write(app, "http://evil.example")).status_code == 200


async def test_cross_origin_json_without_content_type_is_refused(
    canonical, monkeypatch
):
    # fetch(url, {method: "POST", mode: "no-cors", body: new Blob([json])})
    # sends no Content-Type, needs no preflight, and FastAPI parses the body
    # as JSON. Through `npm start` with MAIW_UI_OPERATOR_WRITE_TOKEN set, the
    # dev proxy would add the operator credential to this request.
    token = "operator-token-for-this-test-only-0123456789"
    monkeypatch.setenv("MAIW_OPERATOR_WRITE_TOKEN", token)
    body = b'{"asset_id": "FL-01", "assignee": "worker-1"}'
    async with running_canonical_app() as (_, client):
        resp = await client.post(
            ASSIGN,
            content=body,
            headers={
                "Origin": "http://evil.example",
                "X-Maiw-Operator-Token": token,
            },
        )
    _assert_cross_origin_refused(resp)


async def test_cross_origin_reads_and_preflight_are_unchanged(canonical):
    async with running_canonical_app() as (_, client):
        read = await client.get(
            "/api/v1/health", headers={"Origin": "http://evil.example"}
        )
        preflight = await client.options(
            UPLOAD,
            headers={
                "Origin": "http://localhost:3001",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert read.status_code == 200
    # CORS still withholds the response from the other origin.
    assert "access-control-allow-origin" not in read.headers
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:3001"


# ── Raw exception text ────────────────────────────────────────────────────────

_SECRET = "postgresql://warehouse:s3cret@db.internal:5432/warehouse"


class _FailingCopilot:
    async def ask(self, **_):
        raise RuntimeError(f"connection failed: {_SECRET}")


async def test_copilot_unexpected_error_does_not_return_exception_text(
    canonical, monkeypatch
):
    async with running_canonical_app() as (app, client):
        monkeypatch.setattr(
            app.state, "runtime", SimpleNamespace(copilot_service=_FailingCopilot())
        )
        resp = await client.post(
            "/api/v1/copilot/turn",
            json={"message": "what is the status of FL-01?"},
        )
    assert resp.status_code == 500
    assert "s3cret" not in resp.text
    assert "db.internal" not in resp.text
    assert "Copilot turn failed" in resp.text


def _server_errors_with_exception_text(path: Path) -> list[str]:
    """HTTPException(status_code>=500, detail=...) whose detail uses the caught exception."""
    tree = ast.parse(path.read_text(), filename=str(path))
    found = []
    for handler in ast.walk(tree):
        if not isinstance(handler, ast.ExceptHandler) or not handler.name:
            continue
        for node in ast.walk(handler):
            if not (
                isinstance(node, ast.Call)
                and getattr(node.func, "id", None) == "HTTPException"
            ):
                continue
            kw = {k.arg: k.value for k in node.keywords}
            status = kw.get("status_code")
            detail = kw.get("detail")
            if not (isinstance(status, ast.Constant) and status.value >= 500):
                continue
            if detail is not None and any(
                isinstance(n, ast.Name) and n.id == handler.name
                for n in ast.walk(detail)
            ):
                found.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
    return found


def test_shipped_routers_do_not_return_exception_text_in_server_errors():
    routers = REPO_ROOT / "apps" / "api" / "maiw_api" / "routers"
    offenders = [
        hit
        for path in sorted(routers.glob("*.py"))
        for hit in _server_errors_with_exception_text(path)
    ]
    assert offenders == []
