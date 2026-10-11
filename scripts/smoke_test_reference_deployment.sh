#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# smoke_test_reference_deployment.sh — validate the running MAIW v2 reference
# deployment (the canonical shipped app, maiw_api.app:app).
#
# v2.0.1 round 2: the target is derived ONLY from this deployment's verified
# identity (scripts/lib/deployment_identity.sh) — never from a default port.
# If identity cannot be established the smoke test REFUSES before sending any
# request (no localhost:8001 fallback).
#
# Smoke tests:
#   1.  Liveness                       GET /api/v1/live → 200 (this instance)
#   2.  Readiness                      GET /api/v1/ready → 200, status READY
#   3.  Durable persistence            persistence.durable=true
#   4.  Physical model bindings        readiness model_gateway has no binding
#                                      violations; configured bindings pass the
#                                      shared DeploymentResolver check
#   5.  Inference route mounted        /api/v1/inference in /openapi.json
#   6.  No token → 401                 7. Wrong token → 401
#   8.  Forbidden routing field → 422  9. Unknown field → 422
#   10. Correct token → 200
#   11. Physical model identity        for the response: logical role, resolved
#                                      physical model, generation, provider-
#                                      reported model; the model must be the
#                                      approved deployment for that role and the
#                                      provider-reported ID must match it
#   12. No legacy chat write path      POST /api/v1/chat → 404
#   12b. Operational write boundary    equipment assign/release/maintenance
#                                      denied (401/403/503) with no credential
#                                      and with the inference token; in
#                                      reference_governed the operator
#                                      credential is accepted (empty body → 422)
#   13. OpenShell sandbox Ready        (when MAIW_SANDBOX_MODE=required)
#
# Exit: 0 all pass; 1 failures; 2 refused (identity not verified).
# No secret is ever printed.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
# shellcheck source=lib/load_env.sh
source "$SCRIPT_DIR/lib/load_env.sh"
# shellcheck source=lib/deployment_identity.sh
source "$SCRIPT_DIR/lib/deployment_identity.sh"

echo "=== MAIW v2 Reference Deployment — Smoke Test (canonical app) ==="
maiw_load_env "$PROJECT_ROOT"
maiw_require_vars MAIW_PERSISTENCE_ROOT MAIW_PYTHON
PY="$MAIW_PYTHON"

set +e
maiw_verify_instance
VRC=$?
set -e
if [[ "$VRC" -ne 0 ]]; then
    echo "  REFUSED: NOT RUNNING / CANNOT VERIFY — ${MAIW_VERIFY_REASON}" >&2
    echo "  No request was sent. Start the deployment with scripts/start_reference_deployment.sh." >&2
    exit 2
fi
BASE_URL="$MAIW_TARGET_BASE_URL"
echo "Target: $BASE_URL (verified instance ${MAIW_TARGET_INSTANCE_ID:0:8}…, PID $MAIW_TARGET_PID)"
echo ""

FAIL=0
PASS=0
_pass() { PASS=$((PASS+1)); echo "  PASS  $1"; }
_fail() { FAIL=$((FAIL+1)); echo "  FAIL  $1" >&2; echo "        $2" >&2; }
_json() { "$PY" -c "import sys,json; d=json.load(sys.stdin); $1" 2>/dev/null; }

# ── 1-4: liveness / readiness / persistence / model bindings ─────────────────
echo "--- API Health ---"
_pass "Liveness (GET /api/v1/live answers as this instance)"
READY_BODY=$(curl -s --max-time 30 -w '\n%{http_code}' "${BASE_URL}/api/v1/ready" 2>/dev/null || echo -e "\n000")
READY_HTTP=$(echo "$READY_BODY" | tail -1)
READY_JSON=$(echo "$READY_BODY" | sed '$d')
READY_STATUS=$(echo "$READY_JSON" | _json "print(d.get('status',''))" || echo "")
if [[ "$READY_HTTP" == "200" && "$READY_STATUS" == "READY" ]]; then
    _pass "Readiness (GET /api/v1/ready → 200 READY, profile $(echo "$READY_JSON" | _json "print(d.get('profile',''))"))"
else
    FAILED=$(echo "$READY_JSON" | _json "print(','.join(d.get('failed_components',[])))" || echo "?")
    _fail "Readiness" "Expected 200 READY — got HTTP $READY_HTTP status=$READY_STATUS failed=[$FAILED]"
fi
DURABLE=$(echo "$READY_JSON" | _json "print(d['components']['persistence'].get('durable'))" || echo "")
[[ "$DURABLE" == "True" ]] && _pass "Durable persistence (file-backed)" \
    || _fail "Durable persistence" "Expected persistence.durable=True — got '$DURABLE'"
MG=$(echo "$READY_JSON" | _json "print(d['components']['model_gateway'].get('status'))" || echo "")
[[ "$MG" == "ready" ]] && _pass "ModelGateway ready, every enabled role bound to an approved physical model" \
    || _fail "ModelGateway" "readiness model_gateway=$MG (see binding_violations in /api/v1/ready)"
echo "  Configured bindings (shared DeploymentResolver check):"
if "$PY" "$SCRIPT_DIR/lib/check_model_config.py" | sed 's/^/    /'; then
    _pass "Configured physical model bindings approved"
else
    _fail "Configured physical model bindings" "scripts/lib/check_model_config.py reported a violation"
fi

# ── 5-11: bounded inference boundary ─────────────────────────────────────────
echo ""
echo "--- Inference boundary (POST /api/v1/inference) ---"
INFERENCE_URL="${BASE_URL}/api/v1/inference"
INFERENCE_TOKEN="${MAIW_INFERENCE_INTERNAL_TOKEN:-}"
PAYLOAD='{"task":"smoke_test","messages":[{"role":"user","content":"Reply with the single word OK."}],"deadline_ms":60000}'

if curl -sf --max-time 10 "${BASE_URL}/openapi.json" | _json "sys.exit(0 if '/api/v1/inference' in d.get('paths',{}) else 1)"; then
    _pass "Inference route mounted on the canonical app"
else
    _fail "Inference route" "/api/v1/inference not in ${BASE_URL}/openapi.json"
fi

# Token passed via a curl config on stdin, never on the command line.
_post() {  # $1=payload $2=token-or-__none__ ; prints "<http>\n<body>"
    local hdr=""
    [[ "$2" != "__none__" ]] && hdr="header = \"X-Maiw-Internal-Token: $2\""
    printf '%s\n' "$hdr" | curl -s --max-time 120 -K - -w '\n%{http_code}' -X POST "$INFERENCE_URL" \
        -H "Content-Type: application/json" -d "$1" 2>/dev/null || echo -e "\n000"
}
_code() { _post "$1" "$2" | tail -1; }

CODE=$(_code "$PAYLOAD" "__none__")
[[ "$CODE" == "401" ]] && _pass "No-token inference → 401" || _fail "No-token inference" "Expected 401 — got $CODE"
CODE=$(_code "$PAYLOAD" "wrong-token-smoke-test")
[[ "$CODE" == "401" ]] && _pass "Wrong-token inference → 401" || _fail "Wrong-token inference" "Expected 401 — got $CODE"

if [[ -n "$INFERENCE_TOKEN" ]]; then
    CODE=$(_code '{"task":"smoke_test","messages":[{"role":"user","content":"x"}],"model_id":"meta/llama-3.1-70b-instruct"}' "$INFERENCE_TOKEN")
    [[ "$CODE" == "422" ]] && _pass "Forbidden routing field (model_id) → 422" || _fail "Forbidden field" "Expected 422 — got $CODE"
    CODE=$(_code '{"task":"smoke_test","messages":[{"role":"user","content":"x"}],"model":"meta/llama-3.1-70b-instruct"}' "$INFERENCE_TOKEN")
    [[ "$CODE" == "422" ]] && _pass "Unknown field (model) → 422" || _fail "Unknown field" "Expected 422 — got $CODE"

    RESP=$(_post "$PAYLOAD" "$INFERENCE_TOKEN")
    HTTP=$(echo "$RESP" | tail -1)
    BODY=$(echo "$RESP" | sed '$d')
    if [[ "$HTTP" == "200" ]]; then
        _pass "Authenticated inference → 200"
        ROLE=$(echo "$BODY" | _json "print(d['route']['selected_role'])" || echo "?")
        MID=$(echo "$BODY" | _json "print(d['route']['selected_model_id'])" || echo "?")
        GEN=$(echo "$BODY" | _json "print(d['route']['generation'])" || echo "?")
        APPROVED=$(echo "$BODY" | _json "print(d['route']['approved_family'])" || echo "")
        REPORTED=$(echo "$BODY" | _json "print(d['route'].get('provider_reported_model_id'))" || echo "")
        VERIFIED=$(echo "$BODY" | _json "print(d['route'].get('identity_verified'))" || echo "")
        echo "        logical role=$ROLE resolved physical model=$MID generation=$GEN"
        echo "        provider-reported model=$REPORTED identity_verified=$VERIFIED approved_family=$APPROVED"
        if "$PY" "$SCRIPT_DIR/lib/check_model_config.py" --expect "$ROLE" "$MID" >/dev/null \
            && [[ "$APPROVED" == "True" && "$VERIFIED" == "True" && "$REPORTED" == "$MID" ]]; then
            _pass "Physical model identity: $MID is the approved $ROLE deployment ($GEN); provider reported the same ID"
        else
            _fail "Physical model identity" "role=$ROLE model=$MID gen=$GEN reported=$REPORTED verified=$VERIFIED approved=$APPROVED"
        fi
    else
        CODE_FIELD=$(echo "$BODY" | _json "print(d.get('code',''))" || echo "")
        _fail "Authenticated inference" "Expected 200 — got HTTP $HTTP ${CODE_FIELD}"
    fi
else
    _fail "Authenticated checks" "MAIW_INFERENCE_INTERNAL_TOKEN is not set (check .env)"
fi

# ── 12: no legacy bypass ─────────────────────────────────────────────────────
echo ""
echo "--- No legacy write path ---"
CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 -X POST "${BASE_URL}/api/v1/chat" \
    -H "Content-Type: application/json" -d '{"message":"smoke: route must not exist"}' 2>/dev/null || echo "000")
[[ "$CODE" == "404" ]] && _pass "Legacy POST /api/v1/chat not mounted (404)" || _fail "Legacy chat" "Expected 404 — got $CODE"

# ── 12b: operational write boundary (v2.0.1 round 3, NEW3-P1-01) ─────────────
# Governed write routes require the separate operator write credential. The
# inference token (what the sandbox holds) must never authorise them. Nothing
# here can mutate: denied requests stop at authentication, and the one
# authenticated request carries an empty body (422 / 503, never a proposal).
echo ""
echo "--- Operational write boundary ---"
_wpost() {  # $1=path $2=header-name-or-__none__ $3=value ; prints http code + typed code
    local hdr=""
    [[ "$2" != "__none__" ]] && hdr="header = \"$2: $3\""
    printf '%s\n' "$hdr" | curl -s --max-time 30 -K - -w '\n%{http_code}' -X POST "${BASE_URL}$1" \
        -H "Content-Type: application/json" -d '{}' 2>/dev/null || echo -e "\n000"
}
_wcode() { _wpost "$@" | tail -1; }
for WPATH in /api/v1/equipment/assign /api/v1/equipment/release /api/v1/equipment/maintenance; do
    C1=$(_wcode "$WPATH" "__none__" "")
    C2=$(_wcode "$WPATH" "X-Maiw-Internal-Token" "${INFERENCE_TOKEN:-none}")
    C3=$(_wcode "$WPATH" "X-Maiw-Operator-Token" "${INFERENCE_TOKEN:-none}")
    if [[ "$C1" =~ ^(401|403|503)$ && "$C2" =~ ^(401|403|503)$ && "$C3" =~ ^(401|403|503)$ ]]; then
        _pass "POST $WPATH denied without operator credential (none=$C1, inference-token=$C2, inference-token-as-operator=$C3)"
    else
        _fail "POST $WPATH" "Expected 401/403/503 for every non-operator caller — got none=$C1 inference=$C2 as-operator=$C3"
    fi
done
if [[ "${MAIW_DEPLOYMENT_PROFILE:-reference}" == "reference_governed" ]]; then
    if [[ -n "${MAIW_OPERATOR_WRITE_TOKEN:-}" ]]; then
        C4=$(_wcode /api/v1/equipment/release "X-Maiw-Operator-Token" "$MAIW_OPERATOR_WRITE_TOKEN")
        [[ "$C4" == "422" ]] && _pass "Operator credential accepted (empty body → 422, nothing proposed)" \
            || _fail "Operator credential" "Expected 422 for an authenticated empty body — got $C4"
    else
        _fail "Operator credential" "profile reference_governed but MAIW_OPERATOR_WRITE_TOKEN is not set"
    fi
fi

# ── 13: sandbox (only when required) ─────────────────────────────────────────
echo ""
echo "--- Sandbox ---"
SANDBOX_MODE="${MAIW_SANDBOX_MODE:-disabled}"
if [[ "$SANDBOX_MODE" == "required" ]]; then
    SANDBOX_NAME="${MAIW_SANDBOX_NAME:-}"
    if [[ -z "$SANDBOX_NAME" ]]; then
        _fail "OpenShell sandbox" "MAIW_SANDBOX_MODE=required but MAIW_SANDBOX_NAME is not set"
    elif ! command -v openshell &>/dev/null; then
        _fail "OpenShell sandbox" "openshell CLI not in PATH"
    else
        PHASE=$(openshell sandbox list -o json 2>/dev/null | "$PY" -c "
import sys, json
name = sys.argv[1]
for s in json.load(sys.stdin):
    if s.get('name') == name:
        print(s.get('phase', '')); break
" "$SANDBOX_NAME" 2>/dev/null || echo "")
        [[ "$PHASE" == "Ready" ]] && _pass "OpenShell sandbox '$SANDBOX_NAME' Ready" \
            || _fail "OpenShell sandbox" "Expected '$SANDBOX_NAME' phase Ready — got '${PHASE:-absent}'"
    fi
else
    echo "  SKIP  Sandbox check (MAIW_SANDBOX_MODE=$SANDBOX_MODE)"
fi

echo ""
echo "=== Smoke Test Summary: $PASS passed, $FAIL failed ==="
if [[ "$FAIL" -gt 0 ]]; then
    echo "SMOKE TEST FAILED — see docs/operations/REFERENCE_DEPLOYMENT_RUNBOOK.md § Troubleshooting" >&2
    exit 1
fi
echo "SMOKE TEST PASSED — canonical MAIW reference deployment is operational."
