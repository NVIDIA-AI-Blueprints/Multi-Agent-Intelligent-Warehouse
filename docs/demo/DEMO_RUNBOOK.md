# MAIW Demo Runbook

This runbook walks an operator or developer through a complete MAIW demo from
a cold start to a finished scenario, then through a fault injection sequence.

**Audience:** Developer giving a first demo, or evaluating MAIW for the first time.  
**Time:** ~20 minutes for the core scenario, ~10 minutes for fault injection.

---

## Prerequisites

Run the preflight check first:

```bash
./scripts/check_demo_environment.sh
```

All `[OK]` entries required. Fix any `[!!]` entries before continuing.

---

## Part 1 — Core Scenario (labor_constraint_wave_risk)

This is the **recommended first scenario**. It demonstrates the full
PROPOSE → DECIDE → EXECUTE pipeline against a realistic labor/wave disruption.

### 1. Start the backend

```bash
./scripts/start_demo_mode.sh
```

Expected output:
```
MAIW Synthetic Demo Mode
─────────────────────────────────────────────────────
  API port    : 8001
  MCP servers : not required (SimulationProviders active)
  [OK] NVIDIA_API_KEY set (nvapi-...)
  ...
  3. Select 'labor_constraint_wave_risk' and click START
```

Leave this terminal open. The API is ready when you see `Application startup complete.`

### 2. Start the frontend

In a new terminal:

```bash
cd src/ui/web && npm start
```

Open http://localhost:3001 in a browser.

### 3. Navigate to the COMMAND tab

The top navigation has tabs: COMMAND, WAREHOUSE, FORECASTING, etc.  
Click **COMMAND**.

### 4. Select the scenario

In the **Demo Control Bar** at the top of the COMMAND view:
- Select `Labor Constraint + Wave Risk` from the scenario dropdown
- Click **START**

You should see the scenario status change to RUNNING and the live activity
feed begin populating.

### 5. Trigger analysis

Click **ANALYZE** (or the scenario auto-triggers analysis after a few seconds).

**What to narrate:**
> "MAIW is reading live warehouse state. Two operators are absent. A high-priority
> pick wave has 7 pending tasks with no assigned workers and a 45-minute carrier
> cutoff. The system assembles a state snapshot, seals it with a UUID, and sends
> it to the Operations Coordination Agent."

### 6. Review the proposal

The activity feed shows the agent's reasoning and the proposed action.

**What to narrate:**
> "The agent used Nemotron to reason over the snapshot. It proposed a specific
> labor reallocation — not a generic suggestion. The LLM never touched the write
> path: it produced a typed ActionProposal that now waits for the DecisionEngine."

### 7. Decision evaluation

The activity feed shows `DECISION: APPROVED` (or `REJECTED`/`DEFERRED`).

**What to narrate:**
> "The DecisionEngine evaluated the proposal deterministically — no I/O, no
> model call. It checked policy constraints and approved. Humans can override:
> the Approve and Reject buttons are live."

### 8. Approve and execute

Click **APPROVE** in the Command Center, then **EXECUTE**.

The activity feed shows `EXECUTED` with an `execution_id`.

**What to narrate:**
> "The executor ran four guards before making any write: decision APPROVED,
> decision bound to this exact proposal ID, action in the allowlist, state not
> stale. Only then did it call the MCP write tool. The outcome is explicitly
> one of six states — EXECUTED, NO_OP, DEFERRED, CONFLICT, UNKNOWN, or FAILED.
> We got EXECUTED."

### 9. Observe KPI recovery

The KPI panels show labor utilization rising and wave risk falling over time.

---

## Part 2 — Fault Injection (requires REACT_APP_FAULT_INJECTION_ENABLED=true)

The Fault Injection panel appears on the right of the reliability row when:
- Backend is running with `MAIW_DEMO_MODE=true`
- Frontend was started with `REACT_APP_FAULT_INJECTION_ENABLED=true` in `.env`

To enable, add this line to `src/ui/web/.env` and restart the frontend:
```
REACT_APP_FAULT_INJECTION_ENABLED=true
```

### Recommended fault injection sequence

#### F06 — Ambiguous Write (the hero fault)

**What to narrate:**
> "This is the most important fault in the matrix: the MCP server mutates the
> warehouse state, but the network drops before it can return. The system can't
> distinguish 'write happened' from 'write didn't happen.' Watch the outcome."

1. Select **F06 — Ambiguous Write** in the Fault Injection panel
2. Ensure a scenario is active and EXECUTE is ready
3. Click **INJECT**
4. Observe: outcome is **UNKNOWN**, not FAILED
5. The Reconciliation Status panel shows `RECONCILING`
6. Click **RECONCILE** to verify against world state
7. Outcome resolves to `CONFIRMED_EXECUTED`

**Safety scorecard shows `unauthorized_writes: 0` and `duplicate_writes: 0`.**

**What to narrate:**
> "UNKNOWN is not FAILED. The system knows a mutation may have occurred. It
> doesn't retry — that could create a duplicate write. It doesn't mark it as
> failed — that would be a false signal. It waits for reconciliation. Once
> confirmed, the original execution record remains UNKNOWN in immutable history;
> a new CONFIRMED_EXECUTED record is created. The audit chain is preserved."

#### F10 — State Drift

1. Inject **F10 — State Drift**
2. Start the analyze → approve → execute flow
3. Observe: the executor detects that warehouse state changed between snapshot
   and execution time — outcome is **CONFLICT**
4. Safety scorecard shows `stale_decisions_blocked: 1`

#### F12 — Circuit Open

1. Inject **F12 — Circuit Open** (simulates worker absence event)
2. Observe: Domain Health panel shows `labor: CIRCUIT OPEN`
3. Attempt to execute a labor action — it is blocked
4. The other domains (equipment, wave, inventory) remain **HEALTHY**
5. Narrate domain isolation: one domain's outage cannot affect others

---

## Part 3 — Reset

To run the demo again from a clean state:

1. Click **STOP** in the Demo Control Bar
2. Click **RESET** (if available) or simply click **START** on the same scenario
3. The simulation world re-initializes by reconstructing `DemoWarehouseWorld` from the immutable `WarehouseDataPack` + `ScenarioOverlay` sources — not from a YAML `initial_state` block or snapshot

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `[!!] maiw_api not importable` from preflight | Workspace packages not installed | `./scripts/install_packages.sh` |
| API starts but `/api/v1/health` returns 500 | `NVIDIA_API_KEY` invalid or missing | Check `.env` |
| Scenarios list is empty | YAML file not in `apps/api/maiw_api/demo/scenarios/` | Check filename and YAML syntax |
| Fault Injection panel not visible | `REACT_APP_FAULT_INJECTION_ENABLED` not set | Add to `src/ui/web/.env`, restart frontend |
| `NETWORK ERROR` in activity feed | Frontend proxy can't reach API on port 8001 | Ensure `start_demo_mode.sh` is running |
| Analysis returns DEFERRED | DecisionEngine detected stale state | Click RESET then START to get a fresh snapshot |
