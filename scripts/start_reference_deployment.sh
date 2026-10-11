#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# start_reference_deployment.sh — bring up the MAIW v2 reference deployment
#
# Order (v2.0.1 round 2 — load env → validate → start):
#   1. Load the environment (scripts/lib/load_env.sh — the same loader every
#      deployment script uses)
#   2. Preflight the EFFECTIVE configuration (unless --skip-preflight)
#   3. Create persistence dirs
#   4. Start the canonical shipped app — uvicorn maiw_api.app:app — with a
#      fresh MAIW_INSTANCE_ID, and record its deployment identity in
#      $MAIW_PERSISTENCE_ROOT/runtime/maiw-api.instance
#   5. Wait for /api/v1/ready = 200 on THIS instance (identity checked first)
#   6. Print a safe summary (no secrets)
#
# There is no separate inference server: POST /api/v1/inference is served by
# the canonical app on MAIW_API_PORT.  The legacy src/api/app.py is never
# started by this script.
#
# Usage:
#   bash scripts/start_reference_deployment.sh [--skip-preflight]
#
# Required (from .env or the shell): MAIW_PERSISTENCE_ROOT, MAIW_API_PORT,
# MAIW_PYTHON (an interpreter that imports maiw_api from THIS checkout).
# See .env.example and docs/operations/REFERENCE_DEPLOYMENT_RUNBOOK.md.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
# shellcheck source=lib/load_env.sh
source "$SCRIPT_DIR/lib/load_env.sh"
# shellcheck source=lib/deployment_identity.sh
source "$SCRIPT_DIR/lib/deployment_identity.sh"

SKIP_PREFLIGHT="${1:-}"
READINESS_TIMEOUT_S="${MAIW_READINESS_TIMEOUT_S:-120}"
READINESS_POLL_S=2

echo "=== MAIW v2 Reference Deployment — Start ==="

# ── Step 1: Load environment (BEFORE preflight) ───────────────────────────────
maiw_load_env "$PROJECT_ROOT"
maiw_require_vars MAIW_PERSISTENCE_ROOT MAIW_API_PORT MAIW_PYTHON
MAIW_API_HOST="${MAIW_API_HOST:-127.0.0.1}"
export MAIW_PERSISTENCE_ROOT MAIW_API_PORT MAIW_API_HOST
echo "Persistence root: $MAIW_PERSISTENCE_ROOT"
echo "API: $MAIW_API_HOST:$MAIW_API_PORT"
echo "Profile: ${MAIW_DEPLOYMENT_PROFILE:-reference}"
echo ""

# Refuse to start a second instance over a verified running one.
if maiw_verify_instance --no-live; then
    echo "  MAIW API already running (PID $MAIW_TARGET_PID, port $MAIW_TARGET_PORT) — nothing to do."
    echo "  Use scripts/restart_reference_deployment.sh to restart it."
    exit 0
fi

# ── Step 2: Preflight the effective configuration ─────────────────────────────
if [[ "$SKIP_PREFLIGHT" != "--skip-preflight" ]]; then
    echo "--- Preflight checks ---"
    bash "$SCRIPT_DIR/preflight_reference_deployment.sh"
else
    echo "--- Preflight skipped (--skip-preflight) ---"
fi

# ── Step 3: Persistence directories ───────────────────────────────────────────
echo ""
echo "--- Persistence directories ---"
export MAIW_PROCEDURE_STATE_DIR="${MAIW_PROCEDURE_STATE_DIR:-${MAIW_PERSISTENCE_ROOT}/procedures}"
export MAIW_GOVERNANCE_STATE_DIR="${MAIW_GOVERNANCE_STATE_DIR:-${MAIW_PERSISTENCE_ROOT}/governance}"
export MAIW_RUNTIME_STATE_DIR="${MAIW_RUNTIME_STATE_DIR:-${MAIW_PERSISTENCE_ROOT}/runtime}"
unset MAIW_PERSISTENCE_MODE  # reference profile is always file-backed
for dir in "$MAIW_PROCEDURE_STATE_DIR" "$MAIW_GOVERNANCE_STATE_DIR" "$MAIW_RUNTIME_STATE_DIR"; do
    if [[ ! -d "$dir" ]]; then
        mkdir -p "$dir"
        echo "  Created: $dir"
    else
        echo "  Exists:  $dir"
    fi
    chmod 700 "$dir"  # never world-writable (Step 30)
done

# ── Step 4: Python interpreter must import maiw_api from THIS checkout ────────
echo ""
echo "--- Python packages ---"
API_INIT="$("$MAIW_PYTHON" -c 'import maiw_api, os; print(os.path.realpath(maiw_api.__file__))' 2>/dev/null || true)"
if [[ "$API_INIT" != "$PROJECT_ROOT/"* ]]; then
    echo "  ERROR: MAIW_PYTHON=$MAIW_PYTHON does not import maiw_api from $PROJECT_ROOT" >&2
    echo "         (got: ${API_INIT:-not importable}). Install per the runbook § Install." >&2
    exit 1
fi
echo "  maiw_api: $API_INIT"

# ── Step 5: Start MAIW API ────────────────────────────────────────────────────
echo ""
echo "--- Starting MAIW API ---"
INSTANCE_ID="$(maiw_new_instance_id)"
LOG_FILE="${MAIW_RUNTIME_STATE_DIR}/maiw-api.log"
cd "$PROJECT_ROOT"
MAIW_INSTANCE_ID="$INSTANCE_ID" nohup "$MAIW_PYTHON" -m uvicorn maiw_api.app:app \
    --host "$MAIW_API_HOST" \
    --port "$MAIW_API_PORT" \
    --no-access-log \
    >> "$LOG_FILE" 2>&1 < /dev/null &
MAIW_PID=$!
maiw_write_instance "$INSTANCE_ID" "$MAIW_PID" "$MAIW_API_HOST" "$MAIW_API_PORT" "$PROJECT_ROOT"
echo "  MAIW API started (PID $MAIW_PID, instance ${INSTANCE_ID:0:8}…)"

# ── Step 6: Wait for readiness of THIS instance ───────────────────────────────
echo ""
echo "--- Waiting for MAIW API readiness (timeout: ${READINESS_TIMEOUT_S}s) ---"
ELAPSED=0
READY_HTTP="000"
while :; do
    if ! kill -0 "$MAIW_PID" 2>/dev/null; then
        echo "  ERROR: MAIW API process $MAIW_PID exited (port in use or startup failure)." >&2
        echo "  Log: $LOG_FILE" >&2
        tail -n 20 "$LOG_FILE" >&2 || true
        maiw_clear_instance
        exit 1
    fi
    if maiw_verify_instance; then
        READY_HTTP=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 \
            "${MAIW_TARGET_BASE_URL}/api/v1/ready" 2>/dev/null || echo "000")
        [[ "$READY_HTTP" == "200" ]] && break
    fi
    if [[ "$ELAPSED" -ge "$READINESS_TIMEOUT_S" ]]; then
        echo "  ERROR: MAIW API did not become ready within ${READINESS_TIMEOUT_S}s" >&2
        if [[ -n "${MAIW_TARGET_BASE_URL:-}" ]]; then
            FAILED=$(curl -s --max-time 15 "${MAIW_TARGET_BASE_URL}/api/v1/ready" 2>/dev/null \
                | "$MAIW_PYTHON" -c "import sys,json; print(','.join(json.load(sys.stdin).get('failed_components', [])))" 2>/dev/null || echo "?")
            echo "  Actual:   NOT_READY (HTTP $READY_HTTP) — failed components: ${FAILED}" >&2
        else
            echo "  Actual:   instance identity not established (${MAIW_VERIFY_REASON:-})" >&2
        fi
        echo "  The process is left running for diagnosis: bash scripts/status_reference_deployment.sh" >&2
        echo "  Log: $LOG_FILE ; stop with: bash scripts/stop_reference_deployment.sh" >&2
        exit 1
    fi
    sleep "$READINESS_POLL_S"
    ELAPSED=$((ELAPSED + READINESS_POLL_S))
    echo "  Waiting... ${ELAPSED}s"
done
echo "  MAIW API is ready (${ELAPSED}s)"

# ── Step 7: Safe summary (no secrets) ─────────────────────────────────────────
echo ""
echo "=== MAIW v2 Reference Deployment — RUNNING ==="
echo ""
echo "  MAIW API:              http://${MAIW_API_HOST}:${MAIW_API_PORT}"
echo "  Readiness:             http://127.0.0.1:${MAIW_API_PORT}/api/v1/ready"
echo "  Inference endpoint:    POST /api/v1/inference (X-Maiw-Internal-Token required)"
echo "  Deployment identity:   $(maiw_instance_file)"
echo "  Profile:               ${MAIW_DEPLOYMENT_PROFILE:-reference}"
echo "  Sandbox mode:          ${MAIW_SANDBOX_MODE:-disabled} ${MAIW_SANDBOX_NAME:+(sandbox $MAIW_SANDBOX_NAME)}"
echo ""
echo "  Approved physical model bindings (same check the gateway runs):"
"$MAIW_PYTHON" "$SCRIPT_DIR/lib/check_model_config.py" | sed 's/^/    /' || true
echo ""
echo "  Procedure state:       ${MAIW_PROCEDURE_STATE_DIR}/"
echo "  Governance state:      ${MAIW_GOVERNANCE_STATE_DIR}/"
echo "  API log:               ${LOG_FILE}"
echo "  Tokens / credentials:  NOT printed"
echo ""
echo "Next steps:"
echo "  status:      bash scripts/status_reference_deployment.sh"
echo "  smoke test:  bash scripts/smoke_test_reference_deployment.sh"
echo "  stop:        bash scripts/stop_reference_deployment.sh"
echo ""
