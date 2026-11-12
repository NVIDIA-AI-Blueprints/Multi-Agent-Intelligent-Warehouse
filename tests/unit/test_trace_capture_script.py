# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
scripts/trace_capture.py: the REASON section says when the router fell back.

The recaptured trace (#317) showed ``routing_reason: reasoning=HIGH requires
Super`` next to ``model_id: nemotron-3-ultra``: the reason names the preferred
role, and the fallback to Ultra was only in the server log. The script now
records ``fallback_from`` and ``fallback_reason`` and prints them under the
reason when a fallback happened.
"""

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "trace_capture.py"
TRACE = REPO / "artifacts" / "demo" / "labor_constraint_wave_risk_trace.json"


@pytest.fixture()
def tc():
    spec = importlib.util.spec_from_file_location("trace_capture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def trace() -> dict:
    return copy.deepcopy(json.loads(TRACE.read_text()))


def _reason_section(md: str) -> str:
    return md.split("### REASON")[1].split("###")[0]


def test_fallback_is_printed_under_the_routing_reason(tc, trace):
    reason = trace["analysis"]["reason"]
    reason["fallback_from"] = "super"
    reason["fallback_reason"] = (
        "role=super is disabled or policy-ineligible; escalated to ultra"
    )

    section = _reason_section(tc.render_md(trace))

    lines = [l.strip() for l in section.splitlines()]
    at = next(i for i, l in enumerate(lines) if l.startswith("routing_reason"))
    assert lines[at + 1] == "fallback_from      : super"
    assert lines[at + 2] == (
        "fallback_reason    : role=super is disabled or policy-ineligible; "
        "escalated to ultra"
    )


def test_no_fallback_lines_when_the_preferred_role_served(tc, trace):
    reason = trace["analysis"]["reason"]
    reason["fallback_from"] = None
    reason["fallback_reason"] = None

    section = _reason_section(tc.render_md(trace))

    assert "fallback_from" not in section
    assert "fallback_reason" not in section
