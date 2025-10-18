"""
Document Extraction Agent - Main Orchestrator
Implements the complete 6-stage NVIDIA NeMo pipeline for warehouse document processing.
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import uuid
from dataclasses import dataclass
import json

from chain_server.services.llm.nim_client import get_nim_client
from chain_server.agents.document.models.document_models import (
    DocumentResponse,
    DocumentUpload,
    ProcessingStage,
    ProcessingStatus,
    DocumentType,
    QualityDecision,
    RoutingAction,
    DocumentProcessingError,
)

# Import all pipeline stages
from .preprocessing.nemo_retriever import NeMoRetrieverPreprocessor
from .preprocessing.layout_detection import LayoutDetectionService
from .ocr.nemo_ocr import NeMoOCRService
from .ocr.nemotron_parse import NemotronParseService
from .processing.small_llm_processor import SmallLLMProcessor
from .processing.entity_extractor import EntityExtractor
from .processing.embedding_indexing import EmbeddingIndexingService
from .validation.large_llm_judge import LargeLLMJudge
from .validation.quality_scorer import QualityScorer
from .routing.intelligent_router import IntelligentRouter
from .routing.workflow_manager import WorkflowManager

logger = logging.getLogger(__name__)


@dataclass
class DocumentProcessingResult:
    """Complete document processing result."""

    document_id: str
    status: ProcessingStatus
    stages_completed: List[ProcessingStage]
    extracted_data: Dict[str, Any]
    quality_scores: Dict[str, float]
    routing_decision: RoutingAction
    processing_time_ms: int
    errors: List[DocumentProcessingError]
    confidence: float


class DocumentExtractionAgent:
    """
    Main Document Extraction Agent implementing the complete NVIDIA NeMo pipeline.

    Pipeline Stages:
    1. Document Preprocessing (NeMo Retriever)
    2. Intelligent OCR (NeMoRetriever-OCR-v1 + Nemotron Parse)
    3. Small LLM Processing (Llama Nemotron Nano VL 8B)
    4. Embedding & Indexing (nv-embedqa-e5-v5)
    5. Large LLM Judge (Llama 3.1 Nemotron 70B)
    6. Intelligent Routing (Quality-based routing)
    """

    def __init__(self):
        self.nim_client = None

        # Initialize all pipeline stages
        self.preprocessor = NeMoRetrieverPreprocessor()
        self.layout_detector = LayoutDetectionService()
        self.nemo_ocr = NeMoOCRService()
        self.nemotron_parse = NemotronParseService()
        self.small_llm = SmallLLMProcessor()
        self.entity_extractor = EntityExtractor()
        self.embedding_service = EmbeddingIndexingService()
        self.large_llm_judge = LargeLLMJudge()
        self.quality_scorer = QualityScorer()
        self.intelligent_router = IntelligentRouter()
        self.workflow_manager = WorkflowManager()

        # Processing state
        self.active_processes: Dict[str, Dict[str, Any]] = {}

    async def initialize(self):
        """Initialize all pipeline components."""
        try:
            logger.info("Initializing Document Extraction Agent pipeline...")

            # Initialize NIM client
            self.nim_client = await get_nim_client()

            # Initialize all pipeline stages
            await self.preprocessor.initialize()
            await self.layout_detector.initialize()
            await self.nemo_ocr.initialize()
            await self.nemotron_parse.initialize()
            await self.small_llm.initialize()
            await self.entity_extractor.initialize()
            await self.embedding_service.initialize()
            await self.large_llm_judge.initialize()
            await self.quality_scorer.initialize()
            await self.intelligent_router.initialize()
            await self.workflow_manager.initialize()

            logger.info("Document Extraction Agent pipeline initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Document Extraction Agent: {e}")
            raise

    async def process_document(
        self,
        file_path: str,
        document_type: DocumentType,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DocumentProcessingResult:
        """
        Process a document through the complete 6-stage NVIDIA NeMo pipeline.

        Args:
            file_path: Path to the document file
            document_type: Type of document (invoice, receipt, BOL, etc.)
            user_id: ID of the user uploading the document
            metadata: Additional metadata

        Returns:
            Complete processing result with extracted data and quality scores
        """
        document_id = str(uuid.uuid4())
        start_time = datetime.now()

        logger.info(f"Starting document processing pipeline for {document_id}")

        try:
            # Initialize processing state
            processing_state = {
                "document_id": document_id,
                "file_path": file_path,
                "document_type": document_type,
                "user_id": user_id,
                "metadata": metadata or {},
                "start_time": start_time,
                "stages_completed": [],
                "extracted_data": {},
                "quality_scores": {},
                "errors": [],
            }

            self.active_processes[document_id] = processing_state

            # STAGE 1: Document Preprocessing
            logger.info(f"Stage 1: Document preprocessing for {document_id}")
            preprocessing_result = await self.preprocessor.process_document(file_path)
            processing_state["stages_completed"].append(ProcessingStage.PREPROCESSING)
            processing_state["extracted_data"]["preprocessing"] = preprocessing_result

            # Layout detection
            layout_result = await self.layout_detector.detect_layout(
                preprocessing_result
            )
            processing_state["extracted_data"]["layout"] = layout_result

            # STAGE 2: Intelligent OCR Extraction
            logger.info(f"Stage 2: OCR extraction for {document_id}")

            # Primary OCR with NeMoRetriever-OCR-v1
            ocr_result = await self.nemo_ocr.extract_text(
                preprocessing_result["images"], layout_result
            )

            # Advanced OCR with Nemotron Parse for complex documents
            if ocr_result["confidence"] < 0.8:  # Low confidence, try advanced OCR
                advanced_ocr = await self.nemotron_parse.parse_document(
                    preprocessing_result["images"], layout_result
                )
                # Merge results, preferring higher confidence
                if advanced_ocr["confidence"] > ocr_result["confidence"]:
                    ocr_result = advanced_ocr

            processing_state["stages_completed"].append(ProcessingStage.OCR_EXTRACTION)
            processing_state["extracted_data"]["ocr"] = ocr_result

            # STAGE 3: Small LLM Processing
            logger.info(f"Stage 3: Small LLM processing for {document_id}")

            # Process with Llama Nemotron Nano VL 8B
            llm_result = await self.small_llm.process_document(
                preprocessing_result["images"], ocr_result["text"], document_type
            )

            # Entity extraction
            entities = await self.entity_extractor.extract_entities(
                llm_result["structured_data"], document_type
            )

            processing_state["stages_completed"].append(ProcessingStage.LLM_PROCESSING)
            processing_state["extracted_data"]["llm_processing"] = llm_result
            processing_state["extracted_data"]["entities"] = entities

            # STAGE 4: Embedding & Indexing
            logger.info(f"Stage 4: Embedding and indexing for {document_id}")

            # Generate and store embeddings
            embedding_result = (
                await self.embedding_service.generate_and_store_embeddings(
                    document_id, llm_result["structured_data"], entities, document_type
                )
            )

            processing_state["stages_completed"].append(ProcessingStage.EMBEDDING)
            processing_state["extracted_data"]["embedding_result"] = embedding_result

            # STAGE 5: Large LLM Judge & Validator
            logger.info(f"Stage 5: Large LLM judging for {document_id}")

            # Judge with Llama 3.1 Nemotron 70B
            judge_result = await self.large_llm_judge.evaluate_document(
                llm_result["structured_data"], entities, document_type
            )

            # Quality scoring
            quality_scores = await self.quality_scorer.score_document(
                judge_result, entities, document_type
            )

            processing_state["stages_completed"].append(ProcessingStage.VALIDATION)
            processing_state["extracted_data"]["judge_result"] = judge_result
            processing_state["quality_scores"] = quality_scores

            # STAGE 6: Intelligent Routing
            logger.info(f"Stage 6: Intelligent routing for {document_id}")

            routing_decision = await self.intelligent_router.route_document(
                quality_scores, judge_result, document_type
            )

            processing_state["stages_completed"].append(ProcessingStage.ROUTING)

            # Calculate processing time
            end_time = datetime.now()
            processing_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Create final result
            result = DocumentProcessingResult(
                document_id=document_id,
                status=ProcessingStatus.COMPLETED,
                stages_completed=processing_state["stages_completed"],
                extracted_data=processing_state["extracted_data"],
                quality_scores=quality_scores,
                routing_decision=routing_decision,
                processing_time_ms=processing_time_ms,
                errors=processing_state["errors"],
                confidence=judge_result["confidence"],
            )

            # Clean up processing state
            del self.active_processes[document_id]

            logger.info(
                f"Document processing completed for {document_id} in {processing_time_ms}ms"
            )
            return result

        except Exception as e:
            logger.error(f"Document processing failed for {document_id}: {e}")

            # Create error result
            error_result = DocumentProcessingResult(
                document_id=document_id,
                status=ProcessingStatus.FAILED,
                stages_completed=processing_state.get("stages_completed", []),
                extracted_data=processing_state.get("extracted_data", {}),
                quality_scores={},
                routing_decision=RoutingAction.SEND_TO_HUMAN_REVIEW,
                processing_time_ms=int(
                    (datetime.now() - start_time).total_seconds() * 1000
                ),
                errors=[
                    DocumentProcessingError(
                        stage=ProcessingStage.PREPROCESSING,
                        message=str(e),
                        timestamp=datetime.now(),
                    )
                ],
                confidence=0.0,
            )

            # Clean up processing state
            if document_id in self.active_processes:
                del self.active_processes[document_id]

            return error_result

    async def get_processing_status(self, document_id: str) -> Dict[str, Any]:
        """Get the current processing status of a document."""
        if document_id not in self.active_processes:
            return {
                "status": "not_found",
                "message": "Document not found or processing completed",
            }

        processing_state = self.active_processes[document_id]
        current_stage = (
            processing_state["stages_completed"][-1]
            if processing_state["stages_completed"]
            else ProcessingStage.PREPROCESSING
        )

        return {
            "document_id": document_id,
            "status": "processing",
            "current_stage": current_stage.value,
            "stages_completed": len(processing_state["stages_completed"]),
            "total_stages": 6,
            "progress_percentage": (len(processing_state["stages_completed"]) / 6)
            * 100,
            "estimated_completion": processing_state["start_time"].timestamp()
            + 60,  # 60 seconds estimate
            "errors": processing_state["errors"],
        }


# Singleton instance
_document_agent = None


async def get_document_extraction_agent() -> DocumentExtractionAgent:
    """Get singleton instance of Document Extraction Agent."""
    global _document_agent
    if _document_agent is None:
        _document_agent = DocumentExtractionAgent()
        await _document_agent.initialize()
    return _document_agent
