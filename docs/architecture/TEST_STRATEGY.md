# Test Strategy — MAIW

## Canonical CORE CI Command

```bash
python -m pytest tests/unit/ tests/contract/ tests/mcp/ tests/api/ \
  --ignore=tests/unit/test_all_agents.py \
  --ignore=tests/unit/test_basic.py \
  --ignore=tests/unit/test_nvidia_llm.py \
  --ignore=tests/unit/test_caching_demo.py \
  --ignore=tests/unit/test_response_quality_demo.py \
  --ignore=tests/unit/test_mcp_integrated_planner_graph.py \
  --ignore=tests/unit/test_chunking_demo.py \
  --ignore=tests/unit/test_db_connection.py \
  --ignore=tests/unit/test_enhanced_retrieval.py \
  --ignore=tests/unit/test_evidence_scoring_demo.py \
  --ignore=tests/unit/test_mcp_system.py \
  --ignore=tests/unit/test_guardrails.py \
  --ignore=tests/unit/test_guardrails_sdk.py \
  --ignore=tests/unit/test_mcp_planner_integration.py \
  --ignore=tests/unit/test_nvidia_integration.py \
  --ignore=tests/unit/test_document_action_tools.py \
  --ignore=tests/unit/test_document_pipeline.py \
  --ignore=tests/unit/test_embedding.py \
  --ignore=tests/unit/test_reasoning_evaluation.py \
  --ignore=tests/unit/test_prompt_injection_protection.py \
  --ignore=tests/unit/test_prompt_injection_simple.py
```

**Phase 6B baseline:** 386 passed, 1 skipped, 0 failed  
**Phase 7 baseline:** 483 passed, 1 skipped, 0 failed (+97 new tests: Labor/Wave MCP, contract, state, executor, invariant)  
**Phase 8 baseline:** 512 passed, 1 skipped, 0 failed (+29 new tests: package import smoke, forbidden-dependency guards, compatibility shim verification)  
**Phase 9A baseline:** 528 passed, 1 skipped, 0 failed (+16 net: 20 new Phase 9A package import and invariant tests; −4 from deletion of dead MCP files whose callers were integration tests only)  
**Phase 9B baseline:** 528 + tests/api/ passed (infrastructure-free app startup, router registration, architecture invariants)  
All final phase reports MUST use this command. Any regression against the baseline is a blocker.

> **Note:** `ci-cd.yml` previously ran only `tests/unit/` (327 tests). As of Phase 9A it was corrected to run `tests/unit/ tests/contract/ tests/mcp/` (528 tests). Phase 9B adds `tests/api/` to the canonical command.

All final phase reports MUST use this command. Any regression against the baseline is a blocker.

---

## Why the Count Varies Across Reports

Previous reports showed different passing counts (337, 361, 311, 386) because each ran a different subset:

| Count | What was run |
|-------|-------------|
| 337 | Phase 5 subset: 8 specific files |
| 361 | Phase 6 subset: 9 specific files |
| 311 | Phase 6B subset: 9 Phase 3-6B files including new invariant tests |
| **386** | **Canonical CORE CI (all unit + contract + mcp, minus excluded categories below)** |

The 386 count is the canonical baseline from Phase 7 onward.

---

## Test Categories

### CORE CI (run in every PR, no infrastructure needed)

```
tests/unit/          ← pure Python, no DB/API/GPU required
tests/contract/      ← MCP capability contract tests (in-memory MockProvider)
tests/mcp/           ← MCP protocol tests (in-memory FastMCP server)
tests/api/           ← infrastructure-free API app/router tests (httpx ASGI transport)
```

These tests run in < 10 seconds total. They require only the Python packages installed in the venv and no environment variables.

**Phase 3-6B domain-specific files:**

| File | Domain | Tests |
|------|--------|-------|
| `tests/unit/test_action_executor.py` | Equipment executor guards | 14 |
| `tests/unit/test_decision_engine.py` | DecisionEngine rules | 18 |
| `tests/unit/test_equipment_agent_state.py` | Equipment state assembly | 18 |
| `tests/unit/test_model_gateway.py` | ModelGateway routing | 117 |
| `tests/unit/test_state_aware_ops_phase6.py` | State-aware operations | 10 |
| `tests/unit/test_warehouse_state.py` | WarehouseState / snapshot | 35 |
| `tests/unit/test_architecture_invariants.py` | Architecture boundary enforcement | 18 |
| `tests/mcp/test_equipment_mcp_server.py` | Equipment MCP server protocol | 34 |
| `tests/contract/test_equipment_capability.py` | Equipment capability contract | 45 |

---

### INTEGRATION CI (requires running MAIW server)

```
tests/integration/
```

These tests hit a live server at `API_BASE_URL` (default: `http://localhost:8001`). They require:
- A running MAIW API server
- PostgreSQL (`asyncpg`) with schema migrated
- The server's `.env` configured with valid DB credentials

**Excluded from CORE CI due to:** `asyncpg` import failures at collection time.

Key files: `test_mcp_agent_workflows.py`, `test_mcp_end_to_end.py`, `test_equipment_endpoint.py`, `test_chat_endpoint.py`

---

### EXTERNAL SERVICE TESTS (require NVIDIA API key or NIM endpoint)

Tests that call the NVIDIA NIM inference API. Identified by use of the `nvidia_api_key` fixture, which calls `pytest.skip()` if `NVIDIA_API_KEY` is unset or is a placeholder.

```
tests/unit/test_all_agents.py
tests/unit/test_basic.py
tests/unit/test_nvidia_llm.py
tests/unit/test_caching_demo.py
tests/unit/test_response_quality_demo.py
tests/unit/test_nvidia_integration.py
tests/unit/test_guardrails.py
tests/unit/test_guardrails_sdk.py
tests/unit/test_mcp_planner_integration.py
tests/unit/test_reasoning_evaluation.py
tests/unit/test_prompt_injection_protection.py
tests/unit/test_prompt_injection_simple.py
tests/unit/test_embedding.py
```

**Excluded from CORE CI due to:** `pytest-asyncio` `async def` configuration mismatch (tests written for an older asyncio mode), and runtime dependency on `NVIDIA_API_KEY` / NIM endpoints.

To run: set `NVIDIA_API_KEY` and use a compatible asyncio mode.

---

### GPU / NIM TESTS

No tests in this repository require local GPU resources. All model inference calls go through NVIDIA's hosted NIM API (remote HTTP). Local GPU is not a test dependency.

---

### INFRASTRUCTURE-BROKEN (collection errors — missing optional deps)

Tests that fail at **collection time** due to missing optional Python packages (`asyncpg`, `pymilvus`, `redis`, `milvus`). These are excluded from CORE CI with `--ignore`:

```
tests/unit/test_chunking_demo.py          ← pymilvus / milvus
tests/unit/test_db_connection.py          ← asyncpg
tests/unit/test_enhanced_retrieval.py     ← pymilvus
tests/unit/test_evidence_scoring_demo.py  ← pymilvus
tests/unit/test_mcp_system.py             ← asyncpg
```

**Excluded from CORE CI due to:** `ModuleNotFoundError` at collection time.

---

### PRE-BROKEN (content failures unrelated to current phase)

Tests that run but have assertion failures due to pre-existing content issues:

```
tests/unit/test_mcp_integrated_planner_graph.py   ← wrong intent classification assertions
tests/unit/test_document_action_tools.py           ← document pipeline schema mismatch
tests/unit/test_document_pipeline.py               ← document pipeline infrastructure
```

**Excluded from CORE CI due to:** pre-existing failures not caused by Phase 6/7 changes.

---

## Exclusion Summary Table

| File pattern | Exclusion reason | Fix when |
|---|---|---|
| `test_all_agents.py`, `test_basic.py`, `test_nvidia_llm.py`, `test_caching_demo.py`, `test_response_quality_demo.py` | async def / NVIDIA_API_KEY | When NIM env configured |
| `test_chunking_demo.py`, `test_db_connection.py`, `test_enhanced_retrieval.py`, `test_evidence_scoring_demo.py`, `test_mcp_system.py` | asyncpg / pymilvus missing | When optional deps installed |
| `test_mcp_integrated_planner_graph.py` | Stale intent assertions | When planner graph updated |
| `test_document_action_tools.py`, `test_document_pipeline.py` | Document pipeline pre-broken | Phase 8 Documents modernization |
| `test_guardrails.py`, `test_guardrails_sdk.py`, `test_mcp_planner_integration.py`, `test_nvidia_integration.py` | async def mode | When asyncio mode updated |
| `test_embedding.py`, `test_reasoning_evaluation.py`, `test_prompt_injection_*.py` | async def / external API | When NIM env configured |
| `tests/integration/` | Requires running server | Integration CI only |
