# MAIW v2 Reference Deployment Runbook

**Phase**: 20C-C — Deployment Operationalization; v2.0.1 canonical-app remediation
**Status**: v2.0.1 release candidate — awaiting independent re-audit
**Last updated**: 2026-10-07

> **v2.0.1 change.** Everything in this runbook targets ONE process: the
> canonical shipped app `maiw_api.app:app`. It serves `POST /api/v1/inference`
> on the API port (8001); there is no separate `:8020` inference server and the
> legacy `src/api/app.py` is never started for a deployment. See
> `docs/audits/MAIW_V2.0.1_REMEDIATION_AUDIT.md`.

---

## Purpose / Scope

This runbook describes the canonical single-node MAIW v2 reference deployment.
It covers every lifecycle operation a developer or operator needs to bring up,
validate, stop, restart, recover, back up, restore, and roll back the qualified
architecture without tribal knowledge.

**Covered**: start, stop, restart, status, smoke test, qualification, backup,
restore, rollback, secret rotation, upgrade policy, troubleshooting.

**Not covered**: high availability, multi-region, distributed consensus,
Kubernetes autoscaling, NeMo Relay, SOP Engine extraction.

---

## Supported Topology

```
HOST (single node)
├── MAIW API — uvicorn maiw_api.app:app (port 8001, the only API process)
│   ├── ModelGateway  →  PolicyFilter (nemotron-3 / nemotron-3.5 ONLY)
│   │                 →  ModelRouter  →  NIMProvider  →  NIM endpoint
│   ├── DecisionEngine → ActionExecutor (governed writes only)
│   ├── ProcedureHost (maiw_api.procedure_host) — SOP Engine bound to:
│   │     JsonFileProcedureStateStore  ($MAIW_PERSISTENCE_ROOT/procedures/)
│   │     JsonFileGovernanceInbox      ($MAIW_PERSISTENCE_ROOT/governance/)
│   ├── POST /api/v1/inference  (auth-required: X-Maiw-Internal-Token)
│   ├── GET  /api/v1/procedures (read-only view of the durable store)
│   └── legacy /api/v1/chat — NOT mounted (v2.0.1)
├── Approved Nemotron 3/3.5 deployment
│   └── nvidia/nemotron-3-super-120b-a12b  (gen=nemotron-3, qualified)
│       Hosted at: https://integrate.api.nvidia.com/v1
│       OR local NIM: http://<host>:8000/v1
└── NemoClaw/OpenShell sandbox (MAIW_SANDBOX_MODE=required)
    ├── SOP Engine (agent-side procedure runner)
    ├── DeepAgentsRuntime
    ├── RuntimeCapabilityPolicy (deny-by-default; WRITE/EMERGENCY_WRITE always denied)
    └── MAIWHTTPModelGatewayClient → POST http://<HOST_IP>:8001/api/v1/inference

Persistence root: /var/lib/maiw/
  procedures/   — JsonFileProcedureStateStore (one .json per procedure, atomic)
  governance/   — JsonFileGovernanceInbox (governance_inbox.jsonl, append-only)
  runtime/      — PID file, API log
```

---

## Known Limitations

- **Single node only** — no distributed consensus, no HA failover.
- **File-backed state** — survives process restart on same filesystem; not multi-replica safe.
- **Auth token rotation requires restart** — both API and sandbox must restart.
- **No Kubernetes manifests** — see `docs/architecture/DEPLOYMENT_ARCHITECTURE.md` for conceptual target.
- **No NeMo Relay** — out of scope for v2 reference deployment.
- **Provider dependency** — if NIM endpoint is unreachable, inference degrades; governance and procedure state are preserved.

---

## Version Matrix

| Component | Required Version | Qualification Status |
|---|---|---|
| NemoClaw | **0.0.124** | QUALIFIED (PR #135, 2026-10-05) |
| OpenShell | **0.0.116** | QUALIFIED (PR #135, 2026-10-05) |
| Python (host) | **>= 3.12.3** | Qualified on 3.12.3 |
| Qualified model | `nvidia/nemotron-3-super-120b-a12b` | gen=nemotron-3, latency 572ms |
| Approved generations | `nemotron-3`, `nemotron-3.5` | PolicyFilter enforced |
| MAIW SHA baseline | `1745a2c2d7d90041c2603acfb8291df71855278f` | nvidia/main |

Do **not** use floating `latest` tags. Pin exact versions.

---

## Prerequisites

1. NVIDIA H100 or equivalent GPU (sm_90a or compatible)
2. NVIDIA driver 580+ and CUDA 12+
3. Python 3.12.3+
4. Docker or Podman (container runtime for NemoClaw)
5. NemoClaw 0.0.124: `pip install nemoclaw==0.0.124`
6. OpenShell 0.0.116: `pip install openshell==0.0.116`
7. NVIDIA API key (for hosted NIM) or local NIM endpoint
8. Approved model configured: `LLM_MODEL=nvidia/nemotron-3-super-120b-a12b`

---

## Configuration

All configuration is via environment variables. Copy `.env.example` to `.env`:

```bash
cp .env.example .env
# Edit .env — fill in MAIW_INFERENCE_INTERNAL_TOKEN, NVIDIA_API_KEY, etc.
```

### Required Variables

| Variable | Description | Example |
|---|---|---|
| `MAIW_INFERENCE_INTERNAL_TOKEN` | Auth token for inference boundary | 64-char hex string |
| `NVIDIA_API_KEY` | NIM provider credential | `nvapi-...` |
| `LLM_MODEL` | Approved model ID | `nvidia/nemotron-3-super-120b-a12b` |
| `MAIW_SANDBOX_MODE` | Must be `required` | `required` |
| `MAIW_SANDBOX_RUNTIME` | Must be `openshell` | `openshell` |
| `MAIW_SANDBOX_MODEL_GATEWAY_ENDPOINT` | Sandbox → host inference URL (canonical app, API port) | `http://10.x.x.x:8001/api/v1/inference` |

### Optional Variables

| Variable | Default | Description |
|---|---|---|
| `MAIW_PERSISTENCE_ROOT` | `/var/lib/maiw` | Durable state root |
| `MAIW_API_PORT` | `8001` | MAIW API port |
| `LLM_NIM_URL` | `https://integrate.api.nvidia.com/v1` | NIM provider endpoint |
| `MAIW_NEMOCLAW_VERSION` | (unset) | Version assertion for preflight |
| `MAIW_OPENSHELL_VERSION` | (unset) | Version assertion for preflight |

### Development-Only (NEVER set in reference deployment)

| Variable | Description |
|---|---|
| `MAIW_INFERENCE_ALLOW_UNAUTHENTICATED` | Bypasses auth — dev only |
| `MAIW_MOCK_INFERENCE` | Enables mock inference — dev only |
| `MAIW_DEMO_MODE` | Simulation mode — dev only |

---

## Secrets

| Secret | Who holds it | Process that needs it | Sandbox sees it | Restart on rotation |
|---|---|---|---|---|
| `MAIW_INFERENCE_INTERNAL_TOKEN` | MAIW operator | MAIW API + sandbox | YES (to authenticate to MAIW API) | YES — API and sandbox must restart |
| `NVIDIA_API_KEY` | MAIW operator | MAIW API (NIMProvider) | NO — never forwarded to sandbox | YES — API must restart |
| `JWT_SECRET_KEY` | MAIW operator | MAIW API (auth signing) | NO | YES |
| `POSTGRES_PASSWORD` | MAIW operator | MAIW API (DB layer) | NO | YES |

**Invariants**:
- No secrets are committed to version control
- No secrets appear in logs or health endpoints
- No warehouse write credentials in sandbox
- No NIM/provider credential in sandbox
- `MAIW_INFERENCE_INTERNAL_TOKEN` is the only credential that flows to the sandbox

---

## Preflight

```bash
bash scripts/preflight_reference_deployment.sh
```

Validates: OS, Python, GPU visibility, NVIDIA driver, Docker/Podman, NemoClaw
0.0.124, OpenShell 0.0.116, approved model configured, model generation is
nemotron-3 or nemotron-3.5, Llama-family not configured, required ports free,
persistence dirs writable, auth token set (>= 32 chars), dev override NOT active,
sandbox mode = required.

Returns non-zero on failure. Never proceeds to start on preflight failure.

---

## Start

```bash
bash scripts/start_reference_deployment.sh
```

Startup sequence:
1. Preflight (can skip with `--skip-preflight`)
2. Create persistence directories (chmod 700)
3. Load `.env`
4. Check approved model provider reachability
5. Start MAIW API (uvicorn, background)
6. Wait for readiness (GET /api/v1/ready, timeout 120s)
7. Print safe deployment summary (no secrets)

---

## Readiness

```bash
curl http://localhost:8001/api/v1/ready   # 200 = ready, 503 = not ready
curl http://localhost:8001/api/v1/live    # 200 = process alive
```

`GET /api/v1/ready` (v2.0.1) answers "can the canonical app safely accept
work?" from the dependencies it actually uses. Any **critical** component
failing → HTTP 503 `{"status": "NOT_READY", "failed_components": [...]}`.

| Component | Critical | Ready when |
|---|---|---|
| `runtime` | yes | lifespan assembled `MAIWRuntime` |
| `persistence` | yes | `procedures/` and `governance/` exist, are listable, and accept an fsynced write/read/delete probe; stores constructed |
| `model_gateway` | yes | canonical ModelGateway constructed |
| `governed_write_path` | yes | DecisionEngine + MCP client + equipment agent present |
| `mcp_domains` | yes | not every configured MCP domain CIRCUIT OPEN |
| `database` | yes, unless `MAIW_DEMO_MODE=true` (override: `MAIW_READINESS_REQUIRE_DATABASE`) | `SELECT 1` within 3 s |
| `model_provider` | no | reported (NIM circuit); provider down → inference 503 per request |
| `sandbox_runtime` | no | reported; OpenShell calls the API, not the reverse |

Liveness (`/api/v1/live`) never depends on any of these.

```json
{
  "status": "NOT_READY",
  "failed_components": ["persistence"],
  "components": {
    "persistence": {"status": "failed", "durable": true,
                    "procedure_store": {"status": "failed", "reason": "directory missing"},
                    "governance_inbox": {"status": "ready"}},
    "model_gateway": {"status": "ready"},
    "database": {"status": "ready"}
  }
}
```

### Degraded state semantics (Step 26)

| Condition | MAIW behavior |
|---|---|
| Model provider down | `/ready` stays 200; inference returns 503 `PROVIDER_FAILURE`/`MODEL_UNAVAILABLE`; document stages fail typed; governance/write path unaffected |
| OpenShell down | `/ready` unaffected (API does not depend on it); new sandboxed tasks cannot start; stored procedures remain in the durable store; smoke test fails its sandbox check |
| Persistence unavailable (dir missing / unwritable) | `/ready` 503 `persistence` failed; `/api/v1/procedures` 503 if the store could not be built |
| Database unreachable (reference profile) | `/ready` 503 `database` failed |

---

## Smoke Test

```bash
bash scripts/smoke_test_reference_deployment.sh
```

Tests the canonical app only: liveness; readiness 200 READY; durable
persistence; `/api/v1/inference` mounted; 401 without / with wrong token; 422
for a forbidden routing field (`model_id`) and for an unknown field (`model`);
200 with the correct token and an approved Nemotron 3/3.5 generation in
`route.generation`; legacy `POST /api/v1/chat` → 404; configured model family;
OpenShell sandbox `MAIW_SANDBOX_NAME` Ready when `MAIW_SANDBOX_MODE=required`.

---

## Normal Operation

After start and smoke test pass:

- Procedure state is held host-side by `ProcedureHost` in the durable
  `JsonFileProcedureStateStore`; the sandboxed runtime reasons for its steps
- Inference flows: sandbox → POST /api/v1/inference (canonical app, :8001) → ModelGateway → PolicyFilter → NIMProvider
- Governance wait: procedure reaches WAITING_FOR_GOVERNANCE and is checkpointed to disk
- Governance decision: DecisionEngine routes approval; ActionExecutor executes the write via MCP; the outcome is applied to the procedure with `ProcedureHost.apply_governance`
- `JsonFileGovernanceInbox` records each applied outcome before resume, so a redelivery (including after restart) is dropped
- `GET /api/v1/procedures` shows stored procedures (read-only)

---

## Status

```bash
bash scripts/status_reference_deployment.sh
```

Reports: API liveness, readiness, ModelGateway status, approved model/provider,
OpenShell availability, persistence health, GovernanceInbox, active procedures,
pending governance. No secrets emitted.

---

## Stop

```bash
bash scripts/stop_reference_deployment.sh
```

Stop order:
1. Stop OpenShell sandbox processes (SIGTERM → SIGKILL after 2s)
2. Stop MAIW API (SIGTERM → SIGKILL after 30s)
3. Preserve all durable state (do NOT delete by default)
4. Report what remained running

**State is always preserved on stop.** Use `--delete-state` only for clean-slate test cycles (interactive confirmation required).

---

## Restart

```bash
bash scripts/restart_reference_deployment.sh
```

Restart preserves:
- ProcedureExecutionState (file-backed, revision-tracked)
- GovernanceInbox deduplication ledger (file-backed)
- Correlation IDs (encoded in procedure state)
- SOP version pinning
- Retry/loop budgets
- WAITING_FOR_GOVERNANCE status

The script verifies state counts before and after restart, and warns if any WAITING_FOR_GOVERNANCE procedures disappeared.

---

## Backup

Backup is a consistent copy of the persistence root:

```bash
# Recommended: stop API first for clean consistency point, then copy
bash scripts/stop_reference_deployment.sh

BACKUP_DIR="/backup/maiw/$(date +%Y%m%dT%H%M%S)"
mkdir -p "$BACKUP_DIR"
cp -r /var/lib/maiw/procedures "$BACKUP_DIR/"
cp -r /var/lib/maiw/governance "$BACKUP_DIR/"
echo "Backup at: $BACKUP_DIR"

bash scripts/start_reference_deployment.sh
```

**Notes**:
- Backup is non-destructive — source files are not deleted
- A consistent point requires API to be stopped (or at minimum all procedure writes quiesced)
- For live backup, use the qualify script which handles the sequence

---

## Restore

```bash
# 1. Stop the deployment
bash scripts/stop_reference_deployment.sh

# 2. Validate backup directory
ls -la /backup/maiw/<timestamp>/procedures/
ls -la /backup/maiw/<timestamp>/governance/

# 3. Restore from backup
cp -r /backup/maiw/<timestamp>/procedures/. /var/lib/maiw/procedures/
cp -r /backup/maiw/<timestamp>/governance/. /var/lib/maiw/governance/

# 4. Validate file permissions
chmod 700 /var/lib/maiw/procedures /var/lib/maiw/governance

# 5. Restart and verify readiness
bash scripts/start_reference_deployment.sh
curl http://localhost:8001/api/v1/ready

# 6. Verify procedure state is readable
ls /var/lib/maiw/procedures/*.json 2>/dev/null | wc -l
```

**State schema compatibility**: if stored state was written by a different MAIW
version, verify JSON schema compatibility before starting. Incompatible state
will cause the engine to fail-closed with a clear error (not silent
reinterpretation).

---

## Rollback

**Rollback baseline** (recorded at qualification):
- MAIW SHA: `1745a2c2d7d90041c2603acfb8291df71855278f`
- NemoClaw: 0.0.124
- OpenShell: 0.0.116
- Model: `nvidia/nemotron-3-super-120b-a12b` (gen=nemotron-3)

**Rollback procedure**:
```bash
# 1. Stop current deployment
bash scripts/stop_reference_deployment.sh

# 2. Roll back MAIW application (do NOT delete state)
git checkout <baseline-sha>
pip install -e . -e packages/maiw-models -e packages/maiw-agents -e packages/maiw-mcp -e apps/api

# 3. Keep state and config compatible with baseline schema
# (if state schema changed, consult state schema compatibility section)

# 4. Restart
bash scripts/start_reference_deployment.sh

# 5. Readiness and smoke test
curl http://localhost:8001/api/v1/ready
bash scripts/smoke_test_reference_deployment.sh
```

**Never delete procedure/governance state as a rollback strategy.** A procedure in WAITING_FOR_GOVERNANCE has a pending governance decision. The state records this; deleting it loses the correlation.

**Rollback with active procedure**: if a procedure is in WAITING_FOR_GOVERNANCE when rollback occurs:
- Procedure state is preserved (file-backed)
- GovernanceInbox deduplication ledger is preserved
- SOP version is pinned in the procedure state
- After rollback and restart, the procedure resumes from the same governance-wait

---

## Upgrade Policy

**Rule**: change one major dependency at a time. Rerun relevant qualification after each version change.

| Upgrade | What to requalify |
|---|---|
| MAIW code change | Unit + contract + deployment tests; smoke test |
| NemoClaw version | Sandbox security qualification (tests/contract/) |
| OpenShell version | Sandbox security qualification |
| Model checkpoint change | Policy validation + inference test |
| Approved generation added | PolicyFilter review + all policy tests |

Do not upgrade NemoClaw and OpenShell simultaneously.

---

## Troubleshooting

| Symptom | Likely cause | Check | Recovery |
|---|---|---|---|
| Inference → 401 (no token) | MAIW_INFERENCE_INTERNAL_TOKEN not set | `echo $MAIW_INFERENCE_INTERNAL_TOKEN` | Set token in .env; restart API |
| Inference → 401 (wrong token) | Sandbox using stale token | Sandbox config vs. API config | Restart sandbox with correct token |
| Inference → 503 (no eligible model) | PolicyFilter rejected all models | LLM_MODEL generation; `grep generation .env` | Use approved model (nemotron-3 or nemotron-3.5) |
| Sandbox cannot call API | Network policy / wrong endpoint | MAIW_SANDBOX_MODEL_GATEWAY_ENDPOINT | Set correct host IP (not localhost) |
| Procedure not resuming | State mismatch or inbox duplicate | Check /var/lib/maiw/procedures/*.json | Validate procedure_execution_id + revision |
| Governance stuck | GovernanceInbox has duplicate | Check governance_inbox.jsonl | Verify idempotency_key not already accepted |
| Circuit open | MCP domain repeated failures | `GET /api/v1/ready` → domain_health | Resolve MCP server issue; wait cooldown |
| Startup timeout | Provider/DB not available | Check provider URL and NVIDIA_API_KEY | Fix connectivity; retry start |
| Port already in use | Stale PID file | `ss -tlnp | grep :8001` | `bash scripts/stop_reference_deployment.sh`; then start |
| No procedure state after restart | Wrong MAIW_PERSISTENCE_ROOT | `ls /var/lib/maiw/procedures/` | Correct MAIW_PERSISTENCE_ROOT |

---

## Security Operations

**How to verify the deployment is secure**:

1. **Model generation**: `grep LLM_MODEL .env` → must be nemotron-3 or nemotron-3.5 family
2. **Auth enabled**: `curl http://localhost:8001/api/v1/inference -X POST -d '{}'` → must return 401
3. **Sandbox deny-by-default**: check RuntimeCapabilityPolicy in `integrations/nemoclaw/sandbox_policy.py` — ALWAYS_DENIED_CAPABILITY_CLASSES = frozenset({'WRITE', 'EMERGENCY_WRITE'})
4. **WRITE absent from sandbox**: `grep -r "WRITE\|EMERGENCY_WRITE" integrations/nemoclaw/sandbox_policy.py` → in ALWAYS_DENIED
5. **Secrets not exposed**: `curl http://localhost:8001/api/v1/health` → no tokens, API keys, or credentials in response
6. **Token not logged**: tail the API log → token value must not appear

**Operator do-NOT list**:
- DO NOT commit `.env` or any file containing real credentials
- DO NOT set `MAIW_INFERENCE_ALLOW_UNAUTHENTICATED=true` in reference deployment
- DO NOT set `MAIW_MOCK_INFERENCE=true` in reference deployment
- DO NOT expose the inference endpoint without `X-Maiw-Internal-Token` enforcement
- DO NOT configure Llama-family, Qwen, or any non-Nemotron-3/3.5 model
- DO NOT delete `/var/lib/maiw/procedures/` or `/var/lib/maiw/governance/` during rollback
- DO NOT deploy a new NemoClaw version without rerunning sandbox security qualification
- DO NOT add a new approved model generation without updating PolicyFilter and rerunning policy tests
- DO NOT bypass governance by injecting a WRITE capability into the sandbox policy

---

## Secret Rotation Runbook

### Rotating MAIW_INFERENCE_INTERNAL_TOKEN

1. Generate new token: `python3 -c "import secrets; print(secrets.token_hex(32))"`
2. Update `.env`: `MAIW_INFERENCE_INTERNAL_TOKEN=<new_token>`
3. Stop deployment: `bash scripts/stop_reference_deployment.sh`
4. Update sandbox configuration: the sandbox must receive the new token at launch (via environment injection)
5. Restart deployment: `bash scripts/start_reference_deployment.sh`
6. Verify: `curl -H "X-Maiw-Internal-Token: <new_token>" http://localhost:8001/api/v1/inference -X POST -H "Content-Type: application/json" -d '{"task":"test","messages":[{"role":"user","content":"OK?"}],"deadline_ms":5000}'` → 200 (never 401)
7. Verify old token rejected: same request with old token → 401

### Rotating NVIDIA_API_KEY

1. Obtain new API key from https://build.nvidia.com/
2. Update `.env`: `NVIDIA_API_KEY=<new_key>`
3. Stop deployment: `bash scripts/stop_reference_deployment.sh`
4. Restart deployment: `bash scripts/start_reference_deployment.sh`
5. Verify: smoke test inference succeeds

---

## Failure Recovery

### API process crash

1. Restart: `bash scripts/start_reference_deployment.sh --skip-preflight`
2. JsonFileProcedureStateStore and JsonFileGovernanceInbox survive the crash (file-backed)
3. Verify state count: `ls /var/lib/maiw/procedures/*.json | wc -l`
4. Run smoke test: `bash scripts/smoke_test_reference_deployment.sh`

### OpenShell/sandbox crash

1. Host truth is authoritative — sandbox state is a working copy only
2. Restart API (not necessary if API is still running) or just the sandbox
3. Any in-flight procedure resumes from the host's JsonFileProcedureStateStore
4. Duplicate governance delivery is caught by JsonFileGovernanceInbox

### Provider restart

1. ModelGateway will return 503 MODEL_UNAVAILABLE while provider is down
2. Readiness endpoint reflects degraded state for model gateway
3. No unapproved fallback — failure stays failure (no silent fallback to Llama)
4. When provider recovers, inference resumes automatically

### Governance-wait restart

1. Procedure in WAITING_FOR_GOVERNANCE: run Proof SOP A or any procedure
2. Restart API: `bash scripts/restart_reference_deployment.sh`
3. Verify: procedure still in WAITING_FOR_GOVERNANCE in state store
4. GovernanceInbox deduplication prevents double-application of governance decision

---

## Qualification Procedure

```bash
bash scripts/qualify_reference_deployment.sh [--evidence-dir /path/to/evidence]
```

Runs the full qualification sequence:
0. Preflight
1. Start → startup time baseline
2. Readiness
3. Smoke test
4. Proof SOP A (safe, non-consequential)
5. API restart → verify state preserved
6. Sandbox restart → verify host truth preserved
7. Backup / restore live test
8. Rollback baseline record
9. Stop → shutdown time baseline

Output: PASS/FAIL with evidence in `--evidence-dir`. Evidence includes readiness
response JSON and rollback baseline record.

---

## Log Locations

| Component | Location |
|---|---|
| MAIW API | `/var/lib/maiw/runtime/maiw-api.log` |
| Preflight | stdout / stderr |
| Procedure state | `/var/lib/maiw/procedures/*.json` |
| Governance inbox | `/var/lib/maiw/governance/governance_inbox.jsonl` |
| PID file | `/var/lib/maiw/runtime/maiw-api.pid` |

Log rotation: use platform defaults (logrotate or systemd journal). Configure
logrotate for `/var/lib/maiw/runtime/*.log` if retention > 7 days is required.

### Viewing logs

```bash
tail -f /var/lib/maiw/runtime/maiw-api.log
# or with journald:
journalctl -u maiw-api -f
```

---

## Process Supervision

For production use, install the MAIW API as a systemd service:

```ini
# /etc/systemd/system/maiw-api.service
[Unit]
Description=MAIW v2 API
After=network.target

[Service]
Type=simple
EnvironmentFile=/opt/maiw/.env
WorkingDirectory=/opt/maiw
ExecStart=/opt/maiw/env/bin/python -m uvicorn maiw_api.app:app \
    --host 0.0.0.0 --port 8001 --no-access-log
Restart=on-failure
RestartSec=5
StandardOutput=append:/var/lib/maiw/runtime/maiw-api.log
StandardError=append:/var/lib/maiw/runtime/maiw-api.log

[Install]
WantedBy=multi-user.target
```

One restart policy per service. Do not combine systemd with manual PID file management.
