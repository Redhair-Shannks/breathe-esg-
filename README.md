# Breathe ESG Ingestion Review Prototype

Prototype Django REST + React app for ingesting enterprise ESG activity data, normalizing it, surfacing validation issues, and locking analyst-approved rows for audit.

## What This Builds

- SAP fuel/procurement CSV/XLSX ingestion shaped after S/4HANA material document and purchase extracts.
- Utility electricity CSV/XLSX ingestion shaped after Green Button / utility portal billing-period exports.
- Corporate travel CSV/XLSX ingestion shaped after SAP Concur approved expense data.
- Analyst dashboard for source/status/severity filters, issue summary, blocked rows, warnings, raw row inspection, normalized row edits, approval, rejection, and audit trail.
- Dedicated tenant audit trail view with event timeline, actors, row references, edit notes, and before/after event data.
- Multi-tenant data model with source lineage, unit normalization, Scope 1/2/3 categories, emission estimates, and immutable raw records.

## Demo Access

- Dashboard access: no app login required for the prototype.
- Optional Django admin/demo analyst username: `analyst@demo.local`
- Optional Django admin/demo analyst password: `demo-password`
- Demo tenant: `acme-manufacturing`

## Local Setup

```powershell
cd breathe-esg-
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd frontend
npm install
npm run build
cd ..\backend
..\.venv\Scripts\python.exe manage.py migrate
..\.venv\Scripts\python.exe manage.py seed_demo --reload --noinput
..\.venv\Scripts\python.exe manage.py runserver
```

Open `http://127.0.0.1:8000`.

The React app is built into `frontend/dist` and served by Django. A separate frontend dev server is not required for the demo path.
Do not open `frontend/dist/index.html` directly or use `localhost:5173` for the normal demo; use the Django URL above. If the page looks blank after rebuilding, hard refresh the browser with `Ctrl + F5`.

If the page is still blank, an older Django process may already be serving stale files on port `8000`. Stop it, rebuild, and restart from this repository:

```powershell
netstat -ano | findstr ":8000"
Stop-Process -Id <PID_FROM_LAST_COLUMN> -Force
cd breathe-esg-
cd frontend
npm run build
cd ..\backend
..\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

## Sample Files

The sample files are in `sample_data/`:

- `sap_fuel_procurement.csv`
- `utility_green_button_electricity.csv`
- `concur_travel_expenses.csv`

They intentionally include realistic review problems: German SAP headers, unmapped plant and material codes, overlapping utility periods, electricity usage spikes, airport-code distance estimation, unmapped travel expense type, and invalid hotel nights. The importer also accepts first-sheet `.xlsx` workbooks with tabular headers.

Uploads are source-specific. The analyst chooses the file source category - SAP, Utility, or Travel - before importing. A single source file can still contain multiple row categories inside that source, such as SAP fuel plus procurement or travel flights plus hotels plus taxis. If the selected source does not match strong header clues in the file, the API returns a clear error instead of importing the rows under the wrong parser.

## Deployment

The repo includes `render.yaml` and `Procfile`.

On Render, create from the repository using the Blueprint flow. The build installs Python dependencies, collects the committed React static bundle, runs migrations, seeds demo data, and starts Gunicorn.

When changing frontend code, run `npm run build` inside `frontend/` before committing so `frontend/dist` stays current for deployment.

## Important Docs

- `MODEL.md`: data model and audit/review reasoning.
- `DECISIONS.md`: ambiguity decisions and PM questions.
- `TRADEOFFS.md`: deliberate non-builds.
- `SOURCES.md`: source-format research and sample-data rationale.
- `RULES.md`: validation and classification rules, including which are sourced and which are prototype judgment calls.
- `SUBMISSION_CHECKLIST.md`: deployment and email checklist.
