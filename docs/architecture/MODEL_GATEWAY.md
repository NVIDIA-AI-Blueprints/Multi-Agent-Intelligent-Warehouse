# ModelGateway — MAIW v2 Architecture

**Version:** MAIW v2
**Status:** AUTHORITATIVE — canonical model-access boundary for all MAIW agents and runtimes

---

## Purpose

The ModelGateway is the single model-access boundary in MAIW v2. All agents and
runtimes route model requests through the gateway. No agent or runtime instantiates
a provider client directly.

The gateway separates three distinct concerns:

1. **Policy** — `PolicyFilter` determines which models are eligible for a request
   given deployment mode, risk level, reasoning level, modality, and required capabilities.
2. **Routing** — `ModelRouter` selects among eligible candidates using a deterministic
   rule-based strategy.
3. **Deployment resolution** — the registry and provider layer map the selected logical
   role to a physical endpoint.

Agents express *what they need* (task, reasoning depth, risk level, modality).
The gateway decides *which model to use*. Routing provenance is fully observable
through structured telemetry.

---

## Architectural Principles

- **Single inference boundary.** Every model call in MAIW flows through `ModelGateway.generate()`.
  No agent or runtime holds a raw `NIMClient` reference outside the provider layer.
- **Logical role, not physical model ID.** Agents submit `ModelRequest` objects
  describing task intent. They never name a specific model ID.
- **Policy before routing.** `PolicyFilter` runs before `ModelRouter`. The router
  selects only from the eligible set returned by the filter.
- **Deterministic and auditable.** Routing rules are explicit and ordered.
  Every selection is recorded in `ModelRouteDecision` and emitted as telemetry.
- **No write operations below the gateway.** `ModelGateway` calls the provider and
  returns a normalized `ModelResponse`. It does not create `ActionProposal` objects,
  invoke `DecisionEngine`, or touch `ApprovalStore` or `ActionExecutor`.

---

## Request Flow

```
AgentRuntime
  │  ModelRequest(task, messages, reasoning, risk_level, modality, deployment_mode, …)
  ▼
ModelGateway.generate()
  │
  ├─ 1. Deadline guard (RequestDeadline.expired → reject before any provider call)
  │
  ├─ 2. ModelRouter.route(request)
  │       │
  │       ├─ PolicyFilter.filter(request, deployment_mode)
  │       │       → list[ModelCandidate]   (enabled + eligible after all policy constraints)
  │       │
  │       └─ _select_role(request)
  │               → (preferred_role, routing_rule, routing_reason)
  │               → _resolve_with_fallback(preferred_role)
  │                       → ModelRouteDecision
  │
  ├─ 3. ModelRegistry.get_by_id(decision.selected_model_id)
  │       → ModelCapability (physical endpoint, provider, capability flags)
  │
  ├─ 4. NIMProvider.call(model_id, request, capability)
  │       [wrapped in CircuitBreaker if nim_circuit is configured]
  │       → LLMResponse
  │
  ├─ 5. GatewayTelemetry.record_success(…)
  │
  └─ 6. ModelResponse(content, model_id, latency_ms, route_decision, …)
              returned to AgentRuntime
```

Failure at any step is translated to a `ModelGatewayError` subclass.
The telemetry records both success and failure paths.

---

## Responsibilities

**ModelGateway owns:**
- Deadline enforcement before provider calls
- Routing (via `ModelRouter` + `PolicyFilter`)
- Provider dispatch (via `NIMProvider`)
- Error normalization — provider exceptions become `ModelGatewayError` subclasses
- Structured telemetry

**ModelGateway does NOT own:**
- SOP logic or warehouse operational semantics
- ActionProposal creation or approval
- DecisionEngine or governance
- MCP write capabilities
- Agent conversation state

---

## PolicyFilter

`PolicyFilter` (`packages/maiw-models/maiw_models/routing.py`) is the hard policy
layer. It determines which models are **eligible** for a request before routing runs.

Six eligibility constraints are applied. A model must pass all six:

| # | Constraint | Rule |
|---|------------|------|
| 1 | **Enabled** | `ModelCapability.enabled` must be `True` |
| 2 | **Provider / deployment mode** | Model's `provider` must match the allowed set for the request's `deployment_mode` |
| 3 | **Modality** | Non-TEXT requests require the model to explicitly support that modality; TEXT requests require `"text"` in `modalities` |
| 4 | **Risk level** | `risk_level=CRITICAL` → only high-capability roles (`super`, `ultra`) are eligible |
| 5 | **Reasoning level** | `reasoning=HIGH` → only high-capability roles (`super`, `ultra`) are eligible |
| 6 | **Required capabilities** | Any `required_capabilities` tag (`tool_use`, `structured_output`, `teacher_judge`) must be satisfied by the model's capability flags |

`PolicyFilter` does not rank candidates — that is the routing strategy's job.
The eligible candidate list is recorded as `ModelRouteDecision.candidate_models`
and surfaced in all telemetry and evaluation results.

---

## ModelRouter

`ModelRouter` (`packages/maiw-models/maiw_models/router.py`) selects among
eligible candidates using a deterministic rule-based strategy (`routing_strategy="rules"`).

### Routing rules (priority order)

| Priority | Routing rule | Condition | Preferred role |
|----------|-------------|-----------|----------------|
| 1 | `multimodal_input` | `modality` ≠ TEXT | `nano-omni` |
| 2 | `judge_task` | task name contains `judge`, `teacher`, `eval`, `offline`, `score`, or `grade` | `ultra` |
| 3 | `critical_risk` | `risk_level=CRITICAL` | `super` |
| 4 | `high_reasoning` | `reasoning=HIGH` | `super` |
| 5 | `medium_reasoning` | `reasoning=MEDIUM` | `nano` |
| 6 | `low_reasoning` | `reasoning=LOW` | `lightning` |

### Fallback chains

When the preferred role is disabled, the router walks a fallback chain:

| Primary role | Fallback order                              |
|-------------|---------------------------------------------|
| `lightning` | `nano` → `super`                            |
| `nano` | `super`                                          |
| `super` | *(none — raises `ModelUnavailable`)*         |
| `ultra` | `super`                                      |
| `nano-omni` | `super` *(TEXT requests only — see below)*  |

When a fallback is used, `fallback_from` and `fallback_reason` are populated
in `ModelRouteDecision` and surfaced in telemetry.

### Fallback policy invariant

**Fallback never relaxes policy.** Every fallback candidate is evaluated against
the original `ModelRequest` constraints before it can be selected. Policy determines
eligibility; fallback is part of routing and remains subject to the same constraints.

Constraints enforced on every fallback candidate (primary and fallback):

- `enabled` state in the registry
- Provider/deployment compatibility (`DeploymentMode`)
- Modality support (`modalities` field on `ModelCapability`)
- `RiskLevel` constraint — `CRITICAL` → only high-capability roles (`super`, `ultra`)
- `ReasoningLevel` constraint — `HIGH` → only high-capability roles (`super`, `ultra`)
- Required capabilities (`tool_use`, `structured_output`, `teacher_judge`)

Routing sequence including fallback:

```text
ModelRequest
    ↓
PolicyFilter          — determines eligible candidate set
    ↓
ModelRouter           — selects preferred role from routing rules
    ↓
Preferred Candidate   — checked against PolicyFilter
    ↓
Fallback Ordering     — next roles in fallback chain, if preferred unavailable
    ↓
Policy Revalidation   — each fallback candidate re-evaluated against ModelRequest
    ↓
Selected Candidate (or ModelUnavailable)
```

**No policy relaxation on failure.** Model unavailability does not permit MAIW to
weaken the original request contract. If no fallback candidate satisfies the policy
constraints, `ModelGateway` raises `ModelUnavailable` rather than selecting an
ineligible model.

Concrete examples:

- An IMAGE request cannot fall back from `nano-omni` to `super`: `super` has
  `modalities={"text"}` only. With `nano-omni` disabled the request raises
  `ModelUnavailable`.
- A request requiring `tool_use` cannot fall back to `nano` or `super`: both have
  `tool_use=False` in the current registry.

This invariant is enforced by regression tests in
`tests/unit/test_model_gateway_fallback_policy.py` covering modality, required
capabilities, risk level, reasoning level, and deployment constraints.

### Routing signals

`ModelRouter` uses only the fields on `ModelRequest`:

- `reasoning` (`ReasoningLevel`) — primary routing signal
- `risk_level` (`RiskLevel`) — elevates to high-capability roles at CRITICAL
- `modality` (`Modality`) — triggers multimodal routing
- `task` (str) — inspected for judge/teacher/eval keywords
- `deployment_mode` (`DeploymentMode`) — passed to `PolicyFilter` for provider eligibility

---

## Deployment Resolution

The registry maps logical roles to physical deployments. Agents never see physical
model IDs.

```
Logical role (lightning / nano / super / ultra / nano-omni)
    ↓
ModelRegistry.get_enabled_by_role(role)
    → ModelCapability
        model_id:            physical NIM model identifier (from env var or default)
        deployment_endpoint: per-model URL override (or None → global NIM URL)
        provider:            "nvidia-nim"
        enabled:             True/False (env-driven)
```

Physical model IDs are configured via environment variables
(`NEMOTRON_LIGHTNING_MODEL`, `NEMOTRON_NANO_MODEL`, etc.) and resolved at
startup by `ModelRegistry`. Defaults point to the current Nemotron 3 / 3.5 MoE
model IDs. Operators override via env var for self-hosted or alternate deployments.

### Nemotron model roles

| Role | Generation | Routing use |
|------|------------|-------------|
| `lightning` | Nemotron 3.5 | LOW reasoning, LOW risk — quick classification |
| `nano` | Nemotron 3 | MEDIUM reasoning — moderate analysis |
| `super` | Nemotron 3 | HIGH reasoning, CRITICAL risk, wave recovery |
| `ultra` | Nemotron 3 | Teacher/judge evaluation workloads |
| `nano-omni` | *unverified* | Multimodal (IMAGE/VIDEO/AUDIO) — operator must configure |

---

## Deployment Modes

`DeploymentMode` (`packages/maiw-models/maiw_models/models.py`) controls which
provider endpoints are eligible during policy filtering.

| Value | Description |
|-------|-------------|
| `nvidia_hosted` | NVIDIA NIM public cloud (`integrate.api.nvidia.com`). Requires `NVIDIA_API_KEY`. |
| `local_nim` | Self-hosted NIM container (on-prem). Set `MAIW_NIM_BASE_URL` and `MAIW_NIM_MODEL`. |
| `openai_compatible` | Any OpenAI-compatible endpoint (vLLM, Ollama, etc.). Set `MAIW_NIM_BASE_URL` and `MAIW_NIM_MODEL`. |
| `enterprise` | Enterprise-managed NIM (NGC private registry). Set `MAIW_NIM_BASE_URL`, `MAIW_NIM_MODEL`, and `NVIDIA_API_KEY`. |

Default for `ModelRequest` is `NVIDIA_HOSTED`. All four modes currently route to
`provider="nvidia-nim"` in the registry.

---

## Provider Layer

`NIMProvider` (`packages/maiw-models/maiw_models/providers/nim.py`) is the only
supported provider. It wraps `NIMClient` and:

- Translates provider-specific exceptions to `ModelGatewayError` subclasses
- Does not expose raw provider structures to the rest of the gateway
- Supports an optional `CircuitBreaker` (`nim_circuit`) — when the circuit is OPEN,
  `NIMProvider` raises `ModelUnavailable` with the remaining cooldown duration

All credentials (`NVIDIA_API_KEY`) are held at or below the provider layer.
Agents and runtimes never receive raw provider credentials.

---

## Agent Runtime Integration

Both production runtimes route through `ModelGateway`. Neither instantiates
provider clients directly.

### MAIWDeterministicRuntime

`MAIWDeterministicRuntime` (`packages/maiw-agents/maiw_agents/runtime/deterministic.py`)
is the default production runtime. It executes SOP phases in strict sequence.
Model calls are made by passing a `ModelRequest` to the gateway instance held
in the agent's operational context.

### DeepAgentsRuntime

`DeepAgentsRuntime` (`packages/maiw-agents/maiw_agents/runtime/deep_agents_runtime.py`)
is the adaptive runtime that delegates step scheduling to the Deep Agents framework.
It uses `MAIWModelGatewayChat` as its model — a LangChain `BaseChatModel` backed
by `ModelGateway`. Deep Agents cannot bypass `ModelGateway`.

`MAIWModelGatewayChat` (`packages/maiw-agents/maiw_agents/runtime/model_adapter.py`):

- Implements `BaseChatModel._generate()` and `_agenerate()`
- All model calls route through `context.model_gateway` — `RiskLevel`,
  `ReasoningLevel`, `DeploymentMode`, routing provenance, deadlines, fallback,
  telemetry, and `trace_id` are all preserved
- In test mode (`model_gateway=None`): returns deterministic mock responses
  without any network calls

`MAIWTestModelAdapter` in the same module is a test-only wrapper; it is not
used in production routing.

### Emergency rollback

`is_model_gateway_enabled()` reads the `MODEL_GATEWAY_ENABLED` environment
variable (default `true`). When set to `false`, several legacy agents
(ForecastingAgent, EquipmentAgent, OperationsAgent, SafetyAgent) fall back to
a direct `NIMClient` path. This is an emergency operator rollback only — the
direct path bypasses `PolicyFilter`, `ModelRouter`, and routing telemetry.
The `MODEL_GATEWAY_ENABLED` flag is expected to be removed once the legacy
fallback paths are retired.

---

## Fallback and Failure Handling

| Scenario | Behavior |
|----------|----------|
| Preferred role disabled | Router walks fallback chain; `fallback_from` + `fallback_reason` set in `ModelRouteDecision` |
| Entire fallback chain exhausted | `ModelUnavailable` raised |
| NIM circuit breaker OPEN | `ModelUnavailable` with cooldown duration; telemetry records failure |
| `RequestDeadline` expired before provider call | `RequestDeadlineExceeded` raised; 0 provider calls made |
| Provider exception | Translated to `ModelGatewayError` subclass; telemetry records failure |
| Evaluation forced-model failure | `EvaluationCallResult.error` set; fallback NOT attempted |

---

## Routing Provenance and Observability

Every `ModelResponse` carries a `ModelRouteDecision` with full routing provenance:

| Field | Description |
|-------|-------------|
| `requested_role` | Ideal role chosen by routing policy before any fallback |
| `selected_role` | Role that actually served the request (may differ from `requested_role`) |
| `selected_model_id` | Physical model ID used |
| `routing_rule` | Machine-readable rule name (e.g., `medium_reasoning`) |
| `routing_reason` | Human-readable explanation of why `requested_role` was chosen |
| `fallback_from` | Set when `selected_role` ≠ `requested_role` |
| `fallback_reason` | Why the preferred role was unavailable |
| `routing_strategy` | Always `"rules"` in the current deterministic implementation |
| `routing_latency_ms` | Monotonic time for route selection only (excludes inference) |
| `candidate_models` | Model IDs eligible after `PolicyFilter` (source of truth for evaluation reproducibility) |
| `task` | Task name from the original `ModelRequest` |
| `requested_reasoning` | Reasoning level from the request |
| `requested_risk_level` | Risk level from the request |

Telemetry is emitted by `GatewayTelemetry` (`packages/maiw-models/maiw_models/telemetry.py`)
as structured JSON on both success and failure paths. The Developer Trace panel
and Model Gateway Evaluation Lab consume this data.

Example provenance record:

```json
{
  "requested_role": "nano",
  "selected_role": "super",
  "routing_rule": "medium_reasoning",
  "routing_reason": "reasoning=MEDIUM prefers Nano",
  "fallback_from": "nano",
  "fallback_reason": "role=nano is disabled; escalated to super",
  "selected_model_id": "nvidia/nemotron-3-super-120b-a12b",
  "routing_strategy": "rules",
  "routing_latency_ms": 0.412,
  "candidate_models": ["nvidia/nemotron-3-super-120b-a12b"],
  "task": "warehouse.operations.summarize_state",
  "requested_reasoning": "medium",
  "requested_risk_level": "low"
}
```

---

## Model Gateway Evaluation Lab

`ModelGateway.evaluate_with_model()` is a forced-model evaluation entry point
used exclusively by the offline Model Gateway Evaluation Lab (WS3).

**What it does:**
- Accepts a `model_id` and calls that exact model, bypassing the normal routing strategy
- Still runs `PolicyFilter` — the result records `policy_compliant` to indicate
  whether the forced model would have been eligible under the current policy
- When `allow_out_of_policy=False` (default), refuses the call if the model
  is not eligible and returns an error in `EvaluationCallResult`
- Emits full routing and provider telemetry for every call
- Returns `EvaluationCallResult` — never raises provider exceptions

**What it does NOT do:**
- Never falls back to another model — if the forced model fails, `error` is set
  and `response_content=None`
- Never creates `ActionProposal`, approval, or MCP write operations
- Never modifies Copilot conversation or approval queues

**Reproducibility identity:** `dataset_id + prompt_hash + model_id + deployment_id + context_snapshot_id`
uniquely identifies an evaluation run. Timestamps are not part of the identity.

The Evaluation Lab is **not** the production routing authority. Evaluation results
inform model selection decisions; they do not change live routing.

---

## Configuration

```bash
# ── Enable/disable roles ──────────────────────────────────────────────────────
NEMOTRON_LIGHTNING_ENABLED=true       # default true
NEMOTRON_NANO_ENABLED=true            # default true
NEMOTRON_SUPER_ENABLED=true           # default true
NEMOTRON_ULTRA_ENABLED=false          # default false — high latency; operator opt-in
NEMOTRON_NANO_OMNI_ENABLED=false      # default false — no verified VL model ID

# ── Override physical model IDs ────────────────────────────────────────────────
NEMOTRON_LIGHTNING_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b
NEMOTRON_NANO_MODEL=nvidia/nemotron-3-nano-30b-a3b
NEMOTRON_SUPER_MODEL=nvidia/nemotron-3-super-120b-a12b
NEMOTRON_ULTRA_MODEL=nvidia/nemotron-3-ultra-550b-a55b
# Nano Omni: operator MUST set to a confirmed VL model ID before enabling.
# NEMOTRON_NANO_OMNI_MODEL=<verified-vl-model-id>

# ── Emergency rollback ─────────────────────────────────────────────────────────
MODEL_GATEWAY_ENABLED=true            # default true; set false only for emergency rollback
                                      # (bypasses PolicyFilter, ModelRouter, telemetry)
```

---

## Task Routing Reference

| Task | Reasoning | Risk | Role target |
|------|-----------|------|-------------|
| `warehouse.*.understand_query` | LOW | LOW | lightning |
| `warehouse.forecasting.generate_response` | MEDIUM | LOW | nano |
| `warehouse.operations.generate_response` | MEDIUM | LOW/HIGH | nano/super |
| `warehouse.operations.recover_wave` | MEDIUM | HIGH | super |
| `warehouse.equipment.<maintenance/assign>` | HIGH | HIGH | super |
| `warehouse.equipment.summarize_health` | MEDIUM | LOW | nano |
| `warehouse.safety.broadcast_alert` | HIGH | CRITICAL | super |
| `warehouse.safety.lockout_tagout` | HIGH | CRITICAL | super |
| `warehouse.safety.incident_report` | HIGH | HIGH | super |
| `warehouse.safety.summarize_event` | MEDIUM | MEDIUM | nano |

---

## DocumentAgent Compatibility Exception

DocumentAgent implements a multi-stage NeMo OCR/extraction pipeline with distinct
model requirements per stage. The document pipeline stages that use direct `NIMClient`
calls (OCR, embedding, extraction) are an explicit compatibility exception pending
multimodal NIM endpoint availability for the `nano-omni` role.

Evidence: `document/action_tools.py`, `document/document_extraction_agent.py`,
`document/processing/embedding_indexing.py`, `document/validation/large_llm_judge.py`.

These are pipeline-stage labels, not routing decisions. Full gateway integration
requires multimodal NIM endpoint provisioning for the `nano-omni` role.

---

## Known Modernization Boundary

The ModelGateway implementation is currently split across two paths:

- `src/api/services/model_gateway/` — DEPRECATED compatibility shims. Each file
  re-exports from `maiw_models.*`. These shims exist to allow existing import
  paths to continue working without modification during the migration period.
  They are marked `DEPRECATED — Remove by Phase 9`.
- `packages/maiw-models/maiw_models/` — canonical package. All substantive logic
  lives here: `gateway.py`, `models.py`, `router.py`, `routing.py`, `registry.py`,
  `telemetry.py`, `providers/`, `evaluation/`.

The canonical import path is:

```python
from maiw_models import ModelGateway, ModelRequest, get_model_gateway
```

The `src/` shims are **not dead legacy code**. Physical removal requires an
explicit migration that preserves all ModelGateway invariants (single inference
boundary, `PolicyFilter`, `ModelRouter`, deployment resolver, routing provenance).
See [ARCHITECTURE.md](ARCHITECTURE.md#known-modernization-boundary) for full context.

`LEGACY_*` constants in `packages/maiw-models/maiw_models/registry.py` record
prior model IDs that are no longer available on the configured NIM endpoint.
They are retained for audit and migration tooling only and must not be used as
defaults for any role.

---

## Security

- All provider credentials (`NVIDIA_API_KEY`) are held at or below the `NIMProvider`
  layer. Agents and runtimes never receive raw credentials.
- The Evaluation Lab (`evaluate_with_model`) is a read-only evaluation path.
  It cannot create approvals, write MCP resources, or modify operational state.
- `MODEL_GATEWAY_ENABLED=false` bypasses the gateway's policy and telemetry.
  This mode is an emergency operator rollback; it must not be used in normal operations.

---

## Developer Guidance

**Agent developers:**
Use the runtime adapter provided by your runtime. Submit `ModelRequest` with intent
fields populated (`reasoning`, `risk_level`, `modality`, `task`). Never name a
`model_id` in a `ModelRequest`.

**Model / platform developers:**
Changes to eligibility logic go in `PolicyFilter` (`maiw_models/routing.py`).
Changes to routing rules go in `ModelRouter` (`maiw_models/router.py`).
Changes to the model catalogue go in `ModelRegistry` (`maiw_models/registry.py`).

**Deployment engineers:**
Configure deployment mode and model IDs via environment variables.
To enable `ultra` for evaluation workloads: `NEMOTRON_ULTRA_ENABLED=true`.
To enable multimodal routing: set `NEMOTRON_NANO_OMNI_ENABLED=true` and
`NEMOTRON_NANO_OMNI_MODEL=<verified-vl-model-id>`.

**Evaluators / researchers:**
Use `ModelGateway.evaluate_with_model()` via the Model Gateway Evaluation Lab
harness. Do not call the method directly in production agent code.

---

## Diagnostics

```bash
python scripts/model_routing_report.py
# With additional roles enabled:
NEMOTRON_ULTRA_ENABLED=true python scripts/model_routing_report.py
```

---

## Testing

```bash
python -m pytest tests/unit/test_model_gateway.py \
                 tests/unit/test_model_gateway_18b.py \
                 tests/unit/test_model_gateway_18c.py \
                 tests/unit/test_model_gateway_18d.py \
                 tests/unit/test_model_gateway_18e.py \
                 tests/unit/test_model_lab_api.py \
                 tests/unit/test_model_gateway_fallback_policy.py -v
```

Tests covering:

- `TestModelRegistry` — roles, enabled/disabled, env-driven IDs, reload
- `TestModelCapabilityFields` — generation labels, `DeploymentStatus`, `tool_use` validation,
  `structured_output` conservative defaults, enabled-by-default assertions, Nano Omni sentinel guard
- `TestDefaultModelIds` — default model IDs are Nemotron 3/3.5, no legacy IDs
- `TestModelRouter` — all routing rules, fallback chains, `ModelUnavailable`
- `TestRouteDecisionFields` — `requested_role`, `routing_rule`, telemetry accuracy
- `TestRoutingMatrix` — 11 representative warehouse workloads × 3 assertions
- `TestRoutingMatrixFallbacks` — fallback scenarios, policy-constrained candidates
- `TestModelGateway` — end-to-end with mocked provider
- `TestFallbackPolicyInvariant` (`test_model_gateway_fallback_policy.py`) — 17 regression tests:
  modality, required capabilities, risk level, reasoning level, deployment mode,
  fallback provenance, `PolicyFilter.is_request_eligible` contract
- Provenance, evaluation, replay, calibration suites
- `TestModelLabAPI` — evaluation endpoint coverage
- `TestNIMClientModelOverride`, `TestFeatureFlag`, `TestGatewaySingleton`

All tests are synchronous (`asyncio.run` where needed) — no pytest-asyncio dependency.

---

## Related Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — top-level system architecture;
  [Known Modernization Boundary](ARCHITECTURE.md#known-modernization-boundary)
- [AGENT_RUNTIME.md](AGENT_RUNTIME.md) — runtime adapter contracts,
  `MAIWDeterministicRuntime` and `DeepAgentsRuntime` architecture
- [GLOSSARY.md](../GLOSSARY.md) — canonical definitions for `ModelGateway`,
  `PolicyFilter`, `ModelRouter`, `DeploymentMode`, and related terms
