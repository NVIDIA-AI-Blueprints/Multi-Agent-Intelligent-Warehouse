# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Preflight and status read the provider probe correctly (#269).

In the v2.1.1 release gate, the 4th back-to-back probe got HTTP 429 for
Lightning and the probe printed "FAIL provider does not serve lightning model
... disable the role": status printed FAIL but exited 0, and the same line
fails preflight.  Now a rate limit is retried and reported WARN "could not
verify", which preflight shows (even with --quiet) without failing; a real
serving problem still fails preflight, and status says the FAIL does not
change its readiness verdict.

Runs the real scripts against a local fake provider; nothing foreign is
contacted.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from tests.unit.test_round2_deployment_scripts import _base_env, _free_port, _run

pytestmark = pytest.mark.skipif(
    sys.platform != "linux", reason="lifecycle scripts use /proc (Linux only)"
)

ULTRA = "nvidia/nemotron-3-ultra-550b-a55b"
LIGHTNING = "nvidia/nemotron-3.5-lightning-30b-a3b"


class _Provider(BaseHTTPRequestHandler):
    """Lists both default models; each completion answers ``answers[model]``."""

    answers: dict[str, int] = {}

    def log_message(self, *args):
        pass

    def _send(self, code: int, body: dict, headers: dict | None = None) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self._send(200, {"data": [{"id": ULTRA}, {"id": LIGHTNING}]})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        model = json.loads(self.rfile.read(length))["model"]
        code = self.answers.get(model, 200)
        if code == 200:
            self._send(200, {"model": model, "choices": []})
        else:
            # Retry-After: 0 keeps the probe's retries instant.
            self._send(code, {"status": code}, {"Retry-After": "0"})


@pytest.fixture
def provider():
    server = HTTPServer(("127.0.0.1", 0), _Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()


def _env(tmp_path, provider, answers: dict[str, int]) -> dict:
    _Provider.answers = answers
    url = f"http://127.0.0.1:{provider.server_port}/v1"
    return _base_env(
        tmp_path, _free_port(), {"MAIW_NIM_BASE_URL": url, "LLM_NIM_URL": url}
    )


@pytest.mark.parametrize("args", [(), ("--quiet",)])
def test_preflight_rate_limit_warns_and_does_not_fail_the_model_check(
    tmp_path, provider, args
):
    res = _run(
        "preflight_reference_deployment.sh",
        _env(tmp_path, provider, {LIGHTNING: 429}),
        *args,
    )
    out = res.stdout + res.stderr
    assert "WARN  provider could not verify lightning model (HTTP 429" in out
    assert "FAIL  provider" not in out
    assert "Model configuration check" not in out  # the exit-code fallback
    assert "test-key" not in out


def test_preflight_quiet_runs_every_check(tmp_path, provider):
    # --quiet used to exit 1 at the first passing check (a `[[ ]] && echo`
    # under `set -e`), printing nothing and checking nothing after it.
    res = _run(
        "preflight_reference_deployment.sh",
        _env(tmp_path, provider, {}),
        "--quiet",
    )
    out = res.stdout + res.stderr
    assert "Preflight summary:" in out
    assert "PASS  " not in out  # passes stay quiet


def test_preflight_still_fails_a_model_that_is_not_served(tmp_path, provider):
    res = _run(
        "preflight_reference_deployment.sh",
        _env(tmp_path, provider, {ULTRA: 404}),
    )
    out = res.stdout + res.stderr
    assert res.returncode == 1
    assert "FAIL  provider does not serve ultra model (HTTP 404" in out
    assert "Disable the role or deploy the approved model" in out


def test_preflight_key_refusal_gets_key_advice(tmp_path, provider):
    res = _run(
        "preflight_reference_deployment.sh",
        _env(tmp_path, provider, {ULTRA: 403}),
    )
    out = res.stdout + res.stderr
    assert res.returncode == 1
    assert "FAIL  provider refused the API key for ultra model (HTTP 403)" in out
    assert "Check the API key" in out
    assert "not approved" not in out  # not the bindings message


def test_status_rate_limit_is_a_warning(tmp_path, provider):
    res = _run(
        "status_reference_deployment.sh",
        _env(tmp_path, provider, {LIGHTNING: 429}),
    )
    out = res.stdout + res.stderr
    assert "WARN  provider could not verify lightning model (HTTP 429" in out
    assert "FAIL  provider" not in out
    assert "NOTE: the model check found a configuration problem" not in out


def test_status_says_a_model_failure_does_not_change_its_verdict(tmp_path, provider):
    res = _run(
        "status_reference_deployment.sh",
        _env(tmp_path, provider, {ULTRA: 404}),
    )
    out = res.stdout + res.stderr
    assert "FAIL  provider does not serve ultra model (HTTP 404" in out
    assert "NOTE: the model check found a configuration problem" in out
    # No instance is running, so the readiness verdict is NOT USABLE either way.
    assert "MAIW IS NOT USABLE" in out
