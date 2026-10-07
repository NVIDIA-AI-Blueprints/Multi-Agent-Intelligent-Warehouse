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
Stage 4/5: Large LLM Judge — document quality classification.

v2.0.1 (audit P1-05):
  * Every call goes through the canonical ModelGateway
    (``model_gateway_adapter.generate_for_document``, ``Modality.TEXT``,
    ``ReasoningLevel.HIGH``); PolicyFilter selects an approved Nemotron 3 / 3.5
    model. No provider URL, API key or model id lives here.
  * There is no mock evaluation. Missing credentials, provider failure,
    no eligible model, or a malformed reply raise
    ``DocumentInferenceUnavailable`` — a failure can never become ``APPROVE``.

Decision semantics: ``JudgeEvaluation.decision`` (APPROVE / REJECT /
REVIEW_REQUIRED) is the *model's document-quality classification*
(``decision_kind = "model_quality_classification"``). It is NOT a MAIW
governance decision: it does not pass through DecisionEngine, creates no
ApprovalRecord, and authorises no warehouse action. Document-workflow approval
is a separate, human action (``POST /api/v1/document/approve/{id}``).
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
import os
import json
from datetime import datetime
from dataclasses import dataclass, field

from src.api.agents.document.model_gateway_adapter import (
    MALFORMED_RESPONSE,
    DocumentInferenceUnavailable,
    generate_for_document,
    parse_json_object,
    route_provenance,
)

logger = logging.getLogger(__name__)

#: The only values a judge classification may take.
VALID_JUDGE_DECISIONS = frozenset({"APPROVE", "REJECT", "REVIEW_REQUIRED"})

#: What ``JudgeEvaluation.decision`` means (see module docstring).
JUDGE_DECISION_KIND = "model_quality_classification"


@dataclass
class JudgeEvaluation:
    """
    A model's quality classification of extracted document data.

    ``decision`` is a model classification, not a governance approval.
    """

    overall_score: float
    decision: str
    completeness: Dict[str, Any]
    accuracy: Dict[str, Any]
    compliance: Dict[str, Any]
    quality: Dict[str, Any]
    issues_found: List[str]
    confidence: float
    reasoning: str
    decision_kind: str = JUDGE_DECISION_KIND
    judge_model: str = ""
    model_route: Dict[str, Any] = field(default_factory=dict)


class LargeLLMJudge:
    """
    Large LLM Judge — routed through the canonical ModelGateway.

    Evaluation Framework:
    1. Completeness Check (Score: 1-5)
    2. Accuracy Validation (Score: 1-5)
    3. Business Logic Compliance (Score: 1-5)
    4. Quality & Confidence (Score: 1-5)
    """

    def __init__(self):
        # Bound on the whole judge call. NEMOTRON_SUPER_TIMEOUT is kept for
        # operator compatibility; it no longer selects or addresses a model.
        _timeout_str = os.getenv("NEMOTRON_SUPER_TIMEOUT") or os.getenv(
            "LLAMA_70B_TIMEOUT"
        )
        if os.getenv("LLAMA_70B_TIMEOUT") and not os.getenv("NEMOTRON_SUPER_TIMEOUT"):
            import warnings

            warnings.warn(
                "LLAMA_70B_TIMEOUT is deprecated; use NEMOTRON_SUPER_TIMEOUT instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        self.timeout = int(_timeout_str or "120")

    async def initialize(self):
        """No provider probing: the ModelGateway owns provider connectivity."""
        return None

    async def evaluate_document(
        self,
        structured_data: Dict[str, Any],
        entities: Dict[str, Any],
        document_type: str,
    ) -> JudgeEvaluation:
        """
        Classify extracted document data through the ModelGateway.

        Raises ``DocumentInferenceUnavailable`` on any inference failure or a
        reply that is not a valid classification. Never returns a fabricated
        evaluation.
        """
        logger.info(f"Evaluating {document_type} document with Large LLM Judge")
        evaluation_prompt = self._create_evaluation_prompt(
            structured_data, entities, document_type
        )
        evaluation_result = await self._call_judge_api(evaluation_prompt)
        judge_evaluation = self._parse_judge_result(evaluation_result, document_type)
        logger.info(
            "Judge classification: decision=%s score=%s model=%s",
            judge_evaluation.decision,
            judge_evaluation.overall_score,
            judge_evaluation.judge_model,
        )
        return judge_evaluation

    def _create_evaluation_prompt(
        self,
        structured_data: Dict[str, Any],
        entities: Dict[str, Any],
        document_type: str,
    ) -> str:
        """Create comprehensive evaluation prompt for the judge."""

        prompt = f"""
        You are an expert document quality judge specializing in {document_type} evaluation.
        Please evaluate the following document data and provide a comprehensive assessment.
        
        DOCUMENT DATA:
        {json.dumps(structured_data, indent=2)}
        
        EXTRACTED ENTITIES:
        {json.dumps(entities, indent=2)}
        
        EVALUATION CRITERIA:
        
        1. COMPLETENESS CHECK (Score: 1-5)
        - Are all required fields extracted?
        - Is the line items count consistent with document?
        - Are critical data points present (PO#, dates, totals)?
        
        2. ACCURACY VALIDATION (Score: 1-5)
        - Are data types correct (numbers, dates)?
        - Does arithmetic validation pass (line totals = grand total)?
        - Is cross-field consistency maintained?
        
        3. BUSINESS LOGIC COMPLIANCE (Score: 1-5)
        - Are vendor codes valid?
        - Are quantities and prices reasonable?
        - Is address formatting proper?
        - Does date logic make sense?
        
        4. QUALITY & CONFIDENCE (Score: 1-5)
        - What is the OCR quality assessment?
        - How confident are the field extractions?
        - Are there any anomalies detected?
        
        Please provide your evaluation in the following JSON format:
        {{
            "overall_score": 4.2,
            "decision": "APPROVE|REJECT|REVIEW_REQUIRED",
            "completeness": {{
                "score": 5,
                "reasoning": "All required fields are present and complete",
                "missing_fields": [],
                "issues": []
            }},
            "accuracy": {{
                "score": 4,
                "reasoning": "Most calculations are correct, minor discrepancy in line 3",
                "calculation_errors": [],
                "data_type_issues": []
            }},
            "compliance": {{
                "score": 4,
                "reasoning": "Business logic is mostly compliant, vendor code format needs verification",
                "compliance_issues": [],
                "recommendations": []
            }},
            "quality": {{
                "score": 4,
                "reasoning": "High confidence extractions, OCR quality is good",
                "confidence_assessment": "high",
                "anomalies": []
            }},
            "issues_found": [],
            "confidence": 0.92,
            "reasoning": "Overall high-quality document with minor issues that can be easily resolved"
        }}
        """

        return prompt

    async def _call_judge_api(self, prompt: str) -> Dict[str, Any]:
        """One TEXT inference through the canonical ModelGateway."""
        from maiw_models import Modality, ReasoningLevel

        response = await generate_for_document(
            stage="validation",
            messages=[{"role": "user", "content": prompt}],
            modality=Modality.TEXT,
            reasoning=ReasoningLevel.HIGH,
            timeout_s=self.timeout,
        )
        parsed = parse_json_object(response.content, stage="validation")
        return {
            "content": parsed,
            "raw_response": response.content,
            "model_used": response.model_id,
            "model_route": await route_provenance(response),
        }

    def _parse_judge_result(
        self, result: Dict[str, Any], document_type: str
    ) -> JudgeEvaluation:
        """
        Validate the judge reply. A missing or unknown ``decision`` or a
        non-numeric score is a MALFORMED_RESPONSE — never guessed, never
        defaulted to APPROVE.
        """
        content = result.get("content")
        if not isinstance(content, dict):
            raise DocumentInferenceUnavailable(
                MALFORMED_RESPONSE,
                "judge reply is not an object",
                stage="validation",
                modality="text",
            )
        decision = str(content.get("decision", "")).strip().upper()
        if decision not in VALID_JUDGE_DECISIONS:
            raise DocumentInferenceUnavailable(
                MALFORMED_RESPONSE,
                f"judge decision {content.get('decision')!r} is not one of "
                f"{sorted(VALID_JUDGE_DECISIONS)}",
                stage="validation",
                modality="text",
            )
        try:
            overall_score = float(content["overall_score"])
            confidence = float(content.get("confidence", 0.0))
        except (KeyError, TypeError, ValueError) as exc:
            raise DocumentInferenceUnavailable(
                MALFORMED_RESPONSE,
                f"judge reply missing numeric overall_score/confidence: {exc}",
                stage="validation",
                modality="text",
            ) from exc

        return JudgeEvaluation(
            overall_score=overall_score,
            decision=decision,
            completeness=content.get("completeness", {"score": 0, "reasoning": ""}),
            accuracy=content.get("accuracy", {"score": 0, "reasoning": ""}),
            compliance=content.get("compliance", {"score": 0, "reasoning": ""}),
            quality=content.get("quality", {"score": 0, "reasoning": ""}),
            issues_found=list(content.get("issues_found", []) or []),
            confidence=confidence,
            reasoning=str(content.get("reasoning", "")),
            judge_model=str(result.get("model_used", "")),
            model_route=dict(result.get("model_route", {}) or {}),
        )

    def calculate_decision_threshold(self, overall_score: float) -> str:
        """Calculate decision based on overall score."""
        if overall_score >= 4.5:
            return "APPROVE"
        elif overall_score >= 3.5:
            return "REVIEW_REQUIRED"
        else:
            return "REJECT"

    def get_quality_level(self, overall_score: float) -> str:
        """Get quality level description based on score."""
        if overall_score >= 4.5:
            return "Excellent"
        elif overall_score >= 4.0:
            return "Good"
        elif overall_score >= 3.5:
            return "Fair"
        elif overall_score >= 3.0:
            return "Poor"
        else:
            return "Very Poor"
