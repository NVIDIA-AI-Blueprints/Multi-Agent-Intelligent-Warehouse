"""
RFID/Barcode Scanning Adapter Factory

This module provides a factory for creating scanning adapters based on device type.
"""

import logging
from typing import Dict, Type, Optional
from .base import BaseScanningAdapter, ScanningConfig
from .zebra_rfid import ZebraRFIDAdapter
from .honeywell_barcode import HoneywellBarcodeAdapter
from .generic_scanner import GenericScannerAdapter

logger = logging.getLogger(__name__)

class ScanningAdapterFactory:
    """Factory for creating RFID and barcode scanning adapters."""
    
    _adapters: Dict[str, Type[BaseScanningAdapter]] = {
        "zebra_rfid": ZebraRFIDAdapter,
        "honeywell_barcode": HoneywellBarcodeAdapter,
        "generic_scanner": GenericScannerAdapter,
    }
    
    @classmethod
    def create_adapter(cls, config: ScanningConfig) -> Optional[BaseScanningAdapter]:
        """
        Create a scanning adapter based on the configuration.
        
        Args:
            config: Scanning device configuration
            
        Returns:
            Scanning adapter instance or None if device type not supported
        """
        device_type = config.device_type.lower()
        
        if device_type not in cls._adapters:
            logger.error(f"Unsupported scanning device type: {device_type}")
            return None
            
        adapter_class = cls._adapters[device_type]
        
        try:
            return adapter_class(config)
        except Exception as e:
            logger.error(f"Failed to create {device_type} adapter: {e}")
            return None
            
    @classmethod
    def get_supported_devices(cls) -> list:
        """Get list of supported scanning devices."""
        return list(cls._adapters.keys())
        
    @classmethod
    def register_adapter(cls, device_type: str, adapter_class: Type[BaseScanningAdapter]):
        """
        Register a new scanning adapter.
        
        Args:
            device_type: Device type identifier
            adapter_class: Adapter class to register
        """
        cls._adapters[device_type.lower()] = adapter_class
        logger.info(f"Registered scanning adapter for {device_type}")
        
    @classmethod
    def create_zebra_rfid_adapter(
        cls,
        connection_string: str,
        timeout: int = 30,
        **kwargs
    ) -> Optional[ZebraRFIDAdapter]:
        """Create Zebra RFID adapter with common parameters."""
        config = ScanningConfig(
            device_type="zebra_rfid",
            connection_string=connection_string,
            timeout=timeout,
            **kwargs
        )
        
        adapter = cls.create_adapter(config)
        return adapter if isinstance(adapter, ZebraRFIDAdapter) else None
        
    @classmethod
    def create_honeywell_barcode_adapter(
        cls,
        connection_string: str,
        timeout: int = 30,
        **kwargs
    ) -> Optional[HoneywellBarcodeAdapter]:
        """Create Honeywell barcode adapter with common parameters."""
        config = ScanningConfig(
            device_type="honeywell_barcode",
            connection_string=connection_string,
            timeout=timeout,
            **kwargs
        )
        
        adapter = cls.create_adapter(config)
        return adapter if isinstance(adapter, HoneywellBarcodeAdapter) else None
        
    @classmethod
    def create_generic_scanner_adapter(
        cls,
        device_type: str,
        connection_string: str,
        protocol: str = "generic",
        timeout: int = 30,
        **kwargs
    ) -> Optional[GenericScannerAdapter]:
        """Create generic scanner adapter with common parameters."""
        additional_params = kwargs.get("additional_params", {})
        additional_params["protocol"] = protocol
        
        config = ScanningConfig(
            device_type=device_type,
            connection_string=connection_string,
            timeout=timeout,
            additional_params=additional_params,
            **kwargs
        )
        
        adapter = cls.create_adapter(config)
        return adapter if isinstance(adapter, GenericScannerAdapter) else None
