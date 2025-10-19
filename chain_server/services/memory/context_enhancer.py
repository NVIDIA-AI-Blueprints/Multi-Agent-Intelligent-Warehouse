"""
Context Enhancement Service

Enhances chat responses with conversation memory and context awareness.
Provides intelligent context injection and conversation continuity.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import json

from .conversation_memory import (
    get_conversation_memory_service,
    ConversationMemoryService,
    MemoryType,
    MemoryPriority,
)

logger = logging.getLogger(__name__)


class ContextEnhancer:
    """Service for enhancing responses with conversation context."""

    def __init__(self):
        self.memory_service: Optional[ConversationMemoryService] = None

    async def initialize(self):
        """Initialize the context enhancer."""
        self.memory_service = await get_conversation_memory_service()
        logger.info("Context enhancer initialized")

    async def enhance_with_context(
        self,
        session_id: str,
        user_message: str,
        base_response: str,
        intent: str,
        entities: Dict[str, Any] = None,
        actions_taken: List[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Enhance response with conversation context and memory.

        Args:
            session_id: Session identifier
            user_message: User's current message
            base_response: Base response from agent
            intent: Detected intent
            entities: Extracted entities
            actions_taken: Actions performed

        Returns:
            Enhanced response with context
        """
        try:
            if not self.memory_service:
                await self.initialize()

            # Store current message in conversation history
            await self.memory_service.add_message(
                session_id=session_id,
                message=user_message,
                response=base_response,
                intent=intent,
                entities=entities or {},
                actions_taken=actions_taken or [],
            )

            # Get conversation context
            context = await self.memory_service.get_conversation_context(session_id)

            # Enhance response with context
            enhanced_response = await self._build_contextual_response(
                base_response, context, user_message, intent
            )

            return enhanced_response

        except Exception as e:
            logger.error(f"Error enhancing response with context: {e}")
            return {
                "response": base_response,
                "context_enhanced": False,
                "context_info": {"error": str(e)},
            }

    async def _build_contextual_response(
        self,
        base_response: str,
        context: Dict[str, Any],
        user_message: str,
        intent: str,
    ) -> Dict[str, Any]:
        """Build a contextual response using conversation memory."""

        # Extract relevant context information
        conversation_summary = context.get("conversation_summary", "")
        current_topic = context.get("current_topic", "")
        recent_entities = context.get("entities", {})
        recent_intents = context.get("intents", [])
        recent_actions = context.get("actions_taken", [])
        relevant_memories = context.get("relevant_memories", [])

        # Build context-aware response with more intelligent logic
        enhanced_response = base_response
        context_additions = []

        # Only add context if it provides meaningful value
        message_lower = user_message.lower()

        # Add topic continuity only for significant topic changes
        if (
            current_topic
            and self._is_topic_continuation(user_message, current_topic)
            and len(recent_intents) > 1
            and recent_intents[-1] != intent
        ):
            context_additions.append(
                f"Continuing our discussion about {current_topic}..."
            )

        # Add entity references only if they're directly relevant
        entity_references = self._build_entity_references(user_message, recent_entities)
        if (
            entity_references and len(entity_references) <= 1
        ):  # Limit to 1 entity reference
            context_additions.extend(entity_references)

        # Add action continuity only for related actions
        action_continuity = self._build_action_continuity(intent, recent_actions)
        if action_continuity and not self._is_redundant_action(recent_actions, intent):
            context_additions.append(action_continuity)

        # Add memory-based insights only if they add value
        memory_insights = self._build_memory_insights(relevant_memories, user_message)
        if memory_insights and len(memory_insights) <= 1:  # Limit to 1 insight
            context_additions.extend(memory_insights)

        # Add conversation flow indicators only for significant transitions
        flow_indicators = self._build_flow_indicators(recent_intents, intent)
        if flow_indicators and len(flow_indicators) <= 1:  # Limit to 1 flow indicator
            context_additions.extend(flow_indicators)

        # Combine context additions with base response only if they add value
        if (
            context_additions and len(context_additions) <= 2
        ):  # Limit total context additions
            context_text = " ".join(context_additions)
            enhanced_response = f"{context_text}\n\n{base_response}"
        elif context_additions:
            # If too many context additions, just use the base response
            enhanced_response = base_response

        return {
            "response": enhanced_response,
            "context_enhanced": len(context_additions) > 0,
            "context_info": {
                "conversation_summary": conversation_summary,
                "current_topic": current_topic,
                "entity_count": len(recent_entities),
                "intent_count": len(recent_intents),
                "action_count": len(recent_actions),
                "memory_count": len(relevant_memories),
                "context_additions": len(context_additions),
            },
        }

    def _is_topic_continuation(self, user_message: str, current_topic: str) -> bool:
        """Check if the message continues the current topic."""
        message_lower = user_message.lower()
        topic_keywords = {
            "equipment": ["forklift", "equipment", "machine", "asset", "maintenance"],
            "operations": ["wave", "order", "picking", "packing", "shipping"],
            "safety": ["safety", "incident", "injury", "accident", "hazard"],
            "inventory": ["inventory", "stock", "warehouse", "storage", "location"],
            "analytics": [
                "report",
                "analytics",
                "metrics",
                "performance",
                "utilization",
            ],
        }

        if current_topic in topic_keywords:
            return any(
                keyword in message_lower for keyword in topic_keywords[current_topic]
            )

        return False

    def _build_entity_references(
        self, user_message: str, recent_entities: Dict[str, Any]
    ) -> List[str]:
        """Build references to recently mentioned entities."""
        references = []
        message_lower = user_message.lower()

        # Only reference entities that are directly mentioned in the current message
        for entity_type, entity_value in recent_entities.items():
            if isinstance(entity_value, str) and entity_value.lower() in message_lower:
                # Only add if it's a meaningful entity (not just generic values)
                if entity_type in ["equipment_id", "zone", "order_id", "task_id"]:
                    references.append(f"Regarding {entity_type} {entity_value}...")
            elif isinstance(entity_value, list):
                for value in entity_value:
                    if isinstance(value, str) and value.lower() in message_lower:
                        if entity_type in [
                            "equipment_id",
                            "zone",
                            "order_id",
                            "task_id",
                        ]:
                            references.append(f"Regarding {entity_type} {value}...")
                        break

        return references

    def _build_action_continuity(
        self, current_intent: str, recent_actions: List[Dict[str, Any]]
    ) -> Optional[str]:
        """Build action continuity based on recent actions."""
        if not recent_actions:
            return None

        # Look for related actions in the last 3 actions only
        recent_action_types = [
            action.get("action", "") for action in recent_actions[-3:]
        ]

        # Define action relationships
        action_relationships = {
            "equipment_lookup": ["assign_equipment", "get_equipment_status"],
            "assign_equipment": ["equipment_lookup", "get_equipment_utilization"],
            "create_wave": ["assign_equipment", "get_equipment_status"],
            "log_incident": ["get_safety_policies", "broadcast_alert"],
        }

        if current_intent in action_relationships:
            related_actions = action_relationships[current_intent]
            if any(action in recent_action_types for action in related_actions):
                return "Following up on the previous action..."

        return None

    def _is_redundant_action(
        self, recent_actions: List[Dict[str, Any]], current_intent: str
    ) -> bool:
        """Check if the current action is redundant with recent actions."""
        if not recent_actions:
            return False

        # Get the last action
        last_action = recent_actions[-1].get("action", "")

        # Define redundant action patterns
        redundant_patterns = {
            "equipment_lookup": ["equipment_lookup", "get_equipment_status"],
            "create_wave": ["create_wave", "wave_creation"],
            "assign_equipment": ["assign_equipment", "dispatch_equipment"],
        }

        if current_intent in redundant_patterns:
            return last_action in redundant_patterns[current_intent]

        return False

    def _build_memory_insights(
        self, relevant_memories: List[Dict[str, Any]], user_message: str
    ) -> List[str]:
        """Build insights based on relevant memories."""
        insights = []
        message_lower = user_message.lower()

        # Look for high-priority memories that match the current message
        high_priority_memories = [
            memory
            for memory in relevant_memories
            if memory.get("priority", 0) >= 3
            and any(
                keyword in memory.get("content", "").lower()
                for keyword in message_lower.split()
            )
        ]

        for memory in high_priority_memories[:2]:  # Limit to 2 insights
            memory_type = memory.get("type", "")
            if memory_type == "entity":
                insights.append(
                    f"Based on our previous discussion about {memory.get('content', '')}..."
                )
            elif memory_type == "action":
                insights.append(
                    f"Following up on the previous {memory.get('content', '')}..."
                )

        return insights

    def _build_flow_indicators(
        self, recent_intents: List[str], current_intent: str
    ) -> List[str]:
        """Build conversation flow indicators."""
        indicators = []

        if not recent_intents:
            return indicators

        # Check for intent transitions
        if len(recent_intents) >= 2:
            last_intent = recent_intents[-1]
            if last_intent != current_intent:
                intent_transitions = {
                    ("equipment", "operations"): "Now let's move to operations...",
                    (
                        "operations",
                        "safety",
                    ): "Let's also check safety considerations...",
                    ("safety", "equipment"): "Let's verify equipment status...",
                    (
                        "inventory",
                        "operations",
                    ): "Now let's handle the operational aspects...",
                    (
                        "operations",
                        "inventory",
                    ): "Let's check inventory availability...",
                }

                transition_key = (last_intent, current_intent)
                if transition_key in intent_transitions:
                    indicators.append(intent_transitions[transition_key])

        # Check for repeated intents
        if recent_intents.count(current_intent) > 1:
            indicators.append("Continuing with this topic...")

        return indicators

    async def get_conversation_summary(self, session_id: str) -> Dict[str, Any]:
        """Get a summary of the conversation for the session."""
        try:
            if not self.memory_service:
                await self.initialize()

            context = await self.memory_service.get_conversation_context(session_id)

            return {
                "session_id": session_id,
                "message_count": context.get("message_count", 0),
                "current_topic": context.get("current_topic", "None"),
                "conversation_summary": context.get(
                    "conversation_summary", "No conversation yet"
                ),
                "key_entities": list(context.get("entities", {}).keys()),
                "recent_intents": context.get("intents", []),
                "recent_actions": len(context.get("actions_taken", [])),
                "memory_count": len(context.get("relevant_memories", [])),
                "last_updated": context.get("last_updated", ""),
            }

        except Exception as e:
            logger.error(f"Error getting conversation summary: {e}")
            return {"error": str(e)}

    async def search_conversation_history(
        self, session_id: str, query: str, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search conversation history for specific content."""
        try:
            if not self.memory_service:
                await self.initialize()

            # Search memories
            memories = await self.memory_service.search_memories(session_id, query)

            # Search conversation history
            context = await self.memory_service.get_conversation_context(session_id)
            recent_history = context.get("recent_history", [])

            # Filter history by query
            matching_history = []
            query_lower = query.lower()

            for message in recent_history:
                if (
                    query_lower in message.get("user_message", "").lower()
                    or query_lower in message.get("assistant_response", "").lower()
                ):
                    matching_history.append(message)

            return {
                "memories": memories[:limit],
                "history": matching_history[:limit],
                "total_matches": len(memories) + len(matching_history),
            }

        except Exception as e:
            logger.error(f"Error searching conversation history: {e}")
            return {"error": str(e)}


# Global instance
_context_enhancer: Optional[ContextEnhancer] = None


async def get_context_enhancer() -> ContextEnhancer:
    """Get the global context enhancer instance."""
    global _context_enhancer
    if _context_enhancer is None:
        _context_enhancer = ContextEnhancer()
        await _context_enhancer.initialize()
    return _context_enhancer
