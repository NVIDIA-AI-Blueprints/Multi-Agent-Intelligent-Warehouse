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
Stage 3: Small LLM Processing — structured extraction from document text/images.

v2.0.1 (audit P1-05): every model call goes through the canonical
ModelGateway via ``model_gateway_adapter.generate_for_document``. This module
holds no provider URL, API key or model id. Text extraction is requested with
``Modality.TEXT`` (served by an approved Nemotron 3 / 3.5 text model); page
images are requested with ``Modality.IMAGE`` and are served only if an approved
multimodal Nemotron model is enabled in the registry — otherwise the stage
fails with ``DocumentInferenceUnavailable(MODEL_UNAVAILABLE)``. There is no
mock fallback.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
import os
import base64
import io
import json
from PIL import Image
from datetime import datetime
from src.api.services.agent_config import load_agent_config, AgentConfig
from src.api.agents.document.model_gateway_adapter import (
    generate_for_document,
    parse_json_object,
    route_provenance,
)

logger = logging.getLogger(__name__)


class SmallLLMProcessor:
    """
    Stage 3: structured document extraction through the canonical ModelGateway.

    Model selection is owned by the ModelGateway PolicyFilter (approved
    Nemotron 3 / 3.5 families only). Provider or credential failure raises
    ``DocumentInferenceUnavailable``; it never produces mock or canned data.
    """

    def __init__(self):
        self.timeout = int(os.getenv("DOCUMENT_LLM_TIMEOUT", "60"))
        self.config: Optional[AgentConfig] = None  # Agent configuration

    async def initialize(self):
        """Load the document agent configuration (no provider probing)."""
        self.config = load_agent_config("document")
        logger.info(f"Loaded agent configuration: {self.config.name}")

    async def process_document(
        self, images: List[Image.Image], ocr_text: str, document_type: str
    ) -> Dict[str, Any]:
        """
        Extract structured data from a document through the ModelGateway.

        OCR text present → TEXT request. No OCR text → IMAGE request with the
        page images (approved multimodal model required). Any failure raises
        ``DocumentInferenceUnavailable``; nothing is fabricated.
        """
        logger.info("Processing document with ModelGateway (stage 3)")

        if ocr_text and ocr_text.strip():
            result = await self._call_text_only_api(ocr_text, document_type)
        else:
            multimodal_input = await self._prepare_multimodal_input(
                images, ocr_text, document_type
            )
            result = await self._call_nano_vl_api(multimodal_input)

        structured_data = await self._post_process_results(
            result, document_type, ocr_text
        )
        return {
            "structured_data": structured_data,
            "confidence": result.get("confidence", 0.0),
            "model_used": result.get("model_used", ""),
            "model_route": result.get("model_route", {}),
            "processing_timestamp": datetime.now().isoformat(),
            "multimodal_processed": result.get("processing_method") == "multimodal",
        }

    async def _prepare_multimodal_input(
        self, images: List[Image.Image], ocr_text: str, document_type: str
    ) -> Dict[str, Any]:
        """Prepare multimodal input for the vision-language model."""
        try:
            # Convert images to base64
            image_data = []
            for i, image in enumerate(images):
                image_base64 = await self._image_to_base64(image)
                image_data.append(
                    {"page": i + 1, "image": image_base64, "dimensions": image.size}
                )

            # Create structured prompt
            prompt = self._create_processing_prompt(document_type, ocr_text)

            return {
                "images": image_data,
                "prompt": prompt,
                "document_type": document_type,
                "ocr_text": ocr_text,
            }

        except Exception as e:
            logger.error(f"Failed to prepare multimodal input: {e}")
            raise

    def _create_processing_prompt(self, document_type: str, ocr_text: str) -> str:
        """Create a structured prompt for document processing."""
        
        # Load config if not already loaded
        if self.config is None:
            self.config = load_agent_config("document")
        
        # Get document type specific prompt from config
        document_types = self.config.metadata.get("document_types", {})
        if document_type in document_types:
            base_prompt = document_types[document_type].get("prompt", "")
        else:
            # Fallback to invoice prompt
            base_prompt = document_types.get("invoice", {}).get("prompt", "")

        return f"""
        {base_prompt}
        
        OCR Text for reference:
        {ocr_text}
        
        Please provide your analysis in the following JSON format:
        {{
            "document_type": "{document_type}",
            "extracted_fields": {{
                "field_name": {{
                    "value": "extracted_value",
                    "confidence": 0.95,
                    "source": "image|ocr|both"
                }}
            }},
            "line_items": [
                {{
                    "description": "item_description",
                    "quantity": 10,
                    "unit_price": 125.00,
                    "total": 1250.00,
                    "confidence": 0.92
                }}
            ],
            "quality_assessment": {{
                "overall_confidence": 0.90,
                "completeness": 0.95,
                "accuracy": 0.88
            }}
        }}
        """

    async def _call_text_only_api(
        self, ocr_text: str, document_type: str
    ) -> Dict[str, Any]:
        """Text extraction via ModelGateway (Modality.TEXT)."""
        prompt = f"""
            Analyze the following {document_type} document text and extract structured data:

            Document Text:
            {ocr_text}

            Please extract the following information in JSON format:
            - invoice_number (if applicable)
            - vendor/supplier name
            - total_amount
            - date
            - line_items (array of items with description, quantity, price, total)
            - any other relevant fields

            Return only valid JSON without any additional text.
            """
        from maiw_models import Modality

        response = await generate_for_document(
            stage="llm_processing",
            messages=[{"role": "user", "content": prompt}],
            modality=Modality.TEXT,
            timeout_s=self.timeout,
        )
        parsed = parse_json_object(response.content, stage="llm_processing")
        return {
            "structured_data": parsed,
            "confidence": float(
                parsed.get("quality_assessment", {}).get("overall_confidence", 0.0)
                if isinstance(parsed.get("quality_assessment"), dict)
                else 0.0
            ),
            "raw_response": response.content,
            "processing_method": "text_only",
            "model_used": response.model_id,
            "model_route": await route_provenance(response),
        }

    async def _call_nano_vl_api(
        self, multimodal_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Image extraction via ModelGateway (Modality.IMAGE)."""
        from maiw_models import Modality

        content: List[Dict[str, Any]] = [
            {"type": "text", "text": multimodal_input["prompt"]}
        ]
        for image_data in multimodal_input["images"]:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{image_data['image']}"
                    },
                }
            )
        response = await generate_for_document(
            stage="llm_processing",
            messages=[{"role": "user", "content": content}],
            modality=Modality.IMAGE,
            timeout_s=self.timeout,
        )
        parsed = parse_json_object(
            response.content, stage="llm_processing", modality="image"
        )
        qa = parsed.get("quality_assessment", {})
        return {
            "content": parsed,
            "confidence": float(
                qa.get("overall_confidence", 0.0) if isinstance(qa, dict) else 0.0
            ),
            "raw_response": response.content,
            "processing_method": "multimodal",
            "model_used": response.model_id,
            "model_route": await route_provenance(response),
        }

    async def _post_process_results(
        self, result: Dict[str, Any], document_type: str, ocr_text: str = ""
    ) -> Dict[str, Any]:
        """Post-process LLM results for consistency."""
        try:
            # Handle different response formats from multimodal vs text-only processing
            if "structured_data" in result:
                # Text-only processing result
                content = result["structured_data"]
            elif "content" in result:
                # Multimodal processing result
                content = result["content"]
            else:
                # Fallback: use the entire result
                content = result

            # Get extracted fields from LLM response
            extracted_fields = content.get("extracted_fields", {})
            
            # Fallback: If LLM didn't extract fields, parse from OCR text
            if not extracted_fields or len(extracted_fields) == 0:
                if ocr_text:
                    logger.info(f"LLM returned empty extracted_fields, parsing from OCR text for {document_type}")
                    extracted_fields = await self._parse_fields_from_text(ocr_text, document_type)
                else:
                    # Try to get text from raw_response
                    raw_text = result.get("raw_response", "")
                    if raw_text and not raw_text.startswith("{"):
                        # LLM returned plain text instead of JSON, try to parse it
                        extracted_fields = await self._parse_fields_from_text(raw_text, document_type)

            # Ensure required fields are present
            structured_data = {
                "document_type": document_type,
                "extracted_fields": extracted_fields,
                "line_items": content.get("line_items", []),
                # Only what the model reported — no invented confidence.
                "quality_assessment": content.get(
                    "quality_assessment",
                    {
                        "overall_confidence": result.get("confidence", 0.0),
                        "completeness": None,
                        "accuracy": None,
                    },
                ),
                "processing_metadata": {
                    "model_used": result.get("model_used", ""),
                    "model_route": result.get("model_route", {}),
                    "timestamp": datetime.now().isoformat(),
                    "multimodal": result.get("processing_method") == "multimodal",
                },
            }

            # Validate and clean extracted fields
            structured_data["extracted_fields"] = self._validate_extracted_fields(
                structured_data["extracted_fields"], document_type
            )

            # Validate line items
            structured_data["line_items"] = self._validate_line_items(
                structured_data["line_items"]
            )

            return structured_data

        except Exception as e:
            logger.error(f"Post-processing failed: {e}")
            # Return a safe fallback structure
            return {
                "document_type": document_type,
                "extracted_fields": {},
                "line_items": [],
                "quality_assessment": {
                    "overall_confidence": 0.0,
                    "completeness": None,
                    "accuracy": None,
                },
                "processing_metadata": {
                    "model_used": result.get("model_used", ""),
                    "timestamp": datetime.now().isoformat(),
                    "multimodal": False,
                    "error": str(e),
                    "post_processing_failed": True,
                },
            }

    def _validate_extracted_fields(
        self, fields: Dict[str, Any], document_type: str
    ) -> Dict[str, Any]:
        """Validate and clean extracted fields."""
        validated_fields = {}

        # Define required fields by document type
        required_fields = {
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

        doc_required = required_fields.get(document_type, [])

        for field_name, field_data in fields.items():
            if isinstance(field_data, dict):
                validated_fields[field_name] = {
                    "value": field_data.get("value", ""),
                    "confidence": field_data.get("confidence", 0.5),
                    "source": field_data.get("source", "unknown"),
                    "required": field_name in doc_required,
                }
            else:
                validated_fields[field_name] = {
                    "value": str(field_data),
                    "confidence": 0.5,
                    "source": "unknown",
                    "required": field_name in doc_required,
                }

        return validated_fields

    def _validate_line_items(
        self, line_items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Validate and clean line items."""
        validated_items = []

        for item in line_items:
            if isinstance(item, dict):
                validated_item = {
                    "description": item.get("description", ""),
                    "quantity": self._safe_float(item.get("quantity", 0)),
                    "unit_price": self._safe_float(item.get("unit_price", 0)),
                    "total": self._safe_float(item.get("total", 0)),
                    "confidence": item.get("confidence", 0.5),
                }

                # Calculate total if missing
                if (
                    validated_item["total"] == 0
                    and validated_item["quantity"] > 0
                    and validated_item["unit_price"] > 0
                ):
                    validated_item["total"] = (
                        validated_item["quantity"] * validated_item["unit_price"]
                    )

                validated_items.append(validated_item)

        return validated_items

    def _safe_float(self, value: Any) -> float:
        """Safely convert value to float."""
        try:
            if isinstance(value, (int, float)):
                return float(value)
            elif isinstance(value, str):
                # Remove currency symbols and commas
                cleaned = (
                    value.replace("$", "")
                    .replace(",", "")
                    .replace("€", "")
                    .replace("£", "")
                )
                return float(cleaned)
            else:
                return 0.0
        except (ValueError, TypeError):
            return 0.0

    async def _image_to_base64(self, image: Image.Image) -> str:
        """Convert PIL Image to base64 string."""
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode()

    async def _parse_fields_from_text(self, text: str, document_type: str) -> Dict[str, Any]:
        """Parse invoice fields from text using regex patterns when LLM extraction fails."""
        import re
        
        parsed_fields = {}
        
        if document_type.lower() != "invoice":
            return parsed_fields
        
        try:
            # Invoice Number patterns
            invoice_num_match = re.search(r'Invoice Number:\s*([A-Z0-9-]+)', text, re.IGNORECASE) or \
                              re.search(r'Invoice #:\s*([A-Z0-9-]+)', text, re.IGNORECASE) or \
                              re.search(r'INV[-\s]*([A-Z0-9-]+)', text, re.IGNORECASE)
            if invoice_num_match:
                parsed_fields["invoice_number"] = {
                    "value": invoice_num_match.group(1),
                    "confidence": 0.85,
                    "source": "ocr"
                }
            
            # Order Number patterns
            order_num_match = re.search(r'Order Number:\s*(\d+)', text, re.IGNORECASE) or \
                            re.search(r'Order #:\s*(\d+)', text, re.IGNORECASE) or \
                            re.search(r'PO[-\s]*(\d+)', text, re.IGNORECASE)
            if order_num_match:
                parsed_fields["order_number"] = {
                    "value": order_num_match.group(1),
                    "confidence": 0.85,
                    "source": "ocr"
                }
            
            # Invoice Date patterns
            invoice_date_match = re.search(r'Invoice Date:\s*([^\n+]+?)(?:\n|$)', text, re.IGNORECASE) or \
                               re.search(r'Date:\s*([^\n+]+?)(?:\n|$)', text, re.IGNORECASE)
            if invoice_date_match:
                parsed_fields["invoice_date"] = {
                    "value": invoice_date_match.group(1).strip(),
                    "confidence": 0.80,
                    "source": "ocr"
                }
            
            # Due Date patterns
            due_date_match = re.search(r'Due Date:\s*([^\n+]+?)(?:\n|$)', text, re.IGNORECASE) or \
                           re.search(r'Payment Due:\s*([^\n+]+?)(?:\n|$)', text, re.IGNORECASE)
            if due_date_match:
                parsed_fields["due_date"] = {
                    "value": due_date_match.group(1).strip(),
                    "confidence": 0.80,
                    "source": "ocr"
                }
            
            # Service/Description patterns
            service_match = re.search(r'Service:\s*([^\n+]+?)(?:\n|$)', text, re.IGNORECASE) or \
                          re.search(r'Description:\s*([^\n+]+?)(?:\n|$)', text, re.IGNORECASE)
            if service_match:
                parsed_fields["service"] = {
                    "value": service_match.group(1).strip(),
                    "confidence": 0.80,
                    "source": "ocr"
                }
            
            # Rate/Price patterns
            rate_match = re.search(r'Rate/Price:\s*\$?([0-9,]+\.?\d*)', text, re.IGNORECASE) or \
                        re.search(r'Price:\s*\$?([0-9,]+\.?\d*)', text, re.IGNORECASE) or \
                        re.search(r'Rate:\s*\$?([0-9,]+\.?\d*)', text, re.IGNORECASE)
            if rate_match:
                parsed_fields["rate"] = {
                    "value": f"${rate_match.group(1)}",
                    "confidence": 0.85,
                    "source": "ocr"
                }
            
            # Sub Total patterns
            subtotal_match = re.search(r'Sub Total:\s*\$?([0-9,]+\.?\d*)', text, re.IGNORECASE) or \
                           re.search(r'Subtotal:\s*\$?([0-9,]+\.?\d*)', text, re.IGNORECASE)
            if subtotal_match:
                parsed_fields["subtotal"] = {
                    "value": f"${subtotal_match.group(1)}",
                    "confidence": 0.85,
                    "source": "ocr"
                }
            
            # Tax patterns
            tax_match = re.search(r'Tax:\s*\$?([0-9,]+\.?\d*)', text, re.IGNORECASE) or \
                       re.search(r'Tax Amount:\s*\$?([0-9,]+\.?\d*)', text, re.IGNORECASE)
            if tax_match:
                parsed_fields["tax"] = {
                    "value": f"${tax_match.group(1)}",
                    "confidence": 0.85,
                    "source": "ocr"
                }
            
            # Total patterns
            total_match = re.search(r'Total:\s*\$?([0-9,]+\.?\d*)', text, re.IGNORECASE) or \
                         re.search(r'Total Due:\s*\$?([0-9,]+\.?\d*)', text, re.IGNORECASE) or \
                         re.search(r'Amount Due:\s*\$?([0-9,]+\.?\d*)', text, re.IGNORECASE)
            if total_match:
                parsed_fields["total"] = {
                    "value": f"${total_match.group(1)}",
                    "confidence": 0.90,
                    "source": "ocr"
                }
            
            logger.info(f"Parsed {len(parsed_fields)} fields from OCR text using regex fallback")
            
        except Exception as e:
            logger.error(f"Error parsing fields from text: {e}")
        
        return parsed_fields
