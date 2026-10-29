# Releasing MAIW

Releases are cut deliberately by a maintainer. No workflow creates a tag,
a GitHub release or a release commit on its own: pushes to `main` run tests,
scans and the deployment test only.

## 1. Choose the candidate

The candidate is a merged commit on `main` whose post-merge runs are green:

- CI/CD Pipeline (tests, typecheck, security scan) and CodeQL.
- Multi-Agent-Intelligent-Warehouse deployment test, including the
  `E2E: MCP tool calls` and `E2E: durability across backend restart` steps.

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
candidate from step 1) and the gate results. Remove the draft markers once
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
