"""
ERP Adapter Factory

This module provides a factory for creating ERP adapters based on system type.
"""

import logging
from typing import Dict, Type, Optional
from .base import BaseERPAdapter, ERPConnection
from .sap_ecc import SAPECCAdapter
from .oracle_erp import OracleERPAdapter

logger = logging.getLogger(__name__)

class ERPAdapterFactory:
    """Factory for creating ERP adapters."""
    
    _adapters: Dict[str, Type[BaseERPAdapter]] = {
        "sap_ecc": SAPECCAdapter,
        "oracle_erp": OracleERPAdapter,
    }
    
    @classmethod
    def create_adapter(cls, connection: ERPConnection) -> Optional[BaseERPAdapter]:
        """
        Create an ERP adapter based on the connection configuration.
        
        Args:
            connection: ERP connection configuration
            
        Returns:
            ERP adapter instance or None if system type not supported
        """
        system_type = connection.system_type.lower()
        
        if system_type not in cls._adapters:
            logger.error(f"Unsupported ERP system type: {system_type}")
            return None
            
        adapter_class = cls._adapters[system_type]
        
        try:
            return adapter_class(connection)
        except Exception as e:
            logger.error(f"Failed to create {system_type} adapter: {e}")
            return None
            
    @classmethod
    def get_supported_systems(cls) -> list:
        """Get list of supported ERP systems."""
        return list(cls._adapters.keys())
        
    @classmethod
    def register_adapter(cls, system_type: str, adapter_class: Type[BaseERPAdapter]):
        """
        Register a new ERP adapter.
        
        Args:
            system_type: System type identifier
            adapter_class: Adapter class to register
        """
        cls._adapters[system_type.lower()] = adapter_class
        logger.info(f"Registered ERP adapter for {system_type}")
        
    @classmethod
    def create_sap_ecc_adapter(
        cls,
        base_url: str,
        username: str,
        password: str,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        api_key: Optional[str] = None,
        **kwargs
    ) -> Optional[SAPECCAdapter]:
        """Create SAP ECC adapter with common parameters."""
        connection = ERPConnection(
            system_type="sap_ecc",
            base_url=base_url,
            username=username,
            password=password,
            client_id=client_id,
            client_secret=client_secret,
            api_key=api_key,
            **kwargs
        )
        
        adapter = cls.create_adapter(connection)
        return adapter if isinstance(adapter, SAPECCAdapter) else None
        
    @classmethod
    def create_oracle_erp_adapter(
        cls,
        base_url: str,
        username: str,
        password: str,
        client_id: str,
        client_secret: str,
        **kwargs
    ) -> Optional[OracleERPAdapter]:
        """Create Oracle ERP adapter with common parameters."""
        connection = ERPConnection(
            system_type="oracle_erp",
            base_url=base_url,
            username=username,
            password=password,
            client_id=client_id,
            client_secret=client_secret,
            **kwargs
        )
        
        adapter = cls.create_adapter(connection)
        return adapter if isinstance(adapter, OracleERPAdapter) else None
