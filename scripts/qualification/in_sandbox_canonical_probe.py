# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.0.1 in-sandbox probe — runs INSIDE an OpenShell sandbox. stdlib only.

    cat <token-file> | openshell sandbox exec -n <sandbox> -- \
        python3 - <base-url> < this-file      (see live_canonical_qualification.py)

The internal inference token is read from the first line of stdin (or the
MAIW_PROBE_TOKEN_STDIN protocol used by the driver) and is NEVER printed.
Prints one JSON object describing what the sandbox can and cannot reach on
the canonical shipped app (maiw_api.app:app).
"""

import json
import os
import sys
import urllib.error
import urllib.request


def _http(method, url, body=None, headers=None, timeout=150):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        raw = r.read().decode("utf-8", "replace")
        try:
            return r.status, json.loads(raw)
        except ValueError:
            return r.status, {"raw": raw[:200]}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, {"raw": raw[:200]}
    except Exception as e:  # noqa: BLE001
        return "BLOCKED", {"error": f"{type(e).__name__}: {str(e)[:120]}"}


def main() -> None:
    base = sys.argv[1].rstrip("/")
    token = sys.stdin.readline().strip()
    auth = {"X-Maiw-Internal-Token": token}
    out = {"base": base, "token_received": bool(token)}
    inf = base + "/api/v1/inference"
    req = {
        "task": "v201_in_sandbox_probe",
        "messages": [{"role": "user", "content": "Reply with the single word OK."}],
        "reasoning": "high",
        "deadline_ms": 120000,
        "trace_id": "v201-in-sandbox-trace",
        "agent_task_id": "v201-sandbox-task",
    }

    code, body = _http("POST", inf, req, auth)
    route = body.get("route", {}) if isinstance(body, dict) else {}
    out["inference_with_token"] = {
        "http": code,
        "model_id": body.get("model_id") if isinstance(body, dict) else None,
        "generation": route.get("generation"),
        "approved_family": route.get("approved_family"),
        "selected_role": route.get("selected_role"),
        "trace_id": body.get("trace_id") if isinstance(body, dict) else None,
        "content_nonempty": bool(isinstance(body, dict) and body.get("content")),
    }
    out["inference_no_token"] = _http("POST", inf, req)[0]
    out["inference_wrong_token"] = _http(
        "POST", inf, req, {"X-Maiw-Internal-Token": "wrong-" + "0" * 30}
    )[0]
    out["inference_model_id_injection"] = _http(
        "POST", inf, {**req, "model_id": "meta/llama-3.1-70b-instruct"}, auth
    )[0]
    out["inference_unknown_field_injection"] = _http(
        "POST", inf, {**req, "model": "meta/llama-3.1-70b-instruct"}, auth
    )[0]
    out["readiness"] = _http("GET", base + "/api/v1/ready")[0]
    # The sandbox's one allowed host:port is the canonical app — the legacy
    # ungoverned write paths must not exist behind it.
    out["legacy_chat_post"] = _http(
        "POST",
        base + "/api/v1/chat",
        {"message": "Assign forklift FL-01 to operator J-17", "session_id": "sbx"},
    )[0]
    out["legacy_inventory_write"] = _http(
        "PUT", base + "/api/v1/inventory/items/X", {"quantity": 1}
    )[0]
    out["legacy_migrate"] = _http("POST", base + "/api/v1/migrations/migrate")[0]
    out["direct_provider"] = _http(
        "GET", "https://integrate.api.nvidia.com/v1/models", timeout=10
    )[0]
    out["internet"] = _http("GET", "https://github.com", timeout=10)[0]
    out["metadata_service"] = _http(
        "GET", "http://169.254.169.254/latest/meta-data/", timeout=5
    )[0]
    out["env_secret_names"] = sorted(
        n
        for n in os.environ
        if any(s in n.upper() for s in ("KEY", "TOKEN", "SECRET", "PASS", "NVAPI"))
    )
    try:
        import importlib.util

        out["maiw_execution_importable"] = (
            importlib.util.find_spec("maiw_execution") is not None
        )
    except Exception:  # noqa: BLE001
        out["maiw_execution_importable"] = False
    print(json.dumps(out))


if __name__ == "__main__":
    main()
