# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
CopilotService — Phase 15D: ASK + ANALYZE + ACT.

Trust boundary enforced by explicit import restrictions:
    - MUST NOT import ActionExecutor
    - MUST NOT call ApprovalStore.approve
    - MUST NOT call DecisionEngine.evaluate
    - MUST NOT create ActionProposal

ACT is handled via GovernedActionOrchestrator (injected at bootstrap time).
CopilotService delegates governance to the orchestrator; it never holds
references to ActionExecutor, ApprovalStore, or DecisionEngine.

These are validated by architecture invariant tests in test_phase15d_act.py.

Degradation policy
------------------
If WarehouseState cannot be assembled (provider unavailable, state provider
None, or exception), ASK/ANALYZE returns a structured degraded response rather
than falling back to any simulated/invented operational data.

If individual domains are unavailable, each missing domain is noted in
degradation_reason; available domains still inform the answer.

The agent's _simulate_workforce_data() fallback is suppressed by the
CopilotService: if we cannot inject real state, we degrade explicitly.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

try:
    from maiw_state.warehouse import WarehouseStateSnapshot
    from maiw_state import StateRequirements as _StateRequirements
except ImportError:
    WarehouseStateSnapshot = None  # type: ignore[assignment,misc]
    _StateRequirements = None  # type: ignore[assignment]

from . import context as context_resolver
from . import intent as intent_classifier
from .models import (
    CopilotActResult,
    CopilotAnalyzeResult,
    CopilotAskResult,
    CopilotIntent,
    CopilotTurn,
    EvidenceFact,
    GovernedActionRequest,
    MutationState,
    RecommendedActionResult,
)
from .store import InMemoryCopilotStore

logger = logging.getLogger(__name__)


class CopilotService:
    """
    Orchestrates Copilot ASK and ANALYZE turns.

    Phase 15C scope: ASK + ANALYZE. ACT will be added in 15D.

    This class MUST NOT:
    - import or call ActionExecutor
    - import or call ApprovalStore.approve
    - import or call DecisionEngine.evaluate
    - construct or return ActionProposal

    Dependencies are injected at construction time (same pattern as bootstrap.py).
    """

    def __init__(
        self,
        *,
        operations_agent: Any,
        state_provider: Any,
        event_bus: Any | None = None,
        graph: Any | None = None,
        store: InMemoryCopilotStore | None = None,
    ) -> None:
        self._agent = operations_agent
        self._state_provider = state_provider
        self._event_bus = event_bus
        self._graph = graph
        self._store = store or InMemoryCopilotStore()
        self._orchestrator: Any = None  # injected via set_orchestrator() at bootstrap

    @property
    def store(self) -> InMemoryCopilotStore:
        return self._store

    def set_orchestrator(self, orchestrator: Any) -> None:
        """
        Inject the GovernedActionOrchestrator.

        Called by bootstrap after both the service and orchestrator are
        constructed. Using a setter keeps the constructor signature stable
        and makes the governance boundary explicit.

        CopilotService MUST NOT import GovernedActionOrchestrator directly.
        """
        self._orchestrator = orchestrator

    async def ask(
        self,
        *,
        message: str,
        conversation_id: str | None,
        warehouse_id: str,
        scenario_name: str = "",
    ) -> tuple[CopilotAskResult, CopilotTurn]:
        """
        Process an ASK turn end-to-end.

        Returns (CopilotAskResult, CopilotTurn). The caller persists the turn
        via store.add_turn() after this method returns.

        Zero ActionProposals, zero DecisionEngine evaluations, zero writes.
        """
        _t0 = time.monotonic()
        trace_id = str(uuid.uuid4())
        turn_id = str(uuid.uuid4())

        conv = self._store.get_or_create(
            conversation_id, warehouse_id, scenario_name
        )
        parent_turn_id = conv.last_turn.turn_id if conv.last_turn else None

        await self._publish("COPILOT_TURN_STARTED", f"Copilot ASK — turn {turn_id[:8]}", trace_id=trace_id)
        await self._publish("COPILOT_INTENT_RESOLVED", "intent=ASK", trace_id=trace_id)

        # ── Assemble WarehouseState ───────────────────────────────────────────
        _t_state = time.monotonic()
        state, state_degraded, state_degradation_reason = await self._get_state(
            warehouse_id=warehouse_id,
            scenario_name=scenario_name,
            trace_id=trace_id,
        )
        _state_ms = (time.monotonic() - _t_state) * 1000

        # ── Early answerability check ─────────────────────────────────────────
        missing = _missing_context(state, scenario_name)

        if state is None or missing:
            from maiw_api.copilot.models import ContextNeighborhood as _CN
            neighborhood = _CN(
                focus_entity_id=None,
                focus_entity_label=None,
                entity_ids=[],
                relationship_summary={},
                max_depth=2,
                graph_available=False,
                entity_resolution=None,
            )
            degradation = _build_degradation(state_degradation_reason, missing, neighborhood)
            if state is None:
                answer = (
                    f"I cannot determine the answer because warehouse state is unavailable"
                    f" for scenario '{scenario_name or warehouse_id}'. "
                    + (state_degradation_reason or "")
                ).strip()
                routing_reason = "State unavailable — skipped"
            else:
                domain_str = ", ".join(missing)
                answer = (
                    f"I cannot determine the answer because the following context is unavailable: "
                    f"{domain_str}. This usually means the scenario has not been started or "
                    f"the requested data has not been loaded into the runtime."
                )
                routing_reason = "Answerability gate — empty state refused"
            result = CopilotAskResult(
                answer=answer,
                evidence=[],
                neighborhood=neighborhood,
                agent="OperationsCoordinationAgent",
                skills_used=[],
                skills_available=[],
                model_id="none",
                reasoning_level="MEDIUM",
                routing_rule="none",
                routing_reason=routing_reason,
                trace_id=trace_id,
                snapshot_id="none",
                warehouse_id=warehouse_id,
                latency_ms=(time.monotonic() - _t0) * 1000,
                degraded=True,
                degradation_reason=degradation,
                answerability="insufficient_evidence",
                missing_context=missing,
                timing={
                    "state_assembly_ms": round(_state_ms, 1),
                    "graph_lookup_ms": 0.0,
                    "model_inference_ms": 0.0,
                    "total_ms": round((time.monotonic() - _t0) * 1000, 1),
                },
            )
            turn = self._make_turn(
                turn_id=turn_id, conv_id=conv.conversation_id, message=message,
                intent=CopilotIntent.ASK, trace_id=trace_id, summary=result.answer,
                parent_turn_id=parent_turn_id,
            )
            self._store.add_turn(turn)
            await self._publish("COPILOT_TURN_COMPLETE", "degraded=true insufficient_evidence", trace_id=trace_id)
            return result, turn

        # ── Resolve Operational Graph neighborhood ────────────────────────────
        _t_graph = time.monotonic()
        neighborhood = context_resolver.resolve(
            question=message,
            warehouse_id=warehouse_id,
            graph=self._graph,
            focus_entity_id=conv.last_focus_entity_id,
            focus_entity_label=conv.last_focus_entity_label,
        )
        _graph_ms = (time.monotonic() - _t_graph) * 1000

        await self._publish(
            "COPILOT_CONTEXT_RESOLVED",
            f"focus={neighborhood.focus_entity_label or 'none'} "
            f"entities={len(neighborhood.entity_ids)} "
            f"graph_available={neighborhood.graph_available}",
            trace_id=trace_id,
        )

        # ── Seal snapshot and call agent ──────────────────────────────────────
        try:
            from maiw_models import ReasoningLevel, RiskLevel

            snapshot = WarehouseStateSnapshot.seal(state)

            assessment = await self._agent.analyze_disruption(
                snapshot=snapshot,
                scenario_context=message,
                trace_id=trace_id,
                reasoning_level=ReasoningLevel.MEDIUM,
                risk_level=RiskLevel.LOW,
            )

        except Exception as exc:
            logger.error("CopilotService.ask: agent call failed — %s", exc)
            err_answer = "I encountered an error while analyzing the warehouse state."
            result = CopilotAskResult(
                answer=err_answer,
                evidence=[],
                neighborhood=neighborhood,
                agent="OperationsCoordinationAgent",
                skills_used=[],
                skills_available=[],
                model_id="none",
                reasoning_level="MEDIUM",
                routing_rule="none",
                routing_reason=f"Agent error: {exc}",
                trace_id=trace_id,
                snapshot_id="none",
                warehouse_id=warehouse_id,
                latency_ms=(time.monotonic() - _t0) * 1000,
                degraded=True,
                degradation_reason=str(exc),
                answerability="insufficient_evidence",
                missing_context=[],
            )
            turn = self._make_turn(
                turn_id=turn_id, conv_id=conv.conversation_id, message=message,
                intent=CopilotIntent.ASK, trace_id=trace_id, summary=err_answer,
                parent_turn_id=parent_turn_id,
            )
            self._store.add_turn(turn)
            await self._publish("COPILOT_TURN_COMPLETE", "degraded=true error", trace_id=trace_id)
            return result, turn

        # ── Build result ──────────────────────────────────────────────────────
        _total_ms = (time.monotonic() - _t0) * 1000
        evidence = _facts_to_evidence(assessment.facts_observed, assessment.severity)

        full_degradation = _build_degradation(state_degradation_reason, [], neighborhood)
        partial_missing = [m for m in _missing_context(state, scenario_name)]
        answerability = "partial" if state_degradation_reason else "answerable"

        result = CopilotAskResult(
            answer=assessment.summary,
            evidence=evidence,
            neighborhood=neighborhood,
            agent="OperationsCoordinationAgent",
            skills_used=[],
            skills_available=assessment.skills_consulted,
            model_id=assessment.model_id,
            reasoning_level="MEDIUM",
            routing_rule=assessment.routing_rule,
            routing_reason=assessment.routing_reason,
            requested_role=assessment.requested_role,
            selected_role=assessment.selected_role,
            fallback_from=assessment.fallback_from,
            fallback_reason=assessment.fallback_reason,
            trace_id=trace_id,
            snapshot_id=assessment.snapshot_id,
            warehouse_id=assessment.warehouse_id,
            latency_ms=_total_ms,
            degraded=bool(full_degradation),
            degradation_reason=full_degradation or None,
            answerability=answerability,
            missing_context=partial_missing,
            timing={
                "state_assembly_ms": round(_state_ms, 1),
                "graph_lookup_ms": round(_graph_ms, 1),
                "model_inference_ms": round(assessment.latency_ms, 1),
                "total_ms": round(_total_ms, 1),
            },
        )

        # ── Update focus continuity on conversation ───────────────────────────
        if neighborhood.focus_entity_id:
            conv.last_focus_entity_id = neighborhood.focus_entity_id
            conv.last_focus_entity_label = neighborhood.focus_entity_label
            er = neighborhood.entity_resolution
            conv.last_focus_entity_type = er.entity_type if er else None

        turn = self._make_turn(
            turn_id=turn_id, conv_id=conv.conversation_id, message=message,
            intent=CopilotIntent.ASK, trace_id=trace_id, summary=result.answer,
            parent_turn_id=parent_turn_id,
            focus_entity_id=neighborhood.focus_entity_id,
            focus_entity_type=conv.last_focus_entity_type,
            focus_entity_label=neighborhood.focus_entity_label,
        )
        self._store.add_turn(turn)
        await self._publish("COPILOT_TURN_COMPLETE", f"model={result.model_id}", trace_id=trace_id)
        return result, turn

    async def analyze(
        self,
        *,
        message: str,
        conversation_id: str | None,
        warehouse_id: str,
        scenario_name: str = "",
    ) -> tuple[CopilotAnalyzeResult, CopilotTurn]:
        """
        Process an ANALYZE turn: fresh state read → graph context → recommendations.

        Zero ActionProposals, zero DecisionEngine evaluations, zero writes.
        'No warehouse changes have been made.' is always true after this call.
        """
        _t0 = time.monotonic()
        trace_id = str(uuid.uuid4())
        turn_id = str(uuid.uuid4())

        conv = self._store.get_or_create(
            conversation_id, warehouse_id, scenario_name
        )
        parent_turn_id = conv.last_turn.turn_id if conv.last_turn else None

        await self._publish("COPILOT_TURN_STARTED", f"Copilot ANALYZE — turn {turn_id[:8]}", trace_id=trace_id)
        await self._publish("COPILOT_INTENT_RESOLVED", "intent=ANALYZE", trace_id=trace_id)

        # ── Fresh WarehouseState read (do not reuse prior ASK snapshot) ───────
        await self._publish("COPILOT_READING_STATE", "Reading warehouse state", trace_id=trace_id)
        _t_state = time.monotonic()
        state, state_degraded, state_degradation_reason = await self._get_state(
            warehouse_id=warehouse_id,
            scenario_name=scenario_name,
            trace_id=trace_id,
        )
        _state_ms = (time.monotonic() - _t_state) * 1000

        missing = _missing_context(state, scenario_name)

        if state is None or missing:
            from maiw_api.copilot.models import ContextNeighborhood as _CN
            neighborhood = _CN(
                focus_entity_id=None, focus_entity_label=None, entity_ids=[],
                relationship_summary={}, max_depth=2, graph_available=False,
                entity_resolution=None,
            )
            degradation = _build_degradation(state_degradation_reason, missing, neighborhood)
            summary = (
                "I cannot produce recommendations because warehouse state is unavailable. "
                + (state_degradation_reason or "")
            ).strip()
            result = CopilotAnalyzeResult(
                summary=summary, severity="UNKNOWN", evidence=[], recommendations=[],
                neighborhood=neighborhood, agent="OperationsCoordinationAgent",
                skills_used=[], skills_available=[], model_id="none",
                reasoning_level="HIGH", routing_rule="none",
                routing_reason="State unavailable — skipped",
                trace_id=trace_id, snapshot_id="none", warehouse_id=warehouse_id,
                latency_ms=(time.monotonic() - _t0) * 1000,
                degraded=True, degradation_reason=degradation,
                answerability="insufficient_evidence", missing_context=missing,
                timing={
                    "state_assembly_ms": round(_state_ms, 1),
                    "graph_lookup_ms": 0.0, "model_inference_ms": 0.0,
                    "total_ms": round((time.monotonic() - _t0) * 1000, 1),
                },
            )
            turn = self._make_turn(
                turn_id=turn_id, conv_id=conv.conversation_id, message=message,
                intent=CopilotIntent.ANALYZE, trace_id=trace_id, summary=result.summary,
                parent_turn_id=parent_turn_id,
            )
            self._store.add_turn(turn)
            await self._publish("COPILOT_TURN_COMPLETE", "degraded=true insufficient_evidence", trace_id=trace_id)
            return result, turn

        # ── Resolve Operational Graph neighborhood with focus continuity ──────
        await self._publish("COPILOT_RESOLVING_CONTEXT", "Resolving graph context", trace_id=trace_id)
        _t_graph = time.monotonic()
        neighborhood = context_resolver.resolve(
            question=message,
            warehouse_id=warehouse_id,
            graph=self._graph,
            focus_entity_id=conv.last_focus_entity_id,
            focus_entity_label=conv.last_focus_entity_label,
        )
        _graph_ms = (time.monotonic() - _t_graph) * 1000

        await self._publish(
            "COPILOT_CONTEXT_RESOLVED",
            f"focus={neighborhood.focus_entity_label or conv.last_focus_entity_label or 'none'} "
            f"entities={len(neighborhood.entity_ids)} "
            f"graph_available={neighborhood.graph_available}",
            trace_id=trace_id,
        )

        # ── Seal snapshot and call agent with HIGH reasoning ──────────────────
        await self._publish("COPILOT_ANALYZING", "Generating recommendations", trace_id=trace_id)
        try:
            from maiw_models import ReasoningLevel, RiskLevel

            snapshot = WarehouseStateSnapshot.seal(state)

            # ANALYZE uses HIGH reasoning and MEDIUM risk — the operator is asking
            # for a recommendation that may influence a consequential decision.
            assessment = await self._agent.analyze_disruption(
                snapshot=snapshot,
                scenario_context=message,
                trace_id=trace_id,
                reasoning_level=ReasoningLevel.HIGH,
                risk_level=RiskLevel.MEDIUM,
            )

        except Exception as exc:
            logger.error("CopilotService.analyze: agent call failed — %s", exc)
            err_summary = "I encountered an error while generating recommendations."
            result = CopilotAnalyzeResult(
                summary=err_summary, severity="UNKNOWN", evidence=[], recommendations=[],
                neighborhood=neighborhood, agent="OperationsCoordinationAgent",
                skills_used=[], skills_available=[], model_id="none",
                reasoning_level="HIGH", routing_rule="none",
                routing_reason=f"Agent error: {exc}",
                trace_id=trace_id, snapshot_id="none", warehouse_id=warehouse_id,
                latency_ms=(time.monotonic() - _t0) * 1000,
                degraded=True, degradation_reason=str(exc),
                answerability="insufficient_evidence",
                timing={
                    "state_assembly_ms": round(_state_ms, 1),
                    "graph_lookup_ms": round(_graph_ms, 1),
                    "model_inference_ms": 0.0,
                    "total_ms": round((time.monotonic() - _t0) * 1000, 1),
                },
            )
            turn = self._make_turn(
                turn_id=turn_id, conv_id=conv.conversation_id, message=message,
                intent=CopilotIntent.ANALYZE, trace_id=trace_id, summary=err_summary,
                parent_turn_id=parent_turn_id,
            )
            self._store.add_turn(turn)
            await self._publish("COPILOT_TURN_COMPLETE", "degraded=true error", trace_id=trace_id)
            return result, turn

        # ── Build RecommendedActionResult list with provenance ────────────────
        _total_ms = (time.monotonic() - _t0) * 1000
        evidence = _facts_to_evidence(assessment.facts_observed, assessment.severity)
        full_degradation = _build_degradation(state_degradation_reason, [], neighborhood)
        answerability = "partial" if state_degradation_reason else "answerable"

        effective_focus_id = (
            neighborhood.focus_entity_id or conv.last_focus_entity_id
        )
        effective_focus_label = (
            neighborhood.focus_entity_label or conv.last_focus_entity_label
        )

        recs: list[RecommendedActionResult] = []
        for i, ra in enumerate(assessment.recommendations):
            recs.append(RecommendedActionResult(
                recommendation_id=f"{turn_id[:8]}-rec-{i:02d}",
                domain=ra.domain.value if hasattr(ra.domain, "value") else str(ra.domain),
                capability=ra.capability.value if hasattr(ra.capability, "value") else str(ra.capability),
                target=ra.target,
                objective=ra.objective,
                rationale=ra.rationale,
                priority=ra.priority.value if hasattr(ra.priority, "value") else str(ra.priority),
                subtype=ra.subtype,
                conversation_id=conv.conversation_id,
                turn_id=turn_id,
                trace_id=trace_id,
                snapshot_id=assessment.snapshot_id,
                focus_entity_id=effective_focus_id,
            ))

        result = CopilotAnalyzeResult(
            summary=assessment.summary,
            severity=assessment.severity.value if hasattr(assessment.severity, "value") else str(assessment.severity),
            evidence=evidence,
            recommendations=recs,
            neighborhood=neighborhood,
            agent="OperationsCoordinationAgent",
            skills_used=[],
            skills_available=assessment.skills_consulted,
            model_id=assessment.model_id,
            reasoning_level="HIGH",
            routing_rule=assessment.routing_rule,
            routing_reason=assessment.routing_reason,
            requested_role=assessment.requested_role,
            selected_role=assessment.selected_role,
            fallback_from=assessment.fallback_from,
            fallback_reason=assessment.fallback_reason,
            trace_id=trace_id,
            snapshot_id=assessment.snapshot_id,
            warehouse_id=assessment.warehouse_id,
            latency_ms=_total_ms,
            degraded=bool(full_degradation),
            degradation_reason=full_degradation or None,
            answerability=answerability,
            timing={
                "state_assembly_ms": round(_state_ms, 1),
                "graph_lookup_ms": round(_graph_ms, 1),
                "model_inference_ms": round(assessment.latency_ms, 1),
                "total_ms": round(_total_ms, 1),
            },
            focus_entity_id=effective_focus_id,
            focus_entity_label=effective_focus_label,
        )

        # ── Update conversation: focus continuity + store recommendations ─────
        if neighborhood.focus_entity_id:
            conv.last_focus_entity_id = neighborhood.focus_entity_id
            conv.last_focus_entity_label = neighborhood.focus_entity_label
            er = neighborhood.entity_resolution
            conv.last_focus_entity_type = er.entity_type if er else None
        conv.last_recommendations = list(recs)

        turn = self._make_turn(
            turn_id=turn_id, conv_id=conv.conversation_id, message=message,
            intent=CopilotIntent.ANALYZE, trace_id=trace_id, summary=result.summary,
            parent_turn_id=parent_turn_id,
            focus_entity_id=effective_focus_id,
            focus_entity_type=conv.last_focus_entity_type,
            focus_entity_label=effective_focus_label,
        )
        self._store.add_turn(turn)
        await self._publish("COPILOT_TURN_COMPLETE", f"recommendations={len(recs)} model={result.model_id}", trace_id=trace_id)
        return result, turn

    async def act(
        self,
        *,
        message: str,
        conversation_id: str | None,
        warehouse_id: str,
        scenario_name: str = "",
    ) -> tuple[CopilotActResult, CopilotTurn]:
        """
        Process an ACT turn: resolve recommendation → validate state → governed request.

        CopilotService MUST NOT call DecisionEngine, ApprovalStore, or ActionExecutor.
        All governance is delegated to GovernedActionOrchestrator.

        Returns (CopilotActResult, CopilotTurn). The turn is persisted internally.
        """
        _t0 = time.monotonic()
        trace_id = str(uuid.uuid4())
        turn_id = str(uuid.uuid4())
        _safety_no_mutation = "No warehouse changes have been made."

        conv = self._store.get_or_create(conversation_id, warehouse_id, scenario_name)
        parent_turn_id = conv.last_turn.turn_id if conv.last_turn else None

        await self._publish("COPILOT_TURN_STARTED", f"Copilot ACT — turn {turn_id[:8]}", trace_id=trace_id)
        await self._publish("COPILOT_INTENT_RESOLVED", "intent=ACT", trace_id=trace_id)

        def _make_act_error(
            decision_outcome: str,
            message_text: str,
            *,
            recommendation_id: str = "",
            capability: str = "",
            target: str = "",
            source_snapshot_id: str = "none",
            current_snapshot_id: str = "none",
            degraded: bool = True,
            degradation_reason: str | None = None,
        ) -> CopilotActResult:
            return CopilotActResult(
                message=message_text,
                recommendation_id=recommendation_id,
                capability=capability,
                target=target,
                decision_outcome=decision_outcome,
                proposal_id=None,
                decision_id=None,
                approval_required=False,
                pending_approval_id=None,
                execution_status=None,
                execution_id=None,
                mutation_state=MutationState.NOT_ATTEMPTED,
                safety_note=_safety_no_mutation,
                violations=[],
                source_recommendation_id=recommendation_id,
                source_snapshot_id=source_snapshot_id,
                snapshot_id=current_snapshot_id,
                conversation_id=conv.conversation_id,
                turn_id=turn_id,
                trace_id=trace_id,
                warehouse_id=warehouse_id,
                latency_ms=(time.monotonic() - _t0) * 1000,
                degraded=degraded,
                degradation_reason=degradation_reason,
            )

        # ── Orchestrator check ────────────────────────────────────────────────
        if self._orchestrator is None:
            result = _make_act_error(
                "NOT_IMPLEMENTED",
                (
                    "Governed action handling is not available in this build. "
                    "Ensure the MAIW runtime is fully initialized with a "
                    "GovernedActionOrchestrator."
                ),
                degraded=True,
            )
            turn = self._make_turn(
                turn_id=turn_id, conv_id=conv.conversation_id, message=message,
                intent=CopilotIntent.ACT, trace_id=trace_id, summary=result.message,
                parent_turn_id=parent_turn_id,
            )
            self._store.add_turn(turn)
            await self._publish("COPILOT_TURN_COMPLETE", "not_implemented", trace_id=trace_id)
            return result, turn

        # ── Recommendation resolution ─────────────────────────────────────────
        await self._publish("COPILOT_RESOLVING_RECOMMENDATION", "Resolving recommendation", trace_id=trace_id)
        recs: list[RecommendedActionResult] = list(conv.last_recommendations)

        if not recs:
            result = _make_act_error(
                "CLARIFICATION_REQUIRED",
                (
                    "I have no recommendations to act on. "
                    "Please ask 'What should we do?' first to generate recommendations."
                ),
                degraded=False,
            )
            turn = self._make_turn(
                turn_id=turn_id, conv_id=conv.conversation_id, message=message,
                intent=CopilotIntent.ACT, trace_id=trace_id, summary=result.message,
                parent_turn_id=parent_turn_id,
            )
            self._store.add_turn(turn)
            await self._publish("COPILOT_TURN_COMPLETE", "no_recommendations", trace_id=trace_id)
            return result, turn

        selected_rec, resolution_reason = _select_recommendation(message, recs)

        if selected_rec is None and resolution_reason == "ambiguous":
            rec_list = "\n".join(
                f"{i + 1}. {r.objective} ({r.capability})"
                for i, r in enumerate(recs)
            )
            result = _make_act_error(
                "CLARIFICATION_REQUIRED",
                (
                    f"I have {len(recs)} recommended actions. "
                    f"Which would you like me to prepare?\n\n{rec_list}\n\n"
                    "You can say 'Do the first one', 'Do the second one', "
                    "or reference the action by name."
                ),
                degraded=False,
            )
            turn = self._make_turn(
                turn_id=turn_id, conv_id=conv.conversation_id, message=message,
                intent=CopilotIntent.ACT, trace_id=trace_id, summary=result.message,
                parent_turn_id=parent_turn_id,
            )
            self._store.add_turn(turn)
            await self._publish("COPILOT_TURN_COMPLETE", "clarification_required", trace_id=trace_id)
            return result, turn

        if selected_rec is None:
            result = _make_act_error(
                "ERROR",
                "I could not identify which recommendation to act on.",
                degraded=True,
            )
            turn = self._make_turn(
                turn_id=turn_id, conv_id=conv.conversation_id, message=message,
                intent=CopilotIntent.ACT, trace_id=trace_id, summary=result.message,
                parent_turn_id=parent_turn_id,
            )
            self._store.add_turn(turn)
            return result, turn

        await self._publish(
            "COPILOT_RESOLVING_RECOMMENDATION",
            f"Resolved: {selected_rec.recommendation_id} via {resolution_reason}",
            trace_id=trace_id,
        )

        # ── Re-read WarehouseState (S2) ───────────────────────────────────────
        await self._publish("COPILOT_READING_STATE", "Reading current warehouse state", trace_id=trace_id)
        state, state_degraded, state_degradation_reason = await self._get_state(
            warehouse_id=warehouse_id,
            scenario_name=scenario_name,
            trace_id=trace_id,
        )

        if state is None:
            result = _make_act_error(
                "ERROR",
                (
                    "I cannot safely prepare this action because current warehouse state "
                    "is unavailable. " + (state_degradation_reason or "")
                ).strip(),
                recommendation_id=selected_rec.recommendation_id,
                capability=selected_rec.capability,
                target=selected_rec.target,
                source_snapshot_id=selected_rec.snapshot_id,
                degraded=True,
                degradation_reason=state_degradation_reason,
            )
            turn = self._make_turn(
                turn_id=turn_id, conv_id=conv.conversation_id, message=message,
                intent=CopilotIntent.ACT, trace_id=trace_id, summary=result.message,
                parent_turn_id=parent_turn_id,
            )
            self._store.add_turn(turn)
            await self._publish("COPILOT_TURN_COMPLETE", "state_unavailable", trace_id=trace_id)
            return result, turn

        # ── Seal S2 snapshot ──────────────────────────────────────────────────
        snapshot = WarehouseStateSnapshot.seal(state)
        current_snapshot_id = getattr(snapshot, "snapshot_id", "unknown")

        # ── Validate state drift (S1 vs S2) ──────────────────────────────────
        await self._publish("COPILOT_VALIDATING_STATE", "Validating against current state", trace_id=trace_id)
        drift_reason = _check_state_drift(selected_rec, state)

        if drift_reason:
            result = _make_act_error(
                "STALE_STATE",
                (
                    "The warehouse state has changed since this recommendation was generated.\n\n"
                    f"{drift_reason}\n\n"
                    "I need to re-evaluate the situation before preparing the action."
                ),
                recommendation_id=selected_rec.recommendation_id,
                capability=selected_rec.capability,
                target=selected_rec.target,
                source_snapshot_id=selected_rec.snapshot_id,
                current_snapshot_id=current_snapshot_id,
                degraded=False,
            )
            turn = self._make_turn(
                turn_id=turn_id, conv_id=conv.conversation_id, message=message,
                intent=CopilotIntent.ACT, trace_id=trace_id, summary=result.message,
                parent_turn_id=parent_turn_id,
            )
            self._store.add_turn(turn)
            await self._publish("COPILOT_TURN_COMPLETE", "stale_state", trace_id=trace_id)
            return result, turn

        # ── Build GovernedActionRequest ───────────────────────────────────────
        gov_request = GovernedActionRequest(
            recommendation_id=selected_rec.recommendation_id,
            capability=selected_rec.capability,
            target=selected_rec.target,
            domain=selected_rec.domain,
            objective=selected_rec.objective,
            rationale=selected_rec.rationale,
            priority=selected_rec.priority,
            subtype=selected_rec.subtype,
            conversation_id=conv.conversation_id,
            turn_id=turn_id,
            trace_id=trace_id,
            source_turn_id=selected_rec.turn_id,
            source_trace_id=selected_rec.trace_id,
            source_snapshot_id=selected_rec.snapshot_id,
            current_snapshot_id=current_snapshot_id,
            focus_entity_id=selected_rec.focus_entity_id,
        )

        # ── Delegate to GovernedActionOrchestrator ────────────────────────────
        await self._publish("COPILOT_PREPARING_ACTION", "Preparing governed action", trace_id=trace_id)
        try:
            result = await self._orchestrator.govern(
                request=gov_request,
                snapshot=snapshot,
                warehouse_id=warehouse_id,
            )
        except Exception as exc:
            logger.error("CopilotService.act: orchestrator.govern failed — %s", exc)
            result = _make_act_error(
                "ERROR",
                f"Governance failed: {exc}",
                recommendation_id=selected_rec.recommendation_id,
                capability=selected_rec.capability,
                target=selected_rec.target,
                source_snapshot_id=selected_rec.snapshot_id,
                current_snapshot_id=current_snapshot_id,
                degraded=True,
                degradation_reason=str(exc),
            )

        # ── Persist turn with artifact refs ───────────────────────────────────
        artifact_refs: dict[str, str | None] = {}
        if result.proposal_id:
            artifact_refs["proposal_id"] = result.proposal_id
        if result.decision_id:
            artifact_refs["decision_id"] = result.decision_id
        if result.pending_approval_id:
            artifact_refs["pending_approval_id"] = result.pending_approval_id
        if result.execution_id:
            artifact_refs["execution_id"] = result.execution_id

        turn = self._make_turn(
            turn_id=turn_id, conv_id=conv.conversation_id, message=message,
            intent=CopilotIntent.ACT, trace_id=trace_id,
            summary=result.message[:200],
            parent_turn_id=parent_turn_id,
            focus_entity_id=selected_rec.focus_entity_id,
            focus_entity_type=conv.last_focus_entity_type,
            focus_entity_label=conv.last_focus_entity_label,
        )
        turn.artifact_refs.update(artifact_refs)
        self._store.add_turn(turn)
        await self._publish(
            "COPILOT_TURN_COMPLETE",
            f"outcome={result.decision_outcome} mutation={result.mutation_state.value}",
            trace_id=trace_id,
        )
        return result, turn

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _get_state(
        self,
        warehouse_id: str,
        trace_id: str,
        scenario_name: str = "",
    ) -> tuple[Any | None, bool, str | None]:
        """
        Assemble WarehouseState. Returns (state, degraded, degradation_reason).

        Never falls back to simulated data. If provider is unavailable or
        call fails, returns (None, True, reason).
        """
        if self._state_provider is None:
            return None, True, "WarehouseStateProvider is unavailable in this environment."

        try:
            requirements_cls = _StateRequirements
            if requirements_cls is None:
                from maiw_state import StateRequirements as requirements_cls  # type: ignore[no-redef]

            state = await self._state_provider.get_state(
                warehouse_id,
                requirements_cls(equipment=True, labor=True, waves=True),
                trace_id=trace_id,
            )

            # Note any unavailable domains but still return partial state
            missing = []
            if state.equipment is None:
                missing.append("equipment")
            if state.labor is None:
                missing.append("labor")
            if state.waves is None:
                missing.append("waves")

            if missing:
                reason = (
                    f"{', '.join(d.title() for d in missing)} state unavailable — "
                    f"answer may be incomplete for those domains."
                )
                return state, True, reason

            return state, False, None

        except Exception as exc:
            logger.warning("CopilotService._get_state failed — %s", exc)
            return None, True, f"Warehouse state could not be assembled: {exc}"

    async def _publish(self, category: str, message: str, *, trace_id: str) -> None:
        if self._event_bus is None:
            return
        try:
            from maiw_api.demo.events import ScenarioEvent

            event = ScenarioEvent(
                category=category,
                message=message,
                detail=f'{{"trace_id": "{trace_id}"}}',
            )
            await self._event_bus.publish(event)
        except Exception as exc:
            logger.debug("CopilotService._publish failed — %s", exc)

    def _make_turn(
        self,
        *,
        turn_id: str,
        conv_id: str,
        message: str,
        intent: CopilotIntent,
        trace_id: str,
        summary: str,
        parent_turn_id: str | None = None,
        focus_entity_id: str | None = None,
        focus_entity_type: str | None = None,
        focus_entity_label: str | None = None,
    ) -> CopilotTurn:
        return CopilotTurn(
            turn_id=turn_id,
            conversation_id=conv_id,
            user_message=message,
            intent=intent,
            created_at=datetime.now(timezone.utc),
            trace_id=trace_id,
            response_summary=summary[:200],
            artifact_refs={},
            parent_turn_id=parent_turn_id,
            focus_entity_id=focus_entity_id,
            focus_entity_type=focus_entity_type,
            focus_entity_label=focus_entity_label,
        )


# ── ACT helpers ──────────────────────────────────────────────────────────────

import re as _re

_FIRST_PATTERNS = [
    _re.compile(r"\bfirst\b", _re.IGNORECASE),
    _re.compile(r"\bnumber\s*one\b|\b#?1\b|\b1st\b", _re.IGNORECASE),
]
_SECOND_PATTERNS = [
    _re.compile(r"\bsecond\b", _re.IGNORECASE),
    _re.compile(r"\bnumber\s*two\b|\b#?2\b|\b2nd\b", _re.IGNORECASE),
]

_CAPABILITY_KEYWORDS: dict[str, str] = {
    "labor":        "warehouse.labor.allocate",
    "allocat":      "warehouse.labor.allocate",
    "worker":       "warehouse.labor.allocate",
    "wave":         "warehouse.wave.reprioritize",
    "reprioritiz":  "warehouse.wave.reprioritize",
    "equipment":    "warehouse.equipment.assign",
    "assign":       "warehouse.equipment.assign",
    "maintenance":  "warehouse.equipment.schedule_maintenance",
    "release":      "warehouse.equipment.release",
}


def _select_recommendation(
    message: str,
    recs: list[RecommendedActionResult],
) -> tuple[RecommendedActionResult | None, str]:
    """
    Resolve an operator ACT message to a specific recommendation.

    Returns (rec, reason) where reason is one of:
      "single"           — exactly one recommendation; selected directly
      "explicit_index"   — operator referenced first/second/etc.
      "capability_match" — operator referenced capability domain keyword
      "not_found"        — no recommendations available
      "ambiguous"        — multiple recommendations, cannot resolve deterministically
    """
    if not recs:
        return None, "not_found"
    if len(recs) == 1:
        return recs[0], "single"

    msg_lower = message.lower()

    # Explicit index: "first", "one", "#1", "1st", etc.
    for p in _FIRST_PATTERNS:
        if p.search(msg_lower):
            return recs[0], "explicit_index"
    if len(recs) >= 2:
        for p in _SECOND_PATTERNS:
            if p.search(msg_lower):
                return recs[1], "explicit_index"

    # Capability keyword match
    for kw, cap in _CAPABILITY_KEYWORDS.items():
        if kw in msg_lower:
            for rec in recs:
                if rec.capability == cap:
                    return rec, "capability_match"

    return None, "ambiguous"


def _check_state_drift(rec: RecommendedActionResult, state: Any) -> str | None:
    """
    Heuristic pre-flight check: does current state make the recommendation unsafe?

    Returns None if no obvious drift detected.
    Returns a human-readable reason if material state drift is detected.

    The DecisionEngine provides definitive authority; this is a fast
    user-friendly guard before proposal construction.
    """
    cap = rec.capability

    if cap == "warehouse.labor.allocate":
        labor = getattr(state, "labor", None)
        if labor is not None:
            _sentinel = object()
            idle = next(
                (getattr(labor, attr, _sentinel) for attr in ("idle_workers", "workers_idle", "available_workers")
                 if getattr(labor, attr, _sentinel) is not _sentinel),
                None,
            )
            if idle is not None and idle == 0:
                return (
                    "No idle workers are currently available. "
                    "The labor allocation recommendation may no longer be valid."
                )

    if cap == "warehouse.wave.reprioritize":
        waves = getattr(state, "waves", None)
        if waves is not None:
            total = (
                getattr(waves, "total_waves", None)
                or getattr(waves, "total_tasks", None)
                or 0
            )
            if total == 0:
                return (
                    "No active waves found in current state. "
                    "The wave reprioritization recommendation may no longer be valid."
                )

    return None


# ── Answerability helpers ─────────────────────────────────────────────────────

def _missing_context(state: Any | None, scenario_name: str) -> list[str]:
    """
    Return the list of context items that are absent or functionally empty.

    A domain is "missing" if:
    - state is None (completely unavailable), OR
    - the domain attribute is None, OR
    - all key numeric fields are zero (serialized absence, not legitimate empty)

    Distinguishes empty-but-successful (legitimate zero records) from
    unavailable (provider failed or scenario not loaded).

    "Functionally empty" = all key counters are zero AND scenario_name is
    provided but apparently not loaded. A real warehouse always has some
    equipment, workers, or wave records; total-zero across all three domains
    indicates the scenario was not loaded into the runtime.
    """
    if state is None:
        return ["wave_state", "labor_state", "equipment_state"]

    missing = []

    # Check each domain: None attribute = missing
    if getattr(state, "waves", None) is None:
        missing.append("wave_state")
    if getattr(state, "labor", None) is None:
        missing.append("labor_state")
    if getattr(state, "equipment", None) is None:
        missing.append("equipment_state")

    if missing:
        return missing

    # If all three domains are present but all counters are zero, treat as
    # functionally unavailable — scenario not loaded into runtime.
    waves = state.waves
    labor = state.labor
    equipment = state.equipment

    wave_total = getattr(waves, "total_waves", None) or getattr(waves, "total_tasks", None) or 0
    labor_total = getattr(labor, "total_workers", None) or getattr(labor, "total_labor", None) or 0
    equip_total = getattr(equipment, "total_equipment", None) or getattr(equipment, "total", None) or 0

    if wave_total == 0 and labor_total == 0 and equip_total == 0:
        # All zeros across all three domains = scenario not loaded
        return ["wave_state", "labor_state", "equipment_state"]

    return missing


def _build_degradation(
    state_reason: str | None,
    missing: list[str],
    neighborhood: Any,
) -> str | None:
    """Compose a single degradation_reason string covering all missing context."""
    parts = []
    if state_reason:
        parts.append(state_reason.rstrip("."))
    if missing:
        parts.append(f"Missing state domains: {', '.join(missing)}")
    if neighborhood is not None and not getattr(neighborhood, "graph_available", True):
        parts.append("Operational Graph unavailable — neighborhood context not shown")
    return ". ".join(parts) + "." if parts else None


# ── Evidence extraction ───────────────────────────────────────────────────────

_SEVERITY_KEYWORDS = {
    "CRITICAL": "CRITICAL",
    "critical": "CRITICAL",
    "HIGH": "HIGH",
    "high": "HIGH",
    "at-risk": "HIGH",
    "at_risk": "HIGH",
    "OFFLINE": "HIGH",
    "MAINTENANCE": "MEDIUM",
    "maintenance": "MEDIUM",
    "MEDIUM": "MEDIUM",
    "medium": "MEDIUM",
}


def _facts_to_evidence(facts: list[str], assessment_severity: str) -> list[EvidenceFact]:
    """
    Convert OperationalAssessment.facts_observed into structured EvidenceFacts.

    The facts are already structured strings produced by analyze_disruption;
    we parse them into label/value/severity triples for the UI.
    """
    evidence: list[EvidenceFact] = []

    for fact in facts:
        # Detect severity from keywords in the fact text
        severity = None
        for kw, sev in _SEVERITY_KEYWORDS.items():
            if kw in fact:
                severity = sev
                break

        # UNASSIGNED PENDING TASKS is always HIGH — check before partition
        if fact.startswith("UNASSIGNED"):
            evidence.append(EvidenceFact(
                label="Unassigned pending tasks",
                value=fact.partition(": ")[2] or fact,
                severity="HIGH",
            ))
        elif ": " in fact:
            label, _, value = fact.partition(": ")
            evidence.append(EvidenceFact(
                label=label.strip(),
                value=value.strip(),
                severity=severity,
            ))
        else:
            evidence.append(EvidenceFact(
                label="Observation",
                value=fact,
                severity=severity,
            ))

    return evidence
