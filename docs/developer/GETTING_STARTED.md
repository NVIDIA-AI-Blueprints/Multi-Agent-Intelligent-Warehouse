# MAIW Developer Getting Started

This guide orients a new developer in the codebase: what each package does,
which file to edit for which concern, and how to verify changes.

---

## Codebase Map

```
Multi-Agent-Intelligent-Warehouse/
├── packages/               ← canonical Python packages — import from here, never from src.*
│   ├── maiw-models/        ← ModelGateway, NIM provider, ModelRequest, ReasoningLevel, ModelRouter
│   ├── maiw-mcp/           ← MCP contracts, ActionProposal, circuit breakers, deadlines
│   ├── maiw-state/         ← WarehouseStateSnapshot, domain state (Equipment/Labor/Wave/Inventory)
│   ├── maiw-skills/        ← domain skills (inventory lookup, equipment query, labor capacity, wave status)
│   ├── maiw-decision/      ← DecisionEngine — APPROVED / REJECTED / DEFERRED outcomes
│   ├── maiw-execution/     ← BaseActionExecutor (4-guard pattern), domain executors, ExecutionOutcome
│   └── maiw-agents/        ← Equipment, Operations, Safety reasoning agents
│       ├── equipment/      ← Equipment & Asset Operations Agent (EAO)
│       ├── operations/     ← Operations Coordination Agent (OCA)
│       └── safety/         ← Safety & Compliance Agent (SCA)
│
├── apps/api/maiw_api/      ← FastAPI composition root
│   ├── bootstrap.py        ← wires packages together (gateway, agents, executors, circuit registry)
│   ├── routers/demo.py     ← /demo/* endpoints (analyze, approve, reject, execute, reconcile, events)
│   ├── demo/
│   │   ├── scenarios/      ← YAML scenario definitions (add a new scenario here)
│   │   ├── controller.py   ← DemoScenarioController — loads + runs scenarios
│   │   ├── world.py        ← DemoWarehouseWorld — simulated warehouse state
│   │   ├── providers/      ← SimulationProviders (equipment/labor/wave/inventory) — no real DB/MCP
│   │   ├── events.py       ← EventCategory enum + SSE event emission
│   │   └── kpi.py          ← KPI computation for counterfactual comparison
│   └── config.py           ← all env-var configuration (timeouts, circuit thresholds, etc.)
│
├── mcp_servers/            ← independently deployable MCP 2.0 servers (stdio or HTTP)
│   ├── equipment/server.py
│   ├── labor/server.py
│   ├── wave/server.py
│   └── inventory/server.py
│
├── src/ui/web/src/         ← React frontend
│   ├── pages/CommandCenter.tsx    ← main operator view (demo control, activity feed, reliability)
│   ├── hooks/              ← useDemoSSE, useReliabilityCounters, useRuntime
│   ├── components/reliability/   ← ReliabilityPanel, SafetyScorecard, FaultInjectionPanel, etc.
│   └── services/api.ts     ← typed API client (RuntimeStatus, CircuitStats, DomainHealth)
│
└── tests/
    ├── unit/reliability/   ← Phase 10E fault profiles, golden invariants (388 tests, no services needed)
    ├── unit/               ← all other unit tests
    └── contract/           ← MCP contract tests
```

---

## Dependency Flow (one-way — do not reverse)

```
maiw-models ──┐
maiw-mcp   ──┤
              ▼
        maiw-state ──┐
        maiw-skills ─┤
                     ▼
              maiw-decision ──┐
              maiw-execution ─┤
                              ▼
                        maiw-agents
                              │
                              ▼
                        apps/api (bootstrap.py)
```

Nothing in `packages/` imports from `apps/` or `src.*`.

---

## The Pipeline (one request through the system)

```
POST /demo/analyze
  → bootstrap injects: state_provider, agents, executors, approval_store
  → WarehouseStateProvider.get_state()  [read-only MCP / SimulationProvider]
  → WarehouseStateSnapshot.seal()       [immutable, UUID-stamped]
  → agent.analyze_disruption(snapshot)
      → ModelGateway.generate()         [NIM call, circuit-breaker wrapped]
      → returns ActionProposal
  → DecisionEngine.evaluate(proposal)   [deterministic, no I/O]
      → APPROVED | REJECTED | DEFERRED
  → POST /demo/approve  (human gate)
  → POST /demo/execute
      → BaseActionExecutor.execute(proposal, decision)
          → guard 1: decision.outcome == APPROVED
          → guard 2: decision.proposal_id == proposal.proposal_id
          → guard 3: proposal.action in _ALLOWED_ACTIONS
          → guard 4: decision not stale (snapshot age check)
          → _do_execute() → MCP write tool call
          → returns ExecutionOutcome: EXECUTED | NO_OP | CONFLICT | UNKNOWN | FAILED
```

---

## Running Tests

```bash
# All CORE CI (no services):
./scripts/testing/run_core_ci.sh

# Phase 10E reliability only:
./scripts/testing/run_reliability.sh

# Frontend:
cd src/ui/web && npm test -- --watchAll=false
```

---

## Environment Setup

```bash
python3 -m venv env
source env/bin/activate
./scripts/install_packages.sh

cd src/ui/web
cp .env.example .env
npm install
```

---

## Next Steps

- [ADDING_A_SCENARIO.md](ADDING_A_SCENARIO.md) — add a new demo scenario
- [ADDING_A_CAPABILITY.md](ADDING_A_CAPABILITY.md) — add a new MCP tool / domain skill
- [ADDING_A_PROVIDER.md](ADDING_A_PROVIDER.md) — add a new NIM or model provider
- [ADDING_AN_AGENT_OR_SKILL.md](ADDING_AN_AGENT_OR_SKILL.md) — add a new agent or skill
- [EVALUATION.md](EVALUATION.md) — run counterfactual evaluation
