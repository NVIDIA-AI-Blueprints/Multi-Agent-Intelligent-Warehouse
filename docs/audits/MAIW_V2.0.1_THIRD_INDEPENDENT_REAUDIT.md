# MAIW v2.0.1 Third Independent Re-Audit — frozen PR #143 candidate `86f3004`

**Verdict: `MAIW V2.0.1 THIRD INDEPENDENT RE-AUDIT FAIL`**

| | |
|---|---|
| Repository | NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse |
| Candidate | PR #143, `fix/v2.0.1-canonical-app-remediation` → `main` |
| Candidate head SHA | `86f30040c72f44ee64d52edf135ce61f72851bc2` (start 2026-10-10T15:5xZ, mid 2026-10-10T23:34Z, end 2026-10-11T01:46Z: unchanged) |
| Base SHA (`main`) | `944507ec914665c6682d39b95e8713355f486598` |
| Host | `epg-tme-smc-h100-02` (shared qualification host) |
| Audit window | 2026-10-10 → 2026-10-11 (UTC) |
| Machine-readable companion | `artifacts/audit/v2.0.1_third_independent_reaudit.json` |
| Stance | Independent. Remediation reports, CI status and earlier live proofs were treated as claims. No product code was modified. |

---

## 1. Executive Summary

The release-critical round-2 claims reproduce on the exact frozen SHA:

* All **nine** P1s (five original, four from PR #144) are closed for the scope in which they were raised.
* The **full preflight passed with no skip** (29/29).
* The **clean-shell runbook** sequence passed end to end: install → `.env` → DB → sandbox → preflight → start → status → smoke 14/14 → in-sandbox probe → restart → status → smoke 14/14 → stop → teardown.
* **Physical model identity holds.** In the fake-provider matrix (15 configurations, 24 requests), no unapproved, look-alike, cross-role or unknown model ID ever reached the provider. Provider substitution returns `502 MODEL_IDENTITY_MISMATCH`.
* **Live identity from a fresh sandbox:**
  * Super: resolved `nvidia/nemotron-3-super-120b-a12b`; the provider reported the same ID.
  * Lightning: resolved `nvidia/nemotron-3.5-lightning-30b-a3b`; the provider reported the same ID.
* **Readiness** is correct in 20 of 20 rows.
* **Tests are order-independent:** 2 full runs plus 9 alternative orders and shuffles all passed, 0 failures.
* **Governance crash recovery** behaves exactly once (cases A–D).
* **Network isolation:** no pre-existing host service was contacted. The contamination guard recorded zero connections.

The candidate still **fails**, because this audit found **two new P1s** in the governed-write path. Round 2 now presents that path as a supported, READY profile (`reference_governed`).

1. **NEW3-P1-01 — unauthenticated governed writes are reachable from the sandbox (§45/§48).**
   * Setup: `reference_governed` was READY with `governed_write_path: ready`. Audit-owned recording MCP servers ran the repo's own MCP server modules with mock backends.
   * The fresh sandbox sent `POST /api/v1/equipment/release` with **no credential at all** (not even the internal token).
   * The DecisionEngine auto-approved the LOW-risk release, and the `warehouse.equipment.release` MCP write tool was **executed** (`executed: true`, write recorded).
   * The same write executed in the **default `reference` profile** when the documented-optional `MAIW_MCP_SERVER_EQUIPMENT_URL` was set, while `/api/v1/ready` reported `governed_write_path: not_offered`.
   * Root causes:
     * the sandbox policy grants `access: full` to the whole API port;
     * the governed write routes have no caller authentication;
     * executors are wired whenever an MCP URL is set, whatever the profile.
2. **NEW3-P1-02 — an ambiguous write on the real MCP transport is reported as FAILED and can be duplicated (§49/§50).**
   * Setup: `reference_governed` with a real streamable-HTTP MCP equipment server.
   * A release write that **landed** before the server crashed (no response) was reported as `status: failed, executed: false`. The record says `physical_mutation_occurred=False`, not UNKNOWN.
   * `/api/v1/demo/reconcile` is unusable outside demo mode (503).
   * An operator retry of the "failed" release executed a **second** consequential write. The write log shows 2 writes; `execution_id` was `null` at the backend.

There is no P0. Remaining P2s are listed in §59.

## 2. Host Qualification State (§1)

| Check | Result |
|---|---|
| `nvidia-smi` | exit 0; **4 × NVIDIA H100 NVL** |
| Loaded module (`/proc/driver/nvidia/version`) | **580.178.04** |
| Installed module (`modinfo nvidia`) | **580.178.04** (match) |
| Kernel | 6.8.0-146-generic |
| GPU processes at start | one pre-existing `llama-server` (container `nemoclaw-llama-cpp`, 23.9 GiB on GPU 0), not audit-owned |

Healthy. The preflight's GPU check passed by exit status, against the same driver.

## 3. Candidate Identity (§4)

* `gh pr view 143`: OPEN, head `86f30040c72f44ee64d52edf135ce61f72851bc2`, base `main` @ `944507e`.
  * 22 commits, 98 changed files.
  * Mergeable: `MERGEABLE` / `CLEAN`.
  * 0 unresolved review threads (GraphQL).
* CI on the head: Test & Quality (3.11, 22), CodeQL ×2, Security Scan and Trivy pass; Semantic Release skipped. Recorded as a claim.
* The SHA was rechecked mid-audit (2026-10-10T23:34Z) and at the end (2026-10-11T01:46Z). It was unchanged both times.

## 4. Clean-Room Environment (§5, §7)

* Fresh clone `/home/nvidia/maiw-v201-third-reaudit` from `git@github.com:NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse.git`.
  * `git checkout --detach 86f3004…`; `git status` clean.
  * Audit folders (`.third-*`) were excluded through `.git/info/exclude` only.
* None of the following was read, run or reused:
  * `/home/nvidia/Multi-Agent-Intelligent-Warehouse`;
  * `maiw-v201-remediation`, `maiw-v2-audit`, `maiw-v201-reaudit*`, `maiw-v201-r2-*`;
  * any earlier sandbox.
* **`.env` handling:**
  * There was no stray `.env` (`find . -maxdepth 2 -name .env` was empty before the tests).
  * The runbook's `.env` was created in the clone root for the clean-shell sequence (runbook step 2).
  * It was then moved out of the root to `.third-state/runbook.env` and used through the documented `MAIW_ENV_FILE`.
  * `run_pytest.sh` refuses to run when `.env` exists. The file was deleted at the end.
* `MAIW_INFERENCE_ALLOW_UNAUTHENTICATED` was never set.

## 5. Package Provenance (§6)

* The venv `.venv` was built in the clone with `/usr/bin/python3` 3.12.3, from an `env -i` shell, using the runbook's install block verbatim. The host has no Python 3.11; CI uses 3.11.
* CI test tools were then added (`pytest pytest-cov pytest-asyncio pytest-timeout black httpx`). `pip install --upgrade pip` was the only extra step.
* All 10 packages resolve into the fresh checkout:
  * `maiw_api` → `apps/api/maiw_api/__init__.py`;
  * `maiw_models`, `maiw_agents`, `maiw_world`, `maiw_decision`, `maiw_execution`, `maiw_mcp`, `maiw_state`, `maiw_skills`, `maiw_contracts` → `packages/<pkg>/…`.
* **`maiw_execution` is part of the canonical install.** It appears in `ci-cd.yml` and in the runbook install loop, so it was installed as specified and is verified.
* The host has unrelated `maiw-*` editable installs in another interpreter (`nvidia-wms-workshop/.venv`, pointing at a dev worktree). They are not visible to the audit venv.

## 6. Listener Inventory (§2)

Inventory taken before anything was started (`/proc/net/tcp{,6}`; `ss` is not permitted to the auditor) and `docker ps -a`:

| Port | Owner | Treatment |
|---|---|---|
| 22, 53 (127.0.0.53/54) | system | off-limits |
| 3000 | unknown (other user); appeared intermittently and was gone at the end | off-limits |
| 32768 | `nemo-microservices-postgres-1` | off-limits |
| 32769 | `nemo-microservices-guardrails-1` | off-limits |
| 8081 (container-internal) | `nemoclaw-llama-cpp` (restart loop, pre-existing) | off-limits |
| 8000–8020, 5435, 8991 | **no listener** (`wms-nim-*`, `cuopt`, `wosa-timescaledb` and the `maiw-qual-20c-b` sandbox container are all exited) | off-limits regardless |

**OpenShell gateway.** The registered gateway `nemoclaw-8991` was **down** (connection refused). It was not started, because it is a user component and `maiw-qual-20c-b` lives in it.

## 7. External-Service Isolation (§3)

**Audit-owned ports:**

| Purpose | Port(s) |
|---|---|
| Reference API | 18930 |
| Probe app instances | 18931–18933 |
| Reference DB (`maiw-v201-third-db`) | 55441 |
| Test DB (`maiw-v201-third-testpg`) | 55442 |
| OpenShell gateway `maiw-v201-third-gw` | 18991 (sandbox callback 172.23.0.1:18991) |
| Fake provider | 18901 |
| Recording MCP servers | 18940–18943 |
| Decoys | 18950, and 18930 while stopped |
| Closed "unreachable" targets | 18949, port 1 |

**Test defaults reviewed:**
* `tests/conftest.py` `api_base_url` and `tests/unit/test_config.py` default to `localhost:8001`. They are used only by suites outside CORE CI.
* The `localhost:8000/8002` strings in `test_phase_20c_approved_nemotron.py` are construction-time rejections; no I/O happens.
* `test_phase_20b_real_inference.py` is opt-in (`MAIW_PHASE20B_NIM_URL` unset → skip).

**Contamination guard.** `.third-probes/connwatch.py` sampled `/proc/net/tcp{,6}` every 50 ms for the whole audit (all tests, live runs and probes). It watched for any socket to ports 3000, 5435, 8000–8020, 8080–8082, 8990, 8991 and 32768–32770. It recorded **0 hits**. No pre-existing service was contacted, and no contamination incident occurred.

**Gateway caveat (§28).** The runbook lists "a running OpenShell gateway" as a prerequisite but has no step for it, and the host's gateway was down after the reboot. The auditor therefore ran an **audit-owned** `openshell-gateway` 0.0.116:
* name `maiw-v201-third-gw`, port 18991, docker driver;
* own namespace `maiw-v201-third-audit`, own network `maiw-v201-third-net`;
* own Ed25519 gateway-JWT, own state directory;
* TLS disabled on loopback.

The CLI was pointed at it with `OPENSHELL_GATEWAY_ENDPOINT` in the clean shell. The user's gateway configuration was not touched. The gateway was stopped and its network and keys were removed at the end.

Sandbox isolation is enforced by the same `openshell-sandbox` supervisor binary under any gateway, so the isolation results stand. Running the gateway without mTLS is an audit-environment difference, recorded here.

## 8. Historical Audit Preservation (§8)

* PR #142 is OPEN at `742fd2a`; its artifact still reads `MAIW V2 INDEPENDENT POST-RELEASE AUDIT FAIL`.
* PR #144 is OPEN at `80947b0`; its artifact still reads `MAIW V2.0.1 INDEPENDENT RE-AUDIT FAIL`.
* `v2.0.0` → tag object `0c35a0e` / commit `816ace7`, unchanged. There is no `v2.0.1` tag. The only release is "MAIW v2.0.0".
* PR #143 does not touch the PR #142 or PR #144 files. Nothing was modified.

---

## 9. Original Five P1 Re-Audit (§9–§14)

| P1 | Re-test on `86f3004` | Result |
|---|---|---|
| **P1-01** ungoverned chat write | Live deployment, 45-request bypass battery (`route_bypass.json`). `/api/v1/chat` and all variants (`/`, `/stream`, `//`, upper-case, `%2F`, `?x`, `./`) → 404. `/reasoning/*` and `/mcp/tools/execute` → 404. Legacy writes → 404/405. DB fingerprint (7 tables, md5) **unchanged**; FL-01 `available → available`. Audit FL-01 Postgres scenario `test_p1_01_audit_chat_scenario_against_postgres` against the audit DB: **passed**. From the sandbox: chat 404, inventory PUT 405. | **CLOSED** |
| **P1-02** inference endpoint | No token 401; wrong token 401; forbidden fields `model_id`/`base_url`/`deployment_mode` 422; unknown `model` 422; `role: tool` 422; valid 200 (host, smoke and sandbox). No token configured → 503 fail-closed (`p105_probe`). | **CLOSED** |
| **P1-03** durable state | Real restart. Proof SOP A was driven to `WAITING_FOR_GOVERNANCE` (rev 23, `establish_state` attempts 2) in the deployment root. Script `start` served it over HTTP unchanged; script `restart` again unchanged. The file sha256 `ec6b40b3…` is identical before and after. | **CLOSED** |
| **P1-04** readiness | Persistence `chmod 000` → 503 `[persistence]`. DB container paused → 503 `[database]`. Required sandbox stopped → 503 `[sandbox_runtime]`. Required MCP absent / unreachable / circuit-open → 503. `/live` 200 in every row (§25). | **CLOSED** |
| **P1-05** document → ModelGateway | Judge call through the canonical lifespan sent 1 provider request for the approved Super ID. Non-JSON reply → typed `DocumentInferenceUnavailable[MALFORMED_RESPONSE]`. Provider down → typed `[MODEL_UNAVAILABLE]`. No synthetic APPROVE. Shipped-app module scan: no direct-provider LLM module loaded after import or lifespan (only `src.retrieval.vector.embedding_service`; see P2). | **CLOSED** |

## 10. NEW-P1-01 Physical Model Identity (§15)

**Code path** (all read on the candidate):

```
src/api/routers/inference.py:sandbox_inference
  → maiw_models.ModelGateway.generate
     (gateway.py:110 route; :125 DeploymentResolver.resolve; :133 provider.call(model_id=resolved.model_id); :156 verify_response_identity)
  → ModelRouter.route
     (router.py:232 physical_identity_violation → ModelPolicyViolation; no silent fallback)
  → PolicyFilter.is_request_eligible
     (routing.py:2b physical identity)
  → NIMProvider.call
     (nim.py: empty ID refused, so NIMClient cannot fall back to LLM_MODEL)
  → NIMClient.generate_response(model_override=…)
```

* **Generation is bound to the physical ID.** It comes from `APPROVED_DEPLOYMENTS` (`registry._generation`, `deployment.generation_for`). It is never taken from a role or parsed from the ID.
* **No production caller bypasses the resolver.** `ModelGateway.evaluate_with_model(allow_out_of_policy=True)` skips it, but has no production caller (P2 observation).

## 11. Deployment Resolver / Approved Table (§16)

| Role | Physical ID | Generation | Default |
|---|---|---|---|
| super | `nvidia/nemotron-3-super-120b-a12b` | nemotron-3 | enabled (**live-qualified here**) |
| lightning | `nvidia/nemotron-3.5-lightning-30b-a3b` | nemotron-3.5 | enabled (**live-qualified here**) |
| ultra | `nvidia/nemotron-3-ultra-550b-a55b` | nemotron-3 | disabled (provider-listed; fake-provider dispatch only) |
| nano | `nvidia/nemotron-3-nano-30b-a3b` | nemotron-3 | **disabled** (hosted EOL) |

* There is no multimodal entry.
* The table rejects duplicates, empty or whitespace IDs, and any generation outside `{nemotron-3, nemotron-3.5}`.
* The live provider `/models` probe listed Super and Lightning. Approval is by exact ID; there is no inference from names.

## 12. Fake Provider Matrix (§17, §18)

Canonical app per configuration; audit fake OpenAI-compatible provider on 127.0.0.1:18901 that records the `model` it receives and never forwards anything; cache disabled. Source: `fp_matrix.json`, `fp_d2.json`.

| Case | Configuration | Request | HTTP / code | Provider calls | Provider received | Response model reported | Policy |
|---|---|---|---|---|---|---|---|
| A | defaults | high / low / medium | 200 / 200 / 200 | 1 / 1 / 1 | super / lightning / super | same ID, `identity_verified=true` | allowed |
| A2 | `LLM_MODEL=meta/llama…`, `MAIW_NIM_MODEL=example-org/…` | high / low | 200 / 200 | 1 / 1 | super / lightning | same | not dispatched (preflight FAILs on them) |
| **B** | `NEMOTRON_SUPER_MODEL=example-org/unapproved-model-x` | high, medium | **503 MODEL_POLICY_VIOLATION** | **0** | — | — | rejected; `/ready` 503 `model_gateway` |
| B2 | `NEMOTRON_LIGHTNING_MODEL=meta/llama-3.1-8b-instruct` | low | 503 MODEL_POLICY_VIOLATION | 0 | — | — | rejected |
| **C1–C4** | look-alikes: `…-a12b-v2`, `NVIDIA/…` (case), trailing space, U+2010 hyphen | high | 503 MODEL_POLICY_VIOLATION | **0** | — | — | rejected |
| C5 | super ← Lightning ID (cross-role) | high | 503 (ROLE_MISMATCH) | 0 | — | — | rejected |
| C6 | Nano enabled with `…nano-30b-a3b-instruct` | medium | 503 | 0 | — | — | rejected |
| **D** | Ultra enabled with `totally-unknown/model-d`, judge task | high | **503 MODEL_POLICY_VIOLATION (UNAPPROVED_MODEL_ID)** | **0** | — | — | rejected |
| D′ | Ultra enabled, approved ID, judge task | high | 200 | 1 | ultra ID | same | allowed |
| **E1** | provider answers `example-org/substituted-model-y` | high | **502 MODEL_IDENTITY_MISMATCH**, no content | 1 | super ID | (discarded) | rejected |
| E2 | provider answers the Lightning ID (another *approved* model) | high | 502 MODEL_IDENTITY_MISMATCH | 1 | super ID | (discarded) | rejected |
| E3 | provider answers a case variant of the Super ID | high | 502 MODEL_IDENTITY_MISMATCH | 1 | super ID | (discarded) | rejected |
| E4 | provider **omits** `model` | high | **200 with content**, `identity_verified=false` | 1 | super ID | `null` | fail-open (P2, §59 N-1) |

* In the B and D rows, readiness was 503 while requests for *other*, healthy roles were still served with their approved IDs (e.g. B low → Lightning). That is correct.
* Across all 24 requests the provider received **only** approved IDs.

## 13. Provider Response Identity (§19)

* A different reported ID — unapproved, another approved model, or a case variant — gives 502 `MODEL_IDENTITY_MISMATCH` and the content is discarded.
* An omitted ID is accepted and returned with `identity_verified=false` (P2 N-1). Smoke treats that as a FAIL, but the runtime does not.

## 14. Model Preflight (§20)

* The clean-shell preflight runs `check_model_config.py --provider-probe`, which uses the same `ModelRegistry` and `DeploymentResolver` as the gateway, on the `NEMOTRON_<ROLE>_*` values the runtime dispatches. Result: 29/29 PASS, and the provider listed both enabled models.
* Negative checks (shell exports win over `.env` in the loader):
  * `NEMOTRON_SUPER_MODEL=example-org/…` → FAIL `UNAPPROVED_MODEL_ID`, exit 1;
  * `LLM_MODEL=meta/llama…` → FAIL, exit 1;
  * `NEMOTRON_LIGHTNING_MODEL=<super ID>` → FAIL `ROLE_MISMATCH`, exit 1.
* There is no stale `LLM_MODEL`-only check.

## 15. Model Smoke Validation (§21)

* Smoke 14/14, both before and after restart.
* It reported: logical role `super`; resolved model `nvidia/nemotron-3-super-120b-a12b`; generation `nemotron-3`; provider-reported model = resolved; `identity_verified=True`; `approved_family=True`.
* It checks equality and approval through `check_model_config.py --expect`.

## 16. Nano Default (§22)

* `NEMOTRON_NANO_ENABLED` defaults to false (`registry._ENABLED_DEFAULTS`). Preflight shows it as `INFO disabled`, and the provider probe lists only enabled roles.
* The smoke request (MEDIUM) went to Super with `fallback_used=true`; so did the in-sandbox MEDIUM request.
* No preflight or smoke path touches the 410 endpoint.

## 17. NEW-P1-02 Runbook Reproducibility (§23) and Clean-Shell Deployment (§30)

Every command ran in `env -i HOME PATH LANG OPENSHELL_GATEWAY_ENDPOINT` from the clone root (`.third-logs/runbook/summary.txt`).

| # | Command (runbook "Clean-host procedure") | Exit |
|---|---|---|
| 1 | venv + `pip install -r requirements.txt` + 8 package loop + agents/api (verbatim) | 0 (all 12 sub-steps) |
| 2 | `cp .env.example .env` + edit exactly the runbook-listed variables (no variable outside `.env.example`) | 0 |
| 3 | `bash scripts/validate_reference_runbook.sh` | 0 |
| 4 | `bash scripts/setup/reference_db.sh up` (`maiw-v201-third-db`, 127.0.0.1:55441, schema loaded) | 0 |
| 5 | `bash scripts/setup/reference_sandbox.sh create` (`maiw-v201-third-a`) | 0 |
| 6 | `bash scripts/preflight_reference_deployment.sh` — **full, no skip: 29 passed / 0 failed** | **0** |
| 7 | `bash scripts/start_reference_deployment.sh` (its own preflight passed; READY in 4 s) | 0 |
| 8 | `bash scripts/status_reference_deployment.sh` | 0 |
| 9 | `bash scripts/smoke_test_reference_deployment.sh` — 14/14 | 0 |
| 10 | `bash scripts/setup/reference_sandbox.sh probe` (sandbox → canonical app → Super, identity verified) | 0 |
| 11 | `bash scripts/restart_reference_deployment.sh` (preflight before stop; port held by the verified instance PASS) | 0 |
| 12 | `bash scripts/status_reference_deployment.sh` | 0 |
| 13 | `bash scripts/smoke_test_reference_deployment.sh` — 14/14 | 0 |
| 14 | `bash scripts/stop_reference_deployment.sh` | 0 |
| 15 | status after stop | 1 (NOT RUNNING / CANNOT VERIFY, as designed) |
| 16 | teardown: `reference_sandbox.sh delete`, `reference_db.sh down` (run at the end of the audit) | 0 / 0 |

* **Negative pass.** A first pass ran before the audit gateway had JWT configured. Sandbox create failed, and then:
  * preflight → 28/1 (sandbox absent), exit 1;
  * start refused, exit 1;
  * status, smoke and restart refused (1/2/2);
  * stop exited 0 with nothing signalled.

  The failure was correct and safe. The DB was torn down and everything was recreated from scratch before the passing run.
* **No builder memory and no hidden product step.** The only non-runbook action was providing the host prerequisite "running OpenShell gateway" (§7).

## 18. Environment Loading (§25)

* Every lifecycle script sources `scripts/lib/load_env.sh` and calls `maiw_load_env` before any validation: preflight, start, stop, restart, status, smoke, qualify, reference_db and reference_sandbox.
* Values are parsed, not executed. Shell exports win (verified: loaded 62 + kept 1 when overriding the profile). `PYTHON_DOTENV_DISABLED=1` is exported; python-dotenv 1.2.4 honours it.
* Start, and restart's preflight, re-invoke preflight on the identical exported environment ("loaded 0 … 63 already set").

## 19. Deployment Identity (§26) and Stop-Script Safety (§41)

All decoys were audit-owned `.third-probes/decoy.py` listeners that record every request (`.third-logs/decoy/summary.txt`).

| Scenario | status | smoke | restart | stop | preflight / start | Decoy | Requests reaching decoy |
|---|---|---|---|---|---|---|---|
| D1 decoy on 18930, no instance file | 1 | 2 (refused) | 2 | 0 ("nothing signalled") | 1 / 1 (port in use) | alive | **0** |
| D2 forged instance file → decoy PID | 1 | 2 | 2 | **3** (refused, state kept) | — | alive | **0** |
| D3 impostor with cmdline `python -m uvicorn maiw_api.app:app --host 127.0.0.1 --port 18930 …` (other cwd, no instance env) | 1 | 2 | — | **3** | — | alive | **0** |
| D4 stale instance file (dead PID) + decoy on port | — | 2 | — | 0 (stale state cleared, nothing signalled) | — | alive | **0** |
| Own instance + valid identity | — | — | 0 | 0 (SIGTERM to the verified PID only) | — | — | — |

* There is no kill-by-port, no kill-by-name and no fallback in any lifecycle script; the only `kill -TERM/-KILL` is the verified PID in `stop`.
* `scripts/setup/cleanup_for_testing.sh`, a dev helper outside the runbook, still kills by process name (P2 N-10).

## 20. Database Setup (§27)

* `reference_db.sh up` created the labelled `timescale/timescaledb:2.15.2-pg16` container `maiw-v201-third-db` (id `1b3c96a4…`) on 127.0.0.1:55441, loaded `data/postgres/*.sql`, and verified `SELECT 1` plus the schema.
* `down` removed only that container.
* The CI-mirroring test DB `maiw-v201-third-testpg` (postgres:16.1, 127.0.0.1:55442) was used for `DATABASE_URL` in pytest, then removed.
* Port 5435 (foreign `wosa-timescaledb`, exited) was never used.

## 21. Sandbox Setup (§28, §42)

* `reference_sandbox.sh create` rendered the policy template (egress only to `10.185.115.61:18930`, python3 binaries only), created **`maiw-v201-third-a`** (id `17a35f38-5e7f-49a2-9ab6-eb2ebbaf4651`) from `base` with no provider attached, and waited for Ready. A marker file was recorded.
* The token reached the probe only over stdin.
* The sandbox was deleted by `reference_sandbox.sh delete`. `maiw-qual-20c-b` was never touched.

## 22. MCP Setup (§29)

* The `reference` profile requires no MCP domain; every domain is reported `NOT_CONFIGURED` with readiness 200.
* For `reference_governed`, the runbook documents the required domains (`equipment,labor,wave`, override `MAIW_REQUIRED_MCP_DOMAINS`), the optional `inventory`, the `MAIW_MCP_SERVER_*_URL` variables and the readiness rules.
* It gives **no command to run an MCP server** for that profile (P2 N-9). The auditor used the repo's own MCP server modules with mock providers (`.third-probes/mcp_recorder.py`), run on audit ports over streamable HTTP.

## 23. NEW-P1-03 Readiness (§31–§36)

Twenty rows (`ready_matrix.json`):

| Condition | Expected | `/ready` | failed_components / states | `/live` |
|---|---|---|---|---|
| reference baseline (sandbox required) | 200 | 200 | MCP all `NOT_CONFIGURED`; `governed_write_path: not_offered` | 200 |
| persistence `governance/` chmod 000 → restored | 503 → 200 | 503 → 200 | `[persistence]` | 200 |
| reference DB paused → unpaused | 503 → 200 | 503 → 200 | `[database]` | 200 |
| **required sandbox stopped** (`openshell sandbox stop`) → started | 503 → 200 | 503 → 200 | `[sandbox_runtime]` (phase Stopped) | 200 |
| reference_governed, all required MCP healthy | 200 | 200 | equipment/labor/wave READY | 200 |
| reference_governed, required MCP absent | 503 | 503 | `[governed_write_path, mcp_domains]`, NOT_CONFIGURED | 200 |
| reference_governed, wave unreachable | 503 | 503 | wave `FAILED` | 200 |
| reference_governed, equipment URL → non-MCP listener, after 8 calls | 503 | 503 | equipment `CIRCUIT_OPEN` | 200 |
| reference_governed, required list `labor` only | 200 | 200 | labor READY, others NOT_CONFIGURED | 200 |
| reference, optional equipment unreachable | 200 | 200 | equipment `FAILED` (non-critical) | 200 |
| optional sandbox (mode optional) absent | 200 | 200 | `sandbox_runtime: degraded` | 200 |
| required sandbox named but absent / name unset | 503 / 503 | 503 / 503 | `[sandbox_runtime]` | 200 |
| invalid profile value | 503 | 503 | `[profile]` | 200 |
| unapproved model binding | 503 | 503 | `[model_gateway]` | 200 |
| persistence root not creatable | 503 | 503 | `[persistence]` | 200 |

* Unconfigured never masquerades as HEALTHY.
* Before the circuit trips, a TCP-reachable non-MCP listener on a required URL reads `READY`, because reachability is a TCP connect (P2 N-4).
* **Residual (counted under NEW3-P1-01):** in `reference`, setting an optional MCP equipment URL wires a working executor while readiness says `governed_write_path: not_offered`.

## 24. MCP Readiness (§32, §33)

Required domain absent, unreachable or circuit-open → 503. Optional domain unconfigured → 200 and `NOT_CONFIGURED`. Both verified (§23).

## 25. Sandbox Readiness (§34, §35)

Required sandbox stopped or absent → 503. Optional sandbox → 200, `degraded` / `not_configured`, stated explicitly. Both verified (§23).

## 26. Liveness (§36)

`/api/v1/live` returned 200 and the instance ID in every one of the 20 rows.

## 27. NEW-P1-04 Test Order Independence, Global State, Test Order Matrix (§37, §39)

Every run used a fresh process, the CI selection and ignores, `--timeout=120`, `DATABASE_URL` → the audit test DB (55442), and no `.env` (`.third-logs/pytest_summary.txt`).

| Order | Result |
|---|---|
| ModelGateway → demo (`test_model_gateway.py tests/unit/demo`) | 191 passed |
| demo → ModelGateway | 191 passed |
| canonical app → reliability | 442 passed, 2 skipped |
| reliability → canonical app | 442 passed, 2 skipped |
| reversed directories (agents, api, mcp, contract, unit) | **2805 passed, 8 skipped, 0 failed** |
| ModelGateway first (full) | 2805 / 8 / 0 |
| reliability first (full) | 2805 / 8 / 0 |
| canonical first (full) | 2805 / 8 / 0 |
| seeded file shuffle, seed **7311** (auditor's seed) | 2805 / 8 / 0 |
| seeded file shuffle, seed **90210** (auditor's seed) | 2805 / 8 / 0 |

* The first shuffle attempt aborted at collection, rc 2. The cause was an auditor list-builder bug: `--ignore` lines were parsed with a trailing newline, so `test_mcp_system.py` was included. After the fix both shuffles passed. This was not a product failure.
* **Global state:** the fixes are confirmed in code.
  * `tests/conftest.py::_isolate_process_singletons` saves and restores env, gateway, NIM client, runtime, demo controller, MCP providers, SQL retriever, rate limiter and the task registry.
  * There is no `sys.modules` purge in contract conftest, `test_model_lab_api.py` or `test_checkpoint_d.py`.
  * Demo tests use `asyncio.run`; `PYTHON_DOTENV_DISABLED=1` is set in both conftests.
  * No cross-test contamination was observed in 11 orders.

## 28. Full Python Suites (§38)

| Run | Result |
|---|---|
| Run 1 (CI order) | **2805 passed, 8 skipped, 0 failed**, 224 s |
| Run 2 (CI order, separate process) | **2805 passed, 8 skipped, 0 failed**, 226 s |

The 8 skips:
* legacy `test_migration_system`;
* `MAIWSkillAdapter` unavailable;
* 3 × opt-in `MAIW_PHASE20B_NIM_URL`;
* 1 × OpenShell not importable;
* 2 × opt-in `MAIW_TEST_PG_DSN`.

The counts match the claimed `2805/8`. Opt-in Postgres tests against the audit DB:
* with only `MAIW_TEST_PG_DSN` set: 1 passed, **1 failed**. `test_p1_04_ready_with_reachable_database` is stale since round 2 made readiness probe `PGHOST`/`PGPORT` (P2 N-3).
* with `PGHOST`/`PGPORT`/`POSTGRES_PASSWORD` also set: **2 passed**.

## 29. Governance Crash Recovery (§40)

Every step is a separate process lifetime of `maiw_api.app` (real lifespan, JsonFile stores). Crashes are real `os._exit(137)` at the injected point (`gov/matrix.jsonl`).

| Case | Sequence | Result |
|---|---|---|
| **A** crash before accept | deliver → crash in `inbox.accept`; restart | rev 23 WAITING, unapplied 0, ledger empty → redeliver applied once (rev 24, ledger `accepted, applied`) → redeliver again `duplicate=true` |
| **B** crash after accept, before resume | deliver → crash in `resume_after_governance`; restart | `/ready persistence.unapplied_governance=1`, ledger `[accepted]` → `recover_accepted_governance` resumed **exactly once** (rev 24) → second recover no-op → redeliver `duplicate` |
| **C** crash after resume, before applied marker | deliver → crash in `mark_applied`; restart | stored rev 24 (resume checkpointed), unapplied 1 → recover: `already_applied`, **engine not re-run** → redeliver `duplicate` |
| **D** duplicate | deliver, deliver again | 2nd `duplicate=true`, revision unchanged (24), ledger 2 lines |

**Holds at the library and app-lifespan level.** However, `apply_governance` and `recover_accepted_governance` have **no production caller**: there is no HTTP route, and startup only logs. In the shipped app, case B leaves the procedure WAITING with `unapplied_governance=1` until an owner calls recovery (P2-10).

## 30. UNKNOWN Execution (§49) and Duplicate-Write Recovery (§50)

Setup: canonical app, `reference_governed`, a real streamable-HTTP equipment MCP server (audit recorder with a mock backend) that records the write and then **crashes before responding**. Source: `unknown/result.json`.

| Step | Observation |
|---|---|
| `POST /api/v1/equipment/release FL-01` | 200 `{"status": "failed", "executed": false, …}`; the write **landed** (1 write recorded) |
| wait 8 s, no request | still 1 write (no automatic blind retry) |
| `POST /api/v1/demo/reconcile` | **503** "Demo mode not active" (the reconciliation route is unusable outside demo) |
| identical operator retry | 200 `executed: true`; **2nd write** recorded (no idempotency; `execution_id: null` at the backend) |
| app restart | no re-execution (still 2) |

* **Mechanism.** `BaseActionExecutor` maps only `AmbiguousWriteError` to UNKNOWN (`maiw_execution/base.py:336`). No production code raises it; simulation fakes do. Any real transport error after send falls into the generic `except Exception` branch → `FAILED`, `physical_mutation_occurred=False` (`base.py:365-385`).
* **Result: NEW3-P1-02.** In demo mode the library behaviour is covered by the passing `tests/unit/reliability` fault suites.

## 31. Canonical App Route Inventory (§51)

The real route table holds 143 routes (`route_inventory.json`). Non-GET routes:

| Route | Method | Auth | Mutation | Governance | Notes |
|---|---|---|---|---|---|
| `/api/v1/equipment/assign` | POST | **none** | warehouse (via MCP) | DecisionEngine (MEDIUM → human approval) | executes only if APPROVED |
| `/api/v1/equipment/release` | POST | **none** | warehouse (via MCP) | DecisionEngine (**LOW → auto-approve**) | **executed from the sandbox** (NEW3-P1-01) |
| `/api/v1/equipment/maintenance` | POST | none | proposal only | always human | — |
| `/api/v1/demo/{scenario…,tick,inject,analyze}` | POST | none | simulation state | demo-mode only (503 otherwise) | — |
| `/api/v1/demo/{approve,reject,reconcile}` | POST | none | governed execute / record | pop-once approval; demo controller | reconcile 503 outside demo |
| `/api/v1/copilot/turn` | POST | none | ACT via GovernedActionOrchestrator (demo) | yes | reference: degraded, 0 model calls |
| `/api/v1/inference` | POST | internal token | none | n/a | — |
| `/api/v1/auth/{login,refresh}` | POST | credentials | identity | — | — |
| `/api/v1/auth/register`, `PUT /auth/users/{id}` | POST/PUT | admin JWT | identity | — | 401 unauthenticated |
| `PUT /auth/me`, `POST /auth/change-password` | PUT/POST | JWT | identity | — | — |
| `/api/v1/document/upload` | POST | **none** | file + DB rows | — | P2-04 |
| `/api/v1/document/{approve,reject}/{id}` | POST | none | doc-workflow stub | — | P2-09 |

## 32. Route Policy Bypass Tests (§51)

* Alternate methods on GET-only paths → 405. Trailing slash → 307 to the same path, which then answers 405/401/404 as above. Case, encoding, `//` and `./` variants → 404.
* Hidden legacy writes (migrate, rollback, training, forecasting batch, WMS/ERP/IoT) → 404/405. `/procedures` writes → 405. Inference GET/PUT/PATCH/DELETE → 405.
* The DB fingerprint was unchanged.
* `curated_view` / `read_only_view` copy only `APIRoute`s whose methods are within {GET, HEAD, OPTIONS} plus the explicit allowlist, so they fail safe.
* `GET /api/v1/document/analytics` is still shipped (P2-09).

## 33. Fresh Sandbox Qualification (§42, §43)

| Item | Value |
|---|---|
| Sandbox | `maiw-v201-third-a` (17 chars), id `17a35f38-5e7f-49a2-9ab6-eb2ebbaf4651` |
| Path | sandbox → `http://10.185.115.61:18930/api/v1/inference` (canonical `maiw_api.app`, started by the runbook's `start`) → ModelGateway → DeploymentResolver → hosted NIM |
| Status | Created, Ready, used, and deleted with the runbook script |

## 34. Live Nemotron 3 Super (§44)

| Field | Value |
|---|---|
| Request / logical role | `high` / `super` |
| Resolved model / generation | `nvidia/nemotron-3-super-120b-a12b` / `nemotron-3` |
| Provider-reported model | `nvidia/nemotron-3-super-120b-a12b` — **match** (`identity_verified=true`, `approved_family=true`) |
| Routing rule | `high_reasoning` |
| Latency | 283.0 ms server, 319.5 ms client (from the sandbox) |
| MEDIUM | → super, `fallback_used=true`, match, 211.2 / 236.5 ms |

## 35. Live Nemotron 3.5 Lightning (§44)

| Field | Value |
|---|---|
| Request / logical role | `low` / `lightning` |
| Resolved model / generation | `nvidia/nemotron-3.5-lightning-30b-a3b` / `nemotron-3.5` |
| Provider-reported model | `nvidia/nemotron-3.5-lightning-30b-a3b` — **match** |
| Routing rule | `low_reasoning` |
| Latency | 255.9 ms server, 269.3 ms client (from the sandbox) |

## 36. Direct Provider Denial (§45)

From inside the sandbox (`sbx_probe.json`):

| Target | Result |
|---|---|
| `https://integrate.api.nvidia.com/v1/models` | BLOCKED |
| `http://integrate.api.nvidia.com/v1/chat/completions` | proxy 403 |
| DNS for the provider | DENIED |
| `https://github.com` | BLOCKED |
| `1.1.1.1:443` | refused |
| `169.254.169.254` | 403 |
| sandbox-local `127.0.0.1:8000` and `:18930` | refused |
| Host, **other port on the allowed IP** (audit decoy `10.185.115.61:18950`) | HTTP 403 / TCP refused; 0 requests reached the decoy |
| Host DB `:55441` | refused |
| Gateway callback `172.23.0.1:18991` | refused |

Host `:8001`/`:8002` were not targeted, because there are no listeners there. The decoy on an adjacent port proves port-level denial on the allowed IP.

## 37. Credential Isolation (§46)

* 28 environment variables; 0 names matching KEY/TOKEN/SECRET/PASS/NVAPI/CRED/GITHUB/DATABASE/PG.
* No values with the `nvapi-`, `ghp_`, `gho_`, `github_pat_`, `postgresql://` or `sk-` prefixes.
* The token was passed on stdin only and never printed.
* The token, NVIDIA key and DB password do not appear in the API log, the runbook logs or the `/health` and `/ready` bodies.

## 38. Filesystem Isolation (§47)

* **Absent:** `/home/nvidia`, `~/.ssh`, `~/.env`, `~/.git-credentials`, `~/.config/gh/hosts.yml`, `~/.nemoclaw`, `~/.local/state/nemoclaw`, the clone's `.git/config`, `.third-state` (host persistence and the runbook `.env`), `/var/lib/maiw`, `/var/run/docker.sock`, `/run/docker.sock`, `/root/.ssh`.
* **Denied:** `/etc/shadow`, `/proc/1/environ`.
* **Writes denied:** `/etc`, `/usr`.
* **Not importable:** `maiw_execution`, `maiw_decision`, `maiw_mcp`, `maiw_api`, `integrations`.

## 39. Prompt Injection (§48)

Inputs:
* a system message plus a user message demanding a model switch to Llama-405B, `approved=true`, a direct provider call, an FL-01 assign and key disclosure;
* field injections `model_id`, `base_url`, `deployment_mode` (422) and `role: tool` (422).

On the inference boundary the result was **structural denial**:
* 200 with routing unchanged (super, approved, `high_reasoning`, identity verified);
* the reply text was a refusal, which is irrelevant to the result;
* nothing below `/inference` can write.

**However**, the same untrusted sandbox can perform the write *directly* over its one allowed host:port (NEW3-P1-01): `POST /api/v1/equipment/release` → executed. **§48 "direct write → structural denial" does not hold in `reference_governed`, nor in `reference` with an optional MCP URL set.** In the default `reference` profile with no MCP URL, the same call returns 400 (no MCP).

## 40. Document Authentication (§52) — independent ruling

Unauthenticated `POST /api/v1/document/upload` (`doc/result.json`):
* stores the file under `data/uploads/`, which is never deleted;
* inserts a `documents` row (0 → 1);
* starts processing.

With the default configuration it triggers **0 model calls**: vision is unavailable, and preprocessing of the probe PDF failed with a typed error. With an unapproved Nano-Omni configured it is still 0 calls (policy violation). The endpoint is reachable from the sandbox and any network peer (`MAIW_API_HOST=0.0.0.0` in `.env.example`).

**Ruling: P2.** It enables unbounded disk and DB growth and abuse, but has no inference-quota impact in the shipped configuration and no confidentiality or integrity impact on warehouse operations. It would be P1 for any deployment reachable beyond a trusted network. The runbook should say so and should require network restriction.

## 41. Legacy Read Authentication (§53) — independent ruling

Unauthenticated GETs return:
* equipment (with `owner_user`) and assignments (`assignee`);
* inventory;
* `/version/detailed` (`build_host`, `build_user`, `git_sha`, `docker_image`);
* `/runtime/status` and `/ready` internals;
* `/auth/users/public` (empty list on the reference DB).

All of these are also reachable from the sandbox. `advanced_forecasting` GETs are hard-wired to `localhost:5435` and redis `localhost:6379`, so they ignore `PGHOST`/`PGPORT`. They were deliberately **not called**, because 5435 is a foreign DB on this host.

**Ruling: P2.** This is information exposure on an internal deployment, with no mutation. The hard-wired 5435 path is a data-path hazard on shared hosts.

## 42. Chunked Upload / Rate Limit (§54) — independent ruling

* **Chunked upload.** A 60 MB multipart body with no `Content-Length` bypassed the 50 MB middleware limit. A **62.9 MB file was written to disk and left there**; the response was 500 "Document validation failed".
* **Upload with `Content-Length`.** It was rejected, but as **500** "Request processing failed: 413" rather than 413 (N-8).
* **Rate limiting:** 150 rapid GETs and 30 rapid uploads all returned 200. Rate limiting does not enforce.

**Ruling: P2.** This is a resource-exhaustion DoS from any reachable peer, with no data-integrity impact. Recommend a streaming size cap and a working limiter before any exposed deployment.

## 43. Document Multimodal (§55) — independent ruling

* `modality=image` gives typed **503 `MODEL_UNAVAILABLE`** ("Tried roles: nano-omni, super").
* With `NEMOTRON_NANO_OMNI_ENABLED=true` and a plausible Nemotron-3 Omni ID: typed **503 `MODEL_POLICY_VIOLATION`** (no approved entry).
* No crash and 0 provider calls in either case.
* The prior "crash even with multimodal config" (P2-08, cache-key `.strip()` on list content) is **unreachable** now, because no multimodal deployment can be approved without a code change.

**Ruling: CLOSED as a release blocker.** It is an acceptable, explicit limitation. The latent cache bug is only relevant when a multimodal model is added.

## 44. Response Cache (§56) — independent ruling

With the cache at its default (enabled, TTL 300 s) and a fake provider:

| Sequence | Provider calls | Note |
|---|---|---|
| HIGH | 1 | `reasoning_budget=0` |
| MEDIUM | **0** | served HIGH's cached thinking-mode answer |
| LOW | 1 | Lightning, a different key |
| HIGH | 0 | cached |
| MEDIUM | 0 | cached |

* The cache key (`nim_client.py:301-332`) includes model and sampling parameters but **not** `enable_thinking` / `reasoning_budget`.
* It also **normalises timestamps, UUIDs and dates out of the prompt**: two prompts differing only by an ISO timestamp produced **1** provider call, and the second was answered with the first's cached reply.
* The physical model identity is unaffected; the cached response is from the same approved ID.

**Ruling: P2.** It affects reasoning-mode semantics and can return a stale answer for time-varying prompts. It does not breach model identity.

## 45. UI Tests (§57)

| Check | Result |
|---|---|
| Node / npm | v24.1.0 / 11.3.0; `npm ci` in `src/ui/web` |
| Jest (`--watchAll=false`, `CI=true`) | **964 / 964 passed** |
| ESLint | **0 errors** (1041 warnings) |
| Production build (`npm run build`) | **OK** without `CI`. With `CI=true`, react-scripts treats the 1041 lint warnings as errors and the build fails. CI does not run the build (N-6). |

## 46. TypeScript (§57)

`npx tsc --noEmit`: **0 errors**.

## 47. npm Audit (§58)

* `npm audit`: **0 critical, 50 high**, 34 moderate, 3 low. `--omit=dev` gives the same totals, because `react-scripts`, `typescript` and `@testing-library/*` are in `dependencies`.
* All 50 highs are build, test or dev-server toolchain: jest, `@jest/*`, `@typescript-eslint/*`, eslint plugins, `react-scripts`, `webpack-dev-server`, `http-proxy-middleware` (devDependency), `svgo`/`@svgr`, `tailwindcss`, `chokidar`/`braces`/`micromatch`, `fork-ts-checker`, `react-dev-utils`.
* **Production-reachable:** `react-router` / `react-router-dom` **moderate** (GHSA-wrjc-x8rr-h8h6 open redirect; GHSA-337j-9hxr-rhxg, which is SSR-only). No production high. `axios` is not flagged.

## 48. Python Security Tools (§59)

| Tool | Status |
|---|---|
| pip-audit | **NOT AVAILABLE** (not installed; not downloaded) |
| trivy | **NOT AVAILABLE** locally (CI Trivy check passed on the head; claim only) |
| gitleaks | **NOT AVAILABLE** (grep-based scan used instead, §49) |

## 49. Secret Scan (§60)

`git grep` over the tracked tree at HEAD covered code, docs, scripts, artifacts, notebooks and `.env.example`. Patterns: `nvapi-…`, GitHub PAT/OAuth, AWS AKIA, private keys, Slack, `sk-`, JWT-like strings, and long secret assignments.

* **No real secrets.** Only the `.env.example` `nvapi-xxx…` placeholders.
* The hard-coded dev JWT fallback remains in `jwt_handler.py:110` (and is documented in `docs/secrets.md`) (P2-16).

## 50. Release Notes Audit (§61)

`RELEASE_NOTES_v2.0.1.md` (draft).

**Supported by this audit:**
* NEW-P1-01..04 descriptions;
* Nano disabled;
* profiles;
* round-2 test baseline (2805/8/0; Jest 964; tsc 0);
* chat/reasoning unmounted;
* durable stores;
* document pipeline through the gateway.

**Stale or incorrect:**
* "served … on the API port (**8001**)" and the `:8001` sandbox endpoint: there is no default port any more.
* "Provider **and sandbox** state are reported but not critical" (round-1 readiness text): the sandbox is critical when `MAIW_SANDBOX_MODE=required`.
* "build OK": OK only without `CI=true`.

**Missing limitations:**
* `reference_governed` governed writes are **unauthenticated and reachable from the sandbox** (NEW3-P1-01).
* Ambiguous writes on a real MCP transport are reported as FAILED; reconciliation is demo-only (NEW3-P1-02).
* Unauthenticated upload and legacy reads; the API binds `0.0.0.0` by default.
* Response-cache semantics.
* Identity check fails open when the provider omits `model`.
* There is no HTTP procedure start or governance submit, and recovery has no production caller.
* The runbook needs a pre-existing OpenShell gateway.

The draft makes no PASS claim. P2-17 stays open.

## 51. Round-2 Artifact Audit (§62)

| Round-2 claim | Reproduced? |
|---|---|
| Resolver is the only dispatch source; fake matrix A–E with 0 calls on rejection | **Yes** (24 requests, plus extra look-alikes and an E4 variant) |
| Live Super / Lightning identity | **Yes**, on the exact frozen SHA (round 2 ran on `9c27c12`) |
| Clean-shell reproduction (round 2 needed `--skip-preflight` for the GPU) | **Yes, with full preflight and no skip.** Needs a gateway (§7) |
| Readiness matrix | **Yes** (20 rows) |
| 2805/8/0 ×2 and 11 orders | **Yes** (2 full runs plus 9 alternative orders, auditor's own seeds) |
| P2-01 stop safety | **Yes** |
| P2-02 recovery exactly once | **Yes** (library and lifespan level; no production caller) |
| "No P1 open to my knowledge" | **Refuted:** NEW3-P1-01 and NEW3-P1-02 |
| Opt-in Postgres tests | Round 1 claimed 2 passed. On round-2 code one fails unless `PGHOST`/`PGPORT` are also set (N-3) |

Round 2 also correctly disclosed the response-cache observation (§44 here) and its own :8002 contact incident (four connections on its host). That incident does not affect this audit: 0 connections here.

## 52. Nine-P1 Closure Matrix (§63)

| Finding | Origin | Independently closed? | Evidence | Residual risk |
|---|---|---|---|---|
| P1-01 ungoverned chat write | PR #142 | **CLOSED** | route battery 404/405, DB md5 unchanged, PG FL-01 test pass, sandbox 404/405 | governed equipment POSTs unauthenticated → NEW3-P1-01 |
| P1-02 inference not on the canonical app | PR #142 | **CLOSED** | 401/401/422/422/200; 503 with no token configured; sandbox path | token compared non-constant-time (N-7) |
| P1-03 durable state not wired | PR #142 | **CLOSED** | WAITING procedure rev 23 identical across script start and restart (sha256 equal) | no HTTP start/resume (P2-10) |
| P1-04 readiness | PR #142 | **CLOSED** | 20-row matrix; `/live` independent | TCP-only MCP reachability (N-4) |
| P1-05 document direct provider / mock APPROVE | PR #142 | **CLOSED** | judge → 1 gateway call to Super; typed MALFORMED / UNAVAILABLE; no APPROVE | P2-09 stubs |
| NEW-P1-01 physical model identity | PR #144 | **CLOSED** | fake matrix, preflight negatives, live identities | omitted identity fails open (N-1); cache (N-2) |
| NEW-P1-02 runbook reproducibility | PR #144 | **CLOSED** | clean-shell sequence, all exit 0, full preflight 29/29 | gateway prerequisite undocumented (N-9) |
| NEW-P1-03 readiness vs governed writes | PR #144 | **CLOSED (original scope)** | 20-row matrix | in `reference` with an optional MCP URL, readiness says `not_offered` while writes execute → part of NEW3-P1-01 |
| NEW-P1-04 test order | PR #144 | **CLOSED** | 2 full runs plus 9 orders, 0 failures | — |

## 53. Remaining P2 Findings (§64)

Carried from PR #144 and re-verified:

| ID | Description | Risk / release impact | Recommendation | Decision |
|---|---|---|---|---|
| P2-03 | ExecutionRegistry idempotency unused by canonical callers; `execution_id` not forwarded to MCP (`null`) | duplicates on retry (escalated in combination: NEW3-P1-02) | forward a stable idempotency key to the backend | fix with NEW3-P1-02 |
| P2-04 | Unauthenticated upload: file and DB row persisted; chunked 62.9 MB bypass; no rate limiting | DoS / abuse; P1 if exposed | auth or network restriction; streaming cap; working limiter | defer with documented network restriction |
| P2-06 | Unauthenticated legacy reads (equipment owners, assignments, inventory, build host/user, readiness internals), also from the sandbox; forecasting hard-wired to `localhost:5435`/`:6379` | information exposure; wrong-DB hazard on shared hosts | auth or restrict; honour `PGHOST`/`PGPORT` | defer, document |
| P2-09 | Document approve/reject stubs; `GET /document/analytics` still shipped | false success | remove or implement | defer |
| P2-10 | No HTTP procedure start/resume/governance submit; `apply_governance` and `recover_accepted_governance` have no production caller; reconcile is demo-only | crash-recovery and governance flows need code-level owners | add an owner or document | defer, document |
| P2-11 | `.env.example` sandbox wording | largely addressed (readiness enforces) | — | close at next doc pass |
| P2-14 | Root `Dockerfile` copies `packages/` and `src/` but not `apps/`, `mcp_servers/`, `integrations/` | image cannot import `maiw_api` | fix or remove | defer |
| P2-15 | 50 npm highs, all toolchain | none in production | react-scripts migration | defer |
| P2-16 | Dev JWT fallback; `.env.example` `ENVIRONMENT=development` | weak default if `JWT_SECRET_KEY` is unset | fail closed outside dev | defer |
| P2-17 | Release-notes staleness and missing limitations (§50) | misleading notes | update | fix before tag |
| P2-18 | v2.0.0 release body still claims full qualification below the notice | historical | leave or annotate | defer (audit must not edit) |
| P2-20 | Plain-HTTP non-localhost provider URL only warns | MITM on a misconfigured endpoint | fail closed | defer |

Verified closed:
* P2-01: stop safety.
* P2-02: recovery exactly once.
* P2-07: smoke refuses without identity; no 8001 fallback.
* P2-08: moot, multimodal fails closed.
* P2-13: start never pip-installs.
* P2-19: readiness probes the data-path DB.

New P2s (this audit):

| ID | Description | Evidence |
|---|---|---|
| N-1 | Response identity fails open when the provider omits `model` (200 with content, `identity_verified=false`) | `fp_matrix.json` E4; `deployment.py:233` |
| N-2 | NIMClient cache key ignores `enable_thinking`/`reasoning_budget` (MEDIUM served HIGH's cached answer) and strips timestamps/UUIDs/dates (distinct prompts share an answer for up to 300 s) | `unauth/result.json`; `nim_client.py:278-332` |
| N-3 | Opt-in `test_p1_04_ready_with_reachable_database` is stale (fails unless `PGHOST`/`PGPORT`/`POSTGRES_PASSWORD` are also set); hidden by the CI skip | §28 |
| N-4 | MCP readiness "reachable" is a TCP connect; a wrong service reads READY until the circuit opens | `ready_matrix.json` |
| N-5 | Production-reachable `react-router` moderate advisory (open redirect) | `npm_audit.json` |
| N-6 | `npm run build` fails with `CI=true` (warnings → errors); CI does not run the build | `ui/build.log` |
| N-7 | Internal token compared with `!=` (not constant-time) | `inference.py:322` |
| N-8 | Oversize upload returns 500 wrapping 413 | `doc/result.json` |
| N-9 | Runbook needs "a running OpenShell gateway" with no step; `reference_governed` has no documented MCP server launch | §7, §22 |
| N-10 | `scripts/setup/cleanup_for_testing.sh` kills by process name (`npm start`, `uvicorn.*app:app`), next to the reference setup scripts | code |
| N-11 | `.env.example` defaults `MAIW_API_PORT=8001`, `PGPORT=5435`, `MAIW_API_HOST=0.0.0.0`; preflight, readiness and `sql_retriever` default `PGPORT` to 5435, which collides with the dev and foreign services on shared hosts | code |
| N-12 | `embedding_service` is loaded by the shipped app and calls an embedding NIM outside the approved-deployment table (no mounted route found that invokes it); `evaluate_with_model(allow_out_of_policy=True)` skips the resolver (no production caller) | `route_inventory.json` |

## 54. New P0 Findings

None.

## 55. New P1 Findings (§65)

| ID | Finding | Evidence |
|---|---|---|
| **NEW3-P1-01** | **Unauthenticated governed writes reachable from the untrusted sandbox and any network peer.** In `reference_governed` (READY, `governed_write_path: ready`), the fresh sandbox, holding **no credential**, sent `POST /api/v1/equipment/release`. The DecisionEngine auto-approved it (LOW) and `EquipmentActionExecutor` called the `warehouse.equipment.release` MCP write tool (`executed: true`). The same happened in the default `reference` profile when the documented-optional `MAIW_MCP_SERVER_EQUIPMENT_URL` was set, while readiness reported `governed_write_path: not_offered`. Root causes: (1) the policy template allows `access: full` to the API host:port, although its own comment says the only egress is `POST /api/v1/inference`; (2) the equipment write routes have no authentication or authorization dependency; (3) `bootstrap.py` builds executors whenever an MCP URL is set, independent of profile. The write-denial invariant (§48; `ALWAYS_DENIED {WRITE, EMERGENCY_WRITE}` at capability level) is bypassed at the network level. PR #144 graded this mechanism P2-05 "would be P1 if a working MCP backend were configured"; round 2 now ships a supported profile with exactly that. | `.third-logs/sbx_write.json`, `.third-logs/sbx_write_reference_profile.json`, `.third-logs/mcp/writes.jsonl`; `apps/api/maiw_api/routers/equipment.py:408-538`; `apps/api/maiw_api/bootstrap.py:386-410`; `deploy/openshell/maiw-inference-only.policy.yaml.tmpl:40` (`access: full`) |
| **NEW3-P1-02** | **An ambiguous write on the real MCP transport is reported as FAILED/not-executed, cannot be reconciled outside demo mode, and is duplicated on retry.** With `reference_governed` and a real streamable-HTTP equipment MCP server, a release whose write landed before the server crashed was returned as `status: failed, executed: false` (`physical_mutation_occurred=False`), not UNKNOWN. `/api/v1/demo/reconcile` → 503 outside demo. An identical operator retry executed a **second** write. Only the test-double `AmbiguousWriteError` produces UNKNOWN; no production code raises it, so every post-send transport error is FAILED. §49 ("UNKNOWN → authoritative reread → reconcile; no second consequential write before reconciliation") and §50 ("one actual write; no duplicate") fail for the only non-demo governed profile. | `.third-logs/unknown/result.json`; `packages/maiw-execution/maiw_execution/base.py:336-385`; `apps/api/maiw_api/routers/demo.py:1163-1186` |

## 56. Merge Recommendation

**Do not merge PR #143 as v2.0.1 in its current state.** The nine P1s it targets are genuinely closed, and the rest of the candidate is strong. Two narrow fixes are needed before re-audit. A docs-only "reference_governed not supported" waiver is an alternative for NEW3-P1-02, but **not** for the sandbox reachability in the default profile.

1. **NEW3-P1-01:**
   * Restrict the sandbox policy to `POST /api/v1/inference` (OpenShell L7 rules) instead of `access: full`.
   * Require authentication on governed write routes.
   * Wire executors only when the profile offers governed writes, so readiness and behaviour agree.
2. **NEW3-P1-02:**
   * Classify post-send transport or timeout errors on write tools as `UNKNOWN` (raise `AmbiguousWriteError` in the MCP write skill path).
   * Forward a stable `execution_id`/idempotency key to the backend.
   * Expose reconciliation outside demo mode, or block re-execution of the same intent while an UNKNOWN is unreconciled.

## 57. Post-Merge Release-Gate Recommendation

Do not tag `v2.0.1` from this candidate. After the two fixes:
* re-run this audit's NEW3-P1-01 probe (sandbox POST release → 403/blocked, 0 MCP writes);
* re-run the NEW3-P1-02 probe (crash-after-write → UNKNOWN, reconcile available, retry blocked or idempotent);
* re-run the live identity and runbook sequence on the new frozen SHA;
* update the release notes (§50).

## 58. Audit Artifacts (§66)

* This report: `docs/audits/MAIW_V2.0.1_THIRD_INDEPENDENT_REAUDIT.md`
* JSON: `artifacts/audit/v2.0.1_third_independent_reaudit.json`
* Branch: `audit/v2.0.1-third-independent-reaudit`, from `main` `944507e`. It contains only these two files.
* Probes and logs are not committed and remain on the host:
  * `/home/nvidia/maiw-v201-third-reaudit/.third-probes/`
  * `/home/nvidia/maiw-v201-third-reaudit/.third-logs/`
* **Cleanup:**
  * sandbox `maiw-v201-third-a` deleted (runbook script);
  * DB container `maiw-v201-third-db` removed (runbook script);
  * `maiw-v201-third-testpg` removed;
  * audit gateway `maiw-v201-third-gw` stopped and its JWT keys deleted; network `maiw-v201-third-net` removed;
  * all audit app, fake-provider, MCP, decoy and connwatch processes stopped;
  * `data/uploads` and the runbook `.env` deleted.
* **Untouched:**
  * all user containers (`nemoclaw-llama-cpp`, `nemo-microservices-*`, `wms-nim-*`, `cuopt`, `wosa-*`);
  * the `maiw-qual-20c-b` container;
  * the `nemoclaw-8991` gateway and its configuration;
  * port 5435 and 8000–8020.
* The post-audit listener set equals the pre-audit set, except the transient foreign `:3000`, which vanished on its own.

## 59. Final Verdict

* The exact frozen SHA was unchanged throughout.
* Full preflight passed with no skip, and the live sandbox qualification passed.
* All nine P1s are closed, and there is no P0.
* **Two new P1s** (NEW3-P1-01, NEW3-P1-02) mean §68 requires FAIL.

`MAIW V2.0.1 THIRD INDEPENDENT RE-AUDIT FAIL`
