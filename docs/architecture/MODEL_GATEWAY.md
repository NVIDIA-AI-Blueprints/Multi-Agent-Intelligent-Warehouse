# ModelGateway — Architecture & Developer Guide

**Phase 1A + 1B + 1C of the MAIW Modernization Plan**
Status: **Implemented** | Feature flag: `MODEL_GATEWAY_ENABLED` (default `true`)

---

## Overview

The ModelGateway is a centralized model-selection and request-routing layer that sits between
MAIW agents and the NVIDIA NIM inference endpoints.  Agents no longer name specific model IDs
or handle provider exceptions.  Instead they describe *what* they need (task, reasoning depth,
risk level, modality) and the gateway resolves *which* model to use.

```
Agent
  │  ModelRequest(task, messages, reasoning, risk_level, modality, …)
  ▼
ModelGateway.generate()
  ├─ ModelRouter.route()          → ModelRouteDecision (requested_role, selected_role, routing_rule, …)
  ├─ ModelRegistry.get_by_id()   → ModelCapability (generation, provider, context_window, …)
  ├─ NIMProvider.call()          → LLMResponse
  ├─ GatewayTelemetry.record_*() → structured JSON log
  └─ ModelResponse                (content, latency_ms, usage, route_decision, …)
```

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

## Model audit — Phase 1C (endpoint-validated 2026-08-20)

All four Nemotron 3 / 3.5 MoE models were confirmed live on `integrate.api.nvidia.com/v1`.
The suffix `a3b / a12b / a55b` denotes active parameter count in the Mixture-of-Experts
architecture (active params at inference, not total params).

| Role        | Default model ID                             | Generation   | Enabled? | Endpoint status                             | tool_use |
|-------------|----------------------------------------------|--------------|----------|---------------------------------------------|----------|
| `lightning` | `nvidia/nemotron-3.5-lightning-30b-a3b`      | Nemotron 3.5 | **yes**  | ✓ DEPLOYED — 279 ms p50                     | **yes**  |
| `nano`      | `nvidia/nemotron-3-nano-30b-a3b`             | Nemotron 3   | **yes**  | ✓ DEPLOYED — 364 ms p50                     | no       |
| `super`     | `nvidia/nemotron-3-super-120b-a12b`          | Nemotron 3   | **yes**  | ✓ DEPLOYED — 275 ms p50                     | no       |
| `ultra`     | `nvidia/nemotron-3-ultra-550b-a55b`          | no           | ✓ DEPLOYED — ~31 s (cost; operator opt-in)  | no (assumed) |
| `nano-omni` | *(operator must configure)*                  | unknown      | no       | ✗ NOT CURRENTLY DEPLOYED — no verified VL model ID in NIM catalog | no |

**Legacy models no longer available** (all removed from `integrate.api.nvidia.com/v1` as of 2026-08-20):

| Legacy model ID                              | Prior role  | Status                        |
|----------------------------------------------|-------------|-------------------------------|
| `nvidia/llama-3.3-nemotron-super-49b-v1.5`  | super       | HTTP 200 but `content=null` (endpoint broken) |
| `nvidia/llama-3.1-nemotron-nano-4b-v1.1`    | nano        | HTTP 404                      |
| `nvidia/llama-3.1-nemotron-ultra-253b-v1`   | ultra       | HTTP 404                      |
| `nvidia/llama-nemotron-nano-vl-8b-v1`       | nano-omni   | HTTP 404                      |

These IDs are preserved as `LEGACY_*` constants in `registry.py` for audit and tooling purposes.
They must **not** be used as defaults for any Nemotron 3 role.

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

`ModelCapability` carries these fields (Phase 1B additions in **bold**):

| Field               | Type         | Purpose                                               |
|---------------------|--------------|-------------------------------------------------------|
| `model_id`          | str          | Physical NIM model identifier                         |
| `role`              | str          | Logical role (lightning/nano/super/ultra/nano-omni)   |
| `family`            | str          | `"nemotron"`                                          |
| **`generation`**    | str          | e.g. `"nemotron-3"`, `"nemotron-3.5"`, `"nemotron-vl"` |
| **`provider`**      | str          | `"nvidia-nim"`                                        |
| `modalities`        | set[str]     | What input types this model handles                   |
| `tool_use`          | bool         | Supports tool/function calling                        |
| **`structured_output`** | bool   | Supports structured output / JSON mode                |
| `reasoning_level`   | ReasoningLevel | Intrinsic reasoning capability                      |
| `latency_class`     | LatencyClass | Expected latency tier                                 |
| `cost_class`        | CostClass    | Relative cost tier                                    |
| `teacher_judge`     | bool         | Suitable for teacher/judge evaluation workloads       |
| **`context_window`** | int\|None  | Context window in tokens (None = not confirmed)       |
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
# Phase 1C defaults (validated 2026-08-20):
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

# ── Feature flag (emergency rollback only) ────────────────────────────────────
MODEL_GATEWAY_ENABLED=true            # set false to revert to direct NIMClient

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

## Routing telemetry — Phase 1B accuracy fix

`ModelRouteDecision` now carries separate fields for requested vs actual routing:

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

The pre-Phase-1B bug was: `routing_reason` described the fallback action instead of the routing
policy rule, making it impossible to tell from telemetry whether a request was served optimally.
Now: `routing_reason` always describes WHY `requested_role` was chosen; the fallback fields
explain any deviation.

---

## Agent migration status

| Agent                  | LLM calls | Status        | Tasks assigned                                |
|------------------------|-----------|---------------|-----------------------------------------------|
| `ForecastingAgent`     | 2         | **Migrated**  | `warehouse.forecasting.{parse_query,generate_response}` |
| `OperationsAgent`      | 2         | **Migrated**  | `warehouse.operations.{understand_query,generate_response}` |
| `EquipmentAgent`       | 2         | **Migrated**  | `warehouse.equipment.{understand_query,<intent>}` |
| `SafetyAgent`          | 2         | **Migrated**  | `warehouse.safety.{understand_query,<intent>}` |
| `DocumentAgent`        | 6+        | **Strategy below** | Modality-aware migration planned       |

### Task → reasoning/risk assignments

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

### DocumentAgent — modality-aware migration strategy

DocumentAgent implements a 6-stage NeMo pipeline with distinct model requirements per stage:

| Pipeline stage         | Input type        | Model target      | Gateway route         |
|------------------------|-------------------|-------------------|-----------------------|
| NeMo Retriever OCR     | Image/PDF pages   | NeMo OCR service  | Out of scope — dedicated service |
| Nemotron Parse         | Structured doc    | Parsing model     | Out of scope — dedicated service |
| SmallLLMProcessor      | Text (from doc)   | Nano Omni (VL)    | `multimodal_input` → nano-omni |
| SmallLLMProcessor      | Text-only path    | Nano              | `medium_reasoning`    |
| EmbeddingIndexing      | Text              | Embedding model   | Out of scope — embed endpoint |
| LargeLLMJudge          | Text evaluation   | Ultra/Super       | `judge_task` → ultra  |
| IntelligentRouter      | Text classification| Nano/Lightning    | `low_reasoning`       |

**NOT** all stages should use Nano Omni — only stages with actual image/document-image inputs.
Text-only extracted content routes to text models.

Full gateway migration of DocumentAgent is deferred pending:
- Multimodal NIM endpoint provisioning for nano-omni
- OCR/Nemotron Parse services decoupled from the main gateway

**Hardcoded model strings in DocumentAgent** (`action_tools.py`, `small_llm_processor.py`,
`large_llm_judge.py`) are documented as legacy technical debt.  They are not production routing
decisions — they label which pipeline stage ran.  Gateway migration is the correct path to
eliminate them, but this requires the multimodal endpoint first.

---

## Remaining legacy dependencies

### Production runtime (not yet migrated to gateway)

| Location                                  | Type         | Scope                               |
|-------------------------------------------|--------------|-------------------------------------|
| `document/action_tools.py:30`             | NIMClient    | DocumentAgent pipeline tools        |
| `document/document_extraction_agent.py:29`| NIMClient    | Main pipeline orchestrator          |
| `document/mcp_document_agent.py:29`       | NIMClient    | MCP variant of DocumentAgent        |
| `document/processing/embedding_indexing.py:38` | NIMClient | Embedding stage (embed endpoint) |
| `document/validation/large_llm_judge.py:65` | LLM_MODEL env | Hardcoded judge model string    |
| `document/processing/small_llm_processor.py` | model strings | Hardcoded stage labels         |
| `inventory/equipment_action_tools.py:34`  | NIMClient    | Equipment action tool LLM calls     |
| `inventory/equipment_asset_tools.py:34`   | NIMClient    | Equipment asset tool LLM calls      |
| `inventory/mcp_equipment_agent.py:31`     | NIMClient    | MCP variant of EquipmentAgent       |
| `operations/action_tools.py:35`           | NIMClient    | Operations action tool LLM calls    |
| `operations/mcp_operations_agent.py:30`   | NIMClient    | MCP variant of OperationsAgent      |
| `safety/action_tools.py:37`               | NIMClient    | Safety action tool LLM calls        |
| `safety/mcp_safety_agent.py:31`           | NIMClient    | MCP variant of SafetyAgent          |

### Tests

Existing tests use NIMClient mocks directly — this is correct for unit tests of the legacy
path and does not need to change.

### Documentation

Architecture docs reference legacy model names in description text.  These are accurate
historical references, not prescriptive routing decisions.

### Training artifacts / historical

`docs/architecture/MODEL_MIGRATION_PLAN.md`, `notebooks/` — reference older model strings in
illustrative context.  No routing decisions are driven by these files.

---

## Emergency rollback

```bash
MODEL_GATEWAY_ENABLED=false
```

All migrated agents fall back to direct NIMClient.  This is **temporary compatibility path**,
not a permanent alternative architecture.

**Technical debt**: the direct NIM path should be removed after:
1. All five primary agents are migrated (ForecastingAgent ✓, OperationsAgent ✓, EquipmentAgent ✓, SafetyAgent ✓, DocumentAgent pending)
2. Nemotron endpoints validated in production
3. Regression suite passes with `MODEL_GATEWAY_ENABLED=true`

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
- `TestForecastingAgentGatewaySlice` — vertical slice
- `TestOperationsAgentGatewaySlice` — gateway attribute + feature flag
- `TestEquipmentAgentGatewaySlice` — gateway attribute + feature flag
- `TestSafetyAgentGatewaySlice` — gateway attribute + feature flag
- `TestFeatureFlag` + `TestGatewaySingleton`

All tests are synchronous (asyncio.run where needed) — no pytest-asyncio dependency.
