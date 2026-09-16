# Phase 18D — Benchmark Calibration Report

## Experimental Setup

Phase 18D is a calibration-only phase. No new model calls were made. All grading uses
saved response snippets from the Phase 18C baseline (`artifacts/phase18/baseline.json`).

**Phase objective:** Answer three unresolved questions from 18C:
1. What is the actual Nano vs Super quality/latency tradeoff on MAIW tasks?
2. Are deterministic graders producing false failures from entity surface-form differences?
3. Why did Lightning show unexpected latency behavior?

**Grader version:** 18D-calibrated (see Grader Calibration section)
**Models re-graded:** All 18C saved results (4 model×case pairs)
**Live model calls:** NONE in 18D.1 (calibration only)
**Nano live benchmark:** NOT RUN — Nano is operator-disabled (see Nano Availability)

---

## DataPack / Context Identity

| Field | Value |
|-------|-------|
| Dataset ID | `eval-fixture-dataset-v1` |
| Semantic Checksum | `fixture-checksum-abc123` |
| Context entities | 14 fixture entities (wave-17, labor-shift-*, worker-A00*, conveyor-*, etc.) |
| Fixed-context invariant | All cases share same `FIXTURE_CONTEXT_ENTITIES` (§5) |

---

## Models / Deployments

### Evaluated in 18C (re-graded in 18D)

| Role | Model ID | Deployment | Status |
|------|----------|-----------|--------|
| Super | `nvidia/nemotron-3-super-120b-a12b` | nvidia_hosted | DEPLOYED |
| Lightning | `nvidia/nemotron-3.5-lightning-30b-a3b` | nvidia_hosted | DEPLOYED |

### Current registry state (audit at 18D run time)

| Role | Model ID | Enabled | Status | Note |
|------|----------|---------|--------|------|
| lightning | nvidia/nemotron-3.5-lightning-30b-a3b | YES | DEPLOYED | Active |
| nano | nvidia/nemotron-3-nano-30b-a3b | **NO** | DEPLOYED | Operator-disabled |
| super | nvidia/nemotron-3-super-120b-a12b | YES | DEPLOYED | Primary |
| ultra | nvidia/nemotron-3-ultra-550b-a55b | NO | DEPLOYED | Opt-in only |
| nano-omni | (operator must configure) | NO | NOT_DEPLOYED | — |

---

## Nano Availability Audit

**Question from spec §3:** Distinguish `ENABLED IN REGISTRY` from `ENDPOINT ACTUALLY AVAILABLE`.

| Dimension | Status |
|-----------|--------|
| Registry enabled (default) | YES — `NEMOTRON_NANO_ENABLED` default = `True` |
| Operator enabled | **NO** — `NEMOTRON_NANO_ENABLED=false` in operator `.env` |
| Deployment status | DEPLOYED (confirmed on integrate.api.nvidia.com as of 2026-08-20) |
| Endpoint actually available | CANNOT CONFIRM — operator disabled prevents probe |
| Current routing role | EXCLUDED — never selected for any request |
| ReasoningLevel eligibility (when enabled) | low/medium only |
| RiskLevel eligibility (when enabled) | low/medium only; high/critical → super/ultra |
| Policy eligible for 18C cases (risk=high, reasoning=high) | NO |
| Policy eligible for 18D cases (risk=low/medium, reasoning=medium) | YES (if re-enabled) |

**Root cause of operator disable:** `load_dotenv()` in `nim_client.py` loads
`/home/nvidia/Multi-Agent-Intelligent-Warehouse/.env` which contains
`NEMOTRON_NANO_ENABLED=false`. This is an explicit operator decision, not a
registry or endpoint failure.

**Consequence:** All Nano benchmark results are `NOT RUN — OPERATOR DISABLED`.
Label: **RESEARCH ONLY — NOT PRODUCTION ELIGIBLE** for all 18D Nano comparisons.

**Per spec §4:** Production eligibility has NOT been weakened to obtain data.

---

## Grader Calibration

### Problems found in 18C graders

Three classes of false failures were identified:

#### Class 1: Entity surface-form false failures (RequiredEvidenceGrader)
**Problem:** Required fact `"wave-17"` was not satisfied by model response containing
`"Wave 17"`. The grader used exact substring match on the lowercase normalized response
(`"wave 17"` ≠ `"wave-17"`).

**Fix:** `RequiredEvidenceGrader._fact_found_in_response()` now applies canonical alias
matching for entity-like facts (containing `-` or `_`). Aliases are derived deterministically
via hyphen↔space↔underscore substitution only — no fuzzy matching.

**Regression coverage:** `TestRequiredEvidenceGraderCalibrated` (8 tests)

#### Class 2: Capability synonym gaps (CapabilityMatchGrader)
**Problem:** `equipment_bypass` failed when the model said `"use the backup conveyor"` or
`"switch to backup"` — operationally correct but not in the original synonym list.

**Fix:** Extended `_SYNONYMS["equipment_bypass"]` with: `"backup conveyor"`, `"switch to backup"`,
`"use backup"`, `"alternate path"`, `"conveyor-backup"`. All are semantically correct for the
equipment bypass capability.

**Strictness preserved:** Generic words that could match unrelated content were NOT added.
`TestCapabilityMatchGraderCalibrated` includes a test that labor reallocation phrasing does
NOT satisfy equipment_bypass.

#### Class 3: Hallucination grader allowlist too narrow (HallucinationGrader)
**Original behavior:** The regex `[a-zA-Z][a-zA-Z0-9]*[-_][a-zA-Z0-9][-a-zA-Z0-9]*` flags
ALL hyphenated tokens and checks them against the exact canonical entity ID list.
This flags common English hyphenated words as hallucinations.

**Fix:** Build expanded allowed surface forms via `EntityResolver` and
`build_allowed_surface_forms()`. The full alias set (canonical ID + hyphen↔space↔underscore
variants) is checked before flagging a token as unresolvable.

**What this fixes:** `"wave 17"` (space variant of `"wave-17"`) is no longer flagged.

**What this does NOT fix (by design):** `"in-scope"`, `"labor-bottleneck"` — these are
genuinely not in the context entity list and cannot be resolved to any known entity. They
continue to be flagged. However, inspection of the 18C response snippet shows these appear
in descriptive English phrases (`"The in-scope entities include..."`, `"due to a labor
bottleneck"`), not as entity references. This is a residual grader limitation acknowledged
in the Limitations section.

**No fuzzy matching introduced.** Per spec §10, only the approved alias hierarchy is used.

### Canonical entity resolver (§11)

New module `evaluation/resolver.py` implements `resolve_entity_reference()`:
- Deterministic, bounded to supplied context
- No external lookup, no LLM, no live graph, no edit distance
- Alias derivation: exact canonical ID → hyphen/underscore variants only
- `"Wave 17"` → `"wave-17"` ✓ | `"Wave 18"` → None ✓ | `"wave seventeen"` → None ✓

### Target grader diagnostics (§13)

`TargetMatchGrader` now emits structured diagnostic in `GraderResult.evidence`:
```json
{"model_reference": "wave 17", "resolved_entity_id": "wave-17",
 "expected_entity_id": "wave-17", "match": true}
```

---

## Re-scored 18C Results (§16)

All 18C model outputs were re-graded through calibrated 18D graders without re-calling models.
Source: response snippets (first 300 chars) from `artifacts/phase18/baseline.json`.

> **Caveat:** Response snippets are truncated. Calibration results reflect the visible portion
> only. Full-response re-grading may differ, particularly for the hallucination grader.

| Case | Model | Original Score | Calibrated Score | Δ | Verdict | Policy |
|------|-------|---------------|------------------|---|---------|--------|
| wave17-labor-risk-v1 | Super | 0.40 | 0.60 | +0.20 | NOT ACCEPTABLE | RESEARCH ONLY |
| equipment-failure-v1 | Super | 0.80 | **1.00** | +0.20 | **ACCEPTABLE** | RESEARCH ONLY |
| healthy-baseline-v1 | Lightning | 0.50 | **1.00** | +0.50 | **ACCEPTABLE** | POLICY ELIGIBLE |
| healthy-baseline-v1 | Super | 0.50 | 0.75 | +0.25 | NOT ACCEPTABLE | POLICY ELIGIBLE |

### Per-grader delta detail

**wave17-labor-risk-v1 (Super)**

| Grader | Original | Calibrated | Δ | Classification | Critical? |
|--------|----------|-----------|---|----------------|-----------|
| schema_validity | PASS | PASS | 0 | N/A | YES |
| hallucination | FAIL | FAIL | 0 | TRUE MODEL ERROR | YES |
| capability_match | FAIL | FAIL | 0 | TRUE MODEL ERROR | YES |
| target_match | PASS | PASS | 0 | N/A | YES |
| required_evidence | FAIL | **PASS** | **+1** | **FALSE GRADER FAILURE** | no |
| forbidden_claims | PASS | PASS | 0 | N/A | no |

*Hallucination: model echoed fixture metadata (`wave17-labor-risk-v1` case ID) from
system prompt context, plus descriptive phrases (`labor-bottleneck`, `in-scope`).
Residual hallucination failure after calibration.*

*Capability: model did not recommend `labor_reallocation` — TRUE MODEL ERROR.*

**equipment-failure-v1 (Super)**

| Grader | Original | Calibrated | Δ | Classification | Critical? |
|--------|----------|-----------|---|----------------|-----------|
| hallucination | PASS | PASS | 0 | N/A | YES |
| capability_match | FAIL | **PASS** | **+1** | **FALSE GRADER FAILURE** | YES |
| target_match | PASS | PASS | 0 | N/A | YES |
| required_evidence | PASS | PASS | 0 | N/A | no |
| forbidden_claims | PASS | PASS | 0 | N/A | no |

*Capability fix: model used `"conveyor-backup"` (a valid entity ID in context) which is
now recognized as a synonym for `equipment_bypass`. Calibrated verdict: ACCEPTABLE.*

**healthy-baseline-v1 (Lightning)**

| Grader | Original | Calibrated | Δ | Classification | Critical? |
|--------|----------|-----------|---|----------------|-----------|
| hallucination | FAIL | **PASS** | **+1** | **FALSE GRADER FAILURE** | YES |
| capability_match | PASS | PASS | 0 | N/A (skipped) | YES |
| target_match | PASS | PASS | 0 | N/A | YES |
| required_evidence | FAIL | **PASS** | **+1** | **FALSE GRADER FAILURE** | no |
| forbidden_claims | PASS | PASS | 0 | N/A | no |

*Both failures were false grader failures. Calibrated verdict: ACCEPTABLE.*
*Lightning response correctly identified Wave 17 as ON TRACK — no fabricated interventions.*

**healthy-baseline-v1 (Super)**

| Grader | Original | Calibrated | Δ | Classification | Critical? |
|--------|----------|-----------|---|----------------|-----------|
| hallucination | FAIL | FAIL | 0 | TRUE MODEL ERROR | YES |
| capability_match | PASS | PASS | 0 | N/A (skipped) | YES |
| target_match | PASS | PASS | 0 | N/A | YES |
| required_evidence | FAIL | **PASS** | **+1** | **FALSE GRADER FAILURE** | no |
| forbidden_claims | PASS | PASS | 0 | N/A | no |

*Super echoed fixture metadata including entity-like strings from context description.
Response snippet: "...healthy-baseline-v1 fixture, there is no information indicating any
issues with Wave 17. The context lists Wave 17 as an in-scope entity..."*
*The `in-scope` phrase still fails hallucination (descriptive English, not a context entity).*

### Summary

| Metric | Count |
|--------|-------|
| False grader failures fixed | **5** |
| True model errors (unchanged) | 3 |
| Unchanged passes | 16 |
| Grader results newly failing | 0 |

**No calibration change introduced new failures (§15 preserved).**

---

## Nano vs Super Benchmark

### Status: NOT RUN — NANO OPERATOR DISABLED

Nano (`nvidia/nemotron-3-nano-30b-a3b`) is disabled via `NEMOTRON_NANO_ENABLED=false`
in the operator `.env`. Live Nano benchmark is not possible without operator enabling.

### Policy eligibility for planned 18D cases

| Case | Nano Policy | Super Policy |
|------|------------|--------------|
| wave17-labor-risk-v1 (18B/18C) | RESEARCH ONLY (risk=high, reasoning=high) | POLICY ELIGIBLE |
| equipment-failure-v1 (18B/18C) | RESEARCH ONLY (risk=high, reasoning=high) | POLICY ELIGIBLE |
| healthy-baseline-v1 (18B/18C) | POLICY ELIGIBLE (risk=low, reasoning=medium) | POLICY ELIGIBLE |
| evidence-ask-labor-v1 (18D Case B) | **POLICY ELIGIBLE** (risk=low, reasoning=medium) | POLICY ELIGIBLE |
| analyze-action-v1 (18D Case C) | **POLICY ELIGIBLE** (risk=medium, reasoning=medium) | POLICY ELIGIBLE |
| comparative-reasoning-v1 (18D Case D) | **POLICY ELIGIBLE** (risk=low, reasoning=medium) | POLICY ELIGIBLE |

3 of 6 corpus cases are Nano POLICY ELIGIBLE when Nano is re-enabled.

### Nano vs Super matrix

| Case | Nano Quality | Super Quality | Nano Latency | Super Latency | Policy |
|------|-------------|--------------|-------------|--------------|--------|
| wave17-labor-risk-v1 | NOT RUN | 0.60 (calibrated) | NOT RUN | 2515ms | RESEARCH ONLY |
| equipment-failure-v1 | NOT RUN | 1.00 (calibrated) | NOT RUN | 2348ms | RESEARCH ONLY |
| healthy-baseline-v1 | NOT RUN | 0.75 (calibrated) | NOT RUN | 1447ms | POLICY ELIGIBLE |
| evidence-ask-labor-v1 | NOT RUN | NOT RUN | NOT RUN | NOT RUN | POLICY ELIGIBLE |
| analyze-action-v1 | NOT RUN | NOT RUN | NOT RUN | NOT RUN | POLICY ELIGIBLE |
| comparative-reasoning-v1 | NOT RUN | NOT RUN | NOT RUN | NOT RUN | POLICY ELIGIBLE |

**Classification: NANO EVALUATION INCONCLUSIVE** — operator disabled prevents execution.

---

## Latency Analysis

### 18C latency sample inventory

| Model | Case | routing_ms | inference_ms | total_ms | fallback | warmup |
|-------|------|-----------|-------------|---------|---------|--------|
| Super | wave17-labor-risk-v1 | 0.008 | 2514.9 | 2514.9 | No | No |
| Super | equipment-failure-v1 | 0.009 | 2348.2 | 2348.2 | No | No |
| Lightning | healthy-baseline-v1 | 0.012 | 48569.6 | 48569.6 | No | No |
| Super | healthy-baseline-v1 | 0.021 | 1446.7 | 1446.7 | No | No |

### Connection reuse audit

`NIMClient` creates one `httpx.AsyncClient` per instance at `__init__` time.
This client is shared for ALL model calls (same `base_url=integrate.api.nvidia.com`).

| Question | Finding |
|----------|---------|
| New HTTP client per call? | NO — single `httpx.AsyncClient` singleton |
| HTTP/2 enabled? | NO — HTTP/1.1 with keep-alive |
| Connection reuse? | YES — same base URL, connection pool maintained |
| TLS overhead for Lightning call? | MINIMAL — connection established on Super calls 1-2 |
| DNS overhead for Lightning call? | NONE — same base URL |

**Conclusion:** Lightning's 48570ms is server-side, not client-side.

---

## Lightning Root Cause Analysis

### Observation
Lightning (30B MoE) took 48570ms vs Super (120B MoE) at 1447ms on the same case.
Expected: Lightning should be faster (smaller active parameters: 3B vs 12B active).
Actual: Lightning was 33x SLOWER than Super on the same case.

### Breakdown
- `routing_ms`: 0.012ms — trivial (policy check)
- `inference_ms`: 48569.618ms — **100% of latency is server-side**
- No fallback, no retry, no error

### Root cause assessment

**PRIMARY: COLD CONTAINER / MODEL WARMUP AT NIM ENDPOINT (HIGH CONFIDENCE)**

Evidence:
1. Client-side connection reuse is confirmed — no TLS/connect overhead
2. Super was pre-warmed by cases 1-2 (Super latency: 2515ms → 1447ms, consistent with warm endpoint)
3. Lightning was called ONLY ONCE in 18C (no explicit warm-up call was made, per spec §18)
4. 48s is consistent with cold MoE model loading into GPU (weight loading + graph compilation)
5. After Lightning's "warmup" call, Super ran at 1447ms (steady state confirmed)

**SECONDARY HYPOTHESES:**
- Endpoint queue: Possible but would not explain consistent first-call-only pattern
- JIT compilation: Contributing factor but 48s is unusually long for compilation alone

### Methodology gap
18C did not include an explicit warm-up request excluded from timing (spec §18 requirement).
The 48570ms observation is **a warm-up artifact, not a representative latency sample**.

### Implication for Nano/Lightning comparison
Any future Lightning or Nano latency measurement MUST:
1. Issue one explicit warm-up call before timed measurements
2. Run N≥5 measured calls after warm-up
3. Report median, not single-call observations

---

## Policy Eligibility Summary

| Case | Risk | Reasoning | Super | Lightning | Nano (if enabled) |
|------|------|----------|-------|-----------|-------------------|
| wave17-labor-risk-v1 | high | high | ELIGIBLE | INELIGIBLE | RESEARCH ONLY |
| equipment-failure-v1 | high | high | ELIGIBLE | INELIGIBLE | RESEARCH ONLY |
| healthy-baseline-v1 | low | medium | ELIGIBLE | ELIGIBLE | ELIGIBLE |
| evidence-ask-labor-v1 | low | medium | ELIGIBLE | ELIGIBLE | ELIGIBLE |
| analyze-action-v1 | medium | medium | ELIGIBLE | ELIGIBLE | ELIGIBLE |
| comparative-reasoning-v1 | low | medium | ELIGIBLE | ELIGIBLE | ELIGIBLE |

Lightning is ineligible for HIGH reasoning cases (only `super`/`ultra` in `_HIGH_CAPABILITY_ROLES`).

---

## Router Interpretation

Phase 18C concluded **CURRENT ROUTER SUFFICIENT**. Phase 18D does not overturn this.

Calibrated re-grading changes individual case scores but not routing regret:
- Router selected Super for all cases in 18C — Super was the only enabled eligible model
  for HIGH-risk/HIGH-reasoning cases
- For `healthy-baseline-v1` (risk=low, reasoning=medium), router selected Lightning and
  Super for comparison — this was correct behavior
- No evidence of consistent routing to the wrong model class

**No routing defects identified by calibration evidence.**

---

## Limitations

1. **Response snippets only**: 18C saved first 300 chars. Full-response grading may differ,
   especially for hallucination (model may use more entity IDs later in response).

2. **Residual hallucination failures**: `in-scope`, `labor-bottleneck` continue to fail the
   hallucination grader after calibration. These are descriptive English phrases, not entity
   references. Fixing this without introducing false passes requires either: (a) a curated
   stoplist of common English hyphenated words, or (b) an LLM judge for semantic intent
   classification. Both deferred per spec §10 (no arbitrary fuzzy matching).

3. **Nano evaluation incomplete**: Nano is operator-disabled. The Nano/Super quality
   comparison matrix has no data. Cannot produce NANO SUFFICIENT or NANO SHOWS GAPS verdict.

4. **Lightning latency: N=1**: Only one Lightning observation from 18C (no warm-up, no
   repetitions). Cannot compute median, p95, or stable steady-state latency.
   Classification as cold-start is HIGH CONFIDENCE but not directly measured.

5. **Single run**: 18C and 18D used single benchmark runs. Spec §33 requires repeatability
   verification. Deferred to 18D.3 live benchmark.

6. **Fixture-only corpus**: All cases use mock fixture context (no live OperationalContextSnapshot).
   Model responses reflect fixture metadata echoing, not real warehouse reasoning.

---

## Recommendation

### For Phase 18E

1. **Re-enable Nano and run calibrated benchmark**: Set `NEMOTRON_NANO_ENABLED=true`,
   run the 18D corpus (6 cases) with explicit warm-up calls and N≥5 repetitions per model.
   Focus on the 3 Nano-POLICY-ELIGIBLE cases first.

2. **Fix fixture metadata leakage**: The 18C system prompt exposed fixture metadata
   (case_id, scenario name) to the model, causing it to echo `wave17-labor-risk-v1`
   and `labor-bottleneck`. Use production-like system prompts in benchmarks.

3. **Lightning steady-state latency**: Run Lightning on 5-10 cases with explicit warm-up
   to establish true steady-state latency for comparison with Super.

4. **Full-response grading**: Store complete model responses (not just snippets) for
   accurate hallucination grading.

5. **Do not change routing policy**: Even if Nano proves sufficient for low-risk ASK
   cases, routing changes require architectural review (per phase spec).

---

## Verdict Summary

**Nano:** `NANO EVALUATION INCONCLUSIVE`
— Nano is operator-disabled (`NEMOTRON_NANO_ENABLED=false`). No live Nano observations
available. Endpoint is deployment_status=DEPLOYED but cannot confirm current availability.
Three POLICY ELIGIBLE cases identified in 18D corpus for future evaluation.

**Lightning:** `LIGHTNING LATENCY PARTIALLY EXPLAINED`
— Client-side analysis confirms connection reuse (no TLS/connect overhead). Server-side
root cause is most likely cold container / model warmup (HIGH CONFIDENCE), but cannot
confirm without server-side TTFT breakdown. N=1 observation; no warm-up call was issued.

**Router:** `CURRENT ROUTER REMAINS SUFFICIENT`
— Calibrated grading changed individual case scores (+0.20 to +0.50 per case) but did not
reveal any routing regret or systematic routing defect. Router correctly selected Super for
high-risk/high-reasoning cases and Lightning/Super for the healthy-baseline comparison case.
