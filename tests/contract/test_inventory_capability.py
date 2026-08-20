# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Contract tests for the vendor-neutral inventory capability.

These tests validate that:
  1. The inventory contracts (Pydantic v2 models) are correctly defined.
  2. InventoryLookupSkill uses the client correctly.
  3. Any InventoryProvider implementation satisfies the contract.
  4. The MAIWInventoryAdapter correctly maps MAIW backend data.

Running with different providers
---------------------------------
Currently tested:
  - MockInventoryProvider (in-memory, no dependencies)

Future additions (same test file, parameterised):
  - MAIWInventoryAdapter (against real PostgreSQL)
  - SAPEWMAdapter
  - ManhattanAdapter
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from maiw_mcp.contracts.inventory import (
    INVENTORY_GET_METADATA,
    INVENTORY_LOCATE_METADATA,
    InventoryLocation,
    InventoryLookupRequest,
    InventoryLookupResult,
)
from maiw_mcp.errors import (
    BackendUnavailable,
    CapabilityNotFound,
    MCPContractError,
    MCPToolError,
    MCPUnavailable,
)
from maiw_mcp.testing.fixtures import make_inventory_result


# ── Contract: CapabilityMetadata ──────────────────────────────────────────────


class TestCapabilityMetadata:
    def test_inventory_get_name_is_semantic(self):
        assert INVENTORY_GET_METADATA.name == "warehouse.inventory.get"

    def test_inventory_locate_name_is_semantic(self):
        assert INVENTORY_LOCATE_METADATA.name == "warehouse.inventory.locate"

    def test_inventory_get_is_read_only(self):
        assert INVENTORY_GET_METADATA.side_effect == "read"
        assert INVENTORY_GET_METADATA.idempotent is True

    def test_inventory_get_is_low_risk(self):
        assert INVENTORY_GET_METADATA.risk == "low"

    def test_inventory_get_has_permission(self):
        assert INVENTORY_GET_METADATA.required_permission == "inventory:read"

    def test_inventory_get_version_is_integer(self):
        assert isinstance(INVENTORY_GET_METADATA.version, int)
        assert INVENTORY_GET_METADATA.version >= 1

    def test_metadata_name_follows_namespace_pattern(self):
        import re
        pattern = re.compile(r"^warehouse\.[a-z_]+\.[a-z_]+$")
        assert pattern.match(INVENTORY_GET_METADATA.name)
        assert pattern.match(INVENTORY_LOCATE_METADATA.name)


# ── Contract: InventoryLookupRequest ──────────────────────────────────────────


class TestInventoryLookupRequest:
    def test_sku_is_required(self):
        with pytest.raises(Exception):
            InventoryLookupRequest()  # no sku

    def test_warehouse_id_defaults_to_default(self):
        req = InventoryLookupRequest(sku="SKU-001")
        assert req.warehouse_id == "default"

    def test_location_defaults_to_none(self):
        req = InventoryLookupRequest(sku="SKU-001")
        assert req.location is None

    def test_location_can_be_specified(self):
        req = InventoryLookupRequest(sku="SKU-001", location="A-01-03")
        assert req.location == "A-01-03"

    def test_empty_sku_is_rejected(self):
        with pytest.raises(Exception):
            InventoryLookupRequest(sku="")

    def test_model_dump_excludes_none_location(self):
        req = InventoryLookupRequest(sku="SKU-001")
        dumped = req.model_dump(exclude_none=True)
        assert "location" not in dumped
        assert dumped["sku"] == "SKU-001"


# ── Contract: InventoryLookupResult ───────────────────────────────────────────


class TestInventoryLookupResult:
    def test_fixture_is_valid(self):
        result = make_inventory_result()
        assert result.sku == "SKU-001"
        assert result.total_available == 100
        assert len(result.locations) == 1
        assert result.is_low_stock is False

    def test_low_stock_when_quantity_at_reorder(self):
        result = make_inventory_result(quantity=10, reorder_point=10)
        assert result.is_low_stock is True

    def test_low_stock_when_quantity_below_reorder(self):
        result = make_inventory_result(quantity=5, reorder_point=10)
        assert result.is_low_stock is True

    def test_not_low_stock_when_above_reorder(self):
        result = make_inventory_result(quantity=100, reorder_point=10)
        assert result.is_low_stock is False

    def test_source_is_present(self):
        result = make_inventory_result(source="test-backend")
        assert result.source == "test-backend"

    def test_result_serializes_to_json(self):
        result = make_inventory_result()
        serialized = result.model_dump(mode="json")
        assert isinstance(serialized, dict)
        assert serialized["sku"] == "SKU-001"

    def test_result_round_trips_through_json(self):
        original = make_inventory_result()
        as_json = json.dumps(original.model_dump(mode="json"), default=str)
        restored = InventoryLookupResult.model_validate_json(as_json)
        assert restored.sku == original.sku
        assert restored.total_available == original.total_available


# ── Contract: InventoryLocation ───────────────────────────────────────────────


class TestInventoryLocation:
    def test_quantity_on_hand_property(self):
        loc = InventoryLocation(
            location_id="A-01",
            quantity_available=80,
            quantity_reserved=20,
            reorder_point=10,
        )
        assert loc.quantity_on_hand == 100

    def test_default_quantity_reserved_is_zero(self):
        loc = InventoryLocation(
            location_id="A-01", quantity_available=50, reorder_point=5
        )
        assert loc.quantity_reserved == 0


# ── Contract: InventoryLookupSkill ────────────────────────────────────────────


class TestInventoryLookupSkill:
    """Skill contract tests using a mock client — no network required."""

    def _make_skill(self, result: InventoryLookupResult | None = None):
        from src.api.skills.inventory import InventoryLookupSkill

        mock_client = MagicMock()
        fixture = result or make_inventory_result()
        mock_client.invoke = AsyncMock(
            return_value=fixture.model_dump(mode="json")
        )
        return InventoryLookupSkill(mock_client), mock_client

    def test_execute_returns_typed_result(self):
        skill, _ = self._make_skill()
        request = InventoryLookupRequest(sku="SKU-001")
        result = asyncio.run(skill.execute(request))
        assert isinstance(result, InventoryLookupResult)
        assert result.sku == "SKU-001"

    def test_execute_invokes_correct_capability(self):
        skill, mock_client = self._make_skill()
        request = InventoryLookupRequest(sku="SKU-001")
        asyncio.run(skill.execute(request))
        call_kwargs = mock_client.invoke.call_args
        assert call_kwargs[0][0] == "warehouse.inventory.get"

    def test_execute_passes_sku_in_payload(self):
        skill, mock_client = self._make_skill()
        request = InventoryLookupRequest(sku="SKU-999")
        asyncio.run(skill.execute(request))
        payload = mock_client.invoke.call_args[0][1]
        assert payload["sku"] == "SKU-999"

    def test_execute_propagates_trace_id(self):
        skill, mock_client = self._make_skill()
        request = InventoryLookupRequest(sku="SKU-001")
        asyncio.run(skill.execute(request, trace_id="trace-xyz"))
        kwargs = mock_client.invoke.call_args[1]
        assert kwargs.get("trace_id") == "trace-xyz"

    def test_execute_raises_mcp_contract_error_on_invalid_json(self):
        from src.api.skills.inventory import InventoryLookupSkill

        mock_client = MagicMock()
        mock_client.invoke = AsyncMock(return_value={"not_a_valid_field": True})
        skill = InventoryLookupSkill(mock_client)
        with pytest.raises(MCPContractError):
            asyncio.run(skill.execute(InventoryLookupRequest(sku="SKU-001")))

    def test_execute_propagates_mcp_unavailable(self):
        from src.api.skills.inventory import InventoryLookupSkill

        mock_client = MagicMock()
        mock_client.invoke = AsyncMock(side_effect=MCPUnavailable("server down"))
        skill = InventoryLookupSkill(mock_client)
        with pytest.raises(MCPUnavailable):
            asyncio.run(skill.execute(InventoryLookupRequest(sku="SKU-001")))


# ── Contract: MockInventoryProvider ───────────────────────────────────────────


class TestMockInventoryProvider:
    def test_returns_fixture_for_unknown_sku(self):
        from mcp_servers.inventory.provider import MockInventoryProvider

        provider = MockInventoryProvider()
        result = asyncio.run(
            provider.get_inventory(InventoryLookupRequest(sku="UNKNOWN"))
        )
        assert result.sku == "UNKNOWN"
        assert result.source == "mock"

    def test_returns_configured_result_for_known_sku(self):
        from mcp_servers.inventory.provider import MockInventoryProvider

        fixture = make_inventory_result(sku="CONFIGURED", quantity=42)
        provider = MockInventoryProvider(data={"CONFIGURED": fixture})
        result = asyncio.run(
            provider.get_inventory(InventoryLookupRequest(sku="CONFIGURED"))
        )
        assert result.total_available == 42

    def test_is_inventory_provider_protocol(self):
        from mcp_servers.inventory.provider import MockInventoryProvider, InventoryProvider

        provider = MockInventoryProvider()
        assert isinstance(provider, InventoryProvider)


# ── Contract: MAIWInventoryAdapter ────────────────────────────────────────────


class TestMAIWInventoryAdapter:
    """Tests for the adapter that wraps the existing MAIW InventoryQueries."""

    def _make_adapter(self, sku: str, quantity: int, location: str = "A-01"):
        from mcp_servers.inventory.adapters.maiw_backend import MAIWInventoryAdapter

        class FakeInventoryItem:
            def __init__(self):
                self.sku = sku
                self.name = f"Item {sku}"
                self.quantity = quantity
                self.location = location
                self.reorder_point = 10
                self.updated_at = "2026-08-20T12:00:00"

        fake_queries = MagicMock()
        fake_queries.get_item_by_sku = AsyncMock(return_value=FakeInventoryItem())
        return MAIWInventoryAdapter(fake_queries)

    def test_adapter_maps_quantity_to_total_available(self):
        adapter = self._make_adapter("SKU-001", 50)
        result = asyncio.run(
            adapter.get_inventory(InventoryLookupRequest(sku="SKU-001"))
        )
        assert result.total_available == 50

    def test_adapter_sets_source_to_maiw_backend(self):
        adapter = self._make_adapter("SKU-001", 50)
        result = asyncio.run(
            adapter.get_inventory(InventoryLookupRequest(sku="SKU-001"))
        )
        assert result.source == "maiw-backend"

    def test_adapter_sets_low_stock_when_quantity_at_reorder(self):
        adapter = self._make_adapter("SKU-001", 10)  # quantity == reorder_point
        result = asyncio.run(
            adapter.get_inventory(InventoryLookupRequest(sku="SKU-001"))
        )
        assert result.is_low_stock is True

    def test_adapter_raises_backend_unavailable_when_sku_missing(self):
        from mcp_servers.inventory.adapters.maiw_backend import MAIWInventoryAdapter

        queries = MagicMock()
        queries.get_item_by_sku = AsyncMock(return_value=None)
        adapter = MAIWInventoryAdapter(queries)
        with pytest.raises(BackendUnavailable):
            asyncio.run(adapter.get_inventory(InventoryLookupRequest(sku="MISSING")))

    def test_adapter_raises_backend_unavailable_on_sql_error(self):
        from mcp_servers.inventory.adapters.maiw_backend import MAIWInventoryAdapter

        queries = MagicMock()
        queries.get_item_by_sku = AsyncMock(side_effect=Exception("DB connection lost"))
        adapter = MAIWInventoryAdapter(queries)
        with pytest.raises(BackendUnavailable):
            asyncio.run(adapter.get_inventory(InventoryLookupRequest(sku="SKU-001")))

    def test_adapter_preserves_warehouse_id(self):
        adapter = self._make_adapter("SKU-001", 50)
        result = asyncio.run(
            adapter.get_inventory(
                InventoryLookupRequest(sku="SKU-001", warehouse_id="WH-42")
            )
        )
        assert result.warehouse_id == "WH-42"
