# Phase 14G — MAIW Demo UI Workflow

## Overview

Phase 14G hardens the MAIW v2 demo UI for reliable stakeholder demonstrations. It does not add new agents, capabilities, or model routes. It makes the existing end-to-end demo workflow robust, self-explanatory, and safe to operate.

## Quick Start

1. Ensure the MAIW API backend is running on port 8000
2. Start the frontend dev server: `cd src/ui/web && npm start`
3. Navigate to `http://localhost:3000` (defaults to `/demo`)
4. Select a scenario and click Start
5. Run MAIW Analysis when prompted
6. Follow the lifecycle rail: OBSERVE → REASON → PROPOSE → DECIDE → APPROVE → EXECUTE → OUTCOME

## Demo Shell Layout

### Top Navigation Bar

- **MAIW Command Center** — product identity (always visible)
- **Synthetic demo** — DEMO MODE badge (always visible)
- **Warehouse ID** — shown in the state strip (from `REACT_APP_WAREHOUSE_ID` or `DC-47`)
- **Copilot / Phase 15** — disabled entry point; labeled "Coming in Phase 15". Not functional.
- **Operations / Reliability** — mode switcher for main view vs. reliability view
- **Expert** — toggles the expert overlay (trace, runtime, raw JSON)

### State Strip

Shows in real time:
- `warehouse_id` — operational identity
- State freshness — FRESH (< 60s) / STALE (> 120s) / color-coded
- System status — HEALTHY / DEGRADED / UNKNOWN from runtime status API

### System Footer

- System status with color + text indicator (never color alone)
- Safety invariant status — changes to `! Review required` if RECONCILIATION_REQUIRED event received
- SSE live connection status — shown when a scenario is active
- Details link (future expansion)

## Demo Workflow Step by Step

### Step 1 — Select Scenario

When no scenario is active the ScenarioSelector renders. Recommended scenario: `labor_constraint_wave_risk` (marked with blue border).

Scenarios are fetched from `GET /api/v1/demo/scenarios`. If the backend is unavailable, a `BackendErrorBanner` appears with a **Retry connection** button.

### Step 2 — Start Scenario

Click **Start**. The frontend calls `POST /api/v1/demo/scenario/{name}/start`. The lifecycle rail appears and SSE connection activates.

### Step 3 — OBSERVE (Warehouse State Assembly)

The default view shows:
- **Warehouse Snapshot** — equipment/workers/tasks/inventory grid from `demoStatus.world`
- **Operational Context** — equipment %, labor %, backlog, wave risk from `demoStatus.current_kpis`
- **State freshness** — seconds since last snapshot from `current_kpis.state_freshness_seconds`

Click **▶ Run MAIW Analysis** to trigger the full pipeline.

### Step 4 — REASON, PROPOSE, DECIDE

After analysis completes, the lifecycle rail advances. Each stage shows:
- **REASON** — assessment summary, facts observed, severity, domains affected
- **PROPOSE** — recommended capabilities with domain, target, rationale, risk level
- **DECIDE** — policy result, routing rule, model used, latency

All data comes from `analysisResult` returned by `POST /api/v1/demo/analyze`.

### Step 5 — APPROVE (Human Governance)

If the policy engine requires approval, an **ApprovalCard** appears showing:
- Proposed action and operational target
- Why (rationale from the decision engine)
- Facts from the observe phase
- State validity (freshness + proposal_id + decision_id)
- Risk level badge
- **APPROVE & EXECUTE** and **REJECT** buttons

Approval buttons are disabled after click — duplicate submission is prevented by the backend identity (pending_id). A 404 response indicates the approval was already consumed.

Expired approvals (> 10 minutes) disable both buttons and show an EXPIRED badge.

### Step 6 — EXECUTE

After approval, the ActionExecutor runs. ExecuteStage shows:
- Capability executed and execution_id
- Outcome badge: EXECUTED / NO_OP / DEFERRED / CONFLICT / UNKNOWN / FAILED
- **UNKNOWN** outcome triggers a reconciliation notice — the warehouse state is uncertain and automatic retry is suppressed

### Step 7 — OUTCOME

OutcomeStage shows:
- OBSERVED OPERATIONAL IMPACT (not projected) — pre/post KPI deltas
- Wave Risk, Pending Backlog, Wave Completion, Throughput, Labor Utilization
- Time to recovery (if reached)
- Trend chart from `kpi_history`
- **RUN ANOTHER SCENARIO** button → calls `handleReset()`

### Resetting

Click **Reset** in the scenario header or RUN ANOTHER SCENARIO in OutcomeStage. This:
1. Shows ScenarioSelector immediately (no wait for poll)
2. Clears SSE event buffer
3. Clears analysis result
4. Calls `POST /api/v1/demo/scenario/reset`

## Error and Recovery States

| Error Condition | What the UI Shows |
|---|---|
| Initial load | Spinner + "Connecting to demo backend..." with `role="status"` |
| Backend unavailable | `BackendErrorBanner` with Retry button, `role="alert"` |
| No scenario active | ScenarioSelector with instructional text |
| SSE disconnected | Footer shows amber "Reconnecting" chip |
| Analysis in progress | Spinner in Run Analysis button, disabled state |
| Approval expired | EXPIRED badge, buttons disabled |
| Approval consumed (404) | CONSUMED outcome badge in card |
| Execution unknown | UNKNOWN badge + reconciliation notice |
| Execution failed | FAILED badge in ExecCard |

No blank screens. No raw error objects. No endless spinners. Every error state has an actionable path forward.

## Trust Boundary

The UI makes the following boundaries explicit and visible:

```
Agent/model → analyzes/proposes (reason/propose stages)
WarehouseState → operational truth (observe stage)
DecisionEngine → policy evaluation (decide stage)
Human → approves when required (approve stage)
ActionExecutor → executes (execute stage)
Runtime → confirms outcome (outcome stage)
```

- The model never directly authorizes or executes warehouse actions
- "HUMAN APPROVAL REQUIRED" is shown prominently on every approval card
- The Copilot entry point is disabled and labeled "Coming in Phase 15"

## Viewports

Optimized for:
- 1440×900 (primary)
- 1280×800

Dense tables use contained horizontal scrolling within their card containers.

## Running Tests

```bash
cd src/ui/web && npm test -- --watchAll=false
```

Phase 14G baseline: 500 tests, 23 suites.
