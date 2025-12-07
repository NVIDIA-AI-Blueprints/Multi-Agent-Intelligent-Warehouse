"""
Performance Monitoring Service

Tracks performance metrics for chat requests including latency, cache hits, errors, and routing accuracy.
"""

import logging
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetric:
    """Individual performance metric."""
    name: str
    value: float
    timestamp: datetime
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class RequestMetrics:
    """Metrics for a single request."""
    request_id: str
    start_time: float
    end_time: Optional[float] = None
    latency_ms: Optional[float] = None
    route: Optional[str] = None
    intent: Optional[str] = None
    cache_hit: bool = False
    error: Optional[str] = None
    tool_count: int = 0
    tool_execution_time_ms: float = 0.0


class PerformanceMonitor:
    """Service for tracking and reporting performance metrics."""

    def __init__(self):
        self.metrics: List[PerformanceMetric] = []
        self.request_metrics: Dict[str, RequestMetrics] = {}
        self._lock = asyncio.Lock()
        self._max_metrics = 10000  # Keep last 10k metrics
        self._max_requests = 1000  # Keep last 1k requests

    async def start_request(self, request_id: str) -> None:
        """Start tracking a request."""
        async with self._lock:
            self.request_metrics[request_id] = RequestMetrics(
                request_id=request_id,
                start_time=time.time()
            )

    async def end_request(
        self,
        request_id: str,
        route: Optional[str] = None,
        intent: Optional[str] = None,
        cache_hit: bool = False,
        error: Optional[str] = None,
        tool_count: int = 0,
        tool_execution_time_ms: float = 0.0
    ) -> None:
        """End tracking a request and record metrics."""
        async with self._lock:
            if request_id not in self.request_metrics:
                logger.warning(f"Request {request_id} not found in metrics")
                return

            request_metric = self.request_metrics[request_id]
            request_metric.end_time = time.time()
            request_metric.latency_ms = (request_metric.end_time - request_metric.start_time) * 1000
            request_metric.route = route
            request_metric.intent = intent
            request_metric.cache_hit = cache_hit
            request_metric.error = error
            request_metric.tool_count = tool_count
            request_metric.tool_execution_time_ms = tool_execution_time_ms

            # Record metrics
            await self._record_metric(
                "request_latency_ms",
                request_metric.latency_ms,
                {"route": route or "unknown", "intent": intent or "unknown"}
            )

            if cache_hit:
                await self._record_metric("cache_hit", 1.0, {})
            else:
                await self._record_metric("cache_miss", 1.0, {})

            if error:
                await self._record_metric("request_error", 1.0, {"error_type": error})
            else:
                await self._record_metric("request_success", 1.0, {})

            if tool_count > 0:
                await self._record_metric(
                    "tool_count",
                    float(tool_count),
                    {"route": route or "unknown"}
                )
                await self._record_metric(
                    "tool_execution_time_ms",
                    tool_execution_time_ms,
                    {"route": route or "unknown"}
                )

            # Cleanup old requests
            if len(self.request_metrics) > self._max_requests:
                oldest_request = min(
                    self.request_metrics.items(),
                    key=lambda x: x[1].start_time
                )
                del self.request_metrics[oldest_request[0]]

    async def record_timeout(
        self,
        request_id: str,
        timeout_duration: float,
        timeout_location: str,
        query_type: Optional[str] = None,
        reasoning_enabled: bool = False
    ) -> None:
        """
        Record a timeout event with detailed information.
        
        Args:
            request_id: ID of the request that timed out
            timeout_duration: Duration in seconds when timeout occurred
            timeout_location: Where the timeout occurred (e.g., "main_query_processing", "graph_execution", "agent_processing", "llm_call")
            query_type: Type of query ("simple", "complex", "reasoning")
            reasoning_enabled: Whether reasoning was enabled for this request
        """
        async with self._lock:
            # Record timeout metric
            await self._record_metric(
                "timeout_occurred",
                1.0,
                {
                    "timeout_location": timeout_location,
                    "query_type": query_type or "unknown",
                    "reasoning_enabled": str(reasoning_enabled),
                    "timeout_duration": str(timeout_duration)
                }
            )
            
            # Update request metrics if request exists
            if request_id in self.request_metrics:
                request_metric = self.request_metrics[request_id]
                request_metric.error = f"timeout_{timeout_location}"
                request_metric.end_time = time.time()
                request_metric.latency_ms = timeout_duration * 1000  # Convert to ms
            
            logger.warning(
                f"⏱️ Timeout recorded: location={timeout_location}, "
                f"duration={timeout_duration}s, query_type={query_type}, "
                f"reasoning={reasoning_enabled}, request_id={request_id}"
            )

    async def _record_metric(
        self,
        name: str,
        value: float,
        labels: Dict[str, str]
    ) -> None:
        """Record a performance metric."""
        metric = PerformanceMetric(
            name=name,
            value=value,
            timestamp=datetime.utcnow(),
            labels=labels
        )
        self.metrics.append(metric)

        # Cleanup old metrics
        if len(self.metrics) > self._max_metrics:
            self.metrics = self.metrics[-self._max_metrics:]

    async def get_stats(self, time_window_minutes: int = 60) -> Dict[str, Any]:
        """Get performance statistics for the last N minutes."""
        async with self._lock:
            cutoff_time = time.time() - (time_window_minutes * 60)
            
            # Filter metrics and requests within time window
            recent_metrics = [
                m for m in self.metrics
                if m.timestamp.timestamp() >= cutoff_time
            ]
            recent_requests = [
                r for r in self.request_metrics.values()
                if r.start_time >= cutoff_time and r.end_time is not None
            ]

            if not recent_requests:
                return {
                    "time_window_minutes": time_window_minutes,
                    "total_requests": 0,
                    "message": "No requests in time window"
                }

            # Calculate statistics
            latencies = [r.latency_ms for r in recent_requests if r.latency_ms]
            cache_hits = sum(1 for r in recent_requests if r.cache_hit)
            errors = sum(1 for r in recent_requests if r.error)
            total_tools = sum(r.tool_count for r in recent_requests)
            total_tool_time = sum(r.tool_execution_time_ms for r in recent_requests)

            # Route distribution
            route_counts = defaultdict(int)
            for r in recent_requests:
                if r.route:
                    route_counts[r.route] += 1

            # Intent distribution
            intent_counts = defaultdict(int)
            for r in recent_requests:
                if r.intent:
                    intent_counts[r.intent] += 1

            stats = {
                "time_window_minutes": time_window_minutes,
                "total_requests": len(recent_requests),
                "cache_hits": cache_hits,
                "cache_misses": len(recent_requests) - cache_hits,
                "cache_hit_rate": cache_hits / len(recent_requests) if recent_requests else 0.0,
                "errors": errors,
                "error_rate": errors / len(recent_requests) if recent_requests else 0.0,
                "success_rate": (len(recent_requests) - errors) / len(recent_requests) if recent_requests else 0.0,
                "latency": {
                    "p50": self._percentile(latencies, 50) if latencies else 0.0,
                    "p95": self._percentile(latencies, 95) if latencies else 0.0,
                    "p99": self._percentile(latencies, 99) if latencies else 0.0,
                    "mean": sum(latencies) / len(latencies) if latencies else 0.0,
                    "min": min(latencies) if latencies else 0.0,
                    "max": max(latencies) if latencies else 0.0,
                },
                "tools": {
                    "total_executed": total_tools,
                    "avg_per_request": total_tools / len(recent_requests) if recent_requests else 0.0,
                    "total_execution_time_ms": total_tool_time,
                    "avg_execution_time_ms": total_tool_time / total_tools if total_tools > 0 else 0.0,
                },
                "route_distribution": dict(route_counts),
                "intent_distribution": dict(intent_counts),
            }

            return stats

    def _percentile(self, data: List[float], percentile: int) -> float:
        """Calculate percentile of a list."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * (percentile / 100))
        return sorted_data[min(index, len(sorted_data) - 1)]

    async def check_alerts(self) -> List[Dict[str, Any]]:
        """
        Check performance metrics against alert thresholds and return active alerts.
        
        Returns:
            List of active alerts with details
        """
        alerts = []
        stats = await self.get_stats(time_window_minutes=5)  # Check last 5 minutes
        
        if stats.get("total_requests", 0) == 0:
            return alerts  # No requests, no alerts
        
        # Check latency alerts (P95 > 30s = 30000ms)
        latency = stats.get("latency", {})
        p95_latency = latency.get("p95", 0)
        if p95_latency > 30000:  # 30 seconds
            alerts.append({
                "alert_type": "high_latency",
                "severity": "warning",
                "metric": "p95_latency_ms",
                "value": p95_latency,
                "threshold": 30000,
                "message": f"P95 latency is {p95_latency:.2f}ms (threshold: 30000ms)",
                "timestamp": datetime.utcnow().isoformat()
            })
        
        # Check cache hit rate (should be > 0%)
        cache_hit_rate = stats.get("cache_hit_rate", 0.0)
        if cache_hit_rate == 0.0 and stats.get("total_requests", 0) > 10:
            # Only alert if we have enough requests to expect some cache hits
            alerts.append({
                "alert_type": "low_cache_hit_rate",
                "severity": "info",
                "metric": "cache_hit_rate",
                "value": cache_hit_rate,
                "threshold": 0.0,
                "message": f"Cache hit rate is {cache_hit_rate:.2%} (no cache hits detected)",
                "timestamp": datetime.utcnow().isoformat()
            })
        
        # Check error rate (should be < 5%)
        error_rate = stats.get("error_rate", 0.0)
        if error_rate > 0.05:  # 5%
            alerts.append({
                "alert_type": "high_error_rate",
                "severity": "warning" if error_rate < 0.10 else "critical",
                "metric": "error_rate",
                "value": error_rate,
                "threshold": 0.05,
                "message": f"Error rate is {error_rate:.2%} (threshold: 5%)",
                "timestamp": datetime.utcnow().isoformat()
            })
        
            # Check success rate (should be > 95%)
            success_rate = stats.get("success_rate", 1.0)
            if success_rate < 0.95:  # 95%
                alerts.append({
                    "alert_type": "low_success_rate",
                    "severity": "warning" if success_rate > 0.90 else "critical",
                    "metric": "success_rate",
                    "value": success_rate,
                    "threshold": 0.95,
                    "message": f"Success rate is {success_rate:.2%} (threshold: 95%)",
                    "timestamp": datetime.utcnow().isoformat()
                })
        
        # Check timeout rate (count timeouts in last 5 minutes)
        cutoff_time = time.time() - (5 * 60)  # 5 minutes ago
        timeout_metrics = [
            m for m in self.metrics
            if m.name == "timeout_occurred" and m.timestamp.timestamp() >= cutoff_time
        ]
        if timeout_metrics and len(recent_requests) > 0:
            timeout_rate = len(timeout_metrics) / len(recent_requests)
            if timeout_rate > 0.10:  # 10% timeout rate
                # Group timeouts by location
                timeout_locations = defaultdict(int)
                for m in timeout_metrics:
                    location = m.labels.get("timeout_location", "unknown")
                    timeout_locations[location] += 1
                
                alerts.append({
                    "alert_type": "high_timeout_rate",
                    "severity": "critical" if timeout_rate > 0.20 else "warning",
                    "metric": "timeout_rate",
                    "value": timeout_rate,
                    "threshold": 0.10,
                    "message": f"Timeout rate is {timeout_rate:.2%} (threshold: 10%). Locations: {dict(timeout_locations)}",
                    "timestamp": datetime.utcnow().isoformat(),
                    "timeout_locations": dict(timeout_locations)
                })
        
        return alerts


# Global performance monitor instance
_performance_monitor: Optional[PerformanceMonitor] = None


def get_performance_monitor() -> PerformanceMonitor:
    """Get the global performance monitor instance."""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
    return _performance_monitor

