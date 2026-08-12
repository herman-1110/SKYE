# SKYE — Sentinel AI

SKYE is an indoor worker safety monitoring system built on BLE beacon positioning and AI-generated audit reports. It tracks worker and forklift locations in real time, detects safety hazards (man-down, collision, SOS, geofence breach), and produces LLM-generated patrol and safety-event reports for supervisors.

**Stack:** FastAPI · Firebase (Auth + Realtime Database + Firestore) · Google Gemini · Next.js · Tailwind CSS · Zustand

---

## Prerequisites

- [Node.js](https://nodejs.org/) v18 or higher
- [Python](https://www.python.org/) v3.10 or higher
- A Firebase project with **Authentication**, **Realtime Database**, and **Firestore** enabled
- A Google Gemini API key (or substitute provider — see env vars)

---

## Running the Backend

The backend is a Python FastAPI application that receives BLE telemetry, runs the positioning and safety pipeline, and serves the REST API.

1. **Navigate to the backend directory:**
   ```bash
   cd backend
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Mac / Linux
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and fill in the required values (see [Backend Environment Variables](#backend-environment-variables)).

5. **Add your Firebase service account key:**
   Download `serviceAccountKey.json` from the Firebase Console → Project Settings → Service Accounts and place it in the `backend/` directory (or update `FIREBASE_KEY_PATH` in `.env` to point to its location).

6. **Start the server:**
   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000   
   ```
   API is available at `http://localhost:8000` (or the port set in `.env`).

7. **Run the Simulation Service (optional — for demo/testing):**
   The simulation generates synthetic BLE telemetry for workers and a forklift, drives the full positioning and safety pipeline (Kalman filter, man-down, collision detection), and writes alerts and patrol logs to Firebase — no physical hardware required.
   ```bash
   python services/simulation_service.py
   ```

---

## Running the Frontend

The frontend is a Next.js dashboard for real-time monitoring, alert management, and report viewing.

1. **Navigate to the frontend directory:**
   ```bash
   cd frontend
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Configure environment variables:**
   ```bash
   cp .env.local.example .env.local
   ```
   Edit `.env.local` and fill in the required values (see [Frontend Environment Variables](#frontend-environment-variables)).

4. **Start the development server:**
   ```bash
   npm run dev
   ```
   Open `http://localhost:3000` in your browser.

---

## Run simulations
   
   Simulation Patrol: venv/Scripts/python.exe services/simulation_patrol.py
   Simulation Events: venv/Scripts/python.exe services/simulation_events.py

## Backend Environment Variables

| Variable | Required | Description |
|---|---|---|
| `FIREBASE_KEY_PATH` | Yes | Path to Firebase Admin SDK service account JSON |
| `FIREBASE_RTDB_URL` | Yes | Firebase Realtime Database URL |
| `GEMINI_API_KEY` | Yes* | Google Gemini API key (`*` if `LLM_PROVIDER=gemini`) |
| `ANTHROPIC_API_KEY` | Yes* | Anthropic API key (`*` if `LLM_PROVIDER=claude`) |
| `OPENAI_API_KEY` | Yes* | OpenAI API key (`*` if `LLM_PROVIDER=openai`) |
| `LLM_PROVIDER` | No | `gemini` (default) \| `claude` \| `openai` \| `ollama` |
| `LLM_MODEL_NAME` | No | Model name passed to the active provider |
| `OMADA_ACCESS_TOKEN` | No | Shared secret for the `/telemetry` endpoint (Omada webhook) |
| `PORT` | No | Uvicorn port (default `8000`) |
| `PATH_LOSS_EXPONENT` | No | LDPL indoor path-loss exponent (default `2.5`) |
| `TX_POWER_DEFAULT` | No | BLE TX power at 1 m in dBm (default `-59`) |
| `MAN_DOWN_MINUTES` | No | Minutes stationary before man-down fires (default `5`) |
| `MAN_DOWN_MOVEMENT_THRESHOLD` | No | Movement radius in metres (default `1.0`) |
| `COLLISION_ALERT_SECONDS` | No | Kalman look-ahead seconds for collision (default `3`) |
| `MIN_DWELL_SECONDS` | No | Checkpoint dwell time for patrol compliance (default `30`) |

---

## Frontend Environment Variables

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_FIREBASE_API_KEY` | Firebase JS SDK API key |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | Firebase Auth domain |
| `NEXT_PUBLIC_FIREBASE_RTDB_URL` | Firebase Realtime Database URL |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | Firebase project ID |
| `NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET` | Firebase Storage bucket |
| `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID` | Firebase Messaging sender ID |
| `NEXT_PUBLIC_FIREBASE_APP_ID` | Firebase App ID |
| `BACKEND_URL` | Python backend base URL (default `http://localhost:8000`) |

---

## Project Structure

```
skye/
├── backend/
│   ├── main.py                   # FastAPI app entry point & router registration
│   ├── routers/                  # API route handlers (telemetry, alerts, reports, users…)
│   ├── services/
│   │   ├── positioning_service.py  # LDPL → multilateration → Kalman filter
│   │   ├── safety_service.py       # Man-down, collision, SOS, geofence detection
│   │   ├── llm_service.py          # Gemini/OpenAI prompt builder & report generator
│   │   ├── patrol_service.py       # Patrol log ingestion & checkpoint compliance
│   │   └── simulation_service.py   # Synthetic telemetry for demo/testing
│   ├── models/                   # Pydantic dataclasses (AlertRecord, PositionRecord…)
│   ├── repositories/             # Firebase read/write abstractions
│   └── core/                     # Settings, Firebase init, shared utilities
│
└── frontend/
    ├── app/                      # Next.js App Router pages (dashboard, login, reports…)
    ├── components/
    │   ├── layout/               # Navbar, Sidebar
    │   ├── map/                  # FloorMap, WorkerMarker, GeofenceOverlay
    │   ├── alerts/               # AlertCard, AlertFeed
    │   └── shared/               # CriticalAlertBanner, ToastContainer, LoadingSpinner
    ├── hooks/                    # useAuth, usePositions, useAlerts (Firebase subscriptions)
    ├── services/                 # Firebase client wrappers (alertService, positionService…)
    ├── store/                    # Zustand global stores (dashboardStore, criticalAlertStore)
    └── types/                    # TypeScript interfaces (AlertRecord, PositionRecord…)
```
