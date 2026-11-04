# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Demo Mode starts without PostgreSQL settings.

The README Quickstart runs ``MAIW_DEMO_MODE=true uvicorn maiw_api.app:app``
with a ``.env`` holding only ``NVIDIA_API_KEY``, and states that Demo Mode
needs no ``POSTGRES_PASSWORD``.  ``maiw_api.app`` imports the migration
router, whose module-level ``DatabaseMigrator`` called ``_get_database_url()``
at import, so the app died before startup with ``ValueError:
POSTGRES_PASSWORD environment variable is required``.  The migrator now
resolves the URL on first use.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.api.services.migration import DatabaseMigrator

PROJECT_ROOT = Path(__file__).resolve().parents[2]

_DATABASE_ENV = ("DATABASE_URL", "POSTGRES_PASSWORD")


def test_app_imports_without_database_settings():
    """A clean ``import maiw_api.app`` with no database settings must not raise."""
    env = {k: v for k, v in os.environ.items() if k not in _DATABASE_ENV}
    env["PYTHON_DOTENV_DISABLED"] = "1"  # a developer .env must not supply them
    env["MAIW_DEMO_MODE"] = "true"
    env["MAIW_PERSISTENCE_MODE"] = "memory"
    proc = subprocess.run(
        [sys.executable, "-c", "import maiw_api.app"],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr[-4000:]


@pytest.fixture
def no_database_env(monkeypatch):
    for name in _DATABASE_ENV:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_url_is_not_resolved_at_construction(no_database_env, tmp_path):
    migrator = DatabaseMigrator(migrations_dir=str(tmp_path))
    with pytest.raises(ValueError, match="POSTGRES_PASSWORD"):
        _ = migrator.database_url


def test_url_resolved_on_first_use_and_cached(no_database_env, tmp_path):
    migrator = DatabaseMigrator(migrations_dir=str(tmp_path))
    no_database_env.setenv("DATABASE_URL", "postgresql://u:p@db:5432/warehouse")
    assert migrator.database_url == "postgresql://u:p@db:5432/warehouse"
    no_database_env.setenv("DATABASE_URL", "postgresql://u:p@other:5432/warehouse")
    assert migrator.database_url == "postgresql://u:p@db:5432/warehouse"


def test_explicit_url_is_used(no_database_env, tmp_path):
    migrator = DatabaseMigrator(
        "postgresql://u:p@db:5432/x", migrations_dir=str(tmp_path)
    )
    assert migrator.database_url == "postgresql://u:p@db:5432/x"
