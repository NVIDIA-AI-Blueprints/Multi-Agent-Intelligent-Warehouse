# Evaluation

MAIW supports two types of evaluation: **counterfactual simulation** and
**reliability fault testing**. Neither requires a production database or
live NIM endpoint.

---

## Counterfactual Evaluation

Counterfactual evaluation runs the same scenario twice — once with MAIW
active, once without (control) — and compares KPIs.

### Run it

Start the demo API first:

```bash
./scripts/start_demo_mode.sh &
```

Then run the evaluation script:

```bash
python scripts/counterfactual_eval.py
```

This produces two files:

| File | Description |
|------|-------------|
| `artifacts/demo/labor_wave_control_vs_maiw.json` | Per-tick KPI data for both runs |
| `artifacts/demo/labor_wave_control_vs_maiw.md` | Human-readable comparison table |

### Interpreting results

The markdown report shows:
- **Recovery time** — ticks until wave backlog drops below 10%
- **Backlog reduction** — percentage of pending tasks cleared
- **Wave risk reduction** — OTIF risk score change
- **Constraint** — resource constraint that MAIW resolved

A result is meaningful only when:
- `rng_seed` is identical between runs (same initial state)
- The same `timed_events` fire in both runs (same disruption timeline)
- The CONTROL run received no `POST /demo/analyze` calls

The script enforces all three. Do not modify the seed in the scenario YAML
before re-running unless you want to measure a different disruption.

### Canonical baseline (Scenario 001 — labor_constraint_wave_risk)

| Metric | CONTROL | MAIW | Delta |
|--------|---------|------|-------|
| Recovery | Not reached (>1800s) | 300s | −1500s |
| Backlog reduction | — | 92% | — |
| Wave risk reduction | — | 86.7% | — |

**Any deviation from these numbers requires investigation before accepting
new evaluation results.** The baseline is frozen in
`tests/unit/reliability/test_scenario_001_baseline.py`.

---

## Reliability Fault Testing

The Phase 10E reliability suite verifies that all five golden invariants hold
under 13 fault profiles.

```bash
./scripts/testing/run_reliability.sh
```

Expected output: `388 passed, 0 failed`.

### Golden invariants

| ID | Invariant |
|----|-----------|
| A | `unauthorized_writes == 0` |
| B | `duplicate_writes == 0` |
| C | `false_successes == 0` (`success=true` requires mutation occurred) |
| D | Stale state cannot execute (even with human approval) |
| E | State drift blocks execution (approved against old snapshot ≠ authority against new state) |

### Running a single fault profile

```bash
./scripts/testing/run_reliability.sh -k "F06"   # ambiguous write
./scripts/testing/run_reliability.sh -k "F10"   # state drift
./scripts/testing/run_reliability.sh -v          # all, verbose
```

### Adding a new fault profile

1. Add a `FaultProfile` entry in
   `tests/unit/reliability/fault_framework/__init__.py`
2. Write a test in `tests/unit/reliability/test_scenario_001_faults.py`
   (by analogy with existing F01–F13 tests)
3. Call `check_golden_invariants(result)` at the end of the test
4. Run `./scripts/testing/run_reliability.sh` — all 5 invariants must still pass

---

## CORE CI baseline

```bash
./scripts/testing/run_core_ci.sh
```

Expected output: 528+ passed. The exact count increases with each phase.

---

## Frontend tests

```bash
cd src/ui/web && npm test -- --watchAll=false
```

Expected: 94 passed (Phase 10E baseline).
