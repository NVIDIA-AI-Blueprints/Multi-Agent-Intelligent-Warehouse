# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
``PUT /auth/me`` changes only the caller's personal fields.

The self-service route takes ``UserSelfUpdate`` (email and full name; anything
else, role and status included, is a 422) and calls ``update_profile``, which
forwards only those two fields. Role and status changes stay on the admin
route ``PUT /auth/users/{user_id}``.

Drives the shipped app with a fake user table; no database is contacted.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.api.services.auth import dependencies as auth_deps
from src.api.services.auth.models import User, UserRole, UserSelfUpdate, UserStatus
from src.api.services.auth.user_service import user_service
from tests.api.canonical_harness import (
    FakeNIM,
    canonical_env,
    install_gateway,
    running_canonical_app,
)

NOW = datetime(2026, 11, 7, tzinfo=timezone.utc)
SELF_ID = 42
OTHER_ID = 7
NON_ADMIN_ROLES = [r for r in UserRole if r is not UserRole.ADMIN]


class FakeUsers:
    """A users table that applies ``UPDATE users SET col = $n ... WHERE id = $m``."""

    _SET = re.compile(r"(\w+) = \$(\d+)")

    def __init__(self) -> None:
        self.rows = {
            uid: {
                "id": uid,
                "username": f"user{uid}",
                "email": f"user{uid}@example.com",
                "full_name": f"User {uid}",
                "role": "viewer",
                "status": "active",
                "created_at": NOW,
                "updated_at": NOW,
                "last_login": None,
            }
            for uid in (SELF_ID, OTHER_ID)
        }
        self.updates: list[str] = []

    async def fetch_one(self, query, *params):
        assert query.lstrip().startswith("UPDATE users"), query
        self.updates.append(query)
        row = self.rows.get(params[-1])
        if row is None:
            return None
        for column, index in self._SET.findall(query.split("WHERE")[0]):
            row[column] = params[int(index) - 1]
        return dict(row)

    def set_columns(self) -> set[str]:
        return {
            column
            for query in self.updates
            for column, _ in self._SET.findall(query.split("WHERE")[0])
        }


@pytest.fixture
def users(monkeypatch, tmp_path):
    fake_nim = FakeNIM()
    canonical_env(monkeypatch, tmp_path, fake_nim)
    install_gateway(fake_nim)
    table = FakeUsers()

    async def _no_db():
        return None

    monkeypatch.setattr(user_service, "initialize", _no_db)
    monkeypatch.setattr(user_service, "sql_retriever", table, raising=False)
    yield table
    fake_nim.close()
    from maiw_models import reset_model_gateway

    reset_model_gateway()


def _caller(role: UserRole) -> User:
    return User(
        id=SELF_ID,
        username=f"user{SELF_ID}",
        email=f"user{SELF_ID}@example.com",
        full_name=f"User {SELF_ID}",
        role=role,
        status=UserStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )


async def _put(role: UserRole, path: str, body: dict):
    async with running_canonical_app() as (app, client):
        app.dependency_overrides[auth_deps.get_current_user] = lambda: _caller(role)
        try:
            return await client.put(path, json=body)
        finally:
            app.dependency_overrides.pop(auth_deps.get_current_user, None)


# ── PUT /auth/me refuses role and status ──────────────────────────────────────


@pytest.mark.parametrize("role", list(UserRole), ids=lambda r: r.value)
@pytest.mark.parametrize(
    "body",
    [
        {"role": "admin"},
        {"role": "admin", "full_name": "Still Me"},
        {"status": "active"},
        {"status": "suspended"},
        {"role": "manager", "status": "active"},
    ],
    ids=["role", "role+name", "status-active", "status-suspended", "role+status"],
)
async def test_self_update_rejects_role_and_status(users, role, body):
    resp = await _put(role, "/api/v1/auth/me", body)
    assert resp.status_code == 422
    assert users.updates == []  # nothing written, not even the name
    assert users.rows[SELF_ID]["role"] == "viewer"
    assert users.rows[SELF_ID]["status"] == "active"


@pytest.mark.parametrize("role", NON_ADMIN_ROLES, ids=lambda r: r.value)
async def test_self_update_cannot_promote_to_admin(users, role):
    resp = await _put(role, "/api/v1/auth/me", {"role": "admin"})
    assert resp.status_code == 422
    assert "role" not in users.set_columns()
    assert users.rows[SELF_ID]["role"] == "viewer"


# ── PUT /auth/me still updates personal fields ────────────────────────────────


@pytest.mark.parametrize("role", list(UserRole), ids=lambda r: r.value)
async def test_self_update_changes_name_and_email(users, role):
    resp = await _put(
        role,
        "/api/v1/auth/me",
        {"full_name": "New Name", "email": "new@example.com"},
    )
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "New Name"
    assert resp.json()["email"] == "new@example.com"
    assert users.set_columns() == {"full_name", "email"}


async def test_self_update_unknown_user_is_404_not_500(users):
    users.rows.pop(SELF_ID)
    resp = await _put(UserRole.VIEWER, "/api/v1/auth/me", {"full_name": "Gone"})
    assert resp.status_code == 404


# ── The admin route keeps role and status changes ─────────────────────────────


async def test_admin_can_change_another_users_role_and_status(users):
    resp = await _put(
        UserRole.ADMIN,
        f"/api/v1/auth/users/{OTHER_ID}",
        {"role": "manager", "status": "suspended"},
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "manager"
    assert resp.json()["status"] == "suspended"
    assert {"role", "status"} <= users.set_columns()


@pytest.mark.parametrize("role", NON_ADMIN_ROLES, ids=lambda r: r.value)
@pytest.mark.parametrize("target", [SELF_ID, OTHER_ID], ids=["self", "other"])
async def test_non_admin_cannot_use_the_admin_route(users, role, target):
    resp = await _put(role, f"/api/v1/auth/users/{target}", {"role": "admin"})
    assert resp.status_code == 403
    assert users.updates == []


# ── The service layer never writes role or status for a profile update ──────


def test_self_update_model_forbids_privileged_fields():
    for field, value in (("role", "admin"), ("status", "active"), ("id", 1)):
        with pytest.raises(ValidationError):
            UserSelfUpdate(**{field: value})


async def test_update_profile_forwards_only_personal_fields(users):
    # Even an object carrying role/status (not a validated UserSelfUpdate)
    # only has its email and full name written.
    smuggled = SimpleNamespace(
        email=None,
        full_name="Name Only",
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
    )
    updated = await user_service.update_profile(SELF_ID, smuggled)
    assert updated is not None and updated.role is UserRole.VIEWER
    assert users.set_columns() == {"full_name"}
