# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Required checks for main (docs/operations/MERGE_PROTECTION.md) must be able to pass.

A ruleset that requires a check which never runs on pull requests blocks
every merge. These tests tie the documented required contexts to the jobs
that produce them and pin how the GPU deployment test runs on pull requests.
"""

from __future__ import annotations

import itertools
import json
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github/workflows"
DOC = REPO_ROOT / "docs/operations/MERGE_PROTECTION.md"
GITHUB_ACTIONS_APP_ID = 15368
FORK_PR = (
    "github.event_name == 'pull_request' && "
    "github.event.pull_request.head.repo.full_name != github.repository"
)


def _load(name: str) -> dict:
    return yaml.safe_load((WORKFLOWS / name).read_text())


def _triggers(workflow: dict) -> dict:
    # PyYAML reads the bare key ``on`` as the boolean True.
    return workflow.get("on", workflow.get(True))


def _contexts(job_id: str, job: dict) -> list[str]:
    """Status contexts GitHub reports for a job (name plus matrix values)."""
    name = job.get("name", job_id)
    matrix = (job.get("strategy") or {}).get("matrix") or {}
    axes = [v for k, v in matrix.items() if k not in ("include", "exclude")]
    if not axes or "${{" in name:
        return [name]
    return [
        f"{name} ({', '.join(str(v) for v in combo)})"
        for combo in itertools.product(*axes)
    ]


def _documented_rule() -> dict:
    block = re.search(r"```json\n(.*?)```", DOC.read_text(), re.S)
    assert block, "MERGE_PROTECTION.md must carry the ruleset JSON"
    return json.loads(block.group(1))


def test_documented_rule_pins_github_actions_for_every_context():
    rule = _documented_rule()
    assert rule["type"] == "required_status_checks"
    checks = rule["parameters"]["required_status_checks"]
    assert {c["context"] for c in checks} == {
        "Test & Quality Checks (3.11, 22)",
        "deploy-and-test",
        "CodeQL (python)",
        "CodeQL (javascript)",
    }
    assert all(c["integration_id"] == GITHUB_ACTIONS_APP_ID for c in checks)


def test_every_required_context_runs_on_every_pull_request_to_main():
    produced = {}
    for path in WORKFLOWS.glob("*.yml"):
        workflow = yaml.safe_load(path.read_text())
        for job_id, job in workflow["jobs"].items():
            for context in _contexts(job_id, job):
                produced[context] = (path.name, workflow)

    for check in _documented_rule()["parameters"]["required_status_checks"]:
        context = check["context"]
        assert context in produced, f"no job reports {context!r}"
        name, workflow = produced[context]
        pr = _triggers(workflow).get("pull_request")
        assert pr is not None, f"{name} does not run on pull requests"
        assert pr.get("branches") == ["main"], name
        # A path filter would leave the required check pending forever.
        for key in ("paths", "paths-ignore", "branches-ignore"):
            assert key not in pr, f"{name} filters pull requests by {key}"


def test_deploy_test_runs_on_pull_requests_to_main():
    triggers = _triggers(_load("main.yml"))
    assert triggers["push"] == {"branches": ["main"]}
    assert triggers["pull_request"] == {"branches": ["main"]}
    assert "pull_request_target" not in triggers


def test_fork_pull_requests_never_reach_the_gpu_runner():
    job = _load("main.yml")["jobs"]["deploy-and-test"]
    assert job["runs-on"] == (
        "${{ ("
        + FORK_PR
        + ") && 'ubuntu-latest' || 'arc-runners-org-nvidia-ai-bp-4-gpu' }}"
    )
    first = job["steps"][0]
    assert first["if"] == FORK_PR
    assert "exit 1" in first["run"]
    # The refusal comes before any step that checks out or runs PR code.
    assert "uses" not in first


def test_deploy_check_and_mail_follow_the_pull_request():
    steps = {
        s["name"]: s for s in _load("main.yml")["jobs"]["deploy-and-test"]["steps"]
    }
    report = steps["Report MAIW pytest as a commit check"]
    assert report["env"]["CHECK_HEAD_SHA"] == (
        "${{ github.event.pull_request.head.sha || github.sha }}"
    )
    assert steps["Send mail"]["if"] == "always() && github.event_name != 'pull_request'"
