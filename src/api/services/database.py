"""
Database Service for Warehouse Operational Assistant

This service provides database connection management and health checks.
"""

import os
import asyncpg
from typing import AsyncGenerator
import logging

logger = logging.getLogger(__name__)


async def get_database_connection():
    """
    Get a database connection as an async context manager.

    Returns:
        asyncpg.Connection: Database connection
    """
    # Get database URL from environment
    database_url = os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5435/warehouse_ops"
    )

    return asyncpg.connect(database_url)
