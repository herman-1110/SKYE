# SKYE Sentinel-AI — Handoff (v6, after Prompt 132 and the 7 Oct follow-ups; updated 2026-10-07 15:45)

Paste this into a new chat to resume. Project: FastAPI + Firebase (Firestore/RTDB/Storage) backend, Next.js/TypeScript frontend. Indoor BLE positioning → safety alerting (man-down, collision, patrol compliance) → real-time patrol tracking and reporting. Plus a VIGI camera integration: alarm events, health, discovery, and now live video. Ghost Patrol is next.

**This replaces v5** (6 Oct), which is in git history: `git show 56882ff:HANDOFF.md`. v4 is archived at `Project\skye-log-archive\HANDOFF-v4-20260930.md`. **Check every claim here against the current code, git history and data before relying on it.**

## Where things stand (7 Oct, 15:45)

- **Prompt 132 (live video) is done, live-checked by Herman, and merged to `main`.**
  - Admins click a camera on the dashboard map and watch it live.
  - Measured: about 2.6 s to the first frame and about 0.5 s delay (Herman waved). HD switching works, and closing the panel stops the camera stream.
- **It took two deviations from the original 132 plan**, both decided by Herman. The details are under "Live view" below.
  - **WebRTC is on the laptop's LAN address, not 127.0.0.1 (option A).** Windows won't let a browser's WebRTC traffic reach loopback.
  - **ffmpeg sits in front of go2rtc (option 2).** go2rtc 1.9.14 drops every frame from this camera.
- **7 Oct follow-ups, all on `main`:**
  - APs can be renamed in the device editor.
  - There's a new CCTV icon and map marker.
  - The camera panel's events list scrolls.
  - "Alarm setup" now reports from the alarms that actually arrive.
- **Git:** everything is merged and pushed to `main` (`ef1a1d3`). The work branch `claude/repo-review-r1fviz` was deleted on GitHub by someone after the merge, then pruned and deleted locally. **Work happens on `main` now.**
- **9 Oct:** the man-down flood is fixed (latch once per episode; live, not committed; Open #1). The go2rtc issue won't be posted (Open #16). `/alerts` was cleared by Herman (Open #2).
- **Next up:** Prompt 133, Ghost Patrol.

## Git

- **Branch:** `main` at **`ef1a1d3`**, the same as `origin/main`. The tree was clean before this handoff update; HANDOFF.md itself is now modified and not committed.
- **`ef1a1d3`** is a merge commit with parents `13e515c` (PR #1's old merge) and `2345c0d`. Its files are identical to the old branch's tip.
- **Fetching and pushing:** use `GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=never git fetch|push origin …`. A plain fetch can hang on a credential prompt.
- **Commits since v5:**

  | Commit | What |
  |---|---|
  | `707ff30`, `56882ff` (Herman, 6 Oct) | HANDOFF v4/v5, the animejs `frontend/package*.json`, the root `package-lock.json` |
  | `6691c8e`, `33e320d`, `5567d92`, `c205b90` | **132:** backend (config, signaling route, settings); `tools/go2rtc/start.ps1`; harness; frontend |
  | `4f63436` | 132: WebRTC on the laptop's LAN address (option A) |
  | `7b8e226` | 132: ffmpeg in front of go2rtc (option 2) |
  | `8a65085` | `docs/go2rtc-sei-issue.md`, the upstream bug report draft |
  | `b5246a4`, `2345c0d` | AP rename route and test; frontend (AP rename, CCTV icon, events scroll, alarm setup) |
  | `ef1a1d3` | merge into `main` |

## Working methodology

- **Prompts:** work comes as numbered "Prompt N" specs (CONTEXT → DIAGNOSE → TASK → VALIDATION, with STOP conditions).
  - If DIAGNOSE contradicts the prompt or a STOP fires, stop and report; don't work around it.
  - A precondition that fails gets reported, not assumed.
  - Smaller requests also come as plain bullet lists (like the 7 Oct follow-ups).
- **Evidence:** use real measurements over assumptions. Cite `file:line`. Never fabricate a measurement or a "yes, it's live". If you said something wrong, correct it plainly.
- **Git:**
  - Commit only when asked, and split commits logically (frontend in its own commit).
  - Run `git diff --cached --stat` right before every commit.
  - **Push only when Herman says so.**
  - Work is on **`main`** now.
  - **HANDOFF.md and Herman's package files are tracked now** (Herman committed them on 6 Oct). Commit changes to HANDOFF.md only when asked. Never modify the package files or `backend/encode.py`.
- **Secrets:**
  - Never print, log, write to a fixture, or commit:
    - `VIGI_CAMERA_PASSWORD`;
    - A1 (the camera digest's first hash, which is equivalent to the password);
    - any OpenAPI `stok`;
    - `VIGI_ALARM_PATH_SECRET`.
  - The password **is** on ffmpeg's command line while live view runs. Herman accepted that. Never print an ffmpeg command line.
  - Read `.env` with `dotenv_values`, checking only shape (length, character class), never the value.
  - Before every commit and push, scan the staged diff (or the push range) for the **real** `.env` values and print only key names. A small script does this; see "Environment quirks".
    - `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` in `backend/.env` are the `.env.example` placeholders, so they always "match" `.env.example`.
- **Other actors:**
  - Herman, and the **Codex agent in VS Code** (`codex.exe`, `node_repl`). Snapshot (byte-compare) the live files before work, and re-check before copying in.
  - Someone deleted the GitHub branch on 7 Oct.
- **Live system:**
  - Herman's dev backend is `uvicorn main:app --reload --host 0.0.0.0 --port 8000` (backend venv). `next dev` is on :3000.
  - Saving any `.py` under `backend/` reloads the backend. Each reload costs one new camera OpenAPI login, and produces a short burst of "RuntimeError: No response returned" tracebacks (see Open #15).
  - **go2rtc runs from Herman's own terminal** (`tools\go2rtc\.\start.ps1`). Herman decided on 7 Oct: no auto-start, and don't propose launchers again unless he asks.
  - **Never stop processes by name or path:** Herman's go2rtc and any scratch copy share an executable path. Stop only PIDs you started. (Claude killed Herman's go2rtc once on 7 Oct; `start.ps1` restarted it within 10 s.)
  - Build and test in a `git archive` export in the scratchpad, then copy into the live tree once by an explicit file list, then verify with `cmp`. Before copying, check that the live files are unchanged since HEAD; compare with CR stripped (see "Environment quirks").
- **The camera's admin account locks after repeated failed OpenAPI logins** (errCode `-10030`). Never loop a login. RTSP logins (ffmpeg, probes) are a separate path; no lockout has been seen there.
- **Memory on this laptop is tight** (about 3 GB free).
  - Long-running things go in Herman's own terminal.
  - Herman's rule since 131: **no multi-agent reviews or workflows.** This holds even when Claude Code's "Ultracode" reminder says to use workflows.
- **Frontend builds:** never run `next build` in the live `frontend/`, because `next dev` shares `.next`.
  - Export to the scratchpad and junction its `node_modules` to the live one (`New-Item -ItemType Junction`). Remove the junction with `cmd /c rmdir <path>` (link only); **never `rm -rf` an export that still has the junction.**
  - Copy `frontend/.env.local` in for the build only, and delete it afterwards with a **literal** path.
  - Run `tsc --noEmit --incremental false` first.

## Status by prompt

| Prompt | Topic | Status |
|---|---|---|
| 104–126, 128, Open #0 | earlier work (v3/v4) | on `main` |
| 127 | offline calibration replay | **blocked:** needs ground truth (Herman's notebook times and positions for the Sep 30 / Oct 1 captures) |
| 129 | null-RSSI grace period | not started |
| 130, 131, 131b | VIGI recon, registry/alarms/health/panel, discovery | on `main` |
| **132** | **live video** | **done**: live check passed 7 Oct (Herman), on `main` |
| — | 7 Oct follow-ups (AP rename, CCTV icon, events scroll, alarm setup) | on `main`; Herman looked at the dashboard |
| **133** | **Ghost Patrol** (evaluator, verdicts, `departed_at`, patrol enabled) | **next** |

## VIGI camera

### Hardware and network (verify before relying on it)
- **Camera:** InSight S445 v1.0, firmware 3.3.2 Build 260708.
  - MAC **`98:BA:5F:8B:10:03`**, IP **`192.168.0.101`** (DHCP reservation asked for, never verified).
  - Time zone UTC+08:00. Its clock runs about 0.7 s behind the laptop.
- **Laptop:** **`192.168.0.2`** on Ethernet (`54-05-DB-C4-A5-78`), from DHCP on 7 Oct.
  - It was `.5` on 6 Oct, which was supposed to be reserved in Omada, so **the reservation isn't holding**.
  - On the morning of 7 Oct a Wi-Fi address (`192.168.123.132`) was also up; it was gone by 15:45.
  - Live view follows the address automatically (see below).
- **Alarms:** they were arriving on 7 Oct with the laptop at `.2` (last checked 09:21; the camera panel shows "Working").
  - The camera's Alarm Server entry wasn't re-read; the OpenAPI can't read it.
  - Path: `/vigi/alarm/<VIGI_ALARM_PATH_SECRET>` on port 8000. Enhanced Alarm Message Service is ON and human detection is on.
- **APs** posted from `.3`, `.4` and `.6`.

### What the camera sends (130 captures, archived)
- **The push:** JSON only, with **no auth header**, so the path segment is the credential. A new connection per event.
- **Legacy format:** `event_list: [{dateTime, event_type: [...]}]`.
- **Enhanced format:** `camera: "1"`, `dateTime: "YYYY-MM-DD HH:MM:SS"`, `event_type` is a string, `extra_text` is a list of objects (`obj_num`, `region_id[]`, `obj_rect_info[]`).
- **Event types:** `MOTION` can arrive alone; only `PEOPLE` means a person. An empty scene sends nothing.

### Streams and APIs
- **Streams:**
  - `stream1`: H.264 High, 2688×1520, 25 fps;
  - `stream2`: H.264 High@3.0, 848×480, 25 fps, about 520 kbit/s with movement;
  - `stream6`: JPEG, 1 fps.
- **RTSP:** port 554, Digest MD5, user `admin`. Audio is PCMA.
- **Measured 6 Oct (stream2):**
  - An IDR every 2.0 s, starting with the first frame after PLAY.
  - **Every frame ends with a 61–97 byte SEI NAL that carries the RTP marker bit.** That's what breaks go2rtc's RTSP reader.
  - The SDP advertises `a=smart_encoder:virtualIFrame=1`. The camera's web UI has no Smart Coding setting.
- **ONVIF:** port 2020. **OpenAPI:** HTTPS on 20443, self-signed. It has no method that reads the Alarm Server settings, so `alarm_config` is only ever `mismatch` or `unknown`.
- **Discovery:** answers one ONVIF WS-Discovery probe, with its MAC in a scope.

### Backend as built (131/131b; see the commit messages)
- **Settings:**
  - `VIGI_ALARM_PATH_SECRET`, `VIGI_CAMERA_PASSWORD`, both hidden from repr.
  - `VIGI_RAW_DUMP_ENABLED` (false).
  - `VIGI_LIVENESS_INTERVAL_S` 5, `VIGI_OPENAPI_INTERVAL_S` 300, `VIGI_OPENAPI_START_DELAY_S` 60, `VIGI_DISCOVERY_INTERVAL_S` 60.
  - For 132's settings, see "Live view".
- **Registry:** `buildings/{b}/floors/{f}/cctvs`, with `source_type`, `device_mac`, `channel`, `ip`, `checkpoint_ap_id` and `timezone`.
  - `camera_key` is `"ipc:98BA5F8B1003:1"`.
  - `(device_mac, channel)` is unique.
  - The live camera is on the TPLink floor (`fc6e663e…`) with **no checkpoint yet**.
- **`POST /vigi/alarm/{secret}`:**
  - The secret is compared in constant time; a wrong one gets a 404.
  - Only a registered MAC from its registered IP is buffered and sets `last_event_at`.
  - Every logged path under `/vigi/alarm/` reads `/vigi/alarm/***`.
- **`GET …/cctvs/{id}/detections`:** last 15 minutes, in memory; `require_auth_strict`.
- **`POST /cctvs/discover`:** admin only.
- **Heartbeat** `/cctv_heartbeats/98_BA_5F_8B_10_03`:

  | Field | Meaning |
  |---|---|
  | `last_seen` | last TCP connect to port 554 that succeeded |
  | `last_event_at` | last accepted alarm |
  | `probe`, `probe_ok_at` | OpenAPI health |
  | `alarm_config` | `mismatch` or `unknown` |
  | `discovered_at`, `discovered_via`, `ip`, `ip_mismatch` | from discovery |

- **OpenAPI lockout guard:** `backend/logs/vigi-openapi-lockout-<camera_key>.json`.
- **`PATCH /buildings/{b}/floors/{f}/aps/{ap_id}`** (7 Oct, admin): renames an AP, name only.
  - The name is trimmed, at most 64 characters; blank or too long is a 422, an unknown AP a 404.
  - New patrol logs pick the new name up within the 30 s AP caches.

### Live view (Prompt 132, as built)
- **Flow:**
  1. An admin opens the camera panel (`CameraLiveView.tsx`).
  2. The browser makes a recvonly video-only offer, with no ICE servers, gathering for up to 2 s.
  3. It posts to `POST /buildings/{b}/floors/{f}/cctvs/{id}/webrtc`: `require_admin_strict` (401 without auth), 30/minute.
  4. The backend (`services/live_view_service.py`) checks:
     - the camera exists (404);
     - the offer only receives video (422; go2rtc would treat a sending offer as a publisher);
     - it isn't an NVR camera and has a MAC and an IP (409);
     - it was seen in the last 10 s (409 "offline").
  5. The backend then rewrites the go2rtc config if needed and checks that ffmpeg exists (503).
  6. It forwards the offer to go2rtc: `POST http://127.0.0.1:1984/api/webrtc?src=ipc_98BA5F8B1003_1_sub` (or `_main` for HD).
  7. It returns **only the SDP answer**. Each opened stream logs `[LIVE] … answer candidates: <ip>:8555 tcp, <ip>:8555 udp`.
- **Errors are fixed sentences; go2rtc's error text is never passed on or logged.**
  - 503 "Live view isn't running on the server" (go2rtc down).
  - 503 "Live view hasn't picked up this camera yet…" (go2rtc returned 404).
  - 503 "isn't fully installed" (no ffmpeg).
  - 502 (stream failed) and 504 (too slow).
- **Binaries** (gitignored, in `tools/go2rtc/bin/`):
  - **go2rtc 1.9.14**, from the official GitHub release `go2rtc_win64.zip`: zip SHA-256 `dd4167d7…c939907`, exe `923d5725…7d68f8c`.
  - **ffmpeg 9.0.2**, gyan.dev essentials `ffmpeg-9.0.2-essentials_build.zip`: zip SHA-256 `60f46726…3fa2047ba`, exe `3256173f…1ed8edec`.
  - Both are unsigned; Defender scans were clean.
- **The config** is generated by the backend at `GO2RTC_CONFIG_PATH` (default `tools/go2rtc/go2rtc.yaml`, gitignored). It's written at startup, after every camera create, edit or delete, and before every viewing, but **only when its content changes**, and atomically.
  - `app.modules: [api, webrtc, exec]`. No RTSP module (so no RTSP server) and no HomeKit SRTP.
  - API on `127.0.0.1:1984` with `allow_paths: ["/api", "/api/webrtc"]` (no web UI, no streams/config/log API). go2rtc also refuses `exec` sources from its API.
  - `exec.allow_paths`: only the ffmpeg path.
  - WebRTC `listen` and `candidates` on `<LAN address>:8555`, `ice_servers: []`, filters `networks: [udp4, tcp4]`.
    - The address is `GO2RTC_WEBRTC_HOST`, else the local address on the route to the registered camera, else 127.0.0.1.
    - Today it's `192.168.0.2:8555`.
  - `log.output: file:go2rtc.log`, at info level. go2rtc masks `${VAR}` values as `***` in its log.
  - Streams `ipc_<MAC>_<ch>_sub|main` are each `exec:<ffmpeg> -hide_banner -loglevel quiet -nostdin -fflags nobuffer -rtsp_transport tcp -i rtsp://admin:${VIGI_CAMERA_PASSWORD}@<ip>:554/stream2|stream1 -map 0:v:0 -c:v copy -bsf:v filter_units=remove_types=6 -an -f mpegts -muxdelay 0 -muxpreload 0 -`.
    - The pipe bypasses go2rtc's RTP depacketizer, and the bitstream filter strips the SEI.
    - `-loglevel quiet` keeps ffmpeg's error text, which would contain the address, out of every log and API response.
    - The file holds `${VIGI_CAMERA_PASSWORD}`, never the value.
- **Settings:**
  - `GO2RTC_API_URL` (`http://127.0.0.1:1984`).
  - `GO2RTC_CONFIG_PATH`.
  - `GO2RTC_WEBRTC_HOST` (empty means auto).
  - `GO2RTC_FFMPEG_PATH` (default `tools/go2rtc/bin/ffmpeg.exe`).
  - A relative path is taken from `backend/`.
- **`tools/go2rtc/start.ps1`**, run by Herman in its own terminal:
  - It reads `VIGI_CAMERA_PASSWORD` from `backend/.env` on every launch, rejects characters other than letters, digits and `- _ . ~`, and passes the password only through go2rtc's process environment.
  - It relaunches go2rtc when:
    - the config changes (a camera, or the laptop's address);
    - the password changes;
    - go2rtc dies.
  - Other `.env` edits don't relaunch it.
  - It stops go2rtc **with its process tree** (`taskkill /T`), so no ffmpeg is left on the camera.
  - It warns if ffmpeg is missing, and rotates `go2rtc.log` past 10 MB.
  - It prints only its own lines, such as "go2rtc running on 127.0.0.1:1984" and the restarts.
- **Why not the original plan:**
  - **Loopback:** a socket bound to the LAN address can't send to 127.0.0.1 on Windows (WSAEADDRNOTAVAIL, reproduced). A browser's WebRTC sockets are bound to the LAN address, so go2rtc can't be on loopback only. That's option A.
    - The laptop's own browser reaches its LAN address without leaving the machine. Windows Firewall's inbound **Block** rules for go2rtc (Public profile, created when the prompt was refused) keep other devices out; local traffic isn't subject to them (tested).
  - **The SEI bug:** go2rtc 1.9.14's `pkg/h264/rtp.go:45-48` drops a marked SEI under 128 bytes without flushing the access unit. With this camera, no frame is ever emitted: ICE and DTLS connect, but there's zero RTP. It's unchanged on master. That's option 2, ffmpeg. The upstream report is drafted in `docs/go2rtc-sei-issue.md`.
  - **Restart:** go2rtc's `POST /api/restart` does nothing on Windows (it uses `syscall.Exec`). Hence `start.ps1` watches the config.
- **Measured on 7 Oct, one HD viewer:**
  - go2rtc 0.64% CPU (5% of one core), 29 MB; ffmpeg 0.15% CPU, 19 MB. go2rtc idle is about 14 MB.
  - ffmpeg exits as soon as the viewer leaves.
  - Switching HD replaces the ffmpeg.
- **Listening:** `127.0.0.1:1984` (TCP), and `<LAN>:8555` TCP and UDP.
  - Per session, pion's mDNS also opens `0.0.0.0:5353` and an `0.0.0.0`/`[::]` pair on random ports. Herman accepted these (go2rtc can't turn them off).
  - Anything else listening off loopback would be a STOP.
- **Viewing from other devices:** not built. It would need an inbound Allow rule for TCP and UDP 8555, which Herman adds himself, plus dashboard access.

### Frontend as built (camera parts)
- **`CameraPanel`:** opened by clicking a camera marker.
  - Live video for admins; others see "Live view: admins only".
  - An HD toggle, which opens a new connection.
  - States: connecting, live, the backend's sentence, camera offline, failed, with Try again.
  - Status, health and checkpoint rows.
  - **"Alarm setup"** from `last_event_at`:
    - green "Working: the camera's alarms are reaching SKYE (last one … ago)" within 24 h;
    - an older or missing alarm points to Settings > Event > Alarm Server;
    - human detection off still warns.
  - **The recent events list** scrolls in a box about 10 rows tall, with a sticky header and up to 200 rows.
- **`CctvIcon` / `CctvMarker`** (`components/map/CctvIcon.tsx`):
  - One glyph, a camera tilted down on a wall bracket, used in every place a camera is drawn.
  - On the maps it sits in a round chip with a red ring; the dashboard keeps the status dot.
- **Device editor:**
  - Camera add and edit, with the "online but not placed" list and Scan now.
  - **AP rename** (pencil on each AP row; the MAC is shown read-only).

### Herman's decisions
| # | Decision | Status |
|---|---|---|
| 2 | Patrol stays off until Ghost Patrol (both floors: `patrol_enabled=false`, empty route) | applies in 133 |
| 3, 4 | The verdict is stored on the patrol log; the window pads are ±10 s | 133 |
| 6, 7 | Live view over WebRTC with backend signalling; audio off | done (132) |
| A2 | `alarm_config` (mismatch/unknown) feeds the verdicts somehow | 133 |
| A3 | Herman draws the camera's detection area | 133 |
| 7 Oct | Option A (WebRTC on the LAN address); option 2 (ffmpeg in front); mDNS sockets accepted; password on ffmpeg's command line accepted; API hardening; go2rtc started by hand (no auto-start); work on `main` | done |

The design notes are in `docs/vigi-integration-design.md`: section 7 (Ghost Patrol) and section 8 (live view; **section 8 is partly superseded**, see Open #10).

## Field captures and archive
- **Archive:** `C:\Users\Intern\Downloads\Omada\Project\skye-log-archive\`. Out of git, and `MANIFEST.csv` lists every file with its SHA-256. It holds:
  - every `skye*.log` recovered from the Recycle Bin (7 to 22 Sep, including the 10 Sep calibration run 2);
  - the field captures from **30 Sep** (`skye-20260930-052440.log`, AP data 13:24–13:48) and **1 Oct** (`skye-20261001-012430.log`, AP data 09:24–09:56), both with the dump on;
  - `vigi-2026-10-05\`: the alarm captures (redacted) and Prompt 130's retired `secret_path.txt`;
  - the old handoffs (7 and 8 Sep, and v4).
- **The dump-on logs contain the Omada ingest token**, which is the known placeholder value. Keep them out of git.
- **The 10 Sep stationary evidence** is in `docs/evidence/`.
- **`OMADA_RAW_DUMP_ENABLED=false`** in `backend/.env`. The dump goes on only for captures, and each change needs a restart.

## Null-RSSI (unchanged since v4)
- No null-RSSI buffer or grace period exists. Nulls arrive as `"rssi": {}`, and the APs report about once a second.
- On the Sep 7 replay, a 2 s grace would lift 3-AP decisions from 73% to 95.5%. That's input for Prompt 129.

## Open threads — ask Herman, don't assume
1. **Man-down stillness alert flood: fixed 9 Oct, live, not committed yet.** Herman chose latch once per stillness episode.
   - `_still_alerted` in `safety_service.py`: one stillness alert per episode, cleared wherever the anchor is (re)seeded (cold start, approximate→exact upgrade, movement past the epsilon). The 30 s gate stays.
   - A beacon that goes dark and comes back still within epsilon of the same anchor is the same episode, so there's no second stillness alert. A resolved alert doesn't re-fire until the person moves.
   - Test: `tools/harness/man_down_latch_inprocess.py` (6/6; HEAD before the fix fails 4, with 116 extra alerts in an hour).
2. **`/alerts` was cleared before 5 Oct 11:13:** Herman did it (answered 9 Oct). Resolved.
3. **Prompt 127** needs ground truth for the Sep 30 and Oct 1 captures.
4. **Prompt 129,** the null-RSSI grace period, is not started.
5. **The simulator's Ghost Patrol bug:** `simulation_events._write_patrol_log` calls `verify_multimodal` for every record, so its missed-checkpoint segment also raises a spurious `ghost_patrol`. Matters for 133.
6. **Kalman lock-up** (`kalman_service.py`): solves more than 8 m away are rejected and still refresh `_last_seen`. A "reset after 3 rejections" fix was proposed and never decided.
7. **Sep 23 ingest latency** (median 322 ms, p99 2.3 s) is unexplained.
8. **`.env` changes need a backend restart.** `--reload` only watches `.py` files. (`start.ps1` re-reads the camera password by itself.)
9. **`GET /health/tracker`** has no frontend consumer.
10. **Stale docs:**
    - **`docs/vigi-integration-design.md` §8** describes the route as `/api/cameras/{id}/webrtc`, pins a `.6` LAN candidate, and has go2rtc reading RTSP itself. As built: the cctv-shaped route, an auto-detected LAN address, ffmpeg in front, and `start.ps1` restarts.
    - `SYSTEM_OVERVIEW.md` still describes `/vigi/detection` and says the patrol tracker is "future".
    - `README.md:114` documents a setting that doesn't exist (`MAN_DOWN_MOVEMENT_THRESHOLD`).
    - The `COLLISION_DISTANCE_M` comment in `.env.example` is wrong.
    - `kalman_service.py:13-16` still says "~2 s cadence".
    - `patrol_tracker_service.py:14-17` refers to "Level 2".
    - The `TEMP-MEASURE-119` prints are still live.
11. **Radius settings:** `PATROL_PROXIMITY_RADIUS_M` is 1.0. The per-floor field is ignored, and a newly created floor would store 0.0.
12. **Unchanged since v3:**
    - the "Mystery Man" beacon (`7E66DA30-…`, "pika");
    - whether 117's hysteresis is live is inconclusive;
    - an untracked Firestore composite index;
    - `eac8b38`'s beacon-delete cleanup ignores simulated beacons.
13. **User-owned:**
    - `backend/encode.py` (gitignored; a plaintext camera password): don't touch it.
    - Firestore `man_down_minutes`: don't touch it.
    - The animejs `frontend/package*.json` and the root `package-lock.json` are in git now; don't modify them.
14. **DHCP:** the laptop's `.5` reservation didn't hold (it's `.2` now). The camera's `.101` reservation was never verified. Live view adapts by itself; check the camera's Alarm Server target if alarms stop.
15. **Reload noise:** right after every backend reload there's a 1–2 s burst of 3–15 "RuntimeError: No response returned" tracebacks. These are requests queued during the reload, in Starlette's BaseHTTPMiddleware. It's pre-existing (also seen 5 Oct) and harmless, but noisy.
16. **`docs/go2rtc-sei-issue.md`: not posting** (Herman, 9 Oct). The ffmpeg workaround is enough for SKYE; don't raise it again unless he asks. The draft is kept: it cites `master` `c245815` (bug still there on 9 Oct) and links #2277 ("VIGI no video"). Its `/api/streams` figures come from the MP4 consumer, not WebRTC.

## Test harness (`tools/harness/`; `tools/harness/README.md` has the commands)
- **Point it at a `git archive` export, never the live `backend/`:**
  ```bash
  git archive HEAD backend tools | tar -x -C "$exp"
  ```
  Run with `py=backend/venv/Scripts/python.exe`, as `"$py" -B …`. It refuses port 8000.
- **The suites and expected results:**

  | Suite | Expect |
  |---|---|
  | `selftest.py` | PASS |
  | `run_smoke.py` | 46/46 requests answered 200 |
  | `vigi_131_test.py --port 8003` | 34/34 |
  | `vigi_131_inprocess.py` | 5/5 |
  | `vigi_131b_inprocess.py` | 9/9 |
  | `vigi_132_inprocess.py` | **29/29** (fake go2rtc; a `ConnectionAbortedError` traceback from the fake's slow reply is expected) |
  | `ap_rename_inprocess.py` | **4/4** |

- **Run `run_smoke.py` with the repo's own harness against the export.** The export's copy of the driver reads `<export>/backend/.env`, which `vigi_131_test.py` leaves holding fake values, so the result is 46 × 401.
- **The launcher** sets `VIGI_DISCOVERY_INTERVAL_S=0`, `GO2RTC_CONFIG_PATH=<run_dir>/go2rtc.yaml` and `GO2RTC_API_URL` to a dead port unless the caller sets them. So no harness server multicasts on the LAN or touches the live go2rtc.
- **Opt-in switches:**
  - `HARNESS_FAKE_AUTH=1` (`harness-token:<uid>`);
  - `HARNESS_ENV_PATH` (a test `.env`).

## Environment quirks
- **Shells:** PowerShell is primary; the Bash tool is Git Bash.
- **Python:** `backend\venv\Scripts\python.exe` is a **uv trampoline**, so kill the PID a process reports for itself. The real interpreter is `%APPDATA%\uv\python\cpython-3.12-…`, and the firewall Allow rules are for it. The network profile is Public.
- **Line endings:**
  - `core.autocrlf=true`; the working tree and `git archive` output are CRLF.
  - Keep edited files CRLF.
  - **Git Bash `sed -i` strips the CRs** (re-add them with `sed -i 's/$/\r/'` or use the Edit tool).
  - Python's `read_text`/`write_text` also convert; use bytes.
- **Hashing in Git Bash:** `sha256sum` prefixes its output with `\` for paths containing backslashes. Compare with `cmp`, or cut carefully.
- **Bash tool:** a `\\` inside a heredoc can reach Python as `\`. For text containing escapes, use the Edit tool.
- **Claude Code safety checks:**
  - `rm -rf "$VAR/…"` and `Remove-Item "$X\…"` with variable paths are blocked. Use `"${VAR:?}"` or literal absolute paths.
  - A blocked command doesn't run at all.
- **Logs:**
  - `backend/logs/` captures are UTF-8; one file per backend process start. Nothing prunes `backend/logs`.
  - `tools/go2rtc/go2rtc.log` rotates at 10 MB.
- **Tools:**
  - `openssl` and `pdftotext` are in Git Bash.
  - Chrome 154 and Edge 154 are installed; headless Chrome is good for WebRTC checks (getStats) and for rendering previews to PNG.
  - `gh`, `gcloud` and `ffprobe` aren't installed.
- **Firebase:** the CLI is authenticated to `skye-3fa05`; deploys need an explicit go-ahead. The backend uses service-account key `fdcac568`; the old leaked key `6f81d665` is revoked.
- **Identities:**
  - real beacons: `guard-001`, `worker-001`;
  - simulated: `sim-*`, `test-*`; the simulator's fake camera heartbeat is `A8:57:4E:3C:11:01`.
- **Hardware:** APs `40:AE:30:9D:34:5A`, `40:AE:30:9D:34:5C` (EAP660 HD) and `A8:29:48:C3:88:A0` (EAP770). The active floor is "TPLink" (`fc6e663e…`) in building `53c3872f…`.
- **Diagnostic scripts from 6–7 Oct** live in that session's scratchpad (`webrtc-diag/`, `e2e/`). They're useful as patterns:
  - a minimal RTSP client that logs NAL types and marker bits;
  - a headless-Chrome WebRTC stats page;
  - a scratch go2rtc on other ports.

  The scratchpad is temporary.

## Suggested first message in the new chat
"Continue from HANDOFF.md v6. Before anything else:
1. Run `git status` and `git log` fresh. We work on `main` now; it was at `ef1a1d3`. Ask me before committing anything.
2. Decide with me on the man-down stillness flood (Open #1).

Then start Prompt 133 (Ghost Patrol) from `docs/vigi-integration-design.md` §7 and decisions 2, 3, 4, A2 and A3. Leave `man_down_minutes` and `backend/encode.py` alone, keep secrets out of all output, and no multi-agent workflows."
