"""
Scanning Integration Service

This module provides the main service for managing RFID and barcode scanning devices.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import asyncio

from src.adapters.rfid_barcode import ScanningAdapterFactory, ScanningConfig
from src.adapters.rfid_barcode.base import BaseScanningAdapter, ScanResult, ScanEvent

logger = logging.getLogger(__name__)


class ScanningIntegrationService:
    """
    Service for managing RFID and barcode scanning devices.

    Provides a unified interface for interacting with multiple scanning devices
    including Zebra RFID, Honeywell barcode, and generic scanners.
    """

    def __init__(self):
        self.devices: Dict[str, BaseScanningAdapter] = {}
        self._initialized = False

    async def initialize(self):
        """Initialize the scanning integration service."""
        if not self._initialized:
            # Load scanning devices from configuration
            await self._load_devices()
            self._initialized = True
            logger.info("Scanning Integration Service initialized")

    async def _load_devices(self):
        """Load scanning devices from configuration."""
        # This would typically load from a configuration file or database
        # For now, we'll use placeholder devices
        devices_config = [
            {
                "id": "zebra_rfid_1",
                "device_type": "zebra_rfid",
                "connection_string": "tcp://192.168.1.100:8080",
                "timeout": 30,
            },
            {
                "id": "honeywell_barcode_1",
                "device_type": "honeywell_barcode",
                "connection_string": "tcp://192.168.1.101:8080",
                "timeout": 30,
            },
        ]

        for config in devices_config:
            device_id = config.pop("id")  # Remove id from config
            scanning_config = ScanningConfig(**config)
            adapter = ScanningAdapterFactory.create_adapter(scanning_config)

            if adapter:
                self.devices[device_id] = adapter
                logger.info(f"Loaded scanning device: {device_id}")

    async def get_device(self, device_id: str) -> Optional[BaseScanningAdapter]:
        """Get scanning device by ID."""
        await self.initialize()
        return self.devices.get(device_id)

    async def add_device(self, device_id: str, config: ScanningConfig) -> bool:
        """Add a new scanning device."""
        await self.initialize()

        adapter = ScanningAdapterFactory.create_adapter(config)
        if adapter:
            self.devices[device_id] = adapter
            logger.info(f"Added scanning device: {device_id}")
            return True
        return False

    async def remove_device(self, device_id: str) -> bool:
        """Remove a scanning device."""
        if device_id in self.devices:
            adapter = self.devices[device_id]
            await adapter.disconnect()
            del self.devices[device_id]
            logger.info(f"Removed scanning device: {device_id}")
            return True
        return False

    async def connect_device(self, device_id: str) -> bool:
        """Connect to a scanning device."""
        device = await self.get_device(device_id)
        if not device:
            return False

        try:
            return await device.connect()
        except Exception as e:
            logger.error(f"Failed to connect device {device_id}: {e}")
            return False

    async def disconnect_device(self, device_id: str) -> bool:
        """Disconnect from a scanning device."""
        device = await self.get_device(device_id)
        if not device:
            return False

        try:
            return await device.disconnect()
        except Exception as e:
            logger.error(f"Failed to disconnect device {device_id}: {e}")
            return False

    async def start_scanning(self, device_id: str) -> bool:
        """Start scanning on a device."""
        device = await self.get_device(device_id)
        if not device:
            return False

        try:
            return await device.start_scanning()
        except Exception as e:
            logger.error(f"Failed to start scanning on device {device_id}: {e}")
            return False

    async def stop_scanning(self, device_id: str) -> bool:
        """Stop scanning on a device."""
        device = await self.get_device(device_id)
        if not device:
            return False

        try:
            return await device.stop_scanning()
        except Exception as e:
            logger.error(f"Failed to stop scanning on device {device_id}: {e}")
            return False

    async def single_scan(
        self, device_id: str, timeout: Optional[int] = None
    ) -> Optional[ScanResult]:
        """Perform a single scan on a device."""
        device = await self.get_device(device_id)
        if not device:
            return None

        try:
            return await device.single_scan(timeout)
        except Exception as e:
            logger.error(f"Failed to perform single scan on device {device_id}: {e}")
            return None

    async def get_device_info(self, device_id: str) -> Dict[str, Any]:
        """Get device information."""
        device = await self.get_device(device_id)
        if not device:
            return {"error": "Device not found"}

        try:
            return await device.get_device_info()
        except Exception as e:
            logger.error(f"Failed to get device info for {device_id}: {e}")
            return {"error": str(e)}

    async def get_device_status(self, device_id: str) -> Dict[str, Any]:
        """Get device status."""
        device = await self.get_device(device_id)
        if not device:
            return {
                "connected": False,
                "scanning": False,
                "error": f"Device not found: {device_id}",
            }

        return {
            "connected": device.is_connected(),
            "scanning": device.is_scanning(),
            "device_type": device.config.device_type,
            "connection_string": device.config.connection_string,
        }

    async def get_all_devices_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all scanning devices."""
        status = {}
        for device_id in self.devices.keys():
            status[device_id] = await self.get_device_status(device_id)
        return status

    async def close_all_devices(self):
        """Close all scanning devices."""
        for adapter in self.devices.values():
            try:
                await adapter.disconnect()
            except Exception as e:
                logger.error(f"Error closing scanning device: {e}")
        self.devices.clear()
        logger.info("All scanning devices closed")


# Global instance
scanning_service = ScanningIntegrationService()


async def get_scanning_service() -> ScanningIntegrationService:
    """Get the global scanning integration service instance."""
    return scanning_service
