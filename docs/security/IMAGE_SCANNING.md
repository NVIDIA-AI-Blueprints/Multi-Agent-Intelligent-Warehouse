# Vulnerability Scanning Baseline

CI runs Trivy two ways (`.github/workflows/ci-cd.yml`):

| Job | What it scans | Uploaded to code scanning | Fails CI on |
|---|---|---|---|
| Security Scan | The repository: `requirements*.txt`, `pyproject.toml` and every `package-lock.json`, devDependencies included | category `trivy` (default) | fixable CRITICAL |
| Image Scan (backend, frontend, mcp) | The images built from `Dockerfile.backend`, `Dockerfile.frontend` and `Dockerfile.mcp`: OS packages and every installed Python or Node package | categories `trivy-image-backend`, `trivy-image-frontend`, `trivy-image-mcp` | fixable CRITICAL |

The image scan exists because the repository scan cannot see what an image contains. The first image scan found the following, none of which appeared in the repository scan:
- nginx in the frontend base image;
- `jaraco.context` and `wheel`, vendored inside the MCP image's `setuptools`;
- `curl` in the MCP image, which nothing used.

HIGH findings are reported in each job's log and in code scanning, but they do not fail CI yet. The baseline below shows what is left before they can.

## Baseline (2026-11-02, Trivy 0.75 DB)

### Images: no fixable HIGH or CRITICAL

| Image | Base | HIGH | CRITICAL | Fixable |
|---|---|---|---|---|
| backend | `python:3.13.16-slim-trixie` (Debian 13.7) | 45 | 0 | 0 |
| frontend | `nginxinc/nginx-unprivileged:1.30.6-alpine3.24` | 0 | 0 | 0 |
| mcp | `python:3.11-slim` (Debian 13.7) | 45 | 0 | 0 |

The 45 HIGH findings in the backend and MCP images are all Debian packages with no fixed version published:
- util-linux (`libblkid1`, `libmount1`, `libuuid1`, `mount`, `login` and others);
- ncurses, `libsqlite3-0`, `libsystemd0`/`libudev1`, `perl-base` and `libacl1`.

Both Dockerfiles run `apt-get upgrade`, so a rebuilt image picks up each fix when Debian publishes it.

Changes that reached this baseline:
- **frontend:** nginx 1.30.5 → 1.30.6, for three HIGH findings. nginx comes from nginx.org's Alpine repository, so the Dockerfile's `apk upgrade` does not update it; the base image has to change. Dependabot does not update `ARG` image defaults, so check this scan when an nginx advisory appears.
- **mcp:**
  - Removed `setuptools`, `wheel` and `pip` after installation, which clears HIGH findings in `jaraco.context` 5.3.0 and `wheel` 0.45.1 (both vendored in `setuptools`).
  - Removed the unused `curl`, which carried 4 unfixed HIGH findings.
  - Added `apt-get upgrade`, as in the backend image.

### Repository: 5 fixable HIGH, none fixable here

| Package | Lockfile | Findings | Why it stays |
|---|---|---|---|
| `undici` 6.29.0 | `package-lock.json` (root) | 3 HIGH (CVE-2026-87018, CVE-2026-109383, CVE-2026-109869) | Bundled inside the `npm` package that `semantic-release` depends on. A bundled dependency cannot be overridden, and the newest `npm` (12.2.1) still bundles a vulnerable `undici`. The top-level `undici` is already 6.29.1. Release tooling only: it runs in the release job, not in any image. |
| `svgo` 1.3.2 | `src/ui/web/package-lock.json` | 2 HIGH (CVE-2026-73650, CVE-2026-84370) | Pulled in by `react-scripts` → `@svgr/webpack` 5. The fixed `svgo` versions (2.8.3+) have a different API that `@svgr/plugin-svgo` 5 cannot call. It runs only when application code imports an SVG as a component, which this UI does not: the one SVG is served from `public/`. It runs at build time and is not in the shipped image. |

`webpack-dev-middleware` was updated from 7.4.5 to 7.4.6 (one HIGH finding). It is used only by the development server.

## Making HIGH blocking

1. **Images:** already clean. Gating fixable HIGH in images would fail only when a newly published fix is not yet in an image. That would mostly be a base-image bump, such as nginx, or a Python package.
2. **Repository:** needs the five findings above to clear first. Do not add them to a `.trivyignore`: Trivy would leave them out of the uploaded SARIF, and code scanning would then close those alerts as fixed. The options are:
   - an `npm` release that bundles a fixed `undici`;
   - moving the UI off `react-scripts` 5, or onto an `@svgr/webpack` that uses a fixed `svgo`;
   - scoping the repository HIGH gate to Python and the UI's production dependencies.

## Running the scans locally

```bash
docker build -f Dockerfile.mcp --build-arg MCP_DOMAIN=equipment -t maiw-mcp:scan .
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy:0.75.0 \
  image --scanners vuln --severity HIGH,CRITICAL maiw-mcp:scan
```

Remove the scan images afterwards (`docker rmi maiw-mcp:scan`).
