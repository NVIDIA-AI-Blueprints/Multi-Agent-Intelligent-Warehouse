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
Phase 18B evaluation models.

Typed foundation for offline multi-model benchmarking (18C+).
No benchmarks run here — this is the data model only.

Key invariants:
  - Evaluation must NOT create ActionProposal, invoke DecisionEngine,
    request approval, invoke ActionExecutor, or call write MCP capabilities.
  - Evaluation calls must go through ModelGateway only.
  - Evaluation results must not contaminate Copilot conversation or approval queues.

Reproducibility identity: dataset_id + prompt_hash + model_id + deployment_id
+ context_snapshot_id uniquely identify an evaluation run.  Timestamps are NOT
part of the identity (they change on re-run; they belong in the result only).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── Task family ───────────────────────────────────────────────────────────────


class TaskFamily(str, Enum):
    """High-level classification of evaluation task type."""

    ASK = "ASK"            # Operator question — "Why is Wave 17 at risk?"
    ANALYZE = "ANALYZE"    # Analytical request — deep inspection of warehouse state
    OUTCOME_EXPLAIN = "OUTCOME_EXPLAIN"  # Explain a past decision or outcome


# ── Input ─────────────────────────────────────────────────────────────────────


@dataclass
class ModelEvaluationInput:
    """
    Complete, self-contained specification of one evaluation run.

    Deterministic identity: all fields except evaluation_input_id contribute
    to the semantic checksum.  evaluation_input_id is a stable short name
    (e.g. "wave17-labor-risk-v1").

    OperationalContextSnapshot fields (dataset_id, datapack_checksum,
    scenario_id, warehouse_state_snapshot_id, context_snapshot_id) are
    populated from the WS2 snapshot at capture time.
    """

    evaluation_input_id: str       # human-readable stable ID
    dataset_id: str                # WS2 DataPack dataset identifier
    datapack_checksum: str         # semantic_checksum from DataPack (immutable)
    scenario_id: str               # scenario label (e.g. "wave17-labor-bottleneck")
    warehouse_state_snapshot_id: str | None   # from WarehouseStateSnapshot if available
    context_snapshot_id: str | None           # from OperationalContextSnapshot if available
    prompt: str                    # the exact prompt text
    prompt_hash: str               # SHA-256 of prompt (hex); populated by make_prompt_hash()
    reasoning_level: str           # "low" | "medium" | "high"
    risk_level: str                # "low" | "medium" | "high" | "critical"
    deployment_mode: str           # "nvidia_hosted" | "local_nim" | ...
    task_family: TaskFamily = TaskFamily.ASK
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def make_prompt_hash(prompt: str) -> str:
        """Stable SHA-256 hex digest of prompt text."""
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def evaluation_key(self) -> str:
        """
        Deterministic identity string for this evaluation input.

        Does NOT include evaluation_input_id (human label) or timestamps.
        Suitable as a cache key or dedup check.
        """
        identity = {
            "dataset_id": self.dataset_id,
            "datapack_checksum": self.datapack_checksum,
            "scenario_id": self.scenario_id,
            "context_snapshot_id": self.context_snapshot_id or "",
            "warehouse_state_snapshot_id": self.warehouse_state_snapshot_id or "",
            "prompt_hash": self.prompt_hash,
            "reasoning_level": self.reasoning_level,
            "risk_level": self.risk_level,
            "deployment_mode": self.deployment_mode,
        }
        canonical = json.dumps(identity, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()


# ── Result ────────────────────────────────────────────────────────────────────


@dataclass
class ModelEvaluationResult:
    """
    Result of running one ModelEvaluationInput against one model/deployment.

    Token fields (input_tokens, output_tokens) are populated only when the
    provider returns them.  Do not fabricate.

    evaluation_input_id + model_id + deployment_id together uniquely identify
    this result row for comparison across models.
    """

    evaluation_input_id: str
    model_id: str
    deployment_id: str         # e.g. "nvidia_hosted", "local_nim/server-a", ...
    response: str | None       # raw model response text; None on error
    latency_ms: float          # end-to-end latency for this model call
    routing_latency_ms: float  # routing-only latency from ModelRouteDecision
    routing_strategy: str      # "rules" (from ModelRouteDecision)
    candidate_models: list[str]  # eligible candidates at routing time
    input_tokens: int | None = None    # from usage dict if returned by provider
    output_tokens: int | None = None   # from usage dict if returned by provider
    error: str | None = None           # error message; None on success
    structured_output_valid: bool | None = None  # None when structured output not expected
    grader_results: list[dict[str, Any]] = field(default_factory=list)  # from EvaluationGrader


# ── Case ──────────────────────────────────────────────────────────────────────


@dataclass
class EvaluationCase:
    """
    Reusable typed evaluation case — the dataset format for 18C benchmarking.

    Fields marked Optional are not required; deterministic graders skip checks
    for absent fields.

    Grader contract:
      - expected_capability: graders check that recommendation matches this
      - expected_target: graders check that response addresses this entity ID
      - required_facts: graders verify response references all listed facts
      - forbidden_claims: graders verify response asserts none of these claims
    """

    case_id: str
    task_family: TaskFamily
    prompt: str
    context_snapshot_id: str | None = None
    reasoning_level: str = "medium"
    risk_level: str = "low"
    expected_capability: str | None = None   # e.g. "wave_recovery", "labor_reallocation"
    expected_target: str | None = None       # canonical entity ID expected in response
    required_facts: list[str] = field(default_factory=list)
    forbidden_claims: list[str] = field(default_factory=list)
    # Structured output schema (JSON Schema dict) — if set, schema grader uses this.
    expected_schema: dict[str, Any] | None = None
    # Context supplied to the graders (reduced projection; no PII).
    context_entities: list[str] = field(default_factory=list)   # canonical entity IDs in scope
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Grader result ─────────────────────────────────────────────────────────────


@dataclass
class GraderResult:
    """
    Result from one EvaluationGrader for one EvaluationCase + ModelEvaluationResult.

    score is meaningful only for graders that produce a continuous measure
    (e.g. 0.0–1.0 evidence coverage).  For pass/fail graders, score is None.
    """

    grader_name: str
    passed: bool
    score: float | None = None    # 0.0–1.0 where meaningful; None for pure pass/fail
    reason: str = ""              # human-readable explanation
    evidence: list[str] = field(default_factory=list)  # supporting text fragments


# ── Reproducibility ───────────────────────────────────────────────────────────


def make_evaluation_run_key(
    dataset_id: str,
    prompt_hash: str,
    model_id: str,
    deployment_id: str,
    context_snapshot_id: str | None,
    warehouse_state_snapshot_id: str | None,
) -> str:
    """
    Deterministic evaluation run identity key.

    Timestamps are excluded — re-running the same input on the same model
    must produce the same key.  Use this for dedup and cross-model comparison.
    """
    identity = {
        "dataset_id": dataset_id,
        "prompt_hash": prompt_hash,
        "model_id": model_id,
        "deployment_id": deployment_id,
        "context_snapshot_id": context_snapshot_id or "",
        "warehouse_state_snapshot_id": warehouse_state_snapshot_id or "",
    }
    canonical = json.dumps(identity, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()
