"""
Shared test configuration module for unit tests.

Provides centralized configuration for API endpoints, timeouts, and other test settings.
"""

import os
from pathlib import Path

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent

# API Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8001")
CHAT_ENDPOINT = f"{API_BASE_URL}/api/v1/chat"
HEALTH_ENDPOINT = f"{API_BASE_URL}/api/v1/health/simple"
VERSION_ENDPOINT = f"{API_BASE_URL}/api/v1/version"

# Timeout Configuration (in seconds)
DEFAULT_TIMEOUT = int(os.getenv("TEST_TIMEOUT", "180"))  # 3 minutes for complex queries
GUARDRAILS_TIMEOUT = int(os.getenv("GUARDRAILS_TIMEOUT", "60"))  # 1 minute for guardrails
SIMPLE_QUERY_TIMEOUT = int(os.getenv("SIMPLE_QUERY_TIMEOUT", "30"))  # 30 seconds for simple queries
LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "120"))  # 2 minutes for LLM calls

# Environment Variables
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "changeme")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5435"))
POSTGRES_DB = os.getenv("POSTGRES_DB", "warehouse")
POSTGRES_USER = os.getenv("POSTGRES_USER", "warehouse")

# Test Data Paths
TEST_DATA_DIR = PROJECT_ROOT / "tests" / "fixtures"
SAMPLE_DATA_DIR = PROJECT_ROOT / "data" / "sample"

# Test File Paths
TEST_INVOICE_FILE = "test_invoice.png"
TEST_INVOICE_CANDIDATES = [
    TEST_INVOICE_FILE,
    str(SAMPLE_DATA_DIR / TEST_INVOICE_FILE),
    str(TEST_DATA_DIR / TEST_INVOICE_FILE),
    str(TEST_DATA_DIR / "test_invoice.png"),
]


