# SKYE Sentinel-AI — Handoff (v7, after Prompts 134 and 135; updated 2026-10-16)

Paste this into a new chat to resume. Project: FastAPI + Firebase (Firestore/RTDB/Storage) backend, Next.js/TypeScript frontend. Indoor BLE positioning → safety alerting (man-down, collision, patrol compliance) → real-time patrol tracking and reporting. Plus a VIGI camera integration: alarm events, health, discovery and live video. Next up is Prompt 136 (man-down and collision), then 133 (Ghost Patrol).

**This replaces v6** (7 Oct, with 9 Oct additions), which is in git history: `git show 2f00309:HANDOFF.md`. v5 is `git show 56882ff:HANDOFF.md`; v4 is archived at `Project\skye-log-archive\HANDOFF-v4-20260930.md`. **Check every claim here against the current code, git history and data before relying on it.**

## Where things stand (16 Oct)

- **Prompt 134, a whole-project review, is done** (9 Oct). It found 62 findings, each with an ID (`COR-xx`, `SEC-xx`, `REL-xx`, …), and set a fix plan (below).
  - **It stays off GitHub, because the repo is public.** It lives only on the local branch `review/134` (`f0ecffc`). Read it with `git show review/134:docs/reviews/2026-10-09-project-review.md`.
  - Never push that branch or put the review on `main`.
- **Prompt 135 (credentials and quick safety stops) is done and on `main`.**
  - Herman fast-forwarded `main` to `13491a9` and pushed it on 16 Oct, without a PR.
  - The live check passed:
    - **L1** (rotated token, APs answered 200): passed, as Herman reported on 16 Oct. No capture log on disk shows those posts.
    - **L2** (`OMADA_INGEST_ALLOWED_IPS`): left unset, because the APs have no DHCP reservations.
    - **L3** (simulator): passed on 14 Oct.
  - What changed is under "Git" below; the full report is in `Project\skye-scratch\135\report.md`.
- **The Omada ingest token was rotated on 13 Oct.** The new value is in `backend/.env` and on the controller. The old value, which was committed in `backend/payload.json`, is now worthless.
- **9 Oct:** the man-down stillness latch (Open #1) was committed in `2f00309`.
- **README.md was rewritten in v7** against the code at `13491a9`. It covers:
  - Python and Node version tables, tested on 16 Oct;
  - installation;
  - Firebase set-up step by step;
  - every setting;
  - the AP and camera set-up, and the simulators;
  - troubleshooting;
  - the folder layout.
- **The 134 fix plan, in order** (the review's own titles):
  1. 135: credentials and quick safety stops (**done**).
  2. **136: man-down and collision correctness (next).**
  3. 133: Ghost Patrol, plus its prerequisites.
  4. 137: Firebase rules and account controls.
  5. 138: reports and the simulator.
  6. 139: positioning robustness and observability (with 127 and 129).
  7. 140: reliability and housekeeping.
  8. 141: documentation pass.

  **This replaces v6's "next up: 133".** The review moved 133 after 136.

## Git

- **Branch:** `main`. The last code commit is **`13491a9`**, pushed to `origin/main` on 16 Oct. This handoff (v7) and the README rewrite are one docs commit on top of it.
- **Other branches:**
  - `fix/135-credentials-safety-stops` (local and on GitHub, `13491a9`) is fully merged. Deleting it is Herman's call.
  - `review/134` (`f0ecffc`) is local only and has no upstream. **Never push it.** Local `main` no longer contains `f0ecffc`.
- **Fetching and pushing:** use `GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=never git fetch|push origin …`. A plain fetch can hang on a credential prompt.
- **Commits since v6:**

  | Commit | What |
  |---|---|
  | `388d01c` (Herman, 7 Oct) | HANDOFF v6 |
  | `2f00309` (Herman, 9 Oct, "Camera") | Man-down stillness latch (Open #1), `tools/harness/man_down_latch_inprocess.py`, and the 9 Oct doc updates |
  | `4d3b3b3` | **135**, SEC-04: the raw Omada dump prints `***` for `meta.access_token` |
  | `d602487` | **135**, SEC-01: `/telemetry` accepts loopback callers only; the optional `OMADA_INGEST_ALLOWED_IPS` for `/telemetry/omada`; `backend/payload.json` untracked |
  | `8a46dd4` | **135**, COR-05 and CON-04: simulated people leave `/positions` when their simulation ends; the lifespan stops a running simulation and removes leftovers at startup |
  | `a0a081d` | **135**, COR-12 (simulator half): each scripted event raises only its own alert |
  | `191594a` | **135**, COR-01: `/telemetry` timestamps are validated; the signal-loss sweep skips a bad record |
  | `b5adf49` | **135**, COR-08: deleting a patrol-route AP no longer fails with a 500 |
  | `041090c` | **135**, HYG-03 (part): `frontend/tsconfig.tsbuildinfo` untracked |
  | `73b0e3f` | The stray root `package-lock.json` removed (Herman asked, 14 Oct) |
  | `13491a9` (Herman, 14 Oct, "done") | `frontend/package-lock.json` after his `npx update-browserslist-db@latest` |

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
  - Work is on **`main`** now. A prompt that needs a branch says so (135 used `fix/135-credentials-safety-stops`).
  - **HANDOFF.md and README.md are tracked.** Commit changes to them only when asked. Never modify `frontend/package*.json` (Herman's own lockfile update is `13491a9`) or `backend/encode.py`.
  - **The repo is public.** Never put the 134 review's text, or any description of a **security** finding (`SEC-xx`) that isn't fixed yet, into a tracked file, a commit message or a push. Correctness, reliability and documentation items can be described (the open threads below do), and so can fixed findings, whose IDs the commit messages already carry.
  - **Herman runs git commands himself from these messages**, including steps labelled as Claude's: on 16 Oct he ran the post-merge switch before anything was merged. Give him copy-paste commands in the order he should run them, with any precondition (such as "merged on GitHub") stated before the command.
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
- **Memory on this laptop is tight** (2–3 GB free; 2.25 GB at the start of 135, with Chrome using 4.4 GB).
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
| — | man-down stillness latch (Open #1) | on `main` (`2f00309`, 9 Oct) |
| 134 | whole-project review | **done** (9 Oct); local branch `review/134` only, never pushed |
| **135** | **credentials and quick safety stops** | **done**: live check passed (L1 16 Oct, on Herman's word; L3 14 Oct); on `main` (`13491a9`, 16 Oct) |
| **136** | **man-down and collision correctness** | **next** (the review's fix plan) |
| 133 | Ghost Patrol (evaluator, verdicts, `departed_at`, patrol enabled), plus the review's prerequisites | after 136 |
| 137–141 | rules and account controls; reports and simulator; positioning; reliability; docs | planned, in that order |

## VIGI camera

### Hardware and network (verify before relying on it)
- **Camera:** InSight S445 v1.0, firmware 3.3.2 Build 260708.
  - MAC **`98:BA:5F:8B:10:03`**, IP **`192.168.0.101`** (DHCP reservation asked for, never verified).
  - Time zone UTC+08:00. Its clock runs about 0.7 s behind the laptop.
- **Laptop:** Ethernet (`54-05-DB-C4-A5-78`) gets its address from DHCP, and it keeps moving: `.5` on 6 Oct (supposedly reserved in Omada, so **the reservation isn't holding**), `.2` on 7 Oct, `.6` on 9 Oct.
  - **From 12 to 16 Oct the Ethernet link was down**, and only Wi-Fi was up: `192.168.123.23` on 12 Oct, `192.168.123.13` on 15 Oct (go2rtc's WebRTC address in that day's log), `192.168.122.152` on 16 Oct.
  - While Ethernet was down, no AP report reached the backend: the 14 Oct and 15–16 Oct captures hold none. Check the link first if no markers move.
  - Live view follows the address automatically (see below).
- **Alarms:** they were arriving on 7 Oct with the laptop at `.2` (last checked 09:21; the camera panel shows "Working").
  - The camera's Alarm Server entry wasn't re-read; the OpenAPI can't read it.
  - Path: `/vigi/alarm/<VIGI_ALARM_PATH_SECRET>` on port 8000. Enhanced Alarm Message Service is ON and human detection is on.
- **APs** posted from `.3`, `.4` and `.6` on 7 Oct, and from `.2`, `.3` and `.5` on 9 and 13 Oct. They have no reservations either.

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
    - It was `192.168.0.2:8555` on 7 Oct, and `192.168.123.13:8555` (Wi-Fi) on 15 Oct.
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
| 9 Oct | Man-down: latch one stillness alert per episode (Open #1) | done (`2f00309`) |
| 14 Oct | Remove the stray root `package-lock.json` and root `node_modules` (Herman ran the deletes; Claude Code's auto mode blocks them) | done (`73b0e3f`) |
| 15 Oct | The 134 review stays on the local branch `review/134` and is never pushed | standing |
| 15–16 Oct | `OMADA_INGEST_ALLOWED_IPS` stays unset until the APs have DHCP reservations; CIDR support was offered as a follow-up | standing |
| 16 Oct | 135 merged by fast-forward from Herman's terminal, without a PR | done |

The design notes are in `docs/vigi-integration-design.md`: section 7 (Ghost Patrol) and section 8 (live view; **section 8 is partly superseded**, see Open #10).

## Field captures and archive
- **Archive:** `C:\Users\Intern\Downloads\Omada\Project\skye-log-archive\`. Out of git, and `MANIFEST.csv` lists every file with its SHA-256. It holds:
  - every `skye*.log` recovered from the Recycle Bin (7 to 22 Sep, including the 10 Sep calibration run 2);
  - the field captures from **30 Sep** (`skye-20260930-052440.log`, AP data 13:24–13:48) and **1 Oct** (`skye-20261001-012430.log`, AP data 09:24–09:56), both with the dump on;
  - `vigi-2026-10-05\`: the alarm captures (redacted) and Prompt 130's retired `secret_path.txt`;
  - the old handoffs (7 and 8 Sep, and v4).
- **The dump-on logs contain the old Omada ingest token**, which was rotated on 13 Oct and is now worthless. Keep them out of git anyway. Since 135 (SEC-04), new dumps print `***` in its place.
- **The 10 Sep stationary evidence** is in `docs/evidence/`.
- **`OMADA_RAW_DUMP_ENABLED=false`** in `backend/.env`. The dump goes on only for captures, and each change needs a restart.

## Null-RSSI (unchanged since v4)
- No null-RSSI buffer or grace period exists. Nulls arrive as `"rssi": {}`, and the APs report about once a second.
- On the Sep 7 replay, a 2 s grace would lift 3-AP decisions from 73% to 95.5%. That's input for Prompt 129.

## Open threads — ask Herman, don't assume
1. **Man-down stillness alert flood: fixed and committed** (`2f00309`, 9 Oct). Herman chose latch once per stillness episode.
   - `_still_alerted` in `safety_service.py`: one stillness alert per episode, cleared wherever the anchor is (re)seeded (cold start, approximate→exact upgrade, movement past the epsilon). The 30 s gate stays.
   - A beacon that goes dark and comes back still within epsilon of the same anchor is the same episode, so there's no second stillness alert. A resolved alert doesn't re-fire until the person moves.
   - Test: `tools/harness/man_down_latch_inprocess.py` (6/6; the code before the fix fails 4, with 116 extra alerts in an hour).
2. **`/alerts` was cleared before 5 Oct 11:13:** Herman did it (answered 9 Oct). Resolved.
3. **Prompt 127** needs ground truth for the Sep 30 and Oct 1 captures.
4. **Prompt 129,** the null-RSSI grace period, is not started.
5. **The simulator's Ghost Patrol bug: fixed in 135** (`a0a081d`). Each scripted event now raises only its own alert. The per-cycle limit on `ghost_patrol` inside `verify_multimodal()` is still 133's job (COR-12, second half).
6. **Kalman lock-up** (`kalman_service.py`; COR-02 in the review): solves more than 8 m away are rejected and still refresh `_last_seen`. Recalibration also triggers it. Planned for 136.
7. **Sep 23 ingest latency** (median 322 ms, p99 2.3 s) is unexplained.
8. **`.env` changes need a backend restart.** `--reload` only watches `.py` files. (`start.ps1` re-reads the camera password by itself.)
9. **`GET /health/tracker`** has no frontend consumer.
10. **Stale docs.** README.md was rewritten in v7. The rest belongs to Prompt 141 (DOC-01, DOC-03, DOC-04 in the review), or to whichever prompt touches the code first:
    - **`docs/vigi-integration-design.md`:**
      - its header still says "nothing here is built";
      - **§8** describes the route as `/api/cameras/{id}/webrtc`, pins a `.6` LAN candidate, and has go2rtc reading RTSP itself. As built: the cctv-shaped route, an auto-detected LAN address, ffmpeg in front, and `start.ps1` restarts.
    - **`SYSTEM_OVERVIEW.md`** has about 36 mismatches with the code (review §7.1). For example, it still describes `/vigi/detection` and calls the patrol tracker "future".
    - **`backend/.env.example`:**
      - `MAN_DOWN_MINUTES` says "in a high-risk zone", but man-down ignores zones;
      - `COLLISION_DISTANCE_M` is described as a man-down movement distance.
    - **Docstrings:**
      - `kalman_service.py:15` still says "~2 s" cadence;
      - `patrol_tracker_service.py:15` refers to "Level 2";
      - `check_collision` in `safety_service.py` says 30 s, but the code suppresses repeats for 10 s.
    - The `TEMP-MEASURE-119` prints are still live (`patrol_tracker_service.py`).
11. **Radius settings:** `PATROL_PROXIMITY_RADIUS_M` is 1.0. The per-floor field is ignored, and a newly created floor would store 0.0.
12. **Unchanged since v3:**
    - the "Mystery Man" beacon (`7E66DA30-…`, "pika");
    - whether 117's hysteresis is live is inconclusive;
    - an untracked Firestore composite index;
    - `eac8b38`'s beacon-delete cleanup ignores simulated beacons.
13. **User-owned:**
    - `backend/encode.py` (gitignored; a plaintext camera password): don't touch it.
    - Firestore `man_down_minutes`: don't touch it.
    - `frontend/package*.json`: don't modify them. Herman updated the lockfile himself in `13491a9`. The root `package-lock.json` is gone (`73b0e3f`).
14. **DHCP:** the laptop's `.5` reservation doesn't hold, and the APs have no reservations (see "Hardware and network"). The camera's `.101` reservation was never verified. Live view adapts by itself; check the camera's Alarm Server target if alarms stop, because it names the laptop's address.
15. **Reload noise:** right after every backend reload there's a 1–2 s burst of 3–15 "RuntimeError: No response returned" tracebacks. These are requests queued during the reload, in Starlette's BaseHTTPMiddleware. It's pre-existing (also seen 5 Oct) and harmless, but noisy.
16. **`docs/go2rtc-sei-issue.md`: not posting** (Herman, 9 Oct). The ffmpeg workaround is enough for SKYE; don't raise it again unless he asks. The draft is kept: it cites `master` `c245815` (bug still there on 9 Oct) and links #2277 ("VIGI no video"). Its `/api/streams` figures come from the MP4 consumer, not WebRTC.
17. **Signal-loss man-downs after a backend restart or an AP outage** (REL-01, COR-06): restarts and AP outages can raise man-downs for everyone who is still present. Planned for 136; until it lands, clear them by hand.
18. **Collisions against stale positions** (COR-04): collision checks don't look at a record's age or floor. In L3, 17 of the 30 collision alerts were the simulated forklift against the real worker's old position. Planned for 136.
19. **L1's evidence:** Herman reported the AP posts answered 200 after the token rotation, but no capture on disk shows them. The next time Ethernet is up, confirm that `/telemetry/omada` answers 200 (a 401 means the controller's token doesn't match `.env`).
20. **Simulator limits, for 138:**
    - the `events` scenario's man-down segment can't raise an alert (COR-13);
    - its missed-checkpoint event isn't guaranteed in every cycle;
    - simulations write heartbeats for the real APs, so offline APs look online (REL-07).
21. **`backend/payload.json`** is untracked since 135, but the file stays in history. No history rewrite: that's Herman's call, and the token in it was rotated on 13 Oct.

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
  | `man_down_latch_inprocess.py` | 6/6 |
  | `sec04_dump_redaction_inprocess.py` | 5/5 |
  | `sec01_ingest_fence_inprocess.py` | 9/9 |
  | `cor05_sim_cleanup_inprocess.py` | 8/8 |
  | `cor12_sim_events_inprocess.py` | 7/7 |
  | `cor01_timestamps_inprocess.py` | 7/7 |
  | `cor08_ap_delete_inprocess.py` | 6/6 |

  - The 135 tests are the six `sec0*`/`cor*` suites. All six fail or crash on `2f00309`, the code before 135.
  - COR-05 and COR-12 fake the simulators' HTTP client and send them to a dead port. The harness tripwire doesn't cover `localhost`, and `localhost:8000` is the live backend.
  - The review's fix plan asks every later prompt to add an in-process test for each finding it closes.

- **Run `run_smoke.py` with the repo's own harness against the export.** The export's copy of the driver reads `<export>/backend/.env`, which `vigi_131_test.py` leaves holding fake values, so the result is 46 × 401.
- **The launcher** sets `VIGI_DISCOVERY_INTERVAL_S=0`, `GO2RTC_CONFIG_PATH=<run_dir>/go2rtc.yaml` and `GO2RTC_API_URL` to a dead port unless the caller sets them. So no harness server multicasts on the LAN or touches the live go2rtc.
- **Opt-in switches:**
  - `HARNESS_FAKE_AUTH=1` (`harness-token:<uid>`);
  - `HARNESS_ENV_PATH` (a test `.env`).

## Environment quirks
- **Shells:** PowerShell is primary; the Bash tool is Git Bash.
- **Python:**
  - **A plain `python` on this laptop is 3.14.7** (also `py`'s default). It can't install the backend's pinned `numpy` 2.1.3 or `scipy` 1.14.1, which have no 3.14 wheels: pip stops at numpy with `Unknown compiler(s)` (tested 16 Oct).
  - **`py` is the Python install manager** (26.4 on 16 Oct). `py -3.12` means `-V:PythonCore\3.12`, so it never selects uv's Pythons, registered or not, and there's no python.org 3.12 here. `py install 3.12` would add one (3.12.10); that's Herman's call.
  - **The backend venv is 3.12.13,** built on uv's own Python, and it has pip. Both ways to recreate it were tested on 16 Oct:
    - `& "$env:APPDATA\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe" -m venv venv`, then `venv\Scripts\python.exe -m pip install -r requirements.txt`;
    - or `uv venv --python 3.12 venv`, then `uv pip install -r requirements.txt --python venv\Scripts\python.exe` (that venv has no pip).
  - On 16 Oct, 3.11.15 and 3.13.15 also installed everything and passed all 13 harness suites (`check_capture.py` needs 3.12+). They were scratch installs and have been removed.
  - `backend\venv\Scripts\python.exe` is a **uv trampoline**, so kill the PID a process reports for itself. The real interpreter is `%APPDATA%\uv\python\cpython-3.12-…`, and the firewall Allow rules are for it. The network profile is Public.
- **Line endings:**
  - `core.autocrlf=true` (system-wide). The working tree is mixed: on 16 Oct, 220 tracked files were CRLF and 40 were LF (HANDOFF.md among them; README.md is CRLF). `git archive` output is CRLF.
  - Keep each file's existing endings, and check with `git ls-files --eol <file>`.
  - **Git Bash `sed -i` strips the CRs** (re-add them with `sed -i 's/$/\r/'` or use the Edit tool).
  - Python's `read_text`/`write_text` also convert; use bytes.
- **Hashing in Git Bash:** `sha256sum` prefixes its output with `\` for paths containing backslashes. Compare with `cmp`, or cut carefully.
- **Bash tool:** a `\\` inside a heredoc can reach Python as `\`. For text containing escapes, use the Edit tool.
- **Claude Code safety checks:**
  - `rm -rf "$VAR/…"` and `Remove-Item "$X\…"` with variable paths are blocked. Use `"${VAR:?}"` or literal absolute paths.
  - A blocked command doesn't run at all.
  - Auto mode also blocks `git rm` of tracked files and deleting folders such as `node_modules` (14 Oct). Herman runs those himself.
- **Logs:**
  - `backend/logs/` captures are UTF-8; one file per backend process start. Nothing prunes `backend/logs`.
  - `tools/go2rtc/go2rtc.log` rotates at 10 MB.
- **Tools:**
  - `openssl` and `pdftotext` are in Git Bash.
  - Chrome 154 and Edge 154 are installed; headless Chrome is good for WebRTC checks (getStats) and for rendering previews to PNG.
  - `gh`, `gcloud` and `ffprobe` aren't installed (`gh` re-checked 16 Oct). The repo is public, so `curl https://api.github.com/repos/herman-1110/SKYE/pulls?state=all` reads PR state without a login.
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
"Continue from HANDOFF.md v7. Before anything else:
1. Run `git status`, `git log` and `git ls-remote --heads origin` fresh. We work on `main`: the last code commit is `13491a9`, followed by the v7 docs commit. Ask me before committing anything.
2. Read the Prompt 134 review with `git show review/134:docs/reviews/2026-10-09-project-review.md`. It stays local: never push `review/134` and never copy unfixed findings into a tracked file.

Then wait for my Prompt 136 (man-down and collision correctness) and check its preconditions against git first. Leave `man_down_minutes` and `backend/encode.py` alone, keep secrets out of all output, and no multi-agent workflows."
