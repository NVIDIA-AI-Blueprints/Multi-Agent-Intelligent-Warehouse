"""
Base RFID/Barcode Scanning Adapter

This module defines the base interface and common functionality
for all RFID and barcode scanning adapters.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import asyncio
import json

logger = logging.getLogger(__name__)

class ScanType(Enum):
    """Types of scanning operations."""
    RFID = "rfid"
    BARCODE = "barcode"
    QR_CODE = "qr_code"
    DATA_MATRIX = "data_matrix"
    PDF417 = "pdf417"

class ScanStatus(Enum):
    """Status of scan operations."""
    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"

@dataclass
class ScanResult:
    """Result of a scanning operation."""
    scan_id: str
    scan_type: ScanType
    data: str
    status: ScanStatus
    timestamp: datetime
    device_id: Optional[str] = None
    location: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "scan_id": self.scan_id,
            "scan_type": self.scan_type.value,
            "data": self.data,
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "device_id": self.device_id,
            "location": self.location,
            "metadata": self.metadata or {},
            "error": self.error
        }

@dataclass
class ScanEvent:
    """Event from scanning device."""
    event_type: str
    device_id: str
    data: Optional[Dict[str, Any]] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.utcnow()

@dataclass
class ScanningConfig:
    """Configuration for scanning adapters."""
    device_type: str
    connection_string: str
    timeout: int = 30
    retry_count: int = 3
    scan_interval: float = 0.1
    auto_connect: bool = True
    additional_params: Optional[Dict[str, Any]] = None

class BaseScanningAdapter(ABC):
    """
    Base class for all RFID and barcode scanning adapters.
    
    Provides common functionality and defines the interface that all
    scanning adapters must implement.
    """
    
    def __init__(self, config: ScanningConfig):
        self.config = config
        self.connected = False
        self.scanning = False
        self._scan_callbacks: List[Callable[[ScanResult], None]] = []
        self._event_callbacks: List[Callable[[ScanEvent], None]] = []
        self._scan_queue: asyncio.Queue = asyncio.Queue()
        self._scan_task: Optional[asyncio.Task] = None
        
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
        
    @abstractmethod
    async def connect(self) -> bool:
        """Connect to the scanning device."""
        pass
        
    @abstractmethod
    async def disconnect(self) -> bool:
        """Disconnect from the scanning device."""
        pass
        
    @abstractmethod
    async def start_scanning(self) -> bool:
        """Start continuous scanning."""
        pass
        
    @abstractmethod
    async def stop_scanning(self) -> bool:
        """Stop continuous scanning."""
        pass
        
    @abstractmethod
    async def single_scan(self, timeout: Optional[int] = None) -> Optional[ScanResult]:
        """Perform a single scan operation."""
        pass
        
    @abstractmethod
    async def get_device_info(self) -> Dict[str, Any]:
        """Get information about the scanning device."""
        pass
        
    def add_scan_callback(self, callback: Callable[[ScanResult], None]):
        """Add callback for scan results."""
        self._scan_callbacks.append(callback)
        
    def remove_scan_callback(self, callback: Callable[[ScanResult], None]):
        """Remove scan callback."""
        if callback in self._scan_callbacks:
            self._scan_callbacks.remove(callback)
            
    def add_event_callback(self, callback: Callable[[ScanEvent], None]):
        """Add callback for device events."""
        self._event_callbacks.append(callback)
        
    def remove_event_callback(self, callback: Callable[[ScanEvent], None]):
        """Remove event callback."""
        if callback in self._event_callbacks:
            self._event_callbacks.remove(callback)
            
    async def _notify_scan_result(self, result: ScanResult):
        """Notify all scan callbacks of a new result."""
        for callback in self._scan_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(result)
                else:
                    callback(result)
            except Exception as e:
                logger.error(f"Error in scan callback: {e}")
                
    async def _notify_event(self, event: ScanEvent):
        """Notify all event callbacks of a new event."""
        for callback in self._event_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.error(f"Error in event callback: {e}")
                
    async def _process_scan_queue(self):
        """Process scan queue in background."""
        while self.scanning:
            try:
                # Wait for scan result with timeout
                result = await asyncio.wait_for(
                    self._scan_queue.get(), 
                    timeout=self.config.scan_interval
                )
                
                if result:
                    await self._notify_scan_result(result)
                    
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Error processing scan queue: {e}")
                
    def _generate_scan_id(self) -> str:
        """Generate unique scan ID."""
        return f"scan_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}"
        
    async def _create_scan_result(
        self,
        scan_type: ScanType,
        data: str,
        status: ScanStatus,
        device_id: Optional[str] = None,
        location: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> ScanResult:
        """Create a scan result."""
        return ScanResult(
            scan_id=self._generate_scan_id(),
            scan_type=scan_type,
            data=data,
            status=status,
            timestamp=datetime.utcnow(),
            device_id=device_id or self.config.device_type,
            location=location,
            metadata=metadata,
            error=error
        )
        
    async def _queue_scan_result(self, result: ScanResult):
        """Queue a scan result for processing."""
        await self._scan_queue.put(result)
        
    def is_connected(self) -> bool:
        """Check if adapter is connected."""
        return self.connected
        
    def is_scanning(self) -> bool:
        """Check if adapter is currently scanning."""
        return self.scanning
