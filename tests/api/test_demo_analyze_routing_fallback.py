# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
RUN MAIW ANALYSIS reports a routing fallback (follow-up to #317).

HIGH reasoning prefers Super, which is disabled by default since hosted Super
was retired, so the router falls back to Ultra. ``POST /api/v1/demo/analyze``
returned only ``routing_reason`` ("reasoning=HIGH requires Super"), which
names the preferred role, next to the Ultra ``model_id``. The router's
``fallback_from`` and ``fallback_reason`` were on the assessment but not in
the response, so the trace and the UI showed a reason for a model that did
not serve the request. Both fields are now in the assessment and in the
REASON lifecycle record.
"""

from __future__ import annotations

import json
import secrets

import pytest

from tests.api.canonical_harness import (
    FakeNIM,
    canonical_env,
    install_gateway,
    running_canonical_app,
)

SCENARIO = "healthy_baseline"
ROLE_FLAGS = (
    "NEMOTRON_LIGHTNING_ENABLED",
    "NEMOTRON_NANO_ENABLED",
    "NEMOTRON_SUPER_ENABLED",
    "NEMOTRON_ULTRA_ENABLED",
)


@pytest.fixture
def fake_nim():
    fake = FakeNIM(
        content=json.dumps({"summary": "Nothing to do", "recommendations": []})
    )
    yield fake
    fake.close()


@pytest.fixture
def demo_app_env(monkeypatch, tmp_path, fake_nim):
    import maiw_api.bootstrap as bootstrap
    from maiw_api.demo.controller import reset_demo_controller

    canonical_env(monkeypatch, tmp_path, fake_nim)
    for flag in ROLE_FLAGS:  # the shipped defaults: Super off, Ultra on
        monkeypatch.delenv(flag, raising=False)
    monkeypatch.setenv("MAIW_DEMO_MODE", "true")
    monkeypatch.setenv("MAIW_DEPLOYMENT_PROFILE", "demo")
    monkeypatch.setenv("MAIW_OPERATOR_WRITE_TOKEN", secrets.token_hex(32))
    monkeypatch.setattr(bootstrap, "_DEMO_MODE", True)
    reset_demo_controller()
    install_gateway(fake_nim)
    yield
    from maiw_models import reset_model_gateway

    reset_model_gateway()
    reset_demo_controller()


async def test_analyze_reports_the_fallback_from_super_to_ultra(demo_app_env):
    async with running_canonical_app() as (_app, client):
        r = await client.post(f"/api/v1/demo/scenario/{SCENARIO}/start")
        assert r.status_code == 200, r.text
        r = await client.post("/api/v1/demo/analyze")
        assert r.status_code == 200, r.text
        body = r.json()

    assessment = body["assessment"]
    assert "ultra" in assessment["model_id"]
    assert assessment["routing_rule"] == "high_reasoning"
    assert assessment["fallback_from"] == "super"
    assert "escalated to ultra" in assessment["fallback_reason"]

    # The first REASON record only marks the call start; the second has the route.
    (reason,) = [
        l for l in body["lifecycle"] if l["phase"] == "REASON" and "model_id" in l
    ]
    assert reason["fallback_from"] == "super"
    assert reason["fallback_reason"] == assessment["fallback_reason"]
