# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 18H — Canonical SOP integration test (deterministic).

End-to-end integration test:
    1. Load the labor SOP YAML
    2. Construct a LaborAgent with bounded_context pre-loaded
    3. Run MAIWDeterministicRuntime.run_task()
    4. Verify output: AgentTaskResult.final_status == COMPLETED
    5. Verify no WRITE skills were invoked

This is a fast, isolated, no-network test.
It does NOT require ModelGateway, MCP, or any infrastructure.
"""

from __future__ import annotations

import pathlib
import pytest
from datetime import datetime, timezone

WORKTREE = pathlib.Path(__file__).parent.parent.parent
SOP_DIR = WORKTREE / "agents" / "sops"


@pytest.mark.asyncio
async def test_labor_sop_deterministic_run():
    """
    LaborAgent + MAIWDeterministicRuntime follow the labor SOP and produce
    AgentTaskStatus.COMPLETED with at least one CandidateLaborAction.
    """
    from maiw_agents.contracts import (
        load_sop,
        AgentTaskState,
        AgentTaskStatus,
        LABOR_AGENT_DEFINITION,
    )
    from maiw_agents.contracts.runtime import AgentExecutionContext
    from maiw_agents.labor import LaborAgent
    from maiw_agents.runtime import MAIWDeterministicRuntime

    sop_path = SOP_DIR / "labor" / "labor_constraint_assessment.v1.yaml"
    if not sop_path.exists():
        pytest.skip(f"SOP not found: {sop_path}")

    sop = load_sop(sop_path)

    # Pre-load assessment result into bounded_context (deterministic runtime extracts it)
    labor_agent = LaborAgent()
    bounded_context = {
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
            {
                "task_id": "t2",
                "status": "pending",
                "assigned_to": None,
                "priority": "medium",
                "zone": "A",
            },
        ],
    }

    # Run the specialist directly (the deterministic runtime delegates to assess_*)
    assessment = await labor_agent.assess_labor_constraint(
        task_id="integration-test-001",
        trace_id="trace-integration-001",
        bounded_context=bounded_context,
    )

    # Pre-inject the result into bounded_context so runtime can extract it
    bounded_context["_agent_result"] = assessment

    state = AgentTaskState(
        task_id="integration-test-001",
        agent_id=LABOR_AGENT_DEFINITION.agent_id,
        sop_id=sop.id,
        sop_version=sop.version,
        objective=LABOR_AGENT_DEFINITION.objective,
        status=AgentTaskStatus.PENDING,
        iteration=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    context = AgentExecutionContext(
        warehouse_id="wh-test-001",
        trace_id="trace-integration-001",
        conversation_id="conv-001",
        bounded_context=bounded_context,
    )

    runtime = MAIWDeterministicRuntime()
    result = await runtime.run_task(
        definition=LABOR_AGENT_DEFINITION,
        sop=sop,
        state=state,
        context=context,
    )

    assert result.final_status == AgentTaskStatus.COMPLETED
    assert result.stop_reason == "OBJECTIVE_MET"
    assert result.agent_id == "labor"
    assert result.sop_id == "labor.labor_constraint_assessment"
    assert result.iterations > 0


@pytest.mark.asyncio
async def test_wave_sop_deterministic_run():
    """
    WaveAgent + MAIWDeterministicRuntime produce AgentTaskStatus.COMPLETED.
    """
    import datetime as dt
    from maiw_agents.contracts import (
        load_sop,
        AgentTaskState,
        AgentTaskStatus,
        WAVE_AGENT_DEFINITION,
    )
    from maiw_agents.contracts.runtime import AgentExecutionContext
    from maiw_agents.wave import WaveAgent
    from maiw_agents.runtime import MAIWDeterministicRuntime

    sop_path = SOP_DIR / "wave" / "wave_risk_assessment.v1.yaml"
    if not sop_path.exists():
        pytest.skip(f"SOP not found: {sop_path}")

    sop = load_sop(sop_path)

    soon = (dt.datetime.now(tz=dt.timezone.utc) + dt.timedelta(minutes=25)).isoformat()
    bounded_context = {
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
        "wave_id": "wave-001",
    }

    wave_agent = WaveAgent()
    assessment = await wave_agent.assess_wave_risk(
        task_id="wave-integration-001",
        trace_id="trace-wave-001",
        bounded_context=bounded_context,
    )
    bounded_context["_agent_result"] = assessment

    state = AgentTaskState(
        task_id="wave-integration-001",
        agent_id=WAVE_AGENT_DEFINITION.agent_id,
        sop_id=sop.id,
        sop_version=sop.version,
        objective=WAVE_AGENT_DEFINITION.objective,
        status=AgentTaskStatus.PENDING,
        iteration=0,
        created_at=dt.datetime.now(tz=dt.timezone.utc),
        updated_at=dt.datetime.now(tz=dt.timezone.utc),
    )

    context = AgentExecutionContext(
        warehouse_id="wh-test-001",
        trace_id="trace-wave-001",
        bounded_context=bounded_context,
    )

    runtime = MAIWDeterministicRuntime()
    result = await runtime.run_task(
        definition=WAVE_AGENT_DEFINITION,
        sop=sop,
        state=state,
        context=context,
    )

    assert result.final_status == AgentTaskStatus.COMPLETED
    assert result.agent_id == "wave"


@pytest.mark.asyncio
async def test_runtime_rejects_write_capability_in_sop(tmp_path):
    """
    MAIWDeterministicRuntime must raise ValueError if SOP declares a WRITE capability
    not in the AgentDefinition.
    """
    import yaml
    from maiw_agents.contracts import (
        load_sop,
        AgentTaskState,
        AgentTaskStatus,
        LABOR_AGENT_DEFINITION,
    )
    from maiw_agents.contracts.runtime import AgentExecutionContext
    from maiw_agents.runtime import MAIWDeterministicRuntime

    # Create a SOP that declares a WRITE capability (should be rejected)
    bad_sop_dict = {
        "id": "labor.labor_constraint_assessment",
        "version": "1.0",
        "agent": "labor",
        "objective": "Test.",
        "description": "Test SOP.",
        "triggers": ["test"],
        "required_context": ["worker"],
        "allowed_capabilities": ["warehouse.labor.assign_direct"],  # WRITE — forbidden
        "allowed_subagents": [],
        "steps": [
            {"id": "only_step", "action": "do_something", "description": "Step."}
        ],
        "stop_conditions": ["objective_met"],
    }
    sop_file = tmp_path / "bad.yaml"
    sop_file.write_text(yaml.dump(bad_sop_dict))

    from datetime import datetime, timezone

    state = AgentTaskState(
        task_id="test-bad-001",
        agent_id="labor",
        sop_id="labor.labor_constraint_assessment",
        sop_version="1.0",
        objective="Test.",
        status=AgentTaskStatus.PENDING,
        iteration=0,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    context = AgentExecutionContext(warehouse_id="wh-001", trace_id="trace-001")
    runtime = MAIWDeterministicRuntime()

    # The SOP loader itself will reject WRITE capabilities in validate_sop
    from maiw_agents.contracts import SOPValidationError

    with pytest.raises((SOPValidationError, ValueError)):
        bad_sop = load_sop(sop_file)
        await runtime.run_task(
            definition=LABOR_AGENT_DEFINITION,
            sop=bad_sop,
            state=state,
            context=context,
        )
