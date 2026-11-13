# Merge protection for `main`

Changes reach `main` only through a squash-merged pull request. A workflow file
can make a check *run* on a pull request; only a repository ruleset can make it
*required*. This page lists the required checks and the exact ruleset settings,
and shows how to verify what is actually enforced.

## Required checks

| Check (status context) | Workflow | What it proves |
|---|---|---|
| `Test & Quality Checks (3.11, 22)` | `.github/workflows/ci-cd.yml`, job `test` | CORE CI Python tests, UI tests, lint, typecheck ([TEST_STRATEGY.md](../architecture/TEST_STRATEGY.md)) |
| `deploy-and-test` | `.github/workflows/main.yml` | The full Compose deployment on the GPU runner: health, readiness, MCP, durability, monitoring |
| `CodeQL (python)` | `.github/workflows/codeql.yml`, job `analyze` | CodeQL analysis of the Python code completed |
| `CodeQL (javascript)` | `.github/workflows/codeql.yml`, job `analyze` | CodeQL analysis of the UI code completed |

All four come from the GitHub Actions app (integration id `15368`). Pinning
the integration id stops a commit status with the same name, posted by
anything else, from satisfying the rule.

These checks are **not** required:

- `MAIW internal pytest (NGC)` reports `neutral` (NOT RUN) whenever the
  internal NGC test image is unavailable, so requiring it would block every
  pull request. It stays a release-evidence row ([RELEASING.md](RELEASING.md)).
- `SonarQube Scan` needs network access to `sonar.nvidia.com`, which
  GitHub-hosted runners do not have. A failed job there is a network failure,
  not an analysis result. The manual scan in [RELEASING.md](RELEASING.md) is
  the release evidence.
- `Security Scan`, `Image Scan (*)` and `Trivy` run on every pull request and
  are reviewed there; making them required is a separate decision.

### Limitations

- **Pull requests from forks** cannot pass `deploy-and-test`. They get no
  repository secrets, and their code must not run on the self-hosted GPU
  runner, so the job fails at its first step on a GitHub-hosted runner. A
  maintainer pushes the branch to this repository and opens the pull request
  from there.
- **Dependabot pull requests** read Dependabot secrets, not Actions secrets.
  `deploy-and-test` fails at "Authenticate Docker to nvcr.io" unless
  `NVIDIA_API_KEY` is also stored under *Settings → Secrets and variables →
  Dependabot*. That is a credential decision for a repository admin.
- A required check that never reports blocks the merge. `ci-cd.yml`,
  `codeql.yml` and `main.yml` therefore run on every pull request to `main`,
  with no path filters (`tests/api/test_merge_protection_workflows.py`).

## Ruleset settings

Add a `required_status_checks` rule to the existing repository ruleset named
`main` (target: default branch). Keep its other rules (deletion,
non-fast-forward, pull request with squash only) unchanged.

```json
{
  "type": "required_status_checks",
  "parameters": {
    "strict_required_status_checks_policy": false,
    "do_not_enforce_on_create": false,
    "required_status_checks": [
      {"context": "Test & Quality Checks (3.11, 22)", "integration_id": 15368},
      {"context": "deploy-and-test", "integration_id": 15368},
      {"context": "CodeQL (python)", "integration_id": 15368},
      {"context": "CodeQL (javascript)", "integration_id": 15368}
    ]
  }
}
```

`strict_required_status_checks_policy: false` does not force a pull request
to be up to date with `main` before merging. Setting it to `true` is stricter.
The cost is that every merge into `main` forces another GPU deployment run on
each open pull request.

In the web UI: *Settings → Rules → Rulesets → main → Require status checks to
pass*. Add each context above and choose *GitHub Actions* as its source.

## Verify what is enforced

Do not infer protection from workflow files. Ask GitHub what applies to `main`:

```bash
gh api repos/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse/rules/branches/main \
  --jq '.[] | select(.type == "required_status_checks") | .parameters.required_status_checks'
```

The output must list the four contexts with `integration_id` 15368. An empty
result means no check is required. Classic branch protection is not used:
`GET /repos/{owner}/{repo}/branches/main/protection` returns 404.
