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
Stage 2: OCR — text extraction from page images.

v2.0.1 (audit P1-05): OCR is a vision inference and goes through the canonical
ModelGateway with ``Modality.IMAGE``. PolicyFilter serves it only with an
approved Nemotron 3 / 3.5 multimodal model; with none enabled the stage fails
with ``DocumentInferenceUnavailable(MODEL_UNAVAILABLE)``. The v2.0.0 direct
call to a non-Nemotron Llama vision model and its mock fallback are gone.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
import os
import base64
import io
from PIL import Image
from datetime import datetime

logger = logging.getLogger(__name__)


class NeMoOCRService:
    """
    Stage 2: Intelligent OCR using NeMoRetriever-OCR-v1.

    Features:
    - Fast, accurate text extraction from images
    - Layout-aware OCR preserving spatial relationships
    - Structured output with bounding boxes
    - Optimized for warehouse document types
    """

    def __init__(self):
        self.timeout = int(os.getenv("DOCUMENT_OCR_TIMEOUT", "60"))

    async def initialize(self):
        """No provider probing: the ModelGateway owns provider connectivity."""
        return None

    async def extract_text(
        self, images: List[Image.Image], layout_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Extract text from images using NeMoRetriever-OCR-v1.

        Args:
            images: List of PIL Images to process
            layout_result: Layout detection results

        Returns:
            OCR results with text, bounding boxes, and confidence scores
        """
        try:
            logger.info(f"Extracting text from {len(images)} images using NeMo OCR")

            all_ocr_results = []
            total_text = ""
            overall_confidence = 0.0

            for i, image in enumerate(images):
                logger.info(f"Processing image {i + 1}/{len(images)}")

                # Extract text from single image
                ocr_result = await self._extract_text_from_image(image, i + 1)
                all_ocr_results.append(ocr_result)

                # Accumulate text and confidence
                total_text += ocr_result["text"] + "\n"
                overall_confidence += ocr_result["confidence"]

            # Calculate average confidence
            overall_confidence = overall_confidence / len(images) if images else 0.0

            # Enhance results with layout information
            enhanced_results = await self._enhance_with_layout(
                all_ocr_results, layout_result
            )

            return {
                "text": total_text.strip(),
                "page_results": enhanced_results,
                "confidence": overall_confidence,
                "total_pages": len(images),
                "model_used": ",".join(
                    sorted({r.get("model_used", "") for r in all_ocr_results if r.get("model_used")})
                ),
                "via": "maiw_models.ModelGateway",
                "processing_timestamp": datetime.now().isoformat(),
                "layout_enhanced": True,
            }

        except Exception as e:
            logger.error(f"OCR text extraction failed: {e}")
            raise

    async def _extract_text_from_image(
        self, image: Image.Image, page_number: int
    ) -> Dict[str, Any]:
        """Extract text from one page image via ModelGateway (Modality.IMAGE)."""
        from maiw_models import Modality
        from src.api.agents.document.model_gateway_adapter import (
            generate_for_document,
        )

        image_base64 = await self._image_to_base64(image)
        response = await generate_for_document(
            stage="ocr_extraction",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Extract all text from this document image with "
                                "high accuracy. Return the text only."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_base64}"
                            },
                        },
                    ],
                }
            ],
            modality=Modality.IMAGE,
            max_tokens=2000,
            temperature=0.1,
            timeout_s=self.timeout,
        )
        content = response.content
        ocr_data = self._parse_ocr_result(
            {
                "text": content,
                "words": self._extract_words_from_text(content),
                # The model reports no per-word confidence; none is invented.
                "confidence_scores": [],
            },
            image.size,
        )
        return {
            "page_number": page_number,
            "text": ocr_data["text"],
            "words": ocr_data["words"],
            "confidence": ocr_data["confidence"],
            "image_dimensions": image.size,
            "model_used": response.model_id,
        }

    async def _image_to_base64(self, image: Image.Image) -> str:
        """Convert PIL Image to base64 string."""
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode()

    def _extract_words_from_text(self, text: str) -> List[Dict[str, Any]]:
        """Extract words from text with basic bounding box estimation."""
        if not text:
            return []

        words = []
        lines = text.split("\n")
        y_offset = 0

        for line_num, line in enumerate(lines):
            if not line.strip():
                y_offset += 20  # Approximate line height
                continue

            words_in_line = line.split()
            x_offset = 0

            for word in words_in_line:
                # Estimate bounding box (simplified)
                word_width = len(word) * 8  # Approximate character width
                word_height = 16  # Approximate character height

                words.append(
                    {
                        "text": word,
                        "bbox": [
                            x_offset,
                            y_offset,
                            x_offset + word_width,
                            y_offset + word_height,
                        ],
                        "confidence": 0.9,
                    }
                )

                x_offset += word_width + 5  # Add space between words

            y_offset += 20  # Move to next line

        return words

    def _parse_ocr_result(
        self, api_result: Dict[str, Any], image_size: tuple
    ) -> Dict[str, Any]:
        """Parse NeMo OCR API result."""
        try:
            # Handle new API response format
            if "text" in api_result:
                # New format: direct text and words
                text = api_result.get("text", "")
                words_data = api_result.get("words", [])
                confidence_scores = api_result.get("confidence_scores", [])

                words = []
                for word_data in words_data:
                    words.append(
                        {
                            "text": word_data.get("text", ""),
                            "bbox": word_data.get("bbox", [0, 0, 0, 0]),
                            "confidence": word_data.get("confidence", 0.0),
                        }
                    )

                # Calculate overall confidence
                overall_confidence = (
                    sum(confidence_scores) / len(confidence_scores)
                    if confidence_scores
                    else 0.0
                )

                return {"text": text, "words": words, "confidence": overall_confidence}
            else:
                # Legacy format: outputs array
                outputs = api_result.get("outputs", [])

                text = ""
                words = []
                confidence_scores = []

                for output in outputs:
                    if output.get("name") == "text":
                        text = output.get("data", [""])[0]
                    elif output.get("name") == "words":
                        words_data = output.get("data", [])
                        for word_data in words_data:
                            words.append(
                                {
                                    "text": word_data.get("text", ""),
                                    "bbox": word_data.get("bbox", [0, 0, 0, 0]),
                                    "confidence": word_data.get("confidence", 0.0),
                                }
                            )
                    elif output.get("name") == "confidence":
                        confidence_scores = output.get("data", [])

                # Calculate overall confidence
                overall_confidence = (
                    sum(confidence_scores) / len(confidence_scores)
                    if confidence_scores
                    else 0.0
                )

                return {"text": text, "words": words, "confidence": overall_confidence}

        except Exception as e:
            logger.error(f"Failed to parse OCR result: {e}")
            return {"text": "", "words": [], "confidence": 0.0}

    async def _enhance_with_layout(
        self, ocr_results: List[Dict[str, Any]], layout_result: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Enhance OCR results with layout information."""
        enhanced_results = []

        # Handle missing layout_detection key gracefully
        layout_detection = layout_result.get("layout_detection", [])

        for i, ocr_result in enumerate(ocr_results):
            page_layout = layout_detection[i] if i < len(layout_detection) else None

            enhanced_result = {
                **ocr_result,
                "layout_type": (
                    page_layout.get("layout_type", "unknown")
                    if page_layout
                    else "unknown"
                ),
                "reading_order": (
                    page_layout.get("reading_order", []) if page_layout else []
                ),
                "document_structure": (
                    page_layout.get("document_structure", {}) if page_layout else {}
                ),
                "layout_enhanced": True,
            }

            enhanced_results.append(enhanced_result)

        return enhanced_results
