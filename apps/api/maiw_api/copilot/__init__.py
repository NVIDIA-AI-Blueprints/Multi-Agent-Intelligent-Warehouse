# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
MAIW Copilot — Phase 15.

Copilot is the human-interaction layer over MAIW's existing operational
intelligence and governed decision architecture. It is not a warehouse agent
and not an execution engine.

Trust boundary: Copilot may request intelligence and propose governed actions.
Copilot must never become an alternative approval or execution path.

Exports
-------
CopilotService    — orchestrates ASK / ANALYZE / ACT turns
CopilotIntent     — typed intent enum
CopilotTurn       — per-turn state
InMemoryCopilotStore — process-local conversation store
"""

from .models import CopilotIntent, CopilotTurn, CopilotConversation, CopilotAskResult
from .store import InMemoryCopilotStore
from .service import CopilotService

__all__ = [
    "CopilotIntent",
    "CopilotTurn",
    "CopilotConversation",
    "CopilotAskResult",
    "InMemoryCopilotStore",
    "CopilotService",
]
