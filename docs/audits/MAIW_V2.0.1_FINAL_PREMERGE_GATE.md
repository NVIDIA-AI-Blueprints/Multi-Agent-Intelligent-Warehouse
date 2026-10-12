# MAIW v2.0.1 — Final Pre-Merge Gate (PR #143)

| | |
|---|---|
| Scope | Close the fifth re-audit's last duplicate-write edge case (NEW5-P2-01), run the targeted release-critical regressions and normal CI, freeze PR #143. Not a new independent audit. |
| PR / branch | #143, `fix/v2.0.1-canonical-app-remediation` (NVIDIA-AI-Blueprints) |
| Starting SHA | `42b290f561ca4b7d9dea7cb12bd14c872de6e71d` |
| Final code commit | `5d4d60b` (tests); fix `64422a8`; docs `8c9460d`; this artifact is the last commit of the frozen head |
| `nvidia/main` | `944507ec914665c6682d39b95e8713355f486598` |
| `v2.0.0` | unchanged — tag object `0c35a0e9…`, target `816ace73c4561469978094eeedb2641f6db3c4fa`; no `v2.0.1` tag |
| Historical audit PRs | #142, #144, #145, #146 not touched; the fifth re-audit branch / worktree not touched |
| Hosted Super / Lightning | **real hosted Super/Lightning proof deferred to post-merge/pre-tag release gate** |

Earlier verdicts (rounds 1–4, the fifth re-audit) are not rewritten here.

## 1. Source identity (§0)

At start: PR #143 OPEN, head `42b290f`, worktree clean, `MERGEABLE`
(`UNSTABLE` only because of the code-scanning "Trivy" check), 9 review threads
all resolved. CI on `42b290f`: Test & Quality Checks, Security Scan, CodeQL
(python, javascript-typescript) pass; Semantic Release skipped; Trivy fail
(inherited, §15). Package provenance re-proved in the worktree venv: every
`maiw_*` distribution (`maiw_mcp`, `maiw_execution`, `maiw_skills`,
`maiw_contracts`, `maiw_api`, `maiw_models`, `maiw_decision`, `maiw_agents`,
`maiw_state`, `maiw_world`) and `mcp_servers` import from
`/home/nvidia/maiw-v201-remediation/…`.

## 2. Final safety fix — contradictory `NOT_APPLIED` (NEW5-P2-01)

The fifth re-audit reproduced two payloads that were certified as definite
non-execution, after which the operator retry wrote a second time:

* `isError` + `structuredContent = {execution_disposition: NOT_APPLIED,
  mutation_status: applied, outcome: executed, rejection_code: BOGUS}`;
* a non-error result `{success: true, outcome: failed,
  execution_disposition: NOT_APPLIED, …}`.

Root cause: `certifies_not_applied` checked only the disposition string; the
non-error path in `BaseActionExecutor` used the same check and never looked
at `success`, mutation references or unknown fields (and contract validation
in the skills drops unknown fields before the executor sees them).

Changes (`64422a8`):

* `maiw_mcp/write_disposition.py` — strict predicates
  `certifies_not_applied` (error result) and `certifies_not_applied_result`
  (non-error write result), `not_applied_violations` (log-safe reasons),
  `claims_not_applied`, `KNOWN_REJECTION_CODES`; `describe_disposition`
  reports `untrusted_not_applied:<reasons>`; `not_applied_payload` refuses an
  unknown rejection code.
* `maiw_mcp/client/client.py` — the error path uses the strict predicate; a
  NON-error result whose non-null `execution_disposition` is not a trusted
  NOT_APPLIED raises the new `MCPResultOutcomeUnknown` (an `MCPContractError`
  and `MCPDispatchOutcomeUnknown`), checked on the raw result before contract
  validation can drop fields.
* `maiw_execution/base.py` — `classify_write_failure(MCPResultOutcomeUnknown)`
  → `UNKNOWN / SERVER_RESULT_CONTRADICTORY`, dispatch status
  `dispatched_response_received`; the non-error path applies the strict
  result predicate itself (defence in depth for in-process skills) and maps
  any present-but-untrusted disposition to `SERVER_RESULT_CONTRADICTORY`.
* No server change: the shipped equipment (PostgreSQL adapter and mock),
  labor and wave MCP servers already emit only canonical payloads
  (`not_applied_result`, and contract results with null references).

## 3. Trusted `NOT_APPLIED` contract (§3)

**Error result** (`isError = true`) — trusted only if ALL hold:

1. `structuredContent` is a JSON object;
2. `execution_disposition` is exactly the string `"NOT_APPLIED"` (no str subclass, case, padding);
3. `rejection_code` is present, a `str`, and exactly one of `INVALID_REQUEST`, `NOT_FOUND`, `PRECONDITION_FAILED`;
4. `message`, if present, is a `str`;
5. there is **no other key** — `outcome`, `success`, `executed`, `mutation_status`, `rows_affected`, `mutation_count`, `post_state`, `result` or any unknown key refuses the certification.

**Non-error write result** — trusted only if ALL hold:

1. a JSON object with `execution_disposition` exactly `"NOT_APPLIED"`;
2. `success` present and exactly `False`;
3. `outcome` present and exactly `failed`, `conflict` or `deferred` (the typed rejection of this shape);
4. `rejection_code`, if present, a `str` in the known set;
5. `assignment_id`, `maintenance_id`, `allocation_id`, if present, are `null`; `tasks_updated`, if present, is the integer `0`;
6. echoes `proposal_id`, `decision_id`, `execution_id`, `source`, `message`, `task_id`, `wave_id`, `new_priority` are `str` or `null`; `worker_ids` is a list of `str`;
7. **no key outside** that write-result contract set.

A non-error result with a non-null disposition that fails these rules is
contradictory → UNKNOWN. Message strings are never inspected.

## 4. UNKNOWN fallback, retry blocking, reconciliation (§4–§6)

| Case | Path | HTTP / status | error_code | Retry | Physical writes | Reconcile |
|---|---|---|---|---|---|---|
| A `executed=true` | error | 202 unknown | `MCP_TOOL_ERROR` | 409 | 1 | `confirmed_executed` |
| A `executed=true` | non-error | 202 unknown | `SERVER_RESULT_CONTRADICTORY` | 409 | 1 | `confirmed_executed` |
| B `rows_affected` | error / non-error | 202 unknown | as above | 409 | 1 | `confirmed_executed` |
| B `tasks_updated=3`, `assignment_id=41` | non-error | 202 unknown | `SERVER_RESULT_CONTRADICTORY` | 409 | 1 | `confirmed_executed` |
| C `success=true` + `post_state` | error | 202 unknown | `MCP_TOOL_ERROR` | 409 | 1 | `confirmed_executed` |
| C fifth-audit exact (`mutation_status=applied`, `outcome=executed`, `BOGUS`) | error | 202 unknown | `MCP_TOOL_ERROR` | 409 | 1 | `confirmed_executed` |
| C fifth-audit exact (`success=true`, `outcome=failed`) | non-error | 202 unknown | `SERVER_RESULT_CONTRADICTORY` | 409 | 1 | `confirmed_executed` |
| C `success=true`, `outcome=executed`; `post_state` | non-error | 202 unknown | `SERVER_RESULT_CONTRADICTORY` | 409 | 1 | `confirmed_executed` |
| D code missing / `BOGUS` / lower-case / `409` (int) / unknown field | error | 202 unknown | `MCP_TOOL_ERROR` | 409 | 1 | `confirmed_executed` |
| D `rejection_code=BOGUS` / unknown field | non-error | 202 unknown | `SERVER_RESULT_CONTRADICTORY` | 409 | 1 | `confirmed_executed` |
| contradictory, nothing written (error and non-error fifth-audit payloads) | both | 202 unknown | as above | 409 | 0 | `confirmed_not_executed`; a new request then writes once |
| contradictory, reread down (error A, non-error B) | both | 202 unknown | as above | 409 (still) | 1 | `indeterminate`, then `confirmed_executed` once the backend is back |
| contradictory UNKNOWN → API restart | non-error | 202 unknown | `SERVER_RESULT_CONTRADICTORY` | 409 after restart, 0 new proposals | 1 | `confirmed_executed` |
| **E** clean `isError` NOT_APPLIED (shipped `not_applied_result`) | error | 200 failed, `executed=false` | `MCP_TOOL_NOT_APPLIED` | not blocked; next request writes once | 0 | 409 (not needed) |
| **E** clean non-error `conflict` + NOT_APPLIED | non-error | 200 conflict, `executed=false` | — | not blocked | 0 | — |

Every contradictory row: journal record `unknown`, `physical_mutation_occurred=null`,
`server_disposition=untrusted_not_applied:<reasons>`, `/ready` unresolved 1
until reconciled; the identical retry is refused with `409
RECONCILIATION_REQUIRED` before any proposal, decision or MCP call (backend
write-log entries unchanged). Physical write count ≤ 1 in every case.

Negative control: with the fix files reverted to `42b290f` and the new tests
kept, **18 of 18** A–D integration variants fail (answered `200 failed` /
`MCP_TOOL_NOT_APPLIED`) and both E variants pass.

## 5. Permanent regression tests (§7)

* `tests/api/test_final_contradictory_not_applied.py` — 26 tests: canonical
  app, real `MAIWMCPClient`, real streamable HTTP, the repository's equipment
  MCP server as a separate process (`tests/api/round3_mcp_backend.py`, new
  `contradict_after_write:` / `contradict_before_write:` modes), durable JSON
  journal; plus the real client + executor + journal without HTTP.
* `tests/unit/test_final_not_applied_strict.py` — 73 tests: predicate
  matrices for both shapes, executor non-error path (equipment / labor /
  wave), classification, and the shipped equipment / labor / wave MCP
  servers (demo simulation providers, real tool functions, real client)
  whose genuine pre-mutation rejections (`NOT_FOUND`, `INVALID_REQUEST`, non-
  error `conflict` / `deferred`) still certify.

## 6. Real MCP regression (§8) — 214 passed

`tests/api/test_round3_unknown_writes.py`, `test_round4_server_error_writes.py`,
`test_final_contradictory_not_applied.py`, `test_round4_pg_equipment_mcp.py`
(opt-in PG, run), `tests/unit/test_round4_write_disposition.py`,
`test_final_not_applied_strict.py`, `tests/unit/reliability/test_ambiguous_write.py`:

1. lost response after mutation → UNKNOWN `MCP_RESPONSE_LOST`, 409, `confirmed_executed`, 1 write — pass;
2. mutation then server error → UNKNOWN `MCP_TOOL_ERROR`, 409, `confirmed_executed` (JSON backend and shipped PG server) — pass;
3. explicit clean NOT_APPLIED → `failed`, 0 writes, not blocked — pass;
4. contradictory NOT_APPLIED → UNKNOWN (18 variants) — pass;
5. retry while UNKNOWN → 409, no MCP call — pass;
6. reconciliation → `confirmed_executed` / `confirmed_not_executed` / `indeterminate` — pass;
7. crash / restart after UNKNOWN (lost response, server error, contradictory, write in flight) → still blocked, reconciles — pass.

No duplicate write in any test.

Shipped equipment MCP server on a disposable PostgreSQL 16 (own container,
own port, removed afterwards), real client over streamable HTTP: release
without assignment and assign of a non-available asset →
`MCPToolNotApplied(PRECONDITION_FAILED)`; assign / release / maintenance of
an unknown asset → `MCPToolNotApplied(NOT_FOUND)`; DB unchanged, 0 writes.

## 7. Postgres transaction regression (§9)

Opt-in tests against the disposable PostgreSQL (`MAIW_TEST_PG_DSN`, schema
from `data/postgres/000_schema.sql` + `001_equipment_schema.sql`):
`test_round4_equipment_transactions.py` 29/29 (incl. the three
`test_pg_second_statement_failure_rolls_back_first[assign|release|emergency_maintenance]`:
a real `BEFORE UPDATE` trigger error in the second statement rolls back the
first; snapshot equal; a clean write then commits fully) and, with the
documented `PG*` variables, `test_canonical_shipped_app.py` +
transactions 82/82.

## 8. Sandbox write-boundary regression (§10)

Live, remediation-owned only: own OpenShell gateway `maiw-v201-fin-gw`
(127.0.0.1:19787, via `scripts/setup/reference_gateway.sh`, scratch HOME),
reference DB `maiw-v201-fin-db` (`reference_db.sh`), canonical app
`reference_governed` on 19781 (`start_reference_deployment.sh`, env file in
scratch space, `MAIW_REQUIRED_MCP_DOMAINS=equipment`), the repository's
equipment MCP server with the durable recording backend on 19784, a local
controlled OpenAI-compatible provider on 19789 (`NVIDIA_API_KEY` held a
non-credential placeholder). Preflight 32/0; status USABLE; smoke PASSED.

| Sandbox | Policy | Inference (LOW / MEDIUM / HIGH) | 16 write attempts (4 routes × 4 credentials) | `/ready` from sandbox |
|---|---|---|---|---|
| `maiw-v201-fin-a` | shipped L7 inference-only | 200 lightning / super / super, `identity_verified=true` | **16 × 403 at the proxy** | 403 (proxy) |
| `maiw-v201-fin-b` | deliberately permissive (`access: full` on the API port) | 200 lightning / super / super, `identity_verified=true` | **12 × 403 + 4 × 401 from app auth** | 200 (reaches the app) |

Counters across both sandboxes: DecisionEngine events 0 → 0, executor events
0 → 0, journal records 0 → 0, MCP write-log entries 0 → 0, backend state
hash `c51785fa94b2483f` unchanged. Sandbox environment secret names `[]`;
host secrets present in the sandbox: none. Direct provider and internet
blocked, metadata 403.

Positive control (operator credential, live, contradictory error payload
`err_C_fifth_audit_exact` on FL-01): 202 `unknown` `MCP_TOOL_ERROR`,
`server_disposition=untrusted_not_applied:…`; DecisionEngine 0 → 1, executor
0 → 1, MCP writes 0 → 1, hash changed; retry 409
`RECONCILIATION_REQUIRED` (no new write); reconcile `confirmed_executed`;
`/ready` unresolved 0.

## 9. Operator write auth, provider identity, cache, readiness (§11–§12)

* Operator auth / rate limit / router: `test_round3_write_auth.py`,
  `test_round4_rate_limit.py`, `test_equipment_router.py` — 27 passed; smoke:
  no credential 403, inference token 403, inference token as operator 401,
  operator + empty body 422.
* ModelGateway / provider identity / cache: `test_round2_model_identity.py`,
  `test_round3_identity_and_cache.py`, `test_round4_identity_before_cache.py`,
  `test_round2_deployment_resolver.py`, `tests/unit/deployment`,
  `test_model_gateway.py`, `test_model_gateway_fallback_policy.py`,
  `test_model_gateway_adapter_contract.py` — 253 passed (approved physical
  model, bad env override, missing / mismatched / malformed provider ID fail
  closed, failed identity never cached, LOW / HIGH cache separation).
* Readiness: `test_round2_readiness.py` 20 passed. Live: healthy 200;
  DB stopped → 503 `database`; required equipment MCP stopped → 503
  `governed_write_path`, `mcp_domains`; `/live` 200 throughout; 200 again
  after both were restored.

## 10. Test-order regression (§13)

| Order | Result |
|---|---|
| ModelGateway (`tests/unit/test_model_gateway*.py`) → demo (`tests/unit/demo`) | 558 passed |
| demo → ModelGateway | 558 passed |
| canonical (`tests/api`) → reliability (`tests/unit/reliability`) | 622 passed, 4 skipped |
| reliability → canonical | 622 passed, 4 skipped |

(`tests/api` includes the 26 new real-MCP tests; 596 + 26 = 622.)

## 11. Python tests (§14)

CORE CI command and ignore list from `.github/workflows/ci-cd.yml`
(`DATABASE_URL` pointed at an unused local port; nothing listens on 5435):

| Run | Tree | Result |
|---|---|---|
| 1 | `5d4d60b` (fix + tests) | **3089 passed, 13 skipped, 0 failed** (8 min 29 s) |
| 2 | `8c9460d` (+ docs) | **3089 passed, 13 skipped, 0 failed** (8 min 27 s) |

Round-4 baseline 2990 + 99 new tests = 3089. `black --check tests`: clean.

Skips are the opt-in ones only (PostgreSQL `MAIW_TEST_PG_DSN` ×6 — run
separately above —, real-NIM `MAIW_PHASE20B_NIM_URL` ×3, OpenShell runtime
qualification ×1, `MAIWSkillAdapter` ×1, legacy migration suite ×1).

## 12. UI (§15)

Jest 40 suites, 968/968; ESLint 0 errors (1043 warnings, unchanged
category); `tsc --noEmit` 0 errors; production build OK ("Compiled with
warnings"; output to scratch). No UI file changed in this cleanup.

## 13. pip-audit (§16)

pip-audit 2.10.1 (separate venv): worktree environment (161 pinned,
`--no-deps`) — no known vulnerabilities; `requirements.txt` resolved — no
known vulnerabilities.

## 14. Release notes (§18)

`RELEASE_NOTES_v2.0.1.md`: status after the fifth re-audit and this
cleanup; contradictory `NOT_APPLIED` now fails safe to UNKNOWN; hosted
Super / Lightning proof is a mandatory post-merge / pre-tag gate; no release
qualification claim. `docs/architecture/MCP.md` and the runbook's
write-outcome section document the strict contract.

## 15. Trivy inherited-security-debt status (§17)

The CI "Trivy" check is the code-scanning comparison and was already red on
`42b290f`. The fifth re-audit's same-session pinned comparison (Trivy 0.75.0,
same DB, `fs` scan of `git archive` trees): `main` 944507ec 3 critical / 67
high vs candidate 42b290f 0 critical / 12 high; candidate-only findings = 3
MEDIUM (`postcss-selector-parser`, `react-router` ×2) → **TRIVY
NON-REGRESSION PASS — INHERITED FINDINGS**. This cleanup changes only Python
and Markdown files (`git diff --name-only 42b290f..HEAD`: 5 package modules,
3 test files, 3 docs, this artifact) — no lockfile, `requirements.txt` or
`package.json` change. No security setting changed, no alert dismissed, no
`npm audit fix --force`.

## 16. Findings

* New P0: none. New P1: none.
* NEW5-P2-01: **closed** by this cleanup.
* Accepted contract assumption (not a finding): a server that emits a fully
  consistent canonical NOT_APPLIED after it actually mutated cannot be told
  apart by any schema check; the contract's server rule (emit only on
  pre-write paths) and the shipped servers' compliance carry it.
* Behaviour note: a non-error write result carrying any non-null
  `execution_disposition` other than a trusted NOT_APPLIED (e.g. `"APPLIED"`
  next to `executed`) is now UNKNOWN instead of being ignored; no shipped
  server emits one.
* Remaining P2 / observations (unchanged scope): NEW5-P2-02 (managed
  gateway inherits `.env` secrets), NEW5-P2-03 (rate limiter trusts loopback
  `X-Forwarded-For`), NEW5-OBS-04 (duplicate operator header: first wins),
  NEW5-OBS-05 (`CI=true` UI build fails on lint warnings); carried P2-04 rest
  (upload), P2-06, NEW4-P2-02 (reconciliation infers causality), NEW4-P2-03
  rest (no labor / wave launch entry), NEW4-P2-05 (`CIRCUIT_OPEN` until
  traffic), the round-4 wave / maintenance observations, P2-09/10/14/15/16/18/20,
  N-3…N-12, R3-O*.

## 17. Host isolation and cleanup

Pre-existing listeners (22, 53, 3000, 8002, 8010, 8080, 9000, 32768–32775),
containers (`nemo-microservices-*`, `wms-nim-*`, `wosa-*`, `cuopt-*`,
`nemoclaw-llama-cpp`, the `maiw-qual-20c-b` sandbox container), networks and
the `nemoclaw-8991` gateway were not touched. Every `openshell` call targeted
`http://127.0.0.1:19787` with a scratch HOME. Created and removed: gateway
`maiw-v201-fin-gw` + network `maiw-v201-fin-gw-net`, sandboxes
`maiw-v201-fin-a` / `maiw-v201-fin-b`, containers `maiw-v201-fin-db`,
`maiw-v201-fin-pg`, the API / MCP / provider processes. Fresh random tokens
and passwords in a 0700 scratch directory, never printed; no `.env` in the
worktree; `MAIW_INFERENCE_ALLOW_UNAUTHENTICATED` never set; no NVIDIA
credential searched for, read or used; no hosted call.

## 18. CI / review gate (§20–§21)

Local CI-equivalent gates on the final code: `black --check tests` clean;
CORE CI pytest twice green; Jest / ESLint / `tsc --noEmit` / build green.
GitHub CI on the starting head `42b290f`: all required checks green, Trivy
red (inherited, §15). The CI result, review-thread count and mergeable state
of the frozen head (the commit that adds this file) are recorded in the PR
#143 hand-off; nothing is pushed after the freeze. No commit in this cleanup
carries a Co-Authored-By trailer.

## 19. Merge readiness (§22) and the post-merge / pre-tag gate (§23)

Merge-readiness conditions met locally: contradictory NOT_APPLIED fix passes;
targeted duplicate-write tests pass; prior safety regressions pass; Python
suite passes twice; UI / typecheck pass; no open P0 / P1. The absence of an
exact-candidate live hosted Super / Lightning proof does not block the
merge; it **does block tagging**.

Mandatory before tagging `v2.0.1` (not executed here): merged `main` SHA
identified; full CI green; full preflight PASS; smoke PASS; real hosted HIGH →
Nemotron 3 Super → 200 → `identity_verified=true`; real hosted LOW →
Nemotron 3.5 Lightning → 200 → `identity_verified=true`; Trivy
non-regression vs `main` acceptable; P0 = 0; P1 = 0.
