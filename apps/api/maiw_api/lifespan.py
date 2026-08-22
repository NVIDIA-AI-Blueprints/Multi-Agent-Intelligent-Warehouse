# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
FastAPI lifespan — startup and shutdown logic for the MAIW API.

The lifespan assembles the MAIWRuntime once and stores it on
``app.state.runtime`` so that routers can retrieve it via the
``get_runtime`` dependency.

Usage in app.py:

    from maiw_api.lifespan import lifespan
    app = FastAPI(lifespan=lifespan)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from maiw_api.bootstrap import get_runtime

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the runtime on startup; release resources on shutdown."""
    logger.info("MAIW API: starting up...")

    runtime = await get_runtime()
    app.state.runtime = runtime

    logger.info(
        "MAIW API: startup complete — "
        "equipment_agent=%s, operations_agent=%s, safety_agent=%s, "
        "mcp_inventory=%s, mcp_equipment=%s, mcp_labor=%s, mcp_wave=%s",
        runtime.equipment_agent is not None,
        runtime.operations_agent is not None,
        runtime.safety_agent is not None,
        runtime.mcp_inventory_available,
        runtime.mcp_equipment_available,
        runtime.mcp_labor_available,
        runtime.mcp_wave_available,
    )

    yield

    logger.info("MAIW API: shutting down...")
