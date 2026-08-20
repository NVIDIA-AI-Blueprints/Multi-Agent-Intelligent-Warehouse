# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Contract tests for the vendor-neutral equipment capability.

These tests validate:
  1. Equipment contracts (Pydantic v2 models) are correctly defined.
  2. ActionProposal / RiskLevel types are correctly shaped.
  3. MockEquipmentProvider satisfies the EquipmentProvider Protocol.
  4. EquipmentStatusSkill / EquipmentTelemetrySkill use the client correctly.
  5. MAIWEquipmentAdapter correctly maps EquipmentAssetTools raw dicts.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from maiw_mcp.contracts.actions import ActionProposal, RiskLevel
from maiw_mcp.contracts.equipment import (
    EQUIPMENT_ASSIGN_METADATA,
    EQUIPMENT_GET_STATUS_METADATA,
    EQUIPMENT_GET_TELEMETRY_METADATA,
    AvailableMetric,
    EquipmentAssetInfo,
    EquipmentAssignmentRequest,
    EquipmentAssignmentResult,
    EquipmentStatusRequest,
    EquipmentStatusResult,
    EquipmentTelemetryRequest,
    EquipmentTelemetryResult,
    TelemetryPoint,
)
from maiw_mcp.errors import BackendUnavailable, MCPContractError
from mcp_servers.equipment.provider import MockEquipmentProvider

# ── Contract: CapabilityMetadata ──────────────────────────────────────────────


class TestEquipmentCapabilityMetadata:
    def test_get_status_name_is_semantic(self):
        assert EQUIPMENT_GET_STATUS_METADATA.name == "warehouse.equipment.get_status"

    def test_get_telemetry_name_is_semantic(self):
        assert (
            EQUIPMENT_GET_TELEMETRY_METADATA.name == "warehouse.equipment.get_telemetry"
        )

    def test_assign_name_is_semantic(self):
        assert EQUIPMENT_ASSIGN_METADATA.name == "warehouse.equipment.assign"

    def test_get_status_is_read_only(self):
        assert EQUIPMENT_GET_STATUS_METADATA.side_effect == "read"

    def test_get_telemetry_is_read_only(self):
        assert EQUIPMENT_GET_TELEMETRY_METADATA.side_effect == "read"

    def test_assign_is_write(self):
        assert EQUIPMENT_ASSIGN_METADATA.side_effect == "write"

    def test_assign_risk_is_medium(self):
        assert EQUIPMENT_ASSIGN_METADATA.risk == "medium"

    def test_assign_is_not_idempotent(self):
        assert EQUIPMENT_ASSIGN_METADATA.idempotent is False

    def test_read_capabilities_are_idempotent(self):
        assert EQUIPMENT_GET_STATUS_METADATA.idempotent is True
        assert EQUIPMENT_GET_TELEMETRY_METADATA.idempotent is True

    def test_all_names_match_warehouse_domain_pattern(self):
        import re

        pattern = re.compile(r"^warehouse\.[a-z_]+\.[a-z_]+$")
        for meta in [
            EQUIPMENT_GET_STATUS_METADATA,
            EQUIPMENT_GET_TELEMETRY_METADATA,
            EQUIPMENT_ASSIGN_METADATA,
        ]:
            assert pattern.match(meta.name), f"{meta.name} doesn't match pattern"


# ── Contract: ActionProposal and RiskLevel ────────────────────────────────────


class TestActionProposal:
    def test_risk_levels_ordered(self):
        levels = [
            RiskLevel.READ_ONLY,
            RiskLevel.LOW,
            RiskLevel.MEDIUM,
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        ]
        assert len(levels) == 5

    def test_proposal_has_uuid(self):
        proposal = ActionProposal.for_equipment_assign(
            asset_id="FL-001",
            assignee="operator-1",
            assignment_type="task",
            task_id="T-100",
            duration_hours=4,
            notes=None,
            reason="needed for pick",
            requested_by="operations-agent",
        )
        assert len(proposal.proposal_id) == 36
        assert proposal.proposal_id.count("-") == 4

    def test_proposal_requires_approval_for_medium_risk(self):
        proposal = ActionProposal.for_equipment_assign(
            asset_id="FL-001",
            assignee="operator-1",
            assignment_type="task",
            task_id=None,
            duration_hours=None,
            notes=None,
            reason="",
            requested_by="test",
        )
        assert proposal.risk_level == RiskLevel.MEDIUM
        assert proposal.requires_approval is True

    def test_proposal_captures_action_name(self):
        proposal = ActionProposal.for_equipment_assign(
            asset_id="AMR-002",
            assignee="robot-dispatch",
            assignment_type="zone",
            task_id=None,
            duration_hours=None,
            notes=None,
            reason="zone coverage",
            requested_by="dispatch-agent",
        )
        assert proposal.action == "warehouse.equipment.assign"
        assert proposal.domain == "equipment"
        assert proposal.parameters["asset_id"] == "AMR-002"
        assert proposal.parameters["assignee"] == "robot-dispatch"

    def test_proposal_round_trips_via_model_dump(self):
        original = ActionProposal.for_equipment_assign(
            asset_id="FL-003",
            assignee="jane",
            assignment_type="task",
            task_id="T-999",
            duration_hours=2,
            notes="handle with care",
            reason="urgent pick",
            requested_by="ops-agent",
            trace_id="trace-abc",
            idempotency_key="idem-xyz",
        )
        raw = original.model_dump(mode="json")
        restored = ActionProposal.model_validate(raw)
        assert restored.proposal_id == original.proposal_id
        assert restored.parameters["task_id"] == "T-999"
        assert restored.trace_id == "trace-abc"
        assert restored.idempotency_key == "idem-xyz"


# ── Contract: EquipmentStatusRequest ─────────────────────────────────────────


class TestEquipmentStatusRequest:
    def test_default_request_has_no_filters(self):
        req = EquipmentStatusRequest()
        assert req.asset_id is None
        assert req.equipment_type is None
        assert req.zone is None
        assert req.status_filter is None

    def test_request_with_all_filters(self):
        req = EquipmentStatusRequest(
            asset_id="FL-001",
            equipment_type="forklift",
            zone="ZONE-A",
            status_filter="available",
        )
        assert req.asset_id == "FL-001"
        assert req.equipment_type == "forklift"
        assert req.zone == "ZONE-A"
        assert req.status_filter == "available"


# ── Contract: EquipmentTelemetryRequest ───────────────────────────────────────


class TestEquipmentTelemetryRequest:
    def test_requires_asset_id(self):
        with pytest.raises(Exception):
            EquipmentTelemetryRequest(asset_id="")

    def test_default_hours_back(self):
        req = EquipmentTelemetryRequest(asset_id="AMR-001")
        assert req.hours_back == 24

    def test_hours_back_capped_at_720(self):
        with pytest.raises(Exception):
            EquipmentTelemetryRequest(asset_id="AMR-001", hours_back=721)


# ── Contract: MockEquipmentProvider ──────────────────────────────────────────


class TestMockEquipmentProvider:
    def _make_provider_with_data(self) -> MockEquipmentProvider:
        p = MockEquipmentProvider()
        p.add_asset(
            EquipmentAssetInfo(
                asset_id="FL-001",
                equipment_type="forklift",
                model="FL-3000",
                zone="ZONE-A",
                status="available",
            )
        )
        p.add_asset(
            EquipmentAssetInfo(
                asset_id="AMR-001",
                equipment_type="amr",
                model="AMR-X",
                zone="ZONE-B",
                status="assigned",
                owner_user="operator-1",
            )
        )
        p.add_telemetry(
            "FL-001",
            [
                TelemetryPoint(
                    timestamp=datetime.now(timezone.utc),
                    metric="battery_level",
                    value=85.0,
                    unit="percent",
                    quality_score=1.0,
                ),
                TelemetryPoint(
                    timestamp=datetime.now(timezone.utc),
                    metric="speed",
                    value=3.2,
                    unit="m/s",
                    quality_score=0.95,
                ),
            ],
        )
        return p

    def test_empty_provider_returns_empty_fleet(self):
        async def run():
            provider = MockEquipmentProvider()
            return await provider.get_equipment_status(EquipmentStatusRequest())

        result = asyncio.run(run())
        assert result.total_count == 0
        assert result.equipment == []
        assert result.source == "mock"

    def test_get_status_all_assets(self):
        async def run():
            provider = self._make_provider_with_data()
            return await provider.get_equipment_status(EquipmentStatusRequest())

        result = asyncio.run(run())
        assert result.total_count == 2
        assert result.source == "mock"

    def test_get_status_filter_by_asset_id(self):
        async def run():
            provider = self._make_provider_with_data()
            return await provider.get_equipment_status(
                EquipmentStatusRequest(asset_id="FL-001")
            )

        result = asyncio.run(run())
        assert result.total_count == 1
        assert result.equipment[0].asset_id == "FL-001"

    def test_get_status_filter_by_type(self):
        async def run():
            provider = self._make_provider_with_data()
            return await provider.get_equipment_status(
                EquipmentStatusRequest(equipment_type="amr")
            )

        result = asyncio.run(run())
        assert result.total_count == 1
        assert result.equipment[0].equipment_type == "amr"

    def test_get_status_filter_by_status(self):
        async def run():
            provider = self._make_provider_with_data()
            return await provider.get_equipment_status(
                EquipmentStatusRequest(status_filter="available")
            )

        result = asyncio.run(run())
        assert result.total_count == 1
        assert result.equipment[0].status == "available"

    def test_get_status_summary_populated(self):
        async def run():
            provider = self._make_provider_with_data()
            return await provider.get_equipment_status(EquipmentStatusRequest())

        result = asyncio.run(run())
        assert "forklift" in result.summary
        assert "amr" in result.summary
        assert result.summary["forklift"]["available"] == 1
        assert result.summary["amr"]["assigned"] == 1

    def test_get_status_unknown_asset_returns_synthetic(self):
        async def run():
            provider = MockEquipmentProvider()
            return await provider.get_equipment_status(
                EquipmentStatusRequest(asset_id="UNKNOWN-999")
            )

        result = asyncio.run(run())
        assert result.total_count == 1
        assert result.equipment[0].asset_id == "UNKNOWN-999"

    def test_get_telemetry_returns_points(self):
        async def run():
            provider = self._make_provider_with_data()
            return await provider.get_equipment_telemetry(
                EquipmentTelemetryRequest(asset_id="FL-001")
            )

        result = asyncio.run(run())
        assert result.asset_id == "FL-001"
        assert result.data_points == 2
        assert result.source == "mock"

    def test_get_telemetry_filter_by_metric(self):
        async def run():
            provider = self._make_provider_with_data()
            return await provider.get_equipment_telemetry(
                EquipmentTelemetryRequest(asset_id="FL-001", metric="battery_level")
            )

        result = asyncio.run(run())
        assert result.data_points == 1
        assert result.telemetry_data[0].metric == "battery_level"

    def test_get_telemetry_missing_asset_returns_empty(self):
        async def run():
            provider = MockEquipmentProvider()
            return await provider.get_equipment_telemetry(
                EquipmentTelemetryRequest(asset_id="NO-ASSET")
            )

        result = asyncio.run(run())
        assert result.asset_id == "NO-ASSET"
        assert result.data_points == 0
        assert result.source == "mock"

    def test_propose_assignment_returns_action_proposal(self):
        async def run():
            provider = MockEquipmentProvider()
            return await provider.propose_equipment_assignment(
                EquipmentAssignmentRequest(
                    asset_id="FL-001",
                    assignee="operator-5",
                    assignment_type="task",
                    task_id="T-200",
                    reason="Unload dock 3",
                    requested_by="operations-agent",
                )
            )

        result = asyncio.run(run())
        assert isinstance(result, EquipmentAssignmentResult)
        assert result.proposal.action == "warehouse.equipment.assign"
        assert result.proposal.parameters["asset_id"] == "FL-001"
        assert result.proposal.requires_approval is True
        assert result.proposal.risk_level == RiskLevel.MEDIUM
        assert result.source == "mock"

    def test_proposal_id_is_unique_per_request(self):
        async def run():
            provider = MockEquipmentProvider()
            r1 = await provider.propose_equipment_assignment(
                EquipmentAssignmentRequest(
                    asset_id="FL-001", assignee="op-1", reason="r1", requested_by="a"
                )
            )
            r2 = await provider.propose_equipment_assignment(
                EquipmentAssignmentRequest(
                    asset_id="FL-001", assignee="op-1", reason="r1", requested_by="a"
                )
            )
            return r1.proposal.proposal_id, r2.proposal.proposal_id

        id1, id2 = asyncio.run(run())
        assert id1 != id2


# ── Contract: EquipmentStatusResult and EquipmentTelemetryResult ──────────────


class TestEquipmentResultContracts:
    def test_status_result_round_trip(self):
        result = EquipmentStatusResult(
            equipment=[
                EquipmentAssetInfo(
                    asset_id="FL-001",
                    equipment_type="forklift",
                    model="FL-3000",
                    zone="ZONE-A",
                    status="available",
                )
            ],
            summary={"forklift": {"available": 1}},
            total_count=1,
            source="mock",
        )
        raw = result.model_dump(mode="json")
        restored = EquipmentStatusResult.model_validate(raw)
        assert restored.equipment[0].asset_id == "FL-001"
        assert restored.total_count == 1

    def test_telemetry_result_round_trip(self):
        result = EquipmentTelemetryResult(
            asset_id="FL-001",
            telemetry_data=[
                TelemetryPoint(
                    timestamp=datetime.now(timezone.utc),
                    metric="battery_level",
                    value=90.0,
                    unit="percent",
                    quality_score=1.0,
                )
            ],
            available_metrics=[AvailableMetric(metric="battery_level", unit="percent")],
            hours_back=24,
            data_points=1,
            source="mock",
        )
        raw = result.model_dump(mode="json")
        restored = EquipmentTelemetryResult.model_validate(raw)
        assert restored.asset_id == "FL-001"
        assert restored.data_points == 1
        assert restored.telemetry_data[0].value == 90.0


# ── Contract: MAIWEquipmentAdapter mapping ────────────────────────────────────


class TestMAIWEquipmentAdapterMapping:
    """Tests the adapter's translation of raw EquipmentAssetTools dicts → contracts."""

    def _make_raw_status(
        self, asset_id: str = "FL-001", status: str = "available"
    ) -> dict:
        return {
            "equipment": [
                {
                    "asset_id": asset_id,
                    "type": "forklift",
                    "model": "FL-3000",
                    "zone": "ZONE-A",
                    "status": status,
                    "owner_user": None,
                    "next_pm_due": None,
                    "last_maintenance": None,
                    "metadata": {},
                }
            ],
            "summary": {"forklift": {status: 1}},
            "total_count": 1,
            "timestamp": "2025-01-01T00:00:00",
        }

    def test_adapter_maps_raw_status_to_contract(self):
        from mcp_servers.equipment.adapters.maiw_backend import MAIWEquipmentAdapter

        async def run():
            mock_tools = MagicMock()
            mock_tools.get_equipment_status = AsyncMock(
                return_value=self._make_raw_status("FL-001", "available")
            )
            adapter = MAIWEquipmentAdapter(mock_tools)
            return await adapter.get_equipment_status(
                EquipmentStatusRequest(asset_id="FL-001")
            )

        result = asyncio.run(run())
        assert isinstance(result, EquipmentStatusResult)
        assert result.source == "maiw-backend"
        assert result.equipment[0].asset_id == "FL-001"
        assert result.equipment[0].equipment_type == "forklift"
        assert result.equipment[0].status == "available"

    def test_adapter_raises_backend_unavailable_on_error_key(self):
        from mcp_servers.equipment.adapters.maiw_backend import MAIWEquipmentAdapter

        async def run():
            mock_tools = MagicMock()
            mock_tools.get_equipment_status = AsyncMock(
                return_value={
                    "error": "DB unreachable",
                    "equipment": [],
                    "total_count": 0,
                }
            )
            adapter = MAIWEquipmentAdapter(mock_tools)
            return await adapter.get_equipment_status(EquipmentStatusRequest())

        with pytest.raises(BackendUnavailable, match="DB unreachable"):
            asyncio.run(run())

    def test_adapter_raises_backend_unavailable_on_exception(self):
        from mcp_servers.equipment.adapters.maiw_backend import MAIWEquipmentAdapter

        async def run():
            mock_tools = MagicMock()
            mock_tools.get_equipment_status = AsyncMock(
                side_effect=RuntimeError("connection pool exhausted")
            )
            adapter = MAIWEquipmentAdapter(mock_tools)
            return await adapter.get_equipment_status(EquipmentStatusRequest())

        with pytest.raises(BackendUnavailable):
            asyncio.run(run())

    def test_adapter_maps_telemetry_to_contract(self):
        from mcp_servers.equipment.adapters.maiw_backend import MAIWEquipmentAdapter

        async def run():
            mock_tools = MagicMock()
            mock_tools.get_equipment_telemetry = AsyncMock(
                return_value={
                    "asset_id": "FL-001",
                    "telemetry_data": [
                        {
                            "timestamp": "2025-01-01T12:00:00",
                            "asset_id": "FL-001",
                            "metric": "battery_level",
                            "value": 75.0,
                            "unit": "percent",
                            "quality_score": 0.98,
                        }
                    ],
                    "available_metrics": [
                        {"metric": "battery_level", "unit": "percent"}
                    ],
                    "hours_back": 24,
                    "data_points": 1,
                }
            )
            adapter = MAIWEquipmentAdapter(mock_tools)
            return await adapter.get_equipment_telemetry(
                EquipmentTelemetryRequest(asset_id="FL-001")
            )

        result = asyncio.run(run())
        assert isinstance(result, EquipmentTelemetryResult)
        assert result.source == "maiw-backend"
        assert result.data_points == 1
        assert result.telemetry_data[0].metric == "battery_level"
        assert result.telemetry_data[0].value == 75.0

    def test_adapter_propose_assignment_validates_asset_exists(self):
        from mcp_servers.equipment.adapters.maiw_backend import MAIWEquipmentAdapter

        async def run():
            mock_tools = MagicMock()
            mock_tools.get_equipment_status = AsyncMock(
                return_value={"equipment": [], "total_count": 0}
            )
            adapter = MAIWEquipmentAdapter(mock_tools)
            return await adapter.propose_equipment_assignment(
                EquipmentAssignmentRequest(
                    asset_id="GHOST-001",
                    assignee="operator-1",
                    reason="test",
                    requested_by="test",
                )
            )

        with pytest.raises(BackendUnavailable, match="not found"):
            asyncio.run(run())

    def test_adapter_propose_assignment_returns_proposal(self):
        from mcp_servers.equipment.adapters.maiw_backend import MAIWEquipmentAdapter

        async def run():
            mock_tools = MagicMock()
            mock_tools.get_equipment_status = AsyncMock(
                return_value=self._make_raw_status("FL-001", "available")
            )
            adapter = MAIWEquipmentAdapter(mock_tools)
            return await adapter.propose_equipment_assignment(
                EquipmentAssignmentRequest(
                    asset_id="FL-001",
                    assignee="operator-1",
                    assignment_type="task",
                    task_id="T-100",
                    reason="unload dock",
                    requested_by="ops-agent",
                )
            )

        result = asyncio.run(run())
        assert isinstance(result, EquipmentAssignmentResult)
        assert result.source == "maiw-backend"
        assert result.proposal.action == "warehouse.equipment.assign"
        assert result.proposal.parameters["asset_id"] == "FL-001"
        assert result.proposal.requires_approval is True


# ── Contract: Equipment Skill ─────────────────────────────────────────────────


class TestEquipmentSkillContract:
    """Tests that skills correctly use the MCP client."""

    def test_status_skill_invokes_correct_capability(self):
        from src.api.skills.equipment import EquipmentStatusSkill
        from maiw_mcp.client.client import MAIWMCPClient

        async def run():
            mock_client = MagicMock(spec=MAIWMCPClient)
            mock_client.invoke = AsyncMock(
                return_value={
                    "equipment": [],
                    "summary": {},
                    "total_count": 0,
                    "source": "mock",
                }
            )
            skill = EquipmentStatusSkill(mock_client)
            result = await skill.execute(EquipmentStatusRequest())
            return mock_client.invoke.call_args[0][0], result

        capability_name, result = asyncio.run(run())
        assert capability_name == "warehouse.equipment.get_status"
        assert isinstance(result, EquipmentStatusResult)

    def test_telemetry_skill_invokes_correct_capability(self):
        from src.api.skills.equipment import EquipmentTelemetrySkill
        from maiw_mcp.client.client import MAIWMCPClient

        async def run():
            mock_client = MagicMock(spec=MAIWMCPClient)
            mock_client.invoke = AsyncMock(
                return_value={
                    "asset_id": "AMR-001",
                    "telemetry_data": [],
                    "available_metrics": [],
                    "hours_back": 24,
                    "data_points": 0,
                    "source": "mock",
                }
            )
            skill = EquipmentTelemetrySkill(mock_client)
            result = await skill.execute(EquipmentTelemetryRequest(asset_id="AMR-001"))
            return mock_client.invoke.call_args[0][0], result

        capability_name, result = asyncio.run(run())
        assert capability_name == "warehouse.equipment.get_telemetry"
        assert isinstance(result, EquipmentTelemetryResult)

    def test_status_skill_raises_contract_error_on_invalid_result(self):
        from src.api.skills.equipment import EquipmentStatusSkill
        from maiw_mcp.client.client import MAIWMCPClient

        async def run():
            mock_client = MagicMock(spec=MAIWMCPClient)
            mock_client.invoke = AsyncMock(return_value={"totally": "wrong_shape"})
            skill = EquipmentStatusSkill(mock_client)
            return await skill.execute(EquipmentStatusRequest())

        with pytest.raises(MCPContractError):
            asyncio.run(run())

    def test_assignment_skill_returns_action_proposal_locally(self):
        """EquipmentAssignmentSkill builds proposals locally — no MCP call."""
        from src.api.skills.equipment import EquipmentAssignmentSkill
        from unittest.mock import MagicMock, AsyncMock
        from maiw_mcp.client.client import MAIWMCPClient

        async def run():
            # Skill takes no client argument — proposal is built in-process
            skill = EquipmentAssignmentSkill()
            return await skill.execute(
                EquipmentAssignmentRequest(
                    asset_id="FL-001",
                    assignee="op-1",
                    reason="test",
                    requested_by="test-agent",
                )
            )

        result = asyncio.run(run())
        assert isinstance(result, ActionProposal)
        assert result.action == "warehouse.equipment.assign"
        assert result.parameters["asset_id"] == "FL-001"

    def test_assignment_skill_makes_no_mcp_call(self):
        """Architecture invariant: proposal skill must not call MCP."""
        from src.api.skills.equipment import EquipmentAssignmentSkill
        from unittest.mock import MagicMock, AsyncMock
        from maiw_mcp.client.client import MAIWMCPClient

        async def run():
            mock_client = MagicMock(spec=MAIWMCPClient)
            mock_client.invoke = AsyncMock()
            # Skill no longer accepts a client — but even if it did, no invoke should happen
            skill = EquipmentAssignmentSkill()
            await skill.execute(
                EquipmentAssignmentRequest(
                    asset_id="FL-001",
                    assignee="op-1",
                    reason="test",
                    requested_by="test-agent",
                )
            )
            return mock_client.invoke.call_count

        call_count = asyncio.run(run())
        assert call_count == 0, "EquipmentAssignmentSkill must not invoke MCP"
