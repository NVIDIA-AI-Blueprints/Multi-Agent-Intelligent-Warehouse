"""
Document Extraction Agent Models
Pydantic models for document processing pipeline
"""

from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any, Union
from enum import Enum
from datetime import datetime
import uuid


class DocumentType(str, Enum):
    """Supported document types for processing."""

    PDF = "pdf"
    IMAGE = "image"
    SCANNED = "scanned"
    MOBILE_PHOTO = "mobile_photo"
    INVOICE = "invoice"
    RECEIPT = "receipt"
    BOL = "bol"  # Bill of Lading
    PURCHASE_ORDER = "purchase_order"
    PACKING_LIST = "packing_list"
    SAFETY_REPORT = "safety_report"


class ProcessingStage(str, Enum):
    """Document processing pipeline stages."""

    UPLOADED = "uploaded"
    PREPROCESSING = "preprocessing"
    OCR_EXTRACTION = "ocr_extraction"
    LLM_PROCESSING = "llm_processing"
    EMBEDDING = "embedding"
    VALIDATION = "validation"
    ROUTING = "routing"
    COMPLETED = "completed"
    FAILED = "failed"


class ProcessingStatus(str, Enum):
    """Processing status for each stage."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class RoutingAction(str, Enum):
    """Intelligent routing actions based on quality scores."""

    AUTO_APPROVE = "auto_approve"
    FLAG_REVIEW = "flag_review"
    EXPERT_REVIEW = "expert_review"
    REJECT = "reject"
    RESCAN = "rescan"


class QualityDecision(str, Enum):
    """Quality validation decisions."""

    APPROVE = "APPROVE"
    REVIEW = "REVIEW"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REJECT = "REJECT"
    RESCAN = "RESCAN"


# Base Models
class DocumentUpload(BaseModel):
    """Document upload request model."""

    filename: str = Field(..., description="Original filename")
    file_type: DocumentType = Field(..., description="Type of document")
    file_size: int = Field(..., description="File size in bytes")
    user_id: Optional[str] = Field(None, description="User ID uploading the document")
    document_type: Optional[str] = Field(None, description="Business document type")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    @validator("file_size")
    def validate_file_size(cls, v):
        if v <= 0:
            raise ValueError("File size must be positive")
        if v > 50 * 1024 * 1024:  # 50MB limit
            raise ValueError("File size exceeds 50MB limit")
        return v


class DocumentStatus(BaseModel):
    """Document processing status model."""

    document_id: str = Field(..., description="Document ID")
    status: ProcessingStage = Field(..., description="Current processing stage")
    current_stage: str = Field(..., description="Current stage name")
    progress_percentage: float = Field(
        ..., ge=0, le=100, description="Progress percentage"
    )
    estimated_completion: Optional[datetime] = Field(
        None, description="Estimated completion time"
    )
    error_message: Optional[str] = Field(None, description="Error message if failed")
    stages_completed: List[str] = Field(
        default_factory=list, description="Completed stages"
    )
    stages_pending: List[str] = Field(
        default_factory=list, description="Pending stages"
    )


class ProcessingStageInfo(BaseModel):
    """Individual processing stage information."""

    stage_name: str = Field(..., description="Stage name")
    status: ProcessingStatus = Field(..., description="Stage status")
    started_at: Optional[datetime] = Field(None, description="Stage start time")
    completed_at: Optional[datetime] = Field(None, description="Stage completion time")
    processing_time_ms: Optional[int] = Field(
        None, description="Processing time in milliseconds"
    )
    error_message: Optional[str] = Field(None, description="Error message if failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Stage metadata")


class ExtractionResult(BaseModel):
    """Extraction result from a processing stage."""

    stage: str = Field(..., description="Processing stage name")
    raw_data: Dict[str, Any] = Field(..., description="Raw extraction data")
    processed_data: Dict[str, Any] = Field(..., description="Processed extraction data")
    confidence_score: float = Field(..., ge=0, le=1, description="Confidence score")
    processing_time_ms: int = Field(..., description="Processing time in milliseconds")
    model_used: str = Field(..., description="NVIDIA model used")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class QualityScore(BaseModel):
    """Quality scoring model."""

    overall_score: float = Field(..., ge=0, le=5, description="Overall quality score")
    completeness_score: float = Field(..., ge=0, le=5, description="Completeness score")
    accuracy_score: float = Field(..., ge=0, le=5, description="Accuracy score")
    compliance_score: float = Field(..., ge=0, le=5, description="Compliance score")
    quality_score: float = Field(..., ge=0, le=5, description="Quality score")
    decision: QualityDecision = Field(..., description="Quality decision")
    reasoning: Dict[str, Any] = Field(..., description="Detailed reasoning")
    issues_found: List[str] = Field(default_factory=list, description="Issues found")
    confidence: float = Field(..., ge=0, le=1, description="Confidence in scoring")
    judge_model: str = Field(..., description="Judge model used")


class RoutingDecision(BaseModel):
    """Intelligent routing decision model."""

    routing_action: RoutingAction = Field(..., description="Routing action")
    routing_reason: str = Field(..., description="Reason for routing decision")
    wms_integration_status: str = Field(..., description="WMS integration status")
    wms_integration_data: Optional[Dict[str, Any]] = Field(
        None, description="WMS integration data"
    )
    human_review_required: bool = Field(
        False, description="Whether human review is required"
    )
    human_reviewer_id: Optional[str] = Field(None, description="Human reviewer ID")
    estimated_processing_time: Optional[int] = Field(
        None, description="Estimated processing time"
    )


class DocumentSearchMetadata(BaseModel):
    """Document search and retrieval metadata."""

    search_vector_id: str = Field(..., description="Milvus vector ID")
    embedding_model: str = Field(..., description="Embedding model used")
    extracted_text: str = Field(..., description="Extracted text content")
    key_entities: Dict[str, Any] = Field(
        default_factory=dict, description="Key entities extracted"
    )
    document_summary: str = Field(..., description="Document summary")
    tags: List[str] = Field(default_factory=list, description="Document tags")


# Response Models
class DocumentUploadResponse(BaseModel):
    """Document upload response model."""

    document_id: str = Field(..., description="Generated document ID")
    status: str = Field(..., description="Upload status")
    message: str = Field(..., description="Status message")
    estimated_processing_time: Optional[int] = Field(
        None, description="Estimated processing time in seconds"
    )


class DocumentProcessingResponse(BaseModel):
    """Document processing response model."""

    document_id: str = Field(..., description="Document ID")
    status: ProcessingStage = Field(..., description="Current status")
    progress: float = Field(..., ge=0, le=100, description="Progress percentage")
    current_stage: str = Field(..., description="Current processing stage")
    stages: List[ProcessingStageInfo] = Field(..., description="All processing stages")
    estimated_completion: Optional[datetime] = Field(
        None, description="Estimated completion time"
    )


class DocumentResultsResponse(BaseModel):
    """Document extraction results response model."""

    document_id: str = Field(..., description="Document ID")
    filename: str = Field(..., description="Original filename")
    document_type: str = Field(..., description="Document type")
    extraction_results: List[ExtractionResult] = Field(
        ..., description="Extraction results from all stages"
    )
    quality_score: Optional[QualityScore] = Field(None, description="Quality score")
    routing_decision: Optional[RoutingDecision] = Field(
        None, description="Routing decision"
    )
    search_metadata: Optional[DocumentSearchMetadata] = Field(
        None, description="Search metadata"
    )
    processing_summary: Dict[str, Any] = Field(
        default_factory=dict, description="Processing summary"
    )


class DocumentSearchRequest(BaseModel):
    """Document search request model."""

    query: str = Field(..., description="Search query")
    filters: Optional[Dict[str, Any]] = Field(None, description="Search filters")
    document_types: Optional[List[str]] = Field(
        None, description="Document types to search"
    )
    date_range: Optional[Dict[str, datetime]] = Field(
        None, description="Date range filter"
    )
    quality_threshold: Optional[float] = Field(
        None, ge=0, le=5, description="Minimum quality score"
    )
    limit: int = Field(10, ge=1, le=100, description="Maximum number of results")


class DocumentSearchResult(BaseModel):
    """Document search result model."""

    document_id: str = Field(..., description="Document ID")
    filename: str = Field(..., description="Filename")
    document_type: str = Field(..., description="Document type")
    relevance_score: float = Field(..., ge=0, le=1, description="Relevance score")
    quality_score: float = Field(..., ge=0, le=5, description="Quality score")
    summary: str = Field(..., description="Document summary")
    key_entities: Dict[str, Any] = Field(
        default_factory=dict, description="Key entities"
    )
    upload_date: datetime = Field(..., description="Upload date")
    tags: List[str] = Field(default_factory=list, description="Document tags")


class DocumentSearchResponse(BaseModel):
    """Document search response model."""

    results: List[DocumentSearchResult] = Field(..., description="Search results")
    total_count: int = Field(..., description="Total number of matching documents")
    query: str = Field(..., description="Original search query")
    search_time_ms: int = Field(
        ..., description="Search execution time in milliseconds"
    )


# Agent Response Model (integrated with existing agent system)
class DocumentResponse(BaseModel):
    """Document agent response model (compatible with existing agent system)."""

    response_type: str = Field(..., description="Response type")
    data: Dict[str, Any] = Field(..., description="Response data")
    natural_language: str = Field(..., description="Natural language response")
    recommendations: List[str] = Field(
        default_factory=list, description="Recommendations"
    )
    confidence: float = Field(..., ge=0, le=1, description="Response confidence")
    actions_taken: List[Dict[str, Any]] = Field(
        default_factory=list, description="Actions taken"
    )
    document_id: Optional[str] = Field(None, description="Document ID if applicable")
    processing_status: Optional[DocumentStatus] = Field(
        None, description="Processing status if applicable"
    )


# Error Models
class DocumentProcessingError(BaseModel):
    """Document processing error model."""

    error_code: str = Field(..., description="Error code")
    error_message: str = Field(..., description="Error message")
    document_id: Optional[str] = Field(None, description="Document ID if applicable")
    stage: Optional[str] = Field(
        None, description="Processing stage where error occurred"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now, description="Error timestamp"
    )
    details: Dict[str, Any] = Field(
        default_factory=dict, description="Additional error details"
    )


# Validation Models
class DocumentValidationRequest(BaseModel):
    """Document validation request model."""

    document_id: str = Field(..., description="Document ID to validate")
    validation_type: str = Field("automated", description="Type of validation")
    reviewer_id: Optional[str] = Field(None, description="Human reviewer ID")
    validation_rules: Optional[Dict[str, Any]] = Field(
        None, description="Custom validation rules"
    )


class DocumentValidationResponse(BaseModel):
    """Document validation response model."""

    document_id: str = Field(..., description="Document ID")
    validation_status: str = Field(..., description="Validation status")
    quality_score: QualityScore = Field(..., description="Updated quality score")
    validation_notes: Optional[str] = Field(None, description="Validation notes")
    validated_by: str = Field(..., description="Who performed the validation")
    validation_timestamp: datetime = Field(
        default_factory=datetime.now, description="Validation timestamp"
    )
