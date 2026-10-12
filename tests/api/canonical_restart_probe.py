# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Separate-process restart probe for the canonical shipped app (v2.0.1, P1-03).

Each invocation is one *process lifetime* of ``maiw_api.app:app``: it enters the
real lifespan (bootstrap builds persistence from ``MAIW_PERSISTENCE_ROOT``),
does one thing through ``app.state.runtime.procedure_host`` / the app's own
HTTP routes, exits the lifespan and the interpreter. State can only carry over
between invocations through the durable store on disk.

    python -m tests.api.canonical_restart_probe start
    python -m tests.api.canonical_restart_probe govern <procedure_id> <revision>
    python -m tests.api.canonical_restart_probe replay <procedure_id> <revision>

Prints one JSON object on the last stdout line.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


async def _main(argv: list[str]) -> dict:
    import httpx

    from maiw_api.app import app
    from maiw_api.procedure_host import summarize
    from tests.api.canonical_harness import (
        FakeWaveWorld,
        ProofSopAExecutor,
        governance_input_for,
        proof_sop_a_inputs,
    )

    phase = argv[0]
    definition, sop, context = proof_sop_a_inputs(REPO_ROOT)
    out: dict = {"phase": phase}

    async with app.router.lifespan_context(app):
        rt = app.state.runtime
        host = rt.procedure_host
        out["store_backend"] = type(rt.procedure_store).__name__
        out["inbox_backend"] = type(rt.governance_inbox).__name__
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://c") as c:
            if phase == "start":
                executor = ProofSopAExecutor(fail_first=("establish_state",))
                state = await host.start(
                    definition=definition,
                    sop=sop,
                    agent_task_id="task-v201-restart",
                    context=context,
                    executor=executor,
                    warehouse_state_snapshot=FakeWaveWorld(),
                )
                out["state"] = summarize(state)
                out["executor_steps"] = executor.steps
            else:
                pid, revision = argv[1], int(argv[2])
                listed = await c.get("/api/v1/procedures")
                one = await c.get(f"/api/v1/procedures/{pid}")
                out["http_list_status"] = listed.status_code
                out["http_list"] = listed.json()
                out["http_get_status"] = one.status_code
                out["before"] = one.json()
                stored = await host.load(pid)
                # Rebuild the exact governance message for the paused revision.
                paused_view = stored.model_copy(update={"revision": revision})
                gov = governance_input_for(paused_view)
                world = FakeWaveWorld()
                world.resolve_risk(remaining=0)
                executor = ProofSopAExecutor()
                application = await host.apply_governance(
                    gov,
                    definition=definition,
                    sop=sop,
                    context=context,
                    executor=executor,
                    warehouse_state_snapshot=world,
                )
                out["applied"] = application.applied
                out["duplicate"] = application.duplicate
                final = application.state
                if application.applied:
                    final = await host.resume(
                        pid,
                        definition=definition,
                        sop=sop,
                        context=context,
                        executor=executor,
                        warehouse_state_snapshot=world,
                    )
                out["state"] = summarize(final)
                out["executor_steps"] = executor.steps
    return out


def main() -> None:
    result = asyncio.run(_main(sys.argv[1:]))
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
