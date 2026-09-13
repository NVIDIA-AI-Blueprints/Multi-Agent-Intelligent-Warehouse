# Phase 18E — Nano Qualification Report

**Phase objective:** Finalize benchmark methodology and obtain a defensible Nano-vs-Super qualification result.

**Run date:** 2026-09-13
**Branch:** feat/phase-18-model-gateway-eval-worktree

---

## Methodology Corrections

### Fix 1: Prompt Isolation (BLOCKING — §2)

**Problem identified:** `runner._build_fixture_messages()` leaked evaluator-only fields into the model prompt:

```python
# BEFORE (leaky):
system = (
    "...OPERATIONAL CONTEXT (fixture: {case.case_id}):\n"
    "...\n"
    f"Evaluation case metadata: {case.metadata}"  # leaked metadata dict
)
```

The metadata dict included: `fixture`, `phase`, `scenario`, `policy_eligibility_nano`, `benchmark_case`, `description`. These are evaluator-only fields that must never reach the model.

**Fix applied:**

```python
# AFTER (isolated):
system = (
    "You are MAIW Copilot, an AI assistant for warehouse operations.\n"
    "Answer questions using ONLY the operational context provided below.\n"
    "Do not fabricate entity IDs, names, or facts not present in the context.\n\n"
    "OPERATIONAL CONTEXT:\n"
    f"In-scope entity IDs:\n{entity_list}"
)
```

Only the entity list (operational context) and user prompt are sent to the model.

**Tests:** 14 tests in `TestPromptIsolation` covering all 6 corpus cases. All passing.

---

### Fix 2: Response Completeness (BLOCKING — §4)

**Problem identified:** `BenchmarkModelResult` had `response_snippet: str | None = None  # first 300 chars only`. While graders already received the full response via `grader_input.response`, the field naming was ambiguous and did not enforce the invariant.

**Fix applied:** Added explicit fields:
- `raw_response`: full bounded model output — graders MUST use this
- `display_preview`: optional ≤300-char truncation for CLI/logs only

`response_snippet` retained as deprecated property → `display_preview` for backward compatibility.

Runner now explicitly sets:
```python
raw_response=_raw,           # full output — graders used this
display_preview=(_raw[:300] if _raw else None),  # display only
```

**Tests:** 7 tests in `TestResponseCompleteness` including regression proving facts after char 300 are detected by graders. All passing.

---

## Prompt Isolation Proof

The following fields are **never present** in the outbound model payload for any evaluation case:

| Evaluator-Only Field | Status |
|---|---|
| `case_id` as fixture label | ABSENT from prompt |
| `case.metadata` dict | ABSENT from prompt |
| `policy_eligibility` / `POLICY ELIGIBLE` | ABSENT from prompt |
| `RESEARCH ONLY` label | ABSENT from prompt |
| `expected_capability` value | ABSENT from prompt |
| `required_facts` field label | ABSENT from prompt |
| `forbidden_claims` field label | ABSENT from prompt |
| `benchmark_case` key | ABSENT from prompt |
| `Evaluation case metadata` verbatim | ABSENT from prompt |

Proof: 14 deterministic offline tests in `tests/unit/test_model_gateway_18e.py::TestPromptIsolation`.

---

## Response Completeness Proof

The graders in all phases (18B–18E) call `_response_text(result)` which returns `result.response or ""`. The `grader_input.response` field is always set to the **full** `eval_result.response_content` — never the 300-char preview.

The 300-char truncation in `response_snippet` / `display_preview` was a display-only convenience that never affected grading. The field rename to `raw_response` + `display_preview` makes this contract explicit and enforced by tests.

Regression proof: `TestResponseCompleteness.test_graders_use_full_response_not_preview` — constructs a response where required_fact only appears after char 300, verifies grader passes.

---

## Models / Deployments

| Role | Model ID | Enabled | Status | Phase 18E Outcome |
|------|----------|---------|--------|-------------------|
| super | `nvidia/nemotron-3-super-120b-a12b` | YES | DEPLOYED | Active — live run deferred to 18F |
| lightning | `nvidia/nemotron-3.5-lightning-30b-a3b` | YES | DEPLOYED | Active — warm-up follow-up deferred to 18F |
| **nano** | `nvidia/nemotron-3-nano-30b-a3b` | **NO** | DEPLOYED | **EOL 2026-09-01 — UNAVAILABLE** |
| ultra | `nvidia/nemotron-3-ultra-550b-a55b` | NO | DEPLOYED | Not in scope |
| nano-omni | _(unconfigured)_ | NO | NOT_DEPLOYED | Not in scope |

---

## Nano Endpoint Status

**Finding:** Nano model `nvidia/nemotron-3-nano-30b-a3b` reached EOL on **2026-09-01T09:00:00Z** — 12 days before this phase ran (2026-09-13).

| Dimension | Status |
|---|---|
| Registry status | `DEPLOYED` (endpoint may persist post-EOL) |
| `NEMOTRON_NANO_ENABLED` env | `false` |
| `.env` comment | "nvidia/nemotron-3-nano-30b-a3b reached EOL 2026-09-01T09:00:00Z — disabled." |
| Endpoint probe attempted | NO — enabling an EOL model requires operator decision |
| Structured-output behavior verified | CANNOT VERIFY — endpoint unavailable |
| Authentication verified | NOT APPLICABLE |

**Per spec §6:** Nano endpoint is unavailable. No Nano qualification data collected.

**Per spec §6:** Verdict: `NANO ENDPOINT UNAVAILABLE`. Methodology work completed. No conclusion manufactured.

---

## Corpus

Six cases covering the 18E qualification corpus (spec §7). All POLICY ELIGIBLE (low/medium risk, medium reasoning):

| Label | Case ID | Family | Risk | Reasoning | Policy |
|---|---|---|---|---|---|
| A | `wave17-risk-low-v1` | ASK | low | medium | POLICY ELIGIBLE |
| B | `evidence-ask-labor-v1` | ASK | low | medium | POLICY ELIGIBLE |
| C | `equipment-ask-low-v1` | ASK | low | medium | POLICY ELIGIBLE |
| D | `healthy-baseline-ask-v1` | ASK | low | medium | POLICY ELIGIBLE |
| E | `analyze-action-v1` | ANALYZE | medium | medium | POLICY ELIGIBLE |
| F | `comparative-reasoning-v1` | ANALYZE | low | medium | POLICY ELIGIBLE |

**Note:** 18B high-risk cases (`wave17-labor-risk-v1`, `equipment-failure-v1`) are labeled `RESEARCH ONLY — NOT PRODUCTION ELIGIBLE` and excluded from qualification corpus.

Fixed-context invariant: all 6 cases use the same `FIXTURE_CONTEXT_ENTITIES` (14 entities). Verified by `TestNanoQualificationCorpus.test_18e_cases_use_fixture_context_entities`.

---

## Policy Eligibility

Policy eligibility for Nano (when enabled) requires: `risk_level ∈ {low, medium}` AND `reasoning_level ∈ {low, medium}`. All 6 qualification corpus cases satisfy this. The 2 high-risk 18B cases do not.

Primary Nano qualification conclusion would be based on POLICY ELIGIBLE cases only. Since Nano is unavailable, no conclusion is possible.

---

## Nano Results

**NOT RUN — NANO ENDPOINT UNAVAILABLE (EOL 2026-09-01)**

| Case | Nano Accept | Nano N | Nano Median ms | Critical Fails | Classification |
|---|---|---|---|---|---|
| A (wave17-risk-low) | N/A | 0 | N/A | N/A | INCONCLUSIVE |
| B (evidence-ask-labor) | N/A | 0 | N/A | N/A | INCONCLUSIVE |
| C (equipment-ask-low) | N/A | 0 | N/A | N/A | INCONCLUSIVE |
| D (healthy-baseline-ask) | N/A | 0 | N/A | N/A | INCONCLUSIVE |
| E (analyze-action) | N/A | 0 | N/A | N/A | INCONCLUSIVE |
| F (comparative-reasoning) | N/A | 0 | N/A | N/A | INCONCLUSIVE |

---

## Super Results

**NOT RUN — DEFERRED (no comparative value without Nano)**

Super-only benchmark has no comparative qualification value without Nano data. Methodology verified offline. Live Super runs deferred to 18F Evaluation Lab.

---

## Direct Comparison

No comparison possible. Nano ENDPOINT UNAVAILABLE. All 6 cases: INCONCLUSIVE.

---

## Lightning Follow-Up

**Status: LIGHTNING STILL INCONCLUSIVE**

18D finding: `LIGHTNING LATENCY PARTIALLY EXPLAINED` — warm-up bias was the leading hypothesis for Lightning's elevated initial latency. Improved warm-up methodology (1 warm-up call + N=5 measured reps with alternating order) is now implemented and tested.

However, live Lightning warm-up follow-up calls were not made in 18E. Rationale:
- 18E primary purpose was methodology finalization, not live benchmark execution.
- Without Nano data, a Lightning-only latency test has limited actionable value for qualification.
- All machinery for proper Lightning warm-up retesting is in place (see `qualification.py::NanoQualificationConfig.alternating_order`, `warmup_reps`, warm-up exclusion tests).
- Live Lightning warm-up follow-up is planned for 18F Evaluation Lab.

**Verdict:** `LIGHTNING STILL INCONCLUSIVE` — warm-up hypothesis unconfirmed, methodology ready.

---

## Router Implications

**Status: INSUFFICIENT EVIDENCE**

Without Nano qualification data, no router calibration opportunity can be identified:
- If Nano had qualified on Cases A–F with material latency advantage: `CURRENT ROUTER HAS DETERMINISTIC POLICY OPTIMIZATION OPPORTUNITY`
- Since Nano is unavailable: no empirical basis for any router assessment

**Current router behavior:** Nano is excluded (operator-disabled). Router correctly selects Super for all requests. This is the correct production behavior given Nano's EOL status.

**Verdict:** `INSUFFICIENT EVIDENCE`

---

## Limitations

1. **Nano EOL:** The primary deliverable of 18E (Nano qualification) is blocked by Nano reaching EOL. This is not a methodology failure — the methodology is sound and all invariants are now tested.

2. **No live Super baseline in 18E:** Super runs were deferred since they have no qualification value without Nano for comparison.

3. **Lightning warm-up hypothesis:** The hypothesis from 18D remains unconfirmed due to no live calls in 18E. The improved methodology is ready.

4. **Offline tests only:** All 53 new tests are deterministic and offline. No live endpoint verification.

5. **Context is fixture-based:** The 14-entity fixture context is a simplified proxy for real OperationalContextSnapshot data. Production evaluation should use live WS2 snapshots.

---

## Final Verdicts

**Nano:** `NANO ENDPOINT UNAVAILABLE`

**Lightning:** `LIGHTNING STILL INCONCLUSIVE`

**Router:** `INSUFFICIENT EVIDENCE`

---

## Tests

| Suite | Tests | Status |
|---|---|---|
| test_model_gateway_18b.py | 92 | All passing |
| test_model_gateway_18c.py | 72 | All passing |
| test_model_gateway_18d.py | 119 | All passing |
| test_model_gateway_18e.py | 53 | All passing |
| test_reasoning_evaluation.py | — | All passing |
| **Total (18x suites)** | **336** | **All passing** |
| test_mcp_integrated_planner_graph.py | 10 failures | PRE-EXISTING (confirmed) |

---

## Artifacts

| Artifact | Status |
|---|---|
| `artifacts/phase18/18e/benchmark.json` | Created — methodology verification record |
| `artifacts/phase18/18e/nano_super_samples.jsonl` | Created — empty (no live calls) with explanatory note |
| `artifacts/phase18/18e/methodology_validation.json` | Created — all 10 invariants PASS |
| `artifacts/phase18/18e/NANO_QUALIFICATION_REPORT.md` | This document |

Prior artifacts preserved:
- `artifacts/phase18/18d/` — unchanged
- `artifacts/phase18/baseline.json` — unchanged
- `artifacts/phase18/BASELINE_ROUTER_REPORT.md` — unchanged

---

## Phase 18F Recommendation

Per spec preview: Since Nano is unavailable/inconclusive → **18F = Evaluation Lab UI** while preserving current router and documenting unresolved Nano status.

Specifically:
- Build ModelGateway Evaluation Lab UI
- Wire up the qualification runner (`qualification.py`) to the UI
- Implement live Super + Lightning warm-up benchmark runs in the Lab
- Document Nano as EOL with open status pending operator decision on replacement model
- Do NOT change production routing policy (current router is correct: Nano excluded)
- Do NOT implement adaptive routing
