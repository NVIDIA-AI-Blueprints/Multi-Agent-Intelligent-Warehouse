# Releasing MAIW

Releases are cut deliberately by a maintainer. No workflow creates a tag,
a GitHub release or a release commit on its own: pushes to `main` run tests,
scans and the deployment test only.

Green CI is necessary, not sufficient. A release also needs the security
gates in step 3 (SonarQube, nSpect, SBOM) recorded for the exact candidate
commit; without them the decision is no-go.

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

### Security gates (release-blocking)

These apply to the exact candidate SHA. Unlike the NGC suite, a missing
result is not a NOT RUN: it is a no-go. A failing result needs a written
disposition from Blueprints SRE (or an approved nSpect exception) before
release, recorded in the notes.

- **SonarQube.** An analysis of the candidate SHA, from its
  `SonarQube Analysis` run or, if CI has no NVIDIA-network runner, from
  `scripts/security/run_sonar_scan.sh` on an NVIDIA-network host (candidate
  checkout as `MAIW_SONAR_SOURCE_DIR`, with the `sonar-coverage` artifact of
  its CI run as `coverage.xml`). Set `MAIW_RELEASE_VERSION` to the version
  being released (the `release_version` input when dispatching the
  workflow), so the analysis is recorded under that version rather than a
  development version such as `2.1.1+16.g<sha>`. Record the analysis ID,
  its timestamp and the quality gate status from the evidence file. Exit code 0 is a passing gate;
  5 is an analysis whose gate failed (each failing condition needs a
  disposition); 2, 3 and 4 mean no usable analysis. An analysis of a
  different commit does not count, and neither does a green CI run whose
  SonarQube job did not submit an analysis. Review every new security hotspot
  in SonarQube.
- **nSpect (NSPECT-NJMX-9GQU).** A fresh nSpect / Pulse OSS scan of the
  candidate. Critical and high findings are fixed or carry an approved
  exception. See `docs/security/nspect-reconciliation.md`.
- **SBOM.** The candidate's CycloneDX SBOMs, stamped with the version being
  released: run **CI/CD Pipeline** by hand on the candidate with the
  `release_version` input (artifacts `sbom-<image>`), or
  `MAIW_RELEASE_VERSION=<version> scripts/security/generate_sbom.sh` from a
  checkout of it. Check that `maiw:release_version` is the release version,
  not a `+…` development version, and that `maiw:git_sha` is the candidate.
  Valid per `scripts/security/validate_sbom.py`, submitted to nSpect
  (**Actions → Manage SBOM**). See `docs/security/sbom-generation.md`.
- **Evidence manifest.** Regenerate
  `docs/security/security-evidence-manifest.json` with
  `scripts/security/build_evidence_manifest.py`, the candidate SHA among the
  targets.

If a tool requires a tag before validation, use a release-candidate tag
(`vX.Y.Z-rc.N`), never the final release tag. A published release tag is not
moved or re-pointed; a fix ships in the next version.

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
| SonarQube | analysis `<analysis id>` (<timestamp>), quality gate <OK, or ERROR with SRE disposition (link)> |
| nSpect OSS scan (NSPECT-NJMX-9GQU) | <date>: <result; approved exceptions (link)> |
| SBOM submitted to nSpect | <date>: <artifacts> |
```

Changes that can break existing clients (removed routes, new request
restrictions, changed defaults) go in a **Compatibility** section near the
top of the notes, not only in the change list.

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
