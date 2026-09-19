# ModelGateway — Architecture & Developer Guide

**Version:** MAIW v2
**Status:** AUTHORITATIVE — current single model-access boundary for all MAIW agents
Feature flag: `MODEL_GATEWAY_ENABLED` (default `true`)

---

## Overview

The ModelGateway is the single model-access boundary in MAIW v2. All agents and runtimes
route model requests through the gateway. Agents and runtimes do **not** instantiate provider
clients directly.

Agents describe *what* they need (task, reasoning depth, risk level, modality) and the
gateway resolves *which* model to use. The routing decision and selection provenance are
observable through structured telemetry.

```
AgentRuntime
  │  ModelRequest(task, messages, reasoning, risk_level, modality, …)
  ▼
ModelGateway
  ├─ PolicyFilter          — model eligibility per deployment environment
  ├─ ModelRouter           — routing policy: chooses logical role
  ├─ Deployment Resolver   — selects physical endpoint for the role
  ├─ NIMProvider           — calls NVIDIA NIM inference endpoint
  ├─ GatewayTelemetry      — structured JSON provenance log
  └─ ModelResponse         (content, latency_ms, usage, route_decision, …)
```

Routing provenance is fully observable via `ModelRouteDecision` (see Routing telemetry).

---

## Package layout

```
src/api/services/model_gateway/
├── __init__.py         Public API + singleton (get_model_gateway, is_model_gateway_enabled)
├── models.py           Pydantic v2 request/response/capability types, enums
├── registry.py         ModelRegistry — Nemotron role catalogue, env-driven config
├── router.py           ModelRouter   — deterministic routing policy + routing_rule
├── gateway.py          ModelGateway  — orchestrator
├── telemetry.py        GatewayTelemetry — structured JSON logging
├── errors.py           Typed error hierarchy
└── providers/
    ├── __init__.py
    └── nim.py          NIMProvider — wraps NIMClient, translates errors
```

---

## Model inventory (endpoint-validated 2026-08-20)

All four Nemotron 3 / 3.5 MoE models were confirmed live on `integrate.api.nvidia.com/v1`.
The suffix `a3b / a12b / a55b` denotes active parameter count in the Mixture-of-Experts
architecture (active params at inference, not total params).

| Role        | Default model ID                             | Generation   | Enabled? | Endpoint status                             | tool_use |
|-------------|----------------------------------------------|--------------|----------|---------------------------------------------|----------|
| `lightning` | `nvidia/nemotron-3.5-lightning-30b-a3b`      | Nemotron 3.5 | **yes**  | ✓ DEPLOYED — 279 ms p50                     | **yes**  |
| `nano`      | `nvidia/nemotron-3-nano-30b-a3b`             | Nemotron 3   | **yes**  | ✓ DEPLOYED — 364 ms p50                     | no       |
| `super`     | `nvidia/nemotron-3-super-120b-a12b`          | Nemotron 3   | **yes**  | ✓ DEPLOYED — 275 ms p50                     | no       |
| `ultra`     | `nvidia/nemotron-3-ultra-550b-a55b`          | Nemotron 3   | no       | ✓ DEPLOYED — ~31 s (cost; operator opt-in)  | no (assumed) |
| `nano-omni` | *(operator must configure)*                  | unknown      | no       | ✗ NOT CURRENTLY DEPLOYED — no verified VL model ID in NIM catalog | no |

**Superseded model IDs** (removed from `integrate.api.nvidia.com/v1` as of 2026-08-20):

| Legacy model ID                              | Prior role  | Status                        |
|----------------------------------------------|-------------|-------------------------------|
| `nvidia/llama-3.3-nemotron-super-49b-v1.5`  | super       | HTTP 200 but `content=null` (endpoint broken) |
| `nvidia/llama-3.1-nemotron-nano-4b-v1.1`    | nano        | HTTP 404                      |
| `nvidia/llama-3.1-nemotron-ultra-253b-v1`   | ultra       | HTTP 404                      |
| `nvidia/llama-nemotron-nano-vl-8b-v1`       | nano-omni   | HTTP 404                      |

These IDs are preserved as `LEGACY_*` constants in `registry.py` for audit and tooling purposes.
They must **not** be used as defaults for any role.

**Structured output** (JSON mode): not confirmed for any model — all return extended thinking
traces rather than pure JSON.  `structured_output=False` for all roles until further notice.

---

## Logical role → Physical model separation

Agents depend only on capabilities and task requirements, never on physical model IDs.

```
Logical role  →  ModelCapability  →  deployment_endpoint  →  physical model_id
              (generation, provider,                         (resolved from env var,
               modalities, tool_use,                         never hardcoded in agent)
               context_window, …)
```

`ModelCapability` fields:

| Field               | Type         | Purpose                                               |
|---------------------|--------------|-------------------------------------------------------|
| `model_id`          | str          | Physical NIM model identifier                         |
| `role`              | str          | Logical role (lightning/nano/super/ultra/nano-omni)   |
| `family`            | str          | `"nemotron"`                                          |
| `generation`        | str          | e.g. `"nemotron-3"`, `"nemotron-3.5"`, `"nemotron-vl"` |
| `provider`          | str          | `"nvidia-nim"`                                        |
| `modalities`        | set[str]     | What input types this model handles                   |
| `tool_use`          | bool         | Supports tool/function calling                        |
| `structured_output` | bool         | Supports structured output / JSON mode                |
| `reasoning_level`   | ReasoningLevel | Intrinsic reasoning capability                      |
| `latency_class`     | LatencyClass | Expected latency tier                                 |
| `cost_class`        | CostClass    | Relative cost tier                                    |
| `teacher_judge`     | bool         | Suitable for teacher/judge evaluation workloads       |
| `context_window`    | int\|None    | Context window in tokens (None = not confirmed)       |
| `deployment_endpoint` | str\|None | Overrides global NIM URL                            |
| `enabled`           | bool         | Whether this role is active in the current environment|

---

## Nemotron model roles

| Role        | Generation      | Routing priority                                           |
|-------------|-----------------|------------------------------------------------------------|
| `lightning` | nemotron-3.5    | LOW reasoning, LOW risk — quick classification             |
| `nano`      | nemotron-3      | MEDIUM reasoning — moderate analysis                       |
| `super`     | nemotron-3      | HIGH reasoning, CRITICAL risk, wave recovery — complex planning |
| `ultra`     | nemotron-3      | Teacher/judge tasks — trajectory evaluation                |
| `nano-omni` | *unverified*    | Multimodal (IMAGE/VIDEO/AUDIO) requests (not yet deployed) |

---

## Configuration

```bash
# ── Enable/disable roles ──────────────────────────────────────────────────────
NEMOTRON_LIGHTNING_ENABLED=true       # default true — DEPLOYED, 279ms p50
NEMOTRON_NANO_ENABLED=true            # default true — DEPLOYED, 364ms p50
NEMOTRON_SUPER_ENABLED=true           # default true — DEPLOYED, 275ms p50
NEMOTRON_ULTRA_ENABLED=false          # default false — ~31s latency; operator opt-in
NEMOTRON_NANO_OMNI_ENABLED=false      # default false — NOT_CURRENTLY_DEPLOYED

# ── Override physical model IDs ────────────────────────────────────────────────
# Defaults (validated Nemotron 3 / 3.5 on integrate.api.nvidia.com/v1 2026-08-20):
NEMOTRON_LIGHTNING_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b
NEMOTRON_NANO_MODEL=nvidia/nemotron-3-nano-30b-a3b
NEMOTRON_SUPER_MODEL=nvidia/nemotron-3-super-120b-a12b
NEMOTRON_ULTRA_MODEL=nvidia/nemotron-3-ultra-550b-a55b
# Nano Omni: no verified ID in NIM catalog as of 2026-08-20.
# Operator MUST set this to a confirmed VL/multimodal model ID before enabling.
# NEMOTRON_NANO_OMNI_MODEL=<verified-vl-model-id>

# ── Feature flag ──────────────────────────────────────────────────────────────
MODEL_GATEWAY_ENABLED=true            # default true; set false only for operator rollback

# ── Environment presets ────────────────────────────────────────────────────────
# Standard (uses defaults — Lightning + Nano + Super):
# (no overrides needed — all three enabled by default)
#
# With Ultra for evaluation workloads:
# NEMOTRON_ULTRA_ENABLED=true
#
# With Nano Omni (requires operator-supplied VL model):
# NEMOTRON_NANO_OMNI_ENABLED=true NEMOTRON_NANO_OMNI_MODEL=<verified-vl-model-id>
```

---

## Routing policy

Rules applied in priority order:

| Priority | Routing rule          | Condition                           | Preferred role  |
|----------|-----------------------|-------------------------------------|-----------------|
| 1        | `multimodal_input`    | modality ≠ TEXT                     | nano-omni       |
| 2        | `judge_task`          | task name contains judge/eval/…     | ultra           |
| 3        | `critical_risk`       | risk_level = CRITICAL               | super           |
| 4        | `high_reasoning`      | reasoning = HIGH                    | super           |
| 5        | `medium_reasoning`    | reasoning = MEDIUM                  | nano            |
| 6        | `low_reasoning`       | reasoning = LOW                     | lightning       |

Fallback chains:

| Primary role | Fallback order |
|--------------|----------------|
| `lightning`  | nano → super   |
| `nano`       | super          |
| `super`      | (none → raises ModelUnavailable) |
| `ultra`      | super          |
| `nano-omni`  | super          |

---

## Routing telemetry

`ModelRouteDecision` carries separate fields for requested vs actual routing, making
provenance fully observable. `routing_reason` always describes WHY `requested_role` was
chosen; fallback fields explain any deviation.

```json
{
  "requested_role": "nano",
  "selected_role": "super",
  "routing_rule": "medium_reasoning",
  "routing_reason": "reasoning=MEDIUM prefers Nano",
  "fallback_from": "nano",
  "fallback_reason": "role=nano is disabled; escalated to super",
  "selected_model": "nvidia/nemotron-3-super-120b-a12b",
  "task": "warehouse.operations.summarize_state",
  "requested_reasoning": "medium",
  "requested_risk_level": "low"
}
```

---

## Task routing reference

| Task                                       | Reasoning | Risk     | Role target |
|--------------------------------------------|-----------|----------|-------------|
| `warehouse.*.understand_query`             | LOW       | LOW      | lightning   |
| `warehouse.forecasting.generate_response`  | MEDIUM    | LOW      | nano        |
| `warehouse.operations.generate_response`   | MEDIUM    | LOW/HIGH | nano/super  |
| `warehouse.operations.recover_wave`        | MEDIUM    | HIGH     | super       |
| `warehouse.equipment.<maintenance/assign>` | HIGH      | HIGH     | super       |
| `warehouse.equipment.summarize_health`     | MEDIUM    | LOW      | nano        |
| `warehouse.safety.broadcast_alert`         | HIGH      | CRITICAL | super       |
| `warehouse.safety.lockout_tagout`          | HIGH      | CRITICAL | super       |
| `warehouse.safety.incident_report`         | HIGH      | HIGH     | super       |
| `warehouse.safety.summarize_event`         | MEDIUM    | MEDIUM   | nano        |

---

## DocumentAgent compatibility exception

DocumentAgent implements a multi-stage NeMo OCR/extraction pipeline with distinct model
requirements per stage. The document pipeline stages that use direct NIMClient calls (OCR,
embedding, extraction) are an explicit compatibility exception pending multimodal NIM endpoint
availability for the nano-omni role.

Evidence: `document/action_tools.py`, `document/document_extraction_agent.py`,
`document/processing/embedding_indexing.py`, `document/validation/large_llm_judge.py`.

These are not routing decisions — they label pipeline stages. Full gateway integration
requires multimodal NIM endpoint provisioning for the nano-omni role.

---

## Diagnostic report

```bash
python scripts/model_routing_report.py
# With additional roles enabled:
NEMOTRON_NANO_ENABLED=true python scripts/model_routing_report.py
```

Sample output (default deployment — Lightning + Nano + Super enabled):

```
ROLE        EN   GENERATION      PHYSICAL MODEL                                 PROVIDER    DEPLOYMENT STATUS
────────────────────────────────────────────────────────────────────────────────────────────────────────────
lightning   yes  nemotron-3.5    nvidia/nemotron-3.5-lightning-30b-a3b          nvidia-nim  ✓ deployed
nano        yes  nemotron-3      nvidia/nemotron-3-nano-30b-a3b                 nvidia-nim  ✓ deployed
super       yes  nemotron-3      nvidia/nemotron-3-super-120b-a12b              nvidia-nim  ✓ deployed
ultra       no   nemotron-3      nvidia/nemotron-3-ultra-550b-a55b              nvidia-nim  ✓ deployed
nano-omni   no   unknown         (operator must configure)                      nvidia-nim  ✗ not-deployed
```

---

## Testing

```bash
python -m pytest tests/unit/test_model_gateway.py -v
```

117 tests covering:
- `TestModelRegistry` — roles, enabled/disabled, env-driven IDs, reload
- `TestModelCapabilityFields` — generation labels, DeploymentStatus, tool_use validation,
  structured_output conservative defaults, enabled-by-default assertions, Nano Omni sentinel guard
- `TestDefaultModelIds` — default model IDs are Nemotron 3/3.5, no legacy llama-nemotron
- `TestModelRouter` — all routing rules, fallback chains, ModelUnavailable
- `TestRouteDecisionFields` — requested_role, routing_rule, telemetry accuracy
- `TestRoutingMatrix` — 11 representative warehouse workloads × 3 assertions
- `TestRoutingMatrixFallbacks` — all fallback scenarios validated
- `TestModelGateway` — end-to-end with mocked provider
- `TestNIMClientModelOverride` — model_override plumbing
- `TestOperationsAgentGatewaySlice` — gateway attribute + feature flag
- `TestEquipmentAgentGatewaySlice` — gateway attribute + feature flag
- `TestSafetyAgentGatewaySlice` — gateway attribute + feature flag
- `TestFeatureFlag` + `TestGatewaySingleton`

All tests are synchronous (asyncio.run where needed) — no pytest-asyncio dependency.
