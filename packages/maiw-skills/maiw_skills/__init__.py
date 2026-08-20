# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
maiw-skills — Per-domain skill implementations for MAIW warehouse agents.

Canonical import (Phase 8+):
    from maiw_skills.inventory import InventoryLookupSkill
    from maiw_skills.equipment import EquipmentStatusSkill, EquipmentAssignmentSkill
    from maiw_skills.labor import LaborCapacitySkill, ProposeLaborAllocationSkill
    from maiw_skills.wave import WaveGetSkill, ProposeWaveReprioritizationSkill

Legacy compatibility path (DEPRECATED — remove by Phase 9):
    from src.api.skills.inventory import InventoryLookupSkill  # still works via shim
"""
