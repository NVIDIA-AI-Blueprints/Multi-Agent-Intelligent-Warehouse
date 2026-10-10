#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# validate_reference_runbook.sh — executable check that the reference
# deployment runbook is complete and consistent with the scripts
# (v2.0.1 round 2, NEW-P1-02 §49).
#
# Checks:
#   1. every `bash scripts/...` command and repo path in the runbook's
#      "Clean-host procedure" block exists
#   2. every variable a lifecycle script REQUIRES (maiw_require_vars) is
#      documented (assigned or shown) in .env.example AND named in the runbook
#   3. the runbook has the Database, Sandbox, MCP, Deployment Profiles and
#      Deployment identity sections, and the sandbox policy template exists
#   4. no lifecycle script assumes a default API port / kills by port or name
#
# Exit 0 = consistent; 1 = a finding (each printed).
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
RUNBOOK="$ROOT/docs/operations/REFERENCE_DEPLOYMENT_RUNBOOK.md"
ENV_EXAMPLE="$ROOT/.env.example"

exec python3 - "$ROOT" "$RUNBOOK" "$ENV_EXAMPLE" <<'PYEOF'
import re, sys
from pathlib import Path

root, runbook_path, env_example_path = map(Path, sys.argv[1:4])
runbook = runbook_path.read_text()
env_example = env_example_path.read_text()
findings = []

# 1. clean-host block commands / paths exist
m = re.search(r"## Clean-host procedure.*?```bash\n(.*?)```", runbook, re.S)
if not m:
    findings.append("runbook: no 'Clean-host procedure' bash block")
    block = ""
else:
    block = m.group(1)
for script in sorted(set(re.findall(r"bash (scripts/[\w./-]+\.sh)", block))):
    if not (root / script).is_file():
        findings.append(f"clean-host procedure names missing script {script}")
for rel in ("requirements.txt", ".env.example", "apps/api"):
    if rel in block and not (root / rel).exists():
        findings.append(f"clean-host procedure names missing path {rel}")
for pkg in re.findall(r"for p in ([\w -]+); do", block):
    for name in pkg.split():
        if not (root / "packages" / name).is_dir():
            findings.append(f"clean-host procedure installs missing package {name}")

# 2. required variables documented
lifecycle = [
    "preflight_reference_deployment.sh", "start_reference_deployment.sh",
    "stop_reference_deployment.sh", "restart_reference_deployment.sh",
    "status_reference_deployment.sh", "smoke_test_reference_deployment.sh",
    "qualify_reference_deployment.sh", "setup/reference_db.sh",
    "setup/reference_sandbox.sh",
]
required = set()
for name in lifecycle:
    text = (root / "scripts" / name).read_text()
    for line in re.findall(r"maiw_require_vars ([A-Z0-9_ ]+)", text):
        required.update(line.split())
for var in sorted(required):
    if not re.search(rf"^\s*#?\s*{var}=", env_example, re.M):
        findings.append(f".env.example does not document required variable {var}")
    if var not in runbook:
        findings.append(f"runbook does not mention required variable {var}")

# 3. sections + policy template
for heading in ("## Database", "## Sandbox", "### MCP", "## Deployment Profiles",
                "## Deployment identity", "## Preflight", "## Readiness"):
    if heading not in runbook:
        findings.append(f"runbook missing section '{heading}'")
if not (root / "deploy/openshell/maiw-inference-only.policy.yaml.tmpl").is_file():
    findings.append("sandbox policy template missing")

# 4. no default port / kill-by-port / kill-by-name in lifecycle scripts
for name in lifecycle:
    text = (root / "scripts" / name).read_text()
    for bad in ("MAIW_API_PORT:-8001", "lsof -ti", "pgrep -f", "pkill"):
        if bad in text:
            findings.append(f"scripts/{name} contains forbidden pattern {bad!r}")

for f in findings:
    print(f"FAIL  {f}")
if findings:
    print(f"\nRUNBOOK VALIDATION FAILED ({len(findings)} finding(s))")
    sys.exit(1)
print(f"RUNBOOK VALIDATION PASSED ({len(required)} required variables documented; "
      f"{len(lifecycle)} lifecycle scripts checked)")
PYEOF
