# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
The shipped app records and serves HTTP request metrics (#274).

``metrics_middleware`` called ``record_request_metrics(method=..., path=...,
status_code=..., duration=...)``, but the function takes ``(request, response,
duration)``. Every call raised ``TypeError``, which ``except Exception: pass``
swallowed, so ``http_requests_total`` and ``http_request_duration_seconds``
were never recorded; the app also served no ``/api/v1/metrics``.

Now the middleware passes the request and response, labels by route template
(one series per route, not per ID in the URL; ``unmatched`` for 404s), logs a
recording failure instead of hiding it, and ``GET /api/v1/metrics`` serves the
registry. Nothing is patched: these read the real Prometheus registry.
"""

from __future__ import annotations

import logging
import uuid

import pytest
from prometheus_client import REGISTRY

from src.api.services.monitoring import metrics as metrics_module
from tests.api.canonical_harness import (
    FakeNIM,
    canonical_env,
    install_gateway,
    running_canonical_app,
)

PROCEDURE_ROUTE = "/api/v1/procedures/{procedure_id}"


@pytest.fixture
def canonical(monkeypatch, tmp_path):
    fake = FakeNIM()
    canonical_env(monkeypatch, tmp_path, fake)
    install_gateway(fake)
    yield
    fake.close()
    from maiw_models import reset_model_gateway

    reset_model_gateway()


def _count(method: str, endpoint: str, status: str) -> float:
    value = REGISTRY.get_sample_value(
        "http_requests_total",
        {"method": method, "endpoint": endpoint, "status": status},
    )
    return value or 0.0


def _observations(method: str, endpoint: str) -> float:
    value = REGISTRY.get_sample_value(
        "http_request_duration_seconds_count",
        {"method": method, "endpoint": endpoint},
    )
    return value or 0.0


def _endpoints_seen() -> set[str]:
    return {
        sample.labels["endpoint"]
        for family in REGISTRY.collect()
        if family.name == "http_requests"
        for sample in family.samples
        if sample.name == "http_requests_total"
    }


async def test_request_increments_counter_and_latency_histogram(canonical):
    before = _count("GET", "/api/v1/live", "200")
    observed = _observations("GET", "/api/v1/live")
    async with running_canonical_app() as (_, client):
        resp = await client.get("/api/v1/live")
    assert resp.status_code == 200
    assert _count("GET", "/api/v1/live", "200") == before + 1
    assert _observations("GET", "/api/v1/live") == observed + 1


async def test_path_parameters_share_one_route_template_label(canonical):
    ids = [f"metrics-{uuid.uuid4().hex}" for _ in range(2)]
    before = _count("GET", PROCEDURE_ROUTE, "404")
    async with running_canonical_app() as (_, client):
        for procedure_id in ids:
            resp = await client.get(f"/api/v1/procedures/{procedure_id}")
            assert resp.status_code == 404
    assert _count("GET", PROCEDURE_ROUTE, "404") == before + 2
    seen = _endpoints_seen()
    assert not any(procedure_id in label for label in seen for procedure_id in ids)


async def test_unknown_path_uses_the_unmatched_label(canonical):
    path = f"/no/such/route/{uuid.uuid4().hex}"
    before = _count("GET", "unmatched", "404")
    async with running_canonical_app() as (_, client):
        resp = await client.get(path)
    assert resp.status_code == 404
    assert _count("GET", "unmatched", "404") == before + 1
    assert path not in _endpoints_seen()


async def test_metrics_endpoint_serves_the_http_series(canonical):
    async with running_canonical_app() as (_, client):
        await client.get("/api/v1/live")
        resp = await client.get("/api/v1/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    assert "# TYPE http_requests_total counter" in body
    assert "# TYPE http_request_duration_seconds histogram" in body
    assert 'endpoint="/api/v1/live"' in body


async def test_recording_failure_keeps_the_response_and_is_logged(
    canonical, monkeypatch, caplog
):
    import maiw_api.app as app_module

    def broken(*args, **kwargs):
        raise RuntimeError("collector down")

    monkeypatch.setattr(app_module, "record_request_metrics", broken)
    monkeypatch.setitem(app_module._metrics_failure_state, "logged", False)
    with caplog.at_level(logging.DEBUG, logger="maiw_api.app"):
        async with running_canonical_app() as (_, client):
            first = await client.get("/api/v1/live")
            second = await client.get("/api/v1/live")
    assert first.status_code == second.status_code == 200
    records = [
        r
        for r in caplog.records
        if r.getMessage() == "HTTP request metrics not recorded"
    ]
    assert [r.levelno for r in records] == [logging.WARNING, logging.DEBUG]
    assert "collector down" in caplog.text


def test_endpoint_label_falls_back_without_a_route():
    class _Request:
        scope: dict = {}

    assert metrics_module.endpoint_label(_Request()) == "unmatched"
