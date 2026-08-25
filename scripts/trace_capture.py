#!/usr/bin/env python3
"""
MAIW Hero Scenario Trace Capture
=================================
Runs a complete labor_constraint_wave_risk scenario through the MAIW pipeline
and captures the full trace: T=0 KPIs, MAIW analysis lifecycle, tick-by-tick
KPI trajectory, and recovery detection.

Emits:
  artifacts/demo/labor_constraint_wave_risk_trace.json
  artifacts/demo/labor_constraint_wave_risk_trace.md

Rule: this script is an observer/controller of the existing scenario.
It does not alter simulation state to produce an attractive trace.
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL       = "http://localhost:8001/api/v1"
SCENARIO_NAME  = "labor_constraint_wave_risk"
TICK_SECONDS   = 60          # seconds per tick (matches UI default)
MAX_TICKS      = 60          # maximum ticks before giving up (= 3600 sim-seconds)
ARTIFACTS_DIR  = Path(__file__).parent.parent / "artifacts" / "demo"

# ── Helpers ──────────────────────────────────────────────────────────────────

def get(path: str) -> dict:
    r = requests.get(f"{BASE_URL}{path}", timeout=30)
    r.raise_for_status()
    return r.json()


def post(path: str, body: dict | None = None) -> dict:
    r = requests.post(f"{BASE_URL}{path}", json=body or {}, timeout=120)
    r.raise_for_status()
    return r.json()


def fmt_kpis(k: dict) -> dict:
    """Pull the fields we care about from a KPI snapshot dict."""
    return {
        "sim_time_seconds":       k.get("sim_time_seconds"),
        "clock_iso":              k.get("clock_iso"),
        "labor_availability_pct": k.get("labor_availability_pct"),
        "labor_utilization_pct":  k.get("labor_utilization_pct"),
        "pending_backlog":        k.get("pending_backlog"),
        "wave_risk_score":        k.get("wave_risk_score"),
        "wave_risk_level":        k.get("wave_risk_level"),
        "wave_completion_pct":    k.get("wave_completion_pct"),
        "simulated_throughput":   k.get("simulated_throughput"),
        "projected_service_level": k.get("projected_service_level"),
        "equipment_operational_pct": k.get("equipment_operational_pct"),
        "state_freshness_seconds": k.get("state_freshness_seconds"),
        "time_to_recovery_seconds": k.get("time_to_recovery_seconds"),
    }


def kpi_row(label: str, k: dict) -> str:
    lvl = k.get("wave_risk_level", "—")
    score = k.get("wave_risk_score", "—")
    return (
        f"  labor_availability  : {k.get('labor_availability_pct', '—'):.1f}%\n"
        f"  labor_utilization   : {k.get('labor_utilization_pct', '—'):.1f}%\n"
        f"  pending_backlog     : {k.get('pending_backlog', '—')}\n"
        f"  wave_risk           : {lvl.upper()} / {score}\n"
        f"  wave_completion     : {k.get('wave_completion_pct', '—'):.1f}%\n"
        f"  simulated_throughput: {k.get('simulated_throughput', '—'):.1f} units/hr\n"
        f"  proj_service_level  : {k.get('projected_service_level', '—'):.1f}%\n"
        f"  equipment_oper      : {k.get('equipment_operational_pct', '—'):.1f}%\n"
        f"  sim_time            : {k.get('sim_time_seconds', '—')}s  clock={k.get('clock_iso', '—')}"
    )


# ── Main ─────────────────────────────────────────────────────────────────────

def run() -> dict:
    capture_wall_start = datetime.now(tz=timezone.utc)
    trace: dict = {
        "captured_at": capture_wall_start.isoformat(),
        "scenario": SCENARIO_NAME,
        "warehouse_id": "DC-47",
    }

    print(f"[trace] Starting {SCENARIO_NAME} (reset if needed)...")
    # Ensure a scenario is active before reset (reset 409s with no active scenario)
    status_pre = get("/demo/status")
    if status_pre.get("active"):
        post("/demo/scenario/reset")
        time.sleep(0.3)
    start_resp = post(f"/demo/scenario/{SCENARIO_NAME}/start")
    status = start_resp.get("status", {})
    scenario_meta = status.get("scenario") or {}
    trace["scenario_meta"] = scenario_meta

    print("[trace] Fetching T=0 KPI snapshot...")
    status_resp = get("/demo/status")
    t0_kpis_raw = status_resp.get("current_kpis") or {}
    t0_kpis = fmt_kpis(t0_kpis_raw)
    trace["t0_kpis"] = t0_kpis

    print(f"[trace] T=0 state:\n{kpi_row('T=0', t0_kpis_raw)}")

    # ── RUN MAIW (interleaved with ticks) ────────────────────────────────────
    # Cycle 1 runs immediately to allocate the 2 workers available at T=0.
    # After each tick, if backlog > 0 and no pending approvals, another cycle
    # runs — allowing workers freed by task completion (tick 5) to be allocated
    # to the remaining pending tasks.
    MAX_MAIW_CYCLES = 8   # safety cap across all phases
    maiw_cycles: list[dict] = []
    total_approval_results: list[dict] = []

    def _run_maiw_cycle(cycle_num: int) -> dict:
        """Run one MAIW analyze+approve cycle. Returns the cycle record."""
        status_pre_cycle = get("/demo/status")
        backlog_now = (status_pre_cycle.get("current_kpis") or {}).get("pending_backlog", 0)

        print(f"\n[trace] MAIW cycle {cycle_num} (backlog={backlog_now})...")
        maiw_wall_start = time.perf_counter()
        analyze_resp = post("/demo/analyze")
        maiw_wall_elapsed = time.perf_counter() - maiw_wall_start

        assessment = analyze_resp.get("assessment", {})
        timing     = analyze_resp.get("timing") or {}

        # Approve all pending actions from this cycle
        status_after = get("/demo/status")
        pending = status_after.get("pending_approvals", [])
        cycle_approvals: list[dict] = []
        for pa in pending:
            print(f"  approving: {pa['capability']} (pending_id={pa['pending_id'][:8]}...)")
            ap_resp = post("/demo/approve", {"pending_id": pa["pending_id"], "approved_by": "trace_capture_script"})
            ok = ap_resp.get("ok", False)
            status = ap_resp.get("status", "?")
            if not ok:
                print(f"    ↳ {status}: {ap_resp.get('reason', '')}")
            cycle_approvals.append({
                "pending_id": pa["pending_id"],
                "capability": pa["capability"],
                "result": ap_resp,
            })
            total_approval_results.append(cycle_approvals[-1])
            time.sleep(0.2)

        cycle_rec = {
            "cycle":          cycle_num,
            "trace_id":       analyze_resp.get("trace_id", "—"),
            "snapshot_id":    assessment.get("snapshot_id", "—"),
            "model_id":       assessment.get("model_id"),
            "severity":       assessment.get("severity"),
            "summary":        assessment.get("summary"),
            "recommendations_count": len(assessment.get("recommendations", [])),
            "approvals":      cycle_approvals,
            "timing":         timing,
            "maiw_wall_secs": round(maiw_wall_elapsed, 3),
        }
        maiw_cycles.append(cycle_rec)
        print(f"  → {len(cycle_approvals)} action(s) approved")

        # First cycle: store the full lifecycle for the trace artifact
        if cycle_num == 1:
            trace["trace_id"]       = analyze_resp.get("trace_id", "—")
            trace["snapshot_id"]    = assessment.get("snapshot_id", "—")
            trace["maiw_wall_secs"] = round(maiw_wall_elapsed, 3)

            lifecycle = analyze_resp.get("lifecycle", [])
            lc_by_phase: dict[str, list] = {}
            for rec_lc in lifecycle:
                ph = rec_lc.get("phase", "UNKNOWN")
                lc_by_phase.setdefault(ph, []).append(rec_lc)

            observe_rec  = (lc_by_phase.get("OBSERVE") or [{}])[-1]
            skill_recs   = lc_by_phase.get("SKILL", [])
            propose_recs = lc_by_phase.get("PROPOSE", [])
            decide_recs  = lc_by_phase.get("DECIDE", [])
            execute_recs = lc_by_phase.get("EXECUTE", [])

            trace["analysis"] = {
                "trace_id":    trace["trace_id"],
                "snapshot_id": assessment.get("snapshot_id"),
                "observe": {
                    "domains_assembled": observe_rec.get("domains", []),
                    "freshness":         observe_rec.get("freshness"),
                    "snapshot_id":       observe_rec.get("snapshot_id"),
                },
                "reason": {
                    "model_id":              assessment.get("model_id"),
                    "routing_rule":          assessment.get("routing_rule"),
                    "routing_reason":        assessment.get("routing_reason"),
                    "latency_ms":            assessment.get("latency_ms"),
                    "severity":              assessment.get("severity"),
                    "summary":               assessment.get("summary"),
                    "facts_observed":        assessment.get("facts_observed", []),
                    "domains_affected":      assessment.get("domains_affected", []),
                    "recommendations_count": len(assessment.get("recommendations", [])),
                },
                "recommendations":  assessment.get("recommendations", []),
                "skills_consulted": [s.get("capability") for s in skill_recs],
                "proposals":        propose_recs,
                "decisions":        decide_recs,
                "executions":       execute_recs,
                "pre_kpis":         fmt_kpis(analyze_resp.get("pre_kpis") or {}),
                "post_kpis":        fmt_kpis(analyze_resp.get("post_kpis") or {}),
                "kpi_delta":        analyze_resp.get("kpi_delta") or {},
                "timing":           timing,
            }

        return cycle_rec

    # Cycle 1: run immediately to allocate the 2 workers available at T=0
    _run_maiw_cycle(1)

    # ── TICK LOOP ────────────────────────────────────────────────────────────
    print("\n[trace] Beginning tick loop...")
    tick_trajectory: list[dict] = []
    recovery_event: dict | None = None
    recovery_sim_time: int | None = None

    for tick_num in range(1, MAX_TICKS + 1):
        tick_resp = post("/demo/tick", {"seconds": TICK_SECONDS})
        elapsed   = tick_resp.get("elapsed_seconds", 0)

        # Fetch fresh status with KPIs
        status_resp = get("/demo/status")
        kpis_raw    = status_resp.get("current_kpis") or {}
        kpis        = fmt_kpis(kpis_raw)

        snap = {
            "tick":               tick_num,
            "tick_seconds":       TICK_SECONDS,
            "cumulative_ticked":  tick_num * TICK_SECONDS,
            "elapsed_seconds":    elapsed,
            "kpis":               kpis,
        }

        # Interleave MAIW: if backlog remains and we have capacity, run another cycle.
        # Workers freed by completed tasks (task-001/002 finish at ~tick 5) become
        # available here before the next tick advances the clock further.
        backlog = kpis_raw.get("pending_backlog", 0)
        no_pending_approvals = not status_resp.get("pending_approvals")
        if backlog > 0 and no_pending_approvals and len(maiw_cycles) < MAX_MAIW_CYCLES:
            _run_maiw_cycle(len(maiw_cycles) + 1)
            # Re-fetch KPIs after the MAIW cycle mutated state
            status_resp = get("/demo/status")
            kpis_raw    = status_resp.get("current_kpis") or {}
            kpis        = fmt_kpis(kpis_raw)
            snap["kpis"] = kpis
            snap["maiw_cycle_run"] = len(maiw_cycles)

        # Check for recovery
        ttr = kpis.get("time_to_recovery_seconds")
        if ttr is not None and recovery_event is None:
            recovery_event = {
                "detected_at_tick":      tick_num,
                "sim_time_seconds":      elapsed,
                "time_to_recovery_secs": ttr,
                "wave_risk_level":       kpis.get("wave_risk_level"),
                "wave_risk_score":       kpis.get("wave_risk_score"),
                "pending_backlog":       kpis.get("pending_backlog"),
                "wave_completion_pct":   kpis.get("wave_completion_pct"),
            }
            snap["recovery_detected"] = True
            recovery_sim_time = elapsed

        tick_trajectory.append(snap)

        lvl   = kpis.get("wave_risk_level", "?").upper()
        bl    = kpis.get("pending_backlog", "?")
        wc    = kpis.get("wave_completion_pct", 0)
        recov = " ← RECOVERY" if recovery_event and snap.get("recovery_detected") else ""
        maiw_marker = f" [MAIW cycle {snap.get('maiw_cycle_run')}]" if snap.get("maiw_cycle_run") else ""
        print(f"  tick {tick_num:02d} | +{tick_num*TICK_SECONDS}s | wave={lvl:8s} backlog={bl} wave_compl={wc:.0f}%{maiw_marker}{recov}")

        # Stop at recovery (but only after giving it a tick to stabilize)
        if recovery_event and tick_num >= (recovery_event["detected_at_tick"] + 1):
            print("[trace] Recovery confirmed — stopping tick loop.")
            break

    trace["tick_trajectory"]  = tick_trajectory
    trace["recovery"]         = recovery_event
    trace["maiw_cycles"]      = maiw_cycles
    trace["approval_results"] = total_approval_results
    if "analysis" not in trace:
        trace["analysis"] = {}
    print(f"\n[trace] Total MAIW cycles: {len(maiw_cycles)}, approvals: {len(total_approval_results)}")

    # ── FINAL KPIs ───────────────────────────────────────────────────────────
    final_status = get("/demo/status")
    final_kpis_raw = final_status.get("current_kpis") or {}
    final_kpis = fmt_kpis(final_kpis_raw)
    trace["final_kpis"] = final_kpis

    # ── DELTA FROM DISRUPTION ────────────────────────────────────────────────
    def _delta(field: str) -> float | None:
        t0 = t0_kpis.get(field)
        fn = final_kpis.get(field)
        if t0 is None or fn is None:
            return None
        return round(fn - t0, 2)  # type: ignore[operator]

    trace["delta_from_disruption"] = {
        "pending_backlog":        _delta("pending_backlog"),
        "wave_risk_score":        _delta("wave_risk_score"),
        "wave_completion_pct":    _delta("wave_completion_pct"),
        "simulated_throughput":   _delta("simulated_throughput"),
        "projected_service_level": _delta("projected_service_level"),
        "labor_utilization_pct":  _delta("labor_utilization_pct"),
    }

    trace["capture_duration_secs"] = round(
        (datetime.now(tz=timezone.utc) - capture_wall_start).total_seconds(), 1
    )

    return trace


# ── Markdown renderer ─────────────────────────────────────────────────────────

def render_md(t: dict) -> str:
    an  = t.get("analysis", {})
    r   = an.get("reason", {})
    rec = an.get("recovery") or t.get("recovery") or {}
    pre = an.get("pre_kpis", {})
    pos = an.get("post_kpis", {})
    dlt = an.get("kpi_delta", {})
    tmg = an.get("timing", {})
    t0  = t.get("t0_kpis", {})
    fin = t.get("final_kpis", {})
    d   = t.get("delta_from_disruption", {})

    def pct(v) -> str:
        return f"{v:.1f}%" if v is not None else "—"

    def num(v, suffix="") -> str:
        if v is None:
            return "—"
        if isinstance(v, float):
            return f"{v:.1f}{suffix}"
        return f"{v}{suffix}"

    def risk_line(k: dict) -> str:
        return f"{k.get('wave_risk_level','—').upper()} / {num(k.get('wave_risk_score'))}"

    lines = []
    lines.append(f"# MAIW Trace — {t.get('scenario')}")
    lines.append(f"\nCaptured: {t.get('captured_at')}  \nWarehouse: `{t.get('warehouse_id')}`  \n")

    # ── SCENARIO ──
    meta = t.get("scenario_meta", {})
    lines.append("## SCENARIO")
    lines.append(f"```")
    lines.append(f"name         : {t.get('scenario')}")
    lines.append(f"display_name : {meta.get('display_name','—')}")
    lines.append(f"warehouse_id : {t.get('warehouse_id')}")
    lines.append(f"tags         : {', '.join(meta.get('tags', []))}")
    lines.append(f"```")

    # ── T=0 ──
    lines.append("\n## T=0 — DISRUPTED STATE")
    lines.append("```")
    lines.append(f"sim_time            : {t0.get('sim_time_seconds')}s  clock={t0.get('clock_iso','—')}")
    lines.append(f"labor_availability  : {pct(t0.get('labor_availability_pct'))}")
    lines.append(f"labor_utilization   : {pct(t0.get('labor_utilization_pct'))}")
    lines.append(f"pending_backlog     : {t0.get('pending_backlog','—')}")
    lines.append(f"wave_risk           : {risk_line(t0)}")
    lines.append(f"wave_completion     : {pct(t0.get('wave_completion_pct'))}")
    lines.append(f"simulated_throughput: {num(t0.get('simulated_throughput'))} units/hr")
    lines.append(f"proj_service_level  : {pct(t0.get('projected_service_level'))}")
    lines.append(f"equipment_oper      : {pct(t0.get('equipment_operational_pct'))}")
    lines.append("```")

    # ── RUN MAIW ──
    lines.append("\n## RUN MAIW")
    lines.append("```")
    lines.append(f"trace_id    : {t.get('trace_id','—')}")
    lines.append(f"snapshot_id : {t.get('snapshot_id','—')}")
    lines.append("```")

    # OBSERVE
    obs = an.get("observe", {})
    lines.append("\n### OBSERVE")
    lines.append("```")
    lines.append(f"domains_assembled : {obs.get('domains_assembled', '—')}")
    lines.append(f"snapshot_id       : {obs.get('snapshot_id','—')}")
    lines.append(f"freshness         : {obs.get('freshness','—')}")
    lines.append("```")

    # REASON
    lines.append("\n### REASON")
    lines.append("```")
    lines.append(f"model_id           : {r.get('model_id','—')}")
    lines.append(f"routing_rule       : {r.get('routing_rule','—')}")
    lines.append(f"routing_reason     : {r.get('routing_reason','—')}")
    lines.append(f"model_latency_ms   : {r.get('latency_ms','—')}")
    lines.append(f"severity           : {r.get('severity','—')}")
    lines.append(f"domains_affected   : {r.get('domains_affected','—')}")
    lines.append(f"recommendations    : {r.get('recommendations_count','—')}")
    lines.append(f"skills_consulted   : {an.get('skills_consulted','—')}")
    lines.append("```")

    # ASSESS
    lines.append("\n### ASSESS")
    lines.append(f"**Summary:** {r.get('summary','—')}\n")
    facts = r.get("facts_observed", [])
    if facts:
        lines.append("**Facts observed:**")
        for f in facts:
            lines.append(f"- {f}")

    # RECOMMEND
    recs = an.get("recommendations", [])
    if recs:
        lines.append("\n### RECOMMENDATIONS")
        for i, rec_item in enumerate(recs):
            lines.append(f"\n**rec[{i}]** `{rec_item.get('capability')}` → `{rec_item.get('target')}`")
            lines.append(f"- domain   : {rec_item.get('domain')}")
            lines.append(f"- priority : {rec_item.get('priority')}")
            lines.append(f"- objective: {rec_item.get('objective')}")
            lines.append(f"- rationale: {rec_item.get('rationale')}")

    # PROPOSE / DECIDE / EXECUTE
    for phase_key, phase_label in [("proposals", "PROPOSE"), ("decisions", "DECIDE"), ("executions", "EXECUTE")]:
        phase_recs_list = an.get(phase_key, [])
        if phase_recs_list:
            lines.append(f"\n### {phase_label}")
            lines.append("```")
            for pr in phase_recs_list:
                for k, v in pr.items():
                    if k not in ("trace_id", "phase"):
                        lines.append(f"{k}: {v}")
                lines.append("---")
            lines.append("```")

    # Pre/Post KPI snapshot
    lines.append("\n### PRE → POST KPI (analysis snapshot)")
    lines.append("```")
    lines.append(f"                        PRE      POST     Δ")
    fields_labels = [
        ("labor_availability_pct",  "labor_avail %  "),
        ("labor_utilization_pct",   "labor_util  %  "),
        ("pending_backlog",         "backlog        "),
        ("wave_risk_score",         "wave_risk score"),
        ("wave_completion_pct",     "wave_compl  %  "),
    ]
    for fld, lbl in fields_labels:
        pv = pre.get(fld)
        ov = pos.get(fld)
        dv = dlt.get(fld)
        lines.append(f"  {lbl}  {num(pv):>7}  {num(ov):>7}  {('+' if dv and dv > 0 else '')}{num(dv):>7}")
    lines.append("```")

    lines.append("\n### TIMING")
    lines.append("```")
    lines.append(f"time_to_detect_ms   : {tmg.get('time_to_detect_ms','—')}")
    lines.append(f"time_to_decision_ms : {tmg.get('time_to_decision_ms','—')}")
    lines.append(f"time_to_execution_ms: {tmg.get('time_to_execution_ms','—')}")
    lines.append("```")

    if t.get("approval_results"):
        lines.append("\n### OPERATOR APPROVAL")
        lines.append("```")
        for ar in t["approval_results"]:
            res = ar.get("result", {})
            # approve endpoint returns top-level ok/status/success/execution_id fields
            ok = res.get("ok", False)
            status = res.get("status", "—")
            success = res.get("success")
            exec_id = res.get("execution_id", "—")
            lines.append(f"capability   : {ar['capability']}")
            lines.append(f"outcome      : {'SUCCESS' if ok else 'FAILED'}  status={status}")
            lines.append(f"exec_success : {success}  exec_id={exec_id}")
            lines.append("---")
        lines.append("```")

    # ── TICK TRAJECTORY ──
    lines.append("\n## KPI TRAJECTORY")
    lines.append("```")
    lines.append(f"{'tick':>4}  {'sim_t':>6}  {'risk_level':>10}  {'risk_sc':>7}  {'backlog':>7}  {'wave_%':>6}  {'throughput':>10}  {'proj_svc':>8}")
    lines.append("─" * 75)
    for snap in t.get("tick_trajectory", []):
        k = snap.get("kpis", {})
        recov_marker = " ◀ RECOVERY" if snap.get("recovery_detected") else ""
        lines.append(
            f"{snap['tick']:>4}  "
            f"{snap.get('elapsed_seconds', 0):>6}  "
            f"{(k.get('wave_risk_level') or '?').upper():>10}  "
            f"{num(k.get('wave_risk_score')):>7}  "
            f"{str(k.get('pending_backlog','?')):>7}  "
            f"{num(k.get('wave_completion_pct')):>6}  "
            f"{num(k.get('simulated_throughput')):>10}  "
            f"{num(k.get('projected_service_level')):>8}{recov_marker}"
        )
    lines.append("```")

    # ── RECOVERY ──
    rv = t.get("recovery")
    lines.append("\n## RECOVERY")
    if rv:
        lines.append("```")
        lines.append(f"detected_at_tick    : {rv.get('detected_at_tick')}")
        lines.append(f"sim_time_seconds    : {rv.get('sim_time_seconds')}")
        lines.append(f"time_to_recovery    : {rv.get('time_to_recovery_secs')}s  ({round(rv.get('time_to_recovery_secs',0)/60,1)} sim-min)")
        lines.append(f"wave_risk_at_recov  : {(rv.get('wave_risk_level') or '—').upper()} / {rv.get('wave_risk_score')}")
        lines.append(f"backlog_at_recov    : {rv.get('pending_backlog')}")
        lines.append(f"wave_compl_at_recov : {pct(rv.get('wave_completion_pct'))}")
        lines.append("```")
    else:
        lines.append(f"No recovery detected within {MAX_TICKS} ticks ({MAX_TICKS * TICK_SECONDS}s sim-horizon).")

    # ── FINAL ──
    lines.append("\n## FINAL STATE")
    lines.append("```")
    lines.append(f"sim_time            : {fin.get('sim_time_seconds')}s  clock={fin.get('clock_iso','—')}")
    lines.append(f"labor_availability  : {pct(fin.get('labor_availability_pct'))}")
    lines.append(f"labor_utilization   : {pct(fin.get('labor_utilization_pct'))}")
    lines.append(f"pending_backlog     : {fin.get('pending_backlog','—')}")
    lines.append(f"wave_risk           : {risk_line(fin)}")
    lines.append(f"wave_completion     : {pct(fin.get('wave_completion_pct'))}")
    lines.append(f"simulated_throughput: {num(fin.get('simulated_throughput'))} units/hr")
    lines.append(f"proj_service_level  : {pct(fin.get('projected_service_level'))}")
    lines.append("```")

    # ── DELTA ──
    lines.append("\n## DELTA FROM DISRUPTION (T=0 → FINAL)")
    lines.append("```")
    delta_labels = [
        ("pending_backlog",         "backlog           "),
        ("wave_risk_score",         "wave_risk_score   "),
        ("wave_completion_pct",     "wave_completion % "),
        ("simulated_throughput",    "throughput (u/hr) "),
        ("projected_service_level", "proj_svc_level %  "),
        ("labor_utilization_pct",   "labor_util %      "),
    ]
    for fld, lbl in delta_labels:
        dv = d.get(fld)
        arrow = "↓" if dv is not None and dv < 0 else ("↑" if dv is not None and dv > 0 else " ")
        lines.append(f"  {lbl}  {arrow} {num(dv)}")
    lines.append("```")

    lines.append(f"\n---\n*Capture duration: {t.get('capture_duration_secs')}s wall time*")
    return "\n".join(lines)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        trace = run()
    except requests.exceptions.ConnectionError:
        print("ERROR: Cannot connect to API at", BASE_URL, file=sys.stderr)
        print("Ensure the MAIW API is running with MAIW_DEMO_MODE=true", file=sys.stderr)
        sys.exit(1)

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    json_path = ARTIFACTS_DIR / "labor_constraint_wave_risk_trace.json"
    md_path   = ARTIFACTS_DIR / "labor_constraint_wave_risk_trace.md"

    json_path.write_text(json.dumps(trace, indent=2, default=str))
    md_path.write_text(render_md(trace))

    print(f"\n[trace] Artifacts written:")
    print(f"  {json_path}")
    print(f"  {md_path}")

    rv = trace.get("recovery")
    if rv:
        ttr = rv.get("time_to_recovery_secs", 0)
        print(f"\n[trace] RECOVERY DETECTED — TTR={ttr}s ({ttr/60:.1f} sim-min)")
    else:
        print(f"\n[trace] No recovery within {MAX_TICKS} ticks ({MAX_TICKS * TICK_SECONDS}s horizon)")
