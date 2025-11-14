"""
RFID/Barcode Scanning Adapters

This module provides adapters for integrating with various RFID and barcode
scanning systems for warehouse operations.
"""

from .base import BaseScanningAdapter, ScanResult, ScanEvent, ScanningConfig
from .zebra_rfid import ZebraRFIDAdapter
from .honeywell_barcode import HoneywellBarcodeAdapter
from .generic_scanner import GenericScannerAdapter
from .factory import ScanningAdapterFactory

__all__ = [
    "BaseScanningAdapter",
    "ScanResult",
    "ScanEvent",
    "ScanningConfig",
    "ZebraRFIDAdapter",
    "HoneywellBarcodeAdapter",
    "GenericScannerAdapter",
    "ScanningAdapterFactory"
]
