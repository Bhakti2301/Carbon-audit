# Carbon Audit — Full Stack Application

This project consists of a **Python Flask backend** (backed by Google Cloud Firestore) and a **React 19 (Vite) frontend**.

## Architecture & Overview

- **Backend (`/backend`)**:
  - Python Flask REST API running on port `5001`.
  - Firebase Admin SDK & Google Cloud Firestore integration.
  - Implements emission factor lookups, validation, report creation, calculation (`/api/calculate-and-log`), and audit trails.
- **Frontend (`/frontend`)**:
  - React 19 + Vite single-page application running on port `5173`.
  - Interacts with the backend via `src/lib/api.js`.
  - Supports facility setup, reporting periods, emission auditing, report viewing, and dashboard metrics.

---

## Prerequisites

- **Python**: 3.10+ (tested with Python 3.14)
- **Node.js**: 18+ and npm
- **Google Cloud Service Account**: `backend/carbon-audit-service-account.json` (required for Firestore connection)

---

## Quick Start Guide

### 1. Backend Setup & Run

Open a terminal in the project root:

```bash
cd backend

# Activate existing virtual environment (or create one with: python3 -m venv .venv)
source .venv/bin/activate

# Install dependencies (already satisfied if using the existing .venv)
pip install -r requirements.txt

# Start the Flask API server
python app.py
```

The API will start at: `http://127.0.0.1:5001`
- Health check: `http://127.0.0.1:5001/api/health`
- Catalog: `http://127.0.0.1:5001/api/catalog`

### 2. Frontend Setup & Run

Open a second terminal in the project root:

```bash
cd frontend

# Verify .env.local exists (points to the local Flask backend)
# VITE_API_BASE_URL=http://127.0.0.1:5001

# Install node dependencies
npm install

# Start Vite dev server
npm run dev
```

The frontend will run at: `http://localhost:5173`

---

## Verifying the Integrated Flow

1. Open `http://localhost:5173` in your browser.
2. Navigate to **Carbon audit** in the sidebar.
3. Click **Fill sample data** in the top-right corner.
   - This populates the verified test scenario:
     - **Facility**: UK Gas Power Demo (United Kingdom)
     - **Framework**: GHG Protocol
     - **Factor Source**: DEFRA 2026
     - **Industry**: Power Generation & Utilities (`power_generation`)
     - **Sub-sector**: Gas-fired Power Plant (`gasplant`)
     - **Process**: Gas Turbine Combustion (`fuel_combustion`)
     - **Activity**: Natural gas consumption (`natural_gas_consumption`)
     - **Quantity**: 100 m³ (mapped to cubic metres)
4. Click **Calculate emissions** at the bottom.
   - The UI communicates with `POST /api/reports` and `POST /api/calculate-and-log`.
   - Results display `0.20 tCO2e` calculated live via the backend.
5. Click **Generate carbon report**.
   - Navigates to `/reports/<REPORT_ID>` showing the full breakdown and factor details.
6. Check **Reports** and **Dashboard** tabs:
   - The new report appears in the saved reports table and feeds the dashboard metrics.
