# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Request data in logs (SonarQube pythonsecurity:S5145, CWE-117 / CWE-532).

SonarQube's last analysis reported 11 places that log user-controlled data;
a triage of current main found the same pattern in the canonical API (which
SonarQube never analyzed) and worse:
- the validation-error handler logged pydantic's ``errors()``, whose
  ``input`` is the request body: a login request missing a field logged its
  password;
- the HTTP-exception handler logged ``exc.detail`` raw, and many details
  embed path values, so a GET with ``%0d%0a`` in an ID forged log entries;
- login logged the raw username before authentication.

These tests drive the shipped app and check what reaches the log.
"""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest

from src.api.utils.log_utils import (
    escape_log_control_chars,
    install_log_injection_guard,
)
from tests.api.canonical_harness import (
    FakeNIM,
    canonical_env,
    install_gateway,
    running_canonical_app,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FORGED = "%0d%0aINFO%20admin%20logged%20in%20successfully"


@pytest.fixture
def canonical(monkeypatch, tmp_path):
    fake = FakeNIM()
    canonical_env(monkeypatch, tmp_path, fake)
    install_gateway(fake)
    yield
    fake.close()
    from maiw_models import reset_model_gateway

    reset_model_gateway()


def _messages(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records]


def _assert_single_line(caplog):
    for message in _messages(caplog):
        assert "\n" not in message and "\r" not in message, message


# ── The process-wide guard ────────────────────────────────────────────────────


def test_guard_escapes_control_characters_and_keeps_args(caplog):
    install_log_injection_guard()
    installed = logging.getLogRecordFactory()
    install_log_injection_guard()  # idempotent
    assert logging.getLogRecordFactory() is installed
    logger = logging.getLogger("maiw.test.guard")
    with caplog.at_level(logging.INFO, logger="maiw.test.guard"):
        logger.info("asset %s: %s", "FL-01\r\nINFO forged", "a\tb\x1b[31m")
    (record,) = caplog.records
    assert record.args == ("FL-01\r\nINFO forged", "a\tb\x1b[31m")  # untouched
    assert record.getMessage() == "asset FL-01\\r\\nINFO forged: a\tb\\x1b[31m"


def test_escape_keeps_tab_and_printable_text():
    assert escape_log_control_chars("plain text\twith tab") == "plain text\twith tab"
    assert escape_log_control_chars("a\x00b\x7f") == "a\\x00b\\x7f"


def test_shipped_app_installs_the_guard():
    import maiw_api.app  # noqa: F401  (installs the guard at import)

    record = logging.getLogRecordFactory()(
        "x", logging.INFO, __file__, 1, "%s", ("a\nb",), None
    )
    assert record.getMessage() == "a\\nb"


def test_every_mcp_server_installs_the_guard_and_the_image_ships_it():
    for domain in ("equipment", "inventory", "labor", "wave"):
        tree = ast.parse((REPO_ROOT / f"mcp_servers/{domain}/server.py").read_text())
        main = next(
            node
            for node in tree.body
            if isinstance(node, ast.If) and "__main__" in ast.unparse(node.test)
        )
        assert "install_log_injection_guard()" in ast.unparse(main), domain
    assert (
        "COPY src/api/utils ./src/api/utils"
        in (REPO_ROOT / "Dockerfile.mcp").read_text()
    )


# ── What the shipped app logs ─────────────────────────────────────────────────


async def test_validation_errors_never_log_submitted_values(canonical, caplog):
    secret = "S3cretPW-not-for-logs"
    with caplog.at_level(logging.DEBUG):
        async with running_canonical_app() as (_, client):
            # A login missing `username`: pydantic's error input is the body.
            resp = await client.post("/api/v1/auth/login", json={"password": secret})
    assert resp.status_code == 422
    assert secret not in caplog.text
    assert any("Validation error" in m for m in _messages(caplog))


async def test_path_values_cannot_forge_log_entries(canonical, caplog):
    with caplog.at_level(logging.DEBUG):
        async with running_canonical_app() as (_, client):
            for path in (
                f"/api/v1/equipment/FL-01{FORGED}",
                f"/api/v1/safety/policies/POL-1{FORGED}",
                f"/api/v1/inventory/items/SKU-1{FORGED}",
            ):
                await client.get(path)
    _assert_single_line(caplog)


async def test_login_username_is_sanitized_before_authentication(canonical, caplog):
    forged = "nobody\r\nINFO admin logged in successfully"
    with caplog.at_level(logging.DEBUG):
        async with running_canonical_app() as (_, client):
            await client.post(
                "/api/v1/auth/login", json={"username": forged, "password": "x"}
            )
    _assert_single_line(caplog)
    assert not any(m.startswith("INFO admin") for m in caplog.text.splitlines())


async def test_sql_retriever_does_not_log_bound_parameters(caplog):
    from contextlib import asynccontextmanager

    from src.retrieval.structured.sql_retriever import SQLRetriever

    class _FailingConnection:
        async def fetch(self, *_args, **_kwargs):
            raise RuntimeError("relation does not exist")

    retriever = SQLRetriever.__new__(SQLRetriever)

    @asynccontextmanager
    async def connection():
        yield _FailingConnection()

    retriever.get_connection = connection
    with caplog.at_level(logging.DEBUG), pytest.raises(RuntimeError):
        await retriever.execute_query(
            "SELECT * FROM users WHERE email = $1", ("alice@example.com",)
        )
    assert "alice@example.com" not in caplog.text
    assert "Params: 1 value(s) not logged" in caplog.text
