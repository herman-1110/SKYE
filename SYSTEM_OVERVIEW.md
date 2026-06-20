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
│  VIGI IP Cameras (human presence confirmation)                  │
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
│    2s rolling buffer → emit when ≥3 APs report same beacon      │
│    AP heartbeat write for every AP (registered or not)          │
│                                                                 │
│  PositioningService                                             │
│    RSSI → LDPL distance → numpy least-squares multilateration   │
│    → Kalman filter [x, y, vx, vy] → predict_ahead(3s)          │
│    → pixel conversion → zone assignment                         │
│                                                                 │
│  SafetyService                                                  │
│    check_man_down()  · check_collision()                        │
│    check_patrol_compliance()  · verify_multimodal()             │
│                                                                 │
│  LLMService  →  GeminiProvider / OpenAIProvider /              │
│                 ClaudeProvider / OllamaProvider                 │
│                                                                 │
│  Simulation (patrol · events · shift-change modes)              │
└──────────┬──────────────────────────────────────┬──────────────┘
           │ firebase-admin SDK                   │ Firestore
           ▼                                      ▼
┌──────────────────────┐              ┌───────────────────────────┐
│  Firebase RTDB       │              │  Firestore                │
│  /positions          │              │  users · buildings        │
│  /alerts             │              │  floors · zones           │
│  /ap_heartbeats      │              │  patrol_logs              │
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
| Frontend | Next.js 15 App Router, TypeScript, Tailwind CSS v3, Zustand, Recharts |
| Database | Firebase Realtime DB (live positions/alerts) + Firestore (persistent config/logs) |
| Storage | Firebase Storage (floor plan images) |
| Auth | Firebase Auth (email/password) |
| AI | Gemini 3.1 Flash Lite (reports + zone detection) — pluggable to OpenAI, Claude, Ollama |
| Hardware | TP-Link Omada APs (BLE RSSI capture), VIGI IP cameras (presence verification) |

---

## 3. Prototype — What Has Been Built

### 3.1 Indoor Positioning Engine
- **LDPL formula**: `distance = 10 ^ ((TxPower − RSSI) / (10 × n))` — path loss exponent `n` tunable via env var
- **Multilateration**: least-squares across all N APs simultaneously via `numpy.linalg.lstsq`; requires ≥ 3 AP readings
- **Kalman filter**: state vector `[x, y, vx, vy]`; 8m outlier rejection before update; result clamped to floor bounds; filter reset if signal gap > 10s
- **Collision prediction**: `predict_ahead(3)` projects position forward 3 seconds using velocity — direction-aware, so diverging entities do not trigger

### 3.2 Safety Alert Detection (4 Types)

| Alert Type | Trigger | Suppression |
|---|---|---|
| `man_down` | Worker/guard position timestamp stale > MAN_DOWN_MINUTES. Forklifts exempt. Fires regardless of zone. Only checked on telemetry arrival — see §9b for the stop-gap. | 30s per person_id |
| `collision` | Worker's Kalman-predicted position converges with forklift's within threshold. Stores both parties (`other_person_id`). | 30s per worker+forklift pair |
| `ghost_patrol` | BLE tag detected at checkpoint but VIGI camera does NOT confirm human presence | Per patrol log event |
| `patrol_violation` | Guard misses checkpoint (actual_arrival is null) or dwell_time < MIN_DWELL_SECONDS | Per patrol log event |

### 3.3 Patrol System
- Configurable patrol route (ordered AP ID list) stored per floor in Firestore
- Guards must visit APs in order; dwell time tracked per checkpoint
- VIGI camera cross-verification on each checkpoint visit
- Per-guard shift rotation — Guard Beta starts at mid-route to stay offset from Guard Alpha
- Patrol logs stored in Firestore with full compliance metadata

### 3.4 Simulation System
Three independent simulation modes, all running as asyncio loops via `POST /simulation/start?mode=`:

**Sim/Real namespace isolation:** All simulated `person_id` values carry a `sim-` prefix (`sim-guard-001`, `sim-guard-002`, `sim-worker-001`, `sim-forklift-001`, `sim-guard-003`, `sim-guard-004`). The real phone uses bare `guard-001`. The simulation can never pollute `/positions/guard-001` or real patrol logs.

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

**Shift Change Simulation** (`simulation_shift.py` — mode: `shift`):
- 4 guards: outgoing (Guard Alpha EE:01, Guard Beta EE:04) patrol one full loop then freeze
- Incoming (Guard Gamma EE:05, Guard Delta EE:06) wait at starting APs until both outgoing guards finish
- Shift change triggers when both outgoing guards complete their loop; incoming guards begin patrol

### 3.5 Multi-Floor Building Management
- Hierarchy: **Building → Floor → Zone** — unlimited buildings, floors per building, zones per floor
- Floor plan image upload → Firebase Storage → calibration tool sets `scale_pixels_per_meter`
- One floor per building is "active" — only active floor used for positioning and safety checks
- Zone editor: drag-to-create, resize, move; colour picker; `is_high_risk` toggle
- AI zone detection: Gemini Vision analyses floor plan image → returns suggested zone bounding boxes

### 3.6 Device Status Monitoring
- **AP heartbeats**: simulation writes to RTDB `/ap_heartbeats/{mac}` every tick; real Omada APs write via `OmadaIngestService._write_ap_heartbeat()` on every POST; frontend detects stale > 8s → offline
- **CCTV heartbeats**: VIGI detection writes to `/cctv_heartbeats/{mac}`; stale > 15s → offline
- `DeviceStatusPanel` renders live online/offline status for all APs and CCTVs on the active floor
- **Detected-but-unplaced APs panel** (`APCCTVEditor`): real APs writing heartbeats but not yet placed on a floor appear in an animated panel; click any entry to enter placement mode with the MAC pre-filled

### 3.7 Real Omada RSSI Ingestion
- `POST /telemetry/omada` receives AP-centric BLE scan payloads from the Omada IoT Transport Stream
- Auth: token read from `meta.access_token` in JSON body (real APs don't send `Authorization` headers)
- **AP-centric → beacon-centric inversion**: Omada sends one payload per AP listing all beacons heard; adapter buffers readings per beacon across APs in a 2s rolling window; emits to `PositioningService` when ≥3 distinct APs have reported the same beacon
- **iBeacon identity keying**: phones rotate BLE MAC every ~15 min; adapter keys on stable `uuid:major:minor` composite from the iBeacon advertisement block — identity persists across MAC rotation
- **Stable RTDB key**: `reporter_mac` is set to `person_id` (e.g. `guard-001`) so the RTDB `/positions/` key never changes regardless of which BLE MAC the phone is currently using
- **AP heartbeats for unplaced APs**: every reporting AP gets a heartbeat written BEFORE the "not registered" early-return — this is what populates the detected-but-unplaced panel

### 3.8 AI Audit Reports (2 Report Types)

**Patrol Report**: per-guard, per-shift
- Inputs: Firestore patrol log checkpoints + RTDB alerts filtered by guard ID
- Output: safety rating 1–10, key risk findings, corrective actions

**Safety Event Report**: per-person, per-date
- Inputs: all RTDB alerts for that person on that day
- Output: incident summary, risk assessment, behavioural pattern analysis, corrective actions, safety rating

Both reports use Gemini 3.1 Flash Lite by default. Formatting constrained via prompt — no `####`, no backticks, no HTML from the LLM. Custom `SimpleMarkdown` renderer handles `#`–`#####` headings, `**bold**`, `*italic*`, `` `code` ``, bullet and ordered lists.

### 3.9 Live Dashboard
- **Floor map**: SVG viewport matches floor plan natural size; worker markers coloured by type (guard=green, worker=blue, forklift=amber); hover tooltip shows label, zone, coordinates
- **Personnel sidebar**: grouped Guards → Workers → Forklifts with live position data and per-type colour labels
- **Critical alert banner**: man_down and collision fire a fixed top-centre amber-glowing banner; stacks for simultaneous alerts; manual dismiss only — does not auto-dismiss
- **Alert feed**: full alert history with active/resolved state; collision shows `worker-001 ↔ forklift-001`; resolve and delete actions
- **Simulation controls**: start/stop patrol or safety-events sim; clears stale RTDB positions on each run

### 3.10 User Management
- First registered account → auto-admin, auto-approved
- Subsequent accounts → role `user`, status `pending` until admin approves
- Admin controls: approve, suspend, promote to admin, delete
- Admin self-protection: cannot suspend or demote own account
- Real-time pending count badge on sidebar Users link

---

## 4. Future Improvements

### 4.1 Patrol Route Overlay on Floor Map
Draw the configured patrol route as an SVG polyline directly on the live floor map, connecting APs in patrol order with directional arrows. Data is already available (`floor.patrol_route` AP ID list + `ap.x_m / ap.y_m` coordinates) — this is a purely visual addition to `FloorMap.tsx` to help operators instantly see the expected guard path without opening the patrol config panel.

### 4.2 Real BLE Checkpoint Tracker (`patrol_tracker_service.py`)
Currently the simulation writes patrol logs directly. A production `patrol_tracker_service` would listen to live RTDB position updates, detect when a guard's smoothed position is within threshold of a patrol route AP, and automatically write the checkpoint log with dwell time — replacing the simulation's direct writes with real BLE-driven compliance tracking.

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
A dedicated analytics page showing patrol compliance trends over time: checkpoint hit rate per guard, average dwell time vs. minimum required, ghost patrol frequency by zone, missed checkpoint heatmap. Data is already in Firestore `patrol_logs` — this is a visualisation layer using Recharts.

### 4.7 Mobile Supervisor View
A read-only mobile-optimised view for supervisors on the floor: live personnel positions, active alerts, and the ability to acknowledge/resolve alerts from a phone — without exposing the full admin configuration panels.

---

## 5. Backend Detail

### 5.1 Application Setup (`main.py`)

- FastAPI app: `SKYE Sentinel-AI v0.1.0`
- Firebase Admin SDK initialised with RTDB URL on startup
- Middleware: CORS (all origins), `RequestLogger`, global `error_handler`
- Registered routers: `auth · telemetry · omada_telemetry · alert · user · building · floor · zone · report · simulation · vigi`

### 5.2 Routes

#### Auth — PUBLIC
| Method | Path | Description |
|---|---|---|
| POST | `/auth/register` | Create Firebase Auth account + Firestore user doc. First user → admin/approved. Others → user/pending. |
| POST | `/auth/google` | Verify Google ID token, upsert Firestore user doc. |

#### Telemetry — Omada Bearer token
| Method | Path | Description |
|---|---|---|
| POST | `/telemetry` | Simulation path. Beacon-centric RSSI payload → LDPL → multilateration → Kalman → RTDB + safety checks. Auth: `Authorization: Bearer` header. |
| POST | `/telemetry/omada` | Real AP path. AP-centric Omada payload → invert/buffer → positioning pipeline. Auth: `meta.access_token` in JSON body. Rate limit: 600/min. |

#### Alerts — require_auth / require_admin
| Method | Path | Description |
|---|---|---|
| GET | `/alerts` | All alerts from RTDB. |
| DELETE | `/alerts/{alert_id}` | Delete alert from RTDB. |
| PATCH | `/alerts/{alert_id}/resolve` | Mark alert resolved in RTDB. |

#### Users — require_admin
| Method | Path | Description |
|---|---|---|
| GET | `/users` | All users ordered by created_at desc. |
| GET | `/users/pending` | Users where status == "pending". |
| PATCH | `/users/{uid}/role` | Update role (admin/user). |
| PATCH | `/users/{uid}/status` | Update status (pending/approved/suspended). |
| DELETE | `/users/{uid}` | Delete Firebase Auth account + Firestore doc. |

#### Buildings — require_auth
| Method | Path | Description |
|---|---|---|
| GET | `/buildings` | All buildings. |
| POST | `/buildings` | Create building. |
| PATCH | `/buildings/{id}` | Rename/update building. |
| DELETE | `/buildings/{id}` | Delete building (cascades to floors + zones). |

#### Floors — require_auth
| Method | Path | Description |
|---|---|---|
| GET | `/buildings/{id}/floors` | All floors for a building. |
| POST | `/buildings/{id}/floors` | Upload floor plan image → Storage → create Firestore doc. |
| PATCH | `/buildings/{id}/floors/{id}/scale` | Set pixels-per-metre calibration. |
| PATCH | `/buildings/{id}/floors/{id}/activate` | Activate this floor; deactivates all others in building. |
| PATCH | `/buildings/{id}/floors/{id}/patrol` | Set patrol_enabled + patrol_route (ordered AP ID list). |
| DELETE | `/buildings/{id}/floors/{id}` | Delete floor + Storage image + zones. |
| POST | `/buildings/{id}/floors/{id}/aps` | Add AP to floor with x/y position. |
| DELETE | `/buildings/{id}/floors/{id}/aps/{ap_id}` | Delete AP + RTDB heartbeat cleanup + patrol route cleanup. |
| POST | `/buildings/{id}/floors/{id}/cctvs` | Add CCTV with MAC address. |
| DELETE | `/buildings/{id}/floors/{id}/cctvs/{cctv_id}` | Delete CCTV. |

#### Zones — require_auth
| Method | Path | Description |
|---|---|---|
| GET | `/buildings/{id}/floors/{id}/zones` | All zones for a floor. |
| POST | `/buildings/{id}/floors/{id}/zones` | Create zone (name, color, bounds, is_high_risk). |
| PATCH | `/buildings/{id}/floors/{id}/zones/{id}` | Update zone properties. |
| DELETE | `/buildings/{id}/floors/{id}/zones/{id}` | Delete zone. |
| POST | `/buildings/{id}/floors/{id}/zones/ai-detect` | Gemini Vision auto-detect zones from floor plan image. |

#### Reports — require_admin
| Method | Path | Description |
|---|---|---|
| GET | `/reports/shifts` | Reportable shifts (distinct shift_id + guard_id from patrol_logs). |
| POST | `/reports/generate` | Generate patrol audit report for a shift via Gemini. |
| GET | `/reports/safety-groups` | Distinct (person_id, date) pairs from RTDB alerts. |
| POST | `/reports/generate-safety` | Generate safety event report for a person+date. |
| GET | `/reports` | All saved audit reports from Firestore. |

#### Simulation — require_admin
| Method | Path | Description |
|---|---|---|
| POST | `/simulation/start` | Start simulation (mode: "patrol", "events", or "shift"). |
| POST | `/simulation/stop` | Stop running simulation. |
| GET | `/simulation/status` | Current simulation mode and running state. |

#### VIGI — Omada Bearer token
| Method | Path | Description |
|---|---|---|
| POST | `/vigi/detection` | CCTV detection event — writes heartbeat to RTDB `/cctv_heartbeats`. |

### 5.3 Models

| Model | Key Fields |
|---|---|
| `UserRecord` | uid, email, display_name, role (admin/user), status (pending/approved/suspended), person_id, created_at |
| `PositionRecord` | beacon_mac, person_id, person_type (guard/worker/forklift), label, x, y, zone, timestamp, predicted_x/y, pixel_x/y, is_stationary, floor_id |
| `AlertRecord` | alert_id, alert_type, person_id, zone, timestamp, resolved, other_person_id (collision only) |
| `APRecord` | id, floor_id, building_id, mac, name, x_pct, y_pct, x_m, y_m |
| `CCTVRecord` | id, floor_id, building_id, mac, name, x_pct, y_pct |
| `BuildingRecord` | id, name, description, user_id, created_at |
| `FloorRecord` | id, building_id, name, floor_number, url, storage_path, is_active, scale_pixels_per_meter, image_width_px, image_height_px, patrol_enabled, patrol_route |
| `ZoneRecord` | id, floor_id, name, color, is_high_risk, x_min/max, y_min/max, created_at |
| `PatrolLogRecord` | log_id, guard_id, checkpoint_id, checkpoint_name, expected_arrival, actual_arrival, dwell_time_seconds, min_dwell_required, ble_detected, vigi_detected, compliant, shift_id |
| `AuditReportRecord` | report_id, shift_id, guard_id, generated_at, patrol_summary, alert_summary, rag_examples_used, report_text, model_used, report_type (patrol/safety_event) |

### 5.4 Services

| Service | Responsibility |
|---|---|
| `OmadaIngestService` | AP-centric → beacon-centric inversion; iBeacon identity resolution; 2s rolling buffer; AP heartbeat writes; emits to PositioningService |
| `PositioningService` | Full BLE → position pipeline; LDPL → multilateration → Kalman → pixel conversion → zone assignment → RTDB save |
| `SafetyService` | `check_man_down`, `check_collision` (with 30s pair suppression), `check_patrol_compliance`, `verify_multimodal`, `run_all_checks` |
| `LLMService` | `generate_report` (patrol), `generate_safety_report` (safety events), `get_safety_event_groups`, `get_reportable_shifts` |
| `FloorService` | Floor CRUD, scale recalculation, AP coordinate recalculation on scale change, AP delete with RTDB cleanup |
| `RAGService` | Stubbed — `get_context()` returns `""`. Planned: text-embedding-004 semantic retrieval |
| `KalmanService` | `update(x,y)`, `predict_ahead(seconds)`, `reset()`, `clamp_state()` |
| `VigiService` | Write CCTV heartbeat to RTDB on detection event |

### 5.5 LLM Provider Abstraction

```
LLM_PROVIDER env var
      │
      ├── "gemini"  → GeminiProvider   (google-generativeai)
      ├── "openai"  → OpenAIProvider   (openai SDK)
      ├── "claude"  → ClaudeProvider   (anthropic SDK)
      └── "ollama"  → OllamaProvider   (local Ollama endpoint)
```

All providers implement `BaseLLMProvider.generate(prompt: str) → str`.  
`LLM_MODEL_NAME` env var sets the model — raises `KeyError` if missing (no silent fallback).

### 5.6 Repositories

| Repository | Storage | Key Methods |
|---|---|---|
| `PositionRepository` | RTDB `/positions` | save, get, get_all, delete, delete_ap_heartbeat |
| `AlertRepository` | RTDB `/alerts` | save, get, get_all, mark_resolved, delete |
| `APRepository` | Firestore `aps` | save, get_all, update_coordinates, delete |
| `FloorRepository` | Firestore `floors` | save, get_all, get_active, get_any_active, update_scale, set_active, delete, update_patrol_config |
| `PatrolLogRepository` | Firestore `patrol_logs` | save, get_by_shift_and_guard, get_reportable_shifts |
| `AuditReportRepository` | Firestore `audit_reports` | save, get_all |
| `UserRepository` | Firestore `users` | create, get_by_uid, get_all, get_pending, update_role, update_status, delete |

---

## 6. Frontend Detail

### 6.1 Pages

| Route | Access | Purpose |
|---|---|---|
| `/` | Public | Redirects to `/dashboard` |
| `/login` | Public | Email/password sign-in |
| `/register` | Public | Account creation |
| `/pending-approval` | Pending users | Waiting for admin approval |
| `/suspended` | Suspended users | Account suspended message |
| `/dashboard` | Approved | Live floor map + KPI stats + alert summary |
| `/dashboard/alerts` | Approved | Full alert list with resolve/delete |
| `/dashboard/reports` | Admin | Generate + view patrol and safety event reports |
| `/dashboard/users` | Admin | Approve/suspend/promote/remove users |
| `/dashboard/floor-plans` | Admin | Buildings → Floors → Zones → APs → CCTVs |

### 6.2 Key Components

**Layout**
- `Navbar` — logo, page title, theme toggle, user avatar, sign-out
- `Sidebar` — collapsible nav, amber pending badge on Users link, personnel live list grouped by type (Guards → Workers → Forklifts)

**Dashboard / Map**
- `FloorMap` — SVG floor plan overlay; zone polygons; worker markers; hover tooltip portal; calibration tool
- `WorkerMarker` — animated SVG dot coloured by person_type; colour consistent with `FloorMap` tooltip
- `FloorMapArea` — floor selector dropdown; mounts `FloorMap` + `DeviceStatusPanel`
- `DeviceStatusPanel` — live AP + CCTV online/offline status with glow dot indicators
- `PatrolConfigPanel` — toggle patrol enabled + drag-to-reorder AP route
- `SimulationControls` — start/stop patrol, safety-events, or shift-change simulation
- `APCCTVEditor` — add/delete APs and CCTVs per floor; detected-but-unplaced AP panel for one-click placement of real online APs
- `ZoneEditor` — drag-to-create zones, colour picker, is_high_risk toggle, AI detect button

**Alerts**
- `CriticalAlertBanner` — fixed top-centre banner for man_down/collision; amber glow; stacks; manual dismiss only
- `AlertList` — full alert history, filterable
- `AlertCard` — type badge, person_id, `↔ other_person_id` for collision, zone, timestamp, active/resolved state

**Reports**
- `ReportCard` — rendered audit report card in list
- Reports page — tab switcher (Patrol Reports / Safety Events); selector + generate button; `SimpleMarkdown` renderer for report detail panel

**Shared**
- `ToastContainer` — auto-dismiss success/error/info toasts (independent of critical banner)
- `AlertTypeBadge` — coloured type pill
- `LoadingSpinner` / `FullScreenLoader`

### 6.3 Stores (Zustand)

| Store | State |
|---|---|
| `dashboardStore` | positions, alerts, cachedReports, cachedUsers, cachedBuildings, activeShiftId |
| `criticalAlertStore` | queue (AlertRecord[]), seenIds (Set) — addCritical, dismissCritical |
| `toastStore` | toasts — toast.success(), toast.error(), toast.info() auto-dismiss |
| `themeStore` | isDarkMode — dark/light toggle |

### 6.4 Hooks

| Hook | Description |
|---|---|
| `useAuth` | Firebase auth state + Firestore UserRecord; redirects on status change |
| `usePositions` | RTDB `/positions` live subscription → dashboardStore |
| `useAlerts` | RTDB `/alerts` live subscription → dashboardStore + criticalAlertStore diff for new critical alerts |
| `useAPHeartbeats` | RTDB `/ap_heartbeats` + 1s interval recompute → online/offline per MAC |
| `useCCTVHeartbeats` | RTDB `/cctv_heartbeats` + 1s interval recompute → online/offline per MAC |

---

## 7. Data Flow: BLE → Backend → Frontend

```
[Guard/Worker/Forklift wears BLE beacon tag]
        ↓
[TP-Link Omada APs pick up RSSI from BLE broadcasts]
        ↓
        ├── SIMULATION PATH ──────────────────────────────────────
        │   POST /telemetry  (Authorization: Bearer header)
        │   { reporter_mac=person_id, person_id, person_type,
        │     label, readings: [{ap_mac, rssi, ap_x, ap_y}] }
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
              4. Resolve identity from beacon_registry.py
              5. Buffer reading per beacon across APs (2s window)
              6. When ≥3 APs report same beacon → emit OmadaTelemetryPayload
                 (reporter_mac = person_id for stable RTDB key)
        ↓
PositioningService.compute_position()
  1. RSSI → LDPL distance per AP
  2. Multilateration (≥3 APs, numpy.linalg.lstsq) → raw (x, y) metres
  3. Clamp to floor bounds
  4. KalmanService.update(x, y) → smoothed (x, y), velocity (vx, vy)
  5. KalmanService.predict_ahead(3) → collision candidate (px, py)
  6. pixel_x/y = x/y × scale_pixels_per_meter
  7. zone = coordinate_to_zone(x, y) via ZoneRepository
  8. RTDB /positions/{mac_underscores} ← save PositionRecord
        ↓
SafetyService.run_all_checks()
  ├─ check_man_down(current)
  │    stale timestamp? → RTDB /alerts ← AlertRecord (man_down)
  │    30s suppression via _last_man_down dict
  └─ check_collision(all_positions)
       predicted positions converge? → RTDB /alerts ← AlertRecord (collision, other_person_id)
       30s suppression via _last_collision dict per worker|forklift pair
        ↓
[Firebase RTDB pushes to all connected Next.js clients instantly]
        ↓
useAlerts() RTDB onValue listener
  ├─ dashboardStore.setAlerts(data)        → AlertList + AlertCard update
  └─ criticalAlertStore.addCritical(alert) → CriticalAlertBanner if man_down/collision

usePositions() RTDB onValue listener
  └─ dashboardStore.setPositions(data)     → FloorMap WorkerMarker update

[Simulation tick (patrol or safety-events mode)]
  └─ POST /telemetry with synthetic RSSI → same pipeline as real hardware

[Patrol checkpoint reached]
  PatrolLogRecord written → Firestore patrol_logs
  SafetyService.check_patrol_compliance() → optional patrol_violation alert
  SafetyService.verify_multimodal()       → optional ghost_patrol alert

[Admin generates patrol report]
  POST /reports/generate { log_id, guard_id }
  ├─ Firestore patrol_logs → patrol summaries
  ├─ RTDB /alerts filtered by guard_id → alert summaries
  ├─ RAGService.get_context() (stubbed)
  ├─ LLMService._build_prompt() + provider.generate()
  └─ Firestore audit_reports ← AuditReportRecord (report_type: "patrol")

[Admin generates safety event report]
  POST /reports/generate-safety { person_id, date_str }
  ├─ RTDB /alerts filtered by person_id + date → alert summaries
  ├─ LLMService._build_safety_prompt() + provider.generate()
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
| `/cctv_heartbeats/{mac_underscores}` | `{ last_seen, mac, device_name }` | On VIGI detection event |

> **RTDB `/positions/` key**: derived from `reporter_mac`, which both paths set to `person_id` — simulation writes `sim-guard-001` etc., the real phone writes `guard-001`. These are disjoint namespaces (see §9 "Sim/Real Namespace Isolation"). person_id values contain no colons, so `.replace(":", "_")` is a no-op but kept for consistency.
>
> **RTDB key format**: AP/CCTV heartbeat keys always use underscores — `AA_BB_CC_DD_EE_01`. Always `mac.replace(":", "_")` before constructing those RTDB paths.

### Firestore — persistent, queryable

| Collection | Data |
|---|---|
| `users` | UserRecord |
| `buildings` | BuildingRecord |
| `floors` | FloorRecord (includes patrol_enabled, patrol_route, image dimensions) |
| `aps` | APRecord (includes x_m, y_m real-world coordinates) |
| `cctvs` | CCTVRecord |
| `zones` | ZoneRecord |
| `patrol_logs` | PatrolLogRecord |
| `audit_reports` | AuditReportRecord (report_type: patrol / safety_event) |
| `feedback` | FeedbackRecord (reserved for RAG when re-enabled) |
| `accuracy_metrics` | AccuracyMetricsRecord |

### Storage

| Path | Content |
|---|---|
| `floor_plans/{user_id}/{timestamp}_{filename}` | Floor plan images |

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
`_last_collision: Dict[str, str]` in `safety_service.py` tracks the last alert timestamp per `"worker_id|forklift_id"` pair. A new alert only fires if 30 seconds have elapsed since the last one — preventing 20+ duplicate alerts per collision segment.

### Critical Alert Banner vs. Toast
man_down and collision alerts are safety emergencies that require immediate operator attention. They are surfaced via a persistent `CriticalAlertBanner` (fixed top-centre, manual dismiss, stacks, amber glow) — separate from the auto-dismiss toast system used for routine UI feedback like report generation success.

### Per-Guard Shift Tracking
Each simulated beacon maintains its own `shift_id`, `loops_completed`, and `checkpoints_this_loop` counters. There is no global shift state. `checkpoints_this_loop` is always initialised to 0 — never pre-filled — ensuring all N checkpoints must be visited before a shift rotation.

### Patrol Route on Active Floor Only
Both simulation modes and the safety service only operate on the single active floor per building. Non-active floors have zero effect on positioning or safety checks. This allows multi-floor buildings to be managed without cross-floor interference.

### Two Report Types — Unified Renderer
`AuditReportRecord` carries `report_type: "patrol" | "safety_event"`. Existing Firestore docs without the field default to patrol via frontend fallback check (`!r.report_type || r.report_type === "patrol"`). Both types share the same `SimpleMarkdown` renderer and detail panel.

### Multi-Modal Ghost Patrol Detection
Ghost patrol alerts combine BLE beacon detection (Omada) with VIGI camera confirmation. An alert fires **only** when the BLE tag IS present but VIGI does NOT confirm a human — detecting tag-without-person scenarios (left badge, proxy patrol). The reverse (VIGI detects human but no BLE) does not fire.

### AP Delete Cascade
Deleting an AP triggers: Firestore AP doc delete → RTDB heartbeat path delete → simulation module AP removal → patrol route cleanup (strips deleted AP ID from `floor.patrol_route` and writes back). All in a single `floor_service.delete_ap()` call.

### Pluggable LLM Provider
A single env var (`LLM_PROVIDER`) switches the underlying model without code changes. `LLM_MODEL_NAME` must be set explicitly — raises `KeyError` if missing rather than silently using a wrong model. The factory pattern dispatches to Gemini, OpenAI, Claude, or Ollama — all implementing the same `BaseLLMProvider` interface.

### iBeacon Identity over MAC for Real Devices
Phone BLE MACs rotate every ~15 minutes for privacy. Keying beacon identity on `reported[].mac` (Omada's field) causes the position node to rotate and the Kalman filter to reset every rotation cycle. The adapter instead keys on the stable iBeacon triple `uuid:major:minor` set in nRF Connect (or burned into a Minew beacon). The RTDB position key is then derived from `person_id` (e.g. `guard-001`), which never changes — the marker persists and the Kalman filter accumulates history correctly.

### Sim/Real Namespace Isolation
All simulated `person_id` values are prefixed `sim-` (`sim-guard-001`, etc.). The real beacon registry uses bare IDs (`guard-001`). Both paths set `reporter_mac = person_id`, so simulation writes to `/positions/sim-guard-001` and the real phone writes to `/positions/guard-001` — completely disjoint. Simulation startup-clears target only `sim-` keys. Running a simulation while the real phone is tracking cannot overwrite or delete the real guard's position, patrol logs, or alerts.

---

## 9b. Known Issues & Pending Work

These are live items as of the current build — not yet resolved. Listed so the system is not mistaken for fully complete.

### Real-RSSI marker placement (active blocker)
Real RSSI flows end-to-end (3 Omada APs → `/telemetry/omada` → positioning → `/positions/guard-001`), the marker renders, and the phone shows in the sidebar. However, the marker currently lands in the **top-left corner** of the floor map. Root cause is **stale calibration after a floor-plan swap**: the active floor's `scale_pixels_per_meter` and the placed APs' `x_m/y_m` coordinates belong to a *previous* floor plan image, so multilateration collapses toward the origin. **Resolution:** recalibrate the scale on the floor plan actually in use, and re-place the 3 APs on it. (Open question to confirm: whether a *new floor record* was created, or the *image was swapped on the existing record* — the latter means the app allowed an image swap without invalidating calibration, which should be guarded against.)

### Man-down detection when simulation/telemetry stops
`check_man_down` only runs when a telemetry packet arrives. If the simulation (or real feed) stops, beacon positions freeze in RTDB and no staleness check ever fires — so a man-down that begins after the feed stops is never detected. **Planned fix:** a FastAPI background task (asyncio + lifespan) running every ~60s that scans RTDB `/positions` and fires man-down for stationary non-forklift beacons independently of telemetry arrival. Touches `main.py` (lifespan task) and `safety_service.py` (add `check_man_down_stale()`).

### RAG re-enable
RAG is stubbed: `rag_service.get_context()` returns `""` because `google-generativeai==0.7.2` routes `embed_content` through v1beta where `text-embedding-004` is unavailable. Audit reports work without it. (Also tracked in §4.3.)

### Beacon management UI (future)
Beacon identity currently lives in code (`config/beacon_registry.py`), keyed by iBeacon `uuid:major:minor`. Future work promotes this to a Firestore `beacons` collection + `beacon_repository` + CRUD route + dashboard UI + RTDB last-detected online/offline indicator, mirroring the AP/CCTV pattern. The registration form should accept EITHER a MAC (stable-MAC Minew beacons) OR an iBeacon `uuid/major/minor` (rotating-MAC phones). The identity-matching logic does not change — only the identity *source* swaps from file to Firestore.

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

# LLM — LLM_MODEL_NAME required; raises KeyError if missing
LLM_PROVIDER=gemini
LLM_MODEL_NAME=gemini-3.1-flash-lite
GEMINI_API_KEY=AIza...
ANTHROPIC_API_KEY=sk-ant-...      # if LLM_PROVIDER=claude
OPENAI_API_KEY=sk-...             # if LLM_PROVIDER=openai
OLLAMA_HOST=http://localhost:11434 # if LLM_PROVIDER=ollama

# Telemetry ingest
OMADA_ACCESS_TOKEN=your-omada-bearer-token

# Positioning
TX_POWER_DEFAULT=-59
PATH_LOSS_EXPONENT=2.5
RSSI_NOISE_STD=3.0

# Safety thresholds
MAN_DOWN_MINUTES=5
MAN_DOWN_MOVEMENT_THRESHOLD=1.0
COLLISION_ALERT_SECONDS=3
MIN_DWELL_SECONDS=30

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

NEXT_PUBLIC_BACKEND_URL=http://localhost:8000
```

---

*SKYE Sentinel-AI · Authorised Access Only*