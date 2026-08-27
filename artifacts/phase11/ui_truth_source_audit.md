# Phase 11 §10 — UI Truth Source Audit

**Date:** 2026-08-27  
**Component:** `src/ui/web/src/pages/CommandCenter.tsx` + reliability components  
**Audit scope:** Every data value displayed in the Command Center — classify as
LIVE, DERIVED, VALIDATED_ARTIFACT, or HARDCODED.

---

## Audit Table

| UI Element | Displayed value | Source type | Data source | Notes |
|-----------|----------------|-------------|-------------|-------|
| MAIW Operational Status badge | `HEALTHY` / `DEGRADED` | LIVE | `GET /api/v1/runtime/status` → `runtime.maiw_operational_status` | Color: green if HEALTHY, amber otherwise |
| Model Gateway status | `HEALTHY` / `CIRCUIT OPEN` / `DEGRADED` | LIVE | `runtime.model_gateway_status` | Shown in ReliabilityPanel only when not HEALTHY |
| Domain Health grid (4 domains) | `HEALTHY` / `DEGRADED` / `CIRCUIT OPEN` | LIVE | `runtime.domain_health.{equipment,labor,wave,inventory}` | ReliabilityPanel; values from DomainCircuitRegistry.operational_status() |
| Circuit trip detail | per-domain failure count / last failure | LIVE | `runtime.circuit_states.domains` | Shown only when state ≠ CLOSED |
| Equipment Operational % | numeric KPI | LIVE + FALLBACK | `demoStatus.current_kpis.equipment_operational_pct` (demo) OR computed from `equipment` API response (non-demo) | Falls back to local computation if demo KPI unavailable |
| Labor Availability % | numeric KPI | LIVE + FALLBACK | `demoStatus.current_kpis.labor_availability_pct` OR computed from workforce API | Same fallback pattern |
| Wave Completion % | numeric KPI | LIVE | `demoStatus.current_kpis.wave_completion_pct` | Shows `—` when demo not active |
| Time to Recovery | seconds | LIVE | `demoStatus.current_kpis.time_to_recovery_seconds` | Shows `—` when demo not active |
| Simulated Throughput | units/hr | LIVE | `demoStatus.current_kpis.simulated_throughput` | Demo only |
| Projected Service Level | % | LIVE | `demoStatus.current_kpis.projected_service_level` | Demo only |
| Active Assets count | integer | LIVE | `equipment` API response filtered by status in {available, assigned, active, operational} | Non-demo |
| Pending Tasks count | integer | LIVE | `tasks` API response filtered by status=pending | Non-demo |
| MCP Server status chips | per-server status | LIVE | `GET /api/v1/mcp/status` via `mcpAPI.getStatus()` | |
| Safety Scorecard counters (Batch 6 baseline) | violation counts | VALIDATED_ARTIFACT | `BATCH6_BASELINE` constant in `useReliabilityCounters.ts` | Shows "VALIDATED BATCH 6" label — clearly marked as static artifact |
| Safety Scorecard counters (live) | violation counts | DERIVED | SSE events from `useDemoSSE` → `useReliabilityCounters` | Shows "LIVE CURRENT RUN" label — clearly marked as live |
| Simulation time display | `t=Xs` | LIVE | `demoStatus.world.elapsed_seconds` | |
| Activity Feed entries | log entries with category, content | LIVE | SSE events from `/api/v1/events/stream` via `useDemoSSE` | Persisted to sessionStorage between renders |
| Decision history | proposal/decision pairs | LIVE + LOCAL | `sessionStorage('maiw_decision_history')` | Populated from API responses during demo flow |
| Pending Approvals count | integer | DERIVED | Decision history filtered by status=requires_human_approval | |
| Agent "Ultra" model role | disabled indicator | HARDCODED | `const isDisabled = role === 'Ultra'` | Ultra is slow/opt-in — correct to gate it; not a data display |
| Scenario name in control bar | scenario name | LIVE | `GET /api/v1/demo/scenarios` | |
| Fault Injection panel profiles | 5 static profiles | HARDCODED | Constant array in `FaultInjectionPanel.tsx` | Profile metadata is intentionally static (maps known fault types); injectable profiles trigger real `/demo/inject` API calls |

---

## Findings

### HARDCODED (intentional)

- **Ultra role disabled flag** — correct: Ultra is slow/opt-in, disabling it in UI is deliberate.
- **Fault Injection profiles** — profile metadata (name, description, safety behavior) is static.
  The `injectEventType` and `injectPayload` fields DO reach the live `/demo/inject` endpoint —
  the hardcoding is in the label/description, not the injected data.

### HARDCODED (potential theater) — none found

No operational state values (HEALTHY, DEGRADED, CIRCUIT OPEN) are hardcoded in displayed output.
All domain health values come from `runtime.domain_health` which is populated by
`DomainCircuitRegistry.operational_status()` at request time.

The Safety Scorecard baseline (`BATCH6_BASELINE`) is explicitly labeled "VALIDATED BATCH 6"
in the UI — the static-vs-live distinction is always surfaced to the operator.

### DERIVED (computed from live data)

- KPI fallbacks: equipment/labor percentages fall back to local computation from API data when
  demo KPIs are not available. This is correct behavior (non-demo mode shows real data).
- Reliability counters: derived from SSE event stream, not from a static store.

---

## Verdict

**No demo theater found.** All operational state values displayed in the UI are either:
1. Fetched live from the API at render time, or
2. Explicitly labeled as validated artifacts (BATCH 6 baseline), or
3. Derived from live SSE events.

The `BATCH6_BASELINE` constant is the only static data displayed to the user, and it is
always rendered with a "VALIDATED BATCH 6" badge — the distinction is explicit and preserved.
