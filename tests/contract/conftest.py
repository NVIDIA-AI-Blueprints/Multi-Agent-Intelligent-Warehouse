# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Contract test configuration.

Ensures local package sources take precedence over installed packages so
that in-development changes to maiw_models, maiw_mcp, maiw_agents, and the
nemoclaw integration are tested, not the previously-installed versions.

This conftest runs before collection in tests/contract/, which is the
earliest hook that can inject path changes.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]

_LOCAL_PACKAGES = [
    str(_REPO / "packages" / "maiw-models"),
    str(_REPO / "packages" / "maiw-mcp"),
    str(_REPO / "packages" / "maiw-agents"),
    str(_REPO / "integrations"),
]

# Insert local package paths at the FRONT of sys.path so they shadow
# any installed versions.  This is the contract-test equivalent of
# ``pip install -e .`` — it lets us test in-development code without
# reinstalling on every edit.
for _p in reversed(_LOCAL_PACKAGES):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# NOTE: this conftest deliberately does NOT purge ``maiw_*`` entries from
# ``sys.modules``.  CI installs every maiw-* package editable from this
# checkout (``pip install -e packages/...``), so an already-imported module is
# already the local source.  Purging forced a second import of the same files
# under the same names, giving two distinct class objects (e.g. two
# ``SOPStep`` classes) whenever another directory's tests had been collected
# first — pydantic then rejected instances of the "old" class (NEW-P1-04).
