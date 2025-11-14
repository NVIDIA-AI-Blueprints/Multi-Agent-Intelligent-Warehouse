"""
Redis Caching Service for Warehouse Operational Assistant

Provides intelligent caching for SQL results, evidence packs, and frequently accessed data
with configurable TTL, monitoring, and eviction policies.
"""

import json
import logging
import hashlib
import asyncio
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import redis.asyncio as redis
from redis.asyncio import Redis
import pickle
import gzip

logger = logging.getLogger(__name__)

class CacheType(Enum):
    """Types of cached data."""
    SQL_RESULT = "sql_result"
    EVIDENCE_PACK = "evidence_pack"
    VECTOR_SEARCH = "vector_search"
    QUERY_PREPROCESSING = "query_preprocessing"
    WORKFORCE_DATA = "workforce_data"
    TASK_DATA = "task_data"
    EQUIPMENT_DATA = "equipment_data"

class CachePolicy(Enum):
    """Cache eviction policies."""
    LRU = "lru"  # Least Recently Used
    LFU = "lfu"  # Least Frequently Used
    TTL = "ttl"  # Time To Live
    RANDOM = "random"

@dataclass
class CacheConfig:
    """Configuration for caching behavior."""
    default_ttl: int = 300  # 5 minutes default
    max_memory: str = "100mb"
    eviction_policy: CachePolicy = CachePolicy.LRU
    compression_enabled: bool = True
    monitoring_enabled: bool = True
    warming_enabled: bool = True

@dataclass
class CacheMetrics:
    """Cache performance metrics."""
    hits: int = 0
    misses: int = 0
    hit_rate: float = 0.0
    total_requests: int = 0
    memory_usage: int = 0
    key_count: int = 0
    evictions: int = 0
    last_updated: datetime = None

@dataclass
class CacheEntry:
    """Individual cache entry with metadata."""
    key: str
    data: Any
    cache_type: CacheType
    created_at: datetime
    expires_at: datetime
    access_count: int = 0
    last_accessed: datetime = None
    source_metadata: Optional[Dict[str, Any]] = None
    compressed: bool = False

class RedisCacheService:
    """
    Advanced Redis caching service with intelligent management.
    
    Features:
    - Configurable TTL for different data types
    - Compression for large data
    - Hit/miss monitoring
    - Cache warming
    - Eviction policies
    - Health monitoring
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379", config: Optional[CacheConfig] = None):
        self.redis_url = redis_url
        self.config = config or CacheConfig()
        self.redis: Optional[Redis] = None
        self.metrics = CacheMetrics()
        self.cache_ttl_map = {
            CacheType.SQL_RESULT: 300,  # 5 minutes
            CacheType.EVIDENCE_PACK: 600,  # 10 minutes
            CacheType.VECTOR_SEARCH: 180,  # 3 minutes
            CacheType.QUERY_PREPROCESSING: 900,  # 15 minutes
            CacheType.WORKFORCE_DATA: 300,  # 5 minutes
            CacheType.TASK_DATA: 180,  # 3 minutes
            CacheType.EQUIPMENT_DATA: 600,  # 10 minutes
        }
        
    async def initialize(self) -> None:
        """Initialize Redis connection and configure cache."""
        try:
            self.redis = redis.from_url(self.redis_url, decode_responses=False)
            
            # Test connection
            await self.redis.ping()
            
            # Configure Redis for optimal caching
            await self._configure_redis()
            
            # Initialize metrics
            await self._initialize_metrics()
            
            logger.info("Redis cache service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Redis cache service: {e}")
            raise
    
    async def _configure_redis(self) -> None:
        """Configure Redis settings for optimal caching."""
        try:
            # Set max memory and eviction policy
            await self.redis.config_set("maxmemory", self.config.max_memory)
            await self.redis.config_set("maxmemory-policy", self.config.eviction_policy.value)
            
            # Enable compression if configured
            if self.config.compression_enabled:
                await self.redis.config_set("hash-max-ziplist-entries", "512")
                await self.redis.config_set("hash-max-ziplist-value", "64")
                
        except Exception as e:
            logger.warning(f"Could not configure Redis settings: {e}")
    
    async def _initialize_metrics(self) -> None:
        """Initialize cache metrics from Redis."""
        try:
            # Get current metrics from Redis
            info = await self.redis.info("memory")
            self.metrics.memory_usage = info.get("used_memory", 0)
            self.metrics.key_count = await self.redis.dbsize()
            self.metrics.last_updated = datetime.now()
            
        except Exception as e:
            logger.warning(f"Could not initialize metrics: {e}")
    
    async def get(self, key: str, cache_type: CacheType) -> Optional[Any]:
        """
        Retrieve data from cache.
        
        Args:
            key: Cache key
            cache_type: Type of cached data
            
        Returns:
            Cached data or None if not found/expired
        """
        try:
            if not self.redis:
                await self.initialize()
            
            # Build full cache key
            full_key = self._build_key(key, cache_type)
            
            # Get cached data
            cached_data = await self.redis.get(full_key)
            
            if cached_data is None:
                self.metrics.misses += 1
                self.metrics.total_requests += 1
                return None
            
            # Deserialize and decompress if needed
            data = await self._deserialize_data(cached_data)
            
            # Update access metrics
            self.metrics.hits += 1
            self.metrics.total_requests += 1
            self.metrics.hit_rate = self.metrics.hits / max(1, self.metrics.total_requests)
            
            # Update access count
            await self._update_access_metrics(full_key)
            
            logger.debug(f"Cache hit for key: {full_key}")
            return data
            
        except Exception as e:
            logger.error(f"Error retrieving from cache: {e}")
            self.metrics.misses += 1
            self.metrics.total_requests += 1
            return None
    
    async def set(
        self, 
        key: str, 
        data: Any, 
        cache_type: CacheType,
        ttl: Optional[int] = None,
        source_metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Store data in cache.
        
        Args:
            key: Cache key
            data: Data to cache
            cache_type: Type of data being cached
            ttl: Time to live in seconds (uses default if None)
            source_metadata: Additional metadata about the data source
            
        Returns:
            True if successfully cached, False otherwise
        """
        try:
            if not self.redis:
                await self.initialize()
            
            # Build full cache key
            full_key = self._build_key(key, cache_type)
            
            # Determine TTL
            if ttl is None:
                ttl = self.cache_ttl_map.get(cache_type, self.config.default_ttl)
            
            # Create cache entry
            cache_entry = CacheEntry(
                key=full_key,
                data=data,
                cache_type=cache_type,
                created_at=datetime.now(),
                expires_at=datetime.now() + timedelta(seconds=ttl),
                source_metadata=source_metadata,
                compressed=self.config.compression_enabled
            )
            
            # Serialize and compress data
            serialized_data = await self._serialize_data(cache_entry)
            
            # Store in Redis
            await self.redis.setex(full_key, ttl, serialized_data)
            
            # Update metrics
            self.metrics.key_count = await self.redis.dbsize()
            
            logger.debug(f"Cached data for key: {full_key}, TTL: {ttl}s")
            return True
            
        except Exception as e:
            logger.error(f"Error storing in cache: {e}")
            return False
    
    async def delete(self, key: str, cache_type: CacheType) -> bool:
        """Delete data from cache."""
        try:
            if not self.redis:
                await self.initialize()
            
            full_key = self._build_key(key, cache_type)
            result = await self.redis.delete(full_key)
            
            if result:
                self.metrics.key_count = await self.redis.dbsize()
                logger.debug(f"Deleted cache key: {full_key}")
            
            return bool(result)
            
        except Exception as e:
            logger.error(f"Error deleting from cache: {e}")
            return False
    
    async def clear_cache(self, cache_type: Optional[CacheType] = None) -> int:
        """
        Clear cache entries.
        
        Args:
            cache_type: Specific cache type to clear (None for all)
            
        Returns:
            Number of keys deleted
        """
        try:
            if not self.redis:
                await self.initialize()
            
            if cache_type:
                pattern = f"warehouse:{cache_type.value}:*"
            else:
                pattern = "warehouse:*"
            
            keys = await self.redis.keys(pattern)
            if keys:
                deleted = await self.redis.delete(*keys)
                self.metrics.key_count = await self.redis.dbsize()
                logger.info(f"Cleared {deleted} cache entries for pattern: {pattern}")
                return deleted
            
            return 0
            
        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return 0
    
    async def get_metrics(self) -> CacheMetrics:
        """Get current cache metrics."""
        try:
            if not self.redis:
                await self.initialize()
            
            # Update metrics from Redis
            info = await self.redis.info("memory")
            self.metrics.memory_usage = info.get("used_memory", 0)
            self.metrics.key_count = await self.redis.dbsize()
            self.metrics.last_updated = datetime.now()
            
            return self.metrics
            
        except Exception as e:
            logger.error(f"Error getting cache metrics: {e}")
            return self.metrics
    
    async def warm_cache(self, warming_data: Dict[CacheType, List[Tuple[str, Any]]]) -> Dict[str, int]:
        """
        Warm cache with frequently accessed data.
        
        Args:
            warming_data: Dictionary mapping cache types to lists of (key, data) tuples
            
        Returns:
            Dictionary with warming results
        """
        results = {}
        
        try:
            if not self.redis:
                await self.initialize()
            
            for cache_type, data_list in warming_data.items():
                warmed_count = 0
                
                for key, data in data_list:
                    success = await self.set(key, data, cache_type)
                    if success:
                        warmed_count += 1
                
                results[cache_type.value] = warmed_count
                logger.info(f"Warmed {warmed_count} entries for {cache_type.value}")
            
            return results
            
        except Exception as e:
            logger.error(f"Error warming cache: {e}")
            return results
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform cache health check."""
        try:
            if not self.redis:
                await self.initialize()
            
            # Test Redis connection
            await self.redis.ping()
            
            # Get metrics
            metrics = await self.get_metrics()
            
            # Check memory usage
            info = await self.redis.info("memory")
            max_memory = info.get("maxmemory", 0)
            used_memory = info.get("used_memory", 0)
            
            memory_usage_percent = (used_memory / max_memory * 100) if max_memory > 0 else 0
            
            health_status = {
                "status": "healthy",
                "redis_connected": True,
                "memory_usage_percent": memory_usage_percent,
                "hit_rate": metrics.hit_rate,
                "total_keys": metrics.key_count,
                "memory_usage_mb": used_memory / (1024 * 1024),
                "last_updated": metrics.last_updated.isoformat() if metrics.last_updated else None
            }
            
            # Add warnings
            warnings = []
            if memory_usage_percent > 80:
                warnings.append("High memory usage")
            if metrics.hit_rate < 0.5:
                warnings.append("Low cache hit rate")
            
            if warnings:
                health_status["warnings"] = warnings
                health_status["status"] = "degraded"
            
            return health_status
            
        except Exception as e:
            logger.error(f"Cache health check failed: {e}")
            return {
                "status": "unhealthy",
                "redis_connected": False,
                "error": str(e)
            }
    
    def _build_key(self, key: str, cache_type: CacheType) -> str:
        """Build full cache key with namespace."""
        return f"warehouse:{cache_type.value}:{key}"
    
    async def _serialize_data(self, cache_entry: CacheEntry) -> bytes:
        """Serialize cache entry data."""
        try:
            # Convert to dictionary
            entry_dict = asdict(cache_entry)
            
            # Serialize to JSON
            json_data = json.dumps(entry_dict, default=str)
            
            if self.config.compression_enabled:
                # Compress data
                compressed_data = gzip.compress(json_data.encode('utf-8'))
                return compressed_data
            else:
                return json_data.encode('utf-8')
                
        except Exception as e:
            logger.error(f"Error serializing cache data: {e}")
            raise
    
    async def _deserialize_data(self, data: bytes) -> Any:
        """Deserialize cached data."""
        try:
            if self.config.compression_enabled:
                # Decompress data
                json_data = gzip.decompress(data).decode('utf-8')
            else:
                json_data = data.decode('utf-8')
            
            # Parse JSON
            entry_dict = json.loads(json_data)
            
            # Convert back to CacheEntry
            cache_entry = CacheEntry(**entry_dict)
            
            return cache_entry.data
            
        except Exception as e:
            logger.error(f"Error deserializing cache data: {e}")
            raise
    
    async def _update_access_metrics(self, key: str) -> None:
        """Update access metrics for a cache key."""
        try:
            # Increment access count
            access_key = f"{key}:access"
            await self.redis.incr(access_key)
            await self.redis.expire(access_key, 3600)  # 1 hour TTL for access metrics
            
        except Exception as e:
            logger.debug(f"Could not update access metrics: {e}")
    
    def generate_cache_key(self, query: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Generate consistent cache key from query and context."""
        # Create hash of query and context
        key_data = {
            "query": query.lower().strip(),
            "context": context or {}
        }
        
        key_string = json.dumps(key_data, sort_keys=True)
        return hashlib.md5(key_string.encode()).hexdigest()

# Global cache service instance
_cache_service: Optional[RedisCacheService] = None

async def get_cache_service() -> RedisCacheService:
    """Get or create the global cache service instance."""
    global _cache_service
    if _cache_service is None:
        _cache_service = RedisCacheService()
        await _cache_service.initialize()
    return _cache_service
