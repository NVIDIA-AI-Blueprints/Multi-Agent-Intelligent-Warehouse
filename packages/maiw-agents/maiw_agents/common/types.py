# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Shared types for maiw-agents.

SearchContext is a local copy of src.retrieval.hybrid_retriever.SearchContext so
that maiw_agents has zero src.* imports while preserving the same 5-field contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class SearchContext:
    """Context for hybrid-retriever search operations."""

    query: str
    search_type: str = "hybrid"  # "structured", "vector", "hybrid"
    filters: Optional[Dict[str, Any]] = None
    limit: int = 10
    score_threshold: float = 0.0
