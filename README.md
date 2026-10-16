# SKYE — Sentinel AI

SKYE is an indoor safety monitoring system for industrial sites such as warehouses and factories. TP-Link Omada access points (APs) scan for the Bluetooth Low Energy (BLE) beacons that guards, workers and forklifts carry. The backend turns those signal strengths into positions on a floor plan, raises safety alerts and tracks guard patrols. A Next.js dashboard shows everything live, and a TP-Link VIGI camera adds people detection and live video.

**Stack:** FastAPI (Python) · Firebase (Authentication, Realtime Database, Firestore, Storage) · Google Gemini · Next.js 15 · Tailwind CSS · Zustand · go2rtc and ffmpeg (live video)

**Contents:**
[What it does](#what-it-does) ·
[Requirements](#requirements) ·
[Installation](#installation) ·
[Firebase setup](#firebase-setup) ·
[Configuration](#configuration) ·
[Running SKYE](#running-skye) ·
[Connecting the Omada APs](#connecting-the-omada-aps) ·
[Camera and live video](#camera-and-live-video) ·
[Simulators](#simulators) ·
[Backend settings](#backend-settings) ·
[Frontend settings](#frontend-settings) ·
[Troubleshooting](#troubleshooting) ·
[Tests](#tests) ·
[Documentation](#documentation) ·
[Project structure](#project-structure)

---

## What it does

| Area | What's built | Status |
|---|---|---|
| Positioning | With three or more APs: signal strength → distance (log-distance path loss) → weighted least squares → Kalman filter. With one or two APs: an approximate position at the strongest AP. | Working with real APs |
| Man-down | **Stillness:** a person hasn't moved more than `MAN_DOWN_MOVEMENT_EPSILON_M` for the configured number of minutes. **Signal loss:** no position update for `MAN_DOWN_STALE_SECONDS`. | Working |
| Collision | A worker's and a forklift's Kalman-predicted positions, `COLLISION_ALERT_SECONDS` ahead, come within the collision distance. | Working |
| Patrols | Guards' visits to the checkpoints (APs) on a floor's patrol route: dwell times, patrol logs, and violation alerts for each patrol window. | Built. Runs only on floors with patrol enabled and a route set. |
| Ghost Patrol | Flags a checkpoint visit that the beacon recorded but the camera didn't confirm. | Designed and simulated. Checking real visits against the camera is still to come (Prompt 133). |
| VIGI camera | Alarm events (`PEOPLE`, `MOTION`), health checks, discovery on the local network, and live video on the dashboard (admins only). | Working with a VIGI InSight S445 |
| AI reports | Gemini writes audit reports for patrol shifts and for safety events, using earlier alert feedback as context. It can also suggest zones from a floor-plan image. | Gemini only; the Claude, OpenAI and Ollama providers are stubs. Patrol-shift reports currently cover simulated shifts only. |
| Simulators | Three scripted scenarios that drive the real pipeline without hardware. | Working (see [Simulators](#simulators)) |
| Users | Email and password (with email verification), or Google sign-in. The first account becomes the owner; later accounts wait for an admin's approval. Roles: owner, admin, user. | Working |

## How it fits together

```
Omada APs (about 1 report per second each)
   │  POST /telemetry/omada            token in the report body
   ▼
FastAPI backend (backend/, port 8000) ──► Realtime Database: /positions, /alerts, heartbeats
   ▲   ▲                                 Firestore: users, buildings, floors, APs, cameras,
   │   │                                            zones, beacons, patrol logs, reports, settings
   │   └── POST /telemetry             the simulators (accepted from this machine only)
   └────── POST /vigi/alarm/<secret>   the VIGI camera's alarm events

Next.js dashboard (frontend/, port 3000)
   ├─ reads Firebase directly with the Firebase web SDK
   └─ calls the backend through /api/*  (rewritten to BACKEND_URL in next.config.js)

Live video: browser ◄── WebRTC ── go2rtc ◄── ffmpeg ◄── RTSP ── camera
            (the backend forwards the browser's offer to go2rtc's local API)
```

SKYE is developed and run on **Windows 11**. The backend and the frontend should also run on macOS and Linux (all the Python packages have wheels there), but that hasn't been tested, and the live-video launcher (`tools/go2rtc/start.ps1`) is Windows-only.

---

## Requirements

### Python: use 3.12

| Version | Use it? | Why |
|---|---|---|
| **3.12** | **Yes, recommended** | Developed and tested on 3.12.13. Everything installs without a compiler, and all the test suites pass. |
| 3.13 | Yes | Tested on 3.13.15: everything installs without a compiler, and all the backend's test suites pass. |
| 3.11 | Yes, for running SKYE | Tested on 3.11.15: everything installs without a compiler, and all the backend's test suites pass. One test tool, `tools/harness/check_capture.py`, needs 3.12 or later. |
| 3.10 | No | Reaches end of life in October 2026, and is untested. Its `datetime.fromisoformat` can't read timestamps that end in `Z`, which the backend accepts on 3.11 and later. |
| 3.9 and older | No | The pinned `numpy` (2.1.3) doesn't support them, so `pip install` fails. |
| **3.14 and newer** | **No** | The pinned `numpy` (2.1.3) and `scipy` (1.14.1) were released before Python 3.14, so they have no wheels for 3.14 or later. pip then tries to compile them from source, which fails on a normal Windows machine (no C and Fortran compilers). Tested on 3.14.7. |

**Check before you create the virtual environment.** On a machine with several Pythons, a plain `python` is often the newest one (3.14 is common now). Run `python --version`, and on Windows use the launcher to pick 3.12 explicitly (`py -3.12`), as shown under [Installation](#installation).

### Node.js: use 24 LTS

| Version | Use it? | Why |
|---|---|---|
| **24 LTS** | **Yes, recommended** | Tested with Node 24.19.0 and npm 11.17. Supported until April 2028. |
| 22 LTS | Yes | Meets every dependency's minimum, but untested. In maintenance until April 2027. |
| 26 | Untested | Meets every dependency's minimum. A "Current" release until it becomes LTS on 28 October 2026; supported until April 2029. |
| 25 | No | End of life since June 2026. Odd-numbered releases never become LTS. |
| 20 | No | Meets the minimum (20.3 or later), but reached end of life in April 2026: no more security fixes. |
| 18 and older | No | Below `pdfjs-dist` 4.10's minimum (Node 20), which the floor-plan upload uses; Next.js 15 itself needs at least 18.18. End of life. |

The frontend's `package-lock.json` is lockfile version 3, so npm 7 or later is needed; the npm that comes with Node 22 or 24 is fine.

### Accounts and services

- **A Firebase project on the Blaze (pay-as-you-go) plan.** Storage needs Blaze; Authentication, the Realtime Database and Firestore would work on the free Spark plan. Blaze keeps a free tier, so a small deployment like this one usually costs little or nothing, but set a budget alert in the Google Cloud console. Details are under [Firebase setup](#firebase-setup).
- **A Google Gemini API key**, from Google AI Studio. It's used for the AI reports, report context (embeddings) and zone detection.
- **Git**, to clone the repository.
- **The Firebase CLI** (`firebase-tools`), to deploy the security rules and indexes; see [Firebase setup](#firebase-setup), step 9.

### Hardware (optional)

- **For real positions:** a TP-Link Omada controller with APs that send their BLE scan reports to SKYE (the Omada IoT Transport Stream), and iBeacon tags. Without hardware, use the [Simulators](#simulators).
- **For the camera:** a TP-Link VIGI camera (developed with the InSight S445). Live video also needs go2rtc 1.9.14 and ffmpeg on Windows.

---

## Installation

### 1. Get the code

```bash
git clone https://github.com/herman-1110/SKYE.git
cd SKYE
```

### 2. Install Python 3.12

- **Windows:** [python.org](https://www.python.org/downloads/windows/) now recommends its **Python install manager**, which provides the `py` command. With it:
  ```powershell
  py install 3.12       # installs 3.12.10, the last 3.12 release with Windows builds
  py -0p                # lists the Pythons that py knows about
  py -3.12 --version
  ```
  Every 3.12 release installs the same packages, so 3.12.10 is fine. If you use python.org's classic installer instead, take the 3.12.10 one (later 3.12 releases have no Windows installer) and keep "py launcher" selected.
- **Windows, with [uv](https://docs.astral.sh/uv/):** `uv python install 3.12`. `py -0p` then lists it as an Astral install, but `py -3.12` only selects python.org's own Pythons. Create the venv with `uv venv --python 3.12 venv` instead (step 3).
- **macOS:** `brew install python@3.12`, or uv.
- **Linux:** your distribution's `python3.12` package (plus `python3.12-venv` on Debian and Ubuntu), or uv.

### 3. Create the backend's virtual environment and install the packages

**Windows (PowerShell):**

```powershell
cd backend
py -3.12 -m venv venv
venv\Scripts\python.exe --version          # must say 3.12.x
venv\Scripts\python.exe -m pip install --upgrade pip
venv\Scripts\python.exe -m pip install -r requirements.txt
```

With uv instead:

```powershell
cd backend
uv venv --python 3.12 venv
uv pip install -r requirements.txt --python venv\Scripts\python.exe
```

**macOS / Linux:**

```bash
cd backend
python3.12 -m venv venv
venv/bin/python --version                  # must say 3.12.x
venv/bin/python -m pip install --upgrade pip
venv/bin/python -m pip install -r requirements.txt
```

**About activating the venv.** You don't have to activate it if you call its Python directly, as above. To activate it anyway:
- PowerShell: `venv\Scripts\Activate.ps1`. If PowerShell refuses with "running scripts is disabled on this system", run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.
- cmd: `venv\Scripts\activate.bat`.
- macOS and Linux: `source venv/bin/activate`.

`filterpy` is installed from source. It's pure Python, so it needs no compiler.

### 4. Install Node.js 24 LTS

Install it from [nodejs.org](https://nodejs.org/), or with a version manager (nvm-windows on Windows; nvm or fnm on macOS and Linux). Then check:

```bash
node -v      # v24.x
npm -v
```

### 5. Install the frontend's packages

```bash
cd frontend
npm ci
```

`npm ci` installs exactly the versions in `package-lock.json`. `npm install` also works, but it may update the lockfile.

Recent npm versions (11.17, for example) also print an `allow-scripts` notice for `protobufjs`, `sharp` and `unrs-resolver`, which have install scripts. It's only a notice: by default npm still runs those scripts.

### 6. Install the Firebase CLI

It's only needed to deploy the security rules and indexes (see step 9 of [Firebase setup](#firebase-setup)):

```bash
npm install -g firebase-tools
firebase --version
```

---

## Firebase setup

SKYE uses four Firebase products in one project:
- **Authentication:** user accounts;
- **Realtime Database:** live state such as positions, alerts and heartbeats;
- **Firestore:** configuration and history;
- **Storage:** floor-plan images.

The steps below create them in the [Firebase console](https://console.firebase.google.com/). The console's menus change from time to time, so the names below may differ slightly.

### Step 1. Create the project

In the Firebase console, add a project and note its **project ID**: you need it in several places below. Google Analytics isn't used, so you can turn it off.

### Step 2. Switch to the Blaze plan

Cloud Storage for Firebase needs the pay-as-you-go **Blaze** plan. New default buckets can't be created on the free Spark plan, and Spark projects get a 402 error from Storage. Blaze keeps a free tier: buckets in `us-central1`, `us-east1` and `us-west1` get Google Cloud Storage's "Always Free" allowance.

Upgrade from the plan button in the console. Then set a budget alert under Billing in the Google Cloud console.

### Step 3. Authentication

1. Open **Authentication** and get started.
2. Under **Sign-in method**, turn on:
   - **Email/Password.** Users who register with an email address must click the verification link that Firebase sends before the dashboard opens for them.
   - **Google.** Choose a support email address when asked.
3. Under **Settings → Authorized domains**, `localhost` is listed by default. Add any other hostname you'll open the dashboard on, or Google sign-in fails with `auth/unauthorized-domain`.

### Step 4. Realtime Database

1. Create a Realtime Database.
2. **Choose its location carefully: it can't be changed later.**
3. Start in **locked mode**. The rules from this repository replace the defaults in step 9.
4. Copy the database URL from the top of the **Data** tab. Its form depends on the location:

   | Location | URL |
   |---|---|
   | `us-central1` | `https://<project-id>-default-rtdb.firebaseio.com` |
   | anywhere else | `https://<project-id>-default-rtdb.<region>.firebasedatabase.app` |

   The same URL goes into two settings: `FIREBASE_RTDB_URL` (backend) and `NEXT_PUBLIC_FIREBASE_RTDB_URL` (frontend).

### Step 5. Firestore

1. Create the **(default)** Firestore database in Native mode.
2. **Choose its location carefully: it can't be changed later.**
3. Start in **production mode**. The rules and indexes from this repository are deployed in step 9.

### Step 6. Storage

1. Open **Storage** and get started (this needs Blaze, step 2).
2. Pick a location, and start in **production mode**.
3. The default bucket is called `<project-id>.firebasestorage.app`.
4. **Change one line of code.** The backend names the bucket in `backend/services/floor_service.py`, where it deletes a floor's image when the floor is deleted. Replace the bucket name there with yours.

Floor plans can be uploaded as PNG, JPEG, WebP or PDF. The browser turns each PDF page into a PNG first, and the images are stored under `buildings/<building-id>/floors/`.

### Step 7. Register the web app (frontend settings)

1. Open **Project settings → General → Your apps**, add a **Web** app, and give it a nickname. Firebase Hosting isn't needed.
2. Copy the `firebaseConfig` values into `frontend/.env.local`:

   | `firebaseConfig` key | `frontend/.env.local` setting |
   |---|---|
   | `apiKey` | `NEXT_PUBLIC_FIREBASE_API_KEY` |
   | `authDomain` | `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` |
   | `databaseURL` | `NEXT_PUBLIC_FIREBASE_RTDB_URL` |
   | `projectId` | `NEXT_PUBLIC_FIREBASE_PROJECT_ID` |
   | `storageBucket` | `NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET` |
   | `messagingSenderId` | `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID` |
   | `appId` | `NEXT_PUBLIC_FIREBASE_APP_ID` |

If `databaseURL` is missing, the app was probably registered before the Realtime Database existed. Use the URL from step 4.

These web values aren't secrets, since they're sent to every browser. What protects the data is Authentication plus the security rules from step 9.

### Step 8. Service-account key (backend)

The backend uses the Firebase Admin SDK, which needs a service-account key.

1. Open **Project settings → Service accounts → Firebase Admin SDK**, and generate a new private key.
2. Save the downloaded JSON file as `backend/serviceAccountKey.json`.
3. In `backend/.env`, set:
   ```
   FIREBASE_KEY_PATH=./serviceAccountKey.json
   ```
   The path is relative to `backend/`, where you start the server.

**This key gives full admin access to the project.** It's gitignored. Never commit it, paste it into a chat, or send it anywhere. If it's ever exposed, delete it in the Google Cloud console (IAM & Admin → Service accounts → the account → Keys) and generate a new one.

### Step 9. Deploy the security rules and indexes

`firebase.json`, in the repository root, points the Firebase CLI to these files:

| File | Deploys |
|---|---|
| `firestore.rules` | Firestore security rules |
| `firestore.indexes.json` | Firestore composite indexes |
| `database.rules.json` | Realtime Database security rules |
| `storage.rules` | Storage security rules |

From the repository root:

```bash
firebase login
firebase deploy --project <project-id> --only firestore,database,storage
```

Deploying replaces whatever rules the console shows. Run it again whenever one of these files changes.

### Step 10. First start and first account

1. Fill in `backend/.env` and `frontend/.env.local` (see [Configuration](#configuration)), then start both (see [Running SKYE](#running-skye)).
2. **The backend seeds three things on its first start:**
   - the safety thresholds, into Firestore `settings/safety`;
   - the legacy beacon list, into Firestore `beacons`;
   - an owner: if none exists, the earliest-registered admin is promoted.
3. **Register the first account** at `http://localhost:3000/register`. **The first account becomes the owner** and is approved straight away. If you registered with email and password, verify the address first, then sign in.
4. **Later accounts start as pending.** An admin approves them on the dashboard's **Users** page. Only the owner can change roles.

### What SKYE stores where

| Product | Path or collection | Contents |
|---|---|---|
| Realtime Database | `/positions` | Each person's latest position (one record per person) |
| | `/alerts` | Man-down, collision, patrol-violation and ghost-patrol alerts |
| | `/ap_heartbeats` | The last report from each AP |
| | `/cctv_heartbeats` | Camera health: liveness, last alarm, OpenAPI checks, discovery |
| | `/beacon_scans` | Recently heard beacons (for the beacon manager) |
| Firestore | `users` | Accounts: role (owner, admin, user) and status (pending, approved, suspended) |
| | `buildings/{b}/floors/{f}` | Floors: floor plan, scale, patrol route and settings |
| | `…/floors/{f}/access_points`, `…/cctvs`, `…/zones` | The APs, cameras and zones placed on each floor |
| | `beacons` | Beacon identities (iBeacon UUID, major, minor → person and type) |
| | `patrol_logs` | Checkpoint visits |
| | `audit_reports`, `feedback` | AI reports, and feedback on alerts |
| | `accuracy_metrics` | Positioning accuracy records |
| | `settings/safety` | The man-down minutes and collision distance set on the Safety Settings page |
| Storage | `buildings/<building-id>/floors/…` | Floor-plan images |

---

## Configuration

**Backend:**

```bash
cd backend
cp .env.example .env
```

Then fill in the five required settings:

| Setting | Value |
|---|---|
| `FIREBASE_KEY_PATH` | `./serviceAccountKey.json` |
| `FIREBASE_RTDB_URL` | the Realtime Database URL from step 4 |
| `GEMINI_API_KEY` | your Gemini API key |
| `LLM_MODEL_NAME` | the Gemini model to use (`.env.example` has one) |
| `OMADA_ACCESS_TOKEN` | a long random hex string; see [Connecting the Omada APs](#connecting-the-omada-aps) |

The backend doesn't start without these. Everything else has a default; see [Backend settings](#backend-settings).

**Frontend:**

```bash
cd frontend
cp .env.local.example .env.local
```

Fill in the seven Firebase web values from step 7. Set `BACKEND_URL` too, if the backend isn't at `http://localhost:8000`. See [Frontend settings](#frontend-settings).

`.env`, `.env.local` and `serviceAccountKey.json` are all gitignored. Keep it that way.

---

## Running SKYE

**Backend.** From `backend/`:

```bash
# Windows
venv\Scripts\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
# macOS / Linux
venv/bin/python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

(If the venv is activated, `uvicorn main:app --reload --host 0.0.0.0 --port 8000` is the same.)

- **`--host 0.0.0.0` is needed for the APs and the camera.** Without it, uvicorn listens on `127.0.0.1` only, and nothing on the network can reach it.
- **Windows Firewall must allow inbound TCP 8000.** For example, from an administrator prompt:
  ```
  netsh advfirewall firewall add rule name="SKYE Backend 8000" dir=in action=allow protocol=TCP localport=8000
  ```
- **`--reload` restarts the server on every saved `.py` file, but it doesn't re-read `.env`.** Restart by hand after changing `.env`.
- **Logs:** every start writes its console output to `backend/logs/skye-*.log` (gitignored).
- `PORT` and `DEBUG` in `.env` apply only when the server is started with `python main.py`.

**Frontend.** From `frontend/`:

```bash
npm run dev
```

Open `http://localhost:3000`. The dashboard reaches the backend through its own `/api/*` route, which Next.js forwards to `BACKEND_URL`.

---

## Connecting the Omada APs

1. **Start the backend** as above, with `--host 0.0.0.0` and port 8000 open in the firewall.
2. **Choose a token.** Use a long random hex string (at least 32 characters), generated in your own terminal; `backend/.env.example` has a PowerShell one-liner. Put it in `backend/.env` as `OMADA_ACCESS_TOKEN`.
3. **Point the APs at SKYE.** In the Omada controller, send the APs' BLE scan reports to:
   ```
   http://<this machine's LAN address>:8000/telemetry/omada
   ```
   Set the controller's access token to the same value as `OMADA_ACCESS_TOKEN`. It arrives in every report as `meta.access_token`.
4. **Restart the backend.**
5. **Set up the floor on the dashboard:**
   1. Create a building and a floor, and upload the floor plan.
   2. Set the floor's scale.
   3. Place the APs. An AP that reports but isn't placed yet shows up in the device editor.
   4. Register each beacon on the **Beacons** page: its iBeacon UUID, major and minor, and the person or forklift it belongs to.
6. **Optional: limit which addresses may post.** Once every AP has a DHCP reservation, set `OMADA_INGEST_ALLOWED_IPS` to the AP addresses. An AP whose address changes would be shut out, so leave it empty until the addresses are fixed.

For a measurement session, follow [`docs/field-capture-protocol.md`](docs/field-capture-protocol.md).

---

## Camera and live video

**Alarms and health checks:**

1. **Set two values in `backend/.env`, then restart the backend:**
   - `VIGI_ALARM_PATH_SECRET`: at least 24 characters, for example from `python -c "import secrets; print(secrets.token_urlsafe(24))"`.
   - `VIGI_CAMERA_PASSWORD`: the camera's admin password. Only letters, digits and `- _ . ~` are supported.
2. **Point the camera's alarms at SKYE.** In the camera's web UI (Settings → Event → Alarm Server), send alarms to the address below, and turn on human detection:
   ```
   http://<this machine's LAN address>:8000/vigi/alarm/<VIGI_ALARM_PATH_SECRET>
   ```
   The camera sends no credentials, so the path secret is what protects this endpoint. Keep it out of logs and chats.
3. **Add the camera to its floor** in the dashboard's device editor. Cameras found on the network are listed as "online but not placed"; "Scan now" searches again.

The camera locks its admin account after repeated failed logins. The backend therefore doesn't retry a rejected password until `backend/.env` changes.

**Live video (Windows):**

1. **Put the two programs in `tools/go2rtc/bin/`** (gitignored): `go2rtc.exe` (version 1.9.14) and `ffmpeg.exe`.
   - go2rtc 1.9.14 can't read this camera's stream by itself, so it runs ffmpeg in front of it. Background: [`docs/go2rtc-sei-issue.md`](docs/go2rtc-sei-issue.md).
2. **Run the launcher in its own terminal** and leave it open:
   ```powershell
   tools\go2rtc\start.ps1
   ```
   - It reads the camera password from `backend/.env` and passes it to go2rtc only through go2rtc's environment.
   - It restarts go2rtc when the backend rewrites the config (after a camera change or a new laptop address).
   - The backend never starts or stops go2rtc.
3. **Watch a camera.** On the dashboard, an admin clicks the camera on the map.
   - Video plays on the machine that runs go2rtc.
   - Other devices would need inbound firewall rules for port 8555 (TCP and UDP).

---

## Simulators

Three scripted scenarios feed the real pipeline, so the dashboard can be shown without hardware:

| Mode | Script | What it shows |
|---|---|---|
| `patrol` | `services/simulation_patrol.py` | Two guards patrolling the APs in opposite directions; no safety events |
| `events` | `services/simulation_events.py` | Two guards, a worker and a forklift, with scripted collision, ghost-patrol and missed-checkpoint events |
| `shift` | `services/simulation_shift.py` | A shift change: two guards finish a loop, two more take over |

The simulators need an **active floor with at least three APs placed** (activate the floor on the Floor Plans page). They move their people between those APs, and print a message and stop if there's no such floor.

**Ways to start one:**
- **From the dashboard's simulation controls** (admins), or with `POST /simulation/start?mode=events|patrol|shift`. Stop it with `POST /simulation/stop`. This runs the simulator inside the backend.
- **As a script, from `backend/`, while the backend is running:**
  ```bash
  venv/Scripts/python.exe services/simulation_events.py
  ```
  The scripts post to `http://localhost:8000/telemetry`, which accepts requests from this machine only.

**Notes:**
- Simulated people are removed from `/positions` when their simulation stops, and again at every backend start.
- The `events` scenario's man-down segment doesn't currently raise an alert: the segment is shorter than the man-down threshold.

---

## Backend settings

All of them live in `backend/.env` and are read in `backend/config/settings.py`; `backend/.env.example` explains each one. Changes take effect after a restart.

**Required.** The backend doesn't start without these:

| Variable | Description |
|---|---|
| `FIREBASE_KEY_PATH` | Path to the Firebase Admin service-account JSON (relative to `backend/`) |
| `FIREBASE_RTDB_URL` | Realtime Database URL |
| `GEMINI_API_KEY` | Gemini API key (reports, report context, zone detection) |
| `LLM_MODEL_NAME` | Gemini model used for reports and zone detection |
| `OMADA_ACCESS_TOKEN` | Shared secret in every AP report (`meta.access_token`); the simulators send it too. A long random hex string. |

**Server and AI:**

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8000` | Port for `python main.py` only |
| `DEBUG` | `false` | `true` turns on reload for `python main.py` only |
| `LLM_PROVIDER` | `gemini` | Only `gemini` is implemented |
| `RAG_SIMILARITY_FLOOR` | `0.5` | Minimum similarity (0–1) for earlier alert feedback to be added to a report's context |

**AP ingest:**

| Variable | Default | Description |
|---|---|---|
| `OMADA_INGEST_ALLOWED_IPS` | empty | Comma-separated IPv4 addresses allowed to post to `/telemetry/omada`. Empty allows any address and logs one warning at startup. |
| `OMADA_RAW_DUMP_ENABLED` | `false` | Prints every raw AP report, for debugging. Set `PYTHONIOENCODING=utf-8` first. |

**Positioning:**

| Variable | Default | Description |
|---|---|---|
| `PATH_LOSS_EXPONENT` | `2.5` | Path-loss exponent (2.0 is free space; 2.5–3.5 is indoors) |
| `TX_POWER_DEFAULT` | `-59` | Beacon signal strength at 1 m, in dBm |
| `PROXIMITY_RSSI_FLOOR` | `-90.0` | With one or two APs: if even the strongest AP hears a beacon below this (dBm), it counts as gone |
| `POSITION_EXACT_HOLD_SECONDS` | `10.0` | How long a recent three-AP position outranks a new approximate one |
| `POSITION_EMIT_MIN_INTERVAL_S` | `1.8` | Minimum seconds between position updates for one beacon |
| `RSSI_NOISE_STD` | `3.0` | Noise (dB) the simulators add to their signal strengths |

**Safety:**

| Variable | Default | Description |
|---|---|---|
| `MAN_DOWN_MINUTES` | `5` | Minutes without movement before a stillness man-down * |
| `MAN_DOWN_MOVEMENT_EPSILON_M` | `2.0` | Movement (m) smaller than this counts as not moving |
| `MAN_DOWN_STALE_SECONDS` | `120.0` | Seconds without a position update before a signal-loss man-down |
| `MAN_DOWN_STALE_MAX_AGE_S` | `3600.0` | Older position records are treated as dead, not as an incident |
| `COLLISION_DISTANCE_M` | `2.0` | Distance (m) between a worker and a forklift that raises a collision alert * |
| `COLLISION_ALERT_SECONDS` | `3` | How far ahead (s) the Kalman filter predicts positions for the collision check |

\* These two seed Firestore's `settings/safety` on the first start. After that, the values set on the dashboard's Safety Settings page apply.

**Patrols:**

| Variable | Default | Description |
|---|---|---|
| `PATROL_PROXIMITY_RADIUS_M` | `1.0` | A guard within this distance (m) of a checkpoint is at it |
| `PATROL_PROXIMITY_EXIT_MARGIN_M` | `0.5` | Extra distance (m) before a guard counts as having left a checkpoint |
| `PATROL_NO_PATROL_DWELL_RATIO` | `0.5` | A guard who reached only one checkpoint in a window, and stayed there for at least this share of the window, is flagged as not patrolling |
| `MIN_DWELL_SECONDS` | `30` | Minimum time (s) at a checkpoint for a compliant visit |

**Camera:**

| Variable | Default | Description |
|---|---|---|
| `VIGI_ALARM_PATH_SECRET` | empty | Path secret for `/vigi/alarm/<secret>`, at least 24 characters. Empty or shorter: the endpoint answers 404. |
| `VIGI_CAMERA_PASSWORD` | empty | Camera admin password, for the health check and live video. Empty: no OpenAPI checks. |
| `VIGI_RAW_DUMP_ENABLED` | `false` | Prints each raw alarm, for debugging |
| `VIGI_LIVENESS_INTERVAL_S` | `5` | Seconds between checks that the camera's RTSP port answers |
| `VIGI_OPENAPI_INTERVAL_S` | `300` | Seconds between OpenAPI health checks |
| `VIGI_OPENAPI_START_DELAY_S` | `60` | Delay before the first OpenAPI check after a start |
| `VIGI_DISCOVERY_INTERVAL_S` | `60` | Seconds between camera searches on the local network; `0` turns them off |

**Live video:**

| Variable | Default | Description |
|---|---|---|
| `GO2RTC_API_URL` | `http://127.0.0.1:1984` | go2rtc's API. Keep it on this machine. |
| `GO2RTC_CONFIG_PATH` | `tools/go2rtc/go2rtc.yaml` | The go2rtc config the backend writes. It never contains the password. |
| `GO2RTC_WEBRTC_HOST` | auto | Address for go2rtc's video port (8555). Empty means this machine's LAN address on the route to the camera. |
| `GO2RTC_FFMPEG_PATH` | `tools/go2rtc/bin/ffmpeg.exe` | The ffmpeg that go2rtc runs |

A relative path in the last two settings is taken from `backend/`.

`backend/.env.example` also lists `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` and `OLLAMA_HOST`. Nothing reads them yet.

---

## Frontend settings

All of them live in `frontend/.env.local`. The first seven come from [Firebase setup](#firebase-setup), step 7.

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_FIREBASE_API_KEY` | Firebase web-app API key |
| `NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN` | Firebase Auth domain |
| `NEXT_PUBLIC_FIREBASE_RTDB_URL` | Realtime Database URL (the same as the backend's `FIREBASE_RTDB_URL`) |
| `NEXT_PUBLIC_FIREBASE_PROJECT_ID` | Firebase project ID |
| `NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET` | Storage bucket (`<project-id>.firebasestorage.app`) |
| `NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID` | Messaging sender ID |
| `NEXT_PUBLIC_FIREBASE_APP_ID` | Firebase app ID |
| `BACKEND_URL` | Backend address for the `/api/*` rewrite (default `http://localhost:8000`). Used by Next.js on the server only. |

After changing `.env.local`, restart `npm run dev` so every value is picked up; `BACKEND_URL` in particular is read when the server starts.

---

## Troubleshooting

**Python and installation:**

| Symptom | Cause and fix |
|---|---|
| `pip install` downloads `numpy-2.1.3.tar.gz`, then fails with `ERROR: Unknown compiler(s)` and `metadata-generation-failed` | The venv uses Python 3.14 or newer, which the pinned `numpy` and `scipy` have no ready-made packages for. Delete `venv` and recreate it with 3.12 (`py -3.12 -m venv venv`). |
| `ERROR: No matching distribution found for numpy==2.1.3` | The venv uses Python 3.9 or older. Recreate it with 3.12. |
| PowerShell: "running scripts is disabled on this system" when activating | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or call `venv\Scripts\python.exe` directly without activating. |
| `ModuleNotFoundError` when starting the backend | The packages went into a different Python. Start the server with the venv's Python (`venv\Scripts\python.exe -m uvicorn …`). |

**Backend start-up:**

| Symptom | Cause and fix |
|---|---|
| `KeyError: 'FIREBASE_KEY_PATH'` (or another name) | A required setting is missing from `backend/.env`. |
| `FileNotFoundError` for the service-account key | `FIREBASE_KEY_PATH` is wrong, or the server wasn't started from `backend/`. |
| A setting change has no effect | `--reload` doesn't re-read `.env`. Stop the server and start it again. |
| APs or the camera can't reach the backend | The server isn't started with `--host 0.0.0.0`, Windows Firewall blocks TCP 8000, or the machine's LAN address changed since the controller or camera was set up. |
| AP reports get 401 | `OMADA_ACCESS_TOKEN` and the controller's token differ. Restart the backend after changing `.env`. |
| AP reports get 403 | `OMADA_INGEST_ALLOWED_IPS` is set and doesn't list that AP's address. |

**Firebase and the dashboard:**

| Symptom | Cause and fix |
|---|---|
| "Missing or insufficient permissions" or `permission-denied` | The security rules haven't been deployed: step 9 of [Firebase setup](#firebase-setup). |
| "The query requires an index" | Deploy `firestore.indexes.json` (step 9), or open the link in the error message, which creates the index in the console. |
| Floor-plan upload fails with `storage/unauthorized` | The Storage rules haven't been deployed (step 9). |
| Storage answers 402, or says Spark projects aren't supported | The project is on the Spark plan. Upgrade to Blaze (step 2). |
| Deleting a floor leaves its image in Storage | The bucket name in `backend/services/floor_service.py` wasn't changed (step 6). |
| Google sign-in fails with `auth/unauthorized-domain` | Add the hostname you're using under Authentication → Settings → Authorized domains (step 3). |
| "Firebase error. Please ensure that you have the URL of your Firebase Realtime Database instance configured correctly" | The RTDB URL is wrong. Outside `us-central1`, it's the `firebasedatabase.app` form (step 4). |
| After registering, the app shows "pending approval" | Expected for every account after the first. An admin approves it on the Users page. Email/password accounts must also verify their address. |
| `npm ci` prints `EBADENGINE` warnings | Node is older than 20.3. Install Node 24 LTS. |

---

## Tests

`tools/harness/` is an isolated test harness for the backend:
- it runs the backend against in-memory fakes of the Realtime Database and Firestore;
- it blocks every network path to Google and Firebase;
- it refuses port 8000.

**Point it at a `git archive` export of the backend, never at the live `backend/` folder.** The commands and the test suites are in [`tools/harness/README.md`](tools/harness/README.md).

---

## Documentation

| Document | What it covers |
|---|---|
| [`SYSTEM_OVERVIEW.md`](SYSTEM_OVERVIEW.md) | Architecture, data flow and design decisions. Parts of it are out of date; check against the code. |
| [`HANDOFF.md`](HANDOFF.md) | Current development state, open threads and working rules |
| [`docs/field-capture-protocol.md`](docs/field-capture-protocol.md) | How to run a measurement session with the real APs |
| [`docs/vigi-integration-design.md`](docs/vigi-integration-design.md) | Camera integration design. §1–§6 are built; §7 (Ghost Patrol) is next; §8 (live view) was built differently, see the camera section above. |
| [`docs/go2rtc-sei-issue.md`](docs/go2rtc-sei-issue.md) | Why ffmpeg sits in front of go2rtc |
| [`tools/harness/README.md`](tools/harness/README.md) | The test harness |

---

## Project structure

```
SKYE/
├── backend/
│   ├── main.py               # FastAPI app: routers, middleware, startup tasks and background loops
│   ├── config/               # settings.py (every setting), beacon_registry.py (legacy seed)
│   ├── routes/               # HTTP routes: telemetry, AP ingest, camera alarms, buildings and floors,
│   │                         #   alerts, beacons, zones, reports, users, settings, simulation
│   ├── middleware/           # Firebase ID-token auth and roles, ingest checks, request logging, errors
│   ├── services/             # positioning, proximity, Kalman, Omada ingest, safety, patrol tracker,
│   │                         #   reports (LLM, RAG), camera (VIGI, health, discovery, live view), simulators
│   ├── repositories/         # Firestore and Realtime Database access
│   ├── models/               # data records
│   ├── schemas/              # request and response schemas
│   ├── providers/            # LLM providers (Gemini implemented; Claude, OpenAI, Ollama are stubs)
│   └── utils/                # multilateration, RSSI, timestamps, MAC handling, log redaction, capture log
├── frontend/
│   ├── app/                  # pages: login, register, pending-approval, suspended, and the dashboard
│   │                         #   (alerts, beacons, floor-plans, patrol-reports, reports, safety-settings, users)
│   ├── components/           # map/ (floor map, markers, zones, patrol route, device editor, camera panel
│   │                         #   and live view), dashboard/, alerts/, reports/, layout/, shared/
│   ├── hooks/                # live Firebase subscriptions (positions, alerts, heartbeats, floors, zones, auth)
│   ├── services/             # calls to the backend and Firebase
│   ├── store/                # Zustand stores
│   ├── types/                # TypeScript types
│   ├── utils/                # API client and helpers (PDF floor plans → PNG)
│   └── config/firebase.ts    # Firebase web SDK set-up
├── tools/
│   ├── harness/              # isolated backend test harness
│   ├── go2rtc/start.ps1      # live-video relay launcher
│   └── vigi-listener/        # camera capture and probe scripts used to study the camera
├── docs/                     # design notes, the field-capture protocol, measurement evidence
├── firebase.json             # Firebase CLI config: rules and indexes below
├── firestore.rules · firestore.indexes.json · database.rules.json · storage.rules
├── postman/ · .postman/      # Postman workspace files
├── skye-presentation.html    # project presentation
├── SYSTEM_OVERVIEW.md
└── HANDOFF.md
```
