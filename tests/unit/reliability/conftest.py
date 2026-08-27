# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Reliability test package configuration.

Adds this directory to sys.path so that `fault_framework` package is importable
from any test in tests/unit/reliability/.
"""

from __future__ import annotations

import os
import sys

# Allow `from fault_framework.models import ...` in sibling test files
_HERE = os.path.dirname(__file__)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

# Allow `from maiw_api...` imports (apps/api entrypoint)
_REPO_ROOT = os.path.join(_HERE, "../../..")
_API_PATH = os.path.normpath(os.path.join(_REPO_ROOT, "apps/api"))
if _API_PATH not in sys.path:
    sys.path.insert(0, _API_PATH)
