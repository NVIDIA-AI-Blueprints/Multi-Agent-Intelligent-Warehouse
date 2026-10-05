# MAIW ↔ NemoClaw / OpenShell Integration

**Version:** MAIW v2 — Phase 20C-B (live sandbox + approved Nemotron end-to-end qualified)
**Status:** FULL_END_TO_END_QUALIFIED — Real OpenShell sandbox (maiw-qual-20c-b) ran inference through MAIW HTTP boundary to approved Nemotron 3/3.5 model. 51 real_sandbox tests pass on qualification host (epg-tme-smc-h100-02).
**Code:** [`integrations/nemoclaw/`](../../integrations/nemoclaw/)
**Tests:** `tests/contract/test_sandbox_*.py` (127 tests, in CORE CI) + `tests/contract/test_phase_20b_real_inference.py` (16 tests, host-side) + `tests/contract/test_phase_20c_approved_nemotron.py` (63 tests, Phase 20C-A contract) + `tests/real_sandbox/test_phase_20c_live_sandbox.py` (51 tests, real_sandbox mark)

---

## Governing principle

> OpenShell enforces the security boundary; NemoClaw packages and operates it;
> MAIW continues to define what the agent is allowed to do and remains the sole
> authority over warehouse actions.

---

## Purpose

Phase 20A places the MAIW agent runtime inside a sandbox, so that a compromise
of the reasoning process is contained rather than trusted to restrain itself.

It does **not** move MAIW onto NemoClaw. Nothing in `packages/` changed. The
integration is additive, one-directional and removable: `integrations/nemoclaw`
imports from `maiw_agents`, nothing in `packages/` imports from
`integrations/`, and a test asserts it stays that way.

---

## Why containment, not migration

A migration would move MAIW semantics — SOP progression, capability
authorisation, governance handoff — onto a platform that has its own opinions
about all three. The result is two implementations of each, and two
implementations of a security boundary diverge. The divergence is not
hypothetical: NemoClaw ships a Model Router, and MAIW's `ModelGateway` carries a
`PolicyFilter`, a `DeploymentResolver` and routing provenance that a second
router would bypass without anyone noticing.

So the boundary is a decorator, not a port:

```python
runtime = SandboxedAgentRuntime(
    inner=MAIWDeterministicRuntime(...),   # unchanged, and unaware
    config=SandboxConfig.from_env(),
    provisioner=OpenShellSandboxProvisioner(),
)
```

**The containment property stated as a code fact:** if
`integrations/nemoclaw/` were deleted, MAIW's capability enforcement, governance
handoff and procedure persistence would be exactly as they are today, and only
the second wall would be gone.

**A sandbox authorises nothing.** Every capability check that runs unsandboxed
still runs sandboxed, in the same place, through the same `authorize_step`. The
sandbox is a second wall behind the first, for the case where the first is
defeated by a bug. A deployment that treated the sandbox as *the* control and
relaxed the policy would have fewer walls, not more.

---

## Ownership boundaries

| Concern | MAIW | NemoClaw / OpenShell |
|---|---|---|
| Warehouse semantics | ✓ owns | ✗ never sees |
| SOP semantics (steps, retry, loops, evidence) | ✓ owns | ✗ |
| `RuntimeCapabilityPolicy` | ✓ authors | enforces the rendered projection |
| Sandbox isolation (namespaces, seccomp, fs) | ✗ | ✓ owns |
| Network policy | ✓ defines (deny-by-default + 2 endpoints) | ✓ enforces |
| Credential custody | ✓ sole holder, host-side | ✗ holds none; none injected |
| Inference routing | ✓ `ModelGateway` selects the model | may proxy the transport only |
| Model selection policy | ✓ owns (`PolicyFilter`, `ModelRouter`) | ✗ — platform router disabled |
| Governance (`DecisionEngine`, approval) | ✓ owns, host-side | ✗ |
| `ActionExecutor` | ✓ owns, host-side | ✗ never in the image |
| MCP WRITE capabilities | ✓ owns, host-side | ✗ never exposed |
| Procedure persistence (authoritative) | ✓ `ProcedureStateStore`, host-side | ✗ (working copy only) |
| Agent packaging / image / lifecycle | ✗ | ✓ owns |
| Boundary message validation | ✓ owns (host side) | ✗ |

Every cell is backed by code or a test, not by intent. The rows that would be
most expensive to get wrong — `ActionExecutor`, MCP WRITE, credentials — are
asserted both statically (AST import audit) and in the rendered manifest.

---

## What runs inside the sandbox

```
SOP Engine                 sop_engine/{engine,validators,executor,state_store}.py
Agent runtime              runtime/{deterministic,deep_agents_runtime}.py
Capability authorisation   contracts/capability_policy.py
Procedure state model      contracts/procedure_state.py
Domain predicates          {wave,equipment,inventory}/predicates.py
```

Their combined import closure is stdlib + `pydantic` + `yaml` + MAIW contracts.
No `maiw_execution`, no `maiw_decision`, no database driver, no MCP write
client.

## What stays on the host

```
DecisionEngine             governance
ActionExecutor             the only thing that writes
ApprovalStore              human authority
ModelGateway               model selection, PolicyFilter, routing provenance
MCP write servers          equipment.assign, labor.allocate, wave.reprioritize
ProcedureStateStore        authoritative procedure state
Boundary validators        validate_sandbox_output / validate_governance_input
maiw_agents/*/state_aware_ops.py   holds a DecisionEngine — host-side by design
```

That last line is the one worth noticing. `maiw_agents` is *mostly* sandbox-safe
but not entirely: `operations/state_aware_ops.py` and
`equipment/state_aware_ops.py` import `DecisionEngine`. The payload is therefore
an enumerated module list, not "the package" — and a test asserts the exclusion
is still justified, because a stale exclusion list is how a module quietly
rejoins a payload it was removed from.

---

## RuntimeCapabilityPolicy → sandbox policy

`RuntimeCapabilityPolicy` already answers "what may this runtime invoke?". It
has no opinion about networks, filesystems or credentials, which is what a
sandbox actually enforces. `render_sandbox_policy()` adds that projection.

```yaml
# Generated by MAIW from RuntimeCapabilityPolicy — do not edit by hand.
policy_id: 00000000-0000-4000-8000-000000000000
policy_revision: 1
policy_profile: maiw-readonly-reasoning
sop_id: operations_coordination.wave_risk_resolution_v2
sop_version: 2.0
runtime: deterministic

network:
  default: deny
  allowed:
    - endpoint: http://maiw-api:8000/api/v1/inference
      purpose: inference
    - endpoint: http://maiw-api:8000/api/v1/capabilities/read
      purpose: read_capabilities

filesystem:
  writable:
    - /workspace/procedure_state
  readable:
    - /workspace/sop_definitions

capabilities:
  allowed_classes: [ANALYTICAL, PROPOSAL, READ]
  denied_classes: [EMERGENCY_WRITE, WRITE]
  allowed_ids:
    - warehouse.wave.evaluate_reprioritization
    - warehouse.wave.inspect_tasks
    - warehouse.wave.reprioritize
    - warehouse.wave.status
  allowed_subagents:
    - labor_specialist

credentials:
  custody: host_only
  managed: []
  injected: []  # empty — the sandbox holds no credentials
```

Three properties, each with a test:

| Property | Means | Why it matters |
|---|---|---|
| **Deterministic** | same policy + config → byte-identical YAML | no timestamp, UUID or frozenset ordering leaks in, so a policy diff between two deployments shows a real difference or nothing at all |
| **Monotonic** | rendered ⊆ MAIW policy, checked on every render | if this ever failed, the sandbox would be a privilege-*escalation* path rather than a containment one |
| **Credential-free** | `injected_credentials == ()`, unconditionally | a rendered policy is logged, diffed and written to disk; it has to be safe to treat as non-secret |

### PROPOSAL is not WRITE

`warehouse.wave.reprioritize` is **PROPOSAL** class and *is* on the policy. It
builds an `ActionProposal` locally. The capability that writes is
`warehouse.wave.reprioritize_direct`, which is **WRITE** class and is on no
policy that can be constructed. Conflating the two would either break every SOP
or hide a real write, so the distinction is asserted rather than assumed.

### WRITE has four routes in. All four are closed.

| Route | Closed by |
|---|---|
| naming the class | model validator rejects `WRITE`/`EMERGENCY_WRITE` in `allowed_capability_classes` |
| naming a capability id | every allowed id is looked up in `SKILL_REGISTRY`; a write class is rejected, and an *unregistered* id is rejected too |
| reaching a write surface over the network | endpoint strings are scanned for write-shaped tokens, in both `SandboxConfig` and `SandboxNetworkEndpoint` |
| carrying a credential that writes elsewhere | `injected_credentials` must be empty |

These live on the **model**, not in the renderer. A hand-constructed
`RenderedSandboxPolicy` — in a test, in future glue code, by a caller that
thought it knew better — is held to the same rule.

---

## Network policy

Deny by default. Two endpoints, both host-side MAIW surfaces:

| Purpose | Endpoint | Why not direct |
|---|---|---|
| `inference` | MAIW inference route → `ModelGateway` | the sandbox never holds a provider key and never selects a model |
| `read_capabilities` | MAIW READ/ANALYTICAL capability route | read-only; no write capability is routed here |

There is no `write` purpose and no `governance` purpose in the
`EndpointPurpose` type. Adding one would be a change to the authority model, not
a change to a config file.

Under the container provisioner the namespace is `--network=none`
unconditionally, and the two endpoints are reached through a host-managed egress
proxy. Handing the container a network namespace plus an allow-list would put
the allow-list inside the blast radius of the thing it constrains.

---

## Credential custody

The sandbox holds **no** credentials. Not the NVIDIA/NIM provider key, not a
database URL, not an MCP write token.

- `credential_custody: host_only`, and `injected_credentials` cannot be made
  non-empty.
- `SandboxConfig` rejects an endpoint with URL userinfo
  (`https://user:secret@host/`) — a rendered policy is an artifact that gets
  logged and diffed, and a credential in a URL leaks into all of that.
- `container_run_args()` emits no `--env` flags. The environment is not a policy
  surface.
- A secret-shaped scan over the rendered policy and the integration source is a
  test, not a review step.

The sandbox authenticates *to MAIW*. MAIW authenticates to everything else.

---

## Inference flow

**Option A applies** — `ModelGateway` is host-side.

```
Sandboxed AgentRuntime
    → MAIWModelGatewayChat
    → authenticated MAIW inference endpoint   ══ sandbox boundary ══
    → ModelGateway (host)                         PolicyFilter
                                                  ModelRouter
                                                  DeploymentResolver
                                                  routing provenance
    → NIM / provider
```

The sandbox has no provider access and no provider key. `ModelGateway` remains
the model-selection authority.

**Hard rule, declared in the manifest as data rather than prose:**

```yaml
inference:
  model_selection_authority: maiw.ModelGateway
  use_platform_model_router: false
```

NemoClaw/OpenShell may proxy the *transport*. MAIW selects the *model*. Adopting
NemoClaw's Model Router would bypass `PolicyFilter`, `DeploymentResolver` and
routing provenance in one step, and a duplicated routing decision is one that
can disagree with itself.

> **Gap:** `ModelGateway` is currently instantiated in-process by
> `apps/api/maiw_api/bootstrap.py`; **no HTTP endpoint exposes inference today**.
> The `/api/v1/inference` route in the config above is the designed target, not
> an existing surface. Standing it up is Phase 20B work and is listed under
> Deferred work. Until it exists, a sandbox cannot actually reach inference —
> which is one of the reasons this phase does not claim runtime qualification.

---

## MCP policy

The sandbox sees **no MCP server directly**. READ/ANALYTICAL capability results
arrive through the single MAIW read endpoint.

Mixed read/write MCP servers are the reason. `mcp_servers/equipment` serves
`get_status` and `get_telemetry` (read) alongside `assign`, `release` and
`schedule_maintenance` (write) on the same port. Exposing that server to obtain
its read capabilities would expose its write capabilities too, and no amount of
client-side discipline inside a potentially-compromised sandbox makes that safe.

```yaml
mcp:
  read_servers_via: http://maiw-api:8000/api/v1/capabilities/read
  write_servers: []
  write_servers_exposed: false
```

Stated as manifest data so an operator cannot read the manifest and conclude a
write endpoint was merely forgotten.

---

## State persistence

| | Authoritative | Working copy |
|---|---|---|
| `ProcedureExecutionState` | host `ProcedureStateStore` | `/workspace/procedure_state` in the sandbox |
| `AgentTaskState` | host | not in the sandbox |
| `RuntimeCapabilityPolicy` | derived on every run, never stored | — |

Policies are **derived, not restored**. A restarted sandbox rebuilds the
identical grant from the same reviewed `AgentDefinition` and `SOPDefinition`, so
there is no stored policy to tamper with between runs, and no restore path that
could widen one. `assert_not_broadened` is checked on each render.

`revision` is the optimistic-concurrency counter and doubles as the staleness
check at the boundary: a recommendation or a governance outcome carrying a
revision the host does not currently hold is rejected.

---

## Recovery

| Scenario | Behaviour |
|---|---|
| Sandbox cannot start, `SANDBOX_REQUIRED` | task fails; wrapped runtime never runs |
| Sandbox cannot start, `SANDBOX_PREFERRED` | warn, continue unsandboxed; MAIW policy still applies |
| Policy cannot be applied | treated as unavailable — a sandbox without its policy *looks* contained in the logs, which is worse than an absent one |
| Sandbox dies mid-procedure | procedure state is host-held; a fresh sandbox resumes without replay (tested) |
| Sandbox dies while `WAITING_FOR_GOVERNANCE` | the pause lives on the host; resume is unaffected (tested) |
| Governance outcome delivered twice | `GovernanceInbox` drops the duplicate, keyed on the proposal not the message (tested) |
| Post-write restart | the write already happened on the host before the outcome existed; the risk is a *double resume*, which the inbox prevents |

---

## Threat model

**Assumption: the sandbox is compromised.** The model has been injected, the
runtime has a bug, the process is executing attacker-chosen code. Every boundary
validator is written to be correct under that assumption.

| Attack | Outcome |
|---|---|
| Invoke a WRITE capability | `CapabilityDeniedError` — the policy is frozen and `WRITE` is denied in every policy that can be constructed |
| Invoke an undeclared READ capability | denied — deny-by-default, not deny-known-bad |
| Invent a capability name | denied — unregistered means unclassifiable means denied |
| Claim a READ class for a write capability | denied — the registry is consulted, not the caller |
| Reach an arbitrary internet host | no route — deny-by-default network |
| Reach the governance or execution API | not routed; endpoint strings are also rejected at config time |
| Read host filesystem | only `/workspace/*` mounts; `--read-only`, `--cap-drop=ALL`, `no-new-privileges` |
| Read a provider credential | none present — custody is host-only |
| Forge a recommendation for another procedure | rejected — bound to host-held procedure id, task id and revision |
| Replay a stale recommendation | rejected — revision mismatch |
| Forge a governance outcome | rejected — procedure must be `WAITING_FOR_GOVERNANCE` with a matching revision |
| Replay a governance outcome | dropped by `GovernanceInbox` |
| Burn a legitimate outcome's idempotency key with a malformed copy | prevented — mismatched messages are rejected *before* the inbox records them |
| Smuggle MCP parameters out in a recommendation | structurally impossible — `RecommendedAction` has no params field |
| Persuade the sandbox to report itself as unsandboxed | `SandboxConfig` is host-side and read before the sandbox exists |

**What a sandbox compromise still achieves:** bad *recommendations*. A
compromised agent can recommend a harmful-but-well-formed intervention. That is
unchanged by this phase and is precisely what governance and human approval
exist for — the sandbox narrows the blast radius to "can propose", which is the
authority an agent was always supposed to have.

---

## Current qualification status

**Phase 20B — real NemoClaw/OpenShell runtime qualification performed on epg-tme-smc-h100-02.**

See the full qualification report: `docs/audits/MAIW_NEMOCLAW_SECURITY_QUALIFICATION.md`
Machine-readable evidence: `artifacts/nemoclaw/phase20b/security_qualification.json`

Platform audit performed on Phase 20B host (2026-10-03):

| Component | Result |
|---|---|
| NemoClaw CLI | v0.0.124 installed at `~/.local/bin/nemoclaw` |
| OpenShell CLI | v0.0.116 installed at `~/.local/bin/openshell` |
| OpenShell gateway | healthy (port 8991) |
| Docker | 29.3.0, daemon reachable |
| NVIDIA Container Toolkit | 1.19.0 (CDI configured) |
| GPU | 4× H100 NVL (sm_90a) |
| NemoClaw preflight | 11/11 checks passed |
| Sandbox image | pulled (ghcr.io/nvidia/nemoclaw/langchain-deepagents-code-sandbox) |
| MAIW tests | 584/584 pass |

### What was verified in Phase 20B

- ✅ Policy renderer: determinism, monotonicity, write isolation, credential
  absence, golden YAML
- ✅ Boundary contracts: binding, staleness, terminal-state and duplicate
  rejection
- ✅ Fail-closed: `SANDBOX_REQUIRED` never reaches the inner runtime on any
  failure path
- ✅ Prompt-injection resistance at the authorisation seam
- ✅ Static payload audit: no `maiw_execution`, no `maiw_decision`, no
  `ActionExecutor` binding
- ✅ Proof SOP A across the boundary with a **recording sandbox double**
- ✅ NemoClaw installed and operational on a real host
- ✅ OpenShell gateway started, healthy, and serving on port 8991
- ✅ Sandbox image pulled and container security properties confirmed at runtime:
  `ReadonlyRootFS=true`, `CapDrop=['ALL']`, `no-new-privileges=true`,
  `User=1000:1000`, `Internal network=true`
- ✅ Inference routing audit: NemoClaw OpenShell gateway (port 8991) and MAIW
  ModelGateway are completely independent paths; no conflict
- ✅ All MAIW authority invariants hold: ActionExecutor host-side, credentials
  host-side, no MCP WRITE in sandbox, no NeMo Relay

### Phase 20B Requalification — Inference Provider Gap RESOLVED

**Branch:** `fix/phase-20b-inference-requalification`
**Test file:** `tests/contract/test_phase_20b_real_inference.py` (16 tests, 16/16 PASS)

**F01 resolved:** H100-compatible NIM containers (`wms-nim-nano-8b` on port 8002,
`wms-nim-teacher-49b` on port 8010) were already running on the host. Selected
`nvidia/llama-3.1-nemotron-nano-8b-v1` via MAIW ModelGateway running on the host.

**F02 — architecture clarification (sandbox leg NOT YET PROVEN):** OpenShell SSRF blocks
sandbox→private IPs (expected behavior, SSRF NOT weakened). MAIW ModelGateway runs on HOST.
When Phase 20C delivers an HTTP endpoint for ModelGateway, the sandbox will call that URL
(passes SSRF); host-side ModelGateway then calls localhost:8002. The sandbox→host-endpoint
path has NOT been demonstrated in a real OpenShell sandbox.

**Host-side inference chain qualified (ALL TESTS RUN ON HOST, NOT IN REAL SANDBOX):**
```
host pytest → MAIWModelGatewayChat → ModelGateway → NIMProvider → NIMClient → localhost:8002
                                                                              (nvidia/llama-3.1-nemotron-nano-8b-v1)
```

**Phase 20C-A HTTP boundary is IMPLEMENTED** — `POST /api/v1/inference` is live:
```
real OpenShell sandbox → [SSRF] → POST http://maiw-api:8000/api/v1/inference
                                  ════ OPENSHELL BOUNDARY ════
                                  host ModelGateway → PolicyFilter (Nemotron 3/3.5 only)
                                  → ModelRouter → NIMProvider → approved Nemotron provider
```

Sandbox-side: `MAIWHTTPModelGatewayClient` in `integrations/nemoclaw/http_model_gateway_client.py`

**APPROVED MODEL FAMILY:** Only Nemotron 3 and Nemotron 3.5 may serve production/qualification
inference. `nvidia/llama-3.1-nemotron-nano-8b-v1` (Phase 20B transport smoke test) is NOT
approved — it proved transport mechanics only (TRANSPORT_SMOKE_TEST_ONLY label in qualification docs).

- ✅ Host-side real inference via `ModelGateway` (`test_step7_real_inference_via_model_gateway`, @nim_required)
- ✅ Host-side real inference via `MAIWModelGatewayChat` (`test_step7_chat_adapter_real_inference_via_gateway`, @nim_required)
- ✅ Exactly one gateway call per inference (`test_step7_exactly_one_gateway_call_per_inference`)
- ✅ Trace ID propagated through gateway (`test_step7_trace_id_propagated_through_gateway`)
- ✅ No direct provider calls from agent code (`test_step7_no_direct_provider_call_from_agent_code`)
- ✅ HOST-SIDE SOP A governance boundary with real inference (`test_step8_sop_a_governance_boundary_with_real_gateway`, @nim_required)
- ✅ Agent code cannot instantiate NIMClient (`test_step9_agent_code_cannot_instantiate_nim_client`)
- ✅ Gateway failure is failure, not mock (`test_step10_gateway_failure_is_failure_not_mock`)
- ✅ Expired deadline raises before provider call (`test_step12_expired_deadline_raises_before_provider_call`)
- ✅ Credentials not injected into adapter response (`test_step13_credentials_not_injected_into_adapter_response`)
- ✅ Sandbox policy network default deny (code invariant, `test_step14_sandbox_policy_network_default_deny`)
- ✅ Write authority never rendered in policy (code invariant, `test_step14_sandbox_policy_write_never_rendered`)
- ✅ HTTP inference API contract (54 tests, `tests/contract/test_phase_20c_approved_nemotron.py`)
- ✅ Approved Nemotron family enforced by PolicyFilter (Nemotron 3/3.5 only; Llama-family rejected)
- ✅ Forbidden fields (provider_url, api_key, force_model_id, deployment_mode) rejected at HTTP layer
- ✅ Sandbox HTTP client never falls back to local gateway or direct NIM
- ❌ Real OpenShell sandbox making real inference call — PENDING @real_sandbox tests on qualified host
- ❌ Approved Nemotron 3/3.5 real response from real sandbox — PENDING real NIM deployment
- ❌ localhost:8002 unreachable FROM real sandbox — SSRF documented, not runtime-verified in this PR

---

## Deferred work

| Item | Phase | Status |
|---|---|---|
| ~~Host-side `/api/v1/inference` endpoint fronting `ModelGateway`~~ | 20C-A | **DONE** — `src/api/routers/inference.py` |
| ~~Approved Nemotron 3/3.5 model family policy enforcement~~ | 20C-A | **DONE** — `PolicyFilter.APPROVED_MODEL_GENERATIONS` |
| ~~Sandbox HTTP transport client~~ | 20C-A | **DONE** — `integrations/nemoclaw/http_model_gateway_client.py` |
| Real OpenShell sandbox inference call with approved Nemotron | 20C-B | @real_sandbox qualification required |
| Host-side `/api/v1/capabilities/read` endpoint | 20C | sandboxed reads E2E |
| `OpenShellSandboxProvisioner.apply_policy` against real pinned version | 20C | real policy enforcement |
| Reconcile `maiw.nemoclaw/v1alpha1` manifest against the real NemoClaw schema | 20C | `status: QUALIFIED` |
| Agent image build + pin (`image_reference`) | 20C | packaging |
| `GovernanceInbox` backed by the procedure store (currently per-process) | 20C | multi-process hosts |
| Full end-to-end Proof SOP A across real sandbox boundary | 20C | runtime denial, restart |
| NeMo Relay | — | explicitly out of scope |
| UX-1G | — | explicitly out of scope |

---

## File map

| File | Responsibility |
|---|---|
| `integrations/nemoclaw/sandbox_config.py` | `SandboxMode`, `SandboxRuntimeKind`, `SandboxConfig`, `from_env` |
| `integrations/nemoclaw/sandbox_policy.py` | `RenderedSandboxPolicy`, `render_sandbox_policy`, `render_policy_yaml` |
| `integrations/nemoclaw/boundary_contracts.py` | the two boundary messages, host-side validators, `GovernanceInbox` |
| `integrations/nemoclaw/sandbox_adapter.py` | `SandboxedAgentRuntime`, provisioners, `container_run_args` |
| `integrations/nemoclaw/manifest.py` | `render_agent_manifest` |
| `integrations/nemoclaw/http_model_gateway_client.py` | **Phase 20C-A** — thin sandbox→host inference HTTP transport |
| `integrations/nemoclaw/agent_manifest.yaml` | generated draft, `CONFIGURATION_PENDING` |
| `src/api/routers/inference.py` | **Phase 20C-A** — bounded `POST /api/v1/inference` HTTP endpoint |
| `tests/contract/test_sandbox_policy_render.py` | write isolation, monotonicity, determinism, golden |
| `tests/contract/test_sandbox_boundary_contracts.py` | egress/ingress validation, idempotency |
| `tests/contract/test_sandbox_fail_closed.py` | fail-closed, prompt injection, static payload audit |
| `tests/contract/test_sandbox_proof_sop_a.py` | Proof SOP A across the boundary |
| `tests/contract/test_sandbox_manifest.py` | manifest derivation and honesty |
| `tests/contract/test_phase_20c_approved_nemotron.py` | **Phase 20C-A** — model family policy, HTTP contract, client contract |

---

## See also

- [AGENT_RUNTIME.md](AGENT_RUNTIME.md) — the runtime the sandbox wraps
- [GOVERNANCE.md](GOVERNANCE.md) — why sandbox isolation ≠ authorization
- [MODEL_GATEWAY.md](MODEL_GATEWAY.md) — model selection authority
- [SOP_ENGINE_V2_DESIGN.md](SOP_ENGINE_V2_DESIGN.md) — procedure persistence
- [DEPLOYMENT_ARCHITECTURE.md](DEPLOYMENT_ARCHITECTURE.md) — sandbox topology
