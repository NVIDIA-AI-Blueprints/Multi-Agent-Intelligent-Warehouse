# SOP Engine v2 — Architecture Design Document

**Status:** FOUNDATION IMPLEMENTED — see "Foundation implementation status" below
**Audit date:** 2026-09-26
**Foundation implemented:** 2026-09-26 (branch `feat/sop-engine-v2-foundation`)
**HEAD SHA (audit):** e33ed699470c03639899ac7539ec9690e24d30e7
**Verified source:** packages/maiw-agents/maiw_agents/ (Phase 18H / 19A codebase)
**Note:** This is a verified rerun from nvidia/main. Previous outputs generated against wrong worktree state are superseded.

---

## Foundation implementation status

The V2 foundation has been implemented within `packages/maiw-agents` per ADR Option B.
Sections below retain their original audit language; this table records what is now real.

| Section | Topic | Status |
|---------|-------|--------|
| 5 | Canonical SOP source of truth | **IMPLEMENTED** — unchanged: YAML authoring, Pydantic runtime |
| 11 | SOPStep v2 structure | **IMPLEMENTED** — `contracts/sop.py` + `contracts/sop_v2.py`; all fields Optional |
| 12 | Backward compatibility | **IMPLEMENTED** — all three v1 SOPs run unmodified (`test_v1_compatibility.py`) |
| 13 | Validator taxonomy | **PARTIAL** — SCHEMA, STATE_PREDICATE, CAPABILITY_RESULT, LEGACY_SUCCESS implemented; HUMAN, MODEL_JUDGE, COMPOSITE **DEFERRED** |
| 14 | Validator authority rule | **IMPLEMENTED** — enforced structurally, asserted by `test_security_boundary.py` |
| 15 | MODEL_JUDGE appropriateness | **DEFERRED** — not implemented; `ValidatorRegistry.get()` raises for unsupported types |
| 16 | Step execution state machine | **IMPLEMENTED** — `contracts/step_result.py::StepStatus` |
| 17 | Procedure execution state | **IMPLEMENTED** — `contracts/procedure_state.py` (in-memory; see Section 54) |
| 18 | Identity model | **IMPLEMENTED** — `procedure_execution_id` (UUID4) distinct from and linked to task/trace ids |
| 19 | Branching semantics | **PARTIAL** — `condition` and `on_failure_step_id` honoured; declarative `StepBranch` model **DEFERRED** |
| 20 | Loop semantics | **DEFERRED** — bounded only by the engine's `max_transitions` guard |
| 21 | Retry semantics | **IMPLEMENTED** — `RetryPolicy`, per-step budget, backoff, no blind write retry |
| 22 | Timeout semantics | **IMPLEMENTED** — `SOPStep.timeout_seconds`, enforced via `asyncio.wait_for` |
| 23 | Escalation semantics | **IMPLEMENTED** — `EscalationReasonCode` typed enum |
| 24 | Evidence model | **IMPLEMENTED** — `EvidenceRef`; chain-of-thought rejected at construction |
| 25 | Output schema strategy | **PARTIAL** — `expected_output` is a prompt hint; SCHEMA validates key presence, not types |
| 26 | Runtime-neutral step execution contract | **IMPLEMENTED** — `sop_engine/executor.py::SOPStepExecutor` |
| 27 | Deterministic runtime fit | **IMPLEMENTED** — `MAIWDeterministicRuntime.execute_step()` |
| 28 | Deep Agents runtime fit | **IMPLEMENTED** — step-at-a-time; whole-SOP prompt removed |
| 29 | Runtime replaceability | **IMPLEMENTED** — proven by `test_cross_runtime_equivalence.py` |
| 30 | MCP interface assessment | **DEFERRED** — no MCP surface for the SOP Engine in this phase |
| 31 | SOP Engine authority boundary | **IMPLEMENTED** — zero executable references to ActionExecutor / maiw_execution |
| 32 | Governance handoff | **IMPLEMENTED** — WAITING_FOR_GOVERNANCE pauses without validating |
| 33 | Resume-after-governance contract | **IMPLEMENTED** — `SOPEngine.resume_after_governance()` |
| 34 | Post-write completion (hard invariant) | **IMPLEMENTED** — `test_governance_resume_post_write.py` |
| 35–38 | Strategy / facility configurability | **DEFERRED** — out of scope for the foundation |
| 39 | Human-readable SOP corpus | **DEFERRED** |
| 40 | Three proof SOPs | **PARTIAL** — Proof SOP A shipped (`wave_risk_resolution.v2.yaml`); B and C **DEFERRED** |
| 41–43 | Versioning and change control | **PARTIAL** — v2 SOP carries a distinct id and version; formal change control **DEFERRED** |
| 44 | Testing strategy | **IMPLEMENTED** — 196 tests in `packages/maiw-agents/tests/`, wired into CORE CI |
| 45 | Cross-runtime equivalence | **IMPLEMENTED** — `test_cross_runtime_equivalence.py` |
| 46 | OTEL / trace model | **DEFERRED** — evidence and trace_id provenance carried; spans not instrumented |
| 47 | NeMo Relay fit | **DEFERRED** |
| 48–50 | Package extraction / Blueprint readiness | **DEFERRED** — see Section 50; criteria still unmet |
| 51 | Security | **IMPLEMENTED** — no eval, predicates registered in code, boundary tests |
| 52, 58 | Failure mode analysis | **IMPLEMENTED** — timeout, executor exception, unknown step, runaway all contained |
| 53 | Idempotency | **PARTIAL** — attempts are counted and validators are pure; executor idempotency is the runtime's responsibility |
| 54 | Persistence requirements | **DEFERRED** — `ProcedureExecutionState` is in-memory and serialisable; no backend |
| 55 | Performance assessment | **PARTIAL** — deterministic validators are sub-millisecond; step-at-a-time model latency not yet measured |
| 56 | Operator / developer UX | **DEFERRED** |

Two known deviations from the original design text:

1. **Step advancement.** `SOPStep.next_step_id` documents "if None, proceed to the next
   step in the sequence", but neither the pre-V2 deterministic runtime nor the V2 engine
   does this — `None` terminates the procedure. All three v1 SOPs declare no
   `next_step_id`, so they traverse exactly one step, before and after V2. This behaviour
   is preserved deliberately (no regression); the v2 proof SOP chains steps explicitly.
   Changing it would alter production agent traversal and is out of scope here.
2. **`EXECUTION_AMBIGUITY_UNRESOLVED`** (Section 34) is implemented as
   `EscalationReasonCode.EXECUTION_INDETERMINATE`.

---

## Document conventions

> **CURRENT IMPLEMENTATION** — describes verified code in packages/maiw-agents/ at HEAD e33ed699
> **PROPOSED V2 DESIGN** — design-only; no implementation may begin without architecture review
> **FUTURE OPTIONAL** — potential extension beyond V2 scope

All current-state assertions cite exact file paths and line numbers from packages/maiw-agents/.
Where a section is marked IMPLEMENTED above, its "PROPOSED V2 DESIGN" text describes shipped code.

---

## Section 1. Source Identity Gate — PASSED

### Branch / SHA verification

| Field | Value |
|---|---|
| Repo root | /home/nvidia/Multi-Agent-Intelligent-Warehouse |
| Worktree | .claude/worktrees/agent-a567400dd4d2c771b |
| HEAD SHA | e33ed699470c03639899ac7539ec9690e24d30e7 |
| Branch | design/sop-engine-v2 (created from worktree-agent-a567400dd4d2c771b) |
| Recent commits | e33ed69 fix(agents): LLM timeouts; b888f0b ci: fork-safe SonarQube |

### Required files verified present

```
packages/maiw-agents/maiw_agents/contracts/sop.py        ✓  (Phase 18H)
packages/maiw-agents/maiw_agents/contracts/runtime.py    ✓  (Phase 18H)
packages/maiw-agents/maiw_agents/contracts/task.py       ✓  (Phase 18H)
packages/maiw-agents/maiw_agents/contracts/agent.py      ✓  (Phase 18H)
packages/maiw-agents/maiw_agents/contracts/definitions.py ✓ (Phase 18H)
packages/maiw-agents/maiw_agents/runtime/deterministic.py ✓ (Phase 18H.8)
packages/maiw-agents/maiw_agents/runtime/deep_agents_runtime.py ✓ (Phase 19A)
packages/maiw-agents/maiw_agents/runtime/model_adapter.py ✓ (Phase 19A)
packages/maiw-agents/maiw_agents/runtime/skill_adapter.py ✓ (Phase 19A)
```

### Authority-hardening state (main branch — pre-fix noted)

- `packages/maiw-agents/pyproject.toml` CONTAINS `maiw-execution>=0.1.0` — **NOTED, not a gate failure**. Branch `fix/agent-package-authority-boundary` (SHA 1dc2b7c) exists to remove this.
- `packages/maiw-agents/maiw_agents/equipment/agent.py` line 33 imports `ActionExecutor` from `maiw_execution` — **NOTED, pre-fix state on main**.
- Gate PASSES: packages/maiw-agents/ exists and all core SOP contracts are present.

---

## Section 2. Verified Current SOP Contract Definitions

### SOPDefinition (contracts/sop.py lines 160–207)

```python
class SOPDefinition(BaseModel):
    id: str               # line 169 — stable identifier e.g. 'operations_coordination.wave_risk_resolution'
    version: str          # line 170 — semantic version e.g. '1.0'
    agent: str            # line 171 — agent_id that owns this SOP
    objective: str        # line 172 — plain-English objective
    description: str | None  # line 173

    triggers: list[str]                 # line 175
    required_context: list[str]         # line 176
    allowed_capabilities: list[str]     # lines 178–182 — skill IDs; WRITE blocked by validate_sop()
    allowed_subagents: list[str]        # lines 183–186
    steps: list[SOPStep]                # line 187
    escalation: list[EscalationRule]    # line 188
    stop_conditions: list[str]          # lines 189–197 — at least one required
    runtime_profile: Literal["strict", "adaptive"]  # lines 199–206
    #   "strict"   → MAIWDeterministicRuntime (default, production-safe)
    #   "adaptive" → DeepAgentsRuntime (LLM-adaptive, specialist delegation)
```

### SOPStep (contracts/sop.py lines 119–156)

```python
class SOPStep(BaseModel):
    id: str                          # line 127 — unique within SOP
    action: StepActionType           # line 128 — one of 30 named action literals
    description: str | None         # line 129

    delegate_to: str | None          # lines 132–135 — agent ID for delegate_to_agent action
    skill_id: str | None             # lines 136–139 — skill ID for invoke_skill action

    condition: StepCondition | None  # line 142 — execution guard (skip if False)
    next_step_id: str | None         # lines 145–151 — override linear sequence
    on_failure_step_id: str | None   # lines 152–155 — go here on failure (not yet runtime-implemented)
```

`StepActionType` (sop.py lines 89–116): Literal of 30 named action strings covering:
gather/read/evaluate/generate/compare/select/emit/delegate/invoke_skill/return/no_op patterns.

### StepCondition (contracts/sop.py lines 38–74)

```python
class StepCondition(BaseModel):
    predicate: str          # line 52 — named key evaluated against facts dict
    operator: ConditionOperator  # line 55 — eq|ne|contains|not_contains|exists|not_exists
    value: str | None       # line 56

    def evaluate(self, facts: dict[str, Any]) -> bool: ...  # lines 58–74
```

Conditions evaluate against named predicates in a runtime facts dict. No eval(), no exec().

### EscalationRule (contracts/sop.py lines 79–84)

```python
class EscalationRule(BaseModel):
    rule_id: str
    trigger: str          # human-readable description of trigger
    escalation_message: str | None
```

Currently advisory/human-readable only. Not programmatically triggered at runtime.

### validate_sop() (contracts/sop.py lines 232–317)

Eight rules enforced at load time:
1. Required fields: id, version, agent, objective
2. At least one stop_condition and at least one step
3. Step IDs must be unique within the SOP
4. No write capabilities (regex match on allowed_capabilities)
5. allowed_capabilities must not match write capability pattern `_WRITE_CAPABILITY_PATTERNS`
6. Optional: all capabilities must exist in `known_capabilities` set if provided
7. Optional: all subagents must exist in `known_agents` set if provided
8. No circular step dependencies via next_step_id graph traversal

Raises `SOPValidationError(sop_id, errors: list[str])` on failure.

### load_sop() (contracts/sop.py lines 322–346)

```python
def load_sop(path: str | Path) -> SOPDefinition:
    raw = yaml.safe_load(f)            # safe_load only — no eval/exec from YAML
    sop = SOPDefinition.model_validate(raw)
    validate_sop(sop)
    return sop
```

### AgentRuntime Protocol (contracts/runtime.py lines 87–126)

```python
@runtime_checkable
class AgentRuntime(Protocol):
    async def run_task(
        self,
        definition: AgentDefinition,
        sop: SOPDefinition,
        state: AgentTaskState,
        context: AgentExecutionContext,
    ) -> AgentTaskResult: ...
    # Must NOT: call ActionExecutor, call DecisionEngine, mutate warehouse state,
    # import LangGraph/LangChain/Deep Agents/NemoClaw
```

### AgentExecutionContext (contracts/runtime.py lines 36–59)

```python
@dataclass
class AgentExecutionContext:
    warehouse_id: str
    trace_id: str
    conversation_id: str | None
    copilot_turn_id: str | None
    context_snapshot_id: str | None
    model_gateway: Any       # MUST go through ModelGateway — not raw provider
    state_provider: Any
    skill_registry: dict[str, Any]
    bounded_context: dict[str, Any]   # pre-loaded facts injected before run_task
    started_at: datetime
    # Does NOT carry ActionExecutor or DecisionEngine (runtime.py line 44 docstring)
```

### MAIWDeterministicRuntime (runtime/deterministic.py lines 41–284)

- `run_task()` (line 73): validates capability alignment, builds step index, runs while loop
- Iteration guard (line 109): `iteration >= definition.termination_policy.max_iterations` → escalate
- Condition evaluation (lines 142–155): `step.condition.evaluate({**context.bounded_context, **assessment})`; if False → skip step and advance to `step.next_step_id`
- Step dispatch (lines 158–168): `_run_step(step.id, action, ...)` — logs step, extracts `_agent_result` from bounded_context for terminal steps
- Advancement (line 173): `current_step_id = step.next_step_id` — terminates when None
- Write guard (line 128): rejects steps with action "write"/"execute"/"mutate" at runtime
- No per-step completion validator

### DeepAgentsRuntime (runtime/deep_agents_runtime.py lines 222–560)

- Factory `get_runtime()` (lines 52–75): selects runtime from config, `MAIW_AGENT_RUNTIME` env, or `sop.runtime_profile`
- Full-SOP system prompt (lines 80–111): ALL steps placed in system prompt simultaneously
- WRITE hard-block (line 129): `_build_maiw_tools()` never exposes WRITE/EMERGENCY_WRITE capabilities
- `graph.ainvoke()` (line 313): deepagents==0.7.15; recursion_limit = max(max_iterations + 5, 10)
- Completion detection (lines 392–411): regex search for "WAITING_FOR_GOVERNANCE" or "STOP:" in last AI message
- Resume (lines 460–530): `resume_after_governance()` inspects `decision_outcome` + `execution_status` strings

---

## Section 3. Current-State Analysis Rule

All current-state assertions in this document cite exact file paths and line numbers from `packages/maiw-agents/`. No historical `src/api/*` code substitutes for current architecture analysis.

---

## Section 4. Repo-Wide SOP Inventory

| Path | Type | Runtime use | Current? | Canonical? |
|------|------|-------------|----------|------------|
| packages/maiw-agents/maiw_agents/contracts/sop.py | Python types (SOPDefinition, SOPStep, StepCondition, validate_sop, load_sop) | All runtimes | Yes | Yes |
| packages/maiw-agents/maiw_agents/contracts/runtime.py | AgentRuntime Protocol, AgentExecutionContext, check_capability_alignment | All runtimes | Yes | Yes |
| packages/maiw-agents/maiw_agents/contracts/task.py | AgentTaskState, AgentTaskStatus, StepResult, AgentObservation | All runtimes | Yes | Yes |
| packages/maiw-agents/maiw_agents/contracts/agent.py | AgentDefinition, GovernanceBoundary, TerminationPolicy | Validated at runtime | Yes | Yes |
| packages/maiw-agents/maiw_agents/contracts/definitions.py | Canonical AgentDefinition instances (OCA, Labor, Wave, Equipment, Safety) | Agent startup | Yes | Yes |
| packages/maiw-agents/maiw_agents/contracts/registry.py | CapabilityClass, SkillRegistryEntry, SKILL_REGISTRY | SOP/capability guard | Yes | Yes |
| packages/maiw-agents/maiw_agents/runtime/deterministic.py | MAIWDeterministicRuntime, handle_delegation() | runtime_profile=strict | Yes | Yes |
| packages/maiw-agents/maiw_agents/runtime/deep_agents_runtime.py | DeepAgentsRuntime, get_runtime() factory | runtime_profile=adaptive | Yes | Yes |
| agents/sops/operations_coordination/wave_risk_resolution.v1.yaml | YAML SOP (runtime_profile=adaptive, 8 steps) | OCA/DeepAgents | Yes | Yes |
| agents/sops/labor/labor_constraint_assessment.v1.yaml | YAML SOP (8 steps) | LaborAgent/Deterministic | Yes | Yes |
| agents/sops/wave/wave_risk_assessment.v1.yaml | YAML SOP (7 steps) | WaveAgent/Deterministic | Yes | Yes |
| tests/unit/test_canonical_sop_18h.py | SOP schema, loading, instantiation tests | Test only | Yes | Yes |
| tests/unit/test_sop_validation_18h.py | validate_sop() rule enforcement tests | Test only | Yes | Yes |
| tests/unit/test_deep_agents_arch_invariants_19a.py | Deep Agents governance invariant tests | Test only | Yes | Yes |
| tests/unit/test_deep_agents_real_integration_19a.py | DeepAgentsRuntime integration tests | Test only | Yes | Yes |
| docs/ux/MAIW_AGENT_SOP_UX.md | Human-readable SOP UX design | Documentation | Yes | Informative |
| docs/audits/PHASE_18H_AGENT_GOVERNANCE_BASELINE.md | Governance baseline per agent | Audit reference | Yes | Informative |

No SOP-specific API routes in apps/api. No SOP-specific UI components. SOP is surfaced through agent task trace UX, not as a standalone SOP browser.

---

## Section 5. Canonical SOP Source of Truth

**CURRENT IMPLEMENTATION:**

```
Canonical authoring representation:  YAML (agents/sops/**/*.v1.yaml)
Runtime representation:              Python Pydantic (SOPDefinition, SOPStep, StepCondition)
Human-readable representation:       YAML (also serves as human-readable spec at current scale)
```

Three YAML SOP files exist. Loaded via `load_sop()` (sop.py line 322) at agent startup into Pydantic models. Python `SOPDefinition` instances can also be constructed directly in tests. YAML is the authoritative authoring form; Pydantic validation is the authoritative runtime form.

---

## Section 6. Deterministic SOP Lifecycle (Verified Current Flow)

**CURRENT IMPLEMENTATION** — traced through `packages/maiw-agents/`:

```
SOPDefinition loaded via load_sop() from YAML
    ↓ validate_sop() — 8 rules, write-capability blocking
AgentTaskState(status=PENDING, sop_id, sop_version pinned)
    ↓ state.transition(RUNNING) — task.py line 237, validated state machine
MAIWDeterministicRuntime.run_task() — deterministic.py line 73
    ↓ _check_capability_alignment() — line 237 (write block, belt-and-suspenders)
    ↓ steps = {s.id: s for s in sop.steps}  # build step index — line 97
    ↓ while current_step_id is not None:
        iteration guard (line 109) → escalate if limit exceeded
        steps.get(current_step_id) (line 120)
        write action guard (line 128) → reject "write"/"execute"/"mutate"
        step.condition.evaluate(condition_facts) (line 143) → skip if False
        _run_step(step.id, action, ...) (line 158)
            → log step as observation
            → extract _agent_result from bounded_context for return/terminal steps
            → return (observations, candidate_actions, assessment_update)
        current_step_id = step.next_step_id (line 173)  # advance or terminate
    ↓ AgentTaskResult(COMPLETED, stop_reason="OBJECTIVE_MET") — line 176
```

**Current lifecycle gaps identified:**
- No per-step output validation before advancing (Section 9)
- `_run_step()` does not validate step action produced required output
- Condition evaluation is forward-looking (gate execution), not backward-looking (validate result)
- No retry per step; only iteration guard at task level
- No step-level timeout; only task-level max_iterations
- Branch logic: condition skips/executes, or next_step_id overrides; no branch to alternative named step on condition True
- `on_failure_step_id` field exists on SOPStep (line 152) but is not implemented in runtime today

---

## Section 7. Deep Agents SOP Lifecycle (Verified Current Flow)

**CURRENT IMPLEMENTATION** — traced through `runtime/deep_agents_runtime.py`:

```
SOPDefinition (runtime_profile="adaptive")
    ↓ get_runtime(sop=sop) → DeepAgentsRuntime() — deep_agents_runtime.py line 52
DeepAgentsRuntime.run_task() — line 254
    ↓ _check_capability_alignment() → check_capability_alignment() (runtime.py)
    ↓ MAIWModelGatewayChat(model_gateway, trace_id) — model MUST go through ModelGateway
    ↓ _build_maiw_tools() — line 114: READ/ANALYTICAL only; WRITE hard-blocked line 129
    ↓ _build_subagent_specs() — line 158: labor/wave/equipment as isolated SubAgents
    ↓ _build_sop_system_prompt() — line 80: FULL SOP (all steps) placed in system prompt
    ↓ create_deep_agent(model, tools, system_prompt, subagents, permissions=[], memory=None)
    ↓ graph.ainvoke({"messages": [HumanMessage(task_context)]}, recursion_limit=max_iter+5)
        model sees all steps simultaneously — can skip, compress, reorder (instruction-only)
        model invokes skills as LangChain StructuredTools
        model may call isolated subagents (labor/wave/equipment)
        model produces final message with RECOMMENDATION: {...} and STOP: WAITING_FOR_GOVERNANCE
    ↓ _parse_result() — line 359
        regex: "WAITING_FOR_GOVERNANCE" in last AI message → WAITING_FOR_GOVERNANCE status
        re.search(r"RECOMMENDATION:\s*(\{.*?\})") → JSON parse → recommendation dict
AgentTaskResult(WAITING_FOR_GOVERNANCE, recommendation=parsed_json)
    ↓ resume_after_governance(governance_outcome: dict) — line 460
        checks state == WAITING_FOR_GOVERNANCE
        inspects decision_outcome string ("APPROVED"/"REJECTED")
        inspects execution_status string ("EXECUTED"/"UNKNOWN")
        returns COMPLETED or ESCALATED directly (no authoritative re-read today)
```

**Key structural control observations:**
- Full SOP in system prompt: step order is instruction-only; model may compress or skip steps
- No per-step structural enforcement: governance boundary enforced via tool exclusion; step sequence by instruction only
- Completion detection is text-pattern-based (line 394): not typed or schema-validated
- Resume does not read authoritative warehouse state before declaring COMPLETED

---

## Section 8. Current SOP Contract Field Inventory

### SOPDefinition

| Field | Meaning | Required? | Enforced where? |
|-------|---------|-----------|-----------------|
| id | Stable SOP identifier | Yes | validate_sop() rule 1 |
| version | Semantic version | Yes | validate_sop() rule 1 |
| agent | Owning agent ID | Yes | validate_sop() rule 1 |
| objective | Plain-English objective | Yes | validate_sop() rule 1 |
| description | Optional narrative | No | Not enforced |
| triggers | Activation condition names | No | Advisory only |
| required_context | Context key names | No | Advisory only (not enforced at runtime) |
| allowed_capabilities | Allowed skill IDs | No | validate_sop() rules 4–6; check_capability_alignment() |
| allowed_subagents | Agent IDs for delegation | No | validate_sop() rule 7 |
| steps | Ordered SOPStep list | Yes (min 1) | validate_sop() rule 2b |
| escalation | Named EscalationRule list | No | Advisory only (not triggered programmatically) |
| stop_conditions | Terminal condition names | Yes (min 1) | validate_sop() rule 2 |
| runtime_profile | "strict" or "adaptive" | No (default: "strict") | get_runtime() factory |

### SOPStep

| Field | Meaning | Required? | Enforced where? |
|-------|---------|-----------|-----------------|
| id | Unique step identifier | Yes | validate_sop() rule 3 |
| action | Named action type | Yes | Pydantic (StepActionType literal) |
| description | Optional narrative | No | Not enforced |
| delegate_to | Agent ID for delegation steps | No | handle_delegation() routing |
| skill_id | Skill ID for invoke_skill steps | No | Not validated at runtime today |
| condition | Optional execution guard | No | deterministic.py line 142 |
| next_step_id | Override next step | No | deterministic.py line 173; circular dep in validate_sop() |
| on_failure_step_id | Override on failure | No | Defined in model; NOT implemented in runtime |

### StepCondition

| Field | Meaning | Required? | Enforced where? |
|-------|---------|-----------|-----------------|
| predicate | Named key in facts dict | Yes | StepCondition.evaluate() |
| operator | Comparison operator | Yes | StepCondition.evaluate() |
| value | Expected value | Conditional | StepCondition.evaluate() |

---

## Section 9. Completion-Criteria Gap Analysis

### Deterministic runtime

**Current: NO per-step completion validation.**

`MAIWDeterministicRuntime._run_step()` (deterministic.py lines 190–235) logs the step and extracts `_agent_result` from bounded_context. It does NOT:
- Validate that the step produced expected output before advancing
- Check that required facts are present in observations
- Run any predicate against warehouse state
- Raise on empty/None result from skill invocations

Step advancement at line 173 (`current_step_id = step.next_step_id`) is **unconditional** — it advances regardless of step outcome quality.

`step.condition.evaluate()` (line 143) gates whether a step is EXECUTED, not whether it SUCCEEDED.

**Current code path:** action runs → `_run_step()` returns observations → `current_step_id = step.next_step_id` unconditionally.

### Deep Agents runtime

**Current: NO structural step-completion validation.**

`DeepAgentsRuntime._parse_result()` (lines 359–458): completion determined entirely by text pattern matching on last AI message. "WAITING_FOR_GOVERNANCE" presence (line 394) determines final status. No schema validation, no predicate check, no authoritative state read.

Model may compress, skip, or resequence steps based on reasoning — no MAIW component validates this progression.

**Summary:** Both runtimes lack a mechanism to validate "did this step produce the required output and did the world state satisfy the completion criterion?" before advancing.

---

## Section 10. Current Step Semantics Gap Matrix

| Concept | Status | Notes |
|---------|--------|-------|
| objective | MISSING | SOPStep.description is narrative; no structured objective field |
| required_inputs | MISSING | No field; bounded_context assumed pre-loaded |
| allowed_capabilities | PARTIAL | At SOP level, not per-step |
| allowed_subagents | PARTIAL | At SOP level, not per-step |
| expected_output_schema | MISSING | No field; output type implicit in action name |
| completion_criteria | MISSING | No field; advancement unconditional |
| validator_type | MISSING | No validator model exists |
| branch_conditions | PARTIAL | StepCondition gates skip/execute; no branch to named alternative step on condition True |
| loop_policy | MISSING | No per-step retry or bounded loop; only task-level max_iterations |
| retry_policy | MISSING | No retry; failure escalates or terminates |
| timeout | MISSING | No step-level timeout; task has max_iterations |
| escalation | PARTIAL | EscalationRule at SOP level; not per-step; not programmatically triggered |
| evidence_requirements | MISSING | AgentObservation exists but no required-evidence spec per step |
| next_step | EXISTS | SOPStep.next_step_id (deterministic.py line 173) |
| terminal_step | PARTIAL | Detected by None next_step_id; no explicit terminal flag |

---

## Section 11. SOPStep v2 — Proposed Structure (Design Only)

**PROPOSED V2 DESIGN** — evolution of existing SOPStep; not a replacement. All new fields are Optional with None defaults.

```
SOPStep v2
├── id                    (exists — keep; sop.py line 127)
├── action                (exists — keep StepActionType; sop.py line 128)
├── description           (exists — keep; sop.py line 129)
│
├── objective             (NEW) str — structured statement of what step must accomplish
├── required_inputs       (NEW) list[str] — fact keys required in procedure.variables before executing
│
├── allowed_capabilities  (NEW) list[str] | None — per-step override of SOP-level list
├── allowed_subagents     (NEW) list[str] | None — per-step override
│
├── expected_output       (NEW) StepOutputSpec | None — schema reference or field list
├── completion            (NEW) StepCompletionSpec | None — validator type + criteria
│
├── branches              (NEW) list[StepBranch] | None — declarative branch targets
├── retry_policy          (NEW) StepRetryPolicy | None — max_attempts, backoff, retry_on conditions
├── timeout_seconds       (NEW) int | None — step-level wall-clock timeout
├── escalation            (NEW) str | None — EscalationRule.rule_id to trigger on failure budget exhaustion
├── evidence_requirements (NEW) list[str] — named evidence types required before marking COMPLETED
│
├── condition             (exists — keep StepCondition execution guard; sop.py line 142)
├── delegate_to           (exists — keep; sop.py line 132)
├── skill_id              (exists — keep; sop.py line 136)
├── next_step_id          (exists — keep; sop.py line 145)
└── on_failure_step_id    (exists — keep, now implemented; sop.py line 152)
```

**Backward compatibility:** v1 YAML SOPs load unchanged. New optional fields default to None. When `completion` is None, runtime uses current behavior (unconditional advancement). New semantics activate only when completion is non-None.

---

## Section 12. Backward Compatibility Strategy

**PROPOSED V2 DESIGN**

```
SOPDefinition v1 YAML (current):
  → loads via load_sop() unchanged (all new fields default to None)
  → runtime: None completion → advance without validation (current behavior preserved)
  → None evidence_requirements → no evidence check before advancing

SOPDefinition v2 YAML (new — opt-in):
  → same Pydantic model; additional fields populated
  → SOP Engine runs completion validator before advancing each step
  → evidence_requirements checked against accumulated observations

Migration path:
  1. Deploy V2 SOP Engine with all new SOPStep fields optional (no-op for existing SOPs)
  2. Existing 3 SOPs continue running with no-op validators
  3. New SOPs (SOP B, SOP C from Section 40) authored with full V2 semantics
  4. Existing SOPs upgraded incrementally per step when needed
```

Existing SOPs must run through the V2 SOP Engine without any YAML changes.

---

## Section 13. Validator Taxonomy

**PROPOSED V2 DESIGN** — runtime-neutral; validators determine step completion, NOT write authorization.

### SCHEMA validator

- **Inputs:** StepResult or bounded_context output; expected_output schema (Pydantic class path or JSON Schema ref)
- **Output:** VALID | INVALID with field-level error list
- **Deterministic:** Yes
- **ModelGateway dependency:** None
- **Evidence produced:** Schema validation result, field presence/type confirmation
- **Failure semantics:** Retry up to retry_policy.max_attempts → ESCALATED with INVALID_RESULT_BUDGET_EXHAUSTED

### STATE_PREDICATE validator

- **Inputs:** Authoritative warehouse state (via READ capability); named predicate from restricted set (no eval())
- **Output:** TRUE | FALSE with predicate identifier and fact values evaluated
- **Deterministic:** Yes
- **ModelGateway dependency:** None
- **Evidence produced:** Predicate name, fact values, timestamp, snapshot_id
- **Failure semantics:** Retry read up to budget; for post-write steps: re-read before retry decision

### CAPABILITY_RESULT validator

- **Inputs:** SkillResult from a named READ/ANALYTICAL skill; acceptance criteria (minimum fields, non-empty)
- **Output:** ACCEPTED | REJECTED with specific field failures
- **Deterministic:** Yes
- **ModelGateway dependency:** None
- **Evidence produced:** Skill ID, result content hash, accepted fields list
- **Failure semantics:** Retry skill invocation up to budget

### HUMAN validator

- **Inputs:** Step context summary; completion criteria description; operator prompt
- **Output:** APPROVED | REJECTED (from human operator)
- **Deterministic:** No (human decision)
- **ModelGateway dependency:** None
- **Evidence produced:** Operator ID, timestamp, decision, optional note
- **Failure semantics:** Procedure transitions to PAUSED; timeout → ESCALATED with HUMAN_DECISION_REQUIRED

### MODEL_JUDGE validator

- **Inputs:** Specific text/document/unstructured output; evaluation rubric
- **Output:** PASS | FAIL with rubric scores and explanation
- **Deterministic:** No (LLM)
- **ModelGateway dependency:** Yes — must route through ModelGateway, not raw provider
- **Evidence produced:** Judge model ID, rubric, scores, reasoning summary, routing trace
- **Failure semantics:** Retry with budget; escalate with REPEATED_MODEL_FAILURE

### COMPOSITE validator

- **Inputs:** Two or more sub-validators + combinator (AND | OR | NOT)
- **Output:** Combined VALID/INVALID per combinator logic
- **Deterministic:** Only if all sub-validators are deterministic
- **ModelGateway dependency:** Only if MODEL_JUDGE sub-validator included
- **Evidence produced:** Each sub-validator's evidence; combined result with combinator
- **Failure semantics:** Per combinator — AND: all must pass; OR: any must pass; NOT: must fail

---

## Section 14. Validator Authority Rule (Hard Invariant)

**HARD INVARIANT — no exceptions:**

A validator determines whether an SOP step is complete. It does NOT authorize operational writes.

Specifically, no validator may:
- Invoke `ActionExecutor` (neither directly nor via import)
- Bypass `DecisionEngine`
- Bypass human approval
- Call a WRITE capability: `warehouse.labor.assign_direct`, `warehouse.wave.reprioritize_direct`, `warehouse.equipment.assign_direct` (all `CapabilityClass.WRITE` in SKILL_REGISTRY)
- Call any `CapabilityClass.EMERGENCY_WRITE` capability
- Execute shell commands

A validator that needs to confirm a write occurred must do so by reading authoritative state via a READ capability, not by inspecting execution confirmation signals alone.

This extends the existing `check_capability_alignment()` guard (runtime.py lines 130–161) to the validator layer.

---

## Section 15. MODEL_JUDGE Appropriateness

### NOT suitable for MODEL_JUDGE

Decisions with objectively correct answers derivable from structured data:

| Decision | Correct validator | Why not MODEL_JUDGE |
|----------|------------------|---------------------|
| Labor worker count available | STATE_PREDICATE | Count is a number; deterministic |
| Equipment operational state | STATE_PREDICATE | Telemetry is structured; boolean fact |
| Inventory quantity | STATE_PREDICATE | Read from warehouse state; deterministic |
| State freshness | STATE_PREDICATE | Timestamp comparison; deterministic |
| ActionExecutor execution confirmation | STATE_PREDICATE (re-read) | MUST verify by authoritative re-read |
| KPI threshold compliance | STATE_PREDICATE | Arithmetic on facts; deterministic |
| Reconciliation result | STATE_PREDICATE | Structured pre/post state comparison |

Using MODEL_JUDGE for these introduces non-determinism where determinism is both possible and required.

### Legitimate MODEL_JUDGE use cases

- **Document interpretation:** Determining whether a written SLA document implies a specific commitment (unstructured text → semantic conclusion)
- **Unstructured quality evaluation:** Evaluating whether a generated wave plan explanation is comprehensible and complete for an operator
- **Ambiguous semantic classification:** Classifying a free-text safety incident report when the category taxonomy is ambiguous
- **Explanation completeness:** Validating whether a recommendation rationale sufficiently addresses risk, urgency, and reversibility

MODEL_JUDGE is appropriate when: (a) input is unstructured text or document, (b) evaluation criterion is genuinely semantic (not arithmetic/logical), and (c) a deterministic alternative does not exist.

---

## Section 16. Step Execution State Machine

**PROPOSED V2 DESIGN**

### Primary states

```
PENDING → READY → RUNNING → VALIDATING → COMPLETED
```

### Alternate states

```
RUNNING/VALIDATING → RETRY        (retry budget not exhausted)
RUNNING/VALIDATING → PAUSED       (HUMAN validator awaiting response)
RUNNING/VALIDATING → ESCALATED    (budget exhausted or safety rule)
RUNNING/VALIDATING → TIMED_OUT    (step wall-clock timeout exceeded)
RUNNING/VALIDATING → FAILED       (unrecoverable runtime error)
```

### State definitions

| State | Meaning |
|-------|---------|
| PENDING | Defined; pre-conditions not yet checked |
| READY | required_inputs present in procedure.variables |
| RUNNING | Step action dispatched to runtime/skill/subagent |
| VALIDATING | Action returned; completion validator running |
| COMPLETED | Validator confirmed step objective is met |
| RETRY | Validator failed; retrying within policy budget |
| PAUSED | Waiting for human input (HUMAN validator) |
| ESCALATED | Step cannot complete; procedure escalated |
| TIMED_OUT | Step timeout_seconds exceeded |
| FAILED | Unrecoverable runtime error |

### Relationship to current AgentTaskState

Current `AgentTaskStatus` (task.py lines 28–57) is an 8-state task-level machine. The proposed step-level state machine operates BELOW it — individual step lifecycle, not procedure lifecycle. Task remains RUNNING while steps cycle PENDING → COMPLETED. Task transitions to WAITING_FOR_GOVERNANCE only when the procedure emits a RecommendedAction. Do not duplicate task-level states in the step machine.

---

## Section 17. Procedure Execution State

**PROPOSED V2 DESIGN**

### ProcedureExecutionState candidate fields

```python
@dataclass
class ProcedureExecutionState:
    procedure_execution_id: str     # stable ID for this procedure run
    sop_id: str                     # pinned at start
    sop_version: str                # pinned; immutable for in-flight runs
    agent_task_id: str              # links to AgentTaskState.task_id

    current_step_id: str | None
    step_attempt: int               # attempt number for current step
    completed_steps: list[str]      # ordered, for audit
    branch_history: list[BranchDecision]
    variables: dict[str, Any]       # shared fact namespace for step inputs/outputs

    evidence_refs: list[str]        # evidence IDs accumulated during procedure
    escalation_state: str | None    # EscalationRule.rule_id if escalated
    timestamps: dict[str, datetime] # per-step start/complete timestamps
    terminal_status: str | None     # OBJECTIVE_MET | NO_SAFE_ACTION | etc.
```

### Ownership

`ProcedureExecutionState` is owned by the SOP Engine, not by any runtime. Runtimes produce `StepResult`; the SOP Engine owns procedure progression. Current `AgentTaskState` (task.py lines 199–280) carries `task_id`, `current_step_id`, `completed_steps`, `iteration`, `observations`, and `skill_results`. `ProcedureExecutionState` extends this to add step-level evidence, branch history, and per-step attempt tracking without replacing `AgentTaskState`.

---

## Section 18. Identity Model

**PROPOSED V2 DESIGN**

### Existing MAIW identifiers (verified in current code)

| ID | Location | Meaning |
|----|----------|---------|
| trace_id | AgentExecutionContext (runtime.py line 47) | Cross-service request trace |
| context_snapshot_id | AgentExecutionContext (runtime.py line 49) | Bounded warehouse state snapshot |
| task_id | AgentTaskState (task.py line 210) | Stable agent task identifier |
| delegation_id | AgentDelegationRequest | Delegation from OCA to specialist |
| conversation_id | AgentExecutionContext (runtime.py line 48) | Copilot conversation |
| copilot_turn_id | AgentExecutionContext (runtime.py line 49) | Specific copilot turn |
| recommendation_id | AgentTaskState (task.py line 231) | Emitted RecommendedAction |
| decision_outcome | apps/api copilot/models.py line 256 | DecisionEngine outcome string |

### Proposed new identifiers

| ID | Purpose | Links to |
|----|---------|---------|
| procedure_execution_id | Stable ID for one SOP procedure run | task_id |
| step_execution_id | ID for one step within a procedure | procedure_execution_id |
| step_attempt_id | ID for one retry attempt at a step | step_execution_id |
| evidence_id | ID for one piece of validator evidence | step_attempt_id |

All new IDs are additive. No existing IDs renamed or removed.

---

## Section 19. Branching Semantics

**CURRENT IMPLEMENTATION:** Partial. `StepCondition` (sop.py lines 38–74) gates execution (skip if False). `SOPStep.next_step_id` provides static sequential override. No branch to alternative named step based on runtime outcome.

**PROPOSED V2 DESIGN — Declarative Branch Model**

```python
class StepBranch(BaseModel):
    branch_id: str
    predicate: str          # named key in procedure.variables
    operator: ConditionOperator   # reuse existing enum (sop.py line 35)
    value: str | None
    target_step_id: str     # step ID to jump to if condition matches
    description: str | None
```

Branch evaluation rules:
1. Evaluated in declared order after step reaches COMPLETED
2. First matching branch wins; if no match → proceed to next_step_id
3. Predicates evaluated against `procedure_state.variables` — no eval()
4. Branch target must be a valid step ID in same SOP (validated by validate_sop())
5. Backward branches (loops) must be bounded by retry/loop policy

---

## Section 20. Loop Semantics

**PROPOSED V2 DESIGN** — every loop must be explicitly bounded.

| Loop type | Description | Required bound |
|-----------|-------------|---------------|
| retry_current_step | Retry current step on validation failure | max_attempts in StepRetryPolicy |
| repeat_until | Re-enter a named step until predicate is True | max_iterations + deadline |
| bounded_foreach | Execute a step once per item in a collection | Collection size validated before loop |
| reevaluate_after_state_change | Re-enter step after governance outcome observed | max_governance_wait rounds |

**Hard rules:**
1. Every loop has `max_attempts` (integer, ge=1)
2. Every loop has a termination condition (predicate → True)
3. On exhausting attempts: step → ESCALATED; never infinite retry
4. `bounded_foreach`: collection size validated before loop begins

Current protection: `TerminationPolicy.max_iterations` (agent.py lines 122–135) provides task-level hard upper bound. Step-level retry adds finer granularity beneath it.

---

## Section 21. Retry Semantics

**PROPOSED V2 DESIGN**

| Retry type | When | Policy |
|-----------|------|--------|
| model_retry | Model call failed (network/timeout/model error) | max_attempts=3, exponential backoff |
| read_retry | READ skill returned empty/stale result | max_attempts=2, no backoff |
| validation_retry | Validator returned INVALID/FAIL | max_attempts configurable per SOPStep.retry_policy |
| delegation_retry | Subagent returned escalated/failed | max_attempts=1 (escalate on failure) |

### Hard rule for write ambiguity

**A SOP Engine must NEVER blindly retry an ambiguous write.**

When governance outcome `execution_status == "UNKNOWN"` or `"INDETERMINATE"`:

```
INDETERMINATE execution
    ↓ authoritative re-read via READ capability (not from execution HTTP response)
    ↓ compare pre-write vs post-write state snapshot
    → state changed as expected → treat as EXECUTED → proceed to post-write validator
    → state unchanged → may retry proposal (with caution; see Section 34)
    → state partially changed → ESCALATED with EXECUTION_AMBIGUITY_UNRESOLVED
```

This extends the existing `evaluate_post_execution_state` step in `wave_risk_resolution.v1.yaml` (step `observe`) from an instruction-only step to one with a mandatory STATE_PREDICATE validator.

---

## Section 22. Timeout Semantics

**PROPOSED V2 DESIGN**

### Two distinct timeout levels

- **SOP step timeout** (`timeout_seconds` on SOPStep v2): Wall-clock time for one step. Enforced by SOP Engine. On expiry: step → TIMED_OUT → escalate.
- **RequestDeadline** (referenced in model_adapter.py line 18): Per-request deadline for individual model calls or skill invocations. Enforced by ModelGateway.

These are complementary, not overlapping:

```
SOP step timeout (procedure control layer — SOP Engine)
    └── contains N ModelGateway requests
            └── each with RequestDeadline (request layer — ModelGateway)
```

**Do not duplicate deadline infrastructure.** SOP Engine sets step-level deadline; ModelGateway continues to own request-layer deadlines.

---

## Section 23. Escalation Semantics

**PROPOSED V2 DESIGN** — structured reason codes, not free-form model prose.

| Reason Code | Trigger |
|-------------|---------|
| INVALID_RESULT_BUDGET_EXHAUSTED | Validator returned INVALID/FAIL and retry budget exhausted |
| MISSING_REQUIRED_DATA | required_inputs not present in procedure.variables |
| UNSUPPORTED_STRATEGY | Requested strategy not supported by facility configuration |
| STATE_INCONSISTENCY | Pre-write/post-write state comparison yields unexpected diff |
| UNSAFE_CONDITION | STATE_PREDICATE detected safety policy violation |
| REPEATED_MODEL_FAILURE | MODEL_JUDGE or model call failed repeatedly |
| HUMAN_DECISION_REQUIRED | HUMAN validator timed out awaiting operator response |
| EXECUTION_AMBIGUITY_UNRESOLVED | Write execution_status INDETERMINATE; re-read did not resolve |
| POLICY_CONFLICT | All candidate actions blocked by governance policy |

Each escalation carries: `reason_code` (typed enum), `step_id`, `attempt_count`, `evidence_refs`, human-readable message. Not a free-text string from model output.

This converts existing `EscalationRule` (sop.py lines 79–84) from a YAML advisory narrative into a structured runtime signal.

---

## Section 24. Evidence Model

**PROPOSED V2 DESIGN**

Evidence is structured facts, not chain-of-thought.

| Step domain | Required evidence type | Produced by |
|------------|----------------------|-------------|
| labor assessment | labor_snapshot (worker states, task counts) | CAPABILITY_RESULT from warehouse.labor.capacity |
| wave assessment | wave_assessment (at_risk_count, time_to_cutoff) | CAPABILITY_RESULT from warehouse.wave.status |
| equipment assessment | equipment_status (available/offline counts) | CAPABILITY_RESULT from warehouse.equipment.status |
| inventory check | inventory_snapshot (quantity, location) | CAPABILITY_RESULT from warehouse.inventory.lookup |
| post-write observation | state_comparison (pre/post snapshot diff) | STATE_PREDICATE validator |
| document interpretation | document_citation (doc ID, extracted claims) | MODEL_JUDGE |
| step validation | validator_result (type, pass/fail, criteria) | Any validator |

**No chain-of-thought as evidence.** Model reasoning prose is not evidence. Only structured facts from READ/ANALYTICAL skills or validator results constitute step evidence.

Existing `AgentObservation` (task.py lines 119–140) provides the structural basis: `observation_id`, `observation_type`, `source`, `entity_ids`, `facts`, `timestamp`. Evidence model extends by linking to `step_execution_id` and validator runs.

---

## Section 25. Output Schema Strategy

**CURRENT IMPLEMENTATION:** Existing warehouse domain contracts in maiw-agents:
- `LaborAssessment`, `CandidateLaborAction` (labor domain)
- `WaveAssessment`, `CandidateWaveAction` (wave domain)
- `AgentObservation`, `StepResult`, `SkillResultRef` (task.py)
- `AgentTaskResult` (runtime.py)

**PROPOSED V2 DESIGN:** Reuse existing contracts.

1. `StepResult` (task.py lines 179–194) is already the structured step output container. V2 adds completion validation on top of existing structure.
2. `AgentObservation.facts` dict is the extensible evidence store. V2 formalizes required fact keys per step type.
3. `SkillResultRef` (task.py lines 145–153) links step results to skill outputs with outcome/summary/trace_id.

For `expected_output` in SOPStep v2: reference existing Pydantic model class paths (e.g., `maiw_agents.labor.agent.LaborAssessment`) rather than inline JSON Schema. Pydantic is the existing runtime standard.

---

## Section 26. Runtime-Neutral Step Execution Contract

**PROPOSED V2 DESIGN**

```python
class SOPStepExecutor(Protocol):
    async def execute_step(
        self,
        sop_step: SOPStep,
        procedure_state: ProcedureExecutionState,
        execution_context: AgentExecutionContext,
    ) -> StepResult: ...
```

**Ownership:**
- **SOP Engine** owns: procedure_state, step lifecycle transitions, validator invocation, branch evaluation, retry decisions, escalation routing
- **Runtime** owns: how to execute a step (model call, skill dispatch, subagent delegation)
- **SOP Engine does NOT own:** which model to call, tool definitions, LLM chat loop mechanics

`SOPStepExecutor` sits beneath `AgentRuntime`. `AgentRuntime.run_task()` remains the top-level entry point; `SOPStepExecutor.execute_step()` is the per-step seam between SOP Engine and runtime.

---

## Section 27. Deterministic Runtime Fit

**PROPOSED V2 DESIGN** — future flow with SOP Engine:

```
SOP Engine: get_current_step() → SOPStep
    → check required_inputs vs procedure_state.variables
    → dispatch to MAIWDeterministicRuntime.execute_step() via SOPStepExecutor
        → current _run_step() logic (line 190)
        → returns StepResult
    ← SOP Engine receives StepResult
    → invoke validator (from SOPStep.completion)
        → SCHEMA / STATE_PREDICATE / CAPABILITY_RESULT
    → if VALID: record_step_completed() → advance or branch
    → if INVALID: retry_policy check → RETRY or ESCALATED
```

**Changes required to deterministic.py:**
1. Extract `_run_step()` as `SOPStepExecutor.execute_step()` (new protocol implementation)
2. Add validator invocation between `_run_step()` return and step advancement
3. Step advancement conditional on validator result (not unconditional)
4. Add RETRY path before escalation
5. Retain iteration guard (line 109) as task-level backstop

Current write guards (lines 128–134, 237–261) remain unchanged.

---

## Section 28. Deep Agents Runtime Fit

**PROPOSED V2 DESIGN** — step-at-a-time exposure:

```
SOP Engine: get_current_step() → current SOPStep ONLY
    → build step-scoped system prompt from AgentDefinition + current SOPStep
        (not full SOP — replaces _build_sop_system_prompt() lines 80–111)
    → expose only current step's allowed_capabilities as tools
    → expose only current step's allowed_subagents
    → DeepAgentsRuntime.execute_step(current_step, procedure_state, context)
        → model reasons about this step only (focused context)
        → model produces typed StepResult (not free-text with regex parsing)
    ← SOP Engine receives StepResult
    → validator runs (same path as deterministic)
    → SOP Engine decides advance/retry/escalate (not model)
```

**Comparison with current full-SOP approach:**

| Aspect | Current (full SOP in prompt) | Proposed (step-at-a-time) |
|--------|------------------------------|--------------------------|
| Model context | All steps visible | Only current step visible |
| Step progression | Model-determined; may skip/reorder | SOP Engine-determined |
| Structural completion | Text pattern (regex) | Typed StepResult + validator |
| Runtime replaceability | Steps tightly coupled to prompt | Steps decouple from runtime |
| Traceability | Per-task trace | Per-step trace |
| Governance guarantee | Instruction-only | Structural (no WRITE tools) + validator |

---

## Section 29. Runtime Replaceability

**PROPOSED V2 DESIGN**

With `SOPStepExecutor.execute_step(sop_step, procedure_state, context) → StepResult` as the seam, the same SOP Engine supports multiple runtimes without changing SOP semantics, validators, governance, or state model.

Invariants that must hold across all runtimes:
1. Same SOPDefinition and SOPStep contracts
2. Same procedure lifecycle (ProcedureExecutionState)
3. Same validator taxonomy (runtime-neutral)
4. Same governance handoff (RecommendedAction → WAITING_FOR_GOVERNANCE)
5. Same authority boundary (no WRITE, no ActionExecutor)

Current `MAIWDeterministicRuntime`, `DeepAgentsRuntime`, and future runtimes (Codex-based, Claude-style agentic loop, NemoClaw) are pluggable when they implement `execute_step()`.

---

## Section 30. MCP Interface Assessment

**PROPOSED V2 DESIGN**

Candidate MCP operations for a SOP Engine service:

| Operation | Necessary? | Notes |
|-----------|-----------|-------|
| start_procedure | Yes | Entry point → procedure_execution_id |
| get_current_step | Yes | Query active step |
| submit_step_result | Yes | Runtime posts StepResult to SOP Engine |
| get_procedure_state | Yes | Observe ProcedureExecutionState |
| pause | Yes | Operator or HUMAN validator pause |
| resume | Yes | After human input or governance return |
| escalate | Yes | Operator-initiated or automatic |
| advance | Avoid | SOP Engine decides advancement; MCP should not |
| validate_step | Avoid | Validation is internal to SOP Engine |

**Key design rule:** MCP does NOT own workflow semantics. MCP is a transport boundary. The SOP Engine retains all advancement, branching, retry, and escalation logic. MCP callers observe state and submit results; they do not dictate next step.

---

## Section 31. SOP Engine Authority Boundary

**HARD BOUNDARY:**

```
SOP Engine MAY own:
  ✓ ProcedureExecutionState (step lifecycle, branch history, evidence refs)
  ✓ StepCompletionValidators (all validator types)
  ✓ Branch evaluation (declarative predicates against procedure.variables)
  ✓ Loop bounds enforcement
  ✓ Escalation routing (structured reason codes)
  ✓ Audit trail (step start/complete/escalate events with evidence refs)

SOP Engine MUST NOT own:
  ✗ ActionExecutor
  ✗ Warehouse credentials or MCP write tools
  ✗ Final decision authorization (DecisionEngine's role)
  ✗ Execution reliability authority (ActionExecutor/reliability layer's role)
  ✗ Model routing policy (ModelGateway's role)
  ✗ Human approval workflow (governance layer's role)
```

---

## Section 32. Governance Handoff

**PROPOSED V2 DESIGN**

```
SOP step (action: emit_recommended_action)
    ↓ SOP Engine: step → RUNNING
    ↓ runtime: produce RecommendedAction
        (semantic intent only; no MCP parameters)
    ↓ SOP Engine: step → VALIDATING → COMPLETED
        (RecommendedAction structure validated via SCHEMA validator)
    ↓ task: AgentTaskStatus → WAITING_FOR_GOVERNANCE

──────────────── MAIW AUTHORITY BOUNDARY ────────────────

    GovernedActionOrchestrator (apps/api/maiw_api/copilot/)
    ↓ ActionProposal (built by proposal skill)
    ↓ DecisionEngine evaluates
    ↓ Human Approval (if REQUIRES_HUMAN_APPROVAL)
    ↓ ActionExecutor → MCP WRITE
    ↓ ReliabilityLayer confirms execution
    ↓ GovernanceOutcome {decision_outcome, execution_status, mutation_state}

──────────────── RESUME BOUNDARY ────────────────

    SOP Engine.resume_after_governance(GovernanceOutcome)
    ↓ task: WAITING_FOR_GOVERNANCE → OBSERVING_OUTCOME
    ↓ SOP step (action: evaluate_post_execution_state)
        ↓ READ capability → fresh warehouse state
        ↓ STATE_PREDICATE validator: did state change as expected?
    ↓ if True → step COMPLETED → task COMPLETED
    ↓ if False → EXECUTION_AMBIGUITY_UNRESOLVED → escalate
```

The `observe` step in `wave_risk_resolution.v1.yaml` (step 8, action: evaluate_post_execution_state) embodies this pattern today but lacks the STATE_PREDICATE validator. V2 adds the validator as its completion criterion.

---

## Section 33. Resume-After-Governance Contract

**CURRENT IMPLEMENTATION:**

`DeepAgentsRuntime.resume_after_governance()` (lines 460–530) accepts `governance_outcome: dict[str, Any]` and inspects `decision_outcome` and `execution_status` strings. Returns COMPLETED or ESCALATED directly without reading authoritative warehouse state.

**PROPOSED V2 DESIGN:**

`GovernanceOutcome` (apps/api/maiw_api/copilot/models.py line 256) already carries:
- `decision_outcome: str` — "APPROVED" | "REJECTED" | "REQUIRES_HUMAN_APPROVAL"
- `execution_status: str | None` — "EXECUTED" | "UNKNOWN" | "FAILED"
- `mutation_state: MutationState` — typed enum

**Extension (not replacement):** add `reliability_confirmed: bool` — True only if reliability layer confirmed the write. SOP Engine's resume_after_governance() should:
1. Check decision_outcome/execution_status (current behavior — correct)
2. If EXECUTED: proceed to post-write observation step (STATE_PREDICATE validator)
3. If UNKNOWN: proceed to reconciliation (authoritative re-read)
4. If REJECTED: escalate with structured reason

---

## Section 34. Post-Write Completion (Hard Invariant)

**HARD INVARIANT:**

A write-related SOP step cannot complete solely because HTTP returned 200 or a model judged the response valid.

**Required completion path for write-related steps:**

```
ActionExecutor → HTTP response (202 Accepted)
    ↓ (this alone is NOT completion evidence)
ReliabilityLayer → confirms execution (if available)
    ↓
SOP Engine: evaluate_post_execution_state step
    ↓ warehouse.labor.capacity READ (or domain-appropriate READ capability)
    ↓ STATE_PREDICATE: "assigned_worker_count increased by expected_delta" → True | False
    → if True: step COMPLETED (evidence: state_comparison observation)
    → if False: EXECUTION_AMBIGUITY_UNRESOLVED → escalate
```

---

## Section 35. Strategy Configurability Audit

**CURRENT IMPLEMENTATION:**

Searching `packages/maiw-agents/` finds no occurrences of: batch_picking, zone_picking, discrete_picking, cluster_picking, wave_picking, hybrid_picking, PickingStrategy, replenishment_strategy.

Hardcoded patterns found:
- Specialist delegation in `handle_delegation()` (deterministic.py lines 287–364): routing hardcoded to `target == "labor"` or `target == "wave"` — implementation hardcode
- `StepActionType` literal (sop.py lines 89–116): contains domain-specific names (e.g., `read_wave_status`, `evaluate_assignment_imbalance`) — domain-appropriate names, not arbitrary hardcodes
- Specialist methods (`assess_labor_constraint()` labor/agent.py line 189; `assess_wave_risk()` wave/agent.py line 199) — domain method names

**Assessment:** Current SOP/agent model does NOT support configurable picking strategies. Wave reprioritization and labor reallocation strategies are embedded in specialist agent logic, not parameterized by facility configuration.

---

## Section 36. Hardcoded Action Audit

| Hardcoded element | Location | Classification |
|-------------------|----------|---------------|
| `assess_labor_constraint` method | labor/agent.py line 189; deterministic.py line 319 | Domain method — specialist agent API |
| `assess_wave_risk` method | wave/agent.py line 199; deterministic.py line 328 | Domain method — specialist agent API |
| `target == "labor"` routing | deterministic.py line 318 | Implementation hardcode |
| `target == "wave"` routing | deterministic.py line 327 | Implementation hardcode |
| `_agent_result` context key | deterministic.py line 224 | Convention — bounded_context key name |
| StepActionType literal names | sop.py lines 89–116 | SOP step names — domain-meaningful |
| labor/wave/equipment SubAgent names | deep_agents_runtime.py lines 167–218 | Domain strategy hardcode in runtime |

---

## Section 37. Picking Strategy Model (Design Only)

**FUTURE OPTIONAL — beyond V2 scope**

```python
class PickingStrategy(BaseModel):
    strategy_type: Literal["discrete", "batch", "zone", "cluster", "wave", "hybrid"]
    parameters: dict[str, Any]        # type-specific params (batch_size, zone_ids, etc.)
    constraints: list[str]            # named constraint IDs
    facility_applicability: list[str] # facility or zone IDs
    optimization_objective: Literal["throughput", "labor_efficiency", "cutoff_adherence", "balanced"]
```

Belongs in facility configuration, not in SOPs. SOPs reference strategy by ID.

---

## Section 38. Facility Configuration Boundary

**PROPOSED V2 DESIGN**

| Concern | Current location | Proposed home |
|---------|-----------------|---------------|
| Zone topology | Implicit in worker/task data | FacilityConfiguration.zone_topology |
| Wave cadence | Not modeled | FacilityConfiguration.wave_cadence |
| Labor rules (shift, skill, zone compatibility) | Labor agent domain logic | FacilityConfiguration.labor_policy |
| Equipment profiles | Not modeled | FacilityConfiguration.equipment_profile |
| Carrier cutoffs | Task deadline fields | FacilityConfiguration.carrier_cutoffs |
| Replenishment logic | Not modeled | FacilityConfiguration.replenishment_policy |
| SLAs | Not modeled | FacilityConfiguration.sla_policy |
| Automation profile | Not modeled | FacilityConfiguration.automation_profile |

SOPs should reference policy IDs; facility configuration provides values. Same SOP can run across facilities with different configurations.

---

## Section 39. Human-Readable SOP Corpus Design

**PROPOSED V2 DESIGN** — structure for Word/Markdown SOP specifications:

```
SOP Document
├── Header: ID, Version, Status, Owner, Review Date, Related SOP IDs
├── 1. Purpose and Business Context
├── 2. Trigger Conditions
├── 3. Prerequisites (data, context, system state)
├── 4. Roles and Responsibilities (SME / ops supervisor / AI system / governance approver)
├── 5. Traditional (Non-AI) Process
├── 6. AI-Assisted Process (what AI recommends vs what humans decide)
├── 7. Procedure Steps (numbered, named, with responsible party and output)
├── 8. Operational Variations (facility type, shift context adaptations)
├── 9. Exception Paths (AI recommendation unavailable, rejected, or ambiguous)
├── 10. Safety and Governance (what MUST have human approval; what AI cannot authorize)
├── 11. Completion Criteria (metrics confirming resolution)
├── 12. Examples (1-2 worked examples with realistic data)
└── 13. Facility-Specific Notes
```

---

## Section 40. Three Proof SOPs

**PROPOSED V2 DESIGN** — required before Blueprint readiness.

### SOP A: Wave Risk Resolution v2 (extends existing v1)

**Already exists as:** `agents/sops/operations_coordination/wave_risk_resolution.v1.yaml`

**V2 additions:**
- `completion` validators on `gather_specialist_evidence` (CAPABILITY_RESULT from labor/wave assessments)
- `branches` on `diagnose` (labor constraint → labor branch; wave constraint → wave branch; equipment constraint → equipment branch)
- STATE_PREDICATE validator on `observe` step (post-write authoritative re-read)

**Tests:** Branch logic, specialist delegation, WAITING_FOR_GOVERNANCE handoff, post-write STATE_PREDICATE validation, retry on validator failure.

### SOP B: Equipment Failure and Recovery (new)

**Tests:** Authoritative state reading (equipment telemetry via STATE_PREDICATE), safety escalation (UNSAFE_CONDITION when equipment is critical path), governance handoff for equipment assignment, post-write STATE_PREDICATE, HUMAN validator (safety-critical decision).

**Why needed:** Exercises write-related completion invariant (Section 34), STATE_PREDICATE on real telemetry data, HUMAN validator for safety decisions. Equipment domain has no V1 SOP today.

### SOP C: Picking and Inventory Exception Resolution (new)

**Tests:** Facility strategy variation (discrete vs zone picking via FacilityConfiguration), bounded retry loop (re-read inventory until count fresh), SCHEMA validator on inventory data, structured escalation (UNSUPPORTED_STRATEGY when no feasible picking strategy).

**Why needed:** Exercises bounded loops, SCHEMA validator, facility strategy configurability, escalation reason codes. Covers inventory domain not covered by A or B.

**Together these three cover:** all validator types except MODEL_JUDGE (A+B: STATE_PREDICATE, CAPABILITY_RESULT; B: HUMAN; C: SCHEMA), all branch types, all loop types, all major escalation codes, both runtimes (A: adaptive, B+C: strict), governance handoff (A, B), and two domains not yet in V1 (equipment, inventory).

---

## Section 41. Human vs Executable SOP Relationship

**PROPOSED V2 DESIGN**

| Representation | Format | Audience | Owner |
|---------------|--------|----------|-------|
| Human SOP | Word/Markdown | Warehouse SME, operations owner, auditor | Operations team |
| Executable SOP | YAML + V2 fields | SOP Engine, agents, runtime | Engineering + operations |

Synchronization rules:
1. Same SOP ID in both representations
2. Same version string; both updated together on semantic change
3. Same objective statement (human Section 1 = SOPDefinition.objective)
4. Every executable step corresponds to a step in the human document
5. Human Section 10 (Safety/Governance) mirrored in SOPDefinition.escalation and governance boundary
6. Linked by SOP ID in both documents' metadata

---

## Section 42. Versioning Model

**PROPOSED V2 DESIGN**

```
Status: draft → approved → active → retired

Immutability:
- "approved" and "active" SOPs: immutable without version increment
- "draft": mutable
- "retired": read-only archive
- In-flight procedure executions: pinned to sop_version at start

Version format: Semantic versioning
- Patch: clarifications, no semantic change
- Minor: add optional steps, escalation rules
- Major: step sequence change, objective change, completion criteria change
```

---

## Section 43. Change-Control Model

**PROPOSED V2 DESIGN**

| Role | Responsibility |
|------|---------------|
| Warehouse SME | Drafts procedure steps; owns human SOP document |
| Operations owner | Approves business logic, objective, completion criteria |
| Engineering | Translates to executable YAML; validates against SOP schema |
| Safety/compliance | Reviews escalation rules and governance considerations |
| Release approver | Final sign-off; promotes draft → approved → active |

Procedure approval (human content sign-off) is separate from runtime deployment (YAML to SOP Engine).

---

## Section 44. Testing Strategy

**PROPOSED V2 DESIGN**

| Layer | Test type | What it tests |
|-------|-----------|---------------|
| Unit | Schema | SOPStep v2 Pydantic validation; optional fields; v1 loads unchanged |
| Unit | Transitions | Step state machine all paths (PENDING→COMPLETED, RETRY, ESCALATED, TIMED_OUT) |
| Unit | Validators | Each type (SCHEMA, STATE_PREDICATE, CAPABILITY_RESULT) pass/fail inputs |
| Unit | Branch logic | Declarative branch: first-match, no-match, backward branch detection |
| Unit | Retry bounds | max_attempts enforced; after exhaustion → ESCALATED |
| Contract | Runtime interface | execute_step(): any runtime produces valid StepResult |
| Contract | MCP interface | start_procedure/submit_step_result/get_procedure_state typed responses |
| Scenario | Full SOP A run | Wave risk resolution end-to-end with validators |
| Scenario | Full SOP B run | Equipment failure with HUMAN validator and post-write STATE_PREDICATE |
| Scenario | Full SOP C run | Inventory exception with SCHEMA validator and bounded loop |
| Governance | No-write-bypass | No validator invokes ActionExecutor, WRITE skill, or DecisionEngine |
| Reliability | Post-write | Write step not COMPLETED until STATE_PREDICATE passes on authoritative re-read |
| Cross-runtime | Equivalence | Deterministic and Deep Agents produce equivalent RecommendedAction |

---

## Section 45. Cross-Runtime Equivalence

**PROPOSED V2 DESIGN**

Equivalence definition (structurally equivalent, not identical):

1. Required steps satisfied: all mandatory steps reached COMPLETED
2. Validators passed: all completion validators returned VALID
3. Same authority boundary: neither runtime invoked ActionExecutor, WRITE capability, or DecisionEngine
4. Same allowed capabilities: tools available matched allowed_capabilities exactly
5. Equivalent final outcome: RecommendedAction in same domain, same capability class, compatible priority

Not required: identical number of model calls, same intermediate reasoning, identical JSON field values, same retry count.

---

## Section 46. OTEL / Trace Model

**CURRENT IMPLEMENTATION:**

`trace_id` propagated through `AgentExecutionContext` (runtime.py line 47) and passed to `MAIWModelGatewayChat` (model_adapter.py line 89). `AgentObservation` carries `trace_id | None` (task.py line 139). No OpenTelemetry spans currently instrumented.

**PROPOSED V2 DESIGN — Span hierarchy (design only, no implementation):**

```
procedure.execution (root span)
    attributes: procedure_execution_id, sop_id, sop_version, agent_id, trace_id
    └── sop.step (span per step)
            attributes: step_id, step_action, attempt_number
            ├── skill.call (READ/ANALYTICAL capability invocation)
            ├── runtime.model_call (Deep Agents model invocation)
            ├── delegation.request (subagent delegation)
            ├── validator.run (validator type, pass/fail, evidence_id)
            └── sop.governance_handoff (WAITING_FOR_GOVERNANCE)
                    └── governance.outcome (resume after decision)
                    └── execution.confirmed (post-write STATE_PREDICATE)
```

Existing IDs that map to spans: `trace_id` (root), `task_id` (procedure.execution), `delegation_id` (delegation.request), `context_snapshot_id` (state reference attribute). Missing: `procedure_execution_id`, `step_execution_id`, `step_attempt_id` (Section 18).

---

## Section 47. NeMo Relay Fit

**FUTURE OPTIONAL — not required for V2**

NeMo Relay assessed as future observability/export layer only.

Natural mapping from current MAIW IDs: `trace_id` → Relay root span; `task_id` → procedure execution span; `AgentObservation` list → Relay event stream.

Missing for clean Relay integration: `step_execution_id` for per-step spans; `evidence_id` for structured evidence attachment (both from Section 18).

Likely seam: SOP Engine emits OTEL spans via standard SDK; Relay consumes standard OTEL. No MAIW-specific Relay SDK required. Relay is NOT required for V2.

---

## Section 48. Package Extraction Analysis

**PROPOSED V2 DESIGN**

**Could move to `packages/maiw-sop` (future):**
- SOP contracts (SOPDefinition, SOPStep, StepCondition, EscalationRule, validate_sop, load_sop)
- ProcedureExecutionState
- Validator taxonomy (all validator types)
- Step state machine
- Branch evaluation engine
- SOPStepExecutor protocol

**Must remain elsewhere:**
- Warehouse domain contracts (LaborAssessment, WaveAssessment) — stay in maiw-agents
- AgentDefinition, AgentRuntime, AgentExecutionContext — stay in maiw-agents
- GovernanceOutcome, DecisionEngine, ActionExecutor — stay in apps/api
- ModelGateway policy — stays in model-gateway package
- WRITE capabilities and MCP write tools — never in SOP package

**Decision:** Premature to extract now. 3 SOPs, 2 runtimes, unresolved persistence semantics. Extract when: 5+ SOPs, SOP Engine logic clearly separable, third runtime in scope. For V2: refactor within `packages/maiw-agents` is sufficient.

---

## Section 49. Domain-Neutrality Test

| Abstraction | Domain-neutral? | Notes |
|-------------|----------------|-------|
| SOPDefinition (id, version, agent, objective, steps) | Yes | Could describe retail/manufacturing SOP |
| SOPStep v2 (id, action, completion, branches, retry, timeout) | Yes | Generic procedure step |
| StepCondition (predicate, operator, value) | Yes | Generic conditional |
| ProcedureExecutionState | Yes | Generic procedure state |
| SCHEMA validator | Yes | JSON Schema is domain-neutral |
| STATE_PREDICATE validator | Yes | Predicate logic is generic; domain facts injected |
| CAPABILITY_RESULT validator | Yes | Skill result acceptance is domain-neutral |
| HUMAN validator | Yes | Generic human approval |
| MODEL_JUDGE validator | Yes | Generic semantic judge |
| COMPOSITE validator | Yes | Generic combinator |
| StepBranch | Yes | Generic branching |
| Escalation reason codes | PARTIAL | UNSAFE_CONDITION implies industrial context |
| Warehouse domain evidence types | No | Stay in MAIW warehouse domain |
| PickingStrategy | No | Warehouse-specific; stays in MAIW domain |
| FacilityConfiguration | No | Warehouse-specific; stays in MAIW domain |

SOP Engine core is domain-neutral. Warehouse semantics stay in the domain layer.

---

## Section 50. Standalone Blueprint Readiness

| Criterion | Met? | Evidence |
|-----------|------|---------|
| 3+ materially different warehouse SOPs supported | PARTIAL | 3 SOPs exist; 2 domains covered (labor+wave); equipment and inventory SOPs not yet defined |
| 2+ runtimes supported | Yes | MAIWDeterministicRuntime + DeepAgentsRuntime |
| Core engine has no warehouse-specific imports | NOT YET | SOP engine co-located with warehouse domain code |
| Governance remains external | Yes | RecommendedAction → apps/api; not inside maiw-agents |
| Protocol interface stable | PARTIAL | AgentRuntime Protocol exists; SOPStepExecutor not yet defined |
| Persistence semantics defined | Not yet | ProcedureExecutionState is proposed, not implemented |
| Tracing defined | Not yet | Span hierarchy proposed, not instrumented |
| Failure semantics tested | PARTIAL | Basic escalation tested; no retry/validator tests |
| Cross-runtime equivalence demonstrated | Not yet | No equivalence test exists |

**Conclusion: NOT ready for standalone Blueprint extraction.** Option B (internal SOP Engine refactor) must complete first.

---

## Section 51. Security

**Hard rules:**
1. No warehouse credentials, API keys, or MCP secrets in SOPDefinition, SOPStep, or ProcedureExecutionState
2. SOP YAML must use `yaml.safe_load` only — already enforced by load_sop() line 339
3. No eval(), exec(), or dynamic import from SOP YAML — already enforced by design
4. WRITE tools must never appear in any SOP Engine component — already blocked by validate_sop() and check_capability_alignment()
5. ActionExecutor must never be called by any SOP Engine component
6. Shell command execution not permitted from any validator
7. MODEL_JUDGE must route through ModelGateway — never raw provider
8. SOP YAML files reviewed as code in version control — they define agent authority scope

---

## Section 52. Failure Mode Analysis

| Failure Mode | Detection | Recovery |
|-------------|-----------|---------|
| Crash mid-step | StepResult.status == "error" | Retry if retry_policy allows; else FAILED |
| Duplicate step result | step_execution_id already COMPLETED | Idempotent: return existing result |
| Stale context snapshot | STATE_PREDICATE references old snapshot_id | Re-read required; stale state is validation failure |
| Model unavailable | Model call raises exception | model_retry up to budget → REPEATED_MODEL_FAILURE |
| Validator fail after retries | INVALID after max_attempts | ESCALATED with INVALID_RESULT_BUDGET_EXHAUSTED |
| Procedure restart | New procedure_execution_id | Previous state preserved; new execution is independent |
| SOP version change mid-run | pinned sop_version differs from current active | Run continues with pinned version |
| INDETERMINATE governance outcome | execution_status == "UNKNOWN" | Authoritative re-read; if unresolved → EXECUTION_AMBIGUITY_UNRESOLVED |
| Human validator timeout | PAUSED → timeout exceeded | TIMED_OUT → ESCALATED with HUMAN_DECISION_REQUIRED |
| Subagent escalated | AgentDelegationResult.status == "escalated" | Propagate escalation to parent procedure |

---

## Section 53. Idempotency

**PROPOSED V2 DESIGN**

- `procedure_execution_id`: stable for one SOP run lifetime. Re-submitting start_procedure with same inputs returns same ID.
- `step_execution_id`: stable for one step. Re-executing a completed step returns existing result (no double-advance).
- `step_attempt_id`: unique per attempt. Retries produce new attempt IDs.

SOP Engine transitions are guarded: COMPLETED → COMPLETED is a no-op; duplicate results are rejected idempotently.

---

## Section 54. Persistence Requirements

| State type | Persistence | Owner |
|-----------|-------------|-------|
| ProcedureExecutionState | Durable (survives process restart) | SOP Engine / apps/api |
| StepResult per step | Durable (evidence for audit) | SOP Engine |
| Branch history | Durable (audit trail) | SOP Engine |
| Evidence references | Durable (links to evidence IDs) | SOP Engine |
| Governance correlation IDs | Durable (links procedure to governance records) | SOP Engine |
| AgentObservation | Durable (already in AgentTaskState) | Existing |

Current `AgentTaskState` (task.py) lives in memory during a Copilot session. V2 requires SOP Engine to persist `ProcedureExecutionState` across restarts for long-running procedures spanning governance wait periods.

---

## Section 55. Performance Assessment

**PROPOSED V2 DESIGN**

Current full-SOP-in-prompt (Deep Agents): 1 `graph.ainvoke()` call per task.

Step-at-a-time V2 (Deep Agents): N model calls (one per step) + N validator calls. For 7-step SOP: 7 model calls + 7 skill calls.

**Mitigation strategies:**
- Parallelize independent steps (no data dependency on prior step output)
- Cache state reads within procedure (bounded_context reuse across steps)
- Use STATE_PREDICATE/CAPABILITY_RESULT over MODEL_JUDGE wherever possible
- Step timeout bounds individual step overhead

For deterministic runtime: step-at-a-time adds only validator overhead (microseconds for SCHEMA/STATE_PREDICATE). No significant latency regression.

---

## Section 56. Operator and Developer UX Concepts

**FUTURE OPTIONAL**

### Operator UX (conceptual)
- Procedure status view: current step, step status, last evidence, next expected action
- Escalation inbox: structured reason codes, step context, evidence refs, resolution options
- Governance queue: actions awaiting human approval, linked to procedure execution

### Developer UX (conceptual)
- SOP authoring validator: run validate_sop() locally before commit
- Step coverage report: which steps have completion validators vs instruction-only
- Cross-runtime equivalence runner: run SOP A against both runtimes, compare outcomes
- Evidence trace: per-step evidence, validator results, branch decisions

---

## Section 57. ADR Summary

See `docs/adr/ADR_SOP_ENGINE_V2.md` for full decision record. Summary:

- **Option A** (keep SOP lifecycle in each runtime): Rejected. No cross-runtime consistency, no completion validation, no shared escalation.
- **Option B** (internal reusable SOP Engine in packages/maiw-agents): **Recommended.** Extracts procedure lifecycle from runtimes; validates completion; centralizes escalation. Runtimes become step executors.
- **Option C** (standalone Blueprint package immediately): Deferred. Premature given Section 50 findings.

---

## Section 58. Additional Failure Modes

- **SOP circular dependency not caught at load:** validate_sop() catches static cycles (rule 8); dynamic runtime loops caught by max_iterations guard
- **Race condition on governance resume:** concurrent resume calls for same procedure_execution_id must be serialized; idempotency guard on step state machine
- **SOP file tampered after load:** load_sop() validates at load time; runtime uses validated in-memory Pydantic model
- **partial evidence list:** evidence_requirements check at VALIDATING → COMPLETED transition; if incomplete, validator fails

---

## Section 59. Recommendation

**PROPOSED V2 DESIGN**

**Recommendation: Option B — Internal Reusable SOP Engine within packages/maiw-agents**

### Rationale

The verified Phase 18H/19A implementation (HEAD e33ed699) demonstrates a mature foundation:
- SOPDefinition/SOPStep contracts are well-structured and validated (validate_sop(), 8 rules)
- AgentRuntime Protocol cleanly separates the integration seam (runtime.py lines 87–126)
- Two runtimes implement the Protocol without cross-contamination
- Governance boundary is structurally enforced (WRITE capability block) — not just by instruction

Critical gaps identified:
1. No per-step completion validation (Sections 9, 10) — advancement unconditional
2. Deep Agents completion is text-pattern-based (Section 7, line 394) — not typed or validated
3. No structured retry or escalation at step level (Sections 20, 21, 23)
4. No post-write authoritative re-read in post-execution steps (Section 34)
5. No evidence requirement model per step (Section 24)

These gaps are addressable within `packages/maiw-agents` without extracting a new package. The SOPStep v2 (Section 11) with backward-compatible defaults, validator taxonomy (Section 13), and step-at-a-time Deep Agents approach (Section 28) are sufficient for V2.

**Option B is correct because:**
- Mature enough to extract procedure lifecycle from runtimes (Sections 6–7 show seam)
- Not mature enough for standalone Blueprint (Section 50: 4+ readiness criteria unmet)
- Evolution not replacement: v1 SOPs run unchanged
- Governance boundary preserved: SOP Engine never calls ActionExecutor

### Implementation order (design only — WAIT FOR ARCHITECTURE REVIEW)

```
A. SOPStep v2 Pydantic model with all new fields optional (backward compat)
B. ProcedureExecutionState (extends AgentTaskState.completed_steps)
C. SCHEMA + STATE_PREDICATE validators (two most critical types)
D. Step state machine (PENDING → VALIDATING → COMPLETED)
E. SOPStepExecutor protocol beneath AgentRuntime
F. StepBranch declarative branching model
G. Step-level retry policy enforcement
H. Structured escalation reason codes (typed enum)
I. Evidence requirement model per step
J. Deep Agents step-at-a-time refactor
K. Proof SOP A (wave_risk_resolution v2 with STATE_PREDICATE validator on observe step)
L. Proof SOP B (equipment_failure_recovery — new, with HUMAN validator)
M. Proof SOP C (inventory_exception_resolution — new, with SCHEMA validator + bounded loop)
```

**STOP CONDITIONS: Do not implement any of the above until architecture review approves.**

---

## V1 Procedure Migration

**IMPLEMENTED** — branch `feat/sop-v1-procedure-migration`, based on `380ccf2` (PR #123).

### Problem

`SOPEngine._advance()` treats `next_step_id is None` as **terminal**:

```python
return proc_state.model_copy(update={
    "current_step_id": step.next_step_id,   # None → loop exits → COMPLETED
    ...
})
```

It does *not* fall through to the next step in the YAML list. The three V1 YAML
SOPs declared no `next_step_id` on any step, so each one executed **exactly one
step** and then reported `COMPLETED`. The procedure graphs existed only in the
step descriptions, never in the data the engine reads.

This was silent: the runs did not fail, they returned a successful-looking
single-step result. `SOPStep.next_step_id`'s own field description compounded
the problem by claiming "If None, proceed to the next step in the sequence" —
the opposite of the engine's actual rule. That description has been corrected.

### Migration table

| SOP | Old effective traversal | New traversal | Version |
|---|---|---|---|
| `labor.labor_constraint_assessment` | 1 of 8 (`read_workers`) | 8 of 8 | 1.0 → 1.1 |
| `wave.wave_risk_assessment` | 1 of 7 (`read_wave_status`) | 7 of 7 | 1.0 → 1.1 |
| `operations_coordination.wave_risk_resolution` | 1 of 8 (`establish_state`) | 8 of 8 | 1.0 → 1.1 |
| `operations_coordination.wave_risk_resolution_v2` | 8 of 8 (already chained) | unchanged | 2.0 |

Resulting chains:

```
labor.labor_constraint_assessment
  read_workers → read_tasks → evaluate_imbalance → identify_deficit
  → check_constraints → generate_interventions → rank → return_assessment (TERMINAL)

wave.wave_risk_assessment
  read_wave_status → read_orders → read_cutoff → critical_path
  → identify_at_risk → evaluate_reprioritization → return_assessment (TERMINAL)

operations_coordination.wave_risk_resolution
  establish_state → diagnose → gather_specialist_evidence → generate_candidates
  → compare → recommend → submit → observe (TERMINAL)
```

Each chain is the YAML list order, confirmed step-by-step against data
dependencies (each step's declared output is the next step's declared input) and
against the SOP objective — not assumed from list order. The
`wave_risk_resolution` chain is identical to the already-proven
`wave_risk_resolution.v2.yaml` chain.

### Rules applied

1. **Explicit sequencing** — every non-terminal step names its successor via
   `next_step_id`. No step relies on list position.
2. **Terminal semantics** — exactly one terminal step per SOP, written as an
   explicit `next_step_id: null` plus a `# TERMINAL STEP` comment, so the
   terminal is a stated intent rather than an omission.
3. **Version increment** — traversal semantics changed, so each migrated SOP
   moved 1.0 → 1.1. Per Section 42 this is a *minor* bump: the step set,
   objective, and completion criteria are unchanged; only the declared
   navigation between existing steps became explicit.
4. **Nothing else changed** — action, description, delegate_to, skill_id,
   condition, stop_conditions, allowed_capabilities, allowed_subagents,
   escalation, runtime_profile, triggers, and required_context are untouched.

`next_step_id` is a **V1** navigation field, so the migrated SOPs remain pure V1
artifacts: they still declare none of the V2 step fields (`completion`,
`retry_policy`, `timeout_seconds`, `required_inputs`, `evidence_requirements`).

### No re-entry cycles

`wave_risk_resolution`'s `observe` step is described as "continue SOP from
diagnose" when the objective is not met. That re-entry is **caller-driven** — the
caller starts a new procedure run. It is deliberately *not* modelled as
`next_step_id: diagnose`, because `validate_sop()` Rule 8 statically rejects
`next_step_id` cycles. This follows the terminal semantics already established by
`wave_risk_resolution.v2.yaml`.

### Iteration-policy resolution

`TerminationPolicy.max_iterations` is the SOP **step-transition budget**, not a
separate reasoning-loop budget. Both runtimes compute it identically:

```python
remaining_budget = max(max_iterations - state.iteration, 0)
engine = SOPEngine(..., max_transitions=remaining_budget)
```

`SOPEngine.run_procedure()` increments one transition per step (including
condition-skipped steps) and escalates with `POLICY_CONFLICT` once the budget is
exceeded. A budget below a SOP's step count therefore escalates a perfectly valid
procedure before it can finish.

Once the chains became explicit, two budgets were too small:

| Agent | SOP steps | Old `max_iterations` | New | Status |
|---|---|---|---|---|
| `labor` | 8 | 5 | **10** | was blocked at step 6 |
| `wave` | 7 | 5 | **10** | was blocked at step 6 |
| `operations_coordination` | 8 | 10 | 10 | already sufficient |

The limit was raised rather than decoupled: `max_iterations` is documented and
used as a step bound, and it remains the only guard against `on_failure_step_id`
ping-pong loops, which `validate_sop()`'s static cycle check cannot see. `10`
gives each SOP its step count plus headroom for on-failure branching. The
runaway-loop guard is covered by a dedicated regression test.

This budget is runtime-neutral: `MAIWDeterministicRuntime` and `DeepAgentsRuntime`
derive `max_transitions` from the same expression, so both were affected and both
are fixed by the same change.

### Cross-runtime equivalence

Step progression is owned solely by `SOPEngine`. `SOPStepExecutor` implementations
"never decide the next step" (see `sop_engine/executor.py`), so the deterministic
and Deep Agents runtimes traverse the identical chain and neither can skip,
reorder, or shorten a procedure. Making the chains explicit strengthens this: the
graph is now in the SOP data both runtimes read, not in either runtime.

### Tests

`tests/unit/test_sop_v1_procedure_migration.py` — 51 tests. Per migrated SOP:
loads, validates, every non-terminal step has an explicit successor, all
successors resolve, exactly one terminal, traversal matches the intended chain,
traversal reaches every defined step, no cycles, no orphans, engine completes
every step. Plus: budget-covers-step-count for all three agents, explicit 8-step
labor and 7-step wave completion runs, runaway-loop escalation, no write
capabilities added, still-pure-V1, and versions incremented.

One test guards the premise itself: stripping `next_step_id` reproduces the old
single-step behaviour, so if the engine's terminal rule ever changes, the
migration's rationale is re-examined rather than silently invalidated.

---

## Appendix: Current Package Structure Snapshot

```
packages/maiw-agents/
└── maiw_agents/
    ├── contracts/
    │   ├── sop.py          SOPDefinition, SOPStep, StepCondition, EscalationRule, validate_sop, load_sop
    │   ├── runtime.py      AgentRuntime (Protocol), AgentExecutionContext, AgentTaskResult, check_capability_alignment
    │   ├── task.py         AgentTaskState, AgentTaskStatus, StepResult, AgentObservation, SkillResultRef
    │   ├── agent.py        AgentDefinition, GovernanceBoundary, TerminationPolicy, AgentTrigger
    │   ├── definitions.py  Canonical instances: OCA, Labor, Wave, Equipment, Safety
    │   ├── registry.py     CapabilityClass, SkillRegistryEntry, SKILL_REGISTRY
    │   └── delegation.py   AgentDelegationRequest, AgentDelegationResult
    ├── runtime/
    │   ├── deterministic.py      MAIWDeterministicRuntime (Phase 18H.8), handle_delegation()
    │   ├── deep_agents_runtime.py DeepAgentsRuntime (Phase 19A), get_runtime() factory
    │   ├── model_adapter.py      MAIWModelGatewayChat
    │   └── skill_adapter.py
    ├── operations/agent.py  OperationsCoordinationAgent
    ├── labor/agent.py       LaborAgent
    ├── wave/agent.py        WaveAgent
    ├── equipment/agent.py   EquipmentAssetOperationsAgent
    └── assessment.py        Assessment base types

agents/sops/
├── operations_coordination/wave_risk_resolution.v1.yaml  (runtime_profile: adaptive, 8 steps, v1.1)
├── operations_coordination/wave_risk_resolution.v2.yaml  (runtime_profile: adaptive, 8 steps, v2.0 — Proof SOP A)
├── labor/labor_constraint_assessment.v1.yaml              (runtime_profile: strict, 8 steps, v1.1)
└── wave/wave_risk_assessment.v1.yaml                      (runtime_profile: strict, 7 steps, v1.1)

All four declare explicit next_step_id chains and a single terminal step.
See "V1 Procedure Migration" above.
```
