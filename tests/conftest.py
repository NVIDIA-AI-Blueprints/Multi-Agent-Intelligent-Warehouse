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
Pytest configuration and fixtures for unit tests.

Provides shared fixtures and configuration for pytest-based tests.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Generator

# Tests must never read a developer's ``.env``: the app calls ``load_dotenv()``
# in its lifespan and health checks, so a stray ``.env`` would leak settings
# into whichever test happens to start the app first.  python-dotenv >= 1.1
# makes ``load_dotenv()`` a no-op when PYTHON_DOTENV_DISABLED is truthy.
# ``setdefault`` keeps an explicit caller value (CI already exports it).
os.environ.setdefault("PYTHON_DOTENV_DISABLED", "1")

# Project root must precede site-packages so ``from tests.unit...`` resolves here,
# not a third-party ``tests`` distribution (e.g. transitive test helpers).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
_root = str(PROJECT_ROOT)
if sys.path[0] != _root:
    try:
        sys.path.remove(_root)
    except ValueError:
        pass
    sys.path.insert(0, _root)

import pytest


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Get project root directory."""
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def api_base_url() -> str:
    """
    Get API base URL from environment.

    Security: HTTP protocol is acceptable for localhost in test environments.
    For production deployments, HTTPS must be used to encrypt API communications.
    """
    # Security: HTTP is acceptable for localhost (development/testing only)
    # Production external services must use HTTPS
    return os.getenv("API_BASE_URL", "http://localhost:8001")


@pytest.fixture(scope="session")
def chat_endpoint(api_base_url: str) -> str:
    """Get chat endpoint URL."""
    return f"{api_base_url}/api/v1/chat"


@pytest.fixture(scope="session")
def health_endpoint(api_base_url: str) -> str:
    """Get health endpoint URL."""
    return f"{api_base_url}/api/v1/health/simple"


@pytest.fixture(scope="session")
def test_timeout() -> int:
    """Get test timeout from environment."""
    return int(os.getenv("TEST_TIMEOUT", "180"))


@pytest.fixture(scope="session")
def guardrails_timeout() -> int:
    """Get guardrails timeout from environment."""
    return int(os.getenv("GUARDRAILS_TIMEOUT", "60"))


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """
    Create event loop for async tests.

    This fixture ensures that async tests have a proper event loop.
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
def test_session_id() -> str:
    """Generate a unique test session ID."""
    from datetime import datetime

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return f"test_session_{timestamp}"


@pytest.fixture(scope="function")
def nvidia_api_key() -> str:
    """Get NVIDIA API key from environment."""
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key or api_key == "your_nvidia_api_key_here":
        pytest.skip("NVIDIA_API_KEY not configured")
    return api_key


@pytest.fixture(scope="function")
def test_data_dir(project_root: Path) -> Path:
    """Get test data directory."""
    test_dir = project_root / "tests" / "fixtures"
    test_dir.mkdir(parents=True, exist_ok=True)
    return test_dir


@pytest.fixture(scope="function", autouse=True)
def setup_test_environment() -> Generator[None, None, None]:
    """Reserved for per-test environment hooks (project root is set at conftest import)."""
    yield


# ── Process-global singleton isolation ───────────────────────────────────────
#
# Lazily-created, process-wide singletons that tests under tests/ create or
# replace.  Every entry's module-level default is ``None`` (or, for
# _TASK_REGISTRY, an empty dict).  The fixture below snapshots each one (and
# ``os.environ``) before a test and restores it afterwards, so no test can
# hand its singleton (often bound to a mock, a closed fake server, a reloaded
# app or a patched ``SQLRetriever.initialize``) to whichever test runs next.
# Snapshots are taken after module/class-scoped fixtures run, so state those
# fixtures install is preserved for their own tests.  A module first imported
# during the test is reset to the module default.
#
#   (module, attribute path)
_PROCESS_SINGLETONS: tuple[tuple[str, str], ...] = (
    ("maiw_models", "_gateway_instance"),  # reset_model_gateway()
    ("maiw_models.providers.nim_client", "_nim_client"),  # close_nim_client()
    ("maiw_api.bootstrap", "_runtime"),  # reset_runtime()
    ("maiw_api.demo.controller", "_controller"),  # reset_demo_controller()
    # configure_server(provider) has no reset hook; None = lazy default build.
    ("mcp_servers.inventory.server", "_provider"),
    ("mcp_servers.equipment.server", "_provider"),
    ("mcp_servers.labor.server", "_provider"),
    ("mcp_servers.wave.server", "_provider"),
    ("maiw_api.routers.equipment", "_sql"),
    ("maiw_api.routers.operations", "_sql"),
    ("maiw_api.routers.operations", "_task_queries"),
    ("maiw_api.routers.safety", "_sql"),
    # SQLRetriever is a __new__ singleton whose DatabaseConfig is read from the
    # environment on first construction only.
    ("src.retrieval.structured.sql_retriever", "SQLRetriever._instance"),
    ("src.retrieval.structured.sql_retriever", "_sql_retriever"),
    ("src.api.services.llm.nim_client", "_nim_client"),
    # In-memory request counters live on this singleton (REDIS is stubbed).
    ("src.api.services.security.rate_limiter", "_rate_limiter"),
    ("src.api.services.agent_config", "_config_loader"),
    ("src.api.agents.inventory.equipment_asset_tools", "_equipment_asset_tools"),
    (
        "src.api.agents.forecasting.forecasting_action_tools",
        "_forecasting_action_tools",
    ),
)
_MISSING = object()


def _resolve_owner(module_name: str, path: str):
    """Return (owner object, attribute name) or (None, None) if not imported."""
    module = sys.modules.get(module_name)
    if module is None:
        return None, None
    owner = module
    *parents, attr = path.split(".")
    for part in parents:
        owner = getattr(owner, part, None)
        if owner is None:
            return None, None
    return owner, attr


@pytest.fixture(autouse=True)
def _isolate_process_singletons() -> Generator[None, None, None]:
    """Restore documented process-global singletons (and os.environ) after every test."""
    saved_environ = dict(os.environ)
    saved = {}
    for module_name, path in _PROCESS_SINGLETONS:
        owner, attr = _resolve_owner(module_name, path)
        if owner is not None:
            saved[(module_name, path)] = getattr(owner, attr, _MISSING)
    registry_mod = sys.modules.get("maiw_api.routers.agent_tasks")
    saved_tasks = (
        dict(registry_mod._TASK_REGISTRY) if registry_mod is not None else None
    )
    yield
    for module_name, path in _PROCESS_SINGLETONS:
        owner, attr = _resolve_owner(module_name, path)
        if owner is None:
            continue
        value = saved.get((module_name, path), None)  # first import → default
        if value is not _MISSING:
            setattr(owner, attr, value)
    registry_mod = sys.modules.get("maiw_api.routers.agent_tasks")
    if registry_mod is not None:
        registry_mod._TASK_REGISTRY.clear()
        registry_mod._TASK_REGISTRY.update(saved_tasks or {})
    # Environment: undo raw ``os.environ`` writes that bypassed monkeypatch
    # (including production ``os.environ.setdefault`` calls such as
    # LANGSMITH_TRACING in maiw_agents.runtime.deep_agents_runtime).
    if os.environ != saved_environ:
        for key in set(os.environ) - set(saved_environ):
            del os.environ[key]
        for key, value in saved_environ.items():
            if os.environ.get(key) != value:
                os.environ[key] = value
