# SonarQube Security Findings: Triage and Remediation

| | |
|---|---|
| **Analysis triaged** | SonarQube project `TEGRASW_Blueprints-SRE_warehouse-operational-assistant_Multi-Agent-Intelligent-Warehouse`, last analysis **2026-01-05 22:01 UTC of `4df9a41`** (scope `src/` only). Read through the anonymous web API on 2026-11-02. |
| **Code triaged** | `main` at `0fbcb69` (after v2.1.0, `2fdd9fe`) |
| **Fresh analysis** | **Not yet available.** The scanner workflow is restored in #226, but a run needs an NVIDIA-network runner and an authorized token (see `sonarqube-root-cause-analysis.md`). The dispositions below are engineering dispositions. They must be confirmed against the first fresh analysis and recorded in SonarQube by a project administrator. |

**Method:**
- Each finding's source-to-sink flow, from the SonarQube API, was matched to current code by content, not by line number.
- For each one, I checked whether it is reachable in the shipped app (`maiw_api.app:app`): which routers are mounted, and which `route_policy` views drop which methods.
- Suspected log-forging sinks were probed by sending CR/LF payloads through the app's test client.

## Summary

| Category | Count | Current state |
|---|---|---|
| `pythonsecurity:S5145`, log of user-controlled data (MINOR, OPEN) | 11 | 1 already fixed; 6 reachable in the shipped app; 1 reachable but CR/LF already escaped; 3 not reachable. **All addressed in this change.** |
| The same pattern outside Sonar's scope (`apps/`, `src/api/utils`, auth) | 20+ sinks, incl. **credential exposure** | Addressed in this change: explicit fixes plus a process-wide guard |
| Closed issues (`secrets:S6698` ×5, `python:S5659`, `python:S6709`) | 7 | Confirmed fixed in current code |
| Security hotspots TO_REVIEW | 72 | 70 safe with evidence; 2 groups not safe by design but not reachable (clear-text credentials in optional WMS/IoT adapters). Hardening is tracked as follow-up. |

## 1. Log injection and sensitive data in logs (CWE-117, CWE-532)

### Highest impact: found during triage, outside the old Sonar scope

| # | Location | Problem | Reachable | Fix |
|---|---|---|---|---|
| A2 | `src/api/utils/error_handler.py`, the validation handler | Logged pydantic's `exc.errors()`. Its `input` is the request body, so `POST /api/v1/auth/login` without `username` **logged the password in plain text**. The same applied to change-password, register and profile updates. | Every route with a body, unauthenticated | Logs only `loc`, `msg` and `type` (the existing `_json_safe_validation_errors`), sanitized. |
| A1 | `error_handler.py`, the HTTP-exception handler | Logged `exc.detail` raw. About 20 routes put path or query values in details (equipment, safety policy, inventory, world, model lab…), so `GET …/POL-1%0d%0aFAKE` forged a log line. | Unauthenticated GETs | `sanitize_log_data(detail, 300)`. The generic-exception log is sanitized too. |
| A3, A4 | `src/api/routers/auth.py`, `src/api/services/auth/user_service.py` | Raw username logged before authentication, together with debug lines that logged its type and length. A crafted username forged "admin logged in successfully". | `POST /api/v1/auth/login` | A single sanitized `safe_username` (64 chars); the debug lines are removed. |
| — | `src/api/services/auth/jwt_handler.py` | Logged the `alg` value from the **unverified** JWT header. | Any authenticated auth route | `%r` of a sanitized value. |
| — | `src/retrieval/structured/sql_retriever.py` | On a DB error, logged the bound parameters: request values and row data, such as e-mail addresses. | Any SQL-backed GET | Logs the parameter count only. |

### The 11 SonarQube S5145 findings

| # | Sonar location (4df9a41) | Current location | Reachable in shipped app | Disposition |
|---|---|---|---|---|
| 1 | `src/api/graphs/mcp_integrated_planner_graph.py:1559` | `:1566`, now `sanitize_log_data(message, 100)` | No (only the unmounted chat and MCP routers import it) | **Fixed before this change** |
| 2 | `src/api/routers/advanced_forecasting.py:281` | unchanged | No: `POST /real-time` is dropped by `read_only_view`; shipped callers pass SKUs read from the DB | Not reachable; covered by the guard |
| 3 | `src/api/routers/equipment.py:322` (GET `/equipment/{asset_id}`) | Canonical `apps/api/maiw_api/routers/equipment.py`, "Failed to get equipment" | **Yes**, unauthenticated GET | **Fixed**: `sanitize_log_data(asset_id, 64)` |
| 4 | `equipment.py:382` (assign) | Canonical, "Failed to propose assignment" | Yes, after operator-token authentication | **Fixed** |
| 5 | `equipment.py:408` (release) | Canonical, "Failed to release equipment" | Yes, after operator authentication | **Fixed** |
| 6 | `equipment.py:445` (telemetry) | Canonical, telemetry and status | **Yes**, unauthenticated GET | **Fixed** (both sinks) |
| 7 | `equipment.py:481` (maintenance) | Canonical, "Failed to schedule maintenance" | Yes, after operator authentication | **Fixed** |
| 8 | `src/api/routers/inventory.py:101` (GET `/inventory/items/{sku}`) | unchanged | **Yes**, unauthenticated; a forged line was confirmed | **Fixed**. The message also said "equipment item" by mistake. The daily-demand sink at `:324` is fixed too, and its 500 detail no longer echoes the SKU. |
| 9 | `inventory.py:185` (PUT) | unchanged | No (PUT not mounted) | Not reachable; covered by the guard |
| 10 | `src/api/routers/safety.py:223` | The legacy router is not loaded; the canonical router raises 404 with the policy ID, which the global handler logged | **Yes**, through A1 | **Fixed** by A1 |
| 11 | `src/retrieval/structured/sql_retriever.py:176` | `:190-192` | Yes. Parameters were logged as a tuple, so CR/LF was already escaped; the remaining problem was data exposure. | **Fixed**: parameters are no longer logged |

### Process-wide guard

`install_log_injection_guard()` (`src/api/utils/log_utils.py`) wraps the logging record factory, so every formatted message in the process has CR, LF and other control characters escaped (`\r`, `\n`, `\xNN`; tab is kept).
- **Where it runs:** at import in `maiw_api.app`, the shipped API, and in each MCP domain server's entry point. The MCP image now ships `src/api/utils`.
- **Why it's needed:** a log call added later cannot forge entries. This also covers the MCP tool-argument logs (`asset_id`, `assignee`, `sku`) in `mcp_servers/*` and the agent packages.
- **Limitations:** records keep their `args`, because uvicorn's access formatter needs them. Tracebacks are formatted separately and are not escaped. `sanitize_log_data` remains the tool for length limits and redaction at a call site.
- **SonarQube's view:** its taint analysis does not model the factory, so sinks covered only by the guard may still be reported. A project administrator should resolve those as "Safe" with a reference to this report.

### Tests (`tests/api/test_log_safety.py`, 8 tests, against the shipped app)

| Test | Checks | On `main` without the fix |
|---|---|---|
| Validation error | The password never appears in the log | **fails** (password logged) |
| Path values | CR/LF in equipment, safety-policy and inventory paths produce no multi-line message | **fails** |
| Login username | Same, for a forged username | **fails** |
| SQL retriever | A bound e-mail address is not logged on a DB error | **fails** |
| Guard | Escaping, `args` preserved, idempotent | — |
| Guard installation | The guard is installed by `maiw_api.app` and by every MCP server's `__main__`; `Dockerfile.mcp` copies the module | — |

With the fix, all 8 pass. I also checked that the guard works inside a freshly built MCP image.

## 2. Security hotspots (72 TO_REVIEW)

| Rule | Count | Disposition | Evidence |
|---|---|---|---|
| `python:S2245`, pseudorandom generator | 46 | **Safe** | None is a security use. The `action_tools.py` mock generator has been removed; `service_discovery.py` is deleted. `local_processor.py` (mock document processing) and `sample_metrics.py` (synthetic Prometheus metrics) have no importers. Security identifiers use `uuid4`; JWTs are signed with the configured secret (`jwt_handler.py`). |
| `python:S1313`, hard-coded IP | 9 | **Safe** | `11.13.18.05` is the Oracle Fusion REST API version segment, not an IP. The others are RFC 1918 placeholder devices in the scanning and attendance services. |
| `python:S4790`, weak hash | 4 | **Safe** | MD5 is used for cache keys, chunk IDs and de-duplication, never for integrity or authentication. |
| `python:S5332`, clear-text protocol | 13 | 9 safe, **2 groups not safe by design but not reachable** | Safe: the localhost CORS defaults, and `startswith("http://")` checks on scanned QR content. **Not safe:** `src/adapters/wms/sap_ewm.py` always uses `http://` while sending SAP Basic credentials, and the four `src/adapters/iot/*` adapters send Bearer or Basic credentials with no https option. Connections are created only by `POST /api/v1/{wms,iot}/connections`, which the shipped app does not mount, and none are configured by default. **Follow-up:** add `use_ssl`, defaulting to https, as `wms/oracle.py` and `wms/manhattan.py` already do, before these adapters are exposed. |
| `python:S6418` | 1 | Already reviewed as Safe | — |

## 3. Previously closed issues: confirmed fixed

| Rule | Evidence in current code |
|---|---|
| `python:S5659`, JWT without signature verification | `jwt_handler.py` decodes with `verify_signature: True`, requires `exp` and `iat`, and rejects `alg=none` and any algorithm mismatch. |
| `secrets:S6698` ×5, PostgreSQL passwords in Compose files | `${POSTGRES_PASSWORD}` substitution only. (Unrelated: Grafana's `GRAFANA_ADMIN_PASSWORD` falls back to `changeme` in the monitoring Compose file.) |
| `python:S6709`, fixed seed | Fixed. A side effect was found: `scripts/data/generate_all_sku_forecasts.py` passes `random_state` to `SVR`, which does not accept it, so that data-generation script raises `TypeError`. It is not part of the app; tracked separately. |

## 4. Agent and tool security review

This is a focused review of the MAIW authority boundary. The code was read and nothing was changed here.

| Area | State |
|---|---|
| Governed writes | Equipment, labor and wave writes go through the DecisionEngine, then approval, then `ActionExecutor`, in the API. The API requires the operator write credential (`X-Maiw-Operator-Token`). Copilot ACT goes through `GovernedActionOrchestrator`; there are no `/copilot/approve` or `/copilot/execute` routes (architecture tests). |
| MCP tool authorization | **Gap, by design and documented:** the MCP domain servers are unauthenticated, and their write tools record the caller-supplied proposal and decision IDs without verifying them (SECURITY.md, "Supported Deployment Boundary"). They are supported only on a single trusted host, on 127.0.0.1. |
| Browser-driven writes | Cross-origin POST/PUT/PATCH/DELETE are refused by the origin guard (#223, #224). |
| Prompt injection | `sanitize_prompt_input` and `safe_format_prompt` (`log_utils.py`). LLM output proposes; the DecisionEngine decides. No tool executes model output directly. |
| Deserialization and code execution | `langgraph-checkpoint` ≥ 3 (CVE-2025-64439); in-memory state only. The dependency blocklist keeps out `langchain-experimental` (Python REPL). |
| Error responses | Shipped 5xx responses no longer echo exception text (#223). |

MCP tool contracts are not touched by this change. The tools are `warehouse_equipment_{assign,release,schedule_maintenance,get_status,get_telemetry}`, `warehouse_inventory_{get,locate}`, `warehouse_labor_{allocate,get_allocation,get_capacity}` and `warehouse_wave_{get,get_risk,reprioritize}`. The tool names in the original assignment (`reprioritize_wave`, `protect_carrier_lane`, `reallocate_labor`, `authorize_overtime`, `redirect_sku`, `check_inventory`) do not exist in this repository. The change edits only log statements and one 500 detail string; arguments, approval requirements, authorization and results are unchanged.
