# Architecture and Security-Process Inventory

**Snapshot:** `main` at `0fbcb69` (2026-11-02). Release `v2.1.0` = `2fdd9fe` (annotated tag object `f95dd12`, published 2026-10-31).
**Repository:** https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse (canonical).

| | |
|---|---|
| Mirror | `T-DevH/Multi-Agent-Intelligent-Warehouse`, a contributor fork used for development. It is not authoritative. Its workflow files reached upstream once, in #71 (2026-08-20), and disabled SonarQube and CodeQL there (`sonarqube-root-cause-analysis.md`). |
| Branches and tags | The release branch is `main`. Tags `v2.0.0`, `v2.0.1` and `v2.1.0`; v2.1.0 is the Latest release. |
| Release entrypoint | `uvicorn maiw_api.app:app` (`apps/api/maiw_api/app.py`), the only release composition root. `src/api/app.py` is a legacy development server. |
| Supported deployment | A single trusted host, with every port on `127.0.0.1` and remote UI access through an SSH tunnel (`SECURITY.md`, Supported Deployment Boundary). |

## First-party source areas

Lines are non-test source lines, counted on `0fbcb69`.

| Area | What it is | Lines | Shipped in |
|---|---|---|---|
| `apps/api/maiw_api` | Canonical API: routers, governed writes (operator token), Copilot, demo, reconciliation, origin guard | Python 21k | backend image |
| `packages/maiw-decision` | DecisionEngine and policy | — | backend, MCP |
| `packages/maiw-execution` | `ActionExecutor`, execution journal | — | backend |
| `packages/maiw-agents` | Domain agents, SOP engine, deep-agents integration | — | backend |
| `packages/maiw-mcp`, `maiw-contracts` | MCP client/server library, tool contracts | — | backend, MCP |
| `packages/maiw-models`, `maiw-state`, `maiw-skills`, `maiw-world` | ModelGateway (NIM), WarehouseState, skills, simulation world | all `packages/`: Python 49k | backend (`maiw-world` used by the demo) |
| `mcp_servers/{equipment,inventory,labor,wave}` | MCP domain servers (streamable HTTP, unauthenticated by design) | Python 3k | 4 MCP images |
| `src/api` | Legacy routers (mounted read-only, or curated: document upload), auth, services, agents | Python 61k | backend |
| `src/adapters` | WMS, ERP, IoT, RFID and time-attendance adapters (optional external systems) | Python 10k | backend, MCP |
| `src/retrieval`, `src/memory` | SQL, vector and hybrid retrieval, caching | Python 13k | backend, MCP |
| `src/ui/web` | React UI | TS/JS 65k | frontend image (compiled bundle) |
| `integrations/nemoclaw` | NemoClaw / OpenShell sandbox integration | Python 2k | not in images |
| `scripts/` | Setup, deployment, data, operations and security tooling | Python 10k | not in images |
| `agents/sops` | SOP definitions (YAML) | — | backend |
| `deploy/` | Compose, Docker and OpenShell configuration | — | deployment |
| Dockerfiles | `Dockerfile.backend`, `.frontend`, `.mcp`, `Dockerfile`, `Dockerfile.rapids` | — | — |

## Security-process coverage matrix

Legend:
- ✅ covered and running;
- ⚠️ configured but not running, or partial;
- ❌ not covered.

"→" shows the change in a pending PR.

| Area | SonarQube | CodeQL | Dependency scanning | Secret scanning | CI tests | Coverage measured | SBOM |
|---|---|---|---|---|---|---|---|
| `apps/` | ❌ (scope was `src`) → ✅ #226 | ⚠️ not run on main since 2026-08-17 → ✅ #226 | ✅ via `requirements*.txt`; ⚠️ `apps/api/pyproject.toml` not read by Dependabot | ✅ | ⚠️ `tests/api` covers it; `apps/api/tests` (7 files) and `apps/api/maiw_api/demo/tests` (3) are **not run** | ✅ | ✅ backend image → #228 |
| `packages/` | ❌ → ✅ #226 | ⚠️ → ✅ #226 | ⚠️ per-package `pyproject.toml` not read by Dependabot; resolved versions are in the image scans and SBOMs | ✅ | ✅ `packages/maiw-agents/tests`; `packages/maiw-world/tests` (12 files) as its own CI step since 2026-11 | ✅ | ✅ (images) |
| `mcp_servers/` | ❌ → ✅ #226 | ⚠️ → ✅ #226 | ✅ (MCP image) | ✅ | ✅ `tests/mcp` | ❌ not in `--cov` | ✅ MCP image → #228 |
| `src/` (Python) | ⚠️ last analysis 2026-01-05 → ✅ #226 | ⚠️ → ✅ #226 | ✅ | ✅ | ✅ unit, contract and api, but **21 files `--ignore`d**; `src/adapters/{wms,iot}/tests` not run | ✅ | ✅ (images) |
| `src/ui/web` | ⚠️ (in `src`), stale | ⚠️ → ✅ #226 | ✅ Dependabot npm, Trivy fs (dev dependencies included) | ✅ | ✅ Jest (991 tests) | ❌ disabled in CI | ✅ UI bundle → #228 |
| `integrations/` | ❌ → ✅ #226 | ⚠️ → ✅ #226 | ❌ | ✅ | ⚠️ contract tests, some skipped | ❌ | n/a (not shipped) |
| `scripts/` | ❌ → ✅ #226 (coverage excluded) | ⚠️ → ✅ #226 | ⚠️ `scripts/requirements_synthetic_data.txt` (Trivy fs) | ✅ | ❌ | ❌ | n/a |
| Dockerfiles and images | ❌ → ✅ #226 (Docker rules) | n/a | ✅ Trivy image scan of backend, frontend and MCP, gating fixable HIGH and CRITICAL (#222); ⚠️ Dependabot does not update `ARG` base images | ✅ | ✅ static image tests | n/a | ✅ #228 |
| Root release tooling (`package.json`) | n/a | ⚠️ | ✅ Trivy fs (dev); ⚠️ no Dependabot version updates | ✅ | n/a | n/a | n/a (not shipped) |
| GitHub Actions workflows | n/a | ❌ (the `actions` language is available but not enabled) | ✅ Dependabot github-actions | ✅ | ✅ workflow guard tests | n/a | n/a |

### Gaps (not fixed by the pending PRs)

1. **Test files never run in CI:**
   - 21 files are explicitly `--ignore`d in the CORE pytest command;
   - 24 more sat in directories CI did not collect: `apps/api/tests` and `apps/api/maiw_api/demo/tests` (run since #287), `packages/maiw-world/tests` (run since 2026-11), and `src/adapters/{wms,iot}/tests` (still not run; 21 of 51 fail);
   - `tests/integration`, `performance`, `quality`, `demo` and `real_sandbox` are not part of CORE CI.
2. **Coverage:** `mcp_servers/` is not measured, and UI (Jest) coverage is disabled because of an Istanbul and Node incompatibility.
3. **Dependabot:** it reads only the root Python manifests. Per-package `pyproject.toml` files and Dockerfile `ARG` base images are not tracked. Image scanning (#222) compensates for the runtime images.
4. **Secret scanning:** enabled, with 0 open alerts. **Push protection is disabled**, and so are AI detection, non-provider patterns and validity checks. These are repository settings, not changed here: owner decision.
5. **CodeQL default setup** is "not configured". The repository relies on `codeql.yml`, restored in #226. Actions-workflow analysis is not enabled.
6. **Codecov:** `ci-cd.yml` uploads `coverage.xml` to codecov.io with `codecov/codecov-action@v3`. This is pre-existing; owners should confirm it is an approved external service.

## Runtime interfaces and trust boundary

| Interface | Port | Authentication | Exposure (default) |
|---|---|---|---|
| API (`maiw_api`) | 8001 | Operator write token for governed writes; JWT for auth routes; reads open | `127.0.0.1`; `MAIW_PUBLISH_ADDRESS` widens it |
| Frontend (nginx), dev server | 3001, 3000 | none (static and proxy) | `127.0.0.1` |
| MCP domain servers | 8765–8768 | **none** (caller-supplied decision IDs recorded, not verified) | `127.0.0.1`, no override |
| PostgreSQL/Timescale, Redis, MinIO, Milvus, Kafka, etcd | various | development credentials | `127.0.0.1` |
| NVIDIA NIM (hosted) | outbound HTTPS | `NVIDIA_API_KEY` | outbound only |

Browser cross-origin writes are refused by the origin guard (#223, #224). Log injection is neutralised process-wide (#229).
