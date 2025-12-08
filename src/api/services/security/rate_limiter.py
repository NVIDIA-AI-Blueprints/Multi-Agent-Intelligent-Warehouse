"""
Rate Limiting Service for API Protection

Provides rate limiting functionality to prevent DoS attacks and abuse.
Uses Redis for distributed rate limiting across multiple instances.
"""

import os
import time
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from fastapi import Request, HTTPException, status

# Try to import redis, fallback to None if not available
try:
    import redis.asyncio as redis
except ImportError:
    redis = None

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Rate limiter using Redis for distributed rate limiting.
    
    Falls back to in-memory rate limiting if Redis is unavailable.
    """

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self.redis_available = False
        self.in_memory_store: Dict[str, Dict[str, Any]] = {}
        
        # Rate limit configurations (requests per window)
        self.limits = {
            "default": {"requests": 100, "window_seconds": 60},  # 100 req/min
            "/api/v1/chat": {"requests": 30, "window_seconds": 60},  # 30 req/min for chat
            "/api/v1/auth/login": {"requests": 5, "window_seconds": 60},  # 5 req/min for login
            "/api/v1/document/upload": {"requests": 10, "window_seconds": 60},  # 10 req/min for uploads
            "/api/v1/health": {"requests": 1000, "window_seconds": 60},  # 1000 req/min for health
        }

    async def initialize(self):
        """Initialize Redis connection for distributed rate limiting."""
        if redis is None:
            logger.warning("Redis not available, using in-memory rate limiting")
            self.redis_available = False
            return
        
        try:
            redis_host = os.getenv("REDIS_HOST", "localhost")
            redis_port = int(os.getenv("REDIS_PORT", "6379"))
            redis_password = os.getenv("REDIS_PASSWORD")
            redis_db = int(os.getenv("REDIS_DB", "0"))
            
            # Build Redis URL
            if redis_password:
                redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}/{redis_db}"
            else:
                redis_url = f"redis://{redis_host}:{redis_port}/{redis_db}"
            
            self.redis_client = redis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            
            # Test connection
            await self.redis_client.ping()
            self.redis_available = True
            logger.info("✅ Rate limiter initialized with Redis (distributed)")
            
        except Exception as e:
            logger.warning(f"Redis not available for rate limiting, using in-memory fallback: {e}")
            self.redis_available = False
            self.redis_client = None

    async def close(self):
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()

    def _get_client_identifier(self, request: Request) -> str:
        """
        Get client identifier for rate limiting.
        
        Uses IP address as primary identifier. In production, consider
        using authenticated user ID for authenticated endpoints.
        """
        # Get client IP
        client_ip = request.client.host if request.client else "unknown"
        
        # For authenticated requests, could use user ID instead
        # user_id = getattr(request.state, "user_id", None)
        # if user_id:
        #     return f"user:{user_id}"
        
        return f"ip:{client_ip}"

    def _get_rate_limit_config(self, path: str) -> Dict[str, int]:
        """Get rate limit configuration for a specific path."""
        # Check for exact path match
        if path in self.limits:
            return self.limits[path]
        
        # Check for prefix matches
        for limit_path, config in self.limits.items():
            if path.startswith(limit_path):
                return config
        
        # Return default
        return self.limits["default"]

    async def check_rate_limit(self, request: Request) -> bool:
        """
        Check if request is within rate limit.
        
        Args:
            request: FastAPI request object
            
        Returns:
            True if request is allowed, False if rate limited
            
        Raises:
            HTTPException: If rate limit is exceeded
        """
        try:
            client_id = self._get_client_identifier(request)
            path = request.url.path
            config = self._get_rate_limit_config(path)
            
            key = f"rate_limit:{path}:{client_id}"
            requests_allowed = config["requests"]
            window_seconds = config["window_seconds"]
            
            if self.redis_available and self.redis_client:
                # Use Redis for distributed rate limiting
                return await self._check_redis_rate_limit(
                    key, requests_allowed, window_seconds
                )
            else:
                # Use in-memory rate limiting
                return await self._check_memory_rate_limit(
                    key, requests_allowed, window_seconds
                )
                
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            # On error, allow the request (fail open)
            return True

    async def _check_redis_rate_limit(
        self, key: str, requests_allowed: int, window_seconds: int
    ) -> bool:
        """Check rate limit using Redis."""
        try:
            current_time = time.time()
            window_start = current_time - window_seconds
            
            # Use Redis sorted set for sliding window
            pipe = self.redis_client.pipeline()
            
            # Remove old entries outside the window
            pipe.zremrangebyscore(key, 0, window_start)
            
            # Count current requests in window
            pipe.zcard(key)
            
            # Add current request
            pipe.zadd(key, {str(current_time): current_time})
            
            # Set expiration
            pipe.expire(key, window_seconds)
            
            results = await pipe.execute()
            current_count = results[1]  # Result from zcard
            
            # Check if limit exceeded
            if current_count >= requests_allowed:
                # Get time until next request is allowed
                oldest_request = await self.redis_client.zrange(key, 0, 0, withscores=True)
                if oldest_request:
                    oldest_time = oldest_request[0][1]
                    retry_after = int(window_seconds - (current_time - oldest_time))
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail=f"Rate limit exceeded. Please try again in {retry_after} seconds.",
                        headers={"Retry-After": str(retry_after)},
                    )
            
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Redis rate limit check failed: {e}")
            return True  # Fail open

    async def _check_memory_rate_limit(
        self, key: str, requests_allowed: int, window_seconds: int
    ) -> bool:
        """Check rate limit using in-memory storage."""
        try:
            current_time = time.time()
            window_start = current_time - window_seconds
            
            # Get or create entry for this key
            if key not in self.in_memory_store:
                self.in_memory_store[key] = {
                    "requests": [],
                    "last_cleanup": current_time,
                }
            
            entry = self.in_memory_store[key]
            
            # Cleanup old entries periodically
            if current_time - entry["last_cleanup"] > window_seconds:
                entry["requests"] = [
                    req_time
                    for req_time in entry["requests"]
                    if req_time > window_start
                ]
                entry["last_cleanup"] = current_time
                
                # Remove empty entries
                if not entry["requests"]:
                    del self.in_memory_store[key]
                    return True
            
            # Remove old requests outside window
            entry["requests"] = [
                req_time for req_time in entry["requests"] if req_time > window_start
            ]
            
            # Check if limit exceeded
            if len(entry["requests"]) >= requests_allowed:
                oldest_request = min(entry["requests"]) if entry["requests"] else current_time
                retry_after = int(window_seconds - (current_time - oldest_request))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Please try again in {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)},
                )
            
            # Add current request
            entry["requests"].append(current_time)
            
            return True
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Memory rate limit check failed: {e}")
            return True  # Fail open


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


async def get_rate_limiter() -> RateLimiter:
    """Get or create rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
        await _rate_limiter.initialize()
    return _rate_limiter

