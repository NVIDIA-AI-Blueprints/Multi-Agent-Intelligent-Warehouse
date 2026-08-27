# Phase 10E Operational Hardening — Pre-Merge Validation

**Date:** 2026-08-27  
**Branch:** `feat/phase-10e-operational-hardening`  
**Final commit:** see `git log --oneline -1`

---

## Objective

Prove that MAIW remains safe, traceable, predictable, and recoverable under infrastructure
and distributed-system failures across all seven implementation batches.

---

## Invariant Gate

| # | Invariant | Gate Result |
|---|-----------|-------------|
| A | `unauthorized_writes == 0` — no write without valid APPROVED decision | **PASS** (0 violations across all 13 fault profiles) |
| B | `duplicate_writes == 0` — one physical mutation per idempotency key | **PASS** (0 violations) |
| C | `false_successes == 0` — EXECUTED requires confirmed physical mutation | **PASS** (0 violations) |
| D | Stale decisions blocked, not executed | **PASS** (F09 correctly blocked: `stale_state_blocks=1`) |
| E | State-drifted executions blocked, not executed | **PASS** (F10 correctly blocked: `state_drift_blocks=1`) |
| — | UNKNOWN preserved honestly — never promoted to EXECUTED without reconciliation | **PASS** (F06: UNKNOWN→reconcile→CONFIRMED_EXECUTED; outcome immutable) |
| — | No blind retry on UNKNOWN — `mark_unknown()` is terminal | **PASS** |
| — | Domain outages isolated — labor OPEN does not affect equipment | **PASS** (F04, F12: domain_isolation_verified=true) |
| — | Request deadlines bounded at API boundary, not inside agent/executor | **PASS** |
| — | UI reflects backend truth — live counters vs validated baseline labeled distinctly | **PASS** |

**Overall gate: PASS**

---

## Test Suite Results

### Python reliability tests (`tests/unit/reliability/`)

```
388 passed, 16 warnings in 2.32s
```

| Suite | Tests | Status |
|-------|-------|--------|
| `test_ambiguous_write.py` | (Batch 1) | ✓ |
| `test_capability_semantics.py` | (Batch 1) | ✓ |
| `test_execution_outcome.py` | (Batch 1) | ✓ |
| `test_idempotency.py` | (Batch 1) | ✓ |
| `test_trace.py` | (Batch 1) | ✓ |
| `test_approval_*.py` | (Batch 2) | ✓ |
| `test_reconciliation.py` | (Batch 3) | ✓ |
| `test_checkpoint_d.py` | (Batch 4) | ✓ |
| `test_circuit_breaker.py` | (Batch 5) | ✓ |
| `test_graceful_degradation.py` | (Batch 5) | ✓ |
| `test_scenario_001_baseline.py` | (Batch 6) | ✓ |
| `test_scenario_001_faults.py` | (Batch 6) | ✓ |
| **Total** | **388** | **✓ 0 failures** |

### Frontend tests (`src/ui/web/`)

```
94 passed, 0 failed
10 test suites
```

| Suite | Tests | Status |
|-------|-------|--------|
| `reliability/ExecutionOutcomeBadge.test.tsx` | 8 | ✓ |
| `reliability/SafetyScorecard.test.tsx` | 6 | ✓ |
| `reliability/ReliabilityPanel.test.tsx` | 6 | ✓ |
| `reliability/FaultInjectionPanel.test.tsx` | 7 | ✓ |
| `reliability/f06GuidedFlow.test.tsx` | 8 | ✓ |
| Pre-existing demo/API tests | 59 | ✓ |
| **Total** | **94** | **✓ 0 failures** |

### TypeScript

```
npx tsc --noEmit → 0 errors
```

---

## Batch Summary

| Batch | Objective | Key Deliverable | Status |
|-------|-----------|-----------------|--------|
| 1 | Execution semantics + idempotency | `ExecutionOutcome` (6 values), `ExecutionRegistry`, `AmbiguousWriteError` | ✅ |
| 2 | Approval hardening | `ApprovalState` machine, single-use consume, `CONSUMED` blocks re-auth | ✅ |
| 3 | Reconciliation | `ReconciliationService`, `CONFIRMED_EXECUTED`/`INDETERMINATE`, `effective_status` | ✅ |
| 4 | Request deadlines | Hierarchical `RequestDeadline`, typed failure→HTTP map, lifespan cleanup | ✅ |
| 5 | Circuit breakers + degradation | Per-domain `CircuitBreaker`, `DomainCircuitRegistry`, operational status API | ✅ |
| 6 | Fault injection + safety evidence | 13 fault profiles, all 5 invariants pass, `artifacts/reliability/summary.json` | ✅ |
| 7 | Operator reliability UX | Reliability row in CommandCenter, 5 components, 35 UI tests | ✅ |

---

## Critical Behavioural Properties Confirmed

### UNKNOWN is not FAILED

```python
# BaseActionExecutor._do_execute() on AmbiguousWriteError:
outcome = ExecutionOutcome.UNKNOWN      # not FAILED
physical_mutation_occurred = True       # distinguishable
# Registry marks UNKNOWN → subsequent attempts raise ExecutionAlreadyAttempted
# No automatic retry
```

### No blind retry

```python
# ExecutionRegistry.begin():
if existing := self._get_by_idempotency_key(key):
    if existing.outcome == ExecutionOutcome.UNKNOWN:
        raise ExecutionAlreadyAttempted(...)  # blocks retry
```

### Reconciliation resolves without mutating history

```python
# ReconciliationService.reconcile():
rec_record = ReconciliationRecord(outcome=CONFIRMED_EXECUTED)
# exec_record.outcome is NEVER rewritten — it remains UNKNOWN
# exec_record.effective_status is a @property derived from rec_record
```

### Domain isolation

```python
# GD6 — test_graceful_degradation.py:
# Labor circuit OPEN → MCPUnavailable on labor calls
# Equipment circuit CLOSED → equipment calls succeed normally
# Validated by: test_labor_circuit_open_does_not_affect_equipment()
```

### Approval single-use

```python
# ApprovalStore.authorize_with_approval():
# CONSUMED state is set atomically before returning authority
# Subsequent calls with same approval_id raise ApprovalAlreadyConsumed
```

---

## Scope Boundaries (Not In Phase 10E)

These items were explicitly deferred and must not be inferred from Phase 10E:

- Distributed idempotency (multi-replica exactly-once guarantees)
- Distributed circuit state synchronization across replicas
- Redis/PostgreSQL-backed approval storage
- Automated reconciliation triggers (operator-initiated only)
- Per-capability deadline budgets
- Distributed deadline propagation
- NeMo Agent Toolkit, Switchyard, SAP EWM, Manhattan, Blue Yonder

---

## Evidence Artifacts

```
artifacts/reliability/
├── summary.json                   ← canonical safety scorecard (machine-readable)
├── summary.md                     ← human-readable scorecard
├── scenario001_normal.json        ← Batch 6 baseline: normal run metrics
├── scenario001_normal.md          ← human-readable baseline
└── phase10e_validation.md         ← this document
```

---

> "Intelligence may be probabilistic. Operational authority must remain explicit, governed, and safe."
