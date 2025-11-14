"""
Quality Scorer for Document Processing
Comprehensive quality scoring framework for document evaluation.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class QualityScore:
    """Represents a quality score result."""

    overall_score: float
    completeness_score: float
    accuracy_score: float
    consistency_score: float
    readability_score: float
    confidence: float
    feedback: str
    recommendations: List[str]


class QualityScorer:
    """
    Quality Scorer for document processing.

    Responsibilities:
    - Calculate comprehensive quality scores
    - Provide detailed feedback and recommendations
    - Support continuous improvement
    - Generate quality reports
    """

    def __init__(self):
        self.quality_weights = {
            "completeness": 0.25,
            "accuracy": 0.30,
            "consistency": 0.20,
            "readability": 0.25,
        }

    async def initialize(self):
        """Initialize the quality scorer."""
        logger.info("Quality Scorer initialized successfully")

    async def score_document(
        self, judge_result: Dict[str, Any], entities: Dict[str, Any], document_type: str
    ) -> QualityScore:
        """
        Score document quality based on judge evaluation and entities.

        Args:
            judge_result: Result from Large LLM Judge
            entities: Extracted entities
            document_type: Type of document

        Returns:
            Comprehensive quality score with feedback
        """
        try:
            logger.info(f"Scoring quality for {document_type} document")

            # Calculate individual scores
            completeness_score = await self._calculate_completeness_score(
                judge_result, entities, document_type
            )
            accuracy_score = await self._calculate_accuracy_score(
                judge_result, entities, document_type
            )
            consistency_score = await self._calculate_consistency_score(
                judge_result, entities, document_type
            )
            readability_score = await self._calculate_readability_score(
                judge_result, entities, document_type
            )

            # Calculate overall score
            overall_score = (
                completeness_score * self.quality_weights["completeness"]
                + accuracy_score * self.quality_weights["accuracy"]
                + consistency_score * self.quality_weights["consistency"]
                + readability_score * self.quality_weights["readability"]
            )

            # Generate feedback and recommendations
            feedback = await self._generate_feedback(
                judge_result, entities, document_type
            )
            recommendations = await self._generate_recommendations(
                judge_result, entities, document_type
            )

            # Calculate confidence
            confidence = await self._calculate_confidence(judge_result, entities)

            quality_score = QualityScore(
                overall_score=overall_score,
                completeness_score=completeness_score,
                accuracy_score=accuracy_score,
                consistency_score=consistency_score,
                readability_score=readability_score,
                confidence=confidence,
                feedback=feedback,
                recommendations=recommendations,
            )

            logger.info(
                f"Quality scoring completed with overall score: {overall_score:.2f}"
            )
            return quality_score

        except Exception as e:
            logger.error(f"Quality scoring failed: {e}")
            raise

    async def _calculate_completeness_score(
        self, judge_result: Dict[str, Any], entities: Dict[str, Any], document_type: str
    ) -> float:
        """Calculate completeness score."""
        try:
            # Get judge completeness assessment
            completeness = judge_result.get("completeness", {})
            judge_score = completeness.get("score", 0.0)

            # Calculate entity completeness
            entity_completeness = await self._calculate_entity_completeness(
                entities, document_type
            )

            # Calculate field completeness
            field_completeness = await self._calculate_field_completeness(
                entities, document_type
            )

            # Weighted average
            completeness_score = (
                judge_score * 0.4 + entity_completeness * 0.3 + field_completeness * 0.3
            )

            return min(5.0, max(1.0, completeness_score))

        except Exception as e:
            logger.error(f"Failed to calculate completeness score: {e}")
            return 3.0

    async def _calculate_accuracy_score(
        self, judge_result: Dict[str, Any], entities: Dict[str, Any], document_type: str
    ) -> float:
        """Calculate accuracy score."""
        try:
            # Get judge accuracy assessment
            accuracy = judge_result.get("accuracy", {})
            judge_score = accuracy.get("score", 0.0)

            # Calculate entity accuracy
            entity_accuracy = await self._calculate_entity_accuracy(entities)

            # Calculate data type accuracy
            data_type_accuracy = await self._calculate_data_type_accuracy(entities)

            # Weighted average
            accuracy_score = (
                judge_score * 0.5 + entity_accuracy * 0.3 + data_type_accuracy * 0.2
            )

            return min(5.0, max(1.0, accuracy_score))

        except Exception as e:
            logger.error(f"Failed to calculate accuracy score: {e}")
            return 3.0

    async def _calculate_consistency_score(
        self, judge_result: Dict[str, Any], entities: Dict[str, Any], document_type: str
    ) -> float:
        """Calculate consistency score."""
        try:
            # Get judge compliance assessment
            compliance = judge_result.get("compliance", {})
            judge_score = compliance.get("score", 0.0)

            # Calculate internal consistency
            internal_consistency = await self._calculate_internal_consistency(entities)

            # Calculate format consistency
            format_consistency = await self._calculate_format_consistency(entities)

            # Weighted average
            consistency_score = (
                judge_score * 0.4
                + internal_consistency * 0.3
                + format_consistency * 0.3
            )

            return min(5.0, max(1.0, consistency_score))

        except Exception as e:
            logger.error(f"Failed to calculate consistency score: {e}")
            return 3.0

    async def _calculate_readability_score(
        self, judge_result: Dict[str, Any], entities: Dict[str, Any], document_type: str
    ) -> float:
        """Calculate readability score."""
        try:
            # Get judge quality assessment
            quality = judge_result.get("quality", {})
            judge_score = quality.get("score", 0.0)

            # Calculate text quality
            text_quality = await self._calculate_text_quality(entities)

            # Calculate structure quality
            structure_quality = await self._calculate_structure_quality(entities)

            # Weighted average
            readability_score = (
                judge_score * 0.4 + text_quality * 0.3 + structure_quality * 0.3
            )

            return min(5.0, max(1.0, readability_score))

        except Exception as e:
            logger.error(f"Failed to calculate readability score: {e}")
            return 3.0

    async def _calculate_entity_completeness(
        self, entities: Dict[str, Any], document_type: str
    ) -> float:
        """Calculate entity completeness score."""
        try:
            # Define required entities by document type
            required_entities = {
                "invoice": [
                    "invoice_number",
                    "vendor_name",
                    "invoice_date",
                    "total_amount",
                ],
                "receipt": [
                    "receipt_number",
                    "merchant_name",
                    "transaction_date",
                    "total_amount",
                ],
                "bol": ["bol_number", "shipper_name", "consignee_name", "ship_date"],
                "purchase_order": [
                    "po_number",
                    "buyer_name",
                    "supplier_name",
                    "order_date",
                ],
            }

            required = required_entities.get(document_type, [])
            if not required:
                return 3.0

            # Count found entities
            found_entities = 0
            for category, entity_list in entities.items():
                if isinstance(entity_list, list):
                    for entity in entity_list:
                        if isinstance(entity, dict) and entity.get("name") in required:
                            found_entities += 1

            # Calculate completeness percentage
            completeness = found_entities / len(required)
            return completeness * 5.0  # Scale to 1-5

        except Exception as e:
            logger.error(f"Failed to calculate entity completeness: {e}")
            return 3.0

    async def _calculate_field_completeness(
        self, entities: Dict[str, Any], document_type: str
    ) -> float:
        """Calculate field completeness score."""
        try:
            total_fields = 0
            complete_fields = 0

            for category, entity_list in entities.items():
                if isinstance(entity_list, list):
                    for entity in entity_list:
                        if isinstance(entity, dict):
                            total_fields += 1
                            if entity.get("value") and entity.get("value").strip():
                                complete_fields += 1

            if total_fields == 0:
                return 3.0

            completeness = complete_fields / total_fields
            return completeness * 5.0  # Scale to 1-5

        except Exception as e:
            logger.error(f"Failed to calculate field completeness: {e}")
            return 3.0

    async def _calculate_entity_accuracy(self, entities: Dict[str, Any]) -> float:
        """Calculate entity accuracy score."""
        try:
            total_entities = 0
            accurate_entities = 0

            for category, entity_list in entities.items():
                if isinstance(entity_list, list):
                    for entity in entity_list:
                        if isinstance(entity, dict):
                            total_entities += 1
                            confidence = entity.get("confidence", 0.0)
                            if confidence >= 0.8:
                                accurate_entities += 1

            if total_entities == 0:
                return 3.0

            accuracy = accurate_entities / total_entities
            return accuracy * 5.0  # Scale to 1-5

        except Exception as e:
            logger.error(f"Failed to calculate entity accuracy: {e}")
            return 3.0

    async def _calculate_data_type_accuracy(self, entities: Dict[str, Any]) -> float:
        """Calculate data type accuracy score."""
        try:
            total_fields = 0
            correct_types = 0

            for category, entity_list in entities.items():
                if isinstance(entity_list, list):
                    for entity in entity_list:
                        if isinstance(entity, dict):
                            entity_type = entity.get("entity_type", "")
                            value = entity.get("value", "")

                            if entity_type == "financial" and self._is_valid_financial(
                                value
                            ):
                                correct_types += 1
                            elif entity_type == "temporal" and self._is_valid_date(
                                value
                            ):
                                correct_types += 1
                            elif (
                                entity_type == "identifier"
                                and self._is_valid_identifier(value)
                            ):
                                correct_types += 1
                            elif entity_type in ["contact", "product", "address"]:
                                correct_types += (
                                    1  # Assume correct for non-numeric types
                                )

                            total_fields += 1

            if total_fields == 0:
                return 3.0

            accuracy = correct_types / total_fields
            return accuracy * 5.0  # Scale to 1-5

        except Exception as e:
            logger.error(f"Failed to calculate data type accuracy: {e}")
            return 3.0

    def _is_valid_financial(self, value: str) -> bool:
        """Check if value is a valid financial amount."""
        import re

        return bool(re.match(r"^\$?[\d,]+\.?\d*$", value.strip()))

    def _is_valid_date(self, value: str) -> bool:
        """Check if value is a valid date."""
        import re

        date_patterns = [
            r"\d{4}-\d{2}-\d{2}",
            r"\d{1,2}/\d{1,2}/\d{4}",
            r"\d{1,2}-\d{1,2}-\d{4}",
        ]
        return any(re.match(pattern, value.strip()) for pattern in date_patterns)

    def _is_valid_identifier(self, value: str) -> bool:
        """Check if value is a valid identifier."""
        import re

        return bool(re.match(r"^[A-Z]{2,4}-\d{3,6}$", value.strip()))

    async def _calculate_internal_consistency(self, entities: Dict[str, Any]) -> float:
        """Calculate internal consistency score."""
        try:
            # Check for consistency between related fields
            consistency_score = 4.0  # Start with good score

            # Check financial consistency
            financial_entities = entities.get("financial_entities", [])
            if len(financial_entities) > 1:
                # Check if totals are consistent
                totals = []
                for entity in financial_entities:
                    if "total" in entity.get("name", "").lower():
                        try:
                            totals.append(float(entity.get("value", "0")))
                        except ValueError:
                            pass

                if len(totals) > 1:
                    if (
                        abs(max(totals) - min(totals)) > 0.01
                    ):  # Allow small rounding differences
                        consistency_score -= 1.0

            return min(5.0, max(1.0, consistency_score))

        except Exception as e:
            logger.error(f"Failed to calculate internal consistency: {e}")
            return 3.0

    async def _calculate_format_consistency(self, entities: Dict[str, Any]) -> float:
        """Calculate format consistency score."""
        try:
            consistency_score = 4.0  # Start with good score

            # Check date format consistency
            temporal_entities = entities.get("temporal_entities", [])
            if len(temporal_entities) > 1:
                formats = set()
                for entity in temporal_entities:
                    value = entity.get("value", "")
                    if self._is_valid_date(value):
                        if "YYYY-MM-DD" in value:
                            formats.add("ISO")
                        elif "/" in value:
                            formats.add("US")
                        elif "-" in value:
                            formats.add("US_DASH")

                if len(formats) > 1:
                    consistency_score -= 1.0

            return min(5.0, max(1.0, consistency_score))

        except Exception as e:
            logger.error(f"Failed to calculate format consistency: {e}")
            return 3.0

    async def _calculate_text_quality(self, entities: Dict[str, Any]) -> float:
        """Calculate text quality score."""
        try:
            total_text_length = 0
            quality_indicators = 0

            for category, entity_list in entities.items():
                if isinstance(entity_list, list):
                    for entity in entity_list:
                        if isinstance(entity, dict):
                            value = entity.get("value", "")
                            total_text_length += len(value)

                            # Check for quality indicators
                            if len(value) > 3:  # Not too short
                                quality_indicators += 1
                            if not value.isupper():  # Not all caps
                                quality_indicators += 1
                            if not value.isdigit():  # Not just numbers
                                quality_indicators += 1

            if total_text_length == 0:
                return 3.0

            quality_score = (quality_indicators / (total_text_length / 10)) * 5.0
            return min(5.0, max(1.0, quality_score))

        except Exception as e:
            logger.error(f"Failed to calculate text quality: {e}")
            return 3.0

    async def _calculate_structure_quality(self, entities: Dict[str, Any]) -> float:
        """Calculate structure quality score."""
        try:
            # Check if we have a good distribution of entity types
            entity_types = set()
            for category, entity_list in entities.items():
                if isinstance(entity_list, list):
                    for entity in entity_list:
                        if isinstance(entity, dict):
                            entity_types.add(entity.get("entity_type", ""))

            # More entity types = better structure
            structure_score = min(5.0, len(entity_types) * 0.5)
            return max(1.0, structure_score)

        except Exception as e:
            logger.error(f"Failed to calculate structure quality: {e}")
            return 3.0

    async def _generate_feedback(
        self, judge_result: Dict[str, Any], entities: Dict[str, Any], document_type: str
    ) -> str:
        """Generate comprehensive feedback."""
        try:
            feedback_parts = []

            # Add judge feedback
            reasoning = judge_result.get("reasoning", "")
            if reasoning:
                feedback_parts.append(f"Judge Assessment: {reasoning}")

            # Add completeness feedback
            completeness = judge_result.get("completeness", {})
            if completeness.get("issues"):
                feedback_parts.append(
                    f"Completeness Issues: {', '.join(completeness['issues'])}"
                )

            # Add accuracy feedback
            accuracy = judge_result.get("accuracy", {})
            if accuracy.get("calculation_errors"):
                feedback_parts.append(
                    f"Calculation Errors: {', '.join(accuracy['calculation_errors'])}"
                )

            # Add compliance feedback
            compliance = judge_result.get("compliance", {})
            if compliance.get("compliance_issues"):
                feedback_parts.append(
                    f"Compliance Issues: {', '.join(compliance['compliance_issues'])}"
                )

            # Add quality feedback
            quality = judge_result.get("quality", {})
            if quality.get("anomalies"):
                feedback_parts.append(
                    f"Quality Anomalies: {', '.join(quality['anomalies'])}"
                )

            return (
                ". ".join(feedback_parts)
                if feedback_parts
                else "No specific issues identified."
            )

        except Exception as e:
            logger.error(f"Failed to generate feedback: {e}")
            return "Feedback generation failed."

    async def _generate_recommendations(
        self, judge_result: Dict[str, Any], entities: Dict[str, Any], document_type: str
    ) -> List[str]:
        """Generate recommendations for improvement."""
        try:
            recommendations = []

            # Add judge recommendations
            compliance = judge_result.get("compliance", {})
            if compliance.get("recommendations"):
                recommendations.extend(compliance["recommendations"])

            # Add completeness recommendations
            completeness = judge_result.get("completeness", {})
            if completeness.get("missing_fields"):
                recommendations.append(
                    f"Add missing fields: {', '.join(completeness['missing_fields'])}"
                )

            # Add accuracy recommendations
            accuracy = judge_result.get("accuracy", {})
            if accuracy.get("data_type_issues"):
                recommendations.append("Verify data types and formats")

            # Add quality recommendations
            quality = judge_result.get("quality", {})
            if quality.get("confidence_assessment") == "low":
                recommendations.append(
                    "Improve document quality for better OCR results"
                )

            return recommendations

        except Exception as e:
            logger.error(f"Failed to generate recommendations: {e}")
            return ["Review document processing results"]

    async def _calculate_confidence(
        self, judge_result: Dict[str, Any], entities: Dict[str, Any]
    ) -> float:
        """Calculate overall confidence score."""
        try:
            # Get judge confidence
            judge_confidence = judge_result.get("confidence", 0.0)

            # Calculate entity confidence
            total_entities = 0
            total_confidence = 0.0

            for category, entity_list in entities.items():
                if isinstance(entity_list, list):
                    for entity in entity_list:
                        if isinstance(entity, dict):
                            total_entities += 1
                            total_confidence += entity.get("confidence", 0.0)

            entity_confidence = (
                total_confidence / total_entities if total_entities > 0 else 0.0
            )

            # Weighted average
            overall_confidence = judge_confidence * 0.6 + entity_confidence * 0.4
            return min(1.0, max(0.0, overall_confidence))

        except Exception as e:
            logger.error(f"Failed to calculate confidence: {e}")
            return 0.5
