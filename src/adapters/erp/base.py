"""
Base ERP Adapter

This module defines the base interface and common functionality
for all ERP system adapters.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass
from datetime import datetime
import asyncio
import aiohttp

logger = logging.getLogger(__name__)

@dataclass
class ERPConnection:
    """ERP connection configuration."""
    system_type: str
    base_url: str
    username: str
    password: str
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    api_key: Optional[str] = None
    timeout: int = 30
    verify_ssl: bool = True
    additional_params: Optional[Dict[str, Any]] = None

@dataclass
class ERPResponse:
    """Standardized ERP response."""
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    status_code: Optional[int] = None
    response_time: Optional[float] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()

class BaseERPAdapter(ABC):
    """
    Base class for all ERP adapters.
    
    Provides common functionality and defines the interface that all
    ERP adapters must implement.
    """
    
    def __init__(self, connection: ERPConnection):
        self.connection = connection
        self.session: Optional[aiohttp.ClientSession] = None
        self._auth_token: Optional[str] = None
        self._token_expires: Optional[datetime] = None
        
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
        
    async def connect(self) -> bool:
        """Establish connection to ERP system."""
        try:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.connection.timeout),
                connector=aiohttp.TCPConnector(ssl=self.connection.verify_ssl)
            )
            
            # Authenticate if required
            if self.requires_authentication():
                await self.authenticate()
                
            logger.info(f"Connected to {self.connection.system_type} ERP system")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to ERP system: {e}")
            return False
            
    async def disconnect(self):
        """Close connection to ERP system."""
        if self.session:
            await self.session.close()
            self.session = None
        self._auth_token = None
        self._token_expires = None
        logger.info(f"Disconnected from {self.connection.system_type} ERP system")
        
    @abstractmethod
    def requires_authentication(self) -> bool:
        """Check if this ERP system requires authentication."""
        pass
        
    @abstractmethod
    async def authenticate(self) -> bool:
        """Authenticate with the ERP system."""
        pass
        
    @abstractmethod
    async def get_employees(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get employee data from ERP system."""
        pass
        
    @abstractmethod
    async def get_products(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get product data from ERP system."""
        pass
        
    @abstractmethod
    async def get_suppliers(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get supplier data from ERP system."""
        pass
        
    @abstractmethod
    async def get_purchase_orders(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get purchase order data from ERP system."""
        pass
        
    @abstractmethod
    async def get_sales_orders(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get sales order data from ERP system."""
        pass
        
    @abstractmethod
    async def get_financial_data(self, filters: Optional[Dict[str, Any]] = None) -> ERPResponse:
        """Get financial data from ERP system."""
        pass
        
    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> ERPResponse:
        """Make HTTP request to ERP system."""
        if not self.session:
            return ERPResponse(
                success=False,
                error="Not connected to ERP system"
            )
            
        start_time = datetime.utcnow()
        
        try:
            # Prepare headers
            request_headers = self._get_default_headers()
            if headers:
                request_headers.update(headers)
                
            # Prepare URL
            url = f"{self.connection.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
            
            # Make request
            async with self.session.request(
                method=method,
                url=url,
                json=data,
                params=params,
                headers=request_headers
            ) as response:
                
                response_time = (datetime.utcnow() - start_time).total_seconds()
                
                # Parse response
                try:
                    response_data = await response.json()
                except:
                    response_data = {"raw_response": await response.text()}
                
                return ERPResponse(
                    success=response.status < 400,
                    data=response_data,
                    error=None if response.status < 400 else f"HTTP {response.status}",
                    status_code=response.status,
                    response_time=response_time
                )
                
        except asyncio.TimeoutError:
            return ERPResponse(
                success=False,
                error="Request timeout",
                response_time=(datetime.utcnow() - start_time).total_seconds()
            )
        except Exception as e:
            return ERPResponse(
                success=False,
                error=str(e),
                response_time=(datetime.utcnow() - start_time).total_seconds()
            )
            
    def _get_default_headers(self) -> Dict[str, str]:
        """Get default headers for requests."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
            
        return headers
        
    def _is_token_expired(self) -> bool:
        """Check if authentication token is expired."""
        if not self._token_expires:
            return True
        return datetime.utcnow() >= self._token_expires
        
    async def _refresh_token_if_needed(self) -> bool:
        """Refresh authentication token if needed."""
        if self.requires_authentication() and self._is_token_expired():
            return await self.authenticate()
        return True
