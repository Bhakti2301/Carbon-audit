# Carbon Audit frontend/backend integration files

These files connect the existing React screens to the Flask API that was tested at `http://127.0.0.1:5001`.

## 1. Copy the supplied files

Copy the `src/lib/api.js` and three `src/pages/*.jsx` files from this bundle into the matching paths under your existing `frontend/` directory, replacing the existing files after keeping a backup.

The updated audit page intentionally allows live calculation only for the activity currently validated in Firestore:

- Industry: Power Generation & Utilities (`power_generation`)
- Sub-sector in the current UI: Gas-fired Power Plant
- Process: Gas Turbine Combustion (`fuel_combustion`)
- Activity: Natural gas consumption (`natural_gas_consumption`)
- Dataset: DEFRA/DESNZ 2026 release 1.2, geography UK
- Unit: cubic metres (the UI's `m³` is mapped to `cubic metres` for the API)

Other template activities are rejected before making a calculation request. This is deliberate: the API catalog currently reports no approved factors for those activities. Do not re-enable frontend-side factor calculations as a fallback.

## 2. Make two small edits to existing `src/data/catalog.js`

Replace its `FRAMEWORKS` export with:

```js
export const FRAMEWORKS = ['GHG Protocol', 'ISO 14064-1']
```

Replace its `FACTOR_SOURCES` export with:

```js
export const FACTOR_SOURCES = ['DEFRA 2026']
```

Keep `SOURCES`, `COUNTRIES`, `FACILITY_TYPES`, `PERIOD_TYPES`, `INDUSTRIES`, and helper functions unchanged for now. The local factor numbers in `SOURCES` are not used by the updated live calculation request, but they should eventually be removed or clearly marked as display-only once the UI catalogue is fully backend-driven.

## 3. Configure the local API URL

Create `frontend/.env.local` with:

```env
VITE_API_BASE_URL=http://127.0.0.1:5001
```

Restart Vite after creating or editing this file. For Cloud Run, set `VITE_API_BASE_URL` to the deployed API service URL at frontend build time; do not deploy the localhost value.

## 4. Update the branding

In `frontend/src/App.jsx`, replace the visible `CarbonLedger` text with `Carbon Audit`.

## 5. Run and validate

Keep Flask running in the backend terminal. From another terminal:

```bash
cd frontend
npm run dev
```

Use the **Fill sample data** button on the audit page. It now loads the supported UK natural-gas example (100 m³) so you can exercise a real backend calculation. Click **Calculate emissions**, then **Generate carbon report**. The report should navigate to the backend report ID and remain available on Reports after a page refresh.

Also test `npm run build` from `frontend/`.

## Notes / known MVP limits

- Sign-in remains out of scope, as requested. Do not expose this unauthenticated API to real client data or public traffic.
- Draft saving and display-target preferences still use browser storage. Completed calculation reports are saved in Firestore.
- The evidence picker hashes local file bytes in the browser, but the original file is not uploaded to the backend. The backend stores only the supplied evidence name/reference metadata.
- Verification markers are not currently persisted as an authenticated backend verification decision, so report details display entries as not independently verified.
- Recalculating after modifying inputs creates a new immutable report draft rather than editing the prior report. This preserves prior calculation results but can leave multiple report drafts.
- The `GET /api/catalog` dataset summary still shows a legacy global `calculation_ready: false` status, even though the power-generation natural-gas mapping is available. Use the per-activity `factor_data_available` and `supported_factors` values for current frontend availability; clean up the global status separately.
