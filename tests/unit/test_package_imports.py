# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 8 — package import smoke tests and forbidden-dependency guards.

Tests:
1. Smoke: each canonical package can be imported without infrastructure
2. Forbidden: lightweight packages do not import API, agents, or heavy deps
3. Canonical: new import paths resolve and are functionally correct
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

# ── Helpers ────────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _source_imports(package_dir: Path) -> set[str]:
    """Return the set of top-level module names imported by any .py file in package_dir."""
    imports: set[str] = set()
    for py_file in package_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.level == 0:
                    imports.add(node.module.split(".")[0])
    return imports


# ── Smoke tests: packages import without infrastructure ───────────────────────


class TestPackageImportSmoke:
    """Each canonical package must be importable without live infrastructure."""

    def test_maiw_mcp_importable(self):
        import maiw_mcp  # noqa: F401

    def test_maiw_state_importable(self):
        import maiw_state  # noqa: F401

    def test_maiw_decision_importable(self):
        import maiw_decision  # noqa: F401

    def test_maiw_models_importable(self):
        import maiw_models  # noqa: F401

    def test_maiw_skills_importable(self):
        import maiw_skills  # noqa: F401

    def test_canonical_model_gateway_import(self):
        from maiw_models import ModelGateway, ModelRequest, ReasoningLevel

        assert ModelGateway is not None
        assert ModelRequest is not None
        assert ReasoningLevel is not None

    def test_canonical_skills_import(self):
        from maiw_skills.inventory import InventoryLookupSkill
        from maiw_skills.equipment import EquipmentAssignmentSkill
        from maiw_skills.labor import ProposeLaborAllocationSkill
        from maiw_skills.wave import ProposeWaveReprioritizationSkill

        assert InventoryLookupSkill is not None
        assert EquipmentAssignmentSkill is not None
        assert ProposeLaborAllocationSkill is not None
        assert ProposeWaveReprioritizationSkill is not None

    def test_canonical_decision_import(self):
        from maiw_decision import DecisionEngine
        from maiw_decision.models import DecisionOutcome, DecisionResult

        engine = DecisionEngine()
        assert engine is not None

    def test_canonical_state_import(self):
        from maiw_state import WarehouseState, WarehouseStateSnapshot
        from maiw_state.models.labor import LaborState
        from maiw_state.models.wave import WaveState

        assert WarehouseState is not None
        assert LaborState is not None
        assert WaveState is not None

    def test_canonical_mcp_import(self):
        from maiw_mcp.contracts.actions import ActionProposal
        from maiw_mcp.contracts.inventory import INVENTORY_GET_METADATA
        from maiw_mcp.contracts.equipment import EQUIPMENT_ASSIGN_METADATA
        from maiw_mcp.contracts.labor import LABOR_ALLOCATE_METADATA
        from maiw_mcp.contracts.wave import WAVE_REPRIORITIZE_METADATA

        assert ActionProposal is not None


# ── Forbidden dependency checks ────────────────────────────────────────────────


class TestForbiddenDependencies:
    """
    Lightweight packages must not depend on apps/api, agents, or heavy
    infrastructure dependencies (asyncpg, pymilvus, redis, FastAPI).

    These checks use AST-level import scanning, which is conservative:
    a match means the import exists in source, not necessarily that it
    executes at runtime (guarded imports are also caught).
    """

    HEAVY_DEPS = {"asyncpg", "pymilvus", "redis", "fastapi", "uvicorn"}

    def _check_no_forbidden_imports(
        self, package_dir: Path, forbidden: set[str], label: str
    ):
        imports = _source_imports(package_dir)
        violations = imports & forbidden
        assert not violations, (
            f"{label} imports forbidden modules: {violations}. "
            f"These belong in apps/ or integrations/, not core packages."
        )

    def test_maiw_mcp_no_api_import(self):
        pkg = PROJECT_ROOT / "packages" / "maiw-mcp" / "maiw_mcp"
        imports = _source_imports(pkg)
        assert "src" not in imports, "maiw_mcp must not import from src (API layer)"

    def test_maiw_state_no_api_import(self):
        pkg = PROJECT_ROOT / "packages" / "maiw-state" / "maiw_state"
        imports = _source_imports(pkg)
        assert "src" not in imports, "maiw_state must not import from src (API layer)"

    def test_maiw_decision_no_api_import(self):
        pkg = PROJECT_ROOT / "packages" / "maiw-decision" / "maiw_decision"
        imports = _source_imports(pkg)
        assert (
            "src" not in imports
        ), "maiw_decision must not import from src (API layer)"

    def test_maiw_models_no_api_import(self):
        pkg = PROJECT_ROOT / "packages" / "maiw-models" / "maiw_models"
        imports = _source_imports(pkg)
        assert "src" not in imports, "maiw_models must not import from src (API layer)"

    def test_maiw_skills_no_api_import(self):
        pkg = PROJECT_ROOT / "packages" / "maiw-skills" / "maiw_skills"
        imports = _source_imports(pkg)
        assert "src" not in imports, "maiw_skills must not import from src (API layer)"

    def test_maiw_mcp_no_heavy_deps(self):
        pkg = PROJECT_ROOT / "packages" / "maiw-mcp" / "maiw_mcp"
        self._check_no_forbidden_imports(pkg, self.HEAVY_DEPS, "maiw_mcp")

    def test_maiw_state_no_heavy_deps(self):
        pkg = PROJECT_ROOT / "packages" / "maiw-state" / "maiw_state"
        self._check_no_forbidden_imports(pkg, self.HEAVY_DEPS, "maiw_state")

    def test_maiw_decision_no_heavy_deps(self):
        pkg = PROJECT_ROOT / "packages" / "maiw-decision" / "maiw_decision"
        self._check_no_forbidden_imports(pkg, self.HEAVY_DEPS, "maiw_decision")

    def test_maiw_skills_no_heavy_deps(self):
        pkg = PROJECT_ROOT / "packages" / "maiw-skills" / "maiw_skills"
        self._check_no_forbidden_imports(pkg, self.HEAVY_DEPS, "maiw_skills")

    def test_maiw_mcp_no_agents_import(self):
        pkg = PROJECT_ROOT / "packages" / "maiw-mcp" / "maiw_mcp"
        imports = _source_imports(pkg)
        assert "maiw_agents" not in imports, "maiw_mcp must not depend on maiw_agents"

    def test_maiw_state_no_agents_import(self):
        pkg = PROJECT_ROOT / "packages" / "maiw-state" / "maiw_state"
        imports = _source_imports(pkg)
        assert "maiw_agents" not in imports, "maiw_state must not depend on maiw_agents"

    def test_maiw_execution_no_src_import(self):
        pkg = PROJECT_ROOT / "packages" / "maiw-execution" / "maiw_execution"
        imports = _source_imports(pkg)
        assert (
            "src" not in imports
        ), "maiw_execution must not import from src (API layer)"

    def test_maiw_agents_no_src_import(self):
        pkg = PROJECT_ROOT / "packages" / "maiw-agents" / "maiw_agents"
        imports = _source_imports(pkg)
        assert "src" not in imports, "maiw_agents must not import from src (API layer)"

    def test_maiw_execution_no_heavy_deps(self):
        pkg = PROJECT_ROOT / "packages" / "maiw-execution" / "maiw_execution"
        self._check_no_forbidden_imports(pkg, self.HEAVY_DEPS, "maiw_execution")

    def test_maiw_agents_no_heavy_deps(self):
        pkg = PROJECT_ROOT / "packages" / "maiw-agents" / "maiw_agents"
        self._check_no_forbidden_imports(pkg, self.HEAVY_DEPS, "maiw_agents")

    def test_maiw_execution_no_agents_import(self):
        pkg = PROJECT_ROOT / "packages" / "maiw-execution" / "maiw_execution"
        imports = _source_imports(pkg)
        assert (
            "maiw_agents" not in imports
        ), "maiw_execution must not depend on maiw_agents (would create cycle)"


# ── Phase 9A smoke tests: new packages importable ─────────────────────────────


class TestPhase9AImportSmoke:
    """maiw_execution and maiw_agents must be importable without infrastructure."""

    def test_maiw_execution_importable(self):
        import maiw_execution  # noqa: F401

    def test_maiw_agents_importable(self):
        import maiw_agents  # noqa: F401

    def test_maiw_execution_base_executor(self):
        from maiw_execution import (
            BaseActionExecutor,
            ActionExecutionResult,
            NoOpActionExecutor,
        )

        assert BaseActionExecutor is not None
        assert ActionExecutionResult is not None
        assert NoOpActionExecutor is not None

    def test_maiw_execution_domain_executors(self):
        from maiw_execution import (
            EquipmentActionExecutor,
            LaborActionExecutor,
            WaveActionExecutor,
        )

        assert EquipmentActionExecutor is not None
        assert LaborActionExecutor is not None
        assert WaveActionExecutor is not None

    def test_maiw_execution_error_hierarchy(self):
        from maiw_execution import (
            ActionNotApproved,
            ActionDecisionMismatch,
            ActionUnsupported,
            ActionExpired,
            ActionConflict,
            ActionExecutionError,
        )

        # Guard errors subclass ValueError; wrap error subclasses RuntimeError
        assert issubclass(ActionNotApproved, ValueError)
        assert issubclass(ActionDecisionMismatch, ValueError)
        assert issubclass(ActionUnsupported, ValueError)
        assert issubclass(ActionExpired, ValueError)
        assert issubclass(ActionConflict, RuntimeError)
        assert issubclass(ActionExecutionError, RuntimeError)

    def test_maiw_agents_equipment(self):
        from maiw_agents.equipment import EquipmentAssetOperationsAgent

        assert EquipmentAssetOperationsAgent is not None

    def test_maiw_agents_operations(self):
        from maiw_agents.operations import OperationsCoordinationAgent

        assert OperationsCoordinationAgent is not None

    def test_maiw_agents_safety(self):
        from maiw_agents.safety import SafetyComplianceAgent

        assert SafetyComplianceAgent is not None

    def test_equipment_executor_allowed_actions(self):
        from maiw_execution import EquipmentActionExecutor

        allowed = EquipmentActionExecutor._ALLOWED_ACTIONS
        assert "warehouse.equipment.assign" in allowed
        assert "warehouse.equipment.release" in allowed
        assert "warehouse.equipment.schedule_maintenance" in allowed

    def test_labor_executor_allowed_actions(self):
        from maiw_execution import LaborActionExecutor

        assert "warehouse.labor.allocate" in LaborActionExecutor._ALLOWED_ACTIONS

    def test_wave_executor_allowed_actions(self):
        from maiw_execution import WaveActionExecutor

        assert "warehouse.wave.reprioritize" in WaveActionExecutor._ALLOWED_ACTIONS


# ── Compatibility shim tests ───────────────────────────────────────────────────


class TestCompatibilityShims:
    """
    The old import paths must still work through the compatibility shims.
    These will be removed in Phase 9.
    """

    def test_old_model_gateway_path_still_works(self):
        from src.api.services.model_gateway import (
            ModelGateway,
            ModelRequest,
            ReasoningLevel,
            get_model_gateway,
        )

        assert ModelGateway is not None

    def test_old_model_gateway_models_path_still_works(self):
        from src.api.services.model_gateway.models import ReasoningLevel, RiskLevel

        assert ReasoningLevel is not None

    def test_old_skills_inventory_path_still_works(self):
        from src.api.skills.inventory import InventoryLookupSkill

        assert InventoryLookupSkill is not None

    def test_old_skills_equipment_path_still_works(self):
        from src.api.skills.equipment import (
            EquipmentAssignmentSkill,
            EquipmentStatusSkill,
        )

        assert EquipmentAssignmentSkill is not None

    def test_old_skills_labor_path_still_works(self):
        from src.api.skills.labor import ProposeLaborAllocationSkill

        assert ProposeLaborAllocationSkill is not None

    def test_old_skills_wave_path_still_works(self):
        from src.api.skills.wave import ProposeWaveReprioritizationSkill

        assert ProposeWaveReprioritizationSkill is not None

    def test_shim_and_canonical_are_same_class(self):
        """The shim re-exports the exact same class, not a copy."""
        from src.api.skills.labor import ProposeLaborAllocationSkill as OldPath
        from maiw_skills.labor import ProposeLaborAllocationSkill as NewPath

        assert OldPath is NewPath

    def test_model_gateway_shim_and_canonical_same_class(self):
        from src.api.services.model_gateway import ModelGateway as OldPath
        from maiw_models import ModelGateway as NewPath

        assert OldPath is NewPath
