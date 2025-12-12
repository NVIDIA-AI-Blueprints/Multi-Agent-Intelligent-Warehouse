"""
Document Action Tools for MCP Framework
Implements document processing tools for the MCP-enabled Document Extraction Agent
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
import uuid
import os
import json
from pathlib import Path

from src.api.services.llm.nim_client import get_nim_client
from src.api.agents.document.models.document_models import (
    ProcessingStage,
    QualityDecision,
    RoutingAction,
)
from src.api.utils.log_utils import sanitize_log_data

logger = logging.getLogger(__name__)

# Alias for backward compatibility
_sanitize_log_data = sanitize_log_data


class DocumentActionTools:
    """Document processing action tools for MCP framework."""
    
    # Model name constants
    MODEL_SMALL_LLM = "Llama Nemotron Nano VL 8B"
    MODEL_LARGE_JUDGE = "Llama 3.1 Nemotron 70B"
    MODEL_OCR = "NeMoRetriever-OCR-v1"

    def __init__(self):
        self.nim_client = None
        self.supported_file_types = ["pdf", "png", "jpg", "jpeg", "tiff", "bmp"]
        self.max_file_size = 50 * 1024 * 1024  # 50MB
        self.document_statuses = {}  # Track document processing status
        self.status_file = Path("document_statuses.json")  # Persistent storage

    def _get_value(self, obj, key: str, default=None):
        """Get value from object (dict or object with attributes)."""
        if hasattr(obj, key):
            return getattr(obj, key)
        elif hasattr(obj, "get"):
            return obj.get(key, default)
        else:
            return default

    def _create_error_response(self, operation: str, error: Exception) -> Dict[str, Any]:
        """Create standardized error response for failed operations."""
        logger.error(f"Failed to {operation}: {_sanitize_log_data(str(error))}")
        return {
            "success": False,
            "error": str(error),
            "message": f"Failed to {operation}",
        }

    def _check_document_exists(self, document_id: str) -> tuple[bool, Optional[Dict[str, Any]]]:
        """
        Check if document exists in status tracking.
        
        Args:
            document_id: Document ID to check
            
        Returns:
            Tuple of (exists: bool, doc_status: Optional[Dict])
        """
        if document_id not in self.document_statuses:
            return False, None
        return True, self.document_statuses[document_id]

    def _get_document_status_or_error(self, document_id: str, operation: str = "operation") -> tuple:
        """
        Get document status or return error response if not found.
        
        Args:
            document_id: Document ID to check
            operation: Operation name for error message
            
        Returns:
            Tuple of (success: bool, doc_status: Optional[Dict], error_response: Optional[Dict])
        """
        exists, doc_status = self._check_document_exists(document_id)
        if not exists:
            logger.error(f"Document {_sanitize_log_data(document_id)} not found in status tracking")
            return False, None, {
                "success": False,
                "message": f"Document {document_id} not found",
            }
        return True, doc_status, None

    def _create_mock_data_response(self, reason: Optional[str] = None, message: Optional[str] = None) -> Dict[str, Any]:
        """Create standardized mock data response with optional reason and message."""
        response = {**self._get_mock_extraction_data(), "is_mock": True}
        if reason:
            response["reason"] = reason
        if message:
            response["message"] = message
        return response

    def _create_empty_extraction_response(
        self, reason: str, message: str
    ) -> Dict[str, Any]:
        """Create empty extraction response structure for error/in-progress cases."""
        return {
            "extraction_results": [],
            "confidence_scores": {},
            "stages": [],
            "quality_score": None,
            "routing_decision": None,
            "is_mock": True,
            "reason": reason,
            "message": message,
        }

    def _extract_quality_from_dict_value(
        self, value: Any
    ) -> float:
        """Extract quality score from a value that could be a dict, object, or primitive."""
        if isinstance(value, dict):
            return value.get("overall_score", value.get("quality_score", 0.0))
        elif hasattr(value, "overall_score"):
            return getattr(value, "overall_score", 0.0)
        elif hasattr(value, "quality_score"):
            return getattr(value, "quality_score", 0.0)
        elif isinstance(value, (int, float)) and value > 0:
            return float(value)
        return 0.0

    def _extract_quality_score_from_validation_dict(
        self, validation: Dict[str, Any], doc_id: str
    ) -> float:
        """Extract quality score from validation dictionary with multiple fallback strategies."""
        # Try direct keys first (most common case)
        for key in ["overall_score", "quality_score", "score"]:
            if key in validation:
                quality = self._extract_quality_from_dict_value(validation[key])
                if quality > 0:
                    logger.debug(f"Extracted quality score from validation dict: {quality} for doc {_sanitize_log_data(doc_id)}")
                    return quality
        
        # Check nested quality_score structure
        if "quality_score" in validation:
            quality = self._extract_quality_from_dict_value(validation["quality_score"])
            if quality > 0:
                logger.debug(f"Extracted quality score from nested validation dict: {quality} for doc {_sanitize_log_data(doc_id)}")
                return quality
        
        return 0.0

    async def _extract_quality_from_extraction_data(
        self, doc_id: str
    ) -> float:
        """Extract quality score from extraction data as a fallback."""
        try:
            extraction_data = await self._get_extraction_data(doc_id)
            if extraction_data and "quality_score" in extraction_data:
                qs = extraction_data["quality_score"]
                quality = self._extract_quality_from_dict_value(qs)
                if quality > 0:
                    return quality
        except Exception as e:
            logger.debug(f"Could not extract quality score from extraction data for {_sanitize_log_data(doc_id)}: {_sanitize_log_data(str(e))}")
        return 0.0

    def _extract_quality_score_from_validation_object(
        self, validation: Any, doc_id: str
    ) -> float:
        """Extract quality score from validation object (with attributes)."""
        quality = self._extract_quality_from_dict_value(validation)
        if quality > 0:
            logger.debug(f"Extracted quality score from validation object: {quality} for doc {_sanitize_log_data(doc_id)}")
            return quality
        else:
            logger.debug(f"Validation result for doc {_sanitize_log_data(doc_id)} is not a dict or object with score attributes. Type: {type(validation)}")
            return 0.0

    def _create_quality_score_from_validation(
        self, validation_data: Union[Dict[str, Any], Any]
    ) -> Any:
        """Create QualityScore from validation data (handles both dict and object)."""
        from .models.document_models import QualityScore, QualityDecision
        
        # Handle object with attributes
        if hasattr(validation_data, "overall_score"):
            reasoning_text = getattr(validation_data, "reasoning", "")
            if isinstance(reasoning_text, str):
                reasoning_data = {"summary": reasoning_text, "details": reasoning_text}
            else:
                reasoning_data = reasoning_text if isinstance(reasoning_text, dict) else {}
            
            return QualityScore(
                overall_score=getattr(validation_data, "overall_score", 0.0),
                completeness_score=getattr(validation_data, "completeness_score", 0.0),
                accuracy_score=getattr(validation_data, "accuracy_score", 0.0),
                compliance_score=getattr(validation_data, "compliance_score", 0.0),
                quality_score=getattr(
                    validation_data,
                    "quality_score",
                    getattr(validation_data, "overall_score", 0.0),
                ),
                decision=QualityDecision(getattr(validation_data, "decision", "REVIEW")),
                reasoning=reasoning_data,
                issues_found=getattr(validation_data, "issues_found", []),
                confidence=getattr(validation_data, "confidence", 0.0),
                judge_model=self.MODEL_LARGE_JUDGE,
            )
        
        # Handle dictionary
        reasoning_data = validation_data.get("reasoning", {})
        if isinstance(reasoning_data, str):
            reasoning_data = {"summary": reasoning_data, "details": reasoning_data}
        
        return QualityScore(
            overall_score=validation_data.get("overall_score", 0.0),
            completeness_score=validation_data.get("completeness_score", 0.0),
            accuracy_score=validation_data.get("accuracy_score", 0.0),
            compliance_score=validation_data.get("compliance_score", 0.0),
            quality_score=validation_data.get(
                "quality_score",
                validation_data.get("overall_score", 0.0),
            ),
            decision=QualityDecision(validation_data.get("decision", "REVIEW")),
            reasoning=reasoning_data,
            issues_found=validation_data.get("issues_found", []),
            confidence=validation_data.get("confidence", 0.0),
            judge_model=self.MODEL_LARGE_JUDGE,
        )

    def _parse_hours_range(self, time_str: str) -> Optional[int]:
        """Parse hours range format (e.g., '4-8 hours') and return average in seconds."""
        parts = time_str.split("-")
        if len(parts) != 2:
            return None
        
        try:
            min_hours = int(parts[0].strip())
            max_hours = int(parts[1].strip().split()[0])
            avg_hours = (min_hours + max_hours) / 2
            return int(avg_hours * 3600)  # Convert to seconds
        except (ValueError, IndexError):
            return None

    def _parse_single_hours(self, time_str: str) -> Optional[int]:
        """Parse single hours format (e.g., '4 hours') and return in seconds."""
        try:
            hours = int(time_str.split()[0])
            return hours * 3600  # Convert to seconds
        except (ValueError, IndexError):
            return None

    def _parse_minutes(self, time_str: str) -> Optional[int]:
        """Parse minutes format (e.g., '30 minutes') and return in seconds."""
        try:
            minutes = int(time_str.split()[0])
            return minutes * 60  # Convert to seconds
        except (ValueError, IndexError):
            return None

    def _parse_processing_time(self, time_str: str) -> Optional[int]:
        """Parse processing time string to seconds."""
        if not time_str:
            return None

        # Handle different time formats
        if isinstance(time_str, int):
            return time_str

        time_str = str(time_str).lower()

        # Parse hours format
        if "hours" in time_str:
            # Try range format first (e.g., "4-8 hours")
            if "-" in time_str:
                result = self._parse_hours_range(time_str)
                if result is not None:
                    return result
            # Try single hours format (e.g., "4 hours")
            result = self._parse_single_hours(time_str)
            if result is not None:
                return result

        # Parse minutes format
        if "minutes" in time_str:
            result = self._parse_minutes(time_str)
            if result is not None:
                return result

        # Default fallback
        return 3600  # 1 hour default

    async def initialize(self):
        """Initialize document processing tools."""
        try:
            self.nim_client = await get_nim_client()
            self._load_status_data()  # Load persistent status data (not async)
            logger.info("Document Action Tools initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Document Action Tools: {_sanitize_log_data(str(e))}")
            raise

    def _parse_datetime_field(self, value: Any, field_name: str, doc_id: str) -> Optional[datetime]:
        """Parse a datetime string field, returning None if invalid."""
        if not isinstance(value, str):
            return None
        
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            logger.warning(
                f"Invalid datetime format for {field_name} in {_sanitize_log_data(doc_id)}"
            )
            return None

    def _restore_datetime_fields(self, status_info: Dict[str, Any], doc_id: str) -> None:
        """Restore datetime fields from ISO format strings in status_info."""
        # Restore upload_time
        if "upload_time" in status_info:
            parsed_time = self._parse_datetime_field(
                status_info["upload_time"], "upload_time", doc_id
            )
            if parsed_time is not None:
                status_info["upload_time"] = parsed_time
        
        # Restore started_at for each stage
        for stage in status_info.get("stages", []):
            if "started_at" in stage:
                parsed_time = self._parse_datetime_field(
                    stage["started_at"], "started_at", doc_id
                )
                if parsed_time is not None:
                    stage["started_at"] = parsed_time

    def _load_status_data(self):
        """Load document status data from persistent storage."""
        if not self.status_file.exists():
            logger.info(
                "No persistent status file found, starting with empty status tracking"
            )
            self.document_statuses = {}
            return
        
        try:
            with open(self.status_file, "r") as f:
                data = json.load(f)
            
            # Convert datetime strings back to datetime objects
            for doc_id, status_info in data.items():
                self._restore_datetime_fields(status_info, doc_id)
            
            self.document_statuses = data
            logger.info(
                f"Loaded {len(self.document_statuses)} document statuses from persistent storage"
            )
        except Exception as e:
            logger.error(f"Failed to load status data: {_sanitize_log_data(str(e))}")
            self.document_statuses = {}

    def _serialize_for_json(self, obj):
        """Recursively serialize objects for JSON, handling PIL Images and other non-serializable types."""
        from PIL import Image
        import base64
        import io
        
        if isinstance(obj, Image.Image):
            # Convert PIL Image to base64 string
            buffer = io.BytesIO()
            obj.save(buffer, format='PNG')
            img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
            return {"_type": "PIL_Image", "data": img_str, "format": "PNG"}
        elif isinstance(obj, dict):
            return {key: self._serialize_for_json(value) for key, value in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._serialize_for_json(item) for item in obj]
        elif hasattr(obj, "isoformat"):  # datetime objects
            return obj.isoformat()
        elif hasattr(obj, "__dict__"):  # Custom objects
            return self._serialize_for_json(obj.__dict__)
        else:
            try:
                json.dumps(obj)  # Test if it's JSON serializable
                return obj
            except (TypeError, ValueError):
                return str(obj)  # Fallback to string representation
    
    def _calculate_time_threshold(self, time_range: str) -> datetime:
        """
        Calculate time threshold based on time range string.
        
        Args:
            time_range: Time range string ("today", "week", "month", or other)
            
        Returns:
            datetime threshold for filtering
        """
        from datetime import timedelta
        
        now = datetime.now()
        today_start = datetime(now.year, now.month, now.day)
        
        if time_range == "today":
            return today_start
        elif time_range == "week":
            return now - timedelta(days=7)
        elif time_range == "month":
            return now - timedelta(days=30)
        else:
            return datetime.min  # All time

    def _save_status_data(self):
        """Save document status data to persistent storage."""
        try:
            # Convert datetime objects and PIL Images to JSON-serializable format
            data_to_save = {}
            for doc_id, status_info in self.document_statuses.items():
                data_to_save[doc_id] = self._serialize_for_json(status_info)

            with open(self.status_file, "w") as f:
                json.dump(data_to_save, f, indent=2)
            logger.debug(
                f"Saved {len(self.document_statuses)} document statuses to persistent storage"
            )
        except Exception as e:
            logger.error(f"Failed to save status data: {_sanitize_log_data(str(e))}", exc_info=True)

    async def upload_document(
        self,
        file_path: str,
        document_type: str,
        document_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upload and process document through pipeline."""
        try:
            logger.info(f"Processing document upload: {_sanitize_log_data(file_path)}")

            # Validate file
            validation_result = await self._validate_document_file(file_path)
            if not validation_result["valid"]:
                return {
                    "success": False,
                    "error": validation_result["error"],
                    "message": "Document validation failed",
                }

            # Use provided document ID or generate new one
            if document_id is None:
                document_id = str(uuid.uuid4())

            # Initialize document status tracking
            logger.info(f"Initializing document status for {_sanitize_log_data(document_id)}")
            self.document_statuses[document_id] = {
                "status": ProcessingStage.UPLOADED,
                "current_stage": "Preprocessing",
                "progress": 0,
                "file_path": file_path,  # Store the file path for local processing
                "filename": os.path.basename(file_path),
                "document_type": document_type,
                "stages": [
                    {
                        "name": "preprocessing",
                        "status": "processing",
                        "started_at": datetime.now(),
                    },
                    {"name": "ocr_extraction", "status": "pending", "started_at": None},
                    {"name": "llm_processing", "status": "pending", "started_at": None},
                    {"name": "validation", "status": "pending", "started_at": None},
                    {"name": "routing", "status": "pending", "started_at": None},
                ],
                "upload_time": datetime.now(),
                "estimated_completion": datetime.now().timestamp() + 60,
            }

            # Save status data to persistent storage
            self._save_status_data()

            # Start document processing pipeline
            await self._start_document_processing()

            return {
                "success": True,
                "document_id": document_id,
                "status": "processing_started",
                "message": "Document uploaded and processing started",
                "estimated_processing_time": "30-60 seconds",
                "processing_stages": [
                    "Preprocessing (NeMo Retriever)",
                    "OCR Extraction (NeMoRetriever-OCR-v1)",
                    "Small LLM Processing (Llama Nemotron Nano VL 8B)",
                    "Embedding & Indexing (nv-embedqa-e5-v5)",
                    "Large LLM Judge (Llama 3.1 Nemotron 70B)",
                    "Intelligent Routing",
                ],
            }

        except Exception as e:
            return self._create_error_response("upload document", e)

    async def get_document_status(self, document_id: str) -> Dict[str, Any]:
        """Get document processing status."""
        try:
            logger.info(f"Getting status for document: {_sanitize_log_data(document_id)}")

            # In real implementation, this would query the database
            # For now, return mock status
            status = await self._get_processing_status(document_id)

            return {
                "success": True,
                "document_id": document_id,
                "status": status["status"],
                "current_stage": status["current_stage"],
                "progress": status["progress"],
                "stages": status["stages"],
                "estimated_completion": status.get("estimated_completion"),
                "error_message": status.get("error_message"),
            }

        except Exception as e:
            return self._create_error_response("get document status", e)

    async def extract_document_data(self, document_id: str) -> Dict[str, Any]:
        """Extract structured data from processed document."""
        try:
            logger.info(f"Extracting data from document: {_sanitize_log_data(document_id)}")
            
            # Verify document exists in status tracking
            success, doc_status, error_response = self._get_document_status_or_error(document_id, "extract document data")
            if not success:
                error_response["extracted_data"] = {}
                return error_response

            # In real implementation, this would query extraction results
            # Always fetch fresh data for this specific document_id
            extraction_data = await self._get_extraction_data(document_id)

            return {
                "success": True,
                "document_id": document_id,
                "extracted_data": extraction_data["extraction_results"],
                "confidence_scores": extraction_data.get("confidence_scores", {}),
                "processing_stages": extraction_data.get("stages", []),
                "quality_score": extraction_data.get("quality_score"),
                "routing_decision": extraction_data.get("routing_decision"),
            }

        except Exception as e:
            return self._create_error_response("extract document data", e)

    async def validate_document_quality(
        self, document_id: str, validation_type: str = "automated"
    ) -> Dict[str, Any]:
        """Validate document extraction quality and accuracy."""
        try:
            logger.info(f"Validating document quality: {_sanitize_log_data(document_id)}")

            # In real implementation, this would run quality validation
            validation_result = await self._run_quality_validation(
                document_id, validation_type
            )

            return {
                "success": True,
                "document_id": document_id,
                "quality_score": validation_result["quality_score"],
                "decision": validation_result["decision"],
                "reasoning": validation_result["reasoning"],
                "issues_found": validation_result["issues_found"],
                "confidence": validation_result["confidence"],
                "routing_action": validation_result["routing_action"],
            }

        except Exception as e:
            return self._create_error_response("validate document quality", e)

    async def search_documents(
        self, search_query: str, filters: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Search processed documents by content or metadata."""
        try:
            logger.info(f"Searching documents with query: {_sanitize_log_data(search_query)}")

            # In real implementation, this would use vector search and metadata filtering
            search_results = await self._search_documents(search_query, filters or {})

            return {
                "success": True,
                "query": search_query,
                "results": search_results["documents"],
                "total_count": search_results["total_count"],
                "search_time_ms": search_results["search_time_ms"],
                "filters_applied": filters or {},
            }

        except Exception as e:
            return self._create_error_response("search documents", e)

    async def get_document_analytics(
        self, time_range: str = "week", metrics: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Get analytics and metrics for document processing."""
        try:
            logger.info(f"Getting document analytics for time range: {_sanitize_log_data(time_range)}")

            # In real implementation, this would query analytics from database
            analytics_data = await self._get_analytics_data(time_range, metrics or [])

            return {
                "success": True,
                "time_range": time_range,
                "metrics": analytics_data["metrics"],
                "trends": analytics_data["trends"],
                "summary": analytics_data["summary"],
                "generated_at": datetime.now(),
            }

        except Exception as e:
            return self._create_error_response("get document analytics", e)

    async def approve_document(
        self, document_id: str, approver_id: str, approval_notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """Approve document for WMS integration."""
        try:
            logger.info(f"Approving document: {_sanitize_log_data(document_id)}")

            # In real implementation, this would update database and trigger WMS integration
            approval_result = await self._approve_document(
                document_id, approver_id, approval_notes
            )

            return {
                "success": True,
                "document_id": document_id,
                "approver_id": approver_id,
                "approval_status": "approved",
                "wms_integration_status": approval_result["wms_status"],
                "approval_timestamp": datetime.now(),
                "approval_notes": approval_notes,
            }

        except Exception as e:
            return self._create_error_response("approve document", e)

    async def reject_document(
        self,
        document_id: str,
        rejector_id: str,
        rejection_reason: str,
        suggestions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Reject document and provide feedback."""
        try:
            logger.info(f"Rejecting document: {_sanitize_log_data(document_id)}")

            # In real implementation, this would update database and notify user
            await self._reject_document(
                document_id, rejector_id, rejection_reason, suggestions or []
            )

            return {
                "success": True,
                "document_id": document_id,
                "rejector_id": rejector_id,
                "rejection_status": "rejected",
                "rejection_reason": rejection_reason,
                "suggestions": suggestions or [],
                "rejection_timestamp": datetime.now(),
            }

        except Exception as e:
            return self._create_error_response("reject document", e)

    # Helper methods (mock implementations for now)
    async def _validate_document_file(self, file_path: str) -> Dict[str, Any]:
        """Validate document file using async file operations."""
        # Run synchronous file operations in thread pool to avoid blocking
        file_exists = await asyncio.to_thread(os.path.exists, file_path)
        if not file_exists:
            return {"valid": False, "error": "File does not exist"}

        file_size = await asyncio.to_thread(os.path.getsize, file_path)
        if file_size > self.max_file_size:
            return {
                "valid": False,
                "error": f"File size exceeds {self.max_file_size} bytes",
            }

        # String operations are fast and don't need threading
        file_ext = os.path.splitext(file_path)[1].lower().lstrip(".")
        if file_ext not in self.supported_file_types:
            return {"valid": False, "error": f"Unsupported file type: {file_ext}"}

        return {"valid": True, "file_type": file_ext, "file_size": file_size}

    async def _start_document_processing(self) -> Dict[str, Any]:
        """Start document processing pipeline."""
        # Mock implementation - in real implementation, this would start the actual pipeline
        # Use async sleep to make this truly async (minimal overhead)
        await asyncio.sleep(0)
        return {
            "processing_started": True,
            "pipeline_id": str(uuid.uuid4()),
            "estimated_completion": datetime.now().timestamp()
            + 60,  # 60 seconds from now
        }

    async def _get_processing_status(self, document_id: str) -> Dict[str, Any]:
        """Get processing status - use actual status from document_statuses, not simulation."""
        logger.info(f"Getting processing status for document: {_sanitize_log_data(document_id)}")

        exists, doc_status = self._check_document_exists(document_id)
        if not exists:
            logger.warning(f"Document {_sanitize_log_data(document_id)} not found in status tracking")
            return {
                "status": ProcessingStage.FAILED,
                "current_stage": "Unknown",
                "progress": 0,
                "stages": [],
                "estimated_completion": None,
            }

        status_info = self.document_statuses[document_id]
        
        # Use actual status from document_statuses, not time-based simulation
        # The background task updates status after each stage
        overall_status = status_info.get("status", ProcessingStage.UPLOADED)
        
        # Convert enum to string if needed
        if hasattr(overall_status, "value"):
            overall_status_str = overall_status.value
        elif isinstance(overall_status, str):
            overall_status_str = overall_status
        else:
            overall_status_str = str(overall_status)
        
        current_stage_name = status_info.get("current_stage", "Unknown")
        progress = status_info.get("progress", 0)
        stages = status_info.get("stages", [])
        
        # If status is COMPLETED, verify that processing_results actually exist
        # This prevents race conditions where status shows COMPLETED but results aren't stored yet
        if overall_status_str == "completed" or overall_status == ProcessingStage.COMPLETED:
            if "processing_results" not in status_info:
                logger.warning(f"Document {_sanitize_log_data(document_id)} status is COMPLETED but no processing_results found. Setting to ROUTING.")
                overall_status_str = "routing"
                status_info["status"] = ProcessingStage.ROUTING
                current_stage_name = "Finalizing"
                progress = 95
                # Run synchronous save operation in thread pool to make it async
                await asyncio.to_thread(self._save_status_data)

        return {
            "status": overall_status_str,  # Return string, not enum
            "current_stage": current_stage_name,
            "progress": progress,
            "stages": stages,
            "estimated_completion": status_info.get("estimated_completion"),
            "error_message": status_info.get("error_message"),
        }

    async def _store_processing_results(
        self,
        document_id: str,
        preprocessing_result: Dict[str, Any],
        ocr_result: Dict[str, Any],
        llm_result: Dict[str, Any],
        validation_result: Dict[str, Any],
        routing_result: Dict[str, Any],
    ) -> None:
        """Store actual processing results from NVIDIA NeMo pipeline."""
        try:
            logger.info(f"Storing processing results for document: {_sanitize_log_data(document_id)}")

            # Serialize results to remove PIL Images and other non-JSON-serializable objects
            # Convert PIL Images to metadata (file paths, dimensions) instead of storing the image objects
            serialized_preprocessing = self._serialize_processing_result(preprocessing_result)
            serialized_ocr = self._serialize_processing_result(ocr_result)
            serialized_llm = self._serialize_processing_result(llm_result)
            serialized_validation = self._serialize_processing_result(validation_result)
            serialized_routing = self._serialize_processing_result(routing_result)

            # Store results in document_statuses
            exists, doc_status = self._check_document_exists(document_id)
            if exists:
                self.document_statuses[document_id]["processing_results"] = {
                    "preprocessing": serialized_preprocessing,
                    "ocr": serialized_ocr,
                    "llm_processing": serialized_llm,
                    "validation": serialized_validation,
                    "routing": serialized_routing,
                    "stored_at": datetime.now().isoformat(),
                }
                self.document_statuses[document_id][
                    "status"
                ] = ProcessingStage.COMPLETED
                self.document_statuses[document_id]["progress"] = 100

                # Update all stages to completed
                for stage in self.document_statuses[document_id]["stages"]:
                    stage["status"] = "completed"
                    stage["completed_at"] = datetime.now().isoformat()

                # Save to persistent storage (run in thread pool to avoid blocking)
                await asyncio.to_thread(self._save_status_data)
                logger.info(
                    f"Successfully stored processing results for document: {_sanitize_log_data(document_id)}"
                )
            else:
                logger.error(f"Document {document_id} not found in status tracking")

        except Exception as e:
            logger.error(
                f"Failed to store processing results for {document_id}: {e}",
                exc_info=True,
            )
    
    def _convert_pil_image_to_metadata(self, image) -> Dict[str, Any]:
        """Convert PIL Image to metadata dictionary for JSON serialization."""
        from PIL import Image
        return {
            "_type": "PIL_Image_Reference",
            "size": image.size,
            "mode": image.mode,
            "format": getattr(image, "format", "PNG"),
            "note": "Image object converted to metadata for JSON serialization"
        }

    def _serialize_processing_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Serialize processing result, converting PIL Images to metadata."""
        from PIL import Image
        from dataclasses import asdict, is_dataclass
        
        # Handle dataclass objects (like JudgeEvaluation)
        if is_dataclass(result):
            result = asdict(result)
        
        if not isinstance(result, dict):
            # Try to convert to dict if it has __dict__ attribute
            if hasattr(result, "__dict__"):
                result = result.__dict__
            else:
                return result
        
        serialized = {}
        for key, value in result.items():
            if isinstance(value, Image.Image):
                # Convert PIL Image to metadata (dimensions, format) instead of storing the image
                serialized[key] = self._convert_pil_image_to_metadata(value)
            elif isinstance(value, list):
                # Handle lists that might contain PIL Images
                serialized[key] = [
                    self._convert_pil_image_to_metadata(item) if isinstance(item, Image.Image) else item
                    for item in value
                ]
            elif isinstance(value, dict):
                # Recursively serialize nested dictionaries
                serialized[key] = self._serialize_processing_result(value)
            else:
                serialized[key] = value
        
        return serialized

    async def _update_document_status(
        self, document_id: str, status: str, error_message: str = None
    ) -> None:
        """Update document status (used for error handling)."""
        try:
            exists, doc_status = self._check_document_exists(document_id)
            if exists:
                self.document_statuses[document_id]["status"] = ProcessingStage.FAILED
                self.document_statuses[document_id]["progress"] = 0
                self.document_statuses[document_id]["current_stage"] = "Failed"
                if error_message:
                    self.document_statuses[document_id]["error_message"] = error_message
                # Mark all stages as failed
                if "stages" in self.document_statuses[document_id]:
                    for stage in self.document_statuses[document_id]["stages"]:
                        if stage["status"] not in ["completed", "failed"]:
                            stage["status"] = "failed"
                            stage["error_message"] = error_message
                self._save_status_data()
                logger.info(f"Updated document {_sanitize_log_data(document_id)} status to FAILED: {_sanitize_log_data(error_message)}")
            else:
                logger.error(f"Document {_sanitize_log_data(document_id)} not found for status update")
        except Exception as e:
            logger.error(f"Failed to update document status: {_sanitize_log_data(str(e))}", exc_info=True)

    async def _get_extraction_data(self, document_id: str) -> Dict[str, Any]:
        """Get extraction data from actual processing results."""
        from .models.document_models import (
            ExtractionResult,
            QualityScore,
            RoutingDecision,
            QualityDecision,
        )

        try:
            # Check if we have actual processing results
            exists, doc_status = self._check_document_exists(document_id)
            if exists:

                # If we have actual processing results, return them
                if "processing_results" in doc_status:
                    results = doc_status["processing_results"]

                    # Convert actual results to ExtractionResult format
                    extraction_results = []

                    # OCR Results
                    if "ocr" in results and results["ocr"]:
                        ocr_data = results["ocr"]
                        extraction_results.append(
                            ExtractionResult(
                                stage="ocr_extraction",
                                raw_data={
                                    "text": ocr_data.get("text", ""),
                                    "pages": ocr_data.get("page_results", []),
                                },
                                processed_data={
                                    "extracted_text": ocr_data.get("text", ""),
                                    "total_pages": ocr_data.get("total_pages", 0),
                                },
                                confidence_score=ocr_data.get("confidence", 0.0),
                                processing_time_ms=0,  # OCR doesn't track processing time yet
                                model_used=ocr_data.get("model_used", self.MODEL_OCR),
                                metadata={
                                    "layout_enhanced": ocr_data.get(
                                        "layout_enhanced", False
                                    ),
                                    "timestamp": ocr_data.get(
                                        "processing_timestamp", ""
                                    ),
                                },
                            )
                        )

                    # LLM Processing Results
                    if "llm_processing" in results and results["llm_processing"]:
                        llm_data = results["llm_processing"]
                        structured_data = llm_data.get("structured_data", {})
                        
                        # If extracted_fields is empty, try to parse from OCR text
                        if not structured_data.get("extracted_fields") and ocr_data.get("text"):
                            logger.info("LLM returned empty extracted_fields, attempting fallback parsing from OCR text")
                            from src.api.agents.document.processing.small_llm_processor import SmallLLMProcessor
                            llm_processor = SmallLLMProcessor()
                            parsed_fields = await llm_processor._parse_fields_from_text(
                                ocr_data.get("text", ""),
                                structured_data.get("document_type", "invoice")
                            )
                            if parsed_fields:
                                structured_data["extracted_fields"] = parsed_fields
                                logger.info(f"Fallback parsing extracted {len(parsed_fields)} fields from OCR text")
                        
                        extraction_results.append(
                            ExtractionResult(
                                stage="llm_processing",
                                raw_data={
                                    "entities": llm_data.get("raw_entities", []),
                                    "raw_response": llm_data.get("raw_response", ""),
                                },
                                processed_data=structured_data,
                                confidence_score=llm_data.get("confidence", 0.0),
                                processing_time_ms=llm_data.get(
                                    "processing_time_ms", 0
                                ),
                                model_used=self.MODEL_SMALL_LLM,
                                metadata=llm_data.get("metadata", {}),
                            )
                        )

                    # Quality Score from validation
                    quality_score = None
                    if "validation" in results and results["validation"]:
                        validation_data = results["validation"]

                        # Handle both JudgeEvaluation object and dictionary
                        quality_score = self._create_quality_score_from_validation(validation_data)

                    # Routing Decision
                    routing_decision = None
                    if "routing" in results and results["routing"]:
                        routing_data = results["routing"]
                        routing_decision = RoutingDecision(
                            routing_action=RoutingAction(
                                self._get_value(
                                    routing_data, "routing_action", "flag_review"
                                )
                            ),
                            routing_reason=self._get_value(
                                routing_data, "routing_reason", ""
                            ),
                            wms_integration_status=self._get_value(
                                routing_data, "wms_integration_status", "pending"
                            ),
                            wms_integration_data=self._get_value(
                                routing_data, "wms_integration_data"
                            ),
                            human_review_required=self._get_value(
                                routing_data, "human_review_required", False
                            ),
                            human_reviewer_id=self._get_value(
                                routing_data, "human_reviewer_id"
                            ),
                            estimated_processing_time=self._parse_processing_time(
                                self._get_value(
                                    routing_data, "estimated_processing_time"
                                )
                            ),
                        )

                    return {
                        "extraction_results": extraction_results,
                        "confidence_scores": {
                            "overall": (
                                quality_score.overall_score / 5.0
                                if quality_score
                                else 0.0
                            ),
                            "ocr": (
                                extraction_results[0].confidence_score
                                if extraction_results
                                else 0.0
                            ),
                            "entity_extraction": (
                                extraction_results[1].confidence_score
                                if len(extraction_results) > 1
                                else 0.0
                            ),
                        },
                        "stages": [result.stage for result in extraction_results],
                        "quality_score": quality_score,
                        "routing_decision": routing_decision,
                    }

            # No processing results found - check if NeMo pipeline is still running
            exists, doc_status = self._check_document_exists(document_id)
            if exists:
                current_status = doc_status.get("status", "")
                
                # Check if processing is still in progress
                # Note: PROCESSING doesn't exist in enum, use PREPROCESSING, OCR_EXTRACTION, etc.
                processing_stages = [
                    ProcessingStage.UPLOADED, 
                    ProcessingStage.PREPROCESSING,
                    ProcessingStage.OCR_EXTRACTION,
                    ProcessingStage.LLM_PROCESSING,
                    ProcessingStage.VALIDATION,
                    ProcessingStage.ROUTING
                ]
                if current_status in processing_stages:
                    logger.info(f"Document {_sanitize_log_data(document_id)} is still being processed by NeMo pipeline. Status: {_sanitize_log_data(str(current_status))}")
                    # Return a message indicating processing is in progress
                    return self._create_empty_extraction_response(
                        "processing_in_progress",
                        "Document is still being processed by NVIDIA NeMo pipeline. Please check again in a moment."
                    )
                elif current_status == ProcessingStage.COMPLETED:
                    # Status says COMPLETED but no processing_results - this shouldn't happen
                    # but if it does, wait a bit and check again (race condition)
                    logger.warning(f"Document {_sanitize_log_data(document_id)} status is COMPLETED but no processing_results found. This may be a race condition.")
                    return self._create_empty_extraction_response(
                        "results_not_ready",
                        "Processing completed but results are not ready yet. Please check again in a moment."
                    )
                elif current_status == ProcessingStage.FAILED:
                    # Processing failed
                    error_msg = doc_status.get("error_message", "Unknown error")
                    logger.warning(f"Document {_sanitize_log_data(document_id)} processing failed: {_sanitize_log_data(error_msg)}")
                    return self._create_empty_extraction_response(
                        "processing_failed",
                        f"Document processing failed: {error_msg}"
                    )
                else:
                    logger.warning(f"Document {_sanitize_log_data(document_id)} has no processing results and status is {_sanitize_log_data(str(current_status))}. NeMo pipeline may have failed.")
                    # Return mock data with clear indication that NeMo pipeline didn't complete
                    return self._create_mock_data_response(
                        "nemo_pipeline_incomplete",
                        "NVIDIA NeMo pipeline did not complete processing. Please check server logs for errors."
                    )
            else:
                logger.error(f"Document {_sanitize_log_data(document_id)} not found in status tracking")
                return self._create_mock_data_response("document_not_found")

        except Exception as e:
            logger.error(
                f"Failed to get extraction data for {document_id}: {e}", exc_info=True
            )
            return self._get_mock_extraction_data()

    async def _process_document_locally(self, document_id: str) -> Dict[str, Any]:
        """Process document locally using the local processor."""
        try:
            # Get document info from status
            success, doc_status, error_response = self._get_document_status_or_error(document_id, "process document locally")
            if not success:
                return self._create_mock_data_response()
            file_path = doc_status.get("file_path")
            
            if not file_path or not os.path.exists(file_path):
                logger.warning(f"File not found for document {_sanitize_log_data(document_id)}: {_sanitize_log_data(file_path)}")
                logger.info(f"Attempting to use document filename: {_sanitize_log_data(doc_status.get('filename', 'N/A'))}")
                # Return mock data but mark it as such
                return self._create_mock_data_response("file_not_found")
            
            # Try to process the document locally
            try:
                from .processing.local_processor import local_processor
                result = await local_processor.process_document(file_path, doc_status.get("document_type", "invoice"))
                
                if not result["success"]:
                    logger.error(f"Local processing failed for {_sanitize_log_data(document_id)}: {_sanitize_log_data(str(result.get('error', 'Unknown error')))}")
                    return self._create_mock_data_response("processing_failed")
            except ImportError as e:
                logger.warning(f"Local processor not available (missing dependencies): {_sanitize_log_data(str(e))}")
                missing_module = str(e).replace("No module named ", "").strip("'\"")
                if "fitz" in missing_module.lower() or "pymupdf" in missing_module.lower():
                    logger.info("Install PyMuPDF for PDF processing: pip install PyMuPDF")
                elif "PIL" in missing_module or "Pillow" in missing_module:
                    logger.info("Install Pillow (PIL) for image processing: pip install Pillow")
                else:
                    logger.info(f"Install missing dependency: pip install {_sanitize_log_data(missing_module)}")
                return self._create_mock_data_response("dependencies_missing")
            except Exception as e:
                logger.error(f"Local processing error for {_sanitize_log_data(document_id)}: {_sanitize_log_data(str(e))}")
                return self._create_mock_data_response("processing_error")
            
            # Convert local processing result to expected format
            from .models.document_models import ExtractionResult, QualityScore, RoutingDecision, QualityDecision
            
            extraction_results = []
            
            # OCR Result
            extraction_results.append(
                ExtractionResult(
                    stage="ocr_extraction",
                    raw_data={"text": result["raw_text"]},
                    processed_data={"extracted_text": result["raw_text"]},
                    confidence_score=result["confidence_scores"]["ocr"],
                    processing_time_ms=result["processing_time_ms"],
                    model_used=result["model_used"],
                    metadata=result["metadata"]
                )
            )
            
            # LLM Processing Result
            extraction_results.append(
                ExtractionResult(
                    stage="llm_processing",
                    raw_data={"raw_response": result["raw_text"]},
                    processed_data=result["structured_data"],
                    confidence_score=result["confidence_scores"]["entity_extraction"],
                    processing_time_ms=result["processing_time_ms"],
                    model_used=result["model_used"],
                    metadata=result["metadata"]
                )
            )
            
            # Quality Score
            quality_score = QualityScore(
                overall_score=result["confidence_scores"]["overall"] * 5.0,  # Convert to 0-5 scale
                completeness_score=result["confidence_scores"]["overall"] * 5.0,
                accuracy_score=result["confidence_scores"]["overall"] * 5.0,
                compliance_score=result["confidence_scores"]["overall"] * 5.0,
                quality_score=result["confidence_scores"]["overall"] * 5.0,
                decision=QualityDecision.APPROVE if result["confidence_scores"]["overall"] > 0.7 else QualityDecision.REVIEW,
                reasoning={
                    "summary": "Document processed successfully using local extraction",
                    "details": f"Extracted {len(result['structured_data'])} fields with {result['confidence_scores']['overall']:.2f} confidence"
                },
                issues_found=[],
                confidence=result["confidence_scores"]["overall"],
                judge_model="Local Processing Engine"
            )
            
            # Routing Decision
            routing_decision = RoutingDecision(
                routing_action="auto_approve" if result["confidence_scores"]["overall"] > 0.8 else "flag_review",
                routing_reason="High confidence local processing" if result["confidence_scores"]["overall"] > 0.8 else "Requires human review",
                wms_integration_status="ready" if result["confidence_scores"]["overall"] > 0.8 else "pending",
                wms_integration_data=result["structured_data"],
                human_review_required=result["confidence_scores"]["overall"] <= 0.8,
                human_reviewer_id=None,
                estimated_processing_time=3600  # 1 hour
            )
            
            return {
                "extraction_results": extraction_results,
                "confidence_scores": result["confidence_scores"],
                "stages": [result.stage for result in extraction_results],
                "quality_score": quality_score,
                "routing_decision": routing_decision,
                "is_mock": False,  # Mark as real data
            }
            
        except Exception as e:
            logger.error(f"Failed to process document locally: {_sanitize_log_data(str(e))}", exc_info=True)
            return self._create_mock_data_response("exception")

    def _get_mock_extraction_data(self) -> Dict[str, Any]:
        """Fallback mock extraction data that matches the expected API response format."""
        from .models.document_models import (
            ExtractionResult,
            QualityScore,
            RoutingDecision,
            QualityDecision,
        )
        # Security: Using random module is appropriate here - generating test invoice numbers only
        # For security-sensitive values (tokens, keys, passwords), use secrets module instead
        import random
        import datetime

        # Generate realistic invoice data
        invoice_number = (
            f"INV-{datetime.datetime.now().year}-{random.randint(1000, 9999)}"
        )
        vendors = [
            "ABC Supply Co.",
            "XYZ Manufacturing",
            "Global Logistics Inc.",
            "Tech Solutions Ltd.",
        ]
        vendor = random.choice(vendors)

        # Generate realistic amounts
        base_amount = random.randint(500, 5000)
        tax_rate = 0.08
        tax_amount = round(base_amount * tax_rate, 2)
        total_amount = base_amount + tax_amount

        # Generate line items
        line_items = []
        num_items = random.randint(2, 8)
        for _ in range(num_items):
            item_names = ["Widget A", "Component B", "Part C", "Module D", "Assembly E"]
            item_name = random.choice(item_names)
            quantity = random.randint(1, 50)
            unit_price = round(random.uniform(10, 200), 2)
            line_total = round(quantity * unit_price, 2)
            line_items.append(
                {
                    "description": item_name,
                    "quantity": quantity,
                    "price": unit_price,
                    "total": line_total,
                }
            )

        return {
            "extraction_results": [
                ExtractionResult(
                    stage="ocr_extraction",
                    raw_data={
                        "text": f"Invoice #{invoice_number}\nVendor: {vendor}\nAmount: ${base_amount:,.2f}"
                    },
                    processed_data={
                        "invoice_number": invoice_number,
                        "vendor": vendor,
                        "amount": base_amount,
                        "tax_amount": tax_amount,
                        "total_amount": total_amount,
                        "date": datetime.datetime.now().strftime("%Y-%m-%d"),
                        "line_items": line_items,
                    },
                    confidence_score=0.96,
                    processing_time_ms=1200,
                    model_used=self.MODEL_OCR,
                    metadata={"page_count": 1, "language": "en", "field_count": 8},
                ),
                ExtractionResult(
                    stage="llm_processing",
                    raw_data={
                        "entities": [
                            invoice_number,
                            vendor,
                            str(base_amount),
                            str(total_amount),
                        ]
                    },
                    processed_data={
                        "items": line_items,
                        "line_items_count": len(line_items),
                        "total_amount": total_amount,
                        "validation_passed": True,
                    },
                    confidence_score=0.94,
                    processing_time_ms=800,
                    model_used=self.MODEL_SMALL_LLM,
                    metadata={"entity_count": 4, "validation_passed": True},
                ),
            ],
            "confidence_scores": {
                "overall": 0.95,
                "ocr_extraction": 0.96,
                "llm_processing": 0.94,
            },
            "stages": [
                "preprocessing",
                "ocr_extraction",
                "llm_processing",
                "validation",
                "routing",
            ],
            "quality_score": QualityScore(
                overall_score=4.3,
                completeness_score=4.5,
                accuracy_score=4.2,
                compliance_score=4.1,
                quality_score=4.3,
                decision=QualityDecision.APPROVE,
                reasoning={
                    "completeness": "All required fields extracted successfully",
                    "accuracy": "High accuracy with minor formatting variations",
                    "compliance": "Follows standard business rules",
                    "quality": "Excellent overall quality",
                },
                issues_found=["Minor formatting inconsistencies"],
                confidence=0.91,
                judge_model=self.MODEL_LARGE_JUDGE,
            ),
            "routing_decision": RoutingDecision(
                routing_action=RoutingAction.AUTO_APPROVE,
                routing_reason="High quality extraction with accurate data - auto-approve for WMS integration",
                wms_integration_status="ready_for_integration",
                wms_integration_data={
                    "vendor_code": vendor.replace(" ", "_").upper(),
                    "invoice_number": invoice_number,
                    "total_amount": total_amount,
                    "line_items": line_items,
                },
                human_review_required=False,
                human_reviewer_id=None,
                estimated_processing_time=120,
            ),
        }

    async def _run_quality_validation(
        self, document_id: str, validation_type: str
    ) -> Dict[str, Any]:
        """Run quality validation (mock implementation)."""
        return {
            "quality_score": {
                "overall": 4.2,
                "completeness": 4.5,
                "accuracy": 4.0,
                "compliance": 4.1,
                "quality": 4.2,
            },
            "decision": QualityDecision.REVIEW,
            "reasoning": {
                "completeness": "All required fields extracted",
                "accuracy": "Minor OCR errors detected",
                "compliance": "Follows business rules",
                "quality": "Good overall quality",
            },
            "issues_found": ["Minor OCR error in amount field"],
            "confidence": 0.85,
            "routing_action": RoutingAction.FLAG_REVIEW,
        }

    async def _search_documents(
        self, query: str, filters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Search documents (mock implementation)."""
        return {
            "documents": [
                {
                    "document_id": str(uuid.uuid4()),
                    "filename": "invoice_001.pdf",
                    "document_type": "invoice",
                    "relevance_score": 0.92,
                    "quality_score": 4.2,
                    "summary": "Invoice from ABC Supply Co. for $1,250.00",
                    "upload_date": datetime.now(),
                }
            ],
            "total_count": 1,
            "search_time_ms": 45,
        }

    async def _get_analytics_data(
        self, time_range: str, metrics: List[str]
    ) -> Dict[str, Any]:
        """Get analytics data from actual document processing results."""
        try:
            from datetime import timedelta
            
            # Get current time and today's start
            now = datetime.now()
            today_start = datetime(now.year, now.month, now.day)
            
            # Calculate metrics from actual document_statuses
            total_documents = len(self.document_statuses)
            
            # Filter documents by time range
            time_threshold = self._calculate_time_threshold(time_range)
            
            # Calculate metrics from actual documents
            processed_today = 0
            completed_documents = 0
            total_quality = 0.0
            auto_approved_count = 0
            failed_count = 0
            quality_scores = []
            daily_processing = {}  # Track documents by day
            
            logger.info(f"Calculating analytics from {len(self.document_statuses)} documents")
            
            for doc_id, doc_status in self.document_statuses.items():
                upload_time = doc_status.get("upload_time", datetime.min)
                
                # Convert string to datetime if needed
                if isinstance(upload_time, str):
                    try:
                        upload_time = datetime.fromisoformat(upload_time.replace('Z', '+00:00'))
                    except:
                        upload_time = datetime.min
                
                # Count documents in time range
                if upload_time >= time_threshold:
                    # Count processed today
                    if upload_time >= today_start:
                        processed_today += 1
                    
                    # Track daily processing
                    day_key = upload_time.strftime("%Y-%m-%d")
                    daily_processing[day_key] = daily_processing.get(day_key, 0) + 1
                    
                    # Count completed documents
                    doc_status_value = doc_status.get("status")
                    if doc_status_value == ProcessingStage.COMPLETED:
                        completed_documents += 1
                        
                        # Get quality score from processing results
                        if "processing_results" in doc_status:
                            results = doc_status["processing_results"]
                            quality = 0.0
                            
                            # Try to extract quality score from validation results
                            if "validation" in results and results["validation"]:
                                validation = results["validation"]
                                
                                # Handle different validation result structures
                                if isinstance(validation, dict):
                                    quality = self._extract_quality_score_from_validation_dict(validation, doc_id)
                                else:
                                    quality = self._extract_quality_score_from_validation_object(validation, doc_id)
                            
                            # If still no quality score found, try to get it from extraction data
                            if quality == 0.0:
                                quality = await self._extract_quality_from_extraction_data(doc_id)
                            
                            # Add quality score if found
                            if quality > 0:
                                quality_scores.append(quality)
                                total_quality += quality
                                
                                # Count auto-approved (quality >= 4.0)
                                if quality >= 4.0:
                                    auto_approved_count += 1
                            else:
                                logger.debug(f"Document {_sanitize_log_data(doc_id)} completed but no quality score found. Validation keys: {list(results.get('validation', {}).keys()) if isinstance(results.get('validation'), dict) else 'N/A'}")
                        else:
                            logger.debug(f"Document {_sanitize_log_data(doc_id)} completed but no processing_results found")
                    elif doc_status_value == ProcessingStage.FAILED:
                        # Count failed documents
                        failed_count += 1
                    else:
                        logger.debug(f"Document {_sanitize_log_data(doc_id)} status: {_sanitize_log_data(str(doc_status_value))} (not COMPLETED or FAILED)")
            
            # Calculate averages
            average_quality = (
                total_quality / len(quality_scores) if quality_scores else 0.0
            )
            
            logger.info(f"Analytics calculation: {completed_documents} completed, {len(quality_scores)} with quality scores, avg quality: {average_quality:.2f}")
            
            # Calculate success rate
            total_processed = completed_documents + failed_count
            success_rate = (
                (completed_documents / total_processed * 100) if total_processed > 0 else 0.0
            )
            
            # Calculate auto-approval rate
            auto_approved_rate = (
                (auto_approved_count / completed_documents * 100) if completed_documents > 0 else 0.0
            )
            
            # Generate daily processing trend (last 7 days for better visualization)
            daily_processing_list = []
            for i in range(7):
                day = (now - timedelta(days=6-i)).strftime("%Y-%m-%d")
                daily_processing_list.append(daily_processing.get(day, 0))
            
            # Ensure we always have 7 days of data (pad with zeros if needed)
            while len(daily_processing_list) < 7:
                daily_processing_list.append(0)
            
            # Generate quality trends (last 7 documents with quality scores)
            quality_trends_list = quality_scores[-7:] if len(quality_scores) >= 7 else quality_scores.copy()
            # Pad with average if less than 7, or use sample data if no quality scores
            if len(quality_trends_list) == 0:
                # No quality scores - use sample trend data for visualization
                quality_trends_list = [3.8, 4.0, 4.2, 4.1, 4.3, 4.0, 4.2]
            else:
                # Pad to 7 items with average or last known value
                while len(quality_trends_list) < 7:
                    if average_quality > 0:
                        quality_trends_list.insert(0, average_quality)
                    elif len(quality_trends_list) > 0:
                        quality_trends_list.insert(0, quality_trends_list[0])
                    else:
                        quality_trends_list.insert(0, 4.0)
            
            # Ensure arrays are exactly 7 items
            daily_processing_list = daily_processing_list[:7]
            quality_trends_list = quality_trends_list[:7]
            
            # Generate summary
            if total_documents == 0:
                summary = "No documents processed yet. Upload documents to see analytics."
            elif completed_documents == 0:
                summary = f"{total_documents} document(s) uploaded, processing in progress."
            else:
                summary = (
                    f"Processed {completed_documents} document(s) with "
                    f"{average_quality:.1f}/5.0 average quality. "
                    f"Success rate: {success_rate:.1f}%"
                )
            
            return {
                "metrics": {
                    "total_documents": total_documents,
                    "processed_today": processed_today,
                    "average_quality": round(average_quality, 1),
                    "auto_approved": round(auto_approved_rate, 1),
                    "success_rate": round(success_rate, 1),
                },
                "trends": {
                    "daily_processing": daily_processing_list,
                    "quality_trends": [round(q, 1) for q in quality_trends_list],
                },
                "summary": summary,
            }
            
        except Exception as e:
            logger.error(f"Error calculating analytics from real data: {_sanitize_log_data(str(e))}", exc_info=True)
            # Fallback to default data if calculation fails - ensure arrays always have data
            from datetime import timedelta
            now = datetime.now()
            return {
                "metrics": {
                    "total_documents": len(self.document_statuses),
                    "processed_today": 0,
                    "average_quality": 0.0,
                    "auto_approved": 0.0,
                    "success_rate": 0.0,
                },
                "trends": {
                    "daily_processing": [0, 0, 0, 0, 0, 0, 0],  # 7 days
                    "quality_trends": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],  # 7 days
                },
                "summary": f"Error calculating analytics: {str(e)}",
            }

    async def _approve_document(
        self, document_id: str, approver_id: str, notes: Optional[str]
    ) -> Dict[str, Any]:
        """Approve document (mock implementation)."""
        return {
            "wms_status": "integrated",
            "integration_data": {
                "wms_document_id": f"WMS-{document_id[:8]}",
                "integration_timestamp": datetime.now(),
            },
        }

    async def _reject_document(
        self, document_id: str, rejector_id: str, reason: str, suggestions: List[str]
    ) -> Dict[str, Any]:
        """Reject document (mock implementation)."""
        return {"rejection_recorded": True, "notification_sent": True}
