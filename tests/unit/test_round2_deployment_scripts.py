# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.0.1 round 2 — NEW-P1-02 / P2-01: reference-deployment lifecycle scripts.

Every script runs in a temp deployment (own persistence root, own ephemeral
ports, own env file via MAIW_ENV_FILE) with a minimal environment.  Decoys are
this test's own harmless processes.  Nothing here contacts a port the test
did not open.

Covers spec §15-§19, §47, §48:
  * one env loader (parse, never execute; shell precedence; PYTHON_DOTENV_DISABLED)
  * preflight validates the effective configuration (env loaded first; the
    physical model check is the runtime's own resolver)
  * no localhost/default-port fallback: smoke/status/restart refuse without a
    verified deployment identity and send NO request to a decoy listener
  * stop never kills a decoy (no pidfile, forged pidfile, stale pidfile)
  * full start → status → smoke → restart → stop on the canonical app
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import socket
import subprocess
import sys
import textwrap
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="lifecycle scripts use /proc (Linux only)"
)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _base_env(tmp_path: Path, port: int, extra: dict | None = None) -> dict:
    """Minimal process env + a private env file (MAIW_ENV_FILE)."""
    root = tmp_path / "deploy" / "maiw"
    values = {
        "MAIW_PERSISTENCE_ROOT": str(root),
        "MAIW_API_PORT": str(port),
        "MAIW_API_HOST": "127.0.0.1",
        "MAIW_PYTHON": sys.executable,
        "MAIW_DEPLOYMENT_PROFILE": "reference",
        "MAIW_SANDBOX_MODE": "disabled",
        "MAIW_READINESS_REQUIRE_DATABASE": "false",
        "PGHOST": "127.0.0.1",
        "PGPORT": str(_free_port()),  # closed: nothing foreign is contacted
        "MAIW_NIM_BASE_URL": f"http://127.0.0.1:{_free_port()}/v1",
        "LLM_NIM_URL": f"http://127.0.0.1:{_free_port()}/v1",
        "NVIDIA_API_KEY": "fake-test-key-not-real",
        "POSTGRES_PASSWORD": "not-a-real-password",
        "LLM_CACHE_ENABLED": "false",
        "MAIW_STARTUP_TIMEOUT_SECONDS": "30",
        "MAIW_READINESS_TIMEOUT_S": "90",
    }
    values.update(extra or {})
    env_file = tmp_path / "test.env"
    env_file.write_text("".join(f"{k}={v}\n" for k, v in values.items()))
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "MAIW_ENV_FILE": str(env_file),
        "LANG": "C.UTF-8",
    }
    return env


def _run(script: str, env: dict, *args: str, timeout: int = 180):
    return subprocess.run(
        ["bash", str(SCRIPTS / script), *args],
        env=env,
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


class _Decoy:
    """An unrelated HTTP listener in its OWN process; records requests."""

    def __init__(self, tmp_path: Path, port: int) -> None:
        self.log = tmp_path / f"decoy_{port}.jsonl"
        code = textwrap.dedent(f"""
            import json, sys
            from http.server import BaseHTTPRequestHandler, HTTPServer
            class H(BaseHTTPRequestHandler):
                def log_message(self, *a): pass
                def _rec(self):
                    with open({str(self.log)!r}, "a") as f:
                        f.write(json.dumps({{"m": self.command, "p": self.path}}) + "\\n")
                    self.send_response(200); self.end_headers()
                    self.wfile.write(b'{{"status": "alive"}}')
                do_GET = do_POST = do_PUT = _rec
            HTTPServer(("127.0.0.1", {port}), H).serve_forever()
            """)
        self.proc = subprocess.Popen([sys.executable, "-c", code])
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.05)
        self.log.write_text("")  # ignore our own readiness probe connection

    def requests(self) -> list:
        return [json.loads(ln) for ln in self.log.read_text().splitlines() if ln]

    def alive(self) -> bool:
        return self.proc.poll() is None

    def close(self) -> None:
        if self.alive():
            self.proc.terminate()
            self.proc.wait(timeout=10)


@pytest.fixture
def decoy(tmp_path):
    port = _free_port()
    d = _Decoy(tmp_path, port)
    yield d, port
    d.close()


# ── env loader ───────────────────────────────────────────────────────────────


def test_load_env_parses_without_executing_and_shell_wins(tmp_path):
    marker = tmp_path / "executed"
    env_file = tmp_path / "x.env"
    env_file.write_text(textwrap.dedent(f"""
            # comment
            A=plain
            B="double quoted # not a comment"
            C='single $HOME'
            D=value   # inline comment
            export E=exported
            F=http://<HOST_IP>:8001/api/v1/inference
            G=$(touch {marker})
            KEEP=from-file
            """))
    script = (
        f"source {SCRIPTS}/lib/load_env.sh; "
        f"MAIW_ENV_FILE={env_file} maiw_load_env {REPO} >/dev/null; "
        'printf \'%s|\' "$A" "$B" "$C" "$D" "$E" "$F" "$G" "$KEEP" '
        '"$PYTHON_DOTENV_DISABLED"'
    )
    out = subprocess.run(
        ["bash", "-c", script],
        env={"PATH": os.environ["PATH"], "KEEP": "from-shell"},
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert out.split("|")[:9] == [
        "plain",
        "double quoted # not a comment",
        "single $HOME",
        "value",
        "exported",
        "http://<HOST_IP>:8001/api/v1/inference",
        f"$(touch {marker})",
        "from-shell",
        "1",
    ]
    assert not marker.exists()  # nothing was executed


def test_env_example_loads_cleanly():
    script = (
        f"source {SCRIPTS}/lib/load_env.sh; "
        f"MAIW_ENV_FILE={REPO}/.env.example maiw_load_env {REPO}"
    )
    res = subprocess.run(
        ["bash", "-c", script],
        env={"PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, res.stderr
    assert "0 ignored" in res.stdout
    assert "malformed" not in res.stderr


@pytest.mark.parametrize(
    "script",
    [
        "preflight_reference_deployment.sh",
        "start_reference_deployment.sh",
        "stop_reference_deployment.sh",
        "restart_reference_deployment.sh",
        "status_reference_deployment.sh",
        "smoke_test_reference_deployment.sh",
        "qualify_reference_deployment.sh",
        "setup/reference_db.sh",
        "setup/reference_sandbox.sh",
    ],
)
def test_every_lifecycle_script_uses_the_shared_loader(script):
    text = (SCRIPTS / script).read_text()
    assert "lib/load_env.sh" in text and "maiw_load_env" in text
    assert 'source "$PROJECT_ROOT/.env"' not in text
    # no default-port fallback anywhere in the lifecycle scripts
    assert "MAIW_API_PORT:-8001" not in text
    assert "lsof -ti" not in text and "pgrep -f" not in text


def test_preflight_loads_env_before_validating(tmp_path):
    text = (SCRIPTS / "preflight_reference_deployment.sh").read_text()
    assert text.index("maiw_load_env") < text.index("Check 1:")
    start = (SCRIPTS / "start_reference_deployment.sh").read_text()
    assert start.index("maiw_load_env") < start.index(
        'preflight_reference_deployment.sh"'
    )


# ── preflight validates the effective (runtime) model configuration ──────────


def test_preflight_rejects_unapproved_physical_model_from_env_file(tmp_path):
    env = _base_env(
        tmp_path,
        _free_port(),
        {"NEMOTRON_SUPER_MODEL": "example-org/unapproved-model-x"},
    )
    res = _run("preflight_reference_deployment.sh", env)
    assert res.returncode == 1
    out = res.stdout + res.stderr
    assert "MAIW_API_PORT set" in out  # values came from the env file
    assert "role=super" in out and "UNAPPROVED_MODEL_ID" in out


def test_preflight_accepts_approved_defaults(tmp_path):
    env = _base_env(tmp_path, _free_port())
    res = _run("preflight_reference_deployment.sh", env)
    out = res.stdout + res.stderr
    assert "PASS  role=super" in out and "nvidia/nemotron-3-super-120b-a12b" in out
    assert "PASS  role=lightning" in out
    assert "FAIL  role=" not in out


def test_preflight_requires_explicit_port(tmp_path):
    env = _base_env(tmp_path, _free_port())
    text = Path(env["MAIW_ENV_FILE"]).read_text()
    Path(env["MAIW_ENV_FILE"]).write_text(
        "\n".join(ln for ln in text.splitlines() if not ln.startswith("MAIW_API_PORT"))
    )
    res = _run("preflight_reference_deployment.sh", env)
    assert res.returncode == 1
    assert "no defaults are assumed" in res.stderr


# ── no fallback / wrong target (§17, §19, §47) ───────────────────────────────


@pytest.mark.parametrize(
    "script,code",
    [
        ("smoke_test_reference_deployment.sh", 2),
        ("restart_reference_deployment.sh", 2),
        ("status_reference_deployment.sh", 1),
    ],
)
def test_no_identity_refuses_and_never_contacts_decoy(tmp_path, decoy, script, code):
    d, port = decoy
    env = _base_env(tmp_path, port)
    res = _run(script, env)
    assert res.returncode == code, res.stdout + res.stderr
    assert "NOT RUNNING / CANNOT VERIFY" in res.stdout + res.stderr
    assert d.requests() == []  # zero requests reached the decoy
    assert d.alive()


def test_stop_without_state_never_kills_decoy_listener(tmp_path, decoy):
    d, port = decoy
    env = _base_env(tmp_path, port)
    res = _run("stop_reference_deployment.sh", env)
    assert res.returncode == 0
    assert "NOT RUNNING / CANNOT VERIFY" in res.stdout
    assert "Nothing was signalled" in res.stdout
    time.sleep(0.5)
    assert d.alive()
    assert d.requests() == []


def _forge_instance(tmp_path: Path, env: dict, pid: int, port: int) -> Path:
    from_file = dict(
        ln.split("=", 1)
        for ln in Path(env["MAIW_ENV_FILE"]).read_text().splitlines()
        if "=" in ln
    )
    runtime = Path(from_file["MAIW_PERSISTENCE_ROOT"]) / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    inst = runtime / "maiw-api.instance"
    inst.write_text(
        f"instance_id=0123456789abcdef-forged\npid={pid}\nhost=127.0.0.1\n"
        f"port={port}\nproject_root={REPO}\napp=maiw_api.app:app\n"
    )
    return inst


def test_forged_state_pointing_at_decoy_is_refused(tmp_path, decoy):
    d, port = decoy
    env = _base_env(tmp_path, port)
    inst = _forge_instance(tmp_path, env, d.proc.pid, port)
    stop = _run("stop_reference_deployment.sh", env)
    assert stop.returncode == 3
    assert "is not this MAIW instance" in stop.stdout + stop.stderr
    smoke = _run("smoke_test_reference_deployment.sh", env)
    assert smoke.returncode == 2
    restart = _run("restart_reference_deployment.sh", env)
    assert restart.returncode == 2
    time.sleep(0.5)
    assert d.alive()
    assert d.requests() == []
    assert inst.exists()  # left for the operator to investigate


def test_stale_state_is_cleared_without_signalling(tmp_path, decoy):
    d, port = decoy
    env = _base_env(tmp_path, port)
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    inst = _forge_instance(tmp_path, env, dead.pid, port)
    res = _run("stop_reference_deployment.sh", env)
    assert res.returncode == 0
    assert "stale" in res.stdout
    assert not inst.exists()
    assert d.alive()


# ── the full lifecycle on the canonical app (§24 in miniature) ───────────────


class _FakeProvider:
    def __init__(self) -> None:
        self.models: list[str] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                return

            def do_GET(self):  # /v1/models
                out = json.dumps({"object": "list", "data": []}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.models.append(body.get("model"))
                out = json.dumps(
                    {
                        "model": body.get("model"),
                        "choices": [
                            {
                                "message": {"role": "assistant", "content": "OK"},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {},
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.mark.timeout(600)
def test_lifecycle_start_status_smoke_restart_stop(tmp_path, decoy):
    import secrets

    d, decoy_port = decoy
    provider = _FakeProvider()
    port = _free_port()
    env = _base_env(
        tmp_path,
        port,
        {
            "MAIW_NIM_BASE_URL": provider.url,
            "LLM_NIM_URL": provider.url,
            "MAIW_INFERENCE_INTERNAL_TOKEN": secrets.token_hex(32),
        },
    )
    inst = tmp_path / "deploy" / "maiw" / "runtime" / "maiw-api.instance"
    try:
        start = _run("start_reference_deployment.sh", env, "--skip-preflight")
        assert start.returncode == 0, start.stdout + start.stderr
        assert inst.exists()
        state = dict(ln.split("=", 1) for ln in inst.read_text().splitlines())
        assert state["port"] == str(port)
        pid1 = int(state["pid"])

        status = _run("status_reference_deployment.sh", env)
        assert status.returncode == 0, status.stdout + status.stderr
        assert "MAIW IS USABLE" in status.stdout

        smoke = _run("smoke_test_reference_deployment.sh", env)
        assert smoke.returncode == 0, smoke.stdout + smoke.stderr
        assert "Physical model identity" in smoke.stdout
        assert "nvidia/nemotron-3-super-120b-a12b" in smoke.stdout
        assert set(provider.models) <= {"nvidia/nemotron-3-super-120b-a12b"}

        # restart runs preflight BEFORE stopping: this test env cannot pass it
        # (sandbox mode disabled), so the running instance must be untouched
        refused = _run("restart_reference_deployment.sh", env)
        assert refused.returncode == 1, refused.stdout + refused.stderr
        assert "left untouched" in refused.stderr
        # the port held by OUR verified instance is not a preflight failure
        assert "held by this deployment's verified instance" in refused.stdout
        assert "FAIL  Port" not in refused.stderr
        os.kill(pid1, 0)  # still running
        assert inst.exists()

        restart = _run("restart_reference_deployment.sh", env, "--skip-preflight")
        assert restart.returncode == 0, restart.stdout + restart.stderr
        state2 = dict(ln.split("=", 1) for ln in inst.read_text().splitlines())
        assert int(state2["pid"]) != pid1
        assert state2["instance_id"] != state["instance_id"]

        stop = _run("stop_reference_deployment.sh", env)
        assert stop.returncode == 0, stop.stdout + stop.stderr
        assert "MAIW API stopped" in stop.stdout
        assert not inst.exists()
        for pid in (pid1, int(state2["pid"])):
            with pytest.raises(ProcessLookupError):
                os.kill(pid, 0)
        # the decoy on another port was never touched
        assert d.alive() and d.requests() == []
    finally:
        provider.close()
        if inst.exists():  # cleanup only OUR instance
            pid = int(
                dict(ln.split("=", 1) for ln in inst.read_text().splitlines())["pid"]
            )
            with contextlib.suppress(ProcessLookupError):  # already exited
                os.kill(pid, signal.SIGTERM)


def test_runbook_validation_script_passes():
    res = subprocess.run(
        ["bash", str(SCRIPTS / "validate_reference_runbook.sh")],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert res.returncode == 0, res.stdout + res.stderr
    assert "RUNBOOK VALIDATION PASSED" in res.stdout
