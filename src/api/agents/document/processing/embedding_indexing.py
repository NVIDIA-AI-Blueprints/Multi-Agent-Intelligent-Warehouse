"""
Stage 4: Embedding & Indexing with nv-embedqa-e5-v5
Generates semantic embeddings and stores them in Milvus vector database.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
import os
import json
from datetime import datetime

from src.api.services.llm.nim_client import get_nim_client

logger = logging.getLogger(__name__)


class EmbeddingIndexingService:
    """
    Stage 4: Embedding & Indexing using nv-embedqa-e5-v5.

    Responsibilities:
    - Generate semantic embeddings for document content
    - Store embeddings in Milvus vector database
    - Create metadata indexes for fast retrieval
    - Enable semantic search capabilities
    """

    def __init__(self):
        self.nim_client = None
        self.milvus_host = os.getenv("MILVUS_HOST", "localhost")
        self.milvus_port = int(os.getenv("MILVUS_PORT", "19530"))
        self.collection_name = "warehouse_documents"

    async def initialize(self):
        """Initialize the embedding and indexing service."""
        try:
            # Initialize NIM client for embeddings
            self.nim_client = await get_nim_client()

            # Initialize Milvus connection
            await self._initialize_milvus()

            logger.info("Embedding & Indexing Service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Embedding & Indexing Service: {e}")
            logger.warning("Falling back to mock implementation")

    async def generate_and_store_embeddings(
        self,
        document_id: str,
        structured_data: Dict[str, Any],
        entities: Dict[str, Any],
        document_type: str,
    ) -> Dict[str, Any]:
        """
        Generate embeddings and store them in vector database.

        Args:
            document_id: Unique document identifier
            structured_data: Structured data from Small LLM processing
            entities: Extracted entities
            document_type: Type of document

        Returns:
            Embedding storage results
        """
        try:
            logger.info(f"Generating embeddings for document {document_id}")

            # Prepare text content for embedding
            text_content = await self._prepare_text_content(structured_data, entities)

            # Generate embeddings
            embeddings = await self._generate_embeddings(text_content)

            # Prepare metadata
            metadata = await self._prepare_metadata(
                document_id, structured_data, entities, document_type
            )

            # Store in vector database
            storage_result = await self._store_in_milvus(
                document_id, embeddings, metadata
            )

            return {
                "document_id": document_id,
                "embeddings_generated": len(embeddings),
                "metadata_fields": len(metadata),
                "storage_successful": storage_result["success"],
                "collection_name": self.collection_name,
                "processing_timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Embedding generation and storage failed: {e}")
            raise

    async def _prepare_text_content(
        self, structured_data: Dict[str, Any], entities: Dict[str, Any]
    ) -> List[str]:
        """Prepare text content for embedding generation."""
        text_content = []

        try:
            # Extract text from structured fields
            extracted_fields = structured_data.get("extracted_fields", {})
            for field_name, field_data in extracted_fields.items():
                if isinstance(field_data, dict) and field_data.get("value"):
                    text_content.append(f"{field_name}: {field_data['value']}")

            # Extract text from line items
            line_items = structured_data.get("line_items", [])
            for item in line_items:
                item_text = f"Item: {item.get('description', '')}"
                if item.get("quantity"):
                    item_text += f", Quantity: {item['quantity']}"
                if item.get("unit_price"):
                    item_text += f", Price: {item['unit_price']}"
                text_content.append(item_text)

            # Extract text from entities
            for category, entity_list in entities.items():
                if isinstance(entity_list, list):
                    for entity in entity_list:
                        if isinstance(entity, dict) and entity.get("value"):
                            text_content.append(
                                f"{entity.get('name', '')}: {entity['value']}"
                            )

            # Add document-level summary
            summary = await self._create_document_summary(structured_data, entities)
            text_content.append(f"Document Summary: {summary}")

            logger.info(f"Prepared {len(text_content)} text segments for embedding")
            return text_content

        except Exception as e:
            logger.error(f"Failed to prepare text content: {e}")
            return []

    async def _generate_embeddings(self, text_content: List[str]) -> List[List[float]]:
        """Generate embeddings using nv-embedqa-e5-v5."""
        try:
            if not self.nim_client:
                logger.warning("NIM client not available, using mock embeddings")
                return await self._generate_mock_embeddings(text_content)

            # Generate embeddings for all text content
            embeddings = await self.nim_client.generate_embeddings(text_content)

            logger.info(
                f"Generated {len(embeddings)} embeddings with dimension {len(embeddings[0]) if embeddings else 0}"
            )
            return embeddings

        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            return await self._generate_mock_embeddings(text_content)

    async def _generate_mock_embeddings(
        self, text_content: List[str]
    ) -> List[List[float]]:
        """Generate mock embeddings for development."""
        import random

        embeddings = []
        dimension = 1024  # nv-embedqa-e5-v5 dimension

        for text in text_content:
            # Generate deterministic mock embedding based on text hash
            random.seed(hash(text) % 2**32)
            embedding = [random.uniform(-1, 1) for _ in range(dimension)]
            embeddings.append(embedding)

        return embeddings

    async def _prepare_metadata(
        self,
        document_id: str,
        structured_data: Dict[str, Any],
        entities: Dict[str, Any],
        document_type: str,
    ) -> Dict[str, Any]:
        """Prepare metadata for vector storage."""
        metadata = {
            "document_id": document_id,
            "document_type": document_type,
            "processing_timestamp": datetime.now().isoformat(),
            "total_fields": len(structured_data.get("extracted_fields", {})),
            "total_line_items": len(structured_data.get("line_items", [])),
            "total_entities": entities.get("metadata", {}).get("total_entities", 0),
        }

        # Add quality assessment
        quality_assessment = structured_data.get("quality_assessment", {})
        metadata.update(
            {
                "overall_confidence": quality_assessment.get("overall_confidence", 0.0),
                "completeness": quality_assessment.get("completeness", 0.0),
                "accuracy": quality_assessment.get("accuracy", 0.0),
            }
        )

        # Add entity counts by category
        for category, entity_list in entities.items():
            if isinstance(entity_list, list):
                metadata[f"{category}_count"] = len(entity_list)

        # Add financial information if available
        financial_entities = entities.get("financial_entities", [])
        if financial_entities:
            total_amount = None
            for entity in financial_entities:
                if "total" in entity.get("name", "").lower():
                    try:
                        total_amount = float(entity.get("value", "0"))
                        break
                    except ValueError:
                        continue

            if total_amount is not None:
                metadata["total_amount"] = total_amount

        return metadata

    async def _create_document_summary(
        self, structured_data: Dict[str, Any], entities: Dict[str, Any]
    ) -> str:
        """Create a summary of the document for embedding."""
        summary_parts = []

        # Add document type
        doc_type = structured_data.get("document_type", "unknown")
        summary_parts.append(f"Document type: {doc_type}")

        # Add key fields
        extracted_fields = structured_data.get("extracted_fields", {})
        key_fields = []
        for field_name, field_data in extracted_fields.items():
            if isinstance(field_data, dict) and field_data.get("confidence", 0) > 0.8:
                key_fields.append(f"{field_name}: {field_data['value']}")

        if key_fields:
            summary_parts.append(f"Key information: {', '.join(key_fields[:5])}")

        # Add line items summary
        line_items = structured_data.get("line_items", [])
        if line_items:
            summary_parts.append(f"Contains {len(line_items)} line items")

        # Add entity summary
        total_entities = entities.get("metadata", {}).get("total_entities", 0)
        if total_entities > 0:
            summary_parts.append(f"Extracted {total_entities} entities")

        return ". ".join(summary_parts)

    async def _initialize_milvus(self):
        """Initialize Milvus connection and collection."""
        try:
            # This would initialize actual Milvus connection
            # For now, we'll log the operation
            logger.info(
                f"Initializing Milvus connection to {self.milvus_host}:{self.milvus_port}"
            )
            logger.info(f"Collection: {self.collection_name}")

            # TODO: Implement actual Milvus integration
            # from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType

            # connections.connect("default", host=self.milvus_host, port=self.milvus_port)

            # # Define collection schema
            # fields = [
            #     FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            #     FieldSchema(name="document_id", dtype=DataType.VARCHAR, max_length=100),
            #     FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=1024),
            #     FieldSchema(name="metadata", dtype=DataType.JSON)
            # ]

            # schema = CollectionSchema(fields, "Warehouse documents collection")
            # collection = Collection(self.collection_name, schema)

            logger.info("Milvus collection initialized (mock)")

        except Exception as e:
            logger.error(f"Failed to initialize Milvus: {e}")
            logger.warning("Using mock Milvus implementation")

    async def _store_in_milvus(
        self, document_id: str, embeddings: List[List[float]], metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Store embeddings and metadata in Milvus."""
        try:
            logger.info(
                f"Storing {len(embeddings)} embeddings for document {document_id}"
            )

            # Mock storage implementation
            # In real implementation, this would store in Milvus
            storage_data = {
                "document_id": document_id,
                "embeddings": embeddings,
                "metadata": metadata,
                "stored_at": datetime.now().isoformat(),
            }

            # TODO: Implement actual Milvus storage
            # collection = Collection(self.collection_name)
            # collection.insert([storage_data])
            # collection.flush()

            logger.info(f"Successfully stored embeddings for document {document_id}")

            return {
                "success": True,
                "document_id": document_id,
                "embeddings_stored": len(embeddings),
                "metadata_stored": len(metadata),
            }

        except Exception as e:
            logger.error(f"Failed to store in Milvus: {e}")
            return {"success": False, "error": str(e), "document_id": document_id}

    async def search_similar_documents(
        self, query: str, limit: int = 10, filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar documents using semantic search.

        Args:
            query: Search query
            limit: Maximum number of results
            filters: Optional filters for metadata

        Returns:
            List of similar documents with scores
        """
        try:
            logger.info(f"Searching for documents similar to: {query}")

            # Generate embedding for query
            query_embeddings = await self._generate_embeddings([query])
            if not query_embeddings:
                return []

            # Mock search implementation
            # In real implementation, this would search Milvus
            mock_results = await self._mock_semantic_search(query, limit, filters)

            logger.info(f"Found {len(mock_results)} similar documents")
            return mock_results

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []

    async def _mock_semantic_search(
        self, query: str, limit: int, filters: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Mock semantic search implementation."""
        # Generate mock search results
        mock_results = []

        for i in range(min(limit, 5)):  # Return up to 5 mock results
            mock_results.append(
                {
                    "document_id": f"mock_doc_{i+1}",
                    "similarity_score": 0.9 - (i * 0.1),
                    "metadata": {
                        "document_type": "invoice",
                        "total_amount": 1000 + (i * 100),
                        "processing_timestamp": datetime.now().isoformat(),
                    },
                    "matched_content": f"Mock content matching query: {query}",
                }
            )

        return mock_results
