#!/usr/bin/env python3
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
Test the database connection and the worker roster table
"""

import asyncio
import sys
import pytest
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.retrieval.structured import SQLRetriever
from tests.unit.test_utils import cleanup_async_resource


@pytest.mark.asyncio
async def test_connection():
    """Test the database connection and the worker roster table."""
    print("🔍 Testing database connection...")

    sql_retriever = None

    try:
        # Test SQL retriever
        sql_retriever = SQLRetriever()
        await sql_retriever.initialize()
        print("✅ SQL Retriever initialized")

        # Test simple query
        result = await sql_retriever.fetch_one("SELECT 1 as test")
        print(f"✅ Simple query result: {result}")

        # The users table is the worker roster (no logins)
        roster = await sql_retriever.fetch_one("SELECT COUNT(*) AS workers FROM users")
        print(f"✅ Worker roster rows: {roster['workers']}")

        print("✅ Database connection test completed")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback

        traceback.print_exc()
        raise
    finally:
        # Cleanup
        await cleanup_async_resource(sql_retriever, "close")


if __name__ == "__main__":
    asyncio.run(test_connection())
