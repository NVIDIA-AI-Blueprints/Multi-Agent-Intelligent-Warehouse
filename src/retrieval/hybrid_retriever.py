"""
Hybrid Retriever for Warehouse Operations

Combines structured SQL retrieval (TimescaleDB/Postgres) with vector retrieval (Milvus)
to provide comprehensive search capabilities for warehouse operations.
"""

import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
import asyncio
from .structured.sql_retriever import SQLRetriever, get_sql_retriever
from .structured.inventory_queries import InventoryQueries, InventoryItem
from .vector.milvus_retriever import MilvusRetriever, get_milvus_retriever, SearchResult

logger = logging.getLogger(__name__)

@dataclass
class HybridSearchResult:
    """Combined search result from hybrid retrieval."""
    structured_results: List[InventoryItem]
    vector_results: List[SearchResult]
    combined_score: float
    search_type: str  # "inventory", "documentation", "hybrid"

@dataclass
class SearchContext:
    """Context for search operations."""
    query: str
    search_type: str = "hybrid"  # "structured", "vector", "hybrid"
    filters: Optional[Dict[str, Any]] = None
    limit: int = 10
    score_threshold: float = 0.0

class HybridRetriever:
    """
    Hybrid retriever combining structured and vector search.
    
    Provides unified interface for searching both structured inventory data
    and unstructured documentation using appropriate retrieval methods.
    """
    
    def __init__(self):
        self.sql_retriever: Optional[SQLRetriever] = None
        self.milvus_retriever: Optional[MilvusRetriever] = None
        self.inventory_queries: Optional[InventoryQueries] = None
    
    async def initialize(self) -> None:
        """Initialize both retrieval systems."""
        try:
            # Initialize SQL retriever
            self.sql_retriever = await get_sql_retriever()
            self.inventory_queries = InventoryQueries(self.sql_retriever)
            
            # Initialize Milvus retriever
            self.milvus_retriever = await get_milvus_retriever()
            
            logger.info("Hybrid retriever initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize hybrid retriever: {e}")
            raise
    
    async def search(
        self, 
        context: SearchContext
    ) -> HybridSearchResult:
        """
        Perform hybrid search based on context.
        
        Args:
            context: Search context with query and parameters
            
        Returns:
            HybridSearchResult with combined results
        """
        try:
            structured_results = []
            vector_results = []
            search_type = context.search_type
            
            # Determine search strategy based on query type
            if context.search_type == "hybrid":
                search_type = self._classify_query_type(context.query)
            
            # Execute appropriate searches
            if search_type in ["inventory", "hybrid"]:
                structured_results = await self._search_structured(context)
            
            if search_type in ["documentation", "hybrid"]:
                vector_results = await self._search_vector(context)
            
            # Calculate combined score
            combined_score = self._calculate_combined_score(
                structured_results, vector_results
            )
            
            return HybridSearchResult(
                structured_results=structured_results,
                vector_results=vector_results,
                combined_score=combined_score,
                search_type=search_type
            )
            
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return HybridSearchResult(
                structured_results=[],
                vector_results=[],
                combined_score=0.0,
                search_type="error"
            )
    
    def _classify_query_type(self, query: str) -> str:
        """
        Classify query type to determine search strategy.
        
        Args:
            query: User query string
            
        Returns:
            Query type: "inventory", "documentation", or "hybrid"
        """
        query_lower = query.lower()
        
        # Inventory-specific keywords
        inventory_keywords = [
            "sku", "stock", "inventory", "quantity", "location", 
            "reorder", "item", "product", "warehouse stock"
        ]
        
        # Documentation-specific keywords
        doc_keywords = [
            "how to", "procedure", "process", "manual", "guide",
            "sop", "policy", "training", "safety", "compliance"
        ]
        
        has_inventory = any(keyword in query_lower for keyword in inventory_keywords)
        has_documentation = any(keyword in query_lower for keyword in doc_keywords)
        
        if has_inventory and has_documentation:
            return "hybrid"
        elif has_inventory:
            return "inventory"
        elif has_documentation:
            return "documentation"
        else:
            return "hybrid"  # Default to hybrid for ambiguous queries
    
    async def _search_structured(
        self, 
        context: SearchContext
    ) -> List[InventoryItem]:
        """Search structured inventory data."""
        try:
            if not self.inventory_queries:
                return []
            
            # Extract potential SKU from query
            sku = self._extract_sku_from_query(context.query)
            if sku:
                item = await self.inventory_queries.get_item_by_sku(sku)
                return [item] if item else []
            
            # Search by name or general terms
            search_results = await self.inventory_queries.search_items(
                search_term=context.query,
                limit=context.limit
            )
            
            return search_results.items
            
        except Exception as e:
            logger.error(f"Structured search failed: {e}")
            return []
    
    async def _search_vector(
        self, 
        context: SearchContext
    ) -> List[SearchResult]:
        """Search vector database for documentation."""
        try:
            if not self.milvus_retriever:
                return []
            
            # TODO: Generate embedding for query
            # For now, return empty results until embedding service is implemented
            # query_embedding = await self._generate_embedding(context.query)
            # results = await self.milvus_retriever.search_similar(
            #     query_embedding=query_embedding,
            #     top_k=context.limit,
            #     score_threshold=context.score_threshold
            # )
            
            # Placeholder implementation
            return []
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    def _extract_sku_from_query(self, query: str) -> Optional[str]:
        """Extract potential SKU from query text."""
        import re
        
        # Look for SKU patterns (e.g., SKU123, SKU-123, etc.)
        sku_patterns = [
            r'(SKU[-\s]?\w+)',
            r'(sku[-\s]?\w+)',
            r'(item[-\s]?\w+)',
            r'(product[-\s]?\w+)'
        ]
        
        for pattern in sku_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return None
    
    def _calculate_combined_score(
        self, 
        structured_results: List[InventoryItem],
        vector_results: List[SearchResult]
    ) -> float:
        """Calculate combined relevance score."""
        try:
            # Simple scoring based on result counts and quality
            structured_score = min(len(structured_results) / 10.0, 1.0)
            vector_score = min(len(vector_results) / 10.0, 1.0)
            
            # Weighted combination (can be adjusted based on use case)
            combined = (structured_score * 0.6) + (vector_score * 0.4)
            return min(combined, 1.0)
            
        except Exception as e:
            logger.error(f"Score calculation failed: {e}")
            return 0.0
    
    async def get_inventory_summary(self) -> Dict[str, Any]:
        """Get inventory summary using structured retrieval."""
        try:
            if not self.inventory_queries:
                return {}
            
            return await self.inventory_queries.get_inventory_summary()
            
        except Exception as e:
            logger.error(f"Failed to get inventory summary: {e}")
            return {}
    
    async def health_check(self) -> Dict[str, bool]:
        """Check health of both retrieval systems."""
        try:
            sql_healthy = False
            milvus_healthy = False
            
            if self.sql_retriever:
                sql_healthy = await self.sql_retriever.health_check()
            
            if self.milvus_retriever:
                milvus_healthy = await self.milvus_retriever.health_check()
            
            return {
                "sql_retriever": sql_healthy,
                "milvus_retriever": milvus_healthy,
                "overall": sql_healthy and milvus_healthy
            }
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "sql_retriever": False,
                "milvus_retriever": False,
                "overall": False
            }

# Global hybrid retriever instance
_hybrid_retriever: Optional[HybridRetriever] = None

async def get_hybrid_retriever() -> HybridRetriever:
    """Get or create the global hybrid retriever instance."""
    global _hybrid_retriever
    if _hybrid_retriever is None:
        _hybrid_retriever = HybridRetriever()
        await _hybrid_retriever.initialize()
    return _hybrid_retriever
