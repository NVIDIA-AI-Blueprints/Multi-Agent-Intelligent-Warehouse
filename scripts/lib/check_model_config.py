#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Physical model configuration check shared by preflight, smoke and status
(v2.0.1 round 2, audit NEW-P1-01 §11/§12).

It builds the SAME ``maiw_models.ModelRegistry`` the shipped app builds — from
the same environment variables (``NEMOTRON_<ROLE>_MODEL`` /
``NEMOTRON_<ROLE>_ENABLED``) — and asks the SAME ``DeploymentResolver`` the
gateway uses before dispatch whether every enabled role is bound to an
approved physical deployment.  There is no duplicate shell logic and no check
of a variable the runtime does not dispatch.

Usage:
    python scripts/lib/check_model_config.py              # human-readable
    python scripts/lib/check_model_config.py --json       # machine-readable
    python scripts/lib/check_model_config.py --expect ROLE MODEL_ID
        exit 0 only if MODEL_ID is the approved physical deployment for ROLE
        (used by the smoke test on the model the running app reports)
    python scripts/lib/check_model_config.py --provider-probe
        additionally GET {provider}/models (credential from the environment,
        never printed) and report whether each enabled model is listed

Exit codes: 0 = every enabled role approved; 1 = violation; 2 = usage/import.
No secret value is ever printed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def _registry():
    from maiw_models import ModelRegistry

    return ModelRegistry()


def _bindings(registry) -> list[dict]:
    rows = []
    for role in registry.all_roles():
        cap = registry.get_by_role(role)
        model_id = registry._role_index.get(role)  # noqa: SLF001 - raw binding
        enabled = bool(cap is not None and cap.enabled)
        problem = registry.resolver.violation(role, model_id)
        rows.append(
            {
                "role": role,
                "model_id": model_id,
                "enabled": enabled,
                "generation": registry.resolver.generation_for(model_id or "")
                or "unapproved",
                "approved": problem is None,
                "reason": problem[0] if problem else None,
            }
        )
    return rows


def _selector_findings(resolver) -> list[dict]:
    """Other model selectors: report whether runtime dispatches them."""
    findings = []
    for var in ("LLM_MODEL", "MAIW_NIM_MODEL"):
        value = os.getenv(var)
        if value is None or value == "":
            continue
        approved = value in resolver.approved_model_ids()
        findings.append(
            {
                "variable": var,
                "value": value,
                "dispatched_by_gateway": False,
                "approved_model_id": approved,
            }
        )
    return findings


def _provider_probe(rows: list[dict]) -> dict:
    import urllib.error
    import urllib.request

    base = (
        os.getenv("MAIW_NIM_BASE_URL")
        or os.getenv("LLM_NIM_URL")
        or "https://integrate.api.nvidia.com/v1"
    ).rstrip("/")
    key = os.getenv("MAIW_NIM_API_KEY") or os.getenv("NVIDIA_API_KEY") or ""
    req = urllib.request.Request(f"{base}/models")
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    out: dict = {"provider_base_url": base}
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read() or b"{}")
        listed = {m.get("id") for m in data.get("data", []) if isinstance(m, dict)}
        out["reachable"] = True
        out["listed"] = {
            r["role"]: (r["model_id"] in listed) for r in rows if r["enabled"]
        }
    except urllib.error.HTTPError as exc:
        out["reachable"] = False
        out["error"] = f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        out["reachable"] = False
        out["error"] = type(exc).__name__
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--expect", nargs=2, metavar=("ROLE", "MODEL_ID"))
    parser.add_argument("--provider-probe", action="store_true")
    args = parser.parse_args()

    import logging

    logging.disable(logging.CRITICAL)  # registry logs; this tool prints its own
    try:
        import maiw_models  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL  cannot import maiw_models: {exc}", file=sys.stderr)
        return 2

    from maiw_models import default_resolver

    if args.expect:
        role, model_id = args.expect
        problem = default_resolver().violation(role, model_id)
        generation = default_resolver().generation_for(model_id) or "unapproved"
        result = {
            "role": role,
            "model_id": model_id,
            "generation": generation,
            "approved": problem is None,
            "reason": problem[0] if problem else None,
        }
        if args.json:
            print(json.dumps(result))
        else:
            verdict = "PASS" if problem is None else "FAIL"
            print(
                f"{verdict}  role={role} model={model_id} generation={generation}"
                + (f" reason={problem[0]}" if problem else " approved")
            )
        return 0 if problem is None else 1

    registry = _registry()
    rows = _bindings(registry)
    selectors = _selector_findings(registry.resolver)
    enabled = [r for r in rows if r["enabled"]]
    violations = [r for r in enabled if not r["approved"]]
    bad_selectors = [s for s in selectors if not s["approved_model_id"]]
    report = {
        "bindings": rows,
        "enabled_roles": [r["role"] for r in enabled],
        "violations": violations,
        "other_selectors": selectors,
        "approved": not violations and not bad_selectors and bool(enabled),
    }
    if args.provider_probe:
        report["provider"] = _provider_probe(rows)

    if args.json:
        print(json.dumps(report, indent=1))
    else:
        for r in rows:
            state = "enabled " if r["enabled"] else "disabled"
            if not r["enabled"]:
                verdict = "INFO"
            else:
                verdict = "PASS" if r["approved"] else "FAIL"
            print(
                f"{verdict}  role={r['role']:<10} {state} model={r['model_id']} "
                f"generation={r['generation']}"
                + (f" reason={r['reason']}" if r["reason"] and r["enabled"] else "")
            )
        for s in selectors:
            verdict = "PASS" if s["approved_model_id"] else "FAIL"
            print(
                f"{verdict}  {s['variable']}={s['value']} (not dispatched by "
                f"ModelGateway; must still name an approved model)"
            )
        if not enabled:
            print("FAIL  no model role is enabled")
        if args.provider_probe:
            p = report["provider"]
            if p.get("reachable"):
                for role, ok in p.get("listed", {}).items():
                    print(
                        f"{'PASS' if ok else 'WARN'}  provider lists {role} model"
                        + ("" if ok else " (not listed — the provider may not serve it)")
                    )
            else:
                print(f"WARN  provider not reachable ({p.get('error')})")
    return 0 if report["approved"] else 1


if __name__ == "__main__":
    sys.exit(main())
