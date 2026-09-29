# Equipment Failure / Recovery

**SOP ID:** `equipment.equipment_failure_recovery`
**Version:** `1.0`
**Agent:** `equipment` (EquipmentAssetOperationsAgent)
**Executable definition:** [`agents/sops/equipment/equipment_failure_recovery.v1.yaml`](../../agents/sops/equipment/equipment_failure_recovery.v1.yaml)
**Engine:** SOP Engine V2 — see [SOP_ENGINE_V2_DESIGN.md](../architecture/SOP_ENGINE_V2_DESIGN.md)

This document and the YAML are two views of the same procedure. They share an
ID, a version and an objective. If they disagree, the YAML is what runs.

---

## Purpose

Restore the operational capability lost when a critical equipment asset becomes
unavailable, by the least disruptive means available — and confirm from
authoritative warehouse state that the capability is genuinely restored before
declaring the procedure complete.

The last clause is the whole point of this SOP:

> **Equipment recovery is complete only when the physical/operational state
> proves the recovery — not when the agent, MCP server, or executor says it
> succeeded.**

## Trigger

- `equipment_constraint_detected` — equipment status monitoring observes an asset
  that has left service.
- `delegated_by_oca` — the Operations Coordination Agent has diagnosed equipment
  as the primary constraint on an at-risk wave and delegated the equipment
  question here.

## Traditional warehouse process

A picker finds the forklift dead in the aisle. They flag down a supervisor. The
supervisor walks the floor looking for a spare, radios maintenance, and decides
on the spot whether to move the work or wait for a repair. The decision is
sound — supervisors are good at this — but it is undocumented, it is only as
good as one person's picture of the floor, and nobody reliably checks afterwards
whether the replacement actually got assigned to the right work. The WMS record
and the physical floor drift apart.

## AI-assisted process

The agent does the looking-around part: it reads authoritative equipment state,
quantifies what the loss costs the operation, finds candidate replacements, and
proposes **one** action with its reasoning attached. A human approves or rejects
it. Execution happens through the governed executor. Then — the part the manual
process usually skips — the system re-reads warehouse state and proves the
recovery actually happened.

What the agent does *not* do is touch the warehouse. It cannot. See
[Execution ownership](#execution-ownership).

## Preconditions

| Requirement | Detail |
|---|---|
| Context | `failed_asset_id` must be present in bounded context (declared as `required_inputs` on step 1) |
| State domain | `equipment` must be available in the warehouse state snapshot |
| Capabilities | `warehouse.equipment.status`, `warehouse.equipment.telemetry`, `warehouse.equipment.release`, `warehouse.equipment.schedule_maintenance` |
| Agent definition | `EQUIPMENT_AGENT_DEFINITION` with `may_invoke_action_executor = False` |

Note the capability list does **not** include `warehouse.equipment.assign`.
`validate_sop()` rejects that ID by pattern, so an SOP is structurally incapable
of declaring the write it is asking for. The assignment reaches the warehouse
only through governance.

## Procedure

| # | Step | What it establishes | Completes when |
|---|---|---|---|
| 1 | `detect_failure` | Which asset left service, and from where | The status capability returns `failed_asset_id`, `failed_asset_status`, `zone` |
| 2 | `assess_operational_impact` | What the loss costs | Structured impact: `affected_asset`, `affected_operation`, `severity`, `evidence` |
| 3 | `inspect_alternatives` | Whether anything can replace it | The status capability returns `candidate_count` and `alternate_asset_id` |
| 4 | `determine_recovery_strategy` | The least disruptive option | Structured strategy: `strategy`, `replacement_asset_id`, `rationale` |
| 5 | `produce_recommendation` | One well-formed RecommendedAction | Recommendation struct valid, carrying `recommendation_id` |
| 6 | `wait_for_governance` | **HALT.** Hand off to governance | On resume: authoritative state shows the write landed |
| 7 | `verify_execution` | The transition was the intended one | Authoritative state shows replacement `assigned` |
| 8 | `verify_recovery` | The objective is restored (**TERMINAL**) | Full operational post-condition holds |

Every non-terminal step names its successor explicitly. `verify_recovery` is the
only step with `next_step_id: null`.

### The three-step proof at the end

Steps 6, 7 and 8 all complete by `STATE_PREDICATE`, and the predicates get
deliberately stronger:

| Step | Predicate | Question it asks |
|---|---|---|
| 6 | `equipment_write_landed` | Did the mutation reach the warehouse *at all*? |
| 7 | `equipment_replacement_assigned` | Was it the transition we *intended*? |
| 8 | `equipment_recovery_complete` | Is the warehouse *objective* restored? |

They are separate because they fail separately, and each failure means something
different:

- **6 fails** → the write is lost, or we cannot tell. If the executor outcome was
  ambiguous, this is `EXECUTION_INDETERMINATE`.
- **7 fails** → something changed, but not what we asked for. The asset left the
  available pool into `maintenance` rather than `assigned`.
- **8 fails** → execution genuinely succeeded and recovery still did not happen.
  Most commonly: the replacement landed in the wrong zone, or the failed asset
  silently came back online.

`equipment_recovery_complete` requires all of the following simultaneously:

```
replacement_asset.status == "assigned"
AND replacement_asset.zone == <zone that lost capacity>     (when a zone is named)
AND failed_asset.status NOT IN {"available", "assigned", "charging"}
```

That third clause matters more than it looks. If the asset we declared failed is
operational again, either the diagnosis was wrong or somebody re-enabled faulty
equipment. Both need a human.

## Governance

```
RecommendedAction → ActionProposal → DecisionEngine → Human approval → ActionExecutor
```

The SOP Engine halts at step 6 with `ProcedureStatus.WAITING_FOR_GOVERNANCE` and
executes **nothing** further until `resume_after_governance()` is called. The
pause step carries no `retry_policy`, so resuming can never re-issue the write.

`ActionProposal.for_equipment_assign()` sets `requires_approval = True` and
`risk_level = MEDIUM`, so an equipment assignment always requires a human
decision. Release is `LOW` risk and does not.

### Execution ownership

| Responsibility | Owner |
|---|---|
| Assess, recommend | `EquipmentAssetOperationsAgent` (maiw-agents) |
| Sequence, validate, halt | `SOPEngine` (maiw-agents) |
| Authorize | `DecisionEngine` + human (maiw-decision) |
| **Execute the mutation** | `apps/api/maiw_api/routers/equipment.py` |

The only two places in the system that invoke the equipment ActionExecutor:

- `assign_equipment()` — `apps/api/maiw_api/routers/equipment.py:460`
- `release_equipment()` — `apps/api/maiw_api/routers/equipment.py:520`

Both call `runtime.equipment_executor.execute(proposal, decision, trace_id=...)`
and both are gated on `result["status"] == "approved"`.
`schedule_maintenance()` never executes at all.

Nothing under `packages/maiw-agents/` imports `maiw_execution` or references
`ActionExecutor` in executable code. This is enforced by an AST-based static
test, not by convention.

### Authoritative re-read

Post-write state is read by
`WarehouseStateProvider.get_state(warehouse_id, StateRequirements(equipment=True, ...))`
(`packages/maiw-state/maiw_state/provider.py:132`), which calls
`EquipmentStatusSkill.execute()` → MCP capability
`warehouse.equipment.get_status`. The result is sealed into a
`WarehouseStateSnapshot` and handed to the SOP Engine, which passes it to the
registered predicate.

**A validator never reads an executor response.** It only ever reads state.

## Completion criteria

The procedure reaches `ProcedureStatus.COMPLETED` only when all eight steps have
completed, which requires all three state predicates to hold against
authoritative warehouse state.

None of the following can complete this SOP:

- an HTTP 200 from the equipment MCP server
- `ActionExecutionResult.executed == True`
- `DecisionOutcome.APPROVED`
- an executor return string of any kind
- a model asserting the step is done

## Failure and escalation paths

| Path | Condition | Escalation code | Terminal state |
|---|---|---|---|
| A | No alternate asset available | `CAPABILITY_UNAVAILABLE` | `ESCALATED` |
| B | Governance rejected | `VALIDATION_FAILED` | `ESCALATED` (0 writes) |
| C | Executor UNKNOWN, state does not confirm | `EXECUTION_INDETERMINATE` | `ESCALATED` |
| C′ | Executor UNKNOWN, state **does** confirm | — | `COMPLETED` (reconciled) |
| D | Execution confirmed, recovery predicate fails | `RETRY_BUDGET_EXHAUSTED` | `ESCALATED` |
| E | State unreadable within budget | `RETRY_BUDGET_EXHAUSTED` | `ESCALATED` |
| F | Step exceeds `timeout_seconds` (no budget) | `TIMEOUT` | `FAILED` |
| G | Required inputs missing | `MISSING_DATA` | `ESCALATED` |

### Ambiguity is resolved by reading, never by writing

When the executor cannot say what happened (`UNKNOWN` / `INDETERMINATE` /
`TIMEOUT`), the procedure does exactly one thing: it re-reads authoritative
state.

- If `equipment_write_landed` holds, the ambiguous write is reconciled as
  confirmed and the procedure continues.
- If it does not, the procedure escalates `EXECUTION_INDETERMINATE` and stops.

There is no second write attempt in either branch. `RetryPolicy` makes the
unsafe configuration unbuildable: `retry_on` rejects `EXECUTION_INDETERMINATE`
and `WRITE_AMBIGUOUS` at contract-construction time.

### What the retry budgets actually retry

Only safe, read-only operations: state re-reads, assessment, validation. Steps 6
(the write handoff) carries no budget at all. All budgets are bounded by
`max_attempts` (2–3 here) with explicit backoff.

## Human control

| Decision | Who |
|---|---|
| Approve or reject the recommended assignment | Human, via DecisionEngine |
| Whether faulty equipment returns to service | Human (the SOP refuses to complete if it happens unexplained) |
| Dispatch when no alternate exists | Human (path A escalation) |
| Resolution of any `EXECUTION_INDETERMINATE` | Human |
| Physical lockout / tagout | Human, outside this system entirely |

### Why there is no HUMAN validator

Equipment recovery already flows through MAIW governance: the write requires
human approval via `DecisionEngine` before `ActionExecutor` is reached. Adding a
`HUMAN` completion validator to a step would duplicate that approval, not add
control.

This proof also has no genuinely separate human-confirmation step — nothing like
"technician confirms physical lockout" — that governance does not already cover.
So no `HUMAN` validator is implemented.

This is consistent with the engine as it stands: `ValidatorType` currently
defines exactly four members (`SCHEMA`, `STATE_PREDICATE`, `CAPABILITY_RESULT`,
`LEGACY_SUCCESS`). `HUMAN`, `MODEL_JUDGE` and `COMPOSITE` are commented out in
`contracts/sop_v2.py` and do not exist. If a future procedure needs a physical
human confirmation distinct from approval, that is when `HUMAN` should be built.

## Facility variation notes

The procedure is written to be portable. None of the following is hardcoded, and
none is implemented here — they are the knobs a deployment would turn:

- **Fixed automation vs mobile equipment.** A conveyor cannot be "reassigned to
  another zone"; the `reassign_alternate` strategy simply never gets selected,
  and `schedule_maintenance` or `defer` wins instead. The step graph is unchanged.
- **Equipment class.** Forklift, conveyor and AMR differ in whether a spare pool
  exists at all. Only `EquipmentType` in `maiw-world` enumerates these
  (`agv`, `forklift`, `conveyor`); the operational path treats type as a string.
- **Maintenance availability.** A facility with an on-shift technician will
  prefer `schedule_maintenance`; one without will prefer `reassign_alternate`.
- **Spare equipment pool depth.** A deep pool makes path A rare; a facility
  running at parity makes it the common case.
- **Facility criticality.** Drives the `severity` threshold at which a recovery
  is worth its disruption.
- **Labor fallback.** Some facilities can absorb an equipment loss with manual
  labor. That is a cross-domain recovery and would be a delegation to the labor
  agent — not implemented in this proof.
- **Zone semantics.** `expected_zone` is a predicate argument, so a facility
  where cross-zone assignment is acceptable simply omits it.

## Known gaps

Recorded honestly rather than papered over:

1. **Equipment status is not an enum.** `status` is a bare `str` across
   `maiw-state`, `maiw-contracts` and the DB. The documented vocabulary is
   `available | assigned | charging | maintenance | offline`, but the DB schema
   comment says `out_of_service` instead of `offline`. `predicates.py` codes
   against the contract vocabulary.
2. **Two spellings of the type key.** `maiw_state.models.equipment` emits
   `equipment_type`; `state_aware_ops.get_equipment_state_snapshot` emits `type`.
   These predicates depend only on `asset_id`, `status` and `zone`, which agree,
   so they are unaffected.
3. **Predicate args are literal in the YAML.** Asset IDs appear as
   `predicate_args` constants. Binding them from bounded context requires
   parameter substitution the engine does not have, and adding an expression
   language was explicitly out of scope.
4. **No cross-domain (labor) fallback strategy.**
