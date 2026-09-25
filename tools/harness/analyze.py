"""Analyze one harness run dir -> <run_dir>/analysis.json + analysis.txt (UTF-8).

usage: python analyze.py <run_dir>

Reads: driver_out.json, rtdb_ops.jsonl, firestore_ops.jsonl, state.json,
stdout.log, stderr.log, launcher_exit.txt, TRIPWIRE_HIT.txt, UNIMPLEMENTED.txt.
Console output is ASCII only.
"""
import json
import os
import re
import sys
from typing import Any, Dict, List

sys.dont_write_bytecode = True
HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
if HARNESS_DIR not in sys.path:
    sys.path.append(HARNESS_DIR)
import harness_common as C  # noqa: E402

BUFFER_WINDOW_S = 2.0            # omada_ingest_service.BUFFER_WINDOW_S
HOLD_S = 10.0                    # settings.POSITION_EXACT_HOLD_SECONDS default
GUARD_PATH = "/positions/test-128-guard"
WORKER_PATH = "/positions/test-128-worker"


def _read(path: str) -> str:
    if not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        return f.read().decode("utf-8", "replace")


def _jsonl(path: str) -> List[Dict[str, Any]]:
    out = []
    for ln in _read(path).splitlines():
        ln = ln.strip()
        if ln:
            try:
                out.append(json.loads(ln))
            except Exception:
                pass
    return out


def _phase_of(t: float, phases: List[Dict[str, Any]]) -> str:
    for p in phases:
        if p["t_start"] <= t <= (p["t_end"] or 1e18):
            return f"{p['scenario']}/{p['phase']}"
    return "between/idle"


def analyze(run_dir: str) -> Dict[str, Any]:
    drv = json.loads(_read(os.path.join(run_dir, "driver_out.json")) or "{}")
    phases = drv.get("phases", [])
    reqs = drv.get("requests", [])
    rtdb = _jsonl(os.path.join(run_dir, "rtdb_ops.jsonl"))
    fsops = _jsonl(os.path.join(run_dir, "firestore_ops.jsonl"))
    stderr = _read(os.path.join(run_dir, "stderr.log"))
    stdout = _read(os.path.join(run_dir, "stdout.log"))
    state = json.loads(_read(os.path.join(run_dir, "state.json")) or "{}")
    exit_code = _read(os.path.join(run_dir, "launcher_exit.txt")).strip()
    A: Dict[str, Any] = {"run_dir": run_dir}
    checks: Dict[str, Any] = {}

    # ── status codes ────────────────────────────────────────────────────────
    by: Dict[str, Dict[str, int]] = {}
    for r in reqs:
        k = f"{r['scenario']}/{r['phase']}"
        by.setdefault(k, {})
        by[k][str(r["status"])] = by[k].get(str(r["status"]), 0) + 1
    A["status_by_phase"] = by
    A["request_count"] = len(reqs)

    # ── guard /positions writes ───────────────────────────────────────────────
    def pos_writes(path):
        ws = []
        for o in rtdb:
            if o.get("op") == "set" and o.get("path") == path:
                v = o.get("value") or {}
                ws.append({"t": o["t"], "phase": _phase_of(o["t"], phases), "thread": o.get("thread"),
                           "is_approximate": v.get("is_approximate"), "x": v.get("x"), "y": v.get("y"),
                           "anchor_ap_mac": v.get("anchor_ap_mac"), "radius_m": v.get("radius_m"),
                           "timestamp": v.get("timestamp"), "floor_id": v.get("floor_id")})
        return ws

    gw = pos_writes(GUARD_PATH)
    A["guard_writes"] = gw
    A["worker_writes"] = pos_writes(WORKER_PATH)

    def ph(scn, name):
        for p in phases:
            if p["scenario"] == scn and p["phase"] == name:
                return p
        return None

    # solve
    p_solve = ph("solve", "full3")
    if p_solve:
        ws = [w for w in gw if p_solve["t_start"] <= w["t"] <= p_solve["t_end"] + 0.5]
        exact = [w for w in ws if w["is_approximate"] is False]
        checks["solve"] = {
            "statuses": by.get("solve/full3"),
            "writes_in_phase": len(ws), "exact_writes": len(exact),
            "approx_writes": len(ws) - len(exact),
            "last_write": ws[-1] if ws else None,
            "last_is_exact": bool(ws and ws[-1]["is_approximate"] is False),
            "last_exact_err_m": (round(((exact[-1]["x"] - 8.0) ** 2 + (exact[-1]["y"] - 6.0) ** 2) ** 0.5, 3)
                                 if exact else None),
        }

    # rssinull
    p_null = ph("rssinull", "single_post")
    if p_null:
        rr = [r for r in reqs if r["scenario"] == "rssinull"]
        tb_attr = re.findall(r"AttributeError: 'NoneType' object has no attribute 'get'", stderr)
        m = re.findall(r'File "([^"]*omada_ingest_service\.py)", line (\d+), in (\w+)\s*\n\s*(.+)', stderr)
        checks["rssinull"] = {
            "status": rr[0]["status"] if rr else None,
            "json": rr[0]["json"] if rr else None,
            "stderr_attributeerror_count": len(tb_attr),
            "stderr_ingest_frames": sorted({(os.path.basename(f), int(ln), fn, src.strip()) for f, ln, fn, src in m}),
            "worker_writes_after": [w for w in A["worker_writes"] if w["t"] >= p_null["t_start"]],
        }

    # hold / fallback
    p_f3, p_12, p_1, p_w = (ph("holdfallback", n) for n in ("full3", "ap12_hold", "ap1_fallback", "ap1_weak_-95"))
    if p_f3 and p_12 and p_1 and p_w:
        f3_ap3 = [r for r in reqs if r["scenario"] == "holdfallback" and r["phase"] == "full3" and r["ap_index"] == 3]
        t3 = f3_ap3[-1]["t_end"] if f3_ap3 else p_12["t_start"]
        quiet_start = t3 + BUFFER_WINDOW_S + 0.25
        hf = [w for w in gw if w["t"] >= p_f3["t_start"]]
        exact_hf = [w for w in hf if w["is_approximate"] is False]
        stale_ap3 = [w for w in hf if p_12["t_start"] <= w["t"] < quiet_start]
        hold_window = [w for w in hf if quiet_start <= w["t"] < p_1["t_start"]]
        fb = [w for w in hf if p_1["t_start"] <= w["t"] < p_w["t_start"]]
        weak = [w for w in hf if p_w["t_start"] <= w["t"] <= p_w["t_end"] + 1.0]
        last_exact = exact_hf[-1] if exact_hf else None
        first_approx = next((w for w in hf if w["is_approximate"] is True), None)
        ap1 = C.AP_BY_INDEX[1]
        gap = (round(first_approx["t"] - last_exact["t"], 3) if (first_approx and last_exact) else None)
        checks["holdfallback"] = {
            "statuses": {k: v for k, v in by.items() if k.startswith("holdfallback/")},
            "full3_exact_writes": len([w for w in exact_hf if w["t"] < p_12["t_start"]]),
            "last_full3_ap3_post_t": t3,
            "hold_quiet_window": [round(quiet_start, 3), p_1["t_start"]],
            "writes_ap12_before_ap3_aged_out(allowed)": stale_ap3,
            "writes_in_hold_window(expect 0)": hold_window,
            "fallback_phase_writes": fb,
            "last_exact_write_t": last_exact["t"] if last_exact else None,
            "first_approx_write": first_approx,
            "exact_to_first_approx_gap_s(expect >= 10)": gap,
            "first_approx_anchored_at_ap1": bool(first_approx and first_approx["x"] == ap1["x_m"]
                                                 and first_approx["y"] == ap1["y_m"]
                                                 and first_approx["anchor_ap_mac"] == ap1["mac"]),
            "weak_phase_writes(expect 0)": weak,
        }
        checks["holdfallback"]["PASS"] = bool(
            not hold_window and first_approx and gap is not None and gap >= HOLD_S
            and checks["holdfallback"]["first_approx_anchored_at_ap1"] and not weak
            and all(w["is_approximate"] for w in fb))

    # ── sweeper ───────────────────────────────────────────────────────────────
    sweeps = [o for o in rtdb if o.get("op") == "get" and o.get("path") == "/positions"
              and str(o.get("thread", "")).startswith("asyncio")]
    sweeper_alerts = [o for o in rtdb if o.get("op") == "set" and str(o.get("path", "")).startswith("/alerts/")
                      and str(o.get("thread", "")).startswith("asyncio")]
    checks["sweeper"] = {
        "ticks_observed": len(sweeps), "tick_times": [o["t"] for o in sweeps],
        "alerts_written": [{"path": o["path"], "person_id": (o.get("value") or {}).get("person_id"),
                            "cause": (o.get("value") or {}).get("cause")} for o in sweeper_alerts],
        "stderr_sweep_failed": stderr.count("man-down stale sweep failed"),
        "stderr_signal_loss_log": len(re.findall(r"\[SAFETY\] signal-loss man-down", stderr)),
    }

    # ── safety / tripwire / unimplemented ───────────────────────────────────
    checks["tripwire"] = {
        "hit_file": os.path.exists(os.path.join(run_dir, "TRIPWIRE_HIT.txt")),
        "stderr_banner": "[HARNESS][TRIPWIRE]" in stderr,
        "exit_code": exit_code,
    }
    checks["unimplemented"] = {
        "file": os.path.exists(os.path.join(run_dir, "UNIMPLEMENTED.txt")),
        "stderr": re.findall(r"\[HARNESS\]\[FAKE-UNIMPLEMENTED\] ([^\n]+)", stderr),
    }
    exc_lines = re.findall(r"^(\w+(?:\.\w+)*(?:Error|Exception|Exit)\b[^\n]*)$", stderr, re.M)
    uniq: Dict[str, int] = {}
    for e in exc_lines:
        uniq[e] = uniq.get(e, 0) + 1
    checks["stderr"] = {
        "traceback_count": stderr.count("Traceback (most recent call last)"),
        "exception_lines": uniq,
        "warnings": sorted(set(re.findall(r"^[^\n]*WARNING[^\n]*$", stderr + "\n" + stdout, re.M)))[:40],
    }
    checks["lifecycle"] = {
        "clean_exit_line": "[HARNESS] clean exit" in stdout,
        "launcher_exit_code": exit_code,
        "application_startup_complete": "Application startup complete" in stderr,
        "uvicorn_running_line": bool(re.search(r"Uvicorn running on http://127\.0\.0\.1:\d+", stderr)),
    }

    # ── startup firebase ops (before first request) ──────────────────────────
    t_first = reqs[0]["t"] if reqs else 1e18
    checks["startup_ops"] = [{k: o.get(k) for k in ("op", "path", "query", "found", "n", "thread")}
                             for o in fsops + rtdb if o["t"] < t_first]
    writes = {}
    for o in rtdb:
        if o.get("op") in ("set", "update", "delete"):
            key = re.sub(r"/alerts/[^/]+", "/alerts/<id>", o["path"])
            writes[f"rtdb {o['op']} {key}"] = writes.get(f"rtdb {o['op']} {key}", 0) + 1
    for o in fsops:
        if o.get("op", "").startswith(("doc.set", "doc.update", "doc.delete", "doc.create", "batch")):
            k = f"fs {o['op']} {o.get('path')}"
            writes[k] = writes.get(k, 0) + 1
    checks["write_paths"] = writes
    checks["op_kinds_used"] = sorted({f"rtdb.{o.get('op')}" for o in rtdb} |
                                     {f"fs.{o.get('op')}" for o in fsops})
    checks["queries_used"] = sorted({re.sub(r"'mac', '==', '[^']*'", "'mac', '==', <mac>", o.get("query", ""))
                                     for o in fsops if o.get("op") == "query"})

    # ── final state ───────────────────────────────────────────────────────────
    pos = (state.get("rtdb") or {}).get("positions") or {}
    checks["final_state"] = {
        "state_phase": state.get("phase"),
        "positions": {k: {kk: v.get(kk) for kk in ("is_approximate", "x", "y", "anchor_ap_mac", "timestamp")}
                      for k, v in pos.items()},
        "alerts": [{"person_id": v.get("person_id"), "type": v.get("alert_type"), "cause": v.get("cause")}
                   for v in ((state.get("rtdb") or {}).get("alerts") or {}).values()],
        "ap_heartbeats": sorted(((state.get("rtdb") or {}).get("ap_heartbeats") or {}).keys()),
        "beacon_scans": sorted(((state.get("rtdb") or {}).get("beacon_scans") or {}).keys()),
        "settings_safety": (state.get("firestore") or {}).get("settings/safety"),
        "counters": state.get("counters"),
    }
    A["checks"] = checks

    with open(os.path.join(run_dir, "analysis.json"), "w", encoding="utf-8") as f:
        json.dump(A, f, ensure_ascii=False, indent=1, default=str)
    with open(os.path.join(run_dir, "analysis.txt"), "w", encoding="utf-8") as f:
        f.write(summary_text(A))
    return A


def summary_text(A: Dict[str, Any]) -> str:
    c = A["checks"]
    L = [f"run_dir: {A['run_dir']}", f"requests: {A['request_count']}", "status_by_phase:"]
    for k, v in A["status_by_phase"].items():
        L.append(f"  {k}: {v}")
    if "solve" in c:
        s = c["solve"]
        L.append(f"solve: writes={s['writes_in_phase']} exact={s['exact_writes']} approx={s['approx_writes']} "
                 f"last_is_exact={s['last_is_exact']} last_exact_err_m={s['last_exact_err_m']}")
    if "rssinull" in c:
        r = c["rssinull"]
        L.append(f"rssinull: status={r['status']} json={r['json']} AttributeError_in_stderr={r['stderr_attributeerror_count']}")
        for fr in r["stderr_ingest_frames"]:
            L.append(f"  frame: {fr}")
        L.append(f"  worker writes after: {len(r['worker_writes_after'])}")
    if "holdfallback" in c:
        h = c["holdfallback"]
        L.append(f"holdfallback: PASS={h['PASS']} full3_exact={h['full3_exact_writes']} "
                 f"stale_ap3_writes={len(h['writes_ap12_before_ap3_aged_out(allowed)'])} "
                 f"hold_window_writes={len(h['writes_in_hold_window(expect 0)'])} "
                 f"gap_exact_to_approx={h['exact_to_first_approx_gap_s(expect >= 10)']} "
                 f"anchored_ap1={h['first_approx_anchored_at_ap1']} "
                 f"fallback_writes={len(h['fallback_phase_writes'])} weak_writes={len(h['weak_phase_writes(expect 0)'])}")
    sw = c["sweeper"]
    L.append(f"sweeper: ticks={sw['ticks_observed']} alerts={sw['alerts_written']} failed={sw['stderr_sweep_failed']}")
    L.append(f"tripwire: {c['tripwire']}")
    L.append(f"unimplemented: {c['unimplemented']}")
    L.append(f"stderr: tracebacks={c['stderr']['traceback_count']} exceptions={c['stderr']['exception_lines']}")
    L.append(f"lifecycle: {c['lifecycle']}")
    L.append(f"op kinds: {c['op_kinds_used']}")
    L.append(f"queries: {c['queries_used']}")
    L.append("write paths:")
    for k, v in sorted(c["write_paths"].items()):
        L.append(f"  {k}: {v}")
    return "\n".join(L) + "\n"


def main(argv) -> int:
    if len(argv) != 2:
        print("usage: python analyze.py <run_dir>", file=sys.stderr)
        return 2
    A = analyze(os.path.abspath(argv[1]))
    print(summary_text(A).encode("ascii", "backslashreplace").decode("ascii"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
