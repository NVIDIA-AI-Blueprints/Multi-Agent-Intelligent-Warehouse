"""
Document Action Tools for MCP Framework
Implements document processing tools for the MCP-enabled Document Extraction Agent
"""

import logging
import base64
import re
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
    if re.search(r'[\r\n\t\x00-\x1f]', data_str):
        # Contains control characters - base64 encode for safety
        try:
            encoded = base64.b64encode(data_str.encode('utf-8')).decode('ascii')
            return f"[base64:{encoded}]"
        except Exception:
            # If encoding fails, remove control characters
            data_str = re.sub(r'[\r\n\t\x00-\x1f]', '', data_str)
    
    # Remove any remaining suspicious characters
    data_str = re.sub(r'[\r\n]', '', data_str)
    
    return data_str


class DocumentActionTools:
    """Document processing action tools for MCP framework."""

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

    def _parse_processing_time(self, time_str: str) -> Optional[int]:
        """Parse processing time string to seconds."""
        if not time_str:
            return None

        # Handle different time formats
        if isinstance(time_str, int):
            return time_str

        time_str = str(time_str).lower()

        # Parse "4-8 hours" format
        if "hours" in time_str:
            if "-" in time_str:
                # Take the average of the range
                parts = time_str.split("-")
                if len(parts) == 2:
                    try:
                        min_hours = int(parts[0].strip())
                        max_hours = int(parts[1].strip().split()[0])
                        avg_hours = (min_hours + max_hours) / 2
                        return int(avg_hours * 3600)  # Convert to seconds
                    except (ValueError, IndexError):
                        pass
            else:
                try:
                    hours = int(time_str.split()[0])
                    return hours * 3600  # Convert to seconds
                except (ValueError, IndexError):
                    pass

        # Parse "30 minutes" format
        elif "minutes" in time_str:
            try:
                minutes = int(time_str.split()[0])
                return minutes * 60  # Convert to seconds
            except (ValueError, IndexError):
                pass

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

    def _load_status_data(self):
        """Load document status data from persistent storage."""
        try:
            if self.status_file.exists():
                with open(self.status_file, "r") as f:
                    data = json.load(f)
                    # Convert datetime strings back to datetime objects
                    for doc_id, status_info in data.items():
                        if "upload_time" in status_info and isinstance(
                            status_info["upload_time"], str
                        ):
                            try:
                                status_info["upload_time"] = datetime.fromisoformat(
                                    status_info["upload_time"]
                                )
                            except ValueError:
                                logger.warning(
                                    f"Invalid datetime format for upload_time in "
                                    f"{doc_id}"
                                )
                        for stage in status_info.get("stages", []):
                            if stage.get("started_at") and isinstance(
                                stage["started_at"], str
                            ):
                                try:
                                    stage["started_at"] = datetime.fromisoformat(
                                        stage["started_at"]
                                    )
                                except ValueError:
                                    logger.warning(
                                        f"Invalid datetime format for started_at in {doc_id}"
                                    )
                    self.document_statuses = data
                    logger.info(
                        f"Loaded {len(self.document_statuses)} document statuses from persistent storage"
                    )
            else:
                logger.info(
                    "No persistent status file found, starting with empty status tracking"
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
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None,
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

            # Create document record (in real implementation, this would save to database)
            document_record = {
                "id": document_id,
                "filename": os.path.basename(file_path),
                "file_path": file_path,
                "file_type": validation_result["file_type"],
                "file_size": validation_result["file_size"],
                "document_type": document_type,
                "user_id": user_id,
                "status": ProcessingStage.UPLOADED,
                "metadata": metadata or {},
                "upload_timestamp": datetime.now(),
            }

            # Start document processing pipeline
            await self._start_document_processing(document_record)

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
            logger.error(f"Document upload failed: {_sanitize_log_data(str(e))}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to upload document",
            }

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
            logger.error(f"Failed to get document status: {_sanitize_log_data(str(e))}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to get document status",
            }

    async def extract_document_data(self, document_id: str) -> Dict[str, Any]:
        """Extract structured data from processed document."""
        try:
            logger.info(f"Extracting data from document: {_sanitize_log_data(document_id)}")
            
            # Verify document exists in status tracking
            if document_id not in self.document_statuses:
                logger.error(f"Document {document_id} not found in status tracking")
                return {
                    "success": False,
                    "message": f"Document {document_id} not found",
                    "extracted_data": {},
                }

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
            logger.error(f"Failed to extract document data: {_sanitize_log_data(str(e))}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to extract document data",
            }

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
            logger.error(f"Failed to validate document quality: {_sanitize_log_data(str(e))}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to validate document quality",
            }

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
            logger.error(f"Failed to search documents: {_sanitize_log_data(str(e))}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to search documents",
            }

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
            logger.error(f"Failed to get document analytics: {_sanitize_log_data(str(e))}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to get document analytics",
            }

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
            logger.error(f"Failed to approve document: {_sanitize_log_data(str(e))}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to approve document",
            }

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
            logger.error(f"Failed to reject document: {_sanitize_log_data(str(e))}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to reject document",
            }

    # Helper methods (mock implementations for now)
    async def _validate_document_file(self, file_path: str) -> Dict[str, Any]:
        """Validate document file."""
        if not os.path.exists(file_path):
            return {"valid": False, "error": "File does not exist"}

        file_size = os.path.getsize(file_path)
        if file_size > self.max_file_size:
            return {
                "valid": False,
                "error": f"File size exceeds {self.max_file_size} bytes",
            }

        file_ext = os.path.splitext(file_path)[1].lower().lstrip(".")
        if file_ext not in self.supported_file_types:
            return {"valid": False, "error": f"Unsupported file type: {file_ext}"}

        return {"valid": True, "file_type": file_ext, "file_size": file_size}

    async def _start_document_processing(
        self, document_record: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Start document processing pipeline."""
        # Mock implementation - in real implementation, this would start the actual pipeline
        return {
            "processing_started": True,
            "pipeline_id": str(uuid.uuid4()),
            "estimated_completion": datetime.now().timestamp()
            + 60,  # 60 seconds from now
        }

    async def _get_processing_status(self, document_id: str) -> Dict[str, Any]:
        """Get processing status - use actual status from document_statuses, not simulation."""
        logger.info(f"Getting processing status for document: {_sanitize_log_data(document_id)}")

        if document_id not in self.document_statuses:
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
                overall_status = ProcessingStage.ROUTING
                overall_status_str = "routing"
                status_info["status"] = ProcessingStage.ROUTING
                current_stage_name = "Finalizing"
                progress = 95
                self._save_status_data()

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
            if document_id in self.document_statuses:
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

                # Save to persistent storage
                self._save_status_data()
                logger.info(
                    f"Successfully stored processing results for document: {document_id}"
                )
            else:
                logger.error(f"Document {document_id} not found in status tracking")

        except Exception as e:
            logger.error(
                f"Failed to store processing results for {document_id}: {e}",
                exc_info=True,
            )
    
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
                serialized[key] = {
                    "_type": "PIL_Image_Reference",
                    "size": value.size,
                    "mode": value.mode,
                    "format": getattr(value, "format", "PNG"),
                    "note": "Image object converted to metadata for JSON serialization"
                }
            elif isinstance(value, list):
                # Handle lists that might contain PIL Images
                serialized[key] = [
                    {
                        "_type": "PIL_Image_Reference",
                        "size": item.size,
                        "mode": item.mode,
                        "format": getattr(item, "format", "PNG"),
                        "note": "Image object converted to metadata for JSON serialization"
                    } if isinstance(item, Image.Image) else item
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
            if document_id in self.document_statuses:
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
            if document_id in self.document_statuses:
                doc_status = self.document_statuses[document_id]

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
                                model_used=ocr_data.get(
                                    "model_used", "NeMoRetriever-OCR-v1"
                                ),
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
                                model_used="Llama Nemotron Nano VL 8B",
                                metadata=llm_data.get("metadata", {}),
                            )
                        )

                    # Quality Score from validation
                    quality_score = None
                    if "validation" in results and results["validation"]:
                        validation_data = results["validation"]

                        # Handle both JudgeEvaluation object and dictionary
                        if hasattr(validation_data, "overall_score"):
                            # It's a JudgeEvaluation object
                            reasoning_text = getattr(validation_data, "reasoning", "")
                            quality_score = QualityScore(
                                overall_score=getattr(
                                    validation_data, "overall_score", 0.0
                                ),
                                completeness_score=getattr(
                                    validation_data, "completeness_score", 0.0
                                ),
                                accuracy_score=getattr(
                                    validation_data, "accuracy_score", 0.0
                                ),
                                compliance_score=getattr(
                                    validation_data, "compliance_score", 0.0
                                ),
                                quality_score=getattr(
                                    validation_data,
                                    "quality_score",
                                    getattr(validation_data, "overall_score", 0.0),
                                ),
                                decision=QualityDecision(
                                    getattr(validation_data, "decision", "REVIEW")
                                ),
                                reasoning={
                                    "summary": reasoning_text,
                                    "details": reasoning_text,
                                },
                                issues_found=getattr(
                                    validation_data, "issues_found", []
                                ),
                                confidence=getattr(validation_data, "confidence", 0.0),
                                judge_model="Llama 3.1 Nemotron 70B",
                            )
                        else:
                            # It's a dictionary
                            reasoning_data = validation_data.get("reasoning", {})
                            if isinstance(reasoning_data, str):
                                reasoning_data = {
                                    "summary": reasoning_data,
                                    "details": reasoning_data,
                                }

                            quality_score = QualityScore(
                                overall_score=validation_data.get("overall_score", 0.0),
                                completeness_score=validation_data.get(
                                    "completeness_score", 0.0
                                ),
                                accuracy_score=validation_data.get(
                                    "accuracy_score", 0.0
                                ),
                                compliance_score=validation_data.get(
                                    "compliance_score", 0.0
                                ),
                                quality_score=validation_data.get(
                                    "quality_score",
                                    validation_data.get("overall_score", 0.0),
                                ),
                                decision=QualityDecision(
                                    validation_data.get("decision", "REVIEW")
                                ),
                                reasoning=reasoning_data,
                                issues_found=validation_data.get("issues_found", []),
                                confidence=validation_data.get("confidence", 0.0),
                                judge_model="Llama 3.1 Nemotron 70B",
                            )

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
            if document_id in self.document_statuses:
                doc_status = self.document_statuses[document_id]
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
                    return {
                        "extraction_results": [],
                        "confidence_scores": {},
                        "stages": [],
                        "quality_score": None,
                        "routing_decision": None,
                        "is_mock": True,
                        "reason": "processing_in_progress",
                        "message": "Document is still being processed by NVIDIA NeMo pipeline. Please check again in a moment."
                    }
                elif current_status == ProcessingStage.COMPLETED:
                    # Status says COMPLETED but no processing_results - this shouldn't happen
                    # but if it does, wait a bit and check again (race condition)
                    logger.warning(f"Document {_sanitize_log_data(document_id)} status is COMPLETED but no processing_results found. This may be a race condition.")
                    return {
                        "extraction_results": [],
                        "confidence_scores": {},
                        "stages": [],
                        "quality_score": None,
                        "routing_decision": None,
                        "is_mock": True,
                        "reason": "results_not_ready",
                        "message": "Processing completed but results are not ready yet. Please check again in a moment."
                    }
                elif current_status == ProcessingStage.FAILED:
                    # Processing failed
                    error_msg = doc_status.get("error_message", "Unknown error")
                    logger.warning(f"Document {_sanitize_log_data(document_id)} processing failed: {_sanitize_log_data(error_msg)}")
                    return {
                        "extraction_results": [],
                        "confidence_scores": {},
                        "stages": [],
                        "quality_score": None,
                        "routing_decision": None,
                        "is_mock": True,
                        "reason": "processing_failed",
                        "message": f"Document processing failed: {error_msg}"
                    }
                else:
                    logger.warning(f"Document {_sanitize_log_data(document_id)} has no processing results and status is {_sanitize_log_data(str(current_status))}. NeMo pipeline may have failed.")
                    # Return mock data with clear indication that NeMo pipeline didn't complete
                    mock_data = self._get_mock_extraction_data()
                    mock_data["is_mock"] = True
                    mock_data["reason"] = "nemo_pipeline_incomplete"
                    mock_data["message"] = "NVIDIA NeMo pipeline did not complete processing. Please check server logs for errors."
                    return mock_data
            else:
                logger.error(f"Document {document_id} not found in status tracking")
                mock_data = self._get_mock_extraction_data()
                mock_data["is_mock"] = True
                mock_data["reason"] = "document_not_found"
                return mock_data

        except Exception as e:
            logger.error(
                f"Failed to get extraction data for {document_id}: {e}", exc_info=True
            )
            return self._get_mock_extraction_data()

    async def _process_document_locally(self, document_id: str) -> Dict[str, Any]:
        """Process document locally using the local processor."""
        try:
            # Get document info from status
            if document_id not in self.document_statuses:
                logger.error(f"Document {document_id} not found in status tracking")
                return {**self._get_mock_extraction_data(), "is_mock": True}
            
            doc_status = self.document_statuses[document_id]
            file_path = doc_status.get("file_path")
            
            if not file_path or not os.path.exists(file_path):
                logger.warning(f"File not found for document {_sanitize_log_data(document_id)}: {_sanitize_log_data(file_path)}")
                logger.info(f"Attempting to use document filename: {_sanitize_log_data(doc_status.get('filename', 'N/A'))}")
                # Return mock data but mark it as such
                return {**self._get_mock_extraction_data(), "is_mock": True, "reason": "file_not_found"}
            
            # Try to process the document locally
            try:
                from .processing.local_processor import local_processor
                result = await local_processor.process_document(file_path, doc_status.get("document_type", "invoice"))
                
                if not result["success"]:
                    logger.error(f"Local processing failed for {_sanitize_log_data(document_id)}: {_sanitize_log_data(str(result.get('error', 'Unknown error')))}")
                    return {**self._get_mock_extraction_data(), "is_mock": True, "reason": "processing_failed"}
            except ImportError as e:
                logger.warning(f"Local processor not available (missing dependencies): {_sanitize_log_data(str(e))}")
                missing_module = str(e).replace("No module named ", "").strip("'\"")
                if "fitz" in missing_module.lower() or "pymupdf" in missing_module.lower():
                    logger.info("Install PyMuPDF for PDF processing: pip install PyMuPDF")
                elif "PIL" in missing_module or "Pillow" in missing_module:
                    logger.info("Install Pillow (PIL) for image processing: pip install Pillow")
                else:
                    logger.info(f"Install missing dependency: pip install {_sanitize_log_data(missing_module)}")
                return {**self._get_mock_extraction_data(), "is_mock": True, "reason": "dependencies_missing"}
            except Exception as e:
                logger.error(f"Local processing error for {_sanitize_log_data(document_id)}: {_sanitize_log_data(str(e))}")
                return {**self._get_mock_extraction_data(), "is_mock": True, "reason": "processing_error"}
            
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
            return {**self._get_mock_extraction_data(), "is_mock": True, "reason": "exception"}

    def _get_mock_extraction_data(self) -> Dict[str, Any]:
        """Fallback mock extraction data that matches the expected API response format."""
        from .models.document_models import (
            ExtractionResult,
            QualityScore,
            RoutingDecision,
            QualityDecision,
        )
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
        for i in range(num_items):
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
                    model_used="NeMoRetriever-OCR-v1",
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
                    model_used="Llama Nemotron Nano VL 8B",
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
                judge_model="Llama 3.1 Nemotron 70B",
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
            # Calculate metrics from actual document_statuses
            total_documents = len(self.document_statuses)
            
            # Filter documents by time range
            now = datetime.now()
            today_start = datetime(now.year, now.month, now.day)
            
            if time_range == "today":
                time_threshold = today_start
            elif time_range == "week":
                from datetime import timedelta
                time_threshold = now - timedelta(days=7)
            elif time_range == "month":
                from datetime import timedelta
                time_threshold = now - timedelta(days=30)
            else:
                time_threshold = datetime.min  # All time
            
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
                                    # Check for overall_score directly (this is the main field from JudgeEvaluation)
                                    quality = validation.get("overall_score", 0.0)
                                    
                                    # If not found, check for quality_score field
                                    if quality == 0.0:
                                        quality = validation.get("quality_score", 0.0)
                                    
                                    # If still not found, check nested structures
                                    if quality == 0.0 and "quality_score" in validation:
                                        qs = validation["quality_score"]
                                        if isinstance(qs, dict):
                                            quality = qs.get("overall_score", 0.0)
                                    
                                    # Check if validation contains a QualityScore object (after serialization)
                                    if quality == 0.0:
                                        # Try to find any score field
                                        for key in ["overall_score", "quality_score", "score"]:
                                            if key in validation:
                                                val = validation[key]
                                                if isinstance(val, (int, float)) and val > 0:
                                                    quality = float(val)
                                                    break
                                    
                                    logger.debug(f"Extracted quality score from validation dict: {quality} for doc {_sanitize_log_data(doc_id)}")
                                    
                                elif hasattr(validation, "overall_score"):
                                    # It's an object with overall_score attribute (JudgeEvaluation dataclass)
                                    quality = getattr(validation, "overall_score", 0.0)
                                    logger.debug(f"Extracted quality score from validation object: {quality} for doc {_sanitize_log_data(doc_id)}")
                                elif hasattr(validation, "quality_score"):
                                    # It's an object with quality_score attribute
                                    quality = getattr(validation, "quality_score", 0.0)
                                    logger.debug(f"Extracted quality score from validation object (quality_score): {quality} for doc {_sanitize_log_data(doc_id)}")
                                else:
                                    logger.debug(f"Validation result for doc {_sanitize_log_data(doc_id)} is not a dict or object with score attributes. Type: {type(validation)}")
                            
                            # If still no quality score found, try to get it from extraction data
                            if quality == 0.0:
                                try:
                                    extraction_data = await self._get_extraction_data(doc_id)
                                    if extraction_data and "quality_score" in extraction_data:
                                        qs = extraction_data["quality_score"]
                                        if hasattr(qs, "overall_score"):
                                            quality = qs.overall_score
                                        elif isinstance(qs, dict):
                                            quality = qs.get("overall_score", 0.0)
                                except Exception as e:
                                    logger.debug(f"Could not extract quality score from extraction data for {_sanitize_log_data(doc_id)}: {_sanitize_log_data(str(e))}")
                            
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
            
            # Generate daily processing trend (last 5 days)
            from datetime import timedelta
            daily_processing_list = []
            for i in range(5):
                day = (now - timedelta(days=4-i)).strftime("%Y-%m-%d")
                daily_processing_list.append(daily_processing.get(day, 0))
            
            # Generate quality trends (last 5 documents with quality scores)
            quality_trends_list = quality_scores[-5:] if len(quality_scores) >= 5 else quality_scores
            # Pad with average if less than 5
            while len(quality_trends_list) < 5:
                quality_trends_list.insert(0, average_quality if average_quality > 0 else 4.2)
            
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
            # Fallback to mock data if calculation fails
            return {
                "metrics": {
                    "total_documents": len(self.document_statuses),
                    "processed_today": 0,
                    "average_quality": 0.0,
                    "auto_approved": 0.0,
                    "success_rate": 0.0,
                },
                "trends": {
                    "daily_processing": [0, 0, 0, 0, 0],
                    "quality_trends": [0.0, 0.0, 0.0, 0.0, 0.0],
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
