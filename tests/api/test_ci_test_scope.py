# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""The CORE CI test scope is stated once and run everywhere.

`.github/workflows/ci-cd.yml`, `scripts/testing/run_core_ci.sh` and
docs/architecture/TEST_STRATEGY.md must name the same test paths and the
same ignored files, and every directory that holds test files must be either
in that scope or listed below with the reason it is not. A new test
directory that no command collects fails here instead of going unnoticed
(packages/maiw-world/tests went unrun until 2026-11).
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CI = REPO_ROOT / ".github/workflows/ci-cd.yml"
SCRIPT = REPO_ROOT / "scripts/testing/run_core_ci.sh"
STRATEGY = REPO_ROOT / "docs/architecture/TEST_STRATEGY.md"
WORLD_RUN = "pytest packages/maiw-world/tests --timeout=120"

# Directories with test files that CORE CI does not collect, and why.
NOT_IN_CORE = {
    "tests/integration": "needs a running API server and database",
    "tests/quality": "needs a running API server and a model endpoint",
    "tests/real_sandbox": "needs a qualified NemoClaw/OpenShell host",
    "scripts/testing": "manual smoke and probe scripts, not a test suite",
    "src/adapters/iot/tests": "21 of 51 fail; restoration step in TEST_STRATEGY.md",
    "src/adapters/wms/tests": "fails with the IoT adapters; same step",
}
SKIP_DIRS = {".git", ".venv", "node_modules", "build", "__pycache__"}


def _scope(command: str) -> tuple[list[str], list[str]]:
    tokens = shlex.split(command.replace("\\\n", " "))
    start = tokens.index("pytest") + 1
    paths = [
        t.rstrip("/") for t in tokens[start:] if not t.startswith("-") and "/" in t
    ]
    ignores = [t.split("=", 1)[1] for t in tokens[start:] if t.startswith("--ignore=")]
    return paths, ignores


def _ci_steps() -> dict:
    steps = yaml.safe_load(CI.read_text())["jobs"]["test"]["steps"]
    return {s.get("name"): s for s in steps}


def _ci_scope():
    return _scope(_ci_steps()["Run Python tests"]["run"])


def _script_scope():
    text = SCRIPT.read_text()
    first = text[text.index("python -m pytest") : text.index('"$@"')]
    return _scope(first)


def _strategy_scope():
    block = re.search(
        r"## Canonical CORE CI Command\s+```bash\n(.*?)```", STRATEGY.read_text(), re.S
    )
    assert block, "TEST_STRATEGY.md lost its canonical command block"
    main = block.group(1).split("\n\n")[0]
    return _scope(main), block.group(1)


def test_ci_script_and_strategy_name_the_same_scope():
    ci_paths, ci_ignores = _ci_scope()
    (doc_paths, doc_ignores), _ = _strategy_scope()
    assert _script_scope() == (ci_paths, ci_ignores)
    assert (doc_paths, sorted(doc_ignores)) == (ci_paths, sorted(ci_ignores))


def test_maiw_world_runs_in_its_own_invocation_everywhere():
    assert _ci_steps()["Run maiw-world package tests"]["run"] == WORLD_RUN
    assert f"exec python -m {WORLD_RUN}" in SCRIPT.read_text()
    _, block = _strategy_scope()
    assert f"python -m {WORLD_RUN}" in block
    # Collected together with tests/ it fails: both are packages named "tests".
    assert "packages/maiw-world/tests" not in _ci_scope()[0]


def test_every_test_directory_is_run_or_explained():
    paths, ignores = _ci_scope()
    covered = list(paths)
    if WORLD_RUN in _ci_steps().get("Run maiw-world package tests", {}).get("run", ""):
        covered.append("packages/maiw-world/tests")
    ignored = set(ignores)
    unexplained = set()
    for f in REPO_ROOT.rglob("test_*.py"):
        rel = f.relative_to(REPO_ROOT)
        if SKIP_DIRS & set(rel.parts):
            continue
        rel_s = rel.as_posix()
        if rel_s in ignored:
            continue
        if any(rel_s.startswith(p + "/") for p in covered):
            continue
        if any(rel_s.startswith(p + "/") for p in NOT_IN_CORE):
            continue
        unexplained.add(rel.parent.as_posix())
    assert not unexplained, f"test directories no command runs: {sorted(unexplained)}"


def test_exclusions_are_listed_in_the_strategy():
    text = STRATEGY.read_text()
    # Ignored files appear by file name in the status table, directories by path.
    for name in [Path(p).name for p in _ci_scope()[1]] + list(NOT_IN_CORE):
        assert (
            re.search(rf"`{re.escape(name)}[`,]", text) or f"`{name}`" in text
        ), f"TEST_STRATEGY.md does not explain {name}"
