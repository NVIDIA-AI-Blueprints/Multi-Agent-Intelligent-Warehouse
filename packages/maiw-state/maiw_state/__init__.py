# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
maiw-state — operational warehouse state assembly and snapshot semantics.

Public surface
--------------
    WarehouseState            Assembled operational context for one warehouse
    WarehouseStateSnapshot    Immutable identified snapshot (used by DecisionEngine)
    StateRequirements         Per-request specification of which domains to populate
    StateProvider             Protocol satisfied by WarehouseStateProvider and test doubles
    WarehouseStateProvider    Assembles state through injected Skills
    StateFreshness            Age and staleness metadata per state component
    StateProvenance           Origin metadata per state component
    StateSource               Enum: MCP | DIRECT_DB | CACHE | MOCK
    EquipmentState            Projected equipment fleet context
    EquipmentAssetSummary     Single-asset summary
    InventoryState            Projected inventory context
    InventoryItemSummary      Single-SKU summary
    LaborState                Projected labor/workforce context
    LaborWorkerSummary        Single-worker summary
    LaborZoneSummary          Per-zone labor capacity summary
    WaveState                 Projected wave/pick task context
    WaveTaskSummary           Single-task summary
    WaveZoneSummary           Per-zone wave task summary
    StateAssemblyError        Raised when a domain fails to assemble
    StateFreshnessError       Raised when state exceeds max_age_ms
"""

from .errors import StateAssemblyError, StateFreshnessError
from .freshness import StateFreshness
from .models.equipment import EquipmentAssetSummary, EquipmentState
from .models.inventory import InventoryItemSummary, InventoryState
from .models.labor import LaborState, LaborWorkerSummary, LaborZoneSummary
from .models.wave import WaveState, WaveTaskSummary, WaveZoneSummary
from .provenance import StateProvenance, StateSource
from .provider import StateProvider, WarehouseStateProvider
from .requirements import StateRequirements
from .warehouse import WarehouseState, WarehouseStateSnapshot

__all__ = [
    "EquipmentAssetSummary",
    "EquipmentState",
    "InventoryItemSummary",
    "InventoryState",
    "LaborState",
    "LaborWorkerSummary",
    "LaborZoneSummary",
    "WaveState",
    "WaveTaskSummary",
    "WaveZoneSummary",
    "StateAssemblyError",
    "StateFreshnessError",
    "StateFreshness",
    "StateProvider",
    "StateProvenance",
    "StateRequirements",
    "StateSource",
    "WarehouseState",
    "WarehouseStateProvider",
    "WarehouseStateSnapshot",
]
