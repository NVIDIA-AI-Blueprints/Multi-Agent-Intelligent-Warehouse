# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 18H — SOP validation tests.

Tests verify:
    - All canonical SOPs pass validate_sop()
    - SOPs with WRITE capabilities are rejected
    - SOPs with circular step references are rejected
    - SOPs with missing stop_conditions are rejected
    - StepCondition.evaluate() works correctly
"""

from __future__ import annotations

import pathlib
import pytest
import yaml

WORKTREE = pathlib.Path(__file__).parent.parent.parent
SOP_DIR = WORKTREE / "agents" / "sops"


def _get_sop_paths():
    if not SOP_DIR.exists():
        return []
    return list(SOP_DIR.rglob("*.yaml"))


# ── Canonical SOP validation ──────────────────────────────────────────────────


class TestCanonicalSOPs:
    """All checked-in SOPs must pass validate_sop()."""

    @pytest.mark.parametrize("sop_path", _get_sop_paths())
    def test_canonical_sop_valid(self, sop_path):
        from maiw_agents.contracts import load_sop

        sop = load_sop(sop_path)
        assert sop.id is not None
        assert sop.version is not None
        assert len(sop.steps) > 0
        assert len(sop.stop_conditions) > 0

    def test_oca_sop_exists(self):
        oca_sop = SOP_DIR / "operations_coordination" / "wave_risk_resolution.v1.yaml"
        assert oca_sop.exists(), f"OCA SOP not found at {oca_sop}"

    def test_labor_sop_exists(self):
        labor_sop = SOP_DIR / "labor" / "labor_constraint_assessment.v1.yaml"
        assert labor_sop.exists(), f"Labor SOP not found at {labor_sop}"

    def test_wave_sop_exists(self):
        wave_sop = SOP_DIR / "wave" / "wave_risk_assessment.v1.yaml"
        assert wave_sop.exists(), f"Wave SOP not found at {wave_sop}"

    def test_oca_sop_no_write_capabilities(self):
        from maiw_agents.contracts import load_sop, CapabilityClass, SKILL_REGISTRY

        oca_sop = SOP_DIR / "operations_coordination" / "wave_risk_resolution.v1.yaml"
        sop = load_sop(oca_sop)
        for cap_id in sop.allowed_capabilities:
            skill = SKILL_REGISTRY.get(cap_id)
            if skill is not None:
                assert skill.capability_class not in (
                    CapabilityClass.WRITE,
                    CapabilityClass.EMERGENCY_WRITE,
                ), f"OCA SOP has WRITE capability {cap_id!r}"

    def test_labor_sop_no_subagents(self):
        from maiw_agents.contracts import load_sop

        labor_sop = SOP_DIR / "labor" / "labor_constraint_assessment.v1.yaml"
        sop = load_sop(labor_sop)
        assert sop.allowed_subagents == []

    def test_wave_sop_no_subagents(self):
        from maiw_agents.contracts import load_sop

        wave_sop = SOP_DIR / "wave" / "wave_risk_assessment.v1.yaml"
        sop = load_sop(wave_sop)
        assert sop.allowed_subagents == []

    def test_oca_sop_has_observe_step(self):
        from maiw_agents.contracts import load_sop

        oca_sop = SOP_DIR / "operations_coordination" / "wave_risk_resolution.v1.yaml"
        sop = load_sop(oca_sop)
        step_ids = [s.id for s in sop.steps]
        assert (
            "observe" in step_ids
        ), "OCA SOP must have an 'observe' step (post-execution state evaluation)"

    def test_oca_sop_has_submit_step(self):
        from maiw_agents.contracts import load_sop

        oca_sop = SOP_DIR / "operations_coordination" / "wave_risk_resolution.v1.yaml"
        sop = load_sop(oca_sop)
        step_ids = [s.id for s in sop.steps]
        assert (
            "submit" in step_ids
        ), "OCA SOP must have a 'submit' step (emit_recommended_action)"


# ── SOP rejection tests ───────────────────────────────────────────────────────


class TestSOPRejection:
    """Invalid SOPs must be rejected by validate_sop()."""

    def _make_sop_dict(self, **overrides):
        base = {
            "id": "test.sop",
            "version": "1.0",
            "agent": "test_agent",
            "objective": "Test SOP.",
            "description": "A test SOP.",
            "triggers": ["test_trigger"],
            "required_context": ["warehouse"],
            "allowed_capabilities": ["warehouse.inventory.lookup"],
            "allowed_subagents": [],
            "steps": [
                {"id": "step_one", "action": "invoke_skill", "description": "Read it."}
            ],
            "stop_conditions": ["objective_met"],
        }
        base.update(overrides)
        return base

    def test_sop_with_write_capability_rejected(self, tmp_path):
        from maiw_agents.contracts import load_sop, SOPValidationError

        sop_dict = self._make_sop_dict(
            allowed_capabilities=["warehouse.labor.assign_direct"]
        )
        sop_file = tmp_path / "bad.yaml"
        sop_file.write_text(yaml.dump(sop_dict))
        with pytest.raises(SOPValidationError) as exc_info:
            load_sop(sop_file)
        assert "write" in str(exc_info.value).lower() or "WRITE" in str(exc_info.value)

    def test_sop_with_no_stop_conditions_rejected(self, tmp_path):
        from maiw_agents.contracts import load_sop, SOPValidationError

        sop_dict = self._make_sop_dict(stop_conditions=[])
        sop_file = tmp_path / "bad.yaml"
        sop_file.write_text(yaml.dump(sop_dict))
        with pytest.raises(SOPValidationError):
            load_sop(sop_file)

    def test_sop_with_no_steps_rejected(self, tmp_path):
        from maiw_agents.contracts import load_sop, SOPValidationError

        sop_dict = self._make_sop_dict(steps=[])
        sop_file = tmp_path / "bad.yaml"
        sop_file.write_text(yaml.dump(sop_dict))
        with pytest.raises(SOPValidationError):
            load_sop(sop_file)

    def test_sop_with_circular_steps_rejected(self, tmp_path):
        from maiw_agents.contracts import load_sop, SOPValidationError

        sop_dict = self._make_sop_dict(
            steps=[
                {
                    "id": "step_a",
                    "action": "invoke_skill",
                    "description": "A.",
                    "next_step_id": "step_b",
                },
                {
                    "id": "step_b",
                    "action": "invoke_skill",
                    "description": "B.",
                    "next_step_id": "step_a",
                },
            ]
        )
        sop_file = tmp_path / "circular.yaml"
        sop_file.write_text(yaml.dump(sop_dict))
        with pytest.raises(SOPValidationError) as exc_info:
            load_sop(sop_file)
        assert (
            "circular" in str(exc_info.value).lower()
            or "cycle" in str(exc_info.value).lower()
        )

    def test_sop_with_duplicate_step_ids_rejected(self, tmp_path):
        from maiw_agents.contracts import load_sop, SOPValidationError

        sop_dict = self._make_sop_dict(
            steps=[
                {"id": "step_a", "action": "invoke_skill", "description": "A."},
                {"id": "step_a", "action": "invoke_skill", "description": "Also A."},
            ]
        )
        sop_file = tmp_path / "dup.yaml"
        sop_file.write_text(yaml.dump(sop_dict))
        with pytest.raises(SOPValidationError):
            load_sop(sop_file)

    def test_sop_missing_required_fields_rejected(self, tmp_path):
        from maiw_agents.contracts import load_sop

        sop_file = tmp_path / "empty.yaml"
        sop_file.write_text(yaml.dump({"id": "only_id"}))
        with pytest.raises(Exception):  # SOPValidationError or pydantic ValidationError
            load_sop(sop_file)


# ── StepCondition ─────────────────────────────────────────────────────────────


class TestStepCondition:
    """StepCondition.evaluate() must respect operator semantics."""

    def _make_condition(self, predicate, operator, value=None):
        from maiw_agents.contracts.sop import StepCondition

        return StepCondition(predicate=predicate, operator=operator, value=value)

    def test_eq_true(self):
        cond = self._make_condition("severity", "eq", "high")
        assert cond.evaluate({"severity": "high"}) is True

    def test_eq_false(self):
        cond = self._make_condition("severity", "eq", "high")
        assert cond.evaluate({"severity": "low"}) is False

    def test_contains_true(self):
        cond = self._make_condition("domains_affected", "contains", "labor")
        assert cond.evaluate({"domains_affected": ["labor", "wave"]}) is True

    def test_contains_false(self):
        cond = self._make_condition("domains_affected", "contains", "equipment")
        assert cond.evaluate({"domains_affected": ["labor"]}) is False

    def test_exists_true(self):
        cond = self._make_condition("wave_risk", "exists")
        assert cond.evaluate({"wave_risk": "high"}) is True

    def test_exists_false(self):
        cond = self._make_condition("wave_risk", "exists")
        assert cond.evaluate({"other_key": "value"}) is False

    def test_not_exists_true(self):
        cond = self._make_condition("wave_risk", "not_exists")
        assert cond.evaluate({"other_key": "value"}) is True

    def test_missing_key_eq_false(self):
        cond = self._make_condition("missing_key", "eq", "something")
        assert cond.evaluate({}) is False
