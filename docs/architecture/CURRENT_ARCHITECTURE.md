# Current Architecture — Multi-Agent Intelligent Warehouse (MAIW)

> Generated: 2026-08-20. Based on static analysis of the repository at commit `e33ed69`.
> All file paths are relative to the repository root unless otherwise noted.

---

## 1. Executive Summary

MAIW is a warehouse operational assistant that exposes a FastAPI (Python 3.11) REST backend on port 8001, a React 19 / TypeScript single-page application on port 3001, and an nginx reverse proxy on port 3000. The conversational interface routes user queries through a LangGraph state machine to one of five domain-specific AI agents (equipment, operations, safety, forecasting, document), each of which calls NVIDIA NIM-hosted LLMs via a custom `httpx`-based client and executes domain tools against PostgreSQL, Redis, Milvus, and external adapter services. The system is packaged entirely with Docker Compose; there is no Kubernetes or Helm configuration. NeMo Guardrails wraps every LLM call, and NVIDIA RAPIDS GPU forecasting runs in an optional sidecar container.

---

## 2. Repository Structure

```
Multi-Agent-Intelligent-Warehouse/
│
├── data/
│   ├── config/
│   │   ├── agents/                  # Per-agent YAML persona/prompt configs
│   │   │   ├── equipment_agent.yaml
│   │   │   ├── operations_agent.yaml
│   │   │   ├── forecasting_agent.yaml
│   │   │   ├── document_agent.yaml
│   │   │   └── safety_agent.yaml
│   │   └── guardrails/              # NeMo Guardrails Colang flows + config
│   │       ├── rails.co
│   │       ├── rails.yaml
│   │       └── config.yml
│   ├── postgres/                    # SQL DDL files (applied on first run)
│   │   ├── 000_schema.sql           # Core tables + Frito-Lay SKU seed data
│   │   ├── 001_equipment_schema.sql # Equipment asset/telemetry tables + seed
│   │   ├── 002_document_schema.sql  # Document pipeline tables
│   │   ├── 004_inventory_movements_schema.sql
│   │   └── migrations/              # Schema migration versioning
│   ├── sample/forecasts/            # Pre-generated forecast JSON files
│   └── uploads/                     # Runtime PDF upload storage
│
├── deploy/
│   └── compose/                     # All Docker Compose variants
│       ├── docker-compose.dev.yaml  # Primary dev stack (all services)
│       ├── docker-compose.gpu.yaml  # GPU-accelerated Milvus + infra overlay
│       ├── docker-compose.monitoring.yaml
│       ├── docker-compose.ci.yml
│       ├── docker-compose.rapids.yml
│       ├── docker-compose.versioned.yaml
│       ├── docker-compose.yaml      # Legacy/placeholder stub
│       └── nginx.conf               # Active nginx reverse proxy config
│
├── docs/                            # Architecture, API, deployment docs (static)
├── monitoring/                      # Prometheus + Grafana + Alertmanager configs
│   ├── prometheus/
│   ├── grafana/
│   └── alertmanager/
├── notebooks/setup/                 # Single Jupyter setup guide
├── scripts/
│   ├── data/                        # Synthetic data generators (DB seeding)
│   ├── forecasting/                 # RAPIDS/scikit-learn offline training scripts
│   ├── security/                    # Dependency blocklist checker
│   ├── setup/                       # dev_up.sh, install_rapids.sh
│   ├── testing/                     # Integration test scripts
│   └── tools/                       # Debug/benchmark utilities
│
├── src/
│   ├── adapters/                    # ERP, IoT, RFID/barcode, WMS, attendance adapters
│   ├── api/
│   │   ├── app.py                   # FastAPI application entrypoint
│   │   ├── agents/
│   │   │   ├── document/            # 6-stage NeMo document extraction pipeline
│   │   │   ├── forecasting/         # Forecasting agent + action tools
│   │   │   ├── inventory/           # Equipment/inventory agents + action tools
│   │   │   ├── operations/          # Operations coordination agent
│   │   │   └── safety/              # Safety & compliance agent
│   │   ├── cli/migrate.py           # DB migration CLI
│   │   ├── graphs/
│   │   │   ├── mcp_integrated_planner_graph.py  # Active planner (used by API)
│   │   │   ├── mcp_planner_graph.py             # Phase-2 intermediate (unused)
│   │   │   └── planner_graph.py                 # Legacy planner (unused)
│   │   ├── middleware/
│   │   │   └── security_headers.py  # HSTS, CSP, X-Frame-Options, etc.
│   │   ├── routers/                 # 18 API routers
│   │   ├── services/
│   │   │   ├── agent_config.py      # YAML agent config loader
│   │   │   ├── auth/                # JWT handler, user service, dependencies
│   │   │   ├── cache/               # Query response cache (LRU+TTL)
│   │   │   ├── database.py          # asyncpg connection pool
│   │   │   ├── deduplication/       # In-flight request deduplicator
│   │   │   ├── document/            # Document DB service, job queue, retry
│   │   │   ├── erp/                 # ERP integration service
│   │   │   ├── evidence/            # Evidence collection + integration
│   │   │   ├── guardrails/          # NeMo Guardrails SDK + pattern fallback
│   │   │   ├── iot/                 # IoT integration service
│   │   │   ├── llm/nim_client.py    # NVIDIA NIM httpx client (LLM + embeddings)
│   │   │   ├── mcp/                 # Custom MCP abstraction layer
│   │   │   │   ├── base.py          # MCPAdapter, MCPToolBase, MCPManager
│   │   │   │   ├── client.py        # MCPClient (HTTP/WS/STDIO)
│   │   │   │   ├── server.py        # MCPServer (JSON-RPC 2.0 in-process)
│   │   │   │   ├── security.py      # Tool blocklist, SecurityViolationError
│   │   │   │   ├── tool_discovery.py
│   │   │   │   ├── tool_binding.py
│   │   │   │   ├── tool_routing.py
│   │   │   │   ├── parameter_validator.py
│   │   │   │   └── adapters/        # Domain MCP adapters
│   │   │   ├── memory/              # Conversation memory, context enhancer
│   │   │   ├── monitoring/          # Prometheus metrics, performance monitor
│   │   │   ├── quick_actions/       # Contextual quick-action suggestions
│   │   │   ├── reasoning/           # Multi-step reasoning engine
│   │   │   ├── routing/             # SemanticRouter (embedding-based)
│   │   │   ├── scanning/            # Barcode/RFID integration
│   │   │   ├── security/            # Rate limiter
│   │   │   ├── validation/          # Response validator + enhancer
│   │   │   ├── wms/                 # WMS integration service
│   │   │   └── version.py
│   │   └── utils/
│   │       ├── error_handler.py     # Global exception handlers
│   │       └── log_utils.py         # Log sanitization, prompt injection guards
│   ├── memory/memory_manager.py
│   ├── retrieval/
│   │   ├── hybrid_retriever.py      # BM25 + vector hybrid retrieval
│   │   ├── enhanced_hybrid_retriever.py
│   │   ├── gpu_hybrid_retriever.py
│   │   ├── vector/
│   │   │   ├── milvus_retriever.py
│   │   │   ├── gpu_milvus_retriever.py
│   │   │   ├── enhanced_retriever.py
│   │   │   ├── embedding_service.py
│   │   │   └── evidence_scoring.py
│   │   ├── structured/              # SQL-based structured retriever
│   │   ├── caching/
│   │   └── response_quality/
│   └── ui/web/                      # React 19 + TypeScript SPA
│       └── src/
│           ├── App.tsx              # Root router, 13 routes, AuthProvider
│           ├── contexts/AuthContext.tsx
│           ├── components/          # Layout, chat components, MCP test panels
│           ├── pages/               # Dashboard, ChatInterfaceNew, Equipment, etc.
│           ├── services/
│           │   ├── api.ts           # axios client + all API method groups
│           │   ├── forecastingAPI.ts
│           │   ├── inventoryAPI.ts
│           │   └── trainingAPI.ts
│           └── theme/nvidiaTheme.ts # NVIDIA brand MUI theme
│
├── tests/
│   ├── unit/                        # ~26 files, ~340 collected tests
│   ├── integration/                 # 14 files (5 broken: missing asyncpg/pytest-asyncio)
│   ├── performance/                 # MCP + backend latency/throughput tests
│   └── quality/                     # NL answer quality evaluation
│
├── .github/workflows/               # ci-cd.yml, main.yml, release.yml, codeql.yml
├── Dockerfile                       # Multi-stage: frontend build + FastAPI backend
├── Dockerfile.backend               # Backend-only (dev)
├── Dockerfile.frontend              # React CRA dev server
├── Dockerfile.rapids                # NVIDIA RAPIDS GPU forecasting sidecar
├── pyproject.toml                   # Package: warehouse-operational-assistant 1.0.0
├── requirements.txt                 # Full dev deps
├── requirements.docker.txt          # Slimmed Docker deps (no RAPIDS, no nemoguardrails)
├── requirements.lock                # pip-compiled lock
└── package.json                     # Root: commitizen, semantic-release, husky
```

---

## 3. Technology Stack

### Backend Runtime
| Component | Library / Version | Notes |
|---|---|---|
| Web framework | `fastapi >= 0.120.0` | Uvicorn ASGI server, port 8001 |
| Agent orchestration | `langgraph >= 1.0.5` + `langgraph-checkpoint >= 3.0.0` | StateGraph, no checkpointer (CVE-2025-8709) |
| LLM client | Custom `httpx.AsyncClient` in `src/api/services/llm/nim_client.py` | No OpenAI SDK, no LangChain LLM wrappers |
| LLM model | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | Via NVIDIA NIM hosted at `integrate.api.nvidia.com/v1` |
| Embedding model | `nvidia/llama-nemotron-embed-vl-1b-v2` | 2048-dim, same NIM endpoint |
| Guardrails | `nemoguardrails >= 0.19.0` | Pattern fallback when SDK disabled |
| Vector DB | `pymilvus >= 2.3.0` | Collection `warehouse_docs`, IVF_FLAT index |
| Relational DB | `asyncpg >= 0.29.0` + TimescaleDB | PostgreSQL 5435, hypertables for time-series |
| Caching | `redis >= 5.0.0` | Query cache + rate limiting |
| Message bus | Kafka (`kafka-python`) | Async event bus, wired but not central to chat path |
| Object storage | MinIO | S3-compatible; used by Milvus |
| PDF processing | `pdfplumber 0.11.8`, `pdf2image 1.17.0`, `Pillow >= 10.3.0` |
| Industrial protocols | `paho-mqtt >= 1.6.0`, `pymodbus >= 3.0.0`, `bacpypes3 >= 0.0.100`, `pyserial >= 3.5` |
| ML / forecasting | `scikit-learn >= 1.5.0`, `xgboost >= 1.6.0`, RAPIDS `cudf-cu12`/`cuml-cu12` (optional) |
| Metrics | `prometheus-client >= 0.19.0` |
| Validation | `pydantic >= 2.0` |
| Auth | `python-jose[cryptography]`, `passlib[bcrypt]` |

### Frontend Runtime
| Component | Library / Version |
|---|---|
| Framework | React 19.2 + TypeScript 4.7 |
| Build tool | Create React App + CRACO override |
| UI components | MUI (Material UI) v5 |
| State management | `@tanstack/react-query` v5 + React Context |
| Routing | `react-router-dom` v6 |
| Charts | `recharts` v2, `@mui/x-data-grid` v7 |
| HTTP client | `axios` v1.8 (`allowAbsoluteUrls: false`) |

### Infrastructure
| Component | Technology |
|---|---|
| Reverse proxy | nginx (deploy/compose/nginx.conf) |
| Containerization | Docker + Docker Compose only (no Kubernetes) |
| CI/CD | GitHub Actions (ci-cd.yml, main.yml, release.yml) |
| Observability | Prometheus + Grafana + Alertmanager (monitoring/) |
| Semantic versioning | semantic-release + commitizen |

---

## 4. Runtime Architecture Diagram

```
                         ┌─────────────────────────────────────────────────────┐
                         │                  Docker Compose (dev)               │
                         │                                                     │
  Browser ──────────────►│  nginx :3000                                        │
                         │    ├── location /        → frontend:3001            │
                         │    └── location /api/    → backend:8001             │
                         │         (proxy_buffering off, timeout 300s)         │
                         │                                                     │
                         │  ┌──────────────────────────────────────────────┐  │
                         │  │  React SPA  (Dockerfile.frontend, :3001)     │  │
                         │  │  src/ui/web/                                  │  │
                         │  │  axios → /api/v1/*  (dev proxy → :8001)      │  │
                         │  └──────────────────────────────────────────────┘  │
                         │                                                     │
                         │  ┌──────────────────────────────────────────────┐  │
                         │  │  FastAPI Backend  (Dockerfile.backend, :8001)│  │
                         │  │  src/api/app.py                              │  │
                         │  │                                              │  │
                         │  │  Middleware stack (outermost → innermost):   │  │
                         │  │    Metrics → Size limit → Rate limit →       │  │
                         │  │    CORS → SecurityHeaders                    │  │
                         │  │                                              │  │
                         │  │  18 Routers (all under /api/v1/)            │  │
                         │  │    chat ──► MCPIntegratedPlannerGraph        │  │
                         │  │    equipment, inventory, operations,         │  │
                         │  │    safety, forecasting, document, auth,      │  │
                         │  │    mcp, wms, iot, erp, scanning,             │  │
                         │  │    attendance, reasoning, training,          │  │
                         │  │    migration, health                         │  │
                         │  └──────────┬───────────────────────────────────┘  │
                         │             │                                       │
                         │    ┌────────▼────────────────────────────────┐     │
                         │    │    LangGraph StateGraph                 │     │
                         │    │    src/api/graphs/                      │     │
                         │    │    mcp_integrated_planner_graph.py      │     │
                         │    │                                         │     │
                         │    │  route_intent                           │     │
                         │    │     ├── equipment ──► MCPEquipmentAgent │     │
                         │    │     ├── operations ► MCPOperationsAgent │     │
                         │    │     ├── safety ──── ► MCPSafetyAgent    │     │
                         │    │     ├── forecasting ► ForecastingAgent  │     │
                         │    │     ├── document ── ► MCPDocumentAgent  │     │
                         │    │     ├── general ─── ► ToolDiscovery     │     │
                         │    │     └── ambiguous ─ ► clarify           │     │
                         │    │     └─── all → synthesize → END         │     │
                         │    └────────┬────────────────────────────────┘     │
                         │             │                                       │
                         │    ┌────────▼────────────────────────────────┐     │
                         │    │   NIMClient (src/api/services/llm/)     │     │
                         │    │   httpx.AsyncClient                      │     │
                         │    └────────┬────────────────────────────────┘     │
                         │             │                                       │
                         └─────────────┼───────────────────────────────────────┘
                                       │
              ┌────────────────────────┼──────────────────────────────┐
              │                        │  External / Sidecar           │
              │                        ▼                               │
              │   ┌─────────────────────────────────────────────┐     │
              │   │  NVIDIA NIM API  integrate.api.nvidia.com   │     │
              │   │  POST /chat/completions                      │     │
              │   │  Model: nvidia/llama-3.3-nemotron-super-49b  │     │
              │   │  POST /embeddings                            │     │
              │   │  Model: nvidia/llama-nemotron-embed-vl-1b    │     │
              │   └─────────────────────────────────────────────┘     │
              │                                                        │
              │   TimescaleDB :5435   Redis :6379   Milvus :19530      │
              │   Kafka :9092         MinIO :9000   etcd :2379         │
              │                                                        │
              │   RAPIDS sidecar (Dockerfile.rapids, :8002)           │
              │   scripts/forecasting/rapids_gpu_forecasting.py        │
              └────────────────────────────────────────────────────────┘
```

---

## 5. Request Runtime Flow

The following traces a `POST /api/v1/chat` request end-to-end with actual file paths.

```
1. Browser / API client
   POST /api/v1/chat  { message, session_id, context, enable_reasoning }

2. nginx (deploy/compose/nginx.conf)
   location /api/ → proxy_pass http://backend:8001
   proxy_buffering off (supports future streaming)

3. FastAPI middleware stack  (src/api/app.py)
   a. MetricsMiddleware         → increments http_requests_total
   b. RequestSizeMiddleware     → rejects if Content-Length > 10 MB
   c. RateLimitMiddleware       → checks Redis; 30 req/min on /chat
   d. CORSMiddleware
   e. SecurityHeadersMiddleware (src/api/middleware/security_headers.py)

4. Chat router  (src/api/routers/chat.py  →  async def chat())
   a. request_id = uuid4()
   b. QueryCache.get(message, session_id, context)
      → HIT: return cached ChatResponse immediately
      → MISS: continue
   c. RequestDeduplicator: concurrent identical requests share one future
   d. GuardrailsService.check_input_safety(message)   timeout=3s
      → UNSAFE: return _create_safety_violation_response()
   e. Classify complexity → choose graph_timeout (120–460 s)
   f. get_mcp_planner_graph()  timeout=2s
      → src/api/graphs/mcp_integrated_planner_graph.py  (singleton)

5. MCPIntegratedPlannerGraph.process_warehouse_query()
   asyncio.wait_for(graph.ainvoke(initial_state), timeout=graph_timeout)

6. LangGraph node: _mcp_route_intent()
   src/api/graphs/mcp_integrated_planner_graph.py  ~line 300
   a. MCPIntentClassifier.classify_intent(message)  keyword scoring
   b. SemanticRouter.classify_intent_semantic()
      src/api/services/routing/semantic_router.py
      → NIMClient.generate_embeddings(message)
      → cosine_similarity(embedding, intent_category_descriptions)
   c. Blend keyword + semantic confidence → routing_decision

7. LangGraph node: _mcp_<domain>_agent()
   Example: _mcp_equipment_agent()
   asyncio.wait_for(agent.process_query(...), timeout=90–180s)

8. MCPEquipmentAssetOperationsAgent.process_query()
   src/api/agents/inventory/mcp_equipment_agent.py
   a. _parse_equipment_query()
      → fast keyword path (no LLM) for simple queries
      → NIMClient.generate_response(parse_prompt) for complex
   b. _discover_relevant_tools()
      → ToolDiscoveryService.get_available_tools()
      src/api/services/mcp/tool_discovery.py
   c. _create_tool_execution_plan()
   d. _execute_tool_plan()  (for each tool in plan)
      → ToolDiscoveryService.execute_tool(tool_id, arguments)
      → MCPAdapter.execute_tool(name, arguments)
        src/api/services/mcp/adapters/equipment_adapter.py
      → EquipmentAssetTools.get_equipment_status(...)
        src/api/agents/inventory/equipment_asset_tools.py
      → SQLRetriever.fetch_all("SELECT ... FROM equipment_assets ...")
        src/retrieval/structured/  (asyncpg parameterized query)
      ← Dict[str, Any]
   e. _generate_response_with_tools()
      → NIMClient.generate_response(prompt_with_tool_results,
                                     temperature=0.0, max_tokens=2000)
        src/api/services/llm/nim_client.py
      → POST https://integrate.api.nvidia.com/v1/chat/completions
        Authorization: Bearer $NVIDIA_API_KEY
        model: nvidia/llama-3.3-nemotron-super-49b-v1.5
        chat_template_kwargs: {enable_thinking: false}   (default)
      ← assistant message
   f. Second NIM call → natural_language string (temperature=0.4)
   g. Third NIM call  → recommendations (temperature=0.3)
   ← MCPEquipmentResponse(natural_language, data, recommendations,
                           confidence, mcp_tools_used, reasoning_chain)

9. LangGraph node: _mcp_synthesize_response()
   src/api/graphs/mcp_integrated_planner_graph.py
   → extracts natural_language string (guards against dict leakage)
   → state["final_response"] = natural_language
   → state["context"]["structured_response"] = full response dict
   → state["context"]["mcp_tools_used"] = tool name list

10. Back in ChatRouter  (src/api/routers/chat.py)
    a. Enhancement pipeline (parallelized, 25s timeout each,
       skipped for simple/reasoning queries):
       - EvidenceIntegrationService.enhance_with_evidence()
       - SmartQuickActionsService.generate_quick_actions()
       - ContextEnhancer.enhance_with_context()  (conversation memory)
    b. GuardrailsService.check_output_safety(response)  timeout=5s
    c. _format_user_response() → adds bullets, confidence emoji, footer
    d. ResponseValidator.validate(response, query, tool_results)
    e. QueryCache.set(key, response, ttl=300s)
    f. PerformanceMonitor.end_request(request_id, ...)

11. FastAPI returns ChatResponse JSON
    { reply, route, intent, session_id, structured_data,
      recommendations, confidence, mcp_tools_used,
      tool_execution_results, reasoning_chain, ... }
```

---

## 6. Agent Inventory

| Agent Class | File | LangGraph Node | Primary LLM | Tools Owned | Prompt Location |
|---|---|---|---|---|---|
| `MCPEquipmentAssetOperationsAgent` | `src/api/agents/inventory/mcp_equipment_agent.py` | `_mcp_equipment_agent` | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | `get_equipment_status`, `assign_equipment`, `get_equipment_utilization`, `get_maintenance_schedule`; also inventory tools via `EquipmentActionTools` | `data/config/agents/equipment_agent.yaml` |
| `EquipmentAssetOperationsAgent` (non-MCP) | `src/api/agents/inventory/equipment_agent.py` | Not in active graph | Same NIM model | Same equipment tools | Same YAML |
| `MCPOperationsCoordinationAgent` | `src/api/agents/operations/mcp_operations_agent.py` | `_mcp_operations_agent` | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | `create_task`, `assign_task`, `get_task_status`, `get_workforce_status`, pick wave, workload rebalance | `data/config/agents/operations_agent.yaml` |
| `MCPSafetyComplianceAgent` | `src/api/agents/safety/mcp_safety_agent.py` | `_mcp_safety_agent` | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | `log_incident`, `start_checklist`, `broadcast_alert`, `get_safety_procedures`, lockout-tagout, near-miss | `data/config/agents/safety_agent.yaml` |
| `ForecastingAgent` | `src/api/agents/forecasting/forecasting_agent.py` | `_mcp_forecasting_agent` | `nvidia/llama-3.3-nemotron-super-49b-v1.5` | `get_forecast`, `get_batch_forecast`, `get_reorder_recommendations`, `get_model_performance`, `get_forecast_dashboard`, `get_business_intelligence` | `data/config/agents/forecasting_agent.yaml` |
| `DocumentExtractionAgent` | `src/api/agents/document/document_extraction_agent.py` | `_mcp_document_agent` | Stage 3: Llama-Nemotron-Nano-VL-8B; Stage 5: `nvidia/llama-3.3-nemotron-super-49b-v1.5` | `upload_document`, `get_document_status`, `extract_document_data`, `validate_document_quality`, `search_documents`, `approve_document`, `reject_document` | `data/config/agents/document_agent.yaml` |
| General / fallback | Inline in `_mcp_general_agent` node | `_mcp_general_agent` | Same NIM model | Any tool discovered by `ToolDiscoveryService` | No YAML; uses ToolDiscovery catalog |

---

## 7. Model Execution Path

All agent LLM calls flow through a single shared client. There is no LangChain LLM wrapper, no `ChatNVIDIA`, no OpenAI SDK anywhere in `src/`.

```
Agent method calls:
  self.nim_client.generate_response(prompt, temperature=0.0, max_tokens=2000)

NIMClient.generate_response()
  src/api/services/llm/nim_client.py

  1. Build messages list from prompt string
  2. If "nemotron" in model_name (line 402):
       if enable_thinking=False (default):
         prepend /no_think to system message
         payload["chat_template_kwargs"] = {"enable_thinking": False}
       else:
         payload["reasoning_budget"] = LLM_REASONING_BUDGET
  3. Retry loop (max 3 attempts, backoff 2**attempt seconds):
       await self.llm_client.post(
           "/chat/completions",
           json={
               "model": "nvidia/llama-3.3-nemotron-super-49b-v1.5",
               "messages": [...],
               "temperature": temperature,
               "max_tokens": max_tokens,
               "top_p": 1.0,
               "stream": False,
               ...
           }
       )
       # llm_client = httpx.AsyncClient(
       #     base_url=LLM_NIM_URL,  # https://integrate.api.nvidia.com/v1
       #     timeout=240,            # LLM_CLIENT_TIMEOUT
       #     headers={"Authorization": f"Bearer {NVIDIA_API_KEY}"}
       # )
  4. Response: choices[0].message.content → str
  5. Cache result in Redis (TTL=300s) if LLM_CACHE_ENABLED=true

Embedding calls:
  NIMClient.generate_embeddings(texts)
    await self.embedding_client.post(
        "/embeddings",
        json={"model": "nvidia/llama-nemotron-embed-vl-1b-v2", "input": texts}
    )
    → embeddings[0].embedding  # float[2048]
```

**Document pipeline uses additional standalone httpx clients** (not the shared NIMClient):
- `src/api/agents/document/processing/small_llm_processor.py` → Llama-Nemotron-Nano-VL-8B via `LLAMA_NANO_VL_API_KEY`
- `src/api/agents/document/validation/large_llm_judge.py` → same 49B model via `NVIDIA_API_KEY`, own client per request
- `src/api/agents/document/ocr/nemotron_parse.py` → NeMo Parse endpoint via `NEMO_PARSE_API_KEY`

---

## 8. Tool Execution Path

```
Agent._execute_tool_plan(plan)
  for each step in plan:
    tool_discovery.execute_tool(tool_id, arguments)
      src/api/services/mcp/tool_discovery.py

      1. Lookup DiscoveredTool by tool_id (UUID)
      2. Security gate: is_tool_blocked(tool_name)
         src/api/services/mcp/security.py
      3. Route by source type:
         → "mcp_adapter": adapter.execute_tool(tool_name, arguments)

MCPAdapter.execute_tool(tool_name, arguments)
  src/api/services/mcp/base.py

  1. MCPParameterValidator.validate_tool_parameters(tool_name, schema, arguments)
     src/api/services/mcp/parameter_validator.py
  2. tool = self.tools[tool_name]   # MCPTool dataclass
  3. result = await tool.handler(arguments)

Example: EquipmentMCPAdapter._handle_get_equipment_status(arguments)
  src/api/services/mcp/adapters/equipment_adapter.py
  → self.equipment_tools.get_equipment_status(
        asset_id=arguments.get("asset_id"),
        equipment_type=arguments.get("equipment_type"),
        ...
    )

EquipmentAssetTools.get_equipment_status(...)
  src/api/agents/inventory/equipment_asset_tools.py
  → sql_retriever.fetch_all(
        "SELECT * FROM equipment_assets WHERE ...",
        *params
    )
    src/retrieval/structured/  (asyncpg connection from pool)
    → List[Record]
  ← Dict[str, Any]  {"assets": [...], "total_count": N}

Result flows back up to agent → fed into NIM LLM prompt as context
```

**Tool execution timeout**: 15 seconds (hardcoded in `_execute_tool_plan`). Per-tool retries use delays of 1s, 2s, 4s.

---

## 9. MCP Architecture (Actual)

**The MCP implementation in MAIW is entirely custom and homegrown. It does not use the official Anthropic MCP Python SDK (`mcp` package).**

The official `mcp` package (v1.27.0) is present in a separate project's virtualenv at `/home/nvidia/nvidia-wms-workshop/.venv/` and is not listed in `requirements.txt` or imported anywhere in `src/`.

### What the Custom Implementation Provides

| Component | File | What It Does |
|---|---|---|
| `MCPServer` | `src/api/services/mcp/server.py` | In-process JSON-RPC 2.0 handler. Protocol version `2024-11-05`. Handles `tools/list`, `tools/call`, `resources/list`, `resources/read`, `prompts/list`, `prompts/get`, `initialize`, `ping`. |
| `MCPClient` | `src/api/services/mcp/client.py` | Client that can connect to remote MCP servers via HTTP, WebSocket, or STDIO. Not used in the current chat path — all tool calls go through local adapters. |
| `MCPAdapter` | `src/api/services/mcp/base.py` | Abstract base for domain adapters. Subclasses implement `initialize()`, `connect()`, `disconnect()`, `health_check()`. `execute_tool()` dispatches to `tool.handler`. |
| `MCPManager` | `src/api/services/mcp/base.py` | Registry of servers, clients, and adapters. `initialize_all()` connects all adapters and registers tools. |
| `ToolDiscoveryService` | `src/api/services/mcp/tool_discovery.py` | Discovers tools from adapters, categorizes them (`ToolCategory` enum), enforces security blocklist at registration and execution, tracks usage stats and success rates. |
| `MCPParameterValidator` | `src/api/services/mcp/parameter_validator.py` | JSON Schema-style validation of tool arguments before dispatch. |
| `ToolBindingService` | `src/api/services/mcp/tool_binding.py` | Strategies: EXACT_MATCH, FUZZY_MATCH, SEMANTIC_MATCH, CATEGORY_MATCH, PERFORMANCE_BASED. |
| `ToolRoutingService` | `src/api/services/mcp/tool_routing.py` | Initialized to `None` in active graph — commented as "skip complex routing for now". |
| Security | `src/api/services/mcp/security.py` | 30+ blocked tool name regex patterns, blocked capabilities, blocked parameter names. Prevents code execution tools from registration. No per-user RBAC. |

### Domain Adapters Registered

Registered via `src/api/routers/mcp.py → _register_mcp_adapters()`:

| Adapter | Registered Name | Wraps |
|---|---|---|
| `EquipmentMCPAdapter` | `"equipment_asset_tools"` | `EquipmentAssetTools` |
| `OperationsMCPAdapter` | `"operations_action_tools"` | `OperationsActionTools` |
| `SafetyMCPAdapter` | `"safety_action_tools"` | `SafetyActionTools` |
| `ForecastingMCPAdapter` | `"forecasting_action_tools"` | `ForecastingActionTools` |

The document agent uses direct API endpoints and is **not** registered as an MCP adapter.

### What MCP Gives vs. What Is Missing

The custom layer provides tool registration, parameter validation, security gating, and a discovery catalog. It does not provide: protocol-level transport (all calls are in-process), real MCP sessions, resource subscriptions, sampling, or any interoperability with external MCP clients.

---

## 10. Data and State Layer

### How Per-Request State Flows

State is ephemeral per-request via LangGraph `TypedDict`. There is no persistent warehouse state object.

```python
# Active state schema: src/api/graphs/mcp_integrated_planner_graph.py ~line 203
class MCPWarehouseState(TypedDict):
    messages: Annotated[List[BaseMessage], "Chat messages"]
    user_intent: Optional[str]
    routing_decision: Optional[str]
    agent_responses: Dict[str, str]
    final_response: Optional[str]
    context: Dict[str, any]
    session_id: str
    mcp_results: Optional[Any]
    tool_execution_plan: Optional[List[Dict[str, Any]]]
    available_tools: Optional[List[Dict[str, Any]]]
    enable_reasoning: bool
    reasoning_types: Optional[List[str]]
    reasoning_chain: Optional[Dict[str, Any]]
```

Each graph invocation creates a new state dict. No checkpointer is used (`workflow.compile()` with no checkpointer argument). Cross-session conversational memory is managed by `ConversationMemoryService` (Redis-backed) and read by `ContextEnhancer` during the enhancement pipeline.

### Database: PostgreSQL with TimescaleDB (port 5435)

Access: direct `asyncpg` connection pool. No ORM. All queries are raw parameterized SQL.

**Core tables (000_schema.sql):**
- `inventory_items(id, sku UNIQUE, name, quantity, location, reorder_point, updated_at)` — 16 Frito-Lay SKUs seeded
- `tasks(id, kind∈{pick,pack,putaway,cycle_count}, status, assignee, payload JSONB, created_at, updated_at)`
- `safety_incidents(id, severity, description, reported_by, occurred_at)`
- `equipment_telemetry(ts TIMESTAMPTZ, equipment_id, metric, value DOUBLE)` — TimescaleDB hypertable
- `users`, `user_sessions`, `audit_log`

**Equipment tables (001_equipment_schema.sql):**
- `equipment_assets(asset_id PK, type, model, zone, status, owner_user, next_pm_due, metadata JSONB)` — 12 seeded assets
- `equipment_assignments(id, asset_id FK, task_id, assignee, assignment_type, assigned_at, released_at)`
- `equipment_maintenance(id, asset_id FK, maintenance_type, performed_by, performed_at, cost)`
- `equipment_performance(id, asset_id FK, metric_name, metric_value, measured_at)`

**Document tables (002_document_schema.sql):**
- `documents`, `processing_stages`, `extraction_results`, `quality_scores`, `routing_decisions`, `document_search_metadata`

**Inventory movements (004_inventory_movements_schema.sql):**
- `inventory_movements(id, sku, movement_type∈{inbound,outbound,adjustment}, quantity, timestamp, location)`
- Materialized views: `daily_demand`, `weekly_demand`, `monthly_demand`, `brand_demand`

**Migration schema (migrations/002, 003):**
- `warehouse_locations`, `equipment`, `inventory_locations`, `operations`, `operation_items` — richer entity model not fully reflected in the active 000-004 schemas
- TimescaleDB hypertables: `telemetry_data`, `operation_metrics`, `inventory_movements`, `equipment_events`, `performance_metrics` — 1-year retention, continuous aggregates

### Database: Milvus (port 19530)

Collection `warehouse_docs` with fields: `id (VARCHAR 100)`, `content (VARCHAR 65535)`, `embedding (FLOAT_VECTOR dim=1024)`, `metadata (JSON)`. Index: IVF_FLAT, IP metric. Vector IDs cross-referenced in Postgres `document_search_metadata.search_vector_id`.

### Database: Redis (port 6379)

- LLM response cache: key = hash(messages+params), TTL = 300s
- Query-level response cache: key = hash(message+session_id+context), TTL = 300s
- Rate limiting: sliding-window counters per IP per endpoint
- Conversation memory: per-session turn history (via `ConversationMemoryService`)

---

## 11. Warehouse Operational Entities

These are the entities that exist in actual code (Pydantic models, dataclasses, or SQL tables). Nothing is invented.

### Inventory
- **`InventoryItem`**: `sku, name, quantity, location, reorder_point` (Pydantic + `inventory_items` table)
- **`InventoryMovement`**: `sku, movement_type, quantity, timestamp, location` (SQL only)
- **`ReservationResult`**, **`ReplenishmentTask`**, **`PurchaseRequisition`**: action tool return dataclasses
- **No wave planning structure exists** in the current codebase

### Equipment and Assets
- **`EquipmentAsset`**: `asset_id, type, model, zone, status, owner_user, next_pm_due, metadata` (Pydantic + SQL)
- **`EquipmentAssignment`**: `id, asset_id, task_id, assignee, assignment_type, assigned_at, released_at`
- **`EquipmentTelemetry`**: `timestamp, asset_id, metric, value, unit, quality_score` (Pydantic + TimescaleDB hypertable)
- **`MaintenanceRecord`**: `id, asset_id, maintenance_type, performed_by, performed_at, cost`
- **Seeded equipment types**: `forklift`, `amr`, `agv`, `scanner`, `charger`, `conveyor`, `humanoid`
- **Seeded telemetry metrics**: `battery_soc`, `temp_c`, `speed`, `location_x`, `location_y`, `voltage`, `current`, `power`

### Tasks and Labor
- **`Task`**: `id, kind∈{pick,pack,putaway,cycle_count}, status, assignee, payload JSONB` (Pydantic + SQL)
- **`TaskAssignment`**: action tool result dataclass from `OperationsActionTools.create_task()`
- **`WorkforceStatus`**: `total_workers, active_workers, available_workers, tasks_in_progress, tasks_pending`
- **`PickWave`**, **`PickPathOptimization`**: returned by `OperationsActionTools.generate_pick_wave()` and `optimize_pick_paths()`
- **No order management entity** exists beyond `payload JSONB` inside Task

### Safety
- **`SafetyIncident`**: `id, severity, description, reported_by, occurred_at` (Pydantic + SQL)
- **`SafetyChecklist`**, **`SafetyAlert`**, **`LockoutTagoutRequest`**, **`CorrectiveAction`**, **`SafetyDataSheet`**, **`NearMissReport`**: action tool return dataclasses
- **`SafetyPolicy`**: `id, name, category, last_updated, status, summary` (Pydantic; served from static data)

### Documents
- **`DocumentType`** enum: `pdf, image, scanned, mobile_photo, invoice, receipt, bol, purchase_order, packing_list, safety_report`
- **`ProcessingStage`** enum: `uploaded → preprocessing → ocr_extraction → llm_processing → embedding → validation → routing → completed/failed`

### Forecasting
- **`ForecastResult`**, **`ReorderRecommendation`**, **`ModelPerformanceMetrics`**, **`BusinessIntelligenceSummary`** (Pydantic)
- 38 SKUs tracked: Frito-Lay product codes (CHE, DOR, FRI, FUN, LAY, POP, RUF, SUN, TOS series)

---

## 12. RAG and Document Pipeline

### Retrieval (used by all agents)

Hybrid BM25 + dense vector retrieval:

```
HybridRetriever  (src/retrieval/hybrid_retriever.py)
  ├── MilvusRetriever  (src/retrieval/vector/milvus_retriever.py)
  │     embedding: NIMClient.generate_embeddings() → 2048-dim vector
  │     search: Milvus ANN query (IVF_FLAT, IP metric)
  │     collection: warehouse_docs
  └── SQLRetriever  (src/retrieval/structured/)
        raw parameterized asyncpg queries against TimescaleDB
```

GPU-accelerated variants exist: `gpu_hybrid_retriever.py`, `gpu_milvus_retriever.py` — used when Milvus is configured with GPU index.

Evidence scoring is applied after retrieval: `src/retrieval/vector/evidence_scoring.py` computes per-source confidence scores and overall quality assessments.

### Document Ingestion Pipeline

6-stage pipeline in `src/api/agents/document/`:

```
Stage 1: PREPROCESSING
  src/api/agents/document/preprocessing/nemo_retriever.py
  (NeMoRetrieverPreprocessor + LayoutDetectionService)
  → Image normalization, PDF splitting

Stage 2: OCR_EXTRACTION
  src/api/agents/document/ocr/nemo_ocr.py       → NeMo OCR
  src/api/agents/document/ocr/nemotron_parse.py  → Nemotron Parse endpoint
  Fallback model: meta/llama-3.2-11b-vision-instruct

Stage 3: LLM_PROCESSING (entity extraction)
  src/api/agents/document/processing/small_llm_processor.py
  Primary model: Llama-Nemotron-Nano-VL-8B  (LLAMA_NANO_VL_API_KEY)
  Vision fallback: meta/llama-3.2-11b-vision-instruct
  Text fallback: meta/llama-3.1-8b-instruct
  src/api/agents/document/processing/entity_extractor.py

Stage 4: EMBEDDING
  src/api/agents/document/processing/embedding_indexing.py
  Model: nvidia/llama-nemotron-embed-vl-1b-v2 (2048-dim)
  Writes to: Milvus collection warehouse_docs
  Records vector_id in: Postgres document_search_metadata

Stage 5: VALIDATION (LLM-as-judge)
  src/api/agents/document/validation/quality_scorer.py
  src/api/agents/document/validation/large_llm_judge.py
  Model: nvidia/llama-3.3-nemotron-super-49b-v1.5
  Scores 0-5: completeness, accuracy, compliance, quality
  Writes to: Postgres quality_scores

Stage 6: ROUTING
  src/api/agents/document/routing/intelligent_router.py
  src/api/agents/document/routing/workflow_manager.py
  Routes to: WMS integration, human review queue, or auto-approve
  Writes to: Postgres routing_decisions
```

Document binary files are stored at: `data/uploads/{uuid}_{original_filename}.pdf`

---

## 13. RAPIDS and Forecasting

### GPU Forecasting (Sidecar, Optional)

RAPIDS is **not in the live FastAPI `src/` code path**. It runs as a separate container.

```
Dockerfile.rapids
  Base: nvcr.io/nvidia/rapidsai/rapidsai:24.02-cuda12.0-runtime-ubuntu22.04-py3.10
  CMD: scripts/forecasting/rapids_gpu_forecasting.py
  Port: 8002

scripts/forecasting/rapids_gpu_forecasting.py:
  Tries: import cudf, cuml  (RAPIDS_AVAILABLE = True)
  Falls back to: sklearn + xgboost (RAPIDS_AVAILABLE = False)
  Models: Random Forest, Linear Regression, SVR, XGBoost,
          Gradient Boosting, Ridge Regression
  Output: ensemble average → rapids_gpu_forecasts.json
          (38 SKUs × 30 daily predictions + confidence intervals
           + per-model predictions)
```

The training router invokes the RAPIDS script via subprocess:
```python
# src/api/routers/training.py  ~line 176-181
if training_type == "advanced" and Path(rapids_script).exists():
    subprocess.Popen(["python", rapids_script])
```

### Live Forecasting Service

```
src/api/routers/advanced_forecasting.py  →  AdvancedForecastingService
  Reads: Postgres inventory_movements (via asyncpg)
         Pre-generated JSON files (data/sample/forecasts/)
  Serves: POST /api/v1/forecasting/real-time   → per-SKU forecast
          GET  /api/v1/forecasting/reorder-recommendations
          GET  /api/v1/forecasting/model-performance
          GET  /api/v1/forecasting/business-intelligence
          POST /api/v1/forecasting/batch-forecast (max 100 SKUs)
```

The `ForecastingAgent` (src/api/agents/forecasting/forecasting_agent.py) handles forecasting intents in the chat path and delegates to `ForecastingActionTools` which wraps the same `AdvancedForecastingService`.

---

## 14. Observability and Logging

### Logging

- **Format**: Plain text (`%(asctime)s - %(name)s - %(levelname)s - %(message)s`). No structured JSON logging. No `structlog`, no `python-json-logger`.
- **Configuration**: Inconsistent. No centralized `basicConfig` in `app.py`. Each module calls `logging.getLogger(__name__)`. Two files configure `basicConfig` locally (`cli/migrate.py`, `routers/advanced_forecasting.py`).
- **Log sanitization**: `src/api/utils/log_utils.py → sanitize_log_data()` strips/base64-encodes control characters. `chat.py` uses this on all user inputs before logging.
- **Level**: Uvicorn defaults to `info` (no `--log-level` flag in Dockerfile CMD).

### Metrics

Prometheus metrics exposed at `GET /api/v1/metrics` (no auth, rate-limit-exempt):

- `http_requests_total` (Counter, labels: method/endpoint/status)
- `http_request_duration_seconds` (Histogram, labels: method/endpoint)
- `warehouse_active_users`, `warehouse_tasks_*`, `warehouse_safety_*`, `warehouse_equipment_*` (Counters/Gauges)
- `warehouse_inventory_movements_total`, `warehouse_order_processing_duration_seconds`
- Environment-info metric

Source: `src/api/services/monitoring/metrics.py`

### In-Process Performance Monitor

`src/api/services/monitoring/performance_monitor.py` — tracks last 1000 requests in memory: latency (P50/P95/P99), cache hit/miss, error rate, timeout events, tool counts. Does **not** feed into Prometheus. Used by `AlertChecker` background task that runs every 60 seconds.

Alert thresholds (in-process only, logged at warning/error level):
- P95 latency > 30s
- Cache hit rate == 0% after >10 requests
- Error rate > 5%
- Timeout rate > 10%

### External Monitoring Stack (`monitoring/`)

- **Prometheus** scrapes: backend `:8001/api/v1/metrics`, Postgres `:5435`, Redis `:6379`, Milvus `:19530`, node-exporter `:9100`, cAdvisor `:8080` — all every 10s
- **Alertmanager** routes: critical → email + webhook, warning → email + webhook
- **Grafana** dashboards: `warehouse-overview.json`, `warehouse-operations.json`, `warehouse-safety.json`

### Distributed Tracing

**None.** Zero references to `opentelemetry`, `otel`, `span`, or distributed tracer anywhere in `src/`, `requirements.txt`, or `requirements.lock`.

### Correlation IDs

Partial. `chat.py` generates `request_id = str(uuid.uuid4())` per request and passes it through `PerformanceMonitor`. The ID is **not** returned in HTTP response headers, not propagated to downstream NIM calls, and not included in every log line. It exists for internal performance tracking only.

### Structured Agent Trajectory Logging

**None.** No LangSmith, LangFuse, or JSONL trace file. Reasoning steps are propagated through LangGraph state and included in the `ChatResponse` payload, but are not persisted to any dedicated trace store.

---

## 15. Training and Evaluation

### What Exists

| Capability | Status | Location |
|---|---|---|
| Unit tests (pytest) | Present — ~340 collected tests | `tests/unit/` |
| Integration tests | Present — 14 files, 5 broken (missing `asyncpg`/`pytest-asyncio`) | `tests/integration/` |
| Performance/load tests | Present — P50/P95/P99 latency, concurrency, endurance | `tests/performance/` |
| Security tests | Present — auth, RBAC, injection, encryption | `tests/integration/test_mcp_security_integration.py` |
| Answer quality evaluation | Present — live-agent NL quality scoring | `tests/quality/` |
| Reasoning chain evaluation | Present — CoT/multi-hop against live API | `tests/unit/test_reasoning_evaluation.py` |
| Evidence confidence scoring | Present in production | `src/retrieval/vector/evidence_scoring.py` |
| Guardrails (NeMo) | Present — SDK + pattern fallback | `src/api/services/guardrails/` |
| Prompt injection protection | Present — `SafePromptFormatter`, 16 unit tests | `src/api/utils/log_utils.py` |
| LLM-as-judge (document) | Present | `src/api/agents/document/validation/large_llm_judge.py` |
| Response validator | Present | `src/api/services/validation/response_validator.py` |
| Synthetic data generation | Present — DB seeding only, not ML training corpora | `scripts/data/` |
| CI/CD unit test gate | Present | `.github/workflows/ci-cd.yml` |

### What Is Absent

| Capability | Status |
|---|---|
| Supervised fine-tuning (SFT) | **ABSENT** |
| LoRA / PEFT adapter training | **ABSENT** |
| GRPO / RLHF / PPO | **ABSENT** |
| Chaos engineering framework | **ABSENT** (load simulation only in test files) |
| ML training corpus generation | **ABSENT** (synthetic data is for DB seeding only) |
| Standardized eval benchmarks | **ABSENT** (no RAGAS/DeepEval/HELM/MMLU integration) |
| Training or evaluation notebooks | **ABSENT** (one setup guide notebook only) |
| Human-in-the-loop blocking interrupt | **ABSENT** (`requires_approval` flag is metadata only; no `interrupt_before` in LangGraph) |
| Structured eval dataset (.jsonl) | **ABSENT** |

### CI Test Exclusions

The following 11 test files are explicitly `--ignore`d in `.github/workflows/ci-cd.yml` due to API drift or missing runtime fixtures:
`test_mcp_integrated_planner_graph.py`, `test_mcp_system.py`, `test_guardrails_sdk.py`, `test_all_agents.py`, `test_db_connection.py`, `test_enhanced_retrieval.py`, `test_mcp_planner_integration.py`, `test_document_pipeline.py`, `test_nvidia_integration.py`, `test_nvidia_llm.py`, `test_document_action_tools.py`.

---

## 16. Deployment Architecture

### Docker Compose (primary delivery mechanism)

All deployment is via Docker Compose. There is no Kubernetes, no Helm, no Terraform.

| Compose File | Purpose |
|---|---|
| `deploy/compose/docker-compose.dev.yaml` | **Primary dev stack**: TimescaleDB :5435, Redis :6379, Kafka :9092, etcd :2379, MinIO :9000/9001, Milvus :19530/9091, backend :8001, frontend :3001, nginx :3000, llm-nim (NIM LLaMA 3.3 Nemotron 49B :8000, 4-GPU reservation) |
| `deploy/compose/docker-compose.gpu.yaml` | GPU infrastructure overlay: Milvus v2.4.3-gpu with CUDA, Postgres/Redis/Kafka/ZooKeeper/etcd/MinIO |
| `deploy/compose/docker-compose.monitoring.yaml` | Prometheus + Grafana + Alertmanager |
| `deploy/compose/docker-compose.rapids.yml` | RAPIDS GPU forecasting sidecar |
| `deploy/compose/docker-compose.ci.yml` | CI/CD pipeline services |
| `deploy/compose/docker-compose.versioned.yaml` | Version-tagged image deployment |

### Dockerfiles

| File | Base | What It Builds |
|---|---|---|
| `Dockerfile` | `node:20.19.0-alpine` → `python:3.11-slim` | Multi-stage: builds React frontend, combines with FastAPI backend. Port 8001. |
| `Dockerfile.backend` | `python:3.11-slim` | Backend-only. Port 8001. |
| `Dockerfile.frontend` | `node:20.19.0-alpine` | React CRA dev server. Port 3001. Hot reload enabled. |
| `Dockerfile.rapids` | `nvcr.io/nvidia/rapidsai/rapidsai:24.02-cuda12.0-runtime-ubuntu22.04-py3.10` | RAPIDS GPU forecasting agent. Port 8002. |

All Dockerfiles create non-root users (`appuser` / `rapidsuser`). Backend images install `poppler-utils` for PDF processing. Build ARGs `VERSION`, `GIT_SHA`, `BUILD_TIME` are injected as ENV vars.

### nginx Configuration

`deploy/compose/nginx.conf`:
- Listens on port 80
- `client_max_body_size 10M`
- `location /` → proxy to `frontend:3001` (WebSocket upgrade for HMR)
- `location /api/` → proxy to `backend:8001` with `proxy_buffering off`, `proxy_read_timeout 300s`

Root-level `nginx.conf` is **empty** (placeholder).

### CI/CD

- `.github/workflows/ci-cd.yml` — Python 3.11, Node 22, PostgreSQL service container, runs `pytest tests/unit` (with 11 files ignored), runs `npm test` for frontend, uploads coverage to Codecov
- `.github/workflows/main.yml` — 13-step deployment: clone, NIM health check, migrations, demo data, API server, frontend, integration tests
- `.github/workflows/release.yml` — Manual semantic-release (patch/minor/major/prerelease)
- `.github/workflows/codeql.yml` — CodeQL security analysis (Python + JavaScript)
- `.github/workflows/sonarqube.yml` — Fork-safe stub; exits cleanly on non-upstream repos

---

## 17. Known Technical Debt

### Architectural Issues

1. **No ORM — raw SQL everywhere.** All database queries are raw parameterized SQL via `asyncpg`. There is no SQLAlchemy or any query builder. Schema and query logic are distributed across 18 routers and multiple service/retrieval files. Migrations and schema evolution are manual.

2. **Schema duplication between 000-004 scripts and migrations/.** The initial `000_schema.sql` and the migration schema (`migrations/002_warehouse_tables.sql`, `003_timescale_hypertables.sql`) define overlapping but inconsistent entity models. The richer migration schema (`warehouse_locations`, typed `operations`, `inventory_locations` with reserved_quantity) is not reflected in the Pydantic models or routers used by the running API.

3. **No Pydantic Settings / centralized config.** All `os.getenv()` calls are scattered across dozens of files with no single source of truth, type validation, or startup-time validation of required variables. Missing `NVIDIA_API_KEY` is logged as a warning and silently continues.

4. **Two dead planner graphs.** `src/api/graphs/planner_graph.py` (legacy) and `src/api/graphs/mcp_planner_graph.py` (Phase 2) are not called by any router but remain in the codebase. Only `mcp_integrated_planner_graph.py` is active.

5. **Tool authorization not enforced.** `adjust_reorder_point()` docstring states "requires RBAC 'planner' role" but the method performs no role check. The `requires_approval` flag is metadata only — it does not pause execution, require a confirmation step, or gate on any identity context.

6. **Authentication gap.** Only the `/api/v1/auth/` router requires JWT `Depends(get_current_user)`. The chat endpoint (`POST /api/v1/chat`), all equipment/operations/safety/inventory/forecasting/document endpoints, and the MCP endpoints are completely unauthenticated. Any caller with network access can submit queries or retrieve data.

7. **`ToolRoutingService` initialized to `None`.** `src/api/graphs/mcp_integrated_planner_graph.py` creates `self.tool_routing = None` with a comment "skip complex routing for now". The `ToolRoutingService` code exists in `src/api/services/mcp/tool_routing.py` but is never activated.

8. **Document pipeline uses per-request `httpx.AsyncClient` instances.** `LargeLLMJudge` creates a new `httpx.AsyncClient` for every document validation call rather than using the shared `NIMClient` singleton. This bypasses the shared retry logic, caching, and connection pooling.

9. **No distributed tracing.** There is no OpenTelemetry instrumentation. The internal `request_id` UUID is not propagated in HTTP headers to downstream NIM calls, Milvus, or PostgreSQL. Debugging multi-hop request failures requires correlating plain-text log lines by timestamp.

10. **RAPIDS entirely out-of-process.** The GPU forecasting capability is a separate container invoked via `subprocess.Popen` from the training router. There is no feedback loop, no error capture from the subprocess, and no live model serving — the API reads from pre-generated JSON files.

11. **No human-in-the-loop blocking.** LangGraph supports `interrupt_before`/`interrupt_after` for human approval checkpoints. MAIW uses a `requires_approval` metadata flag on some action tools but never implements an actual interrupt. High-impact operations (reorder point changes, task assignments) execute immediately without a confirmation step.

12. **Milvus embedding dimension mismatch.** `milvus_retriever.py` creates the collection with `FLOAT_VECTOR dim=1024` but the embedding model produces 2048-dim vectors (per `EMBEDDING_DIMENSION` env default and `EmbeddingService` configuration). This suggests the Milvus collection may have been created with a stale dimension and the retriever may fail or silently truncate on first use.

13. **11 unit tests excluded from CI.** Over 40% of unit test files (including the planner graph tests and MCP system tests) are `--ignore`d in `ci-cd.yml`. The CI green state does not validate the core orchestration logic.

14. **`LLAMA_70B_TIMEOUT` env var is a legacy name.** `src/api/agents/document/validation/large_llm_judge.py` reads `os.getenv("LLAMA_70B_TIMEOUT", "120")` despite the model being the 49B Nemotron, not a 70B model. The env var name is misleading and may cause operator confusion.

15. **No streaming LLM responses.** `NIMClient.generate_response()` supports a `stream: bool = False` parameter and forwards it in the JSON payload, but no agent ever calls with `stream=True`, no SSE consumer exists, and the chat endpoint returns complete `ChatResponse` objects. The nginx `proxy_buffering off` header is in place but serves no current purpose.
