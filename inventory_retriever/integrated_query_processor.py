"""
Integrated Query Processing Pipeline for Warehouse Operational Assistant

This module provides a unified interface that combines query preprocessing,
intelligent routing, execution, and result post-processing.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass
from datetime import datetime, timezone
import asyncio

from .query_preprocessing import QueryPreprocessor, PreprocessedQuery
from .structured.sql_query_router import SQLQueryRouter, RoutingDecision, QueryType
from .result_postprocessing import ResultPostProcessor, ProcessedResult, ResultType
from .enhanced_hybrid_retriever import EnhancedHybridRetriever
from .structured.sql_retriever import SQLRetriever

logger = logging.getLogger(__name__)


@dataclass
class QueryProcessingResult:
    """Complete result of query processing pipeline."""
    query: str
    preprocessed_query: PreprocessedQuery
    routing_decision: RoutingDecision
    execution_result: Any
    processed_result: ProcessedResult
    execution_time: float
    success: bool
    error_message: Optional[str] = None


class IntegratedQueryProcessor:
    """
    Integrated query processing pipeline.
    
    This class orchestrates the complete query processing workflow:
    1. Query preprocessing and normalization
    2. Intelligent routing (SQL vs Hybrid RAG)
    3. Query execution with optimization
    4. Result post-processing and quality assessment
    5. Fallback mechanisms for error handling
    """
    
    def __init__(
        self,
        sql_retriever: SQLRetriever,
        hybrid_retriever: EnhancedHybridRetriever
    ):
        self.sql_retriever = sql_retriever
        self.hybrid_retriever = hybrid_retriever
        
        # Initialize components
        self.query_preprocessor = QueryPreprocessor()
        self.sql_router = SQLQueryRouter(sql_retriever, hybrid_retriever)
        self.result_processor = ResultPostProcessor()
        
        # Processing statistics
        self.stats = {
            'total_queries': 0,
            'sql_queries': 0,
            'hybrid_queries': 0,
            'fallback_queries': 0,
            'successful_queries': 0,
            'failed_queries': 0,
            'average_execution_time': 0.0
        }
    
    async def process_query(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
        enable_fallback: bool = True
    ) -> QueryProcessingResult:
        """
        Process a query through the complete pipeline.
        
        Args:
            query: User query string
            context: Additional context for processing
            enable_fallback: Whether to enable fallback mechanisms
            
        Returns:
            QueryProcessingResult with complete processing information
        """
        start_time = datetime.now()
        self.stats['total_queries'] += 1
        
        try:
            # Step 1: Preprocess the query
            preprocessed_query = await self.query_preprocessor.preprocess_query(query, context)
            
            # Step 2: Determine routing
            routing_decision = await self.sql_router.route_query(
                preprocessed_query.normalized_query, 
                context
            )
            
            # Step 3: Execute query based on routing decision
            execution_result, execution_route, execution_metadata = await self._execute_query(
                preprocessed_query, 
                routing_decision, 
                context, 
                enable_fallback
            )
            
            # Step 4: Determine result type for post-processing
            result_type = self._determine_result_type(execution_route, routing_decision)
            
            # Step 5: Post-process results
            processed_result = await self.result_processor.process_result(
                execution_result,
                result_type,
                context
            )
            
            # Update routing decision with actual execution route
            routing_decision.route_to = execution_route
            
            # Calculate execution time
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # Update statistics
            self._update_stats(execution_route, True, execution_time)
            
            return QueryProcessingResult(
                query=query,
                preprocessed_query=preprocessed_query,
                routing_decision=routing_decision,
                execution_result=execution_result,
                processed_result=processed_result,
                execution_time=execution_time,
                success=True
            )
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"Query processing failed: {e}")
            
            # Update statistics
            self._update_stats("error", False, execution_time)
            
            return QueryProcessingResult(
                query=query,
                preprocessed_query=PreprocessedQuery(
                    original_query=query,
                    normalized_query=query.lower().strip(),
                    intent=None,
                    entities={},
                    keywords=[],
                    context_hints=[],
                    complexity_score=0.0,
                    confidence=0.0,
                    suggestions=[]
                ),
                routing_decision=RoutingDecision(
                    route_to="error",
                    query_type=QueryType.UNKNOWN,
                    confidence=0.0,
                    reasoning=f"Processing error: {str(e)}",
                    optimization_applied=[],
                    fallback_available=False
                ),
                execution_result=[],
                processed_result=ProcessedResult(
                    original_data=[],
                    processed_data=[],
                    result_type=ResultType.ERROR,
                    data_quality=None,
                    confidence=0.0,
                    metadata={'error': str(e)},
                    warnings=[f"Processing error: {str(e)}"],
                    suggestions=["Contact support if this error persists"]
                ),
                execution_time=execution_time,
                success=False,
                error_message=str(e)
            )
    
    async def _execute_query(
        self,
        preprocessed_query: PreprocessedQuery,
        routing_decision: RoutingDecision,
        context: Optional[Dict[str, Any]],
        enable_fallback: bool
    ) -> Tuple[Any, str, Dict[str, Any]]:
        """Execute query based on routing decision."""
        try:
            if routing_decision.route_to == "sql":
                # Execute SQL query
                sql_result = await self.sql_router.execute_sql_query(
                    preprocessed_query.normalized_query,
                    routing_decision.query_type,
                    context
                )
                
                if sql_result.success and sql_result.quality_score > 0.7:
                    return (
                        sql_result.data,
                        "sql",
                        {
                            "execution_time": sql_result.execution_time,
                            "quality_score": sql_result.quality_score,
                            "row_count": sql_result.row_count,
                            "warnings": sql_result.warnings
                        }
                    )
                elif enable_fallback:
                    # SQL failed or low quality, fallback to hybrid RAG
                    logger.warning(f"SQL query failed or low quality, falling back to hybrid RAG")
                    return await self._execute_hybrid_fallback(preprocessed_query, context)
                else:
                    return (sql_result.data, "sql", {"error": "SQL execution failed"})
            
            elif routing_decision.route_to == "hybrid_rag":
                # Execute hybrid RAG query
                return await self._execute_hybrid_query(preprocessed_query, context)
            
            else:
                # Fallback to hybrid RAG
                return await self._execute_hybrid_fallback(preprocessed_query, context)
                
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            if enable_fallback:
                return await self._execute_hybrid_fallback(preprocessed_query, context)
            else:
                raise
    
    async def _execute_hybrid_query(
        self,
        preprocessed_query: PreprocessedQuery,
        context: Optional[Dict[str, Any]]
    ) -> Tuple[Any, str, Dict[str, Any]]:
        """Execute hybrid RAG query."""
        try:
            # Enhance query for hybrid RAG routing
            enhanced_query = await self.query_preprocessor.enhance_query_for_routing(
                preprocessed_query,
                "hybrid_rag"
            )
            
            # Execute hybrid retrieval
            results, metadata = await self.hybrid_retriever.retrieve(enhanced_query, context)
            
            return (results, "hybrid_rag", metadata)
            
        except Exception as e:
            logger.error(f"Hybrid RAG execution failed: {e}")
            raise
    
    async def _execute_hybrid_fallback(
        self,
        preprocessed_query: PreprocessedQuery,
        context: Optional[Dict[str, Any]]
    ) -> Tuple[Any, str, Dict[str, Any]]:
        """Execute hybrid RAG as fallback."""
        try:
            # Use original query for fallback
            results, metadata = await self.hybrid_retriever.retrieve(
                preprocessed_query.original_query, 
                context
            )
            
            return (results, "fallback", metadata)
            
        except Exception as e:
            logger.error(f"Hybrid RAG fallback failed: {e}")
            # Return empty result as final fallback
            return ([], "error", {"error": str(e)})
    
    def _determine_result_type(
        self, 
        execution_route: str, 
        routing_decision: RoutingDecision
    ) -> ResultType:
        """Determine result type for post-processing."""
        if execution_route == "sql":
            return ResultType.SQL_DATA
        elif execution_route in ["hybrid_rag", "fallback"]:
            return ResultType.HYBRID_RAG
        else:
            return ResultType.ERROR
    
    def _update_stats(self, route: str, success: bool, execution_time: float):
        """Update processing statistics."""
        if success:
            self.stats['successful_queries'] += 1
        else:
            self.stats['failed_queries'] += 1
        
        if route == "sql":
            self.stats['sql_queries'] += 1
        elif route in ["hybrid_rag", "fallback"]:
            self.stats['hybrid_queries'] += 1
        elif route == "fallback":
            self.stats['fallback_queries'] += 1
        
        # Update average execution time
        total_queries = self.stats['successful_queries'] + self.stats['failed_queries']
        if total_queries > 0:
            current_avg = self.stats['average_execution_time']
            self.stats['average_execution_time'] = (
                (current_avg * (total_queries - 1) + execution_time) / total_queries
            )
    
    async def get_processing_stats(self) -> Dict[str, Any]:
        """Get current processing statistics."""
        return self.stats.copy()
    
    async def reset_stats(self):
        """Reset processing statistics."""
        self.stats = {
            'total_queries': 0,
            'sql_queries': 0,
            'hybrid_queries': 0,
            'fallback_queries': 0,
            'successful_queries': 0,
            'failed_queries': 0,
            'average_execution_time': 0.0
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on all components."""
        health_status = {
            'overall_status': 'healthy',
            'components': {},
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        try:
            # Check SQL retriever
            try:
                await self.sql_retriever.initialize()
                health_status['components']['sql_retriever'] = 'healthy'
            except Exception as e:
                health_status['components']['sql_retriever'] = f'unhealthy: {str(e)}'
                health_status['overall_status'] = 'degraded'
            
            # Check hybrid retriever
            try:
                # Simple test query
                test_results, _ = await self.hybrid_retriever.retrieve("test query")
                health_status['components']['hybrid_retriever'] = 'healthy'
            except Exception as e:
                health_status['components']['hybrid_retriever'] = f'unhealthy: {str(e)}'
                health_status['overall_status'] = 'degraded'
            
            # Check query preprocessor
            try:
                test_preprocessed = await self.query_preprocessor.preprocess_query("test query")
                health_status['components']['query_preprocessor'] = 'healthy'
            except Exception as e:
                health_status['components']['query_preprocessor'] = f'unhealthy: {str(e)}'
                health_status['overall_status'] = 'degraded'
            
            # Check result processor
            try:
                test_processed = await self.result_processor.process_result([], ResultType.SQL_DATA)
                health_status['components']['result_processor'] = 'healthy'
            except Exception as e:
                health_status['components']['result_processor'] = f'unhealthy: {str(e)}'
                health_status['overall_status'] = 'degraded'
            
        except Exception as e:
            health_status['overall_status'] = 'unhealthy'
            health_status['error'] = str(e)
        
        return health_status
    
    async def process_batch_queries(
        self,
        queries: List[str],
        context: Optional[Dict[str, Any]] = None
    ) -> List[QueryProcessingResult]:
        """Process multiple queries in batch."""
        tasks = []
        for query in queries:
            task = self.process_query(query, context)
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle any exceptions
        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append(QueryProcessingResult(
                    query=queries[i],
                    preprocessed_query=PreprocessedQuery(
                        original_query=queries[i],
                        normalized_query=queries[i].lower().strip(),
                        intent=None,
                        entities={},
                        keywords=[],
                        context_hints=[],
                        complexity_score=0.0,
                        confidence=0.0,
                        suggestions=[]
                    ),
                    routing_decision=RoutingDecision(
                        route_to="error",
                        query_type=QueryType.UNKNOWN,
                        confidence=0.0,
                        reasoning=f"Batch processing error: {str(result)}",
                        optimization_applied=[],
                        fallback_available=False
                    ),
                    execution_result=[],
                    processed_result=ProcessedResult(
                        original_data=[],
                        processed_data=[],
                        result_type=ResultType.ERROR,
                        data_quality=None,
                        confidence=0.0,
                        metadata={'error': str(result)},
                        warnings=[f"Batch processing error: {str(result)}"],
                        suggestions=["Contact support if this error persists"]
                    ),
                    execution_time=0.0,
                    success=False,
                    error_message=str(result)
                ))
            else:
                processed_results.append(result)
        
        return processed_results
