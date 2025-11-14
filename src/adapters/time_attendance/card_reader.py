"""
Card Reader Adapter

This module provides integration with card-based time attendance systems
including proximity cards, smart cards, and magnetic stripe cards.
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

class CardReaderAdapter(BaseTimeAttendanceAdapter):
    """
    Card reader adapter implementation.
    
    Supports various card-based time attendance systems via TCP/IP and serial connections.
    """
    
    def __init__(self, config: AttendanceConfig):
        super().__init__(config)
        self.socket: Optional[socket.socket] = None
        self.reader_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.card_database: Dict[str, str] = {}  # card_id -> employee_id mapping
        
    async def connect(self) -> bool:
        """Connect to card reader system."""
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
            logger.error(f"Failed to connect to card reader system: {e}")
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
            logger.info(f"Connected to card reader system at {host}:{port}")
            return True
            
        except Exception as e:
            logger.error(f"TCP connection failed: {e}")
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
        """Background thread for reading card events."""
        while not self._stop_event.is_set():
            try:
                if self.socket:
                    # Read data from socket
                    data = self.socket.recv(1024)
                    if data:
                        # Parse card event
                        event_data = self._parse_card_event(data)
                        if event_data:
                            # Look up employee ID from card ID
                            employee_id = self.card_database.get(event_data["card_id"])
                            if not employee_id:
                                # Try to get employee ID from system
                                employee_id = asyncio.run(self._lookup_employee_by_card(event_data["card_id"]))
                                if employee_id:
                                    self.card_database[event_data["card_id"]] = employee_id
                                    
                            if employee_id:
                                # Create attendance record
                                record = AttendanceRecord(
                                    record_id=self._generate_record_id(),
                                    employee_id=employee_id,
                                    attendance_type=event_data["attendance_type"],
                                    timestamp=event_data["timestamp"],
                                    location=event_data.get("location"),
                                    device_id=self.config.device_type,
                                    status=AttendanceStatus.PENDING,
                                    metadata={
                                        "card_id": event_data["card_id"],
                                        "card_type": event_data.get("card_type", "proximity")
                                    }
                                )
                                
                                # Notify callbacks
                                asyncio.create_task(self._notify_attendance_record(record))
                            else:
                                logger.warning(f"Unknown card ID: {event_data['card_id']}")
                            
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Error reading card events: {e}")
                break
                
    def _parse_card_event(self, data: bytes) -> Optional[Dict[str, Any]]:
        """Parse card event data."""
        try:
            raw_data = data.decode('utf-8').strip()
            event_data = json.loads(raw_data)
            
            return {
                "card_id": event_data.get("card_id"),
                "attendance_type": AttendanceType(event_data.get("type", "check_in")),
                "timestamp": datetime.fromisoformat(event_data.get("timestamp", datetime.utcnow().isoformat())),
                "location": event_data.get("location"),
                "card_type": event_data.get("card_type", "proximity"),
                "metadata": event_data.get("metadata", {})
            }
            
        except Exception as e:
            logger.error(f"Error parsing card event: {e}")
            return None
            
    async def _lookup_employee_by_card(self, card_id: str) -> Optional[str]:
        """Look up employee ID by card ID from the system."""
        try:
            if not self.connected:
                return None
                
            # Send lookup command
            lookup_data = {
                "command": "lookup_employee_by_card",
                "card_id": card_id
            }
            
            if self.socket:
                self.socket.send(json.dumps(lookup_data).encode('utf-8'))
                
                # Wait for response
                data = self.socket.recv(1024)
                if data:
                    response = json.loads(data.decode('utf-8'))
                    return response.get("employee_id")
                    
            return None
            
        except Exception as e:
            logger.error(f"Failed to lookup employee by card: {e}")
            return None
            
    async def disconnect(self) -> bool:
        """Disconnect from card reader system."""
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
                
            logger.info("Disconnected from card reader system")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting from card reader system: {e}")
            return False
            
    async def get_attendance_records(
        self, 
        employee_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[AttendanceRecord]:
        """Get attendance records from card reader system."""
        try:
            if not self.connected:
                return []
                
            # Send query command
            query_data = {
                "command": "get_attendance_records",
                "employee_id": employee_id,
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None
            }
            
            if self.socket:
                self.socket.send(json.dumps(query_data).encode('utf-8'))
                
                # Wait for response
                data = self.socket.recv(4096)
                if data:
                    response = json.loads(data.decode('utf-8'))
                    records = []
                    
                    for record_data in response.get("records", []):
                        record = AttendanceRecord(
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
                        records.append(record)
                        
                    return records
                    
            return []
            
        except Exception as e:
            logger.error(f"Failed to get attendance records: {e}")
            return []
            
    async def create_attendance_record(self, record: AttendanceRecord) -> bool:
        """Create a new attendance record."""
        try:
            if not self.connected:
                return False
                
            # Send create command
            record_data = {
                "command": "create_attendance_record",
                "record": record.to_dict()
            }
            
            if self.socket:
                self.socket.send(json.dumps(record_data).encode('utf-8'))
                
                # Wait for response
                data = self.socket.recv(1024)
                if data:
                    response = json.loads(data.decode('utf-8'))
                    return response.get("success", False)
                    
            return False
            
        except Exception as e:
            logger.error(f"Failed to create attendance record: {e}")
            return False
            
    async def update_attendance_record(self, record: AttendanceRecord) -> bool:
        """Update an existing attendance record."""
        try:
            if not self.connected:
                return False
                
            # Send update command
            record_data = {
                "command": "update_attendance_record",
                "record": record.to_dict()
            }
            
            if self.socket:
                self.socket.send(json.dumps(record_data).encode('utf-8'))
                
                # Wait for response
                data = self.socket.recv(1024)
                if data:
                    response = json.loads(data.decode('utf-8'))
                    return response.get("success", False)
                    
            return False
            
        except Exception as e:
            logger.error(f"Failed to update attendance record: {e}")
            return False
            
    async def delete_attendance_record(self, record_id: str) -> bool:
        """Delete an attendance record."""
        try:
            if not self.connected:
                return False
                
            # Send delete command
            delete_data = {
                "command": "delete_attendance_record",
                "record_id": record_id
            }
            
            if self.socket:
                self.socket.send(json.dumps(delete_data).encode('utf-8'))
                
                # Wait for response
                data = self.socket.recv(1024)
                if data:
                    response = json.loads(data.decode('utf-8'))
                    return response.get("success", False)
                    
            return False
            
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
            
    async def get_biometric_data(
        self, 
        employee_id: Optional[str] = None
    ) -> List[BiometricData]:
        """Card readers don't store biometric data."""
        return []
        
    async def enroll_biometric_data(self, biometric_data: BiometricData) -> bool:
        """Card readers don't support biometric enrollment."""
        return False
        
    async def verify_biometric(
        self, 
        biometric_type: BiometricType, 
        template_data: str
    ) -> Optional[str]:
        """Card readers don't support biometric verification."""
        return None
        
    async def register_card(self, card_id: str, employee_id: str) -> bool:
        """Register a card with an employee."""
        try:
            if not self.connected:
                return False
                
            # Send register command
            register_data = {
                "command": "register_card",
                "card_id": card_id,
                "employee_id": employee_id
            }
            
            if self.socket:
                self.socket.send(json.dumps(register_data).encode('utf-8'))
                
                # Wait for response
                data = self.socket.recv(1024)
                if data:
                    response = json.loads(data.decode('utf-8'))
                    if response.get("success", False):
                        self.card_database[card_id] = employee_id
                        return True
                        
            return False
            
        except Exception as e:
            logger.error(f"Failed to register card: {e}")
            return False
            
    async def unregister_card(self, card_id: str) -> bool:
        """Unregister a card."""
        try:
            if not self.connected:
                return False
                
            # Send unregister command
            unregister_data = {
                "command": "unregister_card",
                "card_id": card_id
            }
            
            if self.socket:
                self.socket.send(json.dumps(unregister_data).encode('utf-8'))
                
                # Wait for response
                data = self.socket.recv(1024)
                if data:
                    response = json.loads(data.decode('utf-8'))
                    if response.get("success", False):
                        self.card_database.pop(card_id, None)
                        return True
                        
            return False
            
        except Exception as e:
            logger.error(f"Failed to unregister card: {e}")
            return False
