# MAIW v2.1.1 — Release Notes

**Status:** released 2026-11-06. **Validated code commit:** `main`
`4259fa37aa3676bbcc3378f00d067d9bdcc01174` (PR #252). Tag `v2.1.1` is on
`6d1395b`, the `main` commit that merged these notes (#253); it differs from
the validated code commit only in documentation. Previous release: `v2.1.0`
(`2fdd9fea…`).

v2.1.1 is a security and bug-fix release. **It changes two behaviors that can
break existing clients; read "Compatibility" first.**

## Validation

| Validation | Result |
|---|---|
| CI/CD Pipeline, CodeQL | PASS (`4259fa3`): CORE CI pytest **3385 passed, 13 skipped, 0 failed** (coverage 51.36%, floor 48%); UI Jest **1010/1010** (46 suites); Security Scan and Trivy image scans (backend, frontend, MCP) passed ([CI run](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/actions/runs/42111328437), [CodeQL run](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/actions/runs/42111328413)) |
| Deployment test (deploy, readiness, MCP tool calls, restart durability) | PASS ([run](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/actions/runs/42111328531)) |
| Internal NGC MAIW pytest suite | **NOT RUN**: could not pull the internal test image (requires internal NGC org access) ([run](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/actions/runs/42111328531)) |
| Release gate on the reference host | PASS (2026-11-05, on `4259fa3`; details below) |
| SonarQube | analysis `eb6b331f-47c1-4647-86f9-3486418d02f0` of `4259fa3` (dated 2026-11-06 04:47 UTC, processed 05:00 UTC), version `2.1.1-rc.1`, quality gate **ERROR**: 46 issues of prioritized security rules and 128 HIGH issues overall; 0 blocker issues, and every new-code condition passes. **Not release-blocking for v2.1.1, by maintainer decision (2026-11-06).** This departs from `docs/operations/RELEASING.md`, which asks for a written Blueprints SRE disposition of a failing gate; none was obtained. Triage: `docs/security/sonarqube-remediation-report.md` ("Analysis of `4259fa3`"). Run manually from an NVIDIA-network host; CI's own run for this commit ([run](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/actions/runs/42113662581)) could not reach `sonar.nvidia.com` (exit 3) |
| nSpect OSS scan (NSPECT-NJMX-9GQU) | 2026-11-05, program version **MAIW v2.1.1**, source at `4259fa3`: 0 Critical, 2 High, 10 Medium, 4 Low. **PASS:** both High findings carry exceptions approved 2026-11-06 in the Exception Tracker: `react-dev-utils` Not Affected **EXC-HPU1-JZI6**, `svgo` Resolved **EXC-TNK9-0X62** (vendor fix in 2.8.3); see below |
| SBOM submitted to nSpect | 2026-11-06: `maiw-v2.1.1-4259fa3.cdx.json` uploaded to MAIW v2.1.1 (Manage SBOM → Upload an SBOM). It merges the CI SBOMs `sbom-backend`, `sbom-frontend` (frontend image and UI bundle) and `sbom-mcp` of the CI run above: CycloneDX 1.6, 1642 components, sha256 `800278356c94534946dffabe9db35a9063c673f80aa5bd4afb3484c7b9f35c1b` |

## Compatibility

Two changes can break existing clients:

1. **Cross-origin browser writes are refused (#223, #224).** The API now
   answers **403 `CROSS_ORIGIN_REQUEST_FORBIDDEN`** to a POST, PUT, PATCH or
   DELETE whose `Origin` header is neither listed in `CORS_ORIGINS` nor the
   API's own loopback origin.
   - Requests without an `Origin` header (curl, scripts, MCP clients, server
     to server) are unchanged.
   - A UI served from another origin needs that origin in `CORS_ORIGINS`. This
     includes an SSH tunnel to a different local port, for example
     `http://localhost:3011`.
   - A `*` entry in `CORS_ORIGINS` widens CORS reads only. It never admits
     cross-origin writes.
   - Why: a web page on another origin, opened in a browser on the host, could
     upload a document (starting the document pipeline and its model calls)
     and send other simple cross-origin POSTs; CORS only hid the response.
2. **Document approve/reject routes removed from the shipped app (#195).**
   `POST /api/v1/document/approve/{id}` and `POST /api/v1/document/reject/{id}`
   are no longer mounted, so they return 404. They never recorded a decision
   or reached a WMS. The legacy router that still defines them answers
   **501**. Clients that called them received a success that did nothing; they
   should stop calling them.

No other API route is removed and no request field changes. Two
development and optional-feature defaults also change (`npm start` opens no
browser; Nemotron Parse has no hosted default); see "Upgrade notes".

## Reference-host release gate (2026-11-05)

Run on the qualification host (H100 NVL, NemoClaw 0.0.124, OpenShell 0.0.116)
against `4259fa3`, following
`docs/operations/REFERENCE_DEPLOYMENT_RUNBOOK.md`: profile `reference`,
`MAIW_SANDBOX_MODE=required`, managed OpenShell gateway, live hosted models on
`integrate.api.nvidia.com`. Approved bindings: Lightning
(`nvidia/nemotron-3.5-lightning-30b-a3b`) and Ultra
(`nvidia/nemotron-3-ultra-550b-a55b`) enabled; Super and Nano disabled, as
shipped. No binding was disabled for the gate. The API key was entered at a
hidden prompt and was not written to `.env`, files or logs.

| Step | Result |
|---|---|
| Provider probe (`check_model_config.py --provider-probe`) | Lightning and Ultra each answered 200 **as the approved model** |
| Managed OpenShell gateway, reference DB, sandbox | created and ready |
| Preflight | **34 passed, 0 failed** |
| Start and status | `/api/v1/ready` 200, "USABLE", every readiness component ready. The status script's own provider probe printed one FAIL line: Lightning HTTP **429** (rate limit), the gate's fourth probe within about 20 s. The script exits 0 by design (provider reachability is not a readiness component); three seconds later Lightning answered 200 again (below) |
| Smoke test | **17 passed, 0 failed**, including a live inference with the provider-reported model verified |
| Live calls through `POST /api/v1/inference` | **4/4**, HTTP 200, `identity_verified=true`, `approved_family=true`, provider-reported ID = resolved ID: LOW → Lightning; MEDIUM → Lightning; HIGH → Ultra (3.8 s); MEDIUM with CRITICAL risk → Ultra (1.4 s). The MEDIUM Lightning call was answered from MAIW's 5-minute response cache, filled seconds earlier by the smoke test's live call with the same prompt and routing |
| In-sandbox probe | inference from the sandbox → **Ultra, HTTP 200, identity verified**. Missing or wrong token → 401; routing-field injection → 422; every governed write denied for every sandbox credential; direct provider and internet access blocked; no host secret in the sandbox |
| Stop and teardown | passed; durable state preserved |

## nSpect findings for MAIW v2.1.1

The scan of `4259fa3` has the same 16 findings as the 2026-11-05 scan of
`9aed676`; no dependency manifest changed between them. Every finding is in
the UI's npm lockfile or a Python minimum version. None is in a shipped image:
the frontend image serves static files from nginx and contains no npm
packages. Of the npm packages, only `react-router` and `react-is` are
compiled into the browser bundle; the rest are build or development-server
tooling pulled in by `react-scripts` 5.

| Severity | Package | Disposition |
|---|---|---|
| High | `react-dev-utils` 12.0.1 (BDSA-2026-18203 / CVE-2026-14802) | **Not Affected exception EXC-HPU1-JZI6** (justification `requires_configuration`), approved 2026-11-06. OS command injection in `openBrowser` (macOS). No fixed release exists. Since #251 the UI start script defaults `BROWSER=none`, so `openBrowser` never runs; a test pins this. Development server only. Removed when the UI leaves `react-scripts` |
| High | `svgo` 2.8.4 (BDSA-2026-27126 / CVE-2026-73650) | **Resolved exception EXC-TNK9-0X62**, approved 2026-11-06. GitHub's advisory (GHSA-2p49-hgcm-8545) lists 2.8.3 as the 2.x fix, so 2.8.4 is patched; Dependabot raises no alert. Build-time only (cssnano / postcss-svgo) |
| Medium | `react-router` 6.30.6 (CVE-2026-53666) | SSR hydration only; MAIW's UI is a client-rendered SPA. The fix is 7.18.0, a major upgrade, planned after this release |
| Medium | `react-is` 19.2.5 (CVE-2026-23870) | Mismatch: the advisory covers `react-server-dom-*`, not `react-is` |
| Medium | `serialize-javascript` 7.0.5 | Real, build-time only (CSS and Rollup minifier plugins). Fixed in 7.1.3; the npm override will be raised after this release |
| Medium | `postcss-selector-parser` 6.1.5 | GitHub's advisory lists 6.1.5 as fixed; discrepancy |
| Medium (6), Low (3) | `uri-js` 4.4.1 (2), `uuid` 8.3.2 (Medium and Low), `inflight` 1.0.6, `braces` 3.0.3, `minimatch` 9.0.9, `@tootallnate/once` 1.1.2, `glob` 10.5.0 | `react-scripts` build and development-server chain, not in the browser bundle or any image |
| Low | `requests` 2.32.4 | nSpect reads the `requirements.txt` minimum as the installed version. The images install 2.34.2. The minimum will be raised after this release |

Details: `docs/security/nspect-reconciliation.md`.

## Changes since v2.1.0

### Security
- **Cross-origin writes refused** (#223, #224): see "Compatibility".
- **No credentials or raw request data in logs** (#229). The validation-error
  handler logged pydantic's `errors()`, whose `input` is the request body, so
  a login request missing a field **logged the password in plain text**. It
  now logs only where and why validation failed. Request values are sanitized
  across the HTTP-exception handler, login, the inventory and equipment
  routes, the JWT `alg` check and uploads, and the SQL retriever no longer
  logs bound parameters. A process-wide guard keeps every log message on one
  line, so request values cannot forge log entries (SonarQube
  `pythonsecurity:S5145`, CWE-117/CWE-532).
- **No exception text in 5xx responses** (#223): the Copilot turn route and
  other shipped 5xx responses no longer return raw exception text, which could
  include connection strings or hosts.
- **Security headers and CORS are the outermost middleware** (#240, #243).
  Before, the 403, 413 and 429 responses of the origin guard, request-size
  limit and rate limiter carried no security headers, and the browser could
  not read a 413 or 429 from an allowed origin.
- **`npm start` no longer opens a browser** (#251): see the `react-dev-utils`
  finding above. Open http://localhost:3001 yourself, or set `BROWSER` to opt
  back in.
- **Images** (#222): CI builds and scans the backend, frontend and MCP images.
  Fixes from the first scan: frontend nginx 1.30.5 → 1.30.6; the MCP image
  drops `setuptools`, `wheel`, `pip` and the unused `curl`, and runs
  `apt-get upgrade`. `passlib` (unused, incompatible with `bcrypt` 5) is
  removed.
- **Dependency floors and overrides** matching what the images install:
  `langchain-core` ≥ 1.7.3 (#242), `starlette`, `langgraph`,
  `langgraph-checkpoint` (#245), and Python floors from Dependabot
  (#167–#214); UI overrides for `svgo` under `@svgr/plugin-svgo` (#244),
  `webpack-dev-server` 5.2.7 and `qs` 6.17.1 (#246), plus lockfile security
  updates (#197–#201, #203).

### Bug fixes
- **IoT:** the MQTT equipment adapter works on paho-mqtt 2.x (#202); the
  Modbus environmental adapter reads registers on pymodbus 3.x (#216); an
  alert acknowledgment or emergency dispatch that did not happen is no longer
  reported as done (#241); WebSocket integrations are qualified on websockets
  17 (#217).
- **Skills:** the labor, wave and equipment skill factories build a working
  MCP client (#239).
- **Demo Mode:** `start_demo_mode.sh` starts a READY demo API (#235);
  `/api/v1/mcp/status` no longer returns 500 with in-memory MCP servers
  (#236); the API starts without PostgreSQL settings (#249); the UI shows
  demo API errors instead of failing silently (#247).
- **UI:** larger text (smallest text 12 px) and every page scrolls (#250).
- **Document:** Nemotron Parse no longer defaults to the hosted endpoint,
  which is retired on 2026-11-16, and no longer returns a hard-coded sample
  invoice at 0.91 confidence when unavailable (#252). It runs only when
  `NEMO_PARSE_URL` points at a self-hosted NIM. The shipped upload route does
  not use it.
- **Deploy:** the MCP domain containers have a working healthcheck (#196).
- **Data:** the all-SKU forecast generator no longer passes `random_state` to
  SVR (#231).

### CI, release process and evidence
- SonarQube analysis and CodeQL are restored as workflows (#226, #232, #237).
  SonarQube needs an NVIDIA-network runner, which is not configured yet.
- CycloneDX SBOMs for every image and the UI on every CI run (#228).
- Coverage across `src`, `apps` and `packages` with a 48% floor; Trivy fails
  on fixable CRITICAL findings (#196, #203).
- The internal NGC suite is its own commit check, reading NOT RUN when it
  cannot run (#225).
- `docs/operations/RELEASING.md` makes SonarQube, nSpect and SBOM
  release-blocking (#238).
- Dependabot scans the UI and groups routine updates (#166, #192, #193,
  #215).
- Removed the stale `requirements.lock` and the unused `langchain`
  dependency (#227).

### Documentation
- README Quickstart first, matching the UI, with a troubleshooting table
  (#248); Demo Mode `.env` guidance (#234).
- `SECURITY.md` states the supported deployment boundary: one trusted host,
  remote UI access through an SSH tunnel (#218).
- v2.1.0 security evidence package and readiness assessment (#230, #238).

## Upgrade notes
- **Browser clients on another origin:** add the UI's origin to
  `CORS_ORIGINS` (see "Compatibility").
- **Document approve/reject:** remove calls to these routes.
- **`npm start`:** no browser opens; set `BROWSER` to restore it.
- **Nemotron Parse:** set `NEMO_PARSE_URL` to a self-hosted NIM to use it; the
  hosted endpoint is retired on 2026-11-16.
- **Rebuild images:** the frontend (nginx 1.30.6) and MCP images changed.

## Known limitations (v2.1.1)
- **Release checks not run:** the internal NGC MAIW pytest suite (above). The
  Compose deployment test makes no live model calls; live models were
  verified on the reference host only.
- **SonarQube:** the analysis of `4259fa3` has quality gate ERROR and was
  released without an SRE disposition, by maintainer decision (see the
  validation table). CI cannot analyze until it has an NVIDIA-network runner.
  Triage: `docs/security/sonarqube-remediation-report.md`.
- **Default passwords in setup scripts:** `scripts/setup/create_default_users.py`
  and the demo data generators fall back to the password `changeme` when
  `DEFAULT_ADMIN_PASSWORD` / `DEFAULT_USER_PASSWORD` are unset (SonarQube
  `python:S2068`). Set both before running them; the scripts will refuse to
  run without them in a later release.
- **UI toolchain:** the UI is built with `react-scripts` 5, which carries the
  nSpect findings above and Dependabot alerts in build tooling. Moving to Vite
  is planned.
- **Root release tooling:** the root `package-lock.json` (semantic-release and
  commit tooling, not shipped) has open Dependabot alerts for `undici`,
  including a copy bundled inside `npm` that an override cannot change.
- **SBOM version stamp:** CI stamps each SBOM with the latest tag, so the CI
  SBOMs of `4259fa3` say `2.1.0`. The submitted SBOM is stamped `2.1.1`.
- **Status script:** a provider rate limit (429) prints FAIL but exits 0.
- Carried over from v2.1.0: MCP write servers have no server-side
  authorization (keep them on the Compose network); the rate limiter fails
  open by default; `/version` in Compose reports `0.0.0 (unknown)`; hosted
  endpoints are not a production SLA.

Full diff of the validated code: [`v2.1.0...4259fa3`](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/compare/v2.1.0...4259fa37aa3676bbcc3378f00d067d9bdcc01174)
