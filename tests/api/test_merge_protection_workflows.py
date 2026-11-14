# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Required checks for main (docs/operations/MERGE_PROTECTION.md) must be able to pass.

A ruleset that requires a check which never runs on pull requests blocks
every merge. Pull request code must not reach the self-hosted GPU runner,
which holds repository credentials: for a pull request GitHub runs the pull
request's own workflow files, so only the triggers decide what can run there.
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
PR_EVENTS = ("pull_request", "pull_request_target")
SELF_HOSTED = ("self-hosted", "arc-runners")


def _workflows() -> dict[str, dict]:
    return {
        p.name: yaml.safe_load(p.read_text()) for p in sorted(WORKFLOWS.glob("*.yml"))
    }


def _triggers(workflow: dict) -> dict:
    # PyYAML reads the bare key ``on`` as the boolean True.
    triggers = workflow.get("on", workflow.get(True))
    return {t: None for t in triggers} if isinstance(triggers, list) else triggers


def _contexts(job_id: str, job: dict) -> list[str]:
    """Status contexts GitHub reports for a job (name plus matrix values)."""
    name = job.get("name", job_id)
    matrix = (job.get("strategy") or {}).get("matrix") or {}
    if "${{" in name:
        values = [
            {k: v for k, v in entry.items() if not isinstance(v, (dict, list))}
            for entry in matrix.get("include", [])
        ]
        return [
            re.sub(r"\$\{\{\s*matrix\.(\w+)\s*\}\}", lambda m: str(v[m[1]]), name)
            for v in values
        ]
    axes = [v for k, v in matrix.items() if k not in ("include", "exclude")]
    if not axes:
        return [name]
    return [
        f"{name} ({', '.join(str(v) for v in combo)})"
        for combo in itertools.product(*axes)
    ]


def _documented_checks() -> list[dict]:
    block = re.search(r"```json\n(.*?)```", DOC.read_text(), re.S)
    assert block, "MERGE_PROTECTION.md must carry the ruleset JSON"
    rule = json.loads(block.group(1))
    assert rule["type"] == "required_status_checks"
    return rule["parameters"]["required_status_checks"]


def test_documented_rule_pins_github_actions_for_every_context():
    checks = _documented_checks()
    assert {c["context"] for c in checks} == {
        "Test & Quality Checks (3.11, 22)",
        "CodeQL (python)",
        "CodeQL (javascript)",
        "Security Scan",
        "Image Scan (backend)",
        "Image Scan (frontend)",
        "Image Scan (mcp)",
    }
    assert all(c["integration_id"] == GITHUB_ACTIONS_APP_ID for c in checks)


def test_every_required_context_runs_on_every_pull_request_without_secrets():
    produced = {}
    for name, workflow in _workflows().items():
        for job_id, job in workflow["jobs"].items():
            for context in _contexts(job_id, job):
                produced[context] = (name, workflow, job)

    for check in _documented_checks():
        context = check["context"]
        assert context in produced, f"no job reports {context!r}"
        name, workflow, job = produced[context]
        pr = _triggers(workflow).get("pull_request")
        assert pr is not None, f"{name} does not run on pull requests"
        assert pr.get("branches") == ["main"], name
        # A path filter would leave the required check pending forever.
        for key in ("paths", "paths-ignore", "branches-ignore"):
            assert key not in pr, f"{name} filters pull requests by {key}"
        assert job["runs-on"] == "ubuntu-latest", context
        assert "secrets." not in yaml.safe_dump(
            job
        ), f"{context} reads a repository secret"


def test_no_pull_request_code_runs_on_a_self_hosted_runner():
    for name, workflow in _workflows().items():
        if not set(PR_EVENTS) & set(_triggers(workflow)):
            continue
        for job_id, job in workflow["jobs"].items():
            runs_on = json.dumps(job.get("runs-on"))
            assert not any(
                label in runs_on for label in SELF_HOSTED
            ), f"{name}:{job_id}"


def test_deploy_test_runs_after_merge_and_on_demand_only():
    workflow = _workflows()["main.yml"]
    triggers = _triggers(workflow)
    assert set(triggers) == {"push", "workflow_dispatch"}
    assert triggers["push"] == {"branches": ["main"]}
    assert (
        workflow["jobs"]["deploy-and-test"]["runs-on"]
        == "arc-runners-org-nvidia-ai-bp-4-gpu"
    )
