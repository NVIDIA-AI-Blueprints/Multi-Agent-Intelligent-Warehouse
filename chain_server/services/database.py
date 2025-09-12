"""
Database Service for Warehouse Operational Assistant

This service provides database connection management and health checks.
"""

import os
import asyncpg
from typing import AsyncGenerator
import logging

logger = logging.getLogger(__name__)

async def get_database_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """
    Get a database connection.
    
    Yields:
        asyncpg.Connection: Database connection
    """
    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5435/warehouse_ops")
    
    try:
        conn = await asyncpg.connect(database_url)
        yield conn
    finally:
        await conn.close()
