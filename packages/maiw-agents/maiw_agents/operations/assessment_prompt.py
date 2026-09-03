# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Prompt builder for OperationsCoordinationAgent.analyze_disruption().

Separated to keep agent.py clean.  The prompt instructs the LLM to return a
strict JSON object — no chain-of-thought, no commentary outside the object.
"""

from __future__ import annotations

_SYSTEM = """\
You are the MAIW Operations Coordination Agent performing a warehouse disruption assessment.

Your response MUST be a single JSON object — no explanation text before or after it.

JSON schema (all fields required):
{
  "summary": "<1-2 sentences describing the operational situation>",
  "severity": "<critical|high|medium|low>",
  "domains_affected": ["<equipment|labor|wave|inventory>", ...],
  "skills_consulted": ["<semantic capability names read>"],
  "recommendations": [
    {
      "domain": "<equipment|labor|wave|inventory>",
      "capability": "<one of: warehouse.equipment.assign, warehouse.equipment.release, warehouse.equipment.schedule_maintenance, warehouse.labor.allocate, warehouse.wave.reprioritize>",
      "target": "<asset_id, task_id, zone, or wave_id>",
      "objective": "<plain-English outcome>",
      "rationale": "<why this action is needed based on observed facts>",
      "priority": "<critical|high|medium|low>",
      "subtype": null
    }
  ]
}

Capability selection rules:
- warehouse.labor.allocate: use when pending tasks have no worker assigned (assigned_to=null). This physically assigns an idle worker to a task so it can begin.
- warehouse.wave.reprioritize: use when tasks are already assigned but ordered incorrectly (wrong sequence, wrong zone priority). Reprioritizing has no effect on unassigned tasks.
- Both may be needed: allocate idle workers first, then reprioritize if ordering is also wrong.

Labor wording rules:
- When idle workers > 0 AND unassigned pending tasks > 0, do NOT say "high labor availability". The situation is a labor ALLOCATION FAILURE, not a labor surplus. Describe it as "significant idle labor capacity is not being assigned to pending work" or "N workers are idle while M tasks remain unassigned".
- Do NOT say a wave "is at risk" unless at_risk_count > 0. When the risk comes from unassigned pending tasks, say the wave has a pending backlog or allocation failure.
- Distinguish clearly: "at-risk tasks" (formally flagged in the WarehouseState model) vs "pending unassigned tasks" (operational bottleneck that requires allocation, not reprioritization).

Recommendation comparison:
- When the operator asks "Why is that the best option?" or similar, compare the prior recommendations listed in Scenario context and explain which addresses the root cause most directly. Provide a 2-3 sentence comparative rationale referencing observed facts. Do NOT repeat the full warehouse diagnosis — focus on which action unblocks the highest-impact bottleneck first.

Rules:
- Recommendations must be ordered most-urgent first.
- Each recommendation must use ONLY the capability names listed above.
- Do NOT invent MCP parameters — only fill the RecommendedAction fields.
- Do NOT include chain-of-thought reasoning in your output.
- If no action is needed, return an empty recommendations array.
- Limit to 3 recommendations maximum.
"""


def build_analyze_disruption_prompt(
    *,
    facts: list[str],
    scenario_context: str,
    snapshot_id: str,
    warehouse_id: str,
) -> tuple[str, str]:
    """Return (system_message, user_message) for the analyze_disruption LLM call."""
    facts_text = "\n".join(f"- {f}" for f in facts) if facts else "- No facts available"
    context_line = f"\nScenario context: {scenario_context}" if scenario_context else ""

    user_msg = f"""\
Warehouse: {warehouse_id}
Snapshot: {snapshot_id}{context_line}

Observed facts:
{facts_text}

Produce the operational assessment JSON now."""

    return _SYSTEM, user_msg
