# tools/harness

An isolated test harness for the SKYE backend. It runs `main:app` under uvicorn against
**in-memory fakes of Firebase RTDB and Firestore**, seeded with a small test world (3 APs,
2 beacons, 1 stale worker for the man-down sweeper). It never touches `skye-3fa05`:

- **Network tripwire.** Every outbound path is patched: socket DNS/connect, requests,
  google-auth, httpx, urllib and gRPC channel creation. Any attempt to reach a
  Google/Firebase host, or the RTDB host named in `.env`, writes `TRIPWIRE_HIT.txt` to the
  run dir and hard-exits with code 99. An `except Exception` cannot swallow it.
- **Loud fakes.** A Firestore/RTDB call the fakes don't implement raises and is logged to
  `UNIMPLEMENTED.txt`.
- **Refuses port 8000**, the live server with real AP traffic (`FORBIDDEN_PORTS` in
  `harness_common.py`). The default port is 8002. `run_smoke`, `broken_pipe_capture` and
  `kill_test` also abort if their port already has a listener.
- Reads `<repo>/backend/.env` (read-only, `override=False`, the token is never printed).
  Nothing else real is read.

## Golden rule: `--backend-dir` is an export, never `backend/`

`--backend-dir` is required and has no default. Since 128, `main.py` tees all console output
into `<backend_dir>/logs/skye-*.log`, and the live `backend/logs` holds real field captures.
Always point the harness at a `git archive` export:

```bash
# Git Bash (or cmd). Don't pipe tar through Windows PowerShell 5.1: it corrupts binary pipes.
exp="$TEMP/skye-export-1ec17c6"; mkdir -p "$exp"
git archive 1ec17c6 backend | tar -x -C "$exp"      # backend dir = $exp/backend
```

The export has no venv; use the repo's venv python.

## Conventions

- Run from the repo root with `py=backend/venv/Scripts/python.exe`, always as `"$py" -B`.
  The scripts also set `sys.dont_write_bytecode`, so no `__pycache__` lands in the export
  or here.
- Run dirs default to `tools/harness/runs/<name>` (git-ignored). A non-empty run dir under
  `runs/` is wiped at start; a non-empty one anywhere else is refused.
- **The venv `python.exe` is a uv shim.** It starts the real interpreter as a child, so
  `Popen.pid` is the shim. The launcher writes the real interpreter's PID to
  `<run_dir>/pid.txt`; kill that one (`taskkill /F /PID <pid.txt>`). For a graceful stop,
  create `<run_dir>/STOP`.
- Commands below are Git Bash. In PowerShell 5.1, `>` re-encodes native output; wrap
  redirecting commands in `cmd /c "..."`.

## Commands

**Self-test** (tripwire + fakes, no server). Expect `tripwire=PASS fakes=PASS`, exit 0.
```bash
"$py" -B tools/harness/selftest.py
```

**Smoke.** Starts the server, runs the driver scenarios (`solve`, `rssinull`,
`holdfallback`), stays up at least 75 s so the man-down sweeper ticks, stops via STOP and
writes `runs/smoke/analysis.txt`. Exit code: 0 clean, 99 tripwire, 4 never ready.
```bash
"$py" -B tools/harness/run_smoke.py --backend-dir "$exp/backend" --port 8002
```

**Deterministic A/B.** Replays 49 ingest steps in-process on a fake clock (no server, no
port). One export per side, `$A` = baseline, `$B` = candidate:
```bash
R=tools/harness/runs
"$py" -B tools/harness/ab_run.py --backend-dir "$A/backend" --run-dir $R/ab_A > $R/ab_A.stdout.txt 2> $R/ab_A.stderr.txt
"$py" -B tools/harness/ab_run.py --backend-dir "$B/backend" --run-dir $R/ab_B > $R/ab_B.stdout.txt 2> $R/ab_B.stderr.txt
"$py" -B tools/harness/ab_compare.py $R/ab_A/trace.json $R/ab_B/trace.json $R/ab_A.stdout.txt $R/ab_B.stdout.txt $R/ab_compare.txt
cat $R/ab_compare.txt
```
The last step (`p5 rssinull`, a JSON-null rssi) is reported on its own; it differs by design
across 128. Console lines are compared with `[MEMBERSHIP-128]` removed from both sides
(`identical=`) and as-is (`raw_identical=`). Same code on both sides: no step differs.

**Tee A/B.** The same replay, but it first installs the backend's own capture tee
(`utils.capture_log`), so the tee runs with a working console. Keep each capture dir inside
its run dir (wiped per run):
```bash
AB_CAPTURE_DIR=$R/tee_A/capture "$py" -B tools/harness/ab_run.py --backend-dir "$A/backend" --run-dir $R/tee_A > $R/tee_A.stdout.txt 2> $R/tee_A.stderr.txt
AB_CAPTURE_DIR=$R/tee_B/capture "$py" -B tools/harness/ab_run.py --backend-dir "$B/backend" --run-dir $R/tee_B > $R/tee_B.stdout.txt 2> $R/tee_B.stderr.txt
"$py" -B tools/harness/tee_ab_compare.py $R/tee_A.stdout.txt $R/tee_B.stdout.txt $R/tee_A/capture $R/tee_B/capture
```
Expect identical consoles, identical captures, every console line in B's capture, and 0
console-dead warnings.

**Broken-pipe matrix.** The server's stdout **and** stderr share one pipe, like the real
`2>&1 | Tee-Object` launch. After 4 posting cycles the pipe reader is killed; posting
continues for `--seconds`. Run all four rows (unbuffered = `PYTHONUNBUFFERED=1`); the two
dump-on rows run for at least 5 minutes:
```bash
for m in unbuffered buffered; do for d in false true; do
  s=60; [ $d = true ] && s=300
  "$py" -B tools/harness/broken_pipe_capture.py --backend-dir "$exp/backend" --mode $m --dump $d --seconds $s --port 8002
done; done
```
Each row writes `runs/bp_<mode>_dump<dump>/result.json`. Pass: every `before_break_http`
and `after_break_http` code is `200`; `delta` and the per-minute `samples` keep growing
`[MEMBERSHIP-128]` and `access POST` (and `[OMADA] dump/warning` on dump-on rows);
`server_alive_after` is true; `shutdown` is graceful.

**Kill test.** `taskkill /F` on the real interpreter from `pid.txt`, then checks the capture
file. Expect `real_alive_after_kill: false`, `bom: false`, `ends_with_newline: true`,
`file_grew_after_kill: false` in `runs/kill_test/result.json`.
```bash
"$py" -B tools/harness/kill_test.py --backend-dir "$exp/backend" --port 8002
```

**Console vs capture coverage** for one run. It reads every `skye-*` in the dir given, so
use a logs dir that holds only that run's files:
```bash
"$py" -B tools/harness/check_capture.py "$exp/backend/logs" tools/harness/runs/smoke tools/harness/runs/smoke_capture.txt
```

## Files

| file | purpose |
|---|---|
| `launcher.py` | Low-level entry: `launcher.py <backend_dir> <port> <run_dir>`. Tripwire, fakes, seed, uvicorn; stops on `STOP`. |
| `harness_fakes.py` | In-memory RTDB/Firestore fakes, network tripwire, state and op-log dumps. |
| `harness_seed.py` | The test world (building, floor, 3 APs, 2 beacons, owner, stale position). |
| `harness_common.py` | Repo-relative paths, `FORBIDDEN_PORTS`, geometry, run-dir and port helpers. |
| `driver.py` | Real-shaped Omada payloads, POST helpers, scenarios `solve`/`rssinull`/`holdfallback`/`all`. |
| `run_smoke.py` | launcher -> driver -> STOP -> analyze, end to end. |
| `analyze.py` | Run dir -> `analysis.json` + `analysis.txt`. |
| `selftest.py` | Tripwire (9 outbound paths) and fakes self-tests. |
| `ab_run.py`, `ab_compare.py`, `tee_ab_compare.py` | Deterministic A/B replay and its comparisons. |
| `broken_pipe_capture.py` | Broken-pipe capture test (stdout+stderr on one pipe). |
| `kill_test.py` | Hard-kill the server, check the capture file. |
| `check_capture.py` | Console-vs-capture coverage for one run. |
| `repo_snapshot.py` | Size/mtime snapshot of the repo; diff two to prove a run changed nothing. |
