"""
GPU-Accelerated Hybrid Retriever for Warehouse Operations

Combines structured SQL retrieval (TimescaleDB/Postgres) with GPU-accelerated
vector retrieval (Milvus + cuVS) for ultra-high-performance warehouse operations.
"""

import logging
import asyncio
import time
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from .structured.sql_retriever import SQLRetriever, get_sql_retriever
from .structured.inventory_queries import InventoryQueries, InventoryItem
from .vector.gpu_milvus_retriever import GPUMilvusRetriever, get_gpu_milvus_retriever, GPUSearchResult
from .vector.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

@dataclass
class GPUHybridSearchResult:
    """Enhanced search result from GPU-accelerated hybrid retrieval."""
    structured_results: List[InventoryItem]
    vector_results: List[GPUSearchResult]
    combined_score: float
    search_type: str  # "inventory", "documentation", "hybrid"
    gpu_processing_time: float
    total_processing_time: float
    gpu_acceleration_used: bool

@dataclass
class GPUSearchContext:
    """Enhanced context for GPU-accelerated search operations."""
    query: str
    search_type: str = "hybrid"  # "inventory", "documentation", "hybrid"
    limit: int = 10
    score_threshold: float = 0.0
    use_gpu: bool = True
    batch_size: int = 1

class GPUHybridRetriever:
    """
    GPU-accelerated hybrid retriever for warehouse operations.
    
    Features:
    - NVIDIA cuVS integration for GPU-accelerated vector search
    - GPU_CAGRA index for ultra-high performance
    - Batch processing optimization
    - Real-time warehouse document search
    - Intelligent query routing (SQL vs Vector vs Hybrid)
    - Performance monitoring and optimization
    """
    
    def __init__(self):
        self.sql_retriever: Optional[SQLRetriever] = None
        self.gpu_milvus_retriever: Optional[GPUMilvusRetriever] = None
        self.embedding_service: Optional[EmbeddingService] = None
        self.inventory_queries: Optional[InventoryQueries] = None
        self._gpu_available = False
    
    async def initialize(self) -> None:
        """Initialize GPU-accelerated hybrid retriever."""
        try:
            # Initialize SQL retriever
            self.sql_retriever = await get_sql_retriever()
            self.inventory_queries = InventoryQueries(self.sql_retriever)
            
            # Initialize GPU Milvus retriever
            self.gpu_milvus_retriever = await get_gpu_milvus_retriever()
            self._gpu_available = self.gpu_milvus_retriever._gpu_available
            
            # Initialize embedding service
            self.embedding_service = EmbeddingService()
            await self.embedding_service.initialize()
            
            logger.info(f"GPU Hybrid retriever initialized - GPU: {'Available' if self._gpu_available else 'Not Available'}")
            
        except Exception as e:
            logger.error(f"Failed to initialize GPU hybrid retriever: {e}")
            raise
    
    async def search(
        self, 
        context: GPUSearchContext
    ) -> GPUHybridSearchResult:
        """
        Perform GPU-accelerated hybrid search.
        
        Args:
            context: Search context with query and parameters
            
        Returns:
            GPUHybridSearchResult with combined results
        """
        start_time = time.time()
        
        try:
            # Route query based on type
            if context.search_type == "inventory":
                return await self._search_inventory_only(context, start_time)
            elif context.search_type == "documentation":
                return await self._search_documentation_only(context, start_time)
            else:  # hybrid
                return await self._search_hybrid(context, start_time)
                
        except Exception as e:
            logger.error(f"GPU hybrid search failed: {e}")
            return self._create_empty_response(start_time)
    
    async def _search_hybrid(
        self, 
        context: GPUSearchContext, 
        start_time: float
    ) -> GPUHybridSearchResult:
        """Perform hybrid search with both SQL and GPU vector search."""
        try:
            # Parallel execution of SQL and GPU vector search
            sql_task = asyncio.create_task(
                self._search_structured_data(context)
            )
            vector_task = asyncio.create_task(
                self._search_vector_data_gpu(context)
            )
            
            # Wait for both searches to complete
            sql_results, vector_results = await asyncio.gather(
                sql_task, vector_task, return_exceptions=True
            )
            
            # Handle exceptions
            if isinstance(sql_results, Exception):
                logger.warning(f"SQL search failed: {sql_results}")
                sql_results = []
            
            if isinstance(vector_results, Exception):
                logger.warning(f"Vector search failed: {vector_results}")
                vector_results = []
            
            # Combine results
            combined_score = self._calculate_combined_score(sql_results, vector_results)
            
            total_time = time.time() - start_time
            gpu_time = sum(result.gpu_processing_time for result in vector_results) if vector_results else 0
            
            return GPUHybridSearchResult(
                structured_results=sql_results,
                vector_results=vector_results,
                combined_score=combined_score,
                search_type="hybrid",
                gpu_processing_time=gpu_time,
                total_processing_time=total_time,
                gpu_acceleration_used=self._gpu_available
            )
            
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return self._create_empty_response(start_time)
    
    async def _search_inventory_only(
        self, 
        context: GPUSearchContext, 
        start_time: float
    ) -> GPUHybridSearchResult:
        """Search only structured inventory data."""
        try:
            sql_results = await self._search_structured_data(context)
            total_time = time.time() - start_time
            
            return GPUHybridSearchResult(
                structured_results=sql_results,
                vector_results=[],
                combined_score=1.0,
                search_type="inventory",
                gpu_processing_time=0.0,
                total_processing_time=total_time,
                gpu_acceleration_used=False
            )
            
        except Exception as e:
            logger.error(f"Inventory search failed: {e}")
            return self._create_empty_response(start_time)
    
    async def _search_documentation_only(
        self, 
        context: GPUSearchContext, 
        start_time: float
    ) -> GPUHybridSearchResult:
        """Search only documentation using GPU-accelerated vector search."""
        try:
            vector_results = await self._search_vector_data_gpu(context)
            total_time = time.time() - start_time
            gpu_time = sum(result.gpu_processing_time for result in vector_results) if vector_results else 0
            
            return GPUHybridSearchResult(
                structured_results=[],
                vector_results=vector_results,
                combined_score=1.0,
                search_type="documentation",
                gpu_processing_time=gpu_time,
                total_processing_time=total_time,
                gpu_acceleration_used=self._gpu_available
            )
            
        except Exception as e:
            logger.error(f"Documentation search failed: {e}")
            return self._create_empty_response(start_time)
    
    async def _search_structured_data(
        self, 
        context: GPUSearchContext
    ) -> List[InventoryItem]:
        """Search structured inventory data."""
        try:
            # Use existing inventory queries
            if "inventory" in context.query.lower() or "stock" in context.query.lower():
                return await self.inventory_queries.search_inventory_items(
                    query=context.query,
                    limit=context.limit
                )
            else:
                return []
                
        except Exception as e:
            logger.error(f"Structured data search failed: {e}")
            return []
    
    async def _search_vector_data_gpu(
        self, 
        context: GPUSearchContext
    ) -> List[GPUSearchResult]:
        """Search documentation using GPU-accelerated vector search."""
        try:
            # Generate query embedding
            query_embedding = await self.embedding_service.generate_embedding(context.query)
            
            # Perform GPU-accelerated search
            if context.use_gpu and self._gpu_available:
                return await self.gpu_milvus_retriever.search_similar_gpu(
                    query_embedding=query_embedding,
                    top_k=context.limit,
                    batch_size=context.batch_size,
                    score_threshold=context.score_threshold
                )
            else:
                # Fallback to CPU search
                return await self.gpu_milvus_retriever.search_similar_gpu(
                    query_embedding=query_embedding,
                    top_k=context.limit,
                    batch_size=1,
                    score_threshold=context.score_threshold
                )
                
        except Exception as e:
            logger.error(f"GPU vector search failed: {e}")
            return []
    
    def _calculate_combined_score(
        self, 
        sql_results: List[InventoryItem], 
        vector_results: List[GPUSearchResult]
    ) -> float:
        """Calculate combined relevance score."""
        try:
            if not sql_results and not vector_results:
                return 0.0
            
            # Weighted combination: 60% vector, 40% SQL
            vector_score = sum(result.score for result in vector_results) / len(vector_results) if vector_results else 0.0
            sql_score = 1.0 if sql_results else 0.0  # Binary score for SQL results
            
            return 0.6 * vector_score + 0.4 * sql_score
            
        except Exception as e:
            logger.error(f"Score calculation failed: {e}")
            return 0.0
    
    def _create_empty_response(self, start_time: float) -> GPUHybridSearchResult:
        """Create empty response for error cases."""
        total_time = time.time() - start_time
        return GPUHybridSearchResult(
            structured_results=[],
            vector_results=[],
            combined_score=0.0,
            search_type="error",
            gpu_processing_time=0.0,
            total_processing_time=total_time,
            gpu_acceleration_used=False
        )
    
    async def batch_search(
        self, 
        queries: List[str],
        search_type: str = "hybrid"
    ) -> List[GPUHybridSearchResult]:
        """
        Perform batch search for multiple queries using GPU acceleration.
        
        Args:
            queries: List of search queries
            search_type: Type of search to perform
            
        Returns:
            List of search results for each query
        """
        try:
            # Generate embeddings for all queries
            query_embeddings = []
            for query in queries:
                embedding = await self.embedding_service.generate_embedding(query)
                query_embeddings.append(embedding)
            
            # Perform batch GPU search
            if self._gpu_available and search_type in ["documentation", "hybrid"]:
                batch_results = await self.gpu_milvus_retriever.batch_search_gpu(
                    query_embeddings=query_embeddings,
                    top_k=10
                )
                
                # Convert to hybrid results
                hybrid_results = []
                for i, vector_results in enumerate(batch_results):
                    context = GPUSearchContext(
                        query=queries[i],
                        search_type=search_type
                    )
                    
                    # Get SQL results for hybrid search
                    sql_results = []
                    if search_type == "hybrid":
                        sql_results = await self._search_structured_data(context)
                    
                    combined_score = self._calculate_combined_score(sql_results, vector_results)
                    
                    hybrid_results.append(GPUHybridSearchResult(
                        structured_results=sql_results,
                        vector_results=vector_results,
                        combined_score=combined_score,
                        search_type=search_type,
                        gpu_processing_time=sum(r.gpu_processing_time for r in vector_results),
                        total_processing_time=0.0,  # Will be calculated by caller
                        gpu_acceleration_used=True
                    ))
                
                return hybrid_results
            else:
                # Fallback to individual searches
                results = []
                for query in queries:
                    context = GPUSearchContext(
                        query=query,
                        search_type=search_type
                    )
                    result = await self.search(context)
                    results.append(result)
                return results
                
        except Exception as e:
            logger.error(f"Batch search failed: {e}")
            return []
    
    async def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics including GPU metrics."""
        try:
            stats = {
                "gpu_available": self._gpu_available,
                "retriever_type": "GPU-accelerated hybrid",
                "sql_retriever_available": self.sql_retriever is not None,
                "vector_retriever_available": self.gpu_milvus_retriever is not None,
                "embedding_service_available": self.embedding_service is not None
            }
            
            if self.gpu_milvus_retriever:
                gpu_stats = await self.gpu_milvus_retriever.get_gpu_performance_stats()
                stats.update(gpu_stats)
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get performance stats: {e}")
            return {}

# Factory function
async def get_gpu_hybrid_retriever() -> GPUHybridRetriever:
    """Get GPU-accelerated hybrid retriever instance."""
    retriever = GPUHybridRetriever()
    await retriever.initialize()
    return retriever
