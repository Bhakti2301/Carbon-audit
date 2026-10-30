# Carbon Audit UI

Vite + React 19 front end for the carbon audit flow:
facility details → reporting period & standards → industry → sub-sector → processes / activities → fuel used (with evidence) → calculate → carbon report → dashboard.

## Setup & Run

1. Configure API endpoint in `.env.local` (defaults to Flask backend on `http://127.0.0.1:5001`):
```bash
cp .env.example .env.local
```

2. Install dependencies & start the dev server:
```bash
npm install
npm run dev
```

Open http://localhost:5173

3. Build for production:
```bash
npm run build
```

## Where things live

| File | What it holds |
| --- | --- |
| `src/data/catalog.js` | Industries, sub-sectors, processes, fuels, emission factors, country grid factors |
| `src/lib/calc.js` | The calculation (quantity × factor, totals per process and scope) and SHA-256 helper |
| `src/lib/api.js` | Single hook point for the backend calculation API |
| `src/lib/storage.js` | Reports, drafts, custom industries, dashboard target (browser localStorage until the database exists) |
| `src/pages/DashboardPage.jsx` | Scope split, target gauge, top 5 activities, trend |
| `src/pages/AuditPage.jsx` | New audit form, evidence + verification, change history |
| `src/pages/ReportsPage.jsx` | Reports list |
| `src/pages/ReportView.jsx` | Single report, printable to PDF |

## Connecting the backend

- Calculation: replace the body of `requestCalculation` in `src/lib/api.js` with a call to the Python API.
- Storage: swap the functions in `src/lib/storage.js` for API calls. Evidence files go to file storage; keep the URL + checksum per entry ID.
- Emission factors in `catalog.js` are indicative (DEFRA 2025 / country grid) and should come from the backend's official factor tables.
