# MAIW Operational Safety Scorecard — Phase 10E Batch 6

**Generated:** 2026-08-27  
**Scenario:** `scenario_001_labor_constraint_wave_risk` (seed=42, frozen)  
**Branch:** `feat/phase-10e-operational-hardening`  

## Objective

Prove, through deterministic fault injection, that MAIW preserves operational safety when models, MCP servers, providers, approvals, and execution paths fail.

## Fault Matrix Results

| Fault ID | Name | Safety Pass | Key Behaviour |
|---|---|---|---|
| F00 | Normal (no fault) | ✓ | Recovery at ~300s; backlog −92%; wave-risk −86.7% |
| **F01** | NIM timeout | ✓ | `ModelTimeout` raised; no proposal or execution |
| **F02** | NIM unavailable | ✓ | `ModelUnavailable` raised; no proposal or execution |
| **F03** | MCP read timeout | ✓ | `MCPTimeout` propagates; state assembly fails cleanly |
| **F04** | MCP domain unavailable | ✓ | Labor unavailable; equipment/inventory circuits CLOSED |
| **F05** | MCP write failure before mutation | ✓ | `FAILED` outcome; `physical_mutation_occurred=False` |
| **F06** | **AMBIGUOUS WRITE (hero fault)** | ✓ | `UNKNOWN` outcome; no retry; reconciliation → `CONFIRMED_EXECUTED` |
| **F07** | Duplicate approval | ✓ | 3 APPROVE attempts → 1 grant; 2 blocked by `CONSUMED` |
| **F08** | Duplicate execution | ✓ | Same idempotency_key → 1 mutation; second call returns `NO_OP` |
| **F09** | Stale decision | ✓ | `ActionExpired` blocks before write; `stale_state_blocks=1` |
| **F10** | State drift | ✓ | `ActionConflict` blocks before write; `state_drift_blocks=1` |
| **F11** | Approval expiry | ✓ | `is_expired()=True` → `REJECTED`; no execution |
| **F12** | Circuit open | ✓ | Labor `CIRCUIT OPEN`; equipment/inventory `HEALTHY`; runtime `DEGRADED` |
| **F13** | Reconciliation read timeout | ✓ | `read_current_state` times out → `INDETERMINATE`; `UNKNOWN` preserved |

**All 13 fault profiles: PASS**

## Golden Invariants

| Invariant | Rule | Result |
|---|---|---|
| A | `unauthorized_writes == 0` | ✓ 0 violations |
| B | `duplicate_writes == 0` | ✓ 0 violations |
| C | `false_successes == 0` | ✓ 0 violations |
| D | Stale decisions blocked, not executed | ✓ 1 correctly blocked |
| E | State-drifted executions blocked, not executed | ✓ 1 correctly blocked |

## F06 Hero Fault Trace

```
operator approves
  → executor.execute() called
  → guard 1–5 pass
  → execution_id generated
  → registry.begin() records intent
  → _do_execute() sends MCP write
  → provider commits mutation
  → network ACK lost
  → AmbiguousWriteError raised
  → outcome = UNKNOWN (not FAILED, not EXECUTED)
  → registry.mark_unknown(execution_id)
  → NO automatic retry
  → ReconciliationService.reconcile() called
  → strategy.read_current_state() reads authoritative state
  → check_postcondition() confirms mutation present
  → ReconciliationRecord.outcome = CONFIRMED_EXECUTED
  → ExecutionRecord.outcome remains UNKNOWN (immutable history)
  → ExecutionRecord.effective_status = "effectively_executed"
```

## Test Coverage

| Suite | Tests |
|---|---|
| `test_scenario_001_faults.py` (F01–F13) | 18 |
| `test_scenario_001_baseline.py` | 12 |
| `test_circuit_breaker.py` | 18 |
| `test_graceful_degradation.py` | 16 |
| All other reliability | 324 |
| **Total reliability tests** | **388** |

## Fault Injection Boundary

All faults injected exclusively at the test/demo boundary:
- `StubNIMProvider(raises=...)` — NIM faults (F01, F02)
- `MinimalTestExecutor(do_execute_fn=...)` — write path faults (F05, F06)
- `MinimalTestExecutor(check_guards_fn=...)` — guard faults (F10)
- `DomainCircuitRegistry` with tripped circuit — circuit faults (F04, F12)
- `ApprovalRecord(expires_at=past)` / `CONSUMED` state — approval faults (F07, F11)
- Simulated `evaluated_at` override — staleness fault (F09)
- Same `idempotency_key` resubmission — idempotency fault (F08)
- `TimeoutStrategy.read_current_state()` raises `MCPTimeout` — reconciliation fault (F13)

**Production packages (`Agent`, `ModelGateway`, `DecisionEngine`, `BaseActionExecutor`) contain zero fault injection code.**
