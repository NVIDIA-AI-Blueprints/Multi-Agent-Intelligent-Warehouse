"""
Equipment & Asset Operations Agent Action Tools

Provides comprehensive action tools for equipment and asset management including:
- Equipment availability and assignment tracking
- Asset utilization and performance monitoring
- Maintenance scheduling and work order management
- Equipment telemetry and status monitoring
- Compliance and safety integration
"""

import logging
from typing import Dict, List, Optional, Any, Union, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import asyncio
import json

from chain_server.services.llm.nim_client import get_nim_client
from inventory_retriever.structured.inventory_queries import InventoryItem
from inventory_retriever.structured.sql_retriever import SQLRetriever
from chain_server.services.wms.integration_service import get_wms_service
from chain_server.services.erp.integration_service import get_erp_service
from chain_server.services.scanning.integration_service import get_scanning_service

logger = logging.getLogger(__name__)


@dataclass
class StockInfo:
    """Stock information for a SKU."""

    sku: str
    on_hand: int
    available_to_promise: int
    locations: List[
        Dict[str, Any]
    ]  # [{"location": "A1", "quantity": 10, "status": "available"}]
    last_updated: datetime
    reorder_point: int
    safety_stock: int


@dataclass
class ReservationResult:
    """Result of inventory reservation."""

    success: bool
    reservation_id: Optional[str]
    reserved_quantity: int
    hold_until: datetime
    order_id: str
    message: str


@dataclass
class ReplenishmentTask:
    """Replenishment task details."""

    task_id: str
    sku: str
    from_location: str
    to_location: str
    quantity: int
    priority: str  # "high", "medium", "low"
    status: str  # "pending", "in_progress", "completed", "failed"
    created_at: datetime
    assigned_to: Optional[str]


@dataclass
class PurchaseRequisition:
    """Purchase requisition details."""

    pr_id: str
    sku: str
    quantity: int
    supplier: Optional[str]
    contract_id: Optional[str]
    need_by_date: datetime
    status: str  # "draft", "pending_approval", "approved", "rejected"
    created_at: datetime
    created_by: str
    total_cost: Optional[float]


@dataclass
class CycleCountTask:
    """Cycle count task details."""

    task_id: str
    sku: Optional[str]
    location: Optional[str]
    class_name: Optional[str]
    priority: str
    status: str
    created_at: datetime
    assigned_to: Optional[str]
    due_date: datetime


@dataclass
class DiscrepancyInvestigation:
    """Discrepancy investigation details."""

    investigation_id: str
    sku: str
    location: str
    expected_quantity: int
    actual_quantity: int
    discrepancy_amount: int
    status: str  # "open", "investigating", "resolved", "closed"
    created_at: datetime
    assigned_to: Optional[str]
    findings: List[str]
    resolution: Optional[str]


class EquipmentActionTools:
    """
    Action tools for Equipment & Asset Operations Agent.

    Provides comprehensive equipment and asset management capabilities including:
    - Equipment availability and assignment tracking
    - Inventory reservations and holds
    - Replenishment task creation
    - Purchase requisition generation
    - Reorder point management
    - Cycle counting operations
    - Discrepancy investigation
    """

    def __init__(self):
        self.nim_client = None
        self.sql_retriever = None
        self.wms_service = None
        self.erp_service = None
        self.scanning_service = None

    async def initialize(self) -> None:
        """Initialize action tools with required services."""
        try:
            self.nim_client = await get_nim_client()
            self.sql_retriever = SQLRetriever()
            await self.sql_retriever.initialize()
            self.wms_service = await get_wms_service()
            self.erp_service = await get_erp_service()
            self.scanning_service = await get_scanning_service()
            logger.info("Inventory Action Tools initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Inventory Action Tools: {e}")
            raise

    async def check_stock(
        self,
        sku: str,
        site: Optional[str] = None,
        locations: Optional[List[str]] = None,
    ) -> StockInfo:
        """
        Check stock levels for a SKU with ATP calculation.

        Args:
            sku: SKU to check
            site: Optional site filter
            locations: Optional location filter

        Returns:
            StockInfo with on_hand, ATP, and location details
        """
        try:
            if not self.sql_retriever:
                await self.initialize()

            # Get stock data directly from database
            query = """
            SELECT sku, name, quantity, location, reorder_point, updated_at
            FROM inventory_items 
            WHERE sku = $1
            """
            params = [sku]

            if locations:
                location_conditions = []
                for i, loc in enumerate(locations, start=2):
                    location_conditions.append(f"location LIKE ${i}")
                    params.append(f"%{loc}%")
                query += f" AND ({' OR '.join(location_conditions)})"

            results = await self.sql_retriever.fetch_all(query, *params)

            if not results:
                return StockInfo(
                    sku=sku,
                    on_hand=0,
                    available_to_promise=0,
                    locations=[],
                    last_updated=datetime.now(),
                    reorder_point=0,
                    safety_stock=0,
                )

            # Calculate ATP (Available to Promise)
            # For now, we'll use the basic quantity as ATP (simplified)
            # In a real system, this would consider reservations, incoming orders, etc.
            item = results[0]
            on_hand = item.get("quantity", 0)
            reserved = 0  # Would come from reservations table in real implementation
            atp = max(0, on_hand - reserved)

            reorder_point = item.get("reorder_point", 0)
            safety_stock = (
                0  # Would come from item configuration in real implementation
            )

            return StockInfo(
                sku=sku,
                on_hand=on_hand,
                available_to_promise=atp,
                locations=[{"location": item.get("location", ""), "quantity": on_hand}],
                last_updated=item.get("updated_at", datetime.now()),
                reorder_point=reorder_point,
                safety_stock=safety_stock,
            )

        except Exception as e:
            logger.error(f"Failed to check stock for SKU {sku}: {e}")
            return StockInfo(
                sku=sku,
                on_hand=0,
                available_to_promise=0,
                locations=[],
                last_updated=datetime.now(),
                reorder_point=0,
                safety_stock=0,
            )

    async def reserve_inventory(
        self, sku: str, qty: int, order_id: str, hold_until: Optional[datetime] = None
    ) -> ReservationResult:
        """
        Reserve inventory for an order.

        Args:
            sku: SKU to reserve
            qty: Quantity to reserve
            order_id: Order identifier
            hold_until: Optional hold expiration date

        Returns:
            ReservationResult with success status and details
        """
        try:
            if not self.wms_service:
                await self.initialize()

            # Check if sufficient stock is available
            stock_info = await self.check_stock(sku)
            if stock_info.available_to_promise < qty:
                return ReservationResult(
                    success=False,
                    reservation_id=None,
                    reserved_quantity=0,
                    hold_until=hold_until or datetime.now() + timedelta(days=7),
                    order_id=order_id,
                    message=f"Insufficient stock. Available: {stock_info.available_to_promise}, Requested: {qty}",
                )

            # Create reservation in WMS
            reservation_data = await self.wms_service.create_reservation(
                sku=sku,
                quantity=qty,
                order_id=order_id,
                hold_until=hold_until or datetime.now() + timedelta(days=7),
            )

            if reservation_data and reservation_data.get("success"):
                return ReservationResult(
                    success=True,
                    reservation_id=reservation_data.get("reservation_id"),
                    reserved_quantity=qty,
                    hold_until=hold_until or datetime.now() + timedelta(days=7),
                    order_id=order_id,
                    message=f"Successfully reserved {qty} units of {sku} for order {order_id}",
                )
            else:
                return ReservationResult(
                    success=False,
                    reservation_id=None,
                    reserved_quantity=0,
                    hold_until=hold_until or datetime.now() + timedelta(days=7),
                    order_id=order_id,
                    message=f"Failed to create reservation: {reservation_data.get('error', 'Unknown error')}",
                )

        except Exception as e:
            logger.error(f"Failed to reserve inventory for SKU {sku}: {e}")
            return ReservationResult(
                success=False,
                reservation_id=None,
                reserved_quantity=0,
                hold_until=hold_until or datetime.now() + timedelta(days=7),
                order_id=order_id,
                message=f"Reservation failed: {str(e)}",
            )

    async def create_replenishment_task(
        self,
        sku: str,
        from_location: str,
        to_location: str,
        qty: int,
        priority: str = "medium",
    ) -> ReplenishmentTask:
        """
        Create a replenishment task in WMS.

        Args:
            sku: SKU to replenish
            from_location: Source location
            to_location: Destination location
            qty: Quantity to move
            priority: Task priority (high, medium, low)

        Returns:
            ReplenishmentTask with task details
        """
        try:
            if not self.wms_service:
                await self.initialize()

            # Create replenishment task in WMS
            task_data = await self.wms_service.create_replenishment_task(
                sku=sku,
                from_location=from_location,
                to_location=to_location,
                quantity=qty,
                priority=priority,
            )

            if task_data and task_data.get("success"):
                return ReplenishmentTask(
                    task_id=task_data.get("task_id"),
                    sku=sku,
                    from_location=from_location,
                    to_location=to_location,
                    quantity=qty,
                    priority=priority,
                    status="pending",
                    created_at=datetime.now(),
                    assigned_to=task_data.get("assigned_to"),
                )
            else:
                # Create fallback task
                task_id = f"REPL_{sku}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                return ReplenishmentTask(
                    task_id=task_id,
                    sku=sku,
                    from_location=from_location,
                    to_location=to_location,
                    quantity=qty,
                    priority=priority,
                    status="pending",
                    created_at=datetime.now(),
                    assigned_to=None,
                )

        except Exception as e:
            logger.error(f"Failed to create replenishment task for SKU {sku}: {e}")
            # Create fallback task
            task_id = f"REPL_{sku}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            return ReplenishmentTask(
                task_id=task_id,
                sku=sku,
                from_location=from_location,
                to_location=to_location,
                quantity=qty,
                priority=priority,
                status="pending",
                created_at=datetime.now(),
                assigned_to=None,
            )

    async def generate_purchase_requisition(
        self,
        sku: str,
        qty: int,
        supplier: Optional[str] = None,
        contract_id: Optional[str] = None,
        need_by_date: Optional[datetime] = None,
        tier: int = 1,
        user_id: str = "system",
    ) -> PurchaseRequisition:
        """
        Generate purchase requisition (Tier 1: propose, Tier 2: auto-approve).

        Args:
            sku: SKU to purchase
            qty: Quantity to purchase
            supplier: Optional supplier
            contract_id: Optional contract ID
            need_by_date: Required delivery date
            tier: Approval tier (1=propose, 2=auto-approve)
            user_id: User creating the PR

        Returns:
            PurchaseRequisition with PR details
        """
        try:
            if not self.erp_service:
                await self.initialize()

            # Get item cost and supplier info
            item_info = await self.erp_service.get_item_details(sku)
            cost_per_unit = item_info.get("cost", 0.0) if item_info else 0.0
            total_cost = cost_per_unit * qty

            # Determine status based on tier
            status = "pending_approval" if tier == 1 else "approved"

            # Create PR in ERP
            pr_data = await self.erp_service.create_purchase_requisition(
                sku=sku,
                quantity=qty,
                supplier=supplier,
                contract_id=contract_id,
                need_by_date=need_by_date or datetime.now() + timedelta(days=14),
                total_cost=total_cost,
                created_by=user_id,
                auto_approve=(tier == 2),
            )

            if pr_data and pr_data.get("success"):
                return PurchaseRequisition(
                    pr_id=pr_data.get("pr_id"),
                    sku=sku,
                    quantity=qty,
                    supplier=supplier,
                    contract_id=contract_id,
                    need_by_date=need_by_date or datetime.now() + timedelta(days=14),
                    status=status,
                    created_at=datetime.now(),
                    created_by=user_id,
                    total_cost=total_cost,
                )
            else:
                # Create fallback PR
                pr_id = f"PR_{sku}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                return PurchaseRequisition(
                    pr_id=pr_id,
                    sku=sku,
                    quantity=qty,
                    supplier=supplier,
                    contract_id=contract_id,
                    need_by_date=need_by_date or datetime.now() + timedelta(days=14),
                    status=status,
                    created_at=datetime.now(),
                    created_by=user_id,
                    total_cost=total_cost,
                )

        except Exception as e:
            logger.error(f"Failed to generate purchase requisition for SKU {sku}: {e}")
            # Create fallback PR
            pr_id = f"PR_{sku}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            return PurchaseRequisition(
                pr_id=pr_id,
                sku=sku,
                quantity=qty,
                supplier=supplier,
                contract_id=contract_id,
                need_by_date=need_by_date or datetime.now() + timedelta(days=14),
                status="pending_approval",
                created_at=datetime.now(),
                created_by=user_id,
                total_cost=0.0,
            )

    async def adjust_reorder_point(
        self,
        sku: str,
        new_rp: int,
        rationale: str,
        user_id: str = "system",
        requires_approval: bool = True,
    ) -> Dict[str, Any]:
        """
        Adjust reorder point for a SKU (requires RBAC "planner" role).

        Args:
            sku: SKU to adjust
            new_rp: New reorder point value
            rationale: Business rationale for change
            user_id: User making the change
            requires_approval: Whether change requires approval

        Returns:
            Dict with adjustment result
        """
        try:
            if not self.wms_service:
                await self.initialize()

            # Get current reorder point
            current_info = await self.wms_service.get_item_info(sku)
            current_rp = current_info.get("reorder_point", 0) if current_info else 0

            # Create adjustment record
            adjustment_data = {
                "sku": sku,
                "old_reorder_point": current_rp,
                "new_reorder_point": new_rp,
                "rationale": rationale,
                "user_id": user_id,
                "timestamp": datetime.now().isoformat(),
                "requires_approval": requires_approval,
            }

            # Update in WMS
            update_result = await self.wms_service.update_item_info(
                sku=sku, updates={"reorder_point": new_rp}
            )

            if update_result and update_result.get("success"):
                return {
                    "success": True,
                    "message": f"Reorder point updated from {current_rp} to {new_rp}",
                    "adjustment_data": adjustment_data,
                }
            else:
                return {
                    "success": False,
                    "message": f"Failed to update reorder point: {update_result.get('error', 'Unknown error')}",
                    "adjustment_data": adjustment_data,
                }

        except Exception as e:
            logger.error(f"Failed to adjust reorder point for SKU {sku}: {e}")
            return {
                "success": False,
                "message": f"Reorder point adjustment failed: {str(e)}",
                "adjustment_data": None,
            }

    async def recommend_reslotting(
        self, sku: str, peak_velocity_window: int = 30
    ) -> Dict[str, Any]:
        """
        Recommend optimal slotting for a SKU based on velocity.

        Args:
            sku: SKU to analyze
            peak_velocity_window: Days to analyze for velocity

        Returns:
            Dict with reslotting recommendations
        """
        try:
            if not self.wms_service:
                await self.initialize()

            # Get velocity data
            velocity_data = await self.wms_service.get_item_velocity(
                sku=sku, days=peak_velocity_window
            )

            if not velocity_data:
                return {
                    "success": False,
                    "message": "No velocity data available for analysis",
                    "recommendations": [],
                }

            # Calculate optimal slotting
            current_location = velocity_data.get("current_location", "Unknown")
            velocity = velocity_data.get("velocity", 0)
            picks_per_day = velocity_data.get("picks_per_day", 0)

            # Simple slotting logic (can be enhanced with ML)
            if picks_per_day > 100:
                recommended_zone = "A"  # High velocity - close to shipping
                recommended_aisle = "01"
            elif picks_per_day > 50:
                recommended_zone = "B"  # Medium velocity
                recommended_aisle = "02"
            else:
                recommended_zone = "C"  # Low velocity - further away
                recommended_aisle = "03"

            new_location = f"{recommended_zone}{recommended_aisle}"

            # Calculate travel time delta (simplified)
            current_travel_time = (
                120
                if current_location.startswith("A")
                else 180 if current_location.startswith("B") else 240
            )
            new_travel_time = (
                120
                if new_location.startswith("A")
                else 180 if new_location.startswith("B") else 240
            )
            travel_time_delta = new_travel_time - current_travel_time

            return {
                "success": True,
                "message": f"Reslotting recommendation generated for {sku}",
                "recommendations": [
                    {
                        "sku": sku,
                        "current_location": current_location,
                        "recommended_location": new_location,
                        "velocity": velocity,
                        "picks_per_day": picks_per_day,
                        "travel_time_delta_seconds": travel_time_delta,
                        "estimated_savings_per_day": abs(travel_time_delta)
                        * picks_per_day,
                        "rationale": f"Based on {picks_per_day} picks/day, recommend moving to {new_location}",
                    }
                ],
            }

        except Exception as e:
            logger.error(
                f"Failed to generate reslotting recommendation for SKU {sku}: {e}"
            )
            return {
                "success": False,
                "message": f"Reslotting analysis failed: {str(e)}",
                "recommendations": [],
            }

    async def start_cycle_count(
        self,
        sku: Optional[str] = None,
        location: Optional[str] = None,
        class_name: Optional[str] = None,
        priority: str = "medium",
    ) -> CycleCountTask:
        """
        Start a cycle count task.

        Args:
            sku: Optional specific SKU to count
            location: Optional specific location to count
            class_name: Optional item class to count
            priority: Task priority (high, medium, low)

        Returns:
            CycleCountTask with task details
        """
        try:
            if not self.wms_service:
                await self.initialize()

            # Create cycle count task
            task_data = await self.wms_service.create_cycle_count_task(
                sku=sku, location=location, class_name=class_name, priority=priority
            )

            if task_data and task_data.get("success"):
                return CycleCountTask(
                    task_id=task_data.get("task_id"),
                    sku=sku,
                    location=location,
                    class_name=class_name,
                    priority=priority,
                    status="pending",
                    created_at=datetime.now(),
                    assigned_to=task_data.get("assigned_to"),
                    due_date=datetime.now() + timedelta(days=7),
                )
            else:
                # Create fallback task
                task_id = f"CC_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                return CycleCountTask(
                    task_id=task_id,
                    sku=sku,
                    location=location,
                    class_name=class_name,
                    priority=priority,
                    status="pending",
                    created_at=datetime.now(),
                    assigned_to=None,
                    due_date=datetime.now() + timedelta(days=7),
                )

        except Exception as e:
            logger.error(f"Failed to start cycle count task: {e}")
            # Create fallback task
            task_id = f"CC_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            return CycleCountTask(
                task_id=task_id,
                sku=sku,
                location=location,
                class_name=class_name,
                priority=priority,
                status="pending",
                created_at=datetime.now(),
                assigned_to=None,
                due_date=datetime.now() + timedelta(days=7),
            )

    async def investigate_discrepancy(
        self, sku: str, location: str, expected_quantity: int, actual_quantity: int
    ) -> DiscrepancyInvestigation:
        """
        Investigate inventory discrepancy.

        Args:
            sku: SKU with discrepancy
            location: Location with discrepancy
            expected_quantity: Expected quantity
            actual_quantity: Actual quantity found

        Returns:
            DiscrepancyInvestigation with investigation details
        """
        try:
            if not self.wms_service:
                await self.initialize()

            discrepancy_amount = actual_quantity - expected_quantity

            # Get recent transaction history
            transaction_history = await self.wms_service.get_transaction_history(
                sku=sku, location=location, days=30
            )

            # Get recent picks and moves
            recent_activity = await self.wms_service.get_recent_activity(
                sku=sku, location=location, days=7
            )

            # Create investigation
            investigation_id = f"INV_{sku}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            # Analyze potential causes
            findings = []
            if transaction_history:
                findings.append(
                    f"Found {len(transaction_history)} transactions in last 30 days"
                )

            if recent_activity:
                picks = [a for a in recent_activity if a.get("type") == "pick"]
                moves = [a for a in recent_activity if a.get("type") == "move"]
                findings.append(
                    f"Recent activity: {len(picks)} picks, {len(moves)} moves"
                )

            if abs(discrepancy_amount) > 10:
                findings.append(
                    "Large discrepancy detected - may require physical recount"
                )

            return DiscrepancyInvestigation(
                investigation_id=investigation_id,
                sku=sku,
                location=location,
                expected_quantity=expected_quantity,
                actual_quantity=actual_quantity,
                discrepancy_amount=discrepancy_amount,
                status="open",
                created_at=datetime.now(),
                assigned_to=None,
                findings=findings,
                resolution=None,
            )

        except Exception as e:
            logger.error(f"Failed to investigate discrepancy for SKU {sku}: {e}")
            investigation_id = f"INV_{sku}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            return DiscrepancyInvestigation(
                investigation_id=investigation_id,
                sku=sku,
                location=location,
                expected_quantity=expected_quantity,
                actual_quantity=actual_quantity,
                discrepancy_amount=actual_quantity - expected_quantity,
                status="open",
                created_at=datetime.now(),
                assigned_to=None,
                findings=[f"Investigation failed: {str(e)}"],
                resolution=None,
            )

    async def get_equipment_status(self, equipment_id: str) -> Dict[str, Any]:
        """
        Get equipment status including telemetry data and operational state.

        Args:
            equipment_id: Equipment identifier (e.g., "Truck-07", "Forklift-01")

        Returns:
            Equipment status with telemetry data and operational state
        """
        try:
            if not self.sql_retriever:
                await self.initialize()

            # Query equipment telemetry for the last 24 hours
            query = """
            SELECT 
                metric,
                value,
                ts
            FROM equipment_telemetry 
            WHERE equipment_id = $1 
            AND ts >= NOW() - INTERVAL '24 hours'
            ORDER BY ts DESC
            """

            telemetry_data = await self.sql_retriever.fetch_all(query, equipment_id)

            # Process telemetry data
            current_metrics = {}
            for row in telemetry_data:
                metric = row["metric"]
                value = row["value"]
                current_metrics[metric] = value

            # Determine equipment status based on metrics
            status = "unknown"
            battery_level = current_metrics.get("battery_level", 0)
            temperature = current_metrics.get("temperature", 0)
            is_charging = current_metrics.get("is_charging", False)
            is_operational = current_metrics.get("is_operational", True)

            # Status determination logic
            if not is_operational:
                status = "out_of_service"
            elif is_charging:
                status = "charging"
            elif battery_level < 20:
                status = "low_battery"
            elif temperature > 80:
                status = "overheating"
            elif battery_level < 50:
                status = "needs_charging"
            else:
                status = "operational"

            # Get last update time
            last_update = telemetry_data[0]["ts"] if telemetry_data else None

            equipment_status = {
                "equipment_id": equipment_id,
                "status": status,
                "battery_level": battery_level,
                "temperature": temperature,
                "is_charging": is_charging,
                "is_operational": is_operational,
                "last_update": last_update.isoformat() if last_update else None,
                "telemetry_data": current_metrics,
                "recommendations": [],
            }

            # Add recommendations based on status
            if status == "low_battery":
                equipment_status["recommendations"].append(
                    "Equipment needs immediate charging"
                )
            elif status == "overheating":
                equipment_status["recommendations"].append(
                    "Equipment is overheating - check cooling system"
                )
            elif status == "needs_charging":
                equipment_status["recommendations"].append(
                    "Consider charging equipment soon"
                )
            elif status == "out_of_service":
                equipment_status["recommendations"].append(
                    "Equipment is out of service - contact maintenance"
                )

            logger.info(f"Retrieved status for equipment {equipment_id}: {status}")

            return {
                "success": True,
                "equipment_status": equipment_status,
                "message": f"Equipment {equipment_id} status: {status}",
            }

        except Exception as e:
            logger.error(f"Error getting equipment status for {equipment_id}: {e}")
            return {
                "success": False,
                "equipment_status": None,
                "message": f"Failed to get equipment status: {str(e)}",
            }

    async def get_charger_status(self, equipment_id: str) -> Dict[str, Any]:
        """
        Get charger status for specific equipment.

        Args:
            equipment_id: Equipment identifier (e.g., "Truck-07", "Forklift-01")

        Returns:
            Charger status with charging information
        """
        try:
            if not self.sql_retriever:
                await self.initialize()

            # Get equipment status first
            equipment_status_result = await self.get_equipment_status(equipment_id)

            if not equipment_status_result["success"]:
                return equipment_status_result

            equipment_status = equipment_status_result["equipment_status"]

            # Extract charger-specific information
            is_charging = equipment_status.get("is_charging", False)
            battery_level = equipment_status.get("battery_level", 0)
            temperature = equipment_status.get("temperature", 0)
            status = equipment_status.get("status", "unknown")

            # Calculate charging progress and time estimates
            charging_progress = 0
            estimated_charge_time = "Unknown"

            if is_charging:
                charging_progress = battery_level
                if battery_level < 25:
                    estimated_charge_time = "2-3 hours"
                elif battery_level < 50:
                    estimated_charge_time = "1-2 hours"
                elif battery_level < 75:
                    estimated_charge_time = "30-60 minutes"
                else:
                    estimated_charge_time = "15-30 minutes"

            charger_status = {
                "equipment_id": equipment_id,
                "is_charging": is_charging,
                "battery_level": battery_level,
                "charging_progress": charging_progress,
                "estimated_charge_time": estimated_charge_time,
                "temperature": temperature,
                "status": status,
                "last_update": equipment_status.get("last_update"),
                "recommendations": equipment_status.get("recommendations", []),
            }

            # Add charger-specific recommendations
            if not is_charging and battery_level < 30:
                charger_status["recommendations"].append(
                    "Equipment should be connected to charger"
                )
            elif is_charging and temperature > 75:
                charger_status["recommendations"].append(
                    "Monitor temperature during charging"
                )
            elif is_charging and battery_level > 95:
                charger_status["recommendations"].append(
                    "Charging nearly complete - consider disconnecting"
                )

            logger.info(
                f"Retrieved charger status for equipment {equipment_id}: charging={is_charging}, battery={battery_level}%"
            )

            return {
                "success": True,
                "charger_status": charger_status,
                "message": f"Charger status for {equipment_id}: {'Charging' if is_charging else 'Not charging'} ({battery_level}% battery)",
            }

        except Exception as e:
            logger.error(f"Error getting charger status for {equipment_id}: {e}")
            return {
                "success": False,
                "charger_status": None,
                "message": f"Failed to get charger status: {str(e)}",
            }


# Global action tools instance
_action_tools: Optional[EquipmentActionTools] = None


async def get_equipment_action_tools() -> EquipmentActionTools:
    """Get or create the global equipment action tools instance."""
    global _action_tools
    if _action_tools is None:
        _action_tools = EquipmentActionTools()
        await _action_tools.initialize()
    return _action_tools
