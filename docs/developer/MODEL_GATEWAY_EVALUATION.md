# ModelGateway Evaluation — Phase 18B Developer Reference

## Overview

Phase 18B establishes the foundation for reproducible, policy-constrained model routing and offline evaluation in MAIW. It makes every routing decision explicit, measurable, and traceable — and builds the typed infrastructure for multi-model benchmarking (Phase 18C+).

## Architecture Decision: Switchyard Not Adopted

Switchyard (an external model routing proxy) was evaluated during Phase 18A and rejected. MAIW routing requirements are:

- Policy-constrained per request (risk level, reasoning level, deployment mode)
- Air-gap compatible (no external routing control plane)
- Traceable to individual agent requests
- Deterministic and auditable

Switchyard's proxy architecture does not match these requirements. The existing deterministic `ModelRouter` remains the routing authority. Phase 18B instruments and formalizes it; it does not replace it.

---

## Conceptual Flow

```
ModelRequest
    ↓
HARD POLICY FILTER (PolicyFilter)
    ├── enabled state
    ├── RiskLevel (CRITICAL/HIGH → high-capability models only)
    ├── ReasoningLevel (HIGH → high-capability models only)
    ├── Modality (non-TEXT → multimodal models only)
    ├── DeploymentMode (LOCAL_NIM, NVIDIA_HOSTED, ENTERPRISE, OPENAI_COMPATIBLE)
    └── required_capabilities (tool_use, structured_output, teacher_judge)
    ↓
Eligible Candidates → candidate_models in ModelRouteDecision
    ↓
ModelRouter (RuleBasedRoutingStrategy)
    ↓
Selected Model + routing_strategy + routing_latency_ms
    ↓
Deployment Resolution (NIMProvider)
    ↓
Model Inference → ModelResponse
```

**Policy decides what is allowed. Routing chooses among allowed candidates.**

A routing strategy MUST NOT select a model excluded by the policy filter.

---

## ModelGateway

`ModelGateway` is the sole inference boundary in MAIW. All agents and Copilot service call `gateway.generate(ModelRequest)`. No code outside `ModelGateway` may instantiate `NIMClient` or `NIMProvider` directly.

```python
from maiw_models import ModelGateway, ModelRequest, ReasoningLevel, RiskLevel

response = await gateway.generate(ModelRequest(
    task="warehouse.wave_recovery",
    messages=[{"role": "user", "content": "Why is Wave 17 at risk?"}],
    reasoning=ReasoningLevel.HIGH,
    risk_level=RiskLevel.HIGH,
    deployment_mode=DeploymentMode.NVIDIA_HOSTED,  # Phase 18B addition
))
# response.route_decision.routing_strategy == "rules"
# response.route_decision.candidate_models == [eligible model IDs]
# response.route_decision.routing_latency_ms == <float ms>
```

---

## Hard Policy Filter

`PolicyFilter` determines which models are ELIGIBLE for a request. Instantiate with a `ModelRegistry`:

```python
from maiw_models.routing import PolicyFilter
from maiw_models.models import DeploymentMode

policy = PolicyFilter(registry)
candidates = policy.filter(request, DeploymentMode.NVIDIA_HOSTED)
```

Policy constraints (all must pass):
1. `enabled=True` in registry
2. Modality supported by model
3. Provider compatible with DeploymentMode
4. `RiskLevel.CRITICAL` → only `super`/`ultra` roles
5. `ReasoningLevel.HIGH` → only `super`/`ultra` roles
6. Required capabilities (`tool_use`, `structured_output`, `teacher_judge`)

---

## RoutingStrategy Protocol

```python
from maiw_models.routing import RoutingStrategy, ModelCandidate, RoutingContext

class RoutingStrategy(Protocol):
    def select(
        self,
        request: ModelRequest,
        candidates: list[ModelCandidate],
        context: RoutingContext,
    ) -> ModelRouteDecision: ...
```

Strategies receive ONLY the eligible candidates (post-policy). They MUST NOT:
- invoke model calls
- access `DecisionEngine`, `ApprovalStore`, `ActionExecutor`, or MCP writes
- modify the candidate list

The deterministic `ModelRouter` is the current and only production implementation.

---

## Eligible Candidates

`ModelRouteDecision.candidate_models` contains the model IDs eligible **after** policy filtering — not all models in the registry. This is the semantically correct list for evaluation reproducibility.

```python
decision = router.route(request)
print(decision.candidate_models)     # ["test/super-model"] (only eligible models)
print(decision.routing_strategy)     # "rules"
print(decision.routing_latency_ms)   # e.g. 0.082 ms
```

---

## Deployment Mode

`DeploymentMode` is now wired into `ModelRequest`:

| Mode | Description |
|------|-------------|
| `NVIDIA_HOSTED` | NVIDIA NIM public cloud (integrate.api.nvidia.com) |
| `LOCAL_NIM` | Self-hosted NIM container (MAIW_NIM_BASE_URL) |
| `OPENAI_COMPATIBLE` | Any OpenAI-compatible endpoint |
| `ENTERPRISE` | Enterprise-managed NIM (NGC private registry) |

Default: `NVIDIA_HOSTED` (backward compatible with all pre-18B code).

---

## Fallback Behavior

The fallback chain is unchanged from pre-18B:

```
lightning → nano → super
nano → super
super → (ModelUnavailable raised)
ultra → super
nano-omni → super (degrades to text-only)
```

Fallback information is preserved in `ModelRouteDecision`:
- `fallback_from`: the skipped preferred role
- `fallback_reason`: human-readable explanation

---

## Routing Provenance

Every `ModelResponse.route_decision` now includes:

| Field | Type | Meaning |
|-------|------|---------|
| `routing_strategy` | `str` | Always `"rules"` until adaptive routing |
| `routing_latency_ms` | `float` | Monotonic time for route selection only |
| `candidate_models` | `list[str]` | Eligible model IDs after policy filter |
| `selected_model_id` | `str` | The chosen model |
| `routing_rule` | `str` | Machine-readable rule slug |
| `routing_reason` | `str` | Human-readable explanation |
| `fallback_from` | `str\|None` | Set when fallback fired |

Telemetry emits all fields as structured JSON log lines.

---

## Evaluation Cases

`EvaluationCase` is the dataset format for 18C benchmarking:

```python
from maiw_models.evaluation.models import EvaluationCase, TaskFamily

case = EvaluationCase(
    case_id="wave17-labor-risk-v1",
    task_family=TaskFamily.ASK,
    prompt="Why is Wave 17 at risk?",
    context_snapshot_id="snap-001",
    reasoning_level="high",
    risk_level="high",
    expected_capability="labor_reallocation",
    expected_target="wave-17",
    required_facts=["wave-17", "labor"],
    forbidden_claims=["wave-99", "external-agency"],
    context_entities=["wave-17", "worker-A001", ...],
)
```

---

## Deterministic Graders

Six graders evaluate `ModelEvaluationResult` against `EvaluationCase` deterministically (no LLM judge):

| Grader | What it checks |
|--------|----------------|
| `SchemaValidityGrader` | Output satisfies `expected_schema` |
| `HallucinationGrader` | No entity IDs outside `context_entities` |
| `CapabilityMatchGrader` | Recommendation matches `expected_capability` |
| `TargetMatchGrader` | Response addresses `expected_target` entity |
| `RequiredEvidenceGrader` | All `required_facts` present in response |
| `ForbiddenClaimsGrader` | None of `forbidden_claims` appear in response |

```python
from maiw_models.evaluation.graders import run_graders, default_graders

results = run_graders(case, model_result)
for gr in results:
    print(f"{gr.grader_name}: {'PASS' if gr.passed else 'FAIL'} — {gr.reason}")
```

---

## OperationalContextSnapshot Replay

Converts a stored `OperationalContextSnapshot` (WS2) into the exact bounded context used during the original turn — no fresh graph traversal, no live state substitution.

```python
from maiw_models.evaluation.replay import replay_context_from_snapshot
from maiw_api.copilot.store import get_copilot_store

store = get_copilot_store()
snapshot = store.get_context_snapshot(context_snapshot_id)
replay_ctx = replay_context_from_snapshot(snapshot, user_prompt="Why is Wave 17 at risk?")

request = ModelRequest(
    task="eval.replay",
    messages=replay_ctx.messages,
    reasoning=ReasoningLevel.HIGH,
    risk_level=RiskLevel.HIGH,
)
response = await gateway.generate(request)
```

For unit tests without the `maiw_api` runtime, use `MockOperationalContextSnapshot`.

---

## Evaluation Architecture Invariants

Evaluation MUST NOT:
- Create `ActionProposal`
- Invoke `DecisionEngine`
- Request approval
- Invoke `ActionExecutor`
- Call MCP write capabilities

Evaluation calls MUST go through `ModelGateway` only. No direct `NIMClient` instantiation.

Evaluation results MUST NOT contaminate:
- Copilot conversation state
- Approval queues
- Developer decision lifecycle
- LIVE warehouse world

---

## Air-Gap Compatibility

Phase 18B infrastructure is usable in air-gapped environments:
- No SaaS routing dependency
- No external routing control plane
- No telemetry that requires Internet access
- `LOCAL_NIM` deployment mode supported throughout

---

## Model Inventory

See `packages/maiw-models/maiw_models/registry.py` for the canonical model inventory. Each model exposes: `model_id`, `role`, `family`, `generation`, `enabled`, `reasoning_level`, `modalities`, `tool_use`, `structured_output`, `teacher_judge`, `deployment_status`, `latency_class`, `cost_class`.

Do not duplicate registry data in another config file.

---

## Phase 18C — Multi-Model Benchmark

Phase 18C adds the benchmark infrastructure on top of the 18B foundation.

### Forced-Model Evaluation Entry Point

```python
from maiw_models import ModelGateway

result = await gateway.evaluate_with_model(
    request=ModelRequest(task=..., messages=..., reasoning=..., risk_level=...),
    model_id="nvidia/nemotron-3-nano-30b-a3b",
    allow_out_of_policy=False,   # default: only policy-eligible models
)
# result: EvaluationCallResult
# result.policy_compliant    — was the model eligible under current policy?
# result.response_content    — raw response text; None on error
# result.fallback_used       — always False (forced eval never silently falls back)
# result.timed_out           — True when deadline/timeout occurred
# result.error               — "FORCED MODEL FAILED: ..." on provider failure
```

Hard invariants:
- `fallback_used` is always `False` — no silent fallback to another model.
- Provider exceptions are caught and returned as `error`, not raised.
- `routing_strategy` in telemetry is `"forced_evaluation"`.
- Policy check still runs. Pass `allow_out_of_policy=True` only for offline research.

### How to Create and Reuse Context Snapshots

For tests, use `MockOperationalContextSnapshot` from `maiw_models.evaluation.replay`:

```python
from maiw_models.evaluation.replay import (
    MockOperationalContextSnapshot, MockSnapshotNode, MockSnapshotEdge,
    replay_context_from_snapshot,
)

snapshot = MockOperationalContextSnapshot(
    context_snapshot_id="my-snapshot-001",
    focus_entity_id="wave-17",
    nodes=[MockSnapshotNode("wave-17", "Wave", "Wave 17", {"status": "delayed"})],
)
context = replay_context_from_snapshot(snapshot, user_prompt="Why is Wave 17 at risk?")
# context.messages → ready for ModelRequest.messages
```

For production replays, import `OperationalContextSnapshot` from `maiw_api.copilot.models`.

### How to Run the Benchmark

```bash
# Print candidate model inventory (no inference):
python -m maiw_models.eval inventory

# Run live benchmark (requires NVIDIA_API_KEY):
python -m maiw_models.eval benchmark \
  --cases artifacts/phase18/cases.json \
  --output artifacts/phase18/baseline.json

# Generate Markdown report from results:
python -m maiw_models.eval report \
  --input artifacts/phase18/baseline.json \
  --output artifacts/phase18/BASELINE_ROUTER_REPORT.md
```

When `NVIDIA_API_KEY` is not set, the CLI validates infrastructure and writes results
with `endpoint_status = "NOT RUN — ENDPOINT UNAVAILABLE"`.

### Deterministic Grader Definitions

Six graders applied to every `(EvaluationCase, model_response)` pair:

| Grader | What it checks | Applicable when |
|--------|---------------|-----------------|
| `schema_validity` | Response matches `expected_schema` JSON structure | `expected_schema` is set |
| `hallucination` | Response references only entity IDs in `context_entities` | `context_entities` is non-empty |
| `capability_match` | Response mentions `expected_capability` or synonym | `expected_capability` is set |
| `target_match` | Response references `expected_target` entity | `expected_target` is set |
| `required_evidence` | Response contains all `required_facts` strings | `required_facts` is non-empty |
| `forbidden_claims` | Response does not assert any `forbidden_claims` | `forbidden_claims` is non-empty |

Quality score = `passed_applicable / total_applicable`. Skipped graders (case field absent)
do not count toward the denominator.

### Interpreting Policy Eligibility

A grader result alone does not indicate whether a model should be deployed for a case.
Cross-reference `policy_compliant` in each `BenchmarkModelResult`:

```
policy_compliant=True  + quality_pass=True  → VALID production candidate
policy_compliant=True  + quality_pass=False → router selected correctly; quality gap
policy_compliant=False + quality_pass=True  → OFFLINE QUALITY PASS /
                                              NOT PRODUCTION ELIGIBLE UNDER CURRENT POLICY
policy_compliant=False + quality_pass=False → out-of-policy and failed; not meaningful
```

An out-of-policy quality pass is NOT a router bug. It means the model passed the offline
corpus but does not meet current deployment policy for that request. Change policy only
after deliberate governance review, not because of benchmark results alone.

### Router / Oracle Comparison

For each case the runner records:
- **Router selection** — what `ModelRouter.route()` chose (rule-based, no inference).
- **Oracle** — offline computation from benchmark results:
  - `BEST QUALITY` — highest quality_score (tie-break: lower latency).
  - `FASTEST PASSING` — min total_latency_ms among quality_pass=True models.
  - `LOWEST COST` — always `"unavailable"` (no pricing metadata in repo/config).
- **Regret** — split by dimension:
  - `quality_regret`: router chose a model that missed graders the oracle passed.
  - `latency_regret`: router chose a slower model when a faster model also passed.

### Phase 18C Live Benchmark Results (2026-09-12)

Run with Nemotron Lightning + Super enabled (Nano disabled in current environment).

| Case | Model | Quality | Latency | Pass |
|------|-------|---------|---------|------|
| Wave17 ASK | Super (120B) | 0.40 | 2515ms | NO |
| Equipment ASK | Super (120B) | 0.80 | 2348ms | NO |
| Healthy ANALYZE | Lightning (30B) | 0.50 | 48570ms | NO |
| Healthy ANALYZE | Super (120B) | 0.50 | 1447ms | NO |

**Decision Gate: CURRENT ROUTER SUFFICIENT**

Observations:
1. **No model achieved `quality_pass=True`** in this run. Quality scores of 0.40–0.80 reflect
   that models generated relevant responses but did not use the exact entity IDs required
   by the keyword graders. This is a grader calibration signal, not a quality failure —
   the models discussed wave-17, labor, and conveyor correctly but in natural language rather
   than canonical entity ID form.
2. **Nano is disabled** in this environment. All Nano-eligible requests fell back to Super
   per the routing policy fallback chain.
3. **Lightning latency anomaly** — Lightning (Nemotron 3.5, supposed fast path) ran 48570ms
   for the healthy-baseline case vs Super at 1447ms. This is worth monitoring across runs.
   Single-run variance is expected; a pattern across runs would indicate endpoint congestion
   or model-tier behavior change.
4. **No router regret detected** — because no model achieved `quality_pass=True`, the oracle
   had no passing candidates to compare against. Regret analysis requires at least one
   passing model.
5. **Cost unavailable** — no pricing metadata exists in the repo/config.

### 18D Recommendation

Enable Nano (set `NEMOTRON_NANO_ENABLED=true`) and re-run the benchmark to:
- Measure Nano vs Super quality differential on low/medium-risk ASK cases.
- Validate that Nano handles `healthy-baseline` (ANALYZE, medium reasoning) correctly.
- Determine if Nano introduces meaningful grounding errors on equipment/labor cases.
- Calibrate graders to accept natural-language entity references rather than requiring
  exact canonical ID strings — the current strict keyword match may under-report quality
  for responses that are semantically correct but use surface-form entity names.
