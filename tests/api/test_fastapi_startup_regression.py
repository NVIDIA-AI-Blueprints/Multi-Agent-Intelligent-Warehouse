# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Startup regression — ``maiw_api.app:app`` must construct and serve with the
FastAPI that is actually installed.

``FastAPI(..., max_request_size=...)`` was never a FastAPI parameter: up to
0.143 it was swallowed by ``**extra`` (and enforced nothing); FastAPI 0.162
removed ``**extra``, so every fresh deployment died at import with
``TypeError: FastAPI.__init__() got an unexpected keyword argument
'max_request_size'``.  These tests import the app in a clean interpreter and
serve a request through it, so any constructor/middleware incompatibility
with a new FastAPI/Starlette fails CI instead of the deployment.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import fastapi
import pytest
import starlette
from fastapi.testclient import TestClient

from tests.api.canonical_harness import (
    FakeNIM,
    canonical_env,
    install_gateway,
    running_canonical_app,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def canonical(monkeypatch, tmp_path):
    fake = FakeNIM()
    canonical_env(monkeypatch, tmp_path, fake)
    install_gateway(fake)
    yield
    fake.close()
    from maiw_models import reset_model_gateway

    reset_model_gateway()


def test_app_module_imports_in_a_fresh_interpreter():
    """A clean ``import maiw_api.app`` (as uvicorn does) must not raise."""
    env = dict(os.environ)
    env.setdefault(
        "DATABASE_URL", "postgresql://warehouse:ci_placeholder@127.0.0.1:1/warehouse"
    )
    env["PYTHON_DOTENV_DISABLED"] = "1"
    code = (
        "import fastapi, maiw_api.app as m; "
        "assert isinstance(m.app, fastapi.FastAPI); "
        "print(fastapi.__version__)"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-4000:]
    assert proc.stdout.strip() == fastapi.__version__


def test_app_serves_live_with_installed_fastapi(canonical):
    """TestClient (no lifespan run) against the shipped app object: /live is 200."""
    from maiw_api.app import app

    with_versions = f"fastapi {fastapi.__version__} / starlette {starlette.__version__}"
    client = TestClient(app)
    resp = client.get("/api/v1/live")
    assert resp.status_code == 200, with_versions
    assert resp.json()["status"] == "alive"


async def test_app_starts_with_real_lifespan_and_serves_live(canonical):
    """Real lifespan start + shutdown with the installed FastAPI/Starlette."""
    async with running_canonical_app() as (_, client):
        live = await client.get("/api/v1/live")
        version = await client.get("/api/v1/version")
    assert live.status_code == 200
    assert version.status_code == 200
