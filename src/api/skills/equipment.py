# DEPRECATED compatibility shim — use maiw_skills.equipment directly. Remove by Phase 9.
from maiw_skills.equipment.skills import (  # noqa: F401
    EquipmentAssignmentSkill,
    EquipmentStatusSkill,
    EquipmentTelemetrySkill,
    ExecuteEquipmentAssignmentSkill,
    ExecuteEquipmentMaintenanceSkill,
    ExecuteEquipmentReleaseSkill,
    get_equipment_assignment_skill,
    get_equipment_status_skill,
    get_equipment_telemetry_skill,
    get_execute_equipment_assignment_skill,
    get_execute_equipment_maintenance_skill,
    get_execute_equipment_release_skill,
    reset_equipment_skills,
)
