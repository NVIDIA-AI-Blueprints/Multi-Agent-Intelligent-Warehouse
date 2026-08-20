# Model Migration Plan: Llama → Nemotron + ModelGateway

**Repository:** Multi-Agent Intelligent Warehouse (MAIW)
**Author:** ML Systems Architecture Review
**Date:** 2026-08-20
**Status:** Draft — ready for engineering review

---

## Table of Contents

1. [Current Model Architecture](#1-current-model-architecture)
2. [Llama Reference Audit](#2-llama-reference-audit)
3. [Nemotron Model Assignments](#3-nemotron-model-assignments)
4. [ModelGateway Design](#4-modelgateway-design)
5. [Migration Steps](#5-migration-steps)
6. [NIM Deployment Targets](#6-nim-deployment-targets)
7. [Definition of Done](#7-definition-of-done)

---

## 1. Current Model Architecture

### 1.1 Models in Active Use

| Role | Model ID | Invocation path | Config source |
|------|----------|-----------------|---------------|
| Primary LLM (all agents) | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | `NIMClient.generate_response()` → `POST /chat/completions` | `LLM_MODEL` env var |
| Guardrails judge | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | `GuardrailsService` → own `httpx` call | `GUARDRAILS_MODEL` env var |
| Document judge (Stage 5) | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | `LargeLLMJudge` → own `httpx.AsyncClient` per request | `LLM_MODEL` env var (runtime), `LLAMA_70B_TIMEOUT` for deadline |
| Document preprocessor fallback | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | `NeMoRetrieverPreprocessor` → own `httpx` call (line 354) | Hardcoded string |
| Embeddings | `nvidia/llama-nemotron-embed-vl-1b-v2` | `NIMClient.generate_embeddings()` → `POST /embeddings` | `EMBEDDING_MODEL` env var |
| Document embeddings (Stage 4) | `llama-nemotron-embed-vl-1b-v2` | `EmbeddingIndexingService` → own `httpx` call | Hardcoded in service (line 45) |
| Document small LLM (Stage 3) | `Llama-Nemotron-Nano-VL-8B` (display name) | `SmallLLMProcessor` → own `httpx.AsyncClient` | `LLAMA_NANO_VL_URL` env var |
| OCR vision fallback | `meta/llama-3.2-11b-vision-instruct` | `NeMoOCRService` → own `httpx` call (line 145) | Hardcoded string |
| Small LLM vision fallback | `meta/llama-3.2-11b-vision-instruct` | `SmallLLMProcessor._call_vision_api()` (line 315) | Hardcoded string |
| Small LLM text fallback | `meta/llama-3.1-8b-instruct` | `SmallLLMProcessor._call_text_api()` (line 248) | Hardcoded string |
| NeMo Parse (OCR) | `nemotron-parse` | `NemotronParseService` → `POST .../models/nemotron-parse/infer` | `NEMO_PARSE_URL` env var |
| NeMo Guardrails config (rails.yaml) | `nvidia/llama-3.3-nemotron-super-49b-v1.5` + `nvidia/llama-nemotron-embed-vl-1b-v2` | NeMo Guardrails SDK (opt-in via `USE_NEMO_GUARDRAILS_SDK=true`) | `data/config/guardrails/rails.yaml` |

### 1.2 Invocation Architecture

All LLM calls flow through one of three paths. **No ChatNVIDIA, LangChain, or openai SDK is used anywhere in the codebase.**

```
Path A — NIMClient (src/api/services/llm/nim_client.py)
  Used by: all five domain agents (equipment, operations, safety, forecasting, document-extraction)
           EmbeddingService, SemanticRouter, GuardrailsService (pattern-based mode)
  Transport: shared httpx.AsyncClient
  Endpoint: POST {LLM_NIM_URL}/chat/completions
            POST {EMBEDDING_NIM_URL}/embeddings

Path B — Per-service httpx.AsyncClient (document pipeline only)
  Used by: SmallLLMProcessor, LargeLLMJudge, NeMoRetrieverPreprocessor, NeMoOCRService,
           NemotronParseService, EmbeddingIndexingService
  Transport: creates a new httpx.AsyncClient per request or per __init__
  Each service has its own auth key env var and URL env var (fragmented configuration)

Path C — NeMo Guardrails SDK (opt-in, disabled by default)
  Activated by: USE_NEMO_GUARDRAILS_SDK=true
  Config: data/config/guardrails/rails.yaml and config.yml
  Transport: NeMo Guardrails SDK reads its own model config
```

**Nemotron-specific conditional logic** (the only model-aware branch in NIMClient):

```python
# src/api/services/llm/nim_client.py lines 402–432
if "nemotron" in self.config.llm_model.lower() and not resolved_enable_thinking:
    request_messages = _ensure_no_think_system_prompt(messages)  # prepends /no_think

if "nemotron" in self.config.llm_model.lower():
    if resolved_enable_thinking:
        payload["reasoning_budget"] = resolved_reasoning_budget
    else:
        payload["chat_template_kwargs"] = {"enable_thinking": False}
```

This string-match on the model name is the exact coupling point that ModelGateway must replace.

### 1.3 Environment Variables Controlling Model Selection

| Variable | Default value | Scope |
|----------|--------------|-------|
| `LLM_MODEL` | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | NIMClient, LargeLLMJudge |
| `EMBEDDING_MODEL` | `nvidia/llama-nemotron-embed-vl-1b-v2` | NIMClient, EmbeddingService |
| `GUARDRAILS_MODEL` | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | GuardrailsConfig |
| `LLAMA_NANO_VL_URL` | `https://integrate.api.nvidia.com/v1` | SmallLLMProcessor endpoint |
| `LLAMA_NANO_VL_API_KEY` | `""` | SmallLLMProcessor auth |
| `LLM_NIM_URL` | `https://integrate.api.nvidia.com/v1` | NIMClient LLM endpoint |
| `EMBEDDING_NIM_URL` | `https://integrate.api.nvidia.com/v1` | NIMClient embedding endpoint |
| `NEMO_PARSE_URL` | `https://integrate.api.nvidia.com/v1` | NemotronParseService endpoint |
| `NEMO_PARSE_API_KEY` | `""` | NemotronParseService auth |
| `LLM_ENABLE_THINKING` | `False` | Nemotron reasoning mode |
| `LLM_REASONING_BUDGET` | `0` | Nemotron chain-of-thought budget |

### 1.4 Timeout and Retry Configuration

**NIMClient retry policy** (`src/api/services/llm/nim_client.py`):

```
max_retries: 3
Backoff: exponential, wait = 2^attempt seconds (1s, 2s, 4s)
Retry on: TimeoutException, asyncio.TimeoutError, HTTP 429, HTTP 5xx
No retry on: HTTP 404, HTTP 401/403, other HTTP 4xx
```

**Timeout stack** (outermost to innermost):

| Layer | Timeout | Variable |
|-------|---------|----------|
| API endpoint (`chat.py`) | 120 / 180 / 230 / 460 s | (complexity × reasoning matrix) |
| LangGraph graph execution | 120 / 180 / 230 / 460 s | Matches API layer |
| Agent `process_query` | 90 / 100 / 180 s | `AGENT_TIMEOUT_SIMPLE/COMPLEX/REASONING` |
| Agent initialization | 10 s | `AGENT_INIT_TIMEOUT` |
| `httpx.AsyncClient` per request | 240 s | `LLM_CLIENT_TIMEOUT` |
| LargeLLMJudge | 120 s | `LLAMA_70B_TIMEOUT` |
| Per-tool MCP execution | 15 s | Hardcoded |
| Guardrails input check | 3 s | Hardcoded |
| Guardrails output check | 5 s | Hardcoded |
| Enhancement operations | 25 s each | Hardcoded |

---

## 2. Llama Reference Audit

Every reference to a Llama model string, env var, or naming artifact in the repository (excluding `env/` virtualenv tree which contains third-party package examples):

| File | Line(s) | Reference | Category | Runtime impact |
|------|---------|-----------|----------|----------------|
| `src/api/services/llm/nim_client.py` | 104 | `nvidia/llama-3.3-nemotron-super-49b-v1.5` (default for `LLM_MODEL`) | **runtime** | Determines every agent LLM call when env var is unset |
| `src/api/services/llm/nim_client.py` | 105 | `nvidia/llama-nemotron-embed-vl-1b-v2` (default for `EMBEDDING_MODEL`) | **runtime** | Determines every embedding call when env var is unset |
| `src/api/services/llm/nim_client.py` | 402, 422 | `"nemotron" in model.lower()` branch | **runtime** | Controls `/no_think` injection and `reasoning_budget`; model-name coupling |
| `src/api/services/guardrails/guardrails_service.py` | 62 | `nvidia/llama-3.3-nemotron-super-49b-v1.5` (default for `GUARDRAILS_MODEL`) | **runtime** | Guardrails judge model when env var is unset |
| `src/api/services/guardrails/guardrails_service.py` | 217 | Comment: `Model: nvidia/llama-3.3-nemotron-super-49b-v1.5` | documentation | None |
| `src/api/agents/document/validation/large_llm_judge.py` | 65 | `nvidia/llama-3.3-nemotron-super-49b-v1.5` (default for `LLM_MODEL`) | **runtime** | Document Stage 5 judge model |
| `src/api/agents/document/validation/large_llm_judge.py` | 67–69 | `LLAMA_70B_TIMEOUT` env var (legacy name) | **runtime** | Timeout for the judge call; confusingly named |
| `src/api/agents/document/validation/large_llm_judge.py` | 260 | `LLAMA_70B_TIMEOUT` in error message | **runtime** | Surface error text seen by operators |
| `src/api/agents/document/preprocessing/nemo_retriever.py` | 354 | `nvidia/llama-3.3-nemotron-super-49b-v1.5` (hardcoded fallback) | **runtime** | Page element detection fallback; not env-configurable |
| `src/api/agents/document/processing/small_llm_processor.py` | 49 | `LLAMA_NANO_VL_API_KEY` env var | **runtime** | Auth for Nano VL endpoint |
| `src/api/agents/document/processing/small_llm_processor.py` | 51 | `LLAMA_NANO_VL_URL` env var | **runtime** | Endpoint URL for Nano VL |
| `src/api/agents/document/processing/small_llm_processor.py` | 65 | `LLAMA_NANO_VL_API_KEY not found` warning | **runtime** | Log message at startup |
| `src/api/agents/document/processing/small_llm_processor.py` | 131, 395, 426 | `"Llama-Nemotron-Nano-VL-8B"` string in `model_used` field | **runtime** | Written to `extraction_results.model_used` in Postgres |
| `src/api/agents/document/processing/small_llm_processor.py` | 248 | `meta/llama-3.1-8b-instruct` (hardcoded text-only fallback) | **runtime** | Called when vision model fails; not env-configurable |
| `src/api/agents/document/processing/small_llm_processor.py` | 315 | `meta/llama-3.2-11b-vision-instruct` (hardcoded vision fallback) | **runtime** | Called on multimodal failure; not env-configurable |
| `src/api/agents/document/processing/small_llm_processor.py` | 17, 38, 87, 98 | `Llama Nemotron Nano VL 8B` in docstrings / logs | documentation | None |
| `src/api/agents/document/processing/embedding_indexing.py` | 17, 45, 184 | `llama-nemotron-embed-vl-1b-v2` in docstrings | documentation | None |
| `src/api/agents/document/ocr/nemo_ocr.py` | 145 | `meta/llama-3.2-11b-vision-instruct` (hardcoded OCR vision fallback) | **runtime** | Called when NeMo OCR service is unavailable |
| `src/api/agents/document/action_tools.py` | 48 | `MODEL_SMALL_LLM = "Llama Nemotron Nano VL 8B"` | **runtime** | Class constant — written to responses and logs; tested in unit tests |
| `src/api/agents/document/action_tools.py` | 49 | `MODEL_LARGE_JUDGE = "Llama 3.3 Nemotron Super 49B"` | **runtime** | Class constant — same as above |
| `src/api/agents/document/action_tools.py` | 560–562, 1162, 1547 | Pipeline stage label strings | documentation | Appear in `ChatResponse` `quick_actions` strings |
| `src/api/agents/document/document_extraction_agent.py` | 79–81, 207, 237 | Docstring and comment references | documentation | None |
| `src/api/agents/document/mcp_document_agent.py` | 338–340 | Pipeline stage label strings | documentation | Appear in MCP tool results |
| `src/retrieval/vector/embedding_service.py` | 37, 45 | `nvidia/llama-nemotron-embed-vl-1b-v2` (default value and docstring) | **runtime** | Controls embedding calls when `EMBEDDING_MODEL` unset |
| `src/retrieval/vector/milvus_retriever.py` | 44 | Comment: `# llama-nemotron-embed-vl-1b-v2` (dimension comment) | legacy-artifact | None — comment only |
| `src/retrieval/vector/gpu_milvus_retriever.py` | 44 | Same dimension comment | legacy-artifact | None — comment only |
| `data/config/guardrails/rails.yaml` | 7, 15 | `nvidia/llama-3.3-nemotron-super-49b-v1.5` and `nvidia/llama-nemotron-embed-vl-1b-v2` | configuration | Active when `USE_NEMO_GUARDRAILS_SDK=true` |
| `data/config/guardrails/config.yml` | 13, 23 | Same two models | configuration | Active when NeMo SDK is enabled |
| `tests/unit/test_document_action_tools.py` | 69–70 | Asserts `MODEL_SMALL_LLM == "Llama Nemotron Nano VL 8B"` and `MODEL_LARGE_JUDGE == "Llama 3.3 Nemotron Super 49B"` | test | Tests will fail if constants change without update |
| `tests/unit/test_nvidia_llm.py` | 92, 98, 103 | `LLAMA_NANO_VL_API_KEY` env check, display strings | test | Env var rename will break this check |
| `tests/unit/test_embedding.py` | 34, 83, 89 | `nvidia/llama-nemotron-embed-vl-1b-v2` in print strings | test | No assertion; display-only |
| `tests/unit/test_document_pipeline.py` | 340 | `LLAMA_NANO_VL_API_KEY` in `os.environ` mock | test | Will fail silently if env var is renamed |
| `docs/configuration/LLM_PARAMETERS.md` | 42, 144, 278 | Model names in docs | documentation | None |
| `docs/architecture/adr/002-nvidia-nims-integration.md` | 32–182 | Model names throughout ADR | documentation | None |
| `docs/architecture/diagrams/warehouse-operational-assistant.md` | 67–592 | Model names in Mermaid diagrams and tables | documentation | None |

**Runtime-impact summary:** 18 distinct locations with live runtime impact (model string defaults, env var names, hardcoded fallbacks, class constants written to the database). The remainder are documentation or test artifacts.

---

## 3. Nemotron Model Assignments

### 3.1 Nemotron Tier Reference

| Tier | Role in MAIW | Characteristics |
|------|-------------|-----------------|
| **Nemotron Lightning** | High-volume structured transforms, simple tool use, intent classification | Lowest latency; best for sub-100ms routing decisions |
| **Nemotron Nano** | Moderate reasoning, domain SFT target, multimodal document extraction | Compact; SFT candidate for warehouse-specific entity types |
| **Nemotron Nano Omni** | Multimodal: equipment images, scanned documents, vision OCR | Replaces `meta/llama-3.2-11b-vision-instruct` vision fallbacks |
| **Nemotron Super** | Complex multi-step planning, cross-domain synthesis, recovery scenarios | Current primary model; remains for the hardest reasoning tasks |
| **Nemotron Ultra** | Judge/evaluator, synthetic data generation, SFT teacher | High quality bar; used where correctness > latency |

### 3.2 Workload-to-Model Mapping

| Workload | Current model | Recommended Nemotron | Reasoning |
|----------|--------------|---------------------|-----------|
| Intent classification (`MCPIntentClassifier` keyword + semantic blend) | `nvidia/llama-3.3-nemotron-super-49b-v1.5` via NIMClient | **Nemotron Lightning** | Pure classification; no deep reasoning needed; latency directly impacts P50 chat response. Super is overprovisioned here. |
| Equipment query parsing (`_parse_equipment_query` complex branch) | Super 49B | **Nemotron Nano** | Structured extraction from a constrained domain vocabulary. Nano is SFT target once trajectory store is active. |
| Equipment response generation (`_generate_response_with_tools`, temp 0.0, 2000 tokens) | Super 49B | **Nemotron Super** | Multi-tool result synthesis with citation; needs depth. Keep Super for now; migrate to fine-tuned Nano in Phase 3. |
| Equipment recommendations (temp 0.3, 500 tokens) | Super 49B | **Nemotron Nano** | Short, formulaic recommendation text from structured data. Nano is appropriate. |
| Operations task management (pick/pack/putaway/cycle\_count queries) | Super 49B | **Nemotron Nano** | Domain-constrained; task types are closed set. High call volume — Nano reduces cost. |
| Safety incident assessment and policy lookup | Super 49B | **Nemotron Super** | Safety decisions must not be under-resourced. Super stays; Ultra as evaluator in offline checks. |
| Safety compliance synthesis | Super 49B | **Nemotron Super** | Regulatory risk. No downgrade until SFT validated. |
| Demand forecast interpretation (forecasting agent NL generation) | Super 49B | **Nemotron Nano** | Narrating tabular forecast data in natural language. Nano handles this well; matches volume of batch forecast calls. |
| Forecasting multi-step scenario planning | Super 49B | **Nemotron Super** | Multi-horizon reasoning with confidence interval analysis needs depth. |
| Document entity extraction — Stage 3 (small LLM) | `Llama-Nemotron-Nano-VL-8B` | **Nemotron Nano Omni** | Multimodal (invoice images, scanned BOLs). Nano Omni is the direct successor. Replaces hardcoded fallbacks for vision too. |
| Document quality judge — Stage 5 (large judge) | Super 49B (via `LargeLLMJudge`) | **Nemotron Ultra** | Quality scoring is an evaluation task. Ultra is the judge-class model; higher precision on low-confidence documents. |
| Document preprocessor page element detection (fallback) | Super 49B (hardcoded line 354) | **Nemotron Nano** | Layout detection is pattern recognition; Nano is sufficient. Removes the only fully hardcoded model string. |
| OCR vision fallback (NeMoOCRService) | `meta/llama-3.2-11b-vision-instruct` | **Nemotron Nano Omni** | Eliminates the one remaining Meta model in the runtime path. |
| Vision fallback in SmallLLMProcessor | `meta/llama-3.2-11b-vision-instruct` | **Nemotron Nano Omni** | Same rationale; unified into Nano Omni endpoint. |
| Text-only fallback in SmallLLMProcessor | `meta/llama-3.1-8b-instruct` | **Nemotron Nano** | Consolidate all text fallbacks to Nano; eliminates second Meta runtime dependency. |
| Semantic routing embedding | `nvidia/llama-nemotron-embed-vl-1b-v2` (2048-dim) | **Nemotron Nano Omni embedding** (or current model retained) | Current model is already Nemotron-family; retain unless a higher-accuracy embedding model ships. No action in Phase 1. |
| Guardrails input/output safety | Super 49B (opt-in via NeMo SDK) | **Nemotron Lightning** (input) + **Nemotron Nano** (output) | Input safety is high-volume and latency-critical (3s budget). Lightning fits. Output check has more room (5s); Nano provides better semantic understanding than pattern matching. |
| Multi-domain ambiguous intent synthesis (`_mcp_synthesize_response`) | Super 49B | **Nemotron Super** | Final synthesis of multi-agent results; quality matters. Keep Super. |
| Trajectory evaluation (future, post Phase 3) | None today | **Nemotron Ultra** | Offline judge for SFT data quality and regression evaluation. |

---

## 4. ModelGateway Design

The ModelGateway is a thin synchronous/async dispatch layer that sits between agent code and httpx transport. It replaces the current `if "nemotron" in model.lower()` branch, the fragmented per-service clients, and the scattered environment variable reads.

### 4.1 ModelRequest Fields

```python
@dataclass
class ModelRequest:
    # Required
    messages: List[dict]              # OpenAI-format message dicts
    workload: str                     # Logical workload label (see WorkloadKind enum)
    session_id: str                   # For telemetry grouping

    # Optional overrides (agents may set these; gateway respects them if within policy)
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    top_p: Optional[float] = None
    stream: bool = False

    # Reasoning control (replaces LLM_ENABLE_THINKING / LLM_REASONING_BUDGET)
    enable_reasoning: bool = False
    reasoning_budget: Optional[int] = None  # tokens; None = model default

    # Multimodal
    images: Optional[List[bytes]] = None    # raw bytes; gateway encodes to base64

    # Context for routing telemetry
    agent_name: Optional[str] = None
    request_id: Optional[str] = None       # UUID; used for deduplication
    priority: int = 5                       # 1 (highest) – 10 (lowest); affects queue
```

**WorkloadKind enum** (maps directly to Section 3.2 workload rows):

```
INTENT_CLASSIFICATION
ENTITY_EXTRACTION
RESPONSE_GENERATION
RECOMMENDATION_GENERATION
OPERATIONS_QUERY
SAFETY_ASSESSMENT
SAFETY_SYNTHESIS
FORECAST_NARRATION
FORECAST_PLANNING
DOCUMENT_EXTRACTION_SMALL
DOCUMENT_JUDGE
DOCUMENT_LAYOUT_DETECTION
VISION_FALLBACK
EMBEDDING
GUARDRAILS_INPUT
GUARDRAILS_OUTPUT
SYNTHESIS
EVALUATION          # offline only
```

### 4.2 ModelResponse Fields

```python
@dataclass
class ModelResponse:
    content: str                       # Final text
    model_id: str                      # Actual model called (for observability)
    model_tier: str                    # Lightning / Nano / NanoOmni / Super / Ultra
    workload: str                      # Echo of request workload
    latency_ms: float                  # Wall-clock time for the LLM call
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    reasoning_tokens: Optional[int]    # Non-null when enable_reasoning=True
    cache_hit: bool                    # True if served from NIMClient response cache
    fallback_used: bool                # True if primary model was unavailable
    fallback_model_id: Optional[str]
    request_id: Optional[str]         # Echo of request request_id
    finish_reason: str                 # stop / length / content_filter
```

### 4.3 Routing Policy (First Deterministic Version)

The routing table is static configuration; no ML-based routing in Phase 1. A `RoutingRule` maps a `WorkloadKind` to a `ModelTier` plus model ID and per-rule parameter overrides.

```python
ROUTING_TABLE: Dict[WorkloadKind, RoutingRule] = {
    WorkloadKind.INTENT_CLASSIFICATION:        RoutingRule(tier="lightning",  model=NEMOTRON_LIGHTNING, max_tokens=64,   temperature=0.0),
    WorkloadKind.ENTITY_EXTRACTION:            RoutingRule(tier="nano",       model=NEMOTRON_NANO,     max_tokens=512,  temperature=0.0),
    WorkloadKind.RESPONSE_GENERATION:          RoutingRule(tier="super",      model=NEMOTRON_SUPER,    max_tokens=2000, temperature=0.0),
    WorkloadKind.RECOMMENDATION_GENERATION:    RoutingRule(tier="nano",       model=NEMOTRON_NANO,     max_tokens=500,  temperature=0.3),
    WorkloadKind.OPERATIONS_QUERY:             RoutingRule(tier="nano",       model=NEMOTRON_NANO,     max_tokens=1000, temperature=0.1),
    WorkloadKind.SAFETY_ASSESSMENT:            RoutingRule(tier="super",      model=NEMOTRON_SUPER,    max_tokens=2000, temperature=0.1),
    WorkloadKind.SAFETY_SYNTHESIS:             RoutingRule(tier="super",      model=NEMOTRON_SUPER,    max_tokens=2000, temperature=0.1),
    WorkloadKind.FORECAST_NARRATION:           RoutingRule(tier="nano",       model=NEMOTRON_NANO,     max_tokens=800,  temperature=0.2),
    WorkloadKind.FORECAST_PLANNING:            RoutingRule(tier="super",      model=NEMOTRON_SUPER,    max_tokens=2000, temperature=0.1),
    WorkloadKind.DOCUMENT_EXTRACTION_SMALL:    RoutingRule(tier="nano_omni",  model=NEMOTRON_NANO_OMNI, max_tokens=1500, temperature=0.0),
    WorkloadKind.DOCUMENT_JUDGE:               RoutingRule(tier="ultra",      model=NEMOTRON_ULTRA,    max_tokens=2000, temperature=0.0),
    WorkloadKind.DOCUMENT_LAYOUT_DETECTION:    RoutingRule(tier="nano",       model=NEMOTRON_NANO,     max_tokens=512,  temperature=0.0),
    WorkloadKind.VISION_FALLBACK:              RoutingRule(tier="nano_omni",  model=NEMOTRON_NANO_OMNI, max_tokens=1000, temperature=0.0),
    WorkloadKind.EMBEDDING:                    RoutingRule(tier="embed",      model=NEMOTRON_EMBED,    max_tokens=None, temperature=None),
    WorkloadKind.GUARDRAILS_INPUT:             RoutingRule(tier="lightning",  model=NEMOTRON_LIGHTNING, max_tokens=32,  temperature=0.0),
    WorkloadKind.GUARDRAILS_OUTPUT:            RoutingRule(tier="nano",       model=NEMOTRON_NANO,     max_tokens=64,   temperature=0.0),
    WorkloadKind.SYNTHESIS:                    RoutingRule(tier="super",      model=NEMOTRON_SUPER,    max_tokens=2000, temperature=0.1),
    WorkloadKind.EVALUATION:                   RoutingRule(tier="ultra",      model=NEMOTRON_ULTRA,    max_tokens=2000, temperature=0.0),
}
```

**Override priority** (highest to lowest):
1. `ModelRequest.temperature` / `max_tokens` (explicit agent override)
2. `RoutingRule` defaults for the workload
3. `NIMConfig` global defaults (from env vars)

**Reasoning budget injection** is handled inside ModelGateway based on `ModelRequest.enable_reasoning` and `ModelRequest.reasoning_budget`, not by a string check on the model name. The `chat_template_kwargs` and `reasoning_budget` fields are injected by the gateway for any Nemotron-family model that supports them, controlled by a per-`RoutingRule` `supports_thinking: bool` flag.

### 4.4 Routing Telemetry Schema

Every gateway call emits one `RoutingTelemetryRecord` to the `performance_metrics` TimescaleDB hypertable (which already exists from `003_timescale_hypertables.sql`):

```python
@dataclass
class RoutingTelemetryRecord:
    timestamp: datetime              # Written to TimescaleDB performance_metrics
    service_name: str = "model_gateway"
    metric_name: str = "routing_decision"
    metric_value: float              # latency_ms
    unit: str = "ms"
    tags: dict = field(default_factory=lambda: {
        "workload":       str,       # WorkloadKind value
        "model_tier":     str,       # lightning / nano / nano_omni / super / ultra
        "model_id":       str,       # exact model string called
        "agent_name":     str,
        "session_id":     str,
        "cache_hit":      bool,
        "fallback_used":  bool,
        "finish_reason":  str,
        "prompt_tokens":  int,
        "completion_tokens": int,
        "reasoning_tokens": int,
        "request_id":     str,
    })
```

This enables per-workload latency dashboards and per-tier token cost accounting without any additional infrastructure.

### 4.5 Fallback and Escalation Rules

```
Primary failure → retry with same model (existing NIMClient retry: 3 attempts, exponential backoff)
After 3 retries fail:
  If tier == ultra    → escalate? No. Ultra failures surface to caller with status=degraded.
  If tier == super    → fallback to ultra (higher quality, not lower; avoids silent quality drop)
  If tier == nano     → fallback to super (preserve quality for user-facing response)
  If tier == nano_omni → fallback to nano (text-only path; vision content stripped)
  If tier == lightning → fallback to nano (acceptable latency increase)
  If tier == embed    → no fallback; raise immediately (vector index is unusable without embeddings)

HTTP 429 (rate limit):
  Back off with jitter: base_delay = min(60, 2^attempt) * random(0.5, 1.5)
  After 3 rate-limit retries: return ModelResponse with finish_reason="rate_limited" and surface to agent

Guardrails timeout (3s input / 5s output):
  Do not retry. Fail open with a log event tagged severity=warning.
  The existing pattern-based guardrails remain as the timeout fallback.
```

---

## 5. Migration Steps

### Phase 1 — ModelGateway Interface + Nemotron Provider (2–3 weeks)

**Goal:** Ship ModelGateway without changing any agent behavior. Existing `NIMClient` wraps ModelGateway internally; agents are unaware.

**Step 1.1 — Create `src/api/services/llm/model_gateway.py`**
- Implement `WorkloadKind` enum, `ModelRequest`, `ModelResponse`, `RoutingRule`, `ROUTING_TABLE`.
- Add `ModelGateway.complete(request: ModelRequest) -> ModelResponse` method.
- Move Nemotron-specific payload logic (`chat_template_kwargs`, `reasoning_budget`, `/no_think` injection) from `NIMClient.generate_response()` (lines 402–432) into `ModelGateway._build_payload()`. The `if "nemotron" in model.lower()` branch is deleted here.
- `ModelGateway` wraps the existing shared `httpx.AsyncClient`; no new transport.

**Step 1.2 — Add `src/api/services/llm/model_gateway_config.py`**
- Consolidate all model endpoint env vars into a single `ModelGatewayConfig` dataclass (see Section 6 for the new env var names).
- `NIMConfig` in `nim_client.py` reads from `ModelGatewayConfig` so both coexist during the transition.

**Step 1.3 — Wire ModelGateway as NIMClient backend**
- In `NIMClient.generate_response()`, call `model_gateway.complete(ModelRequest(workload=WorkloadKind.RESPONSE_GENERATION, ...))` and unpack `ModelResponse`.
- Behavior is identical to today. This is a zero-risk refactor step.

**Step 1.4 — Add routing telemetry**
- On each `ModelGateway.complete()` call, emit `RoutingTelemetryRecord` to `performance_metrics` table (async, fire-and-forget; never blocks the response path).
- Add a `GET /api/v1/model-gateway/stats` endpoint that queries the `performance_metrics` table for per-workload latency and token usage.

**Step 1.5 — Update env vars (backward-compatible)**
- Add new Nemotron-tier env vars (Section 6) alongside existing `LLM_MODEL`, `EMBEDDING_MODEL` etc.
- `ModelGatewayConfig` reads new vars first; falls back to legacy vars.
- No deployment configuration changes required in Phase 1.

**Acceptance criteria for Phase 1:**
- All existing integration tests pass without modification.
- `GET /api/v1/model-gateway/stats` returns per-workload latency data.
- Zero regression in `POST /api/v1/chat` P99 latency.

---

### Phase 2 — Migrate Agents One by One (4–6 weeks)

Each agent migration follows the same pattern: the agent calls `model_gateway.complete(ModelRequest(workload=<specific_kind>, ...))` directly instead of `nim_client.generate_response(...)`. The `workload` field provides the routing context; the gateway selects the right Nemotron tier.

**Migration order** (lowest risk first):

| Step | Agent / Component | Workloads touched | Risk | Notes |
|------|------------------|------------------|------|-------|
| 2.1 | `EquipmentAssetOperationsAgent.process_query` — intent parse branch | `INTENT_CLASSIFICATION`, `ENTITY_EXTRACTION` | Low | Fast keyword path already bypasses LLM; LLM path is the only change |
| 2.2 | `MCPEquipmentAssetOperationsAgent._generate_response_with_tools` second and third calls (temp 0.4 / temp 0.3) | `RECOMMENDATION_GENERATION` | Low | Small output; easy to compare |
| 2.3 | `ForecastingAgent` NL generation | `FORECAST_NARRATION` | Low | Narrates pre-computed numbers; correctness is easy to spot-check |
| 2.4 | `OperationsCoordinationAgent.process_query` | `OPERATIONS_QUERY` | Medium | Task assignment logic; regression tests should cover |
| 2.5 | `SmallLLMProcessor` (Stage 3 document extraction) | `DOCUMENT_EXTRACTION_SMALL`, `VISION_FALLBACK` | Medium | Switches to Nano Omni; must validate against held-out invoice set. Removes `LLAMA_NANO_VL_API_KEY` / `LLAMA_NANO_VL_URL` dependency and both hardcoded `meta/` fallback strings |
| 2.6 | `NeMoOCRService` vision fallback | `VISION_FALLBACK` | Medium | Removes second `meta/llama-3.2-11b-vision-instruct` reference |
| 2.7 | `NeMoRetrieverPreprocessor` hardcoded fallback (line 354) | `DOCUMENT_LAYOUT_DETECTION` | Medium | Only hardcoded model string with no env var override; requires code change, not just config |
| 2.8 | `MCPEquipmentAssetOperationsAgent._generate_response_with_tools` primary call (temp 0.0, 2000 tokens) | `RESPONSE_GENERATION` | Medium-High | Primary equipment response; needs A/B comparison before cutover |
| 2.9 | `GuardrailsService` | `GUARDRAILS_INPUT`, `GUARDRAILS_OUTPUT` | Medium-High | Safety path; requires careful regression testing. Nemotron Lightning for input (latency critical); Nano for output |
| 2.10 | `SafetyAgent.process_query` | `SAFETY_ASSESSMENT`, `SAFETY_SYNTHESIS` | High | Safety decisions; requires human review of model outputs in staging before production cutover |
| 2.11 | `LargeLLMJudge` (Stage 5 document judge) | `DOCUMENT_JUDGE` | High | Switches from Super to Ultra; quality should improve but Ultra's latency budget must be confirmed against the 120s (`LLAMA_70B_TIMEOUT`) deadline |
| 2.12 | `MCPPlannerGraph._mcp_synthesize_response` | `SYNTHESIS` | High | Final synthesis; affects every chat response. Do last |
| 2.13 | `ForecastingAgent` multi-step scenario planning | `FORECAST_PLANNING` | Medium | Migrate after narration is stable |

**For each step in Phase 2:**
1. Add `workload` parameter to the relevant method signature.
2. Replace the `nim_client.generate_response(...)` or direct `httpx` call with `model_gateway.complete(ModelRequest(workload=..., ...))`.
3. Update unit test mocks to mock `ModelGateway.complete` instead of `NIMClient.generate_response`.
4. Run the existing integration test suite. Compare response quality on the 38-SKU demand dataset and the sample document set in `data/uploads/`.
5. Deploy to staging with traffic shadowing for 24 hours before production.

**Parallel work during Phase 2:**
- Rename `LLAMA_70B_TIMEOUT` → `NEMOTRON_JUDGE_TIMEOUT` in `LargeLLMJudge` (line 69) and in the error message (line 260). Keep backward-compat alias.
- Rename `LLAMA_NANO_VL_API_KEY` → `NEMOTRON_NANO_OMNI_API_KEY` and `LLAMA_NANO_VL_URL` → `NEMOTRON_NANO_OMNI_URL`.
- Update `action_tools.py` constants: `MODEL_SMALL_LLM = "Nemotron-Nano-Omni"`, `MODEL_LARGE_JUDGE = "Nemotron-Ultra"`. Update tests in `test_document_action_tools.py` lines 69–70.
- Update the `extraction_results.model_used` string written to Postgres (currently `"Llama-Nemotron-Nano-VL-8B"`) to reflect actual model ID returned in `ModelResponse.model_id`.

---

### Phase 3 — Remove Direct Model Imports and Legacy Artifacts (2 weeks)

**Step 3.1 — Delete `LLM_MODEL` as the sole model selection variable**
- After all agents use ModelGateway, `LLM_MODEL` no longer controls agent routing.
- Retain `LLM_MODEL` as a `ROUTING_TABLE` override mechanism: if `LLM_MODEL` is set, it overrides the `NEMOTRON_SUPER_MODEL` env var only (for operators who prefer explicit control).
- Remove all `os.getenv("LLM_MODEL", "nvidia/llama-3.3-nemotron-super-49b-v1.5")` calls from `nim_client.py` line 104, `large_llm_judge.py` line 65.

**Step 3.2 — Remove per-service httpx clients**
- `LargeLLMJudge`: remove the per-request `httpx.AsyncClient` instantiation. The judge calls `model_gateway.complete(ModelRequest(workload=DOCUMENT_JUDGE))`.
- `NeMoRetrieverPreprocessor`: replace the direct `httpx` call at line 354 with a ModelGateway call.
- `NeMoOCRService`: replace the direct `httpx` call for the vision fallback.
- `EmbeddingIndexingService`: route through `ModelGateway` for the Stage 4 embedding call (currently a separate client with hardcoded model string at line 45).
- `SmallLLMProcessor`: the entire `_call_text_api` and `_call_vision_api` methods are replaced by a single `model_gateway.complete(ModelRequest(workload=DOCUMENT_EXTRACTION_SMALL, images=[...]))`.

**Step 3.3 — Update guardrails configuration**
- Update `data/config/guardrails/rails.yaml` and `config.yml` model references to new Nemotron model IDs.
- Remove `meta/llama-3.3-70b-instruct` from any NeMo SDK example configs that have been copied in.

**Step 3.4 — Clean up legacy env vars**
- Remove `LLAMA_NANO_VL_API_KEY`, `LLAMA_NANO_VL_URL`, `LLAMA_70B_TIMEOUT` from all source files.
- Add deprecation warnings (one release cycle) before removing from deployment documentation.

**Step 3.5 — Update dimension constants**
- Update comments in `milvus_retriever.py` line 44 and `gpu_milvus_retriever.py` line 44 to reflect the current embedding model name.
- Confirm `EMBEDDING_DIMENSION=2048` is still correct for the target embedding model; adjust if the Nano Omni embedding model uses a different dimension.

**Step 3.6 — Documentation**
- Update `docs/architecture/adr/002-nvidia-nims-integration.md` to reflect the ModelGateway architecture and new model assignments.
- Update `docs/configuration/LLM_PARAMETERS.md` to document the new env var names and remove the legacy ones.
- Update Mermaid diagrams in `docs/architecture/diagrams/warehouse-operational-assistant.md` to reflect Nemotron tier names.

---

## 6. NIM Deployment Targets

### 6.1 Required NIM Endpoints

| NIM | Model ID | New env var name | Legacy env var (removed in Phase 3) | Endpoint path |
|-----|----------|------------------|------------------------------------|--------------|
| Nemotron Lightning | `nvidia/nemotron-x-lightning` | `NEMOTRON_LIGHTNING_URL` + `NEMOTRON_LIGHTNING_API_KEY` | None (new) | `/chat/completions` |
| Nemotron Nano | `nvidia/nemotron-x-nano` | `NEMOTRON_NANO_URL` + `NEMOTRON_NANO_API_KEY` | None (new) | `/chat/completions` |
| Nemotron Nano Omni | `nvidia/nemotron-x-nano-omni` | `NEMOTRON_NANO_OMNI_URL` + `NEMOTRON_NANO_OMNI_API_KEY` | `LLAMA_NANO_VL_URL`, `LLAMA_NANO_VL_API_KEY` | `/chat/completions` (multimodal) |
| Nemotron Super | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | `NEMOTRON_SUPER_URL` + `NEMOTRON_SUPER_API_KEY` | `LLM_NIM_URL`, `NVIDIA_API_KEY` | `/chat/completions` |
| Nemotron Ultra | `nvidia/llama-3.1-nemotron-ultra-253b-v1` | `NEMOTRON_ULTRA_URL` + `NEMOTRON_ULTRA_API_KEY` | None (new) | `/chat/completions` |
| Nemotron Embed | `nvidia/llama-nemotron-embed-vl-1b-v2` (retain or upgrade) | `NEMOTRON_EMBED_URL` + `NEMOTRON_EMBED_API_KEY` | `EMBEDDING_NIM_URL`, `EMBEDDING_API_KEY` | `/embeddings` |
| Nemotron Parse (OCR) | `nemotron-parse` | `NEMO_PARSE_URL` + `NEMO_PARSE_API_KEY` | Same (no rename needed) | `/models/nemotron-parse/infer` |

**Note on model IDs:** Exact model IDs for Lightning, Nano, and Nano Omni should be confirmed against `https://integrate.api.nvidia.com/v1/models` at the time of Phase 1 implementation. The names used above (`nvidia/nemotron-x-*`) are placeholders. The Super model ID is already deployed and confirmed.

### 6.2 Deployment Configuration Matrix

| Tier | Recommended deployment | GPU requirement | Concurrent request target |
|------|----------------------|-----------------|--------------------------|
| Lightning | `integrate.api.nvidia.com` (cloud) or single-GPU NIM | 1x A100/H100 | High (intent classification bottleneck) |
| Nano | Cloud API or 1x A100/H100 NIM | 1x A100/H100 | Medium-High |
| Nano Omni | Cloud API or 1x A100/H100 NIM | 1x A100/H100 (vision requires VRAM) | Medium |
| Super | Cloud API or 2x H100 NIM | 2x H100 | Medium (existing deployment) |
| Ultra | Cloud API only in Phase 1–2; self-hosted in Phase 3 | 4–8x H100 | Low (judge calls are infrequent) |
| Embed | Cloud API or 1x A100/H100 NIM | 1x A100/H100 | High (every RAG retrieval) |

### 6.3 Complete New Environment Variable Set

```bash
# Nemotron tier endpoints
NEMOTRON_LIGHTNING_URL=https://integrate.api.nvidia.com/v1
NEMOTRON_LIGHTNING_API_KEY=<key>
NEMOTRON_NANO_URL=https://integrate.api.nvidia.com/v1
NEMOTRON_NANO_API_KEY=<key>
NEMOTRON_NANO_OMNI_URL=https://integrate.api.nvidia.com/v1
NEMOTRON_NANO_OMNI_API_KEY=<key>
NEMOTRON_SUPER_URL=https://integrate.api.nvidia.com/v1
NEMOTRON_SUPER_API_KEY=<key>
NEMOTRON_ULTRA_URL=https://integrate.api.nvidia.com/v1
NEMOTRON_ULTRA_API_KEY=<key>
NEMOTRON_EMBED_URL=https://integrate.api.nvidia.com/v1
NEMOTRON_EMBED_API_KEY=<key>

# ModelGateway behavior
MODEL_GATEWAY_TELEMETRY_ENABLED=true
MODEL_GATEWAY_FALLBACK_ENABLED=true
MODEL_GATEWAY_CACHE_TTL_SECONDS=300

# Reasoning (replaces LLM_ENABLE_THINKING / LLM_REASONING_BUDGET)
NEMOTRON_ENABLE_THINKING=false
NEMOTRON_REASONING_BUDGET=0

# Judge timeout (replaces LLAMA_70B_TIMEOUT)
NEMOTRON_JUDGE_TIMEOUT=120

# Embedding dimension (unchanged)
EMBEDDING_DIMENSION=2048

# NeMo Parse (unchanged)
NEMO_PARSE_URL=https://integrate.api.nvidia.com/v1
NEMO_PARSE_API_KEY=<key>

# Legacy aliases (backward compat, deprecated in Phase 3)
# LLM_MODEL              → maps to NEMOTRON_SUPER_URL model override
# EMBEDDING_MODEL        → maps to NEMOTRON_EMBED_URL model override
# LLAMA_NANO_VL_API_KEY  → alias for NEMOTRON_NANO_OMNI_API_KEY
# LLAMA_NANO_VL_URL      → alias for NEMOTRON_NANO_OMNI_URL
# LLAMA_70B_TIMEOUT      → alias for NEMOTRON_JUDGE_TIMEOUT
```

---

## 7. Definition of Done

"Nemotron-native, ModelGateway-routed" is complete when all of the following criteria pass:

### Code criteria

- [ ] `src/api/services/llm/model_gateway.py` exists with `ModelGateway`, `ModelRequest`, `ModelResponse`, `WorkloadKind`, and `ROUTING_TABLE` as specified in Section 4.
- [ ] The string `"nemotron" in` does not appear anywhere in `src/` as a model-selection branch (the `nim_client.py` lines 402–432 conditional is deleted).
- [ ] `meta/llama-3.1-8b-instruct` does not appear in any `src/` Python file (replaced by Nano or Nano Omni).
- [ ] `meta/llama-3.2-11b-vision-instruct` does not appear in any `src/` Python file (replaced by Nano Omni).
- [ ] `LLAMA_NANO_VL_API_KEY`, `LLAMA_NANO_VL_URL`, and `LLAMA_70B_TIMEOUT` do not appear as `os.getenv` calls in any `src/` file (legacy aliases may exist in `ModelGatewayConfig` for backward compatibility, clearly marked as deprecated).
- [ ] Every `httpx.AsyncClient` used for LLM inference in `src/api/agents/document/` has been replaced by a `ModelGateway.complete()` call. The only remaining `httpx.AsyncClient` instances are the two shared clients inside `NIMClient.__init__()` (which ModelGateway wraps) and the Nemotron Parse client (separate OCR service, not a language model).
- [ ] `action_tools.py` constants `MODEL_SMALL_LLM` and `MODEL_LARGE_JUDGE` reflect actual Nemotron model IDs, and the unit tests in `test_document_action_tools.py` assert against these new values.
- [ ] `data/config/guardrails/rails.yaml` and `config.yml` reference only Nemotron model IDs (no `meta/` models).

### Observability criteria

- [ ] `GET /api/v1/model-gateway/stats` returns per-workload latency percentiles (P50/P95/P99) and per-tier token consumption.
- [ ] `performance_metrics` TimescaleDB table contains `routing_decision` records for at least 100 real production requests, with non-null `model_tier` and `workload` tag values.
- [ ] Alerts exist for: per-workload P99 latency exceeding tier-appropriate thresholds (Lightning >200ms, Nano >2s, Super >15s, Ultra >30s); fallback rate exceeding 1% per workload over a 5-minute window.

### Quality criteria

- [ ] All 38-SKU demand forecast narrations pass a spot-check evaluation against held-out ground truth (Nano replacing Super for `FORECAST_NARRATION`).
- [ ] Document extraction on the 20+ sample PDFs in `data/uploads/` produces `quality_scores.overall_score >= 3.5` (same threshold as pre-migration baseline).
- [ ] Safety agent responses on the existing integration test suite show no regressions (Super retained; baseline is identical).
- [ ] `POST /api/v1/chat` P99 latency on simple inventory queries (`INTENT_CLASSIFICATION` → `OPERATIONS_QUERY` path) decreases by at least 20% versus the pre-migration baseline, owing to Lightning replacing Super for intent classification.

### Deployment criteria

- [ ] All new `NEMOTRON_*` env vars are documented in `docs/configuration/LLM_PARAMETERS.md` with their defaults, valid values, and which agent paths they affect.
- [ ] Legacy env vars (`LLAMA_NANO_VL_API_KEY`, `LLAMA_70B_TIMEOUT`, `LLM_MODEL`, `EMBEDDING_MODEL`) produce a `DeprecationWarning` log line at startup when detected, with the replacement var name.
- [ ] `docker-compose.yml` (or equivalent deployment manifest) references only `NEMOTRON_*` and `NEMO_PARSE_*` vars; no `LLAMA_*` vars appear in deployment configs.
- [ ] The trajectory store (per the target architecture) records at least the `model_id`, `model_tier`, `workload`, `latency_ms`, and `token_counts` fields from `ModelResponse` for every request processed after Phase 2 cutover.
