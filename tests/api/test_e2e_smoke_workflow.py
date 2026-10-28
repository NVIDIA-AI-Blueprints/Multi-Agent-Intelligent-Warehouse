"""
Public e2e smoke + durability guards for the Compose deployment workflow.

The live checks run in .github/workflows/main.yml via
scripts/testing/smoke_e2e.py; these static checks keep the wiring they depend
on (Compose env, profile, workflow steps) from silently regressing.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "deploy/compose/docker-compose.dev.yaml"
WORKFLOW = REPO_ROOT / ".github/workflows/main.yml"
PORTS = {"inventory": 8765, "equipment": 8766, "labor": 8767, "wave": 8768}


def _services() -> dict:
    return yaml.safe_load(COMPOSE.read_text())["services"]


def _steps() -> dict[str, dict]:
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    return {s.get("name", ""): s for job in jobs.values() for s in job["steps"]}


def test_compose_mcp_servers_reach_timescaledb():
    services = _services()
    for domain in PORTS:
        env = services[f"mcp-{domain}"]["environment"]
        assert "PGHOST=timescaledb" in env and "PGPORT=5432" in env, domain


def test_compose_backend_uses_the_mcp_containers():
    backend = _services()["backend"]
    env = backend["environment"]
    for domain, port in PORTS.items():
        assert (
            f"MAIW_MCP_SERVER_{domain.upper()}_URL=http://mcp-{domain}:{port}/mcp"
            in env
        )
        assert f"mcp-{domain}" in backend["depends_on"]


def test_compose_governed_writes_are_opt_in():
    env = _services()["backend"]["environment"]
    assert "MAIW_DEPLOYMENT_PROFILE=${MAIW_DEPLOYMENT_PROFILE:-reference}" in env
    assert "MAIW_OPERATOR_WRITE_TOKEN=${MAIW_OPERATOR_WRITE_TOKEN:-}" in env


def test_workflow_enables_governed_profile_with_masked_random_token():
    run = _steps()["Step 4: Configure environment variables"]["run"]
    assert "MAIW_DEPLOYMENT_PROFILE=reference_governed" in run
    assert 'echo "::add-mask::${OPERATOR_TOKEN}"' in run
    assert "secrets.token_hex(32)" in run
    assert run.index("MAIW_OPERATOR_WRITE_TOKEN") < run.index(
        "cp deploy/compose/.env .env"
    )


def test_workflow_runs_blocking_e2e_and_durability_steps_in_order():
    steps = _steps()
    names = list(steps)
    tools = steps["E2E: MCP tool calls"]
    durability = steps["E2E: durability across backend restart"]
    for step in (tools, durability):
        assert "continue-on-error" not in step
    assert names.index("Verify: MCP domain servers") < names.index(
        "E2E: MCP tool calls"
    )
    assert names.index("E2E: MCP tool calls") < names.index(
        "E2E: durability across backend restart"
    )
    assert "smoke_e2e.py mcp-tools" in tools["run"]
    run = durability["run"]
    order = [
        "smoke_e2e.py durability-create",
        "docker restart wosa-backend",
        "http://localhost:8001/api/v1/ready",
        "smoke_e2e.py durability-verify",
    ]
    positions = [run.index(marker) for marker in order]
    assert positions == sorted(positions)
    assert 'if [ "$before" = "$after" ]' in run


def _smoke():
    spec = importlib.util.spec_from_file_location(
        "smoke_e2e", REPO_ROOT / "scripts/testing/smoke_e2e.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_durable_fields_are_served_by_the_executions_api():
    executions = (REPO_ROOT / "apps/api/maiw_api/routers/executions.py").read_text()
    for field in _smoke().DURABLE_FIELDS:
        assert f'"{field}":' in executions, field


def test_smoke_fixture_ids_are_unique_per_run():
    smoke = _smoke()
    a, b = smoke._ids("101-1"), smoke._ids("101-2")
    assert all(a[k] != b[k] for k in a)
    assert a["worker"].isidentifier()
