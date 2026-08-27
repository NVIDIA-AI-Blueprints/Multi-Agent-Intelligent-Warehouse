# MAIW Demo Acceptance Checklist

Use this checklist to verify that a MAIW demo deployment is ready for an
audience — internal review, customer demo, or recorded walkthrough.

Mark each item **[PASS]**, **[FAIL]**, or **[N/A]** with a note.

---

## Environment

| # | Check | Status | Notes |
|---|-------|--------|-------|
| E1 | `./scripts/check_demo_environment.sh` exits 0 (all `[OK]`) | | |
| E2 | `NVIDIA_API_KEY` is a live `nvapi-...` key (not placeholder) | | |
| E3 | API starts on port 8001 without errors | | |
| E4 | Frontend starts on port 3001 without errors | | |
| E5 | `GET http://localhost:8001/api/v1/health` returns `{"status": "ok"}` | | |
| E6 | `GET http://localhost:8001/api/v1/demo/scenarios` returns ≥ 5 scenarios | | |

---

## Core Scenario (labor_constraint_wave_risk)

| # | Check | Status | Notes |
|---|-------|--------|-------|
| S1 | Scenario starts and status changes to RUNNING | | |
| S2 | Activity feed populates within 10 seconds | | |
| S3 | Analysis completes and produces a visible ActionProposal | | |
| S4 | Decision shows APPROVED (or REJECTED with reason) | | |
| S5 | Approve button is clickable and registers approval | | |
| S6 | Execute completes with outcome EXECUTED (or NO_OP) | | |
| S7 | execution_id is visible in the activity feed | | |
| S8 | KPI panels update after execution (labor utilization / wave risk) | | |
| S9 | Safety Scorecard shows `unauthorized_writes: 0` and `duplicate_writes: 0` | | |
| S10 | Scenario can be stopped and restarted cleanly (STOP → START) | | |

---

## UI Truth Sources

| # | Check | Status | Notes |
|---|-------|--------|-------|
| U1 | Domain Health panel values come from `GET /api/v1/runtime/status` (not hardcoded) | | |
| U2 | Safety Scorecard shows "VALIDATED BATCH 6" label when no live SSE events (baseline mode) | | |
| U3 | Safety Scorecard shows "LIVE CURRENT RUN" label when SSE events are present | | |
| U4 | ExecutionOutcomeBadge shows correct label for each outcome state (EXECUTED / NO_OP / UNKNOWN / FAILED / CONFLICT / DEFERRED) | | |
| U5 | Circuit trip detail appears only when a domain is not CLOSED | | |
| U6 | Activity feed categories (FAULT, SAFETY, CIRCUIT, RECOVERY) display with correct colors | | |

---

## Reliability Demo (if fault injection is enabled)

| # | Check | Status | Notes |
|---|-------|--------|-------|
| R1 | Fault Injection panel is visible (requires `REACT_APP_FAULT_INJECTION_ENABLED=true` AND demo mode) | | |
| R2 | F06 (Ambiguous Write): outcome is UNKNOWN, not FAILED | | |
| R3 | F06: Reconciliation resolves to CONFIRMED_EXECUTED | | |
| R4 | F06: `duplicate_writes: 0` remains zero after reconcile | | |
| R5 | F10 (State Drift): executor returns CONFLICT, `stale_decisions_blocked` increments | | |
| R6 | F12 (Circuit Open): `labor: CIRCUIT OPEN` shown, equipment and wave remain HEALTHY | | |
| R7 | Safety Scorecard shows no violations after any fault injection | | |

---

## Developer Experience

| # | Check | Status | Notes |
|---|-------|--------|-------|
| D1 | `./scripts/check_demo_environment.sh` produces a readable, actionable output | | |
| D2 | `./scripts/install_packages.sh` completes without errors on a fresh venv | | |
| D3 | `./scripts/testing/run_core_ci.sh` passes (528+ tests, 0 failures) | | |
| D4 | `./scripts/testing/run_reliability.sh` passes (388 tests, 0 failures) | | |
| D5 | `cd src/ui/web && npm test -- --watchAll=false` passes (94 tests, 0 failures) | | |
| D6 | `docs/developer/GETTING_STARTED.md` matches current package structure | | |
| D7 | `docs/demo/DEMO_RUNBOOK.md` steps produce the described output | | |

---

## Definition of Done

All items in **Environment** and **Core Scenario** must be **[PASS]**.

Reliability Demo items are required only if `REACT_APP_FAULT_INJECTION_ENABLED=true`
is set for the demo.

Developer Experience items are required before any recording or publication.

---

**Checklist completed by:** _______________  
**Date:** _______________  
**Branch / commit:** _______________
