"""
Caching Module for Warehouse Operational Assistant

Provides intelligent Redis caching for SQL results, evidence packs, vector searches,
and query preprocessing with configurable TTL, monitoring, and eviction policies.
"""

from .redis_cache_service import (
    RedisCacheService,
    CacheType,
    CacheConfig,
    CacheMetrics,
    CacheEntry,
    CachePolicy,
    get_cache_service
)

from .cache_manager import (
    CacheManager,
    CachePolicy as ManagerCachePolicy,
    CacheWarmingRule,
    EvictionStrategy,
    get_cache_manager
)

from .cache_integration import (
    CachedQueryProcessor,
    CacheIntegrationConfig,
    get_cached_query_processor
)

__all__ = [
    # Redis Cache Service
    "RedisCacheService",
    "CacheType",
    "CacheConfig", 
    "CacheMetrics",
    "CacheEntry",
    "CachePolicy",
    "get_cache_service",
    
    # Cache Manager
    "CacheManager",
    "ManagerCachePolicy",
    "CacheWarmingRule", 
    "EvictionStrategy",
    "get_cache_manager",
    
    # Cache Integration
    "CachedQueryProcessor",
    "CacheIntegrationConfig",
    "get_cached_query_processor"
]
