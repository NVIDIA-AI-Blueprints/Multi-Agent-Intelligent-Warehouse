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
Phase 18B deterministic graders.

Six composable graders that evaluate ModelEvaluationResult against an
EvaluationCase deterministically (no LLM judge required in 18B).

Grader contract (EvaluationGrader Protocol):
    def grade(case: EvaluationCase, result: ModelEvaluationResult) -> GraderResult

Graders:
    1. SchemaValidityGrader      — did output satisfy expected JSON structure?
    2. HallucinationGrader       — did response reference entity IDs not in context?
    3. CapabilityMatchGrader     — does recommendation match expected_capability?
    4. TargetMatchGrader         — does response target the correct canonical entity?
    5. RequiredEvidenceGrader    — does response reference all required_facts?
    6. ForbiddenClaimsGrader     — does response avoid all forbidden_claims?

All graders are deterministic: same input → same output, no randomness, no I/O.
"""

from __future__ import annotations

import json
import re
from typing import Protocol, runtime_checkable

from .models import EvaluationCase, GraderResult, ModelEvaluationResult


# ── Protocol ──────────────────────────────────────────────────────────────────


@runtime_checkable
class EvaluationGrader(Protocol):
    """
    Typed protocol for deterministic evaluation graders.

    Graders MUST be deterministic.  They MUST NOT:
      - call any model or LLM;
      - access network or disk;
      - produce non-deterministic results.

    Implement this protocol to add a custom grader.
    """

    def grade(
        self,
        case: EvaluationCase,
        result: ModelEvaluationResult,
    ) -> GraderResult:
        """
        Grade one model result against the evaluation case.

        Args:
            case:   The evaluation case specifying expectations.
            result: The model's response and metadata.

        Returns:
            GraderResult with grader_name, passed, score, reason, evidence.
        """
        ...


# ── Helpers ───────────────────────────────────────────────────────────────────


def _response_text(result: ModelEvaluationResult) -> str:
    """Return response text or empty string if error."""
    return result.response or ""


def _normalize(text: str) -> str:
    """Lowercase and collapse whitespace for fuzzy matching."""
    return re.sub(r"\s+", " ", text.lower()).strip()


# ── Grader 1: Schema validity ─────────────────────────────────────────────────


class SchemaValidityGrader:
    """
    Grader 1 — Schema validity.

    Checks whether the model response satisfies the expected JSON schema
    specified in EvaluationCase.expected_schema.

    When expected_schema is None, the grader passes unconditionally
    (schema validation not applicable for this case).

    Uses minimal JSON Schema validation (type + required fields only).
    Does not require jsonschema library — implements a subset inline.
    """

    grader_name = "schema_validity"

    def grade(
        self,
        case: EvaluationCase,
        result: ModelEvaluationResult,
    ) -> GraderResult:
        if case.expected_schema is None:
            return GraderResult(
                grader_name=self.grader_name,
                passed=True,
                reason="No expected_schema defined — schema check skipped.",
            )

        response = _response_text(result)
        if not response:
            return GraderResult(
                grader_name=self.grader_name,
                passed=False,
                reason="Response is empty — cannot validate schema.",
            )

        # Try to extract JSON from response (model may wrap in markdown).
        parsed = _extract_json(response)
        if parsed is None:
            return GraderResult(
                grader_name=self.grader_name,
                passed=False,
                reason="Response does not contain valid JSON.",
                evidence=[response[:200]],
            )

        # Check required fields.
        required = case.expected_schema.get("required", [])
        missing = [f for f in required if f not in parsed]
        if missing:
            return GraderResult(
                grader_name=self.grader_name,
                passed=False,
                reason=f"Missing required fields: {missing}",
                evidence=[str(list(parsed.keys()))],
            )

        return GraderResult(
            grader_name=self.grader_name,
            passed=True,
            reason=f"All required fields present: {required or '(none)'}",
        )


def _extract_json(text: str) -> dict | None:
    """Extract first JSON object from text, handling markdown code fences."""
    # Try full text first.
    stripped = text.strip()
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Try to find JSON inside ```json ... ``` fence.
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        try:
            parsed = json.loads(fence_match.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    # Try to find first {...} block.
    brace_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if brace_match:
        try:
            parsed = json.loads(brace_match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

    return None


# ── Grader 2: Hallucination (canonical entity) ───────────────────────────────


class HallucinationGrader:
    """
    Grader 2 — Canonical entity hallucination.

    Checks whether the model response references entity IDs or names that
    are NOT present in EvaluationCase.context_entities.

    Only checks for entity IDs (structured references) — free-text phrases
    are not hallucination-checked by this deterministic grader (that requires
    an LLM judge, deferred to 18C+).

    Entity IDs that appear in the response but NOT in context_entities are
    flagged as potential hallucinations.

    When context_entities is empty, the grader passes unconditionally
    (no entity whitelist defined for this case).
    """

    grader_name = "hallucination"

    # Pattern: entity IDs are typically alphanumeric with dashes/underscores.
    # Matches patterns like: wave-17, equip-001, labor-shift-3, SKU-ABC123.
    _ENTITY_ID_PATTERN = re.compile(
        r"\b([a-zA-Z][a-zA-Z0-9]*[-_][a-zA-Z0-9][-a-zA-Z0-9]*)\b"
    )

    def grade(
        self,
        case: EvaluationCase,
        result: ModelEvaluationResult,
    ) -> GraderResult:
        if not case.context_entities:
            return GraderResult(
                grader_name=self.grader_name,
                passed=True,
                reason="No context_entities defined — hallucination check skipped.",
            )

        response = _response_text(result)
        if not response:
            return GraderResult(
                grader_name=self.grader_name,
                passed=True,
                reason="Empty response — no entity IDs to check.",
            )

        allowed = {e.lower() for e in case.context_entities}
        found_ids = self._ENTITY_ID_PATTERN.findall(response)
        hallucinated = [
            eid for eid in found_ids if eid.lower() not in allowed
        ]

        if hallucinated:
            # Deduplicate while preserving order.
            seen: set[str] = set()
            unique_hallucinated = []
            for h in hallucinated:
                if h.lower() not in seen:
                    seen.add(h.lower())
                    unique_hallucinated.append(h)

            return GraderResult(
                grader_name=self.grader_name,
                passed=False,
                reason=f"Response references {len(unique_hallucinated)} entity ID(s) not in context.",
                evidence=unique_hallucinated[:10],  # cap evidence list
            )

        return GraderResult(
            grader_name=self.grader_name,
            passed=True,
            reason="No entity IDs outside context detected.",
        )


# ── Grader 3: Capability match ────────────────────────────────────────────────


class CapabilityMatchGrader:
    """
    Grader 3 — Capability match.

    When EvaluationCase.expected_capability is set, checks that the model's
    response mentions a recommendation aligned with the expected capability
    (e.g. "wave_recovery", "labor_reallocation", "equipment_bypass").

    Matching is keyword-based (the capability slug appears in the response,
    or a synonym mapping matches).  LLM-based semantic match is 18C+.
    """

    grader_name = "capability_match"

    # Synonym expansions: capability slug → additional keywords.
    _SYNONYMS: dict[str, list[str]] = {
        "wave_recovery": ["wave recovery", "recover wave", "wave replan", "reschedule wave"],
        "labor_reallocation": ["labor reallocation", "reallocate labor", "reassign workers",
                               "shift workers", "move workers"],
        "equipment_bypass": ["bypass", "reroute", "alternate conveyor", "alternate equipment"],
        "equipment_shutdown": ["shut down", "shutdown", "take offline", "remove from service"],
        "wave_prioritization": ["prioritize", "reprioritize", "priority wave"],
        "safety_alert": ["safety alert", "alert", "warning", "hazard notification"],
    }

    def grade(
        self,
        case: EvaluationCase,
        result: ModelEvaluationResult,
    ) -> GraderResult:
        if case.expected_capability is None:
            return GraderResult(
                grader_name=self.grader_name,
                passed=True,
                reason="No expected_capability defined — capability check skipped.",
            )

        response = _normalize(_response_text(result))
        capability = case.expected_capability.lower()

        # Check direct slug presence.
        if capability.replace("_", " ") in response or capability in response:
            return GraderResult(
                grader_name=self.grader_name,
                passed=True,
                reason=f"Response mentions expected capability: {case.expected_capability}",
            )

        # Check synonyms.
        synonyms = self._SYNONYMS.get(case.expected_capability, [])
        for synonym in synonyms:
            if synonym.lower() in response:
                return GraderResult(
                    grader_name=self.grader_name,
                    passed=True,
                    score=0.8,  # synonym match is slightly weaker than direct
                    reason=f"Response mentions synonym for {case.expected_capability}: '{synonym}'",
                    evidence=[synonym],
                )

        return GraderResult(
            grader_name=self.grader_name,
            passed=False,
            reason=(
                f"Response does not mention expected capability "
                f"'{case.expected_capability}' or its synonyms."
            ),
        )


# ── Grader 4: Target match ────────────────────────────────────────────────────


class TargetMatchGrader:
    """
    Grader 4 — Target match.

    When EvaluationCase.expected_target is set, checks that the model's
    response references the expected target entity (by ID or label).

    Matching is case-insensitive substring search.
    """

    grader_name = "target_match"

    def grade(
        self,
        case: EvaluationCase,
        result: ModelEvaluationResult,
    ) -> GraderResult:
        if case.expected_target is None:
            return GraderResult(
                grader_name=self.grader_name,
                passed=True,
                reason="No expected_target defined — target check skipped.",
            )

        response = _normalize(_response_text(result))
        target = case.expected_target.lower()

        if target in response:
            return GraderResult(
                grader_name=self.grader_name,
                passed=True,
                reason=f"Response references expected target: {case.expected_target}",
            )

        # Also try underscore/hyphen variants.
        variants = [
            target.replace("-", " "),
            target.replace("_", " "),
            target.replace("-", "_"),
        ]
        for variant in variants:
            if variant in response:
                return GraderResult(
                    grader_name=self.grader_name,
                    passed=True,
                    reason=(
                        f"Response references expected target "
                        f"(variant '{variant}'): {case.expected_target}"
                    ),
                    evidence=[variant],
                )

        return GraderResult(
            grader_name=self.grader_name,
            passed=False,
            reason=(
                f"Response does not reference expected target: {case.expected_target}"
            ),
        )


# ── Grader 5: Required evidence ───────────────────────────────────────────────


class RequiredEvidenceGrader:
    """
    Grader 5 — Required evidence presence.

    Checks that the model response references ALL facts listed in
    EvaluationCase.required_facts.

    Each fact is a string (keyword, phrase, or metric) that must appear
    in the response.  Matching is case-insensitive.

    score = fraction of required facts found (1.0 = all present).
    """

    grader_name = "required_evidence"

    def grade(
        self,
        case: EvaluationCase,
        result: ModelEvaluationResult,
    ) -> GraderResult:
        if not case.required_facts:
            return GraderResult(
                grader_name=self.grader_name,
                passed=True,
                reason="No required_facts defined — evidence check skipped.",
            )

        response = _normalize(_response_text(result))
        found = [f for f in case.required_facts if f.lower() in response]
        missing = [f for f in case.required_facts if f.lower() not in response]
        score = len(found) / len(case.required_facts)

        if missing:
            return GraderResult(
                grader_name=self.grader_name,
                passed=False,
                score=score,
                reason=(
                    f"{len(found)}/{len(case.required_facts)} required facts found. "
                    f"Missing: {missing}"
                ),
                evidence=found,
            )

        return GraderResult(
            grader_name=self.grader_name,
            passed=True,
            score=1.0,
            reason=f"All {len(case.required_facts)} required facts found.",
            evidence=found,
        )


# ── Grader 6: Forbidden claims ────────────────────────────────────────────────


class ForbiddenClaimsGrader:
    """
    Grader 6 — Forbidden unsupported claims.

    Checks that the model response does NOT assert any facts listed in
    EvaluationCase.forbidden_claims.

    Forbidden claims are strings that the model must NOT mention because
    they are absent from the supplied context (potential hallucination or
    out-of-scope assertion).

    Matching is case-insensitive substring search.
    """

    grader_name = "forbidden_claims"

    def grade(
        self,
        case: EvaluationCase,
        result: ModelEvaluationResult,
    ) -> GraderResult:
        if not case.forbidden_claims:
            return GraderResult(
                grader_name=self.grader_name,
                passed=True,
                reason="No forbidden_claims defined — forbidden claim check skipped.",
            )

        response = _normalize(_response_text(result))
        violations = [
            claim for claim in case.forbidden_claims if claim.lower() in response
        ]

        if violations:
            return GraderResult(
                grader_name=self.grader_name,
                passed=False,
                reason=(
                    f"Response asserts {len(violations)} forbidden claim(s) "
                    f"absent from supplied context."
                ),
                evidence=violations,
            )

        return GraderResult(
            grader_name=self.grader_name,
            passed=True,
            reason=f"No forbidden claims detected ({len(case.forbidden_claims)} checked).",
        )


# ── Default grader suite ──────────────────────────────────────────────────────


def default_graders() -> list[EvaluationGrader]:
    """Return the full 18B deterministic grader suite in evaluation order."""
    return [
        SchemaValidityGrader(),
        HallucinationGrader(),
        CapabilityMatchGrader(),
        TargetMatchGrader(),
        RequiredEvidenceGrader(),
        ForbiddenClaimsGrader(),
    ]


def run_graders(
    case: EvaluationCase,
    result: ModelEvaluationResult,
    graders: list[EvaluationGrader] | None = None,
) -> list[GraderResult]:
    """
    Run all graders for one (case, result) pair and return their results.

    Args:
        case:    The evaluation case.
        result:  The model evaluation result to grade.
        graders: Graders to run; defaults to default_graders().

    Returns:
        List of GraderResult, one per grader, in the order provided.
    """
    if graders is None:
        graders = default_graders()
    return [g.grade(case, result) for g in graders]
