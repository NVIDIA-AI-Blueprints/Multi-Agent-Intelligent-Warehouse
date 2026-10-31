# MAIW v2.1.0 — Release Notes

**Status:** not yet tagged or published. **Validated code commit:** `main`
`c19f75f3a3a753d90687e8a6e7c7b0b1358d9ffe` (PR #162). Commits after it on
`main` change only release documentation. The latest published release is
still `v2.0.1` (`53a27e61…`).

> **v2.0.1 users: MEDIUM and HIGH reasoning fail on hosted endpoints.**
> NVIDIA retired the hosted Nemotron 3 Super endpoint
> (`nvidia/nemotron-3-super-120b-a12b`) on **2026-10-19**. v2.0.1 routes MEDIUM
> reasoning, HIGH reasoning and CRITICAL-risk requests to Super by default, so
> since that date those requests return **503** on `integrate.api.nvidia.com`.
> LOW reasoning (Lightning) still works. v2.0.1 has no configuration-only
> workaround: disabling Super there leaves those requests with no eligible
> model. **Upgrade to v2.1.0**, or point `NEMOTRON_SUPER_*` at a self-hosted
> Super NIM. See "Hosted Nemotron 3 Super retired" below.

## Summary

v2.1.0 restores model serving after the hosted Nemotron 3 Super retirement,
and makes the Docker Compose deployment start, serve and verify the full
governed stack. Since v2.0.1:

- **New model defaults (#159, #160):** LOW and MEDIUM reasoning use
  Nemotron 3.5 Lightning; HIGH reasoning and CRITICAL risk use Nemotron 3
  Ultra. Super is disabled by default and can be re-enabled for a self-hosted
  Super NIM. Preflight now verifies that each enabled model is actually
  served, not only listed.
- **Localhost by default (#162):** every published Compose port and the UI
  development server bind `127.0.0.1`. Before, Compose exposed the database,
  Redis, MinIO, the API and the MCP servers on every host interface. The README
  quickstart now works from a clean checkout.
- **Release timing is manual (#158):** merging to `main` no longer publishes
  a release.
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

## Verification on the validated code commit (`c19f75f`)

### CI and the Compose deployment test

| Check | Result |
|---|---|
| CI/CD Pipeline ([run 41238507435](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/actions/runs/41238507435)): CORE CI pytest (Python 3.11) | **3258 passed, 13 skipped, 0 failed** |
| CI/CD Pipeline: UI Jest | **991/991** (42 suites) |
| CI/CD Pipeline: Security Scan | passed |
| CodeQL | passed ([run 41238506439](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/actions/runs/41238506439)) |
| Deployment test ([run 41238507342](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/actions/runs/41238507342)), Compose, profile `reference_governed`, ports bound to `127.0.0.1`, UI dev server through `setupProxy.js` | passed, every gating step green; `docker ps` shows every published port on `127.0.0.1` |
| ↳ Verify: API health checks (gates on `/api/v1/ready`) | passed |
| ↳ Verify: MCP domain servers (4 containers running, restarts 0, `initialize` + `tools/list`) | passed, 13 tools |
| ↳ **E2E: MCP tool calls** | passed |
| ↳ **E2E: durability across backend restart** | passed |
| Internal NGC MAIW pytest suite | **NOT RUN**: see below |

### Reference-host release gate (2026-10-31)

Run on the qualification host against `e789069` (#160), following
`docs/operations/REFERENCE_DEPLOYMENT_RUNBOOK.md`, with live hosted models on
`integrate.api.nvidia.com`. The API key was entered at a hidden prompt and was
not written to `.env`, files or logs.

| Step | Result |
|---|---|
| Provider probe (`check_model_config.py --provider-probe`) | Lightning and Ultra listed **and served**; each answered as the dispatched model |
| Managed OpenShell gateway, reference DB, sandbox | created and ready |
| Preflight | **34 passed, 0 failed** |
| Start and status | "MAIW IS USABLE" |
| Smoke test | **17 passed, 0 failed**, including a live inference with physical model identity verified |
| In-sandbox probe | HIGH reasoning → **Ultra, HTTP 200, `identity_verified=true`**. No host secrets in the sandbox; every governed write denied (inference token rejected as operator credential); direct provider and internet access blocked; missing or wrong token → 401; routing-field injection → 422 |
| Live identity through `/api/v1/inference` | HIGH → `nvidia/nemotron-3-ultra-550b-a55b`; MEDIUM and LOW → `nvidia/nemotron-3.5-lightning-30b-a3b`. Provider-reported model = dispatched model, `identity_verified=true`, `approved_family=true` for all three |

The first gate run, on `3a63397` (#159), stopped at the in-sandbox probe:
hosted Ultra rejected the `reasoning_budget` field that MAIW sent with HIGH
requests. #160 fixed that, and the gate above passed in full.

The gate was not rerun on `c19f75f`. The only change after `e789069` that is
not documentation is #162. It changes the Compose files, the UI development
server (`package.json`, `craco.config.js`, `setupProxy.js`) and tests, and no
Python under `apps/`, `packages/`, `src/` or `scripts/`. The reference
deployment runs none of the files #162 changed.

### Internal NGC suite

**The internal NGC pytest suite still could not run.** The deployment
workflow's MAIW pytest step needs the internal NGC test image
(`nvcr.io/…/blueprint-github-test-image`). On `c19f75f` the pull was denied
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
The release adds functionality and changes shipped defaults. It does not
only fix bugs:
- **Changed model defaults:** Super is disabled and Ultra enabled by default,
  and MEDIUM reasoning moves from Super to Lightning (#159).
- **New functionality:** a PostgreSQL backend for the labor and wave MCP
  servers, with a selection variable for each. Before, labor and wave could
  not be served from MAIW's own database (see the v2.0.1 known limitations).
- **Changed default:** the labor and wave servers now use that backend by
  default instead of the WMS adapters.

No API is removed.

## Changes since v2.0.1

### Hosted Nemotron 3 Super retired: new model defaults (#159, #160)
NVIDIA retired the hosted Super endpoint on 2026-10-19. The model catalogue
(`/v1/models`) still lists it, but every completion returns HTTP 404
("Function … Not found for account").

- **Routing defaults (#159):**

  | Request | v2.0.1 | v2.1.0 |
  |---|---|---|
  | LOW reasoning | Lightning | Lightning |
  | MEDIUM reasoning | Super (503 since 2026-10-19) | **Lightning** |
  | HIGH reasoning | Super (503 since 2026-10-19) | **Ultra** |
  | CRITICAL risk | Super (503 since 2026-10-19) | **Ultra** |
  | `NEMOTRON_SUPER_ENABLED=true` (self-hosted Super) | — | same routing as v2.0.1 |

  - Enabled by default: Lightning and Ultra. Disabled: Super, Nano, Nano
    Omni.
  - Fallback chains: `nano → super → lightning` and `super → ultra`.
  - **The safety policy is unchanged:** HIGH reasoning and CRITICAL risk
    still require a high-capability model (Super or Ultra). With both
    disabled, those requests fail closed with `ModelUnavailable` and no
    provider call; they are never downgraded to Lightning.
  - The legacy direct clients (`LLM_MODEL`, `GUARDRAILS_MODEL`) default to
    Lightning instead of Super.
- **Preflight verifies serving, not only listing (#159):**
  `scripts/lib/check_model_config.py --provider-probe` sends one minimal
  completion to each enabled, approved model and fails unless the provider
  answers 200 **as that model**. Preflight reports a listed-but-not-served
  model as `FAIL  provider does not serve <role> model`, with remediation.
  Without an API key the dispatch check is skipped with a `WARN`.
- **Thinking mode on hosted Ultra (#160):** HIGH reasoning turns Nemotron
  thinking on. Both NIM clients used to send `reasoning_budget`
  (`LLM_REASONING_BUDGET`, default 0) with it. Hosted Ultra rejects that field
  at any value with HTTP 400 ("thinking_token_budget is not yet supported by
  the V2 model runner"). The clients now set
  `chat_template_kwargs.enable_thinking` explicitly (`true` for HIGH, `false`
  otherwise) and send `reasoning_budget` only when a budget above 0 is
  configured.

### Default network exposure and first run (#162)
An external audit of `dd1b40c` found that the default Compose deployment
published every port on all host interfaces, and that the README quickstart
did not work.
- **Compose binds `127.0.0.1`.** Docker publishes a port on every host
  interface unless the mapping names a host IP. All Compose files now bind
  every published port to `127.0.0.1`.
  - The datastores, the four MCP domain servers and the local NIM have no
    override. The MCP write tools trust the decision IDs their caller sends,
    so only the backend, over the Compose network, may reach them.
  - nginx (3000), the frontend (3001) and the API (8001) follow
    `MAIW_PUBLISH_ADDRESS` (default `127.0.0.1`). Widen it only behind your own
    authentication and TLS; governed API writes still need
    `MAIW_OPERATOR_WRITE_TOKEN`.
- **UI development server binds `127.0.0.1`.** `npm start` was hard-coded to
  `HOST=0.0.0.0`; `HOST` and `PORT` are now overridable.
- **The development server's `/api` proxy now runs `src/setupProxy.js`.**
  Before, craco removed the hook that loads it and installed its own proxy,
  and `setupProxy.js` used http-proxy-middleware 2.x handler options that 3.x
  ignores. So a browser-supplied `X-Maiw-Operator-Token` was forwarded and
  `MAIW_UI_OPERATOR_WRITE_TOKEN` was never applied. Now the browser header is
  stripped, the configured token is added on the three equipment write routes
  only, and `MAIW_API_PROXY_TARGET` overrides the API target.
- **README quickstart, verified from a clean clone:**
  - install `requirements.txt` before the editable packages (the backend
    imports `src/api`, which needs it);
  - API on port 8001, the UI proxy's target (was 8000);
  - `npm start` on port 3001 (`npm run dev` does not exist);
  - `python -m maiw_world generate` (the DataPack is committed, so this is
    optional);
  - removed the references to `deploy/brev/` and Helm, which do not exist.
  - The getting-started notebook had the same port and command errors.
- **DEPLOYMENT.md** no longer advises binding `0.0.0.0`; it describes SSH
  tunnelling and deliberate, authenticated publishing.
- `tests/api/test_default_network_exposure.py` (13 tests) pins all of this.

### Release process (#158)
- `ci-cd.yml` no longer runs semantic-release on every push to `main`, so a
  merge cannot publish a release.
- `release.yml` ("Release preview") is a manual, `main`-only dry run.
- `docs/operations/RELEASING.md` documents the procedure: choose the
  candidate, preview, run the release gate, write notes naming the validated
  code commit, merge the notes, verify the resulting `main` commit, then tag
  it and publish with `gh release create --notes-file`.

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
- **Model defaults changed.** If your `.env` sets none of
  `NEMOTRON_*_ENABLED`, v2.1.0 serves LOW/MEDIUM from Lightning and
  HIGH/CRITICAL from Ultra, with the same `NVIDIA_API_KEY`.
  - **Self-hosted Super:** set `NEMOTRON_SUPER_ENABLED=true` and point
    `NEMOTRON_SUPER_*` at your NIM to keep the v2.0.1 routing.
  - **`.env` files that set `NEMOTRON_SUPER_ENABLED=true` for the hosted
    endpoint** must remove it (or set `false`); otherwise preflight fails with
    `provider does not serve super model`.
  - **Ultra is slower and costlier than Super** (the registry records about
    31 s for a short prompt). Expect higher latency on HIGH and CRITICAL
    requests.
  - **MEDIUM reasoning now uses a smaller model** (Lightning instead of
    Super).
  - `LLM_REASONING_BUDGET`: leave it at 0 with hosted Ultra. A value above 0
    is sent as `reasoning_budget`, which hosted Ultra rejects.
- **Compose ports are localhost-only (#162).** Clients on other machines can
  no longer reach the database, Redis, MinIO, Kafka, Milvus, the MCP servers,
  the API or the UI directly. Use an SSH tunnel
  (`ssh -L 3001:127.0.0.1:3001 -L 8001:127.0.0.1:8001 <host>`), or set
  `MAIW_PUBLISH_ADDRESS=0.0.0.0` in `deploy/compose/.env` to publish nginx,
  the frontend and the API behind your own authentication and TLS. There is
  deliberately no setting to publish the datastores or MCP servers.
- **UI development server (#162):** `npm start` listens on `127.0.0.1`; set
  `HOST=0.0.0.0` to change that. With `MAIW_UI_OPERATOR_WRITE_TOKEN` set, it
  now actually adds the operator credential to equipment writes, so anyone who
  can reach the server can perform them.
- **Releases are manual (#158):** merging to `main` no longer creates a tag
  or GitHub Release. See `docs/operations/RELEASING.md`.
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
- **Release checks not run:**
  - The internal NGC MAIW pytest suite has not run (see above).
  - The Compose deployment test runs without `NVIDIA_API_KEY`, so it makes no
    live model calls. Live models were verified on the reference host only.
- **MCP write boundary has no server-side authorization.** The MCP write
  tools trust the `proposal_id` / `decision_id` their caller sends and do not
  verify the approval themselves; the API's DecisionEngine and
  ActionExecutor enforce it before calling them. #162 keeps the MCP ports on
  `127.0.0.1` and the Compose network. Do not expose MCP servers to untrusted
  networks: a remote MCP deployment needs authentication at the MCP server
  (the client-side `MCPAuthConfig` bearer header has no server-side check).
- **Inventory MCP container reports `unhealthy` in Compose.** Its Compose
  healthcheck (since #77) curls `/health`, which the MCP server does not
  serve. The server works: the deployment test's MCP probe gets its 2 tools.
  The deployment workflow gates on running with 0 restarts plus the MCP
  probe, not on Docker health.
- **Quickstart dependency warning:** `requirements.txt` pins
  `uvicorn==0.30.1`, while `mcp` 2.3 needs `uvicorn>=0.31.1`. Installing
  `requirements.txt` prints a resolver conflict; the editable-package install
  that follows upgrades uvicorn and `pip check` is clean.
- **Hosted endpoints are not a production SLA.** build.nvidia.com endpoints
  can be retired, as Super was. For production, self-host the models as NGC
  NIMs.
- **Self-hosted Super was not re-qualified** for this release. The opt-in
  contract tests that need a reachable Super NIM
  (`MAIW_PHASE20B_NIM_URL`) were skipped.
- **Model Lab display:** the Model Lab page still shows Super as
  "AVAILABLE". It renders static benchmark data, not live availability.
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
| #158 | `4b81451` | ci(release): no automatic releases; release workflow is a manual dry-run preview |
| #159 | `3a63397` | fix(models): hosted Nemotron 3 Super is retired; default HIGH/CRITICAL to Ultra, MEDIUM to Lightning |
| #160 | `e789069` | fix(models): don't send reasoning_budget unless configured; hosted Ultra rejects it |
| #157 | `88b73ae` | docs(release): draft v2.1.0 changelog and release notes (documentation only) |
| #161 | `dd1b40c` | docs(release): finalize v2.1.0 notes (documentation only) |
| #162 | `c19f75f` | fix(deploy): bind Compose ports and the UI dev server to localhost; make the quickstart work from a clean checkout |

Full diff of the validated code: [`v2.0.1...c19f75f`](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/compare/v2.0.1...c19f75f3a3a753d90687e8a6e7c7b0b1358d9ffe)
