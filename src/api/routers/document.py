"""
Document Processing API Router
Provides endpoints for document upload, processing, status, and results
"""

import logging
import base64
import re
from typing import Dict, Any, List, Optional, Union
from fastapi import (
    APIRouter,
    HTTPException,
    UploadFile,
    File,
    Form,
    Depends,
    BackgroundTasks,
)
from fastapi.responses import JSONResponse
import uuid
from datetime import datetime
import os
from pathlib import Path
import asyncio

from src.api.agents.document.models.document_models import (
    DocumentUploadResponse,
    DocumentProcessingResponse,
    DocumentResultsResponse,
    DocumentSearchRequest,
    DocumentSearchResponse,
    DocumentValidationRequest,
    DocumentValidationResponse,
    DocumentProcessingError,
    ProcessingStage,
)
from src.api.agents.document.mcp_document_agent import get_mcp_document_agent
from src.api.agents.document.action_tools import DocumentActionTools

logger = logging.getLogger(__name__)


def _sanitize_log_data(data: Union[str, Any], max_length: int = 500) -> str:
    """
    Sanitize data for safe logging to prevent log injection attacks.
    
    Removes newlines, carriage returns, and other control characters that could
    be used to forge log entries. For suspicious data, uses base64 encoding.
    
    Args:
        data: Data to sanitize (will be converted to string)
        max_length: Maximum length of sanitized string (truncates if longer)
        
    Returns:
        Sanitized string safe for logging
    """
    if data is None:
        return "None"
    
    # Convert to string
    data_str = str(data)
    
    # Truncate if too long
    if len(data_str) > max_length:
        data_str = data_str[:max_length] + "...[truncated]"
    
    # Check for newlines, carriage returns, or other control characters
    # \x00-\x1f covers all control characters including \r (0x0D), \n (0x0A), and \t (0x09)
    if re.search(r'[\x00-\x1f]', data_str):
        # Contains control characters - base64 encode for safety
        try:
            encoded = base64.b64encode(data_str.encode('utf-8')).decode('ascii')
            return f"[base64:{encoded}]"
        except Exception:
            # If encoding fails, remove control characters
            data_str = re.sub(r'[\x00-\x1f]', '', data_str)
    
    # Remove any remaining suspicious characters
    data_str = re.sub(r'[\r\n]', '', data_str)
    
    return data_str


def _parse_json_form_data(json_str: Optional[str], default: Any = None) -> Any:
    """
    Parse JSON string from form data with error handling.
    
    Args:
        json_str: JSON string to parse
        default: Default value if parsing fails
        
    Returns:
        Parsed JSON object or default value
    """
    if not json_str:
        return default
    
    try:
        import json
        return json.loads(json_str)
    except json.JSONDecodeError:
        logger.warning(f"Invalid JSON in form data: {_sanitize_log_data(json_str)}")
        return default


def _handle_endpoint_error(operation: str, error: Exception) -> HTTPException:
    """
    Create standardized HTTPException for endpoint errors.
    
    Args:
        operation: Description of the operation that failed
        error: Exception that occurred
        
    Returns:
        HTTPException with appropriate status code and message
    """
    logger.error(f"{operation} failed: {_sanitize_log_data(str(error))}")
    return HTTPException(status_code=500, detail=f"{operation} failed: {str(error)}")


def _check_result_success(result: Dict[str, Any], operation: str) -> None:
    """
    Check if result indicates success, raise HTTPException if not.
    
    Args:
        result: Result dictionary with 'success' key
        operation: Description of operation for error message
        
    Raises:
        HTTPException: If result indicates failure
    """
    if not result.get("success"):
        status_code = 404 if "not found" in result.get("message", "").lower() else 500
        raise HTTPException(status_code=status_code, detail=result.get("message", f"{operation} failed"))


async def _update_stage_completion(
    tools: DocumentActionTools,
    document_id: str,
    stage_name: str,
    current_stage: str,
    progress: int,
) -> None:
    """
    Update document status after stage completion.
    
    Args:
        tools: Document action tools instance
        document_id: Document ID
        stage_name: Name of the completed stage (e.g., "preprocessing")
        current_stage: Name of the next stage
        progress: Progress percentage
    """
    if document_id in tools.document_statuses:
        tools.document_statuses[document_id]["current_stage"] = current_stage
        tools.document_statuses[document_id]["progress"] = progress
        if "stages" in tools.document_statuses[document_id]:
            for stage in tools.document_statuses[document_id]["stages"]:
                if stage["name"] == stage_name:
                    stage["status"] = "completed"
                    stage["completed_at"] = datetime.now().isoformat()
        tools._save_status_data()


async def _handle_stage_error(
    tools: DocumentActionTools,
    document_id: str,
    stage_name: str,
    error: Exception,
) -> None:
    """
    Handle error during document processing stage.
    
    Args:
        tools: Document action tools instance
        document_id: Document ID
        stage_name: Name of the stage that failed
        error: Exception that occurred
    """
    error_msg = f"{stage_name} failed: {str(error)}"
    logger.error(f"{stage_name} failed for {_sanitize_log_data(document_id)}: {_sanitize_log_data(str(error))}")
    await tools._update_document_status(document_id, "failed", error_msg)

# Create router
router = APIRouter(prefix="/api/v1/document", tags=["document"])


# Global document tools instance - use a class-based singleton
class DocumentToolsSingleton:
    _instance: Optional[DocumentActionTools] = None
    _initialized: bool = False

    @classmethod
    async def get_instance(cls) -> DocumentActionTools:
        """Get or create document action tools instance."""
        if cls._instance is None or not cls._initialized:
            logger.info("Creating new DocumentActionTools instance")
            cls._instance = DocumentActionTools()
            await cls._instance.initialize()
            cls._initialized = True
            logger.info(
                f"DocumentActionTools initialized with {len(cls._instance.document_statuses)} documents"
            )  # Safe: len() returns int, not user input
        else:
            logger.info(
                f"Using existing DocumentActionTools instance with {len(cls._instance.document_statuses)} documents"
            )  # Safe: len() returns int, not user input

        return cls._instance


async def get_document_tools() -> DocumentActionTools:
    """Get or create document action tools instance."""
    return await DocumentToolsSingleton.get_instance()


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    document_type: str = Form(...),
    user_id: str = Form(default="anonymous"),
    metadata: Optional[str] = Form(default=None),
    tools: DocumentActionTools = Depends(get_document_tools),
):
    """
    Upload a document for processing through the NVIDIA NeMo pipeline.

    Args:
        file: Document file to upload (PDF, PNG, JPG, JPEG, TIFF, BMP)
        document_type: Type of document (invoice, receipt, BOL, etc.)
        user_id: User ID uploading the document
        metadata: Additional metadata as JSON string
        tools: Document action tools dependency

    Returns:
        DocumentUploadResponse with document ID and processing status
    """
    try:
        logger.info(f"Document upload request: {_sanitize_log_data(file.filename)}, type: {_sanitize_log_data(document_type)}")

        # Validate file type
        allowed_extensions = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp"}
        file_extension = os.path.splitext(file.filename)[1].lower()

        if file_extension not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file_extension}. Allowed types: {', '.join(allowed_extensions)}",
            )

        # Create persistent upload directory
        document_id = str(uuid.uuid4())
        uploads_dir = Path("data/uploads")
        uploads_dir.mkdir(parents=True, exist_ok=True)
        
        # Store file in persistent location
        # Sanitize filename to prevent path traversal
        safe_filename = os.path.basename(file.filename).replace("..", "").replace("/", "_").replace("\\", "_")
        persistent_file_path = uploads_dir / f"{document_id}_{safe_filename}"

        # Save uploaded file to persistent location
        with open(str(persistent_file_path), "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        logger.info(f"Document saved to persistent storage: {_sanitize_log_data(str(persistent_file_path))}")

        # Parse metadata
        parsed_metadata = _parse_json_form_data(metadata, {})

        # Start document processing
        result = await tools.upload_document(
            file_path=str(persistent_file_path),
            document_type=document_type,
            document_id=document_id,  # Pass the document ID from router
        )

        logger.info(f"Upload result: {_sanitize_log_data(str(result))}")

        _check_result_success(result, "Document upload")

        # Schedule background processing
        background_tasks.add_task(
            process_document_background,
            document_id,
            str(persistent_file_path),
            document_type,
            user_id,
            parsed_metadata,
        )

        return DocumentUploadResponse(
            document_id=document_id,
            status="uploaded",
            message="Document uploaded successfully and processing started",
            estimated_processing_time=60,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise _handle_endpoint_error("Document upload", e)


@router.get("/status/{document_id}", response_model=DocumentProcessingResponse)
async def get_document_status(
    document_id: str, tools: DocumentActionTools = Depends(get_document_tools)
):
    """
    Get the processing status of a document.

    Args:
        document_id: Document ID to check status for
        tools: Document action tools dependency

    Returns:
        DocumentProcessingResponse with current status and progress
    """
    try:
        logger.info(f"Getting status for document: {_sanitize_log_data(document_id)}")

        result = await tools.get_document_status(document_id)
        _check_result_success(result, "Status check")

        # Convert ProcessingStage enum to string for frontend compatibility
        status_value = result["status"]
        if hasattr(status_value, "value"):
            status_value = status_value.value
        elif not isinstance(status_value, str):
            status_value = str(status_value)
        
        response_data = {
            "document_id": document_id,
            "status": status_value,
            "progress": result["progress"],
            "current_stage": result["current_stage"],
            "stages": [
                {
                    "stage_name": stage["name"].lower().replace(" ", "_"),
                    "status": stage["status"] if isinstance(stage["status"], str) else str(stage["status"]),
                    "started_at": stage.get("started_at"),
                    "completed_at": stage.get("completed_at"),
                    "processing_time_ms": stage.get("processing_time_ms"),
                    "error_message": stage.get("error_message"),
                    "metadata": stage.get("metadata", {}),
                }
                for stage in result["stages"]
            ],
            "estimated_completion": (
                datetime.fromtimestamp(result.get("estimated_completion", 0))
                if result.get("estimated_completion")
                else None
            ),
        }
        
        # Add error_message to response if status is failed
        if status_value == "failed" and result.get("error_message"):
            response_data["error_message"] = result["error_message"]
        
        return DocumentProcessingResponse(**response_data)

    except HTTPException:
        raise
    except Exception as e:
        raise _handle_endpoint_error("Status check", e)


@router.get("/results/{document_id}", response_model=DocumentResultsResponse)
async def get_document_results(
    document_id: str, tools: DocumentActionTools = Depends(get_document_tools)
):
    """
    Get the extraction results for a processed document.

    Args:
        document_id: Document ID to get results for
        tools: Document action tools dependency

    Returns:
        DocumentResultsResponse with extraction results and quality scores
    """
    try:
        logger.info(f"Getting results for document: {_sanitize_log_data(document_id)}")

        result = await tools.extract_document_data(document_id)
        _check_result_success(result, "Results retrieval")

        # Get actual filename from document status if available
        doc_status = await tools.get_document_status(document_id)
        filename = f"document_{document_id}.pdf"  # Default
        document_type = "invoice"  # Default
        
        if doc_status.get("success"):
            # Try to get filename from status tracking
            if hasattr(tools, 'document_statuses') and document_id in tools.document_statuses:
                status_info = tools.document_statuses[document_id]
                filename = status_info.get("filename", filename)
                document_type = status_info.get("document_type", document_type)
        
        return DocumentResultsResponse(
            document_id=document_id,
            filename=filename,
            document_type=document_type,
            extraction_results=result["extracted_data"],
            quality_score=result.get("quality_score"),
            routing_decision=result.get("routing_decision"),
            search_metadata=None,
            processing_summary={
                "total_processing_time": result.get("processing_time_ms", 0),
                "stages_completed": result.get("stages", []),
                "confidence_scores": result.get("confidence_scores", {}),
                "is_mock_data": result.get("is_mock", False),  # Indicate if this is mock data
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        raise _handle_endpoint_error("Results retrieval", e)


@router.post("/search", response_model=DocumentSearchResponse)
async def search_documents(
    request: DocumentSearchRequest,
    tools: DocumentActionTools = Depends(get_document_tools),
):
    """
    Search processed documents by content or metadata.

    Args:
        request: Search request with query and filters
        tools: Document action tools dependency

    Returns:
        DocumentSearchResponse with matching documents
    """
    try:
        logger.info(f"Searching documents with query: {_sanitize_log_data(request.query)}")

        result = await tools.search_documents(
            search_query=request.query, filters=request.filters or {}
        )
        _check_result_success(result, "Document search")

        return DocumentSearchResponse(
            results=result["results"],
            total_count=result["total_count"],
            query=request.query,
            search_time_ms=result["search_time_ms"],
        )

    except HTTPException:
        raise
    except Exception as e:
        raise _handle_endpoint_error("Document search", e)


@router.post("/validate/{document_id}", response_model=DocumentValidationResponse)
async def validate_document(
    document_id: str,
    request: DocumentValidationRequest,
    tools: DocumentActionTools = Depends(get_document_tools),
):
    """
    Validate document extraction quality and accuracy.

    Args:
        document_id: Document ID to validate
        request: Validation request with type and rules
        tools: Document action tools dependency

    Returns:
        DocumentValidationResponse with validation results
    """
    try:
        logger.info(f"Validating document: {_sanitize_log_data(document_id)}")

        result = await tools.validate_document_quality(
            document_id=document_id, validation_type=request.validation_type
        )
        _check_result_success(result, "Document validation")

        return DocumentValidationResponse(
            document_id=document_id,
            validation_status="completed",
            quality_score=result["quality_score"],
            validation_notes=(
                request.validation_rules.get("notes")
                if request.validation_rules
                else None
            ),
            validated_by=request.reviewer_id or "system",
            validation_timestamp=datetime.now(),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise _handle_endpoint_error("Document validation", e)


@router.get("/analytics")
async def get_document_analytics(
    time_range: str = "week",
    metrics: Optional[List[str]] = None,
    tools: DocumentActionTools = Depends(get_document_tools),
):
    """
    Get analytics and metrics for document processing.

    Args:
        time_range: Time range for analytics (today, week, month)
        metrics: Specific metrics to retrieve
        tools: Document action tools dependency

    Returns:
        Analytics data with metrics and trends
    """
    try:
        logger.info(f"Getting document analytics for time range: {time_range}")

        result = await tools.get_document_analytics(
            time_range=time_range, metrics=metrics or []
        )
        _check_result_success(result, "Analytics retrieval")

        return {
            "time_range": time_range,
            "metrics": result["metrics"],
            "trends": result["trends"],
            "summary": result["summary"],
            "generated_at": datetime.now(),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise _handle_endpoint_error("Analytics retrieval", e)


@router.post("/approve/{document_id}")
async def approve_document(
    document_id: str,
    approver_id: str = Form(...),
    approval_notes: Optional[str] = Form(default=None),
    tools: DocumentActionTools = Depends(get_document_tools),
):
    """
    Approve document for WMS integration.

    Args:
        document_id: Document ID to approve
        approver_id: User ID of approver
        approval_notes: Approval notes
        tools: Document action tools dependency

    Returns:
        Approval confirmation
    """
    try:
        logger.info(f"Approving document: {_sanitize_log_data(document_id)}")

        result = await tools.approve_document(
            document_id=document_id,
            approver_id=approver_id,
            approval_notes=approval_notes,
        )
        _check_result_success(result, "Document approval")

        return {
            "document_id": document_id,
            "approval_status": "approved",
            "approver_id": approver_id,
            "approval_timestamp": datetime.now(),
            "approval_notes": approval_notes,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise _handle_endpoint_error("Document approval", e)


@router.post("/reject/{document_id}")
async def reject_document(
    document_id: str,
    rejector_id: str = Form(...),
    rejection_reason: str = Form(...),
    suggestions: Optional[str] = Form(default=None),
    tools: DocumentActionTools = Depends(get_document_tools),
):
    """
    Reject document and provide feedback.

    Args:
        document_id: Document ID to reject
        rejector_id: User ID of rejector
        rejection_reason: Reason for rejection
        suggestions: Suggestions for improvement
        tools: Document action tools dependency

    Returns:
        Rejection confirmation
    """
    try:
        logger.info(f"Rejecting document: {_sanitize_log_data(document_id)}")

        suggestions_list = _parse_json_form_data(suggestions, [])
        if suggestions and not suggestions_list:
            # If parsing failed, treat as single string
            suggestions_list = [suggestions]

        result = await tools.reject_document(
            document_id=document_id,
            rejector_id=rejector_id,
            rejection_reason=rejection_reason,
            suggestions=suggestions_list,
        )
        _check_result_success(result, "Document rejection")

        return {
            "document_id": document_id,
            "rejection_status": "rejected",
            "rejector_id": rejector_id,
            "rejection_reason": rejection_reason,
            "suggestions": suggestions_list,
            "rejection_timestamp": datetime.now(),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise _handle_endpoint_error("Document rejection", e)


async def process_document_background(
    document_id: str,
    file_path: str,
    document_type: str,
    user_id: str,
    metadata: Dict[str, Any],
):
    """Background task for document processing using NVIDIA NeMo pipeline."""
    try:
        logger.info(
            f"🚀 Starting NVIDIA NeMo processing pipeline for document: {_sanitize_log_data(document_id)}"
        )
        logger.info(f"   File path: {_sanitize_log_data(file_path)}")
        logger.info(f"   Document type: {_sanitize_log_data(document_type)}")
        
        # Verify file exists
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        logger.info(f"✅ File exists: {file_path} ({os.path.getsize(file_path)} bytes)")

        # Import the actual pipeline components
        from src.api.agents.document.preprocessing.nemo_retriever import (
            NeMoRetrieverPreprocessor,
        )
        from src.api.agents.document.ocr.nemo_ocr import NeMoOCRService
        from src.api.agents.document.processing.small_llm_processor import (
            SmallLLMProcessor,
        )
        from src.api.agents.document.validation.large_llm_judge import (
            LargeLLMJudge,
        )
        from src.api.agents.document.routing.intelligent_router import (
            IntelligentRouter,
        )

        # Initialize pipeline components
        preprocessor = NeMoRetrieverPreprocessor()
        ocr_processor = NeMoOCRService()
        llm_processor = SmallLLMProcessor()
        judge = LargeLLMJudge()
        router = IntelligentRouter()

        # Get tools instance for status updates
        tools = await get_document_tools()
        
        # Update status to PROCESSING (use PREPROCESSING as PROCESSING doesn't exist in enum)
        if document_id in tools.document_statuses:
            tools.document_statuses[document_id]["status"] = ProcessingStage.PREPROCESSING
            tools.document_statuses[document_id]["current_stage"] = "Preprocessing"
            tools.document_statuses[document_id]["progress"] = 10
            tools._save_status_data()
            logger.info(f"✅ Updated document {_sanitize_log_data(document_id)} status to PREPROCESSING (10% progress)")
        
        # Stage 1: Document Preprocessing
        logger.info(f"Stage 1: Document preprocessing for {_sanitize_log_data(document_id)}")
        try:
            preprocessing_result = await preprocessor.process_document(file_path)
            # Update status after preprocessing
            await _update_stage_completion(tools, document_id, "preprocessing", "OCR Extraction", 20)
        except Exception as e:
            await _handle_stage_error(tools, document_id, "Preprocessing", e)
            raise

        # Stage 2: OCR Extraction
        logger.info(f"Stage 2: OCR extraction for {_sanitize_log_data(document_id)}")
        try:
            ocr_result = await ocr_processor.extract_text(
                preprocessing_result.get("images", []),
                preprocessing_result.get("metadata", {}),
            )
            # Update status after OCR
            await _update_stage_completion(tools, document_id, "ocr_extraction", "LLM Processing", 40)
        except Exception as e:
            await _handle_stage_error(tools, document_id, "OCR extraction", e)
            raise

        # Stage 3: Small LLM Processing
        logger.info(f"Stage 3: Small LLM processing for {_sanitize_log_data(document_id)}")
        try:
            llm_result = await llm_processor.process_document(
                preprocessing_result.get("images", []),
                ocr_result.get("text", ""),
                document_type,
            )
            # Update status after LLM processing
            await _update_stage_completion(tools, document_id, "llm_processing", "Validation", 60)
        except Exception as e:
            await _handle_stage_error(tools, document_id, "LLM processing", e)
            raise

        # Stage 4: Large LLM Judge & Validation
        logger.info(f"Stage 4: Large LLM judge validation for {_sanitize_log_data(document_id)}")
        try:
            validation_result = await judge.evaluate_document(
                llm_result.get("structured_data", {}),
                llm_result.get("entities", {}),
                document_type,
            )
            # Update status after validation
            await _update_stage_completion(tools, document_id, "validation", "Routing", 80)
        except Exception as e:
            await _handle_stage_error(tools, document_id, "Validation", e)
            raise

        # Stage 5: Intelligent Routing
        logger.info(f"Stage 5: Intelligent routing for {_sanitize_log_data(document_id)}")
        try:
            routing_result = await router.route_document(
                llm_result, validation_result, document_type
            )
            # Update status after routing
            await _update_stage_completion(tools, document_id, "routing", "Finalizing", 90)
        except Exception as e:
            await _handle_stage_error(tools, document_id, "Routing", e)
            raise

        # Store results in the document tools
        # Include OCR text in LLM result for fallback parsing
        if "structured_data" in llm_result and ocr_result.get("text"):
            # Ensure OCR text is available for fallback parsing if LLM extraction fails
            if not llm_result["structured_data"].get("extracted_fields"):
                logger.info(f"LLM returned empty extracted_fields, OCR text available for fallback: {len(ocr_result.get('text', ''))} chars")
            llm_result["ocr_text"] = ocr_result.get("text", "")
        
        # Store processing results (this will also set status to COMPLETED)
        await tools._store_processing_results(
            document_id=document_id,
            preprocessing_result=preprocessing_result,
            ocr_result=ocr_result,
            llm_result=llm_result,
            validation_result=validation_result,
            routing_result=routing_result,
        )

        logger.info(
            f"NVIDIA NeMo processing pipeline completed for document: {_sanitize_log_data(document_id)}"
        )

        # Only delete file after successful processing and results storage
        # Keep file for potential re-processing or debugging
        # Files can be cleaned up later via a cleanup job if needed
        logger.info(f"Document file preserved at: {_sanitize_log_data(file_path)} (for re-processing if needed)")

    except Exception as e:
        error_message = f"{type(e).__name__}: {str(e)}"
        logger.error(
            f"NVIDIA NeMo processing failed for document {_sanitize_log_data(document_id)}: {_sanitize_log_data(error_message)}",
            exc_info=True,
        )
        # Update status to failed with detailed error message
        try:
            tools = await get_document_tools()
            await tools._update_document_status(document_id, "failed", error_message)
        except Exception as status_error:
            logger.error(f"Failed to update document status: {_sanitize_log_data(str(status_error))}", exc_info=True)


@router.get("/health")
async def document_health_check():
    """Health check endpoint for document processing service."""
    return {
        "status": "healthy",
        "service": "document_processing",
        "timestamp": datetime.now(),
        "version": "1.0.0",
    }
