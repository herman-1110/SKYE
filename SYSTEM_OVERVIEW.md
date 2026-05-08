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
                         Positioning + Safety Services
                                    ↓
                     Firebase Realtime DB (/positions, /alerts)
                                    ↓
                    Next.js Frontend (live onValue subscriptions)
                                    ↓
                     Admin Dashboard / Guard Dashboard
```

**Stack:**
- Backend: Python FastAPI + Firebase Admin SDK
- Frontend: Next.js 14 (App Router) + TypeScript + Tailwind CSS
- Database: Firebase Realtime DB (live) + Firestore (persistent) + Storage (images)
- Auth: Firebase Auth (email/password + Google OAuth)
- AI: Gemini (audit reports) + Google text-embedding-004 (RAG)

---

## 2. Backend

### 2.1 Application Setup (`main.py`)

- FastAPI app: `SKYE Sentinel-AI v0.1.0`
- Firebase Admin SDK initialised with RTDB URL on startup
- Middleware: CORS (all origins), RequestLogger
- Route prefixes:
  - `/auth` — public
  - `/telemetry` — Omada Bearer token
  - `/alerts`, `/users`, `/guard`, `/floor-plans`, `/reports` — Firebase ID token

---

### 2.2 Routes

#### `POST /auth/register` — PUBLIC
Creates Firebase Auth account + Firestore user doc.  
Body: `{ email, password, display_name, person_id? }`  
Returns: `{ uid, role, status }`  
First user ever → `role=admin, status=approved`. All others → `role=user, status=pending`.

#### `POST /auth/google` — PUBLIC
Verifies Firebase Google ID token, upserts user doc.  
Body: `{ id_token }`  
Returns: `{ uid, role, status }`

---

#### `POST /telemetry` — Omada Bearer token
Main positioning pipeline. Receives RSSI payload from Omada Controller.  
Body: `{ reporter_mac, person_id, person_type, readings: [{ ap_mac, rssi, ap_x, ap_y }] }`  
Runs: RSSI → distances → multilateration → Kalman → pixel coords → RTDB save → safety checks.  
Returns: `{ status: "ok" }`

---

#### `GET /alerts` — require_auth
All alerts from Realtime DB.

#### `POST /alerts/{alert_id}/feedback` — require_admin
Submit operator feedback on an alert. Marks resolved in RTDB, persists to Firestore for RAG.  
Body: `{ feedback: "confirmed"|"fixed"|"false_alarm", reason? }`

---

#### `GET /users` — require_admin
All users ordered by `created_at` descending.

#### `GET /users/pending` — require_admin
All users where `status == "pending"`.

#### `PATCH /users/{uid}/role` — require_admin
Body: `{ role: "admin"|"user" }`

#### `PATCH /users/{uid}/status` — require_admin
Body: `{ status: "pending"|"approved"|"suspended" }`

#### `DELETE /users/{uid}` — require_admin
Deletes Firebase Auth account + Firestore doc.

---

#### `GET /guard/position` — require_auth
Live position for the calling guard's `person_id` only.

#### `GET /guard/patrol` — require_auth
Patrol log entries for the calling guard's current shift.

#### `GET /guard/alerts` — require_auth
Alerts filtered to the calling guard's `person_id` only.

---

#### `GET /floor-plans` — require_admin
All floor plans for a user, ordered by upload date.  
Query: `?user_id={uid}`

#### `POST /floor-plans` — require_admin
Create floor plan metadata after image upload to Storage.  
Body: `{ user_id, name, url }`

#### `PATCH /floor-plans/{floor_plan_id}/scale` — require_admin
Body: `{ scale_pixels_per_meter }`

#### `PATCH /floor-plans/{floor_plan_id}/activate` — require_admin
Sets this plan active; deactivates all others for the same user.

---

#### `POST /reports/generate` — require_admin
Triggers Gemini audit report generation for a shift.  
Body: `{ shift_id, patrol_summaries, alert_summaries }`

---

### 2.3 Models

| Model | Fields |
|---|---|
| `UserRecord` | uid, email, display_name, role, status, person_id, created_at |
| `PositionRecord` | beacon_mac, person_id, person_type, x, y, zone, timestamp, predicted_x, predicted_y, pixel_x, pixel_y, is_stationary |
| `AlertRecord` | alert_id, alert_type, person_id, zone, timestamp, resolved |
| `PatrolLogRecord` | log_id, guard_id, checkpoint_id, checkpoint_name, expected_arrival, actual_arrival, dwell_time_seconds, min_dwell_required, ble_detected, vigi_detected, compliant, shift_id |
| `FloorPlanRecord` | floor_plan_id, user_id, name, url, uploaded_at, is_active, scale_pixels_per_meter |
| `FeedbackRecord` | feedback_id, alert_id, alert_type, zone, feedback, timestamp, feedback_reason, shift_id |
| `AuditReportRecord` | report_id, shift_id, generated_at, patrol_summary, alert_summary, rag_examples_used, report_text, model_used |

Alert types: `man_down` · `collision` · `ghost_patrol` · `patrol_violation`  
Feedback values: `confirmed` · `fixed` · `false_alarm`

---

### 2.4 Services

#### PositioningService
Full BLE → position pipeline per telemetry packet:
1. RSSI readings → distances via Log-Distance Path Loss (LDPL)  
   `distance = 10^((TX_POWER - RSSI) / (10 × PATH_LOSS_EXPONENT))`
2. Least-squares multilateration (requires ≥ 3 AP readings) → raw (x, y) in metres
3. KalmanFilter.update() → smoothed (x, y) + velocity (vx, vy)
4. KalmanFilter.predict_ahead(3s) → projected position for collision detection
5. Pixel conversion: metres × `scale_pixels_per_meter` (from active FloorPlan)
6. Zone assignment via `coordinate_to_zone(x, y)`
7. Save to Realtime DB `/positions/{beacon_mac}`

#### SafetyService
- `check_man_down()` — Alert if beacon stationary in high-risk zone > `MAN_DOWN_MINUTES`
- `check_collision()` — Alert when worker and forklift predicted positions converge within threshold
- `check_patrol_compliance()` — Alert if guard missed checkpoint or `dwell_time < min_dwell_required`
- `verify_multimodal()` — Ghost patrol: alert when BLE tag present but VIGI does NOT confirm human
- `run_all_checks()` — Called after every telemetry packet; runs man-down + collision

#### AlertService
- `get_all()` — All alerts from RTDB
- `submit_feedback(alert_id, feedback, reason)` — Mark resolved in RTDB + persist to Firestore

#### UserService
- `register()`, `register_google()` — Create/upsert user
- `get_all()`, `get_pending()` — Query users
- `update_role()`, `update_status()` — Admin operations (validates caller is admin)
- `delete(uid)` — Delete Firebase Auth + Firestore doc

#### GuardService
- `get_position(person_id)` — Live position entry
- `get_patrol(guard_id)` — Patrol logs for guard
- `get_alerts(person_id)` — Alerts for guard

#### FloorPlanService
- `get_all(user_id)`, `get_active(user_id)` — Retrieve floor plans
- `create(user_id, name, url)` — Create metadata post-upload
- `update_scale(floor_plan_id, scale)` — Update calibration
- `set_active(floor_plan_id, user_id)` — Activate, deactivate all others

#### LLMService
- `generate_report(shift_id, patrol_summaries, alert_summaries)` — Build prompt with RAG context, call Gemini, persist AuditReport to Firestore

#### RAGService
- `get_context(query, alert_type)` — Hybrid retrieval:
  1. Pre-filter feedback by `alert_type` (rule-based)
  2. Semantic re-rank via Google `text-embedding-004`
  3. Return top-3 most similar past incidents as report context

#### KalmanService
- `update(x, y)` — Apply measurement, return smoothed (x, y)
- `predict_ahead(seconds)` — Project state forward for collision prediction

---

### 2.5 Repositories

| Repository | Storage | Key Methods |
|---|---|---|
| `PositionRepository` | RTDB `/positions` | save, get, get_all, delete |
| `AlertRepository` | RTDB `/alerts` | save, get, get_all, mark_resolved |
| `UserRepository` | Firestore `users` | create, get_by_uid, get_all, get_pending, update_role, update_status, update_person_id, delete |
| `FeedbackRepository` | Firestore `feedback` | save, get_resolved_with_feedback, get_by_alert_type, get_by_zone |
| `FloorPlanRepository` | Firestore `floor_plans` | save, get_all, get_active, update_scale, set_active |
| `PatrolLogRepository` | Firestore `patrol_logs` | save, get, get_by_shift, get_by_guard |
| `AuditReportRepository` | Firestore `audit_reports` | save, get, get_all, get_by_shift |

---

### 2.6 Middleware

```
require_auth(Authorization: Bearer <Firebase ID token>)
  → verify_id_token() → get user from Firestore
  → reject if status == "pending" (403) or "suspended" (403)
  → return UserRecord

require_admin(user: UserRecord = Depends(require_auth))
  → reject if role != "admin" (403)
  → return UserRecord

verify_omada_token(Authorization: Bearer <Omada token>)
  → validates static token from .env
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
| `/dashboard` | Admin | Live map + stats + active alerts |
| `/dashboard/alerts` | Admin | All alerts + feedback form |
| `/dashboard/reports` | Admin | Generate + view AI audit reports |
| `/dashboard/users` | Admin | Approve/suspend/unsuspend/promote/remove users |
| `/dashboard/floor-plans` | Admin | Upload, calibrate, activate floor plans |
| `/guard` | Guard | Own live position + patrol log |
| `/guard/alerts` | Guard | Own alerts only |

---

### 3.2 Layout & Routing

**`/dashboard/layout.tsx`**
- Uses `useAuth()` — redirects unauthenticated → `/login`, guards → `/guard`
- Renders: `Navbar` + `Sidebar` (collapsible) + `ToastContainer`
- Mounts `DataSubscriptions` (positions + alerts real-time hooks)

**`/guard/layout.tsx`**
- Redirects admins → `/dashboard`
- Minimal header bar

---

### 3.3 Components

**Layout**
- `Navbar` — Cloud logo, SKYE wordmark, page title, user initials avatar, sign-out
- `Sidebar` — Collapsible nav: Dashboard, Alerts, Reports, Floor Plans, Users. Amber pending badge on Users link (live Firestore count). Personnel live list at bottom.

**Map**
- `FloorMap` — Renders active floor plan image, scaled to calibration
- `ZoneOverlay` — Draws zone boundaries over floor plan
- `WorkerMarker` — Animated position markers (guard/worker/forklift), coloured by type

**Alerts**
- `AlertList` — Filterable list of alerts, selectable
- `AlertCard` — Type badge, zone, person_id, timestamp, resolved state
- `FeedbackForm` — Radio (confirmed/fixed/false_alarm), notes, submit

**Floor Plans**
- `FloorPlanList` — All uploaded plans, activate/delete actions
- `FloorPlanUpload` — File input → Storage upload → create Firestore metadata
- `FloorPlanModal` — Calibration: mark two reference points → calculate `scale_pixels_per_meter`

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
| `alertService` | RTDB + API | subscribeToAlerts, submitFeedback |
| `positionService` | RTDB | subscribeToPositions, unsubscribeFromPositions |
| `floorPlanService` | Firestore + Storage + API | subscribeToFloorPlans, subscribeToActiveFloorPlan, uploadFloorPlan, updateScale, activateFloorPlan |
| `guardService` | API | getMyPosition, getMyPatrol, getMyAlerts |
| `reportService` | API | generateReport |
| `patrolLogService` | API | getPatrolLogs |

---

### 3.5 Hooks

| Hook | Returns | Description |
|---|---|---|
| `useAuth` | `{ user, userRecord, isLoading }` | Firebase auth state + Firestore UserRecord |
| `usePositions` | `{ positions, isLoading }` | RTDB live subscription → updates dashboardStore |
| `useAlerts` | `{ alerts, isLoading }` | RTDB live subscription → updates dashboardStore |
| `useFloorPlan` | `{ floorPlan }` | Active floor plan from Firestore |

---

### 3.6 Stores (Zustand)

**`dashboardStore`**
```typescript
{
  positions:       Record<beacon_mac, PositionRecord>
  alerts:          Record<alert_id, AlertRecord>
  selectedWorkerId: string | null
  activeShiftId:    string | null
}
```

**`toastStore`**
```typescript
{ toasts: Toast[] }
// toast.success(), toast.error(), toast.info() — auto-dismiss
```

---

### 3.7 Types

| Type | Fields |
|---|---|
| `UserRecord` | uid, email, display_name, role, status, person_id, created_at |
| `PositionRecord` | beacon_mac, person_id, person_type, x, y, zone, timestamp, predicted_x, predicted_y, pixel_x, pixel_y, is_stationary |
| `AlertRecord` | alert_id, alert_type, person_id, zone, timestamp, resolved |
| `FloorPlanRecord` | floor_plan_id, user_id, name, url, uploaded_at, is_active, scale_pixels_per_meter |
| `PatrolLogRecord` | log_id, guard_id, checkpoint_id, checkpoint_name, expected_arrival, actual_arrival, dwell_time_seconds, min_dwell_required, ble_detected, vigi_detected, compliant, shift_id |
| `AuditReportRecord` | report_id, shift_id, generated_at, patrol_summary, alert_summary, rag_examples_used, report_text, model_used |

---

## 4. Data Flow: BLE → Backend → Frontend

```
[Guard wears BLE tag]
        ↓
[Omada WiFi APs pick up RSSI broadcasts]
        ↓
POST /telemetry  (Omada Bearer token)
  payload: { reporter_mac, person_id, person_type, readings: [{ap_mac, rssi, ap_x, ap_y}] }
        ↓
PositioningService.compute_position()
  1. RSSI → LDPL distance per AP
  2. Multilateration (≥3 APs) → (x, y) metres
  3. Kalman filter → smoothed (x, y), velocity (vx, vy)
  4. predict_ahead(3s) → collision candidate position
  5. pixel_x, pixel_y = x,y × scale_pixels_per_meter
  6. zone = coordinate_to_zone(x, y)
  7. RTDB /positions/{beacon_mac} ← save
        ↓
SafetyService.run_all_checks()
  ├─ man_down?   → RTDB /alerts/{id} ← save
  └─ collision?  → RTDB /alerts/{id} ← save
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
  ├─ RAGService.get_context() → top-3 similar past incidents from Firestore feedback
  ├─ LLMService builds prompt + calls Gemini
  └─ Firestore audit_reports/ ← save generated report
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
| `feedback` | FeedbackRecord | by alert_type, by zone (for RAG) |
| `floor_plans` | FloorPlanRecord | by user_id, by is_active==true |
| `patrol_logs` | PatrolLogRecord | by shift_id, by guard_id |
| `audit_reports` | AuditReportRecord | by shift_id |

### Storage — binary files

| Path | Content |
|---|---|
| `floor_plans/{user_id}/{timestamp}_{filename}` | Floor plan images |

---

## 6. Key Design Decisions

### Dual Database Strategy
Realtime DB for **live, ephemeral** data (positions, alerts) — instant frontend streaming.  
Firestore for **persistent, queryable** data (users, feedback, logs) — historical records and RAG.

### No Auto Sign-In After Register
After registration the user is redirected — either to `/login?registered=admin` (first user) or `/pending-approval`. The frontend never calls `signInWithEmailAndPassword` immediately after registering because the backend creates the Firebase Auth account server-side; auto-sign-in was causing race conditions with auth state listeners.

### Kalman Smoothing + Collision Prediction
A 2D Kalman filter (state: x, y, vx, vy) smooths noisy RSSI-based positions and estimates velocity. The filter projects each tracked entity 3 seconds ahead to warn of collisions before impact occurs.

### RAG-Augmented Report Generation
Audit reports are grounded in real past incidents. When generating a shift report, the LLM service fetches the top-3 semantically similar historical feedback records from Firestore (pre-filtered by alert type, then re-ranked by `text-embedding-004` cosine similarity) and injects them into the Gemini prompt.

### Multi-Modal Ghost Patrol Detection
Ghost patrol alerts combine BLE beacon detection (Omada) with VIGI camera confirmation. An alert only fires when the BLE tag is present **but** VIGI does not confirm a human — detecting tag-without-person scenarios (e.g. left badge, proxy).

### Guard Data Isolation
Guard routes (`/guard/*`) always filter by `caller.person_id` extracted from the verified Firebase ID token. A guard can never query another guard's position, patrol, or alerts regardless of what uid they pass.

### Admin Self-Protection
Admins cannot suspend or demote their own account. Self-deletion is allowed but requires a confirmation modal and immediately signs them out. Other users can be suspended, unsuspended, or removed entirely with a separate confirmation flow.

### Pending Badge
The sidebar Users link subscribes to Firestore `users` via `onSnapshot` filtered by `status=="pending"`. The count updates in real-time without polling and cleans up on unmount.

---

## 7. Environment Variables

### Backend (`backend/.env`)

```env
FIREBASE_CREDENTIALS_PATH=path/to/serviceAccount.json
FIREBASE_RTDB_URL=https://your-project-default-rtdb.firebaseio.com
GEMINI_API_KEY=AIza...
OMADA_ACCESS_TOKEN=your-omada-bearer-token

# Positioning
TX_POWER_DEFAULT=-59
PATH_LOSS_EXPONENT=2.5

# Safety thresholds
MAN_DOWN_MINUTES=5
MAN_DOWN_MOVEMENT_THRESHOLD=1.0
COLLISION_ALERT_SECONDS=3

# LLM
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.5-flash
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
