# Releasing MAIW

Releases are cut deliberately by a maintainer. No workflow creates a tag,
a GitHub release or a release commit on its own: pushes to `main` run tests,
scans and the deployment test only.

## 1. Choose the candidate

The candidate is a merged commit on `main` whose post-merge runs are green:

- CI/CD Pipeline (tests, typecheck, security scan) and CodeQL.
- Multi-Agent-Intelligent-Warehouse deployment test, including the
  `E2E: MCP tool calls` and `E2E: durability across backend restart` steps.

Then read the candidate's **MAIW internal pytest (NGC)** check: the
deployment test posts it on the same commit.

| Check result | Meaning |
|---|---|
| success, `PASSED` | The internal NGC UI suite (`pytest -m maiw`) ran and passed. |
| failure, `FAILED` | The suite ran and failed. This is also the deployment test failing; the commit is not a candidate. |
| neutral, `NOT RUN: <reason>` | The suite did not execute, for example because the internal test image could not be pulled. The deployment test is still green, but **only deployment and readiness were verified**. |

A NOT RUN is not a pass. It does not block a release, but it must appear in
the release notes as described in step 4. The result mail's subject carries
the same result.

## 2. Preview the version (optional)

Run the **Release preview** workflow (`.github/workflows/release.yml`) from
`main`. It runs `semantic-release --dry-run` and logs the next version and the
generated notes from the conventional commits since the last tag. It creates
nothing. The preview is advisory: the version is the maintainer's decision,
following [Semantic Versioning](https://semver.org/).

## 3. Run the release gate on the candidate

On the reference host, following
[REFERENCE_DEPLOYMENT_RUNBOOK.md](REFERENCE_DEPLOYMENT_RUNBOOK.md):

- `scripts/preflight_reference_deployment.sh` and
  `scripts/smoke_test_reference_deployment.sh` pass.
- Live hosted model calls through `POST /api/v1/inference` return HTTP 200
  with `identity_verified=true` for each approved model binding.

Record anything that could not run (for example an internal test suite) as
NOT RUN in the release notes; do not omit it.

## 4. Finalize the notes

Release notes live in `RELEASE_NOTES_vX.Y.Z.md` with a matching
`CHANGELOG.md` entry. In the notes, identify the validated code commit (the
candidate from step 1) and the gate results.

Near the top of the notes, before the list of changes, include a validation
table with one row for each item that was checked or could not be checked.
The NGC suite row is required, and when the suite did not run it reads
**NOT RUN** with the reason and the deployment-test run link. Never write
"passed" or leave the row out:

```markdown
| Validation | Result |
|---|---|
| CI/CD Pipeline, CodeQL | PASS (`<sha>`) |
| Deployment test (deploy, readiness, MCP tool calls, restart durability) | PASS ([run](<run url>)) |
| Internal NGC MAIW pytest suite | **NOT RUN**: <reason> ([run](<run url>)) |
| Release gate on the reference host | PASS |
```

The table goes into the GitHub release body too, because the release is
published from this file. Remove the draft markers once
publication is approved. The notes do not name the tagged commit: its SHA
is not known until the notes PR merges.

## 5. Merge the notes, verify, tag and publish

Merge the notes PR. Then verify the resulting `main` commit: its post-merge
runs are green, and its diff from the validated code commit contains only
release notes, changelog and other non-code changes. Tag that commit:

```bash
git tag -a vX.Y.Z <commit> -m "MAIW vX.Y.Z"
git push nvidia vX.Y.Z
gh release create vX.Y.Z --verify-tag --title "MAIW vX.Y.Z" \
  --notes-file RELEASE_NOTES_vX.Y.Z.md \
  -R NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse
```

Publishing a release triggers the CI/CD Pipeline again on the tag.
