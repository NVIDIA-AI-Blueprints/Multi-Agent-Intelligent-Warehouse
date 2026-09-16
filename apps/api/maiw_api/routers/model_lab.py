# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Model Gateway Lab — Phase 18F.

Read-only artifact loader for evaluation runs from phases 18C, 18D, 18E.

Architecture gate:
    This router MUST NOT import DecisionEngine, ApprovalStore, ActionExecutor,
    or any write MCP capability modules. All responses are derived from
    pre-computed artifact files on disk.

Endpoints:
    GET /api/v1/model-lab/runs
    GET /api/v1/model-lab/runs/{run_id}
    GET /api/v1/model-lab/runs/{run_id}/cases
    GET /api/v1/model-lab/runs/{run_id}/cases/{case_id}
    GET /api/v1/model-lab/model-status
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/model-lab", tags=["Model Lab"])

# ── Artifact paths ─────────────────────────────────────────────────────────────
# From routers/ → maiw_api/ → api/ → apps/ → project root
_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
_ARTIFACT_BASE = _PROJECT_ROOT / "artifacts" / "phase18"

_ARTIFACT_PATHS: dict[str, Path] = {
    "18c": _ARTIFACT_BASE / "baseline.json",
    "18d": _ARTIFACT_BASE / "18d" / "benchmark.json",
    "18e": _ARTIFACT_BASE / "18e" / "benchmark.json",
    "18f": _ARTIFACT_BASE / "18f" / "benchmark.json",
}

_CASES_PATH = _ARTIFACT_BASE / "cases.json"

# ── Run metadata (static) ──────────────────────────────────────────────────────
_RUN_METADATA: dict[str, dict[str, Any]] = {
    "18c": {
        "run_id": "18c",
        "phase": "18C",
        "description": "Phase 18C — Live baseline benchmark. LEGACY METHODOLOGY: prompt metadata leakage identified.",
        "methodology_valid": False,
        "methodology_note": "Prompt metadata leakage identified in 18D/18E review. case_id and metadata dict were injected into model system prompt, biasing responses.",
    },
    "18d": {
        "run_id": "18d",
        "phase": "18D",
        "description": "Phase 18D — Calibrated benchmark. Grader calibration using 18C response snippets. Nano availability audit.",
        "methodology_valid": True,
        "methodology_note": "Grader calibration applied. Response snippets (300 chars) used — some grader results may differ from full-response grading.",
    },
    "18e": {
        "run_id": "18e",
        "phase": "18E",
        "description": "Phase 18E — Final methodology. Prompt isolation fixed, raw_response semantics established, warm-up exclusion added.",
        "methodology_valid": True,
        "methodology_note": "All methodology blockers resolved. 53 offline tests validate corrections.",
    },
    "18f": {
        "run_id": "18f",
        "phase": "18F",
        "description": "Phase 18F — Clean benchmark. Live inference with corrected methodology: no prompt leakage, full raw_response.",
        "methodology_valid": True,
        "methodology_note": "Re-run of 18C cases with 18E methodology fixes applied. First clean live comparison.",
    },
}

# ── Model status (static) ──────────────────────────────────────────────────────
_MODEL_STATUS = [
    {
        "model": "Super",
        "model_id": "nvidia/nemotron-3-super-120b-a12b",
        "status": "AVAILABLE",
        "role": "General warehouse reasoning",
    },
    {
        "model": "Lightning",
        "model_id": "nvidia/nemotron-3.5-lightning-30b-a3b",
        "status": "AVAILABLE",
        "role": "Latency-critical tasks",
    },
    {
        "model": "Nano",
        "model_id": "nvidia/nemotron-3-nano-30b-a3b",
        "status": "UNAVAILABLE",
        "reason": "EOL 2026-09-01 — operator disabled",
        "note": "NOT TESTED — endpoint unavailable during qualification. No inference about Nano quality made.",
    },
]

# ── Secret field blocklist (never returned in responses) ───────────────────────
_SECRET_FIELDS = {"api_key", "endpoint_url", "authorization", "password", "token", "secret"}

_RAW_RESPONSE_LIMIT = 10_000


def _load_artifact(run_id: str) -> dict[str, Any]:
    """Load and parse artifact JSON for a run. Raises HTTPException on failure."""
    if run_id not in _ARTIFACT_PATHS:
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found. Valid run IDs: 18c, 18d, 18e, 18f")
    path = _ARTIFACT_PATHS[run_id]
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Artifact for run '{run_id}' not found on disk at {path}",
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.error("Malformed artifact for run %s: %s", run_id, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Artifact for run '{run_id}' is malformed JSON: {exc}",
        )


def _strip_secrets(obj: Any) -> Any:
    """Recursively strip secret fields from a dict/list structure."""
    if isinstance(obj, dict):
        return {
            k: _strip_secrets(v)
            for k, v in obj.items()
            if k.lower() not in _SECRET_FIELDS
        }
    if isinstance(obj, list):
        return [_strip_secrets(item) for item in obj]
    return obj


def _bound_raw_response(obj: Any) -> Any:
    """Recursively bound raw_response fields to _RAW_RESPONSE_LIMIT chars."""
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            if k == "raw_response" and isinstance(v, str) and len(v) > _RAW_RESPONSE_LIMIT:
                result[k] = v[:_RAW_RESPONSE_LIMIT]
                result["raw_response_truncated"] = True
                result["raw_response_original_length"] = len(v)
            else:
                result[k] = _bound_raw_response(v)
        return result
    if isinstance(obj, list):
        return [_bound_raw_response(item) for item in obj]
    return obj


def _safe_artifact(data: Any) -> Any:
    """Apply all safety transforms: strip secrets, bound raw responses."""
    return _bound_raw_response(_strip_secrets(data))


def _get_cases_for_run(run_id: str, artifact: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract case list from an artifact, normalizing across run formats."""
    if run_id == "18c":
        raw_cases = artifact.get("cases", [])
        result = []
        for case in raw_cases:
            case_id = case.get("case_id", "unknown")
            model_results = case.get("model_results", [])
            summary_models = []
            for mr in model_results:
                quality = mr.get("quality", {})
                summary_models.append({
                    "model_id": mr.get("model_id"),
                    "quality_score": quality.get("score"),
                    "quality_pass": quality.get("pass"),
                    "passed_graders": quality.get("passed_graders"),
                    "applicable_graders": quality.get("applicable_graders"),
                })
            result.append({
                "case_id": case_id,
                "prompt": case.get("case_prompt", ""),
                "task_family": case.get("task_family", ""),
                "risk_level": "high",
                "reasoning_level": "high",
                "model_results_summary": summary_models,
            })
        return result
    elif run_id == "18d":
        raw_corpus = artifact.get("corpus", [])
        return [
            {
                "case_id": c.get("case_id", "unknown"),
                "prompt": c.get("description", ""),
                "task_family": c.get("task_family", ""),
                "risk_level": c.get("risk_level", ""),
                "reasoning_level": c.get("reasoning_level", ""),
                "nano_policy_label": c.get("nano_policy_label", ""),
            }
            for c in raw_corpus
        ]
    elif run_id == "18e":
        qc = artifact.get("qualification_corpus", {})
        raw_cases = qc.get("cases", [])
        return [
            {
                "case_id": c.get("case_id", "unknown"),
                "prompt": c.get("prompt", ""),
                "task_family": c.get("task_family", ""),
                "risk_level": c.get("risk_level", ""),
                "reasoning_level": c.get("reasoning_level", ""),
                "policy_eligibility": c.get("policy_eligibility", ""),
                "label": c.get("label", ""),
            }
            for c in raw_cases
        ]
    elif run_id == "18f":
        raw_cases = artifact.get("cases", [])
        result = []
        for case in raw_cases:
            case_id = case.get("case_id", "unknown")
            model_results = case.get("model_results", [])
            summary_models = []
            for mr in model_results:
                quality = mr.get("quality", {})
                summary_models.append({
                    "model_id": mr.get("model_id"),
                    "quality_score": quality.get("score"),
                    "quality_pass": quality.get("pass"),
                    "passed_graders": quality.get("passed_graders"),
                    "applicable_graders": quality.get("applicable_graders"),
                })
            result.append({
                "case_id": case_id,
                "prompt": case.get("case_prompt", ""),
                "task_family": case.get("task_family", ""),
                "risk_level": case.get("risk_level", "high"),
                "reasoning_level": case.get("reasoning_level", "high"),
                "model_results_summary": summary_models,
            })
        return result
    return []


def _build_run_summary(run_id: str, artifact: dict[str, Any]) -> dict[str, Any]:
    """Build a full run summary from raw artifact data."""
    meta = dict(_RUN_METADATA[run_id])

    if run_id == "18c":
        metadata = artifact.get("metadata", {})
        meta["dataset_id"] = metadata.get("dataset_id")
        meta["checksum"] = metadata.get("semantic_checksum")
        meta["timestamp"] = metadata.get("run_timestamp")
        meta["case_count"] = metadata.get("cases_count", 0)
        meta["models_evaluated"] = metadata.get("models_evaluated", [])
        meta["deployment_mode"] = metadata.get("deployment_mode")
        meta["decision_gate"] = artifact.get("decision_gate")
        meta["model_status"] = artifact.get("model_status")
        meta["policy_filter_pipeline"] = artifact.get("policy_filter_pipeline")
        cases = artifact.get("cases", [])
        meta["case_count"] = len(cases)

    elif run_id == "18d":
        d_meta = artifact.get("metadata", {})
        meta["dataset_id"] = d_meta.get("dataset_id")
        meta["checksum"] = d_meta.get("semantic_checksum")
        meta["timestamp"] = d_meta.get("calibration_run_timestamp")
        meta["models_evaluated"] = ["nvidia/nemotron-3-super-120b-a12b", "nvidia/nemotron-3.5-lightning-30b-a3b"]
        meta["decision_gate"] = artifact.get("decision_gate")
        meta["grader_changes"] = d_meta.get("grader_changes", [])
        meta["nano_availability_audit"] = artifact.get("nano_availability_audit")
        meta["case_count"] = len(artifact.get("corpus", []))

    elif run_id == "18e":
        meta["timestamp"] = artifact.get("run_timestamp")
        meta["dataset_id"] = "eval-fixture-dataset-v1"
        meta["checksum"] = "fixture-checksum-abc123"
        meta["models_evaluated"] = ["nvidia/nemotron-3-super-120b-a12b", "nvidia/nemotron-3.5-lightning-30b-a3b"]
        meta["verdicts"] = artifact.get("verdicts")
        meta["nano_endpoint_status"] = artifact.get("nano_endpoint_status")
        meta["methodology_corrections"] = artifact.get("methodology_corrections")
        meta["live_benchmark_results"] = artifact.get("live_benchmark_results")
        meta["methodology_validation"] = artifact.get("methodology_validation")
        qc = artifact.get("qualification_corpus", {})
        meta["case_count"] = len(qc.get("cases", []))

    elif run_id == "18f":
        metadata = artifact.get("metadata", {})
        meta["dataset_id"] = metadata.get("dataset_id")
        meta["checksum"] = metadata.get("semantic_checksum")
        meta["timestamp"] = metadata.get("run_timestamp")
        meta["models_evaluated"] = metadata.get("models_evaluated", [])
        meta["deployment_mode"] = metadata.get("deployment_mode")
        meta["decision_gate"] = artifact.get("decision_gate")
        cases = artifact.get("cases", [])
        meta["case_count"] = len(cases)

    return _safe_artifact(meta)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/runs")
async def list_runs() -> list[dict[str, Any]]:
    """List all available evaluation runs with metadata."""
    runs = []
    for run_id, meta in _RUN_METADATA.items():
        path = _ARTIFACT_PATHS[run_id]
        available = path.exists()
        entry: dict[str, Any] = {
            "run_id": run_id,
            "phase": meta["phase"],
            "description": meta["description"],
            "methodology_valid": meta["methodology_valid"],
            "methodology_note": meta["methodology_note"],
            "artifact_available": available,
        }
        if available:
            try:
                artifact = _load_artifact(run_id)
                if run_id == "18c":
                    artifact_meta = artifact.get("metadata", {})
                    entry["dataset_id"] = artifact_meta.get("dataset_id")
                    entry["checksum"] = artifact_meta.get("semantic_checksum")
                    entry["timestamp"] = artifact_meta.get("run_timestamp")
                    entry["models_evaluated"] = artifact_meta.get("models_evaluated", [])
                    entry["case_count"] = len(artifact.get("cases", []))
                elif run_id == "18d":
                    artifact_meta = artifact.get("metadata", {})
                    entry["dataset_id"] = artifact_meta.get("dataset_id")
                    entry["checksum"] = artifact_meta.get("semantic_checksum")
                    entry["timestamp"] = artifact_meta.get("calibration_run_timestamp")
                    entry["case_count"] = len(artifact.get("corpus", []))
                    entry["models_evaluated"] = ["nvidia/nemotron-3-super-120b-a12b", "nvidia/nemotron-3.5-lightning-30b-a3b"]
                elif run_id == "18e":
                    entry["timestamp"] = artifact.get("run_timestamp")
                    entry["dataset_id"] = "eval-fixture-dataset-v1"
                    entry["checksum"] = "fixture-checksum-abc123"
                    qc = artifact.get("qualification_corpus", {})
                    entry["case_count"] = len(qc.get("cases", []))
                    entry["models_evaluated"] = ["nvidia/nemotron-3-super-120b-a12b", "nvidia/nemotron-3.5-lightning-30b-a3b"]
                    entry["verdicts"] = artifact.get("verdicts")
                elif run_id == "18f":
                    artifact_meta = artifact.get("metadata", {})
                    entry["dataset_id"] = artifact_meta.get("dataset_id")
                    entry["checksum"] = artifact_meta.get("semantic_checksum")
                    entry["timestamp"] = artifact_meta.get("run_timestamp")
                    entry["models_evaluated"] = artifact_meta.get("models_evaluated", [])
                    entry["case_count"] = len(artifact.get("cases", []))
                    entry["decision_gate"] = artifact.get("decision_gate")
            except HTTPException:
                entry["artifact_available"] = False
                entry["error"] = "Artifact unreadable"
        runs.append(entry)
    return runs


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    """Return full run summary for the given run ID."""
    if run_id not in _RUN_METADATA:
        raise HTTPException(
            status_code=404,
            detail=f"Run '{run_id}' not found. Valid run IDs: 18c, 18d, 18e, 18f",
        )
    artifact = _load_artifact(run_id)
    return _build_run_summary(run_id, artifact)


@router.get("/runs/{run_id}/cases")
async def list_run_cases(run_id: str) -> list[dict[str, Any]]:
    """Return list of cases for the given run with summary data."""
    if run_id not in _RUN_METADATA:
        raise HTTPException(
            status_code=404,
            detail=f"Run '{run_id}' not found. Valid run IDs: 18c, 18d, 18e, 18f",
        )
    artifact = _load_artifact(run_id)
    return _safe_artifact(_get_cases_for_run(run_id, artifact))


@router.get("/runs/{run_id}/cases/{case_id}")
async def get_run_case(run_id: str, case_id: str) -> dict[str, Any]:
    """Return full case detail including grader results and bounded raw_response."""
    if run_id not in _RUN_METADATA:
        raise HTTPException(
            status_code=404,
            detail=f"Run '{run_id}' not found. Valid run IDs: 18c, 18d, 18e, 18f",
        )
    artifact = _load_artifact(run_id)

    # For 18C: cases are at top level
    if run_id == "18c":
        cases = artifact.get("cases", [])
        for case in cases:
            if case.get("case_id") == case_id:
                return _safe_artifact(case)
        raise HTTPException(
            status_code=404,
            detail=f"Case '{case_id}' not found in run '{run_id}'",
        )

    # For 18D: cases in corpus (summary only — no full model results)
    if run_id == "18d":
        corpus = artifact.get("corpus", [])
        for case in corpus:
            if case.get("case_id") == case_id:
                detail = dict(case)
                # Pull calibration results if present
                calibration = artifact.get("calibration_results", {})
                if case_id in calibration:
                    detail["calibration_results"] = calibration[case_id]
                return _safe_artifact(detail)
        raise HTTPException(
            status_code=404,
            detail=f"Case '{case_id}' not found in run '{run_id}'",
        )

    # For 18F: same structure as 18C
    if run_id == "18f":
        cases = artifact.get("cases", [])
        for case in cases:
            if case.get("case_id") == case_id:
                return _safe_artifact(case)
        raise HTTPException(
            status_code=404,
            detail=f"Case '{case_id}' not found in run '{run_id}'",
        )

    # For 18E: cases in qualification_corpus
    if run_id == "18e":
        qc = artifact.get("qualification_corpus", {})
        cases = qc.get("cases", [])
        for case in cases:
            if case.get("case_id") == case_id:
                return _safe_artifact(case)
        raise HTTPException(
            status_code=404,
            detail=f"Case '{case_id}' not found in run '{run_id}'",
        )

    raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found")


@router.get("/model-status")
async def get_model_status() -> list[dict[str, Any]]:
    """Return current model availability status."""
    return _MODEL_STATUS
