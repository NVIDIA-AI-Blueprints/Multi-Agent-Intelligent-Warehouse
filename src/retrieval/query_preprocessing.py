"""
Query Preprocessing Service for Warehouse Operational Assistant

This module provides query preprocessing, normalization, and enhancement
to improve retrieval accuracy and routing decisions.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import asyncio

logger = logging.getLogger(__name__)


class QueryIntent(Enum):
    """Query intent classification."""
    LOOKUP = "lookup"  # Find specific information
    COMPARE = "compare"  # Compare multiple items
    ANALYZE = "analyze"  # Analyze trends or patterns
    INSTRUCT = "instruct"  # How-to or procedural
    TROUBLESHOOT = "troubleshoot"  # Problem solving
    SCHEDULE = "schedule"  # Time-based queries
    UNKNOWN = "unknown"


@dataclass
class PreprocessedQuery:
    """Result of query preprocessing."""
    original_query: str
    normalized_query: str
    intent: QueryIntent
    entities: Dict[str, Any]
    keywords: List[str]
    context_hints: List[str]
    complexity_score: float
    confidence: float
    suggestions: List[str]


class QueryPreprocessor:
    """
    Advanced query preprocessing service.
    
    This class normalizes, enhances, and analyzes queries to improve
    routing decisions and retrieval accuracy.
    """
    
    def __init__(self):
        # Common warehouse terminology mappings
        self.terminology_map = {
            # Equipment types
            'forklift': ['forklift', 'lift truck', 'fork truck', 'pallet truck'],
            'conveyor': ['conveyor', 'conveyor belt', 'belt conveyor', 'conveyor system'],
            'scanner': ['scanner', 'barcode scanner', 'rfid scanner', 'handheld scanner'],
            'amr': ['amr', 'autonomous mobile robot', 'mobile robot', 'agv'],
            'agv': ['agv', 'automated guided vehicle', 'guided vehicle'],
            'robot': ['robot', 'robotic', 'automation', 'automated system'],
            
            # Inventory terms
            'sku': ['sku', 'item', 'product', 'part', 'material'],
            'quantity': ['quantity', 'qty', 'amount', 'count', 'number', 'total'],
            'location': ['location', 'position', 'zone', 'area', 'bay', 'aisle'],
            'warehouse': ['warehouse', 'facility', 'building', 'distribution center'],
            
            # Status terms
            'operational': ['operational', 'working', 'running', 'active', 'functional'],
            'maintenance': ['maintenance', 'repair', 'service', 'checkup', 'inspection'],
            'available': ['available', 'ready', 'free', 'unused', 'idle'],
            'broken': ['broken', 'down', 'out of service', 'malfunctioning', 'faulty'],
            
            # Time terms
            'today': ['today', 'current', 'now', 'present'],
            'yesterday': ['yesterday', 'previous day'],
            'this week': ['this week', 'current week'],
            'last week': ['last week', 'previous week'],
            'this month': ['this month', 'current month'],
            'last month': ['last month', 'previous month']
        }
        
        # Intent patterns
        self.intent_patterns = {
            QueryIntent.LOOKUP: [
                r'\b(?:what|which|where|when|how many|how much)\b',
                r'\b(?:find|locate|search|get|retrieve)\b',
                r'\b(?:show|display|list)\b'
            ],
            QueryIntent.COMPARE: [
                r'\b(?:compare|vs|versus|difference|better|best)\b',
                r'\b(?:which.*better|which.*best)\b',
                r'\b(?:pros.*cons|advantages.*disadvantages)\b'
            ],
            QueryIntent.ANALYZE: [
                r'\b(?:analyze|analysis|trend|pattern|statistics)\b',
                r'\b(?:why|reason|cause|factor)\b',
                r'\b(?:performance|efficiency|productivity)\b'
            ],
            QueryIntent.INSTRUCT: [
                r'\b(?:how to|how do|procedure|process|steps)\b',
                r'\b(?:guide|tutorial|instructions|manual)\b',
                r'\b(?:what.*steps|what.*process)\b'
            ],
            QueryIntent.TROUBLESHOOT: [
                r'\b(?:problem|issue|error|fault|trouble)\b',
                r'\b(?:fix|repair|resolve|solve)\b',
                r'\b(?:not working|broken|down|malfunctioning)\b'
            ],
            QueryIntent.SCHEDULE: [
                r'\b(?:schedule|when.*due|next.*maintenance)\b',
                r'\b(?:calendar|timeline|deadline)\b',
                r'\b(?:planning|plan|arrange)\b'
            ]
        }
        
        # Context hint patterns
        self.context_patterns = {
            'urgent': [r'\b(?:urgent|asap|immediately|critical|emergency)\b'],
            'historical': [r'\b(?:yesterday|last week|last month|previous|past)\b'],
            'future': [r'\b(?:tomorrow|next week|next month|upcoming|planned)\b'],
            'maintenance': [r'\b(?:maintenance|repair|service|checkup|inspection)\b'],
            'safety': [r'\b(?:safety|incident|accident|hazard|risk)\b'],
            'performance': [r'\b(?:performance|efficiency|productivity|optimization)\b']
        }
    
    async def preprocess_query(
        self, 
        query: str, 
        context: Optional[Dict[str, Any]] = None
    ) -> PreprocessedQuery:
        """
        Preprocess a query for optimal routing and retrieval.
        
        Args:
            query: Original user query
            context: Additional context information
            
        Returns:
            PreprocessedQuery with enhanced information
        """
        try:
            # Step 1: Normalize the query
            normalized_query = self._normalize_query(query)
            
            # Step 2: Extract entities
            entities = await self._extract_entities(normalized_query)
            
            # Step 3: Extract keywords
            keywords = await self._extract_keywords(normalized_query)
            
            # Step 4: Classify intent
            intent = await self._classify_intent(normalized_query)
            
            # Step 5: Extract context hints
            context_hints = await self._extract_context_hints(normalized_query)
            
            # Step 6: Calculate complexity
            complexity_score = await self._calculate_complexity(normalized_query, entities)
            
            # Step 7: Generate suggestions
            suggestions = await self._generate_suggestions(normalized_query, intent, entities)
            
            # Step 8: Calculate confidence
            confidence = await self._calculate_confidence(normalized_query, intent, entities)
            
            return PreprocessedQuery(
                original_query=query,
                normalized_query=normalized_query,
                intent=intent,
                entities=entities,
                keywords=keywords,
                context_hints=context_hints,
                complexity_score=complexity_score,
                confidence=confidence,
                suggestions=suggestions
            )
            
        except Exception as e:
            logger.error(f"Error in query preprocessing: {e}")
            # Return minimal preprocessing on error
            return PreprocessedQuery(
                original_query=query,
                normalized_query=query.lower().strip(),
                intent=QueryIntent.UNKNOWN,
                entities={},
                keywords=[],
                context_hints=[],
                complexity_score=0.5,
                confidence=0.0,
                suggestions=[]
            )
    
    def _normalize_query(self, query: str) -> str:
        """Normalize query for consistent processing."""
        # Convert to lowercase
        normalized = query.lower().strip()
        
        # Remove extra whitespace
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Normalize common abbreviations
        abbreviations = {
            'qty': 'quantity',
            'qty.': 'quantity',
            'amt': 'amount',
            'amt.': 'amount',
            'loc': 'location',
            'loc.': 'location',
            'eq': 'equipment',
            'eq.': 'equipment',
            'maint': 'maintenance',
            'maint.': 'maintenance',
            'ops': 'operations',
            'ops.': 'operations'
        }
        
        for abbrev, full in abbreviations.items():
            normalized = re.sub(r'\b' + re.escape(abbrev) + r'\b', full, normalized)
        
        # Normalize equipment terminology
        for standard_term, variants in self.terminology_map.items():
            for variant in variants:
                if variant != standard_term:
                    normalized = re.sub(r'\b' + re.escape(variant) + r'\b', standard_term, normalized)
        
        # Remove common filler words
        filler_words = ['please', 'can you', 'could you', 'i need', 'i want', 'i would like']
        for filler in filler_words:
            normalized = re.sub(r'\b' + re.escape(filler) + r'\b', '', normalized)
        
        # Clean up extra spaces
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
    
    async def _extract_entities(self, query: str) -> Dict[str, Any]:
        """Extract entities from normalized query."""
        entities = {}
        
        # Extract SKUs
        sku_pattern = r'sku\d+'
        skus = re.findall(sku_pattern, query)
        if skus:
            entities['skus'] = [sku.upper() for sku in skus]
        
        # Extract equipment types
        equipment_types = []
        for equipment_type in ['forklift', 'conveyor', 'scanner', 'amr', 'agv', 'robot']:
            if equipment_type in query:
                equipment_types.append(equipment_type)
        if equipment_types:
            entities['equipment_types'] = equipment_types
        
        # Extract locations
        location_patterns = [
            r'zone\s+[a-zA-Z0-9]+',
            r'area\s+[a-zA-Z0-9]+',
            r'aisle\s+[a-zA-Z0-9]+',
            r'bay\s+[a-zA-Z0-9]+'
        ]
        locations = []
        for pattern in location_patterns:
            matches = re.findall(pattern, query)
            locations.extend(matches)
        if locations:
            entities['locations'] = locations
        
        # Extract quantities
        quantity_pattern = r'\b(\d+)\s*(?:units?|pieces?|items?|qty|quantity)\b'
        quantities = re.findall(quantity_pattern, query)
        if quantities:
            entities['quantities'] = [int(q) for q in quantities]
        
        # Extract time references
        time_patterns = [
            r'\b(?:today|yesterday|tomorrow)\b',
            r'\b(?:this|last|next)\s+(?:week|month|year)\b',
            r'\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b'
        ]
        time_refs = []
        for pattern in time_patterns:
            matches = re.findall(pattern, query)
            time_refs.extend(matches)
        if time_refs:
            entities['time_references'] = time_refs
        
        return entities
    
    async def _extract_keywords(self, query: str) -> List[str]:
        """Extract important keywords from query."""
        # Remove common stop words
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
            'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'can', 'must', 'shall'
        }
        
        # Extract words
        words = re.findall(r'\b\w+\b', query)
        keywords = [word for word in words if word not in stop_words and len(word) > 2]
        
        # Remove duplicates while preserving order
        seen = set()
        unique_keywords = []
        for keyword in keywords:
            if keyword not in seen:
                seen.add(keyword)
                unique_keywords.append(keyword)
        
        return unique_keywords[:15]  # Limit to top 15 keywords
    
    async def _classify_intent(self, query: str) -> QueryIntent:
        """Classify query intent."""
        best_intent = QueryIntent.UNKNOWN
        best_confidence = 0.0
        
        for intent, patterns in self.intent_patterns.items():
            confidence = 0.0
            for pattern in patterns:
                matches = re.findall(pattern, query, re.IGNORECASE)
                if matches:
                    confidence += len(matches) / len(query.split())
            
            if confidence > best_confidence:
                best_confidence = confidence
                best_intent = intent
        
        return best_intent
    
    async def _extract_context_hints(self, query: str) -> List[str]:
        """Extract context hints from query."""
        hints = []
        
        for hint_type, patterns in self.context_patterns.items():
            for pattern in patterns:
                if re.search(pattern, query, re.IGNORECASE):
                    hints.append(hint_type)
                    break
        
        return hints
    
    async def _calculate_complexity(self, query: str, entities: Dict[str, Any]) -> float:
        """Calculate query complexity score (0.0 to 1.0)."""
        complexity = 0.0
        
        # Base complexity from query length
        word_count = len(query.split())
        complexity += min(0.3, word_count / 50)  # Cap at 0.3
        
        # Entity complexity
        entity_count = sum(len(v) if isinstance(v, list) else 1 for v in entities.values())
        complexity += min(0.3, entity_count / 10)  # Cap at 0.3
        
        # Question complexity
        question_words = ['what', 'how', 'why', 'when', 'where', 'which', 'who']
        question_count = sum(1 for word in question_words if word in query)
        complexity += min(0.2, question_count / 5)  # Cap at 0.2
        
        # Conditional complexity
        conditional_words = ['if', 'when', 'unless', 'provided', 'assuming']
        conditional_count = sum(1 for word in conditional_words if word in query)
        complexity += min(0.2, conditional_count / 3)  # Cap at 0.2
        
        return min(1.0, complexity)
    
    async def _generate_suggestions(
        self, 
        query: str, 
        intent: QueryIntent, 
        entities: Dict[str, Any]
    ) -> List[str]:
        """Generate query improvement suggestions."""
        suggestions = []
        
        # Intent-based suggestions
        if intent == QueryIntent.LOOKUP:
            if 'sku' in query and 'location' not in query:
                suggestions.append("Consider adding location information for more specific results")
            if 'equipment' in query and 'status' not in query:
                suggestions.append("Add status information to get more relevant equipment data")
        
        elif intent == QueryIntent.COMPARE:
            if len(entities.get('skus', [])) < 2:
                suggestions.append("Specify multiple SKUs or items to compare")
            if 'criteria' not in query.lower():
                suggestions.append("Specify comparison criteria (e.g., performance, cost, availability)")
        
        elif intent == QueryIntent.INSTRUCT:
            if 'steps' not in query.lower() and 'process' not in query.lower():
                suggestions.append("Ask for step-by-step instructions for better guidance")
            if 'safety' not in query.lower():
                suggestions.append("Consider asking about safety procedures")
        
        # Entity-based suggestions
        if entities.get('skus') and not entities.get('quantities'):
            suggestions.append("Add quantity information for more specific inventory queries")
        
        if 'equipment' in query and not entities.get('equipment_types'):
            suggestions.append("Specify equipment type (forklift, conveyor, scanner, etc.)")
        
        # General suggestions
        if len(query.split()) < 3:
            suggestions.append("Provide more details for better results")
        
        if 'urgent' in query.lower() or 'asap' in query.lower():
            suggestions.append("Consider adding priority level or deadline information")
        
        return suggestions[:3]  # Limit to 3 suggestions
    
    async def _calculate_confidence(
        self, 
        query: str, 
        intent: QueryIntent, 
        entities: Dict[str, Any]
    ) -> float:
        """Calculate preprocessing confidence score."""
        confidence = 0.5  # Base confidence
        
        # Intent confidence
        if intent != QueryIntent.UNKNOWN:
            confidence += 0.2
        
        # Entity confidence
        if entities:
            confidence += 0.2
        
        # Query clarity
        if len(query.split()) >= 3:
            confidence += 0.1
        
        # Specificity
        specific_terms = ['sku', 'equipment', 'location', 'quantity', 'status']
        specific_count = sum(1 for term in specific_terms if term in query)
        confidence += min(0.2, specific_count * 0.05)
        
        return min(1.0, confidence)
    
    async def enhance_query_for_routing(
        self, 
        preprocessed_query: PreprocessedQuery,
        target_route: str
    ) -> str:
        """Enhance query for specific routing target."""
        query = preprocessed_query.normalized_query
        
        if target_route == "sql":
            # Enhance for SQL routing
            if preprocessed_query.intent == QueryIntent.LOOKUP:
                # Add specific field requests
                if 'sku' in query and 'quantity' not in query:
                    query += " quantity location"
                elif 'equipment' in query and 'status' not in query:
                    query += " status location"
        
        elif target_route == "hybrid_rag":
            # Enhance for hybrid RAG routing
            if preprocessed_query.intent == QueryIntent.INSTRUCT:
                # Add context for procedural queries
                query = f"warehouse procedure {query}"
            elif preprocessed_query.intent == QueryIntent.TROUBLESHOOT:
                # Add troubleshooting context
                query = f"troubleshooting guide {query}"
        
        return query
