# Phase 15 — MAIW Copilot Architecture

> Supersedes `PHASE_15_COPILOT_INTEGRATION.md` (Phase 14G stub).

Copilot is the human-interaction layer over MAIW's existing operational intelligence and governed decision architecture. It is not a warehouse agent and not an execution engine.

---

## Trust Boundary (Non-Negotiable)

```
Operator Input
      ↓
MAIW Copilot  ← intent, grounding, orchestration ONLY
      ↓
  ASK path  → WarehouseState + Operational Graph → Agent → ModelGateway → Nemotron → Skills → Grounded Answer
  ANALYZE   → same path → Assessment + Recommendations (no mutation)
  ACT path  → same path → ActionProposal → DecisionEngine → Human Approval → ActionExecutor → MCP → Warehouse → Outcome
```

**Copilot may request intelligence and propose governed actions.**
**Copilot must never become an alternative approval or execution path.**
**`POST /copilot/approve` and `POST /copilot/execute` must never exist.**

---

## Intent Model

```python
class CopilotIntent(str, Enum):
    ASK     = "ask"      # read-only explanation
    ANALYZE = "analyze"  # assessment + recommendation, no mutation
    ACT     = "act"      # ActionProposal → governed lifecycle
```

SIMULATE is reserved for a future phase. Do not implement it in Phase 15.

Intent is inferred, not operator-selected. Deterministic rules first; ModelGateway structured classifier only for ambiguous cases.

**Safety invariant:** No natural-language phrasing routes directly to execution. "Move 3 workers to Wave 17 now." → `ACT → ActionProposal → DecisionEngine` — never `execute()`.

If intent is ambiguous (e.g., "Take care of Wave 17"), Copilot asks a clarification:
```
Do you want me to: (1) explain the risk, (2) recommend an action, or (3) prepare the recommended action for approval?
```

---

## Conversation Identity

Three distinct IDs — not the same thing:

| ID | Scope | Lifecycle |
|---|---|---|
| `conversation_id` | One operator Copilot session | Created when drawer opens; persists until reset/close |
| `turn_id` | One operator message + Copilot response | `uuid4()` at turn ingress |
| `trace_id` | One MAIW reasoning/decision execution | `uuid4()` at turn ingress; threaded to ModelGateway + Proposal + Decision + Execution |

A three-turn conversation:
```
conversation_id = C1
  Turn 1  turn_id=T1  trace_id=R1  ASK
  Turn 2  turn_id=T2  trace_id=R2  ANALYZE
  Turn 3  turn_id=T3  trace_id=R3  ACT
```

Each turn is a separate trace. Turns are linked by `parent_turn_id` and `related_trace_ids[]`.

---

## Agent Contract (Confirmed by Audit)

**Primary entry point: `OperationsCoordinationAgent.process_query(query, session_id, context)`**

No new `CopilotAgent` is required.

`process_query` already:
- accepts free-text natural-language intent
- maintains per-session conversation history by `session_id`
- accepts `context: Dict[str, Any]` for injecting warehouse state facts
- returns `OperationsResponse` with `natural_language` + `recommendations`

**Thin adapter needed:**
1. Map `conversation_id` → `session_id`
2. Serialize `WarehouseState` summary into `context["warehouse_state"]`
3. Thread `trace_id` through `context["trace_id"]` (since `process_query` does not natively accept it as a kwarg)
4. Wrap `OperationsResponse` in `CopilotTurn` response shape

`analyze_disruption` (the demo pipeline entry point) is NOT the Copilot path — it does not accept free-text intent and assumes a pre-sealed snapshot. It remains the `/demo/analyze` path only.

---

## ModelGateway Contract

`ModelRequest` fields relevant to Copilot:

| Field | Copilot Use |
|---|---|
| `task` | `"warehouse.operations.analyze_disruption"` (reuse for ANALYZE/ACT); suggest `"warehouse.copilot.ask"` for ASK if routing needs differentiation |
| `messages` | `[{"role": "system", ...}, {"role": "user", "content": operator_message}]` |
| `reasoning` | `ReasoningLevel.HIGH` for ACT; `MEDIUM` for ASK/ANALYZE |
| `risk_level` | `RiskLevel.LOW` for ASK/ANALYZE; `HIGH` for ACT |
| `trace_id` | **Always set** from Copilot turn's `trace_id` |
| `deadline` | Reuse existing `RequestDeadline` from Phase 10E deadline architecture |

**No structured output.** No Nemotron model confirmed JSON mode. All response parsing uses regex/markdown extraction with JSON `try/except` fallback.

**Routing outcomes:**
- ASK (MEDIUM reasoning) → `nano` model
- ANALYZE (MEDIUM reasoning) → `nano` model
- ACT (HIGH reasoning, HIGH risk) → `super` model

---

## Operational Context Architecture

Every Copilot turn grounds itself in current state. The context resolver is the boundary between "all of DC-47" and "what Nemotron sees."

```python
@dataclass
class OperationalContext:
    warehouse_id: str
    snapshot_id: str
    focus_entity_ids: list[str]
    facts: list[str]             # human-readable fact strings (existing format)
    relationships: list[dict]    # relevant edges: {from, rel_type, to}
    domain_states: dict          # {labor: {...}, waves: {...}, equipment: {...}}
```

Resolution for "Why is Wave 17 at risk?":
1. Identify focus entity from query text (Wave 17 → find entity by label)
2. `graph.neighbors(wave_id, direction="both", depth=2)` → tasks, assigned workers, orders, carrier cutoffs, equipment
3. `events_for_entity(wave_id)` → recent operational events
4. Pull matching domain state from `WarehouseState` for confirmed entities
5. Serialize to `OperationalContext` (not raw graph dicts)

**Bounds:**
- `max_depth = 2` (default)
- `max_entities = 50`
- `max_relationships = 100`

These must be documented and enforced. Never pass full DataPack to Nemotron.

---

## Skill Inventory (Confirmed by Audit)

### Read-Only (ASK / ANALYZE)
| Skill | Input | Output |
|---|---|---|
| `LaborCapacitySkill` | `warehouse_id, zone?, shift?` | capacity utilization |
| `LaborAllocationSkill` | `warehouse_id, worker_id?, zone?` | allocation state |
| `WaveGetSkill` | `warehouse_id, wave_id?, zone?` | wave task state |
| `WaveRiskSkill` | `warehouse_id, wave_id?, cutoff_minutes` | risk assessment |
| `EquipmentStatusSkill` | `asset_id?, equipment_type?, zone?` | equipment status |
| `EquipmentTelemetrySkill` | `asset_id, metric?, hours_back` | telemetry |
| `InventoryLookupSkill` | `sku, warehouse_id` | inventory position |

### Proposal-Building (ACT)
| Skill | Produces |
|---|---|
| `ProposeLaborAllocationSkill` | `ActionProposal` — `warehouse.labor.allocate` |
| `ProposeWaveReprioritizationSkill` | `ActionProposal` — `warehouse.wave.reprioritize` |
| `EquipmentAssignmentSkill` | `ActionProposal` — `warehouse.equipment.assign` |

All proposal-building skills are in-process only — no MCP write until post-approval execution.

---

## ASK Contract

```python
@dataclass
class CopilotAskResult:
    answer: str
    evidence: list[str]          # fact strings from OperationalContext
    entities_considered: list[str]
    skills_used: list[str]
    model_id: str
    routing_rule: str
    routing_reason: str
    trace_id: str
```

ASK must NOT contain: `proposal`, `decision`, `approval`, `execution` — except historical references to prior turns.

ASK cannot create an `ActionProposal`.

---

## ANALYZE Contract

```python
@dataclass
class CopilotAnalyzeResult:
    summary: str
    severity: str                # LOW / MEDIUM / HIGH / CRITICAL
    evidence: list[str]
    recommendations: list[RecommendedAction]   # reuse existing type
    skills_used: list[str]
    model_id: str
    routing_rule: str
    routing_reason: str
    trace_id: str
```

ANALYZE must NOT execute, approve, or mutate warehouse state.

`RecommendedAction` already exists in `maiw_agents.assessment` — reuse it.

---

## ACT Contract

```python
@dataclass
class CopilotActResult:
    intent_confirmed: str        # "ACT"
    action_description: str
    proposal: ActionProposal
    decision_outcome: str        # APPROVED / REJECTED / REQUIRES_HUMAN_APPROVAL / REQUIRES_FRESH_STATE
    decision_id: str
    approval_id: str | None      # set if REQUIRES_HUMAN_APPROVAL
    execution: dict | None       # set if APPROVED and auto-executed
    trace_id: str
    state_drift_detected: bool
```

### Recommendation Resolution ("Do it.")
Turn 3 resolves prior ANALYZE turn:
1. Look up `last_recommendations` from `CopilotTurn` store by `conversation_id`
2. Select `recommendations[0]` (or the operator-indicated index)
3. **Revalidate** current `WarehouseState` — state may have drifted since Turn 2
4. If material drift detected: inform operator, re-analyze before proposing
5. If state is fresh: call appropriate `Propose*Skill` → `ActionProposal`
6. Call `DecisionEngine.evaluate(DecisionRequest(..., trace_id=turn_trace_id))`
7. Return `CopilotActResult` with decision outcome

### State Drift Handling
If relevant warehouse state changed materially between ANALYZE and ACT:
```
The warehouse state has changed since this recommendation was generated.
I need to re-evaluate before preparing the action.
```
Then re-run ANALYZE with fresh state before creating the proposal.

---

## ActionProposal Boundary (Confirmed by Audit)

Factory methods on `ActionProposal`:
- `ActionProposal.for_labor_allocate(...)`
- `ActionProposal.for_wave_reprioritize(...)`
- `ActionProposal.for_equipment_assign(...)`

**Always use factory methods. Never construct `ActionProposal` JSON manually in the API router.**

`trace_id` flows: `CopilotTurn.trace_id` → `ActionProposal.trace_id` → `DecisionRequest.trace_id` → `DecisionResult.trace_id` → `ApprovalRecord.trace_id` → execution call.

---

## DecisionEngine Boundary (Confirmed by Audit)

Every ACT-derived proposal must call `DecisionEngine.evaluate()`. No exception.

Possible outcomes that Copilot must surface without collapsing:
- `APPROVED` — proposal auto-approved (LOW risk or auto-approves); Copilot surfaces result
- `REJECTED` — explain why; no retry without fresh state and operator re-confirmation
- `REQUIRES_HUMAN_APPROVAL` — Copilot surfaces approval card; Copilot does NOT call `POST /demo/approve`
- `REQUIRES_FRESH_STATE` — state was stale at decision time; revalidate and retry

---

## Human Approval Boundary (Confirmed by Audit)

When `decision_outcome = REQUIRES_HUMAN_APPROVAL`:
- Copilot enqueues to `ctrl.pending_approvals` (same store as the demo pipeline)
- Copilot displays: "This action requires human approval." + existing approval card
- **Copilot does NOT call `POST /demo/approve` automatically**
- The operator must explicitly interact with the approval control
- `POST /demo/approve` remains the only approval path

---

## Execution Boundary (Confirmed by Audit)

Copilot never calls `ActionExecutor.execute()` directly from a conversational handler.

If `DecisionEngine` returns `APPROVED` and the current architecture auto-executes (i.e., executor is present and bound), that canonical behavior is preserved — but it runs through `state_aware_ops.propose_*`, not through a Copilot-specific shortcut.

---

## Conversation Store

Process-local, in-memory — same scope as `InMemoryApprovalStore`:

```python
@dataclass
class CopilotTurn:
    turn_id: str
    conversation_id: str
    user_message: str
    intent: CopilotIntent
    created_at: datetime
    trace_id: str
    response_summary: str
    artifact_refs: dict           # {proposal_id, decision_id, approval_id, execution_id}

@dataclass  
class CopilotConversation:
    conversation_id: str
    warehouse_id: str
    scenario_name: str
    turns: list[CopilotTurn]
    last_recommendations: list[RecommendedAction]
    related_trace_ids: list[str]
    created_at: datetime
```

Do NOT store: `chain_of_thought`, `scratchpad`, `hidden_reasoning`, `reasoning_tokens`.

Process-local limitation must be documented in the API response.

---

## API Design

Single endpoint:

```
POST /api/v1/copilot/turn
```

Request:
```json
{
  "conversation_id": "...",
  "message": "Why is Wave 17 at risk?",
  "context": {}
}
```

Response:
```json
{
  "conversation_id": "C1",
  "turn_id": "T1",
  "trace_id": "R1",
  "intent": "ask",
  "status": "complete",
  "response": {
    "answer": "...",
    "evidence": [...],
    "entities_considered": [...],
    "skills_used": ["wave.get_state", "labor.get_capacity"],
    "model_id": "nvidia/nemotron-3-nano-...",
    "routing_rule": "medium_reasoning",
    "routing_reason": "..."
  },
  "related_artifacts": {}
}
```

**Explicitly forbidden endpoints:**
```
/copilot/approve
/copilot/execute
/copilot/force-action
```

---

## SSE / Developer Trace Integration

Every Copilot turn generates a `trace_id` that flows into `ModelRequest.trace_id` and any downstream `ActionProposal.trace_id`. Copilot-initiated pipeline events (REASON, SKILL, PROPOSE, DECIDE, etc.) appear in the existing SSE stream with the matching `trace_id` in `detail`.

New SSE categories (minimal additions to `EventCategory`):
```python
"COPILOT_TURN_STARTED"
"COPILOT_INTENT_RESOLVED"
"COPILOT_CONTEXT_RESOLVED"
"COPILOT_TURN_COMPLETE"
```

These are NOT added to `SSE_TO_RAIL` — they are conversational events, not pipeline stages.

The Copilot drawer filters the shared SSE event buffer by `trace_id` to show turn-specific pipeline activity. **No second `EventSource` connection.**

---

## UI Architecture

Phase 14G reserved entry point: `data-testid="phase15-copilot-button"` — currently `disabled`. Enable by removing `disabled` / `aria-disabled`, adding `onClick` that opens the drawer.

Layout (desktop):
```
Main MAIW Demo (~65–70%) │ Copilot Drawer (~30–35%)
```

Drawer structure:
```
MAIW COPILOT

Context: DC-47 · Labor Constraint + Wave Risk
────────────────
[conversation turns]
────────────────
Suggested: [Why is the wave at risk?] [What should we do?]
────────────────
Ask MAIW…  [_________________________] [Send]
```

Copilot drawer shares the React Query client and SSE stream. It does not replace the stage workflow view.

---

## Developer Trace Shape (per turn)

```
COPILOT TURN (turn_id, conversation_id)
      ↓ COPILOT_INTENT_RESOLVED
Intent: ASK / ANALYZE / ACT
      ↓ COPILOT_CONTEXT_RESOLVED
WarehouseState snapshot
Operational Graph neighborhood (entity_ids, depth)
      ↓ REASON (existing)
Agent: OperationsCoordinationAgent.process_query
      ↓ MODEL (via ModelGateway routing)
ModelGateway → nano / super
      ↓ SKILL (existing, per skill invocation)
Skills: wave.get_state, labor.get_capacity, ...
      ↓ COPILOT_TURN_COMPLETE
Result: ASK answer / ANALYZE recommendations / ACT proposal

[ACT only continues through:]
      ↓ PROPOSE / DECIDE / APPROVE / EXECUTE / OBSERVE_OUTCOME
```

---

## Architecture Invariants (Tests Required in 15A Scaffolding)

```python
# CopilotService MUST NOT import ActionExecutor
assert "ActionExecutor" not in copilot_service_imports

# CopilotService MUST NOT call ApprovalStore.approve
assert not hasattr(CopilotService, 'approve')

# Copilot API MUST NOT expose /approve or /execute paths
assert "/copilot/approve" not in router_paths
assert "/copilot/execute" not in router_paths

# CopilotIntent must be a typed enum
assert isinstance(CopilotIntent.ASK, CopilotIntent)

# Every CopilotTurn has a trace_id
assert copilot_turn.trace_id is not None

# Context resolver enforces bounds
assert len(context.focus_entity_ids) <= 50
```

---

## Missing Contracts (Gaps Requiring Implementation in 15B+)

1. **`CopilotIntent` enum** — does not exist; must be created in Phase 15A scaffolding
2. **`CopilotTurn` / `CopilotConversation` models** — do not exist
3. **`CopilotAskResult` / `CopilotAnalyzeResult` / `CopilotActResult`** — do not exist
4. **`OperationalContext` + context resolver** — does not exist; `neighbors()` API is available
5. **`InMemoryCopilotStore`** — does not exist
6. **`POST /api/v1/copilot/turn`** — does not exist
7. **`CopilotService`** — does not exist; must enforce trust boundaries
8. **Copilot SSE categories** — `COPILOT_TURN_STARTED` etc. not yet in `EventCategory`
9. **`useCopilot()` hook** — does not exist; must share `useDemoSSE` event buffer

---

## Risk Assessment

**Low risk:**
- `OperationsCoordinationAgent.process_query` is a clean fit — no new agent needed
- `ModelRequest.trace_id` is fully supported — end-to-end correlation is free
- Existing proposal factory methods are correct — no manual proposal JSON
- `POST /demo/approve` already handles the full approval+execution path — no new approval endpoint needed for Phase 15

**Medium risk:**
- `process_query` does not natively accept `trace_id` — must be threaded through `context` dict; this is a workaround, not a clean contract. Phase 15B should add `trace_id` as a native kwarg if possible.
- `process_query` uses `_simulate_workforce_data()` as a fallback when live state is unavailable — Copilot must inject real `WarehouseState` into `context` to suppress simulation fallback.
- No confirmed structured output from any Nemotron model — all JSON parsing is brittle; must have robust extraction fallback.

**Architectural concern:**
- `OperationsCoordinationAgent.process_query` was designed for conversational queries but did not anticipate needing to produce typed `CopilotAskResult` / `CopilotAnalyzeResult` / `CopilotActResult`. The `OperationsResponse.recommendations: list[str]` field returns plain strings, not `RecommendedAction` objects. Copilot's ANALYZE path needs `RecommendedAction` objects (with `action_type`, `target_id`, `reason`). This can be resolved by: (a) having the Copilot adapter parse the string recommendations into typed objects via the existing `OperationalAssessment` schema, or (b) calling `analyze_disruption` for ANALYZE turns and `process_query` only for pure ASK turns. **Option (b) is cleaner** — it gives Copilot typed `OperationalAssessment.recommendations` for ANALYZE/ACT while using `process_query` for conversational ASK.

---

## Phase 15 Implementation Sequence

| Phase | Scope |
|---|---|
| **15A** | Contracts, audit (this doc), typed scaffolding, architecture invariant tests |
| **15B** | ASK — read-only conversational questions |
| **15C** | ANALYZE — typed recommendations without actions |
| **15D** | ACT — governed ActionProposal flow |
| **15E** | Copilot UI — drawer, conversation, trace integration |
| **15F** | Canonical three-turn demo: "Why?" → "What should we do?" → "Do it." |
| **15G** | Hardening: stale state, UNKNOWN outcomes, error states, docs |
