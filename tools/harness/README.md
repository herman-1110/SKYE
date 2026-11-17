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
| `sec04_dump_redaction_inprocess.py` | SEC-04 (Prompt 135): with the raw dump on, the dumped AP report shows `***` for `meta.access_token` and is otherwise unchanged; the ingest still accepts the report. Expect `5 passed` (`2f00309` fails 2). |
| `sec01_ingest_fence_inprocess.py` | SEC-01 (Prompt 135): `/telemetry` only from loopback (403 otherwise, before the token); `/telemetry/omada` limited to `OMADA_INGEST_ALLOWED_IPS` when set (403 before the token, one log line per rejected address per 10 min), open with one startup warning when unset; the setting's parser. Requests use httpx's ASGI transport with a chosen client address. Expect `9 passed` (`2f00309` fails check 1 and has no allowlist to test). |
| `cor05_sim_cleanup_inprocess.py` | COR-05 / CON-04 (Prompt 135): each simulator removes its own `/positions` records when cancelled, failed or stopped through the API; the lifespan cancels a running simulation on shutdown and removes all simulators' leftovers at startup; a hanging clean-up is bounded and logged. The simulators' httpx client is faked (localhost:8000 is the live backend). Expect `8 passed` (`2f00309` has no clean-up module). |
| `cor12_sim_events_inprocess.py` | COR-12, simulator half (Prompt 135): in `simulation_events`, the ghost event raises one `ghost_patrol` only (its log has a BLE arrival and is compliant), the missed event one `patrol_violation` only, normal ticks nothing; two whole scripted cycles report the tick each event fires on (ghost at cycle tick 26 of 37; missed at 35 in this harness layout). httpx faked. Expect `7 passed` (`2f00309` fails 4: each event cross-fires). |
| `cor01_timestamps_inprocess.py` | COR-01 (Prompt 135): `/telemetry` answers 422 to a naive, malformed or >5 min future timestamp and accepts aware, `Z` and past ones; the signal-loss sweep skips an unreadable record (naive, non-string), logs it once per person per hour, and still alerts on a stale good one. Expect `7 passed` (`2f00309` fails 3, then the sweep crashes with the TypeError COR-01 describes). |
| `cor08_ap_delete_inprocess.py` | COR-08 (Prompt 135): deleting a route AP returns 200, removes it from `patrol_route` with an update touching only that field and made before the AP is deleted (checked in the fake's op log), leaves `patrol_enabled` and `patrol_interval_minutes` alone, and still removes the heartbeat and unlinks a covering camera; a non-route or unknown AP leaves the floor alone. Expect `6 passed` (`2f00309` raises the TypeError COR-08 describes). |
| `cor02_kalman_lockup_inprocess.py` | COR-02 (Prompt 136): after a jump of more than the 8 m outlier threshold the output follows within 3 measurements; a rejected measurement doesn't refresh `_last_seen`; isolated outliers (2 bad, 1 good, 2 bad) are still rejected; `invalidate_scale_cache()` drops the Kalman filters. Noiseless RSSI on the seeded floor, fake clock. Expect `5 passed` (`2975863` fails 3). |
| `cor04_collision_age_floor_inprocess.py` | COR-04 (Prompt 136): a fresh worker and forklift on the same floor still collide, with repeats 10 s apart; a record older than `COLLISION_MAX_AGE_S` never pairs; a pair on different floors, or with no floor, never pairs; an unreadable timestamp is skipped and logged once an hour. Clock patched, `check_collision()` called directly. Expect `6 passed` (`2975863` fails 3). |
| `cor03_coverage_edge_inprocess.py` | COR-03 (Prompt 136, decision b): stillness seen by one or two APs raises one amber `possible_man_down` (after an exact anchor, or with approximate readings only) and never a red `man_down`; 30 s of exact stillness after it raises one red `man_down` timed from the run's start; movement on return cancels that; approximate readings during the confirmation don't restart it. Prompt 145, decision (c): a change of strongest AP starts a new run only once no reading has come from the run's AP for the hold, timed from the first reading away (a third AP doesn't restart it, nor does an exact fix); the new run sits at the latest AP, timed from that first reading, with every AP read since as its spots. So an AP that keeps flipping keeps one run and its one amber, and someone still between two other APs gets theirs. The hold's default is 120 s, and at 120 s a move's amber comes on the reading that completes it. Clock patched, `man_down_minutes` 1, the hold set to 30 s but for that one check. Expect `12 passed` (`2975863` fails 11; `794261a`, where a new strongest AP started a new run at once, fails 6; `a886862`, where a third AP restarted the 30 s and the default was 30 s, fails 2). |
| `con03_sweep_lock_inprocess.py` | CON-03 (Prompt 136): a fresh position that lands after the signal-loss sweep read a stale record (forced from inside the read) raises nothing and sets no latch; the sweep's save holds `pipeline_lock` and its read doesn't; with the lock held elsewhere the read finishes but the save waits; someone last seen before the read still alerts. Expect `5 passed` (`2975863` fails 3). |
| `rel01_ap_outage_inprocess.py` | REL-01 (Prompt 136): with every AP silent, no signal-loss and one latched `positioning_offline`; APs back inside the 30 s grace raise nothing for people who refreshed, and hold anyone still missing until the grace has passed; with one AP silent, a person it alone heard is held (logged once) while a person the others heard still alerts; the Omada heartbeat writer's `up_since`. Heartbeats through the real writer, clock patched. Expect `7 passed` (`2975863` fails 6). |
| `cor06_restart_dedup_inprocess.py` | COR-06 (Prompt 136): after a simulated restart (all in-memory state cleared, the fake RTDB kept), an unresolved signal-loss or `positioning_offline` from the same episode isn't repeated and the person is latched; a resolved one, a person who came back and went dark again, or a new outage alert again. Expect `6 passed` (`2975863` fails 5). |
| `f142_active_floors_inprocess.py` | Prompt 142, D1.1-D1.5: two floors active together; activating a floor that shares an AP with an active floor, in the same building or another, is a 409 whose `detail` lists each such floor, its building and the shared APs (one or two conflicts); an AP can be placed on an inactive floor that shares it, but not on an active floor that would clash (409, one sentence naming the floor and building); deactivate-then-activate works; one placement per floor; an unknown floor is a 404. Expect `11 passed` (`3ab8adc` fails 9). |
| `f142_ap_resolution_inprocess.py` | Prompt 142, D1.6, D1.8, D1.9: the Omada ingest resolves an AP to its placement on the active floor; one placed only on an inactive floor is "online, not placed"; activation, moving and placing take effect without the 30 s wait (the ingest's monotonic clock is frozen); deleting a placement keeps the heartbeat while another floor holds the MAC, and a floor delete does the same; the simulators remove by placement id. Expect `11 passed` (`3ab8adc` fails 7). |
| `f142_sweep_inactive_inprocess.py` | Prompt 142, D1.7: the signal-loss sweep skips a stale record on an inactive floor, still alerts on an active floor, an empty `floor_id` or a floor it can't find; `positioning_offline` counts only APs placed on an active floor; with no floor active it raises nothing. APs alive through the ingest's writer, clock patched. Expect `7 passed` (`3ab8adc` fails 3). |
| `f142_calibration_inprocess.py` | Prompt 142, D3: a scale sent with the two points and the distance stores them on the floor as `calibration`; a bad calibration (point off the image, A = B, distance 0 or over 10,000 m, a missing part) is a 422 with one sentence and changes nothing; a scale sent alone clears it; zones are multiplied by old / new px/m so they stay on the same spot of the image, but not on a first calibration or an unchanged scale; APs are re-derived as before. Expect `8 passed` (`3ab8adc` fails 5). |
| `f142_ap_delete_inprocess.py` | Prompt 142, D4: a clean-up failure after an AP is deleted (heartbeat, simulator) still answers 200, with one log line naming the AP; deleting twice is 200 both times; the route update and the camera unlink come before the AP's delete (op log), so a failure there is a 500 with the AP still in place; DIAGNOSE 8's cases (on the patrol route, covered by a camera, loaded by a running patrol or events simulation, no heartbeat node) each delete cleanly. Expect `7 passed` (`3ab8adc` fails 4). |
| `f145_acknowledge_inprocess.py` | Prompt 145, D1: `POST /alerts/{id}/acknowledge` is refused without auth and is a 403 for a user; an admin or the owner gets 200 with `acknowledged_at` (UTC), `acknowledged_by` (the display name, or "admin" when it's empty) and `acknowledged_by_uid`, and only those three fields change in `/alerts` (`resolved` stays false); a second call keeps the first one's values; an unknown alert is a 404 "Alert not found". Fake auth. Expect `7 passed` (`9f28798` has no route: fails 6). |
| `f145_stillness_restart_inprocess.py` | Prompt 145, D3: new stillness `man_down` and `possible_man_down` alerts carry `floor_id` and their anchor; after a simulated restart (in-memory state cleared, the fake RTDB kept), an unresolved one for the same person, floor and spot (acknowledged or not) isn't raised again and the latch is set, for the amber run, the red alert and the upgrade alike; a resolved alert, a pre-145 alert without an anchor, another floor, or a person who moved after the restart (even back to the same spot) alerts again; one `/alerts` read per alert that comes due, none once the person has moved. Only alerts raised in the last 12 h count (`MAN_DOWN_RESTART_MATCH_H`), and not one whose timestamp has no time zone. Someone flipping between two APs, or whose first reading after the restart came from another AP, isn't alerted again; a real move to another AP is. With three APs, someone still between two of them, with a stray reading at the third after the restart, isn't alerted again either. Clock patched, `man_down_minutes` 1, the AP-change hold set to 30 s. Expect `19 passed` (`9f28798` repeats every alert: fails 12; `794261a`, with no age limit and a new strongest AP counted as movement at once, fails 5; `a886862`, where a third AP restarted the 30 s, fails 1). |
| `f143_camera_direction_inprocess.py` | Prompt 143, D2: cameras store `facing_deg` (0 to under 360, clockwise from up; `None` = not set) and `fov_deg` (10-360). Create with and without a facing; a facing without a field of view gets 90; an edit changes only the fields sent; `facing_deg` null clears both (and a field of view sent with it, or alone to a camera with no facing, is ignored); out-of-range values, NaN and Infinity are a 422 with one sentence and write nothing; `GET .../cctvs` returns both fields, `None` for an older record; a direction-only edit doesn't rewrite go2rtc's config or queue a health check. Each check reads the stored document too. Fake auth. Expect `14 passed` (`a1121ea` drops the fields: fails 12). |
| `f143_ap_heartbeat_ip_inprocess.py` | Prompt 143, D4.1: the Omada ingest writes the report's `reporter.ipv4` into `/ap_heartbeats/<MAC>` as `ip`, for a placed AP and for one placed nowhere, but only when it's a dotted IPv4; with none (or an invalid one: out of range, leading zeros, a CIDR, IPv6, an integer, null, a list…) the node has no `ip`, and an earlier report's `ip` doesn't linger. `mac`, `name`, `last_seen` and `up_since` are as before, through `ingest()` and through `POST /telemetry/omada`; simulated heartbeats have no `ip`. Clock patched. Expect `9 passed` (`a1121ea` writes no `ip`: fails 5). |
| `f143_wall_guides_check.ts` | Prompt 143, D1: the placement guides' maths, `frontend/utils/wallGuides.ts`. X and Y for each pair of walls; a point outside the rectangle (and where the walls are extended); fractions → metres → fractions round-trips; typed X and Y give the right point (either side of a wall, from a point on it, clamped at the image's edge) and read back as typed; agreement with `floor_service.derive_ap_metres()`'s numbers for the harness floor and a 597 × 450 floor (taken from a run of the Python function); the localStorage value; the rectangle from a drag and the wall a click picks; the 2-decimal labels and the typed-metres parser; the pixel size used. Prompt 143, D2 (`frontend/utils/cameraFacing.ts`): 0 is up and angles go clockwise with y growing downward (90 right, 180 down); the camera-to-cursor angle is worked out in the image's pixels, not fractions; the handle's whole degrees wrap 359.6 to 0; compass words and the "135° (SE)" label; the cone opens the right way; the dialog's Facing and Field of view boxes. The room's outline (Herman, 18 Nov): its width and height in metres from px/m, equal to the X and Y a device reads on the far walls. **Runs with Node, not Python**, from PowerShell on this PC: `node tools\harness\f143_wall_guides_check.ts` (Node 23.6+ strips the types itself). Needs `frontend/utils` beside `tools/`. Node prints a `MODULE_TYPELESS_PACKAGE_JSON` warning, because `frontend/package.json` has no `"type"`; it's harmless (`--disable-warning=MODULE_TYPELESS_PACKAGE_JSON` hides it). Expect `15 passed` (`a1121ea` has neither module: Node stops with `ERR_MODULE_NOT_FOUND`; `915f170`, before the room's lengths, has no `rectSizeM`: Node stops with a `SyntaxError` naming it). |
| `fixtures/vigi/` | Real InSight S445 alarm payloads (legacy and enhanced), request paths stripped. |
