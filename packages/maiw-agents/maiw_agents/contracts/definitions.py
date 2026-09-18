# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Canonical AgentDefinition instances for all MAIW agents — Phase 18H.8.

These are the authoritative machine-readable specifications for each agent.
They drive:
- Runtime capability enforcement (what skills the agent may call)
- SOP validation (capabilities declared in SOP ⊆ capabilities here)
- Governance boundary enforcement (may_invoke_action_executor, etc.)
- Documentation generation (future)
- Deep Agents integration (future)

Design invariants:
- All PROPOSAL-class capabilities require governance_boundary.may_invoke_decision_engine=True
  for the agent to submit them; currently only OCA submits to GovernedActionOrchestrator.
- Specialist agents (labor, wave, equipment) have governance_boundary with
  may_invoke_action_executor=False and may_invoke_decision_engine=False.
- SafetyComplianceAgent has emergency_authority because it may invoke EMERGENCY_WRITE
  skills through the safety override path — this is an INTENTIONAL EXCEPTION
  documented in the governance baseline audit.
"""

from .agent import (
    AgentDefinition,
    AgentTrigger,
    GovernanceBoundary,
    TerminationCondition,
    TerminationPolicy,
)

# ── OperationsCoordinationAgent ───────────────────────────────────────────────

OPERATIONS_COORDINATION_DEFINITION = AgentDefinition(
    agent_id="operations_coordination",
    version="1.0",
    objective=(
        "Restore an at-risk wave to on-track completion before the carrier cutoff, "
        "by identifying the primary constraint, consulting specialist agents, generating "
        "candidate interventions, and emitting a single highest-priority recommendation "
        "for governance evaluation."
    ),
    domain="operations",
    triggers=[
        AgentTrigger(
            trigger_id="wave_risk_detected",
            trigger_type="wave_risk_detected",
            description="Wave has at_risk_count > 0 or approaching carrier cutoff.",
        ),
        AgentTrigger(
            trigger_id="operator_requests_resolution",
            trigger_type="operator_requests_resolution",
            description="Operator explicitly requests wave risk resolution.",
        ),
    ],
    required_context=["wave", "task", "worker", "equipment", "carrier_cutoff"],
    allowed_capabilities=[
        # READ
        "warehouse.inventory.lookup",
        "warehouse.equipment.status",
        "warehouse.equipment.telemetry",
        "warehouse.labor.capacity",
        "warehouse.labor.inspect_workers",
        "warehouse.labor.inspect_tasks",
        "warehouse.wave.status",
        "warehouse.wave.inspect_tasks",
        # ANALYTICAL
        "warehouse.labor.evaluate_reallocation",
        "warehouse.wave.evaluate_critical_path",
        "warehouse.wave.evaluate_reprioritization",
        # PROPOSAL — for emitting recommendations to GovernedActionOrchestrator
        "warehouse.equipment.assign",
        "warehouse.equipment.release",
        "warehouse.labor.allocate",
        "warehouse.wave.reprioritize",
    ],
    allowed_subagents=["labor", "wave", "equipment"],
    sop_id="operations_coordination.wave_risk_resolution",
    output_contract=(
        "RecommendedAction with domain, capability, target, objective, rationale, priority, subtype. "
        "Flows to GovernedActionOrchestrator for governance evaluation. "
        "Agent does NOT specify MCP parameters."
    ),
    governance_boundary=GovernanceBoundary(
        allowed_capability_classes=["READ", "ANALYTICAL", "PROPOSAL"],
        may_invoke_action_executor=False,
        may_invoke_decision_engine=False,  # submits via GovernedActionOrchestrator, not directly
    ),
    termination_policy=TerminationPolicy(
        max_iterations=10,
        stop_conditions=[
            TerminationCondition(condition_id="OBJECTIVE_MET", description="Recommendation submitted and outcome observed."),
            TerminationCondition(condition_id="NO_SAFE_ACTION", description="No safe intervention exists."),
            TerminationCondition(condition_id="HUMAN_REQUIRED", description="Situation requires human decision."),
            TerminationCondition(condition_id="INSUFFICIENT_CONTEXT", description="Required context unavailable."),
            TerminationCondition(condition_id="MAX_ITERATIONS", description="Iteration limit reached."),
            TerminationCondition(condition_id="POLICY_BLOCKED", description="All candidates blocked by policy."),
        ],
    ),
)


# ── LaborAgent ────────────────────────────────────────────────────────────────

LABOR_AGENT_DEFINITION = AgentDefinition(
    agent_id="labor",
    version="1.0",
    objective=(
        "Determine whether labor is constraining an operational objective "
        "and produce feasible labor interventions."
    ),
    domain="labor",
    triggers=[
        AgentTrigger(
            trigger_id="labor_constraint_detected",
            trigger_type="labor_constraint_detected",
            description="Labor utilization or idle-worker state indicates a constraint.",
        ),
        AgentTrigger(
            trigger_id="delegated_by_oca",
            trigger_type="operator_requests_resolution",
            description="OperationsCoordinationAgent delegated a labor assessment.",
        ),
    ],
    required_context=["worker", "task"],
    allowed_capabilities=[
        "warehouse.labor.capacity",
        "warehouse.labor.inspect_workers",
        "warehouse.labor.inspect_tasks",
        "warehouse.labor.evaluate_reallocation",
    ],
    allowed_subagents=[],
    sop_id="labor.labor_constraint_assessment",
    output_contract=(
        "LaborAssessment containing idle/active worker counts, unassigned task count, "
        "primary constraint classification, and CandidateLaborAction[] ordered by priority. "
        "Never a write action."
    ),
    governance_boundary=GovernanceBoundary(
        allowed_capability_classes=["READ", "ANALYTICAL"],
        may_invoke_action_executor=False,
        may_invoke_decision_engine=False,
    ),
    termination_policy=TerminationPolicy(
        max_iterations=5,
        stop_conditions=[
            TerminationCondition(condition_id="OBJECTIVE_MET", description="LaborAssessment produced."),
            TerminationCondition(condition_id="NO_SAFE_ACTION", description="No feasible reallocation found."),
            TerminationCondition(condition_id="INSUFFICIENT_CONTEXT", description="Labor state unavailable."),
            TerminationCondition(condition_id="MAX_ITERATIONS", description="Iteration limit reached."),
        ],
    ),
)


# ── WaveAgent ─────────────────────────────────────────────────────────────────

WAVE_AGENT_DEFINITION = AgentDefinition(
    agent_id="wave",
    version="1.0",
    objective=(
        "Protect wave completion before carrier cutoff by identifying task sequencing "
        "or reprioritization opportunities and producing candidate wave interventions."
    ),
    domain="wave",
    triggers=[
        AgentTrigger(
            trigger_id="wave_risk_detected",
            trigger_type="wave_risk_detected",
            description="Wave has at_risk_count > 0 or approaching carrier cutoff.",
        ),
        AgentTrigger(
            trigger_id="delegated_by_oca",
            trigger_type="operator_requests_resolution",
            description="OperationsCoordinationAgent delegated a wave risk assessment.",
        ),
    ],
    required_context=["wave", "carrier_cutoff"],
    allowed_capabilities=[
        "warehouse.wave.status",
        "warehouse.wave.inspect_tasks",
        "warehouse.wave.evaluate_critical_path",
        "warehouse.wave.evaluate_reprioritization",
    ],
    allowed_subagents=[],
    sop_id="wave.wave_risk_assessment",
    output_contract=(
        "WaveAssessment containing at_risk_task_count, pending_task_count, "
        "time_to_cutoff (minutes), primary_constraint classification, and "
        "CandidateWaveAction[] ordered by urgency. "
        "Never a write action."
    ),
    governance_boundary=GovernanceBoundary(
        allowed_capability_classes=["READ", "ANALYTICAL"],
        may_invoke_action_executor=False,
        may_invoke_decision_engine=False,
    ),
    termination_policy=TerminationPolicy(
        max_iterations=5,
        stop_conditions=[
            TerminationCondition(condition_id="OBJECTIVE_MET", description="WaveAssessment produced."),
            TerminationCondition(condition_id="NO_SAFE_ACTION", description="No feasible reprioritization found."),
            TerminationCondition(condition_id="INSUFFICIENT_CONTEXT", description="Wave state unavailable."),
            TerminationCondition(condition_id="MAX_ITERATIONS", description="Iteration limit reached."),
        ],
    ),
)


# ── EquipmentAssetOperationsAgent ─────────────────────────────────────────────

EQUIPMENT_AGENT_DEFINITION = AgentDefinition(
    agent_id="equipment",
    version="1.0",
    objective=(
        "Assess equipment availability, telemetry, and assignment constraints, "
        "and produce candidate equipment interventions (assign, release, maintenance proposals)."
    ),
    domain="equipment",
    triggers=[
        AgentTrigger(
            trigger_id="equipment_constraint_detected",
            trigger_type="equipment_constraint_detected",
            description="Equipment is offline, over-assigned, or requires maintenance.",
        ),
        AgentTrigger(
            trigger_id="delegated_by_oca",
            trigger_type="operator_requests_resolution",
            description="OperationsCoordinationAgent delegated an equipment assessment.",
        ),
    ],
    required_context=["equipment"],
    allowed_capabilities=[
        "warehouse.equipment.status",
        "warehouse.equipment.telemetry",
        # PROPOSAL — routes through propose_schedule_maintenance / propose_equipment_release
        "warehouse.equipment.assign",
        "warehouse.equipment.release",
        "warehouse.equipment.schedule_maintenance",
    ],
    allowed_subagents=[],
    sop_id=None,  # Equipment SOP defined in Phase 19 (post-18H baseline)
    output_contract=(
        "Equipment assessment with available_count, offline_count, at_risk_count, "
        "maintenance_candidates, and CandidateEquipmentAction[]. "
        "Write proposals flow through propose_schedule_maintenance() / "
        "propose_equipment_release() → DecisionEngine → governance."
    ),
    governance_boundary=GovernanceBoundary(
        allowed_capability_classes=["READ", "ANALYTICAL", "PROPOSAL"],
        may_invoke_action_executor=False,
        may_invoke_decision_engine=True,  # EAO uses propose_* methods → DecisionEngine
    ),
    termination_policy=TerminationPolicy(
        max_iterations=5,
        stop_conditions=[
            TerminationCondition(condition_id="OBJECTIVE_MET", description="Equipment assessment produced."),
            TerminationCondition(condition_id="NO_SAFE_ACTION", description="No feasible equipment action found."),
            TerminationCondition(condition_id="INSUFFICIENT_CONTEXT", description="Equipment state unavailable."),
            TerminationCondition(condition_id="MAX_ITERATIONS", description="Iteration limit reached."),
        ],
    ),
)


# ── SafetyComplianceAgent ─────────────────────────────────────────────────────

SAFETY_COMPLIANCE_DEFINITION = AgentDefinition(
    agent_id="safety_compliance",
    version="1.0",
    objective=(
        "Monitor warehouse safety state, evaluate policy compliance, and emit "
        "safety alerts. In emergencies (zone_unsafe, equipment_critical), may "
        "invoke emergency authority to halt operations."
    ),
    domain="safety",
    triggers=[
        AgentTrigger(
            trigger_id="safety_alert",
            trigger_type="safety_alert",
            description="A safety condition has been detected.",
        ),
        AgentTrigger(
            trigger_id="operator_requests_resolution",
            trigger_type="operator_requests_resolution",
            description="Operator requests a safety assessment.",
        ),
    ],
    required_context=["equipment", "worker"],
    allowed_capabilities=[
        "warehouse.equipment.status",
        "warehouse.equipment.telemetry",
        "warehouse.labor.inspect_workers",
    ],
    allowed_subagents=[],
    sop_id=None,  # Safety SOP defined post-18H baseline
    output_contract=(
        "SafetyAssessment with alert_level, policy_violations[], and emergency_action "
        "if applicable. Emergency writes are INTENTIONAL EXCEPTIONS documented in "
        "PHASE_18H_AGENT_GOVERNANCE_BASELINE.md."
    ),
    governance_boundary=GovernanceBoundary(
        allowed_capability_classes=["READ", "ANALYTICAL", "PROPOSAL"],
        may_invoke_action_executor=False,
        may_invoke_decision_engine=False,
        emergency_authority=(
            "SafetyComplianceAgent may invoke EMERGENCY_WRITE capabilities "
            "only in zone_unsafe or equipment_critical conditions. "
            "This is an INTENTIONAL EXCEPTION per governance baseline audit."
        ),
    ),
    termination_policy=TerminationPolicy(
        max_iterations=3,
        stop_conditions=[
            TerminationCondition(condition_id="OBJECTIVE_MET", description="Safety assessment complete."),
            TerminationCondition(condition_id="HUMAN_REQUIRED", description="Emergency requires human intervention."),
            TerminationCondition(condition_id="MAX_ITERATIONS", description="Iteration limit reached."),
        ],
    ),
)


# ── Registry of all canonical definitions ────────────────────────────────────

AGENT_DEFINITIONS: dict[str, AgentDefinition] = {
    "operations_coordination": OPERATIONS_COORDINATION_DEFINITION,
    "labor": LABOR_AGENT_DEFINITION,
    "wave": WAVE_AGENT_DEFINITION,
    "equipment": EQUIPMENT_AGENT_DEFINITION,
    "safety_compliance": SAFETY_COMPLIANCE_DEFINITION,
}


def get_agent_definition(agent_id: str) -> AgentDefinition | None:
    """Look up a canonical AgentDefinition by agent_id."""
    return AGENT_DEFINITIONS.get(agent_id)
