# MAIW v2 Release Notes

## What is MAIW v2

MAIW v2 is a reference architecture and implementation for governed AI participation in intelligent warehouse operations, where agents reason and recommend inside bounded runtimes while operational authority, governance, execution, and reconciliation remain explicit, deterministic, and auditable.

Core lifecycle:

```
Observe → Reason → Recommend → Govern → Approve → Execute → Observe Outcome
```

Core invariant: AI may be adaptive in how it reasons, but operational authority remains explicit, deterministic, and auditable.

## Architecture

MAIW v2 is organized around a set of canonical packages, each with a clear, enforced ownership boundary:

| Package | Owns |
|---------|------|
| `maiw-contracts` | Shared contracts: `ActionProposal`, governance types, `RecommendedAction` |
| `maiw-mcp` | MCP client, capability registry, circuit breakers |
| `maiw-state` | `WarehouseState`, domain state models |
| `maiw-decision` | `DecisionEngine` — synchronous, no I/O, APPROVED/REJECTED/DEFERRED |
| `maiw-models` | `ModelGateway`, NIM provider, `PolicyFilter`, `ModelRouter` |
| `maiw-skills` | Inventory, Equipment, Labor, Wave skills |
| `maiw-execution` | `BaseActionExecutor` (6-guard pattern), domain executors |
| `maiw-agents` | Equipment, Labor, Wave, Operations, Safety agents; SOP Engine V2 |
| `maiw-world` | Warehouse World — DataPack, ScenarioOverlay, Explorer |

The FastAPI application (`apps/api`) bootstraps and wires all packages. Integrations (`integrations/nemoclaw`) import from packages and never the reverse.

## Governance and Safety

**Authority boundary:** The `RecommendedAction` from an agent is semantic intent — above the authority boundary. The `ActionProposal` is a governed artifact, below the boundary. Only `ActionExecutor` crosses from proposal to write. The `DecisionEngine` is synchronous and performs no I/O. Human approval is explicit, expirable, and single-use where required.

**Sandbox isolation:** Either runtime can be wrapped in an OpenShell sandbox via NemoClaw. The sandbox boundary is enforced at the `RuntimeCapabilityPolicy` level. `WRITE` and `EMERGENCY_WRITE` capabilities have no route into the sandbox. Provider credentials are outside the sandbox. The sandbox is containment, not migration — all MAIW semantics remain in packages, and the integration imports from packages (never the reverse).

**RuntimeCapabilityPolicy:** Deny-by-default. Each task receives an immutable policy built from `AgentDefinition`, SOP, and the capability registry — never from model output, a prompt, or anything a sandbox declares about itself.

## SOP Engine V2

The SOP Engine is the execution substrate for MAIW's Standard Operating Procedures. Key properties:

- **Explicit executable SOPs:** Versioned YAML artifacts, not prompt templates. A SOP names a registered predicate; it cannot supply one.
- **Validator-owned completion authority:** A runtime reporting `COMPLETED` is a claim. The engine runs the declared validator — the validator's verdict is what advances the procedure.
- **Bounded loops and retries:** All bounds are held by the engine, not the model.
- **Evidence enforcement:** `evidence_requirements` are enforced as completion preconditions. Model prose cannot satisfy an evidence requirement.
- **Persistence and recovery:** `ProcedureStateStore` makes procedures recoverable across restarts. The SOP version is pinned — a procedure never auto-upgrades mid-execution.
- **External governance:** A write-related step pauses at `WAITING_FOR_GOVERNANCE`; the SOP Engine never crosses the authority boundary.

Three proof SOPs ship with MAIW v2:

| SOP | Property Proven |
|-----|-----------------|
| `wave_risk_resolution.v2` | Multi-domain coordination with post-execution state verification |
| `equipment_failure_recovery.v1` | Write landing, intended transition, and actual recovery are three separate proofs |
| `picking_inventory_exception.v1` | Bounded loop + facility-strategy variation without a separate code path |

## ModelGateway

All model calls route through a single `ModelGateway` chain:

```
AgentRuntime → ModelGateway → PolicyFilter → ModelRouter → Deployment Resolver → NVIDIA NIM / Hosted
```

`PolicyFilter` runs before any routing decision and enforces the approved model family list. There is no silent mock fallback in production — failure stays failure.

## Supported Model Families

MAIW v2 supports **Nemotron 3 and Nemotron 3.5** model families only.

This is enforced by `PolicyFilter.APPROVED_MODEL_GENERATIONS = frozenset({"nemotron-3", "nemotron-3.5"})`. Any model with a generation outside this set is rejected before any provider call.

## NemoClaw / OpenShell

MAIW v2 integrates with NemoClaw v0.0.124 and OpenShell v0.0.116 for sandboxed agent execution. The integration:

- Wraps either `MAIWDeterministicRuntime` or `DeepAgentsRuntime` inside an OpenShell sandbox
- Renders a sandbox policy from `RuntimeCapabilityPolicy` — deterministic, monotonic, credential-free
- Connects the sandbox to the host-side `ModelGateway` via `POST /api/v1/inference` (strict field allowlist)
- Enforces deny-by-default network policy inside the sandbox

The sandbox is **containment, not migration.** All SOP semantics, governance, and execution remain in MAIW packages.

## Deployment

MAIW v2 ships a reference deployment for development, demo, and qualification:

- Single-node Docker Compose stack (reference environment)
- Startup validation via `scripts/check_demo_environment.sh`
- Demo mode (`MAIW_DEMO_MODE=true`) runs without PostgreSQL, Redis, Milvus, or Kafka — requires only `NVIDIA_API_KEY`
- Reference deployment runbook: `docs/operations/REFERENCE_DEPLOYMENT_RUNBOOK.md`

## Developer Journey UX

The MAIW v2 UI (`src/ui/web`) provides:

- **7-stage Developer Journey rail** — Environment → Model → World → Scenario → Copilot → Agent → Outcome
- **Operator panel** — Wave risk, labor, equipment, inventory; Copilot turns; governed action approval
- **Developer panel** — Agent reasoning, SOP trace, evidence inspection, ModelGateway provenance
- **Platform/Security page** (`/deployment`) — Sandbox policy, authority boundary, model policy, deployment topology
- **Model Gateway Evaluation Lab** (`/models/lab`) — Read-only artifact-backed multi-model comparison

## Qualification

MAIW v2 has been qualified across four qualification activities:

| Activity | Artifact | Verdict |
|----------|---------|---------|
| Security boundary + live sandbox inference | `artifacts/nemoclaw/phase20b/security_qualification.json` | FULL_END_TO_END_QUALIFIED |
| Live OpenShell sandbox + approved Nemotron 3/3.5 | `artifacts/nemoclaw/phase20c/live_sandbox_qualification.json` | LIVE_SANDBOX_QUALIFIED |
| Reference deployment operationalization | `artifacts/deployment/reference_deployment_qualification.json` | OPERATIONALIZATION COMPLETE |
| UX persona acceptance | `artifacts/ux/ux1g_final_persona_acceptance.json` | PASS (Operator 10/10, Developer 15/15, Platform/Security 12/12) |

Qualification host: epg-tme-smc-h100-02 (4 x H100 NVL, sm_90a, NemoClaw 0.0.124, OpenShell 0.0.116).

## Test Baseline

- Python CORE CI: 2604 passed, 0 failed, 3 skipped (2667 total including `test_phase_20c_approved_nemotron.py` run in isolation)
- UI: 963 passed across 39 test suites
- Black: PASS
- ESLint: 0 errors

## Known Limitations

- **Single-node reference deployment (not HA).** The reference deployment runs on a single host. No multi-replica coordination or HA persistence.
- **Qualified on epg-tme-smc-h100-02 and reference environment.** Behavior on other GPU configurations or cloud environments is not qualified.
- **real_sandbox tests skip on non-qualification hosts.** Tests marked `@pytest.mark.real_sandbox` require NemoClaw/OpenShell installed and skip elsewhere — this is expected behavior.
- **Pre-existing ESLint warnings.** 1041 warnings (no-console, no-explicit-any); 0 errors. Non-blocking.
- **Semantic Release skips on PR branches.** Expected CI behavior for release branches.
- **test_phase_20c_approved_nemotron.py ordering issue.** 23 tests fail when run after the full CORE CI suite due to ModelGateway singleton state; all 63 tests pass when the file is run in isolation. Pre-existing, non-blocking.

## Deferred (Post-v2)

The following items are confirmed out of scope for v2 and deferred:

- HA persistence and multi-replica procedure state coordination
- NeMo Relay integration
- Standalone SOP Blueprint packaging
- `MODEL_JUDGE` and `HUMAN` validators
- Broader SOP library (beyond the three proof SOPs)
- Cosmos / world-model integration
- OTEL span instrumentation
- Declarative `StepBranch` model

These items do not affect the v2 release readiness or safety invariants.
