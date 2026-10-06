# SKYE Sentinel-AI — Handoff (v5, after Prompts 130, 131, 131b; updated 2026-10-06 15:20)

Paste this into a new chat to resume. Project: FastAPI + Firebase (Firestore/RTDB/Storage) backend, Next.js/TypeScript frontend. Indoor BLE positioning → safety alerting (man-down, collision, patrol compliance) → real-time patrol tracking and reporting. Now also a VIGI camera integration (alarm events, health, discovery) heading for Ghost Patrol.

**This replaces v4** (30 Sep), which is archived at `Project\skye-log-archive\HANDOFF-v4-20260930.md` (listed in the archive's `MANIFEST.csv`). **Check every claim here against the current code, git history and data before relying on it.** This file is untracked and overwritten each time.

## Where things stand (6 Oct, 15:20)

- **The VIGI camera works end to end on the live system.**
  - Discovery found it.
  - Herman registered it from the editor's "online but not placed" list.
  - It made exactly one OpenAPI login.
  - Its alarms are accepted (40+ since the 15:07 restart).
  - The camera panel shows the events.
- **Prompts 130, 131, 131b and the `/login` Suspense fix are committed and pushed** (`2dbb475`).
- **Next up:**
  - **Prompt 132:** live video. The plan is go2rtc with WebRTC and signalling through the backend.
  - **Prompt 133:** Ghost Patrol.
  - The man-down stillness alert flood (Open #1) is waiting for Herman's decision.
- **Codex was cleared to resume** after the push. At 15:18 something (almost certainly Codex) **staged** `HANDOFF.md`, `frontend/package.json`, `frontend/package-lock.json` and the root `package-lock.json`. Claude didn't touch the index. Earlier prompts said none of those four may be committed. Ask Herman.

## Git

- **Branch:** `claude/repo-review-r1fviz` at **`2dbb475`**, the same as `origin` (pushed 6 Oct).
- **Against `origin/main`** (`13e515c`, fetched 6 Oct): 43 commits ahead and 1 behind. The 1 is PR #1's merge. Local `main` (`3cdd6bb`) is stale.
- **Fetching and pushing:** use `GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=never git fetch|push origin …`. A plain fetch can hang on a credential prompt.
- **Commits since v4:**

  | Commit | What |
  |---|---|
  | `8cc7027`, `7ed3cdc`, `951fd05`, `70f8d0b` (30 Sep) | field capture protocol doc, 10 Sep evidence, `.gitignore` for `backend/encode.py` |
  | `a5cb614` (5 Oct) | 128 follow-up: only an `OSError` marks the capture tee's console dead (was "Open #0"; live since 5 Oct) |
  | `b7aa153` | **130:** VIGI recon (`tools/vigi-listener/`: listener, OpenAPI/RTSP/ONVIF probes) and `docs/vigi-integration-design.md` |
  | `0e65805`, `bd81ad2`, `a6a8e33`, `cc5a241` | **131:** settings and registry; alarm endpoint, redaction, detections and health; harness tests and fixtures; frontend |
  | `69376b0`, `64d172f` | **131b:** camera discovery (backend and harness); frontend |
  | `2dbb475` | `/login` wrapped in Suspense. `next build` failed at `/login` on untouched code before this; now all 16 pages prerender. |

## Working methodology

- **Prompts:** work comes as numbered "Prompt N" specs (CONTEXT → DIAGNOSE → TASK → VALIDATION, with STOP conditions).
  - If DIAGNOSE contradicts the prompt or a STOP fires, stop and report; don't work around it.
  - A precondition that fails gets reported, not assumed. Example: 131's password precondition was unmet at first, and Herman fixed it.
- **Evidence:** use real measurements over assumptions. Cite `file:line`. Never fabricate a measurement or a "yes, it's live".
- **Git:**
  - Commit only when asked, and split commits logically (frontend in its own commit).
  - Run `git diff --cached --stat` right before every commit.
  - **Push only when Herman says so.** For camera work he pushes only after the live check.
  - **Never commit** `HANDOFF.md`, Herman's `frontend/package*.json` (animejs), the root `package-lock.json`, or `backend/encode.py`.
- **Secrets:**
  - Never print, log, write to a fixture, or commit:
    - `VIGI_CAMERA_PASSWORD`;
    - A1 (the camera digest's first hash, which is equivalent to the password);
    - any OpenAPI `stok`;
    - `VIGI_ALARM_PATH_SECRET`.
  - Read `.env` with `dotenv_values`, checking only shape (length, character class), never the value.
  - Before every commit, scan the staged diff for the **real** values. 131 used a small script that loads `.env` and greps `git diff --cached` without printing.
- **Other actors:** Herman, and the **Codex agent in VS Code** (`codex.exe`, `node_repl`). Snapshot hashes of the live files before work and re-check before copying in. Unexplained edits, reloads or staging may come from either.
- **Live system:**
  - Herman's dev backend is `uvicorn main:app --reload` on :8000. It was last started by hand on 6 Oct at 15:07:23 and logs to `backend/logs/skye-20261006-070724.log`.
  - `next dev` is on :3000.
  - Saving any `.py` under `backend/` reloads the backend. Each reload costs one new camera login, because the stok lives in memory.
  - Build and test in a `git archive` export in the scratchpad, then copy into the live tree once by an explicit file list, then verify hashes.
- **The camera's admin account locks after repeated failed logins** (errCode `-10030`). Never loop a login. The backend's lockout guard is described below.
- **Memory on this laptop is tight** (about 3 GB free). Claude Code's memory reaper killed the background listener more than once.
  - Long-running things like a capture listener go in Herman's own terminal.
  - Herman's rule since 131: **no multi-agent reviews or workflows.**
- **Frontend builds:** never run `next build` in the live `frontend/`, because `next dev` shares `.next`.
  - Export to the scratchpad and junction its `node_modules` to the live one (`New-Item -ItemType Junction`).
  - Copy `frontend/.env.local` in for the build only, and delete it afterwards.
  - Run `tsc --noEmit --incremental false` first.

## Status by prompt

| Prompt | Topic | Status |
|---|---|---|
| 104–126, 128 | earlier work (v3/v4) | committed |
| Open #0 | tee console rule | committed `a5cb614`, live |
| 127 | offline calibration replay | **blocked:** needs a named source log plus ground truth. Field captures exist (Sep 30 and Oct 1, below), but Herman's notebook times and positions were never received. |
| 129 | null-RSSI grace period | not started |
| 130 | VIGI recon | `b7aa153` |
| 131 | camera registry, alarm endpoint, health, camera panel | pushed |
| 131b | camera discovery and click-to-place | pushed |
| — | `/login` Suspense fix | `2dbb475`, pushed after Herman confirmed sign-in |
| **132** | **live video** (go2rtc; decisions below) | next |
| **133** | **Ghost Patrol** (evaluator, verdicts, `departed_at`, patrol enabled) | after 132 |

## VIGI camera

### Hardware and network (verify before relying on it)
- **Camera:** InSight S445 v1.0, firmware 3.3.2 Build 260708.
  - MAC **`98:BA:5F:8B:10:03`**, IP **`192.168.0.101`**. Herman was asked to reserve that address in DHCP; this isn't verified.
  - Time zone UTC+08:00. Its clock runs about 0.7 s behind the laptop.
- **Laptop:** **`192.168.0.5`**, on the Ethernet adapter `54-05-DB-C4-A5-78`, reserved in Omada DHCP on 6 Oct. It was `.6` until 6 Oct 13:33, when an AP held `.6`.
- **APs** posted from `.3`, `.4` and `.6` on 6 Oct.
- **The camera's Alarm Server:** `http://192.168.0.5:8000/vigi/alarm/<VIGI_ALARM_PATH_SECRET>`, HTTP, no image. Enhanced Alarm Message Service is ON and human detection is on.
- **Prompt 130's listener path** (`/P8nC…`) is retired and not a secret any more. The first live failure on 6 Oct was the camera still posting to it (404s).

### What the camera sends (130 captures, archived)
- **The push:** JSON only, with **no auth header**, so the path segment is the credential. A new connection per event, reset about 0.5 s after the reply. The Test button only opens a TCP connection and sends no HTTP.
- **Legacy format** (Enhanced off): `event_list: [{dateTime: "YYYYMMDDHHMMSS", event_type: ["MOTION","PEOPLE"]}]`.
- **Enhanced format** (on): `camera: "1"`, `dateTime: "YYYY-MM-DD HH:MM:SS"`, `event_type` is a *string*, and `extra_text` is a *list of objects* holding `obj_num`, `region_id[]` and `obj_rect_info[]`. This differs from TP-Link's FAQ.
- **Event types:** `MOTION` can arrive alone; only `PEOPLE` means a person.
- **Payload MAC:** `98-ba-5f-8b-10-03`.
- **Timing:** an empty scene sends nothing. While someone moves, there's an event every 1–7 s; a person standing still keeps producing them, but thinner.

### Streams and APIs
- **Streams:**
  - `stream1`: H.264 High, 2688×1520, 25 fps;
  - `stream2`: H.264 High, 848×480, 25 fps;
  - `stream6`: JPEG, 1 fps.
- **RTSP:** port 554, Digest MD5, user `admin`. Audio is PCMA. **No codec change is needed.**
- **ONVIF:** port 2020; port 80 also appears in WS-Discovery.
- **OpenAPI:** HTTPS on port 20443 with a self-signed certificate (VIGI IPC Open API Document V1.1).
  - **It has no method that reads the Alarm Server settings or the "processing mode".** So `alarm_config` can only ever be `mismatch` (human detection off) or `unknown`. Herman deferred this to 133.
- **Discovery:** the camera answers one ONVIF WS-Discovery probe with its MAC in a scope: `onvif://www.onvif.org/VigiInfoStream/98-BA-5F-8B-10-03/…`.
  - VIGI's own ODP (UDP 23001) isn't used, because its request format isn't documented (UNCONFIRMED).

### Backend as built (131/131b; see the commit messages)
- **Settings:**
  - `VIGI_ALARM_PATH_SECRET` (24+ characters, set in `.env`) and `VIGI_CAMERA_PASSWORD` (set). Both are hidden from repr.
  - `VIGI_RAW_DUMP_ENABLED` (false).
  - `VIGI_LIVENESS_INTERVAL_S` 5, `VIGI_OPENAPI_INTERVAL_S` 300, `VIGI_OPENAPI_START_DELAY_S` 60.
  - `VIGI_DISCOVERY_INTERVAL_S` 60 (0 = off).
- **Registry:** the existing `buildings/{b}/floors/{f}/cctvs`, plus `source_type`, `device_mac`, `channel`, `ip`, `checkpoint_ap_id` and `timezone`.
  - `camera_key` is `"ipc:98BA5F8B1003:1"`.
  - `utils/mac_utils.normalize_mac` accepts dashes, colons or none; anything else is a 422 with a plain sentence.
  - `(device_mac, channel)` is unique (409). There's a `PATCH` route.
  - Deleting a camera removes its heartbeat. Deleting an AP unlinks its cameras.
  - The time zone is read once, at registration and when the IP changes.
  - The live camera is on the TPLink floor (`fc6e663e…`) with **no checkpoint yet**.
- **`POST /vigi/alarm/{secret}`:**
  - The secret is compared as bytes in constant time. A wrong or unset secret gets the same 404 as an unknown route.
  - Accepts JSON, or multipart with the image dropped.
  - Runs in `run_in_threadpool`, never under `pipeline_lock`. Replies 200 with `Connection: close`. Rate limit 600/min.
  - Only a registered MAC from its registered IP is buffered.
  - **Every logged path under `/vigi/alarm/` reads `/vigi/alarm/***`.** That covers uvicorn's access log, `request_logger` and slowapi (`utils/log_redaction.py`).
- **`GET …/cctvs/{id}/detections`:** last 15 minutes, newest first, in memory only. Returns `process_started_at`. Uses `require_auth_strict`, so a missing header is 401.
- **`POST /cctvs/discover`:** admin only. One discovery round, about 3 s.
- **Heartbeat** `/cctv_heartbeats/{98_BA_5F_8B_10_03}`, written by partial updates through `cctv_repository.update_heartbeat`:

  | Field | Meaning |
  |---|---|
  | `last_seen` | last TCP connect to port 554 that succeeded |
  | `last_event_at` | last accepted alarm |
  | `probe` | `ok` / `auth_error` / `no_credentials` / `unreachable` / `error` |
  | `probe_ok_at` | when the probe was last ok; absent means never verified (the hook then shows "unknown") |
  | `alarm_config` | `mismatch` or `unknown` |
  | `discovered_at`, `discovered_via`, `ip` | from discovery |
  | `ip_mismatch` | the camera was found at another IP |

- **Health:**
  - TCP liveness every 5 s, to registered cameras and to unregistered ones discovered in the last 10 minutes.
  - OpenAPI checks (status, clock, human-detection switch) run **for registered cameras only**: first at 60 s, then every 300 s, plus once right after a create or IP change.
  - **Lockout guard:** `backend/logs/vigi-openapi-lockout-<camera_key>.json` holds only the camera_key and `.env`'s mtime. It's written before every password-bearing doAuth and deleted on success. With a marker present, no login happens until `.env`'s mtime changes, then exactly one retry.
- **Discovery:**
  - An ONVIF WS-Discovery probe per private LAN interface, multicast with TTL 1. VIGI devices only.
  - The MAC comes from the scope, else from `arp -a`.
  - Unregistered entries unseen for 10 minutes are pruned. It never removes a registered camera's node or a node without `discovered_via` (the simulator's).
- **Frontend:**
  - **Camera editor:** name, MAC, IP and checkpoint, for add and edit. An "online but not placed" list with **Scan now**; clicking an entry places the camera with its details filled in. A camera found at another IP shows **Use the new IP**.
  - **`CameraPanel`** (click a camera marker): status, probe and alarm setup in plain words, and recent events. It polls every 3 s and refetches as soon as `last_event_at` changes. There's a placeholder slot for live video.
  - **`useCCTVHeartbeats`:** a camera is "unknown" when it has no heartbeat or has never been verified.

### Herman's decisions (6 Oct) still to apply
| # | Decision | Applies in |
|---|---|---|
| 2 | Patrol stays off until Ghost Patrol (both floors: `patrol_enabled=false`, empty route) | 133 |
| 3, 4 | The verdict is stored on the patrol log; the window pads are ±10 s | 133 |
| 6, 7 | Live view over WebRTC with backend signalling; audio off | 132 |
| A2 | `alarm_config` (mismatch/unknown only) feeds the verdicts somehow | 133 |
| A3 | Herman draws the camera's detection area | 133 |

The design notes are in `docs/vigi-integration-design.md`, sections 7 (Ghost Patrol) and 8 (live view). go2rtc expands `${VAR}` in its config, so the camera password can stay in `.env`, and it never URL-encodes values. The new password uses only letters, digits and `- _ . ~`, which need no encoding.

## Field captures and archive
- **Archive:** `C:\Users\Intern\Downloads\Omada\Project\skye-log-archive\`. Out of git, and `MANIFEST.csv` lists every file with its SHA-256. It holds:
  - every `skye*.log` recovered from the Recycle Bin (7 to 22 Sep, including the 10 Sep calibration run 2);
  - the field captures from **30 Sep** (`skye-20260930-052440.log`, AP data 13:24–13:48, dump on) and **1 Oct** (`skye-20261001-012430.log`, AP data 09:24–09:56, dump on);
  - `vigi-2026-10-05\`: the alarm captures of 5–6 Oct (redacted), plus Prompt 130's `secret_path.txt`;
  - the old handoffs (7 and 8 Sep) and v4.
- **The dump-on logs contain the Omada ingest token**, which is the known placeholder value. Keep them out of git.
- **The 10 Sep stationary evidence** is in `docs/evidence/`. The Level 2 (`abf7e4a2…`, inactive) and TPLink (`fc6e663e…`, active) floor frames differ.
- **`OMADA_RAW_DUMP_ENABLED=false`** in `backend/.env`. The dump goes on only for captures, and each change needs a restart.

## Null-RSSI (unchanged since v4)
- No null-RSSI buffer or grace period exists. Nulls arrive as `"rssi": {}`, and the APs report about once a second.
- On the Sep 7 replay, a 2 s grace would lift 3-AP decisions from 73% to 95.5%. That's input for Prompt 129.
- Prompt 111's 10 s hold of the last good position is the only cushion.

## Open threads — ask Herman, don't assume
1. **Man-down stillness alert flood** (found 5 Oct; **no decision yet**).
   - **The cause:** once a beacon has been still past `man_down_minutes` (Firestore 60, which Herman owns, so don't change it), `check_man_down` raises a new alert every 30 s for as long as it stays still (`safety_service.py:172-174`). Signal-loss alerts latch once per episode; stillness alerts don't.
   - **The data:** on 5 Oct there were 325 alerts (166 `guard-001` and 159 `worker-001` stillness, from two beacons sitting together on a desk).
   - **The options:** latch once per stillness episode (recommended), or re-alert every 10–15 minutes.
2. **`/alerts` was cleared before 5 Oct 11:13.** Nothing older than that remains. Herman was asked whether he did it and hasn't answered.
3. **Prompt 127** still needs ground truth for the Sep 30 and Oct 1 captures: the beacon's positions and when it was placed and moved.
4. **Prompt 129,** the null-RSSI grace period, is not started.
5. **The simulator's Ghost Patrol bug:** `simulation_events._write_patrol_log` calls `verify_multimodal` for every record, so its missed-checkpoint segment also raises a spurious `ghost_patrol`. Noted only, not fixed. This matters for 133.
6. **Kalman lock-up** (`kalman_service.py`): solves more than 8 m away are rejected and still refresh `_last_seen`. A "reset after 3 rejections" fix was proposed and never decided.
7. **Sep 23 ingest latency** (median 322 ms, p99 2.3 s against 162/897 ms on Sep 24, same code) is unexplained. Ingest is serialised under `pipeline_lock`.
8. **`.env` changes need a restart.** `--reload` only watches `.py` files, and a variable set in the shell environment silently wins over `.env`.
9. **`GET /health/tracker`** has no frontend consumer.
10. **Stale docs:**
    - `SYSTEM_OVERVIEW.md` still describes `/vigi/detection` (lines 395, 428, 701), says fewer than 3 APs goes straight to proximity, and calls the patrol tracker "future".
    - `README.md:114` documents a setting that doesn't exist (`MAN_DOWN_MOVEMENT_THRESHOLD`).
    - The comment for `COLLISION_DISTANCE_M` in `.env.example` is wrong.
    - `kalman_service.py:13-16` still says "~2 s cadence".
    - `patrol_tracker_service.py:14-17` refers to "Level 2".
    - The `TEMP-MEASURE-119` prints are still live.
11. **Radius settings:** `PATROL_PROXIMITY_RADIUS_M` is 1.0. The per-floor field is ignored, and a newly created floor would store 0.0 (a latent bug).
12. **Unchanged since v3:**
    - the "Mystery Man" beacon (`7E66DA30-…`, `person_id` "pika") is unidentified;
    - whether 117's hysteresis is live is inconclusive;
    - an untracked Firestore composite index was never reconciled;
    - `eac8b38`'s beacon-delete RTDB cleanup ignores simulated beacons.
13. **User-owned files:**
    - **`backend/encode.py`** (gitignored; a plaintext camera password): don't touch it.
    - **Firestore `man_down_minutes`:** don't touch it.
    - **The animejs install** in `frontend/package*.json`.
    - **The root `package-lock.json`.**
    - All of these are staged as of 6 Oct 15:18; see "Where things stand".
14. **Camera DHCP reservation for `.101`:** Herman was asked to make it. Not verified.

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
  | `vigi_131_test.py --port 8003` | **34/34** (fake cameras on `127.0.0.2`–`.4`, two server runs) |
  | `vigi_131_inprocess.py` | **5/5** (`pipeline_lock`, buffer cutoff, parser) |
  | `vigi_131b_inprocess.py` | **9/9** (discovery against a loopback responder) |

  The VIGI suites write a test-only `.env` into the export and never read the real one.
- **Opt-in switches:**
  - `HARNESS_FAKE_AUTH=1`: `harness-token:<uid>` is accepted as an ID token.
  - `HARNESS_ENV_PATH`: the launcher loads that file instead of the real `.env`.
- The launcher sets `VIGI_DISCOVERY_INTERVAL_S=0` by default, so no test server multicasts on the LAN.
- **Fixtures:** `tools/harness/fixtures/vigi/` holds 7 real payloads. A legacy `MOTION`-only push was never captured.

## Environment quirks
- **Shells:** PowerShell is primary; the Bash tool is Git Bash.
- **Python:**
  - Use `backend\venv\Scripts\python.exe`, which is a **uv trampoline**: kill the PID a process reports for itself, not `Popen.pid`.
  - The real interpreter is `%APPDATA%\uv\python\cpython-3.12-…`, a junction to `cpython-3.12.13-…`. The inbound firewall Allow rules (TCP/UDP, any port, Public and Private) are for that executable. The network profile is Public.
- **Logs:**
  - `backend/logs/` captures are UTF-8 without a BOM. PowerShell-piped logs are UTF-16LE.
  - Nothing prunes `backend/logs`.
- **Tools:** `openssl` and `pdftotext` are at `/mingw64/bin` (Git Bash). `gh`, `gcloud` and `ffprobe` aren't installed.
- **Firebase:**
  - The CLI is authenticated to `skye-3fa05`. Deploys need an explicit go-ahead.
  - The old leaked service-account key `6f81d665` was deleted by Herman on 5 Oct. The backend uses `fdcac568`.
- **Identities:**
  - real beacons: `guard-001`, `worker-001`;
  - simulated: `sim-*`, `test-*`; the simulator's fake camera heartbeat is `A8:57:4E:3C:11:01`.
- **Hardware:**
  - APs `40:AE:30:9D:34:5A`, `40:AE:30:9D:34:5C` (EAP660 HD) and `A8:29:48:C3:88:A0` (EAP770);
  - the active floor is "TPLink" (`fc6e663e…`) in building `53c3872f…`.

## Suggested first message in the new chat
"Continue from HANDOFF.md v5. Before anything else:
1. Run `git status` and `git log` fresh. Codex has resumed, and as of 6 Oct 15:18 `HANDOFF.md` and the package files were staged by someone. Ask me before committing anything.
2. Decide with me on the man-down stillness flood (Open #1).

Then start Prompt 132 (live video) from `docs/vigi-integration-design.md` §8 and decisions 6–7. Leave `man_down_minutes` and `backend/encode.py` alone, and keep secrets out of all output."
