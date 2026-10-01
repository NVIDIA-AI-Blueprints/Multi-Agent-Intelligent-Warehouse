# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
tests/api/test_architecture.py

Package dependency direction tests.

Rule: canonical packages (maiw-*) must not import from the API layer
(maiw_api or src.api).  The API layer may import from packages — not
the other way around.

These tests grep the source of each package and assert no forbidden
import patterns exist.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent

# Paths to canonical packages
CANONICAL_PACKAGES = [
    REPO_ROOT / "packages" / "maiw-models" / "maiw_models",
    REPO_ROOT / "packages" / "maiw-mcp" / "maiw_mcp",
    REPO_ROOT / "packages" / "maiw-state" / "maiw_state",
    REPO_ROOT / "packages" / "maiw-skills" / "maiw_skills",
    REPO_ROOT / "packages" / "maiw-decision" / "maiw_decision",
    REPO_ROOT / "packages" / "maiw-execution" / "maiw_execution",
    REPO_ROOT / "packages" / "maiw-agents" / "maiw_agents",
]

# Import prefixes that canonical packages must never use
FORBIDDEN_IMPORTS_FROM_PACKAGES = [
    "maiw_api",
    "src.api",
    "apps.api",
]


def _python_files(directory: Path):
    return directory.rglob("*.py")


def _imports_in_file(path: Path) -> list[str]:
    """Return all dotted module names imported in a Python file."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
    return imports


@pytest.mark.parametrize("pkg_path", CANONICAL_PACKAGES, ids=lambda p: p.parent.name)
def test_package_does_not_import_api_layer(pkg_path: Path):
    """Canonical packages must not import from the API layer."""
    if not pkg_path.exists():
        pytest.skip(f"{pkg_path} not found")

    violations: list[str] = []
    for py_file in _python_files(pkg_path):
        for imp in _imports_in_file(py_file):
            for forbidden in FORBIDDEN_IMPORTS_FROM_PACKAGES:
                if imp == forbidden or imp.startswith(forbidden + "."):
                    violations.append(f"{py_file.relative_to(REPO_ROOT)}: import {imp}")

    assert (
        not violations
    ), f"Dependency direction violation in {pkg_path.parent.name}:\n" + "\n".join(
        violations
    )


def test_bootstrap_imports_from_packages_only():
    """bootstrap.py must not import from src.api except for integration adapters."""
    bootstrap = REPO_ROOT / "apps" / "api" / "maiw_api" / "bootstrap.py"
    if not bootstrap.exists():
        pytest.skip("bootstrap.py not found")

    forbidden_in_bootstrap = [
        "src.api.services.model_gateway",
        "src.api.skills",
        "src.api.agents.inventory.equipment_agent",
        "src.api.agents.operations.operations_agent",
        "src.api.agents.safety.safety_agent",
        "src.api.services.mcp",
    ]

    imports = _imports_in_file(bootstrap)
    violations = [
        imp
        for imp in imports
        for forbidden in forbidden_in_bootstrap
        if imp == forbidden or imp.startswith(forbidden + ".")
    ]

    assert (
        not violations
    ), "bootstrap.py imports from forbidden src.api paths:\n" + "\n".join(violations)


def test_maiw_api_routers_do_not_import_src_agents():
    """Canonical routers must not import from src.api.agents (use runtime instead)."""
    routers_dir = REPO_ROOT / "apps" / "api" / "maiw_api" / "routers"
    if not routers_dir.exists():
        pytest.skip("maiw_api/routers not found")

    violations = []
    for py_file in routers_dir.rglob("*.py"):
        for imp in _imports_in_file(py_file):
            if imp.startswith("src.api.agents"):
                violations.append(f"{py_file.name}: import {imp}")

    assert (
        not violations
    ), "Canonical routers must not import from src.api.agents:\n" + "\n".join(
        violations
    )


def test_maiw_api_package_exists():
    pkg = REPO_ROOT / "apps" / "api" / "maiw_api"
    assert pkg.is_dir(), "maiw_api package directory must exist"
    assert (pkg / "__init__.py").exists(), "maiw_api/__init__.py must exist"
    assert (pkg / "app.py").exists(), "maiw_api/app.py must exist"
    assert (pkg / "bootstrap.py").exists(), "maiw_api/bootstrap.py must exist"


def test_pyproject_lists_execution_and_agents():
    """apps/api/pyproject.toml must declare maiw-execution and maiw-agents."""
    pyproject = REPO_ROOT / "apps" / "api" / "pyproject.toml"
    if not pyproject.exists():
        pytest.skip("pyproject.toml not found")
    content = pyproject.read_text()
    assert "maiw-execution" in content, "pyproject.toml must declare maiw-execution"
    assert "maiw-agents" in content, "pyproject.toml must declare maiw-agents"


def test_canonical_entrypoint_in_dockerfile_backend():
    """Dockerfile.backend must use maiw_api.app:app, not src.api.app:app."""
    dockerfile = REPO_ROOT / "Dockerfile.backend"
    if not dockerfile.exists():
        pytest.skip("Dockerfile.backend not found")
    content = dockerfile.read_text()
    assert "maiw_api.app:app" in content, "Dockerfile.backend must use maiw_api.app:app"
    assert (
        "src.api.app:app" not in content
    ), "Dockerfile.backend must not reference src.api.app:app"


def test_no_load_dotenv_at_import_time_in_app():
    """load_dotenv() must not appear at module level in app.py (import-time side effect)."""
    app_py = REPO_ROOT / "apps" / "api" / "maiw_api" / "app.py"
    if not app_py.exists():
        pytest.skip("app.py not found")
    # Parse the AST and look for a bare Call to load_dotenv at module scope
    tree = ast.parse(app_py.read_text(encoding="utf-8"))
    module_level_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "load_dotenv"
    ]
    assert not module_level_calls, (
        "load_dotenv() must not be called at module level in app.py; "
        "move it to lifespan startup"
    )


def test_diagnostic_stub_removed():
    """GET /equipment/assignments/test must not exist in the equipment router."""
    equipment_router = (
        REPO_ROOT / "apps" / "api" / "maiw_api" / "routers" / "equipment.py"
    )
    if not equipment_router.exists():
        pytest.skip("equipment router not found")
    content = equipment_router.read_text()
    assert "/equipment/assignments/test" not in content, (
        "Diagnostic stub GET /equipment/assignments/test must be removed "
        "from the equipment router"
    )


def test_runtime_status_router_exists():
    """runtime_status.py must exist and define the /api/v1/runtime/status route."""
    router_path = (
        REPO_ROOT / "apps" / "api" / "maiw_api" / "routers" / "runtime_status.py"
    )
    assert router_path.exists(), "maiw_api/routers/runtime_status.py must exist"
    content = router_path.read_text()
    assert "/runtime/status" in content, "runtime_status.py must define /runtime/status"


def test_mcp_server_containers_in_compose():
    """docker-compose.dev.yaml must define containers for all 4 MCP domains."""
    compose = REPO_ROOT / "deploy" / "compose" / "docker-compose.dev.yaml"
    if not compose.exists():
        pytest.skip("docker-compose.dev.yaml not found")
    content = compose.read_text()
    for domain in ("mcp-inventory", "mcp-equipment", "mcp-labor", "mcp-wave"):
        assert (
            domain in content
        ), f"docker-compose.dev.yaml must define {domain} service"
