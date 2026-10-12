# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.0.1 live qualification: Proof SOP A through the canonical shipped app.

Every reasoning step of Proof SOP A (wave_risk_resolution.v2) is executed
INSIDE a real OpenShell sandbox, which calls POST /api/v1/inference on the
deployed canonical app (maiw_api.app:app started by
scripts/start_reference_deployment.sh) → ModelGateway → PolicyFilter →
approved Nemotron. The SOP Engine runs host-side in the ProcedureHost built
by maiw_api.app:app's own lifespan, writing to the same MAIW_PERSISTENCE_ROOT
the deployed instance reads; the deployed instance serves the procedure over
GET /api/v1/procedures (and keeps serving it across a restart).

    python scripts/qualification/live_canonical_proof_sop_a.py start
    python scripts/qualification/live_canonical_proof_sop_a.py govern <pid> <rev>
    python scripts/qualification/live_canonical_proof_sop_a.py replay <pid> <rev>

Environment: the live deployment env (MAIW_PERSISTENCE_ROOT, MAIW_API_PORT,
MAIW_SANDBOX_NAME, ...). The inference token is read from the file named by
MAIW_INFERENCE_TOKEN_FILE and passed to the sandbox on stdin only; it is never
printed, logged or placed in argv/env of the sandbox process.

v2.0.1 has no HTTP route that *starts* a procedure (no new features); this
harness drives the canonical ProcedureHost directly. The governance outcome
applied in `govern` is a host-side APPROVED/EXECUTED record for a simulated
wave world — no warehouse write is performed by this script.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

_SANDBOX_CALL = r"""
import json, sys, urllib.error, urllib.request
token = sys.stdin.readline().strip()
req = json.loads(sys.stdin.read())
r = urllib.request.Request(sys.argv[1] + "/api/v1/inference",
                           data=json.dumps(req).encode(), method="POST")
r.add_header("Content-Type", "application/json")
r.add_header("X-Maiw-Internal-Token", token)
try:
    resp = urllib.request.urlopen(r, timeout=170)
    print(json.dumps({"http": resp.status, "body": json.loads(resp.read().decode())}))
except urllib.error.HTTPError as e:
    print(json.dumps({"http": e.code, "body": e.read().decode()[:300]}))
"""

_STEP_FIELDS = {
    "establish_state": ["wave_id", "at_risk_count", "carrier_cutoff_minutes"],
    "diagnose": ["primary_constraint"],
}


def _sandbox_inference(request: dict) -> dict:
    sandbox = os.environ["MAIW_SANDBOX_NAME"]
    host = os.environ.get("MAIW_SANDBOX_HOST_IP", "10.185.115.61")
    base = f"http://{host}:{os.environ['MAIW_API_PORT']}"
    token = Path(os.environ["MAIW_INFERENCE_TOKEN_FILE"]).read_text().strip()
    proc = subprocess.run(
        [
            "openshell", "sandbox", "exec", "-n", sandbox, "--no-tty",
            "--timeout", "200", "--", "python3", "-c", _SANDBOX_CALL, base,
        ],
        input=token + "\n" + json.dumps(request),
        capture_output=True,
        text=True,
        timeout=240,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"sandbox exec failed rc={proc.returncode}: {proc.stderr[-300:]}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _parse_json(text: str) -> dict:
    text = (text or "").strip().strip("`")
    if text.lower().startswith("json"):
        text = text[4:]
    s, e = text.find("{"), text.rfind("}")
    return json.loads(text[s : e + 1]) if 0 <= s < e else {}


class SandboxNemotronExecutor:
    """Fulfils each SOP A step with one sandboxed inference call."""

    RUNTIME_NAME = "openshell-sandbox"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def execute_step(self, *, definition, step, procedure_state, context, attempt):
        from maiw_agents.contracts.step_result import EvidenceRef, StepResult, StepStatus

        facts = dict(context.bounded_context)
        fields = _STEP_FIELDS.get(step.id, [])
        instruction = (
            f"You are executing SOP step '{step.id}' ({step.action}) of the MAIW "
            f"wave risk resolution procedure. Facts: {json.dumps(facts)}. "
            + (
                f"Return ONLY a JSON object with exactly these keys: {fields}. "
                "Integers must be JSON numbers. primary_constraint must be one of "
                "labor | wave | equipment."
                if fields
                else "Return ONLY a JSON object with keys 'summary' (one sentence) "
                "and, for a recommendation, 'capability' and 'rationale'."
            )
        )
        request = {
            "task": f"wave_risk_resolution_v2.{step.id}",
            "messages": [{"role": "user", "content": instruction}],
            "reasoning": "high",
            "risk_level": "medium",
            "deadline_ms": 150000,
            "trace_id": context.trace_id,
            "agent_task_id": procedure_state.agent_task_id,
            "procedure_execution_id": procedure_state.procedure_execution_id,
            "step_execution_id": f"{step.id}-{attempt}",
        }
        resp = await asyncio.to_thread(_sandbox_inference, request)
        body = resp.get("body") if isinstance(resp.get("body"), dict) else {}
        route = body.get("route", {})
        self.calls.append(
            {
                "step": step.id,
                "http": resp.get("http"),
                "model_id": body.get("model_id"),
                "generation": route.get("generation"),
                "approved_family": route.get("approved_family"),
                "trace_id": body.get("trace_id"),
                "procedure_execution_id": body.get("procedure_execution_id"),
            }
        )
        now = datetime.now(timezone.utc)
        if resp.get("http") != 200:
            return StepResult(
                step_id=step.id, status=StepStatus.FAILED, output={},
                runtime=self.RUNTIME_NAME, attempt=attempt, started_at=now,
                completed_at=now, error=f"inference HTTP {resp.get('http')}",
            )
        parsed = _parse_json(body.get("content", ""))
        output = {f: parsed[f] for f in fields if f in parsed}
        status = (
            StepStatus.WAITING_FOR_GOVERNANCE
            if step.action == "emit_recommended_action"
            else StepStatus.COMPLETED
        )
        return StepResult(
            step_id=step.id,
            status=status,
            output=output,
            runtime=self.RUNTIME_NAME,
            attempt=attempt,
            started_at=now,
            completed_at=now,
            evidence=[
                EvidenceRef(
                    type="step_execution",
                    source=self.RUNTIME_NAME,
                    reference_id=body.get("trace_id") or None,
                    timestamp=now,
                    summary=f"sandbox inference fulfilled step {step.id!r}",
                    metadata={
                        "step_id": step.id,
                        "action": step.action,
                        "sop_id": procedure_state.sop_id,
                        "attempt": attempt,
                        "model_id": body.get("model_id"),
                        "generation": route.get("generation"),
                    },
                )
            ],
            metadata={"action": step.action, "sop_id": procedure_state.sop_id},
        )


async def _main(argv: list[str]) -> dict:
    import httpx

    from maiw_api.app import app
    from maiw_api.procedure_host import summarize
    from tests.api.canonical_harness import (
        FakeWaveWorld,
        governance_input_for,
        proof_sop_a_inputs,
    )

    phase = argv[0]
    definition, sop, context = proof_sop_a_inputs(REPO_ROOT)
    import dataclasses

    context = dataclasses.replace(context, trace_id="v201-live-proof-sop-a")
    deployed = f"http://127.0.0.1:{os.environ['MAIW_API_PORT']}"
    out: dict = {"phase": phase}

    async with app.router.lifespan_context(app):
        rt = app.state.runtime
        host = rt.procedure_host
        out["store_backend"] = type(rt.procedure_store).__name__
        out["store_dir"] = str(rt.persistence.config.procedures_dir)
        executor = SandboxNemotronExecutor()
        if phase == "start":
            state = await host.start(
                definition=definition,
                sop=sop,
                agent_task_id="v201-live-task-sop-a",
                context=context,
                executor=executor,
                warehouse_state_snapshot=FakeWaveWorld(),
            )
        else:
            pid, rev = argv[1], int(argv[2])
            stored = await host.load(pid)
            gov = governance_input_for(stored.model_copy(update={"revision": rev}))
            world = FakeWaveWorld()
            world.resolve_risk(remaining=0)
            application = await host.apply_governance(
                gov, definition=definition, sop=sop, context=context,
                executor=executor, warehouse_state_snapshot=world,
            )
            out["applied"], out["duplicate"] = application.applied, application.duplicate
            state = application.state
            if application.applied:
                state = await host.resume(
                    pid, definition=definition, sop=sop, context=context,
                    executor=executor, warehouse_state_snapshot=world,
                )
        out["state"] = summarize(state)
        out["sandbox_calls"] = executor.calls

    # What the DEPLOYED canonical instance serves for this procedure.
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"{deployed}/api/v1/procedures/{out['state']['procedure_execution_id']}"
        )
        out["deployed_app_view"] = {"http": r.status_code, "body": r.json()}
    return out


if __name__ == "__main__":
    print(json.dumps(asyncio.run(_main(sys.argv[1:])), default=str))
