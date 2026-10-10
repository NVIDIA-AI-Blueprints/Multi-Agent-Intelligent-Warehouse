# MAIW v2.0.1 Remediation — Round 2

**Scope:** close the four new P1s and two targeted P2s found by the second
independent re-audit (PR #144, `docs/audits/MAIW_V2.0.1_INDEPENDENT_REAUDIT.md`
on branch `audit/v2.0.1-independent-reaudit`, verdict
`MAIW V2.0.1 INDEPENDENT RE-AUDIT FAIL`), on the existing PR #143 branch, and
freeze a candidate for a third independent re-audit.

This document is remediation evidence, not an audit verdict. It does not edit
PR #142 or PR #144, `v2.0.0`, or any earlier audit artifact. Machine-readable
companion: `artifacts/audit/v2.0.1_remediation_round2.json`.

| | |
|---|---|
| Repository | NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse |
| PR / branch | #143 / `fix/v2.0.1-canonical-app-remediation` |
| Starting head (audited by PR #144) | `785c420604c3b6a16d6e7531fcab2c73da43f67a` |
| Last code commit | `9c27c12f63aedbc1059337735ff55e574b11a195` |
| Final frozen head | the commit that adds this file (recorded in the PR and in the final report; the JSON lists every code commit) |
| `main` at start | `944507ec914665c6682d39b95e8713355f486598` |
| `v2.0.0` | `816ace73c4561469978094eeedb2641f6db3c4fa` (unchanged; no `v2.0.1` tag) |
| PR #144 head | `80947b056aa39d545f55afeebc6d38b52be78e81` (unchanged) |
| Host | `epg-tme-smc-h100-02` (shared qualification host) |
| Date | 2026-10-10 |

---

## 1. Executive Summary

All four new P1s and both targeted P2s are fixed in code, covered by
regression tests that run in CORE CI, and reproduced live against the
canonical shipped app `maiw_api.app:app`:

* **NEW-P1-01** — the dispatched physical model ID is now policy-checked. A
  canonical approved-deployment table binds role ↔ physical ID ↔ generation;
  a bounded `DeploymentResolver` between PolicyFilter and provider dispatch
  is the only source of the ID the provider receives. Unapproved bindings are
  rejected with zero provider calls; provider model substitution fails closed
  (502). Preflight, smoke and status use the same registry and resolver.
* **NEW-P1-02** — the runbook now reproduces the deployment from a clean
  shell: one env loader (loaded before preflight), deployment identity with no
  default-port fallback, DB / sandbox+policy / MCP setup steps and scripts,
  and a runbook validator. Nano is disabled by default.
* **NEW-P1-03** — readiness is profile-aware: unconfigured MCP domains are
  `NOT_CONFIGURED`, a required domain that is unconfigured, unreachable or
  circuit-open is 503, governed writes are `not_offered` in the `reference`
  profile, and a required sandbox participates in readiness.
* **NEW-P1-04** — root causes of the order dependence were fixed (event loop,
  `sys.modules` purges, in-place module reloads, unrestored globals). Eleven
  orders, including reversed and two seeded shuffles, give 0 failures.
* **P2-01** — stop only signals its own verified PID; the decoy survives.
* **P2-02** — accepted-but-unapplied governance is recovered exactly once.

One host limitation affected the live run: `nvidia-smi` fails on this host
with *Driver/library version mismatch* (out of scope, §41). Preflight now
reports that honestly (it previously counted the NVML error line as a GPU),
so the literal `start` / `restart` refuse; the live run used the documented
`--skip-preflight` after running preflight separately (26 pass / 1 fail: the
GPU check only).

---

## 2. Source Identity (§0)

Recorded before any change: PR #143 OPEN at `785c420…`; branch clean; `main`
`944507e…`; `v2.0.0` → `816ace7…`; PR #144 OPEN at `80947b0…`; no `v2.0.1`
tag. Gate passed.

## 3. Audit History Preservation (§1)

No file of PR #142 or PR #144 was modified; their branches were not touched.
Round 2 adds only this document, its JSON, the release-notes draft update and
the runbook update.

## 4. Environment (§2)

Worktree `/home/nvidia/maiw-v201-remediation`, venv `.venv` (Python 3.12.3).
With `PYTHONPATH` unset, `maiw_api`, `maiw_models`, `maiw_agents`,
`maiw_world` (and the other six maiw packages) resolve under the worktree.
The clean-shell reproduction used a separate worktree
`/home/nvidia/maiw-v201-r2-live` whose venv was built with the runbook's
install commands verbatim.

---

## 5. NEW-P1-01 — Physical Model Identity

### 5.1 DeploymentResolver / physical binding (§4, §5, §9)

`packages/maiw-models/maiw_models/deployment.py`:

| Role | Approved physical model ID | Generation | Default |
|---|---|---|---|
| lightning | `nvidia/nemotron-3.5-lightning-30b-a3b` | nemotron-3.5 | enabled |
| super | `nvidia/nemotron-3-super-120b-a12b` | nemotron-3 | enabled |
| ultra | `nvidia/nemotron-3-ultra-550b-a55b` | nemotron-3 | disabled |
| nano | `nvidia/nemotron-3-nano-30b-a3b` | nemotron-3 | **disabled** (hosted EOL) |

Inventory checked against `GET https://integrate.api.nvidia.com/v1/models` on
2026-10-09: Super, Lightning and Ultra are listed; the Nano ID is not. No
multimodal model is in the table, so vision fails closed.
`APPROVED_MODEL_GENERATIONS = {nemotron-3, nemotron-3.5}` is defined once and
`PolicyFilter.APPROVED_MODEL_GENERATIONS` refers to it; a table entry with any
other generation is refused at construction. Not widened.

Flow: `ModelRouter` (role) → `PolicyFilter` (now also checks the physical ID
is the approved deployment for the role) → **`DeploymentResolver.resolve`**
(raises `ModelPolicyViolation`) → `NIMProvider.call(model_id=resolved.model_id)`
→ `verify_response_identity` (raises `ModelIdentityMismatch`). The registry
derives `generation` from the physical ID (unknown → `unapproved`); a role
bound to a violating ID is a hard stop in the router, never a silent fallback.
`NIMProvider` refuses an empty ID, so `NIMClient` can never fall back to
`LLM_MODEL`. Packages stay clean (`maiw_models` imports nothing from `apps/`
or `integrations/`).

### 5.2 Model override safety (§6)

| Selector | Runtime consumes it? | Preflight | Smoke | Can change dispatched model? |
|---|---|---|---|---|
| `NEMOTRON_<ROLE>_MODEL` | yes (registry) | yes (same resolver) | yes (configured + served) | only to the approved ID for that role; anything else fails closed |
| `NEMOTRON_<ROLE>_ENABLED` | yes | yes | yes | enables/disables a role; cannot add an ID |
| `LLM_MODEL`, `MAIW_NIM_MODEL` | NIMClient default only; never used by the gateway (explicit ID always passed; empty ID refused) | reported; must name an approved ID if set | — | no (test `test_llm_model_selectors_do_not_change_dispatch`) |
| `MAIW_NIM_BASE_URL` / `LLM_NIM_URL` | provider endpoint | provider `/models` probe | via response identity | a substituting endpoint is caught by the response-identity check |
| `NEMOTRON_NANO_OMNI_MODEL` | registry | yes | — | no approved entry → always fails closed |

### 5.3 Provider response identity (§8)

`LLMResponse.provider_model` holds the model exactly as the provider
reported it. A different ID → `ModelIdentityMismatch` → `502
MODEL_IDENTITY_MISMATCH`, content discarded (also when the substitute is
another approved model). A provider that reports no model: the dispatched ID
is returned with `identity_verified=false` (not relabelled).

### 5.4 Preflight / smoke model validation (§11, §12)

`scripts/lib/check_model_config.py` builds the same `ModelRegistry` from the
same environment and asks the same resolver. Preflight fails on any enabled
role violation; smoke asserts, for a live inference, logical role, resolved
physical model, generation, provider-reported ID and their equality.

### 5.5 Nano default (§13)

Nano is disabled by default; MEDIUM reasoning is served by Super
(`fallback_used=true`). Live: `medium` → super, provider reported the same ID.

### 5.6 Regression matrix (§10) — fake provider, canonical app

`tests/api/test_round2_model_identity.py` (real lifespan, recording fake
OpenAI-compatible provider):

| Case | Config | HTTP | Code | Provider calls |
|---|---|---|---|---|
| A | defaults, `high` / `low` | 200 / 200 | — (identity_verified=true) | 1 / 1 |
| A' | defaults, `medium` (Nano disabled) | 200 | fallback to super | 1 |
| B | `NEMOTRON_SUPER_MODEL=example-org/unapproved-model-x` (high); `NEMOTRON_LIGHTNING_MODEL=…-z` (low); Nano off + Super unapproved (medium) | 503 ×3 | MODEL_POLICY_VIOLATION; `/ready` 503 `model_gateway` | **0** |
| C | Super ← Lightning ID; Lightning ← Super ID; look-alikes `…-v2`, `nvidia/nemotron-3-super`, leading space | 503 ×5 | MODEL_POLICY_VIOLATION | **0** |
| D | provider answers as `example-org/substituted-model-y` (and as the Lightning ID) | 502 | MODEL_IDENTITY_MISMATCH, no content | 1 |
| E | Ultra enabled with `totally-unknown/model-e`, judge task | 503 | MODEL_POLICY_VIOLATION (UNAPPROVED_MODEL_ID) | **0** |

Gateway-level duplicates with a recording provider:
`tests/unit/test_round2_deployment_resolver.py` (21 tests).

### 5.7 Live physical model evidence (§43, §44, §45)

Canonical app started by `start_reference_deployment.sh` from the clean-shell
worktree at `9c27c12`, hosted provider `integrate.api.nvidia.com`:

| Request | Logical role | Resolved physical model | Generation | Provider-reported model | Match | Approved |
|---|---|---|---|---|---|---|
| host `high` | super | `nvidia/nemotron-3-super-120b-a12b` | nemotron-3 | `nvidia/nemotron-3-super-120b-a12b` | yes | yes |
| host `low` | lightning | `nvidia/nemotron-3.5-lightning-30b-a3b` | nemotron-3.5 | `nvidia/nemotron-3.5-lightning-30b-a3b` | yes | yes |
| host `medium` | super (fallback) | `nvidia/nemotron-3-super-120b-a12b` | nemotron-3 | same (NIMClient cache hit) | yes | yes |
| smoke (×2, before/after restart) | super | `nvidia/nemotron-3-super-120b-a12b` | nemotron-3 | same | yes | yes |
| **in-sandbox** `maiw-v201-r2-a` → `/api/v1/inference` | super | `nvidia/nemotron-3-super-120b-a12b` | nemotron-3 | same | yes | yes |

Live failure injection (same app, overrides via the shell):
`NEMOTRON_SUPER_MODEL=example-org/unapproved-model-x` → `/ready` 503
(`model_gateway.binding_violations`), inference 503 MODEL_POLICY_VIOLATION;
local fake provider answering as `example-org/substituted-model-y` → 502
MODEL_IDENTITY_MISMATCH (the fake recorded exactly one request, for
`nvidia/nemotron-3-super-120b-a12b`).

In-sandbox probe also showed: no/wrong token 401, `model_id`/`model` 422,
legacy chat 404, inventory write 405, direct provider and internet BLOCKED,
metadata 403, no secret-named env vars, `maiw_execution` not importable.

---

## 6. NEW-P1-02 — Runbook Reproducibility

### 6.1 Environment loading (§15, §16)

`scripts/lib/load_env.sh` is sourced by preflight, start, stop, restart,
status, smoke, qualify and both setup scripts (test
`test_every_lifecycle_script_uses_the_shared_loader`). It parses `KEY=VALUE`
without executing (the `.env.example` placeholder `<HOST_IP>` used to be a
shell redirection), lets shell exports win for one run, honours
`MAIW_ENV_FILE`, and exports `PYTHON_DOTENV_DISABLED=1`. Start loads env
**before** preflight; restart preflights **before** stopping, so a
configuration that cannot start never takes the running instance down.

### 6.2 Deployment identity / localhost fallback / stop safety (§17–§19, §47)

`scripts/lib/deployment_identity.sh`: start writes
`runtime/maiw-api.instance` and launches uvicorn with a random
`MAIW_INSTANCE_ID`, which `/api/v1/live` returns. Before acting, scripts
verify the PID is alive, its `/proc` cmdline is `uvicorn maiw_api.app:app
--port <port>`, its cwd is this checkout, its environment carries the
instance ID and (except stop) that `/api/v1/live` on the port returns the
same ID. No default port exists in any lifecycle script; `MAIW_API_PORT`,
`MAIW_PERSISTENCE_ROOT`, `MAIW_PYTHON` are required.

Live decoy (own `python -m http.server` on 127.0.0.1:18942): smoke exit 2,
status exit 1, restart exit 2, stop exit 0 "NOT RUNNING / CANNOT VERIFY";
with a forged instance file pointing at the decoy PID: stop exit 3, smoke
exit 2. Decoy alive afterwards; **0 requests** reached it. Same cases in CI
(`tests/unit/test_round2_deployment_scripts.py`).

### 6.3 Database, sandbox, MCP (§20–§22)

* `scripts/setup/reference_db.sh up|status|down` — labelled TimescaleDB
  container on `127.0.0.1:$PGPORT`, schema from `data/postgres/*.sql`,
  `SELECT 1` + schema check; refuses foreign containers and busy ports.
* `scripts/setup/reference_sandbox.sh create|status|probe|delete` — renders
  `deploy/openshell/maiw-inference-only.policy.yaml.tmpl` (egress only to the
  API host:port), creates the named sandbox with no provider attached,
  deletes only a sandbox it created (marker file).
* MCP: `MAIW_MCP_SERVER_{EQUIPMENT,LABOR,WAVE,INVENTORY}_URL` and
  `MAIW_REQUIRED_MCP_DOMAINS` documented; required in `reference_governed`.

### 6.4 Profiles (§23)

`reference` (no governed writes), `reference_governed`, `demo` —
`apps/api/maiw_api/profile.py`, used by readiness and preflight.

### 6.5 Clean-host reproduction (§24)

Every command (from `env -i`, checkout root, worktree at `35e224e` then
`9c27c12`):

| # | Command | Exit |
|---|---|---|
| 1 | runbook install block (venv + pip, verbatim) | 0 |
| 2 | `cp .env.example .env` + fill required values (scripted operator edit; no variable outside `.env.example` was needed) | 0 |
| 3 | `bash scripts/validate_reference_runbook.sh` | 0 |
| 4 | `bash scripts/setup/reference_db.sh up` | 0 |
| 5 | `bash scripts/setup/reference_sandbox.sh create` (`maiw-v201-r2-a`) | 0 |
| 6 | `bash scripts/preflight_reference_deployment.sh` | 1 — 26 pass / **1 fail: GPU (host NVML mismatch)** |
| 7 | `bash scripts/start_reference_deployment.sh` | 1 — refused by the same preflight |
| 8 | `bash scripts/start_reference_deployment.sh --skip-preflight` | 0 (READY in ~4 s) |
| 9 | `bash scripts/status_reference_deployment.sh` | 0 |
| 10 | `bash scripts/smoke_test_reference_deployment.sh` | 0 — 14/14 |
| 11 | `bash scripts/setup/reference_sandbox.sh probe` | 0 |
| 12 | `bash scripts/restart_reference_deployment.sh` | 1 — refused before stopping (GPU only; port held by own instance PASS); instance untouched |
| 13 | `bash scripts/restart_reference_deployment.sh --skip-preflight` | 0 |
| 14–15 | status / smoke after restart | 0 / 0 (14/14) |
| 16 | `bash scripts/stop_reference_deployment.sh` | 0 |
| 17 | status after stop | 1 — NOT RUNNING / CANNOT VERIFY |
| 18 | `reference_sandbox.sh delete`; `reference_db.sh down` | 0 / 0 |

The first pass (at `35e224e`) found one real defect: restart's preflight
failed on the port held by the instance being restarted. Fixed in `9c27c12`
and re-run (table above). **Unaided?** Every step came from the runbook and
`.env.example`; the only deviation was `--skip-preflight`, required solely by
the host GPU driver mismatch.

---

## 7. NEW-P1-03 — Readiness

### 7.1 MCP readiness semantics (§26–§28)

Per domain: `required`, `configured`, `reachable` (bounded TCP probe for URL
transports), `circuit`, `state ∈ {READY, DEGRADED, CIRCUIT_OPEN, FAILED,
NOT_CONFIGURED}`. Required domain not READY/DEGRADED → `mcp_domains` and
`governed_write_path` failed → 503. `/runtime/status` also reports
`NOT_CONFIGURED` (UI type + ReliabilityPanel updated, Jest test).

### 7.2 Sandbox readiness (§29) and liveness (§31)

`MAIW_SANDBOX_MODE=required` → `sandbox_runtime` critical: the named sandbox
must be `Ready` (OpenShell CLI, read-only, 5 s bound). Otherwise
`not_configured` / `degraded`, non-critical. `/api/v1/live` never depends on
readiness components (asserted in every readiness test).

### 7.3 Readiness matrix (§30, §46)

| Condition | Expected | Test (`tests/api/test_round2_readiness.py` unless noted) | Live |
|---|---|---|---|
| all required healthy (reference) | 200 | `test_reference_profile_optional_mcp_unconfigured_is_ready` | 200 READY |
| all required healthy (reference_governed) | 200 | `test_governed_all_required_healthy_is_ready` | — |
| required persistence unavailable | 503 | `test_required_persistence_unavailable_is_not_ready` | — |
| required DB unavailable | 503 | `test_required_db_unavailable_is_not_ready`, `test_database_url_must_match_data_path` | — |
| required MCP unconfigured | 503 | `test_governed_required_mcp_unconfigured_is_not_ready` | 503 (`reference_governed`) |
| required MCP circuit-open | 503 | `test_governed_required_mcp_circuit_open_is_not_ready`; reliability `test_ready_returns_503_when_required_domain_open` | — |
| required MCP unreachable | 503 | `test_governed_required_mcp_unreachable_is_not_ready` | 503 (FAILED) |
| optional MCP unconfigured | 200 + NOT_CONFIGURED | `test_reference_profile_optional_mcp_unconfigured_is_ready` | 200, all NOT_CONFIGURED |
| optional MCP circuit-open | 200 | reliability `test_ready_returns_200_when_one_domain_open` | — |
| required sandbox unavailable | 503 | `test_required_sandbox_unavailable_is_not_ready`, `…_not_named_…` | 503 (`maiw-v201-r2-none`) |
| optional sandbox unavailable | 200 + degraded / not_configured | `test_optional_sandbox_*` | — |
| provider unavailable | 200, non-critical (all profiles) | `test_provider_unavailable_is_non_critical[reference, reference_governed]` | — |
| unapproved model binding | 503 | `test_unapproved_model_binding_is_not_ready` | 503 |

---

## 8. NEW-P1-04 — Test Order

### 8.1 Root causes and fixes

| Class | Root cause | Fix |
|---|---|---|
| 40 failures (ModelGateway-first, reliability-first) | demo tests called `asyncio.get_event_loop().run_until_complete()`, which on 3.12 fails after any earlier `asyncio.run()` | `asyncio.run()` (`tests/unit/demo/*`) |
| 158 failures + 6 errors (reversed) | `tests/contract/conftest.py` purged `maiw_*` from `sys.modules` during collection → two `SOPStep` identities; similar purges in `test_model_lab_api.py`, `test_checkpoint_d.py` | purges removed |
| latent | `test_app_startup.py` / `test_equipment_router.py` reloaded `maiw_api.app` in place, leaving mocked rate limiter/metrics for the later canonical suite | namespace saved/restored |
| latent | `test_model_gateway.py` replaced `asyncpg.create_pool` / `redis.asyncio` for the session | `monkeypatch` |
| latent | `MAIW_AGENT_RUNTIME` popped without restore | `monkeypatch` |
| latent | stray `.env` loaded by `load_dotenv()` | `PYTHON_DOTENV_DISABLED=1` in `tests/conftest.py` and `packages/maiw-agents/tests/conftest.py`; deployment scripts export it too |

### 8.2 Global state inventory and reset contract (§33, §34)

`tests/conftest.py::_isolate_process_singletons` (autouse) saves and restores,
per test, `os.environ`, the agent-task registry contents and these
process-globals; production code was not changed for resets.

| Global | Owner | Reset mechanism | Risk |
|---|---|---|---|
| `_gateway_instance` | `maiw_models/__init__.py` | `reset_model_gateway()` + fixture | High |
| `_nim_client` | `maiw_models/providers/nim_client.py` | `close_nim_client()` + fixture | Medium |
| `NIMConfig` defaults (import-time env) | `nim_client.py` | none; tests pass explicit config | Medium (production behaviour) |
| `_runtime` | `maiw_api/bootstrap.py` | `reset_runtime()` (also lifespan shutdown) + fixture | Medium |
| `_DEMO_MODE` (import-time env) | `bootstrap.py` | tests patch the attribute | Low |
| demo `_controller` | `maiw_api/demo/controller.py` | `reset_demo_controller()` + fixture | Low |
| MCP server `_provider` ×4 | `mcp_servers/*/server.py` | fixture | Medium |
| router `_sql` / `_task_queries` | `routers/equipment.py`, `operations.py`, `safety.py` | fixture | Medium |
| `SQLRetriever._instance`, `_sql_retriever` | `src/retrieval/structured/sql_retriever.py` | `close_sql_retriever()` + fixture | Medium |
| `_rate_limiter` | `src/api/services/security/rate_limiter.py` | fixture | Medium |
| src lazy singletons (`_nim_client`, `_config_loader`, `_equipment_asset_tools`, `_forecasting_action_tools`) | `src/api/...` | fixture | Low–medium |
| `_TASK_REGISTRY` | `routers/agent_tasks.py` | contents saved/restored | Low |
| `_PREDICATES` | `maiw_agents/sop_engine/validators.py` | `unregister_predicate()`; no leak observed | Low |
| `default_resolver()` cache | `maiw_models/deployment.py` (new) | immutable table; no reset needed | None |
| `load_dotenv()` call sites | `lifespan.py`, `nim_client.py`, `sql_retriever.py`, … | `PYTHON_DOTENV_DISABLED=1` | Medium |
| stubbed asyncpg/redis/pymilvus/bcrypt | `tests/api/conftest.py` | session-wide by design (order-independent) | Low |

### 8.3 Order matrix (§35, §36) — committed candidate

Fresh process each, CI flags and ignores, `MAIW_PHASE20B_NIM_URL` pointed at a
closed port (see §13). `pytest-randomly` is not installed; seeded file
shuffles were used.

| Order | Result |
|---|---|
| CI order (run 1 / run 2) | 2805 passed, 8 skipped, 0 failed / same |
| `test_model_gateway.py` → `tests/unit/demo` | 191 passed |
| `tests/unit/demo` → `test_model_gateway.py` | 191 passed |
| canonical app → reliability | 442 passed, 2 skipped |
| reliability → canonical app | 442 passed, 2 skipped |
| ModelGateway first (full) | 2805 / 8 / 0 |
| demo first (full) | 2805 / 8 / 0 |
| canonical first (full) | 2805 / 8 / 0 |
| reliability first (full) | 2805 / 8 / 0 |
| reversed directories | 2805 / 8 / 0 |
| shuffled files, seed 20261010 | 2805 / 7 / 0 |
| shuffled files, seed 4242 | 2805 / 7 / 0 |

The shuffled runs list test files explicitly; the module-skipped
`tests/unit/test_migration_system.py` has no collected tests so it is not in
the list (7 skips instead of 8). Before the fix the auditor measured 40 / 40 /
158+6 failures for ModelGateway-first / reliability-first / reversed.

### 8.4 Full test repeatability (§37)

See §11 (two fresh full runs on the last code commit).

---

## 9. Governance Crash Recovery (§38, §39) — P2-02

Inbox entries now carry the accepted payload and an `applied` marker;
`ProcedureHost.recover_accepted_governance(inputs_for)` replays only
accepted-but-unapplied outcomes. Startup logs them; readiness reports
`persistence.unapplied_governance`.

| Case | Result (`tests/api/test_round2_governance_recovery.py`, separate app lifecycles over the same root) |
|---|---|
| A crash before accept | nothing applied; recovery no-op; later delivery applied once |
| B crash after accept, before resume | restart reports 1 unapplied; recovery resumes exactly once; second recovery no-op; redelivery dropped; ledger `accepted, applied` |
| C crash after resume, before marker | recovery marks applied without running the engine; revision unchanged |
| D duplicate delivery | dropped; revision unchanged |

The replay is validation-only (`SOPEngine.resume_after_governance` with no
executor), so a replay cannot repeat a write.

---

## 10. Canonical Shipped App (§42)

Every live and in-process test targets `maiw_api.app:app`; `src.api.app` is
not started anywhere.

## 11. Python Tests (§54)

Full CORE CI command (verbatim `ci-cd.yml` selection), last code commit
`9c27c12`, two fresh runs: see the JSON (`python_tests.full_runs`) —
**2805 passed, 8 skipped, 0 failed** each. New round-2 tests: 87
(`test_round2_model_identity` 17, `test_round2_deployment_resolver` 21,
`test_round2_readiness` 20, `test_round2_governance_recovery` 6,
`test_round2_deployment_scripts` 23). `black --check tests`: clean.

## 12. UI, TypeScript, npm (§55, §56)

Jest **964/964** (39 suites; +1 NOT_CONFIGURED test), ESLint **0 errors**
(1041 warnings), `tsc --noEmit` **0 errors**, `npm run build` OK.
`npm audit`: 0 critical, **50 high**, 34 moderate, 3 low; `--omit=dev`
identical (react-scripts/typescript/testing-library sit in `dependencies`).
All highs are the react-scripts build/test/dev-server toolchain, as in the
re-audit; no production-reachable high. `npm audit fix --force` not used.

## 13. Host-state limitations and incidents

* `nvidia-smi`: *Failed to initialize NVML: Driver/library version mismatch*.
  Not touched. Effect: preflight GPU check FAILs (correctly), so literal
  start/restart refuse; live run used `--skip-preflight`. Hosted inference was
  unaffected.
* `tests/contract/test_phase_20b_real_inference.py` used to probe
  `localhost:8002` by default and, when it answered, run 3 real-inference
  tests against it. On this host :8002 is a pre-existing NIM not owned by
  this work. During round 2, three early order-investigation runs (before a
  guard was added) contacted it (4 connections: 1 probe + 3 inference
  requests from the then-unmodified test), and one of my contract runs sent
  its `GET /models` probe (its inference tests were already rejected before
  dispatch by the new policy). The test is now opt-in (no default URL) and
  can only dispatch the approved Super model; all later runs show 0
  connections to :8002.
* No request was sent to :8001/:8000/:8020 or :5435. Only resources created
  by this work were stopped or deleted: sandbox `maiw-v201-r2-a` (and short-lived
  `maiw-v201-r2-t1`, `maiw-v201-r2-dry`), containers `maiw-v201-r2-pg-dry`,
  `maiw-v201-r2-pg-a`, own uvicorn instances, own fake provider and decoys.
  `maiw-qual-20c-b` and all user services untouched. No `.env` left in any
  checkout; `MAIW_INFERENCE_ALLOW_UNAUTHENTICATED` never set.

## 14. Findings

* **P0:** none found.
* **P1:** none open to my knowledge (four new P1s closed; original five
  unchanged — round-1 tests still pass).
* **P2 remaining (from PR #144, not in round-2 scope):** P2-03 ExecutionRegistry
  idempotency unused by canonical callers; P2-04 unauthenticated document
  upload / chunked size bypass / rate limiter fails open; P2-05 governed
  equipment POSTs unauthenticated (governed writes now `not_offered` in the
  `reference` profile, routes still mounted); P2-06 unauthenticated legacy
  GETs; P2-08 vision cache-key crash (moot: no approved multimodal model);
  P2-09 document approve/reject stubs, analytics; P2-10 no HTTP procedure
  start/resume (recovery API has no production caller either); P2-11
  `.env.example` sandbox wording (readiness now enforces the sandbox when
  required); P2-14 root Dockerfile; P2-15 npm toolchain highs; P2-16 dev JWT
  fallback; P2-17 release-notes limitations (partly addressed); P2-18 v2.0.0
  release body; P2-20 plain-HTTP base URL warning only. **Fixed in passing:**
  P2-07 (smoke default port), P2-12 (NVML false PASS; multi-level missing
  root), P2-13 (start no longer pip-installs), P2-19 (readiness DB variables).
* New observations: the NIMClient response cache (default on) can serve a
  repeated prompt across reasoning levels (the live `medium` call was a cache
  hit of the `high` call; identity was still verified); `src/api/app.py` and
  other legacy modules still call `load_dotenv()` (neutralised by
  `PYTHON_DOTENV_DISABLED` in scripts and tests).

## 15. Closure matrices

### Four new P1s

| New P1 | Root cause | Fix | Regression test | Live / fake proof | Status |
|---|---|---|---|---|---|
| NEW-P1-01 | generation label per role; env-bound physical ID unchecked; response model not enforced; preflight/smoke checked `LLM_MODEL` | approved-deployment table + DeploymentResolver before dispatch; response identity check; shared config checker; Nano off | `test_round2_model_identity`, `test_round2_deployment_resolver`, updated routing tests | fake matrix A–E (0 provider calls on rejection); live super/lightning/sandbox identity match; live 503/502 injection | CLOSED |
| NEW-P1-02 | `.env` loaded only by start, after preflight; default port fallback; no DB/sandbox/policy/MCP steps; dead Nano default | one loader; deployment identity; setup scripts + policy template; runbook clean-host procedure + validator | `test_round2_deployment_scripts` (incl. full lifecycle) | clean-shell reproduction §6.5 | CLOSED (host GPU caveat) |
| NEW-P1-03 | unconfigured MCP = HEALTHY; only "all configured open" failed; no profile | profiles; per-domain states; required-domain/governed-write/sandbox rules; data-path DB probe | `test_round2_readiness`, reliability updates | live 200 / 503 rows §7.3 | CLOSED |
| NEW-P1-04 | event loop misuse; `sys.modules` purges; module reloads; unrestored globals; `.env` | test fixes + reset fixture + `PYTHON_DOTENV_DISABLED` | the suite itself under 11 orders | order matrix §8.3 | CLOSED |

### Targeted P2s

| P2 | Root cause | Fix | Test | Live | Status |
|---|---|---|---|---|---|
| P2-01 stop kills arbitrary listener | no-pidfile kill-by-port; qualify pattern kill | verified-PID-only stop; no kill-by-port/name | decoy tests (no state, forged, stale) | decoy alive, 0 requests | CLOSED |
| P2-02 accepted-but-unapplied governance | only the key was persisted; no applied marker | payload + applied marker + `recover_accepted_governance` | crash matrix A–D | — (in-process across app lifecycles) | CLOSED |

## 16. Artifacts

* this document; `artifacts/audit/v2.0.1_remediation_round2.json`
* `RELEASE_NOTES_v2.0.1.md` (draft; no PASS claim), runbook
  `docs/operations/REFERENCE_DEPLOYMENT_RUNBOOK.md`
* host-only logs (not committed): the session scratchpad
  (`live_a_logs`, `live_b_logs`, `live_c_logs`, `logs/r2_*.log`,
  `order_matrix.txt`).

## 17. Third Re-Audit Readiness

Ready for a third independent re-audit once CI is green on the frozen head
and there are no unresolved review threads (recorded in the final report).
Not merged, not tagged.
