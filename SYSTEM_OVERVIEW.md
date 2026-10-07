# SKYE Sentinel-AI — System Overview

> Autonomous Industrial Safety & Patrol Intelligence System

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
9b. [Known Issues & Pending Work](#9b-known-issues--pending-work)
10. [Environment Variables](#10-environment-variables)

---

## 1. System Overview

SKYE Sentinel-AI is an autonomous indoor safety patrol monitoring system designed for industrial environments such as warehouses, factories, and logistics floors. It combines BLE beacon tracking, real-time AI-powered safety detection, and LLM-generated audit reports into a single operations dashboard.

**Core problem it solves:**  
Traditional safety patrols rely on manual logbooks and radio check-ins. Supervisors have no real-time awareness of where guards, workers, or forklifts are inside a building. Incidents — worker collapses, near-miss collisions, missed checkpoints, proxy patrol fraud — go undetected until the next human check.

**How SKYE addresses this:**

| Problem | SKYE Solution |
|---|---|
| No real-time location | BLE beacon RSSI → LDPL → multilateration → Kalman filter → live floor map |
| Delayed incident response | Automated man-down and collision detection within seconds of trigger |
| Unverifiable patrol compliance | Checkpoint logging with dwell time + VIGI camera cross-verification |
| Ghost patrol / proxy fraud | Ghost patrol alert when BLE present but VIGI does not confirm human |
| Manual post-shift reporting | Gemini 3.1 Flash Lite generates structured audit reports from live data |
| No central operations view | Next.js dashboard: floor map, personnel panel, alert feed, device status |

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FIELD LAYER                              │
│  BLE Beacon Tags (Guards / Workers / Forklifts)                 │
│  VIGI IP Cameras (heartbeat only — see §9b for detection gap)   │
└────────────────────────┬────────────────────────────────────────┘
                         │ RSSI broadcasts
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    NETWORK LAYER                                 │
│  TP-Link Omada WiFi Access Points — capture BLE RSSI per MAC    │
└──────────┬──────────────────────────────────────────────────────┘
           │                          │
           │ POST /telemetry          │ POST /telemetry/omada
           │ (simulation path)        │ (real AP path — AP-centric)
           │ Bearer token header      │ token in meta.access_token body
           ▼                          ▼
┌─────────────────────────────────────────────────────────────────┐
│                   BACKEND — Python / FastAPI                     │
│                                                                 │
│  OmadaIngestService  (real AP path only)                        │
│    AP-centric → beacon-centric inversion                        │
│    iBeacon UUID:major:minor identity (survives MAC rotation)    │
│    Identity resolved via BeaconRepository (Firestore, cached)   │
│    2s rolling buffer → emit when ≥3 APs report same beacon      │
│    <3 APs reporting → ProximityService fallback (§3.7)          │
│    AP heartbeat write for every AP (registered or not)          │
│                                                                 │
│  PositioningService                                             │
│    RSSI → LDPL distance → scipy weighted least-squares          │
│    → Kalman filter [x, y, vx, vy] → predict_ahead(3s)          │
│    → pixel conversion → zone assignment                         │
│                                                                 │
│  SafetyService                                                  │
│    check_man_down()  · check_collision()                        │
│    check_patrol_compliance()  · verify_multimodal()             │
│    (ghost_patrol/patrol_violation only wired to simulation —    │
│     see §9b)                                                    │
│                                                                 │
│  LLMService  →  GeminiProvider (real) / OpenAIProvider /       │
│                 ClaudeProvider / OllamaProvider (stubs — §9b)   │
│                                                                 │
│  Simulation (patrol · events · shift-change modes)              │
└──────────┬──────────────────────────────────────┬──────────────┘
           │ firebase-admin SDK                   │ Firestore
           ▼                                      ▼
┌──────────────────────┐              ┌───────────────────────────┐
│  Firebase RTDB       │              │  Firestore                │
│  /positions          │              │  users · buildings        │
│  /alerts             │              │  floors · zones · beacons │
│  /ap_heartbeats      │              │  patrol_logs · settings   │
│  /cctv_heartbeats    │              │  audit_reports · feedback │
└──────────┬───────────┘              └───────────────────────────┘
           │ onValue (real-time)
           ▼
┌─────────────────────────────────────────────────────────────────┐
│               FRONTEND — Next.js 15 App Router                  │
│                                                                 │
│  Dashboard: floor map · personnel sidebar · KPI stats           │
│  Alerts:    alert feed · critical banner · resolve / delete     │
│  Reports:   patrol reports · safety event reports               │
│  Floor Plans: building/floor/zone management · AP/CCTV editor   │
│  Users:     approval · role management                          │
│                                                                 │
│  Zustand stores: dashboardStore · criticalAlertStore            │
│                  toastStore · themeStore                        │
└─────────────────────────────────────────────────────────────────┘
```

**Stack:**

| Layer | Technology |
|---|---|
| Backend | Python 3, FastAPI, firebase-admin, FilterPy (Kalman), NumPy/SciPy |
| Frontend | Next.js 15 App Router, TypeScript, Tailwind CSS v3, Zustand (Recharts is a listed dependency but currently unused — no charts are implemented, see §9b) |
| Database | Firebase Realtime DB (live positions/alerts) + Firestore (persistent config/logs) |
| Storage | Firebase Storage (floor plan images) |
| Auth | Firebase Auth — email/password **and** Google Sign-In (OAuth), both fully implemented |
| AI | Gemini 3.1 Flash Lite (reports + zone detection) — OpenAI/Claude/Ollama providers exist as **unimplemented stubs**, see §5.5/§9b |
| Hardware | TP-Link Omada APs (BLE RSSI capture), VIGI IP cameras (heartbeat only — no real human-presence detection wired up yet, see §9b) |

---

## 3. Prototype — What Has Been Built

### 3.1 Indoor Positioning Engine
- **LDPL formula**: `distance = 10 ^ ((TxPower − RSSI) / (10 × n))` — path loss exponent `n` tunable via env var
- **Multilateration**: weighted nonlinear least-squares via `scipy.optimize.least_squares` (`backend/utils/multilateration.py`) — inverse-square-distance weighted, weighted-centroid initial guess, `method="trf"` with floor bounds or `"lm"` without; requires ≥ 3 AP readings. (Not `numpy.linalg.lstsq` — no linear solver is used anywhere in the pipeline.)
- **<3-AP fallback**: when fewer than 3 distinct APs report a beacon, `ProximityService` produces a lower-confidence single/dual-AP proximity estimate anchored to the strongest AP instead (`PositionRecord.is_approximate=True`, `radius_m`, `anchor_ap_mac`) — see §3.7 and §7.
- **Kalman filter**: state vector `[x, y, vx, vy]`; 8m outlier rejection before update; result clamped to floor bounds; filter reset if signal gap > 10s
- **Collision prediction**: `predict_ahead(3)` projects position forward 3 seconds using velocity — direction-aware, so diverging entities do not trigger

### 3.2 Safety Alert Detection (4 Types)

| Alert Type | Trigger | Suppression |
|---|---|---|
| `man_down` | Worker/guard stays within `MAN_DOWN_MOVEMENT_EPSILON_M` of an anchor position for longer than `MAN_DOWN_MINUTES` — a **physical-stillness** check on server wall-clock time (the anchor re-seeds whenever the person moves past the epsilon). This is *not* payload-timestamp staleness despite the similar name. Forklifts exempt. Fires regardless of zone. Only checked on telemetry arrival — see §9b for the stop-gap. | 30s per person_id |
| `collision` | Worker's Kalman-predicted position converges with forklift's within threshold. Stores both parties (`other_person_id`). | **10s** per worker+forklift pair |
| `ghost_patrol` | BLE tag detected at checkpoint but VIGI camera does NOT confirm human presence | Per patrol log event — **only reachable from the simulation today, see §9b** |
| `patrol_violation` | Guard misses checkpoint (actual_arrival is null) or dwell_time < MIN_DWELL_SECONDS | Per patrol log event — **only reachable from the simulation today, see §9b** |

### 3.3 Patrol System
- Configurable patrol route (ordered AP ID list) stored per floor in Firestore
- Guards must visit APs in order; dwell time tracked per checkpoint
- VIGI camera cross-verification on each checkpoint visit
- Per-guard shift rotation — Guard Beta starts at mid-route to stay offset from Guard Alpha
- Patrol logs stored in Firestore with full compliance metadata
- **Production caveat**: today, patrol logs are only ever written by the simulation (§4.2 — no real BLE checkpoint tracker exists yet), so this system currently runs in demo/scripted form only

### 3.4 Simulation System
Three independent simulation modes, all running as asyncio loops via `POST /simulation/start?mode=`. **Note:** these routes currently have no authentication dependency at all (see §9b) despite being conceptually admin-only.

**Sim/Real namespace isolation:** All simulated `person_id` values carry a `sim-` prefix (`sim-guard-001`, `sim-guard-002`, `sim-worker-001`, `sim-forklift-001`, `sim-guard-003`, `sim-guard-004`). The real phone uses bare `guard-001`. See §9 "Sim/Real Namespace Isolation" for how the RTDB key itself is kept disjoint (it is *not* simply this `sim-` prefix — see that section for the real mechanism).

**Patrol Simulation** (`simulation_patrol.py` — mode: `patrol`):
- 2 guards (Guard Alpha EE:01, Guard Beta EE:04) follow configured patrol route
- Per-guard shift tracking; loop completion detection; wander behaviour at each AP
- RSSI synthesised via inverse LDPL + Gaussian noise — same telemetry path as real hardware

**Safety Events Simulation** (`simulation_events.py` — mode: `events`):
- 4 actors: Guard Alpha, Guard Beta, Worker 1 (EE:02), Forklift 1 (EE:03)
- Scripted timeline: `normal_patrol → man_down → collision_warning → ghost_patrol → missed_checkpoint`
- man_down: backdated seed payload triggers `check_man_down` staleness detection
- collision_warning: forklift and worker converge toward floor centre; collision fires via Kalman backend
- ghost_patrol: Guard Alpha freezes; patrol log written with `vigi_detected=False`
- missed_checkpoint: Guard Alpha skips AP index 1; patrol log written with `compliant=False`
- Does not yet have `simulation_patrol.py`'s per-guard `shift_id`/`loops_completed`/`checkpoints_this_loop` tracking, or try/except error isolation per beacon tick — tracked as future work, §4.5

**Shift Change Simulation** (`simulation_shift.py` — mode: `shift`):
- 4 guards: outgoing (Guard Alpha EE:01, Guard Beta EE:04) patrol one full loop then freeze
- Incoming (Guard Gamma EE:05, Guard Delta EE:06) wait at starting APs until both outgoing guards finish
- Shift change triggers when both outgoing guards complete their loop; incoming guards begin patrol
- This is a third, fully-built simulation mode — don't overlook it when reading dashboard/simulation descriptions elsewhere in this doc that mention only "patrol" and "safety-events"

### 3.5 Multi-Floor Building Management
- Hierarchy: **Building → Floor → Zone** — unlimited buildings, floors per building, zones per floor
- Floor plan image upload → Firebase Storage → calibration tool sets `scale_pixels_per_meter`
- One floor per building is "active" at the **Firestore data-model level** (`set_active` correctly scopes deactivation to one building) — but the real-time positioning/safety pipeline currently resolves the active floor via a single **system-wide** `FloorRepository.get_any_active()` query with no building filter, cached per-service in one non-building-scoped variable. With 2+ buildings each having their own active floor, only one building's floor actually drives AP-coordinate resolution, positioning, and safety checks at a time — see §9b.
- Zone editor: drag-to-create, resize, move; colour picker; `is_high_risk` toggle **and** a separate `risk_level` field (`"high"|"moderate"|"low"`) — both exist independently on `ZoneRecord`
- AI zone detection: Gemini Vision analyses floor plan image → returns suggested zone bounding boxes (this one is a genuine live Gemini call, not a stub)

### 3.6 Device Status Monitoring
- **AP heartbeats**: simulation writes to RTDB `/ap_heartbeats/{mac}` every tick; real Omada APs write via `OmadaIngestService._write_ap_heartbeat()` on every POST; frontend detects stale > **10s** → offline
- **CCTV heartbeats**: VIGI writes to `/cctv_heartbeats/{mac}`; stale > **10s** → offline (same threshold as APs, not a separate 15s)
- `DeviceStatusPanel` renders live online/offline status for all APs and CCTVs on the active floor
- **Detected-but-unplaced APs panel** (`APCCTVEditor`): real APs writing heartbeats but not yet placed on a floor appear in an animated panel; click any entry to enter placement mode with the MAC pre-filled

### 3.7 Real Omada RSSI Ingestion
- `POST /telemetry/omada` receives AP-centric BLE scan payloads from the Omada IoT Transport Stream
- Auth: token read from `meta.access_token` in JSON body (real APs don't send `Authorization` headers)
- **AP-centric → beacon-centric inversion**: Omada sends one payload per AP listing all beacons heard; adapter buffers readings per beacon across APs in a 2s rolling window; emits to `PositioningService` when ≥3 distinct APs have reported the same beacon
- **<3-AP fallback**: when fewer than 3 distinct APs have reported a beacon by flush time, `OmadaIngestService` routes to `ProximityService.compute_position()` instead — a single/dual-AP proximity anchor estimate — and never calls the full multilateration pipeline for that reading
- **iBeacon identity keying**: phones rotate BLE MAC every ~15 min; adapter keys on stable `uuid:major:minor` composite from the iBeacon advertisement block — identity persists across MAC rotation
- **Identity resolution is Firestore-backed**: beacon identity is resolved via `BeaconRepository` against a Firestore `beacons` collection (TTL-cached in `OmadaIngestService`), managed through a full CRUD stack and dashboard UI — see §3.11. `config/beacon_registry.py` is now only a legacy one-time seed migrated into Firestore on startup; it is not read at request time.
- **Stable RTDB key**: `reporter_mac` is set to `person_id` (e.g. `guard-001`) so the RTDB `/positions/` key never changes regardless of which BLE MAC the phone is currently using
- **AP heartbeats for unplaced APs**: every reporting AP gets a heartbeat written BEFORE the "not registered" early-return — this is what populates the detected-but-unplaced panel

### 3.8 AI Audit Reports (2 Report Types)

**Patrol Report**: per-guard, per-shift
- Inputs: Firestore patrol log checkpoints + RTDB alerts filtered by guard ID
- Output: safety rating 1–10, key risk findings, corrective actions

**Safety Event Report**: per-person, per-date
- Inputs: all RTDB alerts for that person on that day
- Output: incident summary, risk assessment, behavioural pattern analysis, corrective actions, safety rating

Both reports use Gemini 3.1 Flash Lite by default — **the only LLM provider that is actually implemented today**, see §5.5/§9b. Formatting constrained via prompt — no `####`, no backticks, no HTML from the LLM. Custom `SimpleMarkdown` renderer handles `#`–`#####` headings, `**bold**`, `*italic*`, `` `code` ``, bullet and ordered lists.

### 3.9 Live Dashboard
- **Floor map**: SVG viewport matches floor plan natural size; worker markers coloured by type (guard=green, worker=blue, forklift=amber); hover tooltip shows label, zone, coordinates
- **Personnel sidebar**: grouped Guards → Workers → Forklifts with live position data and per-type colour labels
- **Critical alert banner**: man_down and collision fire a fixed top-centre **red**-glowing banner (`rgba(220,38,38,...)`; the CSS class name `animate-amber-pulse` is a stale leftover from an earlier amber design — it now only animates opacity); stacks for simultaneous alerts; manual dismiss only — does not auto-dismiss
- **Alert feed**: full alert history with active/resolved state; collision shows `worker-001 ↔ forklift-001`; resolve and delete actions
- **Simulation controls**: start/stop **patrol, safety-events, or shift-change** sim (three modes, not two); clears stale RTDB positions on each run

### 3.10 User Management
- First registered account → auto-admin, auto-approved
- Subsequent accounts → role `user`, status `pending` until admin approves
- **Admin controls (UI)**: approve, promote to admin, delete. Suspend/unsuspend exists as a backend endpoint (`PATCH /users/{uid}/status`) for manual/API use only — it was intentionally removed from the admin table UI (code comment: *"Disabled from UI — kept for manual use only"*), not an oversight
- **Admin self-protection**: cannot delete own account. There is no self-uid guard on role or status changes, and there is no "demote to user" UI action at all — only "Promote to Admin" exists, so self-demotion isn't currently a UI-reachable action either way
- Real-time pending count badge on sidebar Users link

### 3.11 Beacon Identity Management
Fully built — not a future item, despite how earlier drafts of this document described it. Beacon identity (the iBeacon `uuid:major:minor` composite, or a plain MAC, mapped to a `person_id`/`person_type`/`label`) lives in a Firestore `beacons` collection with a full CRUD stack:
- `backend/models/beacon.py` — `Beacon` dataclass
- `backend/repositories/beacon_repository.py` — Firestore CRUD + `seed_from_legacy()` one-time migration
- `backend/services/beacon_service.py` — create/update/delete, cache invalidation, live RTDB label patching on rename
- `backend/routes/beacon_routes.py` — `GET/POST/PATCH/DELETE /beacons`
- Dashboard UI: `frontend/app/dashboard/beacons/page.tsx`, `frontend/components/map/BeaconManager.tsx`, `frontend/hooks/useBeaconScans.ts` (last-seen online/offline via RTDB `/beacon_scans`)

`config/beacon_registry.py` survives only as a legacy one-time seed source, migrated into Firestore on backend startup — it is not consulted at request time.

---

## 4. Future Improvements

### 4.1 Patrol Route Overlay on Floor Map
Draw the configured patrol route as an SVG polyline directly on the live floor map, connecting APs in patrol order with directional arrows. Data is already available (`floor.patrol_route` AP ID list + `ap.x_m / ap.y_m` coordinates) — this is a purely visual addition to `FloorMap.tsx` to help operators instantly see the expected guard path without opening the patrol config panel.

### 4.2 Real BLE Checkpoint Tracker (`patrol_tracker_service.py`)
Currently the simulation writes patrol logs directly. A production `patrol_tracker_service` would listen to live RTDB position updates, detect when a guard's smoothed position is within threshold of a patrol route AP, and automatically write the checkpoint log with dwell time — replacing the simulation's direct writes with real BLE-driven compliance tracking. **This is also why `ghost_patrol` and `patrol_violation` cannot fire from real hardware today** (§3.2, §9b) — there is no real trigger path into `SafetyService.check_patrol_compliance()` / `verify_multimodal()` until this exists.

### 4.3 RAG Re-enable
The RAG service is currently stubbed (`get_context()` returns `""`). Upgrading `google-generativeai` to the v1 stable SDK will unlock `text-embedding-004` embeddings, enabling semantic retrieval of past incidents to ground audit reports in real historical context.

### 4.4 AI Chatbot — Natural Language Query Interface
An in-dashboard AI chatbot that allows admins and users to search reports and alerts using plain English instead of navigating filter panels.

**Concept:**
```
User: "Show me all man_down alerts for worker-001 in the last 7 days"
User: "Generate a patrol report for Guard Alpha's most recent shift"
User: "Which zone had the most alerts this week?"
User: "Was there a collision warning yesterday?"
```

**Planned implementation:**
- **Frontend**: floating chat panel in the dashboard sidebar or as a modal overlay
- **Backend**: `POST /chatbot/query` — receives the user's natural language message, passes it to the active LLM provider with a function-calling prompt that maps the intent to one of:
  - RTDB alert query (by person, date, alert type)
  - Firestore patrol log query (by guard, shift, date)
  - Firestore audit report retrieval (by guard, shift)
  - Report generation trigger
- **LLM returns**: structured JSON specifying the query intent and parameters → backend executes against Firebase → returns formatted results to the frontend chat UI
- **Context awareness**: the chatbot is given the current active floor, today's date, and the list of known person IDs so it can resolve partial references ("the worker", "yesterday", "Guard Alpha")

This removes the need for operators to know which report tab, which selector, or which filter to use — they simply ask.

### 4.5 Simulation Per-Guard Shift Rotation in `simulation_events.py`
Apply the same per-guard `shift_id`, `loops_completed`, `checkpoints_this_loop` pattern already implemented in `simulation_patrol.py` to `simulation_events.py`, along with try/except error isolation per beacon tick so one actor failure does not crash the whole simulation loop.

### 4.6 Patrol Compliance Analytics Dashboard
A dedicated analytics page showing patrol compliance trends over time: checkpoint hit rate per guard, average dwell time vs. minimum required, ghost patrol frequency by zone, missed checkpoint heatmap. Data is already in Firestore `patrol_logs` — this is a visualisation layer using Recharts (already a listed dependency, currently unused — see §9b — so this would be its first real use).

### 4.7 Mobile Supervisor View
A read-only mobile-optimised view for supervisors on the floor: live personnel positions, active alerts, and the ability to acknowledge/resolve alerts from a phone — without exposing the full admin configuration panels.

---

## 5. Backend Detail

### 5.1 Application Setup (`main.py`)

- FastAPI app: `SKYE Sentinel-AI v0.1.0`
- Firebase Admin SDK initialised with RTDB URL on startup
- Middleware: CORS (**restricted to `http://localhost:3000` / `http://127.0.0.1:3000` — not all origins**), `RequestLogger`, global `error_handler`
- Registered routers: `auth · telemetry · omada_telemetry · alert · beacon · building · floor · zone · report · safety_settings · user · simulation · vigi`

### 5.2 Routes

#### Auth — PUBLIC
| Method | Path | Description |
|---|---|---|
| POST | `/auth/register` | Create Firebase Auth account + Firestore user doc. First user → admin/approved. Others → user/pending. |
| POST | `/auth/google` | Verify Google ID token, upsert Firestore user doc. Fully implemented — this is not the only auth path, see §2 stack table. |

#### Telemetry — Omada Bearer token
| Method | Path | Description |
|---|---|---|
| POST | `/telemetry` | Simulation path. Beacon-centric RSSI payload → LDPL → multilateration → Kalman → RTDB + safety checks. Auth: `Authorization: Bearer` header. Rate limit: 200/min. |
| POST | `/telemetry/omada` | Real AP path. AP-centric Omada payload → invert/buffer → positioning pipeline (or `ProximityService` fallback below 3 APs). Auth: `meta.access_token` in JSON body. Rate limit: 600/min. |

#### Alerts — require_auth / require_admin
| Method | Path | Description |
|---|---|---|
| GET | `/alerts` | All alerts from RTDB. (`require_auth`) |
| POST | `/alerts/{alert_id}/feedback` | Submit feedback on an alert; internally marks the alert resolved as a side effect (`mark_resolved()`). There is no separate `PATCH .../resolve` endpoint. (`require_auth`) |
| DELETE | `/alerts/{alert_id}` | Delete alert from RTDB. (`require_admin`) |

#### Beacons — require_auth / require_admin
| Method | Path | Description |
|---|---|---|
| GET | `/beacons` | List all registered beacons. (`require_auth`) |
| POST | `/beacons` | Register a new beacon (iBeacon uuid/major/minor + person_id/type/label). (`require_admin`) |
| PATCH | `/beacons/{beacon_id}` | Update beacon fields; live-patches the RTDB position label if it exists. (`require_admin`) |
| DELETE | `/beacons/{beacon_id}` | Delete a beacon. (`require_admin`) |

#### Users — require_admin
| Method | Path | Description |
|---|---|---|
| GET | `/users` | All users ordered by created_at desc. |
| GET | `/users/pending` | Users where status == "pending". |
| PATCH | `/users/{uid}/role` | Update role (admin/user). No self-uid guard. |
| PATCH | `/users/{uid}/status` | Update status (pending/approved/suspended). No self-uid guard. Not exposed in the frontend UI table (manual/API use only, see §3.10). |
| DELETE | `/users/{uid}` | Delete Firebase Auth account + Firestore doc. Only route with a self-protection check (cannot delete own account). |

#### Buildings — mixed auth
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/buildings` | require_auth | All buildings. |
| POST | `/buildings` | require_admin | Create building. |
| PATCH | `/buildings/{id}` | require_admin | Rename/update building. |
| DELETE | `/buildings/{id}` | require_admin | Delete building (cascades to floors + zones). |

#### Floors / APs / CCTVs — mixed auth
Reads use `require_auth`; every mutation uses `require_admin`.

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/buildings/{id}/floors` | require_auth | All floors for a building. |
| POST | `/buildings/{id}/floors` | require_admin | Upload floor plan image → Storage → create Firestore doc. |
| PATCH | `/buildings/{id}/floors/{id}/scale` | require_admin | Set pixels-per-metre calibration. |
| PATCH | `/buildings/{id}/floors/{id}/activate` | require_admin | Activate this floor; deactivates all others in building (Firestore-level only — see §3.5 for the positioning-pipeline caveat). |
| PATCH | `/buildings/{id}/floors/{id}/patrol` | require_admin | Set patrol_enabled + patrol_route (ordered AP ID list). |
| DELETE | `/buildings/{id}/floors/{id}` | require_admin | Delete floor + Storage image + zones. |
| GET | `/buildings/{id}/floors/{id}/aps` | require_auth | List APs on a floor. |
| POST | `/buildings/{id}/floors/{id}/aps` | require_admin | Add AP to floor with x/y position. |
| DELETE | `/buildings/{id}/floors/{id}/aps/{ap_id}` | require_admin | Delete AP + RTDB heartbeat cleanup + patrol route cleanup. |
| GET | `/buildings/{id}/floors/{id}/cctvs` | require_auth | List CCTVs on a floor. |
| POST | `/buildings/{id}/floors/{id}/cctvs` | require_admin | Add CCTV with MAC address. |
| DELETE | `/buildings/{id}/floors/{id}/cctvs/{cctv_id}` | require_admin | Delete CCTV. |

#### Zones — mixed auth
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/buildings/{id}/floors/{id}/zones` | require_auth | All zones for a floor. |
| POST | `/buildings/{id}/floors/{id}/zones` | require_admin | Create zone (name, color, bounds, is_high_risk, risk_level). |
| PATCH | `/buildings/{id}/floors/{id}/zones/{id}` | require_admin | Update zone properties. |
| DELETE | `/buildings/{id}/floors/{id}/zones/{id}` | require_admin | Delete zone. |
| POST | `/buildings/{id}/floors/{id}/zones/ai-detect` | require_admin | Gemini Vision auto-detect zones from floor plan image (real, working call). |

#### Reports — require_admin
| Method | Path | Description |
|---|---|---|
| GET | `/reports/shifts` | Reportable shifts (distinct shift_id + guard_id from patrol_logs). |
| POST | `/reports/generate` | Generate patrol audit report for a shift via Gemini. |
| GET | `/reports/safety-groups` | Distinct (person_id, date) pairs from RTDB alerts. |
| POST | `/reports/generate-safety` | Generate safety event report for a person+date. |

*(There is no bare `GET /reports` — `audit_report_repository.get_all()` exists but has zero callers anywhere in the backend; this endpoint does not exist despite appearing in earlier drafts of this doc.)*

#### Safety Settings — require_auth / require_admin
| Method | Path | Description |
|---|---|---|
| GET | `/settings/safety` | Current runtime-configurable safety thresholds (man_down_minutes, collision_distance_m). (`require_auth`) |
| PUT | `/settings/safety` | Update thresholds. (`require_admin`) |

#### Simulation — **PUBLIC, no auth enforced**
| Method | Path | Description |
|---|---|---|
| POST | `/simulation/start` | Start simulation (mode: "patrol", "events", or "shift"). |
| POST | `/simulation/stop` | Stop running simulation. |
| GET | `/simulation/status` | Current simulation mode and running state. |

**None of these three routes have any `Depends()` auth check** — unlike almost every other mutating route in the app. See §9b.

#### VIGI — Omada Bearer token
| Method | Path | Description |
|---|---|---|
| POST | `/vigi/detection` | Writes a CCTV heartbeat to RTDB `/cctv_heartbeats`. **Does not perform human-presence detection** — see §9b; this only proves the camera is online. |

### 5.3 Models

| Model | Key Fields |
|---|---|
| `UserRecord` | uid, email, display_name, role (admin/user), status (pending/approved/suspended), person_id, created_at |
| `PositionRecord` | beacon_mac, person_id, person_type (guard/worker/forklift), label, x, y, zone, timestamp, predicted_x/y, pixel_x/y, is_stationary, floor_id, building_id, radius_m (proximity-estimate radius), is_approximate (True when from a single/dual-AP proximity fix, not a full solve), anchor_ap_mac |
| `AlertRecord` | alert_id, alert_type, person_id, zone, timestamp, resolved, other_person_id (collision only), approximate (low-confidence flag when raised from a proximity-fallback position) |
| `AccessPoint` (code class name — the doc previously called this `APRecord`) | id, floor_id, building_id, mac, name, x_pct, y_pct, x_m, y_m, created_at |
| `CCTV` (code class name — the doc previously called this `CCTVRecord`) | id, floor_id, building_id, mac, name, x_pct, y_pct, created_at |
| `BuildingRecord` | id, name, description, user_id, created_at |
| `FloorRecord` | id, building_id, name, floor_number, url, storage_path, is_active, scale_pixels_per_meter, image_width_px, image_height_px, patrol_enabled, patrol_route |
| `ZoneRecord` | id, floor_id, name, color, is_high_risk, risk_level ("high"\|"moderate"\|"low" — a separate field from is_high_risk), x_min/max, y_min/max, created_by, created_at |
| `PatrolLogRecord` | log_id, guard_id, checkpoint_id, checkpoint_name, expected_arrival, actual_arrival, dwell_time_seconds, min_dwell_required, ble_detected, vigi_detected, compliant, shift_id |
| `AuditReportRecord` | report_id, shift_id, guard_id, generated_at, patrol_summary, alert_summary, rag_examples_used, report_text, model_used, report_type (patrol/safety_event) |
| `Beacon` | id (composite `uuid:major:minor`), uuid, major, minor, person_id, person_type, label, created_at, updated_at, building_id (org tag only), tx_power |
| `SafetySettings` | man_down_minutes, collision_distance_m, updated_at |

### 5.4 Services

| Service | Responsibility |
|---|---|
| `OmadaIngestService` | AP-centric → beacon-centric inversion; iBeacon identity resolution via `BeaconRepository`; 2s rolling buffer; <3-AP → `ProximityService` fallback; AP heartbeat writes; emits to PositioningService |
| `PositioningService` | Full BLE → position pipeline; LDPL → multilateration → Kalman → pixel conversion → zone assignment → RTDB save |
| `ProximityService` | Single/dual-AP fallback position estimate when <3 APs report a beacon (proximity anchoring, not full multilateration) |
| `SafetyService` | `check_man_down`, `check_collision` (10s pair suppression), `check_patrol_compliance`, `verify_multimodal`, `run_all_checks` |
| `LLMService` | `generate_report` (patrol), `generate_safety_report` (safety events), `get_safety_event_groups`, `get_reportable_shifts` — routes through whichever `LLM_PROVIDER` is configured, but only Gemini is implemented (§5.5) |
| `FloorService` | Floor CRUD, scale recalculation, AP coordinate recalculation on scale change, AP delete with RTDB cleanup |
| `BeaconService` | Beacon CRUD, cache invalidation on write, live RTDB position-label patching on rename (only patches an existing record — never creates a partial one) |
| `SafetySettingsService` | Runtime-configurable man_down_minutes / collision_distance_m, TTL-cached |
| `RagService` (doc previously wrote this `RAGService`) | Stubbed — `get_context()` returns `""`. Planned: text-embedding-004 semantic retrieval |
| `KalmanService` | `update(x,y)`, `predict_ahead(seconds)`, `reset()`, `clamp_state()` |
| `VigiService` | Write CCTV heartbeat to RTDB on detection event only — no human-presence classification |

### 5.5 LLM Provider Abstraction

```
LLM_PROVIDER env var
      │
      ├── "gemini"  → GeminiProvider   (google-generativeai) — IMPLEMENTED
      ├── "openai"  → OpenAIProvider   (openai SDK)          — STUB, raises NotImplementedError
      ├── "claude"  → ClaudeProvider   (anthropic SDK)       — STUB, raises NotImplementedError
      └── "ollama"  → OllamaProvider   (local Ollama endpoint) — STUB, raises NotImplementedError
```

**Only `GeminiProvider` is implemented today.** `OpenAIProvider`, `ClaudeProvider`, and `OllamaProvider` all have `generate()` methods that immediately `raise NotImplementedError(...)` — selecting `LLM_PROVIDER=openai|claude|ollama` will make every report-generation call fail outright, not silently degrade to a different model. `backend/config/settings.py` does not even load `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `OLLAMA_HOST` as config fields — only `GEMINI_API_KEY` is real. See §9b.

All providers implement (or are meant to implement) `BaseLLMProvider.generate(prompt: str) → str`.  
`LLM_MODEL_NAME` env var sets the model — raises `KeyError` if missing (no silent fallback).

### 5.6 Repositories

| Repository | Storage | Key Methods |
|---|---|---|
| `PositionRepository` | RTDB `/positions` | save, get, get_all, delete, delete_ap_heartbeat |
| `AlertRepository` | RTDB `/alerts` | save, get, get_all, mark_resolved, delete |
| `APRepository` | Firestore, **nested**: `buildings/{building_id}/floors/{floor_id}/access_points` (not a top-level `aps` collection) | save, get_all, update_coordinates, delete, get_by_mac_global (via `collection_group`) |
| `CCTVRepository` | Firestore, nested: `buildings/{building_id}/floors/{floor_id}/cctvs` | save, get_all, delete |
| `ZoneRepository` | Firestore, nested: `buildings/{building_id}/floors/{floor_id}/zones` | save, get_all, update, delete |
| `BuildingRepository` | Firestore `buildings` | save, get_all, get_by_id, update, delete |
| `FloorRepository` | Firestore `floors` | save, get_all, get_active (per-building), get_any_active (**system-wide**, no building filter — see §3.5/§9b), update_scale, set_active, delete, update_patrol_config |
| `PatrolLogRepository` | Firestore `patrol_logs` | save, get_by_shift_and_guard, get_reportable_shifts |
| `AuditReportRepository` | Firestore `audit_reports` | save, get_all (defined but has zero callers — no `GET /reports` route exists to use it) |
| `UserRepository` | Firestore `users` | create, get_by_uid, get_all, get_pending, update_role, update_status, delete |
| `BeaconRepository` | Firestore `beacons` | get_all, get_by_id, exists, save, update_fields, delete, seed_from_legacy |
| `SafetySettingsRepository` | Firestore singleton doc `settings/safety` | get, update |
| `FeedbackRepository` | Firestore `feedback` | save, get_all, get_by_alert_type, get_by_zone — reserved for RAG when re-enabled |
| `AccuracyMetricsRepository` | Firestore `accuracy_metrics` | save, get_by_id, get_by_run_id, get_by_shift_id — **defined but currently unused; nothing in the backend calls it** |

---

## 6. Frontend Detail

### 6.1 Pages

| Route | Access | Purpose |
|---|---|---|
| `/` | Public | Redirects to `/dashboard` |
| `/login` | Public | Email/password or Google sign-in |
| `/register` | Public | Account creation (email/password or Google) |
| `/pending-approval` | Pending users | Waiting for admin approval |
| `/suspended` | Suspended users | Account suspended message |
| `/dashboard` | Approved | Live floor map + KPI stats + alert summary |
| `/dashboard/alerts` | Approved | Full alert list with resolve/delete |
| `/dashboard/reports` | **Approved** (not admin-gated — see note) | Generate + view patrol and safety event reports |
| `/dashboard/users` | Admin | Approve/promote/remove users |
| `/dashboard/floor-plans` | **Approved** (not admin-gated — see note) | Buildings → Floors → Zones → APs → CCTVs |
| `/dashboard/beacons` | Approved/Admin | Beacon registration & management (§3.11) |

**Note:** the Reports and Floor Plans nav links are marked `adminOnly: false` in `Sidebar.tsx`, and neither page nor `dashboard/layout.tsx` enforces a role guard on route access. For Floor Plans, individual *edit* controls are gated behind `isAdmin` in the UI, so non-admins can view but not mutate. For Reports, it goes further: `audit_reports` is read directly from Firestore via `onSnapshot`, and the Firestore rule only requires `isSignedIn()` (no role/approval check) — so any authenticated user can view all report content, though the four `/reports/*` generation endpoints are correctly `require_admin` server-side.

### 6.2 Key Components

**Layout**
- `Navbar` — logo, page title, theme toggle, user avatar, sign-out
- `Sidebar` — collapsible nav, amber pending badge on Users link, personnel live list grouped by type (Guards → Workers → Forklifts)

**Dashboard / Map**
- `FloorMap` — SVG floor plan overlay; zone polygons; worker markers; hover tooltip portal; calibration tool
- `WorkerMarker` — animated SVG dot coloured by person_type; colour consistent with `FloorMap` tooltip
- `FloorMapArea` — Building **and** Floor selector dropdowns (both built on the shared `SelectDropdown` component, Building selector shown when >1 building exists); mounts `FloorMap` + `DeviceStatusPanel`
- `DeviceStatusPanel` — live AP + CCTV online/offline status with glow dot indicators
- `PatrolConfigPanel` — toggle patrol enabled + drag-to-reorder AP route
- `SimulationControls` — start/stop patrol, safety-events, or shift-change simulation
- `APCCTVEditor` — add/delete APs and CCTVs per floor; detected-but-unplaced AP panel for one-click placement of real online APs
- `ZoneEditor` — drag-to-create zones, colour picker, is_high_risk toggle, AI detect button
- `BeaconManager` — register/edit/delete beacons (§3.11)

**Alerts**
- `CriticalAlertBanner` — fixed top-centre banner for man_down/collision; **red** glow (`rgba(220,38,38,...)`, despite the CSS class name `animate-amber-pulse`); stacks; manual dismiss only
- `AlertList` — full alert history, filterable
- `AlertCard` — type badge, person_id, `↔ other_person_id` for collision, zone, timestamp, active/resolved state

**Reports**
- `ReportCard` — rendered audit report card in list
- Reports page — tab switcher (Patrol Reports / Safety Events); selector + generate button; `SimpleMarkdown` renderer for report detail panel

**Shared**
- `SelectDropdown` — generic labeled dropdown (open/close state, keyboard-friendly trigger), used by FloorMapArea's Building/Floor selectors and the Floor selector pattern more broadly
- `ToastContainer` — auto-dismiss success/error/info toasts (independent of critical banner)
- `AlertTypeBadge` — coloured type pill
- `LoadingSpinner` / `FullScreenLoader`

### 6.3 Stores (Zustand)

| Store | State |
|---|---|
| `dashboardStore` | positions, alerts, cachedReports, cachedUsers, cachedBuildings, activeShiftId |
| `criticalAlertStore` | queue (AlertRecord[]), seenIds (Set) — addCritical, dismissCritical |
| `toastStore` | toasts — toast.success(), toast.error(), toast.info() auto-dismiss |
| `themeStore` | `theme: "dark" \| "light"`, `toggleTheme()` — **not** an `isDarkMode` boolean |

### 6.4 Hooks

| Hook | Description |
|---|---|
| `useAuth` | Firebase auth state + Firestore UserRecord; redirects on status change |
| `usePositions` | RTDB `/positions` live subscription → dashboardStore |
| `useAlerts` | RTDB `/alerts` live subscription → dashboardStore + criticalAlertStore diff for new critical alerts |
| `useAPHeartbeats` | RTDB `/ap_heartbeats` + 1s interval recompute → online/offline per MAC (10s threshold) |
| `useCCTVHeartbeats` | RTDB `/cctv_heartbeats` + 1s interval recompute → online/offline per MAC (10s threshold) |
| `useBeaconScans` | RTDB `/beacon_scans` last-seen → online/offline per registered beacon |

---

## 7. Data Flow: BLE → Backend → Frontend

```
[Guard/Worker/Forklift wears BLE beacon tag]
        ↓
[TP-Link Omada APs pick up RSSI from BLE broadcasts]
        ↓
        ├── SIMULATION PATH ──────────────────────────────────────
        │   POST /telemetry  (Authorization: Bearer header)
        │   { reporter_mac=<sim beacon's fixed fake MAC>, person_id, person_type,
        │     label, readings: [{ap_mac, rssi, ap_x, ap_y}] }
        │   (reporter_mac must pass TelemetryRequest's MAC-format validation —
        │    see §"Sim/Real Namespace Isolation" for why this differs from the real path)
        │
        └── REAL AP PATH ──────────────────────────────────────────
            POST /telemetry/omada  (meta.access_token in body)
            { reporter: {mac, name, ...},
              reported: [{mac, rssi:{avg}, ibeacon:{uuid,major,minor}, ...}] }
                ↓
            OmadaIngestService.ingest()
              1. Write AP heartbeat → RTDB /ap_heartbeats/{mac_underscores}
              2. Look up AP coordinates from active floor cache
              3. For each beacon: extract iBeacon uuid:major:minor
              4. Resolve identity via BeaconRepository (Firestore `beacons`
                 collection, TTL-cached) — beacon_registry.py is only a
                 legacy one-time seed, not consulted at request time
              5. Buffer reading per beacon across APs (2s window)
              6a. When ≥3 APs report same beacon → emit OmadaTelemetryPayload
                  (reporter_mac = person_id for stable RTDB key)
                  → PositioningService.compute_position() (full pipeline below)
              6b. When <3 APs have reported by flush time → instead call
                  ProximityService.compute_position() (single/dual-AP
                  anchor estimate, is_approximate=True) → still runs
                  SafetyService.run_all_checks() on the result, but never
                  reaches the multilateration/Kalman pipeline below
        ↓
PositioningService.compute_position()   [full-multilateration path only]
  1. RSSI → LDPL distance per AP
  2. Multilateration (≥3 APs, scipy.optimize.least_squares — weighted
     nonlinear least-squares, not numpy.linalg.lstsq) → raw (x, y) metres
  3. Clamp to floor bounds
  4. KalmanService.update(x, y) → smoothed (x, y), velocity (vx, vy)
  5. KalmanService.predict_ahead(3) → collision candidate (px, py)
  6. pixel_x/y = x/y × scale_pixels_per_meter
  7. zone = self._lookup_zone(x, y) — a per-floor cache refreshed from
     ZoneRepository (not a standalone coordinate_to_zone() call)
  8. RTDB /positions/{mac_underscores} ← save PositionRecord
        ↓
SafetyService.run_all_checks()
  ├─ check_man_down(current)
  │    stillness within MAN_DOWN_MOVEMENT_EPSILON_M past MAN_DOWN_MINUTES?
  │    → RTDB /alerts ← AlertRecord (man_down)
  │    30s suppression via _last_man_down dict
  └─ check_collision(all_positions)
       predicted positions converge? → RTDB /alerts ← AlertRecord (collision, other_person_id)
       10s suppression via _last_collision dict per worker|forklift pair
        ↓
[Firebase RTDB pushes to all connected Next.js clients instantly]
        ↓
useAlerts() RTDB onValue listener
  ├─ dashboardStore.setAlerts(data)        → AlertList + AlertCard update
  └─ criticalAlertStore.addCritical(alert) → CriticalAlertBanner if man_down/collision

usePositions() RTDB onValue listener
  └─ dashboardStore.setPositions(data)     → FloorMap WorkerMarker update

[Simulation tick (patrol, safety-events, or shift-change mode)]
  └─ POST /telemetry with synthetic RSSI → same pipeline as real hardware

[Patrol checkpoint reached — simulation only today, see §4.2/§9b]
  PatrolLogRecord written → Firestore patrol_logs
  SafetyService.check_patrol_compliance() → optional patrol_violation alert
  SafetyService.verify_multimodal()       → optional ghost_patrol alert

[Admin generates patrol report]
  POST /reports/generate { log_id, guard_id }
  ├─ Firestore patrol_logs → patrol summaries
  ├─ RTDB /alerts filtered by guard_id → alert summaries
  ├─ RAGService.get_context() (stubbed)
  ├─ LLMService._build_prompt() + provider.generate() (Gemini only — §5.5)
  └─ Firestore audit_reports ← AuditReportRecord (report_type: "patrol")

[Admin generates safety event report]
  POST /reports/generate-safety { person_id, date_str }
  ├─ RTDB /alerts filtered by person_id + date → alert summaries
  ├─ LLMService._build_safety_prompt() + provider.generate() (Gemini only — §5.5)
  └─ Firestore audit_reports ← AuditReportRecord (report_type: "safety_event")
```

---

## 8. Firebase Usage

### Realtime Database — live, ephemeral

| Path | Data | Update Frequency |
|---|---|---|
| `/positions/{key}` | PositionRecord | Every telemetry packet (~1s) |
| `/alerts/{alert_id}` | AlertRecord | On safety event detection |
| `/ap_heartbeats/{mac_underscores}` | `{ last_seen, mac }` | Every sim tick (~1s) or every real AP POST |
| `/cctv_heartbeats/{mac_underscores}` | `{ last_seen, mac, device_name }` | On VIGI POST (heartbeat only — no detection payload) |
| `/beacon_scans/{...}` | last-seen data powering `useBeaconScans` | On beacon activity |

> **RTDB `/positions/` key**: the two ingestion paths do **not** both key by `person_id`. Only the **real** path sets `reporter_mac = person_id` (bare, e.g. `guard-001`), so `.replace(":", "_")` is genuinely a no-op there. The **simulation** path sets `reporter_mac` to each beacon's own fixed, locally-administered fake MAC (e.g. `AA:BB:CC:DD:EE:01`) to satisfy `TelemetryRequest`'s strict MAC-format validation — so `.replace(":", "_")` is *not* a no-op for sim data, and the RTDB key looks like `/positions/AA_BB_CC_DD_EE_01`, not `/positions/sim-guard-001`. The two paths are isolated by disjoint key *shapes* (MAC-formatted vs. bare person_id), not a shared prefix. See §9 "Sim/Real Namespace Isolation" for the full explanation — this is the authoritative version.
>
> **RTDB key format**: AP/CCTV heartbeat keys always use underscores — `AA_BB_CC_DD_EE_01`. Always `mac.replace(":", "_")` before constructing those RTDB paths.

### Firestore — persistent, queryable

| Collection | Data |
|---|---|
| `users` | UserRecord |
| `buildings` | BuildingRecord |
| `floors` | FloorRecord (includes patrol_enabled, patrol_route, image dimensions) |
| `buildings/{id}/floors/{id}/access_points` | AccessPoint (nested subcollection — **not** a top-level `aps` collection; includes x_m, y_m real-world coordinates) |
| `buildings/{id}/floors/{id}/cctvs` | CCTV (nested subcollection) |
| `buildings/{id}/floors/{id}/zones` | ZoneRecord (nested subcollection) |
| `beacons` | Beacon — full CRUD, see §3.11 |
| `patrol_logs` | PatrolLogRecord |
| `audit_reports` | AuditReportRecord (report_type: patrol / safety_event) |
| `feedback` | FeedbackRecord (reserved for RAG when re-enabled) |
| `accuracy_metrics` | AccuracyMetricsRecord — **model and repository exist, but nothing in the backend currently reads or writes it; effectively dead code** |
| `settings/safety` (singleton doc) | SafetySettings (man_down_minutes, collision_distance_m — runtime-configurable via `/settings/safety`) |

### Storage

| Path | Content |
|---|---|
| `buildings/{buildingId}/floors/{timestamp}_{filename}` | Floor plan images. Path is constructed client-side in `floorService.ts` and passed through to the backend unchanged — the backend never derives this path itself. |

---

## 9. Key Design Decisions

### Dual Database Strategy
Realtime DB for **live, ephemeral** data (positions, alerts, heartbeats) — instant frontend streaming via `onValue`.  
Firestore for **persistent, queryable** data (config, logs, reports) — historical records and future RAG.

### RTDB Key Format — Underscores Only
All RTDB paths use MAC addresses with colons replaced by underscores (`AA_BB_CC_DD_EE_01`). Mixing formats causes silent data loss where listeners never receive updates because the key doesn't match.

### Kalman Filter with Direction-Aware Collision Detection
The `predict_ahead(3)` projection uses velocity state `[vx, vy]` to project each entity's position 3 seconds forward. Two entities moving away from each other will have diverging predicted positions and will NOT trigger a collision alert — reducing false positives vs. raw distance checks.

### Collision Alert Deduplication
`_last_collision: Dict[str, str]` in `safety_service.py` tracks the last alert timestamp per `"worker_id|forklift_id"` pair. A new alert only fires if **10 seconds** have elapsed since the last one (not 30 — that window belongs to the separate `_last_man_down` dict) — preventing duplicate alerts per collision segment.

### Critical Alert Banner vs. Toast
man_down and collision alerts are safety emergencies that require immediate operator attention. They are surfaced via a persistent `CriticalAlertBanner` (fixed top-centre, manual dismiss, stacks, **red** glow) — separate from the auto-dismiss toast system used for routine UI feedback like report generation success.

### Per-Guard Shift Tracking
Each simulated beacon maintains its own `shift_id`, `loops_completed`, and `checkpoints_this_loop` counters. There is no global shift state. `checkpoints_this_loop` is always initialised to 0 — never pre-filled — ensuring all N checkpoints must be visited before a shift rotation. (`simulation_events.py` doesn't have this pattern yet — see §4.5.)

### Patrol Route on Active Floor Only (aspirational — see §3.5/§9b)
Both simulation modes and the safety service are *intended* to only operate on the single active floor per building. Today this is only correctly scoped at the Firestore data-model level; the runtime pipeline resolves a single system-wide active floor via `get_any_active()`, so multi-building deployments do not yet get true per-building isolation for positioning.

### Two Report Types — Unified Renderer
`AuditReportRecord` carries `report_type: "patrol" | "safety_event"`. Existing Firestore docs without the field default to patrol via frontend fallback check (`!r.report_type || r.report_type === "patrol"`). Both types share the same `SimpleMarkdown` renderer and detail panel.

### Multi-Modal Ghost Patrol Detection (design intent — not yet reachable in production, see §9b)
Ghost patrol alerts are designed to combine BLE beacon detection (Omada) with VIGI camera confirmation, firing **only** when the BLE tag IS present but VIGI does NOT confirm a human. This logic (`verify_multimodal`) is fully implemented, but today its only caller is the simulation's scripted timeline — the real `/vigi/detection` endpoint only proves a camera is online, it does not classify human presence, and there is no real patrol-checkpoint trigger yet (§4.2).

### AP Delete Cascade
Deleting an AP triggers: Firestore AP doc delete → RTDB heartbeat path delete → simulation module AP removal → patrol route cleanup (strips deleted AP ID from `floor.patrol_route` and writes back). All in a single `floor_service.delete_ap()` call.

### Pluggable LLM Provider (partially realised — see §5.5/§9b)
A single env var (`LLM_PROVIDER`) is designed to switch the underlying model without code changes. `LLM_MODEL_NAME` must be set explicitly — raises `KeyError` if missing rather than silently using a wrong model. The factory pattern dispatches to Gemini, OpenAI, Claude, or Ollama — but only the Gemini branch is actually implemented today; the other three are stub classes that raise on first call.

### iBeacon Identity over MAC for Real Devices
Phone BLE MACs rotate every ~15 minutes for privacy. Keying beacon identity on `reported[].mac` (Omada's field) causes the position node to rotate and the Kalman filter to reset every rotation cycle. The adapter instead keys on the stable iBeacon triple `uuid:major:minor`, resolved via `BeaconRepository` against Firestore (§3.11). The RTDB position key is then derived from `person_id` (e.g. `guard-001`), which never changes — the marker persists and the Kalman filter accumulates history correctly.

### Sim/Real Namespace Isolation
The real path sets `reporter_mac = person_id` (bare IDs like `guard-001`, bypassing `TelemetryRequest` validation via direct `OmadaTelemetryPayload` construction — see §3.7) so the RTDB position key is stable across the phone's rotating BLE MAC. The simulation path posts through `POST /telemetry`, which *is* validated by `TelemetryRequest.reporter_mac` (strict `XX:XX:XX:XX:XX:XX` format) — so simulated beacons instead set `reporter_mac` to their own fixed, locally-administered fake MAC (e.g. `AA:BB:CC:DD:EE:01`), giving RTDB keys like `/positions/AA_BB_CC_DD_EE_01`. Isolation from real data (`/positions/guard-001`) now comes from the two paths using structurally disjoint key *shapes* (MAC-formatted vs. bare person_id) rather than a shared `sim-` prefix convention. Simulation startup-clears target only its own fixed set of sim beacon MACs. Running a simulation while a real phone is tracking cannot overwrite or delete the real guard's position, patrol logs, or alerts. **This is the authoritative explanation — §8's RTDB note above has been corrected to match it.**

---

## 9b. Known Issues & Pending Work

These are live items as of the current build — not yet resolved, or features that this document previously described as more complete than they actually are. Listed so the system is not mistaken for fully complete.

### Real-RSSI marker placement (active blocker)
Real RSSI flows end-to-end (3 Omada APs → `/telemetry/omada` → positioning → `/positions/guard-001`), the marker renders, and the phone shows in the sidebar. However, the marker currently lands in the **top-left corner** of the floor map. Root cause is **stale calibration after a floor-plan swap**: the active floor's `scale_pixels_per_meter` and the placed APs' `x_m/y_m` coordinates belong to a *previous* floor plan image, so multilateration collapses toward the origin. **Resolution:** recalibrate the scale on the floor plan actually in use, and re-place the 3 APs on it. (Open question to confirm: whether a *new floor record* was created, or the *image was swapped on the existing record* — the latter means the app allowed an image swap without invalidating calibration, which should be guarded against.)

### Man-down detection when simulation/telemetry stops
`check_man_down` only runs when a telemetry packet arrives. If the simulation (or real feed) stops, beacon positions freeze in RTDB and no staleness check ever fires — so a man-down that begins after the feed stops is never detected. **Planned fix:** a FastAPI background task (asyncio + lifespan) running every ~60s that scans RTDB `/positions` and fires man-down for stationary non-forklift beacons independently of telemetry arrival. Touches `main.py` (lifespan task) and `safety_service.py` (add `check_man_down_stale()`).

### RAG re-enable
RAG is stubbed: `rag_service.get_context()` returns `""` because `google-generativeai==0.7.2` routes `embed_content` through v1beta where `text-embedding-004` is unavailable. Audit reports work without it. (Also tracked in §4.3.)

### LLM providers: only Gemini is actually implemented
`LLM_PROVIDER=openai|claude|ollama` selects a stub class whose `generate()` immediately raises `NotImplementedError` — report generation will fail outright with these providers configured, not silently fall back or degrade. `settings.py` doesn't load the corresponding API-key env vars at all today. If this system is presented as having pluggable multi-provider support, that support is currently Gemini-only in practice. (§5.5)

### Ghost patrol and patrol compliance only fire from the simulation
`SafetyService.verify_multimodal()` (ghost_patrol) and `check_patrol_compliance()` (patrol_violation) are fully implemented, but the *only* code that calls them today is `simulation_events.py`'s scripted timeline. In production: (1) there is no real BLE checkpoint tracker yet (§4.2, `patrol_tracker_service.py` doesn't exist), so no real `PatrolLogRecord` is ever written outside the simulation; and (2) the real `POST /vigi/detection` endpoint only writes a CCTV heartbeat (`VigiService.write_cctv_heartbeat`) — it never produces a `vigi_detected` human-presence signal. Both alert types are currently demo-only, not something real hardware can trigger.

### Simulation control routes have no authentication
`POST /simulation/start`, `POST /simulation/stop`, and `GET /simulation/status` have zero `Depends()` auth check — fully public, unlike virtually every other mutating route in the backend (which are at minimum `require_auth`, usually `require_admin`). Anyone who can reach the backend can start or stop simulations. Worth deciding whether this is intentional (e.g. for a kiosk/demo mode) or an oversight before this ships anywhere less trusted than a local dev machine.

### "Active floor" is not correctly scoped per building
`FloorRepository.get_any_active()` is a system-wide Firestore `collection_group` query with `.limit(1)` and no building filter, used by `PositioningService`, `OmadaIngestService`, and all three simulation modules. In a deployment with 2+ buildings each having their own active floor, only one building's floor (whichever Firestore happens to return) actually drives AP-coordinate resolution, positioning, and safety checks — the "other" building's active floor is inert for real-time purposes even though the Firestore data model itself correctly scopes `is_active` per building. Needs a `get_active(building_id)`-style call threaded through the real-time pipeline instead.

### Recharts is installed but unused
Listed in the frontend stack and implied to back the (not-yet-built) analytics dashboard (§4.6), but no chart component exists anywhere in the frontend today. Not a bug, just worth knowing this dependency currently does nothing.

### `GET /reports` and the `accuracy_metrics` collection are unimplemented despite being referenced
`AuditReportRepository.get_all()` and `AccuracyMetricsRepository` both exist with working methods, but neither has any route or caller wired up anywhere in the backend — dead code today, not active features.

### Beacon management UI — **RESOLVED, no longer future work**
This item previously appeared here as "future work." It is fully built: Firestore `beacons` collection, `BeaconRepository`, `BeaconService`, `POST/GET/PATCH/DELETE /beacons`, and a dashboard UI (`/dashboard/beacons`, `BeaconManager.tsx`). See §3.11. `config/beacon_registry.py` now serves only as a legacy one-time seed. Kept here briefly so anyone who remembers the old "future" framing can see it's been superseded, rather than silently disappearing.

### Backend reachability requirement (operational — do not lose this)
For real Omada APs to reach the backend, the server **must** be started with an explicit host bind:
```
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
Without `--host 0.0.0.0`, uvicorn binds to `127.0.0.1` (loopback only) and APs cannot connect — this presents as "no data arriving" despite correct token/config/network. In addition, inbound TCP to :8000 must be permitted: either a Windows Firewall allow rule (`netsh advfirewall firewall add rule name="SKYE Backend 8000" dir=in action=allow protocol=TCP localport=8000`) OR the AP network being classified as a Private profile. Verify an existing rule with `netsh advfirewall firewall show rule name="SKYE Backend 8000"`.

---

## 10. Environment Variables

### Backend (`backend/.env`)

```env
# Firebase
FIREBASE_KEY_PATH=./serviceAccountKey.json
FIREBASE_RTDB_URL=https://your-project-default-rtdb.firebaseio.com

# LLM — LLM_MODEL_NAME required; raises KeyError if missing.
# Only LLM_PROVIDER=gemini is actually implemented today (see §5.5/§9b) —
# openai/claude/ollama select stub providers that raise NotImplementedError,
# and their API-key vars below are not even read by settings.py yet.
LLM_PROVIDER=gemini
LLM_MODEL_NAME=gemini-3.1-flash-lite
GEMINI_API_KEY=AIza...
ANTHROPIC_API_KEY=sk-ant-...      # NOT YET READ — ClaudeProvider is a stub
OPENAI_API_KEY=sk-...             # NOT YET READ — OpenAIProvider is a stub
OLLAMA_HOST=http://localhost:11434 # NOT YET READ — OllamaProvider is a stub

# Telemetry ingest
OMADA_ACCESS_TOKEN=your-omada-bearer-token

# Positioning
TX_POWER_DEFAULT=-59
PATH_LOSS_EXPONENT=2.5
RSSI_NOISE_STD=3.0

# Safety thresholds
MAN_DOWN_MINUTES=5
MAN_DOWN_MOVEMENT_EPSILON_M=2.0
COLLISION_ALERT_SECONDS=3
COLLISION_DISTANCE_M=2.0
MIN_DWELL_SECONDS=30
PROXIMITY_RSSI_FLOOR=-90.0

# Server
PORT=8000
DEBUG=false
```

### Frontend (`frontend/.env.local`)

```env
NEXT_PUBLIC_FIREBASE_API_KEY=AIza...
NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
NEXT_PUBLIC_FIREBASE_RTDB_URL=https://your-project-default-rtdb.firebaseio.com
NEXT_PUBLIC_FIREBASE_PROJECT_ID=your-project-id
NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET=your-project.appspot.com
NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=123456789
NEXT_PUBLIC_FIREBASE_APP_ID=1:123456789:web:abc123

# Server-only — no NEXT_PUBLIC_ prefix. Used in next.config.js rewrites,
# never exposed to client-side code.
BACKEND_URL=http://localhost:8000
```

---

*SKYE Sentinel-AI · Authorised Access Only*
