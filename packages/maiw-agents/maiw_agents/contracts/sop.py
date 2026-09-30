# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW SOP (Standard Operating Procedure) schema — Phase 18H.

SOPs are first-class artifacts. They are NOT system prompts.
They define the allowed procedures an agent follows — declaratively,
auditably, and without arbitrary code execution from YAML.

Security:
    - No eval()
    - No exec()
    - No dynamic import from SOP YAML
    - No arbitrary shell commands
    - Capabilities and subagents resolve through registered IDs only

Versioning:
    - Every SOP has: stable ID, version, owning agent, objective
    - SOP version is included in agent task state and trace metadata
    - SOP semantics must not change without a version increment
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from .sop_v2 import (
    EvidenceRequirement,
    LoopPolicy,
    RetryPolicy,
    StepCompletionSpec,
    ValidatorType,
)


# ── Condition (declarative) ───────────────────────────────────────────────────

ConditionOperator = Literal["eq", "ne", "contains", "not_contains", "exists", "not_exists"]


class StepCondition(BaseModel):
    """
    A declarative condition for conditional SOP step execution.

    Conditions are evaluated against named predicates registered in code.
    No arbitrary expression evaluation occurs from YAML.

    Example:
        condition:
          predicate: primary_constraint
          operator: eq
          value: labor
    """

    predicate: str = Field(
        description="Name of a registered predicate to evaluate."
    )
    operator: ConditionOperator = "eq"
    value: str | None = None

    def evaluate(self, facts: dict[str, Any]) -> bool:
        """Evaluate this condition against a dict of runtime facts."""
        fact_value = facts.get(self.predicate)

        if self.operator == "exists":
            return fact_value is not None
        if self.operator == "not_exists":
            return fact_value is None
        if self.operator == "eq":
            return str(fact_value) == str(self.value)
        if self.operator == "ne":
            return str(fact_value) != str(self.value)
        if self.operator == "contains":
            return self.value in str(fact_value) if fact_value is not None else False
        if self.operator == "not_contains":
            return self.value not in str(fact_value) if fact_value is not None else True
        return False


# ── Escalation rule ───────────────────────────────────────────────────────────

class EscalationRule(BaseModel):
    """A named escalation condition."""

    rule_id: str
    trigger: str = Field(description="Human-readable description of what triggers escalation.")
    escalation_message: str | None = None


# ── SOP step ─────────────────────────────────────────────────────────────────

StepActionType = Literal[
    "gather_operational_context",
    "determine_primary_constraint",
    "consult_required_domains",
    "produce_candidate_interventions",
    "compare_candidates",
    "select_recommendation",
    "emit_recommended_action",
    "evaluate_post_execution_state",
    "delegate_to_agent",
    "invoke_skill",
    "read_labor_state",
    "read_task_assignments",
    "evaluate_assignment_imbalance",
    "identify_capacity_deficit",
    "check_worker_constraints",
    "generate_labor_interventions",
    "rank_labor_interventions",
    "return_labor_assessment",
    "read_wave_status",
    "read_outstanding_orders",
    "read_cutoff",
    "calculate_critical_path",
    "identify_at_risk_tasks",
    "generate_wave_options",
    "return_wave_assessment",
    # Equipment domain (Proof SOP B — equipment failure / recovery). Additive,
    # mirroring the labor and wave domain blocks above. None of these are write
    # actions: they read equipment state, assess impact, and select a strategy.
    # The mutation itself is never an SOP action — it is performed by
    # ActionExecutor outside the agent package after governance approves.
    "read_equipment_state",
    "assess_equipment_impact",
    "inspect_alternate_equipment",
    "determine_recovery_strategy",
    "verify_equipment_recovery",
    # Inventory / picking domain (Proof SOP C — picking inventory exception).
    # Additive, mirroring the labor, wave and equipment blocks above. None of
    # these are write actions: they read inventory state, classify an exception,
    # select a picking strategy from deterministic facility configuration,
    # evaluate replenishment options, and re-read state to decide whether the
    # exception cleared. The adjustment itself is never an SOP action — it is
    # performed by ActionExecutor outside the agent package after governance
    # approves.
    "read_inventory_state",
    "classify_inventory_exception",
    "determine_picking_strategy",
    "inspect_alternate_inventory_locations",
    "evaluate_replenishment_options",
    "verify_inventory_reconciled",
    "return_inventory_assessment",
    "escalate_inventory_exception",
    "no_op",
]

# Step actions that hand control to the governance boundary. A step with one of
# these actions pauses at WAITING_FOR_GOVERNANCE and may be followed by a real
# warehouse mutation performed by ActionExecutor. Repeating such a step can
# duplicate a physical side effect, so it may never carry a loop policy.
GOVERNED_WRITE_ACTIONS: frozenset[str] = frozenset({"emit_recommended_action"})


class SOPStep(BaseModel):
    """
    One step in a Standard Operating Procedure.

    Steps are declarative: they name an action type and optionally
    specify a condition, delegate agent, skill, or next step override.
    """

    id: str = Field(description="Unique step identifier within this SOP.")
    action: StepActionType
    description: str | None = None

    # Optional delegation
    delegate_to: str | None = Field(
        default=None,
        description="Agent ID to delegate this step to (for delegate_to_agent action).",
    )
    skill_id: str | None = Field(
        default=None,
        description="Skill ID to invoke (for invoke_skill action).",
    )

    # Optional condition
    condition: StepCondition | None = None

    # Navigation
    next_step_id: str | None = Field(
        default=None,
        description=(
            "The step ID to execute after this one. "
            "None means this step is TERMINAL and the procedure completes here — "
            "it does NOT fall through to the next step in the YAML list. "
            "Every non-terminal step must name its successor explicitly."
        ),
    )
    on_failure_step_id: str | None = Field(
        default=None,
        description="Go to this step on failure (instead of escalating).",
    )

    # ── V2 extension fields ───────────────────────────────────────────────────
    # Every field below is Optional with a None default. A v1 SOP that sets none
    # of them loads and executes exactly as it did before SOP Engine V2:
    # completion=None selects the LEGACY_SUCCESS validator, retry_policy=None
    # means a single attempt, timeout_seconds=None means no step-level timeout.

    objective: str | None = Field(
        default=None,
        description="What this individual step is trying to achieve (distinct from the SOP objective).",
    )
    required_inputs: list[str] | None = Field(
        default=None,
        description="Context keys that must be present before this step may run.",
    )
    expected_output: dict[str, Any] | None = Field(
        default=None,
        description="JSON-schema-like hint describing the shape of this step's output.",
    )
    completion: StepCompletionSpec | None = Field(
        default=None,
        description=(
            "Declares what 'done' means for this step. "
            "None = legacy/compatibility behaviour (LEGACY_SUCCESS validator)."
        ),
    )
    retry_policy: RetryPolicy | None = Field(
        default=None,
        description="Per-step retry budget. None = no retry (single attempt).",
    )
    loop: LoopPolicy | None = Field(
        default=None,
        description=(
            "Bounded, validator-driven repetition of this step. None = the step "
            "runs once and the procedure moves on. See LoopPolicy: the engine, "
            "not the runtime or the model, decides whether the loop continues."
        ),
    )
    timeout_seconds: float | None = Field(
        default=None,
        description="Step-level wall-clock budget. None = no step-level timeout.",
    )
    escalation_reason: str | None = Field(
        default=None,
        description="Overrides the default escalation message for this step.",
    )
    evidence_requirements: list[str | EvidenceRequirement] | None = Field(
        default=None,
        description=(
            "Evidence this step must produce. Two forms are accepted, and they "
            "mean different things:\n"
            "  - a bare string ('state_snapshot') is a DECLARATIVE HINT. It "
            "    documents the intent and is surfaced to an adaptive runtime in "
            "    the step prompt, but it is not enforced. This is the pre-"
            "    hardening form and every existing SOP uses it.\n"
            "  - an EvidenceRequirement mapping is an ENFORCED PRECONDITION. The "
            "    step cannot complete unless matching structured evidence is "
            "    present. Used on the steps where absence of proof is dangerous: "
            "    governance handoff, post-write reread, final validation.\n"
            "Hints were left unenforced deliberately: the existing string tags "
            "name evidence kinds no component actually emits, so enforcing them "
            "retroactively would fail every step rather than prove anything."
        ),
    )

    def enforced_evidence(self) -> list[EvidenceRequirement]:
        """
        The subset of ``evidence_requirements`` that blocks completion.

        Bare-string hints are excluded — see the field description for why the
        two forms are not equivalent.
        """
        if not self.evidence_requirements:
            return []
        return [r for r in self.evidence_requirements if isinstance(r, EvidenceRequirement)]

    def evidence_requirement_labels(self) -> list[str]:
        """Human/prompt-facing names for every declared requirement, both forms."""
        if not self.evidence_requirements:
            return []
        return [
            r if isinstance(r, str) else r.evidence_type
            for r in self.evidence_requirements
        ]

    @model_validator(mode="after")
    def _check_loop_policy(self) -> "SOPStep":
        """
        A loop is only safe if it is validator-driven, singly-budgeted, and
        cannot repeat a write. All four rules below are structural: a SOP that
        breaks one cannot be constructed, so it can never reach the engine.
        """
        loop = self.loop
        if loop is None:
            return self

        # 1. The loop must be decided by evidence, not by a runtime's say-so.
        #    LEGACY_SUCCESS ("the runtime returned") would exit on iteration 1
        #    every time, which is a loop in name only.
        if self.completion is None:
            raise ValueError(
                f"SOPStep '{self.id}' declares a loop but no completion spec. A loop "
                "must be driven by an explicit completion criterion — otherwise "
                "nothing but the runtime decides when it ends."
            )
        if self.completion.validator_type is ValidatorType.LEGACY_SUCCESS:
            raise ValueError(
                f"SOPStep '{self.id}' declares a loop with validator_type=LEGACY_SUCCESS. "
                "Legacy success means 'the runtime returned', which is not a loop exit "
                "criterion — use STATE_PREDICATE, SCHEMA or CAPABILITY_RESULT."
            )

        # 2. One repetition budget per step. Two budgets would make "attempts"
        #    and "iterations" different numbers and the loop counter ambiguous.
        if self.retry_policy is not None:
            raise ValueError(
                f"SOPStep '{self.id}' declares both a loop and a retry_policy. "
                "These are mutually exclusive repetition budgets: loop.max_iterations "
                "is the authoritative attempt count for a looping step."
            )

        # 3. A governed write must never be loop-retried. Re-entering a step that
        #    hands off to ActionExecutor can duplicate a physical side effect.
        if self.action in GOVERNED_WRITE_ACTIONS:
            raise ValueError(
                f"SOPStep '{self.id}' declares a loop on governed write action "
                f"'{self.action}'. An ambiguous write is resolved by re-reading "
                "authoritative state, never by repeating the write."
            )

        # 4. A loop target pointing at the loop step itself would make the
        #    bound meaningless.
        if loop.exit_step_id == self.id:
            raise ValueError(
                f"SOPStep '{self.id}': loop.exit_step_id must not be the loop step itself."
            )
        if loop.exhaustion_step_id == self.id:
            raise ValueError(
                f"SOPStep '{self.id}': loop.exhaustion_step_id must not be the loop step itself."
            )

        return self


# ── SOP definition ────────────────────────────────────────────────────────────

class SOPDefinition(BaseModel):
    """
    Versioned Standard Operating Procedure.

    A SOP defines the allowed procedure for an agent to follow.
    It is NOT a system prompt — it is a structured, auditable,
    versioned artifact stored in the repository.
    """

    id: str = Field(description="Stable SOP identifier (e.g. 'operations_coordination.wave_risk_resolution').")
    version: str = Field(description="Semantic version (e.g. '1.0').")
    agent: str = Field(description="Agent ID that follows this SOP.")
    objective: str = Field(description="What this SOP is trying to accomplish.")
    description: str | None = None

    triggers: list[str] = Field(default_factory=list)
    required_context: list[str] = Field(default_factory=list)

    allowed_capabilities: list[str] = Field(
        default_factory=list,
        description="Skill IDs allowed within this SOP. Write capabilities are prohibited.",
    )
    allowed_subagents: list[str] = Field(
        default_factory=list,
        description="Agent IDs that may be delegated to from this SOP.",
    )

    steps: list[SOPStep] = Field(default_factory=list)
    escalation: list[EscalationRule] = Field(default_factory=list)
    stop_conditions: list[str] = Field(
        default_factory=list,
        description=(
            "Terminal conditions for this SOP. "
            "At least one must be defined. "
            "Common values: objective_met, no_safe_action, human_intervention_required, "
            "max_iterations_reached."
        ),
    )

    runtime_profile: Literal["strict", "adaptive"] = Field(
        default="strict",
        description=(
            "'strict' → MAIWDeterministicRuntime (default, production-safe). "
            "'adaptive' → DeepAgentsRuntime (LLM-adaptive, specialist delegation). "
            "Used by get_runtime() when no explicit override is provided."
        ),
    )


# ── Validation ────────────────────────────────────────────────────────────────

# Write capabilities are never allowed inside a SOP.
_WRITE_CAPABILITY_PATTERNS = re.compile(
    r"^(warehouse\.(labor\.assign|wave\.assign|equipment\.(assign|release_direct|deploy)|"
    r"inventory\.(adjust|allocate|reserve|replenish_direct))|"
    r"action_executor\.|exec\.)",
    re.IGNORECASE,
)


class SOPValidationError(ValueError):
    """Raised when a SOP fails validation."""

    def __init__(self, sop_id: str, errors: list[str]) -> None:
        self.sop_id = sop_id
        self.errors = errors
        super().__init__(
            f"SOP '{sop_id}' failed validation:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )


def validate_sop(
    sop: SOPDefinition,
    *,
    known_capabilities: set[str] | None = None,
    known_agents: set[str] | None = None,
) -> None:
    """
    Validate a SOPDefinition against the MAIW governance rules.

    Raises SOPValidationError if any rule is violated.

    Rules enforced:
    1. SOP must have an id, version, agent, and objective.
    2. SOP must have at least one stop condition.
    3. Step IDs must be unique.
    4. No step may list a write capability.
    5. allowed_capabilities must not include write capabilities.
    6. If known_capabilities is provided, all listed capabilities must be known.
    7. If known_agents is provided, all listed subagents must be known.
    8. No circular step dependencies (via next_step_id).
    9. Loop targets (exit_step_id / exhaustion_step_id) must name real steps.
   10. A loop must not be re-enterable from its own exit or exhaustion branch,
       which would make the iteration bound meaningless.
    """
    errors: list[str] = []

    # Rule 1: required fields
    if not sop.id:
        errors.append("SOP id is required.")
    if not sop.version:
        errors.append("SOP version is required.")
    if not sop.agent:
        errors.append("SOP agent is required.")
    if not sop.objective:
        errors.append("SOP objective is required.")

    # Rule 2: at least one stop condition
    if not sop.stop_conditions:
        errors.append("SOP must define at least one stop_condition.")

    # Rule 2b: at least one step
    if not sop.steps:
        errors.append("SOP must define at least one step.")

    # Rule 3: unique step IDs
    step_ids = [s.id for s in sop.steps]
    seen: set[str] = set()
    for sid in step_ids:
        if sid in seen:
            errors.append(f"Duplicate step id: '{sid}'.")
        seen.add(sid)

    # Rule 4 & 5: no write capabilities
    for cap in sop.allowed_capabilities:
        if _WRITE_CAPABILITY_PATTERNS.match(cap):
            errors.append(
                f"Write capability '{cap}' is not allowed in SOP allowed_capabilities. "
                "Writes must flow through the MAIW governance boundary."
            )

    # Rule 6: known capabilities
    if known_capabilities is not None:
        for cap in sop.allowed_capabilities:
            if cap not in known_capabilities:
                errors.append(f"Unknown capability: '{cap}'.")

    # Rule 7: known agents
    if known_agents is not None:
        for agent_id in sop.allowed_subagents:
            if agent_id not in known_agents:
                errors.append(f"Unknown subagent: '{agent_id}'.")

    # Rule 8: circular step detection (static)
    # Build a simple graph of id → next_step_id and check for cycles
    next_map = {s.id: s.next_step_id for s in sop.steps if s.next_step_id}
    for start_id in next_map:
        visited: set[str] = set()
        current = next_map.get(start_id)
        while current is not None:
            if current in visited:
                errors.append(
                    f"Circular step dependency detected starting at step '{start_id}'."
                )
                break
            visited.add(current)
            current = next_map.get(current)

    # Rule 9: loop targets must resolve.
    known_step_ids = set(step_ids)
    for step in sop.steps:
        if step.loop is None:
            continue
        for field_name in ("exit_step_id", "exhaustion_step_id"):
            target = getattr(step.loop, field_name)
            if target is not None and target not in known_step_ids:
                errors.append(
                    f"Step '{step.id}' loop.{field_name} references unknown step '{target}'."
                )

    # Rule 10: a loop must be exited for good.
    #
    # The loop's own back-edge is implicit (the engine re-enters the same step)
    # and is bounded by max_iterations. What is NOT bounded is an *outer* cycle:
    # if the exit or exhaustion branch can walk back to the loop step, the
    # iteration counter is reset and the bound means nothing. Only forward
    # edges the engine actually follows are considered here.
    forward_edges: dict[str, set[str]] = {}
    for step in sop.steps:
        targets: set[str] = set()
        if step.next_step_id:
            targets.add(step.next_step_id)
        if step.on_failure_step_id:
            targets.add(step.on_failure_step_id)
        if step.loop is not None:
            if step.loop.exit_step_id:
                targets.add(step.loop.exit_step_id)
            if step.loop.exhaustion_step_id:
                targets.add(step.loop.exhaustion_step_id)
        forward_edges[step.id] = targets

    for step in sop.steps:
        if step.loop is None:
            continue
        branch_starts = {
            t
            for t in (step.loop.exit_step_id, step.loop.exhaustion_step_id, step.next_step_id)
            if t is not None
        }
        seen: set[str] = set()
        frontier = list(branch_starts)
        while frontier:
            node = frontier.pop()
            if node in seen:
                continue
            seen.add(node)
            frontier.extend(forward_edges.get(node, ()))
        if step.id in seen:
            errors.append(
                f"Step '{step.id}' is a loop step reachable from its own exit or "
                "exhaustion branch — the iteration bound would be meaningless."
            )

    if errors:
        raise SOPValidationError(sop.id, errors)


# ── Loader ────────────────────────────────────────────────────────────────────

def load_sop(path: str | Path) -> SOPDefinition:
    """
    Load and validate a SOP from a YAML file.

    Security: only YAML safe_load is used. No eval, no exec,
    no arbitrary Python from YAML.

    Raises:
        FileNotFoundError: if the file does not exist.
        ValueError: if YAML is invalid or SOP fields are missing.
        SOPValidationError: if SOP fails governance validation.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"SOP file not found: {path}")

    with path.open() as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"SOP file must be a YAML mapping, got {type(raw)}: {path}")

    sop = SOPDefinition.model_validate(raw)
    validate_sop(sop)
    return sop
