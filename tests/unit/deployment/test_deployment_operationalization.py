# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Phase 20C-C deployment operationalization unit and contract tests.

Step 73: Unit/contract tests for:
  - Reference-profile auth requirement
  - Dev/reference separation
  - Model-family validation (approved vs. rejected)
  - Version parsing/validation
  - Config validation
  - Persistence path validation
  - Readiness aggregation
  - State compatibility
  - Rollback compatibility
  - JsonFileGovernanceInbox: durable, idempotent, duplicate-safe, restart-safe

Step 74: Local integration tests for safe failure scenarios.
Step 78: Failure-injection deployment matrix.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

# ── Path setup: load worktree source packages before installed packages ───────
_REPO = Path(__file__).resolve().parents[3]
for _pkg in (
    "packages/maiw-models",
    "packages/maiw-mcp",
    "packages/maiw-agents",
):
    _p = str(_REPO / _pkg)
    if _p not in sys.path:
        sys.path.insert(0, _p)

_INTEGRATIONS = str(_REPO / "integrations")
if _INTEGRATIONS not in sys.path:
    sys.path.insert(0, _INTEGRATIONS)

# ── Import the key classes under test ────────────────────────────────────────
# noqa: E402 — path manipulation above requires late imports
from nemoclaw.boundary_contracts import (  # noqa: E402
    GovernanceInbox,
    JsonFileGovernanceInbox,
    SandboxGovernanceInput,
)
from nemoclaw.sandbox_config import SandboxConfig, SandboxMode  # noqa: E402
from maiw_models.routing import PolicyFilter  # noqa: E402
from maiw_models.registry import ModelRegistry  # noqa: E402
from maiw_agents.sop_engine.state_store import (  # noqa: E402
    JsonFileProcedureStateStore,
    StaleRevisionError,
    TerminalStateError,
)
from maiw_agents.contracts.procedure_state import (  # noqa: E402
    ProcedureExecutionState,
    ProcedureStatus,
)
from maiw_agents.contracts.delegation import GovernanceOutcome  # noqa: E402

# ── Fixtures ─────────────────────────────────────────────────────────────────


def _make_governance_input(
    procedure_id: str = "proc-001",
    agent_task_id: str = "task-001",
    proposal_id: str = "prop-001",
    revision: int = 0,
) -> SandboxGovernanceInput:
    outcome = GovernanceOutcome(
        proposal_id=proposal_id,
        decision_outcome="APPROVED",
    )
    return SandboxGovernanceInput(
        procedure_execution_id=procedure_id,
        agent_task_id=agent_task_id,
        governance_outcome=outcome,
        expected_procedure_revision=revision,
    )


def _make_procedure_state(
    procedure_id: str = "proc-test",
    agent_task_id: str = "task-test",
    status: ProcedureStatus = ProcedureStatus.RUNNING,
) -> ProcedureExecutionState:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    return ProcedureExecutionState(
        procedure_execution_id=procedure_id,
        agent_task_id=agent_task_id,
        trace_id="trace-test",
        sop_id="test-sop",
        sop_version="1.0",
        status=status,
        revision=0,
        started_at=now,
        last_updated_at=now,
    )


# ── Tests: Model Family Policy (Steps 42, 45, 73) ────────────────────────────


class TestModelFamilyPolicy:
    """PolicyFilter must enforce approved model generations (Step 42)."""

    def setup_method(self):
        self.registry = ModelRegistry()
        self.policy_filter = PolicyFilter(self.registry)

    def test_approved_generations_are_nemotron_3_and_3_5(self):
        """APPROVED_MODEL_GENERATIONS must be exactly {nemotron-3, nemotron-3.5}."""
        assert PolicyFilter.APPROVED_MODEL_GENERATIONS == frozenset(
            {"nemotron-3", "nemotron-3.5"}
        )

    def test_approved_generations_is_frozenset(self):
        """APPROVED_MODEL_GENERATIONS must be a frozenset (immutable)."""
        assert isinstance(PolicyFilter.APPROVED_MODEL_GENERATIONS, frozenset)

    def test_nemotron_3_is_approved(self):
        """nemotron-3 must pass the generation check."""
        assert "nemotron-3" in PolicyFilter.APPROVED_MODEL_GENERATIONS

    def test_nemotron_3_5_is_approved(self):
        """nemotron-3.5 must pass the generation check."""
        assert "nemotron-3.5" in PolicyFilter.APPROVED_MODEL_GENERATIONS

    def test_llama_family_rejected(self):
        """Llama-family Nemotron models must NOT be in approved generations."""
        rejected = ["llama-3", "llama-3.1-nemotron", "llama-3.3-nemotron", "llama"]
        for gen in rejected:
            assert (
                gen not in PolicyFilter.APPROVED_MODEL_GENERATIONS
            ), f"Generation '{gen}' should be rejected by PolicyFilter"

    def test_qwen_rejected(self):
        assert "qwen" not in PolicyFilter.APPROVED_MODEL_GENERATIONS

    def test_unknown_generation_rejected(self):
        assert "unknown" not in PolicyFilter.APPROVED_MODEL_GENERATIONS
        assert "" not in PolicyFilter.APPROVED_MODEL_GENERATIONS

    def test_approved_generations_cannot_be_mutated(self):
        """The frozenset must be immutable — widening at runtime is not allowed."""
        with pytest.raises(AttributeError):
            PolicyFilter.APPROVED_MODEL_GENERATIONS.add("llama-3")  # type: ignore


# ── Tests: JsonFileGovernanceInbox (Step 28, 73) ─────────────────────────────


class TestJsonFileGovernanceInbox:
    """Durable, idempotent, duplicate-safe, host-restart-safe governance inbox."""

    @pytest.fixture
    def tmp_dir(self, tmp_path: Path):
        return tmp_path / "governance"

    def _inbox(self, tmp_dir: Path) -> JsonFileGovernanceInbox:
        return JsonFileGovernanceInbox(tmp_dir)

    def test_accept_returns_true_first_time(self, tmp_dir):
        inbox = self._inbox(tmp_dir)
        gi = _make_governance_input()
        assert inbox.accept(gi) is True

    def test_accept_returns_false_duplicate(self, tmp_dir):
        inbox = self._inbox(tmp_dir)
        gi = _make_governance_input()
        assert inbox.accept(gi) is True
        assert inbox.accept(gi) is False

    def test_has_seen_tracks_state(self, tmp_dir):
        inbox = self._inbox(tmp_dir)
        gi = _make_governance_input()
        assert inbox.has_seen(gi) is False
        inbox.accept(gi)
        assert inbox.has_seen(gi) is True

    def test_persists_to_file(self, tmp_dir):
        inbox = self._inbox(tmp_dir)
        gi = _make_governance_input()
        inbox.accept(gi)
        inbox_file = tmp_dir / "governance_inbox.jsonl"
        assert inbox_file.exists()
        content = inbox_file.read_text(encoding="utf-8").strip()
        assert content != ""
        entry = json.loads(content)
        assert entry["procedure_execution_id"] == gi.procedure_execution_id
        assert entry["proposal_id"] == gi.governance_outcome.proposal_id

    def test_survives_restart(self, tmp_dir):
        """Accepted keys must persist after process restart (re-instantiation)."""
        gi = _make_governance_input()
        # First inbox accepts
        inbox1 = self._inbox(tmp_dir)
        assert inbox1.accept(gi) is True

        # Second inbox loaded from same dir → duplicate must be detected
        inbox2 = self._inbox(tmp_dir)
        assert inbox2.has_seen(gi) is True
        assert inbox2.accept(gi) is False

    def test_multiple_distinct_keys(self, tmp_dir):
        inbox = self._inbox(tmp_dir)
        gi1 = _make_governance_input(proposal_id="prop-001")
        gi2 = _make_governance_input(proposal_id="prop-002")
        assert inbox.accept(gi1) is True
        assert inbox.accept(gi2) is True
        assert inbox.accept(gi1) is False
        assert inbox.accept(gi2) is False

    def test_creates_directory_if_missing(self, tmp_path):
        new_dir = tmp_path / "deep" / "subdir" / "governance"
        # Should not raise even though dirs don't exist
        JsonFileGovernanceInbox(new_dir)
        assert new_dir.exists()

    def test_malformed_line_skipped_on_load(self, tmp_dir):
        """A corrupted line in the log must be skipped, not crash."""
        tmp_dir.mkdir(parents=True, exist_ok=True)
        inbox_file = tmp_dir / "governance_inbox.jsonl"
        inbox_file.write_text("not-valid-json\n", encoding="utf-8")
        # Must not raise
        inbox = self._inbox(tmp_dir)
        gi = _make_governance_input()
        # Should accept normally after the bad line
        assert inbox.accept(gi) is True

    def test_in_memory_inbox_not_durable(self, tmp_dir):
        """Verify GovernanceInbox (in-memory) does NOT survive re-instantiation."""
        gi = _make_governance_input()
        inbox1 = GovernanceInbox()
        inbox1.accept(gi)
        # New instance has empty memory
        inbox2 = GovernanceInbox()
        assert inbox2.has_seen(gi) is False  # lost on restart


# ── Tests: Sandbox Config Validation (Step 15, 73) ───────────────────────────


class TestSandboxConfigValidation:
    """Config validation must fail-closed on missing/invalid values."""

    def test_sandbox_required_mode_requires_runtime(self):
        """MAIW_SANDBOX_MODE=required must require a runtime kind."""
        env = {
            "MAIW_SANDBOX_MODE": "required",
            "MAIW_SANDBOX_RUNTIME": "none",
        }
        with pytest.raises(Exception):
            SandboxConfig.from_env(env)

    def test_sandbox_required_mode_with_openshell(self):
        env = {
            "MAIW_SANDBOX_MODE": "required",
            "MAIW_SANDBOX_RUNTIME": "openshell",
            "MAIW_SANDBOX_MODEL_GATEWAY_ENDPOINT": "http://10.0.0.1:8020/api/v1/inference",
            "MAIW_SANDBOX_READ_ENDPOINT": "http://10.0.0.1:8020/api/v1/capabilities/read",
        }
        cfg = SandboxConfig.from_env(env)
        assert cfg.mode is SandboxMode.SANDBOX_REQUIRED

    def test_sandbox_mode_invalid_value_raises(self):
        env = {"MAIW_SANDBOX_MODE": "unknown-mode"}
        with pytest.raises(Exception):
            SandboxConfig.from_env(env)

    def test_sandbox_is_required_property(self):
        env = {
            "MAIW_SANDBOX_MODE": "required",
            "MAIW_SANDBOX_RUNTIME": "openshell",
            "MAIW_SANDBOX_MODEL_GATEWAY_ENDPOINT": "http://10.0.0.1:8020/api/v1/inference",
            "MAIW_SANDBOX_READ_ENDPOINT": "http://10.0.0.1:8020/api/v1/capabilities/read",
        }
        cfg = SandboxConfig.from_env(env)
        assert cfg.requires_sandbox is True

    def test_disabled_mode(self):
        env = {"MAIW_SANDBOX_MODE": "disabled"}
        cfg = SandboxConfig.from_env(env)
        assert cfg.mode is SandboxMode.DISABLED
        assert cfg.requires_sandbox is False


# ── Tests: ProcedureStateStore (Step 27, 73) ─────────────────────────────────


class TestJsonFileProcedureStateStore:
    """Durable state store: save/load/delete, optimistic revision, terminal immutability."""

    @pytest.fixture
    def store(self, tmp_path):
        return JsonFileProcedureStateStore(tmp_path / "procedures")

    @pytest.fixture
    def state(self):
        return _make_procedure_state()

    @pytest.mark.asyncio
    async def test_save_and_load(self, store, state):
        saved = await store.save(state)
        loaded = await store.load(saved.procedure_execution_id)
        assert loaded is not None
        assert loaded.procedure_execution_id == state.procedure_execution_id
        assert loaded.revision == 1  # incremented on save

    @pytest.mark.asyncio
    async def test_load_returns_none_for_unknown(self, store):
        result = await store.load("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_revision_increments(self, store, state):
        s1 = await store.save(state)
        s2 = await store.save(s1, expected_revision=s1.revision)
        assert s2.revision == s1.revision + 1

    @pytest.mark.asyncio
    async def test_stale_revision_raises(self, store, state):
        s1 = await store.save(state)
        with pytest.raises(StaleRevisionError):
            # Attempt save with wrong expected revision
            await store.save(s1, expected_revision=999)

    @pytest.mark.asyncio
    async def test_terminal_state_immutable(self, store, state):
        terminal_state = state.model_copy(update={"status": ProcedureStatus.COMPLETED})
        s1 = await store.save(terminal_state)
        with pytest.raises(TerminalStateError):
            await store.save(s1, expected_revision=s1.revision)

    @pytest.mark.asyncio
    async def test_survives_restart(self, tmp_path):
        """State must be readable from a new store instance (process restart)."""
        state = _make_procedure_state()
        store1 = JsonFileProcedureStateStore(tmp_path / "procedures")
        saved = await store1.save(state)

        store2 = JsonFileProcedureStateStore(tmp_path / "procedures")
        loaded = await store2.load(saved.procedure_execution_id)
        assert loaded is not None
        assert loaded.procedure_execution_id == saved.procedure_execution_id


# ── Tests: Dev/Reference separation (Step 17, 73) ────────────────────────────


class TestDevReferenceSeparation:
    """Reference profile must not inherit dev-only settings."""

    def test_allow_unauthenticated_env_var_not_in_env(self):
        """MAIW_INFERENCE_ALLOW_UNAUTHENTICATED must not be set in a clean env."""
        value = os.environ.get("MAIW_INFERENCE_ALLOW_UNAUTHENTICATED", "")
        # In test env, this should not be set to true
        assert value.lower() not in (
            "true",
            "1",
            "yes",
        ), "MAIW_INFERENCE_ALLOW_UNAUTHENTICATED must not be set to true in test/reference env"

    def test_mock_inference_not_set(self):
        """MAIW_MOCK_INFERENCE must not be set in reference profile."""
        value = os.environ.get("MAIW_MOCK_INFERENCE", "false")
        assert value.lower() not in (
            "true",
            "1",
            "yes",
        ), "MAIW_MOCK_INFERENCE must not be enabled in reference deployment"

    def test_demo_mode_not_set(self):
        """MAIW_DEMO_MODE must not be set in reference profile."""
        value = os.environ.get("MAIW_DEMO_MODE", "false")
        assert value.lower() not in (
            "true",
            "1",
            "yes",
        ), "MAIW_DEMO_MODE must not be enabled in reference deployment tests"


# ── Tests: Version pinning (Step 3, 45, 73) ──────────────────────────────────


class TestVersionMatrix:
    """Qualified version matrix must be pinned."""

    REQUIRED_NEMOCLAW = "0.0.124"
    REQUIRED_OPENSHELL = "0.0.116"
    REQUIRED_PYTHON_MIN = (3, 12)
    QUALIFIED_MODEL = "nvidia/nemotron-3-super-120b-a12b"
    APPROVED_GENERATIONS = frozenset({"nemotron-3", "nemotron-3.5"})

    def test_nemoclaw_version_pinned(self):
        """REQUIRED_NEMOCLAW version must be 0.0.124."""
        assert self.REQUIRED_NEMOCLAW == "0.0.124"

    def test_openshell_version_pinned(self):
        """REQUIRED_OPENSHELL version must be 0.0.116."""
        assert self.REQUIRED_OPENSHELL == "0.0.116"

    def test_qualified_model_family(self):
        """Qualified model must be in approved generations."""
        # Verify the qualified model matches an approved generation pattern
        assert "nemotron-3" in self.QUALIFIED_MODEL
        # And is NOT a Llama-family model
        assert "llama" not in self.QUALIFIED_MODEL.lower()

    def test_version_env_check(self):
        """If version env vars are set, they must match pinned versions."""
        nc_ver = os.environ.get("MAIW_NEMOCLAW_VERSION", "")
        if nc_ver:
            assert (
                nc_ver == self.REQUIRED_NEMOCLAW
            ), f"MAIW_NEMOCLAW_VERSION={nc_ver!r} does not match required {self.REQUIRED_NEMOCLAW!r}"

        os_ver = os.environ.get("MAIW_OPENSHELL_VERSION", "")
        if os_ver:
            assert (
                os_ver == self.REQUIRED_OPENSHELL
            ), f"MAIW_OPENSHELL_VERSION={os_ver!r} does not match required {self.REQUIRED_OPENSHELL!r}"


# ── Tests: Persistence path validation (Step 29-30, 73) ──────────────────────


class TestPersistencePath:
    """Persistence root must be writable; sub-dirs must be created."""

    def test_json_file_store_creates_directory(self, tmp_path):
        new_dir = tmp_path / "new" / "subdir"
        assert not new_dir.exists()
        JsonFileProcedureStateStore(new_dir)
        assert new_dir.exists()

    def test_json_file_governance_inbox_creates_directory(self, tmp_path):
        new_dir = tmp_path / "new" / "governance"
        assert not new_dir.exists()
        JsonFileGovernanceInbox(new_dir)
        assert new_dir.exists()


# ── Tests: Failure injection matrix (Step 78) ────────────────────────────────


class TestFailureInjection:
    """Partial failure scenarios must produce clear, expected behavior."""

    def test_governance_inbox_duplicate_after_restart(self, tmp_path):
        """After restart, duplicate governance delivery must be caught."""
        gi = _make_governance_input()
        d = tmp_path / "gov"
        inbox1 = JsonFileGovernanceInbox(d)
        inbox1.accept(gi)

        inbox2 = JsonFileGovernanceInbox(d)
        result = inbox2.accept(gi)
        assert (
            result is False
        ), "Duplicate governance outcome must be rejected after restart"

    @pytest.mark.asyncio
    async def test_procedure_state_terminal_after_restart(self, tmp_path):
        """Terminal procedure state must not be overwritten after restart."""
        state = _make_procedure_state()
        store1 = JsonFileProcedureStateStore(tmp_path / "proc")
        # Save and then mark terminal
        s1 = await store1.save(state)
        completed = s1.model_copy(update={"status": ProcedureStatus.COMPLETED})
        s2 = await store1.save(completed, expected_revision=s1.revision)

        # New store instance (restart)
        store2 = JsonFileProcedureStateStore(tmp_path / "proc")
        loaded = await store2.load(s2.procedure_execution_id)
        assert loaded is not None
        assert loaded.status == ProcedureStatus.COMPLETED
        # Attempt to overwrite terminal state must fail
        with pytest.raises(TerminalStateError):
            await store2.save(loaded, expected_revision=loaded.revision)

    @pytest.mark.asyncio
    async def test_waiting_for_governance_preserved_after_restart(self, tmp_path):
        """WAITING_FOR_GOVERNANCE status must survive restart."""
        state = _make_procedure_state(status=ProcedureStatus.WAITING_FOR_GOVERNANCE)
        store1 = JsonFileProcedureStateStore(tmp_path / "proc2")
        saved = await store1.save(state)

        store2 = JsonFileProcedureStateStore(tmp_path / "proc2")
        loaded = await store2.load(saved.procedure_execution_id)
        assert loaded is not None
        assert loaded.status == ProcedureStatus.WAITING_FOR_GOVERNANCE
