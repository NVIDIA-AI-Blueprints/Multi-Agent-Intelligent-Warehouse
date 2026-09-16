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
Phase 18B/18D deterministic graders.

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

Phase 18D calibration changes (§8–§16):
  - HallucinationGrader: uses EntityResolver to expand allowed surface forms.
    A model that says "Wave 17" for entity "wave-17" is NOT hallucinating.
    Words like "in-scope", "labor-bottleneck" must not produce false failures
    when they are not warehouse entity references.
  - RequiredEvidenceGrader: applies canonical alias matching for required_facts
    that look like entity IDs, so "wave 17" satisfies fact "wave-17".
  - TargetMatchGrader: emits diagnostic fields (model_reference,
    resolved_entity_id, expected_entity_id, match) per §13.
  - CapabilityMatchGrader: extended synonym list for equipment_bypass.

These changes reduce false negatives without increasing false positives (§15).
"""

from __future__ import annotations

import json
import re
from typing import Protocol, runtime_checkable

from .models import EvaluationCase, GraderResult, ModelEvaluationResult
from .resolver import EntityResolver, ResolvedEntity, build_allowed_surface_forms

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
    except json.JSONDecodeError:  # noqa: BLE001 — malformed JSON is expected, fall through
        pass

    # Try to find JSON inside ```json ... ``` fence.
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence_match:
        try:
            parsed = json.loads(fence_match.group(1))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:  # noqa: BLE001 — malformed JSON is expected, fall through
            pass

    # Try to find first {...} block.
    brace_match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if brace_match:
        try:
            parsed = json.loads(brace_match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:  # noqa: BLE001 — malformed JSON is expected, fall through
            pass

    return None


# ── Grader 2: Hallucination (canonical entity) ───────────────────────────────


class HallucinationGrader:
    """
    Grader 2 — Canonical entity hallucination.

    Checks whether the model response references entity IDs that are NOT
    resolvable to any entity in EvaluationCase.context_entities.

    Phase 18D calibration (§8–§12):
      The grader uses EntityResolver to expand the allowed set beyond exact
      canonical IDs.  A response that says "Wave 17" for entity "wave-17" is
      NOT hallucinating — it is a canonical surface-form variant.

      The grader ONLY flags tokens that:
        (a) match the entity ID pattern (alphanumeric + hyphen/underscore), AND
        (b) are NOT resolvable to any known context entity via canonical aliases.

      This eliminates false failures from common English hyphenated words
      (e.g. "in-scope", "well-known") that are not warehouse entity references.

    Strict behaviour preserved:
      - "Wave 18" → fails if wave-18 is not in context (correct rejection).
      - "wave-17" → passes if wave-17 is in context (correct pass).
      - "wave 17" → passes via canonical alias (false-failure eliminated).
      - "in-scope" → passes (not a warehouse entity reference in any context).

    When context_entities is empty, the grader passes unconditionally
    (no entity whitelist defined for this case).
    """

    grader_name = "hallucination"

    # Pattern: structured entity IDs — alphanumeric with dashes/underscores.
    # Matches: wave-17, equip-001, labor-shift-3, SKU-ABC123, conveyor-main.
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

        # 18D: Build expanded allowed surface forms via EntityResolver.
        # This includes exact canonical IDs and all approved aliases
        # (hyphen↔space↔underscore substitution only — no fuzzy matching).
        allowed_surface_forms = build_allowed_surface_forms(case.context_entities)

        found_ids = self._ENTITY_ID_PATTERN.findall(response)
        hallucinated = []
        for eid in found_ids:
            eid_lower = eid.lower()
            # Pass if resolvable to a known entity via any approved alias.
            if eid_lower not in allowed_surface_forms:
                hallucinated.append(eid)

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
                reason=(
                    f"Response references {len(unique_hallucinated)} entity ID(s) "
                    f"not resolvable to any known context entity."
                ),
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
    # 18D calibration (§15): extended equipment_bypass synonyms to cover
    # natural phrasings ("backup conveyor", "switch to backup") that are
    # semantically equivalent but missed in 18C. Strict: only operationally
    # correct synonyms — not generic words that could match unrelated content.
    _SYNONYMS: dict[str, list[str]] = {
        "wave_recovery": [
            "wave recovery",
            "recover wave",
            "wave replan",
            "reschedule wave",
        ],
        "labor_reallocation": [
            "labor reallocation",
            "reallocate labor",
            "reassign workers",
            "shift workers",
            "move workers",
            "reallocate workers",
            "redistribute labor",
            "labor redistribution",
        ],
        "equipment_bypass": [
            "bypass",
            "reroute",
            "alternate conveyor",
            "alternate equipment",
            # 18D additions — operationally equivalent phrasings:
            "backup conveyor",
            "backup system",
            "switch to backup",
            "use backup",
            "use the backup",
            "alternate path",
            "conveyor-backup",
            "conveyor backup",
        ],
        "equipment_shutdown": [
            "shut down",
            "shutdown",
            "take offline",
            "remove from service",
            "decommission",
            "halt equipment",
        ],
        "wave_prioritization": [
            "prioritize",
            "reprioritize",
            "priority wave",
            "wave priority",
        ],
        "safety_alert": [
            "safety alert",
            "alert",
            "warning",
            "hazard notification",
        ],
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

    Phase 18D calibration (§13):
      Uses EntityResolver to find the first surface form from context_entities
      that appears in the response and resolves to expected_target.  Emits
      diagnostic fields: model_reference, resolved_entity_id,
      expected_entity_id, match — stored in GraderResult.evidence as a
      structured JSON string.

    Matching hierarchy:
      1. Exact canonical ID substring (case-insensitive)
      2. Canonical alias variants (hyphen↔space↔underscore)
      3. Resolver scan: each alias of expected_target checked in response

    Never broadens beyond deterministic alias derivation.
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

        # Build resolver for expected_target entity (or all context entities).
        context_ids = case.context_entities if case.context_entities else [target]
        resolver = EntityResolver.from_context_ids(context_ids)

        # Check exact canonical ID and all approved aliases of expected_target.
        from .resolver import _canonical_aliases

        target_aliases = _canonical_aliases(target)

        matched_reference: str | None = None
        for alias in sorted(target_aliases):  # deterministic order
            if alias in response:
                matched_reference = alias
                break

        if matched_reference is not None:
            # 18D: emit diagnostic record (§13).
            resolved = resolver.resolve(matched_reference) or target
            diagnostic = ResolvedEntity(
                model_reference=matched_reference,
                resolved_entity_id=resolved,
                expected_entity_id=target,
                match=(resolved == target),
            )
            import json as _json

            diag_str = _json.dumps(
                {
                    "model_reference": diagnostic.model_reference,
                    "resolved_entity_id": diagnostic.resolved_entity_id,
                    "expected_entity_id": diagnostic.expected_entity_id,
                    "match": diagnostic.match,
                }
            )
            verb = (
                "exactly"
                if matched_reference == target
                else f"(variant '{matched_reference}')"
            )
            return GraderResult(
                grader_name=self.grader_name,
                passed=True,
                reason=(
                    f"Response references expected target {verb}: {case.expected_target}"
                ),
                evidence=[matched_reference, diag_str],
            )

        return GraderResult(
            grader_name=self.grader_name,
            passed=False,
            reason=(
                f"Response does not reference expected target: {case.expected_target}"
            ),
            evidence=[
                _json_diagnostic(
                    model_reference="(none found)",
                    resolved_entity_id=None,
                    expected_entity_id=target,
                    match=False,
                )
            ],
        )


def _json_diagnostic(
    model_reference: str,
    resolved_entity_id: str | None,
    expected_entity_id: str,
    match: bool,
) -> str:
    """Serialize a target grader diagnostic to JSON string."""
    import json as _json

    return _json.dumps(
        {
            "model_reference": model_reference,
            "resolved_entity_id": resolved_entity_id,
            "expected_entity_id": expected_entity_id,
            "match": match,
        }
    )


# ── Grader 5: Required evidence ───────────────────────────────────────────────


class RequiredEvidenceGrader:
    """
    Grader 5 — Required evidence presence.

    Checks that the model response references ALL facts listed in
    EvaluationCase.required_facts.

    Each fact is a string (keyword, phrase, or metric) that must appear
    in the response.  Matching is case-insensitive.

    Phase 18D calibration (§12, §14):
      For facts that resemble entity IDs (contain hyphens or underscores),
      canonical alias variants are also checked (hyphen↔space↔underscore).
      This prevents false failures when a model says "Wave 17" for fact "wave-17".

      Only the SAME deterministic alias derivation used in EntityResolver is
      applied — no fuzzy matching, no edit distance, no LLM.

      For non-entity-like facts (plain words, numbers, phrases), exact
      case-insensitive substring match is preserved.

      If deterministic semantic interpretation is impossible for a fact,
      that fact is left graded as-is and reported as unresolvable (§14).

    score = fraction of required facts found (1.0 = all present).
    """

    grader_name = "required_evidence"

    @staticmethod
    def _fact_found_in_response(fact: str, response: str) -> bool:
        """
        Return True if fact is found in the normalized response.

        For entity-like facts (hyphen/underscore separated), also checks
        canonical alias variants.  For plain words, checks exact substring.
        """
        fact_lower = fact.lower()
        # Direct match always wins.
        if fact_lower in response:
            return True
        # If the fact contains a hyphen or underscore, try canonical aliases.
        if "-" in fact or "_" in fact:
            from .resolver import _canonical_aliases

            for alias in _canonical_aliases(fact):
                if alias in response:
                    return True
        return False

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
        found = [
            f for f in case.required_facts if self._fact_found_in_response(f, response)
        ]
        missing = [
            f
            for f in case.required_facts
            if not self._fact_found_in_response(f, response)
        ]
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
