# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Inventory / picking domain (maiw-agents package).

The inventory domain currently contributes SOP state predicates and no agent
class: Proof SOP C is executed by the generic SOP Engine against the inventory
agent *definition* in ``contracts/definitions.py``. There is deliberately no
``InventoryAgent`` with per-strategy methods — picking strategy is deterministic
facility configuration read from bounded context, not behaviour hardcoded per
strategy in Python.

Importing the inventory domain registers its SOP state predicates with the SOP
Engine (see predicates.py). Inventory semantics belong to the inventory package,
not to the generic validator engine.
"""

from .predicates import (
    INVENTORY_PREDICATES,
    inventory_exception_resolved,
    inventory_quantity_sufficient,
    inventory_write_landed,
    register_inventory_predicates,
)

__all__ = [
    "INVENTORY_PREDICATES",
    "inventory_exception_resolved",
    "inventory_quantity_sufficient",
    "inventory_write_landed",
    "register_inventory_predicates",
]
