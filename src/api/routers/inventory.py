from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from src.retrieval.structured import SQLRetriever, InventoryQueries
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/inventory", tags=["Inventory"])

# Initialize SQL retriever
sql_retriever = SQLRetriever()


class InventoryItem(BaseModel):
    sku: str
    name: str
    quantity: int
    location: str
    reorder_point: int
    updated_at: str


class InventoryUpdate(BaseModel):
    name: Optional[str] = None
    quantity: Optional[int] = None
    location: Optional[str] = None
    reorder_point: Optional[int] = None


@router.get("/items", response_model=List[InventoryItem])
async def get_all_inventory_items():
    """Get all inventory items."""
    try:
        await sql_retriever.initialize()
        query = "SELECT sku, name, quantity, location, reorder_point, updated_at FROM inventory_items ORDER BY name"
        results = await sql_retriever.fetch_all(query)

        items = []
        for row in results:
            items.append(
                InventoryItem(
                    sku=row["sku"],
                    name=row["name"],
                    quantity=row["quantity"],
                    location=row["location"],
                    reorder_point=row["reorder_point"],
                    updated_at=(
                        row["updated_at"].isoformat() if row["updated_at"] else ""
                    ),
                )
            )

        return items
    except Exception as e:
        logger.error(f"Failed to get inventory items: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve inventory items"
        )


@router.get("/items/{sku}", response_model=InventoryItem)
async def get_inventory_item(sku: str):
    """Get a specific inventory item by SKU."""
    try:
        await sql_retriever.initialize()
        item = await InventoryQueries(sql_retriever).get_item_by_sku(sku)

        if not item:
            raise HTTPException(
                status_code=404, detail=f"Inventory item with SKU {sku} not found"
            )

        return InventoryItem(
            sku=item.sku,
            name=item.name,
            quantity=item.quantity,
            location=item.location or "",
            reorder_point=item.reorder_point,
            updated_at=item.updated_at.isoformat() if item.updated_at else "",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get equipment item {sku}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve inventory item")


@router.post("/items", response_model=InventoryItem)
async def create_inventory_item(item: InventoryItem):
    """Create a new inventory item."""
    try:
        await sql_retriever.initialize()
        # Insert new inventory item
        insert_query = """
        INSERT INTO inventory_items (sku, name, quantity, location, reorder_point, updated_at)
        VALUES ($1, $2, $3, $4, $5, NOW())
        """
        await sql_retriever.execute_command(
            insert_query,
            item.sku,
            item.name,
            item.quantity,
            item.location,
            item.reorder_point,
        )

        return item
    except Exception as e:
        logger.error(f"Failed to create inventory item: {e}")
        raise HTTPException(status_code=500, detail="Failed to create inventory item")


@router.put("/items/{sku}", response_model=InventoryItem)
async def update_inventory_item(sku: str, update: InventoryUpdate):
    """Update an existing inventory item."""
    try:
        await sql_retriever.initialize()

        # Get current item
        current_item = await InventoryQueries(sql_retriever).get_item_by_sku(sku)
        if not current_item:
            raise HTTPException(
                status_code=404, detail=f"Inventory item with SKU {sku} not found"
            )

        # Update fields
        name = update.name if update.name is not None else current_item.name
        quantity = (
            update.quantity if update.quantity is not None else current_item.quantity
        )
        location = (
            update.location if update.location is not None else current_item.location
        )
        reorder_point = (
            update.reorder_point
            if update.reorder_point is not None
            else current_item.reorder_point
        )

        await InventoryQueries(sql_retriever).update_item_quantity(sku, quantity)

        # Update other fields if needed
        if update.name or update.location or update.reorder_point:
            query = """
                UPDATE inventory_items 
                SET name = $1, location = $2, reorder_point = $3, updated_at = NOW()
                WHERE sku = $4
            """
            await sql_retriever.execute_command(
                query, name, location, reorder_point, sku
            )

        # Return updated item
        updated_item = await InventoryQueries(sql_retriever).get_item_by_sku(sku)
        return InventoryItem(
            sku=updated_item.sku,
            name=updated_item.name,
            quantity=updated_item.quantity,
            location=updated_item.location or "",
            reorder_point=updated_item.reorder_point,
            updated_at=(
                updated_item.updated_at.isoformat() if updated_item.updated_at else ""
            ),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update inventory item {sku}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update inventory item")


@router.get("/movements")
async def get_inventory_movements(
    sku: Optional[str] = None,
    movement_type: Optional[str] = None,
    days_back: int = 30,
    limit: int = 1000
):
    """Get inventory movements with optional filtering."""
    try:
        await sql_retriever.initialize()
        
        # Build dynamic query
        where_conditions = []
        params = []
        param_count = 1
        
        if sku:
            where_conditions.append(f"sku = ${param_count}")
            params.append(sku)
            param_count += 1
        
        if movement_type:
            where_conditions.append(f"movement_type = ${param_count}")
            params.append(movement_type)
            param_count += 1
        
        # Add date filter
        where_conditions.append(f"timestamp >= NOW() - INTERVAL '{days_back} days'")
        
        where_clause = " AND ".join(where_conditions) if where_conditions else "timestamp >= NOW() - INTERVAL '30 days'"
        
        query = f"""
            SELECT sku, movement_type, quantity, timestamp, location, notes
            FROM inventory_movements 
            WHERE {where_clause}
            ORDER BY timestamp DESC
            LIMIT {limit}
        """
        
        results = await sql_retriever.fetch_all(query, tuple(params))
        
        return {
            "movements": results,
            "count": len(results),
            "filters": {
                "sku": sku,
                "movement_type": movement_type,
                "days_back": days_back
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting inventory movements: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve inventory movements")


@router.get("/demand/summary")
async def get_demand_summary(
    sku: Optional[str] = None,
    days_back: int = 30
):
    """Get demand summary for products."""
    try:
        await sql_retriever.initialize()
        
        where_clause = "WHERE movement_type = 'outbound'"
        params = []
        param_count = 1
        
        if sku:
            where_clause += f" AND sku = ${param_count}"
            params.append(sku)
            param_count += 1
        
        where_clause += f" AND timestamp >= NOW() - INTERVAL '{days_back} days'"
        
        query = f"""
            SELECT 
                sku,
                COUNT(*) as movement_count,
                SUM(quantity) as total_demand,
                AVG(quantity) as avg_daily_demand,
                MIN(quantity) as min_daily_demand,
                MAX(quantity) as max_daily_demand,
                STDDEV(quantity) as demand_stddev
            FROM inventory_movements 
            {where_clause}
            GROUP BY sku
            ORDER BY total_demand DESC
        """
        
        results = await sql_retriever.fetch_all(query, tuple(params))
        
        return {
            "demand_summary": results,
            "period_days": days_back,
            "sku_filter": sku
        }
        
    except Exception as e:
        logger.error(f"Error getting demand summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve demand summary")


@router.get("/demand/daily")
async def get_daily_demand(
    sku: str,
    days_back: int = 30
):
    """Get daily demand for a specific SKU."""
    try:
        await sql_retriever.initialize()
        
        query = f"""
            SELECT 
                DATE(timestamp) as date,
                SUM(quantity) as daily_demand,
                COUNT(*) as movement_count
            FROM inventory_movements 
            WHERE sku = $1 
                AND movement_type = 'outbound'
                AND timestamp >= NOW() - INTERVAL '{days_back} days'
            GROUP BY DATE(timestamp)
            ORDER BY date DESC
        """
        
        results = await sql_retriever.fetch_all(query, (sku,))
        
        return {
            "sku": sku,
            "daily_demand": results,
            "period_days": days_back
        }
        
    except Exception as e:
        logger.error(f"Error getting daily demand for {sku}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve daily demand for {sku}")


@router.get("/demand/weekly")
async def get_weekly_demand(
    sku: Optional[str] = None,
    weeks_back: int = 12
):
    """Get weekly demand aggregation."""
    try:
        await sql_retriever.initialize()
        
        where_clause = "WHERE movement_type = 'outbound'"
        params = []
        param_count = 1
        
        if sku:
            where_clause += f" AND sku = ${param_count}"
            params.append(sku)
            param_count += 1
        
        where_clause += f" AND timestamp >= NOW() - INTERVAL '{weeks_back} weeks'"
        
        query = f"""
            SELECT 
                sku,
                DATE_TRUNC('week', timestamp) as week_start,
                SUM(quantity) as weekly_demand,
                COUNT(*) as movement_count,
                AVG(quantity) as avg_quantity_per_movement
            FROM inventory_movements 
            {where_clause}
            GROUP BY sku, DATE_TRUNC('week', timestamp)
            ORDER BY sku, week_start DESC
        """
        
        results = await sql_retriever.fetch_all(query, tuple(params))
        
        return {
            "weekly_demand": results,
            "period_weeks": weeks_back,
            "sku_filter": sku
        }
        
    except Exception as e:
        logger.error(f"Error getting weekly demand: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve weekly demand")


@router.get("/demand/monthly")
async def get_monthly_demand(
    sku: Optional[str] = None,
    months_back: int = 12
):
    """Get monthly demand aggregation."""
    try:
        await sql_retriever.initialize()
        
        where_clause = "WHERE movement_type = 'outbound'"
        params = []
        param_count = 1
        
        if sku:
            where_clause += f" AND sku = ${param_count}"
            params.append(sku)
            param_count += 1
        
        where_clause += f" AND timestamp >= NOW() - INTERVAL '{months_back} months'"
        
        query = f"""
            SELECT 
                sku,
                DATE_TRUNC('month', timestamp) as month_start,
                SUM(quantity) as monthly_demand,
                COUNT(*) as movement_count,
                AVG(quantity) as avg_quantity_per_movement
            FROM inventory_movements 
            {where_clause}
            GROUP BY sku, DATE_TRUNC('month', timestamp)
            ORDER BY sku, month_start DESC
        """
        
        results = await sql_retriever.fetch_all(query, tuple(params))
        
        return {
            "monthly_demand": results,
            "period_months": months_back,
            "sku_filter": sku
        }
        
    except Exception as e:
        logger.error(f"Error getting monthly demand: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve monthly demand")


@router.get("/forecast/demand")
async def get_demand_forecast(
    sku: str,
    horizon_days: int = 30
):
    """Get demand forecast for a specific SKU."""
    try:
        # Load forecast results from file
        import json
        import os
        
        forecast_file = "phase1_phase2_forecasts.json"
        if not os.path.exists(forecast_file):
            raise HTTPException(status_code=404, detail="Forecast data not found. Run forecasting agent first.")
        
        with open(forecast_file, 'r') as f:
            forecasts = json.load(f)
        
        if sku not in forecasts:
            raise HTTPException(status_code=404, detail=f"No forecast found for SKU {sku}")
        
        forecast_data = forecasts[sku]
        
        return {
            "sku": sku,
            "forecast": {
                "predictions": forecast_data['predictions'][:horizon_days],
                "confidence_intervals": forecast_data['confidence_intervals'][:horizon_days],
                "feature_importance": forecast_data['feature_importance'],
                "forecast_date": forecast_data['forecast_date'],
                "horizon_days": horizon_days
            }
        }
        
    except Exception as e:
        logger.error(f"Error getting forecast for {sku}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve forecast for {sku}")


@router.get("/forecast/summary")
async def get_forecast_summary():
    """Get summary of all available forecasts."""
    try:
        import json
        import os
        
        forecast_file = "phase1_phase2_forecasts.json"
        if not os.path.exists(forecast_file):
            raise HTTPException(status_code=404, detail="Forecast data not found. Run forecasting agent first.")
        
        with open(forecast_file, 'r') as f:
            forecasts = json.load(f)
        
        summary = {}
        for sku, forecast_data in forecasts.items():
            predictions = forecast_data['predictions']
            avg_demand = sum(predictions) / len(predictions)
            min_demand = min(predictions)
            max_demand = max(predictions)
            
            summary[sku] = {
                "average_daily_demand": round(avg_demand, 1),
                "min_demand": round(min_demand, 1),
                "max_demand": round(max_demand, 1),
                "trend": "increasing" if predictions[0] < predictions[-1] else "decreasing" if predictions[0] > predictions[-1] else "stable",
                "forecast_date": forecast_data['forecast_date']
            }
        
        return {
            "forecast_summary": summary,
            "total_skus": len(summary),
            "generated_at": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting forecast summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve forecast summary")
