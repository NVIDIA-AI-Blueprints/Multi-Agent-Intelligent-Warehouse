"""
SQL Query Router for Warehouse Operational Assistant

This module provides intelligent routing between SQL and hybrid RAG systems,
with query classification, optimization, validation, and fallback mechanisms.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timezone
import asyncio

from ..enhanced_hybrid_retriever import EnhancedHybridRetriever
from .sql_retriever import SQLRetriever

logger = logging.getLogger(__name__)


class QueryType(Enum):
    """Types of queries that can be processed."""
    SQL_ATP = "sql_atp"  # Available to Promise queries
    SQL_QUANTITY = "sql_quantity"  # Quantity/stock queries
    SQL_EQUIPMENT_STATUS = "sql_equipment_status"  # Equipment status queries
    SQL_MAINTENANCE = "sql_maintenance"  # Maintenance queries
    SQL_LOCATION = "sql_location"  # Location-based queries
    HYBRID_RAG = "hybrid_rag"  # Complex queries requiring RAG
    UNKNOWN = "unknown"  # Unclassifiable queries


class QueryComplexity(Enum):
    """Query complexity levels."""
    SIMPLE = "simple"  # Single table, basic conditions
    MODERATE = "moderate"  # Joins, aggregations
    COMPLEX = "complex"  # Multiple joins, subqueries, complex logic


@dataclass
class QueryClassification:
    """Result of query classification."""
    query_type: QueryType
    complexity: QueryComplexity
    confidence: float
    sql_optimizable: bool
    suggested_route: str
    reasoning: str
    entities: Dict[str, Any]
    keywords: List[str]


@dataclass
class SQLQueryResult:
    """Result of SQL query execution."""
    success: bool
    data: List[Dict[str, Any]]
    execution_time: float
    row_count: int
    query_type: QueryType
    quality_score: float
    errors: List[str]
    warnings: List[str]


@dataclass
class RoutingDecision:
    """Final routing decision for a query."""
    route_to: str  # "sql", "hybrid_rag", "fallback"
    query_type: QueryType
    confidence: float
    reasoning: str
    optimization_applied: List[str]
    fallback_available: bool


class SQLQueryRouter:
    """
    Intelligent SQL query router with classification, optimization, and fallback.
    
    This class determines whether queries should be handled by SQL or hybrid RAG,
    optimizes SQL queries for performance, and provides fallback mechanisms.
    """
    
    def __init__(
        self,
        sql_retriever: SQLRetriever,
        hybrid_retriever: EnhancedHybridRetriever
    ):
        self.sql_retriever = sql_retriever
        self.hybrid_retriever = hybrid_retriever
        
        # Query patterns for classification
        self.sql_patterns = {
            QueryType.SQL_ATP: [
                r'\b(?:atp|available to promise|available_to_promise)\b',
                r'\b(?:how many|quantity|available|in stock)\b.*\b(?:sku\d+|item|product)\b',
                r'\b(?:can we fulfill|fulfillment|promise)\b',
                r'\b(?:show me|what is|how many)\b.*\b(?:available|atp|quantity)\b'
            ],
            QueryType.SQL_QUANTITY: [
                r'\b(?:quantity|qty|amount|count|number)\b.*\b(?:sku\d+|item|product)\b',
                r'\b(?:how many|total|sum)\b.*\b(?:in stock|available)\b',
                r'\b(?:stock level|inventory level)\b',
                r'\b(?:show me|what is)\b.*\b(?:quantity|stock|available)\b'
            ],
            QueryType.SQL_EQUIPMENT_STATUS: [
                r'\b(?:equipment|machine|forklift|conveyor|scanner)\b.*\b(?:status|working|operational)\b',
                r'\b(?:is.*working|is.*operational|is.*available)\b.*\b(?:equipment|machine)\b',
                r'\b(?:equipment status|machine status|operational status)\b',
                r'\b(?:show me|what is)\b.*\b(?:equipment|machine|forklift|conveyor)\b.*\b(?:status)\b'
            ],
            QueryType.SQL_MAINTENANCE: [
                r'\b(?:maintenance|repair|service|checkup)\b.*\b(?:due|scheduled|needed)\b',
                r'\b(?:when.*maintenance|next.*service|maintenance.*schedule)\b',
                r'\b(?:preventive|routine|scheduled)\b.*\b(?:maintenance|service)\b',
                r'\b(?:show me|what)\b.*\b(?:maintenance|repair|service)\b'
            ],
            QueryType.SQL_LOCATION: [
                r'\b(?:where.*located|location|position|zone|area)\b.*\b(?:sku\d+|item|equipment)\b',
                r'\b(?:find.*location|locate.*item|where.*is)\b',
                r'\b(?:warehouse.*zone|storage.*area|pick.*location)\b',
                r'\b(?:show me|what)\b.*\b(?:location|zone|area)\b'
            ]
        }
        
        # Keywords that suggest hybrid RAG (more specific to avoid false positives)
        self.hybrid_keywords = [
            'how to', 'explain', 'describe', 'procedure', 'process',
            'best practice', 'recommendation', 'guidance', 'troubleshoot',
            'why', 'when should', 'what happens if', 'compare', 'difference',
            'how do i', 'step by step', 'instructions', 'manual', 'guide'
        ]
        
        # SQL optimization rules
        self.optimization_rules = {
            'add_indexes': True,
            'limit_results': True,
            'use_views': True,
            'cache_frequent': True,
            'parallel_execution': True
        }
    
    async def route_query(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> RoutingDecision:
        """
        Route a query to the appropriate processing system.
        
        Args:
            query: User query string
            context: Additional context for routing decision
            
        Returns:
            RoutingDecision with routing information
        """
        try:
            # Step 1: Classify the query
            classification = await self._classify_query(query, context)
            
            # Step 2: Determine routing strategy
            routing_decision = await self._determine_routing(classification, query, context)
            
            # Step 3: Apply optimizations if SQL route
            if routing_decision.route_to == "sql":
                routing_decision.optimization_applied = await self._apply_sql_optimizations(
                    query, classification
                )
            
            logger.info(f"Query routed: {query[:50]}... -> {routing_decision.route_to}")
            return routing_decision
            
        except Exception as e:
            logger.error(f"Error in query routing: {e}")
            # Fallback to hybrid RAG on error
            return RoutingDecision(
                route_to="fallback",
                query_type=QueryType.UNKNOWN,
                confidence=0.0,
                reasoning=f"Routing error, fallback to hybrid RAG: {str(e)}",
                optimization_applied=[],
                fallback_available=True
            )
    
    async def _classify_query(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> QueryClassification:
        """Classify query type and complexity."""
        query_lower = query.lower()
        entities = await self._extract_entities(query)
        keywords = await self._extract_keywords(query)
        
        # Check for hybrid RAG indicators first
        if any(keyword in query_lower for keyword in self.hybrid_keywords):
            return QueryClassification(
                query_type=QueryType.HYBRID_RAG,
                complexity=QueryComplexity.MODERATE,
                confidence=0.9,
                sql_optimizable=False,
                suggested_route="hybrid_rag",
                reasoning="Contains hybrid RAG keywords",
                entities=entities,
                keywords=keywords
            )
        
        # Check SQL patterns
        best_match = None
        best_confidence = 0.0
        
        for query_type, patterns in self.sql_patterns.items():
            for pattern in patterns:
                if re.search(pattern, query_lower, re.IGNORECASE):
                    confidence = self._calculate_pattern_confidence(pattern, query_lower)
                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_match = query_type
        
        if best_match and best_confidence > 0.6:
            complexity = self._assess_complexity(query, entities)
            return QueryClassification(
                query_type=best_match,
                complexity=complexity,
                confidence=best_confidence,
                sql_optimizable=True,
                suggested_route="sql",
                reasoning=f"Matched {best_match.value} pattern with {best_confidence:.2f} confidence",
                entities=entities,
                keywords=keywords
            )
        
        # Default to hybrid RAG for unclassified queries
        return QueryClassification(
            query_type=QueryType.HYBRID_RAG,
            complexity=QueryComplexity.MODERATE,
            confidence=0.5,
            sql_optimizable=False,
            suggested_route="hybrid_rag",
            reasoning="No clear SQL pattern match, defaulting to hybrid RAG",
            entities=entities,
            keywords=keywords
        )
    
    async def _extract_entities(self, query: str) -> Dict[str, Any]:
        """Extract entities from query."""
        entities = {}
        
        # Extract SKUs
        sku_pattern = r'SKU\d+'
        skus = re.findall(sku_pattern, query.upper())
        if skus:
            entities['skus'] = skus
        
        # Extract equipment types
        equipment_patterns = [
            r'\b(forklift|conveyor|scanner|pallet.*jack|amr|agv|robot)\b',
            r'\b(equipment|machine|device|tool)\b'
        ]
        equipment = []
        for pattern in equipment_patterns:
            matches = re.findall(pattern, query.lower())
            equipment.extend(matches)
        if equipment:
            entities['equipment'] = list(set(equipment))
        
        # Extract locations
        location_patterns = [
            r'\b(zone|area|section|bay|aisle)\s+[a-zA-Z0-9]+',
            r'\b(warehouse|storage|pick|receive|ship)\b'
        ]
        locations = []
        for pattern in location_patterns:
            matches = re.findall(pattern, query.lower())
            locations.extend(matches)
        if locations:
            entities['locations'] = list(set(locations))
        
        return entities
    
    async def _extract_keywords(self, query: str) -> List[str]:
        """Extract important keywords from query."""
        # Remove common stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        
        # Extract words
        words = re.findall(r'\b\w+\b', query.lower())
        keywords = [word for word in words if word not in stop_words and len(word) > 2]
        
        return keywords[:10]  # Limit to top 10 keywords
    
    def _calculate_pattern_confidence(self, pattern: str, query: str) -> float:
        """Calculate confidence score for pattern matching."""
        matches = re.findall(pattern, query, re.IGNORECASE)
        if not matches:
            return 0.0
        
        # Base confidence on pattern complexity and match quality
        # Simple patterns get higher confidence
        if len(pattern) < 50:  # Simple pattern
            base_confidence = 0.8
        else:  # Complex pattern
            base_confidence = 0.7
        
        # Boost confidence for multiple matches
        match_boost = min(0.2, len(matches) * 0.1)
        
        # Boost confidence for longer matches
        avg_match_length = sum(len(match) for match in matches) / len(matches)
        length_boost = min(0.1, avg_match_length / 100)
        
        return min(0.95, base_confidence + match_boost + length_boost)
    
    def _assess_complexity(self, query: str, entities: Dict[str, Any]) -> QueryComplexity:
        """Assess query complexity."""
        complexity_indicators = 0
        
        # Multiple entities suggest complexity
        if len(entities) > 2:
            complexity_indicators += 1
        
        # Long queries are more complex
        if len(query.split()) > 15:
            complexity_indicators += 1
        
        # Multiple conditions
        if query.count(' and ') > 1 or query.count(' or ') > 1:
            complexity_indicators += 1
        
        # Time-based queries
        if any(word in query.lower() for word in ['yesterday', 'today', 'last week', 'this month']):
            complexity_indicators += 1
        
        if complexity_indicators >= 3:
            return QueryComplexity.COMPLEX
        elif complexity_indicators >= 1:
            return QueryComplexity.MODERATE
        else:
            return QueryComplexity.SIMPLE
    
    async def _determine_routing(
        self, 
        classification: QueryClassification, 
        query: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> RoutingDecision:
        """Determine final routing decision."""
        
        # High confidence SQL queries go to SQL
        if (classification.sql_optimizable and 
            classification.confidence > 0.6 and 
            classification.query_type != QueryType.HYBRID_RAG):
            return RoutingDecision(
                route_to="sql",
                query_type=classification.query_type,
                confidence=classification.confidence,
                reasoning=classification.reasoning,
                optimization_applied=[],
                fallback_available=True
            )
        
        # Medium confidence SQL queries with context preference
        elif (classification.sql_optimizable and 
              classification.confidence > 0.5 and 
              context and context.get('prefer_sql', False)):
            return RoutingDecision(
                route_to="sql",
                query_type=classification.query_type,
                confidence=classification.confidence,
                reasoning=f"{classification.reasoning} (context preference)",
                optimization_applied=[],
                fallback_available=True
            )
        
        # Everything else goes to hybrid RAG
        else:
            return RoutingDecision(
                route_to="hybrid_rag",
                query_type=QueryType.HYBRID_RAG,
                confidence=classification.confidence,
                reasoning=classification.reasoning,
                optimization_applied=[],
                fallback_available=False
            )
    
    async def _apply_sql_optimizations(
        self, 
        query: str, 
        classification: QueryClassification
    ) -> List[str]:
        """Apply SQL query optimizations."""
        optimizations = []
        
        # Add result limiting for large datasets
        if classification.complexity in [QueryComplexity.MODERATE, QueryComplexity.COMPLEX]:
            optimizations.append("result_limiting")
        
        # Add caching for frequent queries
        if classification.query_type in [QueryType.SQL_ATP, QueryType.SQL_QUANTITY]:
            optimizations.append("query_caching")
        
        # Add parallel execution for complex queries
        if classification.complexity == QueryComplexity.COMPLEX:
            optimizations.append("parallel_execution")
        
        # Add index hints for specific query types
        if classification.query_type == QueryType.SQL_EQUIPMENT_STATUS:
            optimizations.append("equipment_status_index")
        
        return optimizations
    
    async def execute_sql_query(
        self, 
        query: str, 
        query_type: QueryType,
        context: Optional[Dict[str, Any]] = None
    ) -> SQLQueryResult:
        """Execute SQL query with optimization and validation."""
        start_time = datetime.now()
        
        try:
            # Apply query-specific optimizations
            optimized_query = await self._optimize_sql_query(query, query_type, context)
            
            # Execute the query
            if query_type == QueryType.SQL_ATP:
                data = await self._execute_atp_query(optimized_query, context)
            elif query_type == QueryType.SQL_QUANTITY:
                data = await self._execute_quantity_query(optimized_query, context)
            elif query_type == QueryType.SQL_EQUIPMENT_STATUS:
                data = await self._execute_equipment_status_query(optimized_query, context)
            elif query_type == QueryType.SQL_MAINTENANCE:
                data = await self._execute_maintenance_query(optimized_query, context)
            elif query_type == QueryType.SQL_LOCATION:
                data = await self._execute_location_query(optimized_query, context)
            else:
                data = await self.sql_retriever.fetch_all(optimized_query)
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            # Validate results
            quality_score, errors, warnings = await self._validate_sql_results(data, query_type)
            
            return SQLQueryResult(
                success=True,
                data=data,
                execution_time=execution_time,
                row_count=len(data),
                query_type=query_type,
                quality_score=quality_score,
                errors=errors,
                warnings=warnings
            )
            
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"SQL query execution failed: {e}")
            
            return SQLQueryResult(
                success=False,
                data=[],
                execution_time=execution_time,
                row_count=0,
                query_type=query_type,
                quality_score=0.0,
                errors=[str(e)],
                warnings=[]
            )
    
    async def _optimize_sql_query(
        self, 
        query: str, 
        query_type: QueryType,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Apply SQL query optimizations."""
        optimized = query
        
        # Add LIMIT clause for large result sets
        if not re.search(r'\bLIMIT\b', optimized, re.IGNORECASE):
            optimized += " LIMIT 1000"
        
        # Add ORDER BY for consistent results
        if not re.search(r'\bORDER BY\b', optimized, re.IGNORECASE):
            if query_type == QueryType.SQL_ATP:
                optimized += " ORDER BY sku, location"
            elif query_type == QueryType.SQL_QUANTITY:
                optimized += " ORDER BY quantity DESC"
            elif query_type == QueryType.SQL_EQUIPMENT_STATUS:
                optimized += " ORDER BY equipment_id, status"
        
        return optimized
    
    async def _execute_atp_query(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute ATP-specific query."""
        # Extract SKU from context or query
        sku = None
        if context and 'sku' in context:
            sku = context['sku']
        elif 'SKU' in query:
            sku_match = re.search(r'SKU\d+', query)
            if sku_match:
                sku = sku_match.group()
        
        if sku:
            atp_query = """
                SELECT 
                    sku,
                    location,
                    available_quantity,
                    reserved_quantity,
                    (available_quantity - reserved_quantity) as atp_quantity,
                    last_updated
                FROM inventory_items 
                WHERE sku = %s
                ORDER BY location
            """
            return await self.sql_retriever.fetch_all(atp_query, (sku,))
        else:
            # General ATP query
            atp_query = """
                SELECT 
                    sku,
                    location,
                    available_quantity,
                    reserved_quantity,
                    (available_quantity - reserved_quantity) as atp_quantity,
                    last_updated
                FROM inventory_items 
                WHERE available_quantity > 0
                ORDER BY atp_quantity DESC
                LIMIT 50
            """
            return await self.sql_retriever.fetch_all(atp_query)
    
    async def _execute_quantity_query(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute quantity-specific query."""
        quantity_query = """
            SELECT 
                sku,
                name,
                location,
                available_quantity,
                reserved_quantity,
                total_quantity,
                last_updated
            FROM inventory_items 
            WHERE available_quantity > 0
            ORDER BY available_quantity DESC
            LIMIT 100
        """
        return await self.sql_retriever.fetch_all(quantity_query)
    
    async def _execute_equipment_status_query(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute equipment status query."""
        status_query = """
            SELECT 
                equipment_id,
                equipment_type,
                status,
                location,
                last_maintenance,
                next_maintenance,
                operational_hours,
                last_updated
            FROM equipment 
            WHERE status IN ('operational', 'maintenance', 'out_of_service')
            ORDER BY status, equipment_type
        """
        return await self.sql_retriever.fetch_all(status_query)
    
    async def _execute_maintenance_query(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute maintenance query."""
        maintenance_query = """
            SELECT 
                equipment_id,
                equipment_type,
                maintenance_type,
                scheduled_date,
                status,
                priority,
                assigned_technician,
                estimated_duration
            FROM maintenance_schedule 
            WHERE scheduled_date >= CURRENT_DATE
            ORDER BY scheduled_date, priority
        """
        return await self.sql_retriever.fetch_all(maintenance_query)
    
    async def _execute_location_query(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Execute location query."""
        location_query = """
            SELECT 
                sku,
                name,
                location,
                zone,
                aisle,
                bay,
                level,
                last_updated
            FROM inventory_items 
            WHERE location IS NOT NULL
            ORDER BY zone, aisle, bay
        """
        return await self.sql_retriever.fetch_all(location_query)
    
    async def _validate_sql_results(
        self, 
        data: List[Dict[str, Any]], 
        query_type: QueryType
    ) -> Tuple[float, List[str], List[str]]:
        """Validate SQL query results for quality."""
        quality_score = 1.0
        errors = []
        warnings = []
        
        if not data:
            warnings.append("No data returned from query")
            quality_score *= 0.8
        
        # Check for required fields based on query type
        if data:
            first_row = data[0]
            
            if query_type == QueryType.SQL_ATP:
                required_fields = ['sku', 'available_quantity', 'atp_quantity']
                missing_fields = [field for field in required_fields if field not in first_row]
                if missing_fields:
                    errors.append(f"Missing required ATP fields: {missing_fields}")
                    quality_score *= 0.5
            
            elif query_type == QueryType.SQL_EQUIPMENT_STATUS:
                required_fields = ['equipment_id', 'status']
                missing_fields = [field for field in required_fields if field not in first_row]
                if missing_fields:
                    errors.append(f"Missing required equipment fields: {missing_fields}")
                    quality_score *= 0.5
        
        # Check data consistency
        if len(data) > 1:
            # Check for duplicate primary keys
            if query_type == QueryType.SQL_ATP:
                skus = [row.get('sku') for row in data]
                if len(skus) != len(set(skus)):
                    warnings.append("Duplicate SKUs found in results")
                    quality_score *= 0.9
        
        return max(0.0, min(1.0, quality_score)), errors, warnings
    
    async def execute_with_fallback(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[Any, str, Dict[str, Any]]:
        """
        Execute query with automatic fallback from SQL to hybrid RAG.
        
        Returns:
            Tuple of (results, route_used, metadata)
        """
        # Get routing decision
        routing_decision = await self.route_query(query, context)
        
        try:
            if routing_decision.route_to == "sql":
                # Execute SQL query
                sql_result = await self.execute_sql_query(
                    query, 
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
                else:
                    # SQL failed or low quality, fallback to hybrid RAG
                    logger.warning(f"SQL query failed or low quality, falling back to hybrid RAG: {sql_result.errors}")
                    routing_decision.route_to = "hybrid_rag"
            
            if routing_decision.route_to == "hybrid_rag":
                # Execute hybrid RAG query
                results, metadata = await self.hybrid_retriever.retrieve(query, context)
                return (
                    results,
                    "hybrid_rag",
                    metadata
                )
            
            else:
                # Fallback to hybrid RAG
                results, metadata = await self.hybrid_retriever.retrieve(query, context)
                return (
                    results,
                    "fallback",
                    metadata
                )
                
        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            # Final fallback
            try:
                results, metadata = await self.hybrid_retriever.retrieve(query, context)
                return (
                    results,
                    "fallback",
                    metadata
                )
            except Exception as fallback_error:
                logger.error(f"Fallback also failed: {fallback_error}")
                return (
                    [],
                    "error",
                    {"error": str(e), "fallback_error": str(fallback_error)}
                )
