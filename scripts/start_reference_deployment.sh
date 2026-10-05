#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# start_reference_deployment.sh — bring up the MAIW v2 reference deployment
#
# Starts services in the correct dependency order (Step 7):
#   1. Validate persistence dirs and config (preflight)
#   2. Ensure approved model provider is reachable
#   3. Start MAIW API (ModelGateway, PolicyFilter, SOP Engine, GovernanceInbox)
#   4. Wait for MAIW API readiness
#   5. Print safe deployment summary (no secrets)
#
# Usage:
#   bash scripts/start_reference_deployment.sh [--skip-preflight]
#
# Environment variables:
#   See .env.example and docs/operations/REFERENCE_DEPLOYMENT_RUNBOOK.md
#   MAIW_PERSISTENCE_ROOT  — durable state root (default /var/lib/maiw)
#   MAIW_API_PORT          — MAIW API port (default 8001)
#   MAIW_API_HOST          — MAIW API bind address (default 0.0.0.0)
#   MAIW_INFERENCE_PORT    — inference sub-endpoint port (default 8020)
#
# Step 9 of Phase 20C-C.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SKIP_PREFLIGHT="${1:-}"
MAIW_PERSISTENCE_ROOT="${MAIW_PERSISTENCE_ROOT:-/var/lib/maiw}"
MAIW_API_PORT="${MAIW_API_PORT:-8001}"
MAIW_API_HOST="${MAIW_API_HOST:-0.0.0.0}"
READINESS_TIMEOUT_S=120
READINESS_POLL_S=2

echo "=== MAIW v2 Reference Deployment — Start ==="
echo "Persistence root: $MAIW_PERSISTENCE_ROOT"
echo "API port: $MAIW_API_PORT"
echo ""

# ── Step 1: Preflight ─────────────────────────────────────────────────────────
if [[ "$SKIP_PREFLIGHT" != "--skip-preflight" ]]; then
    echo "--- Preflight checks ---"
    bash "$SCRIPT_DIR/preflight_reference_deployment.sh"
else
    echo "--- Preflight skipped (--skip-preflight) ---"
fi

# ── Step 2: Create persistence dirs ──────────────────────────────────────────
echo ""
echo "--- Persistence directories ---"
PERSIST_DIRS=(
    "${MAIW_PERSISTENCE_ROOT}/procedures"
    "${MAIW_PERSISTENCE_ROOT}/governance"
    "${MAIW_PERSISTENCE_ROOT}/runtime"
)
for dir in "${PERSIST_DIRS[@]}"; do
    if [[ ! -d "$dir" ]]; then
        mkdir -p "$dir"
        echo "  Created: $dir"
    else
        echo "  Exists:  $dir"
    fi
    # Enforce permissions: not world-writable (Step 30)
    chmod 700 "$dir"
done

# ── Step 3: Load environment ──────────────────────────────────────────────────
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    echo ""
    echo "--- Loading .env ---"
    set -a
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/.env"
    set +a
    echo "  .env loaded"
fi

# Export persistence paths for the API process
export MAIW_PROCEDURE_STATE_DIR="${MAIW_PERSISTENCE_ROOT}/procedures"
export MAIW_GOVERNANCE_STATE_DIR="${MAIW_PERSISTENCE_ROOT}/governance"
export MAIW_RUNTIME_STATE_DIR="${MAIW_PERSISTENCE_ROOT}/runtime"

# ── Step 4: Check approved model provider ────────────────────────────────────
echo ""
echo "--- Approved model provider ---"
NIM_URL="${LLM_NIM_URL:-https://integrate.api.nvidia.com/v1}"
MODEL_ID="${LLM_MODEL:-nvidia/nemotron-3-super-120b-a12b}"

if curl -sf --max-time 10 "${NIM_URL%/v1}/health/ready" &>/dev/null 2>&1 || \
   curl -sf --max-time 10 "${NIM_URL}/models" -H "Authorization: Bearer ${NVIDIA_API_KEY:-}" &>/dev/null 2>&1; then
    echo "  Provider reachable: $NIM_URL"
    echo "  Model: $MODEL_ID"
else
    echo "  WARNING: Provider not immediately reachable at $NIM_URL" >&2
    echo "  The MAIW API will start but model gateway will be degraded until provider is available." >&2
    echo "  Check NVIDIA_API_KEY and LLM_NIM_URL." >&2
fi

# ── Step 5: Check virtual environment / packages ──────────────────────────────
echo ""
echo "--- Python packages ---"
if [[ -d "$PROJECT_ROOT/env" ]]; then
    echo "  Activating virtual environment: $PROJECT_ROOT/env"
    # shellcheck disable=SC1091
    source "$PROJECT_ROOT/env/bin/activate"
elif [[ -n "${VIRTUAL_ENV:-}" ]]; then
    echo "  Using active virtual environment: $VIRTUAL_ENV"
else
    echo "  No virtual environment found — using system Python"
    echo "  Tip: create env with ./scripts/setup/setup_environment.sh"
fi

if ! python3 -c "import maiw_api" &>/dev/null 2>&1; then
    echo "  Installing packages (editable)..."
    pip install --quiet -e "$PROJECT_ROOT" -e "$PROJECT_ROOT/packages/maiw-models" \
        -e "$PROJECT_ROOT/packages/maiw-agents" -e "$PROJECT_ROOT/packages/maiw-mcp" \
        -e "$PROJECT_ROOT/apps/api" 2>&1 || true
fi

# ── Step 6: Start MAIW API ─────────────────────────────────────────────────────
echo ""
echo "--- Starting MAIW API ---"
echo "  Host: $MAIW_API_HOST"
echo "  Port: $MAIW_API_PORT"
echo "  Persistence: $MAIW_PERSISTENCE_ROOT"
echo "  Sandbox mode: ${MAIW_SANDBOX_MODE:-disabled}"

# Start in background if not already running
PIDFILE="${MAIW_RUNTIME_STATE_DIR}/maiw-api.pid"
if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "  MAIW API already running (PID $(cat "$PIDFILE"))"
else
    python3 -m uvicorn maiw_api.app:app \
        --host "$MAIW_API_HOST" \
        --port "$MAIW_API_PORT" \
        --no-access-log \
        >> "${MAIW_PERSISTENCE_ROOT}/runtime/maiw-api.log" 2>&1 &
    MAIW_PID=$!
    echo "$MAIW_PID" > "$PIDFILE"
    echo "  MAIW API started (PID $MAIW_PID)"
fi

# ── Step 7: Wait for readiness ────────────────────────────────────────────────
echo ""
echo "--- Waiting for MAIW API readiness (timeout: ${READINESS_TIMEOUT_S}s) ---"
READY_URL="http://127.0.0.1:${MAIW_API_PORT}/api/v1/ready"
ELAPSED=0

until curl -sf --max-time 5 "$READY_URL" &>/dev/null; do
    if [[ "$ELAPSED" -ge "$READINESS_TIMEOUT_S" ]]; then
        echo "  ERROR: MAIW API did not become ready within ${READINESS_TIMEOUT_S}s" >&2
        echo "  Expected: HTTP 200 from $READY_URL" >&2
        echo "  Actual:   no response" >&2
        echo "  Next: check logs at ${MAIW_PERSISTENCE_ROOT}/runtime/maiw-api.log" >&2
        echo "  Run: bash scripts/status_reference_deployment.sh" >&2
        exit 1
    fi
    sleep "$READINESS_POLL_S"
    ELAPSED=$((ELAPSED + READINESS_POLL_S))
    echo "  Waiting... ${ELAPSED}s"
done

echo "  MAIW API is ready (${ELAPSED}s)"

# ── Step 8: Print safe summary (no secrets) ───────────────────────────────────
echo ""
echo "=== MAIW v2 Reference Deployment — RUNNING ==="
echo ""
echo "  MAIW API:              http://${MAIW_API_HOST}:${MAIW_API_PORT}"
echo "  Health:                http://${MAIW_API_HOST}:${MAIW_API_PORT}/api/v1/health"
echo "  Readiness:             http://${MAIW_API_HOST}:${MAIW_API_PORT}/api/v1/ready"
echo "  Liveness:              http://${MAIW_API_HOST}:${MAIW_API_PORT}/api/v1/live"
echo "  Inference endpoint:    POST /api/v1/inference (auth required)"
echo ""
echo "  Approved model family: Nemotron 3 / Nemotron 3.5 only"
echo "  Configured model:      ${MODEL_ID}"
echo "  Sandbox mode:          ${MAIW_SANDBOX_MODE:-disabled}"
echo ""
echo "  Procedure state:       ${MAIW_PERSISTENCE_ROOT}/procedures/"
echo "  Governance state:      ${MAIW_PERSISTENCE_ROOT}/governance/"
echo "  API log:               ${MAIW_PERSISTENCE_ROOT}/runtime/maiw-api.log"
echo ""
echo "  Tokens / credentials:  NOT printed (check .env)"
echo ""
echo "Next steps:"
echo "  smoke test:  bash scripts/smoke_test_reference_deployment.sh"
echo "  status:      bash scripts/status_reference_deployment.sh"
echo "  stop:        bash scripts/stop_reference_deployment.sh"
echo ""
