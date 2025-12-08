"""
Operations Coordination Agent Action Tools

Provides comprehensive action tools for operations management including:
- Task assignment and workload balancing
- Pick wave generation and optimization
- Shift scheduling and workforce management
- Dock scheduling and equipment dispatch
- KPI publishing and monitoring
"""

import logging
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import asyncio
import json
import uuid

from src.api.services.llm.nim_client import get_nim_client
from src.api.services.wms.integration_service import get_wms_service
from src.api.services.attendance.integration_service import get_attendance_service
from src.api.services.iot.integration_service import get_iot_service
from src.retrieval.structured import SQLRetriever

logger = logging.getLogger(__name__)


@dataclass
class TaskAssignment:
    """Task assignment details."""

    task_id: str
    task_type: str
    quantity: int
    assigned_to: List[str]
    constraints: Dict[str, Any]
    priority: str
    status: str
    created_at: datetime
    due_date: Optional[datetime]
    zone: Optional[str]
    equipment_required: List[str]
    skills_required: List[str]


@dataclass
class WorkloadRebalance:
    """Workload rebalancing result."""

    rebalance_id: str
    original_assignments: List[Dict[str, Any]]
    new_assignments: List[Dict[str, Any]]
    sla_impact: Dict[str, Any]
    efficiency_gain: float
    created_at: datetime


@dataclass
class PickWave:
    """Pick wave details."""

    wave_id: str
    order_ids: List[str]
    strategy: str
    total_lines: int
    estimated_duration: int  # minutes
    assigned_pickers: List[str]
    zones: List[str]
    status: str
    created_at: datetime
    labels_generated: bool
    route_optimized: bool


@dataclass
class PickPathOptimization:
    """Pick path optimization result."""

    picker_id: str
    optimized_route: List[Dict[str, Any]]
    total_distance: float
    time_savings: int  # minutes
    efficiency_score: float
    waypoints: List[Dict[str, Any]]


@dataclass
class ShiftSchedule:
    """Shift schedule management."""

    shift_id: str
    shift_type: str
    start_time: datetime
    end_time: datetime
    workers: List[Dict[str, Any]]
    capacity: int
    status: str
    changes: List[Dict[str, Any]]
    created_at: datetime


@dataclass
class DockAppointment:
    """Dock appointment details."""

    appointment_id: str
    dock_door: str
    carrier: str
    trailer_id: str
    scheduled_time: datetime
    duration: int  # minutes
    cargo_type: str
    priority: str
    status: str
    created_at: datetime


@dataclass
class EquipmentDispatch:
    """Equipment dispatch details."""

    dispatch_id: str
    equipment_id: str
    equipment_type: str
    task_id: str
    assigned_operator: str
    location: str
    status: str
    created_at: datetime
    estimated_completion: datetime


@dataclass
class KPIMetrics:
    """KPI metrics for publishing."""

    timestamp: datetime
    throughput: Dict[str, float]
    sla_metrics: Dict[str, Any]
    utilization: Dict[str, float]
    productivity: Dict[str, float]
    quality_metrics: Dict[str, float]


class OperationsActionTools:
    """
    Action tools for Operations Coordination Agent.

    Provides comprehensive operations management capabilities including:
    - Task assignment and workload balancing
    - Pick wave generation and optimization
    - Shift scheduling and workforce management
    - Dock scheduling and equipment dispatch
    - KPI publishing and monitoring
    """

    def __init__(self):
        self.nim_client = None
        self.wms_service = None
        self.attendance_service = None
        self.iot_service = None
        self.sql_retriever = None

    async def initialize(self) -> None:
        """Initialize action tools with required services."""
        try:
            self.nim_client = await get_nim_client()
            self.wms_service = await get_wms_service()
            self.attendance_service = await get_attendance_service()
            self.iot_service = await get_iot_service()
            self.sql_retriever = SQLRetriever()
            await self.sql_retriever.initialize()
            logger.info("Operations Action Tools initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Operations Action Tools: {e}")
            raise

    async def assign_tasks(
        self,
        task_type: str,
        quantity: int,
        constraints: Dict[str, Any],
        assignees: Optional[List[str]] = None,
    ) -> TaskAssignment:
        """
        Assign tasks to workers with constraints.

        Args:
            task_type: Type of task (pick, pack, receive, putaway, etc.)
            quantity: Number of tasks to assign
            constraints: Zone, equipment, skill requirements
            assignees: Optional specific assignees

        Returns:
            TaskAssignment with assignment details
        """
        try:
            if not self.wms_service:
                await self.initialize()

            # Generate unique task ID
            task_id = (
                f"TASK_{task_type.upper()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            )

            # Determine assignees based on constraints
            if not assignees:
                assignees = await self._find_qualified_assignees(task_type, constraints)

            # Create task assignment
            assignment = TaskAssignment(
                task_id=task_id,
                task_type=task_type,
                quantity=quantity,
                assigned_to=assignees,
                constraints=constraints,
                priority=constraints.get("priority", "medium"),
                status="assigned",
                created_at=datetime.now(),
                due_date=constraints.get("due_date"),
                zone=constraints.get("zone"),
                equipment_required=constraints.get("equipment", []),
                skills_required=constraints.get("skills", []),
            )

            # Create WMS work queue entries
            wms_result = await self.wms_service.create_work_queue_entry(
                task_id=task_id,
                task_type=task_type,
                quantity=quantity,
                assigned_workers=assignees,
                constraints=constraints,
            )

            if wms_result and wms_result.get("success"):
                assignment.status = "queued"
                logger.info(f"Task {task_id} successfully queued in WMS")
            else:
                assignment.status = "pending"
                logger.warning(f"Task {task_id} created but not queued in WMS")

            return assignment

        except Exception as e:
            logger.error(f"Failed to assign tasks: {e}")
            return TaskAssignment(
                task_id=f"TASK_{task_type.upper()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                task_type=task_type,
                quantity=quantity,
                assigned_to=assignees or [],
                constraints=constraints,
                priority="medium",
                status="error",
                created_at=datetime.now(),
                due_date=None,
                zone=constraints.get("zone"),
                equipment_required=constraints.get("equipment", []),
                skills_required=constraints.get("skills", []),
            )

    async def create_task(
        self,
        task_type: str,
        sku: str,
        quantity: int = 1,
        priority: str = "medium",
        zone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new task for warehouse operations.

        Args:
            task_type: Type of task (pick, pack, putaway, etc.)
            sku: SKU for the task
            quantity: Quantity for the task
            priority: Task priority (high, medium, low)
            zone: Zone for the task

        Returns:
            Dict with task creation result
        """
        try:
            if not self.wms_service:
                await self.initialize()

            task_id = f"TASK_{task_type.upper()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            constraints = {
                "priority": priority,
                "zone": zone,
            }
            
            assignment = await self.assign_tasks(
                task_type=task_type,
                quantity=quantity,
                constraints=constraints,
            )
            
            return {
                "success": True,
                "task_id": assignment.task_id,
                "task_type": assignment.task_type,
                "status": assignment.status,
                "zone": assignment.zone,
                "priority": assignment.priority,
            }
        except Exception as e:
            logger.error(f"Failed to create task: {e}")
            return {
                "success": False,
                "error": str(e),
                "task_id": None,
            }

    async def assign_task(
        self,
        task_id: str,
        worker_id: str,
        assignment_type: str = "manual",
    ) -> Dict[str, Any]:
        """
        Assign a task to a worker.

        Args:
            task_id: Task ID to assign
            worker_id: Worker ID to assign task to
            assignment_type: Type of assignment (manual, automatic)

        Returns:
            Dict with assignment result
        """
        try:
            if not self.wms_service:
                await self.initialize()

            # Update task assignment in WMS
            result = await self.wms_service.update_work_queue_entry(
                task_id=task_id,
                assigned_worker=worker_id,
            )
            
            if result and result.get("success"):
                return {
                    "success": True,
                    "task_id": task_id,
                    "worker_id": worker_id,
                    "assignment_type": assignment_type,
                    "status": "assigned",
                }
            else:
                return {
                    "success": False,
                    "task_id": task_id,
                    "worker_id": worker_id,
                    "error": "Failed to update work queue entry",
                }
        except Exception as e:
            logger.error(f"Failed to assign task: {e}")
            return {
                "success": False,
                "task_id": task_id,
                "worker_id": worker_id,
                "error": str(e),
            }

    async def get_task_status(
        self,
        task_id: Optional[str] = None,
        worker_id: Optional[str] = None,
        status: Optional[str] = None,
        task_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get status of tasks.

        Args:
            task_id: Specific task ID to check
            worker_id: Worker ID to get tasks for
            status: Filter by task status
            task_type: Filter by task type

        Returns:
            Dict with task status information
        """
        try:
            if not self.wms_service:
                await self.initialize()

            # Get tasks from WMS
            tasks = await self.wms_service.get_work_queue_entries(
                task_id=task_id,
                worker_id=worker_id,
                status=status,
                task_type=task_type,
            )
            
            return {
                "success": True,
                "tasks": tasks if tasks else [],
                "count": len(tasks) if tasks else 0,
            }
        except Exception as e:
            logger.error(f"Failed to get task status: {e}")
            return {
                "success": False,
                "error": str(e),
                "tasks": [],
                "count": 0,
            }

    async def get_workforce_status(
        self,
        worker_id: Optional[str] = None,
        shift: Optional[str] = None,
        status: Optional[str] = None,
        zone: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get workforce status and availability.

        Args:
            worker_id: Specific worker ID to check
            shift: Shift to check (day, night, etc.)
            status: Filter by worker status (defaults to 'active' if not specified)
            zone: Filter by zone

        Returns:
            Dict with workforce status information
        """
        try:
            if not self.sql_retriever:
                await self.initialize()

            # Build query to get workers from users table
            where_conditions = []
            params = []
            param_count = 1

            # Filter by worker_id if provided
            if worker_id:
                where_conditions.append(f"u.id = ${param_count}")
                params.append(worker_id)
                param_count += 1

            # Filter by status (default to 'active' if not specified)
            worker_status = status if status else "active"
            where_conditions.append(f"u.status = ${param_count}")
            params.append(worker_status)
            param_count += 1

            # Filter by role (only operational workers)
            where_conditions.append(f"u.role IN (${param_count}, ${param_count + 1}, ${param_count + 2})")
            params.extend(["operator", "supervisor", "manager"])
            param_count += 3

            # Note: Zone filtering is not available in users table
            # Zone information would need to come from task assignments or other tables
            # For now, we'll get all workers and filter by zone in application logic if needed

            # Build WHERE clause
            where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"

            # Query to get workers
            query = f"""
                SELECT 
                    u.id,
                    u.username,
                    u.email,
                    u.full_name,
                    u.role,
                    u.status,
                    u.created_at,
                    u.updated_at
                FROM users u
                WHERE {where_clause}
                ORDER BY u.username
            """

            # Unpack params list for fetch_all which expects *params
            workers = await self.sql_retriever.fetch_all(query, *params) if params else await self.sql_retriever.fetch_all(query)
            
            # Format workers data
            workforce_list = []
            for worker in workers:
                worker_data = {
                    "worker_id": worker.get("id"),
                    "username": worker.get("username"),
                    "email": worker.get("email"),
                    "full_name": worker.get("full_name"),
                    "role": worker.get("role"),
                    "status": worker.get("status"),
                }
                
                # If zone filtering was requested, try to get zone from task assignments
                # For now, we'll include all workers and note that zone filtering
                # would require joining with tasks or assignments table
                if zone:
                    # Note: Zone filtering not available in users table
                    # This would require a join with tasks/assignments to filter by zone
                    pass
                
                workforce_list.append(worker_data)

            # If zone was requested but we can't filter by it, log a note
            if zone:
                logger.info(f"Retrieved {len(workforce_list)} workers from database (status={worker_status}). Note: Zone filtering not available in users table - showing all workers.")
            else:
                logger.info(f"Retrieved {len(workforce_list)} workers from database (status={worker_status})")
            
            return {
                "success": True,
                "workforce": workforce_list,
                "count": len(workforce_list),
                "filters": {
                    "worker_id": worker_id,
                    "shift": shift,
                    "status": worker_status,
                    "zone": zone,
                }
            }
        except Exception as e:
            logger.error(f"Failed to get workforce status: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "workforce": [],
                "count": 0,
            }

    async def rebalance_workload(
        self, sla_rules: Optional[Dict[str, Any]] = None
    ) -> WorkloadRebalance:
        """
        Rebalance workload across workers based on SLA rules.

        Args:
            sla_rules: SLA rules for rebalancing

        Returns:
            WorkloadRebalance with rebalancing results
        """
        try:
            if not self.wms_service:
                await self.initialize()

            rebalance_id = f"REBAL_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Get current workload distribution
            current_workload = await self.wms_service.get_workload_distribution()

            # Get worker availability and capacity
            worker_capacity = await self.attendance_service.get_worker_capacity()

            # Apply rebalancing algorithm
            rebalanced_assignments = await self._apply_rebalancing_algorithm(
                current_workload, worker_capacity, sla_rules
            )

            # Calculate efficiency gain
            original_efficiency = self._calculate_workload_efficiency(current_workload)
            new_efficiency = self._calculate_workload_efficiency(rebalanced_assignments)
            efficiency_gain = new_efficiency - original_efficiency

            # Create rebalance result
            rebalance = WorkloadRebalance(
                rebalance_id=rebalance_id,
                original_assignments=current_workload.get("assignments", []),
                new_assignments=rebalanced_assignments.get("assignments", []),
                sla_impact=rebalanced_assignments.get("sla_impact", {}),
                efficiency_gain=efficiency_gain,
                created_at=datetime.now(),
            )

            # Apply rebalancing if efficiency gain is positive
            if efficiency_gain > 0:
                await self.wms_service.apply_workload_rebalancing(
                    rebalanced_assignments
                )
                logger.info(
                    f"Workload rebalancing applied with {efficiency_gain:.2f}% efficiency gain"
                )
            else:
                logger.info("No rebalancing needed - current distribution is optimal")

            return rebalance

        except Exception as e:
            logger.error(f"Failed to rebalance workload: {e}")
            return WorkloadRebalance(
                rebalance_id=f"REBAL_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                original_assignments=[],
                new_assignments=[],
                sla_impact={},
                efficiency_gain=0.0,
                created_at=datetime.now(),
            )

    async def generate_pick_wave(
        self, order_ids: List[str], wave_strategy: str = "zone_based"
    ) -> PickWave:
        """
        Generate pick wave with labels and route optimization.

        Args:
            order_ids: List of order IDs to include in wave
            wave_strategy: Strategy for wave generation (zone_based, time_based, etc.)

        Returns:
            PickWave with wave details
        """
        try:
            if not self.wms_service:
                await self.initialize()

            wave_id = f"WAVE_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Get order details - for now, simulate order data since we don't have real orders
            # In a real implementation, this would query the WMS system
            order_details = []
            for order_id in order_ids:
                # Simulate order data based on the query context
                simulated_order = {
                    "order_id": order_id,
                    "line_count": 120,  # Default line count from the query
                    "items": [
                        {"zone": "A", "sku": f"SKU_{i:03d}", "quantity": 1}
                        for i in range(1, 21)  # Simulate 20 items for Zone A
                    ],
                }
                order_details.append(simulated_order)

            # Calculate wave metrics
            total_lines = sum(order.get("line_count", 0) for order in order_details)
            zones = list(
                set(
                    item.get("zone")
                    for order in order_details
                    for item in order.get("items", [])
                )
            )

            # Assign pickers based on strategy
            assigned_pickers = await self._assign_pickers_for_wave(zones, wave_strategy)

            # Estimate duration
            estimated_duration = await self._estimate_wave_duration(
                total_lines, len(assigned_pickers)
            )

            # Create pick wave
            pick_wave = PickWave(
                wave_id=wave_id,
                order_ids=order_ids,
                strategy=wave_strategy,
                total_lines=total_lines,
                estimated_duration=estimated_duration,
                assigned_pickers=assigned_pickers,
                zones=zones,
                status="generated",
                created_at=datetime.now(),
                labels_generated=False,
                route_optimized=False,
            )

            # Generate labels - simulate for now
            # In a real implementation, this would call the WMS system
            pick_wave.labels_generated = True
            pick_wave.status = "labels_ready"

            # Optimize routes
            route_result = await self._optimize_pick_routes(pick_wave)
            if route_result:
                pick_wave.route_optimized = True
                pick_wave.status = "ready"

            # Create WMS wave - simulate for now
            # In a real implementation, this would call the WMS system
            pick_wave.status = "active"

            return pick_wave

        except Exception as e:
            logger.error(f"Failed to generate pick wave: {e}")
            return PickWave(
                wave_id=f"WAVE_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                order_ids=order_ids,
                strategy=wave_strategy,
                total_lines=0,
                estimated_duration=0,
                assigned_pickers=[],
                zones=[],
                status="error",
                created_at=datetime.now(),
                labels_generated=False,
                route_optimized=False,
            )

    async def optimize_pick_paths(
        self, picker_id: str, wave_id: Optional[str] = None
    ) -> PickPathOptimization:
        """
        Optimize pick paths for a picker.

        Args:
            picker_id: ID of the picker
            wave_id: Optional wave ID to optimize

        Returns:
            PickPathOptimization with optimized route
        """
        try:
            if not self.wms_service:
                await self.initialize()

            # Get picker's current tasks
            picker_tasks = await self.wms_service.get_picker_tasks(picker_id, wave_id)

            if not picker_tasks:
                return PickPathOptimization(
                    picker_id=picker_id,
                    optimized_route=[],
                    total_distance=0.0,
                    time_savings=0,
                    efficiency_score=0.0,
                    waypoints=[],
                )

            # Apply path optimization algorithm
            optimized_route = await self._apply_path_optimization(picker_tasks)

            # Calculate metrics
            original_distance = self._calculate_original_distance(picker_tasks)
            optimized_distance = optimized_route.get("total_distance", 0.0)
            time_savings = int(
                (original_distance - optimized_distance) * 2
            )  # Assume 2 min per unit distance

            efficiency_score = (
                min(100.0, (1 - optimized_distance / original_distance) * 100)
                if original_distance > 0
                else 0.0
            )

            return PickPathOptimization(
                picker_id=picker_id,
                optimized_route=optimized_route.get("route", []),
                total_distance=optimized_distance,
                time_savings=time_savings,
                efficiency_score=efficiency_score,
                waypoints=optimized_route.get("waypoints", []),
            )

        except Exception as e:
            logger.error(f"Failed to optimize pick paths for {picker_id}: {e}")
            return PickPathOptimization(
                picker_id=picker_id,
                optimized_route=[],
                total_distance=0.0,
                time_savings=0,
                efficiency_score=0.0,
                waypoints=[],
            )

    async def manage_shift_schedule(
        self,
        shift_id: str,
        action: str,
        workers: Optional[List[str]] = None,
        swaps: Optional[List[Dict[str, str]]] = None,
    ) -> ShiftSchedule:
        """
        Manage shift schedule with worker changes.

        Args:
            shift_id: ID of the shift
            action: Action to perform (add, remove, swap)
            workers: List of workers to add/remove
            swaps: List of worker swaps

        Returns:
            ShiftSchedule with updated schedule
        """
        try:
            if not self.attendance_service:
                await self.initialize()

            # Get current shift details
            shift_details = await self.attendance_service.get_shift_details(shift_id)

            if not shift_details:
                raise ValueError(f"Shift {shift_id} not found")

            # Apply changes based on action
            changes = []
            current_workers = shift_details.get("workers", [])

            if action == "add" and workers:
                for worker_id in workers:
                    if worker_id not in current_workers:
                        current_workers.append(worker_id)
                        changes.append(
                            {
                                "action": "add",
                                "worker_id": worker_id,
                                "timestamp": datetime.now().isoformat(),
                            }
                        )

            elif action == "remove" and workers:
                for worker_id in workers:
                    if worker_id in current_workers:
                        current_workers.remove(worker_id)
                        changes.append(
                            {
                                "action": "remove",
                                "worker_id": worker_id,
                                "timestamp": datetime.now().isoformat(),
                            }
                        )

            elif action == "swap" and swaps:
                for swap in swaps:
                    worker_a = swap.get("from")
                    worker_b = swap.get("to")
                    if worker_a in current_workers and worker_b not in current_workers:
                        current_workers.remove(worker_a)
                        current_workers.append(worker_b)
                        changes.append(
                            {
                                "action": "swap",
                                "from": worker_a,
                                "to": worker_b,
                                "timestamp": datetime.now().isoformat(),
                            }
                        )

            # Update shift schedule
            updated_shift = ShiftSchedule(
                shift_id=shift_id,
                shift_type=shift_details.get("shift_type", "regular"),
                start_time=datetime.fromisoformat(
                    shift_details.get("start_time", datetime.now().isoformat())
                ),
                end_time=datetime.fromisoformat(
                    shift_details.get("end_time", datetime.now().isoformat())
                ),
                workers=[{"worker_id": w, "status": "active"} for w in current_workers],
                capacity=shift_details.get("capacity", len(current_workers)),
                status="updated",
                changes=changes,
                created_at=datetime.now(),
            )

            # Apply changes to attendance system
            await self.attendance_service.update_shift_schedule(shift_id, updated_shift)

            return updated_shift

        except Exception as e:
            logger.error(f"Failed to manage shift schedule: {e}")
            return ShiftSchedule(
                shift_id=shift_id,
                shift_type="regular",
                start_time=datetime.now(),
                end_time=datetime.now() + timedelta(hours=8),
                workers=[],
                capacity=0,
                status="error",
                changes=[],
                created_at=datetime.now(),
            )

    async def dock_scheduling(
        self, appointments: List[Dict[str, Any]], capacity: Dict[str, int]
    ) -> List[DockAppointment]:
        """
        Schedule dock appointments with capacity constraints.

        Args:
            appointments: List of appointment requests
            capacity: Dock capacity by door

        Returns:
            List[DockAppointment] with scheduled appointments
        """
        try:
            if not self.wms_service:
                await self.initialize()

            scheduled_appointments = []

            for appointment in appointments:
                # Find optimal dock door
                optimal_door = await self._find_optimal_dock_door(appointment, capacity)

                if optimal_door:
                    # Create dock appointment
                    dock_appointment = DockAppointment(
                        appointment_id=f"APT_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                        dock_door=optimal_door,
                        carrier=appointment.get("carrier", "Unknown"),
                        trailer_id=appointment.get("trailer_id", ""),
                        scheduled_time=datetime.fromisoformat(
                            appointment.get(
                                "requested_time", datetime.now().isoformat()
                            )
                        ),
                        duration=appointment.get("duration", 60),
                        cargo_type=appointment.get("cargo_type", "general"),
                        priority=appointment.get("priority", "normal"),
                        status="scheduled",
                        created_at=datetime.now(),
                    )

                    scheduled_appointments.append(dock_appointment)

                    # Update capacity
                    capacity[optimal_door] -= 1
                else:
                    logger.warning(
                        f"No available dock door for appointment: {appointment}"
                    )

            # Create dock schedule in WMS
            await self.wms_service.create_dock_schedule(scheduled_appointments)

            return scheduled_appointments

        except Exception as e:
            logger.error(f"Failed to schedule dock appointments: {e}")
            return []

    async def dispatch_equipment(
        self, equipment_id: str, task_id: str, operator: Optional[str] = None
    ) -> EquipmentDispatch:
        """
        Dispatch equipment for a task.

        Args:
            equipment_id: ID of the equipment
            task_id: ID of the task
            operator: Optional specific operator

        Returns:
            EquipmentDispatch with dispatch details
        """
        try:
            if not self.iot_service:
                await self.initialize()

            dispatch_id = f"DISP_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Get equipment details from IoT service first
            equipment_details = await self.iot_service.get_equipment_details(
                equipment_id
            )

            # Fallback to database if not found in IoT service
            if not equipment_details:
                logger.info(
                    f"Equipment {equipment_id} not found in IoT service, checking database..."
                )
                from src.api.agents.inventory.equipment_asset_tools import (
                    get_equipment_asset_tools,
                )

                asset_tools = await get_equipment_asset_tools()
                equipment_status = await asset_tools.get_equipment_status(
                    asset_id=equipment_id
                )

                if equipment_status and equipment_status.get("equipment"):
                    equipment_data = (
                        equipment_status["equipment"][0]
                        if equipment_status["equipment"]
                        else {}
                    )
                    equipment_details = {
                        "type": equipment_data.get("type", "unknown"),
                        "current_location": equipment_data.get("zone", "unknown"),
                        "status": equipment_data.get("status", "unknown"),
                    }
                else:
                    raise ValueError(
                        f"Equipment {equipment_id} not found in database or IoT service"
                    )

            # Find operator if not specified
            if not operator:
                operator = await self._find_available_operator(equipment_id)

            # Create task in database
            task_created = False
            task_db_id = None
            if self.sql_retriever:
                try:
                    # Extract zone and task type from context if available
                    zone = equipment_details.get("current_location", "unknown")
                    task_type = "equipment_dispatch"
                    
                    # Create task payload
                    task_payload = {
                        "equipment_id": equipment_id,
                        "equipment_type": equipment_details.get("type", "unknown"),
                        "dispatch_id": dispatch_id,
                        "zone": zone,
                        "operator": operator,
                    }
                    
                    # Insert task into database
                    create_task_query = """
                        INSERT INTO tasks (kind, status, assignee, payload, created_at, updated_at)
                        VALUES ($1, $2, $3, $4, NOW(), NOW())
                        RETURNING id
                    """
                    task_result = await self.sql_retriever.fetch_one(
                        create_task_query,
                        task_type,
                        "pending",
                        operator or "system",
                        json.dumps(task_payload),
                    )
                    
                    if task_result:
                        task_db_id = task_result["id"]
                        task_created = True
                        logger.info(f"Created task {task_db_id} for equipment dispatch {dispatch_id}")
                except Exception as e:
                    logger.warning(f"Failed to create task in database: {e}")
                    # Continue with dispatch even if task creation fails

            # Assign equipment to task using equipment asset tools
            equipment_assigned = False
            try:
                from src.api.agents.inventory.equipment_asset_tools import (
                    get_equipment_asset_tools,
                )
                
                asset_tools = await get_equipment_asset_tools()
                assignment_result = await asset_tools.assign_equipment(
                    asset_id=equipment_id,
                    assignee=operator or "system",
                    assignment_type="task",
                    task_id=task_id,
                    notes=f"Dispatched for task {task_id}",
                )
                
                if assignment_result.get("success"):
                    equipment_assigned = True
                    logger.info(f"Assigned equipment {equipment_id} to task {task_id}")
                else:
                    logger.warning(f"Equipment assignment failed: {assignment_result.get('error')}")
            except Exception as e:
                logger.warning(f"Failed to assign equipment: {e}")
                # Continue with dispatch even if assignment fails

            # Create dispatch
            dispatch_status = "dispatched" if (task_created or equipment_assigned) else "pending"
            dispatch = EquipmentDispatch(
                dispatch_id=dispatch_id,
                equipment_id=equipment_id,
                equipment_type=equipment_details.get("type", "unknown"),
                task_id=task_id,
                assigned_operator=operator,
                location=equipment_details.get("current_location", "unknown"),
                status=dispatch_status,
                created_at=datetime.now(),
                estimated_completion=datetime.now() + timedelta(hours=2),
            )

            # Update equipment status in IoT service if available
            try:
                await self.iot_service.update_equipment_status(
                    equipment_id, "in_use", task_id
                )
                await self.iot_service.notify_operator(operator, dispatch)
            except Exception as e:
                logger.warning(f"Could not update IoT service: {e}")
                # Continue with dispatch even if IoT update fails

            return dispatch

        except Exception as e:
            logger.error(f"Failed to dispatch equipment {equipment_id}: {e}")
            return EquipmentDispatch(
                dispatch_id=f"DISP_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                equipment_id=equipment_id,
                equipment_type="unknown",
                task_id=task_id,
                assigned_operator=operator or "unknown",
                location="unknown",
                status="error",
                created_at=datetime.now(),
                estimated_completion=datetime.now(),
            )

    async def publish_kpis(
        self, metrics: Optional[KPIMetrics] = None
    ) -> Dict[str, Any]:
        """
        Publish KPI metrics to Kafka for dashboard updates.

        Args:
            metrics: Optional specific metrics to publish

        Returns:
            Dict with publishing results
        """
        try:
            if not metrics:
                # Generate current metrics
                metrics = await self._generate_current_kpis()

            # Publish to Kafka
            kafka_result = await self._publish_to_kafka(metrics)

            return {
                "success": kafka_result,
                "metrics_published": asdict(metrics),
                "timestamp": datetime.now().isoformat(),
                "topics": [
                    "warehouse.throughput",
                    "warehouse.sla",
                    "warehouse.utilization",
                ],
            }

        except Exception as e:
            logger.error(f"Failed to publish KPIs: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    # Helper methods
    async def _find_qualified_assignees(
        self, task_type: str, constraints: Dict[str, Any]
    ) -> List[str]:
        """Find qualified assignees for a task."""
        # This would integrate with HR/attendance system
        return ["worker_001", "worker_002", "worker_003"]

    async def _apply_rebalancing_algorithm(
        self, workload: Dict, capacity: Dict, sla_rules: Dict
    ) -> Dict:
        """Apply workload rebalancing algorithm."""
        # Simplified rebalancing logic
        return {
            "assignments": workload.get("assignments", []),
            "sla_impact": {"improvement": 0.05},
        }

    def _calculate_workload_efficiency(self, workload: Dict) -> float:
        """Calculate workload efficiency score."""
        # Simplified efficiency calculation
        return 0.85

    async def _assign_pickers_for_wave(
        self, zones: List[str], strategy: str
    ) -> List[str]:
        """Assign pickers for a wave based on strategy."""
        # Simplified picker assignment
        return ["picker_001", "picker_002"]

    async def _estimate_wave_duration(self, total_lines: int, picker_count: int) -> int:
        """Estimate wave duration in minutes."""
        # Simplified duration estimation
        return max(30, total_lines // max(1, picker_count) * 2)

    async def _optimize_pick_routes(self, pick_wave: PickWave) -> Optional[Dict]:
        """Optimize pick routes for a wave."""
        # Simplified route optimization
        return {"optimized": True, "efficiency_gain": 0.15}

    def _calculate_original_distance(self, tasks: List[Dict]) -> float:
        """Calculate original distance for tasks."""
        return len(tasks) * 10.0  # Simplified calculation

    async def _apply_path_optimization(self, tasks: List[Dict]) -> Dict:
        """Apply path optimization algorithm."""
        # Simplified path optimization
        return {"route": tasks, "total_distance": len(tasks) * 8.0, "waypoints": []}

    async def _find_optimal_dock_door(
        self, appointment: Dict, capacity: Dict
    ) -> Optional[str]:
        """Find optimal dock door for appointment."""
        # Simplified dock door selection
        for door, cap in capacity.items():
            if cap > 0:
                return door
        return None

    async def _find_available_operator(self, equipment_id: str) -> str:
        """Find available operator for equipment."""
        # Simplified operator assignment
        return "operator_001"

    async def _generate_current_kpis(self) -> KPIMetrics:
        """Generate current KPI metrics."""
        return KPIMetrics(
            timestamp=datetime.now(),
            throughput={"orders_per_hour": 45.2, "lines_per_hour": 120.5},
            sla_metrics={"on_time_delivery": 0.95, "pick_accuracy": 0.98},
            utilization={"equipment": 0.78, "labor": 0.82},
            productivity={"picks_per_hour": 15.3, "moves_per_hour": 8.7},
            quality_metrics={"error_rate": 0.02, "rework_rate": 0.01},
        )

    async def _publish_to_kafka(self, metrics: KPIMetrics) -> bool:
        """Publish metrics to Kafka."""
        # Simplified Kafka publishing
        logger.info(f"Publishing KPIs to Kafka: {metrics.timestamp}")
        return True


# Global action tools instance
_action_tools: Optional[OperationsActionTools] = None


async def get_operations_action_tools() -> OperationsActionTools:
    """Get or create the global operations action tools instance."""
    global _action_tools
    if _action_tools is None:
        _action_tools = OperationsActionTools()
        await _action_tools.initialize()
    return _action_tools
