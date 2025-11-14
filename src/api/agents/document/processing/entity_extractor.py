"""
Entity Extractor for Document Processing
Extracts and normalizes entities from structured document data.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
import re
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ExtractedEntity:
    """Represents an extracted entity."""

    name: str
    value: str
    entity_type: str
    confidence: float
    source: str
    normalized_value: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class EntityExtractor:
    """
    Entity Extractor for document processing.

    Responsibilities:
    - Extract entities from structured document data
    - Normalize entity values
    - Validate entity formats
    - Categorize entities by type
    """

    def __init__(self):
        self.entity_patterns = self._initialize_entity_patterns()

    async def initialize(self):
        """Initialize the entity extractor."""
        logger.info("Entity Extractor initialized successfully")

    async def extract_entities(
        self, structured_data: Dict[str, Any], document_type: str
    ) -> Dict[str, Any]:
        """
        Extract entities from structured document data.

        Args:
            structured_data: Structured data from Small LLM processing
            document_type: Type of document

        Returns:
            Dictionary containing extracted and normalized entities
        """
        try:
            logger.info(f"Extracting entities from {document_type} document")

            entities = {
                "financial_entities": [],
                "temporal_entities": [],
                "address_entities": [],
                "identifier_entities": [],
                "product_entities": [],
                "contact_entities": [],
                "metadata": {
                    "document_type": document_type,
                    "extraction_timestamp": datetime.now().isoformat(),
                    "total_entities": 0,
                },
            }

            # Extract from structured fields
            extracted_fields = structured_data.get("extracted_fields", {})
            for field_name, field_data in extracted_fields.items():
                entity = await self._extract_field_entity(
                    field_name, field_data, document_type
                )
                if entity:
                    entities = self._categorize_entity(entity, entities)

            # Extract from line items
            line_items = structured_data.get("line_items", [])
            for item in line_items:
                product_entities = await self._extract_product_entities(item)
                entities["product_entities"].extend(product_entities)

            # Calculate total entities
            total_entities = sum(
                len(entity_list)
                for entity_list in entities.values()
                if isinstance(entity_list, list)
            )
            entities["metadata"]["total_entities"] = total_entities

            logger.info(f"Extracted {total_entities} entities")
            return entities

        except Exception as e:
            logger.error(f"Entity extraction failed: {e}")
            raise

    async def _extract_field_entity(
        self, field_name: str, field_data: Dict[str, Any], document_type: str
    ) -> Optional[ExtractedEntity]:
        """Extract entity from a single field."""
        try:
            value = field_data.get("value", "")
            confidence = field_data.get("confidence", 0.5)
            source = field_data.get("source", "unknown")

            if not value:
                return None

            # Determine entity type based on field name and value
            entity_type = self._determine_entity_type(field_name, value)

            # Normalize the value
            normalized_value = await self._normalize_entity_value(value, entity_type)

            # Extract metadata
            metadata = await self._extract_entity_metadata(
                value, entity_type, document_type
            )

            return ExtractedEntity(
                name=field_name,
                value=value,
                entity_type=entity_type,
                confidence=confidence,
                source=source,
                normalized_value=normalized_value,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"Failed to extract entity from field {field_name}: {e}")
            return None

    def _determine_entity_type(self, field_name: str, value: str) -> str:
        """Determine the type of entity based on field name and value."""
        field_name_lower = field_name.lower()
        value_lower = value.lower()

        # Financial entities
        if any(
            keyword in field_name_lower
            for keyword in ["amount", "total", "price", "cost", "value"]
        ):
            return "financial"
        elif any(keyword in field_name_lower for keyword in ["tax", "fee", "charge"]):
            return "financial"
        elif re.match(r"^\$?[\d,]+\.?\d*$", value.strip()):
            return "financial"

        # Temporal entities
        elif any(
            keyword in field_name_lower
            for keyword in ["date", "time", "due", "created", "issued"]
        ):
            return "temporal"
        elif re.match(r"\d{4}-\d{2}-\d{2}", value.strip()):
            return "temporal"
        elif re.match(r"\d{1,2}/\d{1,2}/\d{4}", value.strip()):
            return "temporal"

        # Address entities
        elif any(
            keyword in field_name_lower
            for keyword in ["address", "location", "street", "city", "state", "zip"]
        ):
            return "address"
        elif re.search(
            r"\d+\s+\w+\s+(street|st|avenue|ave|road|rd|boulevard|blvd)", value_lower
        ):
            return "address"

        # Identifier entities
        elif any(
            keyword in field_name_lower
            for keyword in ["number", "id", "code", "reference"]
        ):
            return "identifier"
        elif re.match(r"^[A-Z]{2,4}-\d{3,6}$", value.strip()):
            return "identifier"

        # Contact entities
        elif any(
            keyword in field_name_lower
            for keyword in ["name", "company", "vendor", "supplier", "customer"]
        ):
            return "contact"
        elif "@" in value and "." in value:
            return "contact"

        # Product entities
        elif any(
            keyword in field_name_lower
            for keyword in ["item", "product", "description", "sku"]
        ):
            return "product"

        else:
            return "general"

    async def _normalize_entity_value(self, value: str, entity_type: str) -> str:
        """Normalize entity value based on its type."""
        try:
            if entity_type == "financial":
                # Remove currency symbols and normalize decimal places
                normalized = re.sub(r"[^\d.,]", "", value)
                normalized = normalized.replace(",", "")
                try:
                    float_val = float(normalized)
                    return f"{float_val:.2f}"
                except ValueError:
                    return value

            elif entity_type == "temporal":
                # Normalize date formats
                date_patterns = [
                    (r"(\d{4})-(\d{2})-(\d{2})", r"\1-\2-\3"),  # YYYY-MM-DD
                    (
                        r"(\d{1,2})/(\d{1,2})/(\d{4})",
                        r"\3-\1-\2",
                    ),  # MM/DD/YYYY -> YYYY-MM-DD
                    (
                        r"(\d{1,2})-(\d{1,2})-(\d{4})",
                        r"\3-\1-\2",
                    ),  # MM-DD-YYYY -> YYYY-MM-DD
                ]

                for pattern, replacement in date_patterns:
                    if re.match(pattern, value.strip()):
                        return re.sub(pattern, replacement, value.strip())
                return value

            elif entity_type == "identifier":
                # Normalize identifier formats
                return value.strip().upper()

            elif entity_type == "contact":
                # Normalize contact information
                return value.strip().title()

            else:
                return value.strip()

        except Exception as e:
            logger.error(f"Failed to normalize entity value: {e}")
            return value

    async def _extract_entity_metadata(
        self, value: str, entity_type: str, document_type: str
    ) -> Dict[str, Any]:
        """Extract metadata for an entity."""
        metadata = {
            "entity_type": entity_type,
            "document_type": document_type,
            "extraction_timestamp": datetime.now().isoformat(),
        }

        if entity_type == "financial":
            metadata.update(
                {
                    "currency_detected": "$" in value or "€" in value or "£" in value,
                    "has_decimal": "." in value,
                    "is_negative": "-" in value or "(" in value,
                }
            )

        elif entity_type == "temporal":
            metadata.update(
                {
                    "format_detected": self._detect_date_format(value),
                    "is_future_date": self._is_future_date(value),
                }
            )

        elif entity_type == "address":
            metadata.update(
                {
                    "has_street_number": bool(re.search(r"^\d+", value)),
                    "has_zip_code": bool(re.search(r"\d{5}(-\d{4})?", value)),
                    "components": self._parse_address_components(value),
                }
            )

        elif entity_type == "identifier":
            metadata.update(
                {
                    "prefix": self._extract_id_prefix(value),
                    "length": len(value),
                    "has_numbers": bool(re.search(r"\d", value)),
                }
            )

        return metadata

    def _detect_date_format(self, value: str) -> str:
        """Detect the format of a date string."""
        if re.match(r"\d{4}-\d{2}-\d{2}", value):
            return "ISO"
        elif re.match(r"\d{1,2}/\d{1,2}/\d{4}", value):
            return "US"
        elif re.match(r"\d{1,2}-\d{1,2}-\d{4}", value):
            return "US_DASH"
        else:
            return "UNKNOWN"

    def _is_future_date(self, value: str) -> bool:
        """Check if a date is in the future."""
        try:
            from datetime import datetime

            # Try to parse the date
            date_formats = ["%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y"]

            for fmt in date_formats:
                try:
                    parsed_date = datetime.strptime(value.strip(), fmt)
                    return parsed_date > datetime.now()
                except ValueError:
                    continue

            return False
        except Exception:
            return False

    def _parse_address_components(self, value: str) -> Dict[str, str]:
        """Parse address into components."""
        components = {"street": "", "city": "", "state": "", "zip": ""}

        # Simple address parsing (can be enhanced)
        parts = value.split(",")
        if len(parts) >= 2:
            components["street"] = parts[0].strip()
            components["city"] = parts[1].strip()

            if len(parts) >= 3:
                state_zip = parts[2].strip()
                zip_match = re.search(r"(\d{5}(-\d{4})?)", state_zip)
                if zip_match:
                    components["zip"] = zip_match.group(1)
                    components["state"] = state_zip.replace(
                        zip_match.group(1), ""
                    ).strip()

        return components

    def _extract_id_prefix(self, value: str) -> str:
        """Extract prefix from an identifier."""
        match = re.match(r"^([A-Z]{2,4})", value)
        return match.group(1) if match else ""

    async def _extract_product_entities(
        self, item: Dict[str, Any]
    ) -> List[ExtractedEntity]:
        """Extract entities from line items."""
        entities = []

        try:
            # Extract product description
            description = item.get("description", "")
            if description:
                entities.append(
                    ExtractedEntity(
                        name="product_description",
                        value=description,
                        entity_type="product",
                        confidence=item.get("confidence", 0.5),
                        source="line_item",
                        normalized_value=description.strip(),
                        metadata={
                            "quantity": item.get("quantity", 0),
                            "unit_price": item.get("unit_price", 0),
                            "total": item.get("total", 0),
                        },
                    )
                )

            # Extract SKU if present
            sku_match = re.search(r"[A-Z]{2,4}\d{3,6}", description)
            if sku_match:
                entities.append(
                    ExtractedEntity(
                        name="sku",
                        value=sku_match.group(),
                        entity_type="identifier",
                        confidence=0.9,
                        source="line_item",
                        normalized_value=sku_match.group(),
                        metadata={"extracted_from": "description"},
                    )
                )

        except Exception as e:
            logger.error(f"Failed to extract product entities: {e}")

        return entities

    def _categorize_entity(
        self, entity: ExtractedEntity, entities: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Categorize entity into the appropriate category."""
        category_map = {
            "financial": "financial_entities",
            "temporal": "temporal_entities",
            "address": "address_entities",
            "identifier": "identifier_entities",
            "product": "product_entities",
            "contact": "contact_entities",
        }

        category = category_map.get(entity.entity_type, "general_entities")

        if category not in entities:
            entities[category] = []

        entities[category].append(
            {
                "name": entity.name,
                "value": entity.value,
                "entity_type": entity.entity_type,
                "confidence": entity.confidence,
                "source": entity.source,
                "normalized_value": entity.normalized_value,
                "metadata": entity.metadata,
            }
        )

        return entities

    def _initialize_entity_patterns(self) -> Dict[str, List[str]]:
        """Initialize regex patterns for entity detection."""
        return {
            "financial": [
                r"\$?[\d,]+\.?\d*",
                r"[\d,]+\.?\d*\s*(dollars?|USD|EUR|GBP)",
                r"total[:\s]*\$?[\d,]+\.?\d*",
            ],
            "temporal": [
                r"\d{4}-\d{2}-\d{2}",
                r"\d{1,2}/\d{1,2}/\d{4}",
                r"\d{1,2}-\d{1,2}-\d{4}",
                r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{1,2},?\s+\d{4}",
            ],
            "address": [
                r"\d+\s+\w+\s+(street|st|avenue|ave|road|rd|boulevard|blvd)",
                r"\d{5}(-\d{4})?",
                r"[A-Z]{2}\s+\d{5}",
            ],
            "identifier": [r"[A-Z]{2,4}-\d{3,6}", r"#?\d{6,}", r"[A-Z]{2,4}\d{3,6}"],
            "email": [r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"],
            "phone": [
                r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
                r"\+\d{1,3}[-.\s]?\d{3,4}[-.\s]?\d{3,4}[-.\s]?\d{3,4}",
            ],
        }
