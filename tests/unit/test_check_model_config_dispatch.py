# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.1.0 — scripts/lib/check_model_config.py --provider-probe dispatches.

The hosted catalogue kept listing Nemotron 3 Super after its 2026-10-19
retirement while every completion returned HTTP 404, so the probe sends each
enabled model one minimal completion and fails unless it answers as that
model.  A local fake provider stands in for the hosted endpoint.

#269: a rate limit (429) or provider error (5xx) is retried and, if it
persists, reported WARN "could not verify" without failing the check -- it
used to print "FAIL provider does not serve ... disable the role" and fail
preflight.  A key refusal (401/403) and no answer at all get their own FAIL
wording.
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
    """Lists every model; serves completions only for ``served``.

    ``script[model]`` is a queue of (status, headers) answers sent before the
    normal behaviour, e.g. ``[(429, {"Retry-After": "1"})]``.
    """

    served: dict[str, str] = {}
    auth_seen: list[str] = []
    script: dict[str, list] = {}
    calls: dict[str, int] = {}

    def log_message(self, *args):  # silence
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

    def do_GET(self):  # /models
        self._send(200, {"data": [{"id": m} for m in (SUPER, ULTRA, LIGHTNING)]})

    def do_POST(self):  # /chat/completions
        self.auth_seen.append(self.headers.get("Authorization", ""))
        length = int(self.headers.get("Content-Length", 0))
        model = json.loads(self.rfile.read(length))["model"]
        self.calls[model] = self.calls.get(model, 0) + 1
        queue = self.script.get(model)
        if queue:
            code, headers = queue.pop(0)
            self._send(code, {"status": code}, headers)
        elif model in self.served:
            self._send(200, {"model": self.served[model], "choices": []})
        else:
            self._send(404, {"status": 404, "detail": "Function not found for account"})


@pytest.fixture
def provider(monkeypatch):
    _Provider.served = {}
    _Provider.auth_seen = []
    _Provider.script = {}
    _Provider.calls = {}
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


# ── #269: transient answers are not "does not serve" ──────────────────────────


@pytest.fixture
def no_sleep(monkeypatch):
    """Record retry delays instead of sleeping."""
    mod = _load()
    delays: list[float] = []
    monkeypatch.setattr(mod.time, "sleep", delays.append)
    return mod, delays


def test_rate_limit_then_success_passes_after_retry(
    provider, no_sleep, monkeypatch, capsys
):
    mod, delays = no_sleep
    provider.served = {LIGHTNING: LIGHTNING, ULTRA: ULTRA}
    provider.script = {LIGHTNING: [(429, {"Retry-After": "3"})]}
    rc, out = _run(mod, monkeypatch, capsys, "--provider-probe")
    assert rc == 0, out
    assert "PASS  provider serves lightning model" in out
    assert provider.calls[LIGHTNING] == 2
    assert delays == [3.0]  # Retry-After honoured


@pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
def test_persistent_transient_answer_warns_without_failing(
    code, provider, no_sleep, monkeypatch, capsys
):
    mod, delays = no_sleep
    provider.served = {LIGHTNING: LIGHTNING, ULTRA: ULTRA}
    provider.script = {LIGHTNING: [(code, {})] * 3}
    rc, out = _run(mod, monkeypatch, capsys, "--provider-probe")
    assert rc == 0, out
    assert "FAIL" not in out
    reason = "rate limited" if code == 429 else "provider error"
    assert (
        f"WARN  provider could not verify lightning model (HTTP {code}, {reason}, "
        "3 attempts) — retry later; this is not a configuration error"
    ) in out
    assert "disable the role" not in out
    assert "PASS  provider serves ultra model" in out
    assert provider.calls[LIGHTNING] == 3
    assert delays == [2.0, 5.0]  # backoff without Retry-After


def test_retry_after_is_capped_and_http_dates_fall_back(
    provider, no_sleep, monkeypatch, capsys
):
    mod, delays = no_sleep
    provider.served = {LIGHTNING: LIGHTNING, ULTRA: ULTRA}
    provider.script = {
        LIGHTNING: [
            (429, {"Retry-After": "3600"}),
            (429, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}),
        ]
    }
    rc, _ = _run(mod, monkeypatch, capsys, "--provider-probe")
    assert rc == 0
    assert delays == [10.0, 5.0]


def test_json_report_carries_the_verdict(provider, no_sleep, monkeypatch, capsys):
    mod, _ = no_sleep
    provider.served = {LIGHTNING: LIGHTNING}
    provider.script = {ULTRA: [(429, {})] * 3}
    rc, out = _run(mod, monkeypatch, capsys, "--provider-probe", "--json")
    assert rc == 0
    dispatch = json.loads(out)["provider"]["dispatch"]
    assert dispatch["lightning"]["verdict"] == "served"
    assert dispatch["ultra"] == {
        "ok": False,
        "verdict": "unverified",
        "http": 429,
        "reported": None,
        "attempts": 3,
    }


@pytest.mark.parametrize("code", [401, 403])
def test_key_refusal_fails_with_key_advice(
    code, provider, no_sleep, monkeypatch, capsys
):
    mod, delays = no_sleep
    provider.served = {LIGHTNING: LIGHTNING, ULTRA: ULTRA}
    provider.script = {ULTRA: [(code, {})]}
    rc, out = _run(mod, monkeypatch, capsys, "--provider-probe")
    assert rc == 1
    assert f"FAIL  provider refused the API key for ultra model (HTTP {code})" in out
    assert "MAIW_NIM_API_KEY / NVIDIA_API_KEY" in out
    assert "test-key-not-real" not in out
    assert provider.calls[ULTRA] == 1  # not retried
    assert delays == []


def test_no_answer_fails_with_endpoint_advice(provider, no_sleep, monkeypatch, capsys):
    mod, _ = no_sleep
    # Nothing listens on port 9 (discard) on the loopback interface.
    monkeypatch.setenv("MAIW_NIM_BASE_URL", "http://127.0.0.1:9/v1")
    rc, out = _run(mod, monkeypatch, capsys, "--provider-probe")
    assert rc == 1
    assert "WARN  provider not reachable (URLError)" in out
    assert "FAIL  provider did not answer for lightning model (URLError)" in out
    assert "check MAIW_NIM_BASE_URL" in out


def test_model_list_rate_limit_is_not_called_unreachable(
    provider, no_sleep, monkeypatch, capsys
):
    mod, _ = no_sleep
    provider.served = {LIGHTNING: LIGHTNING, ULTRA: ULTRA}
    original = _Provider.do_GET
    monkeypatch.setattr(
        _Provider, "do_GET", lambda self: self._send(429, {"status": 429})
    )
    rc, out = _run(mod, monkeypatch, capsys, "--provider-probe")
    monkeypatch.setattr(_Provider, "do_GET", original)
    assert rc == 0, out
    assert "WARN  provider model list unavailable (HTTP 429)" in out
    assert "not reachable" not in out


def test_not_found_is_still_a_failure_and_not_retried(
    provider, no_sleep, monkeypatch, capsys
):
    mod, delays = no_sleep
    provider.served = {LIGHTNING: LIGHTNING}  # ultra answers 404
    rc, out = _run(mod, monkeypatch, capsys, "--provider-probe")
    assert rc == 1
    assert "FAIL  provider does not serve ultra model (HTTP 404" in out
    assert provider.calls[ULTRA] == 1
    assert delays == []
