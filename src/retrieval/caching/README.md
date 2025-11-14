# Redis Caching System for Warehouse Operational Assistant

A comprehensive Redis caching system that provides intelligent caching for SQL results, evidence packs, vector searches, and query preprocessing with advanced monitoring, warming, and optimization capabilities.

##  Features

### Core Caching
- **Multi-Type Caching**: SQL results, evidence packs, vector searches, query preprocessing
- **Configurable TTL**: Different expiration times for different data types
- **Compression**: Automatic data compression for large cache entries
- **Serialization**: JSON-based serialization with metadata preservation

### Cache Management
- **Eviction Policies**: LRU, LFU, TTL, Random, Size-based
- **Memory Management**: Configurable memory limits and monitoring
- **Cache Warming**: Automatic preloading of frequently accessed data
- **Health Monitoring**: Real-time health checks and performance metrics

### Performance Optimization
- **Hit/Miss Tracking**: Comprehensive metrics collection
- **Response Time Monitoring**: Performance analytics
- **Cache Optimization**: Automatic cleanup and optimization
- **Trend Analysis**: Performance trend calculation

### Monitoring & Alerting
- **Real-time Dashboard**: Live cache performance data
- **Automated Alerts**: Configurable alerting for performance issues
- **Health Reports**: Comprehensive health and performance reports
- **Recommendations**: Intelligent optimization suggestions

## 📁 Architecture

```
inventory_retriever/caching/
├── redis_cache_service.py      # Core Redis caching service
├── cache_manager.py            # Cache management and policies
├── cache_integration.py        # Integration with query processors
├── cache_monitoring.py         # Monitoring and alerting
└── __init__.py                 # Module exports
```

##  Configuration

### Cache Types and Default TTLs

| Cache Type | Default TTL | Description |
|------------|-------------|-------------|
| `SQL_RESULT` | 5 minutes | SQL query results |
| `EVIDENCE_PACK` | 10 minutes | Evidence scoring results |
| `VECTOR_SEARCH` | 3 minutes | Vector search results |
| `QUERY_PREPROCESSING` | 15 minutes | Preprocessed queries |
| `WORKFORCE_DATA` | 5 minutes | Workforce information |
| `TASK_DATA` | 3 minutes | Task management data |
| `EQUIPMENT_DATA` | 10 minutes | Equipment information |

### Cache Configuration

```python
from inventory_retriever.caching import CacheConfig, CachePolicy

# Redis cache configuration
cache_config = CacheConfig(
    default_ttl=300,           # 5 minutes default
    max_memory="100mb",        # Memory limit
    eviction_policy=CachePolicy.LRU,  # Eviction strategy
    compression_enabled=True,  # Enable compression
    monitoring_enabled=True,   # Enable monitoring
    warming_enabled=True       # Enable cache warming
)

# Cache manager policy
manager_policy = CachePolicy(
    max_size=1000,             # Maximum entries
    max_memory_mb=100,         # Memory limit in MB
    default_ttl=300,           # Default TTL
    eviction_strategy=EvictionStrategy.LRU,
    warming_enabled=True,
    monitoring_enabled=True,
    compression_enabled=True
)
```

##  Usage

### Basic Caching

```python
import asyncio
from inventory_retriever.caching import get_cache_service, CacheType

async def basic_caching_example():
    # Get cache service
    cache_service = await get_cache_service()
    
    # Store data
    data = {"workers": 6, "shifts": ["morning", "afternoon"]}
    await cache_service.set("workforce_data", data, CacheType.WORKFORCE_DATA)
    
    # Retrieve data
    cached_data = await cache_service.get("workforce_data", CacheType.WORKFORCE_DATA)
    print(f"Cached data: {cached_data}")
    
    # Get metrics
    metrics = await cache_service.get_metrics()
    print(f"Hit rate: {metrics.hit_rate:.2%}")

asyncio.run(basic_caching_example())
```

### Cache Integration with Query Processing

```python
from inventory_retriever.caching import get_cached_query_processor

async def cached_query_processing():
    # Get cached query processor
    processor = await get_cached_query_processor()
    
    # Process query with caching
    result = await processor.process_query_with_caching(
        "How many active workers we have?",
        context={"session_id": "user123"}
    )
    
    print(f"Query result: {result['data']}")
    print(f"Cache hits: {result['cache_hits']}")
    print(f"Cache misses: {result['cache_misses']}")
    print(f"Processing time: {result['processing_time']:.3f}s")
```

### Cache Warming

```python
from inventory_retriever.caching import CacheWarmingRule, CacheType

async def setup_cache_warming():
    # Get cache manager
    cache_manager = await get_cache_manager()
    
    # Define warming rule
    async def generate_workforce_data():
        return {
            "total_workers": 6,
            "shifts": {"morning": 3, "afternoon": 3},
            "productivity": {"picks_per_hour": 45.2}
        }
    
    warming_rule = CacheWarmingRule(
        cache_type=CacheType.WORKFORCE_DATA,
        key_pattern="workforce_summary",
        data_generator=generate_workforce_data,
        priority=1,
        frequency_minutes=15
    )
    
    # Add warming rule
    cache_manager.add_warming_rule(warming_rule)
    
    # Manually warm cache
    warmed_count = await cache_manager.warm_cache_rule(warming_rule)
    print(f"Warmed {warmed_count} cache entries")
```

### Monitoring and Health Checks

```python
from inventory_retriever.caching import get_cache_monitoring_service

async def monitoring_example():
    # Get monitoring service
    monitoring = await get_cache_monitoring_service()
    
    # Get dashboard data
    dashboard = await monitoring.get_dashboard_data()
    print(f"Cache status: {dashboard['overview']['status']}")
    print(f"Hit rate: {dashboard['overview']['hit_rate']:.2%}")
    print(f"Memory usage: {dashboard['overview']['memory_usage_mb']:.1f}MB")
    
    # Get performance report
    report = await monitoring.get_performance_report(hours=24)
    print(f"Overall status: {report.overall_status}")
    print(f"Performance score: {report.performance_score:.1f}")
    print(f"Uptime: {report.uptime_percentage:.1f}%")
    
    # Add alert callback
    def alert_callback(alert):
        print(f"Alert: {alert.message} (Level: {alert.level.value})")
    
    monitoring.add_alert_callback(alert_callback)
```

##  Performance Metrics

### Cache Metrics

| Metric | Description |
|--------|-------------|
| `hits` | Number of cache hits |
| `misses` | Number of cache misses |
| `hit_rate` | Hit rate percentage |
| `total_requests` | Total cache requests |
| `memory_usage` | Memory usage in bytes |
| `key_count` | Number of cached keys |
| `evictions` | Number of evicted keys |

### Performance Targets

- **Hit Rate**: > 70% for optimal performance
- **Response Time**: < 50ms for cached data
- **Memory Usage**: < 80% of allocated memory
- **Uptime**: > 99.9% availability

## 🏥 Health Monitoring

### Health Status Levels

- **Healthy**: All metrics within normal ranges
- **Degraded**: Some metrics outside optimal ranges
- **Unhealthy**: Critical issues detected
- **Critical**: System failure or severe performance issues

### Alert Conditions

- **Low Hit Rate**: < 30% hit rate
- **High Memory Usage**: > 80% memory usage
- **High Error Rate**: > 10% error rate
- **Critical Hit Rate**: < 10% hit rate

##  Advanced Configuration

### Redis Configuration

```python
# Custom Redis configuration
cache_service = RedisCacheService(
    redis_url="redis://localhost:6379/0",
    config=CacheConfig(
        default_ttl=300,
        max_memory="200mb",
        eviction_policy=CachePolicy.LRU,
        compression_enabled=True,
        monitoring_enabled=True
    )
)
```

### Cache Integration Configuration

```python
from inventory_retriever.caching import CacheIntegrationConfig

# Configure cache integration
config = CacheIntegrationConfig(
    enable_sql_caching=True,
    enable_vector_caching=True,
    enable_evidence_caching=True,
    enable_preprocessing_caching=True,
    sql_cache_ttl=300,          # 5 minutes
    vector_cache_ttl=180,       # 3 minutes
    evidence_cache_ttl=600,     # 10 minutes
    preprocessing_cache_ttl=900, # 15 minutes
    warming_enabled=True,
    monitoring_enabled=True
)
```

## Testing

Run the comprehensive cache system test:

```bash
python test_caching_demo.py
```

This will test:
- Redis cache service functionality
- Cache manager operations
- Cache integration with query processing
- Monitoring and alerting
- Performance metrics collection

##  Best Practices

### Cache Key Design
- Use consistent, descriptive key patterns
- Include relevant context in keys
- Avoid special characters in keys
- Use appropriate key expiration times

### Memory Management
- Monitor memory usage regularly
- Set appropriate memory limits
- Use compression for large data
- Implement proper eviction policies

### Performance Optimization
- Enable cache warming for critical data
- Monitor hit rates and optimize TTL
- Use appropriate cache types for different data
- Implement cache invalidation strategies

### Monitoring
- Set up alerting for critical metrics
- Monitor performance trends
- Regular health checks
- Performance report analysis

##  Troubleshooting

### Common Issues

1. **Low Hit Rate**
   - Check cache key generation
   - Review TTL settings
   - Verify data consistency

2. **High Memory Usage**
   - Reduce TTL values
   - Enable compression
   - Review eviction policies

3. **Cache Misses**
   - Check Redis connectivity
   - Verify key patterns
   - Review cache configuration

4. **Performance Issues**
   - Monitor response times
   - Check Redis performance
   - Review cache warming

### Debug Commands

```python
# Get cache statistics
stats = await processor.get_cache_stats()
print(json.dumps(stats, indent=2))

# Get cache health
health = await cache_manager.get_cache_health()
print(json.dumps(health, indent=2))

# Clear specific cache type
cleared = await cache_service.clear_cache(CacheType.SQL_RESULT)
print(f"Cleared {cleared} SQL result entries")
```

## API Reference

### RedisCacheService
- `get(key, cache_type)` - Retrieve cached data
- `set(key, data, cache_type, ttl)` - Store data in cache
- `delete(key, cache_type)` - Delete cached data
- `clear_cache(cache_type)` - Clear cache entries
- `get_metrics()` - Get cache metrics
- `health_check()` - Perform health check

### CacheManager
- `get_with_fallback(key, cache_type, fallback_func)` - Get with fallback
- `invalidate_by_pattern(pattern, cache_type)` - Invalidate by pattern
- `invalidate_by_ttl(cache_type, max_age)` - Invalidate by age
- `warm_cache_rule(rule)` - Warm cache with rule
- `optimize_cache()` - Optimize cache performance

### CachedQueryProcessor
- `process_query_with_caching(query, context)` - Process with caching
- `get_cache_stats()` - Get comprehensive statistics

### CacheMonitoringService
- `get_dashboard_data()` - Get dashboard data
- `get_performance_report(hours)` - Get performance report
- `add_alert_callback(callback)` - Add alert callback

##  Future Enhancements

- **Distributed Caching**: Multi-node Redis cluster support
- **Cache Analytics**: Advanced analytics and reporting
- **Machine Learning**: ML-based cache optimization
- **Auto-scaling**: Dynamic cache scaling based on load
- **Cache Federation**: Cross-service cache sharing
- **Advanced Warming**: Predictive cache warming
- **Cache Security**: Encryption and access control
