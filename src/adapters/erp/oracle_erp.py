"""
Oracle ERP Adapter

This module provides integration with Oracle ERP Cloud and on-premises
Oracle ERP systems using REST API and SOAP interfaces.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import base64
import json

from .base import BaseERPAdapter, ERPConnection, ERPResponse

logger = logging.getLogger(__name__)

class OracleERPAdapter(BaseERPAdapter):
    """
    Oracle ERP adapter implementation.
    
    Supports both Oracle ERP Cloud and on-premises Oracle ERP systems.
    """
    
    def __init__(self, connection: ERPConnection):
        super().__init__(connection)
        self.api_version = "v1"
        self.service_root = "/fscmRestApi"
        
    def requires_authentication(self) -> bool:
        """Oracle ERP requires authentication."""
        return True
        
    async def authenticate(self) -> bool:
        """Authenticate with Oracle ERP using OAuth2."""
        try:
            # Oracle ERP Cloud OAuth2 authentication
            auth_data = {
                "grant_type": "client_credentials",
                "client_id": self.connection.client_id,
                "client_secret": self.connection.client_secret,
                "scope": "https://your-instance.fa.ocs.oraclecloud.com"
            }
            
            response = await self._make_request(
                method="POST",
                endpoint="/oauth2/v1/token",
                data=auth_data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            
            if response.success and response.data:
                self._auth_token = response.data.get("access_token")
                expires_in = response.data.get("expires_in", 3600)
                self._token_expires = datetime.utcnow() + timedelta(seconds=expires_in)
                return True
                
        except Exception as e:
            logger.error(f"Oracle ERP authentication failed: {e}")
            
        return False
        
    async def get_employees(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get employee data from Oracle ERP."""
        await self._refresh_token_if_needed()
        
        endpoint = f"{self.service_root}/resources/11.13.18.05/workers"
        params = self._build_oracle_filters(filters)
        
        return await self._make_request(
            method="GET",
            endpoint=endpoint,
            params=params
        )
        
    async def get_products(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get product data from Oracle ERP."""
        await self._refresh_token_if_needed()
        
        endpoint = f"{self.service_root}/resources/11.13.18.05/items"
        params = self._build_oracle_filters(filters)
        
        return await self._make_request(
            method="GET",
            endpoint=endpoint,
            params=params
        )
        
    async def get_suppliers(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get supplier data from Oracle ERP."""
        await self._refresh_token_if_needed()
        
        endpoint = f"{self.service_root}/resources/11.13.18.05/suppliers"
        params = self._build_oracle_filters(filters)
        
        return await self._make_request(
            method="GET",
            endpoint=endpoint,
            params=params
        )
        
    async def get_purchase_orders(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get purchase order data from Oracle ERP."""
        await self._refresh_token_if_needed()
        
        endpoint = f"{self.service_root}/resources/11.13.18.05/purchaseOrders"
        params = self._build_oracle_filters(filters)
        
        return await self._make_request(
            method="GET",
            endpoint=endpoint,
            params=params
        )
        
    async def get_sales_orders(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get sales order data from Oracle ERP."""
        await self._refresh_token_if_needed()
        
        endpoint = f"{self.service_root}/resources/11.13.18.05/salesOrders"
        params = self._build_oracle_filters(filters)
        
        return await self._make_request(
            method="GET",
            endpoint=endpoint,
            params=params
        )
        
    async def get_financial_data(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get financial data from Oracle ERP."""
        await self._refresh_token_if_needed()
        
        endpoint = f"{self.service_root}/resources/11.13.18.05/financialDocuments"
        params = self._build_oracle_filters(filters)
        
        return await self._make_request(
            method="GET",
            endpoint=endpoint,
            params=params
        )
        
    async def get_inventory_data(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get inventory data from Oracle ERP."""
        await self._refresh_token_if_needed()
        
        endpoint = f"{self.service_root}/resources/11.13.18.05/inventoryItems"
        params = self._build_oracle_filters(filters)
        
        return await self._make_request(
            method="GET",
            endpoint=endpoint,
            params=params
        )
        
    async def get_warehouse_data(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get warehouse data from Oracle ERP."""
        await self._refresh_token_if_needed()
        
        endpoint = f"{self.service_root}/resources/11.13.18.05/warehouses"
        params = self._build_oracle_filters(filters)
        
        return await self._make_request(
            method="GET",
            endpoint=endpoint,
            params=params
        )
        
    async def get_production_data(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get production data from Oracle ERP."""
        await self._refresh_token_if_needed()
        
        endpoint = f"{self.service_root}/resources/11.13.18.05/productionOrders"
        params = self._build_oracle_filters(filters)
        
        return await self._make_request(
            method="GET",
            endpoint=endpoint,
            params=params
        )
        
    def _build_oracle_filters(self, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Build Oracle ERP specific filter parameters."""
        if not filters:
            return {}
            
        oracle_params = {}
        
        # Map common filters to Oracle parameters
        if "date_from" in filters:
            oracle_params["q"] = f"CreationDate >= '{filters['date_from']}'"
        if "date_to" in filters:
            if "q" in oracle_params:
                oracle_params["q"] += f" and CreationDate <= '{filters['date_to']}'"
            else:
                oracle_params["q"] = f"CreationDate <= '{filters['date_to']}'"
                
        if "status" in filters:
            if "q" in oracle_params:
                oracle_params["q"] += f" and Status = '{filters['status']}'"
            else:
                oracle_params["q"] = f"Status = '{filters['status']}'"
                
        if "limit" in filters:
            oracle_params["limit"] = filters["limit"]
            
        if "offset" in filters:
            oracle_params["offset"] = filters["offset"]
            
        # Add Oracle-specific parameters
        if "business_unit" in filters:
            oracle_params["businessUnit"] = filters["business_unit"]
        if "legal_entity" in filters:
            oracle_params["legalEntity"] = filters["legal_entity"]
            
        return oracle_params
        
    def _get_default_headers(self) -> Dict[str, str]:
        """Get Oracle ERP specific headers."""
        headers = super()._get_default_headers()
        
        # Add Oracle-specific headers
        headers.update({
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/vnd.oracle.adf.resourceitem+json",
            "Accept-Language": "en-US"
        })
        
        return headers
