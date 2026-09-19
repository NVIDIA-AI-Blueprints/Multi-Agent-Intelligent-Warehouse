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
    "no_op",
]


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
            "Override: go to this step ID after this one. "
            "If None, proceed to the next step in the sequence."
        ),
    )
    on_failure_step_id: str | None = Field(
        default=None,
        description="Go to this step on failure (instead of escalating).",
    )


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
_PROHIBITED_CAPABILITY_PREFIXES = ("warehouse.write.", "exec.", "action_executor.")
_WRITE_CAPABILITY_PATTERNS = re.compile(
    r"^(warehouse\.(labor\.assign|wave\.assign|equipment\.(assign|release_direct|deploy))|"
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
