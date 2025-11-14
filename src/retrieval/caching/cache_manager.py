"""
Cache Manager for Warehouse Operational Assistant

Provides intelligent cache management including TTL configuration, eviction policies,
cache warming, and health monitoring.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
import json

from .redis_cache_service import RedisCacheService, CacheType, CacheConfig, CacheMetrics

logger = logging.getLogger(__name__)

class EvictionStrategy(Enum):
    """Cache eviction strategies."""
    LRU = "lru"  # Least Recently Used
    LFU = "lfu"  # Least Frequently Used
    TTL = "ttl"  # Time To Live
    SIZE = "size"  # Size-based eviction
    RANDOM = "random"

@dataclass
class CachePolicy:
    """Cache policy configuration."""
    max_size: int = 1000  # Maximum number of entries
    max_memory_mb: int = 100  # Maximum memory usage in MB
    default_ttl: int = 300  # Default TTL in seconds
    eviction_strategy: EvictionStrategy = EvictionStrategy.LRU
    warming_enabled: bool = True
    monitoring_enabled: bool = True
    compression_enabled: bool = True

@dataclass
class CacheWarmingRule:
    """Rule for cache warming."""
    cache_type: CacheType
    key_pattern: str
    data_generator: Callable[[], Any]
    priority: int = 1  # Higher number = higher priority
    frequency_minutes: int = 30  # How often to warm this data

class CacheManager:
    """
    Advanced cache manager with intelligent policies and monitoring.
    
    Features:
    - Configurable eviction policies
    - Cache warming with rules
    - Health monitoring and alerts
    - Performance optimization
    - Data freshness validation
    """
    
    def __init__(self, cache_service: RedisCacheService, policy: Optional[CachePolicy] = None):
        self.cache_service = cache_service
        self.policy = policy or CachePolicy()
        self.warming_rules: List[CacheWarmingRule] = []
        self.monitoring_callbacks: List[Callable[[CacheMetrics], None]] = []
        self._warming_task: Optional[asyncio.Task] = None
        self._monitoring_task: Optional[asyncio.Task] = None
        
    async def initialize(self) -> None:
        """Initialize cache manager and start background tasks."""
        try:
            # Initialize cache service
            await self.cache_service.initialize()
            
            # Start cache warming if enabled
            if self.policy.warming_enabled:
                self._warming_task = asyncio.create_task(self._warming_loop())
            
            # Start monitoring if enabled
            if self.policy.monitoring_enabled:
                self._monitoring_task = asyncio.create_task(self._monitoring_loop())
            
            logger.info("Cache manager initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize cache manager: {e}")
            raise
    
    async def shutdown(self) -> None:
        """Shutdown cache manager and stop background tasks."""
        try:
            # Cancel background tasks
            if self._warming_task:
                self._warming_task.cancel()
            if self._monitoring_task:
                self._monitoring_task.cancel()
            
            logger.info("Cache manager shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during cache manager shutdown: {e}")
    
    async def get_with_fallback(
        self, 
        key: str, 
        cache_type: CacheType,
        fallback_func: Callable[[], Any],
        ttl: Optional[int] = None
    ) -> Any:
        """
        Get data from cache with fallback to function if not found.
        
        Args:
            key: Cache key
            cache_type: Type of cached data
            fallback_func: Function to call if cache miss
            ttl: Time to live for cached data
            
        Returns:
            Cached data or result from fallback function
        """
        try:
            # Try to get from cache
            cached_data = await self.cache_service.get(key, cache_type)
            
            if cached_data is not None:
                logger.debug(f"Cache hit for {cache_type.value}:{key}")
                return cached_data
            
            # Cache miss - call fallback function
            logger.debug(f"Cache miss for {cache_type.value}:{key}, calling fallback")
            data = await fallback_func()
            
            # Cache the result
            if data is not None:
                await self.cache_service.set(key, data, cache_type, ttl)
            
            return data
            
        except Exception as e:
            logger.error(f"Error in get_with_fallback: {e}")
            # Fallback to function call
            return await fallback_func()
    
    async def invalidate_by_pattern(self, pattern: str, cache_type: CacheType) -> int:
        """
        Invalidate cache entries matching a pattern.
        
        Args:
            pattern: Pattern to match (supports wildcards)
            cache_type: Type of cache to search
            
        Returns:
            Number of entries invalidated
        """
        try:
            # Get all keys matching pattern
            full_pattern = f"warehouse:{cache_type.value}:{pattern}"
            keys = await self.cache_service.redis.keys(full_pattern)
            
            if keys:
                # Delete matching keys
                deleted = await self.cache_service.redis.delete(*keys)
                logger.info(f"Invalidated {deleted} cache entries matching pattern: {pattern}")
                return deleted
            
            return 0
            
        except Exception as e:
            logger.error(f"Error invalidating cache by pattern: {e}")
            return 0
    
    async def invalidate_by_ttl(self, cache_type: CacheType, max_age_seconds: int) -> int:
        """
        Invalidate cache entries older than specified age.
        
        Args:
            cache_type: Type of cache to check
            max_age_seconds: Maximum age in seconds
            
        Returns:
            Number of entries invalidated
        """
        try:
            pattern = f"warehouse:{cache_type.value}:*"
            keys = await self.cache_service.redis.keys(pattern)
            
            invalidated_count = 0
            cutoff_time = datetime.now() - timedelta(seconds=max_age_seconds)
            
            for key in keys:
                # Get TTL for key
                ttl = await self.cache_service.redis.ttl(key)
                
                if ttl == -1:  # No expiration set
                    # Check creation time from key metadata
                    # This is a simplified approach - in production, you'd store creation time
                    continue
                elif ttl > max_age_seconds:
                    # Key is too old
                    await self.cache_service.redis.delete(key)
                    invalidated_count += 1
            
            logger.info(f"Invalidated {invalidated_count} cache entries older than {max_age_seconds}s")
            return invalidated_count
            
        except Exception as e:
            logger.error(f"Error invalidating cache by TTL: {e}")
            return 0
    
    async def warm_cache_rule(self, rule: CacheWarmingRule) -> int:
        """
        Warm cache using a specific rule.
        
        Args:
            rule: Cache warming rule to execute
            
        Returns:
            Number of entries warmed
        """
        try:
            # Generate data using the rule's generator
            data = await rule.data_generator()
            
            if data is None:
                return 0
            
            # Generate cache key
            key = self.cache_service.generate_cache_key(rule.key_pattern)
            
            # Cache the data
            success = await self.cache_service.set(
                key, 
                data, 
                rule.cache_type,
                ttl=self.policy.default_ttl
            )
            
            if success:
                logger.info(f"Warmed cache for rule: {rule.key_pattern}")
                return 1
            
            return 0
            
        except Exception as e:
            logger.error(f"Error warming cache with rule {rule.key_pattern}: {e}")
            return 0
    
    def add_warming_rule(self, rule: CacheWarmingRule) -> None:
        """Add a cache warming rule."""
        self.warming_rules.append(rule)
        # Sort by priority (higher priority first)
        self.warming_rules.sort(key=lambda r: r.priority, reverse=True)
        logger.info(f"Added warming rule: {rule.key_pattern}")
    
    def add_monitoring_callback(self, callback: Callable[[CacheMetrics], None]) -> None:
        """Add a monitoring callback for cache metrics."""
        self.monitoring_callbacks.append(callback)
        logger.info("Added cache monitoring callback")
    
    async def get_cache_health(self) -> Dict[str, Any]:
        """Get comprehensive cache health information."""
        try:
            # Get basic health from cache service
            health = await self.cache_service.health_check()
            
            # Add manager-specific metrics
            health.update({
                "warming_rules_count": len(self.warming_rules),
                "monitoring_callbacks_count": len(self.monitoring_callbacks),
                "policy": {
                    "max_size": self.policy.max_size,
                    "max_memory_mb": self.policy.max_memory_mb,
                    "default_ttl": self.policy.default_ttl,
                    "eviction_strategy": self.policy.eviction_strategy.value,
                    "warming_enabled": self.policy.warming_enabled,
                    "monitoring_enabled": self.policy.monitoring_enabled
                }
            })
            
            return health
            
        except Exception as e:
            logger.error(f"Error getting cache health: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    async def optimize_cache(self) -> Dict[str, Any]:
        """
        Optimize cache performance by cleaning up and reorganizing.
        
        Returns:
            Optimization results
        """
        try:
            results = {
                "entries_cleaned": 0,
                "memory_freed_mb": 0,
                "optimization_time": 0
            }
            
            start_time = datetime.now()
            
            # Clean up expired entries
            for cache_type in CacheType:
                cleaned = await self.invalidate_by_ttl(cache_type, 0)  # Remove expired
                results["entries_cleaned"] += cleaned
            
            # Get memory usage before and after
            metrics_before = await self.cache_service.get_metrics()
            
            # Force garbage collection
            await self.cache_service.redis.memory_purge()
            
            metrics_after = await self.cache_service.get_metrics()
            results["memory_freed_mb"] = (metrics_before.memory_usage - metrics_after.memory_usage) / (1024 * 1024)
            
            results["optimization_time"] = (datetime.now() - start_time).total_seconds()
            
            logger.info(f"Cache optimization completed: {results}")
            return results
            
        except Exception as e:
            logger.error(f"Error optimizing cache: {e}")
            return {"error": str(e)}
    
    async def _warming_loop(self) -> None:
        """Background task for cache warming."""
        while True:
            try:
                logger.debug("Starting cache warming cycle")
                
                for rule in self.warming_rules:
                    try:
                        await self.warm_cache_rule(rule)
                        # Small delay between warming operations
                        await asyncio.sleep(0.1)
                    except Exception as e:
                        logger.error(f"Error in warming rule {rule.key_pattern}: {e}")
                
                # Wait before next warming cycle
                await asyncio.sleep(60)  # 1 minute between cycles
                
            except asyncio.CancelledError:
                logger.info("Cache warming loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in cache warming loop: {e}")
                await asyncio.sleep(60)  # Wait before retrying
    
    async def _monitoring_loop(self) -> None:
        """Background task for cache monitoring."""
        while True:
            try:
                # Get current metrics
                metrics = await self.cache_service.get_metrics()
                
                # Call monitoring callbacks
                for callback in self.monitoring_callbacks:
                    try:
                        callback(metrics)
                    except Exception as e:
                        logger.error(f"Error in monitoring callback: {e}")
                
                # Check for alerts
                await self._check_alerts(metrics)
                
                # Wait before next monitoring cycle
                await asyncio.sleep(30)  # 30 seconds between checks
                
            except asyncio.CancelledError:
                logger.info("Cache monitoring loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in cache monitoring loop: {e}")
                await asyncio.sleep(30)  # Wait before retrying
    
    async def _check_alerts(self, metrics: CacheMetrics) -> None:
        """Check for cache alerts and warnings."""
        try:
            # Low hit rate alert
            if metrics.hit_rate < 0.3:
                logger.warning(f"Low cache hit rate: {metrics.hit_rate:.2%}")
            
            # High memory usage alert
            if metrics.memory_usage > 80 * 1024 * 1024:  # 80MB
                logger.warning(f"High cache memory usage: {metrics.memory_usage / (1024 * 1024):.1f}MB")
            
            # Too many keys alert
            if metrics.key_count > self.policy.max_size:
                logger.warning(f"Cache key count exceeds limit: {metrics.key_count} > {self.policy.max_size}")
                
        except Exception as e:
            logger.error(f"Error checking cache alerts: {e}")

# Global cache manager instance
_cache_manager: Optional[CacheManager] = None

async def get_cache_manager() -> CacheManager:
    """Get or create the global cache manager instance."""
    global _cache_manager
    if _cache_manager is None:
        from .redis_cache_service import get_cache_service
        cache_service = await get_cache_service()
        _cache_manager = CacheManager(cache_service)
        await _cache_manager.initialize()
    return _cache_manager
