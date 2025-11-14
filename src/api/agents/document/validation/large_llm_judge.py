"""
Stage 5: Large LLM Judge & Validator with Llama 3.1 Nemotron 70B
Comprehensive evaluation framework for document quality and accuracy.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
import os
import httpx
import json
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class JudgeEvaluation:
    """Represents a judge evaluation result."""

    overall_score: float
    decision: str
    completeness: Dict[str, Any]
    accuracy: Dict[str, Any]
    compliance: Dict[str, Any]
    quality: Dict[str, Any]
    issues_found: List[str]
    confidence: float
    reasoning: str


class LargeLLMJudge:
    """
    Stage 5: Large LLM Judge using Llama 3.1 Nemotron 70B Instruct NIM.

    Evaluation Framework:
    1. Completeness Check (Score: 1-5)
    2. Accuracy Validation (Score: 1-5)
    3. Business Logic Compliance (Score: 1-5)
    4. Quality & Confidence (Score: 1-5)
    """

    def __init__(self):
        self.api_key = os.getenv("LLAMA_70B_API_KEY", "")
        self.base_url = os.getenv(
            "LLAMA_70B_URL", "https://integrate.api.nvidia.com/v1"
        )
        self.timeout = 60

    async def initialize(self):
        """Initialize the Large LLM Judge."""
        try:
            if not self.api_key:
                logger.warning("LLAMA_70B_API_KEY not found, using mock implementation")
                return

            # Test API connection
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                response.raise_for_status()

            logger.info("Large LLM Judge initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Large LLM Judge: {e}")
            logger.warning("Falling back to mock implementation")

    async def evaluate_document(
        self,
        structured_data: Dict[str, Any],
        entities: Dict[str, Any],
        document_type: str,
    ) -> JudgeEvaluation:
        """
        Evaluate document using comprehensive judge framework.

        Args:
            structured_data: Structured data from Small LLM processing
            entities: Extracted entities
            document_type: Type of document

        Returns:
            Complete judge evaluation with scores and reasoning
        """
        try:
            logger.info(f"Evaluating {document_type} document with Large LLM Judge")

            # Prepare evaluation prompt
            evaluation_prompt = self._create_evaluation_prompt(
                structured_data, entities, document_type
            )

            # Call Large LLM for evaluation
            if not self.api_key:
                # Mock implementation for development
                evaluation_result = await self._mock_judge_evaluation(document_type)
            else:
                evaluation_result = await self._call_judge_api(evaluation_prompt)

            # Parse and structure the evaluation
            judge_evaluation = self._parse_judge_result(
                evaluation_result, document_type
            )

            logger.info(
                f"Judge evaluation completed with overall score: {judge_evaluation.overall_score}"
            )
            return judge_evaluation

        except Exception as e:
            logger.error(f"Document evaluation failed: {e}")
            raise

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
        """Call Llama 3.1 Nemotron 70B API for evaluation."""
        try:
            messages = [{"role": "user", "content": prompt}]

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "meta/llama-3.1-70b-instruct",
                        "messages": messages,
                        "max_tokens": 2000,
                        "temperature": 0.1,
                    },
                )
                response.raise_for_status()

                result = response.json()
                # Extract response content from chat completions
                content = result["choices"][0]["message"]["content"]

                # Try to parse JSON response
                try:
                    parsed_content = json.loads(content)
                    return {
                        "content": parsed_content,
                        "confidence": parsed_content.get("confidence", 0.8),
                        "raw_response": content,
                    }
                except json.JSONDecodeError:
                    # If JSON parsing fails, return raw content
                    return {
                        "content": {"raw_text": content},
                        "confidence": 0.7,
                        "raw_response": content,
                    }

        except Exception as e:
            logger.error(f"Judge API call failed: {e}")
            raise

    def _parse_judge_result(
        self, result: Dict[str, Any], document_type: str
    ) -> JudgeEvaluation:
        """Parse judge API result into structured evaluation."""
        try:
            content = result["content"]

            # Handle both structured and raw responses
            if "raw_text" in content:
                # Parse raw text response
                return self._parse_raw_judge_response(
                    content["raw_text"], document_type
                )

            # Use structured response
            return JudgeEvaluation(
                overall_score=content.get("overall_score", 0.0),
                decision=content.get("decision", "REVIEW_REQUIRED"),
                completeness=content.get("completeness", {"score": 0, "reasoning": ""}),
                accuracy=content.get("accuracy", {"score": 0, "reasoning": ""}),
                compliance=content.get("compliance", {"score": 0, "reasoning": ""}),
                quality=content.get("quality", {"score": 0, "reasoning": ""}),
                issues_found=content.get("issues_found", []),
                confidence=content.get("confidence", 0.0),
                reasoning=content.get("reasoning", ""),
            )

        except Exception as e:
            logger.error(f"Failed to parse judge result: {e}")
            return self._create_fallback_evaluation(document_type)

    def _parse_raw_judge_response(
        self, raw_text: str, document_type: str
    ) -> JudgeEvaluation:
        """Parse raw text response from judge."""
        # Simple parsing logic for raw text
        # In a real implementation, this would use more sophisticated NLP

        # Extract overall score
        import re

        score_match = re.search(r"overall[_\s]score[:\s]*(\d+\.?\d*)", raw_text.lower())
        overall_score = float(score_match.group(1)) if score_match else 3.0

        # Extract decision
        if "approve" in raw_text.lower():
            decision = "APPROVE"
        elif "reject" in raw_text.lower():
            decision = "REJECT"
        else:
            decision = "REVIEW_REQUIRED"

        # Extract confidence
        confidence_match = re.search(r"confidence[:\s]*(\d+\.?\d*)", raw_text.lower())
        confidence = float(confidence_match.group(1)) if confidence_match else 0.8

        return JudgeEvaluation(
            overall_score=overall_score,
            decision=decision,
            completeness={"score": overall_score, "reasoning": "Parsed from raw text"},
            accuracy={"score": overall_score, "reasoning": "Parsed from raw text"},
            compliance={"score": overall_score, "reasoning": "Parsed from raw text"},
            quality={"score": overall_score, "reasoning": "Parsed from raw text"},
            issues_found=[],
            confidence=confidence,
            reasoning=raw_text[:200] + "..." if len(raw_text) > 200 else raw_text,
        )

    def _create_fallback_evaluation(self, document_type: str) -> JudgeEvaluation:
        """Create fallback evaluation when parsing fails."""
        return JudgeEvaluation(
            overall_score=3.0,
            decision="REVIEW_REQUIRED",
            completeness={"score": 3.0, "reasoning": "Fallback evaluation"},
            accuracy={"score": 3.0, "reasoning": "Fallback evaluation"},
            compliance={"score": 3.0, "reasoning": "Fallback evaluation"},
            quality={"score": 3.0, "reasoning": "Fallback evaluation"},
            issues_found=["Evaluation parsing failed"],
            confidence=0.5,
            reasoning="Fallback evaluation due to parsing error",
        )

    async def _mock_judge_evaluation(self, document_type: str) -> Dict[str, Any]:
        """Mock judge evaluation for development."""

        mock_evaluations = {
            "invoice": {
                "overall_score": 4.2,
                "decision": "APPROVE",
                "completeness": {
                    "score": 5,
                    "reasoning": "All required invoice fields are present and complete",
                    "missing_fields": [],
                    "issues": [],
                },
                "accuracy": {
                    "score": 4,
                    "reasoning": "Most calculations are correct, minor discrepancy in line 3",
                    "calculation_errors": [],
                    "data_type_issues": [],
                },
                "compliance": {
                    "score": 4,
                    "reasoning": "Business logic is mostly compliant, vendor code format needs verification",
                    "compliance_issues": [],
                    "recommendations": ["Verify vendor code format"],
                },
                "quality": {
                    "score": 4,
                    "reasoning": "High confidence extractions, OCR quality is good",
                    "confidence_assessment": "high",
                    "anomalies": [],
                },
                "issues_found": [],
                "confidence": 0.92,
                "reasoning": "Overall high-quality invoice with minor issues that can be easily resolved",
            },
            "receipt": {
                "overall_score": 3.8,
                "decision": "REVIEW_REQUIRED",
                "completeness": {
                    "score": 4,
                    "reasoning": "Most fields present, missing transaction time",
                    "missing_fields": ["transaction_time"],
                    "issues": [],
                },
                "accuracy": {
                    "score": 4,
                    "reasoning": "Calculations are accurate",
                    "calculation_errors": [],
                    "data_type_issues": [],
                },
                "compliance": {
                    "score": 3,
                    "reasoning": "Some business logic issues with item categorization",
                    "compliance_issues": ["Item categorization unclear"],
                    "recommendations": ["Clarify item categories"],
                },
                "quality": {
                    "score": 4,
                    "reasoning": "Good OCR quality and confidence",
                    "confidence_assessment": "high",
                    "anomalies": [],
                },
                "issues_found": [
                    "Missing transaction time",
                    "Item categorization unclear",
                ],
                "confidence": 0.85,
                "reasoning": "Good quality receipt with some missing information",
            },
            "bol": {
                "overall_score": 4.5,
                "decision": "APPROVE",
                "completeness": {
                    "score": 5,
                    "reasoning": "All BOL fields are complete and accurate",
                    "missing_fields": [],
                    "issues": [],
                },
                "accuracy": {
                    "score": 5,
                    "reasoning": "All calculations and data types are correct",
                    "calculation_errors": [],
                    "data_type_issues": [],
                },
                "compliance": {
                    "score": 4,
                    "reasoning": "Compliant with shipping regulations",
                    "compliance_issues": [],
                    "recommendations": [],
                },
                "quality": {
                    "score": 4,
                    "reasoning": "Excellent OCR quality and high confidence",
                    "confidence_assessment": "very_high",
                    "anomalies": [],
                },
                "issues_found": [],
                "confidence": 0.95,
                "reasoning": "Excellent quality BOL with no issues found",
            },
        }

        return {
            "content": mock_evaluations.get(document_type, mock_evaluations["invoice"]),
            "confidence": 0.9,
            "raw_response": "Mock judge evaluation for development",
        }

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
