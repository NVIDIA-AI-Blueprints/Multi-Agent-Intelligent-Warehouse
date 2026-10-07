#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# smoke_test_reference_deployment.sh — validate the running MAIW v2 reference
# deployment. Targets ONLY the canonical shipped app (maiw_api.app:app) started
# by scripts/start_reference_deployment.sh, on MAIW_API_PORT. There is no
# separate inference server (v2.0.1).
#
# Smoke tests:
#   1.  Liveness                       GET /api/v1/live → 200
#   2.  Readiness                      GET /api/v1/ready → 200, status READY
#   3.  Durable persistence            readiness reports persistence durable=true
#   4.  Inference route mounted        /api/v1/inference present in /openapi.json
#   5.  No token → 401                 (fail-closed)
#   6.  Wrong token → 401
#   7.  Forbidden routing field → 422  (model_id cannot be chosen by a caller)
#   8.  Unknown field → 422            (no silently ignored routing hints)
#   9.  Correct token → 200            (if MAIW_INFERENCE_INTERNAL_TOKEN is set)
#   10. Returned model is approved     route.generation ∈ {nemotron-3, nemotron-3.5}
#   11. No legacy chat write path      POST /api/v1/chat → 404
#   12. Approved model configured      LLM_MODEL is not Llama-family
#   13. OpenShell sandbox Ready        (only if MAIW_SANDBOX_MODE=required;
#                                       sandbox name from MAIW_SANDBOX_NAME)
#
# Exit: 0 = all pass; 1 = one or more failed. No secret is ever printed.
# ---------------------------------------------------------------------------
set -euo pipefail

MAIW_API_PORT="${MAIW_API_PORT:-8001}"
BASE_URL="${MAIW_SMOKE_BASE_URL:-http://127.0.0.1:${MAIW_API_PORT}}"
PY="${MAIW_PYTHON:-python3}"
FAIL=0
PASS=0

_pass() { PASS=$((PASS+1)); echo "  PASS  $1"; }
_fail() { FAIL=$((FAIL+1)); echo "  FAIL  $1" >&2; echo "        $2" >&2; }
_json() { "$PY" -c "import sys,json; d=json.load(sys.stdin); $1" 2>/dev/null; }

echo "=== MAIW v2 Reference Deployment — Smoke Test (canonical app) ==="
echo "Target: $BASE_URL"
echo ""

# ── 1-3: liveness / readiness / persistence ───────────────────────────────────
echo "--- API Health ---"
if curl -sf --max-time 10 "${BASE_URL}/api/v1/live" &>/dev/null; then
    _pass "Liveness (GET /api/v1/live)"
else
    _fail "Liveness" "Expected HTTP 200 from ${BASE_URL}/api/v1/live — got no response"
fi

READY_BODY=$(curl -s --max-time 15 -w '\n%{http_code}' "${BASE_URL}/api/v1/ready" 2>/dev/null || echo -e "\n000")
READY_HTTP=$(echo "$READY_BODY" | tail -1)
READY_JSON=$(echo "$READY_BODY" | sed '$d')
READY_STATUS=$(echo "$READY_JSON" | _json "print(d.get('status',''))" || echo "")
if [[ "$READY_HTTP" == "200" && "$READY_STATUS" == "READY" ]]; then
    _pass "Readiness (GET /api/v1/ready → 200 READY)"
else
    FAILED=$(echo "$READY_JSON" | _json "print(','.join(d.get('failed_components',[])))" || echo "?")
    _fail "Readiness" "Expected 200 READY — got HTTP $READY_HTTP status=$READY_STATUS failed=[$FAILED]"
fi
DURABLE=$(echo "$READY_JSON" | _json "print(d['components']['persistence'].get('durable'))" || echo "")
if [[ "$DURABLE" == "True" ]]; then
    _pass "Durable persistence (ProcedureStateStore + GovernanceInbox file-backed)"
else
    _fail "Durable persistence" "Expected persistence.durable=True in /api/v1/ready — got '$DURABLE'"
fi

# ── 4-10: bounded inference boundary ─────────────────────────────────────────
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

_post() {  # $1=payload $2=token-or-empty-marker
    if [[ "$2" == "__none__" ]]; then
        curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X POST "$INFERENCE_URL" \
            -H "Content-Type: application/json" -d "$1" 2>/dev/null || echo "000"
    else
        curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X POST "$INFERENCE_URL" \
            -H "Content-Type: application/json" -H "X-Maiw-Internal-Token: $2" \
            -d "$1" 2>/dev/null || echo "000"
    fi
}

CODE=$(_post "$PAYLOAD" "__none__")
[[ "$CODE" == "401" ]] && _pass "No-token inference → 401" || _fail "No-token inference" "Expected 401 — got $CODE"
CODE=$(_post "$PAYLOAD" "wrong-token-smoke-test")
[[ "$CODE" == "401" ]] && _pass "Wrong-token inference → 401" || _fail "Wrong-token inference" "Expected 401 — got $CODE"

if [[ -n "$INFERENCE_TOKEN" ]]; then
    FORBIDDEN='{"task":"smoke_test","messages":[{"role":"user","content":"x"}],"model_id":"meta/llama-3.1-70b-instruct"}'
    CODE=$(_post "$FORBIDDEN" "$INFERENCE_TOKEN")
    [[ "$CODE" == "422" ]] && _pass "Forbidden routing field (model_id) → 422" || _fail "Forbidden field" "Expected 422 — got $CODE"
    UNKNOWN='{"task":"smoke_test","messages":[{"role":"user","content":"x"}],"model":"meta/llama-3.1-70b-instruct"}'
    CODE=$(_post "$UNKNOWN" "$INFERENCE_TOKEN")
    [[ "$CODE" == "422" ]] && _pass "Unknown field (model) → 422" || _fail "Unknown field" "Expected 422 — got $CODE"

    RESP=$(curl -s --max-time 120 -w '\n%{http_code}' -X POST "$INFERENCE_URL" \
        -H "Content-Type: application/json" -H "X-Maiw-Internal-Token: $INFERENCE_TOKEN" \
        -d "$PAYLOAD" 2>/dev/null || echo -e "\n000")
    HTTP=$(echo "$RESP" | tail -1)
    BODY=$(echo "$RESP" | sed '$d')
    if [[ "$HTTP" == "200" ]]; then
        _pass "Authenticated inference → 200"
        GEN=$(echo "$BODY" | _json "print(d['route']['generation'])" || echo "unknown")
        MID=$(echo "$BODY" | _json "print(d['model_id'])" || echo "unknown")
        APPROVED=$(echo "$BODY" | _json "print(d['route']['approved_family'])" || echo "")
        if [[ ( "$GEN" == "nemotron-3" || "$GEN" == "nemotron-3.5" ) && "$APPROVED" == "True" ]]; then
            _pass "Returned model approved: $MID (generation $GEN)"
        else
            _fail "Approved model" "Expected nemotron-3/3.5 approved_family=True — got $MID/$GEN/$APPROVED"
        fi
    else
        CODE_FIELD=$(echo "$BODY" | _json "print(d.get('code',''))" || echo "")
        _fail "Authenticated inference" "Expected 200 — got HTTP $HTTP ${CODE_FIELD}"
    fi
else
    echo "  SKIP  Authenticated checks (MAIW_INFERENCE_INTERNAL_TOKEN not set in this shell)"
fi

# ── 11: no legacy bypass ─────────────────────────────────────────────────────
echo ""
echo "--- No legacy write path ---"
CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 15 -X POST "${BASE_URL}/api/v1/chat" \
    -H "Content-Type: application/json" -d '{"message":"Show me the status of forklift FL-01"}' 2>/dev/null || echo "000")
[[ "$CODE" == "404" ]] && _pass "Legacy POST /api/v1/chat not mounted (404)" || _fail "Legacy chat" "Expected 404 — got $CODE"

# ── 12: configured model family ──────────────────────────────────────────────
echo ""
echo "--- Approved Model Policy ---"
MODEL_ID="${LLM_MODEL:-${MAIW_NIM_MODEL:-}}"
if [[ -n "$MODEL_ID" ]]; then
    case "$MODEL_ID" in
        *llama*|*Llama*) _fail "Approved model" "Nemotron 3/3.5 required — got Llama-family: $MODEL_ID" ;;
        nvidia/nemotron-3-*|nvidia/nemotron-3.5-*) _pass "Approved model configured: $MODEL_ID" ;;
        *) echo "  WARN  Model $MODEL_ID — generation not inferred from name; PolicyFilter enforces" ;;
    esac
else
    echo "  INFO  LLM_MODEL not set in this shell — PolicyFilter selects from the registry"
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
for s in json.load(sys.stdin):
    if s.get('name') == '$SANDBOX_NAME':
        print(s.get('phase', '')); break
" 2>/dev/null || echo "")
        [[ "$PHASE" == "Ready" ]] && _pass "OpenShell sandbox '$SANDBOX_NAME' Ready" || _fail "OpenShell sandbox" "Expected '$SANDBOX_NAME' phase Ready — got '${PHASE:-absent}'"
    fi
else
    echo "  SKIP  Sandbox check (MAIW_SANDBOX_MODE=$SANDBOX_MODE)"
fi

# ── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "=== Smoke Test Summary: $PASS passed, $FAIL failed ==="
echo ""
if [[ "$FAIL" -gt 0 ]]; then
    echo "SMOKE TEST FAILED — resolve the failures above." >&2
    echo "See docs/operations/REFERENCE_DEPLOYMENT_RUNBOOK.md § Troubleshooting" >&2
    exit 1
fi
echo "SMOKE TEST PASSED — canonical MAIW reference deployment is operational."
echo ""
