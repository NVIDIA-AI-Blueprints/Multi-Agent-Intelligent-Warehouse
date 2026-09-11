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
Phase 18B evaluation fixture cases.

A small deterministic test corpus that proves evaluation infrastructure works.
NOT the full benchmark corpus — that is 18C.

Fixtures:
  1. wave17_labor_risk   — ASK: "Why is Wave 17 at risk?"
  2. equipment_failure   — ASK: "Is equipment contributing to the delay?"
  3. healthy_baseline    — ANALYZE: baseline scenario, no intervention needed

These fixtures use mock entity IDs that match the test context below.
"""

from __future__ import annotations

from .models import EvaluationCase, ModelEvaluationInput, TaskFamily


# ── Canonical test context ────────────────────────────────────────────────────

# Shared fixture context entity IDs — used in hallucination grader tests.
FIXTURE_CONTEXT_ENTITIES = [
    "wave-17",
    "labor-shift-morning",
    "labor-shift-afternoon",
    "worker-A001",
    "worker-A002",
    "worker-A003",
    "conveyor-main",
    "conveyor-backup",
    "equip-forklift-001",
    "zone-receiving",
    "zone-picking",
    "zone-shipping",
    "sku-high-priority",
    "sku-standard",
]

FIXTURE_DATASET_ID = "eval-fixture-dataset-v1"
FIXTURE_DATAPACK_CHECKSUM = "fixture-checksum-abc123"


# ── Case 1: Wave 17 labor risk ────────────────────────────────────────────────

WAVE17_LABOR_RISK_PROMPT = (
    "Why is Wave 17 at risk? "
    "Based on the current labor allocation and shift assignments, "
    "what is the primary bottleneck and what action would you recommend?"
)

wave17_labor_risk = EvaluationCase(
    case_id="wave17-labor-risk-v1",
    task_family=TaskFamily.ASK,
    prompt=WAVE17_LABOR_RISK_PROMPT,
    reasoning_level="high",
    risk_level="high",
    expected_capability="labor_reallocation",
    expected_target="wave-17",
    required_facts=[
        "wave-17",
        "labor",
    ],
    forbidden_claims=[
        # These entity IDs are NOT in the fixture context and must not appear.
        "wave-18",
        "wave-99",
        "worker-Z999",
        "external-agency",
    ],
    context_entities=FIXTURE_CONTEXT_ENTITIES,
    metadata={"fixture": True, "phase": "18B", "scenario": "labor-bottleneck"},
)

wave17_labor_risk_input = ModelEvaluationInput(
    evaluation_input_id="wave17-labor-risk-v1",
    dataset_id=FIXTURE_DATASET_ID,
    datapack_checksum=FIXTURE_DATAPACK_CHECKSUM,
    scenario_id="wave17-labor-bottleneck",
    warehouse_state_snapshot_id=None,
    context_snapshot_id="fixture-ctx-wave17-001",
    prompt=WAVE17_LABOR_RISK_PROMPT,
    prompt_hash=ModelEvaluationInput.make_prompt_hash(WAVE17_LABOR_RISK_PROMPT),
    reasoning_level="high",
    risk_level="high",
    deployment_mode="nvidia_hosted",
    task_family=TaskFamily.ASK,
)


# ── Case 2: Equipment failure contribution ────────────────────────────────────

EQUIPMENT_FAILURE_PROMPT = (
    "Is equipment contributing to the delay in Wave 17? "
    "Check the conveyor system and forklift status and explain "
    "whether any equipment issues are on the critical path."
)

equipment_failure = EvaluationCase(
    case_id="equipment-failure-v1",
    task_family=TaskFamily.ASK,
    prompt=EQUIPMENT_FAILURE_PROMPT,
    reasoning_level="high",
    risk_level="high",
    expected_capability="equipment_bypass",
    expected_target="conveyor-main",
    required_facts=[
        "conveyor",
        "wave-17",
    ],
    forbidden_claims=[
        "fire suppression",
        "structural damage",
        "evacuation",
    ],
    context_entities=FIXTURE_CONTEXT_ENTITIES,
    metadata={"fixture": True, "phase": "18B", "scenario": "equipment-failure"},
)

equipment_failure_input = ModelEvaluationInput(
    evaluation_input_id="equipment-failure-v1",
    dataset_id=FIXTURE_DATASET_ID,
    datapack_checksum=FIXTURE_DATAPACK_CHECKSUM,
    scenario_id="equipment-failure-wave17",
    warehouse_state_snapshot_id=None,
    context_snapshot_id="fixture-ctx-equipment-001",
    prompt=EQUIPMENT_FAILURE_PROMPT,
    prompt_hash=ModelEvaluationInput.make_prompt_hash(EQUIPMENT_FAILURE_PROMPT),
    reasoning_level="high",
    risk_level="high",
    deployment_mode="nvidia_hosted",
    task_family=TaskFamily.ASK,
)


# ── Case 3: Healthy baseline ──────────────────────────────────────────────────

HEALTHY_BASELINE_PROMPT = (
    "Analyze the current operational state of Wave 17. "
    "Is the wave on track? Are there any issues that require intervention?"
)

healthy_baseline = EvaluationCase(
    case_id="healthy-baseline-v1",
    task_family=TaskFamily.ANALYZE,
    prompt=HEALTHY_BASELINE_PROMPT,
    reasoning_level="medium",
    risk_level="low",
    expected_capability=None,    # no specific capability expected (model may say "no action needed")
    expected_target="wave-17",
    required_facts=[
        "wave-17",
    ],
    forbidden_claims=[
        # On a healthy baseline, model must NOT recommend fabricated interventions.
        "emergency shutdown",
        "evacuate",
        "crisis",
    ],
    context_entities=FIXTURE_CONTEXT_ENTITIES,
    metadata={
        "fixture": True,
        "phase": "18B",
        "scenario": "healthy-baseline",
        "note": "Model should NOT recommend unnecessary intervention on a healthy baseline.",
    },
)

healthy_baseline_input = ModelEvaluationInput(
    evaluation_input_id="healthy-baseline-v1",
    dataset_id=FIXTURE_DATASET_ID,
    datapack_checksum=FIXTURE_DATAPACK_CHECKSUM,
    scenario_id="healthy-baseline",
    warehouse_state_snapshot_id=None,
    context_snapshot_id="fixture-ctx-healthy-001",
    prompt=HEALTHY_BASELINE_PROMPT,
    prompt_hash=ModelEvaluationInput.make_prompt_hash(HEALTHY_BASELINE_PROMPT),
    reasoning_level="medium",
    risk_level="low",
    deployment_mode="nvidia_hosted",
    task_family=TaskFamily.ANALYZE,
)


# ── Fixture registry ──────────────────────────────────────────────────────────


ALL_FIXTURE_CASES = [
    wave17_labor_risk,
    equipment_failure,
    healthy_baseline,
]

ALL_FIXTURE_INPUTS = [
    wave17_labor_risk_input,
    equipment_failure_input,
    healthy_baseline_input,
]


def get_fixture_case(case_id: str) -> EvaluationCase:
    """Look up a fixture case by ID."""
    for case in ALL_FIXTURE_CASES:
        if case.case_id == case_id:
            return case
    raise KeyError(f"No fixture case with case_id={case_id!r}")


def get_fixture_input(evaluation_input_id: str) -> ModelEvaluationInput:
    """Look up a fixture input by ID."""
    for inp in ALL_FIXTURE_INPUTS:
        if inp.evaluation_input_id == evaluation_input_id:
            return inp
    raise KeyError(f"No fixture input with evaluation_input_id={evaluation_input_id!r}")
