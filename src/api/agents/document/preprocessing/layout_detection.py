"""
Layout Detection Service
Handles page layout detection and element classification using NeMo models.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
import os
import httpx
from PIL import Image
from datetime import datetime

logger = logging.getLogger(__name__)


class LayoutDetectionService:
    """
    Layout Detection Service using NeMo models.

    Uses:
    - nv-yolox-page-elements-v1 for element detection
    - nemoretriever-page-elements-v1 for semantic regions
    """

    def __init__(self):
        self.api_key = os.getenv("NEMO_RETRIEVER_API_KEY", "")
        self.base_url = os.getenv(
            "NEMO_RETRIEVER_URL", "https://integrate.api.nvidia.com/v1"
        )
        self.timeout = 60

    async def initialize(self):
        """Initialize the layout detection service."""
        try:
            if not self.api_key:
                logger.warning(
                    "NEMO_RETRIEVER_API_KEY not found, using mock implementation"
                )
                return

            logger.info("Layout Detection Service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Layout Detection Service: {e}")
            logger.warning("Falling back to mock implementation")

    async def detect_layout(
        self, preprocessing_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Detect page layout and classify elements.

        Args:
            preprocessing_result: Result from NeMo Retriever preprocessing

        Returns:
            Layout detection results with element classifications
        """
        try:
            logger.info("Detecting page layout...")

            layout_results = []

            for page in preprocessing_result["processed_pages"]:
                page_layout = await self._detect_page_layout(page)
                layout_results.append(page_layout)

            return {
                "layout_detection": layout_results,
                "total_pages": len(layout_results),
                "detection_timestamp": datetime.now().isoformat(),
                "confidence": self._calculate_overall_confidence(layout_results),
            }

        except Exception as e:
            logger.error(f"Layout detection failed: {e}")
            raise

    async def _detect_page_layout(self, page_data: Dict[str, Any]) -> Dict[str, Any]:
        """Detect layout for a single page."""
        try:
            image = page_data["image"]
            elements = page_data["elements"]

            # Classify elements by type
            classified_elements = await self._classify_elements(elements, image)

            # Detect reading order
            reading_order = await self._detect_reading_order(classified_elements)

            # Identify document structure
            document_structure = await self._identify_document_structure(
                classified_elements
            )

            return {
                "page_number": page_data["page_number"],
                "dimensions": page_data["dimensions"],
                "elements": classified_elements,
                "reading_order": reading_order,
                "document_structure": document_structure,
                "layout_type": self._determine_layout_type(classified_elements),
            }

        except Exception as e:
            logger.error(f"Page layout detection failed: {e}")
            raise

    async def _classify_elements(
        self, elements: List[Dict[str, Any]], image: Image.Image
    ) -> List[Dict[str, Any]]:
        """Classify detected elements by type and purpose."""
        classified = []

        for element in elements:
            element_type = element["type"]

            # Enhanced classification based on element properties
            classification = {
                "original_type": element_type,
                "classified_type": self._enhance_element_classification(element, image),
                "confidence": element["confidence"],
                "bbox": element["bbox"],
                "area": element["area"],
                "properties": self._extract_element_properties(element, image),
            }

            classified.append(classification)

        return classified

    def _enhance_element_classification(
        self, element: Dict[str, Any], image: Image.Image
    ) -> str:
        """Enhance element classification based on properties."""
        element_type = element["type"]
        bbox = element["bbox"]
        area = element["area"]

        # Calculate element properties
        width = bbox[2] - bbox[0] if len(bbox) >= 4 else 0
        height = bbox[3] - bbox[1] if len(bbox) >= 4 else 0
        aspect_ratio = width / height if height > 0 else 0

        # Enhanced classification logic
        if element_type == "table":
            if aspect_ratio > 2.0:
                return "wide_table"
            elif aspect_ratio < 0.5:
                return "tall_table"
            else:
                return "standard_table"

        elif element_type == "text":
            if area > 50000:  # Large text area
                return "body_text"
            elif height > 30:
                return "heading"
            else:
                return "small_text"

        elif element_type == "title":
            return "document_title"

        else:
            return element_type

    def _extract_element_properties(
        self, element: Dict[str, Any], image: Image.Image
    ) -> Dict[str, Any]:
        """Extract additional properties from elements."""
        bbox = element["bbox"]

        if len(bbox) >= 4:
            x1, y1, x2, y2 = bbox[:4]
            width = x2 - x1
            height = y2 - y1

            return {
                "width": width,
                "height": height,
                "aspect_ratio": width / height if height > 0 else 0,
                "center_x": (x1 + x2) / 2,
                "center_y": (y1 + y2) / 2,
                "area_percentage": (width * height)
                / (image.size[0] * image.size[1])
                * 100,
            }
        else:
            return {}

    async def _detect_reading_order(self, elements: List[Dict[str, Any]]) -> List[int]:
        """Detect the reading order of elements on the page."""
        try:
            # Sort elements by reading order (top to bottom, left to right)
            sorted_elements = sorted(
                elements,
                key=lambda e: (e["bbox"][1], e["bbox"][0]),  # Sort by y, then x
            )

            # Return indices in reading order
            reading_order = []
            for i, element in enumerate(sorted_elements):
                reading_order.append(i)

            return reading_order

        except Exception as e:
            logger.error(f"Reading order detection failed: {e}")
            return list(range(len(elements)))

    async def _identify_document_structure(
        self, elements: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Identify the overall document structure."""
        structure = {
            "has_title": False,
            "has_headers": False,
            "has_tables": False,
            "has_footers": False,
            "has_signatures": False,
            "layout_pattern": "unknown",
        }

        for element in elements:
            classified_type = element["classified_type"]

            if "title" in classified_type.lower():
                structure["has_title"] = True
            elif "header" in classified_type.lower():
                structure["has_headers"] = True
            elif "table" in classified_type.lower():
                structure["has_tables"] = True
            elif "footer" in classified_type.lower():
                structure["has_footers"] = True
            elif "signature" in classified_type.lower():
                structure["has_signatures"] = True

        # Determine layout pattern
        if structure["has_tables"] and structure["has_title"]:
            structure["layout_pattern"] = "form_with_table"
        elif structure["has_tables"]:
            structure["layout_pattern"] = "table_document"
        elif structure["has_title"] and structure["has_headers"]:
            structure["layout_pattern"] = "structured_document"
        else:
            structure["layout_pattern"] = "simple_text"

        return structure

    def _determine_layout_type(self, elements: List[Dict[str, Any]]) -> str:
        """Determine the overall layout type of the page."""
        table_count = sum(
            1 for e in elements if "table" in e["classified_type"].lower()
        )
        text_count = sum(1 for e in elements if "text" in e["classified_type"].lower())

        if table_count > text_count:
            return "table_dominant"
        elif text_count > table_count * 2:
            return "text_dominant"
        else:
            return "mixed_layout"

    def _calculate_overall_confidence(
        self, layout_results: List[Dict[str, Any]]
    ) -> float:
        """Calculate overall confidence for layout detection."""
        if not layout_results:
            return 0.0

        total_confidence = 0.0
        total_elements = 0

        for result in layout_results:
            for element in result["elements"]:
                total_confidence += element["confidence"]
                total_elements += 1

        return total_confidence / total_elements if total_elements > 0 else 0.0
