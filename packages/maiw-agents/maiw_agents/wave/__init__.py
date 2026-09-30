# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Wave domain agent — Phase 18H."""

from .agent import (
    WaveAgent,
    WaveAssessment,
    CandidateWaveAction,
)

# Importing the wave domain registers its SOP state predicates with the
# SOP Engine (see predicates.py). Wave semantics belong to the wave package,
# not to the generic validator engine.
from .predicates import (
    WAVE_PREDICATES,
    register_wave_predicates,
    wave_risk_reduced,
)

__all__ = [
    "WaveAgent",
    "WaveAssessment",
    "CandidateWaveAction",
    "WAVE_PREDICATES",
    "wave_risk_reduced",
    "register_wave_predicates",
]
