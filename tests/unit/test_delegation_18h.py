# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 18H — Delegation contract tests.

Tests:
    - AgentDelegationRequest / AgentDelegationResult round-trip
    - handle_delegation() routes to LaborAgent correctly
    - handle_delegation() routes to WaveAgent correctly
    - handle_delegation() with no matching specialist returns escalated
    - LaborAgent.assess_labor_constraint() — idle workers → candidate actions
    - LaborAgent.assess_labor_constraint() — no idle workers → no_idle_workers constraint
    - WaveAgent.assess_wave_risk() — at-risk tasks → candidate actions
    - WaveAgent.assess_wave_risk() — no risk → no_constraint
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone


def _make_delegation_request(
    target: str, bounded_context: dict
) -> "AgentDelegationRequest":
    from maiw_agents.contracts import AgentDelegationRequest

    return AgentDelegationRequest(
        delegation_id="del-test-001",
        parent_task_id="parent-task-001",
        requesting_agent="operations_coordination",
        target_agent=target,
        objective="Assess constraint.",
        context_snapshot_id="snap-001",
        bounded_context=bounded_context,
        trace_id="trace-001",
        created_at=datetime.now(timezone.utc),
    )


# ── LaborAgent tests ──────────────────────────────────────────────────────────


class TestLaborAgent:
    """LaborAgent.assess_labor_constraint() output contract."""

    @pytest.mark.asyncio
    async def test_idle_workers_with_tasks_produces_candidates(self):
        from maiw_agents.labor import LaborAgent

        agent = LaborAgent()
        bounded = {
            "workers": [
                {
                    "worker_id": "w1",
                    "status": "active",
                    "current_task_id": None,
                    "zone": "A",
                },
                {
                    "worker_id": "w2",
                    "status": "active",
                    "current_task_id": "t99",
                    "zone": "B",
                },
            ],
            "pending_tasks": [
                {
                    "task_id": "t1",
                    "status": "pending",
                    "assigned_to": None,
                    "priority": "high",
                    "zone": "A",
                },
            ],
        }
        assessment = await agent.assess_labor_constraint(
            task_id="test-001", trace_id="trace-001", bounded_context=bounded
        )
        assert assessment.total_workers == 2
        assert assessment.idle_workers == 1
        assert assessment.active_workers == 1
        assert assessment.unassigned_task_count == 1
        assert assessment.primary_constraint == "idle_workers_available"
        assert len(assessment.candidate_actions) == 1
        action = assessment.candidate_actions[0]
        assert action.worker_id == "w1"
        assert action.task_id == "t1"
        assert action.feasible is True

    @pytest.mark.asyncio
    async def test_no_idle_workers_constraint(self):
        from maiw_agents.labor import LaborAgent

        agent = LaborAgent()
        bounded = {
            "workers": [
                {"worker_id": "w1", "status": "active", "current_task_id": "t99"},
            ],
            "pending_tasks": [
                {"task_id": "t1", "status": "pending", "assigned_to": None},
            ],
        }
        assessment = await agent.assess_labor_constraint(
            task_id="test-002", trace_id="trace-002", bounded_context=bounded
        )
        assert assessment.primary_constraint == "no_idle_workers"
        assert assessment.candidate_actions == []

    @pytest.mark.asyncio
    async def test_no_unassigned_tasks_no_constraint(self):
        from maiw_agents.labor import LaborAgent

        agent = LaborAgent()
        bounded = {
            "workers": [
                {"worker_id": "w1", "status": "active", "current_task_id": "t1"},
            ],
            "pending_tasks": [
                {"task_id": "t1", "status": "pending", "assigned_to": "w1"},
            ],
        }
        assessment = await agent.assess_labor_constraint(
            task_id="test-003", trace_id="trace-003", bounded_context=bounded
        )
        assert assessment.primary_constraint == "no_constraint"

    @pytest.mark.asyncio
    async def test_candidate_actions_never_write(self):
        from maiw_agents.labor import LaborAgent, CandidateLaborAction

        agent = LaborAgent()
        bounded = {
            "workers": [
                {"worker_id": "w1", "status": "active", "current_task_id": None},
            ],
            "pending_tasks": [
                {"task_id": "t1", "status": "pending", "assigned_to": None},
            ],
        }
        assessment = await agent.assess_labor_constraint(
            task_id="test-004", trace_id="trace-004", bounded_context=bounded
        )
        # Verify the type — should be CandidateLaborAction not a write tool call
        for action in assessment.candidate_actions:
            assert isinstance(action, CandidateLaborAction)
            # Must not have any "execute" or "direct" flag
            assert not hasattr(action, "execute")


# ── WaveAgent tests ───────────────────────────────────────────────────────────


class TestWaveAgent:
    """WaveAgent.assess_wave_risk() output contract."""

    @pytest.mark.asyncio
    async def test_at_risk_tasks_produce_candidates(self):
        from maiw_agents.wave import WaveAgent
        import datetime

        soon = (
            datetime.datetime.now(tz=datetime.timezone.utc)
            + datetime.timedelta(minutes=30)
        ).isoformat()
        bounded = {
            "wave_tasks": [
                {
                    "task_id": "wt1",
                    "status": "pending",
                    "priority": "high",
                    "at_risk": True,
                },
                {
                    "task_id": "wt2",
                    "status": "pending",
                    "priority": "low",
                    "at_risk": False,
                },
                {
                    "task_id": "wt3",
                    "status": "in_progress",
                    "priority": "medium",
                    "at_risk": False,
                },
            ],
            "carrier_cutoff_iso": soon,
            "wave_id": "wave-001",
        }
        agent = WaveAgent()
        assessment = await agent.assess_wave_risk(
            task_id="wave-test-001", trace_id="trace-001", bounded_context=bounded
        )
        assert assessment.at_risk_task_count >= 1
        assert assessment.time_to_cutoff_minutes is not None
        assert assessment.time_to_cutoff_minutes <= 31
        assert len(assessment.candidate_actions) > 0

    @pytest.mark.asyncio
    async def test_no_at_risk_tasks_no_constraint(self):
        from maiw_agents.wave import WaveAgent

        bounded = {
            "wave_tasks": [
                {
                    "task_id": "wt1",
                    "status": "in_progress",
                    "priority": "high",
                    "at_risk": False,
                },
                {"task_id": "wt2", "status": "completed", "at_risk": False},
            ],
            "carrier_cutoff_iso": None,
        }
        agent = WaveAgent()
        assessment = await agent.assess_wave_risk(
            task_id="wave-test-002", trace_id="trace-002", bounded_context=bounded
        )
        assert assessment.primary_constraint == "no_constraint"
        assert assessment.candidate_actions == []

    @pytest.mark.asyncio
    async def test_candidate_wave_actions_not_write(self):
        from maiw_agents.wave import WaveAgent, CandidateWaveAction
        import datetime

        soon = (
            datetime.datetime.now(tz=datetime.timezone.utc)
            + datetime.timedelta(minutes=20)
        ).isoformat()
        bounded = {
            "wave_tasks": [
                {
                    "task_id": "wt1",
                    "status": "pending",
                    "priority": "high",
                    "at_risk": True,
                },
                {
                    "task_id": "wt2",
                    "status": "pending",
                    "priority": "low",
                    "at_risk": False,
                },
            ],
            "carrier_cutoff_iso": soon,
        }
        agent = WaveAgent()
        assessment = await agent.assess_wave_risk(
            task_id="wave-test-003", trace_id="trace-003", bounded_context=bounded
        )
        for action in assessment.candidate_actions:
            assert isinstance(action, CandidateWaveAction)
            # intervention_type must not be a direct write
            assert action.intervention_type in (
                "reprioritize",
                "resequence",
                "defer_low_priority",
                "escalate",
            )


# ── handle_delegation() routing tests ────────────────────────────────────────


class TestHandleDelegation:
    """handle_delegation() must route to the correct specialist."""

    @pytest.mark.asyncio
    async def test_routes_to_labor_agent(self):
        from maiw_agents.runtime.deterministic import handle_delegation
        from maiw_agents.labor import LaborAgent

        labor_agent = LaborAgent()
        req = _make_delegation_request(
            "labor",
            {
                "workers": [
                    {"worker_id": "w1", "status": "active", "current_task_id": None}
                ],
                "pending_tasks": [
                    {"task_id": "t1", "status": "pending", "assigned_to": None}
                ],
            },
        )
        result = await handle_delegation(req, labor_agent=labor_agent)
        assert result.responding_agent == "labor"
        assert result.status == "completed"
        assert "primary_constraint" in result.assessment

    @pytest.mark.asyncio
    async def test_routes_to_wave_agent(self):
        from maiw_agents.runtime.deterministic import handle_delegation
        from maiw_agents.wave import WaveAgent

        wave_agent = WaveAgent()
        req = _make_delegation_request(
            "wave",
            {
                "wave_tasks": [],
                "carrier_cutoff_iso": None,
            },
        )
        result = await handle_delegation(req, wave_agent=wave_agent)
        assert result.responding_agent == "wave"
        assert result.status == "completed"

    @pytest.mark.asyncio
    async def test_no_specialist_returns_escalated(self):
        from maiw_agents.runtime.deterministic import handle_delegation

        req = _make_delegation_request("equipment", {"equipment": []})
        result = await handle_delegation(req)
        assert result.status == "escalated"
        assert result.escalation_reason is not None

    @pytest.mark.asyncio
    async def test_delegation_result_has_required_fields(self):
        from maiw_agents.runtime.deterministic import handle_delegation
        from maiw_agents.labor import LaborAgent

        labor_agent = LaborAgent()
        req = _make_delegation_request(
            "labor",
            {
                "workers": [],
                "pending_tasks": [],
            },
        )
        result = await handle_delegation(req, labor_agent=labor_agent)
        assert result.delegation_id == "del-test-001"
        assert result.requesting_agent == "operations_coordination"
        assert result.child_task_id is not None
        assert result.trace_id == "trace-001"
        assert result.completed_at is not None


# ── GovernanceOutcome ─────────────────────────────────────────────────────────


class TestGovernanceOutcome:
    """GovernanceOutcome Pydantic model must serialize correctly."""

    def test_governance_outcome_serializes(self):
        from maiw_agents.contracts import GovernanceOutcome
        from datetime import datetime, timezone

        outcome = GovernanceOutcome(
            proposal_id="prop-001",
            decision_outcome="approved",
            approval_status="approved",
            execution_id="exec-001",
            execution_status="succeeded",
            resulting_context_snapshot_id="snap-002",
            trace_id="trace-001",
            received_at=datetime.now(timezone.utc),
        )
        d = outcome.model_dump()
        assert d["proposal_id"] == "prop-001"
        assert d["decision_outcome"] == "approved"
        assert d["execution_status"] == "succeeded"
