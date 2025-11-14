"""
Inventory-specific SQL queries for warehouse operations.

Provides parameterized queries for inventory management including
stock lookup, replenishment analysis, and cycle counting.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from .sql_retriever import SQLRetriever

@dataclass
class InventoryItem:
    """Data class for inventory items."""
    id: int
    sku: str
    name: str
    quantity: int
    location: Optional[str]
    reorder_point: int
    updated_at: str

@dataclass
class InventorySearchResult:
    """Search result for inventory queries."""
    items: List[InventoryItem]
    total_count: int
    low_stock_items: List[InventoryItem]

class InventoryQueries:
    """Inventory-specific query operations."""
    
    def __init__(self, sql_retriever: SQLRetriever):
        self.sql_retriever = sql_retriever
    
    async def get_item_by_sku(self, sku: str) -> Optional[InventoryItem]:
        """
        Retrieve inventory item by SKU.
        
        Args:
            sku: Stock Keeping Unit identifier
            
        Returns:
            InventoryItem if found, None otherwise
        """
        query = """
        SELECT id, sku, name, quantity, location, reorder_point, updated_at
        FROM inventory_items 
        WHERE sku = $1
        """
        
        try:
            results = await self.sql_retriever.execute_query(query, (sku,))
            if results:
                item_data = results[0]
                return InventoryItem(
                    id=item_data['id'],
                    sku=item_data['sku'],
                    name=item_data['name'],
                    quantity=item_data['quantity'],
                    location=item_data['location'],
                    reorder_point=item_data['reorder_point'],
                    updated_at=str(item_data['updated_at'])
                )
            return None
        except Exception as e:
            raise Exception(f"Failed to retrieve item by SKU {sku}: {e}")
    
    async def search_items(
        self, 
        search_term: Optional[str] = None,
        location: Optional[str] = None,
        low_stock_only: bool = False,
        limit: int = 100,
        offset: int = 0
    ) -> InventorySearchResult:
        """
        Search inventory items with various filters.
        
        Args:
            search_term: Search in SKU and name fields
            location: Filter by location
            low_stock_only: Only return items below reorder point
            limit: Maximum number of results
            offset: Number of results to skip
            
        Returns:
            InventorySearchResult with items and metadata
        """
        # Build dynamic WHERE clause
        where_conditions = []
        params = []
        param_count = 0
        
        if search_term:
            param_count += 1
            where_conditions.append(f"(sku ILIKE ${param_count} OR name ILIKE ${param_count})")
            params.append(f"%{search_term}%")
        
        if location:
            param_count += 1
            where_conditions.append(f"location = ${param_count}")
            params.append(location)
        
        if low_stock_only:
            where_conditions.append("quantity <= reorder_point")
        
        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""
        
        # Count query
        count_query = f"SELECT COUNT(*) FROM inventory_items {where_clause}"
        total_count = await self.sql_retriever.execute_scalar(count_query, tuple(params))
        
        # Main query
        param_count += 1
        limit_param = f"${param_count}"
        param_count += 1
        offset_param = f"${param_count}"
        params.extend([limit, offset])
        
        query = f"""
        SELECT id, sku, name, quantity, location, reorder_point, updated_at
        FROM inventory_items 
        {where_clause}
        ORDER BY updated_at DESC
        LIMIT {limit_param} OFFSET {offset_param}
        """
        
        try:
            results = await self.sql_retriever.execute_query(query, tuple(params))
            items = [
                InventoryItem(
                    id=row['id'],
                    sku=row['sku'],
                    name=row['name'],
                    quantity=row['quantity'],
                    location=row['location'],
                    reorder_point=row['reorder_point'],
                    updated_at=str(row['updated_at'])
                )
                for row in results
            ]
            
            # Get low stock items separately
            low_stock_query = """
            SELECT id, sku, name, quantity, location, reorder_point, updated_at
            FROM inventory_items 
            WHERE quantity <= reorder_point
            ORDER BY (quantity - reorder_point) ASC
            LIMIT 50
            """
            low_stock_results = await self.sql_retriever.execute_query(low_stock_query)
            low_stock_items = [
                InventoryItem(
                    id=row['id'],
                    sku=row['sku'],
                    name=row['name'],
                    quantity=row['quantity'],
                    location=row['location'],
                    reorder_point=row['reorder_point'],
                    updated_at=str(row['updated_at'])
                )
                for row in low_stock_results
            ]
            
            return InventorySearchResult(
                items=items,
                total_count=total_count,
                low_stock_items=low_stock_items
            )
            
        except Exception as e:
            raise Exception(f"Failed to search inventory items: {e}")
    
    async def get_low_stock_items(self, limit: int = 50) -> List[InventoryItem]:
        """
        Get items that are below reorder point.
        
        Args:
            limit: Maximum number of items to return
            
        Returns:
            List of low stock inventory items
        """
        query = """
        SELECT id, sku, name, quantity, location, reorder_point, updated_at
        FROM inventory_items 
        WHERE quantity <= reorder_point
        ORDER BY (quantity - reorder_point) ASC
        LIMIT $1
        """
        
        try:
            results = await self.sql_retriever.execute_query(query, (limit,))
            return [
                InventoryItem(
                    id=row['id'],
                    sku=row['sku'],
                    name=row['name'],
                    quantity=row['quantity'],
                    location=row['location'],
                    reorder_point=row['reorder_point'],
                    updated_at=str(row['updated_at'])
                )
                for row in results
            ]
        except Exception as e:
            raise Exception(f"Failed to get low stock items: {e}")
    
    async def update_item_quantity(self, sku: str, new_quantity: int) -> bool:
        """
        Update inventory item quantity.
        
        Args:
            sku: Stock Keeping Unit identifier
            new_quantity: New quantity value
            
        Returns:
            True if update was successful
        """
        query = """
        UPDATE inventory_items 
        SET quantity = $2, updated_at = NOW()
        WHERE sku = $1
        """
        
        try:
            result = await self.sql_retriever.execute_command(query, (sku, new_quantity))
            return "UPDATE" in result
        except Exception as e:
            raise Exception(f"Failed to update quantity for SKU {sku}: {e}")
    
    async def get_inventory_summary(self) -> Dict[str, Any]:
        """
        Get inventory summary statistics.
        
        Returns:
            Dictionary with inventory summary data
        """
        queries = {
            'total_items': "SELECT COUNT(*) FROM inventory_items",
            'total_quantity': "SELECT SUM(quantity) FROM inventory_items",
            'low_stock_count': "SELECT COUNT(*) FROM inventory_items WHERE quantity <= reorder_point",
            'locations': "SELECT location, COUNT(*) as count FROM inventory_items WHERE location IS NOT NULL GROUP BY location ORDER BY count DESC"
        }
        
        try:
            results = {}
            for key, query in queries.items():
                if key == 'locations':
                    results[key] = await self.sql_retriever.execute_query(query)
                else:
                    results[key] = await self.sql_retriever.execute_scalar(query)
            
            return results
        except Exception as e:
            raise Exception(f"Failed to get inventory summary: {e}")
