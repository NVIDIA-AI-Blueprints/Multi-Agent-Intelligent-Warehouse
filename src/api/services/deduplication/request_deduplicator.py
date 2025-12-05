"""
Request Deduplication Service

Prevents duplicate concurrent requests from being processed simultaneously.
Uses request hashing and async locks to ensure only one instance of identical requests runs at a time.
"""

import hashlib
import json
import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class RequestDeduplicator:
    """Service to deduplicate concurrent requests."""

    def __init__(self):
        self.active_requests: Dict[str, asyncio.Task] = {}
        self.request_results: Dict[str, Any] = {}
        self.request_locks: Dict[str, asyncio.Lock] = {}
        self._cleanup_interval = 300  # 5 minutes
        self._result_ttl = 600  # 10 minutes

    def _generate_request_key(
        self,
        message: str,
        session_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Generate a unique key for a request."""
        # Normalize the message
        normalized_message = message.lower().strip()
        
        # Create a hash of the request
        request_data = {
            "message": normalized_message,
            "session_id": session_id,
            "context": context or {},
        }
        request_string = json.dumps(request_data, sort_keys=True)
        request_key = hashlib.sha256(request_string.encode()).hexdigest()
        
        return request_key

    async def get_or_create_task(
        self,
        request_key: str,
        task_factory: callable
    ) -> Any:
        """
        Get existing task result or create a new task if not already running.
        
        Args:
            request_key: Unique key for the request
            task_factory: Async function that creates the task
            
        Returns:
            Result from the task
        """
        # Check if we have a cached result
        if request_key in self.request_results:
            result_data = self.request_results[request_key]
            if result_data.get("expires_at") and datetime.utcnow() < result_data["expires_at"]:
                logger.info(f"Returning cached result for duplicate request: {request_key[:16]}...")
                return result_data["result"]
            else:
                # Expired, remove it
                del self.request_results[request_key]

        # Get or create lock for this request
        if request_key not in self.request_locks:
            self.request_locks[request_key] = asyncio.Lock()

        lock = self.request_locks[request_key]

        async with lock:
            # Check again after acquiring lock (double-check pattern)
            if request_key in self.request_results:
                result_data = self.request_results[request_key]
                if result_data.get("expires_at") and datetime.utcnow() < result_data["expires_at"]:
                    logger.info(f"Returning cached result (after lock): {request_key[:16]}...")
                    return result_data["result"]

            # Check if there's an active task
            if request_key in self.active_requests:
                active_task = self.active_requests[request_key]
                if not active_task.done():
                    logger.info(f"Waiting for existing task for duplicate request: {request_key[:16]}...")
                    try:
                        result = await active_task
                        # Cache the result
                        self.request_results[request_key] = {
                            "result": result,
                            "expires_at": datetime.utcnow() + timedelta(seconds=self._result_ttl),
                            "cached_at": datetime.utcnow(),
                        }
                        return result
                    except Exception as e:
                        logger.error(f"Error waiting for duplicate request task: {e}")
                        # Remove failed task and continue to create new one
                        del self.active_requests[request_key]

            # Create new task
            logger.info(f"Creating new task for request: {request_key[:16]}...")
            task = asyncio.create_task(task_factory())
            self.active_requests[request_key] = task

            try:
                result = await task
                # Cache the result
                self.request_results[request_key] = {
                    "result": result,
                    "expires_at": datetime.utcnow() + timedelta(seconds=self._result_ttl),
                    "cached_at": datetime.utcnow(),
                }
                return result
            finally:
                # Clean up active task
                if request_key in self.active_requests:
                    del self.active_requests[request_key]

    async def cleanup_expired(self) -> None:
        """Remove expired results and clean up locks."""
        now = datetime.utcnow()
        
        # Remove expired results
        expired_keys = [
            key for key, data in self.request_results.items()
            if data.get("expires_at") and now > data["expires_at"]
        ]
        
        for key in expired_keys:
            del self.request_results[key]
            # Also clean up lock if no active request
            if key in self.request_locks and key not in self.active_requests:
                del self.request_locks[key]
        
        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired request results")

    async def get_stats(self) -> Dict[str, Any]:
        """Get deduplication statistics."""
        await self.cleanup_expired()
        
        return {
            "active_requests": len(self.active_requests),
            "cached_results": len(self.request_results),
            "active_locks": len(self.request_locks),
        }


# Global deduplicator instance
_request_deduplicator: Optional[RequestDeduplicator] = None


def get_request_deduplicator() -> RequestDeduplicator:
    """Get the global request deduplicator instance."""
    global _request_deduplicator
    if _request_deduplicator is None:
        _request_deduplicator = RequestDeduplicator()
    return _request_deduplicator

