# MAIW UI/UX Screen Inventory — UX-0 Baseline

> Audit date: 2026-09-20  
> Branch: feat/ux-0-current-state-audit  
> SHA: cd741bb (main HEAD at audit start)  
> Method: React source code inspection + API router review

---

## Navigation Structure

The global Layout (`src/ui/web/src/components/Layout.tsx`) renders a persistent top bar with:

```
[NVIDIA logo] [MAIW COMMAND CENTER] [LIVE/OFFLINE] [WAREHOUSE: DC-47]
COMMAND | STATE | DECISIONS | MODELS | WORLD | CAPABILITIES | ACTIVITY
```

**The default route `/` redirects to `/demo` (DemoShell), which is NOT in the global nav.** The primary user-facing experience lives at a route invisible in navigation.

---

## Route Inventory

| Route | Page Component | In Global Nav | Persona | Purpose | Primary Action | Data Dependency | Persona Fit Score |
|-------|---------------|--------------|---------|---------|----------------|-----------------|-------------------|
| `/demo` (default) | DemoShell | NO | OPERATOR | Live scenario lifecycle management | Run MAIW Analysis | /api/v1/demo/status, /api/v1/events/stream | 3/5 |
| `/command` | CommandCenter | YES (COMMAND) | SHARED | System dashboard with metrics, decisions, activity | Approve/reject pending actions | Equipment, operations, safety, MCP, demo APIs | 2/5 |
| `/state` | WarehouseStatePage | YES (STATE) | DEVELOPER/GSI | Warehouse entity inspector | View/filter entities | /api/v1/equipment, /api/v1/operations | 2/5 |
| `/decisions` | DecisionCenter | YES (DECISIONS) | OPERATOR/DEVELOPER | Decision history + manual action trigger | Trigger equipment action | /api/v1/equipment, sessionStorage | 2/5 |
| `/models` | ModelGateway | YES (MODELS) | DEVELOPER/GSI | Model Gateway configuration and status | View model policy | /api/v1/runtime/status | 3/5 |
| `/models/lab` | ModelGatewayLab | NO (sub-route) | DEVELOPER | Read-only evaluation artifact inspector | Compare model runs | /api/v1/model-lab/* | 4/5 |
| `/world` | WorldShell | YES (WORLD) | DEVELOPER/GSI | Warehouse World Explorer | Navigate entities/graph | /api/v1/world/* | 2/5 |
| `/capabilities` | CapabilityPlane | YES (CAPABILITIES) | DEVELOPER/GSI | MCP capability catalogue | View skill types | /api/v1/mcp/status | 3/5 |
| `/activity` | ActivityFeed | YES (ACTIVITY) | DEVELOPER | Full session event log | Filter/scroll events | sessionStorage | 3/5 |
| `/health` | SystemHealth | NO | DEVELOPER | System health check | Ping backend | /api/v1/health | 3/5 |
| `/chat` | ChatInterfaceNew | NO | LEGACY | Legacy chat interface | N/A | Legacy API | 1/5 |
| `/equipment` | EquipmentNew | NO | LEGACY | Equipment list | N/A | /api/v1/equipment | 1/5 |
| `/operations` | Operations | NO | LEGACY | Operations view | N/A | /api/v1/operations | 1/5 |
| `/safety` | Safety | NO | LEGACY | Safety incidents | N/A | /api/v1/safety | 1/5 |
| `/forecasting` | Forecasting | NO | LEGACY | Forecasting | N/A | /api/v1/forecasting | 1/5 |
| `/analytics` | Analytics | NO | LEGACY | Analytics dashboard | N/A | Various | 1/5 |
| `/documents` | DocumentExtraction | NO | LEGACY | Document extraction | N/A | Training API | 1/5 |
| `/documentation` | Documentation | NO | DEVELOPER/GSI | Documentation hub | Navigate docs | Static | 3/5 |
| `/documentation/mcp-integration` | MCPIntegrationGuide | NO | GSI | MCP integration guide | Read | Static | 3/5 |
| `/documentation/api-reference` | APIReference | NO | DEVELOPER | API reference | Read | Static | 3/5 |
| `/documentation/deployment` | DeploymentGuide | NO | GSI | Deployment guide | Read | Static | 3/5 |
| `/documentation/architecture` | ArchitectureDiagrams | NO | DEVELOPER/GSI | Architecture diagrams | Read | Static | 3/5 |
| `/mcp-test` | MCPTest | NO | DEVELOPER | MCP connection test panel | Test MCP | /api/v1/mcp/* | 3/5 |

---

## DemoShell Embedded Surfaces (within /demo)

The DemoShell (`src/ui/web/src/pages/DemoShell.tsx`) is a composite shell containing multiple surfaces accessed via internal mode and stage state, not URL routing:

| Internal Surface | Access Path | Persona | Purpose | Persona Fit Score |
|-----------------|-------------|---------|---------|-------------------|
| ScenarioSelector | /demo + no active scenario | OPERATOR | Choose and start a scenario | 3/5 |
| LifecycleRail (Observe) | /demo + scenario active | OPERATOR | See warehouse state, trigger analysis | 3/5 |
| LifecycleRail (Reason) | /demo + scenario active + REASON | OPERATOR | See agent reasoning output | 2/5 |
| LifecycleRail (Propose) | /demo + scenario active + PROPOSE | OPERATOR | Review proposed actions | 3/5 |
| LifecycleRail (Decide) | /demo + scenario active + DECIDE | OPERATOR/DEVELOPER | See decision outcome | 3/5 |
| LifecycleRail (Approve) | /demo + scenario active + APPROVE | OPERATOR | Human approval gate | 4/5 |
| LifecycleRail (Execute) | /demo + scenario active + EXECUTE | OPERATOR | See execution result | 3/5 |
| LifecycleRail (Outcome) | /demo + scenario active + OUTCOME | OPERATOR | Compare pre/post state | 3/5 |
| CopilotDrawer | /demo + scenario active + Copilot open | OPERATOR | ASK/ANALYZE/ACT/OBSERVE_OUTCOME | 4/5 |
| WorldShell (Overview) | /demo + mode=world + tab=overview | OPERATOR/DEVELOPER | Entity summary table | 3/5 |
| WorldShell (Graph) | /demo + mode=world + tab=graph | DEVELOPER/GSI | Entity relationship graph | 2/5 |
| WorldShell (Changes) | /demo + mode=world + tab=changes | DEVELOPER | Diff of scenario vs BASE | 2/5 |
| WorldShell (Context) | /demo + mode=world + tab=context | DEVELOPER | Historical snapshot at decision time | 2/5 |
| WorldShell (Raw) | /demo + mode=world + tab=raw | DEVELOPER | Raw JSON entity data | 1/5 |
| ReliabilityPanel | /demo + mode=reliability | DEVELOPER | Fault injection, reconciliation, safety | 2/5 |
| ExpertOverlay (Trace) | /demo + Expert ON + TRACE tab | DEVELOPER | Developer trace timeline, artifacts | 2/5 |
| ExpertOverlay (Runtime) | /demo + Expert ON + RUNTIME tab | DEVELOPER | Runtime health, MCP, agents | 2/5 |
| ExpertOverlay (Raw Events) | /demo + Expert ON + RAW EVENTS tab | DEVELOPER | SSE event stream | 1/5 |

---

## Summary Counts

- Total distinct routes: 23
- Routes in global nav: 7
- Primary operator route (/demo): NOT in global nav
- Screens with dual/conflicting implementations: 3 (ReliabilityPanel, CommandCenter vs DemoShell, ChatInterface)
- Screens marked LEGACY (not part of MAIW v2 core): ~8
- Routes accessible only via URL (not linked from nav): ~10
