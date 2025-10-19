"""
ERP Integration Service

This module provides the main service for managing ERP system integrations.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import asyncio

from adapters.erp import ERPAdapterFactory, ERPConnection, BaseERPAdapter
from adapters.erp.base import ERPResponse

logger = logging.getLogger(__name__)


class ERPIntegrationService:
    """
    Service for managing ERP system integrations.

    Provides a unified interface for interacting with multiple ERP systems
    including SAP ECC, Oracle ERP, and other enterprise systems.
    """

    def __init__(self):
        self.connections: Dict[str, BaseERPAdapter] = {}
        self._initialized = False

    async def initialize(self):
        """Initialize the ERP integration service."""
        if not self._initialized:
            # Load ERP connections from configuration
            await self._load_connections()
            self._initialized = True
            logger.info("ERP Integration Service initialized")

    async def _load_connections(self):
        """Load ERP connections from configuration."""
        # This would typically load from a configuration file or database
        # For now, we'll use placeholder connections
        connections_config = [
            {
                "id": "sap_ecc_prod",
                "system_type": "sap_ecc",
                "base_url": "https://sap-ecc.company.com",
                "username": "erp_user",
                "password": "erp_password",
                "client_id": "sap_client",
                "client_secret": "sap_secret",
            },
            {
                "id": "oracle_erp_prod",
                "system_type": "oracle_erp",
                "base_url": "https://oracle-erp.company.com",
                "username": "erp_user",
                "password": "erp_password",
                "client_id": "oracle_client",
                "client_secret": "oracle_secret",
            },
        ]

        for config in connections_config:
            connection_id = config.pop("id")  # Remove id from config
            connection = ERPConnection(**config)
            adapter = ERPAdapterFactory.create_adapter(connection)

            if adapter:
                self.connections[connection_id] = adapter
                logger.info(f"Loaded ERP connection: {connection_id}")

    async def get_connection(self, connection_id: str) -> Optional[BaseERPAdapter]:
        """Get ERP connection by ID."""
        await self.initialize()
        return self.connections.get(connection_id)

    async def add_connection(
        self, connection_id: str, connection: ERPConnection
    ) -> bool:
        """Add a new ERP connection."""
        await self.initialize()

        adapter = ERPAdapterFactory.create_adapter(connection)
        if adapter:
            self.connections[connection_id] = adapter
            logger.info(f"Added ERP connection: {connection_id}")
            return True
        return False

    async def remove_connection(self, connection_id: str) -> bool:
        """Remove an ERP connection."""
        if connection_id in self.connections:
            adapter = self.connections[connection_id]
            await adapter.disconnect()
            del self.connections[connection_id]
            logger.info(f"Removed ERP connection: {connection_id}")
            return True
        return False

    async def get_employees(
        self, connection_id: str, filters: Optional[Dict[str, Any]] = None
    ) -> ERPResponse:
        """Get employees from specified ERP system."""
        adapter = await self.get_connection(connection_id)
        if not adapter:
            return ERPResponse(
                success=False, error=f"ERP connection not found: {connection_id}"
            )

        try:
            async with adapter:
                return await adapter.get_employees(filters)
        except Exception as e:
            logger.error(f"Failed to get employees from {connection_id}: {e}")
            return ERPResponse(success=False, error=str(e))

    async def get_products(
        self, connection_id: str, filters: Optional[Dict[str, Any]] = None
    ) -> ERPResponse:
        """Get products from specified ERP system."""
        adapter = await self.get_connection(connection_id)
        if not adapter:
            return ERPResponse(
                success=False, error=f"ERP connection not found: {connection_id}"
            )

        try:
            async with adapter:
                return await adapter.get_products(filters)
        except Exception as e:
            logger.error(f"Failed to get products from {connection_id}: {e}")
            return ERPResponse(success=False, error=str(e))

    async def get_suppliers(
        self, connection_id: str, filters: Optional[Dict[str, Any]] = None
    ) -> ERPResponse:
        """Get suppliers from specified ERP system."""
        adapter = await self.get_connection(connection_id)
        if not adapter:
            return ERPResponse(
                success=False, error=f"ERP connection not found: {connection_id}"
            )

        try:
            async with adapter:
                return await adapter.get_suppliers(filters)
        except Exception as e:
            logger.error(f"Failed to get suppliers from {connection_id}: {e}")
            return ERPResponse(success=False, error=str(e))

    async def get_purchase_orders(
        self, connection_id: str, filters: Optional[Dict[str, Any]] = None
    ) -> ERPResponse:
        """Get purchase orders from specified ERP system."""
        adapter = await self.get_connection(connection_id)
        if not adapter:
            return ERPResponse(
                success=False, error=f"ERP connection not found: {connection_id}"
            )

        try:
            async with adapter:
                return await adapter.get_purchase_orders(filters)
        except Exception as e:
            logger.error(f"Failed to get purchase orders from {connection_id}: {e}")
            return ERPResponse(success=False, error=str(e))

    async def get_sales_orders(
        self, connection_id: str, filters: Optional[Dict[str, Any]] = None
    ) -> ERPResponse:
        """Get sales orders from specified ERP system."""
        adapter = await self.get_connection(connection_id)
        if not adapter:
            return ERPResponse(
                success=False, error=f"ERP connection not found: {connection_id}"
            )

        try:
            async with adapter:
                return await adapter.get_sales_orders(filters)
        except Exception as e:
            logger.error(f"Failed to get sales orders from {connection_id}: {e}")
            return ERPResponse(success=False, error=str(e))

    async def get_financial_data(
        self, connection_id: str, filters: Optional[Dict[str, Any]] = None
    ) -> ERPResponse:
        """Get financial data from specified ERP system."""
        adapter = await self.get_connection(connection_id)
        if not adapter:
            return ERPResponse(
                success=False, error=f"ERP connection not found: {connection_id}"
            )

        try:
            async with adapter:
                return await adapter.get_financial_data(filters)
        except Exception as e:
            logger.error(f"Failed to get financial data from {connection_id}: {e}")
            return ERPResponse(success=False, error=str(e))

    async def get_warehouse_data(
        self, connection_id: str, filters: Optional[Dict[str, Any]] = None
    ) -> ERPResponse:
        """Get warehouse data from specified ERP system."""
        adapter = await self.get_connection(connection_id)
        if not adapter:
            return ERPResponse(
                success=False, error=f"ERP connection not found: {connection_id}"
            )

        try:
            async with adapter:
                # Try warehouse-specific method first, fallback to general method
                if hasattr(adapter, "get_warehouse_data"):
                    return await adapter.get_warehouse_data(filters)
                else:
                    return await adapter.get_products(filters)
        except Exception as e:
            logger.error(f"Failed to get warehouse data from {connection_id}: {e}")
            return ERPResponse(success=False, error=str(e))

    async def get_connection_status(self, connection_id: str) -> Dict[str, Any]:
        """Get status of ERP connection."""
        adapter = await self.get_connection(connection_id)
        if not adapter:
            return {
                "connected": False,
                "error": f"Connection not found: {connection_id}",
            }

        try:
            # Test connection by making a simple request
            test_response = await self.get_products(connection_id, {"limit": 1})
            return {
                "connected": test_response.success,
                "error": test_response.error,
                "response_time": test_response.response_time,
            }
        except Exception as e:
            return {"connected": False, "error": str(e)}

    async def get_all_connections_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all ERP connections."""
        status = {}
        for connection_id in self.connections.keys():
            status[connection_id] = await self.get_connection_status(connection_id)
        return status

    async def close_all_connections(self):
        """Close all ERP connections."""
        for adapter in self.connections.values():
            try:
                await adapter.disconnect()
            except Exception as e:
                logger.error(f"Error closing ERP connection: {e}")
        self.connections.clear()
        logger.info("All ERP connections closed")


# Global instance
erp_service = ERPIntegrationService()


async def get_erp_service() -> ERPIntegrationService:
    """Get the global ERP integration service instance."""
    return erp_service
