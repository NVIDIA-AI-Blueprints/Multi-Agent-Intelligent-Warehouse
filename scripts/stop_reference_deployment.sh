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

# ── Step 1: Stop sandbox/OpenShell runtime ───────────────────────────────────
echo ""
echo "--- Sandbox runtime ---"
if command -v openshell &>/dev/null; then
    # Graceful: signal any running MAIW sandboxes to terminate
    SANDBOX_PIDS=$(pgrep -f "openshell.*maiw" 2>/dev/null || true)
    if [[ -n "$SANDBOX_PIDS" ]]; then
        echo "  Sending SIGTERM to OpenShell sandbox process(es): $SANDBOX_PIDS"
        kill -TERM $SANDBOX_PIDS 2>/dev/null || true
        sleep 2
        # Force if still running
        REMAINING=$(echo "$SANDBOX_PIDS" | while read -r p; do
            kill -0 "$p" 2>/dev/null && echo "$p" || true
        done)
        if [[ -n "$REMAINING" ]]; then
            echo "  Sandbox process(es) still running after SIGTERM; sending SIGKILL"
            kill -KILL $REMAINING 2>/dev/null || true
        fi
        echo "  Sandbox stopped"
    else
        echo "  No OpenShell sandbox processes found"
    fi
else
    echo "  OpenShell not installed or not in PATH — skipping"
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
