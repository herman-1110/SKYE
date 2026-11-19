# SKYE Sentinel-AI — System Overview

> Autonomous Industrial Safety & Patrol Intelligence System

*Updated 18 November 2026 against the code. What isn't built yet is listed in §4 and §9b.*

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [System Architecture](#2-system-architecture)
3. [Prototype — What Has Been Built](#3-prototype--what-has-been-built)
4. [Future Improvements](#4-future-improvements)
5. [Backend Detail](#5-backend-detail)
6. [Frontend Detail](#6-frontend-detail)
7. [Data Flow](#7-data-flow-ble--backend--frontend)
8. [Firebase Usage](#8-firebase-usage)
9. [Key Design Decisions](#9-key-design-decisions)
   - [9b. Known Issues & Pending Work](#9b-known-issues--pending-work)
10. [Environment Variables](#10-environment-variables)

---

## 1. System Overview

SKYE Sentinel-AI is an indoor safety and patrol monitoring system for industrial sites such as warehouses, factories and logistics floors. It tracks guards, workers and forklifts with BLE beacons heard by Wi-Fi access points, detects safety incidents in real time, takes alarm events and live video from IP cameras, and generates audit reports with an LLM, all in one operations dashboard.

**Core problem it solves:**
Traditional safety patrols rely on manual logbooks and radio check-ins. Supervisors have no real-time awareness of where guards, workers or forklifts are inside a building. Incidents such as worker collapses, near-miss collisions, missed checkpoints and proxy patrol fraud go undetected until the next human check.

**How SKYE addresses this:**

| Problem | SKYE solution |
|---|---|
| No real-time location | BLE beacon RSSI from Omada APs → log-distance path loss → weighted multilateration (3 or more APs, then a Kalman filter) or a nearest-AP estimate (1–2 APs, unsmoothed) → live floor map, on several active floors at once (§3.1, §3.7) |
| Delayed incident response | Collision prediction on every computed position; man-down after a configurable stillness time (default 5 min) or a loss of signal (a 60 s sweep); critical pop-ups on every dashboard until an admin acknowledges them or someone resolves them (§3.2) |
| Unverifiable patrol compliance | A real-time patrol tracker logs each checkpoint visit with its dwell time and raises a patrol violation when a window closes with checkpoints missed or too short (§3.3). Camera cross-verification of visits is designed but not built yet (§9b) |
| Ghost patrol / proxy fraud | A ghost-patrol alert when a guard's beacon is at a checkpoint but no camera confirms a person. The cameras already push people-detection events (§3.12); so far only the events simulation raises the alert (§9b) |
| Manual post-shift reporting | LLM-generated audit reports for patrol shifts and safety events (Gemini through the google-genai SDK, with the model set in configuration), with similar past incidents from alert feedback as context for patrol reports (§3.8); plus a per-guard, per-cycle patrol report built without an LLM (§3.3) |
| No central operations view | A Next.js dashboard: floor map with devices and camera direction, personnel panel, alert feed, device status, and a camera panel with live video for admins (§3.9) |

---

## 2. System Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                                FIELD LAYER                                 │
│ BLE beacon tags (guards, workers, forklifts)                               │
│ VIGI IP cameras (people and motion alarms, RTSP video)                     │
└─────────┬─────────────────────────────────────────────────┬───────────────┬┘
          │ BLE advertisements                   alarm push │          RTSP │
          ▼                                                 │               │
┌──────────────────────────────────────┐                    │               │
│ TP-Link Omada Wi-Fi APs              │                    │               │
│ a BLE scan report per AP, about 1 s  │                    │               │
└─────────┬────────────────────────────┘                    │               │
          │ POST /telemetry/omada (token in the body)       │               │
          ▼                       POST /vigi/alarm/<secret> ▼               │
┌────────────────────────────────────────────────────────────────────┐      │
│              BACKEND — Python / FastAPI (one process)              │      │
│                                                                    │      │
│ OmadaIngestService: AP-centric → per-beacon readings, iBeacon      │      │
│   uuid:major:minor identity, 2 s buffer, AP heartbeats;            │      │
│   3+ APs → exact solve, 1–2 APs → proximity estimate               │      │
│ PositioningService: LDPL → weighted least squares (floor-bounded)  │      │
│   → Kalman [x, y, vx, vy] → predict ahead → pixels and zone        │      │
│ SafetyService: man-down (per position + 60 s signal-loss sweep) ·  │      │
│   collision · PatrolTrackerService (patrol logs, violations) ·     │      │
│   ghost patrol (events simulation only)                            │      │
│ Camera services: alarm ingest → 15-min detection buffer ·          │      │
│   RTSP-port liveness · OpenAPI health · ONVIF discovery ·          │      │
│   live-view signalling and the go2rtc config                       │      │
│ LLMService (Gemini; other providers are stubs) · RAG               │      │
│ Simulators: patrol · events · shift (POST /telemetry)              │      │
└─────────┬─────────────────────────┬─────────────────────────┬──────┘      │
          │ firebase-admin          │ firebase-admin          │ SDP         │
          ▼                         ▼                         ▼             ▼
┌──────────────────────┐  ┌──────────────────────────┐  ┌────────────────────┐
│ Firebase RTDB        │  │ Firestore                │  │ go2rtc + ffmpeg    │
│ /positions           │  │ users · beacons          │  │ own process,       │
│ /alerts              │  │ buildings/{b}/floors/{f} │  │ start.ps1          │
│ /ap_heartbeats       │  │   access_points · cctvs  │  │ RTSP → MPEG-TS →   │
│ /cctv_heartbeats     │  │   · zones                │  │ WebRTC, port 8555  │
│ /beacon_scans        │  │ patrol_logs · feedback   │  └─────────┬──────────┘
└─────────┬────────────┘  │ audit_reports · settings │            │
          │               │ + Storage: plan images   │            │
          │               └─────────┬────────────────┘            │
          │ onValue                 │ onSnapshot                  │ video
          ▼                         ▼                             ▼
┌────────────────────────────────────────────────────────────────────────────┐
│                      FRONTEND — Next.js 15 App Router                      │
│                                                                            │
│ Dashboard: stats · floor map (zones, APs, cameras, cones, route, people)   │
│   · device status · personnel · active alerts                              │
│ Alerts: feed · critical pop-ups · feedback · acknowledge · remove          │
│ Reports (AI audit) · Patrol Reports (per-cycle checkpoints, print to PDF)  │
│ Floor Plans: buildings · floors · calibration · zones · patrol ·           │
│   Manage Devices (placement guides, camera direction)                      │
│ Beacons · Users · Safety Settings · camera panel with live video           │
│ Reads Firebase directly; calls the backend through /api/* with the         │
│ user's ID token                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

The browser never writes RTDB or Firestore: it streams live data from Firebase and changes records through the backend's API (§5.2, §8). The one exception is the floor-plan image, which an admin uploads to Storage directly (§3.5). The backend keeps its ingest, safety and patrol state in memory, so it runs as a single process with one uvicorn worker (§5.1).

**Stack:**

| Layer | Technology |
|---|---|
| Backend | Python 3 (the README asks for 3.12), FastAPI, uvicorn, pydantic 2, firebase-admin, FilterPy (Kalman), NumPy and SciPy, google-genai, slowapi (rate limits), httpx, Pillow |
| Frontend | Next.js 15 App Router, React 18, TypeScript 5, Tailwind CSS v3 (CSS-variable themes, dark and light), Zustand 4, Firebase JS SDK 10, pdfjs-dist (PDF floor plans). `recharts`, `framer-motion` and `animejs` are listed dependencies but unused (§9b) |
| Database | Firebase Realtime Database (live state) + Firestore (persistent records) |
| Storage | Firebase Storage (floor-plan images) |
| Auth | Firebase Auth: email and password with email verification, and Google sign-in. The backend verifies the ID token and requires an approved account; roles are owner, admin and user (§3.10) |
| AI | Gemini through the google-genai SDK: audit reports (the provider is selectable, but only Gemini is implemented, §5.5), AI zone detection, and `gemini-embedding-001` embeddings for retrieving past incidents. The model comes from the required `LLM_MODEL_NAME` |
| Hardware | TP-Link Omada Wi-Fi APs (BLE scan reports), TP-Link VIGI IP cameras (alarm events, RTSP liveness, OpenAPI health checks, ONVIF discovery, live video) |
| Live video | go2rtc with ffmpeg in front, a separate process started by `tools/go2rtc/start.ps1`; WebRTC to the browser (§3.12) |

---

## 3. Prototype — What Has Been Built

### 3.1 Indoor Positioning Engine
`PositioningService.compute_position()` (`backend/services/positioning_service.py`) turns one beacon's readings from three or more APs into a smoothed position. With one or two APs the ingest uses `ProximityService` instead (last bullet; §3.7 decides which).

- **Coordinates**: metres from the floor-plan image's top-left corner, x to the right and y down. An AP's `x_m`/`y_m` is its image fraction × the image's size in pixels ÷ `scale_pixels_per_meter`, and the server always derives it (`floor_service`).
- **Calibration**: the Floor Plans calibration tool takes two points on the image and the real distance between them, and saves the resulting px/m.
- **LDPL** (`utils/rssi_utils.py`): `distance = 10 ^ ((TxPower − RSSI) / (10 × n))`, where `n` is `PATH_LOSS_EXPONENT` (configurable, default 2.5).
  - TxPower is the beacon's registered `tx_power` (§3.11, default −59 dBm).
  - `TX_POWER_DEFAULT` (configurable, default −59) is the solve's fallback only for a TxPower of 0.
  - `settings.py` describes these values as uncalibrated defaults.
- **Multilateration** (`least_squares_position()`, `utils/multilateration.py`): weighted nonlinear least squares via `scipy.optimize.least_squares`. Weights are inverse-square distance, and `method="trf"` keeps the estimate inside the floor's bounds.
- **Per-floor context** (`_FloorContext`): the scale, zones and bounds of one floor, so two active floors never share geometry.
  - Bounds are `[0, image_width_px ÷ scale] × [0, image_height_px ÷ scale]` when the image size and scale are known.
  - The real path passes the floor its APs resolved to (§3.7).
  - Contexts have no TTL. `invalidate_scale_cache()` clears them, and every Kalman filter, after a scale change, a floor activation or deactivation, and any zone create, update or delete.
- **Kalman filter** (`KalmanService`, FilterPy): one per `reporter_mac`, which is the `person_id` on the real path and the simulated tag's MAC on `/telemetry`.
  - State `[x, y, vx, vy]`, constant velocity.
  - A measurement more than 8 m from the current estimate is rejected (predict only). The third rejection in a row resets the filter and starts it again from that measurement.
- **Collision prediction**: `predict_ahead(COLLISION_ALERT_SECONDS)` (configurable, default 3 s) projects the state at constant velocity into `predicted_x/y`. The collision check (§3.2) measures the distance between a worker's and a forklift's projected points.
- **Output**: `pixel_x/y` = metres × `scale_pixels_per_meter`. `zone` is the name of the first zone whose rectangle contains the point, else `"unknown"`. The record is written to RTDB `/positions/{key}` (§7).
- **<3-AP fallback** (`ProximityService`, `backend/services/proximity_service.py`): the beacon is anchored at the AP that hears it strongest. `x/y` are that AP's own coordinates, `radius_m` is the LDPL distance from its RSSI, `is_approximate` is true, and `zone` is `"unknown"`.
  - There's no Kalman smoothing, prediction or pixel position, so approximate positions take no part in the collision check or the patrol tracker. Man-down times them separately (§3.2).
  - Nothing is written when even the strongest AP hears the beacon below `PROXIMITY_RSSI_FLOOR` (configurable, default −90 dBm). Nothing is written either while the person's last exact solve is younger than `POSITION_EXACT_HOLD_SECONDS` (the hold, §3.7).

### 3.2 Safety Alert Detection (6 Types)

`SafetyService` (`backend/services/safety_service.py`) raises each alert as an `AlertRecord` (`backend/models/alert.py`) and writes it to RTDB `/alerts/{alert_id}` through `AlertRepository`. The checks run from three places:

- **After every computed position** (an exact solve on either ingest path, or the Omada path's <3-AP proximity fallback): `run_all_checks()` runs `check_man_down()`, then the patrol tracker (§3.3), then `check_collision()` over every record in `/positions`, all inside `positioning_service.pipeline_lock`.
- **Every 60 s:** `_man_down_stale_loop()`, a task started by the FastAPI lifespan in `main.py`, runs `check_man_down_stale()`, so a beacon that stops reporting is still caught.
- **From the events simulation:** its scripted ghost and missed-checkpoint events call `verify_multimodal()` and `check_patrol_compliance()` directly (§3.4).

| Alert type (`cause`) | Trigger | On the dashboard |
|---|---|---|
| `man_down` (`stillness`) | A worker's or guard's exact (≥3-AP) position stays within `MAN_DOWN_MOVEMENT_EPSILON_M` of its anchor for `man_down_minutes`. Moving away takes `MAN_DOWN_MOVE_CONFIRM_FIXES` exact fixes in a row past it, so a single stray fix doesn't restart the clock. Also raised when exact fixes confirm a `possible_man_down`. | Red pop-up |
| `man_down` (`signal_loss`) | The sweep finds a worker's or guard's `/positions` record older than `MAN_DOWN_STALE_SECONDS` but not older than `MAN_DOWN_STALE_MAX_AGE_S`, unless none of the APs that last heard them is alive | Red pop-up |
| `possible_man_down` (`stillness`, `approximate=true`) | Stillness seen by only one or two APs: an approximate run at one strongest AP lasts `man_down_minutes` | Amber pop-up |
| `positioning_offline` (no person or zone) | The sweep finds that no AP placed on an active floor has reported within `AP_SILENT_AFTER_S`, though at least one has reported before | Amber pop-up |
| `collision` | A worker's and a forklift's Kalman-predicted positions, `COLLISION_ALERT_SECONDS` ahead, are closer than `collision_distance_m` | Red pop-up, `<worker> ↔ <forklift>` |
| `patrol_violation` (`missed_checkpoint`, `short_dwell`, `no_patrol`) | At a patrol window's close, from live guard positions (§3.3): a checkpoint whose best visit was missed or shorter than `MIN_DWELL_SECONDS`, or a guard who was on the floor but didn't patrol. | Alert lists only |
| `ghost_patrol` | A guard's tag reached a checkpoint but the camera didn't confirm a person (`verify_multimodal()`). Its only caller is the events simulation's scripted ghost event. | Alert lists only |

**Thresholds.** Two values can be changed while the backend runs: `man_down_minutes` (whole minutes, 1–60) and `collision_distance_m` (0.5–10 m). They live in the Firestore doc `settings/safety`, which startup creates from `MAN_DOWN_MINUTES` (default 5) and `COLLISION_DISTANCE_M` (default 2.0) when it's missing. The rest are configurable in `.env` and read at startup; the main ones are below, and §10 lists them all (code defaults from `backend/config/settings.py`):

| Setting | Default | Meaning |
|---|---|---|
| `MAN_DOWN_MOVEMENT_EPSILON_M` | 2.0 m | movement below this counts as still |
| `MAN_DOWN_MOVE_CONFIRM_FIXES` | 3 | exact fixes in a row, each ε or more from the anchor, that make a move |
| `MAN_DOWN_UPGRADE_CONFIRM_S` | 30 s | exact stillness that turns an amber alert red |
| `MAN_DOWN_STALE_SECONDS` / `MAN_DOWN_STALE_MAX_AGE_S` | 120 s / 3600 s | the record age window for a signal-loss alert |
| `AP_SILENT_AFTER_S` / `AP_ALIVE_GRACE_S` | 10 s / 30 s | an AP counts as reporting / as alive again after a gap |
| `COLLISION_ALERT_SECONDS` | 3 s | how far ahead the Kalman prediction looks |

**Man-down.** Below, ε is `MAN_DOWN_MOVEMENT_EPSILON_M` and N is `MAN_DOWN_MOVE_CONFIRM_FIXES` (3).

```
fresh position ─► check_man_down()                          (forklifts skipped)
  exact (≥3 APs) ─► one anchor (x, y, since) per person
      N fixes in a row ≥ ε ─► new anchor at the last one; the clock restarts
      fewer in a row, then one within ε ─► nothing changes; the count starts again
      still for man_down_minutes ─► red man_down (stillness), once per episode
  approximate (1–2 APs) ─► a run at the strongest AP; it doesn't touch the count
      lasts man_down_minutes ─► amber possible_man_down, once per run
      then exact fixes within ε for MAN_DOWN_UPGRADE_CONFIRM_S ─► red man_down
      (a single fix ≥ ε doesn't end that; N in a row end the run as movement)

every 60 s ─► check_man_down_stale()
  record stale, and an AP that last heard them is alive ─► red man_down (signal_loss)
  no placed AP reporting ─► one amber positioning_offline; signal-loss alerts held
```

**Lifecycle.** Acknowledging is optional: feedback resolves an alert whether or not anyone acknowledged it.

| Step | Route (auth) | Effect |
|---|---|---|
| Raised | none: the checks above | `/alerts/{alert_id}` written with `resolved=false` |
| Acknowledged | `POST /alerts/{id}/acknowledge` (`require_admin`: admin or owner) | The pop-up closes for everyone, and the alert stays active. |
| Resolved | `POST /alerts/{id}/feedback` (`require_auth`) | `feedback` is `confirmed`, `fixed` or `false_alarm`, with an optional `reason`. Sets `resolved=true` and writes a Firestore `feedback` doc, which `RagService` draws on as context for patrol audit reports (§3.8). |
| Deleted | `DELETE /alerts/{id}` (`require_admin`) | Removes the alert for good |

`database.rules.json` allows no client writes to `/alerts`, so clients change alerts only through these routes. The thresholds use `GET /settings/safety` (`require_auth`) and `PUT /settings/safety` (`require_admin`).

**Dashboard**

- `useAlerts()`, mounted once in `dashboard/layout.tsx`, subscribes to `/alerts` and keeps them in `dashboardStore`.
- **Pop-ups.** `CriticalAlertBanner` shows `useCriticalQueue()`: every unresolved, unacknowledged `man_down`, `collision`, `possible_man_down` and `positioning_offline`, worked out from the live alerts. An admin's or the owner's ✕ acknowledges the alert for everyone. Anyone else's ✕ hides the pop-up in that tab until a reload.

### 3.3 Patrol System

Patrol compliance is tracked live from guard positions by `PatrolTrackerService` (`backend/services/patrol_tracker_service.py`), on real AP data and simulated guards alike. The simulators also write scripted patrol logs of their own (§3.4).

**Configuration (per floor, on the floor's Firestore document)**
- `patrol_enabled`, `patrol_route` (ordered AP ids: the checkpoints) and `patrol_interval_minutes` (the cycle window, default 10).
- Saved with `PATCH /buildings/{id}/floors/{id}/patrol` (`require_admin`) from `PatrolConfigPanel` (Floor Plans → the floor's ⋯ menu → Manage Patrol, admins only).
- Radius and dwell are global settings, not per floor: `PATROL_PROXIMITY_RADIUS_M` (default 1.0 m), `PATROL_PROXIMITY_EXIT_MARGIN_M` (default 0.5 m) and `MIN_DWELL_SECONDS` (default 30), all configurable.

**Real-time tracker**

```
exact guard position (POST /telemetry/omada or POST /telemetry)
  └─ SafetyService.run_all_checks()             (under positioning_service.pipeline_lock)
       └─ PatrolTrackerService.check_patrol_progress()
            guards only · exact positions only · floor has patrol_enabled and a route
            ├─ enters a checkpoint: within PATROL_PROXIMITY_RADIUS_M of a route AP
            ├─ leaves it (beyond radius + PATROL_PROXIMITY_EXIT_MARGIN_M)
            │     → PatrolLogRecord → Firestore patrol_logs
            ├─ arrives past route entries not yet logged this cycle
            │     → one skip record each (actual_arrival = null)
            └─ cycle window has run out → close the cycle:
                  not_in_window records · ≤ 1 patrol_violation per checkpoint
                  · ≤ 1 patrol_violation (no_patrol) · new cycle_id
```

- **Visit record:** written when the guard leaves. `checkpoint_id` is the AP's MAC; `expected_arrival` is when the guard left the previous checkpoint this cycle, or the cycle start (derived: there is no schedule). `compliant` is the negation of `SafetyService.is_patrol_violation()`: no arrival, or a dwell under the minimum, is a violation; a `not_in_window` record never is.
- **Cycle window:** a cycle starts at the guard's first exact position on the floor (rolling, not a wall-clock grid) and runs for `patrol_interval_minutes`. Closing ends any open visit, writes a `not_in_window` record for every checkpoint never reached, and decides the alerts (RTDB `/alerts`):
  - per checkpoint, at most one `patrol_violation`, judged on its best visit: `cause` is `missed_checkpoint` (no arrival) or `short_dwell`, and `zone` is the checkpoint's name (`check_patrol_window_compliance()`);
  - at most one `patrol_violation` with `cause` `no_patrol` (`check_patrol_window_no_patrol()`): the guard was seen in the window but reached no checkpoint, or reached exactly one on a route of two or more and stayed there for at least `PATROL_NO_PATROL_DWELL_RATIO` of the window (configurable, default 0.5). A guard not seen in the window raises nothing;
  - then the next cycle starts, with a new `cycle_id`.
- **Limits:** state is in memory, per process. A restart drops open cycles, a cycle closes only when that guard's next exact position arrives, and a single worker process is assumed.
- `ghost_patrol` comes only from the `events` simulator (§3.4, §9b).

**Viewing patrols**
- **Patrol Reports page** (`/dashboard/patrol-reports`, any approved user): a per-guard, per-cycle checkpoint report built in the browser, with no LLM. It is not the AI Reports page's "Patrol Reports" tab (§3.8).
- **AI patrol audit reports** (§3.8) are offered per `shift_id`, so they cover simulator-written shifts only; tracker cycles (`shift_id=""`) aren't listed.

### 3.4 Simulation System

Three scripted scenarios drive the real positioning and safety pipeline without hardware. Started from the API, each runs as an asyncio task inside the backend, one at a time; each can also be run as a script against a running backend (§7).

**Control (admins).** `POST /simulation/start?mode=patrol|events|shift` (default `events`) and `POST /simulation/stop` use `require_admin`.

**How a simulator feeds the pipeline**
- **Floor:** `FloorRepository.get_any_active()`, the first active floor Firestore returns, in any building. It needs at least 3 APs placed. With patrol enabled and at least 3 route APs that resolve, it uses the route, in order, and only those APs; otherwise every AP on the floor, sorted by coordinates.
- **Telemetry:** each tick it synthesises an RSSI per AP by inverse LDPL from `TX_POWER_DEFAULT` and `PATH_LOSS_EXPONENT`, plus Gaussian noise of `RSSI_NOISE_STD` (configurable; defaults −59 dBm, 2.5 and 3.0 dB), and posts one beacon-centric payload per person to `POST /telemetry`. That route calls `PositioningService.compute_position()` and `SafetyService.run_all_checks()` directly: the same multilateration, Kalman, man-down, collision and patrol-tracker code as real data, but not `OmadaIngestService` (no AP-centric inversion, buffer or <3-AP fallback).

**Sim/real isolation.** Simulated people have `sim-` person IDs and fixed fake beacon MACs (`AA:BB:CC:DD:EE:01` to `…:06`), sent as `reporter_mac`. Their `/positions` keys are those MACs with underscores; real positions are keyed by the bare `person_id`, so the two key shapes can't collide (§8, §9).

**Clean-up**
- At start, a simulator deletes its own `/positions` keys.
- However it ends, its `finally` removes its people from `/positions`.

**Modes**

| Mode | Module | People | Patrol logs it writes | Scripted alerts |
|---|---|---|---|---|
| `patrol` | `simulation_patrol.py` | Guard Alpha (`EE:01`), Guard Beta (`EE:04`) | One per checkpoint arrival: `compliant=True`, `vigi_detected=True`, a random dwell of `MIN_DWELL_SECONDS` to 60 s, the guard's own `shift_id` | none |
| `events` (default) | `simulation_events.py` | Guard Alpha, Guard Beta, Worker 1 (`EE:02`), Forklift 1 (`EE:03`) | Only the two scripted events' logs, under one `shift_id` per run | `ghost_patrol`; `patrol_violation` (`missed_checkpoint`); a collision set-up |
| `shift` | `simulation_shift.py` | outgoing Guard Alpha and Beta; incoming Guard Gamma (`EE:05`) and Delta (`EE:06`) | As in `patrol` | none |

- **`events`:** a 37-tick scripted cycle that repeats: `normal_patrol` (3) → `man_down` (10) → `normal_patrol` (3) → `collision_warning` (5) → `normal_patrol` (3) → `ghost_patrol` (5) → `normal_patrol` (3) → `missed_checkpoint` (5).
  - `man_down`: the worker goes to a far corner and stays there. Stillness is timed on the server clock from when the person's anchor was set, and the segment is shorter than any threshold the Safety Settings page allows, so this segment raises no alert.
  - `collision_warning`: the forklift and the worker converge on the floor's centre; any `collision` comes from the real Kalman-predicted check (§3.2).
  - `ghost_patrol`: Guard Alpha freezes. At segment tick 2 a log is written with a BLE arrival and `vigi_detected=False`, and only `verify_multimodal()` runs: one `ghost_patrol`.
  - `missed_checkpoint`: Guard Alpha skips the second AP in the list; a log with no arrival is written and only `check_patrol_compliance()` runs: one `patrol_violation` (`missed_checkpoint`). The skip only happens if Alpha gets that far along the route within the 5-tick segment, so not every cycle produces it.
- **`shift`:** outgoing Alpha and Beta each patrol one full loop, then freeze; incoming Gamma and Delta wait. Once both outgoing guards have finished, the shift change triggers and the incoming guards patrol.

### 3.5 Multi-Floor Building Management

Buildings, floors and everything placed on a floor are nested Firestore documents (§5.3), with no limit on how many of each.

```
buildings/{building_id}          BuildingRecord
 └─ floors/{floor_id}            FloorRecord
     ├─ access_points/{ap_id}     AccessPoint
     ├─ cctvs/{cctv_id}           CCTV (§3.12)
     └─ zones/{zone_id}           ZoneRecord: a rectangle in metres
```

- **Reads and writes:** records change only through the backend routes: reads are `require_auth`, every mutation is `require_admin` (admin or owner). The exception is the plan image, which the browser uploads to and deletes from Firebase Storage itself; the repository's Storage rules allow that only for an approved admin or owner.
- **Floor plan upload:** PNG, JPG or WEBP up to 10 MB, or a PDF whose pages are rasterised to PNG in the browser (`utils/pdfRasterise.ts`), each page becoming its own floor (§8). A new floor is inactive and uncalibrated. No route swaps a floor's image: a new plan is a new, uncalibrated floor.
- **Calibration** (`CalibrationTool`, `FloorService.update_scale()`): two points on the plan and the real distance between them give px/m. `PATCH …/scale` stores the scale and, when sent, the two points and the distance as `calibration`. When the scale changes, every zone's bounds are multiplied by old ÷ new px/m, so zones stay where they were drawn, and every AP's `x_m` / `y_m` is re-derived from its image fractions (§3.1).
- **AP placement** (`FloorService.create_ap()` / `move_ap()`):
  - A MAC can be placed once per floor.
  - Metres are always derived on the server by `derive_ap_metres()`. Metres sent by a client are ignored.
  - The same AP may also sit on other floors (a backup map), but an active floor can't take a MAC that another active floor already holds.
- **Several active floors:** any number of floors, in any buildings, can be active at once. `PATCH …/activate` activates that floor only, and is refused (409) while another active floor holds one of its APs. `PATCH …/deactivate` turns a floor off. A successful activation or deactivation drops positioning's per-floor cache and Kalman filters and clears the ingest's AP cache.

How a reading finds its floor:

```
AP report ─► every placement of its MAC, in any building ─► only those on an active floor
                                                             ├─ none: online, not placed (heartbeat only, §3.6)
                                                             └─ one:  floor, building, x_m, y_m (cached 30 s)
a beacon's fresh readings ─► their APs' floors ─► one floor (the strongest reading's when they differ)
                                                  └─► that floor's positioning context: scale, zones, bounds
```

- **Zones** (drawing and editing are in §3.13): axis-aligned rectangles in metres with a name, a colour, `is_high_risk` and a separate `risk_level` (`high`, `moderate` or `low`). An exact position is tagged with the first zone whose rectangle holds it (§3.1).
- **AI zone detection** (`POST …/zones/ai-detect`, calibrated floors only): the backend asks Gemini for named bounding boxes, each with a risk level. It converts them to metres with the floor's scale and returns them as suggestions: nothing is saved until an admin confirms them (§5.5).
- **Deletes** (`FloorService`, §5.2):
  - **AP** (`delete_ap()`), in order: (1) it leaves the floor's `patrol_route`; (2) cameras covering it are unlinked; (3) the AP document is deleted; (4) clean-ups: it leaves a running patrol or events simulation, and its heartbeat is deleted only if no other placement of the MAC remains.

### 3.6 Device Status Monitoring

Device status comes from heartbeat nodes in RTDB, keyed by MAC with underscores (`AA_BB_CC_DD_EE_01`) and written only by the backend (the repository's RTDB rules deny client writes).

| Node | Written by | Fields |
|---|---|---|
| `/ap_heartbeats/{mac}` | `OmadaIngestService._write_ap_heartbeat()`, for every AP report that passes the ingest's source and token checks (§3.7), placed or not | `mac`, `name`, `last_seen`, `up_since`, and `ip` only when the report's `reporter.ipv4` is a dotted IPv4 |
| `/ap_heartbeats/{mac}` | the simulators, every 1 s tick, for the APs they move between; `POST /telemetry`, for each reading's AP | `mac`, `last_seen` |
| `/cctv_heartbeats/{mac}` | the backend's camera liveness probe: a TCP connect to each registered camera's IP on the RTSP port. Alarm, discovery and OpenAPI fields share the node (§3.12) | `mac`, `last_seen`, … |
| `/cctv_heartbeats/{mac}` | the simulators, for one simulated camera | `mac`, `last_seen`, `device_name` |

`up_since` is when the AP's current unbroken run of reports began.

- **One status rule** (`apStatus()` in `useAPHeartbeats`, `cctvStatus()` in `useCCTVHeartbeats`): **online** while `last_seen` is under 10 s old, recomputed every second; **offline** when it's older or missing; **unknown** (grey) only until the first RTDB snapshot arrives, and for a camera with no MAC. A camera's status is reachability alone; its login and alarm health show in the camera panel (§3.12).
- **Icons:** `ApIcon` and `CctvIcon` / `CctvMarker` are green online, red offline and grey unknown, on the dashboard map, the Manage Devices map and its device list (§3.13).
- **`DeviceStatusPanel`** (under the dashboard map): every AP and camera placed on the floor the dashboard is showing, each with an Online, Offline or Unknown badge.
- **APs online but not placed** (`APCCTVEditor`, calibrated floors only): every online heartbeat whose MAC isn't placed on *this* floor, with the reported name, IP and MAC. Place starts a placement with the MAC filled in and the name set to the IP, or else the reported name (§3.13). The camera list is in §3.12.
- **Backend use:** the signal-loss sweep (§3.2) reads `/ap_heartbeats`. An AP is *reporting* while `last_seen` is at most `AP_SILENT_AFTER_S` old (default 10 s) and *alive* once its current run is `AP_ALIVE_GRACE_S` old (default 30 s). The sweep holds a person's signal-loss alert while none of the APs that last heard them is alive, and raises one `positioning_offline` when no AP placed on an active floor is reporting.
- Beacons' online/offline state on the Beacons page comes from `/beacon_scans` instead (§3.11).

### 3.7 Real Omada RSSI Ingestion
- `POST /telemetry/omada` (`backend/routes/omada_telemetry.py`) receives the BLE scan reports of the Omada IoT Transport Stream: one report per AP, about once a second each and unsynchronised, listing every beacon that AP heard. `OmadaIngestService` (`backend/services/omada_ingest_service.py`) reads `reporter.mac`, `reporter.name`, `reporter.ipv4`, `reported[].ibeacon.{uuid, major, minor}`, `reported[].rssi.avg` and `meta.access_token`; the report's beacon MAC and Tx-power fields aren't used.
- **Access controls**, as route dependencies, in this order:
  1. `verify_omada_source`: `OMADA_INGEST_ALLOWED_IPS` (a comma-separated list of IPv4 addresses).
  2. `verify_omada_body_token`: `meta.access_token` must match `OMADA_ACCESS_TOKEN` (compared with `hmac.compare_digest`). The token travels in the body because real APs send no `Authorization` header.
  - Rate limit: 600/minute (slowapi).
- **Threading**: the route runs `OmadaIngestService.ingest()` in a worker thread, and `ingest()` holds `positioning_service.pipeline_lock` for the whole report. `/telemetry` and the signal-loss sweep's decisions take the same lock, so AP reports and simulation ticks are processed one at a time.
- **AP heartbeat first**: every reporting AP, placed or not, gets `/ap_heartbeats/{AA_BB_CC_DD_EE_FF}` before the placement and beacon checks.
  - Because the heartbeat comes before the placement check, an AP that isn't placed yet still appears in the device editor's "online but not placed" list (§3.6).
- **AP → floor**: an AP resolves to its placement on an *active* floor, and that floor's whole AP set is then cached for 30 s.
  - An AP with no placement on an active floor answers `{"status": "online_unregistered"}`, and its report goes no further.
  - The API refuses to put one AP on two active floors (§3.5).
- **iBeacon identity keying**: phones rotate their BLE MAC for privacy, so beacons are keyed on `uuid:major:minor` from the report's iBeacon block (`make_ibeacon_key()`). Entries without one are skipped.
  - The identity comes from the Firestore `beacons` registry (§3.11) through a 30 s cache.
- **Beacon scans**: every heard iBeacon with an RSSI, registered or not, is written to `/beacon_scans/{uuid_major_minor}` before the registration check. Unregistered beacons stop there.
- **AP-centric → beacon-centric inversion**: a registered beacon's reading is buffered per AP.
  - After each report the buffer drops readings older than 2 s (`BUFFER_WINDOW_S`) and makes at most one decision per beacon every `POSITION_EMIT_MIN_INTERVAL_S` (configurable, default 1.8 s), so the APs' staggered reports give one solve, not one each.
  - The beacon's floor is the floor of its fresh readings; if they span floors, the strongest reading's floor.
  - **3 or more distinct APs**: an `OmadaTelemetryPayload` with `reporter_mac = person_id` and the registry's label and TxPower → `PositioningService.compute_position()` for that floor (§3.1) → `SafetyService.run_all_checks()`.
  - **1 or 2 APs**: While the person's last exact solve is younger than `POSITION_EXACT_HOLD_SECONDS` (configurable, default 10 s), nothing is written: the exact position stands. Otherwise `ProximityService.compute_position()` (§3.1) → `run_all_checks()`.
- **Stable RTDB key**: exact and approximate records are both keyed by `person_id` (`/positions/<person_id>`), so the marker, the Kalman filter and the man-down state survive MAC rotation (§9).

### 3.8 AI Audit Reports (2 Report Types)

Both types are written by the configured LLM provider (§5.5) through `LLMService` (`backend/services/llm_service.py`) and saved to Firestore `audit_reports` as `AuditReportRecord`, with `report_type` `"patrol"` or `"safety_event"`. All four routes are under `/reports` and use `require_admin`.

| | Patrol report | Safety event report |
|---|---|---|
| Covers | one guard's shift (`shift_id`) | one person on one UTC date |
| Picker | `GET /reports/shifts` | `GET /reports/safety-groups` |
| Generate | `POST /reports/generate` `{log_id, guard_id}` (`log_id` is the `shift_id`) | `POST /reports/generate-safety` `{person_id, date_str}` |
| Inputs | that shift's `patrol_logs` for the guard (checkpoint, compliant, dwell); every RTDB alert whose `person_id` is the guard, from any date; RAG context (below) | the person's RTDB alerts whose timestamp starts with that date (type and time of each) |
| Asks for | safety rating 1–10, key risk findings, corrective actions | incident summary, risk assessment, behavioural patterns, corrective actions, safety rating 1–10 |

- **Reportable shifts:** `PatrolLogRepository.get_reportable_shifts()` groups `patrol_logs` by (`shift_id`, `guard_id`), skipping logs with no `shift_id` and groups with no arrival; the newest 50 are returned. The real-time tracker writes `shift_id=""` (§3.3), so only simulator shifts can be reported on.
- **Safety groups:** distinct (`person_id`, date) pairs in RTDB `/alerts`, with alert counts, newest date first.
- **Prompts:** each states today's UTC date as the audit date and lists the inputs. `_FORMAT_INSTRUCTIONS` limits the reply to `##` headings, `**bold**`, `- ` bullets and `1. ` numbered lines.
- **Report context (RAG):** `RagService` (`backend/services/rag_service.py`), patrol reports only.
  - Corpus: Firestore `feedback`, one `FeedbackRecord` per piece of alert feedback, written by `POST /alerts/{id}/feedback`.
  - Retrieval: an optional pre-filter on `alert_type` (the patrol report passes none, so every feedback document is a candidate). The query and each candidate's text are embedded with `gemini-embedding-001`, and ranked by cosine similarity. Of the 3 most similar, those at or above `RAG_SIMILARITY_FLOOR` (configurable, default 0.5) go into the prompt's Historical Context as "Similar past incidents", and their IDs into `rag_examples_used`.
- **Dashboard** (`/dashboard/reports`, sidebar "Reports"): two tabs, Patrol Reports and Safety Events, each with a picker and Generate. The lists come straight from Firestore `audit_reports` (live `onSnapshot`, newest first) and are split by `report_type`. The detail panel renders `report_text` with the page's `SimpleMarkdown` and has Copy. Any approved user can open the page and read reports; the pickers and Generate need an admin. Clients can't write `audit_reports`: reports only come from the generation routes.
- The deterministic, per-cycle Patrol Reports page is separate (§3.3).

### 3.9 Live Dashboard

Every `/dashboard/*` page shares one shell (`app/dashboard/layout.tsx`): the `Navbar`, the `Sidebar`, the critical pop-ups and the toasts, plus three RTDB subscriptions that last as long as the shell (`usePositions` on `/positions` and `useAlerts` on `/alerts`, both into `dashboardStore`, and the Sidebar's `useBeaconScans` on `/beacon_scans`). The `/dashboard` page itself:

```
┌──────────────────────────────────────────────────────────────────┐
│ Navbar: logo · page title · theme · Safety Settings* · sign out  │
├─────────────┬────────────────────────────────────────────────────┤
│ Sidebar     │ StatsRow: personnel, alerts, collision, man down   │
│  nav+badges ├──────────────────────────────┬─────────────────────┤
│  Personnel  │ FloorMapArea                 │ Active Alerts       │
│   Guards    │  Building / Floor selectors  │  AlertList          │
│   Workers   │  FloorMap + overlays         │  (unresolved only)  │
│   Forklifts │  DeviceStatusPanel           │                     │
└─────────────┴──────────────────────────────┴─────────────────────┘
 CriticalAlertBanner: fixed top-centre on every dashboard page
 ToastContainer: bottom-right                       * admins only
```

- **Building and floor** (`FloorMapArea`): several floors can be active at once (§3.5), and the map shows one active floor of the selected building. Only positions whose `floor_id` is the shown floor are drawn.
- **Floor map** (`FloorMap`): the floor-plan image, with overlays placed in fractions of the image:
  - zones as coloured rectangles, shown or hidden by a ZONES button;
  - AP icons and camera markers coloured by heartbeat;
  - a translucent cone for each camera with a saved facing; a click on a camera opens its `CameraPanel` (§3.12);
  - the patrol route as a faint line through its APs while the floor's patrol is enabled (§3.3);
  - worker markers (`WorkerMarker`): a dot and halo coloured by person type, guard green, worker blue, forklift amber, plus a dashed circle of `radius_m` for an approximate one- or two-AP fix.
- **Stale markers**: nothing deletes a departed beacon's `/positions` record, so a marker more than 12 s older than the freshest one is hidden.
- **Critical pop-ups** (`CriticalAlertBanner`, on every dashboard page):
  - The queue is worked out from the live `/alerts` data (`useCriticalQueue`): `man_down`, `collision`, `possible_man_down` and `positioning_offline` alerts that are unresolved and not acknowledged, oldest first.
  - An admin's or the owner's ✕ calls `POST /alerts/{id}/acknowledge` (`require_admin`), which closes the pop-up on every open dashboard. Acknowledged isn't resolved: the alert stays active until someone gives feedback.
- **Alerts page** (`/dashboard/alerts`): search, Active and Resolved tabs with counts, and type filters. Selecting an alert opens `FeedbackForm`: `POST /alerts/{id}/feedback` (`require_auth`) marks the alert resolved and stores a `feedback` document.
- **Simulation**: the dashboard has no simulation controls (§3.4).
- **Safety Settings** (`/dashboard/safety-settings`, the navbar's gear; admins only): the man-down stillness timer (whole minutes, 1–60) and the collision distance (0.5–10 m), read with `GET /settings/safety` (`require_auth`) and saved with `PUT /settings/safety` (`require_admin`). The values are first seeded from the configurable `MAN_DOWN_MINUTES` and `COLLISION_DISTANCE_M` (code defaults 5 and 2.0).

### 3.10 User Management

**Roles** (`UserRecord.role`):

| Role | Who | Can |
|---|---|---|
| `owner` | The first account ever registered, by either sign-up route, approved at once (only one) | Everything an admin can, plus switch other accounts between `admin` and `user` |
| `admin` | Promoted by the owner | Approve and remove accounts, and use every admin-only route and control |
| `user` | Every later account | Use the dashboard once approved, including alert feedback |

Statuses are `pending` (where every account after the first starts), `approved` and `suspended`; the backend's `require_auth` accepts only approved accounts (§5.2). The owner counts as an admin everywhere: `require_admin`, the frontend's `isAdminRole()` and the Firestore and Storage rules all accept either role.

**Sign-up**
- **Email and password:** the browser creates the Firebase Auth account and sends the verification email, then `POST /auth/register` verifies the ID token and creates `users/{uid}`. The form accepts only a "strong" password (8 or more characters with at least three of upper case, lower case, digit and symbol) with a matching confirmation.
- **Email verification:** every email-and-password account, the owner's included, must verify its address before the dashboard opens. `/pending-approval` checks Firebase until the link is clicked, then calls `POST /auth/verify-email` with a force-refreshed token. The backend trusts only the token's signed `email_verified` claim and sets `email_verified` on the user doc.
- **Google:** `POST /auth/google` verifies the Firebase ID token from the Google sign-in, creates the user doc if it's missing (already verified) and returns role and status.

**Sign-in gate**
- `AuthProvider` (`hooks/useAuth.ts`) runs one app-wide Firebase auth listener. For a user with a verified email it reads `users/{uid}` with a 15 s deadline.
- `app/dashboard/layout.tsx` sends a signed-out visitor to `/login`, a pending account to `/pending-approval` and a suspended one to `/suspended`.
- The record is read once per sign-in, not live, so an approval takes effect at the user's next sign-in or page reload.
- On the backend, `require_auth` verifies the Firebase ID token and loads `users/{uid}`. `require_admin` adds role `admin` or `owner`, and `require_owner` role `owner`. Browsers can't write user documents.

**Users page** (`/dashboard/users`, admins)
- A live Firestore listener over `users`, newest first, leaving out pending accounts whose email isn't verified.
- **Approve** (pending rows): `PATCH /users/{uid}/status` with `approved` (`require_admin`).
- **Promote to Admin** (approved users) and **Demote to User** (admins), shown to the owner only: `PATCH /users/{uid}/role` (`require_owner`). The owner's own role can't be changed.
- **Remove**, after a confirmation: `DELETE /users/{uid}` (`require_admin`) deletes the Firebase Auth account and the Firestore doc.
- `person_id` links an account to a beacon's track. The register form doesn't set it and no route changes it.

### 3.11 Beacon Identity Management
A beacon is identified by its iBeacon triple, key `"<uuid, lower-cased>:<major>:<minor>"`, mapped to a `person_id`, a `person_type` (`guard`, `worker` or `forklift`), a `label` and a per-device `tx_power`. There's no plain-MAC identity: report entries without an iBeacon block are skipped (§3.7). The registry is the Firestore `beacons` collection:
- `backend/models/beacon.py`: `Beacon`.
- `backend/repositories/beacon_repository.py`: Firestore CRUD, plus `seed_from_legacy()`.
- `backend/services/beacon_service.py`: create, update and delete. Each empties `OmadaIngestService`'s identity cache, so the next report resolves against the new registry. A label change also patches `label` on the live `/positions/<person_id>` node when one exists (it never creates one), and a delete removes that node.
- `backend/routes/beacon_routes.py`: `GET /beacons` (`require_auth`); `POST /beacons`, `PATCH /beacons/{beacon_id}` and `DELETE /beacons/{beacon_id}` (`require_admin`). The iBeacon triple is the key, so re-keying means deleting the beacon and registering it again.
- `person_id` is the key the real path writes `/positions` under, and the key of the person's Kalman filter and man-down state.
- Major and minor must match the exact strings the APs report (for example zero-padded `0001`); only the UUID is lower-cased.

**Dashboard** (`/dashboard/beacons`; the nav link is shown to admins, and writes are enforced by `require_admin`):
- `frontend/components/map/BeaconManager.tsx`: the registry table (status, person, type, iBeacon), a create and edit dialog (the identity fields are locked when editing; Tx power defaults to −59), and an **Unknown Beacons** panel listing unregistered beacons heard in the last 10 s, each with a Register button that pre-fills the form with the identity exactly as reported.
- `frontend/hooks/useBeaconScans.ts`: subscribes to RTDB `/beacon_scans` and re-renders every second. A registered beacon is Online while its node is under 10 s old.
- `frontend/services/beaconService.ts`: calls `/api/beacons` with the user's Firebase ID token.

**`/beacon_scans`**: the ingest writes `{uuid, major, minor, rssi, ap_mac, last_seen, registered}` for every iBeacon heard by an AP placed on an active floor (§3.7); the latest report wins, not the strongest.

`config/beacon_registry.py` still supplies `make_ibeacon_key()` and the `BeaconIdentity` type at request time. Its `SEED_BEACONS` dict is empty by design: beacons are registered through the dashboard or the API.

### 3.12 VIGI Camera Integration

TP-Link VIGI IP cameras are placed on a floor like APs and connected to SKYE in four ways: the camera **pushes its alarm events** to the backend; the backend **checks each camera's health** and **finds cameras on the local network**; and admins **watch live video** through go2rtc. Camera events are kept for 15 minutes and shown in the dashboard's camera panel, but nothing uses them yet to confirm patrol checkpoint visits: Ghost Patrol's camera check is not built (§3.2, §9b).

```
Alarms
  camera ── POST /vigi/alarm/<secret> (backend port) ──► VigiService.handle_alarm
  └─► only a registered MAC from its registered IP: vigi_alarm_parser
      └─► DetectionBuffer (in memory, last 15 min, per camera_key)
          └─► GET …/cctvs/{id}/detections ──► CameraPanel (every 3 s)

Health and discovery (default intervals; every write through cctv_repository.update_heartbeat)
  liveness_loop    TCP connect to port 554, every 5 s ──► last_seen
  openapi_loop     read-only OpenAPI calls, every 300 s ──► probe, alarm_config
  discovery_loop   ONVIF WS-Discovery, every 60 s ──► discovered_*, ip
  handle_alarm     accepted alarm push ──► last_event_at
  └─► RTDB /cctv_heartbeats/{AA_BB_CC_DD_EE_FF} ── onValue ──► useCCTVHeartbeats

Live view
  SDP:    browser ↔ …/cctvs/{id}/webrtc ↔ live_view_service ↔ go2rtc API (loopback)
  media:  camera ─RTSP─► ffmpeg ─MPEG-TS─► go2rtc ─WebRTC, port 8555─► browser
  (live_view_service writes go2rtc.yaml; tools/go2rtc/start.ps1 runs go2rtc)
```

**Registry and `camera_key`** (`backend/models/cctv.py`, `backend/services/cctv_service.py`)
- **`camera_key`** is `<source_type>:<MAC without separators>:<channel>`. It is derived, not stored, and it keys the detection buffer, the OpenAPI client, and go2rtc's stream names (§5.3).
- **Create, edit and delete go through `CCTVService`**: `(device_mac, channel)` is unique across all floors, and a create, or an edit that includes the IP, MAC or channel, queues an immediate health check (`camera_health_service.check_now`).
- **Dashboard:** the camera dialog requires a MAC and an IPv4 address, since alarms are only accepted from that address (§3.13).
- **Checkpoint link:** a camera can name the checkpoint AP it covers (`checkpoint_ap_id`, an AP on its own floor); deleting that AP clears the link. Only Manage Devices and the camera panel show it so far; Ghost Patrol will use it (§4.8).

**Alarm push: `POST /vigi/alarm/{path_secret}`** (`backend/routes/vigi_routes.py`, `backend/services/vigi_service.py`)
- The camera's Alarm Server posts each event straight to the backend's port, so the backend must listen on the LAN (§9b). The camera sends no authentication header, so **the path segment is the credential**.
- Checks, in order:
  1. **Rate limit:** 600 requests a minute.
  2. **Secret:** `VIGI_ALARM_PATH_SECRET` must be set and at least 24 characters long, and the segment is compared in constant time (`hmac.compare_digest`).
  3. **Sender:** only a registered MAC posting **from its registered IP** has its events parsed, added to the detection buffer and stamped on the heartbeat as `last_event_at`.
- **Payload formats** (`services/vigi_alarm_parser.py`): each event becomes a `CameraDetection`. `is_human` is true only for `PEOPLE`; `MOTION` alone never counts as a person.

**Liveness (port 554) and status colours** (`backend/services/camera_health_service.py`)
- `CameraHealthService.liveness_loop` runs every `VIGI_LIVENESS_INTERVAL_S` (default 5 s): an async TCP connect to port 554 at each registered camera's IP, and at each unregistered camera that discovery or an alarm push found in the last 10 minutes. No credentials are involved.
- **Green means only that the RTSP port answers at the registered IP.** Whether the camera's login works and whether its alarms arrive are separate rows in the camera panel (§3.6, §8).

**OpenAPI health checks and the lockout guard** (`camera_health_service.py`, `backend/services/vigi_openapi_client.py`)
- `openapi_loop` checks one registered camera per reporting device, one at a time, every `VIGI_OPENAPI_INTERVAL_S` (default 300 s).
- Each check is read-only: `getDeviceStatus`, `getSystemTime` and `getPeopleDetectionSwitch`.
- **Lockout guard:** the camera locks its admin account after repeated failed logins, so `LockoutGuard` writes a marker file under `backend/logs/` before each password-bearing `doAuth`, and deletes it on a confirmed success (§5.4).

**Discovery** (`backend/services/camera_discovery_service.py`)
- One ONVIF WS-Discovery Probe goes out from each of this machine's private LAN interfaces to the WS-Discovery multicast group (UDP 3702) with TTL 1, so it never leaves the local segment. Only VIGI cameras are kept.
- A round runs at startup and then every `VIGI_DISCOVERY_INTERVAL_S` (default 60 s), and on demand from Manage Devices' **Scan now** (`POST /cctvs/discover`, §5.2).
- A registered camera found at another address gets `ip_mismatch`; alarms are still accepted only from its registered IP.
- Manage Devices lists cameras **online but not placed**. Clicking one starts Add CCTV with its MAC and IP filled in.

**Live view: WebRTC through go2rtc, ffmpeg in front** (`backend/services/live_view_service.py`, `tools/go2rtc/start.ps1`, `frontend/components/map/CameraLiveView.tsx`)
- **Why ffmpeg:** the VIGI camera SKYE was built against ends every frame with a small SEI NAL unit, and go2rtc 1.9.14's H.264 depacketizer drops that unit without completing the frame (`docs/go2rtc-sei-issue.md`). Each stream is therefore an `exec:` source: ffmpeg strips the SEI units and pipes MPEG-TS to go2rtc.
- **The generated file never holds the camera password:** each stream's RTSP address carries the `${VIGI_CAMERA_PASSWORD}` placeholder, which go2rtc fills in from its own environment when it loads the file.
- **`start.ps1`** relaunches go2rtc when the config file changes, when the password in `.env` changes and when go2rtc exits.
- **Signalling:** the browser posts its SDP offer to `POST …/cctvs/{cctv_id}/webrtc` (`require_admin_strict`: admins only; 30 a minute). `open_stream()` checks, in order: that the offer is a video-only, receive-only SDP of at most 64 KB; that the camera isn't behind an NVR and has a MAC and an IP; and that it is online by the 10 s rule. It then forwards the offer to go2rtc and returns **only the SDP answer**, never a stream address.
- **In the browser,** `CameraLiveView` (top of the camera panel) is for admins only. Video plays in a browser on the machine that runs go2rtc; viewing from other devices isn't built (§4.11).

**Camera direction: `facing_deg`, `fov_deg` and the cones** (`frontend/components/map/CameraCone.tsx`)
- A camera can store which way it faces on the floor plan: `facing_deg`, in degrees clockwise from the top of the plan (0 to under 360), and `fov_deg`, its field of view (10–360). The direction is for display only: nothing else in the backend reads it (§3.13).

**Detections and the camera panel** (`backend/services/camera_detection_buffer.py`, `frontend/components/map/CameraPanel.tsx`)
- `DetectionBuffer` keeps the last **15 minutes** of accepted events per `camera_key` in memory.
- Clicking a camera marker on the dashboard map opens the **camera panel**. Alarm setup is judged from what actually arrives, since the camera's API can't read its Alarm Server settings: "Working" when the last accepted alarm is under 24 hours old.

### 3.13 Floor Plans Editor

The Floor Plans tab (`app/dashboard/floor-plans/page.tsx`). Every approved user can open it and see the buildings and floors. Everything below is admin-only in the UI: each record change goes through a `require_admin` route (§3.5).

- **Layout:** the buildings list on the left and the selected building's floor cards on the right. A card shows the thumbnail, the name, an ACTIVE badge, the calibration and the patrol state. Its ⋯ menu holds **Set as Active** or **Deactivate**, Rename, **Calibrate Scale** or **Recalibrate** (§3.5), **Manage Zones**, **Manage Devices**, **Manage Patrol** (§3.3) and Delete Floor.
- **Activation:** a refused activation (409, §3.5) opens a dialog listing each conflicting active floor, its building and the shared APs, with a Deactivate button per floor. Every deactivation asks first: live tracking, alerts and patrols stop on that floor until it's active again.
- **Manage Zones** (`ZoneEditor`), on a calibrated floor:
  - **Add Zone:** click the corners, right-click to close; the outline is saved as its bounding rectangle. Then a name, one of four colour presets and a high-risk checkbox.
  - **AI Detect** (§3.5): suggestions are drawn dashed. Each can be moved, resized and renamed before it's saved, or discarded.
  - **Saved zones** can be shown or hidden, and deleted. A saved zone can't be edited in the UI.
- **Manage Devices** (`APCCTVEditor`); Add AP, Add CCTV and Walls stay off until the floor is calibrated:
  - **Add AP / Add CCTV** always start from an empty form, and a click on the plan opens the place dialog: a name and MAC for an AP, and for a camera its MAC, IP, an optional checkpoint AP and its direction (§3.12). Place in an online-but-not-placed list (§3.6, §3.12) fills the form in.
  - **Markers**, coloured by status (§3.6), are dragged to move: the move is saved on release (an AP's metres re-derived on the server), and Esc while the button is held cancels it. ✕ on hover, or the device table, removes a device.
  - **Placement guides (Walls)**, in three steps: (1) draw the room's outline the way a zone is drawn (`PolygonDraft.tsx` is shared); (2) click the wall to measure X from; (3) click another wall for Y, which must be more than 30° from parallel to the first (§9).
  - **The guides:** while a device is placed, dragged or hovered, two dimension lines show its X and Y, its distances in metres from the two walls. The place dialog takes typed X and Y, which move the point to where those distances meet.
  - **Where the walls live:** per floor in that browser's `localStorage`, not in Firestore. They're an aid only: a device is still saved as image fractions.
  - **Camera direction** (§3.12): a camera with a facing gets a translucent cone in its status colour on both maps, a fixed length on screen, since it shows a direction, not coverage. In Manage Devices a handle at the cone's tip turns it in whole degrees, saved on release. A camera with no facing gets a dashed default cone towards the middle of the map, here only: it's saved when its handle is released or when Facing is saved in the camera dialog.

---

## 4. Future Improvements

4.1–4.3 are done and kept for reference; 4.8 onward is the plan as of 18 November 2026.

### 4.1 Patrol Route Overlay on Floor Map
**Done.** The live map draws the route as a faint dashed line through its APs while patrol is enabled; direction arrows, checkpoint states, arrival times and dwell-sized markers are on the Patrol Reports page (§3.3, §3.9).

### 4.2 Real BLE Checkpoint Tracker (`patrol_tracker_service.py`)
**Done for BLE.** `PatrolTrackerService` logs live checkpoint visits with their dwell and raises `patrol_violation` (`missed_checkpoint`, `short_dwell`, `no_patrol`) as each window closes (§3.3). The camera half isn't built: the tracker writes `vigi_detected=False` placeholders and never calls `verify_multimodal()`, so `ghost_patrol` still can't fire from real hardware (§4.8, §9b).

### 4.3 RAG Re-enable
**Done.** Re-enabled on the `google-genai` SDK with `gemini-embedding-001`: patrol reports get the most similar past alert feedback as context (§3.8).

### 4.4 AI Chatbot — Natural Language Query Interface
Not built: there's no `/chatbot` route and no chat UI. The idea is a chatbot in the dashboard that lets admins and users search reports and alerts in plain English instead of filter panels.

**Concept:**
```
User: "Show me all man_down alerts for worker-001 in the last 7 days"
User: "Generate a patrol report for Guard Alpha's most recent shift"
User: "Which zone had the most alerts this week?"
User: "Was there a collision warning yesterday?"
```

**Planned implementation:**
- **Frontend**: a floating chat panel in the dashboard, or a modal overlay.
- **Backend**: `POST /chatbot/query` passes the message to the configured LLM provider (Gemini today, §5.5) with a function-calling prompt that maps the intent to one of:
  - an RTDB alert query (by person, date, alert type);
  - a Firestore patrol log query (by guard, cycle or shift, date);
  - an audit report lookup in Firestore;
  - a report generation trigger, admin-only like the report routes (§3.8).
- **LLM returns** structured JSON with the intent and its parameters; the backend runs the query against Firebase and returns formatted results to the chat panel.
- **Context awareness**: the active floors, today's date and the known person IDs, so it can resolve "the worker", "yesterday" or "Guard Alpha".

Operators would no longer need to know which tab, selector or filter to use: they would simply ask.

### 4.5 Simulation Per-Guard Shift Rotation in `simulation_events.py`
Not built. `simulation_events.py` still keeps one `shift_id` per run, and its tick handlers have no per-actor try/except; only the HTTP post is guarded (§3.4). The plan: the per-guard `shift_id`, `loops_completed` and `checkpoints_this_loop` pattern of `simulation_patrol.py` and `simulation_shift.py`, and a try/except per actor per tick, so one actor's failure can't crash the whole loop.

### 4.6 Patrol Compliance Analytics Dashboard
Not built. A page of patrol compliance trends over time: checkpoint hit rate per guard, average dwell against the minimum, ghost patrol frequency by zone, a missed-checkpoint heatmap. `patrol_logs` now hold the live tracker's visits per cycle (`cycle_id`, `not_in_window`) besides the simulators' logs. The closest thing today is the per-cycle Patrol Reports page (§3.3), which has no charts; this would be Recharts' first real use (§9b).

### 4.7 Mobile Supervisor View
Not built. A read-only, mobile-optimised view for supervisors on the floor: live positions, active alerts, and acknowledging (admins) and resolving alerts from a phone, without the admin configuration panels. Both actions exist on the desktop dashboard (§3.2, §3.9), whose shell is a desktop layout with a fixed sidebar.

### 4.8 Ghost Patrol Evaluator
Planned next: the camera half of patrol verification, as designed in section 7 of `docs/vigi-integration-design.md`, with its prerequisites.
- An evaluator, outside the pipeline lock, takes each real checkpoint visit the tracker closes and looks for `PEOPLE` events from the cameras linked to that checkpoint (`checkpoint_ap_id`, §3.12), in the visit's window padded by 10 s on each side.
- The verdict is stored on the patrol log, which also gains `departed_at`. `alarm_config` (mismatch or unknown) is to feed into the verdicts in some form, and the project owner draws each camera's detection area.
- Only a "not seen" verdict raises `ghost_patrol`, through `verify_multimodal()`, at most once per guard, checkpoint and cycle: the limit `verify_multimodal()` lacks today.
- Patrol is switched on for the real floors, where it stays off until then.

It also needs the camera's alarms to get through (§9b).

### 4.9 Planned Work After Ghost Patrol
After Ghost Patrol, the plan continues in this order:
- Firebase rules and account controls.
- Reports and the simulator, including the simulator limits in §9b.
- Positioning robustness and observability, with two earlier items:
  - an offline calibration replay, which waits for ground truth (times and positions) for the 30 Sep and 1 Oct field captures;
  - a null-RSSI grace period, not started yet. Null readings (`"rssi": {}`) are dropped, and each AP reports about once a second; on a 7 Sep replay, a 2 s grace would lift three-AP decisions from 73% to 95.5%.
- Reliability and housekeeping, including the two items parked for it (§4.10).
- A documentation pass, unless earlier work touches the code first: `docs/vigi-integration-design.md` (its header still says nothing is built, and its section 8 predates the live view as built, §3.12); `README.md`'s note on the simulators and active floors; two comments in `backend/.env.example` (`MAN_DOWN_MINUTES` mentions zones, which man-down ignores; `COLLISION_DISTANCE_M` is described as a man-down distance); stale docstrings in `kalman_service.py` and `patrol_tracker_service.py`; and the tracker's leftover temporary diagnostic print.

### 4.10 Parked Items
Decided on 17–18 Nov to wait; each is described in §9b:
- alerts that store every AP their run had, against restart repeats at the 1-minute test setting;
- a firmer cancel rule for the AP-change hold, which one missed report restarts;
- the camera's lost alarms, being looked at again as the camera's alarm settings are set up (18 Nov);
- for the reliability work: the 22 s Firebase hang after one reload, and a 404 instead of a 500 for a position update to a device that's gone.

### 4.11 Live View from Other Devices
Not built: video plays only in a browser on the machine that runs go2rtc (§3.12). Viewing from other devices would need go2rtc's media port (8555, TCP and UDP) opened to them on that machine, and dashboard access from those devices.

---

## 5. Backend Detail

### 5.1 Application Setup (`main.py`)

`backend/main.py` builds one FastAPI app, `SKYE Sentinel-AI` v0.1.0, in `create_app()` when the module is imported:

1. **Console and capture log, before any other import:** stdout and stderr are switched to UTF-8, then `utils/capture_log.install_capture_log()` copies everything printed or logged into `backend/logs/skye-<UTC timestamp>.log` (UTF-8, a new `.partNNN.log` every 50 MB; gitignored). Once logging is configured, `utils/log_redaction.install_log_redaction()` rewrites any `/vigi/alarm/<…>` path to `/vigi/alarm/***` in uvicorn's, slowapi's and the request logger's records.
2. **Settings:** importing `config/settings.py` loads `backend/.env` into a frozen `Settings` object; a missing required variable stops startup (§10).
3. **Firebase:** `firebase_admin.initialize_app()` with the service-account certificate at `FIREBASE_KEY_PATH` and `databaseURL` set to `FIREBASE_RTDB_URL`. RTDB, Firestore and Storage all go through this one Admin SDK app.
4. **Idempotent seeds:** `beacon_repository.seed_from_legacy()` copies `config/beacon_registry.SEED_BEACONS` into Firestore `beacons` (the dict is empty, so nothing is copied unless entries are added); `safety_settings_repository.seed_defaults()` creates `settings/safety` from `MAN_DOWN_MINUTES` and `COLLISION_DISTANCE_M` if it's missing; `user_repository.ensure_owner_exists()` promotes the earliest-registered admin to owner if there is no owner.
5. **Middleware**, outermost first:
   - `RequestLoggerMiddleware`: method, redacted path and duration in ms for every request.
   - `MaxBodySizeMiddleware`: a 1 MB request-size cap (413 `Payload too large`).
   - CORS: origins `http://localhost:3000` and the same port on the IPv4 loopback address only; credentials allowed; methods GET, POST, PUT, PATCH and DELETE; headers `Authorization` and `Content-Type`. The dashboard calls the backend through Next.js's same-origin `/api/*` rewrite (§10), so CORS only comes into play for a page that calls port 8000 directly.
   - `SlowAPIMiddleware` with `utils/limiter.limiter`; an exceeded limit answers 429 (§5.2).
6. **Exception handlers** (`middleware/error_handler.py`): a `ValueError` becomes a 400 with an `error` field; any other unhandled exception becomes a 500 with the fixed `error` text `Internal server error`. `HTTPException`s keep FastAPI's `detail` body.
7. **Routers**, all mounted with no prefix (no `/api`): `auth · telemetry · omada_telemetry · vigi · alert · beacon · building · floor · health · zone · report · safety_settings · user · simulation`. No router-level dependencies are applied; each route declares its own auth (§5.2).

**Lifespan** (`lifespan()`):

- **Startup:** stamps the camera detection buffer's process start; logs one warning if `VIGI_ALARM_PATH_SECRET` is unset or shorter than 24 characters (the alarm route then answers 404); brings go2rtc's live-view config in line with the camera registry (`live_view_service.refresh_config()`, written only when its content changes); removes every simulator's leftover `/positions` records, since no simulation can be running yet and the signal-loss sweep would otherwise alert on them.
- **Background tasks:**

  | Task | What it does |
  |---|---|
  | `_man_down_stale_loop()` | Every 60 s, runs `SafetyService.check_man_down_stale()` in a worker thread: signal-loss man-down and `positioning_offline`, independent of telemetry arrival |
  | `camera_health_service.liveness_loop()` | A TCP connect to each camera's RTSP port every `VIGI_LIVENESS_INTERVAL_S` (default 5 s) |
  | `camera_health_service.openapi_loop()` | The camera OpenAPI health check: first after `VIGI_OPENAPI_START_DELAY_S` (default 60 s), then every `VIGI_OPENAPI_INTERVAL_S` (default 300 s) |
  | `camera_discovery_service.discovery_loop()` | An ONVIF discovery round at startup, then every `VIGI_DISCOVERY_INTERVAL_S` (default 60 s; 0 turns it off) |

- **Shutdown**, which also happens on every `--reload`: `cancel_running_simulation(timeout=8.0)` runs first, so a running simulator's `finally` removes its people from `/positions` while the event loop still runs; then the background tasks are cancelled.

**Running it.** README.md's dev command runs `uvicorn main:app --reload` on port 8000, bound to all interfaces: the APs and the camera post to this machine, which a loopback-only bind wouldn't let them reach (§9b). `python main.py` makes the same bind itself, on `PORT`, with reload set by `DEBUG`. `--reload` restarts the server on every saved `.py` file but doesn't watch `.env`: restart the backend after editing it.

**One process.** `pipeline_lock`, the man-down latches, the ingest buffers and caches, the patrol tracker's state, the camera detection buffer and the background loops all live in memory, per process. The design assumes a single worker: under several, each loop would run once per worker and raise duplicate alerts.

### 5.2 Routes

Every route is mounted at the root; the dashboard's `/api/...` calls reach it through the Next.js rewrite. The tables give each route's auth dependency; the Limit columns give slowapi rate limits. Plain `def` handlers run in FastAPI's thread pool; the two telemetry routes hand their blocking Firebase work to a worker thread and hold `positioning_service.pipeline_lock` around positioning and the safety checks, so the simulated and the real path never interleave. Some reads exist for API clients only: the dashboard takes alerts, buildings, floors, APs, cameras and users straight from Firebase (§8), and nothing in the dashboard calls `GET /health/tracker`.

#### Auth dependencies (`middleware/auth_middleware.py`)

| Dependency | Checks | Fails with |
|---|---|---|
| `require_auth` | `Authorization: Bearer <Firebase ID token>`, verified by the Admin SDK (60 s clock skew); `users/{uid}` must exist and be neither pending nor suspended | 401 (bad or expired token, no user doc), 403 (pending, suspended), 422 (no header) |
| `require_auth_strict` | As `require_auth` | Also 401 when the header is missing |
| `require_admin`, `require_admin_strict` | The matching `require_auth` variant, then role `admin` or `owner` | 403 |
| `require_owner` | `require_auth`, then role `owner` | 403 |
| `require_loopback` | The caller is a loopback address (IPv4 or IPv6) | 403 with a fixed sentence, before any token check |
| `verify_omada_source` | The caller's IPv4 address is on `OMADA_INGEST_ALLOWED_IPS` | 403 with a fixed sentence |
| `verify_omada_token` | `Authorization: Bearer <OMADA_ACCESS_TOKEN>`, compared in constant time | 401 |
| `verify_omada_body_token` | The JSON body's `meta.access_token` equals `OMADA_ACCESS_TOKEN`, compared in constant time | 401 |

#### Auth — public, rate-limited

| Method | Path | Limit | Description |
|---|---|---|---|
| POST | `/auth/register` | 5 per 15 min | `{id_token, display_name, person_id?}`. The browser creates the Firebase Auth account (email and password) and sends its ID token; the backend verifies it and creates `users/{uid}` unless it already exists. The very first account becomes `owner` and `approved`; every later one starts as `user` and `pending`. `email_verified` comes from the token. |
| POST | `/auth/verify-email` | 10 per min | The ID token in `Authorization: Bearer`, verified in the handler. When its `email_verified` claim is true, sets `email_verified` on the user doc; 400 while it isn't. |
| POST | `/auth/google` | 5 per 15 min | `{id_token}` from Google sign-in, verified; returns the existing user doc's role and status, or creates the doc (same first-account rule, `email_verified` true). |

#### Telemetry — device credentials

| Method | Path | Auth | Limit | Description |
|---|---|---|---|---|
| POST | `/telemetry` | `require_loopback`, then `verify_omada_token` | 200 per min | The simulators' and the test harness's path, from this machine. A beacon-centric `TelemetryRequest` (§5.3) → `/ap_heartbeats` `{mac, last_seen}` for each AP in it → `PositioningService.compute_position()` → `SafetyService.run_all_checks()`. |
| POST | `/telemetry/omada` | `verify_omada_source`, then `verify_omada_body_token` | 600 per min | Real APs, which send no auth header. The raw AP-centric Omada report → `OmadaIngestService.ingest()` (§3.7). Answers `ok` with counts, `online_unregistered` for an AP that isn't placed on an active floor (its heartbeat is still written), or `ignored` when there's no `reporter.mac`. |

#### Alerts — require_auth / require_admin

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/alerts` | require_auth | All of RTDB `/alerts`, keyed by alert id. |
| POST | `/alerts/{alert_id}/feedback` | require_auth | `{feedback: confirmed / fixed / false_alarm, reason?}`. Sets `resolved` on the alert and writes a Firestore `feedback` doc, the RAG corpus. Feedback is the only way an alert gets resolved. An unknown alert is a 400. |
| POST | `/alerts/{alert_id}/acknowledge` | require_admin | Closes the alert's pop-up on every dashboard: writes `acknowledged_at`, `acknowledged_by` (the admin's display name, or `admin`) and `acknowledged_by_uid` once; a repeat returns the first values. The alert stays unresolved. 404 for an unknown alert. |
| DELETE | `/alerts/{alert_id}` | require_admin | Deletes the alert permanently. |

#### Beacons — require_auth / require_admin

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/beacons` | require_auth | Every registered beacon (§3.11). |
| POST | `/beacons` | require_admin | `{uuid, major, minor, person_id, person_type: guard / worker / forklift, label, building_id?, tx_power = -59}`. The id is `<uuid in lower case>:<major>:<minor>`; a duplicate is a 409. |
| PATCH | `/beacons/{beacon_id}` | require_admin | Changes person_id, person_type, label, building_id or tx_power (404 if unknown). A new label is patched onto `/positions/{person_id}` when that record exists; none is ever created. |
| DELETE | `/beacons/{beacon_id}` | require_admin | Deletes the beacon and the person's `/positions/{person_id}` record (404 if unknown). |

Every beacon write clears the ingest's beacon cache, so a change applies from the next AP report.

#### Users — require_admin / require_owner

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/users` | require_admin | Every user, newest first, leaving out pending users who haven't verified their email. First deletes the Firestore doc of any user whose Firebase Auth account no longer exists. |
| GET | `/users/pending` | require_admin | Pending users, with the same clean-up. |
| PATCH | `/users/{uid}/role` | require_owner | `{role: admin / user}`. The owner's own role can't be changed (400). |
| PATCH | `/users/{uid}/status` | require_admin | `{status: pending / approved / suspended}`. The Users page's Approve button uses it; suspending isn't offered in the UI. |
| DELETE | `/users/{uid}` | require_admin | Deletes the Firebase Auth account, then the user doc. The caller's own account is refused (400). |

The Users page and the sidebar's pending badge read `users` from Firestore directly (§8).

#### Buildings — require_auth / require_admin

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/buildings` | require_auth | Every building, newest first. |
| POST | `/buildings` | require_admin | `{name, description?}`; `user_id` is the creating admin. |
| PATCH | `/buildings/{building_id}` | require_admin | `{name}`. |
| DELETE | `/buildings/{building_id}` | require_admin | Deletes each floor through `FloorService.delete()` (below), then the building. |

#### Floors / APs / CCTVs — require_auth / require_admin

Paths start with `/buildings/{building_id}/floors`. Reads use `require_auth` and changes `require_admin`, except the two camera routes on the strict variants. A scale change, activation or deactivation clears `PositioningService`'s per-floor caches and Kalman filters; those and every AP placement, move or delete also clear the ingest's AP cache instead of waiting out its 30 s expiry.

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | (prefix) | require_auth | The building's floors, by `floor_number`. |
| POST | (prefix) | require_admin | `{name?, floor_number = 1, url, storage_path, image_width_px?, image_height_px?}`, sent after the browser has uploaded the plan to Storage (§8). A blank name becomes `Level N`. New floors are inactive. |
| PATCH | `/{floor_id}` | require_admin | Rename; only `name` is applied. |
| PATCH | `/{floor_id}/scale` | require_admin | `{scale_pixels_per_meter, calibration?: {a: {x_pct, y_pct}, b: {x_pct, y_pct}, distance_m}}`. Saves the scale with the calibration that produced it (kept for the next Recalibrate; leaving it out clears it), multiplies each zone's bounds by old ÷ new px/m so zones stay where they're drawn, and re-derives every AP's metres. 422 with one sentence for a bad calibration; 400 for a scale of 0 or less. |
| PATCH | `/{floor_id}/activate` | require_admin | Other active floors stay active. 409 with `{message, conflicts: [{floor_id, floor_name, building_id, building_name, aps: [{name, mac}]}]}` when another active floor holds one of this floor's APs (by MAC); 404 for an unknown floor. |
| PATCH | `/{floor_id}/deactivate` | require_admin | Deactivates the floor. |
| PATCH | `/{floor_id}/patrol` | require_admin | `{patrol_enabled, patrol_route: [ap_id, …], patrol_interval_minutes = 10}`. |
| DELETE | `/{floor_id}` | require_admin | Deletes the zones; the APs (each MAC's `/ap_heartbeats` node only when no other floor holds that AP); the cameras and their heartbeat nodes; the plan in Storage; then the floor. |
| GET | `/{floor_id}/aps` | require_auth | The floor's APs. |
| POST | `/{floor_id}/aps` | require_admin | `{name, mac, x_pct, y_pct}`, the MAC as `XX:XX:XX:XX:XX:XX` (stored upper-case). `x_m` and `y_m` are derived from the floor's scale and image size; metres from the client are ignored. 409 with one sentence when the MAC is already on this floor, when this floor is active and another active floor holds the MAC, or when the floor isn't calibrated. |
| PATCH | `/{floor_id}/aps/{ap_id}` | require_admin | Rename only: trimmed, 1–64 characters (422), 404 if unknown. The MAC is the AP's identity. |
| PATCH | `/{floor_id}/aps/{ap_id}/position` | require_admin | The marker was dragged: new fractions, metres re-derived (409 on an uncalibrated floor). |
| DELETE | `/{floor_id}/aps/{ap_id}` | require_admin | The cascade in `FloorService.delete_ap()` (§9, AP Delete Cascade). |
| GET | `/{floor_id}/cctvs` | require_auth | The floor's cameras, each with its derived `camera_key`. |
| POST | `/{floor_id}/cctvs` | require_admin | `{name, x_pct, y_pct, mac?, ip?, checkpoint_ap_id?, channel?, source_type?, facing_deg?, fov_deg?}`, checked by `CCTVService` (422 or 409 with one sentence): the MAC in any common form, normalised; the device MAC and channel unique across all floors; the checkpoint an AP on the same floor; an IPv4 address; channel 1–256; facing from 0 to under 360°, field of view 10–360° (90 when a facing comes without one). Reads the camera's time zone once and queues an immediate health check. |
| PATCH | `/{floor_id}/cctvs/{cctv_id}` | require_admin | Changes only the fields sent; `null` clears `ip` or `checkpoint_ap_id`, and `facing_deg: null` clears the facing and the field of view together. An edit that sends ip, MAC or channel queues a health check. |
| GET | `/{floor_id}/cctvs/{cctv_id}/detections` | require_auth_strict | The camera's alarm events from the last 15 minutes, newest first, from backend memory, with `process_started_at` (a restart empties the window). |
| POST | `/{floor_id}/cctvs/{cctv_id}/webrtc` | require_admin_strict; 30 per min | Live view: `{sdp, quality: sub / main}`. The browser's offer goes to go2rtc on the backend machine and only the SDP answer comes back, never a stream address. 404 unknown camera; 409 camera offline, without a MAC or IP, or behind an NVR; 422 not a receive-only video offer; 503 go2rtc not running or not reloaded yet, or ffmpeg missing; 502 or 504 when the stream doesn't start. |
| PATCH | `/{floor_id}/cctvs/{cctv_id}/position` | require_admin | New `x_pct` and `y_pct`. |
| DELETE | `/{floor_id}/cctvs/{cctv_id}` | require_admin | Deletes the camera, drops its buffered detections and OpenAPI session, rewrites the go2rtc config, and removes its `/cctv_heartbeats` node unless another camera reports through the same device. |

The camera's alarm route and `POST /cctvs/discover` are with the VIGI routes.

#### Zones — require_auth / require_admin

Paths start with `/buildings/{building_id}/floors/{floor_id}/zones`. Every change clears the positioning cache, so a zone applies at once.

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | (prefix) | require_auth | The floor's zones: axis-aligned rectangles in metres. |
| POST | (prefix) | require_admin | `{name, color = #3b82f633, is_high_risk = false, risk_level = moderate, x_min, x_max, y_min, y_max}`; `created_by` is the admin. |
| PATCH | `/{zone_id}` | require_admin | Changes the fields sent; an unknown zone answers 500, not 404, as the position updates do (§9b). |
| DELETE | `/{zone_id}` | require_admin | Deletes the zone. |
| POST | `/ai-detect` | require_admin | Gemini vision reads the floor plan and suggests zones (`utils/gemini_zone_detector.py`, with the `LLM_MODEL_NAME` model); 400 on an uncalibrated floor. Nothing is saved: the editor creates the zones it keeps. |

#### Reports — require_admin

| Method | Path | Description |
|---|---|---|
| GET | `/reports/shifts` | One entry per shift_id and guard_id in `patrol_logs` with at least one arrival, newest first, at most 50. |
| POST | `/reports/generate` | `{log_id (the shift_id), guard_id}`: the guard's logs for that shift, all of the guard's RTDB alerts and RAG context go to the LLM; the report is saved to `audit_reports` as `report_type` `patrol`, with `rag_examples_used`. 404 when there are no logs. |
| GET | `/reports/safety-groups` | Each person and date with alerts in RTDB `/alerts`, with its count, newest date first. |
| POST | `/reports/generate-safety` | `{person_id, date_str}` (`YYYY-MM-DD`): that person's alerts on that day go to the LLM; saved as `report_type` `safety_event` with `shift_id` `safety-<person>-<date>`. 404 when there are none. |

No route lists reports: the Reports page subscribes to `audit_reports` in Firestore (§8).

#### Safety Settings — require_auth / require_admin

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/settings/safety` | require_auth | `settings/safety`, or the `.env` defaults when the doc is missing. |
| PUT | `/settings/safety` | require_admin | `{man_down_minutes: 1–60, collision_distance_m: 0.5–10}`; clears `SafetyService`'s 30 s settings cache. |

#### Health — require_auth

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health/tracker` | require_auth | The patrol tracker's invocation health, from `SafetyService`: failure counts and the times of the last error, success and invocation. In memory, so a restart resets it. |

#### Simulation — require_admin / require_auth

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/simulation/start?mode=` | require_admin | Starts the `patrol`, `events` (the default) or `shift` simulator (§3.4) as an asyncio task inside the backend; 400 if one is already running. |
| POST | `/simulation/stop` | require_admin | Cancels it and waits; its `finally` removes its people from `/positions`. 400 if none is running. |
| GET | `/simulation/status` | require_auth | `{running, mode}`. |

The simulators feed the pipeline through `POST /telemetry` on `localhost:8000`, with the Omada token.

#### VIGI — path secret / require_admin
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/vigi/alarm/{path_secret}` | Path secret (`VIGI_ALARM_PATH_SECRET`, at least 24 characters, compared in constant time); the camera sends no auth header. Rate limit: 600/min. | The camera's Alarm Server push (§3.12). Unprefixed and called by the camera directly on the backend's port (8000 by default, §10), like `/telemetry/omada`; left out of the OpenAPI schema. A wrong or unset secret answers 404, as an unknown route does. Every other push is answered `200 {"ok": true}` with `Connection: close`; events are buffered only for a registered MAC posting from its registered IP, and an unregistered MAC only gets a heartbeat. Logged paths read `/vigi/alarm/***`. |
| POST | `/cctvs/discover` | require_admin | Manage Devices' "Scan now": one ONVIF WS-Discovery round on this machine's LAN segments (about 3 s, no credentials). Returns `scanned_at` and `found` (`mac`, `ip`, `name`, `model`, `discovered_via`, `registered`, `registered_ip`); the results also land in `/cctv_heartbeats`. |

The old `POST /vigi/detection` heartbeat writer no longer exists: camera heartbeats come from the backend's own probes and from accepted alarms (§3.12). The floor-scoped camera routes, including `GET …/cctvs/{cctv_id}/detections` (`require_auth_strict`) and `POST …/cctvs/{cctv_id}/webrtc` (`require_admin_strict`, 30/min), are listed with the floor routes above; §3.12 describes their camera-specific behaviour.

### 5.3 Models

Dataclasses in `backend/models/` (plus `BeaconIdentity` in `config/`); each is stored as its field dict.

| Model | Stored in | Key fields |
|---|---|---|
| `UserRecord` | Firestore `users/{uid}` | uid, email, display_name, role (`owner` / `admin` / `user`; one owner, never reassigned), status (`pending` / `approved` / `suspended`), person_id (links the account to a beacon's person), created_at, email_verified |
| `PositionRecord` | RTDB `/positions/{key}` | beacon_mac (the key's source: `person_id` for real devices, the fixed fake MAC for simulators), person_id, person_type (`guard` / `worker` / `forklift`), label, x, y (metres), zone, timestamp, predicted_x/y (Kalman, `COLLISION_ALERT_SECONDS` ahead), pixel_x/y, is_stationary, floor_id, building_id, is_approximate (a one- or two-AP fix whose x/y is the anchor AP), radius_m, anchor_ap_mac, heard_by (sorted MACs of the APs behind the fix) |
| `AlertRecord` | RTDB `/alerts/{alert_id}` | alert_id, alert_type (`man_down`, `possible_man_down`, `collision`, `ghost_patrol`, `patrol_violation`, `positioning_offline`), person_id, zone, timestamp, resolved, other_person_id (collision), approximate, cause (`stillness` / `signal_loss` for man-down; `missed_checkpoint` / `short_dwell` / `no_patrol` for patrol violations; none otherwise), floor_id, anchor_x, anchor_y (stillness alerts, for the restart check), acknowledged_at, acknowledged_by, acknowledged_by_uid |
| `AccessPoint` | `buildings/{b}/floors/{f}/access_points/{id}` | id, floor_id, building_id, name, mac, x_pct, y_pct (fractions of the image), x_m, y_m (derived by the backend), created_at |
| `CCTV` | `…/floors/{f}/cctvs/{id}` | id, floor_id, building_id, name, x_pct, y_pct, created_at, mac, source_type (`ipc`; `nvr` reserved), device_mac, channel, ip (alarms are accepted only from it), checkpoint_ap_id, timezone (read from the camera), facing_deg (0 to under 360, clockwise from the top of the plan), fov_deg (10–360); derived `camera_key` = `ipc:<MAC without colons>:<channel>`, e.g. `ipc:AABBCCDDEE01:1` |
| `BuildingRecord` | `buildings/{id}` | id, name, description, user_id (creator), created_at |
| `FloorRecord` | `buildings/{b}/floors/{id}` | id, building_id, name, floor_number, url, storage_path, is_active, uploaded_at, scale_pixels_per_meter, image_width_px, image_height_px, patrol_enabled, patrol_route (ordered AP ids), patrol_interval_minutes (default 10), patrol_proximity_radius_m (filled from `PATROL_PROXIMITY_RADIUS_M` when read, not per-floor data), calibration (`{a: {x_pct, y_pct}, b: {x_pct, y_pct}, distance_m, calibrated_at}` or none) |
| `ZoneRecord` | `…/floors/{f}/zones/{id}` | id, floor_id, name, color (hex with alpha), is_high_risk, risk_level (`high` / `moderate` / `low`, separate from is_high_risk), x_min, x_max, y_min, y_max (metres, axis-aligned), created_by, created_at |
| `PatrolLogRecord` | `patrol_logs/{log_id}` | log_id, guard_id, checkpoint_id, checkpoint_name, expected_arrival, actual_arrival (none when missed), dwell_time_seconds, min_dwell_required, ble_detected, vigi_detected, compliant, shift_id, cycle_id (one patrol window; empty on simulated and older logs), not_in_window (the window closed before the checkpoint was reached) |
| `AuditReportRecord` | `audit_reports/{report_id}` | report_id, shift_id, guard_id, generated_at, patrol_summary, alert_summary, rag_examples_used (feedback ids), report_text, model_used (the provider's configured model), report_type (`patrol` / `safety_event`) |
| `Beacon` | `beacons/{id}` | id (`<uuid in lower case>:<major>:<minor>`), uuid, major, minor, person_id, person_type, label, created_at, updated_at, building_id (an organisational tag, never used to resolve), tx_power (RSSI at 1 m, default −59) |
| `SafetySettings` | `settings/safety` | man_down_minutes (default 5), collision_distance_m (default 2.0), updated_at |
| `FeedbackRecord` | `feedback/{feedback_id}` | feedback_id, alert_id, alert_type, zone, feedback (`confirmed` / `fixed` / `false_alarm`), timestamp, feedback_reason, shift_id |
| `AccuracyMetricsRecord` | `accuracy_metrics/{metrics_id}` | metrics_id, run_id, shift_id, recorded_at, mean_position_error_m, rmse_m, alert_precision, alert_recall, kalman_improvement_pct, ap_count, extra |
| `CameraDetection` | backend memory, 15 minutes | camera_key, source_type, device_mac, channel, event_type (`PEOPLE`, `MOTION`, …), is_human, obj_num, regions, boxes, camera_time_raw, camera_time_utc, received_at, source_ip, payload_format (`legacy` / `enhanced`) |
| `APRssiReading`, `OmadaTelemetryPayload` | in flight only | one AP's reading (ap_mac, rssi, ap_x, ap_y); one beacon's payload for the solver (reporter_mac, timestamp, readings, person_id, person_type, label, tx_power) |
| `BeaconIdentity` (`config/beacon_registry.py`) | the ingest's cache | person_id, person_type, label, tx_power |

**Request schemas** (pydantic: `backend/schemas/`, plus a few models inside the route files):

| Schema | Validation |
|---|---|
| `TelemetryRequest`, `APRssiSchema` | `reporter_mac` and `ap_mac` as `XX:XX:XX:XX:XX:XX` (stored upper-case); rssi −120 to 0; ap_x and ap_y 0 to 10 000; at most 50 readings; person_id up to 64 characters; person_type `guard` / `worker` / `forklift` (default `worker`); timestamp ISO 8601 with a time zone, no more than 5 minutes ahead of the server (older is fine) |
| `RegisterRequest`, `GoogleAuthRequest` | `id_token`, plus display_name and an optional person_id for registration |
| `UpdateRoleRequest`, `UpdateStatusRequest` | role `admin` / `user` (`owner` can't be set); status `pending` / `approved` / `suspended` |
| `FeedbackRequest` | feedback `confirmed` / `fixed` / `false_alarm`; reason optional |
| `ReportRequest`, `SafetyReportRequest` | `{log_id, guard_id}`; `{person_id, date_str}` (`YYYY-MM-DD`) |
| `BuildingCreateRequest`, `BuildingUpdateRequest` | name, plus description on create |
| `FloorCreateRequest`, `FloorUpdateRequest`, `FloorScaleRequest`, `CalibrationRequest` | As in §5.2; the calibration's parts are optional in the schema so that `FloorService` can answer a missing part with one sentence (422) |
| `ZoneCreateRequest`, `ZoneUpdateRequest` | Rectangle bounds in metres; color default `#3b82f633`, risk_level default `moderate` |
| In `floor_routes.py` | `APCreateRequest` (MAC pattern), `APUpdateRequest`, `CCTVCreateRequest`, `CCTVUpdateRequest`, `PositionUpdateRequest` (x_pct and y_pct only: metres from a client are never accepted), `PatrolConfigRequest`, `WebRTCOfferRequest` (`sdp`, quality `sub` / `main`) |
| In `beacon_routes.py` and `safety_settings_routes.py` | `BeaconCreateRequest`, `BeaconUpdateRequest` (person_type literal, tx_power default −59); `SafetySettingsUpdate` (1–60 minutes, 0.5–10 m) |

### 5.4 Services

| Service | Responsibility |
|---|---|
| `OmadaIngestService` | The `/telemetry/omada` worker, under `pipeline_lock`. Writes the reporting AP's `/ap_heartbeats` node (placed or not); resolves the AP to its placement on an active floor (30 s cache, cleared by floor and AP changes); writes `/beacon_scans` for every iBeacon heard with an RSSI; resolves identity by `uuid:major:minor` from Firestore `beacons` (30 s cache); buffers readings per beacon for 2 s and solves at most once per `POSITION_EMIT_MIN_INTERVAL_S`. Three or more fresh APs go to `PositioningService` (with `reporter_mac = person_id`); fewer keep a recent exact fix (`POSITION_EXACT_HOLD_SECONDS`) or go to `ProximityService`; then `SafetyService.run_all_checks()`. |
| `PositioningService` | RSSI → LDPL distances → weighted least squares (`utils/multilateration.py`) → clamp to floor bounds → per-beacon `KalmanService` → predicted position `COLLISION_ALERT_SECONDS` ahead → pixels → zone → `/positions`. Caches a context per floor (scale, zones, bounds); refuses degenerate AP geometry; owns `pipeline_lock`. `invalidate_scale_cache()` also drops every Kalman filter. |
| `ProximityService` | The one- or two-AP fallback: places the beacon at its strongest AP with an LDPL radius, `is_approximate` true; writes nothing below `PROXIMITY_RSSI_FLOOR`. |
| `KalmanService` | Constant-velocity filter `[x, y, vx, vy]` on real elapsed time; rejects a jump of more than 8 m and re-initialises after 3 rejections in a row; `predict_ahead()`, `clamp_state()`, `reset()`. |
| `SafetyService` | `check_man_down` (stillness: red `man_down` from exact fixes, amber `possible_man_down` from approximate ones, upgraded after `MAN_DOWN_UPGRADE_CONFIRM_S`; one alert per episode, also across a restart), `check_man_down_stale` (signal loss, held while the person's APs are silent; one `positioning_offline` while no placed AP reports), `check_collision` (fresh worker and forklift records on the same floor whose predicted distance is under the configured distance, once per pair per 10 s), the patrol-compliance checks, `verify_multimodal`, `run_all_checks`, `get_tracker_health`. Thresholds come from `settings/safety` (30 s cache). |
| `PatrolTrackerService` | Turns exact guard positions on patrol-enabled floors into `patrol_logs` (route order, enter and exit hysteresis, time-boxed windows of `patrol_interval_minutes`) and raises patrol violations through `SafetyService`. Called from `run_all_checks()`; its failures are counted for `/health/tracker`, never raised. |
| `SafetySettingsService` | Reads and writes `settings/safety` (the `.env` defaults when it's missing); a write clears `SafetyService`'s cache. |
| `AlertService` | Lists alerts; feedback (RTDB `resolved` plus a Firestore `feedback` doc); acknowledge once; delete. |
| `BeaconService` | Beacon CRUD; clears the ingest's beacon cache; patches a new label onto an existing `/positions/{person_id}` only; deleting a beacon also deletes that position. |
| `BuildingService` | Building CRUD; a delete goes through `FloorService.delete()` for each floor. |
| `FloorService` | Floors: create (`Level N` by default), rename, scale with calibration (zones rescaled, AP metres re-derived), activate (409 when an AP would be on two active floors), deactivate, delete. APs: place (metres derived server-side; one active placement per MAC), move, delete (§9). Placement and activation check and write under one `_placement_lock`. Clears the positioning and ingest caches. |
| `ZoneService` | Zone CRUD (clears the positioning cache); AI detection on a calibrated floor through `utils/gemini_zone_detector.py`. |
| `LLMService` | `get_reportable_shifts`, `generate_report` (patrol logs, the guard's alerts and RAG context), `get_safety_event_groups`, `generate_safety_report`; the prompt restricts the formatting; saves `audit_reports`. Gets its provider from `providers/llm_factory.py` at import (§5.5). |
| `RagService` | Retrieval over Firestore `feedback` for patrol reports: an optional alert-type pre-filter (patrol reports pass none), `gemini-embedding-001` embeddings (cached, at most 500), cosine re-rank, the top 3 at or above `RAG_SIMILARITY_FLOOR`. Any failure gives empty context, never an error. |
| `UserService` | User docs on registration and Google sign-in (idempotent), the email-verified sync, role changes (owner only; the owner's role is fixed), status, delete (Firebase Auth account and doc), and clean-up of docs whose Auth account is gone. |
| `CCTVService` | Camera registry rules (MAC normalised, device MAC and channel unique, checkpoint on the same floor, IPv4, channel, facing and field of view), the time-zone read on create and on an IP change, heartbeat clean-up, go2rtc config refresh, `unlink_ap()`; a 30 s cache of all cameras. |
| `VigiService` | The `/vigi/alarm` worker: constant-time path-secret check; JSON or multipart body; a registered camera posting from its registered IP → detection buffer and `last_event_at`; an unregistered MAC → heartbeat only. Never takes `pipeline_lock`. |
| `vigi_alarm_parser` | Legacy and enhanced alarm payloads → `CameraDetection`s, with the camera's time converted using its time zone. |
| `DetectionBuffer` (`camera_detection_buffer.py`) | The last 15 minutes of detections per `camera_key`, in memory, with `process_started_at`. |
| `CameraHealthService` | TCP liveness to each camera's port 554 (`last_seen`) and the OpenAPI check (`probe`, `probe_ok_at`, `alarm_config`) into `/cctv_heartbeats`; `check_now()` after a registration or edit. |
| `VigiOpenApiClient` (`vigi_openapi_client.py`) | Read-only camera OpenAPI over HTTPS (port 20443): one shared session per camera, and a lockout guard that allows one login attempt per change to `backend/.env` after a failure. |
| `CameraDiscoveryService` | ONVIF WS-Discovery on each LAN interface (multicast, TTL 1, no credentials); records found cameras in `/cctv_heartbeats` and prunes unregistered ones unseen for 10 minutes. |
| `live_view_service` | Writes go2rtc's config from the camera registry (only on change, atomically; the password appears only as a variable reference); `open_stream()` checks the camera and the offer, then relays the SDP offer and answer to go2rtc. |
| `simulation_patrol`, `simulation_events`, `simulation_shift` | The three simulators (§3.4): asyncio loops on one active floor that write AP and simulated-camera heartbeats, post synthetic RSSI to `/telemetry` every second and write patrol logs. |
| `simulation_cleanup` | Removes simulated people's `/positions` records (when a simulator ends and at startup) in a worker thread, within 5 s, never raising. |

Helpers in `backend/utils/`: `multilateration.least_squares_position()`, `rssi_utils` (LDPL in both directions), `mac_utils` (MAC forms and RTDB keys), `gemini_zone_detector`, `zone_utils`, `timestamp_utils`, `arp_utils` (MAC lookup for discovery), `limiter`, `log_redaction` and `capture_log`.

### 5.5 LLM Provider Abstraction

```
LLM_PROVIDER (configurable, default "gemini")
      │  get_llm_provider() (providers/llm_factory.py), called once when llm_service is imported
      ├── "gemini" → GeminiProvider   google-genai SDK (genai.Client)                    — IMPLEMENTED
      ├── "openai" → OpenAIProvider   stub: generate() raises NotImplementedError
      ├── "claude" → ClaudeProvider   stub (an Anthropic call is sketched in comments)
      ├── "ollama" → OllamaProvider   stub
      └── anything else → ValueError, so the backend doesn't start
```

- **Interface:** `BaseLLMProvider` (ABC) has two abstract methods, `generate(prompt: str) -> str` and `get_model_name() -> str`; the name is saved on every report as `model_used`.
- **Gemini:** `GeminiProvider.generate()` calls `client.models.generate_content(model=LLM_MODEL_NAME, contents=prompt)` with automatic function calling disabled (no tools are passed) and no sampling parameters (the SDK's defaults), and returns `response.text`. `GEMINI_API_KEY` and `LLM_MODEL_NAME` are required: `LLM_MODEL_NAME` has no code default, and a missing one of either raises `KeyError` when settings load, so the backend doesn't start, whichever provider is selected.
- **Stubs:** the other three construct fine, then raise `NotImplementedError` on the first `generate()`, so report generation answers 500 and saves nothing. Their `get_model_name()` returns `openai-stub`, `claude-stub` and `ollama-stub`. `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` and `OLLAMA_HOST` appear in `backend/.env.example`, but `settings.py` doesn't read them.
- **Scope:** the abstraction covers report text only (§3.8). Two other model calls use the Gemini SDK directly and ignore `LLM_PROVIDER`:
  - RAG embeddings: `RagService`, with the fixed model `gemini-embedding-001` (§3.8);
  - AI zone detection: `utils/gemini_zone_detector.py` sends the floor-plan image to `LLM_MODEL_NAME` (120 s timeout; quota exhausted → 503, deadline → 504) (§3.5).

So `LLM_MODEL_NAME` has to name a Gemini model for zone detection to work, and a working Gemini key is needed whichever provider writes the reports.

### 5.6 Repositories

Repositories own the Firebase calls (`firebase_admin.db` for RTDB, `firestore.client()` for Firestore). Floors and everything on them are nested under their building; cross-building lookups are collection-group queries.

| Repository | Storage | Key methods |
|---|---|---|
| `PositionRepository` | RTDB `/positions` (and `/ap_heartbeats`) | save (key = `beacon_mac` with `:` → `_`), get, get_all, delete, get_ap_heartbeats, delete_ap_heartbeat |
| `AlertRepository` | RTDB `/alerts` | save, get, get_all, mark_resolved, acknowledge (patches only the three acknowledgement fields), delete |
| `APRepository` | Firestore `buildings/{b}/floors/{f}/access_points` | save, get_all, get_by_mac_global and get_all_placed (collection group), update_coordinates, update_position, rename, delete (returns the MAC) |
| `CCTVRepository` | Firestore `…/floors/{f}/cctvs`; RTDB `/cctv_heartbeats` | save, get_all, get_by_id, get_all_global (collection group), update_fields, update_position, delete; update_heartbeat (the single heartbeat writer outside the simulators: a partial update that skips `None` values and deletes the fields in `remove`), get_all_heartbeats, get_heartbeat, delete_cctv_heartbeat |
| `ZoneRepository` | Firestore `…/floors/{f}/zones` | save, get_all (skips malformed docs), update (returns the updated zone), delete |
| `BuildingRepository` | Firestore `buildings` | create, get_all (newest first), get_by_id, update, delete |
| `FloorRepository` | Firestore `buildings/{b}/floors` | save, get_all (by floor_number), get_by_id, get_active(building_id), get_any_active (one active floor across all buildings; used by the simulators and as the `/telemetry` path's fallback), get_all_active and get_every_floor (collection group), update_scale (the scale, the calibration and the rescaled zone bounds in one batch), set_active (this floor only), deactivate, update, delete, update_patrol_config, update_patrol_route |
| `PatrolLogRepository` | Firestore `patrol_logs` | save, get, get_by_shift, get_by_guard, get_by_shift_and_guard, get_reportable_shifts |
| `AuditReportRepository` | Firestore `audit_reports` | save, get, get_all, get_by_shift; only save has a caller |
| `UserRepository` | Firestore `users` | create (the first user becomes owner and approved), get_by_uid, get_all, get_pending, update_role, update_status, update_person_id, update_email_verified, delete, ensure_owner_exists |
| `BeaconRepository` | Firestore `beacons` | get_all, get_by_id, exists, save, update_fields, delete, seed_from_legacy |
| `SafetySettingsRepository` | Firestore `settings/safety` (one doc) | get, exists, save, seed_defaults |
| `FeedbackRepository` | Firestore `feedback` | save (by `AlertService`), get_resolved_with_feedback and get_by_alert_type (by `RagService`), get_by_zone |
| `AccuracyMetricsRepository` | Firestore `accuracy_metrics` | save, get, get_by_run, get_by_shift; nothing calls it yet |

A few Firebase calls sit outside the repositories: the heartbeat writes in `/telemetry` and `OmadaIngestService`, `OmadaIngestService`'s `/beacon_scans`, `BeaconService`'s label patch, `LLMService`'s `/alerts` reads, the simulators and `simulation_cleanup` (`/positions`, heartbeats), and the Storage delete in `FloorService.delete()`.

---

## 6. Frontend Detail

### 6.1 Pages

| Route | Access | Purpose |
|---|---|---|
| `/` | Public | Redirects to `/dashboard` |
| `/login` | Public | Email/password or Google sign-in. A signed-in visitor goes on by status (pending → `/pending-approval`, suspended → `/suspended`, otherwise `/dashboard`); a failed account check is explained in plain words (§3.10) |
| `/register` | Public | Name, email and password with a strength meter (Create Account needs "strong" or better and a matching confirmation), or Google. The first account, the owner, goes to `/login`; any other to `/pending-approval` |
| `/pending-approval` | Signed-in accounts awaiting verification or approval | Email not verified: checks every 3 s, with Resend (60 s cooldown). Verified: tells the backend, then waits for an admin. Sign out |
| `/suspended` | Suspended accounts | Suspension notice and sign out |
| `/dashboard` | Approved | Stats row, live floor map, device status and active alerts (§3.9) |
| `/dashboard/alerts` | Approved | Search, Active/Resolved tabs, type filters and feedback; Remove on resolved alerts (admin) (§3.9) |
| `/dashboard/reports` | Approved; generating is admin-only | AI audit reports in two tabs, Patrol Reports and Safety Events: a shift or person-and-date selector with Generate, the report list, and the report in `SimpleMarkdown` with Copy (§3.8) |
| `/dashboard/patrol-reports` | Approved | One guard's patrol cycle on one floor: the checkpoint sequence on the floor plan (route arrows, arrival times, dwell-sized markers) and a checkpoint table (Compliant, Short dwell, Missed, No record, Not in window); Print / Save as PDF (§3.3) |
| `/dashboard/floor-plans` | Approved; editing is admin-only | Buildings and their floors. Admins create, rename and delete buildings; Add Floor takes PNG, JPEG or WebP up to 10 MB, or a PDF whose pages each become a floor; each floor's menu has Set as Active / Deactivate, Rename, Calibrate, Manage Zones, Manage Devices, Manage Patrol and Delete (§3.5/§3.13; cameras §3.12) |
| `/dashboard/beacons` | Admins (Sidebar link) | Beacon registry and Unknown Beacons (§3.11) |
| `/dashboard/users` | Admins (Sidebar link) | Approve, promote or demote (owner only), remove (§3.10) |
| `/dashboard/safety-settings` | Admins | Man-down timer and collision distance (§3.9); anyone else is redirected to `/dashboard` |

**How access is enforced**
- `app/dashboard/layout.tsx` wraps every `/dashboard/*` page: a signed-out visitor goes to `/login`, a pending account to `/pending-approval` and a suspended one to `/suspended`, and a failed account read shows an error screen (Retry, Sign out) instead of the dashboard. Only the first load shows the full-screen AUTHENTICATING loader. `AuthProvider` also sends an unverified email address from any other page to `/pending-approval`.
- Roles in the UI: the Sidebar shows Beacons and Users to admins only, and the Navbar shows the Safety Settings gear to admins only. The Users list comes from Firestore, whose rules let only an admin or the owner list `users`, and the beacon list from `GET /beacons` (`require_auth`). Floor Plans shows its edit controls to admins only, and on Reports the shift and person lists come from admin-only routes, so the selectors stay empty for anyone else.
- The backend checks every change again: `require_admin`, or `require_owner` for role changes (§5.2).

**Root layout** (`app/layout.tsx`): IBM Plex Sans and Mono; an inline script that applies the saved theme before React loads, so the page never flashes the wrong theme; a load watchdog that reloads the page once if React hasn't started or the AUTHENTICATING loader is still up 20 s after the page arrived (not again within 2 minutes, and never on Next's error page); and `ThemeProvider` and `AuthProvider` around every page.

### 6.2 Key Components

**Layout** (`components/layout/`)
- `Navbar` — fixed top bar: logo, page title (from a path map), theme toggle, the Safety Settings gear (admins) and sign-out.
- `Sidebar` — collapsible (240 or 60 px). Nav filtered by role: Dashboard, Alerts, Reports, Floor Plans, Patrol Reports, then Beacons and Users for admins. Badges: unresolved alerts on Alerts, pending accounts with a verified email on Users (admins), unknown beacons heard in the last 10 s on Beacons. When expanded, the Personnel list (§3.9).
- `ThemeProvider` — sets `dark` or `light` on `<html>` from `themeStore`, with a brief transition.

**Dashboard** (`components/dashboard/`)
- `StatsRow` — Active Personnel, Active Alerts, Collision and Man Down (§3.9).
- `FloorMapArea` — Building and Floor selectors (`SelectDropdown`), the default building (`useFirstBuildingWithActiveFloor`), the shown floor's positions for `FloorMap`, then `DeviceStatusPanel`; empty states for no buildings and no active floor.
- `DeviceStatusPanel` — the shown floor's APs and cameras (Firestore listeners), each with a dot (glowing when online) and a badge by `apStatus`/`cctvStatus`; hidden when the floor has no devices.
- `SafetySettings` — the Safety Settings form (§3.9).
- `SimulationControls` — Patrol, Events and Shift Change start buttons, Stop, and a status badge polled every 5 s; no page mounts it (§3.9).

**Map** (`components/map/`)
- `FloorMap` — the live map (§3.9): floor-plan image, zones with the ZONES toggle, status-coloured AP and camera markers, camera cones, the patrol-route line, worker markers with JS hit detection and a tooltip for every beacon under the cursor, the calibration warning, and `CameraPanel` on a camera click.
- `WorkerMarker` — SVG dot and halo in the person-type colour, plus a dashed uncertainty circle for an approximate fix; it has no hover handlers of its own.
- `PatrolRouteOverlay` — with `lineOnly` (dashboard), a faint line through the route's APs; with `showDetails` (Patrol Reports), checkpoint states, direction arrows, arrival times and dwell-sized markers (§3.3).
- `ApIcon`, `CctvIcon`/`CctvMarker` — the shared AP and camera glyphs; `apStatusColor`/`cctvStatusColor` give green online, red offline, grey unknown.
- Camera (§3.12): `CameraCone` (which way a camera faces), `CameraPanel` (status, health, alarm set-up and recent events) and `CameraLiveView` (admin-only WebRTC live video).
- Floor Plans editors (§3.5/§3.13): `CalibrationTool` (scale from two points and a distance; Recalibrate opens on the last calibration), `ZoneEditor` (zones drawn point by point and saved as their bounding box, colour and risk, AI detection, whose suggestions can be moved and resized), `APCCTVEditor` (Manage Devices: place, drag, rename and remove APs and cameras, the "online but not placed" list, each camera's IP, checkpoint and facing), `WallGuides` (the room's outline and X/Y distance guides for placing a device, kept per floor in the browser), `PolygonDraft` (the click-per-corner drawing shared by zones and walls) and `PatrolConfigPanel` (patrol on/off, drag-to-reorder route, cycle interval).
- `BeaconManager` — the beacon registry (§3.11): a table with Online/Offline (a `/beacon_scans` record under 10 s old), a Register/Edit modal (UUID, major and minor fixed once created; person ID, type, label, and Tx power defaulting to −59 dBm), Delete, and a collapsible Unknown Beacons panel whose Register pre-fills the form.
- `ZoneOverlay` — an old demo overlay with hard-coded zones; not used.

**Alerts** (`components/alerts/`)
- `AlertList` — type filters (All, Man Down, Possible Man Down, Positioning Offline, Ghost Patrol, Collision, Patrol Breach) over a list of `AlertCard`s.
- `AlertCard` — type badge (plus "signal lost" on a signal-loss man-down), ACTIVE or RESOLVED, person ("All APs" for `positioning_offline`), `↔ other_person_id` on a collision, zone, timestamp and any acknowledgement (who and when), with a pulsing edge while unresolved (red for man-down and collision, amber for the two amber types), and Remove on resolved alerts on the Alerts page.
- `FeedbackForm` — Confirmed Incident, Resolved On-site or False Alarm, with optional notes, sent to `POST /alerts/{id}/feedback`.

**Reports** (`components/reports/`)
- `ReportCard` — a list entry: shift ID, generation time, model and an 80-character preview.
- `GenerateReportButton` — a link button to Reports; not used.
- The reports page itself holds `SimpleMarkdown` (`#` to `#####` headings, `---`, bullets, numbered lines, bold, italic and code) and its `CustomSelect` dropdown.

**Shared** (`components/shared/`)
- `CriticalAlertBanner` — the critical pop-ups (§3.9).
- `ToastContainer` — bottom-right toasts (success, error, info), at most 3, each dismissed after 4 s (paused on hover). Only the dashboard layout mounts it, so the toasts `/pending-approval` raises for Resend aren't shown.
- `AlertTypeBadge` — a coloured pill per type: red for man-down and collision, amber for possible man-down and positioning offline, the accent colour for ghost patrol, orange for patrol breach.
- `SelectDropdown` — a generic labelled dropdown (`getId`/`getLabel`, optional scrolling menu), used by `FloorMapArea` and Patrol Reports.
- `MacAddressInput` — six two-hex-digit boxes with auto-advance and a 12-digit paste; used in Manage Devices.
- `LoadingSpinner`; `FullScreenLoader`, the AUTHENTICATING screen, which the load watchdog looks for and which shows "This is taking longer than it should" after 25 s; `FullScreenError`, which says why the account check failed, with Retry and Sign out.
- `SkeletonCard`/`SkeletonRow` and `StatusBadge` — not used.

### 6.3 Stores (Zustand)

| Store | State |
|---|---|
| `dashboardStore` | `positions` and `alerts` (keyed as in RTDB, filled by the dashboard layout's subscriptions); `cachedReports`, `cachedUsers` and `cachedBuildings`, so a page opens on its last list while its listener reconnects; `showZones`/`toggleShowZones`, the map's ZONES toggle, kept here because every route change remounts the page (`<main key={pathname}>`). `selectedWorkerId`, `activeShiftId` and their setters are declared, but nothing reads them. |
| `criticalAlertStore` | This tab's part of the pop-ups only: `hiddenIds` (closed here, by a non-admin's ✕ or an admin's acknowledge that went through) and `pendingIds` (acknowledges in flight, so ✕ isn't sent twice), with `hide()` and `setPending()`. Which alerts pop up is worked out from the live `/alerts` data by `useCriticalQueue` (§6.4); a reload clears the store. |
| `toastStore` | `toasts` (`{id, message, type}`, at most 3, the oldest dropped), `addToast` and `removeToast`, and the helpers `toast.success()`, `toast.error()` and `toast.info()`. `ToastContainer` does the 4 s auto-dismiss. |
| `themeStore` | `theme: "dark" \| "light"` (dark by default) and `toggleTheme()`, persisted in `localStorage` under `skye-theme`, which the root layout's pre-hydration script also reads. |

### 6.4 Hooks

| Hook | Description |
|---|---|
| `useAuth` / `AuthProvider` | A React context mounted in the root layout. One app-wide Firebase auth listener; for a user with a verified email it reads `users/{uid}` with a 15 s deadline, and only the newest check may publish. Exposes `user`, `userRecord`, `isLoading`, `recordError` (why the account read failed, in plain words) and `recheck()`. It sends an unverified user to `/pending-approval` from any page but `/login`, `/register`, `/pending-approval` and `/suspended`; the status redirects are in `dashboard/layout.tsx` (§3.10). |
| `usePositions` | RTDB `/positions` into `dashboardStore.positions`; mounted once, by the dashboard layout. |
| `useAlerts` | RTDB `/alerts` into `dashboardStore.alerts`, also mounted by the layout. The same file exports `CRITICAL_TYPES` and `useCriticalQueue()`, the pop-up queue worked out from the live alerts (a critical type, unresolved, not acknowledged and not hidden in this tab; oldest first). |
| `useAPHeartbeats` | RTDB `/ap_heartbeats`, recomputed every second: `{mac, name, ip, status}` per upper-case MAC (online while the heartbeat is under 10 s old), plus `loaded`. `apStatus()` is the one rule for every AP icon and dot: grey until the first snapshot, then online or offline, with a missing heartbeat counting as offline. Malformed nodes are skipped. |
| `useCCTVHeartbeats` | RTDB `/cctv_heartbeats`, recomputed every second: status from `last_seen` (10 s), plus the last alarm, the OpenAPI probe result, the alarm-config check and the discovery fields that the camera panel shows. `cctvStatus()` mirrors `apStatus()`, and is grey for a camera without a MAC. |
| `useBeaconScans` | RTDB `/beacon_scans`, keyed `uuid_major_minor`, with a 1 s re-render so a beacon that goes quiet flips without a new event. The consumers apply the 10 s online rule (`BeaconManager`, the Sidebar's unknown-beacon badge). |
| `useBuildings` | A Firestore `buildings` listener (newest first) once signed in; it starts from and refreshes `dashboardStore.cachedBuildings`. |
| `useFloors` | A Firestore `buildings/{id}/floors` listener in `floor_number` order, giving `floors`, `activeFloors` and `activeFloor` (the first active one). `useFirstBuildingWithActiveFloor(ids)` listens to each building's floors (the rules allow no collection-group query from the browser) and returns the first building with an active floor. |
| `useZones` | One `GET /buildings/{b}/floors/{f}/zones` per floor change, not live, giving `zones`, `setZones` and `isLoading`; used by `FloorMap` and `ZoneEditor`. |

**Services and utilities.** Live data is read straight from Firebase; everything else goes to the backend through `/api/*`, which `next.config.js` rewrites to `BACKEND_URL` (default `http://localhost:8000`). Every backend call carries the user's Firebase ID token as a Bearer header (`utils/apiClient.ts`'s `authFetch`, a service's own `req()`, or a plain `fetch` with the header set by hand), except `/auth/register` and `/auth/google`, which send it as `id_token` in the JSON body.

| Service | Reads from Firebase | Calls on the backend |
|---|---|---|
| `authService` | Firebase Auth | `/auth/verify-email`, `/auth/google` |
| `userService` | `users/{uid}` (own record), the pending-count query | `/auth/register`, `/users/*` |
| `alertService` | RTDB `/alerts` | `/alerts/{id}` delete, feedback and acknowledge |
| `positionService` | RTDB `/positions` | — |
| `buildingService` | `buildings` | create, rename, delete |
| `floorService` | floors, `access_points`, `cctvs`, `patrol_logs` (bounded: the newest N, or one guard's); floor images to Storage | floors, APs, cameras, discovery, detections, live view |
| `zoneService` | — | zone CRUD, `ai-detect` (90 s timeout) |
| `beaconService` | — | `/beacons` CRUD |
| `reportService` | `audit_reports` (newest first) | `/reports/*` lists and generation |
| `safetySettingsService` | — | `GET`/`PUT /settings/safety` |
| `simulationService` | — | `/simulation/start`, `stop`, `status` (only `SimulationControls` uses it) |
| `patrolLogService` | `patrol_logs`, unbounded | — (no callers) |

Utilities: `authCheck` (the account-read deadline and its messages), `passwordUtils` (the register page's strength levels), `macUtils` (MAC checks), `pdfRasterise` (a PDF's pages to images, with `pdfjs-dist`), and `cameraFacing`, `wallGuides` and `patrolLogOrder` for the camera, Floor Plans and patrol views.

---

## 7. Data Flow: BLE → Backend → Frontend

```
[A guard, worker or forklift carries an iBeacon tag (or a phone advertising one)]
        ↓  BLE advertisements
[TP-Link Omada APs: each posts its own scan report, about once a second, unsynchronised]
        │
        ├── REAL AP PATH ──────────────────────────────────────────────────────────
        │   POST /telemetry/omada              rate limit 600/min; runs in a worker thread
        │     1. verify_omada_source          OMADA_INGEST_ALLOWED_IPS allow-list     (else 403)
        │     2. verify_omada_body_token      meta.access_token = OMADA_ACCESS_TOKEN  (else 401)
        │   { reporter: {mac, name, ipv4, …},
        │     reported: [{rssi: {avg}, ibeacon: {uuid, major, minor}, …}],
        │     meta: {access_token} }
        │       ↓
        │   OmadaIngestService.ingest()        [§3.7; holds pipeline_lock for the whole report]
        │     a. RTDB /ap_heartbeats/{AA_BB_…} ← {mac, name, last_seen, up_since, ip}
        │        for every reporting AP, placed or not
        │     b. resolve the AP to its placement on an active floor (cached)
        │        none → {"status": "online_unregistered"}; stop
        │     c. each entry with an iBeacon block: key uuid:major:minor → identity
        │        (Firestore beacons, cached)
        │        RTDB /beacon_scans/{uuid_major_minor} ← last-seen record, registered or not
        │        registered and with an RSSI → buffer[key][AP] ← (rssi, AP x_m/y_m, floor)
        │     d. flush: readings under 2 s old; one decision per beacon per
        │        POSITION_EMIT_MIN_INTERVAL_S; floor = where its fresh readings came from
        │          ≥ 3 APs → OmadaTelemetryPayload(reporter_mac = person_id, label, tx_power)
        │                    → PositioningService.compute_position(floor)  (below)
        │          1–2 APs → hold (an exact solve within POSITION_EXACT_HOLD_SECONDS),
        │                    else ProximityService.compute_position()
        │                    → RTDB /positions/<person_id> (is_approximate = true)
        │          either result → SafetyService.run_all_checks()
        │
        └── SIMULATION PATH ───────────────────────────────────────────────────────
            simulators: started by an admin (POST /simulation/start, a task inside the
            backend) or run as scripts; one tick per second; RSSI from distance by
            inverse LDPL (TX_POWER_DEFAULT) plus Gaussian noise (RSSI_NOISE_STD);
            readings below −95 dBm dropped
            POST /telemetry                    rate limit 200/min; worker thread; same lock
              1. require_loopback             loopback callers only                 (else 403)
              2. verify_omada_token           Authorization: Bearer <OMADA_ACCESS_TOKEN> (else 401)
            TelemetryRequest {
              reporter_mac: the simulated tag's fixed MAC (XX:XX:XX:XX:XX:XX only),
              timestamp: ISO 8601 with a time zone, at most 5 min ahead,
              readings (≤ 50): [{ap_mac, rssi, ap_x, ap_y}], person_id, person_type }
              (no label or TxPower fields: label stays empty, TxPower is −59 dBm)
              → RTDB /ap_heartbeats/{AA_BB_…} ← {mac, last_seen} for every AP in readings
              → PositioningService.compute_position()     no floor given → get_any_active()
              → SafetyService.run_all_checks()
        ↓
PositioningService.compute_position()          [§3.1; three or more readings]
  1. refuse degenerate AP geometry (every AP at one point)
  2. RSSI → LDPL distance per AP
  3. least_squares_position(): weighted, bounded to the floor (scipy "trf")
  4. KalmanService: reset after 10 s without an accepted fix; update behind an 8 m gate
  5. clamp to the floor; predict_ahead(COLLISION_ALERT_SECONDS) → predicted_x/y
  6. pixel_x/y = metres × scale_pixels_per_meter; zone = first zone rectangle containing it
  7. RTDB /positions/{reporter_mac, ':' → '_'} ← PositionRecord (heard_by, is_approximate = false)
        ↓
SafetyService.run_all_checks(position)          [§3.2, §3.3]
  ├─ check_man_down(): exact fixes still within MAN_DOWN_MOVEMENT_EPSILON_M for
  │    man_down_minutes (Firestore settings/safety) → red man_down, where only
  │    MAN_DOWN_MOVE_CONFIRM_FIXES fixes in a row past it count as a move; approximate runs →
  │    amber possible_man_down, which later exact fixes can upgrade; one alert per
  │    stillness episode, and a restarted backend checks /alerts before raising one again
  ├─ patrol_tracker_service.check_patrol_progress(): exact guard positions on a floor
  │    with patrol enabled → Firestore patrol_logs (each visit's compliant flag via
  │    is_patrol_violation()); patrol_violation at each window's close
  │    (check_patrol_window_compliance(), check_patrol_window_no_patrol())
  └─ check_collision(every /positions record): a worker and a forklift, both younger
       than COLLISION_MAX_AGE_S and on the same floor, whose predicted points are closer
       than collision_distance_m (Firestore settings/safety) → collision
       (at most one per pair per 10 s)
  every alert → RTDB /alerts/{alert_id}

[Background, every 60 s: main.py lifespan → SafetyService.check_man_down_stale()]
  a non-forklift record, not on an inactive floor, unrefreshed for MAN_DOWN_STALE_SECONDS
  (records older than MAN_DOWN_STALE_MAX_AGE_S are ignored) → man_down, cause
  signal_loss; held while none of the APs that heard it is alive; when no placed AP is
  reporting at all → one positioning_offline instead.
  At startup, leftover simulated /positions records are removed first; at shutdown or a
  reload, a running simulation is cancelled so that it removes its own.
        ↓
[Firebase RTDB pushes each change to the open dashboards. The dashboards only read,
 and no client may write (database.rules.json): every write above is the backend's.]
        ↓
DashboardLayout → DataSubscriptions (mounted once for every /dashboard page)
  usePositions() → positionService: onValue("/positions") → dashboardStore.positions
     ├─ FloorMapArea: one active floor of the selected building (a Floor selector when
     │    several are active) → only records with that floor_id → FloorMap
     │    FloorMap: drops markers more than 12 s older than the freshest one; places
     │    pixel_x/y, else x/y × scale; WorkerMarker: a dot coloured by person_type, plus
     │    a dashed radius_m circle when approximate; hover lists every marker under the cursor
     ├─ Sidebar personnel list: every record on every floor (grey when over 60 s old)
     └─ StatsRow "Active Personnel": the number of records
  useAlerts() → alertService: onValue("/alerts") → dashboardStore.alerts
     ├─ AlertList, AlertCard, StatsRow
     └─ useCriticalQueue(): man_down, possible_man_down, collision and positioning_offline
          alerts that are unresolved, unacknowledged and not hidden in this tab
          → CriticalAlertBanner; an admin's ✕ → POST /alerts/{id}/acknowledge (closes it
          for everyone); anyone else's ✕ hides it in that tab
  useAPHeartbeats / useCCTVHeartbeats / useBeaconScans: online while under 10 s old

[Operator gives feedback]  POST /alerts/{id}/feedback { feedback, reason }
  ├─ RTDB /alerts/{id}: resolved = true
  └─ Firestore feedback ← FeedbackRecord (the corpus for report context)

[Admin generates a patrol report]  POST /reports/generate { log_id (a shift_id), guard_id }
  ├─ Firestore patrol_logs for that shift and guard (the tracker's logs carry a cycle_id
  │    and an empty shift_id, so GET /reports/shifts lists simulated shifts only)
  ├─ RTDB /alerts for that guard, of any date
  ├─ RagService.get_context_with_sources(): the top 3 feedback records by embedding
  │    similarity, kept at or above RAG_SIMILARITY_FLOOR; empty on any failure
  ├─ LLMService._build_prompt() → provider.generate()   (Gemini; §5.5)
  └─ Firestore audit_reports ← AuditReportRecord (report_type "patrol", rag_examples_used)

[Admin generates a safety event report]  POST /reports/generate-safety { person_id, date_str }
  ├─ RTDB /alerts for that person on that date (404 when there are none)
  ├─ LLMService._build_safety_prompt() → provider.generate()
  └─ Firestore audit_reports ← AuditReportRecord (report_type "safety_event")
```

- **Keys**: a real person's record is `/positions/<person_id>`; a simulated one is `/positions/AA_BB_CC_DD_EE_0N`, the tag's validated MAC with `:` → `_` (§9).
- **Shared pipeline**: simulated and real people never share a `/positions` key, but they share the lock, the safety checks and the AP heartbeats. A simulation's readings name the active floor's real APs, so while it runs it rewrites their heartbeats and they read as online. The collision check pairs any fresh worker and forklift on the same floor, simulated or real.
- **Persistence**: in the backend, a real person's `/positions` record is removed only when their beacon is deleted (§3.11). The map hides stale records and the Sidebar greys them. Simulated records go when their simulation stops, and again at every backend start.

---

## 8. Firebase Usage

The backend reaches Firebase through the Admin SDK app set up in `create_app()` (§5.1), mostly via the repositories (§5.6); the exception is AI zone detection, which downloads the plan image from its Storage download URL (`utils/gemini_zone_detector.py`). The dashboard uses the web SDK (`frontend/config/firebase.ts`) for sign-in, for live reads and to upload floor plans; every database write goes through the backend's API.

### Realtime Database — live, ephemeral

| Path | Key | Contents | Written by | Read by |
|---|---|---|---|---|
| `/positions/{key}` | Real devices: the bare `person_id` (e.g. `guard-001`). Simulators: the simulated beacon's fixed MAC with underscores (e.g. `AA_BB_CC_DD_EE_01`) | `PositionRecord`, one per person, replaced on every solve: at most once per `POSITION_EMIT_MIN_INTERVAL_S` (default 1.8 s) per beacon from the APs, every 1 s tick from a simulator | `PositionRepository.save()` from `PositioningService` and `ProximityService`; `BeaconService` (label patch, delete on beacon delete); the simulators and `simulation_cleanup` (remove simulated keys) | Dashboard (`usePositions`); `SafetyService` (collision check, signal-loss sweep) |
| `/alerts/{alert_id}` | UUID | `AlertRecord` | `AlertRepository`: `save()` from `SafetyService` (patrol violations included), `mark_resolved()` on feedback, `acknowledge()`, `delete()` | Dashboard (`useAlerts`); `LLMService` (reports); `SafetyService` (restart and outage checks) |
| `/ap_heartbeats/{AA_BB_CC_DD_EE_FF}` | AP MAC with underscores | From `/telemetry/omada`: `{mac, name, last_seen, up_since, ip?}`, where ip is the AP's reported IPv4. From `/telemetry` and the simulators: `{mac, last_seen}` | `OmadaIngestService` on every AP report, placed or not (this feeds the device editor's *online but not placed* list); `/telemetry` for each AP in a payload; each simulator tick for the active floor's APs. Deleted when the last placement of that MAC is removed | Dashboard (`useAPHeartbeats`: online while `last_seen` is under 10 s old); the signal-loss sweep (`AP_SILENT_AFTER_S`, `AP_ALIVE_GRACE_S`) |
| `/cctv_heartbeats/{AA_BB_CC_DD_EE_FF}` | Camera MAC, normalised, with underscores | `mac`, `last_seen` (RTSP port answered), `last_event_at` (accepted alarm), `device_name`, `probe`, `probe_ok_at`, `alarm_config`, `discovered_at`, `discovered_via`, `ip`, `ip_mismatch` | `CCTVRepository.update_heartbeat()`, partial updates shared by liveness, alarm ingest, the OpenAPI check and discovery; the simulators set a simulated camera's node. Deleted with the camera (unless another camera reports through the same device), and by discovery for unregistered cameras unseen for 10 min | Dashboard (`useCCTVHeartbeats`, 10 s); live view (opens only for a camera seen in the last 10 s) |
| `/beacon_scans/{uuid_major_minor}` | The iBeacon triple with underscores | `{uuid, major, minor, rssi, ap_mac, last_seen, registered}` | `OmadaIngestService`, for every iBeacon heard with an RSSI, registered or not, by an AP placed on an active floor. Unregistered nodes unheard for 300 s are pruned, at most once a minute | Dashboard (`useBeaconScans`: beacon status, unknown beacons) |

**Keys.** By convention, MAC-shaped keys use underscores while the records keep colon MACs; code that compares MACs normalises them first (`utils/mac_utils.py`: `mac_heartbeat_key()`, `ap_mac_colons()`). Real and simulated `/positions` keys can't collide (bare person ids versus MAC-shaped keys), and a real phone's record doesn't move when its BLE MAC rotates, because the ingest keys it by `person_id` (§9).

**Rules** (`database.rules.json`): no client can write any of the five nodes; only the backend's Admin SDK writes.

### Firestore — persistent, queryable

| Collection or document | Model | Written by (backend) | Dashboard reads it |
|---|---|---|---|
| `users/{uid}` | `UserRecord` | `UserRepository` (registration, Google sign-in, email sync, role, status, delete, owner backfill) | Its own doc at sign-in; the Users page and the pending badge list it |
| `buildings/{b}` | `BuildingRecord` | `BuildingRepository` | Live (`subscribeToBuildings`) |
| `buildings/{b}/floors/{f}` | `FloorRecord` | `FloorRepository` | Live (`subscribeToFloors`) |
| `…/floors/{f}/access_points/{ap}` | `AccessPoint` | `APRepository` | Live (`subscribeToAPs`) |
| `…/floors/{f}/cctvs/{c}` | `CCTV` | `CCTVRepository`, `CCTVService` | Live (`subscribeToCCTVs`) |
| `…/floors/{f}/zones/{z}` | `ZoneRecord` | `ZoneRepository`; `FloorRepository.update_scale()` rescales the bounds in the same batch as the scale | Through `GET …/zones` |
| `beacons/{uuid:major:minor}` | `Beacon` | `BeaconRepository` | Through `GET /beacons` |
| `patrol_logs/{log_id}` | `PatrolLogRecord` | `PatrolTrackerService` and the simulators | Live: the latest N by `expected_arrival`, and one guard's history |
| `audit_reports/{report_id}` | `AuditReportRecord` | `LLMService` | Live, newest first (Reports page) |
| `feedback/{feedback_id}` | `FeedbackRecord` | `AlertService.submit_feedback()` | No (read by `RagService`) |
| `accuracy_metrics/{metrics_id}` | `AccuracyMetricsRecord` | Nothing yet | No |
| `settings/safety` | `SafetySettings` | Seeded at startup; `PUT /settings/safety` | Through `GET /settings/safety` |

Floors and everything placed on them are nested under their building; there is no top-level `floors` or `aps` collection. Cross-building lookups (active floors, an AP by MAC, all cameras) are collection-group queries.

**Rules** (`firestore.rules`): `users/{uid}` can be fetched by its own user and listed by an admin or the owner; client writes are denied everywhere.

**Indexes** (`firestore.indexes.json`, deployed through `firebase.json`): a composite index on `patrol_logs` (`guard_id` ascending, `expected_arrival` descending) for the per-guard query, and collection-group indexes on `floors.is_active` and `access_points.mac`.

### Storage

| Path | Content |
|---|---|
| `buildings/{buildingId}/floors/{timestamp}_{filename}` | Floor-plan images, at most 10 MB. The browser uploads them (`floorService.uploadFloor()`; a PDF is first rasterised to one PNG per page, each becoming its own floor), then calls `POST /buildings/{id}/floors` with the download URL and the path. Deleting a floor removes the object: the dashboard deletes it first, and `FloorService.delete()` again through the Admin SDK. |

**Rules** (`storage.rules`): writes need an approved admin or owner.

### Not in Firebase

- Camera detections: backend memory, the last 15 minutes (`DetectionBuffer`); a restart empties them.
- The placement-guide walls: the browser's `localStorage`, per floor (`skye-wall-guides:<floorId>`).
- Capture logs and the camera OpenAPI lockout markers: `backend/logs/` (gitignored).
- go2rtc's generated config: `GO2RTC_CONFIG_PATH` (gitignored).

---

## 9. Key Design Decisions

### Dual Database Strategy
RTDB for **live, ephemeral** state (positions, alerts, heartbeats, beacon scans), streamed with `onValue`; Firestore for **persistent, queryable** data (config, beacons, patrol logs, reports, settings, and the alert feedback RAG reads, §3.8). Camera detections (backend memory) and the placement-guide walls (browser `localStorage`) stay out of Firebase (§8).

### RTDB Key Format — Underscores Only
By convention, MAC-shaped keys (`/ap_heartbeats`, `/cctv_heartbeats`, simulated `/positions`) use underscores, as in `AA_BB_CC_DD_EE_01`; `/beacon_scans` uses `uuid_major_minor`, and real `/positions` the bare `person_id`. Records keep colon MACs, and code normalises before comparing (`utils/mac_utils.py`, §8): a key in the wrong format is silently never matched.

### Kalman Filter with Direction-Aware Collision Detection
`predict_ahead(COLLISION_ALERT_SECONDS)` (default 3 s) projects each filter's state along its velocity, and the check compares a worker's and a forklift's projected points at that instant (not the closest approach), so a pair moving apart doesn't alert. Only exact, fresh (`COLLISION_MAX_AGE_S`, 5 s) records on the same floor take part, and the time-aware filter can't lock onto an old position (§3.1, §3.2).

### Collision Alert Deduplication
`_last_collision` keys on `"worker_id|forklift_id"`; a pair alerts again only after **10 s** (30 s is man-down's separate `_last_man_down`). It's a gap, not an episode latch: a pair that stays close alerts every 10 s (§3.2).

### One Stillness Alert per Episode, and the AP-Change Hold
- **Latch:** one stillness alert per episode (there had been one every 30 s), re-armed only when the person moves. After a restart, the backend checks `/alerts` once and doesn't repeat an unresolved alert for the same person and spot from the last 12 h (`MAN_DOWN_RESTART_MATCH_H`); a failed read raises the alert.
- **A move takes three fixes in a row:** a beacon lying still still gets the odd single exact fix 2 m or more from its anchor, and the next fix comes back. When one such fix counted as a move, it restarted the clock, re-armed the latch and marked the person as moving, which also skipped the restart check. In a replay of a night when two beacons lay still for over an hour, their clocks restarted 32 and 177 times, the longest stillness was under 18 minutes, and a 60-minute timer never fired. So a move now needs `MAN_DOWN_MOVE_CONFIRM_FIXES` (3) exact fixes in a row, each ε or more away; on the same night both 60-minute alerts come. Exact fixes arrive about every 2 s, so a real move counts about 6 s later. Approximate readings don't count towards it (§3.2).
- **AP-change hold:** with one or two APs the strongest AP flips while a beacon sits still, so a change counts only after `MAN_DOWN_AP_CHANGE_HOLD_S` (120 s) without a reading back at the run's AP. In a replay, a beacon on a desk "moved" up to hourly at 30 s, and never at 120 s (§3.2, §9b).

### Critical Alert Banner vs. Toast
Emergencies get a persistent, stacked `CriticalAlertBanner` that never auto-dismisses: `man_down` and `collision` in red, `possible_man_down` and `positioning_offline` in amber. Its queue is worked out from live `/alerts` (unresolved, unacknowledged, oldest first), so pop-ups survive reloads and sign-ins. Routine feedback stays in toasts (bottom right, at most three, 4 s) (§3.9).

### Acknowledged for Everyone, Resolved Only by Feedback
An admin's or the owner's ✕ (or Dismiss all) acknowledges the alert, closing its pop-up on every dashboard; anyone else's ✕ hides it in that tab. Acknowledging doesn't resolve: only feedback does (§3.2).

### Per-Guard Shift Tracking
The `patrol` and `shift` simulators give each guard its own `shift_id`, `loops_completed` and `checkpoints_this_loop` (from 0), so a rotation needs every checkpoint; no shift state is global. `simulation_events.py` keeps one `shift_id` per run (§4.5). Real patrols have cycles, not shifts (`cycle_id`, empty `shift_id`), so AI patrol reports list simulator shifts only (§3.3, §3.8).

### Patrol Route on Active Floor Only (now per floor — see §3.3/§3.4)
The tracker takes the route and window from each position's own floor and keeps state per guard and floor, so every active floor with patrol enabled is tracked. The simulators still run on the one floor `get_any_active()` returns, from any building.

### Several Active Floors, Each AP on One
Any number of floors can be active, but an AP's MAC on only one of them: an activation or placement that would break this is refused. So each AP report resolves to one floor, a beacon takes its readings' floor, and positioning keeps a context per floor; an inactive floor may hold the AP as a backup map (§3.5, §3.7).

### Two Report Types — Unified Renderer
`report_type` is `"patrol"` or `"safety_event"`, and a document without it counts as patrol. Both share the `SimpleMarkdown` renderer and one detail panel. The per-cycle Patrol Reports page is separate, not an AI report (§3.3, §3.8).

### Multi-Modal Ghost Patrol Detection (design intent — not yet reachable in production, see §9b)
`verify_multimodal()` raises `ghost_patrol` **only** when the tag is at a checkpoint and no camera confirms a person. Cameras now push `PEOPLE` events (kept 15 minutes) and can be linked to a checkpoint AP (§3.12), but nothing joins them to visits: the tracker writes `vigi_detected=False`, and only the events simulation calls `verify_multimodal()`, still with no per-cycle limit (§4.8).

### AP Delete Cascade
`floor_service.delete_ap()`: (1) a `patrol_route`-only update; (2) covering cameras unlinked; (3) the AP document deleted; (4) separate clean-ups: running patrol and events simulations, the heartbeat (unless another placement of the MAC remains) and the ingest's AP cache. A clean-up failure doesn't fail the delete, and an AP already gone counts as deleted (§3.5).

### Pluggable LLM Provider (partially realised — see §5.5/§9b)
`LLM_PROVIDER` is read once, at import (an unknown value stops startup), and `LLM_MODEL_NAME` has no default (`KeyError`), so no model is picked silently. Only Gemini (`google-genai`) is implemented; the other three are stubs. RAG embeddings and AI zone detection call Gemini directly.

### iBeacon Identity over MAC for Real Devices
Phone BLE MACs rotate for privacy, so beacons are keyed on `uuid:major:minor` through the Firestore registry (30 s cache; §3.7, §3.11), and records go to `/positions/<person_id>` (e.g. `guard-001`), which also keys the Kalman filter and man-down state: a rotation changes nothing.

### Sim/Real Namespace Isolation
Real records are keyed by `person_id` (§3.7); `POST /telemetry` validates `reporter_mac` as a MAC, so simulators use fixed fake MACs (`/positions/AA_BB_CC_DD_EE_01`) and `sim-` person IDs, and the keys can't collide. Simulators clear their own records (§3.4). The pipeline is shared, though: a simulation refreshes the real APs' heartbeats (§9b), and a simulated forklift can raise a collision with a real worker on the same floor (§7).

### Live View over WebRTC, ffmpeg in Front of go2rtc
WebRTC, video only, signalled through the backend for admins. Media goes from go2rtc to the browser on port 8555 at the LAN address, as Windows won't deliver a browser's LAN-bound packets to loopback. ffmpeg reads the camera because go2rtc 1.9.14 drops its marked SEI units and emits no frame (`docs/go2rtc-sei-issue.md`). go2rtc is started by hand; `tools/go2rtc/start.ps1` relaunches it on config changes, as its restart API does nothing on Windows (§3.12).

### Placement Guides from the Room's Outline
The walls are the room's outline, with any number of corners, drawn like a zone. X and Y are measured square to two walls more than 30° from parallel (to a wall's line extended where needed), and typed values land on the clicked point's side. The walls stay in the browser's `localStorage`, per floor: an aid, while devices are still saved as image fractions (§3.13).

### Default Camera Cone, in the Editor Only
Cones show direction, not coverage, so their length is fixed on screen. A camera with no facing gets a dashed cone towards the map's middle in Manage Devices only, saved only on its handle's release (a plain click counts) or from the camera dialog. The dashboard draws none for it, and the camera panel says "Not set" (§3.12, §3.13).

---

## 9b. Known Issues & Pending Work

Live items as of 18 November 2026: not resolved yet, or not yet confirmed in the field. Items resolved since an earlier version of this document stay, marked **RESOLVED** with what fixed them.

### Real-RSSI marker placement (was the active blocker; fixed in code, live check pending)
Real readings reached the map, but the marker landed in its top-left corner: the floor's scale and the APs' metres belonged to an earlier plan image, so multilateration collapsed towards the origin. The app can no longer get into that state (§3.1, §3.5). AP metres are derived on the server at placement, on every drag and after every rescale, and an uncalibrated floor refuses AP placement and moves. `PATCH …/floors/{id}` only renames, so a plan image can't be swapped under a calibration (which answers the old open question). A solve with every AP at one point is refused instead of clamped into a corner. Also fixed: a Kalman lock-up after a recalibration (`73f131a`), and a bug that left the dashboard map's overlays undrawn on most loads (`e9d824a`; then drawn on 14 of 14 loads). **Still to do:** a live check with three APs placed.

### Man-down detection when simulation/telemetry stops — **RESOLVED**
Built as planned in `24f81f8` (4 Sep): the lifespan's `_man_down_stale_loop()` runs `check_man_down_stale()` every 60 s, so a worker or guard whose record goes stale gets a signal-loss `man_down` without waiting for telemetry. Since 20 Oct the sweep decides under `pipeline_lock` (`bcff733`), holds the alert while none of the person's APs is alive and raises one `positioning_offline` when no placed AP reports (`d64c72d`), and a restart doesn't repeat an alert for the same episode (`a971584`) (§3.2).

### RAG re-enable — **RESOLVED**
`24f81f8` (4 Sep) moved the backend to the `google-genai` SDK and re-enabled retrieval with `gemini-embedding-001`: patrol reports get similar past alert feedback as context, and a failure gives empty context (§3.8, §4.3).

### LLM providers: only Gemini is actually implemented
Still true (§5.5). `LLM_PROVIDER=openai|claude|ollama` selects a stub whose `generate()` raises `NotImplementedError`, so report generation fails outright (500, nothing saved) rather than falling back, and `settings.py` doesn't read `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` or `OLLAMA_HOST`.

### Ghost patrol and patrol compliance only fire from the simulation — **patrol compliance RESOLVED; ghost patrol still open**
- **`patrol_violation`** now fires from real positions: the patrol tracker raises `missed_checkpoint`, `short_dwell` and `no_patrol` as each window closes (§3.3).
- **`ghost_patrol`** still comes only from the events simulation, the one caller of `verify_multimodal()`. `POST /vigi/detection` is gone; cameras push `PEOPLE` and `MOTION` alarms, kept 15 minutes in memory, and can be linked to a checkpoint (§3.12), but no check reads those events, and the tracker logs `vigi_detected=False` placeholders. Matching visits to camera events is Ghost Patrol (§4.8).

### Simulation control routes have no authentication — **RESOLVED**
The routes require sign-in: `POST /simulation/start` and `POST /simulation/stop` are for admins (and the owner), and `GET /simulation/status` for any approved user (§3.4, §5.2). This has been so since `24f81f8` (4 Sep); the earlier text here was out of date.

### "Active floor" is not correctly scoped per building — **RESOLVED for real hardware; the simulators still use one floor**
Since `4bcf64c` (22 Oct) any number of floors can be active, each AP's MAC on at most one (§9). The ingest resolves each AP to its active-floor placement and each beacon to its readings' floor, positioning keeps a context per floor, and the signal-loss sweep and collision check work per floor (§3.5, §3.7). Still single-floor: the three simulators and `/telemetry`'s positioning fallback, through `FloorRepository.get_any_active()` (§3.4).

### Recharts is installed but unused
Still true, and `framer-motion` and `animejs` are listed but unused too: nothing imports them, and no chart exists in the frontend. The analytics dashboard (§4.6) would be Recharts' first use. Not a bug.

### `GET /reports` and the `accuracy_metrics` collection are unimplemented despite being referenced
Still true, though no `GET /reports` is needed: the Reports page reads `audit_reports` from Firestore. `AuditReportRepository.get_all()`, `get()` and `get_by_shift()` have no callers (only `save()` is used), and nothing reads or writes `accuracy_metrics` (§3.8).

### Beacon management UI — **RESOLVED, no longer future work**
Still built: the Firestore registry, `BeaconService`, `/beacons` (reads for any approved user, writes for admins) and `/dashboard/beacons` with its Unknown Beacons panel (§3.11). Deleting a beacon now also removes the person's `/positions` record. Kept so the old "future" framing is visibly superseded.

### Backend reachability requirement (operational — do not lose this)
The APs and the camera's Alarm Server post straight to the backend's port 8000, not through the dashboard's `/api` rewrite (§3.7, §3.12). So:
- uvicorn must listen on all interfaces, not loopback only (README.md's dev command passes `--host` for it; `python main.py` does it itself); otherwise it looks like "no data arriving".
- Inbound TCP 8000 must be allowed: `netsh advfirewall firewall add rule name="SKYE Backend 8000" dir=in action=allow protocol=TCP localport=8000`.
- The APs' push URL and the camera's Alarm Server target name this machine's LAN address, so it should stay fixed (a DHCP reservation or a static address): after a change, reports and alarms stop until both are updated. Live view follows the address by itself (§3.12).

### Red man-down restart check: live test waits for a third AP
The restart check (§9) passed its live check on 17 Nov for the amber path only: with two APs placed on the floor in use, every reading was approximate. The test suites in `tools/harness/` cover the red `man_down`'s check; its live test needs three APs placed (exact fixes), so it waits for the third AP.

### Parked man-down edges: the AP-change hold and restart repeats
- **One missed report restarts the hold.** A single reading where the run's AP is strongest again cancels a pending change, and the 120 s starts over (§9). In the 17 Nov check a move took 4.7 minutes to count instead of 2, because the old AP still won about 2% of readings; with more misses it could take much longer, and meanwhile an already-alerted run raises nothing new at the new spot. Options: cancel only after two or more readings back in a row, or not when the new AP is missing from that reading.
- **Restart repeats at the 1-minute test setting.** In a replay of one night at man-down 1 minute (89% of readings from one AP), 4 of 213 simulated restarts repeated an amber within 3 minutes (0 of 286 by day): the earlier alert sat at the AP heard least, which the new run hadn't yet had as its strongest. The fix, alerts that store every AP their run had, waits.

### Camera alarms don't get through (open)
The camera now in use closes each alarm connection before the backend has read the request body, and uvicorn then drops the body, so the alarm is lost; on 16–17 Nov this happened throughout the day. SKYE only gets alarms from a camera that waits for the reply, as the October camera did. Next: count the pushes during a 30 s walk in view with human detection on, and capture one with `tools/vigi-listener/listener.py` before changing how alarms are received. It stays open until alarms are seen arriving; the camera's alarm settings are being set up (18 Nov).

### The camera's OpenAPI is switched off (open)
The camera refuses connections on its OpenAPI port (20443), so the health check can't log in, and the camera panel's Health check reads "Camera API not reachable"; liveness and live view don't use it. It's switched on in the camera's web UI (Settings > Network Settings > OpenAPI), which is being done (18 Nov); this stays open until the check logs in.

### Simulator limits (planned)
- The events scenario's man-down segment can't raise an alert: stillness is timed on the server clock, and the segment is shorter than any man-down time Safety Settings allows (§3.4).
- Its missed-checkpoint event doesn't happen in every cycle.
- Every simulator writes heartbeats for the floor's real APs, so while one runs, offline APs look online to the dashboard and the signal-loss sweep (§3.6).

### Reload noise, and one Firebase hang after a reload
Right after every backend reload comes a 1–2 s burst of 3–15 "RuntimeError: No response returned" tracebacks: requests queued during the reload, in Starlette's `BaseHTTPMiddleware`. Long-standing and harmless, but noisy. On 17 Nov one reload was also followed by a 22 s Firebase hang (an RTDB write on a fresh connection was reset and retried); that's parked for the reliability work.

### A position update for a device that's gone answers 500 (parked)
`PATCH …/aps/{ap_id}/position` and `PATCH …/cctvs/{cctv_id}/position` answer 500, not 404, when the device was removed meanwhile, because the update meets a missing document (seen on 18 Nov after an AP drag).

---

## 10. Environment Variables

### Backend (`backend/.env`)

`config/settings.py` loads `backend/.env` with python-dotenv when the backend starts and builds a frozen `Settings` object from it. Nothing re-reads the file, so a change needs a restart (`--reload` only watches `.py` files). A missing required variable stops startup with a `KeyError`. `backend/.env.example` is the template; `.env` and the service-account key are gitignored. `VIGI_ALARM_PATH_SECRET` and `VIGI_CAMERA_PASSWORD` are kept out of the settings' `repr()` and out of every log line. The defaults below are the code defaults in `settings.py`.

**Required** (no default):

| Variable | Purpose |
|---|---|
| `FIREBASE_KEY_PATH` | Path to the Firebase Admin service-account JSON |
| `FIREBASE_RTDB_URL` | Realtime Database URL |
| `GEMINI_API_KEY` | Gemini API key: reports, RAG embeddings and AI zone detection |
| `LLM_MODEL_NAME` | The Gemini model for reports and AI zone detection; deliberately without a default, so a missing value stops startup instead of picking a model silently |
| `OMADA_ACCESS_TOKEN` | Shared ingest secret: AP reports carry it as `meta.access_token`, and the simulators send it as a Bearer token on `/telemetry` |

**Server and AI:**

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `8000` | Port for `python main.py` only; the uvicorn command sets its own |
| `DEBUG` | `false` | `true` turns on reload for `python main.py` only |
| `LLM_PROVIDER` | `gemini` | `gemini`, `openai`, `ollama` or `claude`. Only `gemini` is implemented: the other three raise `NotImplementedError` on the first report, and any other value stops startup (§5.5) |
| `RAG_SIMILARITY_FLOOR` | `0.5` | Minimum cosine similarity (0–1) for an earlier alert's feedback to enter a patrol report's context |

**AP ingest:**

| Variable | Default | Purpose |
|---|---|---|
| `OMADA_INGEST_ALLOWED_IPS` | empty | Comma-separated IPv4 addresses allowed to post to `/telemetry/omada`, checked before the token. An entry that isn't an IPv4 address stops startup |
| `OMADA_RAW_DUMP_ENABLED` | `false` | Print every raw AP report, with the token masked; for debugging |

**Positioning:**

| Variable | Default | Purpose |
|---|---|---|
| `PATH_LOSS_EXPONENT` | `2.5` | LDPL path-loss exponent *n* |
| `TX_POWER_DEFAULT` | `-59` | RSSI at 1 m (dBm) that the simulators synthesise their readings with; the solver falls back to it only when a payload's `tx_power` is 0. Real beacons use their own `tx_power` (default −59 on the beacon record) |
| `PROXIMITY_RSSI_FLOOR` | `-90.0` | One- or two-AP fallback: a beacon this faint even at its strongest AP counts as gone, and nothing is written |
| `POSITION_EXACT_HOLD_SECONDS` | `10.0` | How long a recent exact (three-AP) fix outranks a new approximate one |
| `POSITION_EMIT_MIN_INTERVAL_S` | `1.8` | Minimum seconds between solves for one beacon on the AP path |
| `RSSI_NOISE_STD` | `3.0` | Gaussian noise (dB) the simulators add to their synthetic RSSI |

**Safety** († seeds Firestore `settings/safety` on the first start; after that the Safety Settings page's values apply, re-read every 30 s, and the `.env` value is only the fallback when that document can't be read):

| Variable | Default | Purpose |
|---|---|---|
| `MAN_DOWN_MINUTES` † | `5` | Minutes of stillness before a stillness man-down |
| `MAN_DOWN_MOVEMENT_EPSILON_M` | `2.0` | Movement under this (m) counts as still |
| `MAN_DOWN_STALE_SECONDS` | `120.0` | Seconds without a position update before a signal-loss man-down |
| `MAN_DOWN_STALE_MAX_AGE_S` | `3600.0` | Position records older than this (s) are treated as dead, not as incidents |
| `MAN_DOWN_UPGRADE_CONFIRM_S` | `30` | Seconds of exact fixes within the epsilon that upgrade an amber `possible_man_down` to a red `man_down` |
| `MAN_DOWN_AP_CHANGE_HOLD_S` | `120` | With one or two APs: a change of strongest AP counts as movement only after this long (s) without a reading back at the AP the stillness run is timed at |
| `MAN_DOWN_RESTART_MATCH_H` | `12` | After a restart, an unresolved stillness alert for the same person and spot raised within this many hours isn't raised again |
| `MAN_DOWN_MOVE_CONFIRM_FIXES` | `3` | How many exact fixes in a row, each at least the epsilon from the stillness anchor, count as a move; fewer change nothing. A whole number of at least 1 (anything else stops startup); 1 counts a single fix, as before |
| `AP_SILENT_AFTER_S` | `10` | An AP whose last report is older than this (s) is silent |
| `AP_ALIVE_GRACE_S` | `30` | An AP that reports again counts as alive only once it has been reporting for this long (s) |
| `COLLISION_DISTANCE_M` † | `2.0` | Predicted worker–forklift distance (m) under which a collision alert is raised |
| `COLLISION_ALERT_SECONDS` | `3` | How far ahead (s) the Kalman filter predicts positions for the collision check |
| `COLLISION_MAX_AGE_S` | `5` | Position records older than this (s) are left out of the collision check |

**Patrols:**

| Variable | Default | Purpose |
|---|---|---|
| `PATROL_PROXIMITY_RADIUS_M` | `1.0` | A guard within this distance (m) of a route AP is at that checkpoint |
| `PATROL_PROXIMITY_EXIT_MARGIN_M` | `0.5` | Extra distance (m) before a checkpoint counts as left |
| `PATROL_NO_PATROL_DWELL_RATIO` | `0.5` | On a route of two or more checkpoints, a guard who reached only one in a window and stayed there for at least this share of it is flagged `no_patrol` |
| `MIN_DWELL_SECONDS` | `30` | Minimum dwell (s) for a compliant checkpoint visit (patrol tracker and simulators) |

**Camera (VIGI):**

| Variable | Default | Purpose |
|---|---|---|
| `VIGI_ALARM_PATH_SECRET` | empty | The secret path segment of `/vigi/alarm/<secret>`; under 24 characters counts as unset, and the route then answers 404 |
| `VIGI_CAMERA_PASSWORD` | empty | Camera admin password for the OpenAPI health check and the time-zone read (empty: those are off; TCP liveness still runs). `tools/go2rtc/start.ps1` passes it to go2rtc for live view; the generated go2rtc config only references it |
| `VIGI_RAW_DUMP_ENABLED` | `false` | Print each raw alarm body (never the path); for debugging |
| `VIGI_LIVENESS_INTERVAL_S` | `5` | Seconds between TCP checks of each camera's RTSP port |
| `VIGI_OPENAPI_INTERVAL_S` | `300` | Seconds between OpenAPI health checks |
| `VIGI_OPENAPI_START_DELAY_S` | `60` | Delay (s) before the first OpenAPI check after a start |
| `VIGI_DISCOVERY_INTERVAL_S` | `60` | Seconds between ONVIF discovery rounds (one also runs at startup); `0` turns them off, while the editor's Scan now still works |

**Live view (go2rtc):**

| Variable | Default | Purpose |
|---|---|---|
| `GO2RTC_API_URL` | go2rtc's API on the loopback interface, port 1984 | Where WebRTC offers are forwarded; keep it on this machine |
| `GO2RTC_CONFIG_PATH` | `tools/go2rtc/go2rtc.yaml` | The go2rtc config the backend generates (gitignored) |
| `GO2RTC_WEBRTC_HOST` | empty (auto) | The address go2rtc's WebRTC port (8555) listens on; empty means this machine's LAN address on the route to the registered camera |
| `GO2RTC_FFMPEG_PATH` | `tools/go2rtc/bin/ffmpeg.exe` | The ffmpeg go2rtc runs for each viewing |

The defaults are under the repository root's `tools/go2rtc/`; a relative `GO2RTC_CONFIG_PATH` or `GO2RTC_FFMPEG_PATH` set in `.env` is taken from `backend/`.

**Listed in `backend/.env.example` but not read:** `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` and `OLLAMA_HOST`, for the stub providers (§5.5); `settings.py` doesn't load them.

**Not settings:** the simulators post to a fixed `http://localhost:8000/telemetry` (a constant in each `simulation_*.py`), so they expect the backend on port 8000 of the same machine.

**Test harness only** (`tools/harness/`, never read by `settings.py`): `HARNESS_ENV_PATH` (load a test `.env` instead of the real one) and `HARNESS_FAKE_AUTH`. The harness launcher also defaults `VIGI_DISCOVERY_INTERVAL_S` to `0` and points `GO2RTC_CONFIG_PATH` and `GO2RTC_API_URL` away from the live go2rtc, unless the caller sets them. See `tools/harness/README.md`.

### Frontend (`frontend/.env.local`)

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_FIREBASE_API_KEY` | Firebase web-app API key |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | Firebase Auth domain |
| `NEXT_PUBLIC_FIREBASE_RTDB_URL` | Realtime Database URL (the same database as the backend's `FIREBASE_RTDB_URL`) |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | Firebase project ID |
| `NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET` | Storage bucket for floor-plan uploads |
| `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID` | Messaging sender ID |
| `NEXT_PUBLIC_FIREBASE_APP_ID` | Firebase app ID |
| `BACKEND_URL` | Server-only (no `NEXT_PUBLIC_` prefix): the target of the `/api/*` rewrite in `next.config.js`, default `http://localhost:8000`; read when `next dev` starts |

The seven `NEXT_PUBLIC_*` values are read once, in `frontend/config/firebase.ts`, and are bundled into the browser code: they're the Firebase web config, not secrets. `frontend/.env.local.example` is the template; `.env.local` is gitignored. Restart `npm run dev` after a change.

---

*SKYE Sentinel-AI · Authorised Access Only*
