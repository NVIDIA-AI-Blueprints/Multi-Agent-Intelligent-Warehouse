#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# restart_reference_deployment.sh — restart the MAIW v2 reference deployment
#
# Restart MUST preserve (Step 11): ProcedureExecutionState, GovernanceInbox
# entries, correlation IDs, SOP version pinning, retry/loop budgets and
# WAITING_FOR_GOVERNANCE state (all file-backed under MAIW_PERSISTENCE_ROOT).
#
# v2.0.1 round 2: restart acts only on a VERIFIED deployment identity (see
# scripts/lib/deployment_identity.sh).  If the running instance cannot be
# verified — no state, stale PID, a different process, or a port that does not
# answer as this instance — restart REFUSES and changes nothing.  Use
# start_reference_deployment.sh when nothing is running.
#
# Usage:
#   bash scripts/restart_reference_deployment.sh [--skip-preflight]
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
# shellcheck source=lib/load_env.sh
source "$SCRIPT_DIR/lib/load_env.sh"
# shellcheck source=lib/deployment_identity.sh
source "$SCRIPT_DIR/lib/deployment_identity.sh"

SKIP_PREFLIGHT="${1:-}"

echo "=== MAIW v2 Reference Deployment — Restart ==="
maiw_load_env "$PROJECT_ROOT"
maiw_require_vars MAIW_PERSISTENCE_ROOT

set +e
maiw_verify_instance
VRC=$?
set -e
if [[ "$VRC" -ne 0 ]]; then
    echo "  REFUSED: NOT RUNNING / CANNOT VERIFY — ${MAIW_VERIFY_REASON}" >&2
    echo "  Nothing was stopped or started. If nothing is running, use:" >&2
    echo "    bash scripts/start_reference_deployment.sh" >&2
    exit 2
fi
echo "  Verified MAIW instance: PID $MAIW_TARGET_PID, port $MAIW_TARGET_PORT"
echo ""

# ── Pre-restart: snapshot durable state ──────────────────────────────────────
echo "--- Pre-restart state snapshot ---"
PROC_DIR="${MAIW_PROCEDURE_STATE_DIR:-${MAIW_PERSISTENCE_ROOT}/procedures}"
GOV_FILE="${MAIW_GOVERNANCE_STATE_DIR:-${MAIW_PERSISTENCE_ROOT}/governance}/governance_inbox.jsonl"
_count_procs() { find "$PROC_DIR" -name "*.json" 2>/dev/null | wc -l; }
_count_waiting() { grep -lE '"status": ?"waiting_for_governance"' "$PROC_DIR"/*.json 2>/dev/null | wc -l || true; }
_count_gov() { [[ -f "$GOV_FILE" ]] && wc -l < "$GOV_FILE" || echo 0; }
PRE_PROC_COUNT=$(_count_procs)
PRE_WAITING=$(_count_waiting)
PRE_GOV_COUNT=$(_count_gov)
echo "  Procedure state files: $PRE_PROC_COUNT (WAITING_FOR_GOVERNANCE: $PRE_WAITING)"
echo "  Governance inbox entries: $PRE_GOV_COUNT"

# ── Preflight BEFORE stopping: a configuration that cannot start must not take
#    the running instance down ──────────────────────────────────────────────
if [[ "$SKIP_PREFLIGHT" != "--skip-preflight" ]]; then
    echo ""
    echo "--- Preflight (before stopping the running instance) ---"
    if ! bash "$SCRIPT_DIR/preflight_reference_deployment.sh"; then
        echo "  REFUSED: preflight failed — the running instance was left untouched." >&2
        exit 1
    fi
fi

# ── Stop (verified PID only) → start ─────────────────────────────────────────
echo ""
echo "--- Stopping current deployment ---"
bash "$SCRIPT_DIR/stop_reference_deployment.sh"
echo ""
echo "--- Starting deployment ---"
bash "$SCRIPT_DIR/start_reference_deployment.sh" --skip-preflight

# ── Post-restart durable state verification ──────────────────────────────────
echo ""
echo "--- Post-restart durable state verification ---"
POST_PROC_COUNT=$(_count_procs)
POST_WAITING=$(_count_waiting)
POST_GOV_COUNT=$(_count_gov)
echo "  Procedure state files: $POST_PROC_COUNT (WAITING_FOR_GOVERNANCE: $POST_WAITING)"
echo "  Governance inbox entries: $POST_GOV_COUNT"
STATUS=0
if [[ "$POST_PROC_COUNT" -lt "$PRE_PROC_COUNT" ]]; then
    echo "  ERROR: fewer procedure state files after restart" >&2; STATUS=1
fi
if [[ "$POST_WAITING" -lt "$PRE_WAITING" ]]; then
    echo "  WARNING: fewer WAITING_FOR_GOVERNANCE procedures after restart" >&2
fi
if [[ "$POST_GOV_COUNT" -lt "$PRE_GOV_COUNT" ]]; then
    echo "  ERROR: governance inbox shrank after restart" >&2; STATUS=1
fi

echo ""
echo "=== MAIW v2 Reference Deployment — Restart Complete ==="
echo "  Run the smoke test: bash scripts/smoke_test_reference_deployment.sh"
exit "$STATUS"
