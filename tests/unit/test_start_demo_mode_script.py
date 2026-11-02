# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
scripts/start_demo_mode.sh must start a READY demo-profile API even when .env
is a copy of .env.example.

.env.example selects MAIW_DEPLOYMENT_PROFILE=reference, MAIW_SANDBOX_MODE=required,
MAIW_PERSISTENCE_ROOT=/var/lib/maiw and MAIW_API_HOST=0.0.0.0.  An explicit
profile beats MAIW_DEMO_MODE, so the script has to force the demo profile.

Each test copies the script into a throwaway repo tree whose interpreter is a
stub: it answers the ``-c "import maiw_api"`` preflight and records the
environment and argv of the final ``exec`` instead of starting uvicorn.  No
server starts and no network is used.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "start_demo_mode.sh"

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="bash script under test"
)

STUB = """#!/usr/bin/env bash
if [[ "${1:-}" == "-c" ]]; then exit 0; fi
printf '%s\\n' "$(basename "$0")" "$@" > "$STUB_OUT.args"
env > "$STUB_OUT.env"
"""


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _write_stub(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(STUB)
    path.chmod(0o755)


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "scripts" / "lib").mkdir(parents=True)
    shutil.copy2(SCRIPT, root / "scripts" / "start_demo_mode.sh")
    shutil.copy2(
        REPO / "scripts" / "lib" / "load_env.sh",
        root / "scripts" / "lib" / "load_env.sh",
    )
    pack = root / "data" / "worlds" / "dc47-demo-v1"
    pack.mkdir(parents=True)
    (pack / "manifest.json").write_text("{}")
    shutil.copy2(REPO / ".env.example", root / ".env")
    return root


def _run(root: Path, tmp_path: Path, extra: dict | None = None) -> tuple[list, dict]:
    out = tmp_path / "exec"
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "STUB_OUT": str(out),
        "DEMO_PORT": str(_free_port()),
    }
    env.update(extra or {})
    proc = subprocess.run(
        ["bash", str(root / "scripts" / "start_demo_mode.sh")],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    args = Path(f"{out}.args").read_text().splitlines()
    exec_env = dict(
        line.split("=", 1)
        for line in Path(f"{out}.env").read_text().splitlines()
        if "=" in line
    )
    return args, exec_env


def _host_port(args: list) -> tuple[str, str]:
    return args[args.index("--host") + 1], args[args.index("--port") + 1]


def test_env_example_copy_still_selects_the_demo_profile(fake_repo, tmp_path):
    _write_stub(fake_repo / ".venv" / "bin" / "python")
    args, env = _run(fake_repo, tmp_path)

    assert args[1:4] == ["-m", "uvicorn", "maiw_api.app:app"]
    assert env["MAIW_DEMO_MODE"] == "true"
    assert env["MAIW_DEPLOYMENT_PROFILE"] == "demo"
    assert env["MAIW_SANDBOX_MODE"] == "disabled"
    assert env["MAIW_READINESS_REQUIRE_DATABASE"] == "false"
    assert env["MAIW_PERSISTENCE_MODE"] == "memory"
    assert "MAIW_PERSISTENCE_ROOT" not in env
    # .env was loaded (parsed, not sourced) and the app will not reload it.
    assert env["MAIW_ENV_LOADED_FROM"] == str(fake_repo / ".env")
    assert env["PYTHON_DOTENV_DISABLED"] == "1"


def test_resolved_profile_is_demo_with_no_sandbox_or_database(fake_repo, tmp_path):
    from maiw_api.profile import resolve_profile

    _write_stub(fake_repo / ".venv" / "bin" / "python")
    _, env = _run(fake_repo, tmp_path)

    profile = resolve_profile(env)
    assert profile.valid
    assert profile.name == "demo"
    assert not profile.sandbox_required
    assert not profile.database_required


def test_binds_loopback_by_default_not_env_example_host(fake_repo, tmp_path):
    _write_stub(fake_repo / ".venv" / "bin" / "python")
    port = str(_free_port())
    args, _ = _run(fake_repo, tmp_path, {"DEMO_PORT": port})
    assert _host_port(args) == ("127.0.0.1", port)


def test_demo_host_overrides_bind_address(fake_repo, tmp_path):
    _write_stub(fake_repo / ".venv" / "bin" / "python")
    args, _ = _run(fake_repo, tmp_path, {"DEMO_HOST": "0.0.0.0"})
    assert _host_port(args)[0] == "0.0.0.0"


def test_shell_profile_and_root_do_not_override_demo(fake_repo, tmp_path):
    _write_stub(fake_repo / ".venv" / "bin" / "python")
    _, env = _run(
        fake_repo,
        tmp_path,
        {
            "MAIW_DEPLOYMENT_PROFILE": "reference_governed",
            "MAIW_SANDBOX_MODE": "required",
            "MAIW_PERSISTENCE_ROOT": "/var/lib/maiw",
        },
    )
    assert env["MAIW_DEPLOYMENT_PROFILE"] == "demo"
    assert env["MAIW_SANDBOX_MODE"] == "disabled"
    assert env["MAIW_PERSISTENCE_MODE"] == "memory"
    assert "MAIW_PERSISTENCE_ROOT" not in env


def test_demo_persistence_root_opts_into_file_mode(fake_repo, tmp_path):
    _write_stub(fake_repo / ".venv" / "bin" / "python")
    root = tmp_path / "durable"
    _, env = _run(fake_repo, tmp_path, {"DEMO_PERSISTENCE_ROOT": str(root)})
    assert env["MAIW_PERSISTENCE_MODE"] == "file"
    assert env["MAIW_PERSISTENCE_ROOT"] == str(root)


@pytest.mark.parametrize("venv_dir", [".venv", "env"])
def test_finds_quickstart_venv_or_legacy_env(fake_repo, tmp_path, venv_dir):
    _write_stub(fake_repo / venv_dir / "bin" / "python")
    args, _ = _run(fake_repo, tmp_path)
    assert args[0] == "python"


def test_prefers_dot_venv_over_env(fake_repo, tmp_path):
    _write_stub(fake_repo / ".venv" / "bin" / "python")
    (fake_repo / "env" / "bin").mkdir(parents=True)
    legacy = fake_repo / "env" / "bin" / "python"
    legacy.write_text("#!/usr/bin/env bash\nexit 97\n")
    legacy.chmod(0o755)
    _run(fake_repo, tmp_path)  # would fail on the legacy interpreter


def test_demo_python_overrides_interpreter(fake_repo, tmp_path):
    stub = tmp_path / "custom" / "py"
    _write_stub(stub)
    args, _ = _run(fake_repo, tmp_path, {"DEMO_PYTHON": str(stub)})
    assert args[0] == "py"


def test_missing_interpreter_fails_with_quickstart_hint(fake_repo, tmp_path):
    proc = subprocess.run(
        ["bash", str(fake_repo / "scripts" / "start_demo_mode.sh")],
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 1
    assert "python3 -m venv .venv" in proc.stdout
