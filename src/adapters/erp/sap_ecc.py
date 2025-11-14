"""
SAP ECC ERP Adapter

This module provides integration with SAP ECC (Enterprise Central Component)
ERP system using RFC and REST API interfaces.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import base64
import json

from .base import BaseERPAdapter, ERPConnection, ERPResponse

logger = logging.getLogger(__name__)

class SAPECCAdapter(BaseERPAdapter):
    """
    SAP ECC ERP adapter implementation.
    
    Supports both RFC and REST API integration with SAP ECC systems.
    """
    
    def __init__(self, connection: ERPConnection):
        super().__init__(connection)
        self.rfc_connection = None
        self.api_version = "v1"
        
    def requires_authentication(self) -> bool:
        """SAP ECC requires authentication."""
        return True
        
    async def authenticate(self) -> bool:
        """Authenticate with SAP ECC using OAuth2 or Basic Auth."""
        try:
            if self.connection.api_key:
                # API Key authentication
                self._auth_token = self.connection.api_key
                self._token_expires = datetime.utcnow() + timedelta(hours=24)
                return True
            else:
                # OAuth2 authentication
                auth_data = {
                    "grant_type": "client_credentials",
                    "client_id": self.connection.client_id,
                    "client_secret": self.connection.client_secret
                }
                
                response = await self._make_request(
                    method="POST",
                    endpoint="/oauth/token",
                    data=auth_data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                
                if response.success and response.data:
                    self._auth_token = response.data.get("access_token")
                    expires_in = response.data.get("expires_in", 3600)
                    self._token_expires = datetime.utcnow() + timedelta(seconds=expires_in)
                    return True
                    
        except Exception as e:
            logger.error(f"SAP ECC authentication failed: {e}")
            
        return False
        
    async def get_employees(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get employee data from SAP ECC."""
        await self._refresh_token_if_needed()
        
        endpoint = f"/api/{self.api_version}/employees"
        params = self._build_sap_filters(filters)
        
        return await self._make_request(
            method="GET",
            endpoint=endpoint,
            params=params
        )
        
    async def get_products(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get product data from SAP ECC."""
        await self._refresh_token_if_needed()
        
        endpoint = f"/api/{self.api_version}/materials"
        params = self._build_sap_filters(filters)
        
        return await self._make_request(
            method="GET",
            endpoint=endpoint,
            params=params
        )
        
    async def get_suppliers(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get supplier data from SAP ECC."""
        await self._refresh_token_if_needed()
        
        endpoint = f"/api/{self.api_version}/vendors"
        params = self._build_sap_filters(filters)
        
        return await self._make_request(
            method="GET",
            endpoint=endpoint,
            params=params
        )
        
    async def get_purchase_orders(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get purchase order data from SAP ECC."""
        await self._refresh_token_if_needed()
        
        endpoint = f"/api/{self.api_version}/purchase-orders"
        params = self._build_sap_filters(filters)
        
        return await self._make_request(
            method="GET",
            endpoint=endpoint,
            params=params
        )
        
    async def get_sales_orders(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get sales order data from SAP ECC."""
        await self._refresh_token_if_needed()
        
        endpoint = f"/api/{self.api_version}/sales-orders"
        params = self._build_sap_filters(filters)
        
        return await self._make_request(
            method="GET",
            endpoint=endpoint,
            params=params
        )
        
    async def get_financial_data(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get financial data from SAP ECC."""
        await self._refresh_token_if_needed()
        
        endpoint = f"/api/{self.api_version}/financial-documents"
        params = self._build_sap_filters(filters)
        
        return await self._make_request(
            method="GET",
            endpoint=endpoint,
            params=params
        )
        
    async def get_warehouse_data(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get warehouse-specific data from SAP ECC."""
        await self._refresh_token_if_needed()
        
        endpoint = f"/api/{self.api_version}/warehouse-data"
        params = self._build_sap_filters(filters)
        
        return await self._make_request(
            method="GET",
            endpoint=endpoint,
            params=params
        )
        
    async def get_inventory_levels(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get inventory levels from SAP ECC."""
        await self._refresh_token_if_needed()
        
        endpoint = f"/api/{self.api_version}/inventory-levels"
        params = self._build_sap_filters(filters)
        
        return await self._make_request(
            method="GET",
            endpoint=endpoint,
            params=params
        )
        
    async def get_production_orders(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get production order data from SAP ECC."""
        await self._refresh_token_if_needed()
        
        endpoint = f"/api/{self.api_version}/production-orders"
        params = self._build_sap_filters(filters)
        
        return await self._make_request(
            method="GET",
            endpoint=endpoint,
            params=params
        )
        
    def _build_sap_filters(self, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Build SAP-specific filter parameters."""
        if not filters:
            return {}
            
        sap_params = {}
        
        # Map common filters to SAP parameters
        if "date_from" in filters:
            sap_params["$filter"] = f"Date ge {filters['date_from']}"
        if "date_to" in filters:
            if "$filter" in sap_params:
                sap_params["$filter"] += f" and Date le {filters['date_to']}"
            else:
                sap_params["$filter"] = f"Date le {filters['date_to']}"
                
        if "status" in filters:
            if "$filter" in sap_params:
                sap_params["$filter"] += f" and Status eq '{filters['status']}'"
            else:
                sap_params["$filter"] = f"Status eq '{filters['status']}'"
                
        if "limit" in filters:
            sap_params["$top"] = filters["limit"]
            
        if "offset" in filters:
            sap_params["$skip"] = filters["offset"]
            
        # Add custom SAP parameters
        if "plant" in filters:
            sap_params["Plant"] = filters["plant"]
        if "company_code" in filters:
            sap_params["CompanyCode"] = filters["company_code"]
            
        return sap_params
        
    def _get_default_headers(self) -> Dict[str, str]:
        """Get SAP ECC specific headers."""
        headers = super()._get_default_headers()
        
        # Add SAP-specific headers
        headers.update({
            "X-SAP-Client": self.connection.client_id or "100",
            "X-SAP-Service": "ERP",
            "Accept-Language": "en-US"
        })
        
        return headers
