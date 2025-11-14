"""
Cache Integration Service for Warehouse Operational Assistant

Integrates Redis caching with existing query processors and retrieval systems
to provide intelligent caching for SQL results, evidence packs, and vector searches.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import hashlib

from .redis_cache_service import RedisCacheService, CacheType, get_cache_service
from .cache_manager import CacheManager, CachePolicy, CacheWarmingRule, get_cache_manager
from ..structured.sql_query_router import SQLQueryRouter, QueryType
from ..vector.enhanced_retriever import EnhancedVectorRetriever
from ..vector.evidence_scoring import EvidenceScoringEngine, EvidenceScore
from ..query_preprocessing import QueryPreprocessor, PreprocessedQuery

logger = logging.getLogger(__name__)

@dataclass
class CacheIntegrationConfig:
    """Configuration for cache integration."""
    enable_sql_caching: bool = True
    enable_vector_caching: bool = True
    enable_evidence_caching: bool = True
    enable_preprocessing_caching: bool = True
    sql_cache_ttl: int = 300  # 5 minutes
    vector_cache_ttl: int = 180  # 3 minutes
    evidence_cache_ttl: int = 600  # 10 minutes
    preprocessing_cache_ttl: int = 900  # 15 minutes
    warming_enabled: bool = True
    monitoring_enabled: bool = True

class CachedQueryProcessor:
    """
    Query processor with integrated caching for all retrieval types.
    
    Provides intelligent caching for:
    - SQL query results
    - Vector search results
    - Evidence scoring results
    - Query preprocessing results
    """
    
    def __init__(
        self,
        sql_router: SQLQueryRouter,
        vector_retriever: EnhancedVectorRetriever,
        query_preprocessor: QueryPreprocessor,
        evidence_scoring_engine: EvidenceScoringEngine,
        config: Optional[CacheIntegrationConfig] = None
    ):
        self.sql_router = sql_router
        self.vector_retriever = vector_retriever
        self.query_preprocessor = query_preprocessor
        self.evidence_scoring_engine = evidence_scoring_engine
        self.config = config or CacheIntegrationConfig()
        
        self.cache_service: Optional[RedisCacheService] = None
        self.cache_manager: Optional[CacheManager] = None
        
    async def initialize(self) -> None:
        """Initialize cache integration."""
        try:
            # Initialize cache service and manager
            self.cache_service = await get_cache_service()
            self.cache_manager = await get_cache_manager()
            
            # Set up cache warming rules
            if self.config.warming_enabled:
                await self._setup_warming_rules()
            
            logger.info("Cache integration initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize cache integration: {e}")
            raise
    
    async def process_query_with_caching(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Process query with intelligent caching at all levels.
        
        Args:
            query: User query
            context: Additional context
            
        Returns:
            Processed query result with caching metadata
        """
        try:
            result = {
                "query": query,
                "context": context,
                "cache_metadata": {},
                "processing_time": 0,
                "cache_hits": 0,
                "cache_misses": 0
            }
            
            start_time = datetime.now()
            
            # Step 1: Cache query preprocessing
            preprocessed_query = await self._get_cached_preprocessing(query, context)
            result["cache_metadata"]["preprocessing_cached"] = preprocessed_query is not None
            
            if preprocessed_query is None:
                preprocessed_query = await self.query_preprocessor.preprocess_query(query)
                await self._cache_preprocessing(query, context, preprocessed_query)
                result["cache_misses"] += 1
            else:
                result["cache_hits"] += 1
            
            # Step 2: Determine query type and route
            routing_decision = await self.sql_router.route_query(query)
            
            if routing_decision.route_to == "sql":
                # SQL path with caching
                sql_result = await self._get_cached_sql_result(query, context, routing_decision)
                result["cache_metadata"]["sql_cached"] = sql_result is not None
                
                if sql_result is None:
                    sql_result = await self.sql_router.execute_sql_query(query, routing_decision.query_type)
                    await self._cache_sql_result(query, context, routing_decision, sql_result)
                    result["cache_misses"] += 1
                else:
                    result["cache_hits"] += 1
                
                result["data"] = sql_result
                result["route"] = "sql"
                
            else:
                # Vector/hybrid path with caching
                vector_result = await self._get_cached_vector_result(query, context)
                result["cache_metadata"]["vector_cached"] = vector_result is not None
                
                if vector_result is None:
                    vector_result = await self.vector_retriever.search(query)
                    await self._cache_vector_result(query, context, vector_result)
                    result["cache_misses"] += 1
                else:
                    result["cache_hits"] += 1
                
                # Cache evidence scoring if available
                if "evidence_score" in vector_result:
                    evidence_score = await self._get_cached_evidence_score(query, context)
                    if evidence_score is None:
                        evidence_score = vector_result["evidence_score"]
                        await self._cache_evidence_score(query, context, evidence_score)
                        result["cache_misses"] += 1
                    else:
                        result["cache_hits"] += 1
                    
                    result["cache_metadata"]["evidence_cached"] = True
                
                result["data"] = vector_result
                result["route"] = "vector"
            
            result["processing_time"] = (datetime.now() - start_time).total_seconds()
            result["cache_metadata"]["total_cache_hits"] = result["cache_hits"]
            result["cache_metadata"]["total_cache_misses"] = result["cache_misses"]
            
            return result
            
        except Exception as e:
            logger.error(f"Error in cached query processing: {e}")
            # Fallback to non-cached processing
            return await self._fallback_processing(query, context)
    
    async def _get_cached_preprocessing(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]]
    ) -> Optional[PreprocessedQuery]:
        """Get cached query preprocessing result."""
        if not self.config.enable_preprocessing_caching:
            return None
        
        try:
            cache_key = self._generate_cache_key(query, context, "preprocessing")
            cached_data = await self.cache_service.get(cache_key, CacheType.QUERY_PREPROCESSING)
            
            if cached_data:
                # Convert back to PreprocessedQuery
                # Handle the case where some fields might be missing
                return PreprocessedQuery(
                    original_query=cached_data.get('original_query', ''),
                    normalized_query=cached_data.get('normalized_query', ''),
                    intent=cached_data.get('intent', 'workforce'),
                    entities=cached_data.get('entities', {}),
                    keywords=cached_data.get('keywords', []),
                    complexity_score=cached_data.get('complexity_score', 0.5),
                    suggestions=cached_data.get('suggestions', []),
                    context_hints=cached_data.get('context_hints', []),
                    confidence=cached_data.get('confidence', 0.8)
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting cached preprocessing: {e}")
            return None
    
    async def _cache_preprocessing(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]], 
        preprocessed: PreprocessedQuery
    ) -> None:
        """Cache query preprocessing result."""
        if not self.config.enable_preprocessing_caching:
            return
        
        try:
            cache_key = self._generate_cache_key(query, context, "preprocessing")
            # Convert to dictionary for caching
            data = {
                "original_query": getattr(preprocessed, 'original_query', ''),
                "normalized_query": preprocessed.normalized_query,
                "intent": preprocessed.intent.value if hasattr(preprocessed.intent, 'value') else str(preprocessed.intent),
                "entities": preprocessed.entities,
                "keywords": preprocessed.keywords,
                "complexity_score": preprocessed.complexity_score,
                "suggestions": preprocessed.suggestions,
                "context_hints": getattr(preprocessed, 'context_hints', []),
                "confidence": getattr(preprocessed, 'confidence', 0.8)
            }
            
            await self.cache_service.set(
                cache_key, 
                data, 
                CacheType.QUERY_PREPROCESSING,
                ttl=self.config.preprocessing_cache_ttl
            )
            
        except Exception as e:
            logger.error(f"Error caching preprocessing: {e}")
    
    async def _get_cached_sql_result(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]], 
        routing_decision
    ) -> Optional[Dict[str, Any]]:
        """Get cached SQL result."""
        if not self.config.enable_sql_caching:
            return None
        
        try:
            cache_key = self._generate_cache_key(query, context, f"sql_{routing_decision.query_type.value}")
            return await self.cache_service.get(cache_key, CacheType.SQL_RESULT)
            
        except Exception as e:
            logger.error(f"Error getting cached SQL result: {e}")
            return None
    
    async def _cache_sql_result(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]], 
        routing_decision, 
        result: Dict[str, Any]
    ) -> None:
        """Cache SQL result."""
        if not self.config.enable_sql_caching:
            return
        
        try:
            cache_key = self._generate_cache_key(query, context, f"sql_{routing_decision.query_type.value}")
            
            # Add metadata
            cache_data = {
                "result": result,
                "routing_decision": {
                    "route_to": routing_decision.route_to,
                    "query_type": routing_decision.query_type.value,
                    "confidence": routing_decision.confidence
                },
                "cached_at": datetime.now().isoformat()
            }
            
            await self.cache_service.set(
                cache_key, 
                cache_data, 
                CacheType.SQL_RESULT,
                ttl=self.config.sql_cache_ttl
            )
            
        except Exception as e:
            logger.error(f"Error caching SQL result: {e}")
    
    async def _get_cached_vector_result(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Get cached vector search result."""
        if not self.config.enable_vector_caching:
            return None
        
        try:
            cache_key = self._generate_cache_key(query, context, "vector")
            return await self.cache_service.get(cache_key, CacheType.VECTOR_SEARCH)
            
        except Exception as e:
            logger.error(f"Error getting cached vector result: {e}")
            return None
    
    async def _cache_vector_result(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]], 
        result: Dict[str, Any]
    ) -> None:
        """Cache vector search result."""
        if not self.config.enable_vector_caching:
            return
        
        try:
            cache_key = self._generate_cache_key(query, context, "vector")
            
            # Add metadata
            cache_data = {
                "result": result,
                "cached_at": datetime.now().isoformat()
            }
            
            await self.cache_service.set(
                cache_key, 
                cache_data, 
                CacheType.VECTOR_SEARCH,
                ttl=self.config.vector_cache_ttl
            )
            
        except Exception as e:
            logger.error(f"Error caching vector result: {e}")
    
    async def _get_cached_evidence_score(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]]
    ) -> Optional[EvidenceScore]:
        """Get cached evidence score."""
        if not self.config.enable_evidence_caching:
            return None
        
        try:
            cache_key = self._generate_cache_key(query, context, "evidence")
            cached_data = await self.cache_service.get(cache_key, CacheType.EVIDENCE_PACK)
            
            if cached_data:
                return EvidenceScore(**cached_data)
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting cached evidence score: {e}")
            return None
    
    async def _cache_evidence_score(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]], 
        evidence_score: EvidenceScore
    ) -> None:
        """Cache evidence score."""
        if not self.config.enable_evidence_caching:
            return
        
        try:
            cache_key = self._generate_cache_key(query, context, "evidence")
            
            # Convert to dictionary for caching
            data = {
                "overall_score": evidence_score.overall_score,
                "confidence_level": evidence_score.confidence_level,
                "evidence_quality": evidence_score.evidence_quality,
                "validation_status": evidence_score.validation_status,
                "source_diversity": evidence_score.source_diversity,
                "cross_references": evidence_score.cross_references,
                "freshness_score": evidence_score.freshness_score,
                "authority_score": evidence_score.authority_score,
                "similarity_score": evidence_score.similarity_score,
                "scoring_breakdown": evidence_score.scoring_breakdown
            }
            
            await self.cache_service.set(
                cache_key, 
                data, 
                CacheType.EVIDENCE_PACK,
                ttl=self.config.evidence_cache_ttl
            )
            
        except Exception as e:
            logger.error(f"Error caching evidence score: {e}")
    
    def _generate_cache_key(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]], 
        suffix: str
    ) -> str:
        """Generate consistent cache key."""
        key_data = {
            "query": query.lower().strip(),
            "context": context or {},
            "suffix": suffix
        }
        
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    async def _setup_warming_rules(self) -> None:
        """Set up cache warming rules for frequently accessed data."""
        try:
            # Workforce data warming
            workforce_rule = CacheWarmingRule(
                cache_type=CacheType.WORKFORCE_DATA,
                key_pattern="workforce_summary",
                data_generator=self._generate_workforce_data,
                priority=1,
                frequency_minutes=15
            )
            self.cache_manager.add_warming_rule(workforce_rule)
            
            # Task data warming
            task_rule = CacheWarmingRule(
                cache_type=CacheType.TASK_DATA,
                key_pattern="task_summary",
                data_generator=self._generate_task_data,
                priority=1,
                frequency_minutes=10
            )
            self.cache_manager.add_warming_rule(task_rule)
            
            # Equipment data warming
            equipment_rule = CacheWarmingRule(
                cache_type=CacheType.EQUIPMENT_DATA,
                key_pattern="equipment_summary",
                data_generator=self._generate_equipment_data,
                priority=2,
                frequency_minutes=20
            )
            self.cache_manager.add_warming_rule(equipment_rule)
            
            logger.info("Cache warming rules configured")
            
        except Exception as e:
            logger.error(f"Error setting up warming rules: {e}")
    
    async def _generate_workforce_data(self) -> Dict[str, Any]:
        """Generate workforce data for cache warming."""
        # This would typically call the actual workforce data generation
        return {
            "total_workers": 6,
            "shifts": {
                "morning": {"count": 3, "active_tasks": 8},
                "afternoon": {"count": 3, "active_tasks": 6}
            },
            "productivity_metrics": {
                "picks_per_hour": 45.2,
                "packages_per_hour": 38.7,
                "accuracy_rate": 98.5
            }
        }
    
    async def _generate_task_data(self) -> Dict[str, Any]:
        """Generate task data for cache warming."""
        # This would typically call the actual task data generation
        return {
            "total_tasks": 8,
            "pending_tasks": 3,
            "in_progress_tasks": 3,
            "completed_tasks": 2,
            "tasks_by_kind": [
                {"kind": "pack", "count": 2},
                {"kind": "pick", "count": 2},
                {"kind": "inspection", "count": 1}
            ]
        }
    
    async def _generate_equipment_data(self) -> Dict[str, Any]:
        """Generate equipment data for cache warming."""
        # This would typically call the actual equipment data generation
        return {
            "total_equipment": 15,
            "active_equipment": 12,
            "maintenance_due": 3,
            "equipment_types": {
                "forklifts": 5,
                "conveyors": 4,
                "scanners": 6
            }
        }
    
    async def _fallback_processing(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Fallback processing without caching."""
        try:
            # Simple fallback - just return basic processing
            return {
                "query": query,
                "context": context,
                "data": {"message": "Fallback processing - caching unavailable"},
                "route": "fallback",
                "cache_metadata": {"caching_disabled": True},
                "processing_time": 0,
                "cache_hits": 0,
                "cache_misses": 0
            }
            
        except Exception as e:
            logger.error(f"Error in fallback processing: {e}")
            return {
                "query": query,
                "context": context,
                "data": {"error": str(e)},
                "route": "error",
                "cache_metadata": {"error": True},
                "processing_time": 0,
                "cache_hits": 0,
                "cache_misses": 0
            }
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        try:
            if not self.cache_service or not self.cache_manager:
                return {"error": "Cache not initialized"}
            
            # Get basic metrics
            metrics = await self.cache_service.get_metrics()
            
            # Get health information
            health = await self.cache_manager.get_cache_health()
            
            return {
                "metrics": {
                    "hits": metrics.hits,
                    "misses": metrics.misses,
                    "hit_rate": metrics.hit_rate,
                    "total_requests": metrics.total_requests,
                    "memory_usage_mb": metrics.memory_usage / (1024 * 1024),
                    "key_count": metrics.key_count
                },
                "health": health,
                "config": {
                    "sql_caching": self.config.enable_sql_caching,
                    "vector_caching": self.config.enable_vector_caching,
                    "evidence_caching": self.config.enable_evidence_caching,
                    "preprocessing_caching": self.config.enable_preprocessing_caching
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"error": str(e)}

# Global cached query processor instance
_cached_processor: Optional[CachedQueryProcessor] = None

async def get_cached_query_processor() -> CachedQueryProcessor:
    """Get or create the global cached query processor instance."""
    global _cached_processor
    if _cached_processor is None:
        # Import here to avoid circular imports
        from ..structured.sql_query_router import SQLQueryRouter
        from ..vector.enhanced_retriever import EnhancedVectorRetriever
        from ..query_preprocessing import QueryPreprocessor
        from ..vector.evidence_scoring import EvidenceScoringEngine
        
        # Initialize components
        sql_router = SQLQueryRouter(None, None)  # Will be properly initialized
        vector_retriever = EnhancedVectorRetriever()
        query_preprocessor = QueryPreprocessor()
        evidence_scoring_engine = EvidenceScoringEngine()
        
        _cached_processor = CachedQueryProcessor(
            sql_router, vector_retriever, query_preprocessor, evidence_scoring_engine
        )
        await _cached_processor.initialize()
    
    return _cached_processor
