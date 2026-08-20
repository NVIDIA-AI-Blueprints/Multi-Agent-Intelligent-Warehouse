# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
maiw-mcp — Shared MCP v2 client infrastructure for MAIW warehouse agents.

Provides:
  - Vendor-neutral capability contracts (Pydantic v2)
  - Official MCP SDK client wrapper with correlation telemetry
  - Capability registry (semantic name → server URL)
  - In-process testing utilities (mock server, conformance suite)

Usage in agents:
    from maiw_mcp.client.client import MAIWMCPClient
    from maiw_mcp.registry.registry import CapabilityRegistry
    from maiw_mcp.contracts.inventory import InventoryLookupRequest, InventoryLookupResult

    registry = CapabilityRegistry.from_env()
    client = MAIWMCPClient(registry)
    result_dict = await client.invoke("warehouse.inventory.get", {"sku": "SKU-001"})
"""

from .errors import (
    MAIWMCPError,
    MCPUnavailable,
    MCPTimeout,
    MCPToolError,
    MCPContractError,
    CapabilityNotFound,
    CapabilityPermissionDenied,
    BackendUnavailable,
)

__all__ = [
    "MAIWMCPError",
    "MCPUnavailable",
    "MCPTimeout",
    "MCPToolError",
    "MCPContractError",
    "CapabilityNotFound",
    "CapabilityPermissionDenied",
    "BackendUnavailable",
]
