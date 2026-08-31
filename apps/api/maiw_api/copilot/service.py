# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
CopilotService — Phase 15B: ASK path only.

Trust boundary enforced by explicit import restrictions:
    - MUST NOT import ActionExecutor
    - MUST NOT call ApprovalStore.approve
    - MUST NOT call DecisionEngine.evaluate
    - MUST NOT create ActionProposal

These are validated by architecture invariant tests in test_copilot_ask.py.

Degradation policy
------------------
If WarehouseState cannot be assembled (provider unavailable, state provider
None, or exception), ASK returns a structured degraded response rather than
falling back to any simulated/invented operational data.

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
from .models import (
    CopilotAskResult,
    CopilotIntent,
    CopilotTurn,
    EvidenceFact,
)
from .store import InMemoryCopilotStore

logger = logging.getLogger(__name__)


class CopilotService:
    """
    Orchestrates Copilot ASK turns.

    Phase 15B scope: ASK only. ANALYZE and ACT will be added in 15C/15D.

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

    @property
    def store(self) -> InMemoryCopilotStore:
        return self._store

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

        await self._publish("COPILOT_TURN_STARTED", f"Copilot ASK — turn {turn_id[:8]}", trace_id=trace_id)

        # ── Resolve intent ────────────────────────────────────────────────────
        intent = CopilotIntent.ASK
        await self._publish("COPILOT_INTENT_RESOLVED", "intent=ASK", trace_id=trace_id)

        # ── Assemble WarehouseState ───────────────────────────────────────────
        _t_state = time.monotonic()
        state, state_degraded, state_degradation_reason = await self._get_state(
            warehouse_id=warehouse_id,
            scenario_name=scenario_name,
            trace_id=trace_id,
        )
        _state_ms = (time.monotonic() - _t_state) * 1000

        # ── Early answerability check — skip graph lookup if state is missing ─
        missing = _missing_context(state, scenario_name)

        if state is None or missing:
            # Build a null neighborhood — no graph lookup needed
            from maiw_api.copilot.models import ContextNeighborhood as _CN
            neighborhood = _CN(
                focus_entity_id=None,
                focus_entity_label=None,
                entity_ids=[],
                relationship_summary={},
                max_depth=2,
                graph_available=False,
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
                turn_id=turn_id,
                conv_id=conv.conversation_id,
                message=message,
                intent=intent,
                trace_id=trace_id,
                result=result,
            )
            self._store.add_turn(turn)
            await self._publish("COPILOT_TURN_COMPLETE", "degraded=true insufficient_evidence", trace_id=trace_id)
            return result, turn

        # ── Resolve Operational Graph neighborhood (only when state is present) ─
        _t_graph = time.monotonic()
        neighborhood = context_resolver.resolve(
            question=message,
            warehouse_id=warehouse_id,
            graph=self._graph,
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
            result = CopilotAskResult(
                answer="I encountered an error while analyzing the warehouse state.",
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
                turn_id=turn_id,
                conv_id=conv.conversation_id,
                message=message,
                intent=intent,
                trace_id=trace_id,
                result=result,
            )
            self._store.add_turn(turn)
            await self._publish("COPILOT_TURN_COMPLETE", "degraded=true error", trace_id=trace_id)
            return result, turn

        # ── Build structured evidence from assessment facts ───────────────────
        _total_ms = (time.monotonic() - _t0) * 1000
        evidence = _facts_to_evidence(assessment.facts_observed, assessment.severity)

        # Collect all degradation reasons: state domains + graph availability
        full_degradation = _build_degradation(state_degradation_reason, [], neighborhood)
        partial_missing = [m for m in _missing_context(state, scenario_name)]
        answerability = "partial" if (state_degradation_reason or not neighborhood.graph_available) else "answerable"

        result = CopilotAskResult(
            answer=assessment.summary,
            evidence=evidence,
            neighborhood=neighborhood,
            agent="OperationsCoordinationAgent",
            skills_used=[],                              # ASK invokes no tools
            skills_available=assessment.skills_consulted,
            model_id=assessment.model_id,
            reasoning_level="MEDIUM",
            routing_rule=assessment.routing_rule,
            routing_reason=assessment.routing_reason,
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

        turn = self._make_turn(
            turn_id=turn_id,
            conv_id=conv.conversation_id,
            message=message,
            intent=intent,
            trace_id=trace_id,
            result=result,
        )
        self._store.add_turn(turn)
        await self._publish("COPILOT_TURN_COMPLETE", f"model={result.model_id}", trace_id=trace_id)
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
        result: CopilotAskResult,
    ) -> CopilotTurn:
        return CopilotTurn(
            turn_id=turn_id,
            conversation_id=conv_id,
            user_message=message,
            intent=intent,
            created_at=datetime.now(timezone.utc),
            trace_id=trace_id,
            response_summary=result.answer[:200],
            artifact_refs={},
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
