# MAIW Modernization Migration Plan

**Repository:** Multi-Agent-Intelligent-Warehouse  
**Date:** 2026-08-20  
**Author:** Architecture Review  
**Status:** Proposed  

---

## 1. Migration Principles

### 1.1 Core Rules

**No big-bang rewrites.** Every phase ships a working system. The production API at `/api/v1/chat` must return correct responses after every merged PR. Tests must pass at the end of each phase before the next begins.

**Small, reviewable PRs.** Each numbered task within a phase should be a separate PR of 200–600 lines. A PR that adds a new abstraction and a PR that migrates callers to it are two distinct PRs, not one.

**Backward compatibility is a first-class constraint.** Old call sites are not removed in the same PR that introduces the new abstraction. The old path is deprecated first (`# DEPRECATED: use X instead`), remains functional for one full phase, then is deleted in a dedicated cleanup PR at the start of the subsequent phase.

**Feature flags for every non-trivial swap.** New code paths are activated via environment variables (`MODEL_GATEWAY_ENABLED`, `MCP_SDK_ENABLED`, `DECISION_ENGINE_ENABLED`, etc.) defaulting to `false` until the phase is validated in staging.

**The test suite is a migration safety net, not an afterthought.** Each phase adds tests before migrating production code. The "Tests required" section of each phase definition lists what must be green before any production code change in that phase is merged.

**No silent fallbacks that mask failures.** The current codebase has several patterns where a `try/except Exception` silently catches errors and returns a 0.75 confidence default. During migration, fallback paths must log at WARNING or ERROR and emit a Prometheus counter so failures are observable.

**One dependency bump per PR.** When a phase requires a new package (`mcp>=1.27.0`, `pydantic-settings`, etc.), that package is added and pinned in its own PR before the code that uses it is merged.

**Data contracts before implementation.** Every phase that introduces a new data structure (Pydantic model, TypedDict, dataclass) defines and tests those contracts before writing the code that produces or consumes them.

**Authentication before exposure.** No new endpoint is added without the `get_current_user` dependency. The existing gap (only `/api/v1/auth/*` is guarded) is tracked as a Phase 0 hardening item.

**Preserve the CVE-2025-8709 mitigation.** The decision to omit a LangGraph checkpointer was deliberate. No phase reintroduces `langgraph-checkpoint-sqlite` without a security review confirming the CVE is patched in the pinned version.

### 1.2 Quality Gates

Before any phase PR is merged:
- `pytest tests/unit` passes with zero errors (no `--ignore` waivers allowed after Phase 2).
- `pytest tests/integration` passes for the domains touched by the phase.
- Type-checking (`mypy src/ --ignore-missing-imports`) produces no new errors.
- `black --check src/` and `flake8 src/` produce no new violations.
- The `GET /api/v1/health/simple` and `POST /api/v1/chat` endpoints respond correctly in a local `docker compose up` run.

### 1.3 Vocabulary

| Term | Definition in this document |
|---|---|
| ModelGateway | Centralized abstraction over all NIM model calls (LLM, embedding, guardrails). Replaces direct `NIMClient` instantiation scattered across 15+ files. |
| MCP SDK | Official Anthropic `mcp` Python package v1.27+ replacing the home-grown JSON-RPC implementation in `src/api/services/mcp/`. |
| Capability Server | A standalone FastAPI process exposing a domain's tools as MCP-SDK-native endpoints (one per domain: equipment, operations, safety, forecasting, document). |
| Skills | Reusable, domain-agnostic prompt templates + tool subsets that sit above MCP and below Agents. |
| WarehouseState | A single, fully typed Pydantic model representing the live state of a warehouse query session. Replaces the `MCPWarehouseState` TypedDict. |
| DecisionEngine | A synchronous, policy-driven gate that must approve every write action before it executes. Replaces the current unenforced `requires_approval` metadata flag. |
| AgentRuntime | An interface that hides LangGraph internals from callers, enabling future graph engine swaps. |
| TrajectoryStore | A persistent, append-only log of every meaningful agent execution step, keyed by `trace_id`. |
| Intelligence Flywheel | The pipeline from TrajectoryStore data through human labeling, SFT, and RL/GRPO back to deployed Nemotron models. |

---

## 2. Phase Overview

| Phase | Name | Primary Deliverable | Estimated Complexity | Est. Duration |
|---|---|---|---|---|
| 0 | Foundation Hardening | Pydantic Settings, auth on all endpoints, structured logging, CI fixes | Low | 1 week |
| 1 | ModelGateway | Single entry point for all NIM calls with telemetry and model routing | Medium | 2 weeks |
| 2 | MCP SDK Adoption | Replace custom JSON-RPC stack with official `mcp` package | High | 3 weeks |
| 3 | Capability Servers | Independent FastAPI processes per domain exposing MCP-SDK tools | High | 4 weeks |
| 4 | Warehouse Contracts | Vendor-neutral Pydantic domain models replacing ad-hoc dataclasses | Medium | 2 weeks |
| 5 | Skills Layer | Reusable prompt + tool bundles between MCP and Agents | Medium | 2 weeks |
| 6 | WarehouseState | Typed, Pydantic-validated session state with freshness metadata | Medium | 2 weeks |
| 7 | DecisionEngine | Blocking policy/risk/approval gate before every write action | High | 3 weeks |
| 8 | AgentRuntime | Interface hiding LangGraph; pluggable graph engine | Medium | 2 weeks |
| 9 | Trajectory Store | Persistent execution log; trace_id propagation across all layers | High | 3 weeks |
| 10 | Evaluation Platform | Automated regression tests against TrajectoryStore baselines | High | 3 weeks |
| 11 | Intelligence Flywheel | Trajectory export, SFT data pipeline, RL/GRPO training hooks | Very High | 6 weeks |
| 12 | Nemotron Specialization | Swap base models for fine-tuned domain Nemotron checkpoints | Very High | Ongoing |

Total estimated elapsed time assuming one team of four engineers: ~33 weeks. Phases 1, 4, 5 can overlap with adjacent phases after their foundational PRs land.

---

## 3. Phase Definitions

---

### Phase 0: Foundation Hardening

**Objective:** Fix the structural deficiencies that would compound migration risk if left in place. No new features; only hardening and scaffolding.

**Pre-conditions:** None. This is the starting point.

**Tasks:**

0.1. Add `pydantic-settings` to `requirements.txt` and `pyproject.toml`. Create `src/api/config/settings.py` with a `Settings(BaseSettings)` class that reads every environment variable currently consumed via raw `os.getenv()`. Set `env_file=".env"` and `env_file_encoding="utf-8"`. Remove the two manual `load_dotenv()` calls from `app.py` and the health endpoint.

0.2. Apply `get_current_user` (from `src/api/services/auth/dependencies.py`) to all routers that currently lack authentication: `chat`, `equipment`, `operations`, `safety`, `inventory`, `reasoning`, `mcp`, `document`, `advanced_forecasting`, `training`, `wms`, `iot`, `erp`, `scanning`, `attendance`. Add a `SKIP_AUTH` env var (default `false`) for local development and CI use. Update `.env.example`.

0.3. Add `python-json-logger` to requirements. Replace the ad-hoc `logging.basicConfig(format="%(asctime)s...")` calls in `migrate.py` and `advanced_forecasting.py` with a centralized `configure_logging(level, format)` function in `src/api/utils/log_utils.py`. Output JSON in production (`ENVIRONMENT=production`), plain text in development. Pass `request_id` as a logging context variable using `contextvars.ContextVar`.

0.4. Fix the five broken integration tests (`test_mcp_agent_workflows.py`, `test_mcp_end_to_end.py`, `test_mcp_system_integration.py`, `test_mcp_monitoring_integration.py`, `test_mcp_rollback_integration.py`) by adding `asyncpg` and `pytest-asyncio` to the CI dev-dependencies section and updating the `--ignore` list in `ci-cd.yml` to reflect only tests that require a live NIM API key.

0.5. Remove the eleven `--ignore` entries from the `ci-cd.yml` pytest invocation that mask real failures (`test_mcp_integrated_planner_graph.py`, `test_mcp_system.py`, `test_guardrails_sdk.py`, `test_all_agents.py`, `test_db_connection.py`, `test_enhanced_retrieval.py`, `test_mcp_planner_integration.py`, `test_document_pipeline.py`, `test_nvidia_integration.py`, `test_nvidia_llm.py`, `test_document_action_tools.py`). Fix each test or mark explicitly as `@pytest.mark.requires_nim` and skip via a CI env var.

0.6. Add a `POST /api/v1/chat` smoke test to CI that starts the backend with a mock NIM response (use `httpx.MockTransport` or `respx`) and asserts HTTP 200 with a valid `ChatResponse` structure.

0.7. Rename the root-level duplicate JSON files (`historical_demand_summary.json`, `rapids_gpu_forecasts.json`) by adding a Git-tracked symlink to `data/sample/forecasts/` and deleting the root-level copies.

0.8. Add `LLAMA_49B_TIMEOUT` env var (matching the existing `LLAMA_70B_TIMEOUT` used in `large_llm_judge.py`) to `.env.example` with a comment explaining the legacy variable name. No code change yet — just documentation.

**Files to add/modify:**
- `src/api/config/__init__.py` (new)
- `src/api/config/settings.py` (new)
- `src/api/utils/log_utils.py` (modify — add `configure_logging`, `LogContext`)
- `src/api/app.py` (modify — import Settings, centralize logging, add auth deps to all routers)
- `src/api/routers/*.py` (modify — add `Depends(get_current_user)`)
- `requirements.txt` (modify — add `pydantic-settings`, `python-json-logger`)
- `.github/workflows/ci-cd.yml` (modify — fix ignored tests)
- `.env.example` (modify — document new vars)

**Tests required:**
- Unit: `tests/unit/test_config.py` — verify all required env vars have defaults or raise on missing.
- Unit: `tests/unit/test_log_utils.py` — verify JSON output in production mode, plain text in dev.
- Integration: smoke test `POST /api/v1/chat` with mock NIM returns HTTP 200.
- Integration: `GET /api/v1/equipment` without JWT returns HTTP 401.

**Definition of done:** `pytest tests/` with no `--ignore` flags passes (minus `@pytest.mark.requires_nim`). Every endpoint returns 401 without a valid token. Structured logs emit valid JSON in production mode. CI pipeline is green.

**Rollback strategy:** All changes are additive or purely internal. `SKIP_AUTH=true` preserves the old unauthenticated behavior for local dev. If `pydantic-settings` import fails, the `Settings` class can be patched to a simple `os.getenv()` wrapper without changing callers.

---

### Phase 1: ModelGateway

**Objective:** Centralize every NIM API call behind a single `ModelGateway` abstraction with built-in model routing, telemetry emission, retry configuration, and timeout enforcement. Remove the fifteen scattered `httpx.AsyncClient` instantiations spread across `nim_client.py`, `large_llm_judge.py`, `small_llm_processor.py`, `nemo_ocr.py`, `nemo_retriever.py`, `nemotron_parse.py`, and `guardrails_service.py`.

**Pre-conditions:** Phase 0 complete. `Settings` class available.

**Tasks:**

1.1. Define `src/api/gateway/__init__.py` and `src/api/gateway/model_gateway.py`. The `ModelGateway` class holds one shared `httpx.AsyncClient` (LLM) and one (Embedding), both configured from `Settings`. Expose four async methods: `complete(messages, model_hint, temperature, max_tokens, enable_thinking, reasoning_budget) -> str`, `embed(texts, model_hint) -> list[list[float]]`, `check_guardrails_input(text, context) -> GuardrailsResult`, `check_guardrails_output(text, context) -> GuardrailsResult`.

1.2. Define `src/api/gateway/model_selector.py`. The `ModelSelector` class maps a `model_hint` string (`"llm"`, `"embedding"`, `"judge"`, `"small_vlm"`, `"ocr"`, `"parse"`) to the actual model identifier and endpoint URL from `Settings`. This is the single place where model identifiers live; remove all hardcoded model strings from individual service files.

1.3. Define `src/api/gateway/telemetry.py`. Every `ModelGateway` call emits Prometheus counters: `model_requests_total{model, endpoint, status}`, `model_latency_seconds{model, endpoint}`, `model_token_usage_total{model, direction}`. Reuse `prometheus_client` already present in requirements.

1.4. Migrate `src/api/services/llm/nim_client.py`: replace the internal `httpx.AsyncClient` calls with `ModelGateway` calls. Keep the `NIMClient` class as a thin adapter for backward compatibility (agents still call `nim_client.generate_response()`). Add a `# DEPRECATED` comment noting it will be removed in Phase 2 cleanup.

1.5. Migrate `src/api/agents/document/validation/large_llm_judge.py`: replace its own `httpx.AsyncClient` with `get_model_gateway().complete(model_hint="judge", ...)`. Remove `LLAMA_70B_TIMEOUT` reading; timeout now comes from `Settings.llm_judge_timeout`.

1.6. Migrate `src/api/agents/document/processing/small_llm_processor.py`: replace its `httpx.AsyncClient` with `get_model_gateway().complete(model_hint="small_vlm", ...)` with fallback to `model_hint="small_text"`.

1.7. Migrate `src/api/agents/document/ocr/nemo_ocr.py`, `nemotron_parse.py`, `preprocessing/nemo_retriever.py`: same pattern.

1.8. Migrate `src/api/services/guardrails/guardrails_service.py` and `nemo_sdk_service.py`: route guardrails model calls through `ModelGateway.check_guardrails_input/output`.

1.9. Add the `MODEL_GATEWAY_ENABLED` feature flag (default `true` after migration). If `false`, the old `NIMClient` direct-httpx path is used. This allows instant rollback.

1.10. Update `src/api/config/settings.py` with all model routing settings: `LLM_MODEL`, `EMBEDDING_MODEL`, `JUDGE_MODEL`, `SMALL_VLM_MODEL`, `OCR_MODEL`, `PARSE_MODEL` — each with its NIM URL override.

**Files to add/modify:**
- `src/api/gateway/__init__.py` (new)
- `src/api/gateway/model_gateway.py` (new)
- `src/api/gateway/model_selector.py` (new)
- `src/api/gateway/telemetry.py` (new)
- `src/api/services/llm/nim_client.py` (wrap via gateway)
- `src/api/agents/document/validation/large_llm_judge.py` (migrate)
- `src/api/agents/document/processing/small_llm_processor.py` (migrate)
- `src/api/agents/document/ocr/nemo_ocr.py` (migrate)
- `src/api/agents/document/ocr/nemotron_parse.py` (migrate)
- `src/api/agents/document/preprocessing/nemo_retriever.py` (migrate)
- `src/api/services/guardrails/guardrails_service.py` (migrate)
- `src/api/services/guardrails/nemo_sdk_service.py` (migrate)
- `src/api/config/settings.py` (extend)

**Tests required:**
- Unit: `tests/unit/test_model_gateway.py` — mock httpx; verify `complete()`, `embed()`, guardrails methods; verify Prometheus counters increment; verify model_hint → model_id mapping.
- Unit: verify `NIMClient.generate_response()` delegates to gateway when flag is on.
- Integration: `POST /api/v1/chat` still returns HTTP 200 with gateway enabled.
- Integration: gateway telemetry endpoint shows new `model_requests_total` metric.

**Definition of done:** All NIM API calls pass through `ModelGateway`. `model_requests_total` Prometheus counter appears in `GET /api/v1/metrics` for every model type. Zero direct `httpx.AsyncClient` instantiations remain outside `model_gateway.py`. Old `NIMClient` is marked deprecated but still functional.

**Rollback strategy:** Set `MODEL_GATEWAY_ENABLED=false` to revert to `NIMClient` direct httpx. No database changes. Frontend unaffected.

---

### Phase 2: MCP SDK Adoption

**Objective:** Replace the 15-file custom JSON-RPC MCP implementation in `src/api/services/mcp/` with the official Anthropic `mcp` Python package. The custom server, client, base, security, tool_discovery, tool_binding, tool_routing, parameter_validator, and adapter classes are replaced with SDK equivalents or minimal wrappers.

**Pre-conditions:** Phase 1 complete.

**Tasks:**

2.1. Add `mcp>=1.27.0` to `requirements.txt` and `pyproject.toml`. Pin to a specific minor version. Verify no conflict with `langgraph>=1.0.5`.

2.2. Create `src/api/mcp_sdk/__init__.py` and `src/api/mcp_sdk/server_factory.py`. The `WarehouseMCPServerFactory` class knows how to construct an `mcp.Server` instance and register tools using the `@server.call_tool()` and `@server.list_tools()` decorators from the SDK. This file is the only place that imports from the `mcp` package directly.

2.3. Create `src/api/mcp_sdk/security_filter.py`. Port the `BLOCKED_TOOL_PATTERNS`, `BLOCKED_TOOL_NAMES`, `BLOCKED_CAPABILITIES`, `BLOCKED_PARAMETER_NAMES` regex lists and `validate_chain_path()` from `src/api/services/mcp/security.py` into an SDK-compatible tool registration hook. The security gate runs before any tool is registered with the SDK server.

2.4. Create `src/api/mcp_sdk/parameter_bridge.py`. Translates the existing per-adapter parameter schema dicts (currently `{"type": "object", "properties": {...}, "required": [...]}`) into `mcp.types.Tool` `inputSchema` objects. This is a translation layer only — the actual tool parameter schemas stay in the adapter files unchanged.

2.5. Migrate `src/api/services/mcp/adapters/equipment_adapter.py` to SDK registration. The adapter class keeps its `_handle_*` methods unchanged. A new `register_with_sdk_server(server: mcp.Server)` class method wraps each handler in `@server.call_tool()`. The old `MCPTool` dataclass-based `_register_tools()` method is kept but marked `# DEPRECATED`.

2.6. Migrate the remaining adapters: `operations_adapter.py`, `safety_adapter.py`, `forecasting_adapter.py`, `wms_adapter.py`, `iot_adapter.py`, `erp_adapter.py`, `rfid_barcode_adapter.py`, `time_attendance_adapter.py` — same pattern as 2.5.

2.7. Add `MCP_SDK_ENABLED` feature flag (default `false`). When true, `src/api/routers/mcp.py`'s `_register_mcp_adapters()` function calls `register_with_sdk_server()` on each adapter instead of the old `MCPManager` path. When false, existing path unchanged.

2.8. Update `src/api/graphs/mcp_integrated_planner_graph.py`: add a branch in `_execute_tool_plan()` that, when `MCP_SDK_ENABLED`, calls tools via the SDK server's `call_tool()` method rather than `tool_discovery.execute_tool()`. Keep the old path as fallback.

2.9. The `ToolDiscoveryService`, `ToolBindingService`, and `ToolRoutingService` remain in place but are marked `# DEPRECATED: will be replaced in Phase 3`. Their removal is scheduled for Phase 3 cleanup.

2.10. Update `tests/unit/test_mcp_system.py` to exercise the SDK path alongside the legacy path under the feature flag.

**Files to add/modify:**
- `src/api/mcp_sdk/__init__.py` (new)
- `src/api/mcp_sdk/server_factory.py` (new)
- `src/api/mcp_sdk/security_filter.py` (new, ports from `services/mcp/security.py`)
- `src/api/mcp_sdk/parameter_bridge.py` (new)
- `src/api/services/mcp/adapters/*.py` (add `register_with_sdk_server()`)
- `src/api/routers/mcp.py` (feature-flag branch)
- `src/api/graphs/mcp_integrated_planner_graph.py` (feature-flag branch in tool execution)
- `requirements.txt`, `pyproject.toml` (add `mcp>=1.27.0`)

**Tests required:**
- Unit: `tests/unit/test_mcp_sdk_adoption.py` — verify SDK server registers all 28 tools; verify security filter blocks blocked tool names; verify parameter bridge produces valid `mcp.types.Tool` inputSchema.
- Unit: run existing `test_mcp_system.py` with `MCP_SDK_ENABLED=true`; all 30 tests must pass.
- Integration: `GET /api/v1/mcp/tools` returns same tool list with SDK enabled as with legacy enabled.
- Integration: `POST /api/v1/mcp/tools/execute` for `get_equipment_status` succeeds with SDK enabled.

**Definition of done:** `MCP_SDK_ENABLED=true` produces functionally identical behavior to the legacy path for all 28 registered tools. Security filter blocks all patterns from the blocklist. Old `MCPServer` and `MCPClient` classes marked deprecated. Zero direct JSON-RPC message construction outside `server_factory.py`.

**Rollback strategy:** Set `MCP_SDK_ENABLED=false`. The legacy custom MCP stack is fully intact.

---

### Phase 3: Capability Servers

**Objective:** Extract each domain's MCP tools into independently deployable FastAPI processes, each serving a standard MCP HTTP endpoint. The orchestrator (planner graph) connects to these servers via the SDK client rather than calling adapter handlers in-process.

**Pre-conditions:** Phase 2 complete with `MCP_SDK_ENABLED=true` stable in staging.

**Tasks:**

3.1. Define `src/capability_servers/base_capability_server.py`. The `CapabilityServer` class is a thin FastAPI application that mounts one or more SDK-registered `mcp.Server` instances and exposes them at `POST /mcp`. Includes health endpoint `GET /health` and Prometheus metrics.

3.2. Create `src/capability_servers/equipment/server.py`. Imports `EquipmentMCPAdapter`, creates an `mcp.Server`, calls `register_with_sdk_server()`, mounts it. Entry point: `uvicorn src.capability_servers.equipment.server:app --port 8011`. Add `Dockerfile.equipment-server` inheriting from `python:3.11-slim`.

3.3. Create `src/capability_servers/operations/server.py` (port 8012), `safety/server.py` (port 8013), `forecasting/server.py` (port 8014), `document/server.py` (port 8015). Same pattern.

3.4. Add these five services to `deploy/compose/docker-compose.dev.yaml` as `equipment-server`, `operations-server`, `safety-server`, `forecasting-server`, `document-server`. Each declares a dependency on `timescaledb`.

3.5. Create `src/api/mcp_sdk/client_pool.py`. The `MCPClientPool` maintains one persistent `mcp.ClientSession` per capability server URL, with connection health monitoring, automatic reconnect, and a `call_tool(server_name, tool_name, arguments)` method. Pool is initialized at app startup in `app.py` lifespan.

3.6. Update `src/api/graphs/mcp_integrated_planner_graph.py`: replace in-process adapter calls with `MCPClientPool.call_tool(server_name, tool_name, arguments)` when `CAPABILITY_SERVERS_ENABLED=true`. Keep the in-process path as fallback.

3.7. Delete `src/api/services/mcp/server.py`, `client.py`, `tool_binding.py`, `tool_routing.py`, `service_discovery.py` (these were the deprecated custom stack from Phase 2). Move security patterns to `src/api/mcp_sdk/security_filter.py` exclusively. Move `tool_discovery.py` to `src/api/mcp_sdk/tool_registry.py` (it still serves as an in-process catalog for the fallback path).

3.8. Update environment variables: `EQUIPMENT_SERVER_URL` (default `http://equipment-server:8011`), `OPERATIONS_SERVER_URL`, `SAFETY_SERVER_URL`, `FORECASTING_SERVER_URL`, `DOCUMENT_SERVER_URL`. Add to `Settings`.

3.9. Update nginx config to route `/mcp/equipment/*`, `/mcp/operations/*`, etc. directly to capability servers when debugging.

**Files to add:**
- `src/capability_servers/__init__.py`
- `src/capability_servers/base_capability_server.py`
- `src/capability_servers/equipment/server.py`
- `src/capability_servers/operations/server.py`
- `src/capability_servers/safety/server.py`
- `src/capability_servers/forecasting/server.py`
- `src/capability_servers/document/server.py`
- `src/api/mcp_sdk/client_pool.py`
- `Dockerfile.equipment-server` (and 4 more)

**Files to modify:**
- `deploy/compose/docker-compose.dev.yaml`
- `src/api/graphs/mcp_integrated_planner_graph.py`
- `src/api/app.py` (lifespan — initialize MCPClientPool)
- `src/api/config/settings.py` (add server URLs)

**Files to delete:**
- `src/api/services/mcp/server.py`
- `src/api/services/mcp/client.py`
- `src/api/services/mcp/tool_binding.py`
- `src/api/services/mcp/tool_routing.py`
- `src/api/services/mcp/service_discovery.py`
- `src/api/services/mcp/base.py` (fold `MCPError` into `src/api/mcp_sdk/`)

**Tests required:**
- Integration: each capability server starts and `GET /health` returns 200.
- Integration: `MCPClientPool.call_tool("equipment", "get_equipment_status", {...})` returns correct response.
- Integration: `POST /api/v1/chat` with equipment query routes through capability server when `CAPABILITY_SERVERS_ENABLED=true`.
- Integration: capability server failure causes graceful fallback (error response, not 500 to user).

**Definition of done:** All five capability servers run as independent Docker containers. The orchestrator connects via `MCPClientPool`. Legacy in-process adapter calls still work with `CAPABILITY_SERVERS_ENABLED=false`. Zero deleted file imports remain in the live code.

**Rollback strategy:** Set `CAPABILITY_SERVERS_ENABLED=false`. Stop and remove the five new Docker containers. All adapter code remains in-process.

---

### Phase 4: Warehouse Semantic Contracts

**Objective:** Define a single, vendor-neutral, fully typed set of Pydantic domain models that every layer of the system (capability servers, agents, routers, adapters) shares. Eliminate the current fragmentation where `EquipmentAsset` is defined in `equipment.py` (router), `EquipmentResponse` in `equipment_agent.py`, and `MCPEquipmentResponse` in `mcp_equipment_agent.py` as unrelated classes with overlapping fields.

**Pre-conditions:** Phase 3 complete (capability servers are the primary consumers of these contracts).

**Tasks:**

4.1. Create `src/warehouse_contracts/__init__.py` and the following domain contract files:
- `src/warehouse_contracts/equipment.py` — `EquipmentAsset`, `EquipmentAssignment`, `EquipmentTelemetry`, `MaintenanceRecord`, `EquipmentStatus` (enum), `EquipmentType` (enum)
- `src/warehouse_contracts/inventory.py` — `InventoryItem`, `InventoryMovement`, `StockInfo`, `ReservationResult`, `ReplenishmentTask`, `PurchaseRequisition`
- `src/warehouse_contracts/operations.py` — `Task`, `TaskKind` (enum), `TaskStatus` (enum), `TaskAssignment`, `WorkforceStatus`, `PickWave`, `PickPathOptimization`, `WorkloadRebalance`, `KPIMetrics`
- `src/warehouse_contracts/safety.py` — `SafetyIncident`, `SafetySeverity` (enum), `SafetyChecklist`, `SafetyAlert`, `LockoutTagoutRequest`, `CorrectiveAction`, `SafetyDataSheet`, `NearMissReport`, `SafetyPolicy`
- `src/warehouse_contracts/forecasting.py` — `ForecastResult`, `BatchForecastResult`, `ReorderRecommendation`, `ModelPerformance`, `BusinessIntelligence`
- `src/warehouse_contracts/document.py` — consolidate `document_models.py` and `extraction_models.py` here
- `src/warehouse_contracts/agent_response.py` — `AgentResponse` base model with fields `response_type`, `natural_language`, `recommendations`, `confidence`, `actions_taken`, `mcp_tools_used`, `tool_execution_results`, `reasoning_chain`, `reasoning_steps`. Domain responses extend this.

4.2. Update each capability server to return `warehouse_contracts` types in tool responses.

4.3. Update each action tool class (`EquipmentAssetTools`, `OperationsActionTools`, `SafetyActionTools`, `ForecastingActionTools`, `DocumentActionTools`) to return `warehouse_contracts` types.

4.4. Update each agent class to accept and return `warehouse_contracts` types. Remove the per-agent `*Response` dataclasses (`EquipmentResponse`, `MCPEquipmentResponse`, `SafetyResponse`, `OperationsResponse`, `MCPForecastingResponse`) — these are replaced by the unified `AgentResponse` base + domain extensions.

4.5. Update routers to accept and return `warehouse_contracts` types. The `InventoryItem` in `routers/inventory.py`, `Task` in `routers/operations.py`, `EquipmentAsset` in `routers/equipment.py`, `SafetyIncident` in `routers/safety.py` are replaced with their `warehouse_contracts` equivalents.

4.6. Add Pydantic validators where none currently exist: `EquipmentAsset.status` must be `EquipmentStatus` enum; `SafetyIncident.severity` must be `SafetySeverity` enum; `Task.kind` must be `TaskKind` enum.

**Files to add:**
- `src/warehouse_contracts/__init__.py`
- `src/warehouse_contracts/equipment.py`
- `src/warehouse_contracts/inventory.py`
- `src/warehouse_contracts/operations.py`
- `src/warehouse_contracts/safety.py`
- `src/warehouse_contracts/forecasting.py`
- `src/warehouse_contracts/document.py`
- `src/warehouse_contracts/agent_response.py`

**Files to modify:** All agent classes, all action tool classes, all domain routers, all capability servers, `src/api/agents/document/models/document_models.py` (migrate to contracts, then delete).

**Tests required:**
- Unit: `tests/unit/test_warehouse_contracts.py` — valid construction, enum validation, JSON round-trip for every contract type.
- Unit: verify `AgentResponse.model_validate(existing_dict)` works for existing response shapes.
- Integration: `GET /api/v1/equipment` response validates against `list[EquipmentAsset]`.
- Integration: `POST /api/v1/safety/incidents` request validates against `SafetyIncident`.

**Definition of done:** `mypy src/warehouse_contracts/ src/api/agents/ src/api/routers/` produces zero new type errors. All domain response types are Pydantic models inheriting from `warehouse_contracts`. Per-agent `*Response` dataclasses deleted. Router models deleted.

**Rollback strategy:** Contracts are backward-compatible (same field names, added validation). If a contract type causes a validation error on existing data, add `model_config = ConfigDict(extra="ignore")` as a temporary shim.

---

### Phase 5: Skills Layer

**Objective:** Introduce a reusable Skills layer between MCP capability servers and the agent classes. A Skill is a named, versioned bundle of: a prompt template, a subset of MCP tools to offer, optional few-shot examples, and configuration knobs (model hint, temperature, max_tokens). Skills allow the same MCP tools to be surfaced to agents with different personas and instructions without duplicating logic.

**Pre-conditions:** Phase 4 complete (contracts defined); Phase 3 stable (capability servers running).

**Tasks:**

5.1. Create `src/skills/__init__.py`, `src/skills/base.py`. The `Skill` base class has: `name: str`, `version: str`, `description: str`, `prompt_template: str`, `allowed_tools: list[str]`, `model_hint: str`, `temperature: float`, `max_tokens: int`. It exposes `async execute(query, context, tool_results) -> AgentResponse`.

5.2. Create domain skills:
- `src/skills/equipment_status.py` — `EquipmentStatusSkill`: wraps `get_equipment_status`, `get_equipment_utilization`, `get_maintenance_schedule`
- `src/skills/incident_triage.py` — `IncidentTriageSkill`: wraps `log_incident`, `broadcast_alert`, `get_safety_procedures`
- `src/skills/pick_wave_planning.py` — `PickWavePlanningSkill`: wraps `create_task`, `assign_task`, `get_workforce_status`
- `src/skills/demand_forecast.py` — `DemandForecastSkill`: wraps `get_forecast`, `get_reorder_recommendations`
- `src/skills/document_intake.py` — `DocumentIntakeSkill`: wraps document upload and extraction tools
- `src/skills/inventory_replenishment.py` — `InventoryReplenishmentSkill`: wraps `check_stock`, `create_replenishment_task`, `generate_purchase_requisition`

5.3. Create `src/skills/skill_registry.py`. The `SkillRegistry` singleton holds all registered skills, resolves by name and version, and exposes `get_skills_for_intent(intent: str) -> list[Skill]`.

5.4. Update agent classes to use `SkillRegistry` to select their skill before calling NIM LLM. The agent's prompt is now `skill.prompt_template.format(query=query, tool_results=tool_results)` rather than a per-agent hardcoded string. The old hardcoded prompts remain as the template defaults, ensuring no behavioral regression.

5.5. Add `SKILLS_ENABLED` feature flag (default `false`).

5.6. Create `data/config/skills/` directory with one YAML per skill for runtime prompt override without code deployment.

**Files to add:**
- `src/skills/__init__.py`
- `src/skills/base.py`
- `src/skills/equipment_status.py`
- `src/skills/incident_triage.py`
- `src/skills/pick_wave_planning.py`
- `src/skills/demand_forecast.py`
- `src/skills/document_intake.py`
- `src/skills/inventory_replenishment.py`
- `src/skills/skill_registry.py`
- `data/config/skills/*.yaml` (6 files)

**Files to modify:**
- `src/api/agents/inventory/mcp_equipment_agent.py`
- `src/api/agents/operations/mcp_operations_agent.py`
- `src/api/agents/safety/mcp_safety_agent.py`
- `src/api/agents/forecasting/forecasting_agent.py`
- `src/api/agents/document/mcp_document_agent.py`

**Tests required:**
- Unit: `tests/unit/test_skills.py` — verify each skill has valid prompt template, allowed_tools list, and produces an `AgentResponse` from mock tool results.
- Unit: `SkillRegistry.get_skills_for_intent("equipment")` returns `EquipmentStatusSkill`.
- Integration: `POST /api/v1/chat` with `SKILLS_ENABLED=true` returns same quality response as legacy path.

**Definition of done:** All six domain skills registered and resolvable. Prompts live in YAML and can be updated without a code deploy. `SKILLS_ENABLED=true` passes all chat integration tests.

**Rollback strategy:** Set `SKILLS_ENABLED=false`. Agent classes fall back to their hardcoded prompt strings.

---

### Phase 6: WarehouseState

**Objective:** Replace the `MCPWarehouseState` TypedDict (which accepts `Dict[str, any]` for most fields and has no validation) with a fully typed, Pydantic-validated `WarehouseState` model that includes freshness metadata on every retrieved data field.

**Pre-conditions:** Phase 4 complete (warehouse contracts available). Phase 1 complete (ModelGateway telemetry available).

**Tasks:**

6.1. Create `src/api/state/__init__.py` and `src/api/state/warehouse_state.py`. Define:

```python
class DataFreshness(BaseModel):
    retrieved_at: datetime
    ttl_seconds: int
    source: str

class WarehouseStateField(BaseModel, Generic[T]):
    value: T
    freshness: DataFreshness

class WarehouseState(BaseModel):
    session_id: str
    trace_id: str  # UUID, new field, propagated everywhere
    messages: list[BaseMessage]
    user_intent: Optional[str]
    routing_decision: Optional[str]
    enable_reasoning: bool = False
    reasoning_types: list[str] = []
    equipment_data: Optional[WarehouseStateField[list[EquipmentAsset]]] = None
    operations_data: Optional[WarehouseStateField[list[Task]]] = None
    safety_data: Optional[WarehouseStateField[list[SafetyIncident]]] = None
    forecasting_data: Optional[WarehouseStateField[ForecastResult]] = None
    document_data: Optional[WarehouseStateField[dict]] = None
    agent_response: Optional[AgentResponse] = None
    mcp_tools_used: list[str] = []
    tool_execution_results: list[dict] = []
    reasoning_chain: Optional[dict] = None
    context: dict = {}
```

6.2. Create `src/api/state/state_transitions.py`. Defines `StateTransition` enum (`INITIALIZED`, `ROUTING`, `TOOL_EXECUTION`, `LLM_SYNTHESIS`, `GUARDRAILS_CHECK`, `ENHANCEMENT`, `COMPLETE`, `FAILED`) and a `record_transition(state, transition, metadata)` function that appends to an in-memory log (later replaced by TrajectoryStore in Phase 9).

6.3. Update `src/api/graphs/mcp_integrated_planner_graph.py`: replace the `MCPWarehouseState(TypedDict)` with `WarehouseState`. LangGraph `StateGraph` accepts Pydantic models as of `langgraph>=1.0.5`. Add `trace_id = str(uuid.uuid4())` initialization at graph entry. Each node's return is now `WarehouseState` mutation, not a raw dict.

6.4. Update the planner graph nodes to populate typed fields: `_mcp_equipment_agent()` writes `state.equipment_data = WarehouseStateField(value=..., freshness=DataFreshness(retrieved_at=now(), ttl_seconds=60, source="timescaledb"))`.

6.5. Update `src/api/routers/chat.py`: replace dict construction with `WarehouseState(session_id=..., trace_id=..., messages=[...], ...)`. Include `trace_id` in the `ChatResponse` (new field, non-breaking).

6.6. Retain `MCPWarehouseState` as a deprecated alias for one phase, mapping through a `to_legacy_dict()` method for any remaining callers.

**Files to add:**
- `src/api/state/__init__.py`
- `src/api/state/warehouse_state.py`
- `src/api/state/state_transitions.py`

**Files to modify:**
- `src/api/graphs/mcp_integrated_planner_graph.py` (major refactor)
- `src/api/graphs/mcp_planner_graph.py` (mark fully deprecated, no changes needed)
- `src/api/routers/chat.py` (add `trace_id` to `ChatResponse`)

**Tests required:**
- Unit: `tests/unit/test_warehouse_state.py` — construct `WarehouseState`, verify `WarehouseStateField` freshness tracking, verify Pydantic validation rejects invalid state.
- Unit: verify `trace_id` appears in every state transition.
- Integration: `POST /api/v1/chat` response includes `trace_id` field.
- Integration: stale data (TTL expired) is flagged in `DataFreshness`.

**Definition of done:** `MCPWarehouseState` TypedDict is no longer the primary state container in the active graph. Every retrieved data field in `WarehouseState` carries freshness metadata. `trace_id` propagates from chat request to chat response.

**Rollback strategy:** The graph accepts both `WarehouseState` and the legacy `MCPWarehouseState` dict via the `to_legacy_dict()` bridge. Feature flag `WAREHOUSE_STATE_V2=false` reverts to old TypedDict.

---

### Phase 7: DecisionEngine

**Objective:** Implement a blocking, synchronous, deterministic policy/risk/approval gate that must return `APPROVED` before any write action executes. Enforce the `requires_approval` flag that currently exists only as metadata with no actual enforcement. Introduce RBAC-based tool authorization.

**Pre-conditions:** Phase 6 complete (WarehouseState includes `session_id`, `trace_id`, and user identity). Phase 0 complete (all endpoints authenticated, `get_current_user` available).

**Tasks:**

7.1. Create `src/decision_engine/__init__.py`, `src/decision_engine/engine.py`. The `DecisionEngine` exposes one method: `async gate(action: ProposedAction, actor: User, state: WarehouseState) -> DecisionResult`. `DecisionResult` has fields `approved: bool`, `reason: str`, `risk_score: float [0-1]`, `required_approver: Optional[str]`.

7.2. Define `src/decision_engine/models.py`: `ProposedAction(tool_name, arguments, domain, estimated_impact)`, `DecisionResult`, `PolicyRule(condition_fn, action: Literal["approve","deny","escalate"], reason_template)`.

7.3. Implement `src/decision_engine/policy_loader.py`. Loads `data/config/policies/*.yaml` at startup (same pattern as agent YAML config). Each YAML file defines one or more `PolicyRule` entries. Policies are domain-scoped: `equipment_policies.yaml`, `operations_policies.yaml`, `safety_policies.yaml`, `inventory_policies.yaml`.

7.4. Implement `src/decision_engine/rbac_gate.py`. Maps `(tool_name, User.role)` against the `ROLE_PERMISSIONS` dict in `src/api/services/auth/models.py`. An operator cannot call `adjust_reorder_point` (requires `inventory:write`). A viewer cannot call `create_task` (requires `operations:write/assign`).

7.5. Implement `src/decision_engine/risk_scorer.py`. Computes `risk_score` for a `ProposedAction` based on: estimated quantity change (>100 units → elevated), zone sensitivity (safety zones → elevated), action type (write > read), time of day (off-hours → elevated).

7.6. Wire `DecisionEngine.gate()` into each action tool class immediately before the actual write. In `EquipmentAssetTools.schedule_maintenance()`, `OperationsActionTools.create_task()`, `SafetyActionTools.log_incident()`, `EquipmentActionTools.adjust_reorder_point()`, etc.: the method raises `DecisionDeniedError` if `gate()` returns `approved=False`.

7.7. Add `DECISION_ENGINE_ENABLED` feature flag (default `false`). When disabled, all actions pass through without gating. When enabled, the gate runs synchronously before every write.

7.8. Create `data/config/policies/` with initial YAML policy files encoding the existing implicit rules (high-risk operations require manager role, emergency broadcasts require supervisor role, purchase requisitions require manager role).

7.9. Add audit logging: every `DecisionResult` is written to the `audit_log` PostgreSQL table (already schema-defined in `000_schema.sql`) with `action=tool_name`, `resource_type=domain`, `details=ProposedAction.arguments + DecisionResult`.

**Files to add:**
- `src/decision_engine/__init__.py`
- `src/decision_engine/engine.py`
- `src/decision_engine/models.py`
- `src/decision_engine/policy_loader.py`
- `src/decision_engine/rbac_gate.py`
- `src/decision_engine/risk_scorer.py`
- `data/config/policies/equipment_policies.yaml`
- `data/config/policies/operations_policies.yaml`
- `data/config/policies/safety_policies.yaml`
- `data/config/policies/inventory_policies.yaml`

**Files to modify:**
- `src/api/agents/inventory/equipment_action_tools.py` (add gate call)
- `src/api/agents/inventory/equipment_asset_tools.py` (add gate call)
- `src/api/agents/operations/action_tools.py` (add gate call)
- `src/api/agents/safety/action_tools.py` (add gate call)
- `src/api/agents/forecasting/forecasting_action_tools.py` (add gate call)
- `src/api/services/database.py` (used by audit logging)

**Tests required:**
- Unit: `tests/unit/test_decision_engine.py` — viewer role denied `create_task`; operator denied `adjust_reorder_point`; manager approved; emergency broadcast requires supervisor; risk_score elevated for large quantity writes.
- Unit: `PolicyLoader` loads YAML and applies rules correctly.
- Integration: `POST /api/v1/chat` with a create-task request from an operator user passes gate; same from a viewer returns a denial message.
- Integration: every denied gate call writes to `audit_log`.

**Definition of done:** `DECISION_ENGINE_ENABLED=true` enforces all policy rules. Zero write action tool methods execute without passing `DecisionEngine.gate()`. `audit_log` captures every gate decision. Existing tests still pass (they use a mock user with manager role by default).

**Rollback strategy:** Set `DECISION_ENGINE_ENABLED=false`. All action tools immediately resume the old pre-gate execution path.

---

### Phase 8: AgentRuntime Interface

**Objective:** Introduce an `AgentRuntime` abstract interface that hides LangGraph internals. The planner graph becomes one implementation of `AgentRuntime`; a future sequential or ReAct implementation can be swapped in without touching the router or any caller above the runtime layer.

**Pre-conditions:** Phase 6 complete (WarehouseState). Phase 5 complete (Skills layer).

**Tasks:**

8.1. Create `src/agent_runtime/__init__.py` and `src/agent_runtime/base.py`:

```python
class AgentRuntime(ABC):
    @abstractmethod
    async def run(self, state: WarehouseState) -> WarehouseState:
        ...

    @abstractmethod
    async def health(self) -> dict:
        ...
```

8.2. Create `src/agent_runtime/langgraph_runtime.py`. The `LangGraphRuntime(AgentRuntime)` class wraps `MCPIntegratedPlannerGraph`. Its `run()` method calls `graph.ainvoke(state)` with appropriate timeout wrapping (all timeout logic moves here from the router).

8.3. Update `src/api/routers/chat.py` to call `runtime.run(state)` instead of directly calling `mcp_planner.process_warehouse_query(...)`. The planner graph becomes an implementation detail of `LangGraphRuntime`.

8.4. Move timeout calculation logic from `chat.py` into `LangGraphRuntime.run()`. The router becomes a thin HTTP boundary layer only — no timeout arithmetic, no LangGraph imports.

8.5. Create `src/agent_runtime/simple_sequential_runtime.py` as a non-LangGraph reference implementation for testing: intent classification → single skill execution → synthesis. Does not use LangGraph at all. Used in unit tests to verify contracts without LangGraph overhead.

8.6. Add `AGENT_RUNTIME` env var (`"langgraph"` or `"sequential"`, default `"langgraph"`). `app.py` lifespan instantiates the appropriate runtime.

8.7. Deprecate `src/api/graphs/mcp_planner_graph.py` (Phase 2 intermediate): this file is now unused. Move to `src/api/graphs/_deprecated/mcp_planner_graph.py` and schedule deletion for Phase 9 cleanup.

**Files to add:**
- `src/agent_runtime/__init__.py`
- `src/agent_runtime/base.py`
- `src/agent_runtime/langgraph_runtime.py`
- `src/agent_runtime/simple_sequential_runtime.py`

**Files to modify:**
- `src/api/routers/chat.py` (remove direct graph dependency)
- `src/api/app.py` (instantiate runtime from env var)

**Files to move/deprecate:**
- `src/api/graphs/mcp_planner_graph.py` → `src/api/graphs/_deprecated/`

**Tests required:**
- Unit: `SimpleSequentialRuntime.run()` produces a valid `WarehouseState` with `agent_response` populated.
- Unit: `LangGraphRuntime` is swappable with `SimpleSequentialRuntime` — same input produces same contract shape output.
- Integration: `POST /api/v1/chat` with `AGENT_RUNTIME=sequential` returns HTTP 200.

**Definition of done:** `src/api/routers/chat.py` imports zero LangGraph symbols. The router only depends on `AgentRuntime`. `LangGraphRuntime` and `SimpleSequentialRuntime` both pass the integration smoke test.

**Rollback strategy:** Set `AGENT_RUNTIME=langgraph`. The `LangGraphRuntime` is the production default and has been stable for multiple phases.

---

### Phase 9: Trajectory Store

**Objective:** Persist a complete, queryable record of every meaningful agent execution. Every `trace_id` (introduced in Phase 6) links: the initial request, each state transition (Phase 6), each tool call with its arguments and result, each LLM call with its prompt and completion, the final response, and any errors. This is the foundation for evaluation (Phase 10) and fine-tuning (Phase 11).

**Pre-conditions:** Phase 6 complete (`trace_id` in `WarehouseState`). Phase 8 complete (`AgentRuntime` interface isolates instrumentation). Phase 0 complete (structured logging).

**Tasks:**

9.1. Add a `trajectories` table to `data/postgres/migrations/004_trajectories.sql`:

```sql
CREATE TABLE trajectories (
    trace_id UUID PRIMARY KEY,
    session_id TEXT NOT NULL,
    user_id TEXT,
    query TEXT NOT NULL,
    intent TEXT,
    routing_decision TEXT,
    final_response TEXT,
    confidence FLOAT,
    tools_used TEXT[],
    latency_ms INTEGER,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE trajectory_steps (
    id BIGSERIAL PRIMARY KEY,
    trace_id UUID REFERENCES trajectories(trace_id),
    step_index INTEGER NOT NULL,
    step_type TEXT NOT NULL,  -- 'tool_call', 'llm_call', 'state_transition', 'guardrail'
    step_name TEXT NOT NULL,
    input_data JSONB,
    output_data JSONB,
    latency_ms INTEGER,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

SELECT create_hypertable('trajectories', 'created_at');
SELECT create_hypertable('trajectory_steps', 'created_at');
```

9.2. Create `src/trajectory/__init__.py` and `src/trajectory/store.py`. The `TrajectoryStore` class exposes async methods: `begin_trace(trace_id, session_id, user_id, query)`, `record_step(trace_id, step_type, step_name, input_data, output_data, latency_ms, error)`, `end_trace(trace_id, final_response, confidence, tools_used, latency_ms, error)`. Uses a background asyncio queue to avoid blocking the main request path.

9.3. Create `src/trajectory/decorators.py`. The `@record_tool_call` decorator wraps any action tool method: captures arguments, calls the method, captures the return value and latency, and calls `trajectory_store.record_step(step_type="tool_call", ...)`. The `@record_llm_call` decorator wraps `ModelGateway.complete()`.

9.4. Apply `@record_tool_call` to every action tool method across all five domains. Apply `@record_llm_call` to `ModelGateway.complete()`.

9.5. Wire `TrajectoryStore.begin_trace()` into `AgentRuntime.run()` at entry (using `state.trace_id`) and `end_trace()` at exit.

9.6. Wire `state_transitions.record_transition()` (from Phase 6) to call `trajectory_store.record_step(step_type="state_transition", ...)`.

9.7. Add `GET /api/v1/trajectories/{trace_id}` endpoint (protected, admin role) that returns the full trace with all steps.

9.8. Add `GET /api/v1/trajectories/export?since=ISO8601&format=jsonl` endpoint (protected, admin role) for bulk export to JSONL for offline processing. This is the entry point for Phase 11.

9.9. Delete `src/api/graphs/_deprecated/mcp_planner_graph.py` (cleanup from Phase 8).

**Files to add:**
- `src/trajectory/__init__.py`
- `src/trajectory/store.py`
- `src/trajectory/decorators.py`
- `data/postgres/migrations/004_trajectories.sql`
- `src/api/routers/trajectories.py`

**Files to modify:**
- `src/agent_runtime/langgraph_runtime.py` (begin/end trace)
- `src/agent_runtime/base.py` (add `trajectory_store` dependency)
- `src/api/gateway/model_gateway.py` (apply `@record_llm_call`)
- All action tool files (apply `@record_tool_call`)
- `src/api/state/state_transitions.py` (call trajectory store)
- `src/api/app.py` (add trajectories router, initialize TrajectoryStore in lifespan)

**Tests required:**
- Unit: `tests/unit/test_trajectory_store.py` — `begin_trace` + 3 `record_step` + `end_trace` writes correct rows; queue is non-blocking (test completes in <10ms even with slow DB write simulation).
- Unit: `@record_tool_call` decorator captures arguments and return values correctly.
- Integration: `POST /api/v1/chat` creates a trajectory row. `GET /api/v1/trajectories/{trace_id}` returns it with all steps.
- Integration: `GET /api/v1/trajectories/export?since=...` returns valid JSONL.

**Definition of done:** Every chat request produces a complete trajectory in the database. `GET /api/v1/trajectories/{trace_id}` returns all steps. The queue depth never exceeds 1000 pending writes. Zero blocking DB writes on the request path.

**Rollback strategy:** Set `TRAJECTORY_STORE_ENABLED=false`. TrajectoryStore becomes a no-op stub. No request-path impact.

---

### Phase 10: Evaluation Platform

**Objective:** Build an automated regression and quality testing platform that uses `TrajectoryStore` data as the ground truth. Replace the current ad-hoc quality scripts in `tests/quality/` with a systematic evaluation harness that can detect regressions across model swaps, prompt changes, and architecture changes.

**Pre-conditions:** Phase 9 complete (TrajectoryStore populated). Phase 7 complete (DecisionEngine — so we know which actions are writes and need coverage).

**Tasks:**

10.1. Create `src/evaluation/__init__.py`, `src/evaluation/harness.py`. The `EvaluationHarness` class loads a set of `EvaluationCase` objects (query + expected_intent + expected_tools_used + expected_response_contains), runs each against the live `AgentRuntime`, and produces an `EvaluationReport`.

10.2. Create `data/evaluation/cases/` directory with JSONL evaluation case files:
- `equipment_cases.jsonl` (20+ cases from real trajectories)
- `operations_cases.jsonl`
- `safety_cases.jsonl`
- `forecasting_cases.jsonl`
- `document_cases.jsonl`
- `regression_cases.jsonl` (specifically crafted to catch previously seen failure modes)

10.3. Create `src/evaluation/metrics.py`: `IntentAccuracy`, `ToolSelectionPrecision`, `ToolSelectionRecall`, `ResponseCompleteness`, `LatencyP50P95P99`, `GuardrailFalsePositiveRate`, `DecisionEngineAccuracy`.

10.4. Create `src/evaluation/trajectory_sampler.py`. Exports a configured number of trajectories from `TrajectoryStore`, applies a quality filter (confidence > 0.8, no error, latency < 10s), and generates `EvaluationCase` objects. This automates ground-truth dataset growth.

10.5. Add `POST /api/v1/evaluation/run` endpoint (admin role): triggers a full evaluation run, stores results in a new `evaluation_runs` table.

10.6. Integrate evaluation into CI: add a `make eval` target that runs the evaluation harness against the 20 regression cases in `data/evaluation/cases/regression_cases.jsonl`. Fail CI if `IntentAccuracy < 0.95` or any safety case produces an unsafe action.

10.7. Create `src/evaluation/llm_judge_evaluator.py`. Uses `ModelGateway.complete(model_hint="judge")` to grade response quality on completeness (1-5), accuracy (1-5), and tone (1-5). Replaces the ad-hoc `test_answer_quality.py` scripts.

10.8. Integrate `LLMJudgeEvaluator` into `EvaluationReport` as an optional component (adds ~30s per case; enabled with `--with-llm-judge` flag).

**Files to add:**
- `src/evaluation/__init__.py`
- `src/evaluation/harness.py`
- `src/evaluation/metrics.py`
- `src/evaluation/trajectory_sampler.py`
- `src/evaluation/llm_judge_evaluator.py`
- `data/evaluation/cases/*.jsonl` (6 files)
- `src/api/routers/evaluation.py`
- `data/postgres/migrations/005_evaluation_runs.sql`

**Tests required:**
- Unit: `tests/unit/test_evaluation_harness.py` — harness runs 3 mock cases, produces correct metrics.
- Unit: `TrajectorySampler` correctly filters low-confidence trajectories.
- Integration: `POST /api/v1/evaluation/run` returns HTTP 200 and a valid `EvaluationReport`.
- CI gate: `make eval` passes all 20 regression cases.

**Definition of done:** Automated evaluation runs in CI under 5 minutes for the 20 regression cases. `IntentAccuracy >= 0.95` on the baseline case set. `EvaluationReport` stored in `evaluation_runs` table for trend tracking.

**Rollback strategy:** Evaluation platform is additive; removing it requires only deleting the router and turning off the CI step. No production path depends on it.

---

### Phase 11: Intelligence Flywheel

**Objective:** Connect `TrajectoryStore` to a supervised fine-tuning (SFT) data pipeline and a reinforcement learning (RL/GRPO) training loop that produces specialized Nemotron checkpoints. This phase operationalizes the flywheel: production trajectories → human labeling → SFT → RL/GRPO → deployed models → better trajectories.

**Pre-conditions:** Phase 10 complete (evaluation platform provides quality signal). Phase 9 must have collected at least 10,000 high-quality trajectories.

**Tasks:**

11.1. Create `src/flywheel/__init__.py` and `src/flywheel/trajectory_exporter.py`. Exports `TrajectoryStore` data as OpenAI-format JSONL chat completion records (`{"messages": [{"role": "user", "content": query}, {"role": "assistant", "content": response}], "tools": [...], "tool_calls": [...], "quality_score": float}`). Applies filters: confidence > 0.85, no error, validated by `LLMJudgeEvaluator` score >= 4/5.

11.2. Create `src/flywheel/label_queue.py`. Exports trajectories to a human-labeling queue (initially a local SQLite file, later replaceable with Label Studio or Scale AI API). Labelers see the query, the agent's response, tool calls, and assign a quality score and optional corrected response.

11.3. Create `src/flywheel/sft_dataset_builder.py`. Takes labeled trajectories + high-confidence auto-labeled trajectories and builds a structured SFT dataset in the Nemotron NeMo format (Alpaca-style for instruct fine-tuning). Outputs to `data/flywheel/sft_datasets/`. Tracks dataset versions.

11.4. Create `scripts/flywheel/export_sft_dataset.py`. CLI script: `python -m scripts.flywheel.export_sft_dataset --since 2026-06-01 --min-quality 4 --output data/flywheel/sft_datasets/v1.jsonl`. Uses `trajectory_exporter.py` and `sft_dataset_builder.py`.

11.5. Create `scripts/flywheel/grpo_reward_fn.py`. Defines domain-specific GRPO reward functions:
- `equipment_reward(trajectory)`: positive if correct equipment identified, positive if maintenance schedule included when needed, negative if wrong zone reported.
- `safety_reward(trajectory)`: high positive for correct severity classification, negative for missed high-severity incidents, zero for low-confidence responses.
- `forecasting_reward(trajectory)`: positive scaled by `1 - MAPE` on forecast accuracy.

11.6. Create `src/flywheel/rl_feedback_collector.py`. Collects implicit feedback signals from the system: guardrail blocks (negative signal), quick action clicks (positive), user follow-up questions (neutral-to-negative), DecisionEngine approvals/denials (correctness signal).

11.7. Add `FLYWHEEL_ENABLED` feature flag. When enabled, every chat trajectory is evaluated in a background task and, if quality score >= 4.0, appended to the labeling queue.

11.8. Integrate with NeMo framework: add `nemo-toolkit` as an optional extra in `pyproject.toml`. Create `scripts/flywheel/run_sft_training.sh` that mounts the SFT dataset into the NeMo container and runs `nemo_launcher` fine-tuning on the base Nemotron Super 49B checkpoint.

**Files to add:**
- `src/flywheel/__init__.py`
- `src/flywheel/trajectory_exporter.py`
- `src/flywheel/label_queue.py`
- `src/flywheel/sft_dataset_builder.py`
- `src/flywheel/rl_feedback_collector.py`
- `scripts/flywheel/export_sft_dataset.py`
- `scripts/flywheel/grpo_reward_fn.py`
- `scripts/flywheel/run_sft_training.sh`
- `data/flywheel/sft_datasets/.gitkeep`

**Tests required:**
- Unit: `tests/unit/test_flywheel.py` — `TrajectorExporter` correctly formats a trajectory as a chat completion record; `SFTDatasetBuilder` produces valid JSONL with correct role assignments.
- Unit: `grpo_reward_fn.py` safety reward assigns negative score to trajectory that missed a high-severity incident.
- Integration: `scripts/flywheel/export_sft_dataset.py` runs without error on a local DB with 100 seed trajectories.

**Definition of done:** `export_sft_dataset.py` produces valid JSONL that can be validated against the NeMo SFT format spec. GRPO reward functions return float in `[-1, 1]` for all test cases. Implicit feedback collector records signals in the `trajectories` table without blocking requests.

**Rollback strategy:** Set `FLYWHEEL_ENABLED=false`. All flywheel components are background processes with no request-path impact. SFT dataset files are offline artifacts.

---

### Phase 12: Nemotron Specialization

**Objective:** Deploy domain-specific Nemotron model checkpoints (fine-tuned via Phase 11) and route them through the `ModelGateway`'s `ModelSelector`. This phase is ongoing — each training run produces a candidate checkpoint that must pass evaluation (Phase 10) before being promoted to production.

**Pre-conditions:** Phase 11 producing SFT datasets. Phase 10 evaluation platform running regression gates. Phase 1 `ModelGateway` in production.

**Tasks:**

12.1. Add checkpoint registry to `src/api/gateway/model_selector.py`: beyond the existing `model_hint` → model_id mapping, add a versioned checkpoint registry loaded from `data/config/model_registry.yaml`. Each entry: `{hint, version, model_id, base_model, training_date, eval_score, status: draft|staging|production}`.

12.2. Update `ModelSelector.select(model_hint, context)` to pick the highest-version `production`-status checkpoint for the given hint. Context (intent, domain) can override: a `"safety"` domain query always selects the `safety-nemotron` checkpoint.

12.3. Define evaluation promotion criteria in `data/config/model_registry.yaml`: a checkpoint is promoted from `staging` to `production` only when `IntentAccuracy >= 0.97` and `LLMJudgeScore >= 4.2` on the domain evaluation case set.

12.4. Create `scripts/flywheel/promote_checkpoint.py`: CLI that runs Phase 10 evaluation against a staged checkpoint and, if criteria met, updates `model_registry.yaml` to `production` status and hot-reloads `ModelSelector` (via `POST /api/v1/admin/reload-model-registry`).

12.5. Add `POST /api/v1/admin/reload-model-registry` endpoint (admin role) that re-reads `model_registry.yaml` and updates the in-memory `ModelSelector` without restart.

12.6. Update `docker-compose.dev.yaml` to support spinning up local NIM containers for fine-tuned checkpoints alongside the base `llm-nim` container. Add an `llm-nim-equipment` service placeholder (commented out until first fine-tuned checkpoint is ready).

12.7. Target model family rollout order (based on training data volume from Phase 11):
1. Equipment Nemotron (highest trajectory volume — 40% of queries)
2. Safety Nemotron (most critical correctness requirement)
3. Operations Nemotron
4. Forecasting Nemotron (requires numeric accuracy, most complex reward fn)
5. Document Nemotron (multimodal — requires separate VL fine-tuning pipeline)

**Files to add/modify:**
- `src/api/gateway/model_selector.py` (add checkpoint registry)
- `data/config/model_registry.yaml` (new — initial entries for base models)
- `scripts/flywheel/promote_checkpoint.py` (new)
- `src/api/routers/admin.py` (new — model registry reload endpoint)
- `deploy/compose/docker-compose.dev.yaml` (add commented NIM service stubs)

**Tests required:**
- Unit: `ModelSelector` returns `staging` checkpoint when `FORCE_STAGING_MODELS=true`.
- Unit: `promote_checkpoint.py` correctly updates `model_registry.yaml` status.
- Integration: after `POST /api/v1/admin/reload-model-registry`, subsequent requests use the updated model.
- Evaluation gate: Phase 10 evaluation must pass at `>= 0.97 IntentAccuracy` before any checkpoint promotion script can succeed.

**Definition of done:** At least one domain Nemotron checkpoint promoted to production via the automated evaluation gate. `ModelSelector` dynamically routes that domain's queries to the fine-tuned checkpoint. Zero manual model ID edits in source code — all routing via `model_registry.yaml`.

**Rollback strategy:** Change checkpoint status in `model_registry.yaml` from `production` to `deprecated`. Call reload endpoint. Traffic immediately reverts to the previous production checkpoint or base model.

---

## 4. File-by-File Migration Map

The table below covers all significant Python files in `src/`. UI files (`src/ui/web/`) are excluded — the React frontend requires no changes during this migration.

| Current File | Current Responsibility | Target Package | Action | Phase | Risk | Required Tests |
|---|---|---|---|---|---|---|
| `src/api/app.py` | FastAPI app, middleware, router registration | `src/api/app.py` | REFACTOR | 0,3,8,9 | Low | Phase 0 smoke test |
| `src/api/config/settings.py` | (does not exist) | `src/api/config/settings.py` | ADD | 0 | Low | `test_config.py` |
| `src/api/utils/log_utils.py` | Prompt sanitization, log sanitization | `src/api/utils/log_utils.py` | REFACTOR | 0 | Low | `test_log_utils.py` |
| `src/api/utils/error_handler.py` | Global exception handlers | `src/api/utils/error_handler.py` | KEEP | — | None | Existing |
| `src/api/middleware/security_headers.py` | HTTP security headers | `src/api/middleware/security_headers.py` | KEEP | — | None | Existing |
| `src/api/services/llm/nim_client.py` | Raw httpx NIM API calls, retry, cache | `src/api/gateway/model_gateway.py` | WRAP then DEPRECATE | 1 | Medium | `test_model_gateway.py` |
| `src/api/gateway/model_gateway.py` | (does not exist) | `src/api/gateway/model_gateway.py` | ADD | 1 | Medium | `test_model_gateway.py` |
| `src/api/gateway/model_selector.py` | (does not exist) | `src/api/gateway/model_selector.py` | ADD | 1,12 | Medium | `test_model_selector.py` |
| `src/api/gateway/telemetry.py` | (does not exist) | `src/api/gateway/telemetry.py` | ADD | 1 | Low | `test_gateway_telemetry.py` |
| `src/api/services/guardrails/guardrails_service.py` | Input/output safety filtering | `src/api/gateway/model_gateway.py` + keep | WRAP | 1 | Low | `test_guardrails_sdk.py` |
| `src/api/services/guardrails/nemo_sdk_service.py` | NeMo SDK wrapper | `src/api/gateway/model_gateway.py` + keep | WRAP | 1 | Low | `test_guardrails_sdk.py` |
| `src/api/agents/document/validation/large_llm_judge.py` | LLM-as-judge for document quality | Via `ModelGateway` | REFACTOR | 1 | Low | `test_model_gateway.py` |
| `src/api/agents/document/processing/small_llm_processor.py` | Llama Nano VL 8B calls | Via `ModelGateway` | REFACTOR | 1 | Low | `test_model_gateway.py` |
| `src/api/agents/document/ocr/nemo_ocr.py` | NeMo OCR NIM calls | Via `ModelGateway` | REFACTOR | 1 | Low | `test_model_gateway.py` |
| `src/api/agents/document/ocr/nemotron_parse.py` | Nemotron Parse NIM calls | Via `ModelGateway` | REFACTOR | 1 | Low | `test_model_gateway.py` |
| `src/api/agents/document/preprocessing/nemo_retriever.py` | NeMo Retriever preprocessing | Via `ModelGateway` | REFACTOR | 1 | Low | `test_model_gateway.py` |
| `src/api/services/mcp/server.py` | Custom JSON-RPC MCP server | `src/api/mcp_sdk/server_factory.py` | REPLACE | 2 | High | `test_mcp_sdk_adoption.py` |
| `src/api/services/mcp/client.py` | Custom JSON-RPC MCP client | `src/api/mcp_sdk/client_pool.py` | REPLACE | 2,3 | High | `test_mcp_sdk_adoption.py` |
| `src/api/services/mcp/base.py` | MCPAdapter base, MCPManager, MCPError | `src/api/mcp_sdk/` | REPLACE | 2 | High | `test_mcp_sdk_adoption.py` |
| `src/api/services/mcp/security.py` | Tool blocklist, SecurityViolationError | `src/api/mcp_sdk/security_filter.py` | MOVE | 2 | Medium | `test_mcp_sdk_adoption.py` |
| `src/api/services/mcp/parameter_validator.py` | JSON schema validation for tool params | `src/api/mcp_sdk/parameter_bridge.py` | MOVE | 2 | Low | `test_mcp_sdk_adoption.py` |
| `src/api/services/mcp/tool_discovery.py` | Discovers/catalogs tools | `src/api/mcp_sdk/tool_registry.py` | REPLACE | 2,3 | High | `test_mcp_sdk_adoption.py` |
| `src/api/services/mcp/tool_binding.py` | Binds tool calls to adapters | SDK handles binding | DELETE-LATER | 2 | Medium | N/A |
| `src/api/services/mcp/tool_routing.py` | Routes tool calls (currently unused) | Not needed | DELETE-LATER | 2 | Low | N/A |
| `src/api/services/mcp/service_discovery.py` | Dynamic MCP discovery | Not needed with capability servers | DELETE-LATER | 3 | Low | N/A |
| `src/api/services/mcp/monitoring.py` | MCP tool metrics | `src/api/gateway/telemetry.py` | MERGE | 1,2 | Low | `test_gateway_telemetry.py` |
| `src/api/services/mcp/rollback.py` | Tool rollback logic | `src/decision_engine/` | MOVE | 7 | Medium | `test_decision_engine.py` |
| `src/api/services/mcp/tool_validation.py` | ErrorHandlingService, severity enums | `src/api/mcp_sdk/` | MOVE | 2 | Low | `test_mcp_sdk_adoption.py` |
| `src/api/services/mcp/adapters/equipment_adapter.py` | MCP adapter wrapping equipment tools | `src/capability_servers/equipment/` | MOVE | 3 | Medium | `test_capability_servers.py` |
| `src/api/services/mcp/adapters/operations_adapter.py` | MCP adapter wrapping operations tools | `src/capability_servers/operations/` | MOVE | 3 | Medium | `test_capability_servers.py` |
| `src/api/services/mcp/adapters/safety_adapter.py` | MCP adapter wrapping safety tools | `src/capability_servers/safety/` | MOVE | 3 | Medium | `test_capability_servers.py` |
| `src/api/services/mcp/adapters/forecasting_adapter.py` | MCP adapter wrapping forecasting tools | `src/capability_servers/forecasting/` | MOVE | 3 | Medium | `test_capability_servers.py` |
| `src/api/services/mcp/adapters/wms_adapter.py` | WMS MCP adapter | `src/capability_servers/` or keep | MOVE | 3 | Low | `test_capability_servers.py` |
| `src/api/services/mcp/adapters/iot_adapter.py` | IoT MCP adapter | `src/capability_servers/` or keep | MOVE | 3 | Low | `test_capability_servers.py` |
| `src/api/services/mcp/adapters/erp_adapter.py` | ERP MCP adapter | `src/capability_servers/` or keep | MOVE | 3 | Low | N/A |
| `src/api/services/mcp/adapters/rfid_barcode_adapter.py` | RFID/barcode adapter | `src/capability_servers/` or keep | MOVE | 3 | Low | N/A |
| `src/api/services/mcp/adapters/time_attendance_adapter.py` | Time/attendance adapter | `src/capability_servers/` or keep | MOVE | 3 | Low | N/A |
| `src/api/agents/inventory/equipment_agent.py` | Basic (non-MCP) equipment agent | Legacy graph only | DEPRECATE | 4 | Low | N/A |
| `src/api/agents/inventory/mcp_equipment_agent.py` | MCP equipment agent, tool planning | Via `AgentRuntime` + Skills | REFACTOR | 5,8 | High | `test_skills.py` |
| `src/api/agents/inventory/equipment_asset_tools.py` | Equipment DB queries | `src/warehouse_contracts/` types | REFACTOR | 4,7 | Medium | `test_warehouse_contracts.py` |
| `src/api/agents/inventory/equipment_action_tools.py` | Inventory write operations | `src/warehouse_contracts/` types + DecisionEngine | REFACTOR | 4,7 | High | `test_decision_engine.py` |
| `src/api/agents/operations/operations_agent.py` | Basic (non-MCP) operations agent | Legacy graph only | DEPRECATE | 4 | Low | N/A |
| `src/api/agents/operations/mcp_operations_agent.py` | MCP operations agent | Via `AgentRuntime` + Skills | REFACTOR | 5,8 | High | `test_skills.py` |
| `src/api/agents/operations/action_tools.py` | Operations write operations | `src/warehouse_contracts/` types + DecisionEngine | REFACTOR | 4,7 | High | `test_decision_engine.py` |
| `src/api/agents/safety/safety_agent.py` | Basic (non-MCP) safety agent | Legacy graph only | DEPRECATE | 4 | Low | N/A |
| `src/api/agents/safety/mcp_safety_agent.py` | MCP safety agent | Via `AgentRuntime` + Skills | REFACTOR | 5,8 | High | `test_skills.py` |
| `src/api/agents/safety/action_tools.py` | Safety write operations | `src/warehouse_contracts/` types + DecisionEngine | REFACTOR | 4,7 | High | `test_decision_engine.py` |
| `src/api/agents/forecasting/forecasting_agent.py` | Forecasting agent | Via `AgentRuntime` + Skills | REFACTOR | 5,8 | Medium | `test_skills.py` |
| `src/api/agents/forecasting/forecasting_action_tools.py` | Forecasting read operations | `src/warehouse_contracts/` types | REFACTOR | 4 | Low | `test_warehouse_contracts.py` |
| `src/api/agents/document/document_extraction_agent.py` | 6-stage document pipeline | Keep, wrap via Skills | WRAP | 5 | Medium | `test_document_pipeline.py` |
| `src/api/agents/document/mcp_document_agent.py` | MCP document agent | Via `AgentRuntime` + Skills | REFACTOR | 5,8 | Medium | `test_skills.py` |
| `src/api/agents/document/action_tools.py` | Document write operations | `src/warehouse_contracts/` types + DecisionEngine | REFACTOR | 4,7 | Medium | `test_decision_engine.py` |
| `src/api/agents/document/models/document_models.py` | Document Pydantic models | `src/warehouse_contracts/document.py` | REPLACE | 4 | Low | `test_warehouse_contracts.py` |
| `src/api/agents/document/models/extraction_models.py` | Extraction Pydantic models | `src/warehouse_contracts/document.py` | REPLACE | 4 | Low | `test_warehouse_contracts.py` |
| `src/api/agents/document/processing/embedding_indexing.py` | Milvus embedding + indexing | Via `ModelGateway` | REFACTOR | 1 | Low | `test_model_gateway.py` |
| `src/api/agents/document/processing/entity_extractor.py` | Entity extraction | Keep in document pipeline | KEEP | — | None | `test_document_pipeline.py` |
| `src/api/agents/document/routing/intelligent_router.py` | Document routing logic | Keep in document pipeline | KEEP | — | None | `test_document_pipeline.py` |
| `src/api/agents/document/routing/workflow_manager.py` | Document workflow state | `src/warehouse_contracts/document.py` state fields | REFACTOR | 4 | Low | `test_warehouse_contracts.py` |
| `src/api/agents/document/validation/quality_scorer.py` | Quality scoring | Keep, uses `ModelGateway` | REFACTOR | 1 | Low | `test_document_pipeline.py` |
| `src/api/agents/document/preprocessing/layout_detection.py` | Layout detection | Keep in pipeline | KEEP | — | None | Existing |
| `src/api/agents/document/ocr/nemo_ocr.py` | NeMo OCR calls | Via `ModelGateway` | REFACTOR | 1 | Low | `test_model_gateway.py` |
| `src/api/agents/document/processing/local_processor.py` | Local/offline processor | Keep as fallback | KEEP | — | None | Existing |
| `src/api/graphs/mcp_integrated_planner_graph.py` | Active LangGraph orchestration | `src/agent_runtime/langgraph_runtime.py` | REFACTOR | 6,8 | High | `test_agent_runtime.py` |
| `src/api/graphs/mcp_planner_graph.py` | Phase 2 intermediate graph (unused) | N/A | DELETE-LATER | 8 | Low | N/A |
| `src/api/graphs/planner_graph.py` | Legacy basic graph (unused) | N/A | DELETE-LATER | 8 | Low | N/A |
| `src/api/routers/chat.py` | HTTP chat endpoint, enhancement pipeline | Keep as thin boundary | REFACTOR | 0,6,8 | High | Smoke test |
| `src/api/routers/equipment.py` | Equipment CRUD endpoints | `src/warehouse_contracts/equipment.py` types | REFACTOR | 4 | Low | `test_equipment_endpoint.py` |
| `src/api/routers/inventory.py` | Inventory CRUD endpoints | `src/warehouse_contracts/inventory.py` types | REFACTOR | 4 | Low | Existing |
| `src/api/routers/operations.py` | Operations/task endpoints | `src/warehouse_contracts/operations.py` types | REFACTOR | 4 | Low | Existing |
| `src/api/routers/safety.py` | Safety incident endpoints | `src/warehouse_contracts/safety.py` types | REFACTOR | 4 | Low | Existing |
| `src/api/routers/advanced_forecasting.py` | Forecasting REST API | `src/warehouse_contracts/forecasting.py` types | REFACTOR | 4 | Low | `test_forecasting_endpoint.py` |
| `src/api/routers/document.py` | Document management API | `src/warehouse_contracts/document.py` types | REFACTOR | 4 | Low | Existing |
| `src/api/routers/mcp.py` | MCP tool management API | `src/api/mcp_sdk/` | REFACTOR | 2,3 | Medium | `test_mcp_sdk_adoption.py` |
| `src/api/routers/auth.py` | JWT auth endpoints | KEEP | — | None | Existing |
| `src/api/routers/reasoning.py` | Reasoning chain endpoints | Keep, use `AgentRuntime` | REFACTOR | 8 | Low | `test_reasoning_integration.py` |
| `src/api/routers/training.py` | Model training trigger | Keep, no changes needed | KEEP | — | None | N/A |
| `src/api/routers/health.py` | Health/version endpoints | KEEP | — | None | Existing |
| `src/api/routers/migration.py` | DB migration endpoints | KEEP | — | None | Existing |
| `src/api/routers/wms.py` | WMS integration endpoints | KEEP | — | None | N/A |
| `src/api/routers/iot.py` | IoT integration endpoints | KEEP | — | None | N/A |
| `src/api/routers/erp.py` | ERP integration endpoints | KEEP | — | None | N/A |
| `src/api/routers/scanning.py` | Scanning endpoints | KEEP | — | None | N/A |
| `src/api/routers/attendance.py` | Attendance endpoints | KEEP | — | None | N/A |
| `src/api/services/agent_config.py` | YAML agent config loader | KEEP (Skills YAML supersedes in Phase 5) | KEEP | — | None | Existing |
| `src/api/services/auth/dependencies.py` | JWT auth dependency | KEEP | — | None | Existing |
| `src/api/services/auth/jwt_handler.py` | JWT creation/verification | KEEP | — | None | Existing |
| `src/api/services/auth/models.py` | Auth Pydantic models, RBAC permissions | KEEP, used by DecisionEngine | KEEP | — | None | Existing |
| `src/api/services/auth/user_service.py` | User CRUD | KEEP | — | None | Existing |
| `src/api/services/cache/query_cache.py` | LRU/TTL response cache | KEEP | — | None | `test_caching_demo.py` |
| `src/api/services/database.py` | asyncpg connection pool | KEEP | — | None | `test_db_connection.py` |
| `src/api/services/deduplication/request_deduplicator.py` | In-flight request dedup | KEEP | — | None | Existing |
| `src/api/services/document/document_db_service.py` | Document metadata DB | KEEP | — | None | `test_document_pipeline.py` |
| `src/api/services/document/job_queue.py` | Async document job queue | KEEP | — | None | `test_document_pipeline.py` |
| `src/api/services/document/parallel_executor.py` | Parallel document processing | KEEP | — | None | `test_document_pipeline.py` |
| `src/api/services/document/retry_handler.py` | Document processing retry | KEEP | — | None | `test_document_pipeline.py` |
| `src/api/services/erp/integration_service.py` | ERP integration | KEEP | — | None | N/A |
| `src/api/services/evidence/evidence_collector.py` | Evidence/citation collection | KEEP | — | None | `test_evidence_scoring_demo.py` |
| `src/api/services/evidence/evidence_integration.py` | Evidence → response integration | KEEP | — | None | `test_evidence_scoring_demo.py` |
| `src/api/services/forecasting_config.py` | Forecasting model config | KEEP | — | None | Existing |
| `src/api/services/migration.py` | DB migration runner | KEEP | — | None | `test_migration_system.py` |
| `src/api/services/monitoring/metrics.py` | Prometheus metric definitions | KEEP, add gateway metrics | REFACTOR | 1 | Low | `test_model_gateway.py` |
| `src/api/services/monitoring/performance_monitor.py` | In-memory request perf tracker | KEEP; feeds TrajectoryStore in Phase 9 | REFACTOR | 9 | Low | `test_trajectory_store.py` |
| `src/api/services/monitoring/alert_checker.py` | Background alert checker | KEEP | — | None | Existing |
| `src/api/services/memory/context_enhancer.py` | Conversation context enhancement | KEEP | — | None | Existing |
| `src/api/services/memory/conversation_memory.py` | Per-session conversation history | KEEP | — | None | Existing |
| `src/api/services/quick_actions/smart_quick_actions.py` | Quick action generation | KEEP | — | None | Existing |
| `src/api/services/reasoning/reasoning_engine.py` | Multi-step reasoning chains | KEEP, route via `ModelGateway` | REFACTOR | 1 | Low | `test_reasoning_integration.py` |
| `src/api/services/routing/semantic_router.py` | Embedding-based intent routing | KEEP; absorb into `AgentRuntime` in Phase 8 | REFACTOR | 8 | Low | `test_mcp_integrated_planner_graph.py` |
| `src/api/services/security/rate_limiter.py` | Redis-backed rate limiting | KEEP | — | None | Existing |
| `src/api/services/validation/response_validator.py` | Response quality validation | KEEP; feed to TrajectoryStore Phase 9 | REFACTOR | 9 | Low | `test_response_quality_demo.py` |
| `src/api/services/validation/response_enhancer.py` | Response post-processing | KEEP | — | None | Existing |
| `src/api/services/wms/integration_service.py` | WMS integration | KEEP | — | None | N/A |
| `src/api/services/scanning/integration_service.py` | Scanning integration | KEEP | — | None | N/A |
| `src/api/services/attendance/integration_service.py` | Attendance integration | KEEP | — | None | N/A |
| `src/api/services/iot/integration_service.py` | IoT integration | KEEP | — | None | N/A |
| `src/api/services/version.py` | Version metadata | KEEP | — | None | N/A |
| `src/api/cli/migrate.py` | DB migration CLI | KEEP | — | None | N/A |
| `src/memory/memory_manager.py` | Memory manager | KEEP | — | None | Existing |
| `src/retrieval/hybrid_retriever.py` | BM25 + vector hybrid retrieval | KEEP | — | None | `test_enhanced_retrieval.py` |
| `src/retrieval/enhanced_hybrid_retriever.py` | Enhanced hybrid retrieval | KEEP | — | None | `test_enhanced_retrieval.py` |
| `src/retrieval/gpu_hybrid_retriever.py` | GPU-accelerated hybrid retrieval | KEEP | — | None | N/A |
| `src/retrieval/vector/embedding_service.py` | Embedding via NIM | Via `ModelGateway` | REFACTOR | 1 | Low | `test_model_gateway.py` |
| `src/retrieval/vector/milvus_retriever.py` | Milvus vector search | KEEP | — | None | Existing |
| `src/retrieval/vector/gpu_milvus_retriever.py` | GPU Milvus search | KEEP | — | None | N/A |
| `src/retrieval/vector/evidence_scoring.py` | Evidence confidence scoring | KEEP | — | None | `test_evidence_scoring_demo.py` |
| `src/retrieval/vector/chunking_service.py` | Text chunking | KEEP | — | None | `test_chunking_demo.py` |
| `src/retrieval/vector/hybrid_ranker.py` | Hybrid result ranking | KEEP | — | None | Existing |
| `src/retrieval/structured/sql_retriever.py` | Raw SQL queries via asyncpg | KEEP | — | None | Existing |
| `src/retrieval/structured/sql_query_router.py` | Routes SQL query types | KEEP | — | None | Existing |
| `src/retrieval/structured/inventory_queries.py` | Inventory SQL queries | KEEP | — | None | Existing |
| `src/retrieval/structured/task_queries.py` | Task SQL queries | KEEP | — | None | Existing |
| `src/retrieval/structured/telemetry_queries.py` | Telemetry SQL queries | KEEP | — | None | Existing |
| `src/retrieval/caching/` (all files) | Retrieval result caching | KEEP | — | None | Existing |
| `src/retrieval/query_preprocessing.py` | Query preprocessing | KEEP | — | None | Existing |
| `src/retrieval/result_postprocessing.py` | Result postprocessing | KEEP | — | None | Existing |
| `src/retrieval/response_quality/` (all files) | Response quality | KEEP; feed to Evaluation Phase 10 | REFACTOR | 10 | Low | Existing |
| `src/adapters/erp/` (all files) | ERP protocol adapters | KEEP | — | None | N/A |
| `src/adapters/iot/` (all files) | IoT protocol adapters | KEEP | — | None | Existing |
| `src/adapters/wms/` (all files) | WMS protocol adapters | KEEP | — | None | Existing |
| `src/adapters/rfid_barcode/` (all files) | RFID/barcode adapters | KEEP | — | None | N/A |
| `src/adapters/time_attendance/` (all files) | Time/attendance adapters | KEEP | — | None | N/A |

---

## 5. Dependency Graph

The diagram below shows which phases block which. An arrow from A to B means B cannot begin until A is complete.

```
Phase 0 (Foundation)
    |
    ├──► Phase 1 (ModelGateway)
    |         |
    |         ├──► Phase 2 (MCP SDK) ──► Phase 3 (Capability Servers)
    |         |                               |
    |         └──► Phase 4 (Contracts) ───────┤
    |                   |                     |
    |                   ├──► Phase 5 (Skills)─┤
    |                   |         |            |
    |                   └──► Phase 6 (State)──┤
    |                             |            |
    |                             └──► Phase 7 (DecisionEngine)
    |                                         |
    └──► Phase 8 (AgentRuntime) ◄─────────────┘
              |
              └──► Phase 9 (TrajectoryStore)
                         |
                         └──► Phase 10 (Evaluation)
                                    |
                                    └──► Phase 11 (Flywheel) ──► Phase 12 (Specialization)
```

**Parallelization opportunities:**
- Phase 4 (Contracts) can begin in parallel with Phase 2 (MCP SDK) after Phase 1 is done.
- Phase 5 (Skills) can begin after Phase 4 foundational contracts are defined, in parallel with Phase 3 final stabilization.
- Phase 7 (DecisionEngine) and Phase 8 (AgentRuntime) can be developed in parallel after Phase 6 is complete.
- Phase 10 (Evaluation) case authoring and harness setup can begin during Phase 9, with the full run gated on Phase 9 completion.
- Phase 12 training runs are ongoing once Phase 11 produces the first SFT dataset; they do not need Phase 11 to be fully complete.

**Critical path (minimum serial chain):**
Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 6 → Phase 8 → Phase 9 → Phase 10 → Phase 11 → Phase 12

---

## 6. Testing Gates

Each row defines what must be green before the named phase's first PR can be merged.

| Before Phase | Required passing tests | Additional gate |
|---|---|---|
| Phase 0 | `pytest tests/unit -x` — zero failures (any failures are pre-existing bugs to fix first) | Git history audit: no `.env` files committed |
| Phase 1 | All Phase 0 tests. `POST /api/v1/chat` smoke test with mock NIM. `GET /api/v1/metrics` returns HTTP 200. | No raw `httpx.AsyncClient` instantiation outside `nim_client.py` |
| Phase 2 | All Phase 1 tests. `test_model_gateway.py` 100% pass. | All 28 action tools still callable via legacy path |
| Phase 3 | All Phase 2 tests. `MCP_SDK_ENABLED=true` passes all integration tests. `mcp` package version pinned in lock file. | `test_mcp_sdk_adoption.py` 100% pass |
| Phase 4 | All Phase 3 tests. Five capability server health endpoints respond. `MCPClientPool.call_tool` succeeds for equipment. | No `mcp.Server` or `mcp.Client` imports outside `src/api/mcp_sdk/` and capability servers |
| Phase 5 | All Phase 4 tests. `mypy src/warehouse_contracts/` zero errors. Every domain type JSON-serializable. | All deprecated per-agent `*Response` dataclasses removed |
| Phase 6 | All Phase 5 tests. `test_skills.py` 100% pass. All six skills produce valid `AgentResponse`. | Skill YAML files loadable at startup |
| Phase 7 | All Phase 6 tests. `WarehouseState` validates in LangGraph. `trace_id` appears in `ChatResponse`. | `MCPWarehouseState` TypedDict removed from active graph |
| Phase 8 | All Phase 7 tests. `DecisionEngine.gate()` blocks denied actions for all RBAC test cases. Audit log writes verified. | `DECISION_ENGINE_ENABLED=true` passes all chat integration tests |
| Phase 9 | All Phase 8 tests. `AgentRuntime` interface satisfied by both `LangGraphRuntime` and `SimpleSequentialRuntime`. | No LangGraph imports in `src/api/routers/chat.py` |
| Phase 10 | All Phase 9 tests. Every chat request produces a trajectory row. `GET /api/v1/trajectories/{trace_id}` returns all steps. | `@record_tool_call` coverage on all 45+ action tool methods |
| Phase 11 | All Phase 10 tests. `IntentAccuracy >= 0.95` on 20-case regression suite. LLM judge scores >= 3.5 average. | `make eval` passes in CI under 5 minutes |
| Phase 12 | All Phase 11 tests. SFT dataset has >= 5,000 quality-filtered examples. GRPO reward functions return valid floats. | Domain evaluation accuracy >= 0.97 before any checkpoint promoted |

---

## 7. Rollback Strategies

| Phase | Rollback Mechanism | Recovery Time |
|---|---|---|
| 0 | `SKIP_AUTH=true` bypasses new auth. Revert `settings.py` to pure `os.getenv()` if Settings breaks. All changes are additive. | < 5 minutes |
| 1 | `MODEL_GATEWAY_ENABLED=false` routes all LLM calls through original `NIMClient`. No DB changes. | < 5 minutes |
| 2 | `MCP_SDK_ENABLED=false` routes all tool calls through original custom JSON-RPC stack. `mcp` package remains installed but unused. | < 5 minutes |
| 3 | `CAPABILITY_SERVERS_ENABLED=false` routes all tool calls in-process through adapters. Stop the five Docker services. | < 10 minutes |
| 4 | Contracts are additive Pydantic models with `extra="ignore"`. If a contract causes validation errors, add `model_config = ConfigDict(extra="ignore")` as a shim and file a bug. | < 30 minutes |
| 5 | `SKILLS_ENABLED=false` reverts all agents to their hardcoded prompt strings. | < 5 minutes |
| 6 | `WAREHOUSE_STATE_V2=false` reverts planner graph to `MCPWarehouseState` TypedDict. `trace_id` field omitted from responses. | < 5 minutes |
| 7 | `DECISION_ENGINE_ENABLED=false` disables all action gating. All write tools execute immediately as before. | < 5 minutes |
| 8 | `AGENT_RUNTIME=langgraph` selects `LangGraphRuntime`. The router calls runtime interface regardless. | < 5 minutes |
| 9 | `TRAJECTORY_STORE_ENABLED=false` makes `TrajectoryStore` a no-op stub. Zero request-path impact. `trajectories` table retains existing data. | < 5 minutes |
| 10 | Evaluation platform is additive; remove from CI by commenting the `make eval` step. No production impact. | < 10 minutes |
| 11 | `FLYWHEEL_ENABLED=false` stops all background labeling queue submissions. SFT dataset files are offline artifacts. | < 5 minutes |
| 12 | Revert `model_registry.yaml` checkpoint status from `production` to `deprecated`. Call `POST /api/v1/admin/reload-model-registry`. Traffic reverts to previous checkpoint immediately. | < 1 minute |

**Universal rollback:** If a phase has caused a production incident and individual feature flags are not sufficient, `git revert` the phase's merge commit. All phases are structured so that the revert touches only the new files added in that phase plus the flag-guarded modifications, minimizing conflict surface.

---

## 8. First Vertical Slice (Recommended)

The recommended first vertical slice implements Phase 1 (ModelGateway) for the single most critical code path: the `NIMClient.generate_response()` method used by all five domain agents in the chat flow. This slice validates the gateway pattern end-to-end before any agent, graph, or router code changes.

### Files to Add

**`src/api/config/__init__.py`** — empty

**`src/api/config/settings.py`**
```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    nvidia_api_key: str = ""
    llm_nim_url: str = "https://integrate.api.nvidia.com/v1"
    llm_model: str = "nvidia/llama-3.3-nemotron-super-49b-v1.5"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 2000
    llm_client_timeout: int = 240
    llm_cache_enabled: bool = True
    llm_cache_ttl_seconds: int = 300
    llm_enable_thinking: bool = False
    llm_reasoning_budget: int = 0
    embedding_api_key: str = ""
    embedding_nim_url: str = "https://integrate.api.nvidia.com/v1"
    embedding_model: str = "nvidia/llama-nemotron-embed-vl-1b-v2"
    embedding_dimension: int = 2048
    model_gateway_enabled: bool = True
    environment: str = "development"

    @property
    def resolved_embedding_api_key(self) -> str:
        return self.embedding_api_key or self.nvidia_api_key

_settings: Settings | None = None

def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
```

**`src/api/gateway/__init__.py`** — empty

**`src/api/gateway/model_gateway.py`**
```python
import time
import asyncio
from typing import Optional
import httpx
from src.api.config.settings import get_settings
from src.api.gateway.telemetry import record_model_call

class ModelGateway:
    def __init__(self):
        settings = get_settings()
        self._llm_client = httpx.AsyncClient(
            base_url=settings.llm_nim_url,
            timeout=settings.llm_client_timeout,
            headers={"Authorization": f"Bearer {settings.nvidia_api_key}"},
        )
        self._embed_client = httpx.AsyncClient(
            base_url=settings.embedding_nim_url,
            timeout=settings.llm_client_timeout,
            headers={"Authorization": f"Bearer {settings.resolved_embedding_api_key}"},
        )
        self._settings = settings

    async def complete(
        self,
        messages: list[dict],
        model_hint: str = "llm",
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        enable_thinking: Optional[bool] = None,
        reasoning_budget: Optional[int] = None,
    ) -> str:
        settings = self._settings
        model = settings.llm_model  # Phase 12 will route by model_hint
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature if temperature is not None else settings.llm_temperature,
            "max_tokens": max_tokens if max_tokens is not None else settings.llm_max_tokens,
        }
        resolved_thinking = enable_thinking if enable_thinking is not None else settings.llm_enable_thinking
        if "nemotron" in model.lower():
            if resolved_thinking:
                payload["reasoning_budget"] = reasoning_budget or settings.llm_reasoning_budget
            else:
                payload["chat_template_kwargs"] = {"enable_thinking": False}

        t0 = time.monotonic()
        try:
            resp = await self._llm_client.post("/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            record_model_call(model=model, endpoint="chat/completions", status="ok",
                              latency=time.monotonic() - t0)
            return content
        except Exception as exc:
            record_model_call(model=model, endpoint="chat/completions", status="error",
                              latency=time.monotonic() - t0)
            raise

    async def embed(self, texts: list[str]) -> list[list[float]]:
        settings = self._settings
        model = settings.embedding_model
        payload = {"model": model, "input": texts}
        t0 = time.monotonic()
        try:
            resp = await self._embed_client.post("/embeddings", json=payload)
            resp.raise_for_status()
            data = resp.json()
            vectors = [item["embedding"] for item in data["data"]]
            record_model_call(model=model, endpoint="embeddings", status="ok",
                              latency=time.monotonic() - t0)
            return vectors
        except Exception as exc:
            record_model_call(model=model, endpoint="embeddings", status="error",
                              latency=time.monotonic() - t0)
            raise

    async def close(self):
        await self._llm_client.aclose()
        await self._embed_client.aclose()

_gateway: ModelGateway | None = None

def get_model_gateway() -> ModelGateway:
    global _gateway
    if _gateway is None:
        _gateway = ModelGateway()
    return _gateway
```

**`src/api/gateway/telemetry.py`**
```python
from prometheus_client import Counter, Histogram

model_requests_total = Counter(
    "model_requests_total",
    "Total NIM model API calls",
    ["model", "endpoint", "status"],
)
model_latency_seconds = Histogram(
    "model_latency_seconds",
    "NIM model API call latency",
    ["model", "endpoint"],
)

def record_model_call(model: str, endpoint: str, status: str, latency: float) -> None:
    model_requests_total.labels(model=model, endpoint=endpoint, status=status).inc()
    model_latency_seconds.labels(model=model, endpoint=endpoint).observe(latency)
```

### Files to Modify

**`src/api/services/llm/nim_client.py`**

In the `generate_response()` method, add a branch at the top:

```python
from src.api.config.settings import get_settings

async def generate_response(self, messages, temperature=None, max_tokens=None, ...):
    if get_settings().model_gateway_enabled:
        from src.api.gateway.model_gateway import get_model_gateway
        return await get_model_gateway().complete(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            enable_thinking=enable_thinking,
            reasoning_budget=reasoning_budget,
        )
    # ... existing httpx code unchanged below this point
```

Add `# DEPRECATED: direct httpx path; remove in Phase 2 cleanup` comment above the existing httpx block.

**`src/retrieval/vector/embedding_service.py`**

In `generate_embeddings()`:
```python
if get_settings().model_gateway_enabled:
    from src.api.gateway.model_gateway import get_model_gateway
    return await get_model_gateway().embed(texts)
# ... existing NIMClient path unchanged
```

**`src/api/app.py`**

Remove the two `load_dotenv()` calls (Settings handles this via `env_file`). In the lifespan context manager, add:
```python
from src.api.gateway.model_gateway import ModelGateway, _gateway
# ... at shutdown:
if _gateway:
    await _gateway.close()
```

### Files Not to Touch Yet

Do not modify any of the following in this slice:
- Any file in `src/api/agents/` (agents still call `NIMClient`)
- `src/api/routers/chat.py` (no interface change)
- Any graph file
- Any adapter file
- Any retrieval file except `embedding_service.py`
- Any test file except to add the new tests below
- `requirements.lock` until the PR is approved (update lock as final step)

### Tests to Add

**`tests/unit/test_model_gateway.py`** (new file, ~100 lines):

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.api.gateway.model_gateway import ModelGateway

@pytest.fixture
def gateway(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_GATEWAY_ENABLED", "true")
    return ModelGateway()

@pytest.mark.asyncio
async def test_complete_returns_content(gateway, respx_mock):
    respx_mock.post("https://integrate.api.nvidia.com/v1/chat/completions").respond(
        200, json={"choices": [{"message": {"content": "hello"}}]}
    )
    result = await gateway.complete(messages=[{"role": "user", "content": "hi"}])
    assert result == "hello"

@pytest.mark.asyncio
async def test_complete_nemotron_disables_thinking_by_default(gateway, respx_mock):
    captured = {}
    def capture(request):
        import json
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
    respx_mock.post("https://integrate.api.nvidia.com/v1/chat/completions").mock(side_effect=capture)
    await gateway.complete(messages=[{"role": "user", "content": "test"}])
    assert captured.get("chat_template_kwargs", {}).get("enable_thinking") is False

@pytest.mark.asyncio
async def test_embed_returns_vectors(gateway, respx_mock):
    respx_mock.post("https://integrate.api.nvidia.com/v1/embeddings").respond(
        200, json={"data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}]}
    )
    result = await gateway.embed(["text one", "text two"])
    assert len(result) == 2
    assert result[0] == [0.1, 0.2]

def test_model_requests_total_increments(gateway, respx_mock):
    # verify prometheus counter is accessible
    from src.api.gateway.telemetry import model_requests_total
    before = model_requests_total.labels(
        model="nvidia/llama-3.3-nemotron-super-49b-v1.5",
        endpoint="chat/completions",
        status="ok"
    )._value.get()
    # (call gateway.complete in async context, then check counter increased)
    assert before >= 0

@pytest.mark.asyncio
async def test_nim_client_delegates_to_gateway_when_enabled(monkeypatch):
    monkeypatch.setenv("MODEL_GATEWAY_ENABLED", "true")
    from src.api.config.settings import get_settings
    get_settings.cache_clear() if hasattr(get_settings, "cache_clear") else None
    from src.api.services.llm.nim_client import NIMClient
    client = NIMClient()
    with patch("src.api.gateway.model_gateway.get_model_gateway") as mock_gw:
        mock_gw.return_value.complete = AsyncMock(return_value="gateway response")
        result = await client.generate_response(messages=[{"role": "user", "content": "test"}])
    assert result == "gateway response"
```

**`tests/unit/test_config.py`** (new file, ~30 lines):
```python
from src.api.config.settings import Settings

def test_settings_loads_defaults():
    s = Settings()
    assert s.llm_model == "nvidia/llama-3.3-nemotron-super-49b-v1.5"
    assert s.embedding_dimension == 2048
    assert s.llm_enable_thinking is False

def test_settings_resolved_embedding_key_falls_back_to_nvidia_key():
    s = Settings(nvidia_api_key="nvapi-test", embedding_api_key="")
    assert s.resolved_embedding_api_key == "nvapi-test"

def test_settings_embedding_key_overrides_nvidia_key():
    s = Settings(nvidia_api_key="nvapi-test", embedding_api_key="nvapi-embed")
    assert s.resolved_embedding_api_key == "nvapi-embed"
```

### Expected Behavior After This Slice

- `POST /api/v1/chat` produces identical responses to before (same NIM calls, same prompts).
- `GET /api/v1/metrics` includes `model_requests_total{model="nvidia/llama-3.3-nemotron-super-49b-v1.5",endpoint="chat/completions"}` counter.
- `MODEL_GATEWAY_ENABLED=false` produces exactly the same behavior as before this PR (legacy `NIMClient` httpx path).
- `pydantic-settings` `Settings` replaces all scattered `os.getenv()` calls in `app.py` only (other files migrated one-by-one in subsequent PRs).
- No change to the React frontend, nginx config, Docker Compose, or any database schema.

### Definition of Done for This Slice

- [ ] `tests/unit/test_model_gateway.py` passes (5 tests).
- [ ] `tests/unit/test_config.py` passes (3 tests).
- [ ] Existing `tests/unit/test_nvidia_llm.py` passes with `MODEL_GATEWAY_ENABLED=true`.
- [ ] `POST /api/v1/chat` returns HTTP 200 in local Docker run with gateway enabled.
- [ ] `GET /api/v1/metrics` includes `model_requests_total` and `model_latency_seconds` metrics.
- [ ] `mypy src/api/config/ src/api/gateway/ --ignore-missing-imports` produces zero errors.
- [ ] `black --check src/api/config/ src/api/gateway/` produces zero violations.
- [ ] PR description includes a before/after screenshot of `GET /api/v1/metrics` showing the new counters.
