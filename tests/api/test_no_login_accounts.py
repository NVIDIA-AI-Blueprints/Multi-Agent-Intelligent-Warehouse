# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
The blueprint has no user login (#261).

The UI never had a login screen and no shipped route checked a user token, but
the legacy ``/api/v1/auth/*`` router was still mounted, ``create_default_users.py``
seeded ``admin``/``user`` accounts, and the demo-data scripts hashed the
fallback password ``changeme`` into every row. All of that is removed.

The ``users`` table stays: it is the worker roster read by the labor tools and
by ``/operations/workforce``. The UI's assignment dropdowns now read it from
``GET /api/v1/operations/workers`` instead of ``/auth/users/public``.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from maiw_api.routers import operations as operations_module
from tests.api.canonical_harness import (
    FakeNIM,
    canonical_env,
    install_gateway,
    running_canonical_app,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def canonical(monkeypatch, tmp_path):
    fake = FakeNIM()
    canonical_env(monkeypatch, tmp_path, fake)
    install_gateway(fake)
    yield
    fake.close()
    from maiw_models import reset_model_gateway

    reset_model_gateway()


class _FakeSQL:
    def __init__(self, rows=None, error: Exception | None = None):
        self.rows = rows or []
        self.error = error
        self.queries: list[str] = []

    async def initialize(self):
        if self.error:
            raise self.error

    async def fetch_all(self, query, *params):
        self.queries.append(query)
        return self.rows


# ── The worker roster endpoint ────────────────────────────────────────────────


async def test_workers_endpoint_returns_the_active_roster(canonical, monkeypatch):
    rows = [
        {
            "id": 3,
            "username": "operator1",
            "full_name": "James Wilson",
            "role": "operator",
        },
        {
            "id": 1,
            "username": "manager1",
            "full_name": "Sarah Johnson",
            "role": "manager",
        },
    ]
    fake = _FakeSQL(rows)
    monkeypatch.setattr(operations_module, "_get_sql", lambda: fake)
    async with running_canonical_app() as (_, client):
        resp = await client.get("/api/v1/operations/workers")
    assert resp.status_code == 200
    assert resp.json() == rows
    (query,) = fake.queries
    assert "status::text = 'active'" in query
    assert "hashed_password" not in query and "email" not in query


async def test_workers_endpoint_failure_is_a_fixed_500(canonical, monkeypatch):
    fake = _FakeSQL(error=RuntimeError("connection refused to db.internal:5435"))
    monkeypatch.setattr(operations_module, "_get_sql", lambda: fake)
    async with running_canonical_app() as (_, client):
        resp = await client.get("/api/v1/operations/workers")
    assert resp.status_code == 500
    assert "db.internal" not in resp.text


async def test_workers_endpoint_is_read_only(canonical):
    async with running_canonical_app() as (_, client):
        resp = await client.post("/api/v1/operations/workers", json={})
    assert resp.status_code == 405


async def test_login_routes_are_gone(canonical):
    async with running_canonical_app() as (_, client):
        login = await client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "changeme"}
        )
        roster = await client.get("/api/v1/auth/users/public")
    assert login.status_code in (404, 405)
    assert roster.status_code == 404


def test_auth_package_and_user_script_are_removed():
    for path in (
        "src/api/routers/auth.py",
        "src/api/services/auth",
        "scripts/setup/create_default_users.py",
        "src/ui/web/src/pages/Login.tsx",
        "src/ui/web/src/contexts/AuthContext.tsx",
    ):
        assert not (REPO_ROOT / path).exists(), path


# ── Schema and demo data ──────────────────────────────────────────────────────


def _users_ddl() -> str:
    schema = (REPO_ROOT / "data/postgres/000_schema.sql").read_text()
    match = re.search(r"CREATE TABLE IF NOT EXISTS users \((.*?)\);", schema, re.S)
    assert match, "users table not found"
    return match.group(1)


def test_users_table_has_no_password_and_old_databases_are_migrated():
    assert "hashed_password" not in _users_ddl()
    schema = (REPO_ROOT / "data/postgres/000_schema.sql").read_text()
    assert "ALTER TABLE users DROP COLUMN IF EXISTS hashed_password;" in schema
    assert "DROP TABLE IF EXISTS user_sessions;" in schema
    assert "CREATE TABLE IF NOT EXISTS user_sessions" not in schema


@pytest.mark.parametrize(
    "script",
    [
        "scripts/data/quick_demo_data.py",
        "scripts/data/generate_synthetic_data.py",
        "scripts/testing/smoke_e2e.py",
    ],
)
def test_demo_data_writes_no_passwords(script):
    source = (REPO_ROOT / script).read_text()
    assert "bcrypt" not in source
    assert "DEFAULT_USER_PASSWORD" not in source
    assert "changeme" not in source
    for insert in re.findall(r"INSERT INTO users \(([^)]*)\)", source):
        assert "hashed_password" not in insert, (script, insert)


def test_no_script_falls_back_to_a_default_credential():
    pattern = re.compile(
        r"os\.(?:getenv|environ\.get)\(\s*['\"][A-Z_]*(?:PASSWORD|SECRET|TOKEN)[A-Z_]*['\"]\s*,\s*['\"]changeme['\"]"
    )
    offenders = [
        str(path.relative_to(REPO_ROOT))
        for path in (REPO_ROOT / "scripts").rglob("*.py")
        if pattern.search(path.read_text(encoding="utf-8", errors="replace"))
    ]
    assert offenders == []


def test_login_only_dependencies_are_dropped():
    for name in ("requirements.txt", "requirements.docker.txt", "pyproject.toml"):
        text = (REPO_ROOT / name).read_text().lower()
        for dep in ("pyjwt", "python-jose", "bcrypt", "email-validator"):
            assert dep not in text, (name, dep)


def test_env_example_has_no_login_secrets():
    text = (REPO_ROOT / ".env.example").read_text()
    for name in ("JWT_SECRET_KEY", "DEFAULT_ADMIN_PASSWORD", "DEFAULT_USER_PASSWORD"):
        assert name not in text, name


# ── generate_equipment_telemetry.py requires POSTGRES_PASSWORD ───────────────


def _load_telemetry_script(monkeypatch):
    monkeypatch.setitem(sys.modules, "asyncpg", MagicMock())
    path = REPO_ROOT / "scripts/data/generate_equipment_telemetry.py"
    spec = importlib.util.spec_from_file_location("_telemetry_script", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_telemetry_script_exits_without_postgres_password(monkeypatch):
    module = _load_telemetry_script(monkeypatch)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    with pytest.raises(SystemExit) as info:
        module.postgres_password()
    assert "POSTGRES_PASSWORD is not set" in str(info.value)


def test_telemetry_script_uses_postgres_password_when_set(monkeypatch):
    module = _load_telemetry_script(monkeypatch)
    monkeypatch.setenv("POSTGRES_PASSWORD", "from-the-environment")
    assert module.postgres_password() == "from-the-environment"
