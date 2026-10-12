# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Document Processing API Router
Provides endpoints for document upload, processing, status, and results
"""

import logging
from functools import wraps
from typing import Dict, Any, List, Optional, Union, Callable, TypeVar
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

T = TypeVar('T')

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
from src.api.agents.document.action_tools import DocumentActionTools
from src.api.utils.log_utils import sanitize_log_data

logger = logging.getLogger(__name__)

# Alias for backward compatibility
_sanitize_log_data = sanitize_log_data


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
    from src.api.utils.error_handler import sanitize_error_message
    error_msg = sanitize_error_message(error, operation)
    return HTTPException(status_code=500, detail=error_msg)


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


def _handle_endpoint_errors(operation: str) -> Callable:
    """
    Decorator to handle endpoint errors consistently.
    
    Args:
        operation: Description of the operation for error messages
        
    Returns:
        Decorated function with error handling
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                raise
            except Exception as e:
                raise _handle_endpoint_error(operation, e)
        return wrapper
    return decorator


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
    # Update database if available
    if tools.use_database and tools.db_service:
        try:
            await tools.db_service.update_processing_stage(
                document_id=document_id,
                stage_name=stage_name,
                status="completed",
            )
            await tools.db_service.update_document_status(
                document_id=document_id,
                status=stage_name,
                processing_stage=stage_name,
            )
        except Exception as db_error:
            logger.warning(f"Failed to update stage completion in database: {db_error}")
    
    # Fallback: update in-memory status
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
    from src.api.utils.error_handler import sanitize_error_message
    from src.api.agents.document.model_gateway_adapter import (
        DocumentInferenceUnavailable,
    )

    if isinstance(error, DocumentInferenceUnavailable):
        # Typed, non-secret failure code is always surfaced (v2.0.1, P1-05):
        # the operator must see *why* no result exists, and it must never be
        # mistaken for a quality decision.
        error_msg = (
            f"{stage_name} failed: {error.code} — model inference unavailable "
            f"through ModelGateway (modality={error.modality})"
        )
    else:
        error_msg = sanitize_error_message(error, stage_name)
    logger.error(f"{stage_name} failed for {_sanitize_log_data(document_id)}: {_sanitize_log_data(str(error))}")
    await tools._update_document_status(document_id, "failed", error_msg)


def _convert_status_enum_to_string(status_value: Any) -> str:
    """
    Convert ProcessingStage enum to string for frontend compatibility.
    
    Args:
        status_value: Status value (enum, string, or other)
        
    Returns:
        String representation of status
    """
    if hasattr(status_value, "value"):
        return status_value.value
    elif isinstance(status_value, str):
        return status_value
    else:
        return str(status_value)


def _extract_document_metadata(
    tools: DocumentActionTools,
    document_id: str,
) -> tuple:
    """
    Extract filename and document_type from document status.
    
    Args:
        tools: Document action tools instance
        document_id: Document ID
        
    Returns:
        Tuple of (filename, document_type)
    """
    default_filename = f"document_{document_id}.pdf"
    default_document_type = "invoice"
    
    if hasattr(tools, 'document_statuses') and document_id in tools.document_statuses:
        status_info = tools.document_statuses[document_id]
        filename = status_info.get("filename", default_filename)
        document_type = status_info.get("document_type", default_document_type)
        return filename, document_type
    
    return default_filename, default_document_type


async def _execute_processing_stage(
    tools: DocumentActionTools,
    document_id: str,
    stage_number: int,
    stage_name: str,
    next_stage: str,
    progress: int,
    processor_func: callable,
    *args,
    **kwargs,
) -> Any:
    """
    Execute a processing stage with standardized error handling, retry logic, and status updates.
    
    Args:
        tools: Document action tools instance
        document_id: Document ID
        stage_number: Stage number (1-5)
        stage_name: Name of the stage (e.g., "preprocessing")
        next_stage: Name of the next stage
        progress: Progress percentage after this stage
        processor_func: Async function to execute for this stage
        *args: Positional arguments for processor_func
        **kwargs: Keyword arguments for processor_func
        
    Returns:
        Result from processor_func
        
    Raises:
        Exception: Re-raises any exception from processor_func after handling
    """
    logger.info(f"Stage {stage_number}: {stage_name} for {_sanitize_log_data(document_id)}")
    
    # Update stage status to processing in database
    if tools.use_database and tools.db_service:
        try:
            await tools.db_service.update_processing_stage(
                document_id=document_id,
                stage_name=stage_name,
                status="processing",
            )
        except Exception as db_error:
            logger.warning(f"Failed to update stage status in database: {db_error}")
    
    # Execute with retry logic
    from src.api.services.document import retry_with_backoff, RetryConfig
    
    retry_config = RetryConfig(
        max_retries=3,
        initial_delay=1.0,
        max_delay=30.0,
        exponential_base=2.0,
    )
    
    try:
        result = await retry_with_backoff(
            processor_func,
            *args,
            config=retry_config,
            **kwargs,
        )
        await _update_stage_completion(tools, document_id, stage_name, next_stage, progress)
        return result
    except Exception as e:
        await _handle_stage_error(tools, document_id, stage_name, e)
        raise

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

        # Schedule background processing via job queue
        try:
            from src.api.services.document import get_job_queue
            
            job_queue = await get_job_queue()
            job_id = await job_queue.enqueue_job(
                job_type="process_document",
                job_data={
                    "document_id": document_id,
                    "file_path": str(persistent_file_path),
                    "document_type": document_type,
                    "user_id": user_id,
                    "metadata": parsed_metadata,
                },
                priority=0,
                max_retries=3,
            )
            logger.info(f"Enqueued document processing job: {job_id} for document: {document_id}")
            
            # Also add as background task for immediate processing (fallback if job queue fails)
            background_tasks.add_task(
                process_document_background,
                document_id,
                str(persistent_file_path),
                document_type,
                user_id,
                parsed_metadata,
            )
        except Exception as queue_error:
            logger.warning(f"Job queue not available, using background task only: {queue_error}")
            # Fallback to background task only
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
        
        # Check if result indicates failure
        if not result.get("success", True):
            raise HTTPException(
                status_code=404 if "not found" in result.get("message", "").lower() else 500,
                detail=result.get("message", "Document status not available")
            )

        # Convert ProcessingStage enum to string for frontend compatibility
        status_value = _convert_status_enum_to_string(result.get("status", "unknown"))
        
        # Ensure stages list exists and is properly formatted
        stages_list = result.get("stages", [])
        if not isinstance(stages_list, list):
            stages_list = []
        
        # Handle estimated_completion - can be timestamp, datetime, or None
        estimated_completion = None
        est_comp = result.get("estimated_completion")
        if est_comp:
            try:
                if isinstance(est_comp, (int, float)):
                    estimated_completion = datetime.fromtimestamp(est_comp)
                elif isinstance(est_comp, datetime):
                    estimated_completion = est_comp
                elif isinstance(est_comp, str):
                    # Try parsing ISO format
                    try:
                        estimated_completion = datetime.fromisoformat(est_comp.replace('Z', '+00:00'))
                    except ValueError:
                        # Try timestamp string
                        estimated_completion = datetime.fromtimestamp(float(est_comp))
            except (ValueError, TypeError, OSError) as e:
                logger.warning(f"Failed to parse estimated_completion: {e}")
                estimated_completion = None
        
        response_data = {
            "document_id": document_id,
            "status": status_value,
            "progress": result.get("progress", 0),
            "current_stage": result.get("current_stage", "Unknown"),
            "stages": [
                {
                    "stage_name": (
                        stage.get("name", "").lower().replace(" ", "_") 
                        if isinstance(stage, dict) 
                        else str(stage).lower().replace(" ", "_")
                    ),
                    "status": (
                        str(stage.get("status", "pending")) 
                        if isinstance(stage, dict) 
                        else str(stage.get("status", "pending") if hasattr(stage, "get") else "pending")
                    ),
                    "started_at": stage.get("started_at") if isinstance(stage, dict) else None,
                    "completed_at": stage.get("completed_at") if isinstance(stage, dict) else None,
                    "processing_time_ms": stage.get("processing_time_ms") if isinstance(stage, dict) else None,
                    "error_message": stage.get("error_message") if isinstance(stage, dict) else None,
                    "metadata": stage.get("metadata", {}) if isinstance(stage, dict) else {},
                }
                for stage in stages_list
            ],
            "estimated_completion": estimated_completion,
        }
        
        # Add error_message to response if status is failed
        if status_value == "failed" and result.get("error_message"):
            response_data["error_message"] = result["error_message"]
        
        return DocumentProcessingResponse(**response_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_document_status endpoint: {e}", exc_info=True)
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
        filename, document_type = _extract_document_metadata(tools, document_id)
        
        # Ensure extraction_results is a list
        extraction_results = result.get("extracted_data", [])
        if not isinstance(extraction_results, list):
            # Convert dictionary to list if needed
            if isinstance(extraction_results, dict):
                from src.api.agents.document.models.document_models import ExtractionResult
                extraction_results = [
                    ExtractionResult(
                        stage=stage_name,
                        raw_data=stage_data.get("raw_data", {}),
                        processed_data=stage_data.get("processed_data", {}),
                        confidence_score=stage_data.get("confidence_score", 0.0),
                        processing_time_ms=stage_data.get("processing_time_ms", 0),
                        model_used=stage_data.get("model_used", ""),
                        metadata=stage_data.get("metadata", {}),
                    )
                    for stage_name, stage_data in extraction_results.items()
                    if isinstance(stage_data, dict)
                ]
            else:
                extraction_results = []
        
        # Ensure quality_score is a QualityScore object if it's a dict
        quality_score = result.get("quality_score")
        
        # If quality_score is None, try to extract from validation stage in extraction_results
        if not quality_score and isinstance(extraction_results, list):
            for ext_result in extraction_results:
                if hasattr(ext_result, 'stage') and ext_result.stage == 'validation':
                    # Try to extract quality score from processed_data
                    if hasattr(ext_result, 'processed_data') and isinstance(ext_result.processed_data, dict):
                        processed_data = ext_result.processed_data
                        if 'overall_score' in processed_data or 'decision' in processed_data:
                            from src.api.agents.document.models.document_models import QualityScore, QualityDecision
                            try:
                                quality_score = QualityScore(
                                    overall_score=processed_data.get("overall_score", 0.0),
                                    completeness_score=processed_data.get("completeness_score", 0.0),
                                    accuracy_score=processed_data.get("accuracy_score", 0.0),
                                    compliance_score=processed_data.get("compliance_score", 0.0),
                                    quality_score=processed_data.get("quality_score", processed_data.get("overall_score", 0.0)),
                                    decision=QualityDecision(processed_data.get("decision", "REVIEW_REQUIRED")),
                                    reasoning=processed_data.get("reasoning", {}),
                                    issues_found=processed_data.get("issues_found", []),
                                    confidence=processed_data.get("confidence", ext_result.confidence_score if hasattr(ext_result, 'confidence_score') else 0.0),
                                    judge_model=ext_result.model_used if hasattr(ext_result, 'model_used') else "",
                                )
                                logger.info(f"Extracted quality_score from validation stage for document {document_id}")
                                break
                            except Exception as qs_error:
                                logger.warning(f"Failed to create QualityScore from validation stage: {qs_error}")
        
        if quality_score and isinstance(quality_score, dict):
            from src.api.agents.document.models.document_models import QualityScore, QualityDecision
            try:
                quality_score = QualityScore(
                    overall_score=quality_score.get("overall_score", 0.0),
                    completeness_score=quality_score.get("completeness_score", 0.0),
                    accuracy_score=quality_score.get("accuracy_score", 0.0),
                    compliance_score=quality_score.get("compliance_score", 0.0),
                    quality_score=quality_score.get("quality_score", 0.0),
                    decision=QualityDecision(quality_score.get("decision", "REVIEW_REQUIRED")),
                    reasoning=quality_score.get("reasoning", {}),
                    issues_found=quality_score.get("issues_found", []),
                    confidence=quality_score.get("confidence", 0.0),
                    judge_model=quality_score.get("judge_model", ""),
                )
            except Exception as qs_error:
                logger.warning(f"Failed to convert quality_score to QualityScore object: {qs_error}")
                quality_score = None
        
        # Ensure routing_decision is a RoutingDecision object if it's a dict
        routing_decision = result.get("routing_decision")
        
        # If routing_decision is None, try to extract from routing stage in extraction_results
        if not routing_decision and isinstance(extraction_results, list):
            for ext_result in extraction_results:
                if hasattr(ext_result, 'stage') and ext_result.stage == 'routing':
                    # Try to extract routing decision from processed_data
                    if hasattr(ext_result, 'processed_data') and isinstance(ext_result.processed_data, dict):
                        processed_data = ext_result.processed_data
                        if 'routing_action' in processed_data or 'routing_reason' in processed_data:
                            from src.api.agents.document.models.document_models import RoutingDecision, RoutingAction
                            try:
                                routing_decision = RoutingDecision(
                                    routing_action=RoutingAction(processed_data.get("routing_action", "flag_review")),
                                    routing_reason=processed_data.get("routing_reason", ""),
                                    wms_integration_status=processed_data.get("wms_integration_status", "pending"),
                                    wms_integration_data=processed_data.get("wms_integration_data", {}),
                                    human_review_required=processed_data.get("human_review_required", False),
                                )
                                logger.info(f"Extracted routing_decision from routing stage for document {document_id}")
                                break
                            except Exception as rd_error:
                                logger.warning(f"Failed to create RoutingDecision from routing stage: {rd_error}")
        
        if routing_decision and isinstance(routing_decision, dict):
            from src.api.agents.document.models.document_models import RoutingDecision, RoutingAction
            try:
                routing_decision = RoutingDecision(
                    routing_action=RoutingAction(routing_decision.get("routing_action", "flag_review")),
                    routing_reason=routing_decision.get("routing_reason", ""),
                    wms_integration_status=routing_decision.get("wms_integration_status", "pending"),
                    wms_integration_data=routing_decision.get("wms_integration_data", {}),
                    human_review_required=routing_decision.get("human_review_required", False),
                )
            except Exception as rd_error:
                logger.warning(f"Failed to convert routing_decision to RoutingDecision object: {rd_error}")
                routing_decision = None
        
        # Get extracted_fields and confidence_scores from result if available
        extracted_fields = result.get("extracted_fields", {})
        confidence_scores = result.get("confidence_scores", {})
        
        # Log what we're returning for debugging
        logger.info(f"Returning document results for {_sanitize_log_data(document_id)}:")
        logger.info(f"  - extracted_fields keys: {list(extracted_fields.keys()) if extracted_fields else 'empty'}")
        logger.info(f"  - confidence_scores keys: {list(confidence_scores.keys()) if confidence_scores else 'empty'}")
        logger.info(f"  - extraction_results stages: {[r.stage for r in extraction_results if hasattr(r, 'stage')]}")
        
        return DocumentResultsResponse(
            document_id=document_id,
            filename=filename,
            document_type=document_type,
            extraction_results=extraction_results,
            quality_score=quality_score,
            routing_decision=routing_decision,
            search_metadata=None,
            processing_summary={
                "total_processing_time": result.get("processing_time_ms", 0),
                "stages_completed": result.get("processing_stages", [r.stage for r in extraction_results if hasattr(r, "stage")]),
                "confidence_scores": confidence_scores,
                "is_mock_data": result.get("is_mock", False),  # Indicate if this is mock data
                "extracted_fields": extracted_fields,  # Include flattened extracted fields for frontend
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
    """
    Background document processing.

    v2.0.1 (audit P1-05): every model call in stages 2–4 goes through the
    canonical ModelGateway (``model_gateway_adapter``). Stage 1 is local. A
    stage whose inference cannot be served raises
    ``DocumentInferenceUnavailable`` and the document is marked FAILED with
    the typed code — no mock data, no synthetic approval.
    """
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
        preprocessing_result = await _execute_processing_stage(
            tools, document_id, 1, "preprocessing", "OCR Extraction", 20,
            preprocessor.process_document, file_path
        )

        # Stage 2: OCR Extraction
        ocr_result = await _execute_processing_stage(
            tools, document_id, 2, "ocr_extraction", "LLM Processing", 40,
            ocr_processor.extract_text,
            preprocessing_result.get("images", []),
            preprocessing_result.get("metadata", {}),
        )

        # Stage 3: Small LLM Processing
        llm_result = await _execute_processing_stage(
            tools, document_id, 3, "llm_processing", "Validation", 60,
            llm_processor.process_document,
            preprocessing_result.get("images", []),
            ocr_result.get("text", ""),
            document_type,
        )

        # Stage 4: Large LLM Judge & Validation
        # Make validation optional - if it fails, continue with default values
        validation_result = {}
        try:
            validation_result = await _execute_processing_stage(
                tools, document_id, 4, "validation", "Routing", 80,
                judge.evaluate_document,
                llm_result.get("structured_data", {}),
                llm_result.get("entities", {}),
                document_type,
            )
            logger.info(f"Validation stage completed successfully for {_sanitize_log_data(document_id)}")
        except Exception as validation_error:
            logger.warning(
                f"Validation stage failed for {_sanitize_log_data(document_id)}: {_sanitize_log_data(str(validation_error))}. "
                f"Routing to human review."
            )
            # v2.0.1 (P1-05): a failed quality classification is never an
            # approval. The document is routed to human review and the result
            # is explicitly marked as *unavailable* (not a model decision).
            validation_result = {
                "overall_score": 0.0,
                "decision": "REVIEW_REQUIRED",
                "decision_kind": "validation_unavailable",
                "validation_status": "unavailable",
                "failure_code": getattr(validation_error, "code", type(validation_error).__name__),
                "quality": {"score": 0.0},
                "accuracy": {"score": 0.0},
                "compliance": {"score": 0.0},
                "reasoning": {},
                "issues_found": ["Validation unavailable — human review required"],
                "confidence": 0.0,
            }
            # Mark validation stage as failed in database
            if tools.use_database and tools.db_service:
                try:
                    await tools.db_service.update_processing_stage(
                        document_id=document_id,
                        stage_name="validation",
                        status="failed",
                        error_message=str(validation_error)[:500],  # Limit error message length
                    )
                except Exception as db_error:
                    logger.warning(f"Failed to update validation stage status: {db_error}")

        # Stage 5: Intelligent Routing
        # Make routing optional - if it fails, continue with default values
        routing_result = {}
        try:
            routing_result = await _execute_processing_stage(
                tools, document_id, 5, "routing", "Finalizing", 90,
                router.route_document,
                llm_result, validation_result, document_type
            )
            logger.info(f"Routing stage completed successfully for {_sanitize_log_data(document_id)}")
        except Exception as routing_error:
            logger.warning(
                f"Routing stage failed for {_sanitize_log_data(document_id)}: {_sanitize_log_data(str(routing_error))}. "
                f"Continuing with default routing result."
            )
            # Create default routing result
            routing_result = {
                "routing_action": "flag_review",
                "routing_reason": "Routing stage failed or timed out",
                "wms_integration_status": "pending",
                "wms_integration_data": {},
                "human_review_required": True,
            }
            # Mark routing stage as failed in database
            if tools.use_database and tools.db_service:
                try:
                    await tools.db_service.update_processing_stage(
                        document_id=document_id,
                        stage_name="routing",
                        status="failed",
                        error_message=str(routing_error)[:500],  # Limit error message length
                    )
                except Exception as db_error:
                    logger.warning(f"Failed to update routing stage status: {db_error}")

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
        from src.api.utils.error_handler import sanitize_error_message
        from src.api.agents.document.model_gateway_adapter import (
            DocumentInferenceUnavailable,
        )

        if isinstance(e, DocumentInferenceUnavailable):
            error_message = (
                f"{e.stage} failed: {e.code} — model inference unavailable "
                f"through ModelGateway (modality={e.modality})"
            )
        else:
            error_message = sanitize_error_message(e, "NVIDIA NeMo processing")
        logger.error(
            f"NVIDIA NeMo processing failed for document {_sanitize_log_data(document_id)}: {_sanitize_log_data(str(e))}",
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
