#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# status_reference_deployment.sh — check status of the MAIW v2 reference deployment
#
# Reports (no secrets emitted):
#   - MAIW API status (liveness + readiness)
#   - ModelGateway readiness (via runtime status)
#   - Approved model / provider readiness
#   - OpenShell sandbox availability
#   - Persistence health
#   - GovernanceInbox health
#   - Stored / waiting / completed procedure counts (GET /api/v1/procedures)
#   - Readiness component breakdown (GET /api/v1/ready)
#
# Usage:
#   bash scripts/status_reference_deployment.sh [--json]
#
# Step 12 / Step 56 of Phase 20C-C.
# ---------------------------------------------------------------------------
set -euo pipefail

JSON_MODE="${1:-}"
MAIW_PERSISTENCE_ROOT="${MAIW_PERSISTENCE_ROOT:-/var/lib/maiw}"
MAIW_API_PORT="${MAIW_API_PORT:-8001}"
BASE_URL="http://127.0.0.1:${MAIW_API_PORT}"

# ── Helpers ───────────────────────────────────────────────────────────────────
_status() {
    local label="$1" value="$2" ok="${3:-true}"
    if [[ "$ok" == "true" ]]; then
        printf "  %-35s %s\n" "$label" "$value"
    else
        printf "  %-35s %s  [WARN]\n" "$label" "$value"
    fi
}

echo "=== MAIW v2 Reference Deployment — Status ==="
echo "Querying: $BASE_URL"
echo ""

# ── 1. Liveness ───────────────────────────────────────────────────────────────
echo "--- Process / Liveness ---"
LIVE_RESPONSE=$(curl -sf --max-time 5 "${BASE_URL}/api/v1/live" 2>/dev/null || echo "")
if [[ -n "$LIVE_RESPONSE" ]]; then
    LIVE_STATUS=$(echo "$LIVE_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null || echo "parse error")
    UPTIME=$(echo "$LIVE_RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('uptime','?'))" 2>/dev/null || echo "?")
    _status "MAIW API liveness" "$LIVE_STATUS (uptime: $UPTIME)"
else
    _status "MAIW API liveness" "NOT RESPONDING" "false"
fi

# ── 2. Readiness ──────────────────────────────────────────────────────────────
# v2.0.1: /api/v1/ready is computed from real dependencies (persistence,
# ModelGateway, governed write path, MCP domains, database) and returns 503
# NOT_READY with failed_components when any critical one is unavailable.
echo ""
echo "--- Readiness ---"
READY_RAW=$(curl -s --max-time 15 -w '\n%{http_code}' "${BASE_URL}/api/v1/ready" 2>/dev/null || echo -e "\n000")
READY_HTTP=$(echo "$READY_RAW" | tail -1)
READY_BODY=$(echo "$READY_RAW" | sed '$d')
[[ -z "$READY_BODY" ]] && READY_BODY="{}"
if [[ "$READY_HTTP" == "200" ]]; then
    _status "MAIW API readiness" "READY (HTTP 200)"
else
    _status "MAIW API readiness" "NOT READY (HTTP $READY_HTTP)" "false"
fi
echo "$READY_BODY" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print('    (no readiness body)'); sys.exit(0)
if d.get('failed_components'):
    print('    failed components: ' + ', '.join(d['failed_components']))
for k, v in (d.get('components') or {}).items():
    status = v.get('status', '?') if isinstance(v, dict) else v
    extra = ''
    if k == 'persistence' and isinstance(v, dict):
        extra = f\" (durable={v.get('durable')}, mode={v.get('mode')})\"
    print(f'    {k}: {status}{extra}')
" 2>/dev/null || echo "    (could not parse)"

# ── 3. ModelGateway / Runtime Status ──────────────────────────────────────────
echo ""
echo "--- ModelGateway / Runtime ---"
RUNTIME_RESP=$(curl -sf --max-time 5 "${BASE_URL}/api/v1/runtime/status" 2>/dev/null || echo "")
if [[ -n "$RUNTIME_RESP" ]]; then
    MG_STATUS=$(echo "$RUNTIME_RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
mg = d.get('model_gateway', {})
if isinstance(mg, dict):
    print(mg.get('status', str(mg)))
else:
    print(str(mg))
" 2>/dev/null || echo "?")
    _status "ModelGateway" "$MG_STATUS"
else
    _status "ModelGateway" "status endpoint not available" "false"
fi

# ── 4. Approved model provider ────────────────────────────────────────────────
echo ""
echo "--- Approved Model Provider ---"
NIM_URL="${LLM_NIM_URL:-https://integrate.api.nvidia.com/v1}"
MODEL_ID="${LLM_MODEL:-nvidia/nemotron-3-super-120b-a12b}"
_status "Configured model" "$MODEL_ID"
_status "Provider URL" "$NIM_URL"

NIM_HEALTH=$(curl -sf --max-time 10 "${NIM_URL%/v1}/health/ready" 2>/dev/null && echo "reachable" || echo "not reachable")
_status "Provider reachability" "$NIM_HEALTH"

# ── 5. OpenShell / Sandbox ────────────────────────────────────────────────────
echo ""
echo "--- OpenShell / Sandbox ---"
SANDBOX_MODE="${MAIW_SANDBOX_MODE:-disabled}"
_status "MAIW_SANDBOX_MODE" "$SANDBOX_MODE"
if command -v openshell &>/dev/null; then
    OS_VERSION=$(openshell --version 2>/dev/null | head -1 || echo "unknown")
    _status "OpenShell" "$OS_VERSION"
else
    _status "OpenShell" "not in PATH" "false"
fi

# ── 6. Persistence health ─────────────────────────────────────────────────────
# Procedure counts come from the running app's durable store
# (GET /api/v1/procedures), not from grepping files.
echo ""
echo "--- Persistence ---"
GOV_DIR="${MAIW_PERSISTENCE_ROOT}/governance"
PROCS=$(curl -s --max-time 10 -w '\n%{http_code}' "${BASE_URL}/api/v1/procedures" 2>/dev/null || echo -e "\n000")
PROCS_HTTP=$(echo "$PROCS" | tail -1)
PROCS_BODY=$(echo "$PROCS" | sed '$d')
if [[ "$PROCS_HTTP" == "200" ]]; then
    echo "$PROCS_BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
by = d.get('by_status', {})
print(f\"  {'Stored procedures':<35} {d.get('count', 0)}\")
print(f\"  {'  Running':<35} {by.get('running', 0)}\")
print(f\"  {'  Waiting for governance':<35} {by.get('waiting_for_governance', 0)}\")
print(f\"  {'  Completed':<35} {by.get('completed', 0)}\")
print(f\"  {'  Escalated / failed':<35} {by.get('escalated', 0) + by.get('failed', 0)}\")
" 2>/dev/null || _status "Procedure store" "could not parse /api/v1/procedures" "false"
else
    _status "Procedure store" "unavailable (HTTP $PROCS_HTTP from /api/v1/procedures)" "false"
fi

GOV_FILE="${GOV_DIR}/governance_inbox.jsonl"
if [[ -f "$GOV_FILE" ]]; then
    GOV_ENTRIES=$(wc -l < "$GOV_FILE" 2>/dev/null || echo 0)
    _status "GovernanceInbox ledger" "ok ($GOV_ENTRIES accepted outcomes)"
elif [[ -d "$GOV_DIR" ]]; then
    _status "GovernanceInbox ledger" "no outcomes recorded yet (ok for fresh deployment)"
else
    _status "GovernanceInbox dir" "not found: $GOV_DIR" "false"
fi

# ── 7. Overall verdict ────────────────────────────────────────────────────────
echo ""
echo "--- Overall verdict ---"
if [[ "$READY_HTTP" == "200" ]]; then
    echo "  MAIW IS USABLE: API is ready and accepting requests."
else
    echo "  MAIW IS NOT USABLE: API is not ready (HTTP $READY_HTTP on /api/v1/ready)."
    echo "  Run: bash scripts/start_reference_deployment.sh"
fi
echo ""
