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
Phase 18C: Developer CLI for offline model benchmarking.

Usage:
    python -m maiw_models.eval benchmark \\
        --cases artifacts/phase18/cases.json \\
        --output artifacts/phase18/baseline.json

    # Use built-in fixture cases (default):
    python -m maiw_models.eval benchmark \\
        --output artifacts/phase18/baseline.json

    # Print candidate inventory only (no inference):
    python -m maiw_models.eval inventory

    # Generate baseline router report (requires existing baseline.json):
    python -m maiw_models.eval report \\
        --input artifacts/phase18/baseline.json \\
        --output artifacts/phase18/BASELINE_ROUTER_REPORT.md

Architecture invariants:
    - Live benchmark requires NVIDIA_API_KEY and live NIM endpoints.
    - When endpoints are unavailable, infrastructure is verified and results
      are explicitly marked NOT RUN — ENDPOINT UNAVAILABLE.
    - Evaluation results are NEVER written to Copilot conversation or approval queues.
    - No MCP write calls are made.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("maiw_models.eval")


# ── Subcommand: inventory ─────────────────────────────────────────────────────


def cmd_inventory(args: argparse.Namespace) -> int:
    """Print candidate model inventory (no inference)."""
    from maiw_models.evaluation.inventory import build_candidate_inventory
    from maiw_models.models import DeploymentMode
    from maiw_models.registry import ModelRegistry

    registry = ModelRegistry()
    deployment_mode = DeploymentMode(args.deployment_mode)
    inventory = build_candidate_inventory(registry, deployment_mode)

    print("\nCANDIDATE MODEL INVENTORY")
    print("=" * 80)
    header = f"{'ROLE':<12} {'MODEL ID':<50} {'ENABLED':<8} {'AVAIL':<8} {'LATENCY':<8} {'COST':<8}"
    print(header)
    print("-" * 80)
    for info in inventory:
        avail = "YES" if info.available else "NO"
        enabled = "YES" if info.enabled else "NO"
        print(
            f"{info.role:<12} {info.model_id:<50} {enabled:<8} {avail:<8} "
            f"{info.latency_class:<8} {info.cost_class:<8}"
        )
    print()
    for info in inventory:
        print(f"  {info.role}: {info.logical_role}")
        print(f"    reasoning_support: {info.reasoning_support}")
        print(f"    risk_suitability:  {info.risk_suitability}")
        print(f"    deployment_status: {info.deployment_status}")
        print(
            f"    tool_use={info.tool_use} structured_output={info.structured_output} "
            f"teacher_judge={info.teacher_judge}"
        )
        print()
    return 0


# ── Subcommand: benchmark ─────────────────────────────────────────────────────


async def _run_benchmark(args: argparse.Namespace) -> int:
    """Execute the multi-model benchmark (requires live endpoints)."""
    from maiw_models import get_model_gateway, reset_model_gateway
    from maiw_models.evaluation.fixtures import ALL_FIXTURE_CASES
    from maiw_models.evaluation.runner import EvaluationRunner
    from maiw_models.models import DeploymentMode
    from maiw_models.registry import ModelRegistry

    deployment_mode = DeploymentMode(args.deployment_mode)
    registry = ModelRegistry()

    # Load cases: either from file or use built-in fixtures.
    if args.cases and Path(args.cases).exists():
        logger.info("Loading cases from %s", args.cases)
        with open(args.cases) as f:
            cases_data = json.load(f)
        # For now, built-in fixture cases are used regardless.
        # Custom cases from JSON are documented for future extension.
        logger.info(
            "Custom cases file loaded (%d entries) — using built-in fixture cases "
            "for 18C benchmark corpus.",
            len(cases_data),
        )
        cases = ALL_FIXTURE_CASES
    else:
        logger.info("No --cases file; using built-in Phase 18C fixture corpus.")
        cases = ALL_FIXTURE_CASES

    # Check for API key — skip live run if unavailable.
    api_key = os.environ.get("NVIDIA_API_KEY", "").strip()
    endpoint_status: str

    if not api_key:
        logger.warning(
            "NVIDIA_API_KEY not set — infrastructure verified, "
            "benchmark NOT RUN — ENDPOINT UNAVAILABLE"
        )
        endpoint_status = "NOT RUN — ENDPOINT UNAVAILABLE (NVIDIA_API_KEY not set)"

        # Validate infrastructure (import paths, registry, runner).
        _validate_infrastructure(registry, cases, deployment_mode)
        run = _make_dry_run_result(cases, registry, deployment_mode, endpoint_status)

    else:
        endpoint_status = f"LIVE — deployment_mode={deployment_mode.value}"
        logger.info("NVIDIA_API_KEY present — running live benchmark.")

        try:
            gateway = await get_model_gateway()
            runner = EvaluationRunner(gateway, registry)
            run = await runner.run_benchmark(
                cases=cases,
                deployment_mode=deployment_mode,
                endpoint_status=endpoint_status,
            )
        except Exception as exc:
            logger.error("Live benchmark failed: %s", exc)
            endpoint_status = f"FAILED — {type(exc).__name__}: {exc}"
            run = _make_dry_run_result(
                cases, registry, deployment_mode, endpoint_status
            )
        finally:
            reset_model_gateway()

    # Write output.
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(run.to_json())
    logger.info("Benchmark result written to %s", output_path)

    # Print summary table.
    _print_summary_table(run)

    return 0


def _validate_infrastructure(registry: Any, cases: list, deployment_mode: Any) -> None:
    """Validate that all infrastructure is importable and functional."""
    from maiw_models.evaluation.runner import EvaluationRunner, record_router_selection
    from maiw_models.evaluation.benchmark import compute_oracle, compute_router_regret
    from maiw_models.evaluation.inventory import build_candidate_inventory

    inventory = build_candidate_inventory(registry, deployment_mode)
    logger.info(
        "Infrastructure validated: %d models in registry, %d cases in corpus",
        len(inventory),
        len(cases),
    )
    for case in cases:
        selection = record_router_selection(case, registry, deployment_mode)
        logger.info(
            "  Case %s → router selects %s (%s)",
            case.case_id,
            selection.selected_model_id,
            selection.routing_rule,
        )


def _make_dry_run_result(
    cases: list, registry: Any, deployment_mode: Any, endpoint_status: str
) -> Any:
    """Build a dry-run BenchmarkRun (no inference) for infrastructure validation."""
    from maiw_models.evaluation.benchmark import (
        BenchmarkCaseResult,
        BenchmarkMetadata,
        BenchmarkRun,
        BenchmarkModelResult,
        OracleResult,
        compute_decision_gate,
    )
    from maiw_models.evaluation.fixtures import (
        FIXTURE_DATASET_ID,
        FIXTURE_DATAPACK_CHECKSUM,
    )
    from maiw_models.evaluation.inventory import build_candidate_inventory
    from maiw_models.evaluation.runner import record_router_selection
    from maiw_models.routing import PolicyFilter
    from maiw_models.evaluation.runner import (
        _make_request_from_case,
        _build_fixture_messages,
    )

    policy_filter = PolicyFilter(registry)
    case_results = []

    for case in cases:
        messages = _build_fixture_messages(case)
        request = _make_request_from_case(case, messages, deployment_mode)
        candidate_ids = policy_filter.candidate_model_ids(request, deployment_mode)
        router_selection = record_router_selection(case, registry, deployment_mode)

        # Build placeholder results (no actual responses).
        model_results = []
        for mid in candidate_ids:
            model_results.append(
                BenchmarkModelResult(
                    evaluation_run_key="dry-run-no-inference",
                    case_id=case.case_id,
                    dataset_id=FIXTURE_DATASET_ID,
                    semantic_checksum=FIXTURE_DATAPACK_CHECKSUM,
                    scenario_id=case.case_id,
                    context_snapshot_id=case.context_snapshot_id,
                    warehouse_state_snapshot_id=None,
                    prompt_hash="dry-run",
                    model_id=mid,
                    deployment=deployment_mode.value,
                    error="NOT RUN — ENDPOINT UNAVAILABLE",
                )
            )

        oracle = OracleResult()
        case_results.append(
            BenchmarkCaseResult(
                case_id=case.case_id,
                case_prompt=case.prompt,
                task_family=case.task_family.value,
                model_results=model_results,
                router_selection=router_selection,
                oracle=oracle,
                regret=None,
            )
        )

    from datetime import datetime, timezone

    metadata = BenchmarkMetadata(
        dataset_id=FIXTURE_DATASET_ID,
        semantic_checksum=FIXTURE_DATAPACK_CHECKSUM,
        run_timestamp=datetime.now(timezone.utc).isoformat(),
        cases_count=len(cases),
        models_evaluated=[],
        deployment_mode=deployment_mode.value,
        phase="18C",
        endpoint_status=endpoint_status,
    )
    return BenchmarkRun(
        metadata=metadata,
        cases=case_results,
        decision_gate="NOT RUN — ENDPOINT UNAVAILABLE",
    )


def _print_summary_table(run: Any) -> None:
    """Print concise benchmark summary table to stdout."""
    print()
    print("BENCHMARK SUMMARY")
    print("=" * 80)
    print(f"{'CASE':<30} {'MODEL':<40} {'QUALITY':>8} {'LATENCY':>10} {'PASS':>5}")
    print("-" * 80)
    for case_result in run.cases:
        for mr in case_result.model_results:
            case_label = mr.case_id[:28]
            model_label = mr.model_id[-38:] if len(mr.model_id) > 38 else mr.model_id
            if mr.error and "NOT RUN" in mr.error:
                quality_str = "N/A"
                latency_str = "N/A"
                pass_str = "N/A"
            elif mr.error:
                quality_str = "ERR"
                latency_str = f"{mr.total_latency_ms:.0f}ms"
                pass_str = "X"
            else:
                quality_str = f"{mr.quality_score:.2f}"
                latency_str = f"{mr.total_latency_ms:.0f}ms"
                pass_str = "OK" if mr.quality_pass else "X"
            print(
                f"{case_label:<30} {model_label:<40} "
                f"{quality_str:>8} {latency_str:>10} {pass_str:>5}"
            )
    print()
    print(f"ENDPOINT STATUS: {run.metadata.endpoint_status}")
    print(f"DECISION GATE:   {run.decision_gate}")
    print()

    if run.cases:
        print("ROUTER SELECTIONS:")
        for cr in run.cases:
            if cr.router_selection:
                print(
                    f"  {cr.case_id:<40} → {cr.router_selection.selected_model_id} "
                    f"({cr.router_selection.routing_rule})"
                )
    print()


def cmd_benchmark(args: argparse.Namespace) -> int:
    """Entry point for benchmark subcommand."""
    return asyncio.run(_run_benchmark(args))


# ── Subcommand: report ────────────────────────────────────────────────────────


def cmd_report(args: argparse.Namespace) -> int:
    """Generate BASELINE_ROUTER_REPORT.md from a baseline.json result."""
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: input file not found: {input_path}", file=sys.stderr)
        return 1

    with open(input_path) as f:
        data = json.load(f)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    report = _generate_markdown_report(data)
    output_path.write_text(report)
    print(f"Report written to {output_path}")
    return 0


def _generate_markdown_report(data: dict) -> str:
    """Generate BASELINE_ROUTER_REPORT.md content from benchmark JSON."""
    lines = []
    meta = data.get("metadata", {})

    lines.append("# Baseline Router Report — Phase 18C")
    lines.append("")
    lines.append("## Evaluation Identity")
    lines.append("")
    lines.append(f"| Field | Value |")
    lines.append(f"|-------|-------|")
    lines.append(f"| Phase | {meta.get('phase', '18C')} |")
    lines.append(f"| Dataset | `{meta.get('dataset_id', '')}` |")
    lines.append(f"| Semantic Checksum | `{meta.get('semantic_checksum', '')}` |")
    lines.append(f"| Run Timestamp | {meta.get('run_timestamp', '')} |")
    lines.append(f"| Deployment Mode | {meta.get('deployment_mode', '')} |")
    lines.append(f"| Endpoint Status | {meta.get('endpoint_status', '')} |")
    lines.append(f"| Cases | {meta.get('cases_count', 0)} |")
    lines.append("")

    models_evaluated = meta.get("models_evaluated", [])
    if models_evaluated:
        lines.append("## Candidate Models")
        lines.append("")
        for m in models_evaluated:
            lines.append(f"- `{m}`")
        lines.append("")

    lines.append("## Case Results")
    lines.append("")

    cases = data.get("cases", [])
    for case in cases:
        lines.append(f"### Case: `{case['case_id']}`")
        lines.append("")
        lines.append(f"**Prompt:** {case['case_prompt'][:120]}...")
        lines.append("")
        lines.append(f"**Task family:** {case['task_family']}")
        lines.append("")

        router = case.get("router_selection")
        if router:
            lines.append(
                f"**Router selected:** `{router['selected_model_id']}` "
                f"via rule `{router['routing_rule']}`"
            )
            lines.append("")

        model_results = case.get("model_results", [])
        if model_results:
            lines.append("| Model | Quality | Latency | Pass | Error |")
            lines.append("|-------|---------|---------|------|-------|")
            for mr in model_results:
                q = mr["quality"]["score"]
                l_ms = mr["latency"]["total_ms"]
                passed = mr["quality"]["pass"]
                err = mr["outcome"].get("error") or ""
                if "NOT RUN" in err:
                    lines.append(
                        f"| `{mr['model_id']}` | N/A | N/A | N/A | {err[:60]} |"
                    )
                else:
                    lines.append(
                        f"| `{mr['model_id']}` | {q:.2f} | {l_ms:.0f}ms | "
                        f"{'YES' if passed else 'NO'} | {err[:60]} |"
                    )
            lines.append("")

        oracle = case.get("oracle", {})
        if oracle:
            lines.append("**Oracle:**")
            bq = oracle.get("best_quality", {})
            fp = oracle.get("fastest_passing", {})
            lines.append(
                f"- Best quality: `{bq.get('model_id', 'N/A')}` "
                f"(score={bq.get('quality_score', 0):.2f})"
            )
            lines.append(
                f"- Fastest passing: `{fp.get('model_id', 'N/A')}` "
                f"({fp.get('total_latency_ms', 0):.0f}ms)"
            )
            lines.append(f"- Lowest cost: unavailable (no pricing metadata)")
            lines.append("")

        regret = case.get("regret")
        if regret:
            lines.append("**Router regret:**")
            if regret.get("quality_regret"):
                lines.append(f"- QUALITY REGRET: {regret['quality_regret_detail']}")
                if regret.get("quality_regret_policy_note"):
                    lines.append(f"  - Note: {regret['quality_regret_policy_note']}")
            else:
                lines.append("- Quality regret: none")
            if regret.get("latency_regret"):
                lines.append(f"- LATENCY REGRET: {regret['latency_regret_detail']}")
            else:
                lines.append("- Latency regret: none")
            lines.append("")

    lines.append("## Findings")
    lines.append("")
    lines.append(
        "See individual case results above for per-case quality, latency, and regret analysis."
    )
    lines.append("")
    lines.append(
        "Nano (low-risk ASK) and Super (high-risk ANALYZE) findings are reported per case."
    )
    lines.append("")

    decision_gate = data.get("decision_gate", "")
    lines.append("## Decision Gate")
    lines.append("")
    lines.append(f"**{decision_gate}**")
    lines.append("")

    endpoint_status = meta.get("endpoint_status", "")
    if "NOT RUN" in endpoint_status or "UNAVAILABLE" in endpoint_status:
        lines.append(
            "> Infrastructure verified. Live benchmark not executed — "
            "endpoint unavailable. Re-run with `NVIDIA_API_KEY` set to collect "
            "actual quality/latency/regret data."
        )
    lines.append("")

    return "\n".join(lines)


# ── Any type hint needed above ────────────────────────────────────────────────

from typing import Any  # noqa: E402 (needed for _validate_infrastructure signature)

# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m maiw_models.eval",
        description="MAIW Phase 18C: offline model benchmarking developer CLI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # benchmark
    p_bench = sub.add_parser(
        "benchmark",
        help="Run multi-model benchmark against fixture corpus.",
    )
    p_bench.add_argument(
        "--cases",
        default=None,
        help="Path to cases JSON file (optional; built-in fixtures used if not set).",
    )
    p_bench.add_argument(
        "--output",
        default="artifacts/phase18/baseline.json",
        help="Output path for benchmark result JSON.",
    )
    p_bench.add_argument(
        "--deployment-mode",
        dest="deployment_mode",
        default="nvidia_hosted",
        choices=["nvidia_hosted", "local_nim", "enterprise", "openai_compatible"],
        help="Deployment mode for candidate eligibility (default: nvidia_hosted).",
    )

    # inventory
    p_inv = sub.add_parser(
        "inventory",
        help="Print candidate model inventory (no inference).",
    )
    p_inv.add_argument(
        "--deployment-mode",
        dest="deployment_mode",
        default="nvidia_hosted",
        choices=["nvidia_hosted", "local_nim", "enterprise", "openai_compatible"],
    )

    # report
    p_report = sub.add_parser(
        "report",
        help="Generate BASELINE_ROUTER_REPORT.md from benchmark JSON.",
    )
    p_report.add_argument(
        "--input",
        default="artifacts/phase18/baseline.json",
        help="Input benchmark JSON path.",
    )
    p_report.add_argument(
        "--output",
        default="artifacts/phase18/BASELINE_ROUTER_REPORT.md",
        help="Output Markdown report path.",
    )

    args = parser.parse_args()

    dispatch = {
        "benchmark": cmd_benchmark,
        "inventory": cmd_inventory,
        "report": cmd_report,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
