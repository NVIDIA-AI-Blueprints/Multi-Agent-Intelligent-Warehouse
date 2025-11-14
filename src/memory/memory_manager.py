"""
Memory Manager for Warehouse Operations Assistant

Provides intelligent conversation persistence, user context management,
and knowledge base updates for the warehouse operations assistant.
"""

import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
import json
from datetime import datetime, timedelta
import asyncio
import uuid

from src.api.services.llm.nim_client import get_nim_client, LLMResponse
from src.retrieval.structured.sql_retriever import get_sql_retriever

logger = logging.getLogger(__name__)

@dataclass
class ConversationTurn:
    """Single conversation turn."""
    turn_id: str
    session_id: str
    user_query: str
    agent_response: str
    intent: str
    entities: Dict[str, Any]
    timestamp: datetime
    metadata: Dict[str, Any]

@dataclass
class UserProfile:
    """User profile information."""
    user_id: str
    name: str
    role: str
    preferences: Dict[str, Any]
    last_active: datetime
    conversation_count: int

@dataclass
class SessionContext:
    """Session context information."""
    session_id: str
    user_id: str
    start_time: datetime
    last_activity: datetime
    current_focus: Optional[str]
    conversation_summary: str
    key_entities: Dict[str, Any]

class MemoryManager:
    """
    Memory Manager with NVIDIA NIM integration.
    
    Provides comprehensive memory management capabilities including:
    - Chat history persistence and retrieval
    - User profile and preferences management
    - Session context and conversation summarization
    - Knowledge base updates and learning
    - Cross-session context awareness
    """
    
    def __init__(self):
        self.nim_client = None
        self.sql_retriever = None
        self.active_sessions = {}  # In-memory session cache
        self.user_profiles = {}  # In-memory user profile cache
    
    async def initialize(self) -> None:
        """Initialize the memory manager with required services."""
        try:
            self.nim_client = await get_nim_client()
            self.sql_retriever = await get_sql_retriever()
            
            # Initialize memory tables if they don't exist
            await self._initialize_memory_tables()
            
            logger.info("Memory Manager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Memory Manager: {e}")
            raise
    
    async def _initialize_memory_tables(self) -> None:
        """Initialize memory-related database tables."""
        try:
            # Create conversation_history table
            conversation_table = """
            CREATE TABLE IF NOT EXISTS conversation_history (
                turn_id VARCHAR(36) PRIMARY KEY,
                session_id VARCHAR(36) NOT NULL,
                user_id VARCHAR(36) NOT NULL,
                user_query TEXT NOT NULL,
                agent_response TEXT NOT NULL,
                intent VARCHAR(50) NOT NULL,
                entities JSONB DEFAULT '{}'::jsonb,
                timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                metadata JSONB DEFAULT '{}'::jsonb
            );
            """
            
            # Create user_profiles table
            profiles_table = """
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id VARCHAR(36) PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                role VARCHAR(100) NOT NULL,
                preferences JSONB DEFAULT '{}'::jsonb,
                last_active TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                conversation_count INTEGER DEFAULT 0,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """
            
            # Create session_contexts table
            sessions_table = """
            CREATE TABLE IF NOT EXISTS session_contexts (
                session_id VARCHAR(36) PRIMARY KEY,
                user_id VARCHAR(36) NOT NULL,
                start_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                last_activity TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                current_focus VARCHAR(100),
                conversation_summary TEXT,
                key_entities JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
            """
            
            # Create indexes for better performance
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_conversation_session ON conversation_history(session_id);",
                "CREATE INDEX IF NOT EXISTS idx_conversation_user ON conversation_history(user_id);",
                "CREATE INDEX IF NOT EXISTS idx_conversation_timestamp ON conversation_history(timestamp);",
                "CREATE INDEX IF NOT EXISTS idx_sessions_user ON session_contexts(user_id);",
                "CREATE INDEX IF NOT EXISTS idx_sessions_activity ON session_contexts(last_activity);"
            ]
            
            # Execute all table creation and index statements
            await self.sql_retriever.execute_command(conversation_table)
            await self.sql_retriever.execute_command(profiles_table)
            await self.sql_retriever.execute_command(sessions_table)
            
            for index_sql in indexes:
                await self.sql_retriever.execute_command(index_sql)
            
            logger.info("Memory tables initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize memory tables: {e}")
            raise
    
    async def store_conversation_turn(
        self,
        session_id: str,
        user_id: str,
        user_query: str,
        agent_response: str,
        intent: str,
        entities: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Store a conversation turn in memory.
        
        Args:
            session_id: Session identifier
            user_id: User identifier
            user_query: User's query
            agent_response: Agent's response
            intent: Detected intent
            entities: Extracted entities
            metadata: Additional metadata
            
        Returns:
            turn_id: Unique identifier for this conversation turn
        """
        try:
            turn_id = str(uuid.uuid4())
            timestamp = datetime.now()
            
            # Store in database
            query = """
            INSERT INTO conversation_history 
            (turn_id, session_id, user_id, user_query, agent_response, intent, entities, timestamp, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """
            
            await self.sql_retriever.execute_command(
                query,
                turn_id, session_id, user_id, user_query, agent_response, intent, json.dumps(entities), timestamp, json.dumps(metadata or {})
            )
            
            # Update session context
            await self._update_session_context(session_id, user_id, intent, entities)
            
            # Update user profile
            await self._update_user_profile(user_id)
            
            logger.info(f"Stored conversation turn {turn_id} for session {session_id}")
            return turn_id
            
        except Exception as e:
            logger.error(f"Failed to store conversation turn: {e}")
            raise
    
    async def get_conversation_history(
        self,
        session_id: str,
        limit: int = 10,
        include_metadata: bool = False
    ) -> List[ConversationTurn]:
        """
        Retrieve conversation history for a session.
        
        Args:
            session_id: Session identifier
            limit: Maximum number of turns to retrieve
            include_metadata: Whether to include metadata
            
        Returns:
            List of conversation turns
        """
        try:
            query = """
            SELECT turn_id, session_id, user_query, agent_response, intent, entities, timestamp, metadata
            FROM conversation_history
            WHERE session_id = $1
            ORDER BY timestamp DESC
            LIMIT $2
            """
            
            results = await self.sql_retriever.fetch_all(query, session_id, limit)
            
            turns = []
            for row in results:
                turn = ConversationTurn(
                    turn_id=row['turn_id'],
                    session_id=row['session_id'],
                    user_query=row['user_query'],
                    agent_response=row['agent_response'],
                    intent=row['intent'],
                    entities=json.loads(row['entities']) if row['entities'] else {},
                    timestamp=row['timestamp'],
                    metadata=json.loads(row['metadata']) if row['metadata'] and include_metadata else {}
                )
                turns.append(turn)
            
            # Return in chronological order (oldest first)
            return list(reversed(turns))
            
        except Exception as e:
            logger.error(f"Failed to get conversation history: {e}")
            return []
    
    async def get_user_profile(self, user_id: str) -> Optional[UserProfile]:
        """
        Get user profile information.
        
        Args:
            user_id: User identifier
            
        Returns:
            UserProfile or None if not found
        """
        try:
            # Check cache first
            if user_id in self.user_profiles:
                return self.user_profiles[user_id]
            
            query = """
            SELECT user_id, name, role, preferences, last_active, conversation_count
            FROM user_profiles
            WHERE user_id = $1
            """
            
            result = await self.sql_retriever.fetch_one(query, user_id)
            
            if result:
                profile = UserProfile(
                    user_id=result['user_id'],
                    name=result['name'],
                    role=result['role'],
                    preferences=json.loads(result['preferences']) if result['preferences'] else {},
                    last_active=result['last_active'],
                    conversation_count=result['conversation_count']
                )
                
                # Cache the profile
                self.user_profiles[user_id] = profile
                return profile
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get user profile: {e}")
            return None
    
    async def create_or_update_user_profile(
        self,
        user_id: str,
        name: str,
        role: str,
        preferences: Optional[Dict[str, Any]] = None
    ) -> UserProfile:
        """
        Create or update user profile.
        
        Args:
            user_id: User identifier
            name: User's name
            role: User's role
            preferences: User preferences
            
        Returns:
            Updated UserProfile
        """
        try:
            preferences = preferences or {}
            
            query = """
            INSERT INTO user_profiles (user_id, name, role, preferences, last_active, conversation_count)
            VALUES ($1, $2, $3, $4, NOW(), 0)
            ON CONFLICT (user_id) DO UPDATE SET
                name = EXCLUDED.name,
                role = EXCLUDED.role,
                preferences = EXCLUDED.preferences,
                last_active = NOW(),
                updated_at = NOW()
            RETURNING user_id, name, role, preferences, last_active, conversation_count
            """
            
            result = await self.sql_retriever.fetch_one(
                query,
                user_id,
                name,
                role,
                json.dumps(preferences)
            )
            
            profile = UserProfile(
                user_id=result['user_id'],
                name=result['name'],
                role=result['role'],
                preferences=json.loads(result['preferences']) if result['preferences'] else {},
                last_active=result['last_active'],
                conversation_count=result['conversation_count']
            )
            
            # Update cache
            self.user_profiles[user_id] = profile
            
            logger.info(f"Created/updated user profile for {user_id}")
            return profile
            
        except Exception as e:
            logger.error(f"Failed to create/update user profile: {e}")
            raise
    
    async def get_session_context(self, session_id: str) -> Optional[SessionContext]:
        """
        Get session context information.
        
        Args:
            session_id: Session identifier
            
        Returns:
            SessionContext or None if not found
        """
        try:
            # Check cache first
            if session_id in self.active_sessions:
                return self.active_sessions[session_id]
            
            query = """
            SELECT session_id, user_id, start_time, last_activity, current_focus, 
                   conversation_summary, key_entities
            FROM session_contexts
            WHERE session_id = $1
            """
            
            result = await self.sql_retriever.fetch_one(query, session_id)
            
            if result:
                context = SessionContext(
                    session_id=result['session_id'],
                    user_id=result['user_id'],
                    start_time=result['start_time'],
                    last_activity=result['last_activity'],
                    current_focus=result['current_focus'],
                    conversation_summary=result['conversation_summary'] or "",
                    key_entities=json.loads(result['key_entities']) if result['key_entities'] else {}
                )
                
                # Cache the context
                self.active_sessions[session_id] = context
                return context
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get session context: {e}")
            return None
    
    async def create_session_context(
        self,
        session_id: str,
        user_id: str
    ) -> SessionContext:
        """
        Create a new session context.
        
        Args:
            session_id: Session identifier
            user_id: User identifier
            
        Returns:
            New SessionContext
        """
        try:
            query = """
            INSERT INTO session_contexts (session_id, user_id, start_time, last_activity)
            VALUES ($1, $2, NOW(), NOW())
            RETURNING session_id, user_id, start_time, last_activity, current_focus, 
                      conversation_summary, key_entities
            """
            
            result = await self.sql_retriever.fetch_one(query, session_id, user_id)
            
            context = SessionContext(
                session_id=result['session_id'],
                user_id=result['user_id'],
                start_time=result['start_time'],
                last_activity=result['last_activity'],
                current_focus=result['current_focus'],
                conversation_summary=result['conversation_summary'] or "",
                key_entities=json.loads(result['key_entities']) if result['key_entities'] else {}
            )
            
            # Cache the context
            self.active_sessions[session_id] = context
            
            logger.info(f"Created session context for {session_id}")
            return context
            
        except Exception as e:
            logger.error(f"Failed to create session context: {e}")
            raise
    
    async def _update_session_context(
        self,
        session_id: str,
        user_id: str,
        intent: str,
        entities: Dict[str, Any]
    ) -> None:
        """Update session context with new information."""
        try:
            # Get current context
            context = await self.get_session_context(session_id)
            if not context:
                context = await self.create_session_context(session_id, user_id)
            
            # Update current focus if intent is specific
            if intent not in ["general", "unknown"]:
                context.current_focus = intent
            
            # Merge entities
            context.key_entities.update(entities)
            
            # Generate conversation summary using LLM
            summary = await self._generate_conversation_summary(session_id)
            context.conversation_summary = summary
            
            # Update in database
            query = """
            UPDATE session_contexts 
            SET last_activity = NOW(), current_focus = $2, conversation_summary = $3, 
                key_entities = $4, updated_at = NOW()
            WHERE session_id = $1
            """
            
            await self.sql_retriever.execute_command(
                query,
                session_id, context.current_focus, context.conversation_summary, json.dumps(context.key_entities)
            )
            
            # Update cache
            self.active_sessions[session_id] = context
            
        except Exception as e:
            logger.error(f"Failed to update session context: {e}")
    
    async def _update_user_profile(self, user_id: str) -> None:
        """Update user profile with activity."""
        try:
            query = """
            UPDATE user_profiles 
            SET last_active = NOW(), conversation_count = conversation_count + 1, updated_at = NOW()
            WHERE user_id = $1
            """
            
            await self.sql_retriever.execute_command(query, user_id)
            
            # Update cache if exists
            if user_id in self.user_profiles:
                self.user_profiles[user_id].last_active = datetime.now()
                self.user_profiles[user_id].conversation_count += 1
            
        except Exception as e:
            logger.error(f"Failed to update user profile: {e}")
    
    async def _generate_conversation_summary(self, session_id: str) -> str:
        """Generate conversation summary using LLM."""
        try:
            # Get recent conversation history
            history = await self.get_conversation_history(session_id, limit=5)
            
            if not history:
                return "No conversation history available"
            
            # Build context for LLM
            conversation_text = ""
            for turn in history:
                conversation_text += f"User: {turn.user_query}\nAgent: {turn.agent_response}\n\n"
            
            prompt = f"""
Summarize the following warehouse operations conversation in 2-3 sentences, focusing on:
1. The main topics discussed
2. Key decisions or actions taken
3. Current focus or ongoing issues

Conversation:
{conversation_text}

Provide a concise summary:
"""
            
            messages = [
                {"role": "system", "content": "You are an expert at summarizing warehouse operations conversations. Be concise and focus on key points."},
                {"role": "user", "content": prompt}
            ]
            
            response = await self.nim_client.generate_response(messages, temperature=0.3)
            return response.content.strip()
            
        except Exception as e:
            logger.error(f"Failed to generate conversation summary: {e}")
            return "Summary generation failed"
    
    async def get_context_for_query(
        self,
        session_id: str,
        user_id: str,
        query: str
    ) -> Dict[str, Any]:
        """
        Get relevant context for a new query.
        
        Args:
            session_id: Session identifier
            user_id: User identifier
            query: New user query
            
        Returns:
            Context dictionary with relevant information
        """
        try:
            context = {
                "session_context": None,
                "user_profile": None,
                "recent_history": [],
                "relevant_entities": {}
            }
            
            # Get session context
            session_context = await self.get_session_context(session_id)
            if session_context:
                context["session_context"] = asdict(session_context)
            
            # Get user profile
            user_profile = await self.get_user_profile(user_id)
            if user_profile:
                context["user_profile"] = asdict(user_profile)
            
            # Get recent conversation history
            recent_history = await self.get_conversation_history(session_id, limit=3)
            context["recent_history"] = [asdict(turn) for turn in recent_history]
            
            # Extract relevant entities from session context
            if session_context and session_context.key_entities:
                context["relevant_entities"] = session_context.key_entities
            
            return context
            
        except Exception as e:
            logger.error(f"Failed to get context for query: {e}")
            return {}
    
    async def clear_session_context(self, session_id: str) -> None:
        """Clear session context and remove from cache."""
        try:
            # Remove from cache
            if session_id in self.active_sessions:
                del self.active_sessions[session_id]
            
            # Update database to mark as inactive
            query = """
            UPDATE session_contexts 
            SET last_activity = NOW(), current_focus = NULL, updated_at = NOW()
            WHERE session_id = $1
            """
            
            await self.sql_retriever.execute_command(query, session_id)
            
            logger.info(f"Cleared session context for {session_id}")
            
        except Exception as e:
            logger.error(f"Failed to clear session context: {e}")
    
    async def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory usage statistics."""
        try:
            stats = {}
            
            # Get conversation count
            conv_count = await self.sql_retriever.fetch_scalar(
                "SELECT COUNT(*) FROM conversation_history"
            )
            stats["total_conversations"] = conv_count or 0
            
            # Get user count
            user_count = await self.sql_retriever.fetch_scalar(
                "SELECT COUNT(*) FROM user_profiles"
            )
            stats["total_users"] = user_count or 0
            
            # Get active session count
            active_sessions = await self.sql_retriever.fetch_scalar(
                "SELECT COUNT(*) FROM session_contexts WHERE last_activity > NOW() - INTERVAL '1 hour'"
            )
            stats["active_sessions"] = active_sessions or 0
            
            # Get cache stats
            stats["cached_sessions"] = len(self.active_sessions)
            stats["cached_profiles"] = len(self.user_profiles)
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get memory stats: {e}")
            return {}

# Global memory manager instance
_memory_manager: Optional[MemoryManager] = None

async def get_memory_manager() -> MemoryManager:
    """Get or create the global memory manager instance."""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
        await _memory_manager.initialize()
    return _memory_manager
