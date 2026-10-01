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

6. **`RuntimeCapabilityPolicy`** is an immutable, deny-by-default grant issued per agent
   task, enforced at the capability invocation seam in both runtimes. `WRITE` and
   `EMERGENCY_WRITE` cannot appear in any policy that can be constructed — a model
   validator rejects it, so a hand-built policy cannot bypass the builder to get one.

---

## Procedure Persistence Does Not Move Authority

The SOP Engine can now checkpoint `ProcedureExecutionState` to a
`ProcedureStateStore` so a procedure survives a crash. This is worth stating
explicitly because "the engine now remembers things across restarts" is exactly
the kind of change that quietly relocates authority — and here it does not.

A store's entire API is `save` / `load` / `delete`. It holds no `ActionExecutor`,
no `DecisionEngine`, no MCP client and no credentials, and a test asserts that
API is exactly three methods rather than trusting this paragraph.

What the boundary looks like across a restart:

- A procedure that was `WAITING_FOR_GOVERNANCE` is **still** waiting after
  recovery. Restoring it does not approve it, does not re-emit a proposal, and
  does not advance past the approval it never received.
- A procedure that crashed *after* a governed write landed does not repeat the
  write. It resumes at the authoritative re-read and proves the outcome by
  reading, never by writing. The recovery test asserts `write_count == 1`
  across the crash.
- Terminal procedures are immutable, so a restart cannot re-open a closed
  procedure and run its write path a second time.
- The SOP version is pinned. A restored procedure never silently continues
  under a newer SOP, because the steps already completed and the steps still to
  come would then have come from different documents.

Governance still runs entirely outside the SOP Engine. Persistence changed what
MAIW can *remember*, not what the agent layer is allowed to *do*.

---

## Sandbox Isolation Is Not Authorization

Phase 20A can place the agent runtime inside an OpenShell sandbox. This is the
same category of change as persistence above, and it deserves the same explicit
statement: **isolation narrows what a compromised agent can reach. It grants
nothing, and it relaxes nothing.**

Three consequences follow, and the third is the one that matters in review:

1. **Every capability check still runs.** `authorize_step` executes in the same
   place, through the same code, sandboxed or not. The sandbox is a second wall
   behind the first — for the case where the first is defeated by a bug.

2. **The authority boundary did not move.** `RecommendedAction` still leaves the
   agent; `DecisionEngine`, approval and `ActionExecutor` still run on the host.
   The sandbox contains the half of the pipeline that was already advisory. It
   does not contain, replace, or sit between any part of the governed half.

3. **A sandbox must never be traded against the policy.** The reasoning "the
   agent is contained now, so the capability policy can be looser" inverts the
   design: it replaces two independent controls with one. A deployment that took
   it would have *fewer* walls after adding a sandbox than before.

What the boundary looks like in both directions:

| Direction | Message | Validated against |
|---|---|---|
| sandbox → host | `SandboxRecommendedActionOutput` | host-held procedure id, task id, revision, non-terminal status |
| host → sandbox | `SandboxGovernanceInput` | host-held procedure id, task id, revision, `WAITING_FOR_GOVERNANCE` status, duplicate ledger |

Both validators assume the sandbox is compromised and is sending whatever it
likes — which is the only assumption under which they are worth having.
`SOPEngine.resume_after_governance` duck-types the outcome it is handed, correct
for a runtime-neutral engine and insufficient at a trust boundary, so the
binding check lives on the host side of the boundary rather than in the engine.

**What a sandbox compromise still achieves:** bad *recommendations*. A
compromised agent can recommend a harmful-but-well-formed intervention. That is
unchanged, and it is precisely what `DecisionEngine` and human approval exist
for. The sandbox narrows the blast radius to "can propose" — the authority an
agent was always supposed to have.

See [NEMOCLAW_OPENSHELL_INTEGRATION.md](NEMOCLAW_OPENSHELL_INTEGRATION.md).

---

## Evidence, Not Assurances, Closes a Write

A write-related step does not complete because governance returned `APPROVED` or
because a call returned 2xx. Steps may declare `EvidenceRequirement`s, enforced
ahead of the completion validator, and only a structured `EvidenceRef` satisfies
one — model prose cannot. The three proof SOPs require `state_snapshot` evidence
from source `authoritative_reread` on their post-write steps, so resuming after
governance **without** re-reading authoritative state escalates as
`EVIDENCE_MISSING` rather than completing.

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
