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

"""
Supervisor Orchestration Graph - multi-agent fan-out with decision arbitration.

The default MCP planner graph (`mcp_integrated_planner_graph.py`) routes every
query to exactly one specialized agent. Cross-domain queries are therefore only
answered from a single perspective. A query such as "forklift C-02 broke down in
zone A, what are the consequences and what should we do?" spans equipment
(asset state), safety (hazard containment), operations (task reassignment) and
forecasting (throughput impact), but only one of those agents ever runs.

This module adds an opt-in supervisor that:

1. selects the *set* of agents relevant to a query (not just the top one);
2. runs them concurrently (fan-out via LangGraph ``Send``);
3. merges their responses through a reducer (fan-in);
4. arbitrates the merged result with a deterministic policy - safety-first veto,
   then confidence-weighted ranking;
5. optionally escalates residual conflicts to an LLM arbiter.

The supervisor reuses the agent nodes of :class:`MCPPlannerGraph` unchanged, so
agent behavior is identical; only orchestration differs. It is disabled by
default and enabled with ``ENABLE_MULTI_AGENT_SUPERVISOR=true``.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Annotated, Any, Callable, Dict, List, Optional, Tuple, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.types import Send

from src.api.graphs.mcp_integrated_planner_graph import (
    MCPPlannerGraph,
    MCPWarehouseState,
    _extract_message_text,
)
from src.api.utils.log_utils import sanitize_log_data

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: Agents that may take part in a fan-out, in canonical order.
SUPERVISED_AGENTS: Tuple[str, ...] = (
    "equipment",
    "operations",
    "safety",
    "forecasting",
    "document",
)

#: Human readable labels used when composing a multi-agent answer.
DOMAIN_LABELS: Dict[str, str] = {
    "equipment": "Equipment & assets",
    "operations": "Operations",
    "safety": "Safety & compliance",
    "forecasting": "Forecasting",
    "document": "Documents",
    "general": "General",
}

#: High precision secondary-domain triggers.
#:
#: These are deliberately narrower than ``MCPIntentClassifier``'s keyword lists,
#: which overlap heavily (for example ``"action"`` and ``"report"`` appear in the
#: safety list) and would fan out on almost every query. Terms here are only used
#: to decide whether a domain should be added *in addition to* the primary intent
#: chosen by the existing keyword + semantic router.
#:
#: Known limitation: like the rest of the routing layer these triggers are
#: English-only. Non-English deployments currently rely on the semantic router
#: for the primary intent and will under-detect secondary domains.
DOMAIN_TRIGGERS: Dict[str, Tuple[str, ...]] = {
    # Equipment-failure terms are intentionally included: ``MCPIntentClassifier``
    # already classifies "malfunction" and "failure" as safety keywords, since a
    # machine failing inside an operating area is a hazard event.
    "safety": (
        "safety", "incident", "hazard", "danger", "dangerous", "unsafe", "injury",
        "accident", "emergency", "evacuate", "evacuation", "lockout", "tagout",
        "loto", "ppe", "spill", "leak", "fire", "flood", "flooding", "risk",
        "compliance", "violation", "near miss",
        "breakdown", "broke down", "broken down", "out of service", "malfunction",
        "failure",
    ),
    "equipment": (
        "equipment", "forklift", "conveyor", "scanner", "amr", "agv", "truck",
        "pallet jack", "machine", "machinery", "asset", "battery", "telemetry",
        "maintenance", "breakdown", "broken", "broke down", "out of service",
        "malfunction", "failure", "repair",
    ),
    "operations": (
        "task", "tasks", "wave", "waves", "order", "orders", "pick", "picking",
        "pack", "packing", "putaway", "shift", "worker", "workers", "staff",
        "employee", "employees", "crew", "assign", "reassign", "reassignment",
        "reschedule", "workload", "throughput", "backlog", "workflow",
    ),
    "forecasting": (
        "forecast", "forecasting", "demand", "predict", "prediction", "projection",
        "trend", "reorder", "replenish", "replenishment", "stockout", "impact",
        "consequence", "consequences", "delay", "delays", "eta", "sla",
        "downstream",
    ),
    "document": (
        "document", "documents", "invoice", "receipt", "bol", "bill of lading",
        "purchase order", "ocr", "upload", "scan", "pdf", "paperwork",
    ),
}

#: Safety response types that carry a hard operational block. When the safety
#: agent returns one of these with sufficient confidence, its constraint wins
#: over any recommendation produced by another agent in the same turn.
DEFAULT_SAFETY_BLOCKING_TYPES: Tuple[str, ...] = (
    "incident_logged",
    "loto_procedure",
    "alert_broadcast",
    "corrective_action_plan",
    "hazard_block",
    "compliance_block",
)


def _getenv_bool(key: str, default: bool = False) -> bool:
    """Read a boolean environment variable."""
    return os.getenv(key, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _getenv_int(key: str, default: int) -> int:
    """Read an integer environment variable, falling back on malformed input."""
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid int for %s, using default %s", key, default)
        return default


def _getenv_float(key: str, default: float) -> float:
    """Read a float environment variable, falling back on malformed input."""
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        logger.warning("Invalid float for %s, using default %s", key, default)
        return default


def supervisor_enabled() -> bool:
    """Whether the supervisor should replace the single-route planner graph."""
    return _getenv_bool("ENABLE_MULTI_AGENT_SUPERVISOR", False)


def _max_parallel_agents() -> int:
    """Upper bound on concurrently executed agents (latency and cost guard)."""
    return max(1, _getenv_int("SUPERVISOR_MAX_PARALLEL_AGENTS", 4))


def _min_secondary_hits() -> int:
    """Distinct trigger terms required before adding a secondary domain."""
    return max(1, _getenv_int("SUPERVISOR_MIN_SECONDARY_HITS", 1))


def _safety_veto_min_confidence() -> float:
    """Minimum safety confidence required to trigger the veto."""
    return _getenv_float("SUPERVISOR_SAFETY_VETO_MIN_CONFIDENCE", 0.6)


def _arbiter_enabled() -> bool:
    """Whether unresolved conflicts escalate to the LLM arbiter."""
    return _getenv_bool("SUPERVISOR_ENABLE_ARBITER", False)


def _safety_blocking_types() -> frozenset[str]:
    """Configurable set of blocking safety response types."""
    raw = os.getenv("SUPERVISOR_SAFETY_BLOCKING_TYPES")
    if not raw:
        return frozenset(DEFAULT_SAFETY_BLOCKING_TYPES)
    return frozenset(item.strip() for item in raw.split(",") if item.strip())


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


def merge_agent_responses(
    left: Optional[Dict[str, Any]], right: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Fan-in reducer merging responses written by concurrent agent nodes.

    Without a reducer LangGraph rejects two branches writing the same channel in
    one superstep. Each agent writes under its own key, so a shallow union is
    both sufficient and order independent.
    """
    merged: Dict[str, Any] = dict(left or {})
    merged.update(right or {})
    return merged


class SupervisorWarehouseState(MCPWarehouseState):
    """Warehouse state extended for concurrent multi-agent execution.

    ``agent_responses`` is re-declared with a reducer so parallel branches merge
    instead of colliding; the remaining fields record how the final answer was
    reached, which is what makes the arbitration auditable.
    """

    agent_responses: Annotated[Dict[str, Any], merge_agent_responses]
    selected_agents: Optional[List[Dict[str, Any]]]
    routing_confidence: Optional[float]
    conflicts: Optional[List[Dict[str, Any]]]
    decision_path: Optional[str]
    arbitration: Optional[Dict[str, Any]]


# ---------------------------------------------------------------------------
# Agent selection
# ---------------------------------------------------------------------------


def score_domains(message: str) -> Dict[str, int]:
    """Count distinct secondary-domain triggers present in ``message``."""
    lowered = (message or "").lower()
    return {
        domain: sum(1 for term in terms if term in lowered)
        for domain, terms in DOMAIN_TRIGGERS.items()
    }


def select_agents(
    message: str,
    primary_intent: str,
    max_agents: Optional[int] = None,
    min_hits: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Select the agents that should answer ``message``.

    The primary intent from the existing keyword + semantic router is always
    kept at priority 0. Additional domains whose trigger count reaches
    ``min_hits`` are appended at priority 1, ordered by descending score and
    capped by ``max_agents``.
    """
    limit = max_agents if max_agents is not None else _max_parallel_agents()
    threshold = min_hits if min_hits is not None else _min_secondary_hits()

    primary = primary_intent if primary_intent in SUPERVISED_AGENTS else "general"
    selected: List[Dict[str, Any]] = [
        {"agent": primary, "priority": 0, "reason": "primary intent"}
    ]
    if limit <= 1:
        return selected

    scores = score_domains(message)
    candidates = sorted(
        (
            (domain, hits)
            for domain, hits in scores.items()
            if domain != primary and hits >= threshold
        ),
        key=lambda item: (-item[1], SUPERVISED_AGENTS.index(item[0])),
    )

    for domain, hits in candidates[: limit - 1]:
        selected.append(
            {
                "agent": domain,
                "priority": 1,
                "reason": f"{hits} secondary signal(s)",
            }
        )
    return selected


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------


def _is_grounded(response: Dict[str, Any]) -> bool:
    """Whether the response actually executed MCP tools (i.e. read real data)."""
    return bool(response.get("mcp_tools_used"))


def response_score(response: Dict[str, Any], priority: int) -> float:
    """Rank a response by confidence, data grounding and planner priority."""
    try:
        confidence = float(response.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    grounding = 1.0 if _is_grounded(response) else 0.6
    return confidence * grounding * (1.0 / (1 + max(0, priority)))


def _usable(response: Any) -> bool:
    """Whether an agent produced a usable narrative (errors are dropped)."""
    if not isinstance(response, dict):
        return False
    if response.get("response_type") in {"error", "timeout"}:
        return False
    text = response.get("natural_language")
    return isinstance(text, str) and bool(text.strip())


def safety_veto(responses: Dict[str, Any], min_confidence: Optional[float] = None) -> bool:
    """Whether the safety agent returned a blocking, confident constraint."""
    threshold = (
        min_confidence if min_confidence is not None else _safety_veto_min_confidence()
    )
    safety = responses.get("safety")
    if not isinstance(safety, dict):
        return False
    if safety.get("response_type") not in _safety_blocking_types():
        return False
    try:
        return float(safety.get("confidence") or 0.0) >= threshold
    except (TypeError, ValueError):
        return False


def detect_conflicts(
    responses: Dict[str, Any], veto_active: bool
) -> List[Dict[str, Any]]:
    """Identify agents proposing action while safety imposes a hard block.

    This intentionally covers the one conflict class that can be established
    without semantic comparison: a blocking safety constraint coexisting with
    another agent's actionable output. Broader contradiction detection needs
    embedding or LLM comparison and is left to the arbiter.
    """
    if not veto_active:
        return []
    conflicts: List[Dict[str, Any]] = []
    for name, response in responses.items():
        if name == "safety" or not isinstance(response, dict):
            continue
        if response.get("actions_taken") or response.get("recommendations"):
            conflicts.append(
                {
                    "agent": name,
                    "reason": "proposes actions while a blocking safety constraint is active",
                    "confidence": response.get("confidence", 0.0),
                }
            )
    return conflicts


def _dedupe(items: List[str]) -> List[str]:
    """Preserve order while removing duplicate recommendation strings."""
    seen: set[str] = set()
    out: List[str] = []
    for item in items:
        key = item.strip().lower()
        if item.strip() and key not in seen:
            seen.add(key)
            out.append(item)
    return out


def compose_narrative(ordered: List[Tuple[str, Dict[str, Any]]]) -> str:
    """Compose the user-facing answer from ranked agent contributions.

    A single contribution is returned verbatim so single-agent behavior is
    byte-identical to the existing planner graph.
    """
    if not ordered:
        return ""
    if len(ordered) == 1:
        return ordered[0][1]["natural_language"].strip()

    lead_name, lead = ordered[0]
    parts = [lead["natural_language"].strip()]
    for name, response in ordered[1:]:
        label = DOMAIN_LABELS.get(name, name.title())
        parts.append(f"**{label}** — {response['natural_language'].strip()}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Supervisor graph
# ---------------------------------------------------------------------------


class SupervisorPlannerGraph(MCPPlannerGraph):
    """Planner graph that runs several agents concurrently and arbitrates.

    Inherits every agent node from :class:`MCPPlannerGraph`; only the graph
    topology and the response-merging stage are redefined.
    """

    def _create_graph(self) -> StateGraph:
        """Build the fan-out / fan-in graph."""
        workflow = StateGraph(SupervisorWarehouseState)

        workflow.add_node("plan", self._plan)
        for agent in SUPERVISED_AGENTS:
            workflow.add_node(agent, self._make_agent_node(agent))
        workflow.add_node("general", self._make_agent_node("general"))
        workflow.add_node("aggregate", self._aggregate)
        workflow.add_node("arbiter", self._arbiter)

        workflow.set_entry_point("plan")

        workflow.add_conditional_edges(
            "plan",
            self._fan_out,
            list(SUPERVISED_AGENTS) + ["general", "aggregate"],
        )
        for agent in SUPERVISED_AGENTS:
            workflow.add_edge(agent, "aggregate")
        workflow.add_edge("general", "aggregate")

        workflow.add_conditional_edges(
            "aggregate",
            self._route_after_aggregate,
            {"arbiter": "arbiter", "end": END},
        )
        workflow.add_edge("arbiter", END)

        # SECURITY: in-memory state only, matching the planner graph rationale
        # (CVE-2025-8709 in langgraph-checkpoint-sqlite).
        return workflow.compile()

    # -- agent execution ----------------------------------------------------

    def _agent_handler(self, agent_key: str) -> Callable[[Any], Any]:
        """Resolve the inherited MCP node function for ``agent_key``."""
        return getattr(self, f"_mcp_{agent_key}_agent")

    def _make_agent_node(self, agent_key: str) -> Callable[[Dict[str, Any]], Any]:
        """Wrap an inherited agent node so it only emits its own response.

        The inherited nodes mutate and return the whole state. Under fan-out that
        would make every branch write every channel, which LangGraph rejects. The
        wrapper isolates each branch and returns just the ``agent_responses``
        delta, which the reducer merges.
        """

        async def _node(state: Dict[str, Any]) -> Dict[str, Any]:
            handler = self._agent_handler(agent_key)
            working: Dict[str, Any] = dict(state)
            working["agent_responses"] = {}
            working["context"] = dict(state.get("context") or {})
            working["messages"] = list(state.get("messages") or [])

            try:
                result = await handler(working)
            except Exception as exc:  # defensive: one agent must not fail the turn
                logger.error("Supervised agent %s raised: %s", agent_key, exc, exc_info=True)
                return {
                    "agent_responses": {
                        agent_key: {
                            "natural_language": "",
                            "data": {"error": str(exc)[:200]},
                            "recommendations": [],
                            "confidence": 0.0,
                            "response_type": "error",
                            "mcp_tools_used": [],
                        }
                    }
                }

            emitted = result.get("agent_responses", {}) if isinstance(result, dict) else {}
            return {"agent_responses": dict(emitted)}

        _node.__name__ = f"supervised_{agent_key}"
        return _node

    # -- planning -----------------------------------------------------------

    async def _plan(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Classify the query, then select the set of agents to run."""
        routed = await self._mcp_route_intent(state)

        message_text = _extract_message_text(routed) or ""
        primary = routed.get("routing_decision") or "general"

        if primary == "ambiguous":
            routed["selected_agents"] = []
            routed["decision_path"] = "clarify"
            return routed

        selected = select_agents(message_text, primary)
        routed["selected_agents"] = selected
        routed["decision_path"] = (
            "single_agent" if len(selected) == 1 else "fan_out"
        )

        logger.info(
            "🧭 Supervisor selected %s agent(s): %s | query: %s",
            len(selected),
            ", ".join(f"{s['agent']}(p{s['priority']})" for s in selected),
            sanitize_log_data(message_text, max_length=100),
        )
        return routed

    def _fan_out(self, state: Dict[str, Any]) -> Any:
        """Dispatch the query to every selected agent concurrently."""
        selected = state.get("selected_agents") or []
        if not selected:
            return "aggregate"
        return [Send(item["agent"], state) for item in selected]

    # -- aggregation --------------------------------------------------------

    def _aggregate(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Merge agent responses into one answer using the arbitration policy."""
        raw = state.get("agent_responses") or {}
        responses = {name: r for name, r in raw.items() if _usable(r)}
        priorities = {
            item["agent"]: item.get("priority", 0)
            for item in (state.get("selected_agents") or [])
        }

        if not responses:
            # Clarifying question already set by the router, or every agent failed.
            if not state.get("final_response"):
                state["final_response"] = (
                    "I'm sorry, I couldn't process your request. "
                    "Please try rephrasing your question."
                )
                state["decision_path"] = "no_usable_response"
            state.setdefault("decision_path", "clarify")
            state["conflicts"] = []
            return state

        veto = safety_veto(responses)
        conflicts = detect_conflicts(responses, veto)

        ranked = sorted(
            responses.items(),
            key=lambda item: response_score(item[1], priorities.get(item[0], 1)),
            reverse=True,
        )
        if veto:
            # The blocking constraint leads the answer regardless of its score.
            ranked.sort(key=lambda item: item[0] != "safety")
            decision_path = "safety_veto"
        elif len(ranked) == 1:
            decision_path = "single_agent"
        else:
            decision_path = "confidence_merge"

        state["final_response"] = compose_narrative(ranked)
        state["conflicts"] = conflicts
        state["decision_path"] = decision_path
        state["context"] = dict(state.get("context") or {})
        state["context"]["structured_response"] = self._build_structured_response(
            ranked, veto, conflicts, decision_path, priorities
        )
        state["context"]["decision_path"] = decision_path
        state["context"]["contributing_agents"] = [name for name, _ in ranked]
        state["context"]["mcp_tools_used"] = sorted(
            {
                tool
                for _, response in ranked
                for tool in (response.get("mcp_tools_used") or [])
            }
        )

        logger.info(
            "🧩 Supervisor aggregated %s response(s) via %s (conflicts: %s)",
            len(ranked),
            decision_path,
            len(conflicts),
        )
        return state

    def _build_structured_response(
        self,
        ranked: List[Tuple[str, Dict[str, Any]]],
        veto: bool,
        conflicts: List[Dict[str, Any]],
        decision_path: str,
        priorities: Dict[str, int],
    ) -> Dict[str, Any]:
        """Assemble the structured payload consumed by the API layer."""
        lead_name, lead = ranked[0]

        if veto:
            recommendations = list(lead.get("recommendations") or [])
        else:
            recommendations = _dedupe(
                [
                    rec
                    for _, response in ranked
                    for rec in (response.get("recommendations") or [])
                    if isinstance(rec, str)
                ]
            )

        weights = [
            (response_score(response, priorities.get(name, 1)), response)
            for name, response in ranked
        ]
        total_weight = sum(weight for weight, _ in weights)
        if veto:
            confidence = float(lead.get("confidence") or 0.0)
        elif total_weight > 0:
            confidence = sum(
                weight * float(response.get("confidence") or 0.0)
                for weight, response in weights
            ) / total_weight
        else:
            confidence = 0.0

        return {
            "response_type": (
                lead.get("response_type") if len(ranked) == 1 else "multi_agent_summary"
            ),
            "natural_language": compose_narrative(ranked),
            "data": {name: response.get("data", {}) for name, response in ranked},
            "recommendations": recommendations,
            "confidence": round(confidence, 4),
            "actions_taken": [
                action
                for _, response in ranked
                for action in (response.get("actions_taken") or [])
            ],
            "mcp_tools_used": sorted(
                {
                    tool
                    for _, response in ranked
                    for tool in (response.get("mcp_tools_used") or [])
                }
            ),
            "contributing_agents": [name for name, _ in ranked],
            "lead_agent": lead_name,
            "decision_path": decision_path,
            "conflicts": conflicts,
        }

    def _route_after_aggregate(self, state: Dict[str, Any]) -> str:
        """Escalate to the arbiter only when enabled and a conflict remains."""
        if state.get("conflicts") and _arbiter_enabled():
            return "arbiter"
        return "end"

    # -- arbitration --------------------------------------------------------

    async def _arbiter(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Reconcile conflicting recommendations with the configured LLM.

        The arbiter ranks and reconciles the material the agents already
        produced; it must not introduce new facts. On any failure the
        deterministic aggregation stands.
        """
        conflicts = state.get("conflicts") or []
        responses = state.get("agent_responses") or {}
        query = _extract_message_text(state) or ""

        try:
            from src.api.services.llm.nim_client import get_nim_client

            candidates = "\n\n".join(
                f"[{name}] confidence={response.get('confidence', 0.0)} "
                f"type={response.get('response_type')}\n"
                f"{response.get('natural_language', '')}"
                for name, response in responses.items()
                if _usable(response)
            )
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You arbitrate between warehouse agents that produced "
                        "conflicting guidance. Apply this strict precedence: "
                        "Safety > Compliance > Operations > Cost. Reconcile the "
                        "guidance you are given and state which agent justifies "
                        "each decision. Do not introduce facts that are not "
                        "present in the candidate responses."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f'Operator question: "{query}"\n\n'
                        f"Candidate agent responses:\n{candidates}\n\n"
                        f"Detected conflicts: {conflicts}\n\n"
                        "Produce the single reconciled answer for the operator."
                    ),
                },
            ]

            client = await get_nim_client()
            result = await asyncio.wait_for(
                client.generate_response(messages=messages, temperature=0.1),
                timeout=_getenv_float("SUPERVISOR_ARBITER_TIMEOUT", 30.0),
            )

            if result and isinstance(result.content, str) and result.content.strip():
                state["final_response"] = result.content.strip()
                state["decision_path"] = "arbiter"
                state["arbitration"] = {
                    "resolved_by": "llm",
                    "conflicts": conflicts,
                    "model": getattr(result, "model", None),
                }
                context = dict(state.get("context") or {})
                context["decision_path"] = "arbiter"
                structured = dict(context.get("structured_response") or {})
                structured["natural_language"] = state["final_response"]
                structured["decision_path"] = "arbiter"
                context["structured_response"] = structured
                state["context"] = context
                logger.info("⚖️ Arbiter resolved %s conflict(s)", len(conflicts))
            else:
                logger.warning("Arbiter returned empty content, keeping aggregation")

        except Exception as exc:
            logger.error("Arbiter failed, keeping deterministic aggregation: %s", exc)
            state["arbitration"] = {"resolved_by": "fallback", "error": str(exc)[:200]}

        return state

    # -- public API ---------------------------------------------------------

    async def process_warehouse_query(
        self, message: str, session_id: str = "default", context: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Run a query through the supervisor graph.

        Returns the same contract as :meth:`MCPPlannerGraph.process_warehouse_query`
        plus supervisor-specific telemetry, so API and UI layers are unchanged.
        """
        base = await super().process_warehouse_query(message, session_id, context)
        return base


# ---------------------------------------------------------------------------
# Module-level access
# ---------------------------------------------------------------------------

_supervisor_graph: Optional[SupervisorPlannerGraph] = None
_supervisor_lock = asyncio.Lock()


async def get_supervisor_graph() -> SupervisorPlannerGraph:
    """Get (and lazily initialize) the global supervisor graph."""
    global _supervisor_graph
    if _supervisor_graph is None:
        async with _supervisor_lock:
            if _supervisor_graph is None:
                graph = SupervisorPlannerGraph()
                await graph.initialize()
                _supervisor_graph = graph
    return _supervisor_graph


async def process_supervisor_warehouse_query(
    message: str, session_id: str = "default", context: Optional[Dict] = None
) -> Dict[str, Any]:
    """Process a warehouse query through the supervisor graph."""
    supervisor = await get_supervisor_graph()
    return await supervisor.process_warehouse_query(message, session_id, context)
