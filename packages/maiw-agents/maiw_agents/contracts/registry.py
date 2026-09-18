# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW Skill Registry — Phase 18H.

Every MAIW skill is classified by capability type:

    READ            — reads operational state, no mutation
    ANALYTICAL      — performs analysis on read data, no mutation
    PROPOSAL        — builds an ActionProposal, no mutation (governance validates)
    WRITE           — mutates operational state (must cross MAIW governance boundary)
    EMERGENCY_WRITE — emergency write with explicit authority model

Normal agents may directly use: READ, ANALYTICAL, PROPOSAL
Normal agents may NOT directly invoke: WRITE, EMERGENCY_WRITE
    (must flow through RecommendedAction → ActionProposal → DecisionEngine → ActionExecutor)

This registry supports SOP validation (cross-checking allowed_capabilities)
and architecture invariant tests.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


# ── Capability classification ─────────────────────────────────────────────────

class CapabilityClass(str, Enum):
    """Classification of a MAIW skill/capability."""

    READ = "READ"
    """Read operational state. No mutation."""

    ANALYTICAL = "ANALYTICAL"
    """Analysis over read data. No mutation."""

    PROPOSAL = "PROPOSAL"
    """Builds an ActionProposal. No mutation — governance validates before execution."""

    WRITE = "WRITE"
    """Mutates operational state. Must cross MAIW governance boundary."""

    EMERGENCY_WRITE = "EMERGENCY_WRITE"
    """Emergency write with explicit authority model. Must be documented and policy-controlled."""


# ── Skill registry entry ──────────────────────────────────────────────────────

class SkillRegistryEntry(BaseModel):
    """Metadata for a registered MAIW skill."""

    skill_id: str = Field(description="Stable skill identifier (e.g. 'warehouse.labor.capacity').")
    domain: str = Field(description="Primary domain: equipment, labor, wave, inventory, safety.")
    capability_class: CapabilityClass
    description: str
    input_schema: str = Field(
        default="",
        description="Module path of the input Pydantic model (or empty string).",
    )
    output_schema: str = Field(
        default="",
        description="Module path of the output Pydantic model (or empty string).",
    )
    governance_required: bool = Field(
        description=(
            "True if this skill's output must flow through governance before "
            "any operational effect. Always True for WRITE/EMERGENCY_WRITE."
        ),
    )
    uses_mcp: bool = False
    implementation: str = Field(
        default="",
        description="Module path of the skill implementation (or empty string).",
    )
    is_write: bool = Field(
        description="Convenience flag. True for WRITE and EMERGENCY_WRITE.",
    )

    @classmethod
    def from_fields(
        cls,
        skill_id: str,
        domain: str,
        capability_class: CapabilityClass,
        description: str,
        *,
        input_schema: str = "",
        output_schema: str = "",
        uses_mcp: bool = False,
        implementation: str = "",
    ) -> "SkillRegistryEntry":
        is_write = capability_class in (CapabilityClass.WRITE, CapabilityClass.EMERGENCY_WRITE)
        governance_required = is_write or capability_class == CapabilityClass.PROPOSAL
        return cls(
            skill_id=skill_id,
            domain=domain,
            capability_class=capability_class,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            governance_required=governance_required,
            uses_mcp=uses_mcp,
            implementation=implementation,
            is_write=is_write,
        )


# ── Registry ──────────────────────────────────────────────────────────────────

def _reg(
    skill_id: str,
    domain: str,
    cap: CapabilityClass,
    description: str,
    *,
    input_schema: str = "",
    output_schema: str = "",
    uses_mcp: bool = False,
    implementation: str = "",
) -> tuple[str, SkillRegistryEntry]:
    return skill_id, SkillRegistryEntry.from_fields(
        skill_id=skill_id,
        domain=domain,
        capability_class=cap,
        description=description,
        input_schema=input_schema,
        output_schema=output_schema,
        uses_mcp=uses_mcp,
        implementation=implementation,
    )


#: The canonical MAIW skill registry.
#: Key = skill_id, Value = SkillRegistryEntry.
SKILL_REGISTRY: dict[str, SkillRegistryEntry] = dict([
    # ── Inventory ──────────────────────────────────────────────────────────────
    _reg(
        "warehouse.inventory.lookup",
        "inventory",
        CapabilityClass.READ,
        "Look up inventory levels and locations by SKU.",
        input_schema="maiw_contracts.inventory.InventoryLookupRequest",
        output_schema="maiw_contracts.inventory.InventoryLookupResult",
        implementation="maiw_skills.inventory.lookup.InventoryLookupSkill",
    ),

    # ── Equipment — read ───────────────────────────────────────────────────────
    _reg(
        "warehouse.equipment.status",
        "equipment",
        CapabilityClass.READ,
        "Read equipment status, availability, and assignments.",
        input_schema="maiw_contracts.equipment.EquipmentStatusRequest",
        output_schema="maiw_contracts.equipment.EquipmentStatusResult",
        implementation="maiw_skills.equipment.skills.EquipmentStatusSkill",
    ),
    _reg(
        "warehouse.equipment.telemetry",
        "equipment",
        CapabilityClass.READ,
        "Read equipment telemetry and health metrics.",
        input_schema="maiw_contracts.equipment.EquipmentTelemetryRequest",
        output_schema="maiw_contracts.equipment.EquipmentTelemetryResult",
        implementation="maiw_skills.equipment.skills.EquipmentTelemetrySkill",
    ),

    # ── Equipment — proposal ──────────────────────────────────────────────────
    _reg(
        "warehouse.equipment.assign",
        "equipment",
        CapabilityClass.PROPOSAL,
        "Build an ActionProposal to assign equipment to a task or worker.",
        input_schema="maiw_skills.equipment.skills.EquipmentAssignmentRequest",
        output_schema="maiw_decision.proposal.ActionProposal",
        implementation="maiw_skills.equipment.skills.EquipmentAssignmentSkill",
    ),
    _reg(
        "warehouse.equipment.release",
        "equipment",
        CapabilityClass.PROPOSAL,
        "Build an ActionProposal to release equipment.",
        output_schema="maiw_decision.proposal.ActionProposal",
        implementation="maiw_decision.proposal.ActionProposal.for_equipment_release",
    ),
    _reg(
        "warehouse.equipment.schedule_maintenance",
        "equipment",
        CapabilityClass.PROPOSAL,
        "Build an ActionProposal to schedule equipment maintenance.",
        output_schema="maiw_decision.proposal.ActionProposal",
        implementation="maiw_decision.proposal.ActionProposal.for_schedule_maintenance",
    ),

    # ── Labor — read ──────────────────────────────────────────────────────────
    _reg(
        "warehouse.labor.capacity",
        "labor",
        CapabilityClass.READ,
        "Read labor capacity, worker states, task assignments, and zone staffing.",
        input_schema="maiw_contracts.labor.LaborCapacityRequest",
        output_schema="maiw_contracts.labor.LaborCapacityResult",
        implementation="maiw_skills.labor.skills.LaborCapacitySkill",
    ),
    _reg(
        "warehouse.labor.inspect_workers",
        "labor",
        CapabilityClass.READ,
        "Inspect worker states, roles, and current assignments.",
        implementation="maiw_skills.labor.skills.LaborCapacitySkill",
    ),
    _reg(
        "warehouse.labor.inspect_tasks",
        "labor",
        CapabilityClass.READ,
        "Inspect pending and in-progress task assignments.",
        implementation="maiw_skills.labor.skills.LaborCapacitySkill",
    ),
    _reg(
        "warehouse.labor.evaluate_reallocation",
        "labor",
        CapabilityClass.ANALYTICAL,
        "Evaluate feasibility of worker reallocation between zones/tasks.",
        implementation="maiw_skills.labor.skills.LaborCapacitySkill",
    ),

    # ── Labor — proposal ──────────────────────────────────────────────────────
    _reg(
        "warehouse.labor.allocate",
        "labor",
        CapabilityClass.PROPOSAL,
        "Build an ActionProposal to allocate workers to tasks.",
        output_schema="maiw_decision.proposal.ActionProposal",
        implementation="maiw_skills.labor.skills.ProposeLaborAllocationSkill",
    ),

    # ── Wave — read ───────────────────────────────────────────────────────────
    _reg(
        "warehouse.wave.status",
        "wave",
        CapabilityClass.READ,
        "Read wave status, task backlog, and risk indicators.",
        input_schema="maiw_contracts.wave.WaveStatusRequest",
        output_schema="maiw_contracts.wave.WaveStatusResult",
        implementation="maiw_skills.wave.skills.WaveStatusSkill",
    ),
    _reg(
        "warehouse.wave.inspect_tasks",
        "wave",
        CapabilityClass.READ,
        "Inspect outstanding orders and pending wave tasks.",
        implementation="maiw_skills.wave.skills.WaveStatusSkill",
    ),
    _reg(
        "warehouse.wave.evaluate_critical_path",
        "wave",
        CapabilityClass.ANALYTICAL,
        "Calculate critical path and identify at-risk tasks relative to carrier cutoff.",
        implementation="maiw_skills.wave.skills.WaveStatusSkill",
    ),
    _reg(
        "warehouse.wave.evaluate_reprioritization",
        "wave",
        CapabilityClass.ANALYTICAL,
        "Evaluate wave reprioritization options.",
        implementation="maiw_skills.wave.skills.WaveStatusSkill",
    ),

    # ── Wave — proposal ───────────────────────────────────────────────────────
    _reg(
        "warehouse.wave.reprioritize",
        "wave",
        CapabilityClass.PROPOSAL,
        "Build an ActionProposal to reprioritize a wave.",
        output_schema="maiw_decision.proposal.ActionProposal",
        implementation="maiw_skills.wave.skills.ProposeWaveReprioritizationSkill",
    ),

    # ── Write capabilities — must flow through governance ─────────────────────
    # These entries document what exists in ActionExecutors. They are listed
    # here for registry completeness and SOP validation, but are NEVER
    # listed in any agent's allowed_capabilities.
    _reg(
        "warehouse.labor.assign_direct",
        "labor",
        CapabilityClass.WRITE,
        "WRITE: Direct MCP labor assignment. Must flow through governance boundary.",
        uses_mcp=True,
        implementation="maiw_execution.labor.LaborActionExecutor",
    ),
    _reg(
        "warehouse.wave.reprioritize_direct",
        "wave",
        CapabilityClass.WRITE,
        "WRITE: Direct MCP wave reprioritization. Must flow through governance boundary.",
        uses_mcp=True,
        implementation="maiw_execution.wave.WaveActionExecutor",
    ),
    _reg(
        "warehouse.equipment.assign_direct",
        "equipment",
        CapabilityClass.WRITE,
        "WRITE: Direct MCP equipment assignment. Must flow through governance boundary.",
        uses_mcp=True,
        implementation="maiw_execution.equipment.EquipmentActionExecutor",
    ),
])


def get_skill(skill_id: str) -> SkillRegistryEntry | None:
    """Look up a skill by its ID. Returns None if not registered."""
    return SKILL_REGISTRY.get(skill_id)


def get_skills_by_domain(domain: str) -> list[SkillRegistryEntry]:
    """Return all registered skills for a domain."""
    return [s for s in SKILL_REGISTRY.values() if s.domain == domain]


def get_read_skills() -> list[SkillRegistryEntry]:
    """Return all READ-classified skills."""
    return [s for s in SKILL_REGISTRY.values() if s.capability_class == CapabilityClass.READ]


def get_write_skills() -> list[SkillRegistryEntry]:
    """Return all WRITE and EMERGENCY_WRITE skills (should never appear in agent allowed_capabilities)."""
    return [
        s for s in SKILL_REGISTRY.values()
        if s.capability_class in (CapabilityClass.WRITE, CapabilityClass.EMERGENCY_WRITE)
    ]
