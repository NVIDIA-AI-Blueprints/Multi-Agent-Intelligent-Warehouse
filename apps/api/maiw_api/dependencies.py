# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
FastAPI dependency helpers for the MAIW API.

All routers import ``get_runtime`` from here rather than from bootstrap
directly, keeping the dependency injection surface small and mockable in tests.

Usage in a router:

    from maiw_api.dependencies import get_runtime
    from maiw_api.bootstrap import MAIWRuntime

    @router.get("/example")
    async def example(runtime: MAIWRuntime = Depends(get_runtime)):
        ...
"""

from __future__ import annotations

from fastapi import Request

from maiw_api.bootstrap import MAIWRuntime


async def get_runtime(request: Request) -> MAIWRuntime:
    """
    Return the MAIWRuntime stored on ``app.state.runtime``.

    The lifespan function sets ``app.state.runtime`` at startup.
    Tests can override it by setting ``app.state.runtime`` directly
    before calling the test client.
    """
    return request.app.state.runtime
