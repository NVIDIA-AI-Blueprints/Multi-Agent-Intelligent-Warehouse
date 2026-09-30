# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Equipment & Asset Operations Agent (maiw-agents package)."""

from .agent import EquipmentAssetOperationsAgent, EquipmentQuery, EquipmentResponse

# Importing the equipment domain registers its SOP state predicates with the
# SOP Engine (see predicates.py). Equipment semantics belong to the equipment
# package, not to the generic validator engine.
from .predicates import (
    EQUIPMENT_PREDICATES,
    equipment_recovery_complete,
    equipment_replacement_assigned,
    equipment_write_landed,
    register_equipment_predicates,
)

__all__ = [
    "EquipmentAssetOperationsAgent",
    "EquipmentQuery",
    "EquipmentResponse",
    "EQUIPMENT_PREDICATES",
    "equipment_recovery_complete",
    "equipment_replacement_assigned",
    "equipment_write_landed",
    "register_equipment_predicates",
]
