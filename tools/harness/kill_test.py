"""Kill test: taskkill /F the REAL server interpreter (pid.txt), not the venv shim, then check the
capture file (<backend-dir>/logs/skye-*) is intact: UTF-8 no BOM, every line whole, stops growing.

usage: python -B kill_test.py --backend-dir DIR [--port 8002] [--run-dir DIR] [--out JSON]
  --run-dir  launcher run dir (default tools/harness/runs/kill_test; wiped if under runs/)
  --out      result json (default <run-dir>/result.json)
The venv python is a uv shim: Popen.pid is the shim, the interpreter's PID is in <run-dir>/pid.txt."""
import sys, os, subprocess, time, glob, io, json, argparse
sys.dont_write_bytecode = True
H = os.path.dirname(os.path.abspath(__file__))
sys.path.append(H)
import harness_common as C
_ap = argparse.ArgumentParser(description="hard-kill the server and check the capture file")
_ap.add_argument("--backend-dir", required=True, help="backend dir to run (a git-archive export, never the live backend/)")
_ap.add_argument("--port", type=int, default=8002)
_ap.add_argument("--run-dir", default=os.path.join(C.RUNS_DIR, "kill_test"))
_ap.add_argument("--out", default=None)
_a = _ap.parse_args()
BK, PORT = os.path.abspath(_a.backend_dir), _a.port
if PORT in C.FORBIDDEN_PORTS:
    print(f"refusing port {PORT} (live dev server)", file=sys.stderr); sys.exit(2)
if C.port_busy(PORT):
    print(f"port {PORT} already has a listener on {C.HOST}; aborting", file=sys.stderr); sys.exit(2)
RUN = C.prepare_run_dir(_a.run_dir)
OUT = os.path.abspath(_a.out) if _a.out else os.path.join(RUN, "result.json")
import driver as Dr
logs = os.path.join(BK, "logs")
before = set(glob.glob(os.path.join(logs, "skye-*")))
fo = open(os.path.join(RUN, "stdout.log"), "wb"); fe = open(os.path.join(RUN, "stderr.log"), "wb")
shim = subprocess.Popen([sys.executable, "-B", os.path.join(H, "launcher.py"), BK, str(PORT), RUN], cwd=H, stdout=fo, stderr=fe, stdin=subprocess.DEVNULL)
ok = Dr.wait_ready(PORT, timeout=60, proc=shim)
Dr.configure(PORT)
real_pid = int(open(os.path.join(RUN, "pid.txt")).read().strip())
rs = Dr.rssi_for_point(8, 6)
codes = []
for c in range(3):
    for ap in (1, 2, 3):
        st, js = Dr.post(ap, [Dr.entry("0001", rs[ap])], port=PORT); codes.append(st); time.sleep(0.34)
time.sleep(0.5)
def alive(pid):
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
    return str(pid) in r.stdout
res = {"ready": ok, "shim_pid": shim.pid, "real_pid": real_pid, "post_codes": codes,
       "real_alive_before_kill": alive(real_pid)}
k = subprocess.run(["taskkill", "/F", "/PID", str(real_pid)], capture_output=True, text=True)
res["taskkill_rc"] = k.returncode
try:
    res["shim_exit"] = shim.wait(15)
except subprocess.TimeoutExpired:
    res["shim_exit"] = "still running"
time.sleep(3)
res["real_alive_after_kill"] = alive(real_pid)
fo.close(); fe.close()
new = sorted(set(glob.glob(os.path.join(logs, "skye-*"))) - before)
raw = open(new[0], "rb").read()
lines = raw.decode("utf-8").splitlines()
res.update({
  "capture_file": os.path.basename(new[0]), "bytes": len(raw), "bom": raw[:3] == b"\xef\xbb\xbf",
  "ends_with_newline": raw.endswith(b"\n"),
  "access_200_lines": sum(1 for l in lines if "POST /telemetry/omada HTTP/1.1" in l and " 200" in l),
  "membership_lines": sum(1 for l in lines if "[MEMBERSHIP-128]" in l),
  "shutdown_lines": [l[25:] for l in lines if any(k in l for k in ("Shutting down", "Finished server process", "[HARNESS] clean exit"))],
  "last_line": lines[-1][:160],
})
size1 = len(raw); time.sleep(3); res["file_grew_after_kill"] = os.path.getsize(new[0]) != size1
json.dump(res, io.open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print(f"[KILL] wrote {OUT}")
