#!/usr/bin/env python3
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
MAIW Model Routing Diagnostic Report

Prints the current model registry state and representative routing decisions
without connecting to any NIM endpoint.  Safe to run in any environment.

Usage:
    python scripts/model_routing_report.py
    NEMOTRON_ULTRA_ENABLED=true python scripts/model_routing_report.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.api.services.model_gateway.models import (
    DeploymentStatus,
    Modality,
    ModelRequest,
    ReasoningLevel,
    RiskLevel,
)
from src.api.services.model_gateway.registry import ModelRegistry
from src.api.services.model_gateway.router import ModelRouter
from src.api.services.model_gateway.errors import ModelUnavailable

_ROLE_ORDER = ["lightning", "nano", "super", "ultra", "nano-omni"]

_REPRESENTATIVE_ROUTES = [
    # (display_label, task, reasoning, risk, modality)
    ("forecast.summarize",         "warehouse.forecasting.summarize_demand",        ReasoningLevel.LOW,    RiskLevel.LOW,      Modality.TEXT),
    ("forecast.analyze_anomaly",   "warehouse.forecasting.analyze_anomaly",         ReasoningLevel.MEDIUM, RiskLevel.LOW,      Modality.TEXT),
    ("operations.summarize_state", "warehouse.operations.summarize_state",          ReasoningLevel.LOW,    RiskLevel.LOW,      Modality.TEXT),
    ("operations.recover_wave",    "warehouse.operations.recover_wave",             ReasoningLevel.HIGH,   RiskLevel.HIGH,     Modality.TEXT),
    ("equipment.health",           "warehouse.equipment.summarize_health",          ReasoningLevel.LOW,    RiskLevel.LOW,      Modality.TEXT),
    ("equipment.diagnose",         "warehouse.equipment.diagnose_failure",          ReasoningLevel.HIGH,   RiskLevel.HIGH,     Modality.TEXT),
    ("safety.event_summary",       "warehouse.safety.summarize_event",              ReasoningLevel.MEDIUM, RiskLevel.MEDIUM,   Modality.TEXT),
    ("safety.broadcast_alert",     "warehouse.safety.broadcast_alert",              ReasoningLevel.HIGH,   RiskLevel.CRITICAL, Modality.TEXT),
    ("documents.summarize_text",   "warehouse.documents.summarize_text",            ReasoningLevel.LOW,    RiskLevel.LOW,      Modality.TEXT),
    ("documents.inspect_image",    "warehouse.documents.inspect_image",             ReasoningLevel.MEDIUM, RiskLevel.LOW,      Modality.IMAGE),
    ("eval.judge_trajectory",      "warehouse.eval.judge_trajectory",               ReasoningLevel.HIGH,   RiskLevel.LOW,      Modality.TEXT),
]

_DEPLOY_SYMBOLS = {
    DeploymentStatus.DEPLOYED:              "✓ deployed",
    DeploymentStatus.SUPPORTED_BY_ARCH:     "~ arch-supported",
    DeploymentStatus.NOT_CURRENTLY_DEPLOYED:"✗ not-deployed",
    DeploymentStatus.LEGACY:               "⚠ legacy",
}


def _yn(b: bool) -> str:
    return "yes" if b else "no"


def main() -> None:
    registry = ModelRegistry()
    router = ModelRouter(registry)

    print()
    print("╔══════════════════════════════════════════════════════════════════════════════════╗")
    print("║                         MAIW MODEL ROUTING REPORT                              ║")
    print("╚══════════════════════════════════════════════════════════════════════════════════╝")
    print()

    # ── Registry table ────────────────────────────────────────────────────────
    print(f"{'ROLE':<12}{'EN':<5}{'GENERATION':<16}{'PHYSICAL MODEL':<46}{'PROVIDER':<12}{'DEPLOYMENT STATUS'}")
    print("─" * 108)
    for role in _ROLE_ORDER:
        cap = registry.get_by_role(role)
        if cap is None:
            print(f"{role:<12}{'—':<5}{'—':<16}{'(not registered)':<46}{'—':<12}{'—'}")
            continue
        mid = cap.model_id
        if "OPERATOR_MUST_CONFIGURE" in mid:
            mid = "(operator must configure)"
        elif len(mid) > 44:
            mid = mid[:41] + "..."
        deploy = _DEPLOY_SYMBOLS.get(cap.deployment_status, cap.deployment_status.value)
        print(f"{cap.role:<12}{_yn(cap.enabled):<5}{cap.generation:<16}{mid:<46}{cap.provider:<12}{deploy}")

    print()

    # ── Capability detail ─────────────────────────────────────────────────────
    print(f"{'ROLE':<12}{'TOOL_USE':<11}{'STRUCT_OUT':<12}{'CTX_WIN':<10}{'MODALITIES'}")
    print("─" * 65)
    for role in _ROLE_ORDER:
        cap = registry.get_by_role(role)
        if cap is None:
            continue
        ctx = str(cap.context_window) if cap.context_window else "unknown"
        mods = ",".join(sorted(cap.modalities))
        print(f"{cap.role:<12}{_yn(cap.tool_use):<11}{_yn(cap.structured_output):<12}{ctx:<10}{mods}")

    print()

    # ── Representative routes ─────────────────────────────────────────────────
    print(f"{'WORKLOAD':<30}{'REASON':<12}{'RISK':<12}{'→ ROLE':<14}{'MODEL / NOTE'}")
    print("─" * 100)
    for label, task, reasoning, risk, modality in _REPRESENTATIVE_ROUTES:
        req = ModelRequest(task=task, messages=[], reasoning=reasoning, risk_level=risk, modality=modality)
        try:
            decision = router.route(req)
            role_str = decision.selected_role
            cap = registry.get_by_role(role_str)
            mid = cap.model_id if cap else decision.selected_model_id
            short = mid.split("/")[-1] if "/" in mid else mid
            if decision.fallback_from:
                note = f"{short}  ← fallback from {decision.fallback_from}"
            else:
                note = short
        except ModelUnavailable as exc:
            role_str = "UNAVAILABLE"
            note = str(exc)[:50]
        print(f"{label:<30}{reasoning.value:<12}{risk.value:<12}{role_str:<14}{note}")

    print()

    # ── Summary ───────────────────────────────────────────────────────────────
    enabled = registry.all_enabled()
    total = len(registry.all_roles())
    print(f"Enabled roles: {len(enabled)}/{total}")
    print()
    deployed_count = sum(
        1 for c in registry.all_enabled()
        if c.deployment_status == DeploymentStatus.DEPLOYED
    )
    print(f"Endpoint-validated models: {deployed_count}/{len(enabled)} enabled roles")
    print()
    if any(c.deployment_status == DeploymentStatus.LEGACY for c in enabled):
        print("WARNING: One or more enabled roles are mapped to legacy (pre-Nemotron-3) models.")
    print("To enable a role: NEMOTRON_<ROLE>_ENABLED=true")
    print("To override model: NEMOTRON_<ROLE>_MODEL=<verified-nim-model-id>")
    print()


if __name__ == "__main__":
    main()
