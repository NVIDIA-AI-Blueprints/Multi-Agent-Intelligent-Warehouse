# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.0.1 round 3 — disposable equipment MCP backend for the ambiguous-write
regression tests and the live §40 proof.  Not a test module.

Runs the repository's OWN equipment MCP server module
(``mcp_servers.equipment.server``) over streamable HTTP, with a backend that:

* holds asset state in a JSON file, so the state survives a server crash /
  restart exactly like a real warehouse backend (the third re-audit's
  recorder used an in-memory mock, whose state was lost on crash);
* APPLIES each write (release → available, assign → assigned to the
  assignee) and appends every write to a JSONL log (the write count);
* obeys a one-shot control file read on every write:
      crash_after_write   apply + log the write, then os._exit(1) before the
                          response is sent (response lost, write landed)
      crash_before_write  log the attempt, then os._exit(1) without applying
                          (response lost, write NOT applied)
      hang_after_write    apply + log, then never answer (read timeout)

Usage:
    python round3_mcp_backend.py PORT STATE_FILE WRITE_LOG CONTROL_FILE
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from maiw_contracts.equipment import EquipmentAssetInfo  # noqa: E402
from mcp_servers.equipment import server as srv  # noqa: E402
from mcp_servers.equipment.provider import MockEquipmentProvider  # noqa: E402

SEED = [
    {
        "asset_id": "FL-01",
        "equipment_type": "forklift",
        "model": "r3-backend",
        "zone": "A",
        "status": "assigned",
        "owner_user": "J-17",
    },
    {
        "asset_id": "FL-02",
        "equipment_type": "forklift",
        "model": "r3-backend",
        "zone": "A",
        "status": "available",
        "owner_user": None,
    },
]


class DurableRecordingProvider(MockEquipmentProvider):
    def __init__(self, state_file: Path, write_log: Path, control: Path) -> None:
        super().__init__()
        self._state_file = state_file
        self._write_log = write_log
        self._control = control
        rows = json.loads(state_file.read_text()) if state_file.exists() else list(SEED)
        for row in rows:
            self.add_asset(EquipmentAssetInfo(**row))
        self._save()

    def _save(self) -> None:
        tmp = self._state_file.with_suffix(".tmp")
        tmp.write_text(
            json.dumps([a.model_dump(mode="json") for a in self._assets.values()])
        )
        os.replace(tmp, self._state_file)

    def _log(self, entry: dict) -> None:
        with self._write_log.open("a") as fh:
            fh.write(json.dumps({"t": time.time(), "pid": os.getpid(), **entry}) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    def _take_mode(self) -> str:
        try:
            mode = self._control.read_text().strip()
        except OSError:
            return ""
        if mode:
            self._control.unlink()
        return mode

    def _set(self, asset_id: str, **fields) -> None:
        asset = self._assets[asset_id]
        self._assets[asset_id] = asset.model_copy(update=fields)
        self._save()

    async def _write(self, name: str, request, apply, call):
        mode = self._take_mode()
        payload = request.model_dump(mode="json")
        if mode == "crash_before_write":
            self._log({"event": "write_received_not_applied", "write": name, **payload})
            os._exit(1)
        result = await call(request)
        apply()
        self._log({"event": "write_applied", "write": name, "mode": mode, **payload})
        if mode == "crash_after_write":
            os._exit(1)
        if mode == "hang_after_write":
            await asyncio.sleep(3600)
        return result

    async def execute_equipment_release(self, request):
        return await self._write(
            "execute_equipment_release",
            request,
            lambda: self._set(request.asset_id, status="available", owner_user=None),
            super().execute_equipment_release,
        )

    async def execute_equipment_assignment(self, request):
        return await self._write(
            "execute_equipment_assignment",
            request,
            lambda: self._set(
                request.asset_id, status="assigned", owner_user=request.assignee
            ),
            super().execute_equipment_assignment,
        )


def main() -> None:
    port = int(sys.argv[1])
    state_file, write_log, control = (Path(a) for a in sys.argv[2:5])
    srv.configure_server(DurableRecordingProvider(state_file, write_log, control))
    srv.mcp_server.run(
        "streamable-http", host="127.0.0.1", port=port, stateless_http=True
    )


if __name__ == "__main__":
    main()
