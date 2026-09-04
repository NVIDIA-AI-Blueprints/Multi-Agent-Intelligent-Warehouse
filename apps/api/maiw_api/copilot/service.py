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
    CopilotObserveResult,
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

            # Enrich context when the operator is asking a comparative question
            # about why a prior recommendation is the best option.
            enriched_context = _enrich_with_recommendations(message, conv.last_recommendations)

            assessment = await self._agent.analyze_disruption(
                snapshot=snapshot,
                scenario_context=enriched_context,
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
        # Graph unavailability is captured in full_degradation; it must not
        # demote answerability — the answer is still grounded in state facts.
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

        # ── Capture pre-ACT state metrics for OBSERVE_OUTCOME comparison ─────
        pre_metrics = _extract_state_metrics(state)

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

        # ── Store ACT result in conversation for OBSERVE_OUTCOME ──────────────
        conv.last_act_result = result
        conv.last_act_pre_state_metrics = pre_metrics

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

    async def observe_outcome(
        self,
        *,
        message: str,
        conversation_id: str | None,
        warehouse_id: str,
        scenario_name: str = "",
        is_still_pending: bool | None = None,
        pending_outcome: str | None = None,
    ) -> tuple[CopilotObserveResult, CopilotTurn]:
        """
        Process an OBSERVE_OUTCOME turn: compare pre-ACT state with current state.

        Reads current WarehouseState, compares with pre_metrics captured at ACT time,
        and generates a narrative outcome assessment. Zero writes — read-only.

        is_still_pending: injected by the router after checking the approval queue.
            True  = pending_approval_id still queued (not yet decided)
            False = removed from queue AND outcome is 'rejected' or 'expired'
            None  = outcome is 'executed' (let operational_improved guide narrative)
                    or status unknown (controller unavailable / no prior ACT)
        pending_outcome: 'executed' | 'rejected' | 'expired' | None
            Terminal outcome from ctrl._pending_approval_outcomes, or None if unknown.
        """
        _t0 = time.monotonic()
        trace_id = str(uuid.uuid4())
        turn_id = str(uuid.uuid4())

        conv = self._store.get_or_create(conversation_id, warehouse_id, scenario_name)
        parent_turn_id = conv.last_turn.turn_id if conv.last_turn else None
        from maiw_api.copilot.models import ContextNeighborhood as _CN

        await self._publish("COPILOT_TURN_STARTED", f"Copilot OBSERVE — turn {turn_id[:8]}", trace_id=trace_id)
        await self._publish("COPILOT_INTENT_RESOLVED", "intent=OBSERVE_OUTCOME", trace_id=trace_id)

        # ── No prior ACT on this conversation ─────────────────────────────────
        last_act = conv.last_act_result
        pre_metrics = conv.last_act_pre_state_metrics or {}

        if last_act is None:
            answer = (
                "I have not performed any governed action in this conversation yet. "
                "Ask 'What should we do?' to get recommendations, then 'Do it.' to request a governed action."
            )
            neighborhood = _CN(
                focus_entity_id=None, focus_entity_label=None, entity_ids=[],
                relationship_summary={}, max_depth=2, graph_available=False,
                entity_resolution=None,
            )
            result = CopilotObserveResult(
                answer=answer,
                execution_confirmed=False,
                pre_metrics={},
                post_metrics={},
                kpi_delta={},
                operational_improved=False,
                operational_summary="No prior action to observe.",
                act_pending_approval_id=None,
                act_decision_outcome=None,
                evidence=[],
                neighborhood=neighborhood,
                agent="OperationsCoordinationAgent",
                model_id="none",
                reasoning_level="LOW",
                routing_rule="none",
                routing_reason="No prior ACT in conversation",
                trace_id=trace_id,
                snapshot_id="none",
                warehouse_id=warehouse_id,
                latency_ms=(time.monotonic() - _t0) * 1000,
                degraded=False,
                answerability="answerable",
            )
            turn = self._make_turn(
                turn_id=turn_id, conv_id=conv.conversation_id, message=message,
                intent=CopilotIntent.OBSERVE_OUTCOME, trace_id=trace_id, summary=answer,
                parent_turn_id=parent_turn_id,
            )
            self._store.add_turn(turn)
            await self._publish("COPILOT_TURN_COMPLETE", "no_prior_act", trace_id=trace_id)
            return result, turn

        # ── Read current state ────────────────────────────────────────────────
        await self._publish("COPILOT_READING_STATE", "Reading current warehouse state for outcome", trace_id=trace_id)
        _t_state = time.monotonic()
        state, state_degraded, state_degradation_reason = await self._get_state(
            warehouse_id=warehouse_id,
            scenario_name=scenario_name,
            trace_id=trace_id,
        )
        _state_ms = (time.monotonic() - _t_state) * 1000

        neighborhood = context_resolver.resolve(
            question=message,
            warehouse_id=warehouse_id,
            graph=self._graph,
            focus_entity_id=conv.last_focus_entity_id,
            focus_entity_label=conv.last_focus_entity_label,
        )

        if state is None:
            answer = (
                "I cannot assess the outcome because current warehouse state is unavailable. "
                + (state_degradation_reason or "")
            ).strip()
            result = CopilotObserveResult(
                answer=answer,
                execution_confirmed=False,
                pre_metrics=pre_metrics,
                post_metrics={},
                kpi_delta={},
                operational_improved=False,
                operational_summary="State unavailable — cannot compare.",
                act_pending_approval_id=getattr(last_act, "pending_approval_id", None),
                act_decision_outcome=getattr(last_act, "decision_outcome", None),
                evidence=[],
                neighborhood=neighborhood,
                agent="OperationsCoordinationAgent",
                model_id="none",
                reasoning_level="LOW",
                routing_rule="none",
                routing_reason="State unavailable",
                trace_id=trace_id,
                snapshot_id="none",
                warehouse_id=warehouse_id,
                latency_ms=(time.monotonic() - _t0) * 1000,
                degraded=True,
                degradation_reason=state_degradation_reason,
                answerability="insufficient_evidence",
            )
            turn = self._make_turn(
                turn_id=turn_id, conv_id=conv.conversation_id, message=message,
                intent=CopilotIntent.OBSERVE_OUTCOME, trace_id=trace_id, summary=answer,
                parent_turn_id=parent_turn_id,
            )
            self._store.add_turn(turn)
            await self._publish("COPILOT_TURN_COMPLETE", "state_unavailable", trace_id=trace_id)
            return result, turn

        # ── Compute post-metrics and delta ────────────────────────────────────
        post_metrics = _extract_state_metrics(state)
        kpi_delta = _compute_kpi_delta(pre_metrics, post_metrics)

        decision_outcome = getattr(last_act, "decision_outcome", None)
        mutation_state = getattr(last_act, "mutation_state", None)
        execution_confirmed = (
            mutation_state is not None and
            getattr(mutation_state, "value", str(mutation_state)) == "CONFIRMED"
        )
        # The last_act_result is written at ACT time (mutation_state=NOT_ATTEMPTED).
        # After the human approves and execution runs, last_act_result is never updated.
        # pending_outcome="executed" from ctrl._pending_approval_outcomes is the only
        # authoritative signal that execution actually completed for this approval path.
        if pending_outcome == "executed":
            execution_confirmed = True
        pending_approval_id = getattr(last_act, "pending_approval_id", None)

        # ── Compose narrative ─────────────────────────────────────────────────
        answer, operational_improved, summary = _compose_observe_narrative(
            decision_outcome=decision_outcome,
            execution_confirmed=execution_confirmed,
            pending_approval_id=pending_approval_id,
            pre_metrics=pre_metrics,
            post_metrics=post_metrics,
            kpi_delta=kpi_delta,
            last_act=last_act,
            is_still_pending=is_still_pending,
            pending_outcome=pending_outcome,
        )

        evidence = _facts_to_evidence(
            _observe_facts(pre_metrics, post_metrics, kpi_delta), "HIGH"
        )

        result = CopilotObserveResult(
            answer=answer,
            execution_confirmed=execution_confirmed,
            pre_metrics=pre_metrics,
            post_metrics=post_metrics,
            kpi_delta=kpi_delta,
            operational_improved=operational_improved,
            operational_summary=summary,
            act_pending_approval_id=pending_approval_id,
            act_decision_outcome=decision_outcome,
            evidence=evidence,
            neighborhood=neighborhood,
            agent="OperationsCoordinationAgent",
            model_id="state-comparison",
            reasoning_level="LOW",
            routing_rule="deterministic",
            routing_reason="KPI delta comparison — no model inference",
            trace_id=trace_id,
            snapshot_id=post_metrics.get("snapshot_id", "unknown"),
            warehouse_id=warehouse_id,
            latency_ms=(time.monotonic() - _t0) * 1000,
            degraded=state_degraded,
            degradation_reason=state_degradation_reason,
            answerability="answerable",
            timing={
                "state_assembly_ms": round(_state_ms, 1),
                "graph_lookup_ms": 0.0,
                "model_inference_ms": 0.0,
                "total_ms": round((time.monotonic() - _t0) * 1000, 1),
            },
        )

        turn = self._make_turn(
            turn_id=turn_id, conv_id=conv.conversation_id, message=message,
            intent=CopilotIntent.OBSERVE_OUTCOME, trace_id=trace_id, summary=summary,
            parent_turn_id=parent_turn_id,
            focus_entity_id=conv.last_focus_entity_id,
            focus_entity_type=conv.last_focus_entity_type,
            focus_entity_label=conv.last_focus_entity_label,
        )
        self._store.add_turn(turn)
        await self._publish(
            "COPILOT_TURN_COMPLETE",
            f"improved={operational_improved} confirmed={execution_confirmed}",
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


# ── Recommendation context enrichment ────────────────────────────────────────

_WHY_BEST_RE = _re.compile(
    r"\b(why\b|why.*best|why.*option|why.*recommend|why.*that|explain.*recommend"
    r"|best option|why not|compare|makes.*better|instead of|versus|vs\.?|what.*differ)\b",
    _re.IGNORECASE,
)


def _enrich_with_recommendations(message: str, recs: list) -> str:
    """
    Inject prior ANALYZE recommendation context when the operator asks a follow-up
    explanation or comparison question (e.g. "Why REALLOCATE_LABOR?", "Why not X?").

    Returns the original message when no enrichment is needed.
    """
    if not recs or not _WHY_BEST_RE.search(message):
        return message
    rec_lines = []
    for i, r in enumerate(recs[:3]):
        cap = getattr(r, "capability", "")
        tgt = getattr(r, "target", "")
        pri = getattr(r, "priority", "")
        obj = getattr(r, "objective", "")
        rat = getattr(r, "rationale", "") or ""
        rat_clause = f" Rationale: {rat}" if rat else ""
        rec_lines.append(f"  #{i + 1}: {cap} → {tgt} ({pri} priority) — {obj}.{rat_clause}")
    rec_summary = "\n".join(rec_lines)
    is_comparison = _re.search(r"\b(why not|compare|instead|versus|vs\.?|differ|makes.*better)\b", message, _re.IGNORECASE)
    if is_comparison:
        directive = (
            "Compare recommendation #1 against the alternatives. Explain which specific "
            "bottleneck each addresses and why #1 delivers the highest operational impact "
            "first. Be concise — do not repeat the full warehouse diagnosis."
        )
    else:
        directive = (
            "Explain why recommendation #1 is the best first action given the current "
            "warehouse state. Reference the specific operational bottleneck it unblocks. "
            "Do not repeat the full warehouse diagnosis."
        )
    return (
        f"{message}\n\n"
        f"Prior ANALYZE recommendations:\n{rec_summary}\n\n"
        f"{directive}"
    )


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


def _extract_state_metrics(state: Any) -> dict:
    """
    Extract key KPI metrics from a WarehouseState for pre/post comparison.
    Returns an empty dict for absent domains rather than raising.
    """
    metrics: dict = {}
    if state is None:
        return metrics

    waves = getattr(state, "waves", None)
    labor = getattr(state, "labor", None)
    equipment = getattr(state, "equipment", None)

    if waves:
        metrics["pending_tasks"] = (
            getattr(waves, "pending_count", None)
            or getattr(waves, "pending_tasks", None)
            or 0
        )
        metrics["wave_risk_score"] = getattr(waves, "risk_score", None) or 0
        metrics["wave_risk_level"] = getattr(waves, "risk_level", None) or "unknown"
        metrics["at_risk_tasks"] = getattr(waves, "at_risk_count", None) or 0

    if labor:
        idle = next(
            (getattr(labor, attr, None) for attr in
             ("idle_workers", "workers_idle", "available_workers")
             if getattr(labor, attr, None) is not None),
            None,
        )
        metrics["idle_workers"] = idle if idle is not None else 0
        metrics["total_workers"] = getattr(labor, "total_workers", None) or 0
        metrics["active_workers"] = getattr(labor, "active_workers", None) or 0

    if equipment:
        metrics["equipment_available"] = getattr(equipment, "available", None) or 0
        metrics["equipment_offline"] = getattr(equipment, "offline", None) or 0

    return metrics


def _compute_kpi_delta(pre: dict, post: dict) -> dict:
    """Compute post - pre for numeric KPIs shared between both snapshots."""
    delta: dict = {}
    for key in pre:
        if key in post and isinstance(pre[key], (int, float)) and isinstance(post[key], (int, float)):
            delta[key] = post[key] - pre[key]
    # Include string fields with change markers
    for key in ("wave_risk_level",):
        if key in pre and key in post and pre[key] != post[key]:
            delta[f"{key}_change"] = f"{pre[key]} → {post[key]}"
    return delta


def _compose_observe_narrative(
    *,
    decision_outcome: str | None,
    execution_confirmed: bool,
    pending_approval_id: str | None,
    pre_metrics: dict,
    post_metrics: dict,
    kpi_delta: dict,
    last_act: Any,
    is_still_pending: bool | None = None,
    pending_outcome: str | None = None,
) -> tuple[str, bool, str]:
    """
    Compose the OBSERVE_OUTCOME narrative.
    Returns (answer, operational_improved, summary).
    """
    backlog_delta = kpi_delta.get("pending_tasks", None)
    idle_delta = kpi_delta.get("idle_workers", None)
    risk_delta = kpi_delta.get("wave_risk_score", None)
    risk_level_change = kpi_delta.get("wave_risk_level_change", None)

    pre_backlog = pre_metrics.get("pending_tasks", "unknown")
    post_backlog = post_metrics.get("pending_tasks", "unknown")
    pre_idle = pre_metrics.get("idle_workers", "unknown")
    post_idle = post_metrics.get("idle_workers", "unknown")
    pre_risk = pre_metrics.get("wave_risk_level", "unknown")
    post_risk = post_metrics.get("wave_risk_level", "unknown")

    # Determine if operationally improved
    operational_improved = False
    improvement_signals = []
    if backlog_delta is not None and backlog_delta < 0:
        operational_improved = True
        improvement_signals.append(f"pending backlog fell from {pre_backlog} to {post_backlog}")
    if idle_delta is not None and idle_delta < 0:
        operational_improved = True
        improvement_signals.append(f"idle workers reduced from {pre_idle} to {post_idle}")
    if risk_level_change:
        improvement_signals.append(f"wave risk classification: {risk_level_change}")
        # Treat risk reduction as improvement
        risk_order = ["critical", "high", "medium", "low", "none", "unknown"]
        pre_idx = next((i for i, r in enumerate(risk_order) if r in str(pre_risk).lower()), 999)
        post_idx = next((i for i, r in enumerate(risk_order) if r in str(post_risk).lower()), 999)
        if post_idx > pre_idx:
            operational_improved = True

    # Case 1: REQUIRES_HUMAN_APPROVAL — check if state changed (implies approval occurred)
    if decision_outcome == "REQUIRES_HUMAN_APPROVAL":
        if not pre_metrics or not post_metrics:
            return (
                "The action was submitted for human approval. "
                "I cannot compare state because baseline metrics were not captured.",
                False,
                "State comparison unavailable.",
            )

        if operational_improved and improvement_signals:
            signals_str = "; ".join(improvement_signals)
            _one_task = (
                "\n\nWhy only one task resolved? A single governed action unblocks the "
                "highest-priority allocation bottleneck. Broader backlog reduction requires "
                "additional reallocation cycles authorized through the governance pipeline."
            ) if backlog_delta is not None and backlog_delta == -1 else ""
            answer = (
                f"Yes — the warehouse state improved after the governed action was executed. "
                f"{signals_str.capitalize()}.{_one_task}\n\n"
                f"The action was approved and executed through the MAIW governance pipeline. "
                f"The operational bottleneck has been partially resolved."
            )
            summary = f"Improvement confirmed: {improvement_signals[0]}"
        elif (not kpi_delta or pre_metrics == post_metrics):
            # State unchanged — distinguish still-pending, rejected, or unknown
            if is_still_pending is True:
                answer = (
                    "The action has not been executed. Human approval is still required.\n\n"
                    "Open the APPROVE stage in MAIW to review and authorize the action."
                )
                summary = "Awaiting human approval — action not yet executed."
            elif is_still_pending is False:
                if pending_outcome == "expired":
                    answer = (
                        "The approval window closed before the operator acted. "
                        "The action was not executed — no warehouse changes were made.\n\n"
                        "You can request a new governed action via the ACT command."
                    )
                    summary = "Approval expired — action not executed."
                else:
                    answer = (
                        "No. The proposed action was rejected by the human reviewer and was never executed. "
                        "No warehouse changes were made — the state is unchanged from before the action was requested."
                    )
                    summary = "Action rejected — no warehouse change."
                operational_improved = False
            elif pending_outcome == "executed":
                answer = (
                    "The action was approved and executed through the MAIW governance pipeline. "
                    "No immediate warehouse KPI change was detected — the task may still be in progress "
                    "or requires a clock tick to register the completed allocation."
                )
                summary = "Executed — no immediate KPI delta detected."
            else:
                answer = (
                    "The warehouse state has not changed since the action was submitted. "
                    "Either the approval is still pending, or the action was not executed.\n\n"
                    "Open the APPROVE stage in MAIW to check the approval status."
                )
                summary = "No state change detected — approval status unknown."
            operational_improved = False
        else:
            answer = (
                "The warehouse state changed after the action, but not all indicators improved.\n\n"
                f"OBSERVED STATE\n"
                f"Pending tasks: {pre_backlog} → {post_backlog}\n"
                f"Idle workers: {pre_idle} → {post_idle}\n"
                f"Wave risk: {pre_risk} → {post_risk}\n\n"
                "The execution may have partially succeeded. Review the approval panel for details."
            )
            summary = "Partial state change observed."

        return answer, operational_improved, summary

    # Case 2: APPROVED + execution confirmed
    if execution_confirmed:
        if operational_improved and improvement_signals:
            signals_str = "; ".join(improvement_signals)
            _one_task = (
                "\n\nWhy only one task resolved? A single governed action unblocks the "
                "highest-priority allocation bottleneck. Broader backlog reduction requires "
                "additional reallocation cycles authorized through the governance pipeline."
            ) if backlog_delta is not None and backlog_delta == -1 else ""
            answer = (
                f"Yes. The action executed and the operational state improved. "
                f"{signals_str.capitalize()}.{_one_task}\n\n"
                f"The labor allocation was executed through the MAIW governance pipeline."
            )
            summary = f"Execution confirmed; improvement observed: {improvement_signals[0]}"
        else:
            answer = (
                "The action executed successfully (CONFIRMED), "
                "but the key operational metrics have not yet changed measurably. "
                f"Pending backlog: {pre_backlog} → {post_backlog}. "
                f"Idle workers: {pre_idle} → {post_idle}.\n\n"
                "This may indicate a processing delay in the warehouse system."
            )
            summary = "Execution confirmed; no measurable operational improvement yet."
        return answer, operational_improved, summary

    # Case 3: REJECTED
    if decision_outcome == "REJECTED":
        return (
            "The action was rejected by the MAIW decision engine and was never executed. "
            "No warehouse changes were made. The warehouse state has not changed as a result of this action.",
            False,
            "Action rejected — no state change.",
        )

    # Case 4: UNKNOWN execution
    if decision_outcome == "APPROVED" and not execution_confirmed:
        return (
            "The execution result is uncertain. The backend may have accepted the action, "
            "but acknowledgement was not confirmed.\n\n"
            "Automatic retry has been suppressed. Reconciliation is required before "
            "I can confirm whether the operational state improved.",
            False,
            "Execution status uncertain — reconciliation required.",
        )

    # Fallback
    return (
        f"The last governed action outcome was: {decision_outcome or 'unknown'}. "
        f"I cannot confirm operational improvement without execution confirmation.",
        False,
        f"Outcome: {decision_outcome or 'unknown'}",
    )


def _observe_facts(pre: dict, post: dict, delta: dict) -> list[str]:
    """Build fact strings for OBSERVE_OUTCOME evidence cards."""
    facts = []
    if "pending_tasks" in pre and "pending_tasks" in post:
        facts.append(f"Pending tasks: {pre['pending_tasks']} → {post['pending_tasks']}")
    if "idle_workers" in pre and "idle_workers" in post:
        facts.append(f"Idle workers: {pre['idle_workers']} → {post['idle_workers']}")
    if "wave_risk_level" in pre and "wave_risk_level" in post:
        facts.append(f"Wave risk: {pre['wave_risk_level']} → {post['wave_risk_level']}")
    if "wave_risk_score" in pre and "wave_risk_score" in post:
        facts.append(f"Wave risk score: {pre['wave_risk_score']} → {post['wave_risk_score']}")
    return facts


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
