"""
Sample metrics data generator for testing and demonstration purposes.
"""

import asyncio
import random
import time
from typing import Dict, Any
from chain_server.services.monitoring.metrics import metrics_collector
import logging

logger = logging.getLogger(__name__)


class SampleMetricsGenerator:
    """Generates sample metrics data for testing and demonstration."""

    def __init__(self):
        self.running = False
        self.task_types = ["pick", "pack", "ship", "receive", "inventory_check"]
        self.priorities = ["low", "medium", "high", "urgent"]
        self.incident_types = [
            "slip",
            "fall",
            "equipment_malfunction",
            "safety_violation",
        ]
        self.equipment_types = ["forklift", "conveyor", "picker", "packer", "scanner"]
        self.alert_types = ["low_stock", "overstock", "expired", "damaged", "missing"]
        self.movement_types = ["inbound", "outbound", "transfer", "adjustment"]
        self.worker_ids = [
            "worker_001",
            "worker_002",
            "worker_003",
            "worker_004",
            "worker_005",
        ]
        self.equipment_ids = ["FL001", "FL002", "CV001", "CV002", "PK001", "PK002"]
        self.zones = ["zone_a", "zone_b", "zone_c", "zone_d"]

    async def start(self):
        """Start generating sample metrics."""
        self.running = True
        logger.info("Starting sample metrics generation...")

        # Start background tasks
        tasks = [
            asyncio.create_task(self._generate_user_metrics()),
            asyncio.create_task(self._generate_task_metrics()),
            asyncio.create_task(self._generate_inventory_metrics()),
            asyncio.create_task(self._generate_safety_metrics()),
            asyncio.create_task(self._generate_equipment_metrics()),
            asyncio.create_task(self._generate_environmental_metrics()),
            asyncio.create_task(self._generate_compliance_metrics()),
        ]

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Sample metrics generation stopped.")
        finally:
            self.running = False

    def stop(self):
        """Stop generating sample metrics."""
        self.running = False
        logger.info("Stopping sample metrics generation...")

    async def _generate_user_metrics(self):
        """Generate user-related metrics."""
        while self.running:
            try:
                # Simulate active users (5-25 users)
                active_users = random.randint(5, 25)
                metrics_collector.update_active_users(active_users)

                await asyncio.sleep(30)  # Update every 30 seconds
            except Exception as e:
                logger.error(f"Error generating user metrics: {e}")
                await asyncio.sleep(5)

    async def _generate_task_metrics(self):
        """Generate task-related metrics."""
        while self.running:
            try:
                # Generate task creation events
                if random.random() < 0.3:  # 30% chance every cycle
                    task_type = random.choice(self.task_types)
                    priority = random.choice(self.priorities)
                    metrics_collector.record_task_created(task_type, priority)

                # Generate task completion events
                if random.random() < 0.4:  # 40% chance every cycle
                    task_type = random.choice(self.task_types)
                    worker_id = random.choice(self.worker_ids)
                    metrics_collector.record_task_completed(task_type, worker_id)

                # Update task status distribution
                status_counts = {
                    "pending": random.randint(10, 50),
                    "in_progress": random.randint(5, 30),
                    "completed": random.randint(20, 100),
                    "failed": random.randint(0, 5),
                }
                metrics_collector.update_task_status(status_counts)

                await asyncio.sleep(10)  # Update every 10 seconds
            except Exception as e:
                logger.error(f"Error generating task metrics: {e}")
                await asyncio.sleep(5)

    async def _generate_inventory_metrics(self):
        """Generate inventory-related metrics."""
        while self.running:
            try:
                # Generate inventory alerts
                if random.random() < 0.1:  # 10% chance every cycle
                    alert_type = random.choice(self.alert_types)
                    severity = random.choice(["low", "medium", "high"])
                    metrics_collector.record_inventory_alert(alert_type, severity)

                # Generate inventory movements
                if random.random() < 0.2:  # 20% chance every cycle
                    movement_type = random.choice(self.movement_types)
                    location = random.choice(self.zones)
                    metrics_collector.record_inventory_movement(movement_type, location)

                # Update pick accuracy (85-99%)
                pick_accuracy = random.uniform(85.0, 99.0)
                metrics_collector.update_pick_accuracy(pick_accuracy)

                await asyncio.sleep(15)  # Update every 15 seconds
            except Exception as e:
                logger.error(f"Error generating inventory metrics: {e}")
                await asyncio.sleep(5)

    async def _generate_safety_metrics(self):
        """Generate safety-related metrics."""
        while self.running:
            try:
                # Generate safety incidents (rare)
                if random.random() < 0.02:  # 2% chance every cycle
                    incident_type = random.choice(self.incident_types)
                    severity = random.choice(["low", "medium", "high", "critical"])
                    metrics_collector.record_safety_incident(incident_type, severity)

                # Generate near miss events
                if random.random() < 0.05:  # 5% chance every cycle
                    event_type = random.choice(
                        ["near_collision", "equipment_malfunction", "safety_violation"]
                    )
                    metrics_collector.record_near_miss_event(event_type)

                # Update safety score (70-95%)
                safety_score = random.uniform(70.0, 95.0)
                metrics_collector.update_safety_score(safety_score)

                # Update safety violations by category
                violations = {
                    "ppe": random.randint(0, 3),
                    "equipment": random.randint(0, 2),
                    "procedure": random.randint(0, 4),
                    "environment": random.randint(0, 2),
                }
                metrics_collector.update_safety_violations(violations)

                await asyncio.sleep(20)  # Update every 20 seconds
            except Exception as e:
                logger.error(f"Error generating safety metrics: {e}")
                await asyncio.sleep(5)

    async def _generate_equipment_metrics(self):
        """Generate equipment-related metrics."""
        while self.running:
            try:
                # Update equipment utilization
                for equipment_id in self.equipment_ids:
                    equipment_type = random.choice(self.equipment_types)
                    utilization = random.uniform(20.0, 95.0)
                    metrics_collector.update_equipment_utilization(
                        equipment_id, equipment_type, utilization
                    )

                # Update equipment status
                for equipment_id in self.equipment_ids:
                    status = random.choices(
                        ["operational", "maintenance", "offline"], weights=[85, 10, 5]
                    )[0]
                    metrics_collector.update_equipment_status(equipment_id, status)

                await asyncio.sleep(25)  # Update every 25 seconds
            except Exception as e:
                logger.error(f"Error generating equipment metrics: {e}")
                await asyncio.sleep(5)

    async def _generate_environmental_metrics(self):
        """Generate environmental metrics."""
        while self.running:
            try:
                # Update environmental conditions for each zone
                for zone in self.zones:
                    temperature = random.uniform(18.0, 25.0)  # 18-25°C
                    humidity = random.uniform(40.0, 60.0)  # 40-60%
                    metrics_collector.update_environmental_conditions(
                        temperature, humidity, zone
                    )

                await asyncio.sleep(60)  # Update every minute
            except Exception as e:
                logger.error(f"Error generating environmental metrics: {e}")
                await asyncio.sleep(5)

    async def _generate_compliance_metrics(self):
        """Generate compliance-related metrics."""
        while self.running:
            try:
                # Update compliance checks
                passed = random.randint(45, 55)
                failed = random.randint(0, 5)
                pending = random.randint(0, 10)
                metrics_collector.update_compliance_checks(passed, failed, pending)

                # Update PPE compliance (80-98%)
                ppe_compliance = random.uniform(80.0, 98.0)
                metrics_collector.update_ppe_compliance(ppe_compliance)

                # Update training completion (70-95%)
                training_completion = random.uniform(70.0, 95.0)
                metrics_collector.update_training_completion(training_completion)

                await asyncio.sleep(45)  # Update every 45 seconds
            except Exception as e:
                logger.error(f"Error generating compliance metrics: {e}")
                await asyncio.sleep(5)


# Global instance
sample_metrics_generator = SampleMetricsGenerator()


async def start_sample_metrics():
    """Start the sample metrics generator."""
    await sample_metrics_generator.start()


def stop_sample_metrics():
    """Stop the sample metrics generator."""
    sample_metrics_generator.stop()
