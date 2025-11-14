"""
GPU-Accelerated Milvus Vector Retriever for Warehouse Operations

Provides high-performance semantic search capabilities using NVIDIA cuVS
for GPU-accelerated vector search over warehouse documentation and procedures.
"""

import logging
import os
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import numpy as np
from pymilvus import (
    connections, Collection, CollectionSchema, FieldSchema, DataType,
    utility, Index, MilvusException
)
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

@dataclass
class GPUMilvusConfig:
    """GPU-accelerated Milvus configuration for warehouse operations."""
    host: str = os.getenv("MILVUS_HOST", "localhost")
    port: str = os.getenv("MILVUS_PORT", "19530")
    collection_name: str = "warehouse_docs_gpu"
    dimension: int = 1024  # NV-EmbedQA-E5-v5 embedding dimension
    
    # GPU Configuration
    use_gpu: bool = os.getenv("MILVUS_USE_GPU", "true").lower() == "true"
    gpu_device_id: int = int(os.getenv("MILVUS_GPU_DEVICE_ID", "0"))
    cuda_visible_devices: str = os.getenv("CUDA_VISIBLE_DEVICES", "0")
    
    # GPU Index Configuration
    index_type: str = "GPU_CAGRA"  # GPU-accelerated CAGRA index
    metric_type: str = "L2"
    
    # CAGRA-specific parameters
    cagra_params: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.cagra_params is None:
            self.cagra_params = {
                "intermediate_graph_degree": 128,
                "graph_degree": 64,
                "build_algo": "IVF_PQ",
                "build_algo_params": {
                    "pq_dim": 8,
                    "nlist": 1024
                }
            }

@dataclass
class GPUSearchResult:
    """Enhanced search result from GPU-accelerated vector database."""
    id: str
    content: str
    metadata: Dict[str, Any]
    score: float
    distance: float
    gpu_processing_time: float
    batch_size: int

class GPUMilvusRetriever:
    """
    GPU-accelerated Milvus retriever for warehouse operations.
    
    Features:
    - NVIDIA cuVS integration for GPU acceleration
    - GPU_CAGRA index for high-performance search
    - Batch processing optimization
    - Real-time warehouse document search
    - High-throughput semantic search
    """
    
    def __init__(self, config: Optional[GPUMilvusConfig] = None):
        self.config = config or GPUMilvusConfig()
        self.collection: Optional[Collection] = None
        self._connected = False
        self._gpu_available = False
        
        # Set CUDA environment
        if self.config.use_gpu:
            os.environ["CUDA_VISIBLE_DEVICES"] = self.config.cuda_visible_devices
    
    async def connect(self) -> None:
        """Connect to Milvus server with GPU support."""
        try:
            # Set GPU environment variables
            if self.config.use_gpu:
                os.environ["CUDA_VISIBLE_DEVICES"] = self.config.cuda_visible_devices
                logger.info(f"Using GPU device: {self.config.gpu_device_id}")
            
            connections.connect(
                alias="default",
                host=self.config.host,
                port=self.config.port
            )
            
            # Check GPU availability
            if self.config.use_gpu:
                self._gpu_available = await self._check_gpu_availability()
                if not self._gpu_available:
                    logger.warning("GPU not available, falling back to CPU")
                    self.config.use_gpu = False
            
            self._connected = True
            logger.info(f"Connected to Milvus at {self.config.host}:{self.config.port}")
            logger.info(f"GPU acceleration: {'Enabled' if self.config.use_gpu else 'Disabled'}")
            
        except Exception as e:
            logger.error(f"Failed to connect to Milvus: {e}")
            raise
    
    async def _check_gpu_availability(self) -> bool:
        """Check if GPU is available for Milvus operations."""
        try:
            import torch
            if torch.cuda.is_available():
                logger.info(f"CUDA available with {torch.cuda.device_count()} devices")
                return True
            else:
                logger.warning("CUDA not available")
                return False
        except ImportError:
            logger.warning("PyTorch not available for GPU check")
            return False
    
    async def create_collection(self) -> None:
        """Create GPU-optimized collection for warehouse documents."""
        try:
            if not self._connected:
                await self.connect()
            
            # Check if collection exists
            if utility.has_collection(self.config.collection_name):
                logger.info(f"Collection {self.config.collection_name} already exists")
                self.collection = Collection(self.config.collection_name)
                return
            
            # Define collection schema optimized for GPU operations
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
                ),
                FieldSchema(
                    name="priority",
                    dtype=DataType.INT64,
                    default_value=0
                ),
                FieldSchema(
                    name="access_count",
                    dtype=DataType.INT64,
                    default_value=0
                )
            ]
            
            schema = CollectionSchema(
                fields=fields,
                description="GPU-accelerated warehouse operational documents and procedures"
            )
            
            # Create collection
            self.collection = Collection(
                name=self.config.collection_name,
                schema=schema
            )
            
            # Create GPU-accelerated index
            await self._create_gpu_index()
            
            logger.info(f"Created GPU-optimized collection {self.config.collection_name}")
            
        except Exception as e:
            logger.error(f"Failed to create collection: {e}")
            raise
    
    async def _create_gpu_index(self) -> None:
        """Create GPU-accelerated index for vector field."""
        try:
            if self.config.use_gpu and self._gpu_available:
                # GPU_CAGRA index for high performance
                index_params = {
                    "metric_type": self.config.metric_type,
                    "index_type": self.config.index_type,
                    "params": self.config.cagra_params
                }
                
                logger.info(f"Creating GPU_CAGRA index with params: {index_params}")
                
            else:
                # Fallback to CPU index
                index_params = {
                    "metric_type": self.config.metric_type,
                    "index_type": "IVF_FLAT",
                    "params": {"nlist": 1024}
                }
                
                logger.info("Creating CPU IVF_FLAT index (GPU not available)")
            
            # Create index
            self.collection.create_index(
                field_name="embedding",
                index_params=index_params
            )
            
            logger.info("Index created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create index: {e}")
            raise
    
    async def insert_documents_batch(
        self, 
        documents: List[Dict[str, Any]],
        batch_size: int = 1000
    ) -> bool:
        """
        Insert documents in optimized batches for GPU processing.
        
        Args:
            documents: List of document dictionaries
            batch_size: Batch size for GPU optimization
            
        Returns:
            True if insertion was successful
        """
        try:
            if not self.collection:
                await self.create_collection()
                await self.load_collection()
            
            # Process documents in batches for GPU optimization
            total_inserted = 0
            for i in range(0, len(documents), batch_size):
                batch = documents[i:i + batch_size]
                
                # Prepare data for insertion
                data = [
                    [doc["id"] for doc in batch],
                    [doc["content"] for doc in batch],
                    [doc["embedding"] for doc in batch],
                    [doc.get("doc_type", "general") for doc in batch],
                    [doc.get("category", "warehouse") for doc in batch],
                    [doc.get("created_at", "2024-01-01") for doc in batch],
                    [doc.get("priority", 0) for doc in batch],
                    [doc.get("access_count", 0) for doc in batch]
                ]
                
                # Insert batch
                insert_result = self.collection.insert(data)
                total_inserted += len(batch)
                
                logger.info(f"Inserted batch {i//batch_size + 1}: {len(batch)} documents")
            
            # Flush all data
            self.collection.flush()
            
            logger.info(f"Successfully inserted {total_inserted} documents in batches")
            return True
            
        except Exception as e:
            logger.error(f"Failed to insert documents: {e}")
            return False
    
    async def search_similar_gpu(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        batch_size: int = 1,
        filter_expr: Optional[str] = None,
        score_threshold: float = 0.0
    ) -> List[GPUSearchResult]:
        """
        GPU-accelerated similarity search with batch processing.
        
        Args:
            query_embedding: Query vector embedding
            top_k: Number of results to return
            batch_size: Batch size for GPU optimization
            filter_expr: Optional filter expression
            score_threshold: Minimum similarity score
            
        Returns:
            List of GPUSearchResult objects with GPU timing info
        """
        try:
            if not self.collection:
                await self.create_collection()
                await self.load_collection()
            
            import time
            start_time = time.time()
            
            # Configure search parameters for GPU
            if self.config.use_gpu and self._gpu_available:
                search_params = {
                    "metric_type": self.config.metric_type,
                    "params": {
                        "itopk_size": 128,  # GPU-optimized parameter
                        "max_iterations": 0
                    }
                }
            else:
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
                output_fields=["id", "content", "doc_type", "category", "created_at", "priority", "access_count"]
            )
            
            processing_time = time.time() - start_time
            
            # Process results
            search_results = []
            for hits in results:
                for hit in hits:
                    if hit.score >= score_threshold:
                        result = GPUSearchResult(
                            id=hit.entity.get("id"),
                            content=hit.entity.get("content"),
                            metadata={
                                "doc_type": hit.entity.get("doc_type"),
                                "category": hit.entity.get("category"),
                                "created_at": hit.entity.get("created_at"),
                                "priority": hit.entity.get("priority"),
                                "access_count": hit.entity.get("access_count")
                            },
                            score=hit.score,
                            distance=hit.distance,
                            gpu_processing_time=processing_time,
                            batch_size=batch_size
                        )
                        search_results.append(result)
            
            logger.info(f"GPU search completed in {processing_time:.4f}s, found {len(search_results)} results")
            return search_results
            
        except Exception as e:
            logger.error(f"GPU search failed: {e}")
            return []
    
    async def search_by_category_gpu(
        self,
        category: str,
        query_embedding: List[float],
        top_k: int = 10
    ) -> List[GPUSearchResult]:
        """GPU-accelerated search within specific category."""
        filter_expr = f'category == "{category}"'
        return await self.search_similar_gpu(
            query_embedding=query_embedding,
            top_k=top_k,
            filter_expr=filter_expr
        )
    
    async def batch_search_gpu(
        self,
        query_embeddings: List[List[float]],
        top_k: int = 10
    ) -> List[List[GPUSearchResult]]:
        """
        Batch search for multiple queries using GPU acceleration.
        
        Args:
            query_embeddings: List of query embeddings
            top_k: Number of results per query
            
        Returns:
            List of search results for each query
        """
        try:
            if not self.collection:
                await self.create_collection()
                await self.load_collection()
            
            import time
            start_time = time.time()
            
            # Configure batch search parameters
            if self.config.use_gpu and self._gpu_available:
                search_params = {
                    "metric_type": self.config.metric_type,
                    "params": {
                        "itopk_size": 128,
                        "max_iterations": 0
                    }
                }
            else:
                search_params = {
                    "metric_type": self.config.metric_type,
                    "params": {"nprobe": 10}
                }
            
            # Perform batch search
            results = self.collection.search(
                data=query_embeddings,
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                output_fields=["id", "content", "doc_type", "category", "created_at", "priority", "access_count"]
            )
            
            processing_time = time.time() - start_time
            
            # Process batch results
            batch_results = []
            for i, hits in enumerate(results):
                query_results = []
                for hit in hits:
                    result = GPUSearchResult(
                        id=hit.entity.get("id"),
                        content=hit.entity.get("content"),
                        metadata={
                            "doc_type": hit.entity.get("doc_type"),
                            "category": hit.entity.get("category"),
                            "created_at": hit.entity.get("created_at"),
                            "priority": hit.entity.get("priority"),
                            "access_count": hit.entity.get("access_count")
                        },
                        score=hit.score,
                        distance=hit.distance,
                        gpu_processing_time=processing_time / len(query_embeddings),
                        batch_size=len(query_embeddings)
                    )
                    query_results.append(result)
                batch_results.append(query_results)
            
            logger.info(f"Batch search completed: {len(query_embeddings)} queries in {processing_time:.4f}s")
            return batch_results
            
        except Exception as e:
            logger.error(f"Batch search failed: {e}")
            return []
    
    async def get_gpu_performance_stats(self) -> Dict[str, Any]:
        """Get GPU performance statistics."""
        try:
            if not self.collection:
                await self.create_collection()
            
            stats = {
                "collection_name": self.config.collection_name,
                "num_entities": self.collection.num_entities,
                "is_empty": self.collection.is_empty,
                "gpu_enabled": self.config.use_gpu and self._gpu_available,
                "gpu_device_id": self.config.gpu_device_id,
                "index_type": self.config.index_type,
                "dimension": self.config.dimension,
                "cuda_visible_devices": self.config.cuda_visible_devices
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get GPU stats: {e}")
            return {}
    
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
    
    async def disconnect(self) -> None:
        """Disconnect from Milvus server."""
        try:
            if self._connected:
                connections.disconnect("default")
                self._connected = False
                logger.info("Disconnected from Milvus")
        except Exception as e:
            logger.error(f"Error disconnecting from Milvus: {e}")

# Factory function for easy integration
async def get_gpu_milvus_retriever(config: Optional[GPUMilvusConfig] = None) -> GPUMilvusRetriever:
    """Get GPU-accelerated Milvus retriever instance."""
    retriever = GPUMilvusRetriever(config)
    await retriever.connect()
    return retriever
