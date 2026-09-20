# MAIW UI/UX Journey Maps — UX-0 Baseline

> Audit date: 2026-09-20  
> Method: Source code inspection (DemoShell, CopilotDrawer, stages/*, world/*, API routers)

---

## Persona Definitions

- **Operator (OPR)**: Warehouse supervisor making real-time operational decisions. Needs clear, plain-language answers. Not technical. Goal: understand what's at risk and what to do.
- **Developer (DEV)**: NVIDIA / partner engineer building on MAIW. Needs full trace, runtime provenance, model route, SOP path. Goal: verify the pipeline worked correctly.
- **GSI / Solution Architect (GSI)**: Systems integrator deploying MAIW. Needs to understand where to connect WMS/WES, how to configure SOPs/agents/governance, what can be replaced. Goal: map MAIW onto a real deployment.

---

## Journey A — Warehouse Operator: Canonical Wave 17 Scenario

### Context
Operator opens the app, loads the "Wave 17 at risk" scenario, asks why, reviews proposal, approves action, and observes outcome.

| Step | Operator Goal | UI Surface | Current State | Friction | Severity |
|------|-------------|-----------|--------------|----------|----------|
| 1 | Open app, see warehouse state | `/demo` → ScenarioSelector | Operator sees a scenario list. App says "Synthetic demo". Not clear this is a real warehouse simulation. | No context on what "scenario" means to a real operator. | P2 |
| 2 | Start scenario — see wave risk | ScenarioSelector → "Wave 17 disruption" | Scenario starts. LifecycleRail appears at OBSERVE stage. WorldGrid shows equipment/workers/tasks/inventory counts. | Numbers are raw. No explanation of what "pending tasks: 47" means for wave risk. | P2 |
| 3 | See that Wave 17 is at risk | OBSERVE stage / OperationalContextStrip | OperationalContextStrip shows wave_risk_level (HIGH/CRITICAL) as badge. KPI strip shows wave completion %. | Wave risk badge present. Not linked to specific wave or carrier cutoff. | P2 |
| 4 | Run analysis to understand | OBSERVE stage — "Run MAIW Analysis" button | Button present with `▶ Run MAIW Analysis`. Sub-label: "Triggers observe → reason → propose → decide pipeline". | Sub-label is developer-facing. Operator doesn't know what propose/decide means. | P2 |
| 5 | Read agent's assessment | REASON stage | Shows model_id, routing_rule, assessment summary, severity badge, domains affected. | Model ID and routing rule are developer detail at Level 3 mixed into operator view at Level 1. | P1 |
| 6 | Review proposed action | PROPOSE stage | ProposalCard shows: Action, Capability, Target, Risk badge, Rationale, Proposal ID. "WHY THIS RECOMMENDATION?" button present. | "Capability" is technical (warehouse.labor.allocate). Proposal ID visible but explained. Operator-facing rationale present. | P2 |
| 7 | Ask "Why is Wave 17 at risk?" | CopilotDrawer (ASK intent) | Copilot opens on "Copilot" button. Sends ASK turn, returns evidence-grounded answer with severity, facts, citations. "VIEW CONTEXT AT DECISION TIME" button appears. | Copilot entry point labeled "ASK" badge but does ANALYZE/ACT/OBSERVE_OUTCOME too. "ASK" is confusing for operators who would say "ask a question". | P2 |
| 8 | Understand AI has NOT executed yet | Pre-APPROVE state visibility | APPROVE stage shows "HUMAN APPROVAL REQUIRED" hero header. Facts and rationale shown. REJECT/APPROVE & EXECUTE buttons present. | "APPROVE & EXECUTE" button label conflates approval (governance) with execution (ActionExecutor). These are distinct in MAIW architecture but the UI presents them as one action. | P1 |
| 9 | Approve the action | ApproveStage — APPROVE & EXECUTE button | Click starts execution. Rail shows EXECUTE then OUTCOME. | No intermediate "approved — waiting for execution" state visible. Execution happens synchronously. | P2 |
| 10 | See execution result | EXECUTE stage | Shows execution_id, success/failure, outcome label (CONFIRMED_EXECUTED / CONFIRMED_NOT_EXECUTED / INDETERMINATE). | INDETERMINATE outcome has no clear operator-facing guidance. | P2 |
| 11 | See that it worked | OUTCOME stage | Pre/post KPI delta shown. Equipment/labor/wave changes visible. | Operator must mentally compare numbers. No plain-language "Wave 17 is now back on track" summary. | P2 |
| 12 | Confirm authority boundary was respected | Throughout journey | Authority boundary not visually marked anywhere in the pipeline UI. | No permanent "MAIW has not executed anything" reminder visible before approval. The separation is implicit in the rail position, not explicit. | P1 |

**Operator Journey Score: PARTIAL**  
Operator can complete the core journey but faces consistent developer-level detail mixed into the operational narrative. The authority boundary is architecturally sound but not visually enforced in the UI.

---

## Journey B — NVIDIA Developer: Full Pipeline Trace Reconstruction

### Context
Developer verifies the complete pipeline: ContextSnapshot → Agent → SOP → Runtime → Model route → Skills → Subagents → RecommendedAction → ActionProposal → Decision → Approval → Execution → MCP → LIVE state → Outcome

| Pipeline Link | Developer Goal | UI Surface | Visibility | Notes |
|--------------|---------------|-----------|-----------|-------|
| OperationalContextSnapshot | Verify snapshot sealed correctly | OBSERVE stage → snapshot_id field | VISIBLE | snapshot_id shown in IdText. snapshot_id also in ExpertOverlay → Trace. |
| Agent | Verify OperationsCoordinationAgent ran | REASON stage → model_id, routing_rule | VISIBLE | Agent type not labeled (always "Operations Agent"). SOP not shown here. |
| SOP | Verify SOP selection and step sequence | NONE in operator view | HIDDEN | No SOP-level view in any screen. ExpertOverlay traces model calls but not SOP steps. |
| Runtime | Verify which runtime executed | ExpertOverlay → RUNTIME tab | PARTIALLY VISIBLE | Runtime type shown but not which SOP was used or iteration count. |
| Model route | Verify routing_rule + model_id | REASON stage + ExpertOverlay TRACE | VISIBLE | routing_rule and model_id shown in REASON stage lifecycle card. |
| Skills | Verify which skill built the proposal | SKILL events in SSE / ExpertOverlay | PARTIALLY VISIBLE | SKILL SSE events visible in RAW EVENTS. Not mapped to proposal in developer trace. |
| Subagents | Verify delegation chain | NONE | MISSING | No subagent delegation visualization exists in any screen. |
| RecommendedAction | Verify capability/target/rationale | PROPOSE stage → ProposalCard | VISIBLE | capability, target, rationale all present. |
| ActionProposal | Verify proposal_id, risk_level | PROPOSE stage + APPROVE stage | VISIBLE | proposal_id, risk_level shown on proposal card and approval card. |
| Decision | Verify decision outcome + violations | DECIDE stage → outcome, violations | VISIBLE | decision_id, outcome, violations shown. |
| Approval | Verify approval governance | APPROVE stage + approval_id | VISIBLE | approval_id in ApproveStage state validity row. |
| Execution | Verify execution_id + outcome | EXECUTE stage | VISIBLE | execution_id, success, outcome_label shown. |
| MCP | Verify MCP transport used | ExpertOverlay RUNTIME → MCP domain status | PARTIALLY VISIBLE | MCP domain availability (equipment/labor/wave) shown, but specific MCP call parameters not shown. |
| LIVE state | Verify warehouse mutation occurred | World view → LIVE tab → WorldLive | VISIBLE | WorldLive shows execution record when available. |
| Outcome | Verify CONFIRMED_EXECUTED/NOT/INDETERMINATE | OUTCOME stage | VISIBLE | Reconciliation outcome shown. INDETERMINATE handling unclear. |
| trace_id | Verify single trace correlates all steps | ExpertOverlay TRACE tab | VISIBLE | trace_id shown in developer trace timeline. |

**Developer Journey Score: PARTIALLY VISIBLE overall**  
Key missing: SOP step sequence, subagent delegation chain, explicit MCP call parameters. Full trace reconstruction possible for most links but requires switching between DemoShell stages, ExpertOverlay tabs, and World view — no single unified trace surface.

---

## Journey C — GSI / Solution Architect: Integration Assessment

### Context
GSI evaluating MAIW for a real warehouse deployment needs to understand: what to connect, what to configure, what can be customized.

| GSI Question | Relevant Screen(s) | Score | Notes |
|-------------|-------------------|-------|-------|
| Where do I connect WMS/WES/labor/equipment systems? | /capabilities, /documentation/mcp-integration | REQUIRES CODE READING | CapabilityPlane shows skill names but not the MCP server endpoints or configuration schema. MCPIntegrationGuide exists in docs. |
| Where do SOPs live? How do I define a new SOP? | NONE in UI | ABSENT | No SOP management or viewing surface exists in the UI. SOPs are YAML files in the codebase, visible only to developers. |
| Where do agents and their objectives live? | /capabilities → CapabilityPlane, ExpertOverlay RUNTIME | REQUIRES CODE READING | Agent names visible (Operations, Equipment, Safety) but agent definitions, domains, and objectives not surfaced. |
| How do I select which runtime executes? | ExpertOverlay RUNTIME | REQUIRES CODE READING | Runtime type shown (Deterministic vs DeepAgents) in ExpertOverlay, not configurable from UI. |
| Where is the model routing policy? | /models → ModelGateway, /models/lab | CLEAR | ModelGateway page shows policy rules and enabled models. ModelGatewayLab shows evaluation evidence. |
| What governance rules apply? | /decisions → DecisionCenter, ApproveStage | REQUIRES CODE READING | Approval flow is visible but the governance policy rules (DecisionEngine) are not inspectable from UI. |
| What can I replace/customize vs. what is fixed? | NONE in UI | ABSENT | No extension boundary visualization. The MAIW Authority Boundary concept exists in GLOSSARY.md but not surfaced in any UI screen. |
| What MCP capabilities are registered? | /capabilities → CapabilityPlane | CLEAR | READ/PROPOSAL/EXECUTION types visible with descriptions. Wiring status shown. |
| How do I see which scenario stresses which domain? | /demo → ScenarioSelector | PARTIAL | Scenario names are descriptive. No domain-impact preview shown before starting. |
| What happened during the last run? | /activity → ActivityFeed, ExpertOverlay | PARTIAL | ActivityFeed shows SSE events. No structured summary of what was executed in a run. |

**GSI Journey Score: REQUIRES CODE READING for most integration questions**  
Key missing: SOP management surface, agent configuration view, extension boundary diagram, governance policy inspector.
