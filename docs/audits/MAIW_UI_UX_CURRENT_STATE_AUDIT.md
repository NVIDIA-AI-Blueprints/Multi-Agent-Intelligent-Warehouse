# MAIW UI/UX Current State Audit — UX-0 Baseline

**Audit type**: Code-inspection-based (React source + API routers)  
**Audit date**: 2026-09-20  
**Branch**: feat/ux-0-current-state-audit  
**HEAD SHA**: cd741bb  
**Auditor method**: Full source inspection of all React components, API router endpoints, GLOSSARY.md, and design constants. No CSS/layout/styling changes. No UX fixes (P0 P1 P2 P3 all documented only).

---

## 1. Executive Summary

MAIW v2 has a well-structured agentic pipeline and a rich multi-surface UI. The core operator journey — scenario → observe → analyze → propose → decide → approve → execute → outcome — is functionally complete and architecturally sound. However, the audit reveals four systemic UX problems that risk trust, safety, and comprehension:

1. **Authority boundary is architecturally enforced but visually invisible.** The operator cannot tell from the UI that MAIW has NOT executed anything until the approval step. The "APPROVE & EXECUTE" button label in ApproveStage conflates governance (approval) with execution (ActionExecutor), which are architecturally distinct in MAIW v2.

2. **Developer detail is mixed into the operator view without gating.** Model IDs, routing rules, proposal IDs, snapshot IDs, and trace IDs appear in the primary lifecycle stages by default. The Expert overlay toggle exists but the stages beneath it leak developer-level content to all users.

3. **The primary operator screen is not in the global navigation.** The default landing route `/demo` (DemoShell) is absent from the global nav bar. The global nav's primary item "COMMAND" leads to a different and older CommandCenter page, which also labels itself "MAIW COMMAND CENTER". Two pages share the same name for different purposes.

4. **Terminology is inconsistent between the GLOSSARY and the UI.** The most critical inconsistency: `CommandCenter.tsx` maps the decision outcome `'approved'` to the display label `'EXECUTED'`, incorrectly suggesting execution whenever the DecisionEngine approves a proposal — regardless of whether `ActionExecutor` ran.

No P0 build blockers were found. The application is architecturally healthy. All findings are P1–P3 and require no changes to architecture, SOPs, runtime, governance, or ModelGateway.

---

## 2. Build Identity

| Field | Value |
|-------|-------|
| Branch | feat/ux-0-current-state-audit |
| Base SHA | cd741bb |
| Base PRs | #103 (docs consistency), #104 (legacy file audit) |
| React version | 18.x (from package.json) |
| MUI version | 5.x |
| API framework | FastAPI (maiw_api) |
| Backend port | 8000 |
| Frontend port | 3000 (npm run dev) |
| Demo mode | MAIW_DEMO_MODE=true (env-gated) |
| Node version | System default |
| Audit method | Source code inspection (no live browser screenshots) |

---

## 3. Audit Method

This audit is **code-inspection-based**. Browser automation was not required because the source code provides a complete and reliable basis for understanding:

- Navigation structure: `src/ui/web/src/App.tsx` (routes), `src/ui/web/src/components/Layout.tsx` (nav)
- All screen contents: individual page and component `.tsx` files
- API data dependencies: `apps/api/maiw_api/routers/*.py`
- Canonical terminology: `docs/GLOSSARY.md`
- Color semantics: hardcoded hex constants in component files

All 19 primary screens and ~17 embedded sub-surfaces were inspected. API router endpoints were read to understand data dependencies.

---

## 4. Personas

Three personas guide this audit:

**Operator (OPR)**: Warehouse supervisor making real-time operational decisions. Non-technical. Needs plain-language operational answers: "What is at risk? What should I do? Did it work?"

**Developer (DEV)**: NVIDIA or partner engineer verifying the pipeline. Technical. Needs full trace: snapshot_id → agent → SOP → runtime → model route → skill → proposal_id → decision_id → approval_id → execution_id → reconciliation_outcome.

**GSI / Solution Architect (GSI)**: Systems integrator deploying MAIW at a real warehouse. Needs to understand what to connect (MCP endpoints), what to configure (SOPs, agents, governance), and what can be replaced or customized.

---

## 5. Navigation Inventory

### Global Nav (Layout.tsx)
```
COMMAND → /command
STATE   → /state
DECISIONS → /decisions
MODELS  → /models
WORLD   → /world
CAPABILITIES → /capabilities
ACTIVITY → /activity
```

**Critical finding**: Default route `/` redirects to `/demo` (DemoShell), which is the primary operator screen and the canonical Wave 17 demo entry point. This route is NOT in the global nav. An operator who opens the URL and is then navigated away via the global nav may never find their way back.

### All Routes (from App.tsx)

23 routes total. See `docs/audits/uiux/MAIW_UI_UX_SCREEN_INVENTORY.md` for full inventory.

---

## 6. Screen Inventory

19 primary screens audited. See `docs/audits/uiux/MAIW_UI_UX_SCREEN_INVENTORY.md` for the complete table.

**Primary operator screens**: DemoShell (/demo) with embedded LifecycleRail, CopilotDrawer, WorldShell, ReliabilityPanel.

**Primary developer screens**: ExpertOverlay (within DemoShell), ModelGatewayLab (/models/lab), WorldShell CONTEXT/RAW tabs, ActivityFeed (/activity).

**GSI screens**: CapabilityPlane (/capabilities), ModelGateway (/models), Documentation.

**Legacy screens (not MAIW v2 core)**: /chat, /equipment, /operations, /safety, /forecasting, /analytics, /documents, Dashboard.

---

## 7. Canonical Scenario (Wave 17)

The canonical Wave 17 disruption scenario maps to the following UI surfaces:

| Step | Description | UI Surface | Status |
|------|-------------|-----------|--------|
| 1 | Warehouse state visible | DemoShell → ScenarioSelector → WorldGrid / OperationalContextStrip | PRESENT |
| 2 | Scenario applied | ScenarioSelector → POST /api/v1/demo/scenario/{name}/start | PRESENT |
| 3 | Wave 17 at risk | OperationalContextStrip → wave_risk_level badge | PARTIAL — badge present but not linked to specific wave |
| 4 | Operator asks "Why is Wave 17 at risk?" | CopilotDrawer → ASK intent → POST /api/v1/copilot/turn | PRESENT |
| 5 | Evidence-grounded answer | CopilotDrawer → facts_observed, severity, citations | PRESENT |
| 6 | Context at Decision Time | CopilotDrawer → VIEW CONTEXT AT DECISION TIME → WorldShell CONTEXT tab | PRESENT |
| 7 | SOP-driven agent task | REASON stage → assessment.summary | PARTIAL — SOP not named in UI |
| 8 | Labor specialist delegation | NONE | MISSING — subagent delegation not visualized |
| 9 | Recommendation generated | PROPOSE stage → ProposalCard | PRESENT |
| 10 | WAITING_FOR_GOVERNANCE | APPROVE stage → "HUMAN APPROVAL REQUIRED" hero | PRESENT |
| 11 | DecisionEngine evaluates | DECIDE stage → outcome, violations | PRESENT |
| 12 | Human reviews and approves | ApproveStage → APPROVE & EXECUTE button | PRESENT (with P1 label issue) |
| 13 | ActionExecutor executes | EXECUTE stage → execution_id, outcome | PRESENT |
| 14 | LIVE World changes | WorldShell → LIVE view → WorldLive execution record | PRESENT |
| 15 | Outcome measured | OUTCOME stage → pre/post KPI delta | PRESENT |
| 16 | Full trace reconstructable | ExpertOverlay → TRACE tab | PARTIAL — SOP steps and subagent chain missing |

---

## 8. Operator Journey

See `docs/audits/uiux/MAIW_UI_UX_JOURNEY_MAPS.md` — Journey A.

**Summary scores**:

| Operator Question | Score |
|------------------|-------|
| What is happening? | PARTIAL — KPI numbers present but not narrated |
| What is at risk and why? | PARTIAL — wave_risk_level badge present, but reason requires Copilot ASK |
| What should I do? | CLEAR — proposal card with rationale and facts |
| What exactly am I approving? | PARTIAL — action, objective, rationale, facts shown; authority boundary not explicit |
| Did it work? | PARTIAL — CONFIRMED_EXECUTED present; INDETERMINATE outcome has no guidance |

---

## 9. Developer Journey

See `docs/audits/uiux/MAIW_UI_UX_JOURNEY_MAPS.md` — Journey B.

**Summary scores**:

| Pipeline Link | Visibility |
|--------------|-----------|
| OperationalContextSnapshot | VISIBLE |
| Agent | VISIBLE (type only) |
| SOP | MISSING |
| Runtime | PARTIALLY VISIBLE |
| Model route | VISIBLE |
| Skills | PARTIALLY VISIBLE |
| Subagents | MISSING |
| RecommendedAction | VISIBLE |
| ActionProposal | VISIBLE |
| Decision | VISIBLE |
| Approval | VISIBLE |
| Execution | VISIBLE |
| MCP | PARTIALLY VISIBLE |
| LIVE state | VISIBLE |
| Outcome | VISIBLE |
| trace_id correlation | VISIBLE |

---

## 10. GSI Journey

See `docs/audits/uiux/MAIW_UI_UX_JOURNEY_MAPS.md` — Journey C.

**Summary scores**:

| GSI Question | Score |
|-------------|-------|
| Where to connect WMS/WES | REQUIRES CODE READING |
| SOP definition/management | ABSENT |
| Agent objectives | REQUIRES CODE READING |
| Runtime selection | REQUIRES CODE READING |
| Model routing policy | CLEAR |
| Governance rules | REQUIRES CODE READING |
| Extension boundary | ABSENT |
| MCP capabilities | CLEAR |

---

## 11. Authority Boundary

**This is the highest-priority finding category.**

The MAIW Authority Boundary (from GLOSSARY.md):
```
Agents → RecommendedAction → GovernedActionOrchestrator
─────────────── MAIW AUTHORITY BOUNDARY ────────────────
ActionProposal → DecisionEngine → Human Approval → ActionExecutor → MCP → LIVE
```

### Finding AB-1 [P1]: "APPROVE & EXECUTE" button label

**File**: `src/ui/web/src/components/demo/stages/ApproveStage.tsx` line 312

The primary operator action button is labeled "APPROVE & EXECUTE". This label merges two architecturally distinct concepts:
- **APPROVE**: The human governance act — operator grants authority for execution
- **EXECUTE**: The ActionExecutor invocation — system executes the approved proposal via MCP

MAIW v2 explicitly distinguishes these. An approved proposal with no wired executor returns "approved_no_executor" — meaning approval happened but execution did not. The button label cannot represent both states accurately.

**Risk**: Operator may believe they have explicitly triggered both the governance decision AND the operational change in one act, reducing their understanding of the two-phase model.

### Finding AB-2 [P1]: STATUS_LABEL['approved'] = 'EXECUTED'

**File**: `src/ui/web/src/pages/CommandCenter.tsx` lines 109–115

```typescript
const STATUS_LABEL: Record<string, string> = {
  approved: 'EXECUTED',
  rejected: 'REJECTED',
  requires_human_approval: 'APPROVAL',
  ...
};
```

A decision outcome of `'approved'` is displayed as `'EXECUTED'`. These are distinct states in MAIW v2:
- `approved`: DecisionEngine returned APPROVED (policy check passed)
- `executed`: ActionExecutor successfully ran and produced an execution record

An approved proposal may NOT be executed (if no executor is wired, if execution fails, or if the demo route returns `approved_no_executor`). Displaying "EXECUTED" for any "approved" outcome is **factually incorrect** for these cases.

**Risk**: Operator believes execution occurred when only governance approval was granted.

### Finding AB-3 [P1]: No persistent pre-approval "nothing executed" indicator

The stages OBSERVE, REASON, and PROPOSE do not display any persistent indicator that MAIW has not yet executed any warehouse changes. The authority boundary only becomes visible when the APPROVE stage is reached (if a human approval is required). For LOW-risk proposals that are auto-approved and executed without human involvement, there is no operator-facing indication that execution is about to happen — the pipeline moves from PROPOSE directly to EXECUTE stage via SSE events.

**Risk**: Operator does not know that a pipeline run without human approval can change warehouse state automatically.

### Finding AB-4 [P2]: Two approval UIs for the same action

`CommandCenter.tsx` (route `/command`) has inline "APPROVE / REJECT" buttons in the right sidebar Decision Center panel. `ApproveStage.tsx` (within `DemoShell` at `/demo`) has a full-screen `ApprovalCard` with rationale and facts. Both call the same `demoAPI.approvePending()` endpoint but provide dramatically different amounts of context. The operator can approve actions with far less information from the CommandCenter than from the DemoShell.

---

## 12. Recommendation UX

**Location**: `src/ui/web/src/components/demo/stages/ProposeStage.tsx`

ProposeStage renders `ProposalCard` components with: action, capability, target, risk_level badge, rationale, proposal_id. "WHY THIS RECOMMENDATION?" button links to DecisionExplanationDrawer (for explanation).

**Current strengths**: ProposalCard shows rationale and facts. Risk badge is visually clear. "WHY THIS RECOMMENDATION?" CTA present.

**Issues**:
- "Capability" field value is a machine-readable string (`warehouse.labor.allocate`) with no human-readable expansion
- Proposal ID shown by default — this is developer-level detail (Level 3)
- Footer text "No projected impact numbers — actuals captured post-execution in Outcome" is a developer-facing implementation note visible to all users (P2)

---

## 13. Governance / Approval UX

**Location**: `src/ui/web/src/components/demo/stages/ApproveStage.tsx`

ApproveStage renders full ApprovalCard with: proposed action, objective, rationale, facts supporting the decision, state validity (freshness tag, proposal_id, decision_id), REJECT and APPROVE & EXECUTE buttons.

**Current strengths**: Facts section, rationale section, state freshness tag, and dual REJECT/APPROVE buttons are all present. The card header "HUMAN APPROVAL REQUIRED" is large and clear.

**Issues**:
- "APPROVE & EXECUTE" button label (see AB-1 above) — P1
- "05 APPROVE" stage label uses a numeric prefix that is not used elsewhere in the UI
- ApprovalCard has no visual element that says "MAIW has not changed anything yet" — the boundary must be inferred from the stage position
- TTL expiry message ("Approval TTL elapsed — operator must resubmit") requires operator knowledge of the concept of TTL — P2

---

## 14. Execution UX

**Location**: `src/ui/web/src/components/demo/stages/ExecuteStage.tsx`

ExecuteStage shows: execution_id, success boolean, outcome_label (CONFIRMED_EXECUTED / CONFIRMED_NOT_EXECUTED / INDETERMINATE).

**Issues**:
- INDETERMINATE outcome shows the label but has no operator guidance ("What do I do next?") — P2
- execution_id is always visible (developer-level) — P2
- No loading state shown during execution (between approval and result) — P2

---

## 15. Reliability UX

**Locations**: `src/ui/web/src/components/demo/reliability/ReliabilityPanel.tsx` and `src/ui/web/src/components/reliability/ReliabilityPanel.tsx`

**Dual implementation issue**: Two separate `ReliabilityPanel` components exist. The `demo/reliability` version is used in DemoShell reliability mode; the plain `reliability` version is used in CommandCenter. They have similar but not identical implementations.

**Finding**: DemoShell has a dedicated "reliability" mode tab with fault injection, reconciliation status, and safety scorecard. This mode is separate from the lifecycle stages and has no cross-linking.

---

## 16. Outcome UX

**Location**: `src/ui/web/src/components/demo/stages/OutcomeStage.tsx`

OutcomeStage shows pre/post KPI delta and reconciliation status.

**Issues**:
- Numeric KPI delta shown without narrative ("labor availability went from 72% to 85%") — operator must interpret numbers — P2
- No direct link to "View what changed in the warehouse" (World LIVE tab) from the Outcome stage — P2

---

## 17. World UX

**Location**: `src/ui/web/src/components/world/WorldShell.tsx` + subtabs

WorldShell has 5 tabs (OVERVIEW, GRAPH, CHANGES, CONTEXT, RAW) and 3 world views (BASE, SCENARIO, LIVE).

**BASE/SCENARIO/LIVE semantics**:
- BASE = immutable WarehouseDataPack (never changes after generation)
- SCENARIO = BASE + scenario overlay
- LIVE = SCENARIO + runtime mutations from executed actions

All three are named correctly per GLOSSARY. The switcher is present.

**Issues**:
- The OVERVIEW tab shows different content when worldView=live (WorldLive component) vs. worldView=base/scenario (WorldOverview component) — behavior change without clear indication — P2
- The CONTEXT tab says "No context snapshot selected. Open the Copilot and click VIEW CONTEXT AT DECISION TIME" — this is correct but the cross-surface instruction may confuse operators in the standalone `/world` page (where Copilot is not available) — P2
- RAW tab shows raw JSON — developer-only content with no gating — P2

---

## 18. Operational Graph UX

**Location**: `src/ui/web/src/components/world/OperationalGraph.tsx`, `WorldGraph.tsx`, `NodeInspector.tsx`

The Graph tab (WorldGraph) shows entity relationships with node inspector for drilling into individual entities. Can receive `focusContext` from CopilotDrawer to highlight a specific entity.

**Strengths**: Deep link from Copilot answer to graph node is architecturally present (Phase 17E).

**Issues**:
- Graph is developer/technical surface with no operator-level explanation of what the nodes and edges mean — P2
- No legend for node colors/shapes — P2
- Focus context from Copilot does arrive and switch to GRAPH tab automatically — P3 (works, but no visual confirmation)

---

## 19. Context Snapshot UX

**Location**: `src/ui/web/src/components/world/WorldContextSnapshot.tsx`

Accessible from Copilot "VIEW CONTEXT AT DECISION TIME" → World CONTEXT tab. Shows the OperationalContextSnapshot from a specific turn.

**Strengths**: Historical context preserved and viewable. "View Decision Trace" link back to developer trace.

**Issues**:
- Context tab empty state message instructs user to use Copilot — unavailable on standalone `/world` page — P2
- The relationship between "context at decision time" and the canonical OperationalContextSnapshot concept is not explained — P2

---

## 20. Agent/SOP UX

**No dedicated surface exists.**

The REASON stage shows that an agent ran (implicitly — the assessment summary is the agent output) and shows the model_id and routing_rule. However:
- The agent's name, domain, and objective are not displayed
- The SOP that was executed is not named
- SOP step sequence is not shown
- This is a MISSING surface for both operator (GSI) and developer

**Finding**: SOP visibility is MISSING from all screens — P1 (developer journey gap).

---

## 21. Delegation UX

**No dedicated surface exists.**

MAIW v2 supports agent delegation to subagents via SOPDefinition. The architecture supports labor specialist → wave specialist delegation, but this delegation chain is:
- Not reflected in any UI stage or panel
- Not visible in the developer trace (ExpertOverlay TRACE tab shows model calls, not subagent invocation chain)

**Finding**: Subagent delegation is MISSING from all screens — P1 (developer journey gap).

---

## 22. Runtime UX

**Location**: ExpertOverlay → RUNTIME tab

The RUNTIME tab shows: maiw_operational_status, model_gateway, operations_agent_available, equipment/labor/wave executors, MCP domain availability, runtime type (Deterministic vs DeepAgents).

**Strengths**: Runtime health visible. MCP domain availability per port visible.

**Issues**:
- Runtime tab requires Expert mode ON — not accessible to operators or GSIs without enabling Expert — appropriate for level 3, but GSI may need this
- No UI surface to switch runtime (Deterministic vs DeepAgents) — configuration-only — P3 (not a UI issue, just a note)

---

## 23. ModelGateway UX

**Location**: `src/ui/web/src/pages/ModelGateway.tsx`

ModelGateway page shows: model policy overview, model role tier (Lightning/Nano/Super/Ultra), deployment mode, enabled status.

**Strengths**: Model policy visible. Deployment mode clear.

---

## 24. Model Lab UX

**Location**: `src/ui/web/src/pages/ModelGatewayLab.tsx`

Read-only evaluation artifact inspector for Phase 18C/D/E/F runs. Five sections: Evaluation Input, Router Decision, Model Comparison, Response Inspector, Router Assessment.

**Strengths**: "VIEW ONLY — no live inference, no governance mutations" banner is clear and prominent. Run selector, case selector, methodology badges all present.

**Issues**:
- Route `/models/lab` is not in global nav — requires knowledge of the URL or the back button from `/models` — P3
- Loading error message ("Ensure the API server is running and artifacts exist at artifacts/phase18/") is developer-facing — P3

---

## 25. Decision Graph

**Location**: `src/ui/web/src/components/demo/decision-graph/`

DecisionGraph is a component used within the DecisionExplanationDrawer (accessible via "WHY THIS RECOMMENDATION?" and "WHY IS APPROVAL REQUIRED?" buttons in lifecycle stages). Shows agent → recommendation → proposal → decision nodes.

**Strengths**: Provides visual representation of the decision chain. Semantic zoom implemented.

**Issues**:
- DecisionGraph and DeveloperTraceView cover overlapping territory — both show decision chain — P2 (duplication)
- Graph is technical — shows internal node types not explained to operators — P2

---

## 26. Developer Trace

**Location**: `src/ui/web/src/components/demo/developer-trace/DeveloperTraceView.tsx`

Accessible via ExpertOverlay TRACE tab. Shows: trace_id, timeline of events, performance metrics, artifacts.

**Strengths**: trace_id correlation across all events. Timeline shows sequence. Artifact list for model calls.

**Issues**:
- SOP step sequence not shown — MISSING
- Subagent delegation not shown — MISSING
- Accessible only via Expert toggle — correctly gated — OK

---

## 27. Navigation / State Continuity

**Finding SC-1 [P1]**: Two "MAIW Command Center" pages

- DemoShell (`/demo`) renders `Typography: "MAIW Command Center"` in its top nav
- CommandCenter (`/command`) renders `Typography: "DC-47 — LIVE OPERATIONAL STATE"` in its center and is labeled "COMMAND" in the global nav, but the Layout header says `"MAIW COMMAND CENTER"` for ALL pages
- Both `/demo` and `/command` are accessible. Both contain approval UX. They show different states of the world.

**Finding SC-2 [P1]**: DemoShell not in global nav

Operator landing on `/demo` and navigating to `COMMAND` in the global nav arrives at a different page (`/command`) that also shows pending approvals. The two approval surfaces are not synchronized in real-time — they both query `demoStatus` but the CommandCenter polls on a 3s interval while DemoShell polls via `useDemoStatus` (also polling).

**Finding SC-3 [P2]**: Mode transitions lose stage context

When operator switches from DemoShell `operations` mode to `world` mode and back, the lifecycle stage is preserved (via React state). However, if the operator navigates away via the global nav and returns to `/demo`, the scenario may still be active but the stage UI reinitializes. No URL-level state persistence for stage position.

---

## 28. Information Hierarchy

Information hierarchy analysis per screen:

| Screen | L1 Operational | L2 Evidence | L3 Developer | Mixed? |
|--------|---------------|-------------|--------------|--------|
| OBSERVE stage | WorldGrid (counts), KPI strip | Facts observed | snapshot_id | YES — snapshot_id at L1 |
| REASON stage | Assessment summary, severity | Domains affected | model_id, routing_rule, latency_ms | YES — model_id at L1 |
| PROPOSE stage | Action, rationale | Capability, target | proposal_id, risk_level | PARTIAL — proposal_id at L1 |
| APPROVE stage | Action, objective, rationale, facts | State validity | proposal_id, decision_id | PARTIAL — IDs at L2 (acceptable) |
| EXECUTE stage | Outcome label, success | — | execution_id | YES — execution_id at L1 |
| OUTCOME stage | KPI delta | Reconciliation status | — | OK |
| ExpertOverlay | — | — | Everything | CORRECT — gated |
| CommandCenter | KPI metrics, risks | Decision counts | model_id, agent status | YES — mixed |

---

## 29. Terminology

Terminology inconsistencies found (comparing UI source to GLOSSARY.md):

| UI Label/Value | Location | Canonical Term | Issue |
|---------------|---------|---------------|-------|
| `STATUS_LABEL['approved'] = 'EXECUTED'` | CommandCenter.tsx:109 | approved ≠ executed | P1 — factually wrong conflation |
| "APPROVE & EXECUTE" button | ApproveStage.tsx:312 | APPROVE (then system executes) | P1 — conflates two distinct actions |
| "capability" field in ProposalCard | ProposeStage.tsx | Skill (the skill invoked the proposal) | P2 — Glossary: "Skill" is the capability class; "capability" is its type |
| "SKILL" SSE event / lifecycle phase | CommandCenter.tsx:145 | ProposalSkill invocation within PROPOSE phase | P2 — "SKILL" is a separate SSE event category not a separate pipeline stage |
| "Copilot" button labeled "ASK" | DemoShell.tsx:131-136 | CopilotService handles ASK/ANALYZE/ACT/OBSERVE_OUTCOME | P2 — Only ASK is badged; other intents available |
| "Recommendation" (UI) | Throughout CopilotDrawer | RecommendedAction (GLOSSARY) | P2 — consistent shortening but inconsistent |
| "Facts supporting this decision" | ApproveStage.tsx | facts_observed from assessment | P3 — acceptable paraphrase |
| "State validity" | ApproveStage.tsx | OperationalContextSnapshot freshness | P3 — acceptable paraphrase |

---

## 30. Visual Semantics

Color constants identified across UI source:

| Color | Hex | Semantic Usages |
|-------|-----|----------------|
| Green | #3FB950 | Operational/HEALTHY, available, success, CONFIRMED_EXECUTED, LOW risk, APPROVE button, live SSE dot |
| Red | #F85149 | Critical/error, offline, REJECTED, HIGH/CRITICAL risk, fault events |
| Amber | #D29922 | Warning, PENDING approval, MEDIUM risk, REQUIRES_HUMAN_APPROVAL, AGING state |
| Blue (GitHub) | #58A6FF | Active/selected navigation, COPILOT, BLOCKED decisions, REQUIRES_FRESH_STATE |
| NVIDIA Green | #76B900 | Agent active, model active, MAIW brand, positive (non-status) |
| Dim | #484F58 | Inactive, unavailable, unknown, secondary text |
| Dark blue | #0d2146 | Copilot open background, Expert active background |

**Consistency issue**: `#58A6FF` (blue) is used for:
1. OBSERVE stage header color ("active/current step")  
2. BLOCKED decision status (`requires_fresh_state`)  
3. Copilot button highlight  
4. "View ALL →" navigation links  

These four uses have different meanings (status vs. state vs. action vs. navigation). Blue is semantically overloaded.

---

## 31. Accessibility (Inspection-Based)

| Finding | Severity |
|---------|----------|
| aria-label present on LifecycleRail stage buttons | OK |
| aria-pressed on ModeSwitcher, ExpertToggle, WorldTabSwitcher | OK |
| role="group" on all button groups (ModeSwitcher, WorldTabSwitcher) | OK |
| role="alert" on BackendErrorBanner | OK |
| role="status" on demo-loading spinner | OK |
| No aria-live region for SSE events in LifecycleRail | P2 |
| Approval card has no aria-label identifying the proposal action | P2 |
| "Details ›" link in DemoShell footer has no onClick handler | P2 |
| Color as sole semantic differentiator (SSE event categories use color only) | P2 |
| Focus management when CopilotDrawer opens/closes | Not inspectable from source alone |

---

## 32. Responsive Layout (Inspection-Based)

| Finding | Severity |
|---------|----------|
| Layout has mobile hamburger nav (display: { md: 'none' }) | OK |
| DemoShell top nav uses fixed pixel values, may overflow on small screens | P3 |
| CommandCenter 3-column layout (flex: '0 0 22%', flex: 1, flex: '0 0 26%') not responsive | P3 |
| WorldGrid uses grid-template-columns: repeat(4, 1fr) — may overflow on narrow screens | P3 |

---

## 33. Error / Loading / Empty States

| Surface | Loading | Empty | Error |
|---------|---------|-------|-------|
| DemoShell initial | CircularProgress spinner with "Connecting to demo backend..." | ScenarioSelector | BackendErrorBanner with retry |
| OBSERVE stage pre-analysis | AnalyzeCTA button | N/A | N/A |
| APPROVE stage no pending | "No pending approvals — waiting for backend approval record..." | Same | N/A |
| WorldShell CONTEXT no snapshot | "No context snapshot selected. Open the Copilot..." | Same | N/A |
| ModelGatewayLab | CircularProgress | N/A | Alert with developer error message |
| CopilotDrawer | TerminalTypewriter loading stages | N/A | conversationError state |

**Missing**: Error states for OBSERVE stage when state assembly fails, EXECUTE stage when execution errors, DECIDE stage when violations block execution. These conditions exist in the API (`_raise_typed_http`) but the frontend stage components do not have specific error rendering for these cases.

---

## 34. Performance / Network (Qualitative)

| Finding | Assessment |
|---------|-----------|
| Demo status polling (`useDemoStatus`) | React Query with staleTime — appropriate |
| SSE connection (`useDemoSSE`) | Clean connect/disconnect, heartbeat, reconnect — well-implemented |
| Runtime status polling (`useRuntimeStatus`) | 30s refetch interval — appropriate |
| Equipment/tasks/workforce queries in CommandCenter | 30s staleTime — appropriate |
| ModelGatewayLab loads all runs + model status in parallel | Promise.all — appropriate |
| CopilotDrawer sends HTTP turn then streams response | No streaming UI shown — response appears all at once after TerminalTypewriter |

---

## 35. Trust

Trust is established through:
1. **Facts_observed** grounding in Copilot answers — STRONG
2. **State freshness** indicators in OBSERVE and APPROVE stages — PRESENT but not persistent
3. **Evidence-grounded approval card** with rationale and facts — STRONG
4. **"View Context at Decision Time"** link from Copilot — PRESENT
5. **CONFIRMED_EXECUTED vs. CONFIRMED_NOT_EXECUTED vs. INDETERMINATE** distinction — PRESENT but INDETERMINATE has no follow-up guidance

**Trust gap**: Operator has no way to verify that the `facts_observed` in the assessment are actually from the live warehouse graph vs. model-generated. The architecture guarantees this (snapshot grounding) but the UI does not explain the grounding mechanism.

---

## 36. Persona Fit

| Surface | OPR | DEV | GSI |
|---------|-----|-----|-----|
| DemoShell LifecycleRail | 3/5 | 3/5 | 2/5 |
| CopilotDrawer | 4/5 | 3/5 | 2/5 |
| WorldShell Overview | 3/5 | 3/5 | 3/5 |
| WorldShell Graph | 1/5 | 4/5 | 4/5 |
| WorldShell Context | 1/5 | 5/5 | 3/5 |
| ExpertOverlay Trace | 1/5 | 5/5 | 2/5 |
| ModelGatewayLab | 1/5 | 5/5 | 4/5 |
| CommandCenter | 2/5 | 3/5 | 2/5 |
| CapabilityPlane | 2/5 | 4/5 | 5/5 |
| ActivityFeed | 2/5 | 4/5 | 3/5 |
| ApproveStage | 4/5 | 3/5 | 3/5 |

---

## 37. UX Heatmap

Score 1–5: 1=Poor, 3=Adequate, 5=Excellent

| Surface | Discoverability | Comprehension | Trust | Authority Clarity | Continuity | Feedback | Persona Fit |
|---------|----------------|---------------|-------|-------------------|------------|----------|-------------|
| DemoShell (Observe) | 2 | 3 | 3 | 2 | 3 | 3 | 3 |
| DemoShell (Reason) | 3 | 2 | 3 | 2 | 3 | 3 | 2 |
| DemoShell (Propose) | 3 | 3 | 3 | 3 | 3 | 3 | 3 |
| DemoShell (Approve) | 4 | 4 | 4 | 3 | 3 | 4 | 4 |
| DemoShell (Execute) | 3 | 3 | 3 | 3 | 3 | 2 | 3 |
| DemoShell (Outcome) | 3 | 2 | 3 | 3 | 3 | 2 | 2 |
| CopilotDrawer | 3 | 4 | 4 | 3 | 4 | 4 | 4 |
| WorldShell (Overview) | 3 | 3 | 3 | 3 | 2 | 2 | 3 |
| WorldShell (Context) | 2 | 3 | 4 | 4 | 2 | 2 | 2 |
| ExpertOverlay (Trace) | 2 | 4 | 4 | 4 | 3 | 3 | 2 |
| CommandCenter | 4 | 2 | 2 | 1 | 2 | 3 | 2 |
| ModelGatewayLab | 2 | 4 | 5 | 5 | 3 | 3 | 4 |
| CapabilityPlane | 3 | 4 | 4 | 4 | 3 | 2 | 4 |
| DecisionCenter | 3 | 2 | 2 | 1 | 2 | 2 | 2 |

**Lowest scores**: CommandCenter and DecisionCenter on Authority Clarity (1/5). These pages show decision states without the approval governance context visible in DemoShell.

---

## 38. P0 Findings

**No P0 findings.** The application builds and runs. No authority boundary code defect was found. No functionality is broken in a way that blocks the core journey.

---

## 39. P1 Findings

### P1-01: STATUS_LABEL['approved'] = 'EXECUTED' conflation
**File**: `src/ui/web/src/pages/CommandCenter.tsx` line 109  
**Impact**: Operator believes execution occurred when only DecisionEngine approval was granted. A proposal can be APPROVED without execution (no executor wired, executor fails, demo path returns approved_no_executor).  
**Do not fix in UX-0. Document for UX-1.**

### P1-02: "APPROVE & EXECUTE" button label conflates governance and execution
**File**: `src/ui/web/src/components/demo/stages/ApproveStage.tsx` line 312  
**Impact**: MAIW's authority boundary distinguishes the approval act (human governance) from the execution act (ActionExecutor). The button label presents them as a single human action, reducing operator understanding of the two-phase model.  
**Do not fix in UX-0. Document for UX-1.**

### P1-03: Primary operator screen (/demo) absent from global navigation
**File**: `src/ui/web/src/components/Layout.tsx` (NAV array)  
**Impact**: Operator must know to navigate to `/demo` or trust the root redirect. After navigating away via the global nav, there is no labeled way to return to the primary lifecycle interface. "COMMAND" in the nav leads to a different page.  
**Do not fix in UX-0. Document for UX-1.**

### P1-04: Two pages named "MAIW Command Center" serve different purposes
**Files**: `src/ui/web/src/pages/DemoShell.tsx` (Typography: "MAIW Command Center"), `src/ui/web/src/components/Layout.tsx` (Typography: "MAIW COMMAND CENTER" in global header)  
**Impact**: DemoShell calls itself "MAIW Command Center". The global Layout header says "MAIW COMMAND CENTER" for all pages, including CommandCenter. CommandCenter is the nav item labeled "COMMAND". Three surfaces share one identity.  
**Do not fix in UX-0. Document for UX-1.**

### P1-05: SOP step sequence invisible in all screens
**Impact**: Developer cannot verify which SOP was executed, which step failed, or whether iteration limits were hit. Subagent delegation chain also invisible. Two key developer-journey links (SOP, Subagents) are MISSING from all surfaces.  
**Do not fix in UX-0. Document as missing surface for UX-1.**

### P1-06: No pre-approval "nothing has executed yet" indicator
**Impact**: For auto-approved LOW-risk proposals (no human gate), execution happens without any operator visibility. The lifecycle moves PROPOSE → SSE EXECUTE without stopping at APPROVE. An operator watching the lifecycle has no indication that the system is about to make a warehouse change.  
**Do not fix in UX-0. Document for UX-1.**

---

## 40. P2 Findings (count: 18)

01. Developer detail (model_id, routing_rule) in REASON stage default view  
02. Developer detail (snapshot_id) in OBSERVE stage default view  
03. Developer detail (proposal_id) in PROPOSE stage default view  
04. Developer detail (execution_id) in EXECUTE stage default view  
05. "No projected impact numbers" footer text in ProposeStage is developer-facing  
06. wave_risk_level badge not linked to specific wave or carrier cutoff  
07. OUTCOME stage shows numeric delta without narrative interpretation  
08. OUTCOME stage has no link to "View what changed" (LIVE world tab)  
09. INDETERMINATE reconciliation outcome has no operator guidance  
10. Copilot "ASK" badge implies only ASK intent but ANALYZE/ACT/OBSERVE_OUTCOME are also available  
11. WorldShell CONTEXT empty state references Copilot (unavailable on standalone /world route)  
12. WorldShell OVERVIEW shows different components for LIVE vs. BASE/SCENARIO without visual explanation  
13. WorldShell RAW tab shows raw JSON — developer content with no gating  
14. DecisionGraph overlaps with DeveloperTraceView in covering the decision chain  
15. Blue (#58A6FF) semantically overloaded across OBSERVE stage color, BLOCKED status, Copilot highlight, and nav links  
16. "Details ›" link in DemoShell footer has cursor:pointer but no onClick handler  
17. No aria-live region for SSE events in lifecycle rail  
18. Demo mode indicator ("Synthetic demo" badge) absent from non-DemoShell pages during demo sessions  

---

## 41. P3 Findings (count: 8)

01. DemoShell top nav uses fixed pixel values that may overflow on very small viewports  
02. CommandCenter 3-column layout not responsive  
03. WorldGrid 4-column layout may overflow on narrow screens  
04. ModelGatewayLab route not linked from global nav  
05. ModelGatewayLab error message references `artifacts/phase18/` — developer-facing  
06. CapabilityPlane lists machine-readable skill names without human descriptions for all entries  
07. "05 APPROVE" stage label uses numeric prefix inconsistently with other stages  
08. ActivityFeed is session-storage only — history lost on browser refresh  

---

## 42. Current Strengths

1. **CopilotDrawer evidence grounding**: facts_observed, severity, citations, and "VIEW CONTEXT AT DECISION TIME" create a strong evidence chain — the best trust-building UX in the product.

2. **ApproveStage ApprovalCard**: "HUMAN APPROVAL REQUIRED" hero header, rationale, facts, state validity, and dual REJECT/APPROVE buttons provide the most complete operator-facing approval experience.

3. **ExpertOverlay gating**: The Expert toggle cleanly gates developer-facing content. Most of the correct developer detail is behind this gate.

4. **SSE-driven real-time pipeline**: The LifecycleRail advances automatically via SSE events with correct stage transitions. No polling needed for stage updates.

5. **ModelGatewayLab VIEW ONLY banner**: Clear and prominent. The read-only constraint is explained. Authority boundary is explicit for this surface.

6. **WorldShell BASE/SCENARIO/LIVE switcher**: Three world states correctly named per GLOSSARY. The distinction is surfaced and switchable.

7. **Closed-loop outcome observation**: CONFIRMED_EXECUTED / CONFIRMED_NOT_EXECUTED / INDETERMINATE reconciliation outcomes are shown. The architecture's three-outcome model is represented.

8. **State freshness indicators**: FreshnessTag component in OBSERVE and APPROVE stages correctly signals FRESH/AGING/STALE.

9. **BackendErrorBanner with retry**: Clean error state on initial load failure.

10. **aria-pressed and aria-label on all interactive button groups**: Good baseline accessibility for keyboard/screen reader support.

---

## 43. Missing UX Concepts

| Missing Concept | Description | Persona Most Affected |
|----------------|-------------|----------------------|
| SOP step sequence view | Which SOP ran, which steps completed, iteration count | DEV, GSI |
| Subagent delegation chain | Which agents were delegated to, in what order | DEV |
| Authority boundary visual | Persistent graphical marker of the governance boundary | OPR |
| SOP management surface | View/edit available SOPs and their steps | GSI |
| Agent definition viewer | View agent objectives, domains, termination policies | DEV, GSI |
| Extension boundary map | What parts of MAIW can be replaced/customized by GSI | GSI |
| Auto-execution notification | Visual alert when execution happens without human approval | OPR |
| Governance policy inspector | View DecisionEngine rules without reading Python code | GSI |
| MCP call parameter viewer | See the exact MCP payload sent during execution | DEV |
| Demo mode global indicator | Show "SYNTHETIC DEMO" banner on all pages during demo sessions | ALL |

---

## 44. Duplicate UX Concepts

| Concept | Surfaces | Issue |
|---------|---------|-------|
| Approval UI | ApproveStage (DemoShell) + CommandCenter right sidebar | Same action, very different context provided |
| ReliabilityPanel | `components/reliability/ReliabilityPanel.tsx` + `components/demo/reliability/ReliabilityPanel.tsx` | Similar but different implementations |
| Decision history/status | DecisionCenter + CommandCenter right sidebar | Both show decision records from sessionStorage |
| "Command Center" identity | DemoShell header + CommandCenter + Layout global header | Three places, one name |
| DecisionGraph + DeveloperTraceView | Both show the decision chain in visual form | Overlapping developer surfaces |
| WorldShell | Embedded in DemoShell (mode=world) + standalone /world route | Same component, two entry points |

---

## 45. Design Principles

See `docs/audits/uiux/MAIW_UI_UX_DESIGN_PRINCIPLES.md` for the 10 principles derived from these findings.

Summary:
- DP-1: Authority Boundary Visibility
- DP-2: Progressive Disclosure by Persona
- DP-3: Single Entry Point for the Core Journey
- DP-4: Consistent Terminology
- DP-5: State Freshness Always Visible
- DP-6: Trust Through Evidence
- DP-7: Navigation Continuity Across Modes
- DP-8: Operator and Developer Views Must Not Mix Without a Gate
- DP-9: Error and Ambiguous Outcomes Require Explicit Guidance
- DP-10: Demo Context Must Not Bleed Into Production Framing

---

## 46. UX-1 Questions

1. Should `/demo` become the primary nav entry point (replacing or absorbing `/command`)?
2. Should the "APPROVE & EXECUTE" button be renamed to "APPROVE" with a secondary label explaining that execution follows?
3. Should STATUS_LABEL['approved'] be changed to 'APPROVED' (or 'APPROVED — EXECUTED' to preserve both)?
4. Should P1-06 (auto-approval no notification) result in a new rail stage or notification surface?
5. Should developer detail in the lifecycle stages be gated behind an existing Expert toggle or a new expandable section?
6. Should SOP/agent/subagent visibility be a new UX-1 surface or folded into ExpertOverlay?
7. Should the "Synthetic demo" banner be a Layout-level component?
8. Should INDETERMINATE outcomes trigger an in-app notification or modal?
9. Should the WorldShell CONTEXT tab be accessible without Copilot (e.g., via a trace_id URL param)?
10. Should the two ReliabilityPanel implementations be consolidated?

---

## 47. Recommended Next Phase (UX-1)

**UX-1 Scope (prioritized)**:

1. **(Must)** Fix STATUS_LABEL['approved'] ≠ 'EXECUTED' conflation in CommandCenter — this is the only finding that is factually incorrect, not just a UX concern. A one-line change.

2. **(Must)** Add `/demo` to global nav as the primary entry point. Rename or consolidate `/command`.

3. **(Should)** Rename "APPROVE & EXECUTE" button to "APPROVE" with a sub-label: "Execution will follow automatically if approved." 

4. **(Should)** Gate developer detail (model_id, routing_rule, proposal_id, snapshot_id, execution_id) in lifecycle stages behind an expandable "Details" section activated by Expert toggle.

5. **(Should)** Add a persistent "MAIW has not changed anything yet" indicator in the OBSERVE, REASON, and PROPOSE stages.

6. **(Should)** Add a "SYNTHETIC DEMO" indicator to the Layout global header when demo mode is active.

7. **(Could)** Add plain-language Outcome narrative alongside numeric KPI delta.

8. **(Could)** Add SOP name and step count to REASON stage.

9. **(Could)** Consolidate the two ReliabilityPanel implementations.

10. **(Could)** Add guidance text for INDETERMINATE reconciliation outcomes.
