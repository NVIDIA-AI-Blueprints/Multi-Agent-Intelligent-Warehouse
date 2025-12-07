"""
Semantic Routing Service

Provides embedding-based semantic intent classification to complement keyword-based routing.
Uses cosine similarity between query embeddings and intent category embeddings.
"""

import logging
from typing import Dict, List, Optional, Tuple
import numpy as np
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class IntentCategory:
    """Represents an intent category with its semantic description."""
    name: str
    description: str
    keywords: List[str]
    embedding: Optional[List[float]] = None


class SemanticRouter:
    """Semantic routing service using embeddings for intent classification."""

    def __init__(self):
        self.embedding_service = None
        self.intent_categories: Dict[str, IntentCategory] = {}
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the semantic router with embedding service and intent categories."""
        try:
            from src.retrieval.vector.embedding_service import get_embedding_service
            
            self.embedding_service = await get_embedding_service()
            
            # Define intent categories with enhanced semantic descriptions and diverse examples
            # Enhanced descriptions include domain-specific terminology and common query patterns
            self.intent_categories = {
                "equipment": IntentCategory(
                    name="equipment",
                    description=(
                        "Queries about warehouse equipment, assets, machinery, material handling vehicles, "
                        "forklifts, pallet jacks, scanners, barcode readers, conveyors, AGVs, AMRs, "
                        "equipment availability, status checks, maintenance schedules, telemetry data, "
                        "equipment assignments, utilization rates, battery levels, and equipment operations. "
                        "Examples: 'What equipment is available?', 'Show me forklift status', "
                        "'Check equipment condition', 'What machinery needs maintenance?'"
                    ),
                    keywords=[
                        "equipment", "forklift", "conveyor", "scanner", "asset", "machine", "machinery",
                        "availability", "status", "maintenance", "telemetry", "vehicle", "truck", "pallet jack",
                        "agv", "amr", "battery", "utilization", "assignment", "condition", "state"
                    ]
                ),
                "operations": IntentCategory(
                    name="operations",
                    description=(
                        "Queries about warehouse operations, daily tasks, work assignments, job lists, "
                        "workforce management, employee shifts, pick waves, packing operations, putaway tasks, "
                        "order fulfillment, scheduling, task assignments, productivity metrics, "
                        "operational workflows, work queues, pending work, today's jobs, and operational planning. "
                        "Examples: 'What tasks need to be done today?', 'Show me today's job list', "
                        "'What work assignments are pending?', 'What operations are scheduled?'"
                    ),
                    keywords=[
                        "task", "tasks", "work", "job", "jobs", "assignment", "assignments", "wave", "order",
                        "workforce", "worker", "employee", "shift", "schedule", "pick", "pack", "putaway",
                        "fulfillment", "operations", "pending", "queue", "today", "scheduled", "planning",
                        "productivity", "workflow", "list", "show", "need", "done"
                    ]
                ),
                "inventory": IntentCategory(
                    name="inventory",
                    description=(
                        "Queries about inventory levels, stock quantities, product availability, "
                        "SKU information, item counts, stock status, inventory management, "
                        "warehouse stock, product quantities, available items, stock levels, "
                        "inventory queries, and stock inquiries. "
                        "Examples: 'How much stock do we have?', 'What's our inventory level?', "
                        "'Check product quantities', 'Show me available items', 'What's in stock?'"
                    ),
                    keywords=[
                        "inventory", "stock", "quantity", "quantities", "sku", "item", "items", "product",
                        "products", "available", "availability", "level", "levels", "count", "counts",
                        "warehouse", "storage", "have", "show", "check", "what", "how much"
                    ]
                ),
                "safety": IntentCategory(
                    name="safety",
                    description=(
                        "Queries about safety incidents, workplace accidents, safety violations, "
                        "hazards, compliance issues, safety procedures, PPE requirements, "
                        "lockout/tagout procedures, emergency protocols, safety training, "
                        "incident reporting, safety documentation, and safety compliance. "
                        "Examples: 'Report a safety incident', 'Log a workplace accident', "
                        "'Document a safety violation', 'Record a hazard occurrence'"
                    ),
                    keywords=[
                        "safety", "incident", "incidents", "hazard", "hazards", "accident", "accidents",
                        "compliance", "ppe", "emergency", "protocol", "protocols", "loto", "lockout",
                        "tagout", "violation", "violations", "report", "log", "document", "record",
                        "training", "procedure", "procedures"
                    ]
                ),
                "forecasting": IntentCategory(
                    name="forecasting",
                    description=(
                        "Queries about demand forecasting, sales predictions, inventory forecasts, "
                        "reorder recommendations, model performance, business intelligence, "
                        "trend analysis, projections, and predictive analytics. "
                        "Examples: 'What's the demand forecast?', 'Show sales predictions', "
                        "'Get reorder recommendations', 'Check model performance'"
                    ),
                    keywords=[
                        "forecast", "forecasting", "prediction", "predictions", "demand", "sales",
                        "inventory", "reorder", "recommendation", "recommendations", "model", "models",
                        "trend", "trends", "projection", "projections", "analytics", "intelligence"
                    ]
                ),
                "document": IntentCategory(
                    name="document",
                    description=(
                        "Queries about document processing, file uploads, document scanning, "
                        "data extraction, invoices, receipts, bills of lading (BOL), "
                        "purchase orders (PO), OCR processing, and document management. "
                        "Examples: 'Upload a document', 'Process an invoice', "
                        "'Extract data from receipt', 'Scan a BOL'"
                    ),
                    keywords=[
                        "document", "documents", "upload", "scan", "scanning", "extract", "extraction",
                        "invoice", "invoices", "receipt", "receipts", "bol", "bill of lading",
                        "po", "purchase order", "ocr", "file", "files", "process", "processing"
                    ]
                ),
            }
            
            # Pre-compute embeddings for intent categories
            await self._precompute_category_embeddings()
            
            self._initialized = True
            logger.info(f"Semantic router initialized with {len(self.intent_categories)} intent categories")
            
        except Exception as e:
            logger.error(f"Failed to initialize semantic router: {e}")
            # Continue without semantic routing - will fall back to keyword-based
            self._initialized = False

    async def _precompute_category_embeddings(self) -> None:
        """Pre-compute embeddings for all intent categories with enhanced semantic text."""
        if not self.embedding_service:
            return
            
        try:
            for category_name, category in self.intent_categories.items():
                # Create enhanced semantic text with description, keywords, and examples
                # This provides richer context for better embedding quality
                keywords_text = ', '.join(category.keywords[:15])  # Use more keywords
                semantic_text = (
                    f"Category: {category.name}. "
                    f"{category.description} "
                    f"Related terms: {keywords_text}"
                )
                category.embedding = await self.embedding_service.generate_embedding(
                    semantic_text,
                    input_type="passage"
                )
                logger.debug(f"Pre-computed embedding for intent category: {category_name}")
        except Exception as e:
            logger.warning(f"Failed to pre-compute category embeddings: {e}")

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        try:
            v1 = np.array(vec1)
            v2 = np.array(vec2)
            
            dot_product = np.dot(v1, v2)
            norm1 = np.linalg.norm(v1)
            norm2 = np.linalg.norm(v2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            return float(dot_product / (norm1 * norm2))
        except Exception as e:
            logger.error(f"Error calculating cosine similarity: {e}")
            return 0.0

    async def classify_intent_semantic(
        self,
        message: str,
        keyword_intent: str,
        keyword_confidence: float = 0.5
    ) -> Tuple[str, float]:
        """
        Classify intent using semantic similarity.
        
        Args:
            message: User message
            keyword_intent: Intent from keyword-based classification
            keyword_confidence: Confidence of keyword-based classification
            
        Returns:
            Tuple of (intent, confidence)
        """
        if not self._initialized or not self.embedding_service:
            # Fall back to keyword-based if semantic routing not available
            return (keyword_intent, keyword_confidence)
        
        try:
            # Generate embedding for the query
            query_embedding = await self.embedding_service.generate_embedding(
                message,
                input_type="query"
            )
            
            # Calculate similarity to each intent category
            similarities: Dict[str, float] = {}
            for category_name, category in self.intent_categories.items():
                if category.embedding:
                    similarity = self._cosine_similarity(query_embedding, category.embedding)
                    similarities[category_name] = similarity
            
            if not similarities:
                # No similarities calculated, fall back to keyword
                return (keyword_intent, keyword_confidence)
            
            # Find the category with highest similarity
            best_category = max(similarities.items(), key=lambda x: x[1])
            semantic_intent, semantic_score = best_category
            
            # Enhanced combination logic with improved thresholds
            # Adjusted thresholds for better classification accuracy
            
            # If semantic score is very high (>0.75), trust it strongly
            if semantic_score > 0.75:
                # Very high semantic confidence - use semantic intent
                if semantic_intent == keyword_intent:
                    # Both agree - boost confidence
                    final_confidence = min(0.95, max(keyword_confidence, semantic_score) + 0.05)
                    return (semantic_intent, final_confidence)
                else:
                    # Semantic disagrees but is very confident - trust semantic
                    return (semantic_intent, semantic_score)
            
            # If keyword confidence is high (>0.7), trust it more
            if keyword_confidence > 0.7:
                # High keyword confidence - use keyword but boost if semantic agrees
                if semantic_intent == keyword_intent:
                    final_confidence = min(0.95, keyword_confidence + 0.1)
                    return (keyword_intent, final_confidence)
                else:
                    # Semantic disagrees - use weighted average with adjusted weights
                    # Give more weight to semantic if it's reasonably confident (>0.65)
                    if semantic_score > 0.65:
                        final_confidence = (keyword_confidence * 0.5) + (semantic_score * 0.5)
                        # If semantic is significantly better, use it
                        if semantic_score > keyword_confidence + 0.15:
                            return (semantic_intent, final_confidence)
                        else:
                            return (keyword_intent, final_confidence)
                    else:
                        # Semantic not confident enough - trust keyword
                        return (keyword_intent, keyword_confidence)
            else:
                # Low keyword confidence - trust semantic more
                # Lowered threshold from 0.6 to 0.55 for better coverage
                if semantic_score > 0.55:
                    return (semantic_intent, semantic_score)
                else:
                    # Both low confidence - use keyword as fallback
                    return (keyword_intent, keyword_confidence)
                    
        except Exception as e:
            logger.error(f"Error in semantic intent classification: {e}")
            # Fall back to keyword-based
            return (keyword_intent, keyword_confidence)


# Global semantic router instance
_semantic_router: Optional[SemanticRouter] = None


async def get_semantic_router() -> SemanticRouter:
    """Get or create the global semantic router instance."""
    global _semantic_router
    if _semantic_router is None:
        _semantic_router = SemanticRouter()
        await _semantic_router.initialize()
    return _semantic_router

