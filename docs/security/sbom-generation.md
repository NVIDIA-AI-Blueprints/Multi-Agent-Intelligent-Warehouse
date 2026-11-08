# SBOM Generation

MAIW publishes CycloneDX 1.6 JSON SBOMs for everything it builds. Every CI run produces them, and they can be reproduced locally with one script.

## What MAIW ships

| Deliverable | How it is distributed | SBOM |
|---|---|---|
| Source | GitHub repository and tagged releases (v2.1.0 → `2fdd9fe`). Nothing is published to PyPI or npm. | The image SBOMs below record the resolved Python packages; the UI bundle SBOM records the npm packages |
| Backend image (`Dockerfile.backend`) | Built by Compose. The Dockerfile notes it is published internally as `bpf-maiw-backend`, but no workflow in this repository pushes it. | `maiw-backend.cdx.json`: Debian packages + Python packages |
| Frontend image (`Dockerfile.frontend`) | As above (`bpf-maiw-frontend`) | `maiw-frontend.cdx.json`: Alpine packages + nginx |
| Web UI bundle (static JS inside the frontend image) | Compiled from `src/ui/web` at image build time | `maiw-ui-bundle.cdx.json`: production npm dependencies from `src/ui/web/package-lock.json`. An image scan cannot see them, because only the compiled bundle ships. |
| MCP domain images (`Dockerfile.mcp` ×4) | Built locally by Compose only | `maiw-mcp.cdx.json`. The four images differ only in server code, so one SBOM (equipment) covers their packages. |
| Third-party images (TimescaleDB, Redis, Kafka, etcd, MinIO, Milvus, nginx, NIM) | Pulled from their publishers; MAIW does not redistribute them | Not generated here; they are the publishers' artifacts |
| Helm chart | None in this repository | — |

**Owner confirmation needed:** whether `bpf-maiw-backend` and `bpf-maiw-frontend` are actually published, where, and whether they should be registered as nSpect artifacts. nSpect currently shows no registered binary or container image.

## Contents and validation

`scripts/security/validate_sbom.py` stamps each SBOM's `metadata.properties` with:
- `maiw:artifact`;
- `maiw:git_sha`, the commit built;
- `maiw:release_version`, from `scripts/security/release_version.sh` (see [Release version](#release-version));
- `maiw:repository`;
- for images, `maiw:artifact_digest`, the local image ID.

It then fails unless the SBOM:
- validates against the CycloneDX JSON schema of its `specVersion`, using `cyclonedx-python-lib`'s strict validator;
- lists at least the minimum number of components, so an empty or truncated inventory fails;
- records the generating tool;
- carries a semantic version (`2.1.1`, `2.2.0-rc.1`, `2.1.1+16.g4d2e0c4`; no leading `v`).

### Release version

`scripts/security/release_version.sh` decides `maiw:release_version`. The SonarQube `projectVersion` uses the same helper, so the two always agree.

| Commit | `maiw:release_version` | Example |
|---|---|---|
| Release candidate, built with `MAIW_RELEASE_VERSION` set | that version | `2.1.2` |
| Carries a `v*` tag | the tag's version | `2.1.1` (the CI run for a published release) |
| Anything else | `<last tag>+<commits since>.g<short sha>`, semver build metadata | `2.1.1+16.g4d2e0c4` |
| No `v*` tag reachable (shallow clone) | `0.0.0+g<short sha>` | `0.0.0+g4d2e0c4` |

Until #268, every build was stamped with the latest tag reachable from it. A release candidate built before its tag therefore carried the previous version (the v2.1.1 candidate `4259fa3` said `2.1.0` and was re-stamped by hand for nSpect), and every later `main` build looked like the last release. A version with `+…` is never a release.

`MAIW_RELEASE_VERSION` must be `X.Y.Z` or `X.Y.Z-pre`. If the commit already carries a different `v*` tag, the helper exits 2 and the SBOM step fails.

Trivy's output also includes package URLs (purl), licences (90–100% of components) and the dependency graph.

Baseline, generated from `main` `0fbcb69` with Trivy 0.70.0:

| SBOM | Components | Notes |
|---|---|---|
| maiw-backend | 190 | 101 PyPI, 87 Debian. Includes `aiohttp` 3.14.5, `fastapi` 0.162.0, `langchain-core` 1.7.3, `uvicorn` 0.54.0 and `bcrypt` 5.0.0. |
| maiw-mcp | 154 | 66 PyPI, 87 Debian |
| maiw-frontend | 71 | 70 Alpine packages |
| maiw-ui-bundle | 1,379 | 1,378 npm packages. `react-scripts` is a production dependency in `package.json`, so the build toolchain is included. |

## CI

Each matrix job of **Image Scan** in `.github/workflows/ci-cd.yml` does the following:
- builds the image;
- generates its SBOM with the pinned Trivy action (the frontend job adds the UI bundle);
- validates and stamps it;
- uploads it as the artifact `sbom-<image>`, kept 90 days.

An invalid or truncated SBOM fails the job. The validator's own unit tests (`tests/unit/test_validate_sbom.py`) run in the CORE test job.

To get the SBOMs for a commit: open its CI/CD Pipeline run, then **Artifacts → `sbom-backend` / `sbom-frontend` / `sbom-mcp`**.

For a release candidate, run the pipeline by hand so the SBOMs carry the version being prepared: **Actions → CI/CD Pipeline → Run workflow**, choose the branch whose head is the candidate (normally `main`), and enter `release_version` (for example `2.1.2`). The **Validate SBOM** step logs the version it stamped.

## Locally

```bash
python3 -m pip install "cyclonedx-python-lib[json-validation]==11.12.0"
scripts/security/generate_sbom.sh            # writes sbom/
MAIW_RELEASE_VERSION=2.1.2 scripts/security/generate_sbom.sh   # release candidate
docker rmi maiw-backend:sbom maiw-frontend:sbom maiw-mcp:sbom
```

The script builds the three images from the checkout. It runs the same Trivy version as CI (`aquasec/trivy:0.70.0`, pinned by digest) as the invoking user, and validates each SBOM. For SPDX instead of CycloneDX, run Trivy with `--format spdx-json`; the validator handles CycloneDX only.

## nSpect

The nSpect program page offers **Actions → Manage SBOM**. Whether it accepts a direct upload of these files, a pipeline submission, or only nSpect's own scan has not been verified, because nSpect is not accessible from this environment. No upload has been made. For the steps a program owner needs, see `nspect-reconciliation.md`.
