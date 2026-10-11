# MAIW v2.0.1 — Remediation Audit (canonical shipped app)

**Remediates:** independent post-release audit of `v2.0.0` — PR #142
(`audit/v2-independent-post-release` @ `742fd2a0505c63a4835741c66f2e911802202b81`),
`docs/audits/MAIW_V2_INDEPENDENT_POST_RELEASE_AUDIT.md`,
`artifacts/audit/v2_independent_audit.json`. That audit's verdict
(`MAIW V2 INDEPENDENT POST-RELEASE AUDIT FAIL`, 0 P0 / 5 P1 / 10 P2) stands
for `v2.0.0` and is **not** modified by this document.

**Branch:** `fix/v2.0.1-canonical-app-remediation`, started from `nvidia/main`
`944507ec914665c6682d39b95e8713355f486598`.
**Release target:** v2.0.1 release candidate — *not tagged*; requires an
independent re-audit.
**Machine-readable record:** `artifacts/audit/v2.0.1_remediation.json`.

---

## 1. Source identity and v2.0.0 preservation

| Check | Result |
|---|---|
| Start SHA | `944507e` = `nvidia/main` (v2.0.0 + #139/#140/#141, docs-only) |
| `v2.0.0` tag | annotated tag `0c35a0e9…` → commit `816ace73c4561469978094eeedb2641f6db3c4fa` — unchanged (verified with `git ls-remote nvidia`) |
| PR #142 | open, head `742fd2a`; its files are not touched by this branch |
| Canonical entrypoint | `apps/api/maiw_api/app.py` (`uvicorn maiw_api.app:app`) — `Dockerfile.backend`, `scripts/start_reference_deployment.sh` |
| Worktree / env | isolated worktree `/home/nvidia/maiw-v201-remediation`; venv `.venv` with every `maiw_*` package resolving inside the worktree (`maiw_models.__file__`, `maiw_api.__file__` …), `PYTHONNOUSERSITE=1` |

## 2. Release-composition rule

Every release-critical claim below was proven against `maiw_api.app:app`
(imported with its real lifespan in tests; started by
`scripts/start_reference_deployment.sh` live). No result comes from
`src/api/app.py`, which is now documented as a legacy development server.

## 3. Router inventory — canonical app after v2.0.1

143 HTTP routes (excluding HEAD/OPTIONS). Read-only = GET only.

| Router (module) | Canonical / legacy | Read-only routes | Mutating routes | Auth | Governance / classification |
|---|---|---|---|---|---|
| `maiw_api.routers.health` | canonical | 6 | — | none | `/ready` now dependency-based (P1-04) |
| `maiw_api.routers.equipment` | canonical | 6 | assign, release, maintenance | none | **governed**: agent proposal → DecisionEngine → `EquipmentActionExecutor` only if APPROVED |
| `maiw_api.routers.operations` | canonical | 3 | *(task POST/PUT/assign unmounted)* | none | read-only in shipped app |
| `maiw_api.routers.safety` | canonical | 4 | *(incident POST unmounted)* | none | read-only in shipped app |
| `maiw_api.routers.demo` | canonical | 4 | scenario start/pause/resume/reset, tick, inject | none | **simulation** — 503 unless `MAIW_DEMO_MODE` |
| ″ | ″ | | analyze, approve, reject, reconcile | none | **governed** (DecisionEngine → executor; reconcile reads only) |
| `maiw_api.routers.copilot` | canonical | — | `/copilot/turn` | none | **governed** (ACT via GovernedActionOrchestrator; demo only) |
| `maiw_api.routers.{mcp_status,runtime_status,world,model_lab,agent_tasks}` | canonical | 21 | — | none | read-only |
| `maiw_api.routers.procedures` *(new)* | canonical | 2 | — | none | read-only view of the durable store |
| `src.api.routers.inference` | shared impl. | — | `/inference` | internal token, fail-closed | **bounded inference** — ModelGateway only, no governance below it |
| `src.api.routers.auth` | legacy | 6 | register, login, refresh, me, change-password, users/{id} | own (`require_admin` / `get_current_user`) | identity management, not warehouse state |
| `src.api.routers.document` | legacy (curated) | 4 | upload, approve/{id}, reject/{id} | none | **document workflow** — inference via ModelGateway (P1-05); approve/reject record workflow state only; `/search`, `/validate`, `/analytics` (fabricated data) unmounted |
| `src.api.routers.{inventory,wms,iot,erp,scanning,attendance,migration,advanced_forecasting,training}` | legacy | 58 | *(all unmounted)* | none | read-only views (`maiw_api.route_policy.read_only_view`) |
| `src.api.routers.chat` | legacy | — | — | — | **not mounted** (P1-01) |
| `src.api.routers.reasoning` | legacy | — | — | — | **not mounted** (legacy NIM client outside ModelGateway) |

The exact list of 24 mutating routes and their classification is asserted by
`tests/api/test_canonical_shipped_app.py::test_p1_01_mutating_route_inventory_is_exactly_classified`.

## 4. Canonical app authority graph (after v2.0.1)

```
maiw_api.app:app
├── read-only routers ............ health, world, model_lab, agent_tasks, procedures,
│                                  mcp_status, runtime_status, operations*, safety*,
│                                  legacy inventory/wms/iot/erp/scanning/attendance/
│                                  migration/forecasting/training (GET only)
├── bounded inference ............ POST /api/v1/inference → ModelGateway → PolicyFilter
│                                  → ModelRouter → NIMProvider (token, 422 allowlist)
├── governed operational APIs .... /equipment/{assign,release,maintenance},
│                                  /demo/{analyze,approve,reject,reconcile}, /copilot/turn
│                                  → DecisionEngine → ActionExecutor (APPROVED only) → MCP
├── simulation controls .......... /demo/{scenario/*,tick,inject} (503 outside demo mode)
├── identity ..................... /auth/* (own auth dependencies)
├── document workflow ............ /document/upload (→ ModelGateway only),
│                                  /document/{approve,reject} (workflow state)
└── host procedure service ....... runtime.procedure_host (not an HTTP write surface):
                                   SOP Engine + JsonFileProcedureStateStore +
                                   JsonFileGovernanceInbox; holds no executor/credentials
```
No shipped route reaches `ToolDiscoveryService`, the legacy MCP planner, or
`EquipmentAssetTools.assign_equipment` (import-graph test in a fresh
interpreter + behavioural spies; the SQL adapter is used for reads only).

## 5. P1-01 — chat governance

* **Root cause.** `app.py` mounted `src.api.routers.chat` (and other legacy
  routers) wholesale; the chat planner's legacy equipment agent executed
  `assign_equipment` SQL through `ToolDiscoveryService` with no
  DecisionEngine/approval/executor, unauthenticated.
* **Fix (Option A).** `fb406d7`: chat and reasoning unmounted; all other legacy
  routers mounted through `read_only_view` / `curated_view`
  (`apps/api/maiw_api/route_policy.py`); operations/safety writes unmounted.
* **Regression tests.** `test_p1_01_audit_chat_scenario_cannot_mutate`
  (stateful asset adapter + spies on `EquipmentAssetTools.assign_equipment`
  and `ToolDiscoveryService.execute_tool`),
  `test_p1_01_audit_chat_scenario_against_postgres` (real SQL adapter, opt-in
  `MAIW_TEST_PG_DSN`; **run and passed** locally on a disposable Postgres),
  `test_p1_01_mutating_route_inventory_is_exactly_classified`,
  `test_p1_01_legacy_chat_and_reasoning_not_mounted`,
  `test_p1_01_legacy_routers_mounted_read_only`,
  `test_p1_01_import_graph_excludes_legacy_agent_tool_layer`,
  `test_p1_01_legacy_write_routes_not_reachable`,
  `test_p1_01_operational_writes_go_through_decision_engine`,
  `test_p1_01_demo_simulation_routes_inactive_outside_demo_mode`.
* **Live proof (deployed canonical app, disposable Postgres).** FL-01
  `available`, 4 assignment rows before and after: chat ×2 → 404, copilot ×2 →
  200 (ASK, no write), `/reasoning/chat-with-reasoning` → 404,
  `PUT /inventory/items/…` → 405, `POST /operations/tasks` → 405,
  `/equipment/assign` → governed 400 (no MCP state; nothing executed). From
  inside the sandbox: chat 404, inventory write 405, migrate 404.
* **Auth (§6).** No consequential operation is exposed anonymously by a
  write route any more; the remaining unauthenticated routes are reads,
  governed proposals, simulation controls (demo only) and document upload.
* **Status: CLOSED.**

## 6. P1-02 — inference mounting

* **Root cause.** The bounded router was included only by `src/api/app.py`.
* **Fix.** `60c4ad6`: `app.include_router(inference_router)` in the canonical
  app (same `src/api/routers/inference.py`, no second implementation);
  `extra="forbid"`; validation-error serialisation no longer turns 422 into 500.
* **Tests.** `test_p1_02_*` (route mounted; 401 ×3; 503 unconfigured; 422 for 8
  forbidden + 5 unknown fields with zero provider calls; 200 through the
  runtime's real gateway with the registry model id reaching the provider and
  an approved generation; typed 503 on provider failure; IMAGE → no eligible
  approved model, zero provider calls).
* **Live proof.** Smoke 13/13 on the deployed app; from inside fresh sandbox
  `maiw-v201-10071730`: 200 `nvidia/nemotron-3-super-120b-a12b`
  (`nemotron-3`, approved), 401/401, 422 `model_id`, 422 `model`;
  `tests/real_sandbox` **51 passed** with
  `MAIW_QUAL_INFERENCE_ENDPOINT=http://10.185.115.61:18301/api/v1/inference`
  (canonical app — no `:8020` server exists).
* **§9.** No release/reference script starts `src.api.app:app`; preflight no
  longer requires port 8020; `.env.example`, runbook and architecture doc
  point the sandbox at the API port.
* **Status: CLOSED.**

## 7. P1-03 — persistence wiring

* **Root cause.** No composition code constructed the JSON stores or read
  `MAIW_PERSISTENCE_ROOT`.
* **Fix.** `03d34c9`: `maiw_api/persistence.py` (single factory; file-backed
  reference profile; explicit `MAIW_PERSISTENCE_MODE=memory`; failures
  recorded, never silently downgraded); `maiw_api/procedure_host.py`
  (`ProcedureHost` — start/resume/accept_recommendation/apply_governance on the
  durable store and inbox; inbox key fsynced before resume; WAITING procedures
  never re-run on resume); bootstrap wiring; read-only
  `GET /api/v1/procedures`; lifespan resets singletons on shutdown.
  Package boundary respected: the inbox factory lives in the composition root;
  `packages/*` still import nothing from `integrations`.
* **Tests.** `test_p1_03_reference_profile_is_file_backed`,
  `…_memory_profile_requires_explicit_opt_in`,
  `…_persistence_root_is_consumed_by_runtime`,
  `…_restart_preserves_procedure_in_process`,
  `…_governance_replay_after_restart_is_dropped`,
  `…_restart_across_separate_processes` (three interpreters; retry counter
  `establish_state=2` preserved; governance applied once; replay dropped).
* **Live proof.** Proof SOP A (below) persisted at WAITING_FOR_GOVERNANCE
  (rev 22) under the deployment's `MAIW_PERSISTENCE_ROOT`; after
  `restart_reference_deployment.sh` the new API process served it unchanged
  (rev 22, same step/attempts); governance applied → `completed` (rev 28);
  second restart; replay → `duplicate=true`, 0 executor calls, rev 28; ledger
  holds exactly 1 entry.
* **Not in scope / unchanged.** `ApprovalStore` / `CopilotStore` used by the
  demo-mode governed surfaces remain in-memory (the spec scopes P1-03 to the
  ProcedureStateStore and GovernanceInbox); v2.0.1 adds no HTTP route that
  starts or resumes a procedure (no new features) — the ProcedureHost is the
  host-side service.
* **Status: CLOSED.**

## 8. P1-04 — readiness

* **Root cause.** `/ready` checked object presence + MCP circuits only.
* **Fix.** `60632ba`: component readiness (runtime, persistence probe with
  fsynced write/read/delete, model_gateway, governed_write_path, mcp_domains,
  database `SELECT 1` ≤3 s unless demo mode); provider/sandbox reported but
  non-critical; 503 `NOT_READY` + `failed_components`.
* **Tests.** `test_p1_04_*` (healthy READY; procedures dir deleted; governance
  dir deleted; unwritable (chmod 000); unconstructible root; ModelGateway
  construction failure; DB unreachable; provider down stays READY; opt-in
  reachable-DB READY — run and passed locally); GD7–GD10 updated.
* **Live injection (deployed app).**

  | Injection | `/ready` | `/live` |
  |---|---|---|
  | baseline | 200 READY | 200 |
  | `procedures/` chmod 000 | 503 `[persistence]` | 200 |
  | `governance/` chmod 000 | 503 `[persistence]` | — |
  | `procedures/` removed | 503 `[persistence]` | — |
  | restored | 200 READY | — |
  | Postgres container `docker pause` | 503 `[database]` | 200 |
  | unpaused | 200 READY | — |
  | provider URL → closed port (restart) | 200 READY, inference 503 `MODEL_UNAVAILABLE`; after repeated failures `model_provider: degraded, nim_circuit: open` | — |
  | provider restored (restart) | 200 READY, inference 200 | — |
  | own sandbox `openshell sandbox stop` | 200 READY (not an API dependency); smoke 12/13 — sandbox check FAILS | — |
  | ModelGateway unavailable | not injectable on a live process; covered by `test_p1_04_ready_fails_when_model_gateway_unavailable` | |

* **Status: CLOSED.**

## 9. P1-05 — document model path

* **Inventory (§21).** Upload → stage 1 `NeMoRetrieverPreprocessor` (local
  PDF→image; *had* a direct text-only provider call + hard-coded/mock layout),
  stage 2 `NeMoOCRService` (*direct* `meta/llama-3.2-11b-vision-instruct`, mock
  on failure), stage 3 `SmallLLMProcessor` (*direct* Llama vision / text,
  mock on no key/failure), stage 4 `LargeLLMJudge` (*direct* provider, mock
  `APPROVE` on no key, "contains 'approve' → APPROVE" heuristic), stage 5
  `IntelligentRouter` (no model). `DocumentActionTools` returned randomly
  generated invoices with a synthetic `APPROVE` and constructed an unused
  legacy NIM client.
* **Fix.** `6970d36`: `src/api/agents/document/model_gateway_adapter.py` is the
  only model seam (ModelRequest with explicit modality → ModelGateway →
  PolicyFilter; typed `DocumentInferenceUnavailable`: `MODEL_UNAVAILABLE`,
  `PROVIDER_FAILURE`, `DEADLINE_EXCEEDED`, `MALFORMED_RESPONSE`); OCR and image
  extraction request `Modality.IMAGE`; text extraction and judge request
  `Modality.TEXT`; strict judge parsing; all mocks and the random generator
  removed; layout detection reports `not_performed`; failure code surfaced in
  document status; a failed judge routes to human review marked
  `validation_unavailable`. **Approved families were not widened** — vision
  needs an approved multimodal Nemotron (nano-omni role, disabled by default).
* **Decision semantics (§25).** `JudgeEvaluation.decision` is a *model quality
  classification* (`decision_kind="model_quality_classification"`); it is not
  a DecisionEngine outcome and authorises nothing. Document approve/reject is
  a separate human workflow action.
* **Tests.** `test_p1_05_document_judge_uses_canonical_gateway`,
  `…_provider_failure_never_approve`, `…_missing_credential_never_approve`,
  `…_malformed_judge_reply_never_approve` (×3), `…_vision_has_no_eligible_model`,
  `…_upload_end_to_end_fails_typed` (HTTP upload → FAILED `MODEL_UNAVAILABLE`,
  no fabricated results, 0 provider calls), `…_has_no_direct_provider_calls`.
* **Live proof.** Upload to the deployed app → `failed`,
  `ocr_extraction failed: MODEL_UNAVAILABLE … (modality=image)`; results:
  `quality_score null`, `routing null`, `is_mock false`, no fields, no
  `APPROVE`. Injection via the canonical lifespan
  (`scripts/qualification/live_document_failure_injection.py`): real provider →
  classification by `nvidia/nemotron-3-super-120b-a12b` (`nemotron-3`); bad key,
  no key, provider down → typed `MODEL_UNAVAILABLE`; OCR vision →
  `MODEL_UNAVAILABLE`; `synthetic_approve_on_failure: false`.
* **Status: CLOSED.**

## 10. Canonical ModelGateway call-site audit (§27)

Repo-wide production search (`NIMClient(`, `get_nim_client`,
`chat/completions`, `openai`, `ChatNVIDIA`, `.generate(prompt=`), classified by
reachability from `maiw_api.app:app` (import graph after import + lifespan):

| Hit | Reachable from shipped app? | Classification |
|---|---|---|
| `packages/maiw-models/…/nim_client.py`, `maiw_models/__init__.py` | yes | the canonical provider behind ModelGateway |
| `packages/maiw-agents/…/runtime/model_adapter.py` | no (in-sandbox runtime) | comment only; uses `ModelRequest` |
| `src/api/agents/document/*` pipeline | yes (upload) | **now ModelGateway only** (P1-05) |
| `src/api/agents/inventory/equipment_asset_tools.py` | yes (bootstrap, reads) | constructed an unused legacy client — **removed** |
| `src/retrieval/vector/embedding_service.py` | imported by package `__init__`s | no mounted route calls it (no model call on any shipped path) |
| `src/api/services/llm/nim_client.py` and legacy agents (`mcp_*_agent`, `operations/safety/forecasting agents`, `reasoning_engine`, `guardrails_service`, `memory_manager`, `smart_quick_actions`, `evidence_collector`, document `mcp_document_agent`/`document_extraction_agent`/`embedding_indexing`) | **no** (only via unmounted chat/reasoning or the dev server) | legacy dev-server code; not part of the release |

Result: **zero** model calls outside ModelGateway on any route the shipped
app serves.

## 11. Deployment scripts and runbook (§32–§36)

* start: starts only `maiw_api.app:app`, runs from the project root, prints
  failed readiness components on timeout.
* smoke: canonical app only (13 checks incl. inference, auth, 422s, approved
  generation, legacy chat 404, durable persistence, sandbox Ready).
* status: readiness components + `GET /api/v1/procedures` counts.
* stop: no longer kills processes by name pattern (could hit unrelated
  sandboxes / shells on a shared host).
* preflight: disk check on a fresh root fixed; only the API port required.
* runbook / README / DEPLOYMENT_ARCHITECTURE / `.env.example`: one process,
  inference on the API port, accurate readiness & degraded-state semantics.
  README keeps "MAIW v2 supports Nemotron 3 and Nemotron 3.5 model families."

## 12. Canonical live qualification (§44–§49)

Host `epg-tme-smc-h100-02` (NemoClaw 0.0.124, OpenShell 0.0.116). All
resources were created for this run and removed at the end; the user's
deployment and sandbox `maiw-qual-20c-b` were not touched.

* **Deployment.** `preflight` 19/19 → `start_reference_deployment.sh` (port
  18301, persistence under a scratch root, fresh random
  `MAIW_INFERENCE_INTERNAL_TOKEN`, approved Nemotron on the NVIDIA hosted
  endpoint, disposable Postgres `maiw-v201-pg-…` on 127.0.0.1:55441) → READY
  in 4 s. `NEMOTRON_NANO_ENABLED=false` because the hosted endpoint returns
  410 for `nvidia/nemotron-3-nano-30b-a3b` (documented opt-out; approved set
  unchanged). Process: `…/.venv/bin/python -m uvicorn maiw_api.app:app`.
* **Sandbox.** Fresh `maiw-v201-10071730` from
  `ghcr.io/nvidia/openshell-community/sandboxes/base:latest`, policy
  `maiw_inference_only` → `10.185.115.61:18301` only. Deleted at the end.
* **§44 sandbox → canonical inference.** 200 via the sandbox, approved
  `nemotron-3` Super, trace id preserved; direct provider / internet blocked,
  metadata 403, no secret env names, `maiw_execution` not importable.
* **§45 Proof SOP A.** 7 reasoning steps, each a sandbox → canonical
  `/api/v1/inference` call (all HTTP 200, `nvidia/nemotron-3-super-120b-a12b`,
  `approved_family=true`, procedure id propagated) → `WAITING_FOR_GOVERNANCE` at
  `submit`, no write. Harness: `scripts/qualification/live_canonical_proof_sop_a.py`
  (SOP Engine in the ProcedureHost built by `maiw_api.app:app`'s lifespan on the
  deployment's persistence root; the deployed instance served the procedure).
* **§46 write safety.** See §5 (FL-01 unchanged).
* **§47 restart.** See §7 (two restarts, state and governance durable).
* **§48 readiness.** See §8.
* **§49 documents.** See §9.

## 13. Test results

| Suite | Result |
|---|---|
| Python CORE CI command (verbatim `ci-cd.yml`), run 1 | **2720 passed, 0 failed, 5 skipped** (197 s) |
| same, run 2 | **2720 passed, 0 failed, 5 skipped** (188 s) |
| opt-in Postgres tests (`MAIW_TEST_PG_DSN`, disposable DB) | 2 passed |
| `tests/real_sandbox` (live, canonical app) | 51 passed |
| CI-ignored `test_document_action_tools.py` + `test_document_pipeline.py` | 67 passed (updated to v2.0.1 semantics) |
| UI Jest | 963 passed / 39 suites |
| ESLint | 0 errors (1041 warnings) |
| `tsc --noEmit` | 0 errors (was 1) — now a CI step |
| `npm run build` | OK |
| `black --check tests` | clean |

Skips: 3 pre-existing (legacy migration suite, MAIWSkillAdapter, OpenShell
in-CI) + 2 opt-in Postgres tests.

## 14. NPM audit (§40)

`npm audit fix` without `--force` (lockfile only; full UI suite re-run):
**critical 3 → 0, high 62 → 50**, moderate 13 → 34 (reclassification: packages
whose own high advisories were fixed still depend on pre-existing moderate
roots — `postcss-selector-parser`, `sprintf-js`, `uuid`, `qs`, `react-router`;
no new advisory roots), low 5 → 3.

| Package (critical/high) | Before | After | Prod bundle? | Direct? | Fix | Action |
|---|---|---|---|---|---|---|
| proxy-addr, shell-quote, websocket-driver | critical | fixed | no (dev server) | transitive | non-breaking | applied |
| axios | high | fixed (1.20.0) | **yes** (browser client) | direct | non-breaking | applied |
| form-data, ws, nanoid, js-yaml, postcss, browserslist, brace-expansion, compression, fast-uri, source-map-js, @babel/plugin-transform-modules-systemjs | high | fixed | build/dev | transitive | non-breaking | applied |
| jest / @jest/* / babel-jest / jest-* (26) | high | high | no (test runner) | transitive | via react-scripts | accept; breaking |
| @typescript-eslint/*, eslint-config-react-app, eslint-plugin-testing-library, eslint-webpack-plugin | high | high | no (lint) | transitive | via react-scripts | accept |
| webpack-dev-server, http-proxy-middleware, react-dev-utils, chokidar, braces, micromatch, fast-glob, globby, fork-ts-checker-webpack-plugin, tailwindcss | high | high | no (dev server/build) | http-proxy-middleware direct (dev proxy) | breaking | accept |
| svgo, @svgr/*, react-scripts | high | high | no (build) | react-scripts direct | breaking (`react-scripts`) | accept |

**No reachable production critical; no reachable production high** remains
(the only prod-bundle high, axios, is fixed). The remaining highs require
replacing `react-scripts` (breaking) and are recorded as P2.

## 15. Security tools (§41)

| Tool | Status |
|---|---|
| trivy | NOT AVAILABLE locally; runs in GitHub CI "Security Scan" job on the PR (see PR checks) |
| pip-audit | NOT AVAILABLE |
| gitleaks | NOT AVAILABLE |
| regex secret sweep of the branch diff | RUN — 0 secrets (only the CI placeholder DSN); no key material in the worktree |

## 16. Findings after remediation

**P0: 0. P1: 0.**

**P2 (remaining / new):**
1. (orig P2-02, partial) positive `deadline_ms=1` may still return 200 (no pre-expiry check before the provider call).
2. (orig P2-03) no `DeploymentResolver` class / `/api/v1/capabilities/read`; DeploymentMode check is a no-op.
3. (orig P2-04, partial) `DecisionOutcome.DEFERRED` named in some docs (README corrected).
4. (orig P2-06) `PolicyFilter.APPROVED_MODEL_GENERATIONS` reassignable in-process; family check is on the role label, not `model_id` (policy intentionally unchanged).
5. (orig P2-07) rollback baseline `1745a2c` predates the deployment tooling.
6. (orig P2-08, partial) 50 high npm advisories remain, all in the react-scripts build/test/dev toolchain (breaking upgrade).
7. (orig P2-09) package-dependency edges in ARCHITECTURE/PACKAGE_OWNERSHIP vs pyproject.
8. (orig P2-10) two broken doc references (`deploy/brev/`, a DEPLOYMENT.md anchor).
9. (new) `ApprovalStore`/`CopilotStore` for demo-mode governed surfaces remain in-memory.
10. (new) no HTTP route starts/resumes a sandboxed procedure; `/demo/approve` is not linked to `ProcedureHost.apply_governance`.
11. (new) document vision stages are unavailable until an approved multimodal Nemotron model is configured (by design; typed failure).
12. (new) registry default `nvidia/nemotron-3-nano-30b-a3b` returns 410 on the hosted endpoint; operators must set `NEMOTRON_NANO_ENABLED=false`.
13. (new) legacy read routes and `/document/upload` remain unauthenticated (no warehouse mutation; upload consumes inference).
14. (new) `/api/v1/ready` reports persistence directory paths (non-secret).
15. (new, pre-existing) combined `Dockerfile` does not include `apps/api` (the reference image is `Dockerfile.backend`).
16. (new) `src/api/app.py` dev server still mounts the ungoverned legacy chat path (documented as dev-only; never started by release tooling).
17. (orig) UI `DeploymentSecurity` page shows static constants rather than live readiness.

## 17. Five-P1 closure matrix

| P1 | Root cause | Fix (commit) | Regression test | Live proof | Status |
|---|---|---|---|---|---|
| P1-01 | legacy chat (and CRUD) routers mounted wholesale; chat agent wrote SQL without governance | unmount chat/reasoning; legacy + ops/safety read-only; curated document (`fb406d7`) | `test_canonical_shipped_app.py::test_p1_01_audit_chat_scenario_cannot_mutate` (+ `_against_postgres`, inventory, import-graph) | deployed app + disposable PG: FL-01 unchanged; chat 404 (host and sandbox) | **CLOSED** |
| P1-02 | inference router only in legacy app | mount on canonical app; `extra="forbid"`; 422 fix (`60c4ad6`) | `::test_p1_02_valid_inference_reaches_canonical_gateway` (+ auth/422 tests) | sandbox → :18301 200 approved Nemotron 3 Super; smoke 13/13; real_sandbox 51/51 | **CLOSED** |
| P1-03 | stores never constructed; env never read | persistence factory + ProcedureHost + bootstrap wiring (`03d34c9`) | `::test_p1_03_restart_across_separate_processes` (+ file-backed, replay) | Proof SOP A WAITING survives restart; governance once; replay dropped | **CLOSED** |
| P1-04 | readiness checked object presence only | dependency-based readiness (`60632ba`) | `::test_p1_04_ready_fails_when_procedures_dir_deleted` (+ unwritable, DB, gateway) | chmod 000 / removed dir / DB paused → 503; restored → 200 | **CLOSED** |
| P1-05 | direct Llama vision calls + mock APPROVE | ModelGateway adapter, typed failures, mocks removed (`6970d36`) | `::test_p1_05_document_upload_end_to_end_fails_typed` (+ judge/credential/malformed) | upload → FAILED MODEL_UNAVAILABLE; bad/no key/provider down → typed; no APPROVE | **CLOSED** |

## 18. Files changed / commits

See `artifacts/audit/v2.0.1_remediation.json` (`files_changed`, `commits`).

## 19. Independent re-audit readiness

All five P1s are closed against `maiw_api.app:app` with permanent regression
tests in the CORE CI path and live evidence from a fresh sandbox.
Reproduce: §13 commands; live: `scripts/start_reference_deployment.sh`,
`scripts/smoke_test_reference_deployment.sh`,
`scripts/qualification/*.py`, `tests/real_sandbox` with
`MAIW_QUAL_INFERENCE_ENDPOINT` pointing at the canonical app.

```
MAIW V2.0.1 REMEDIATION COMPLETE — READY FOR INDEPENDENT RE-AUDIT
```
