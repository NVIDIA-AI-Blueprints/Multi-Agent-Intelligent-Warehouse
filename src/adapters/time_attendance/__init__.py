"""
Time Attendance Adapters

This module provides adapters for integrating with various time attendance
and biometric systems for employee tracking and management.
"""

from .base import BaseTimeAttendanceAdapter, AttendanceRecord, BiometricData, AttendanceConfig
from .biometric_system import BiometricSystemAdapter
from .card_reader import CardReaderAdapter
from .mobile_app import MobileAppAdapter
from .factory import TimeAttendanceAdapterFactory

__all__ = [
    "BaseTimeAttendanceAdapter",
    "AttendanceRecord",
    "BiometricData",
    "AttendanceConfig",
    "BiometricSystemAdapter",
    "CardReaderAdapter",
    "MobileAppAdapter",
    "TimeAttendanceAdapterFactory"
]
