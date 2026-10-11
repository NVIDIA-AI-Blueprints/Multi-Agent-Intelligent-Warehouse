# MAIW v2.0.1 Remediation — Round 4

**Scope:** this round closes NEW4-P1-01, the one new P1 found by the fourth
independent re-audit of the frozen PR #143 candidate `6ad2cbf`. That audit is
`docs/audits/MAIW_V2.0.1_FOURTH_INDEPENDENT_REAUDIT.md` on branch
`audit/v2.0.1-fourth-independent-reaudit` (PR #146, head `9120aa9`), verdict
`MAIW V2.0.1 FOURTH INDEPENDENT RE-AUDIT FAIL`.

NEW4-P1-01: a server-reported MCP tool error after a mutation was classified
as a definite FAILED with `executed=false`, so an operator retry wrote twice.
It is closed at both layers:

* the MCP / execution-semantics layer;
* the shipped PostgreSQL equipment adapter.

This round also fixes the listed low-risk P2s. All earlier fixes are kept,
and a candidate is frozen for a fifth independent re-audit.

This document is remediation evidence, not an audit verdict. It does not edit:

* PRs #142, #144, #145 or #146, or their branches;
* `v2.0.0`;
* any earlier audit artifact.

Machine-readable companion: `artifacts/audit/v2.0.1_remediation_round4.json`.

| | |
|---|---|
| Repository | NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse |
| PR / branch | #143 / `fix/v2.0.1-canonical-app-remediation` |
| Starting head (audited by the fourth re-audit) | `6ad2cbf1b4b8233ce6ca8528692ebba8f97eb10c` |
| Last code commit | `ff8ede17e3c270c52b1fa336e230989c2c23af1f`. All live proofs, both full suites and the order permutations ran at this SHA. |
| Final frozen head | The commit that adds this file, or the later artifact-update commit. Both are recorded in the PR and the final report. |
| `main` at start | `944507ec914665c6682d39b95e8713355f486598` |
| `v2.0.0` | Tag object `0c35a0e` → `816ace73c4561469978094eeedb2641f6db3c4fa`. Unchanged; there is no `v2.0.1` tag. |
| PR #146 | `audit/v2.0.1-fourth-independent-reaudit` @ `9120aa93a618e9e7da8f527208a9d458b81607a5`. Open, read only, not modified. |
| Host | `epg-tme-smc-h100-02`, a shared qualification host |
| Date | 2026-10-11 |

---

## 1. Executive Summary

| Finding | Status | One line |
|---|---|---|
| **NEW4-P1-01** server error after mutation = FAILED → duplicate write | **CLOSED** | After dispatch, only a typed `execution_disposition = "NOT_APPLIED"` in `structuredContent` gives FAILED. Every other error or non-success result is UNKNOWN: journal unresolved, retry 409, reconcile. Live: 1 backend write. |
| Shipped Postgres adapter partial writes | **CLOSED** | Each multi-statement logical write runs in one asyncpg transaction (asset row locked). A second-statement failure rolls back the first, proven against a real PostgreSQL. |
| NEW4-P2-01 replay of FAILED answers `no_op` | fixed | Replay answers the original `failed` without writing. |
| NEW4-P2-03 shipped equipment MCP server unusable | fixed | The provider is initialised. `get_status` metadata is a dict. Governed smoke passed against PostgreSQL. |
| NEW4-P2-04 identity failures cached | fixed | A response is cached only after its identity matches the dispatched model. |
| NEW4-P2-06 pdfminer-six PYSEC-2026-1761 | fixed | `pdfplumber` 0.11.9 → `pdfminer.six` 20251230. pip-audit is clean. |
| P2-04 rate limiter swallows its own 429 | fixed | Real `429` + `Retry-After`. Internal limiter failure still fails open. |

* All eleven earlier P1s remain closed (§13).
* No new P0 or P1 is known to this remediation.
* Every live proof ran against the canonical shipped app `maiw_api.app:app`, using only remediation-owned infrastructure: gateway, sandboxes, databases, MCP backends and a local controlled provider.
* **The hosted Nemotron 3 Super / 3.5 Lightning live identity test was NOT RUN in this round** (§45 of the spec). No hosted credential was searched for, read or used.

## 2. Source Identity (§0) and Environment (§1)

* **Source identity.** PR #143 was OPEN at `6ad2cbf` with CI green and 0 unresolved review threads. PR #146 was OPEN at `9120aa9`. `v2.0.0` resolves to `816ace7`, and there is no `v2.0.1` tag.
* **Worktree.** Remediation worktree `/home/nvidia/maiw-v201-remediation`, with its own `.venv` (`include-system-site-packages = false`, so no user site).
* **Package provenance.** `maiw_api`, `maiw_mcp`, `maiw_execution`, `maiw_models`, `maiw_agents`, `maiw_contracts`, `maiw_skills`, `maiw_decision`, `maiw_state`, `maiw_world` and `mcp_servers` resolve to this checkout under `env -i`.
* **Live worktree.** The detached live worktree at `ff8ede1` had its own fresh `.venv`. All 10 packages resolved to that worktree.

## 3. NEW4-P1-01 Root Cause

* `MAIWMCPClient._call_tool` raised a plain `MCPToolError` for every `is_error` result.
* `classify_write_failure` mapped that to `FAILED / MCP_TOOL_ERROR / physical_mutation_occurred=False`, so:
  * the journal record was not unresolved;
  * the asset was not blocked;
  * reconciliation was refused (UNKNOWN only);
  * the operator's retry executed again.
* MCP `isError` reports a tool error. It does not say the tool made no side effects.
* The shipped Postgres adapter made the case realistic:
  * Each logical write was two independent statements.
  * Any exception became `success=false`, then `BackendUnavailable`, then MCP `isError`.
* The CI suite pinned the unsafe row: `tests/api/test_round3_unknown_writes.py`, `MCPToolError("x"): ("failed", False)`.

## 4. Explicit NOT_APPLIED Contract (§4, §5)

**Contract module:** `packages/maiw-mcp/maiw_mcp/write_disposition.py`.

A server certifies a rejection before any mutation only with an error result of this shape:

```
CallToolResult(isError=true,
               content=[TextContent(<same JSON>)],
               structuredContent={"execution_disposition": "NOT_APPLIED",   # required, exact
                                  "rejection_code": "INVALID_REQUEST" | "NOT_FOUND" | "PRECONDITION_FAILED",
                                  "message": "..."})
```

* **Client rule (`certifies_not_applied`).** The disposition is read only from `structuredContent`. Its value must be exactly the `str` `"NOT_APPLIED"`; a `str` subclass is rejected.
* **What never certifies:**
  * text content;
  * an exception name;
  * an HTTP status;
  * `isError` alone;
  * an absent, `null`, non-string, other-case, padded or unknown value;
  * a wrong key or a nested value.
* **Server rule.** Providers raise `maiw_mcp.errors.WriteNotApplied` (a `BackendUnavailable`) only on paths that provably ran no mutation. The equipment, labor and wave MCP write tools turn it into the result above. The equipment tools also answer an invalid write request that way, before the provider is called.
* **Non-error results.** A result whose outcome is `failed`, `conflict` or `deferred` is a definite non-execution only if it carries `execution_disposition = "NOT_APPLIED"`. That field is a new optional field on the five write-result contracts.

## 5. MCP Client Changes (§7) — `maiw_mcp/client/client.py`, `maiw_mcp/errors.py`

| Server / transport behaviour | Client raises | Base classes |
|---|---|---|
| connect / handshake fails, or circuit open | `MCPConnectFailed` / `MCPConnectTimeout` / `MCPCircuitOpen` | `MCPNotDispatched` |
| `tools/call` sent, then transport lost or timed out | `MCPResponseLost` / `MCPTimeoutAfterDispatch` | `MCPDispatchOutcomeUnknown` |
| `isError` + valid `NOT_APPLIED` | **`MCPToolNotApplied`** (`rejection_code`) | `MCPToolError` |
| `isError` without a valid disposition | **`MCPToolErrorOutcomeUnknown`** (`observed_disposition`) | `MCPToolError`, `MCPDispatchOutcomeUnknown` |
| result is not JSON / not an object | `MCPContractError` | — |
| success | parsed dict | — |

## 6. Execution Layer Changes (§6, §8) — `maiw_execution/base.py`

| Cause | Outcome | `error_code` | mutation | `dispatch_status` |
|---|---|---|---|---|
| `AmbiguousWriteError` | UNKNOWN | AMBIGUOUS_WRITE | True | dispatched_mutation_known |
| `WriteNotDispatched` (the request could not be built) | FAILED | NOT_DISPATCHED | False | not_dispatched |
| `MCPNotDispatched` | FAILED | MCP_NOT_DISPATCHED | False | not_dispatched |
| `MCPToolNotApplied` | FAILED | MCP_TOOL_NOT_APPLIED | False | rejected_before_mutation |
| `WriteNotApplied` (in-process provider) | FAILED | WRITE_NOT_APPLIED | False | rejected_before_mutation |
| any other `MCPToolError` | **UNKNOWN** | MCP_TOOL_ERROR | None | dispatched_server_error |
| `MCPDispatchOutcomeUnknown` / `MCPTimeout` | UNKNOWN | MCP_RESPONSE_LOST / MCP_TIMEOUT | None | dispatched_no_response |
| `MCPContractError` | UNKNOWN | MCP_RESPONSE_UNREADABLE | None | dispatched_unreadable_response |
| `CapabilityNotFound` / deadline expired | FAILED | NOT_DISPATCHED | False | not_dispatched |
| **anything else** | **UNKNOWN** (was FAILED) | EXECUTION_OUTCOME_UNKNOWN | None | unknown |
| result `failed` / `conflict` / `deferred` without `NOT_APPLIED` | **UNKNOWN** | SERVER_FAILURE_UNCERTIFIED | None | dispatched_response_received |
| result `success=false` with outcome `executed` / `no_op` | **UNKNOWN** | SERVER_RESULT_CONTRADICTORY | None | dispatched_response_received |
| result outcome `unknown` | UNKNOWN | SERVER_REPORTED_UNKNOWN | None (was False) | dispatched_response_received |
| result `failed` / `conflict` / `deferred` with `NOT_APPLIED` | that outcome | — | False | dispatched_response_received |
| result `executed` / `no_op` (success) | unchanged | — | True / False | dispatched_response_received |

**`isError=true` alone can never produce `executed=false`.**

## 7. Durable Journal, Retry Blocking, Replay (§9, §10)

* **Journal fields.** The journal (`JsonFileExecutionRegistry`, fsynced before dispatch) records:
  * `execution_id`, `proposal_id`, `decision_id`, the capability and the target;
  * the intended postcondition and the pre-write status (`expected_effect`);
  * the trace ID and timestamps;
  * new in round 4: `dispatch_status`, `server_disposition` and `uncertainty_reason`.
* **Where they appear.** The new fields are in the result, in `/api/v1/executions` and in the 202 response body.
* **Retry blocking.** An UNKNOWN target refuses every further write with 409 `RECONCILIATION_REQUIRED`, before any proposal, decision or write. This holds across restarts. No fresh idempotency identity is created for a repeated request.
* **Idempotency replay (NEW4-P2-01).**
  * Replaying a FAILED / CONFLICT / DEFERRED write answers the original outcome (`failed`, `executed=false`, `replayed: true`) and never `no_op`.
  * An unresolved UNKNOWN replays as `RECONCILIATION_REQUIRED`.
  * Only a reconciled CONFIRMED_EXECUTED replays as `no_op`.
  * An UNKNOWN therefore cannot be "replayed" into a success that hides it.

## 8. Equipment Postgres Transactions (§14–§17)

* **`SQLRetriever.transaction()`.** One pooled connection inside asyncpg's own `Connection.transaction()`: BEGIN on entry, COMMIT on a clean exit, ROLLBACK on an exception. The connection is released only after COMMIT or ROLLBACK.
* **Transactional writes.** `EquipmentAssetTools` runs every statement of these operations on that connection, with the asset row locked `FOR UPDATE`:
  * `assign_equipment`: INSERT assignment, then UPDATE asset;
  * `release_equipment`: UPDATE assignment, then UPDATE asset;
  * `schedule_maintenance`: INSERT maintenance, plus UPDATE asset for emergency maintenance.
* **Precondition rejections.** A rejection taken before any write (asset not found, not available, no active assignment) returns `mutation_status: not_applied` with a `rejection_code`. `MAIWEquipmentAdapter` maps only that to `WriteNotApplied`. Every other failure, including a rolled-back transaction, is a plain `BackendUnavailable`, which becomes UNKNOWN. This is deliberately conservative.

**Partial SQL failure evidence:**

| Check | Result |
|---|---|
| CI fake asyncpg pool (`tests/unit/test_round4_equipment_transactions.py`, 24 CI tests) | For each operation, a failure of write statement 1 or 2 gives ROLLBACK, no COMMIT, tables equal to the pre-write state, the connection reusable afterwards and `mutation_status` absent. A success gives exactly 1 BEGIN and 1 COMMIT. A write outside a transaction fails the test. Precondition rejections run 0 write statements. |
| Real PostgreSQL, opt-in `MAIW_TEST_PG_DSN` (3 tests; ran against disposable `maiw-v201-r4-testpg`, TimescaleDB 2.15.2-pg16) | A trigger raises a real SQL error in the second statement. For assign, release and emergency maintenance, the first statement is rolled back and the asset, assignment and maintenance rows equal the pre-write snapshot. The same pool then commits a normal write fully. |
| Mutation check | With the pre-round-4 `equipment_asset_tools.py` restored, 9 of these tests fail (partial writes survive). |

**§17.** Transactions do not replace UNKNOWN. An error after COMMIT is still UNKNOWN and is reconciled:

* opt-in test `test_commit_then_server_error_is_unknown_and_reconciles_executed`;
* live run in §10.

## 9. Real MCP Integration Coverage (§11–§13, §19–§23)

**Replaced unsafe test.** In `tests/api/test_round3_unknown_writes.py::test_failure_classification_table`:

* `MCPToolError → unknown`, `MCPToolNotApplied` and `WriteNotApplied → failed`, and `RuntimeError` / `BackendUnavailable → unknown`;
* reliability tests that treated an uncertified exception as proof of non-execution now use `WriteNotApplied` or `MCPConnectFailed` for the FAILED cases;
* new tests assert the UNKNOWN cases.

**`tests/api/test_round4_server_error_writes.py` (21 tests).** These run the canonical app (real lifespan, real `MAIWMCPClient`, streamable HTTP, real JSON journal) against the repository's equipment MCP server process. The recording backend `tests/api/round3_mcp_backend.py` gained round-4 modes.

| Case | Result |
|---|---|
| Mutation, then generic error | 202 `unknown`, `executed` null, `MCP_TOOL_ERROR`, `dispatched_server_error`. Journal unresolved with full identity, pre-status and uncertainty reason. `/ready` reports unresolved 1. Retry 409, 0 new proposals. Reconcile gives `confirmed_executed`. 1 write. |
| Same, then app process gone and restart | Journal kept, retry 409, reconcile `confirmed_executed`, 1 write |
| Generic error, no mutation | 202 `unknown` → `confirmed_not_executed` → new request writes once |
| Explicit `NOT_APPLIED` | 200 `failed`, `executed=false`, `MCP_TOOL_NOT_APPLIED`. Not unresolved; reconcile 409 (not needed). 0 writes. A new request writes once. |
| 13 malformed variants (none, no field, null, int, bool, list, nested, lowercase, padded, unknown value, `APPLIED`, wrong key, text-only claim) | All 202 `unknown`. The exact observed disposition is asserted, so the crafted payload reached the client. Retry 409, 1 write each. |
| Non-error `success=false, outcome=failed` after mutation | 202 `SERVER_FAILURE_UNCERTIFIED`, 409 |
| Non-error `conflict` + `NOT_APPLIED` | 200 `conflict`, not unresolved, 0 writes |
| Idempotency-Key replay of `NOT_APPLIED` | `failed` both times, same execution, 0 writes |
| Real client + executor + journal without HTTP | Typed `MCPToolNotApplied` / `MCPToolErrorOutcomeUnknown`. The UNKNOWN survives reopening the journal. |

**Other round-4 tests:**

* `tests/unit/test_round4_write_disposition.py` (68 tests): the contract table, classification, in-memory server decoding, executor result mapping, replay rules and the demo-provider certification.
* Mutation check: restoring `MCPToolError → FAILED` makes the first round-4 API test fail with `200 failed`.

## 10. Live Controlled Proof — Round-4 Security Matrix (§48)

**Setup:**

* canonical app `reference_governed` on 127.0.0.1:18981, started by `start_reference_deployment.sh` with `MAIW_ENV_FILE`;
* adversarial equipment backend: the repository's `mcp_servers.equipment.server` over streamable HTTP on 18984, with durable JSON state and a JSONL write log;
* labor / wave mock servers on 18985 / 18986;
* local controlled OpenAI-compatible provider on 18989;
* own OpenShell gateway `maiw-v201-r4-gw` on 18987;
* sandboxes `maiw-v201-r4-a` (L7 inference-only) and `maiw-v201-r4-b` (deliberately permissive);
* reference DB `maiw-v201-r4-db` on 55582.

| Case | Expected | Actual | Backend writes |
|---|---|---|---|
| Sandbox inference | allowed | 200 LOW→Lightning and HIGH→Super, `identity_verified=true` (L7 and permissive) | — |
| Sandbox write (L7) | denied | 24/24 → 403 at the proxy. DecisionEngine 11→11, executor 10→10, MCP writes 10→10, state hash unchanged. | 0 |
| Sandbox write (permissive policy) | denied by app auth | 16 × 403, 8 × 401. DecisionEngine 11→11, executor 10→10, MCP writes 10→10, state hash and journal unchanged. | 0 |
| Operator valid write (FL-01) | governed, executed | 200 `executed` | 1 |
| Server error after dispatch (FL-02, applied then raised) | UNKNOWN | 202 `unknown`, `executed` null, `MCP_TOOL_ERROR`; journal unresolved; `/ready` unresolved 1 | 1 |
| Explicit NOT_APPLIED (FL-03) | failed, not executed | 200 `failed`, `executed=false`, `MCP_TOOL_NOT_APPLIED`; unresolved false; reconcile 409 | 0 |
| Lost transport response (FL-04, crash after write) | UNKNOWN | 202 `unknown`, `MCP_RESPONSE_LOST` → reconcile `confirmed_executed` | 1 |
| Retry while UNKNOWN (FL-02) | blocked | 409 `RECONCILIATION_REQUIRED` | 1 (unchanged) |
| Reconcile landed write (FL-02) | CONFIRMED_EXECUTED | `confirmed_executed` / `effectively_executed` | 1 |
| Reconcile non-landed write (FL-05, crash before write) | CONFIRMED_NOT_EXECUTED | `confirmed_not_executed`, asset still `assigned` | 0 |
| Reconcile, backend unavailable (FL-06) | INDETERMINATE | `indeterminate`; retry 409; after the backend returned, `confirmed_executed` | 1 |
| Uncertified error, no mutation (FL-08) | UNKNOWN → not executed | 202 `MCP_TOOL_ERROR` → `confirmed_not_executed` | 0 |
| Replay of NOT_APPLIED (FL-09, same Idempotency-Key) | not a success | `failed` / `failed`, same execution | 0 |
| `kill -9` after server-error UNKNOWN (FL-10) | survives | Journal record `unknown`, `dispatched_server_error` on disk. API PID killed with `-9` and restarted with the start script. `/ready` unresolved 1, retry 409, reconcile `confirmed_executed`. | 1 |

* **Totals.** 6 applied backend writes, exactly one per asset that was meant to change (FL-01, -02, -04, -06, -07, -10). There was no duplicate write.
* **Deviation, recorded honestly.** The first `kill -9` attempt (FL-07) was a no-op: the PID check compared NUL-separated `cmdline` text, so the API was not killed, and FL-07 was reconciled without a restart. The `kill -9` proof was repeated on FL-10 with a verified kill.

## 11. Equipment MCP Provider, `get_status`, Governed Smoke (§29–§31)

* **Reproduced:**
  * the default provider built `EquipmentAssetTools()` without `initialize()`, so `sql_retriever` was None;
  * once initialised, asyncpg returned JSONB `metadata` as the string `'{}'`, which failed `EquipmentStatusResult` validation.
* **Fixed:**
  * the adapter initialises the tools once, lazily, inside the serving loop, under a lock;
  * `__main__` composes the shipped provider at startup;
  * `_as_metadata` decodes JSON strings to dicts, and anything else becomes `{}`;
  * the schema was not loosened.
* **Live smoke.** The real `python -m mcp_servers.equipment.server` ran on 18988, configured by `PGHOST`, `PGPORT` and `POSTGRES_*` against the reference DB. A `reference_governed` app on 18982 (`MAIW_REQUIRED_MCP_DOMAINS=equipment`) passed preflight 32/0.

| Step | Result |
|---|---|
| `/ready` | 200 READY; equipment domain READY / HEALTHY |
| `get_status` (all 12 assets) | validates against the contract; metadata type `dict` |
| HTTP release FL-02 (full pipeline) | 200 `executed`; DB `assigned` → `available`, assignment released |
| HTTP assign FL-01 | 200 `requires_human_approval` (governance; not executed) |
| Governed executor assign FL-01 | `executed`; DB `assigned` to `r4-op-7` |
| Governed executor emergency maintenance CHG-01 | `executed`; status `maintenance`; maintenance rows 1 → 2 |
| Pre-mutation rejection (release SCN-02, no active assignment) | `failed`, `MCP_TOOL_NOT_APPLIED`, `server_disposition=NOT_APPLIED`, mutation false, DB unchanged |
| Ambiguous server error (real DB trigger fails the second statement of the AGV-01 release) | DB unchanged (rollback). 202 `unknown` `MCP_TOOL_ERROR`, retry 409, reconcile `confirmed_not_executed`. After the trigger was dropped, a new request was 200 `executed` (`available`). |

## 12. P2 Fixes

**Rate limiter (§24, §25).**

* `check_rate_limit` re-raises its own `HTTPException(429)` before the fail-open handler.
* The canonical (and legacy) HTTP middleware answers it as a `JSONResponse`; an exception raised from middleware would otherwise surface as 500.
* An emptied in-memory bucket no longer lets a request through uncounted.
* Tests (`tests/api/test_round4_rate_limit.py`, 4):
  * 12 logins against the 5/min limit gave 5 non-429 responses and 7 × 429 with `Retry-After`, and no 500;
  * an internal limiter failure fails open (3 × 200);
  * health paths stay unlimited.
* Mutation check: the old limiter fails 3 of the 4 tests.

**Identity before cache (§26–§28).**

* `NIMClient` caches only when `provider_model == dispatched model`.
* Tests (`tests/api/test_round4_identity_before_cache.py`, 7):
  * for substituted, cross-role, missing, empty and malformed identities: 502, a second identical request calls the provider again, the fixed provider then gives 200 `identity_verified`, and the verified answer is then served from cache;
  * HIGH / MEDIUM / LOW stay isolated after a failure (provider calls Super, Super, Super, Lightning).
* Mutation check: the old client fails all 7.
* Live (§26 of the audit's matrix, cache enabled):
  * missing identity, then healthy with the same prompt: 502 then 200 with a fresh provider call (the audit saw 502, 502);
  * HIGH/LOW/HIGH/LOW gave provider calls 1,1,0,0, and every other sequence matches the audit;
  * prompts that differ only by a timestamp are not merged.

**Equipment MCP server:** §11.

**pdfminer-six.**

* `pdfplumber` 0.11.8 pinned `pdfminer.six==20251107`. 0.11.9 pins `20251230` (the fix) with unchanged Pillow / pypdfium2 constraints.
* `requirements.txt` was bumped; the full suite passes.
* pip-audit 2.10.1 (separate tool venv) reported no known vulnerabilities for both the remediation environment (161 pinned packages, `--no-deps`) and `requirements.txt` resolved (132 packages).

## 13. Regression of the Eleven Earlier P1s

| P1 | Origin | Evidence this round | Status |
|---|---|---|---|
| P1-01 ungoverned chat write | #142 | smoke: `/api/v1/chat` 404; sandbox L7 403; permissive 404; copilot turn ran no write (DecisionEngine / MCP writes unchanged) | CLOSED |
| P1-02 inference endpoint | #142 | smoke 401/401/422/422/200; in-sandbox 200 with verified identity | CLOSED |
| P1-03 durable stores | #142 | journal survived `kill -9` (§10); durability tests pass | CLOSED |
| P1-04 readiness false positive | #142 | readiness matrix below | CLOSED |
| P1-05 document MG bypass / mock APPROVE | #142 | canonical document tests pass (full suite) | CLOSED |
| NEW-P1-01 physical model identity | #144 | policy matrix: every override gives `/ready` 503, inference 503 `MODEL_POLICY_VIOLATION`, 0 provider calls; provider substitution 502 | CLOSED |
| NEW-P1-02 runbook reproducibility | #144 | clean-shell runbook (§15) | CLOSED |
| NEW-P1-03 readiness vs governed writes | #144 | governed readiness rows below | CLOSED |
| NEW-P1-04 test order | #144 | §16 | CLOSED |
| NEW3-P1-01 sandbox → write routes | #145 | §10 rows 2–3; `reference_sandbox.sh probe` all denied; operator token absent from the sandbox (`env_secret_names: []`) | CLOSED |
| NEW3-P1-02 ambiguous transport write | #145 | §10 FL-04 / FL-05 / FL-06, `kill -9`; 1 write each | CLOSED |
| **NEW4-P1-01 server error after mutation** | #146 | §3–§10 | **CLOSED** |

**Provider identity, live (16 cases).**

| Provider reports | Result |
|---|---|
| exact (high, low) | 200, `identity_verified=true` |
| other string, unicode look-alike, upper case, cross-role ×2, unknown, `-v2` suffix | 502 `MODEL_IDENTITY_MISMATCH` |
| missing, `""`, `"   "`, null / int / list / dict | 502 `MODEL_IDENTITY_UNVERIFIABLE` |

Every case made exactly 1 provider call, always to the resolved approved ID. No successful response had `identity_verified=false`.

**Readiness, live (fresh instances).** `/live` was 200 in every row.

| Configuration | `/ready` | Failed component / write result |
|---|---|---|
| reference, sandbox disabled | 200 | — |
| reference, required sandbox Ready | 200 | — |
| reference, required sandbox absent | 503 | `sandbox_runtime` |
| reference, optional sandbox absent | 200 | — |
| reference + MCP URL + operator token | 200 | write 503 `GOVERNED_WRITES_NOT_OFFERED` |
| governed healthy | 200 | write 422 on an empty body |
| governed, write token missing | 503 | `governed_write_path`; write 503 `OPERATOR_WRITE_AUTH_NOT_CONFIGURED` |
| governed, token equals the inference token | 503 | `governed_write_path` |
| governed, required MCP unreachable | 503 | `governed_write_path`, `mcp_domains` |
| governed, required MCP unset | 503 | `governed_write_path`, `mcp_domains` |
| governed, optional inventory MCP unset | 200 | — |
| invalid profile | 503 | `profile` |
| DB unreachable | 503 | `database` |
| provider down | 200 | inference 503 |

## 14. Full Preflight (§38)

| Run | Result |
|---|---|
| reference | **32 passed, 0 failed, no skip** |
| governed (`MAIW_ENV_FILE`) | 34 / 0 |
| during restart | 32 / 0 |
| governed against the shipped equipment server (equipment only) | 32 / 0 |

Caveat: the provider probe targeted the local controlled provider.

## 15. Clean-Shell Runbook (§39)

Every step ran under `env -i` with a scratch `HOME` and `PATH=~/.local/bin:/usr/bin:/bin`, from the detached live worktree at `ff8ede1`, using only runbook commands.

| Step | Exit |
|---|---|
| 1 install: venv / requirements / 8-package loop / agents + api | 0 / 0 / 0 / 0 |
| 2 `cp .env.example .env` + the listed edits | 0 |
| `validate_reference_runbook.sh` | 0 |
| 3 gateway start / status | 0 / 0 |
| 4 `reference_db.sh up` | 0 |
| 5 `reference_sandbox.sh create` | 0 |
| 6 preflight (32/0) / start / status / smoke (17/17) | 0 / 0 / 0 / 0 |
| 7 `reference_sandbox.sh probe` (writes all denied; no host secret in the sandbox) | 0 |
| 8 restart (preflight 32/0) / status / smoke (17/17) / stop | 0 / 0 / 0 / 0 |
| status after stop | 1 (as designed) |
| governed: preflight 34/0 / start / smoke 18/18 / start after `kill -9` / stop | 0 / 0 / 0 / 0 / 0 |
| 9 sandbox delete / db down / gateway stop | 0 / 0 / 0 |

* **Deviation.** `MAIW_NIM_BASE_URL` and `LLM_NIM_URL` pointed at the local controlled provider (the runbook's local-NIM option). `NVIDIA_API_KEY` held a non-credential placeholder.
* **MCP backends.** These were launched by the remediation. The equipment server launch command is now documented; the labor and wave servers still have no shipped PostgreSQL entry point (P2).

## 16. Tests (§40–§44)

Each run was a separate process with the CORE CI selection and ignores, `--timeout=120`, under `env -i`, with a remediation-owned `DATABASE_URL` / `PG*` (127.0.0.1:55581) and no `.env`.

| Run | Result |
|---|---|
| Full run 1 | **2990 passed, 13 skipped, 0 failed** |
| Full run 2 | **2990 passed, 13 skipped, 0 failed** |
| ModelGateway → demo / demo → ModelGateway | 558 / 558 passed |
| canonical → reliability / reliability → canonical | 443 passed, 2 skipped (both) |
| reversed directories | 2990 / 13 / 0 |
| file shuffle, seed 4401 | 2990 / 13 / 0 |
| file shuffle, seed 5502 | 2990 / 13 / 0 |
| round-4 suites first | 2990 / 13 / 0 |
| opt-in PostgreSQL (`MAIW_TEST_PG_DSN`, disposable `maiw-v201-r4-testpg`): `test_round4_equipment_transactions.py` + `test_round4_pg_equipment_mcp.py` + `test_canonical_shipped_app.py` | **84 passed, 0 skipped** (the 5 round-4 opt-in tests and the 2 earlier opt-in canonical tests ran) |

* **Baseline at `6ad2cbf`:** 2865 / 8 / 0.
* **New:** 129 round-4 tests in 6 files plus 1 in `test_ambiguous_write.py`, so +125 passed in CI and +5 opt-in skips.
* **Stable skips (13):**
  * the 8 earlier skips: legacy migration; `MAIWSkillAdapter`; 3 × `MAIW_PHASE20B_NIM_URL`; 1 × OpenShell not on the test `PATH`; 2 × `MAIW_TEST_PG_DSN`;
  * plus 5 new `MAIW_TEST_PG_DSN` skips.
* **UI:**
  * `npm ci` OK;
  * Jest **968/968** (40 suites);
  * ESLint **0 errors** (1043 warnings);
  * `tsc --noEmit` **0 errors**;
  * `npm run build` OK (compiled with warnings);
  * Node 24.1.0 locally; CI uses 22.
* **npm audit (fresh):**
  * 0 critical, 50 high, 34 moderate, 3 low. `--omit=dev` is identical because the toolchain sits in `dependencies`.
  * All 50 highs are build or test tooling (jest, eslint / @typescript-eslint, react-scripts, webpack-dev-server, http-proxy-middleware, svgo / @svgr, tailwindcss, braces / micromatch / chokidar).
  * Production-reachable: `react-router` / `react-router-dom` are moderate only.
  * `--force` was not used.

## 17. Host Isolation and Cleanup (§46, §47)

* **Start inventory.** Listeners 22, 53, 3000 (an intermittent pre-existing restart loop), 32768 and 32769. User containers were treated as off-limits:
  * `nemoclaw-llama-cpp`;
  * `nemo-microservices-*`;
  * `wms-nim-*`;
  * `cuopt`;
  * `maiw-qual-20c-b`;
  * `wosa-*`.
* **Watcher.** A watcher polled `/proc/net/tcp{,6}` every 20 ms for the whole session:
  * off-limits set: 3000, 32768–32778, 5435, 8000–8020, 8080–8082, 8991;
  * **0 off-limits hits**;
  * private-address hits were only the remediation's own DB containers (172.17.0.2 = `maiw-v201-r4-testpg`, 172.17.0.3 = `maiw-v201-r4-db`) and the remediation gateway's sandbox network (172.23.0.x).
* **Remediation-owned ports:**
  * API 18981 / 18982;
  * gateway 18987;
  * MCP 18984–18986 and 18988;
  * provider 18989;
  * DBs 55581 / 55582;
  * closed probe ports 18992–18994.
* **OpenShell isolation.** Every `openshell` call used `OPENSHELL_GATEWAY_ENDPOINT=http://127.0.0.1:18987` and a scratch `HOME`. The user's `nemoclaw-8991` gateway was never touched.
* **Credentials.** No hosted credential was searched for, read or used. Tokens were fresh and random, held in 0600 files and never printed. `MAIW_INFERENCE_ALLOW_UNAUTHENTICATED` was never set. The operator token was absent from the sandbox.
* **Cleanup.**
  * Sandboxes `maiw-v201-r4-a` / `-b` deleted.
  * Gateway `maiw-v201-r4-gw` stopped and its network removed.
  * `maiw-v201-r4-db` removed.
  * `maiw-v201-r4-testpg` removed at the end of the session.
  * API instances, MCP backends and the provider stopped.
  * The live worktree (and its `.env`) removed.
  * No `.env` in the remediation worktree.
  * The final inventory equals the start inventory (see the final report).

## 18. Remaining P2 Findings (unchanged scope, documented for the fifth audit)

* **NEW4-P2-02.** Reconciliation infers causality from state.
  * The forwarded `execution_id` is not used by reconciliation.
  * The labor and wave strategies are weaker; there is no canonical HTTP write route for them.
  * When `pre_status` was not recorded, a mismatch still resolves to CONFIRMED_NOT_EXECUTED.
* **NEW4-P2-05.** Readiness shows `CIRCUIT_OPEN` until traffic probes the half-open circuit.
* **NEW4-P2-03 (remaining part).** The labor and wave MCP servers have no shipped PostgreSQL launch entry point.
* **P2-04 (rest).** Document upload is unauthenticated, a chunked upload can exceed 50 MB, and an oversize upload gives 500. Rate limiting is fixed.
* **P2-06.** Legacy unauthenticated reads.
* **Carried P2s:** P2-09, P2-10, P2-14, P2-15 (react-router moderate), P2-16, P2-18, P2-20, N-3, N-4, N-5, N-6, N-7, N-10, N-11, N-12 (document OCR / embedding outside ModelGateway), R3-O1, R3-O2, R3-O4, R3-O6, and the rest of N-9.
* **New observations from this round (P2 / observation):**
  * The wave PostgreSQL / WMS adapter reports `success=True` even when individual task updates fail (no canonical route).
  * The Postgres `schedule_maintenance` changes asset status only for `emergency`, while reconciliation expects `maintenance` for every maintenance write. This is reachable only through the demo approval route; the canonical maintenance route never auto-executes.

## 19. Fifth Re-Audit Readiness

The candidate is ready for a fifth independent re-audit at the frozen head recorded in the PR.

* **Hosted provider.** The fifth audit must still run the hosted Nemotron 3 Super / 3.5 Lightning identity proof. It needs a credential provided explicitly:
  * `read -s NVIDIA_API_KEY; export NVIDIA_API_KEY` in the parent shell;
  * the auditor verifies only `test -n "${NVIDIA_API_KEY:-}"` and never prints it.
* **What round 4 did not do.** It did not consume or persist that credential, and it makes no claim of hosted Super / Lightning proof.
