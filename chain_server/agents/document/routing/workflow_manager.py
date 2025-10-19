"""
Workflow Manager for Document Processing
Orchestrates the complete document processing workflow and manages state.
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import uuid
from dataclasses import dataclass

from chain_server.agents.document.models.document_models import (
    ProcessingStage,
    ProcessingStatus,
    RoutingAction,
    QualityDecision,
)

logger = logging.getLogger(__name__)


@dataclass
class WorkflowState:
    """Represents the state of a document processing workflow."""

    workflow_id: str
    document_id: str
    current_stage: ProcessingStage
    status: ProcessingStatus
    stages_completed: List[ProcessingStage]
    stages_pending: List[ProcessingStage]
    progress_percentage: float
    start_time: datetime
    last_updated: datetime
    metadata: Dict[str, Any]
    errors: List[str]


class WorkflowManager:
    """
    Workflow Manager for document processing.

    Responsibilities:
    - Orchestrate the complete 6-stage pipeline
    - Manage workflow state and transitions
    - Handle error recovery and retries
    - Provide progress tracking and monitoring
    - Coordinate between different processing stages
    """

    def __init__(self):
        self.active_workflows: Dict[str, WorkflowState] = {}
        self.workflow_history: List[WorkflowState] = []

        # Define the complete pipeline stages
        self.pipeline_stages = [
            ProcessingStage.PREPROCESSING,
            ProcessingStage.OCR_EXTRACTION,
            ProcessingStage.LLM_PROCESSING,
            ProcessingStage.EMBEDDING,
            ProcessingStage.VALIDATION,
            ProcessingStage.ROUTING,
        ]

    async def initialize(self):
        """Initialize the workflow manager."""
        logger.info("Workflow Manager initialized successfully")

    async def start_workflow(
        self,
        document_id: str,
        document_type: str,
        user_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> WorkflowState:
        """
        Start a new document processing workflow.

        Args:
            document_id: Unique document identifier
            document_type: Type of document
            user_id: ID of the user uploading the document
            metadata: Additional metadata

        Returns:
            Initial workflow state
        """
        try:
            workflow_id = str(uuid.uuid4())

            workflow_state = WorkflowState(
                workflow_id=workflow_id,
                document_id=document_id,
                current_stage=ProcessingStage.PREPROCESSING,
                status=ProcessingStatus.PENDING,
                stages_completed=[],
                stages_pending=self.pipeline_stages.copy(),
                progress_percentage=0.0,
                start_time=datetime.now(),
                last_updated=datetime.now(),
                metadata={
                    "document_type": document_type,
                    "user_id": user_id,
                    "metadata": metadata or {},
                },
                errors=[],
            )

            self.active_workflows[workflow_id] = workflow_state

            logger.info(f"Started workflow {workflow_id} for document {document_id}")
            return workflow_state

        except Exception as e:
            logger.error(f"Failed to start workflow: {e}")
            raise

    async def update_workflow_stage(
        self,
        workflow_id: str,
        stage: ProcessingStage,
        status: ProcessingStatus,
        metadata: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> WorkflowState:
        """
        Update workflow stage and status.

        Args:
            workflow_id: Workflow identifier
            stage: Current processing stage
            status: Current status
            metadata: Additional metadata
            error: Error message if any

        Returns:
            Updated workflow state
        """
        try:
            if workflow_id not in self.active_workflows:
                raise ValueError(f"Workflow {workflow_id} not found")

            workflow_state = self.active_workflows[workflow_id]

            # Update stage
            workflow_state.current_stage = stage
            workflow_state.status = status
            workflow_state.last_updated = datetime.now()

            # Add to completed stages if not already there
            if stage not in workflow_state.stages_completed:
                workflow_state.stages_completed.append(stage)

            # Remove from pending stages
            if stage in workflow_state.stages_pending:
                workflow_state.stages_pending.remove(stage)

            # Update metadata
            if metadata:
                workflow_state.metadata.update(metadata)

            # Add error if present
            if error:
                workflow_state.errors.append(error)

            # Calculate progress percentage
            workflow_state.progress_percentage = (
                len(workflow_state.stages_completed) / len(self.pipeline_stages) * 100
            )

            logger.info(
                f"Updated workflow {workflow_id} to stage {stage.value} ({workflow_state.progress_percentage:.1f}% complete)"
            )

            return workflow_state

        except Exception as e:
            logger.error(f"Failed to update workflow stage: {e}")
            raise

    async def complete_workflow(
        self,
        workflow_id: str,
        final_status: ProcessingStatus,
        final_metadata: Optional[Dict[str, Any]] = None,
    ) -> WorkflowState:
        """
        Complete a workflow and move it to history.

        Args:
            workflow_id: Workflow identifier
            final_status: Final status of the workflow
            final_metadata: Final metadata

        Returns:
            Completed workflow state
        """
        try:
            if workflow_id not in self.active_workflows:
                raise ValueError(f"Workflow {workflow_id} not found")

            workflow_state = self.active_workflows[workflow_id]

            # Update final status
            workflow_state.status = final_status
            workflow_state.last_updated = datetime.now()
            workflow_state.progress_percentage = 100.0

            # Add final metadata
            if final_metadata:
                workflow_state.metadata.update(final_metadata)

            # Move to history
            self.workflow_history.append(workflow_state)
            del self.active_workflows[workflow_id]

            logger.info(f"Completed workflow {workflow_id} with status {final_status}")
            return workflow_state

        except Exception as e:
            logger.error(f"Failed to complete workflow: {e}")
            raise

    async def get_workflow_status(self, workflow_id: str) -> Optional[WorkflowState]:
        """Get current workflow status."""
        return self.active_workflows.get(workflow_id)

    async def get_workflow_history(
        self, document_id: Optional[str] = None
    ) -> List[WorkflowState]:
        """Get workflow history, optionally filtered by document ID."""
        if document_id:
            return [w for w in self.workflow_history if w.document_id == document_id]
        return self.workflow_history.copy()

    async def get_active_workflows(self) -> List[WorkflowState]:
        """Get all active workflows."""
        return list(self.active_workflows.values())

    async def retry_workflow_stage(
        self, workflow_id: str, stage: ProcessingStage, max_retries: int = 3
    ) -> bool:
        """
        Retry a failed workflow stage.

        Args:
            workflow_id: Workflow identifier
            stage: Stage to retry
            max_retries: Maximum number of retries

        Returns:
            True if retry was successful
        """
        try:
            if workflow_id not in self.active_workflows:
                return False

            workflow_state = self.active_workflows[workflow_id]

            # Check retry count
            retry_key = f"retry_count_{stage.value}"
            retry_count = workflow_state.metadata.get(retry_key, 0)

            if retry_count >= max_retries:
                logger.warning(
                    f"Maximum retries exceeded for workflow {workflow_id}, stage {stage.value}"
                )
                return False

            # Increment retry count
            workflow_state.metadata[retry_key] = retry_count + 1

            # Reset stage status
            workflow_state.status = ProcessingStatus.PENDING
            workflow_state.last_updated = datetime.now()

            logger.info(
                f"Retrying workflow {workflow_id}, stage {stage.value} (attempt {retry_count + 1})"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to retry workflow stage: {e}")
            return False

    async def cancel_workflow(self, workflow_id: str, reason: str) -> bool:
        """
        Cancel an active workflow.

        Args:
            workflow_id: Workflow identifier
            reason: Reason for cancellation

        Returns:
            True if cancellation was successful
        """
        try:
            if workflow_id not in self.active_workflows:
                return False

            workflow_state = self.active_workflows[workflow_id]

            # Update status
            workflow_state.status = ProcessingStatus.FAILED
            workflow_state.last_updated = datetime.now()
            workflow_state.errors.append(f"Workflow cancelled: {reason}")

            # Move to history
            self.workflow_history.append(workflow_state)
            del self.active_workflows[workflow_id]

            logger.info(f"Cancelled workflow {workflow_id}: {reason}")
            return True

        except Exception as e:
            logger.error(f"Failed to cancel workflow: {e}")
            return False

    async def get_workflow_statistics(self) -> Dict[str, Any]:
        """Get workflow statistics for monitoring."""
        try:
            active_count = len(self.active_workflows)
            completed_count = len(self.workflow_history)

            # Calculate stage distribution
            stage_counts = {}
            for stage in self.pipeline_stages:
                stage_counts[stage.value] = sum(
                    1
                    for w in self.active_workflows.values()
                    if w.current_stage == stage
                )

            # Calculate average processing time
            avg_processing_time = 0.0
            if self.workflow_history:
                total_time = sum(
                    (w.last_updated - w.start_time).total_seconds()
                    for w in self.workflow_history
                )
                avg_processing_time = total_time / len(self.workflow_history)

            # Calculate success rate
            successful_workflows = sum(
                1
                for w in self.workflow_history
                if w.status == ProcessingStatus.COMPLETED
            )
            success_rate = (
                successful_workflows / len(self.workflow_history) * 100
                if self.workflow_history
                else 0.0
            )

            return {
                "active_workflows": active_count,
                "completed_workflows": completed_count,
                "stage_distribution": stage_counts,
                "average_processing_time_seconds": avg_processing_time,
                "success_rate_percentage": success_rate,
                "last_updated": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error(f"Failed to get workflow statistics: {e}")
            return {}

    async def cleanup_old_workflows(self, max_age_hours: int = 24) -> int:
        """
        Clean up old completed workflows.

        Args:
            max_age_hours: Maximum age in hours for completed workflows

        Returns:
            Number of workflows cleaned up
        """
        try:
            cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)

            # Count workflows to be cleaned up
            workflows_to_remove = [
                w
                for w in self.workflow_history
                if w.last_updated.timestamp() < cutoff_time
            ]

            # Remove old workflows
            self.workflow_history = [
                w
                for w in self.workflow_history
                if w.last_updated.timestamp() >= cutoff_time
            ]

            logger.info(f"Cleaned up {len(workflows_to_remove)} old workflows")
            return len(workflows_to_remove)

        except Exception as e:
            logger.error(f"Failed to cleanup old workflows: {e}")
            return 0

    async def get_workflow_progress(self, workflow_id: str) -> Dict[str, Any]:
        """Get detailed progress information for a workflow."""
        try:
            if workflow_id not in self.active_workflows:
                return {"error": "Workflow not found"}

            workflow_state = self.active_workflows[workflow_id]

            return {
                "workflow_id": workflow_id,
                "document_id": workflow_state.document_id,
                "current_stage": workflow_state.current_stage.value,
                "status": workflow_state.status.value,
                "progress_percentage": workflow_state.progress_percentage,
                "stages_completed": [
                    stage.value for stage in workflow_state.stages_completed
                ],
                "stages_pending": [
                    stage.value for stage in workflow_state.stages_pending
                ],
                "start_time": workflow_state.start_time.isoformat(),
                "last_updated": workflow_state.last_updated.isoformat(),
                "estimated_completion": self._estimate_completion_time(workflow_state),
                "errors": workflow_state.errors,
            }

        except Exception as e:
            logger.error(f"Failed to get workflow progress: {e}")
            return {"error": str(e)}

    def _estimate_completion_time(self, workflow_state: WorkflowState) -> Optional[str]:
        """Estimate completion time based on current progress."""
        try:
            if workflow_state.progress_percentage == 0:
                return "Unknown"

            # Calculate average time per stage
            elapsed_time = (
                workflow_state.last_updated - workflow_state.start_time
            ).total_seconds()
            stages_completed = len(workflow_state.stages_completed)

            if stages_completed == 0:
                return "Unknown"

            avg_time_per_stage = elapsed_time / stages_completed
            remaining_stages = len(workflow_state.stages_pending)
            estimated_remaining_time = remaining_stages * avg_time_per_stage

            # Convert to human readable format
            if estimated_remaining_time < 60:
                return f"{int(estimated_remaining_time)} seconds"
            elif estimated_remaining_time < 3600:
                return f"{int(estimated_remaining_time / 60)} minutes"
            else:
                return f"{int(estimated_remaining_time / 3600)} hours"

        except Exception:
            return "Unknown"
