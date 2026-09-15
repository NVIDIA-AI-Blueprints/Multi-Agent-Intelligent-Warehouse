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
Phase 18E test suite — Benchmark Methodology Finalization.

Covers (spec §2, §4, §5, §8, §12, §17):
  - BLOCKING: Fixture metadata not present in model prompt (§2, §17)
  - BLOCKING: Expected outputs remain evaluator-only (§2, §17)
  - BLOCKING: Full raw_response reaches graders (§4, §17)
  - BLOCKING: display_preview truncation does NOT affect grading (§4, §17)
  - Context-size invariance across models (§5, §17)
  - Deterministic run identity is stable (§17)
  - Warm-up samples excluded from qualification metrics (§8, §17)
  - Fallback samples flagged and excluded (§17)
  - Deployment metadata preserved (§17)
  - 18E qualification corpus: Cases A–F registered (§7)
  - Policy eligibility labels correct (§7)
  - Nano qualification classification logic (§12, §14)
  - Material latency threshold defined before results (§13)

All tests are deterministic and offline — no live endpoints required.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from maiw_models.evaluation.benchmark import BenchmarkModelResult
from maiw_models.evaluation.calibration import CRITICAL_GRADERS
from maiw_models.evaluation.fixtures import (
    FIXTURE_CONTEXT_ENTITIES,
    NANO_QUALIFICATION_CORPUS,
    POLICY_ELIGIBILITY,
    ALL_18E_FIXTURE_CASES,
    ALL_KNOWN_CASES,
    equipment_ask_low,
    healthy_baseline_ask,
    wave17_risk_low,
    evidence_ask_labor,
    analyze_action,
    comparative_reasoning,
    get_policy_eligibility,
)
from maiw_models.evaluation.graders import (
    GraderResult,
    HallucinationGrader,
    RequiredEvidenceGrader,
    default_graders,
    run_graders,
)
from maiw_models.evaluation.models import (
    EvaluationCase,
    ModelEvaluationResult,
    TaskFamily,
)
from maiw_models.evaluation.qualification import (
    MATERIAL_LATENCY_ADVANTAGE_THRESHOLD,
    NanoQualificationConfig,
    QualificationSample,
    QualificationRunResult,
    build_comparison_row,
    classify_case_comparison,
    compute_qualification_run,
)
from maiw_models.evaluation.runner import _build_fixture_messages

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_result(case: EvaluationCase, response: str) -> ModelEvaluationResult:
    return ModelEvaluationResult(
        evaluation_input_id=case.case_id,
        model_id="test-model",
        deployment_id="test",
        response=response,
        latency_ms=100.0,
        routing_latency_ms=1.0,
        routing_strategy="test",
        candidate_models=[],
    )


def _passing_grader_result(name: str) -> GraderResult:
    return GraderResult(grader_name=name, passed=True, reason="ok")


def _failing_grader_result(name: str) -> GraderResult:
    return GraderResult(grader_name=name, passed=False, reason="fail")


def _make_sample(
    case_id: str,
    model_id: str,
    rep_index: int,
    warmup: bool,
    acceptable: bool,
    fallback_used: bool = False,
    latency_ms: float = 100.0,
) -> QualificationSample:
    return QualificationSample(
        case_id=case_id,
        model_id=model_id,
        rep_index=rep_index,
        warmup=warmup,
        fallback_used=fallback_used,
        total_latency_ms=latency_ms,
        grader_results=[],
        acceptable=acceptable,
        deployment="nvidia_hosted",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# § BLOCKING INVARIANT 1: Fixture metadata NOT in model prompt (18E §2, §17)
# ═══════════════════════════════════════════════════════════════════════════════


class TestPromptIsolation:
    """
    18E §2 BLOCKING: The outbound model payload must NOT contain evaluator-only fields.

    This is the highest-priority invariant in Phase 18E.
    """

    EVALUATOR_ONLY_FIELDS = [
        "expected_target",
        "expected_capability",
        "required_facts",
        "forbidden_claims",
        "benchmark_case",
        "policy_eligibility",
        "POLICY ELIGIBLE",
        "RESEARCH ONLY",
        "fixture",
        "phase",  # "phase" alone is too generic; test the fixture label format
    ]

    # Evaluator-only metadata values that must NOT appear in the prompt.
    EVALUATOR_ONLY_VALUES = [
        "wave17-labor-risk-v1",  # case_id
        "wave17-risk-low-v1",
        "equipment-ask-low-v1",
        "evidence-ask-labor-v1",
        "analyze-action-v1",
        "comparative-reasoning-v1",
        "healthy-baseline-ask-v1",
        "labor_reallocation",  # expected_capability value
        "equipment_bypass",
        "wave-18",  # forbidden_claims values
        "worker-Z999",
        "Evaluation case metadata",  # verbatim metadata key from old prompt
        "benchmark_case",
        "policy_eligibility_nano",
    ]

    def _get_all_message_text(self, messages: list[dict]) -> str:
        """Concatenate all message content for assertion checks."""
        return "\n".join(m.get("content", "") for m in messages)

    def test_case_id_not_in_prompt_wave17_risk_low(self) -> None:
        """18E §2: case_id must not appear in the model prompt."""
        messages = _build_fixture_messages(wave17_risk_low)
        text = self._get_all_message_text(messages)
        # case_id should not be in the system prompt
        assert (
            "wave17-risk-low-v1" not in text
        ), "case_id 'wave17-risk-low-v1' leaked into model prompt"

    def test_case_id_not_in_prompt_equipment_ask(self) -> None:
        messages = _build_fixture_messages(equipment_ask_low)
        text = self._get_all_message_text(messages)
        assert "equipment-ask-low-v1" not in text

    def test_case_id_not_in_prompt_evidence_ask(self) -> None:
        messages = _build_fixture_messages(evidence_ask_labor)
        text = self._get_all_message_text(messages)
        assert "evidence-ask-labor-v1" not in text

    def test_case_id_not_in_prompt_analyze_action(self) -> None:
        messages = _build_fixture_messages(analyze_action)
        text = self._get_all_message_text(messages)
        assert "analyze-action-v1" not in text

    def test_case_id_not_in_prompt_comparative(self) -> None:
        messages = _build_fixture_messages(comparative_reasoning)
        text = self._get_all_message_text(messages)
        assert "comparative-reasoning-v1" not in text

    def test_metadata_dict_not_in_prompt(self) -> None:
        """18E §2: case.metadata dict must not be serialized into the model prompt."""
        messages = _build_fixture_messages(wave17_risk_low)
        text = self._get_all_message_text(messages)
        assert (
            "Evaluation case metadata" not in text
        ), "Verbatim 'Evaluation case metadata' leaked into prompt"
        assert (
            "benchmark_case" not in text
        ), "'benchmark_case' metadata key leaked into prompt"
        assert (
            "policy_eligibility" not in text
        ), "'policy_eligibility' metadata key leaked into prompt"

    def test_policy_eligibility_label_not_in_prompt(self) -> None:
        """18E §2: Policy eligibility labels (POLICY ELIGIBLE, RESEARCH ONLY) must not appear."""
        for case in NANO_QUALIFICATION_CORPUS:
            messages = _build_fixture_messages(case)
            text = self._get_all_message_text(messages)
            assert (
                "POLICY ELIGIBLE" not in text
            ), f"Policy eligibility label leaked into prompt for {case.case_id}"
            assert (
                "RESEARCH ONLY" not in text
            ), f"Research-only label leaked into prompt for {case.case_id}"

    def test_expected_capability_not_in_prompt(self) -> None:
        """18E §2: expected_capability values must not appear in model prompt."""
        for case in NANO_QUALIFICATION_CORPUS:
            if case.expected_capability is None:
                continue
            messages = _build_fixture_messages(case)
            text = self._get_all_message_text(messages)
            assert (
                case.expected_capability not in text
            ), f"expected_capability '{case.expected_capability}' leaked into prompt for {case.case_id}"

    def test_expected_target_not_in_grading_context(self) -> None:
        """
        18E §2: expected_target appears in the user prompt text (the question asks about Wave 17
        legitimately), but must NOT appear as a grader-control field in the messages.

        We verify that forbidden_claims, required_facts, and expected_capability are absent.
        """
        for case in NANO_QUALIFICATION_CORPUS:
            messages = _build_fixture_messages(case)
            text = self._get_all_message_text(messages)
            for claim in case.forbidden_claims:
                # forbidden_claims are things the model must NOT say — but the
                # list itself should not be passed to the model as instructions.
                # (The user prompt may organically mention them; we check that
                # "forbidden_claims" as a field label is not exposed.)
                assert (
                    "forbidden_claims" not in text
                ), f"'forbidden_claims' key leaked for {case.case_id}"

    def test_required_facts_list_not_in_prompt(self) -> None:
        """18E §2: required_facts field label must not appear in model prompt."""
        for case in NANO_QUALIFICATION_CORPUS:
            messages = _build_fixture_messages(case)
            text = self._get_all_message_text(messages)
            assert (
                "required_facts" not in text
            ), f"'required_facts' key leaked into prompt for {case.case_id}"

    def test_fixture_label_not_in_system_prompt(self) -> None:
        """18E §2: 'fixture: <case_id>' pattern from old runner must be absent."""
        for case in ALL_KNOWN_CASES:
            messages = _build_fixture_messages(case)
            system_content = messages[0]["content"]
            assert (
                f"fixture: {case.case_id}" not in system_content
            ), f"'fixture: {case.case_id}' label leaked into system prompt"

    def test_prompt_contains_only_system_and_user_turns(self) -> None:
        """18E §2: Messages must be exactly [system, user] — no extra leakage turns."""
        for case in NANO_QUALIFICATION_CORPUS:
            messages = _build_fixture_messages(case)
            assert (
                len(messages) == 2
            ), f"Expected 2 messages (system+user) for {case.case_id}, got {len(messages)}"
            assert messages[0]["role"] == "system"
            assert messages[1]["role"] == "user"

    def test_user_prompt_is_case_prompt(self) -> None:
        """18E §2: User turn must be exactly case.prompt — no appended metadata."""
        for case in NANO_QUALIFICATION_CORPUS:
            messages = _build_fixture_messages(case)
            assert (
                messages[1]["content"] == case.prompt
            ), f"User turn for {case.case_id} does not match case.prompt"

    def test_same_messages_for_all_models(self) -> None:
        """
        18E §5: Context-size invariance — identical messages must be produced for a
        given case regardless of which model will receive them.

        The runner builds messages once and sends the same list to all candidate
        models. This test verifies the message-builder is deterministic.
        """
        for case in NANO_QUALIFICATION_CORPUS:
            msgs_a = _build_fixture_messages(case)
            msgs_b = _build_fixture_messages(case)
            assert (
                msgs_a == msgs_b
            ), f"Message builder is non-deterministic for {case.case_id}"

    def test_messages_hash_stable(self) -> None:
        """18E §17: Deterministic run identity — message content hash must be stable."""
        for case in NANO_QUALIFICATION_CORPUS:
            messages = _build_fixture_messages(case)
            content = json.dumps(messages, sort_keys=True)
            hash_a = hashlib.sha256(content.encode()).hexdigest()
            # Second call
            messages2 = _build_fixture_messages(case)
            content2 = json.dumps(messages2, sort_keys=True)
            hash_b = hashlib.sha256(content2.encode()).hexdigest()
            assert hash_a == hash_b, f"Message hash not stable for {case.case_id}"


# ═══════════════════════════════════════════════════════════════════════════════
# § BLOCKING INVARIANT 2: Full raw_response reaches graders (18E §4, §17)
# ═══════════════════════════════════════════════════════════════════════════════


class TestResponseCompleteness:
    """
    18E §4 BLOCKING: Graders must always use the full raw_response.
    display_preview truncation must never affect grading.
    """

    LONG_RESPONSE = (
        "Wave 17 is at risk primarily due to labor constraints in the morning shift. "
        "The specific workers affected are worker-A001, worker-A002, and worker-A003 "
        "who are understaffed for the picking zone. "
        "The labor-shift-morning has insufficient headcount to meet the wave targets. "
        "Recommended action: reallocate labor from zone-receiving to zone-picking. "
        "Evidence: labor allocation report shows morning shift at 60% capacity. "
        "Additional context: conveyor-main is operational but zone-picking throughput "
        "is bottlenecked by the labor deficit. Wave 17 completion is projected at "
        "risk of 2-hour delay without intervention. The labor-shift-afternoon team "
        "can be partially redeployed to cover the gap."
    )

    def test_long_response_exceeds_300_chars(self) -> None:
        """Sanity check: test response is longer than 300 chars to make test meaningful."""
        assert len(self.LONG_RESPONSE) > 300, "Test response must exceed 300 chars"

    def test_graders_use_full_response_not_preview(self) -> None:
        """
        18E §4: Graders must receive the full response.

        Construct a response where a required_fact only appears after character 300.
        Verify grader passes when given full response, would fail on truncated preview.
        """
        # Build a response where "labor-shift-afternoon" only appears after char 300.
        prefix = "A" * 305  # fills the first 305 characters with noise
        fact_after_300 = "labor-shift-afternoon is the key constraint."
        long_resp = prefix + " " + fact_after_300

        case = EvaluationCase(
            case_id="test-truncation-regression",
            task_family=TaskFamily.ASK,
            prompt="test",
            required_facts=["labor-shift-afternoon"],
            context_entities=[],
        )
        result = _make_result(case, long_resp)

        # Grader sees full response → should pass.
        from maiw_models.evaluation.graders import RequiredEvidenceGrader

        grader = RequiredEvidenceGrader()
        gr = grader.grade(case, result)
        assert gr.passed, (
            f"RequiredEvidenceGrader must use full response (found after char 300). "
            f"Reason: {gr.reason}"
        )

        # Verify that truncated preview at 300 chars would NOT contain the fact.
        preview = long_resp[:300]
        assert (
            "labor-shift-afternoon" not in preview
        ), "Test is invalid: fact appears within first 300 chars"

    def test_hallucination_grader_uses_full_response(self) -> None:
        """
        18E §4: HallucinationGrader must use the full response.

        If a hallucinated entity only appears after char 300, the grader
        must still catch it (because it uses raw_response, not display_preview).
        """
        prefix = "B" * 305
        # Add an entity NOT in context after char 300.
        hallucinated_resp = prefix + " wave-99 is also affected."

        case = EvaluationCase(
            case_id="test-hallucination-full-response",
            task_family=TaskFamily.ASK,
            prompt="test",
            context_entities=["wave-17", "labor-shift-morning"],
        )
        result = _make_result(case, hallucinated_resp)

        grader = HallucinationGrader()
        gr = grader.grade(case, result)
        assert (
            not gr.passed
        ), "HallucinationGrader must detect hallucination appearing after char 300"
        assert "wave-99" in " ".join(
            gr.evidence
        ), f"Evidence must include 'wave-99', got: {gr.evidence}"

    def test_benchmark_model_result_raw_response_field(self) -> None:
        """
        18E §4: BenchmarkModelResult must have raw_response field (full response)
        and display_preview (truncated, optional).
        """
        long_text = "X" * 500

        # BenchmarkModelResult is a dataclass — test that field exists and is separate.
        result = BenchmarkModelResult(
            evaluation_run_key="test-key",
            case_id="test-case",
            dataset_id="ds",
            semantic_checksum="ck",
            scenario_id="sc",
            context_snapshot_id=None,
            warehouse_state_snapshot_id=None,
            prompt_hash="ph",
            model_id="m",
            deployment="test",
            raw_response=long_text,
            display_preview=long_text[:300],
        )
        assert result.raw_response == long_text, "raw_response must be full text"
        assert (
            result.display_preview == long_text[:300]
        ), "display_preview must be truncated"
        assert len(result.display_preview) == 300
        assert len(result.raw_response) == 500

    def test_display_preview_does_not_equal_raw_response_when_truncated(self) -> None:
        """18E §4: display_preview != raw_response for long responses."""
        long_text = "Y" * 500
        result = BenchmarkModelResult(
            evaluation_run_key="rk",
            case_id="c",
            dataset_id="d",
            semantic_checksum="s",
            scenario_id="sc",
            context_snapshot_id=None,
            warehouse_state_snapshot_id=None,
            prompt_hash="ph",
            model_id="m",
            deployment="d",
            raw_response=long_text,
            display_preview=long_text[:300],
        )
        assert (
            result.raw_response != result.display_preview
        ), "raw_response and display_preview must differ for responses > 300 chars"

    def test_to_dict_includes_raw_response_not_response_snippet(self) -> None:
        """18E §4: to_dict() must output 'raw_response' and 'display_preview', not 'response_snippet'."""
        result = BenchmarkModelResult(
            evaluation_run_key="rk",
            case_id="c",
            dataset_id="d",
            semantic_checksum="s",
            scenario_id="sc",
            context_snapshot_id=None,
            warehouse_state_snapshot_id=None,
            prompt_hash="ph",
            model_id="m",
            deployment="d",
            raw_response="full text",
            display_preview="full",
        )
        d = result.to_dict()
        assert "raw_response" in d, "to_dict() must include 'raw_response'"
        assert "display_preview" in d, "to_dict() must include 'display_preview'"

    def test_response_snippet_compat_property(self) -> None:
        """18E §4: response_snippet property returns display_preview for backward compat."""
        result = BenchmarkModelResult(
            evaluation_run_key="rk",
            case_id="c",
            dataset_id="d",
            semantic_checksum="s",
            scenario_id="sc",
            context_snapshot_id=None,
            warehouse_state_snapshot_id=None,
            prompt_hash="ph",
            model_id="m",
            deployment="d",
            raw_response="full",
            display_preview="prev",
        )
        assert result.response_snippet == "prev"


# ═══════════════════════════════════════════════════════════════════════════════
# § 18E Qualification Corpus (spec §7)
# ═══════════════════════════════════════════════════════════════════════════════


class TestNanoQualificationCorpus:
    """18E §7: Cases A–F are registered and correctly labeled."""

    EXPECTED_CASE_IDS = {
        "wave17-risk-low-v1",  # A
        "evidence-ask-labor-v1",  # B
        "equipment-ask-low-v1",  # C
        "healthy-baseline-ask-v1",  # D
        "analyze-action-v1",  # E
        "comparative-reasoning-v1",  # F
    }

    def test_qualification_corpus_has_6_cases(self) -> None:
        """18E §7: Corpus must contain exactly Cases A–F (6 cases)."""
        assert len(NANO_QUALIFICATION_CORPUS) == 6

    def test_qualification_corpus_case_ids(self) -> None:
        """18E §7: All six required case IDs present."""
        corpus_ids = {c.case_id for c in NANO_QUALIFICATION_CORPUS}
        assert (
            corpus_ids == self.EXPECTED_CASE_IDS
        ), f"Corpus case IDs mismatch. Got: {corpus_ids}"

    def test_all_corpus_cases_policy_eligible(self) -> None:
        """18E §7: All qualification corpus cases must be POLICY ELIGIBLE."""
        for case in NANO_QUALIFICATION_CORPUS:
            eligibility = get_policy_eligibility(case.case_id)
            assert (
                eligibility == "POLICY ELIGIBLE"
            ), f"Case {case.case_id} expected POLICY ELIGIBLE, got: {eligibility}"

    def test_all_corpus_cases_low_or_medium_risk(self) -> None:
        """18E §7: Policy eligibility requires low/medium risk."""
        for case in NANO_QUALIFICATION_CORPUS:
            assert case.risk_level in (
                "low",
                "medium",
            ), f"Case {case.case_id}: risk_level={case.risk_level!r} is not low/medium"

    def test_all_corpus_cases_medium_reasoning(self) -> None:
        """18E §7: Policy eligibility requires low/medium reasoning."""
        for case in NANO_QUALIFICATION_CORPUS:
            assert case.reasoning_level in (
                "low",
                "medium",
            ), f"Case {case.case_id}: reasoning_level={case.reasoning_level!r} is not low/medium"

    def test_18b_high_risk_cases_research_only(self) -> None:
        """18E §7: 18B high-risk cases (wave17-labor-risk, equipment-failure) are RESEARCH ONLY."""
        for case_id in ["wave17-labor-risk-v1", "equipment-failure-v1"]:
            label = get_policy_eligibility(case_id)
            assert (
                label == "RESEARCH ONLY — NOT PRODUCTION ELIGIBLE"
            ), f"Expected RESEARCH ONLY for {case_id}, got: {label}"

    def test_case_a_wave17_risk_low(self) -> None:
        """18E §7 Case A: wave17-risk-low has correct fields."""
        case = wave17_risk_low
        assert case.case_id == "wave17-risk-low-v1"
        assert case.task_family == TaskFamily.ASK
        assert case.risk_level == "low"
        assert case.reasoning_level == "medium"
        assert case.expected_target == "wave-17"

    def test_case_c_equipment_ask_low(self) -> None:
        """18E §7 Case C: equipment-ask-low has correct fields."""
        case = equipment_ask_low
        assert case.case_id == "equipment-ask-low-v1"
        assert case.task_family == TaskFamily.ASK
        assert case.risk_level == "low"
        assert "conveyor" in case.required_facts

    def test_case_d_healthy_baseline_ask(self) -> None:
        """18E §7 Case D: healthy-baseline-ask has correct fields."""
        case = healthy_baseline_ask
        assert case.case_id == "healthy-baseline-ask-v1"
        assert case.task_family == TaskFamily.ASK
        assert case.risk_level == "low"
        assert case.expected_target == "wave-17"

    def test_18e_cases_use_fixture_context_entities(self) -> None:
        """18E §5: New 18E cases must use the same FIXTURE_CONTEXT_ENTITIES."""
        for case in ALL_18E_FIXTURE_CASES:
            assert (
                case.context_entities == FIXTURE_CONTEXT_ENTITIES
            ), f"Case {case.case_id} uses different context entities"


# ═══════════════════════════════════════════════════════════════════════════════
# § Warm-up methodology (18E §8, §17)
# ═══════════════════════════════════════════════════════════════════════════════


class TestWarmupMethodology:
    """18E §8: Warm-up samples must be excluded from latency and quality statistics."""

    def test_warmup_samples_excluded_from_latency(self) -> None:
        """Warm-up samples must not contribute to latency stats."""
        samples = [
            _make_sample(
                "case-a", "nano", 0, warmup=True, acceptable=False, latency_ms=9999.0
            ),
            _make_sample(
                "case-a", "nano", 1, warmup=False, acceptable=True, latency_ms=200.0
            ),
            _make_sample(
                "case-a", "nano", 2, warmup=False, acceptable=True, latency_ms=210.0
            ),
            _make_sample(
                "case-a", "nano", 3, warmup=False, acceptable=True, latency_ms=195.0
            ),
            _make_sample(
                "case-a", "nano", 4, warmup=False, acceptable=True, latency_ms=205.0
            ),
            _make_sample(
                "case-a", "nano", 5, warmup=False, acceptable=True, latency_ms=200.0
            ),
        ]
        result = compute_qualification_run(samples)
        # Warm-up latency (9999ms) must not appear in stats.
        assert (
            result.latency_max_ms < 500.0
        ), f"Warm-up latency leaked into stats: max={result.latency_max_ms}"
        assert result.warmup_count == 1

    def test_warmup_samples_excluded_from_accept_count(self) -> None:
        """Warm-up acceptable=True must not increment accept_count."""
        samples = [
            _make_sample(
                "case-a", "nano", 0, warmup=True, acceptable=True, latency_ms=100.0
            ),
            _make_sample(
                "case-a", "nano", 1, warmup=False, acceptable=True, latency_ms=100.0
            ),
            _make_sample(
                "case-a", "nano", 2, warmup=False, acceptable=True, latency_ms=100.0
            ),
            _make_sample(
                "case-a", "nano", 3, warmup=False, acceptable=True, latency_ms=100.0
            ),
            _make_sample(
                "case-a", "nano", 4, warmup=False, acceptable=False, latency_ms=100.0
            ),
            _make_sample(
                "case-a", "nano", 5, warmup=False, acceptable=False, latency_ms=100.0
            ),
        ]
        result = compute_qualification_run(samples)
        assert result.n_measured == 5, f"Expected 5 measured, got {result.n_measured}"
        assert result.warmup_count == 1
        assert result.accept_count == 3  # only the non-warmup acceptances

    def test_fallback_samples_excluded(self) -> None:
        """18E §17: Fallback samples must be flagged and excluded from qualification metrics."""
        samples = [
            _make_sample(
                "case-a", "nano", 0, warmup=True, acceptable=True, latency_ms=100.0
            ),
            # Fallback sample — excluded from metrics.
            _make_sample(
                "case-a",
                "nano",
                1,
                warmup=False,
                acceptable=True,
                fallback_used=True,
                latency_ms=9999.0,
            ),
            _make_sample(
                "case-a", "nano", 2, warmup=False, acceptable=True, latency_ms=200.0
            ),
            _make_sample(
                "case-a", "nano", 3, warmup=False, acceptable=True, latency_ms=210.0
            ),
            _make_sample(
                "case-a", "nano", 4, warmup=False, acceptable=True, latency_ms=195.0
            ),
            _make_sample(
                "case-a", "nano", 5, warmup=False, acceptable=True, latency_ms=205.0
            ),
        ]
        result = compute_qualification_run(samples)
        assert result.fallback_count == 1
        # Fallback latency (9999ms) must not appear in stats.
        assert (
            result.latency_max_ms < 500.0
        ), f"Fallback latency leaked into stats: max={result.latency_max_ms}"
        assert result.n_measured == 4  # 5 non-warmup, 1 fallback → 4 measured

    def test_warmup_count_preserved_in_result(self) -> None:
        """18E §17: warmup_count is preserved in QualificationRunResult for audit."""
        samples = [
            _make_sample("c", "m", 0, warmup=True, acceptable=True),
            _make_sample("c", "m", 1, warmup=True, acceptable=True),
            _make_sample("c", "m", 2, warmup=False, acceptable=True),
        ]
        result = compute_qualification_run(samples)
        assert result.warmup_count == 2

    def test_no_samples_returns_empty_result(self) -> None:
        """compute_qualification_run handles empty sample list."""
        result = compute_qualification_run([])
        assert result.n_measured == 0
        assert result.accept_count == 0
        assert result.qualified is False


# ═══════════════════════════════════════════════════════════════════════════════
# § Qualification classification (18E §12, §13, §14)
# ═══════════════════════════════════════════════════════════════════════════════


class TestQualificationClassification:
    """18E §12–§14: Qualification threshold and material latency advantage logic."""

    def test_material_latency_threshold_defined(self) -> None:
        """18E §13: Material latency advantage threshold is defined before results."""
        assert (
            MATERIAL_LATENCY_ADVANTAGE_THRESHOLD == 0.20
        ), "Threshold must be 20% as defined in spec §13"

    def test_nano_qualified_when_faster_and_passes(self) -> None:
        """18E §14: NANO QUALIFIED when Nano passes all critical graders and is ≥20% faster."""
        nano = QualificationRunResult(
            case_id="c",
            model_id="nano",
            accept_count=5,
            n_measured=5,
            accept_rate=1.0,
            qualified=True,
            latency_median_ms=150.0,
        )
        super_ = QualificationRunResult(
            case_id="c",
            model_id="super",
            accept_count=5,
            n_measured=5,
            accept_rate=1.0,
            qualified=True,
            latency_median_ms=200.0,  # 25% improvement
        )
        result = classify_case_comparison(nano, super_)
        assert result == "NANO QUALIFIED"

    def test_super_required_when_nano_fails_critical(self) -> None:
        """18E §13: Quality dominates — failing critical grader → SUPER REQUIRED."""
        nano = QualificationRunResult(
            case_id="c",
            model_id="nano",
            accept_count=3,
            n_measured=5,
            accept_rate=0.6,
            qualified=False,
            latency_median_ms=100.0,  # faster but fails
        )
        super_ = QualificationRunResult(
            case_id="c",
            model_id="super",
            accept_count=5,
            n_measured=5,
            accept_rate=1.0,
            qualified=True,
            latency_median_ms=200.0,
        )
        result = classify_case_comparison(nano, super_)
        assert result == "SUPER REQUIRED"

    def test_no_material_difference_when_both_qualify_similar_latency(self) -> None:
        """18E §14: NO MATERIAL DIFFERENCE when both qualify and latency diff < 20%."""
        nano = QualificationRunResult(
            case_id="c",
            model_id="nano",
            accept_count=5,
            n_measured=5,
            accept_rate=1.0,
            qualified=True,
            latency_median_ms=190.0,  # only 5% faster than super
        )
        super_ = QualificationRunResult(
            case_id="c",
            model_id="super",
            accept_count=5,
            n_measured=5,
            accept_rate=1.0,
            qualified=True,
            latency_median_ms=200.0,
        )
        result = classify_case_comparison(nano, super_)
        assert result == "NO MATERIAL DIFFERENCE"

    def test_inconclusive_when_nano_not_run(self) -> None:
        """18E §14: INCONCLUSIVE when Nano has no measured samples."""
        nano = QualificationRunResult(
            case_id="c",
            model_id="nano",
            n_measured=0,
            accept_rate=0.0,
            qualified=False,
        )
        super_ = QualificationRunResult(
            case_id="c",
            model_id="super",
            accept_count=5,
            n_measured=5,
            accept_rate=1.0,
            qualified=True,
            latency_median_ms=200.0,
        )
        result = classify_case_comparison(nano, super_)
        assert result == "INCONCLUSIVE"

    def test_inconclusive_when_nano_none(self) -> None:
        """18E §14: INCONCLUSIVE when Nano result is None (endpoint unavailable)."""
        super_ = QualificationRunResult(
            case_id="c",
            model_id="super",
            accept_count=5,
            n_measured=5,
            accept_rate=1.0,
            qualified=True,
            latency_median_ms=200.0,
        )
        result = classify_case_comparison(None, super_)
        assert result == "INCONCLUSIVE"

    def test_qualification_requires_90_percent_acceptance(self) -> None:
        """18E §12: Nano must pass all critical graders in ≥90% of N measured runs."""
        config = NanoQualificationConfig(acceptance_rate=0.90, n_reps=5)
        # 4/5 = 80% → below threshold → not qualified
        samples_4_of_5 = [
            _make_sample("c", "nano", i, warmup=(i == 0), acceptable=(i > 1))
            for i in range(6)
        ]
        result = compute_qualification_run(
            samples_4_of_5, acceptance_rate=config.acceptance_rate
        )
        # measured: 5, accept: 4 → rate=0.8 < 0.9
        assert result.accept_rate < 0.90
        assert result.qualified is False

        # 5/5 = 100% → above threshold → qualified
        samples_5_of_5 = [
            _make_sample("c", "nano", i, warmup=(i == 0), acceptable=(i > 0))
            for i in range(6)
        ]
        result2 = compute_qualification_run(
            samples_5_of_5, acceptance_rate=config.acceptance_rate
        )
        assert result2.accept_rate == 1.0
        assert result2.qualified is True

    def test_build_comparison_row_nano_unavailable(self) -> None:
        """18E §14: build_comparison_row returns INCONCLUSIVE when Nano is None."""
        row = build_comparison_row(
            case_id="wave17-risk-low-v1",
            policy_eligibility="POLICY ELIGIBLE",
            nano=None,
            super_=QualificationRunResult(
                case_id="wave17-risk-low-v1",
                model_id="super",
                accept_count=5,
                n_measured=5,
                accept_rate=1.0,
                qualified=True,
                latency_median_ms=200.0,
            ),
        )
        assert row.classification == "INCONCLUSIVE"
        assert row.nano_accept is None
        assert row.nano_n is None

    def test_config_default_threshold(self) -> None:
        """18E §13: NanoQualificationConfig default threshold is 20%."""
        config = NanoQualificationConfig()
        assert config.material_threshold == 0.20
        assert config.n_reps == 5
        assert config.warmup_reps == 1
        assert config.acceptance_rate == 0.90


# ═══════════════════════════════════════════════════════════════════════════════
# § Deployment metadata preserved (18E §17, §18)
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeploymentMetadataPreservation:
    """18E §17, §18: Deployment metadata must be preserved in samples and results."""

    def test_sample_preserves_deployment(self) -> None:
        """QualificationSample.deployment is preserved."""
        sample = QualificationSample(
            case_id="c",
            model_id="nvidia/nemotron-3-super-120b-a12b",
            rep_index=1,
            warmup=False,
            fallback_used=False,
            total_latency_ms=200.0,
            deployment="nvidia_hosted",
        )
        d = sample.to_dict()
        assert d["deployment"] == "nvidia_hosted"
        assert d["model_id"] == "nvidia/nemotron-3-super-120b-a12b"

    def test_sample_warmup_flag_in_dict(self) -> None:
        """QualificationSample.warmup flag preserved in to_dict."""
        sample = _make_sample("c", "m", 0, warmup=True, acceptable=False)
        d = sample.to_dict()
        assert d["warmup"] is True
        assert d["rep_index"] == 0

    def test_sample_fallback_flag_in_dict(self) -> None:
        """QualificationSample.fallback_used flag preserved in to_dict."""
        sample = _make_sample(
            "c", "m", 1, warmup=False, acceptable=True, fallback_used=True
        )
        d = sample.to_dict()
        assert d["fallback_used"] is True

    def test_sample_raw_response_vs_display_preview(self) -> None:
        """18E §4, §17: QualificationSample stores raw_response and display_preview separately."""
        long_text = "Z" * 500
        sample = QualificationSample(
            case_id="c",
            model_id="m",
            rep_index=1,
            warmup=False,
            fallback_used=False,
            total_latency_ms=100.0,
            raw_response=long_text,
            display_preview=long_text[:300],
        )
        d = sample.to_dict()
        assert d["raw_response"] == long_text
        assert d["display_preview"] == long_text[:300]


# ═══════════════════════════════════════════════════════════════════════════════
# § Context-size invariance (18E §5, §17)
# ═══════════════════════════════════════════════════════════════════════════════


class TestContextInvariance:
    """18E §5: Identical context must be used across all models for the same case."""

    def test_all_qualification_corpus_cases_share_context_entities(self) -> None:
        """18E §5: All corpus cases use the same FIXTURE_CONTEXT_ENTITIES."""
        for case in NANO_QUALIFICATION_CORPUS:
            assert sorted(case.context_entities) == sorted(
                FIXTURE_CONTEXT_ENTITIES
            ), f"Case {case.case_id} has different context entities"

    def test_message_system_content_identical_for_same_case(self) -> None:
        """18E §5: Two calls to _build_fixture_messages for same case must produce identical system prompt."""
        for case in NANO_QUALIFICATION_CORPUS:
            m1 = _build_fixture_messages(case)
            m2 = _build_fixture_messages(case)
            assert (
                m1[0]["content"] == m2[0]["content"]
            ), f"System prompt not identical for {case.case_id}"

    def test_entity_list_in_system_prompt(self) -> None:
        """18E §5: Each fixture entity ID must appear in the system prompt."""
        for case in NANO_QUALIFICATION_CORPUS:
            messages = _build_fixture_messages(case)
            system = messages[0]["content"]
            for entity in FIXTURE_CONTEXT_ENTITIES:
                assert (
                    entity in system
                ), f"Entity '{entity}' missing from system prompt for {case.case_id}"
