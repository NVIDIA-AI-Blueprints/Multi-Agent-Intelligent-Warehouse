"""
Generic Scanner Adapter

This module provides a generic adapter for various scanning devices
that can be configured for different protocols and connection types.
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

class GenericScannerAdapter(BaseScanningAdapter):
    """
    Generic scanner adapter implementation.
    
    Supports various scanning devices with configurable protocols.
    """
    
    def __init__(self, config: ScanningConfig):
        super().__init__(config)
        self.socket: Optional[socket.socket] = None
        self.reader_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.protocol = self.config.additional_params.get("protocol", "generic") if self.config.additional_params else "generic"
        
    async def connect(self) -> bool:
        """Connect to generic scanner device."""
        try:
            # Parse connection string
            if self.config.connection_string.startswith("tcp://"):
                return await self._connect_tcp()
            elif self.config.connection_string.startswith("udp://"):
                return await self._connect_udp()
            elif self.config.connection_string.startswith("serial://"):
                return await self._connect_serial()
            else:
                logger.error(f"Unsupported connection string format: {self.config.connection_string}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to generic scanner: {e}")
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
            logger.info(f"Connected to generic scanner at {host}:{port}")
            return True
            
        except Exception as e:
            logger.error(f"TCP connection failed: {e}")
            return False
            
    async def _connect_udp(self) -> bool:
        """Connect via UDP."""
        try:
            # Parse UDP connection string
            parts = self.config.connection_string.replace("udp://", "").split(":")
            host = parts[0]
            port = int(parts[1]) if len(parts) > 1 else 8080
            
            # Create socket connection
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.settimeout(self.config.timeout)
            self.socket.bind((host, port))
            
            # Start reader thread
            self._stop_event.clear()
            self.reader_thread = threading.Thread(target=self._read_loop)
            self.reader_thread.daemon = True
            self.reader_thread.start()
            
            self.connected = True
            logger.info(f"Connected to generic scanner via UDP at {host}:{port}")
            return True
            
        except Exception as e:
            logger.error(f"UDP connection failed: {e}")
            return False
            
    async def _connect_serial(self) -> bool:
        """Connect via serial port."""
        try:
            # Parse serial connection string
            parts = self.config.connection_string.replace("serial://", "").split(":")
            port = parts[0]
            baudrate = int(parts[1]) if len(parts) > 1 else 9600
            
            # For serial connection, we would use pyserial
            # This is a simplified implementation
            logger.info(f"Serial connection to {port} at {baudrate} baud")
            self.connected = True
            return True
            
        except Exception as e:
            logger.error(f"Serial connection failed: {e}")
            return False
            
    def _read_loop(self):
        """Background thread for reading scan data."""
        while not self._stop_event.is_set():
            try:
                if self.socket:
                    # Read data from socket
                    data = self.socket.recv(1024)
                    if data:
                        # Parse scan data based on protocol
                        scan_data = self._parse_scan_data(data)
                        if scan_data:
                            # Create scan result
                            result = ScanResult(
                                scan_id=self._generate_scan_id(),
                                scan_type=scan_data["scan_type"],
                                data=scan_data["data"],
                                status=ScanStatus.SUCCESS,
                                timestamp=datetime.utcnow(),
                                device_id=self.config.device_type,
                                metadata={
                                    "protocol": self.protocol,
                                    "raw_data": scan_data.get("raw_data", "")
                                }
                            )
                            
                            # Queue result for processing
                            asyncio.create_task(self._queue_scan_result(result))
                            
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Error reading scan data: {e}")
                break
                
    def _parse_scan_data(self, data: bytes) -> Optional[Dict[str, Any]]:
        """Parse scan data based on protocol."""
        try:
            raw_data = data.decode('utf-8').strip()
            
            # Parse based on protocol
            if self.protocol == "json":
                # JSON protocol
                parsed_data = json.loads(raw_data)
                return {
                    "scan_type": ScanType(parsed_data.get("type", "barcode")),
                    "data": parsed_data.get("data", ""),
                    "raw_data": raw_data
                }
            elif self.protocol == "csv":
                # CSV protocol
                parts = raw_data.split(",")
                if len(parts) >= 2:
                    return {
                        "scan_type": ScanType(parts[0]),
                        "data": parts[1],
                        "raw_data": raw_data
                    }
            elif self.protocol == "simple":
                # Simple text protocol
                return {
                    "scan_type": self._detect_scan_type(raw_data),
                    "data": raw_data,
                    "raw_data": raw_data
                }
            else:
                # Default protocol
                return {
                    "scan_type": ScanType.BARCODE,
                    "data": raw_data,
                    "raw_data": raw_data
                }
                
        except Exception as e:
            logger.error(f"Error parsing scan data: {e}")
            return None
            
    def _detect_scan_type(self, data: str) -> ScanType:
        """Detect scan type based on data format."""
        # Simple heuristics for scan type detection
        if data.startswith("http://") or data.startswith("https://"):
            return ScanType.QR_CODE
        elif len(data) == 12 and data.isdigit():
            return ScanType.BARCODE  # UPC-A
        elif len(data) == 13 and data.isdigit():
            return ScanType.BARCODE  # EAN-13
        elif data.startswith("^") and data.endswith("^"):
            return ScanType.DATA_MATRIX
        elif data.startswith("RFID:"):
            return ScanType.RFID
        else:
            return ScanType.BARCODE
            
    async def disconnect(self) -> bool:
        """Disconnect from generic scanner."""
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
                
            logger.info("Disconnected from generic scanner")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting from generic scanner: {e}")
            return False
            
    async def start_scanning(self) -> bool:
        """Start continuous scanning."""
        if not self.connected:
            logger.error("Not connected to scanner")
            return False
            
        try:
            # Send start scanning command based on protocol
            if self.socket:
                start_cmd = self._get_start_command()
                self.socket.send(start_cmd.encode('utf-8'))
                
            self.scanning = True
            
            # Start scan processing task
            if not self._scan_task or self._scan_task.done():
                self._scan_task = asyncio.create_task(self._process_scan_queue())
                
            logger.info("Started scanning")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start scanning: {e}")
            return False
            
    async def stop_scanning(self) -> bool:
        """Stop continuous scanning."""
        try:
            # Send stop scanning command based on protocol
            if self.socket:
                stop_cmd = self._get_stop_command()
                self.socket.send(stop_cmd.encode('utf-8'))
                
            self.scanning = False
            
            # Cancel scan processing task
            if self._scan_task and not self._scan_task.done():
                self._scan_task.cancel()
                
            logger.info("Stopped scanning")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop scanning: {e}")
            return False
            
    def _get_start_command(self) -> str:
        """Get start scanning command based on protocol."""
        if self.protocol == "json":
            return json.dumps({"command": "start_scan"}) + "\n"
        elif self.protocol == "simple":
            return "START\n"
        else:
            return "START_SCAN\n"
            
    def _get_stop_command(self) -> str:
        """Get stop scanning command based on protocol."""
        if self.protocol == "json":
            return json.dumps({"command": "stop_scan"}) + "\n"
        elif self.protocol == "simple":
            return "STOP\n"
        else:
            return "STOP_SCAN\n"
            
    async def single_scan(self, timeout: Optional[int] = None) -> Optional[ScanResult]:
        """Perform a single scan."""
        if not self.connected:
            logger.error("Not connected to scanner")
            return None
            
        try:
            # Send single scan command
            if self.socket:
                scan_cmd = self._get_single_scan_command()
                self.socket.send(scan_cmd.encode('utf-8'))
                
            # Wait for response
            wait_time = timeout or self.config.timeout
            start_time = datetime.utcnow()
            
            while (datetime.utcnow() - start_time).total_seconds() < wait_time:
                try:
                    if self.socket:
                        data = self.socket.recv(1024)
                        if data:
                            scan_data = self._parse_scan_data(data)
                            if scan_data:
                                return await self._create_scan_result(
                                    scan_type=scan_data["scan_type"],
                                    data=scan_data["data"],
                                    status=ScanStatus.SUCCESS,
                                    metadata={
                                        "protocol": self.protocol,
                                        "single_scan": True,
                                        "raw_data": scan_data.get("raw_data", "")
                                    }
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
            
    def _get_single_scan_command(self) -> str:
        """Get single scan command based on protocol."""
        if self.protocol == "json":
            return json.dumps({"command": "single_scan"}) + "\n"
        elif self.protocol == "simple":
            return "SCAN\n"
        else:
            return "SINGLE_SCAN\n"
            
    async def get_device_info(self) -> Dict[str, Any]:
        """Get generic scanner information."""
        try:
            if not self.connected:
                return {"error": "Not connected"}
                
            # Send device info command
            if self.socket:
                info_cmd = self._get_device_info_command()
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
                "device_type": "Generic Scanner",
                "protocol": self.protocol,
                "connection": self.config.connection_string,
                "status": "connected" if self.connected else "disconnected",
                "scanning": self.scanning
            }
            
        except Exception as e:
            logger.error(f"Failed to get device info: {e}")
            return {"error": str(e)}
            
    def _get_device_info_command(self) -> str:
        """Get device info command based on protocol."""
        if self.protocol == "json":
            return json.dumps({"command": "get_info"}) + "\n"
        elif self.protocol == "simple":
            return "INFO\n"
        else:
            return "GET_DEVICE_INFO\n"
