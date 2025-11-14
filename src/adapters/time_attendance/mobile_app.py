"""
Mobile App Adapter

This module provides integration with mobile time attendance applications
for employee self-service attendance tracking.
"""

import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, date
import asyncio
import json
import aiohttp

from .base import (
    BaseTimeAttendanceAdapter, AttendanceConfig, AttendanceRecord, 
    BiometricData, AttendanceType, AttendanceStatus, BiometricType
)

logger = logging.getLogger(__name__)

class MobileAppAdapter(BaseTimeAttendanceAdapter):
    """
    Mobile app adapter implementation.
    
    Supports mobile time attendance applications via REST API.
    """
    
    def __init__(self, config: AttendanceConfig):
        super().__init__(config)
        self.session: Optional[aiohttp.ClientSession] = None
        self.api_base_url = self.config.connection_string
        self.api_key = self.config.additional_params.get("api_key") if self.config.additional_params else None
        
    async def connect(self) -> bool:
        """Connect to mobile app API."""
        try:
            # Create HTTP session
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.config.timeout)
            )
            
            # Test connection
            test_response = await self._make_request("GET", "/health")
            if test_response and test_response.get("status") == "ok":
                self.connected = True
                logger.info("Connected to mobile app API")
                return True
            else:
                logger.error("Failed to connect to mobile app API")
                return False
                
        except Exception as e:
            logger.error(f"Failed to connect to mobile app API: {e}")
            return False
            
    async def disconnect(self) -> bool:
        """Disconnect from mobile app API."""
        try:
            if self.session:
                await self.session.close()
                self.session = None
                
            self.connected = False
            logger.info("Disconnected from mobile app API")
            return True
            
        except Exception as e:
            logger.error(f"Error disconnecting from mobile app API: {e}")
            return False
            
    async def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Make HTTP request to mobile app API."""
        if not self.session:
            return None
            
        try:
            url = f"{self.api_base_url.rstrip('/')}/{endpoint.lstrip('/')}"
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
                
            async with self.session.request(
                method=method,
                url=url,
                json=data,
                params=params,
                headers=headers
            ) as response:
                
                if response.status < 400:
                    return await response.json()
                else:
                    logger.error(f"API request failed: {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"API request error: {e}")
            return None
            
    async def get_attendance_records(
        self, 
        employee_id: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[AttendanceRecord]:
        """Get attendance records from mobile app."""
        try:
            if not self.connected:
                return []
                
            params = {}
            if employee_id:
                params["employee_id"] = employee_id
            if start_date:
                params["start_date"] = start_date.isoformat()
            if end_date:
                params["end_date"] = end_date.isoformat()
                
            response = await self._make_request("GET", "/attendance/records", params=params)
            if not response:
                return []
                
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
            
        except Exception as e:
            logger.error(f"Failed to get attendance records: {e}")
            return []
            
    async def create_attendance_record(self, record: AttendanceRecord) -> bool:
        """Create a new attendance record."""
        try:
            if not self.connected:
                return False
                
            response = await self._make_request(
                "POST", 
                "/attendance/records", 
                data=record.to_dict()
            )
            
            return response is not None and response.get("success", False)
            
        except Exception as e:
            logger.error(f"Failed to create attendance record: {e}")
            return False
            
    async def update_attendance_record(self, record: AttendanceRecord) -> bool:
        """Update an existing attendance record."""
        try:
            if not self.connected:
                return False
                
            response = await self._make_request(
                "PUT", 
                f"/attendance/records/{record.record_id}", 
                data=record.to_dict()
            )
            
            return response is not None and response.get("success", False)
            
        except Exception as e:
            logger.error(f"Failed to update attendance record: {e}")
            return False
            
    async def delete_attendance_record(self, record_id: str) -> bool:
        """Delete an attendance record."""
        try:
            if not self.connected:
                return False
                
            response = await self._make_request(
                "DELETE", 
                f"/attendance/records/{record_id}"
            )
            
            return response is not None and response.get("success", False)
            
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
            if not self.connected:
                return {}
                
            response = await self._make_request(
                "GET", 
                f"/attendance/employees/{employee_id}/summary",
                params={"date": date.isoformat()}
            )
            
            if response:
                return response.get("summary", {})
                
            return {}
            
        except Exception as e:
            logger.error(f"Failed to get employee attendance: {e}")
            return {}
            
    async def get_biometric_data(
        self, 
        employee_id: Optional[str] = None
    ) -> List[BiometricData]:
        """Get biometric data from mobile app."""
        try:
            if not self.connected:
                return []
                
            params = {}
            if employee_id:
                params["employee_id"] = employee_id
                
            response = await self._make_request("GET", "/biometric/data", params=params)
            if not response:
                return []
                
            biometric_data = []
            for bio_data in response.get("biometric_data", []):
                bio = BiometricData(
                    employee_id=bio_data["employee_id"],
                    biometric_type=BiometricType(bio_data["biometric_type"]),
                    template_data=bio_data["template_data"],
                    quality_score=bio_data.get("quality_score"),
                    created_at=datetime.fromisoformat(bio_data.get("created_at", datetime.utcnow().isoformat())),
                    metadata=bio_data.get("metadata", {})
                )
                biometric_data.append(bio)
                
            return biometric_data
            
        except Exception as e:
            logger.error(f"Failed to get biometric data: {e}")
            return []
            
    async def enroll_biometric_data(self, biometric_data: BiometricData) -> bool:
        """Enroll new biometric data for an employee."""
        try:
            if not self.connected:
                return False
                
            response = await self._make_request(
                "POST", 
                "/biometric/enroll", 
                data={
                    "employee_id": biometric_data.employee_id,
                    "biometric_type": biometric_data.biometric_type.value,
                    "template_data": biometric_data.template_data,
                    "quality_score": biometric_data.quality_score,
                    "created_at": biometric_data.created_at.isoformat(),
                    "metadata": biometric_data.metadata or {}
                }
            )
            
            return response is not None and response.get("success", False)
            
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
            if not self.connected:
                return None
                
            response = await self._make_request(
                "POST", 
                "/biometric/verify", 
                data={
                    "biometric_type": biometric_type.value,
                    "template_data": template_data
                }
            )
            
            if response and response.get("success", False):
                return response.get("employee_id")
                
            return None
            
        except Exception as e:
            logger.error(f"Failed to verify biometric: {e}")
            return None
            
    async def get_employee_profile(self, employee_id: str) -> Optional[Dict[str, Any]]:
        """Get employee profile information."""
        try:
            if not self.connected:
                return None
                
            response = await self._make_request("GET", f"/employees/{employee_id}")
            return response
            
        except Exception as e:
            logger.error(f"Failed to get employee profile: {e}")
            return None
            
    async def update_employee_profile(self, employee_id: str, profile_data: Dict[str, Any]) -> bool:
        """Update employee profile information."""
        try:
            if not self.connected:
                return False
                
            response = await self._make_request(
                "PUT", 
                f"/employees/{employee_id}", 
                data=profile_data
            )
            
            return response is not None and response.get("success", False)
            
        except Exception as e:
            logger.error(f"Failed to update employee profile: {e}")
            return False
            
    async def get_attendance_policies(self) -> List[Dict[str, Any]]:
        """Get attendance policies."""
        try:
            if not self.connected:
                return []
                
            response = await self._make_request("GET", "/attendance/policies")
            return response.get("policies", []) if response else []
            
        except Exception as e:
            logger.error(f"Failed to get attendance policies: {e}")
            return []
            
    async def submit_attendance_request(
        self, 
        employee_id: str, 
        request_type: str, 
        start_date: date, 
        end_date: Optional[date] = None,
        reason: Optional[str] = None
    ) -> bool:
        """Submit attendance request (leave, overtime, etc.)."""
        try:
            if not self.connected:
                return False
                
            request_data = {
                "employee_id": employee_id,
                "request_type": request_type,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat() if end_date else None,
                "reason": reason
            }
            
            response = await self._make_request(
                "POST", 
                "/attendance/requests", 
                data=request_data
            )
            
            return response is not None and response.get("success", False)
            
        except Exception as e:
            logger.error(f"Failed to submit attendance request: {e}")
            return False
