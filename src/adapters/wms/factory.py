"""
WMS Adapter Factory - Creates and manages WMS adapter instances.
"""
from typing import Dict, Any, Optional, Type
from .base import BaseWMSAdapter
from .sap_ewm import SAPEWMAdapter
from .manhattan import ManhattanAdapter
from .oracle import OracleWMSAdapter
import logging

logger = logging.getLogger(__name__)

class WMSAdapterFactory:
    """
    Factory class for creating and managing WMS adapter instances.
    
    Supports multiple WMS systems and provides a unified interface
    for adapter creation and management.
    """
    
    # Registry of available WMS adapters
    _adapters: Dict[str, Type[BaseWMSAdapter]] = {
        'sap_ewm': SAPEWMAdapter,
        'manhattan': ManhattanAdapter,
        'oracle': OracleWMSAdapter
    }
    
    # Active adapter instances
    _instances: Dict[str, BaseWMSAdapter] = {}
    
    @classmethod
    def register_adapter(cls, name: str, adapter_class: Type[BaseWMSAdapter]):
        """
        Register a new WMS adapter type.
        
        Args:
            name: Adapter name/identifier
            adapter_class: Adapter class to register
        """
        cls._adapters[name] = adapter_class
        logger.info(f"Registered WMS adapter: {name}")
    
    @classmethod
    def create_adapter(cls, wms_type: str, config: Dict[str, Any], 
                      instance_id: Optional[str] = None) -> BaseWMSAdapter:
        """
        Create a new WMS adapter instance.
        
        Args:
            wms_type: Type of WMS system (sap_ewm, manhattan, oracle)
            config: Configuration for the adapter
            instance_id: Optional instance identifier for reuse
            
        Returns:
            BaseWMSAdapter: Configured adapter instance
            
        Raises:
            ValueError: If WMS type is not supported
        """
        if wms_type not in cls._adapters:
            available_types = list(cls._adapters.keys())
            raise ValueError(f"Unsupported WMS type: {wms_type}. Available types: {available_types}")
        
        # Use instance_id for caching if provided
        if instance_id:
            cache_key = f"{wms_type}_{instance_id}"
            if cache_key in cls._instances:
                logger.info(f"Reusing existing WMS adapter instance: {cache_key}")
                return cls._instances[cache_key]
        
        # Create new adapter instance
        adapter_class = cls._adapters[wms_type]
        adapter = adapter_class(config)
        
        # Cache instance if instance_id provided
        if instance_id:
            cache_key = f"{wms_type}_{instance_id}"
            cls._instances[cache_key] = adapter
            logger.info(f"Cached new WMS adapter instance: {cache_key}")
        
        logger.info(f"Created WMS adapter: {wms_type}")
        return adapter
    
    @classmethod
    def get_adapter(cls, wms_type: str, instance_id: str) -> Optional[BaseWMSAdapter]:
        """
        Get an existing adapter instance.
        
        Args:
            wms_type: Type of WMS system
            instance_id: Instance identifier
            
        Returns:
            BaseWMSAdapter or None: Cached adapter instance
        """
        cache_key = f"{wms_type}_{instance_id}"
        return cls._instances.get(cache_key)
    
    @classmethod
    def remove_adapter(cls, wms_type: str, instance_id: str) -> bool:
        """
        Remove and disconnect an adapter instance.
        
        Args:
            wms_type: Type of WMS system
            instance_id: Instance identifier
            
        Returns:
            bool: True if removed successfully
        """
        cache_key = f"{wms_type}_{instance_id}"
        if cache_key in cls._instances:
            adapter = cls._instances[cache_key]
            try:
                # Disconnect the adapter
                import asyncio
                if asyncio.iscoroutinefunction(adapter.disconnect):
                    asyncio.create_task(adapter.disconnect())
                else:
                    adapter.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting adapter {cache_key}: {e}")
            
            del cls._instances[cache_key]
            logger.info(f"Removed WMS adapter instance: {cache_key}")
            return True
        
        return False
    
    @classmethod
    def list_adapters(cls) -> Dict[str, Type[BaseWMSAdapter]]:
        """
        List all registered adapter types.
        
        Returns:
            Dict[str, Type[BaseWMSAdapter]]: Registered adapters
        """
        return cls._adapters.copy()
    
    @classmethod
    def list_instances(cls) -> Dict[str, BaseWMSAdapter]:
        """
        List all active adapter instances.
        
        Returns:
            Dict[str, BaseWMSAdapter]: Active instances
        """
        return cls._instances.copy()
    
    @classmethod
    async def health_check_all(cls) -> Dict[str, Dict[str, Any]]:
        """
        Perform health check on all active adapter instances.
        
        Returns:
            Dict[str, Dict[str, Any]]: Health check results for each instance
        """
        results = {}
        
        for instance_key, adapter in cls._instances.items():
            try:
                health_result = await adapter.health_check()
                results[instance_key] = health_result
            except Exception as e:
                results[instance_key] = {
                    "status": "error",
                    "connected": False,
                    "error": str(e),
                    "timestamp": None
                }
        
        return results
    
    @classmethod
    async def disconnect_all(cls) -> Dict[str, bool]:
        """
        Disconnect all active adapter instances.
        
        Returns:
            Dict[str, bool]: Disconnection results for each instance
        """
        results = {}
        
        for instance_key, adapter in cls._instances.items():
            try:
                success = await adapter.disconnect()
                results[instance_key] = success
            except Exception as e:
                logger.error(f"Error disconnecting adapter {instance_key}: {e}")
                results[instance_key] = False
        
        # Clear all instances
        cls._instances.clear()
        
        return results

# Convenience functions for common operations
def create_sap_ewm_adapter(config: Dict[str, Any], instance_id: Optional[str] = None) -> SAPEWMAdapter:
    """Create a SAP EWM adapter instance."""
    return WMSAdapterFactory.create_adapter('sap_ewm', config, instance_id)

def create_manhattan_adapter(config: Dict[str, Any], instance_id: Optional[str] = None) -> ManhattanAdapter:
    """Create a Manhattan WMS adapter instance."""
    return WMSAdapterFactory.create_adapter('manhattan', config, instance_id)

def create_oracle_adapter(config: Dict[str, Any], instance_id: Optional[str] = None) -> OracleWMSAdapter:
    """Create an Oracle WMS adapter instance."""
    return WMSAdapterFactory.create_adapter('oracle', config, instance_id)
