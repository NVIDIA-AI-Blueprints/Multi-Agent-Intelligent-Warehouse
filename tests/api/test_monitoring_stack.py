# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
The bundled monitoring stack can monitor the shipped API (#277).

Before: the Compose file mounted ``./monitoring/...``, which resolves to the
non-existent ``deploy/compose/monitoring/...``, so Prometheus, Grafana and
Alertmanager started without their configuration. Prometheus scraped
``localhost:8001`` from inside its own container and pointed the postgres,
redis and milvus jobs at service ports instead of exporters. The dashboards
were wrapped in the HTTP-API ``{"dashboard": ...}`` envelope that file
provisioning does not read, and most of their panels and three alert rules
queried ``warehouse_*`` business metrics the shipped app never sets. Images
were ``:latest``, Grafana fell back to the admin password ``changeme`` and
published 127.0.0.1:3000, which the dev stack's nginx already uses, and
``warehouse_system_info`` claimed version 1.0.0.

The live check (Prometheus reports ``up{job="warehouse-api"} == 1``) runs in
the deployment test, .github/workflows/main.yml; these tests pin the static
contract.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml
from prometheus_client import REGISTRY

from src.api.services.monitoring import metrics as metrics_module
from tests.api.canonical_harness import (
    FakeNIM,
    canonical_env,
    install_gateway,
    running_canonical_app,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_DIR = REPO_ROOT / "deploy/compose"
MONITORING_COMPOSE = COMPOSE_DIR / "docker-compose.monitoring.yaml"
DEV_COMPOSE = COMPOSE_DIR / "docker-compose.dev.yaml"
PROMETHEUS = REPO_ROOT / "monitoring/prometheus/prometheus.yml"
RULES = REPO_ROOT / "monitoring/prometheus/rules/warehouse-alerts.yml"
DASHBOARDS = REPO_ROOT / "monitoring/grafana/dashboards"

# Metric families the stack can actually see: the API's own metrics, the
# Prometheus `up` series and the exporters it runs.
KNOWN_METRIC_PREFIXES = (
    "http_requests_total",
    "http_request_duration_seconds",
    "warehouse_system_info",
    "up",
    "pg_",
    "redis_",
    "node_",
    "container_",
)
PROMQL_WORDS = {
    "sum",
    "max",
    "min",
    "avg",
    "rate",
    "increase",
    "histogram_quantile",
    "topk",
    "by",
    "and",
    "or",
    "le",
    "endpoint",
    "status",
    "instance",
    "mode",
    "job",
    "fstype",
}


@pytest.fixture
def canonical(monkeypatch, tmp_path):
    fake = FakeNIM()
    canonical_env(monkeypatch, tmp_path, fake)
    install_gateway(fake)
    yield
    fake.close()
    from maiw_models import reset_model_gateway

    reset_model_gateway()


def _compose() -> dict:
    return yaml.safe_load(MONITORING_COMPOSE.read_text())


def _metric_names(expr: str) -> set[str]:
    without_selectors = re.sub(r"\{[^}]*\}", "", expr)
    without_ranges = re.sub(r"\[[^\]]*\]", "", without_selectors)
    tokens = set(re.findall(r"[A-Za-z_:][A-Za-z0-9_:]*", without_ranges))
    return {t for t in tokens if t not in PROMQL_WORDS}


def _dashboard_exprs() -> list[tuple[str, str]]:
    exprs = []
    for path in sorted(DASHBOARDS.glob("*.json")):
        data = json.loads(path.read_text())
        # Read the old HTTP-API envelope too, so the format test reports it.
        dashboard = data.get("dashboard", data)
        for panel in dashboard["panels"]:
            for target in panel.get("targets", []):
                exprs.append((path.name, target["expr"]))
    return exprs


def _rule_exprs() -> list[tuple[str, str]]:
    rules = yaml.safe_load(RULES.read_text())
    return [
        (rule["alert"], rule["expr"])
        for group in rules["groups"]
        for rule in group["rules"]
    ]


# ── Compose file ──────────────────────────────────────────────────────────────


def test_every_bind_mount_resolves_to_a_file_in_the_repo():
    for name, service in _compose()["services"].items():
        for volume in service.get("volumes", []):
            source = volume.split(":", 1)[0]
            if source.startswith("."):
                resolved = (COMPOSE_DIR / source).resolve()
                assert resolved.exists(), (name, source, resolved)
                assert REPO_ROOT in resolved.parents, (name, source)


def test_every_image_is_pinned_by_tag_and_digest():
    for name, service in _compose()["services"].items():
        image = service["image"]
        assert re.fullmatch(r"[^:@\s]+:[^:@\s]+@sha256:[0-9a-f]{64}", image), (
            name,
            image,
        )
        assert ":latest" not in image, (name, image)


def test_grafana_has_no_default_password_and_avoids_the_nginx_port():
    grafana = _compose()["services"]["grafana"]
    env = "\n".join(grafana["environment"])
    assert "changeme" not in MONITORING_COMPOSE.read_text()
    assert "GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD:?" in env
    (port,) = grafana["ports"]
    assert port.startswith("127.0.0.1:")
    assert ":3000:" not in port.replace("127.0.0.1", "")
    assert "MAIW_GRAFANA_PORT" in port


def test_published_ports_bind_to_loopback():
    for name, service in _compose()["services"].items():
        for port in service.get("ports", []):
            assert port.startswith("127.0.0.1:"), (name, port)


def test_prometheus_and_db_exporters_join_the_dev_stack_network():
    compose = _compose()
    network = compose["networks"]["maiw"]
    assert network["external"] is True
    assert network["name"] == "${MAIW_COMPOSE_NETWORK:-compose_default}"
    for name in ("prometheus", "postgres-exporter", "redis-exporter"):
        assert "maiw" in compose["services"][name]["networks"], name


def test_monitoring_is_its_own_compose_project():
    """Both Compose files live in deploy/compose, so without an explicit name
    they share the project `compose`, and `down --remove-orphans` from the
    monitoring file removed the whole dev stack (deployment test on b1f1d11)."""
    name = _compose().get("name")
    assert name == "maiw-monitoring"
    assert name != yaml.safe_load(DEV_COMPOSE.read_text()).get("name", "compose")


def test_deployment_check_never_removes_other_projects_containers():
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/main.yml").read_text())
    (step,) = [
        s
        for s in workflow["jobs"]["deploy-and-test"]["steps"]
        if s.get("name") == "Verify: monitoring stack scrapes the API"
    ]
    assert "--remove-orphans" not in step["run"]
    assert "docker-compose.monitoring.yaml" in step["run"]


# ── Prometheus scrape configuration ──────────────────────────────────────────


def test_scrape_targets_are_reachable_service_names():
    dev_services = set(yaml.safe_load(DEV_COMPOSE.read_text())["services"])
    monitoring_services = set(_compose()["services"])
    config = yaml.safe_load(PROMETHEUS.read_text())
    jobs = {job["job_name"]: job for job in config["scrape_configs"]}

    assert jobs["warehouse-api"]["static_configs"][0]["targets"] == ["backend:8001"]
    assert jobs["warehouse-api"]["metrics_path"] == "/api/v1/metrics"
    assert jobs["postgres"]["static_configs"][0]["targets"] == [
        "postgres-exporter:9187"
    ]
    assert jobs["redis"]["static_configs"][0]["targets"] == ["redis-exporter:9121"]

    for name, job in jobs.items():
        for target in job["static_configs"][0]["targets"]:
            host = target.split(":")[0]
            if name == "prometheus":
                assert host == "localhost"
                continue
            assert host in dev_services | monitoring_services, (name, target)


# ── Dashboards and alert rules ───────────────────────────────────────────────


def test_dashboards_are_in_file_provisioning_format():
    files = sorted(DASHBOARDS.glob("*.json"))
    assert [f.name for f in files] == ["warehouse-overview.json"]
    for path in files:
        dashboard = json.loads(path.read_text())
        assert "dashboard" not in dashboard, path.name
        assert dashboard["uid"] and dashboard["title"]
        for panel in dashboard["panels"]:
            assert panel["type"] in {"stat", "timeseries"}, (path.name, panel)


@pytest.mark.parametrize(
    "source, expr", _dashboard_exprs() + _rule_exprs(), ids=lambda v: str(v)[:60]
)
def test_every_query_uses_a_metric_the_stack_produces(source, expr):
    for metric in _metric_names(expr):
        assert metric.startswith(KNOWN_METRIC_PREFIXES), (source, metric, expr)


def test_business_alerts_are_gone():
    alerts = {name for name, _ in _rule_exprs()}
    assert not alerts & {
        "HighInventoryAlerts",
        "SafetyIncidentDetected",
        "LowTaskCompletionRate",
    }
    assert {"APIDown", "APIHighErrorRate", "APIHighLatency"} <= alerts


def test_alertmanager_sends_nothing_by_default():
    config = yaml.safe_load(
        (REPO_ROOT / "monitoring/alertmanager/alertmanager.yml").read_text()
    )
    assert config["route"]["receiver"] == "default"
    assert config["receivers"] == [{"name": "default"}]
    assert "global" not in config


# ── What the API exports ─────────────────────────────────────────────────────


def test_no_business_metrics_are_defined():
    names = {
        collector._name
        for collector in vars(metrics_module).values()
        if hasattr(collector, "_name") and hasattr(collector, "collect")
    }
    assert names == {
        "http_requests",
        "http_request_duration_seconds",
        "warehouse_system_info",
    }
    assert not (REPO_ROOT / "src/api/services/monitoring/sample_metrics.py").exists()


async def test_system_info_reports_the_release_version(canonical, monkeypatch):
    from src.api.services.version import version_service

    monkeypatch.setitem(metrics_module._system_info_state, "set", False)
    monkeypatch.setattr(
        version_service,
        "get_version_info",
        lambda: {
            "version": "9.8.7",
            "git_sha": "abc1234",
            "environment": "test",
            "build_time": "x",
        },
    )
    async with running_canonical_app() as (_, client):
        resp = await client.get("/api/v1/metrics")
    assert resp.status_code == 200
    labels = {
        "version": "9.8.7",
        "git_sha": "abc1234",
        "service": "maiw-api",
        "environment": "test",
    }
    assert REGISTRY.get_sample_value("warehouse_system_info_info", labels) == 1.0
    assert 'version="1.0.0"' not in resp.text


async def test_system_info_survives_a_version_lookup_failure(canonical, monkeypatch):
    from src.api.services.version import version_service

    def boom():
        raise RuntimeError("git not available")

    monkeypatch.setitem(metrics_module._system_info_state, "set", False)
    monkeypatch.setattr(version_service, "get_version_info", boom)
    async with running_canonical_app() as (_, client):
        resp = await client.get("/api/v1/metrics")
    assert resp.status_code == 200
    assert 'version="unknown"' in resp.text
