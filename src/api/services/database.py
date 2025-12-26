# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Database Service for Warehouse Operational Assistant

This service provides database connection management and health checks.
"""

import os
import asyncpg
from typing import AsyncGenerator
import logging

logger = logging.getLogger(__name__)


def _get_database_url() -> str:
    """
    Get database URL from environment variables.
    
    Constructs DATABASE_URL from individual components if not directly set.
    Requires POSTGRES_PASSWORD to be set (no hardcoded defaults).
    
    Returns:
        str: Database connection URL
        
    Raises:
        ValueError: If required environment variables are not set
    """
    # First, try to get DATABASE_URL directly
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url
    
    # If not set, construct from individual environment variables
    # SECURITY: Do not hardcode passwords - require POSTGRES_PASSWORD to be set
    postgres_user = os.getenv("POSTGRES_USER", "warehouse")
    postgres_password = os.getenv("POSTGRES_PASSWORD")
    postgres_db = os.getenv("POSTGRES_DB", "warehouse")
    postgres_host = os.getenv("DB_HOST", "localhost")
    postgres_port = os.getenv("DB_PORT", "5435")
    
    if not postgres_password:
        raise ValueError(
            "POSTGRES_PASSWORD environment variable is required. "
            "Set it in your .env file or environment."
        )
    
    return f"postgresql://{postgres_user}:{postgres_password}@{postgres_host}:{postgres_port}/{postgres_db}"


async def get_database_connection():
    """
    Get a database connection as an async context manager.

    Returns:
        asyncpg.Connection: Database connection
        
    Raises:
        ValueError: If required environment variables are not set
    """
    database_url = _get_database_url()
    return asyncpg.connect(database_url)
