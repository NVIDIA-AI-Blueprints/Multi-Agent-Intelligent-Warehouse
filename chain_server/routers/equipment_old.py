from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel
from inventory_retriever.structured import SQLRetriever, InventoryQueries
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Equipment"])

# Initialize SQL retriever
sql_retriever = SQLRetriever()


class EquipmentItem(BaseModel):
    sku: str
    name: str
    quantity: int
    location: str
    reorder_point: int
    updated_at: str


class EquipmentUpdate(BaseModel):
    name: Optional[str] = None
    quantity: Optional[int] = None
    location: Optional[str] = None
    reorder_point: Optional[int] = None


@router.get("/equipment", response_model=List[EquipmentItem])
async def get_all_equipment_items():
    """Get all equipment items."""
    try:
        await sql_retriever.initialize()
        query = "SELECT sku, name, quantity, location, reorder_point, updated_at FROM inventory_items ORDER BY name"
        results = await sql_retriever.fetch_all(query)

        items = []
        for row in results:
            items.append(
                EquipmentItem(
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
        logger.error(f"Failed to get equipment items: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve equipment items"
        )


@router.get("/equipment/{sku}", response_model=EquipmentItem)
async def get_equipment_item(sku: str):
    """Get a specific equipment item by SKU."""
    try:
        await sql_retriever.initialize()
        item = await InventoryQueries(sql_retriever).get_item_by_sku(sku)

        if not item:
            raise HTTPException(
                status_code=404, detail=f"Equipment item with SKU {sku} not found"
            )

        return EquipmentItem(
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
        raise HTTPException(status_code=500, detail="Failed to retrieve equipment item")


@router.post("/equipment", response_model=EquipmentItem)
async def create_equipment_item(item: EquipmentItem):
    """Create a new equipment item."""
    try:
        await sql_retriever.initialize()
        # Insert new equipment item
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
        logger.error(f"Failed to create equipment item: {e}")
        raise HTTPException(status_code=500, detail="Failed to create equipment item")


@router.put("/equipment/{sku}", response_model=EquipmentItem)
async def update_equipment_item(sku: str, update: EquipmentUpdate):
    """Update an existing equipment item."""
    try:
        await sql_retriever.initialize()

        # Get current item
        current_item = await InventoryQueries(sql_retriever).get_item_by_sku(sku)
        if not current_item:
            raise HTTPException(
                status_code=404, detail=f"Equipment item with SKU {sku} not found"
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
        return EquipmentItem(
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
        logger.error(f"Failed to update equipment item {sku}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update equipment item")
