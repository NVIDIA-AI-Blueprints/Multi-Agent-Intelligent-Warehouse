# Picking / Inventory Exception

**SOP ID:** `inventory.picking_inventory_exception`
**Version:** `1.0`
**Agent:** `inventory` (InventoryExceptionAgent definition)
**Executable definition:** [`agents/sops/inventory/picking_inventory_exception.v1.yaml`](../../agents/sops/inventory/picking_inventory_exception.v1.yaml)
**Engine:** SOP Engine V2 — see [SOP_ENGINE_V2_DESIGN.md](../architecture/SOP_ENGINE_V2_DESIGN.md)

This document and the YAML are two views of the same procedure. They share an
ID, a version and an objective. If they disagree, the YAML is what runs.

---

## Purpose

Resolve a picking exception — a SKU that cannot satisfy the quantity a pick
requires — by the least disruptive means the facility's configured picking
strategy allows, and confirm from authoritative inventory state that the pick
can genuinely resume before declaring the procedure complete. Where the
exception does not clear within a bounded reassessment budget, hand control to a
human rather than continuing to look.

This is Proof SOP C. It exists to demonstrate one thing:

> **The SOP Engine controls the loop. The model may provide evidence, but it
> cannot decide that the loop is finished.**

It also re-proves, in a second domain, the invariant Proof SOP B established:

> **A picking exception is resolved only when authoritative inventory state
> proves it — not when an adjustment was submitted, approved, or reported
> successful.**

## Trigger

- `inventory_exception_detected` — a picker reached a location and the SKU could
  not satisfy the required quantity, or the count is inconsistent with the
  record.
- `delegated_by_oca` — the Operations Coordination Agent has diagnosed inventory
  as the constraint on an at-risk wave and delegated the question here.

## Traditional warehouse process

A picker arrives at A-01-03 for 12 units and finds 4. They flag the short pick
on the RF gun and move on, or they radio a lead. Someone else — often much
later — decides whether to replenish from reserve, substitute an equivalent SKU,
short the order, or send someone to count the bin. In the meantime the wave
carries a line that will miss its carrier cutoff and nobody is watching the
clock on it.

The part that goes wrong most often is not the decision. It is the follow-up.
An adjustment gets keyed, everyone assumes it took, and nobody re-reads the bin.
The WMS record and the physical shelf drift apart, and the next picker walks
into the same shortage.

## AI-assisted process

The agent does the assessment: it reads authoritative inventory state,
classifies what kind of exception this is, establishes what the facility's
picking strategy permits, evaluates the replenishment options, and proposes
**one** action with its reasoning attached. A human approves or rejects it.
Execution happens through the governed executor.

Then it does the part the manual process usually skips — and does it a bounded
number of times. Warehouses are not instantaneous: a replenishment authorized at
10:04 may not show in the record until 10:06. So the system re-reads
authoritative inventory state, up to three times, until it can prove the pick
can resume. If three reads is not enough, it stops looking and calls a human.

What the agent does *not* do is touch the stock. It cannot. See
[Execution ownership](#execution-ownership).

## Preconditions

| Requirement | Detail |
|---|---|
| `sku` | The SKU that short-picked. Required input of step 1. |
| `required_quantity` | What the pick needs. Required input of step 1. |
| `facility_picking_strategy` | `zone` or `discrete`. Deterministic facility configuration. Required input of step 3. |
| `inventory` context | Authoritative inventory state must be readable. |

If `facility_picking_strategy` is absent the procedure escalates `MISSING_DATA`
rather than assuming a strategy. A guess about how a facility picks is not a
safe default.

## Procedure

| # | Step | Action | Completes when |
|---|---|---|---|
| 1 | `detect_exception` | `read_inventory_state` | `warehouse.inventory.lookup` returned `sku`, `total_available`, `required_quantity` |
| 2 | `classify_exception` | `classify_inventory_exception` | output carries `exception_type`, `severity`, both quantities, `evidence` |
| 3 | `select_picking_strategy` | `determine_picking_strategy` | output carries `picking_strategy`, `strategy_source`, `rationale` |
| 4 | `inspect_alternate_locations` *(zone only)* | `inspect_alternate_inventory_locations` | `warehouse.inventory.locate` returned `candidate_location_count`, `alternate_location_id` |
| 5 | `evaluate_resolution_options` | `evaluate_replenishment_options` | output carries ranked `options` and a `selected_option` |
| 6 | `propose_resolution` | `emit_recommended_action` | **on resume:** `inventory_write_landed` holds |
| 7 | `reassess_inventory_state` **(LOOP)** | `verify_inventory_reconciled` | `inventory_exception_resolved` holds |
| 8a | `resume_picking` *(terminal)* | `return_inventory_assessment` | output carries `resolution`, `available_after`, `pick_can_resume` |
| 8b | `escalate_to_human` *(terminal)* | `escalate_inventory_exception` | output carries the structured handoff |

Step 4 runs only in a zone-picking facility. Steps 8a and 8b are mutually
exclusive: 8a is the loop's exit branch, 8b is its exhaustion branch.

### The bounded loop

Step 7 is the only looping step in any MAIW SOP, and every part of it is held by
the engine:

| Property | Value | Held by |
|---|---|---|
| Iteration bound | `max_iterations: 3` | SOP Engine, counted in `ProcedureExecutionState.attempt_by_step` |
| Wall-clock bound | `max_total_seconds: 120` | SOP Engine, from first entry into the step |
| Exit criterion | `inventory_exception_resolved` | Registered predicate, evaluated against authoritative state |
| Exit target | `resume_picking` | SOP definition |
| Exhaustion target | `escalate_to_human` | SOP definition |

The loop body is the step itself. There is no multi-step back-edge, and none can
be written: `LoopPolicy` has no `loop_back_step_id`. That is deliberate — a loop
spanning several steps could re-enter the governed write, which is exactly the
failure mode the no-blind-retry rule exists to prevent.

### Loop state machine

```
                  ┌──────────────────┐
                  │   LOOP_RUNNING   │
                  └────────┬─────────┘
                           │  engine runs the step, then runs the validator
                           ▼
              ┌────────────────────────┐
              │ inventory_exception_   │
              │ resolved  holds?       │
              └───┬────────────────┬───┘
                yes                no
                  │                 │
                  ▼                 ▼
              ┌───────┐   ┌───────────────────────┐
              │ EXIT  │   │ iterations < 3  AND   │
              └───┬───┘   │ elapsed   < 120s ?    │
                  │       └────┬─────────────┬────┘
                  │          yes             no
                  │            │              │
                  │            ▼              ▼
                  │        ┌───────┐   ┌────────────┐
                  │        │ RETRY │   │ EXHAUSTED  │
                  │        └───┬───┘   └──────┬─────┘
                  │            │              │
                  ▼            └──► (re-enter)▼
           resume_picking                escalate_to_human
              COMPLETED                     ESCALATED
```

Nothing in that diagram consults a runtime, a model, or `StepResult.output`. The
runtime is handed one step, returns one claim about it, and is never asked
whether to go round again.

### What the model cannot do

| Attempt | What happens |
|---|---|
| Return `status=COMPLETED` on every iteration | The validator's verdict decides. The loop runs its full budget and escalates. |
| Return `status=FAILED` when state is actually fine | The validator's verdict decides. The loop exits on iteration 1. |
| Return `exit_loop: true` in its output | Ignored. The engine reads no loop-control field from output. |
| Return `iterations_remaining: 99` | Ignored, for the same reason. |
| Select a different next step | The seam has no such parameter. |

Each row is a test in `test_sop_loop_semantics.py` and
`test_sop_picking_inventory_exception.py`.

## Facility strategy variation

The same procedure behaves differently in a zone-picking facility and a
discrete-picking facility:

| Facility | Step 4 | Rationale |
|---|---|---|
| `zone` | runs | Stock is held across zones; searching other locations is a real option. |
| `discrete` | skipped by the engine | One order, one picker, one location — there is nothing to search. |

The mechanism is the existing declarative `StepCondition`, evaluated against
`facility_picking_strategy` in bounded context. That value is **deterministic
operational configuration**. It is not selected by a model, not inferred from
state, and not defaulted. There is no `InventoryAgent` class and therefore no
per-strategy method: adding a strategy would mean adding configuration and a
condition, not a code branch.

A skipped step appears in `branch_history` (which records traversal) and not in
`completed_step_ids` (which records completion). A step that never ran has not
completed anything.

### Documented limitation

Of the six picking strategies in the literature — discrete, batch, zone,
cluster, wave and hybrid — this codebase models only two in a form a procedure
can act on:

| Strategy | Status in this codebase |
|---|---|
| `discrete` | Representable — the degenerate single-location case. |
| `zone` | Representable — `Zone.zone_type == "picking"`, `WaveTaskSummary.zone`, per-location inventory rows. |
| `batch`, `cluster`, `hybrid` | **Not present.** No contract, no configuration, no code. |
| `wave` | `Wave.strategy` exists but its values (`fifo`, `priority`, `deadline`) are wave *release* sequencing, not a picking method. |

This SOP therefore supports exactly `discrete` and `zone`, and says so. The
general `PickingStrategy` model sketched in SOP_ENGINE_V2_DESIGN.md §37 remains
design-only and is not implemented here. Inventing configuration values the
warehouse cannot honour would make the strategy variation a demonstration rather
than a capability.

## Completion criteria

Every step declares one. None uses `LEGACY_SUCCESS`.

The three inventory predicates get stronger as the procedure advances:

| Predicate | Question | Used by |
|---|---|---|
| `inventory_write_landed` | Did availability move off the number we recorded before the write? | Step 6, on governance resume |
| `inventory_quantity_sufficient` | Is enough on hand? | Available to SOPs; not used by this one directly |
| `inventory_exception_resolved` | Can the pick actually resume — enough on hand **and** held somewhere pickable? | Step 7, the loop exit criterion |

The gap between the second and third is the interesting one. A record showing 12
units available in zero locations satisfies "enough on hand" and resolves
nothing: it is an inconsistent record, which is precisely what a picker walks
into. The engine escalates it rather than letting a model reconcile the
contradiction.

The low-stock flag is consulted only when a SOP opts in via
`require_not_low_stock`. See [Known gaps](#known-gaps).

## Retry rules

Two different budgets, deliberately kept apart:

| Budget | Where | What it covers | Exhaustion code |
|---|---|---|---|
| `retry_policy.max_attempts` | Steps 1, 2, 3, 4, 5 | A *step* failing transiently — a capability unavailable, a malformed read | `RETRY_BUDGET_EXHAUSTED` |
| `loop.max_iterations` | Step 7 | The *world* not yet being in the required state, though every attempt ran cleanly | `LOOP_BUDGET_EXHAUSTED` |

A step may not declare both. `SOPStep` rejects it at construction time, which is
what guarantees that for a looping step "attempts" and "iterations" are the same
number and the counter is unambiguous.

Step 6 — the governed write — has neither. It cannot have a loop: `SOPStep`
refuses a loop on `emit_recommended_action`.

## Escalation

| Rule | Trigger | Reason code |
|---|---|---|
| `inventory_state_unreadable` | Authoritative state unreadable within the retry budget | `RETRY_BUDGET_EXHAUSTED` |
| `no_feasible_resolution` | No option the configured strategy permits | `VALIDATION_FAILED` |
| `unsupported_strategy` | Configured strategy is not one this SOP supports | `UNSUPPORTED_STRATEGY` |
| `governance_rejected` | Governance did not approve the adjustment | — (no write attempted) |
| `execution_indeterminate` | Executor outcome ambiguous, state does not settle it | `EXECUTION_INDETERMINATE` |
| `reassessment_budget_exhausted` | The loop ran its full budget without reconciling | `LOOP_BUDGET_EXHAUSTED` |
| `inconsistent_inventory_state` | Quantity satisfies the requirement but the SKU is held nowhere | `LOOP_BUDGET_EXHAUSTED` |

Loop exhaustion cannot be laundered into success. `escalate_to_human` runs and
validates cleanly — it is well-formed escalation, not a failure to produce
one — yet the **procedure** still terminates `ESCALATED`, because the engine
records the exhausted loop in `loop_exhausted_step_ids` and a downstream step
running cleanly cannot overwrite that.

## Governance

### Execution ownership

```
SOP step 6  ──► RecommendedAction ──► ActionProposal ──► DecisionEngine
                                                              │
                                                    human approval required
                                                              │
                                                              ▼
                                                       ActionExecutor
                                                       (outside this package)
                                                              │
                                                              ▼
                                                        warehouse write
```

Nothing left of `ActionExecutor` in that diagram can perform a write. The
`maiw-agents` package does not depend on `maiw-execution`, holds no executor
reference, and exposes no write tool to any runtime.

This SOP cannot even *name* the write capability: `validate_sop()` rejects
`warehouse.inventory.adjust` in `allowed_capabilities`. The declared list is
READ, ANALYTICAL and one non-adjust PROPOSAL.

### Write ambiguity

Exactly one write occurs in this procedure, at step 6, outside the loop and
before it. When its outcome is ambiguous:

```
UNKNOWN  ──►  no repeated write  ──►  authoritative re-read  ──►  reconcile
                                                                   │
                                          holds ──► CONFIRMED_EXECUTED
                                      does not ──► EXECUTION_INDETERMINATE
```

The loop that follows can only read. A test asserts write count `== 1` even when
the loop runs all three iterations — the sharpest edge of the design, because a
loop over a write step is exactly how an automated system duplicates a physical
side effect.

## Human involvement

| Moment | Who | What |
|---|---|---|
| Step 6 | Human approver | Approves or rejects the proposed adjustment |
| Step 8b | Human operator | Receives control when the exception did not clear |

### Why there is no HUMAN validator

`ValidatorType.HUMAN` remains deferred, and this SOP did not need it.

The distinction that decides it:

- **Escalation to a human** — the engine cannot safely resolve the situation and
  transfers control. The procedure ends. Nothing resumes when the human replies.
- **HUMAN validator** — a human response is itself a step's completion criterion.
  The procedure *pauses*, waits, and continues on the answer.

Step 8b is the first. It produces a structured handoff and stops. There is no
`next_step_id`, nothing is awaiting a decision, and the human's eventual count is
a new piece of work, not the completion of this one.

Adding a HUMAN validator here would have meant inventing a pause the procedure
does not have, plus a request/response contract, an expiry, and a no-answer
timeout — all to model a handoff that structured escalation already models
correctly. The moment a genuinely procedural human decision appears — an
operator confirming a physical count *as a step of this procedure*, or approving
a substitution mid-flow — that is when `HUMAN` earns its place.

When it is added it must stay separate from governance approval. Approving an
`ActionProposal` authorizes a *write*; answering a HUMAN validator supplies
*evidence*. Collapsing them would let a validator response grant operational
authority.

## Failure cases

| Case | Behaviour |
|---|---|
| A. Inventory still short after 3 re-reads | `LOOP_BUDGET_EXHAUSTED` → `escalate_to_human` → `ESCALATED` |
| B. Capability unavailable | Retried if the step's policy allows, then `CAPABILITY_UNAVAILABLE`. Never treated as a loop iteration. |
| C. Quantity sufficient, held in no location | `inventory_exception_resolved` is false → loop → escalation. No model-guessed reconciliation, no corrective write. |
| D. State reconciles on iteration 2 or 3 | Loop exits correctly; the procedure completes. |
| E. Human does not respond | Not applicable — no HUMAN validator, so there is nothing to time out. |
| F. Write outcome UNKNOWN | No repeat write. Authoritative re-read. Reconciled or `EXECUTION_INDETERMINATE`. |
| G. Strategy configuration missing | `MISSING_DATA` before any option is evaluated. |
| H. Model insists the loop is finished | Ignored. Full budget runs, then escalation. |

## What remains outside AI authority

- Adjusting stock, reserving it, or moving it. All writes are `ActionExecutor`'s.
- Deciding that the loop is finished.
- Deciding how many times to look.
- Choosing the facility's picking strategy.
- Reconciling a self-contradictory inventory record.
- Approving its own proposal.
- Turning an unresolved exception into a completed procedure.

## Known gaps

| Gap | Detail |
|---|---|
| `is_low_stock` threshold disagreement | `apps/api/maiw_api/demo/world.py` computes `quantity_available <= reorder_point`; `packages/maiw-world/maiw_world/projections.py` computes `<`. Because the boundary case is ambiguous, `inventory_exception_resolved` consults the flag only when a SOP passes `require_not_low_stock`. The default criterion rests on quantities and location counts, on which both producers agree. |
| Field-name disagreement | `maiw_state` emits `sku` / `total_available`; `maiw_world` projections emit `sku_id` / `quantity_available`. The predicates tolerate both spellings and aggregate per-location rows. |
| `InventoryState.from_lookup_result` projects one SKU | A multi-SKU exception cannot be represented in state today. This SOP is single-SKU by construction. |
| No `PickingStrategy` contract | Strategy is a bounded-context string, not a typed model. SOP_ENGINE_V2_DESIGN.md §37 remains design-only. |
| No inventory write capability registered | `warehouse.inventory.adjust` is guarded by `_WRITE_CAPABILITY_PATTERNS` but has no `SKILL_REGISTRY` entry, because no inventory `ActionExecutor` exists yet. The guard is deliberately ahead of the implementation. |

## Tests

| File | Covers |
|---|---|
| `packages/maiw-agents/tests/test_sop_loop_semantics.py` | The loop as a generic engine feature — no domain imports at all |
| `packages/maiw-agents/tests/test_sop_picking_inventory_exception.py` | This procedure end to end, under both runtimes |
