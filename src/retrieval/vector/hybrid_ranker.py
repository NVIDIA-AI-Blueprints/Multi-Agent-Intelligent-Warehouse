"""
Hybrid Ranker for Warehouse Operations

Combines structured and vector search results with intelligent ranking
to provide the most relevant results for warehouse operational queries.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import math
from .milvus_retriever import SearchResult
from ..structured.inventory_queries import InventoryItem

logger = logging.getLogger(__name__)

@dataclass
class RankedResult:
    """Ranked search result with combined score."""
    item: Any  # Can be InventoryItem or SearchResult
    structured_score: float
    vector_score: float
    combined_score: float
    result_type: str  # "inventory", "documentation"

class HybridRanker:
    """
    Hybrid ranking system for combining structured and vector search results.
    
    Uses multiple ranking factors to provide the most relevant results
    for warehouse operational queries.
    """
    
    def __init__(self):
        self.structured_weight = 0.6
        self.vector_weight = 0.4
        self.relevance_boost = 1.2
        self.recency_boost = 1.1
    
    def rank_results(
        self,
        structured_results: List[InventoryItem],
        vector_results: List[SearchResult],
        query: str,
        max_results: int = 10
    ) -> List[RankedResult]:
        """
        Rank and combine structured and vector search results.
        
        Args:
            structured_results: Results from structured search
            vector_results: Results from vector search
            query: Original query for relevance scoring
            max_results: Maximum number of results to return
            
        Returns:
            List of RankedResult objects sorted by combined score
        """
        try:
            ranked_results = []
            
            # Rank structured results
            for item in structured_results:
                structured_score = self._calculate_structured_score(item, query)
                combined_score = structured_score * self.structured_weight
                
                ranked_result = RankedResult(
                    item=item,
                    structured_score=structured_score,
                    vector_score=0.0,
                    combined_score=combined_score,
                    result_type="inventory"
                )
                ranked_results.append(ranked_result)
            
            # Rank vector results
            for result in vector_results:
                vector_score = self._calculate_vector_score(result, query)
                combined_score = vector_score * self.vector_weight
                
                ranked_result = RankedResult(
                    item=result,
                    structured_score=0.0,
                    vector_score=vector_score,
                    combined_score=combined_score,
                    result_type="documentation"
                )
                ranked_results.append(ranked_result)
            
            # Sort by combined score (descending)
            ranked_results.sort(key=lambda x: x.combined_score, reverse=True)
            
            # Apply diversity and relevance boosting
            final_results = self._apply_ranking_boosts(ranked_results, query)
            
            return final_results[:max_results]
            
        except Exception as e:
            logger.error(f"Ranking failed: {e}")
            return []
    
    def _calculate_structured_score(self, item: InventoryItem, query: str) -> float:
        """
        Calculate relevance score for structured inventory results.
        
        Args:
            item: Inventory item
            query: Original query
            
        Returns:
            Relevance score between 0 and 1
        """
        try:
            score = 0.0
            query_lower = query.lower()
            
            # SKU exact match (highest priority)
            if item.sku.lower() in query_lower:
                score += 0.8
            
            # Name relevance
            if any(word in item.name.lower() for word in query_lower.split()):
                score += 0.6
            
            # Location relevance
            if item.location and any(word in item.location.lower() for word in query_lower.split()):
                score += 0.3
            
            # Stock level relevance
            if "stock" in query_lower or "quantity" in query_lower:
                if item.quantity <= item.reorder_point:
                    score += 0.4  # Boost for low stock items
                else:
                    score += 0.2
            
            # Reorder relevance
            if "reorder" in query_lower and item.quantity <= item.reorder_point:
                score += 0.5
            
            # Normalize score
            return min(score, 1.0)
            
        except Exception as e:
            logger.error(f"Structured score calculation failed: {e}")
            return 0.0
    
    def _calculate_vector_score(self, result: SearchResult, query: str) -> float:
        """
        Calculate relevance score for vector search results.
        
        Args:
            result: Vector search result
            query: Original query
            
        Returns:
            Relevance score between 0 and 1
        """
        try:
            # Base score from vector similarity
            base_score = result.score
            
            # Boost for exact keyword matches in content
            query_words = set(query.lower().split())
            content_words = set(result.content.lower().split())
            keyword_overlap = len(query_words.intersection(content_words)) / len(query_words)
            
            # Apply keyword boost
            keyword_boost = 1.0 + (keyword_overlap * 0.3)
            
            # Boost for specific document types
            doc_type_boost = 1.0
            if result.metadata.get("doc_type") in ["sop", "manual", "procedure"]:
                doc_type_boost = 1.2
            
            # Calculate final score
            final_score = base_score * keyword_boost * doc_type_boost
            
            return min(final_score, 1.0)
            
        except Exception as e:
            logger.error(f"Vector score calculation failed: {e}")
            return 0.0
    
    def _apply_ranking_boosts(
        self, 
        results: List[RankedResult], 
        query: str
    ) -> List[RankedResult]:
        """
        Apply additional ranking boosts for diversity and relevance.
        
        Args:
            results: Ranked results
            query: Original query
            
        Returns:
            Results with applied boosts
        """
        try:
            boosted_results = []
            seen_types = set()
            
            for result in results:
                # Apply diversity boost (prefer different result types)
                diversity_boost = 1.0
                if result.result_type not in seen_types:
                    diversity_boost = 1.1
                    seen_types.add(result.result_type)
                
                # Apply recency boost for inventory items
                recency_boost = 1.0
                if result.result_type == "inventory":
                    # TODO: Implement recency calculation based on updated_at
                    recency_boost = self.recency_boost
                
                # Apply query-specific boosts
                query_boost = self._calculate_query_boost(result, query)
                
                # Update combined score
                result.combined_score *= diversity_boost * recency_boost * query_boost
                boosted_results.append(result)
            
            # Re-sort by updated combined score
            boosted_results.sort(key=lambda x: x.combined_score, reverse=True)
            
            return boosted_results
            
        except Exception as e:
            logger.error(f"Ranking boost application failed: {e}")
            return results
    
    def _calculate_query_boost(self, result: RankedResult, query: str) -> float:
        """
        Calculate query-specific boost factors.
        
        Args:
            result: Ranked result
            query: Original query
            
        Returns:
            Boost factor
        """
        try:
            boost = 1.0
            query_lower = query.lower()
            
            # Emergency/safety queries boost safety documentation
            if any(word in query_lower for word in ["emergency", "safety", "incident", "hazard"]):
                if result.result_type == "documentation":
                    boost *= 1.3
            
            # Inventory queries boost inventory results
            if any(word in query_lower for word in ["stock", "inventory", "sku", "quantity"]):
                if result.result_type == "inventory":
                    boost *= 1.2
            
            # Procedure queries boost documentation
            if any(word in query_lower for word in ["how", "procedure", "process", "manual"]):
                if result.result_type == "documentation":
                    boost *= 1.2
            
            return boost
            
        except Exception as e:
            logger.error(f"Query boost calculation failed: {e}")
            return 1.0
    
    def get_ranking_explanation(self, result: RankedResult) -> Dict[str, Any]:
        """
        Get explanation of ranking factors for a result.
        
        Args:
            result: Ranked result
            
        Returns:
            Dictionary with ranking explanation
        """
        return {
            "structured_score": result.structured_score,
            "vector_score": result.vector_score,
            "combined_score": result.combined_score,
            "result_type": result.result_type,
            "structured_weight": self.structured_weight,
            "vector_weight": self.vector_weight
        }
