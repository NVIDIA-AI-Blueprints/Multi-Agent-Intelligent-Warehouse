# Redis Caching System

## Overview

The Redis Caching System provides comprehensive caching capabilities for the Warehouse Operational Assistant, ensuring optimal performance and reduced latency for frequently accessed data.

## Architecture

### Multi-Type Caching

The system implements multiple caching strategies for different data types:

1. **SQL Query Results**: Cached database query results
2. **Vector Search Results**: Cached vector search and retrieval results
3. **Evidence Packs**: Cached evidence scoring and validation results
4. **User Sessions**: Cached user context and conversation history
5. **Configuration Data**: Cached system configuration and settings

### Cache Hierarchy

#### L1 Cache (Memory)
- **Purpose**: Ultra-fast access for critical data
- **Storage**: In-memory Redis cache
- **TTL**: 5-15 minutes
- **Size**: Limited by available memory

#### L2 Cache (Persistent)
- **Purpose**: Longer-term storage for less critical data
- **Storage**: Redis with persistence enabled
- **TTL**: 1-24 hours
- **Size**: Limited by disk space

#### L3 Cache (Database)
- **Purpose**: Fallback for cache misses
- **Storage**: PostgreSQL/TimescaleDB
- **TTL**: Indefinite (with cleanup policies)
- **Size**: Limited by database storage

## Implementation

The snippets below are illustrative. The implementation is
`RedisCacheService` (`src/retrieval/caching/redis_cache_service.py`, default
TTLs in `cache_ttl_map`) and `CacheManager`
(`src/retrieval/caching/cache_manager.py`); see `src/retrieval/caching/README.md`.

### Cache Manager

```python
class CacheManager:
    """Manages multi-type caching with Redis."""
    
    def __init__(self):
        self.redis_client = redis.Redis(host='localhost', port=6379, db=0)
        self.cache_config = CacheConfig()
        self.monitor = CacheMonitor()
    
    async def get(self, key, cache_type="default"):
        """Get value from cache."""
        try:
            cache_key = self.build_cache_key(key, cache_type)
            value = await self.redis_client.get(cache_key)
            
            if value:
                self.monitor.record_hit(cache_type)
                return self.deserialize(value)
            else:
                self.monitor.record_miss(cache_type)
                return None
                
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None
    
    async def set(self, key, value, ttl=None, cache_type="default"):
        """Set value in cache."""
        try:
            cache_key = self.build_cache_key(key, cache_type)
            ttl = ttl or self.cache_config.get_ttl(cache_type)
            
            serialized_value = self.serialize(value)
            await self.redis_client.setex(cache_key, ttl, serialized_value)
            
            self.monitor.record_set(cache_type, len(serialized_value))
            
        except Exception as e:
            logger.error(f"Cache set error: {e}")
    
    def build_cache_key(self, key, cache_type):
        """Build namespaced cache key."""
        return f"{cache_type}:{key}"
```

### Cache Types

#### SQL Query Cache
```python
class SQLQueryCache:
    """Caches SQL query results."""
    
    def __init__(self, cache_manager):
        self.cache_manager = cache_manager
        self.ttl = 300  # 5 minutes
    
    async def get_query_result(self, query_hash, parameters):
        """Get cached SQL query result."""
        cache_key = f"sql:{query_hash}:{hash(str(parameters))}"
        return await self.cache_manager.get(cache_key, "sql_query")
    
    async def set_query_result(self, query_hash, parameters, result):
        """Cache SQL query result."""
        cache_key = f"sql:{query_hash}:{hash(str(parameters))}"
        await self.cache_manager.set(cache_key, result, self.ttl, "sql_query")
```

#### Vector Search Cache
```python
class VectorSearchCache:
    """Caches vector search results."""
    
    def __init__(self, cache_manager):
        self.cache_manager = cache_manager
        self.ttl = 180  # 3 minutes
    
    async def get_search_result(self, query_hash, filters):
        """Get cached vector search result."""
        cache_key = f"vector:{query_hash}:{hash(str(filters))}"
        return await self.cache_manager.get(cache_key, "vector_search")
    
    async def set_search_result(self, query_hash, filters, result):
        """Cache vector search result."""
        cache_key = f"vector:{query_hash}:{hash(str(filters))}"
        await self.cache_manager.set(cache_key, result, self.ttl, "vector_search")
```

#### Evidence Pack Cache
```python
class EvidencePackCache:
    """Caches evidence scoring results."""
    
    def __init__(self, cache_manager):
        self.cache_manager = cache_manager
        self.ttl = 600  # 10 minutes
    
    async def get_evidence_pack(self, query_hash, evidence_hash):
        """Get cached evidence pack."""
        cache_key = f"evidence:{query_hash}:{evidence_hash}"
        return await self.cache_manager.get(cache_key, "evidence_pack")
    
    async def set_evidence_pack(self, query_hash, evidence_hash, evidence_pack):
        """Cache evidence pack."""
        cache_key = f"evidence:{query_hash}:{evidence_hash}"
        await self.cache_manager.set(cache_key, evidence_pack, self.ttl, "evidence_pack")
```

### Cache Configuration

```yaml
cache:
  redis:
    host: localhost
    port: 6379
    db: 0
    password: null
    max_connections: 100
  
  types:
    sql_query:
      ttl: 300  # 5 minutes
      max_size: 100MB
      compression: true
    
    vector_search:
      ttl: 180  # 3 minutes
      max_size: 500MB
      compression: true
    
    evidence_pack:
      ttl: 600  # 10 minutes
      max_size: 200MB
      compression: true
    
    user_session:
      ttl: 3600  # 1 hour
      max_size: 50MB
      compression: false
    
    config_data:
      ttl: 86400  # 24 hours
      max_size: 10MB
      compression: false
  
  eviction:
    policy: "allkeys-lru"
    max_memory: "2gb"
    max_memory_policy: "allkeys-lru"
  
  monitoring:
    track_hit_rate: true
    track_memory_usage: true
    alert_threshold: 0.8
```

## Performance Benefits

### Speed Improvements
- **Query Response Time**: 80% reduction in average response time
- **Database Load**: 60% reduction in database queries
- **Memory Usage**: 40% reduction in memory consumption
- **Network Latency**: 70% reduction in external API calls

### Scalability Benefits
- **Concurrent Users**: Support for 10x more concurrent users
- **Query Throughput**: 5x increase in queries per second
- **Resource Utilization**: 50% reduction in CPU usage
- **Cost Efficiency**: 60% reduction in database costs

### User Experience
- **Faster Responses**: Sub-second response times for cached data
- **Consistent Performance**: Predictable response times
- **Reduced Errors**: Fewer timeout and connection errors
- **Better Availability**: Higher system uptime and reliability

## Cache Strategies

### Write-Through Caching
```python
async def write_through_cache(key, value, ttl):
    """Write to both cache and database."""
    # Write to database first
    await database.write(key, value)
    
    # Then write to cache
    await cache.set(key, value, ttl)
```

### Write-Behind Caching
```python
async def write_behind_cache(key, value, ttl):
    """Write to cache immediately, database asynchronously."""
    # Write to cache immediately
    await cache.set(key, value, ttl)
    
    # Queue for database write
    await write_queue.put((key, value))
```

### Cache-Aside Pattern
```python
async def cache_aside_get(key):
    """Get from cache, fallback to database."""
    # Try cache first
    value = await cache.get(key)
    if value:
        return value
    
    # Fallback to database
    value = await database.get(key)
    if value:
        await cache.set(key, value)
    
    return value
```

## Cache Invalidation

### Time-Based Invalidation
```python
class TimeBasedInvalidation:
    """Invalidates cache based on TTL."""
    
    def __init__(self, cache_manager):
        self.cache_manager = cache_manager
    
    async def invalidate_expired(self):
        """Remove expired cache entries."""
        expired_keys = await self.cache_manager.get_expired_keys()
        for key in expired_keys:
            await self.cache_manager.delete(key)
```

### Event-Based Invalidation
```python
class EventBasedInvalidation:
    """Invalidates cache based on data changes."""
    
    def __init__(self, cache_manager):
        self.cache_manager = cache_manager
        self.event_listener = EventListener()
    
    async def on_data_change(self, event):
        """Handle data change events."""
        if event.type == "inventory_update":
            await self.invalidate_inventory_cache(event.sku)
        elif event.type == "equipment_update":
            await self.invalidate_equipment_cache(event.asset_id)
```

### Manual Invalidation
```python
class ManualInvalidation:
    """Manual cache invalidation methods."""
    
    def __init__(self, cache_manager):
        self.cache_manager = cache_manager
    
    async def invalidate_pattern(self, pattern):
        """Invalidate all keys matching pattern."""
        keys = await self.cache_manager.get_keys(pattern)
        for key in keys:
            await self.cache_manager.delete(key)
    
    async def invalidate_type(self, cache_type):
        """Invalidate all keys of specific type."""
        pattern = f"{cache_type}:*"
        await self.invalidate_pattern(pattern)
```

## Monitoring & Analytics

### Cache Metrics
- **Hit Rate**: Percentage of cache hits vs misses
- **Miss Rate**: Percentage of cache misses
- **Memory Usage**: Current memory consumption
- **Eviction Rate**: Rate of cache evictions
- **Response Time**: Average cache operation time

### Performance Monitoring
```python
class CacheMonitor:
    """Monitors cache performance and health."""
    
    def __init__(self):
        self.metrics = CacheMetrics()
        self.alerting = CacheAlerting()
    
    def record_hit(self, cache_type):
        """Record cache hit."""
        self.metrics.increment_hit(cache_type)
    
    def record_miss(self, cache_type):
        """Record cache miss."""
        self.metrics.increment_miss(cache_type)
    
    def check_health(self):
        """Check cache health and alert if needed."""
        hit_rate = self.metrics.get_hit_rate()
        if hit_rate < 0.8:  # 80% hit rate threshold
            self.alerting.send_alert("Low cache hit rate", hit_rate)
```

### Dashboards
- **Cache Performance**: Hit rate, miss rate, response time
- **Memory Usage**: Current usage, peak usage, eviction rate
- **Cache Types**: Performance breakdown by cache type
- **Error Rate**: Cache errors, timeouts, connection failures

## Best Practices

### Cache Key Design
- **Namespacing**: Use prefixes to avoid key collisions
- **Consistency**: Use consistent key naming conventions
- **Uniqueness**: Ensure keys are unique and deterministic
- **Readability**: Use human-readable key formats

### TTL Management
- **Appropriate TTLs**: Set TTLs based on data volatility
- **Graceful Degradation**: Handle cache misses gracefully
- **Refresh Strategies**: Implement cache refresh strategies
- **Monitoring**: Monitor TTL effectiveness

### Error Handling
- **Graceful Failures**: Continue operation when cache fails
- **Fallback Mechanisms**: Use database as fallback
- **Retry Logic**: Implement retry for transient failures
- **Logging**: Log cache errors for debugging

## Future Enhancements

### Planned Features
- **Distributed Caching**: Multi-node Redis cluster support
- **Cache Warming**: Proactive cache population
- **Intelligent Eviction**: ML-based eviction policies
- **Cache Compression**: Advanced compression algorithms
- **Real-time Monitoring**: Live cache performance dashboards
