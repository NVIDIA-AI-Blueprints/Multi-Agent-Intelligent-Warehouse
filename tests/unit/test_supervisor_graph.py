# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for the supervisor orchestration graph.

These tests stub the agent nodes, so they run without NVIDIA API keys, a
database or any MCP backend.
"""

import asyncio
import time
from typing import Any, Dict

import pytest

from src.api.graphs.supervisor_graph import (
    SupervisorPlannerGraph,
    compose_narrative,
    detect_conflicts,
    merge_agent_responses,
    response_score,
    safety_veto,
    score_domains,
    select_agents,
)

# A cross-domain query: asset state, hazard containment, task reassignment and
# downstream impact all apply. Single-route planning can only answer one of them.
BREAKDOWN_QUERY = (
    "Forklift C-02 broke down in zone A - what are the consequences "
    "and should we reassign the picking tasks?"
)


def _response(
    text: str,
    confidence: float = 0.8,
    response_type: str = "info",
    tools: Any = None,
    recommendations: Any = None,
    actions: Any = None,
) -> Dict[str, Any]:
    """Build an agent response payload in the shape agents actually return."""
    return {
        "natural_language": text,
        "data": {},
        "recommendations": recommendations or [],
        "confidence": confidence,
        "response_type": response_type,
        "mcp_tools_used": tools or [],
        "actions_taken": actions or [],
    }


# ---------------------------------------------------------------------------
# Reducer
# ---------------------------------------------------------------------------


def test_merge_agent_responses_unions_branches():
    left = {"equipment": {"natural_language": "a"}}
    right = {"safety": {"natural_language": "b"}}
    assert set(merge_agent_responses(left, right)) == {"equipment", "safety"}


def test_merge_agent_responses_handles_none():
    assert merge_agent_responses(None, None) == {}
    assert merge_agent_responses(None, {"a": 1}) == {"a": 1}


# ---------------------------------------------------------------------------
# Agent selection
# ---------------------------------------------------------------------------


def test_score_domains_detects_cross_domain_signals():
    scores = score_domains(BREAKDOWN_QUERY)
    assert scores["equipment"] > 0
    assert scores["safety"] > 0
    assert scores["operations"] > 0
    assert scores["forecasting"] > 0


def test_select_agents_fans_out_on_cross_domain_query():
    selected = select_agents(BREAKDOWN_QUERY, "equipment")
    agents = [item["agent"] for item in selected]

    assert agents[0] == "equipment", "primary intent must stay first"
    assert selected[0]["priority"] == 0
    assert len(agents) > 1, "cross-domain query must engage more than one agent"
    assert len(agents) == len(set(agents)), "no duplicate agents"
    assert {"safety", "operations", "forecasting"} & set(agents)


def test_select_agents_keeps_single_agent_for_narrow_query():
    selected = select_agents("Upload this invoice PDF for processing", "document")
    assert [item["agent"] for item in selected] == ["document"]


def test_select_agents_respects_max_cap():
    selected = select_agents(BREAKDOWN_QUERY, "equipment", max_agents=2)
    assert len(selected) == 2


def test_select_agents_cap_of_one_disables_fan_out():
    selected = select_agents(BREAKDOWN_QUERY, "equipment", max_agents=1)
    assert [item["agent"] for item in selected] == ["equipment"]


def test_select_agents_falls_back_to_general_for_unknown_intent():
    selected = select_agents("hello there", "something_else")
    assert selected[0]["agent"] == "general"


# ---------------------------------------------------------------------------
# Scoring and arbitration policy
# ---------------------------------------------------------------------------


def test_response_score_rewards_tool_grounded_answers():
    grounded = _response("x", confidence=0.8, tools=["get_equipment_status"])
    ungrounded = _response("x", confidence=0.8)
    assert response_score(grounded, 0) > response_score(ungrounded, 0)


def test_response_score_penalises_lower_priority():
    payload = _response("x", confidence=0.8)
    assert response_score(payload, 0) > response_score(payload, 1)


def test_response_score_tolerates_malformed_confidence():
    assert response_score({"confidence": "not-a-number"}, 0) == 0.0


def test_safety_veto_triggers_on_blocking_type():
    responses = {"safety": _response("locked out", 0.9, "loto_procedure")}
    assert safety_veto(responses) is True


def test_safety_veto_ignores_low_confidence():
    responses = {"safety": _response("locked out", 0.2, "loto_procedure")}
    assert safety_veto(responses) is False


def test_safety_veto_ignores_non_blocking_type():
    responses = {"safety": _response("here is a policy", 0.95, "policy_info")}
    assert safety_veto(responses) is False


def test_safety_veto_absent_without_safety_agent():
    assert safety_veto({"equipment": _response("fine", 0.9)}) is False


def test_detect_conflicts_flags_action_under_active_veto():
    responses = {
        "safety": _response("area locked out", 0.9, "loto_procedure"),
        "operations": _response("reassigned", 0.8, recommendations=["Reassign to C-05"]),
    }
    conflicts = detect_conflicts(responses, veto_active=True)
    assert [c["agent"] for c in conflicts] == ["operations"]


def test_detect_conflicts_empty_without_veto():
    responses = {"operations": _response("ok", 0.8, recommendations=["do it"])}
    assert detect_conflicts(responses, veto_active=False) == []


# ---------------------------------------------------------------------------
# Narrative composition
# ---------------------------------------------------------------------------


def test_compose_narrative_single_agent_is_verbatim():
    """Single-agent output must stay byte-identical to the existing planner."""
    ordered = [("equipment", _response("Forklift C-02 is offline."))]
    assert compose_narrative(ordered) == "Forklift C-02 is offline."


def test_compose_narrative_multi_agent_labels_contributions():
    ordered = [
        ("safety", _response("Zone A is cordoned off.")),
        ("operations", _response("Three picking tasks moved to C-05.")),
    ]
    narrative = compose_narrative(ordered)
    assert narrative.startswith("Zone A is cordoned off.")
    assert "Operations" in narrative
    assert "C-05" in narrative


def test_compose_narrative_empty_input():
    assert compose_narrative([]) == ""


# ---------------------------------------------------------------------------
# Graph execution
# ---------------------------------------------------------------------------


def _build_stubbed_graph(
    primary_intent: str,
    payloads: Dict[str, Dict[str, Any]],
    delay: float = 0.0,
):
    """Compile a supervisor graph whose routing and agents are stubbed."""
    supervisor = SupervisorPlannerGraph()

    async def fake_route(state):
        state["user_intent"] = primary_intent
        state["routing_decision"] = primary_intent
        return state

    supervisor._mcp_route_intent = fake_route

    def make_agent(name: str):
        async def _agent(state):
            if delay:
                await asyncio.sleep(delay)
            state["agent_responses"][name] = payloads.get(
                name, _response(f"{name} had nothing to add.")
            )
            return state

        return _agent

    for name in ("equipment", "operations", "safety", "forecasting", "document", "general"):
        setattr(supervisor, f"_mcp_{name}_agent", make_agent(name))

    return supervisor._create_graph()


def _initial_state(message: str) -> Dict[str, Any]:
    from langchain_core.messages import HumanMessage

    return {
        "messages": [HumanMessage(content=message)],
        "user_intent": None,
        "routing_decision": None,
        "agent_responses": {},
        "final_response": None,
        "context": {},
        "session_id": "test",
        "mcp_results": None,
        "tool_execution_plan": None,
        "available_tools": None,
        "enable_reasoning": False,
        "reasoning_types": None,
        "reasoning_chain": None,
        "selected_agents": None,
        "routing_confidence": None,
        "conflicts": None,
        "decision_path": None,
        "arbitration": None,
    }


@pytest.mark.asyncio
async def test_graph_fans_out_and_merges_cross_domain_query():
    """The flagship case: one query, several domains, one coherent answer."""
    payloads = {
        "equipment": _response(
            "Forklift C-02 is offline pending repair.",
            confidence=0.9,
            tools=["get_equipment_status"],
        ),
        "safety": _response(
            "Zone A aisle is obstructed; cordon it off.",
            confidence=0.85,
            tools=["log_incident"],
        ),
        "operations": _response(
            "Three picking tasks can move to C-05.",
            confidence=0.8,
            tools=["get_task_status"],
        ),
        "forecasting": _response(
            "Expect roughly 18 minutes of extra wave latency.",
            confidence=0.7,
        ),
    }
    graph = _build_stubbed_graph("equipment", payloads)
    result = await graph.ainvoke(_initial_state(BREAKDOWN_QUERY))

    contributing = result["context"]["contributing_agents"]
    assert len(contributing) > 1, "cross-domain query must merge several agents"

    narrative = result["final_response"]
    assert "C-02" in narrative
    assert any(
        marker in narrative for marker in ("Zone A", "C-05", "18 minutes")
    ), "the merged answer must carry secondary domains, not just the primary one"

    structured = result["context"]["structured_response"]
    assert structured["response_type"] == "multi_agent_summary"
    assert structured["lead_agent"] in contributing
    assert set(structured["data"]) == set(contributing)
    assert result["decision_path"] in {"confidence_merge", "safety_veto"}


@pytest.mark.asyncio
async def test_graph_runs_agents_concurrently():
    """Fan-out latency must approach the slowest agent, not their sum."""
    delay = 0.20
    graph = _build_stubbed_graph("equipment", {}, delay=delay)

    started = time.perf_counter()
    result = await graph.ainvoke(_initial_state(BREAKDOWN_QUERY))
    elapsed = time.perf_counter() - started

    agent_count = len(result["context"]["contributing_agents"])
    assert agent_count >= 2, "test needs a fan-out to be meaningful"
    assert elapsed < delay * agent_count, (
        f"{agent_count} agents took {elapsed:.3f}s; "
        f"serial execution would need ~{delay * agent_count:.3f}s"
    )


@pytest.mark.asyncio
async def test_graph_single_agent_path_is_unchanged():
    """A narrow query must behave exactly like the single-route planner."""
    payloads = {"document": _response("Invoice INV-42 was extracted.", confidence=0.9)}
    graph = _build_stubbed_graph("document", payloads)
    result = await graph.ainvoke(
        _initial_state("Upload this invoice PDF for processing")
    )

    assert result["context"]["contributing_agents"] == ["document"]
    assert result["final_response"] == "Invoice INV-42 was extracted."
    assert result["decision_path"] == "single_agent"
    # No multi-agent envelope is introduced on the single-agent path.
    assert result["context"]["structured_response"]["response_type"] == "info"


@pytest.mark.asyncio
async def test_graph_safety_veto_leads_and_suppresses_conflicting_recommendations():
    payloads = {
        "safety": _response(
            "Zone A is under lockout/tagout; no equipment may enter.",
            confidence=0.95,
            response_type="loto_procedure",
            tools=["lockout_tagout_request"],
            recommendations=["Keep the aisle cordoned until sign-off"],
        ),
        "operations": _response(
            "Reassigning picks through zone A.",
            confidence=0.99,
            tools=["assign_task"],
            recommendations=["Route pickers through zone A"],
        ),
    }
    graph = _build_stubbed_graph("operations", payloads)
    result = await graph.ainvoke(_initial_state(BREAKDOWN_QUERY))

    assert result["decision_path"] == "safety_veto"
    # Safety leads despite operations having the higher raw confidence.
    assert result["final_response"].startswith("Zone A is under lockout")
    structured = result["context"]["structured_response"]
    assert structured["lead_agent"] == "safety"
    assert structured["recommendations"] == ["Keep the aisle cordoned until sign-off"]
    assert "Route pickers through zone A" not in structured["recommendations"]
    assert [c["agent"] for c in result["conflicts"]] == ["operations"]


@pytest.mark.asyncio
async def test_graph_drops_failed_agents_but_keeps_the_turn():
    payloads = {
        "equipment": _response("Forklift C-02 is offline.", confidence=0.9),
        "safety": {
            "natural_language": "",
            "response_type": "error",
            "confidence": 0.0,
            "data": {"error": "boom"},
        },
    }
    graph = _build_stubbed_graph("equipment", payloads)
    result = await graph.ainvoke(_initial_state(BREAKDOWN_QUERY))

    assert "safety" not in result["context"]["contributing_agents"]
    assert "Forklift C-02 is offline." in result["final_response"]


@pytest.mark.asyncio
async def test_graph_recovers_when_every_agent_fails():
    failing = {
        name: {"natural_language": "", "response_type": "error", "confidence": 0.0}
        for name in ("equipment", "safety", "operations", "forecasting")
    }
    graph = _build_stubbed_graph("equipment", failing)
    result = await graph.ainvoke(_initial_state(BREAKDOWN_QUERY))

    assert result["decision_path"] == "no_usable_response"
    assert result["final_response"]


@pytest.mark.asyncio
async def test_planner_factory_honours_the_feature_flag(monkeypatch):
    """The flag must switch the planner returned to the API layer."""
    import src.api.graphs.mcp_integrated_planner_graph as planner_module
    import src.api.graphs.supervisor_graph as supervisor_module

    sentinel = object()

    async def fake_supervisor():
        return sentinel

    monkeypatch.setattr(supervisor_module, "get_supervisor_graph", fake_supervisor)
    monkeypatch.setattr(planner_module, "_mcp_planner_graph", None)

    monkeypatch.setenv("ENABLE_MULTI_AGENT_SUPERVISOR", "true")
    assert await planner_module.get_mcp_planner_graph() is sentinel

    monkeypatch.setenv("ENABLE_MULTI_AGENT_SUPERVISOR", "false")
    assert await planner_module.get_mcp_planner_graph() is not sentinel


def test_supervisor_enabled_reads_common_truthy_values(monkeypatch):
    from src.api.graphs.supervisor_graph import supervisor_enabled

    monkeypatch.delenv("ENABLE_MULTI_AGENT_SUPERVISOR", raising=False)
    assert supervisor_enabled() is False
    for value in ("true", "TRUE", "1", "yes", "on"):
        monkeypatch.setenv("ENABLE_MULTI_AGENT_SUPERVISOR", value)
        assert supervisor_enabled() is True
    monkeypatch.setenv("ENABLE_MULTI_AGENT_SUPERVISOR", "false")
    assert supervisor_enabled() is False


@pytest.mark.asyncio
async def test_graph_agent_exception_does_not_break_the_turn():
    supervisor = SupervisorPlannerGraph()

    async def fake_route(state):
        state["user_intent"] = "equipment"
        state["routing_decision"] = "equipment"
        return state

    supervisor._mcp_route_intent = fake_route

    async def exploding(state):
        raise RuntimeError("agent crashed")

    async def working(state):
        state["agent_responses"]["equipment"] = _response("Forklift C-02 is offline.")
        return state

    for name in ("operations", "safety", "forecasting", "document", "general"):
        setattr(supervisor, f"_mcp_{name}_agent", exploding)
    supervisor._mcp_equipment_agent = working

    graph = supervisor._create_graph()
    result = await graph.ainvoke(_initial_state(BREAKDOWN_QUERY))

    assert "Forklift C-02 is offline." in result["final_response"]
