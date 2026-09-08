# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Package boundary architecture tests.

These tests enforce dependency constraints so that CI catches regressions
before they accumulate. They scan pyproject.toml files rather than the
import graph — import-graph scanning is expensive and pyproject.toml is
the canonical dependency declaration.

Invariants tested:
  I1. maiw-contracts has zero maiw-* dependencies.
  I2. maiw-mcp/contracts/ directory has been deleted (no tombstone files).
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]


class TestMaiwContractsBoundary:
    """maiw-contracts must be governance-independent: pydantic only."""

    def test_maiw_contracts_has_no_maiw_deps(self):
        pyproject = REPO_ROOT / "packages" / "maiw-contracts" / "pyproject.toml"
        assert pyproject.exists(), f"pyproject.toml not found: {pyproject}"
        content = pyproject.read_text()

        # Extract only the dependencies block to avoid matching package name/description
        deps_match = re.search(r"dependencies\s*=\s*\[(.*?)\]", content, re.DOTALL)
        deps_block = deps_match.group(1) if deps_match else ""
        maiw_deps = re.findall(r'"maiw-[^"]*"', deps_block)
        assert maiw_deps == [], (
            "maiw-contracts must have zero maiw-* dependencies "
            f"(packages/maiw-contracts/pyproject.toml). Found: {maiw_deps}"
        )

    def test_maiw_mcp_contracts_directory_deleted(self):
        contracts_dir = REPO_ROOT / "packages" / "maiw-mcp" / "maiw_mcp" / "contracts"
        assert not contracts_dir.exists(), (
            "packages/maiw-mcp/maiw_mcp/contracts/ must not exist — "
            "domain contracts have moved to maiw-contracts. "
            "Delete the directory and all tombstone files."
        )
