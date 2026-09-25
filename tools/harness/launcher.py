"""p128 harness launcher: run a SKYE backend against in-memory Firebase fakes.

usage: python -B launcher.py <backend_dir> <port> <run_dir>

Low-level entry point; run_smoke.py / broken_pipe_capture.py / kill_test.py
wrap it. <backend_dir> should be a git-archive export, never the live
backend/ (the app's capture log writes into <backend_dir>/logs). Refuses
port 8000 (harness_common.FORBIDDEN_PORTS).

Order of operations (each step matters):
  1. no .pyc writes (never touch the backend dir's __pycache__)
  2. load the REAL .env (<repo>/backend/.env) explicitly (settings.py's bare
     load_dotenv() cannot find it from an export). override=False: anything the caller already
     exported wins; nothing is added or overridden by the harness.
  3. sys.path.insert(0, backend_dir); chdir(backend_dir)
  4. tripwire + fakes installed, fake world seeded
  5. uvicorn.Config("main:app", ...) built FIRST (configures uvicorn's logging
     StreamHandlers against the current sys.stdout/sys.stderr), then
     uvicorn.Server(config).run() imports main:app - same order as the CLI.
Stop: create <run_dir>/STOP. Server exits gracefully, "[HARNESS] clean exit"
is printed and main() returns normally so atexit handlers run.
"""
import sys

sys.dont_write_bytecode = True

import os  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402

HARNESS_DIR = os.path.dirname(os.path.abspath(__file__))
if HARNESS_DIR not in sys.path:
    sys.path.append(HARNESS_DIR)

import harness_common as C  # noqa: E402


def _dumper(run_dir: str, stop_evt: threading.Event, fakes_mod) -> None:
    failures = 0
    while not stop_evt.is_set():
        try:
            if not fakes_mod.dump_state(run_dir):
                failures += 1
        except Exception:
            failures += 1
            if failures <= 3:
                fakes_mod._stderr("[HARNESS] state dump failed:\n" + traceback.format_exc())
        stop_evt.wait(0.5)


def _stop_watcher(run_dir: str, server) -> None:
    stop_path = os.path.join(run_dir, "STOP")
    while True:
        if os.path.exists(stop_path):
            print("[HARNESS] STOP file seen - requesting graceful shutdown", flush=True)
            server.should_exit = True
            return
        time.sleep(0.2)


def main(argv) -> int:
    if len(argv) != 4:
        print("usage: python launcher.py <backend_dir> <port> <run_dir>", file=sys.stderr)
        return 2
    backend_dir = os.path.abspath(argv[1])
    port = int(argv[2])
    run_dir = os.path.abspath(argv[3])
    if port in C.FORBIDDEN_PORTS:
        print(f"[HARNESS] refusing port {port} (live dev server)", file=sys.stderr)
        return 2
    if not os.path.isfile(os.path.join(backend_dir, "main.py")):
        print(f"[HARNESS] no main.py in {backend_dir}", file=sys.stderr)
        return 2

    os.makedirs(run_dir, exist_ok=True)
    stop_path = os.path.join(run_dir, "STOP")
    if os.path.exists(stop_path):
        os.remove(stop_path)
    with open(os.path.join(run_dir, "pid.txt"), "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))

    # (2) real .env, explicitly, before anything can import config.settings
    from dotenv import load_dotenv
    if not load_dotenv(dotenv_path=C.REAL_ENV_PATH, override=False):
        print(f"[HARNESS] could not load {C.REAL_ENV_PATH}", file=sys.stderr)
        return 2

    # (3)
    sys.path.insert(0, backend_dir)
    os.chdir(backend_dir)

    # (4)
    import harness_fakes
    patched = harness_fakes.install_tripwire(run_dir)
    store = harness_fakes.install_fakes(run_dir)
    import harness_seed
    seeded = harness_seed.seed(store)
    print(f"[HARNESS] pid={os.getpid()} backend_dir={backend_dir} port={port}", flush=True)
    print(f"[HARNESS] tripwire patch points: {len(patched)}; fakes installed; seeded: "
          f"{len(seeded.get('aps', []))} APs, {len(seeded.get('beacons', {}))} beacons, "
          f"stale={seeded.get('stale_position_seeded')}", flush=True)
    print(f"[HARNESS] POSITION_EMIT_MIN_INTERVAL_S in env: "
          f"{'POSITION_EMIT_MIN_INTERVAL_S' in os.environ}", flush=True)

    stop_evt = threading.Event()
    harness_fakes.dump_state(run_dir, {"phase": "pre-import"})
    threading.Thread(target=_dumper, args=(run_dir, stop_evt, harness_fakes),
                     name="harness-dumper", daemon=True).start()

    # (5) CLI ordering: Config first (logging configured now), import on run()
    import uvicorn
    config = uvicorn.Config("main:app", host=C.HOST, port=port, log_level="info")
    server = uvicorn.Server(config)
    threading.Thread(target=_stop_watcher, args=(run_dir, server),
                     name="harness-stop-watcher", daemon=True).start()

    server.run()

    stop_evt.set()
    try:
        harness_fakes.dump_state(run_dir, {"phase": "final"})
    except Exception:
        harness_fakes._stderr("[HARNESS] final state dump failed:\n" + traceback.format_exc())
    if not getattr(server, "started", False):
        print("[HARNESS] server never started (see stderr)", flush=True)
        return 3
    print("[HARNESS] clean exit", flush=True)
    return 0


if __name__ == "__main__":
    rc = main(sys.argv)
    if rc:
        sys.exit(rc)
