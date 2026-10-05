# UX-1G: Final Persona Acceptance Audit

**Build SHA:** `1c8606a` (nvidia/main at acceptance time)
**Acceptance date:** 2026-10-05
**Branch:** `feat/ux-1g-final-persona-acceptance`
**Test environment:** Unit tests (JSDOM), static analysis against qualification artifact

---

## Source Identity Verification

| Item | Status | Notes |
|------|--------|-------|
| PR #136 content (scripts/, REFERENCE_DEPLOYMENT_RUNBOOK.md, JsonFileGovernanceInbox) | PRESENT | 1c8606a |
| FULL_END_TO_END_QUALIFIED artifact (Phase 20B) | PRESENT | artifacts/deployment/phase20b/ |
| live_sandbox_qualification.json (Phase 20C) | PRESENT | artifacts/deployment/phase20c/ |
| UX-1A–1F changes | PRESENT | Layout, AuthorityBoundary, DeveloperJourney, etc. |
| Developer Journey (DeveloperJourneyRail, DeveloperJourneyPanel) | PRESENT | 7-stage rail |
| Governance/execution/outcome views | PRESENT | ApproveStage, ExecutionOutcomeBadge, OutcomeSummary |

Source identity: **VERIFIED**

---

## Three Acceptance Personas

### Persona A — Warehouse Operator
Questions answered by the UI:
- What is happening? → OPERATIONS page (DemoShell) with SSE-driven live stage rail
- What is at risk? → RiskBadge, severity indicators in ApprovalCard
- What is AI recommending? → "AI Recommendation" stage (OPERATOR_LABELS.recommendation_ready)
- Why? → "Why (rationale)" block in ApprovalCard, WhyPanel in ExpertOverlay
- Does this require my approval? → "HUMAN APPROVAL REQUIRED" header, pre-execution notice
- Has anything actually executed? → PRE_EXECUTION_NOTICE shown until execution state confirmed
- Is execution confirmed? → ExecutionOutcomeBadge (EXECUTED/UNKNOWN/CONFIRMED_EXECUTED)
- What happened operationally afterward? → OutcomeSummary (OUTCOME stage)
- Is the system uncertain? → UNKNOWN/INDETERMINATE/RECONCILING shown distinctly
- What should I do next? → CTA per stage; escalation state shows recommended action

### Persona B — Developer/Solution Architect
Full chain inspectable via DeveloperJourney tab in ExpertOverlay:
- OperationalContextSnapshot → WorldContextSnapshot (CONTEXT stage)
- AgentTask → CopilotAgentStatus, DeveloperJourneyPanel AGENT stage
- SOP step/progression → AgentTaskView (sop_id, sop_version, current_step, step_status)
- ModelGateway route → MODEL stage: model_id, generation, approved_family_status, routing_rule, latency
- Selected approved model → ApprovedFamilyBadge (NEW in UX-1G)
- StepResult/evidence → DECISION stage; ExecutionReliabilityPanel
- Governance → APPROVE stage (ApproveStage); WAITING_FOR_GOVERNANCE label
- ActionExecutor → EXECUTION stage; authority boundary in AuthorityBoundary
- Final outcome → OUTCOME stage (OutcomeSummary)
- Trace correlation → trace_id in DeveloperTraceView; JOURNEY cross-links by ID

### Persona C — Platform/Security Engineer
Reachable via DEPLOYMENT nav link → /deployment (new DeploymentSecurity page):
- Runtime identity and SHA
- Version matrix (MAIW, NemoClaw, OpenShell, approved model)
- Sandbox status and capability policy (WRITE DENIED visually)
- Approved model family policy (Nemotron 3/3.5 APPROVED; Llama REJECTED)
- Network boundary (sandbox → gateway: allowed; sandbox → direct provider: denied)
- Auth state (fail-closed; unauthenticated override: disabled in reference)
- Persistence status (ProcedureStateStore + GovernanceInbox)
- Deployment readiness (READY/DEGRADED/NOT READY from runtime status)
- Qualification scope clearly stated as "qualified reference deployment" not HA production

---

## Acceptance Principles Audit

| Principle | Status | Evidence |
|-----------|--------|---------|
| Recommended ≠ Approved | PASS | OPERATOR_LABELS.recommendation_ready ≠ approved |
| Approved ≠ Executed | PASS | DECISION_STATUS_LABEL['approved'] = 'Approved' (not 'Executed') |
| Executed ≠ Execution confirmed | PASS | ExecutionOutcomeBadge: EXECUTED ≠ CONFIRMED_EXECUTED |
| Execution confirmed ≠ Operational outcome | PASS | OUTCOME stage separate from EXECUTION stage |
| Procedure completion separate | PASS | OUTCOME stage shows terminal procedure state |
| Agent claim ≠ Step completion | PASS | Validator verdict shown separately from StepResult |
| Model claim ≠ Validator verdict | PASS | DECISION stage separates these |
| Sandbox isolation ≠ Governance approval | PASS | DeploymentSecurity note; ux1g.test.tsx C-1.2 |
| Model availability ≠ Model eligibility | PASS | ApprovedFamilyBadge; ux1g.test.tsx B-2.5 |

---

## Defects Found and Fixed

### P1 — MODEL panel missing approved-family status (Steps 20, 31)
- **Finding:** DeveloperJourneyPanel MODEL stage showed model_id and routing_rule but no approved-family status or model generation. Developer could not verify Nemotron 3 vs legacy Llama without external lookup.
- **Fix:** Added `ApprovedFamilyBadge` component to MODEL panel. Shows "APPROVED FAMILY" (Nemotron 3/3.5) or "UNAPPROVED FAMILY" (Llama, etc.) with aria-label. Added `model_generation` field row.
- **Files:** `DeveloperJourneyPanel.tsx`, `journeyIdentity.ts`

### P1 — Legacy Llama model ID in ux1e test fixtures (Step 38)
- **Finding:** `ux1e.test.tsx` used `model_id: 'meta/llama3-70b-instruct'` throughout. MAIW v2 uses Nemotron 3 exclusively; legacy Llama must never appear as production selection.
- **Fix:** Updated all fixtures to `nvidia/nemotron-3-super-120b-a12b` + added `model_approved_family: 'approved'` and `model_generation: 'Nemotron 3'`.
- **Files:** `ux1e.test.tsx`

### P1 — No Platform/Security deployment surface (Steps 27–35)
- **Finding:** No dedicated page for Platform/Security persona. SystemHealth showed component availability but not: sandbox capability policy, approved model policy, network boundary, auth state, qualification scope.
- **Fix:** Created `DeploymentSecurity.tsx` page at `/deployment` route with all required Platform/Security fields. Added "DEPLOYMENT" to nav bar.
- **Files:** `DeploymentSecurity.tsx`, `App.tsx`, `Layout.tsx`

### Minor — ExecutionOutcomeBadge reconciliation descriptions not shown (Step 8)
- **Finding:** INDETERMINATE and CONFIRMED_NOT_EXECUTED reconciliation states showed label only, no description text. Operator couldn't see "manual review required" or "safe to retry" without tooltip.
- **Fix:** Added `desc` text rendering for non-compact reconciliation badge states.
- **Files:** `ExecutionOutcomeBadge.tsx`

---

## Scenario Walkthroughs

### Operator Scenario A — Wave Risk (Step 11)
**UI path:** OPERATIONS → Copilot → scenario active → ANALYZE stage → APPROVE stage → EXECUTE stage → OUTCOME stage
- Context → risk detected: visible in RiskBadge (HIGH) on ApprovalCard
- Agent/SOP reasoning: AGENT stage in ExpertOverlay JOURNEY tab
- Recommendation: `recommendation_ready` label — never "Applied"
- WAITING_FOR_GOVERNANCE: shown before any approval button is clicked
- Approval: "HUMAN APPROVAL REQUIRED" + "No warehouse action has executed yet"
- Execution: SSE-driven rail advances; PRE_EXECUTION_NOTICE removed after execution
- Authoritative reread → state predicate → outcome: OUTCOME stage with OutcomeSummary
**Result: PASS**

### Operator Scenario B — Equipment Failure (Step 12)
**UI path:** Equipment failure → ApprovalCard shows write → execution badge after
- Write executed ≠ equipment recovered: ExecutionOutcomeBadge shows EXECUTED (write occurred), OUTCOME stage shows actual equipment state from reread
- "Mutation confirmed" ≠ procedure completed: OUTCOME stage is separate
**Result: PASS (architecture verified; ExpertOverlay surfaces this)**

### Operator Scenario C — Inventory/Picking Loop (Step 13)
**UI path:** SOP C progress → loop attempt/max → escalation if exhausted
- AgentTaskView exposes: current_step, loop_attempt, max_iterations, strategy
- SOPProgress component shows step chain progression
**Result: PASS**

---

## Checklist Results

### Operator Checklist (10 items)
1. What is happening: PASS (OPERATIONS rail, SSE-driven)
2. What AI recommends: PASS (OPERATOR_LABELS.recommendation_ready = 'AI Recommendation')
3. Why: PASS (rationale block in ApprovalCard)
4. Approval required: PASS (HUMAN_APPROVAL_REQUIRED label + PRE_EXECUTION_NOTICE)
5. Approved/rejected: PASS (APPROVED / REJECTED result badges)
6. Execution occurred: PASS (EXECUTION stage; EXECUTED badge after ActionExecutor)
7. Execution confirmed: PASS (CONFIRMED_EXECUTED in reconciliation)
8. Operational outcome: PASS (OUTCOME stage separate from EXECUTION)
9. Uncertainty visible: PASS (UNKNOWN badge shows warning text; RECONCILING visible)
10. Human action required: PASS (WAITING_FOR_GOVERNANCE; escalation state)

**Score: 10/10 PASS**

### Developer Checklist (15 items)
1. Context snapshot: PASS (snapshot_id, warehouse_id in CONTEXT panel)
2. Agent/runtime: PASS (agent_id, runtime in AGENT panel)
3. SOP/version/step: PASS (sop_id, sop_version, current_step in AGENT panel)
4. Model route: PASS (model_id, routing_rule, routing_reason in MODEL panel)
5. Approved model generation: PASS (ApprovedFamilyBadge + model_generation NEW)
6. Capability calls: PASS (SKILLS panel — skills_used only)
7. StepResult: PASS (ExecutionReliabilityPanel)
8. Evidence: PASS (facts_observed in ApprovalCard; evidence in DECISION panel)
9. Validator verdict: PASS (DECISION stage — validator result distinct from model output)
10. Governance: PASS (APPROVE stage; decision_id, proposal_id)
11. Execution: PASS (EXECUTION stage; execution_id, mutation_state)
12. Reconciliation: PASS (ExecutionOutcomeBadge + ReconciliationStatus)
13. Outcome: PASS (OUTCOME stage; authoritative reread result)
14. Trace correlation: PASS (trace_id in JOURNEY cross-links; DeveloperTraceView)
15. Authoritative identification: PASS (ArtifactIdentity chain — all IDs present)

**Score: 15/15 PASS**

### Platform/Security Checklist (12 items)
1. Deployed versions: PASS (version matrix in DeploymentSecurity)
2. Current approved model: PASS (model_id in DeploymentSecurity)
3. Model generation verification: PASS (generation label = "Nemotron 3")
4. Sandbox status: PASS (OpenShell runtime, capability policy)
5. Capability policy: PASS (READ/ANALYTICAL/PROPOSAL allowed; WRITE/EMERGENCY_WRITE denied)
6. WRITE denied: PASS (CapabilityRow with DeniedIcon)
7. Inference auth enabled: PASS (auth fail-closed = true shown)
8. Direct provider access denied: PASS (network boundary: sandbox→provider = denied)
9. Persistence health: PASS (ProcedureStateStore + GovernanceInbox status)
10. Deployment readiness: PASS (READY/DEGRADED/NOT READY from runtime status)
11. Sandbox isolation ≠ governance: PASS (note shown in DeploymentSecurity)
12. Qualification scope/limitations: PASS ("qualified reference deployment — not HA")

**Score: 12/12 PASS**

---

## Remaining Limitations

1. DeploymentSecurity page reads static qualification constants (not live backend policy endpoint). The qualification artifact is accurate for the reference deployment but cannot reflect runtime policy changes without a new backend endpoint. Acceptable for reference deployment scope.

2. Reconciliation desc text is hidden in compact mode (by design — compact badges are used in tables where space is constrained). Full mode shows all descriptions.

3. ApprovedFamilyBadge falls back to model_id string matching when `model_approved_family` field is not set by the backend. This heuristic is correct for known model IDs but a backend-side approved_family field is preferable long-term.

4. E2E framework not present in repo — persona flows tested via unit/component tests only.

---

## Test Results

| Suite | Before | After | Delta |
|-------|--------|-------|-------|
| UI unit/component | 937 | 963 | +26 (new UX-1G tests) |
| Test suites | 37 | 39 | +2 (ux1g.test.tsx + ux1e TC-6) |
| Failures | 0 | 0 | 0 |

---

## Final Verdict

`MAIW UX-1G FINAL PERSONA ACCEPTANCE COMPLETE`

All 40 explicit acceptance questions answered. All three persona checklists pass (10/10, 15/15, 12/12). Zero new test failures (963 passing). All P0 and P1 UX issues fixed.

The release gate is: **MAIW v2 UX READY FOR REVIEW** (pending human review of this PR before final freeze).
