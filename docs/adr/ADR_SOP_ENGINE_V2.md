# ADR: SOP Engine v2 — Architecture Decision Record

**Status:** ACCEPTED — Foundation Implementation
**Date:** 2026-09-26
**Deciders:** MAIW Architecture Team
**Verified rerun:** Yes — generated from verified HEAD e33ed699 (nvidia/main state)
**Related document:** docs/architecture/SOP_ENGINE_V2_DESIGN.md
**Implemented on:** branch `feat/sop-engine-v2-foundation`

Option B is implemented as a foundation. `packages/maiw-agents/maiw_agents/sop_engine/`
exists; both runtimes implement `SOPStepExecutor`; all three v1 SOPs run unmodified;
Proof SOP A (`agents/sops/operations_coordination/wave_risk_resolution.v2.yaml`) ships
with declared completion criteria. Proof SOPs B and C, MODEL_JUDGE, persistence, OTEL
spans and Blueprint extraction (Option C) remain deferred — see the design document's
"Foundation implementation status" table.

---

## Context

### Problem statement

The MAIW Phase 18H/19A implementation has a mature SOP contract layer (`packages/maiw-agents/maiw_agents/contracts/sop.py`) and two working runtimes (`MAIWDeterministicRuntime`, `DeepAgentsRuntime`). However, an architecture audit conducted at HEAD e33ed699 identified five critical gaps:

1. **No per-step completion validation.** Both runtimes advance unconditionally after step execution. `MAIWDeterministicRuntime._run_step()` does not validate step output before calling `current_step_id = step.next_step_id` (deterministic.py line 173). `DeepAgentsRuntime._parse_result()` uses regex on the last AI message (line 394) — not a typed or schema-validated result.

2. **Deep Agents completion is text-pattern-based.** Completion is detected via `re.search(r"RECOMMENDATION:\s*(\{.*?\})")` (deep_agents_runtime.py line 399) and "WAITING_FOR_GOVERNANCE" substring match (line 394). The full SOP is placed in the system prompt (`_build_sop_system_prompt()` lines 80–111), giving the model the ability to skip, compress, or reorder steps without MAIW detection.

3. **No structured retry or escalation at step level.** Retry exists only as a task-level iteration counter (`TerminationPolicy.max_iterations`, agent.py line 122). No per-step retry policy, no retry budget per validator failure type, no structured escalation reason codes.

4. **No post-write authoritative re-read.** `DeepAgentsRuntime.resume_after_governance()` (lines 460–530) returns COMPLETED based on `decision_outcome == "APPROVED"` string check without reading authoritative warehouse state to confirm the write succeeded.

5. **No evidence requirement model per step.** `AgentObservation` (task.py lines 119–140) exists but no `evidence_requirements` field on `SOPStep` specifies what must be collected before marking a step complete.

### Current architecture constraints

- `SOPDefinition` and `SOPStep` are stable, validated Pydantic models (Phase 18H)
- `AgentRuntime` Protocol exists and cleanly separates the runtime seam (runtime.py lines 87–126)
- Both runtimes implement the Protocol without cross-contamination
- WRITE capability blocking is structurally enforced at multiple layers (validate_sop() rules 4–5; check_capability_alignment() runtime.py lines 130–161; _build_maiw_tools() deep_agents_runtime.py line 129)
- Governance handoff (`WAITING_FOR_GOVERNANCE`) is a typed status in `AgentTaskStatus`
- Three YAML SOPs exist covering operations coordination, labor, and wave domains
- Authority-hardening PR (fix/agent-package-authority-boundary, SHA 1dc2b7c) removes `maiw-execution` from `packages/maiw-agents/pyproject.toml`

---

## Decision drivers

1. **Completion guarantees:** Step completion must be validated, not assumed.
2. **Runtime neutrality:** SOP semantics (completion criteria, validators, escalation) must not be embedded in any single runtime.
3. **Write safety:** No SOP step may complete solely on HTTP 200 or model assertion.
4. **Backward compatibility:** Existing v1 SOPs must run unchanged.
5. **Governance boundary:** SOP Engine must never call ActionExecutor, DecisionEngine, or WRITE capabilities.
6. **Operational audit trail:** Every step completion must produce structured evidence.
7. **Incremental evolution:** Changes must be additive; no breaking changes to existing contracts.

---

## Options considered

### Option A: Keep SOP lifecycle embedded in each runtime

**Description:** Each runtime (deterministic, deep_agents, future runtimes) continues to manage its own step lifecycle. Completion validation is added to each runtime independently.

**Pros:**
- Minimal refactoring; changes are localized to each runtime
- No new protocol or state model

**Cons:**
- Cross-runtime consistency requires duplicating validator logic in every runtime
- Step-level retry policy must be reimplemented per runtime
- Escalation reason codes diverge between runtimes
- Adding a third runtime (NemoClaw, Codex) requires re-implementing completion semantics again
- No single place to enforce post-write completion invariant
- Deep Agents runtime continues to have text-based completion detection with no structural improvement path
- Evidence model must be duplicated per runtime

**Verdict: REJECTED.** Does not address the cross-runtime consistency, structured completion validation, or evidence model gaps. Technical debt compounds with each new runtime.

---

### Option B: Internal reusable SOP Engine within packages/maiw-agents

**Description:** Extract procedure lifecycle (step execution, validation, branching, retry, escalation, evidence) into a SOP Engine layer within `packages/maiw-agents`. Runtimes become step executors via a `SOPStepExecutor` protocol. The SOP Engine owns `ProcedureExecutionState` and all completion decisions.

**Architecture:**

```
SOP Engine (new, within packages/maiw-agents)
    ├── ProcedureExecutionState (procedure lifecycle)
    ├── StepCompletionValidator (SCHEMA, STATE_PREDICATE, CAPABILITY_RESULT, HUMAN, MODEL_JUDGE)
    ├── BranchEvaluator (declarative predicates, no eval())
    ├── RetryPolicy enforcer (per-step budget)
    ├── EscalationRouter (structured reason codes)
    └── AuditTrail (step evidence, branch history)

SOPStepExecutor Protocol (new seam)
    ├── MAIWDeterministicRuntime.execute_step()  (implements protocol)
    └── DeepAgentsRuntime.execute_step()         (implements protocol, step-at-a-time)

AgentRuntime Protocol (existing, unchanged)
    └── run_task(definition, sop, state, context) → AgentTaskResult
```

**Changes to existing code:**
- `SOPStep`: add optional v2 fields (objective, required_inputs, expected_output, completion, branches, retry_policy, timeout_seconds, escalation, evidence_requirements) — all Optional, None defaults
- `MAIWDeterministicRuntime._run_step()`: extract as `execute_step()` implementing `SOPStepExecutor`; add validator invocation between step execution and advancement
- `DeepAgentsRuntime.run_task()`: refactor to step-at-a-time model; replace regex completion detection with typed `StepResult`
- `DeepAgentsRuntime.resume_after_governance()`: add authoritative re-read before declaring COMPLETED

**No changes to:**
- `SOPDefinition` (v1 fields unchanged)
- `AgentRuntime` Protocol
- `AgentTaskState` or `AgentTaskStatus`
- `AgentDefinition`, `GovernanceBoundary`, `TerminationPolicy`
- `validate_sop()` rules 1–8 (only additions)
- WRITE capability blocking (already correct)
- Governance handoff architecture

**Pros:**
- Single source of truth for step completion semantics across all runtimes
- Backward compatibility: v1 SOPs run with no-op validators (None completion field)
- No new package; refactor within existing package structure
- Centralizes escalation reason codes (typed, not free-form)
- Enables runtime replaceability: any future runtime implementing `execute_step()` gets correct completion, retry, escalation, and evidence behavior
- Post-write STATE_PREDICATE validator enforces Section 34 hard invariant
- Incremental: add validators per step, per SOP, at the team's pace

**Cons:**
- More refactoring than Option A in the short term
- Requires step-at-a-time refactor of DeepAgentsRuntime (behavioral change)
- ProcedureExecutionState adds new persistence requirement (procedure state must survive restarts for governance-wait periods)
- Step-at-a-time Deep Agents: N model calls per task vs 1 graph.ainvoke() today (latency regression for long SOPs)

**Verdict: RECOMMENDED.** The refactoring cost is justified by the gains in completion guarantees, runtime neutrality, and write safety. The latency regression is bounded by step timeouts and is mitigated by using STATE_PREDICATE/CAPABILITY_RESULT validators (deterministic, fast) over MODEL_JUDGE wherever possible.

---

### Option C: Standalone Blueprint package immediately

**Description:** Extract the SOP Engine into a new standalone package (`packages/maiw-sop` or `packages/maiw-procedure`) that can be published as a reusable NVIDIA AI Blueprint component.

**Pros:**
- Maximum reusability; other teams could adopt the SOP Engine
- Clean package boundary forces domain-neutral design
- Blueprint publishing enables external ecosystem

**Cons:**
- Premature: Section 50 of the Design Document shows 4+ Blueprint readiness criteria not yet met:
  - Equipment and inventory SOPs not yet defined (only 2 warehouse domains covered)
  - ProcedureExecutionState not implemented; persistence semantics unresolved
  - No cross-runtime equivalence test
  - Core engine not yet extracted from warehouse-specific code
- Package extraction before internal validation risks publishing an immature API
- Additional packaging, versioning, and dependency management overhead with no current external consumers
- Warehouse domain code entanglement must be resolved before extraction anyway (same work as Option B)

**Verdict: DEFERRED.** Appropriate after Option B is complete and validated with 3+ proof SOPs across 2+ runtimes. The internal SOP Engine (Option B) is the prerequisite for a meaningful Blueprint.

---

## Decision

**Option B is adopted: Internal Reusable SOP Engine within `packages/maiw-agents`.**

This decision:
- Addresses all five identified gaps in the current implementation
- Preserves backward compatibility for existing v1 SOPs
- Does not change the AgentRuntime Protocol or governance boundary
- Enables future runtime replaceability (NemoClaw, Codex, future agentic frameworks)
- Creates the foundation for eventual Blueprint extraction (Option C) once the three proof SOPs are validated

---

## Consequences

### Positive consequences

1. **Completion guarantees:** Every SOP step has a defined completion criterion (or explicitly opts into the current no-op via None). No step advances without passing its validator.

2. **Write safety enforced:** Post-write steps cannot complete without authoritative state re-read via STATE_PREDICATE validator. EXECUTION_AMBIGUITY_UNRESOLVED escalation handles INDETERMINATE outcomes.

3. **Structured escalation:** Typed `EscalationReasonCode` enum replaces free-form model prose. Operator escalation inbox receives structured, actionable reason codes.

4. **Runtime neutrality:** Any future runtime implementing `SOPStepExecutor.execute_step()` inherits correct completion, retry, escalation, and evidence semantics without re-implementing them.

5. **Evidence audit trail:** `evidence_requirements` on SOPStep v2 enforces structured evidence collection before step completion. No chain-of-thought accepted as evidence.

6. **Backward compatibility:** All existing v1 SOPs (wave_risk_resolution, labor_constraint_assessment, wave_risk_assessment) continue running unchanged. New fields default to None.

### Negative consequences / accepted risks

1. **Step-at-a-time latency (Deep Agents):** N model calls per task replaces 1 graph.ainvoke(). For a 7-step SOP: 7 calls vs 1. Mitigation: step timeouts bound latency; deterministic validators add <1ms overhead; MODEL_JUDGE is avoided for deterministic decisions.

2. **ProcedureExecutionState persistence:** Long-running procedures (spanning governance wait periods) require durable state. This adds a persistence dependency not present in the current in-memory implementation. Mitigation: store in existing apps/api database; existing `AgentTaskState` can be extended.

3. **Migration work:** Proof SOPs B and C require new YAML files with V2 fields. Proof SOP A requires updating `wave_risk_resolution.v1.yaml` to v2 format (or creating `wave_risk_resolution.v2.yaml`). This is implementation work approved by this ADR.

4. **Step-at-a-time behavioral change (Deep Agents):** The model no longer sees all SOP steps simultaneously. This may change model behavior for SOPs where full procedure context improves reasoning. Mitigation: SOPStepExecutor may pass procedure history (completed steps + their outcomes) as additional context to each step.

---

## Alternatives not considered in depth

- **LangGraph as SOP Engine:** Rejected in MAIW V2 Roadmap (memory per project_v2_roadmap.md). LangGraph would own procedure workflow semantics, violating the MAIW principle that operational semantics are framework-independent.
- **External workflow engine (Temporal, Airflow):** Not appropriate for real-time warehouse decisions requiring sub-second step execution. Operational overhead exceeds value.
- **Rule engine (Drools, etc.):** SOP steps are not pure rules — they involve skill invocations, model calls, and subagent delegation. A pure rule engine cannot express the required action diversity.

---

## Implementation constraints (enforced by this ADR)

The following are hard constraints on any implementation of Option B:

1. **No implementation without architecture review.** Section 59 of the Design Document lists an implementation order (A–M). None of these steps may begin until architecture review of this ADR and the Design Document. — *Satisfied: review complete; steps A–K implemented. L and M (Proof SOPs B and C) remain outstanding.*

2. **No changes to packages, apps, src, or tests during design phase.** Only `docs/architecture/SOP_ENGINE_V2_DESIGN.md` and `docs/adr/ADR_SOP_ENGINE_V2.md` are produced by this audit. — *Design phase closed. The foundation implementation is confined to `packages/maiw-agents`, `agents/sops`, and these docs; `apps/api`, `src/`, and every other package are unmodified.*

3. **Validator authority rule is absolute** (Design Document Section 14): No validator may invoke ActionExecutor, bypass DecisionEngine or human approval, or call a WRITE/EMERGENCY_WRITE capability. This is non-negotiable.

4. **Post-write completion invariant is absolute** (Design Document Section 34): A write-related SOP step cannot complete solely on HTTP 200 or model assertion. Authoritative re-read + STATE_PREDICATE is required.

5. **Backward compatibility is required:** v1 SOPs must run through the V2 SOP Engine without any YAML modification.

6. **No standalone Blueprint extraction before readiness gate:** Option C may not begin until all Section 50 readiness criteria are met.

---

## Related documents

- `docs/architecture/SOP_ENGINE_V2_DESIGN.md` — Full 59-section design document (this ADR summarizes)
- `packages/maiw-agents/maiw_agents/contracts/sop.py` — Current SOPDefinition/SOPStep contracts
- `packages/maiw-agents/maiw_agents/contracts/runtime.py` — AgentRuntime Protocol
- `packages/maiw-agents/maiw_agents/runtime/deterministic.py` — MAIWDeterministicRuntime
- `packages/maiw-agents/maiw_agents/runtime/deep_agents_runtime.py` — DeepAgentsRuntime
- `agents/sops/operations_coordination/wave_risk_resolution.v1.yaml` — Current canonical SOP
- `docs/audits/PHASE_18H_AGENT_GOVERNANCE_BASELINE.md` — Governance baseline per agent
- `docs/audits/PHASE_19A_11_OWNERSHIP_MATRIX.md` — Phase 19A ownership matrix
