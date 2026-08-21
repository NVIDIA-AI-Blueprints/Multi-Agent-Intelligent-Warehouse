# Modernization Gap Analysis
# Multi-Agent Intelligent Warehouse (MAIW)

**Date:** 2026-08-20
**Analyst:** Senior Software Architect
**Repository:** `/home/nvidia/Multi-Agent-Intelligent-Warehouse`
**Branch:** `main`

---

## 1. Assessment Methodology

This analysis compares the current MAIW codebase state — derived from full structural inspection of source code, configuration, infrastructure, tests, and CI/CD pipelines — against the target architecture defined by the MAIW Modernization Skill. Each capability dimension is assessed independently using three evidence categories:

- **Exists and correct**: the component is present, structurally sound, and aligned with the target contract.
- **Exists but insufficient**: the component is present but in a form that requires significant rework to meet the target contract (wrong abstraction level, missing interface, coupled to wrong layer, or incomplete).
- **Absent**: the capability does not exist anywhere in the repository in any form.

**Rating scale:**

| Rating | Meaning |
|--------|---------|
| GREEN | Capability is present and substantially aligned with the target architecture. Hardening or minor extension may be needed but no re-architecture is required. |
| YELLOW | Capability is partially present. The intent is there and some useful code exists, but the current form is insufficient for the target contract without moderate rework. |
| RED | Capability is absent or its current form is so far from the target contract that reuse is negligible. A net-new build is required. |

---

## 2. Capability Assessment Table

| # | Capability | Rating | Evidence Summary |
|---|-----------|--------|-----------------|
| 1 | Nemotron-native runtime | YELLOW | `nvidia/llama-3.3-nemotron-super-49b-v1.5` is the default model. Nemotron-specific parameters (`reasoning_budget`, `enable_thinking`, `/no_think` system prefix) are conditionally injected via a name-substring check in `nim_client.py`. However only one Nemotron model is wired; the Lightning/Nano/Ultra/Nano-Omni family variants are not reachable without env-var changes and the conditional logic is not extensible to multi-model dispatch. |
| 2 | ModelGateway | RED | No centralized gateway abstraction exists. LLM calls originate from at least six distinct call sites: `NIMClient` (shared agents), `SmallLLMProcessor` (document pipeline), `LargeLLMJudge` (document validation), `NemotronParseService` (OCR), `NeMoRetrieverPreprocessor` (preprocessing), and `GuardrailsService`. Each maintains its own `httpx.AsyncClient`, its own env-var credentials, and its own retry logic. There is no single choke point for model selection, telemetry, rate management, or cost attribution. |
| 3 | Model registry | RED | No registry, catalog, or manifest of available models exists anywhere in the codebase. Model names are string literals or env-var defaults scattered across source files. There is no mechanism to enumerate available models, check capability flags, or perform capability negotiation. |
| 4 | Dynamic model routing | RED | The only routing logic is a single string-contains check (`"nemotron" in model_name.lower()`) in `nim_client.py` lines 402-432. This gates Nemotron-specific payload fields but performs no capability-based selection, no cost/latency-based routing, and no fallback to alternative models. Routing between agents (equipment/operations/safety) is keyword + embedding similarity but this is agent routing, not model routing. |
| 5 | Agent/model separation | RED | Every agent class directly instantiates or calls `get_nim_client()` and issues `nim_client.generate_response(...)` calls with hard-coded temperature and token parameters inline. The agent layer is responsible for both orchestration logic and model invocation mechanics. There is no boundary between "what the agent decides to do" and "which model executes the inference." |
| 6 | Official MCP v2 SDK | RED | The official Anthropic MCP Python SDK (version 1.27.0) is installed only in a separate unrelated virtualenv (`/home/nvidia/nvidia-wms-workshop/.venv/`). It is not listed in `requirements.txt` or `pyproject.toml` and is not imported anywhere in `src/`. All MCP functionality is a fully custom JSON-RPC 2.0 implementation across `src/api/services/mcp/server.py`, `client.py`, and `base.py`. |
| 7 | maiw-mcp package | RED | No standalone `maiw-mcp` installable package exists. Tool definitions are embedded inside agent classes and MCP adapter classes within the monolithic `src/` tree. There is no separately versioned, independently deployable package boundary. |
| 8 | MCP server boundaries | RED | All MCP adapters (`EquipmentMCPAdapter`, `OperationsMCPAdapter`, `SafetyMCPAdapter`, `ForecastingMCPAdapter`) are instantiated in-process and registered via `_register_mcp_adapters()` in `src/api/routers/mcp.py`. They share the same Python interpreter, memory, database pool, and lifecycle as the FastAPI application. There are no independently deployable capability servers; the isolation boundary is a Python class, not a network boundary. |
| 9 | Vendor-neutral capability contracts | RED | Tool parameter schemas (in each `MCPAdapter._register_tools()`) and action tool method signatures reference concrete infrastructure directly: SQL table names appear in `SQLRetriever.fetch_all()` calls inside tool handlers, `asyncpg` connection pools are used directly, and WMS integration delegates to adapter-specific classes (`SAPEWMAdapter`, `ManhattanWMSAdapter`). There are no vendor-neutral semantic contracts (e.g., abstract `InventoryCapability` interfaces) that could be swapped behind an adapter boundary. |
| 10 | Skills layer | RED | No intermediate Skills layer exists between MCP tools and agents. Agent classes contain orchestration logic, LLM prompt construction, tool selection heuristics, response formatting, and domain-specific business rules all in the same class. The closest approximation is the `*ActionTools` classes, but these are direct database/service clients, not reusable compositional skills. |
| 11 | Reduced agent coupling | RED | Each agent class (`MCPEquipmentAssetOperationsAgent`, `MCPOperationsAgent`, etc.) directly imports and instantiates its database retriever, NIM client, tool discovery service, reasoning engine, and MCP manager. Circular imports are avoided only by lazy `get_*()` singleton functions. There is no dependency injection framework and no interface that an agent depends on rather than a concrete class. |
| 12 | AgentRuntime abstraction | RED | LangGraph `StateGraph` is used directly in `mcp_integrated_planner_graph.py` with `MCPWarehouseState` as a raw `TypedDict`. The graph construction, node wiring, conditional edge logic, and compilation are all exposed in the planner graph file. There is no `AgentRuntime` interface that would allow swapping LangGraph for another orchestration engine or running agents without graph machinery. |
| 13 | WarehouseState explicit model | YELLOW | `MCPWarehouseState` (a `TypedDict`) exists in `src/api/graphs/mcp_integrated_planner_graph.py` and captures messages, routing decisions, agent responses, tool plans, reasoning chain, and context. However it is a flat TypedDict with `Dict[str, Any]` fields for most structured data. There are no typed Pydantic models for warehouse entities within the state, no field-level freshness/staleness metadata, no schema versioning, and no validation on state transitions. |
| 14 | Typed event model | RED | No event model exists. Kafka is configured as a dependency in `docker-compose.dev.yaml` with `KAFKA_BOOTSTRAP_SERVERS` in `.env.example`, but there are no Kafka producers or consumers in `src/`. There are no typed event schemas (Avro, Pydantic, or dataclass), no event bus abstraction, and no event-sourcing pattern. Kafka is infrastructure presence without application-layer integration. |
| 15 | DecisionEngine | RED | No policy evaluation gate exists before write actions. The `adjust_reorder_point()` method in `src/api/agents/inventory/equipment_action_tools.py` (line 500) accepts a `requires_approval: bool = True` parameter and stores it as metadata in the returned dict, but this flag is not checked or enforced anywhere in the call chain. Write actions (task creation, inventory adjustment, safety alert broadcast, equipment assignment) execute immediately when called. |
| 16 | Policy engine | RED | No policy engine, rule evaluator, or constraint checker exists. NeMo Guardrails is used for LLM input/output safety filtering but operates on text patterns, not on business policy rules (e.g., "reorder quantity cannot exceed 30-day supply", "LOTO request requires supervisor role"). |
| 17 | Human approval gating | RED | The only HITL implementation is a metadata flag. No LangGraph `interrupt_before`/`interrupt_after` mechanism, no blocking checkpoint, no async approval workflow, and no human task queue exists. The document routing workflow mentions `human_review_required` in `routing_decisions` schema but the graph does not pause execution pending a response. |
| 18 | Simulation-before-execution | RED | No simulation or dry-run mode exists for any write action. Operations such as pick-wave generation, inventory reservation, task assignment, and reorder-point adjustment execute against live systems with no preview, rollback preview, or consequences estimation step. The `mcp/rollback.py` service exists as a skeleton but is not called in any execution path. |
| 19 | Optimization separation | YELLOW | RAPIDS-based GPU forecasting is architecturally separated into `Dockerfile.rapids` and `scripts/forecasting/rapids_gpu_forecasting.py`. The training router invokes it via subprocess. However the separation is a subprocess call, not a cleanly defined optimization service contract. The live API's `AdvancedForecastingService` reads pre-generated JSON forecast files and Postgres demand views rather than calling an optimization service. The boundary exists but is fragile and not contractually defined. |
| 20 | Multimodal perception | YELLOW | The six-stage document pipeline in `src/api/agents/document/` ingests PDFs and images through NeMo OCR, `NemotronParseService`, `SmallLLMProcessor` (Llama Nemotron Nano VL 8B with vision fallback to `meta/llama-3.2-11b-vision-instruct`), and `LargeLLMJudge`. This is a functional multimodal pipeline for documents. However it is not integrated into the main agent routing graph as a first-class perception capability — it is a side-channel pipeline reached through separate REST endpoints. Non-document visual inputs (camera feeds, RFID readers, IoT sensors) are adapter stubs without real perception logic. |
| 21 | Trajectory store | RED | No structured trajectory store exists. Agent reasoning steps are propagated through LangGraph state (`state["context"]["reasoning_steps"]`) and returned in the `ChatResponse` payload, but they are not persisted to any durable store. There is no JSONL trace file, no LangSmith/LangFuse integration, no dedicated trajectory database table, and no mechanism to replay or retrospectively analyze execution paths. |
| 22 | Evaluation framework | YELLOW | Answer quality evaluation tests exist in `tests/quality/` (`test_answer_quality.py`, `test_answer_quality_enhanced.py`) with per-agent quality scoring and `generate_quality_report.py`. `EvidenceScoringEngine` provides production confidence scoring. However there is no standardized benchmark dataset, no RAGAS/DeepEval/HELM integration, no golden-answer regression test suite, and no automated eval gate in the CI pipeline. The existing evaluation is manual, live-system-dependent, and not reproducible without a running API. |
| 23 | Regression scenarios | RED | No regression scenario corpus exists. The CI pipeline (`ci-cd.yml`) runs unit tests with eleven files explicitly ignored due to API drift or missing dependencies. There are no locked golden responses, no deterministic replay scenarios, and no mechanism to catch behavioral regressions across model or prompt changes. |
| 24 | Observability (OTel) | RED | Zero OpenTelemetry instrumentation exists. `requirements.txt` and `pyproject.toml` contain no `opentelemetry-*` dependency. There are no spans, no traces, no distributed trace propagation, and no trace context headers. Prometheus metric collection is present and functional but covers only HTTP request counters and duration histograms — not LLM call latency, token counts, tool execution traces, or agent step timing. There are no correlation IDs propagated beyond an internal `request_id` UUID that is never surfaced in logs or HTTP response headers. |
| 25 | SFT pipeline | RED | No supervised fine-tuning pipeline exists. There is no training corpus, no data formatting code, no model training configuration, and no fine-tuning script of any kind. The repository exclusively consumes pre-trained NIM models via API. |
| 26 | GRPO pipeline | RED | No GRPO (Group Relative Policy Optimization) or any reinforcement learning pipeline exists. Terms `grpo`, `rlhf`, `ppo`, `reward model`, and `policy gradient` are absent from the source tree. |
| 27 | Model promotion gates | RED | No model promotion workflow, canary deployment mechanism, A/B test harness, or promotion gate exists. Model selection is a single environment variable (`LLM_MODEL`). Changing the model requires a redeployment with no automated quality gate, regression check, or rollback mechanism. |
| 28 | Kubernetes scalability | RED | The deployment infrastructure consists entirely of Docker Compose files in `deploy/compose/`. No Kubernetes manifests, no Helm charts, no operator, no `k8s/` directory, and no container orchestration beyond Docker Compose exists. Services cannot be horizontally scaled, health-checked by an orchestrator, or deployed to a cloud-managed Kubernetes cluster without building this infrastructure from scratch. |

---

## 3. Critical Gaps (RED Items)

### 3.1 ModelGateway

**Current implementation:**
- `src/api/services/llm/nim_client.py` — shared `NIMClient` used by most agents
- `src/api/agents/document/processing/small_llm_processor.py` — own `httpx.AsyncClient`, own credentials
- `src/api/agents/document/validation/large_llm_judge.py` — own `httpx.AsyncClient` per request
- `src/api/agents/document/ocr/nemotron_parse.py` — own `httpx.AsyncClient`, own base URL
- `src/api/services/guardrails/guardrails_service.py` — own model config, own credentials
- `src/retrieval/vector/embedding_service.py` — routes through `NIMClient` but with separate config

**Problem:** There are six independent model call sites, each maintaining its own connection pool, retry logic, authentication header, and error handling. There is no single surface for cross-cutting concerns: rate limiting against the NIM API quota, cost attribution, latency telemetry per model, or fallback orchestration. Adding a new Nemotron model variant requires updating multiple files. A NIM API key rotation requires finding and updating every `os.getenv("NVIDIA_API_KEY")` call site.

**Architectural risk:** Every new capability that requires an LLM call (a new agent, a new validation pass, a new document stage) will add yet another independent call site. Operational incidents (rate limit storms, credential expiry, model deprecation) will surface inconsistently and require multi-file hotfixes. The six-site pattern is already present at the current feature surface; it will expand.

**Recommended target:** A `ModelGateway` service with a registry of named model endpoints, a single authenticated connection pool per provider, centralized retry/backoff, Prometheus counters per model (`model_requests_total{model, status}`), and a routing API (`gateway.complete(capability="judge", messages=...)`) that resolves capability names to model endpoints from the registry. All six current call sites collapse to a single import.

**Migration complexity:** Medium. `NIMClient` is close to the right shape; it needs to absorb the other five call sites, grow a capability registry, and expose telemetry. The document pipeline models (`SmallLLMProcessor`, `LargeLLMJudge`) will require interface changes.

**Blocking dependencies:** Model registry (3.2) must exist first; ModelGateway reads from it.

---

### 3.2 Model Registry

**Current implementation:** No file. Model names exist as string defaults in `os.getenv()` calls: `nim_client.py:104`, `guardrails_service.py:62`, `large_llm_judge.py:65`, `nemo_retriever.py:354`, `small_llm_processor.py:38`, `embedding_service.py:45`.

**Problem:** There is no machine-readable catalog of which models are available, what their capability flags are (vision, thinking, structured output, embedding dimension), what their API endpoints are, or what their cost profiles are. Changing from `nvidia/llama-3.3-nemotron-super-49b-v1.5` to a Nemotron Ultra variant requires grep-and-replace across six files with no automated verification.

**Architectural risk:** When the Nemotron model family expands (Lightning, Nano, Ultra, Nano-Omni, domain-specialized variants), the codebase has no mechanism to declare which model serves which capability. Prompt engineering will diverge per model because there is no registry-enforced contract on what each model accepts.

**Recommended target:** A `models.yaml` (or Pydantic `ModelCard` registry) declaring each model's identifier, provider endpoint, capability flags (`vision: bool`, `thinking: bool`, `embedding_dimension: int`, `max_context: int`), and version. Loaded at startup by the ModelGateway. Model promotion gates (3.14) validate against this registry.

**Migration complexity:** Low for the registry itself. The downstream wiring (ModelGateway consuming it) is the Medium-complexity work.

**Blocking dependencies:** None. Can be built in isolation.

---

### 3.3 Official MCP v2 SDK

**Current implementation:**
- `src/api/services/mcp/server.py` — custom JSON-RPC 2.0 server (protocol version `2024-11-05`)
- `src/api/services/mcp/client.py` — custom client with HTTP/WebSocket/STDIO connection types
- `src/api/services/mcp/base.py` — custom `MCPAdapter`, `MCPToolBase`, `MCPManager` abstractions

**Problem:** The custom implementation reimplements the MCP wire protocol at roughly 1,500 lines of code that must be maintained against a moving specification. It lacks the SDK's session lifecycle management, capability negotiation, error code standardization, and schema validation. As the MCP specification evolves (tool annotations, resource subscriptions, sampling callbacks), the custom implementation will lag. External MCP servers (from the broader NIM/Blueprint ecosystem) cannot be connected without extending the custom client.

**Architectural risk:** Tool interoperability with third-party MCP servers is blocked. NVIDIA Blueprint tooling that targets the official MCP SDK will not function with this custom implementation. Protocol bugs will be caught late and will require in-house fixes rather than SDK upgrades.

**Recommended target:** Replace `server.py`, `client.py`, and the connection management layer with the official `mcp` Python SDK (`mcp>=1.0.0`). The `MCPAdapter` base class and domain adapter implementations (`EquipmentMCPAdapter` etc.) can be preserved as server-side tool providers if they implement the SDK's `@server.tool()` decorator pattern. The `MCPManager` registry role can be retained as a higher-level orchestration layer above the SDK.

**Migration complexity:** High. The custom protocol layer is load-bearing for all agent tool calls. Migration must be done without breaking the tool execution path. A parallel-run strategy (custom server + SDK server on different ports, with traffic migration) is advisable.

**Blocking dependencies:** MCP server boundaries (3.4). The SDK migration and the server extraction should be done together.

---

### 3.4 MCP Server Boundaries / `maiw-mcp` Package

**Current implementation:**
- `src/api/routers/mcp.py` — `_register_mcp_adapters()` registers adapters in-process at API startup
- `src/api/services/mcp/adapters/` — four adapters (equipment, operations, safety, forecasting) as Python classes in the same process
- No standalone deployable server or installable package

**Problem:** All domain capability servers share one Python process with the FastAPI web layer. A bug or resource exhaustion in the equipment adapter can take down the safety alert system. Adapters cannot be independently scaled, independently versioned, or deployed to separate nodes. The document processing pipeline is not even registered as an MCP adapter — it is called through direct REST endpoints.

**Architectural risk:** Single point of failure for all domain capabilities. No independent deployability means no capability-level SLAs. Adding a new domain (e.g., labor planning, slotting optimization) requires modifying the monolith rather than deploying a new server.

**Recommended target:** Extract each domain adapter as an independently deployable MCP server implemented with the official SDK, packaged as `maiw-mcp-equipment`, `maiw-mcp-operations`, `maiw-mcp-safety`, `maiw-mcp-forecasting`, `maiw-mcp-document`. Each runs as its own container (a `Dockerfile.mcp-*` per domain). The planner graph connects to them as remote MCP clients. The existing adapter tool definitions (`_register_tools()` methods) map directly to `@server.tool()` decorators.

**Migration complexity:** High. Requires the official MCP SDK migration first, Docker networking for MCP-over-SSE or WebSocket between containers, and service discovery for the planner to locate MCP servers dynamically.

**Blocking dependencies:** Official MCP SDK (3.3), model registry (3.2).

---

### 3.5 AgentRuntime Abstraction

**Current implementation:**
- `src/api/graphs/mcp_integrated_planner_graph.py` — `MCPPlannerGraph` class directly constructs `StateGraph(MCPWarehouseState)`, wires all nodes as bound methods, and calls `workflow.compile()`
- All agents are called as coroutines inside graph node methods
- No interface separating "what the orchestrator does" from "how LangGraph implements it"

**Problem:** LangGraph `StateGraph`, `Annotated`, `BaseMessage`, and `HumanMessage` are first-class imports in the planner. The planner graph is the agent runtime; there is no seam. This means: LangGraph version upgrades require testing the entire agent behavior surface. CVE-2025-8709 (already in the codebase comments as the reason for disabling checkpointing) will recur — any LangGraph security issue requires immediate hotfix of the orchestration layer. Multi-agent patterns (subgraphs, map-reduce, swarm) cannot be composed without rewriting the planner.

**Architectural risk:** Vendor lock-in at the orchestration layer. The checkpointing decision (`workflow.compile()` with no checkpointer) means session state is entirely in-memory — if the process restarts, all in-flight sessions are lost. This cannot be fixed without re-architecting against the CVE-affected checkpoint packages or building a custom checkpoint store.

**Recommended target:** Define an `AgentRuntime` abstract interface with methods `async run(query, session_id, context) -> AgentResult` and `async stream(query, session_id, context) -> AsyncIterator[AgentEvent]`. The `MCPPlannerGraph` becomes one implementation of this interface. The FastAPI chat router depends on `AgentRuntime`, not on `MCPPlannerGraph` directly. This seam allows swapping the underlying orchestration engine and enables testing agents without spinning up a full LangGraph.

**Migration complexity:** Medium. The interface extraction is straightforward; wiring all callers through it (currently only `chat.py` calls the planner directly) requires a moderate refactor.

**Blocking dependencies:** None. Can be done independently.

---

### 3.6 DecisionEngine / Policy Engine / Human Approval Gating

**Current implementation:**
- `src/api/agents/inventory/equipment_action_tools.py:500` — `requires_approval: bool = True` parameter stored as metadata in returned dict, never checked
- `src/api/agents/operations/mcp_operations_agent.py` — "Requires human approval" noted in comments
- `src/api/agents/document/routing/intelligent_router.py` — `human_review_required` field in `routing_decisions` table
- No blocking mechanism, no approval queue, no interrupt pattern

**Problem:** Write actions (inventory adjustment, task creation, equipment assignment, safety incident logging) execute immediately with no policy evaluation and no human confirmation step. The `requires_approval` flag is advisory metadata that is returned to the API caller but never enforced in the execution path. High-impact operations (adjusting reorder points, creating purchase requisitions, broadcasting emergency alerts) carry the same risk profile as low-impact read operations.

**Architectural risk:** An LLM hallucination, a misrouted query, or a prompt injection attack that bypasses the NeMo Guardrails layer can cause irreversible write actions against production inventory, WMS, or ERP systems. The pattern of "metadata flag + hope the caller checks it" provides no real control surface.

**Recommended target:** A `DecisionEngine` that runs synchronously before any write-action tool execution. It receives the intended action, the action's risk tier (derived from a policy manifest), the user's JWT roles, and current warehouse state. For low-risk actions it approves immediately. For medium-risk actions it applies policy rules deterministically. For high-risk actions it raises a `RequiresApprovalException` that triggers a LangGraph `interrupt_before` pattern, pausing the graph and writing the pending decision to a `pending_approvals` Postgres table. The human review endpoint resumes the graph upon approval.

**Migration complexity:** High. Requires implementing the `DecisionEngine`, defining a risk-tier manifest for every existing tool, implementing LangGraph interrupt/resume (which reintroduces the checkpointing requirement — the CVE-2025-8709 issue must be addressed by using a Postgres checkpoint store instead of SQLite), and building the human review UI endpoint.

**Blocking dependencies:** Typed event model (for approval events), WarehouseState explicit model (for risk context), Postgres checkpoint store (to resume graph after human approval).

---

### 3.7 Trajectory Store

**Current implementation:**
- `src/api/routers/chat.py:614` — `request_id = str(uuid.uuid4())` passed to `PerformanceMonitor.start_request()` and `end_request()`
- `src/api/services/monitoring/performance_monitor.py` — in-memory ring buffer of last 1,000 requests (latency, route, error flag)
- LangGraph state carries `reasoning_steps` in `state["context"]`; returned in `ChatResponse.reasoning_steps`
- No persistence to any durable store

**Problem:** Every agent execution — intent classification, tool selection, tool execution results, LLM reasoning steps, synthesis — exists only in ephemeral request memory. There is no historical record of what the system decided, why, and what happened as a result. This blocks: (a) offline evaluation against real traffic, (b) data collection for the SFT pipeline, (c) debugging of incorrect responses after the fact, (d) audit trail for regulatory or safety-critical decisions.

**Architectural risk:** The intelligence flywheel (trajectories → SFT → GRPO → specialized models) cannot be started without trajectory data. Every cycle of model improvement requires restarting data collection from zero. Post-incident investigation of safety-related agent decisions is impossible.

**Recommended target:** A `TrajectoryStore` that writes one JSONL record per agent invocation containing: `session_id`, `request_id`, `timestamp`, `intent`, `routing_decision`, `tool_execution_plan`, `tool_results` (per tool), `llm_calls` (prompt + completion + latency per call), `reasoning_steps`, `final_response`, `validation_score`, `user_feedback` (null until rated). Written asynchronously (fire-and-forget to a background task queue) so it does not add latency to the critical path. Initial target: a `trajectories` TimescaleDB hypertable. Later: export to object storage for SFT preprocessing.

**Migration complexity:** Medium. The data already exists in the LangGraph state at synthesis time; the gap is persistence. The `_mcp_synthesize_response` node is the right injection point. The schema design requires care to handle variable-length tool result arrays.

**Blocking dependencies:** None. Can be built independently and activated progressively.

---

### 3.8 Observability (OpenTelemetry)

**Current implementation:**
- Prometheus metrics at `/api/v1/metrics` — HTTP counters and duration histograms only
- Plain-text `logging.getLogger(__name__)` across all modules with no consistent format
- Internal `request_id` UUID never propagated beyond `PerformanceMonitor`
- No `opentelemetry-*` dependency anywhere

**Problem:** When a chat request takes 90 seconds, there is no way to determine whether the latency was in NeMo Guardrails input check, intent classification, LLM generation, tool execution, or the enhancement pipeline. Log lines from different async tasks interleave without correlation. The Prometheus metrics at the HTTP layer are insufficient to attribute latency to specific model calls or tool executions. Incidents require log trawling rather than trace inspection.

**Architectural risk:** As the system grows to multiple independently deployable MCP servers (the target architecture), correlating a slow response across five networked processes is impossible without distributed tracing. Multi-process debugging without OTel is operationally untenable at production scale.

**Recommended target:** Instrument with `opentelemetry-sdk`, `opentelemetry-instrumentation-fastapi`, `opentelemetry-instrumentation-httpx`, and `opentelemetry-instrumentation-asyncpg`. Every LLM call, tool execution, and database query becomes a child span of the top-level request trace. Emit to an OTLP collector (Grafana Tempo or Jaeger in the Docker Compose stack). Add `X-Request-ID` and `traceparent` headers to all HTTP responses. Enrich Prometheus metrics with `model` and `tool_name` labels that are absent today.

**Migration complexity:** Medium. `opentelemetry-instrumentation-fastapi` and `opentelemetry-instrumentation-httpx` provide auto-instrumentation that covers most cases with minimal code changes. Manual span creation is needed for LLM call attribution and LangGraph node boundaries.

**Blocking dependencies:** None. Can be added incrementally.

---

### 3.9 Typed Event Model / Kafka Integration

**Current implementation:**
- Kafka service defined in `docker-compose.dev.yaml` (port 9092)
- `KAFKA_BOOTSTRAP_SERVERS` in `.env.example`
- Zero Kafka producers or consumers in `src/`

**Problem:** Kafka is declared as infrastructure but the application never uses it. Real-time events (inventory movements, equipment telemetry updates, safety alerts, task state changes) are written directly to Postgres via synchronous SQL in tool handlers. There is no event-driven decoupling between the agent layer and the warehouse data layer. This means: agents cannot react to warehouse events without polling, and external systems cannot subscribe to agent decisions.

**Architectural risk:** The absence of an event bus is a scalability ceiling. At higher event volumes (IoT telemetry, RFID scans), synchronous SQL writes from within agent tool handlers will create backpressure on the LangGraph execution path. The IoT and RFID adapter stubs in `src/adapters/` have no delivery mechanism into the system.

**Recommended target:** Define typed Pydantic event schemas (`InventoryMovementEvent`, `EquipmentAlertEvent`, `SafetyIncidentEvent`, `AgentDecisionEvent`) as a shared `maiw-events` package. Produce events from tool action handlers via a lightweight `EventBus` abstraction backed by Kafka (or Redis Streams as a simpler alternative for development). Consume in background workers to update materialized views and trigger downstream flows.

**Migration complexity:** High. Requires schema design, Kafka producer integration in tool handlers, consumer worker infrastructure, and idempotency handling.

**Blocking dependencies:** MCP server boundaries (independent server processes need event bus to communicate).

---

### 3.10 SFT / GRPO / Model Promotion Gates

**Current implementation:** None. No training data, no training code, no pipeline, no evaluation gate.

**Problem:** The system has no mechanism to specialize Nemotron models on warehouse-domain data. All intelligence is general-purpose. There is no feedback loop from trajectory data (which does not yet exist) to model improvement. When base models are updated, there is no automated quality gate to validate that the new model maintains behavioral consistency on warehouse tasks.

**Architectural risk:** The system's intelligence is entirely dependent on the general-purpose capability of the base NIM models. Warehouse-specific terminology, SKU naming conventions, WMS integration patterns, and safety regulation language are not represented in fine-tuned weights. As warehouse-specific tasks become more demanding, general-purpose models will plateau in accuracy.

**Recommended target:** Phase 1: Trajectory store (see 3.7) to accumulate `(prompt, completion, metadata)` triplets. Phase 2: SFT pipeline — format trajectories as instruction-tuning datasets, submit to NVIDIA NeMo Curator/NeMo Framework for domain-adapted Nemotron fine-tuning, register resulting model checkpoints in the model registry (see 3.2). Phase 3: GRPO pipeline — define reward functions (validation score, user feedback, safety compliance) and run policy optimization on the domain-adapted model. Phase 4: Model promotion gate — an automated eval job runs the regression scenario corpus (see 3.8) against the candidate model before the model registry entry is updated.

**Migration complexity:** High for the full pipeline. Each phase can be built independently. The trajectory store is the essential precondition.

**Blocking dependencies:** Trajectory store (3.7), model registry (3.2), evaluation framework (capability 22), regression scenarios (capability 23).

---

### 3.11 Kubernetes Scalability

**Current implementation:**
- `deploy/compose/docker-compose.dev.yaml` — all services in a single Docker Compose file
- No `k8s/`, no Helm charts, no operator, no HPA, no PodDisruptionBudget
- Four Dockerfiles (combined, backend, frontend, RAPIDS) are K8s-deployable in principle

**Problem:** The entire system — FastAPI backend, React frontend, TimescaleDB, Redis, Kafka, Milvus, Zookeeper, etcd, MinIO, nginx, Prometheus, Grafana, local NIM — runs as a single Docker Compose stack on one host. There is no horizontal scaling for the agent-compute layer, no pod-level health checks for the orchestrator, no resource quotas, and no namespace isolation between workloads.

**Architectural risk:** Single-host deployment is not viable for production warehouse deployments where high availability, rolling updates, and multi-GPU NIM serving are required. The four-GPU NIM container reservation in `docker-compose.dev.yaml` (`nvidia.com/gpu: 4`) cannot be scheduled by Docker Compose across multiple nodes.

**Recommended target:** Helm chart with separate deployments for: API backend (scalable, stateless), MCP capability servers (one deployment per domain), frontend (CDN-backed), infrastructure (TimescaleDB StatefulSet, Redis, Kafka via Strimzi operator, Milvus operator). Horizontal Pod Autoscaler on the API backend keyed on HTTP request rate. NVIDIA GPU Operator for NIM container scheduling. ConfigMaps for all environment configuration.

**Migration complexity:** High. Requires Kubernetes infrastructure setup, Helm chart authoring, StatefulSet management for TimescaleDB and Milvus, secrets management (Vault or K8s Secrets), and ingress configuration. The Docker Compose files are a useful reference but are not a direct migration path.

**Blocking dependencies:** MCP server boundaries (3.4) should be resolved first so each server has a clean container image.

---

## 4. Refactoring Needed (YELLOW Items)

### 4.1 Nemotron-Native Runtime

**Current implementation:** `src/api/services/llm/nim_client.py` lines 402-432 conditionally inject `reasoning_budget`, `enable_thinking`, and `/no_think` system prefix when `"nemotron" in self.config.llm_model.lower()`. The default model is `nvidia/llama-3.3-nemotron-super-49b-v1.5`.

**What needs to change:**

1. The string-contains check must be replaced with a capability flag from the model registry. A model entry should declare `supports_thinking: bool`, `supports_reasoning_budget: bool`, and `system_prefix_mode: "no_think" | "none"`. The `NIMClient` (or `ModelGateway`) reads these flags rather than parsing the model name string.

2. The `LLM_ENABLE_THINKING` / `LLM_REASONING_BUDGET` env vars control a single global toggle. The target architecture requires per-call control with model-specific defaults, so that a reasoning-intensive agent step can opt into thinking mode while a fast intent-classification call opts out, even when both share the same model.

3. The Lightning (fast), Nano (edge), Super (balanced), Ultra (maximum quality), and Nano-Omni (multimodal) variants are not addressable without env-var changes. A capability-routing layer needs to map query characteristics to the appropriate Nemotron variant.

**Migration effort:** Medium. The `NIMClient` payload construction code is well-contained. Adding capability flags from a registry is additive. The agent-level call sites need to pass a `capability_hint` rather than raw temperature parameters.

---

### 4.2 WarehouseState Explicit Model

**Current implementation:** `MCPWarehouseState` in `src/api/graphs/mcp_integrated_planner_graph.py:203` is a `TypedDict` with `Dict[str, Any]` for `context`, `agent_responses`, `mcp_results`, `tool_execution_plan`, and `available_tools`. The synthesize node guards against dict leakage into `final_response` with string-type checks but cannot enforce type safety statically.

**What needs to change:**

1. Replace `Dict[str, Any]` fields with typed Pydantic models: `AgentResponse`, `ToolExecutionPlan`, `ToolResult`, `ReasoningChain`. These already exist implicitly as dataclasses on individual agent response objects but are serialized to dict before entering the state.

2. Add `freshness: datetime` and `source: str` metadata to state fields that carry warehouse data (inventory quantities, equipment statuses, workforce counts) so that agents can reason about data staleness.

3. Add a `WarehouseStateVersion: str` field and a state migration path to handle schema evolution across graph upgrades without breaking in-flight sessions.

**Migration effort:** Medium. The TypedDict-to-Pydantic conversion requires updating all node functions that read/write state fields. The LangGraph state reducer patterns must accommodate Pydantic model merging.

---

### 4.3 Optimization Separation

**Current implementation:** RAPIDS GPU forecasting runs as a subprocess called from `src/api/routers/training.py:176-181`. The live `AdvancedForecastingService` reads pre-generated JSON files and Postgres demand views rather than calling an optimization service. The `Dockerfile.rapids` exists for the forecasting container.

**What needs to change:**

1. Define a formal optimization service contract: a REST or gRPC API exposed by the `Dockerfile.rapids` container that the `AdvancedForecastingService` calls rather than reading static JSON files. The contract should include endpoints for `POST /forecast/{sku}`, `POST /forecast/batch`, `GET /model/performance`, and `GET /reorder-recommendations`.

2. The subprocess invocation in `training.py` must be replaced with an HTTP call to this service. The subprocess pattern is synchronous and blocks the FastAPI worker thread.

3. Add health check and circuit breaker logic so that the live API gracefully falls back to the pre-generated JSON files when the RAPIDS service is unavailable, but the fallback is a defined behavior rather than the default path.

**Migration effort:** Low-Medium. The RAPIDS forecasting code is already well-isolated. Adding an HTTP service wrapper around `rapids_gpu_forecasting.py` and updating `AdvancedForecastingService` to call it is the primary work.

---

### 4.4 Multimodal Perception

**Current implementation:** The six-stage document pipeline in `src/api/agents/document/` handles PDFs and images through NeMo OCR, NemotronParse, Llama Nano VL 8B, and LargeLLMJudge. Functional for document ingestion. IoT and RFID adapters in `src/adapters/` are stubs.

**What needs to change:**

1. The document pipeline is reachable only through dedicated REST endpoints (`POST /api/v1/documents/upload`). It is not integrated into the chat agent graph as a `perception` capability that agents can invoke when they detect a document-type query. The `MCPDocumentAgent` in the graph routes to the pipeline but only through the existing document API, not as an in-graph multimodal step.

2. IoT telemetry in `equipment_telemetry` and `telemetry_data` tables is written by adapters that are currently stubs. The live vision/perception path from physical warehouse sensors to agent-readable state does not exist.

3. The SmallLLMProcessor has hardcoded fallback model strings (`meta/llama-3.2-11b-vision-instruct`, `meta/llama-3.1-8b-instruct`) that should be resolved through the model registry.

**Migration effort:** Medium. Document pipeline integration into the graph is the primary work. IoT perception is a separate, larger effort.

---

### 4.5 Evaluation Framework

**Current implementation:** `tests/quality/` contains manual quality evaluation scripts that call live agents. `EvidenceScoringEngine` provides production confidence scoring. No CI-integrated eval, no benchmark datasets, no RAGAS/DeepEval.

**What needs to change:**

1. Create a golden-answer dataset: a versioned JSONL file of `{query, expected_intent, expected_tools_used, expected_response_contains, expected_validation_score_min}` pairs covering all agent domains. This becomes the regression corpus.

2. Wire a `pytest` eval job in CI that runs the golden-answer dataset against a mock or recorded NIM backend (not live API) and asserts that intent routing, tool selection, and response quality meet thresholds.

3. Integrate `DeepEval` or a lightweight RAGAS-equivalent to score faithfulness, answer relevance, and context recall on retrieval-augmented responses.

4. The eleven test files currently ignored in CI due to "API drift" indicate that the test suite has already diverged from the implementation. These need to be restored or rewritten as part of the eval framework work.

**Migration effort:** Medium. The quality evaluation logic already exists in `tests/quality/`; the gap is a deterministic backend mock, a golden-answer corpus, and CI integration.

---

## 5. Aligned Items (GREEN Items)

There are no fully GREEN capabilities in the current codebase against the target architecture. The items rated YELLOW represent the closest alignment. The areas where the codebase has built meaningful, reusable foundations are:

**Nemotron model integration:** The `NIMClient` in `src/api/services/llm/nim_client.py` correctly handles Nemotron-specific parameters (`reasoning_budget`, `enable_thinking`, `/no_think` prefix), implements retry with exponential backoff, and supports response caching. This code is the right nucleus for the ModelGateway.

**MCP conceptual model:** The custom MCP implementation (`src/api/services/mcp/`) correctly implements the tool registry, tool discovery, parameter validation, security blocklist, and tool execution pipeline as separate concerns. The `DiscoveredTool`, `ToolCategory`, and `MCPTool` data structures map cleanly to the official SDK's tool model. The adapter pattern (`MCPAdapter` base class) is the right abstraction for domain capability servers.

**Domain action tools:** The four action tool classes (`EquipmentAssetTools`, `OperationsActionTools`, `SafetyActionTools`, `ForecastingActionTools`) contain well-defined, unit-testable tool methods with clear parameter contracts. These are reusable as the implementation layer for the target MCP capability servers.

**Document multimodal pipeline:** The six-stage NeMo document pipeline is architecturally sophisticated and uses the correct NVIDIA model stack. It is the most complete capability in the codebase and closest to production-ready for its specific use case.

**Security infrastructure:** The MCP security blocklist, `SafePromptFormatter`, NeMo Guardrails integration (with SDK and pattern fallback), `SecurityHeadersMiddleware`, rate limiter, and JWT auth foundation collectively represent a mature security posture for the LLM and API layers.

**Observability infrastructure:** Prometheus metric collection with Grafana dashboards, Alertmanager rules, and an in-process `PerformanceMonitor` provide a functional operational monitoring layer that can be extended with OTel without replacement.

**TimescaleDB schema design:** The hypertable schema in `data/postgres/migrations/003_timescale_hypertables.sql` correctly models time-series telemetry, operation metrics, and inventory movements with continuous aggregates and 1-year retention. This is production-quality and forms the right foundation for the trajectory store.

---

## 6. Architectural Risk Register

| Rank | Risk | Likelihood | Impact | Description |
|------|------|-----------|--------|-------------|
| 1 | **Unauthenticated write endpoints in production** | High | Critical | All API endpoints except `/api/v1/auth/*` have no authentication dependency. The chat endpoint at `POST /api/v1/chat` is completely unauthenticated and, through the agent graph, can trigger write actions against inventory, WMS, and ERP systems. In a development environment this is acceptable; in a production deployment it is a critical access control failure. The auth infrastructure (`JWT`, `get_current_user`, RBAC) exists and works but is not applied to the endpoints that need it. This is the single highest-risk finding in the codebase. |
| 2 | **No durable agent state — process restart loses all sessions** | High | High | `MCPPlannerGraph.compile()` explicitly uses no checkpointer (referencing CVE-2025-8709 in the source comment). All in-flight conversation state, tool execution plans, and reasoning chains are held in Python heap memory. A process restart or OOM kill discards all active sessions. In a warehouse operations context where agents may be mid-execution on a critical task (emergency alert broadcast, reorder requisition), this creates operational risk. The CVE must be addressed with a Postgres-backed checkpoint store, not by abandoning checkpointing entirely. |
| 3 | **Intelligence flywheel blocked by absent trajectory store** | High | High | The modernization roadmap's value proposition — specialized Nemotron models trained on warehouse trajectories — cannot be started without a trajectory store. Every day the system operates without trajectory persistence is a day of training data lost permanently. The longer this is deferred, the longer the time-to-first-specialized-model. Given that the trajectory store is Medium migration complexity with no blocking dependencies, deferring it beyond the first sprint represents the highest-opportunity-cost sequencing risk. |
| 4 | **Custom MCP implementation drift from specification** | Medium | High | The custom MCP implementation targets protocol version `2024-11-05`. The MCP specification has evolved since that date. As the official SDK adds capability negotiation, resource subscriptions, tool annotations, and sampling, the custom implementation will not keep pace. Blueprint tooling from NVIDIA's ecosystem that targets the official SDK (NIM Agent Blueprints, NeMo Retriever MCP servers) will not be compatible with this implementation. The longer the custom implementation is maintained, the larger the migration to the official SDK becomes. |
| 5 | **Absent Kubernetes infrastructure blocks production deployment** | Medium | High | The system is architected as a Docker Compose application. The four-GPU NIM container requirement, the TimescaleDB time-series data, the Milvus vector index, and the MCP adapter layer are all single-host, single-process components. Scaling to handle production warehouse traffic (real-time IoT ingestion, concurrent operator sessions, scheduled forecasting runs) requires Kubernetes. Building the Helm chart and StatefulSet configurations is High complexity, and starting this work early is required to avoid a deployment blocker late in the modernization timeline. |

---

## 7. Summary

### What Must Be Built From Scratch

The following capabilities have no meaningful code to reuse. They require greenfield implementation:

| Capability | Estimated Size |
|-----------|----------------|
| ModelGateway with capability routing | Medium service (~500 LOC) |
| Model registry (YAML + Pydantic loader) | Small (~200 LOC + manifest files) |
| DecisionEngine + policy manifest | Medium service (~800 LOC) |
| Typed event model + Kafka producer | Small-Medium (~400 LOC + schemas) |
| Trajectory store (writer + schema) | Medium (~600 LOC + DB migration) |
| Human approval gating (interrupt/resume + UI) | Large (~1,200 LOC across graph, DB, router, frontend) |
| Simulation-before-execution mode | Medium (~600 LOC per domain) |
| SFT data pipeline | Large (data formatting, NeMo Framework integration) |
| GRPO reward functions + training pipeline | Large (separate from SFT) |
| Model promotion gate CI job | Small (~300 LOC) |
| Kubernetes Helm chart | Large (~2,000 lines of YAML across all services) |
| OpenTelemetry instrumentation | Medium (~400 LOC + OTel collector config) |

### What Can Be Adapted (Significant Rework Required)

| Capability | Current Asset | Rework Required |
|-----------|--------------|-----------------|
| Official MCP SDK migration | Custom server/client in `src/api/services/mcp/` | Replace JSON-RPC layer with `mcp` SDK; preserve adapter tool implementations |
| MCP server extraction to standalone containers | In-process `MCPAdapter` classes | Add HTTP transport, service discovery, Dockerfiles per domain |
| AgentRuntime abstraction | `MCPPlannerGraph` class | Extract `AgentRuntime` interface; keep LangGraph as implementation |
| WarehouseState typed models | `MCPWarehouseState` TypedDict | Replace `Dict[str, Any]` fields with Pydantic models; add freshness metadata |
| Evaluation framework | `tests/quality/` scripts + `EvidenceScoringEngine` | Add golden-answer corpus, CI integration, offline mock backend |
| Auth enforcement on all write endpoints | JWT + RBAC exist in `src/api/services/auth/` | Apply `Depends(get_current_user)` to all non-health routers |
| Postgres checkpointing (replacing no-checkpointer) | LangGraph compile call in `mcp_integrated_planner_graph.py` | Migrate CVE-affected SQLite checkpoint to `langgraph-checkpoint-postgres` |
| Optimization service contract for RAPIDS | `Dockerfile.rapids` + `scripts/forecasting/` | Add HTTP API wrapper, replace subprocess call in training router |

### What Is Well-Positioned (Extend Rather Than Replace)

| Asset | Path | Next Step |
|-------|------|-----------|
| `NIMClient` with Nemotron parameter injection | `src/api/services/llm/nim_client.py` | Grow into ModelGateway by absorbing other call sites and adding model registry lookup |
| Domain action tool methods | `src/api/agents/*/action_tools.py` | Wrap with `@server.tool()` decorators when migrating to official MCP SDK |
| TimescaleDB hypertable schema | `data/postgres/migrations/003_timescale_hypertables.sql` | Add `trajectories` hypertable with agent execution schema |
| NeMo Guardrails + security blocklist | `src/api/services/guardrails/`, `src/api/services/mcp/security.py` | Integrate as a gate within DecisionEngine rather than standalone middleware |
| Document six-stage pipeline | `src/api/agents/document/` | Surface as a first-class `maiw-mcp-document` server with official SDK |
| Prometheus + Grafana stack | `monitoring/` | Extend with OTel collector as an additional sink; add `model` and `tool_name` metric labels |
| MCP security, parameter validation, tool discovery | `src/api/services/mcp/security.py`, `parameter_validator.py`, `tool_discovery.py` | Retain as server-side middleware in each extracted MCP capability server |

### Recommended Sequencing

The modernization program has three hard dependencies that must be resolved before most other work can proceed in parallel:

1. **Trajectory Store** — unblocks SFT, GRPO, evaluation framework, and regression scenarios. Zero blocking dependencies. Start immediately.
2. **Model Registry** — unblocks ModelGateway, dynamic model routing, and model promotion gates. Zero blocking dependencies. Start immediately, in parallel with trajectory store.
3. **Auth enforcement on all write endpoints** — a correctness fix, not a modernization feature. Apply `Depends(get_current_user)` and map roles to the existing RBAC `ROLE_PERMISSIONS` matrix. This is the highest-risk item in the system and the fastest to fix.

Once those three are in place, the Official MCP SDK migration and MCP server extraction can proceed as the central architectural transformation. The DecisionEngine, AgentRuntime abstraction, WarehouseState typed model, and OTel instrumentation are best sequenced in the same phase as MCP server extraction, since they share the same structural boundaries. Kubernetes and the SFT/GRPO pipelines are Phase 3 — they depend on having stable, independently deployable services and accumulated trajectory data respectively.
