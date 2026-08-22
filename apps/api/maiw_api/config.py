# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Application settings for the MAIW API.

All configuration is read from environment variables.  Defaults are chosen
to be safe for local development — production deployments must supply values
for all settings without defaults.
"""

from __future__ import annotations

import os


def _bool(key: str, default: bool = False) -> bool:
    return os.getenv(key, str(default)).lower() in ("1", "true", "yes")


def _int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


class Settings:
    """Reads configuration from the process environment at access time."""

    # ── API metadata ──────────────────────────────────────────────────────────
    @property
    def app_title(self) -> str:
        return os.getenv("MAIW_APP_TITLE", "Multi-Agent Intelligent Warehouse API")

    @property
    def app_version(self) -> str:
        return os.getenv("MAIW_APP_VERSION", "0.1.0")

    @property
    def app_description(self) -> str:
        return "MAIW canonical API — STATE → REASON → PROPOSE → DECIDE → EXECUTE → MCP"

    # ── Server ────────────────────────────────────────────────────────────────
    @property
    def host(self) -> str:
        return os.getenv("MAIW_API_HOST", "0.0.0.0")

    @property
    def port(self) -> int:
        return _int("MAIW_API_PORT", 8001)

    @property
    def reload(self) -> bool:
        return _bool("MAIW_API_RELOAD", False)

    # ── CORS ──────────────────────────────────────────────────────────────────
    @property
    def cors_origins(self) -> list[str]:
        raw = os.getenv("MAIW_CORS_ORIGINS", "*")
        return [o.strip() for o in raw.split(",") if o.strip()]

    @property
    def cors_allow_credentials(self) -> bool:
        return _bool("MAIW_CORS_ALLOW_CREDENTIALS", False)

    # ── Security ──────────────────────────────────────────────────────────────
    @property
    def secret_key(self) -> str:
        return os.getenv("SECRET_KEY", "dev-insecure-key-change-in-production")

    # ── MCP server URLs (read-only mirror — bootstrap uses these via os.getenv) ──
    @property
    def mcp_inventory_url(self) -> str | None:
        return os.getenv("MAIW_MCP_SERVER_INVENTORY_URL")

    @property
    def mcp_equipment_url(self) -> str | None:
        return os.getenv("MAIW_MCP_SERVER_EQUIPMENT_URL")

    @property
    def mcp_labor_url(self) -> str | None:
        return os.getenv("MAIW_MCP_SERVER_LABOR_URL")

    @property
    def mcp_wave_url(self) -> str | None:
        return os.getenv("MAIW_MCP_SERVER_WAVE_URL")

    # ── Rate limiting ─────────────────────────────────────────────────────────
    @property
    def rate_limit_requests(self) -> int:
        return _int("MAIW_RATE_LIMIT_REQUESTS", 100)

    @property
    def rate_limit_window_seconds(self) -> int:
        return _int("MAIW_RATE_LIMIT_WINDOW_SECONDS", 60)

    # ── Request limits ────────────────────────────────────────────────────────
    @property
    def max_request_size_bytes(self) -> int:
        return _int("MAIW_MAX_REQUEST_SIZE_BYTES", 10 * 1024 * 1024)  # 10 MB


settings = Settings()
