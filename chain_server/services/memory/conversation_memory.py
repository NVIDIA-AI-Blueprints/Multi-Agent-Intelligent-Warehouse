"""
Conversation Memory Service

Provides persistent context across messages for intelligent conversation continuity.
Handles conversation history, context extraction, and memory management.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import asyncio
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class MemoryType(Enum):
    """Types of memory stored in conversation context."""

    CONVERSATION = "conversation"
    ENTITY = "entity"
    INTENT = "intent"
    ACTION = "action"
    PREFERENCE = "preference"
    CONTEXT = "context"


class MemoryPriority(Enum):
    """Priority levels for memory retention."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class MemoryItem:
    """Individual memory item with metadata."""

    id: str
    type: MemoryType
    content: str
    priority: MemoryPriority
    created_at: datetime
    last_accessed: datetime
    access_count: int = 0
    metadata: Dict[str, Any] = None
    expires_at: Optional[datetime] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.expires_at is None:
            # Set default expiration based on priority
            if self.priority == MemoryPriority.CRITICAL:
                self.expires_at = self.created_at + timedelta(days=30)
            elif self.priority == MemoryPriority.HIGH:
                self.expires_at = self.created_at + timedelta(days=7)
            elif self.priority == MemoryPriority.MEDIUM:
                self.expires_at = self.created_at + timedelta(days=3)
            else:
                self.expires_at = self.created_at + timedelta(hours=24)


@dataclass
class ConversationContext:
    """Complete conversation context for a session."""

    session_id: str
    user_id: Optional[str]
    created_at: datetime
    last_updated: datetime
    message_count: int = 0
    entities: Dict[str, Any] = None
    intents: List[str] = None
    actions_taken: List[Dict[str, Any]] = None
    preferences: Dict[str, Any] = None
    current_topic: Optional[str] = None
    conversation_summary: Optional[str] = None

    def __post_init__(self):
        if self.entities is None:
            self.entities = {}
        if self.intents is None:
            self.intents = []
        if self.actions_taken is None:
            self.actions_taken = []
        if self.preferences is None:
            self.preferences = {}


class ConversationMemoryService:
    """Service for managing conversation memory and context."""

    def __init__(
        self, max_memories_per_session: int = 100, max_conversation_length: int = 50
    ):
        self.max_memories_per_session = max_memories_per_session
        self.max_conversation_length = max_conversation_length

        # In-memory storage (in production, this would be Redis or database)
        self._conversations: Dict[str, ConversationContext] = {}
        self._memories: Dict[str, List[MemoryItem]] = defaultdict(list)
        self._conversation_history: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=max_conversation_length)
        )

        # Memory cleanup task
        self._cleanup_task = None
        self._start_cleanup_task()

    def _start_cleanup_task(self):
        """Start background task for memory cleanup."""

        async def cleanup_expired_memories():
            while True:
                try:
                    await self._cleanup_expired_memories()
                    await asyncio.sleep(300)  # Run every 5 minutes
                except Exception as e:
                    logger.error(f"Error in memory cleanup task: {e}")
                    await asyncio.sleep(60)

        self._cleanup_task = asyncio.create_task(cleanup_expired_memories())

    async def _cleanup_expired_memories(self):
        """Remove expired memories to prevent memory leaks."""
        current_time = datetime.now()
        expired_count = 0

        for session_id, memories in self._memories.items():
            # Remove expired memories
            self._memories[session_id] = [
                memory
                for memory in memories
                if memory.expires_at is None or memory.expires_at > current_time
            ]
            expired_count += len(memories) - len(self._memories[session_id])

        if expired_count > 0:
            logger.info(f"Cleaned up {expired_count} expired memories")

    async def get_or_create_conversation(
        self, session_id: str, user_id: Optional[str] = None
    ) -> ConversationContext:
        """Get existing conversation or create new one."""
        if session_id not in self._conversations:
            self._conversations[session_id] = ConversationContext(
                session_id=session_id,
                user_id=user_id,
                created_at=datetime.now(),
                last_updated=datetime.now(),
            )
            logger.info(f"Created new conversation context for session {session_id}")
        else:
            # Update last accessed time
            self._conversations[session_id].last_updated = datetime.now()

        return self._conversations[session_id]

    async def add_message(
        self,
        session_id: str,
        message: str,
        response: str,
        intent: str,
        entities: Dict[str, Any] = None,
        actions_taken: List[Dict[str, Any]] = None,
    ) -> None:
        """Add a message exchange to conversation history."""
        conversation = await self.get_or_create_conversation(session_id)

        # Add to conversation history
        message_data = {
            "timestamp": datetime.now().isoformat(),
            "user_message": message,
            "assistant_response": response,
            "intent": intent,
            "entities": entities or {},
            "actions_taken": actions_taken or [],
        }

        self._conversation_history[session_id].append(message_data)
        conversation.message_count += 1

        # Update conversation context
        await self._update_conversation_context(conversation, message_data)

        # Extract and store memories
        await self._extract_and_store_memories(session_id, message_data)

        logger.debug(
            f"Added message to conversation {session_id}, total messages: {conversation.message_count}"
        )

    async def _update_conversation_context(
        self, conversation: ConversationContext, message_data: Dict[str, Any]
    ):
        """Update conversation context with new message data."""
        # Update entities
        if message_data.get("entities"):
            conversation.entities.update(message_data["entities"])

        # Update intents
        intent = message_data.get("intent")
        if intent and intent not in conversation.intents:
            conversation.intents.append(intent)

        # Update actions taken
        if message_data.get("actions_taken"):
            conversation.actions_taken.extend(message_data["actions_taken"])

        # Update current topic (simple keyword-based topic detection)
        current_topic = self._extract_topic(message_data["user_message"])
        if current_topic:
            conversation.current_topic = current_topic

        # Update conversation summary
        conversation.conversation_summary = await self._generate_conversation_summary(
            conversation
        )

    def _extract_topic(self, message: str) -> Optional[str]:
        """Extract current topic from message using simple keyword matching."""
        message_lower = message.lower()

        # Topic keywords
        topics = {
            "equipment": [
                "forklift",
                "equipment",
                "machine",
                "asset",
                "maintenance",
                "repair",
            ],
            "operations": [
                "wave",
                "order",
                "picking",
                "packing",
                "shipping",
                "dispatch",
            ],
            "safety": [
                "safety",
                "incident",
                "injury",
                "accident",
                "hazard",
                "emergency",
            ],
            "inventory": [
                "inventory",
                "stock",
                "warehouse",
                "storage",
                "location",
                "quantity",
            ],
            "analytics": [
                "report",
                "analytics",
                "metrics",
                "performance",
                "utilization",
                "efficiency",
            ],
        }

        for topic, keywords in topics.items():
            if any(keyword in message_lower for keyword in keywords):
                return topic

        return None

    async def _generate_conversation_summary(
        self, conversation: ConversationContext
    ) -> str:
        """Generate a summary of the conversation."""
        if conversation.message_count <= 3:
            return "New conversation started"

        # Simple summary based on intents and topics
        summary_parts = []

        if conversation.intents:
            unique_intents = list(
                set(conversation.intents[-5:])
            )  # Last 5 unique intents
            summary_parts.append(f"Recent intents: {', '.join(unique_intents)}")

        if conversation.current_topic:
            summary_parts.append(f"Current topic: {conversation.current_topic}")

        if conversation.entities:
            key_entities = list(conversation.entities.keys())[:3]  # First 3 entities
            summary_parts.append(f"Key entities: {', '.join(key_entities)}")

        return "; ".join(summary_parts) if summary_parts else "Conversation in progress"

    async def _extract_and_store_memories(
        self, session_id: str, message_data: Dict[str, Any]
    ):
        """Extract and store relevant memories from message data."""
        memories = []

        # Extract entity memories
        if message_data.get("entities"):
            for entity_type, entity_value in message_data["entities"].items():
                memory = MemoryItem(
                    id=f"{session_id}_{entity_type}_{datetime.now().timestamp()}",
                    type=MemoryType.ENTITY,
                    content=f"{entity_type}: {entity_value}",
                    priority=MemoryPriority.MEDIUM,
                    created_at=datetime.now(),
                    last_accessed=datetime.now(),
                    metadata={"entity_type": entity_type, "entity_value": entity_value},
                )
                memories.append(memory)

        # Extract intent memories
        intent = message_data.get("intent")
        if intent:
            memory = MemoryItem(
                id=f"{session_id}_intent_{datetime.now().timestamp()}",
                type=MemoryType.INTENT,
                content=f"Intent: {intent}",
                priority=MemoryPriority.HIGH,
                created_at=datetime.now(),
                last_accessed=datetime.now(),
                metadata={"intent": intent},
            )
            memories.append(memory)

        # Extract action memories
        if message_data.get("actions_taken"):
            for action in message_data["actions_taken"]:
                memory = MemoryItem(
                    id=f"{session_id}_action_{datetime.now().timestamp()}",
                    type=MemoryType.ACTION,
                    content=f"Action: {action.get('action', 'unknown')}",
                    priority=MemoryPriority.HIGH,
                    created_at=datetime.now(),
                    last_accessed=datetime.now(),
                    metadata=action,
                )
                memories.append(memory)

        # Store memories
        for memory in memories:
            self._memories[session_id].append(memory)

        # Limit memories per session
        if len(self._memories[session_id]) > self.max_memories_per_session:
            # Keep only the most recent and highest priority memories
            self._memories[session_id].sort(
                key=lambda m: (m.priority.value, m.created_at), reverse=True
            )
            self._memories[session_id] = self._memories[session_id][
                : self.max_memories_per_session
            ]

    async def get_conversation_context(
        self, session_id: str, limit: int = 10
    ) -> Dict[str, Any]:
        """Get conversation context for a session."""
        conversation = await self.get_or_create_conversation(session_id)

        # Get recent conversation history
        recent_history = list(self._conversation_history[session_id])[-limit:]

        # Get relevant memories
        relevant_memories = await self._get_relevant_memories(session_id, limit=20)

        return {
            "session_id": session_id,
            "user_id": conversation.user_id,
            "message_count": conversation.message_count,
            "current_topic": conversation.current_topic,
            "conversation_summary": conversation.conversation_summary,
            "recent_history": recent_history,
            "entities": conversation.entities,
            "intents": conversation.intents[-5:],  # Last 5 intents
            "actions_taken": conversation.actions_taken[-10:],  # Last 10 actions
            "preferences": conversation.preferences,
            "relevant_memories": relevant_memories,
            "last_updated": conversation.last_updated.isoformat(),
        }

    async def _get_relevant_memories(
        self, session_id: str, limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get relevant memories for a session."""
        memories = self._memories.get(session_id, [])

        # Sort by priority and recency
        memories.sort(key=lambda m: (m.priority.value, m.last_accessed), reverse=True)

        # Return top memories as dictionaries
        return [
            {
                "id": memory.id,
                "type": memory.type.value,
                "content": memory.content,
                "priority": memory.priority.value,
                "created_at": memory.created_at.isoformat(),
                "metadata": memory.metadata,
            }
            for memory in memories[:limit]
        ]

    async def search_memories(
        self, session_id: str, query: str, memory_types: List[MemoryType] = None
    ) -> List[Dict[str, Any]]:
        """Search memories by content or metadata."""
        memories = self._memories.get(session_id, [])
        query_lower = query.lower()

        # Filter by memory types if specified
        if memory_types:
            memories = [m for m in memories if m.type in memory_types]

        # Search in content and metadata
        matching_memories = []
        for memory in memories:
            if query_lower in memory.content.lower() or any(
                query_lower in str(value).lower() for value in memory.metadata.values()
            ):
                matching_memories.append(
                    {
                        "id": memory.id,
                        "type": memory.type.value,
                        "content": memory.content,
                        "priority": memory.priority.value,
                        "created_at": memory.created_at.isoformat(),
                        "metadata": memory.metadata,
                    }
                )

        # Sort by relevance (priority and recency)
        matching_memories.sort(
            key=lambda m: (m["priority"], m["created_at"]), reverse=True
        )

        return matching_memories

    async def update_memory_access(self, session_id: str, memory_id: str):
        """Update memory access time and count."""
        memories = self._memories.get(session_id, [])
        for memory in memories:
            if memory.id == memory_id:
                memory.last_accessed = datetime.now()
                memory.access_count += 1
                break

    async def clear_conversation(self, session_id: str):
        """Clear all conversation data for a session."""
        if session_id in self._conversations:
            del self._conversations[session_id]
        if session_id in self._memories:
            del self._memories[session_id]
        if session_id in self._conversation_history:
            del self._conversation_history[session_id]

        logger.info(f"Cleared conversation data for session {session_id}")

    async def get_conversation_stats(self) -> Dict[str, Any]:
        """Get statistics about conversation memory usage."""
        total_conversations = len(self._conversations)
        total_memories = sum(len(memories) for memories in self._memories.values())

        # Memory type distribution
        memory_type_counts = defaultdict(int)
        for memories in self._memories.values():
            for memory in memories:
                memory_type_counts[memory.type.value] += 1

        return {
            "total_conversations": total_conversations,
            "total_memories": total_memories,
            "memory_type_distribution": dict(memory_type_counts),
            "average_memories_per_conversation": total_memories
            / max(total_conversations, 1),
        }

    async def shutdown(self):
        """Shutdown the memory service and cleanup tasks."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("Conversation memory service shutdown complete")


# Global instance
_conversation_memory_service: Optional[ConversationMemoryService] = None


async def get_conversation_memory_service() -> ConversationMemoryService:
    """Get the global conversation memory service instance."""
    global _conversation_memory_service
    if _conversation_memory_service is None:
        _conversation_memory_service = ConversationMemoryService()
    return _conversation_memory_service
