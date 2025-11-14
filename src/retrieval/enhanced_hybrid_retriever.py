"""
Enhanced Hybrid Retriever with Vector Search Optimization

Integrates enhanced chunking, optimized vector retrieval, and intelligent
query routing for improved accuracy and performance.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import asyncio

from .vector.chunking_service import ChunkingService, Chunk
from .vector.enhanced_retriever import EnhancedVectorRetriever, EnhancedSearchResult, RetrievalConfig
from .vector.milvus_retriever import MilvusRetriever
from .vector.embedding_service import EmbeddingService
from .structured.sql_retriever import SQLRetriever
from .structured.inventory_queries import InventoryQueries

logger = logging.getLogger(__name__)

@dataclass
class SearchContext:
    """Enhanced search context with additional metadata."""
    query: str
    search_type: str = "hybrid"  # "sql", "vector", "hybrid"
    limit: int = 6
    score_threshold: float = 0.35
    filters: Optional[Dict[str, Any]] = None
    context: Optional[Dict[str, Any]] = None
    require_clarification: bool = False

@dataclass
class EnhancedSearchResponse:
    """Enhanced search response with detailed metadata."""
    results: List[Any]
    search_type: str
    total_results: int
    evidence_score: float
    confidence_level: str
    sources: List[str]
    categories: List[str]
    requires_clarification: bool
    clarifying_question: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class EnhancedHybridRetriever:
    """
    Enhanced hybrid retriever with vector search optimization.
    
    Features:
    - Intelligent query routing (SQL vs Vector vs Hybrid)
    - Enhanced chunking with 512-token chunks and 64-token overlap
    - Optimized retrieval with top-k=12 → re-rank to 6
    - Evidence scoring and confidence assessment
    - Source diversity validation
    - Clarifying questions for low-confidence scenarios
    """
    
    def __init__(
        self,
        sql_retriever: Optional[SQLRetriever] = None,
        milvus_retriever: Optional[MilvusRetriever] = None,
        embedding_service: Optional[EmbeddingService] = None,
        retrieval_config: Optional[RetrievalConfig] = None
    ):
        self.sql_retriever = sql_retriever
        self.milvus_retriever = milvus_retriever
        self.embedding_service = embedding_service
        
        # Initialize chunking service
        self.chunking_service = ChunkingService(
            chunk_size=512,
            overlap_size=64,
            min_chunk_size=100
        )
        
        # Initialize enhanced vector retriever
        if milvus_retriever and embedding_service:
            self.enhanced_vector_retriever = EnhancedVectorRetriever(
                milvus_retriever=milvus_retriever,
                embedding_service=embedding_service,
                config=retrieval_config
            )
        else:
            self.enhanced_vector_retriever = None
        
        # Initialize inventory queries
        if sql_retriever:
            self.inventory_queries = InventoryQueries(sql_retriever)
        else:
            self.inventory_queries = None
        
        # SQL query keywords for routing
        self.sql_keywords = {
            'atp', 'available_to_promise', 'quantity', 'stock', 'inventory',
            'equipment_status', 'location', 'sku', 'item', 'count',
            'on_hand', 'reserved', 'allocated', 'available'
        }
        
        logger.info("EnhancedHybridRetriever initialized")
    
    async def initialize(self) -> None:
        """Initialize the hybrid retriever with all required services."""
        try:
            # Import here to avoid circular imports
            from .structured.sql_retriever import get_sql_retriever
            from .vector.milvus_retriever import get_milvus_retriever
            from .vector.embedding_service import get_embedding_service
            
            # Initialize services if not provided
            if not self.sql_retriever:
                self.sql_retriever = await get_sql_retriever()
                self.inventory_queries = InventoryQueries(self.sql_retriever)
            
            if not self.milvus_retriever:
                self.milvus_retriever = await get_milvus_retriever()
            
            if not self.embedding_service:
                self.embedding_service = await get_embedding_service()
            
            # Re-initialize enhanced vector retriever with services
            if self.milvus_retriever and self.embedding_service:
                self.enhanced_vector_retriever = EnhancedVectorRetriever(
                    milvus_retriever=self.milvus_retriever,
                    embedding_service=self.embedding_service,
                    config=RetrievalConfig()
                )
            
            logger.info("EnhancedHybridRetriever fully initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize EnhancedHybridRetriever: {e}")
            raise
    
    async def search(self, context: SearchContext) -> EnhancedSearchResponse:
        """
        Perform enhanced hybrid search with optimization.
        
        Args:
            context: Search context with query and parameters
            
        Returns:
            Enhanced search response with detailed metadata
        """
        try:
            # Determine search type
            search_type = self._classify_query_type(context.query, context.search_type)
            
            # Route to appropriate search method
            if search_type == "sql":
                return await self._search_sql(context)
            elif search_type == "vector":
                return await self._search_vector(context)
            else:  # hybrid
                return await self._search_hybrid(context)
                
        except Exception as e:
            logger.error(f"Enhanced search failed: {e}")
            return EnhancedSearchResponse(
                results=[],
                search_type="error",
                total_results=0,
                evidence_score=0.0,
                confidence_level="low",
                sources=[],
                categories=[],
                requires_clarification=True,
                clarifying_question=f"I encountered an error while searching: {str(e)}. Could you please rephrase your question?",
                metadata={"error": str(e)}
            )
    
    def _classify_query_type(self, query: str, preferred_type: str) -> str:
        """Classify query type for optimal routing."""
        if preferred_type != "hybrid":
            return preferred_type
        
        query_lower = query.lower()
        
        # Check for SQL-specific keywords
        sql_keyword_count = sum(1 for keyword in self.sql_keywords if keyword in query_lower)
        
        # Check for vector-specific keywords
        vector_keywords = {
            'how', 'what', 'why', 'when', 'where', 'explain', 'describe',
            'procedure', 'process', 'safety', 'compliance', 'policy',
            'manual', 'guide', 'instruction', 'training'
        }
        vector_keyword_count = sum(1 for keyword in vector_keywords if keyword in query_lower)
        
        # Route based on keyword density
        if sql_keyword_count >= 2:
            return "sql"
        elif vector_keyword_count >= 2:
            return "vector"
        elif sql_keyword_count > 0:
            return "sql"
        else:
            return "hybrid"
    
    async def _search_sql(self, context: SearchContext) -> EnhancedSearchResponse:
        """Perform SQL-based search for structured data."""
        try:
            if not self.inventory_queries:
                return self._create_error_response("SQL retriever not available")
            
            # Extract SKU if present
            sku = self._extract_sku_from_query(context.query)
            
            if sku:
                # Single item lookup
                item = await self.inventory_queries.get_item_by_sku(sku)
                results = [item] if item else []
            else:
                # General search
                search_results = await self.inventory_queries.search_items(
                    search_term=context.query,
                    limit=context.limit
                )
                results = search_results.items if search_results else []
            
            # Calculate evidence score for SQL results
            evidence_score = self._calculate_sql_evidence_score(results, context.query)
            
            return EnhancedSearchResponse(
                results=results,
                search_type="sql",
                total_results=len(results),
                evidence_score=evidence_score,
                confidence_level="high" if evidence_score >= 0.8 else "medium" if evidence_score >= 0.5 else "low",
                sources=["inventory_database"],
                categories=["equipment", "inventory"],
                requires_clarification=evidence_score < 0.35,
                clarifying_question=self._generate_sql_clarifying_question(context.query, results) if evidence_score < 0.35 else None,
                metadata={"sql_query_type": "sku_lookup" if sku else "general_search"}
            )
            
        except Exception as e:
            logger.error(f"SQL search failed: {e}")
            return self._create_error_response(f"SQL search failed: {str(e)}")
    
    async def _search_vector(self, context: SearchContext) -> EnhancedSearchResponse:
        """Perform vector-based search for unstructured data."""
        try:
            if not self.enhanced_vector_retriever:
                return self._create_error_response("Vector retriever not available")
            
            # Perform enhanced vector search
            results, metadata = await self.enhanced_vector_retriever.search(
                query=context.query,
                filters=context.filters,
                context=context.context
            )
            
            # Check if clarifying question is needed
            requires_clarification = self.enhanced_vector_retriever.should_ask_clarifying_question(metadata)
            clarifying_question = None
            
            if requires_clarification:
                clarifying_question = self.enhanced_vector_retriever.generate_clarifying_question(
                    context.query, metadata
                )
            
            # Extract sources and categories
            sources = list(set(result.chunk.metadata.source_id for result in results))
            categories = list(set(result.chunk.metadata.category for result in results))
            
            return EnhancedSearchResponse(
                results=results,
                search_type="vector",
                total_results=len(results),
                evidence_score=metadata.get("avg_evidence_score", 0.0),
                confidence_level=metadata.get("confidence_level", "low"),
                sources=sources,
                categories=categories,
                requires_clarification=requires_clarification,
                clarifying_question=clarifying_question,
                metadata=metadata
            )
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return self._create_error_response(f"Vector search failed: {str(e)}")
    
    async def _search_hybrid(self, context: SearchContext) -> EnhancedSearchResponse:
        """Perform hybrid search combining SQL and vector results."""
        try:
            # Perform both SQL and vector searches in parallel
            sql_task = self._search_sql(context) if self.inventory_queries else None
            vector_task = self._search_vector(context) if self.enhanced_vector_retriever else None
            
            # Wait for both searches to complete
            results = await asyncio.gather(
                sql_task or asyncio.create_task(self._create_empty_response()),
                vector_task or asyncio.create_task(self._create_empty_response()),
                return_exceptions=True
            )
            
            sql_response = results[0] if not isinstance(results[0], Exception) else None
            vector_response = results[1] if not isinstance(results[1], Exception) else None
            
            # Combine results
            combined_results = []
            combined_sources = []
            combined_categories = []
            
            if sql_response and sql_response.results:
                combined_results.extend(sql_response.results)
                combined_sources.extend(sql_response.sources)
                combined_categories.extend(sql_response.categories)
            
            if vector_response and vector_response.results:
                combined_results.extend(vector_response.results)
                combined_sources.extend(vector_response.sources)
                combined_categories.extend(vector_response.categories)
            
            # Calculate combined evidence score
            evidence_scores = []
            if sql_response:
                evidence_scores.append(sql_response.evidence_score)
            if vector_response:
                evidence_scores.append(vector_response.evidence_score)
            
            combined_evidence_score = sum(evidence_scores) / len(evidence_scores) if evidence_scores else 0.0
            
            # Determine if clarification is needed
            requires_clarification = (
                combined_evidence_score < 0.35 or
                len(set(combined_sources)) < 2 or
                len(combined_results) < 2
            )
            
            clarifying_question = None
            if requires_clarification:
                if vector_response and vector_response.clarifying_question:
                    clarifying_question = vector_response.clarifying_question
                else:
                    clarifying_question = f"I found some information about '{context.query}', but I'd like to ensure I'm providing the most relevant details. Could you clarify what specific aspect you need help with?"
            
            return EnhancedSearchResponse(
                results=combined_results,
                search_type="hybrid",
                total_results=len(combined_results),
                evidence_score=combined_evidence_score,
                confidence_level="high" if combined_evidence_score >= 0.8 else "medium" if combined_evidence_score >= 0.5 else "low",
                sources=list(set(combined_sources)),
                categories=list(set(combined_categories)),
                requires_clarification=requires_clarification,
                clarifying_question=clarifying_question,
                metadata={
                    "sql_results": len(sql_response.results) if sql_response else 0,
                    "vector_results": len(vector_response.results) if vector_response else 0,
                    "combined_evidence_score": combined_evidence_score
                }
            )
            
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return self._create_error_response(f"Hybrid search failed: {str(e)}")
    
    def _extract_sku_from_query(self, query: str) -> Optional[str]:
        """Extract SKU from query using regex patterns."""
        import re
        
        # Common SKU patterns
        sku_patterns = [
            r'SKU\s*:?\s*([A-Z0-9-]+)',
            r'sku\s*:?\s*([A-Z0-9-]+)',
            r'item\s*:?\s*([A-Z0-9-]+)',
            r'part\s*:?\s*([A-Z0-9-]+)',
            r'\b([A-Z]{2,}\d{3,})\b',  # Pattern like SKU123, EQ456
            r'\b([A-Z0-9-]{6,})\b'     # General alphanumeric pattern
        ]
        
        for pattern in sku_patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        
        return None
    
    def _calculate_sql_evidence_score(self, results: List[Any], query: str) -> float:
        """Calculate evidence score for SQL results."""
        if not results:
            return 0.0
        
        # Base score from result count
        base_score = min(len(results) / 5.0, 1.0)
        
        # Boost for exact matches
        query_lower = query.lower()
        exact_match_boost = 0.0
        
        for result in results:
            if hasattr(result, 'name') and query_lower in result.name.lower():
                exact_match_boost += 0.2
            if hasattr(result, 'sku') and query_lower in str(result.sku).lower():
                exact_match_boost += 0.3
        
        evidence_score = base_score + min(exact_match_boost, 0.5)
        return min(evidence_score, 1.0)
    
    def _generate_sql_clarifying_question(self, query: str, results: List[Any]) -> str:
        """Generate clarifying question for SQL results."""
        if not results:
            return f"I couldn't find any equipment matching '{query}'. Could you provide a specific SKU or equipment name?"
        
        if len(results) > 10:
            return f"I found many results for '{query}'. Could you be more specific about which equipment or location you're interested in?"
        
        return f"I found {len(results)} results for '{query}'. Could you specify which particular equipment or aspect you need information about?"
    
    def _create_error_response(self, error_message: str) -> EnhancedSearchResponse:
        """Create error response."""
        return EnhancedSearchResponse(
            results=[],
            search_type="error",
            total_results=0,
            evidence_score=0.0,
            confidence_level="low",
            sources=[],
            categories=[],
            requires_clarification=True,
            clarifying_question=f"I encountered an issue: {error_message}. Could you please rephrase your question?",
            metadata={"error": error_message}
        )
    
    async def _create_empty_response(self) -> EnhancedSearchResponse:
        """Create empty response for failed searches."""
        return EnhancedSearchResponse(
            results=[],
            search_type="empty",
            total_results=0,
            evidence_score=0.0,
            confidence_level="low",
            sources=[],
            categories=[],
            requires_clarification=False,
            metadata={}
        )
    
    async def add_documents(
        self,
        documents: List[Dict[str, Any]],
        source_id: str,
        source_type: str = "document"
    ) -> bool:
        """Add documents to the vector database with enhanced chunking."""
        try:
            if not self.enhanced_vector_retriever:
                logger.warning("Vector retriever not available for document addition")
                return False
            
            # Process each document
            all_chunks = []
            for doc in documents:
                content = doc.get('content', '')
                category = doc.get('category', 'general')
                section = doc.get('section')
                page_number = doc.get('page_number')
                
                # Create chunks
                chunks = self.chunking_service.create_chunks(
                    text=content,
                    source_id=source_id,
                    source_type=source_type,
                    category=category,
                    section=section,
                    page_number=page_number
                )
                
                all_chunks.extend(chunks)
            
            # Convert chunks to documents for Milvus
            documents_for_milvus = []
            for chunk in all_chunks:
                doc = {
                    'id': chunk.metadata.chunk_id,
                    'content': chunk.content,
                    'source_id': chunk.metadata.source_id,
                    'source_type': chunk.metadata.source_type,
                    'chunk_index': chunk.metadata.chunk_index,
                    'total_chunks': chunk.metadata.total_chunks,
                    'token_count': chunk.metadata.token_count,
                    'start_position': chunk.metadata.start_position,
                    'end_position': chunk.metadata.end_position,
                    'created_at': chunk.metadata.created_at.isoformat() if chunk.metadata.created_at else None,
                    'quality_score': chunk.metadata.quality_score,
                    'keywords': chunk.metadata.keywords,
                    'category': chunk.metadata.category,
                    'section': chunk.metadata.section,
                    'page_number': chunk.metadata.page_number
                }
                documents_for_milvus.append(doc)
            
            # Insert into Milvus
            success = await self.milvus_retriever.insert_documents(documents_for_milvus)
            
            if success:
                logger.info(f"Successfully added {len(all_chunks)} chunks from {len(documents)} documents")
            else:
                logger.error("Failed to add documents to vector database")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to add documents: {e}")
            return False
