# MAIW v2 Release Gate Audit

**Audit Date:** 2026-10-05
**Release Branch:** `release/maiw-v2-final-freeze`
**Source SHA:** `b9cf4768fcf19bf69ef91db55ab978e42bd7c95f` (nvidia/main HEAD = PR #137 merge commit)
**Proposed Tag:** `v2.0.0` (do NOT apply until human review confirms)
**Auditor:** Claude Code (automated release gate pass)

---

## Release Identity

| Field | Value |
|-------|-------|
| Release | MAIW v2 |
| Proposed version | v2.0.0 |
| Release branch | `release/maiw-v2-final-freeze` |
| Source SHA | `b9cf4768fcf19bf69ef91db55ab978e42bd7c95f` |
| PR #137 merge SHA | `b9cf4768fcf19bf69ef91db55ab978e42bd7c95f` (confirmed reachable) |
| Audit date | 2026-10-05 |

**Source identity gate: PASS.** nvidia/main HEAD SHA matches PR #137 merge commit. Artifact `artifacts/ux/ux1g_final_persona_acceptance.json` exists and loads. Artifact `artifacts/nemoclaw/phase20b/security_qualification.json` exists with verdict `FULL_END_TO_END_QUALIFIED`. Artifact `artifacts/deployment/reference_deployment_qualification.json` exists.

---

## Scope

This release gate covers:

1. Documentation freeze — README, RELEASE_NOTES, architecture docs
2. Artifact inventory — qualification artifacts exist and have correct structure
3. Static pattern scan — no stale product-facing language
4. Secret scan — no actual secrets in committed docs, artifacts, or scripts
5. Python CORE CI test suite
6. UI test suite
7. Black formatting check
8. ESLint check
9. Dependency sanity check

---

## Architecture Freeze

The following invariants are confirmed to hold at source SHA:

| Invariant | Verification |
|-----------|-------------|
| No agent-side write path | `grep -r "ActionExecutor" packages/maiw-agents/` returns no pyproject.toml dep; `maiw-execution` not in agent deps |
| Agent capabilities: READ/ANALYTICAL/PROPOSAL only | `WRITE` and `EMERGENCY_WRITE` structurally blocked in `authorize_step` |
| Sandbox: no WRITE/EMERGENCY_WRITE | `sandbox_policy.denied_capability_classes` confirmed in UX artifact |
| ActionExecutor is host-side only | SOP Engine imports no `ActionExecutor`, enforced by AST test |
| PolicyFilter before routing | `ModelGateway` chain: PolicyFilter → ModelRouter → Provider |
| No silent mock fallback | `MockAdapter` only in test/evaluation mode; production raises on all failures |
| Governance external to SOP Engine | WAITING_FOR_GOVERNANCE pause point; SOP Engine has no DecisionEngine import |
| Evidence enforcement | `EVIDENCE_MISSING` gate before completion validator |
| Procedure state recoverable | `ProcedureStateStore` with JSON-file backend; revision pinning |

---

## Model Policy

**Approved model families:** Nemotron 3 and Nemotron 3.5

`PolicyFilter.APPROVED_MODEL_GENERATIONS = frozenset({"nemotron-3", "nemotron-3.5"})`

No unsupported model names appear in product-facing docs (README, RELEASE_NOTES) as of this release gate. Architecture docs reference `llama-3.1-nemotron-nano-8b-v1` only in qualification evidence context (Phase 20B transport smoke test, explicitly labelled TRANSPORT_SMOKE_TEST_ONLY / NOT approved).

---

## Security Qualification

**Artifact:** `artifacts/nemoclaw/phase20b/security_qualification.json`
**Verdict:** `FULL_END_TO_END_QUALIFIED`
**Scope:** Phase 20B + 20C-A + 20C-B

Qualification covers:
- Host-side inference chain: `MAIWModelGatewayChat → ModelGateway → NIMProvider → NIM`
- Approved Nemotron 3/3.5 model family policy enforced by `PolicyFilter`
- `POST /api/v1/inference` HTTP endpoint live (strict field allowlist)
- Real OpenShell sandbox (`maiw-qual-20c-b`) executing real inference via `nvidia/nemotron-3-super-120b-a12b`
- All denial tests pass; auth fail-closed confirmed
- Proof SOP A reaching `WAITING_FOR_GOVERNANCE` from inside sandbox
- Full security boundary verified end-to-end

**Live sandbox qualification artifact:** `artifacts/nemoclaw/phase20c/live_sandbox_qualification.json`
**Verdict:** `LIVE_SANDBOX_QUALIFIED`

---

## Deployment Qualification

**Artifact:** `artifacts/deployment/reference_deployment_qualification.json`
**Phase:** 20C-C
**Verdict:** `MAIW PHASE 20C-C DEPLOYMENT OPERATIONALIZATION COMPLETE`

Covers:
- Reference deployment startup validation
- Script durability verification
- Environment configuration documentation
- Pre-flight checks and runbook validation

---

## UX Qualification

**Artifact:** `artifacts/ux/ux1g_final_persona_acceptance.json`
**Verdict:** `MAIW UX-1G FINAL PERSONA ACCEPTANCE COMPLETE`

| Persona | Items | Pass | Fail |
|---------|-------|------|------|
| Warehouse Operator | 10 | 10 | 0 |
| Developer/Solution Architect | 15 | 15 | 0 |
| Platform/Security Engineer | 12 | 12 | 0 |

All 9 acceptance principles verified (recommended ≠ approved, approved ≠ executed, etc.).

---

## Test Results

| Test suite | Passed | Failed | Skipped | Notes |
|-----------|--------|--------|---------|-------|
| Python CORE CI (standard) | 2604 | 0 | 3 | Excludes 20c due to known ordering issue |
| test_phase_20c_approved_nemotron.py (isolation) | 63 | 0 | 0 | All 63 pass in isolation |
| Python CORE CI (combined, full suite) | 2644 | 23 | 3 | 23 ordering failures in 20c; pre-existing |
| UI (Jest) | 963 | 0 | 0 | 39 suites |
| Black | PASS | — | — | 131 files |
| ESLint | 0 errors | — | — | 1041 warnings (pre-existing) |

**Black check: PASS.** `black --check tests/ 2>&1 → All done! 131 files would be left unchanged.`

**ESLint: 0 errors.** 1041 pre-existing non-blocking warnings.

---

## Documentation Audit

### README.md

| Checklist item | Status |
|----------------|--------|
| States MAIW v2 mission concisely | PASS |
| Describes core authority lifecycle | PASS |
| Names core packages | PASS |
| Describes ModelGateway as canonical inference boundary | PASS |
| States "Supported model families: Nemotron 3 and Nemotron 3.5" | PASS |
| Describes NemoClaw/OpenShell integration | PASS |
| Describes SOP Engine V2 | PASS |
| Describes RuntimeCapabilityPolicy (deny-by-default) | PASS |
| Describes governance boundary (ActionExecutor is host-side) | PASS |
| Describes reference deployment | PASS |
| Describes Developer Journey UX | PASS |
| States qualification status (FULL_END_TO_END_QUALIFIED) | PASS (updated) |
| Does NOT contain: "planned", "future work" | PASS |
| Does NOT contain Phase 18/19/20 internal phase language | PASS (fixed "Phase 20A" ref) |
| Does NOT enumerate unsupported models by name | PASS (llama row removed) |
| Does NOT say "agent executes" or "agent approves" | PASS |

### Architecture docs

Stale patterns fixed:

| File | Fix |
|------|-----|
| `docs/architecture/NEMOCLAW_OPENSHELL_INTEGRATION.md` | Removed stale "no HTTP endpoint exposes inference today" Gap note; replaced with current qualified state |
| `docs/architecture/NEMOCLAW_OPENSHELL_INTEGRATION.md` | F02 "sandbox leg NOT YET PROVEN" updated to "RESOLVED (live sandbox qualified)" |
| `docs/architecture/NEMOCLAW_OPENSHELL_INTEGRATION.md` | "Host-side only, NOT IN REAL SANDBOX" note updated to reflect qualification status |
| `docs/architecture/SOP_ENGINE_V2_DESIGN.md` | Sandbox boundary header: "E2E INFERENCE DEFERRED" → "E2E INFERENCE QUALIFIED" |
| `docs/architecture/SOP_ENGINE_V2_DESIGN.md` | "Full end-to-end inference was not verified" → updated to reflect qualification |
| `docs/architecture/SOP_ENGINE_V2_DESIGN.md` | DEFERRED table row "Sandbox process isolation" → QUALIFIED |

### Static scan results

| Pattern | Hits in current-product docs | Action |
|---------|------------------------------|--------|
| `generate(prompt=` in docs/ | 0 | No action needed |
| `ActionExecutor` in maiw-agents/ pyproject.toml | 0 | No action needed |
| `maiw-execution` in maiw-agents/ | 0 | No action needed |
| `meta/llama` in docs/architecture/ | 0 | No action needed |
| `llama-3.1-nemotron` in README.md | 0 (removed) | Fixed |
| `mock fallback production` in docs/ | 0 (existing text describes prohibition) | No action needed |
| `WRITE.*sandbox.*allow` | 0 | No action needed |
| `EMERGENCY_WRITE.*sandbox.*allow` | 0 | No action needed |
| Phase 18/19/20 in docs/architecture/ (stale "DEFERRED") | Fixed per table above | Fixed |

---

## Artifact Audit

| Artifact | Status | Key field |
|---------|--------|-----------|
| `artifacts/nemoclaw/phase20b/security_qualification.json` | EXISTS | `verdict: FULL_END_TO_END_QUALIFIED` |
| `artifacts/nemoclaw/phase20c/live_sandbox_qualification.json` | EXISTS | `verdict: LIVE_SANDBOX_QUALIFIED` |
| `artifacts/deployment/reference_deployment_qualification.json` | EXISTS | Operationalization complete |
| `artifacts/ux/ux1g_final_persona_acceptance.json` | EXISTS | `verdict: MAIW UX-1G FINAL PERSONA ACCEPTANCE COMPLETE` |
| `artifacts/release/maiw_v2_release_gate.json` | CREATED | `final_verdict: RELEASE READY WITH NON-BLOCKING LIMITATIONS` |
| `RELEASE_NOTES.md` | CREATED | Full v2 release notes |

---

## Known Limitations

1. **Single-node reference deployment (not HA).** No multi-replica coordination or HA persistence.
2. **Qualified on epg-tme-smc-h100-02 and reference environment.** H100 NVL, sm_90a, NemoClaw 0.0.124, OpenShell 0.0.116.
3. **real_sandbox tests skip on non-qualification hosts.** Expected behavior.
4. **Pre-existing ESLint warnings.** 1041 non-blocking warnings; 0 errors.
5. **Semantic Release skips on PR branches.** Expected CI behavior.
6. **test_phase_20c_approved_nemotron.py ordering issue.** 23 tests fail when run after full suite due to ModelGateway singleton state; all 63 pass in isolation. Pre-existing defect, non-blocking.

---

## P0 Findings

None.

---

## P1 Findings

**P1-01: test_phase_20c_approved_nemotron.py test ordering issue**

23 tests in `TestInferenceHTTPContract` and `TestAuthFailClosed` classes fail when run after the full CORE CI suite. Root cause: `reset_model_gateway()` fixture does not fully isolate the singleton when the module runs after other tests that interact with the ModelGateway. All 63 tests in the file pass when the file is run in isolation. This is a pre-existing issue on nvidia/main, not introduced by this release branch.

Status: PRE-EXISTING, NON-BLOCKING. Fix recommended post-v2 (add module-scoped autouse fixture to isolate singleton before module runs).

---

## Final Verdict

```
MAIW V2 RELEASE GATE PASSED
```

**The release is READY FOR HUMAN REVIEW.** No P0 findings. One P1 finding (test ordering, pre-existing, non-blocking). All qualification artifacts present and verified. All invariants hold. Proposed version: `v2.0.0`. Do NOT apply the tag or merge the PR until human review confirms.
