"""
Time Attendance Integration Service

This module provides the main service for managing time attendance systems.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, date
import asyncio

from adapters.time_attendance import TimeAttendanceAdapterFactory, AttendanceConfig
from adapters.time_attendance.base import (
    BaseTimeAttendanceAdapter,
    AttendanceRecord,
    BiometricData,
)

logger = logging.getLogger(__name__)


class AttendanceIntegrationService:
    """
    Service for managing time attendance systems.

    Provides a unified interface for interacting with multiple time attendance systems
    including biometric systems, card readers, and mobile apps.
    """

    def __init__(self):
        self.systems: Dict[str, BaseTimeAttendanceAdapter] = {}
        self._initialized = False

    async def initialize(self):
        """Initialize the attendance integration service."""
        if not self._initialized:
            # Load attendance systems from configuration
            await self._load_systems()
            self._initialized = True
            logger.info("Attendance Integration Service initialized")

    async def _load_systems(self):
        """Load attendance systems from configuration."""
        # This would typically load from a configuration file or database
        # For now, we'll use placeholder systems
        systems_config = [
            {
                "id": "biometric_main",
                "device_type": "biometric_system",
                "connection_string": "tcp://192.168.1.200:8080",
                "timeout": 30,
            },
            {
                "id": "card_reader_main",
                "device_type": "card_reader",
                "connection_string": "tcp://192.168.1.201:8080",
                "timeout": 30,
            },
            {
                "id": "mobile_app",
                "device_type": "mobile_app",
                "connection_string": "https://attendance.company.com/api",
                "timeout": 30,
                "additional_params": {"api_key": "mobile_api_key"},
            },
        ]

        for config in systems_config:
            system_id = config.pop("id")  # Remove id from config
            attendance_config = AttendanceConfig(**config)
            adapter = TimeAttendanceAdapterFactory.create_adapter(attendance_config)

            if adapter:
                self.systems[system_id] = adapter
                logger.info(f"Loaded attendance system: {system_id}")

    async def get_system(self, system_id: str) -> Optional[BaseTimeAttendanceAdapter]:
        """Get attendance system by ID."""
        await self.initialize()
        return self.systems.get(system_id)

    async def add_system(self, system_id: str, config: AttendanceConfig) -> bool:
        """Add a new attendance system."""
        await self.initialize()

        adapter = TimeAttendanceAdapterFactory.create_adapter(config)
        if adapter:
            self.systems[system_id] = adapter
            logger.info(f"Added attendance system: {system_id}")
            return True
        return False

    async def remove_system(self, system_id: str) -> bool:
        """Remove an attendance system."""
        if system_id in self.systems:
            adapter = self.systems[system_id]
            await adapter.disconnect()
            del self.systems[system_id]
            logger.info(f"Removed attendance system: {system_id}")
            return True
        return False

    async def get_attendance_records(
        self,
        system_id: str,
        employee_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[AttendanceRecord]:
        """Get attendance records from specified system."""
        system = await self.get_system(system_id)
        if not system:
            return []

        try:
            async with system:
                return await system.get_attendance_records(
                    employee_id, start_date, end_date
                )
        except Exception as e:
            logger.error(f"Failed to get attendance records from {system_id}: {e}")
            return []

    async def create_attendance_record(
        self, system_id: str, record: AttendanceRecord
    ) -> bool:
        """Create a new attendance record."""
        system = await self.get_system(system_id)
        if not system:
            return False

        try:
            async with system:
                return await system.create_attendance_record(record)
        except Exception as e:
            logger.error(f"Failed to create attendance record in {system_id}: {e}")
            return False

    async def update_attendance_record(
        self, system_id: str, record: AttendanceRecord
    ) -> bool:
        """Update an existing attendance record."""
        system = await self.get_system(system_id)
        if not system:
            return False

        try:
            async with system:
                return await system.update_attendance_record(record)
        except Exception as e:
            logger.error(f"Failed to update attendance record in {system_id}: {e}")
            return False

    async def delete_attendance_record(self, system_id: str, record_id: str) -> bool:
        """Delete an attendance record."""
        system = await self.get_system(system_id)
        if not system:
            return False

        try:
            async with system:
                return await system.delete_attendance_record(record_id)
        except Exception as e:
            logger.error(f"Failed to delete attendance record from {system_id}: {e}")
            return False

    async def get_employee_attendance(
        self, system_id: str, employee_id: str, date: date
    ) -> Dict[str, Any]:
        """Get employee attendance summary for a specific date."""
        system = await self.get_system(system_id)
        if not system:
            return {}

        try:
            async with system:
                return await system.get_employee_attendance(employee_id, date)
        except Exception as e:
            logger.error(f"Failed to get employee attendance from {system_id}: {e}")
            return {}

    async def get_biometric_data(
        self, system_id: str, employee_id: Optional[str] = None
    ) -> List[BiometricData]:
        """Get biometric data from specified system."""
        system = await self.get_system(system_id)
        if not system:
            return []

        try:
            async with system:
                return await system.get_biometric_data(employee_id)
        except Exception as e:
            logger.error(f"Failed to get biometric data from {system_id}: {e}")
            return []

    async def enroll_biometric_data(
        self, system_id: str, biometric_data: BiometricData
    ) -> bool:
        """Enroll new biometric data for an employee."""
        system = await self.get_system(system_id)
        if not system:
            return False

        try:
            async with system:
                return await system.enroll_biometric_data(biometric_data)
        except Exception as e:
            logger.error(f"Failed to enroll biometric data in {system_id}: {e}")
            return False

    async def verify_biometric(
        self, system_id: str, biometric_type: str, template_data: str
    ) -> Optional[str]:
        """Verify biometric data and return employee ID if match found."""
        system = await self.get_system(system_id)
        if not system:
            return None

        try:
            async with system:
                from adapters.time_attendance.base import BiometricType

                return await system.verify_biometric(
                    BiometricType(biometric_type), template_data
                )
        except Exception as e:
            logger.error(f"Failed to verify biometric in {system_id}: {e}")
            return None

    async def get_system_status(self, system_id: str) -> Dict[str, Any]:
        """Get status of attendance system."""
        system = await self.get_system(system_id)
        if not system:
            return {
                "connected": False,
                "syncing": False,
                "error": f"System not found: {system_id}",
            }

        return {
            "connected": system.is_connected(),
            "syncing": system.is_syncing(),
            "device_type": system.config.device_type,
            "connection_string": system.config.connection_string,
        }

    async def get_all_systems_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status of all attendance systems."""
        status = {}
        for system_id in self.systems.keys():
            status[system_id] = await self.get_system_status(system_id)
        return status

    async def close_all_systems(self):
        """Close all attendance systems."""
        for adapter in self.systems.values():
            try:
                await adapter.disconnect()
            except Exception as e:
                logger.error(f"Error closing attendance system: {e}")
        self.systems.clear()
        logger.info("All attendance systems closed")


# Global instance
attendance_service = AttendanceIntegrationService()


async def get_attendance_service() -> AttendanceIntegrationService:
    """Get the global attendance integration service instance."""
    return attendance_service
