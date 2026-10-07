"""Start launcher -> wait ready -> run driver scenario -> STOP -> wait clean exit -> analyze.

usage (run with the backend venv python):
  python -B run_smoke.py --backend-dir DIR [--port 8002] [--run-dir DIR]
                         [--scenario all] [--min-uptime 75] [--ready-timeout 90]

--backend-dir is required (no default): point it at a git-archive export,
never the live backend/. Defaults: port 8002, run dir tools/harness/runs/smoke.
--min-uptime keeps the server up at least this many seconds after it became
ready, so the 60 s man-down sweeper ticks at least once (0 to skip).
launcher stdout/stderr are redirected by subprocess straight to
<run_dir>/stdout.log and <run_dir>/stderr.log (bytes as written; the app
reconfigures its streams to UTF-8). Console output here is ASCII only.
Exit code: launcher exit code (0 = clean), 99 = tripwire, 4 = not ready.
"""
import argparse
import os
import shutil
import socket
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
if HARNESS_DIR not in sys.path:
    sys.path.append(HARNESS_DIR)

import harness_common as C  # noqa: E402
import driver as D  # noqa: E402
import analyze as AN  # noqa: E402


def _port_busy(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        return s.connect_ex((C.HOST, port)) == 0
    finally:
        s.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend-dir", required=True,
                    help="backend dir to run (a git-archive export, never the live backend/)")
    ap.add_argument("--port", type=int, default=8002)
    ap.add_argument("--run-dir", default=os.path.join(C.RUNS_DIR, "smoke"))
    ap.add_argument("--scenario", default="all")
    ap.add_argument("--min-uptime", type=float, default=75.0)
    ap.add_argument("--ready-timeout", type=float, default=90.0)
    ap.add_argument("--stop-timeout", type=float, default=45.0)
    a = ap.parse_args()
    # the launcher runs with cwd=HARNESS_DIR, so resolve relative paths here
    a.backend_dir = os.path.abspath(a.backend_dir)

    if a.port in C.FORBIDDEN_PORTS:
        print(f"refusing port {a.port}")
        return 2
    if _port_busy(a.port):
        print(f"port {a.port} already has a listener on {C.HOST}; aborting")
        return 2
    run_dir = os.path.abspath(a.run_dir)
    runs_root = C.RUNS_DIR
    if os.path.exists(run_dir) and os.listdir(run_dir):
        if os.path.commonpath([run_dir, runs_root]) == runs_root and run_dir != runs_root:
            shutil.rmtree(run_dir)
        else:
            print(f"run dir {run_dir} is not empty and not under tools/harness/runs; aborting")
            return 2
    os.makedirs(run_dir, exist_ok=True)

    py = sys.executable
    cmd = [py, "-B", os.path.join(HARNESS_DIR, "launcher.py"), a.backend_dir, str(a.port), run_dir]
    with open(os.path.join(run_dir, "cmd.txt"), "w", encoding="utf-8") as f:
        f.write(" ".join(f'"{c}"' if " " in c else c for c in cmd) + "\n")
    f_out = open(os.path.join(run_dir, "stdout.log"), "wb")
    f_err = open(os.path.join(run_dir, "stderr.log"), "wb")
    t_launch = time.time()
    proc = subprocess.Popen(cmd, cwd=HARNESS_DIR, stdout=f_out, stderr=f_err, stdin=subprocess.DEVNULL,
                            env=os.environ.copy())
    print(f"[RUN] launcher pid={proc.pid} port={a.port} backend={a.backend_dir}")
    rc = None
    try:
        ready = D.wait_ready(a.port, timeout=a.ready_timeout, proc=proc)
        t_ready = time.time()
        print(f"[RUN] ready={ready} after {t_ready - t_launch:.1f}s")
        if not ready:
            if proc.poll() is None:
                open(os.path.join(run_dir, "STOP"), "w").close()
                try:
                    proc.wait(a.stop_timeout)
                except subprocess.TimeoutExpired:
                    proc.kill()
            rc = proc.wait()
            with open(os.path.join(run_dir, "launcher_exit.txt"), "w", encoding="utf-8") as f:
                f.write(str(rc))
            print(f"[RUN] launcher not ready, exit={rc}; see {run_dir}\\stderr.log")
            return 4 if rc in (0, None) else rc

        out_json = os.path.join(run_dir, "driver_out.json")
        with open(os.path.join(run_dir, "driver_stdout.log"), "wb") as dso, \
                open(os.path.join(run_dir, "driver_stderr.log"), "wb") as dse:
            drc = subprocess.call([py, "-B", os.path.join(HARNESS_DIR, "driver.py"), str(a.port), a.scenario,
                                   out_json], cwd=HARNESS_DIR, stdout=dso, stderr=dse, stdin=subprocess.DEVNULL)
        print(f"[RUN] driver exit={drc}")

        while proc.poll() is None and time.time() - t_ready < a.min_uptime:
            time.sleep(0.5)

        if proc.poll() is None:
            open(os.path.join(run_dir, "STOP"), "w").close()
            try:
                proc.wait(a.stop_timeout)
            except subprocess.TimeoutExpired:
                print("[RUN] launcher did not exit after STOP; killing")
                with open(os.path.join(run_dir, "KILLED.txt"), "w", encoding="utf-8") as f:
                    f.write("launcher did not exit within stop timeout\n")
                proc.kill()
        rc = proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
            rc = proc.wait()
        f_out.close()
        f_err.close()
        with open(os.path.join(run_dir, "launcher_exit.txt"), "w", encoding="utf-8") as f:
            f.write(str(rc))

    print(f"[RUN] launcher exit={rc} total={time.time() - t_launch:.1f}s")
    try:
        A = AN.analyze(run_dir)
        print(AN.summary_text(A).encode("ascii", "backslashreplace").decode("ascii"))
    except Exception as e:
        print(f"[RUN] analyze failed: {type(e).__name__}: {e}")
    return rc or 0


if __name__ == "__main__":
    sys.exit(main())
