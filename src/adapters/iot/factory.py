"""
IoT Adapter Factory - Creates and manages IoT adapter instances.
"""
from typing import Dict, Any, Optional, Type
from .base import BaseIoTAdapter
from .equipment_monitor import EquipmentMonitorAdapter
from .environmental import EnvironmentalSensorAdapter
from .safety_sensors import SafetySensorAdapter
from .asset_tracking import AssetTrackingAdapter
import logging

logger = logging.getLogger(__name__)

class IoTAdapterFactory:
    """
    Factory class for creating and managing IoT adapter instances.
    
    Supports multiple IoT systems and provides a unified interface
    for adapter creation and management.
    """
    
    # Registry of available IoT adapters
    _adapters: Dict[str, Type[BaseIoTAdapter]] = {
        'equipment_monitor': EquipmentMonitorAdapter,
        'environmental': EnvironmentalSensorAdapter,
        'safety_sensors': SafetySensorAdapter,
        'asset_tracking': AssetTrackingAdapter
    }
    
    # Active adapter instances
    _instances: Dict[str, BaseIoTAdapter] = {}
    
    @classmethod
    def register_adapter(cls, name: str, adapter_class: Type[BaseIoTAdapter]):
        """
        Register a new IoT adapter type.
        
        Args:
            name: Adapter name/identifier
            adapter_class: Adapter class to register
        """
        cls._adapters[name] = adapter_class
        logger.info(f"Registered IoT adapter: {name}")
    
    @classmethod
    def create_adapter(cls, iot_type: str, config: Dict[str, Any], 
                      instance_id: Optional[str] = None) -> BaseIoTAdapter:
        """
        Create a new IoT adapter instance.
        
        Args:
            iot_type: Type of IoT system (equipment_monitor, environmental, safety_sensors, asset_tracking)
            config: Configuration for the adapter
            instance_id: Optional instance identifier for reuse
            
        Returns:
            BaseIoTAdapter: Configured adapter instance
            
        Raises:
            ValueError: If IoT type is not supported
        """
        if iot_type not in cls._adapters:
            available_types = list(cls._adapters.keys())
            raise ValueError(f"Unsupported IoT type: {iot_type}. Available types: {available_types}")
        
        # Use instance_id for caching if provided
        if instance_id:
            cache_key = f"{iot_type}_{instance_id}"
            if cache_key in cls._instances:
                logger.info(f"Reusing existing IoT adapter instance: {cache_key}")
                return cls._instances[cache_key]
        
        # Create new adapter instance
        adapter_class = cls._adapters[iot_type]
        adapter = adapter_class(config)
        
        # Cache instance if instance_id provided
        if instance_id:
            cache_key = f"{iot_type}_{instance_id}"
            cls._instances[cache_key] = adapter
            logger.info(f"Cached new IoT adapter instance: {cache_key}")
        
        logger.info(f"Created IoT adapter: {iot_type}")
        return adapter
    
    @classmethod
    def get_adapter(cls, iot_type: str, instance_id: str) -> Optional[BaseIoTAdapter]:
        """
        Get an existing adapter instance.
        
        Args:
            iot_type: Type of IoT system
            instance_id: Instance identifier
            
        Returns:
            BaseIoTAdapter or None: Cached adapter instance
        """
        cache_key = f"{iot_type}_{instance_id}"
        return cls._instances.get(cache_key)
    
    @classmethod
    def remove_adapter(cls, iot_type: str, instance_id: str) -> bool:
        """
        Remove and disconnect an adapter instance.
        
        Args:
            iot_type: Type of IoT system
            instance_id: Instance identifier
            
        Returns:
            bool: True if removed successfully
        """
        cache_key = f"{iot_type}_{instance_id}"
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
            logger.info(f"Removed IoT adapter instance: {cache_key}")
            return True
        
        return False
    
    @classmethod
    def list_adapters(cls) -> Dict[str, Type[BaseIoTAdapter]]:
        """
        List all registered adapter types.
        
        Returns:
            Dict[str, Type[BaseIoTAdapter]]: Registered adapters
        """
        return cls._adapters.copy()
    
    @classmethod
    def list_instances(cls) -> Dict[str, BaseIoTAdapter]:
        """
        List all active adapter instances.
        
        Returns:
            Dict[str, BaseIoTAdapter]: Active instances
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
def create_equipment_monitor_adapter(config: Dict[str, Any], instance_id: Optional[str] = None) -> EquipmentMonitorAdapter:
    """Create an equipment monitor adapter instance."""
    return IoTAdapterFactory.create_adapter('equipment_monitor', config, instance_id)

def create_environmental_adapter(config: Dict[str, Any], instance_id: Optional[str] = None) -> EnvironmentalSensorAdapter:
    """Create an environmental sensor adapter instance."""
    return IoTAdapterFactory.create_adapter('environmental', config, instance_id)

def create_safety_sensor_adapter(config: Dict[str, Any], instance_id: Optional[str] = None) -> SafetySensorAdapter:
    """Create a safety sensor adapter instance."""
    return IoTAdapterFactory.create_adapter('safety_sensors', config, instance_id)

def create_asset_tracking_adapter(config: Dict[str, Any], instance_id: Optional[str] = None) -> AssetTrackingAdapter:
    """Create an asset tracking adapter instance."""
    return IoTAdapterFactory.create_adapter('asset_tracking', config, instance_id)
