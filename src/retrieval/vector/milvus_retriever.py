"""
Milvus Vector Retriever for Warehouse Operations

Provides semantic search capabilities over warehouse documentation,
SOPs, manuals, and other unstructured content using Milvus vector database.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import numpy as np
from pymilvus import (
    connections, Collection, CollectionSchema, FieldSchema, DataType,
    utility, Index, MilvusException
)
import os
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

@dataclass
class MilvusConfig:
    """Milvus configuration for warehouse operations."""
    host: str = os.getenv("MILVUS_HOST", "localhost")
    port: str = os.getenv("MILVUS_PORT", "19530")
    collection_name: str = "warehouse_docs"
    dimension: int = 1024  # NV-EmbedQA-E5-v5 embedding dimension
    index_type: str = "IVF_FLAT"
    metric_type: str = "L2"

@dataclass
class SearchResult:
    """Search result from vector database."""
    id: str
    content: str
    metadata: Dict[str, Any]
    score: float
    distance: float

class MilvusRetriever:
    """
    Milvus-based vector retriever for warehouse operations.
    
    Provides semantic search capabilities over warehouse documentation
    and operational procedures with similarity scoring.
    """
    
    def __init__(self, config: Optional[MilvusConfig] = None):
        self.config = config or MilvusConfig()
        self.collection: Optional[Collection] = None
        self._connected = False
    
    async def connect(self) -> None:
        """Connect to Milvus server."""
        try:
            connections.connect(
                alias="default",
                host=self.config.host,
                port=self.config.port
            )
            self._connected = True
            logger.info(f"Connected to Milvus at {self.config.host}:{self.config.port}")
        except Exception as e:
            logger.error(f"Failed to connect to Milvus: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Disconnect from Milvus server."""
        try:
            if self._connected:
                connections.disconnect("default")
                self._connected = False
                logger.info("Disconnected from Milvus")
        except Exception as e:
            logger.error(f"Error disconnecting from Milvus: {e}")
    
    async def create_collection(self) -> None:
        """Create the warehouse documents collection if it doesn't exist."""
        try:
            if not self._connected:
                await self.connect()
            
            # Check if collection exists
            if utility.has_collection(self.config.collection_name):
                logger.info(f"Collection {self.config.collection_name} already exists")
                self.collection = Collection(self.config.collection_name)
                return
            
            # Define collection schema
            fields = [
                FieldSchema(
                    name="id",
                    dtype=DataType.VARCHAR,
                    is_primary=True,
                    max_length=100
                ),
                FieldSchema(
                    name="content",
                    dtype=DataType.VARCHAR,
                    max_length=65535
                ),
                FieldSchema(
                    name="embedding",
                    dtype=DataType.FLOAT_VECTOR,
                    dim=self.config.dimension
                ),
                FieldSchema(
                    name="doc_type",
                    dtype=DataType.VARCHAR,
                    max_length=50
                ),
                FieldSchema(
                    name="category",
                    dtype=DataType.VARCHAR,
                    max_length=100
                ),
                FieldSchema(
                    name="created_at",
                    dtype=DataType.VARCHAR,
                    max_length=50
                )
            ]
            
            schema = CollectionSchema(
                fields=fields,
                description="Warehouse operational documents and procedures"
            )
            
            # Create collection
            self.collection = Collection(
                name=self.config.collection_name,
                schema=schema
            )
            
            # Create index for vector field
            index_params = {
                "metric_type": self.config.metric_type,
                "index_type": self.config.index_type,
                "params": {"nlist": 1024}
            }
            
            self.collection.create_index(
                field_name="embedding",
                index_params=index_params
            )
            
            logger.info(f"Created collection {self.config.collection_name} with index")
            
        except Exception as e:
            logger.error(f"Failed to create collection: {e}")
            raise
    
    async def load_collection(self) -> None:
        """Load collection into memory for search operations."""
        try:
            if not self.collection:
                await self.create_collection()
            
            self.collection.load()
            logger.info(f"Loaded collection {self.config.collection_name}")
            
        except Exception as e:
            logger.error(f"Failed to load collection: {e}")
            raise
    
    async def insert_documents(
        self, 
        documents: List[Dict[str, Any]]
    ) -> bool:
        """
        Insert documents into the vector database.
        
        Args:
            documents: List of document dictionaries with id, content, embedding, etc.
            
        Returns:
            True if insertion was successful
        """
        try:
            if not self.collection:
                await self.create_collection()
                await self.load_collection()
            
            # Prepare data for insertion
            data = [
                [doc["id"] for doc in documents],
                [doc["content"] for doc in documents],
                [doc["embedding"] for doc in documents],
                [doc.get("doc_type", "general") for doc in documents],
                [doc.get("category", "warehouse") for doc in documents],
                [doc.get("created_at", "2024-01-01") for doc in documents]
            ]
            
            # Insert data
            insert_result = self.collection.insert(data)
            self.collection.flush()
            
            logger.info(f"Inserted {len(documents)} documents into collection")
            return True
            
        except Exception as e:
            logger.error(f"Failed to insert documents: {e}")
            return False
    
    async def search_similar(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filter_expr: Optional[str] = None,
        score_threshold: float = 0.0
    ) -> List[SearchResult]:
        """
        Search for similar documents using vector similarity.
        
        Args:
            query_embedding: Query vector embedding
            top_k: Number of results to return
            filter_expr: Optional filter expression
            score_threshold: Minimum similarity score
            
        Returns:
            List of SearchResult objects
        """
        try:
            if not self.collection:
                await self.create_collection()
                await self.load_collection()
            
            # Search parameters
            search_params = {
                "metric_type": self.config.metric_type,
                "params": {"nprobe": 10}
            }
            
            # Perform search
            results = self.collection.search(
                data=[query_embedding],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                expr=filter_expr,
                output_fields=["id", "content", "doc_type", "category", "created_at"]
            )
            
            # Process results
            search_results = []
            for hits in results:
                for hit in hits:
                    if hit.score >= score_threshold:
                        result = SearchResult(
                            id=hit.entity.get("id"),
                            content=hit.entity.get("content"),
                            metadata={
                                "doc_type": hit.entity.get("doc_type"),
                                "category": hit.entity.get("category"),
                                "created_at": hit.entity.get("created_at")
                            },
                            score=hit.score,
                            distance=hit.distance
                        )
                        search_results.append(result)
            
            logger.info(f"Found {len(search_results)} similar documents")
            return search_results
            
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
    
    async def search_by_category(
        self,
        category: str,
        query_embedding: List[float],
        top_k: int = 10
    ) -> List[SearchResult]:
        """
        Search for documents within a specific category.
        
        Args:
            category: Document category to search in
            query_embedding: Query vector embedding
            top_k: Number of results to return
            
        Returns:
            List of SearchResult objects
        """
        filter_expr = f'category == "{category}"'
        return await self.search_similar(
            query_embedding=query_embedding,
            top_k=top_k,
            filter_expr=filter_expr
        )
    
    async def get_collection_stats(self) -> Dict[str, Any]:
        """
        Get collection statistics.
        
        Returns:
            Dictionary with collection statistics
        """
        try:
            if not self.collection:
                await self.create_collection()
            
            stats = {
                "collection_name": self.config.collection_name,
                "num_entities": self.collection.num_entities,
                "is_empty": self.collection.is_empty,
                "description": self.collection.description
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get collection stats: {e}")
            return {}
    
    async def health_check(self) -> bool:
        """
        Check Milvus connectivity and health.
        
        Returns:
            True if Milvus is healthy, False otherwise
        """
        try:
            if not self._connected:
                await self.connect()
            
            # Try to list collections
            collections = utility.list_collections()
            return True
            
        except Exception as e:
            logger.error(f"Milvus health check failed: {e}")
            return False

# Global retriever instance
_milvus_retriever: Optional[MilvusRetriever] = None

async def get_milvus_retriever() -> MilvusRetriever:
    """Get or create the global Milvus retriever instance."""
    global _milvus_retriever
    if _milvus_retriever is None:
        _milvus_retriever = MilvusRetriever()
        await _milvus_retriever.connect()
        await _milvus_retriever.create_collection()
        await _milvus_retriever.load_collection()
    return _milvus_retriever

async def close_milvus_retriever() -> None:
    """Close the global Milvus retriever instance."""
    global _milvus_retriever
    if _milvus_retriever:
        await _milvus_retriever.disconnect()
        _milvus_retriever = None
