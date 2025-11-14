"""
Enhanced Vector Retriever with Optimization

Implements advanced retrieval with top-k=12 → re-rank to 6, diversity scoring,
relevance thresholds, and source diversity for improved accuracy.
"""

import logging
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict
import asyncio

from .chunking_service import Chunk, ChunkMetadata
from .milvus_retriever import MilvusRetriever, SearchResult
from .embedding_service import EmbeddingService
from .evidence_scoring import EvidenceScoringEngine, EvidenceSource, EvidenceItem, EvidenceScore
from .clarifying_questions import ClarifyingQuestionsEngine, QuestionSet

logger = logging.getLogger(__name__)

@dataclass
class EnhancedSearchResult:
    """Enhanced search result with additional metadata."""
    chunk: Chunk
    content: str  # Added for easier access to content
    similarity_score: float
    relevance_score: float
    diversity_score: float
    source_diversity: float
    evidence_score: float
    rank: int
    rerank_score: float
    confidence_level: str = "medium"
    clarifying_questions: List[str] = None
    evidence_quality: str = "fair"

@dataclass
class RetrievalConfig:
    """Configuration for enhanced retrieval."""
    initial_top_k: int = 12
    final_top_k: int = 6
    min_similarity_threshold: float = 0.3
    min_relevance_threshold: float = 0.35
    diversity_weight: float = 0.3
    relevance_weight: float = 0.7
    source_diversity_penalty: float = 0.1
    evidence_threshold: float = 0.35
    min_sources: int = 2

class EnhancedVectorRetriever:
    """
    Enhanced vector retriever with optimization features.
    
    Features:
    - top-k=12 initial retrieval → re-rank to top-6
    - Diversity scoring for varied source coverage
    - Relevance scoring with configurable thresholds
    - Source diversity to avoid single-source bias
    - Evidence scoring for confidence assessment
    - Intelligent re-ranking based on multiple factors
    """
    
    def __init__(
        self,
        milvus_retriever: MilvusRetriever,
        embedding_service: EmbeddingService,
        config: Optional[RetrievalConfig] = None
    ):
        self.milvus_retriever = milvus_retriever
        self.embedding_service = embedding_service
        self.config = config or RetrievalConfig()
        self.evidence_scoring_engine = EvidenceScoringEngine()
        self.clarifying_questions_engine = ClarifyingQuestionsEngine()
        
        logger.info(f"EnhancedVectorRetriever initialized with config: {self.config}")
    
    async def search(
        self,
        query: str,
        filters: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[List[EnhancedSearchResult], Dict[str, Any]]:
        """
        Perform enhanced vector search with optimization.
        
        Args:
            query: Search query
            filters: Optional filters for search
            context: Additional context for search
            
        Returns:
            Tuple of (search_results, metadata)
        """
        try:
            # Generate query embedding
            query_embedding = await self.embedding_service.generate_embedding(query)
            
            # Initial retrieval with top-k=12
            initial_results = await self._initial_retrieval(
                query_embedding, filters, self.config.initial_top_k
            )
            
            if not initial_results:
                return [], {"message": "No results found", "total_retrieved": 0}
            
            # Convert to enhanced results
            enhanced_results = await self._convert_to_enhanced_results(
                initial_results, query, context
            )
            
            # Apply relevance filtering
            relevant_results = self._filter_by_relevance(enhanced_results)
            
            # Calculate diversity scores
            enhanced_results = await self._calculate_diversity_scores(enhanced_results)
            
            # Re-rank to top-6
            reranked_results = self._rerank_results(enhanced_results)
            
            # Final filtering and validation
            final_results = self._final_filtering(reranked_results)
            
            # Calculate evidence scores and generate clarifying questions
            evidence_score, clarifying_questions = await self._calculate_evidence_and_questions(
                final_results, query, context
            )
            
            # Update results with evidence scoring
            final_results = self._update_results_with_evidence(final_results, evidence_score)
            
            # Generate metadata
            metadata = self._generate_metadata(final_results, query, evidence_score, clarifying_questions)
            
            logger.info(f"Enhanced search completed: {len(final_results)} results, evidence_score: {evidence_score.overall_score:.3f}")
            return final_results, metadata
            
        except Exception as e:
            logger.error(f"Enhanced search failed: {e}")
            return [], {"error": str(e), "total_retrieved": 0}
    
    async def _calculate_evidence_and_questions(
        self,
        results: List[EnhancedSearchResult],
        query: str,
        context: Optional[Dict[str, Any]]
    ) -> Tuple[EvidenceScore, Optional[QuestionSet]]:
        """Calculate evidence scores and generate clarifying questions."""
        try:
            # Convert results to evidence items
            evidence_items = []
            for result in results:
                evidence_source = self.evidence_scoring_engine.create_evidence_source(
                    source_id=result.chunk.metadata.source_id,
                    source_type=result.chunk.metadata.source_type,
                    content=result.chunk.content,
                    last_updated=result.chunk.metadata.last_updated
                )
                
                evidence_item = EvidenceItem(
                    content=result.chunk.content,
                    source=evidence_source,
                    similarity_score=result.similarity_score,
                    relevance_score=result.relevance_score,
                    cross_references=result.chunk.metadata.cross_references,
                    keywords=result.chunk.metadata.keywords,
                    metadata=result.chunk.metadata.metadata
                )
                evidence_items.append(evidence_item)
            
            # Calculate evidence score
            evidence_score = self.evidence_scoring_engine.calculate_evidence_score(
                evidence_items, context
            )
            
            # Generate clarifying questions if confidence is low
            clarifying_questions = None
            if evidence_score.confidence_level == "low" or evidence_score.overall_score < self.config.evidence_threshold:
                query_type = context.get("query_type", "general") if context else "general"
                clarifying_questions = self.clarifying_questions_engine.generate_questions(
                    query=query,
                    evidence_score=evidence_score.overall_score,
                    query_type=query_type,
                    context=context
                )
            
            return evidence_score, clarifying_questions
            
        except Exception as e:
            logger.error(f"Evidence calculation failed: {e}")
            # Return default evidence score
            from .evidence_scoring import EvidenceScore
            return EvidenceScore(
                overall_score=0.0,
                similarity_component=0.0,
                authority_component=0.0,
                freshness_component=0.0,
                cross_reference_component=0.0,
                source_diversity_score=0.0,
                confidence_level="low",
                evidence_quality="poor",
                validation_status="insufficient",
                sources_count=0,
                distinct_sources=0
            ), None
    
    def _update_results_with_evidence(
        self,
        results: List[EnhancedSearchResult],
        evidence_score: EvidenceScore
    ) -> List[EnhancedSearchResult]:
        """Update results with evidence scoring information."""
        for result in results:
            result.evidence_score = evidence_score.overall_score
            result.confidence_level = evidence_score.confidence_level
            result.evidence_quality = evidence_score.evidence_quality
        
        return results
    
    async def _initial_retrieval(
        self,
        query_embedding: List[float],
        filters: Optional[Dict[str, Any]],
        top_k: int
    ) -> List[SearchResult]:
        """Perform initial retrieval from vector database."""
        try:
            # Build filter expression
            filter_expr = self._build_filter_expression(filters) if filters else None
            
            # Search with Milvus
            results = await self.milvus_retriever.search_similar(
                query_embedding=query_embedding,
                top_k=top_k,
                filter_expr=filter_expr,
                score_threshold=self.config.min_similarity_threshold
            )
            
            logger.debug(f"Initial retrieval returned {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Initial retrieval failed: {e}")
            return []
    
    async def _convert_to_enhanced_results(
        self,
        results: List[SearchResult],
        query: str,
        context: Optional[Dict[str, Any]]
    ) -> List[EnhancedSearchResult]:
        """Convert basic search results to enhanced results."""
        enhanced_results = []
        
        for i, result in enumerate(results):
            # Create chunk from search result
            chunk = self._create_chunk_from_result(result)
            
            # Calculate relevance score
            relevance_score = await self._calculate_relevance_score(chunk, query, context)
            
            # Create enhanced result
            enhanced_result = EnhancedSearchResult(
                chunk=chunk,
                content=chunk.content,  # Add content field
                similarity_score=result.score,
                relevance_score=relevance_score,
                diversity_score=0.0,  # Will be calculated later
                source_diversity=0.0,  # Will be calculated later
                evidence_score=0.0,  # Will be calculated later
                rank=i + 1,
                rerank_score=0.0  # Will be calculated during re-ranking
            )
            
            enhanced_results.append(enhanced_result)
        
        return enhanced_results
    
    def _create_chunk_from_result(self, result: SearchResult) -> Chunk:
        """Create a Chunk object from a SearchResult."""
        # Extract metadata from result
        metadata = ChunkMetadata(
            chunk_id=result.id,
            source_id=result.metadata.get('source_id', 'unknown'),
            source_type=result.metadata.get('source_type', 'document'),
            chunk_index=result.metadata.get('chunk_index', 0),
            total_chunks=result.metadata.get('total_chunks', 1),
            token_count=result.metadata.get('token_count', 0),
            char_count=len(result.content),
            start_position=result.metadata.get('start_position', 0),
            end_position=result.metadata.get('end_position', len(result.content)),
            created_at=result.metadata.get('created_at', None),
            quality_score=result.metadata.get('quality_score', 1.0),
            keywords=result.metadata.get('keywords', []),
            category=result.metadata.get('category', 'general'),
            section=result.metadata.get('section'),
            page_number=result.metadata.get('page_number')
        )
        
        return Chunk(content=result.content, metadata=metadata)
    
    async def _calculate_relevance_score(
        self,
        chunk: Chunk,
        query: str,
        context: Optional[Dict[str, Any]]
    ) -> float:
        """Calculate relevance score for a chunk."""
        try:
            # Base relevance from similarity
            base_score = 0.5
            
            # Boost for exact keyword matches
            query_words = set(query.lower().split())
            content_words = set(chunk.content.lower().split())
            keyword_matches = len(query_words.intersection(content_words))
            keyword_boost = min(keyword_matches * 0.1, 0.3)
            
            # Boost for category relevance
            category_boost = 0.0
            if context and 'category' in context:
                if chunk.metadata.category == context['category']:
                    category_boost = 0.2
            
            # Boost for source type relevance
            source_boost = 0.0
            if context and 'preferred_source_types' in context:
                if chunk.metadata.source_type in context['preferred_source_types']:
                    source_boost = 0.1
            
            # Penalty for low quality chunks
            quality_penalty = (1.0 - chunk.metadata.quality_score) * 0.2
            
            relevance_score = base_score + keyword_boost + category_boost + source_boost - quality_penalty
            return min(max(relevance_score, 0.0), 1.0)
            
        except Exception as e:
            logger.error(f"Failed to calculate relevance score: {e}")
            return 0.5
    
    def _filter_by_relevance(self, results: List[EnhancedSearchResult]) -> List[EnhancedSearchResult]:
        """Filter results by relevance threshold."""
        filtered = [
            result for result in results
            if result.relevance_score >= self.config.min_relevance_threshold
        ]
        
        logger.debug(f"Filtered {len(results)} results to {len(filtered)} by relevance")
        return filtered
    
    async def _calculate_diversity_scores(self, results: List[EnhancedSearchResult]) -> List[EnhancedSearchResult]:
        """Calculate diversity scores for results."""
        if not results:
            return results
        
        # Calculate source diversity
        source_counts = defaultdict(int)
        for result in results:
            source_counts[result.chunk.metadata.source_id] += 1
        
        total_sources = len(source_counts)
        max_source_count = max(source_counts.values()) if source_counts else 1
        
        # Calculate diversity scores
        for result in results:
            # Source diversity (penalize over-represented sources)
            source_count = source_counts[result.chunk.metadata.source_id]
            source_diversity = 1.0 - (source_count - 1) / max_source_count
            
            # Content diversity (based on keyword overlap)
            content_diversity = self._calculate_content_diversity(result, results)
            
            # Overall diversity score
            diversity_score = (source_diversity + content_diversity) / 2
            
            result.diversity_score = diversity_score
            result.source_diversity = source_diversity
        
        return results
    
    def _calculate_content_diversity(self, result: EnhancedSearchResult, all_results: List[EnhancedSearchResult]) -> float:
        """Calculate content diversity for a result."""
        if len(all_results) <= 1:
            return 1.0
        
        # Get keywords for this result
        this_keywords = set(result.chunk.metadata.keywords)
        
        # Calculate overlap with other results
        overlaps = []
        for other_result in all_results:
            if other_result.chunk.metadata.chunk_id != result.chunk.metadata.chunk_id:
                other_keywords = set(other_result.chunk.metadata.keywords)
                overlap = len(this_keywords.intersection(other_keywords))
                total = len(this_keywords.union(other_keywords))
                if total > 0:
                    overlaps.append(overlap / total)
        
        if not overlaps:
            return 1.0
        
        # Diversity is inverse of average overlap
        avg_overlap = sum(overlaps) / len(overlaps)
        return 1.0 - avg_overlap
    
    def _rerank_results(self, results: List[EnhancedSearchResult]) -> List[EnhancedSearchResult]:
        """Re-rank results based on combined scoring."""
        for result in results:
            # Calculate combined rerank score
            rerank_score = (
                result.similarity_score * 0.4 +
                result.relevance_score * self.config.relevance_weight +
                result.diversity_score * self.config.diversity_weight
            )
            
            # Apply source diversity penalty
            if result.source_diversity < 0.5:
                rerank_score *= (1.0 - self.config.source_diversity_penalty)
            
            result.rerank_score = rerank_score
        
        # Sort by rerank score (descending)
        results.sort(key=lambda x: x.rerank_score, reverse=True)
        
        # Update ranks
        for i, result in enumerate(results):
            result.rank = i + 1
        
        return results
    
    def _final_filtering(self, results: List[EnhancedSearchResult]) -> List[EnhancedSearchResult]:
        """Apply final filtering and return top-k results."""
        # Take top-k results
        final_results = results[:self.config.final_top_k]
        
        # Calculate evidence scores
        for result in final_results:
            result.evidence_score = self._calculate_evidence_score(result, final_results)
        
        logger.debug(f"Final filtering: {len(results)} -> {len(final_results)} results")
        return final_results
    
    def _calculate_evidence_score(
        self,
        result: EnhancedSearchResult,
        all_results: List[EnhancedSearchResult]
    ) -> float:
        """Calculate evidence score for a result."""
        # Base evidence score from similarity and relevance
        base_score = (result.similarity_score + result.relevance_score) / 2
        
        # Boost for high-quality chunks
        quality_boost = result.chunk.metadata.quality_score * 0.2
        
        # Boost for source diversity
        source_boost = result.source_diversity * 0.1
        
        evidence_score = base_score + quality_boost + source_boost
        return min(evidence_score, 1.0)
    
    def _generate_metadata(
        self,
        results: List[EnhancedSearchResult],
        query: str,
        evidence_score: Optional[EvidenceScore] = None,
        clarifying_questions: Optional[QuestionSet] = None
    ) -> Dict[str, Any]:
        """Generate metadata about the search results."""
        if not results:
            return {"total_results": 0, "avg_evidence_score": 0.0}
        
        # Calculate statistics
        evidence_scores = [result.evidence_score for result in results]
        relevance_scores = [result.relevance_score for result in results]
        similarity_scores = [result.similarity_score for result in results]
        
        # Count unique sources
        unique_sources = len(set(result.chunk.metadata.source_id for result in results))
        unique_categories = len(set(result.chunk.metadata.category for result in results))
        
        # Check if evidence quality meets threshold
        avg_evidence_score = sum(evidence_scores) / len(evidence_scores)
        meets_evidence_threshold = avg_evidence_score >= self.config.evidence_threshold
        meets_source_diversity = unique_sources >= self.config.min_sources
        
        metadata = {
            "total_results": len(results),
            "unique_sources": unique_sources,
            "unique_categories": unique_categories,
            "avg_evidence_score": avg_evidence_score,
            "avg_relevance_score": sum(relevance_scores) / len(relevance_scores),
            "avg_similarity_score": sum(similarity_scores) / len(similarity_scores),
            "meets_evidence_threshold": meets_evidence_threshold,
            "meets_source_diversity": meets_source_diversity,
            "confidence_level": "high" if meets_evidence_threshold and meets_source_diversity else "medium" if meets_evidence_threshold else "low",
            "query": query
        }
        
        # Add evidence scoring details if available
        if evidence_score:
            metadata.update({
                "evidence_scoring": {
                    "overall_score": evidence_score.overall_score,
                    "similarity_component": evidence_score.similarity_component,
                    "authority_component": evidence_score.authority_component,
                    "freshness_component": evidence_score.freshness_component,
                    "cross_reference_component": evidence_score.cross_reference_component,
                    "source_diversity_score": evidence_score.source_diversity_score,
                    "confidence_level": evidence_score.confidence_level,
                    "evidence_quality": evidence_score.evidence_quality,
                    "validation_status": evidence_score.validation_status,
                    "sources_count": evidence_score.sources_count,
                    "distinct_sources": evidence_score.distinct_sources
                }
            })
        
        # Add clarifying questions if available
        if clarifying_questions:
            metadata.update({
                "clarifying_questions": {
                    "questions": [q.question for q in clarifying_questions.questions],
                    "context": clarifying_questions.context,
                    "query_type": clarifying_questions.query_type,
                    "confidence_level": clarifying_questions.confidence_level,
                    "total_priority_score": clarifying_questions.total_priority_score,
                    "estimated_completion_time": clarifying_questions.estimated_completion_time
                }
            })
        
        return metadata
    
    def _build_filter_expression(self, filters: Dict[str, Any]) -> str:
        """Build Milvus filter expression from filters."""
        conditions = []
        
        for key, value in filters.items():
            if isinstance(value, str):
                conditions.append(f"{key} == '{value}'")
            elif isinstance(value, list):
                if value:
                    value_list = "', '".join(str(v) for v in value)
                    conditions.append(f"{key} in ['{value_list}']")
            else:
                conditions.append(f"{key} == {value}")
        
        return " and ".join(conditions) if conditions else ""
    
    def should_ask_clarifying_question(self, metadata: Dict[str, Any]) -> bool:
        """Determine if a clarifying question should be asked."""
        return (
            not metadata.get("meets_evidence_threshold", False) or
            not metadata.get("meets_source_diversity", False) or
            metadata.get("total_results", 0) < 2
        )
    
    def generate_clarifying_question(self, query: str, metadata: Dict[str, Any]) -> str:
        """Generate a clarifying question based on search metadata."""
        if not metadata.get("meets_evidence_threshold", False):
            return f"I found some information about '{query}', but the evidence quality is low. Could you provide more specific details about what you're looking for?"
        
        if not metadata.get("meets_source_diversity", False):
            return f"I found information about '{query}' from limited sources. Would you like me to search for more specific aspects or different types of information?"
        
        if metadata.get("total_results", 0) < 2:
            return f"I found limited information about '{query}'. Could you clarify what specific aspect you're most interested in?"
        
        return f"I found information about '{query}', but I'd like to ensure I'm providing the most relevant details. Could you specify what particular aspect you need help with?"
