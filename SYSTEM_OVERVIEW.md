# SKYE Sentinel-AI — System Overview

> Autonomous Industrial Safety & Semantic Patrol Intelligence System

---

## Table of Contents

1. [Architecture Summary](#1-architecture-summary)
2. [Backend](#2-backend)
3. [Frontend](#3-frontend)
4. [Data Flow](#4-data-flow-ble--backend--frontend)
5. [Firebase Usage](#5-firebase-usage)
6. [Key Design Decisions](#6-key-design-decisions)
7. [Environment Variables](#7-environment-variables)

---

## 1. Architecture Summary

```
Omada WiFi APs (BLE beacons) → POST /telemetry
                                    ↓
              PositioningService + SafetyService
               RSSI → LDPL → Multilateration → Kalman
                                    ↓
                    Firebase Realtime DB (/positions, /alerts)
                                    ↓
               Next.js Frontend (live onValue subscriptions)
                                    ↓
                   Admin Dashboard (map · alerts · reports)
```

**Stack:**
- Backend: Python FastAPI + Firebase Admin SDK
- Frontend: Next.js 14 (App Router) + TypeScript + Tailwind CSS
- Database: Firebase Realtime DB (live) + Firestore (persistent) + Storage (images)
- Auth: Firebase Auth (email/password + Google OAuth)
- AI: Google Gemini 2.5-flash (audit reports + zone detection) + Google text-embedding-004 (RAG)
- LLM Abstraction: Pluggable providers — Gemini · OpenAI · Claude · Ollama (env-var switch)

---

## 2. Backend

### 2.1 Application Setup (`main.py`)

- FastAPI app: `SKYE Sentinel-AI v0.1.0`
- Firebase Admin SDK initialised with RTDB URL on startup
- Middleware: CORS (all origins), `RequestLogger`, global `error_handler`
- Route prefixes registered:
  - `/auth` — public
  - `/telemetry` — Omada Bearer token
  - `/alerts`, `/users` — Firebase ID token
  - `/buildings`, `/floors`, `/zones` — Firebase ID token
  - `/floor-plans` — Firebase ID token (legacy; kept for backward compat)
  - `/reports` — Firebase ID token (admin only)

---

### 2.2 Routes

#### Auth — PUBLIC
| Method | Path | Description |
|---|---|---|
| POST | `/auth/register` | Create Firebase Auth account + Firestore user doc. First user → admin. Others → pending. |
| POST | `/auth/google` | Verify Google ID token, upsert Firestore user doc. |

#### Telemetry — Omada Bearer token
| Method | Path | Description |
|---|---|---|
| POST | `/telemetry` | Main positioning pipeline. RSSI → distances → multilateration → Kalman → RTDB + safety checks. |

#### Alerts — require_auth / require_admin
| Method | Path | Description |
|---|---|---|
| GET | `/alerts` | All alerts from RTDB. |
| POST | `/alerts/{alert_id}/feedback` | Submit feedback (confirmed/fixed/false_alarm). Resolves in RTDB + persists to Firestore for RAG. |

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
| GET | `/buildings` | All buildings for the authenticated user. |
| POST | `/buildings` | Create a new building. |
| PATCH | `/buildings/{building_id}` | Rename/update building. |
| DELETE | `/buildings/{building_id}` | Delete building (cascades to floors + zones). |

#### Floors — require_auth
| Method | Path | Description |
|---|---|---|
| GET | `/buildings/{building_id}/floors` | All floors for a building. |
| POST | `/buildings/{building_id}/floors` | Upload floor plan image → Storage → create Firestore doc. |
| PATCH | `/buildings/{building_id}/floors/{floor_id}/scale` | Set pixels-per-metre calibration. |
| PATCH | `/buildings/{building_id}/floors/{floor_id}/activate` | Activate this floor; deactivates all others in building. |
| DELETE | `/buildings/{building_id}/floors/{floor_id}` | Delete floor + Storage image + zones. |

#### Zones — require_auth
| Method | Path | Description |
|---|---|---|
| GET | `/buildings/{building_id}/floors/{floor_id}/zones` | All zones for a floor. |
| POST | `/buildings/{building_id}/floors/{floor_id}/zones` | Create a zone (name, color, bounds, is_high_risk). |
| PATCH | `/buildings/{building_id}/floors/{floor_id}/zones/{zone_id}` | Update zone properties. |
| DELETE | `/buildings/{building_id}/floors/{floor_id}/zones/{zone_id}` | Delete a zone. |
| POST | `/buildings/{building_id}/floors/{floor_id}/zones/ai-detect` | Gemini Vision auto-detect zones from floor plan image. |

#### Floor Plans — require_admin (legacy)
| Method | Path | Description |
|---|---|---|
| GET | `/floor-plans` | All floor plans for a user. |
| POST | `/floor-plans` | Create floor plan metadata post-upload. |
| PATCH | `/floor-plans/{id}/scale` | Update calibration. |
| PATCH | `/floor-plans/{id}/activate` | Activate plan. |

#### Reports — require_admin
| Method | Path | Description |
|---|---|---|
| POST | `/reports/generate` | Trigger Gemini audit report for a shift (with RAG context). |

---

### 2.3 Models

| Model | Key Fields |
|---|---|
| `UserRecord` | uid, email, display_name, role (admin/user), status (pending/approved/suspended), person_id, created_at |
| `PositionRecord` | beacon_mac, person_id, person_type (guard/worker/forklift), x, y, zone, timestamp, predicted_x/y, pixel_x/y, is_stationary |
| `AlertRecord` | alert_id, alert_type, person_id, zone, timestamp, resolved |
| `BuildingRecord` | id, name, description, user_id, created_at |
| `FloorRecord` | id, building_id, name, floor_number, url, storage_path, is_active, uploaded_at, scale_pixels_per_meter |
| `ZoneRecord` | id, floor_plan_id, name, color (hex+alpha), is_high_risk, x_min/max, y_min/max, created_at, created_by |
| `FloorPlanRecord` | floor_plan_id, user_id, name, url, storage_path, uploaded_at, is_active, scale_pixels_per_meter (legacy) |
| `PatrolLogRecord` | log_id, guard_id, checkpoint_id, checkpoint_name, expected_arrival, actual_arrival, dwell_time_seconds, min_dwell_required, ble_detected, vigi_detected, compliant, shift_id |
| `FeedbackRecord` | feedback_id, alert_id, alert_type, zone, feedback, timestamp, feedback_reason, shift_id |
| `AuditReportRecord` | report_id, shift_id, generated_at, patrol_summary, alert_summary, rag_examples_used, report_text, model_used |
| `AccuracyMetricsRecord` | metrics_id, run_id, shift_id, recorded_at, mean_position_error_m, rmse_m, alert_precision, alert_recall, kalman_improvement_pct, ap_count |

Alert types: `man_down` · `collision` · `ghost_patrol` · `patrol_violation`  
Feedback values: `confirmed` · `fixed` · `false_alarm`

---

### 2.4 Services

#### PositioningService
Full BLE → position pipeline per telemetry packet:
1. RSSI readings → distances via Log-Distance Path Loss (LDPL)  
   `distance = 10^((TX_POWER - RSSI) / (10 × PATH_LOSS_EXPONENT))`
2. Least-squares multilateration (requires ≥ 3 AP readings) → raw (x, y) in metres
3. `KalmanFilter.update()` → smoothed (x, y) + velocity (vx, vy)
4. `KalmanFilter.predict_ahead(3s)` → projected position for collision detection
5. Pixel conversion: metres × `scale_pixels_per_meter` (from active Floor)
6. Zone assignment via `coordinate_to_zone(x, y)`
7. Save to Realtime DB `/positions/{beacon_mac}`

#### SafetyService
- `check_man_down()` — Alert if beacon stationary in high-risk zone > `MAN_DOWN_MINUTES`
- `check_collision()` — Alert when worker and forklift predicted positions converge within threshold
- `check_patrol_compliance()` — Alert if guard missed checkpoint or dwell_time < min_dwell_required
- `verify_multimodal()` — Ghost patrol: alert when BLE tag present but VIGI does NOT confirm human
- `run_all_checks()` — Called after every telemetry packet; runs man-down + collision

#### AlertService
- `get_all()` — All alerts from RTDB
- `submit_feedback(alert_id, feedback, reason)` — Mark resolved in RTDB + persist to Firestore

#### UserService
- `register()`, `register_google()` — Create/upsert user
- `get_all()`, `get_pending()` — Query users
- `update_role()`, `update_status()` — Admin operations
- `delete(uid)` — Delete Firebase Auth + Firestore doc

#### BuildingService
- `get_all(user_id)`, `create()`, `update()`, `delete()` — Building CRUD

#### FloorService
- `get_all(building_id)`, `create()`, `update_scale()`, `set_active()`, `delete()` — Floor CRUD + activation

#### ZoneService
- `get_zones(floor_id)`, `create()`, `update()`, `delete()` — Zone CRUD
- `ai_detect(floor_id, image_url)` — Gemini Vision generates zone suggestions from floor plan image

#### FloorPlanService (legacy)
- `get_all()`, `create()`, `update_scale()`, `set_active()` — Original single-floor plan management

#### LLMService
- `generate_report(shift_id, patrol_summaries, alert_summaries)` — Build prompt with RAG context → call active LLM provider → persist AuditReport to Firestore

#### RAGService
- `get_context(query, alert_type)` — Hybrid retrieval:
  1. Pre-filter feedback by `alert_type` (rule-based)
  2. Semantic re-rank via Google `text-embedding-004` cosine similarity
  3. Return top-3 most similar past incidents as report context

#### KalmanService
- `update(x, y)` — Apply measurement, return smoothed (x, y)
- `predict_ahead(seconds)` — Project state forward for collision prediction

#### SimulationService
- Generates synthetic RSSI telemetry and patrol log data for testing

---

### 2.5 LLM Provider Abstraction

```
LLM_PROVIDER env var
      │
      ├── "gemini"  → GeminiProvider   (google-generativeai)
      ├── "openai"  → OpenAIProvider   (openai SDK)
      ├── "claude"  → ClaudeProvider   (anthropic SDK)
      └── "ollama"  → OllamaProvider   (local Ollama endpoint)
```

All providers implement `BaseLLMProvider.complete(prompt: str) → str`.  
The `llm_factory.get_llm_provider()` factory reads `LLM_PROVIDER` and instantiates the correct class.

---

### 2.6 Repositories

| Repository | Storage | Key Methods |
|---|---|---|
| `PositionRepository` | RTDB `/positions` | save, get, get_all, delete |
| `AlertRepository` | RTDB `/alerts` | save, get, get_all, mark_resolved |
| `UserRepository` | Firestore `users` | create, get_by_uid, get_all, get_pending, update_role, update_status, delete |
| `FeedbackRepository` | Firestore `feedback` | save, get_by_alert_type, get_by_zone |
| `BuildingRepository` | Firestore `buildings` | create, get_all, update, delete |
| `FloorRepository` | Firestore `floors` | save, get_all, get_active, update_scale, set_active, delete |
| `ZoneRepository` | Firestore `zones` | save, get_by_floor, update, delete |
| `FloorPlanRepository` | Firestore `floor_plans` | save, get_all, get_active, update_scale, set_active (legacy) |
| `PatrolLogRepository` | Firestore `patrol_logs` | save, get, get_by_shift, get_by_guard |
| `AuditReportRepository` | Firestore `audit_reports` | save, get, get_all, get_by_shift |
| `AccuracyMetricsRepository` | Firestore `accuracy_metrics` | save, get_by_run, get_by_shift |

---

### 2.7 Middleware

```
require_auth(Authorization: Bearer <Firebase ID token>)
  → verify_id_token() → get user from Firestore
  → reject if status == "pending" (403) or "suspended" (403)
  → return UserRecord

require_admin(user: UserRecord = Depends(require_auth))
  → reject if role != "admin" (403)
  → return UserRecord

verify_omada_token(Authorization: Bearer <Omada token>)
  → validates static token from OMADA_ACCESS_TOKEN env var
```

---

## 3. Frontend

### 3.1 Pages

| Route | Access | Purpose |
|---|---|---|
| `/` | Public | Redirects to `/dashboard` |
| `/login` | Public | Email/password + Google sign-in |
| `/register` | Public | Account creation (first = admin, others = pending) |
| `/pending-approval` | Pending users | Waiting for admin approval message |
| `/suspended` | Suspended users | Account suspended message |
| `/dashboard` | Admin | Live map + KPI stats + active alerts |
| `/dashboard/alerts` | Admin | All alerts + feedback form |
| `/dashboard/reports` | Admin | Generate + view AI audit reports |
| `/dashboard/users` | Admin | Approve/suspend/promote/remove users |
| `/dashboard/floor-plans` | Admin | Buildings → Floors → Zones management |

---

### 3.2 Layout & Routing

**`/dashboard/layout.tsx`**
- Uses `useAuth()` — redirects unauthenticated → `/login`
- Renders: `Navbar` + `Sidebar` (collapsible) + `ToastContainer`
- Mounts `DataSubscriptions` (positions + alerts real-time hooks)
- Wraps in `ThemeProvider` (dark/light mode toggle)

---

### 3.3 Components

**Layout**
- `Navbar` — Logo, SKYE wordmark, page title, user avatar, dark mode toggle, sign-out
- `Sidebar` — Collapsible nav: Dashboard, Alerts, Reports, Floor Plans, Users. Amber pending badge on Users link (live Firestore count). Personnel live list at bottom.
- `ThemeProvider` — Dark/light mode context via `themeStore`

**Dashboard**
- `StatsRow` — KPI cards: active alerts count, active workers, floors, zones
- `FloorMapArea` — Floor selector + `FloorMap` + `WorkerMarker` rendering

**Map**
- `FloorMap` — Renders active floor plan image, draws zone overlays, places worker markers
- `WorkerMarker` — Animated position dot, coloured by person_type (guard/worker/forklift)
- `CalibrationTool` — Mark two reference points on the floor plan → compute `scale_pixels_per_meter`
- `ZoneEditor` — Full drag-to-create / resize / move zone editor; colour picker; is_high_risk toggle; AI detection trigger button; connects to Gemini Vision for auto zone suggestions

**Alerts**
- `AlertList` — Filterable, scrollable list of alerts
- `AlertCard` — Type badge, zone, person_id, timestamp, resolved state
- `FeedbackForm` — Radio (confirmed/fixed/false_alarm), reason textarea, submit

**Floor Plans**
- `FloorPlanList` — Buildings → Floors tabbed interface with activate/delete actions
- `FloorPlanUpload` — File input → Firebase Storage upload → create Floor doc
- `FloorPlanModal` — Metadata modal (rename, delete, activate actions)

**Reports**
- `ReportCard` — Rendered audit report: markdown text, model used, timestamp
- `GenerateReportButton` — Trigger report generation with shift_id

**Shared**
- `LoadingSpinner` / `FullScreenLoader`
- `StatusBadge` — pending / approved / suspended
- `AlertTypeBadge` — man_down / collision / ghost_patrol / patrol_violation
- `SkeletonCard` — Loading placeholder
- `ToastContainer` — Auto-dismiss success/error/info toasts

---

### 3.4 Services

| Service | Transport | Key Functions |
|---|---|---|
| `authService` | Firebase SDK | signIn, signOut, onAuthChanged, signInWithGoogle |
| `userService` | Firestore + API | getUserRecord, registerUser, getUsers, updateUserStatus, updateUserRole, deleteUser, subscribeToPendingCount |
| `buildingService` | Firestore + API | createBuilding, renameBuilding, deleteBuilding |
| `floorService` | Firestore + Storage + API | uploadFloor, activateFloor, deactivateFloor, deleteFloor, renameFloor |
| `zoneService` | Firestore + API | createZone, updateZone, deleteZone, aiDetectZones |
| `alertService` | RTDB + API | subscribeToAlerts, submitFeedback |
| `positionService` | RTDB | subscribeToPositions, unsubscribeFromPositions |
| `floorPlanService` | Firestore + Storage + API | legacy floor plan operations |
| `reportService` | API | generateReport, subscribeToReports |
| `patrolLogService` | API | getPatrolLogs, getDistinctShifts |

---

### 3.5 Hooks

| Hook | Returns | Description |
|---|---|---|
| `useAuth` | `{ user, userRecord, isLoading }` | Firebase auth state + Firestore UserRecord |
| `usePositions` | `{ positions, isLoading }` | RTDB live subscription → updates dashboardStore |
| `useAlerts` | `{ alerts, isLoading }` | RTDB live subscription → updates dashboardStore |
| `useBuildings` | `{ buildings, isLoading }` | All buildings for current user |
| `useFloors` | `{ floors, isLoading }` | Floors for a building, with active state |
| `useFloorPlan` | `{ floorPlan }` | Active floor plan (legacy) |
| `useZones` | `{ zones, isLoading }` | Live zones for a floor |

---

### 3.6 Stores (Zustand)

**`dashboardStore`**
```typescript
{
  positions:         Record<beacon_mac, PositionRecord>
  alerts:            Record<alert_id, AlertRecord>
  selectedWorkerId:  string | null
  activeShiftId:     string | null
  cachedReports:     AuditReportRecord[]
  cachedUsers:       UserRecord[]
  cachedBuildings:   BuildingRecord[]
}
```

**`themeStore`**
```typescript
{ isDarkMode: boolean }
```

**`toastStore`**
```typescript
{ toasts: Toast[] }
// toast.success(), toast.error(), toast.info() — auto-dismiss
```

---

### 3.7 Types

| Type | Key Fields |
|---|---|
| `UserRecord` | uid, email, display_name, role, status, person_id, created_at |
| `PositionRecord` | beacon_mac, person_id, person_type, x, y, zone, timestamp, predicted_x/y, pixel_x/y, is_stationary |
| `AlertRecord` | alert_id, alert_type, person_id, zone, timestamp, resolved |
| `BuildingRecord` | id, name, description, user_id, created_at |
| `FloorRecord` | id, building_id, name, floor_number, url, storage_path, is_active, uploaded_at, scale_pixels_per_meter |
| `ZoneRecord` | id, floor_plan_id, name, color, is_high_risk, x_min/max, y_min/max, created_at, created_by |
| `FloorPlanRecord` | floor_plan_id, user_id, name, url, uploaded_at, is_active, scale_pixels_per_meter |
| `PatrolLogRecord` | log_id, guard_id, checkpoint_id, checkpoint_name, expected_arrival, actual_arrival, dwell_time_seconds, min_dwell_required, ble_detected, vigi_detected, compliant, shift_id |
| `AuditReportRecord` | report_id, shift_id, generated_at, patrol_summary, alert_summary, rag_examples_used, report_text, model_used |

---

## 4. Data Flow: BLE → Backend → Frontend

```
[Guard/Worker wears BLE tag]
        ↓
[TP-Link Omada WiFi APs pick up RSSI broadcasts]
        ↓
POST /telemetry  (Omada Bearer token)
  payload: { reporter_mac, person_id, person_type, readings: [{ap_mac, rssi, ap_x, ap_y}] }
        ↓
PositioningService.compute_position()
  1. RSSI → LDPL distance per AP
  2. Multilateration (≥3 APs) → (x, y) metres
  3. Kalman filter → smoothed (x, y), velocity (vx, vy)
  4. predict_ahead(3s) → collision candidate position
  5. pixel_x, pixel_y = x,y × scale_pixels_per_meter (from active Floor)
  6. zone = coordinate_to_zone(x, y)
  7. RTDB /positions/{beacon_mac} ← save
        ↓
SafetyService.run_all_checks()
  ├─ man_down?    → RTDB /alerts/{id} ← save
  └─ collision?   → RTDB /alerts/{id} ← save
        ↓
[Firebase RTDB pushes to all connected clients instantly]
        ↓
Frontend — onValue listeners
  ├─ /positions → dashboardStore.positions → FloorMap WorkerMarkers update
  └─ /alerts    → dashboardStore.alerts    → AlertList updates

[Admin submits feedback]
  POST /alerts/{id}/feedback
  ├─ RTDB mark_resolved   → live alert disappears from dashboard
  └─ Firestore feedback/  → persisted for RAG

[Admin generates shift report]
  POST /reports/generate
  ├─ RAGService.get_context() → top-3 similar past incidents (text-embedding-004 cosine similarity)
  ├─ LLMService builds prompt + calls active provider (default: Gemini 2.5-flash)
  └─ Firestore audit_reports/ ← save generated report

[Admin manages floor plans]
  Buildings → Floors → Zones hierarchy
  ├─ Floor plan image → Firebase Storage
  ├─ CalibrationTool → scale_pixels_per_meter
  ├─ ZoneEditor → drag-to-create zones with color + risk flags
  └─ AI Detect button → POST /zones/ai-detect → Gemini Vision → zone suggestions
```

---

## 5. Firebase Usage

### Realtime Database — live, ephemeral

| Path | Data | Update Frequency |
|---|---|---|
| `/positions/{beacon_mac}` | PositionRecord | Every telemetry packet (~1–2s) |
| `/alerts/{alert_id}` | AlertRecord | On safety event detection |

### Firestore — persistent, queryable

| Collection | Data | Key Queries |
|---|---|---|
| `users` | UserRecord | by uid, by status=="pending" |
| `buildings` | BuildingRecord | by user_id |
| `floors` | FloorRecord | by building_id, by is_active==true |
| `zones` | ZoneRecord | by floor_plan_id |
| `feedback` | FeedbackRecord | by alert_type, by zone (for RAG) |
| `floor_plans` | FloorPlanRecord | by user_id, by is_active==true (legacy) |
| `patrol_logs` | PatrolLogRecord | by shift_id, by guard_id |
| `audit_reports` | AuditReportRecord | by shift_id |
| `accuracy_metrics` | AccuracyMetricsRecord | by run_id, by shift_id |

### Storage — binary files

| Path | Content |
|---|---|
| `floor_plans/{user_id}/{timestamp}_{filename}` | Floor plan images |

---

## 6. Key Design Decisions

### Multi-Floor Hierarchy
The system organises floor plans as: **Building → Floors → Zones**. Each building can have multiple floors; each floor can have multiple named zones (with risk flags and colors). One floor per building can be "active" — only the active floor's zones are used for positioning and safety checks. This replaced the original flat `FloorPlan` model.

### Dual Database Strategy
Realtime DB for **live, ephemeral** data (positions, alerts) — instant frontend streaming.  
Firestore for **persistent, queryable** data (users, buildings, floors, zones, feedback, logs) — historical records and RAG.

### Kalman Smoothing + Collision Prediction
A 2D Kalman filter (state: x, y, vx, vy) smooths noisy RSSI-based positions and estimates velocity. The filter projects each tracked entity 3 seconds ahead to warn of collisions before impact occurs.

### AI Zone Detection
The `ZoneEditor` component includes an "AI Detect" button that sends the floor plan image URL to `POST /zones/ai-detect`. The backend calls Gemini Vision to analyse the image and returns suggested zone bounding boxes, names, and risk flags — reducing manual zone configuration.

### RAG-Augmented Report Generation
Audit reports are grounded in real past incidents. The LLM service fetches the top-3 semantically similar historical feedback records from Firestore (pre-filtered by alert type, then re-ranked by `text-embedding-004` cosine similarity) and injects them into the Gemini prompt.

### Pluggable LLM Provider
A single env var (`LLM_PROVIDER`) switches the underlying model without code changes. The factory pattern (`llm_factory.get_llm_provider()`) dispatches to Gemini, OpenAI, Claude, or Ollama — all implementing the same `BaseLLMProvider` interface.

### Multi-Modal Ghost Patrol Detection
Ghost patrol alerts combine BLE beacon detection (Omada) with VIGI camera confirmation. An alert fires only when the BLE tag is present **but** VIGI does NOT confirm a human — detecting tag-without-person scenarios (left badge, proxy).

### No Auto Sign-In After Register
After registration the user is redirected to `/login?registered=admin` (first user) or `/pending-approval`. The backend creates the Firebase Auth account server-side; auto-sign-in was causing race conditions with auth state listeners.

### Admin Self-Protection
Admins cannot suspend or demote their own account. Self-deletion requires a confirmation modal and immediately signs them out.

### Pending Badge
The sidebar Users link subscribes to Firestore `users` via `onSnapshot` filtered by `status=="pending"`. The count updates in real-time without polling.

### Accuracy Metrics Collection
A dedicated `AccuracyMetricsRecord` tracks per-run positioning accuracy (mean position error, RMSE, alert precision/recall, Kalman improvement %). Stored in Firestore `accuracy_metrics` for evaluation and reporting.

---

## 7. Environment Variables

### Backend (`backend/.env`)

```env
# Firebase
FIREBASE_KEY_PATH=./serviceAccountKey.json
FIREBASE_RTDB_URL=https://your-project-default-rtdb.firebaseio.com

# LLM
LLM_PROVIDER=gemini
LLM_MODEL_NAME=gemini-2.5-flash
GEMINI_API_KEY=AIza...
ANTHROPIC_API_KEY=sk-ant-...      # if LLM_PROVIDER=claude
OPENAI_API_KEY=sk-...             # if LLM_PROVIDER=openai
OLLAMA_HOST=http://localhost:11434 # if LLM_PROVIDER=ollama

# Telemetry ingest
OMADA_ACCESS_TOKEN=your-omada-bearer-token

# Positioning
TX_POWER_DEFAULT=-59
PATH_LOSS_EXPONENT=2.5

# Safety thresholds
MAN_DOWN_MINUTES=5
MAN_DOWN_MOVEMENT_THRESHOLD=1.0
COLLISION_ALERT_SECONDS=3
MIN_DWELL_SECONDS=30

# Simulation
RSSI_NOISE_STD=3.0

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

BACKEND_URL=http://localhost:8000
```

---

*SKYE Sentinel-AI · Authorised Access Only*
