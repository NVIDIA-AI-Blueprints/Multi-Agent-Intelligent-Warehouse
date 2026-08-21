# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Typed error hierarchy for MCP capability calls.

All errors raised by MAIWMCPClient and InventoryLookupSkill are subclasses of
MAIWMCPError.  Agents catch these typed errors instead of bare exceptions.
"""

from __future__ import annotations


class MAIWMCPError(Exception):
    """Base class for all MAIW MCP errors."""


class MCPUnavailable(MAIWMCPError):
    """MCP server is unreachable or transport-level connection failed."""


class MCPTimeout(MAIWMCPError):
    """MCP call timed out before the server responded."""


class MCPToolError(MAIWMCPError):
    """Server returned a tool-level error (isError=True in CallToolResult)."""


class MCPContractError(MAIWMCPError):
    """Response could not be validated against the expected capability contract."""


class CapabilityNotFound(MAIWMCPError):
    """No MCP server is registered for the requested capability name."""


class CapabilityPermissionDenied(MAIWMCPError):
    """Caller lacks the required permission for the capability."""


class BackendUnavailable(MAIWMCPError):
    """The warehouse backend (DB, WMS, ERP) is unavailable or returned an error."""
