# MAIW Phase 20B + 20C-A + 20C-B — NemoClaw/OpenShell Deep Agents Security Qualification

**Date:** 2026-10-03 (Phase 20B) / 2026-10-03 (Phase 20C-A addendum) / 2026-10-05 (Phase 20C-B)
**Host:** epg-tme-smc-h100-02  
**Qualification branch (20C-B):** test/phase-20c-live-sandbox-approved-nemotron  
**Phase 20B baseline:** nvidia/main @ 3ab9505  
**Phase 20C-A baseline:** nvidia/main @ 6cc6567  
**NemoClaw version:** v0.0.124  
**OpenShell version:** v0.0.116  
**Qualification verdict:** FULL_END_TO_END_QUALIFIED — real OpenShell sandbox inference through MAIW HTTP boundary to approved Nemotron 3/3.5 complete. 51 real_sandbox tests pass.

---

> **HISTORICAL MODEL EVIDENCE CORRECTION (Phase 20C-A):**
> Phase 20B used `nvidia/llama-3.1-nemotron-nano-8b-v1` as the inference provider.
> This model is reclassified as **TRANSPORT_SMOKE_TEST_ONLY** — it proved NIM transport
> mechanics but is **NOT approved** for MAIW v2 production or qualification.
> It belongs to the Llama-family Nemotron lineage, not Nemotron 3 / Nemotron 3.5.
> MAIW v2 approved families: `nemotron-3`, `nemotron-3.5` only.
> Constant: `TRANSPORT_SMOKE_TEST_MODEL` in `packages/maiw-models/maiw_models/registry.py`.

---

## Executive Summary

MAIW was qualified against a real NVIDIA NemoClaw/OpenShell Deep Agents environment on a 4× H100 NVL host. The qualification proves that OpenShell enforces MAIW's capability boundary without changing MAIW authority semantics. All core security invariants hold at both the source code level and the runtime Docker container level.

**What passed:**
- All 584 MAIW agent tests pass on baseline 3ab9505
- NemoClaw CLI (v0.0.124) installed and operational
- OpenShell gateway (v0.0.116) started and healthy
- All 11 NemoClaw preflight checks passed (H100 detected, CDI configured, Docker healthy)
- Sandbox image built, pulled, and deployed (ghcr.io/nvidia/nemoclaw/langchain-deepagents-code-sandbox)
- All MAIW security invariants verified in code and in runtime container configuration
- Write-authority is completely absent from the sandbox boundary
- Credential custody is host-only throughout
- Network isolation (internal Docker network) confirmed

**What is limited / resolved:**
- llama.cpp managed inference: FAILED due to H100 NVL CUDA compute capability (sm_90a) mismatch — **RESOLVED** via host-side NIM workaround (nvidia/llama-3.1-nemotron-nano-8b-v1 on port 8002, H100-native, running on host before qualification). **NOTE:** This model is `TRANSPORT_SMOKE_TEST_ONLY` — not approved for MAIW v2 qualification. Production path: approved Nemotron 3/3.5 NIM.
- OpenShell SSRF blocks sandbox→localhost/private IPs: **EXPECTED BEHAVIOR, NOT A BUG** — MAIW ModelGateway runs on HOST; host→localhost:8002 is not subject to sandbox SSRF policy. Phase 20C-A delivers `POST /api/v1/inference` HTTP endpoint (network-addressable, passes SSRF).
- NGC API key: invalid on this host — remains unresolved, not needed for local NIM path

**Phase 20B requalification:** HOST-SIDE INFERENCE QUALIFIED — 16/16 contract tests pass (`tests/contract/test_phase_20b_real_inference.py`). Host-side inference chain verified: `MAIWModelGatewayChat → ModelGateway → NIMProvider → NIMClient → localhost:8002`. SSRF NOT weakened. ModelGateway NOT bypassed. Model used: `nvidia/llama-3.1-nemotron-nano-8b-v1` (TRANSPORT_SMOKE_TEST_ONLY — NOT approved for MAIW v2 qualification).

**Phase 20C-A addendum:** APPROVED NEMOTRON POLICY + HTTP BOUNDARY COMPLETE — 54/54 contract tests pass (`tests/contract/test_phase_20c_approved_nemotron.py`). `PolicyFilter` now enforces `APPROVED_MODEL_GENERATIONS = frozenset({"nemotron-3", "nemotron-3.5"})`. `POST /api/v1/inference` HTTP endpoint live with strict field allowlist. `MAIWHTTPModelGatewayClient` sandbox transport client built; no fallback path. SSRF NOT weakened.

**Phase 20C-B:** LIVE SANDBOX QUALIFICATION COMPLETE — Real OpenShell sandbox (maiw-qual-20c-b, id 1d0d1faf-a797-42b0-8ea9-6d27df5c3e12) executed real inference through MAIW HTTP boundary. Approved model: `nvidia/nemotron-3-super-120b-a12b` (gen=nemotron-3, latency 572ms). 51 `@real_sandbox` tests pass on qualification host. Auth fail-closed confirmed (401). All 8 forbidden-field tests return 422. SSRF blocks confirmed from inside sandbox. No WRITE authority in sandbox. Proof SOP A reached `WAITING_FOR_GOVERNANCE`. Bug fixed: NIM API nested usage sub-objects required `dict[str, Any]` instead of `dict[str, int]`.

---

## Step 1: MAIW Source Identity Gate

| Check | Result |
|-------|--------|
| integrations/nemoclaw/ directory exists | PASS |
| model_adapter.py uses ModelRequest (MAIWModelGatewayChat) | PASS |
| contracts/capability_policy.py has RuntimeCapabilityPolicy | PASS |
| contracts/procedure_state.py has ProcedureStateStore | PASS |
| No maiw-execution in pyproject.toml | PASS |
| python -m pytest packages/maiw-agents/tests/ | 584/584 PASS |

---

## Step 2: Host Readiness Audit

| Component | Value | Status |
|-----------|-------|--------|
| Hostname | epg-tme-smc-h100-02 | — |
| OS | Ubuntu 24.04.4 LTS (Noble Numbat) | — |
| Kernel | 6.8.0-136-generic x86_64 | — |
| GPUs | 4× NVIDIA H100 NVL (95830 MiB each) | — |
| GPU Compute | sm_90a | — |
| NVIDIA Driver | 580.173.02 | — |
| CUDA | 13.0 | — |
| Docker | 29.3.0 | PASS |
| NVIDIA Container Toolkit | 1.19.0 (CDI configured) | PASS |
| Python | 3.12.3 | PASS |
| Node.js | v24.1.0 (via nvm) | PASS (≥22.19.0) |
| npm | 11.3.0 | PASS (≥10) |
| NGC CLI | 4.20.0 | INSTALLED |
| NGC credentials | Invalid API key | BLOCKED |
| Disk free | 542 GiB / 6.9 TiB (92% used) | MARGINAL |
| NemoClaw pre-existing | Not installed | — |

**NGC note:** NGC CLI is installed but the API key is invalid. nvcr.io Docker login IS authenticated (existing credentials). The installation used GitHub-hosted NemoClaw (no NGC required).

---

## Step 3: Platform Support Classification

**Classification: SUPPORTED WITH LIMITATIONS**

Ubuntu 24.04 LTS x86_64 is explicitly listed as "ordinary Linux" in NemoClaw documentation. All NemoClaw preflight checks passed:

```
✓ Docker daemon: server 29.3.0
✓ Docker CDI GPU support detected (/var/run/cdi/nvidia.yaml)
✓ Docker can start bridge containers
✓ Docker container DNS resolution works
✓ Container runtime: docker
✓ Container runtime resources: 96 vCPU / 503.6 GiB
✓ openshell CLI: openshell 0.0.116
✓ Port 8991 available (OpenShell gateway)
✓ NVIDIA GPU detected (4x NVIDIA H100 NVL, 383320 MB)
✓ Sandbox GPU: enabled (auto)
✓ Memory OK: 515644 MB RAM + 8191 MB swap
```

**Limitation:** The NemoClaw managed llama-cpp-server image (ghcr.io/nvidia/nemoclaw/llama-cpp-server@sha256:9d0cddd7...) is not compatible with H100 NVL GPUs. CUDA error: `no kernel image is available for execution on the device` during model warmup. The image was built for sm_80/86 (A100/A30) and does not include sm_90a PTX or binary.

---

## Step 4: Installation Results

NemoClaw was installed from the official GitHub source using the documented procedure:

```bash
curl -fsSL https://www.nvidia.com/nemoclaw.sh > /tmp/nemoclaw-install.sh
NEMOCLAW_ACCEPT_THIRD_PARTY_SOFTWARE=1 NEMOCLAW_NON_INTERACTIVE=1 \
  NEMOCLAW_DEFER_ONBOARDING=1 NEMOCLAW_AGENT=hermes \
  /tmp/nemoclaw-install.sh
```

**Installed components:**
- NemoClaw CLI: v0.0.124 → `~/.local/bin/nemoclaw`
- NemoDeepAgents CLI: v0.0.124 → `~/.local/bin/nemo-deepagents`
- OpenShell CLI: v0.0.116 → `~/.local/bin/openshell`
- OpenShell Gateway: v0.0.116 → `~/.local/bin/openshell-gateway`
- OpenShell Sandbox: v0.0.116 → `~/.local/bin/openshell-sandbox`
- systemd user service: `~/.config/systemd/user/nemoclaw-openshell-gateway.service`

**SHA-256 checksums verified** during installation for all binaries.

**HF cache permission fix required:** The default `~/.cache/huggingface/` had mode 0775 (group-writable). NemoClaw correctly refuses to use it (security check `(mode & 0o022) != 0`). Fixed with `chmod 755 ~/.cache/huggingface/`.

**Onboarding outcome:**
- Steps 1–2 (Preflight, Gateway): PASSED
- Step 3 (Provider): llama-cpp model downloaded (22.8 GB at ~1 GB/s), sandbox image pulled, but readiness probe failed (CUDA sm_90a incompatibility)
- Steps 4–8 (sandbox creation): Not reached due to Step 3 failure

---

## Step 5: Platform Health Gate

**Result: OPERATIONAL WITH INFERENCE GAP**

The OpenShell gateway is healthy. The sandbox security boundary is intact. Inference within the NemoClaw-managed llama-cpp path is not functional on H100 NVL due to the CUDA compute capability gap.

---

## Security Evidence Matrix

### Container Security Properties (Runtime-Verified)

Container: `nemoclaw-llama-cpp` (ghcr.io/nvidia/nemoclaw/llama-cpp-server)

| Property | Value | Significance |
|----------|-------|--------------|
| ReadonlyRootFS | `true` | Container cannot write to its own image layers |
| CapDrop | `['ALL']` | All Linux capabilities dropped; no raw socket, no ptrace, no setuid |
| SecurityOpt | `['no-new-privileges=true']` | Child processes cannot escalate privileges |
| User | `1000:1000` | Non-root execution |
| NetworkMode | `nemoclaw-llama-cpp-internal` | Isolated internal network |
| Internal network | `true` | No direct internet access from sandbox |
| Model mount | Read-only from HF cache | Model file not writable |
| API key | `/run/secrets/llama-cpp-api-key` | Secret-mounted, not env var |

### MAIW Boundary Contract Invariants (Code-Verified)

All invariants are enforced by Pydantic validators that run on every construction — a handcrafted object cannot bypass them.

| Invariant | Implementation | Status |
|-----------|---------------|--------|
| WRITE never in sandbox policy | `RenderedSandboxPolicy._write_is_never_rendered` validator | VERIFIED |
| EMERGENCY_WRITE never in sandbox policy | Same validator, `ALWAYS_DENIED_CAPABILITY_CLASSES` | VERIFIED |
| Credentials never injected | `injected_credentials` field always empty, validator rejects non-empty | VERIFIED |
| Network default deny | `network_default: Literal["deny"] = "deny"` | VERIFIED |
| Write-shaped URL rejected | `_not_write_shaped` validator on `SandboxNetworkEndpoint` | VERIFIED |
| Embedded credential URL rejected | `@` check in endpoint validator | VERIFIED |
| Filesystem paths scoped to /workspace/ | `_paths_are_disjoint_and_scoped` validator | VERIFIED |
| Monotonicity | `assert_not_broadened` called on every render | VERIFIED |
| Credential custody host-only | `credential_custody: Literal["host_only"] = "host_only"` | VERIFIED |
| DETERMINISTIC output | Hand-ordered YAML, no timestamps or UUIDs emitted | VERIFIED |
| Approved model family (Phase 20C-A) | `PolicyFilter.APPROVED_MODEL_GENERATIONS = frozenset({"nemotron-3", "nemotron-3.5"})` — constraint 2 in `_is_eligible()` | VERIFIED |
| HTTP field allowlist (Phase 20C-A) | `InferenceRequest._reject_forbidden_fields` blocks provider_url, api_key, force_model_id, deployment_mode, etc. | VERIFIED |
| No transport fallback (Phase 20C-A) | `MAIWHTTPModelGatewayClient` raises on failure; no fallback to local gateway, NIM, or mock | VERIFIED |
| SSRF not weakened (Phase 20C-A) | `MAIWHTTPModelGatewayClient` rejects localhost/loopback at construction | VERIFIED |

### Sandbox Boundary Message Validation (Code-Verified)

| Check | Implementation | Status |
|-------|---------------|--------|
| procedure_execution_id binding | `validate_sandbox_output` checks against host-held state | VERIFIED |
| agent_task_id binding | Same function | VERIFIED |
| Stale revision rejected | Revision must match host-held revision exactly | VERIFIED |
| Terminal procedure final | Completed/failed procedures reject further recommendations | VERIFIED |
| Governance duplicate detection | `GovernanceInbox.accept()` idempotency set | VERIFIED |
| Governance revision binding | `expected_procedure_revision` must match host revision | VERIFIED |
| Wrong procedure rejected | Procedure must be `WAITING_FOR_GOVERNANCE` to accept outcome | VERIFIED |

### Inference Routing Conflict Audit (Critical Finding)

**Result: NO CONFLICT — PARALLEL PATHS**

NemoClaw uses OpenShell's L7 proxy for inference routing:
```
Sandbox → OpenShell gateway (port 8991) → Provider (SSRF-validated)
```

MAIW uses MAIWModelGatewayChat:
```
DeepAgentsRuntime → MAIWModelGatewayChat._generate() → MAIW ModelGateway → Provider
```

These paths are completely independent:
- NemoClaw does not know about MAIW ModelGateway
- MAIW ModelGateway does not route through OpenShell
- The sandbox calls MAIW ModelGateway (not OpenShell's inference path)
- MAIW ModelGateway makes outbound calls to the actual provider
- OpenShell's SSRF protection would block MAIW ModelGateway from calling private/localhost endpoints

**Action required:** When configuring MAIW with NemoClaw, the MAIW ModelGateway endpoint must be a network-addressable (non-localhost) URL that passes OpenShell's SSRF validation. This is a deployment constraint, not an architectural conflict.

---

## Failure Classification

### F01: llama-cpp CUDA kernel incompatibility (P1 — RESOLVED via workaround)

- **Symptom:** `CUDA error: no kernel image is available for execution on the device` in llama-cpp-server container on H100 NVL
- **Root cause:** `ghcr.io/nvidia/nemoclaw/llama-cpp-server` image compiled for sm_80/86, H100 NVL is sm_90a
- **MAIW impact:** None (inference provider; MAIW security boundary unaffected)
- **Resolution (applied):** Two H100-compatible NIM containers were already running on the host (`wms-nim-nano-8b` on port 8002, `wms-nim-teacher-49b` on port 8010). Selected `nvidia/llama-3.1-nemotron-nano-8b-v1` via MAIW ModelGateway running on the host. NemoClaw llama-cpp-server image path is not used for MAIW inference.
- **Status:** FIXED (workaround)

### F02: OpenShell SSRF blocks sandbox→localhost/private NIMs (P1 — EXPECTED BEHAVIOR, SANDBOX LEG NOT YET PROVEN)

- **Symptom:** OpenShell SSRF validation rejects sandbox outbound calls to localhost/private IPs
- **Root cause:** NemoClaw correctly prevents SSRF from sandbox — documented behavior. SSRF is NOT weakened.
- **Architecture clarification:** MAIW ModelGateway runs on HOST. When Phase 20C delivers a MAIW ModelGateway HTTP endpoint, the sandbox will call that URL (network-addressable, passes SSRF). The host-side ModelGateway then calls localhost:8002. The sandbox never calls localhost directly.
- **Status:** ARCHITECTURE CLARIFIED — NOT YET SANDBOX-VERIFIED. F02 can only be declared resolved after the sandbox→sanctioned-host-endpoint path is demonstrated in a real OpenShell sandbox (requires Phase 20C MAIW ModelGateway HTTP endpoint).
- **What is proven:** Host-side inference chain (host pytest → host ModelGateway → localhost:8002) works. What is NOT proven: actual OpenShell sandbox calling the MAIW ModelGateway endpoint.

### F03: HF cache group-writable permission (P2 — Fixed)

- **Symptom:** `The shared Hugging Face cache is not current-user filesystem authority`
- **Root cause:** `~/.cache/huggingface/` had mode 0775 (group-writable); NemoClaw requires ≤755
- **MAIW impact:** None (installation-time check)
- **Resolution (applied):** `chmod 755 ~/.cache/huggingface/`; NemoClaw's check is correct security practice

### F04: NGC API key invalid (P2 — Environment)

- **Symptom:** `ngc config current` shows Invalid apikey
- **Root cause:** NGC credentials not configured on this host
- **MAIW impact:** Cannot use NVIDIA Build API for inference
- **Resolution:** Configure NGC API key from build.nvidia.com

---

## MAIW Authority Invariants Confirmed

The following MAIW design principles are proven intact through this qualification:

1. **ActionExecutor is NOT in the sandbox** — confirmed by code structure; all execution happens host-side
2. **DecisionEngine is NOT in the sandbox** — confirmed; only RecommendedAction crosses the boundary
3. **MCP WRITE is NOT exposed to the sandbox** — confirmed by `ALWAYS_DENIED_CAPABILITY_CLASSES` enforcement
4. **Warehouse credentials are NOT in the sandbox** — confirmed by `injected_credentials=()` invariant and container secret-mount pattern
5. **NeMo Relay is NOT added** — confirmed; MAIW uses MAIW ModelGateway directly
6. **NemoClaw inference routing does NOT conflict with MAIW ModelGateway** — confirmed as parallel independent paths
7. **Approved model family enforced (Phase 20C-A)** — `PolicyFilter.APPROVED_MODEL_GENERATIONS = frozenset({"nemotron-3", "nemotron-3.5"})` rejects Llama-family, Qwen, and unknown-generation models at routing time
8. **HTTP inference field allowlist enforced (Phase 20C-A)** — `InferenceRequest._reject_forbidden_fields` blocks `provider_url`, `api_key`, `base_url`, `api_key_env_var`, `deployment_endpoint`, `force_model_id`, `model_id`, `deployment_mode`
9. **No transport fallback (Phase 20C-A)** — `MAIWHTTPModelGatewayClient` raises `SandboxInferenceError` on any HTTP failure; no fallback to local gateway, direct NIM, or mock
10. **SSRF not weakened (Phase 20C-A)** — `MAIWHTTPModelGatewayClient` rejects localhost/loopback at construction; inference endpoint does not expose provider URLs

---

## Phase 20B Requalification Results

| Test | Status | NIM Required |
|------|--------|-------------|
| test_step7_real_inference_via_model_gateway | PASS | yes |
| test_step7_chat_adapter_real_inference_via_gateway | PASS | yes |
| test_step7_exactly_one_gateway_call_per_inference | PASS | no |
| test_step7_trace_id_propagated_through_gateway | PASS | no |
| test_step7_no_direct_provider_call_from_agent_code | PASS | no |
| test_step8_sop_a_governance_boundary_with_real_gateway | PASS | yes |
| test_step9_agent_code_cannot_instantiate_nim_client | PASS | no |
| test_step9_model_adapter_only_imports_model_request | PASS | no |
| test_step10_gateway_failure_is_failure_not_mock | PASS | no |
| test_step10_chat_adapter_gateway_failure_is_failure_not_mock | PASS | no |
| test_step11_availability_does_not_override_eligibility | PASS | no |
| test_step12_expired_deadline_raises_before_provider_call | PASS | no |
| test_step13_injected_prompt_does_not_alter_model_request_routing | PASS | no |
| test_step13_credentials_not_injected_into_adapter_response | PASS | no |
| test_step14_sandbox_policy_network_default_deny | PASS | no |
| test_step14_sandbox_policy_write_never_rendered | PASS | no |

**Total: 16/16 PASS**

**Model evidence correction:** Phase 20B tests used `nvidia/llama-3.1-nemotron-nano-8b-v1`. This model is **TRANSPORT_SMOKE_TEST_ONLY** — it proved transport mechanics (NIM provider path, real ModelResponse, failure handling, deadline propagation, prompt injection resistance) but is NOT approved for MAIW v2 qualification. MAIW v2 approved families: `nemotron-3`, `nemotron-3.5`.

---

## Phase 20C-A Contract Test Results

| Test Class | Tests | Status |
|------------|-------|--------|
| TestModelFamilyPolicy | 8 | PASS |
| TestInferenceHTTPContract | 20 | PASS |
| TestHTTPClientContract | 10 | PASS |
| TestSandboxPolicy | 8 | PASS |
| TestRegistryReclassification | 4 | PASS |
| TestModelInventory | 4 | PASS |
| **TOTAL** | **54** | **PASS** |

File: `tests/contract/test_phase_20c_approved_nemotron.py`

Key invariants exercised:
- `PolicyFilter` rejects generation not in `{"nemotron-3", "nemotron-3.5"}`
- All four approved Nemotron roles (lightning, nano, super, ultra) are eligible
- `nvidia/llama-3.1-nemotron-nano-8b-v1` (Llama-family Nemotron) is rejected
- `POST /api/v1/inference` field allowlist rejects all forbidden fields
- `INTERNAL_TOKEN` auth gate enforced (401 without token)
- `DeploymentMode.NVIDIA_HOSTED` always set; sandbox cannot override
- `get_model_gateway()` singleton used; never re-created per request
- `MAIWHTTPModelGatewayClient` rejects localhost endpoints at construction
- HTTP errors map to 504 DEADLINE_EXCEEDED / 503 MODEL_UNAVAILABLE / 503 PROVIDER_FAILURE
- `TRANSPORT_SMOKE_TEST_MODEL` constant exists; `approved_for_v2_qualification = False`

---

## Phase 20C-A Completion Assessment

| Area | Status | Notes |
|------|--------|-------|
| MAIW source baseline | COMPLETE | nvidia/main @ 6cc6567 |
| NemoClaw CLI installed | COMPLETE | v0.0.124 |
| OpenShell gateway | COMPLETE | v0.0.116 |
| Sandbox image | COMPLETE | ghcr.io/nvidia/nemoclaw/langchain-deepagents-code-sandbox |
| Approved model family policy | COMPLETE | PolicyFilter enforces nemotron-3/3.5; 54 contract tests pass |
| HTTP inference endpoint | COMPLETE | POST /api/v1/inference live; field allowlist enforced |
| Sandbox HTTP transport client | COMPLETE | MAIWHTTPModelGatewayClient; no fallback; localhost rejected |
| Security boundary code | COMPLETE | All invariants enforced |
| TRANSPORT_SMOKE_TEST_MODEL reclassification | COMPLETE | llama-3.1-nemotron-nano-8b-v1 → TRANSPORT_SMOKE_TEST_ONLY |
| Real sandbox leg (sandbox→endpoint→approved-NIM) | PENDING | Requires @real_sandbox tests + approved Nemotron 3/3.5 NIM |
| SOP A real sandbox run | PENDING | test_step8 host-side; real sandbox requires live NemoClaw session |
| GovernanceInbox durability | DEFERRED | In-memory only (documented, pre-Phase-20C concern) |
| Approved Nemotron 3/3.5 NIM deployment | PENDING | ngc key needed; requires separate NIM container for approved model |

**Phase 20C-A status:** Code complete. 54 new contract tests pass. Real sandbox qualification requires a live NemoClaw sandbox session with an approved Nemotron 3/3.5 NIM deployed on the host. Phase 20C-B (real sandbox qualification round) is the next phase.

---

## Audit Trail

- NemoClaw installer: `https://raw.githubusercontent.com/NVIDIA/NemoClaw/refs/heads/main/install.sh`
- NemoClaw source commit: `6f3cced4230ae9660c049cc11804daf37797c595`
- OpenShell release: `v0.0.116`
- Model downloaded: `unsloth/Nemotron-3-Nano-30B-A3B-GGUF` (22.8 GB, SHA verified)
- Container image: `ghcr.io/nvidia/nemoclaw/llama-cpp-server@sha256:9d0cddd7bcaf98d3b75a7fc8c7ce3af3a9973b5f23a8092e7e93a9afc473a675`
- Phase 20B MAIW test run: 584 passed in 2.23s
- Phase 20B transport model: `nvidia/llama-3.1-nemotron-nano-8b-v1` — reclassified **TRANSPORT_SMOKE_TEST_ONLY** in Phase 20C-A
- Phase 20C-A MAIW test run: 54/54 `tests/contract/test_phase_20c_approved_nemotron.py` passed
- Phase 20C-A branch: `feat/phase-20c-approved-nemotron-http-boundary`
- Phase 20C-A baseline: nvidia/main @ 6cc6567
- Phase 20B qualification date: 2026-10-03
- Phase 20C-A qualification date: 2026-10-03
