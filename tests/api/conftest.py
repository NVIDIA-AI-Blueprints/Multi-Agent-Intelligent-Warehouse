# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
tests/api/conftest.py

Stub native packages that are not installed in the CI test environment.
These stubs must be in sys.modules before any src.* or maiw_api.* code is
imported so that module-level import chains don't blow up at collection time.

Packages stubbed here:
  asyncpg      — PostgreSQL driver (requires C extension)
  redis        — Redis client (requires a running server)
  redis.asyncio — async Redis sub-package
  pymilvus     — Milvus vector-DB client
  bcrypt       — password hashing (C extension)

Actual database / cache / vector-search calls are patched at the individual
test or fixture level using unittest.mock.
"""

import sys
from unittest.mock import MagicMock

_STUBS = [
    "asyncpg",
    "redis",
    "redis.asyncio",
    "pymilvus",
    "bcrypt",
]

for _mod in _STUBS:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()
