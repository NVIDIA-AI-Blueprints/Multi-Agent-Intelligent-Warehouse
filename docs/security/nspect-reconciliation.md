# nSpect Reconciliation: NSPECT-NJMX-9GQU

## MAIW v3.0.0 (candidate `1c96c2e`)

Recorded 2026-11-15. The program-side state below was set up and observed in
nSpect by the program owner (NVIDIA SSO) and relayed as screenshots; no
automation read from or wrote to nSpect. Times are nSpect display times.

| Item | State |
|---|---|
| Program version | **MAIW v3.0.0**, created 2026-11-15 (planned release date 2026-11-18, External: General Use, Published To GitHub), cloned from MAIW v2.1.1 with ConneX and attributes; builds not cloned. No child programs in ConneX |
| Registered source | Component `Multi-Agent-Intelligent-Warehouse`: `ssh://git@github.com/NVIDIA-AI-Blueprints/multi-agent-intelligent-warehouse.git` at `1c96c2e735d1661a97110d9e26738eed0d9d7e19`, reporting enabled, no SBOM name (nSpect scanning). No builds, binary artifacts, container images or Helm charts, as for v2.1.1 |
| OSS scan | On-demand scan, started 2026-11-15 13:14, completed (last scan 13:43): **0 Critical, 2 High, 8 Medium, 3 Low**. Program Scan Health: no scan failures, no clone failures. Security Risk Report: 0 verified secrets, 0 high-risk licences |
| Exceptions | **EXC-MOOT-B57E** (Source Repo Exception, Not Affected, branch `1c96c2e…`), created 2026-11-15 14:48 and approved the same day; covers both High findings (below). EXC-HPU1-JZI6 and EXC-TNK9-0X62 are bound to the v2.1.1 branch `4259fa3`, and Allowed Vulnerabilities was empty for MAIW v3.0.0 before EXC-MOOT-B57E |
| SBOM | **Uploaded** 2026-11-15 (below) |

### Findings

The 16 findings of v2.1.1 less `react-router`, `serialize-javascript` and the
`requests` minimum, which v3.0.0 fixes; none is new. Dispositions are in
`RELEASE_NOTES_v3.0.0.md` ("nSpect findings for MAIW v3.0.0").

| Finding | Exception (EXC-MOOT-B57E) | Evidence, re-checked at `1c96c2e` |
|---|---|---|
| `react-dev-utils` 12.0.1, BDSA-2026-18203 / CVE-2026-14802 (CVSS 8.9, SLA breach 2027-02-13) | Not Affected, `requires_configuration` | The UI start script sets `BROWSER=${BROWSER:-none}`; `src/ui/web/src/__tests__/devServerNoAutoBrowser.test.ts` pins it. Development server only |
| `svgo` 2.8.4, BDSA-2026-27126 / CVE-2026-73650 (CVSS 7.4, SLA breach 2027-02-13) | Not Affected, `code_not_present` | GHSA-2p49-hgcm-8545: affected < 2.8.3, fixed in 2.8.3. Resolved under `postcss-svgo`; the top-level `svgo` is 4.1.0. Build time only |

### SBOM to submit

The four CI SBOMs of `1c96c2e` come from
[CI run 43736730172](https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/actions/runs/43736730172)
(CI/CD Pipeline dispatched on `main` at `1c96c2e` with `release_version=3.0.0`;
artifacts `sbom-backend`, `sbom-frontend`, `sbom-mcp`, kept until 2027-02-13).
Each records `maiw:git_sha=1c96c2e735d1661a97110d9e26738eed0d9d7e19` and
`maiw:release_version=3.0.0` and passes `scripts/security/validate_sbom.py`;
no re-stamping was needed.

| File | Components | sha256 |
|---|---|---|
| `maiw-backend.cdx.json` | 187 | `967bdff7eb7455bd5ded5c8d829aab7b9dd5ef924f80ffec5dcdbc9d20f649e7` |
| `maiw-frontend.cdx.json` | 71 | `d28236b83cc87349e008a439893fba895a596b424a4e23d2fe31ea06fa16dd1c` |
| `maiw-ui-bundle.cdx.json` | 1365 | `3007f209c0bfe741b24075c12dc2bfad8e31464f63f90c8ae6c03c2488f8859c` |
| `maiw-mcp.cdx.json` | 154 | `dc968f424c835536773fc72c76c9f26c3cde64253365732281797c9f1b8f0707` |

nSpect's form takes one file, so they are merged as for v2.1.1 (each image or
bundle becomes a component the release depends on; components kept flat, a
`bom-ref` in more than one input listed once, dependencies unioned, nothing
added or edited):

| | |
|---|---|
| File | `maiw-v3.0.0-1c96c2e.cdx.json`, CycloneDX 1.6, **1639 components**, sha256 `3abea3726ca937b3135a0da6c41ece591d70b04cd4bbf0df2c25a318756ae683` |
| Identity | `metadata.component` = Multi-Agent-Intelligent-Warehouse 3.0.0; `maiw:artifact=maiw-release`, `maiw:git_sha=1c96c2e735d1661a97110d9e26738eed0d9d7e19`, `maiw:release_version=3.0.0`; inputs and their sha256 recorded as `merged-from:*` properties |
| Checks | `validate_sbom.py` from `1c96c2e` (schema, ≥ 1000 components, tool recorded): valid; no dangling dependency references |
| Upload | **Uploaded** 2026-11-15 21:23 under **Actions → Manage SBOM → Upload an SBOM** on MAIW v3.0.0, type "Custom", with no program attributes (not partner- or commercially provided). The uploader's local copy has the sha256 above. nSpect's returned copy has a different sha256 (re-serialized) but parses to identical content: same serial number `urn:uuid:e8235098-b302-42d6-9308-5656fabae8f5`, 1639 components |

### Remaining owner steps for v3.0.0

None for the release gate. Optional: generate the Version and ConneX SBOMs
under Manage SBOM step 4, and link the SonarQube project under Security
Analysis (registration summary: "no source code is being analyzed by static
analysis tools").

### Older program versions and unregistered images

Recorded 2026-11-16 from the program owner's review of the program's
container-scanning view; the decisions are the program owner's.

| Item | State |
|---|---|
| `bpf-maiw-backend:1.0.0`, `bpf-maiw-frontend:1.0.0` | Container scans under the program (last scanned 2026-11-14), not attached to any program version. Not built by any workflow in this repository (the frontend derives from an internal base image, not the pinned public one); `1.0.0` is not a MAIW release. **Not used or distributed** (program owner, 2026-11-16), so they are not registered as release artifacts and their findings do not apply to a MAIW release. The images built from this repository are scanned by CI (Trivy) and described by the CI SBOMs |
| Program version **Multi-Agent Intelligent Warehouse v0.2-test** | Created 2026-05-09 ("adds container + helm chart artifacts"); its images came from internal registries and were built from older code. **Not used or distributed**; marked **End of Life** in nSpect on 2026-11-16, so its findings no longer count against the program |
| Program version **Multi-Agent Intelligent Warehouse v0.1** | The first published version. Left **active**: nSpect does not allow End of Life while the version has an open legal compliance request. It does not affect v3.0.0 |

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
| Exceptions | `react-dev-utils`: Not Affected exception **EXC-HPU1-JZI6** (Launch nAbler / Exception Tracker), filed and approved 2026-11-06. `svgo`: exception **EXC-TNK9-0X62**, filed and approved 2026-11-06; recorded here at the time as Resolved, but Exception Tracker shows its category as **Not Affected** (checked 2026-11-15). Approvals as reported by the program owner |
| Registered builds or images | None. Binary and container-image sources are not registered: no image is distributed; Compose builds them locally |

### Findings

All 16 are in the UI's npm lockfile or a Python minimum; none is in a shipped
image. Dispositions and reasoning are in `RELEASE_NOTES_v2.1.1.md` ("nSpect
findings for MAIW v2.1.1"). Both High findings carry approved exceptions:

| Finding | Requested disposition | Evidence |
|---|---|---|
| `react-dev-utils` 12.0.1, BDSA-2026-18203 / CVE-2026-14802 | Not Affected, justification `requires_configuration`: **EXC-HPU1-JZI6** (SLA breach date 2027-02-03) | No fixed release. `openBrowser` never runs: the UI start script defaults `BROWSER=none` (#251, pinned by `src/ui/web/src/__tests__/devServerNoAutoBrowser.test.ts`). Development server only. Removed with the move off `react-scripts` |
| `svgo` 2.8.4, BDSA-2026-27126 / CVE-2026-73650 | Resolved (vendor patched): **EXC-TNK9-0X62** (SLA breach date 2027-02-03). GHSA-2p49-hgcm-8545 lists the affected range as >= 1.0.0, < 2.8.3 and 2.8.3 as the fix. An optional http://nv/sbom ticket would correct the BDSA's affected range in nSpect's data | GHSA-2p49-hgcm-8545 lists 2.8.3 as the 2.x fix; Dependabot has no alert. Build-time only (cssnano / postcss-svgo) |

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

The CI SBOMs say `maiw:release_version=2.1.0`: CI stamped the latest tag
(`git describe`), not the version being prepared. The merged file is stamped
`2.1.1`. Since #268, a candidate's SBOMs are stamped with the release version
directly (CI/CD Pipeline run by hand with `release_version`, see
`sbom-generation.md`), so no re-stamping is needed. The form warns that "ConneX children SBOM data will become empty
when an uploaded SBOM is used"; the program owner checks the v2.1.1 ConneX
report for child programs.

### Remaining owner steps for v2.1.1
1. ~~Approval of EXC-HPU1-JZI6 and EXC-TNK9-0X62~~: both approved 2026-11-06.
2. SonarQube: the analysis of `4259fa3` (`eb6b331f…`, 2026-11-06) has quality
   gate ERROR. By maintainer decision (2026-11-06) it does not block v2.1.1;
   no SRE disposition was obtained (`sonarqube-remediation-report.md`).
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
| Registered builds or images | No workflow publishes images. The Dockerfiles said "published as `bpf-maiw-backend` / `bpf-maiw-frontend`". | Owner to confirm. Closed 2026-11-16: not used or distributed (see v3.0.0, "Older program versions and unregistered images") |

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
| `v0.2-test` rows in reports | Not from this repository: no `v0.2*` tag exists upstream | Owner: check whether an old test registration or release in the program feeds the v2.1.0 report, and archive or separate it. Closed 2026-11-16: program version v0.2-test, marked End of Life |
| Security exceptions | None requested here | Possible: undici (release tooling, not shipped). svgo is fixed by the npm override; evidence in the OSS document |
| SBOM | Available (see below); **not uploaded** | Owner: Manage SBOM |
| Registered builds | Zero | Owner: decide whether `bpf-maiw-*` images are release artifacts; if so, register them and attach their image SBOMs. Closed 2026-11-16: not distributed, so not registered |

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
3. ~~**v0.2-test:** identify which program release or registration the `v0.2-test` rows belong to, and stop them aggregating into v2.1.0.~~ Closed 2026-11-16: they belong to program version v0.2-test, whose images are not used or distributed; it is marked End of Life.
4. **SBOM:**
   - Under **Actions → Manage SBOM**, check whether direct CycloneDX upload is supported.
   - If it is, upload the release candidate's `sbom-*` CI artifacts, or the v2.1.0 files listed above.
   - Record the response.
5. ~~**Artifacts:** decide whether `bpf-maiw-backend` and `bpf-maiw-frontend` are distributed. If they are, register them, with their image digests and SBOMs.~~ Closed 2026-11-16: not used or distributed, so not registered.
6. **Exceptions:** if undici is not remediated, file exceptions with the reachability evidence. `.nspect-allowlist.toml` could exclude the root release tooling, which is not shipped; that is a policy decision, so the file is unchanged.
7. **Release identity:** v2.1.0 (`2fdd9fe`) predates the security fixes in #222–#229. If the registered release must carry them, register the next tag (for example v2.1.1, cut from `main` after these PRs are merged) rather than re-pointing v2.1.0.
