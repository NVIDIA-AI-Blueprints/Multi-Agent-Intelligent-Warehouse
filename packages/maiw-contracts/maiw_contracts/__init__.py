# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
maiw-contracts — MCP-independent warehouse domain capability contracts.

These types define the semantic vocabulary for MAIW warehouse operations.
They are independent of the MCP transport layer and can be used by any
transport, simulation, or test infrastructure.

Public surface
--------------
    CapabilityMetadata          Per-capability descriptor: name, side_effect, risk, timeout

    Equipment:
        EquipmentStatusRequest / EquipmentStatusResult
        EquipmentTelemetryRequest / EquipmentTelemetryResult
        EquipmentAssignmentRequest / EquipmentAssignmentResult
        EquipmentExecuteAssign/Release/MaintenanceResult
        EquipmentAssetInfo, TelemetryPoint, AvailableMetric
        EQUIPMENT_*_METADATA constants

    Labor:
        LaborCapacityRequest / LaborCapacityResult
        LaborAllocationRequest / LaborAllocationResult
        LaborAllocateRequest / LaborAllocateResult
        LaborWorkerInfo, LaborTaskInfo
        LABOR_*_METADATA constants

    Wave:
        WaveGetRequest / WaveGetResult
        WaveRiskRequest / WaveRiskResult
        WaveReprioritizeRequest / WaveReprioritizeResult
        WaveTaskInfo, WaveRiskFactor
        WAVE_*_METADATA constants

    Inventory:
        InventoryLookupRequest / InventoryLocateRequest / InventoryLookupResult
        InventoryLocation
        INVENTORY_*_METADATA constants

"""

from .common import CapabilityMetadata
from .equipment import (
    AvailableMetric,
    EQUIPMENT_ASSIGN_METADATA,
    EQUIPMENT_GET_STATUS_METADATA,
    EQUIPMENT_GET_TELEMETRY_METADATA,
    EQUIPMENT_RELEASE_METADATA,
    EQUIPMENT_SCHEDULE_MAINTENANCE_METADATA,
    EquipmentAssignmentRequest,
    EquipmentAssignmentResult,
    EquipmentAssetInfo,
    EquipmentExecuteAssignResult,
    EquipmentExecuteMaintenanceResult,
    EquipmentExecuteReleaseResult,
    EquipmentStatusRequest,
    EquipmentStatusResult,
    EquipmentTelemetryRequest,
    EquipmentTelemetryResult,
    TelemetryPoint,
)
from .inventory import (
    INVENTORY_GET_METADATA,
    INVENTORY_LOCATE_METADATA,
    InventoryLocateRequest,
    InventoryLocation,
    InventoryLookupRequest,
    InventoryLookupResult,
)
from .labor import (
    LABOR_ALLOCATE_METADATA,
    LABOR_GET_ALLOCATION_METADATA,
    LABOR_GET_CAPACITY_METADATA,
    LaborAllocateRequest,
    LaborAllocateResult,
    LaborAllocationRequest,
    LaborAllocationResult,
    LaborCapacityRequest,
    LaborCapacityResult,
    LaborTaskInfo,
    LaborWorkerInfo,
)
from .wave import (
    WAVE_GET_METADATA,
    WAVE_GET_RISK_METADATA,
    WAVE_REPRIORITIZE_METADATA,
    WaveGetRequest,
    WaveGetResult,
    WaveReprioritizeRequest,
    WaveReprioritizeResult,
    WaveRiskFactor,
    WaveRiskRequest,
    WaveRiskResult,
    WaveTaskInfo,
)
