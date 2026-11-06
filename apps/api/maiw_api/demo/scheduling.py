# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Default time slots for governed proposals built against the demo world.

Shared by the copilot's GovernedActionOrchestrator and the demo
analyze-disruption route, so both propose the same slot.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


def default_scheduled_for(ctrl: Any = None) -> str:
    """
    Next-day slot for maintenance proposals that carry no explicit time.

    Demo mode runs on the world's SimulationClock, which is deliberately not
    tied to wall time, so "tomorrow" is the simulated now + 1 day. Without a
    simulation clock it falls back to UTC wall time.

    The slot is fixed when the proposal is built. The DecisionEngine rejects it
    at authorization if the clock has passed it by then (rule
    ``maintenance.scheduled_for_past``), so a late approval never executes a
    slot in the past.
    """
    clock = getattr(getattr(ctrl, "world", None), "clock", None)
    now = clock.now() if clock is not None else datetime.now(timezone.utc)
    return (now + timedelta(days=1)).isoformat()
