#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Run the NVIDIA SonarQube analysis of this checkout and record what happened.
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
#
# Exit codes: 0 analysis processed (and quality gate passed when waited for);
# 2 configuration missing; 3 server unreachable; other = scanner or quality
# gate failure (the evidence file is still written when an analysis exists).

set -euo pipefail

SCANNER_IMAGE="sonarsource/sonar-scanner-cli:12.3.0.4285_8.1.0@sha256:47956b669bf486bdad919e1cbd0533223515aa0b6d1d31763e5a3754942df6d7"
HOST="${SONAR_HOST_URL:-https://sonar.nvidia.com}"
HOST="${HOST%/}"
EVIDENCE="${MAIW_SONAR_EVIDENCE:-.scannerwork/maiw-sonar-evidence.json}"

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
# The release this commit belongs to: the latest v* tag reachable from it.
version="$(git describe --tags --abbrev=0 --match 'v[0-9]*' 2>/dev/null || echo v0.0.0)"
version="${version#v}"

args=(
  "-Dsonar.host.url=${HOST}"
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

echo "Analyzing ${revision} as version ${version}"
set +e
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e SONAR_TOKEN \
  -e SONAR_USER_HOME=/usr/src/.scannerwork/.sonar \
  -v "$PWD:/usr/src" \
  -w /usr/src \
  "${SCANNER_IMAGE}" "${args[@]}"
scanner_exit=$?
set -e

# Record the analysis that this run produced, from the server's own records.
report=.scannerwork/report-task.txt
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
else
  echo "::error title=SonarQube analysis not submitted::the scanner did not produce ${report}" >&2
fi

exit "$scanner_exit"
