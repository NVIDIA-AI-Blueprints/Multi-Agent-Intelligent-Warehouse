# MAIW Glossary — Canonical Terminology

> This glossary defines terms as used in MAIW v2. Use these definitions consistently
> in code, docs, SOPs, tests, and conversations to avoid ambiguity.

---

## Core Concepts

**MAIW (Multi-Agent Intelligent Warehouse)**
: The NVIDIA AI Blueprint for agentic warehouse operations. MAIW owns warehouse
  semantics, operational authority, SOP definitions, governance, and execution contracts.

**Warehouse World**
: The deterministic warehouse simulation used for development and demo. Three states:
  BASE (immutable DataPack from generator), SCENARIO (scenario overlay on BASE),
  LIVE (runtime-mutable state). See `docs/developer/WAREHOUSE_WORLD_MODEL.md`.

**WarehouseDataPack**
: The immutable, on-disk, checksummed artifact produced by `WarehouseWorldGenerator`.
  Contains the canonical graph of all entities and relationships. Never modified after generation.

**OperationalContextSnapshot**
: A point-in-time, immutable snapshot of warehouse state assembled before a model call.
  Identified by `snapshot_id`. Used to anchor agent reasoning to a specific moment.
  Historical snapshots are never overwritten by LIVE state changes.

**WarehouseState**
: The current runtime view of warehouse entities (workers, equipment, tasks, waves, orders).
  Assembled from DataPack + scenario overlay + LIVE events.

**AgentDefinition**
: Declares an agent's identity: `agent_id`, `version`, `domain`, `objective`,
  allowed capabilities, `TerminationPolicy`. MAIW-owned.

**SOPDefinition**
: A versioned, YAML-declared Standard Operating Procedure. Defines: `id`, `version`,
  steps, `allowed_capabilities`, `allowed_subagents`, `stop_conditions`, `escalation` rules,
  `runtime_profile`. MAIW-owned. Agents execute SOPs; SOPs do not own agents.

**AgentTaskState**
: Tracks one agent's execution of one SOP: `task_id`, `agent_id`, `sop_id`, `sop_version`,
  current step, completed steps, iteration count, `context_snapshot_id`, delegation results,
  `recommendation_id`, governance state, `stop_reason`.

**AgentRuntime**
: The protocol (interface) that all runtimes implement. Two implementations:
  `MAIWDeterministicRuntime` and `DeepAgentsRuntime`.

**MAIWDeterministicRuntime**
: Reference runtime. Executes SOP steps in exact order. Used for CI, testing, degraded mode.
  Does NOT adapt, select tools, or delegate.

**DeepAgentsRuntime**
: Adaptive runtime backed by `deepagents==0.7.15`. Uses ReAct-style reasoning.
  MAIW supplies system prompt, tools, subagent specs. Deep Agents provides the runtime loop.

**Skill**
: A bounded, stateless capability class. Has no independent goal, state machine, or delegation.
  Types: READ, ANALYTICAL, PROPOSAL, WRITE, EMERGENCY_WRITE.
  Deep Agents receives only READ/ANALYTICAL tools.

**Agent (vs. Skill)**
: An agent has: an operational objective, SOP, task state, ability to use multiple skills,
  ability to delegate to subagents, escalation logic, and termination policy.
  A skill has none of these.

**RecommendedAction**
: The output of a successful SOP execution. Carries domain, capability, target, objective,
  rationale, priority. Does NOT specify MCP parameters — only semantic intent.

**ActionProposal**
: A concrete, parameterized proposal for an action. Created by WRITE skills or the
  `GovernedActionOrchestrator` from a `RecommendedAction`. Flows to `DecisionEngine`.

---

## Governance

**MAIW Authority Boundary**
: The architectural divide between reasoning (above) and execution (below).
  No agent or copilot may cross this boundary autonomously.
  ```
  Agents → RecommendedAction → GovernedActionOrchestrator
  ─────────────── MAIW AUTHORITY BOUNDARY ────────────────
  ActionProposal → DecisionEngine → Human Approval → ActionExecutor → MCP → LIVE
  ```

**DecisionEngine**
: Synchronous, deterministic evaluator. Takes `DecisionRequest` → `APPROVED / REJECTED / DEFERRED`.
  Never LLM-evaluated. Policy rules are Python, not prompts.

**ApprovalStore**
: Single-use approval state machine: PENDING → APPROVED/REJECTED/EXPIRED → CONSUMED.

**ActionExecutor**
: Executes an approved `ActionProposal` by calling write MCP capabilities.
  Only invoked after a governance approval.

**GovernedActionOrchestrator**
: Coordinates the full proposal → decision → approval → execution chain.
  Injected into `CopilotService` at bootstrap; never directly exposed to agents.

---

## ModelGateway

**ModelGateway**
: The only inference boundary. All model calls go through ModelGateway. Agents never
  hold direct provider clients.

**PolicyFilter**
: Hard eligibility gate before routing. Checks risk level, reasoning level, deployment mode.

**ModelRouter**
: Deterministic rule-based model selector. Risk + reasoning level → model role → deployment.

**DeploymentMode**
: LOCAL_NIM | HOSTED | LOCAL_FALLBACK. Selected by env config, not by agents.

**ModelGateway Evaluation Lab**
: Read-only developer tool at `/models/lab`. Inspects pre-computed evaluation artifacts.
  Cannot create proposals, invoke DecisionEngine, or call write MCP.

---

## MCP

**MCP (Model Context Protocol)**
: Standardized interoperability protocol. MAIW uses the official `mcp` Python SDK.
  MCP has no governance authority — it is the execution transport only.

**MAIWMCPClient**
: Thin MAIW wrapper around the official MCP client. No custom JSON-RPC or session logic.

**maiw-mcp**
: MAIW's MCP capability implementations. Thin — domain contracts live in `maiw-contracts`.

**maiw-contracts**
: Domain contract types (equipment, labor, wave, inventory). Shared between MCP servers
  and execution layer. Does not own governance logic.

---

## Observability

**trace_id**
: Unique identifier for one Copilot turn or agent task execution. Correlates all
  observations, model calls, and governance events in a single reasoning chain.

**conversation_id / turn_id**
: Copilot conversation and turn identifiers. Separate from trace_id but linked.

**context_snapshot_id**
: Identifies the `OperationalContextSnapshot` used for a specific model call.

**runtime_provenance**
: Record of which runtime, version, SOP, model route, and iteration count produced
  a given `AgentTaskResult`.

---

## Copilot

**CopilotService**
: Handles ASK / ANALYZE / ACT / OBSERVE_OUTCOME intents. MUST NOT import `ActionExecutor`,
  `ApprovalStore`, or `DecisionEngine`. Delegates ACT to `GovernedActionOrchestrator`.

**CopilotIntent**
: Four intents over a single endpoint (`POST /api/v1/copilot/turn`):
  - `ASK` — graph-grounded question answering; no proposal, no execution
  - `ANALYZE` — deterministic severity assessment + ranked `RecommendedAction` list
  - `ACT` — governed action trigger: `ActionProposal` → `DecisionEngine` → approval / execution
  - `OBSERVE_OUTCOME` — post-execution outcome observation; compares pre/post state

---

## Warehouse Domains

**Wave**
: A batch of pick tasks grouped for carrier fulfillment. Has a `carrier_cutoff` deadline.

**Worker (Labor)**
: A warehouse worker with zone, skill, shift, and task assignment state.

**Equipment**
: A physical asset (forklift, scanner, conveyor). Has operational status and zone assignment.

**Order / Task**
: An order is a customer request. A task is a discrete pick/pack/move operation
  within a wave, assigned to workers.

---

## Testing and CI

**Architecture invariant test**
: A test that enforces a structural property of the MAIW architecture (e.g., CopilotService
  does not import ActionExecutor; Deep Agents only receives READ/ANALYTICAL tools).
  These tests live in `tests/unit/test_architecture_invariants.py` and related files.

**PRE-V2 LEGACY (skip label)**
: Tests marked with this label depend on pre-v2 import chains (asyncpg, old MCP stack)
  that are not part of the MAIW v2 architecture. They are preserved for reference.

---

## Outcome Terminology

**Closed-Loop Outcome Observation**
: MAIW's mechanism for observing whether the intended operational outcome occurred after
  execution. Post-execution state is read and compared to the pre-execution snapshot.
  Result: `CONFIRMED_EXECUTED`, `CONFIRMED_NOT_EXECUTED`, or `INDETERMINATE`.
  This does NOT imply autonomous learning or self-modification — MAIW does not update
  its own SOPs, models, or policies based on outcomes.

**CONFIRMED_EXECUTED**
: Reconciliation outcome — the write succeeded and the operational state reflects the change.

**CONFIRMED_NOT_EXECUTED**
: Reconciliation outcome — the write did not take effect (state is unchanged).

**INDETERMINATE**
: Reconciliation outcome — authoritative state cannot confirm either outcome.
  Requires operator review. Never triggers automatic retry.

---

*Last updated: MAIW v2*
