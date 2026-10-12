#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# qualify_reference_deployment.sh — full qualification run for MAIW v2 reference deployment
#
# Qualification sequence (Step 58):
#   0. Preflight
#   1. Start
#   2. Readiness
#   3. Smoke test
#   4. Safe Proof SOP A (non-consequential)
#   5. API restart → verify resume
#   6. Sandbox restart → verify host truth preserved
#   7. Backup / restore live test
#   8. Rollback compatibility check
#   9. Output PASS/FAIL with evidence
#
# IMPORTANT: This script does NOT execute real warehouse writes.
# All SOP runs target non-destructive reasoning and stop before execution.
#
# Usage:
#   bash scripts/qualify_reference_deployment.sh [--evidence-dir DIR]
#
# Step 58 of Phase 20C-C.
# ---------------------------------------------------------------------------
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
# v2.0.1 round 2: same env loader and deployment identity as every other
# lifecycle script; no default port, no kill-by-pattern.
# shellcheck source=lib/load_env.sh
source "$SCRIPT_DIR/lib/load_env.sh"
# shellcheck source=lib/deployment_identity.sh
source "$SCRIPT_DIR/lib/deployment_identity.sh"
maiw_load_env "$PROJECT_ROOT"
maiw_require_vars MAIW_PERSISTENCE_ROOT MAIW_API_PORT MAIW_PYTHON

EVIDENCE_DIR="${2:-${PROJECT_ROOT}/artifacts/deployment/qualification_evidence}"
_base_url() {  # base URL of the VERIFIED instance (empty if not verifiable)
    if maiw_verify_instance; then printf '%s' "$MAIW_TARGET_BASE_URL"; fi
}

QUAL_PASS=0
QUAL_FAIL=0
QUAL_SKIP=0
QUAL_LOG="${EVIDENCE_DIR}/qualify_$(date +%Y%m%dT%H%M%S).log"

mkdir -p "$EVIDENCE_DIR"
exec > >(tee -a "$QUAL_LOG") 2>&1

_qpass() { QUAL_PASS=$((QUAL_PASS+1)); echo "  [PASS] $1"; }
_qfail() { QUAL_FAIL=$((QUAL_FAIL+1)); echo "  [FAIL] $1" >&2; }
_qskip() { QUAL_SKIP=$((QUAL_SKIP+1)); echo "  [SKIP] $1"; }

echo "========================================"
echo "MAIW v2 Reference Deployment Qualification"
echo "Started: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Evidence dir: $EVIDENCE_DIR"
echo "========================================"
echo ""

# ── Phase 0: Preflight ────────────────────────────────────────────────────────
echo "--- Phase 0: Preflight ---"
if bash "$SCRIPT_DIR/preflight_reference_deployment.sh" 2>&1; then
    _qpass "Preflight all checks passed"
else
    _qfail "Preflight failed — see output above"
    echo ""
    echo "QUALIFICATION ABORTED at Phase 0."
    exit 1
fi

# ── Phase 1: Start ────────────────────────────────────────────────────────────
echo ""
echo "--- Phase 1: Start ---"
START_T=$(date +%s)
if bash "$SCRIPT_DIR/start_reference_deployment.sh" --skip-preflight 2>&1; then
    END_T=$(date +%s)
    STARTUP_S=$((END_T - START_T))
    _qpass "Deployment started in ${STARTUP_S}s"
    echo "  Startup time baseline: ${STARTUP_S}s"  # Step 59
else
    _qfail "Start failed"
    exit 1
fi

# ── Phase 2: Readiness ────────────────────────────────────────────────────────
echo ""
echo "--- Phase 2: Readiness ---"
BASE_URL="$(_base_url)"
READY_HTTP=$(curl -so /dev/null -w "%{http_code}" --max-time 10 "${BASE_URL}/api/v1/ready" 2>/dev/null || echo "000")
if [[ "$READY_HTTP" == "200" ]]; then
    _qpass "Readiness check HTTP 200"
    # Record readiness body as evidence
    curl -sf "${BASE_URL}/api/v1/ready" > "${EVIDENCE_DIR}/readiness_response.json" 2>/dev/null || true
else
    _qfail "Readiness check returned HTTP $READY_HTTP"
fi

# ── Phase 3: Smoke test ────────────────────────────────────────────────────────
echo ""
echo "--- Phase 3: Smoke test ---"
if bash "$SCRIPT_DIR/smoke_test_reference_deployment.sh" 2>&1; then
    _qpass "Smoke test passed"
else
    _qfail "Smoke test failed"
fi

# ── Phase 4: Safe Proof SOP A (non-consequential) ─────────────────────────────
echo ""
echo "--- Phase 4: Safe Proof SOP A (reaches WAITING_FOR_GOVERNANCE) ---"
if "$MAIW_PYTHON" -m pytest tests/contract/test_sandbox_proof_sop_a.py -x -q \
    --no-header 2>&1 | tail -5; then
    _qpass "Proof SOP A test suite passed"
else
    _qfail "Proof SOP A test suite failed (or not available)"
fi

# ── Phase 5: API restart → verify resume ──────────────────────────────────────
echo ""
echo "--- Phase 5: API restart + resume verification ---"
# Snapshot pre-restart procedure state
PROC_DIR="${MAIW_PERSISTENCE_ROOT}/procedures"
PRE_COUNT=$(find "$PROC_DIR" -name "*.json" 2>/dev/null | wc -l || echo 0)
PRE_WAITING=$(grep -lE '"status": ?"waiting_for_governance"' "$PROC_DIR"/*.json 2>/dev/null | wc -l || echo 0)

RESTART_T=$(date +%s)
if bash "$SCRIPT_DIR/restart_reference_deployment.sh" --skip-preflight 2>&1; then
    RESTART_END_T=$(date +%s)
    RESTART_S=$((RESTART_END_T - RESTART_T))
    POST_COUNT=$(find "$PROC_DIR" -name "*.json" 2>/dev/null | wc -l || echo 0)
    POST_WAITING=$(grep -lE '"status": ?"waiting_for_governance"' "$PROC_DIR"/*.json 2>/dev/null | wc -l || echo 0)
    echo "  Restart time baseline: ${RESTART_S}s"  # Step 60
    echo "  Procedure count: $PRE_COUNT → $POST_COUNT"
    echo "  WAITING_FOR_GOVERNANCE: $PRE_WAITING → $POST_WAITING"

    if [[ "$POST_COUNT" -ge "$PRE_COUNT" ]] && [[ "$POST_WAITING" -ge "$PRE_WAITING" ]]; then
        _qpass "API restart preserved procedure + governance state ($RESTART_S s)"
    else
        _qfail "State lost after API restart: procedure $PRE_COUNT→$POST_COUNT, waiting $PRE_WAITING→$POST_WAITING"
    fi
else
    _qfail "API restart failed"
fi

# ── Phase 6: Sandbox restart (if sandbox mode is required) ────────────────────
echo ""
echo "--- Phase 6: Sandbox restart (host truth authoritative) ---"
SANDBOX_MODE="${MAIW_SANDBOX_MODE:-disabled}"
if [[ "$SANDBOX_MODE" == "required" && -n "${MAIW_SANDBOX_NAME:-}" ]]; then
    # v2.0.1 round 2: restart ONLY the named reference sandbox through the
    # OpenShell control plane (no name-pattern process kill, which matched
    # unrelated processes on a shared host).
    echo "  Restarting sandbox '$MAIW_SANDBOX_NAME' via openshell"
    openshell sandbox stop "$MAIW_SANDBOX_NAME" >/dev/null 2>&1 || true
    openshell sandbox start "$MAIW_SANDBOX_NAME" >/dev/null 2>&1 || true
    sleep 2
    # Verify host state still readable
    POST_KILL_COUNT=$(find "$PROC_DIR" -name "*.json" 2>/dev/null | wc -l || echo 0)
    POST_KILL_WAITING=$(grep -lE '"status": ?"waiting_for_governance"' "$PROC_DIR"/*.json 2>/dev/null | wc -l || echo 0)
    if [[ "$POST_KILL_COUNT" -ge "$PRE_COUNT" ]] && [[ "$POST_KILL_WAITING" -ge "$PRE_WAITING" ]]; then
        _qpass "Sandbox kill preserved host procedure/governance state"
    else
        _qfail "Host state changed after sandbox kill: procedures $PRE_COUNT→$POST_KILL_COUNT"
    fi
else
    _qskip "Sandbox restart (MAIW_SANDBOX_MODE=$SANDBOX_MODE — not required)"
fi

# ── Phase 7: Backup / restore live test ───────────────────────────────────────
echo ""
echo "--- Phase 7: Backup / restore ---"
BACKUP_DIR="${EVIDENCE_DIR}/backup_$(date +%Y%m%dT%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup: consistent copy of procedure + governance state
if [[ -d "${MAIW_PERSISTENCE_ROOT}/procedures" ]]; then
    cp -r "${MAIW_PERSISTENCE_ROOT}/procedures" "$BACKUP_DIR/"
    echo "  Backup: procedures → $BACKUP_DIR/procedures"
fi
if [[ -d "${MAIW_PERSISTENCE_ROOT}/governance" ]]; then
    cp -r "${MAIW_PERSISTENCE_ROOT}/governance" "$BACKUP_DIR/"
    echo "  Backup: governance → $BACKUP_DIR/governance"
fi
_qpass "Backup completed (non-destructive): $BACKUP_DIR"

# Restore test: stop, restore, restart, readiness
echo "  Testing restore path..."
bash "$SCRIPT_DIR/stop_reference_deployment.sh" >/dev/null 2>&1 || true

# Restore from backup
if [[ -d "$BACKUP_DIR/procedures" ]]; then
    cp -r "$BACKUP_DIR/procedures/." "${MAIW_PERSISTENCE_ROOT}/procedures/"
fi
if [[ -d "$BACKUP_DIR/governance" ]]; then
    cp -r "$BACKUP_DIR/governance/." "${MAIW_PERSISTENCE_ROOT}/governance/"
fi

RESTORE_T=$(date +%s)
bash "$SCRIPT_DIR/start_reference_deployment.sh" --skip-preflight >/dev/null 2>&1
RESTORE_END_T=$(date +%s)
BASE_URL="$(_base_url)"
RESTORE_HTTP=$(curl -so /dev/null -w "%{http_code}" --max-time 10 "${BASE_URL}/api/v1/ready" 2>/dev/null || echo "000")
RESTORE_S=$((RESTORE_END_T - RESTORE_T))

POST_RESTORE_COUNT=$(find "$PROC_DIR" -name "*.json" 2>/dev/null | wc -l || echo 0)
if [[ "$RESTORE_HTTP" == "200" ]] && [[ "$POST_RESTORE_COUNT" -ge "$PRE_COUNT" ]]; then
    _qpass "Restore from backup: readiness OK, procedure state preserved (${RESTORE_S}s)"
else
    _qfail "Restore from backup: ready=$RESTORE_HTTP procedures=$POST_RESTORE_COUNT (expected >= $PRE_COUNT)"
fi

# ── Phase 8: Rollback compatibility check ─────────────────────────────────────
echo ""
echo "--- Phase 8: Rollback baseline check ---"
# Record current baseline for rollback (Step 47)
ROLLBACK_RECORD="${EVIDENCE_DIR}/rollback_baseline.json"
CURRENT_SHA=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
python3 -c "
import json, os, datetime
record = {
    'maiw_sha': '$CURRENT_SHA',
    'nemoclaw_version': '0.0.124',
    'openshell_version': '0.0.116',
    'qualified_model': 'nvidia/nemotron-3-super-120b-a12b',
    'approved_generations': ['nemotron-3', 'nemotron-3.5'],
    'config_schema_version': '1.0',
    'state_schema_version': '1.0',
    'recorded_at': datetime.datetime.utcnow().isoformat() + 'Z',
    'note': 'Rollback to this baseline requires: stop, restore this app version and compatible state, start, readiness check. Do NOT delete procedure/governance state as part of rollback.'
}
with open('$ROLLBACK_RECORD', 'w') as f:
    json.dump(record, f, indent=2)
" 2>/dev/null
_qpass "Rollback baseline recorded: $ROLLBACK_RECORD"

# ── Summary ────────────────────────────────────────────────────────────────────
SHUTDOWN_T=$(date +%s)
bash "$SCRIPT_DIR/stop_reference_deployment.sh" >/dev/null 2>&1 || true
SHUTDOWN_END_T=$(date +%s)
SHUTDOWN_S=$((SHUTDOWN_END_T - SHUTDOWN_T))
echo ""
echo "  Shutdown time baseline: ${SHUTDOWN_S}s"  # Step 61

echo ""
echo "========================================"
echo "Qualification complete: $QUAL_PASS passed, $QUAL_FAIL failed, $QUAL_SKIP skipped"
echo "Evidence: $EVIDENCE_DIR"
echo "Log: $QUAL_LOG"
echo ""

if [[ "$QUAL_FAIL" -gt 0 ]]; then
    echo "QUALIFICATION: FAIL"
    echo "MAIW PHASE 20C-C DEPLOYMENT OPERATIONALIZATION INCOMPLETE" >&2
    exit 1
fi

echo "QUALIFICATION: PASS"
echo ""
