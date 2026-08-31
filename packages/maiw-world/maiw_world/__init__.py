# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
maiw-world — canonical typed warehouse world models (Phase 14A).

Provides:
- WarehouseWorldConfig: deterministic config for world generation
- Typed entity models (Warehouse, Zone, Location, Worker, Task, ...)
- WarehouseEdge: typed relationships between entities
- OperationalEvent: event log entries
- CanonicalWarehouseGraph: in-memory typed graph
- ValidationReport: graph and config integrity checks

No dependency on maiw-agents, maiw-decision, or maiw-execution.
"""

from .config import (
    EquipmentConfig,
    FacilityConfig,
    HistoryConfig,
    InventoryConfig,
    LaborConfig,
    OrderConfig,
    WarehouseWorldConfig,
    WaveConfig,
)
from .edges import (
    RELATIONSHIP_COMPATIBILITY,
    RelationshipType,
    WarehouseEdge,
)
from .entities import (
    CarrierCutoff,
    EntityType,
    Equipment,
    EquipmentType,
    InventoryPosition,
    Location,
    Order,
    SKU,
    Shift,
    Task,
    TaskStatus,
    TaskType,
    WarehouseEntity,
    Wave,
    Worker,
    Zone,
)
from .events import (
    OperationalEvent,
    OperationalEventType,
)
from .graph import CanonicalWarehouseGraph
from .datapack import (
    WarehouseDataPack,
    compute_semantic_checksum,
    DataPackVerificationResult,
)
from .validation import (
    FindingSeverity,
    ValidationFinding,
    ValidationReport,
    validate_config,
    validate_graph,
)
from .scenario import (
    OverlayEvent,
    OverlayEventKind,
    ScenarioOverlay,
    ScenarioOverlayBuilder,
    ScenarioWorld,
    labor_constraint_scenario,
    equipment_failure_scenario,
)
from .projections import (
    InventoryItemProjection,
    InventoryProjection,
    WorkerProjection,
    LaborProjection,
    EquipmentItemProjection,
    EquipmentProjection,
    TaskProjection,
    WaveItemProjection,
    WaveProjection,
    WarehouseProjectionBuilder,
)

__all__ = [
    # config
    "WarehouseWorldConfig",
    "FacilityConfig",
    "InventoryConfig",
    "LaborConfig",
    "EquipmentConfig",
    "OrderConfig",
    "WaveConfig",
    "HistoryConfig",
    # entities
    "EntityType",
    "WarehouseEntity",
    "Zone",
    "Location",
    "Worker",
    "Shift",
    "EquipmentType",
    "Equipment",
    "SKU",
    "InventoryPosition",
    "Order",
    "Wave",
    "TaskType",
    "TaskStatus",
    "Task",
    "CarrierCutoff",
    # edges
    "RelationshipType",
    "RELATIONSHIP_COMPATIBILITY",
    "WarehouseEdge",
    # events
    "OperationalEventType",
    "OperationalEvent",
    # graph
    "CanonicalWarehouseGraph",
    # datapack
    "WarehouseDataPack",
    "compute_semantic_checksum",
    "DataPackVerificationResult",
    # validation
    "FindingSeverity",
    "ValidationFinding",
    "ValidationReport",
    "validate_graph",
    "validate_config",
    # scenario overlay (Phase 14D)
    "OverlayEventKind",
    "OverlayEvent",
    "ScenarioOverlay",
    "ScenarioOverlayBuilder",
    "ScenarioWorld",
    "labor_constraint_scenario",
    "equipment_failure_scenario",
    # projections (Phase 14E)
    "InventoryItemProjection",
    "InventoryProjection",
    "WorkerProjection",
    "LaborProjection",
    "EquipmentItemProjection",
    "EquipmentProjection",
    "TaskProjection",
    "WaveItemProjection",
    "WaveProjection",
    "WarehouseProjectionBuilder",
]
