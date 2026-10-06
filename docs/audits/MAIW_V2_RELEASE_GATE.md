# MAIW v2 Release Gate Audit

**Audit Date:** 2026-10-06 (final correction pass)
**Release Branch:** `release/maiw-v2-final-freeze`
**Source SHA:** `b9cf4768fcf19bf69ef91db55ab978e42bd7c95f` (nvidia/main HEAD = PR #137 merge commit)
**Proposed Tag:** `v2.0.0` (do NOT apply until human review confirms)
**Auditor:** Claude Code (automated release gate pass — final correction pass)

---

## Release Identity

| Field | Value |
|-------|-------|
| Release | MAIW v2 |
| Proposed version | v2.0.0 |
| Release branch | `release/maiw-v2-final-freeze` |
| Source SHA | `b9cf4768fcf19bf69ef91db55ab978e42bd7c95f` |
| PR #137 merge SHA | `b9cf4768fcf19bf69ef91db55ab978e42bd7c95f` (confirmed reachable) |
| Audit date | 2026-10-06 |

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

MAIW v2 supports Nemotron 3 and Nemotron 3.5 model families. No unsupported or competitor model names appear in product-facing docs (README, RELEASE_NOTES) as of this release gate. Architecture docs reference `llama-3.1-nemotron-nano-8b-v1` only in qualification evidence context (Phase 20B transport smoke test, explicitly labelled TRANSPORT_SMOKE_TEST_ONLY / NOT approved).

**README model-language audit: PASS.** Sentence enumerating Llama-family Nemotron, Qwen, and unknown model families removed. Policy statement updated to: "MAIW v2 supports Nemotron 3 and Nemotron 3.5 model families."

---

## Package Ownership Audit

| Type | Actual Package | Doc Claims (pre-fix) | Status |
|------|---------------|----------------------|--------|
| `ActionProposal` | `maiw-decision` | `maiw-contracts` | CORRECTED in PACKAGE_OWNERSHIP.md, RELEASE_NOTES.md, README.md |
| `DecisionResult` | `maiw-decision` | `maiw-contracts` | CORRECTED |
| `ApprovalRecord` | `maiw-decision` | `maiw-contracts` | CORRECTED |
| `DecisionEngine` | `maiw-decision` | listed separately | CONSISTENT |
| `ModelGateway` | `maiw-models` | `maiw-models` | CORRECT |
| `RuntimeCapabilityPolicy` | `maiw-agents` | `maiw-agents` | CORRECT |
| `ProcedureStateStore` | `maiw-agents` | `maiw-agents` | CORRECT |
| `maiw-contracts` actual owns | Domain value objects (equipment, labor, wave, inventory) | listed governance types | CORRECTED |

All ownership corrections applied to `docs/architecture/PACKAGE_OWNERSHIP.md`, `RELEASE_NOTES.md`, and `README.md` repository structure section.

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
| Python CORE CI (full combined suite) | 2667 | 0 | 3 | Singleton ordering defect resolved; 0 failures |
| UI (Jest) | 963 | 0 | 0 | 39 suites |
| Black | PASS | — | — | 131+ files |
| ESLint | 0 errors | — | — | 1041 warnings (pre-existing) |

**Python test suite: 2667 passed, 0 failed, 3 skipped.** Singleton ordering defect (P1-01) resolved: root cause was hardcoded `sys.path.insert(0, "/home/nvidia/Multi-Agent-Intelligent-Warehouse")` in `tests/unit/reliability/test_ambiguous_write.py` which caused `src` module to resolve from main checkout (which lacks `src/api/routers/inference.py`). Fix: removed the unnecessary sys.path insertion; `maiw_api` is available via venv. Belt-and-suspenders: added module-level autouse `_reset_gateway_singleton` fixture to `test_phase_20c_approved_nemotron.py`.

**Black check: PASS.** `black --check tests/ 2>&1 → All done! files would be left unchanged.`

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
| States qualification status (FULL_END_TO_END_QUALIFIED) | PASS |
| Does NOT contain: "planned", "future work" | PASS |
| Does NOT contain Phase 18/19/20 internal phase language | PASS |
| Does NOT enumerate unsupported models by name | PASS (corrected: Llama/Qwen removed) |
| Does NOT say "agent executes" or "agent approves" | PASS |
| maiw-contracts described correctly (domain value objects) | PASS (corrected) |
| maiw-decision described correctly (ActionProposal, DecisionEngine) | PASS (corrected) |

### Architecture docs

Stale patterns fixed:

| File | Fix |
|------|-----|
| `docs/architecture/NEMOCLAW_OPENSHELL_INTEGRATION.md` | Removed stale "no HTTP endpoint exposes inference today" Gap note |
| `docs/architecture/NEMOCLAW_OPENSHELL_INTEGRATION.md` | F02 "sandbox leg NOT YET PROVEN" updated to "RESOLVED" |
| `docs/architecture/SOP_ENGINE_V2_DESIGN.md` | Sandbox boundary header updated to reflect qualification |
| `docs/architecture/PACKAGE_OWNERSHIP.md` | maiw-contracts owns domain value objects (not ActionProposal/governance) |
| `docs/architecture/PACKAGE_OWNERSHIP.md` | maiw-decision owns ActionProposal, DecisionResult, ApprovalRecord |

### Static scan results

| Pattern | Hits | Action |
|---------|------|--------|
| `Llama\|Qwen` in README.md model policy section | 0 | Fixed (removed) |
| `unsupported model` enumeration in README.md | 0 | Fixed |
| `ActionProposal is in maiw-contracts` | 0 | Fixed in all three docs |
| `generate(prompt=` in docs/ | 0 | No action needed |
| `ActionExecutor` in maiw-agents/ pyproject.toml | 0 | No action needed |
| `maiw-execution` in maiw-agents/ | 0 | No action needed |
| `WRITE.*sandbox.*allow` | 0 | No action needed |
| `ALLOW_UNAUTHENTICATED=true` in committed config | 0 actual | PASS |

---

## Secret Scan

No actual secrets found in `docs/`, `artifacts/`, `scripts/`. Pattern matches were all substrings in normal content (e.g., `task-`, `case_id`, `wave17-risk`). One RUNBOOK doc references `MAIW_INFERENCE_ALLOW_UNAUTHENTICATED=true` in a **DO NOT DO** instruction context — not a committed secret.

**Secret scan: PASS (0 actual secrets).**

---

## Artifact Audit

| Artifact | Status | Key field |
|---------|--------|-----------|
| `artifacts/nemoclaw/phase20b/security_qualification.json` | EXISTS | `verdict: FULL_END_TO_END_QUALIFIED` |
| `artifacts/nemoclaw/phase20c/live_sandbox_qualification.json` | EXISTS | `verdict: LIVE_SANDBOX_QUALIFIED` |
| `artifacts/deployment/reference_deployment_qualification.json` | EXISTS | Operationalization complete |
| `artifacts/ux/ux1g_final_persona_acceptance.json` | EXISTS | `verdict: MAIW UX-1G FINAL PERSONA ACCEPTANCE COMPLETE` |
| `artifacts/release/maiw_v2_release_gate.json` | UPDATED | `final_verdict: RELEASE READY` |
| `RELEASE_NOTES.md` | EXISTS | Full v2 release notes (corrected package ownership) |

---

## Known Limitations (Platform, non-defects)

1. **Single-node reference deployment (not HA).** No multi-replica coordination or HA persistence.
2. **Qualified on epg-tme-smc-h100-02 and reference environment.** H100 NVL, sm_90a, NemoClaw 0.0.124, OpenShell 0.0.116.
3. **real_sandbox tests skip on non-qualification hosts.** Expected behavior.
4. **Pre-existing ESLint warnings.** 1041 non-blocking warnings; 0 errors.
5. **Semantic Release skips on PR branches.** Expected CI behavior.

---

## P0 Findings

None.

---

## P1 Findings

None. (P1-01 resolved — see singleton defect fix in Test Results section above.)

---

## Singleton Defect Resolution (was P1-01)

**Root cause identified and fixed.** `tests/unit/reliability/test_ambiguous_write.py` had a hardcoded `sys.path.insert(0, "/home/nvidia/Multi-Agent-Intelligent-Warehouse")` in the `TestProviderFaultInjection._make_world()` method. This inserted the main checkout root into sys.path, shadowing the worktree's `src/` with the main checkout's `src/`, which does NOT contain `src/api/routers/inference.py`. After `test_model_gateway.py` cached the `src` module from the wrong path, subsequent attempts by `TestInferenceHTTPContract` and `TestAuthFailClosed` to `from src.api.routers.inference import router` failed with `ModuleNotFoundError`.

**Fix:** Removed the unnecessary `sys.path.insert` call. `maiw_api` is importable from the venv without it.

**Belt-and-suspenders:** Added module-level autouse `_reset_gateway_singleton` fixture to `test_phase_20c_approved_nemotron.py` to isolate ModelGateway singleton across test modules regardless of run order.

**Result:** Full combined suite now passes: 2667 passed, 0 failed.

---

## Final Verdict

```
MAIW V2 RELEASE GATE PASSED — RELEASE READY
```

**P0: 0. P1: 0.** All qualification artifacts present and verified. All invariants hold. README model-language PASS. Package ownership corrected throughout. Singleton ordering defect resolved. Proposed version: `v2.0.0`. Do NOT apply the tag or merge the PR until human review confirms.
