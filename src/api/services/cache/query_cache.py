"""
Query Result Cache Service

Provides caching for chat query results to avoid reprocessing identical queries.
"""

import hashlib
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import asyncio

logger = logging.getLogger(__name__)


class QueryCache:
    """Simple in-memory cache for query results with TTL support."""

    def __init__(self, default_ttl_seconds: int = 300):  # 5 minutes default
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.default_ttl = default_ttl_seconds
        self._lock = asyncio.Lock()

    def _generate_cache_key(self, message: str, session_id: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Generate a cache key from query parameters."""
        # Normalize the message (lowercase, strip whitespace)
        normalized_message = message.lower().strip()
        
        # Create a hash of the query
        cache_data = {
            "message": normalized_message,
            "session_id": session_id,
            "context": context or {},
        }
        cache_string = json.dumps(cache_data, sort_keys=True)
        cache_key = hashlib.sha256(cache_string.encode()).hexdigest()
        
        return cache_key

    async def get(self, message: str, session_id: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Get a cached result if available and not expired."""
        async with self._lock:
            cache_key = self._generate_cache_key(message, session_id, context)
            
            if cache_key not in self.cache:
                return None
            
            cached_item = self.cache[cache_key]
            expires_at = cached_item.get("expires_at")
            
            # Check if expired
            if expires_at and datetime.utcnow() > expires_at:
                del self.cache[cache_key]
                logger.debug(f"Cache entry expired for key: {cache_key[:16]}...")
                return None
            
            logger.info(f"Cache hit for query: {message[:50]}...")
            return cached_item.get("result")

    async def set(
        self,
        message: str,
        session_id: str,
        result: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Cache a query result with optional TTL."""
        async with self._lock:
            cache_key = self._generate_cache_key(message, session_id, context)
            ttl = ttl_seconds or self.default_ttl
            expires_at = datetime.utcnow() + timedelta(seconds=ttl)
            
            self.cache[cache_key] = {
                "result": result,
                "expires_at": expires_at,
                "cached_at": datetime.utcnow(),
            }
            
            logger.info(f"Cached result for query: {message[:50]}... (TTL: {ttl}s)")

    async def clear(self) -> None:
        """Clear all cached entries."""
        async with self._lock:
            self.cache.clear()
            logger.info("Query cache cleared")

    async def clear_expired(self) -> None:
        """Remove expired entries from cache."""
        async with self._lock:
            now = datetime.utcnow()
            expired_keys = [
                key for key, item in self.cache.items()
                if item.get("expires_at") and now > item["expires_at"]
            ]
            
            for key in expired_keys:
                del self.cache[key]
            
            if expired_keys:
                logger.info(f"Cleared {len(expired_keys)} expired cache entries")

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        async with self._lock:
            await self.clear_expired()  # Clean up expired entries first
            
            return {
                "total_entries": len(self.cache),
                "default_ttl_seconds": self.default_ttl,
            }


# Global cache instance
_query_cache: Optional[QueryCache] = None


def get_query_cache() -> QueryCache:
    """Get the global query cache instance."""
    global _query_cache
    if _query_cache is None:
        _query_cache = QueryCache()
    return _query_cache

