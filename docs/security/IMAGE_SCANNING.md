# Vulnerability Scanning Baseline

CI runs Trivy two ways (`.github/workflows/ci-cd.yml`):

| Job | What it scans | Uploaded to code scanning | Fails CI on |
|---|---|---|---|
| Security Scan | The repository: `requirements*.txt`, `pyproject.toml` and every `package-lock.json`, devDependencies included | category `trivy` (default) | fixable CRITICAL (HIGH report-only) |
| Image Scan (backend, frontend, mcp) | The images built from `Dockerfile.backend`, `Dockerfile.frontend` and `Dockerfile.mcp`: OS packages and every installed Python or Node package | categories `trivy-image-backend`, `trivy-image-frontend`, `trivy-image-mcp` | fixable HIGH or CRITICAL |

The image scan exists because the repository scan cannot see what an image contains. The first image scan found the following, none of which appeared in the repository scan:
- nginx in the frontend base image;
- `jaraco.context` and `wheel`, vendored inside the MCP image's `setuptools`;
- `curl` in the MCP image, which nothing used.

"Fixable" means a fixed version has been released. Findings without one cannot fail CI. They stay visible in code scanning and are listed below as disclosed risks: an image with no fixable finding is not an image with no known vulnerability.

## Baseline (2026-11-02, Trivy 0.75 DB)

### Images: no fixable HIGH or CRITICAL (enforced by CI)

| Image | Base | HIGH | CRITICAL | Fixable |
|---|---|---|---|---|
| backend | `python:3.13.16-slim-trixie` (Debian 13.7) | 45 | 0 | 0 |
| frontend | `nginxinc/nginx-unprivileged:1.30.6-alpine3.24` | 0 | 0 | 0 |
| mcp | `python:3.11-slim` (Debian 13.7) | 45 | 0 | 0 |

**Disclosed risk:** the backend and MCP images each carry 45 HIGH findings that have no fix. They are all in Debian packages with no fixed version published yet:
- util-linux (`libblkid1`, `libmount1`, `libuuid1`, `mount`, `login` and others);
- ncurses, `libsqlite3-0`, `libsystemd0`/`libudev1`, `perl-base` and `libacl1`.

Both Dockerfiles run `apt-get upgrade`, so the next CI build picks up each fix when Debian publishes it. A published fix that does not reach the image fails the image gate.

Changes that reached this baseline:
- **frontend:** nginx 1.30.5 → 1.30.6, for three HIGH findings. nginx comes from nginx.org's Alpine repository, so the Dockerfile's `apk upgrade` does not update it; the base image has to change. Dependabot does not update `ARG` image defaults, so check this scan when an nginx advisory appears.
- **mcp:**
  - Removed `setuptools`, `wheel` and `pip` after installation, which clears HIGH findings in `jaraco.context` 5.3.0 and `wheel` 0.45.1 (both vendored in `setuptools`).
  - Removed the unused `curl`, which carried 4 unfixed HIGH findings.
  - Added `apt-get upgrade`, as in the backend image.

### Repository (report-only)

The three `undici` 6.29.0 HIGH findings (CVE-2026-87018, CVE-2026-109383, CVE-2026-109869) in the root `package-lock.json` are fixed (#266). That copy is bundled inside the `npm` package that `semantic-release` depends on, so it could not be overridden; `npm` 11.21.2 bundles `undici` 6.29.1, and the root lockfile now resolves it.

| Package | Lockfile | Findings | Why it stays |
|---|---|---|---|
| `uuid` 8.3.2 | `src/ui/web/package-lock.json` | 1 HIGH (CVE-2026-41907; Medium on GitHub) | Pulled in by the `react-scripts` 5 build and development-server chain; not in the browser bundle or any image. Goes away with the move off Create React App (#265). |

`webpack-dev-middleware` was updated from 7.4.5 to 7.4.6 (one HIGH finding). It is used only by the development server.

`svgo` 1.3.2 (3 HIGH: CVE-2026-73650, CVE-2026-84369, CVE-2026-84370; nSpect BDSA-2026-24092), pulled in by `react-scripts` → `@svgr/webpack` 5 → `@svgr/plugin-svgo` 5, is replaced by 4.1.0 through a scoped `overrides` entry in `src/ui/web/package.json`. `@svgr/plugin-svgo` 5 cannot call the 4.x API, which is safe only because `react-scripts` configures that loader with `svgo: false`, so the plugin never runs svgo. `src/ui/web/src/__tests__/svgrSvgoDisabled.test.ts` fails if svgo is enabled there or the override stops resolving. The production build is byte-identical with and without the override. The other copy, `svgo` 2.8.4 under `cssnano` → `postcss-svgo`, is already past the fixed versions.

## HIGH gating

- **Images:** fixable HIGH and CRITICAL fail the Image Scan job. In practice, the job fails when a released fix has not reached an image: a base-image bump (nginx is set by an `ARG` that Dependabot does not update) or a Python package.
- **Repository:** HIGH stays report-only while the `uuid` finding above remains. Do not add findings to a `.trivyignore`: Trivy would leave them out of the uploaded SARIF, and code scanning would then close those alerts as fixed. Once the UI is off `react-scripts` (#265), the filesystem gate can be raised to fixable HIGH.

## Running the scans locally

```bash
docker build -f Dockerfile.mcp --build-arg MCP_DOMAIN=equipment -t maiw-mcp:scan .
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:0.75.0 \
  image --scanners vuln --severity HIGH,CRITICAL maiw-mcp:scan
```

Remove the scan images afterwards (`docker rmi maiw-mcp:scan`).
