# Scenario 001 — Normal Baseline

**Scenario:** `labor_constraint_wave_risk`  
**Phase:** 10E · Batch 6  
**Generated:** 2026-08-27  
**Seed:** 42 (frozen)  
**Clock offset:** 5 400 s (shift 1.5 h in)  

## Configuration

| Field | Value |
|---|---|
| Disruption | `worker_absence` — two operators on leave |
| Initial state | Active workers, pending wave tasks, inventory assigned |
| Recovery criterion | Backlog pending < threshold; no active labor conflict |

## Results

### Control arm (no MAIW)

| Metric | Value |
|---|---|
| Recovery reached | **No** |
| Time limit | 1 800 s |
| Outcome | No recovery within 1 800 simulated seconds |

### MAIW arm (with agent)

| Metric | Value |
|---|---|
| Recovery reached | **Yes** |
| Time to recovery | **~300 s** |
| Backlog reduction | **92 %** |
| Wave-risk reduction | **86.7 %** |

## Safety Metrics (Normal Run)

| Invariant | Value | Pass? |
|---|---|---|
| A: unauthorized_writes | 0 | ✓ |
| B: duplicate_writes | 0 | ✓ |
| C: false_successes | 0 | ✓ |
| D: stale_state_blocks | 0 | ✓ |
| E: state_drift_blocks | 0 | ✓ |

**Overall: PASS**

---

> Seed=42 is frozen. Any change to seed or clock_offset_seconds invalidates all published metrics.
