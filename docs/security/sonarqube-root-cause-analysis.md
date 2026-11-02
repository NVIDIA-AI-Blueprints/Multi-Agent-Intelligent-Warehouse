# SonarQube and CodeQL: Why Analysis Stopped

**Scope:** NVIDIA SonarQube project `TEGRASW_Blueprints-SRE_warehouse-operational-assistant_Multi-Agent-Intelligent-Warehouse` on https://sonar.nvidia.com (associated with nSpect `NSPECT-NJMX-9GQU`, component MAIW-Core), and GitHub CodeQL code scanning, for `NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse`.

**Investigated:** 2026-11-02, against `main` at `0fbcb69`.

Every statement below cites the evidence it rests on. The sources are:
- the repository's Git history;
- the GitHub Actions run records (`gh run list`, the runs API, and the run pages for runs whose logs have expired);
- the SonarQube web API, which reads anonymously because the project is public.

## Summary

| Period | What happened | Analyses uploaded |
|---|---|---|
| 2025-12-11 | Integration added: the workflow calls `NVIDIA-AI-Blueprints/sonarqube-workflows/.github/workflows/sonarqube-reusable-template.yml@main` on the internal runner `sonarqube-workflows-bp-sre`. First main analysis is `b8d66a0`. | yes |
| 2025-12-12 → 2026-01-05 | The scan ran and uploaded on almost every push to main, but the GitHub job was **red** (`SonarQube Scan`: "Process completed with exit code 3"). The quality gate failed from the second analysis on (event "Failed" at `d1b1e27`), and the template waits for the gate. | yes: 23 more, last **2026-01-05 22:01 UTC, `4df9a41`** |
| 2026-01-06 → 2026-01-09 | The scan job ran but failed before uploading ("exit code 2"). The workflow had started running `pytest` itself (`testCommand`, added 2026-01-05). Logs have expired, so the failing step cannot be confirmed. | **none** |
| 2026-01-12 → 2026-07-29 | Every run failed at startup: "Invalid workflow file … error parsing called workflow … `NVIDIA-AI-Blueprints/sonarqube-workflows/…@main`: **workflow was not found**". That is 105 red runs, none of which started a job. | none |
| 2026-08-20 → now | No run since. PR #71, "Fix/double timeouts stack wide", synced 175 files from the T-DevH mirror. It replaced `sonarqube.yml` with a mirror placeholder that runs only on manual dispatch and only prints a notice. | none |

**Result:** the dashboard's latest analysis is 2026-01-05 of `4df9a41`, ten months before v2.1.0 (`2fdd9fe`, tagged 2026-10-31), and its version label is `1.0.0`.

## Root causes

1. **The shared workflow became unreachable from this repository (2026-01-12).**
   - The template lives in `NVIDIA-AI-Blueprints/sonarqube-workflows`. That repository is not visible to a repository-scoped token (`GET /repos/NVIDIA-AI-Blueprints/sonarqube-workflows` returns 404), so it is private or internal.
   - GitHub lets a public repository call reusable workflows only from public repositories.
   - The sibling public blueprints that call the same template fail the same way today, with runs that have no jobs: Retail-Agentic-Commerce (last success 2026-03-11) and Retail-Catalog-Enrichment (last success 2026-01-08).
   - **Most likely cause:** MAIW and those blueprints went public, which cut off access. **Not verified:** the date MAIW became public is not exposed by the API. Blueprints SRE, the owners of the shared workflow, can confirm it.
2. **The mirror placeholder (2026-08-20).** PR #71 carried T-DevH mirror workflow files upstream:
   - `sonarqube.yml` became a dispatch-only notice ("SonarQube reusable workflows are only wired on NVIDIA-AI-Blueprints/… This T-DevH mirror does not call sonarqube-workflows").
   - The **same PR** removed the push, pull_request and weekly triggers from `codeql.yml`. As a result, GitHub code scanning has no CodeQL security analysis for main after **2026-08-17** (commit `e630a21`).
   - The `Analyze (python)` and `Analyze (javascript-typescript)` checks that still appear on pull requests come from GitHub Code Quality. They upload no security alerts.
3. **The analysis scope was `src/` only.** `sonar-project.properties` set `sonar.sources=src`, so even the successful analyses never covered:
   - `apps/` (the canonical API, `maiw_api`, which is the only release entrypoint; 21k lines);
   - `packages/` (DecisionEngine, execution, agents, MCP, models and state; 49k lines);
   - `mcp_servers/`, `integrations/`, `scripts/`, or any Dockerfile.

   The scanner itself was outdated too: the run page warns "This version of the SonarQube Scanner GitHub Action is no longer supported and contains a security vulnerability."
4. **Network placement.** `sonar.nvidia.com` resolves to `10.220.72.10`, a private address. It is reachable only from the NVIDIA network: the template used the internal runner `sonarqube-workflows-bp-sre`, and this host reaches it. GitHub-hosted runners cannot.

The server is healthy: version 2026.3.1.123439 (`GET /api/server/version`), and the project's `main` and `add-sonarqube-integration` branches are intact.

## What was restored (this change)

| Item | Change |
|---|---|
| `.github/workflows/sonarqube.yml` | A self-contained scanner job replaces the placeholder (detailed below). |
| `scripts/security/run_sonar_scan.sh` | One implementation for CI and manual runs (detailed below). |
| `sonar-project.properties` | Full source scope (detailed below). |
| `pyproject.toml` | `relative_files = true` for coverage, so `coverage.xml` from one runner maps on another. |
| `.github/workflows/ci-cd.yml` | Uploads `coverage.xml` as artifact `sonar-coverage` (7 days). |
| `.github/workflows/codeql.yml` | Push, pull request and weekly triggers restored; job named `CodeQL` so its checks are distinct from Code Quality's. |

**`sonarqube.yml`:**
- It runs after a successful CI/CD Pipeline for pushes to main and for pull requests from this repository's branches, and analyzes the same commit with that run's coverage. There is no second test run.
- `workflow_dispatch` is available for troubleshooting.
- It never runs for pull requests from forks.
- The scan script and `sonar-project.properties` come from the commit the workflow runs from (`github.sha`; for `workflow_run`, the default branch), in a sparse checkout at `sonar-tools/`. The analyzed commit is checked out separately at `source/`, together with its CI run's `coverage.xml`, and is only scanned. A pull request branch therefore never runs code in the step that holds `SONAR_TOKEN`, and branches cut before the script existed are still analyzed (they used to fail with exit 127).
- The runner comes from the repository variable `MAIW_SONAR_RUNNER`. On a GitHub-hosted runner the job **fails at the reachability check** instead of passing without a scan.
- Permissions are `contents: read` and `actions: read`.

**`run_sonar_scan.sh`:**
- It uses the pinned scanner image `sonarsource/sonar-scanner-cli:12.3.0.4285_8.1.0@sha256:47956b…`.
- `SONAR_TOKEN` is passed by name only, never on a command line.
- `projectVersion` is the latest `v*` tag (2.1.0, not 1.0.0), and `sonar.scm.revision` is the commit.
- `MAIW_SONAR_SOURCE_DIR` selects the checkout to analyze and `MAIW_SONAR_SETTINGS` the properties file; the scanner reads the settings file mounted read-only. Both default to the checkout the script lives in, so a manual run from the repository is unchanged.
- It handles branch and pull-request analysis, waits for the quality gate, and writes `maiw-sonar-evidence.json` with the server's analysis ID, timestamp and gate result.

**`sonar-project.properties`:**
- Sources: `src`, `apps`, `packages`, `mcp_servers`, `integrations`, `scripts` and the Dockerfiles.
- Tests are classified by pattern wherever they live (`tests/`, `packages/*/tests`, `apps/api/tests`, `src/ui/web/src/__tests__`).
- Exclusions cover only generated and vendored output.

### Validation done

- `run_sonar_scan.sh` from this host (NVIDIA network) with a deliberately invalid token:
  - the scanner image starts and reads the new properties;
  - it reaches `https://sonar.nvidia.com` over TLS and stops at `HTTP 401 Unauthorized`.

  This proves connectivity and configuration up to authentication.
- No analysis was submitted, because no authorized token was used.

### Outstanding, owner action required

1. **Runner:** an approved NVIDIA-network runner for this public repository. The old `sonarqube-workflows-bp-sre` group or another group, set as the repository variable `MAIW_SONAR_RUNNER`. Whether that group may serve a public repository is an organization runner-group setting for Blueprints SRE to decide. Self-hosted runners on public repositories must not run fork code; the workflow already excludes forks.
2. **Credentials:** confirm that the repository secrets `SONAR_TOKEN` and `SONAR_HOST_URL` (both present) are a valid analysis token for this project and `https://sonar.nvidia.com`.
3. **First fresh analysis:**
   - either run `SonarQube Analysis` by dispatch once (1) and (2) are done;
   - or run `scripts/security/run_sonar_scan.sh` from an NVIDIA-network host with an authorized token. Check out the target commit, put its CI run's `coverage.xml` in the repository root, then `read -rs SONAR_TOKEN; export SONAR_TOKEN`.
4. **Alternative:** if Blueprints SRE prefers their maintained shared workflow, it must be callable from public repositories (a public workflow repository), and this workflow would then call it. The sibling blueprints are broken the same way and need the same decision.
