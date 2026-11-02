#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Publish the internal NGC MAIW pytest result as its own commit check.

The deployment workflow (.github/workflows/main.yml) passes when the
deployment and readiness checks pass, even if the internal NGC test image
could not be pulled and ``pytest -m maiw`` never ran. Its warning
annotation and job summary say so, but the commit still shows one green
check. This script adds a separate check run, "MAIW internal pytest (NGC)",
on the same commit:

    E2E=PASSED   -> success
    E2E=FAILED   -> failure
    E2E=NOT_RUN  -> neutral, titled "NOT RUN: <reason>"
    (unset)      -> neutral, "NOT RUN: the step did not report a result"

so a commit chosen as a release candidate shows plainly whether the suite
ran (docs/operations/RELEASING.md).

Environment: E2E, REASON (from the pytest step), RUN_URL, GITHUB_TOKEN,
GITHUB_REPOSITORY, GITHUB_SHA, GITHUB_API_URL. ``--dry-run`` prints the
request body instead of sending it. A failed request only warns: reporting
must not change the deployment result.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request

CHECK_NAME = "MAIW internal pytest (NGC)"

_CONCLUSIONS = {"PASSED": "success", "FAILED": "failure"}


def build_check_run(e2e: str, reason: str, run_url: str, sha: str) -> dict:
    e2e = (e2e or "").strip().upper()
    conclusion = _CONCLUSIONS.get(e2e, "neutral")
    if e2e == "PASSED":
        title = "PASSED"
    elif e2e == "FAILED":
        title = "FAILED"
    else:
        title = f"NOT RUN: {reason.strip() or 'the step did not report a result'}"
    summary = (
        f"Internal NGC MAIW UI suite (`pytest -m maiw`): **{title}**.\n\n"
        f"Deployment test run: {run_url}\n\n"
        "NOT RUN means the suite did not execute, which is not a pass. "
        "Release notes must report it as NOT RUN "
        "(docs/operations/RELEASING.md)."
    )
    return {
        "name": CHECK_NAME,
        "head_sha": sha,
        "status": "completed",
        "conclusion": conclusion,
        "details_url": run_url,
        "output": {"title": title, "summary": summary},
    }


def _post(body: dict) -> None:
    api = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    url = f"{api}/repos/{os.environ['GITHUB_REPOSITORY']}/check-runs"
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        print(f"Posted check '{CHECK_NAME}': {body['output']['title']} ({response.status})")


def main(argv: list[str]) -> int:
    body = build_check_run(
        os.environ.get("E2E", ""),
        os.environ.get("REASON", ""),
        os.environ.get("RUN_URL", ""),
        os.environ.get("GITHUB_SHA", ""),
    )
    if "--dry-run" in argv:
        print(json.dumps(body, indent=2))
        return 0
    try:
        _post(body)
    except Exception as exc:  # reporting must never fail the deployment job
        print(f"::warning title=MAIW pytest check not posted::{exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
