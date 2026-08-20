# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Authentication configuration for MCP server connections.

Phase 2 supports bearer token auth via environment variable.
Future phases will add OAuth 2.0 via the official MCP auth extensions
(mcp.client.auth.oauth2).
"""

from __future__ import annotations

import os


class MCPAuthConfig:
    """Auth credentials injected into MCP HTTP request headers."""

    def __init__(
        self,
        api_key: str | None = None,
        api_key_env_var: str = "MAIW_MCP_API_KEY",
    ) -> None:
        self._api_key = api_key or os.getenv(api_key_env_var)

    @property
    def headers(self) -> dict[str, str]:
        """Return HTTP headers to include in MCP requests."""
        if self._api_key:
            return {"Authorization": f"Bearer {self._api_key}"}
        return {}

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)


_no_auth = MCPAuthConfig()


def get_default_auth() -> MCPAuthConfig:
    """Return the process-level auth config (reads MAIW_MCP_API_KEY from env)."""
    return _no_auth
