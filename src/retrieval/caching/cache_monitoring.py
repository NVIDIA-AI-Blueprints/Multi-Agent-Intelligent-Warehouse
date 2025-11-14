"""
Cache Monitoring Dashboard for Warehouse Operational Assistant

Provides comprehensive monitoring, alerting, and analytics for the Redis cache system
with real-time metrics, performance tracking, and health monitoring.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import json

from .redis_cache_service import RedisCacheService, CacheType, CacheMetrics
from .cache_manager import CacheManager

logger = logging.getLogger(__name__)

class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class CacheAlert:
    """Cache alert/notification."""
    id: str
    level: AlertLevel
    message: str
    timestamp: datetime
    cache_type: Optional[CacheType] = None
    metrics: Optional[Dict[str, Any]] = None
    resolved: bool = False

@dataclass
class CachePerformanceMetrics:
    """Detailed cache performance metrics."""
    timestamp: datetime
    hit_rate: float
    response_time_ms: float
    memory_usage_mb: float
    key_count: int
    eviction_count: int
    warming_success_rate: float
    error_rate: float

@dataclass
class CacheHealthReport:
    """Comprehensive cache health report."""
    overall_status: str  # healthy, degraded, unhealthy
    timestamp: datetime
    metrics: CachePerformanceMetrics
    alerts: List[CacheAlert]
    recommendations: List[str]
    uptime_percentage: float
    performance_score: float

class CacheMonitoringService:
    """
    Advanced cache monitoring service with real-time analytics and alerting.
    
    Features:
    - Real-time metrics collection
    - Performance trend analysis
    - Automated alerting
    - Health scoring
    - Recommendation engine
    - Dashboard data generation
    """
    
    def __init__(
        self, 
        cache_service: RedisCacheService, 
        cache_manager: CacheManager
    ):
        self.cache_service = cache_service
        self.cache_manager = cache_manager
        self.alerts: List[CacheAlert] = []
        self.performance_history: List[CachePerformanceMetrics] = []
        self.alert_callbacks: List[Callable[[CacheAlert], None]] = []
        self.monitoring_task: Optional[asyncio.Task] = None
        self.start_time = datetime.now()
        
    async def start_monitoring(self, interval_seconds: int = 30) -> None:
        """Start continuous cache monitoring."""
        try:
            self.monitoring_task = asyncio.create_task(
                self._monitoring_loop(interval_seconds)
            )
            logger.info(f"Cache monitoring started with {interval_seconds}s interval")
            
        except Exception as e:
            logger.error(f"Failed to start cache monitoring: {e}")
            raise
    
    async def stop_monitoring(self) -> None:
        """Stop cache monitoring."""
        try:
            if self.monitoring_task:
                self.monitoring_task.cancel()
                logger.info("Cache monitoring stopped")
                
        except Exception as e:
            logger.error(f"Error stopping cache monitoring: {e}")
    
    async def get_dashboard_data(self) -> Dict[str, Any]:
        """Get comprehensive dashboard data."""
        try:
            # Get current metrics
            current_metrics = await self.cache_service.get_metrics()
            
            # Get health information
            health = await self.cache_manager.get_cache_health()
            
            # Calculate performance trends
            trends = self._calculate_trends()
            
            # Generate recommendations
            recommendations = await self._generate_recommendations(current_metrics)
            
            # Get recent alerts
            recent_alerts = self._get_recent_alerts(hours=24)
            
            return {
                "timestamp": datetime.now().isoformat(),
                "overview": {
                    "status": health.get("status", "unknown"),
                    "hit_rate": current_metrics.hit_rate,
                    "memory_usage_mb": current_metrics.memory_usage / (1024 * 1024),
                    "key_count": current_metrics.key_count,
                    "uptime_hours": (datetime.now() - self.start_time).total_seconds() / 3600
                },
                "metrics": {
                    "hits": current_metrics.hits,
                    "misses": current_metrics.misses,
                    "total_requests": current_metrics.total_requests,
                    "hit_rate": current_metrics.hit_rate,
                    "memory_usage_bytes": current_metrics.memory_usage,
                    "key_count": current_metrics.key_count
                },
                "trends": trends,
                "alerts": [asdict(alert) for alert in recent_alerts],
                "recommendations": recommendations,
                "health": health
            }
            
        except Exception as e:
            logger.error(f"Error getting dashboard data: {e}")
            return {"error": str(e)}
    
    async def get_performance_report(
        self, 
        hours: int = 24
    ) -> CacheHealthReport:
        """Generate comprehensive performance report."""
        try:
            # Get current metrics
            current_metrics = await self.cache_service.get_metrics()
            
            # Calculate performance metrics
            perf_metrics = CachePerformanceMetrics(
                timestamp=datetime.now(),
                hit_rate=current_metrics.hit_rate,
                response_time_ms=self._calculate_avg_response_time(),
                memory_usage_mb=current_metrics.memory_usage / (1024 * 1024),
                key_count=current_metrics.key_count,
                eviction_count=0,  # Would need to track this
                warming_success_rate=self._calculate_warming_success_rate(),
                error_rate=self._calculate_error_rate()
            )
            
            # Get recent alerts
            recent_alerts = self._get_recent_alerts(hours)
            
            # Calculate overall status
            overall_status = self._calculate_overall_status(perf_metrics, recent_alerts)
            
            # Generate recommendations
            recommendations = await self._generate_recommendations(current_metrics)
            
            # Calculate uptime
            uptime_percentage = self._calculate_uptime_percentage()
            
            # Calculate performance score
            performance_score = self._calculate_performance_score(perf_metrics)
            
            return CacheHealthReport(
                overall_status=overall_status,
                timestamp=datetime.now(),
                metrics=perf_metrics,
                alerts=recent_alerts,
                recommendations=recommendations,
                uptime_percentage=uptime_percentage,
                performance_score=performance_score
            )
            
        except Exception as e:
            logger.error(f"Error generating performance report: {e}")
            return CacheHealthReport(
                overall_status="error",
                timestamp=datetime.now(),
                metrics=CachePerformanceMetrics(
                    timestamp=datetime.now(),
                    hit_rate=0.0,
                    response_time_ms=0.0,
                    memory_usage_mb=0.0,
                    key_count=0,
                    eviction_count=0,
                    warming_success_rate=0.0,
                    error_rate=1.0
                ),
                alerts=[],
                recommendations=["Error generating report"],
                uptime_percentage=0.0,
                performance_score=0.0
            )
    
    def add_alert_callback(self, callback: Callable[[CacheAlert], None]) -> None:
        """Add alert callback for notifications."""
        self.alert_callbacks.append(callback)
        logger.info("Added cache alert callback")
    
    async def _monitoring_loop(self, interval_seconds: int) -> None:
        """Main monitoring loop."""
        while True:
            try:
                # Collect metrics
                metrics = await self.cache_service.get_metrics()
                
                # Store performance data
                perf_metrics = CachePerformanceMetrics(
                    timestamp=datetime.now(),
                    hit_rate=metrics.hit_rate,
                    response_time_ms=self._calculate_avg_response_time(),
                    memory_usage_mb=metrics.memory_usage / (1024 * 1024),
                    key_count=metrics.key_count,
                    eviction_count=0,
                    warming_success_rate=self._calculate_warming_success_rate(),
                    error_rate=self._calculate_error_rate()
                )
                
                self.performance_history.append(perf_metrics)
                
                # Keep only last 24 hours of data
                cutoff_time = datetime.now() - timedelta(hours=24)
                self.performance_history = [
                    m for m in self.performance_history 
                    if m.timestamp > cutoff_time
                ]
                
                # Check for alerts
                await self._check_alerts(perf_metrics)
                
                # Wait for next check
                await asyncio.sleep(interval_seconds)
                
            except asyncio.CancelledError:
                logger.info("Cache monitoring loop cancelled")
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(interval_seconds)
    
    async def _check_alerts(self, metrics: CachePerformanceMetrics) -> None:
        """Check for alert conditions."""
        try:
            # Low hit rate alert
            if metrics.hit_rate < 0.3 and not self._has_active_alert("low_hit_rate"):
                alert = CacheAlert(
                    id=f"low_hit_rate_{datetime.now().timestamp()}",
                    level=AlertLevel.WARNING,
                    message=f"Low cache hit rate: {metrics.hit_rate:.2%}",
                    timestamp=datetime.now(),
                    metrics=asdict(metrics)
                )
                await self._trigger_alert(alert)
            
            # High memory usage alert
            if metrics.memory_usage_mb > 80 and not self._has_active_alert("high_memory"):
                alert = CacheAlert(
                    id=f"high_memory_{datetime.now().timestamp()}",
                    level=AlertLevel.WARNING,
                    message=f"High memory usage: {metrics.memory_usage_mb:.1f}MB",
                    timestamp=datetime.now(),
                    metrics=asdict(metrics)
                )
                await self._trigger_alert(alert)
            
            # High error rate alert
            if metrics.error_rate > 0.1 and not self._has_active_alert("high_error_rate"):
                alert = CacheAlert(
                    id=f"high_error_rate_{datetime.now().timestamp()}",
                    level=AlertLevel.ERROR,
                    message=f"High error rate: {metrics.error_rate:.2%}",
                    timestamp=datetime.now(),
                    metrics=asdict(metrics)
                )
                await self._trigger_alert(alert)
            
            # Very low hit rate critical alert
            if metrics.hit_rate < 0.1 and not self._has_active_alert("critical_hit_rate"):
                alert = CacheAlert(
                    id=f"critical_hit_rate_{datetime.now().timestamp()}",
                    level=AlertLevel.CRITICAL,
                    message=f"Critical low hit rate: {metrics.hit_rate:.2%}",
                    timestamp=datetime.now(),
                    metrics=asdict(metrics)
                )
                await self._trigger_alert(alert)
                
        except Exception as e:
            logger.error(f"Error checking alerts: {e}")
    
    async def _trigger_alert(self, alert: CacheAlert) -> None:
        """Trigger an alert and notify callbacks."""
        try:
            self.alerts.append(alert)
            
            # Notify callbacks
            for callback in self.alert_callbacks:
                try:
                    callback(alert)
                except Exception as e:
                    logger.error(f"Error in alert callback: {e}")
            
            logger.warning(f"Cache alert triggered: {alert.message}")
            
        except Exception as e:
            logger.error(f"Error triggering alert: {e}")
    
    def _has_active_alert(self, alert_type: str) -> bool:
        """Check if there's an active alert of the given type."""
        cutoff_time = datetime.now() - timedelta(minutes=30)  # 30 minute cooldown
        
        for alert in self.alerts:
            if (alert.id.startswith(alert_type) and 
                not alert.resolved and 
                alert.timestamp > cutoff_time):
                return True
        
        return False
    
    def _get_recent_alerts(self, hours: int = 24) -> List[CacheAlert]:
        """Get recent alerts within specified hours."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [
            alert for alert in self.alerts 
            if alert.timestamp > cutoff_time
        ]
    
    def _calculate_trends(self) -> Dict[str, Any]:
        """Calculate performance trends from historical data."""
        if len(self.performance_history) < 2:
            return {"hit_rate_trend": 0.0, "memory_trend": 0.0}
        
        # Get recent data (last 2 hours)
        recent_data = [
            m for m in self.performance_history 
            if m.timestamp > datetime.now() - timedelta(hours=2)
        ]
        
        if len(recent_data) < 2:
            return {"hit_rate_trend": 0.0, "memory_trend": 0.0}
        
        # Calculate trends
        hit_rates = [m.hit_rate for m in recent_data]
        memory_usage = [m.memory_usage_mb for m in recent_data]
        
        hit_rate_trend = (hit_rates[-1] - hit_rates[0]) / len(hit_rates) if len(hit_rates) > 1 else 0.0
        memory_trend = (memory_usage[-1] - memory_usage[0]) / len(memory_usage) if len(memory_usage) > 1 else 0.0
        
        return {
            "hit_rate_trend": hit_rate_trend,
            "memory_trend": memory_trend,
            "data_points": len(recent_data)
        }
    
    def _calculate_avg_response_time(self) -> float:
        """Calculate average response time (simplified)."""
        # This would typically be measured from actual requests
        return 50.0  # Placeholder
    
    def _calculate_warming_success_rate(self) -> float:
        """Calculate cache warming success rate."""
        # This would be tracked from actual warming operations
        return 0.95  # Placeholder
    
    def _calculate_error_rate(self) -> float:
        """Calculate error rate from recent operations."""
        # This would be calculated from actual error tracking
        return 0.02  # Placeholder
    
    def _calculate_overall_status(
        self, 
        metrics: CachePerformanceMetrics, 
        alerts: List[CacheAlert]
    ) -> str:
        """Calculate overall cache status."""
        critical_alerts = [a for a in alerts if a.level == AlertLevel.CRITICAL and not a.resolved]
        error_alerts = [a for a in alerts if a.level == AlertLevel.ERROR and not a.resolved]
        warning_alerts = [a for a in alerts if a.level == AlertLevel.WARNING and not a.resolved]
        
        if critical_alerts:
            return "critical"
        elif error_alerts:
            return "unhealthy"
        elif warning_alerts or metrics.hit_rate < 0.5:
            return "degraded"
        else:
            return "healthy"
    
    def _calculate_uptime_percentage(self) -> float:
        """Calculate cache uptime percentage."""
        # This would be calculated from actual uptime tracking
        return 99.9  # Placeholder
    
    def _calculate_performance_score(self, metrics: CachePerformanceMetrics) -> float:
        """Calculate overall performance score (0-100)."""
        # Weighted scoring based on key metrics
        hit_rate_score = min(100, metrics.hit_rate * 100)
        memory_score = max(0, 100 - (metrics.memory_usage_mb / 100) * 100)
        error_score = max(0, 100 - metrics.error_rate * 1000)
        
        # Weighted average
        performance_score = (
            hit_rate_score * 0.5 +
            memory_score * 0.3 +
            error_score * 0.2
        )
        
        return min(100, max(0, performance_score))
    
    async def _generate_recommendations(self, metrics: CacheMetrics) -> List[str]:
        """Generate cache optimization recommendations."""
        recommendations = []
        
        try:
            # Hit rate recommendations
            if metrics.hit_rate < 0.5:
                recommendations.append("Consider increasing cache TTL for frequently accessed data")
                recommendations.append("Review cache key generation for better hit rates")
            
            if metrics.hit_rate < 0.3:
                recommendations.append("Implement cache warming for critical data")
                recommendations.append("Consider increasing cache size limits")
            
            # Memory recommendations
            memory_mb = metrics.memory_usage / (1024 * 1024)
            if memory_mb > 80:
                recommendations.append("Consider reducing cache TTL to free memory")
                recommendations.append("Review cache eviction policies")
            
            if memory_mb > 90:
                recommendations.append("Increase Redis memory limit")
                recommendations.append("Implement more aggressive eviction policies")
            
            # General recommendations
            if metrics.key_count > 1000:
                recommendations.append("Consider implementing cache partitioning")
            
            if not recommendations:
                recommendations.append("Cache performance is optimal")
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
            return ["Error generating recommendations"]

# Global monitoring service instance
_monitoring_service: Optional[CacheMonitoringService] = None

async def get_cache_monitoring_service() -> CacheMonitoringService:
    """Get or create the global cache monitoring service instance."""
    global _monitoring_service
    if _monitoring_service is None:
        from .redis_cache_service import get_cache_service
        from .cache_manager import get_cache_manager
        
        cache_service = await get_cache_service()
        cache_manager = await get_cache_manager()
        
        _monitoring_service = CacheMonitoringService(cache_service, cache_manager)
        await _monitoring_service.start_monitoring()
    
    return _monitoring_service
