# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""scripts/ci/report_maiw_pytest_check.py: the NGC suite's own commit check."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/ci/report_maiw_pytest_check.py"
RUN_URL = "https://github.com/o/r/actions/runs/1"


def _load():
    spec = importlib.util.spec_from_file_location("report_maiw_pytest_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


report = _load()


@pytest.mark.parametrize(
    ("e2e", "reason", "conclusion", "title"),
    [
        ("PASSED", "", "success", "PASSED"),
        ("FAILED", "", "failure", "FAILED"),
        (
            "NOT_RUN",
            "could not pull the internal test image",
            "neutral",
            "NOT RUN: could not pull the internal test image",
        ),
        ("", "", "neutral", "NOT RUN: the step did not report a result"),
        ("garbage", "", "neutral", "NOT RUN: the step did not report a result"),
    ],
)
def test_result_maps_to_check_conclusion(e2e, reason, conclusion, title):
    body = report.build_check_run(e2e, reason, RUN_URL, "abc123")
    assert body["name"] == "MAIW internal pytest (NGC)"
    assert body["head_sha"] == "abc123"
    assert body["status"] == "completed"
    assert body["conclusion"] == conclusion
    assert body["output"]["title"] == title
    assert body["details_url"] == RUN_URL
    assert RUN_URL in body["output"]["summary"]


def test_not_run_is_never_reported_as_success():
    for e2e in ("NOT_RUN", "", "SKIPPED", "not_run"):
        assert report.build_check_run(e2e, "", RUN_URL, "s")["conclusion"] != "success"


def test_dry_run_prints_body_without_network(monkeypatch, capsys):
    monkeypatch.setenv("E2E", "NOT_RUN")
    monkeypatch.setenv("REASON", "TEST_DOCKER_PULL_KEY not set")
    monkeypatch.setenv("RUN_URL", RUN_URL)
    monkeypatch.setenv("GITHUB_SHA", "def456")

    def no_network(_):
        raise AssertionError("dry run must not post")

    monkeypatch.setattr(report, "_post", no_network)
    assert report.main(["--dry-run"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["conclusion"] == "neutral"
    assert body["output"]["title"] == "NOT RUN: TEST_DOCKER_PULL_KEY not set"


def test_post_failure_only_warns(monkeypatch, capsys):
    monkeypatch.setenv("E2E", "PASSED")

    def failing(_):
        raise OSError("network down")

    monkeypatch.setattr(report, "_post", failing)
    assert report.main([]) == 0
    assert "::warning title=MAIW pytest check not posted::network down" in (
        capsys.readouterr().out
    )


@pytest.mark.parametrize(
    ("head_sha", "expected"),
    [("pr-head-sha", "pr-head-sha"), ("", "merge-sha")],
)
def test_check_goes_on_the_pull_request_head_commit(
    monkeypatch, capsys, head_sha, expected
):
    # On a pull request GITHUB_SHA is the temporary merge commit.
    monkeypatch.setenv("E2E", "PASSED")
    monkeypatch.setenv("GITHUB_SHA", "merge-sha")
    monkeypatch.setenv("CHECK_HEAD_SHA", head_sha)
    assert report.main(["--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["head_sha"] == expected
