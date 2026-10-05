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
#   - Active procedures count
#   - Pending governance count
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
echo ""
echo "--- Readiness ---"
READY_HTTP=$(curl -so /dev/null -w "%{http_code}" --max-time 5 "${BASE_URL}/api/v1/ready" 2>/dev/null || echo "000")
READY_BODY=$(curl -sf --max-time 5 "${BASE_URL}/api/v1/ready" 2>/dev/null || echo "{}")
if [[ "$READY_HTTP" == "200" ]]; then
    READY_STATUS=$(echo "$READY_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null || echo "?")
    _status "MAIW API readiness" "ready (HTTP 200)"
    # Component details
    COMPONENTS=$(echo "$READY_BODY" | python3 -c "
import sys, json
d = json.load(sys.stdin)
comps = d.get('components', {})
for k, v in comps.items():
    print(f'    {k}: {v}')
" 2>/dev/null || echo "    (could not parse)")
    echo "$COMPONENTS"
else
    _status "MAIW API readiness" "NOT READY (HTTP $READY_HTTP)" "false"
    READY_DETAIL=$(echo "$READY_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('detail',''))" 2>/dev/null || echo "")
    [[ -n "$READY_DETAIL" ]] && echo "  Detail: $READY_DETAIL"
fi

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
echo ""
echo "--- Persistence ---"
PROC_DIR="${MAIW_PERSISTENCE_ROOT}/procedures"
GOV_DIR="${MAIW_PERSISTENCE_ROOT}/governance"

if [[ -d "$PROC_DIR" ]] && [[ -w "$PROC_DIR" ]]; then
    PROC_COUNT=$(find "$PROC_DIR" -name "*.json" 2>/dev/null | wc -l)
    _status "Procedure state dir" "ok ($PROC_COUNT files)"
    # Count by status
    WAITING=$(grep -l '"status": "waiting_for_governance"' "$PROC_DIR"/*.json 2>/dev/null | wc -l || echo 0)
    ACTIVE=$(grep -l '"status": "running"' "$PROC_DIR"/*.json 2>/dev/null | wc -l || echo 0)
    COMPLETED=$(grep -l '"status": "completed"' "$PROC_DIR"/*.json 2>/dev/null | wc -l || echo 0)
    _status "  Active procedures" "$ACTIVE running"
    _status "  Waiting for governance" "$WAITING"
    _status "  Completed procedures" "$COMPLETED"
else
    _status "Procedure state dir" "not found or not writable: $PROC_DIR" "false"
fi

if [[ -d "$GOV_DIR" ]]; then
    GOV_FILE="${GOV_DIR}/governance_inbox.jsonl"
    if [[ -f "$GOV_FILE" ]]; then
        GOV_ENTRIES=$(wc -l < "$GOV_FILE" 2>/dev/null || echo 0)
        _status "GovernanceInbox" "ok ($GOV_ENTRIES entries)"
    else
        _status "GovernanceInbox" "inbox file not yet created (ok for fresh deployment)"
    fi
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
