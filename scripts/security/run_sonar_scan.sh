#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Run the NVIDIA SonarQube analysis of a checkout and record what happened.
#
# Used by .github/workflows/sonarqube.yml and for manual runs from a host on
# the NVIDIA network (sonar.nvidia.com resolves to a private address, so
# GitHub-hosted runners cannot reach it).
#
#   export SONAR_TOKEN            # read it without echoing: read -rs SONAR_TOKEN
#   scripts/security/run_sonar_scan.sh
#
# Environment
#   SONAR_TOKEN          required; passed to the scanner by name only, never
#                        on a command line
#   SONAR_HOST_URL       default https://sonar.nvidia.com
#   MAIW_SONAR_BRANCH    branch analysis name (default: none = main branch)
#   MAIW_SONAR_PR_KEY / MAIW_SONAR_PR_BRANCH / MAIW_SONAR_PR_BASE
#                        pull-request analysis instead of branch analysis
#   MAIW_SONAR_QG_WAIT   wait for the quality gate and fail on ERROR (default true)
#   MAIW_SONAR_EVIDENCE  where to write the evidence JSON
#                        (default .scannerwork/maiw-sonar-evidence.json)
#   MAIW_SONAR_SOURCE_DIR  checkout to analyze (default: the one containing
#                        the current directory)
#   MAIW_RELEASE_VERSION projectVersion for a release candidate (see
#                        release_version.sh next to this script; default:
#                        the tag, or a development version such as
#                        2.1.1+16.g4d2e0c4)
#   MAIW_SONAR_SETTINGS  sonar-project.properties to use (default: the one
#                        next to this script, not the analyzed checkout's).
#                        CI runs this script and these settings from the
#                        default branch, so the analyzed commit never
#                        controls the step that holds SONAR_TOKEN.
#
# Exit codes (the scanner's own exit code is recorded in the evidence, never
# passed through: its 3 means "quality gate failed", which is not ours):
#   0  analysis processed (and quality gate passed when waited for)
#   2  configuration missing
#   3  server unreachable
#   4  scanner failed; no analysis recorded, or its quality gate is unknown
#   5  analysis recorded, quality gate failed
# The evidence file is written whenever an analysis was recorded (0, 4, 5).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
SCANNER_IMAGE="sonarsource/sonar-scanner-cli:12.3.0.4285_8.1.0@sha256:47956b669bf486bdad919e1cbd0533223515aa0b6d1d31763e5a3754942df6d7"
HOST="${SONAR_HOST_URL:-https://sonar.nvidia.com}"
HOST="${HOST%/}"
EVIDENCE="${MAIW_SONAR_EVIDENCE:-.scannerwork/maiw-sonar-evidence.json}"
SETTINGS="${MAIW_SONAR_SETTINGS:-$(dirname "${BASH_SOURCE[0]}")/../../sonar-project.properties}"
if [ ! -f "$SETTINGS" ]; then
  echo "::error title=SonarQube not configured::settings file ${SETTINGS} not found" >&2
  exit 2
fi
SETTINGS="$(cd "$(dirname "$SETTINGS")" && pwd -P)/$(basename "$SETTINGS")"

cd "${MAIW_SONAR_SOURCE_DIR:-.}"
cd "$(git rev-parse --show-toplevel)"

if [ -z "${SONAR_TOKEN:-}" ]; then
  echo "::error title=SonarQube not configured::SONAR_TOKEN is not set" >&2
  exit 2
fi

# Reachability first, so a network problem is reported as one.
if ! server_version="$(curl -fsS -m 20 "${HOST}/api/server/version")"; then
  echo "::error title=SonarQube unreachable::${HOST} is not reachable from this runner. sonar.nvidia.com is on the NVIDIA network: run on an NVIDIA-network runner (repository variable MAIW_SONAR_RUNNER) or host." >&2
  exit 3
fi
echo "SonarQube server ${HOST} version ${server_version}"

revision="$(git rev-parse HEAD)"
# The version this commit is analyzed as (release_version.sh next to this
# script, i.e. the trusted copy, run inside the analyzed checkout).
if ! version="$("${SCRIPT_DIR}/release_version.sh")"; then
  echo "::error title=SonarQube not configured::invalid MAIW_RELEASE_VERSION" >&2
  exit 2
fi

args=(
  "-Dsonar.host.url=${HOST}"
  "-Dproject.settings=/opt/maiw-sonar/sonar-project.properties"
  "-Dsonar.projectBaseDir=/usr/src"
  # The scanner image keeps its working directory in the container's /tmp,
  # which --rm deletes; write the analysis metadata into the checkout.
  "-Dsonar.scanner.metadataFilePath=/usr/src/.scannerwork/report-task.txt"
  "-Dsonar.projectVersion=${version}"
  "-Dsonar.scm.revision=${revision}"
  "-Dsonar.qualitygate.wait=${MAIW_SONAR_QG_WAIT:-true}"
  "-Dsonar.qualitygate.timeout=600"
)
if [ -n "${MAIW_SONAR_PR_KEY:-}" ]; then
  args+=(
    "-Dsonar.pullrequest.key=${MAIW_SONAR_PR_KEY}"
    "-Dsonar.pullrequest.branch=${MAIW_SONAR_PR_BRANCH:?MAIW_SONAR_PR_BRANCH is required with MAIW_SONAR_PR_KEY}"
    "-Dsonar.pullrequest.base=${MAIW_SONAR_PR_BASE:-main}"
  )
elif [ -n "${MAIW_SONAR_BRANCH:-}" ] && [ "${MAIW_SONAR_BRANCH}" != "main" ]; then
  args+=("-Dsonar.branch.name=${MAIW_SONAR_BRANCH}")
fi

if [ -f coverage.xml ]; then
  echo "Python coverage: coverage.xml"
else
  echo "::warning title=No Python coverage::coverage.xml not found; SonarQube will report 0% Python coverage" >&2
fi

echo "Analyzing ${revision} as version ${version} with settings ${SETTINGS}"
report=.scannerwork/report-task.txt
mkdir -p .scannerwork
rm -f "$report"
set +e
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e SONAR_TOKEN \
  -e SONAR_USER_HOME=/usr/src/.scannerwork/.sonar \
  -v "$PWD:/usr/src" \
  -v "$SETTINGS:/opt/maiw-sonar/sonar-project.properties:ro" \
  -w /usr/src \
  "${SCANNER_IMAGE}" "${args[@]}"
scanner_exit=$?
set -e

# Record the analysis that this run produced, from the server's own records.
gate_status=""
if [ -f "$report" ]; then
  task_id="$(sed -n 's/^ceTaskId=//p' "$report")"
  dashboard="$(sed -n 's/^dashboardUrl=//p' "$report")"
  # The token goes to curl through stdin (-K -), not argv.
  api() { printf 'user = "%s:"\n' "$SONAR_TOKEN" | curl -fsS -m 30 -K - "${HOST}$1"; }
  task_json="$(api "/api/ce/task?id=${task_id}" || echo '{}')"
  analysis_id="$(printf '%s' "$task_json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("task",{}).get("analysisId",""))' 2>/dev/null || true)"
  gate_json='{}'
  if [ -n "$analysis_id" ]; then
    gate_json="$(api "/api/qualitygates/project_status?analysisId=${analysis_id}" || echo '{}')"
  fi
  mkdir -p "$(dirname "$EVIDENCE")"
  TASK_JSON="$task_json" GATE_JSON="$gate_json" python3 - "$EVIDENCE" <<EOF
import json, os, sys
task = json.loads(os.environ["TASK_JSON"] or "{}").get("task", {})
gate = json.loads(os.environ["GATE_JSON"] or "{}").get("projectStatus", {})
evidence = {
    "scan_type": "sonarqube",
    "server": "${HOST}",
    "server_version": "${server_version}",
    "scanner_image": "${SCANNER_IMAGE}",
    "project_key": "TEGRASW_Blueprints-SRE_warehouse-operational-assistant_Multi-Agent-Intelligent-Warehouse",
    "git_sha": "${revision}",
    "project_version": "${version}",
    "branch": task.get("branch"),
    "pull_request": task.get("pullRequest"),
    "ce_task_id": "${task_id}",
    "ce_task_status": task.get("status"),
    "analysis_id": task.get("analysisId"),
    "executed_at": task.get("executedAt"),
    "dashboard_url": "${dashboard}",
    "quality_gate_status": gate.get("status"),
    "quality_gate_conditions": gate.get("conditions", []),
    "scanner_exit_code": ${scanner_exit},
}
json.dump(evidence, open(sys.argv[1], "w"), indent=2)
print(json.dumps({k: evidence[k] for k in ("git_sha", "analysis_id", "executed_at", "quality_gate_status", "dashboard_url")}, indent=2))
EOF
  gate_status="$(printf '%s' "$gate_json" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("projectStatus",{}).get("status",""))' 2>/dev/null || true)"
fi

if [ "$scanner_exit" -eq 0 ]; then
  exit 0
fi
if [ ! -f "$report" ]; then
  echo "::error title=SonarQube analysis not recorded::the scanner exited ${scanner_exit} without writing ${report}" >&2
  exit 4
fi
if [ "$gate_status" = "ERROR" ]; then
  echo "::error title=SonarQube quality gate failed::analysis recorded; see ${dashboard}" >&2
  exit 5
fi
echo "::error title=SonarQube scanner failed::the scanner exited ${scanner_exit}; quality gate status '${gate_status:-unknown}'" >&2
exit 4
