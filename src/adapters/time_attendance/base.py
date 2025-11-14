"""
Base Time Attendance Adapter

This module defines the base interface and common functionality
for all time attendance and biometric system adapters.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime, date, time
from enum import Enum
import asyncio
import json

logger = logging.getLogger(__name__)

class AttendanceType(Enum):
    """Types of attendance events."""
    CHECK_IN = "check_in"
    CHECK_OUT = "check_out"
    BREAK_START = "break_start"
    BREAK_END = "break_end"
    LUNCH_START = "lunch_start"
    LUNCH_END = "lunch_end"
    OVERTIME_START = "overtime_start"
    OVERTIME_END = "overtime_end"

class AttendanceStatus(Enum):
    """Status of attendance records."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING_APPROVAL = "pending_approval"

class BiometricType(Enum):
    """Types of biometric data."""
    FINGERPRINT = "fingerprint"
    FACE = "face"
    IRIS = "iris"
    PALM = "palm"
    VOICE = "voice"

@dataclass
class AttendanceRecord:
    """Employee attendance record."""
    record_id: str
    employee_id: str
    attendance_type: AttendanceType
    timestamp: datetime
    location: Optional[str] = None
    device_id: Optional[str] = None
    status: AttendanceStatus = AttendanceStatus.PENDING
    notes: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "record_id": self.record_id,
            "employee_id": self.employee_id,
            "attendance_type": self.attendance_type.value,
            "timestamp": self.timestamp.isoformat(),
            "location": self.location,
            "device_id": self.device_id,
            "status": self.status.value,
            "notes": self.notes,
            "metadata": self.metadata or {}
        }

@dataclass
class BiometricData:
    """Biometric data for employee identification."""
    employee_id: str
    biometric_type: BiometricType
    template_data: str
    quality_score: Optional[float] = None
    created_at: datetime = None
    metadata: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()

@dataclass
class AttendanceConfig:
    """Configuration for time attendance adapters."""
    device_type: str
    connection_string: str
    timeout: int = 30
    retry_count: int = 3
    auto_connect: bool = True
    sync_interval: int = 300  # 5 minutes
    additional_params: Optional[Dict[str, Any]] = None

class BaseTimeAttendanceAdapter(ABC):
    """
    Base class for all time attendance adapters.
    
    Provides common functionality and defines the interface that all
    time attendance adapters must implement.
    """
    
    def __init__(self, config: AttendanceConfig):
        self.config = config
        self.connected = False
        self.syncing = False
        self._attendance_callbacks: List[Callable[[AttendanceRecord], None]] = []
        self._sync_task: Optional[asyncio.Task] = None
        
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
        
    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the time attendance system."""
        pass
        
    @abstractmethod
    async def disconnect(self) -> bool:
        """Disconnect from the time attendance system."""
        pass
        
    @abstractmethod
    async def get_attendance_records(
        self, 
        employee_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[AttendanceRecord]:
        """Get attendance records from the system."""
        pass
        
    @abstractmethod
    async def create_attendance_record(self, record: AttendanceRecord) -> bool:
        """Create a new attendance record."""
        pass
        
    @abstractmethod
    async def update_attendance_record(self, record: AttendanceRecord) -> bool:
        """Update an existing attendance record."""
        pass
        
    @abstractmethod
    async def delete_attendance_record(self, record_id: str) -> bool:
        """Delete an attendance record."""
        pass
        
    @abstractmethod
    async def get_employee_attendance(
        self, 
        employee_id: str, 
        date: date
    ) -> Dict[str, Any]:
        """Get employee attendance summary for a specific date."""
        pass
        
    @abstractmethod
    async def get_biometric_data(
        self, 
        employee_id: Optional[str] = None
    ) -> List[BiometricData]:
        """Get biometric data from the system."""
        pass
        
    @abstractmethod
    async def enroll_biometric_data(self, biometric_data: BiometricData) -> bool:
        """Enroll new biometric data for an employee."""
        pass
        
    @abstractmethod
    async def verify_biometric(
        self, 
        biometric_type: BiometricType, 
        template_data: str
    ) -> Optional[str]:
        """Verify biometric data and return employee ID if match found."""
        pass
        
    async def start_sync(self) -> bool:
        """Start automatic synchronization with the system."""
        if not self.connected:
            logger.error("Not connected to time attendance system")
            return False
            
        try:
            self.syncing = True
            
            # Start sync task
            if not self._sync_task or self._sync_task.done():
                self._sync_task = asyncio.create_task(self._sync_loop())
                
            logger.info("Started time attendance synchronization")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start synchronization: {e}")
            return False
            
    async def stop_sync(self) -> bool:
        """Stop automatic synchronization."""
        try:
            self.syncing = False
            
            # Cancel sync task
            if self._sync_task and not self._sync_task.done():
                self._sync_task.cancel()
                
            logger.info("Stopped time attendance synchronization")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop synchronization: {e}")
            return False
            
    async def _sync_loop(self):
        """Background synchronization loop."""
        while self.syncing:
            try:
                # Sync attendance records
                await self._sync_attendance_records()
                
                # Wait for next sync interval
                await asyncio.sleep(self.config.sync_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in sync loop: {e}")
                await asyncio.sleep(60)  # Wait 1 minute before retry
                
    async def _sync_attendance_records(self):
        """Sync attendance records from the system."""
        try:
            # Get recent attendance records
            end_date = date.today()
            start_date = end_date  # Sync today's records
            
            records = await self.get_attendance_records(
                start_date=start_date,
                end_date=end_date
            )
            
            # Notify callbacks of new records
            for record in records:
                await self._notify_attendance_record(record)
                
        except Exception as e:
            logger.error(f"Error syncing attendance records: {e}")
            
    def add_attendance_callback(self, callback: Callable[[AttendanceRecord], None]):
        """Add callback for attendance records."""
        self._attendance_callbacks.append(callback)
        
    def remove_attendance_callback(self, callback: Callable[[AttendanceRecord], None]):
        """Remove attendance callback."""
        if callback in self._attendance_callbacks:
            self._attendance_callbacks.remove(callback)
            
    async def _notify_attendance_record(self, record: AttendanceRecord):
        """Notify all callbacks of a new attendance record."""
        for callback in self._attendance_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(record)
                else:
                    callback(record)
            except Exception as e:
                logger.error(f"Error in attendance callback: {e}")
                
    def _generate_record_id(self) -> str:
        """Generate unique record ID."""
        return f"att_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}"
        
    def is_connected(self) -> bool:
        """Check if adapter is connected."""
        return self.connected
        
    def is_syncing(self) -> bool:
        """Check if adapter is currently syncing."""
        return self.syncing
