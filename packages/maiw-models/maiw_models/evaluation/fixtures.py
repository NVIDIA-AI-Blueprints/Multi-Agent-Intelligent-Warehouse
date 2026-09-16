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
Phase 18B/18D/18E evaluation fixture cases.

A small deterministic test corpus that proves evaluation infrastructure works.
NOT the full benchmark corpus — that is 18C/18D/18E.

18B Fixtures:
  1. wave17_labor_risk   — ASK: "Why is Wave 17 at risk?"
  2. equipment_failure   — ASK: "Is equipment contributing to the delay?"
  3. healthy_baseline    — ANALYZE: baseline scenario, no intervention needed

18D Additions (§6 benchmark corpus expansion):
  4. evidence_ask_labor  — Case B: Evidence ASK "What evidence shows labor constraint?"
  5. analyze_action      — Case E: ANALYZE "What should we do?" (medium risk, medium reasoning)
  6. comparative_reasoning — Case F: "Why is that the best option?" (low risk)

18E Additions (§7 Nano qualification corpus):
  7. wave17_risk_low     — Case A: Wave 17 low-risk ASK (medium reasoning) POLICY ELIGIBLE
  8. equipment_ask_low   — Case C: Equipment ASK (low risk, medium reasoning) POLICY ELIGIBLE
  9. healthy_baseline_ask — Case D: Healthy baseline ASK POLICY ELIGIBLE

All cases use the same context entities for fixed-context invariant (§5).
Cases 4–9 are designed with low/medium risk so Nano is POLICY ELIGIBLE (when available).

Policy eligibility labels (18E §7):
  POLICY ELIGIBLE       — low/medium risk + medium reasoning → Nano-routable when enabled
  RESEARCH ONLY         — high/critical risk or high reasoning → Super/Ultra only
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
    expected_capability=None,  # no specific capability expected (model may say "no action needed")
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


# ── Case 4 (18D): Evidence ASK — labor constraint ─────────────────────────────

EVIDENCE_ASK_LABOR_PROMPT = (
    "What evidence shows that labor is the primary constraint on Wave 17? "
    "Cite the specific workers, shifts, and tasks that support this conclusion."
)

evidence_ask_labor = EvaluationCase(
    case_id="evidence-ask-labor-v1",
    task_family=TaskFamily.ASK,
    prompt=EVIDENCE_ASK_LABOR_PROMPT,
    reasoning_level="medium",
    risk_level="low",
    expected_capability="labor_reallocation",
    expected_target="wave-17",
    required_facts=[
        "labor",
        "wave-17",
        "worker",
    ],
    forbidden_claims=[
        "wave-18",
        "wave-99",
        "worker-Z999",
        "external-agency",
    ],
    context_entities=FIXTURE_CONTEXT_ENTITIES,
    metadata={
        "fixture": True,
        "phase": "18D",
        "scenario": "labor-bottleneck",
        "policy_eligibility_nano": "POLICY ELIGIBLE",
        "benchmark_case": "B",
        "description": "Evidence ASK — labor constraint evidence for Wave 17",
    },
)

evidence_ask_labor_input = ModelEvaluationInput(
    evaluation_input_id="evidence-ask-labor-v1",
    dataset_id=FIXTURE_DATASET_ID,
    datapack_checksum=FIXTURE_DATAPACK_CHECKSUM,
    scenario_id="wave17-labor-bottleneck",
    warehouse_state_snapshot_id=None,
    context_snapshot_id="fixture-ctx-wave17-001",
    prompt=EVIDENCE_ASK_LABOR_PROMPT,
    prompt_hash=ModelEvaluationInput.make_prompt_hash(EVIDENCE_ASK_LABOR_PROMPT),
    reasoning_level="medium",
    risk_level="low",
    deployment_mode="nvidia_hosted",
    task_family=TaskFamily.ASK,
)


# ── Case 5 (18D): ANALYZE — what should we do ────────────────────────────────

ANALYZE_ACTION_PROMPT = (
    "Based on the current state of Wave 17, what is the recommended course of action? "
    "Explain why this action addresses the root cause."
)

analyze_action = EvaluationCase(
    case_id="analyze-action-v1",
    task_family=TaskFamily.ANALYZE,
    prompt=ANALYZE_ACTION_PROMPT,
    reasoning_level="medium",
    risk_level="medium",
    expected_capability="labor_reallocation",
    expected_target="wave-17",
    required_facts=[
        "wave-17",
        "labor",
    ],
    forbidden_claims=[
        "wave-18",
        "wave-99",
        "emergency shutdown",
        "evacuate",
        "external-agency",
    ],
    context_entities=FIXTURE_CONTEXT_ENTITIES,
    metadata={
        "fixture": True,
        "phase": "18D",
        "scenario": "labor-bottleneck",
        "policy_eligibility_nano": "POLICY ELIGIBLE",
        "benchmark_case": "C",
        "description": "ANALYZE — recommended action for Wave 17 labor constraint",
    },
)

analyze_action_input = ModelEvaluationInput(
    evaluation_input_id="analyze-action-v1",
    dataset_id=FIXTURE_DATASET_ID,
    datapack_checksum=FIXTURE_DATAPACK_CHECKSUM,
    scenario_id="wave17-labor-bottleneck",
    warehouse_state_snapshot_id=None,
    context_snapshot_id="fixture-ctx-wave17-001",
    prompt=ANALYZE_ACTION_PROMPT,
    prompt_hash=ModelEvaluationInput.make_prompt_hash(ANALYZE_ACTION_PROMPT),
    reasoning_level="medium",
    risk_level="medium",
    deployment_mode="nvidia_hosted",
    task_family=TaskFamily.ANALYZE,
)


# ── Case 6 (18D): Comparative reasoning ──────────────────────────────────────

COMPARATIVE_REASONING_PROMPT = (
    "Compare labor reallocation vs equipment bypass as interventions for Wave 17. "
    "Which is more appropriate given current conditions, and why?"
)

comparative_reasoning = EvaluationCase(
    case_id="comparative-reasoning-v1",
    task_family=TaskFamily.ANALYZE,
    prompt=COMPARATIVE_REASONING_PROMPT,
    reasoning_level="medium",
    risk_level="low",
    expected_capability=None,  # either labor_reallocation or equipment_bypass valid
    expected_target="wave-17",
    required_facts=[
        "wave-17",
        "labor",
        "conveyor",
    ],
    forbidden_claims=[
        "wave-18",
        "wave-99",
        "emergency shutdown",
        "evacuate",
        "external-agency",
    ],
    context_entities=FIXTURE_CONTEXT_ENTITIES,
    metadata={
        "fixture": True,
        "phase": "18D",
        "scenario": "labor-bottleneck",
        "policy_eligibility_nano": "POLICY ELIGIBLE",
        "benchmark_case": "D",
        "description": "Comparative reasoning — labor vs equipment intervention for Wave 17",
    },
)

comparative_reasoning_input = ModelEvaluationInput(
    evaluation_input_id="comparative-reasoning-v1",
    dataset_id=FIXTURE_DATASET_ID,
    datapack_checksum=FIXTURE_DATAPACK_CHECKSUM,
    scenario_id="wave17-labor-bottleneck",
    warehouse_state_snapshot_id=None,
    context_snapshot_id="fixture-ctx-wave17-001",
    prompt=COMPARATIVE_REASONING_PROMPT,
    prompt_hash=ModelEvaluationInput.make_prompt_hash(COMPARATIVE_REASONING_PROMPT),
    reasoning_level="medium",
    risk_level="low",
    deployment_mode="nvidia_hosted",
    task_family=TaskFamily.ANALYZE,
)


# ── Case 7 (18E): Case A — Wave 17 low-risk ASK ──────────────────────────────
# 18E §7 Case A: "Why is Wave 17 at risk?" — low risk, medium reasoning.
# NOTE: wave17_labor_risk (18B) uses high risk/reasoning → RESEARCH ONLY.
# This 18E variant uses low risk/medium reasoning → POLICY ELIGIBLE for Nano.

WAVE17_RISK_LOW_PROMPT = (
    "Why is Wave 17 at risk? "
    "Summarize the primary bottleneck based on available labor and shift data."
)

wave17_risk_low = EvaluationCase(
    case_id="wave17-risk-low-v1",
    task_family=TaskFamily.ASK,
    prompt=WAVE17_RISK_LOW_PROMPT,
    reasoning_level="medium",
    risk_level="low",
    expected_capability="labor_reallocation",
    expected_target="wave-17",
    required_facts=[
        "wave-17",
        "labor",
    ],
    forbidden_claims=[
        "wave-18",
        "wave-99",
        "worker-Z999",
        "external-agency",
        "emergency shutdown",
        "evacuate",
    ],
    context_entities=FIXTURE_CONTEXT_ENTITIES,
    metadata={
        "fixture": True,
        "phase": "18E",
        "scenario": "labor-bottleneck",
        "policy_eligibility": "POLICY ELIGIBLE",
        "benchmark_case": "A",
        "description": "18E Case A — Wave 17 at-risk ASK (low risk, medium reasoning)",
    },
)

wave17_risk_low_input = ModelEvaluationInput(
    evaluation_input_id="wave17-risk-low-v1",
    dataset_id=FIXTURE_DATASET_ID,
    datapack_checksum=FIXTURE_DATAPACK_CHECKSUM,
    scenario_id="wave17-labor-bottleneck",
    warehouse_state_snapshot_id=None,
    context_snapshot_id="fixture-ctx-wave17-001",
    prompt=WAVE17_RISK_LOW_PROMPT,
    prompt_hash=ModelEvaluationInput.make_prompt_hash(WAVE17_RISK_LOW_PROMPT),
    reasoning_level="medium",
    risk_level="low",
    deployment_mode="nvidia_hosted",
    task_family=TaskFamily.ASK,
)


# ── Case 8 (18E): Case C — Equipment ASK ─────────────────────────────────────
# 18E §7 Case C: "What is causing the equipment-related disruption?"
# Low risk, medium reasoning → POLICY ELIGIBLE.
# NOTE: equipment_failure (18B) uses high risk/reasoning → RESEARCH ONLY.

EQUIPMENT_ASK_LOW_PROMPT = (
    "What is causing the equipment-related disruption in the warehouse? "
    "Which equipment is affected and what is the recommended response?"
)

equipment_ask_low = EvaluationCase(
    case_id="equipment-ask-low-v1",
    task_family=TaskFamily.ASK,
    prompt=EQUIPMENT_ASK_LOW_PROMPT,
    reasoning_level="medium",
    risk_level="low",
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
        "wave-18",
        "wave-99",
    ],
    context_entities=FIXTURE_CONTEXT_ENTITIES,
    metadata={
        "fixture": True,
        "phase": "18E",
        "scenario": "equipment-failure",
        "policy_eligibility": "POLICY ELIGIBLE",
        "benchmark_case": "C",
        "description": "18E Case C — Equipment disruption ASK (low risk, medium reasoning)",
    },
)

equipment_ask_low_input = ModelEvaluationInput(
    evaluation_input_id="equipment-ask-low-v1",
    dataset_id=FIXTURE_DATASET_ID,
    datapack_checksum=FIXTURE_DATAPACK_CHECKSUM,
    scenario_id="equipment-failure-wave17",
    warehouse_state_snapshot_id=None,
    context_snapshot_id="fixture-ctx-equipment-001",
    prompt=EQUIPMENT_ASK_LOW_PROMPT,
    prompt_hash=ModelEvaluationInput.make_prompt_hash(EQUIPMENT_ASK_LOW_PROMPT),
    reasoning_level="medium",
    risk_level="low",
    deployment_mode="nvidia_hosted",
    task_family=TaskFamily.ASK,
)


# ── Case 9 (18E): Case D — Healthy baseline ASK ──────────────────────────────
# 18E §7 Case D: "Is there an operational problem that requires intervention?"
# Low risk, medium reasoning → POLICY ELIGIBLE.
# healthy_baseline (18B) is an ANALYZE case; this 18E variant is ASK.

HEALTHY_BASELINE_ASK_PROMPT = (
    "Is there an operational problem with Wave 17 that requires immediate intervention? "
    "Based on current labor and equipment status, what is your assessment?"
)

healthy_baseline_ask = EvaluationCase(
    case_id="healthy-baseline-ask-v1",
    task_family=TaskFamily.ASK,
    prompt=HEALTHY_BASELINE_ASK_PROMPT,
    reasoning_level="medium",
    risk_level="low",
    expected_capability=None,  # correct answer is "no urgent action needed" — capability may be absent
    expected_target="wave-17",
    required_facts=[
        "wave-17",
    ],
    forbidden_claims=[
        "emergency shutdown",
        "evacuate",
        "crisis",
        "wave-18",
        "wave-99",
    ],
    context_entities=FIXTURE_CONTEXT_ENTITIES,
    metadata={
        "fixture": True,
        "phase": "18E",
        "scenario": "healthy-baseline",
        "policy_eligibility": "POLICY ELIGIBLE",
        "benchmark_case": "D",
        "description": "18E Case D — Healthy baseline ASK (low risk, medium reasoning)",
    },
)

healthy_baseline_ask_input = ModelEvaluationInput(
    evaluation_input_id="healthy-baseline-ask-v1",
    dataset_id=FIXTURE_DATASET_ID,
    datapack_checksum=FIXTURE_DATAPACK_CHECKSUM,
    scenario_id="healthy-baseline",
    warehouse_state_snapshot_id=None,
    context_snapshot_id="fixture-ctx-healthy-001",
    prompt=HEALTHY_BASELINE_ASK_PROMPT,
    prompt_hash=ModelEvaluationInput.make_prompt_hash(HEALTHY_BASELINE_ASK_PROMPT),
    reasoning_level="medium",
    risk_level="low",
    deployment_mode="nvidia_hosted",
    task_family=TaskFamily.ASK,
)


# ── Policy eligibility labels (18E §7) ───────────────────────────────────────

# Map case_id → policy eligibility label for the qualification corpus.
# POLICY ELIGIBLE: low/medium risk + medium reasoning → Nano-routable when enabled.
# RESEARCH ONLY — NOT PRODUCTION ELIGIBLE: high/critical risk or high reasoning.
POLICY_ELIGIBILITY: dict[str, str] = {
    # 18B high-risk cases — RESEARCH ONLY
    "wave17-labor-risk-v1": "RESEARCH ONLY — NOT PRODUCTION ELIGIBLE",
    "equipment-failure-v1": "RESEARCH ONLY — NOT PRODUCTION ELIGIBLE",
    # 18B baseline — POLICY ELIGIBLE (low risk, medium reasoning)
    "healthy-baseline-v1": "POLICY ELIGIBLE",
    # 18D cases — POLICY ELIGIBLE
    "evidence-ask-labor-v1": "POLICY ELIGIBLE",
    "analyze-action-v1": "POLICY ELIGIBLE",
    "comparative-reasoning-v1": "POLICY ELIGIBLE",
    # 18E corpus (Cases A–F)
    "wave17-risk-low-v1": "POLICY ELIGIBLE",        # Case A
    # Case B = evidence-ask-labor-v1 (18D)          # Case B
    "equipment-ask-low-v1": "POLICY ELIGIBLE",       # Case C
    "healthy-baseline-ask-v1": "POLICY ELIGIBLE",    # Case D
    # Case E = analyze-action-v1 (18D)               # Case E
    # Case F = comparative-reasoning-v1 (18D)        # Case F
}


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

# 18D additions — Nano-eligible cases (low/medium risk + medium reasoning)
ALL_18D_FIXTURE_CASES = [
    evidence_ask_labor,
    analyze_action,
    comparative_reasoning,
]

ALL_18D_FIXTURE_INPUTS = [
    evidence_ask_labor_input,
    analyze_action_input,
    comparative_reasoning_input,
]

# 18E additions — Nano qualification corpus (Cases A, C, D; B/E/F reuse 18D)
ALL_18E_FIXTURE_CASES = [
    wave17_risk_low,       # Case A
    equipment_ask_low,     # Case C
    healthy_baseline_ask,  # Case D
]

ALL_18E_FIXTURE_INPUTS = [
    wave17_risk_low_input,
    equipment_ask_low_input,
    healthy_baseline_ask_input,
]

# 18E qualification corpus — all 6 policy-eligible cases (A–F)
NANO_QUALIFICATION_CORPUS: list[EvaluationCase] = [
    wave17_risk_low,          # A
    evidence_ask_labor,       # B
    equipment_ask_low,        # C
    healthy_baseline_ask,     # D
    analyze_action,           # E
    comparative_reasoning,    # F
]

# Combined registry (all 18B + 18D + 18E cases)
ALL_KNOWN_CASES = ALL_FIXTURE_CASES + ALL_18D_FIXTURE_CASES + ALL_18E_FIXTURE_CASES
ALL_KNOWN_INPUTS = ALL_FIXTURE_INPUTS + ALL_18D_FIXTURE_INPUTS + ALL_18E_FIXTURE_INPUTS


def get_fixture_case(case_id: str) -> EvaluationCase:
    """Look up a fixture case by ID (18B + 18D + 18E)."""
    for case in ALL_KNOWN_CASES:
        if case.case_id == case_id:
            return case
    raise KeyError(f"No fixture case with case_id={case_id!r}")


def get_fixture_input(evaluation_input_id: str) -> ModelEvaluationInput:
    """Look up a fixture input by ID (18B + 18D + 18E)."""
    for inp in ALL_KNOWN_INPUTS:
        if inp.evaluation_input_id == evaluation_input_id:
            return inp
    raise KeyError(f"No fixture input with evaluation_input_id={evaluation_input_id!r}")


def get_policy_eligibility(case_id: str) -> str:
    """Return policy eligibility label for a case_id (18E §7)."""
    return POLICY_ELIGIBILITY.get(case_id, "UNKNOWN — NOT IN ELIGIBILITY MAP")
