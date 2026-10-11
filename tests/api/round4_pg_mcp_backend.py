# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.0.1 round 4 — the SHIPPED equipment MCP server + PostgreSQL adapter as a
process, with an optional post-commit fault.  Not a test module.

Runs ``mcp_servers.equipment.server`` with its own default provider
(``_build_default_provider()`` → ``MAIWEquipmentAdapter`` →
``EquipmentAssetTools`` → PostgreSQL, configured by the standard ``PGHOST`` /
``PGPORT`` / ``POSTGRES_*`` environment) over streamable HTTP.  The only
addition is a thin fault layer driven by a one-shot control file, read on
every write:

    error_after_commit   run the real adapter write (the transaction
                         COMMITS), log it, then raise → MCP isError with no
                         disposition (the fourth re-audit's Case B on the
                         shipped stack)

Every committed write is appended (fsynced) to a JSONL log — the write count.

Usage:
    python round4_pg_mcp_backend.py PORT WRITE_LOG CONTROL_FILE
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mcp_servers.equipment import server as srv  # noqa: E402


class FaultLayer:
    """Delegates to the shipped provider; injects a fault AFTER a commit."""

    def __init__(self, inner, write_log: Path, control: Path) -> None:
        self._inner = inner
        self._write_log = write_log
        self._control = control

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def _take_mode(self) -> str:
        try:
            mode = self._control.read_text().strip()
        except OSError:
            return ""
        if mode:
            self._control.unlink()
        return mode

    def _log(self, entry: dict) -> None:
        with self._write_log.open("a") as fh:
            fh.write(json.dumps({"t": time.time(), "pid": os.getpid(), **entry}) + "\n")
            fh.flush()
            os.fsync(fh.fileno())

    async def _write(self, name: str, request):
        mode = self._take_mode()
        result = await getattr(self._inner, name)(request)  # COMMITTED here
        self._log(
            {
                "event": "write_committed",
                "write": name,
                "mode": mode,
                **request.model_dump(mode="json"),
            }
        )
        if mode == "error_after_commit":
            raise RuntimeError(
                "r4 backend: failure AFTER the PostgreSQL transaction committed"
            )
        return result

    async def execute_equipment_assignment(self, request):
        return await self._write("execute_equipment_assignment", request)

    async def execute_equipment_release(self, request):
        return await self._write("execute_equipment_release", request)

    async def execute_schedule_maintenance(self, request):
        return await self._write("execute_schedule_maintenance", request)


def main() -> None:
    port = int(sys.argv[1])
    write_log, control = Path(sys.argv[2]), Path(sys.argv[3])
    srv.configure_server(FaultLayer(srv._build_default_provider(), write_log, control))
    srv.mcp_server.run(
        "streamable-http", host="127.0.0.1", port=port, stateless_http=True
    )


if __name__ == "__main__":
    main()
