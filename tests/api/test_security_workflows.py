# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Guards for the security-scanning workflows.

SonarQube and CodeQL both stopped analyzing main without anyone noticing:
#71 replaced sonarqube.yml with a mirror placeholder and cut codeql.yml down
to manual dispatch (docs/security/sonarqube-root-cause-analysis.md). These
static checks keep them wired, scoped to the whole code base, and safe to
run with internal credentials.
"""

from __future__ import annotations

import configparser
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
PROJECT_KEY = "TEGRASW_Blueprints-SRE_warehouse-operational-assistant_Multi-Agent-Intelligent-Warehouse"


def _workflow(name: str) -> dict:
    data = yaml.safe_load((WORKFLOWS / name).read_text())
    # PyYAML reads the bare key `on` as True.
    data["on"] = data.pop(True, data.get("on"))
    return data


def _sonar_properties() -> dict[str, str]:
    parser = configparser.ConfigParser(delimiters=("=",), interpolation=None)
    parser.optionxform = str
    parser.read_string("[p]\n" + (REPO_ROOT / "sonar-project.properties").read_text())
    return dict(parser["p"])


# ── SonarQube ─────────────────────────────────────────────────────────────────


def test_sonarqube_runs_after_ci_for_main_and_same_repo_pull_requests():
    wf = _workflow("sonarqube.yml")
    assert wf["on"]["workflow_run"] == {
        "workflows": ["CI/CD Pipeline"],
        "types": ["completed"],
    }
    assert "workflow_dispatch" in wf["on"]
    condition = wf["jobs"]["sonarqube"]["if"]
    # workflow_run carries this repository's secrets: forks must never run.
    assert (
        "github.event.workflow_run.head_repository.full_name == github.repository"
        in condition
    )
    assert "github.event.workflow_run.conclusion == 'success'" in condition
    assert "github.event.workflow_run.head_branch == 'main'" in condition


def test_sonarqube_is_least_privilege_and_never_inlines_the_token():
    wf = _workflow("sonarqube.yml")
    assert wf["permissions"] == {}
    job = wf["jobs"]["sonarqube"]
    assert job["permissions"] == {"contents": "read", "actions": "read"}
    checkouts = [
        s for s in job["steps"] if s.get("uses", "").startswith("actions/checkout")
    ]
    assert checkouts
    for checkout in checkouts:
        assert checkout["with"]["persist-credentials"] is False
    for step in job["steps"]:
        assert "secrets." not in step.get("run", "")
    scan = next(s for s in job["steps"] if s.get("name") == "Run SonarQube analysis")
    assert scan["env"]["SONAR_TOKEN"] == "${{ secrets.SONAR_TOKEN }}"


def test_sonarqube_runs_trusted_tooling_against_the_analyzed_commit():
    # The scan step holds SONAR_TOKEN, so its script and settings come from
    # the commit the workflow runs from, never from the pull request under
    # analysis; that commit is checked out apart and only scanned. PR branches
    # cut before the script existed failed with exit 127 when it ran from the
    # analyzed checkout.
    steps = _workflow("sonarqube.yml")["jobs"]["sonarqube"]["steps"]
    by_name = {s.get("name"): s for s in steps}
    tools = by_name["Checkout trusted scan tooling"]["with"]
    assert tools["ref"] == "${{ github.sha }}"
    assert tools["path"] == "sonar-tools"
    assert set(tools["sparse-checkout"].split()) == {
        "scripts/security/run_sonar_scan.sh",
        "sonar-project.properties",
    }
    source = by_name["Checkout analyzed commit"]["with"]
    assert source["ref"] == "${{ steps.target.outputs.sha }}"
    assert source["path"] == "source"
    assert source["fetch-depth"] == 0
    coverage = by_name["Download coverage from the CI/CD Pipeline run"]["with"]
    assert coverage["path"] == "source"
    assert coverage["run-id"] == "${{ steps.target.outputs.ci_run_id }}"
    scan = by_name["Run SonarQube analysis"]
    assert scan["run"] == "sonar-tools/scripts/security/run_sonar_scan.sh"
    assert scan["env"]["MAIW_SONAR_SOURCE_DIR"] == "source"
    assert scan["env"]["MAIW_SONAR_SETTINGS"] == "sonar-tools/sonar-project.properties"
    # Tooling is in place before any step that uses it.
    names = [s.get("name") for s in steps]
    assert names.index("Checkout trusted scan tooling") < names.index(
        "Run SonarQube analysis"
    )

    script = (REPO_ROOT / "scripts/security/run_sonar_scan.sh").read_text()
    # The scanner reads the trusted settings, mounted read-only, not the
    # analyzed checkout's sonar-project.properties.
    assert '-v "$SETTINGS:/opt/maiw-sonar/sonar-project.properties:ro"' in script
    assert "-Dproject.settings=/opt/maiw-sonar/sonar-project.properties" in script
    assert "-Dsonar.projectBaseDir=/usr/src" in script


def test_sonarqube_runner_is_configurable_and_reachability_is_checked():
    job = _workflow("sonarqube.yml")["jobs"]["sonarqube"]
    assert job["runs-on"] == "${{ vars.MAIW_SONAR_RUNNER || 'ubuntu-latest' }}"
    script = (REPO_ROOT / "scripts/security/run_sonar_scan.sh").read_text()
    # An unreachable server or missing token fails the job; it never passes
    # without a scan.
    assert re.search(r"/api/server/version.*\n.*\n\s*exit 3", script)
    assert re.search(r'-z "\$\{SONAR_TOKEN:-\}".*\n.*\n\s*exit 2', script)


def test_scan_script_pins_the_scanner_and_keeps_the_token_off_command_lines():
    script = (REPO_ROOT / "scripts/security/run_sonar_scan.sh").read_text()
    assert re.search(
        r'SCANNER_IMAGE="sonarsource/sonar-scanner-cli:[\d._]+@sha256:[0-9a-f]{64}"',
        script,
    )
    assert "-e SONAR_TOKEN \\" in script  # by name: docker reads the value from env
    assert "sonar.token=" not in script and "sonar.login=" not in script
    assert "curl -fsS -m 30 -K -" in script  # token via stdin config
    assert "-Dsonar.qualitygate.wait=" in script
    assert "-Dsonar.scm.revision=" in script


def test_ci_publishes_coverage_for_sonarqube():
    steps = _workflow("ci-cd.yml")["jobs"]["test"]["steps"]
    upload = next(s for s in steps if s.get("name") == "Upload coverage for SonarQube")
    assert upload["with"]["name"] == "sonar-coverage"
    assert upload["with"]["path"] == "coverage.xml"
    pyproject = (REPO_ROOT / "pyproject.toml").read_text()
    assert "relative_files = true" in pyproject


def test_sonar_scope_covers_every_first_party_code_area():
    props = _sonar_properties()
    assert props["sonar.projectKey"] == PROJECT_KEY
    sources = props["sonar.sources"].split(",")
    for area in ("src", "apps", "packages", "mcp_servers", "integrations", "scripts"):
        assert area in sources
        assert (REPO_ROOT / area).is_dir()
    for dockerfile in REPO_ROOT.glob("Dockerfile*"):
        assert dockerfile.name in sources
    # Exclusions are generated/vendored output and test files only.
    for pattern in props["sonar.exclusions"].split(","):
        assert not any(
            pattern.startswith(f"{area}/") for area in sources
        ), f"first-party directory excluded: {pattern}"


def test_sonar_classifies_colocated_tests_as_tests():
    props = _sonar_properties()
    inclusions = props["sonar.test.inclusions"].split(",")
    exclusions = props["sonar.exclusions"].split(",")
    for pattern in ("**/tests/**", "**/test_*.py", "**/__tests__/**", "**/*.test.tsx"):
        assert pattern in inclusions
        assert pattern in exclusions  # so no file is both source and test


# ── CodeQL ────────────────────────────────────────────────────────────────────


def test_codeql_runs_on_push_pull_request_and_schedule():
    wf = _workflow("codeql.yml")
    assert wf["on"]["push"] == {"branches": ["main"]}
    assert wf["on"]["pull_request"] == {"branches": ["main"]}
    assert wf["on"]["schedule"]
    job = wf["jobs"]["analyze"]
    assert job["permissions"]["security-events"] == "write"
    assert set(job["strategy"]["matrix"]["language"]) == {"python", "javascript"}
