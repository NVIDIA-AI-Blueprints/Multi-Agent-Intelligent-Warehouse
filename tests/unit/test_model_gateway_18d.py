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
Phase 18D test suite — Benchmark Calibration.

Covers (spec §37):
  - Canonical entity alias resolution (§9–§11)
  - False-positive hallucination prevention (§12)
  - Target normalization diagnostics (§13)
  - Invalid entity rejection (§10, §12)
  - Grader regression: canonical ID, display name, valid alias, wrong entity,
    nonexistent entity, unsupported fact (§15)
  - Saved-result re-grading (§16)
  - Latency sample classification and fallback exclusion (§22)
  - Evaluation repeatability metadata (§33)
  - Policy eligibility labels (§4, §27)
  - RequiredEvidence canonical alias matching (§14)
  - CapabilityMatch extended synonyms (§15)
  - 18D fixture case registration (§6)

All tests are deterministic and offline — no live endpoints required.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from maiw_models.evaluation.resolver import (
    EntityResolver,
    ContextEntity,
    ResolvedEntity,
    build_allowed_surface_forms,
    resolve_entity_reference,
    _canonical_aliases,
)
from maiw_models.evaluation.graders import (
    HallucinationGrader,
    RequiredEvidenceGrader,
    TargetMatchGrader,
    CapabilityMatchGrader,
    default_graders,
    run_graders,
)
from maiw_models.evaluation.calibration import (
    CRITICAL_GRADERS,
    NON_CRITICAL_GRADERS,
    CalibratedCaseResult,
    LatencySample,
    RegradeRecord,
    compute_latency_stats,
    is_critical,
    policy_label,
    regrade_result,
)
from maiw_models.evaluation.fixtures import (
    FIXTURE_CONTEXT_ENTITIES,
    ALL_FIXTURE_CASES,
    ALL_18D_FIXTURE_CASES,
    ALL_KNOWN_CASES,
    wave17_labor_risk,
    equipment_failure,
    healthy_baseline,
    evidence_ask_labor,
    analyze_action,
    comparative_reasoning,
)
from maiw_models.evaluation.models import (
    EvaluationCase,
    ModelEvaluationResult,
    TaskFamily,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def make_result(
    model_id: str = "nvidia/nemotron-3-super-120b-a12b",
    response: str = "",
    error: str | None = None,
) -> ModelEvaluationResult:
    return ModelEvaluationResult(
        evaluation_input_id="test-input",
        model_id=model_id,
        deployment_id="nvidia_hosted",
        response=response,
        error=error,
        latency_ms=1000.0,
        routing_latency_ms=0.01,
        routing_strategy="forced_evaluation",
        candidate_models=[model_id],
        input_tokens=50,
        output_tokens=30,
    )


def make_case(
    case_id: str = "test-case",
    context_entities: list[str] | None = None,
    required_facts: list[str] | None = None,
    expected_target: str | None = None,
    expected_capability: str | None = None,
) -> EvaluationCase:
    return EvaluationCase(
        case_id=case_id,
        task_family=TaskFamily.ASK,
        prompt="test prompt",
        context_entities=context_entities or FIXTURE_CONTEXT_ENTITIES,
        required_facts=required_facts or [],
        expected_target=expected_target,
        expected_capability=expected_capability,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Part 1 — Canonical entity resolver (§9–§11)
# ══════════════════════════════════════════════════════════════════════════════


class TestCanonicalAliases:
    """_canonical_aliases must produce deterministic, bounded alias sets."""

    def test_exact_id_included(self):
        aliases = _canonical_aliases("wave-17")
        assert "wave-17" in aliases

    def test_hyphen_to_space(self):
        aliases = _canonical_aliases("wave-17")
        assert "wave 17" in aliases

    def test_hyphen_to_underscore(self):
        aliases = _canonical_aliases("wave-17")
        assert "wave_17" in aliases

    def test_underscore_to_space(self):
        aliases = _canonical_aliases("conveyor_main")
        assert "conveyor main" in aliases

    def test_case_insensitive_lowercased(self):
        aliases = _canonical_aliases("Worker-A001")
        assert "worker-a001" in aliases
        assert "worker a001" in aliases

    def test_no_arbitrary_expansion(self):
        """Aliases are ONLY deterministic substitutions — no fuzzy expansion."""
        aliases = _canonical_aliases("wave-17")
        # These must NOT be in aliases:
        assert "wave seventeen" not in aliases
        assert "w-17" not in aliases
        assert "wave-18" not in aliases


class TestEntityResolver:
    """EntityResolver resolves surface forms to canonical IDs."""

    @pytest.fixture
    def resolver(self) -> EntityResolver:
        return EntityResolver.from_context_ids(
            ["wave-17", "conveyor-main", "labor-shift-morning"]
        )

    def test_exact_id_resolves(self, resolver):
        assert resolver.resolve("wave-17") == "wave-17"

    def test_hyphen_space_variant_resolves(self, resolver):
        """'wave 17' → 'wave-17' (§9: canonical surface form)."""
        assert resolver.resolve("wave 17") == "wave-17"

    def test_case_insensitive(self, resolver):
        assert resolver.resolve("Wave 17") == "wave-17"
        assert resolver.resolve("WAVE-17") == "wave-17"

    def test_underscore_variant_resolves(self, resolver):
        assert resolver.resolve("wave_17") == "wave-17"

    def test_wrong_entity_does_not_resolve(self, resolver):
        """'Wave 18' must NOT resolve to 'wave-17'. (§9)"""
        assert resolver.resolve("Wave 18") is None

    def test_nonexistent_entity_does_not_resolve(self, resolver):
        assert resolver.resolve("wave-99") is None

    def test_common_english_hyphenated_word_does_not_resolve(self, resolver):
        """'in-scope', 'well-known' are NOT warehouse entities."""
        assert resolver.resolve("in-scope") is None
        assert resolver.resolve("well-known") is None

    def test_labor_bottleneck_does_not_resolve(self, resolver):
        """'labor-bottleneck' is a description, not a context entity."""
        assert resolver.resolve("labor-bottleneck") is None

    def test_multi_entity_context(self, resolver):
        assert resolver.resolve("conveyor main") == "conveyor-main"
        assert resolver.resolve("labor shift morning") == "labor-shift-morning"


class TestResolveEntityReference:
    """Public resolve_entity_reference API (§11)."""

    def test_resolves_wave_17(self):
        result = resolve_entity_reference("wave 17", ["wave-17", "conveyor-main"])
        assert result == "wave-17"

    def test_wrong_entity_returns_none(self):
        result = resolve_entity_reference("Wave 18", ["wave-17", "conveyor-main"])
        assert result is None

    def test_empty_context_returns_none(self):
        result = resolve_entity_reference("wave-17", [])
        assert result is None

    def test_conveyor_main_resolves(self):
        result = resolve_entity_reference("conveyor main", ["wave-17", "conveyor-main"])
        assert result == "conveyor-main"


class TestBuildAllowedSurfaceForms:
    """build_allowed_surface_forms expands context entities to all approved aliases."""

    def test_contains_exact_ids(self):
        forms = build_allowed_surface_forms(["wave-17", "conveyor-main"])
        assert "wave-17" in forms
        assert "conveyor-main" in forms

    def test_contains_space_variants(self):
        forms = build_allowed_surface_forms(["wave-17"])
        assert "wave 17" in forms

    def test_does_not_contain_wrong_entity(self):
        forms = build_allowed_surface_forms(["wave-17"])
        assert "wave 18" not in forms
        assert "wave-18" not in forms

    def test_empty_returns_empty(self):
        forms = build_allowed_surface_forms([])
        assert len(forms) == 0


# ══════════════════════════════════════════════════════════════════════════════
# Part 2 — Calibrated HallucinationGrader (§12)
# ══════════════════════════════════════════════════════════════════════════════


class TestHallucinationGraderCalibrated:
    """
    Hallucination grader must NOT produce false failures for canonical surface forms.
    Must still reject truly hallucinated entities.
    """

    @pytest.fixture
    def grader(self) -> HallucinationGrader:
        return HallucinationGrader()

    @pytest.fixture
    def case(self) -> EvaluationCase:
        return make_case()

    def test_canonical_id_passes(self, grader, case):
        """'wave-17' is in context → pass."""
        result = make_result(response="The primary issue is wave-17 capacity.")
        r = grader.grade(case, result)
        assert r.passed, f"Expected pass but got: {r.reason}"

    def test_display_name_passes(self, grader, case):
        """'Wave 17' (space variant) resolves to 'wave-17' → pass (§12)."""
        result = make_result(response="Wave 17 is at risk due to insufficient labor.")
        r = grader.grade(case, result)
        assert r.passed, f"Expected pass (Wave 17 is canonical alias): {r.reason}"

    def test_uppercase_canonical_passes(self, grader, case):
        """'WAVE-17' case-insensitive match → pass."""
        result = make_result(response="WAVE-17 shows a labor bottleneck.")
        r = grader.grade(case, result)
        assert r.passed, f"Expected pass (WAVE-17 is canonical alias): {r.reason}"

    def test_wrong_entity_fails(self, grader, case):
        """'wave-18' is NOT in context → fail (true hallucination)."""
        result = make_result(response="Wave-18 is the primary concern, not wave-17.")
        r = grader.grade(case, result)
        assert not r.passed, "wave-18 not in context — should fail"
        assert "wave-18" in [e.lower() for e in r.evidence]

    def test_nonexistent_entity_fails(self, grader, case):
        """'worker-Z999' is explicitly NOT in context → fail."""
        result = make_result(response="worker-Z999 is the key bottleneck.")
        r = grader.grade(case, result)
        assert not r.passed

    def test_no_context_entities_passes(self, grader):
        """No context_entities defined → grader skips (pass unconditionally)."""
        case_no_ctx = EvaluationCase(
            case_id="test-no-ctx",
            task_family=TaskFamily.ASK,
            prompt="test",
            context_entities=[],  # explicitly empty — not using make_case helper
        )
        result = make_result(response="some-unknown-entity-999 is the issue.")
        r = grader.grade(case_no_ctx, result)
        assert r.passed, "No context → skip hallucination check"

    def test_empty_response_passes(self, grader, case):
        result = make_result(response="")
        r = grader.grade(case, result)
        assert r.passed

    def test_conveyor_backup_passes(self, grader, case):
        """'conveyor-backup' is in FIXTURE_CONTEXT_ENTITIES → pass."""
        result = make_result(response="Use conveyor-backup as an alternative path.")
        r = grader.grade(case, result)
        assert r.passed, f"conveyor-backup is in context: {r.reason}"

    def test_common_word_still_fails_if_not_in_context(self, grader, case):
        """'high-priority' used in phrase — if not in context, still checked."""
        # 'sku-high-priority' IS in FIXTURE_CONTEXT_ENTITIES but 'high-priority' alone is not
        result = make_result(response="This is a high-priority issue.")
        r = grader.grade(case, result)
        # 'high-priority' is not an alias of any fixture entity (sku-high-priority is)
        # So it should be flagged — this is correct strict behavior
        assert not r.passed
        assert "high-priority" in r.evidence


# ══════════════════════════════════════════════════════════════════════════════
# Part 3 — RequiredEvidenceGrader canonical alias matching (§14)
# ══════════════════════════════════════════════════════════════════════════════


class TestRequiredEvidenceGraderCalibrated:
    """
    Required evidence grader must accept canonical surface forms of entity-like facts.
    """

    @pytest.fixture
    def grader(self) -> RequiredEvidenceGrader:
        return RequiredEvidenceGrader()

    def test_exact_fact_passes(self, grader):
        """Required fact 'labor' found exactly → pass."""
        case = make_case(required_facts=["labor"])
        result = make_result(response="Labor is the constraint.")
        r = grader.grade(case, result)
        assert r.passed

    def test_entity_id_fact_space_variant_passes(self, grader):
        """'wave-17' fact satisfied by 'Wave 17' (§12 example)."""
        case = make_case(required_facts=["wave-17"])
        result = make_result(response="Wave 17 is the focus of the analysis.")
        r = grader.grade(case, result)
        assert r.passed, f"'Wave 17' should satisfy fact 'wave-17': {r.reason}"

    def test_entity_id_fact_exact_still_passes(self, grader):
        """Exact 'wave-17' in response → pass."""
        case = make_case(required_facts=["wave-17"])
        result = make_result(response="The wave-17 backlog is 200 units.")
        r = grader.grade(case, result)
        assert r.passed

    def test_wrong_entity_fact_fails(self, grader):
        """'wave-18' cannot satisfy fact 'wave-17'."""
        case = make_case(required_facts=["wave-17"])
        result = make_result(response="Wave 18 analysis complete.")
        r = grader.grade(case, result)
        assert not r.passed

    def test_missing_fact_fails(self, grader):
        """Response does not contain required fact → fail."""
        case = make_case(required_facts=["wave-17", "labor"])
        result = make_result(response="Equipment is fine.")
        r = grader.grade(case, result)
        assert not r.passed
        assert r.score == 0.0

    def test_partial_facts_partial_score(self, grader):
        """Some facts found → partial score."""
        case = make_case(required_facts=["wave-17", "labor"])
        result = make_result(response="Wave 17 analysis.")  # wave-17 ✓, labor ✗
        r = grader.grade(case, result)
        assert not r.passed
        assert r.score == pytest.approx(0.5)

    def test_all_facts_found_full_score(self, grader):
        case = make_case(required_facts=["wave-17", "labor"])
        result = make_result(response="Wave 17 is impacted by a labor shortage.")
        r = grader.grade(case, result)
        assert r.passed
        assert r.score == pytest.approx(1.0)

    def test_underscore_variant_passes(self, grader):
        """'wave_17' satisfies fact 'wave-17'."""
        case = make_case(required_facts=["wave-17"])
        result = make_result(response="wave_17 is the focus.")
        r = grader.grade(case, result)
        assert r.passed


# ══════════════════════════════════════════════════════════════════════════════
# Part 4 — TargetMatchGrader diagnostics (§13)
# ══════════════════════════════════════════════════════════════════════════════


class TestTargetMatchGraderDiagnostics:
    """TargetMatchGrader emits model_reference / resolved_entity_id diagnostics."""

    @pytest.fixture
    def grader(self) -> TargetMatchGrader:
        return TargetMatchGrader()

    def test_canonical_id_passes_with_diagnostic(self, grader):
        case = make_case(expected_target="wave-17")
        result = make_result(response="The wave-17 backlog is at risk.")
        r = grader.grade(case, result)
        assert r.passed
        # Diagnostic should be in evidence
        diag_str = next((e for e in r.evidence if "{" in e), None)
        assert diag_str is not None
        diag = json.loads(diag_str)
        assert diag["resolved_entity_id"] == "wave-17"
        assert diag["expected_entity_id"] == "wave-17"
        assert diag["match"] is True

    def test_space_variant_passes_with_diagnostic(self, grader):
        case = make_case(expected_target="wave-17")
        result = make_result(response="Wave 17 is at risk.")
        r = grader.grade(case, result)
        assert r.passed
        diag_str = next((e for e in r.evidence if "{" in e), None)
        assert diag_str is not None
        diag = json.loads(diag_str)
        assert diag["resolved_entity_id"] == "wave-17"
        assert diag["match"] is True

    def test_wrong_target_fails_with_diagnostic(self, grader):
        case = make_case(expected_target="wave-17")
        result = make_result(response="Wave 18 is the priority today.")
        r = grader.grade(case, result)
        assert not r.passed
        diag_str = next((e for e in r.evidence if "{" in e), None)
        assert diag_str is not None
        diag = json.loads(diag_str)
        assert diag["match"] is False

    def test_no_target_defined_skips(self, grader):
        case = make_case(expected_target=None)
        result = make_result(response="Some analysis here.")
        r = grader.grade(case, result)
        assert r.passed
        assert "skipped" in r.reason


# ══════════════════════════════════════════════════════════════════════════════
# Part 5 — CapabilityMatchGrader extended synonyms (§15)
# ══════════════════════════════════════════════════════════════════════════════


class TestCapabilityMatchGraderCalibrated:
    """Extended synonym list for equipment_bypass reduces false negatives."""

    @pytest.fixture
    def grader(self) -> CapabilityMatchGrader:
        return CapabilityMatchGrader()

    def test_direct_slug_passes(self, grader):
        case = make_case(expected_capability="equipment_bypass")
        result = make_result(response="Recommend equipment bypass to avoid the fault.")
        r = grader.grade(case, result)
        assert r.passed

    def test_bypass_synonym_passes(self, grader):
        case = make_case(expected_capability="equipment_bypass")
        result = make_result(response="Reroute traffic through the secondary conveyor.")
        r = grader.grade(case, result)
        assert r.passed

    def test_backup_conveyor_synonym_passes(self, grader):
        """18D addition: 'backup conveyor' satisfies equipment_bypass."""
        case = make_case(expected_capability="equipment_bypass")
        result = make_result(response="Use the backup conveyor to maintain throughput.")
        r = grader.grade(case, result)
        assert r.passed, f"'backup conveyor' should match equipment_bypass: {r.reason}"

    def test_switch_to_backup_synonym_passes(self, grader):
        """18D addition: 'switch to backup' satisfies equipment_bypass."""
        case = make_case(expected_capability="equipment_bypass")
        result = make_result(response="Switch to backup immediately to avoid delays.")
        r = grader.grade(case, result)
        assert r.passed, f"'switch to backup' should match: {r.reason}"

    def test_alternate_path_synonym_passes(self, grader):
        """18D addition: 'alternate path' satisfies equipment_bypass."""
        case = make_case(expected_capability="equipment_bypass")
        result = make_result(response="Use the alternate path for Wave 17 units.")
        r = grader.grade(case, result)
        assert r.passed, f"'alternate path' should match: {r.reason}"

    def test_wrong_capability_fails(self, grader):
        """Response recommending labor reallocation should not pass equipment_bypass."""
        case = make_case(expected_capability="equipment_bypass")
        result = make_result(response="Reallocate workers from Zone A to Zone B.")
        r = grader.grade(case, result)
        assert not r.passed

    def test_labor_reallocation_synonyms(self, grader):
        case = make_case(expected_capability="labor_reallocation")
        result = make_result(
            response="Redistribute labor from morning to afternoon shift."
        )
        r = grader.grade(case, result)
        assert r.passed


# ══════════════════════════════════════════════════════════════════════════════
# Part 6 — Grader criticality classification (§26)
# ══════════════════════════════════════════════════════════════════════════════


class TestGraderCriticality:
    """Critical graders must block model acceptability."""

    def test_hallucination_is_critical(self):
        assert is_critical("hallucination")

    def test_capability_match_is_critical(self):
        assert is_critical("capability_match")

    def test_target_match_is_critical(self):
        assert is_critical("target_match")

    def test_schema_validity_is_critical(self):
        assert is_critical("schema_validity")

    def test_required_evidence_not_critical(self):
        assert not is_critical("required_evidence")

    def test_forbidden_claims_not_critical(self):
        assert not is_critical("forbidden_claims")

    def test_critical_grader_set_complete(self):
        assert CRITICAL_GRADERS == frozenset(
            {"hallucination", "capability_match", "target_match", "schema_validity"}
        )


# ══════════════════════════════════════════════════════════════════════════════
# Part 7 — Saved-result re-grading (§16)
# ══════════════════════════════════════════════════════════════════════════════


class TestRegradeResult:
    """regrade_result re-grades saved 18C outputs without model re-calls."""

    def _make_original_grader_results(
        self, grader_results: list[tuple[str, bool, str]]
    ) -> list[dict]:
        """Build saved grader result dicts from (name, passed, reason) tuples."""
        return [
            {"name": name, "passed": passed, "reason": reason, "evidence": []}
            for name, passed, reason in grader_results
        ]

    def test_regrade_fixes_wave17_required_evidence(self):
        """
        18C false failure: required_facts=['wave-17'] but response says 'Wave 17'.
        Calibrated grader should fix this.
        """
        case = make_case(
            required_facts=["wave-17", "labor"],
            context_entities=FIXTURE_CONTEXT_ENTITIES,
        )
        result = make_result(
            response="Wave 17 is at risk due to labor shortages in the morning shift."
        )
        original_graders = self._make_original_grader_results(
            [
                (
                    "schema_validity",
                    True,
                    "No expected_schema defined — schema check skipped.",
                ),
                ("hallucination", True, "No entity IDs outside context detected."),
                (
                    "capability_match",
                    True,
                    "No expected_capability defined — capability check skipped.",
                ),
                ("target_match", True, "Response references expected target: wave-17"),
                (
                    "required_evidence",
                    False,
                    "1/2 required facts found. Missing: ['wave-17']",
                ),
                ("forbidden_claims", True, "No forbidden claims detected (4 checked)."),
            ]
        )
        cal = regrade_result(case, result, original_graders)
        # Required evidence should now pass (Wave 17 → wave-17 alias).
        req_record = next(
            r for r in cal.regrade_records if r.grader_name == "required_evidence"
        )
        assert req_record.calibrated_passed is True
        assert req_record.delta == 1  # fixed
        assert req_record.failure_class == "FALSE GRADER FAILURE"

    def test_regrade_preserves_true_model_error(self):
        """
        If the model said 'wave-18' (a hallucination), re-grading should still fail.
        """
        case = make_case(
            context_entities=FIXTURE_CONTEXT_ENTITIES,
        )
        result = make_result(response="wave-18 is the primary bottleneck, not wave-17.")
        original_graders = self._make_original_grader_results(
            [
                (
                    "schema_validity",
                    True,
                    "No expected_schema defined — schema check skipped.",
                ),
                (
                    "hallucination",
                    False,
                    "Response references 1 entity ID(s) not in context.",
                ),
                (
                    "capability_match",
                    True,
                    "No expected_capability defined — capability check skipped.",
                ),
                (
                    "target_match",
                    True,
                    "No expected_target defined — target check skipped.",
                ),
                (
                    "required_evidence",
                    True,
                    "No required_facts defined — evidence check skipped.",
                ),
                (
                    "forbidden_claims",
                    True,
                    "No forbidden_claims defined — forbidden claim check skipped.",
                ),
            ]
        )
        cal = regrade_result(case, result, original_graders)
        hall_record = next(
            r for r in cal.regrade_records if r.grader_name == "hallucination"
        )
        assert hall_record.calibrated_passed is False  # wave-18 still fails
        assert hall_record.failure_class == "TRUE MODEL ERROR"

    def test_regrade_verdict_acceptable_when_critical_pass(self):
        """Model with all critical graders passing gets verdict ACCEPTABLE."""
        case = make_case(
            context_entities=FIXTURE_CONTEXT_ENTITIES,
            expected_target="wave-17",
        )
        result = make_result(
            response="Wave 17 is at risk. The workers are underallocated."
        )
        original_graders = self._make_original_grader_results(
            [
                (
                    "schema_validity",
                    True,
                    "No expected_schema defined — schema check skipped.",
                ),
                ("hallucination", True, "No entity IDs outside context detected."),
                (
                    "capability_match",
                    True,
                    "No expected_capability defined — capability check skipped.",
                ),
                ("target_match", True, "Response references expected target: wave-17"),
                (
                    "required_evidence",
                    True,
                    "No required_facts defined — evidence check skipped.",
                ),
                (
                    "forbidden_claims",
                    True,
                    "No forbidden_claims defined — forbidden claim check skipped.",
                ),
            ]
        )
        cal = regrade_result(case, result, original_graders)
        assert cal.evaluation_verdict == "ACCEPTABLE"


# ══════════════════════════════════════════════════════════════════════════════
# Part 8 — Latency sample classification (§22–§24)
# ══════════════════════════════════════════════════════════════════════════════


class TestLatencySample:
    """Latency samples must classify clean vs contaminated correctly."""

    def _make_sample(
        self,
        total_ms: float = 1500.0,
        fallback_used: bool = False,
        error: str | None = None,
        warmup: bool = False,
        run_index: int = 1,
        output_tokens: int | None = 50,
    ) -> LatencySample:
        return LatencySample(
            sample_id=f"sample-{run_index}",
            case_id="wave17-labor-risk-v1",
            model_id="nvidia/nemotron-3-super-120b-a12b",
            requested_model="nvidia/nemotron-3-super-120b-a12b",
            actual_model="nvidia/nemotron-3-super-120b-a12b",
            deployment="nvidia_hosted",
            provider="nvidia-nim",
            routing_ms=0.01,
            inference_ms=total_ms - 0.01,
            total_ms=total_ms,
            input_tokens=100,
            output_tokens=output_tokens,
            fallback_used=fallback_used,
            retry_count=0,
            error=error,
            warmup=warmup,
            run_index=run_index,
        )

    def test_clean_sample(self):
        s = self._make_sample()
        assert s.clean() is True

    def test_fallback_contaminates(self):
        """Fallback samples must be excluded from clean latency comparison (§22)."""
        s = self._make_sample(fallback_used=True)
        assert s.clean() is False

    def test_error_contaminates(self):
        s = self._make_sample(error="Timeout")
        assert s.clean() is False

    def test_warmup_excluded_from_timing(self):
        """Warm-up calls are excluded from summary statistics."""
        s = self._make_sample(warmup=True, run_index=0)
        assert s.warmup is True

    def test_tokens_per_sec_computed(self):
        s = self._make_sample(total_ms=2000.0, output_tokens=100)
        # 100 tokens / 2s ≈ 50 tok/s
        assert s.tokens_per_sec == pytest.approx(50.0, abs=5.0)

    def test_tokens_per_sec_none_when_no_tokens(self):
        s = self._make_sample(output_tokens=None)
        assert s.tokens_per_sec is None

    def test_to_dict_includes_clean_field(self):
        s = self._make_sample()
        d = s.to_dict()
        assert d["clean"] is True
        assert "fallback_used" in d
        assert "warmup" in d


class TestComputeLatencyStats:
    """compute_latency_stats produces correct per-§24 statistics."""

    def _make_samples(self, latencies: list[float]) -> list[LatencySample]:
        return [
            LatencySample(
                sample_id=f"s{i}",
                case_id="test",
                model_id="model",
                requested_model="model",
                actual_model="model",
                deployment="nvidia_hosted",
                provider="nvidia-nim",
                routing_ms=0.01,
                inference_ms=ms - 0.01,
                total_ms=ms,
                input_tokens=100,
                output_tokens=50,
                fallback_used=False,
                retry_count=0,
                error=None,
                warmup=(i == 0),
                run_index=i,
            )
            for i, ms in enumerate(latencies)
        ]

    def test_warmup_excluded_from_stats(self):
        """First sample (warmup=True) must not affect median."""
        # warmup=48570ms, then 5 clean samples at ~1500ms
        samples = self._make_samples([48570.0, 1400.0, 1500.0, 1600.0, 1450.0, 1520.0])
        stats = compute_latency_stats(samples)
        assert stats["n"] == 5  # warmup excluded
        assert stats["median_ms"] < 2000.0  # not contaminated by 48570ms warmup

    def test_fallback_excluded_from_clean_count(self):
        samples = self._make_samples([1000.0, 1200.0, 1100.0])
        # Mark first non-warmup as fallback
        samples[1].fallback_used = True
        stats = compute_latency_stats(samples)
        assert stats["n"] == 1  # warmup=0, fallback=1, clean=1 (samples[2])
        assert stats["fallback_count"] == 1

    def test_empty_samples_returns_null_stats(self):
        stats = compute_latency_stats([])
        assert stats["n"] == 0
        assert stats["median_ms"] is None

    def test_min_max_correct(self):
        samples = self._make_samples([0.0, 1000.0, 2000.0, 3000.0])  # 0=warmup
        stats = compute_latency_stats(samples)
        assert stats["min_ms"] == pytest.approx(1000.0, abs=1.0)
        assert stats["max_ms"] == pytest.approx(3000.0, abs=1.0)

    def test_p95_unavailable_when_n_small(self):
        samples = self._make_samples([0.0] + [1000.0] * 5)  # warmup + 5 clean
        stats = compute_latency_stats(samples)
        assert stats["p95_ms"] is None  # N=5 < 20 required


# ══════════════════════════════════════════════════════════════════════════════
# Part 9 — Policy eligibility labels (§4, §27)
# ══════════════════════════════════════════════════════════════════════════════


class TestPolicyLabel:
    """policy_label must correctly classify Nano eligibility."""

    def test_low_risk_low_reasoning_eligible(self):
        assert policy_label("low", "low") == "POLICY ELIGIBLE"

    def test_low_risk_medium_reasoning_eligible(self):
        assert policy_label("low", "medium") == "POLICY ELIGIBLE"

    def test_medium_risk_medium_reasoning_eligible(self):
        assert policy_label("medium", "medium") == "POLICY ELIGIBLE"

    def test_high_reasoning_not_eligible(self):
        """HIGH reasoning → only super/ultra eligible."""
        label = policy_label("low", "high")
        assert label == "RESEARCH ONLY — NOT PRODUCTION ELIGIBLE"

    def test_high_risk_not_eligible(self):
        """HIGH risk → only super/ultra eligible."""
        label = policy_label("high", "medium")
        assert label == "RESEARCH ONLY — NOT PRODUCTION ELIGIBLE"

    def test_critical_risk_not_eligible(self):
        """CRITICAL risk → only super/ultra eligible."""
        label = policy_label("critical", "low")
        assert label == "RESEARCH ONLY — NOT PRODUCTION ELIGIBLE"

    def test_18c_wave17_case_not_eligible(self):
        """wave17-labor-risk-v1: risk=high, reasoning=high → RESEARCH ONLY."""
        label = policy_label("high", "high")
        assert label == "RESEARCH ONLY — NOT PRODUCTION ELIGIBLE"

    def test_18d_evidence_ask_labor_eligible(self):
        """evidence-ask-labor-v1: risk=low, reasoning=medium → POLICY ELIGIBLE."""
        assert policy_label("low", "medium") == "POLICY ELIGIBLE"

    def test_18d_healthy_baseline_eligible(self):
        """healthy-baseline-v1: risk=low, reasoning=medium → POLICY ELIGIBLE."""
        assert policy_label("low", "medium") == "POLICY ELIGIBLE"


# ══════════════════════════════════════════════════════════════════════════════
# Part 10 — 18D fixture registration (§6, §7)
# ══════════════════════════════════════════════════════════════════════════════


class TestFixture18DRegistration:
    """18D fixture cases must be registered and have correct metadata."""

    def test_18b_cases_still_present(self):
        ids = {c.case_id for c in ALL_FIXTURE_CASES}
        assert "wave17-labor-risk-v1" in ids
        assert "equipment-failure-v1" in ids
        assert "healthy-baseline-v1" in ids

    def test_18d_cases_registered(self):
        ids = {c.case_id for c in ALL_18D_FIXTURE_CASES}
        assert "evidence-ask-labor-v1" in ids
        assert "analyze-action-v1" in ids
        assert "comparative-reasoning-v1" in ids

    def test_all_known_cases_combined(self):
        # 18B (3) + 18D (3) + 18E (3) = 9
        assert len(ALL_KNOWN_CASES) >= 6

    def test_18d_cases_use_same_context_entities(self):
        """Fixed-context invariant: same context_entities as 18B (§5)."""
        for case in ALL_18D_FIXTURE_CASES:
            assert set(case.context_entities) == set(
                FIXTURE_CONTEXT_ENTITIES
            ), f"{case.case_id} uses different context_entities"

    def test_18d_cases_nano_eligible(self):
        """18D low/medium cases are POLICY ELIGIBLE for Nano."""
        for case in ALL_18D_FIXTURE_CASES:
            label = policy_label(case.risk_level, case.reasoning_level)
            assert label == "POLICY ELIGIBLE", (
                f"{case.case_id}: risk={case.risk_level}, reasoning={case.reasoning_level} "
                f"should be POLICY ELIGIBLE but got {label}"
            )

    def test_evidence_ask_labor_case_b(self):
        assert evidence_ask_labor.task_family == TaskFamily.ASK
        assert evidence_ask_labor.risk_level == "low"
        assert evidence_ask_labor.reasoning_level == "medium"
        assert evidence_ask_labor.expected_capability == "labor_reallocation"

    def test_analyze_action_case_c(self):
        assert analyze_action.task_family == TaskFamily.ANALYZE
        assert analyze_action.risk_level == "medium"
        assert analyze_action.reasoning_level == "medium"

    def test_comparative_reasoning_case_d(self):
        assert comparative_reasoning.task_family == TaskFamily.ANALYZE
        assert comparative_reasoning.risk_level == "low"
        assert "conveyor" in comparative_reasoning.required_facts

    def test_18c_high_risk_cases_not_eligible(self):
        """Confirm 18B high-risk cases are RESEARCH ONLY for Nano."""
        not_eligible = [wave17_labor_risk, equipment_failure]
        for case in not_eligible:
            label = policy_label(case.risk_level, case.reasoning_level)
            assert (
                label == "RESEARCH ONLY — NOT PRODUCTION ELIGIBLE"
            ), f"{case.case_id} should be NOT PRODUCTION ELIGIBLE"


# ══════════════════════════════════════════════════════════════════════════════
# Part 11 — Evaluation repeatability metadata (§33)
# ══════════════════════════════════════════════════════════════════════════════


class TestEvaluationRepeatability:
    """Re-grading saved results must be deterministic."""

    def test_regrade_is_deterministic(self):
        """Running regrade_result twice on the same input must produce same output."""
        case = make_case(
            required_facts=["wave-17"],
            context_entities=FIXTURE_CONTEXT_ENTITIES,
        )
        result = make_result(response="Wave 17 is at risk.")
        original_graders = [
            {
                "name": "schema_validity",
                "passed": True,
                "reason": "No expected_schema defined — schema check skipped.",
                "evidence": [],
            },
            {
                "name": "hallucination",
                "passed": True,
                "reason": "No entity IDs outside context detected.",
                "evidence": [],
            },
            {
                "name": "capability_match",
                "passed": True,
                "reason": "No expected_capability defined — capability check skipped.",
                "evidence": [],
            },
            {
                "name": "target_match",
                "passed": True,
                "reason": "No expected_target defined — target check skipped.",
                "evidence": [],
            },
            {
                "name": "required_evidence",
                "passed": False,
                "reason": "0/1 required facts found. Missing: ['wave-17']",
                "evidence": [],
            },
            {
                "name": "forbidden_claims",
                "passed": True,
                "reason": "No forbidden_claims defined — forbidden claim check skipped.",
                "evidence": [],
            },
        ]

        cal1 = regrade_result(case, result, original_graders)
        cal2 = regrade_result(case, result, original_graders)

        assert cal1.calibrated_score == cal2.calibrated_score
        assert cal1.evaluation_verdict == cal2.evaluation_verdict
        for r1, r2 in zip(cal1.regrade_records, cal2.regrade_records):
            assert r1.calibrated_passed == r2.calibrated_passed
            assert r1.delta == r2.delta
