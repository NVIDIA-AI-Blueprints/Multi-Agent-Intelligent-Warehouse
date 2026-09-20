# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
UX-1B: Agent Tasks API Tests

Tests for GET /api/v1/agent-tasks/* endpoints.

Security invariants verified:
    - Read-only (GET only — no POST/PUT/DELETE)
    - No chain_of_thought, scratchpad, raw prompts
    - No framework internals (LangGraph, deepagents)
    - Bounded response (no full conversation history)
    - AgentTaskView fields are structured MAIW state only

Serialization verified:
    - AgentTaskState → AgentTaskView
    - SOP step metadata included
    - Delegation results serialized
"""

from __future__ import annotations

import sys
from pathlib import Path
import pytest
from datetime import datetime, timezone

# The agent_tasks router is in the worktree — add the worktree API path before
# the editable-install path so tests exercise the worktree code.
_WORKTREE_API = Path(__file__).parents[2] / "apps" / "api"
if str(_WORKTREE_API) not in sys.path:
    sys.path.insert(0, str(_WORKTREE_API))

from maiw_agents.contracts.task import AgentTaskState, AgentTaskStatus, AgentResultRef

# ── Fixtures ───────────────────────────────────────────────────────────────────


def make_task(**kwargs) -> AgentTaskState:
    defaults = dict(
        task_id="test-task-001",
        agent_id="operations_coordination",
        sop_id="operations_coordination.wave_risk_resolution",
        sop_version="1.0",
        objective="Recover Wave 17 before carrier cutoff",
        status=AgentTaskStatus.RUNNING,
        current_step_id="diagnose",
        completed_steps=["establish_state"],
        trace_id="trace-abc123",
        context_snapshot_id="snap-001",
    )
    defaults.update(kwargs)
    return AgentTaskState(**defaults)


# ── Registry tests ────────────────────────────────────────────────────────────


class TestAgentTaskRegistry:
    def test_register_and_retrieve(self):
        from maiw_api.routers.agent_tasks import (
            register_agent_task,
            get_registered_task,
            clear_task_registry,
        )

        clear_task_registry()
        task = make_task()
        register_agent_task(task.task_id, task)
        retrieved = get_registered_task(task.task_id)
        assert retrieved is task

    def test_missing_task_returns_none(self):
        from maiw_api.routers.agent_tasks import (
            get_registered_task,
            clear_task_registry,
        )

        clear_task_registry()
        assert get_registered_task("nonexistent-task") is None

    def test_list_tasks(self):
        from maiw_api.routers.agent_tasks import (
            register_agent_task,
            list_registered_tasks,
            clear_task_registry,
        )

        clear_task_registry()
        t1 = make_task(task_id="t1")
        t2 = make_task(task_id="t2")
        register_agent_task(t1.task_id, t1)
        register_agent_task(t2.task_id, t2)
        tasks = list_registered_tasks()
        assert len(tasks) == 2

    def test_clear_registry(self):
        from maiw_api.routers.agent_tasks import (
            register_agent_task,
            list_registered_tasks,
            clear_task_registry,
        )

        register_agent_task("x", make_task())
        clear_task_registry()
        assert list_registered_tasks() == []


# ── Task view serialization ───────────────────────────────────────────────────


class TestAgentTaskViewSerialization:
    def test_status_serialized_as_string(self):
        from maiw_api.routers.agent_tasks import _build_task_view

        task = make_task()
        view = _build_task_view(task)
        assert isinstance(view.status, str)
        assert view.status == "RUNNING"

    def test_core_fields_serialized(self):
        from maiw_api.routers.agent_tasks import _build_task_view

        task = make_task()
        view = _build_task_view(task)
        assert view.task_id == "test-task-001"
        assert view.agent_id == "operations_coordination"
        assert view.sop_id == "operations_coordination.wave_risk_resolution"
        assert view.sop_version == "1.0"
        assert view.objective == "Recover Wave 17 before carrier cutoff"
        assert view.current_step_id == "diagnose"
        assert view.completed_steps == ["establish_state"]
        assert view.trace_id == "trace-abc123"
        assert view.context_snapshot_id == "snap-001"

    def test_timestamps_serialized_as_iso_strings(self):
        from maiw_api.routers.agent_tasks import _build_task_view

        task = make_task()
        view = _build_task_view(task)
        assert view.created_at is not None
        assert view.updated_at is not None
        # Should be ISO format
        datetime.fromisoformat(view.created_at)
        datetime.fromisoformat(view.updated_at)

    def test_delegation_results_serialized(self):
        from maiw_api.routers.agent_tasks import _build_task_view

        task = make_task()
        ref = AgentResultRef(
            child_task_id="child-labor-001",
            agent_id="labor",
            status="COMPLETED",
            assessment_summary="Labor constrained",
            candidate_action_count=2,
        )
        task = task.model_copy(update={"subagent_results": [ref]})
        view = _build_task_view(task)
        assert len(view.delegation_results) == 1
        dr = view.delegation_results[0]
        assert dr.child_task_id == "child-labor-001"
        assert dr.responding_agent == "labor"
        assert dr.status == "COMPLETED"
        assert dr.candidate_action_count == 2

    def test_no_chain_of_thought_field(self):
        """AgentTaskView must not expose chain_of_thought or scratchpad."""
        from maiw_api.routers.agent_tasks import AgentTaskView

        view_fields = set(AgentTaskView.model_fields.keys())
        forbidden = {
            "chain_of_thought",
            "scratchpad",
            "hidden_reasoning",
            "raw_prompt",
            "system_prompt",
        }
        violations = view_fields & forbidden
        assert violations == set(), f"Forbidden fields found: {violations}"

    def test_no_framework_internals(self):
        """AgentTaskView must not expose LangGraph or deepagents internal fields."""
        from maiw_api.routers.agent_tasks import AgentTaskView

        view_fields = set(AgentTaskView.model_fields.keys())
        forbidden = {
            "langgraph_state",
            "deepagents_checkpoint",
            "node_state",
            "graph_state",
        }
        violations = view_fields & forbidden
        assert violations == set(), f"Framework internal fields found: {violations}"

    def test_response_bounded_no_full_conversation(self):
        """AgentTaskView must not expose full conversation history."""
        from maiw_api.routers.agent_tasks import AgentTaskView

        view_fields = set(AgentTaskView.model_fields.keys())
        # Should have a reference to conversation_id, not a full conversation object
        assert "conversation_id" in view_fields
        assert "conversation" not in view_fields
        assert "messages" not in view_fields
        assert "turn_history" not in view_fields


# ── Read-only API invariant ───────────────────────────────────────────────────


class TestReadOnlyInvariant:
    def test_router_has_no_post_routes(self):
        """The agent-tasks router must have no POST, PUT, or DELETE routes."""
        from maiw_api.routers.agent_tasks import router

        non_get_methods = set()
        for route in router.routes:
            methods = getattr(route, "methods", set()) or set()
            for m in methods:
                if m.upper() not in {"GET", "HEAD", "OPTIONS"}:
                    non_get_methods.add(f"{m.upper()} {route.path}")  # type: ignore[attr-defined]
        assert non_get_methods == set(), f"Non-GET routes found: {non_get_methods}"


# ── SOP metadata loading ──────────────────────────────────────────────────────


class TestSOPMetadataLoading:
    def test_loads_wave_risk_resolution_sop(self):
        from maiw_api.routers.agent_tasks import _load_sop_metadata

        meta = _load_sop_metadata("operations_coordination.wave_risk_resolution")
        assert meta is not None
        assert meta["id"] == "operations_coordination.wave_risk_resolution"
        assert meta["version"] == "1.0"
        assert len(meta["steps"]) > 0
        # Verify step IDs match SOP YAML
        step_ids = [s["id"] for s in meta["steps"]]
        assert "establish_state" in step_ids
        assert "diagnose" in step_ids

    def test_loads_labor_constraint_assessment_sop(self):
        from maiw_api.routers.agent_tasks import _load_sop_metadata

        meta = _load_sop_metadata("labor.labor_constraint_assessment")
        assert meta is not None
        assert meta["agent"] == "labor"

    def test_steps_have_descriptions(self):
        from maiw_api.routers.agent_tasks import _load_sop_metadata

        meta = _load_sop_metadata("operations_coordination.wave_risk_resolution")
        assert meta is not None
        for step in meta["steps"]:
            # description may be None for some steps, but id and action are always present
            assert step["id"]
            assert step["action"]

    def test_unknown_sop_returns_none(self):
        from maiw_api.routers.agent_tasks import _load_sop_metadata

        meta = _load_sop_metadata("nonexistent.sop_name")
        assert meta is None

    def test_sop_steps_included_in_task_view(self):
        from maiw_api.routers.agent_tasks import (
            _build_task_view,
            register_agent_task,
            clear_task_registry,
        )

        clear_task_registry()
        task = make_task(sop_id="operations_coordination.wave_risk_resolution")
        register_agent_task(task.task_id, task)
        view = _build_task_view(task)
        assert len(view.sop_steps) > 0
        assert any(s.id == "establish_state" for s in view.sop_steps)


# ── AgentTaskView field invariants ────────────────────────────────────────────


class TestAgentTaskViewFields:
    def test_view_exposes_all_required_operator_fields(self):
        from maiw_api.routers.agent_tasks import AgentTaskView

        fields = set(AgentTaskView.model_fields.keys())
        required_operator = {
            "task_id",
            "agent_id",
            "sop_id",
            "sop_version",
            "objective",
            "status",
        }
        assert (
            required_operator <= fields
        ), f"Missing operator fields: {required_operator - fields}"

    def test_view_exposes_all_required_developer_fields(self):
        from maiw_api.routers.agent_tasks import AgentTaskView

        fields = set(AgentTaskView.model_fields.keys())
        required_dev = {
            "trace_id",
            "context_snapshot_id",
            "conversation_id",
            "copilot_turn_id",
            "stop_reason",
            "recommendation_id",
            "completed_steps",
            "iteration",
        }
        assert (
            required_dev <= fields
        ), f"Missing developer fields: {required_dev - fields}"

    def test_view_includes_sop_steps_for_ui(self):
        from maiw_api.routers.agent_tasks import AgentTaskView

        assert "sop_steps" in AgentTaskView.model_fields

    def test_view_includes_delegation_results(self):
        from maiw_api.routers.agent_tasks import AgentTaskView

        assert "delegation_results" in AgentTaskView.model_fields
