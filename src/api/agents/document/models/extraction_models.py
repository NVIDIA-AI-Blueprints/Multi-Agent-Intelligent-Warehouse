"""
Extraction Result Models for Document Processing
Pydantic models for extraction results and processing data.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from enum import Enum


class ExtractionStatus(str, Enum):
    """Status of extraction process."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class ElementType(str, Enum):
    """Type of document element."""

    TITLE = "title"
    HEADER = "header"
    BODY = "body"
    FOOTER = "footer"
    TABLE = "table"
    IMAGE = "image"
    SIGNATURE = "signature"
    LOGO = "logo"
    TEXT = "text"
    UNKNOWN = "unknown"


class ConfidenceLevel(str, Enum):
    """Confidence level for extractions."""

    VERY_HIGH = "very_high"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    VERY_LOW = "very_low"


class BoundingBox(BaseModel):
    """Bounding box coordinates."""

    x1: float = Field(..., description="Left coordinate")
    y1: float = Field(..., description="Top coordinate")
    x2: float = Field(..., description="Right coordinate")
    y2: float = Field(..., description="Bottom coordinate")

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1

    @property
    def area(self) -> float:
        return self.width * self.height


class DocumentElement(BaseModel):
    """A detected document element."""

    element_id: str = Field(..., description="Unique element identifier")
    element_type: ElementType = Field(..., description="Type of element")
    text: str = Field(..., description="Extracted text content")
    bounding_box: BoundingBox = Field(..., description="Element position")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Extraction confidence")
    reading_order: int = Field(..., description="Reading order index")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class OCRResult(BaseModel):
    """OCR extraction result."""

    page_number: int = Field(..., description="Page number")
    text: str = Field(..., description="Extracted text")
    words: List[Dict[str, Any]] = Field(
        default_factory=list, description="Word-level data"
    )
    elements: List[DocumentElement] = Field(
        default_factory=list, description="Document elements"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Overall OCR confidence")
    image_dimensions: tuple = Field(..., description="Image dimensions (width, height)")
    processing_time_ms: int = Field(..., description="Processing time in milliseconds")


class EntityExtraction(BaseModel):
    """Entity extraction result."""

    entity_name: str = Field(..., description="Name of the entity")
    entity_value: str = Field(..., description="Extracted value")
    entity_type: str = Field(..., description="Type of entity")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Extraction confidence")
    source: str = Field(..., description="Source of extraction")
    normalized_value: Optional[str] = Field(None, description="Normalized value")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Entity metadata"
    )


class LineItem(BaseModel):
    """Line item from document."""

    item_id: str = Field(..., description="Unique item identifier")
    description: str = Field(..., description="Item description")
    quantity: float = Field(..., description="Quantity")
    unit_price: float = Field(..., description="Unit price")
    total: float = Field(..., description="Total price")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Extraction confidence")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Item metadata")


class QualityAssessment(BaseModel):
    """Quality assessment result."""

    overall_score: float = Field(
        ..., ge=1.0, le=5.0, description="Overall quality score"
    )
    completeness_score: float = Field(
        ..., ge=1.0, le=5.0, description="Completeness score"
    )
    accuracy_score: float = Field(..., ge=1.0, le=5.0, description="Accuracy score")
    consistency_score: float = Field(
        ..., ge=1.0, le=5.0, description="Consistency score"
    )
    readability_score: float = Field(
        ..., ge=1.0, le=5.0, description="Readability score"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Assessment confidence")
    feedback: str = Field(..., description="Quality feedback")
    recommendations: List[str] = Field(
        default_factory=list, description="Improvement recommendations"
    )


class JudgeEvaluation(BaseModel):
    """Judge evaluation result."""

    overall_score: float = Field(
        ..., ge=1.0, le=5.0, description="Overall evaluation score"
    )
    decision: str = Field(..., description="Judge decision")
    completeness: Dict[str, Any] = Field(
        default_factory=dict, description="Completeness assessment"
    )
    accuracy: Dict[str, Any] = Field(
        default_factory=dict, description="Accuracy assessment"
    )
    compliance: Dict[str, Any] = Field(
        default_factory=dict, description="Compliance assessment"
    )
    quality: Dict[str, Any] = Field(
        default_factory=dict, description="Quality assessment"
    )
    issues_found: List[str] = Field(
        default_factory=list, description="Issues identified"
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Evaluation confidence")
    reasoning: str = Field(..., description="Judge reasoning")


class RoutingDecision(BaseModel):
    """Routing decision result."""

    action: str = Field(..., description="Routing action")
    reason: str = Field(..., description="Routing reason")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Decision confidence")
    next_steps: List[str] = Field(default_factory=list, description="Next steps")
    estimated_processing_time: Optional[str] = Field(
        None, description="Estimated processing time"
    )
    requires_human_review: bool = Field(
        ..., description="Whether human review is required"
    )
    priority: str = Field(..., description="Processing priority")


class ProcessingStageResult(BaseModel):
    """Result from a processing stage."""

    stage: str = Field(..., description="Processing stage name")
    status: ExtractionStatus = Field(..., description="Stage status")
    start_time: datetime = Field(..., description="Stage start time")
    end_time: Optional[datetime] = Field(None, description="Stage end time")
    processing_time_ms: int = Field(..., description="Processing time in milliseconds")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Stage confidence")
    result_data: Dict[str, Any] = Field(
        default_factory=dict, description="Stage result data"
    )
    errors: List[str] = Field(default_factory=list, description="Stage errors")


class DocumentProcessingResult(BaseModel):
    """Complete document processing result."""

    document_id: str = Field(..., description="Document identifier")
    status: ExtractionStatus = Field(..., description="Processing status")
    stages_completed: List[str] = Field(
        default_factory=list, description="Completed stages"
    )
    extracted_data: Dict[str, Any] = Field(
        default_factory=dict, description="Extracted data"
    )
    quality_scores: Dict[str, float] = Field(
        default_factory=dict, description="Quality scores"
    )
    routing_decision: RoutingDecision = Field(..., description="Routing decision")
    processing_time_ms: int = Field(..., description="Total processing time")
    errors: List[str] = Field(default_factory=list, description="Processing errors")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Overall confidence")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Processing metadata"
    )


class EmbeddingResult(BaseModel):
    """Embedding generation result."""

    document_id: str = Field(..., description="Document identifier")
    embeddings: List[List[float]] = Field(..., description="Generated embeddings")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Embedding metadata"
    )
    storage_successful: bool = Field(..., description="Whether storage was successful")
    processing_time_ms: int = Field(..., description="Processing time in milliseconds")


class SemanticSearchResult(BaseModel):
    """Semantic search result."""

    query: str = Field(..., description="Search query")
    results: List[Dict[str, Any]] = Field(
        default_factory=list, description="Search results"
    )
    total_results: int = Field(..., description="Total number of results")
    processing_time_ms: int = Field(..., description="Search time in milliseconds")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Search confidence")


class WorkflowProgress(BaseModel):
    """Workflow progress information."""

    workflow_id: str = Field(..., description="Workflow identifier")
    document_id: str = Field(..., description="Document identifier")
    current_stage: str = Field(..., description="Current processing stage")
    status: str = Field(..., description="Workflow status")
    progress_percentage: float = Field(
        ..., ge=0.0, le=100.0, description="Progress percentage"
    )
    stages_completed: List[str] = Field(
        default_factory=list, description="Completed stages"
    )
    stages_pending: List[str] = Field(
        default_factory=list, description="Pending stages"
    )
    start_time: datetime = Field(..., description="Workflow start time")
    last_updated: datetime = Field(..., description="Last update time")
    estimated_completion: Optional[str] = Field(
        None, description="Estimated completion time"
    )
    errors: List[str] = Field(default_factory=list, description="Workflow errors")


class ProcessingStatistics(BaseModel):
    """Processing statistics."""

    total_documents_processed: int = Field(..., description="Total documents processed")
    successful_processes: int = Field(..., description="Successful processes")
    failed_processes: int = Field(..., description="Failed processes")
    average_processing_time_ms: float = Field(
        ..., description="Average processing time"
    )
    success_rate_percentage: float = Field(
        ..., ge=0.0, le=100.0, description="Success rate"
    )
    average_quality_score: float = Field(
        ..., ge=1.0, le=5.0, description="Average quality score"
    )
    last_updated: datetime = Field(..., description="Last statistics update")
