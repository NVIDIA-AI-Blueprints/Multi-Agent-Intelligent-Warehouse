# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW Agent Runtimes — Phase 19A.

Exports:
    MAIWDeterministicRuntime — Phase 18H: deterministic SOP execution
    DeepAgentsRuntime        — Phase 19A: simulated Deep Agents POC
    MAIWModelAdapter         — Phase 19A: ModelGateway adapter for Deep Agents
    MAIWSkillAdapter         — Phase 19A: skill adapter for Deep Agents
    get_runtime              — factory: selects runtime from config or MAIW_AGENT_RUNTIME env var
"""

from .deterministic import MAIWDeterministicRuntime
from .deep_agents_runtime import DeepAgentsRuntime, get_runtime
from .model_adapter import MAIWModelAdapter
from .skill_adapter import MAIWSkillAdapter

__all__ = [
    "MAIWDeterministicRuntime",
    "DeepAgentsRuntime",
    "MAIWModelAdapter",
    "MAIWSkillAdapter",
    "get_runtime",
]
