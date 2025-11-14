"""
ERP Integration API Router

This module provides REST API endpoints for ERP system integration.
"""

import logging
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from datetime import datetime

from src.api.services.erp.integration_service import erp_service
from src.adapters.erp.base import ERPResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/erp", tags=["ERP Integration"])


def parse_filters(filters: Optional[str]) -> Optional[Dict[str, Any]]:
    """Parse JSON string filters to dictionary."""
    if not filters:
        return None
    try:
        import json

        return json.loads(filters)
    except json.JSONDecodeError:
        return None


# Pydantic models
class ERPConnectionRequest(BaseModel):
    """Request model for creating ERP connections."""

    connection_id: str = Field(..., description="Unique connection identifier")
    system_type: str = Field(..., description="ERP system type (sap_ecc, oracle_erp)")
    base_url: str = Field(..., description="ERP system base URL")
    username: str = Field(..., description="Username for authentication")
    password: str = Field(..., description="Password for authentication")
    client_id: Optional[str] = Field(None, description="OAuth2 client ID")
    client_secret: Optional[str] = Field(None, description="OAuth2 client secret")
    api_key: Optional[str] = Field(None, description="API key for authentication")
    timeout: int = Field(30, description="Request timeout in seconds")
    verify_ssl: bool = Field(True, description="Verify SSL certificates")


class ERPQueryRequest(BaseModel):
    """Request model for ERP queries."""

    connection_id: str = Field(..., description="ERP connection ID")
    filters: Optional[Dict[str, Any]] = Field(None, description="Query filters")
    limit: Optional[int] = Field(None, description="Maximum number of results")
    offset: Optional[int] = Field(None, description="Number of results to skip")


class ERPResponseModel(BaseModel):
    """Response model for ERP data."""

    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    status_code: Optional[int] = None
    response_time: Optional[float] = None
    timestamp: datetime


class ERPConnectionStatus(BaseModel):
    """Model for ERP connection status."""

    connection_id: str
    connected: bool
    error: Optional[str] = None
    response_time: Optional[float] = None


@router.get("/connections", response_model=Dict[str, ERPConnectionStatus])
async def get_connections_status():
    """Get status of all ERP connections."""
    try:
        status = await erp_service.get_all_connections_status()
        return {
            conn_id: ERPConnectionStatus(
                connection_id=conn_id,
                connected=info["connected"],
                error=info.get("error"),
                response_time=info.get("response_time"),
            )
            for conn_id, info in status.items()
        }
    except Exception as e:
        logger.error(f"Failed to get connections status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connections/{connection_id}/status", response_model=ERPConnectionStatus)
async def get_connection_status(connection_id: str):
    """Get status of specific ERP connection."""
    try:
        status = await erp_service.get_connection_status(connection_id)
        return ERPConnectionStatus(
            connection_id=connection_id,
            connected=status["connected"],
            error=status.get("error"),
            response_time=status.get("response_time"),
        )
    except Exception as e:
        logger.error(f"Failed to get connection status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/connections", response_model=Dict[str, str])
async def create_connection(request: ERPConnectionRequest):
    """Create a new ERP connection."""
    try:
        from src.adapters.erp.base import ERPConnection

        connection = ERPConnection(
            system_type=request.system_type,
            base_url=request.base_url,
            username=request.username,
            password=request.password,
            client_id=request.client_id,
            client_secret=request.client_secret,
            api_key=request.api_key,
            timeout=request.timeout,
            verify_ssl=request.verify_ssl,
        )

        success = await erp_service.add_connection(request.connection_id, connection)

        if success:
            return {
                "message": f"ERP connection '{request.connection_id}' created successfully"
            }
        else:
            raise HTTPException(
                status_code=400, detail="Failed to create ERP connection"
            )

    except Exception as e:
        logger.error(f"Failed to create ERP connection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/connections/{connection_id}", response_model=Dict[str, str])
async def delete_connection(connection_id: str):
    """Delete an ERP connection."""
    try:
        success = await erp_service.remove_connection(connection_id)

        if success:
            return {"message": f"ERP connection '{connection_id}' deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="ERP connection not found")

    except Exception as e:
        logger.error(f"Failed to delete ERP connection: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connections/{connection_id}/employees", response_model=ERPResponseModel)
async def get_employees(
    connection_id: str,
    filters: Optional[str] = Query(None, description="Query filters as JSON string"),
):
    """Get employees from ERP system."""
    try:
        response = await erp_service.get_employees(
            connection_id, parse_filters(filters)
        )
        return ERPResponseModel(
            success=response.success,
            data=response.data,
            error=response.error,
            status_code=response.status_code,
            response_time=response.response_time,
            timestamp=response.timestamp,
        )
    except Exception as e:
        logger.error(f"Failed to get employees: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connections/{connection_id}/products", response_model=ERPResponseModel)
async def get_products(
    connection_id: str,
    filters: Optional[str] = Query(None, description="Query filters as JSON string"),
):
    """Get products from ERP system."""
    try:
        response = await erp_service.get_products(connection_id, parse_filters(filters))
        return ERPResponseModel(
            success=response.success,
            data=response.data,
            error=response.error,
            status_code=response.status_code,
            response_time=response.response_time,
            timestamp=response.timestamp,
        )
    except Exception as e:
        logger.error(f"Failed to get products: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/connections/{connection_id}/suppliers", response_model=ERPResponseModel)
async def get_suppliers(
    connection_id: str,
    filters: Optional[str] = Query(None, description="Query filters as JSON string"),
):
    """Get suppliers from ERP system."""
    try:
        response = await erp_service.get_suppliers(
            connection_id, parse_filters(filters)
        )
        return ERPResponseModel(
            success=response.success,
            data=response.data,
            error=response.error,
            status_code=response.status_code,
            response_time=response.response_time,
            timestamp=response.timestamp,
        )
    except Exception as e:
        logger.error(f"Failed to get suppliers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/connections/{connection_id}/purchase-orders", response_model=ERPResponseModel
)
async def get_purchase_orders(
    connection_id: str,
    filters: Optional[str] = Query(None, description="Query filters as JSON string"),
):
    """Get purchase orders from ERP system."""
    try:
        response = await erp_service.get_purchase_orders(
            connection_id, parse_filters(filters)
        )
        return ERPResponseModel(
            success=response.success,
            data=response.data,
            error=response.error,
            status_code=response.status_code,
            response_time=response.response_time,
            timestamp=response.timestamp,
        )
    except Exception as e:
        logger.error(f"Failed to get purchase orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/connections/{connection_id}/sales-orders", response_model=ERPResponseModel
)
async def get_sales_orders(
    connection_id: str,
    filters: Optional[str] = Query(None, description="Query filters as JSON string"),
):
    """Get sales orders from ERP system."""
    try:
        response = await erp_service.get_sales_orders(
            connection_id, parse_filters(filters)
        )
        return ERPResponseModel(
            success=response.success,
            data=response.data,
            error=response.error,
            status_code=response.status_code,
            response_time=response.response_time,
            timestamp=response.timestamp,
        )
    except Exception as e:
        logger.error(f"Failed to get sales orders: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/connections/{connection_id}/financial-data", response_model=ERPResponseModel
)
async def get_financial_data(
    connection_id: str,
    filters: Optional[str] = Query(None, description="Query filters as JSON string"),
):
    """Get financial data from ERP system."""
    try:
        response = await erp_service.get_financial_data(
            connection_id, parse_filters(filters)
        )
        return ERPResponseModel(
            success=response.success,
            data=response.data,
            error=response.error,
            status_code=response.status_code,
            response_time=response.response_time,
            timestamp=response.timestamp,
        )
    except Exception as e:
        logger.error(f"Failed to get financial data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/connections/{connection_id}/warehouse-data", response_model=ERPResponseModel
)
async def get_warehouse_data(
    connection_id: str,
    filters: Optional[str] = Query(None, description="Query filters as JSON string"),
):
    """Get warehouse data from ERP system."""
    try:
        response = await erp_service.get_warehouse_data(
            connection_id, parse_filters(filters)
        )
        return ERPResponseModel(
            success=response.success,
            data=response.data,
            error=response.error,
            status_code=response.status_code,
            response_time=response.response_time,
            timestamp=response.timestamp,
        )
    except Exception as e:
        logger.error(f"Failed to get warehouse data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=Dict[str, Any])
async def health_check():
    """Health check for ERP integration service."""
    try:
        await erp_service.initialize()
        connections_status = await erp_service.get_all_connections_status()

        total_connections = len(connections_status)
        active_connections = sum(
            1 for status in connections_status.values() if status["connected"]
        )

        return {
            "status": "healthy",
            "total_connections": total_connections,
            "active_connections": active_connections,
            "connections": connections_status,
        }
    except Exception as e:
        logger.error(f"ERP health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}
