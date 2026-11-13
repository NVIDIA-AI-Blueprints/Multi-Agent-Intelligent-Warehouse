# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""The canonical API reports one version, the build's, everywhere.

Before, ``GET /`` and the OpenAPI document said ``0.1.0`` (the
``MAIW_APP_VERSION`` default) while ``/api/v1/version`` said something else.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_root_openapi_and_version_endpoint_agree(monkeypatch):
    monkeypatch.delenv("MAIW_APP_VERSION", raising=False)
    from maiw_api.app import app
    from maiw_api.config import settings
    from src.api.services.version import version_service

    client = TestClient(app)
    root = client.get("/").json()
    version = client.get("/api/v1/version").json()
    detailed = client.get("/api/v1/version/detailed").json()

    expected = version_service.version
    assert expected != "0.1.0"
    assert settings.app_version == expected
    assert root["version"] == expected
    assert app.version == expected
    assert client.get("/openapi.json").json()["info"]["version"] == expected
    assert version["version"] == detailed["version"] == expected
    assert version["commit"] == detailed["commit"] == version_service.commit
    assert version["build"] in {"release", "development", "declared", "unknown"}


def test_explicit_version_still_overrides(monkeypatch):
    from maiw_api.config import settings

    monkeypatch.setenv("MAIW_APP_VERSION", "2.2.0-rc.1")
    assert settings.app_version == "2.2.0-rc.1"


def test_compose_and_image_carry_the_build_identity():
    dockerfile = (REPO_ROOT / "Dockerfile.backend").read_text()
    assert "ARG MAIW_BUILD_DESCRIBE=" in dockerfile
    assert "ENV MAIW_BUILD_DESCRIBE=$MAIW_BUILD_DESCRIBE" in dockerfile
    compose = yaml.safe_load(
        (REPO_ROOT / "deploy/compose/docker-compose.dev.yaml").read_text()
    )
    assert compose["services"]["backend"]["build"]["args"] == {
        "MAIW_BUILD_DESCRIBE": "${MAIW_BUILD_DESCRIBE:-}",
        "GIT_SHA": "${GIT_SHA:-unknown}",
    }
    dev_up = (REPO_ROOT / "scripts/setup/dev_up.sh").read_text()
    assert "export MAIW_BUILD_DESCRIBE GIT_SHA" in dev_up
    assert dev_up.index("export MAIW_BUILD_DESCRIBE GIT_SHA") < dev_up.index(
        "docker-compose.dev.yaml up -d"
    )


def test_deploy_test_checks_the_reported_commit():
    workflow = yaml.safe_load((REPO_ROOT / ".github/workflows/main.yml").read_text())
    steps = {s["name"]: s for s in workflow["jobs"]["deploy-and-test"]["steps"]}
    run = steps["Verify: /api/v1/version identifies this build"]["run"]
    assert 'expected="$(git rev-parse HEAD)"' in run
    assert 'body["commit"] == expected' in run
