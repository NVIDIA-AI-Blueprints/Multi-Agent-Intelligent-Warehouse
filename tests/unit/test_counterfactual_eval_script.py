# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
scripts/counterfactual_eval.py: compare the two runs over the same window (#309).

The MAIW run used to stop one tick after recovery while the control run kept
going for all 30 ticks, and each run's area under the curve was summed over its
own ticks. The shorter MAIW run was credited with the area it never covered:
on the DC-47 DataPack the script reported a 49.1% backlog AUC reduction where
the shared six ticks gave 13.4%. The horizon table was also empty because
DataPack scenarios start the simulation clock at an offset and the checkpoints
were compared with the absolute clock.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "counterfactual_eval.py"

OFFSET = 5400  # labor_constraint_wave_risk: clock_offset_seconds


@pytest.fixture()
def cf():
    spec = importlib.util.spec_from_file_location("counterfactual_eval", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _snap(cf, tick: int, backlog: int, risk: float) -> dict:
    elapsed = OFFSET + tick * cf.TICK_SECONDS
    return {
        "tick": tick,
        "elapsed_seconds": elapsed,
        "scenario_seconds": elapsed - OFFSET,
        "kpis": {
            "pending_backlog": backlog,
            "wave_risk_score": risk,
            "wave_completion_pct": float(tick),
        },
    }


def _run(cf, rows: list[tuple[int, float]]) -> dict:
    traj = [_snap(cf, i + 1, b, r) for i, (b, r) in enumerate(rows)]
    return {
        "trajectory": traj,
        "recovery": None,
        "peak_backlog": max(b for b, _ in rows),
        "backlog_auc": cf._auc(traj, "pending_backlog", len(traj)),
        "wave_risk_auc": cf._auc(traj, "wave_risk_score", len(traj)),
    }


def test_auc_compares_only_the_ticks_both_runs_cover(cf):
    # Figures from the 2026-11-12 DataPack run: control ran 30 ticks, MAIW 6.
    control = _run(
        cf, [(42, 95.0)] * 3 + [(28, 95.0)] * 2 + [(19, 95.0)] + [(5, 95.0)] * 24
    )
    maiw = _run(
        cf, [(40, 95.0), (39, 95.0), (38, 95.0), (23, 0.0), (22, 0.0), (12, 0.0)]
    )

    cmp = cf.compute_comparison(control, maiw)

    assert cmp["auc_window_ticks"] == 6
    assert cmp["backlog_auc_control"] == 201 * cf.TICK_SECONDS
    assert cmp["backlog_auc_maiw"] == 174 * cf.TICK_SECONDS
    assert cmp["backlog_auc_reduction_pct"] == 13.4
    assert cmp["wave_risk_auc_reduction_pct"] == 50.0


def test_horizons_count_from_the_scenario_start(cf):
    run = _run(cf, [(10 - i // 3, 50.0) for i in range(30)])

    cmp = cf.compute_comparison(run, run)

    for h in cf.HORIZONS:
        row = cmp["at_horizon"][f"{h}s"]["wave_completion_pct"]
        assert row["control"] == float(h // cf.TICK_SECONDS)
        assert row["maiw"] == float(h // cf.TICK_SECONDS)
    md = cf.render_md(
        {
            "evaluated_at": "t",
            "scenario": "s",
            "horizon_seconds": 1800,
            "control": run,
            "maiw": {**run, "maiw_cycles": []},
            "comparison": cmp,
        }
    )
    horizon_table = md.split("## KPI AT FIXED HORIZONS")[1].split("## CONTROL")[0]
    backlog_rows = [l for l in horizon_table.splitlines() if "pending_backlog" in l]
    assert len(backlog_rows) == len(cf.HORIZONS)
    assert all("—" not in row for row in backlog_rows)
    assert "+    300s" in md  # trajectory shows seconds into the scenario


def test_scenario_start_reads_t0_clock_or_first_tick(cf):
    assert cf._scenario_start({"sim_time_seconds": OFFSET}, OFFSET + 60) == OFFSET
    assert cf._scenario_start({}, OFFSET + 60) == OFFSET


class _FakeApi:
    """Just enough of /api/v1/demo for run_maiw: recovery shows at tick 3."""

    def __init__(self, cf):
        self.cf = cf
        self.elapsed = OFFSET
        self.analyze_calls = 0

    def kpis(self) -> dict:
        tick = (self.elapsed - OFFSET) // self.cf.TICK_SECONDS
        return {
            "sim_time_seconds": self.elapsed,
            "pending_backlog": max(5, 40 - 5 * tick),
            "wave_risk_score": 95.0 if tick < 3 else 0.0,
            "wave_risk_level": "critical" if tick < 3 else "none",
            "wave_completion_pct": float(tick),
            "time_to_recovery_seconds": 60.0 if tick >= 3 else None,
        }

    def get(self, path: str) -> dict:
        assert path == "/demo/status"
        return {"active": True, "current_kpis": self.kpis(), "pending_approvals": []}

    def post(self, path: str, body: dict | None = None) -> dict:
        if path == "/demo/tick":
            self.elapsed += body["seconds"]
            return {"elapsed_seconds": self.elapsed}
        if path == "/demo/analyze":
            self.analyze_calls += 1
            return {"assessment": {"recommendations": [], "model_id": "fake"}}
        return {"status": {}}


def test_maiw_run_covers_the_whole_horizon_after_recovery(cf, monkeypatch):
    api = _FakeApi(cf)
    monkeypatch.setattr(cf, "get", api.get)
    monkeypatch.setattr(cf, "post", api.post)
    monkeypatch.setattr(cf.time, "sleep", lambda _s: None)

    maiw = cf.run_maiw()

    assert len(maiw["trajectory"]) == cf.MAX_TICKS
    assert maiw["recovery"]["detected_at_tick"] == 3
    assert maiw["trajectory"][-1]["scenario_seconds"] == cf.MAX_TICKS * cf.TICK_SECONDS
    assert api.analyze_calls <= cf.MAX_MAIW
