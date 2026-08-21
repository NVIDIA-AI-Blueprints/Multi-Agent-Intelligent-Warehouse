# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Exceptions raised by the state assembly layer."""

from __future__ import annotations


class StateAssemblyError(RuntimeError):
    """
    Raised when the WarehouseStateProvider fails to assemble state.

    Wraps the underlying exception and annotates it with the domain that
    failed so callers can decide whether to propagate or continue with
    partial state.
    """

    def __init__(self, domain: str, message: str, cause: Exception | None = None) -> None:
        self.domain = domain
        self.cause = cause
        super().__init__(f"[{domain}] {message}")


class StateFreshnessError(RuntimeError):
    """
    Raised when required state is present but too stale for the caller.

    The DecisionEngine raises this when a WarehouseStateSnapshot component
    exceeds the ``max_age_ms`` threshold declared in ``StateRequirements``.
    """

    def __init__(self, domain: str, age_ms: int, max_age_ms: int) -> None:
        self.domain = domain
        self.age_ms = age_ms
        self.max_age_ms = max_age_ms
        super().__init__(
            f"[{domain}] State is stale: age_ms={age_ms} exceeds max_age_ms={max_age_ms}"
        )
