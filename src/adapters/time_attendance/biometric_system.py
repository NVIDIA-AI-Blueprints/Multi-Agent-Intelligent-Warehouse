"""
Biometric System Adapter

This module provides integration with biometric time attendance systems
including fingerprint, face recognition, and other biometric readers.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, date
import asyncio
import json
import socket
import threading

from .base import (
    BaseTimeAttendanceAdapter, AttendanceConfig, AttendanceRecord, 
    BiometricData, AttendanceType, AttendanceStatus, BiometricType
)

logger = logging.getLogger(__name__)

class BiometricSystemAdapter(BaseTimeAttendanceAdapter):
    """
    Biometric system adapter implementation.
    
    Supports various biometric time attendance systems via TCP/IP and serial connections.
    """
    
    def __init__(self, config: AttendanceConfig):
        super().__init__(config)
        self.socket: Optional[socket.socket] = None
        self.reader_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.biometric_templates: Dict[str, BiometricData] = {}
    
    def _check_connection(self, default_return: Any = False) -> Any:
        """
        Check if connected, return default value if not.
        
        Args:
            default_return: Value to return if not connected
            
        Returns:
            default_return if not connected, None if connected
        """
        if not self.connected:
            return default_return
        return None
    
    def _send_command_and_receive(
        self, 
        command_data: Dict[str, Any], 
        buffer_size: int = 1024
    ) -> Optional[Dict[str, Any]]:
        """
        Send command to socket and receive response.
        
        Args:
            command_data: Command dictionary to send
            buffer_size: Buffer size for receiving data
            
        Returns:
            Parsed JSON response or None if failed
        """
        if not self.socket:
            return None
        
        try:
            self.socket.send(json.dumps(command_data).encode('utf-8'))
            data = self.socket.recv(buffer_size)
            if data:
                return json.loads(data.decode('utf-8'))
        except Exception as e:
            logger.error(f"Error sending command: {e}")
        
        return None
    
    def _send_command_for_success(
        self, 
        command_data: Dict[str, Any], 
        operation_name: str
    ) -> bool:
        """
        Send command and return success status.
        
        Args:
            command_data: Command dictionary to send
            operation_name: Name of operation for error logging
            
        Returns:
            True if operation succeeded, False otherwise
        """
        response = self._send_command_and_receive(command_data)
        if response:
            return response.get("success", False)
        return False
        
    async def connect(self) -> bool:
        """Connect to biometric system."""
        try:
            # Parse connection string
            if self.config.connection_string.startswith("tcp://"):
                return await self._connect_tcp()
            elif self.config.connection_string.startswith("serial://"):
                return await self._connect_serial()
            else:
                logger.error(f"Unsupported connection string format: {self.config.connection_string}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to biometric system: {e}")
            return False
            
    def _parse_connection_string(self, prefix: str, default_port: int = 8080) -> tuple:
        """
        Parse connection string into host/port or port/baudrate.
        
        Args:
            prefix: Connection string prefix to remove (e.g., "tcp://", "serial://")
            default_port: Default port/baudrate value
            
        Returns:
            Tuple of (host/port, port/baudrate)
        """
        parts = self.config.connection_string.replace(prefix, "").split(":")
        first_part = parts[0]
        second_part = int(parts[1]) if len(parts) > 1 else default_port
        return first_part, second_part
    
    async def _connect_tcp(self) -> bool:
        """Connect via TCP/IP."""
        try:
            host, port = self._parse_connection_string("tcp://", 8080)
            
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
            logger.info(f"Connected to biometric system at {host}:{port}")
            return True
            
        except Exception as e:
            logger.error(f"TCP connection failed: {e}")
            return False
            
    async def _connect_serial(self) -> bool:
        """Connect via serial port."""
        try:
            port, baudrate = self._parse_connection_string("serial://", 9600)
            
            # For serial connection, we would use pyserial
            # This is a simplified implementation
            logger.info(f"Serial connection to {port} at {baudrate} baud")
            self.connected = True
            return True
            
        except Exception as e:
            logger.error(f"Serial connection failed: {e}")
            return False
            
    def _read_loop(self):
        """Background thread for reading biometric events."""
        while not self._stop_event.is_set():
            try:
                if self.socket:
                    # Read data from socket
                    data = self.socket.recv(1024)
                    if data:
                        # Parse biometric event
                        event_data = self._parse_biometric_event(data)
                        if event_data:
                            # Create attendance record
                            record = AttendanceRecord(
                                record_id=self._generate_record_id(),
                                employee_id=event_data["employee_id"],
                                attendance_type=event_data["attendance_type"],
                                timestamp=event_data["timestamp"],
                                location=event_data.get("location"),
                                device_id=self.config.device_type,
                                status=AttendanceStatus.PENDING,
                                metadata=event_data.get("metadata", {})
                            )
                            
                            # Notify callbacks
                            asyncio.create_task(self._notify_attendance_record(record))
                            
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Error reading biometric events: {e}")
                break
                
    def _parse_biometric_event(self, data: bytes) -> Optional[Dict[str, Any]]:
        """Parse biometric event data."""
        try:
            raw_data = data.decode('utf-8').strip()
            event_data = json.loads(raw_data)
            
            return {
                "employee_id": event_data.get("employee_id"),
                "attendance_type": AttendanceType(event_data.get("type", "check_in")),
                "timestamp": datetime.fromisoformat(event_data.get("timestamp", datetime.utcnow().isoformat())),
                "location": event_data.get("location"),
                "metadata": event_data.get("metadata", {})
            }
            
        except Exception as e:
            logger.error(f"Error parsing biometric event: {e}")
            return None
            
    async def disconnect(self) -> bool:
        """Disconnect from biometric system."""
        try:
            self.connected = False
            self.syncing = False
            
            # Stop reader thread
            if self.reader_thread:
                self._stop_event.set()
                self.reader_thread.join(timeout=1)
                
            # Close socket
            if self.socket:
                self.socket.close()
                self.socket = None
                
            logger.info("Disconnected from biometric system")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting from biometric system: {e}")
            return False
            
    def _parse_attendance_record(self, record_data: Dict[str, Any]) -> AttendanceRecord:
        """
        Parse attendance record from dictionary.
        
        Args:
            record_data: Dictionary containing record data
            
        Returns:
            AttendanceRecord object
        """
        return AttendanceRecord(
            record_id=record_data["record_id"],
            employee_id=record_data["employee_id"],
            attendance_type=AttendanceType(record_data["attendance_type"]),
            timestamp=datetime.fromisoformat(record_data["timestamp"]),
            location=record_data.get("location"),
            device_id=record_data.get("device_id"),
            status=AttendanceStatus(record_data.get("status", "pending")),
            notes=record_data.get("notes"),
            metadata=record_data.get("metadata", {})
        )
    
    async def get_attendance_records(
        self, 
        employee_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[AttendanceRecord]:
        """Get attendance records from biometric system."""
        try:
            if self._check_connection([]) is not None:
                return []
                
            query_data = {
                "command": "get_attendance_records",
                "employee_id": employee_id,
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None
            }
            
            response = self._send_command_and_receive(query_data, buffer_size=4096)
            if response:
                records = []
                for record_data in response.get("records", []):
                    records.append(self._parse_attendance_record(record_data))
                return records
                    
            return []
            
        except Exception as e:
            logger.error(f"Failed to get attendance records: {e}")
            return []
            
    async def create_attendance_record(self, record: AttendanceRecord) -> bool:
        """Create a new attendance record."""
        try:
            if self._check_connection(False) is not None:
                return False
                
            command_data = {
                "command": "create_attendance_record",
                "record": record.to_dict()
            }
            
            return self._send_command_for_success(command_data, "create attendance record")
            
        except Exception as e:
            logger.error(f"Failed to create attendance record: {e}")
            return False
            
    async def update_attendance_record(self, record: AttendanceRecord) -> bool:
        """Update an existing attendance record."""
        try:
            if self._check_connection(False) is not None:
                return False
                
            command_data = {
                "command": "update_attendance_record",
                "record": record.to_dict()
            }
            
            return self._send_command_for_success(command_data, "update attendance record")
            
        except Exception as e:
            logger.error(f"Failed to update attendance record: {e}")
            return False
            
    async def delete_attendance_record(self, record_id: str) -> bool:
        """Delete an attendance record."""
        try:
            if self._check_connection(False) is not None:
                return False
                
            command_data = {
                "command": "delete_attendance_record",
                "record_id": record_id
            }
            
            return self._send_command_for_success(command_data, "delete attendance record")
            
        except Exception as e:
            logger.error(f"Failed to delete attendance record: {e}")
            return False
            
    async def get_employee_attendance(
        self, 
        employee_id: str, 
        date: date
    ) -> Dict[str, Any]:
        """Get employee attendance summary for a specific date."""
        try:
            records = await self.get_attendance_records(
                employee_id=employee_id,
                start_date=date,
                end_date=date
            )
            
            # Calculate summary
            check_in = None
            check_out = None
            breaks = []
            total_hours = 0
            
            for record in records:
                if record.attendance_type == AttendanceType.CHECK_IN:
                    check_in = record.timestamp
                elif record.attendance_type == AttendanceType.CHECK_OUT:
                    check_out = record.timestamp
                elif record.attendance_type in [AttendanceType.BREAK_START, AttendanceType.LUNCH_START]:
                    breaks.append({"start": record.timestamp, "type": record.attendance_type.value})
                elif record.attendance_type in [AttendanceType.BREAK_END, AttendanceType.LUNCH_END]:
                    if breaks:
                        breaks[-1]["end"] = record.timestamp
                        
            # Calculate total hours
            if check_in and check_out:
                total_hours = (check_out - check_in).total_seconds() / 3600
                
                # Subtract break time
                for break_period in breaks:
                    if "end" in break_period:
                        break_duration = (break_period["end"] - break_period["start"]).total_seconds() / 3600
                        total_hours -= break_duration
                        
            return {
                "employee_id": employee_id,
                "date": date.isoformat(),
                "check_in": check_in.isoformat() if check_in else None,
                "check_out": check_out.isoformat() if check_out else None,
                "breaks": breaks,
                "total_hours": round(total_hours, 2),
                "status": "present" if check_in else "absent"
            }
            
        except Exception as e:
            logger.error(f"Failed to get employee attendance: {e}")
            return {}
            
    def _parse_biometric_data(self, bio_data: Dict[str, Any]) -> BiometricData:
        """
        Parse biometric data from dictionary.
        
        Args:
            bio_data: Dictionary containing biometric data
            
        Returns:
            BiometricData object
        """
        return BiometricData(
            employee_id=bio_data["employee_id"],
            biometric_type=BiometricType(bio_data["biometric_type"]),
            template_data=bio_data["template_data"],
            quality_score=bio_data.get("quality_score"),
            created_at=datetime.fromisoformat(bio_data.get("created_at", datetime.utcnow().isoformat())),
            metadata=bio_data.get("metadata", {})
        )
    
    async def get_biometric_data(
        self, 
        employee_id: Optional[str] = None
    ) -> List[BiometricData]:
        """Get biometric data from the system."""
        try:
            if self._check_connection([]) is not None:
                return []
                
            query_data = {
                "command": "get_biometric_data",
                "employee_id": employee_id
            }
            
            response = self._send_command_and_receive(query_data, buffer_size=4096)
            if response:
                biometric_data = []
                for bio_data in response.get("biometric_data", []):
                    biometric_data.append(self._parse_biometric_data(bio_data))
                return biometric_data
                    
            return []
            
        except Exception as e:
            logger.error(f"Failed to get biometric data: {e}")
            return []
            
    def _biometric_data_to_dict(self, biometric_data: BiometricData) -> Dict[str, Any]:
        """
        Convert BiometricData to dictionary for transmission.
        
        Args:
            biometric_data: BiometricData object
            
        Returns:
            Dictionary representation
        """
        return {
            "employee_id": biometric_data.employee_id,
            "biometric_type": biometric_data.biometric_type.value,
            "template_data": biometric_data.template_data,
            "quality_score": biometric_data.quality_score,
            "created_at": biometric_data.created_at.isoformat(),
            "metadata": biometric_data.metadata or {}
        }
    
    async def enroll_biometric_data(self, biometric_data: BiometricData) -> bool:
        """Enroll new biometric data for an employee."""
        try:
            if self._check_connection(False) is not None:
                return False
                
            command_data = {
                "command": "enroll_biometric_data",
                "biometric_data": self._biometric_data_to_dict(biometric_data)
            }
            
            return self._send_command_for_success(command_data, "enroll biometric data")
            
        except Exception as e:
            logger.error(f"Failed to enroll biometric data: {e}")
            return False
            
    async def verify_biometric(
        self, 
        biometric_type: BiometricType, 
        template_data: str
    ) -> Optional[str]:
        """Verify biometric data and return employee ID if match found."""
        try:
            if self._check_connection(None) is not None:
                return None
                
            command_data = {
                "command": "verify_biometric",
                "biometric_type": biometric_type.value,
                "template_data": template_data
            }
            
            response = self._send_command_and_receive(command_data)
            if response and response.get("success", False):
                return response.get("employee_id")
                        
            return None
            
        except Exception as e:
            logger.error(f"Failed to verify biometric: {e}")
            return None
