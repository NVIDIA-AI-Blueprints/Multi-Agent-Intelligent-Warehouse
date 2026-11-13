# Merge protection for `main`

Changes reach `main` only through a squash-merged pull request. A workflow file
can make a check *run* on a pull request; only a repository ruleset can make it
*required*. This page lists the required checks and the exact ruleset settings,
and shows how to verify what is actually enforced.

## Required checks

Every required check runs on every pull request to `main`, on a
GitHub-hosted runner, without repository secrets.

| Check (status context) | Workflow | What it proves |
|---|---|---|
| `Test & Quality Checks (3.11, 22)` | `.github/workflows/ci-cd.yml`, job `test` | CORE CI Python tests, UI tests, lint, typecheck ([TEST_STRATEGY.md](../architecture/TEST_STRATEGY.md)) |
| `CodeQL (python)` | `.github/workflows/codeql.yml`, job `analyze` | CodeQL analysis of the Python code completed |
| `CodeQL (javascript)` | `.github/workflows/codeql.yml`, job `analyze` | CodeQL analysis of the UI code completed |
| `Security Scan` | `.github/workflows/ci-cd.yml`, job `security` | Trivy filesystem scan and dependency checks |
| `Image Scan (backend)`, `Image Scan (frontend)`, `Image Scan (mcp)` | `.github/workflows/ci-cd.yml`, job `image-scan` | Each image builds, its Trivy scan passes, and its SBOM is valid |

All of them come from the GitHub Actions app (integration id `15368`). Pinning
the integration id stops a commit status with the same name, posted by
anything else, from satisfying the rule.

## The deployment test is not a pull request check

`deploy-and-test` (`.github/workflows/main.yml`) runs on a self-hosted GPU
runner with repository credentials (`NVIDIA_API_KEY` and registry logins).
It does not run on pull requests:

- For a pull request, GitHub runs the workflow files of the pull request
  itself. A guard written in the workflow (for example "refuse forks") can be
  removed by the pull request it is meant to stop, so it is not a security
  boundary. GitHub advises against running untrusted pull request code on
  self-hosted runners.
- Dependabot pull requests would need the credential as a Dependabot secret.
  Dependency updates do not need it, and it is not stored there.

It runs after every merge to `main`, and a maintainer can run it on any
branch with **Actions → Multi-Agent-Intelligent-Warehouse deployment test →
Run workflow** before merging a change that needs it. A failure after merge
is fixed forward, and a release candidate needs a green run
([RELEASING.md](RELEASING.md)).

These checks are not required either:

- `MAIW internal pytest (NGC)` reports `neutral` (NOT RUN) whenever the
  internal NGC test image is unavailable. It is a release-evidence row.
- `SonarQube Scan` needs network access to `sonar.nvidia.com`, which
  GitHub-hosted runners do not have. A failed job there is a network failure,
  not an analysis result. The manual scan in [RELEASING.md](RELEASING.md) is
  the release evidence.
- `Trivy` and `CodeQL` (code-scanning results, GitHub Advanced Security app)
  are reviewed on the pull request.

`tests/api/test_merge_protection_workflows.py` fails if a required check
stops running on every pull request, or if a workflow that pull requests
trigger runs on a self-hosted runner.

## Ruleset settings

Applied 2026-11-13 to the repository ruleset `main` (id 19123293, target:
default branch), next to its deletion, non-fast-forward and pull-request
(squash only) rules:

```json
{
  "type": "required_status_checks",
  "parameters": {
    "strict_required_status_checks_policy": false,
    "do_not_enforce_on_create": false,
    "required_status_checks": [
      {"context": "Test & Quality Checks (3.11, 22)", "integration_id": 15368},
      {"context": "CodeQL (python)", "integration_id": 15368},
      {"context": "CodeQL (javascript)", "integration_id": 15368},
      {"context": "Security Scan", "integration_id": 15368},
      {"context": "Image Scan (backend)", "integration_id": 15368},
      {"context": "Image Scan (frontend)", "integration_id": 15368},
      {"context": "Image Scan (mcp)", "integration_id": 15368}
    ]
  }
}
```

`strict_required_status_checks_policy: false` does not require a pull request
to be up to date with `main` before merging.

## Verify what is enforced

Do not infer protection from workflow files. Ask GitHub what applies to `main`:

```bash
gh api repos/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/rules/branches/main \
  --jq '.[] | select(.type == "required_status_checks") | .parameters.required_status_checks'
```

The output must list the seven contexts with `integration_id` 15368. An empty
result means no check is required. Classic branch protection is not used:
`GET /repos/{owner}/{repo}/branches/main/protection` returns 404.
