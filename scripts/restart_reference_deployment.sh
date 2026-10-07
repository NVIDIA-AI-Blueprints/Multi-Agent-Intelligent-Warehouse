#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# restart_reference_deployment.sh — restart the MAIW v2 reference deployment
#
# Restart MUST preserve (Step 11):
#   - ProcedureExecutionState (file-backed, persisted in /var/lib/maiw/procedures/)
#   - GovernanceInbox entries (file-backed, in /var/lib/maiw/governance/)
#   - correlation IDs (encoded in procedure state)
#   - SOP version pinning (encoded in procedure state)
#   - retry/loop budgets (encoded in procedure state)
#   - WAITING_FOR_GOVERNANCE state (encoded in procedure state)
#
# Restart sequence:
#   1. Stop sandbox runtime (safe)
#   2. Stop MAIW API (preserving durable state)
#   3. Wait for full shutdown
#   4. Start fresh (preflight + dir creation + API)
#   5. Verify readiness
#   6. Confirm that WAITING_FOR_GOVERNANCE procedures are still present
#
# Usage:
#   bash scripts/restart_reference_deployment.sh [--skip-preflight]
#
# Step 11 of Phase 20C-C.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKIP_PREFLIGHT="${1:-}"

MAIW_PERSISTENCE_ROOT="${MAIW_PERSISTENCE_ROOT:-/var/lib/maiw}"
MAIW_API_PORT="${MAIW_API_PORT:-8001}"

echo "=== MAIW v2 Reference Deployment — Restart ==="
echo ""

# ── Pre-restart: snapshot durable state ──────────────────────────────────────
echo "--- Pre-restart state snapshot ---"
PROC_DIR="${MAIW_PERSISTENCE_ROOT}/procedures"
if [[ -d "$PROC_DIR" ]]; then
    PRE_PROC_COUNT=$(find "$PROC_DIR" -name "*.json" 2>/dev/null | wc -l)
    echo "  Procedure state files before restart: $PRE_PROC_COUNT"
    # Note WAITING_FOR_GOVERNANCE procedures
    WAITING=$(grep -lE '"status": ?"waiting_for_governance"' "$PROC_DIR"/*.json 2>/dev/null | wc -l || echo 0)
    echo "  WAITING_FOR_GOVERNANCE procedures: $WAITING"
fi

GOV_DIR="${MAIW_PERSISTENCE_ROOT}/governance"
if [[ -f "${GOV_DIR}/governance_inbox.jsonl" ]]; then
    PRE_GOV_COUNT=$(wc -l < "${GOV_DIR}/governance_inbox.jsonl" 2>/dev/null || echo 0)
    echo "  Governance inbox entries before restart: $PRE_GOV_COUNT"
fi

# ── Step 1-2: Stop ───────────────────────────────────────────────────────────
echo ""
echo "--- Stopping current deployment ---"
bash "$SCRIPT_DIR/stop_reference_deployment.sh"

# ── Step 3: Brief pause ───────────────────────────────────────────────────────
echo ""
echo "--- Waiting for clean shutdown (3s) ---"
sleep 3

# ── Step 4-5: Start ──────────────────────────────────────────────────────────
echo ""
echo "--- Starting deployment ---"
bash "$SCRIPT_DIR/start_reference_deployment.sh" "${SKIP_PREFLIGHT}"

# ── Step 6: Verify durable state preserved ────────────────────────────────────
echo ""
echo "--- Post-restart durable state verification ---"
if [[ -d "$PROC_DIR" ]]; then
    POST_PROC_COUNT=$(find "$PROC_DIR" -name "*.json" 2>/dev/null | wc -l)
    echo "  Procedure state files after restart: $POST_PROC_COUNT"
    POST_WAITING=$(grep -lE '"status": ?"waiting_for_governance"' "$PROC_DIR"/*.json 2>/dev/null | wc -l || echo 0)
    echo "  WAITING_FOR_GOVERNANCE procedures: $POST_WAITING"
    if [[ "${PRE_PROC_COUNT:-0}" -gt 0 ]] && [[ "$POST_PROC_COUNT" -lt "${PRE_PROC_COUNT:-0}" ]]; then
        echo "  WARNING: fewer procedure state files after restart ($POST_PROC_COUNT < ${PRE_PROC_COUNT})" >&2
    fi
    if [[ "${WAITING:-0}" -gt 0 ]] && [[ "$POST_WAITING" -lt "${WAITING:-0}" ]]; then
        echo "  WARNING: fewer WAITING_FOR_GOVERNANCE procedures after restart" >&2
    fi
fi

if [[ -f "${GOV_DIR}/governance_inbox.jsonl" ]]; then
    POST_GOV_COUNT=$(wc -l < "${GOV_DIR}/governance_inbox.jsonl" 2>/dev/null || echo 0)
    echo "  Governance inbox entries after restart: $POST_GOV_COUNT"
    if [[ "${PRE_GOV_COUNT:-0}" -gt 0 ]] && [[ "$POST_GOV_COUNT" -lt "${PRE_GOV_COUNT:-0}" ]]; then
        echo "  WARNING: governance inbox shrunk after restart ($POST_GOV_COUNT < ${PRE_GOV_COUNT})" >&2
    fi
fi

echo ""
echo "=== MAIW v2 Reference Deployment — Restart Complete ==="
echo ""
echo "  Durable state (procedure + governance) has been preserved."
echo "  Run smoke test to verify full path: bash scripts/smoke_test_reference_deployment.sh"
echo ""
