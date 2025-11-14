"""
Prometheus metrics collection for Warehouse Operational Assistant.
"""

import time
from typing import Dict, Any
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    Info,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from fastapi import Request, Response
from fastapi.responses import PlainTextResponse
import logging

logger = logging.getLogger(__name__)

# HTTP Metrics
http_requests_total = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "endpoint", "status"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
)

# Business Logic Metrics
warehouse_active_users = Gauge("warehouse_active_users", "Number of active users")

warehouse_tasks_created_total = Counter(
    "warehouse_tasks_created_total", "Total tasks created", ["task_type", "priority"]
)

warehouse_tasks_completed_total = Counter(
    "warehouse_tasks_completed_total",
    "Total tasks completed",
    ["task_type", "worker_id"],
)

warehouse_tasks_by_status = Gauge(
    "warehouse_tasks_by_status", "Tasks by status", ["status"]
)

warehouse_inventory_alerts_total = Counter(
    "warehouse_inventory_alerts_total",
    "Total inventory alerts",
    ["alert_type", "severity"],
)

warehouse_safety_incidents_total = Counter(
    "warehouse_safety_incidents_total",
    "Total safety incidents",
    ["incident_type", "severity"],
)

warehouse_safety_score = Gauge("warehouse_safety_score", "Overall safety score (0-100)")

warehouse_equipment_utilization_percent = Gauge(
    "warehouse_equipment_utilization_percent",
    "Equipment utilization percentage",
    ["equipment_id", "equipment_type"],
)

warehouse_equipment_status = Gauge(
    "warehouse_equipment_status", "Equipment status", ["equipment_id", "status"]
)

warehouse_order_processing_duration_seconds = Histogram(
    "warehouse_order_processing_duration_seconds",
    "Order processing duration in seconds",
    ["order_type"],
)

warehouse_inventory_movements_total = Counter(
    "warehouse_inventory_movements_total",
    "Total inventory movements",
    ["movement_type", "location"],
)

warehouse_pick_accuracy_percent = Gauge(
    "warehouse_pick_accuracy_percent", "Pick accuracy percentage"
)

warehouse_compliance_checks_passed = Gauge(
    "warehouse_compliance_checks_passed", "Number of passed compliance checks"
)

warehouse_compliance_checks_failed = Gauge(
    "warehouse_compliance_checks_failed", "Number of failed compliance checks"
)

warehouse_compliance_checks_pending = Gauge(
    "warehouse_compliance_checks_pending", "Number of pending compliance checks"
)

warehouse_ppe_compliance_percent = Gauge(
    "warehouse_ppe_compliance_percent", "PPE compliance percentage"
)

warehouse_training_completion_percent = Gauge(
    "warehouse_training_completion_percent", "Training completion percentage"
)

warehouse_near_miss_events_total = Counter(
    "warehouse_near_miss_events_total", "Total near miss events", ["event_type"]
)

warehouse_temperature_celsius = Gauge(
    "warehouse_temperature_celsius", "Warehouse temperature in Celsius", ["zone"]
)

warehouse_humidity_percent = Gauge(
    "warehouse_humidity_percent", "Warehouse humidity percentage", ["zone"]
)

warehouse_emergency_response_duration_seconds = Histogram(
    "warehouse_emergency_response_duration_seconds",
    "Emergency response duration in seconds",
    ["emergency_type"],
)

warehouse_safety_violations_by_category = Gauge(
    "warehouse_safety_violations_by_category",
    "Safety violations by category",
    ["category"],
)

# System Info
system_info = Info("warehouse_system_info", "System information")


class MetricsCollector:
    """Collects and manages warehouse operational metrics."""

    def __init__(self):
        self.start_time = time.time()
        system_info.info(
            {
                "version": "1.0.0",
                "service": "warehouse-operational-assistant",
                "environment": "development",
            }
        )

    def record_http_request(
        self, request: Request, response: Response, duration: float
    ):
        """Record HTTP request metrics."""
        method = request.method
        endpoint = request.url.path
        status = str(response.status_code)

        http_requests_total.labels(
            method=method, endpoint=endpoint, status=status
        ).inc()

        http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(
            duration
        )

    def update_active_users(self, count: int):
        """Update active users count."""
        warehouse_active_users.set(count)

    def record_task_created(self, task_type: str, priority: str):
        """Record task creation."""
        warehouse_tasks_created_total.labels(
            task_type=task_type, priority=priority
        ).inc()

    def record_task_completed(self, task_type: str, worker_id: str):
        """Record task completion."""
        warehouse_tasks_completed_total.labels(
            task_type=task_type, worker_id=worker_id
        ).inc()

    def update_task_status(self, status_counts: Dict[str, int]):
        """Update task status distribution."""
        for status, count in status_counts.items():
            warehouse_tasks_by_status.labels(status=status).set(count)

    def record_inventory_alert(self, alert_type: str, severity: str):
        """Record inventory alert."""
        warehouse_inventory_alerts_total.labels(
            alert_type=alert_type, severity=severity
        ).inc()

    def record_safety_incident(self, incident_type: str, severity: str):
        """Record safety incident."""
        warehouse_safety_incidents_total.labels(
            incident_type=incident_type, severity=severity
        ).inc()

    def update_safety_score(self, score: float):
        """Update overall safety score."""
        warehouse_safety_score.set(score)

    def update_equipment_utilization(
        self, equipment_id: str, equipment_type: str, utilization: float
    ):
        """Update equipment utilization."""
        warehouse_equipment_utilization_percent.labels(
            equipment_id=equipment_id, equipment_type=equipment_type
        ).set(utilization)

    def update_equipment_status(self, equipment_id: str, status: str):
        """Update equipment status."""
        warehouse_equipment_status.labels(equipment_id=equipment_id, status=status).set(
            1
        )

    def record_order_processing_time(self, order_type: str, duration: float):
        """Record order processing time."""
        warehouse_order_processing_duration_seconds.labels(
            order_type=order_type
        ).observe(duration)

    def record_inventory_movement(self, movement_type: str, location: str):
        """Record inventory movement."""
        warehouse_inventory_movements_total.labels(
            movement_type=movement_type, location=location
        ).inc()

    def update_pick_accuracy(self, accuracy: float):
        """Update pick accuracy percentage."""
        warehouse_pick_accuracy_percent.set(accuracy)

    def update_compliance_checks(self, passed: int, failed: int, pending: int):
        """Update compliance check counts."""
        warehouse_compliance_checks_passed.set(passed)
        warehouse_compliance_checks_failed.set(failed)
        warehouse_compliance_checks_pending.set(pending)

    def update_ppe_compliance(self, compliance: float):
        """Update PPE compliance percentage."""
        warehouse_ppe_compliance_percent.set(compliance)

    def update_training_completion(self, completion: float):
        """Update training completion percentage."""
        warehouse_training_completion_percent.set(completion)

    def record_near_miss_event(self, event_type: str):
        """Record near miss event."""
        warehouse_near_miss_events_total.labels(event_type=event_type).inc()

    def update_environmental_conditions(
        self, temperature: float, humidity: float, zone: str = "main"
    ):
        """Update environmental conditions."""
        warehouse_temperature_celsius.labels(zone=zone).set(temperature)
        warehouse_humidity_percent.labels(zone=zone).set(humidity)

    def record_emergency_response_time(self, emergency_type: str, duration: float):
        """Record emergency response time."""
        warehouse_emergency_response_duration_seconds.labels(
            emergency_type=emergency_type
        ).observe(duration)

    def update_safety_violations(self, violations_by_category: Dict[str, int]):
        """Update safety violations by category."""
        for category, count in violations_by_category.items():
            warehouse_safety_violations_by_category.labels(category=category).set(count)


# Global metrics collector instance
metrics_collector = MetricsCollector()


def get_metrics_response() -> PlainTextResponse:
    """Generate Prometheus metrics response."""
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


def record_request_metrics(request: Request, response: Response, duration: float):
    """Record request metrics."""
    metrics_collector.record_http_request(request, response, duration)
