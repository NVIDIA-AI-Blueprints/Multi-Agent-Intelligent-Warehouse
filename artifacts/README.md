# artifacts/

Preserved evaluation artifacts, baselines, and validation evidence generated during MAIW development phases. These files are **committed reference data** — not live runtime state, transient output, or configuration.

## What belongs here

- Offline benchmark results (JSON outputs from `maiw_models.eval benchmark`)
- Counterfactual evaluation outputs from `scripts/counterfactual_eval.py` and `scripts/trace_capture.py`
- Frozen performance baselines for regression comparison
- Runtime comparison records used as adoption-decision evidence
- Phase validation reports (Markdown summaries of multi-phase test runs)

## What does NOT belong here

- Transient logs, debug dumps, or temporary outputs
- Secrets, credentials, API keys, or tokens
- Environment dumps that include local paths beyond project root
- Cache files or build artifacts
- PII of any kind

Public endpoints and commit SHAs are acceptable.

## Classification

| Type | Description | Examples |
|------|-------------|---------|
| Benchmark artifact | Output of a fixed evaluation protocol run | `phase18/baseline.json`, `phase18/18f/benchmark.json` |
| Baseline snapshot | Frozen performance/test-count reference for future regression | `baselines/pre_nemoclaw_performance.json` |
| Counterfactual / trace | Simulated scenario comparison or execution trace | `demo/labor_wave_control_vs_maiw.*`, `demo/labor_constraint_wave_risk_trace.*` |
| Reliability artifact | Phase validation from reliability test runs | `reliability/phase10e_validation.md`, `reliability/summary.*` |
| Runtime comparison | Side-by-side comparison of runtime execution paths | `phase19a/runtime_comparison*.json` |

## Directory Map

```
artifacts/
├─ baselines/                      # Frozen performance snapshots
│  └─ pre_nemoclaw_performance.json  # Phase 19B baseline before NemoClaw integration (CURRENT)
├─ demo/                           # Counterfactual evaluation + trace artifacts for the canonical demo
│  ├─ labor_wave_control_vs_maiw.* # Simulated: control vs MAIW-governed world comparison
│  └─ labor_constraint_wave_risk_trace.*  # Execution trace for labor-constraint/wave-risk scenario
├─ phase11/                        # Phase 11 validation report (HISTORICAL)
│  └─ phase11_report.md
├─ phase18/                        # Model Gateway evaluation artifacts (CURRENT — phases 18C–18F)
│  ├─ cases.json                   # Shared evaluation case corpus
│  ├─ baseline.json                # Phase 18C benchmark results
│  ├─ BASELINE_ROUTER_REPORT.md    # Phase 18C Markdown report
│  ├─ 18d/benchmark.json           # Phase 18D benchmark results
│  ├─ 18e/benchmark.json           # Phase 18E benchmark results (fixed methodology)
│  └─ 18f/benchmark.json           # Phase 18F benchmark results (Evaluation Lab baseline)
├─ phase19a/                       # Runtime comparison artifacts from Phase 19A (CURRENT)
│  ├─ runtime_comparison.json      # Initial POC: deterministic vs simulated DeepAgentsRuntime
│  ├─ runtime_comparison_simulated.json  # POC with simulated Deep Agents (pre-integration)
│  └─ runtime_comparison_real_deepagents.json  # Real DeepAgentsRuntime integration (adoption evidence)
└─ reliability/                    # Reliability and phase validation results
   ├─ phase10e_validation.md       # Phase 10E operational hardening validation
   ├─ scenario001_normal.*         # Scenario 001 normal-path reliability run
   └─ summary.*                    # Reliability suite summary
```

## Phase 19A Runtime Comparison Files

Three JSON files record the Phase 19A runtime evaluation:

| File | What it contains |
|------|-----------------|
| `runtime_comparison_simulated.json` | POC run using a *simulated* DeepAgentsRuntime stub (pre-integration, no real LangGraph). Used to validate test harness before real integration. |
| `runtime_comparison.json` | Intermediate comparison using the real `MAIWDeterministicRuntime` against a simulated Deep Agents path (`"DeepAgentsRuntime (POC simulation)"`). |
| `runtime_comparison_real_deepagents.json` | **Adoption-decision artifact.** Uses the real `DeepAgentsRuntime` (deepagents 0.7.15, LangGraph ReAct loop). Records the `adoption_decision`: **"KEEP DEEP AGENTS AS OPTIONAL RUNTIME"** — deterministic runtime remains production default; Deep Agents retained as an optional adaptive runtime. |

The `runtime_comparison_real_deepagents.json` file is the authoritative evidence artifact for the adoption decision. The architecture documents remain normative.

## Phase 18 Benchmark Artifacts

The `phase18/` artifacts are outputs of the fixed 10-step benchmark protocol described in [`docs/developer/MODEL_GATEWAY_EVALUATION.md`](../docs/developer/MODEL_GATEWAY_EVALUATION.md). Each `benchmark.json` captures model quality scores, policy compliance, and grader results for the evaluation corpus at that phase.

To regenerate the Phase 18F benchmark:

```bash
python -m maiw_models.eval benchmark \
  --cases artifacts/phase18/cases.json \
  --output artifacts/phase18/18f/benchmark.json
```

Requires `NVIDIA_API_KEY`. Without it, the CLI validates infrastructure and records `endpoint_status = "NOT RUN — ENDPOINT UNAVAILABLE"`.

## Security Rules

1. No credentials, API keys, tokens, or secrets in any artifact file.
2. No PII (names, emails, user IDs) except as anonymized or synthetic test identifiers.
3. No local filesystem paths outside the project root.
4. No environment dumps (output of `env`, `printenv`, etc.).
5. Public NVIDIA API endpoints and commit SHAs are acceptable.

If an artifact contains any of the above, remove it and regenerate before committing.

## Reproducibility Metadata

Future evaluation artifacts should include the following metadata fields where applicable:

| Field | Description |
|-------|-------------|
| `phase` | MAIW phase identifier (e.g., `"19A"`) |
| `generated` or `created` | ISO-8601 timestamp of artifact generation |
| `commit` or `commit_sha` | Git commit SHA the artifact was generated from |
| `python_version` | Python version used |
| `deepagents_version` | Deep Agents version (if applicable) |
| `dataset_id` / `semantic_checksum` | Fixture corpus version for benchmark runs |
| `deployment_mode` | `"nvidia_hosted"` or `"local"` for benchmark runs |

These fields make it possible to reproduce or diff artifacts across phases without running inference again.
