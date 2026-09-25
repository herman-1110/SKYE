"""Deterministic A/B: drive omada_ingest_service.ingest() in-process on a fake clock
against the harness's in-memory Firebase; record a full behavioural trace.

usage: python -B ab_run.py --backend-dir DIR [--run-dir DIR] [--out TRACE_JSON] > stdout.txt 2> stderr.txt
  --run-dir  fakes' op logs (default tools/harness/runs/ab; a non-empty dir under runs/ is wiped)
  --out      trace json (default <run-dir>/trace.json)
  env AB_CAPTURE_DIR=<dir>  also install the backend's capture tee (utils.capture_log) into <dir>
                            first thing, as main.py does (resolved before the chdir into the backend)
No server, no port. Compare two runs with ab_compare.py (and tee_ab_compare.py for AB_CAPTURE_DIR runs)."""
import sys
sys.dont_write_bytecode = True
import argparse, os, json, types, time as _real_time
for _s in (sys.stdout, sys.stderr):
    _s.reconfigure(encoding="utf-8")  # as main.py (Prompt 126) does
from datetime import datetime, timezone
HARNESS = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HARNESS)
import harness_common as C
_ap = argparse.ArgumentParser(description="deterministic in-process A/B replay of omada_ingest_service")
_ap.add_argument("--backend-dir", required=True, help="backend dir to import (a git-archive export)")
_ap.add_argument("--run-dir", default=os.path.join(C.RUNS_DIR, "ab"))
_ap.add_argument("--out", default=None, help="trace json (default <run-dir>/trace.json)")
_a = _ap.parse_args()
backend_dir = os.path.abspath(_a.backend_dir)
run_dir = C.prepare_run_dir(_a.run_dir)
out_path = os.path.abspath(_a.out) if _a.out else os.path.join(run_dir, "trace.json")
capture_dir = os.path.abspath(os.environ["AB_CAPTURE_DIR"]) if os.environ.get("AB_CAPTURE_DIR") else None
from dotenv import load_dotenv
load_dotenv(dotenv_path=C.REAL_ENV_PATH, override=False)
sys.path.insert(0, backend_dir); os.chdir(backend_dir)
# Optional: install the backend's own capture tee first thing, as main.py does, so the
# tee itself is exercised with a working console (set AB_CAPTURE_DIR to a scratch dir).
if capture_dir:
    from pathlib import Path
    from utils.capture_log import install_capture_log
    install_capture_log(Path(capture_dir))
import harness_fakes
harness_fakes.install_tripwire(run_dir)
store = harness_fakes.install_fakes(run_dir)
import harness_seed
harness_seed.seed(store)
import driver as D

class Clock: t = 1_000_000.0
fake_time = types.SimpleNamespace(**{k: getattr(_real_time, k) for k in dir(_real_time) if not k.startswith("__")})
fake_time.monotonic = lambda: Clock.t
fake_time.time = lambda: 1_790_000_000.0 + Clock.t
fake_iso = lambda: datetime.fromtimestamp(fake_time.time(), timezone.utc).isoformat()

from services.omada_ingest_service import omada_ingest_service as S
import services.omada_ingest_service as OIS
root = os.path.normcase(backend_dir)
patched = []
for name, mod in list(sys.modules.items()):
    f = os.path.normcase(os.path.abspath(getattr(mod, "__file__", "") or "x"))
    if f.startswith(root) and (os.sep + "venv" + os.sep) not in f:
        if getattr(mod, "time", None) is _real_time:
            mod.time = fake_time; patched.append(name + ".time")
        if hasattr(mod, "utcnow_iso"):
            mod.utcnow_iso = fake_iso; patched.append(name + ".utcnow_iso")
D.time = fake_time
print(f"[AB] patched: {sorted(patched)}", file=sys.stderr)
print(f"[AB] EMIT_MIN_INTERVAL_S={OIS.EMIT_MIN_INTERVAL_S!r} BUFFER_WINDOW_S={OIS.BUFFER_WINDOW_S!r} MIN_APS={OIS.MIN_APS_FOR_POSITION!r}", file=sys.stderr)

def rnd(v): return round(v, 9) if isinstance(v, float) else v
trace = []
def step(label, ap, entries):
    try:
        r = S.ingest(D.payload(ap, entries)); res = dict(r)
    except Exception as e:
        res = {"exception": type(e).__name__, "msg": str(e)}
    snap = store.snapshot()["rtdb"]
    pos = {k: {f: rnd(v.get(f)) for f in ("x", "y", "is_approximate", "anchor_ap_mac", "zone", "radius_m",
                                          "predicted_x", "predicted_y", "floor_id", "timestamp")}
           for k, v in sorted((snap.get("positions") or {}).items()) if k != "test-128-stale"}
    alerts = sorted(json.dumps({k: v.get(k) for k in ("person_id", "cause", "type", "zone")}) for v in (snap.get("alerts") or {}).values())
    scans = {k: (v.get("rssi"), v.get("ap_mac")) for k, v in sorted((snap.get("beacon_scans") or {}).items())}
    trace.append({"label": label, "t": round(Clock.t, 3), "res": res, "positions": pos, "alerts": alerts,
                  "scans": scans, "null": dict(S._rssi_null_count), "total": dict(S._rssi_report_total),
                  "last_emit": {k: round(v, 6) for k, v in S._last_emit.items()}})
    sys.stdout.flush()

G, W = "0001", "0002"
rs = D.rssi_for_point(8, 6)
def adv(dt): Clock.t += dt
for c in range(8):                              # phase 1: full 3-AP cycles with nulls
    for ap in (1, 2, 3):
        r = rs[ap] + ((c * 7 + ap * 3) % 5 - 2)
        null = (ap == 2 and c == 3) or (ap == 3 and c in (5, 6))
        ents = [D.entry(G, None if null else r)]
        if ap == 1: ents.append(D.entry(W, -65 - (c % 3)))
        step(f"p1 c{c} ap{ap}", ap, ents); adv(0.333)
for c in range(6):                              # phase 2: AP1+AP2 only -> hold
    for ap in (1, 2):
        step(f"p2 c{c} ap{ap}", ap, [D.entry(G, rs[ap])]); adv(0.5)
for c in range(8):                              # phase 3: AP1 only -> fallback after 10 s
    step(f"p3 c{c}", 1, [D.entry(G, rs[1])]); adv(1.0)
for c in range(4):                              # phase 4: AP1 at -95 -> below floor
    step(f"p4 c{c}", 1, [D.entry(G, -95)]); adv(1.0)
step("p5 rssinull", 1, [D.entry(G, "JSONNULL"), D.entry(W, -66)])   # last: differs by design
json.dump(trace, open(out_path, "w", encoding="utf-8"), indent=1, default=str)
print(f"[AB] steps={len(trace)}", file=sys.stderr)
