# Multi-Agent Intelligent Warehouse (MAIW)

**An NVIDIA AI Blueprint for governed, agentic warehouse operations.**

Powered by NVIDIA Nemotron, MCP, SOP-driven agents, and pluggable agent runtimes.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.120+-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19+-61dafb.svg)](https://reactjs.org/)
[![NVIDIA NIMs](https://img.shields.io/badge/NVIDIA-NIMs-76B900.svg)](https://www.nvidia.com/en-us/ai-data-science/nim/)

---

## What MAIW Is

**MAIW — Multi-Agent Intelligent Warehouse — is an operational AI architecture for reasoning about, governing, and acting on dynamic warehouse systems.**

MAIW is designed around a single question:

> **What does it take for AI to participate safely in running a warehouse — not simply answer questions about one?**

Warehouse operations are continuously changing. Workers move between tasks, equipment fails, inventory changes, orders arrive, waves approach carrier cutoffs, and the state observed when reasoning begins may no longer be valid when an action is ready to execute.

MAIW addresses this by separating intelligence from operational authority.

---

## Why This Architecture

Warehouse AI is different from general AI deployment:

- **State is physical and consequential.** A reassigned forklift or a reprioritized wave is not reversible the way a text generation is.
- **Timing matters operationally.** The state observed when reasoning begins may no longer be valid when an action executes.
- **Authority is human, not model.** Consequential warehouse actions require explicit human approval — not implicit LLM confidence.
- **Traceability is non-negotiable.** Every recommendation, decision, approval, and outcome must be auditable end to end.

This drives the core architectural principle:

> **AI may be adaptive in how it reasons, but operational authority remains explicit, deterministic, and auditable.**

---

## Core Lifecycle

```
Observe → Reason → Recommend → Govern → Approve → Execute → Observe Outcome
```

| Stage | What Happens |
|-------|-------------|
| **Observe** | `WarehouseState` assembled across inventory, labor, equipment, and wave domains |
| **Reason** | SOP-driven agent reasons over operational context; `ModelGateway` selects the appropriate Nemotron model |
| **Recommend** | Agent emits a typed `RecommendedAction` — semantic intent, not write parameters |
| **Govern** | `DecisionEngine` evaluates the proposal against deterministic policy, risk, and invariants |
| **Approve** | Where required, human authority approves — explicit, expirable, single-use |
| **Execute** | `ActionExecutor` crosses the execution boundary; MCP write capability is invoked |
| **Observe Outcome** | Post-execution state is read; outcome is classified as `CONFIRMED_EXECUTED` / `CONFIRMED_NOT_EXECUTED` / `INDETERMINATE` |

---

## Canonical Architecture

![MAIW Runtime Pipeline](docs/architecture/diagrams/maiw-runtime-pipeline.png)

The diagram expresses: **Operator/Human Authority** → **MAIW Copilot** → **MAIW Agent Runtime** (AgentDefinition / SOP / TaskState) → **Deterministic Runtime** and **Deep Agents Runtime** → canonical agents → **Warehouse World** + **ModelGateway** → **RecommendedAction** → **MAIW Authority Boundary** → **ActionProposal** → **DecisionEngine** → **Human Approval** → **ActionExecutor** → **MCP Interoperability Layer** → **Warehouse Systems** → **Observability & Trace** → **LIVE World & Outcome** → **Closed-Loop Outcome Observation**.

See [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) for the full architecture document.

---

## Warehouse World

MAIW ships with a deterministic synthetic warehouse environment used for development, demo, and evaluation. The canonical generation path is:

```
WarehouseWorldConfig
    ↓
WarehouseWorldGenerator  (deterministic, seed-based)
    ↓
Canonical Operational Graph
    ↓
WarehouseDataPack  (immutable, on-disk, verifiable)
    ↓
ScenarioOverlay  (disruption events)
    ↓
ScenarioWorld  (base + overlay, immutable view)
    ↓
DemoWarehouseWorld  (mutable runtime execution world)
    ↓
Simulation Providers
    ↓
WarehouseStateProvider → WarehouseState → Agents
```

### Three-State Distinction

| Layer | Description |
|-------|-------------|
| **BASE (DataPack)** | Immutable, on-disk, checksummed artifact. Never mutated by a demo run. Identified by `dataset_id + warehouse_id + seed`. |
| **SCENARIO (ScenarioWorld)** | Immutable view: DataPack base graph + deterministic event overlay. Validates entity references at construction. Does not modify the DataPack. |
| **LIVE (DemoWarehouseWorld)** | Mutable runtime execution world. Derived from DataPack + ScenarioOverlay. Reset reconstructs from immutable sources — not from a snapshot. |

```
DataPack           = what the warehouse is
ScenarioWorld      = what happened to it
DemoWarehouseWorld = what MAIW is currently operating on
```

### OperationalContextSnapshot

Each Copilot turn that reaches a model produces one `OperationalContextSnapshot`. It is captured **before** the model call — not reconstructed afterward. It is:

- Linked to the turn via `turn_id`, `trace_id`, and `context_snapshot_id`
- Linked to the DataPack via `datapack_checksum` (the same immutable `semantic_checksum`)
- Immutable after capture — LIVE mutations do not change historical snapshots
- Inspectable in the WORLD / CONTEXT tab or via `GET /api/v1/world/context/by-turn/{turn_id}`

`OperationalContextSnapshot` is a first-class concept in MAIW. It provides: exact bounded context for agent reasoning, provenance tracing back to the immutable DataPack, and reproducibility and historical inspection — the exact context the model saw is preserved, regardless of subsequent warehouse mutations.

See [docs/architecture/WAREHOUSE_WORLD.md](docs/architecture/WAREHOUSE_WORLD.md) and [docs/developer/WAREHOUSE_WORLD_MODEL.md](docs/developer/WAREHOUSE_WORLD_MODEL.md).

---

## Agents, SOPs, and Skills

### What an Agent Is

An agent is a **bounded operational role** — not a general-purpose autonomous entity:

| Dimension | Description |
|-----------|-------------|
| **AgentDefinition** | Declares identity: `agent_id`, `version`, `domain`, `objective`, allowed capabilities, `TerminationPolicy`. MAIW-owned. |
| **SOPDefinition** | A versioned, machine-readable Standard Operating Procedure: steps, allowed capabilities, allowed subagents, stop conditions, escalation rules, runtime profile. MAIW-owned. |
| **AgentTaskState** | Tracks one execution of one SOP: `task_id`, current step, completed steps, context snapshot, delegation results, governance state, stop reason. |

Agents execute SOPs. SOPs do not own agents. An SOP defines the policy envelope; the agent runtime decides how to navigate within it.

### Canonical Agents

| Agent | Domain | Package |
|-------|--------|---------|
| `OperationsCoordinationAgent` | Cross-domain coordination | `packages/maiw-agents/maiw_agents/operations/` |
| `LaborAgent` | Labor capacity and allocation | `packages/maiw-agents/maiw_agents/labor/` |
| `WaveAgent` | Wave prioritization and risk | `packages/maiw-agents/maiw_agents/wave/` |
| `EquipmentAgent` | Equipment status and assignment | `packages/maiw-agents/maiw_agents/equipment/` |
| `SafetyAgent` | Safety incident and compliance | `packages/maiw-agents/maiw_agents/safety/` |

### Agent vs. Skill

| | Agent | Skill |
|-|-------|-------|
| **Has a goal?** | Yes — SOP objective | No — executes one bounded capability |
| **Has state?** | Yes — AgentTaskState | No — stateless |
| **Has a lifecycle?** | Yes — SOP steps, stop conditions | No |
| **Can delegate?** | Yes — to subagents (SOPs govern) | No |
| **Governance?** | Yes — must emit RecommendedAction | Capability class constrains use |

### Skill Capability Classes

| Class | Description | Direct Write? |
|-------|-------------|---------------|
| `READ` | Reads operational state via MCP | No |
| `ANALYTICAL` | Computes metrics and assessments | No |
| `PROPOSAL` | Builds typed `ActionProposal` | No |
| `WRITE` | Invokes MCP write capability | Structurally blocked from agent runtime |
| `EMERGENCY_WRITE` | Bypasses standard policy gating | Structurally blocked from agent runtime |

`WRITE` and `EMERGENCY_WRITE` are **structurally blocked** from the agent runtime. They can only be invoked by `ActionExecutor` after a full governance pass.

---

## Runtime Architecture

MAIW provides two runtimes behind the `AgentRuntime` protocol:

### MAIWDeterministicRuntime (strict mode)

- Executes SOP steps in exact declared order
- No LLM nondeterminism — same inputs always produce the same output
- Used for CI/CD pipelines, safety-sensitive procedural checks, and degraded-mode fallback
- No external dependencies beyond MAIW packages

### DeepAgentsRuntime (adaptive mode)

- Adaptive reasoning within the SOP policy envelope
- Uses ReAct-style tool/subagent scheduling via `deepagents==0.7.15`
- MAIW supplies: system prompt, tools (READ/ANALYTICAL only), subagent specs, SOP envelope
- Deep Agents provides: the runtime loop, tool selection, intermediate context management
- All model calls route through `MAIWModelGatewayChat` — never directly to a provider
- Does NOT own governance, SOPs, task state, or execution authority

```yaml
runtime_profile: strict    # → MAIWDeterministicRuntime
runtime_profile: adaptive  # → DeepAgentsRuntime
```

**The dual-runtime architecture is intentional design.** It provides a clean separation between deterministic compliance and adaptive reasoning. `MAIWDeterministicRuntime` is the reference and strict-mode fallback; `DeepAgentsRuntime` is the primary adaptive runtime for complex resolution SOPs.

See [docs/architecture/AGENT_RUNTIME.md](docs/architecture/AGENT_RUNTIME.md).

---

## ModelGateway

All model calls — from both runtimes — pass through a single `ModelGateway` chain:

```
AgentRuntime
    ↓
ModelGateway
    ↓
PolicyFilter  (hard eligibility gate: risk × reasoning × deployment)
    ↓
ModelRouter   (deterministic rule-based model selection)
    ↓
Deployment Resolver  (NVIDIA_HOSTED / LOCAL_NIM / OPENAI_COMPATIBLE / ENTERPRISE)
    ↓
NVIDIA NIM / Hosted / Local
```

Agents express **what level of reasoning a decision requires** (via `ReasoningLevel`). `ModelGateway` selects the physical model. Agents never reference model IDs directly.

Nemotron model roles: `lightning` (fast, low-risk), `nano` (local NIM), `super` (default), `ultra` (opt-in for highest complexity).

See [docs/architecture/MODEL_GATEWAY.md](docs/architecture/MODEL_GATEWAY.md).

---

## Governance and Authority Boundary

```
Agent (either runtime)
    → RecommendedAction
    → WAITING_FOR_GOVERNANCE
──────── MAIW AUTHORITY BOUNDARY ────────
ActionProposal  (typed, immutable)
    ↓
DecisionEngine  (synchronous, no I/O, deterministic)
    → APPROVED / REJECTED / DEFERRED
    ↓
Human Approval  (where required — explicit, expirable, single-use)
    ↓
ActionExecutor  (6-guard pattern before any MCP write)
    ↓
MCP Interoperability Layer
    ↓
Warehouse Systems
```

**`RecommendedAction` lives ABOVE the authority boundary** — it is agent output, semantic intent, not a write command.

**`ActionProposal` lives BELOW the authority boundary** — it is a governed operational artifact with explicit target, risk, and trace identity.

The invariant is non-negotiable:

> **The LLM never touches a write path directly.**

AI recommends and proposes. The `DecisionEngine` governs. Human authority approves where required. `ActionExecutor` executes.

`DecisionEngine` is synchronous, performs no I/O, and cannot be overridden by a model-generated argument. `ActionExecutor` checks six guards in order: (1) decision outcome is `APPROVED`, (2) decision binds to the exact proposal ID, (3) action name is in the static allowlist, (4) the decision is not stale, (5) domain-specific additional guards (e.g. state-drift check), (6) request deadline not expired immediately before write.

See [docs/architecture/GOVERNANCE.md](docs/architecture/GOVERNANCE.md) and [docs/architecture/DECISION_ENGINE.md](docs/architecture/DECISION_ENGINE.md).

---

## MCP Interoperability Layer

MAIW uses the **official MCP Python SDK** (`mcp 2.0.0`, protocol `2026-07-28`).

```
Skill
    ↓
MAIWMCPClient.invoke("warehouse.inventory.get", payload)
    ↓
CapabilityRegistry.resolve()  →  server URL
    ↓
mcp.client.Client(server_url)     ← official MCP v2 Client
    ↓
client.call_tool("warehouse.inventory.get", payload)
    ↓
[MCP 2026-07-28 over Streamable HTTP]
    ↓
MCPServer (mcp.server.MCPServer)
    ↓
Warehouse Backend
```

**MCP is the interoperability layer, not the authority layer.** MCP capabilities are not exposed to the LLM's tool registry. The LLM produces a `RecommendedAction`; `ActionExecutor` translates a governed `ActionProposal` into an MCP call.

`MAIWMCPClient` wraps `mcp.client.Client`. Servers use `mcp.server.MCPServer`. Transport: Streamable HTTP (stateless, no session affinity required). Test transport: in-memory via `CapabilityRegistry`.

See [docs/architecture/MCP.md](docs/architecture/MCP.md).

---

## Reliability and Closed-Loop Outcome Observation

MAIW treats distributed-systems uncertainty as a first-class concern.

When a write may have succeeded but its acknowledgement is lost, MAIW does **not** blindly retry:

```
UNKNOWN → suppress automatic retry → reread authoritative state → reconcile
    ↓
CONFIRMED_EXECUTED | CONFIRMED_NOT_EXECUTED | INDETERMINATE
```

The reliability infrastructure includes:

| Concern | Mechanism |
|---------|-----------|
| Ambiguous writes | `AmbiguousWriteError` → `UNKNOWN` outcome — never auto-retried |
| Execution identity | `execution_id` generated before write, propagated through MCP |
| Idempotency | `ExecutionRegistry` — same idempotency key cannot produce multiple mutations |
| Reconciliation | `ReconciliationService` with capability-specific postcondition strategies |
| Request deadlines | Hierarchy at API boundary — analyze / execution / reconciliation / startup budgets |
| Circuit breakers | `DomainCircuitRegistry` — per-domain isolation; NIM circuit independent of MCP circuits |
| Fault injection | Deterministic fault framework (F01–F16 profiles) — test/demo only, never in production |

Every operational interaction is traceable through:

```
Evidence → Agent Interpretation → Skills → RecommendedAction → ActionProposal
    → Decision → Approval → Execution → Outcome
```

**MAIW implements Closed-Loop Outcome Observation.** The system observes whether the intended operational outcome occurred: Did backlog fall? Did wave risk improve? Did throughput recover? Outcome observation closes the operational loop — it does not imply autonomous learning or self-modification.

---

## MAIW Copilot

MAIW Copilot is the conversational interaction layer over the governed lifecycle. Operators ask natural-language questions, receive evidence-grounded analysis with ranked recommendations, and initiate governed warehouse actions — all through a single endpoint (`POST /api/v1/copilot/turn`).

### Four Intents, One Endpoint

| Intent | What it does |
|--------|-------------|
| **ASK** | Graph-grounded answer about current warehouse state. Returns evidence facts and Operational Graph neighborhood context. No proposal, no execution. |
| **ANALYZE** | Deterministic severity assessment + ranked `RecommendedAction` list. Severity is computed before the LLM call; recommendations route through the standard governance pipeline when acted upon. |
| **ACT** | Converts the selected recommendation into a governed `ActionProposal`, evaluates it through `DecisionEngine`, and either executes (if approved autonomously) or queues for human approval. |
| **OBSERVE_OUTCOME** | Post-execution outcome observation. Compares pre- and post-execution state to determine whether the intended operational objective was achieved. |

Copilot never bypasses `DecisionEngine`, human approval, or `ActionExecutor`. The trust boundary is enforced architecturally: `CopilotService` cannot import `ActionExecutor`, `ApprovalStore`, or `DecisionEngine` — only `GovernedActionOrchestrator` crosses that boundary, and only after a full policy evaluation.

---

## Model Gateway Evaluation Lab

The **Model Gateway Evaluation Lab** (at `/models/lab`) is a read-only developer tool for inspecting pre-computed model evaluation artifacts. It provides:

- Multi-model comparison across fixed evaluation benchmarks
- Deterministic graders (not LLM judges)
- Router assessment with routing provenance (`requested_role`, `selected_role`, `fallback_from`)
- Evidence for model selection decisions (insufficient evidence → retain current router)

The Lab is **not** a production adaptive router. It is fixed-context, artifact-backed, and read-only. Artifact paths are whitelisted; no path traversal; no write capability.

See [docs/developer/MODEL_GATEWAY_EVALUATION.md](docs/developer/MODEL_GATEWAY_EVALUATION.md).

---

## Architecture Ownership

| Layer | Owns |
|-------|------|
| **MAIW** | Warehouse semantics, SOPs, task state, permissions, governance, execution, outcome |
| **Deep Agents** | Adaptive runtime loop, tool/subagent scheduling, working context |
| **ModelGateway** | Model access, eligibility, routing, deployment |
| **MCP** | Standardized interoperability |
| **WMS / WES / etc.** | Operational systems of record |

---

## What MAIW Is NOT

| What people might expect | What MAIW actually is |
|--------------------------|----------------------|
| A WMS replacement | An intelligence and governance layer above warehouse systems |
| A WES replacement | An agent orchestration framework that integrates with execution systems |
| A generic chatbot | A governed operational intelligence architecture with SOP-driven agents |
| A generic agent framework | A warehouse-specific framework with typed contracts, SOPs, and execution governance |
| Direct LLM-to-tool execution | Governed: LLM → RecommendedAction → DecisionEngine → ActionExecutor → MCP |
| An MCP orchestration layer | MCP is the interoperability layer; MAIW is the governance and semantic layer above it |
| A replacement for enterprise warehouse systems | A complement that adds reasoning, governance, and outcome observation to existing systems |

---

## Quickstart

### Prerequisites

- Python 3.11+
- Node.js 20+
- NVIDIA API key (`nvapi-...`) from [build.nvidia.com](https://build.nvidia.com/)
- Git

### Steps

```bash
# 1. Clone
git clone https://github.com/NVIDIA-AI-Blueprints/Multi-Agent-Intelligent-Warehouse.git
cd Multi-Agent-Intelligent-Warehouse

# 2. Install all MAIW packages (editable)
pip install -e packages/maiw-contracts -e packages/maiw-mcp -e packages/maiw-state \
    -e packages/maiw-models -e packages/maiw-skills -e packages/maiw-decision \
    -e packages/maiw-execution -e packages/maiw-agents -e packages/maiw-world \
    -e apps/api

# 3. Configure model endpoint
cp .env.example .env
# Set NVIDIA_API_KEY=nvapi-...
# For local NIM: set MAIW_NIM_BASE_URL and MAIW_NIM_MODEL

# 4. Generate Warehouse World (DataPack)
python -m maiw_world dc47_demo --output data/worlds/

# 5. Start backend
MAIW_DEMO_MODE=true uvicorn maiw_api.app:app --reload --port 8000

# 6. Start frontend
cd src/ui/web && npm install && npm run dev
# Runs at http://localhost:3000

# 7. Open WORLD tab → inspect DataPack, Operational Graph, LIVE state
# 8. Activate Wave 17 scenario → observe SCENARIO layer
# 9. Ask Copilot: "What is the current wave risk?" (ASK intent)
# 10. Ask Copilot: "What should I do about the labor shortage?" (ANALYZE intent)
# 11. Inspect OperationalContextSnapshot in WORLD → CONTEXT tab
# 12. Run SOP-driven agent: OperationsCoordinationAgent → wave_risk_resolution SOP
# 13. Review RecommendedAction — semantic intent above the authority boundary
# 14. Execute governed action: Copilot ACT or POST /api/v1/demo/approve
# 15. Observe LIVE outcome in WORLD → LIVE tab
# 16. Ask Copilot: "Did the intervention work?" (OBSERVE_OUTCOME intent)
# 17. Open Model Gateway Lab at http://localhost:3000/models/lab
```

> **Demo Mode** (`MAIW_DEMO_MODE=true`) does not require PostgreSQL, Redis, Milvus, or Kafka. Only `NVIDIA_API_KEY` is needed.

---

## Developer Notebook / Brev

The canonical developer journey is available as a Jupyter notebook:

```
notebooks/MAIW_v2_Getting_Started.ipynb
```

This notebook walks through the full 17-step journey — from environment validation through Warehouse World generation, scenario activation, Copilot interaction, SOP-driven agent execution, governance, outcome observation, and the Model Gateway Evaluation Lab.

For hosted deployment on Brev, see the Brev Launchable configuration in `deploy/brev/`.

---

## Environment Configuration

### Required

| Variable | Required for | Description |
|----------|-------------|-------------|
| `NVIDIA_API_KEY` | All modes | NVIDIA API key (`nvapi-...`), from [build.nvidia.com](https://build.nvidia.com/) |
| `POSTGRES_PASSWORD` | Full-stack only | PostgreSQL password — **not required for Demo Mode** |
| `JWT_SECRET_KEY` | Full-stack only | JWT signing secret (min 32 chars) — **not required for Demo Mode** |

> **Demo Mode (`MAIW_DEMO_MODE=true`) does not require PostgreSQL, Redis, Milvus, or Kafka.**

### Model Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_NIM_URL` | `https://integrate.api.nvidia.com/v1` | NIM inference endpoint |
| `LLM_MODEL` | `nvidia/nemotron-3-super-120b-a12b` | Default model ID |
| `MAIW_MODEL_LIGHTNING` | `nvidia/nemotron-3.5-lightning-30b-a3b` | Lightning role override |
| `MAIW_MODEL_NANO` | `nvidia/nemotron-3-nano-30b-a3b` | Nano role override |
| `MAIW_MODEL_SUPER` | `nvidia/nemotron-3-super-120b-a12b` | Super role override |
| `MAIW_MODEL_ULTRA` | `nvidia/nemotron-3-ultra-550b-a55b` | Ultra role override (opt-in) |

### Infrastructure (Full-stack only)

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | `localhost` | PostgreSQL host |
| `DB_PORT` | `5435` | PostgreSQL port |
| `REDIS_HOST` | `localhost` | Redis host |
| `MILVUS_HOST` | `localhost` | Milvus vector DB host |

---

## Architecture Invariants

These invariants are enforced by the test suite and must not be broken:

| Invariant | Enforcement |
|-----------|------------|
| LLM cannot call MCP write tools directly | No MCP write tool in any agent tool registry |
| Proposals are built locally, never via MCP | `ActionProposal` factories have no MCP client |
| `DecisionEngine` is synchronous, no I/O | `evaluate()` has no `await`, no client dependencies |
| Only `ActionExecutor.execute()` reaches MCP writes | Single call-site per domain executor |
| Action names are statically allowlisted | `_ALLOWED_ACTIONS` is a `frozenset` literal |
| No canonical package imports from `src.*` | AST scanner in `test_package_imports.py` |
| `UNKNOWN` outcome is never auto-retried | `ExecutionRegistry.mark_unknown()` blocks subsequent attempts |
| Post-mutation timeout produces `UNKNOWN`, not `FAILED` | `AmbiguousWriteError` → distinct outcome path in `BaseActionExecutor` |
| Same idempotency key cannot produce multiple mutations | `ExecutionRegistry` capability:key compound dedup |
| `execution_id` generated before write, propagated through MCP | `BaseActionExecutor.execute()` generates UUID pre-write |
| One circuit breaker per domain | `DomainCircuitRegistry`: equipment/labor/wave/inventory circuits are independent |
| NIM circuit breaker independent of MCP domain circuits | `ModelGateway` has its own `nim_circuit` |
| Fault injection lives only in test/demo infrastructure | Production packages contain zero `fault_id` checks or `FaultProfile` references |

---

## Testing

MAIW uses a three-tier test structure. **CORE CI** requires no running services:

```bash
python -m pytest tests/unit/ tests/contract/ tests/mcp/ \
  --ignore=tests/unit/test_all_agents.py \
  --ignore=tests/unit/test_basic.py \
  --ignore=tests/unit/test_nvidia_llm.py \
  --ignore=tests/unit/test_caching_demo.py \
  --ignore=tests/unit/test_response_quality_demo.py \
  --ignore=tests/unit/test_mcp_integrated_planner_graph.py \
  --ignore=tests/unit/test_chunking_demo.py \
  --ignore=tests/unit/test_db_connection.py \
  --ignore=tests/unit/test_enhanced_retrieval.py \
  --ignore=tests/unit/test_evidence_scoring_demo.py \
  --ignore=tests/unit/test_mcp_system.py \
  --ignore=tests/unit/test_guardrails.py \
  --ignore=tests/unit/test_guardrails_sdk.py \
  --ignore=tests/unit/test_mcp_planner_integration.py \
  --ignore=tests/unit/test_nvidia_integration.py \
  --ignore=tests/unit/test_document_action_tools.py \
  --ignore=tests/unit/test_document_pipeline.py \
  --ignore=tests/unit/test_embedding.py \
  --ignore=tests/unit/test_reasoning_evaluation.py \
  --ignore=tests/unit/test_prompt_injection_protection.py \
  --ignore=tests/unit/test_prompt_injection_simple.py
```

**MAIW v2 test baseline: ~1600 Python unit tests (+ 388 reliability tests + 94 frontend tests)**

| Test tier | Command | Requires |
|-----------|---------|---------|
| CORE CI | Command above | Python packages only |
| Integration | `pytest tests/integration/` | Running MAIW server + PostgreSQL |
| External service | Set `NVIDIA_API_KEY`, remove `--ignore` flags | NVIDIA API key + NIM endpoint |

See [docs/architecture/TEST_STRATEGY.md](docs/architecture/TEST_STRATEGY.md) for per-file exclusion rationale.

---

## Counterfactual Evaluation (SIMULATED)

Two warehouse worlds (same scenario, same seed) were advanced through the same disruption timeline. The control world received no MAIW intervention; the MAIW world executed governed actions through the standard pipeline.

> **These results are SIMULATED in MAIW's deterministic synthetic warehouse environment. They are not measurements from a production warehouse.**

| Metric | Control | MAIW |
|--------|---------|------|
| Time to recovery | not reached | 300s (5 sim-min) |
| Backlog AUC reduction | — | −92% |
| Wave-risk exposure reduction | — | −86.7% |
| MAIW governance cycles | 0 | 6 |

Reproduce with:

```bash
MAIW_DEMO_MODE=true uvicorn maiw_api.app:app --port 8000
python scripts/counterfactual_eval.py   # generates artifacts/demo/labor_wave_control_vs_maiw.*
python scripts/trace_capture.py          # generates artifacts/demo/labor_constraint_wave_risk_trace.*
```

---

## Repository Structure

```
.
├─ packages/               # Canonical Python packages
│  ├─ maiw-contracts/      # Shared contracts (ActionProposal, governance types)
│  ├─ maiw-mcp/            # MCP client, capability registry, circuit breakers
│  ├─ maiw-state/          # WarehouseState, domain state models
│  ├─ maiw-decision/       # DecisionEngine — APPROVED/REJECTED/DEFERRED
│  ├─ maiw-models/         # ModelGateway, NIM provider, PolicyFilter, ModelRouter
│  ├─ maiw-skills/         # Inventory, Equipment, Labor, Wave skills
│  ├─ maiw-execution/      # BaseActionExecutor (6-guard pattern), domain executors
│  ├─ maiw-agents/         # Equipment, Labor, Wave, Operations, Safety agents
│  └─ maiw-world/          # Warehouse World — DataPack, ScenarioOverlay, Explorer
├─ apps/api/               # FastAPI application (bootstrap.py, MAIWRuntime)
├─ mcp_servers/            # Standalone MCP v2 servers (Inventory, Equipment, Labor, Wave)
├─ src/ui/web/             # React web dashboard
├─ notebooks/              # Developer notebook (MAIW_v2_Getting_Started.ipynb)
├─ artifacts/              # Evaluation artifacts (reliability, model lab, counterfactual)
├─ data/                   # Generated world DataPacks (data/worlds/<dataset_id>/)
├─ deploy/                 # Docker Compose, Helm, Brev configurations
├─ scripts/                # Utility scripts (counterfactual eval, model scripts, data gen)
├─ tests/                  # Test suite (unit, contract, mcp, integration, reliability)
└─ docs/                   # Documentation
   ├─ architecture/        # Architecture docs and diagrams
   ├─ developer/           # Developer reference docs
   └─ GLOSSARY.md          # Canonical terminology glossary
```

---

## Developer Documentation

| Document | Description |
|----------|------------|
| [docs/architecture/ARCHITECTURE.md](docs/architecture/ARCHITECTURE.md) | Full architecture document |
| [docs/architecture/AGENT_RUNTIME.md](docs/architecture/AGENT_RUNTIME.md) | Agent runtime (deterministic vs. adaptive) |
| [docs/architecture/GOVERNANCE.md](docs/architecture/GOVERNANCE.md) | Authority boundary, DecisionEngine, approval lifecycle |
| [docs/architecture/MODEL_GATEWAY.md](docs/architecture/MODEL_GATEWAY.md) | ModelGateway chain, Nemotron roles, routing policy |
| [docs/architecture/MCP.md](docs/architecture/MCP.md) | MCP SDK, protocol version, deployment |
| [docs/architecture/WAREHOUSE_WORLD.md](docs/architecture/WAREHOUSE_WORLD.md) | Warehouse World layers, OperationalContextSnapshot |
| [docs/architecture/DECISION_ENGINE.md](docs/architecture/DECISION_ENGINE.md) | Constraint rules, outcome model |
| [docs/architecture/CAPABILITY_MATRIX.md](docs/architecture/CAPABILITY_MATRIX.md) | All 13 capabilities, read/write classification |
| [docs/architecture/DEPENDENCY_BOUNDARIES.md](docs/architecture/DEPENDENCY_BOUNDARIES.md) | Package boundary rules |
| [docs/architecture/RUNTIME_EXECUTION_FLOW.md](docs/architecture/RUNTIME_EXECUTION_FLOW.md) | Full pipeline sequence diagrams |
| [docs/architecture/TEST_STRATEGY.md](docs/architecture/TEST_STRATEGY.md) | CORE CI command, exclusion rationale |
| [docs/developer/WAREHOUSE_WORLD_MODEL.md](docs/developer/WAREHOUSE_WORLD_MODEL.md) | Warehouse World developer reference |
| [docs/developer/MODEL_DEPLOYMENT.md](docs/developer/MODEL_DEPLOYMENT.md) | Model deployment modes — hosted, local NIM |
| [docs/developer/MODEL_GATEWAY_EVALUATION.md](docs/developer/MODEL_GATEWAY_EVALUATION.md) | Model Gateway Lab artifacts and evaluation methodology |
| [docs/GLOSSARY.md](docs/GLOSSARY.md) | Canonical terminology glossary |

---

## Contributing

1. Fork the repository and create a feature branch.
2. All changes must keep CORE CI green: current baseline ~1600 Python tests + 94 frontend tests.
3. New canonical code goes in `packages/`, never in `src.*` for business logic.
4. No `src.*` imports in any `packages/` code — enforced by the test suite.
5. Commit messages must follow [Conventional Commits](https://www.conventionalcommits.org/).

---

## License

Apache License 2.0. See [LICENSE](LICENSE) for full text.

Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
