# VIGI camera integration: design (Prompt 130, Part D)

*Draft, 5 Oct 2026. Not approved, and nothing here is built. Building starts at Prompt 131.*

**Goal:** make Ghost Patrol work with a real camera, and let a click on a camera marker open live video. One VIGI InSight S445 is connected directly now; a VIGI NVR may be added later without reworking the core.

**Evidence:** everything below was measured on 5 Oct against the real camera (192.168.0.101, firmware 3.3.2 Build 260708). The sources are:
- `tools/vigi-listener/` (the alarm capture, plus OpenAPI, RTSP and ONVIF probes);
- the TP-Link *VIGI IPC Open API Document V1.1*.

Anything marked UNCONFIRMED was not observed.

## 0. What the camera actually does

| Topic | Measured |
|---|---|
| Alarm push | HTTP POST to the configured host, port and path, `Content-Type: application/json; charset=utf-8`. **Only the `Host`, `Content-Type`, `Content-Length` and `Cache-Control` headers are sent, so there's nowhere to put a token.** It uses a new connection per event and resets it about 0.5 s after our reply. |
| Formats | **Legacy** (Enhanced Alarm Message Service off) and **enhanced** (on). Both are in Appendix A. The enhanced format **differs from TP-Link's FAQ**: `event_type` is one string per event, `camera` is the string `"1"`, `extra_text` is a *list of objects* holding `region_id[]`, `obj_rect_info[]` and `obj_num`, and there's no `direction` field. |
| Event types | `PEOPLE` and `MOTION`. Legacy sends them combined (`["MOTION","PEOPLE"]`); enhanced sends them as separate events, and **`MOTION` can arrive on its own**. |
| Cadence | While a person moves in view, an event every 1–7 s (median 3 s). A person standing still keeps producing `PEOPLE` events, but less often: 15 in the first minute, then 5 (gaps up to 15 s). |
| Empty scene | **0 events in 3 minutes.** Silence means "nobody there" *or* "camera dead"; the payloads alone can't tell which. |
| Two people | Legacy: indistinguishable from one. Enhanced: `obj_num: 2` with two boxes. |
| Test button | A TCP connect followed by a reset after 0.1 s. **No HTTP request is sent.** |
| MAC | The payload sends `98-ba-5f-8b-10-03`; `getDeviceInfo` returns `98-BA-5F-8B-10-03`; `getDeviceStatus` returns lowercase. The registry and frontend use `98:BA:5F:8B:10:03`. |
| Time | The `dateTime` field has no time zone. The camera zone is `UTC+08:00` (`getTimeZone`). The camera clock runs **0.64–0.85 s behind** this PC. A push arrives **0.3–1.3 s after the event**, and `dateTime` is truncated to the second. |
| Streams | `stream1` is **H.264** High@5.0, 2688×1520, 25 fps. `stream2` is **H.264** High@3.0, 848×480, 25 fps (about 170 kbit/s on a quiet scene). `stream6` is JPEG, 640×360, 1 fps. All run on RTSP port 554 with Digest MD5 as `admin`. Audio is PCMA 8 kHz. ONVIF answers on port 2020. **No codec change is needed.** |
| Lockout | OpenAPI locks the admin account after repeated failed logins (errCode `-10030`). |

## 1. Identity and registry: extend `cctvs`, don't add a new registry

**Camera identity** is `(source_type, device_mac, channel)`, written as the key `camera_key = "<source_type>:<MAC, no separators>:<channel>"`.
- The camera now: `ipc:98BA5F8B1003:1`.
- Later, a camera behind an NVR: `nvr:<NVR MAC>:<N>`.

The existing collection `buildings/{b}/floors/{f}/cctvs/{id}` (`models/cctv.py:5-14`, `repositories/cctv_repository.py:9-39`) keeps its uuid ids, `name`, `x_pct`/`y_pct` (map placement exactly as for APs) and `mac`. It gains these fields:

| Field | Type | Notes |
|---|---|---|
| `source_type` | `"ipc"` \| `"nvr"` | default `"ipc"` |
| `device_mac` | `"98:BA:5F:8B:10:03"` | the MAC of the *reporting* device, stored colon-uppercase. For `ipc` it equals `mac` (kept for the existing UI). |
| `channel` | int | 1 for a direct camera |
| `ip` | string | for RTSP and health probes. Push requests must come from this IP. |
| `checkpoint_ap_id` | AP doc id or null | **the checkpoint this camera covers**: an AP on the same floor, the same kind of id `patrol_route` holds |
| `timezone` | e.g. `"UTC+08:00"` | used to read `dateTime`; filled from `getTimeZone` |

**Gaps to close at the same time:**
- `create_cctv` doesn't check MAC uniqueness (`routes/floor_routes.py:261-279`, unlike APs at `:181-193`). Make `(device_mac, channel)` globally unique.
- A single CCTV delete leaves its RTDB heartbeat behind (`:294-302`; only deleting a floor clears it, `services/floor_service.py:111-116`).
- There's no route to edit a camera's name, MAC, link or channel.
- `delete_ap` (`services/floor_service.py:131-147`) must set `checkpoint_ap_id` to null on cameras linked to the deleted AP, the same way it strips `patrol_route`.

**UI (`APCCTVEditor.tsx:188-204, 520-547`):** the placement dialog gains a "Covers checkpoint" drop-down listing the APs on that floor, plus an IP field. Source type and channel stay hidden until there's an NVR. The MAC input accepts dashes or colons and stores colons.

**Rules:** none to change. `cctvs` stays write-only through the backend (`firestore.rules:62-65`), and so does `cctv_heartbeats` (`database.rules.json`).

## 2. Source adapters

Each adapter turns one HTTP body into a list of normalized records:

```
CameraDetection: camera_key, source_type, device_mac, channel,
                 event_type ("PEOPLE" | "MOTION" | other, raw),
                 is_human (event_type == "PEOPLE"),
                 obj_num (int | None; enhanced only), regions (list | None),
                 boxes (list of {x,y,w,h} | None; scale looks like 0-10000, UNCONFIRMED),
                 camera_time_raw (str), camera_time_utc (datetime | None),
                 received_at (server UTC), source_ip, payload_format ("legacy" | "enhanced")
```

- **IPC adapter (now):**
  - **Legacy:** `event_list[i].dateTime` (`YYYYMMDDHHMMSS`) with `event_type` as a list. Each type becomes one record, with `channel = 1`.
  - **Enhanced:** `camera` (a string, read as int) is the channel; `dateTime` is `YYYY-MM-DD HH:MM:SS`; `event_type` is a string; each `extra_text[]` object supplies `obj_num`, `region_id[]` and `obj_rect_info[]`.
  - Both formats can put more than one event in a single POST.
  - Unknown fields are ignored, never fatal.
- **NVR adapter (later):** the payload format is **UNCONFIRMED** until it's captured with `tools/vigi-listener`. It must produce the same records, taking the channel from whatever field the NVR uses.

## 3. Ingest endpoint

- **Route:** `POST /vigi/alarm/{path_secret}`, with no `/api` prefix, like `/telemetry/omada` (`routes/omada_telemetry.py:11`).
  - The secret comes from `.env` (`VIGI_ALARM_PATH_SECRET`, added to `config/settings.py` in the existing frozen-dataclass style, with a comment in `.env.example`).
  - It's compared with `hmac.compare_digest`, and a mismatch returns **404**.
  - **Header authentication isn't possible**, because the camera sends no auth header. So neither `verify_omada_token` (`middleware/auth_middleware.py:10-13`) nor a body token will work.
- **Who's accepted:** detections are kept only if the payload `mac` (normalized) is registered **and** the request comes from that camera's registered `ip`. A request from an unregistered device still writes the heartbeat and is logged as "online but not placed", which is how `omada_ingest_service.py:344-346` handles APs.
- **Bodies:**
  - JSON: the real format.
  - `multipart/form-data` with the `ReportEventBoundary` boundary: parse the JSON part and **drop image parts**. Images stay off on the camera; the 1 MB cap (`main.py:63`) is fine without them.
- **Execution:** `run_in_threadpool`, like Omada ingest, but **never under `positioning_service.pipeline_lock`**: camera events must not queue behind position solves. Reply `200 {"ok": true}` with `Connection: close`. Rate limit: 600 requests a minute.
- **The old `/vigi/detection` (`routes/vigi_routes.py:12-20`):**
  - It would answer every real push with 422 (it requires an `Authorization` header).
  - It reuses the Omada token.
  - It writes the heartbeat under an un-normalized key (`services/vigi_service.py:8`), so a dashed MAC never matches.
  - **Remove it in 131.** Nothing calls it today; the simulations write heartbeats directly.

## 4. Detection storage

- **In memory:** a ring buffer per `camera_key` (the last 15 minutes, `deque` with `maxlen`) holding `(received_at, is_human, obj_num)`. It has its own lock and is used only for matching.
- **Persisted:** **no raw detections** (about 20 a minute per camera while people move). What is persisted:
  - the per-visit verdict (§7) on the patrol log;
  - the heartbeat (§6);
  - optionally, behind `VIGI_RAW_DUMP_ENABLED` (off by default, like `OMADA_RAW_DUMP_ENABLED`), the raw bodies in the capture log, for debugging.
- **Restarts:** the buffer is lost on every process restart, and the dev server's `--reload` restarts on every `.py` save. Any window that overlaps a restart **must** get the verdict `unknown` (§6). Record `process_started_at` for that.

## 5. Time

- **Match on server receive time** (`received_at`). The camera side is small and measured: its clock is 0.6–0.9 s behind, and a push lands 0.3–1.3 s after the event.
- **Keep** `camera_time_raw`, `camera_time_utc` (using the registry `timezone`) and `received_at − camera_time_utc` for auditing. Alert if that gap drifts past 10 s (a sign of clock trouble).
- **The BLE side is what drives the matching window, not the camera.**
  - Visit times are position ticks about 2 s apart, Kalman-smoothed, with up to 10 s of exact-hold (Prompt 111) and a 1.0 m entry radius.
  - `PatrolLogRecord` has no `departed_at`, so departure is `actual_arrival + dwell_time_seconds`, truncated to the second (`patrol_tracker_service.py:383-386`). **Add `departed_at` in 131.**

## 6. Health and the three-way verdict

- **Liveness without credentials:** a TCP connect to the camera's port 554 (RTSP), or an unauthenticated RTSP `OPTIONS`, every 5 s from a background task like `_man_down_stale_loop` (`main.py:67-81`).
  - Each success writes the heartbeat (below).
  - Alarm events also refresh `last_event_at`, but they **can't prove the camera is alive**: an empty scene sends nothing.
- **OpenAPI, slow cadence (every 5 min):** `getDeviceStatus` (`link_status`, `uptime`) and `getSystemTime` (clock drift), using `tools/vigi-listener/openapi_probe.py` as the reference.
  - **Any `-10021` (bad password) or `-10030` (locked) stops OpenAPI probing for that camera until a human resets it.** It never retries automatically.
  - The `stok` token lasts 30 minutes; log in again only when it expires.
- **Heartbeat contract (feeds `useCCTVHeartbeats.ts:6-37`):** `/cctv_heartbeats/{98_BA_5F_8B_10_03}` = `{last_seen: unix s, mac: "98:BA:5F:8B:10:03", device_name, last_event_at, probe: "ok" | "auth_error" | …}`.
  - Normalize the MAC **before** building the key; the hook matches on `mac.toUpperCase()`.
  - The hook counts a camera as online when its heartbeat is under 10 s old (`:6`). A 5 s probe meets that; the alternative is a camera-specific threshold (decision 5).
  - `"unknown"` (`:8`) is declared but never produced. Use it for cameras whose probe has never succeeded.
- **The verdict for one visit window:**
  - **`seen`:** at least one **`PEOPLE`** event (never `MOTION`) from a registered camera linked to that checkpoint, inside the window.
  - **`not_seen`:** zero `PEOPLE` events **and** a successful reachability probe both before and after the window, with no gap longer than 15 s, **and** the ingest process up for the whole window.
  - **`unknown`:** everything else (no linked camera, camera unhealthy, a restart inside the window, an evaluator error).
  - **Only `not_seen` can raise Ghost Patrol. A dead, unlinked or unknown camera never does.**

## 7. Ghost Patrol evaluation

- **Feed:**
  - One guarded line at the end of `_close_visit` (`patrol_tracker_service.py:362-413`) appends the closed `PatrolLogRecord` to a **bounded** `deque(maxlen=500)` inside `try/except: pass`. The tracker stays camera-unaware, never calls `verify_multimodal`, and still can't raise; tracker exceptions are already swallowed at `safety_service.py:477-499`.
  - The `_close_visit` call sites all already run under `pipeline_lock`, so the append adds no locking.
- **Evaluator:** an asyncio loop (every 5 s, started in `lifespan` next to the stale loop, `main.py:95-96`), running outside `pipeline_lock`. It has the same single-worker caveat as the tracker (`patrol_tracker_service.py:45-50`).
- **Which visits:** only real ones, where `actual_arrival is not None and not not_in_window`. `_close_visit` also emits skips and backfills, which are never evaluated.
- **Window:** `[actual_arrival − 10 s, departure + 10 s]`, evaluated once `now ≥ departure + 10 s + 5 s` (5 s covers push latency).
- **Linked cameras:** checkpoint AP MAC (`checkpoint_id`, `:391`) → AP id (from the AP cache) → cameras with that `checkpoint_ap_id`. If **any** linked camera says `seen`, the result is `seen`. If none is `seen` and **all** say `not_seen`, the result is `not_seen`. Otherwise it's `unknown`.
- **Writes:**
  - The verdict goes onto the patrol-log doc: a new `camera_verdict` field (tri-state), `camera_keys`, `human_events_in_window`; `vigi_detected` becomes `camera_verdict == "seen"`.
  - On `not_seen`, the evaluator (not the tracker) calls `safety_service.verify_multimodal(log, ble_detected=True, vigi_detected=False)` (`safety_service.py:456-474`). That keeps the existing alert schema: `alert_type="ghost_patrol"`, `zone=checkpoint_name`, `cause=None` (`models/alert.py:5-22`).
- **Rate bound:** **at most one `ghost_patrol` per `(guard_id, checkpoint, cycle_id)`.** `verify_multimodal` has no suppression of its own, unlike man-down's once-per-stillness-episode latch and 30 s gate (`safety_service.py:183-191`, since 9 Oct). Without this cap, a parked tag would repeat the 325-alert day.
- **Prerequisite:** patrol is **off on both floors** (`patrol_enabled=false`, empty route; read 5 Oct). Ghost Patrol needs patrol enabled and a route on the TPLink floor.

## 8. Live view

- **Relay: go2rtc** on the laptop. It's a single binary (installed in 131, not 130) that turns RTSP into WebRTC **without transcoding**: both streams are H.264, and PCMA is a WebRTC audio codec. It needs no ffmpeg for this.
  - Its docs say streams are pulled on demand unless `preload` is set, so it should cost nothing while idle. UNCONFIRMED; measure memory in 131.
  - Default to `stream2` (848×480). Offer `stream1` (2688×1520) only through an "HD" button. Nothing is recorded.
- **Password:** only in `.env`.
  - `go2rtc.yaml` refers to `${VIGI_CAMERA_PASSWORD}` (go2rtc expands environment variables in its config; per Frigate discussion #15313 it doesn't URL-encode them, so a password with `@ : / #` would need encoding).
  - The browser, Firestore and RTDB never see it.
- **Recommended mode: WebRTC with signaling through the backend.**
  - go2rtc's API listens on `127.0.0.1:1984`, and its RTSP re-server on `127.0.0.1:8554` or is disabled.
  - The browser posts its SDP offer to `/api/cameras/{cctv_id}/webrtc`. The Next.js rewrite (`next.config.js:3-7`) passes that to FastAPI with `require_admin` and the existing Bearer token (`frontend/services/floorService.ts:22-30`).
  - FastAPI looks up the camera, maps its `camera_key` to a go2rtc stream name, and forwards the offer to `http://127.0.0.1:1984/api/webrtc?src=<name>`. It returns the answer.
  - Media then flows between the browser and go2rtc on **port 8555 (TCP/UDP)**. That port has to be reachable from the viewer's browser unless the browser runs on the laptop. It carries only DTLS-SRTP sessions negotiated through the authenticated signaling; go2rtc's API and stream list are never exposed.
  - Pin the LAN candidate (`webrtc: candidates: [192.168.0.6:8555]`); the DHCP reservation keeps that address stable.
- **Alternative: MSE over a WebSocket proxied by FastAPI.** Only port 8000 is exposed, but Next dev rewrites don't carry WebSocket upgrades, so the browser connects to :8000 directly, and about 170 kbit/s per viewer passes through Python.
- **Browsers:** H.264 High profile over WebRTC works in Chrome, Edge and Safari; Firefox is UNCONFIRMED.
- **UI:** clicking a camera marker (`FloorMap.tsx:327-336`) opens a panel with the live video, the camera status and its recent detections. It's admin-only, to match the endpoint.
- **NVR-ready:** the stream source comes from `camera_key`: `ipc` → `rtsp://<ip>:554/stream{1|2}`, `nvr` → the NVR's per-channel path (UNCONFIRMED). go2rtc stream names equal `camera_key` plus `_sub`/`_main`.

## 9. Adding an NVR later

What changes:
- **One new adapter** (§2), from a captured NVR payload.
- **Registry entries** with `source_type: "nvr"`, `device_mac` = the NVR's MAC, `channel` = N, `ip` = the NVR's IP.
- **The RTSP path template for `nvr`** in the relay config.
- **Liveness:** heartbeats are per reporting device. An NVR channel inherits the NVR's liveness until per-channel status (`{MAC}_ch{N}` keys, a small hook change) is needed.
- **Optionally,** the NVR OpenAPI `event_server` registration instead of manual Alarm Server setup.

The buffer, verdict, evaluator, endpoint, UI and relay are all keyed by `camera_key` and don't change.

## 10. Decisions for Herman

1. **Enhanced Alarm Message Service: keep it ON** (recommended). It's the only format that gives `obj_num` and separate `MOTION`/`PEOPLE` events.
2. **Enable patrol and a route on TPLink.** Ghost Patrol can't fire without it.
3. **Verdict storage:** a tri-state `camera_verdict` on the patrol log, with `vigi_detected` derived (recommended), or a separate `camera_verdicts` collection.
4. **Window pads:** 10 s before and after, evaluated 5 s later. Tune them after the first real patrols.
5. **Liveness:** a TCP probe every 5 s with the 10 s hook threshold kept (recommended), or a 30 s probe with a camera-specific 90 s threshold in the hook.
6. **Live view:** WebRTC with backend signaling, opening port 8555 to the LAN (recommended), or MSE through FastAPI with only :8000 open.
7. **Audio** in the live view: on or off. PCMA works either way.
8. **Remove `/vigi/detection`** and replace it with §3 (recommended).
9. **Raw alarm dump flag** (`VIGI_RAW_DUMP_ENABLED`, off by default): yes or no.
10. **One camera per checkpoint, or several** (the design allows several: any `seen` wins).
11. **Camera time zone:** take it from `getTimeZone` at registration (recommended), or a single setting.

## Appendix A: captured payloads (5 Oct, path and token-free)

Legacy (Enhanced off), 821 requests between 14:32 and 15:34:
```json
{"ip": "192.168.0.101", "mac": "98-ba-5f-8b-10-03", "protocol": "HTTP",
 "device_name": "InSight S445 1.0_1003",
 "event_list": [{"dateTime": "20261005150501", "event_type": ["MOTION", "PEOPLE"]}]}
```
Enhanced (on), 11 requests between 16:23 and 16:26. This one has two people:
```json
{"ip": "192.168.0.101", "mac": "98-ba-5f-8b-10-03", "protocol": "HTTP",
 "device_name": "InSight S445 1.0_1003",
 "event_list": [{"camera": "1", "dateTime": "2026-10-05 16:25:31", "event_type": "PEOPLE",
   "extra_text": [{"region_id": [1], "obj_num": 2,
     "obj_rect_info": [{"x": 2109, "y": 4722, "height": 5278, "width": 1797},
                       {"x": 4062, "y": 4305, "height": 4167, "width": 1875}]}]}]}
```
