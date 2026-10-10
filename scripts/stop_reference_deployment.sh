#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# stop_reference_deployment.sh — stop the MAIW v2 reference deployment
#
# v2.0.1 round 2 (P2-01 / NEW-P1-02): this script terminates ONLY the PID
# recorded in this deployment's own instance-state file, and only after
# verifying from /proc that the PID is that MAIW instance (uvicorn
# maiw_api.app:app on the recorded port, started from this checkout, with the
# recorded MAIW_INSTANCE_ID).  There is NO kill-by-port and NO kill-by-name
# fallback: with no or stale state it reports "NOT RUNNING / CANNOT VERIFY" and
# signals nothing.  OpenShell sandboxes are never touched (manage them with
# `openshell sandbox ...` / scripts/setup/reference_sandbox.sh).
#
# Durable procedure/governance state is preserved unless --delete-state.
#
# Usage:
#   bash scripts/stop_reference_deployment.sh [--delete-state]
#
# Exit codes: 0 stopped (or already stopped with no state);
#             3 NOT RUNNING / CANNOT VERIFY (state present but not verifiable).
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
# shellcheck source=lib/load_env.sh
source "$SCRIPT_DIR/lib/load_env.sh"
# shellcheck source=lib/deployment_identity.sh
source "$SCRIPT_DIR/lib/deployment_identity.sh"

DELETE_STATE="${1:-}"

echo "=== MAIW v2 Reference Deployment — Stop ==="
maiw_load_env "$PROJECT_ROOT"
maiw_require_vars MAIW_PERSISTENCE_ROOT
EXIT_CODE=0

# ── Sandbox (report only) ─────────────────────────────────────────────────────
echo ""
echo "--- Sandbox runtime ---"
if command -v openshell &>/dev/null && [[ -n "${MAIW_SANDBOX_NAME:-}" ]]; then
    PHASE=$(openshell sandbox list -o json 2>/dev/null | "${MAIW_PYTHON:-python3}" -c "
import sys, json
name = sys.argv[1]
for s in json.load(sys.stdin):
    if s.get('name') == name:
        print(s.get('phase', '')); break
" "$MAIW_SANDBOX_NAME" 2>/dev/null || echo "")
    echo "  Sandbox '${MAIW_SANDBOX_NAME}': ${PHASE:-not found} (left running; manage with openshell)"
else
    echo "  No sandbox action (MAIW_SANDBOX_NAME not set)"
fi

# ── MAIW API — verified PID only ──────────────────────────────────────────────
echo ""
echo "--- MAIW API ---"
set +e
maiw_verify_instance --no-live
VRC=$?
set -e
case "$VRC" in
    0)
        echo "  Verified MAIW instance: PID $MAIW_TARGET_PID, port $MAIW_TARGET_PORT"
        echo "  Sending SIGTERM to PID $MAIW_TARGET_PID..."
        kill -TERM "$MAIW_TARGET_PID" 2>/dev/null || true
        WAIT=0
        while kill -0 "$MAIW_TARGET_PID" 2>/dev/null && [[ "$WAIT" -lt 30 ]]; do
            sleep 1
            WAIT=$((WAIT + 1))
        done
        if kill -0 "$MAIW_TARGET_PID" 2>/dev/null; then
            # Re-verify identity before escalating: never SIGKILL a reused PID.
            if maiw_pid_is_instance "$MAIW_TARGET_PID" "$MAIW_TARGET_PORT" "$MAIW_I_ROOT" "$MAIW_TARGET_INSTANCE_ID"; then
                echo "  MAIW API did not exit after ${WAIT}s; sending SIGKILL to PID $MAIW_TARGET_PID"
                kill -KILL "$MAIW_TARGET_PID" 2>/dev/null || true
            fi
        fi
        maiw_clear_instance
        echo "  MAIW API stopped (PID $MAIW_TARGET_PID)"
        ;;
    10)
        echo "  MAIW API: NOT RUNNING / CANNOT VERIFY — ${MAIW_VERIFY_REASON}"
        echo "  Nothing was signalled (no kill-by-port fallback)."
        ;;
    11)
        echo "  MAIW API: NOT RUNNING / CANNOT VERIFY — ${MAIW_VERIFY_REASON}"
        echo "  Removing stale deployment state; nothing was signalled."
        maiw_clear_instance
        ;;
    *)
        echo "  MAIW API: NOT RUNNING / CANNOT VERIFY — ${MAIW_VERIFY_REASON}" >&2
        echo "  Nothing was signalled. Investigate manually; state left in place: $(maiw_instance_file)" >&2
        EXIT_CODE=3
        ;;
esac

# ── Durable state report ──────────────────────────────────────────────────────
echo ""
echo "--- Durable state ---"
PROC_DIR="${MAIW_PROCEDURE_STATE_DIR:-${MAIW_PERSISTENCE_ROOT}/procedures}"
GOV_DIR="${MAIW_GOVERNANCE_STATE_DIR:-${MAIW_PERSISTENCE_ROOT}/governance}"
if [[ -d "$PROC_DIR" ]]; then
    PROC_COUNT=$(find "$PROC_DIR" -name "*.json" 2>/dev/null | wc -l)
    echo "  Procedure state files preserved: $PROC_COUNT (in $PROC_DIR)"
else
    echo "  No procedure state directory found"
fi
GOV_FILE="${GOV_DIR}/governance_inbox.jsonl"
if [[ -f "$GOV_FILE" ]]; then
    GOV_ENTRIES=$(grep -vc '"event": "applied"' "$GOV_FILE" 2>/dev/null || true)
    echo "  Governance inbox accepted outcomes preserved: ${GOV_ENTRIES:-0} (in $GOV_FILE)"
else
    echo "  No governance inbox file found"
fi

if [[ "$DELETE_STATE" == "--delete-state" ]]; then
    echo ""
    echo "  WARNING: --delete-state requested — removing all durable state!"
    read -r -p "  Confirm deletion (type DELETE): " CONFIRM
    if [[ "$CONFIRM" == "DELETE" ]]; then
        rm -rf "$PROC_DIR" "$GOV_DIR"
        echo "  Durable state deleted."
    else
        echo "  Deletion cancelled."
    fi
fi

echo ""
echo "=== MAIW v2 Reference Deployment — STOP COMPLETE ==="
echo "  Durable state has been preserved (unless --delete-state was used)."
echo "  To start again: bash scripts/start_reference_deployment.sh"
exit "$EXIT_CODE"
