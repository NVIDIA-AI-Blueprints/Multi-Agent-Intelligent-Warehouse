# Test Strategy — MAIW

## Canonical CORE CI Command

```bash
python -m pytest tests/unit/ tests/contract/ tests/mcp/ tests/api/ packages/maiw-agents/tests/ \
  --timeout=120 \
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

This is the command `.github/workflows/ci-cd.yml` runs ("Run Python tests"; CI also adds
`--cov=src --cov=apps --cov=packages --cov-fail-under=48 --cov-report=xml --cov-report=term-missing`).
`--timeout` requires `pytest-timeout`.

Coverage covers the shipped app (`apps/`) and packages (`packages/`) as well as `src/`;
total line coverage was 49.7% when the 48% floor was set (2026-11-01). CI fails below the
floor. The Codecov upload is informational and does not gate CI.

> **Note:** `ci-cd.yml` previously ran only `tests/unit/` (327 tests). As of Phase 9A it was corrected to run `tests/unit/ tests/contract/ tests/mcp/` (528 tests). Phase 9B adds `tests/api/` to the canonical command.

All final phase reports MUST use this command. Any regression against the baseline is a blocker.

---

---

## Test Categories

### CORE CI (run in every PR, no infrastructure needed)

```
tests/unit/          ← pure Python, no DB/API/GPU required
tests/contract/      ← MCP capability contract tests (in-memory MockProvider)
tests/mcp/           ← MCP SDK protocol tests (FastMCP not importable — tests verify SDK v2 boundary)
tests/api/           ← infrastructure-free API app/router tests (httpx ASGI transport)
packages/maiw-agents/tests/  ← SOP Engine, runtimes, capability policy, proof SOPs
```

These tests run in < 10 seconds total. They require only the Python packages installed in the venv and no environment variables.

**CORE CI domain test files:**

| File | Domain | Tests |
|------|--------|-------|
| `tests/unit/test_action_executor.py` | Equipment executor guards | 14 |
| `tests/unit/test_decision_engine.py` | DecisionEngine rules | 18 |
| `tests/unit/test_equipment_agent_state.py` | Equipment state assembly | 18 |
| `tests/unit/test_model_gateway.py` | ModelGateway routing | 117 |
| `tests/unit/test_state_aware_ops_phase6.py` | State-aware operations | 10 |
| `tests/unit/test_warehouse_state.py` | WarehouseState / snapshot | 37 |
| `tests/unit/test_architecture_invariants.py` | Architecture boundary enforcement | 28 |
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

Key files: `test_equipment_endpoint.py`, `test_chat_endpoint.py`, `test_reasoning_integration.py`, `test_forecasting_endpoint.py`

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

CORE CI requires no GPU and no NIM endpoint. Tests that need live inference or a sandbox host are marked and skip when their dependency is absent:

- `nim_required` — a live NIM endpoint (e.g. `tests/contract/test_phase_20b_real_inference.py` targets a local NIM on `localhost:8002`)
- `real_sandbox` / `sandbox` — a qualified NemoClaw/OpenShell host with an approved Nemotron deployment (`tests/real_sandbox/`)
- `approved_model_required` — an approved Nemotron 3 / 3.5 deployment

Markers are declared in `pyproject.toml` (`[tool.pytest.ini_options]`).

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

**Excluded from CORE CI due to:** pre-existing failures unrelated to current changes.

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
