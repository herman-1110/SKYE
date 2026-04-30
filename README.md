# SKYE

SKYE is a full-stack application consisting of a Flask-based backend and a Next.js/React frontend.

## Prerequisites

Make sure you have the following installed on your system:
- [Node.js](https://nodejs.org/) (v18 or higher recommended)
- [Python](https://www.python.org/) (v3.8 or higher)

---

## Running the Backend

The backend is built with Python and FastAPI.

1. **Navigate to the backend directory:**
   ```bash
   cd backend
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   ```

3. **Activate the virtual environment:**
   - **Windows:**
     ```bash
     venv\Scripts\activate
     ```
   - **Mac/Linux:**
     ```bash
     source venv/bin/activate
     ```

4. **Install the required dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

5. **Set up environment variables:**
   - Copy `.env.example` to a new file named `.env` and fill in the required values (e.g., Firebase credentials paths, ports).
   - Ensure your `serviceAccountKey.json` for Firebase is securely placed where `settings.FIREBASE_KEY_PATH` expects it.

6. **Run the server:**
   ```bash
   uvicorn main:app --reload
   ```
   The backend should now be running (default is usually http://localhost:8000 or the port specified in `.env`).

7. **Run the Simulation Service (Optional):**
   To generate synthetic telemetry and patrol log data for testing, run the simulation script from the `backend` directory:
   ```bash
   python services/simulation_service.py
   ```

---

## 🖥️ Running the Frontend

The frontend is built with Next.js, React, and Tailwind CSS.

1. **Navigate to the frontend directory:**
   ```bash
   cd frontend
   ```

2. **Install the dependencies:**
   ```bash
   npm install
   ```

3. **Set up environment variables:**
   - Copy `.env.local.example` to a new file named `.env.local` and add your required configuration keys.

4. **Run the development server:**
   ```bash
   npm run dev
   ```
   Open [http://localhost:3000](http://localhost:3000) in your browser to view the application.

---

## Structure Overview

- `/backend`: Python FastAPI, integrating with Firebase and generating telemetry data/reports.
- `/frontend`: Next.js Web App dashboard for viewing alerts, telemetry, and generating real-time reports.
