# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW Agent Runtimes — Phase 19A.

Exports:
    MAIWDeterministicRuntime  — Phase 18H: deterministic SOP execution
    DeepAgentsRuntime         — Phase 19A: real deepagents==0.7.15 integration
    _SimulatedDeepAgentsRuntime — Phase 19A POC: integration-seam prototype (internal)
    MAIWModelAdapter          — Phase 19A: legacy async ModelGateway adapter
    MAIWModelGatewayChat      — Phase 19A: LangChain BaseChatModel → ModelGateway
    MAIWSkillAdapter          — Phase 19A: skill adapter for Deep Agents
    get_runtime               — factory: selects runtime from config or MAIW_AGENT_RUNTIME env var
"""

from .deterministic import MAIWDeterministicRuntime
from .deep_agents_runtime import DeepAgentsRuntime, _SimulatedDeepAgentsRuntime, get_runtime
from .model_adapter import MAIWModelAdapter, MAIWModelGatewayChat
from .skill_adapter import MAIWSkillAdapter

__all__ = [
    "MAIWDeterministicRuntime",
    "DeepAgentsRuntime",
    "_SimulatedDeepAgentsRuntime",
    "MAIWModelAdapter",
    "MAIWModelGatewayChat",
    "MAIWSkillAdapter",
    "get_runtime",
]
