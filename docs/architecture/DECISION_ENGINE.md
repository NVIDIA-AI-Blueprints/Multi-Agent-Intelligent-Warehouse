# DecisionEngine — Deterministic Proposal Evaluation

## Purpose

The `DecisionEngine` evaluates `ActionProposal` objects against a `WarehouseStateSnapshot` using deterministic rules.  It **never executes actions** — it classifies them.

This establishes the approval boundary between agent reasoning and system mutation.  No MCP write tool, database write, or external API call is triggered by the engine.

```
Agent reasoning
    │
    ▼
ActionProposal  ──────────────────────────┐
                                          │
WarehouseStateSnapshot  ──────────────────┤
                                          ▼
                              DecisionEngine.evaluate()
                                          │
                                ┌─────────┴────────────┐
                                ▼                      ▼
                          DecisionResult         DecisionAuditRecord
                         (APPROVED /              (structured log)
                          REJECTED /
                          REQUIRES_HUMAN_APPROVAL /
                          REQUIRES_FRESH_STATE)
```

## Package

`packages/maiw-decision/` — depends on `maiw-state` and `maiw-mcp`, never on `src/api/`.

## Outcomes

| Outcome | Meaning |
|---------|---------|
| `APPROVED` | All rules passed; action may proceed |
| `REJECTED` | Hard constraint violated; action must not proceed |
| `REQUIRES_HUMAN_APPROVAL` | Risk threshold exceeded; human must review |
| `REQUIRES_FRESH_STATE` | Required state is absent or stale; refresh and resubmit |

## Rule Evaluation Order

Rules are evaluated in sequence; the first matching rule determines the outcome.

| # | Rule | Outcome |
|---|------|---------|
| 1 | `risk_level == READ_ONLY` | `APPROVED` immediately — read actions bypass all checks |
| 2 | `domain == equipment` + `asset_id` provided + equipment state **absent** | `REQUIRES_FRESH_STATE` |
| 3 | `domain == equipment` + `asset_id` provided + equipment state **stale** | `REQUIRES_FRESH_STATE` |
| 4 | `domain == equipment` + `asset_id` provided + **asset not in snapshot** | `REJECTED` |
| 5 | `risk_level == LOW` + `requires_approval == False` | `APPROVED` |
| 6 | `requires_approval == True` OR `risk_level` in MEDIUM/HIGH/CRITICAL | `REQUIRES_HUMAN_APPROVAL` |
| 7 | *(fallback)* | `APPROVED` |

## Usage

```python
from maiw_decision import DecisionEngine, DecisionRequest
from maiw_state import WarehouseStateSnapshot

engine = DecisionEngine()

request = DecisionRequest(
    proposal=action_proposal,
    state=warehouse_snapshot,
    trace_id="trace-001",
)

result, audit = engine.evaluate(request)
# result.outcome → DecisionOutcome
# result.violations → list[ConstraintViolation]
# audit.to_log_dict() → dict for structured logging
```

`evaluate()` is **synchronous** — all logic is in-memory with no I/O.

## ActionProposal Evaluation Inputs

The engine reads the following fields from `ActionProposal`:

| Field | Used by rule |
|-------|-------------|
| `risk_level` | Rules 1, 5, 6 |
| `requires_approval` | Rules 5, 6 |
| `domain` | Rules 2–4 (equipment domain checks) |
| `parameters["asset_id"]` | Rules 2–4 (existence and freshness gating) |
| `proposal_id` | Echoed in result and audit |

## DecisionAuditRecord

Every evaluation emits one `DecisionAuditRecord`:

```python
audit.result_id        # cross-references DecisionResult.result_id
audit.proposal_id      # cross-references ActionProposal.proposal_id
audit.snapshot_id      # the exact state version evaluated
audit.outcome          # DecisionOutcome value
audit.violation_rules  # ["equipment.asset_not_found"]
audit.engine_version   # "1.0.0"
audit.trace_id         # propagated from DecisionRequest

log.info(audit.to_log_dict())  # flat dict with event="decision_engine.evaluation"
```

## Constraint Violations

Each rule that fires adds a `ConstraintViolation`:

```python
class ConstraintViolation(BaseModel):
    rule: str     # machine-readable: "equipment.asset_not_found"
    message: str  # human-readable explanation
    details: dict # structured context (asset_id, snapshot_id, age_ms, …)
```

`APPROVED` outcomes have zero violations.  `REQUIRES_HUMAN_APPROVAL` has exactly one (`approval.required`).  `REJECTED` has one or more.

## Deliberate Constraints

The engine is intentionally minimal:

- **No policy engine**: no YAML/JSON rule files, no ML, no external calls
- **No approval UI**: outcomes are returned to the caller; surfacing them to a human is the caller's responsibility
- **No execution**: `APPROVED` means the caller *may* proceed; the engine never proceeds on their behalf
- **No persistence**: audit records are returned to the caller for logging; the engine stores nothing
- **Synchronous only**: no async I/O; rules are pure functions over in-memory objects

## Extending the Rule Set

To add a rule:
1. Identify the insertion point in `engine.py` (rules are evaluated in order)
2. Add a `_check_<rule_name>()` helper method
3. Call it from `evaluate()` before the fallback
4. Bump `_ENGINE_VERSION`
5. Add a `ConstraintViolation` with a new `rule` slug
6. Add tests in `tests/unit/test_decision_engine.py`

## State Drift Protection

`EquipmentActionExecutor._check_state_drift()` runs **after** all rule-based guards pass and **before** the MCP write tool is called. It is best-effort:

| Classification | Meaning |
|----------------|---------|
| `STATE_DRIFT_PROTECTION = LIMITED` | Only checks asset status for "offline" or "maintenance" — it does NOT re-evaluate the full decision rule set against fresh state |

**Why LIMITED**: The drift check requires a live state fetch (`WarehouseStateProvider.get_state`). If the provider is absent, the check is skipped (no error). If the provider is present, only a single asset status field is validated. A full re-evaluation would require re-running DecisionEngine against a new snapshot, which is the caller's responsibility if the decision token expires.

**`warehouse_id` propagation (Phase 6B):** `_check_state_drift()` reads `warehouse_id` from `proposal.parameters["warehouse_id"]` — never uses a hardcoded default. All three `ActionProposal` factories include `warehouse_id` in their parameters dict.

## NIM Fallback

The `_llm_generate()` path in `MCPEquipmentAssetOperationsAgent` can fall back to direct NIM calls. This path is:

```
Classification: COMPATIBILITY_ONLY
```

**When active**: `MAIW_MODEL_GATEWAY_ENABLED` is unset or `false`.  
**What it does**: Routes to `nim_client.generate_response()` directly, bypassing `ModelGateway`.  
**Why kept**: Some deployments do not have `ModelGateway` configured; the fallback ensures the agent remains functional. It is not the production path.  
**Invariant**: The NIM fallback path is not a new capability. No new code should use it. All new agent work should use `ModelGateway`.

## Version History

| Version | Changes |
|---------|---------|
| `1.0.0` | Initial: READ_ONLY bypass, freshness check, asset-not-found, approval threshold |
| `1.0.0` (Phase 6B) | State drift documentation: `STATE_DRIFT_PROTECTION = LIMITED`; `warehouse_id` propagation fix |
