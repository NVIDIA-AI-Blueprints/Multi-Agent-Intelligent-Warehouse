# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Harness for the v2.0.1 canonical shipped-app suite.

Everything here drives the REAL release composition root,
``maiw_api.app:app``, through its REAL lifespan (``maiw_api.lifespan`` →
``maiw_api.bootstrap.get_runtime``). Nothing in the app is patched:

* the provider is a local fake OpenAI-compatible NIM HTTP server, reached by
  the real ``ModelGateway → PolicyFilter → ModelRouter → NIMProvider →
  NIMClient`` chain (the gateway singleton is pre-built with an ``NIMClient``
  whose base URL points at the fake, because ``NIMConfig`` reads its
  environment at import time);
* persistence is the real factory reading ``MAIW_PERSISTENCE_ROOT`` (a pytest
  tmp dir);
* the inference token is a fresh random value per test.

The fake provider records every request (never the Authorization value).
"""

from __future__ import annotations

import contextlib
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

APPROVED_GENERATIONS = {"nemotron-3", "nemotron-3.5"}
_UNSET = object()


class FakeNIM:
    """
    Threaded fake OpenAI-compatible endpoint on 127.0.0.1:<random port>.

    ``mode``:
        "ok"     200 chat.completion with ``content``
        "fail"   HTTP 500
        "empty"  200 with empty content
    A request whose ``Authorization`` is ``Bearer`` with no key gets 401,
    exactly like the real provider with a missing credential.
    """

    def __init__(self, content: str = "FAKE_NIM_OK") -> None:
        self.content = content
        self.mode = "ok"
        # v2.0.1 round 2: when set, the fake answers as THIS model instead of
        # echoing the requested one (provider model substitution).
        self.return_model: str | None = None
        # When True the response carries no ``model`` field at all.
        self.omit_model = False
        # v2.0.1 round 3: when not _UNSET, the ``model`` field is EXACTLY this
        # JSON value (e.g. "", "   ", 123, None, a list) — malformed identity.
        self.model_field: Any = _UNSET
        self.requests: list[dict[str, Any]] = []
        outer = self

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:  # silence
                return

            def _send(self, code: int, payload: dict[str, Any]) -> None:
                out = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def do_GET(self) -> None:  # noqa: N802
                self._send(200, {"object": "list", "data": []})

            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length)
                try:
                    body = json.loads(raw)
                except Exception:  # noqa: BLE001
                    body = {}
                auth = (self.headers.get("Authorization") or "").strip()
                outer.requests.append(
                    {
                        "path": self.path,
                        "model": body.get("model") if isinstance(body, dict) else None,
                        "auth_present": auth not in ("", "Bearer"),
                        "body": body,
                    }
                )
                if auth in ("", "Bearer"):
                    self._send(401, {"error": "missing credential"})
                    return
                if outer.mode == "fail":
                    self._send(500, {"error": "provider down"})
                    return
                content = "" if outer.mode == "empty" else outer.content
                payload = {
                    "id": "fake-1",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": outer.return_model or body.get("model", "unknown"),
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": content},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                    },
                }
                if outer.model_field is not _UNSET:
                    payload["model"] = outer.model_field
                if outer.omit_model:
                    payload.pop("model", None)
                self._send(200, payload)

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.port = self._server.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}/v1"
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def chat_requests(self) -> list[dict[str, Any]]:
        return [r for r in self.requests if r["path"].endswith("/chat/completions")]

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()


def canonical_env(
    monkeypatch: Any,
    tmp_path: Any,
    fake: FakeNIM,
    *,
    api_key: str = "fake-test-key-not-real",
    require_database: bool = False,
    persistence_root: Any | None = None,
) -> str:
    """
    Configure the process environment for one canonical-app test.

    Returns the fresh inference token (never printed).
    """
    token = secrets.token_urlsafe(32)
    root = persistence_root if persistence_root is not None else tmp_path / "maiw"
    env = {
        "MAIW_PERSISTENCE_ROOT": str(root),
        "MAIW_INFERENCE_INTERNAL_TOKEN": token,
        "MAIW_READINESS_REQUIRE_DATABASE": "true" if require_database else "false",
        "MAIW_DEMO_MODE": "false",
        "MAIW_STARTUP_TIMEOUT_SECONDS": "20",
        "LLM_NIM_URL": fake.base_url,
        "MAIW_NIM_BASE_URL": fake.base_url,
        "NVIDIA_API_KEY": api_key,
        "LLM_CACHE_ENABLED": "false",
        "REDIS_HOST": "127.0.0.1",
        "REDIS_PORT": "1",
        "MILVUS_HOST": "127.0.0.1",
        "MILVUS_PORT": "1",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    for key in (
        "MAIW_PERSISTENCE_MODE",
        "MAIW_PROCEDURE_STATE_DIR",
        "MAIW_GOVERNANCE_STATE_DIR",
        "MAIW_INFERENCE_ALLOW_UNAUTHENTICATED",
        "NEMOTRON_NANO_OMNI_ENABLED",
        "NEMOTRON_NANO_OMNI_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)
    # Same as CI: the legacy migration router reads DB config at import time.
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://warehouse:ci_placeholder@127.0.0.1:1/warehouse",
    )
    return token


def install_gateway(fake: FakeNIM, *, api_key: str = "fake-test-key-not-real") -> Any:
    """
    Pre-build the process ModelGateway singleton exactly as
    ``maiw_models.get_model_gateway`` does, but with an NIMClient whose
    config points at the fake provider. Registry/PolicyFilter/Router are real.
    """
    import maiw_models
    import maiw_models.providers.nim
    import maiw_models.providers.nim_client
    import maiw_models.router
    import maiw_models.telemetry

    nim_client = maiw_models.providers.nim_client
    maiw_models.reset_model_gateway()
    client = nim_client.NIMClient(
        config=nim_client.NIMConfig(
            llm_base_url=fake.base_url, llm_api_key=api_key, timeout=10
        ),
        enable_cache=False,
    )
    registry = maiw_models.ModelRegistry()
    gateway = maiw_models.ModelGateway(
        provider=maiw_models.providers.nim.NIMProvider(client),
        registry=registry,
        router=maiw_models.router.ModelRouter(registry),
        telemetry=maiw_models.telemetry.GatewayTelemetry(),
    )
    maiw_models._gateway_instance = gateway  # noqa: SLF001 — same as the factory
    return gateway


@contextlib.asynccontextmanager
async def running_canonical_app():
    """
    Start ``maiw_api.app:app`` with its real lifespan; yield (app, client).
    On exit the real shutdown path runs (closes NIM client, resets singletons).
    """
    import httpx

    from maiw_api.app import app
    from maiw_api.bootstrap import reset_runtime

    reset_runtime()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://canonical"
        ) as client:
            yield app, client


# ── Proof SOP A fixtures (mirrors tests/contract/test_sandbox_proof_sop_a.py) ──

SOP_A_RELATIVE = "agents/sops/operations_coordination/wave_risk_resolution.v2.yaml"

_SOP_A_FACTS: dict[str, Any] = {
    "wave_id": "wave-17",
    "at_risk_count": 3,
    "carrier_cutoff_minutes": 47,
    "primary_constraint": "labor",
}


class FakeWaveWorld:
    """Authoritative wave state; read-only source for the terminal predicate."""

    def __init__(self, *, at_risk_count: int = 3) -> None:
        self.at_risk_count = at_risk_count
        self.reads = 0

    def resolve_risk(self, *, remaining: int = 0) -> None:
        self.at_risk_count = remaining

    def model_dump(self) -> dict[str, Any]:
        self.reads += 1
        return {
            "warehouse_id": "wh-test",
            "waves": {
                "warehouse_id": "wh-test",
                "total_tasks": 12,
                "pending_count": 4,
                "in_progress_count": 3,
                "completed_count": 5,
                "at_risk_count": self.at_risk_count,
                "zones_active": ["ZONE-A"],
                "tasks": [],
            },
        }


class ProofSopAExecutor:
    """
    Stands in for the sandboxed runtime: fulfils one step per call, never
    decides completion, never writes. ``fail_first`` lists step ids whose first
    attempt returns output missing its schema fields (→ VALIDATION_FAILED →
    retry), so retry counters > 1 can be exercised across a restart.
    """

    RUNTIME_NAME = "deterministic"

    def __init__(self, *, fail_first: tuple[str, ...] = ()) -> None:
        self.steps: list[str] = []
        self.capabilities_invoked: list[str] = []
        self._fail_first = set(fail_first)

    async def execute_step(
        self, *, definition, step, procedure_state, context, attempt
    ):
        from datetime import datetime, timezone

        from maiw_agents.contracts.step_result import (
            EvidenceRef,
            StepResult,
            StepStatus,
        )

        now = datetime.now(timezone.utc)
        self.steps.append(step.id)
        if getattr(step, "skill_id", None):
            self.capabilities_invoked.append(step.skill_id)
        status = StepStatus.COMPLETED
        if step.action == "emit_recommended_action":
            status = StepStatus.WAITING_FOR_GOVERNANCE
        completion = step.completion
        output = (
            {f: _SOP_A_FACTS[f] for f in completion.schema_fields if f in _SOP_A_FACTS}
            if completion is not None and completion.schema_fields
            else {}
        )
        if step.id in self._fail_first and attempt == 1:
            output = {}
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
                    reference_id=context.trace_id or None,
                    timestamp=now,
                    summary=f"runtime fulfilled step {step.id!r}",
                    metadata={
                        "step_id": step.id,
                        "action": step.action,
                        "sop_id": procedure_state.sop_id,
                        "attempt": attempt,
                    },
                )
            ],
            metadata={"action": step.action, "sop_id": procedure_state.sop_id},
        )


def proof_sop_a_inputs(repo_root: Any) -> tuple[Any, Any, Any]:
    """(definition, sop, context) for Proof SOP A."""
    from maiw_agents.contracts.agent import AgentDefinition, GovernanceBoundary
    from maiw_agents.contracts.runtime import AgentExecutionContext
    from maiw_agents.contracts.sop import load_sop
    from maiw_agents.domain_predicates import register_all_domain_predicates

    register_all_domain_predicates()
    sop = load_sop(repo_root / SOP_A_RELATIVE)
    definition = AgentDefinition(
        agent_id="operations_coordination",
        version="1.0",
        objective="Resolve wave risk before carrier cutoff",
        domain="operations",
        allowed_capabilities=[
            "warehouse.wave.status",
            "warehouse.wave.inspect_tasks",
            "warehouse.wave.evaluate_reprioritization",
            "warehouse.wave.reprioritize",
        ],
        allowed_subagents=[],
        output_contract="RecommendedAction",
        governance_boundary=GovernanceBoundary(),
    )
    context = AgentExecutionContext(
        warehouse_id="wh-test",
        trace_id="trace-v201-canonical-sop-a",
        bounded_context={
            "wave_id": "wave-17",
            "at_risk_count": 3,
            "carrier_cutoff_minutes": 47,
            "primary_constraint": "labor",
            "domains_affected": "labor",
        },
    )
    return definition, sop, context


def governance_input_for(state: Any, *, proposal_id: str = "proposal-wave-17") -> Any:
    """The host's governance outcome for a paused procedure (APPROVED/EXECUTED)."""
    from maiw_agents.contracts.delegation import GovernanceOutcome

    from integrations.nemoclaw.boundary_contracts import SandboxGovernanceInput

    return SandboxGovernanceInput(
        procedure_execution_id=state.procedure_execution_id,
        agent_task_id=state.agent_task_id,
        governance_outcome=GovernanceOutcome(
            proposal_id=proposal_id,
            decision_outcome="APPROVED",
            execution_id="exec-wave-17",
            execution_status="EXECUTED",
            trace_id=state.trace_id,
        ),
        expected_procedure_revision=state.revision,
    )


__all__ = [
    "FakeWaveWorld",
    "ProofSopAExecutor",
    "proof_sop_a_inputs",
    "governance_input_for",
    "SOP_A_RELATIVE",
    "APPROVED_GENERATIONS",
    "FakeNIM",
    "canonical_env",
    "install_gateway",
    "running_canonical_app",
]
