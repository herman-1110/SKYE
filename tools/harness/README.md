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

**VIGI camera events (Prompt 131).** Two scripts. `vigi_131_test.py` drives the launcher
through Prompt 131's VALIDATION 1-11 against fake cameras on `127.0.0.2`-`.4`
(`vigi_fake_camera.py`: an RTSP-port listener plus an HTTPS OpenAPI that checks the
real SHA-256 digest and counts logins), with two server runs so the lockout guard is
tested across a restart. `vigi_131_inprocess.py` covers VALIDATION 12 (an alarm push
completes while `pipeline_lock` is held by another thread), the 15-minute buffer cutoff
and the parser on every fixture. Both write `<backend-dir>/.env` with **fake values only**
and never read the real `backend/.env`. `vigi_131_test.py` needs `openssl` on PATH
(Git Bash has it).
```bash
"$py" -B tools/harness/vigi_131_test.py --backend-dir "$exp/backend" --port 8003
"$py" -B tools/harness/vigi_131_inprocess.py --backend-dir "$exp/backend"
```
Expect `34 passed, 0 failed` and `5 passed, 0 failed`. Results in
`runs/vigi131/result.json` and `runs/vigi131_inprocess/result.json`.

**Camera discovery (Prompt 131b).** `vigi_131b_inprocess.py` drives the discovery service
against a loopback WS-Discovery responder (no LAN traffic): MAC/IP/name recorded and
replies merged by MAC, the ARP fallback, pruning, `ip_mismatch`, `POST /cctvs/discover`
(admin only), and that an unregistered camera never sees a doAuth or a login. Expect
`9 passed, 0 failed`.
```bash
"$py" -B tools/harness/vigi_131b_inprocess.py --backend-dir "$exp/backend"
```
The launcher sets `VIGI_DISCOVERY_INTERVAL_S=0` unless the caller sets it, so no harness
server multicasts on the real LAN. Fixtures (real
payloads from the InSight S445, request paths stripped) are in `fixtures/vigi/`.

**Live view (Prompt 132).** `vigi_132_inprocess.py` drives the WebRTC signaling route against
a fake go2rtc (a small HTTP server on 127.0.0.1 with a canned SDP answer): 401/403/200, every
error (go2rtc down 503, stream not loaded 503, ffmpeg missing 503, go2rtc error 502, too slow
504, camera offline 409, no IP / NVR 409, unknown camera 404, offers that would send video or
audio 422), the generated go2rtc config (written at startup, each stream an `exec:` ffmpeg that
copies the camera's video and strips SEI, `exec` limited to that ffmpeg, no RTSP module,
`_sub`/`_main` paths, `${VIGI_CAMERA_PASSWORD}`
and never the test password, API on loopback and WebRTC on the address towards the camera or
`GO2RTC_WEBRTC_HOST`, rewritten after create / IP edit / delete and when that address changes,
not after a name edit), and that the fixed test password is in no log line, response body or
config file. Expect `29 passed, 0 failed`. (A `ConnectionAbortedError` traceback from the fake
go2rtc is expected: its deliberately slow reply arrives after the backend has given up.)
```bash
"$py" -B tools/harness/vigi_132_inprocess.py --backend-dir "$exp/backend"
```
The launcher points `GO2RTC_CONFIG_PATH` at `<run_dir>/go2rtc.yaml` and `GO2RTC_API_URL` at a
dead port unless the caller sets them, so a harness server never rewrites the live go2rtc
config (which would make `tools/go2rtc/start.ps1` relaunch the real go2rtc) or reaches it.

Two opt-in switches the VIGI tests use (both off by default, so other runs are unchanged):
- `HARNESS_FAKE_AUTH=1`: `firebase_admin.auth.verify_id_token` accepts
  `harness-token:<uid>`, so `require_auth`/`require_admin` routes can be driven as the
  seeded `harness-owner`.
- `HARNESS_ENV_PATH=<file>`: the launcher loads that file instead of the real
  `backend/.env`.

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
| `vigi_131_test.py` | Prompt 131 VIGI camera checks through the launcher (fake cameras, two runs). |
| `vigi_131_inprocess.py` | Prompt 131 in-process checks: `pipeline_lock`, buffer cutoff, parser on fixtures. |
| `vigi_fake_camera.py` | Fake VIGI camera: RTSP-port listener + HTTPS OpenAPI with real digest checks. |
| `vigi_131b_inprocess.py` | Prompt 131b camera discovery checks against a loopback WS-Discovery responder. |
| `vigi_132_inprocess.py` | Prompt 132 live-view checks: signaling route, go2rtc config, secrets, against a fake go2rtc. |
| `ap_rename_inprocess.py` | Renaming an AP (`PATCH .../aps/{id}`): auth, trimmed name stored, MAC/position untouched, 422/404. Expect `4 passed`. |
| `man_down_latch_inprocess.py` | Man-down stillness latch: one alert per stillness episode, a new one after moving past the epsilon or an approximate→exact upgrade. Clock patched, no server. Expect `6 passed` (HEAD before 9 Oct fails 4). |
| `fixtures/vigi/` | Real InSight S445 alarm payloads (legacy and enhanced), request paths stripped. |
