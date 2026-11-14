# Test Strategy — MAIW

## Canonical CORE CI Command

```bash
python -m pytest tests/unit tests/contract tests/mcp tests/api packages/maiw-agents/tests \
  apps/api/tests apps/api/maiw_api/demo/tests tests/demo \
  --timeout=120 \
  --ignore=tests/unit/test_mcp_integrated_planner_graph.py \
  --ignore=tests/unit/test_mcp_system.py \
  --ignore=tests/unit/test_guardrails_sdk.py \
  --ignore=tests/unit/test_guardrails.py \
  --ignore=tests/unit/test_all_agents.py \
  --ignore=tests/unit/test_basic.py \
  --ignore=tests/unit/test_db_connection.py \
  --ignore=tests/unit/test_enhanced_retrieval.py \
  --ignore=tests/unit/test_mcp_planner_integration.py \
  --ignore=tests/unit/test_document_pipeline.py \
  --ignore=tests/unit/test_document_action_tools.py \
  --ignore=tests/unit/test_nvidia_integration.py \
  --ignore=tests/unit/test_nvidia_llm.py \
  --ignore=tests/unit/test_chunking_demo.py \
  --ignore=tests/unit/test_caching_demo.py \
  --ignore=tests/unit/test_response_quality_demo.py \
  --ignore=tests/unit/test_evidence_scoring_demo.py \
  --ignore=tests/unit/test_embedding.py \
  --ignore=tests/unit/test_reasoning_evaluation.py \
  --ignore=tests/unit/test_prompt_injection_protection.py \
  --ignore=tests/unit/test_prompt_injection_simple.py

python -m pytest packages/maiw-world/tests --timeout=120
```

These are the two commands `.github/workflows/ci-cd.yml` runs in the required
`Test & Quality Checks` job: "Run Python tests" (CI also adds
`--cov=src --cov=apps --cov=packages --cov-fail-under=48 --cov-report=xml --cov-report=term-missing`)
and "Run maiw-world package tests". `./scripts/testing/run_core_ci.sh` runs both without
coverage. `--timeout` requires `pytest-timeout`. `tests/api/test_ci_test_scope.py` fails if the
workflow, the script and this block disagree, or if a directory of test files is neither run
nor listed under [Not in CORE CI](#not-in-core-ci-infrastructure-or-a-live-model).

`packages/maiw-world/tests` is a separate invocation because it is a package named `tests`
(it has an `__init__.py` and its modules import `tests.fixtures`). Collected in the same
process as the repository's `tests/` package, all 12 of its files fail to import.

Coverage covers the shipped app (`apps/`) and packages (`packages/`) as well as `src/`;
total line coverage was 49.7% when the 48% floor was set (2026-11-01). CI fails below the
floor. The Codecov upload is informational and does not gate CI.

> **Note:** `ci-cd.yml` previously ran only `tests/unit/` (327 tests). As of Phase 9A it was corrected to run `tests/unit/ tests/contract/ tests/mcp/` (528 tests). Phase 9B adds `tests/api/` to the canonical command. #287 adds `apps/api/tests/` and `apps/api/maiw_api/demo/tests/`, which no command ran: five of their tests had been failing unnoticed. #308 adds `tests/demo/`: four of its tests had been failing since #83 moved the scripted demo scenarios to the DataPack world. `packages/maiw-world/tests` (204 tests: the canonical world model, DataPack generator, validation and CLI) was never run by CI; it passed in full on `18f2d6d` (2026-11-13) and is now its own CI step.

All final phase reports MUST use this command. Any regression against the baseline is a blocker.

---

## Test Categories

### CORE CI (run in every PR, no infrastructure needed)

```
tests/unit/          ← pure Python, no DB/API/GPU required
tests/contract/      ← MCP capability contract tests (in-memory MockProvider)
tests/mcp/           ← MCP SDK protocol tests (FastMCP not importable — tests verify SDK v2 boundary)
tests/api/           ← infrastructure-free API app/router tests (httpx ASGI transport)
packages/maiw-agents/tests/  ← SOP Engine, runtimes, capability policy, proof SOPs
packages/maiw-world/tests/   ← world model, DataPack generator, validation, CLI (own invocation)
apps/api/tests/      ← Copilot (intent, entity resolution, ACT, release gate) and demo world tests
apps/api/maiw_api/demo/tests/  ← demo KPI engine, scenario evidence and provenance
tests/demo/          ← every demo scenario started through the controller, as the API does
```

They need only the Python packages CI installs and no environment variables, network services or GPU. The CI step takes about 17 minutes (4,222 passed and 13 skipped on `18f2d6d`); the maiw-world step about one minute.

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

### UI tests (Jest)

The same CI job runs `npm test -- --watchAll=false` in `src/ui/web` (1,056 tests on `18f2d6d`),
plus `npm run lint` and `npx tsc --noEmit`. **UI coverage is disabled**: `babel-plugin-istanbul`
and `test-exclude` break under the current Jest and Node versions, so no UI coverage is
measured. The 48% floor and the coverage SonarQube reports cover Python (`src/`, `apps/`,
`packages/`) only. Do not quote them as UI coverage. Turning UI coverage back on is a separate
change.

---

### GPU / NIM TESTS

CORE CI requires no GPU and no NIM endpoint. Tests that need live inference or a sandbox host are marked and skip when their dependency is absent:

- `nim_required` — a live NIM endpoint (e.g. `tests/contract/test_phase_20b_real_inference.py` targets a local NIM on `localhost:8002`)
- `real_sandbox` / `sandbox` — a qualified NemoClaw/OpenShell host with an approved Nemotron deployment (`tests/real_sandbox/`)
- `approved_model_required` — an approved Nemotron 3 / 3.5 deployment

Markers are declared in `pyproject.toml` (`[tool.pytest.ini_options]`).

---

### Not in CORE CI (infrastructure or a live model)

These directories hold test files that CORE CI does not collect. They stay out of CORE CI and
are not counted in its results:

| Directory | Needs |
|---|---|
| `tests/integration` | A running MAIW API server and a migrated PostgreSQL (`API_BASE_URL`, default `http://localhost:8001`). Key files: `test_equipment_endpoint.py`, `test_chat_endpoint.py`, `test_reasoning_integration.py`, `test_forecasting_endpoint.py` |
| `tests/quality` | A running API server and a model endpoint |
| `tests/real_sandbox` | A qualified NemoClaw/OpenShell host (`-m real_sandbox`) |
| `scripts/testing` | Nothing to collect: manual smoke and probe scripts (`smoke_e2e.py`, `probe_mcp_servers.py`) |
| `src/adapters/iot/tests`, `src/adapters/wms/tests` | Nothing external (they mock their clients), but 21 of 51 fail on `18f2d6d`; see step 4 below |

The deployment test (`.github/workflows/main.yml`, check `deploy-and-test`) covers the running
stack: health and readiness, MCP tool calls, durability across a backend restart and the
monitoring stack.

---

## Ignored files in `tests/unit`

The CORE command ignores 21 files with `--ignore`. The reasons this page gave before
(collection errors from missing `asyncpg` or `pymilvus`, an old asyncio mode) no longer
hold: CI installs those packages, and 17 of the 21 files now collect. Status measured on
`18f2d6d` (2026-11-13) with the CI install set on Python 3.11, without `NVIDIA_API_KEY` and
without services. The infrastructure-dependent files were collected, not run.

| File | Tests | Result on `18f2d6d` | Needs | Proposed |
|---|---|---|---|---|
| `test_prompt_injection_protection.py` | 16 | 16 pass | nothing | Step 1: restore |
| `test_prompt_injection_simple.py` | 1 | 1 pass | nothing | Step 1: delete (a script-style subset of the file above) |
| `test_document_action_tools.py` | 67 | 67 pass | nothing (mocked) | Step 1: restore |
| `test_guardrails_sdk.py` | 11 | 6 pass, 5 skip | the 5 look for the config in `src/data/config/guardrails`; it is in `data/config/guardrails` | Step 2: restore; fix the path and mark the SDK tests `nim_required` |
| `test_mcp_integrated_planner_graph.py` | 60 | 56 pass, 4 fail | nothing (mocked) | Step 2: the 4 intent-classifier cases expect `operations` or `general` and get `equipment`; decide whether the classifier or the assertions are wrong, then restore |
| `test_evidence_scoring_demo.py` | 3 | 3 pass | nothing | Step 3: low value (`src/retrieval` only); restore or delete |
| `test_mcp_system.py` | — | import error: `src.api.services.mcp.adapters.erp_adapter` no longer exists | — | Step 3: delete |
| `test_chunking_demo.py`, `test_document_pipeline.py`, `test_reasoning_evaluation.py` | 0 | collect nothing (standalone `__main__` scripts) | Milvus, sample documents and NIM; a running API | Step 3: move to `scripts/` or delete |
| `test_db_connection.py` | 1 | not run | PostgreSQL | Infrastructure: move to `tests/integration` |
| `test_enhanced_retrieval.py` | 3 | not run | Milvus and a NIM embedding endpoint | Infrastructure: move to `tests/integration` |
| `test_caching_demo.py` | 4 | not run | Redis | Infrastructure: move to `tests/integration` |
| `test_all_agents.py`, `test_guardrails.py`, `test_nvidia_integration.py` | 5, 2, 2 | not run | the legacy `/api/v1/chat` route, which the release API does not mount | Delete, or rewrite against the release API |
| `test_basic.py`, `test_nvidia_llm.py`, `test_embedding.py`, `test_response_quality_demo.py`, `test_mcp_planner_integration.py` | 9, 3, 1, 4, 1 | not run | `NVIDIA_API_KEY` and a hosted or local model | External: mark `nim_required` and move out of `tests/unit` |

### Restoration sequence

Each step is its own pull request. The CORE CI result before and after is in the description.

1. **Restore what already passes.** Remove the `--ignore` for `test_prompt_injection_protection.py`
   and `test_document_action_tools.py` (83 tests). They cover `sanitize_prompt_input`, which
   the shipped operations agent calls, and `DocumentActionTools`, which the document router
   uses. Delete `test_prompt_injection_simple.py`.
2. **Fix and restore the two nearly green files.** In `test_guardrails_sdk.py`, fix the config
   path and mark the SDK cases `nim_required` so they skip without a model. In
   `test_mcp_integrated_planner_graph.py`, settle the 4 intent-classifier failures.
3. **Remove dead files.** Delete `test_mcp_system.py` (it imports a removed module). Move or
   delete the three `__main__` scripts. Decide on `test_evidence_scoring_demo.py`.
4. **Fix the adapter tests** in `src/adapters/{iot,wms}/tests` (21 failures) and add them to
   CORE CI.
5. **Separate the infrastructure and model tests.** Move them to `tests/integration`, or mark
   them `nim_required`, so `tests/unit` holds only CORE tests and the `--ignore` list goes away.
