"""
Safety & Compliance Agent Action Tools

Provides comprehensive action tools for safety management including:
- Incident logging and SIEM integration
- Safety checklist management
- Alert broadcasting and notifications
- Lockout/Tagout procedures
- Corrective action tracking
- Safety Data Sheet retrieval
- Near-miss capture and reporting
"""

import logging
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import asyncio
import json
import uuid

from chain_server.services.llm.nim_client import get_nim_client
from chain_server.services.iot.integration_service import get_iot_service
from chain_server.services.erp.integration_service import get_erp_service

logger = logging.getLogger(__name__)


@dataclass
class SafetyIncident:
    """Safety incident details."""

    incident_id: str
    severity: str
    description: str
    location: str
    reporter: str
    attachments: List[str]
    status: str
    created_at: datetime
    updated_at: datetime
    siem_event_id: Optional[str] = None
    assigned_to: Optional[str] = None
    resolution_notes: Optional[str] = None


@dataclass
class SafetyChecklist:
    """Safety checklist details."""

    checklist_id: str
    checklist_type: str
    assignee: str
    due_date: datetime
    status: str
    items: List[Dict[str, Any]]
    completed_items: List[Dict[str, Any]]
    created_at: datetime
    completed_at: Optional[datetime] = None
    supervisor_approval: Optional[str] = None


@dataclass
class SafetyAlert:
    """Safety alert details."""

    alert_id: str
    message: str
    zone: str
    channels: List[str]
    priority: str
    status: str
    created_at: datetime
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    escalation_level: int = 1


@dataclass
class LockoutTagoutRequest:
    """Lockout/Tagout request details."""

    loto_id: str
    asset_id: str
    reason: str
    requester: str
    status: str
    created_at: datetime
    maintenance_ticket_id: Optional[str] = None
    authorized_by: Optional[str] = None
    authorized_at: Optional[datetime] = None
    lockout_devices: List[str] = None
    isolation_points: List[str] = None


@dataclass
class CorrectiveAction:
    """Corrective action details."""

    action_id: str
    incident_id: str
    action_owner: str
    description: str
    due_date: datetime
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None
    completion_notes: Optional[str] = None
    verification_required: bool = True


@dataclass
class SafetyDataSheet:
    """Safety Data Sheet details."""

    sds_id: str
    chemical_name: str
    cas_number: str
    hazard_classification: List[str]
    handling_precautions: List[str]
    emergency_procedures: List[str]
    ppe_requirements: List[str]
    storage_requirements: List[str]
    created_at: datetime
    last_updated: datetime


@dataclass
class NearMissReport:
    """Near-miss report details."""

    report_id: str
    description: str
    zone: str
    reporter: str
    severity: str
    status: str
    created_at: datetime
    photos: List[str] = None
    geotag: Optional[Dict[str, float]] = None
    follow_up_required: bool = False
    follow_up_notes: Optional[str] = None


class SafetyActionTools:
    """
    Action tools for Safety & Compliance Agent.

    Provides comprehensive safety management capabilities including:
    - Incident logging and SIEM integration
    - Safety checklist management
    - Alert broadcasting and notifications
    - Lockout/Tagout procedures
    - Corrective action tracking
    - Safety Data Sheet retrieval
    - Near-miss capture and reporting
    """

    def __init__(self):
        self.nim_client = None
        self.iot_service = None
        self.erp_service = None

    async def initialize(self) -> None:
        """Initialize action tools with required services."""
        try:
            self.nim_client = await get_nim_client()
            self.iot_service = await get_iot_service()
            self.erp_service = await get_erp_service()
            logger.info("Safety Action Tools initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Safety Action Tools: {e}")
            raise

    async def log_incident(
        self,
        severity: str,
        description: str,
        location: str,
        reporter: str,
        attachments: Optional[List[str]] = None,
    ) -> SafetyIncident:
        """
        Log a safety incident and create SIEM event.

        Args:
            severity: Incident severity (low, medium, high, critical)
            description: Detailed incident description
            location: Location where incident occurred
            reporter: Person reporting the incident
            attachments: Optional list of attachment URLs

        Returns:
            SafetyIncident with incident details
        """
        try:
            if not self.iot_service:
                await self.initialize()

            # Generate unique incident ID
            incident_id = f"INC_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Create incident record
            incident = SafetyIncident(
                incident_id=incident_id,
                severity=severity,
                description=description,
                location=location,
                reporter=reporter,
                attachments=attachments or [],
                status="open",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )

            # Create SIEM event
            siem_event = await self._create_siem_event(incident)
            if siem_event:
                incident.siem_event_id = siem_event.get("event_id")

            # Store incident in database
            await self._store_incident(incident)

            # Auto-assign based on severity
            if severity in ["high", "critical"]:
                incident.assigned_to = await self._get_safety_manager()
                incident.status = "assigned"

            # Send notifications
            await self._notify_safety_team(incident)

            return incident

        except Exception as e:
            logger.error(f"Failed to log incident: {e}")
            return SafetyIncident(
                incident_id=f"INC_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                severity=severity,
                description=description,
                location=location,
                reporter=reporter,
                attachments=attachments or [],
                status="error",
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )

    async def start_checklist(
        self, checklist_type: str, assignee: str, due_in: int = 24  # hours
    ) -> SafetyChecklist:
        """
        Start a safety checklist.

        Args:
            checklist_type: Type of checklist (forklift_pre_op, PPE, LOTO, etc.)
            assignee: Person assigned to complete checklist
            due_in: Hours until due (default 24)

        Returns:
            SafetyChecklist with checklist details
        """
        try:
            checklist_id = f"CHK_{checklist_type.upper()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Get checklist template
            checklist_items = await self._get_checklist_template(checklist_type)

            # Create checklist
            checklist = SafetyChecklist(
                checklist_id=checklist_id,
                checklist_type=checklist_type,
                assignee=assignee,
                due_date=datetime.now() + timedelta(hours=due_in),
                status="pending",
                items=checklist_items,
                completed_items=[],
                created_at=datetime.now(),
            )

            # Store checklist
            await self._store_checklist(checklist)

            # Notify assignee
            await self._notify_checklist_assignment(checklist)

            return checklist

        except Exception as e:
            logger.error(f"Failed to start checklist: {e}")
            return SafetyChecklist(
                checklist_id=f"CHK_{checklist_type.upper()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                checklist_type=checklist_type,
                assignee=assignee,
                due_date=datetime.now() + timedelta(hours=due_in),
                status="error",
                items=[],
                completed_items=[],
                created_at=datetime.now(),
            )

    async def broadcast_alert(
        self, message: str, zone: str, channels: List[str]
    ) -> SafetyAlert:
        """
        Broadcast safety alert to multiple channels.

        Args:
            message: Alert message
            zone: Zone to broadcast to
            channels: List of channels (PA, Teams/Slack, SMS)

        Returns:
            SafetyAlert with alert details
        """
        try:
            alert_id = f"ALERT_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Determine priority based on message content
            priority = self._determine_alert_priority(message)

            # Create alert
            alert = SafetyAlert(
                alert_id=alert_id,
                message=message,
                zone=zone,
                channels=channels,
                priority=priority,
                status="broadcasting",
                created_at=datetime.now(),
            )

            # Broadcast to each channel
            for channel in channels:
                await self._broadcast_to_channel(alert, channel)

            alert.status = "broadcast"

            # Store alert
            await self._store_alert(alert)

            return alert

        except Exception as e:
            logger.error(f"Failed to broadcast alert: {e}")
            return SafetyAlert(
                alert_id=f"ALERT_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                message=message,
                zone=zone,
                channels=channels,
                priority="medium",
                status="error",
                created_at=datetime.now(),
            )

    async def lockout_tagout_request(
        self, asset_id: str, reason: str, requester: str
    ) -> LockoutTagoutRequest:
        """
        Create lockout/tagout request and open maintenance ticket.

        Args:
            asset_id: ID of the asset to lockout
            reason: Reason for lockout
            requester: Person requesting lockout

        Returns:
            LockoutTagoutRequest with LOTO details
        """
        try:
            loto_id = f"LOTO_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Create LOTO request
            loto_request = LockoutTagoutRequest(
                loto_id=loto_id,
                asset_id=asset_id,
                reason=reason,
                requester=requester,
                status="pending",
                created_at=datetime.now(),
                lockout_devices=[],
                isolation_points=[],
            )

            # Open maintenance ticket in CMMS
            if self.erp_service:
                maintenance_ticket = await self.erp_service.create_maintenance_ticket(
                    asset_id=asset_id,
                    issue_description=f"LOTO Request: {reason}",
                    priority="high",
                    requester=requester,
                )
                if maintenance_ticket:
                    loto_request.maintenance_ticket_id = maintenance_ticket.get(
                        "ticket_id"
                    )

            # Store LOTO request
            await self._store_loto_request(loto_request)

            # Notify maintenance team
            await self._notify_maintenance_team(loto_request)

            return loto_request

        except Exception as e:
            logger.error(f"Failed to create LOTO request: {e}")
            return LockoutTagoutRequest(
                loto_id=f"LOTO_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                asset_id=asset_id,
                reason=reason,
                requester=requester,
                status="error",
                created_at=datetime.now(),
            )

    async def create_corrective_action(
        self, incident_id: str, action_owner: str, description: str, due_date: datetime
    ) -> CorrectiveAction:
        """
        Create corrective action linked to incident.

        Args:
            incident_id: ID of the incident
            action_owner: Person responsible for the action
            description: Action description
            due_date: Due date for completion

        Returns:
            CorrectiveAction with action details
        """
        try:
            action_id = f"CA_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Create corrective action
            corrective_action = CorrectiveAction(
                action_id=action_id,
                incident_id=incident_id,
                action_owner=action_owner,
                description=description,
                due_date=due_date,
                status="pending",
                created_at=datetime.now(),
            )

            # Store corrective action
            await self._store_corrective_action(corrective_action)

            # Notify action owner
            await self._notify_action_owner(corrective_action)

            return corrective_action

        except Exception as e:
            logger.error(f"Failed to create corrective action: {e}")
            return CorrectiveAction(
                action_id=f"CA_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                incident_id=incident_id,
                action_owner=action_owner,
                description=description,
                due_date=due_date,
                status="error",
                created_at=datetime.now(),
            )

    async def retrieve_sds(
        self, chemical_name: str, assignee: Optional[str] = None
    ) -> SafetyDataSheet:
        """
        Retrieve Safety Data Sheet and send micro-training.

        Args:
            chemical_name: Name of the chemical
            assignee: Optional person to send training to

        Returns:
            SafetyDataSheet with SDS details
        """
        try:
            sds_id = f"SDS_{chemical_name.upper().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}"

            # Retrieve SDS from database or external system
            sds_data = await self._retrieve_sds_data(chemical_name)

            # Create SDS object
            sds = SafetyDataSheet(
                sds_id=sds_id,
                chemical_name=chemical_name,
                cas_number=sds_data.get("cas_number", ""),
                hazard_classification=sds_data.get("hazard_classification", []),
                handling_precautions=sds_data.get("handling_precautions", []),
                emergency_procedures=sds_data.get("emergency_procedures", []),
                ppe_requirements=sds_data.get("ppe_requirements", []),
                storage_requirements=sds_data.get("storage_requirements", []),
                created_at=datetime.now(),
                last_updated=datetime.now(),
            )

            # Send micro-training if assignee specified
            if assignee:
                await self._send_micro_training(sds, assignee)

            return sds

        except Exception as e:
            logger.error(f"Failed to retrieve SDS: {e}")
            return SafetyDataSheet(
                sds_id=f"SDS_{chemical_name.upper().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}",
                chemical_name=chemical_name,
                cas_number="",
                hazard_classification=[],
                handling_precautions=[],
                emergency_procedures=[],
                ppe_requirements=[],
                storage_requirements=[],
                created_at=datetime.now(),
                last_updated=datetime.now(),
            )

    async def near_miss_capture(
        self, description: str, zone: str, reporter: str, severity: str = "medium"
    ) -> NearMissReport:
        """
        Capture near-miss report with photo upload and geotagging.

        Args:
            description: Description of the near-miss
            zone: Zone where near-miss occurred
            reporter: Person reporting the near-miss
            severity: Severity level (low, medium, high)

        Returns:
            NearMissReport with report details
        """
        try:
            report_id = f"NM_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Create near-miss report
            near_miss = NearMissReport(
                report_id=report_id,
                description=description,
                zone=zone,
                reporter=reporter,
                severity=severity,
                status="open",
                created_at=datetime.now(),
                photos=[],
                geotag=None,
            )

            # Store near-miss report
            await self._store_near_miss(near_miss)

            # Send photo upload reminder
            await self._send_photo_upload_reminder(near_miss)

            # Notify safety team
            await self._notify_safety_team_near_miss(near_miss)

            return near_miss

        except Exception as e:
            logger.error(f"Failed to capture near-miss: {e}")
            return NearMissReport(
                report_id=f"NM_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                description=description,
                zone=zone,
                reporter=reporter,
                severity=severity,
                status="error",
                created_at=datetime.now(),
            )

    async def get_safety_procedures(
        self, procedure_type: Optional[str] = None, category: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retrieve comprehensive safety procedures and policies.

        Args:
            procedure_type: Specific procedure type (e.g., "emergency", "equipment", "ppe")
            category: Safety category (e.g., "general", "equipment", "chemical", "emergency")

        Returns:
            Dict containing safety procedures and policies
        """
        try:
            # Get comprehensive safety procedures
            procedures = await self._get_comprehensive_safety_procedures(
                procedure_type, category
            )

            return {
                "procedures": procedures,
                "total_count": len(procedures),
                "last_updated": datetime.now().isoformat(),
                "categories": list(
                    set([p.get("category", "General") for p in procedures])
                ),
            }

        except Exception as e:
            logger.error(f"Failed to get safety procedures: {e}")
            return {
                "procedures": [],
                "total_count": 0,
                "error": str(e),
                "last_updated": datetime.now().isoformat(),
            }

    # Helper methods
    async def _create_siem_event(
        self, incident: SafetyIncident
    ) -> Optional[Dict[str, Any]]:
        """Create SIEM event for incident."""
        try:
            # Simulate SIEM event creation
            return {
                "event_id": f"SIEM_{incident.incident_id}",
                "severity": incident.severity,
                "timestamp": incident.created_at.isoformat(),
                "source": "safety_system",
            }
        except Exception as e:
            logger.error(f"Failed to create SIEM event: {e}")
            return None

    async def _store_incident(self, incident: SafetyIncident) -> bool:
        """Store incident in database."""
        try:
            # Simulate database storage
            logger.info(f"Stored incident {incident.incident_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to store incident: {e}")
            return False

    async def _get_safety_manager(self) -> str:
        """Get safety manager for assignment."""
        return "safety_manager_001"

    async def _notify_safety_team(self, incident: SafetyIncident) -> bool:
        """Notify safety team of incident."""
        try:
            logger.info(f"Notified safety team of incident {incident.incident_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to notify safety team: {e}")
            return False

    async def _get_checklist_template(
        self, checklist_type: str
    ) -> List[Dict[str, Any]]:
        """Get checklist template based on type."""
        templates = {
            "forklift_pre_op": [
                {"item": "Check hydraulic fluid levels", "required": True},
                {"item": "Inspect tires and wheels", "required": True},
                {"item": "Test brakes and steering", "required": True},
                {"item": "Check safety equipment", "required": True},
            ],
            "PPE": [
                {"item": "Hard hat inspection", "required": True},
                {"item": "Safety glasses check", "required": True},
                {"item": "Steel-toed boots verification", "required": True},
                {"item": "High-visibility vest check", "required": True},
            ],
            "LOTO": [
                {"item": "Identify energy sources", "required": True},
                {"item": "Shut down equipment", "required": True},
                {"item": "Isolate energy sources", "required": True},
                {"item": "Apply lockout devices", "required": True},
                {"item": "Test isolation", "required": True},
            ],
        }
        return templates.get(checklist_type, [])

    async def _store_checklist(self, checklist: SafetyChecklist) -> bool:
        """Store checklist in database."""
        try:
            logger.info(f"Stored checklist {checklist.checklist_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to store checklist: {e}")
            return False

    async def _notify_checklist_assignment(self, checklist: SafetyChecklist) -> bool:
        """Notify assignee of checklist assignment."""
        try:
            logger.info(
                f"Notified {checklist.assignee} of checklist {checklist.checklist_id}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to notify checklist assignment: {e}")
            return False

    def _determine_alert_priority(self, message: str) -> str:
        """Determine alert priority based on message content."""
        message_lower = message.lower()
        if any(
            word in message_lower
            for word in ["emergency", "evacuate", "critical", "immediate"]
        ):
            return "critical"
        elif any(
            word in message_lower for word in ["urgent", "hazard", "danger", "stop"]
        ):
            return "high"
        elif any(word in message_lower for word in ["caution", "warning", "attention"]):
            return "medium"
        else:
            return "low"

    async def _broadcast_to_channel(self, alert: SafetyAlert, channel: str) -> bool:
        """Broadcast alert to specific channel."""
        try:
            if channel == "PA":
                logger.info(f"Broadcasting to PA system: {alert.message}")
            elif channel in ["Teams", "Slack"]:
                logger.info(f"Broadcasting to {channel}: {alert.message}")
            elif channel == "SMS":
                logger.info(f"Broadcasting via SMS: {alert.message}")
            return True
        except Exception as e:
            logger.error(f"Failed to broadcast to {channel}: {e}")
            return False

    async def _store_alert(self, alert: SafetyAlert) -> bool:
        """Store alert in database."""
        try:
            logger.info(f"Stored alert {alert.alert_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to store alert: {e}")
            return False

    async def _store_loto_request(self, loto_request: LockoutTagoutRequest) -> bool:
        """Store LOTO request in database."""
        try:
            logger.info(f"Stored LOTO request {loto_request.loto_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to store LOTO request: {e}")
            return False

    async def _notify_maintenance_team(
        self, loto_request: LockoutTagoutRequest
    ) -> bool:
        """Notify maintenance team of LOTO request."""
        try:
            logger.info(
                f"Notified maintenance team of LOTO request {loto_request.loto_id}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to notify maintenance team: {e}")
            return False

    async def _store_corrective_action(
        self, corrective_action: CorrectiveAction
    ) -> bool:
        """Store corrective action in database."""
        try:
            logger.info(f"Stored corrective action {corrective_action.action_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to store corrective action: {e}")
            return False

    async def _notify_action_owner(self, corrective_action: CorrectiveAction) -> bool:
        """Notify action owner of corrective action."""
        try:
            logger.info(
                f"Notified {corrective_action.action_owner} of corrective action {corrective_action.action_id}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to notify action owner: {e}")
            return False

    async def _retrieve_sds_data(self, chemical_name: str) -> Dict[str, Any]:
        """Retrieve SDS data from database or external system."""
        # Simulate SDS data retrieval
        return {
            "cas_number": "123-45-6",
            "hazard_classification": ["Flammable", "Toxic"],
            "handling_precautions": [
                "Use in well-ventilated area",
                "Wear appropriate PPE",
            ],
            "emergency_procedures": ["Evacuate area", "Call emergency services"],
            "ppe_requirements": ["Safety glasses", "Gloves", "Respirator"],
            "storage_requirements": [
                "Store in cool, dry place",
                "Keep away from heat sources",
            ],
        }

    async def _send_micro_training(self, sds: SafetyDataSheet, assignee: str) -> bool:
        """Send micro-training to assignee."""
        try:
            logger.info(f"Sent micro-training for {sds.chemical_name} to {assignee}")
            return True
        except Exception as e:
            logger.error(f"Failed to send micro-training: {e}")
            return False

    async def _store_near_miss(self, near_miss: NearMissReport) -> bool:
        """Store near-miss report in database."""
        try:
            logger.info(f"Stored near-miss report {near_miss.report_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to store near-miss report: {e}")
            return False

    async def _send_photo_upload_reminder(self, near_miss: NearMissReport) -> bool:
        """Send photo upload reminder for near-miss."""
        try:
            logger.info(
                f"Sent photo upload reminder for near-miss {near_miss.report_id}"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send photo upload reminder: {e}")
            return False

    async def _notify_safety_team_near_miss(self, near_miss: NearMissReport) -> bool:
        """Notify safety team of near-miss."""
        try:
            logger.info(f"Notified safety team of near-miss {near_miss.report_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to notify safety team of near-miss: {e}")
            return False

    async def _get_comprehensive_safety_procedures(
        self, procedure_type: Optional[str] = None, category: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get comprehensive safety procedures and policies."""
        try:
            # Comprehensive safety procedures database
            all_procedures = [
                {
                    "id": "PROC-001",
                    "name": "Personal Protective Equipment (PPE) Requirements",
                    "category": "General Safety",
                    "type": "ppe",
                    "priority": "High",
                    "description": "Mandatory PPE requirements for all warehouse personnel",
                    "steps": [
                        "Hard hat must be worn at all times in warehouse areas",
                        "Safety glasses required in production and storage zones",
                        "Steel-toed boots mandatory for all floor operations",
                        "High-visibility vests required in loading dock areas",
                        "Cut-resistant gloves for material handling operations",
                        "Hearing protection in high-noise areas (>85 dB)",
                    ],
                    "compliance_requirements": [
                        "Daily PPE inspection before shift start",
                        "Immediate replacement of damaged equipment",
                        "Proper storage and maintenance of PPE",
                        "Training on correct usage and limitations",
                    ],
                    "emergency_procedures": [
                        "Report damaged or missing PPE immediately",
                        "Stop work if proper PPE is not available",
                        "Contact supervisor for PPE replacement",
                    ],
                    "last_updated": "2024-01-15",
                    "status": "Active",
                },
                {
                    "id": "PROC-002",
                    "name": "Forklift Operation Safety Procedures",
                    "category": "Equipment Safety",
                    "type": "equipment",
                    "priority": "Critical",
                    "description": "Comprehensive safety procedures for forklift operations",
                    "steps": [
                        "Pre-operation inspection checklist completion",
                        "Verify operator certification and training status",
                        "Check load capacity and weight distribution",
                        "Inspect hydraulic systems and controls",
                        "Test brakes, steering, and warning devices",
                        "Ensure clear visibility and proper lighting",
                    ],
                    "safety_requirements": [
                        "Valid forklift operator certification required",
                        "Maximum speed: 5 mph in warehouse, 3 mph in congested areas",
                        "Load must not exceed rated capacity",
                        "Load must be tilted back and secured",
                        "No passengers allowed on forklift",
                        "Use horn at intersections and blind spots",
                    ],
                    "emergency_procedures": [
                        "Immediate shutdown if safety systems fail",
                        "Report mechanical issues to maintenance",
                        "Evacuate area if fuel leak detected",
                        "Contact emergency services for serious incidents",
                    ],
                    "last_updated": "2024-01-10",
                    "status": "Active",
                },
                {
                    "id": "PROC-003",
                    "name": "Emergency Evacuation Procedures",
                    "category": "Emergency Response",
                    "type": "emergency",
                    "priority": "Critical",
                    "description": "Step-by-step emergency evacuation procedures",
                    "steps": [
                        "Activate nearest fire alarm or emergency notification system",
                        "Follow designated evacuation routes to assembly points",
                        "Account for all personnel at assembly points",
                        "Wait for all-clear signal before re-entering building",
                        "Report missing personnel to emergency responders",
                    ],
                    "evacuation_routes": [
                        "Primary: Main exits through loading dock",
                        "Secondary: Emergency exits in each zone",
                        "Assembly Point: Parking lot area A",
                        "Disabled Access: Designated assistance areas",
                    ],
                    "emergency_contacts": [
                        "Internal Emergency: Ext. 911",
                        "Fire Department: 911",
                        "Medical Emergency: 911",
                        "Safety Manager: Ext. 5555",
                    ],
                    "last_updated": "2024-01-05",
                    "status": "Active",
                },
                {
                    "id": "PROC-004",
                    "name": "Lockout/Tagout (LOTO) Procedures",
                    "category": "Equipment Safety",
                    "type": "equipment",
                    "priority": "Critical",
                    "description": "Energy isolation procedures for equipment maintenance",
                    "steps": [
                        "Identify all energy sources (electrical, hydraulic, pneumatic)",
                        "Notify affected personnel of lockout",
                        "Shut down equipment using normal shutdown procedures",
                        "Isolate all energy sources",
                        "Apply lockout devices to isolation points",
                        "Test equipment to verify isolation",
                        "Perform maintenance work",
                        "Remove lockout devices and restore energy",
                    ],
                    "safety_requirements": [
                        "Only authorized personnel may perform LOTO",
                        "Each person must apply their own lock",
                        "Locks must be individually keyed",
                        "Tags must clearly identify the person and purpose",
                        "Verify zero energy state before work begins",
                    ],
                    "emergency_procedures": [
                        "Emergency removal requires management approval",
                        "Document all emergency LOTO removals",
                        "Investigate circumstances of emergency removal",
                        "Provide additional training if needed",
                    ],
                    "last_updated": "2024-01-08",
                    "status": "Active",
                },
                {
                    "id": "PROC-005",
                    "name": "Chemical Handling and Storage Procedures",
                    "category": "Chemical Safety",
                    "type": "chemical",
                    "priority": "High",
                    "description": "Safe handling and storage of hazardous chemicals",
                    "steps": [
                        "Review Safety Data Sheet (SDS) before handling",
                        "Wear appropriate PPE as specified in SDS",
                        "Use proper handling equipment and containers",
                        "Store chemicals in designated areas only",
                        "Maintain proper segregation of incompatible materials",
                        "Label all containers clearly and accurately",
                    ],
                    "storage_requirements": [
                        "Store in well-ventilated areas",
                        "Maintain proper temperature controls",
                        "Keep away from heat sources and ignition points",
                        "Ensure proper segregation of incompatible chemicals",
                        "Maintain clear access to emergency equipment",
                    ],
                    "emergency_procedures": [
                        "Evacuate area immediately if spill occurs",
                        "Call emergency services for large spills",
                        "Use appropriate spill containment materials",
                        "Follow SDS emergency procedures",
                        "Report all chemical incidents immediately",
                    ],
                    "last_updated": "2024-01-12",
                    "status": "Active",
                },
                {
                    "id": "PROC-006",
                    "name": "Material Handling Safety Procedures",
                    "category": "General Safety",
                    "type": "general",
                    "priority": "High",
                    "description": "Safe material handling and lifting procedures",
                    "steps": [
                        "Assess load weight and size before lifting",
                        "Use mechanical aids when available",
                        "Maintain proper body mechanics during lifting",
                        "Keep load close to body and centered",
                        "Use team lifting for heavy or awkward loads",
                        "Clear path of travel before moving loads",
                    ],
                    "lifting_guidelines": [
                        "Maximum individual lift: 50 pounds",
                        "Use two-person lift for 50-100 pounds",
                        "Use mechanical aids for over 100 pounds",
                        "Never lift above shoulder height",
                        "Take breaks to prevent fatigue",
                    ],
                    "emergency_procedures": [
                        "Stop immediately if injury occurs",
                        "Report all lifting injuries",
                        "Seek medical attention for back injuries",
                        "Investigate cause of injury",
                    ],
                    "last_updated": "2024-01-18",
                    "status": "Active",
                },
                {
                    "id": "PROC-007",
                    "name": "Fire Prevention and Response Procedures",
                    "category": "Emergency Response",
                    "type": "emergency",
                    "priority": "Critical",
                    "description": "Fire prevention measures and response procedures",
                    "prevention_measures": [
                        "Maintain clear access to fire exits and equipment",
                        "Store flammable materials in designated areas",
                        "Ensure proper electrical maintenance",
                        "Prohibit smoking in warehouse areas",
                        "Regular inspection of fire suppression systems",
                    ],
                    "response_procedures": [
                        "Activate fire alarm immediately",
                        "Call 911 and report fire location",
                        "Evacuate building using designated routes",
                        "Use fire extinguisher only if safe to do so",
                        "Meet at designated assembly point",
                        "Account for all personnel",
                    ],
                    "fire_extinguisher_usage": [
                        "P - Pull the pin",
                        "A - Aim at base of fire",
                        "S - Squeeze the handle",
                        "S - Sweep from side to side",
                    ],
                    "last_updated": "2024-01-20",
                    "status": "Active",
                },
                {
                    "id": "PROC-008",
                    "name": "Incident Reporting and Investigation Procedures",
                    "category": "General Safety",
                    "type": "general",
                    "priority": "High",
                    "description": "Procedures for reporting and investigating safety incidents",
                    "reporting_requirements": [
                        "Report all incidents immediately to supervisor",
                        "Complete incident report within 24 hours",
                        "Include witness statements and evidence",
                        "Document conditions and circumstances",
                        "Preserve evidence and scene",
                    ],
                    "investigation_process": [
                        "Immediate response to secure scene",
                        "Interview witnesses and involved parties",
                        "Document findings and root causes",
                        "Develop corrective action plan",
                        "Implement preventive measures",
                        "Follow up on corrective actions",
                    ],
                    "documentation_requirements": [
                        "Incident report form completion",
                        "Witness statement collection",
                        "Photo documentation of scene",
                        "Medical treatment documentation",
                        "Corrective action tracking",
                    ],
                    "last_updated": "2024-01-22",
                    "status": "Active",
                },
            ]

            # Filter procedures based on type and category
            filtered_procedures = all_procedures

            if procedure_type:
                filtered_procedures = [
                    p for p in filtered_procedures if p.get("type") == procedure_type
                ]

            if category:
                filtered_procedures = [
                    p for p in filtered_procedures if p.get("category") == category
                ]

            return filtered_procedures

        except Exception as e:
            logger.error(f"Failed to get safety procedures: {e}")
            return []


# Global action tools instance
_action_tools: Optional[SafetyActionTools] = None


async def get_safety_action_tools() -> SafetyActionTools:
    """Get or create the global safety action tools instance."""
    global _action_tools
    if _action_tools is None:
        _action_tools = SafetyActionTools()
        await _action_tools.initialize()
    return _action_tools
