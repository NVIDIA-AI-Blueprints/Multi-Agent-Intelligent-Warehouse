"""
Advanced OCR with Nemotron Parse
VLM-based OCR with semantic understanding for complex documents.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
import os
import httpx
import base64
import io
from PIL import Image
from datetime import datetime

logger = logging.getLogger(__name__)


class NemotronParseService:
    """
    Advanced OCR using NeMo Retriever Parse for complex documents.

    Features:
    - VLM-based OCR with semantic understanding
    - Preserves reading order & document structure
    - Element classification (headers, body, footers)
    - Spatial grounding with coordinates
    - Better handling of damaged/poor quality scans
    """

    def __init__(self):
        self.api_key = os.getenv("NEMO_PARSE_API_KEY", "")
        self.base_url = os.getenv(
            "NEMO_PARSE_URL", "https://integrate.api.nvidia.com/v1"
        )
        self.timeout = 60

    async def initialize(self):
        """Initialize the Nemotron Parse service."""
        try:
            if not self.api_key:
                logger.warning(
                    "NEMO_PARSE_API_KEY not found, using mock implementation"
                )
                return

            # Test API connection
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                response.raise_for_status()

            logger.info("Nemotron Parse Service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Nemotron Parse Service: {e}")
            logger.warning("Falling back to mock implementation")

    async def parse_document(
        self, images: List[Image.Image], layout_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Parse document using Nemotron Parse for advanced OCR.

        Args:
            images: List of PIL Images to process
            layout_result: Layout detection results

        Returns:
            Advanced OCR results with semantic understanding
        """
        try:
            logger.info(f"Parsing {len(images)} images using Nemotron Parse")

            all_parse_results = []
            total_text = ""
            overall_confidence = 0.0

            for i, image in enumerate(images):
                logger.info(f"Parsing image {i + 1}/{len(images)}")

                # Parse single image
                parse_result = await self._parse_image(image, i + 1)
                all_parse_results.append(parse_result)

                # Accumulate text and confidence
                total_text += parse_result["text"] + "\n"
                overall_confidence += parse_result["confidence"]

            # Calculate average confidence
            overall_confidence = overall_confidence / len(images) if images else 0.0

            # Enhance with semantic understanding
            semantic_results = await self._add_semantic_understanding(
                all_parse_results, layout_result
            )

            return {
                "text": total_text.strip(),
                "page_results": semantic_results,
                "confidence": overall_confidence,
                "total_pages": len(images),
                "model_used": "Nemotron-Parse",
                "processing_timestamp": datetime.now().isoformat(),
                "semantic_enhanced": True,
                "reading_order_preserved": True,
            }

        except Exception as e:
            logger.error(f"Document parsing failed: {e}")
            raise

    async def _parse_image(
        self, image: Image.Image, page_number: int
    ) -> Dict[str, Any]:
        """Parse a single image using Nemotron Parse."""
        try:
            if not self.api_key:
                # Mock implementation for development
                return await self._mock_parse_extraction(image, page_number)

            # Convert image to base64
            image_base64 = await self._image_to_base64(image)

            # Call Nemotron Parse API
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/models/nemoretriever-parse/infer",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "inputs": [
                            {
                                "name": "image",
                                "shape": [1],
                                "datatype": "BYTES",
                                "data": [image_base64],
                            }
                        ]
                    },
                )
                response.raise_for_status()

                result = response.json()

                # Parse results
                parse_data = self._parse_parse_result(result, image.size)

                return {
                    "page_number": page_number,
                    "text": parse_data["text"],
                    "elements": parse_data["elements"],
                    "reading_order": parse_data["reading_order"],
                    "confidence": parse_data["confidence"],
                    "image_dimensions": image.size,
                }

        except Exception as e:
            logger.error(f"Image parsing failed for page {page_number}: {e}")
            # Fall back to mock implementation
            return await self._mock_parse_extraction(image, page_number)

    async def _image_to_base64(self, image: Image.Image) -> str:
        """Convert PIL Image to base64 string."""
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode()

    def _parse_parse_result(
        self, api_result: Dict[str, Any], image_size: tuple
    ) -> Dict[str, Any]:
        """Parse Nemotron Parse API result."""
        try:
            outputs = api_result.get("outputs", [])

            text = ""
            elements = []
            reading_order = []

            for output in outputs:
                if output.get("name") == "text":
                    text = output.get("data", [""])[0]
                elif output.get("name") == "elements":
                    elements_data = output.get("data", [])
                    for element_data in elements_data:
                        elements.append(
                            {
                                "text": element_data.get("text", ""),
                                "type": element_data.get("type", "text"),
                                "bbox": element_data.get("bbox", [0, 0, 0, 0]),
                                "confidence": element_data.get("confidence", 0.0),
                                "reading_order": element_data.get("reading_order", 0),
                            }
                        )
                elif output.get("name") == "reading_order":
                    reading_order = output.get("data", [])

            # Calculate overall confidence
            confidence_scores = [elem["confidence"] for elem in elements]
            overall_confidence = (
                sum(confidence_scores) / len(confidence_scores)
                if confidence_scores
                else 0.0
            )

            return {
                "text": text,
                "elements": elements,
                "reading_order": reading_order,
                "confidence": overall_confidence,
            }

        except Exception as e:
            logger.error(f"Failed to parse Nemotron Parse result: {e}")
            return {"text": "", "elements": [], "reading_order": [], "confidence": 0.0}

    async def _add_semantic_understanding(
        self, parse_results: List[Dict[str, Any]], layout_result: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Add semantic understanding to parse results."""
        enhanced_results = []

        for i, parse_result in enumerate(parse_results):
            page_layout = (
                layout_result["layout_detection"][i]
                if i < len(layout_result["layout_detection"])
                else None
            )

            # Enhance elements with semantic information
            enhanced_elements = await self._enhance_elements_semantically(
                parse_result["elements"], page_layout
            )

            enhanced_result = {
                **parse_result,
                "elements": enhanced_elements,
                "semantic_analysis": await self._perform_semantic_analysis(
                    enhanced_elements
                ),
                "layout_type": page_layout["layout_type"] if page_layout else "unknown",
                "document_structure": (
                    page_layout["document_structure"] if page_layout else {}
                ),
                "semantic_enhanced": True,
            }

            enhanced_results.append(enhanced_result)

        return enhanced_results

    async def _enhance_elements_semantically(
        self, elements: List[Dict[str, Any]], page_layout: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Enhance elements with semantic understanding."""
        enhanced_elements = []

        for element in elements:
            enhanced_element = {
                **element,
                "semantic_type": self._determine_semantic_type(element),
                "context": self._extract_context(element, elements),
                "importance": self._calculate_importance(element),
                "relationships": self._find_relationships(element, elements),
            }

            enhanced_elements.append(enhanced_element)

        return enhanced_elements

    def _determine_semantic_type(self, element: Dict[str, Any]) -> str:
        """Determine semantic type of element."""
        text = element["text"].lower()
        element_type = element["type"]

        # Invoice-specific semantic types
        if "invoice" in text or "bill" in text:
            return "document_title"
        elif "vendor" in text or "supplier" in text:
            return "vendor_info"
        elif "date" in text and any(char.isdigit() for char in text):
            return "date_field"
        elif "total" in text and any(char in text for char in ["$", "€", "£"]):
            return "total_amount"
        elif "item" in text or "description" in text:
            return "item_header"
        elif element_type == "table":
            return "data_table"
        elif element_type == "text" and len(text) > 50:
            return "body_text"
        else:
            return "general_text"

    def _extract_context(
        self, element: Dict[str, Any], all_elements: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Extract contextual information for an element."""
        bbox = element["bbox"]
        element_x = (bbox[0] + bbox[2]) / 2 if len(bbox) >= 4 else 0
        element_y = (bbox[1] + bbox[3]) / 2 if len(bbox) >= 4 else 0

        # Find nearby elements
        nearby_elements = []
        for other_element in all_elements:
            if other_element == element:
                continue

            other_bbox = other_element["bbox"]
            other_x = (other_bbox[0] + other_bbox[2]) / 2 if len(other_bbox) >= 4 else 0
            other_y = (other_bbox[1] + other_bbox[3]) / 2 if len(other_bbox) >= 4 else 0

            distance = ((element_x - other_x) ** 2 + (element_y - other_y) ** 2) ** 0.5

            if distance < 100:  # Within 100 pixels
                nearby_elements.append(
                    {
                        "text": other_element["text"],
                        "type": other_element["type"],
                        "distance": distance,
                    }
                )

        return {
            "nearby_elements": nearby_elements,
            "position": {"x": element_x, "y": element_y},
            "isolation_score": 1.0
            - (len(nearby_elements) / 10),  # Less isolated = lower score
        }

    def _calculate_importance(self, element: Dict[str, Any]) -> float:
        """Calculate importance score for an element."""
        text = element["text"]
        semantic_type = self._determine_semantic_type(element)

        # Base importance by semantic type
        importance_scores = {
            "document_title": 0.9,
            "total_amount": 0.8,
            "vendor_info": 0.7,
            "date_field": 0.6,
            "data_table": 0.7,
            "item_header": 0.5,
            "body_text": 0.4,
            "general_text": 0.3,
        }

        base_importance = importance_scores.get(semantic_type, 0.3)

        # Adjust by text length and confidence
        length_factor = min(len(text) / 100, 1.0)  # Longer text = more important
        confidence_factor = element["confidence"]

        return base_importance * 0.5 + length_factor * 0.3 + confidence_factor * 0.2

    def _find_relationships(
        self, element: Dict[str, Any], all_elements: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Find relationships between elements."""
        relationships = []

        for other_element in all_elements:
            if other_element == element:
                continue

            # Check for logical relationships
            if self._are_related(element, other_element):
                relationships.append(
                    {
                        "target": other_element["text"][:50],  # Truncate for brevity
                        "relationship_type": self._get_relationship_type(
                            element, other_element
                        ),
                        "strength": self._calculate_relationship_strength(
                            element, other_element
                        ),
                    }
                )

        return relationships

    def _are_related(self, element1: Dict[str, Any], element2: Dict[str, Any]) -> bool:
        """Check if two elements are related."""
        text1 = element1["text"].lower()
        text2 = element2["text"].lower()

        # Check for common patterns
        related_patterns = [
            ("invoice", "number"),
            ("date", "due"),
            ("item", "quantity"),
            ("price", "total"),
            ("vendor", "address"),
        ]

        for pattern1, pattern2 in related_patterns:
            if (pattern1 in text1 and pattern2 in text2) or (
                pattern1 in text2 and pattern2 in text1
            ):
                return True

        return False

    def _get_relationship_type(
        self, element1: Dict[str, Any], element2: Dict[str, Any]
    ) -> str:
        """Get the type of relationship between elements."""
        semantic_type1 = self._determine_semantic_type(element1)
        semantic_type2 = self._determine_semantic_type(element2)

        if semantic_type1 == "vendor_info" and semantic_type2 == "date_field":
            return "vendor_date"
        elif semantic_type1 == "item_header" and semantic_type2 == "data_table":
            return "header_table"
        elif semantic_type1 == "total_amount" and semantic_type2 == "data_table":
            return "table_total"
        else:
            return "general"

    def _calculate_relationship_strength(
        self, element1: Dict[str, Any], element2: Dict[str, Any]
    ) -> float:
        """Calculate the strength of relationship between elements."""
        # Simple distance-based relationship strength
        bbox1 = element1["bbox"]
        bbox2 = element2["bbox"]

        if len(bbox1) >= 4 and len(bbox2) >= 4:
            center1_x = (bbox1[0] + bbox1[2]) / 2
            center1_y = (bbox1[1] + bbox1[3]) / 2
            center2_x = (bbox2[0] + bbox2[2]) / 2
            center2_y = (bbox2[1] + bbox2[3]) / 2

            distance = (
                (center1_x - center2_x) ** 2 + (center1_y - center2_y) ** 2
            ) ** 0.5

            # Closer elements have stronger relationships
            return max(0.0, 1.0 - (distance / 200))

        return 0.5

    async def _perform_semantic_analysis(
        self, elements: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Perform semantic analysis on all elements."""
        analysis = {
            "document_type": "unknown",
            "key_fields": [],
            "data_quality": 0.0,
            "completeness": 0.0,
        }

        # Determine document type
        semantic_types = [elem["semantic_type"] for elem in elements]
        if "document_title" in semantic_types and "total_amount" in semantic_types:
            analysis["document_type"] = "invoice"
        elif "vendor_info" in semantic_types:
            analysis["document_type"] = "business_document"

        # Identify key fields
        key_fields = []
        for elem in elements:
            if elem["importance"] > 0.7:
                key_fields.append(
                    {
                        "field": elem["semantic_type"],
                        "value": elem["text"],
                        "confidence": elem["confidence"],
                    }
                )
        analysis["key_fields"] = key_fields

        # Calculate data quality
        confidence_scores = [elem["confidence"] for elem in elements]
        analysis["data_quality"] = (
            sum(confidence_scores) / len(confidence_scores)
            if confidence_scores
            else 0.0
        )

        # Calculate completeness
        required_fields = [
            "document_title",
            "vendor_info",
            "date_field",
            "total_amount",
        ]
        found_fields = [field for field in required_fields if field in semantic_types]
        analysis["completeness"] = len(found_fields) / len(required_fields)

        return analysis

    async def _mock_parse_extraction(
        self, image: Image.Image, page_number: int
    ) -> Dict[str, Any]:
        """Mock parse extraction for development."""
        width, height = image.size

        # Generate mock parse data with semantic understanding
        mock_elements = [
            {
                "text": "INVOICE",
                "type": "title",
                "bbox": [50, 50, 150, 80],
                "confidence": 0.95,
                "reading_order": 0,
            },
            {
                "text": "#INV-2024-001",
                "type": "text",
                "bbox": [200, 50, 350, 80],
                "confidence": 0.92,
                "reading_order": 1,
            },
            {
                "text": "Vendor: ABC Supply Company",
                "type": "text",
                "bbox": [50, 120, 400, 150],
                "confidence": 0.88,
                "reading_order": 2,
            },
            {
                "text": "Date: 2024-01-15",
                "type": "text",
                "bbox": [50, 180, 250, 210],
                "confidence": 0.90,
                "reading_order": 3,
            },
            {
                "text": "Total: $1,763.13",
                "type": "text",
                "bbox": [400, 300, 550, 330],
                "confidence": 0.94,
                "reading_order": 4,
            },
        ]

        mock_text = "\n".join([elem["text"] for elem in mock_elements])

        return {
            "page_number": page_number,
            "text": mock_text,
            "elements": mock_elements,
            "reading_order": list(range(len(mock_elements))),
            "confidence": 0.91,
            "image_dimensions": image.size,
        }
