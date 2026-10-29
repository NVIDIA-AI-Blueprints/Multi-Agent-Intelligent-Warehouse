# MAIW v2.1.0 — Release Notes

**Status:** DRAFT for review, not tagged or published. Candidate commit:
`main` `b8b0a139effa67ba18a4cc23a46a696468cd7056` (PR #156). The latest
published release is still `v2.0.1` (`53a27e61…`). The version number
(`v2.1.0` rather than `v2.0.2`) is proposed in "Why v2.1.0" below.

## Summary

v2.1.0 makes the Docker Compose deployment start, serve and verify the full
governed stack. Since v2.0.1:

- The **labor and wave MCP servers have a PostgreSQL backend**, which is now
  their default and the **reference backend for the Compose deployment**.
- **All four MCP domain containers start** and are wired to the backend.
- The Compose backend has **durable state and database access**.
- The deployment workflow now **blocks on readiness, MCP startup, real MCP
  tool calls, and a backend-restart durability check**.
- It also fixes:
  - a startup crash on FastAPI 0.162;
  - a request-size bypass for chunked requests;
  - a labor allocation bug that reset task priority;
  - hardened container images, and the demo F06 ambiguous-write flow.

## Verification on the candidate commit (`b8b0a13`)

| Check | Result |
|---|---|
| CI/CD Pipeline: CORE CI pytest (Python 3.11) | **3219 passed, 13 skipped, 0 failed** |
| CI/CD Pipeline: UI Jest | **991/991** (42 suites) |
| CI/CD Pipeline: Security Scan | passed |
| CodeQL | passed |
| Deployment test ([run 40947216985](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/actions/runs/40947216985)), Compose, profile `reference_governed` | passed, every gating step green |
| ↳ Verify: API health checks (gates on `/api/v1/ready`) | passed |
| ↳ Verify: MCP domain servers (4 containers running, restarts 0, `initialize` + `tools/list`) | passed, 13 tools |
| ↳ **E2E: MCP tool calls** | passed |
| ↳ **E2E: durability across backend restart** | passed |
| Internal NGC MAIW pytest suite | **NOT RUN**: see below |

**The internal NGC pytest suite still could not run.** The deployment
workflow's MAIW pytest step needs the internal NGC test image
(`nvcr.io/…/blueprint-github-test-image`). On `b8b0a13` the pull was denied
(`requires internal NGC org access`). The step reports this as a warning, as
`E2E=NOT_RUN` in the job summary, and as "MAIW pytest NOT RUN" in the result
mail; it no longer passes silently (#154). Running that suite needs
`TEST_DOCKER_PULL_KEY` with access to the internal image, which is outside
this repository. **The public end-to-end checks above did run and pass**, and
they are what this release relies on.

### What the public end-to-end checks cover
`scripts/testing/smoke_e2e.py` runs against the live Compose stack. It
creates its own uniquely named rows, so it never depends on demo data. Each
write is checked three ways: the tool's response, the database row, and a
read-back through the domain's read tool.

| Domain | Read | Write |
|---|---|---|
| inventory | `get`: fixture quantity and location | (no write tool) |
| equipment | `get_status` | `assign`: asset `assigned` with owner in the DB, the `equipment_assignments` row matches, `get_status` agrees |
| labor | `get_capacity` lists the fixture worker | `allocate`: task assignee and allocation record in the DB, `get_allocation` returns exactly that task; allocating a missing task is a certified `NOT_APPLIED (NOT_FOUND)` |
| wave | `get`, `get_risk` | `reprioritize`: 2 tasks updated, `critical` in the DB and in `get` |

**Durability.** The check makes a governed `POST /api/v1/equipment/release`
through the API with the operator token. It checks the asset is released and
the assignment closed in the DB, then reads the execution record. Next it runs
`docker restart wosa-backend`, confirms the container's start time changed,
and waits for `/api/v1/ready`. Finally it reads **the same execution record**
back: all 12 durable fields must be unchanged, and the record must be listed
by `GET /api/v1/executions?status=all`.

Scope: this check covers the durable **execution journal**. The procedure
store and governance inbox use the same persistence root and volume, but have
no HTTP route that creates records, so the check does not exercise them.

## Why v2.1.0
The release adds functionality and changes a shipped default. It does not
only fix bugs:
- **New functionality:** a PostgreSQL backend for the labor and wave MCP
  servers, with a selection variable for each. Before, labor and wave could
  not be served from MAIW's own database (see the v2.0.1 known limitations).
- **Changed default:** the labor and wave servers now use that backend by
  default instead of the WMS adapters.

No API is removed. If you prefer a patch number (`v2.0.2`), only the file
name and headings change.

## Changes since v2.0.1

### PostgreSQL labor and wave providers: the Compose reference backend (#156)
- **New default backends:**
  - `mcp_servers/labor/adapters/postgres_backend.py` (`PostgresLaborProvider`):
    - workers are `users` rows with an operator, supervisor or manager role;
    - tasks are `tasks` rows, and the allocation writes `assignee` plus an
      allocation record in `payload`.
  - `mcp_servers/wave/adapters/postgres_backend.py` (`PostgresWaveProvider`):
    - a wave is the `tasks` rows sharing `payload->>'wave_id'`;
    - reprioritize updates `payload->>'priority'`.
- **Selection:**
  - `MAIW_MCP_LABOR_BACKEND` and `MAIW_MCP_WAVE_BACKEND` take `postgres`
    (default) or `wms`.
  - Any other value fails at startup.
  - The servers connect through `PGHOST`/`PGPORT`.
- **Write semantics follow the v2.0.1 round-4 rules**, the same as the
  equipment backend:
  - each write runs in one transaction with the target rows locked;
  - validation and precondition failures are reported before any write
    statement as a certified `NOT_APPLIED` with `INVALID_REQUEST`,
    `NOT_FOUND` or `PRECONDITION_FAILED`;
  - any other failure is reported as UNKNOWN, so the executor reconciles
    instead of retrying;
  - repeating a call with the same `execution_id` returns the recorded result
    without writing again.
- **Wave scope guard:** reprioritize requires a `wave_id` or a `zone`, so it
  cannot touch every task.
- **The WMS adapters no longer report false success:**
  - labor `allocate` with no WMS connected is `NOT_APPLIED
    (PRECONDITION_FAILED)`, and an empty worker list is `NOT_APPLIED
    (INVALID_REQUEST)`;
  - wave `reprioritize` through the WMS adapter is always `NOT_APPLIED
    (PRECONDITION_FAILED)`, because the WMS integration cannot set task
    priority.
- **Scope:**
  - The providers are qualified on the **Compose deployment**, which runs
    them in its `mcp-labor` / `mcp-wave` containers against the Compose
    TimescaleDB.
  - The single-process reference deployment in
    `docs/operations/REFERENCE_DEPLOYMENT_RUNBOOK.md` was not re-qualified
    with them for this release. Its runbook still documents an equipment-only
    governed deployment (`MAIW_REQUIRED_MCP_DOMAINS=equipment`).

### Labor allocation no longer resets task priority (#156)
`LaborAllocateRequest.priority` defaults to `"medium"`. The labor MCP tool,
`ExecuteLaborAllocationSkill` and `LaborActionExecutor` all forwarded that
default, so **every labor allocation that did not ask for a priority
overwrote the task's own priority with `medium`**. The new end-to-end check
found this. Priority is now forwarded and written only when the caller sets
it.

### Compose deployment (#154, #155, #156, #150)
- **Durable state (#154):**
  - `Dockerfile.backend` creates `/var/lib/maiw` owned by `appuser`.
  - The Compose backend mounts the named volume `maiw_state` there, so the
    procedure store, governance inbox and execution journal survive container
    restarts.
  - Before, startup logged `Permission denied: '/var/lib/maiw'`.
- **Database access (#154):** the Compose backend sets
  `PGHOST=timescaledb` / `PGPORT=5432`. Before, it tried `localhost:5435`
  inside the container.
- **MCP containers start (#155):** before this, all four `wosa-mcp-*`
  containers crash-looped. Three causes:
  - `Dockerfile.mcp` did not install `maiw-contracts` / `maiw-decision`;
  - the equipment server lacked the packages and code its PostgreSQL provider
    imports;
  - labor and wave had no `__main__` entry point.
- **MCP wiring (#156):**
  - The MCP containers get `PGHOST`/`PGPORT`.
  - The backend gets `MAIW_MCP_SERVER_<DOMAIN>_URL` for all four containers
    and depends on them.
  - `MAIW_DEPLOYMENT_PROFILE` and `MAIW_OPERATOR_WRITE_TOKEN` are read from
    `deploy/compose/.env`. The defaults stay `reference` and unset, so
    **governed writes stay off unless a deployment opts in**.
- **MinIO image (#150):** `quay.io/minio/minio` and `minio/minio` can no
  longer be pulled. Compose now uses `pgsty/minio:RELEASE.2026-08-04T00-00-00Z`,
  a pinned community build; swap in an internal mirror if you prefer.

### Deployment workflow gates (#154, #155, #156)
The steps run in this order and all of them fail the job:
1. **Readiness:** `/api/v1/ready` must return 200 within 60 s. On failure the
   step prints `failed_components` and the backend logs.
2. **MCP domain servers:** each container must be running with 0 restarts and
   answer MCP `initialize` and `tools/list`
   (`scripts/testing/probe_mcp_servers.py`).
3. **E2E: MCP tool calls**, then **E2E: durability across backend restart**
   (described above).

CI runs the deployment as `reference_governed` with a random operator token
that is masked in the logs. The MAIW pytest step has no `continue-on-error`
and reports `NOT_RUN` when the internal image is unavailable.

### API fixes (#153)
- **Startup crash on FastAPI 0.162:** `FastAPI(..., max_request_size=...)`
  was never a FastAPI parameter. It was ignored up to 0.143, and on 0.162 the
  import raises `TypeError`. The parameter is removed.
  - `requirements.docker.txt` pins `fastapi==0.162.0` / `starlette==1.10.0`.
  - `requirements.txt` is capped at `fastapi<0.163`, `starlette<1.11`.
- **Request size enforced on streamed bodies:** a pure ASGI middleware counts
  the bytes actually received.
  - A chunked body over the limit now gets a 413 (before, a 60 MB upload got
    through the 50 MB limit).
  - A declared oversize `Content-Length` is rejected before the app runs.
  - The 413 is a JSON response, not a 500.
  - SSE and streaming responses are unaffected.
- **Configurable rate-limiter fail mode:** `RATE_LIMIT_FAIL_MODE=open|closed`.
  - The default `open` keeps the old behaviour: on an internal limiter error,
    for example Redis being unavailable, the request is allowed.
  - `closed` returns `503 RATE_LIMITER_UNAVAILABLE`.
  - This is an opt-in mitigation; the default is unchanged.

### Container image hardening (#149, #151)
- **Backend image (`Dockerfile.backend`):**
  - Base: `python:3.13.16-slim-trixie` (digest-pinned).
  - No `curl`, `git`, `poppler-utils`, `setuptools`, `wheel` or `pip` in the
    runtime image; the healthcheck uses Python.
  - OS packages: 183 → 87.
  - Also fixed: the image did not install `maiw-contracts` / `maiw-world` or
    ship `mcp_servers/` and `data/worlds/`, so `/ready` was always 503 in the
    demo profile.
- **Frontend image (`Dockerfile.frontend`):**
  - Multi-stage build; runs on `nginx-unprivileged` (uid 101) with no
    Node.js, npm or `node_modules` (589 MB → 63 MB).
  - nginx **strips `X-Maiw-Operator-Token`** from browser requests.
  - The container listens on 8080, and Compose publishes it as `3001:8080`.
- **Trivy results (critical/high, same DB snapshot, recorded in #149):**
  - backend 1/29 → 0/8, all 8 in the Debian base with no fix available;
  - frontend 2/36 → 0/0.
  - This is not an nSpect/Anchore rescan; that happens outside this
    repository.
- **#151:**
  - the backend image ships `artifacts/demo/`, so the "Control vs MAIW"
    evaluation loads;
  - `/version` falls back to the `GIT_SHA` / `BUILD_TIME` build environment
    when git is unavailable.

### Demo reliability: F06 ambiguous write end to end (#148, #152)
- **Fault-injection targets (#148):** equipment fault and restore injection
  resolve the target asset from the active DataPack world, deterministically.
  `asset_id` is optional, and the UI no longer hard-codes `AGV-01`.
  - An unknown `asset_id` returns `404 ASSET_NOT_IN_ACTIVE_WORLD`.
  - No eligible asset returns `409 NO_ELIGIBLE_ASSET`.
- **Ambiguous write is armed (#148):** F06 now arms a one-shot ambiguous
  write on the resolved asset.
- **Approval binding (#152):** `/demo/analyze` binds proposals to the active
  world's warehouse (`DC-47`), so `/demo/approve` is no longer rejected for a
  warehouse mismatch.
- **Real outcome from `/demo/approve` (#152):** it now reports the actual
  outcome:
  - `202 status=unknown` with `reconciliation_required`;
  - `409 RECONCILIATION_REQUIRED` while the target has an unresolved
    execution.
  - Before, it always returned `executed`.
- **Reconciliation events (#152):**
  - `RECONCILIATION_REQUIRED` is published once per UNKNOWN execution;
  - `/demo/reconcile` publishes `CONFIRMED_EXECUTED`,
    `CONFIRMED_NOT_EXECUTED` or `INDETERMINATE`;
  - the UI's RECONCILE NOW button follows those events.
  - The full flow writes to the backend exactly once.

### Documentation (#147)
- The v2.0.1 notes and runbook now match the published release.
- The runbook's clean-host procedure starts with `unset PYTHONPATH`.

## Upgrade notes
- **Rebuild all images.** `Dockerfile.backend` (persistence root, Python
  3.13.16), `Dockerfile.frontend` and `Dockerfile.mcp` (packages, code and
  entry points) all changed.
- **Labor and wave MCP backend:** the servers now default to PostgreSQL.
  - Give them `PGHOST`/`PGPORT` and the `POSTGRES_*` credentials; Compose does
    this.
  - To keep the WMS adapters, set `MAIW_MCP_LABOR_BACKEND=wms` /
    `MAIW_MCP_WAVE_BACKEND=wms`.
  - With `wms`, an allocation with no WMS connected, and every wave
    reprioritize, now return `NOT_APPLIED` instead of success.
- **Labor allocation priority:** an allocation without `priority` keeps the
  task's existing priority. Callers that relied on the old reset to `medium`
  must pass `priority` explicitly.
- **Governed writes in Compose (opt-in):** set
  `MAIW_DEPLOYMENT_PROFILE=reference_governed` and a fresh
  `MAIW_OPERATOR_WRITE_TOKEN` (≥ 32 characters) in `deploy/compose/.env`.
  - Write callers and readers of `/api/v1/executions` must send
    `X-Maiw-Operator-Token`.
  - The bundled frontend strips that header by design, so governed writes
    from the UI are refused.
- **Compose state volume:** the backend now uses the `maiw_state` volume.
  - Remove it only when you intend to discard procedures, governance and the
    execution journal.
  - The backend now declares a dependency on the four MCP containers in
    every profile, so Compose starts them first.
- **Dependencies:** FastAPI 0.162.0 / Starlette 1.10.0 in the image.
  `requirements.txt` now has upper bounds (`fastapi<0.163`,
  `starlette<1.11`).
- **New setting:** `RATE_LIMIT_FAIL_MODE` (default `open`). Set `closed` to
  reject requests when the limiter is unavailable.
- **Request size:** oversize chunked requests now get 413. Clients that
  streamed large bodies past the limit will see it.
- **Frontend container port:** 8080 inside the container (published as 3001
  by Compose). Hot reload is no longer containerised; run `npm start` in
  `src/ui/web`.
- **MinIO:** the image is now `pgsty/minio` (third-party, pinned).
- **Demo API:**
  - `/demo/approve` can return `202` (unknown) and `409` (reconciliation
    required);
  - fault and restore injection no longer need `asset_id`.

## Known limitations (v2.1.0)
- **Release checks not run for this candidate:**
  - The internal NGC MAIW pytest suite has not run (see above).
  - The v2.0.1-style release gate has **not yet been run on this candidate**:
    reference-host preflight and smoke, plus live hosted Nemotron 3 Super and
    3.5 Lightning through ModelGateway.
  - The Compose deployment test runs without `NVIDIA_API_KEY`, so it makes no
    live model calls.
- **Reference (non-Compose) deployment:** the PostgreSQL labor and wave
  providers were not qualified there, and the runbook still documents
  equipment-only governed writes.
- **Rate limiter:** it still fails open by default; `closed` is opt-in.
- **Upload and legacy routes:** `POST /api/v1/document/upload` and the legacy
  read routes are unauthenticated. The size limit now applies to chunked
  bodies. Run on a trusted network.
- **No create routes:** there is no HTTP route to start a procedure or submit
  governance, so the restart check covers the execution journal only.
- **Reconciliation:** it infers execution from state. The labor and wave
  strategies are weaker than equipment's: neither has a canonical HTTP write
  route, and labor and wave writes in Compose are exercised directly against
  the MCP tools.
- **Single node:** the execution journal and the unresolved-target guard are
  single-node.
- **`/version` in Compose:** a Compose-built backend reports
  `0.0.0 (unknown)`, because Compose does not pass `GIT_SHA` / `BUILD_TIME`
  build arguments.
- **Unhardened images:** `Dockerfile` (combined) and `Dockerfile.mcp` still
  use `python:3.11-slim` with `curl`. The #149 hardening covered the backend
  and frontend images only.
- **Residual image findings:** the backend image has 8 Trivy high findings in
  Essential Debian packages with no fix available, which need VEX statements.
  The nSpect rescan of rebuilt images happens outside this repository.
- **UI build toolchain:** `npm audit` findings remain in the `react-scripts`
  toolchain. They are build-time only and not in the runtime image.
- **Carried over from v2.0.1:**
  - The managed OpenShell gateway is loopback-only with TLS off.
  - The legacy `src/api/services/llm/nim_client.py` keeps its old cache key.
  - Install from a shell with `PYTHONPATH` unset.

## Merged pull requests since v2.0.1
| PR | Commit | Title |
|---|---|---|
| #147 | `f2c7c81` | docs(release): align v2.0.1 notes and setup guidance |
| #148 | `ba959f8` | fix(demo): resolve fault-injection targets from the active DataPack world |
| #149 | `38ba930` | fix(security): harden backend/frontend images for NSPECT-NJMX-9GQU |
| #151 | `08d3141` | fix(image): ship demo evaluation artifact; report build GIT_SHA in /version |
| #150 | `3a3b03e` | fix(deploy): replace unavailable minio image with pgsty/minio |
| #152 | `44909e1` | fix(demo): make F06 ambiguous-write flow work end to end |
| #153 | `638bfdb` | fix(api): startup crash on FastAPI 0.162, enforce body size on streamed requests, configurable rate-limit fail mode |
| #154 | `737f80a` | fix(deploy): durable state + DB access for Compose backend; gate deployment on /api/v1/ready |
| #155 | `97c17ed` | fix(mcp): MCP domain containers crash at startup; probe all four in the deployment workflow |
| #156 | `b8b0a13` | feat: public e2e smoke + restart durability in the deployment workflow; PostgreSQL labor/wave MCP providers |

Full diff: [`v2.0.1...b8b0a13`](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/compare/v2.0.1...b8b0a139effa67ba18a4cc23a46a696468cd7056)
