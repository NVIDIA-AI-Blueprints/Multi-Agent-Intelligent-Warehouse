# MAIW v2 Reference Deployment Runbook

**Phase**: 20C-C — Deployment Operationalization; v2.0.1 canonical-app remediation (round 2)
**Status**: v2.0.1 release candidate — awaiting independent re-audit
**Last updated**: 2026-10-10

> **v2.0.1 change.** Everything in this runbook targets ONE process: the
> canonical shipped app `maiw_api.app:app`. It serves `POST /api/v1/inference`
> on the API port; there is no separate `:8020` inference server and the
> legacy `src/api/app.py` is never started for a deployment.
>
> **v2.0.1 round 2 (re-audit PR #144, NEW-P1-02).** This runbook is the
> complete procedure: every command a fresh host needs is listed in
> [Clean-host procedure](#clean-host-procedure), in order. Every lifecycle
> script loads `.env` through one loader (`scripts/lib/load_env.sh`) *before*
> it validates anything, and acts only on the deployment identity recorded at
> start — never on a default port.

---

## Purpose / Scope

This runbook describes the canonical single-node MAIW v2 reference deployment.
It covers every lifecycle operation a developer or operator needs to bring up,
validate, stop, restart, recover, back up, restore, and roll back the qualified
architecture without tribal knowledge.

**Covered**: install, configuration, database, sandbox, MCP, preflight, start,
status, smoke test, stop, restart, qualification, backup, restore, rollback,
secret rotation, upgrade policy, troubleshooting.

**Not covered**: high availability, multi-region, distributed consensus,
Kubernetes autoscaling, NeMo Relay, SOP Engine extraction.

---

## Supported Topology

```
HOST (single node)
├── MAIW API — uvicorn maiw_api.app:app (MAIW_API_PORT, the only API process)
│   ├── ModelGateway → ModelRouter/PolicyFilter (nemotron-3 / nemotron-3.5 ONLY)
│   │              → DeploymentResolver (role → APPROVED physical model ID)
│   │              → NIMProvider → NIM endpoint (reported model must match)
│   ├── DecisionEngine → ActionExecutor → MCP (governed writes; profile
│   │                    reference_governed only)
│   ├── ProcedureHost (maiw_api.procedure_host) — SOP Engine bound to:
│   │     JsonFileProcedureStateStore  ($MAIW_PERSISTENCE_ROOT/procedures/)
│   │     JsonFileGovernanceInbox      ($MAIW_PERSISTENCE_ROOT/governance/)
│   ├── POST /api/v1/inference  (auth-required: X-Maiw-Internal-Token)
│   ├── POST /api/v1/equipment/{assign,release,maintenance}
│   │     (operator write credential X-Maiw-Operator-Token; never the sandbox)
│   ├── GET  /api/v1/procedures (read-only view of the durable store)
│   └── legacy /api/v1/chat — NOT mounted (v2.0.1)
├── Postgres/TimescaleDB (reference DB; scripts/setup/reference_db.sh)
├── Approved Nemotron 3 / 3.5 deployments (maiw_models/deployment.py)
│   ├── super      nvidia/nemotron-3-super-120b-a12b      (nemotron-3)
│   ├── lightning  nvidia/nemotron-3.5-lightning-30b-a3b  (nemotron-3.5)
│   ├── ultra      nvidia/nemotron-3-ultra-550b-a55b      (nemotron-3, disabled by default)
│   └── nano       nvidia/nemotron-3-nano-30b-a3b         (nemotron-3, DISABLED: hosted EOL)
│       Hosted at: https://integrate.api.nvidia.com/v1  OR a local NIM
└── NemoClaw/OpenShell sandbox MAIW_SANDBOX_NAME (MAIW_SANDBOX_MODE=required)
    ├── policy deploy/openshell/maiw-inference-only.policy.yaml.tmpl
    │   (egress ONLY `POST /api/v1/inference` on <HOST_IP>:MAIW_API_PORT —
    │    OpenShell L7 REST rule; no provider, no internet)
    ├── SOP Engine / DeepAgentsRuntime / RuntimeCapabilityPolicy
    └── POST http://<HOST_IP>:MAIW_API_PORT/api/v1/inference

Persistence root: $MAIW_PERSISTENCE_ROOT (e.g. /var/lib/maiw)
  procedures/   — JsonFileProcedureStateStore (one .json per procedure, atomic)
  governance/   — JsonFileGovernanceInbox (governance_inbox.jsonl, append-only:
                  "accepted" entries with payload + "applied" markers)
  runtime/      — maiw-api.instance (deployment identity), maiw-api.pid, API log,
                  rendered sandbox policy
```

---

## Deployment Profiles

`MAIW_DEPLOYMENT_PROFILE` decides what `/api/v1/ready` requires (round 2):

| Profile | Use | Governed writes | Required for READY |
|---|---|---|---|
| `reference` | the reference deployment (default outside demo mode) | **not offered** (`governed_write_path: not_offered`) | persistence, ModelGateway with every enabled role bound to an approved physical model, database, sandbox when `MAIW_SANDBOX_MODE=required` |
| `reference_governed` | reference + governed operational writes | offered (operator write credential required) | everything in `reference` **plus** every required MCP write domain (default `equipment,labor,wave`, override `MAIW_REQUIRED_MCP_DOMAINS`) configured, reachable and not circuit-open, its executor built, and `MAIW_OPERATOR_WRITE_TOKEN` usable |
| `demo` | `MAIW_DEMO_MODE=true`, SimulationProviders (in-memory MCP) — not a reference deployment | simulation only | persistence, ModelGateway, all four in-memory MCP domains; no database |

The reference profile is honest about what it cannot do: it never reports a
governed write path as ready, and an unconfigured MCP domain is
`NOT_CONFIGURED`, never `HEALTHY`. Since round 3 behaviour matches: in
`reference` no ActionExecutor is built even when an MCP URL is set (MCP is
read-only there) and the write routes answer `503 GOVERNED_WRITES_NOT_OFFERED`
after authentication.

### Operational write authentication (v2.0.1 round 3)

| Route | Credential | Denied caller |
|---|---|---|
| `POST /api/v1/inference` | `X-Maiw-Internal-Token` = `MAIW_INFERENCE_INTERNAL_TOKEN` (the sandbox's only credential) | 401 |
| `POST /api/v1/equipment/assign`, `/release`, `/maintenance` | `X-Maiw-Operator-Token` = `MAIW_OPERATOR_WRITE_TOKEN` (host operator only) | no header → 403 `OPERATOR_WRITE_CREDENTIAL_REQUIRED`; wrong value (incl. the inference token) → 401 `INVALID_OPERATOR_WRITE_CREDENTIAL`; not configured → 503 `OPERATOR_WRITE_AUTH_NOT_CONFIGURED` |

Authentication is a route dependency: it is decided before the body is read
and before any agent, DecisionEngine, ActionExecutor or MCP call. The
DecisionEngine remains the *authority* decision after authentication; it is
not a substitute for it. A JWT user session alone never authorises an
operational write. The two tokens must differ (preflight and the app both
refuse an operator token equal to the inference token).

**UI.** The browser never holds the operator credential (never use a
`REACT_APP_*` variable for it). The UI's equipment write actions work only
behind an authenticated operator proxy that adds `X-Maiw-Operator-Token`
server-side; for a localhost-only development console, the CRA dev server
does this when `MAIW_UI_OPERATOR_WRITE_TOKEN` is set in *its* environment
(`src/ui/web/src/setupProxy.js`). Without it the UI shows "Operational writes
require the operator write credential".

---

## Known Limitations

- **Single node only** — no distributed consensus, no HA failover.
- **File-backed state** — survives process restart on same filesystem; not multi-replica safe.
- **Auth token rotation requires restart** — both API and sandbox must restart.
- **No Kubernetes manifests** — see `docs/architecture/DEPLOYMENT_ARCHITECTURE.md` for conceptual target.
- **No NeMo Relay** — out of scope for v2 reference deployment.
- **Provider dependency** — if the NIM endpoint is unreachable, inference fails per request (typed 503); governance and procedure state are preserved.
- **Nano disabled** — the hosted endpoint retired `nvidia/nemotron-3-nano-30b-a3b` (HTTP 410, 2026-09-01). MEDIUM reasoning is served by Super (`fallback_used=true`). Enable Nano only with a working deployment of that exact ID.
- **No approved multimodal model** — IMAGE/vision requests fail closed.
- **Governed writes need working MCP servers** — the `reference` profile does not offer them; `reference_governed` refuses READY until they are configured and reachable.

---

## Version Matrix

| Component | Required Version | Qualification Status |
|---|---|---|
| NemoClaw | **0.0.124** | QUALIFIED (PR #135, 2026-10-05) |
| OpenShell | **0.0.116** | QUALIFIED (PR #135, 2026-10-05) |
| Python (host) | **>= 3.12** | Qualified on 3.12.3 |
| Approved physical models | `maiw_models/deployment.py` `APPROVED_DEPLOYMENTS` | generation bound to physical ID |
| Approved generations | `nemotron-3`, `nemotron-3.5` | fixed; cannot be widened |
| Reference DB image | `timescale/timescaledb:2.15.2-pg16` | schema `data/postgres/*.sql` |

Do **not** use floating `latest` tags. Pin exact versions.

---

## Prerequisites

1. NVIDIA H100 or equivalent GPU (sm_90a or compatible) with a working driver (`nvidia-smi` must succeed — preflight checks its exit status)
2. Python 3.12+ and `python3 -m venv`
3. Docker (reference database container; NemoClaw)
4. NemoClaw 0.0.124 and OpenShell 0.0.116 CLIs on `PATH` (`nemoclaw --version`, `openshell --version`) with a running OpenShell gateway
5. NVIDIA API key (hosted NIM) or a local NIM serving the approved model IDs
6. `curl`

---

## Clean-host procedure

The complete, ordered command list (each step is detailed below). Run from
the repository root.

```bash
# 1. Install (venv mirrors CI)
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
for p in maiw-mcp maiw-state maiw-decision maiw-models maiw-skills maiw-execution maiw-contracts maiw-world; do
  .venv/bin/pip install -e "packages/$p"; done
.venv/bin/pip install -e "packages/maiw-agents[deep-agents]" -e apps/api

# 2. Configure
cp .env.example .env
#    edit .env: NVIDIA_API_KEY, MAIW_INFERENCE_INTERNAL_TOKEN (fresh random),
#    POSTGRES_PASSWORD, JWT_SECRET_KEY, MAIW_PYTHON=$PWD/.venv/bin/python,
#    MAIW_PERSISTENCE_ROOT (writable), MAIW_API_PORT (free), PGPORT (free),
#    MAIW_DB_CONTAINER, MAIW_SANDBOX_NAME,
#    MAIW_SANDBOX_MODEL_GATEWAY_ENDPOINT=http://<HOST_IP>:<MAIW_API_PORT>/api/v1/inference

# 3. Database
bash scripts/setup/reference_db.sh up

# 4. Sandbox + network policy
bash scripts/setup/reference_sandbox.sh create

# 5. Preflight → start → status → smoke
bash scripts/preflight_reference_deployment.sh
bash scripts/start_reference_deployment.sh
bash scripts/status_reference_deployment.sh
bash scripts/smoke_test_reference_deployment.sh

# 6. In-sandbox check (sandbox → canonical app → approved model)
bash scripts/setup/reference_sandbox.sh probe

# 7. Restart / stop
bash scripts/restart_reference_deployment.sh
bash scripts/stop_reference_deployment.sh

# 8. Teardown (only what steps 3–4 created)
bash scripts/setup/reference_sandbox.sh delete
bash scripts/setup/reference_db.sh down
```

`scripts/validate_reference_runbook.sh` checks that every script and file
this procedure names exists and that `.env.example` documents every variable
the scripts require.

---

## Configuration

All configuration is via environment variables in `.env`
(`cp .env.example .env`). Every lifecycle script loads it with
`scripts/lib/load_env.sh`: values are **parsed, not executed**; a variable
already exported in your shell wins for that one run; `MAIW_ENV_FILE=<path>`
selects another file. The scripts then export `PYTHON_DOTENV_DISABLED=1`, so
the app reads only what the loader exported.

### Required Variables

| Variable | Description | Example |
|---|---|---|
| `MAIW_PYTHON` | venv interpreter that imports `maiw_api` from this checkout | `/opt/maiw/.venv/bin/python` |
| `MAIW_PERSISTENCE_ROOT` | durable state root (writable, not world-writable) | `/var/lib/maiw` |
| `MAIW_API_PORT` | API port — must be free; **no default is assumed** | `8001` |
| `MAIW_DEPLOYMENT_PROFILE` | `reference` or `reference_governed` | `reference` |
| `MAIW_INFERENCE_INTERNAL_TOKEN` | auth token for the inference boundary (fresh, >= 32 chars) | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `MAIW_OPERATOR_WRITE_TOKEN` | **`reference_governed` only** — operator write credential (fresh, >= 32 chars, different from the inference token; never given to the sandbox) | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `NVIDIA_API_KEY` | hosted NIM credential (host only) | `nvapi-...` |
| `POSTGRES_PASSWORD`, `JWT_SECRET_KEY` | DB / auth secrets | |
| `PGHOST`, `PGPORT`, `POSTGRES_USER`, `POSTGRES_DB` | the data-path database (readiness probes exactly these) | `127.0.0.1`, `5435` |
| `MAIW_DB_CONTAINER` | reference DB container name (unique per host) | `maiw-reference-db` |
| `MAIW_SANDBOX_MODE` | must be `required` | `required` |
| `MAIW_SANDBOX_NAME` | reference sandbox (<= 19 chars) | `maiw-ref-sandbox` |
| `MAIW_SANDBOX_MODEL_GATEWAY_ENDPOINT` | sandbox → host inference URL (host's routable IP, API port) | `http://10.x.x.x:8001/api/v1/inference` |

### Model bindings (optional — approved defaults apply)

`NEMOTRON_<ROLE>_MODEL` / `NEMOTRON_<ROLE>_ENABLED` for `LIGHTNING`, `NANO`,
`SUPER`, `ULTRA`. A role may only be bound to its approved physical ID
(`maiw_models/deployment.py`); anything else fails closed at preflight, at
readiness (`model_gateway` failed) and per request (`503
MODEL_POLICY_VIOLATION`, zero provider calls). `LLM_MODEL` / `MAIW_NIM_MODEL`
are **not** dispatched by ModelGateway; if set they must still name an
approved model. Check any configuration with:

```bash
.venv/bin/python scripts/lib/check_model_config.py --provider-probe
```

### MCP (profile `reference_governed`)

| Variable | Required | Notes |
|---|---|---|
| `MAIW_MCP_SERVER_EQUIPMENT_URL` | yes (write domain) | |
| `MAIW_MCP_SERVER_LABOR_URL` | yes (write domain) | |
| `MAIW_MCP_SERVER_WAVE_URL` | yes (write domain) | |
| `MAIW_MCP_SERVER_INVENTORY_URL` | no (read-only) | |
| `MAIW_REQUIRED_MCP_DOMAINS` | no | override the required set (comma-separated) |

In the `reference` profile all four are optional; unset domains are reported
`NOT_CONFIGURED` and governed writes are `not_offered`.

### Development-Only (NEVER set in reference deployment)

| Variable | Description |
|---|---|
| `MAIW_INFERENCE_ALLOW_UNAUTHENTICATED` | Bypasses auth — dev only |
| `MAIW_MOCK_INFERENCE` | Enables mock inference — dev only |
| `MAIW_DEMO_MODE` | Simulation mode — dev only |

---

## Secrets

| Secret | Who holds it | Process that needs it | Sandbox sees it | Restart on rotation |
|---|---|---|---|---|
| `MAIW_INFERENCE_INTERNAL_TOKEN` | MAIW operator | MAIW API + sandbox | YES (to authenticate to MAIW API; passed on stdin) | YES — API and sandbox must restart |
| `MAIW_OPERATOR_WRITE_TOKEN` | MAIW operator | MAIW API; host operator tooling / operator proxy | **NO** — never; the sandbox probe proves it by digest comparison | YES — API must restart |
| `NVIDIA_API_KEY` | MAIW operator | MAIW API (NIMProvider) | NO — never forwarded to sandbox | YES — API must restart |
| `JWT_SECRET_KEY` | MAIW operator | MAIW API (auth signing) | NO | YES |
| `POSTGRES_PASSWORD` | MAIW operator | MAIW API (DB layer), reference DB container | NO | YES |

**Invariants**:
- No secrets are committed to version control
- No secrets appear in logs, script output, or health endpoints
- No warehouse write credentials in sandbox — the operator write token is never injected; `reference_sandbox.sh probe` fails if a digest of it (or of the provider key, DB password or JWT secret) is found in the sandbox environment
- No NIM/provider credential in sandbox
- `MAIW_INFERENCE_INTERNAL_TOKEN` is the only credential that flows to the sandbox

---

## Database

The reference profile requires the Postgres/TimescaleDB the SQL data path
uses (`PGHOST`/`PGPORT`/`POSTGRES_*`). `/api/v1/ready` probes exactly those
values; if `DATABASE_URL` is also set it must name the same database.

```bash
bash scripts/setup/reference_db.sh up       # create container MAIW_DB_CONTAINER on 127.0.0.1:PGPORT,
                                            # load data/postgres/*.sql, verify SELECT 1 + schema
bash scripts/setup/reference_db.sh status   # health check
bash scripts/setup/reference_db.sh down     # remove ONLY the container this script created
```

The script refuses to reuse a container it did not create (label
`maiw.reference-db`) and refuses a `PGPORT` that is already in use.

---

## Sandbox

With `MAIW_SANDBOX_MODE=required` the sandbox participates in readiness.
Create it **before** starting the API (the sandbox only needs the endpoint
address, not a running API):

```bash
bash scripts/setup/reference_sandbox.sh create   # render policy, create MAIW_SANDBOX_NAME, wait for Ready
bash scripts/setup/reference_sandbox.sh status
bash scripts/setup/reference_sandbox.sh probe    # after start: sandbox → POST /api/v1/inference
bash scripts/setup/reference_sandbox.sh delete   # only a sandbox this script created
```

The policy (`deploy/openshell/maiw-inference-only.policy.yaml.tmpl`) allows
egress ONLY to the host IP and port in `MAIW_SANDBOX_MODEL_GATEWAY_ENDPOINT`,
and on that host:port ONLY `POST /api/v1/inference` (OpenShell L7 `protocol:
rest` rule; the API is plain HTTP, so the sandbox proxy inspects method and
path — any other request on the port is denied by the proxy with 403). No
provider, internet, metadata service, private NIMs or databases. No
credential provider is attached; the probe receives the internal token on
stdin.

The network rule is one layer, not the authority boundary: the application
still authenticates every request (inference token for inference; the
separate operator write credential for every operational write), so a
misconfigured policy does not open a write path.

`probe` exits non-zero unless: inference with the token returns 200 with a
verified approved model; every governed write route is denied for every
credential the sandbox holds (none, the inference token in each header, the
inference token as a bearer); and no host secret is present in the sandbox
environment (digest comparison — values are never printed).

---

## Preflight

```bash
bash scripts/preflight_reference_deployment.sh
```

Loads `.env` first, then validates the **effective** configuration: required
variables present (no default port/root); profile; OS; `MAIW_PYTHON` version
and that it imports `maiw_api` from this checkout; GPU (`nvidia-smi` exit
status, driver, compute capability); Docker/Podman; NemoClaw 0.0.124 and
OpenShell 0.0.116 CLIs; **physical model bindings** — the same
`ModelRegistry` + `DeploymentResolver` the gateway runs, on the
`NEMOTRON_<ROLE>_MODEL` values it dispatches, plus a provider `/models`
listing probe; API port free; persistence root creatable; auth token set,
not the placeholder, >= 32 chars; operator write credential usable and
distinct from the inference token (`reference_governed`; must be valid if
set in `reference`); `MAIW_DEMO_MODE` not enabled; dev override not active; sandbox mode
required and the named sandbox Ready; database reachable with schema loaded;
required MCP write domains reachable (`reference_governed`).

Returns non-zero on failure. `start` runs it unless `--skip-preflight`.

---

## Start

```bash
bash scripts/start_reference_deployment.sh [--skip-preflight]
```

1. Load `.env` (shared loader) and require `MAIW_PERSISTENCE_ROOT`, `MAIW_API_PORT`, `MAIW_PYTHON`
2. If a verified instance is already running, do nothing
3. Preflight the effective configuration (unless `--skip-preflight`)
4. Create persistence directories (chmod 700)
5. Check `MAIW_PYTHON` imports `maiw_api` from this checkout (never `pip install`s)
6. Start `uvicorn maiw_api.app:app` with a fresh random `MAIW_INSTANCE_ID`;
   record the deployment identity in `runtime/maiw-api.instance`
7. Wait for `/api/v1/ready` = 200 on **this** instance (fails fast if the
   process exits, e.g. port taken)
8. Print a safe summary, including the approved physical model bindings

---

## Deployment identity

`runtime/maiw-api.instance` records `instance_id`, `pid`, `port`,
`project_root`. `status`, `smoke`, `restart` and `stop` act only after
verifying: the PID is alive; `/proc/<pid>` shows `uvicorn maiw_api.app:app
--port <port>`, started in this checkout, with this `MAIW_INSTANCE_ID`; and
(except `stop`) `GET /api/v1/live` on that port returns the same
`instance_id`. Otherwise they report **NOT RUNNING / CANNOT VERIFY** and send
no request / signal nothing. There is no fallback to `localhost:8001`.

---

## Readiness

```bash
curl http://127.0.0.1:$MAIW_API_PORT/api/v1/ready   # 200 = ready, 503 = not ready
curl http://127.0.0.1:$MAIW_API_PORT/api/v1/live    # 200 = process alive (+ instance_id)
```

Any **critical** component failing → HTTP 503
`{"status": "NOT_READY", "profile": ..., "failed_components": [...]}`.

| Component | Critical | Ready when |
|---|---|---|
| `profile` | yes | `MAIW_DEPLOYMENT_PROFILE` is valid |
| `runtime` | yes | lifespan assembled `MAIWRuntime` |
| `persistence` | yes | `procedures/` and `governance/` exist, are listable, accept an fsynced probe; reports `unapplied_governance` |
| `model_gateway` | yes | ModelGateway constructed AND every enabled role bound to its approved physical model (`binding_violations` otherwise) |
| `mcp_domains` | yes | every **required** domain `READY`/`DEGRADED`; per-domain states `READY`, `DEGRADED`, `CIRCUIT_OPEN`, `FAILED` (unreachable), `NOT_CONFIGURED` |
| `governed_write_path` | yes when the profile offers governed writes | DecisionEngine, MCP client, equipment agent, required domains usable, executors built; else `not_offered` |
| `database` | yes in `reference*` (override `MAIW_READINESS_REQUIRE_DATABASE`) | `SELECT 1` on `PGHOST:PGPORT/POSTGRES_DB` within 3 s; `DATABASE_URL`, if set, names the same DB |
| `sandbox_runtime` | yes when `MAIW_SANDBOX_MODE=required` | `MAIW_SANDBOX_NAME` phase `Ready`; otherwise reported `not_configured`/`degraded` |
| `model_provider` | no | reported (NIM circuit); provider down → inference 503 per request, every profile |

Liveness (`/api/v1/live`) never depends on any of these.

### Degraded state semantics

| Condition | MAIW behavior |
|---|---|
| Model provider down | `/ready` stays 200; inference returns 503 `PROVIDER_FAILURE`/`MODEL_UNAVAILABLE` |
| Provider reports a different model | that request: 502 `MODEL_IDENTITY_MISMATCH`, response discarded |
| Role bound to an unapproved model | `/ready` 503 `model_gateway`; requests routed to that role: 503 `MODEL_POLICY_VIOLATION`, no provider call |
| Required sandbox not Ready | `/ready` 503 `sandbox_runtime` |
| Required MCP domain unconfigured / unreachable / circuit-open | `/ready` 503 `mcp_domains` + `governed_write_path` |
| Persistence unavailable | `/ready` 503 `persistence` |
| Database unreachable | `/ready` 503 `database` |

---

## Smoke Test

```bash
bash scripts/smoke_test_reference_deployment.sh
```

Targets only the verified instance (refuses otherwise, exit 2): liveness;
readiness 200 READY; durable persistence; ModelGateway bindings; configured
bindings via `check_model_config.py`; `/api/v1/inference` mounted; 401
without / with wrong token; 422 for `model_id` and for an unknown `model`
field; 200 with the token, then **physical model identity**: logical role,
resolved physical model, generation, provider-reported model — the model must
be the approved deployment for that role and the provider must report the
same ID; legacy `POST /api/v1/chat` → 404; **operational write boundary** —
`POST /api/v1/equipment/{assign,release,maintenance}` denied (401/403/503)
with no credential, with the inference token and with the inference token
sent as the operator header; in `reference_governed` the operator credential
is accepted (authenticated empty body → 422, so nothing is proposed or
written); sandbox `MAIW_SANDBOX_NAME` Ready.
The token is passed to curl on stdin, never on the command line.

---

## Normal Operation

After start and smoke test pass:

- Procedure state is held host-side by `ProcedureHost` in the durable
  `JsonFileProcedureStateStore`; the sandboxed runtime reasons for its steps
- Inference flows: sandbox → POST /api/v1/inference (canonical app) → ModelGateway → PolicyFilter → DeploymentResolver → NIMProvider
- Governance wait: a procedure reaches WAITING_FOR_GOVERNANCE and is checkpointed to disk
- Governance decision: in `reference_governed`, DecisionEngine routes approval and ActionExecutor executes the write via MCP; the outcome is applied with `ProcedureHost.apply_governance`
- `JsonFileGovernanceInbox` records each outcome (with its payload) before the resume and an `applied` marker after it, so a redelivery is dropped and a crash between the two is recoverable (`ProcedureHost.recover_accepted_governance`)
- `GET /api/v1/procedures` shows stored procedures (read-only). There is no HTTP route to start or resume procedures in v2.0.1.

---

## Status

```bash
bash scripts/status_reference_deployment.sh
```

Reports (no secrets): verified identity, liveness, readiness breakdown
(profile, persistence + `unapplied_governance`, model bindings, MCP domain
states with required markers, sandbox), procedure counts, configured model
bindings and provider `/models` reachability. Exit 0 only when ready.

---

## Stop

```bash
bash scripts/stop_reference_deployment.sh
```

1. Report the sandbox phase (never stops or kills it — use `reference_sandbox.sh`)
2. Verify the recorded PID is this MAIW instance, then SIGTERM it (SIGKILL after 30 s only if the identity still matches)
3. No state / dead PID → `NOT RUNNING / CANNOT VERIFY`, nothing signalled (stale state cleared); PID belongs to another process → refuse, exit 3
4. Preserve all durable state (`--delete-state` is interactive, test cycles only)

There is no kill-by-port and no kill-by-name.

---

## Restart

```bash
bash scripts/restart_reference_deployment.sh [--skip-preflight]
```

Refuses (exit 2, nothing changed) unless the running instance is verified.
Runs preflight FIRST (unless `--skip-preflight`) and refuses (exit 1) with the
running instance untouched if it fails; then stop → start and compare durable
state before/after: procedure files, WAITING_FOR_GOVERNANCE count, governance
ledger.

Restart preserves ProcedureExecutionState, the GovernanceInbox ledger,
correlation IDs, SOP version pinning, retry/loop budgets and
WAITING_FOR_GOVERNANCE status.

---

## Backup

Backup is a consistent copy of the persistence root:

```bash
# Recommended: stop API first for clean consistency point, then copy
bash scripts/stop_reference_deployment.sh

BACKUP_DIR="/backup/maiw/$(date +%Y%m%dT%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp -r /var/lib/maiw/procedures "$BACKUP_DIR/"
cp -r /var/lib/maiw/governance "$BACKUP_DIR/"
echo "Backup at: $BACKUP_DIR"

bash scripts/start_reference_deployment.sh
```

**Notes**:
- Backup is non-destructive — source files are not deleted
- A consistent point requires API to be stopped (or at minimum all procedure writes quiesced)
- For live backup, use the qualify script which handles the sequence

---

## Restore

```bash
# 1. Stop the deployment
bash scripts/stop_reference_deployment.sh

# 2. Validate backup directory
ls -la /backup/maiw/<timestamp>/procedures/
ls -la /backup/maiw/<timestamp>/governance/

# 3. Restore from backup
cp -r /backup/maiw/<timestamp>/procedures/. /var/lib/maiw/procedures/
cp -r /backup/maiw/<timestamp>/governance/. /var/lib/maiw/governance/

# 4. Validate file permissions
chmod 700 /var/lib/maiw/procedures /var/lib/maiw/governance

# 5. Restart and verify readiness
bash scripts/start_reference_deployment.sh
bash scripts/status_reference_deployment.sh

# 6. Verify procedure state is readable
ls /var/lib/maiw/procedures/*.json 2>/dev/null | wc -l
```

**State schema compatibility**: if stored state was written by a different MAIW
version, verify JSON schema compatibility before starting. Incompatible state
will cause the engine to fail-closed with a clear error (not silent
reinterpretation).

---

## Rollback

**Rollback baseline** (recorded at qualification):
- MAIW SHA: `1745a2c2d7d90041c2603acfb8291df71855278f`
- NemoClaw: 0.0.124
- OpenShell: 0.0.116
- Model: `nvidia/nemotron-3-super-120b-a12b` (gen=nemotron-3)

**Rollback procedure**:
```bash
# 1. Stop current deployment
bash scripts/stop_reference_deployment.sh

# 2. Roll back MAIW application (do NOT delete state)
git checkout <baseline-sha>
# reinstall exactly as in "Clean-host procedure" step 1 (same .venv)

# 3. Keep state and config compatible with baseline schema
# (if state schema changed, consult state schema compatibility section)

# 4. Restart
bash scripts/start_reference_deployment.sh

# 5. Readiness and smoke test
bash scripts/status_reference_deployment.sh
bash scripts/smoke_test_reference_deployment.sh
```

**Never delete procedure/governance state as a rollback strategy.** A procedure in WAITING_FOR_GOVERNANCE has a pending governance decision. The state records this; deleting it loses the correlation.

**Rollback with active procedure**: if a procedure is in WAITING_FOR_GOVERNANCE when rollback occurs:
- Procedure state is preserved (file-backed)
- GovernanceInbox deduplication ledger is preserved
- SOP version is pinned in the procedure state
- After rollback and restart, the procedure resumes from the same governance-wait

---

## Upgrade Policy

**Rule**: change one major dependency at a time. Rerun relevant qualification after each version change.

| Upgrade | What to requalify |
|---|---|
| MAIW code change | Unit + contract + deployment tests; smoke test |
| NemoClaw version | Sandbox security qualification (tests/contract/) |
| OpenShell version | Sandbox security qualification |
| Model checkpoint change | Policy validation + inference test |
| Approved generation added | PolicyFilter review + all policy tests |

Do not upgrade NemoClaw and OpenShell simultaneously.

---

## Troubleshooting

| Symptom | Likely cause | Check | Recovery |
|---|---|---|---|
| Inference → 401 (no token) | MAIW_INFERENCE_INTERNAL_TOKEN not set | `echo $MAIW_INFERENCE_INTERNAL_TOKEN` | Set token in .env; restart API |
| Inference → 401 (wrong token) | Sandbox using stale token | Sandbox config vs. API config | Restart sandbox with correct token |
| Inference → 503 `MODEL_POLICY_VIOLATION` | a role is bound to an unapproved physical model | `check_model_config.py`; `/api/v1/ready` → `model_gateway.binding_violations` | unset or fix `NEMOTRON_<ROLE>_MODEL`; restart |
| Inference → 502 `MODEL_IDENTITY_MISMATCH` | provider served/reported a different model | provider endpoint / NIM deployment | point `MAIW_NIM_BASE_URL` at a deployment serving the approved ID |
| Inference → 503 `MODEL_UNAVAILABLE` (medium) | role disabled with no eligible fallback | `check_model_config.py` | enable Super (default) |
| Sandbox cannot call API | Network policy / wrong endpoint | MAIW_SANDBOX_MODEL_GATEWAY_ENDPOINT | Set correct host IP (not localhost) |
| Procedure not resuming | State mismatch or inbox duplicate | Check /var/lib/maiw/procedures/*.json | Validate procedure_execution_id + revision |
| Governance stuck | GovernanceInbox has duplicate | Check governance_inbox.jsonl | Verify idempotency_key not already accepted |
| `/ready` 503 `mcp_domains` | required MCP domain NOT_CONFIGURED / FAILED / CIRCUIT_OPEN | `GET /api/v1/ready` → `components.mcp_domains.domains` | configure/start the MCP server; wait cooldown; or use profile `reference` |
| `/ready` 503 `sandbox_runtime` | sandbox absent / not Ready | `reference_sandbox.sh status` | `reference_sandbox.sh create` |
| Script says NOT RUNNING / CANNOT VERIFY | no or stale `runtime/maiw-api.instance`, or the PID is not this instance | `cat $MAIW_PERSISTENCE_ROOT/runtime/maiw-api.instance` | start with `start_reference_deployment.sh`; never kill by port |
| Startup timeout | Provider/DB not available | Check provider URL and NVIDIA_API_KEY | Fix connectivity; retry start |
| Port already in use | another process owns MAIW_API_PORT | `ss -tlnp | grep :$MAIW_API_PORT` | choose a free MAIW_API_PORT (stop never kills by port) |
| No procedure state after restart | Wrong MAIW_PERSISTENCE_ROOT | `ls /var/lib/maiw/procedures/` | Correct MAIW_PERSISTENCE_ROOT |

---

## Security Operations

**How to verify the deployment is secure**:

1. **Physical model identity**: `.venv/bin/python scripts/lib/check_model_config.py` → every enabled role PASS
2. **Auth enabled**: `curl http://127.0.0.1:$MAIW_API_PORT/api/v1/inference -X POST -d '{}'` → must return 401
2b. **Write auth enabled**: `curl -X POST http://127.0.0.1:$MAIW_API_PORT/api/v1/equipment/release -H 'Content-Type: application/json' -d '{}'` → must return 403 (or 503 where writes are not configured / offered)
3. **Sandbox deny-by-default**: check RuntimeCapabilityPolicy in `integrations/nemoclaw/sandbox_policy.py` — ALWAYS_DENIED_CAPABILITY_CLASSES = frozenset({'WRITE', 'EMERGENCY_WRITE'})
4. **WRITE absent from sandbox**: `grep -r "WRITE\|EMERGENCY_WRITE" integrations/nemoclaw/sandbox_policy.py` → in ALWAYS_DENIED
5. **Secrets not exposed**: `curl http://127.0.0.1:$MAIW_API_PORT/api/v1/health` → no tokens, API keys, or credentials in response
6. **Token not logged**: tail the API log → token value must not appear

**Operator do-NOT list**:
- DO NOT commit `.env` or any file containing real credentials
- DO NOT set `MAIW_INFERENCE_ALLOW_UNAUTHENTICATED=true` in reference deployment
- DO NOT set `MAIW_MOCK_INFERENCE=true` in reference deployment
- DO NOT expose the inference endpoint without `X-Maiw-Internal-Token` enforcement
- DO NOT give `MAIW_OPERATOR_WRITE_TOKEN` to the sandbox, put it in the UI bundle, or set it equal to the inference token
- DO NOT configure Llama-family, Qwen, or any non-Nemotron-3/3.5 model
- DO NOT delete `/var/lib/maiw/procedures/` or `/var/lib/maiw/governance/` during rollback
- DO NOT deploy a new NemoClaw version without rerunning sandbox security qualification
- DO NOT add a new approved model generation without updating PolicyFilter and rerunning policy tests
- DO NOT bypass governance by injecting a WRITE capability into the sandbox policy

---

## Secret Rotation Runbook

### Rotating MAIW_INFERENCE_INTERNAL_TOKEN

1. Generate new token: `python3 -c "import secrets; print(secrets.token_hex(32))"`
2. Update `.env`: `MAIW_INFERENCE_INTERNAL_TOKEN=<new_token>`
3. Stop deployment: `bash scripts/stop_reference_deployment.sh`
4. Update sandbox configuration: the sandbox must receive the new token at launch (via environment injection)
5. Restart deployment: `bash scripts/start_reference_deployment.sh`
6. Verify: `bash scripts/smoke_test_reference_deployment.sh` (authenticated inference → 200)
7. Verify the old token is rejected (401)

### Rotating NVIDIA_API_KEY

1. Obtain new API key from https://build.nvidia.com/
2. Update `.env`: `NVIDIA_API_KEY=<new_key>`
3. Stop deployment: `bash scripts/stop_reference_deployment.sh`
4. Restart deployment: `bash scripts/start_reference_deployment.sh`
5. Verify: smoke test inference succeeds

---

## Failure Recovery

### API process crash

1. Restart: `bash scripts/start_reference_deployment.sh` (a dead PID's stale identity is replaced)
2. JsonFileProcedureStateStore and JsonFileGovernanceInbox survive the crash (file-backed)
3. Verify state count: `ls /var/lib/maiw/procedures/*.json | wc -l`
4. Run smoke test: `bash scripts/smoke_test_reference_deployment.sh`

### OpenShell/sandbox crash

1. Host truth is authoritative — sandbox state is a working copy only
2. Restart API (not necessary if API is still running) or just the sandbox
3. Any in-flight procedure resumes from the host's JsonFileProcedureStateStore
4. Duplicate governance delivery is caught by JsonFileGovernanceInbox

### Provider restart

1. ModelGateway will return 503 MODEL_UNAVAILABLE while provider is down
2. Readiness endpoint reflects degraded state for model gateway
3. No unapproved fallback — failure stays failure (no silent fallback to Llama)
4. When provider recovers, inference resumes automatically

### Governance-wait restart

1. A procedure in WAITING_FOR_GOVERNANCE survives restart unchanged (file-backed)
2. A governance outcome redelivered after restart is a dropped duplicate
3. **Crash between acceptance and resume** (v2.0.1 round 2): the inbox holds an
   `accepted` entry without an `applied` marker. On startup the app logs it and
   `/api/v1/ready` reports `persistence.unapplied_governance > 0`. The
   procedure's owner calls `ProcedureHost.recover_accepted_governance(inputs_for)`:
   if the stored procedure is still waiting at the bound revision the resume is
   replayed once (validation only — no write); if it already moved on it is only
   marked applied. Nothing is ever executed twice.

---

## Qualification Procedure

```bash
bash scripts/qualify_reference_deployment.sh [--evidence-dir /path/to/evidence]
```

Runs the full qualification sequence:
0. Preflight
1. Start → startup time baseline
2. Readiness
3. Smoke test
4. Proof SOP A (safe, non-consequential)
5. API restart → verify state preserved
6. Sandbox restart → verify host truth preserved
7. Backup / restore live test
8. Rollback baseline record
9. Stop → shutdown time baseline

Output: PASS/FAIL with evidence in `--evidence-dir`. Evidence includes readiness
response JSON and rollback baseline record.

---

## Log Locations

| Component | Location |
|---|---|
| MAIW API | `/var/lib/maiw/runtime/maiw-api.log` |
| Preflight | stdout / stderr |
| Procedure state | `/var/lib/maiw/procedures/*.json` |
| Governance inbox | `/var/lib/maiw/governance/governance_inbox.jsonl` |
| Deployment identity | `$MAIW_PERSISTENCE_ROOT/runtime/maiw-api.instance` (+ legacy `maiw-api.pid`) |

Log rotation: use platform defaults (logrotate or systemd journal). Configure
logrotate for `/var/lib/maiw/runtime/*.log` if retention > 7 days is required.

### Viewing logs

```bash
tail -f /var/lib/maiw/runtime/maiw-api.log
# or with journald:
journalctl -u maiw-api -f
```

---

## Process Supervision

For production use, install the MAIW API as a systemd service:

```ini
# /etc/systemd/system/maiw-api.service
[Unit]
Description=MAIW v2 API
After=network.target

[Service]
Type=simple
EnvironmentFile=/opt/maiw/.env
WorkingDirectory=/opt/maiw
ExecStart=/opt/maiw/env/bin/python -m uvicorn maiw_api.app:app \
    --host 0.0.0.0 --port 8001 --no-access-log
Restart=on-failure
RestartSec=5
StandardOutput=append:/var/lib/maiw/runtime/maiw-api.log
StandardError=append:/var/lib/maiw/runtime/maiw-api.log

[Install]
WantedBy=multi-user.target
```

One restart policy per service. Do not combine systemd with the lifecycle
scripts: a systemd-managed process has no `maiw-api.instance` identity, so
`stop`/`restart`/`smoke` will (correctly) refuse to act on it — manage it with
`systemctl`. `EnvironmentFile` must point at the same `.env`, and set
`PYTHON_DOTENV_DISABLED=1` in the unit.
