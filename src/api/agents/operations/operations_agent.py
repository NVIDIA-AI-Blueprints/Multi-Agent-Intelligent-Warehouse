"""
Operations Coordination Agent for Warehouse Operations

Provides intelligent workforce scheduling, task management, equipment allocation,
and operational KPI tracking for warehouse operations.
"""

import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
import json
from datetime import datetime, timedelta
import asyncio

from src.api.services.llm.nim_client import get_nim_client, LLMResponse
from src.retrieval.hybrid_retriever import get_hybrid_retriever, SearchContext
from src.retrieval.structured.task_queries import TaskQueries, Task
from src.retrieval.structured.telemetry_queries import TelemetryQueries
from .action_tools import get_operations_action_tools, OperationsActionTools

logger = logging.getLogger(__name__)


@dataclass
class OperationsQuery:
    """Structured operations query."""

    intent: str  # "workforce", "task_management", "equipment", "kpi", "scheduling", "task_assignment", "workload_rebalance", "pick_wave", "optimize_paths", "shift_management", "dock_scheduling", "equipment_dispatch", "publish_kpis"
    entities: Dict[str, Any]  # Extracted entities like shift, employee, equipment, etc.
    context: Dict[str, Any]  # Additional context
    user_query: str  # Original user query


@dataclass
class OperationsResponse:
    """Structured operations response."""

    response_type: str  # "workforce_info", "task_assignment", "equipment_status", "kpi_report", "schedule_info"
    data: Dict[str, Any]  # Structured data
    natural_language: str  # Natural language response
    recommendations: List[str]  # Actionable recommendations
    confidence: float  # Confidence score (0.0 to 1.0)
    actions_taken: List[Dict[str, Any]]  # Actions performed by the agent


@dataclass
class WorkforceInfo:
    """Workforce information structure."""

    shift: str
    employees: List[Dict[str, Any]]
    total_count: int
    active_tasks: int
    productivity_score: float


@dataclass
class TaskAssignment:
    """Task assignment structure."""

    task_id: int
    assignee: str
    priority: str
    estimated_duration: int
    dependencies: List[str]
    status: str


class OperationsCoordinationAgent:
    """
    Operations Coordination Agent with NVIDIA NIM integration.

    Provides comprehensive operations management capabilities including:
    - Workforce scheduling and shift management
    - Task assignment and prioritization
    - Equipment allocation and maintenance
    - KPI tracking and performance analytics
    - Workflow optimization recommendations
    """

    def __init__(self):
        self.nim_client = None
        self.hybrid_retriever = None
        self.task_queries = None
        self.telemetry_queries = None
        self.action_tools = None
        self.conversation_context = {}  # Maintain conversation context

    async def initialize(self) -> None:
        """Initialize the agent with required services."""
        try:
            self.nim_client = await get_nim_client()
            self.hybrid_retriever = await get_hybrid_retriever()

            # Initialize task and telemetry queries
            from src.retrieval.structured.sql_retriever import get_sql_retriever

            sql_retriever = await get_sql_retriever()
            self.task_queries = TaskQueries(sql_retriever)
            self.telemetry_queries = TelemetryQueries(sql_retriever)
            self.action_tools = await get_operations_action_tools()

            logger.info("Operations Coordination Agent initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Operations Coordination Agent: {e}")
            raise

    async def process_query(
        self,
        query: str,
        session_id: str = "default",
        context: Optional[Dict[str, Any]] = None,
    ) -> OperationsResponse:
        """
        Process operations-related queries with full intelligence.

        Args:
            query: User's operations query
            session_id: Session identifier for context
            context: Additional context

        Returns:
            OperationsResponse with structured data and natural language
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

            # Step 1: Understand intent and extract entities using LLM
            operations_query = await self._understand_query(query, session_id, context)

            # Step 2: Retrieve relevant data using hybrid retriever and task queries
            retrieved_data = await self._retrieve_operations_data(operations_query)

            # Step 3: Execute action tools if needed
            actions_taken = await self._execute_action_tools(operations_query, context)

            # Step 4: Generate intelligent response using LLM
            response = await self._generate_operations_response(
                operations_query, retrieved_data, session_id, actions_taken
            )

            # Step 5: Update conversation context
            self._update_context(session_id, operations_query, response)

            return response

        except Exception as e:
            logger.error(f"Failed to process operations query: {e}")
            return OperationsResponse(
                response_type="error",
                data={"error": str(e)},
                natural_language=f"I encountered an error processing your operations query: {str(e)}",
                recommendations=[],
                confidence=0.0,
                actions_taken=[],
            )

    async def _understand_query(
        self, query: str, session_id: str, context: Optional[Dict[str, Any]]
    ) -> OperationsQuery:
        """Use LLM to understand query intent and extract entities."""
        try:
            # Build context-aware prompt
            conversation_history = self.conversation_context.get(session_id, {}).get(
                "history", []
            )
            context_str = self._build_context_string(conversation_history, context)

            prompt = f"""
You are an operations coordination agent for warehouse operations. Analyze the user query and extract structured information.

User Query: "{query}"

Previous Context: {context_str}

IMPORTANT: For queries about workers, employees, staff, workforce, shifts, or team members, use intent "workforce".
IMPORTANT: For queries about tasks, work orders, assignments, job status, or "latest tasks", use intent "task_management".
IMPORTANT: For queries about pick waves, orders, zones, wave creation, or "create a wave", use intent "pick_wave".
IMPORTANT: For queries about dispatching, assigning, or deploying equipment (forklifts, conveyors, etc.), use intent "equipment_dispatch".

Extract the following information:
1. Intent: One of ["workforce", "task_management", "equipment", "kpi", "scheduling", "task_assignment", "workload_rebalance", "pick_wave", "optimize_paths", "shift_management", "dock_scheduling", "equipment_dispatch", "publish_kpis", "general"]
   - "workforce": For queries about workers, employees, staff, shifts, team members, headcount, active workers
   - "task_management": For queries about tasks, assignments, work orders, job status, latest tasks, pending tasks, in-progress tasks
   - "pick_wave": For queries about pick waves, order processing, wave creation, zones, order management
   - "equipment": For queries about machinery, forklifts, conveyors, equipment status
   - "equipment_dispatch": For queries about dispatching, assigning, or deploying equipment to specific tasks or zones
   - "kpi": For queries about performance metrics, productivity, efficiency
2. Entities: Extract the following from the query:
   - equipment_id: Equipment identifier (e.g., "FL-03", "C-01", "Forklift-001")
   - task_id: Task identifier if mentioned (e.g., "T-123", "TASK-456")
   - zone: Zone or location (e.g., "Zone A", "Loading Dock", "Warehouse B")
   - operator: Operator name if mentioned
   - task_type: Type of task (e.g., "pick operations", "loading", "maintenance")
   - shift: Shift time if mentioned
   - employee: Employee name if mentioned
3. Context: Any additional relevant context

Examples:
- "How many active workers we have?" → intent: "workforce"
- "What are the latest tasks?" → intent: "task_management"
- "What are the main tasks today?" → intent: "task_management"
- "We got a 120-line order; create a wave for Zone A" → intent: "pick_wave"
- "Create a pick wave for orders ORD001, ORD002" → intent: "pick_wave"
- "Show me equipment status" → intent: "equipment"
- "Dispatch forklift FL-03 to Zone A for pick operations" → intent: "equipment_dispatch", entities: {"equipment_id": "FL-03", "zone": "Zone A", "task_type": "pick operations"}
- "Assign conveyor C-01 to task T-123" → intent: "equipment_dispatch", entities: {"equipment_id": "C-01", "task_id": "T-123"}
- "Deploy forklift FL-05 to loading dock" → intent: "equipment_dispatch", entities: {"equipment_id": "FL-05", "zone": "loading dock"}

Respond in JSON format:
{{
    "intent": "workforce",
    "entities": {{
        "shift": "morning",
        "employee": "John Doe",
        "task_type": "picking",
        "equipment": "Forklift-001"
    }},
    "context": {{
        "time_period": "today",
        "urgency": "high"
    }}
}}
"""

            messages = [
                {
                    "role": "system",
                    "content": "You are an expert operations coordinator. Always respond with valid JSON.",
                },
                {"role": "user", "content": prompt},
            ]

            response = await self.nim_client.generate_response(
                messages, temperature=0.1
            )

            # Parse LLM response
            try:
                parsed_response = json.loads(response.content)
                return OperationsQuery(
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

    def _fallback_intent_detection(self, query: str) -> OperationsQuery:
        """Fallback intent detection using keyword matching."""
        query_lower = query.lower()

        if any(
            word in query_lower
            for word in [
                "shift",
                "workforce",
                "employee",
                "staff",
                "team",
                "worker",
                "workers",
                "active workers",
                "how many",
            ]
        ):
            intent = "workforce"
        elif any(
            word in query_lower for word in ["assign", "task assignment", "assign task"]
        ):
            intent = "task_assignment"
        elif any(word in query_lower for word in ["rebalance", "workload", "balance"]):
            intent = "workload_rebalance"
        elif any(
            word in query_lower for word in ["wave", "pick wave", "generate wave"]
        ):
            intent = "pick_wave"
        elif any(
            word in query_lower for word in ["optimize", "path", "route", "efficiency"]
        ):
            intent = "optimize_paths"
        elif any(
            word in query_lower
            for word in ["shift management", "manage shift", "schedule shift"]
        ):
            intent = "shift_management"
        elif any(word in query_lower for word in ["dock", "appointment", "scheduling"]):
            intent = "dock_scheduling"
        elif any(
            word in query_lower
            for word in ["dispatch", "equipment dispatch", "send equipment"]
        ):
            intent = "equipment_dispatch"
        elif any(
            word in query_lower for word in ["publish", "kpi", "metrics", "dashboard"]
        ):
            intent = "publish_kpis"
        elif any(
            word in query_lower
            for word in [
                "task",
                "tasks",
                "work",
                "job",
                "pick",
                "pack",
                "latest",
                "pending",
                "in progress",
                "assignment",
                "assignments",
            ]
        ):
            intent = "task_management"
        elif any(
            word in query_lower
            for word in ["equipment", "forklift", "conveyor", "machine"]
        ):
            intent = "equipment"
        elif any(word in query_lower for word in ["performance", "productivity"]):
            intent = "kpi"
        elif any(word in query_lower for word in ["schedule", "planning", "roster"]):
            intent = "scheduling"
        else:
            intent = "general"

        return OperationsQuery(intent=intent, entities={}, context={}, user_query=query)

    async def _retrieve_operations_data(
        self, operations_query: OperationsQuery
    ) -> Dict[str, Any]:
        """Retrieve relevant operations data."""
        try:
            data = {}

            # Get task summary
            if self.task_queries:
                task_summary = await self.task_queries.get_task_summary()
                data["task_summary"] = task_summary

            # Get tasks by status
            if operations_query.intent == "task_management":
                pending_tasks = await self.task_queries.get_tasks_by_status(
                    "pending", limit=20
                )
                in_progress_tasks = await self.task_queries.get_tasks_by_status(
                    "in_progress", limit=20
                )
                data["pending_tasks"] = [asdict(task) for task in pending_tasks]
                data["in_progress_tasks"] = [asdict(task) for task in in_progress_tasks]

            # Get equipment health status
            if operations_query.intent == "equipment":
                equipment_health = (
                    await self.telemetry_queries.get_equipment_health_status()
                )
                data["equipment_health"] = equipment_health

            # Get workforce simulation data (since we don't have real workforce data yet)
            if operations_query.intent == "workforce":
                data["workforce_info"] = self._simulate_workforce_data()

            return data

        except Exception as e:
            logger.error(f"Operations data retrieval failed: {e}")
            return {"error": str(e)}

    async def _execute_action_tools(
        self, operations_query: OperationsQuery, context: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Execute action tools based on query intent and entities."""
        actions_taken = []

        try:
            if not self.action_tools:
                return actions_taken

            # Extract entities for action execution
            task_type = operations_query.entities.get("task_type")
            quantity = operations_query.entities.get("quantity", 0)
            constraints = operations_query.entities.get("constraints", {})
            assignees = operations_query.entities.get("assignees")
            order_ids = operations_query.entities.get("order_ids", [])
            wave_strategy = operations_query.entities.get("wave_strategy", "zone_based")
            shift_id = operations_query.entities.get("shift_id")
            action = operations_query.entities.get("action")
            workers = operations_query.entities.get("workers")
            equipment_id = operations_query.entities.get("equipment_id")
            task_id = operations_query.entities.get("task_id")

            # Execute actions based on intent
            if operations_query.intent == "task_assignment":
                # Extract task details from query if not in entities
                if not task_type:
                    import re

                    if "pick" in operations_query.user_query.lower():
                        task_type = "pick"
                    elif "pack" in operations_query.user_query.lower():
                        task_type = "pack"
                    elif "receive" in operations_query.user_query.lower():
                        task_type = "receive"
                    else:
                        task_type = "general"

                if not quantity:
                    import re

                    qty_matches = re.findall(r"\b(\d+)\b", operations_query.user_query)
                    if qty_matches:
                        quantity = int(qty_matches[0])
                    else:
                        quantity = 1

                if task_type and quantity:
                    # Assign tasks
                    assignment = await self.action_tools.assign_tasks(
                        task_type=task_type,
                        quantity=quantity,
                        constraints=constraints,
                        assignees=assignees,
                    )
                    actions_taken.append(
                        {
                            "action": "assign_tasks",
                            "task_type": task_type,
                            "quantity": quantity,
                            "result": asdict(assignment),
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

            elif operations_query.intent == "workload_rebalance":
                # Rebalance workload
                rebalance = await self.action_tools.rebalance_workload(
                    sla_rules=operations_query.entities.get("sla_rules")
                )
                actions_taken.append(
                    {
                        "action": "rebalance_workload",
                        "result": asdict(rebalance),
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif operations_query.intent == "pick_wave":
                # Extract order IDs from the query if not in entities
                if not order_ids:
                    # Try to extract from the user query
                    import re

                    order_matches = re.findall(r"ORD\d+", operations_query.user_query)
                    if order_matches:
                        order_ids = order_matches
                    else:
                        # If no specific order IDs, create a simulated order based on line count and zone
                        line_count_match = re.search(
                            r"(\d+)-line order", operations_query.user_query
                        )
                        zone_match = re.search(
                            r"Zone ([A-Z])", operations_query.user_query
                        )

                        if line_count_match and zone_match:
                            line_count = int(line_count_match.group(1))
                            zone = zone_match.group(1)

                            # Create a simulated order ID for the wave
                            order_id = f"ORD_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                            order_ids = [order_id]

                            # Store additional context for the wave
                            wave_context = {
                                "simulated_order": True,
                                "line_count": line_count,
                                "zone": zone,
                                "original_query": operations_query.user_query,
                            }
                        else:
                            # Fallback: create a generic order
                            order_id = f"ORD_{datetime.now().strftime('%Y%m%d%H%M%S')}"
                            order_ids = [order_id]
                            wave_context = {
                                "simulated_order": True,
                                "original_query": operations_query.user_query,
                            }

                if order_ids:
                    # Generate pick wave
                    pick_wave = await self.action_tools.generate_pick_wave(
                        order_ids=order_ids, wave_strategy=wave_strategy
                    )
                    actions_taken.append(
                        {
                            "action": "generate_pick_wave",
                            "order_ids": order_ids,
                            "result": asdict(pick_wave),
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

            elif (
                operations_query.intent == "optimize_paths"
                and operations_query.entities.get("picker_id")
            ):
                # Optimize pick paths
                optimization = await self.action_tools.optimize_pick_paths(
                    picker_id=operations_query.entities.get("picker_id"),
                    wave_id=operations_query.entities.get("wave_id"),
                )
                actions_taken.append(
                    {
                        "action": "optimize_pick_paths",
                        "picker_id": operations_query.entities.get("picker_id"),
                        "result": asdict(optimization),
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif operations_query.intent == "shift_management" and shift_id and action:
                # Manage shift schedule
                shift_schedule = await self.action_tools.manage_shift_schedule(
                    shift_id=shift_id,
                    action=action,
                    workers=workers,
                    swaps=operations_query.entities.get("swaps"),
                )
                actions_taken.append(
                    {
                        "action": "manage_shift_schedule",
                        "shift_id": shift_id,
                        "action": action,
                        "result": asdict(shift_schedule),
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif (
                operations_query.intent == "dock_scheduling"
                and operations_query.entities.get("appointments")
            ):
                # Schedule dock appointments
                appointments = await self.action_tools.dock_scheduling(
                    appointments=operations_query.entities.get("appointments", []),
                    capacity=operations_query.entities.get("capacity", {}),
                )
                actions_taken.append(
                    {
                        "action": "dock_scheduling",
                        "appointments_count": len(appointments),
                        "result": [asdict(apt) for apt in appointments],
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif operations_query.intent == "equipment_dispatch" and equipment_id:
                # Dispatch equipment - create task_id if not provided
                if not task_id:
                    # Generate a task ID for the dispatch operation
                    task_id = f"TASK_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

                dispatch = await self.action_tools.dispatch_equipment(
                    equipment_id=equipment_id,
                    task_id=task_id,
                    operator=operations_query.entities.get("operator"),
                )
                actions_taken.append(
                    {
                        "action": "dispatch_equipment",
                        "equipment_id": equipment_id,
                        "task_id": task_id,
                        "result": asdict(dispatch),
                        "timestamp": datetime.now().isoformat(),
                    }
                )

            elif operations_query.intent == "publish_kpis":
                # Publish KPIs
                kpi_result = await self.action_tools.publish_kpis(
                    metrics=operations_query.entities.get("metrics")
                )
                actions_taken.append(
                    {
                        "action": "publish_kpis",
                        "result": kpi_result,
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

    def _simulate_workforce_data(self) -> Dict[str, Any]:
        """Simulate workforce data for demonstration."""
        return {
            "shifts": {
                "morning": {
                    "start_time": "06:00",
                    "end_time": "14:00",
                    "employees": [
                        {"name": "John Smith", "role": "Picker", "status": "active"},
                        {"name": "Sarah Johnson", "role": "Packer", "status": "active"},
                        {
                            "name": "Mike Wilson",
                            "role": "Forklift Operator",
                            "status": "active",
                        },
                    ],
                    "total_count": 3,
                    "active_tasks": 8,
                },
                "afternoon": {
                    "start_time": "14:00",
                    "end_time": "22:00",
                    "employees": [
                        {"name": "Lisa Brown", "role": "Picker", "status": "active"},
                        {"name": "David Lee", "role": "Packer", "status": "active"},
                        {"name": "Amy Chen", "role": "Supervisor", "status": "active"},
                    ],
                    "total_count": 3,
                    "active_tasks": 6,
                },
            },
            "productivity_metrics": {
                "picks_per_hour": 45.2,
                "packages_per_hour": 38.7,
                "accuracy_rate": 98.5,
            },
        }

    async def _generate_operations_response(
        self,
        operations_query: OperationsQuery,
        retrieved_data: Dict[str, Any],
        session_id: str,
        actions_taken: Optional[List[Dict[str, Any]]] = None,
    ) -> OperationsResponse:
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

            prompt = f"""
You are an operations coordination agent. Generate a comprehensive response based on the user query and retrieved data.

User Query: "{operations_query.user_query}"
Intent: {operations_query.intent}
Entities: {operations_query.entities}

Retrieved Data:
{context_str}
{actions_str}

Conversation History: {conversation_history[-3:] if conversation_history else "None"}

Generate a response that includes:
1. Natural language answer to the user's question
2. Structured data in JSON format
3. Actionable recommendations for operations improvement
4. Confidence score (0.0 to 1.0)

IMPORTANT: For workforce queries, always provide the total count of active workers and break down by shifts.

Respond in JSON format:
{{
    "response_type": "workforce_info",
    "data": {{
        "total_active_workers": 6,
        "shifts": {{
            "morning": {{"total_count": 3, "employees": [...]}},
            "afternoon": {{"total_count": 3, "employees": [...]}}
        }},
        "productivity_metrics": {{...}}
    }},
    "natural_language": "Currently, we have 6 active workers across all shifts: Morning shift: 3 workers, Afternoon shift: 3 workers...",
    "recommendations": [
        "Monitor shift productivity metrics",
        "Consider cross-training employees for flexibility"
    ],
    "confidence": 0.95
}}
"""

            messages = [
                {
                    "role": "system",
                    "content": "You are an expert operations coordinator. Always respond with valid JSON.",
                },
                {"role": "user", "content": prompt},
            ]

            response = await self.nim_client.generate_response(
                messages, temperature=0.2
            )

            # Parse LLM response
            try:
                parsed_response = json.loads(response.content)
                return OperationsResponse(
                    response_type=parsed_response.get("response_type", "general"),
                    data=parsed_response.get("data", {}),
                    natural_language=parsed_response.get(
                        "natural_language", "I processed your operations query."
                    ),
                    recommendations=parsed_response.get("recommendations", []),
                    confidence=parsed_response.get("confidence", 0.8),
                    actions_taken=actions_taken or [],
                )
            except json.JSONDecodeError:
                # Fallback response
                return self._generate_fallback_response(
                    operations_query, retrieved_data, actions_taken
                )

        except Exception as e:
            logger.error(f"Response generation failed: {e}")
            return self._generate_fallback_response(
                operations_query, retrieved_data, actions_taken
            )

    def _generate_fallback_response(
        self,
        operations_query: OperationsQuery,
        retrieved_data: Dict[str, Any],
        actions_taken: Optional[List[Dict[str, Any]]] = None,
    ) -> OperationsResponse:
        """Generate fallback response when LLM fails."""
        try:
            intent = operations_query.intent
            data = retrieved_data

            if intent == "workforce":
                # Extract workforce data and provide specific worker count
                workforce_info = data.get("workforce_info", {})
                shifts = workforce_info.get("shifts", {})

                # Calculate total active workers across all shifts
                total_workers = 0
                shift_details = []
                for shift_name, shift_data in shifts.items():
                    shift_count = shift_data.get("total_count", 0)
                    total_workers += shift_count
                    shift_details.append(
                        f"{shift_name.title()} shift: {shift_count} workers"
                    )

                natural_language = (
                    f"Currently, we have **{total_workers} active workers** across all shifts:\n\n"
                    + "\n".join(shift_details)
                )

                if workforce_info.get("productivity_metrics"):
                    metrics = workforce_info["productivity_metrics"]
                    natural_language += f"\n\n**Productivity Metrics:**\n"
                    natural_language += (
                        f"- Picks per hour: {metrics.get('picks_per_hour', 0)}\n"
                    )
                    natural_language += (
                        f"- Packages per hour: {metrics.get('packages_per_hour', 0)}\n"
                    )
                    natural_language += (
                        f"- Accuracy rate: {metrics.get('accuracy_rate', 0)}%"
                    )

                recommendations = [
                    "Monitor shift productivity metrics",
                    "Consider cross-training employees for flexibility",
                    "Ensure adequate coverage during peak hours",
                ]

                # Set response data with workforce information
                response_data = {
                    "total_active_workers": total_workers,
                    "shifts": shifts,
                    "productivity_metrics": workforce_info.get(
                        "productivity_metrics", {}
                    ),
                }

            elif intent == "task_management":
                # Extract task data and provide detailed task information
                task_summary = data.get("task_summary", {})
                pending_tasks = data.get("pending_tasks", [])
                in_progress_tasks = data.get("in_progress_tasks", [])

                # Build detailed task response
                natural_language = "Here's the current task status and assignments:\n\n"

                # Add task summary
                if task_summary:
                    total_tasks = task_summary.get("total_tasks", 0)
                    pending_count = task_summary.get("pending_tasks", 0)
                    in_progress_count = task_summary.get("in_progress_tasks", 0)
                    completed_count = task_summary.get("completed_tasks", 0)

                    natural_language += f"**Task Summary:**\n"
                    natural_language += f"- Total Tasks: {total_tasks}\n"
                    natural_language += f"- Pending: {pending_count}\n"
                    natural_language += f"- In Progress: {in_progress_count}\n"
                    natural_language += f"- Completed: {completed_count}\n\n"

                    # Add task breakdown by kind
                    tasks_by_kind = task_summary.get("tasks_by_kind", [])
                    if tasks_by_kind:
                        natural_language += f"**Tasks by Type:**\n"
                        for task_kind in tasks_by_kind:
                            natural_language += f"- {task_kind.get('kind', 'Unknown').title()}: {task_kind.get('count', 0)}\n"
                        natural_language += "\n"

                # Add pending tasks details
                if pending_tasks:
                    natural_language += f"**Pending Tasks ({len(pending_tasks)}):**\n"
                    for i, task in enumerate(pending_tasks[:5], 1):  # Show first 5
                        task_id = task.get("id", "N/A")
                        task_kind = task.get("kind", "Unknown")
                        priority = (
                            task.get("payload", {}).get("priority", "medium")
                            if isinstance(task.get("payload"), dict)
                            else "medium"
                        )
                        zone = (
                            task.get("payload", {}).get("zone", "N/A")
                            if isinstance(task.get("payload"), dict)
                            else "N/A"
                        )
                        natural_language += f"{i}. {task_kind.title()} (ID: {task_id}, Priority: {priority}, Zone: {zone})\n"
                    if len(pending_tasks) > 5:
                        natural_language += (
                            f"... and {len(pending_tasks) - 5} more pending tasks\n"
                        )
                    natural_language += "\n"

                # Add in-progress tasks details
                if in_progress_tasks:
                    natural_language += (
                        f"**In Progress Tasks ({len(in_progress_tasks)}):**\n"
                    )
                    for i, task in enumerate(in_progress_tasks[:5], 1):  # Show first 5
                        task_id = task.get("id", "N/A")
                        task_kind = task.get("kind", "Unknown")
                        assignee = task.get("assignee", "Unassigned")
                        priority = (
                            task.get("payload", {}).get("priority", "medium")
                            if isinstance(task.get("payload"), dict)
                            else "medium"
                        )
                        zone = (
                            task.get("payload", {}).get("zone", "N/A")
                            if isinstance(task.get("payload"), dict)
                            else "N/A"
                        )
                        natural_language += f"{i}. {task_kind.title()} (ID: {task_id}, Assigned to: {assignee}, Priority: {priority}, Zone: {zone})\n"
                    if len(in_progress_tasks) > 5:
                        natural_language += f"... and {len(in_progress_tasks) - 5} more in-progress tasks\n"

                recommendations = [
                    "Prioritize urgent tasks",
                    "Balance workload across team members",
                    "Monitor task completion rates",
                    "Review task assignments for efficiency",
                ]

                # Set response data with task information
                response_data = {
                    "task_summary": task_summary,
                    "pending_tasks": pending_tasks,
                    "in_progress_tasks": in_progress_tasks,
                    "total_pending": len(pending_tasks),
                    "total_in_progress": len(in_progress_tasks),
                }
            elif intent == "pick_wave":
                # Handle pick wave generation response
                natural_language = "Pick wave generation completed successfully!\n\n"

                # Check if we have pick wave data from actions taken
                pick_wave_data = None
                for action in actions_taken or []:
                    if action.get("action") == "generate_pick_wave":
                        pick_wave_data = action.get("result")
                        break

                if pick_wave_data:
                    wave_id = pick_wave_data.get("wave_id", "Unknown")
                    order_ids = action.get("order_ids", [])
                    total_lines = pick_wave_data.get("total_lines", 0)
                    zones = pick_wave_data.get("zones", [])
                    assigned_pickers = pick_wave_data.get("assigned_pickers", [])
                    estimated_duration = pick_wave_data.get(
                        "estimated_duration", "Unknown"
                    )

                    natural_language += f"**Wave Details:**\n"
                    natural_language += f"- Wave ID: {wave_id}\n"
                    natural_language += f"- Orders: {', '.join(order_ids)}\n"
                    natural_language += f"- Total Lines: {total_lines}\n"
                    natural_language += (
                        f"- Zones: {', '.join(zones) if zones else 'All zones'}\n"
                    )
                    natural_language += (
                        f"- Assigned Pickers: {len(assigned_pickers)} pickers\n"
                    )
                    natural_language += f"- Estimated Duration: {estimated_duration}\n"

                    if assigned_pickers:
                        natural_language += f"\n**Assigned Pickers:**\n"
                        for picker in assigned_pickers:
                            natural_language += f"- {picker}\n"

                    natural_language += (
                        f"\n**Status:** {pick_wave_data.get('status', 'Generated')}\n"
                    )

                    # Add recommendations
                    recommendations = [
                        "Monitor pick wave progress",
                        "Ensure all pickers have necessary equipment",
                        "Track completion against estimated duration",
                    ]

                    response_data = {
                        "wave_id": wave_id,
                        "order_ids": order_ids,
                        "total_lines": total_lines,
                        "zones": zones,
                        "assigned_pickers": assigned_pickers,
                        "estimated_duration": estimated_duration,
                        "status": pick_wave_data.get("status", "Generated"),
                    }
                else:
                    natural_language += "Pick wave generation is in progress. Please check back shortly for details."
                    recommendations = [
                        "Monitor wave generation progress",
                        "Check for any errors or issues",
                    ]
                    response_data = {"status": "in_progress"}

            elif intent == "equipment":
                natural_language = (
                    "Here's the current equipment status and health information."
                )
                recommendations = [
                    "Schedule preventive maintenance",
                    "Monitor equipment performance",
                ]
                response_data = data
            elif intent == "kpi":
                natural_language = (
                    "Here are the current operational KPIs and performance metrics."
                )
                recommendations = [
                    "Focus on accuracy improvements",
                    "Optimize workflow efficiency",
                ]
                response_data = data
            else:
                natural_language = "I processed your operations query and retrieved relevant information."
                recommendations = [
                    "Review operational procedures",
                    "Monitor performance metrics",
                ]
                response_data = data

            return OperationsResponse(
                response_type="fallback",
                data=response_data,
                natural_language=natural_language,
                recommendations=recommendations,
                confidence=0.6,
                actions_taken=actions_taken or [],
            )

        except Exception as e:
            logger.error(f"Fallback response generation failed: {e}")
            return OperationsResponse(
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

            # Add task summary
            if "task_summary" in retrieved_data:
                task_summary = retrieved_data["task_summary"]
                task_context = f"Task Summary:\n"
                task_context += f"- Total Tasks: {task_summary.get('total_tasks', 0)}\n"
                task_context += f"- Pending: {task_summary.get('pending_tasks', 0)}\n"
                task_context += (
                    f"- In Progress: {task_summary.get('in_progress_tasks', 0)}\n"
                )
                task_context += (
                    f"- Completed: {task_summary.get('completed_tasks', 0)}\n"
                )

                # Add task breakdown by kind
                tasks_by_kind = task_summary.get("tasks_by_kind", [])
                if tasks_by_kind:
                    task_context += f"- Tasks by Type:\n"
                    for task_kind in tasks_by_kind:
                        task_context += f"  - {task_kind.get('kind', 'Unknown').title()}: {task_kind.get('count', 0)}\n"

                context_parts.append(task_context)

            # Add pending tasks
            if "pending_tasks" in retrieved_data:
                pending_tasks = retrieved_data["pending_tasks"]
                if pending_tasks:
                    pending_context = f"Pending Tasks ({len(pending_tasks)}):\n"
                    for i, task in enumerate(pending_tasks[:3], 1):  # Show first 3
                        task_id = task.get("id", "N/A")
                        task_kind = task.get("kind", "Unknown")
                        priority = (
                            task.get("payload", {}).get("priority", "medium")
                            if isinstance(task.get("payload"), dict)
                            else "medium"
                        )
                        pending_context += f"{i}. {task_kind.title()} (ID: {task_id}, Priority: {priority})\n"
                    if len(pending_tasks) > 3:
                        pending_context += (
                            f"... and {len(pending_tasks) - 3} more pending tasks\n"
                        )
                    context_parts.append(pending_context)

            # Add in-progress tasks
            if "in_progress_tasks" in retrieved_data:
                in_progress_tasks = retrieved_data["in_progress_tasks"]
                if in_progress_tasks:
                    in_progress_context = (
                        f"In Progress Tasks ({len(in_progress_tasks)}):\n"
                    )
                    for i, task in enumerate(in_progress_tasks[:3], 1):  # Show first 3
                        task_id = task.get("id", "N/A")
                        task_kind = task.get("kind", "Unknown")
                        assignee = task.get("assignee", "Unassigned")
                        in_progress_context += f"{i}. {task_kind.title()} (ID: {task_id}, Assigned to: {assignee})\n"
                    if len(in_progress_tasks) > 3:
                        in_progress_context += f"... and {len(in_progress_tasks) - 3} more in-progress tasks\n"
                    context_parts.append(in_progress_context)

            # Add workforce info
            if "workforce_info" in retrieved_data:
                workforce_info = retrieved_data["workforce_info"]
                shifts = workforce_info.get("shifts", {})

                # Calculate total workers
                total_workers = sum(
                    shift.get("total_count", 0) for shift in shifts.values()
                )

                workforce_context = f"Workforce Info:\n"
                workforce_context += f"- Total Active Workers: {total_workers}\n"

                for shift_name, shift_data in shifts.items():
                    workforce_context += f"- {shift_name.title()} Shift: {shift_data.get('total_count', 0)} workers\n"
                    workforce_context += (
                        f"  - Active Tasks: {shift_data.get('active_tasks', 0)}\n"
                    )
                    workforce_context += f"  - Employees: {', '.join([emp.get('name', 'Unknown') for emp in shift_data.get('employees', [])])}\n"

                if workforce_info.get("productivity_metrics"):
                    metrics = workforce_info["productivity_metrics"]
                    workforce_context += f"- Productivity Metrics:\n"
                    workforce_context += (
                        f"  - Picks per hour: {metrics.get('picks_per_hour', 0)}\n"
                    )
                    workforce_context += f"  - Packages per hour: {metrics.get('packages_per_hour', 0)}\n"
                    workforce_context += (
                        f"  - Accuracy rate: {metrics.get('accuracy_rate', 0)}%\n"
                    )

                context_parts.append(workforce_context)

            # Add equipment health
            if "equipment_health" in retrieved_data:
                equipment_health = retrieved_data["equipment_health"]
                context_parts.append(f"Equipment Health: {equipment_health}")

            return (
                "\n".join(context_parts) if context_parts else "No relevant data found"
            )

        except Exception as e:
            logger.error(f"Context building failed: {e}")
            return "Error building context"

    def _update_context(
        self,
        session_id: str,
        operations_query: OperationsQuery,
        response: OperationsResponse,
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
                    "query": operations_query.user_query,
                    "intent": operations_query.intent,
                    "response_type": response.response_type,
                    "timestamp": datetime.now().isoformat(),
                }
            )

            # Update current focus
            if operations_query.intent != "general":
                self.conversation_context[session_id][
                    "current_focus"
                ] = operations_query.intent

            # Update last entities
            if operations_query.entities:
                self.conversation_context[session_id][
                    "last_entities"
                ] = operations_query.entities

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


# Global operations agent instance
_operations_agent: Optional[OperationsCoordinationAgent] = None


async def get_operations_agent() -> OperationsCoordinationAgent:
    """Get or create the global operations agent instance."""
    global _operations_agent
    if _operations_agent is None:
        _operations_agent = OperationsCoordinationAgent()
        await _operations_agent.initialize()
    return _operations_agent
