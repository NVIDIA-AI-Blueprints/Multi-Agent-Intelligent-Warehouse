# MAIW Phase 19A — Deep Agents Compatibility Audit (Real Package)

**Audit Date:** 2026-09-19
**Auditor:** Phase 19A Corrective Commits (19A.6–19A.10)
**Status:** REAL PACKAGE — deepagents==0.7.15 installed from PyPI (MIT)

> **Note:** The previous version of this document (2026-09-19 initial) was labelled
> "SIMULATED ADAPTER (package not found on PyPI)". That evaluation used a
> self-contained "integration-seam prototype" that ZERO-imported `deepagents`.
> This document supersedes it with real package facts.

---

## 1. Package Identity

| Field | Value |
|---|---|
| Package name | `deepagents` |
| PyPI availability | **AVAILABLE** — `pip install deepagents==0.7.15` |
| Installed version | 0.7.15 |
| License | MIT |
| Python requirement | >=3.10 |
| Entry point | `from deepagents import create_deep_agent` |
| Previous simulated evaluation | "integration-seam prototype" — not real package evaluation |

---

## 2. Dependency Audit (Real Package)

| Dependency | Version | Notes |
|---|---|---|
| langchain | 1.4.2 | Required transitive |
| langchain-core | 1.6.3 | Required transitive |
| langgraph | 1.2.11 | Required transitive — ReAct graph execution |
| langgraph-prebuilt | 1.1.0 | Required transitive |
| langsmith | 0.13.0 | Required — tracing SDK (see §9 for air-gap note) |
| langchain-anthropic | 1.7.2 | Required transitive |
| langchain-google-genai | 4.4.0 | Required transitive |

**Total estimated transitive dependency weight:** ~150 MB

---

## 3. Runtime Model (Real Package)

| Property | Value |
|---|---|
| Execution model | LangGraph CompiledStateGraph — ReAct agent loop |
| Planning behavior | **EMERGENT** — no explicit TodoListMiddleware or planning middleware in 0.7.15 |
| Task decomposition | Emergent from LLM reasoning within system prompt + tool schema |
| Sub-agent interface | SubAgent TypedDict (name, description, tools, model, system_prompt, mode) |
| Model input | Accepts `BaseChatModel` directly — MAIW MAIWModelGatewayChat plugs in here |
| Graph output | `CompiledStateGraph` — invoke with `graph.ainvoke({"messages": [...]})` |

**Planning note:** There is NO `TodoListMiddleware` or explicit planning step in deepagents 0.7.15.
Planning is emergent from the LLM's ReAct loop (think → tool call → observe → repeat).
The previous simulated prototype had an explicit `_generate_plan()` method; that was
MAIW-invented behavior, not real deepagents behavior.

---

## 4. SubAgent TypedDict (Real Package)

```python
SubAgent(
    name: str,
    description: str,
    # Optional:
    tools: list | None = None,
    model: BaseChatModel | None = None,
    middleware: list | None = None,
    system_prompt: str | None = None,
    mode: Literal["isolated", "fork"] = "isolated",
)
```

MAIW defines SubAgent specs from `SOPDefinition.allowed_subagents`. The LLM decides
when to invoke a subagent based on its description and the task context.

---

## 5. Tool Interface (Real Package)

| Property | Value |
|---|---|
| Tool format | LangChain `BaseTool` / `StructuredTool` |
| Tool registration | Via `tools=` parameter to `create_deep_agent()` |
| MAIW skill wrapping | `_build_maiw_tools()` wraps SKILL_REGISTRY entries as StructuredTool objects |
| WRITE capability blocking | Hard-blocked at `_build_maiw_tools()` adapter layer |

---

## 6. Filesystem Tools / Permissions

| Property | Value |
|---|---|
| Disable filesystem tools | Pass `permissions=[]` to `create_deep_agent()` |
| MAIW enforcement | Always passes `permissions=[]` — no filesystem access |

---

## 7. Model Abstraction (Real Package)

| Property | Value |
|---|---|
| Model input type | `BaseChatModel` (langchain-core) |
| MAIW ModelGateway integration | `MAIWModelGatewayChat(BaseChatModel)` adapter wraps ModelGateway |
| Direct provider bypass | **IMPOSSIBLE** — deepagents only calls `model._generate()` via BaseChatModel interface |
| Invariants preserved | RiskLevel, ReasoningLevel, DeploymentMode, trace_id, routing provenance |
| Test mode | `MAIWModelGatewayChat(model_gateway=None)` — deterministic mock responses |

---

## 8. State / Memory Model (Real Package)

| Property | Value |
|---|---|
| Working memory | LangGraph message history (`{"messages": [...]}`) — ephemeral |
| Authoritative state | MAIW AgentTaskState — external, structured, unchanged |
| State transitions | All MAIW state transitions remain via `AgentTaskState.transition()` |
| State ownership | MAIW owns state; deepagents provides LangGraph execution scaffolding |
| Checkpointing | MAIW-external (not framework-native) |

---

## 9. LangSmith Dependency (Air-Gap Risk)

| Property | Value |
|---|---|
| LangSmith package | Required transitive (`langsmith==0.13.0`) |
| LangSmith tracing | Disabled via `LANGSMITH_TRACING=false` environment variable |
| SaaS requirement | **NO** — tracing SDK is required as package but telemetry is opt-out |
| Air-gap risk | MEDIUM — package must be installed; set `LANGSMITH_TRACING=false` in env |

**Finding:** `langsmith` is a required transitive dependency. It will always be installed
alongside `deepagents`. However, active tracing to LangSmith SaaS is disabled by setting
`LANGSMITH_TRACING=false`. The runtime code does this automatically via `os.environ.setdefault`.

---

## 10. Local / Air-Gapped Support (Real Package)

| Property | Value |
|---|---|
| Local NIM support | **VIABLE** — `MAIWModelGatewayChat` can route to local NIM endpoint |
| Air-gapped deployment | **CONDITIONAL** — requires: (1) `LANGSMITH_TRACING=false`, (2) local NIM, (3) deepagents installed from internal mirror |
| SaaS control-plane | **NOT REQUIRED** — deepagents runtime is fully local |
| No direct SaaS calls | Confirmed — LangSmith is telemetry-only and is disabled at runtime |

---

## 11. Human-in-Loop Support (Real Package)

| Property | Value |
|---|---|
| Governance boundary | Enforced via system prompt instruction + response parsing |
| WAITING_FOR_GOVERNANCE | Triggered when LLM response contains "STOP: WAITING_FOR_GOVERNANCE" |
| Governance enforcement type | STRUCTURAL (response parse) + PROMPT (system prompt instruction) |
| Resume mechanism | `resume_after_governance(governance_outcome)` method |

---

## 12. Async Support (Real Package)

| Property | Value |
|---|---|
| Async | Yes — `graph.ainvoke()` is async |
| Streaming | Not used in MAIW integration |
| Sync fallback | `_generate()` sync method honored by LangChain |

---

## 13. SOP Conformance (Real Package)

| Property | Value |
|---|---|
| Step conformance | **APPROXIMATE** — LLM may reorder or skip steps within system prompt |
| Governance stop | **EXACT** — structurally enforced via response parsing |
| Write skill blocking | **EXACT** — enforced at `_build_maiw_tools()` adapter layer |
| Determinism | **NON-DETERMINISTIC** — LLM output varies across runs |

---

## 14. Adoption Decision

Given the real package facts:

**KEEP DEEP AGENTS AS OPTIONAL RUNTIME**

Rationale:
- deepagents==0.7.15 is a real, MIT-licensed package from PyPI
- `MAIWModelGatewayChat` preserves ModelGateway invariants (cannot bypass)
- WRITE skill blocking is enforced at adapter layer (structural, not prompt-only)
- Governance boundary is enforced structurally (response parse + prompt)
- Local NIM and air-gapped deployment are viable with `LANGSMITH_TRACING=false`
- **Regressions vs MAIWDeterministicRuntime:** ~150MB dependencies, non-deterministic,
  SOP step conformance is approximate, LangSmith SDK required even when tracing off
- **Recommendation:** Use `MAIWDeterministicRuntime` as production default;
  use `DeepAgentsRuntime` for complex adaptive reasoning tasks where emergent
  LLM planning and specialist delegation add value over the deterministic SOP executor
