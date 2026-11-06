# nSpect Reconciliation: NSPECT-NJMX-9GQU

## MAIW v2.1.1 (candidate `4259fa3`)

Recorded 2026-11-06. The program-side state below was observed in nSpect by
the program owner (NVIDIA SSO) and relayed as screenshots; no automation read
from or wrote to nSpect.

| Item | State |
|---|---|
| Program version | **MAIW v2.1.1**, created 2026-11-06 (planned release date 2026-11-10, External: General Use, Published To GitHub; ConneX cloned from v2.1.0) |
| Registered source | `ssh://git@github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse.git`, commit `4259fa37aa3676bbcc3378f00d067d9bdcc01174` |
| OSS scan | Repository `…multi-agent-intelligent-warehouse--4259fa37aa3676bbcc3378f00d067d9bdcc01174`, last scan 2026-11-05 17:57 (nSpect display time): **0 Critical, 2 High, 10 Medium, 4 Low** |
| Package inventory | npm rows match the UI SBOM (`maiw-ui-bundle.cdx.json`) version for version. Python rows are the minimums in `requirements.txt` (for example `requests` 2.32.4 and `xgboost` 3.2.0), not installed versions: the images install `requests` 2.34.2 and the backend image has no `xgboost` |
| SBOM | Uploaded 2026-11-06 under Manage SBOM → Upload an SBOM (see below) |
| Exceptions | **Pending:** `react-dev-utils` exception and `svgo` discrepancy (below) |
| Registered builds or images | None. Binary and container-image sources are not registered: no image is distributed; Compose builds them locally |

### Findings

All 16 are in the UI's npm lockfile or a Python minimum; none is in a shipped
image. Dispositions and reasoning are in `RELEASE_NOTES_v2.1.1.md` ("nSpect
findings for MAIW v2.1.1"). The two High findings are release-blocking until
nSpect records a decision:

| Finding | Requested disposition | Evidence |
|---|---|---|
| `react-dev-utils` 12.0.1, BDSA-2026-18203 / CVE-2026-14802 | Exception | No fixed release. `openBrowser` never runs: the UI start script defaults `BROWSER=none` (#251, pinned by `src/ui/web/src/__tests__/devServerNoAutoBrowser.test.ts`). Development server only. Removed with the move off `react-scripts` |
| `svgo` 2.8.4, BDSA-2026-27126 / CVE-2026-73650 | Discrepancy | GHSA-2p49-hgcm-8545 lists 2.8.3 as the 2.x fix; Dependabot has no alert. Build-time only (cssnano / postcss-svgo) |

### SBOM submitted

nSpect's upload form takes one CycloneDX or SPDX JSON file, so the four CI
SBOMs of `4259fa3` ([CI run 42111328437](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/actions/runs/42111328437), artifacts `sbom-backend`, `sbom-frontend`, `sbom-mcp`) were merged into one:

| | |
|---|---|
| File | `maiw-v2.1.1-4259fa3.cdx.json`, CycloneDX 1.6, **1642 components**, sha256 `800278356c94534946dffabe9db35a9063c673f80aa5bd4afb3484c7b9f35c1b` |
| Uploaded | 2026-11-06 04:28 (nSpect display time), type "Custom". The program owner's local copy matches the sha256 above |
| Identity | `metadata.component` = Multi-Agent-Intelligent-Warehouse 2.1.1; `maiw:git_sha=4259fa37…`, `maiw:release_version=2.1.1`, `maiw:artifact=maiw-release` |
| Merge | Each input's image or bundle component becomes a component that the release depends on. Components are kept flat, a `bom-ref` present in more than one input is listed once, and dependency entries are unioned. No component was added or edited. Validated with `scripts/security/validate_sbom.py` from `4259fa3` (schema, ≥ 1000 components, tool recorded); no dangling dependency references |
| Inputs (sha256, recorded in the file as `merged-from:*` properties) | `maiw-backend.cdx.json` (190 components) `51bf7b3a…b088`; `maiw-frontend.cdx.json` (71) `b43153e9…35ca9`; `maiw-ui-bundle.cdx.json` (1365) `a2659151…78ec6`; `maiw-mcp.cdx.json` (154) `eea0a18d…c331e` |

The CI SBOMs say `maiw:release_version=2.1.0`: CI stamps the latest tag
(`git describe`), not the version being prepared. The merged file is stamped
`2.1.1`. The form warns that "ConneX children SBOM data will become empty
when an uploaded SBOM is used"; the program owner checks the v2.1.1 ConneX
report for child programs.

### Remaining owner steps for v2.1.1
1. Record the nSpect decision on the two High findings.
2. SonarQube: an analysis of `4259fa3` (NVIDIA-network runner or
   `scripts/security/run_sonar_scan.sh`), or a written Blueprints SRE
   disposition. The latest analysis is of `ff5ce22`, quality gate ERROR.
3. Confirm the ConneX children question above.

## MAIW v2.1.0 (historical, 2026-11-02)

| | |
|---|---|
| **Program** | Retail Multi-Agent Intelligent Warehouse |
| **Registered release** | MAIW v2.1.0 |
| **Component** | MAIW-Core (source), branch `main` |
| **Static analysis** | NVIDIA IPP SonarQube |
| **Access from this environment** | `nspect.nvidia.com` resolves to 10.14.68.10 and answers HTTP 200. It is behind NVIDIA SSO. **No nSpect credentials were used**, so nothing below was read from, or changed in, nSpect. The program-side state comes from the assignment ("previously observed") and must be confirmed by a program owner. |

### Repository-side facts

| Item | Value | Evidence |
|---|---|---|
| Canonical repository | https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse | `gh repo view`. The T-DevH repository is a contributor fork. |
| v2.1.0 commit | `2fdd9feac6d222284349cdbecb8ff94b4dca514c` | Annotated tag `v2.1.0` (object `f95dd12`), GitHub release published 2026-10-31, Latest |
| v2.1.0 CI | CI/CD Pipeline **success**, deployment test **success** | `security-evidence-manifest.json` |
| SonarQube project | `TEGRASW_Blueprints-SRE_warehouse-operational-assistant_Multi-Agent-Intelligent-Warehouse` | `sonar-project.properties`, `GET /api/components/show` |
| SonarQube latest analysis | **2026-01-05 22:01 UTC, `4df9a41`, version "1.0.0", quality gate ERROR** | SonarQube API (anonymous) |
| SonarQube analysis of `2fdd9fe` | **None** | `GET /api/project_analyses/search`: no analysis has that revision |
| SBOM for v2.1.0 | Generated locally from `2fdd9fe`, CycloneDX 1.6, all schema-valid; not uploaded | See "SBOM" below |
| Registered builds or images | No workflow publishes images. The Dockerfiles say "published as `bpf-maiw-backend` / `bpf-maiw-frontend`". | Owner to confirm |

### Reconciliation

| nSpect expectation | State | Action |
|---|---|---|
| Repository identity, no invalid entries | Consistent: the canonical repository, branch `main` | Owner to confirm in nSpect |
| Registered version v2.1.0 ↔ SonarQube version | **Mismatch.** SonarQube shows version `1.0.0` and its analyses stop on 2026-01-05. | #226 sets `sonar.projectVersion` from the release tag (`2.1.0`) |
| Valid SonarQube association | The project exists and is public. Analysis has been **stale for ten months** (root cause: `sonarqube-root-cause-analysis.md`). | #226, plus the owner runner and token actions below |
| Scan timestamp current | **No** | First fresh analysis after #226 is merged and configured |
| Current OSS findings | The historical langchain and aiohttp findings do not match shipped versions; svgo 1.3.2 is replaced by 4.1.0 through an npm override | `oss-vulnerability-remediation.md`; #227 removes the stale manifests. A fresh nSpect scan is needed. |
| Current static-analysis findings | 11 open S5145 findings triaged; 6 were reachable and are fixed in #229, together with a credential-logging issue | `sonarqube-remediation-report.md` |
| "Scan health: no failures in two days" | Not evidence of scanning. SonarQube had not run since 2026-07-29 (dispatch-only placeholder), so there was nothing to fail. | — |
| `v0.2-test` rows in reports | Not from this repository: no `v0.2*` tag exists upstream | Owner: check whether an old test registration or release in the program feeds the v2.1.0 report, and archive or separate it |
| Security exceptions | None requested here | Possible: undici (release tooling, not shipped). svgo is fixed by the npm override; evidence in the OSS document |
| SBOM | Available (see below); **not uploaded** | Owner: Manage SBOM |
| Registered builds | Zero | Owner: decide whether `bpf-maiw-*` images are release artifacts; if so, register them and attach their image SBOMs |

### SBOM for the v2.1.0 commit

Generated with `scripts/security/generate_sbom.sh` (#228) from a checkout of `2fdd9fe`. All four are valid CycloneDX 1.6, stamped with `maiw:git_sha=2fdd9feac6d2…` and `maiw:release_version=2.1.0`.

| File | Components | sha256 |
|---|---|---|
| `maiw-backend.cdx.json` (image `sha256:ef58c55f…`) | 192 | `10774667a61889a8e17dd618ed4ef3659877d0adc4b9c80dc3baf1465d3df311` |
| `maiw-frontend.cdx.json` (image `sha256:96c37032…`) | 71 | `346a7fb5d398322f3f0b783d2e950c9ebdaee1240a84418c327eb8aa9a6ab781` |
| `maiw-mcp.cdx.json` (image `sha256:68354188…`) | 200 | `756189fd4c8757ae77bb541f619c8c6f0c4cbd60719092683127f97f983df13a` |
| `maiw-ui-bundle.cdx.json` | 1,378 | `4e6382210cbbe43273482241552c95aa0ea3a8218d96d90a689aa351a9cb3050` |

Image IDs are local build IDs. Rebuilding produces different IDs but the same package inventory, because the base images are pinned by digest (backend and frontend). The MCP base `python:3.11-slim` is not pinned.

The files are not committed. Regenerate them with `git checkout v2.1.0 && scripts/security/generate_sbom.sh`, using the script from #228. For commits after #228 is merged, CI attaches them to every run.

### Manual steps for the program owner

1. **SonarQube** (Blueprints SRE):
   - Merge #226.
   - Provide an NVIDIA-network runner allowed for this public repository, and set its label as `MAIW_SONAR_RUNNER`.
   - Confirm that the repository secrets `SONAR_TOKEN` and `SONAR_HOST_URL` are valid.
   - Run **SonarQube Analysis** for the release candidate.
   - Record the analysis (ID, timestamp, quality gate) in nSpect.
2. **OSS:** trigger a fresh nSpect / Pulse scan of the release candidate after #227 is merged, and compare it with `oss-vulnerability-remediation.md`.
3. **v0.2-test:** identify which program release or registration the `v0.2-test` rows belong to, and stop them aggregating into v2.1.0.
4. **SBOM:**
   - Under **Actions → Manage SBOM**, check whether direct CycloneDX upload is supported.
   - If it is, upload the release candidate's `sbom-*` CI artifacts, or the v2.1.0 files listed above.
   - Record the response.
5. **Artifacts:** decide whether `bpf-maiw-backend` and `bpf-maiw-frontend` are distributed. If they are, register them, with their image digests and SBOMs.
6. **Exceptions:** if undici is not remediated, file exceptions with the reachability evidence. `.nspect-allowlist.toml` could exclude the root release tooling, which is not shipped; that is a policy decision, so the file is unchanged.
7. **Release identity:** v2.1.0 (`2fdd9fe`) predates the security fixes in #222–#229. If the registered release must carry them, register the next tag (for example v2.1.1, cut from `main` after these PRs are merged) rather than re-pointing v2.1.0.
