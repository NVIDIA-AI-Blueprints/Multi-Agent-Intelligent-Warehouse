#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# stop_reference_deployment.sh — stop the MAIW v2 reference deployment
#
# Stop order (Step 7 reverse):
#   1. Stop sandbox/OpenShell runtime (if running)
#   2. Stop MAIW API
#   3. Preserve durable procedure/governance state (do NOT delete by default)
#   4. Report what remained running
#
# Usage:
#   bash scripts/stop_reference_deployment.sh [--delete-state]
#
# Options:
#   --delete-state  Remove durable state after stop (destructive — do not use
#                   in production; use only for clean-slate test cycles)
#
# Step 10 of Phase 20C-C.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DELETE_STATE="${1:-}"

MAIW_PERSISTENCE_ROOT="${MAIW_PERSISTENCE_ROOT:-/var/lib/maiw}"
PIDFILE="${MAIW_PERSISTENCE_ROOT}/runtime/maiw-api.pid"

echo "=== MAIW v2 Reference Deployment — Stop ==="

ANYTHING_REMAINED=0

# ── Step 1: Sandbox/OpenShell runtime (report only) ──────────────────────────
# v2.0.1: this script no longer signals processes matched by a name pattern
# (`pgrep -f "openshell.*maiw"`), which could hit unrelated sandboxes, CLI
# sessions or gateways on a shared host. OpenShell sandboxes are owned by the
# OpenShell control plane: stop or delete one explicitly with
#   openshell sandbox delete <name>
# Stopping the MAIW API never requires killing a sandbox — a sandboxed agent
# simply cannot reach the inference endpoint while the API is down.
echo ""
echo "--- Sandbox runtime ---"
if command -v openshell &>/dev/null && [[ -n "${MAIW_SANDBOX_NAME:-}" ]]; then
    PHASE=$(openshell sandbox list -o json 2>/dev/null | python3 -c "
import sys, json
for s in json.load(sys.stdin):
    if s.get('name') == '${MAIW_SANDBOX_NAME}':
        print(s.get('phase', '')); break
" 2>/dev/null || echo "")
    echo "  Sandbox '${MAIW_SANDBOX_NAME}': ${PHASE:-not found} (left running; manage with openshell)"
else
    echo "  No sandbox action (set MAIW_SANDBOX_NAME to report its phase)"
fi

# ── Step 2: Stop MAIW API ────────────────────────────────────────────────────
echo ""
echo "--- MAIW API ---"
if [[ -f "$PIDFILE" ]]; then
    MAIW_PID=$(cat "$PIDFILE")
    if kill -0 "$MAIW_PID" 2>/dev/null; then
        echo "  Sending SIGTERM to MAIW API (PID $MAIW_PID)..."
        kill -TERM "$MAIW_PID" 2>/dev/null || true
        WAIT=0
        while kill -0 "$MAIW_PID" 2>/dev/null && [[ "$WAIT" -lt 30 ]]; do
            sleep 1
            WAIT=$((WAIT + 1))
        done
        if kill -0 "$MAIW_PID" 2>/dev/null; then
            echo "  MAIW API did not exit after ${WAIT}s; sending SIGKILL"
            kill -KILL "$MAIW_PID" 2>/dev/null || true
        fi
        echo "  MAIW API stopped (PID $MAIW_PID)"
        rm -f "$PIDFILE"
    else
        echo "  PID $MAIW_PID is not running (stale pidfile)"
        rm -f "$PIDFILE"
    fi
else
    # Try to find by port
    MAIW_API_PORT="${MAIW_API_PORT:-8001}"
    API_PID=$(lsof -ti :"$MAIW_API_PORT" 2>/dev/null || true)
    if [[ -n "$API_PID" ]]; then
        echo "  Found MAIW API on port $MAIW_API_PORT (PID $API_PID); stopping..."
        kill -TERM "$API_PID" 2>/dev/null || true
        sleep 3
        if kill -0 "$API_PID" 2>/dev/null; then
            kill -KILL "$API_PID" 2>/dev/null || true
        fi
        echo "  MAIW API stopped"
    else
        echo "  MAIW API not found running on port $MAIW_API_PORT"
        ANYTHING_REMAINED=$((ANYTHING_REMAINED + 1))
    fi
fi

# ── Step 3: Durable state report ──────────────────────────────────────────────
echo ""
echo "--- Durable state ---"
PROC_DIR="${MAIW_PERSISTENCE_ROOT}/procedures"
GOV_DIR="${MAIW_PERSISTENCE_ROOT}/governance"

if [[ -d "$PROC_DIR" ]]; then
    PROC_COUNT=$(find "$PROC_DIR" -name "*.json" 2>/dev/null | wc -l)
    echo "  Procedure state files preserved: $PROC_COUNT (in $PROC_DIR)"
else
    echo "  No procedure state directory found"
fi

if [[ -d "$GOV_DIR" ]]; then
    GOV_FILE="${GOV_DIR}/governance_inbox.jsonl"
    if [[ -f "$GOV_FILE" ]]; then
        GOV_ENTRIES=$(wc -l < "$GOV_FILE" 2>/dev/null || echo 0)
        echo "  Governance inbox entries preserved: $GOV_ENTRIES (in $GOV_FILE)"
    else
        echo "  No governance inbox file found"
    fi
else
    echo "  No governance state directory found"
fi

# Optionally delete state (destructive — operator must opt in explicitly)
if [[ "$DELETE_STATE" == "--delete-state" ]]; then
    echo ""
    echo "  WARNING: --delete-state requested — removing all durable state!"
    echo "  This is irreversible. MAIW will start fresh on next boot."
    read -r -p "  Confirm deletion (type DELETE): " CONFIRM
    if [[ "$CONFIRM" == "DELETE" ]]; then
        rm -rf "${MAIW_PERSISTENCE_ROOT}/procedures/"
        rm -rf "${MAIW_PERSISTENCE_ROOT}/governance/"
        echo "  Durable state deleted."
    else
        echo "  Deletion cancelled."
    fi
fi

# ── Step 4: Summary ───────────────────────────────────────────────────────────
echo ""
echo "=== MAIW v2 Reference Deployment — STOPPED ==="
echo ""
if [[ "$ANYTHING_REMAINED" -gt 0 ]]; then
    echo "  NOTE: Some components were not found running — they may have already been stopped."
fi
echo "  Durable state has been preserved (unless --delete-state was used)."
echo "  To restart: bash scripts/start_reference_deployment.sh"
echo ""
