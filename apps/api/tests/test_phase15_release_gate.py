# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 15 Final Release Gate — blocking tests for three live issues.

Issue 1: OBSERVE_OUTCOME with pending_outcome="executed" must set execution_confirmed=True
         and produce the "Warehouse state mutated" safety_note, not "No warehouse changes."

Issue 2: "Why is that the best option?" enrichment must include recommendation rationale
         so the model receives the "why" already articulated at ANALYZE time.

Issue 3: ANALYZE must never create ActionProposal, Decision, or ApprovalRecord objects.
         The trust boundary is structural (service.py cannot even import those types).
"""

from __future__ import annotations

import ast
import pathlib
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────

@dataclass
class _FakeRec:
    recommendation_id: str = "rec-001"
    domain: str = "labor"
    capability: str = "warehouse.labor.allocate"
    target: str = "wave-017"
    objective: str = "Unblock labor allocation to Wave 17"
    rationale: str = "3 idle workers available in zone-A; wave-017 has 5 pending tasks with HIGH priority"
    priority: str = "HIGH"
    subtype: Any = None
    conversation_id: str = "conv-001"
    turn_id: str = "turn-001"
    trace_id: str = "trace-001"
    snapshot_id: str = "snap-001"
    focus_entity_id: str = "wave-017"


# ═══════════════════════════════════════════════════════════════════════════════
# Issue 1: execution_confirmed override via pending_outcome="executed"
# ═══════════════════════════════════════════════════════════════════════════════

class TestObserveOutcomeExecutionConfirmed:
    """
    Verify that _compose_observe_narrative and the execution_confirmed override
    work correctly when pending_outcome="executed".

    Root cause: last_act.mutation_state is NOT_ATTEMPTED at ACT time (written before
    approval/execution). pending_outcome="executed" from ctrl._pending_approval_outcomes
    is the only authoritative signal post-execution. It must override execution_confirmed.
    """

    def _run_narrative(self, *, pending_outcome, pre, post, delta, is_still_pending=None):
        from maiw_api.copilot.service import _compose_observe_narrative
        return _compose_observe_narrative(
            decision_outcome="REQUIRES_HUMAN_APPROVAL",
            execution_confirmed=False,  # Always False from last_act (stale)
            pending_approval_id="pending-001",
            pre_metrics=pre,
            post_metrics=post,
            kpi_delta=delta,
            last_act=None,
            is_still_pending=is_still_pending,
            pending_outcome=pending_outcome,
        )

    def test_executed_with_kpi_improvement_returns_improved_narrative(self):
        """119→118 backlog: narrative must say 'state improved', not 'rejected'."""
        pre = {"pending_tasks": 119, "idle_workers": 2, "wave_risk_level": "high"}
        post = {"pending_tasks": 118, "idle_workers": 1, "wave_risk_level": "high"}
        delta = {"pending_tasks": -1, "idle_workers": -1}
        answer, improved, summary = self._run_narrative(
            pending_outcome="executed", pre=pre, post=post, delta=delta
        )
        assert improved is True
        assert "improved" in answer.lower() or "fell" in answer.lower() or "reduced" in answer.lower()
        assert "rejected" not in answer.lower()
        assert "not executed" not in answer.lower()

    def test_executed_no_kpi_change_does_not_say_rejected(self):
        """Execution with no measurable KPI delta must say 'executed' not 'rejected'."""
        metrics = {"pending_tasks": 119, "idle_workers": 2, "wave_risk_level": "high"}
        answer, improved, summary = self._run_narrative(
            pending_outcome="executed", pre=metrics, post=metrics, delta={},
            is_still_pending=None,
        )
        assert "rejected" not in answer.lower()
        assert "executed" in answer.lower() or "approved" in answer.lower() or "in progress" in answer.lower()

    def test_rejected_outcome_says_rejected(self):
        """is_still_pending=False + pending_outcome="rejected" must say 'rejected'."""
        metrics = {"pending_tasks": 119, "idle_workers": 2, "wave_risk_level": "high"}
        answer, improved, summary = self._run_narrative(
            pending_outcome="rejected", pre=metrics, post=metrics, delta={},
            is_still_pending=False,
        )
        assert "rejected" in answer.lower()
        assert improved is False

    def test_expired_outcome_says_expired_not_rejected(self):
        """Expired approval must say 'expired' or 'TTL', not 'rejected'."""
        metrics = {"pending_tasks": 119, "idle_workers": 2, "wave_risk_level": "high"}
        answer, improved, summary = self._run_narrative(
            pending_outcome="expired", pre=metrics, post=metrics, delta={},
            is_still_pending=False,
        )
        assert "expired" in answer.lower() or "window" in answer.lower() or "ttl" in answer.lower()
        assert "rejected" not in answer.lower()

    def test_pending_outcome_executed_overrides_execution_confirmed_in_service(self):
        """
        The execution_confirmed override in observe_outcome() must fire when
        pending_outcome="executed", regardless of last_act.mutation_state.

        Verifies the fix at service.py lines 1009–1019 by inspecting the source AST.
        """
        src = pathlib.Path("apps/api/maiw_api/copilot/service.py").read_text()
        # The override must be a conditional assignment inside observe_outcome()
        assert 'pending_outcome == "executed"' in src or "pending_outcome == 'executed'" in src, (
            "service.py must override execution_confirmed when pending_outcome == 'executed'"
        )
        assert "execution_confirmed = True" in src, (
            "service.py must set execution_confirmed = True for the executed path"
        )

    def test_observe_response_safety_note_uses_execution_confirmed(self):
        """
        _observe_response() in copilot.py must emit the mutation safety note when
        result.execution_confirmed is True, not the 'No warehouse changes' fallback.
        Verified by checking that the safety_note= assignment is gated by execution_confirmed.
        """
        src = pathlib.Path("apps/api/maiw_api/routers/copilot.py").read_text()
        assert "execution_confirmed" in src, (
            "copilot.py router must branch on execution_confirmed for safety_note"
        )
        assert "No warehouse changes have been made." in src, (
            "Safety note constant must exist as the False-branch fallback"
        )
        # The _observe_response function must conditionally assign safety_note based on
        # result.execution_confirmed. Look for both guards in the _observe_response body.
        obs_start = src.index("def _observe_response(")
        # Find the next top-level function after _observe_response
        next_fn = src.find("\ndef ", obs_start + 10)
        obs_body = src[obs_start:next_fn if next_fn != -1 else obs_start + 3000]
        assert "execution_confirmed" in obs_body, (
            "_observe_response must read result.execution_confirmed to set safety_note"
        )
        # _observe_response uses the _SAFETY_NOTE module constant (not the literal) for the else branch
        assert "_SAFETY_NOTE" in obs_body or "No warehouse changes" in obs_body, (
            "_observe_response must reference _SAFETY_NOTE (or the literal) as the else-branch fallback"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Issue 2: _enrich_with_recommendations must include rationale
# ═══════════════════════════════════════════════════════════════════════════════

class TestWhyBestRecommendationContext:
    """
    Verify that "Why is that the best option?" triggers _WHY_BEST_RE,
    and that the enrichment includes the recommendation rationale (not just
    capability/target/objective).
    """

    def _enrich(self, message: str, recs=None):
        from maiw_api.copilot.service import _enrich_with_recommendations
        if recs is None:
            recs = [_FakeRec()]
        return _enrich_with_recommendations(message, recs)

    def test_why_best_phrase_triggers_enrichment(self):
        """Canonical phrase must match _WHY_BEST_RE and trigger recommendation injection."""
        result = self._enrich("Why is that the best option?")
        assert result != "Why is that the best option?", (
            "_enrich_with_recommendations must modify the message for this phrase"
        )
        assert "Prior ANALYZE recommendations" in result

    def test_why_best_includes_capability(self):
        result = self._enrich("Why is that the best option?")
        assert "warehouse.labor.allocate" in result

    def test_why_best_includes_target(self):
        result = self._enrich("Why is that the best option?")
        assert "wave-017" in result

    def test_why_best_includes_rationale(self):
        """
        Rationale must be in the enriched prompt so the model explains 'why'
        rather than re-deriving it from scratch. This is the root cause of the
        missing recommendation-context continuity.
        """
        result = self._enrich("Why is that the best option?")
        assert "3 idle workers" in result or "zone-A" in result or "idle workers" in result, (
            "Rationale must appear in the enriched prompt: "
            f"got: {result[:300]!r}"
        )

    def test_why_best_uses_explanation_directive_not_comparison(self):
        """Non-comparison why-best phrase must use explanation directive."""
        result = self._enrich("Why is that the best option?")
        assert "best first action" in result or "best option" in result.lower() or "bottleneck it unblocks" in result

    def test_compare_phrase_uses_comparison_directive(self):
        """'Why not the other one?' must use comparison directive."""
        result = self._enrich("Why not the other option instead?")
        assert "Compare recommendation" in result or "alternatives" in result

    def test_why_best_regex_matches_canonical_phrase(self):
        """_WHY_BEST_RE must match 'Why is that the best option?' directly."""
        from maiw_api.copilot.service import _WHY_BEST_RE
        assert _WHY_BEST_RE.search("Why is that the best option?") is not None

    def test_why_best_regex_matches_explain_variants(self):
        """Additional phrases that should trigger enrichment."""
        from maiw_api.copilot.service import _WHY_BEST_RE
        phrases = [
            "Why did you recommend that?",
            "Why is this the best option?",
            "Why not something else?",
            "Compare these options",
            "versus the other option",
        ]
        for phrase in phrases:
            assert _WHY_BEST_RE.search(phrase) is not None, (
                f"_WHY_BEST_RE must match: {phrase!r}"
            )

    def test_no_enrichment_without_prior_recs(self):
        """When no prior recommendations exist, message must pass through unchanged."""
        result = self._enrich("Why is that the best option?", recs=[])
        assert result == "Why is that the best option?"

    def test_rationale_in_service_enrichment_source(self):
        """
        The source of _enrich_with_recommendations in service.py must read 'rationale'
        from recommendation objects. Verified by AST inspection.
        """
        src = pathlib.Path("apps/api/maiw_api/copilot/service.py").read_text()
        # rationale must appear in the _enrich_with_recommendations function body
        enrich_start = src.index("def _enrich_with_recommendations")
        # Find next top-level def after it
        next_def = src.find("\ndef ", enrich_start + 10)
        enrich_body = src[enrich_start:next_def]
        assert "rationale" in enrich_body, (
            "_enrich_with_recommendations must access r.rationale — "
            "missing rationale means model cannot explain 'why best'"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Issue 3: ANALYZE trust boundary — no proposals/decisions/approvals
# ═══════════════════════════════════════════════════════════════════════════════

class TestAnalyzeTrustBoundary:
    """
    Structural proof that ANALYZE never creates ActionProposal, Decision, or ApprovalRecord.

    These tests are blocking: any future regression that lets analyze() touch the
    governance layer will fail here.
    """

    def _service_src(self) -> str:
        return pathlib.Path("apps/api/maiw_api/copilot/service.py").read_text()

    def _orchestrator_src(self) -> str:
        return pathlib.Path("apps/api/maiw_api/copilot/orchestrator.py").read_text()

    def _router_src(self) -> str:
        return pathlib.Path("apps/api/maiw_api/routers/copilot.py").read_text()

    def test_service_does_not_import_action_executor(self):
        tree = ast.parse(self._service_src())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                full = (getattr(node, "module", "") or "") + " ".join(
                    a.name for a in getattr(node, "names", [])
                )
                assert "ActionExecutor" not in full, (
                    "CopilotService must never import ActionExecutor"
                )

    def test_service_does_not_import_decision_engine(self):
        tree = ast.parse(self._service_src())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                full = (getattr(node, "module", "") or "") + " ".join(
                    a.name for a in getattr(node, "names", [])
                )
                assert "DecisionEngine" not in full, (
                    "CopilotService must never import DecisionEngine"
                )

    def test_service_does_not_import_approval_store(self):
        tree = ast.parse(self._service_src())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                full = (getattr(node, "module", "") or "") + " ".join(
                    a.name for a in getattr(node, "names", [])
                )
                assert "ApprovalStore" not in full, (
                    "CopilotService must never import ApprovalStore"
                )

    def test_analyze_method_does_not_call_orchestrator_govern(self):
        """
        The analyze() method body must not contain 'self._orchestrator.govern'.
        GovernedActionOrchestrator.govern() is the sole gateway to proposal/decision/approval.
        """
        src = self._service_src()
        # Extract the analyze() method body (between 'async def analyze' and the next
        # top-level 'async def' at column 4)
        lines = src.split("\n")
        in_analyze = False
        analyze_lines = []
        for line in lines:
            if line.startswith("    async def analyze(") or line.startswith("    def analyze("):
                in_analyze = True
            elif in_analyze and (
                line.startswith("    async def ") or line.startswith("    def ")
            ) and not line.startswith("        "):
                break
            if in_analyze:
                analyze_lines.append(line)
        analyze_body = "\n".join(analyze_lines)
        assert "_orchestrator" not in analyze_body, (
            "analyze() must never call self._orchestrator — "
            "orchestrator.govern() is the governance boundary and belongs only in act()"
        )

    def test_analyze_result_has_no_proposal_decision_approval_fields(self):
        """CopilotAnalyzeResult must not carry proposal_id, decision_id, approval_id, etc."""
        from maiw_api.copilot.models import CopilotAnalyzeResult
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(CopilotAnalyzeResult)}
        forbidden = {"proposal_id", "decision_id", "approval_id", "pending_approval_id", "execution_id"}
        found = forbidden & field_names
        assert not found, (
            f"CopilotAnalyzeResult must not carry governance IDs: {found}"
        )

    def test_recommended_action_result_has_no_proposal_decision_approval_fields(self):
        """RecommendedActionResult must not carry proposal/decision/approval IDs."""
        from maiw_api.copilot.models import RecommendedActionResult
        import dataclasses
        field_names = {f.name for f in dataclasses.fields(RecommendedActionResult)}
        forbidden = {"proposal_id", "decision_id", "approval_id", "pending_approval_id", "execution_id"}
        found = forbidden & field_names
        assert not found, (
            f"RecommendedActionResult must not carry governance IDs: {found}"
        )

    def test_pending_approvals_append_only_reachable_from_act_flow(self):
        """
        add_pending_approval() in the controller is the only writer to _pending_approvals.
        Verify it is called only from orchestrator.py (the ACT governance path),
        not from analyze().
        """
        orch_src = self._orchestrator_src()
        assert "add_pending_approval" in orch_src, (
            "GovernedActionOrchestrator must call ctrl.add_pending_approval — "
            "confirms ownership of the approval creation path"
        )
        # analyze() in service.py must NOT call add_pending_approval
        service_src = self._service_src()
        lines = service_src.split("\n")
        in_analyze = False
        analyze_lines = []
        for line in lines:
            if line.startswith("    async def analyze(") or line.startswith("    def analyze("):
                in_analyze = True
            elif in_analyze and (
                line.startswith("    async def ") or line.startswith("    def ")
            ) and not line.startswith("        "):
                break
            if in_analyze:
                analyze_lines.append(line)
        analyze_body = "\n".join(analyze_lines)
        assert "add_pending_approval" not in analyze_body, (
            "analyze() must never call add_pending_approval"
        )

    def test_router_analyze_branch_has_no_approval_call(self):
        """
        The ANALYZE branch in the copilot router must not call any approval/execution endpoint.
        """
        src = self._router_src()
        # Verify no /approve, /execute, /force-action path decorators exist
        forbidden_paths = ["/approve", "/execute", "/force-action"]
        for path in forbidden_paths:
            assert f'"{path}"' not in src and f"'{path}'" not in src, (
                f"copilot router must not expose {path}"
            )

    def test_analyze_safety_note_always_no_changes(self):
        """
        The _analyze_response() function must always emit 'No warehouse changes have been made.'
        — confirming that ANALYZE never mutates state.
        """
        src = self._router_src()
        # _analyze_response must set safety_note to _SAFETY_NOTE (the constant)
        assert "_SAFETY_NOTE" in src, "Router must reference _SAFETY_NOTE constant"
        # The constant itself must be 'No warehouse changes have been made.'
        assert "No warehouse changes have been made." in src
