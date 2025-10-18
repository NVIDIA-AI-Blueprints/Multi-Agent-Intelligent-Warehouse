"""
Smart Quick Actions Service

This module provides intelligent quick actions and suggestions based on
user queries, system responses, and contextual information.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json

from chain_server.services.llm.nim_client import get_nim_client, LLMResponse

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """Types of quick actions."""

    EQUIPMENT_ACTION = "equipment_action"
    OPERATIONS_ACTION = "operations_action"
    SAFETY_ACTION = "safety_action"
    DOCUMENT_ACTION = "document_action"
    NAVIGATION_ACTION = "navigation_action"
    INFORMATION_ACTION = "information_action"
    FOLLOW_UP_ACTION = "follow_up_action"


class ActionPriority(Enum):
    """Priority levels for actions."""

    HIGH = "high"  # Critical actions
    MEDIUM = "medium"  # Important actions
    LOW = "low"  # Optional actions


@dataclass
class QuickAction:
    """Represents a quick action."""

    action_id: str
    title: str
    description: str
    action_type: ActionType
    priority: ActionPriority
    icon: str
    command: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    requires_confirmation: bool = False
    success_message: str = ""
    error_message: str = ""


@dataclass
class ActionContext:
    """Context for generating quick actions."""

    query: str
    intent: str
    entities: Dict[str, Any]
    response_data: Dict[str, Any]
    session_id: str
    user_context: Dict[str, Any] = field(default_factory=dict)
    system_context: Dict[str, Any] = field(default_factory=dict)
    evidence_summary: Dict[str, Any] = field(default_factory=dict)


class SmartQuickActionsService:
    """
    Service for generating intelligent quick actions and suggestions.

    This service provides:
    - Context-aware action generation
    - Priority-based action ranking
    - Dynamic action suggestions
    - Action execution capabilities
    - User preference learning
    """

    def __init__(self):
        self.nim_client = None
        self.action_templates = {}
        self.user_preferences = {}
        self.action_history = []
        self.action_stats = {
            "total_actions_generated": 0,
            "actions_by_type": {},
            "actions_by_priority": {},
            "most_used_actions": [],
        }

    async def initialize(self) -> None:
        """Initialize the smart quick actions service."""
        try:
            self.nim_client = await get_nim_client()
            await self._load_action_templates()
            logger.info("Smart Quick Actions Service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Smart Quick Actions Service: {e}")
            raise

    async def _load_action_templates(self) -> None:
        """Load predefined action templates."""
        self.action_templates = {
            # Equipment Actions
            "equipment_status": QuickAction(
                action_id="equipment_status",
                title="Check Equipment Status",
                description="View detailed status of equipment",
                action_type=ActionType.EQUIPMENT_ACTION,
                priority=ActionPriority.HIGH,
                icon="🔍",
                command="get_equipment_status",
                parameters={"equipment_type": "forklift"},
                success_message="Equipment status retrieved successfully",
                error_message="Failed to retrieve equipment status",
            ),
            "assign_equipment": QuickAction(
                action_id="assign_equipment",
                title="Assign Equipment",
                description="Assign equipment to a user or task",
                action_type=ActionType.EQUIPMENT_ACTION,
                priority=ActionPriority.MEDIUM,
                icon="👤",
                command="assign_equipment",
                parameters={},
                requires_confirmation=True,
                success_message="Equipment assigned successfully",
                error_message="Failed to assign equipment",
            ),
            "schedule_maintenance": QuickAction(
                action_id="schedule_maintenance",
                title="Schedule Maintenance",
                description="Schedule maintenance for equipment",
                action_type=ActionType.EQUIPMENT_ACTION,
                priority=ActionPriority.MEDIUM,
                icon="🔧",
                command="schedule_maintenance",
                parameters={},
                requires_confirmation=True,
                success_message="Maintenance scheduled successfully",
                error_message="Failed to schedule maintenance",
            ),
            # Operations Actions
            "create_task": QuickAction(
                action_id="create_task",
                title="Create Task",
                description="Create a new operational task",
                action_type=ActionType.OPERATIONS_ACTION,
                priority=ActionPriority.HIGH,
                icon="➕",
                command="create_task",
                parameters={},
                requires_confirmation=True,
                success_message="Task created successfully",
                error_message="Failed to create task",
            ),
            "assign_task": QuickAction(
                action_id="assign_task",
                title="Assign Task",
                description="Assign task to a worker",
                action_type=ActionType.OPERATIONS_ACTION,
                priority=ActionPriority.MEDIUM,
                icon="📋",
                command="assign_task",
                parameters={},
                requires_confirmation=True,
                success_message="Task assigned successfully",
                error_message="Failed to assign task",
            ),
            "view_workforce": QuickAction(
                action_id="view_workforce",
                title="View Workforce",
                description="Check workforce status and availability",
                action_type=ActionType.OPERATIONS_ACTION,
                priority=ActionPriority.MEDIUM,
                icon="👥",
                command="get_workforce_status",
                parameters={},
                success_message="Workforce status retrieved",
                error_message="Failed to retrieve workforce status",
            ),
            # Safety Actions
            "log_incident": QuickAction(
                action_id="log_incident",
                title="Log Safety Incident",
                description="Report a safety incident",
                action_type=ActionType.SAFETY_ACTION,
                priority=ActionPriority.HIGH,
                icon="⚠️",
                command="log_incident",
                parameters={},
                requires_confirmation=True,
                success_message="Incident logged successfully",
                error_message="Failed to log incident",
            ),
            "start_checklist": QuickAction(
                action_id="start_checklist",
                title="Start Safety Checklist",
                description="Begin a safety checklist",
                action_type=ActionType.SAFETY_ACTION,
                priority=ActionPriority.MEDIUM,
                icon="✅",
                command="start_checklist",
                parameters={},
                success_message="Safety checklist started",
                error_message="Failed to start checklist",
            ),
            "broadcast_alert": QuickAction(
                action_id="broadcast_alert",
                title="Broadcast Alert",
                description="Send safety alert to all workers",
                action_type=ActionType.SAFETY_ACTION,
                priority=ActionPriority.HIGH,
                icon="📢",
                command="broadcast_alert",
                parameters={},
                requires_confirmation=True,
                success_message="Alert broadcasted successfully",
                error_message="Failed to broadcast alert",
            ),
            # Information Actions
            "get_analytics": QuickAction(
                action_id="get_analytics",
                title="View Analytics",
                description="Open analytics dashboard",
                action_type=ActionType.INFORMATION_ACTION,
                priority=ActionPriority.LOW,
                icon="📊",
                command="navigate_to_analytics",
                parameters={"page": "analytics"},
                success_message="Analytics dashboard opened",
                error_message="Failed to open analytics",
            ),
            "export_data": QuickAction(
                action_id="export_data",
                title="Export Data",
                description="Export current data",
                action_type=ActionType.INFORMATION_ACTION,
                priority=ActionPriority.LOW,
                icon="📤",
                command="export_data",
                parameters={},
                success_message="Data exported successfully",
                error_message="Failed to export data",
            ),
            # Follow-up Actions
            "view_details": QuickAction(
                action_id="view_details",
                title="View Details",
                description="Get more detailed information",
                action_type=ActionType.FOLLOW_UP_ACTION,
                priority=ActionPriority.MEDIUM,
                icon="🔍",
                command="get_detailed_info",
                parameters={},
                success_message="Detailed information retrieved",
                error_message="Failed to retrieve details",
            ),
            "related_items": QuickAction(
                action_id="related_items",
                title="View Related Items",
                description="Show related equipment or tasks",
                action_type=ActionType.FOLLOW_UP_ACTION,
                priority=ActionPriority.LOW,
                icon="🔗",
                command="get_related_items",
                parameters={},
                success_message="Related items retrieved",
                error_message="Failed to retrieve related items",
            ),
        }

    async def generate_quick_actions(self, context: ActionContext) -> List[QuickAction]:
        """
        Generate smart quick actions based on context.

        Args:
            context: Action generation context

        Returns:
            List of relevant quick actions
        """
        try:
            actions = []

            # Generate actions based on intent
            intent_actions = await self._generate_intent_based_actions(context)
            actions.extend(intent_actions)

            # Generate actions based on entities
            entity_actions = await self._generate_entity_based_actions(context)
            actions.extend(entity_actions)

            # Generate follow-up actions
            followup_actions = await self._generate_followup_actions(context)
            actions.extend(followup_actions)

            # Generate contextual actions using LLM
            llm_actions = await self._generate_llm_actions(context)
            actions.extend(llm_actions)

            # Remove duplicates and rank by priority
            unique_actions = self._deduplicate_actions(actions)
            ranked_actions = self._rank_actions(unique_actions, context)

            # Update statistics
            self._update_action_stats(ranked_actions)

            logger.info(
                f"Generated {len(ranked_actions)} quick actions for query: {context.query[:50]}..."
            )

            return ranked_actions[:8]  # Limit to 8 actions

        except Exception as e:
            logger.error(f"Error generating quick actions: {e}")
            return []

    async def _generate_intent_based_actions(
        self, context: ActionContext
    ) -> List[QuickAction]:
        """Generate actions based on user intent."""
        actions = []

        try:
            intent_lower = context.intent.lower()

            if "equipment" in intent_lower:
                # Equipment-related actions
                if "status" in intent_lower or "check" in intent_lower:
                    actions.append(
                        self._create_action_from_template("equipment_status", context)
                    )
                    actions.append(
                        self._create_action_from_template(
                            "schedule_maintenance", context
                        )
                    )

                if "assign" in intent_lower or "dispatch" in intent_lower:
                    actions.append(
                        self._create_action_from_template("assign_equipment", context)
                    )

                if "maintenance" in intent_lower:
                    actions.append(
                        self._create_action_from_template(
                            "schedule_maintenance", context
                        )
                    )

            elif "operation" in intent_lower or "task" in intent_lower:
                # Operations-related actions
                actions.append(
                    self._create_action_from_template("create_task", context)
                )
                actions.append(
                    self._create_action_from_template("assign_task", context)
                )
                actions.append(
                    self._create_action_from_template("view_workforce", context)
                )

            elif "safety" in intent_lower or "incident" in intent_lower:
                # Safety-related actions
                actions.append(
                    self._create_action_from_template("log_incident", context)
                )
                actions.append(
                    self._create_action_from_template("start_checklist", context)
                )
                actions.append(
                    self._create_action_from_template("broadcast_alert", context)
                )

            elif "analytics" in intent_lower or "report" in intent_lower:
                # Information-related actions
                actions.append(
                    self._create_action_from_template("get_analytics", context)
                )
                actions.append(
                    self._create_action_from_template("export_data", context)
                )

        except Exception as e:
            logger.error(f"Error generating intent-based actions: {e}")

        return actions

    async def _generate_entity_based_actions(
        self, context: ActionContext
    ) -> List[QuickAction]:
        """Generate actions based on extracted entities."""
        actions = []

        try:
            entities = context.entities

            # Equipment ID-based actions
            if "equipment_id" in entities or "asset_id" in entities:
                equipment_id = entities.get("equipment_id") or entities.get("asset_id")

                # Create equipment-specific actions
                status_action = self._create_action_from_template(
                    "equipment_status", context
                )
                status_action.parameters["asset_id"] = equipment_id
                status_action.title = f"Check {equipment_id} Status"
                actions.append(status_action)

                assign_action = self._create_action_from_template(
                    "assign_equipment", context
                )
                assign_action.parameters["asset_id"] = equipment_id
                assign_action.title = f"Assign {equipment_id}"
                actions.append(assign_action)

            # Zone-based actions
            if "zone" in entities:
                zone = entities["zone"]

                # Create zone-specific actions
                view_action = self._create_action_from_template("view_details", context)
                view_action.parameters["zone"] = zone
                view_action.title = f"View {zone} Details"
                actions.append(view_action)

            # Task ID-based actions
            if "task_id" in entities:
                task_id = entities["task_id"]

                # Create task-specific actions
                assign_action = self._create_action_from_template(
                    "assign_task", context
                )
                assign_action.parameters["task_id"] = task_id
                assign_action.title = f"Assign {task_id}"
                actions.append(assign_action)

        except Exception as e:
            logger.error(f"Error generating entity-based actions: {e}")

        return actions

    async def _generate_followup_actions(
        self, context: ActionContext
    ) -> List[QuickAction]:
        """Generate follow-up actions based on response data."""
        actions = []

        try:
            response_data = context.response_data

            # Equipment follow-up actions
            if "equipment" in response_data:
                equipment_data = response_data["equipment"]
                if isinstance(equipment_data, list) and equipment_data:
                    # Suggest viewing related equipment
                    related_action = self._create_action_from_template(
                        "related_items", context
                    )
                    related_action.title = "View All Equipment"
                    related_action.description = "See all equipment in the system"
                    actions.append(related_action)

                    # Suggest maintenance if equipment is available
                    available_equipment = [
                        eq for eq in equipment_data if eq.get("status") == "available"
                    ]
                    if available_equipment:
                        maintenance_action = self._create_action_from_template(
                            "schedule_maintenance", context
                        )
                        maintenance_action.title = "Schedule Maintenance"
                        maintenance_action.description = (
                            "Schedule maintenance for available equipment"
                        )
                        actions.append(maintenance_action)

            # Task follow-up actions
            if "tasks" in response_data:
                tasks_data = response_data["tasks"]
                if isinstance(tasks_data, list) and tasks_data:
                    # Suggest creating more tasks
                    create_action = self._create_action_from_template(
                        "create_task", context
                    )
                    create_action.title = "Create Another Task"
                    create_action.description = "Create additional tasks"
                    actions.append(create_action)

            # Safety follow-up actions
            if "incidents" in response_data or "safety" in response_data:
                # Suggest safety checklist
                checklist_action = self._create_action_from_template(
                    "start_checklist", context
                )
                checklist_action.title = "Start Safety Checklist"
                checklist_action.description = "Begin a safety inspection"
                actions.append(checklist_action)

        except Exception as e:
            logger.error(f"Error generating follow-up actions: {e}")

        return actions

    async def _generate_llm_actions(self, context: ActionContext) -> List[QuickAction]:
        """Generate actions using LLM analysis."""
        actions = []

        try:
            if not self.nim_client:
                return actions

            # Create prompt for LLM-based action generation
            prompt = [
                {
                    "role": "system",
                    "content": """You are a warehouse operations assistant. Generate relevant quick actions based on the user query and response data.

Return JSON format:
{
    "actions": [
        {
            "title": "Action Title",
            "description": "Action description",
            "action_type": "equipment_action",
            "priority": "high",
            "icon": "🔍",
            "command": "action_command",
            "parameters": {"key": "value"},
            "requires_confirmation": false
        }
    ]
}

Action types: equipment_action, operations_action, safety_action, document_action, navigation_action, information_action, follow_up_action
Priority levels: high, medium, low
Icons: Use relevant emojis (🔍, 👤, 🔧, ➕, 📋, 👥, ⚠️, ✅, 📢, 📊, 📤, 🔗)

Generate 2-4 relevant actions based on the context.""",
                },
                {
                    "role": "user",
                    "content": f"""Query: "{context.query}"
Intent: {context.intent}
Entities: {json.dumps(context.entities, indent=2)}
Response Data: {json.dumps(context.response_data, indent=2)}

Generate relevant quick actions.""",
                },
            ]

            response = await self.nim_client.generate_response(prompt)

            # Parse LLM response with better error handling
            try:
                if not response or not response.content:
                    logger.warning("Empty response from LLM for action generation")
                    return actions

                # Try to extract JSON from response content
                content = response.content.strip()
                if not content:
                    logger.warning("Empty content in LLM response")
                    return actions

                # Look for JSON in the response
                json_start = content.find("{")
                json_end = content.rfind("}") + 1

                if json_start == -1 or json_end == 0:
                    logger.warning(f"No JSON found in LLM response: {content[:100]}...")
                    return actions

                json_content = content[json_start:json_end]
                llm_data = json.loads(json_content)
                llm_actions = llm_data.get("actions", [])

                if not isinstance(llm_actions, list):
                    logger.warning(
                        f"Invalid actions format in LLM response: {type(llm_actions)}"
                    )
                    return actions

                for action_data in llm_actions:
                    if not isinstance(action_data, dict):
                        logger.warning(
                            f"Invalid action data format: {type(action_data)}"
                        )
                        continue

                    action = QuickAction(
                        action_id=f"llm_{datetime.utcnow().timestamp()}",
                        title=action_data.get("title", "Custom Action"),
                        description=action_data.get("description", ""),
                        action_type=ActionType(
                            action_data.get("action_type", "information_action")
                        ),
                        priority=ActionPriority(action_data.get("priority", "medium")),
                        icon=action_data.get("icon", "🔧"),
                        command=action_data.get("command", "custom_action"),
                        parameters=action_data.get("parameters", {}),
                        requires_confirmation=action_data.get(
                            "requires_confirmation", False
                        ),
                        metadata={"generated_by": "llm", "context": context.query},
                    )
                    actions.append(action)

            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse LLM action response: {e}")
                logger.debug(
                    f"Response content: {response.content if response else 'None'}"
                )
            except Exception as e:
                logger.error(f"Unexpected error parsing LLM response: {e}")
                logger.debug(
                    f"Response content: {response.content if response else 'None'}"
                )

        except Exception as e:
            logger.error(f"Error generating LLM actions: {e}")

        return actions

    def _create_action_from_template(
        self, template_id: str, context: ActionContext
    ) -> QuickAction:
        """Create an action from a template with context-specific parameters."""
        try:
            template = self.action_templates.get(template_id)
            if not template:
                logger.warning(f"Action template '{template_id}' not found")
                return None

            # Create a copy of the template
            action = QuickAction(
                action_id=f"{template_id}_{datetime.utcnow().timestamp()}",
                title=template.title,
                description=template.description,
                action_type=template.action_type,
                priority=template.priority,
                icon=template.icon,
                command=template.command,
                parameters=template.parameters.copy(),
                metadata=template.metadata.copy(),
                enabled=template.enabled,
                requires_confirmation=template.requires_confirmation,
                success_message=template.success_message,
                error_message=template.error_message,
            )

            # Add context-specific metadata
            action.metadata.update(
                {
                    "context_query": context.query,
                    "context_intent": context.intent,
                    "generated_at": datetime.utcnow().isoformat(),
                }
            )

            return action

        except Exception as e:
            logger.error(f"Error creating action from template '{template_id}': {e}")
            return None

    def _deduplicate_actions(self, actions: List[QuickAction]) -> List[QuickAction]:
        """Remove duplicate actions based on command and parameters."""
        unique_actions = {}

        for action in actions:
            if not action:
                continue

            # Create a key based on command and parameters
            key = f"{action.command}_{json.dumps(action.parameters, sort_keys=True)}"

            if key not in unique_actions:
                unique_actions[key] = action
            else:
                # Keep the action with higher priority
                existing_action = unique_actions[key]
                if action.priority.value > existing_action.priority.value:
                    unique_actions[key] = action

        return list(unique_actions.values())

    def _rank_actions(
        self, actions: List[QuickAction], context: ActionContext
    ) -> List[QuickAction]:
        """Rank actions by priority and relevance."""
        try:
            # Sort by priority (high, medium, low)
            priority_order = {
                ActionPriority.HIGH: 3,
                ActionPriority.MEDIUM: 2,
                ActionPriority.LOW: 1,
            }

            ranked_actions = sorted(
                actions,
                key=lambda a: (
                    priority_order.get(a.priority, 1),
                    len(a.title),  # Shorter titles first
                    a.action_type.value,
                ),
                reverse=True,
            )

            return ranked_actions

        except Exception as e:
            logger.error(f"Error ranking actions: {e}")
            return actions

    def _update_action_stats(self, actions: List[QuickAction]) -> None:
        """Update action generation statistics."""
        try:
            self.action_stats["total_actions_generated"] += len(actions)

            for action in actions:
                # Count by type
                action_type = action.action_type.value
                self.action_stats["actions_by_type"][action_type] = (
                    self.action_stats["actions_by_type"].get(action_type, 0) + 1
                )

                # Count by priority
                priority = action.priority.value
                self.action_stats["actions_by_priority"][priority] = (
                    self.action_stats["actions_by_priority"].get(priority, 0) + 1
                )

        except Exception as e:
            logger.error(f"Error updating action stats: {e}")

    async def execute_action(
        self, action: QuickAction, context: ActionContext
    ) -> Dict[str, Any]:
        """Execute a quick action."""
        try:
            # This would integrate with the actual MCP tools or API endpoints
            # For now, return a mock execution result

            execution_result = {
                "action_id": action.action_id,
                "command": action.command,
                "parameters": action.parameters,
                "success": True,
                "message": action.success_message,
                "timestamp": datetime.utcnow().isoformat(),
                "execution_time": 0.1,
            }

            # Record action execution
            self.action_history.append(
                {
                    "action": action,
                    "context": context,
                    "result": execution_result,
                    "timestamp": datetime.utcnow(),
                }
            )

            logger.info(f"Executed action: {action.title}")

            return execution_result

        except Exception as e:
            logger.error(f"Error executing action '{action.title}': {e}")
            return {
                "action_id": action.action_id,
                "command": action.command,
                "parameters": action.parameters,
                "success": False,
                "message": action.error_message,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            }

    def get_action_stats(self) -> Dict[str, Any]:
        """Get action generation statistics."""
        return self.action_stats.copy()

    def get_action_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent action execution history."""
        return self.action_history[-limit:]


# Global smart quick actions service instance
_smart_quick_actions_service = None


async def get_smart_quick_actions_service() -> SmartQuickActionsService:
    """Get the global smart quick actions service instance."""
    global _smart_quick_actions_service
    if _smart_quick_actions_service is None:
        _smart_quick_actions_service = SmartQuickActionsService()
        await _smart_quick_actions_service.initialize()
    return _smart_quick_actions_service
