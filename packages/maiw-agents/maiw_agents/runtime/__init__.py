# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW Agent Runtimes — Phase 19A.11 (simplified).

Exports:
    MAIWDeterministicRuntime  — deterministic SOP execution (strict mode)
    DeepAgentsRuntime         — real deepagents==0.7.15 integration (adaptive mode)
    MAIWModelGatewayChat      — LangChain BaseChatModel → ModelGateway (production)
    MAIWTestModelAdapter      — async ModelGateway adapter (test/reference only)
    MAIWModelAdapter          — deprecated alias for MAIWTestModelAdapter
    MAIWSkillAdapter          — skill adapter for Deep Agents
    check_capability_alignment — consolidated capability guard (from contracts)
    get_runtime               — factory: selects runtime from config, env, or SOP profile

Phase 19A.11b: _SimulatedDeepAgentsRuntime removed. It was ~600 LOC of generic
orchestration (planning loop, step dispatch, subagent delegation, scratchpad,
error handling) that is now provided by the real deepagents==0.7.15 SDK.
"""

from .deterministic import MAIWDeterministicRuntime
from .deep_agents_runtime import DeepAgentsRuntime, get_runtime
from .model_adapter import MAIWTestModelAdapter, MAIWModelAdapter, MAIWModelGatewayChat
from .skill_adapter import MAIWSkillAdapter
from ..contracts.runtime import check_capability_alignment

__all__ = [
    "MAIWDeterministicRuntime",
    "DeepAgentsRuntime",
    "MAIWTestModelAdapter",
    "MAIWModelAdapter",          # deprecated alias → MAIWTestModelAdapter
    "MAIWModelGatewayChat",
    "MAIWSkillAdapter",
    "check_capability_alignment",
    "get_runtime",
]
