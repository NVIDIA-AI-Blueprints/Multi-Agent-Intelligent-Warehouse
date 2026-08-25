#!/usr/bin/env python3
"""
Increment 3 — Deterministic Counterfactual Evaluation
======================================================
Runs the labor_constraint_wave_risk scenario twice against the same API:

  CONTROL  — same initial state, same timed events, ticks only (no MAIW)
  MAIW     — same initial state, same timed events, ticks + MAIW governance

Records per-tick KPIs for both runs and computes a comparison.

Label: Deterministic Counterfactual Simulation — same seed, same disruption,
       MAIW intervention vs no intervention.

Emits:
  artifacts/demo/labor_wave_control_vs_maiw.json
  artifacts/demo/labor_wave_control_vs_maiw.md
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_URL      = "http://localhost:8001/api/v1"
SCENARIO_NAME = "labor_constraint_wave_risk"
TICK_SECONDS  = 60
MAX_TICKS     = 30   # 1800 sim-seconds = 30 sim-minutes
MAX_MAIW      = 10   # safety cap on MAIW cycles
HORIZONS      = [300, 600, 900, 1200, 1800]  # fixed checkpoints (sim-seconds)
ARTIFACTS_DIR = Path(__file__).parent.parent / "artifacts" / "demo"


def get(path: str) -> dict:
    r = requests.get(f"{BASE_URL}{path}", timeout=30)
    r.raise_for_status()
    return r.json()


def post(path: str, body: dict | None = None) -> dict:
    r = requests.post(f"{BASE_URL}{path}", json=body or {}, timeout=120)
    r.raise_for_status()
    return r.json()


def fmt_kpis(k: dict) -> dict:
    return {
        "sim_time_seconds":          k.get("sim_time_seconds"),
        "clock_iso":                 k.get("clock_iso"),
        "pending_backlog":           k.get("pending_backlog"),
        "wave_risk_score":           k.get("wave_risk_score"),
        "wave_risk_level":           k.get("wave_risk_level"),
        "wave_completion_pct":       k.get("wave_completion_pct"),
        "simulated_throughput":      k.get("simulated_throughput"),
        "projected_service_level":   k.get("projected_service_level"),
        "labor_availability_pct":    k.get("labor_availability_pct"),
        "labor_utilization_pct":     k.get("labor_utilization_pct"),
        "equipment_operational_pct": k.get("equipment_operational_pct"),
        "time_to_recovery_seconds":  k.get("time_to_recovery_seconds"),
    }


def _reset_and_start():
    status_pre = get("/demo/status")
    if status_pre.get("active"):
        post("/demo/scenario/reset")
        time.sleep(0.3)
    resp = post(f"/demo/scenario/{SCENARIO_NAME}/start")
    return resp.get("status", {})


def _snapshot_at(horizon_s: int, trajectory: list[dict]) -> dict | None:
    """Return the KPI snapshot closest to the given sim-second horizon."""
    best = None
    for snap in trajectory:
        elapsed = snap.get("elapsed_seconds", 0)
        if elapsed <= horizon_s:
            best = snap
        else:
            break
    return best.get("kpis") if best else None


# ── Run CONTROL ───────────────────────────────────────────────────────────────

def run_control() -> dict:
    print("\n[counterfactual] ── CONTROL RUN (no MAIW) ──")
    start_status = _reset_and_start()
    t0_raw = (get("/demo/status").get("current_kpis") or {})
    t0 = fmt_kpis(t0_raw)
    print(f"  T=0  backlog={t0.get('pending_backlog')}  risk={t0.get('wave_risk_level','?').upper()}/{t0.get('wave_risk_score')}")

    trajectory: list[dict] = []
    recovery: dict | None = None

    for tick_num in range(1, MAX_TICKS + 1):
        tick_resp = post("/demo/tick", {"seconds": TICK_SECONDS})
        elapsed   = tick_resp.get("elapsed_seconds", 0)
        kpis_raw  = (get("/demo/status").get("current_kpis") or {})
        kpis      = fmt_kpis(kpis_raw)

        snap = {
            "tick":              tick_num,
            "elapsed_seconds":   elapsed,
            "kpis":              kpis,
        }

        ttr = kpis.get("time_to_recovery_seconds")
        if ttr is not None and recovery is None:
            recovery = {
                "detected_at_tick":      tick_num,
                "sim_time_seconds":      elapsed,
                "time_to_recovery_secs": ttr,
                "wave_risk_level":       kpis.get("wave_risk_level"),
                "wave_risk_score":       kpis.get("wave_risk_score"),
                "pending_backlog":       kpis.get("pending_backlog"),
                "wave_completion_pct":   kpis.get("wave_completion_pct"),
            }
            snap["recovery_detected"] = True

        trajectory.append(snap)
        bl  = kpis.get("pending_backlog", "?")
        lvl = (kpis.get("wave_risk_level") or "?").upper()
        wc  = kpis.get("wave_completion_pct", 0)
        print(f"  tick {tick_num:02d} | +{elapsed}s | {lvl:8s} backlog={bl} wave={wc:.0f}%")

    final_raw = (get("/demo/status").get("current_kpis") or {})

    # Aggregate metrics
    backlogs  = [s["kpis"].get("pending_backlog", 0) or 0 for s in trajectory]
    risk_vals = [s["kpis"].get("wave_risk_score", 0) or 0 for s in trajectory]

    return {
        "run_type":            "control",
        "t0_kpis":             t0,
        "final_kpis":          fmt_kpis(final_raw),
        "trajectory":          trajectory,
        "recovery":            recovery,
        "peak_backlog":        max(backlogs) if backlogs else 0,
        "peak_wave_risk_score": max(risk_vals) if risk_vals else 0,
        "backlog_auc":         sum(b * TICK_SECONDS for b in backlogs),
        "wave_risk_auc":       sum(r * TICK_SECONDS for r in risk_vals),
    }


# ── Run MAIW ─────────────────────────────────────────────────────────────────

def run_maiw() -> dict:
    print("\n[counterfactual] ── MAIW RUN (with governance) ──")
    start_status = _reset_and_start()
    t0_raw = (get("/demo/status").get("current_kpis") or {})
    t0 = fmt_kpis(t0_raw)
    print(f"  T=0  backlog={t0.get('pending_backlog')}  risk={t0.get('wave_risk_level','?').upper()}/{t0.get('wave_risk_score')}")

    trajectory: list[dict] = []
    recovery: dict | None = None
    maiw_cycles: list[dict] = []

    def _run_cycle(cycle_num: int):
        status_pre  = get("/demo/status")
        backlog_now = (status_pre.get("current_kpis") or {}).get("pending_backlog", 0)
        print(f"\n  [MAIW cycle {cycle_num}] backlog={backlog_now}")

        analyze_resp = post("/demo/analyze")
        assessment   = analyze_resp.get("assessment", {})

        pending = get("/demo/status").get("pending_approvals", [])
        approvals = []
        for pa in pending:
            ap = post("/demo/approve", {
                "pending_id": pa["pending_id"],
                "approved_by": "counterfactual_eval",
            })
            ok     = ap.get("ok", False)
            status = ap.get("status", "?")
            print(f"    {pa['capability']}  → {'OK' if ok else status}")
            approvals.append({"capability": pa["capability"], "ok": ok, "status": status})
            time.sleep(0.15)

        maiw_cycles.append({
            "cycle":       cycle_num,
            "trace_id":    analyze_resp.get("trace_id"),
            "severity":    assessment.get("severity"),
            "model_id":    assessment.get("model_id"),
            "approvals":   approvals,
        })

    # Cycle 1 at T=0 (allocates the 2 idle workers immediately)
    _run_cycle(1)

    for tick_num in range(1, MAX_TICKS + 1):
        tick_resp = post("/demo/tick", {"seconds": TICK_SECONDS})
        elapsed   = tick_resp.get("elapsed_seconds", 0)
        status_resp = get("/demo/status")
        kpis_raw  = (status_resp.get("current_kpis") or {})
        kpis      = fmt_kpis(kpis_raw)

        snap = {
            "tick":            tick_num,
            "elapsed_seconds": elapsed,
            "kpis":            kpis,
        }

        # Interleave: trigger another MAIW cycle when backlog > 0 and no pending approvals
        backlog = kpis_raw.get("pending_backlog", 0)
        no_pending = not status_resp.get("pending_approvals")
        if backlog > 0 and no_pending and len(maiw_cycles) < MAX_MAIW:
            _run_cycle(len(maiw_cycles) + 1)
            status_resp = get("/demo/status")
            kpis_raw    = (status_resp.get("current_kpis") or {})
            kpis        = fmt_kpis(kpis_raw)
            snap["kpis"] = kpis
            snap["maiw_cycle"] = len(maiw_cycles)

        ttr = kpis.get("time_to_recovery_seconds")
        if ttr is not None and recovery is None:
            recovery = {
                "detected_at_tick":      tick_num,
                "sim_time_seconds":      elapsed,
                "time_to_recovery_secs": ttr,
                "wave_risk_level":       kpis.get("wave_risk_level"),
                "wave_risk_score":       kpis.get("wave_risk_score"),
                "pending_backlog":       kpis.get("pending_backlog"),
                "wave_completion_pct":   kpis.get("wave_completion_pct"),
            }
            snap["recovery_detected"] = True

        trajectory.append(snap)
        bl  = kpis.get("pending_backlog", "?")
        lvl = (kpis.get("wave_risk_level") or "?").upper()
        wc  = kpis.get("wave_completion_pct", 0)
        mc  = f"  [MAIW cycle {snap['maiw_cycle']}]" if snap.get("maiw_cycle") else ""
        rc  = "  ◀ RECOVERY" if snap.get("recovery_detected") else ""
        print(f"  tick {tick_num:02d} | +{elapsed}s | {lvl:8s} backlog={bl} wave={wc:.0f}%{mc}{rc}")

        if recovery and tick_num >= recovery["detected_at_tick"] + 1:
            print("  Recovery confirmed — stopping MAIW tick loop.")
            break

    final_raw = (get("/demo/status").get("current_kpis") or {})

    backlogs  = [s["kpis"].get("pending_backlog", 0) or 0 for s in trajectory]
    risk_vals = [s["kpis"].get("wave_risk_score", 0) or 0 for s in trajectory]

    return {
        "run_type":             "maiw",
        "t0_kpis":              t0,
        "final_kpis":           fmt_kpis(final_raw),
        "trajectory":           trajectory,
        "recovery":             recovery,
        "maiw_cycles":          maiw_cycles,
        "peak_backlog":         max(backlogs) if backlogs else 0,
        "peak_wave_risk_score": max(risk_vals) if risk_vals else 0,
        "backlog_auc":          sum(b * TICK_SECONDS for b in backlogs),
        "wave_risk_auc":        sum(r * TICK_SECONDS for r in risk_vals),
    }


# ── Comparison metrics ────────────────────────────────────────────────────────

def compute_comparison(ctrl: dict, maiw: dict) -> dict:
    def at_horizon(run: dict, h: int) -> dict | None:
        snap = _snapshot_at(h, run["trajectory"])
        return snap

    horizon_comparison: dict = {}
    for h in HORIZONS:
        c_snap = at_horizon(ctrl, h)
        m_snap = at_horizon(maiw, h)
        horizon_comparison[f"{h}s"] = {
            "wave_risk_score":         {"control": c_snap.get("wave_risk_score") if c_snap else None,
                                        "maiw":    m_snap.get("wave_risk_score") if m_snap else None},
            "pending_backlog":         {"control": c_snap.get("pending_backlog") if c_snap else None,
                                        "maiw":    m_snap.get("pending_backlog") if m_snap else None},
            "wave_completion_pct":     {"control": c_snap.get("wave_completion_pct") if c_snap else None,
                                        "maiw":    m_snap.get("wave_completion_pct") if m_snap else None},
            "simulated_throughput":    {"control": c_snap.get("simulated_throughput") if c_snap else None,
                                        "maiw":    m_snap.get("simulated_throughput") if m_snap else None},
            "projected_service_level": {"control": c_snap.get("projected_service_level") if c_snap else None,
                                        "maiw":    m_snap.get("projected_service_level") if m_snap else None},
        }

    ctrl_ttr = (ctrl.get("recovery") or {}).get("time_to_recovery_secs")
    maiw_ttr = (maiw.get("recovery") or {}).get("time_to_recovery_secs")

    c_auc = ctrl["backlog_auc"]
    m_auc = maiw["backlog_auc"]
    auc_reduction = round((c_auc - m_auc) / max(c_auc, 1) * 100, 1) if c_auc else None

    cr_auc = ctrl["wave_risk_auc"]
    mr_auc = maiw["wave_risk_auc"]
    risk_auc_reduction = round((cr_auc - mr_auc) / max(cr_auc, 1) * 100, 1) if cr_auc else None

    return {
        "control_recovery_seconds":   ctrl_ttr,
        "maiw_recovery_seconds":      maiw_ttr,
        "recovery_delta_seconds":     (None if ctrl_ttr is None or maiw_ttr is None
                                       else round(ctrl_ttr - maiw_ttr, 1)),
        "control_never_recovered":    ctrl_ttr is None,
        "peak_backlog_control":       ctrl["peak_backlog"],
        "peak_backlog_maiw":          maiw["peak_backlog"],
        "backlog_auc_control":        c_auc,
        "backlog_auc_maiw":           m_auc,
        "backlog_auc_reduction_pct":  auc_reduction,
        "wave_risk_auc_control":      cr_auc,
        "wave_risk_auc_maiw":         mr_auc,
        "wave_risk_auc_reduction_pct": risk_auc_reduction,
        "at_horizon":                 horizon_comparison,
    }


# ── Markdown renderer ─────────────────────────────────────────────────────────

def render_md(result: dict) -> str:
    ctrl = result["control"]
    maiw = result["maiw"]
    cmp  = result["comparison"]
    lines = []

    lines.append(f"# Counterfactual Evaluation — {result['scenario']}")
    lines.append(f"\n> Deterministic Counterfactual Simulation — same seed, same disruption, MAIW intervention vs no intervention")
    lines.append(f"\nEvaluated: {result['evaluated_at']}  \nScenario: `{result['scenario']}`  \nHorizon: {result['horizon_seconds']}s ({result['horizon_seconds']//60} sim-min)  \n")

    # ── OUTCOME SUMMARY ──
    lines.append("## OUTCOME SUMMARY")
    lines.append("```")
    ctrl_rec = ctrl.get("recovery")
    maiw_rec = maiw.get("recovery")
    ctrl_ttr = ctrl_rec.get("time_to_recovery_secs") if ctrl_rec else None
    maiw_ttr = maiw_rec.get("time_to_recovery_secs") if maiw_rec else None

    lines.append("CONTROL")
    lines.append(f"  Recovery         : {'not reached within ' + str(result['horizon_seconds']) + 's horizon' if ctrl_ttr is None else str(ctrl_ttr) + 's (' + str(round(ctrl_ttr/60,1)) + ' sim-min)'}")
    lines.append(f"  Peak backlog     : {ctrl['peak_backlog']}")
    c300 = cmp["at_horizon"].get("300s", {}).get("wave_completion_pct", {})
    lines.append(f"  Wave compl @300s : {c300.get('control', '—')}")
    lines.append("")
    lines.append("MAIW")
    lines.append(f"  Recovery         : {'not reached' if maiw_ttr is None else str(maiw_ttr) + 's (' + str(round(maiw_ttr/60,1)) + ' sim-min)'}")
    lines.append(f"  Peak backlog     : {maiw['peak_backlog']}")
    lines.append(f"  Wave compl @300s : {c300.get('maiw', '—')}")
    lines.append(f"  MAIW cycles      : {len(maiw.get('maiw_cycles', []))}")
    lines.append("")
    lines.append("DELTA")
    if cmp.get("control_never_recovered") and maiw_ttr is not None:
        lines.append(f"  Recovery time    : MAIW recovered; Control did not")
    elif cmp.get("recovery_delta_seconds") is not None:
        lines.append(f"  Recovery time    : {cmp['recovery_delta_seconds']}s faster with MAIW")
    else:
        lines.append(f"  Recovery time    : neither run recovered within horizon")

    lines.append(f"  Backlog AUC      : {cmp.get('backlog_auc_reduction_pct', '—')}% reduction with MAIW")
    lines.append(f"  Wave risk AUC    : {cmp.get('wave_risk_auc_reduction_pct', '—')}% reduction with MAIW")
    lines.append("```")

    # ── HORIZON TABLE ──
    lines.append("\n## KPI AT FIXED HORIZONS")
    lines.append("```")
    lines.append(f"{'horizon':>8}  {'metric':>25}  {'control':>10}  {'maiw':>10}")
    lines.append("─" * 60)
    metrics = [
        ("pending_backlog",         "pending_backlog"),
        ("wave_risk_score",         "wave_risk_score"),
        ("wave_completion_pct",     "wave_completion %"),
        ("simulated_throughput",    "throughput (u/hr)"),
        ("projected_service_level", "proj_service %"),
    ]
    for h_key, h_data in cmp["at_horizon"].items():
        first = True
        for metric_key, metric_label in metrics:
            vals = h_data.get(metric_key, {})
            cv = vals.get("control")
            mv = vals.get("maiw")
            def _f(v):
                if v is None: return "—"
                if isinstance(v, float): return f"{v:.1f}"
                return str(v)
            h_label = h_key if first else ""
            lines.append(f"{h_label:>8}  {metric_label:>25}  {_f(cv):>10}  {_f(mv):>10}")
            first = False
        lines.append("")
    lines.append("```")

    # ── TRAJECTORY ──
    for run_key, run_label, traj in [("control", "CONTROL", ctrl["trajectory"]), ("maiw", "MAIW", maiw["trajectory"])]:
        lines.append(f"\n## {run_label} TRAJECTORY")
        lines.append("```")
        lines.append(f"{'tick':>4}  {'elapsed':>7}  {'risk_lv':>8}  {'risk_sc':>7}  {'backlog':>7}  {'wave_%':>6}  {'recov':>5}")
        lines.append("─" * 60)
        for snap in traj:
            k   = snap.get("kpis", {})
            rec = " ◀" if snap.get("recovery_detected") else ""
            mc  = f" [c{snap['maiw_cycle']}]" if snap.get("maiw_cycle") else ""
            lvl = (k.get("wave_risk_level") or "?").upper()[:4]
            lines.append(
                f"{snap['tick']:>4}  "
                f"+{snap['elapsed_seconds']:>6}s  "
                f"{lvl:>8}  "
                f"{str(k.get('wave_risk_score','?')):>7}  "
                f"{str(k.get('pending_backlog','?')):>7}  "
                f"{(k.get('wave_completion_pct') or 0):>5.1f}%"
                f"{mc}{rec}"
            )
        lines.append("```")

    lines.append(f"\n---\n*Evaluation wall time: {result.get('eval_duration_secs')}s*")
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    wall_start = datetime.now(tz=timezone.utc)

    print(f"[counterfactual] Scenario: {SCENARIO_NAME}")
    print(f"[counterfactual] Horizon:  {MAX_TICKS} ticks × {TICK_SECONDS}s = {MAX_TICKS * TICK_SECONDS}s sim-time")

    ctrl = run_control()
    maiw = run_maiw()
    cmp  = compute_comparison(ctrl, maiw)

    result = {
        "evaluated_at":    wall_start.isoformat(),
        "scenario":        SCENARIO_NAME,
        "horizon_seconds": MAX_TICKS * TICK_SECONDS,
        "tick_seconds":    TICK_SECONDS,
        "label":           "Deterministic Counterfactual Simulation — same seed, same disruption, MAIW intervention vs no intervention",
        "control":         ctrl,
        "maiw":            maiw,
        "comparison":      cmp,
        "eval_duration_secs": round(
            (datetime.now(tz=timezone.utc) - wall_start).total_seconds(), 1
        ),
    }

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = ARTIFACTS_DIR / "labor_wave_control_vs_maiw.json"
    md_path   = ARTIFACTS_DIR / "labor_wave_control_vs_maiw.md"
    json_path.write_text(json.dumps(result, indent=2, default=str))
    md_path.write_text(render_md(result))

    print(f"\n[counterfactual] Artifacts:")
    print(f"  {json_path}")
    print(f"  {md_path}")

    ctrl_ttr = (ctrl.get("recovery") or {}).get("time_to_recovery_secs")
    maiw_ttr = (maiw.get("recovery") or {}).get("time_to_recovery_secs")
    print(f"\n[counterfactual] CONTROL  recovery: {ctrl_ttr or 'NOT REACHED'}")
    print(f"[counterfactual] MAIW     recovery: {maiw_ttr or 'NOT REACHED'}")
    if cmp.get("backlog_auc_reduction_pct") is not None:
        print(f"[counterfactual] Backlog AUC reduction: {cmp['backlog_auc_reduction_pct']}%")
    if cmp.get("wave_risk_auc_reduction_pct") is not None:
        print(f"[counterfactual] Wave risk AUC reduction: {cmp['wave_risk_auc_reduction_pct']}%")


if __name__ == "__main__":
    try:
        main()
    except requests.exceptions.ConnectionError:
        print(f"ERROR: Cannot connect to {BASE_URL}", file=sys.stderr)
        print("Ensure: MAIW_DEMO_MODE=true env/bin/python -m uvicorn maiw_api.app:app --port 8001", file=sys.stderr)
        sys.exit(1)
