# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.0.1 round 3 — reproducible OpenShell gateway step (third re-audit N-9 / §28).

The runbook listed "a running OpenShell gateway" as a prerequisite with no step
to start or verify it.  ``scripts/setup/reference_gateway.sh`` is that step.

These tests run the script with FAKE ``openshell`` / ``openshell-gateway``
binaries on PATH (no real gateway is ever contacted or started) and check the
safety contract: external gateways are verified, never started or stopped;
a managed gateway is only ever this deployment's own (its own endpoint on
loopback, its own marker); misconfiguration refuses.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "setup" / "reference_gateway.sh"

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="bash + /proc")


def _fake_bin(tmp_path: Path, *, reachable: bool, version: str = "0.0.116") -> Path:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    log = tmp_path / "openshell_calls.log"
    rc = 0 if reachable else 1
    (bindir / "openshell").write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> "{log}"\n'
        f'if [ "$1" = "--version" ]; then echo "openshell {version}"; exit 0; fi\n'
        f"exit {rc}\n"
    )
    for name in ("openshell",):
        p = bindir / name
        p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return bindir


def _run(tmp_path: Path, action: str, env_values: dict, bindir: Path):
    env_file = tmp_path / "gw.env"
    env_file.write_text("".join(f"{k}={v}\n" for k, v in env_values.items()))
    env = {
        "PATH": f"{bindir}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "MAIW_ENV_FILE": str(env_file),
    }
    return subprocess.run(
        ["bash", str(SCRIPT), action],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _values(tmp_path: Path, **over) -> dict:
    values = {
        "MAIW_PERSISTENCE_ROOT": str(tmp_path / "maiw"),
        "OPENSHELL_GATEWAY_ENDPOINT": "http://127.0.0.1:18999",
        "MAIW_OPENSHELL_GATEWAY_MODE": "managed",
        "MAIW_OPENSHELL_GATEWAY_NAME": "maiw-test-gw",
        "MAIW_OPENSHELL_GATEWAY_PORT": "18999",
    }
    values.update(over)
    return values


def test_script_uses_shared_loader_and_never_kills_by_name_or_port():
    text = SCRIPT.read_text()
    assert "lib/load_env.sh" in text and "maiw_load_env" in text
    for bad in ("pkill", "pgrep", "killall", "lsof -ti", "fuser"):
        assert bad not in text, bad
    # the only signals go to the PID recorded by this script, after _pid_ok
    assert 'kill -TERM "$PID"' in text
    assert text.index("_pid_ok; then\n            PID=") > 0


def test_external_mode_verifies_and_never_starts(tmp_path):
    bindir = _fake_bin(tmp_path, reachable=True)
    res = _run(
        tmp_path,
        "start",
        _values(tmp_path, MAIW_OPENSHELL_GATEWAY_MODE="external"),
        bindir,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "PASS  OpenShell gateway reachable" in res.stdout
    calls = (tmp_path / "openshell_calls.log").read_text()
    # every gateway call targeted the configured endpoint only
    for line in calls.splitlines():
        if line != "--version":
            assert "--gateway-endpoint http://127.0.0.1:18999" in line, line


def test_external_mode_down_fails_with_guidance(tmp_path):
    bindir = _fake_bin(tmp_path, reachable=False)
    res = _run(
        tmp_path,
        "start",
        _values(tmp_path, MAIW_OPENSHELL_GATEWAY_MODE="external"),
        bindir,
    )
    assert res.returncode == 1
    assert "not reachable" in res.stderr
    assert "never starts or stops an external gateway" in res.stderr


def test_external_mode_stop_refuses(tmp_path):
    bindir = _fake_bin(tmp_path, reachable=True)
    res = _run(
        tmp_path,
        "stop",
        _values(tmp_path, MAIW_OPENSHELL_GATEWAY_MODE="external"),
        bindir,
    )
    assert res.returncode == 2
    assert "REFUSED" in res.stderr


def test_wrong_cli_version_fails(tmp_path):
    bindir = _fake_bin(tmp_path, reachable=True, version="0.0.115")
    res = _run(
        tmp_path,
        "status",
        _values(tmp_path, MAIW_OPENSHELL_GATEWAY_MODE="external"),
        bindir,
    )
    assert res.returncode == 1
    assert "required 0.0.116" in res.stderr


def test_managed_mode_requires_its_own_loopback_endpoint(tmp_path):
    bindir = _fake_bin(tmp_path, reachable=True)
    res = _run(
        tmp_path,
        "start",
        _values(tmp_path, OPENSHELL_GATEWAY_ENDPOINT="https://127.0.0.1:8991"),
        bindir,
    )
    assert res.returncode == 2
    assert "managed mode requires OPENSHELL_GATEWAY_ENDPOINT" in res.stderr


def test_managed_status_not_running_and_stop_without_marker(tmp_path):
    bindir = _fake_bin(tmp_path, reachable=True)
    status = _run(tmp_path, "status", _values(tmp_path), bindir)
    assert status.returncode == 1
    assert "NOT RUNNING" in status.stderr
    stop = _run(tmp_path, "stop", _values(tmp_path), bindir)
    assert stop.returncode == 2
    assert "no gateway was started by this script" in stop.stderr


def test_missing_required_configuration_refuses(tmp_path):
    bindir = _fake_bin(tmp_path, reachable=True)
    values = _values(tmp_path)
    del values["OPENSHELL_GATEWAY_ENDPOINT"]
    res = _run(tmp_path, "status", values, bindir)
    assert res.returncode != 0
    assert "OPENSHELL_GATEWAY_ENDPOINT" in res.stdout + res.stderr


def test_runbook_and_env_example_document_the_gateway_step():
    runbook = (REPO / "docs/operations/REFERENCE_DEPLOYMENT_RUNBOOK.md").read_text()
    block = runbook.split("## Clean-host procedure", 1)[1].split("```", 2)[1]
    assert "bash scripts/setup/reference_gateway.sh start" in block
    assert "bash scripts/setup/reference_gateway.sh status" in block
    assert block.index("reference_gateway.sh start") < block.index(
        "reference_sandbox.sh create"
    )
    assert "## OpenShell gateway" in runbook
    env_example = (REPO / ".env.example").read_text()
    for var in (
        "OPENSHELL_GATEWAY_ENDPOINT",
        "MAIW_OPENSHELL_GATEWAY_MODE",
        "MAIW_OPENSHELL_GATEWAY_NAME",
        "MAIW_OPENSHELL_GATEWAY_PORT",
    ):
        assert f"\n{var}=" in env_example, var
    assert os.access(SCRIPT, os.X_OK)
