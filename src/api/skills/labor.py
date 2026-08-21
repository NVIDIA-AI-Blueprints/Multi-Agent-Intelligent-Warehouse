# DEPRECATED compatibility shim — use maiw_skills.labor directly. Remove by Phase 9.
from maiw_skills.labor.skills import (  # noqa: F401
    ExecuteLaborAllocationSkill,
    LaborAllocationSkill,
    LaborCapacitySkill,
    ProposeLaborAllocationSkill,
    get_execute_labor_allocation_skill,
    get_labor_allocation_skill,
    get_labor_capacity_skill,
    get_propose_labor_allocation_skill,
)
