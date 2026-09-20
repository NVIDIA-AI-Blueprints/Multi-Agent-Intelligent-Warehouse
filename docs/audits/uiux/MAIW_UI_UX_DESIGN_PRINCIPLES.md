# MAIW UI/UX Design Principles — UX-0 Baseline

> Derived from findings in the UX-0 current-state audit (2026-09-20).  
> These principles describe the **intended** design direction for UX-1 and beyond.  
> They are NOT yet implemented consistently — they describe the target state.

---

## DP-1 — Authority Boundary Visibility

**Statement**: Every screen must make it unambiguous whether MAIW has or has not executed an action on the warehouse. The authority boundary between AI recommendation and operational execution must be visually persistent and explicit.

**Derived from**: P1 finding — no persistent "nothing has been executed yet" indicator before approval. The APPROVE & EXECUTE button conflates approval (governance) with execution (ActionExecutor). Recommendation views can look like execution views.

**Implementation guidance**: Consider a persistent banner in the recommendation and approval stages. The approval button should say "APPROVE" and describe execution as a consequence, not as the action label itself.

---

## DP-2 — Progressive Disclosure by Persona

**Statement**: Information must be stratified into at least three levels: (1) operational answer (what the operator needs to act), (2) evidence (supporting facts and context), (3) implementation detail (IDs, trace, model route). Level 3 detail must require explicit opt-in.

**Derived from**: P1 finding — model_id, routing_rule, proposal_id, snapshot_id, and trace_id appear in the primary operator view (REASON, PROPOSE, OBSERVE stages) without progressive disclosure. Operators cannot distinguish operational signal from developer provenance.

**Implementation guidance**: Apply an "Expert" or "Details" expansion pattern. Show only operational summary by default; expose IDs, trace links, and model provenance only when expanded.

---

## DP-3 — Single Entry Point for the Core Journey

**Statement**: The canonical operator journey (scenario → analyze → propose → approve → execute → outcome) must be accessible from one clearly labeled, always-discoverable entry point in the global navigation.

**Derived from**: P1 finding — the primary screen (`/demo`) is not in the global nav. Two pages both claim to be "MAIW Command Center". The operator's primary workflow starts at a hidden route.

**Implementation guidance**: Promote `/demo` or a renamed equivalent to the global nav as the first item. Retire or clearly demote `/command` (or merge it into the primary page).

---

## DP-4 — Consistent Terminology Across All Surfaces

**Statement**: Every UI label must use the canonical term from `docs/GLOSSARY.md`. No surface may use a term that conflicts with the glossary definition.

**Derived from**: P2 findings — the UI uses "approved → EXECUTED" conflation in CommandCenter status labels, "capability" where the glossary defines "skill", and the lifecycle stage labeled "SKILL" where the architecture calls it proposal skill invocation within the PROPOSE phase.

**Implementation guidance**: Before UX-1, create a UI terminology mapping that links every label to its canonical glossary term. Automated tests should enforce that displayed strings match glossary terms for critical authority-boundary concepts.

---

## DP-5 — State Freshness is Always Visible

**Statement**: Any screen that shows warehouse state must display how fresh that state is. Stale state must be clearly signaled before the operator takes any approval action.

**Derived from**: Finding that state freshness (FreshnessTag) exists in OBSERVE stage and ApproveStage but is not visible at the top level before the operator initiates analysis. An operator may analyze stale state without realizing it.

**Implementation guidance**: Promote the STATE FRESH/STALE indicator (already in DemoShell's StateStrip) to be contextually visible whenever state-dependent information is displayed. Block or warn on approval if state is STALE.

---

## DP-6 — Trust is Built Through Evidence, Not Interface Decoration

**Statement**: Every operator-facing claim ("Wave 17 is at risk", "This action will resolve the disruption") must be backed by surfaced facts from the warehouse graph. AI-generated claims without grounding evidence must be visually distinct and lower-confidence.

**Derived from**: Strength observation — the Copilot ASK flow already surfaces facts_observed and citations. The APPROVE stage already surfaces "Facts supporting this decision". This pattern must be applied consistently to all agent-generated claims.

**Implementation guidance**: Extend the facts_observed / grounding evidence pattern to the REASON stage and the Outcome assessment.

---

## DP-7 — Navigation Continuity Across Modes

**Statement**: When the operator moves between the operations lifecycle and the world view (or Copilot), their current position in the lifecycle should be preserved and recoverable. No navigation action should lose pipeline state.

**Derived from**: Finding that switching to "world" mode from DemoShell exits the lifecycle view without returning to the same stage. The Copilot has a "Return to Copilot" button (good) but other cross-mode navigations have no clear return path.

**Implementation guidance**: Implement breadcrumb or persistent stage indicator even when in world/reliability modes. "Back to [stage]" affordance on all mode transitions.

---

## DP-8 — Operator and Developer Views Must Not Mix Without a Gate

**Statement**: The Expert/Developer view toggle must be the only path to developer-level detail. Every element behind the gate must be consistently gated; no developer detail should leak into the default operator view.

**Derived from**: Finding that ExpertOverlay toggle exists and works well, but developer-level information (model_id, routing_rule, proposal_id, snapshot_id) is visible by default in the lifecycle stages before the Expert toggle is activated.

**Implementation guidance**: Audit every element in the lifecycle stages for its persona level. Elements that require Expert mode must only render when the toggle is on.

---

## DP-9 — Error and Ambiguous Outcomes Require Explicit Operator Guidance

**Statement**: Any reconciliation outcome of INDETERMINATE, execution outcome of UNKNOWN, or state freshness of STALE must surface an operator-facing action recommendation, not just a status label.

**Derived from**: Finding that INDETERMINATE reconciliation shows a label but no guidance. UNKNOWN execution shows a label but no next step. Operators have no clear path when the system cannot confirm execution.

**Implementation guidance**: For each ambiguous outcome, define and display a specific operator prompt: "INDETERMINATE — Contact system administrator to verify wave task assignment on WMS." Do not leave operators with status codes.

---

## DP-10 — The Demo Context Must Never Bleed Into Production Framing

**Statement**: All demo/simulation mode indicators (Synthetic Demo badge, scenario controls, clock) must be visually consistent and present on every screen accessible during a demo session. Operators must always know they are in simulation.

**Derived from**: Finding that the "Synthetic demo" badge appears in DemoShell's top bar but not in CommandCenter, DecisionCenter, or World Explorer when navigated to from within a demo session. An operator could mistake the simulated warehouse state for live production data.

**Implementation guidance**: Thread the demo mode indicator through the global Layout when `MAIW_DEMO_MODE=true`. Do not rely on per-page banners.
