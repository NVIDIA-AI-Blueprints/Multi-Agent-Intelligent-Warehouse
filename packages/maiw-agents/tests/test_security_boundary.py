# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
SOP Engine authority boundary.

Design Sections 14 and 31: the SOP Engine decides whether a step is complete.
It never authorizes an operational write. These tests assert that structurally
— by inspecting the module source and the import graph — rather than trusting a
docstring.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from maiw_agents import sop_engine
from maiw_agents.contracts.registry import SKILL_REGISTRY, CapabilityClass
from maiw_agents.sop_engine import engine as engine_module
from maiw_agents.sop_engine import executor as executor_module
from maiw_agents.sop_engine import validators as validators_module

SOP_ENGINE_DIR = Path(sop_engine.__file__).parent
SOP_ENGINE_MODULES = [engine_module, executor_module, validators_module]

FORBIDDEN_NAMES = (
    "ActionExecutor",
    "maiw_execution",
    "DecisionEngine",
    "NoOpActionExecutor",
)


def _source_files() -> list[Path]:
    return sorted(p for p in SOP_ENGINE_DIR.glob("*.py"))


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _code_identifiers(path: Path) -> set[str]:
    """
    Every identifier that actually executes.

    Deliberately AST-based: string literals and docstrings are excluded, so a
    module may *describe* the boundary it upholds without tripping the check,
    while any real reference is caught.
    """
    tree = ast.parse(path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.update(alias.name.split("."))
                if alias.asname:
                    names.add(alias.asname)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.update(node.module.split("."))
            for alias in node.names:
                names.add(alias.name)
                if alias.asname:
                    names.add(alias.asname)
    return names


# ── No execution authority in the SOP Engine ──────────────────────────────────

def test_sop_engine_package_has_source_files():
    assert _source_files(), "SOP engine package must contain modules to inspect"


@pytest.mark.parametrize("forbidden", FORBIDDEN_NAMES)
def test_sop_engine_source_never_references_execution_authority(forbidden):
    offenders = [
        path.name for path in _source_files()
        if forbidden in _code_identifiers(path)
    ]
    assert not offenders, (
        f"SOP Engine must not reference {forbidden} in executable code: {offenders}"
    )


def test_sop_engine_does_not_import_maiw_execution():
    for path in _source_files():
        modules = _imported_modules(path)
        assert not any(m.startswith("maiw_execution") for m in modules), (
            f"{path.name} imports maiw_execution: {sorted(modules)}"
        )


def test_sop_engine_does_not_import_decision_engine():
    for path in _source_files():
        modules = _imported_modules(path)
        assert not any(m.startswith("maiw_decision") for m in modules), (
            f"{path.name} imports maiw_decision: {sorted(modules)}"
        )


def test_sop_engine_imports_only_contracts_and_stdlib():
    """Every first-party import must stay within maiw_agents.contracts / sop_engine."""
    for path in _source_files():
        for module in _imported_modules(path):
            if module.startswith("maiw_"):
                assert module.startswith("maiw_agents"), f"{path.name} imports {module}"


@pytest.mark.parametrize("module", SOP_ENGINE_MODULES, ids=lambda m: m.__name__)
def test_sop_engine_module_namespace_has_no_executor(module):
    for forbidden in ("ActionExecutor", "NoOpActionExecutor", "DecisionEngine"):
        assert not hasattr(module, forbidden), (
            f"{module.__name__} exposes {forbidden} in its namespace"
        )


# ── Validators cannot write ───────────────────────────────────────────────────

def test_validator_registry_does_not_import_action_executor():
    source = inspect.getsource(validators_module)
    assert "from maiw_execution" not in source
    assert "import maiw_execution" not in source


def test_no_validator_exposes_a_write_capability():
    """
    No validator may be configured with, or reference, a WRITE capability id.

    A validator confirms a write happened by reading authoritative state, never
    by invoking the write.
    """
    write_caps = [
        skill_id
        for skill_id, entry in SKILL_REGISTRY.items()
        if entry.capability_class in (CapabilityClass.WRITE, CapabilityClass.EMERGENCY_WRITE)
    ]
    assert write_caps, "registry must contain WRITE capabilities for this test to mean anything"

    combined = "\n".join(p.read_text() for p in _source_files())
    for cap_id in write_caps:
        assert cap_id not in combined, (
            f"SOP Engine references WRITE capability {cap_id!r}"
        )


def test_validators_have_no_execute_or_invoke_methods():
    from maiw_agents.sop_engine.validators import (
        CapabilityResultValidator,
        LegacySuccessValidator,
        SchemaValidator,
        StatePredicateValidator,
    )

    for cls in (
        SchemaValidator, StatePredicateValidator,
        CapabilityResultValidator, LegacySuccessValidator,
    ):
        public = {n for n in dir(cls) if not n.startswith("_")}
        assert public == {"validate"}, (
            f"{cls.__name__} exposes more than validate(): {sorted(public)}"
        )


def test_validation_context_carries_no_executor():
    """
    StepValidationContext is the validator's entire view of the world. It must
    not hand over anything that could perform a write.
    """
    from maiw_agents.sop_engine.validators import StepValidationContext

    fields = set(StepValidationContext.__dataclass_fields__)
    assert fields == {
        "step", "procedure_state", "execution_context",
        "warehouse_state_snapshot", "metadata",
    }
    for forbidden in ("action_executor", "executor", "decision_engine", "mcp_client",
                      "credentials", "write_client"):
        assert forbidden not in fields


def test_agent_execution_context_carries_no_executor():
    from maiw_agents.contracts.runtime import AgentExecutionContext

    fields = set(AgentExecutionContext.__dataclass_fields__)
    for forbidden in ("action_executor", "decision_engine", "credentials"):
        assert forbidden not in fields


# ── Engine authority ──────────────────────────────────────────────────────────

def test_engine_has_no_write_or_execute_entry_point():
    from maiw_agents.sop_engine import SOPEngine

    public = {n for n in dir(SOPEngine) if not n.startswith("_")}
    assert public == {"run_procedure", "resume_after_governance"}, (
        f"SOPEngine exposes unexpected public API: {sorted(public)}"
    )


def test_engine_constructor_takes_no_executor_of_actions():
    from maiw_agents.sop_engine import SOPEngine

    params = set(inspect.signature(SOPEngine.__init__).parameters)
    assert params == {
        "self", "executor", "validator_registry", "trace_id", "max_transitions"
    }
    # 'executor' here is a SOPStepExecutor (a step runner), not an ActionExecutor.
    annotation = inspect.signature(SOPEngine.__init__).parameters["executor"].annotation
    assert "SOPStepExecutor" in str(annotation)
