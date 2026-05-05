# SKYE — System Overview

**Autonomous Industrial Safety & Semantic Patrol Intelligence System**

---

## Table of Contents

1. [Architecture Summary](#architecture-summary)
2. [Backend](#backend)
   - [Entry Point & Config](#entry-point--config)
   - [Routes](#routes)
   - [Services](#services)
   - [Repositories](#repositories)
   - [Models](#models)
   - [Providers (LLM)](#providers-llm)
   - [Utils](#utils)
   - [Middleware](#middleware)
3. [Frontend](#frontend)
   - [Pages](#pages)
   - [Components](#components)
   - [Hooks](#hooks)
   - [Services](#services-1)
   - [Stores](#stores)
   - [Types](#types)
4. [Firebase Split](#firebase-split)
5. [Data Flows](#data-flows)
6. [Safety Features](#safety-features)
7. [Environment Variables](#environment-variables)
8. [File Tree](#file-tree)

---

## Architecture Summary

| Layer | Technology |
|---|---|
| Backend | Python 3.13 + FastAPI + Uvicorn |
| Frontend | Next.js 15 + React 18 + TypeScript |
| State | Zustand 4.5 |
| Realtime DB | Firebase Realtime Database (RTDB) |
| Persistent DB | Firestore |
| File Storage | Firebase Cloud Storage |
| Auth | Firebase Auth (email/password) |
| LLM | Pluggable — Gemini (default), OpenAI, Ollama, Claude |
| Positioning | BLE RSSI → LDPL → Multilateration → Kalman filter |

**Strict one-way layering (backend):**
```
Routes → Services → Repositories → Firebase
```

---

## Backend

### Entry Point & Config

| File | Purpose |
|---|---|
| `main.py` | FastAPI app factory — registers routers, CORS, request logger, Firebase Admin SDK init |
| `config/settings.py` | Dataclass config from env vars — Firebase URLs, LLM provider, safety thresholds, RSSI calibration |
| `requirements.txt` | Pinned deps — fastapi 0.111.1, firebase-admin 6.5.0, filterpy 1.4.5, numpy 2.1.3, scipy 1.14.1, pydantic 2.10.6 |

---

### Routes

| File | Endpoints |
|---|---|
| `routes/telemetry_routes.py` | `POST /telemetry` — accepts RSSI payload from Omada WiFi controller (Bearer token required); triggers positioning + safety checks |
| `routes/alert_routes.py` | `GET /alerts` — all alerts from RTDB; `POST /alerts/{alert_id}/feedback` — mark resolved in RTDB + save feedback to Firestore |
| `routes/report_routes.py` | `POST /reports/generate` — triggers LLM audit report for a given shift |
| `routes/floor_plan_routes.py` | `GET /floor-plans?user_id=`, `POST /floor-plans`, `PATCH /{id}/scale`, `PATCH /{id}/activate` |

---

### Services

| File | Responsibility |
|---|---|
| `services/positioning_service.py` | Full positioning pipeline: RSSI → LDPL distances → multilateration (least squares) → Kalman smoothing → predict 3s ahead → metres-to-pixels conversion → save to RTDB |
| `services/kalman_service.py` | 2D Kalman filter per beacon; state `[x, y, vx, vy]`; `update()` smooths position, `predict_ahead(seconds)` projects for collision detection; reduces error to ~1.2 m |
| `services/safety_service.py` | `check_man_down()` — stationary in high-risk zone > threshold; `check_collision()` — predicted positions converge within threshold; `check_patrol_compliance()` — missed checkpoint or short dwell; `verify_multimodal()` — BLE present but VIGI absent (ghost patrol) |
| `services/alert_service.py` | `get_all()` from RTDB; `submit_feedback()` — dual write: mark resolved in RTDB + save FeedbackRecord to Firestore |
| `services/llm_service.py` | Builds prompt with patrol logs + alerts + RAG context → calls LLM provider → saves AuditReportRecord to Firestore |
| `services/rag_service.py` | Hybrid RAG: rule-based pre-filter (same alert_type) → Google text-embedding-004 semantic re-rank → cosine similarity → top-3 examples injected into prompt |
| `services/floor_plan_service.py` | CRUD for floor plan metadata; `set_active()` deactivates others for same user_id; `update_scale()` validates > 0 |
| `services/simulation_service.py` | Generates synthetic telemetry and patrol log data for testing |

---

### Repositories

All repos interface with Firebase only. Services never call Firebase directly.

| File | Database | Collection / Path |
|---|---|---|
| `repositories/position_repository.py` | RTDB | `/positions/{beacon_mac}` |
| `repositories/alert_repository.py` | RTDB | `/alerts/{alert_id}` |
| `repositories/feedback_repository.py` | Firestore | `feedback` |
| `repositories/floor_plan_repository.py` | Firestore | `floor_plans` |
| `repositories/audit_report_repository.py` | Firestore | `audit_reports` |
| `repositories/patrol_log_repository.py` | Firestore | `patrol_logs` |
| `repositories/accuracy_metrics_repository.py` | Firestore | `accuracy_metrics` |

---

### Models

| File | Key Fields |
|---|---|
| `models/position.py` | `beacon_mac`, `person_id`, `person_type` (guard/worker/forklift), `x`, `y`, `zone`, `timestamp`, `predicted_x/y`, `pixel_x/y`, `is_stationary` |
| `models/alert.py` | `alert_id`, `alert_type` (man_down/collision/ghost_patrol/patrol_violation), `person_id`, `zone`, `timestamp`, `resolved` |
| `models/telemetry.py` | `OmadaTelemetryPayload`: `reporter_mac`, `timestamp`, `readings[]` (each: `ap_mac`, `rssi`, `ap_x`, `ap_y`), `person_id`, `person_type` |
| `models/patrol_log.py` | `log_id`, `guard_id`, `checkpoint_id/name`, `expected_arrival`, `actual_arrival`, `dwell_time_seconds`, `min_dwell_required`, `ble_detected`, `vigi_detected`, `compliant`, `shift_id` |
| `models/feedback.py` | `feedback_id`, `alert_id`, `alert_type`, `zone`, `feedback` (confirmed/fixed/false_alarm), `timestamp`, `feedback_reason`, `shift_id` |
| `models/floor_plan.py` | `floor_plan_id`, `user_id`, `name`, `url` (Storage), `uploaded_at`, `is_active`, `scale_pixels_per_meter` |
| `models/audit_report.py` | `report_id`, `shift_id`, `generated_at`, `patrol_summary`, `alert_summary`, `rag_examples_used[]`, `report_text`, `model_used` |

---

### Providers (LLM)

Pluggable via `LLM_PROVIDER` env var. All implement `BaseLLMProvider` ABC.

| File | Provider |
|---|---|
| `providers/base_llm_provider.py` | ABC — `generate(prompt) -> str`, `get_model_name() -> str` |
| `providers/llm_factory.py` | `get_llm_provider()` — reads `LLM_PROVIDER`, returns correct instance |
| `providers/gemini_provider.py` | Google Gemini (default, active) |
| `providers/openai_provider.py` | OpenAI ChatGPT |
| `providers/ollama_provider.py` | Ollama (local LLM) |
| `providers/claude_provider.py` | Anthropic Claude |

---

### Utils

| File | Purpose |
|---|---|
| `utils/multilateration.py` | `least_squares_position(ap_positions, distances)` → `(x, y)` using `np.linalg.lstsq`; requires ≥ 3 APs |
| `utils/rssi_utils.py` | RSSI → distance via Log Distance Path Loss model |
| `utils/zone_utils.py` | `coordinate_to_zone(x, y)` → zone name; 7 axis-aligned zones defined; high-risk: loading_bay, forklift_corridor, storage_rack_a/b |
| `utils/timestamp_utils.py` | ISO 8601 timestamp helpers |

---

### Middleware

| File | Purpose |
|---|---|
| `middleware/auth_middleware.py` | `verify_omada_token()` FastAPI dependency — validates Bearer token on `/telemetry` against `OMADA_ACCESS_TOKEN` config |
| `middleware/request_logger.py` | Logs incoming requests |
| `middleware/error_handler.py` | Global exception handlers |

---

## Frontend

### Pages

| Route | File | Description |
|---|---|---|
| `/` | `app/page.tsx` | Redirects to `/dashboard` |
| `/login` | `app/login/page.tsx` | Split-screen — 60% branding with feature list, 40% email/password form; auto-redirects if already authenticated |
| `/dashboard` | `app/dashboard/layout.tsx` + `page.tsx` | Auth guard + shell (Navbar, Sidebar, ToastContainer, DataSubscriptions); page shows StatsRow + FloorMapArea + active AlertList |
| `/dashboard/alerts` | `app/dashboard/alerts/page.tsx` | 40/60 split — AlertList with filter bar on left, FeedbackForm (or empty state) on right |
| `/dashboard/reports` | `app/dashboard/reports/page.tsx` | 35/65 split — shift selector + Generate button + report list on left; markdown report detail + copy button on right |
| `/dashboard/floor-plans` | `app/dashboard/floor-plans/page.tsx` | Floor plan upload, list, scale calibration, activate |

**Dashboard layout responsibilities (`app/dashboard/layout.tsx`):**
- Checks `useAuth()` and redirects unauthenticated users to `/login`
- Mounts `DataSubscriptions` — calls `usePositions()` + `useAlerts()` once, populates Zustand for all child pages
- Renders `Navbar`, collapsible `Sidebar`, `ToastContainer`

---

### Components

**Layout**
| File | Purpose |
|---|---|
| `components/layout/Navbar.tsx` | Top bar — SKYE amber logo, page title (from pathname), shift status badge, user initials, sign-out button |
| `components/layout/Sidebar.tsx` | Collapsible (240 px / 60 px) — nav links with inline SVG icons, amber active state, live personnel list from Zustand (colour-coded by role), system OPERATIONAL status |

**Map**
| File | Purpose |
|---|---|
| `components/map/FloorMap.tsx` | Renders floor plan image + SVG overlay; converts `pixel_x/y` (or metre fallback) to canvas coordinates; mounts ZoneOverlay + WorkerMarkers |
| `components/map/WorkerMarker.tsx` | Per-worker SVG marker — green (guard), blue (worker), amber (forklift); outer glow ring; dark tooltip |
| `components/map/ZoneOverlay.tsx` | SVG zone rectangles synced with `zone_utils.py`; danger fill (red 10% opacity), safe fill (green 6% opacity) |

**Dashboard**
| File | Purpose |
|---|---|
| `components/dashboard/StatsRow.tsx` | 4 stat cards — Active Personnel, Active Alerts (amber pulse if > 0), Patrol Compliance, Ghost Patrol Detections |
| `components/dashboard/FloorMapArea.tsx` | Wraps FloorMap; shows "No Floor Plan" empty state with upload CTA; FloorPlanModal for upload/change |

**Alerts**
| File | Purpose |
|---|---|
| `components/alerts/AlertList.tsx` | Filter bar + scrollable list of AlertCards; emits `onSelectAlert` |
| `components/alerts/AlertCard.tsx` | Single alert — AlertTypeBadge, person_id, zone, timestamp, ACTIVE/RESOLVED pill; animate-alert-pulse for man_down/collision |
| `components/alerts/FeedbackForm.tsx` | Radio cards (confirmed/fixed/false_alarm) + optional notes textarea; calls `alertService.submitFeedback()`; toast on result |

**Reports**
| File | Purpose |
|---|---|
| `components/reports/ReportCard.tsx` | Summary card — shift ID (amber), generated_at, model_used, text preview |
| `components/reports/GenerateReportButton.tsx` | Standalone generate trigger button |

**Floor Plans**
| File | Purpose |
|---|---|
| `components/floor-plans/FloorPlanModal.tsx` | Modal overlay — drag-drop zone, name input, progress bar, Cancel/Upload buttons |
| `components/floor-plans/FloorPlanList.tsx` | List with activate button + scale number input per plan |
| `components/floor-plans/FloorPlanUpload.tsx` | File picker + name input + upload to Firebase Storage + backend POST |

**Shared**
| File | Purpose |
|---|---|
| `components/shared/AlertTypeBadge.tsx` | Coloured badge per alert type — red (man_down/collision), amber (ghost_patrol), orange-600 (patrol_violation) |
| `components/shared/StatusBadge.tsx` | ACTIVE / RESOLVED pill |
| `components/shared/LoadingSpinner.tsx` | Full-screen and inline spinner variants |
| `components/shared/SkeletonCard.tsx` | Shimmer skeleton loading placeholder |
| `components/shared/ToastContainer.tsx` | Fixed bottom-right toast stack; slide-in; colour-coded border-l-2; auto-dismissed via toastStore |

---

### Hooks

| File | Returns |
|---|---|
| `hooks/useAuth.ts` | `{ user: User \| null, isLoading: boolean }` — subscribes to Firebase Auth state |
| `hooks/usePositions.ts` | Calls `subscribeToPositions()`, stores result in `dashboardStore` |
| `hooks/useAlerts.ts` | Calls `subscribeToAlerts()`, stores result in `dashboardStore` |
| `hooks/useFloorPlan.ts` | `useActiveFloorPlan()` → `{ floorPlan, isLoading }` — fetches active floor plan for current user |

---

### Services

| File | Responsibility |
|---|---|
| `services/authService.ts` | `signIn()`, `signOut()`, `onAuthChanged()` via Firebase Auth |
| `services/positionService.ts` | `subscribeToPositions()` / `unsubscribeFromPositions()` — RTDB `onValue` listener on `/positions` |
| `services/alertService.ts` | `subscribeToAlerts()` / `unsubscribeFromAlerts()` — RTDB `onValue` on `/alerts`; `submitFeedback()` → `POST /api/alerts/{id}/feedback` |
| `services/reportService.ts` | `subscribeToReports()` — Firestore `onSnapshot` on `audit_reports`; `generateReport()` → `POST /reports/generate` |
| `services/floorPlanService.ts` | `subscribeToFloorPlans()`, `subscribeToActiveFloorPlan()`, `uploadFloorPlan()` (Storage + backend POST), `updateScale()`, `activateFloorPlan()` |
| `services/patrolLogService.ts` | `getDistinctShifts()` — queries Firestore `patrol_logs`, deduplicates by `shift_id`, returns `ShiftOption[]` for report selector |

---

### Stores

| File | State |
|---|---|
| `store/dashboardStore.ts` | `positions: Record<string, PositionRecord>`, `alerts: Record<string, AlertRecord>`, `selectedWorkerId`, `activeShiftId`; setters for each |
| `store/toastStore.ts` | `toasts[]`; `addToast()` auto-dismisses after 4 s; exported helpers: `toast.success()`, `toast.error()`, `toast.info()` |

---

### Types

| File | Key Types |
|---|---|
| `types/alert.ts` | `AlertType`, `FeedbackValue`, `AlertRecord` |
| `types/position.ts` | `PositionRecord` (includes `pixel_x/y`, `predicted_x/y`) |
| `types/floorPlan.ts` | `FloorPlanRecord` |
| `types/auditReport.ts` | `AuditReportRecord` |
| `types/feedback.ts` | `FeedbackRecord` |
| `types/patrolLog.ts` | `PatrolLogRecord` |

---

## Firebase Split

| Data | Database | Why |
|---|---|---|
| `/positions/{beacon_mac}` | **RTDB** | Live, low-latency — streams to frontend in real-time |
| `/alerts/{alert_id}` | **RTDB** | Live — frontend subscribes, RTDB pushes on new alerts |
| `feedback` collection | **Firestore** | Queryable — RAG pipeline filters by alert_type, zone |
| `floor_plans` collection | **Firestore** | Structured — ordered queries, single-active constraint |
| `audit_reports` collection | **Firestore** | Structured — ordered by generated_at desc |
| `patrol_logs` collection | **Firestore** | Structured — queried by shift_id, guard_id |
| `accuracy_metrics` collection | **Firestore** | Structured — historical metrics |
| Floor plan images | **Cloud Storage** | Binary blob — accessed via download URL stored in Firestore |

---

## Data Flows

### 1. Real-time Position Tracking

```
Omada WiFi Controller
  → POST /telemetry (Bearer token)
    → positioning_service.compute_position()
        RSSI → LDPL distance
        Multilateration (np.linalg.lstsq, ≥3 APs)
        Kalman smoothing per beacon
        Predict 3s ahead (collision)
        Metres → pixels (floor plan scale, cached)
      → RTDB /positions/{beacon_mac}
    → safety_service.run_all_checks()
        check_man_down()
        check_collision()
      → RTDB /alerts/{alert_id}  (if triggered)

Frontend:
  positionService.subscribeToPositions()
    → RTDB onValue listener
      → dashboardStore.setPositions()
        → FloorMap re-renders markers
        → Sidebar updates personnel list
```

### 2. Alert Feedback

```
FeedbackForm.handleSubmit()
  → alertService.submitFeedback(alertId, feedback, reason)
    → POST /api/alerts/{alertId}/feedback
      → alert_service.submit_feedback()
          mark_resolved() → RTDB /alerts/{alertId}
          FeedbackRecord → Firestore /feedback
            (used by rag_service for future reports)
```

### 3. Audit Report Generation

```
ReportsPage: shift selector → handleGenerate()
  → reportService.generateReport({ shift_id, ... })
    → POST /reports/generate
      → llm_service.generate_report()
          rag_service.get_context()
            Firestore /feedback → rule-based pre-filter
            Google text-embedding-004 → cosine similarity
            Top-3 examples
          Build prompt (patrol logs + alerts + RAG)
          LLM provider (Gemini) → report_text
          AuditReportRecord → Firestore /audit_reports

Frontend:
  subscribeToReports() (Firestore onSnapshot)
    → ReportsPage list updates live
```

### 4. Floor Plan Calibration

```
FloorPlanUpload: user picks image + name
  → uploadToStorage() → Firebase Cloud Storage (URL)
  → POST /floor-plans { user_id, name, url }
    → floor_plan_service.create() → Firestore /floor_plans

User marks reference points on map → calculates scale
  → PATCH /floor-plans/{id}/scale { scale_pixels_per_meter }
    → floor_plan_service.update_scale() → Firestore
    → positioning_service.invalidate_scale_cache()

Next telemetry packet:
  positioning_service._get_scale() → Firestore (fresh)
  pixel_x = sx * scale, pixel_y = sy * scale
```

---

## Safety Features

| Feature | Trigger Condition | Alert Type |
|---|---|---|
| Man-Down Detection | Beacon stationary (< movement threshold) in high-risk zone for > `MAN_DOWN_MINUTES` | `man_down` |
| Collision Prediction | Worker + forklift Kalman-predicted positions converge within threshold in 3 s | `collision` |
| Patrol Compliance | Guard missed checkpoint or dwell_time < min_dwell_required | `patrol_violation` |
| Ghost Patrol Verification | BLE tag detected but VIGI (visual) camera absent at checkpoint | `ghost_patrol` |

**High-risk zones:** `loading_bay`, `forklift_corridor`, `storage_rack_a`, `storage_rack_b`

---

## Environment Variables

### Backend (`.env`)

| Variable | Description |
|---|---|
| `FIREBASE_KEY_PATH` | Path to service account JSON |
| `FIREBASE_RTDB_URL` | Realtime Database URL |
| `GEMINI_API_KEY` | Google Gemini API key |
| `ANTHROPIC_API_KEY` | Claude API key (if using claude provider) |
| `OPENAI_API_KEY` | OpenAI API key (if using openai provider) |
| `OLLAMA_HOST` | Ollama server URL (if using ollama provider) |
| `LLM_PROVIDER` | `gemini` \| `openai` \| `ollama` \| `claude` (default: `gemini`) |
| `LLM_MODEL_NAME` | e.g. `gemini-2.5-flash` |
| `OMADA_ACCESS_TOKEN` | Bearer token for telemetry endpoint |
| `PORT` | Uvicorn port (default: `8000`) |
| `MAN_DOWN_MINUTES` | Stationary threshold for man-down alert |
| `COLLISION_ALERT_SECONDS` | Prediction window for collision detection |

### Frontend (`.env.local`)

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_FIREBASE_API_KEY` | Firebase project API key |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | Firebase Auth domain |
| `NEXT_PUBLIC_FIREBASE_RTDB_URL` | Realtime Database URL |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | Firestore project ID |
| `NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET` | Cloud Storage bucket |
| `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID` | FCM sender ID |
| `NEXT_PUBLIC_FIREBASE_APP_ID` | Firebase App ID |

---

## File Tree

```
SKYE/
├── backend/
│   ├── main.py
│   ├── requirements.txt
│   ├── .env / .env.example
│   ├── config/
│   │   └── settings.py
│   ├── middleware/
│   │   ├── auth_middleware.py
│   │   ├── error_handler.py
│   │   └── request_logger.py
│   ├── models/
│   │   ├── accuracy_metrics.py
│   │   ├── alert.py
│   │   ├── audit_report.py
│   │   ├── feedback.py
│   │   ├── floor_plan.py
│   │   ├── patrol_log.py
│   │   ├── position.py
│   │   └── telemetry.py
│   ├── providers/
│   │   ├── base_llm_provider.py
│   │   ├── llm_factory.py
│   │   ├── gemini_provider.py
│   │   ├── openai_provider.py
│   │   ├── ollama_provider.py
│   │   └── claude_provider.py
│   ├── repositories/
│   │   ├── accuracy_metrics_repository.py
│   │   ├── alert_repository.py
│   │   ├── audit_report_repository.py
│   │   ├── feedback_repository.py
│   │   ├── floor_plan_repository.py
│   │   ├── patrol_log_repository.py
│   │   └── position_repository.py
│   ├── routes/
│   │   ├── alert_routes.py
│   │   ├── floor_plan_routes.py
│   │   ├── report_routes.py
│   │   └── telemetry_routes.py
│   ├── services/
│   │   ├── alert_service.py
│   │   ├── floor_plan_service.py
│   │   ├── kalman_service.py
│   │   ├── llm_service.py
│   │   ├── positioning_service.py
│   │   ├── rag_service.py
│   │   ├── safety_service.py
│   │   └── simulation_service.py
│   └── utils/
│       ├── multilateration.py
│       ├── rssi_utils.py
│       ├── timestamp_utils.py
│       └── zone_utils.py
│
└── frontend/
    ├── app/
    │   ├── layout.tsx               # Root layout (IBM Plex fonts)
    │   ├── page.tsx                 # → /dashboard redirect
    │   ├── globals.css              # CSS variables + keyframes
    │   ├── login/
    │   │   └── page.tsx
    │   └── dashboard/
    │       ├── layout.tsx           # Auth guard + Navbar + Sidebar
    │       ├── page.tsx             # Overview (StatsRow + map + alerts)
    │       ├── alerts/
    │       │   └── page.tsx
    │       ├── reports/
    │       │   └── page.tsx
    │       └── floor-plans/
    │           └── page.tsx
    ├── components/
    │   ├── layout/
    │   │   ├── Navbar.tsx
    │   │   └── Sidebar.tsx
    │   ├── map/
    │   │   ├── FloorMap.tsx
    │   │   ├── WorkerMarker.tsx
    │   │   └── ZoneOverlay.tsx
    │   ├── dashboard/
    │   │   ├── StatsRow.tsx
    │   │   └── FloorMapArea.tsx
    │   ├── alerts/
    │   │   ├── AlertCard.tsx
    │   │   ├── AlertList.tsx
    │   │   └── FeedbackForm.tsx
    │   ├── reports/
    │   │   ├── ReportCard.tsx
    │   │   └── GenerateReportButton.tsx
    │   ├── floor-plans/
    │   │   ├── FloorPlanModal.tsx
    │   │   ├── FloorPlanList.tsx
    │   │   └── FloorPlanUpload.tsx
    │   └── shared/
    │       ├── AlertTypeBadge.tsx
    │       ├── LoadingSpinner.tsx
    │       ├── SkeletonCard.tsx
    │       ├── StatusBadge.tsx
    │       └── ToastContainer.tsx
    ├── config/
    │   └── firebase.ts              # db (RTDB), fsdb (Firestore), storage, auth
    ├── hooks/
    │   ├── useAuth.ts
    │   ├── useAlerts.ts
    │   ├── usePositions.ts
    │   └── useFloorPlan.ts
    ├── services/
    │   ├── authService.ts
    │   ├── alertService.ts
    │   ├── positionService.ts
    │   ├── reportService.ts
    │   ├── floorPlanService.ts
    │   └── patrolLogService.ts
    ├── store/
    │   ├── dashboardStore.ts
    │   └── toastStore.ts
    ├── types/
    │   ├── alert.ts
    │   ├── auditReport.ts
    │   ├── feedback.ts
    │   ├── floorPlan.ts
    │   ├── patrolLog.ts
    │   └── position.ts
    ├── next.config.js
    ├── tailwind.config.ts
    └── package.json
```
