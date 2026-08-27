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

import asyncio
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from maiw_api.bootstrap import get_runtime
from maiw_api.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the runtime on startup; release resources on shutdown."""
    logger.info("MAIW API: starting up...")
    load_dotenv()

    # Bound startup so a hung dependency (NIM, DB) cannot block indefinitely.
    try:
        runtime = await asyncio.wait_for(
            get_runtime(),
            timeout=settings.startup_timeout_seconds,
        )
    except asyncio.TimeoutError:
        logger.error(
            "MAIW API: startup timed out after %.0fs — "
            "proceeding with partial runtime (some capabilities unavailable)",
            settings.startup_timeout_seconds,
        )
        # get_runtime() caches its singleton; retrieve whatever was assembled.
        from maiw_api.bootstrap import _runtime as _partial  # noqa: PLC0415

        runtime = _partial  # may be None if assembly failed entirely

    app.state.runtime = runtime

    logger.info(
        "MAIW API: startup complete — "
        "equipment_agent=%s, operations_agent=%s, safety_agent=%s, "
        "mcp_inventory=%s, mcp_equipment=%s, mcp_labor=%s, mcp_wave=%s",
        runtime.equipment_agent is not None if runtime else False,
        runtime.operations_agent is not None if runtime else False,
        runtime.safety_agent is not None if runtime else False,
        runtime.mcp_inventory_available if runtime else False,
        runtime.mcp_equipment_available if runtime else False,
        runtime.mcp_labor_available if runtime else False,
        runtime.mcp_wave_available if runtime else False,
    )

    yield

    logger.info("MAIW API: shutting down...")
    # MAIWMCPClient is per-call / context-managed — it has no persistent
    # connection and no aclose() method.  Close the NIM httpx clients instead.
    try:
        from maiw_models.providers.nim_client import close_nim_client  # noqa: PLC0415

        await close_nim_client()
    except Exception as exc:
        logger.warning("NIM client close error: %s", exc)
