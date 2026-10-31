# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.1.0 — scripts/lib/check_model_config.py --provider-probe dispatches.

The hosted catalogue kept listing Nemotron 3 Super after its 2026-10-19
retirement while every completion returned HTTP 404, so the probe sends each
enabled model one minimal completion and fails unless it answers as that
model.  A local fake provider stands in for the hosted endpoint.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "lib" / "check_model_config.py"
)
SUPER = "nvidia/nemotron-3-super-120b-a12b"
ULTRA = "nvidia/nemotron-3-ultra-550b-a55b"
LIGHTNING = "nvidia/nemotron-3.5-lightning-30b-a3b"


def _load():
    spec = importlib.util.spec_from_file_location("check_model_config", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Provider(BaseHTTPRequestHandler):
    """Lists every model; serves completions only for ``served``."""

    served: dict[str, str] = {}
    auth_seen: list[str] = []

    def log_message(self, *args):  # silence
        pass

    def _send(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # /models
        self._send(200, {"data": [{"id": m} for m in (SUPER, ULTRA, LIGHTNING)]})

    def do_POST(self):  # /chat/completions
        self.auth_seen.append(self.headers.get("Authorization", ""))
        length = int(self.headers.get("Content-Length", 0))
        model = json.loads(self.rfile.read(length))["model"]
        if model in self.served:
            self._send(200, {"model": self.served[model], "choices": []})
        else:
            self._send(404, {"status": 404, "detail": "Function not found for account"})


@pytest.fixture
def provider(monkeypatch):
    _Provider.served = {}
    _Provider.auth_seen = []
    server = HTTPServer(("127.0.0.1", 0), _Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    for key in list(__import__("os").environ):
        if key.startswith("NEMOTRON_"):
            monkeypatch.delenv(key)
    monkeypatch.delenv("MAIW_NIM_API_KEY", raising=False)
    monkeypatch.setenv("MAIW_NIM_BASE_URL", f"http://127.0.0.1:{server.server_port}/v1")
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key-not-real")
    yield _Provider
    server.shutdown()


def _run(mod, monkeypatch, capsys, *args):
    monkeypatch.setattr("sys.argv", ["check_model_config.py", *args])
    try:
        rc = mod.main()
    finally:
        # main() calls logging.disable(CRITICAL) for its CLI output; undo it so
        # later tests that capture logs are unaffected.
        logging.disable(logging.NOTSET)
    return rc, capsys.readouterr().out


def test_listed_but_not_served_fails(provider, monkeypatch, capsys):
    """Retired-but-listed: Super enabled and listed, completion 404 → FAIL."""
    provider.served = {LIGHTNING: LIGHTNING, ULTRA: ULTRA}
    monkeypatch.setenv("NEMOTRON_SUPER_ENABLED", "true")
    rc, out = _run(_load(), monkeypatch, capsys, "--provider-probe")
    assert rc == 1
    assert "PASS  provider lists super model" in out
    assert "FAIL  provider does not serve super model (HTTP 404" in out
    assert "PASS  provider serves lightning model" in out
    assert "test-key-not-real" not in out


def test_defaults_served_pass(provider, monkeypatch, capsys):
    provider.served = {LIGHTNING: LIGHTNING, ULTRA: ULTRA}
    rc, out = _run(_load(), monkeypatch, capsys, "--provider-probe")
    assert rc == 0, out
    assert "PASS  provider serves lightning model" in out
    assert "PASS  provider serves ultra model" in out
    assert "serve super" not in out  # Super is disabled by default: not probed
    assert provider.auth_seen == ["Bearer test-key-not-real"] * 2


def test_wrong_reported_model_fails(provider, monkeypatch, capsys):
    provider.served = {LIGHTNING: LIGHTNING, ULTRA: "example-org/substituted"}
    rc, out = _run(_load(), monkeypatch, capsys, "--provider-probe")
    assert rc == 1
    assert (
        "FAIL  provider does not serve ultra model (HTTP 200, reported example-org/substituted)"
        in out
    )


def test_no_key_skips_dispatch(provider, monkeypatch, capsys):
    monkeypatch.delenv("NVIDIA_API_KEY")
    rc, out = _run(_load(), monkeypatch, capsys, "--provider-probe")
    assert rc == 0
    assert "WARN  provider dispatch not probed" in out
    assert provider.auth_seen == []


def test_without_flag_no_provider_calls(provider, monkeypatch, capsys):
    rc, _ = _run(_load(), monkeypatch, capsys)
    assert rc == 0
    assert provider.auth_seen == []
