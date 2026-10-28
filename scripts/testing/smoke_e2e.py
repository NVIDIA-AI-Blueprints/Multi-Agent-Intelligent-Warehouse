#!/usr/bin/env python3
"""
Public end-to-end smoke test for the Compose deployment.

Runs against the deployment started by .github/workflows/main.yml (or any
local ``docker-compose.dev.yaml`` stack) using its own disposable fixture rows,
and verifies the OUTCOME of every call — the tool result, the database row it
changed, and a read-back through the domain's read tool.

    mcp-tools           inventory/equipment/labor/wave reads; equipment,
                        labor and wave writes; one certified NOT_APPLIED
    durability-create   governed write through the app API
                        (POST /api/v1/equipment/release) -> execution record
    durability-verify   after the backend restarts: the same execution record
                        is served back unchanged

Environment: POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB (database on
--pg-host:--pg-port) and, for the durability phases, MAIW_OPERATOR_WRITE_TOKEN.
Needs ``asyncpg``.  Exit status is non-zero on the first failed check.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_mcp_servers import DEFAULT_DOMAINS, call_tool  # noqa: E402

# Fields of an execution record that must survive a backend restart unchanged.
DURABLE_FIELDS = (
    "execution_id",
    "domain",
    "capability",
    "target",
    "proposal_id",
    "decision_id",
    "idempotency_key",
    "trace_id",
    "outcome",
    "started_at",
    "completed_at",
    "expected_effect",
)


class SmokeFailure(AssertionError):
    pass


def check(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeFailure(message)
    print(f"  ✅ {message}")


def _ids(run: str) -> dict[str, str]:
    tag = f"ci-smoke-{run}"
    return {
        "tag": tag,
        "sku": f"{tag.upper()}-SKU",
        "location": f"{tag.upper()}-LOC",
        "asset": f"{tag.upper()}-FL",
        "durable_asset": f"{tag.upper()}-DUR",
        "worker": tag.replace("-", "_"),
        "wave": f"{tag.upper()}-WAVE",
        "zone": f"{tag.upper()}-ZONE",
    }


async def _connect(args: argparse.Namespace):
    import asyncpg

    return await asyncpg.connect(
        host=args.pg_host,
        port=args.pg_port,
        user=os.environ.get("POSTGRES_USER", "warehouse"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
        database=os.environ.get("POSTGRES_DB", "warehouse"),
    )


def _tool(args, domain: str, name: str, **arguments) -> tuple[bool, Any]:
    is_error, payload = call_tool(
        args.mcp_host, DEFAULT_DOMAINS[domain], name, arguments
    )
    return is_error, payload


def _ok(args, domain: str, name: str, **arguments) -> dict:
    is_error, payload = _tool(args, domain, name, **arguments)
    if is_error or not isinstance(payload, dict) or payload.get("error"):
        raise SmokeFailure(f"{name} failed: {payload}")
    return payload


# ── mcp-tools ────────────────────────────────────────────────────────────────


async def mcp_tools(args: argparse.Namespace) -> None:
    ids = _ids(args.run_id)
    governance = {
        "proposal_id": f"{ids['tag']}-proposal",
        "decision_id": f"{ids['tag']}-decision",
    }
    conn = await _connect(args)
    try:
        await conn.execute(
            "INSERT INTO inventory_items (sku, name, quantity, location, reorder_point) "
            "VALUES ($1, 'CI smoke item', 42, $2, 5)",
            ids["sku"],
            ids["location"],
        )
        await conn.execute(
            "INSERT INTO equipment_assets (asset_id, type, model, zone, status) "
            "VALUES ($1, 'forklift', 'CI smoke', $2, 'available')",
            ids["asset"],
            ids["zone"],
        )
        await conn.execute(
            "INSERT INTO users (username, email, full_name, role, status, hashed_password) "
            "VALUES ($1, $2, 'CI smoke operator', 'operator', 'active', 'not-a-login')",
            ids["worker"],
            f"{ids['worker']}@ci.invalid",
        )
        task_ids = [
            await conn.fetchval(
                "INSERT INTO tasks (kind, status, payload) VALUES ('pick', 'pending', $1::jsonb) "
                "RETURNING id",
                json.dumps(
                    {"wave_id": ids["wave"], "zone": ids["zone"], "priority": "low"}
                ),
            )
            for _ in range(2)
        ]
        print(f"Fixtures: {ids['tag']} (tasks {task_ids})")

        print("inventory")
        item = _ok(args, "inventory", "warehouse.inventory.get", sku=ids["sku"])
        check(
            item.get("total_available") == 42,
            "inventory.get returns the fixture quantity (42)",
        )
        check(
            [loc.get("location_id") for loc in item.get("locations", [])]
            == [ids["location"]],
            "inventory.get returns the fixture location",
        )

        print("equipment")
        status = _ok(
            args, "equipment", "warehouse.equipment.get_status", asset_id=ids["asset"]
        )
        assets = {a["asset_id"]: a for a in status.get("equipment", [])}
        check(
            assets.get(ids["asset"], {}).get("status") == "available",
            "equipment.get_status: fixture asset available",
        )
        assigned = _ok(
            args,
            "equipment",
            "warehouse.equipment.assign",
            asset_id=ids["asset"],
            assignee=ids["worker"],
            **governance,
        )
        check(
            assigned.get("success") is True and assigned.get("assignment_id"),
            "equipment.assign reports success with an assignment_id",
        )
        row = await conn.fetchrow(
            "SELECT status, owner_user FROM equipment_assets WHERE asset_id = $1",
            ids["asset"],
        )
        check(
            row["status"] == "assigned" and row["owner_user"] == ids["worker"],
            "DB: asset status=assigned, owner_user=worker",
        )
        arow = await conn.fetchrow(
            "SELECT asset_id, assignee FROM equipment_assignments WHERE id = $1",
            int(assigned["assignment_id"]),
        )
        check(
            arow is not None
            and arow["asset_id"] == ids["asset"]
            and arow["assignee"] == ids["worker"],
            "DB: equipment_assignments row matches assignment_id",
        )
        status = _ok(
            args, "equipment", "warehouse.equipment.get_status", asset_id=ids["asset"]
        )
        asset = {a["asset_id"]: a for a in status.get("equipment", [])}.get(
            ids["asset"], {}
        )
        check(
            asset.get("status") == "assigned"
            and asset.get("owner_user") == ids["worker"],
            "equipment.get_status read-back shows the assignment",
        )

        print("labor")
        capacity = _ok(args, "labor", "warehouse.labor.get_capacity")
        check(
            ids["worker"] in [w["worker_id"] for w in capacity.get("workers", [])],
            "labor.get_capacity lists the fixture worker",
        )
        allocated = _ok(
            args,
            "labor",
            "warehouse.labor.allocate",
            warehouse_id="default",
            task_id=str(task_ids[0]),
            task_type="pick",
            worker_ids=[ids["worker"]],
            **governance,
        )
        check(
            allocated.get("success") is True and allocated.get("allocation_id"),
            "labor.allocate reports success with an allocation_id",
        )
        trow = await conn.fetchrow(
            "SELECT assignee, payload FROM tasks WHERE id = $1", task_ids[0]
        )
        record = json.loads(trow["payload"]).get("last_allocation", {})
        check(
            trow["assignee"] == ids["worker"]
            and record.get("allocation_id") == allocated["allocation_id"],
            "DB: task assignee and allocation record match",
        )
        allocation = _ok(
            args, "labor", "warehouse.labor.get_allocation", worker_id=ids["worker"]
        )
        check(
            [t["task_id"] for t in allocation.get("allocations", [])]
            == [str(task_ids[0])],
            "labor.get_allocation read-back shows exactly the allocated task",
        )
        is_error, rejected = _tool(
            args,
            "labor",
            "warehouse.labor.allocate",
            warehouse_id="default",
            task_id="999999999",
            task_type="pick",
            worker_ids=[ids["worker"]],
            **governance,
        )
        check(
            is_error
            and isinstance(rejected, dict)
            and rejected.get("execution_disposition") == "NOT_APPLIED"
            and rejected.get("rejection_code") == "NOT_FOUND",
            "labor.allocate on a missing task is a certified NOT_APPLIED (NOT_FOUND), not a success",
        )

        print("wave")
        wave = _ok(args, "wave", "warehouse.wave.get", wave_id=ids["wave"])
        check(
            wave.get("total_tasks") == 2
            and {t["priority"] for t in wave["tasks"]} == {"low"},
            "wave.get returns both fixture tasks at priority low",
        )
        risk = _ok(args, "wave", "warehouse.wave.get_risk", wave_id=ids["wave"])
        check(
            risk.get("total_task_count") == 2,
            "wave.get_risk evaluates the fixture wave",
        )
        updated = _ok(
            args,
            "wave",
            "warehouse.wave.reprioritize",
            warehouse_id="default",
            wave_id=ids["wave"],
            new_priority="critical",
            reason="CI smoke",
            **governance,
        )
        check(
            updated.get("success") is True and updated.get("tasks_updated") == 2,
            "wave.reprioritize reports 2 tasks updated",
        )
        priorities = await conn.fetch(
            "SELECT payload->>'priority' AS p FROM tasks WHERE id = ANY($1::int[])",
            task_ids,
        )
        check(
            [r["p"] for r in priorities] == ["critical", "critical"],
            "DB: both tasks now priority critical",
        )
        wave = _ok(args, "wave", "warehouse.wave.get", wave_id=ids["wave"])
        check(
            {t["priority"] for t in wave["tasks"]} == {"critical"},
            "wave.get read-back shows priority critical",
        )
    finally:
        await conn.close()


# ── durability ───────────────────────────────────────────────────────────────


def _api(
    args, method: str, path: str, body: dict | None = None, headers: dict | None = None
):
    request = urllib.request.Request(
        f"{args.api}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read().decode() or "null")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode()


async def durability_create(args: argparse.Namespace) -> None:
    token = os.environ.get("MAIW_OPERATOR_WRITE_TOKEN", "")
    if len(token) < 32:
        raise SmokeFailure(
            "MAIW_OPERATOR_WRITE_TOKEN is not set (>= 32 chars) for this run"
        )
    ids = _ids(args.run_id)
    conn = await _connect(args)
    try:
        await conn.execute(
            "INSERT INTO equipment_assets (asset_id, type, model, zone, status, owner_user) "
            "VALUES ($1, 'forklift', 'CI smoke', $2, 'assigned', $3)",
            ids["durable_asset"],
            ids["zone"],
            ids["worker"],
        )
        await conn.execute(
            "INSERT INTO equipment_assignments (asset_id, assignee, assignment_type) "
            "VALUES ($1, $2, 'task')",
            ids["durable_asset"],
            ids["worker"],
        )
        print(f"Fixture: {ids['durable_asset']} assigned to {ids['worker']}")

        status, body = _api(
            args,
            "POST",
            "/api/v1/equipment/release",
            {
                "asset_id": ids["durable_asset"],
                "released_by": ids["worker"],
                "notes": "CI durability",
            },
            {
                "X-Maiw-Operator-Token": token,
                "Idempotency-Key": f"{ids['tag']}-release",
            },
        )
        check(
            status == 200 and isinstance(body, dict),
            f"POST /api/v1/equipment/release -> 200 (got {status}: {str(body)[:300]})",
        )
        check(
            body.get("status") == "executed"
            and body.get("executed") is True
            and body.get("execution_id"),
            f"release approved and executed (status={body.get('status')})",
        )
        row = await conn.fetchrow(
            "SELECT status, owner_user FROM equipment_assets WHERE asset_id = $1",
            ids["durable_asset"],
        )
        check(
            row["status"] == "available" and row["owner_user"] is None,
            "DB: asset released (status=available, no owner)",
        )
        released = await conn.fetchval(
            "SELECT count(*) FROM equipment_assignments WHERE asset_id = $1 AND released_at IS NOT NULL",
            ids["durable_asset"],
        )
        check(released == 1, "DB: the assignment row is closed")
    finally:
        await conn.close()

    execution_id = body["execution_id"]
    status, record = _api(args, "GET", f"/api/v1/executions/{execution_id}")
    check(
        status == 200 and record.get("execution_id") == execution_id,
        "GET /api/v1/executions/{id} serves the new record",
    )
    check(
        record.get("domain") == "equipment"
        and record.get("target") == ids["durable_asset"],
        "execution record names the equipment domain and the asset",
    )
    Path(args.state_file).write_text(json.dumps(record, indent=2, sort_keys=True))
    print(f"Saved execution record {execution_id} to {args.state_file}")


async def durability_verify(args: argparse.Namespace) -> None:
    before = json.loads(Path(args.state_file).read_text())
    execution_id = before["execution_id"]
    status, after = _api(args, "GET", f"/api/v1/executions/{execution_id}")
    check(
        status == 200 and isinstance(after, dict),
        f"after restart GET /api/v1/executions/{execution_id} -> 200 (got {status})",
    )
    changed = [f for f in DURABLE_FIELDS if before.get(f) != after.get(f)]
    check(
        not changed,
        f"after restart the record is unchanged ({len(DURABLE_FIELDS)} fields compared; changed: {changed})",
    )
    print(f"  ℹ️  recovered_after_restart={after.get('recovered_after_restart')}")
    status, listing = _api(args, "GET", "/api/v1/executions?status=all")
    listed = (
        [e.get("execution_id") for e in (listing or {}).get("executions", [])]
        if status == 200
        else []
    )
    check(
        execution_id in listed,
        "after restart the record is listed by GET /api/v1/executions?status=all",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "phase", choices=("mcp-tools", "durability-create", "durability-verify")
    )
    parser.add_argument(
        "--run-id",
        default=(
            f"{os.environ['GITHUB_RUN_ID']}-{os.environ.get('GITHUB_RUN_ATTEMPT', '1')}"
            if os.environ.get("GITHUB_RUN_ID")
            else secrets.token_hex(4)
        ),
    )
    parser.add_argument("--pg-host", default="localhost")
    parser.add_argument("--pg-port", type=int, default=5435)
    parser.add_argument("--mcp-host", default="localhost")
    parser.add_argument("--api", default="http://localhost:8001")
    parser.add_argument("--state-file", default="durability_record.json")
    args = parser.parse_args(argv)
    phase = {
        "mcp-tools": mcp_tools,
        "durability-create": durability_create,
        "durability-verify": durability_verify,
    }[args.phase]
    try:
        asyncio.run(phase(args))
    except SmokeFailure as exc:
        print(f"  ❌ {exc}")
        return 1
    print(f"✅ {args.phase} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
