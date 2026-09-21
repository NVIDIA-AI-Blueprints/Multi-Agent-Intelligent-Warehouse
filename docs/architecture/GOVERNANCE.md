# MAIW Governance and Authority Boundary

**Version:** MAIW v2
**Status:** AUTHORITATIVE
**Diagram:** [docs/architecture/diagrams/maiw-runtime-pipeline.png](diagrams/maiw-runtime-pipeline.png)

---

## The Non-Negotiable Invariant

> **The LLM never touches a write path directly.**

AI recommends and proposes. The `DecisionEngine` governs. Human authority approves where required.
`ActionExecutor` executes.

---

## Authority Boundary

The MAIW authority boundary separates **agent output** (intelligence) from **governed execution**
(operational action). The boundary is structural, not configurable.

```
Agent (either runtime)
    ↓
  emit_recommended_action()
    ↓
  RecommendedAction          ← ABOVE the boundary
  (semantic intent — no MCP parameters, no write calls)
    ↓
  AgentTaskState → WAITING_FOR_GOVERNANCE

──────────── MAIW AUTHORITY BOUNDARY ────────────

  ActionProposal             ← BELOW the boundary
  (typed, immutable: target, action_name, params, risk, trace_id, snapshot_id)
    ↓
  DecisionEngine
    ↓
  [APPROVED / REJECTED / DEFERRED]
    ↓
  Human Approval (where required)
    ↓
  ActionExecutor
    ↓
  MCP write capability
    ↓
  Warehouse System
```

**`RecommendedAction`** is agent output — a semantic description of the best intervention.
It does NOT contain MCP parameters. It lives above the boundary.

**`ActionProposal`** is a governed operational artifact. It is typed, immutable, and contains
explicit target, action name, risk level, trace identity, and snapshot binding. It lives below
the boundary. The governance layer translates a `RecommendedAction` into an `ActionProposal`.

---

## How the Boundary Is Enforced Structurally

The boundary is enforced at multiple levels — not by convention:

1. **`_build_maiw_tools()`** in both runtimes hard-blocks `WRITE` and `EMERGENCY_WRITE`
   capability classes from the agent tool list. An agent cannot call a write skill.

2. **`check_capability_alignment()`** rejects SOPs that declare `WRITE` or `EMERGENCY_WRITE`
   capabilities at invocation time. It is a shared MAIW-owned guard, not runtime-specific.

3. **`CopilotService`** cannot import `ActionExecutor`, `ApprovalStore`, or `DecisionEngine`.
   Only `GovernedActionOrchestrator` crosses the boundary, and only after full policy evaluation.

4. **`emit_recommended_action`** in any SOP always transitions `AgentTaskState` to
   `WAITING_FOR_GOVERNANCE`. No runtime may return `COMPLETED` while bypassing this step.

5. **Package structure**: `maiw-execution` does not import `maiw-agents`. The governance
   path is unidirectional — agents flow up to `RecommendedAction`; governance flows down
   from `ActionProposal` to `ActionExecutor`. These are separate code paths.

---

## DecisionEngine

`DecisionEngine.evaluate(proposal, state)` is:

- **Synchronous** — no `await`, no I/O
- **Deterministic** — same inputs always produce the same output
- **Policy-only** — evaluates constraints, risk, allowlist, state validity
- **Non-overridable** — cannot be bypassed by a model-generated argument

Outcomes: `APPROVED`, `REJECTED`, `DEFERRED`

Constraints evaluated:
- Action name in static allowlist
- Proposal snapshot matches current state snapshot
- Risk level within approved threshold
- No active conflicting proposals for the same target
- Proposal not stale (TTL not exceeded)

See [DECISION_ENGINE.md](DECISION_ENGINE.md) for full constraint specifications.

---

## Approval Lifecycle

When `DecisionEngine` returns `DEFERRED` or `REQUIRES_HUMAN_APPROVAL`:

```
ApprovalState: PENDING
    ↓ (operator approves via UI or POST /api/v1/demo/approve)
ApprovalState: APPROVED
    ↓ (ActionExecutor.execute() calls consume())
ApprovalState: CONSUMED
```

Other transitions: `REJECTED` (operator rejects), `EXPIRED` (TTL exceeded — default 300s).

**Approval properties:**
- **Explicit** — requires an active human decision, not implicit model confidence
- **Expirable** — default TTL 300s; expired approvals cannot execute
- **Single-use** — `consume()` transitions to `CONSUMED`; cannot be used again
- **Bound** — approval is bound to the exact `proposal_id`, `decision_id`, and
  `warehouse_snapshot_id`; approving for a different proposal is not possible

The approval state machine is audited: all transitions are recorded with timestamps
and actor identity. The audit chain is preserved even after consumption.

---

## ActionExecutor — Six Guards

`BaseActionExecutor.execute()` checks six guards **in order** before any MCP write:

1. **Decision outcome is `APPROVED`** — rejects anything else
2. **Decision binds to the exact `proposal_id`** — prevents stale-decision replay
3. **Action name is in the executor's static `_ALLOWED_ACTIONS` frozenset** — allowlist check
4. **Decision is not stale** — `evaluated_at` age exceeds `max_decision_age_seconds`
5. **Domain-specific additional guards** — subclass `_check_additional_guards()` hook (e.g. state-drift for equipment)
6. **Request deadline not expired** — checked immediately before write; no mutation on expiry

If any guard fails, no MCP write is attempted. The outcome is `REJECTED` or `CONFLICT`.

`execution_id` is generated **before** the write and propagated through the MCP call.
This enables idempotency checking and reconciliation even if the write acknowledgement is lost.

---

## Reliability at the Execution Boundary

The execution boundary handles distributed-systems uncertainty:

```
Write attempt
    ↓
MCP write call
    ↓ (success) → EXECUTED
    ↓ (explicit failure) → FAILED
    ↓ (timeout / lost ack) → AmbiguousWriteError → UNKNOWN
                                    ↓
                          suppress automatic retry
                                    ↓
                          reread authoritative state
                                    ↓
                   CONFIRMED_EXECUTED | CONFIRMED_NOT_EXECUTED | INDETERMINATE
```

`UNKNOWN` is never auto-retried. The `ExecutionRegistry` blocks any subsequent attempt
on the same idempotency key until reconciliation resolves the outcome.

See [RUNTIME_EXECUTION_FLOW.md](RUNTIME_EXECUTION_FLOW.md) for full sequence diagrams.

---

## What This Means for Developers

- You cannot add a write skill to an agent tool registry. The guard will reject it.
- You cannot bypass `DecisionEngine` from `CopilotService`. The import boundary prevents it.
- You cannot auto-retry an `UNKNOWN` write. `ExecutionRegistry` blocks it.
- You cannot approve a proposal for a different proposal ID. Approval is proposal-bound.
- A model cannot persuade `DecisionEngine` to change its outcome. It has no LLM path.
