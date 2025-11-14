"""
Honeywell Barcode Adapter

This module provides integration with Honeywell barcode scanners and readers.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import asyncio
import json
import socket
import threading

from .base import BaseScanningAdapter, ScanningConfig, ScanResult, ScanEvent, ScanType, ScanStatus

logger = logging.getLogger(__name__)

class HoneywellBarcodeAdapter(BaseScanningAdapter):
    """
    Honeywell barcode adapter implementation.
    
    Supports Honeywell barcode scanners via USB HID, Bluetooth, and TCP/IP.
    """
    
    def __init__(self, config: ScanningConfig):
        super().__init__(config)
        self.socket: Optional[socket.socket] = None
        self.reader_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
    async def connect(self) -> bool:
        """Connect to Honeywell barcode scanner."""
        try:
            # Parse connection string
            if self.config.connection_string.startswith("tcp://"):
                return await self._connect_tcp()
            elif self.config.connection_string.startswith("bluetooth://"):
                return await self._connect_bluetooth()
            elif self.config.connection_string.startswith("usb://"):
                return await self._connect_usb()
            else:
                logger.error(f"Unsupported connection string format: {self.config.connection_string}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to Honeywell barcode scanner: {e}")
            return False
            
    async def _connect_tcp(self) -> bool:
        """Connect via TCP/IP."""
        try:
            # Parse TCP connection string
            parts = self.config.connection_string.replace("tcp://", "").split(":")
            host = parts[0]
            port = int(parts[1]) if len(parts) > 1 else 8080
            
            # Create socket connection
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.config.timeout)
            self.socket.connect((host, port))
            
            # Start reader thread
            self._stop_event.clear()
            self.reader_thread = threading.Thread(target=self._read_loop)
            self.reader_thread.daemon = True
            self.reader_thread.start()
            
            self.connected = True
            logger.info(f"Connected to Honeywell barcode scanner at {host}:{port}")
            return True
            
        except Exception as e:
            logger.error(f"TCP connection failed: {e}")
            return False
            
    async def _connect_bluetooth(self) -> bool:
        """Connect via Bluetooth."""
        try:
            # Parse Bluetooth connection string
            parts = self.config.connection_string.replace("bluetooth://", "").split(":")
            device_address = parts[0]
            
            # For Bluetooth connection, we would use pybluez or similar
            # This is a simplified implementation
            logger.info(f"Bluetooth connection to {device_address}")
            self.connected = True
            return True
            
        except Exception as e:
            logger.error(f"Bluetooth connection failed: {e}")
            return False
            
    async def _connect_usb(self) -> bool:
        """Connect via USB HID."""
        try:
            # Parse USB connection string
            parts = self.config.connection_string.replace("usb://", "").split(":")
            device_path = parts[0] if parts[0] else "/dev/hidraw0"
            
            # For USB HID connection, we would use hidapi or similar
            # This is a simplified implementation
            logger.info(f"USB HID connection to {device_path}")
            self.connected = True
            return True
            
        except Exception as e:
            logger.error(f"USB connection failed: {e}")
            return False
            
    def _read_loop(self):
        """Background thread for reading barcode data."""
        while not self._stop_event.is_set():
            try:
                if self.socket:
                    # Read data from socket
                    data = self.socket.recv(1024)
                    if data:
                        # Parse barcode data
                        barcode_data = data.decode('utf-8').strip()
                        if barcode_data:
                            # Determine barcode type
                            scan_type = self._detect_barcode_type(barcode_data)
                            
                            # Create scan result
                            result = ScanResult(
                                scan_id=self._generate_scan_id(),
                                scan_type=scan_type,
                                data=barcode_data,
                                status=ScanStatus.SUCCESS,
                                timestamp=datetime.utcnow(),
                                device_id=self.config.device_type,
                                metadata={"protocol": "honeywell_barcode"}
                            )
                            
                            # Queue result for processing
                            asyncio.create_task(self._queue_scan_result(result))
                            
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Error reading barcode data: {e}")
                break
                
    def _detect_barcode_type(self, data: str) -> ScanType:
        """Detect barcode type based on data format."""
        # Simple heuristics for barcode type detection
        if data.startswith("http://") or data.startswith("https://"):
            return ScanType.QR_CODE
        elif len(data) == 12 and data.isdigit():
            return ScanType.BARCODE  # UPC-A
        elif len(data) == 13 and data.isdigit():
            return ScanType.BARCODE  # EAN-13
        elif data.startswith("^") and data.endswith("^"):
            return ScanType.DATA_MATRIX
        else:
            return ScanType.BARCODE
            
    async def disconnect(self) -> bool:
        """Disconnect from Honeywell barcode scanner."""
        try:
            self.connected = False
            self.scanning = False
            
            # Stop reader thread
            if self.reader_thread:
                self._stop_event.set()
                self.reader_thread.join(timeout=1)
                
            # Close socket
            if self.socket:
                self.socket.close()
                self.socket = None
                
            logger.info("Disconnected from Honeywell barcode scanner")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting from Honeywell barcode scanner: {e}")
            return False
            
    async def start_scanning(self) -> bool:
        """Start continuous barcode scanning."""
        if not self.connected:
            logger.error("Not connected to barcode scanner")
            return False
            
        try:
            # Send start scanning command
            if self.socket:
                start_cmd = "START_SCAN\n"
                self.socket.send(start_cmd.encode('utf-8'))
                
            self.scanning = True
            
            # Start scan processing task
            if not self._scan_task or self._scan_task.done():
                self._scan_task = asyncio.create_task(self._process_scan_queue())
                
            logger.info("Started barcode scanning")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start barcode scanning: {e}")
            return False
            
    async def stop_scanning(self) -> bool:
        """Stop continuous barcode scanning."""
        try:
            # Send stop scanning command
            if self.socket:
                stop_cmd = "STOP_SCAN\n"
                self.socket.send(stop_cmd.encode('utf-8'))
                
            self.scanning = False
            
            # Cancel scan processing task
            if self._scan_task and not self._scan_task.done():
                self._scan_task.cancel()
                
            logger.info("Stopped barcode scanning")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop barcode scanning: {e}")
            return False
            
    async def single_scan(self, timeout: Optional[int] = None) -> Optional[ScanResult]:
        """Perform a single barcode scan."""
        if not self.connected:
            logger.error("Not connected to barcode scanner")
            return None
            
        try:
            # Send single scan command
            if self.socket:
                scan_cmd = "SINGLE_SCAN\n"
                self.socket.send(scan_cmd.encode('utf-8'))
                
            # Wait for response
            wait_time = timeout or self.config.timeout
            start_time = datetime.utcnow()
            
            while (datetime.utcnow() - start_time).total_seconds() < wait_time:
                try:
                    if self.socket:
                        data = self.socket.recv(1024)
                        if data:
                            barcode_data = data.decode('utf-8').strip()
                            if barcode_data:
                                scan_type = self._detect_barcode_type(barcode_data)
                                return await self._create_scan_result(
                                    scan_type=scan_type,
                                    data=barcode_data,
                                    status=ScanStatus.SUCCESS,
                                    metadata={"protocol": "honeywell_barcode", "single_scan": True}
                                )
                except socket.timeout:
                    continue
                    
            # Timeout
            return await self._create_scan_result(
                scan_type=ScanType.BARCODE,
                data="",
                status=ScanStatus.TIMEOUT,
                error="Scan timeout"
            )
            
        except Exception as e:
            logger.error(f"Single scan failed: {e}")
            return await self._create_scan_result(
                scan_type=ScanType.BARCODE,
                data="",
                status=ScanStatus.ERROR,
                error=str(e)
            )
            
    async def get_device_info(self) -> Dict[str, Any]:
        """Get Honeywell barcode scanner information."""
        try:
            if not self.connected:
                return {"error": "Not connected"}
                
            # Send device info command
            if self.socket:
                info_cmd = "GET_DEVICE_INFO\n"
                self.socket.send(info_cmd.encode('utf-8'))
                
                # Wait for response
                data = self.socket.recv(1024)
                if data:
                    info_data = data.decode('utf-8').strip()
                    try:
                        return json.loads(info_data)
                    except json.JSONDecodeError:
                        return {"raw_info": info_data}
                        
            return {
                "device_type": "Honeywell Barcode Scanner",
                "connection": self.config.connection_string,
                "status": "connected" if self.connected else "disconnected",
                "scanning": self.scanning
            }
            
        except Exception as e:
            logger.error(f"Failed to get device info: {e}")
            return {"error": str(e)}
