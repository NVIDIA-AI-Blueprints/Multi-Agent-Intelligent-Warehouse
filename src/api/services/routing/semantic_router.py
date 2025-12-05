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
            
            # Define intent categories with semantic descriptions
            self.intent_categories = {
                "equipment": IntentCategory(
                    name="equipment",
                    description="Queries about warehouse equipment, assets, machinery, forklifts, scanners, conveyors, availability, status, maintenance, telemetry, and equipment operations",
                    keywords=["equipment", "forklift", "conveyor", "scanner", "asset", "machine", "availability", "status", "maintenance", "telemetry"]
                ),
                "operations": IntentCategory(
                    name="operations",
                    description="Queries about warehouse operations, tasks, workforce, shifts, pick waves, orders, scheduling, assignments, productivity, and operational workflows",
                    keywords=["task", "wave", "order", "workforce", "shift", "schedule", "assignment", "pick", "pack", "operations"]
                ),
                "safety": IntentCategory(
                    name="safety",
                    description="Queries about safety incidents, compliance, hazards, accidents, safety procedures, PPE, lockout/tagout, emergency protocols, and safety training",
                    keywords=["safety", "incident", "hazard", "accident", "compliance", "ppe", "emergency", "protocol", "loto", "lockout"]
                ),
                "forecasting": IntentCategory(
                    name="forecasting",
                    description="Queries about demand forecasting, sales predictions, inventory forecasts, reorder recommendations, model performance, and business intelligence",
                    keywords=["forecast", "prediction", "demand", "sales", "inventory", "reorder", "model", "trend", "projection"]
                ),
                "document": IntentCategory(
                    name="document",
                    description="Queries about document processing, uploads, scanning, extraction, invoices, receipts, BOL, purchase orders, OCR, and document management",
                    keywords=["document", "upload", "scan", "extract", "invoice", "receipt", "bol", "po", "ocr", "file"]
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
        """Pre-compute embeddings for all intent categories."""
        if not self.embedding_service:
            return
            
        try:
            for category_name, category in self.intent_categories.items():
                # Create a rich description combining name, description, and keywords
                semantic_text = f"{category.description}. Keywords: {', '.join(category.keywords[:10])}"
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
            
            # Combine keyword and semantic results
            # If keyword confidence is high (>0.7), trust it more
            # If semantic score is much higher, use semantic
            if keyword_confidence > 0.7:
                # High keyword confidence - use keyword but boost if semantic agrees
                if semantic_intent == keyword_intent:
                    final_confidence = min(0.95, keyword_confidence + 0.1)
                    return (keyword_intent, final_confidence)
                else:
                    # Semantic disagrees - use weighted average
                    final_confidence = (keyword_confidence * 0.6) + (semantic_score * 0.4)
                    if semantic_score > keyword_confidence + 0.2:
                        return (semantic_intent, final_confidence)
                    else:
                        return (keyword_intent, final_confidence)
            else:
                # Low keyword confidence - trust semantic more
                if semantic_score > 0.6:
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

