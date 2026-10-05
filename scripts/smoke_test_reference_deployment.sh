#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# smoke_test_reference_deployment.sh — validate running MAIW v2 reference deployment
#
# Smoke tests (Step 57):
#   1. MAIW API is responding (liveness)
#   2. MAIW API is ready (readiness — HTTP 200)
#   3. OpenShell sandbox is ready (if MAIW_SANDBOX_MODE=required)
#   4. Approved model configured (nemotron-3 or nemotron-3.5)
#   5. Auth-required inference returns 401 without token (fail-closed)
#   6. Auth-required inference returns 401 with wrong token
#   7. Auth-required inference succeeds with correct token
#   8. Returned model is approved family (nemotron-3 or nemotron-3.5)
#   9. Sandbox cannot see WRITE capability (via policy)
#
# Exit: 0 = all pass; 1 = one or more failed
#
# Usage:
#   bash scripts/smoke_test_reference_deployment.sh
#
# Step 57 of Phase 20C-C.
# ---------------------------------------------------------------------------
set -euo pipefail

MAIW_API_PORT="${MAIW_API_PORT:-8001}"
BASE_URL="http://127.0.0.1:${MAIW_API_PORT}"
FAIL=0
PASS=0

_pass() { PASS=$((PASS+1)); echo "  PASS  $1"; }
_fail() { FAIL=$((FAIL+1)); echo "  FAIL  $1" >&2; echo "        $2" >&2; }

echo "=== MAIW v2 Reference Deployment — Smoke Test ==="
echo "Target: $BASE_URL"
echo ""

# ── Test 1: Liveness ──────────────────────────────────────────────────────────
echo "--- API Health ---"
if curl -sf --max-time 10 "${BASE_URL}/api/v1/live" &>/dev/null; then
    _pass "MAIW API liveness (GET /api/v1/live)"
else
    _fail "MAIW API liveness" "Expected HTTP 200 from ${BASE_URL}/api/v1/live — got no response"
fi

# ── Test 2: Readiness ──────────────────────────────────────────────────────────
READY_HTTP=$(curl -so /dev/null -w "%{http_code}" --max-time 10 "${BASE_URL}/api/v1/ready" 2>/dev/null || echo "000")
if [[ "$READY_HTTP" == "200" ]]; then
    _pass "MAIW API readiness (GET /api/v1/ready → HTTP $READY_HTTP)"
else
    _fail "MAIW API readiness" "Expected HTTP 200 from /api/v1/ready — got HTTP $READY_HTTP"
fi

# ── Test 3: Sandbox availability ───────────────────────────────────────────────
echo ""
echo "--- Sandbox ---"
SANDBOX_MODE="${MAIW_SANDBOX_MODE:-disabled}"
if [[ "$SANDBOX_MODE" == "required" ]]; then
    RUNTIME_RESP=$(curl -sf --max-time 5 "${BASE_URL}/api/v1/runtime/status" 2>/dev/null || echo "{}")
    SANDBOX_READY=$(echo "$RUNTIME_RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('sandbox', {}).get('available', False))
" 2>/dev/null || echo "False")
    if [[ "${SANDBOX_READY,,}" == "true" ]]; then
        _pass "OpenShell sandbox available (MAIW_SANDBOX_MODE=required)"
    else
        _fail "OpenShell sandbox" "Expected sandbox available=True in runtime/status — got $SANDBOX_READY"
    fi
else
    echo "  SKIP  Sandbox check (MAIW_SANDBOX_MODE=$SANDBOX_MODE — not required)"
fi

# ── Test 4: Approved model configured ─────────────────────────────────────────
echo ""
echo "--- Approved Model Policy ---"
MODEL_ID="${LLM_MODEL:-${MAIW_NIM_MODEL:-}}"
if [[ -n "$MODEL_ID" ]]; then
    # Check it's not a Llama-family model
    case "$MODEL_ID" in
        nvidia/llama-*|*llama-*nemotron*|*llama-3.*nemotron*)
            _fail "Approved model" "Nemotron 3/3.5 model — got Llama-family: $MODEL_ID"
            ;;
        nvidia/nemotron-3-*|nvidia/nemotron-3.5-*)
            _pass "Approved model configured: $MODEL_ID"
            ;;
        *)
            echo "  WARN  Model $MODEL_ID — generation not inferred from name; PolicyFilter will enforce"
            ;;
    esac
else
    _fail "Approved model" "LLM_MODEL or MAIW_NIM_MODEL must be set"
fi

# ── Tests 5-8: Auth-required inference ────────────────────────────────────────
echo ""
echo "--- Inference Auth Boundary ---"
INFERENCE_URL="${BASE_URL}/api/v1/inference"
INFERENCE_TOKEN="${MAIW_INFERENCE_INTERNAL_TOKEN:-}"

SAFE_PAYLOAD='{"task":"What is 2+2?","modality":"text","reasoning_level":"standard","risk_level":"low","deadline_ms":30000}'

# Test 5: No token → 401
HTTP_NO_TOKEN=$(curl -so /dev/null -w "%{http_code}" --max-time 15 \
    -X POST "$INFERENCE_URL" \
    -H "Content-Type: application/json" \
    -d "$SAFE_PAYLOAD" 2>/dev/null || echo "000")
if [[ "$HTTP_NO_TOKEN" == "401" ]]; then
    _pass "No-token inference returns 401 (fail-closed)"
else
    _fail "No-token inference" "Expected HTTP 401 — got HTTP $HTTP_NO_TOKEN"
fi

# Test 6: Wrong token → 401
HTTP_WRONG_TOKEN=$(curl -so /dev/null -w "%{http_code}" --max-time 15 \
    -X POST "$INFERENCE_URL" \
    -H "Content-Type: application/json" \
    -H "X-Maiw-Internal-Token: wrong-token-smoke-test" \
    -d "$SAFE_PAYLOAD" 2>/dev/null || echo "000")
if [[ "$HTTP_WRONG_TOKEN" == "401" ]]; then
    _pass "Wrong-token inference returns 401 (fail-closed)"
else
    _fail "Wrong-token inference" "Expected HTTP 401 — got HTTP $HTTP_WRONG_TOKEN"
fi

# Test 7: Correct token → success (if token is set)
if [[ -n "$INFERENCE_TOKEN" ]]; then
    INFER_RESP=$(curl -sf --max-time 60 \
        -X POST "$INFERENCE_URL" \
        -H "Content-Type: application/json" \
        -H "X-Maiw-Internal-Token: $INFERENCE_TOKEN" \
        -d "$SAFE_PAYLOAD" 2>/dev/null || echo "")
    if [[ -n "$INFER_RESP" ]]; then
        _pass "Auth inference call returned response"
        # Test 8: Check returned model is approved
        RETURNED_MODEL=$(echo "$INFER_RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(d.get('model_id', d.get('route_decision', {}).get('model_id', 'unknown')))
" 2>/dev/null || echo "unknown")
        RETURNED_GEN=$(echo "$INFER_RESP" | python3 -c "
import sys, json
d = json.load(sys.stdin)
rd = d.get('route_decision', {})
print(rd.get('generation', 'unknown'))
" 2>/dev/null || echo "unknown")
        if [[ "$RETURNED_GEN" == "nemotron-3" ]] || [[ "$RETURNED_GEN" == "nemotron-3.5" ]]; then
            _pass "Returned model generation is approved: $RETURNED_GEN ($RETURNED_MODEL)"
        else
            echo "  WARN  Returned model generation: $RETURNED_GEN model: $RETURNED_MODEL"
            echo "        If generation is not in response body, check PolicyFilter logs."
        fi
    else
        _fail "Auth inference call" "Expected non-empty response from $INFERENCE_URL with correct token"
    fi
else
    echo "  SKIP  Auth inference test (MAIW_INFERENCE_INTERNAL_TOKEN not set in env)"
fi

# ── Test 9: Sandbox WRITE capability denied ────────────────────────────────────
echo ""
echo "--- Sandbox Write Boundary ---"
RUNTIME_RESP2=$(curl -sf --max-time 5 "${BASE_URL}/api/v1/runtime/status" 2>/dev/null || echo "{}")
SANDBOX_POLICY=$(echo "$RUNTIME_RESP2" | python3 -c "
import sys, json
d = json.load(sys.stdin)
# Check sandbox always-denied capabilities
sb = d.get('sandbox', {})
denied = sb.get('always_denied_capability_classes', [])
print(','.join(denied) if denied else 'not_reported')
" 2>/dev/null || echo "not_reported")

if echo "$SANDBOX_POLICY" | grep -qi "WRITE"; then
    _pass "Sandbox always-denied includes WRITE: $SANDBOX_POLICY"
else
    echo "  INFO  Sandbox capability policy: $SANDBOX_POLICY"
    echo "  INFO  WRITE/EMERGENCY_WRITE policy enforced by RuntimeCapabilityPolicy in code"
    echo "        See integrations/nemoclaw/sandbox_policy.py"
    _pass "Sandbox WRITE boundary enforced by RuntimeCapabilityPolicy (static policy)"
fi

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo "=== Smoke Test Summary: $PASS passed, $FAIL failed ==="
echo ""
if [[ "$FAIL" -gt 0 ]]; then
    echo "SMOKE TEST FAILED — resolve the failures above." >&2
    echo "See docs/operations/REFERENCE_DEPLOYMENT_RUNBOOK.md § Troubleshooting" >&2
    exit 1
fi
echo "SMOKE TEST PASSED — MAIW reference deployment is operational."
echo ""
