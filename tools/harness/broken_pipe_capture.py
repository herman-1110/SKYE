"""Broken-pipe capture test: server stdout AND stderr share one OS pipe (like `2>&1 | Tee-Object`);
the reader is killed mid-run. Reports HTTP codes and per-tag capture-file growth, sampled every 60 s.
usage: python -B broken_pipe_capture.py --backend-dir DIR --mode unbuffered|buffered --dump true|false
                                        --seconds AFTER_BREAK_S [--port 8002] [--run-dir DIR] [--out JSON]
  --seconds  how long to keep posting after the pipe reader is killed
  --run-dir  launcher run dir (default tools/harness/runs/bp_<mode>_dump<dump>; wiped if under runs/)
  --out      result json (default <run-dir>/result.json)
Capture files are read from <backend-dir>/logs (only files created by this run are counted)."""
import sys, os, subprocess, time, glob, io, json, argparse
sys.dont_write_bytecode = True
H = os.path.dirname(os.path.abspath(__file__))
sys.path.append(H)
import harness_common as C
_ap = argparse.ArgumentParser(description="broken-pipe capture test (stdout+stderr on one pipe)")
_ap.add_argument("--backend-dir", required=True, help="backend dir to run (a git-archive export, never the live backend/)")
_ap.add_argument("--mode", required=True, choices=["unbuffered", "buffered"])
_ap.add_argument("--dump", required=True, choices=["true", "false"], help="OMADA_RAW_DUMP_ENABLED for the server")
_ap.add_argument("--seconds", required=True, type=float, help="seconds to keep posting after the pipe breaks")
_ap.add_argument("--port", type=int, default=8002)
_ap.add_argument("--run-dir", default=None)
_ap.add_argument("--out", default=None)
_a = _ap.parse_args()
BK, MODE, DUMP, AFTER_S, PORT = os.path.abspath(_a.backend_dir), _a.mode, _a.dump, _a.seconds, _a.port
if PORT in C.FORBIDDEN_PORTS:
    print(f"refusing port {PORT} (live dev server)", file=sys.stderr); sys.exit(2)
if C.port_busy(PORT):
    print(f"port {PORT} already has a listener on {C.HOST}; aborting", file=sys.stderr); sys.exit(2)
RUN = C.prepare_run_dir(_a.run_dir or os.path.join(C.RUNS_DIR, f"bp_{MODE}_dump{DUMP}"))
OUT = os.path.abspath(_a.out) if _a.out else os.path.join(RUN, "result.json")
import driver as Dr
logs = os.path.join(BK, "logs")
before_files = set(glob.glob(os.path.join(logs, "skye-*")))
env = os.environ.copy()
env["OMADA_RAW_DUMP_ENABLED"] = DUMP
if MODE == "unbuffered": env["PYTHONUNBUFFERED"] = "1"
else: env.pop("PYTHONUNBUFFERED", None)
consumer = subprocess.Popen([sys.executable, "-c", "import sys\nwhile sys.stdin.buffer.read(65536): pass"], stdin=subprocess.PIPE)
server = subprocess.Popen([sys.executable, "-B", os.path.join(H, "launcher.py"), BK, str(PORT), RUN], cwd=H,
                          stdout=consumer.stdin, stderr=consumer.stdin, stdin=subprocess.DEVNULL, env=env)   # 2>&1
consumer.stdin.close()

def counts():
    files = sorted(set(glob.glob(os.path.join(logs, "skye-*"))) - before_files)
    L = []
    for f in files:
        with io.open(f, encoding="utf-8", errors="replace") as fh: L += fh.read().splitlines()
    B = [l[25:] for l in L]
    return {"files": len(files), "total lines": len(L),
            "[MEMBERSHIP-128]": sum(b.startswith("[MEMBERSHIP-128]") for b in B),
            "[OMADA] dump/warning": sum(b.startswith("[OMADA]") for b in B),
            "access POST": sum(b.startswith("INFO:") and '"POST /telemetry/omada HTTP/1.1"' in b for b in B),
            "request_logger POST": sum("[POST] /telemetry/omada" in b for b in B),
            "console-dead WARNING": sum("[CAPTURE-128] WARNING: console" in b for b in B),
            "--- Logging error ---": sum("--- Logging error ---" in b for b in B),
            "Traceback": sum("Traceback" in b for b in B),
            "Unhandled exception": sum("Unhandled exception" in b for b in B)}

res = {"mode": MODE, "raw_dump": DUMP, "after_break_s": AFTER_S, "backend": BK}
res["ready"] = Dr.wait_ready(PORT, timeout=90, proc=server)
Dr.configure(PORT)
real_pid = int(open(os.path.join(RUN, "pid.txt")).read().strip())
rs = Dr.rssi_for_point(8, 6)
def one_cycle(codes):
    for ap in (1, 2, 3):
        try:
            st, _js = Dr.post(ap, [Dr.entry("0001", rs[ap])], port=PORT)
        except Exception as e:
            st = type(e).__name__
        codes.append(st); time.sleep(0.33)
c1 = []
for _ in range(4): one_cycle(c1)
time.sleep(0.5)
res["before_break"] = counts(); res["before_break_http"] = {str(k): c1.count(k) for k in set(c1)}
consumer.kill(); consumer.wait()
res["break_at_local"] = time.strftime("%H:%M:%S")
t0 = time.time(); c2 = []; samples = []; next_sample = 60.0
while time.time() - t0 < AFTER_S:
    one_cycle(c2)
    el = time.time() - t0
    if el >= next_sample:
        samples.append({"t_s": round(el), "http_so_far": {str(k): c2.count(k) for k in set(c2)}, **counts()}); next_sample += 60.0
time.sleep(1.0)
res["after_break_elapsed_s"] = round(time.time() - t0, 1)
res["after_break"] = counts(); res["after_break_http"] = {str(k): c2.count(k) for k in set(c2)}
res["samples"] = samples
res["server_alive_after"] = server.poll() is None
res["delta"] = {k: res["after_break"][k] - res["before_break"][k] for k in res["after_break"]}
open(os.path.join(RUN, "STOP"), "w").close()
try:
    res["shutdown"] = f"graceful exit={server.wait(45)}"
except subprocess.TimeoutExpired:
    subprocess.run(["taskkill", "/F", "/PID", str(real_pid)], capture_output=True)
    res["shutdown"] = f"FORCED (graceful stop hung), shim exit={server.wait(15)}"
res["final"] = counts()
json.dump(res, io.open(OUT, "w", encoding="utf-8"), indent=1)
print(f"[BP] wrote {OUT}")
