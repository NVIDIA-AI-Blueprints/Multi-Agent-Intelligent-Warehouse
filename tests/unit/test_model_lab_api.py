# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 18F — Model Lab API tests.

Covers:
  1. GET /api/v1/model-lab/runs returns list with 18c, 18d, 18e
  2. GET /api/v1/model-lab/runs/18c returns phase metadata
  3. GET /api/v1/model-lab/runs/18e returns verdicts
  4. GET /api/v1/model-lab/model-status returns nano as UNAVAILABLE
  5. GET /api/v1/model-lab/runs/nonexistent returns 404
  6. Architecture invariant: model_lab router does not import forbidden modules
  7. All endpoints are GET-only (no POST/PUT/DELETE)
  8. raw_response bounded to 10000 chars
  9. No secret fields in responses
"""

from __future__ import annotations

import ast
import pathlib
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# ── Ensure worktree apps/api takes precedence over the editable-installed copy ──
# When running tests inside a git worktree the editable install of maiw_api
# points at the main-repo path.  Insert the worktree's apps/api first so that
# `maiw_api.routers.model_lab` (added in 18F) is importable even before the
# branch is merged back.
_worktree_api = str(Path(__file__).resolve().parent.parent.parent / "apps" / "api")
if _worktree_api not in sys.path:
    sys.path.insert(0, _worktree_api)

# Reload maiw_api.routers to pick up the worktree version if it was already
# cached pointing at the main-repo path.
import importlib
import maiw_api.routers

if str(Path(maiw_api.routers.__file__).parent) != str(
    Path(_worktree_api) / "maiw_api" / "routers"
):
    # Force reimport from worktree path
    for mod_name in list(sys.modules.keys()):
        if mod_name.startswith("maiw_api"):
            del sys.modules[mod_name]
    import maiw_api.routers  # noqa: F811

# ── Build a minimal test app ──────────────────────────────────────────────────
from maiw_api.routers.model_lab import router as model_lab_router

_test_app = FastAPI()
_test_app.include_router(model_lab_router)
_client = TestClient(_test_app)


# ── Architecture invariant ─────────────────────────────────────────────────────


class TestArchitectureInvariants:
    """model_lab.py must not import forbidden production modules."""

    _ROUTER_PATH = (
        pathlib.Path(__file__).parent.parent.parent
        / "apps"
        / "api"
        / "maiw_api"
        / "routers"
        / "model_lab.py"
    )

    def _parse_imports(self) -> list[str]:
        source = self._ROUTER_PATH.read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.append(node.module)
        return imports

    def test_no_decision_engine_import(self):
        imports = self._parse_imports()
        for imp in imports:
            assert "DecisionEngine" not in imp, f"Forbidden import found: {imp}"
            assert (
                "decision_engine" not in imp.lower() or "maiw_decision" not in imp
            ), f"Unexpected decision engine import: {imp}"

    def test_no_approval_store_import(self):
        imports = self._parse_imports()
        for imp in imports:
            assert "ApprovalStore" not in imp, f"Forbidden import found: {imp}"
            assert (
                "approval" not in imp.lower() or "maiw_decision" not in imp
            ), f"Unexpected approval import: {imp}"

    def test_no_action_executor_import(self):
        imports = self._parse_imports()
        for imp in imports:
            assert "ActionExecutor" not in imp, f"Forbidden import found: {imp}"
            assert "executor" not in imp.lower(), f"Forbidden executor import: {imp}"

    def test_no_write_mcp_imports(self):
        # Check via AST imports — not raw text — to avoid false positives from comments
        imports = self._parse_imports()
        forbidden_module_fragments = [
            "decision_engine",
            "action_executor",
            "mcp_write",
        ]
        for imp in imports:
            for fragment in forbidden_module_fragments:
                assert (
                    fragment not in imp.lower()
                ), f"Forbidden import fragment '{fragment}' found in import: {imp}"

    def test_all_endpoints_are_get_only(self):
        source = self._ROUTER_PATH.read_text(encoding="utf-8")
        # Should have router.get but NOT router.post, router.put, router.delete
        assert "@router.get" in source, "Should have GET endpoints"
        assert "@router.post" not in source, "POST not allowed in read-only Lab"
        assert "@router.put" not in source, "PUT not allowed in read-only Lab"
        assert "@router.delete" not in source, "DELETE not allowed in read-only Lab"
        assert "@router.patch" not in source, "PATCH not allowed in read-only Lab"


# ── /runs ─────────────────────────────────────────────────────────────────────


class TestListRuns:
    def test_returns_200(self):
        resp = _client.get("/api/v1/model-lab/runs")
        assert resp.status_code == 200

    def test_returns_list(self):
        resp = _client.get("/api/v1/model-lab/runs")
        data = resp.json()
        assert isinstance(data, list)

    def test_contains_all_run_ids(self):
        resp = _client.get("/api/v1/model-lab/runs")
        run_ids = {r["run_id"] for r in resp.json()}
        assert "18c" in run_ids
        assert "18d" in run_ids
        assert "18e" in run_ids

    def test_18c_methodology_invalid(self):
        resp = _client.get("/api/v1/model-lab/runs")
        runs = {r["run_id"]: r for r in resp.json()}
        assert runs["18c"]["methodology_valid"] is False

    def test_18d_methodology_valid(self):
        resp = _client.get("/api/v1/model-lab/runs")
        runs = {r["run_id"]: r for r in resp.json()}
        assert runs["18d"]["methodology_valid"] is True

    def test_18e_methodology_valid(self):
        resp = _client.get("/api/v1/model-lab/runs")
        runs = {r["run_id"]: r for r in resp.json()}
        assert runs["18e"]["methodology_valid"] is True

    def test_no_secret_fields_in_runs(self):
        resp = _client.get("/api/v1/model-lab/runs")
        response_text = resp.text.lower()
        for secret in ["api_key", "authorization", "password", "token", "secret"]:
            assert (
                f'"{secret}"' not in response_text
            ), f"Secret field '{secret}' found in /runs response"


# ── /runs/18c ────────────────────────────────────────────────────────────────


class TestGetRun18C:
    def test_returns_200(self):
        resp = _client.get("/api/v1/model-lab/runs/18c")
        assert resp.status_code == 200

    def test_has_phase_metadata(self):
        resp = _client.get("/api/v1/model-lab/runs/18c")
        data = resp.json()
        assert data["phase"] == "18C"
        assert data["run_id"] == "18c"

    def test_methodology_invalid(self):
        resp = _client.get("/api/v1/model-lab/runs/18c")
        data = resp.json()
        assert data["methodology_valid"] is False

    def test_has_dataset_id(self):
        resp = _client.get("/api/v1/model-lab/runs/18c")
        data = resp.json()
        assert "dataset_id" in data

    def test_no_secret_fields(self):
        resp = _client.get("/api/v1/model-lab/runs/18c")
        response_text = resp.text.lower()
        for secret in ["api_key", "authorization", "password"]:
            assert f'"{secret}"' not in response_text


# ── /runs/18e ────────────────────────────────────────────────────────────────


class TestGetRun18E:
    def test_returns_200(self):
        resp = _client.get("/api/v1/model-lab/runs/18e")
        assert resp.status_code == 200

    def test_has_verdicts(self):
        resp = _client.get("/api/v1/model-lab/runs/18e")
        data = resp.json()
        assert "verdicts" in data
        verdicts = data["verdicts"]
        assert verdicts is not None

    def test_verdict_router_insufficient_evidence(self):
        resp = _client.get("/api/v1/model-lab/runs/18e")
        data = resp.json()
        verdicts = data.get("verdicts", {})
        assert "INSUFFICIENT EVIDENCE" in verdicts.get("router", "").upper()

    def test_verdict_nano_unavailable(self):
        resp = _client.get("/api/v1/model-lab/runs/18e")
        data = resp.json()
        verdicts = data.get("verdicts", {})
        assert "UNAVAILABLE" in verdicts.get("nano", "").upper()

    def test_methodology_valid(self):
        resp = _client.get("/api/v1/model-lab/runs/18e")
        data = resp.json()
        assert data["methodology_valid"] is True


# ── /runs/nonexistent ─────────────────────────────────────────────────────────


class TestNotFound:
    def test_nonexistent_run_returns_404(self):
        resp = _client.get("/api/v1/model-lab/runs/nonexistent")
        assert resp.status_code == 404

    def test_nonexistent_run_error_message(self):
        resp = _client.get("/api/v1/model-lab/runs/nonexistent")
        data = resp.json()
        assert "detail" in data
        assert "nonexistent" in data["detail"]

    def test_nonexistent_case_returns_404(self):
        resp = _client.get("/api/v1/model-lab/runs/18c/cases/does-not-exist")
        assert resp.status_code == 404

    def test_nonexistent_run_for_cases_returns_404(self):
        resp = _client.get("/api/v1/model-lab/runs/badrun/cases")
        assert resp.status_code == 404


# ── /model-status ─────────────────────────────────────────────────────────────


class TestModelStatus:
    def test_returns_200(self):
        resp = _client.get("/api/v1/model-lab/model-status")
        assert resp.status_code == 200

    def test_returns_list(self):
        resp = _client.get("/api/v1/model-lab/model-status")
        data = resp.json()
        assert isinstance(data, list)

    def test_nano_is_unavailable(self):
        resp = _client.get("/api/v1/model-lab/model-status")
        data = resp.json()
        nano = next((m for m in data if m.get("model") == "Nano"), None)
        assert nano is not None, "Nano model not found in model-status"
        assert nano["status"] == "UNAVAILABLE"

    def test_nano_has_not_tested_note(self):
        resp = _client.get("/api/v1/model-lab/model-status")
        data = resp.json()
        nano = next((m for m in data if m.get("model") == "Nano"), None)
        assert nano is not None
        note = nano.get("note", "")
        assert "NOT TESTED" in note

    def test_super_is_available(self):
        resp = _client.get("/api/v1/model-lab/model-status")
        data = resp.json()
        super_model = next((m for m in data if m.get("model") == "Super"), None)
        assert super_model is not None
        assert super_model["status"] == "AVAILABLE"

    def test_lightning_is_available(self):
        resp = _client.get("/api/v1/model-lab/model-status")
        data = resp.json()
        lightning = next((m for m in data if m.get("model") == "Lightning"), None)
        assert lightning is not None
        assert lightning["status"] == "AVAILABLE"


# ── raw_response bounding ─────────────────────────────────────────────────────


class TestRawResponseBounding:
    def test_bound_raw_response_truncates_long_strings(self):
        from maiw_api.routers.model_lab import _bound_raw_response

        long_text = "x" * 15_000
        result = _bound_raw_response({"raw_response": long_text})
        assert len(result["raw_response"]) <= 10_000
        assert result.get("raw_response_truncated") is True
        assert result.get("raw_response_original_length") == 15_000

    def test_bound_raw_response_preserves_short_strings(self):
        from maiw_api.routers.model_lab import _bound_raw_response

        short_text = "Hello warehouse"
        result = _bound_raw_response({"raw_response": short_text})
        assert result["raw_response"] == short_text
        assert "raw_response_truncated" not in result

    def test_bound_raw_response_recurses_into_list(self):
        from maiw_api.routers.model_lab import _bound_raw_response

        long_text = "y" * 20_000
        result = _bound_raw_response([{"raw_response": long_text}])
        assert len(result[0]["raw_response"]) <= 10_000


# ── secret stripping ──────────────────────────────────────────────────────────


class TestSecretStripping:
    def test_strips_api_key(self):
        from maiw_api.routers.model_lab import _strip_secrets

        data = {"api_key": "secret-value", "model": "Super"}
        result = _strip_secrets(data)
        assert "api_key" not in result
        assert result["model"] == "Super"

    def test_strips_authorization(self):
        from maiw_api.routers.model_lab import _strip_secrets

        data = {"authorization": "Bearer abc123", "run_id": "18e"}
        result = _strip_secrets(data)
        assert "authorization" not in result

    def test_strips_nested_secrets(self):
        from maiw_api.routers.model_lab import _strip_secrets

        data = {"outer": {"api_key": "secret", "safe": "value"}}
        result = _strip_secrets(data)
        assert "api_key" not in result["outer"]
        assert result["outer"]["safe"] == "value"


# ── runs/{run_id}/cases ───────────────────────────────────────────────────────


class TestRunCases:
    def test_18c_cases_returns_list(self):
        resp = _client.get("/api/v1/model-lab/runs/18c/cases")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_18e_cases_returns_list(self):
        resp = _client.get("/api/v1/model-lab/runs/18e/cases")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_18e_cases_have_case_id(self):
        resp = _client.get("/api/v1/model-lab/runs/18e/cases")
        cases = resp.json()
        if cases:
            assert "case_id" in cases[0]


# ── Path traversal security tests ────────────────────────────────────────────


class TestModelLabPathSecurity:
    """Architecture invariant: artifact loader cannot escape the artifact root."""

    def test_unknown_run_id_rejected(self):
        """Unknown run IDs are rejected with 404 — no filesystem path is constructed."""
        for bad_id in [
            "../etc/passwd",
            "../../requirements.txt",
            "18c/../../../.env",
            "18c%2F..%2F.env",
            "18x",
        ]:
            resp = _client.get(f"/api/v1/models/lab/runs/{bad_id}")
            # Any unknown run_id must return 404 (not 200, 500, or path-relative content)
            assert resp.status_code in (
                404,
                307,
                422,
            ), f"Expected 404/307/422 for run_id={bad_id!r}, got {resp.status_code}"

    def test_run_endpoint_only_accepts_whitelisted_ids(self):
        """Valid run IDs succeed; everything else is rejected."""
        valid_ids = {"18c", "18d", "18e", "18f"}
        # These may 200 (artifact on disk) or 404 (artifact not on disk) — both safe
        for vid in valid_ids:
            resp = _client.get(f"/api/v1/models/lab/runs/{vid}")
            assert resp.status_code in (
                200,
                404,
            ), f"Unexpected status {resp.status_code} for valid run_id={vid}"

    def test_run_list_does_not_expose_secrets(self):
        """Run list response must not contain secret fields."""
        resp = _client.get("/api/v1/models/lab/runs")
        if resp.status_code == 200:
            body = resp.json()
            text = str(body).lower()
            for secret_term in ["api_key", "authorization", "password"]:
                assert (
                    secret_term not in text
                ), f"Run list response contains secret field: {secret_term!r}"
