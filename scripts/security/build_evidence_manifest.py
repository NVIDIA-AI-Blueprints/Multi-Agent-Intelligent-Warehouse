#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Build the security evidence manifest for one or more commits from live sources.

    python3 scripts/security/build_evidence_manifest.py \\
        --target v2.1.0=2fdd9feac6d2... --target main=0fbcb69a48... \\
        --output docs/security/security-evidence-manifest.json

For each commit it records what each scanner actually did for that SHA:
- GitHub Actions runs of the CI/CD Pipeline, deployment test, CodeQL and
  SonarQube workflows (via the `gh` CLI, which must be authenticated);
- GitHub code-scanning analyses uploaded for the commit (CodeQL, Trivy
  filesystem and image categories) with their result counts;
- the SonarQube project's analysis of that exact revision, if any (anonymous
  read of sonar.nvidia.com; requires the NVIDIA network);
plus repository-wide state (open Dependabot and code-scanning alerts by
severity, secret-scanning alerts, the latest SonarQube analysis).

Anything that cannot be determined is written as null with a reason; nothing
is inferred. Approvals are not discoverable and are always null.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import subprocess
import sys
import urllib.parse
import urllib.request

REPO = "NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse"
SONAR = "https://sonar.nvidia.com"
SONAR_PROJECT = "TEGRASW_Blueprints-SRE_warehouse-operational-assistant_Multi-Agent-Intelligent-Warehouse"
WORKFLOWS = {
    "ci": "ci-cd.yml",
    "deployment_test": "main.yml",
    "codeql": "codeql.yml",
    "sonarqube": "sonarqube.yml",
}


def gh(path: str) -> object:
    out = subprocess.run(
        ["gh", "api", "--paginate", path], check=True, capture_output=True, text=True
    ).stdout
    # --paginate concatenates JSON arrays/objects; normalise to one value.
    decoder, items, idx = json.JSONDecoder(), [], 0
    while idx < len(out):
        while idx < len(out) and out[idx].isspace():
            idx += 1
        if idx >= len(out):
            break
        value, idx = decoder.raw_decode(out, idx)
        items.append(value)
    if len(items) == 1:
        return items[0]
    if all(isinstance(i, list) for i in items):
        return [x for i in items for x in i]
    return items


def sonar(path: str, **params: str) -> dict | None:
    url = f"{SONAR}{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            return json.load(response)
    except Exception as exc:  # unreachable off the NVIDIA network
        return {"_error": f"{type(exc).__name__}: {exc}"}


def workflow_runs(sha: str) -> dict:
    result = {}
    for key, workflow in WORKFLOWS.items():
        try:
            runs = gh(f"repos/{REPO}/actions/workflows/{workflow}/runs?head_sha={sha}&per_page=20")
            runs = runs.get("workflow_runs", []) if isinstance(runs, dict) else []
        except subprocess.CalledProcessError as exc:
            result[key] = {"status": None, "reason": f"gh api failed: {exc.stderr.strip()[:200]}"}
            continue
        if not runs:
            result[key] = {"status": None, "reason": "no run for this commit"}
            continue
        run = runs[0]
        result[key] = {
            "workflow": workflow,
            "run_url": run["html_url"],
            "event": run["event"],
            "status": run["status"],
            "conclusion": run["conclusion"],
            "executed_at": run["run_started_at"],
        }
    return result


def code_scanning(sha: str) -> list[dict]:
    try:
        # The endpoint has no commit filter; match commit_sha here.
        analyses = gh(f"repos/{REPO}/code-scanning/analyses?per_page=100")
    except subprocess.CalledProcessError:
        return []
    latest = {}
    for a in analyses if isinstance(analyses, list) else []:
        if a.get("commit_sha") != sha:
            continue
        key = (a["tool"]["name"], a["category"])
        if key not in latest or a["created_at"] > latest[key]["created_at"]:
            latest[key] = a
    return [
        {
            "scan_type": f"{tool} ({category})",
            "scanner": tool,
            "scanner_version": a["tool"].get("version"),
            "executed_at": a["created_at"],
            "results_count": a["results_count"],
            "analysis_url": a["url"],
        }
        for (tool, category), a in sorted(latest.items())
    ]


def sonar_for(sha: str) -> dict:
    data = sonar("/api/project_analyses/search", project=SONAR_PROJECT, ps="500")
    if not data or "_error" in data:
        return {"status": None, "reason": (data or {}).get("_error", "no response")}
    for analysis in data.get("analyses", []):
        if analysis.get("revision") == sha:
            return {
                "status": "analyzed",
                "analysis_key": analysis["key"],
                "executed_at": analysis["date"],
                "project_version": analysis.get("projectVersion"),
                "dashboard_url": f"{SONAR}/dashboard?id={SONAR_PROJECT}",
            }
    return {"status": None, "reason": "no SonarQube analysis of this revision"}


def repository_state() -> dict:
    state: dict = {}
    try:
        alerts = gh(f"repos/{REPO}/dependabot/alerts?state=open&per_page=100")
        state["dependabot_open_alerts"] = dict(
            collections.Counter(a["security_advisory"]["severity"] for a in alerts)
        )
    except subprocess.CalledProcessError as exc:
        state["dependabot_open_alerts"] = None
        state["dependabot_reason"] = exc.stderr.strip()[:200]
    try:
        alerts = gh(f"repos/{REPO}/code-scanning/alerts?state=open&per_page=100")
        state["code_scanning_open_alerts"] = dict(
            collections.Counter(
                f"{a['tool']['name']}:{a['rule'].get('security_severity_level') or a['rule'].get('severity')}"
                for a in alerts
            )
        )
    except subprocess.CalledProcessError:
        state["code_scanning_open_alerts"] = None
    try:
        alerts = gh(f"repos/{REPO}/secret-scanning/alerts?state=open&per_page=100")
        state["secret_scanning_open_alerts"] = len(alerts)
    except subprocess.CalledProcessError:
        state["secret_scanning_open_alerts"] = None
    component = sonar("/api/components/show", component=SONAR_PROJECT)
    gate = sonar("/api/qualitygates/project_status", projectKey=SONAR_PROJECT)
    if component and "_error" not in component:
        c = component["component"]
        state["sonarqube_latest_analysis"] = {
            "executed_at": c.get("analysisDate"),
            "project_version": c.get("version"),
            "quality_gate_status": (gate or {}).get("projectStatus", {}).get("status"),
            "dashboard_url": f"{SONAR}/dashboard?id={SONAR_PROJECT}",
        }
    else:
        state["sonarqube_latest_analysis"] = None
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", action="append", required=True, help="label=sha")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    targets = []
    for spec in args.target:
        label, sha = spec.split("=", 1)
        targets.append(
            {
                "label": label,
                "git_sha": sha,
                "workflow_runs": workflow_runs(sha),
                "code_scanning": code_scanning(sha),
                "sonarqube": sonar_for(sha),
            }
        )
    manifest = {
        "schema": "maiw-security-evidence/1",
        "repository": f"https://github.com/{REPO}",
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "generator": "scripts/security/build_evidence_manifest.py",
        "nspect": {"id": "NSPECT-NJMX-9GQU", "component": "MAIW-Core", "branch": "main"},
        "targets": targets,
        "repository_state": repository_state(),
        "approvals": None,
    }
    with open(args.output, "w") as fh:
        json.dump(manifest, fh, indent=2)
        fh.write("\n")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
