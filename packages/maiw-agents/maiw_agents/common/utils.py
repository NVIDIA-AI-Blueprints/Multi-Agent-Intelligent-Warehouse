# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Shared utilities for maiw-agents (no src.* imports)."""

from __future__ import annotations

import json
import re
from typing import Any


def sanitize_prompt_input(value: Any) -> Any:
    """
    Sanitize user input before embedding in LLM prompts.

    Strips common template-injection markers (double braces, format strings)
    from string inputs; non-strings are returned as-is. This is a lightweight
    defense-in-depth measure; primary prompt-injection defense is in the
    application layer (NeMo Guardrails).
    """
    if not isinstance(value, str):
        return value
    # Collapse {{ / }} to avoid accidental .format() expansion
    sanitized = value.replace("{", "{{").replace("}", "}}")
    # Limit length to prevent prompt stuffing
    return sanitized[:8000]
