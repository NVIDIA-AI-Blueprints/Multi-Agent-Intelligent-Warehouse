#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# status_reference_deployment.sh — status of the MAIW v2 reference deployment
#
# Reports (no secrets): deployment identity, liveness, readiness breakdown
# (profile, persistence, ModelGateway + physical model bindings, MCP domains,
# governed write path, database, sandbox), configured physical model bindings,
# provider reachability, procedure counts, governance ledger.
#
# v2.0.1 round 2: the API is queried ONLY at the port recorded in this
# deployment's verified identity — never at a default port.  If identity
# cannot be established the API section reports NOT RUNNING / CANNOT VERIFY
# and no request is sent.
#
# Usage: bash scripts/status_reference_deployment.sh
# Exit: 0 ready; 1 not ready / not verifiable.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
# shellcheck source=lib/load_env.sh
source "$SCRIPT_DIR/lib/load_env.sh"
# shellcheck source=lib/deployment_identity.sh
source "$SCRIPT_DIR/lib/deployment_identity.sh"

echo "=== MAIW v2 Reference Deployment — Status ==="
maiw_load_env "$PROJECT_ROOT"
maiw_require_vars MAIW_PERSISTENCE_ROOT MAIW_PYTHON
PY="$MAIW_PYTHON"

_status() {
    local label="$1" value="$2" ok="${3:-true}"
    if [[ "$ok" == "true" ]]; then
        printf "  %-35s %s\n" "$label" "$value"
    else
        printf "  %-35s %s  [WARN]\n" "$label" "$value"
    fi
}

echo ""
echo "--- Deployment identity ---"
set +e
maiw_verify_instance
VRC=$?
set -e
READY_HTTP="n/a"
if [[ "$VRC" -ne 0 ]]; then
    _status "MAIW API" "NOT RUNNING / CANNOT VERIFY — ${MAIW_VERIFY_REASON}" "false"
else
    BASE_URL="$MAIW_TARGET_BASE_URL"
    _status "MAIW API" "verified instance ${MAIW_TARGET_INSTANCE_ID:0:8}… PID $MAIW_TARGET_PID port $MAIW_TARGET_PORT"
    LIVE=$(curl -sf --max-time 5 "${BASE_URL}/api/v1/live" 2>/dev/null || echo "")
    _status "Liveness" "$(echo "$LIVE" | "$PY" -c "import sys,json; d=json.load(sys.stdin); print(d.get('status'), '(uptime', d.get('uptime'), ')')" 2>/dev/null || echo '?')"

    echo ""
    echo "--- Readiness ---"
    READY_RAW=$(curl -s --max-time 30 -w '\n%{http_code}' "${BASE_URL}/api/v1/ready" 2>/dev/null || echo -e "\n000")
    READY_HTTP=$(echo "$READY_RAW" | tail -1)
    READY_BODY=$(echo "$READY_RAW" | sed '$d')
    [[ -z "$READY_BODY" ]] && READY_BODY="{}"
    if [[ "$READY_HTTP" == "200" ]]; then
        _status "MAIW API readiness" "READY (HTTP 200)"
    else
        _status "MAIW API readiness" "NOT READY (HTTP $READY_HTTP)" "false"
    fi
    echo "$READY_BODY" | "$PY" -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print('    (no readiness body)'); sys.exit(0)
print('    profile: ' + str(d.get('profile')))
if d.get('failed_components'):
    print('    failed components: ' + ', '.join(d['failed_components']))
for k, v in (d.get('components') or {}).items():
    if not isinstance(v, dict):
        print(f'    {k}: {v}'); continue
    extra = ''
    if k == 'persistence':
        extra = f\" (durable={v.get('durable')}, unapplied_governance={v.get('unapplied_governance', 0)})\"
    elif k == 'mcp_domains':
        extra = ' ' + ', '.join(f\"{dn}={de.get('state')}{'*' if de.get('required') else ''}\" for dn, de in (v.get('domains') or {}).items()) + '  (*=required)'
    elif k == 'model_gateway' and v.get('binding_violations'):
        extra = ' violations=' + str(v['binding_violations'])
    elif k == 'sandbox_runtime':
        extra = f\" (mode={v.get('mode')}, name={v.get('name')}, phase={v.get('phase')})\"
    print(f\"    {k}: {v.get('status', '?')}{extra}\")
" 2>/dev/null || echo "    (could not parse)"

    echo ""
    echo "--- Procedures ---"
    PROCS=$(curl -s --max-time 10 -w '\n%{http_code}' "${BASE_URL}/api/v1/procedures" 2>/dev/null || echo -e "\n000")
    if [[ "$(echo "$PROCS" | tail -1)" == "200" ]]; then
        echo "$PROCS" | sed '$d' | "$PY" -c "
import sys, json
d = json.load(sys.stdin)
by = d.get('by_status', {})
print(f\"  {'Stored procedures':<35} {d.get('count', 0)}\")
print(f\"  {'  Waiting for governance':<35} {by.get('waiting_for_governance', 0)}\")
print(f\"  {'  Completed':<35} {by.get('completed', 0)}\")
" 2>/dev/null || _status "Procedure store" "could not parse" "false"
    else
        _status "Procedure store" "unavailable" "false"
    fi
fi

echo ""
echo "--- Configured physical model bindings (shared DeploymentResolver check) ---"
"$PY" "$SCRIPT_DIR/lib/check_model_config.py" --provider-probe | sed 's/^/  /' || true

echo ""
echo "--- Sandbox ---"
_status "MAIW_SANDBOX_MODE" "${MAIW_SANDBOX_MODE:-disabled}"
_status "MAIW_SANDBOX_NAME" "${MAIW_SANDBOX_NAME:-(not set)}"

echo ""
echo "--- Durable state ---"
GOV_FILE="${MAIW_GOVERNANCE_STATE_DIR:-${MAIW_PERSISTENCE_ROOT}/governance}/governance_inbox.jsonl"
if [[ -f "$GOV_FILE" ]]; then
    _status "GovernanceInbox ledger" "$(grep -vc '"event": "applied"' "$GOV_FILE" || true) accepted outcome(s)"
else
    _status "GovernanceInbox ledger" "no outcomes recorded yet"
fi

echo ""
echo "--- Overall verdict ---"
if [[ "$READY_HTTP" == "200" ]]; then
    echo "  MAIW IS USABLE: verified instance is ready."
    exit 0
fi
echo "  MAIW IS NOT USABLE (readiness: $READY_HTTP)."
exit 1
