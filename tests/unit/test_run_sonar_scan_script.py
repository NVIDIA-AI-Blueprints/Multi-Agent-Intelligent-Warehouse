# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
scripts/security/run_sonar_scan.sh records the analysis and reports why it failed.

The first real run (main 0ee535a, 2026-11-02) uploaded an analysis whose
quality gate failed, yet the script wrote no evidence and exited 3, its own
code for "server unreachable":

- the scanner image keeps its working directory in the container's /tmp, so
  report-task.txt vanished with ``docker run --rm``;
- the scanner's exit code (3 = quality gate failed) was passed through.

Each test runs the real script against a throwaway git checkout with stub
``docker`` and ``curl`` on PATH.  The docker stub writes report-task.txt where
``sonar.scanner.metadataFilePath`` points (mapped back through the ``/usr/src``
mount) and exits with the scanner code under test.  No container runs and no
network is used.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "security" / "run_sonar_scan.sh"

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="bash script under test"
)

DOCKER_STUB = r"""#!/usr/bin/env bash
printf '%s\n' "$@" > "$STUB_DIR/docker.args"
src=""; meta=""
prev=""
for a in "$@"; do
  if [[ "$prev" == "-v" && "$a" == *":/usr/src" ]]; then src="${a%:/usr/src}"; fi
  case "$a" in -Dsonar.scanner.metadataFilePath=*) meta="${a#*=}";; esac
  prev="$a"
done
if [[ "${FAKE_WRITE_REPORT:-1}" == 1 && -n "$src" && "$meta" == /usr/src/* ]]; then
  out="$src/${meta#/usr/src/}"
  mkdir -p "$(dirname "$out")"
  printf 'ceTaskId=TASK1\ndashboardUrl=https://sonar.example/dashboard?id=P\n' > "$out"
fi
exit "${FAKE_SCANNER_EXIT:-0}"
"""

CURL_STUB = r"""#!/usr/bin/env bash
cat > /dev/null 2>&1 || true  # the token config arrives on stdin (-K -)
url="${@: -1}"
case "$url" in
  */api/server/version) [[ "${FAKE_UNREACHABLE:-0}" == 1 ]] && exit 7; echo "2026.3.1";;
  */api/ce/task*) echo '{"task":{"analysisId":"AN1","status":"SUCCESS","branch":"main"}}';;
  */api/qualitygates/project_status*) printf '{"projectStatus":{"status":"%s","conditions":[]}}' "${FAKE_GATE:-OK}";;
  *) exit 22;;
esac
"""


@pytest.fixture()
def run(tmp_path):
    stubs = tmp_path / "bin"
    stubs.mkdir()
    for name, body in (("docker", DOCKER_STUB), ("curl", CURL_STUB)):
        stub = stubs / name
        stub.write_text(body)
        stub.chmod(0o755)

    src = tmp_path / "src"
    src.mkdir()
    git = ["git", "-C", str(src), "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run(["git", "init", "-q", str(src)], check=True)
    (src / "a.py").write_text("x = 1\n")
    subprocess.run([*git, "add", "a.py"], check=True)
    subprocess.run([*git, "commit", "-qm", "init"], check=True)
    subprocess.run([*git, "tag", "v9.8.7"], check=True)

    settings = tmp_path / "sonar-project.properties"
    settings.write_text("sonar.projectKey=P\n")
    evidence = tmp_path / "evidence.json"

    def _run(**fake):
        env = {
            "PATH": f"{stubs}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(tmp_path),
            "SONAR_TOKEN": "tok-not-on-argv",
            "SONAR_HOST_URL": "https://sonar.example",
            "MAIW_SONAR_SOURCE_DIR": str(src),
            "MAIW_SONAR_SETTINGS": str(settings),
            "MAIW_SONAR_EVIDENCE": str(evidence),
            "STUB_DIR": str(tmp_path),
            **{k: str(v) for k, v in fake.items()},
        }
        proc = subprocess.run(
            ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60
        )
        args_file = tmp_path / "docker.args"
        docker_args = args_file.read_text().splitlines() if args_file.exists() else []
        ev = json.loads(evidence.read_text()) if evidence.exists() else None
        return proc, docker_args, ev

    return _run


def test_passing_gate_exits_0_and_records_the_analysis(run):
    proc, docker_args, ev = run(FAKE_SCANNER_EXIT=0, FAKE_GATE="OK")
    assert proc.returncode == 0, proc.stderr
    assert (
        "-Dsonar.scanner.metadataFilePath=/usr/src/.scannerwork/report-task.txt"
        in docker_args
    )
    assert "tok-not-on-argv" not in "\n".join(docker_args)
    assert ev["analysis_id"] == "AN1"
    assert ev["quality_gate_status"] == "OK"
    assert ev["project_version"] == "9.8.7"


def test_failed_quality_gate_exits_5_with_evidence_not_the_scanners_3(run):
    proc, _, ev = run(FAKE_SCANNER_EXIT=3, FAKE_GATE="ERROR")
    assert proc.returncode == 5, proc.stderr
    assert "quality gate failed" in proc.stderr
    assert "not recorded" not in proc.stderr
    assert ev["analysis_id"] == "AN1"
    assert ev["quality_gate_status"] == "ERROR"
    assert ev["scanner_exit_code"] == 3


def test_scanner_failure_without_analysis_exits_4(run):
    proc, _, ev = run(FAKE_SCANNER_EXIT=1, FAKE_WRITE_REPORT=0)
    assert proc.returncode == 4
    assert "not recorded" in proc.stderr
    assert ev is None


def test_scanner_failure_with_unknown_gate_exits_4(run):
    proc, _, ev = run(FAKE_SCANNER_EXIT=2, FAKE_GATE="")
    assert proc.returncode == 4
    assert ev["analysis_id"] == "AN1"


def test_unreachable_server_exits_3_before_scanning(run):
    proc, docker_args, ev = run(FAKE_UNREACHABLE=1)
    assert proc.returncode == 3
    assert docker_args == []
    assert ev is None


def test_missing_token_exits_2(run):
    proc, docker_args, _ = run(SONAR_TOKEN="")
    assert proc.returncode == 2
    assert docker_args == []
