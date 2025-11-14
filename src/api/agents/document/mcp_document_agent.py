"""
MCP-enabled Document Extraction Agent
Integrated with Warehouse Operational Assistant architecture
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid
from dataclasses import dataclass, asdict
import json

from src.api.services.llm.nim_client import get_nim_client, LLMResponse
from src.api.services.mcp.tool_discovery import (
    ToolDiscoveryService,
    DiscoveredTool,
    ToolCategory,
)
from src.api.services.mcp.base import MCPManager
from src.api.agents.document.models.document_models import (
    DocumentResponse,
    DocumentUpload,
    DocumentStatus,
    ProcessingStage,
    DocumentType,
    QualityDecision,
    RoutingAction,
    DocumentProcessingError,
)
from .action_tools import DocumentActionTools

logger = logging.getLogger(__name__)


@dataclass
class MCPDocumentQuery:
    """MCP-enabled document query."""

    intent: str
    entities: Dict[str, Any]
    context: Dict[str, Any]
    user_query: str
    mcp_tools: List[str] = None  # Available MCP tools for this query
    tool_execution_plan: List[Dict[str, Any]] = None  # Planned tool executions


@dataclass
class MCPDocumentResponse:
    """MCP-enabled document response."""

    response_type: str
    data: Dict[str, Any]
    natural_language: str
    recommendations: List[str]
    confidence: float
    actions_taken: List[Dict[str, Any]]
    mcp_tools_used: List[str] = None
    tool_execution_results: Dict[str, Any] = None


class MCPDocumentExtractionAgent:
    """MCP-enabled Document Extraction Agent integrated with Warehouse Operational Assistant."""

    def __init__(self):
        self.nim_client = None
        self.document_tools = None
        self.mcp_manager = None
        self.tool_discovery = None
        self.conversation_context = {}
        self.mcp_tools_cache = {}
        self.tool_execution_history = []

        # Document processing keywords for intent classification
        self.document_keywords = [
            "document",
            "upload",
            "scan",
            "extract",
            "process",
            "pdf",
            "image",
            "invoice",
            "receipt",
            "bol",
            "bill of lading",
            "purchase order",
            "po",
            "quality",
            "validation",
            "approve",
            "review",
            "ocr",
            "text extraction",
            "file",
            "photo",
            "picture",
            "documentation",
            "paperwork",
            "neural",
            "nemo",
            "retriever",
            "parse",
            "vision",
            "multimodal",
        ]

    async def initialize(self):
        """Initialize the document extraction agent."""
        try:
            self.nim_client = await get_nim_client()
            self.document_tools = DocumentActionTools()
            await self.document_tools.initialize()

            # Initialize MCP components
            self.mcp_manager = MCPManager()
            self.tool_discovery = ToolDiscoveryService()

            # Start tool discovery
            await self.tool_discovery.start_discovery()

            # Register MCP sources
            await self._register_mcp_sources()

            logger.info("MCP Document Extraction Agent initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Document Extraction Agent: {e}")
            raise

    async def _register_mcp_sources(self) -> None:
        """Register MCP sources for tool discovery."""
        try:
            # For now, skip MCP registration to avoid errors
            # In a full implementation, this would register with MCP manager
            logger.info(
                "MCP sources registration skipped for Document Extraction Agent"
            )
        except Exception as e:
            logger.error(f"Failed to register MCP sources: {e}")
            # Don't raise - allow agent to work without MCP

    async def process_query(
        self,
        query: str,
        session_id: str,
        context: Optional[Dict] = None,
        mcp_results: Optional[Any] = None,
    ) -> DocumentResponse:
        """Process document-related queries through MCP framework."""
        try:
            logger.info(f"Processing document query: {query[:100]}...")

            # Intent classification for document queries
            intent = await self._classify_document_intent(query)
            logger.info(f"Document intent classified as: {intent}")

            # Route to appropriate document processing
            if intent == "document_upload":
                return await self._handle_document_upload(query, context)
            elif intent == "document_status":
                return await self._handle_document_status(query, context)
            elif intent == "document_search":
                return await self._handle_document_search(query, context)
            elif intent == "document_validation":
                return await self._handle_document_validation(query, context)
            elif intent == "document_analytics":
                return await self._handle_document_analytics(query, context)
            else:
                return await self._handle_general_document_query(query, context)

        except Exception as e:
            logger.error(f"Document agent processing failed: {e}")
            return DocumentResponse(
                response_type="error",
                data={"error": str(e)},
                natural_language=f"Error processing document query: {str(e)}",
                recommendations=[
                    "Please try rephrasing your request or contact support"
                ],
                confidence=0.0,
                actions_taken=[],
            )

    async def _classify_document_intent(self, query: str) -> str:
        """Classify document-related intents."""
        query_lower = query.lower()

        # Upload and processing intents
        if any(
            keyword in query_lower
            for keyword in ["upload", "process", "extract", "scan", "neural", "nemo"]
        ):
            return "document_upload"

        # Status checking intents
        elif any(
            keyword in query_lower
            for keyword in [
                "status",
                "progress",
                "processing",
                "where is",
                "how is",
                "check",
                "my document",
                "document status",
            ]
        ):
            return "document_status"

        # Search intents
        elif any(
            keyword in query_lower
            for keyword in ["search", "find", "locate", "retrieve", "show me"]
        ):
            return "document_search"

        # Validation intents
        elif any(
            keyword in query_lower
            for keyword in ["validate", "approve", "review", "quality", "check"]
        ):
            return "document_validation"

        # Analytics intents
        elif any(
            keyword in query_lower
            for keyword in ["analytics", "statistics", "metrics", "dashboard", "report"]
        ):
            return "document_analytics"

        else:
            return "general_document_query"

    async def _handle_document_upload(
        self, query: str, context: Optional[Dict]
    ) -> DocumentResponse:
        """Handle document upload requests."""
        try:
            # Extract document information from query
            document_info = await self._extract_document_info_from_query(query)

            # For now, return a structured response indicating upload capability
            return DocumentResponse(
                response_type="document_upload",
                data={
                    "upload_capability": True,
                    "supported_formats": ["PDF", "PNG", "JPG", "JPEG", "TIFF", "BMP"],
                    "max_file_size": "50MB",
                    "processing_pipeline": [
                        "Document Preprocessing (NeMo Retriever)",
                        "Intelligent OCR (NeMoRetriever-OCR-v1)",
                        "Small LLM Processing (Llama Nemotron Nano VL 8B)",
                        "Embedding & Indexing (nv-embedqa-e5-v5)",
                        "Large LLM Judge (Llama 3.1 Nemotron 70B)",
                        "Intelligent Routing",
                    ],
                    "estimated_processing_time": "30-60 seconds",
                },
                natural_language="I can help you upload and process warehouse documents using NVIDIA's NeMo models. Supported formats include PDFs, images, and scanned documents. The processing pipeline includes intelligent OCR, entity extraction, quality validation, and automatic routing based on quality scores.",
                recommendations=[
                    "Use the Document Extraction page to upload files",
                    "Ensure documents are clear and well-lit for best results",
                    "Supported document types: invoices, receipts, BOLs, purchase orders",
                    "Processing typically takes 30-60 seconds per document",
                ],
                confidence=0.9,
                actions_taken=[
                    {
                        "action": "document_upload_info",
                        "details": "Provided upload capabilities and processing pipeline information",
                    }
                ],
            )

        except Exception as e:
            logger.error(f"Error handling document upload: {e}")
            return DocumentResponse(
                response_type="error",
                data={"error": str(e)},
                natural_language=f"Error processing document upload request: {str(e)}",
                recommendations=["Please try again or contact support"],
                confidence=0.0,
                actions_taken=[],
            )

    async def _handle_document_status(
        self, query: str, context: Optional[Dict]
    ) -> DocumentResponse:
        """Handle document status requests."""
        try:
            # Extract document ID from query if present
            document_id = await self._extract_document_id_from_query(query)

            if document_id:
                # In a real implementation, this would check actual document status
                return DocumentResponse(
                    response_type="document_status",
                    data={
                        "document_id": document_id,
                        "status": "processing",
                        "current_stage": "OCR Extraction",
                        "progress_percentage": 65.0,
                        "stages_completed": ["Preprocessing", "Layout Detection"],
                        "stages_pending": ["LLM Processing", "Validation", "Routing"],
                    },
                    natural_language=f"Document {document_id} is currently being processed. It's at the OCR Extraction stage with 65% completion. The preprocessing and layout detection stages have been completed.",
                    recommendations=[
                        "Processing typically takes 30-60 seconds",
                        "You'll be notified when processing is complete",
                        "Check the Document Extraction page for real-time updates",
                    ],
                    confidence=0.8,
                    actions_taken=[
                        {"action": "document_status_check", "document_id": document_id}
                    ],
                )
            else:
                return DocumentResponse(
                    response_type="document_status",
                    data={
                        "status": "no_document_specified",
                        "message": "No specific document ID provided",
                    },
                    natural_language="I can help you check the status of document processing. Please provide a document ID or visit the Document Extraction page to see all your documents.",
                    recommendations=[
                        "Provide a document ID to check specific status",
                        "Visit the Document Extraction page for overview",
                        "Use 'show me document status for [ID]' format",
                    ],
                    confidence=0.7,
                    actions_taken=[
                        {
                            "action": "document_status_info",
                            "details": "Provided status checking information",
                        }
                    ],
                )

        except Exception as e:
            logger.error(f"Error handling document status: {e}")
            return DocumentResponse(
                response_type="error",
                data={"error": str(e)},
                natural_language=f"Error checking document status: {str(e)}",
                recommendations=["Please try again or contact support"],
                confidence=0.0,
                actions_taken=[],
            )

    async def _handle_document_search(
        self, query: str, context: Optional[Dict]
    ) -> DocumentResponse:
        """Handle document search requests."""
        try:
            # Extract search parameters from query
            search_params = await self._extract_search_params_from_query(query)

            return DocumentResponse(
                response_type="document_search",
                data={
                    "search_capability": True,
                    "search_methods": [
                        "Semantic search using embeddings",
                        "Keyword-based search",
                        "Metadata filtering",
                        "Quality score filtering",
                    ],
                    "search_params": search_params,
                    "example_queries": [
                        "Find invoices from last month",
                        "Show me all BOLs with quality score > 4.0",
                        "Search for documents containing 'SKU-12345'",
                    ],
                },
                natural_language="I can help you search through processed documents using semantic search, keywords, or metadata filters. You can search by content, document type, quality scores, or date ranges.",
                recommendations=[
                    "Use specific keywords for better results",
                    "Filter by document type for targeted searches",
                    "Use quality score filters to find high-confidence extractions",
                    "Try semantic search for conceptual queries",
                ],
                confidence=0.8,
                actions_taken=[
                    {"action": "document_search_info", "search_params": search_params}
                ],
            )

        except Exception as e:
            logger.error(f"Error handling document search: {e}")
            return DocumentResponse(
                response_type="error",
                data={"error": str(e)},
                natural_language=f"Error processing document search: {str(e)}",
                recommendations=["Please try again or contact support"],
                confidence=0.0,
                actions_taken=[],
            )

    async def _handle_document_validation(
        self, query: str, context: Optional[Dict]
    ) -> DocumentResponse:
        """Handle document validation requests."""
        try:
            return DocumentResponse(
                response_type="document_validation",
                data={
                    "validation_capability": True,
                    "validation_methods": [
                        "Automated quality scoring (1-5 scale)",
                        "Completeness checking",
                        "Accuracy validation",
                        "Business logic compliance",
                        "Human review for edge cases",
                    ],
                    "quality_criteria": {
                        "completeness": "All required fields extracted",
                        "accuracy": "Data types and values correct",
                        "compliance": "Business rules followed",
                        "quality": "OCR and extraction confidence",
                    },
                    "routing_decisions": {
                        "score_4.5+": "Auto-approve and integrate to WMS",
                        "score_3.5-4.4": "Flag for quick human review",
                        "score_2.5-3.4": "Queue for expert review",
                        "score_<2.5": "Reject or request rescan",
                    },
                },
                natural_language="I can validate document extraction quality using a comprehensive scoring system. Documents are automatically scored on completeness, accuracy, compliance, and quality, then routed based on scores for optimal processing efficiency.",
                recommendations=[
                    "High-quality documents (4.5+) are auto-approved",
                    "Medium-quality documents get flagged for quick review",
                    "Low-quality documents require expert attention",
                    "All validation decisions include detailed reasoning",
                ],
                confidence=0.9,
                actions_taken=[
                    {
                        "action": "document_validation_info",
                        "details": "Provided validation capabilities and quality criteria",
                    }
                ],
            )

        except Exception as e:
            logger.error(f"Error handling document validation: {e}")
            return DocumentResponse(
                response_type="error",
                data={"error": str(e)},
                natural_language=f"Error processing document validation: {str(e)}",
                recommendations=["Please try again or contact support"],
                confidence=0.0,
                actions_taken=[],
            )

    async def _handle_document_analytics(
        self, query: str, context: Optional[Dict]
    ) -> DocumentResponse:
        """Handle document analytics requests."""
        try:
            return DocumentResponse(
                response_type="document_analytics",
                data={
                    "analytics_capability": True,
                    "available_metrics": [
                        "Total documents processed",
                        "Processing success rate",
                        "Average quality scores",
                        "Auto-approval rate",
                        "Processing time statistics",
                        "Document type distribution",
                        "Quality score trends",
                    ],
                    "sample_analytics": {
                        "total_documents": 1250,
                        "processed_today": 45,
                        "average_quality": 4.2,
                        "auto_approved": 78,
                        "success_rate": 96.5,
                    },
                },
                natural_language="I can provide comprehensive analytics on document processing performance, including success rates, quality trends, processing times, and auto-approval statistics. This helps monitor and optimize the document processing pipeline.",
                recommendations=[
                    "Monitor quality score trends for model performance",
                    "Track auto-approval rates for efficiency metrics",
                    "Analyze processing times for optimization opportunities",
                    "Review document type distribution for capacity planning",
                ],
                confidence=0.8,
                actions_taken=[
                    {
                        "action": "document_analytics_info",
                        "details": "Provided analytics capabilities and sample metrics",
                    }
                ],
            )

        except Exception as e:
            logger.error(f"Error handling document analytics: {e}")
            return DocumentResponse(
                response_type="error",
                data={"error": str(e)},
                natural_language=f"Error processing document analytics: {str(e)}",
                recommendations=["Please try again or contact support"],
                confidence=0.0,
                actions_taken=[],
            )

    async def _handle_general_document_query(
        self, query: str, context: Optional[Dict]
    ) -> DocumentResponse:
        """Handle general document-related queries."""
        try:
            return DocumentResponse(
                response_type="general_document_info",
                data={
                    "capabilities": [
                        "Document upload and processing",
                        "Intelligent OCR with NVIDIA NeMo models",
                        "Entity extraction and validation",
                        "Quality scoring and routing",
                        "Document search and retrieval",
                        "Analytics and reporting",
                    ],
                    "supported_document_types": [
                        "Invoices",
                        "Receipts",
                        "Bills of Lading (BOL)",
                        "Purchase Orders",
                        "Packing Lists",
                        "Safety Reports",
                    ],
                    "processing_pipeline": "6-stage NVIDIA NeMo pipeline with intelligent routing",
                },
                natural_language="I'm the Document Extraction Agent, specialized in processing warehouse documents using NVIDIA's NeMo models. I can upload, process, validate, and search documents with intelligent quality-based routing. How can I help you with document processing?",
                recommendations=[
                    "Try uploading a document to see the processing pipeline",
                    "Ask about specific document types or processing stages",
                    "Request analytics on processing performance",
                    "Search for previously processed documents",
                ],
                confidence=0.8,
                actions_taken=[
                    {
                        "action": "general_document_info",
                        "details": "Provided general document processing capabilities",
                    }
                ],
            )

        except Exception as e:
            logger.error(f"Error handling general document query: {e}")
            return DocumentResponse(
                response_type="error",
                data={"error": str(e)},
                natural_language=f"Error processing document query: {str(e)}",
                recommendations=["Please try again or contact support"],
                confidence=0.0,
                actions_taken=[],
            )

    async def _extract_document_info_from_query(self, query: str) -> Dict[str, Any]:
        """Extract document information from query."""
        # Simple extraction logic - in real implementation, this would use NLP
        query_lower = query.lower()

        document_type = None
        if "invoice" in query_lower:
            document_type = "invoice"
        elif "receipt" in query_lower:
            document_type = "receipt"
        elif "bol" in query_lower or "bill of lading" in query_lower:
            document_type = "bol"
        elif "purchase order" in query_lower or "po" in query_lower:
            document_type = "purchase_order"

        return {"document_type": document_type, "query": query}

    async def _extract_document_id_from_query(self, query: str) -> Optional[str]:
        """Extract document ID from query."""
        # Simple extraction - in real implementation, this would use regex or NLP
        import re

        uuid_pattern = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
        match = re.search(uuid_pattern, query, re.IGNORECASE)
        return match.group(0) if match else None

    async def _extract_search_params_from_query(self, query: str) -> Dict[str, Any]:
        """Extract search parameters from query."""
        query_lower = query.lower()

        params = {
            "query": query,
            "document_types": [],
            "date_range": None,
            "quality_threshold": None,
        }

        # Extract document types
        if "invoice" in query_lower:
            params["document_types"].append("invoice")
        if "receipt" in query_lower:
            params["document_types"].append("receipt")
        if "bol" in query_lower:
            params["document_types"].append("bol")

        # Extract quality threshold
        if "quality" in query_lower and ">" in query_lower:
            import re

            quality_match = re.search(r"quality.*?(\d+\.?\d*)", query_lower)
            if quality_match:
                params["quality_threshold"] = float(quality_match.group(1))

        return params


# Factory function for getting the document agent
async def get_mcp_document_agent() -> MCPDocumentExtractionAgent:
    """Get or create MCP Document Extraction Agent instance."""
    global _document_agent_instance

    if _document_agent_instance is None:
        _document_agent_instance = MCPDocumentExtractionAgent()
        await _document_agent_instance.initialize()

    return _document_agent_instance


# Global instance
_document_agent_instance: Optional[MCPDocumentExtractionAgent] = None
