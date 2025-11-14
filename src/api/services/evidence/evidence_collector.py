"""
Evidence Collection and Context Synthesis System

This module provides comprehensive evidence collection and context synthesis
capabilities for the warehouse operational assistant, enabling better
response quality and source attribution.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json

from src.api.services.llm.nim_client import get_nim_client, LLMResponse
from src.retrieval.hybrid_retriever import get_hybrid_retriever, SearchContext
from src.memory.memory_manager import get_memory_manager
from src.api.services.mcp.tool_discovery import ToolDiscoveryService, ToolCategory

logger = logging.getLogger(__name__)


class EvidenceType(Enum):
    """Types of evidence."""

    EQUIPMENT_DATA = "equipment_data"
    OPERATIONS_DATA = "operations_data"
    SAFETY_DATA = "safety_data"
    DOCUMENT_DATA = "document_data"
    HISTORICAL_DATA = "historical_data"
    REAL_TIME_DATA = "real_time_data"
    USER_CONTEXT = "user_context"
    SYSTEM_CONTEXT = "system_context"


class EvidenceSource(Enum):
    """Sources of evidence."""

    DATABASE = "database"
    MCP_TOOLS = "mcp_tools"
    MEMORY = "memory"
    RETRIEVAL = "retrieval"
    USER_INPUT = "user_input"
    SYSTEM_STATE = "system_state"


class EvidenceQuality(Enum):
    """Quality levels of evidence."""

    HIGH = "high"  # Direct, recent, verified
    MEDIUM = "medium"  # Indirect, older, partially verified
    LOW = "low"  # Inferred, outdated, unverified


@dataclass
class Evidence:
    """Represents a piece of evidence."""

    evidence_id: str
    evidence_type: EvidenceType
    source: EvidenceSource
    content: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    quality: EvidenceQuality = EvidenceQuality.MEDIUM
    timestamp: datetime = field(default_factory=datetime.utcnow)
    confidence: float = 0.0
    relevance_score: float = 0.0
    source_attribution: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass
class EvidenceContext:
    """Context for evidence collection."""

    query: str
    intent: str
    entities: Dict[str, Any]
    session_id: str
    user_context: Dict[str, Any] = field(default_factory=dict)
    system_context: Dict[str, Any] = field(default_factory=dict)
    time_range: Optional[Dict[str, datetime]] = None
    evidence_types: List[EvidenceType] = field(default_factory=list)
    max_evidence: int = 10


class EvidenceCollector:
    """
    Comprehensive evidence collection and context synthesis system.

    This class provides:
    - Multi-source evidence collection
    - Evidence quality assessment
    - Context synthesis and relevance scoring
    - Source attribution and traceability
    - Evidence-based response enhancement
    """

    def __init__(self):
        self.nim_client = None
        self.hybrid_retriever = None
        self.memory_manager = None
        self.tool_discovery = None
        self.evidence_cache = {}
        self.collection_stats = {
            "total_collections": 0,
            "evidence_by_type": {},
            "evidence_by_source": {},
            "average_confidence": 0.0,
        }

    async def initialize(self) -> None:
        """Initialize the evidence collector."""
        try:
            self.nim_client = await get_nim_client()
            self.hybrid_retriever = await get_hybrid_retriever()
            self.memory_manager = await get_memory_manager()
            self.tool_discovery = ToolDiscoveryService()
            await self.tool_discovery.start_discovery()

            logger.info("Evidence Collector initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Evidence Collector: {e}")
            raise

    async def collect_evidence(self, context: EvidenceContext) -> List[Evidence]:
        """
        Collect comprehensive evidence for a given context.

        Args:
            context: Evidence collection context

        Returns:
            List of collected evidence
        """
        try:
            evidence_list = []

            # Collect evidence from multiple sources
            collection_tasks = [
                self._collect_equipment_evidence(context),
                self._collect_operations_evidence(context),
                self._collect_safety_evidence(context),
                self._collect_historical_evidence(context),
                self._collect_user_context_evidence(context),
                self._collect_system_context_evidence(context),
            ]

            # Execute evidence collection in parallel
            results = await asyncio.gather(*collection_tasks, return_exceptions=True)

            # Combine results
            for result in results:
                if isinstance(result, list):
                    evidence_list.extend(result)
                elif isinstance(result, Exception):
                    logger.error(f"Evidence collection error: {result}")

            # Score and rank evidence
            evidence_list = await self._score_and_rank_evidence(evidence_list, context)

            # Update statistics
            self._update_collection_stats(evidence_list)

            logger.info(
                f"Collected {len(evidence_list)} pieces of evidence for query: {context.query[:50]}..."
            )

            return evidence_list[: context.max_evidence]

        except Exception as e:
            logger.error(f"Error collecting evidence: {e}")
            return []

    async def _collect_equipment_evidence(
        self, context: EvidenceContext
    ) -> List[Evidence]:
        """Collect equipment-related evidence."""
        evidence_list = []

        try:
            # Extract equipment-related entities
            equipment_entities = {
                k: v
                for k, v in context.entities.items()
                if k in ["equipment_id", "equipment_type", "asset_id", "zone", "status"]
            }

            if not equipment_entities and "equipment" not in context.intent.lower():
                return evidence_list

            # Use MCP tools to get equipment data
            if self.tool_discovery:
                equipment_tools = await self.tool_discovery.get_tools_by_category(
                    ToolCategory.EQUIPMENT
                )

                for tool in equipment_tools[:3]:  # Limit to 3 tools
                    try:
                        # Prepare arguments for tool execution
                        arguments = self._prepare_equipment_tool_arguments(
                            tool, equipment_entities
                        )

                        # Execute tool
                        result = await self.tool_discovery.execute_tool(
                            tool.tool_id, arguments
                        )

                        if result and not result.get("error"):
                            evidence = Evidence(
                                evidence_id=f"equipment_{tool.tool_id}_{datetime.utcnow().timestamp()}",
                                evidence_type=EvidenceType.EQUIPMENT_DATA,
                                source=EvidenceSource.MCP_TOOLS,
                                content=result,
                                metadata={
                                    "tool_name": tool.name,
                                    "tool_id": tool.tool_id,
                                    "arguments": arguments,
                                    "execution_time": datetime.utcnow().isoformat(),
                                },
                                quality=EvidenceQuality.HIGH,
                                confidence=0.9,
                                source_attribution=f"MCP Tool: {tool.name}",
                                tags=["equipment", "real_time", "mcp"],
                            )
                            evidence_list.append(evidence)

                    except Exception as e:
                        logger.error(
                            f"Error collecting equipment evidence from tool {tool.name}: {e}"
                        )

            # Use hybrid retriever for additional equipment context
            if self.hybrid_retriever:
                try:
                    search_context = SearchContext(
                        query=context.query, filters={"category": "equipment"}, limit=5
                    )

                    retrieval_results = await self.hybrid_retriever.search(
                        search_context
                    )

                    if retrieval_results and (
                        retrieval_results.structured_results
                        or retrieval_results.vector_results
                    ):
                        # Convert HybridSearchResult to dictionary for storage
                        results_data = {
                            "structured_results": [
                                {
                                    "item_id": item.item_id,
                                    "name": item.name,
                                    "category": item.category,
                                    "location": item.location,
                                    "quantity": item.quantity,
                                    "status": item.status,
                                }
                                for item in retrieval_results.structured_results
                            ],
                            "vector_results": [
                                {
                                    "content": result.content,
                                    "score": result.score,
                                    "metadata": result.metadata,
                                }
                                for result in retrieval_results.vector_results
                            ],
                            "combined_score": retrieval_results.combined_score,
                            "search_type": retrieval_results.search_type,
                        }

                        evidence = Evidence(
                            evidence_id=f"equipment_retrieval_{datetime.utcnow().timestamp()}",
                            evidence_type=EvidenceType.EQUIPMENT_DATA,
                            source=EvidenceSource.RETRIEVAL,
                            content=results_data,
                            metadata={
                                "search_context": search_context.__dict__,
                                "result_count": len(
                                    retrieval_results.structured_results
                                )
                                + len(retrieval_results.vector_results),
                            },
                            quality=EvidenceQuality.MEDIUM,
                            confidence=0.7,
                            source_attribution="Hybrid Retriever",
                            tags=["equipment", "retrieval", "context"],
                        )
                        evidence_list.append(evidence)

                except Exception as e:
                    logger.error(
                        f"Error collecting equipment evidence from retriever: {e}"
                    )

        except Exception as e:
            logger.error(f"Error in equipment evidence collection: {e}")

        return evidence_list

    async def _collect_operations_evidence(
        self, context: EvidenceContext
    ) -> List[Evidence]:
        """Collect operations-related evidence."""
        evidence_list = []

        try:
            # Extract operations-related entities
            operations_entities = {
                k: v
                for k, v in context.entities.items()
                if k
                in ["task_id", "user_id", "worker_id", "shift", "zone", "operation"]
            }

            if not operations_entities and "operation" not in context.intent.lower():
                return evidence_list

            # Use MCP tools for operations data
            if self.tool_discovery:
                operations_tools = await self.tool_discovery.get_tools_by_category(
                    ToolCategory.OPERATIONS
                )

                for tool in operations_tools[:2]:  # Limit to 2 tools
                    try:
                        arguments = self._prepare_operations_tool_arguments(
                            tool, operations_entities
                        )
                        result = await self.tool_discovery.execute_tool(
                            tool.tool_id, arguments
                        )

                        if result and not result.get("error"):
                            evidence = Evidence(
                                evidence_id=f"operations_{tool.tool_id}_{datetime.utcnow().timestamp()}",
                                evidence_type=EvidenceType.OPERATIONS_DATA,
                                source=EvidenceSource.MCP_TOOLS,
                                content=result,
                                metadata={
                                    "tool_name": tool.name,
                                    "tool_id": tool.tool_id,
                                    "arguments": arguments,
                                },
                                quality=EvidenceQuality.HIGH,
                                confidence=0.9,
                                source_attribution=f"MCP Tool: {tool.name}",
                                tags=["operations", "real_time", "mcp"],
                            )
                            evidence_list.append(evidence)

                    except Exception as e:
                        logger.error(
                            f"Error collecting operations evidence from tool {tool.name}: {e}"
                        )

        except Exception as e:
            logger.error(f"Error in operations evidence collection: {e}")

        return evidence_list

    async def _collect_safety_evidence(
        self, context: EvidenceContext
    ) -> List[Evidence]:
        """Collect safety-related evidence."""
        evidence_list = []

        try:
            # Extract safety-related entities
            safety_entities = {
                k: v
                for k, v in context.entities.items()
                if k
                in ["incident_id", "safety_type", "severity", "location", "procedure"]
            }

            if not safety_entities and "safety" not in context.intent.lower():
                return evidence_list

            # Use MCP tools for safety data
            if self.tool_discovery:
                safety_tools = await self.tool_discovery.get_tools_by_category(
                    ToolCategory.SAFETY
                )

                for tool in safety_tools[:2]:  # Limit to 2 tools
                    try:
                        arguments = self._prepare_safety_tool_arguments(
                            tool, safety_entities
                        )
                        result = await self.tool_discovery.execute_tool(
                            tool.tool_id, arguments
                        )

                        if result and not result.get("error"):
                            evidence = Evidence(
                                evidence_id=f"safety_{tool.tool_id}_{datetime.utcnow().timestamp()}",
                                evidence_type=EvidenceType.SAFETY_DATA,
                                source=EvidenceSource.MCP_TOOLS,
                                content=result,
                                metadata={
                                    "tool_name": tool.name,
                                    "tool_id": tool.tool_id,
                                    "arguments": arguments,
                                },
                                quality=EvidenceQuality.HIGH,
                                confidence=0.9,
                                source_attribution=f"MCP Tool: {tool.name}",
                                tags=["safety", "real_time", "mcp"],
                            )
                            evidence_list.append(evidence)

                    except Exception as e:
                        logger.error(
                            f"Error collecting safety evidence from tool {tool.name}: {e}"
                        )

        except Exception as e:
            logger.error(f"Error in safety evidence collection: {e}")

        return evidence_list

    async def _collect_historical_evidence(
        self, context: EvidenceContext
    ) -> List[Evidence]:
        """Collect historical evidence from memory."""
        evidence_list = []

        try:
            if self.memory_manager:
                # Search for relevant historical data
                memory_results = await self.memory_manager.get_context_for_query(
                    session_id=context.session_id,
                    user_id="system",  # Use system as default user
                    query=context.query,
                )

                if memory_results:
                    evidence = Evidence(
                        evidence_id=f"historical_{datetime.utcnow().timestamp()}",
                        evidence_type=EvidenceType.HISTORICAL_DATA,
                        source=EvidenceSource.MEMORY,
                        content=memory_results,
                        metadata={
                            "session_id": context.session_id,
                            "context_keys": list(memory_results.keys()),
                        },
                        quality=EvidenceQuality.MEDIUM,
                        confidence=0.6,
                        source_attribution="Memory System",
                        tags=["historical", "memory", "context"],
                    )
                    evidence_list.append(evidence)

        except Exception as e:
            logger.error(f"Error collecting historical evidence: {e}")

        return evidence_list

    async def _collect_user_context_evidence(
        self, context: EvidenceContext
    ) -> List[Evidence]:
        """Collect user context evidence."""
        evidence_list = []

        try:
            if context.user_context:
                evidence = Evidence(
                    evidence_id=f"user_context_{datetime.utcnow().timestamp()}",
                    evidence_type=EvidenceType.USER_CONTEXT,
                    source=EvidenceSource.USER_INPUT,
                    content=context.user_context,
                    metadata={
                        "session_id": context.session_id,
                        "context_keys": list(context.user_context.keys()),
                    },
                    quality=EvidenceQuality.HIGH,
                    confidence=0.8,
                    source_attribution="User Context",
                    tags=["user", "context", "session"],
                )
                evidence_list.append(evidence)

        except Exception as e:
            logger.error(f"Error collecting user context evidence: {e}")

        return evidence_list

    async def _collect_system_context_evidence(
        self, context: EvidenceContext
    ) -> List[Evidence]:
        """Collect system context evidence."""
        evidence_list = []

        try:
            if context.system_context:
                evidence = Evidence(
                    evidence_id=f"system_context_{datetime.utcnow().timestamp()}",
                    evidence_type=EvidenceType.SYSTEM_CONTEXT,
                    source=EvidenceSource.SYSTEM_STATE,
                    content=context.system_context,
                    metadata={
                        "system_keys": list(context.system_context.keys()),
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                    quality=EvidenceQuality.HIGH,
                    confidence=0.9,
                    source_attribution="System State",
                    tags=["system", "context", "state"],
                )
                evidence_list.append(evidence)

        except Exception as e:
            logger.error(f"Error collecting system context evidence: {e}")

        return evidence_list

    def _prepare_equipment_tool_arguments(
        self, tool, entities: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Prepare arguments for equipment tool execution."""
        arguments = {}

        # Map entities to tool parameters
        for param_name in tool.parameters.get("properties", {}):
            if param_name in entities:
                arguments[param_name] = entities[param_name]
            elif (
                param_name in ["asset_id", "equipment_id"]
                and "equipment_id" in entities
            ):
                arguments[param_name] = entities["equipment_id"]
            elif param_name in ["equipment_type"] and "equipment_type" in entities:
                arguments[param_name] = entities["equipment_type"]

        return arguments

    def _prepare_operations_tool_arguments(
        self, tool, entities: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Prepare arguments for operations tool execution."""
        arguments = {}

        for param_name in tool.parameters.get("properties", {}):
            if param_name in entities:
                arguments[param_name] = entities[param_name]

        return arguments

    def _prepare_safety_tool_arguments(
        self, tool, entities: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Prepare arguments for safety tool execution."""
        arguments = {}

        for param_name in tool.parameters.get("properties", {}):
            if param_name in entities:
                arguments[param_name] = entities[param_name]

        return arguments

    async def _score_and_rank_evidence(
        self, evidence_list: List[Evidence], context: EvidenceContext
    ) -> List[Evidence]:
        """Score and rank evidence by relevance and quality."""
        try:
            # Calculate relevance scores
            for evidence in evidence_list:
                evidence.relevance_score = await self._calculate_relevance_score(
                    evidence, context
                )

            # Sort by relevance score and confidence
            evidence_list.sort(
                key=lambda e: (e.relevance_score, e.confidence, e.quality.value),
                reverse=True,
            )

            return evidence_list

        except Exception as e:
            logger.error(f"Error scoring and ranking evidence: {e}")
            return evidence_list

    async def _calculate_relevance_score(
        self, evidence: Evidence, context: EvidenceContext
    ) -> float:
        """Calculate relevance score for evidence."""
        try:
            score = 0.0

            # Base score from confidence and quality
            score += evidence.confidence * 0.4
            score += self._quality_to_score(evidence.quality) * 0.3

            # Relevance based on evidence type and intent
            if evidence.evidence_type.value in context.intent.lower():
                score += 0.2

            # Recency bonus
            age_hours = (datetime.utcnow() - evidence.timestamp).total_seconds() / 3600
            if age_hours < 1:
                score += 0.1
            elif age_hours < 24:
                score += 0.05

            return min(score, 1.0)

        except Exception as e:
            logger.error(f"Error calculating relevance score: {e}")
            return 0.0

    def _quality_to_score(self, quality: EvidenceQuality) -> float:
        """Convert quality enum to numeric score."""
        quality_scores = {
            EvidenceQuality.HIGH: 1.0,
            EvidenceQuality.MEDIUM: 0.6,
            EvidenceQuality.LOW: 0.3,
        }
        return quality_scores.get(quality, 0.5)

    def _update_collection_stats(self, evidence_list: List[Evidence]) -> None:
        """Update collection statistics."""
        try:
            self.collection_stats["total_collections"] += 1

            # Count by type
            for evidence in evidence_list:
                evidence_type = evidence.evidence_type.value
                self.collection_stats["evidence_by_type"][evidence_type] = (
                    self.collection_stats["evidence_by_type"].get(evidence_type, 0) + 1
                )

                # Count by source
                source = evidence.source.value
                self.collection_stats["evidence_by_source"][source] = (
                    self.collection_stats["evidence_by_source"].get(source, 0) + 1
                )

            # Calculate average confidence
            if evidence_list:
                total_confidence = sum(e.confidence for e in evidence_list)
                self.collection_stats["average_confidence"] = total_confidence / len(
                    evidence_list
                )

        except Exception as e:
            logger.error(f"Error updating collection stats: {e}")

    async def synthesize_evidence(
        self, evidence_list: List[Evidence], context: EvidenceContext
    ) -> Dict[str, Any]:
        """Synthesize evidence into a comprehensive context."""
        try:
            synthesis = {
                "evidence_summary": {
                    "total_evidence": len(evidence_list),
                    "evidence_by_type": {},
                    "evidence_by_source": {},
                    "average_confidence": 0.0,
                    "high_confidence_count": 0,
                },
                "key_findings": [],
                "source_attributions": [],
                "confidence_assessment": {},
                "recommendations": [],
            }

            if not evidence_list:
                return synthesis

            # Analyze evidence
            for evidence in evidence_list:
                # Count by type
                evidence_type = evidence.evidence_type.value
                synthesis["evidence_summary"]["evidence_by_type"][evidence_type] = (
                    synthesis["evidence_summary"]["evidence_by_type"].get(
                        evidence_type, 0
                    )
                    + 1
                )

                # Count by source
                source = evidence.source.value
                synthesis["evidence_summary"]["evidence_by_source"][source] = (
                    synthesis["evidence_summary"]["evidence_by_source"].get(source, 0)
                    + 1
                )

                # Track high confidence evidence
                if evidence.confidence >= 0.8:
                    synthesis["evidence_summary"]["high_confidence_count"] += 1

                # Collect source attributions
                if evidence.source_attribution:
                    synthesis["source_attributions"].append(evidence.source_attribution)

                # Extract key findings
                if evidence.confidence >= 0.7:
                    synthesis["key_findings"].append(
                        {
                            "content": evidence.content,
                            "source": evidence.source_attribution,
                            "confidence": evidence.confidence,
                            "type": evidence.evidence_type.value,
                        }
                    )

            # Calculate average confidence
            total_confidence = sum(e.confidence for e in evidence_list)
            synthesis["evidence_summary"]["average_confidence"] = (
                total_confidence / len(evidence_list)
            )

            # Generate recommendations based on evidence
            synthesis["recommendations"] = (
                await self._generate_evidence_recommendations(evidence_list, context)
            )

            return synthesis

        except Exception as e:
            logger.error(f"Error synthesizing evidence: {e}")
            return {"error": str(e)}

    async def _generate_evidence_recommendations(
        self, evidence_list: List[Evidence], context: EvidenceContext
    ) -> List[str]:
        """Generate recommendations based on evidence."""
        recommendations = []

        try:
            # Analyze evidence patterns
            high_confidence_count = sum(1 for e in evidence_list if e.confidence >= 0.8)
            equipment_evidence = [
                e
                for e in evidence_list
                if e.evidence_type == EvidenceType.EQUIPMENT_DATA
            ]
            safety_evidence = [
                e for e in evidence_list if e.evidence_type == EvidenceType.SAFETY_DATA
            ]

            # Generate contextual recommendations
            if high_confidence_count < 2:
                recommendations.append(
                    "Consider gathering additional evidence for higher confidence"
                )

            if equipment_evidence and any(
                "maintenance" in str(e.content).lower() for e in equipment_evidence
            ):
                recommendations.append(
                    "Schedule maintenance for equipment showing issues"
                )

            if safety_evidence:
                recommendations.append("Review safety procedures and compliance status")

            # Add general recommendations
            recommendations.extend(
                [
                    "Verify information with multiple sources when possible",
                    "Consider recent changes that might affect the data",
                ]
            )

        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
            recommendations.append("Review evidence quality and sources")

        return recommendations

    def get_collection_stats(self) -> Dict[str, Any]:
        """Get evidence collection statistics."""
        return self.collection_stats.copy()


# Global evidence collector instance
_evidence_collector = None


async def get_evidence_collector() -> EvidenceCollector:
    """Get the global evidence collector instance."""
    global _evidence_collector
    if _evidence_collector is None:
        _evidence_collector = EvidenceCollector()
        await _evidence_collector.initialize()
    return _evidence_collector
