"""
Time Attendance Adapter Factory

This module provides a factory for creating time attendance adapters based on device type.
"""

import logging
from typing import Dict, Type, Optional
from .base import BaseTimeAttendanceAdapter, AttendanceConfig
from .biometric_system import BiometricSystemAdapter
from .card_reader import CardReaderAdapter
from .mobile_app import MobileAppAdapter

logger = logging.getLogger(__name__)

class TimeAttendanceAdapterFactory:
    """Factory for creating time attendance adapters."""
    
    _adapters: Dict[str, Type[BaseTimeAttendanceAdapter]] = {
        "biometric_system": BiometricSystemAdapter,
        "card_reader": CardReaderAdapter,
        "mobile_app": MobileAppAdapter,
    }
    
    @classmethod
    def create_adapter(cls, config: AttendanceConfig) -> Optional[BaseTimeAttendanceAdapter]:
        """
        Create a time attendance adapter based on the configuration.
        
        Args:
            config: Time attendance device configuration
            
        Returns:
            Time attendance adapter instance or None if device type not supported
        """
        device_type = config.device_type.lower()
        
        if device_type not in cls._adapters:
            logger.error(f"Unsupported time attendance device type: {device_type}")
            return None
            
        adapter_class = cls._adapters[device_type]
        
        try:
            return adapter_class(config)
        except Exception as e:
            logger.error(f"Failed to create {device_type} adapter: {e}")
            return None
            
    @classmethod
    def get_supported_devices(cls) -> list:
        """Get list of supported time attendance devices."""
        return list(cls._adapters.keys())
        
    @classmethod
    def register_adapter(cls, device_type: str, adapter_class: Type[BaseTimeAttendanceAdapter]):
        """
        Register a new time attendance adapter.
        
        Args:
            device_type: Device type identifier
            adapter_class: Adapter class to register
        """
        cls._adapters[device_type.lower()] = adapter_class
        logger.info(f"Registered time attendance adapter for {device_type}")
        
    @classmethod
    def create_biometric_system_adapter(
        cls,
        connection_string: str,
        timeout: int = 30,
        **kwargs
    ) -> Optional[BiometricSystemAdapter]:
        """Create biometric system adapter with common parameters."""
        config = AttendanceConfig(
            device_type="biometric_system",
            connection_string=connection_string,
            timeout=timeout,
            **kwargs
        )
        
        adapter = cls.create_adapter(config)
        return adapter if isinstance(adapter, BiometricSystemAdapter) else None
        
    @classmethod
    def create_card_reader_adapter(
        cls,
        connection_string: str,
        timeout: int = 30,
        **kwargs
    ) -> Optional[CardReaderAdapter]:
        """Create card reader adapter with common parameters."""
        config = AttendanceConfig(
            device_type="card_reader",
            connection_string=connection_string,
            timeout=timeout,
            **kwargs
        )
        
        adapter = cls.create_adapter(config)
        return adapter if isinstance(adapter, CardReaderAdapter) else None
        
    @classmethod
    def create_mobile_app_adapter(
        cls,
        api_base_url: str,
        api_key: Optional[str] = None,
        timeout: int = 30,
        **kwargs
    ) -> Optional[MobileAppAdapter]:
        """Create mobile app adapter with common parameters."""
        additional_params = kwargs.get("additional_params", {})
        additional_params["api_key"] = api_key
        
        config = AttendanceConfig(
            device_type="mobile_app",
            connection_string=api_base_url,
            timeout=timeout,
            additional_params=additional_params,
            **kwargs
        )
        
        adapter = cls.create_adapter(config)
        return adapter if isinstance(adapter, MobileAppAdapter) else None
