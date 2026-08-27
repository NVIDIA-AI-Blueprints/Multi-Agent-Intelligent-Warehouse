# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Safety & Compliance Agent — maiw-agents package.

Migration notes (Phase 9A)
--------------------------
- All src.* imports removed; dependencies are injected at construction time.
- NIM fallback branches removed; only the ModelGateway path is retained.
- sql_retriever, reasoning_engine injected as Optional[Any].
- ReasoningType defined locally as string constants (mirrors src.api.services.reasoning).
- sanitize_prompt_input sourced from maiw_agents.common.utils.
- Bootstrap (apps/api/maiw_api/bootstrap.py) creates concrete instances and injects them.

Provides intelligent safety incident management, compliance monitoring,
policy lookup, and safety checklist management for warehouse operations.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..common.utils import sanitize_prompt_input

logger = logging.getLogger(__name__)


class ReasoningType:
    """Local mirror of src.api.services.reasoning.ReasoningType string constants."""

    CHAIN_OF_THOUGHT = "chain_of_thought"
    MULTI_HOP = "multi_hop"
    SCENARIO_ANALYSIS = "scenario_analysis"
    CAUSAL = "causal"
    PATTERN_RECOGNITION = "pattern_recognition"


@dataclass
class SafetyQuery:
    """Structured safety query."""

    intent: str
    entities: Dict[str, Any]
    context: Dict[str, Any]
    user_query: str


@dataclass
class SafetyResponse:
    """Structured safety response."""

    response_type: str
    data: Dict[str, Any]
    natural_language: str
    recommendations: List[str]
    confidence: float
    actions_taken: List[Dict[str, Any]]
    reasoning_chain: Optional[Any] = None
    reasoning_steps: Optional[List[Dict[str, Any]]] = None


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
    Safety & Compliance Agent — ModelGateway-only, no src.* imports.

    All heavy runtime dependencies are injected at construction time.
    Bootstrap is responsible for creating and wiring them.
    """

    def __init__(
        self,
        *,
        model_gateway: Optional[Any] = None,
        hybrid_retriever: Optional[Any] = None,
        sql_retriever: Optional[Any] = None,
        action_tools: Optional[Any] = None,
        reasoning_engine: Optional[Any] = None,
        config: Optional[Any] = None,
    ) -> None:
        self.model_gateway = model_gateway
        self.hybrid_retriever = hybrid_retriever
        self.sql_retriever = sql_retriever
        self.action_tools = action_tools
        self.reasoning_engine = reasoning_engine
        self.config = config
        self.conversation_context: Dict[str, Any] = {}

    async def initialize(self) -> None:
        """No-op: all dependencies are injected at construction time."""
        logger.info(
            "SafetyComplianceAgent.initialize() called — all deps pre-injected."
        )

    async def process_query(
        self,
        query: str,
        session_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
        enable_reasoning: bool = True,
        reasoning_types: Optional[List[Any]] = None,
    ) -> SafetyResponse:
        try:
            if session_id not in self.conversation_context:
                self.conversation_context[session_id] = {
                    "history": [],
                    "current_focus": None,
                    "last_entities": {},
                }

            reasoning_chain = None
            if (
                enable_reasoning
                and self.reasoning_engine
                and self._is_complex_query(query)
            ):
                try:
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
                        "Advanced reasoning completed: %d steps",
                        len(reasoning_chain.steps),
                    )
                except Exception as e:
                    logger.warning(
                        "Advanced reasoning failed, continuing with standard processing: %s",
                        e,
                    )
            else:
                logger.info("Skipping advanced reasoning for simple query")

            safety_query = await self._understand_query(query, session_id, context)
            retrieved_data = await self._retrieve_safety_data(safety_query)
            actions_taken = await self._execute_action_tools(safety_query, context)
            response = await self._generate_safety_response(
                safety_query, retrieved_data, session_id, actions_taken, reasoning_chain
            )
            self._update_context(session_id, safety_query, response)
            return response

        except Exception as e:
            logger.error("Failed to process safety query: %s", e)
            return SafetyResponse(
                response_type="error",
                data={"error": str(e)},
                natural_language=f"I encountered an error processing your safety query: {e}",
                recommendations=[],
                confidence=0.0,
                actions_taken=[],
                reasoning_chain=None,
                reasoning_steps=None,
            )

    async def _understand_query(
        self, query: str, session_id: str, context: Optional[Dict[str, Any]]
    ) -> SafetyQuery:
        try:
            conversation_history = self.conversation_context.get(session_id, {}).get(
                "history", []
            )
            context_str = self._build_context_string(conversation_history, context)

            understanding_prompt_template = self.config.persona.understanding_prompt
            system_prompt = self.config.persona.system_prompt
            prompt = understanding_prompt_template.format(
                query=query, context=context_str
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]

            from maiw_models import ModelRequest, ReasoningLevel, RiskLevel

            gw_resp = await self.model_gateway.generate(
                ModelRequest(
                    task="warehouse.safety.understand_query",
                    messages=messages,
                    reasoning=ReasoningLevel.LOW,
                    risk_level=RiskLevel.LOW,
                    temperature=0.1,
                )
            )
            _response_content = gw_resp.content

            try:
                parsed_response = json.loads(_response_content)
                return SafetyQuery(
                    intent=parsed_response.get("intent", "general"),
                    entities=parsed_response.get("entities", {}),
                    context=parsed_response.get("context", {}),
                    user_query=query,
                )
            except json.JSONDecodeError:
                return self._fallback_intent_detection(query)

        except Exception as e:
            logger.error("Query understanding failed: %s", e)
            return self._fallback_intent_detection(query)

    def _fallback_intent_detection(self, query: str) -> SafetyQuery:
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
        try:
            data: Dict[str, Any] = {}

            if (
                safety_query.intent in ["incident_report", "general"]
                or "issue" in safety_query.user_query.lower()
                or "problem" in safety_query.user_query.lower()
            ):
                incidents = await self._get_safety_incidents()
                data["incidents"] = incidents

            if safety_query.intent == "policy_lookup":
                data["policies"] = self._get_safety_policies()

            if safety_query.intent == "compliance_check":
                data["compliance"] = self._get_compliance_status()

            if safety_query.intent == "training":
                data["training"] = self._get_training_records()

            if (
                safety_query.intent in ["policy_lookup", "general"]
                or "procedure" in safety_query.user_query.lower()
            ):
                data["procedures"] = await self._get_safety_procedures()

            return data

        except Exception as e:
            logger.error("Safety data retrieval failed: %s", e)
            return {"error": str(e)}

    async def _execute_action_tools(
        self, safety_query: SafetyQuery, context: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        actions_taken: List[Dict[str, Any]] = []

        try:
            if not self.action_tools:
                return actions_taken

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

            if safety_query.intent == "incident_report":
                if not description:
                    desc_match = re.search(
                        r"(?:incident|accident|hazard)[:\s]+(.+?)(?:,|$)",
                        safety_query.user_query,
                        re.IGNORECASE,
                    )
                    description = (
                        desc_match.group(1).strip()
                        if desc_match
                        else safety_query.user_query
                    )

                if not location:
                    location_match = re.search(
                        r"(?:in|at|zone)\s+([A-Za-z0-9\s]+?)(?:,|$)",
                        safety_query.user_query,
                        re.IGNORECASE,
                    )
                    location = (
                        location_match.group(1).strip() if location_match else "unknown"
                    )

                if not severity:
                    if any(
                        w in safety_query.user_query.lower()
                        for w in ["high", "critical", "severe"]
                    ):
                        severity = "high"
                    elif any(
                        w in safety_query.user_query.lower()
                        for w in ["medium", "moderate"]
                    ):
                        severity = "medium"
                    elif any(
                        w in safety_query.user_query.lower() for w in ["low", "minor"]
                    ):
                        severity = "low"
                    else:
                        severity = "medium"

                if description:
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
                if not checklist_type:
                    if "forklift" in safety_query.user_query.lower():
                        checklist_type = "forklift_pre_op"
                    elif "ppe" in safety_query.user_query.lower():
                        checklist_type = "PPE"
                    elif "loto" in safety_query.user_query.lower():
                        checklist_type = "LOTO"
                    else:
                        checklist_type = "general"

                if not assignee:
                    assignee_match = re.search(
                        r"(?:for|assign to|worker)\s+([A-Za-z\s]+?)(?:$|,|\.)",
                        safety_query.user_query,
                        re.IGNORECASE,
                    )
                    assignee = (
                        assignee_match.group(1).strip() if assignee_match else "system"
                    )

                if checklist_type and assignee:
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
                if not message:
                    alert_match = re.search(
                        r"(?:alert|broadcast|emergency)[:\s]+(.+?)(?:$|,|\.)",
                        safety_query.user_query,
                        re.IGNORECASE,
                    )
                    message = (
                        alert_match.group(1).strip()
                        if alert_match
                        else safety_query.user_query
                    )

                if not zone:
                    zone_match = re.search(
                        r"(?:zone|area|location)\s+([A-Za-z0-9\s]+?)(?:$|,|\.)",
                        safety_query.user_query,
                        re.IGNORECASE,
                    )
                    zone = zone_match.group(1).strip() if zone_match else "all"

                if message:
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
            logger.error("Action tools execution failed: %s", e)
            return [
                {
                    "action": "error",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
            ]

    async def _get_safety_incidents(self) -> List[Dict[str, Any]]:
        try:
            if not self.sql_retriever:
                return []
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
            logger.error("Failed to get safety incidents: %s", e)
            return []

    def _get_safety_policies(self) -> Dict[str, Any]:
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
        try:
            if not self.action_tools:
                return {
                    "procedures": [],
                    "total_count": 0,
                    "last_updated": datetime.now().isoformat(),
                }
            return await self.action_tools.get_safety_procedures()
        except Exception as e:
            logger.error("Failed to get safety procedures: %s", e)
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
        reasoning_chain: Optional[Any] = None,
    ) -> SafetyResponse:
        try:
            context_str = self._build_retrieved_context(retrieved_data)
            conversation_history = self.conversation_context.get(session_id, {}).get(
                "history", []
            )

            actions_str = ""
            if actions_taken:
                actions_str = f"\nActions Taken:\n{json.dumps(actions_taken, indent=2, default=str)}"

            reasoning_str = ""
            if reasoning_chain:
                reasoning_steps_text = []
                for step in reasoning_chain.steps:
                    reasoning_steps_text.append(
                        f"Step {step.step_id}: {step.description}\n{step.reasoning}"
                    )
                reasoning_str = (
                    f"\nAdvanced Reasoning Analysis:\n{chr(10).join(reasoning_steps_text)}"
                    f"\n\nFinal Conclusion: {reasoning_chain.final_conclusion}"
                )

            safe_user_query = sanitize_prompt_input(safety_query.user_query)
            safe_intent = sanitize_prompt_input(safety_query.intent)
            safe_entities = sanitize_prompt_input(safety_query.entities)

            response_prompt_template = self.config.persona.response_prompt
            system_prompt = self.config.persona.system_prompt

            prompt = response_prompt_template.format(
                user_query=safe_user_query,
                intent=safe_intent,
                entities=safe_entities,
                retrieved_data=context_str,
                actions_taken=actions_str,
                reasoning_analysis=reasoning_str,
                conversation_history=(
                    conversation_history[-3:] if conversation_history else "None"
                ),
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]

            from maiw_models import ModelRequest, ReasoningLevel, RiskLevel

            _high_risk_intents = {
                "incident_report",
                "broadcast_alert",
                "lockout_tagout",
                "corrective_action",
                "near_miss",
            }
            _critical_intents = {"broadcast_alert", "lockout_tagout"}
            _intent = safety_query.intent
            _gw_risk = (
                RiskLevel.CRITICAL
                if _intent in _critical_intents
                else (
                    RiskLevel.HIGH
                    if _intent in _high_risk_intents
                    else RiskLevel.MEDIUM
                )
            )
            _gw_reasoning = (
                ReasoningLevel.HIGH
                if _intent in _high_risk_intents
                else ReasoningLevel.MEDIUM
            )

            gw_resp = await self.model_gateway.generate(
                ModelRequest(
                    task=f"warehouse.safety.{_intent}",
                    messages=messages,
                    reasoning=_gw_reasoning,
                    risk_level=_gw_risk,
                    temperature=0.2,
                )
            )
            _gen_response_content = gw_resp.content

            try:
                parsed_response = json.loads(_gen_response_content)
                reasoning_steps = self._extract_reasoning_steps(reasoning_chain)
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
                return self._generate_fallback_response(
                    safety_query, retrieved_data, actions_taken, reasoning_chain
                )

        except Exception as e:
            logger.error("Response generation failed: %s", e)
            return self._generate_fallback_response(
                safety_query, retrieved_data, actions_taken
            )

    def _extract_reasoning_steps(
        self, reasoning_chain: Optional[Any]
    ) -> Optional[List[Dict[str, Any]]]:
        if not reasoning_chain:
            return None
        try:
            return [
                {
                    "step_id": step.step_id,
                    "step_type": step.step_type,
                    "description": step.description,
                    "reasoning": step.reasoning,
                    "confidence": step.confidence,
                    "timestamp": step.timestamp.isoformat(),
                }
                for step in reasoning_chain.steps
            ]
        except Exception:
            return None

    def _generate_fallback_response(
        self,
        safety_query: SafetyQuery,
        retrieved_data: Dict[str, Any],
        actions_taken: Optional[List[Dict[str, Any]]] = None,
        reasoning_chain: Optional[Any] = None,
    ) -> SafetyResponse:
        try:
            intent = safety_query.intent
            data = retrieved_data

            if intent == "incident_report":
                incidents = data.get("incidents", [])
                if incidents:
                    query_lower = safety_query.user_query.lower()
                    filtered = incidents
                    if "critical" in query_lower:
                        filtered = [
                            i for i in incidents if i.get("severity") == "critical"
                        ]
                    elif "high" in query_lower:
                        filtered = [
                            i
                            for i in incidents
                            if i.get("severity") in ["high", "critical"]
                        ]
                    elif "medium" in query_lower:
                        filtered = [
                            i
                            for i in incidents
                            if i.get("severity") in ["medium", "high", "critical"]
                        ]
                    elif "low" in query_lower:
                        filtered = [i for i in incidents if i.get("severity") == "low"]

                    if filtered:
                        summary = f"Found {len(filtered)} safety incidents:\n"
                        for incident in filtered[:5]:
                            summary += f"• {incident.get('description', 'No description')} (Severity: {incident.get('severity', 'Unknown')}, Reported by: {incident.get('reported_by', 'Unknown')}, Date: {incident.get('occurred_at', 'Unknown')})\n"
                        natural_language = (
                            f"Here's the safety incident information:\n\n{summary}"
                        )
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
                    natural_language = (
                        "Here are the comprehensive safety procedures and policies:\n\n"
                    )
                    for i, proc in enumerate(procedure_list[:5], 1):
                        natural_language += (
                            f"{i}. **{proc.get('name', 'Unknown Procedure')}**\n"
                            f"   Category: {proc.get('category', 'General')}\n"
                            f"   Priority: {proc.get('priority', 'Medium')}\n"
                            f"   Description: {proc.get('description', 'No description available')}\n"
                        )
                        steps = proc.get("steps", [])
                        if steps:
                            natural_language += "   Key Steps:\n"
                            for step in steps[:3]:
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

            else:
                incidents = data.get("incidents", [])
                query_lower = safety_query.user_query.lower()
                if incidents and (
                    "issue" in query_lower
                    or "problem" in query_lower
                    or "today" in query_lower
                ):
                    natural_language = f"Here are the main safety issues based on recent incidents:\n\nFound {len(incidents)} recent safety incidents:\n"
                    for incident in incidents[:5]:
                        natural_language += f"• {incident.get('description', 'No description')} (Severity: {incident.get('severity', 'Unknown')}, Reported by: {incident.get('reported_by', 'Unknown')}, Date: {incident.get('occurred_at', 'Unknown')})\n"
                    recommendations = [
                        "Address high-priority incidents immediately",
                        "Review incident patterns",
                        "Implement preventive measures",
                    ]
                else:
                    procedures = data.get("procedures", {})
                    if procedures and procedures.get("procedures"):
                        procedure_list = procedures["procedures"]
                        natural_language = "Here are the comprehensive safety procedures and policies:\n\n"
                        for i, proc in enumerate(procedure_list[:5], 1):
                            natural_language += (
                                f"{i}. **{proc.get('name', 'Unknown Procedure')}**\n"
                                f"   Category: {proc.get('category', 'General')}\n"
                                f"   Priority: {proc.get('priority', 'Medium')}\n"
                                f"   Description: {proc.get('description', 'No description available')}\n"
                            )
                        if len(procedure_list) > 5:
                            natural_language += f"... and {len(procedure_list) - 5} more procedures available.\n"
                    else:
                        natural_language = "I processed your safety query and retrieved relevant information."
                    recommendations = [
                        "Review policy updates",
                        "Ensure team compliance",
                        "Follow all safety procedures",
                    ]

            return SafetyResponse(
                response_type="fallback",
                data=data,
                natural_language=natural_language,
                recommendations=recommendations,
                confidence=0.6,
                actions_taken=actions_taken or [],
                reasoning_chain=reasoning_chain,
                reasoning_steps=self._extract_reasoning_steps(reasoning_chain),
            )

        except Exception as e:
            logger.error("Fallback response generation failed: %s", e)
            return SafetyResponse(
                response_type="error",
                data={"error": str(e)},
                natural_language="I encountered an error processing your request.",
                recommendations=[],
                confidence=0.0,
                actions_taken=actions_taken or [],
            )

    def _build_context_string(
        self,
        conversation_history: List[Dict[str, Any]],
        context: Optional[Dict[str, Any]],
    ) -> str:
        if not conversation_history and not context:
            return "No previous context"
        context_parts = []
        if conversation_history:
            context_parts.append(f"Recent conversation: {conversation_history[-3:]}")
        if context:
            context_parts.append(f"Additional context: {context}")
        return "; ".join(context_parts)

    def _build_retrieved_context(self, retrieved_data: Dict[str, Any]) -> str:
        try:
            context_parts = []
            if "incidents" in retrieved_data:
                incidents = retrieved_data["incidents"]
                if incidents:
                    context_parts.append(f"Recent Incidents ({len(incidents)} found):")
                    for incident in incidents:
                        context_parts.append(
                            f"  - ID {incident.get('id', 'N/A')}: {incident.get('description', 'No description')} "
                            f"(Severity: {incident.get('severity', 'Unknown')}, Reported by: {incident.get('reported_by', 'Unknown')}, Date: {incident.get('occurred_at', 'Unknown')})"
                        )
                else:
                    context_parts.append("Recent Incidents: No incidents found")
            if "policies" in retrieved_data:
                context_parts.append(
                    f"Safety Policies: {retrieved_data['policies'].get('total_count', 0)} policies available"
                )
            if "compliance" in retrieved_data:
                context_parts.append(
                    f"Compliance Status: {retrieved_data['compliance'].get('overall_status', 'Unknown')}"
                )
            if "training" in retrieved_data:
                context_parts.append(
                    f"Training Records: {len(retrieved_data['training'].get('employees', []))} employees tracked"
                )
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
            logger.error("Context building failed: %s", e)
            return "Error building context"

    def _update_context(
        self, session_id: str, safety_query: SafetyQuery, response: SafetyResponse
    ) -> None:
        try:
            if session_id not in self.conversation_context:
                self.conversation_context[session_id] = {
                    "history": [],
                    "current_focus": None,
                    "last_entities": {},
                }

            self.conversation_context[session_id]["history"].append(
                {
                    "query": safety_query.user_query,
                    "intent": safety_query.intent,
                    "response_type": response.response_type,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            if safety_query.intent != "general":
                self.conversation_context[session_id][
                    "current_focus"
                ] = safety_query.intent

            if safety_query.entities:
                self.conversation_context[session_id][
                    "last_entities"
                ] = safety_query.entities

            if len(self.conversation_context[session_id]["history"]) > 10:
                self.conversation_context[session_id]["history"] = (
                    self.conversation_context[session_id]["history"][-10:]
                )

        except Exception as e:
            logger.error("Context update failed: %s", e)

    async def get_conversation_context(self, session_id: str) -> Dict[str, Any]:
        return self.conversation_context.get(
            session_id, {"history": [], "current_focus": None, "last_entities": {}}
        )

    async def clear_conversation_context(self, session_id: str) -> None:
        if session_id in self.conversation_context:
            del self.conversation_context[session_id]

    def _is_complex_query(self, query: str) -> bool:
        query_lower = query.lower()
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
        for pattern in simple_patterns:
            if pattern in query_lower:
                return False
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
    ) -> List[str]:
        reasoning_types = [ReasoningType.CHAIN_OF_THOUGHT]
        query_lower = query.lower()

        if any(
            k in query_lower
            for k in [
                "analyze",
                "compare",
                "relationship",
                "connection",
                "across",
                "multiple",
            ]
        ):
            reasoning_types.append(ReasoningType.MULTI_HOP)
        if any(
            k in query_lower
            for k in [
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
        if any(
            k in query_lower
            for k in [
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
        if any(
            k in query_lower
            for k in [
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
        if any(
            k in query_lower
            for k in ["safety", "incident", "hazard", "risk", "compliance"]
        ):
            if ReasoningType.CAUSAL not in reasoning_types:
                reasoning_types.append(ReasoningType.CAUSAL)

        return reasoning_types
