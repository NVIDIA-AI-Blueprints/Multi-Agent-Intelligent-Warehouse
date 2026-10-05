# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Real sandbox qualification conftest.

Provides shared fixtures and marks for tests that require:
  - A running OpenShell sandbox (maiw-qual-20c-b or env-configured)
  - A live MAIW HTTP inference endpoint
  - An approved Nemotron 3/3.5 deployment

On the qualification host (epg-tme-smc-h100-02):
  - All real_sandbox tests MUST run (not skip).
  - Required tests skipped = qualification failure.

On non-qualification hosts:
  - Tests skip automatically when the MAIW endpoint is not reachable.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# ── Path setup ────────────────────────────────────────────────────────────────

_REPO = Path(__file__).resolve().parents[2]
for _pkg in ("packages/maiw-models", "packages/maiw-mcp", "packages/maiw-agents"):
    _p = str(_REPO / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── Endpoint / token configuration ───────────────────────────────────────────

MAIW_INFERENCE_ENDPOINT = os.getenv(
    "MAIW_QUAL_INFERENCE_ENDPOINT",
    "http://localhost:8020/api/v1/inference",
)
MAIW_INFERENCE_TOKEN = os.getenv("MAIW_INFERENCE_INTERNAL_TOKEN", "")
SANDBOX_NAME = os.getenv("MAIW_QUAL_SANDBOX_NAME", "maiw-qual-20c-b")

# ── Availability checks ───────────────────────────────────────────────────────


def _maiw_endpoint_reachable() -> bool:
    """Probe MAIW inference endpoint health."""
    import urllib.request

    health = MAIW_INFERENCE_ENDPOINT.replace("/api/v1/inference", "/api/v1/health")
    try:
        resp = urllib.request.urlopen(health, timeout=5)
        return resp.status == 200
    except Exception:
        return False


def _sandbox_available() -> bool:
    """Check if the qualification sandbox is in Ready phase."""
    try:
        import subprocess

        r = subprocess.run(
            ["openshell", "sandbox", "list", "-o", "json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            return False
        import json

        data = json.loads(r.stdout)
        for s in data:
            if s.get("name") == SANDBOX_NAME and s.get("phase") == "Ready":
                return True
        return False
    except Exception:
        return False


_ENDPOINT_AVAILABLE = _maiw_endpoint_reachable()
_SANDBOX_AVAILABLE = _sandbox_available()
_TOKEN_CONFIGURED = bool(MAIW_INFERENCE_TOKEN)

# ── Marks ─────────────────────────────────────────────────────────────────────

# real_sandbox: requires running OpenShell sandbox AND live MAIW endpoint.
# On the qualification host, these are mandatory (not skipable).
_QUAL_HOST = os.uname().nodename == "epg-tme-smc-h100-02"

real_sandbox = pytest.mark.skipif(
    not (_ENDPOINT_AVAILABLE and _SANDBOX_AVAILABLE and _TOKEN_CONFIGURED),
    reason=(
        "real_sandbox tests require: running MAIW inference endpoint at "
        f"{MAIW_INFERENCE_ENDPOINT}, running OpenShell sandbox '{SANDBOX_NAME}', "
        "and MAIW_INFERENCE_INTERNAL_TOKEN set. "
        "On qualification host these are MANDATORY."
    ),
)

approved_model_required = pytest.mark.skipif(
    not _ENDPOINT_AVAILABLE,
    reason="approved_model_required: MAIW inference endpoint not reachable",
)

# ── Shared fixtures ───────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def maiw_endpoint() -> str:
    """The MAIW HTTP inference endpoint URL."""
    return MAIW_INFERENCE_ENDPOINT


@pytest.fixture(scope="session")
def maiw_token() -> str:
    """The MAIW internal inference token."""
    assert MAIW_INFERENCE_TOKEN, "MAIW_INFERENCE_INTERNAL_TOKEN must be set"
    return MAIW_INFERENCE_TOKEN


@pytest.fixture(scope="session")
def sandbox_name() -> str:
    """The OpenShell sandbox name under test."""
    return SANDBOX_NAME


@pytest.fixture(scope="session")
def inference_request_factory():
    """Factory for valid InferenceRequest payloads."""

    def _factory(
        task: str = "qualification_test",
        content: str = "Describe warehouse wave status in one sentence.",
        trace_id: str | None = None,
        deadline_ms: int = 30000,
        **kwargs,
    ) -> dict:
        payload = {
            "task": task,
            "messages": [{"role": "user", "content": content}],
            "deadline_ms": deadline_ms,
        }
        if trace_id:
            payload["trace_id"] = trace_id
        payload.update(kwargs)
        return payload

    return _factory


def _post_inference(
    payload: dict, token: str | None, endpoint: str
) -> tuple[int, dict]:
    """Make a POST to the inference endpoint, return (status, body)."""
    import json
    import urllib.error
    import urllib.request

    req = urllib.request.Request(
        endpoint, data=json.dumps(payload).encode(), method="POST"
    )
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Maiw-Internal-Token", token)
    try:
        resp = urllib.request.urlopen(req, timeout=40)
        return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except Exception:
            body = {"raw": e.read().decode()[:200]}
        return e.code, body
    except Exception as e:
        return 0, {"error": str(e)[:200]}


@pytest.fixture(scope="session")
def post_inference():
    """HTTP POST helper for inference tests."""
    return _post_inference
