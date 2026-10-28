"""
Compose deployment readiness guards.

Static checks so the Compose deployment (deploy/compose/docker-compose.dev.yaml,
exercised by .github/workflows/main.yml) keeps durable state, can reach its
database, and is gated on /api/v1/ready rather than liveness alone.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "deploy/compose/docker-compose.dev.yaml"
WORKFLOW = REPO_ROOT / ".github/workflows/main.yml"


def _backend_service() -> dict:
    return yaml.safe_load(COMPOSE.read_text())["services"]["backend"]


def _steps() -> dict[str, dict]:
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    return {s.get("name", ""): s for job in jobs.values() for s in job["steps"]}


def test_backend_image_creates_persistence_root_owned_by_appuser():
    # maiw_api.persistence defaults MAIW_PERSISTENCE_ROOT to /var/lib/maiw; the
    # image runs as appuser, which cannot create it at runtime (EACCES).
    text = (REPO_ROOT / "Dockerfile.backend").read_text()
    user_at = text.index("\nUSER appuser")
    setup = text[:user_at]
    assert "mkdir -p /var/lib/maiw" in setup
    assert re.search(r"chown -R appuser:appuser[^\n]*/var/lib/maiw", setup)


def test_compose_backend_mounts_durable_state_volume():
    backend = _backend_service()
    assert "maiw_state:/var/lib/maiw" in backend.get("volumes", [])
    assert "maiw_state" in yaml.safe_load(COMPOSE.read_text())["volumes"]


def test_compose_backend_data_path_targets_timescaledb():
    # The SQL data path and /api/v1/ready read PGHOST/PGPORT (default
    # localhost:5435), not DB_HOST/DB_PORT.
    env = _backend_service()["environment"]
    assert "PGHOST=timescaledb" in env
    assert "PGPORT=5432" in env


def test_deploy_workflow_gates_on_ready_endpoint():
    run = _steps()["Verify: API health checks"]["run"]
    assert "http://localhost:8001/api/v1/ready" in run
    assert re.search(r'if \[ "\$ready_code" != "200" \]; then.*?exit 1', run, re.S)


def test_deploy_workflow_maiw_pytest_is_blocking_and_skip_is_reported():
    steps = _steps()
    pytest_step = steps["Post-deploy: Run MAIW pytest (pytest -m maiw)"]
    assert "continue-on-error" not in pytest_step
    run = pytest_step["run"]
    assert run.count('echo "E2E=NOT_RUN" >> "$GITHUB_OUTPUT"') == 2
    assert 'exit "$PYTEST_EXIT"' in run
    result = steps["Set result output"]["run"]
    assert "steps.maiw_pytest.outputs.E2E" in result
    assert "NOT RUN" in result
