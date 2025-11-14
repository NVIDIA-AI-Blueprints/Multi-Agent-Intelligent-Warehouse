"""
Evidence Scoring System for Enhanced Vector Search

This module implements comprehensive evidence scoring based on multiple factors:
- Vector similarity score
- Source authority/credibility
- Content freshness/recency
- Cross-reference validation
- Source diversity validation
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
import logging
import re
from collections import Counter

logger = logging.getLogger(__name__)

@dataclass
class EvidenceSource:
    """Represents a source of evidence with metadata."""
    source_id: str
    source_type: str  # "manual", "procedure", "policy", "database", "api"
    authority_level: float  # 0.0 to 1.0
    freshness_score: float  # 0.0 to 1.0
    content_quality: float  # 0.0 to 1.0
    last_updated: Optional[datetime] = None
    source_credibility: float = 0.8  # Default credibility

@dataclass
class EvidenceItem:
    """Represents a single piece of evidence."""
    content: str
    source: EvidenceSource
    similarity_score: float
    relevance_score: float
    cross_references: List[str] = None
    keywords: List[str] = None
    metadata: Dict[str, Any] = None

@dataclass
class EvidenceScore:
    """Comprehensive evidence scoring result."""
    overall_score: float
    similarity_component: float
    authority_component: float
    freshness_component: float
    cross_reference_component: float
    source_diversity_score: float
    confidence_level: str  # "high", "medium", "low"
    evidence_quality: str  # "excellent", "good", "fair", "poor"
    validation_status: str  # "validated", "partial", "insufficient"
    sources_count: int
    distinct_sources: int

class EvidenceScoringEngine:
    """Advanced evidence scoring engine with multiple validation factors."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or self._get_default_config()
        self.source_authority_map = self._build_source_authority_map()
        self.content_quality_indicators = self._build_content_quality_indicators()
        
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration for evidence scoring."""
        return {
            "confidence_threshold": 0.35,
            "min_sources": 2,
            "similarity_weight": 0.3,
            "authority_weight": 0.25,
            "freshness_weight": 0.2,
            "cross_reference_weight": 0.15,
            "diversity_weight": 0.1,
            "max_age_days": 365,  # Maximum age for content to be considered fresh
            "cross_reference_threshold": 0.7,  # Minimum similarity for cross-reference validation
            "source_credibility_threshold": 0.6
        }
    
    def _build_source_authority_map(self) -> Dict[str, float]:
        """Build authority mapping for different source types."""
        return {
            "official_manual": 1.0,
            "sop": 0.95,
            "policy": 0.9,
            "procedure": 0.85,
            "database": 0.8,
            "api": 0.75,
            "documentation": 0.7,
            "training_material": 0.65,
            "wiki": 0.6,
            "forum": 0.4,
            "user_generated": 0.3,
            "unknown": 0.5
        }
    
    def _build_content_quality_indicators(self) -> Dict[str, float]:
        """Build content quality indicators and their weights."""
        return {
            "has_structure": 0.2,  # Headers, bullet points, numbered lists
            "has_examples": 0.15,  # Code examples, use cases
            "has_references": 0.1,  # Citations, links to other sources
            "has_metadata": 0.1,   # Author, date, version info
            "completeness": 0.2,   # Length, detail level
            "clarity": 0.15,       # Readability, technical accuracy
            "uniqueness": 0.1      # Not duplicated content
        }
    
    def calculate_evidence_score(
        self, 
        evidence_items: List[EvidenceItem],
        query_context: Optional[Dict[str, Any]] = None
    ) -> EvidenceScore:
        """
        Calculate comprehensive evidence score based on multiple factors.
        
        Args:
            evidence_items: List of evidence items to score
            query_context: Additional context for scoring
            
        Returns:
            EvidenceScore with detailed scoring breakdown
        """
        if not evidence_items:
            return self._create_empty_evidence_score()
        
        # Calculate individual components
        similarity_component = self._calculate_similarity_component(evidence_items)
        authority_component = self._calculate_authority_component(evidence_items)
        freshness_component = self._calculate_freshness_component(evidence_items)
        cross_reference_component = self._calculate_cross_reference_component(evidence_items)
        diversity_score = self._calculate_source_diversity_score(evidence_items)
        
        # Weighted overall score
        overall_score = (
            similarity_component * self.config["similarity_weight"] +
            authority_component * self.config["authority_weight"] +
            freshness_component * self.config["freshness_weight"] +
            cross_reference_component * self.config["cross_reference_weight"] +
            diversity_score * self.config["diversity_weight"]
        )
        
        # Determine confidence level and quality
        confidence_level = self._determine_confidence_level(overall_score, evidence_items)
        evidence_quality = self._determine_evidence_quality(overall_score, evidence_items)
        validation_status = self._determine_validation_status(evidence_items, overall_score)
        
        return EvidenceScore(
            overall_score=overall_score,
            similarity_component=similarity_component,
            authority_component=authority_component,
            freshness_component=freshness_component,
            cross_reference_component=cross_reference_component,
            source_diversity_score=diversity_score,
            confidence_level=confidence_level,
            evidence_quality=evidence_quality,
            validation_status=validation_status,
            sources_count=len(evidence_items),
            distinct_sources=len(set(item.source.source_id for item in evidence_items))
        )
    
    def _calculate_similarity_component(self, evidence_items: List[EvidenceItem]) -> float:
        """Calculate similarity component of evidence score."""
        if not evidence_items:
            return 0.0
        
        # Use the highest similarity score as base, with penalty for low diversity
        max_similarity = max(item.similarity_score for item in evidence_items)
        avg_similarity = sum(item.similarity_score for item in evidence_items) / len(evidence_items)
        
        # Weight towards max similarity but consider average for diversity
        return (max_similarity * 0.7) + (avg_similarity * 0.3)
    
    def _calculate_authority_component(self, evidence_items: List[EvidenceItem]) -> float:
        """Calculate authority component based on source credibility."""
        if not evidence_items:
            return 0.0
        
        authority_scores = []
        for item in evidence_items:
            source_type = item.source.source_type.lower()
            base_authority = self.source_authority_map.get(source_type, 0.5)
            
            # Adjust based on source credibility and content quality
            adjusted_authority = (
                base_authority * 0.6 +
                item.source.source_credibility * 0.3 +
                item.source.content_quality * 0.1
            )
            authority_scores.append(adjusted_authority)
        
        # Use weighted average, giving more weight to higher authority sources
        authority_scores.sort(reverse=True)
        if len(authority_scores) == 1:
            return authority_scores[0]
        elif len(authority_scores) == 2:
            return (authority_scores[0] * 0.7) + (authority_scores[1] * 0.3)
        else:
            return (authority_scores[0] * 0.5) + (authority_scores[1] * 0.3) + (authority_scores[2] * 0.2)
    
    def _calculate_freshness_component(self, evidence_items: List[EvidenceItem]) -> float:
        """Calculate freshness component based on content age and recency."""
        if not evidence_items:
            return 0.0
        
        now = datetime.now(timezone.utc)
        freshness_scores = []
        
        for item in evidence_items:
            if item.source.last_updated:
                age_days = (now - item.source.last_updated).days
                # Exponential decay for freshness
                freshness = max(0.0, 1.0 - (age_days / self.config["max_age_days"]))
            else:
                # Unknown age gets medium freshness score
                freshness = 0.5
            
            freshness_scores.append(freshness)
        
        # Weight towards most recent content
        freshness_scores.sort(reverse=True)
        if len(freshness_scores) == 1:
            return freshness_scores[0]
        else:
            return (freshness_scores[0] * 0.6) + (sum(freshness_scores[1:]) / len(freshness_scores[1:]) * 0.4)
    
    def _calculate_cross_reference_component(self, evidence_items: List[EvidenceItem]) -> float:
        """Calculate cross-reference validation component."""
        if len(evidence_items) < 2:
            return 0.0
        
        # Check for cross-references between evidence items
        cross_reference_score = 0.0
        total_pairs = 0
        
        for i, item1 in enumerate(evidence_items):
            for j, item2 in enumerate(evidence_items[i+1:], i+1):
                total_pairs += 1
                
                # Check keyword overlap
                keywords1 = set(item1.keywords or [])
                keywords2 = set(item2.keywords or [])
                
                if keywords1 and keywords2:
                    overlap = len(keywords1.intersection(keywords2)) / len(keywords1.union(keywords2))
                    if overlap >= self.config["cross_reference_threshold"]:
                        cross_reference_score += 1.0
                    else:
                        cross_reference_score += overlap
                else:
                    # Fallback to similarity score comparison
                    similarity_diff = abs(item1.similarity_score - item2.similarity_score)
                    if similarity_diff <= 0.2:  # Similar similarity scores
                        cross_reference_score += 0.8
                    else:
                        cross_reference_score += 0.4
        
        return cross_reference_score / total_pairs if total_pairs > 0 else 0.0
    
    def _calculate_source_diversity_score(self, evidence_items: List[EvidenceItem]) -> float:
        """Calculate source diversity score."""
        if not evidence_items:
            return 0.0
        
        # Count unique sources
        unique_sources = len(set(item.source.source_id for item in evidence_items))
        total_sources = len(evidence_items)
        
        # Diversity ratio
        diversity_ratio = unique_sources / total_sources
        
        # Bonus for having multiple distinct sources
        diversity_bonus = min(0.3, (unique_sources - 1) * 0.1)
        
        return min(1.0, diversity_ratio + diversity_bonus)
    
    def _determine_confidence_level(self, overall_score: float, evidence_items: List[EvidenceItem]) -> str:
        """Determine confidence level based on overall score and evidence quality."""
        if overall_score >= 0.8:
            return "high"
        elif overall_score >= 0.6:
            return "medium"
        else:
            return "low"
    
    def _determine_evidence_quality(self, overall_score: float, evidence_items: List[EvidenceItem]) -> str:
        """Determine evidence quality based on score and source diversity."""
        if overall_score >= 0.85 and len(evidence_items) >= 3:
            return "excellent"
        elif overall_score >= 0.7 and len(evidence_items) >= 2:
            return "good"
        elif overall_score >= 0.5:
            return "fair"
        else:
            return "poor"
    
    def _determine_validation_status(self, evidence_items: List[EvidenceItem], overall_score: float) -> str:
        """Determine validation status based on evidence quality and source diversity."""
        unique_sources = len(set(item.source.source_id for item in evidence_items))
        
        if overall_score >= self.config["confidence_threshold"] and unique_sources >= self.config["min_sources"]:
            return "validated"
        elif overall_score >= self.config["confidence_threshold"] or unique_sources >= self.config["min_sources"]:
            return "partial"
        else:
            return "insufficient"
    
    def _create_empty_evidence_score(self) -> EvidenceScore:
        """Create empty evidence score for no evidence."""
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
        )
    
    def create_evidence_source(
        self,
        source_id: str,
        source_type: str,
        content: str,
        last_updated: Optional[datetime] = None,
        authority_level: Optional[float] = None
    ) -> EvidenceSource:
        """Create an EvidenceSource with calculated quality metrics."""
        if authority_level is None:
            authority_level = self.source_authority_map.get(source_type.lower(), 0.5)
        
        # Calculate content quality
        content_quality = self._calculate_content_quality(content)
        
        # Calculate freshness
        if last_updated:
            now = datetime.now(timezone.utc)
            age_days = (now - last_updated).days
            freshness_score = max(0.0, 1.0 - (age_days / self.config["max_age_days"]))
        else:
            freshness_score = 0.5
        
        return EvidenceSource(
            source_id=source_id,
            source_type=source_type,
            authority_level=authority_level,
            freshness_score=freshness_score,
            content_quality=content_quality,
            last_updated=last_updated,
            source_credibility=authority_level
        )
    
    def _calculate_content_quality(self, content: str) -> float:
        """Calculate content quality based on various indicators."""
        if not content:
            return 0.0
        
        quality_score = 0.0
        content_lower = content.lower()
        
        # Check for structure indicators
        if any(indicator in content_lower for indicator in ["##", "###", "1.", "2.", "- ", "* "]):
            quality_score += self.content_quality_indicators["has_structure"]
        
        # Check for examples
        if any(indicator in content_lower for indicator in ["example", "for instance", "such as", "e.g."]):
            quality_score += self.content_quality_indicators["has_examples"]
        
        # Check for references
        if any(indicator in content_lower for indicator in ["reference", "see also", "link", "citation"]):
            quality_score += self.content_quality_indicators["has_references"]
        
        # Check for metadata
        if any(indicator in content_lower for indicator in ["author:", "date:", "version:", "updated:"]):
            quality_score += self.content_quality_indicators["has_metadata"]
        
        # Check completeness (length and detail)
        word_count = len(content.split())
        if word_count >= 100:
            quality_score += self.content_quality_indicators["completeness"]
        elif word_count >= 50:
            quality_score += self.content_quality_indicators["completeness"] * 0.7
        
        # Check clarity (sentence structure, technical terms)
        sentences = content.split('.')
        avg_sentence_length = sum(len(s.split()) for s in sentences) / len(sentences) if sentences else 0
        if 10 <= avg_sentence_length <= 25:  # Good sentence length
            quality_score += self.content_quality_indicators["clarity"]
        
        # Check uniqueness (avoid duplicate content)
        if len(set(content.split())) / len(content.split()) > 0.7:  # High word diversity
            quality_score += self.content_quality_indicators["uniqueness"]
        
        return min(1.0, quality_score)
