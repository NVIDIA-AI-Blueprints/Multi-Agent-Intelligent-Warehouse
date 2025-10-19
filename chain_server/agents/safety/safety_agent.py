"""
Safety & Compliance Agent for Warehouse Operations

Provides intelligent safety incident management, compliance monitoring,
policy lookup, and safety checklist management for warehouse operations.
"""

import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
import json
from datetime import datetime, timedelta
import asyncio

from chain_server.services.llm.nim_client import get_nim_client, LLMResponse
from inventory_retriever.hybrid_retriever import get_hybrid_retriever, SearchContext
from inventory_retriever.structured.sql_retriever import get_sql_retriever
from chain_server.services.reasoning import (
    get_reasoning_engine,
    ReasoningType,
    ReasoningChain,
)
from .action_tools import get_safety_action_tools, SafetyActionTools

logger = logging.getLogger(__name__)


@dataclass
class SafetyQuery:
    """Structured safety query."""

    intent: str  # "incident_report", "policy_lookup", "compliance_check", "safety_audit", "training", "start_checklist", "broadcast_alert", "lockout_tagout", "corrective_action", "retrieve_sds", "near_miss"
    entities: Dict[
        str, Any
    ]  # Extracted entities like incident_type, severity, location, etc.
    context: Dict[str, Any]  # Additional context
    user_query: str  # Original user query


@dataclass
class SafetyResponse:
    """Structured safety response."""

    response_type: str  # "incident_logged", "policy_info", "compliance_status", "audit_report", "training_info"
    data: Dict[str, Any]  # Structured data
    natural_language: str  # Natural language response
    recommendations: List[str]  # Actionable recommendations
    confidence: float  # Confidence score (0.0 to 1.0)
    actions_taken: List[Dict[str, Any]]  # Actions performed by the agent
    reasoning_chain: Optional[ReasoningChain] = None  # Advanced reasoning chain
    reasoning_steps: Optional[List[Dict[str, Any]]] = None  # Individual reasoning steps


@dataclass
class SafetyIncident:
    """Safety incident structure."""

    id: int
    severity: str
    description: str
    reported_by: str
    occurred_at: datetime
    location: str
    incident_type: str
    status: str


class SafetyComplianceAgent:
    """
    Safety & Compliance Agent with NVIDIA NIM integration.

    Provides comprehensive safety and compliance capabilities including:
    - Incident logging and reporting
    - Safety policy lookup and enforcement
    - Compliance checklist management
    - Hazard identification and alerts
    - Training record tracking
    """

    def __init__(self):
        self.nim_client = None
        self.hybrid_retriever = None
        self.sql_retriever = None
        self.action_tools = None
        self.reasoning_engine = None
        self.conversation_context = {}  # Maintain conversation context

    async def initialize(self) -> None:
        """Initialize the agent with required services."""
        try:
            self.nim_client = await get_nim_client()
            self.hybrid_retriever = await get_hybrid_retriever()
            self.sql_retriever = await get_sql_retriever()
            self.action_tools = await get_safety_action_tools()
            self.reasoning_engine = await get_reasoning_engine()

            logger.info("Safety & Compliance Agent initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Safety & Compliance Agent: {e}")
            raise

    async def process_query(
        self,
        query: str,
        session_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
        enable_reasoning: bool = True,
        reasoning_types: List[ReasoningType] = None,
    ) -> SafetyResponse:
        """
        Process safety and compliance queries with full intelligence and advanced reasoning.

        Args:
            query: User's safety/compliance query
            session_id: Session identifier for context
            context: Additional context
            enable_reasoning: Whether to enable advanced reasoning
            reasoning_types: Types of reasoning to apply

        Returns:
            SafetyResponse with structured data, natural language, and reasoning chain
        """
        try:
            # Initialize if needed
            if not self.nim_client or not self.hybrid_retriever:
                await self.initialize()

            # Update conversation context
            if session_id not in self.conversation_context:
                self.conversation_context[session_id] = {
                    "history": [],
                    "current_focus": None,
                    "last_entities": {},
                }

            # Step 1: Advanced Reasoning Analysis (if enabled and query is complex)
            reasoning_chain = None
            if (
                enable_reasoning
                and self.reasoning_engine
                and self._is_complex_query(query)
            ):
                try:
                    # Determine reasoning types based on query complexity
                    if reasoning_types is None:
                        reasoning_types = self._determine_reasoning_types(
                            query, context
                        )

                    reasoning_chain = (
                        await self.reasoning_engine.process_with_reasoning(
                            query=query,
                            context=context or {},
                            reasoning_types=reasoning_types,
                            session_id=session_id,
                        )
                    )
                    logger.info(
                        f"Advanced reasoning completed: {len(reasoning_chain.steps)} steps"
                    )
                except Exception as e:
                    logger.warning(
                        f"Advanced reasoning failed, continuing with standard processing: {e}"
                    )
            else:
                logger.info("Skipping advanced reasoning for simple query")

            # Step 2: Understand intent and extract entities using LLM
            safety_query = await self._understand_query(query, session_id, context)

            # Step 3: Retrieve relevant data using hybrid retriever and safety queries
            retrieved_data = await self._retrieve_safety_data(safety_query)

            # Step 4: Execute action tools if needed
            actions_taken = await self._execute_action_tools(safety_query, context)

            # Step 5: Generate intelligent response using LLM (with reasoning context)
            response = await self._generate_safety_response(
                safety_query, retrieved_data, session_id, actions_taken, reasoning_chain
            )

            # Step 6: Update conversation context
            self._update_context(session_id, safety_query, response)

            return response

        except Exception as e:
            logger.error(f"Failed to process safety query: {e}")
            return SafetyResponse(
                response_type="error",
                data={"error": str(e)},
                natural_language=f"I encountered an error processing your safety query: {str(e)}",
                recommendations=[],
                confidence=0.0,
                actions_taken=[],
                reasoning_chain=None,
                reasoning_steps=None,
            )

    async def _understand_query(
        self, query: str, session_id: str, context: Optional[Dict[str, Any]]
    ) -> SafetyQuery:
        """Use LLM to understand query intent and extract entities."""
        try:
            # Build context-aware prompt
            conversation_history = self.conversation_context.get(session_id, {}).get(
                "history", []
            )
            context_str = self._build_context_string(conversation_history, context)

            prompt = f"""
You are a safety and compliance agent for warehouse operations. Analyze the user query and extract structured information.

User Query: "{query}"

Previous Context: {context_str}

Extract the following information:
1. Intent: One of ["incident_report", "policy_lookup", "compliance_check", "safety_audit", "training", "start_checklist", "broadcast_alert", "lockout_tagout", "corrective_action", "retrieve_sds", "near_miss", "general"]
2. Entities: Extract incident types, severity levels, locations, policy names, compliance requirements, etc.
3. Context: Any additional relevant context

Respond in JSON format:
{{
    "intent": "incident_report",
    "entities": {{
        "incident_type": "slip_and_fall",
        "severity": "minor",
        "location": "Aisle A3",
        "reported_by": "John Smith"
    }},
    "context": {{
        "urgency": "high",
        "requires_immediate_action": true
    }}
}}
"""

            messages = [
                {
                    "role": "system",
                    "content": "You are an expert safety and compliance officer. Always respond with valid JSON.",
                },
                {"role": "user", "content": prompt},
            ]

            response = await self.nim_client.generate_response(
                messages, temperature=0.1
            )

            # Parse LLM response
            try:
                parsed_response = json.loads(response.content)
                return SafetyQuery(
                    intent=parsed_response.get("intent", "general"),
                    entities=parsed_response.get("entities", {}),
                    context=parsed_response.get("context", {}),
                    user_query=query,
                )
            except json.JSONDecodeError:
                # Fallback to simple intent detection
                return self._fallback_intent_detection(query)

        except Exception as e:
            logger.error(f"Query understanding failed: {e}")
            return self._fallback_intent_detection(query)

    def _fallback_intent_detection(self, query: str) -> SafetyQuery:
        """Fallback intent detection using keyword matching."""
        query_lower = query.lower()

        if any(
            word in query_lower
            for word in ["incident", "accident", "injury", "hazard", "report"]
        ):
            intent = "incident_report"
        elif any(
            word in query_lower
            for word in ["checklist", "start checklist", "safety checklist"]
        ):
            intent = "start_checklist"
        elif any(
            word in query_lower
            for word in ["alert", "broadcast", "emergency", "urgent"]
        ):
            intent = "broadcast_alert"
        elif any(
            word in query_lower for word in ["lockout", "tagout", "loto", "lock out"]
        ):
            intent = "lockout_tagout"
        elif any(
            word in query_lower
            for word in ["corrective action", "corrective", "action plan"]
        ):
            intent = "corrective_action"
        elif any(
            word in query_lower
            for word in ["sds", "safety data sheet", "chemical", "hazardous"]
        ):
            intent = "retrieve_sds"
        elif any(
            word in query_lower for word in ["near miss", "near-miss", "close call"]
        ):
            intent = "near_miss"
        elif any(
            word in query_lower for word in ["policy", "procedure", "guideline", "rule"]
        ):
            intent = "policy_lookup"
        elif any(
            word in query_lower
            for word in ["compliance", "audit", "check", "inspection"]
        ):
            intent = "compliance_check"
        elif any(
            word in query_lower
            for word in ["training", "certification", "safety course"]
        ):
            intent = "training"
        else:
            intent = "general"

        return SafetyQuery(intent=intent, entities={}, context={}, user_query=query)

    async def _retrieve_safety_data(self, safety_query: SafetyQuery) -> Dict[str, Any]:
        """Retrieve relevant safety data."""
        try:
            data = {}

            # Always get safety incidents for general safety queries and incident-related queries
            if (
                safety_query.intent in ["incident_report", "general"]
                or "issue" in safety_query.user_query.lower()
                or "problem" in safety_query.user_query.lower()
            ):
                incidents = await self._get_safety_incidents()
                data["incidents"] = incidents

            # Get safety policies (simulated for now)
            if safety_query.intent == "policy_lookup":
                policies = self._get_safety_policies()
                data["policies"] = policies

            # Get compliance status
            if safety_query.intent == "compliance_check":
                compliance_status = self._get_compliance_status()
                data["compliance"] = compliance_status

            # Get training records (simulated)
            if safety_query.intent == "training":
                training_records = self._get_training_records()
                data["training"] = training_records

            # Get safety procedures
            if (
                safety_query.intent in ["policy_lookup", "general"]
                or "procedure" in safety_query.user_query.lower()
            ):
                procedures = await self._get_safety_procedures()
                data["procedures"] = procedures

            return data

        except Exception as e:
            logger.error(f"Safety data retrieval failed: {e}")
            return {"error": str(e)}

    async def _execute_action_tools(
        self, safety_query: SafetyQuery, context: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Execute action tools based on query intent and entities."""
        actions_taken = []

        try:
            if not self.action_tools:
                return actions_taken

            # Extract entities for action execution
            severity = safety_query.entities.get("severity", "medium")
            description = safety_query.entities.get("description", "")
            location = safety_query.entities.get("location", "unknown")
            reporter = safety_query.entities.get("reporter", "system")
            attachments = safety_query.entities.get("attachments", [])
            checklist_type = safety_query.entities.get("checklist_type")
            assignee = safety_query.entities.get("assignee")
            due_in = safety_query.entities.get("due_in", 24)
            message = safety_query.entities.get("message", "")
            zone = safety_query.entities.get("zone", "all")
            channels = safety_query.entities.get("channels", ["PA"])
            asset_id = safety_query.entities.get("asset_id")
            reason = safety_query.entities.get("reason", "")
            requester = safety_query.entities.get("requester", "system")
            incident_id = safety_query.entities.get("incident_id")
            action_owner = safety_query.entities.get("action_owner")
            due_date = safety_query.entities.get("due_date")
            chemical_name = safety_query.entities.get("chemical_name")

            # Execute actions based on intent
            if safety_query.intent == "incident_report":
                # Extract incident details from query if not in entities
                if not description:
                    # Try to extract from the user query
                    import re

                    # Look for description after "incident:" or similar patterns
                    desc_match = re.search(
                        r"(?:incident|accident|hazard)[:\s]+(.+?)(?:,|$)",
                        safety_query.user_query,
                        re.IGNORECASE,
                    )
                    if desc_match:
                        description = desc_match.group(1).strip()
                    else:
                        description = safety_query.user_query

                if not location:
                    # Try to extract location
                    location_match = re.search(
                        r"(?:in|at|zone)\s+([A-Za-z0-9\s]+?)(?:,|$)",
                        safety_query.user_query,
                        re.IGNORECASE,
                    )
                    if location_match:
                        location = location_match.group(1).strip()
                    else:
                        location = "unknown"

                if not severity:
                    # Try to extract severity
                    if any(
                        word in safety_query.user_query.lower()
                        for word in ["high", "critical", "severe"]
                    ):
                        severity = "high"
                    elif any(
                        word in safety_query.user_query.lower()
                        for word in ["medium", "moderate"]
                    ):
                        severity = "medium"
                    elif any(
                        word in safety_query.user_query.lower()
                        for word in ["low", "minor"]
                    ):
                        severity = "low"
                    else:
                        severity = "medium"

                if description:
                    # Log incident
                    incident = await self.action_tools.log_incident(
                        severity=severity,
                        description=description,
                        location=location,
                        reporter=reporter,
                        attachments=attachments,
                    )
                    actions_taken.append(
                        {
                            "action": "log_incident",
                            "severity": severity,
                            "description": description,
                            "result": asdict(incident),
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

            elif safety_query.intent == "start_checklist":
                # Extract checklist details from query if not in entities
                if not checklist_type:
                    # Try to extract checklist type
                    if "forklift" in safety_query.user_query.lower():
                        checklist_type = "forklift_pre_op"
                    elif "ppe" in safety_query.user_query.lower():
                        checklist_type = "PPE"
                    elif "loto" in safety_query.user_query.lower():
                        checklist_type = "LOTO"
                    else:
                        checklist_type = "general"

                if not assignee:
                    # Try to extract assignee
                    import re

                    assignee_match = re.search(
                        r"(?:for|assign to|worker)\s+([A-Za-z\s]+?)(?:$|,|\.)",
                        safety_query.user_query,
                        re.IGNORECASE,
                    )
                    if assignee_match:
                        assignee = assignee_match.group(1).strip()
                    else:
                        assignee = "system"

                if checklist_type and assignee:
                    # Start safety checklist
                    checklist = await self.action_tools.start_checklist(
                        checklist_type=checklist_type, assignee=assignee, due_in=due_in
                    )
                    actions_taken.append(
                        {
                            "action": "start_checklist",
                            "checklist_type": checklist_type,
                            "assignee": assignee,
                            "result": asdict(checklist),
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

            elif safety_query.intent == "broadcast_alert":
                # Extract alert details from query if not in entities
                if not message:
                    # Try to extract message from query
                    import re

                    alert_match = re.search(
                        r"(?:alert|broadcast|emergency)[:\s]+(.+?)(?:$|,|\.)",
                        safety_query.user_query,
                        re.IGNORECASE,
                    )
                    if alert_match:
                        message = alert_match.group(1).strip()
                    else:
                        message = safety_query.user_query

                if not zone:
                    # Try to extract zone
                    zone_match = re.search(
                        r"(?:zone|area|location)\s+([A-Za-z0-9\s]+?)(?:$|,|\.)",
                        safety_query.user_query,
                        re.IGNORECASE,
                    )
                    if zone_match:
                        zone = zone_match.group(1).strip()
                    else:
                        zone = "all"

                if message:
                    # Broadcast safety alert
                    alert = await self.action_tools.broadcast_alert(
                        message=message, zone=zone, channels=channels
                    )
                    actions_taken.append(
                        {
                            "action": "broadcast_alert",
                            "message": message,
                            "zone": zone,
                            "result": asdict(alert),
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

            elif safety_query.intent == "lockout_tagout" and asset_id and reason:
                # Create LOTO request
                loto_request = await self.action_tools.lockout_tagout_request(
                    asset_id=asset_id, reason=reason, requester=requester
                )
                actions_taken.append(
                    {
                        "action": "lockout_tagout_request",
                        "asset_id": asset_id,
                        "reason": reason,
                        "result": asdict(loto_request),
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif (
                safety_query.intent == "corrective_action"
                and incident_id
                and action_owner
                and due_date
            ):
                # Create corrective action
                corrective_action = await self.action_tools.create_corrective_action(
                    incident_id=incident_id,
                    action_owner=action_owner,
                    description=description,
                    due_date=due_date,
                )
                actions_taken.append(
                    {
                        "action": "create_corrective_action",
                        "incident_id": incident_id,
                        "action_owner": action_owner,
                        "result": asdict(corrective_action),
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif safety_query.intent == "retrieve_sds" and chemical_name:
                # Retrieve Safety Data Sheet
                sds = await self.action_tools.retrieve_sds(
                    chemical_name=chemical_name, assignee=assignee
                )
                actions_taken.append(
                    {
                        "action": "retrieve_sds",
                        "chemical_name": chemical_name,
                        "result": asdict(sds),
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif safety_query.intent == "near_miss" and description:
                # Capture near-miss report
                near_miss = await self.action_tools.near_miss_capture(
                    description=description,
                    zone=zone,
                    reporter=reporter,
                    severity=severity,
                )
                actions_taken.append(
                    {
                        "action": "near_miss_capture",
                        "description": description,
                        "zone": zone,
                        "result": asdict(near_miss),
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif (
                safety_query.intent in ["policy_lookup", "general"]
                or "procedure" in safety_query.user_query.lower()
            ):
                # Get safety procedures
                procedure_type = safety_query.entities.get("procedure_type")
                category = safety_query.entities.get("category")
                procedures = await self.action_tools.get_safety_procedures(
                    procedure_type=procedure_type, category=category
                )
                actions_taken.append(
                    {
                        "action": "get_safety_procedures",
                        "procedure_type": procedure_type,
                        "category": category,
                        "result": procedures,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            return actions_taken

        except Exception as e:
            logger.error(f"Action tools execution failed: {e}")
            return [
                {
                    "action": "error",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
            ]

    async def _get_safety_incidents(self) -> List[Dict[str, Any]]:
        """Get safety incidents from database."""
        try:
            await self.sql_retriever.initialize()
            query = """
            SELECT id, severity, description, reported_by, occurred_at
            FROM safety_incidents 
            ORDER BY occurred_at DESC
            LIMIT 10
            """
            results = await self.sql_retriever.fetch_all(query)
            return results
        except Exception as e:
            logger.error(f"Failed to get safety incidents: {e}")
            return []

    def _get_safety_policies(self) -> Dict[str, Any]:
        """Get safety policies (simulated for demonstration)."""
        return {
            "policies": [
                {
                    "id": "POL-001",
                    "name": "Personal Protective Equipment (PPE) Policy",
                    "category": "Safety Equipment",
                    "last_updated": "2024-01-15",
                    "status": "Active",
                    "summary": "All personnel must wear appropriate PPE in designated areas",
                },
                {
                    "id": "POL-002",
                    "name": "Forklift Operation Safety Guidelines",
                    "category": "Equipment Safety",
                    "last_updated": "2024-01-10",
                    "status": "Active",
                    "summary": "Comprehensive guidelines for safe forklift operation",
                },
                {
                    "id": "POL-003",
                    "name": "Emergency Evacuation Procedures",
                    "category": "Emergency Response",
                    "last_updated": "2024-01-05",
                    "status": "Active",
                    "summary": "Step-by-step emergency evacuation procedures",
                },
            ],
            "total_count": 3,
        }

    def _get_compliance_status(self) -> Dict[str, Any]:
        """Get compliance status (simulated for demonstration)."""
        return {
            "overall_status": "Compliant",
            "compliance_score": 95.5,
            "areas": [
                {
                    "area": "Safety Equipment",
                    "status": "Compliant",
                    "score": 98.0,
                    "last_audit": "2024-01-20",
                },
                {
                    "area": "Training Records",
                    "status": "Compliant",
                    "score": 92.0,
                    "last_audit": "2024-01-18",
                },
                {
                    "area": "Incident Reporting",
                    "status": "Minor Issues",
                    "score": 88.0,
                    "last_audit": "2024-01-15",
                },
            ],
            "next_audit": "2024-02-15",
        }

    def _get_training_records(self) -> Dict[str, Any]:
        """Get training records (simulated for demonstration)."""
        return {
            "employees": [
                {
                    "name": "John Smith",
                    "role": "Picker",
                    "certifications": [
                        {
                            "name": "Forklift Safety",
                            "expires": "2024-06-15",
                            "status": "Valid",
                        },
                        {
                            "name": "PPE Training",
                            "expires": "2024-08-20",
                            "status": "Valid",
                        },
                    ],
                },
                {
                    "name": "Sarah Johnson",
                    "role": "Packer",
                    "certifications": [
                        {
                            "name": "Safety Awareness",
                            "expires": "2024-05-10",
                            "status": "Valid",
                        },
                        {
                            "name": "Emergency Response",
                            "expires": "2024-07-25",
                            "status": "Valid",
                        },
                    ],
                },
            ],
            "upcoming_expirations": [
                {
                    "employee": "Mike Wilson",
                    "certification": "Forklift Safety",
                    "expires": "2024-02-28",
                },
                {
                    "employee": "Lisa Brown",
                    "certification": "PPE Training",
                    "expires": "2024-03-05",
                },
            ],
        }

    async def _get_safety_procedures(self) -> Dict[str, Any]:
        """Get comprehensive safety procedures."""
        try:
            if not self.action_tools:
                await self.initialize()

            procedures = await self.action_tools.get_safety_procedures()
            return procedures
        except Exception as e:
            logger.error(f"Failed to get safety procedures: {e}")
            return {
                "procedures": [],
                "total_count": 0,
                "error": str(e),
                "last_updated": datetime.now().isoformat(),
            }

    async def _generate_safety_response(
        self,
        safety_query: SafetyQuery,
        retrieved_data: Dict[str, Any],
        session_id: str,
        actions_taken: Optional[List[Dict[str, Any]]] = None,
        reasoning_chain: Optional[ReasoningChain] = None,
    ) -> SafetyResponse:
        """Generate intelligent response using LLM with retrieved context."""
        try:
            # Build context for LLM
            context_str = self._build_retrieved_context(retrieved_data)
            conversation_history = self.conversation_context.get(session_id, {}).get(
                "history", []
            )

            # Add actions taken to context
            actions_str = ""
            if actions_taken:
                actions_str = f"\nActions Taken:\n{json.dumps(actions_taken, indent=2, default=str)}"

            # Add reasoning context if available
            reasoning_str = ""
            if reasoning_chain:
                reasoning_steps = []
                for step in reasoning_chain.steps:
                    reasoning_steps.append(
                        f"Step {step.step_id}: {step.description}\n{step.reasoning}"
                    )
                reasoning_str = f"\nAdvanced Reasoning Analysis:\n{chr(10).join(reasoning_steps)}\n\nFinal Conclusion: {reasoning_chain.final_conclusion}"

            prompt = f"""
You are a safety and compliance agent. Generate a comprehensive response based on the user query, retrieved data, and advanced reasoning analysis.

User Query: "{safety_query.user_query}"
Intent: {safety_query.intent}
Entities: {safety_query.entities}

Retrieved Data:
{context_str}
{actions_str}
{reasoning_str}

Conversation History: {conversation_history[-3:] if conversation_history else "None"}

Generate a response that includes:
1. Natural language answer to the user's question
2. Structured data in JSON format
3. Actionable recommendations for safety improvement
4. Confidence score (0.0 to 1.0)
5. Reasoning insights if available

Respond in JSON format:
{{
    "response_type": "incident_logged",
    "data": {{
        "incidents": [...],
        "policies": [...]
    }},
    "natural_language": "Based on your query and analysis, here's the safety information...",
    "recommendations": [
        "Recommendation 1",
        "Recommendation 2"
    ],
    "confidence": 0.95
}}
"""

            messages = [
                {
                    "role": "system",
                    "content": "You are an expert safety and compliance officer. Always respond with valid JSON.",
                },
                {"role": "user", "content": prompt},
            ]

            response = await self.nim_client.generate_response(
                messages, temperature=0.2
            )

            # Parse LLM response
            try:
                parsed_response = json.loads(response.content)

                # Prepare reasoning steps for response
                reasoning_steps = None
                if reasoning_chain:
                    reasoning_steps = []
                    for step in reasoning_chain.steps:
                        reasoning_steps.append(
                            {
                                "step_id": step.step_id,
                                "step_type": step.step_type,
                                "description": step.description,
                                "reasoning": step.reasoning,
                                "confidence": step.confidence,
                                "timestamp": step.timestamp.isoformat(),
                            }
                        )

                return SafetyResponse(
                    response_type=parsed_response.get("response_type", "general"),
                    data=parsed_response.get("data", {}),
                    natural_language=parsed_response.get(
                        "natural_language", "I processed your safety query."
                    ),
                    recommendations=parsed_response.get("recommendations", []),
                    confidence=parsed_response.get("confidence", 0.8),
                    actions_taken=actions_taken or [],
                    reasoning_chain=reasoning_chain,
                    reasoning_steps=reasoning_steps,
                )
            except json.JSONDecodeError:
                # Fallback response
                return self._generate_fallback_response(
                    safety_query, retrieved_data, actions_taken, reasoning_chain
                )

        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            return self._generate_fallback_response(
                safety_query, retrieved_data, actions_taken
            )

    def _generate_fallback_response(
        self,
        safety_query: SafetyQuery,
        retrieved_data: Dict[str, Any],
        actions_taken: Optional[List[Dict[str, Any]]] = None,
        reasoning_chain: Optional[ReasoningChain] = None,
    ) -> SafetyResponse:
        """Generate fallback response when LLM fails."""
        try:
            intent = safety_query.intent
            data = retrieved_data

            if intent == "incident_report":
                incidents = data.get("incidents", [])
                if incidents:
                    # Filter by severity if mentioned in query
                    query_lower = safety_query.user_query.lower()
                    filtered_incidents = incidents
                    if "critical" in query_lower:
                        filtered_incidents = [
                            inc
                            for inc in incidents
                            if inc.get("severity") == "critical"
                        ]
                    elif "high" in query_lower:
                        filtered_incidents = [
                            inc
                            for inc in incidents
                            if inc.get("severity") in ["high", "critical"]
                        ]
                    elif "medium" in query_lower:
                        filtered_incidents = [
                            inc
                            for inc in incidents
                            if inc.get("severity") in ["medium", "high", "critical"]
                        ]
                    elif "low" in query_lower:
                        filtered_incidents = [
                            inc for inc in incidents if inc.get("severity") == "low"
                        ]

                    if filtered_incidents:
                        incident_summary = (
                            f"Found {len(filtered_incidents)} safety incidents:\n"
                        )
                        for incident in filtered_incidents[:5]:  # Show top 5 incidents
                            incident_summary += f"• {incident.get('description', 'No description')} (Severity: {incident.get('severity', 'Unknown')}, Reported by: {incident.get('reported_by', 'Unknown')}, Date: {incident.get('occurred_at', 'Unknown')})\n"
                        natural_language = f"Here's the safety incident information:\n\n{incident_summary}"
                    else:
                        natural_language = f"No incidents found matching your criteria. Total incidents in system: {len(incidents)}"
                else:
                    natural_language = "No recent safety incidents found in the system."
                recommendations = [
                    "Report incidents immediately",
                    "Follow up on open incidents",
                    "Review incident patterns for safety improvements",
                ]
            elif intent == "policy_lookup":
                procedures = data.get("procedures", {})
                if procedures and procedures.get("procedures"):
                    procedure_list = procedures["procedures"]
                    natural_language = f"Here are the comprehensive safety procedures and policies:\n\n"

                    for i, proc in enumerate(
                        procedure_list[:5], 1
                    ):  # Show top 5 procedures
                        natural_language += (
                            f"{i}. **{proc.get('name', 'Unknown Procedure')}**\n"
                        )
                        natural_language += (
                            f"   Category: {proc.get('category', 'General')}\n"
                        )
                        natural_language += (
                            f"   Priority: {proc.get('priority', 'Medium')}\n"
                        )
                        natural_language += f"   Description: {proc.get('description', 'No description available')}\n"

                        # Add key steps
                        steps = proc.get("steps", [])
                        if steps:
                            natural_language += f"   Key Steps:\n"
                            for step in steps[:3]:  # Show first 3 steps
                                natural_language += f"   - {step}\n"
                        natural_language += "\n"

                    if len(procedure_list) > 5:
                        natural_language += f"... and {len(procedure_list) - 5} more procedures available.\n"
                else:
                    natural_language = (
                        "Here are the relevant safety policies and procedures."
                    )
                recommendations = [
                    "Review policy updates",
                    "Ensure team compliance",
                    "Follow all safety procedures",
                ]
            elif intent == "compliance_check":
                natural_language = (
                    "Here's the current compliance status and audit information."
                )
                recommendations = ["Address compliance gaps", "Schedule regular audits"]
            elif intent == "training":
                natural_language = (
                    "Here are the training records and certification status."
                )
                recommendations = [
                    "Schedule upcoming training",
                    "Track certification expirations",
                ]
            else:  # General safety queries
                # Check if we have incidents data and the query is about issues/problems
                incidents = data.get("incidents", [])
                query_lower = safety_query.user_query.lower()

                if incidents and (
                    "issue" in query_lower
                    or "problem" in query_lower
                    or "today" in query_lower
                ):
                    # Show recent incidents as main safety issues
                    natural_language = f"Here are the main safety issues based on recent incidents:\n\n"
                    natural_language += (
                        f"Found {len(incidents)} recent safety incidents:\n"
                    )
                    for incident in incidents[:5]:  # Show top 5 incidents
                        natural_language += f"• {incident.get('description', 'No description')} (Severity: {incident.get('severity', 'Unknown')}, Reported by: {incident.get('reported_by', 'Unknown')}, Date: {incident.get('occurred_at', 'Unknown')})\n"
                    recommendations = [
                        "Address high-priority incidents immediately",
                        "Review incident patterns",
                        "Implement preventive measures",
                    ]
                else:
                    # Fall back to procedures for general safety queries
                    procedures = data.get("procedures", {})
                    if procedures and procedures.get("procedures"):
                        procedure_list = procedures["procedures"]
                        natural_language = f"Here are the comprehensive safety procedures and policies:\n\n"

                        for i, proc in enumerate(
                            procedure_list[:5], 1
                        ):  # Show top 5 procedures
                            natural_language += (
                                f"{i}. **{proc.get('name', 'Unknown Procedure')}**\n"
                            )
                            natural_language += (
                                f"   Category: {proc.get('category', 'General')}\n"
                            )
                            natural_language += (
                                f"   Priority: {proc.get('priority', 'Medium')}\n"
                            )
                            natural_language += f"   Description: {proc.get('description', 'No description available')}\n"

                            # Add key steps
                            steps = proc.get("steps", [])
                            if steps:
                                natural_language += f"   Key Steps:\n"
                                for step in steps[:3]:  # Show first 3 steps
                                    natural_language += f"   - {step}\n"
                            natural_language += "\n"

                        if len(procedure_list) > 5:
                            natural_language += f"... and {len(procedure_list) - 5} more procedures available.\n"
                    else:
                        natural_language = "I processed your safety query and retrieved relevant information."
                    recommendations = [
                        "Review policy updates",
                        "Ensure team compliance",
                        "Follow all safety procedures",
                    ]

            # Prepare reasoning steps for fallback response
            reasoning_steps = None
            if reasoning_chain:
                reasoning_steps = []
                for step in reasoning_chain.steps:
                    reasoning_steps.append(
                        {
                            "step_id": step.step_id,
                            "step_type": step.step_type,
                            "description": step.description,
                            "reasoning": step.reasoning,
                            "confidence": step.confidence,
                            "timestamp": step.timestamp.isoformat(),
                        }
                    )

            return SafetyResponse(
                response_type="fallback",
                data=data,
                natural_language=natural_language,
                recommendations=recommendations,
                confidence=0.6,
                actions_taken=actions_taken or [],
                reasoning_chain=reasoning_chain,
                reasoning_steps=reasoning_steps,
            )

        except Exception as e:
            logger.error(f"Fallback response generation failed: {e}")
            return SafetyResponse(
                response_type="error",
                data={"error": str(e)},
                natural_language="I encountered an error processing your request.",
                recommendations=[],
                confidence=0.0,
                actions_taken=actions_taken or [],
            )

    def _build_context_string(
        self, conversation_history: List[Dict], context: Optional[Dict[str, Any]]
    ) -> str:
        """Build context string from conversation history."""
        if not conversation_history and not context:
            return "No previous context"

        context_parts = []

        if conversation_history:
            recent_history = conversation_history[-3:]  # Last 3 exchanges
            context_parts.append(f"Recent conversation: {recent_history}")

        if context:
            context_parts.append(f"Additional context: {context}")

        return "; ".join(context_parts)

    def _build_retrieved_context(self, retrieved_data: Dict[str, Any]) -> str:
        """Build context string from retrieved data."""
        try:
            context_parts = []

            # Add incidents
            if "incidents" in retrieved_data:
                incidents = retrieved_data["incidents"]
                if incidents:
                    context_parts.append(f"Recent Incidents ({len(incidents)} found):")
                    for incident in incidents:
                        context_parts.append(
                            f"  - ID {incident.get('id', 'N/A')}: {incident.get('description', 'No description')} (Severity: {incident.get('severity', 'Unknown')}, Reported by: {incident.get('reported_by', 'Unknown')}, Date: {incident.get('occurred_at', 'Unknown')})"
                        )
                else:
                    context_parts.append("Recent Incidents: No incidents found")

            # Add policies
            if "policies" in retrieved_data:
                policies = retrieved_data["policies"]
                context_parts.append(
                    f"Safety Policies: {policies.get('total_count', 0)} policies available"
                )

            # Add compliance
            if "compliance" in retrieved_data:
                compliance = retrieved_data["compliance"]
                context_parts.append(
                    f"Compliance Status: {compliance.get('overall_status', 'Unknown')}"
                )

            # Add training
            if "training" in retrieved_data:
                training = retrieved_data["training"]
                context_parts.append(
                    f"Training Records: {len(training.get('employees', []))} employees tracked"
                )

            # Add procedures
            if "procedures" in retrieved_data:
                procedures = retrieved_data["procedures"]
                if procedures and procedures.get("procedures"):
                    procedure_list = procedures["procedures"]
                    context_parts.append(
                        f"Safety Procedures: {len(procedure_list)} procedures available"
                    )
                    context_parts.append(
                        f"Categories: {', '.join(procedures.get('categories', []))}"
                    )
                else:
                    context_parts.append("Safety Procedures: No procedures found")

            return (
                "\n".join(context_parts) if context_parts else "No relevant data found"
            )

        except Exception as e:
            logger.error(f"Context building failed: {e}")
            return "Error building context"

    def _update_context(
        self, session_id: str, safety_query: SafetyQuery, response: SafetyResponse
    ) -> None:
        """Update conversation context."""
        try:
            if session_id not in self.conversation_context:
                self.conversation_context[session_id] = {
                    "history": [],
                    "current_focus": None,
                    "last_entities": {},
                }

            # Add to history
            self.conversation_context[session_id]["history"].append(
                {
                    "query": safety_query.user_query,
                    "intent": safety_query.intent,
                    "response_type": response.response_type,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            # Update current focus
            if safety_query.intent != "general":
                self.conversation_context[session_id][
                    "current_focus"
                ] = safety_query.intent

            # Update last entities
            if safety_query.entities:
                self.conversation_context[session_id][
                    "last_entities"
                ] = safety_query.entities

            # Keep history manageable
            if len(self.conversation_context[session_id]["history"]) > 10:
                self.conversation_context[session_id]["history"] = (
                    self.conversation_context[session_id]["history"][-10:]
                )

        except Exception as e:
            logger.error(f"Context update failed: {e}")

    async def get_conversation_context(self, session_id: str) -> Dict[str, Any]:
        """Get conversation context for a session."""
        return self.conversation_context.get(
            session_id, {"history": [], "current_focus": None, "last_entities": {}}
        )

    async def clear_conversation_context(self, session_id: str) -> None:
        """Clear conversation context for a session."""
        if session_id in self.conversation_context:
            del self.conversation_context[session_id]

    def _is_complex_query(self, query: str) -> bool:
        """Determine if a query is complex enough to require advanced reasoning."""
        query_lower = query.lower()

        # Simple queries that don't need reasoning
        simple_patterns = [
            "what are the safety procedures",
            "show me safety procedures",
            "list safety procedures",
            "safety procedures",
            "what is the safety procedure",
            "safety procedure",
            "ppe requirements",
            "what is ppe",
            "lockout tagout procedure",
            "emergency evacuation procedure",
        ]

        # Check if it's a simple query
        for pattern in simple_patterns:
            if pattern in query_lower:
                return False

        # Complex queries that need reasoning
        complex_keywords = [
            "analyze",
            "compare",
            "relationship",
            "connection",
            "across",
            "multiple",
            "what if",
            "scenario",
            "alternative",
            "option",
            "if",
            "when",
            "suppose",
            "why",
            "cause",
            "effect",
            "because",
            "result",
            "consequence",
            "due to",
            "leads to",
            "pattern",
            "trend",
            "learn",
            "insight",
            "recommendation",
            "optimize",
            "improve",
            "how does",
            "explain",
            "understand",
            "investigate",
            "determine",
            "evaluate",
        ]

        return any(keyword in query_lower for keyword in complex_keywords)

    def _determine_reasoning_types(
        self, query: str, context: Optional[Dict[str, Any]]
    ) -> List[ReasoningType]:
        """Determine appropriate reasoning types based on query complexity and context."""
        reasoning_types = [
            ReasoningType.CHAIN_OF_THOUGHT
        ]  # Always include chain-of-thought

        query_lower = query.lower()

        # Multi-hop reasoning for complex queries
        if any(
            keyword in query_lower
            for keyword in [
                "analyze",
                "compare",
                "relationship",
                "connection",
                "across",
                "multiple",
            ]
        ):
            reasoning_types.append(ReasoningType.MULTI_HOP)

        # Scenario analysis for what-if questions
        if any(
            keyword in query_lower
            for keyword in [
                "what if",
                "scenario",
                "alternative",
                "option",
                "if",
                "when",
                "suppose",
            ]
        ):
            reasoning_types.append(ReasoningType.SCENARIO_ANALYSIS)

        # Causal reasoning for cause-effect questions
        if any(
            keyword in query_lower
            for keyword in [
                "why",
                "cause",
                "effect",
                "because",
                "result",
                "consequence",
                "due to",
                "leads to",
            ]
        ):
            reasoning_types.append(ReasoningType.CAUSAL)

        # Pattern recognition for learning queries
        if any(
            keyword in query_lower
            for keyword in [
                "pattern",
                "trend",
                "learn",
                "insight",
                "recommendation",
                "optimize",
                "improve",
            ]
        ):
            reasoning_types.append(ReasoningType.PATTERN_RECOGNITION)

        # For safety queries, always include causal reasoning
        if any(
            keyword in query_lower
            for keyword in ["safety", "incident", "hazard", "risk", "compliance"]
        ):
            if ReasoningType.CAUSAL not in reasoning_types:
                reasoning_types.append(ReasoningType.CAUSAL)

        return reasoning_types


# Global safety agent instance
_safety_agent: Optional[SafetyComplianceAgent] = None


async def get_safety_agent() -> SafetyComplianceAgent:
    """Get or create the global safety agent instance."""
    global _safety_agent
    if _safety_agent is None:
        _safety_agent = SafetyComplianceAgent()
        await _safety_agent.initialize()
    return _safety_agent
