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
        "self", "executor", "validator_registry", "trace_id", "max_transitions",
        "store",
    }
    # 'executor' here is a SOPStepExecutor (a step runner), not an ActionExecutor.
    annotation = inspect.signature(SOPEngine.__init__).parameters["executor"].annotation
    assert "SOPStepExecutor" in str(annotation)

    # 'store' is a ProcedureStateStore — a record keeper, not an actor. It can
    # save, load and delete procedure state and nothing else, so handing the
    # engine persistence grants it no operational authority.
    store_annotation = str(
        inspect.signature(SOPEngine.__init__).parameters["store"].annotation
    )
    assert "ProcedureStateStore" in store_annotation

    from maiw_agents.sop_engine import ProcedureStateStore

    store_api = {n for n in dir(ProcedureStateStore) if not n.startswith("_")}
    assert store_api == {"save", "load", "delete"}, (
        f"ProcedureStateStore exposes unexpected API: {sorted(store_api)}"
    )


# ── Engine domain neutrality ──────────────────────────────────────────────────

# Domain packages the generic SOP Engine must never reach into. The engine
# expresses loops, retries and validation in terms of steps and budgets; the
# moment it imports a warehouse domain it has stopped being an engine and
# started being one procedure's implementation.
_DOMAIN_MODULES = (
    "wave", "equipment", "inventory", "labor", "safety_compliance",
    "domain_predicates", "assessment",
)


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: p.name)
def test_sop_engine_imports_no_domain_modules(path):
    imported = _imported_modules(path)
    leaked = {
        name for name in imported
        if any(
            name == dom or name.endswith(f".{dom}") or f".{dom}." in name
            for dom in _DOMAIN_MODULES
        )
    }
    assert not leaked, (
        f"{path.name} imports domain-specific modules {sorted(leaked)} — the "
        "generic SOP Engine must stay domain-neutral"
    )


def test_sop_engine_source_names_no_warehouse_domain_concepts():
    """
    Belt-and-suspenders on the import check: the engine's *code* must not
    mention SKUs, pallets, forklifts or waves either.
    """
    forbidden_terms = ("sku", "pallet", "forklift", "wave_id", "picker", "carrier")
    for path in _source_files():
        # Strip docstrings and comments — prose explaining the boundary is fine,
        # executable code referencing a domain is not.
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) or isinstance(node, ast.Attribute):
                text = getattr(node, "id", None) or getattr(node, "attr", "")
                lowered = text.lower()
                for term in forbidden_terms:
                    assert term not in lowered, (
                        f"{path.name} references warehouse domain concept "
                        f"{term!r} in executable code ({text})"
                    )


# ── Credential boundary (sandbox-target layer) ────────────────────────────────

_AGENTS_PACKAGE_DIR = SOP_ENGINE_DIR.parent

# Patterns that would indicate a real secret, as opposed to prose asserting that
# the package holds none. Assignment and env lookup are what matter.
_CREDENTIAL_PATTERNS = (
    "NVIDIA_API_KEY",
    "WMS_PASSWORD",
    "DATABASE_URL",
    "AWS_SECRET",
)


def _package_sources() -> list[Path]:
    return sorted(
        p for p in _AGENTS_PACKAGE_DIR.rglob("*.py")
        if "__pycache__" not in p.parts
    )


def test_agent_package_holds_no_operational_credentials():
    """
    The sandbox-target layer must carry no warehouse credentials.

    This is a precondition for handing any part of this package to a sandboxed
    executor: a sandbox that cannot reach a credential cannot leak one. Checked
    against executable code, so docstrings documenting the boundary are fine.
    """
    offenders: list[str] = []
    for path in _package_sources():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                # A docstring is an ast.Constant too; skip ones used as such.
                if any(pat in node.value for pat in _CREDENTIAL_PATTERNS):
                    if len(node.value) < 200:   # a literal, not a prose block
                        offenders.append(f"{path.name}:{node.lineno} {node.value[:60]}")
    assert not offenders, f"credential-like literals found: {offenders}"


def test_agent_package_reads_no_credential_environment_variables():
    """No os.environ / os.getenv lookup of a warehouse or provider credential."""
    offenders: list[str] = []
    for path in _package_sources():
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name not in ("getenv", "environ"):
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if any(pat in arg.value for pat in _CREDENTIAL_PATTERNS):
                        offenders.append(f"{path.name}:{node.lineno} {arg.value}")
    assert not offenders, f"credential env lookups found: {offenders}"


# ── Capability policy cannot be widened from outside ──────────────────────────

def test_capability_policy_is_built_only_from_maiw_controlled_inputs():
    """
    build_capability_policy's signature is the whole list of things that can
    influence authority. If a prompt, an env var or a model response ever
    becomes a parameter, this test is the tripwire.
    """
    from maiw_agents.contracts.capability_policy import build_capability_policy

    params = set(inspect.signature(build_capability_policy).parameters)
    assert params == {
        "definition", "sop", "agent_task_id", "runtime", "policy_revision"
    }, f"unexpected policy inputs: {sorted(params)}"


def test_capability_policy_module_imports_no_model_or_execution_surface():
    policy_path = SOP_ENGINE_DIR.parent / "contracts" / "capability_policy.py"
    imported = _imported_modules(policy_path)
    for forbidden in ("maiw_execution", "maiw_models", "model_gateway", "os"):
        assert not any(forbidden in name for name in imported), (
            f"capability_policy imports {forbidden} — policy must be derived "
            "from MAIW contracts alone"
        )
