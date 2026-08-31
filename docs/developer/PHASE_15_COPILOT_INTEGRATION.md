# Phase 15 — Copilot Integration Boundary

This document defines the architectural contract for the Phase 15 Copilot feature. It is written in Phase 14G so that Phase 15 work starts from a clear, agreed-upon boundary.

The Copilot entry point is already reserved in the UI (`data-testid="phase15-copilot-button"`) but is disabled. No Copilot functionality is implemented in Phase 14.

---

## Recommended Placement

The Copilot panel should open as a **slide-over drawer** anchored to the right side of the DemoShell, beneath the top nav bar. It must not replace the lifecycle rail or stage content — it is a companion view.

Entry point: the existing disabled `Phase15CopilotButton` in `src/pages/DemoShell.tsx` (top navigation row, left of mode switcher). When enabled in Phase 15, clicking this button opens the Copilot drawer.

Do not add a second entry point or route (`/copilot`). The Copilot is contextual to an active demo session.

---

## Shared State Copilot Must Consume

Copilot is NOT a second source of truth. It reads from the same state the main UI already has:

| State | Source | How to access |
|---|---|---|
| Demo status (scenario, world, KPIs) | React Query cache | `useQueryClient().getQueryData(['demo-status'])` or `useDemoStatus()` hook |
| SSE events | `useDemoSSE` hook | Pass via prop from DemoShell, do not open a second SSE connection |
| Analysis result | Parent state in DemoShell | Pass as prop — do not re-trigger analysis |
| Pending approvals | `demoStatus.pending_approvals` | Same polling source as the rest of the UI |
| Runtime status | `useRuntimeStatus` hook | Reuse existing query |

**Copilot must share the same React Query client.** Pass the query client via `QueryClientProvider` (already in place). Do not create a second client.

---

## APIs Copilot Should Call

Copilot may call:
- `GET /api/v1/demo/status` — already polled every 3s; use React Query cache, do not add a separate poller
- `GET /api/v1/events/stream` — already consumed by `useDemoSSE`; do not open a second SSE connection. Reuse the same event stream by accepting SSE events as props.
- `POST /api/v1/demo/analyze` — only if user explicitly requests re-analysis via Copilot. Must show the same `analyzing` guard the main UI uses to prevent double-analyze.
- `GET /api/v1/demo/counterfactual` — if Copilot surfaces counterfactual scenarios (see CounterfactualPanel for existing implementation)

Copilot may NOT call:
- Any API that starts, resets, or stops a scenario (`POST /demo/scenario/{name}/start`, `POST /demo/scenario/reset`) without routing through `DemoShell` handlers.
- Any approval endpoint (`POST /demo/approve/*`, `POST /demo/reject/*`) — see "Actions Copilot Must NEVER Execute Directly" below.

---

## Actions Copilot Must NEVER Execute Directly

The Copilot is an assistant. It explains, summarizes, and surfaces options. It does not act.

Copilot must NEVER:
- Call `demoAPI.approvePending()` or `demoAPI.rejectPending()` directly
- Call `demoAPI.startScenario()` or `demoAPI.resetScenario()` directly
- POST to any execution endpoint
- Modify the global `analysisResult` state without going through the `handleAnalyze` handler in DemoShell

If the user asks Copilot "approve this" — Copilot must:
1. Surface the pending approval card from the existing ApproveStage view
2. Highlight the **APPROVE & EXECUTE** button already in the UI
3. NOT call the approval API itself

The approval path must always pass through the human operator interacting with the `ApproveStage` component.

---

## How Copilot Links to Proposal/Approval/Trace Views

Copilot may render links or "jump to" controls that:
- Scroll or focus the main stage content to a specific proposal or approval
- Open the Expert overlay at the `trace` tab (use `onViewFullTrace` callback from DemoShell)
- Deep-link to a lifecycle stage by setting a shared active-stage signal (add to DemoShell context if needed)

Copilot must NOT duplicate the trace/proposal/decision views — it references and links to them.

---

## Trust Boundary Requirements

The trust boundary enforced in Phase 14 must be preserved:

```
Agent/model → analyzes/proposes ONLY
Human → approves ALWAYS when required
ActionExecutor → executes AFTER approval
Copilot → explains, summarizes, links to existing views
```

Copilot output must be clearly labeled as assistant output, not as an authoritative system status. Example: use a distinct header like "Copilot" with a Phase 15 indicator.

Copilot reasoning must not be shown in the existing lifecycle rail or stage content panes — those are reserved for authoritative pipeline output.

---

## Implementation Notes

- Copilot drawer component: `src/components/demo/copilot/CopilotDrawer.tsx` (to be created in Phase 15)
- The existing `Phase15CopilotButton` in `DemoShell.tsx` will be wired up when CopilotDrawer is ready
- All new Copilot state should be local to CopilotDrawer or a new `CopilotContext` — do not pollute DemoShell state
- Copilot tests should go in `src/__tests__/demo/phase15_copilot.test.tsx`

---

## What Is Out of Scope for Phase 15 Copilot

- Autonomous warehouse actions of any kind
- A second SSE stream
- A separate API backend for Copilot
- Replacing any existing lifecycle stage views
- Fabricated analytics or placeholder KPIs not from an authoritative API
