# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Canonical persistence factory for the shipped MAIW app (v2.0.1, P1-03).

This is the ONE place where the runtime decides how procedure state and the
governance dedupe ledger are stored. ``maiw_api.bootstrap`` calls
``build_persistence()`` exactly once while assembling ``MAIWRuntime``; nothing
else constructs a ProcedureStateStore or GovernanceInbox for the shipped app.

Profiles
--------
``file`` (default — the reference profile)
    ``JsonFileProcedureStateStore`` under ``<root>/procedures`` and
    ``JsonFileGovernanceInbox`` under ``<root>/governance``, where ``<root>`` is
    ``MAIW_PERSISTENCE_ROOT`` (default ``/var/lib/maiw``). Survives process
    restart on a single node. If the directories cannot be created or used the
    runtime records the failure and ``/api/v1/ready`` reports NOT_READY — the
    app never silently downgrades to memory.

``memory`` (development/test only — must be configured explicitly)
    ``MAIW_PERSISTENCE_MODE=memory`` selects ``InMemoryProcedureStateStore`` and
    the in-process ``GovernanceInbox``. Readiness reports ``durable: false``.

Environment
-----------
    MAIW_PERSISTENCE_MODE       file | memory            (default: file)
    MAIW_PERSISTENCE_ROOT       durable state root       (default: /var/lib/maiw)
    MAIW_PROCEDURE_STATE_DIR    override procedures dir  (default: <root>/procedures)
    MAIW_GOVERNANCE_STATE_DIR   override governance dir  (default: <root>/governance)

Package boundary
----------------
``JsonFileGovernanceInbox`` lives in ``integrations/nemoclaw`` (it is the host
side of the sandbox boundary). Canonical packages (``packages/*``) must not
import ``integrations``; the composition root may. That is why this factory is
here and not in ``maiw_agents``.
"""

from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

logger = logging.getLogger(__name__)

ENV_MODE = "MAIW_PERSISTENCE_MODE"
ENV_ROOT = "MAIW_PERSISTENCE_ROOT"
ENV_PROCEDURE_DIR = "MAIW_PROCEDURE_STATE_DIR"
ENV_GOVERNANCE_DIR = "MAIW_GOVERNANCE_STATE_DIR"

DEFAULT_ROOT = "/var/lib/maiw"
MODE_FILE = "file"
MODE_MEMORY = "memory"
_VALID_MODES = frozenset({MODE_FILE, MODE_MEMORY})

GOVERNANCE_INBOX_FILENAME = "governance_inbox.jsonl"


class PersistenceConfigurationError(ValueError):
    """The persistence environment is invalid (e.g. unknown mode)."""


@dataclass(frozen=True)
class PersistenceConfig:
    """Resolved persistence configuration. Built from the environment only."""

    mode: str
    root: Path | None
    procedures_dir: Path | None
    governance_dir: Path | None

    @property
    def durable(self) -> bool:
        return self.mode == MODE_FILE

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "PersistenceConfig":
        env = os.environ if environ is None else environ
        mode = (env.get(ENV_MODE) or MODE_FILE).strip().lower()
        if mode not in _VALID_MODES:
            raise PersistenceConfigurationError(
                f"{ENV_MODE}={mode!r} is not one of {sorted(_VALID_MODES)}"
            )
        if mode == MODE_MEMORY:
            return cls(mode=mode, root=None, procedures_dir=None, governance_dir=None)

        root = Path(env.get(ENV_ROOT) or DEFAULT_ROOT)
        procedures = Path(env.get(ENV_PROCEDURE_DIR) or (root / "procedures"))
        governance = Path(env.get(ENV_GOVERNANCE_DIR) or (root / "governance"))
        return cls(
            mode=mode,
            root=root,
            procedures_dir=procedures,
            governance_dir=governance,
        )

    def describe(self) -> dict[str, Any]:
        """Non-secret description for readiness/status output."""
        return {
            "mode": self.mode,
            "durable": self.durable,
            "root": str(self.root) if self.root else None,
            "procedures_dir": str(self.procedures_dir) if self.procedures_dir else None,
            "governance_dir": str(self.governance_dir) if self.governance_dir else None,
        }


@dataclass
class PersistenceRuntime:
    """What the composition root built. ``error`` is set when construction failed."""

    config: PersistenceConfig | None
    procedure_store: Any = None
    governance_inbox: Any = None
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (
            not self.errors
            and self.procedure_store is not None
            and self.governance_inbox is not None
        )


# ── Factories ─────────────────────────────────────────────────────────────────


def build_procedure_state_store(config: PersistenceConfig) -> Any:
    """Construct the ProcedureStateStore for ``config``."""
    from maiw_agents.sop_engine.state_store import (
        InMemoryProcedureStateStore,
        JsonFileProcedureStateStore,
    )

    if config.mode == MODE_MEMORY:
        return InMemoryProcedureStateStore()
    assert config.procedures_dir is not None
    return JsonFileProcedureStateStore(config.procedures_dir)


def build_governance_inbox(config: PersistenceConfig) -> Any:
    """Construct the governance dedupe ledger for ``config``."""
    from integrations.nemoclaw.boundary_contracts import (
        GovernanceInbox,
        JsonFileGovernanceInbox,
    )

    if config.mode == MODE_MEMORY:
        return GovernanceInbox()
    assert config.governance_dir is not None
    return JsonFileGovernanceInbox(config.governance_dir)


def build_persistence(environ: Mapping[str, str] | None = None) -> PersistenceRuntime:
    """
    Build the runtime's persistence. Never raises: failures are recorded on the
    returned object so readiness can report them (fail loud, not fail open).
    """
    try:
        config = PersistenceConfig.from_env(environ)
    except PersistenceConfigurationError as exc:
        logger.error("MAIW persistence: invalid configuration — %s", exc)
        return PersistenceRuntime(config=None, errors=[str(exc)])

    result = PersistenceRuntime(config=config)
    try:
        result.procedure_store = build_procedure_state_store(config)
    except Exception as exc:  # noqa: BLE001 — recorded, surfaced by /ready
        result.errors.append(f"procedure_store: {type(exc).__name__}: {exc}")
        logger.error("MAIW persistence: ProcedureStateStore unavailable — %s", exc)
    try:
        result.governance_inbox = build_governance_inbox(config)
    except Exception as exc:  # noqa: BLE001
        result.errors.append(f"governance_inbox: {type(exc).__name__}: {exc}")
        logger.error("MAIW persistence: GovernanceInbox unavailable — %s", exc)

    if config.mode == MODE_MEMORY:
        logger.warning(
            "MAIW persistence: %s=memory — procedure and governance state will NOT "
            "survive a restart (development/test profile only)",
            ENV_MODE,
        )
    else:
        logger.info(
            "MAIW persistence: file-backed (procedures=%s governance=%s)",
            config.procedures_dir,
            config.governance_dir,
        )
    return result


# ── Readiness probe ───────────────────────────────────────────────────────────


def _probe_directory(path: Path) -> dict[str, Any]:
    """
    Prove a directory is usable for durable state: it exists, it can be listed,
    and a file can be created, fsynced, read back and removed in it.
    """
    detail: dict[str, Any] = {"path": str(path)}
    try:
        if not path.exists():
            return {**detail, "status": "failed", "reason": "directory missing"}
        if not path.is_dir():
            return {**detail, "status": "failed", "reason": "not a directory"}
        entries = sum(1 for _ in path.iterdir())
        fd, tmp_name = tempfile.mkstemp(dir=str(path), prefix=".maiw-ready-", suffix=".probe")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write("ok")
                handle.flush()
                os.fsync(handle.fileno())
            with open(tmp_name, encoding="utf-8") as handle:
                if handle.read() != "ok":
                    return {**detail, "status": "failed", "reason": "read-back mismatch"}
        finally:
            Path(tmp_name).unlink(missing_ok=True)
        return {**detail, "status": "ready", "entries": entries}
    except Exception as exc:  # noqa: BLE001 — every failure is a readiness failure
        return {**detail, "status": "failed", "reason": f"{type(exc).__name__}: {exc}"}


def probe_persistence(persistence: PersistenceRuntime | None) -> dict[str, Any]:
    """
    Component-level readiness for procedure state and the governance inbox.

    Returns ``{"status": "ready"|"failed", "durable": bool, "procedure_store":
    {...}, "governance_inbox": {...}}``.
    """
    if persistence is None or persistence.config is None:
        errors = persistence.errors if persistence is not None else ["not constructed"]
        return {"status": "failed", "durable": False, "errors": errors}

    config = persistence.config
    out: dict[str, Any] = {"durable": config.durable, "mode": config.mode}

    if persistence.procedure_store is None:
        out["procedure_store"] = {"status": "failed", "reason": "not constructed"}
    elif config.mode == MODE_MEMORY:
        out["procedure_store"] = {"status": "ready", "backend": "memory"}
    else:
        out["procedure_store"] = {
            "backend": type(persistence.procedure_store).__name__,
            **_probe_directory(config.procedures_dir),  # type: ignore[arg-type]
        }

    if persistence.governance_inbox is None:
        out["governance_inbox"] = {"status": "failed", "reason": "not constructed"}
    elif config.mode == MODE_MEMORY:
        out["governance_inbox"] = {"status": "ready", "backend": "memory"}
    else:
        gov = {
            "backend": type(persistence.governance_inbox).__name__,
            **_probe_directory(config.governance_dir),  # type: ignore[arg-type]
        }
        ledger = config.governance_dir / GOVERNANCE_INBOX_FILENAME  # type: ignore[operator]
        if gov["status"] == "ready" and ledger.exists():
            try:
                with ledger.open("a", encoding="utf-8"):
                    pass
                with ledger.open(encoding="utf-8") as handle:
                    handle.read(1)
            except Exception as exc:  # noqa: BLE001
                gov = {**gov, "status": "failed", "reason": f"ledger: {exc}"}
        out["governance_inbox"] = gov

    if persistence.errors:
        out["errors"] = list(persistence.errors)

    healthy = (
        not persistence.errors
        and out["procedure_store"].get("status") == "ready"
        and out["governance_inbox"].get("status") == "ready"
    )
    out["status"] = "ready" if healthy else "failed"
    return out


__all__ = [
    "ENV_MODE",
    "ENV_ROOT",
    "ENV_PROCEDURE_DIR",
    "ENV_GOVERNANCE_DIR",
    "DEFAULT_ROOT",
    "MODE_FILE",
    "MODE_MEMORY",
    "PersistenceConfig",
    "PersistenceConfigurationError",
    "PersistenceRuntime",
    "build_procedure_state_store",
    "build_governance_inbox",
    "build_persistence",
    "probe_persistence",
]
