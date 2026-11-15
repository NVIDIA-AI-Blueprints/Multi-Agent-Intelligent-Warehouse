# MAIW v3.0.0 — Release Notes

> **DRAFT — not tagged, not published.** Two release-blocking security gates are
> still open (nSpect scan and SBOM upload); see "Validation". Remove this block
> when publication is approved.

**Status:** release candidate, not yet released. **Validated code commit:**
`main` `1c96c2e735d1661a97110d9e26738eed0d9d7e19` (PR #321). Previous release:
`v2.1.1` (tag → `6d1395b`, validated code `4259fa3`).

v3.0.0 removes the unused login system (its routes, settings and stored
password hashes), moves every scripted demo scenario to the DC-47 DataPack
world, and tightens when the Copilot acts. **It removes documented API routes
and deletes stored data on schema re-apply: read "Compatibility" before
upgrading.** MAIW remains a single-trusted-host developer blueprint. Remote MCP
and API exposure is not supported.

**Why 3.0.0:** v2.1.1 documented `/api/v1/auth/*` as mounted, and this release
removes those routes without a replacement and drops stored password hashes.
Under Semantic Versioning both are major changes. The advisory
`semantic-release` preview proposes 2.2.0 only because no commit carries a
`BREAKING CHANGE` footer; the version is the maintainer's decision
(`docs/operations/RELEASING.md` §2).

## Validation

| Validation | Result |
|---|---|
| CI/CD Pipeline, CodeQL | PASS (`1c96c2e`): CORE CI pytest **4260 passed, 13 skipped, 0 failed** (coverage 53.79%, floor 48%); `packages/maiw-world` **204 passed**; UI Jest **1056/1056** (48 suites); Security Scan and Trivy image scans (backend, frontend, MCP) passed ([CI run](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/actions/runs/43630324310), [CodeQL run](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/actions/runs/43630324246)) |
| Deployment test (deploy, readiness, MCP tool calls, restart durability, reported build commit) | PASS ([run](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/actions/runs/43630324382)); `/api/v1/version` reported commit `1c96c2e735d1` |
| Internal NGC MAIW pytest suite | **NOT RUN**: could not pull the internal test image (requires internal NGC org access) ([run](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/actions/runs/43630324382)) |
| Release gate on the reference host | PASS (2026-11-15, on `1c96c2e`; details below). The first live-call run hit HTTP 503 from hosted Ultra; the counted run reached the provider for all four calls |
| SonarQube | analysis `dea59560-2068-4486-84b6-d9a6fb450a2e` of `1c96c2e` (analysis date 2026-11-15 16:56:21 UTC, gate computed 16:58:20 UTC), version `3.0.0`, quality gate **ERROR**: 6 new HIGH issues, 42 issues of prioritized security rules, 134 HIGH issues overall; 0 blocker issues; new-code coverage 93.9%; **0 new security hotspots**. The gate failed; this is not a passing scan. Each failing condition is triaged by the maintainers in [sonarqube-remediation-report.md](docs/security/sonarqube-remediation-report.md#analysis-of-1c96c2e-2026-11-15-v300-candidate): the 6 new HIGH issues are `shelldre:S7688` (`[` instead of `[[`) in two operator scripts, accepted; of the 42 prioritized-rule issues, 40 are `pythonsecurity:S5145` log injection, mitigated by the process-wide log guard, and 2 are false positives; the 134 HIGH issues are 84 S7688 shell style, 49 maintainability and the same S2083 false positive. Under RELEASING.md a gate ERROR with this triage does not block the release. Run manually from an NVIDIA-network host with `scripts/security/run_sonar_scan.sh` and the CI run's `sonar-coverage` artifact. CI's own SonarQube job for this commit ([run](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/actions/runs/43632460971)) could not resolve `sonar.nvidia.com` and submitted no analysis |
| nSpect OSS scan (NSPECT-NJMX-9GQU) | **NOT RUN (release-blocking)**: no scan of `1c96c2e` has been confirmed by the program owner. An older scan does not count |
| SBOMs stamped with the release version | PASS: [CI run](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/actions/runs/43736730172) dispatched on `1c96c2e` with `release_version=3.0.0`; `sbom-backend`, `sbom-frontend` (frontend image and UI bundle) and `sbom-mcp` each record `maiw:git_sha=1c96c2e735d1661a97110d9e26738eed0d9d7e19` and `maiw:release_version=3.0.0`, and pass `validate_sbom.py` |
| SBOM submitted to nSpect | **NOT RUN (release-blocking)**: upload file prepared, not yet uploaded: `maiw-v3.0.0-1c96c2e.cdx.json`, CycloneDX 1.6, 1639 components, sha256 `3abea3726ca937b3135a0da6c41ece591d70b04cd4bbf0df2c25a318756ae683` |

### Release gate on the reference host (2026-11-15)

Host `epg-tme-smc-h100-02` (4 × H100 NVL, driver 580.178.04; NemoClaw 0.0.124,
OpenShell 0.0.116, Python 3.12.3), profile `reference`, sandbox required,
managed OpenShell gateway, approved default bindings: Lightning
`nvidia/nemotron-3.5-lightning-30b-a3b` and Ultra
`nvidia/nemotron-3-ultra-550b-a55b` enabled, Super and Nano disabled (hosted
endpoints retired). The API reported version `2.1.1+47.g1c96c2e`, build
`development`, commit `1c96c2e735d1661a97110d9e26738eed0d9d7e19`.

| Step | Result |
|---|---|
| Provider probe, preflight (35 checks), start, status | PASS. Start warned that hosted Ultra answered HTTP 503 three times ("retry later; not a configuration error") |
| Smoke test | PASS, 20/20 |
| Live `POST /api/v1/inference` per binding | PASS, 4/4 (16:51–16:54 UTC, a unique prompt per call so none came from the 5-minute response cache): Lightning low and medium; Ultra high; Ultra medium with critical risk. Each HTTP 200, `identity_verified=true`, provider-reported model = approved model |
| In-sandbox probe | PASS: inference 200 (Ultra, identity verified); every governed write denied for every sandbox credential; direct provider and internet blocked; no host secret in the sandbox |

The first live-call run (16:49–16:50 UTC) passed 3 of 4: Ultra with critical
risk returned 503 `MODEL_UNAVAILABLE` because the hosted endpoint answered
503. No answer from a different model was accepted.

## Compatibility

> **Back up `users` and `user_sessions` before upgrading an existing
> database.** Re-applying `data/postgres/000_schema.sql`, or running the
> demo-data scripts, drops the `users.hashed_password` column and the
> `user_sessions` table. There is no down-migration and it cannot be undone.
> A fresh volume is unaffected, and an existing volume changes only when the
> schema file or a demo-data script is re-applied to it.

- **`/api/v1/auth/*` is removed (12 routes).** Login, refresh, register,
  change-password, `me` (GET and PUT), user admin (`users`, `users/{id}` GET
  and PUT), `users/public`, roles and permissions. Clients get 404. The UI
  never used them, and no shipped route checked their tokens. The only
  replacement is the worker list: `GET /api/v1/operations/workers` instead of
  `/api/v1/auth/users/public`. Governed writes are still gated by
  `MAIW_OPERATOR_WRITE_TOKEN` ([#261](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/issues/261))
- **Stored password hashes are deleted** when the schema or a demo-data script
  is re-applied (see the box above). The `users` table stays as the worker
  roster.
- **Removed setup script and settings:** `scripts/setup/create_default_users.py`;
  `JWT_SECRET_KEY`, `DEFAULT_ADMIN_PASSWORD` and `DEFAULT_USER_PASSWORD`
  (ignored if still set); the PyJWT, python-jose, bcrypt and email-validator
  dependencies. Automation that calls the script breaks.
- **Removed Python modules:** `src/api/agents/document/document_extraction_agent.py`
  (`DocumentExtractionAgent`) and its helper modules, with `NEMO_PARSE_URL` and
  `NEMO_PARSE_API_KEY` ([#270](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/issues/270)).
  Only external importers are affected.
- **Monitoring stack:** it runs as Compose project `maiw-monitoring`; Grafana
  moves from :3000 to `${MAIW_GRAFANA_PORT:-3030}` and needs
  `GRAFANA_ADMIN_PASSWORD`; exporter ports are no longer published; the Ops and
  Safety dashboards and 22 unused metrics are removed. Containers from the old
  project stay until you remove them ([#277](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/issues/277))
- **Copilot acts only on a command.** A question, a statement, a negation or
  "cancel" that mentions an action no longer runs a recommendation
  ([#258](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/issues/258))
- **A maintenance proposal whose slot has passed is rejected,** not executed
  ([#259](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/issues/259))
- **Demo scenarios use DataPack entity ids,** and the published counterfactual
  figures change. With hosted Nemotron 3 Ultra on DC-47 the MAIW run recovers
  180 s after the disruption, with −46.8% backlog AUC and −90.0% wave-risk AUC;
  the control run never recovers. The YAML-world figures were 300 s, −92% and
  −86.7% ([#309](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/issues/309))
- **Version reporting:** `GET /`, the OpenAPI document and `/api/v1/version`
  report the build's version instead of `0.1.0`: `3.0.0` on the tag,
  `3.0.0+N.g<sha>` after it, `0.0.0+unknown` when nothing identifies the build.
  `/api/v1/version` adds `build` and the full `commit` (#321)

## Security

- The login system and the `changeme` fallback passwords are removed ([#261](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/issues/261)).
- React Router v7 (CVE-2026-53669, CVE-2026-53666) ([#264](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/issues/264)).
- `serialize-javascript` ^7.1.3 ([#263](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/issues/263)).
- `requests` >= 2.34.2 ([#262](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/issues/262)).
- Root release-tooling `undici` and `ajv` are updated; `minimatch` and `glob` bundled in `npm` are accepted with reasons ([#266](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/issues/266)).
- Self-service profile updates were restricted to personal fields (#275) before the routes were removed.
- The Copilot no longer runs recommendations from questions or negations ([#258](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/issues/258)).
- Pull requests to `main` must pass seven required checks (tests, CodeQL, Security Scan, image scans). The GPU deployment test, which holds repository credentials, runs only after merge or on demand (#319, #322).

## Fixes and additions

- **Demo:**
  - Scripted scenarios run again and run on the DataPack world, with work
    progressing and absent workers' tasks released (#308, #309).
  - The labor recommendation targets the unassigned task.
  - Analyze keeps going after one proposal fails to build (#260).
  - The routing fallback (`fallback_from`, `fallback_reason`) is shown in
    traces and the UI (#318).
- **Agents:** the operations agent reads an assessment from any reply and
  reports unreadable ones (#314).
- **Scripts:**
  - `counterfactual_eval.py` compares runs over equal windows, retries
    429/503/504 responses, and reads `MAIW_API_URL`.
  - The provider probe no longer reports a rate limit as a missing model (#269).
- **API:**
  - HTTP request metrics are recorded and served at `/api/v1/metrics` (#274).
  - The Copilot binds wave proposals to the request's warehouse, and
    `schedule_maintenance` proposals carry `scheduled_for`.
  - "What happened to X" is answered as a question, not an outcome check.
- **Document:** results name the judge model that actually answered.
- **Monitoring:** the bundled stack scrapes the API (#277).
- **Build:** the root `Dockerfile` UI stage uses the pinned Node 22 image.
- **CI and release evidence:**
  - SBOMs and SonarQube are stamped with the release being built (#268).
  - `apps/api` tests (#287) and `packages/maiw-world/tests` (#320) run in CI.
  - The deployment test checks that `/api/v1/version` reports the deployed
    commit (#321).
- **Dependencies:** routine floor and lockfile updates (anyio, websockets,
  langchain-core, httpx, paho-mqtt, pymodbus, scikit-learn,
  `@tanstack/react-query`, Node 22.23.4) and GitHub Actions major versions.

## Known limitations

- **No login and no per-user authorization.** Governed writes are gated by
  `MAIW_OPERATOR_WRITE_TOKEN`. Run MAIW on a single trusted host; remote MCP
  and API exposure is unsupported.
- **MCP write servers have no server-side authorization.** Keep them on the
  Compose network.
- **The rate limiter fails open by default.**
- **UI coverage is disabled.** No UI coverage is measured; the coverage floor
  (48%) and SonarQube coverage are Python-only.
- **21 `tests/unit` files are still excluded from CORE CI.** Their status and
  the restoration plan are in `docs/architecture/TEST_STRATEGY.md`.
- **The GitHub `SonarQube Scan` job cannot reach `sonar.nvidia.com`.** The
  release analysis is a manual scan from an NVIDIA-network host.
- **The deployment test reports a `0.0.0+g<sha>` version,** because its
  checkout fetches one commit without tags; the commit it checks is correct.
- **Hosted model endpoints are not a production SLA.** Hosted Ultra returned
  HTTP 503 during this release's gate (2026-11-15) and empty replies on
  2026-11-11; the API reports both (`MODEL_UNAVAILABLE`, #314).
- **The UI still builds with `react-scripts` 5.** Moving to Vite is tracked in
  #265.

Full diff of the validated code: `v2.1.1...1c96c2e`
