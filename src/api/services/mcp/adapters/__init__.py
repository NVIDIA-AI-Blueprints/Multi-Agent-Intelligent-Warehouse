"""
MCP Adapters for Warehouse Operational Assistant

This package contains MCP-enabled adapters for various external systems
including ERP, WMS, IoT, RFID, and Time Attendance systems.
"""

from .erp_adapter import MCPERPAdapter

__all__ = [
    "MCPERPAdapter",
]

__version__ = "1.0.0"
