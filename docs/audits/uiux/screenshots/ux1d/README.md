# UX-1D Screenshot Manifest

Outcome, Reliability & Decision Trace Consolidation

## Required Screenshots (14)

| # | Filename | Surface | State | What to Capture |
|---|---|---|---|---|
| 1 | `01-outcome-summary-achieved.png` | OutcomeSummary | Execution confirmed + Objective achieved | All 4 sections green outcome, entity deltas, KPI deltas |
| 2 | `02-outcome-summary-not-achieved.png` | OutcomeSummary | Execution confirmed + Objective NOT achieved | Amber outcome (not green), "MAIW is reassessing" |
| 3 | `03-outcome-summary-unknown.png` | OutcomeSummary | Execution UNKNOWN | Yellow pending banner, no outcome claim |
| 4 | `04-outcome-summary-indeterminate.png` | OutcomeSummary | INDETERMINATE | Orange guidance banner, no outcome claim |
| 5 | `05-reliability-panel-unknown.png` | ExecutionReliabilityPanel | UNKNOWN | Amber chip "Execution confirmation unavailable", next action |
| 6 | `06-reliability-panel-reconciling.png` | ExecutionReliabilityPanel | RECONCILING | Amber "Verifying execution", "No operator action required" |
| 7 | `07-reliability-panel-confirmed.png` | ExecutionReliabilityPanel | CONFIRMED_EXECUTED | Green "Execution confirmed" |
| 8 | `08-reliability-panel-indeterminate.png` | ExecutionReliabilityPanel | INDETERMINATE | Orange "Operator review required" + orange badge |
| 9 | `09-reliability-panel-expert.png` | ExecutionReliabilityPanel | Any (expert mode on) | execution_id, timestamps, expert details section |
| 10 | `10-state-delta.png` | StateDelta | Task TASK-000001 | Before/after with strikethrough, arrow, highlighted value |
| 11 | `11-kpi-delta.png` | KPIDelta | Labor utilization | Before/after, +0.8% in green |
| 12 | `12-decision-graph-cross-links.png` | DecisionGraph | Any | VIEW DEVELOPER TRACE / CONTEXT / LIVE WORLD links in toolbar |
| 13 | `13-developer-trace-cross-links.png` | DeveloperTraceView | Trace loaded | VIEW DECISION GRAPH / CONTEXT / LIVE WORLD cross-links |
| 14 | `14-outcome-agent-status-separate.png` | OutcomeSummary | Execution confirmed, agent Completed | EXECUTION and AGENT STATUS sections clearly separate |
