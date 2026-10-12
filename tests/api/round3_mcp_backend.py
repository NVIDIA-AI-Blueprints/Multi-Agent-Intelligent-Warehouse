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

  v2.0.1 round 4 (fourth re-audit NEW4-P1-01) — server-reported errors:
      error_after_write   apply + log, THEN raise a generic error → MCP
                          isError without a disposition (mutation applied)
      error_before_write  raise a generic error before applying → isError
                          without a disposition (nothing applied, but nothing
                          certified either)
      reject_not_applied  raise ``WriteNotApplied`` before applying → the
                          server's typed ``execution_disposition=NOT_APPLIED``
      malformed_after_write:<variant>
                          apply + log, then answer isError with a crafted /
                          malformed disposition (see ``MALFORMED``)
      soft_fail_after_write
                          apply + log, then answer a NON-error result with
                          ``success=false, outcome=failed`` and no disposition
      conflict_not_applied
                          no mutation; non-error ``outcome=conflict`` result
                          certified ``execution_disposition=NOT_APPLIED``

  v2.0.1 final pre-merge (fifth re-audit NEW5-P2-01) — contradictory
  NOT_APPLIED claims (see ``CONTRADICTORY``):
      contradict_after_write:<variant>
                          apply + log, then answer with a crafted result that
                          claims ``execution_disposition=NOT_APPLIED`` but
                          contradicts it (error or non-error result)
      contradict_before_write:<variant>
                          no mutation; the same crafted contradictory answer

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
from maiw_mcp.errors import WriteNotApplied  # noqa: E402
from mcp_servers.equipment import server as srv  # noqa: E402
from mcp_servers.equipment.provider import MockEquipmentProvider  # noqa: E402

# Round 4: crafted isError structuredContent variants (None = no structuredContent).
MALFORMED = {
    "no_structured": None,
    "no_field": {"error": "boom"},
    "null": {"execution_disposition": None},
    "int": {"execution_disposition": 1},
    "bool": {"execution_disposition": True},
    "list": {"execution_disposition": ["NOT_APPLIED"]},
    "nested": {"execution_disposition": {"value": "NOT_APPLIED"}},
    "lowercase": {"execution_disposition": "not_applied"},
    "padded": {"execution_disposition": " NOT_APPLIED"},
    "unknown_value": {"execution_disposition": "REJECTED_BEFORE_MUTATION"},
    "applied": {"execution_disposition": "APPLIED"},
    "wrong_key": {"disposition": "NOT_APPLIED"},
    "text_only_claim": None,  # the TEXT claims NOT_APPLIED; structuredContent absent
}


_CLEAN_ERROR = {
    "execution_disposition": "NOT_APPLIED",
    "rejection_code": "PRECONDITION_FAILED",
    "message": "r5 backend: rejected",
}


def _clean_result(echo: dict) -> dict:
    """A canonical non-error NOT_APPLIED write result for ``echo`` (the request)."""
    return {
        "success": False,
        "proposal_id": echo.get("proposal_id"),
        "decision_id": echo.get("decision_id"),
        "execution_id": echo.get("execution_id"),
        "outcome": "failed",
        "execution_disposition": "NOT_APPLIED",
        "source": "r5-backend",
        "message": "r5 backend: rejected",
    }


# Final pre-merge: variant -> (is_error, build(echo) -> structuredContent).
# A–D of the spec: each one CLAIMS NOT_APPLIED and contradicts it.
CONTRADICTORY = {
    # error result (isError=true) + NOT_APPLIED + …
    "err_A_executed_true": (True, lambda e: {**_CLEAN_ERROR, "executed": True}),
    "err_B_rows_affected": (True, lambda e: {**_CLEAN_ERROR, "rows_affected": 1}),
    "err_C_success_post_state": (
        True,
        lambda e: {
            **_CLEAN_ERROR,
            "success": True,
            "post_state": {"asset_id": e.get("asset_id"), "status": "available"},
        },
    ),
    "err_C_fifth_audit_exact": (
        True,
        lambda e: {
            "execution_disposition": "NOT_APPLIED",
            "mutation_status": "applied",
            "outcome": "executed",
            "rejection_code": "BOGUS",
        },
    ),
    "err_D_code_missing": (
        True,
        lambda e: {"execution_disposition": "NOT_APPLIED", "message": "x"},
    ),
    "err_D_code_unknown": (True, lambda e: {**_CLEAN_ERROR, "rejection_code": "BOGUS"}),
    "err_D_code_lowercase": (
        True,
        lambda e: {**_CLEAN_ERROR, "rejection_code": "precondition_failed"},
    ),
    "err_D_code_not_string": (True, lambda e: {**_CLEAN_ERROR, "rejection_code": 409}),
    "err_D_unknown_field": (True, lambda e: {**_CLEAN_ERROR, "detail": "x"}),
    # non-error result + NOT_APPLIED + …
    "ok_A_executed_true": (False, lambda e: {**_clean_result(e), "executed": True}),
    "ok_B_rows_affected": (False, lambda e: {**_clean_result(e), "rows_affected": 2}),
    "ok_B_tasks_updated": (False, lambda e: {**_clean_result(e), "tasks_updated": 3}),
    "ok_B_mutation_reference": (
        False,
        lambda e: {**_clean_result(e), "assignment_id": 41},
    ),
    "ok_C_fifth_audit_success_true_failed": (
        False,
        lambda e: {**_clean_result(e), "success": True},
    ),
    "ok_C_success_true_executed": (
        False,
        lambda e: {**_clean_result(e), "success": True, "outcome": "executed"},
    ),
    "ok_C_post_state": (
        False,
        lambda e: {
            **_clean_result(e),
            "post_state": {"asset_id": e.get("asset_id"), "status": "available"},
        },
    ),
    "ok_D_code_unknown": (
        False,
        lambda e: {**_clean_result(e), "rejection_code": "BOGUS"},
    ),
    "ok_D_unknown_field": (
        False,
        lambda e: {**_clean_result(e), "mutation_status": "x"},
    ),
}


class _RawResult(Exception):
    """Raised by the provider; turned into a crafted CallToolResult below."""

    def __init__(self, variant: str, echo: dict) -> None:
        super().__init__(variant)
        self.variant = variant
        self.echo = echo


class _RawToolError(Exception):
    """Raised by the provider; turned into a crafted isError result below."""

    def __init__(self, variant: str) -> None:
        super().__init__(variant)
        self.variant = variant


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
        if mode == "error_before_write":
            self._log({"event": "write_received_not_applied", "write": name, **payload})
            raise RuntimeError("r4 backend: generic failure BEFORE any mutation")
        if mode == "reject_not_applied":
            self._log({"event": "write_rejected_not_applied", "write": name, **payload})
            raise WriteNotApplied(
                "r4 backend: precondition failed before any mutation",
                rejection_code="PRECONDITION_FAILED",
            )
        if mode.startswith("contradict_before_write:"):
            self._log({"event": "write_received_not_applied", "write": name, **payload})
            raise _RawResult(mode.split(":", 1)[1], payload)
        if mode == "conflict_not_applied":
            self._log({"event": "write_rejected_not_applied", "write": name, **payload})
            result = await call(request)
            return result.model_copy(
                update={
                    "success": False,
                    "outcome": "conflict",
                    "execution_disposition": "NOT_APPLIED",
                }
            )
        result = await call(request)
        apply()
        self._log({"event": "write_applied", "write": name, "mode": mode, **payload})
        if mode == "crash_after_write":
            os._exit(1)
        if mode == "hang_after_write":
            await asyncio.sleep(3600)
        if mode == "error_after_write":
            raise RuntimeError(
                "r4 backend: failure AFTER the mutation was applied "
                "(e.g. audit-row insert failed)"
            )
        if mode.startswith("contradict_after_write:"):
            raise _RawResult(mode.split(":", 1)[1], payload)
        if mode.startswith("malformed_after_write:"):
            raise _RawToolError(mode.split(":", 1)[1])
        if mode == "soft_fail_after_write":
            return result.model_copy(update={"success": False, "outcome": "failed"})
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


def _install_raw_error_results() -> None:
    """Round 4: answer ``_RawToolError`` with a crafted isError CallToolResult;
    final pre-merge: answer ``_RawResult`` with a crafted contradictory one."""
    from mcp.types import CallToolResult, TextContent

    original = srv.mcp_server.call_tool

    async def call_tool(name, arguments, context=None, **kwargs):
        try:
            return await original(name, arguments, context, **kwargs)
        except Exception as exc:  # noqa: BLE001 - inspect the cause chain
            cur = exc
            while cur is not None and not isinstance(cur, (_RawToolError, _RawResult)):
                cur = cur.__cause__ or cur.__context__
            if cur is None:
                raise
            if isinstance(cur, _RawResult):
                is_error, build = CONTRADICTORY[cur.variant]
                body = build(cur.echo)
                text = json.dumps(body)
                return CallToolResult(
                    content=[TextContent(type="text", text=text)],
                    # a non-error result keeps the write tools' declared output
                    # schema (the JSON string wrapped as {"result": ...})
                    structured_content=body if is_error else {"result": text},
                    is_error=is_error,
                )
            text = (
                json.dumps({"execution_disposition": "NOT_APPLIED"})
                if cur.variant == "text_only_claim"
                else "r4 backend: failure AFTER the mutation was applied"
            )
            return CallToolResult(
                content=[TextContent(type="text", text=text)],
                structured_content=MALFORMED[cur.variant],
                is_error=True,
            )

    srv.mcp_server.call_tool = call_tool


def main() -> None:
    port = int(sys.argv[1])
    state_file, write_log, control = (Path(a) for a in sys.argv[2:5])
    srv.configure_server(DurableRecordingProvider(state_file, write_log, control))
    _install_raw_error_results()
    srv.mcp_server.run(
        "streamable-http", host="127.0.0.1", port=port, stateless_http=True
    )


if __name__ == "__main__":
    main()
