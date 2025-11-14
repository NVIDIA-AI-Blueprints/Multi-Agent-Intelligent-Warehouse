"""
ERP Integration Adapters

This module provides adapters for integrating with various ERP systems
including SAP ECC, Oracle ERP, and other enterprise resource planning systems.
"""

from .base import BaseERPAdapter, ERPConnection, ERPResponse
from .sap_ecc import SAPECCAdapter
from .oracle_erp import OracleERPAdapter
from .factory import ERPAdapterFactory

__all__ = [
    "BaseERPAdapter",
    "ERPConnection", 
    "ERPResponse",
    "SAPECCAdapter",
    "OracleERPAdapter",
    "ERPAdapterFactory"
]
