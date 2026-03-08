# GIS_TN - Tamil Nadu Fiber Route Planning Platform

A local-first GIS planning workspace for fiber route computation across Tamil Nadu.

It combines:
- `planning-dashboard` (React + Leaflet web UI)
- `planning-service` (FastAPI + PostGIS + pgRouting backend)
- `desktop-app` (Electron wrapper bundling frontend + backend)
- Large GeoJSON datasets and historical version snapshots (`v3.0` -> `v7.0.2`)

## What This Project Does

- Computes shortest road-network routes from selected infra node to customer location.
- Supports single-point and batch planning flows.
- Provides estimated rollout cost from route distance.
- Exposes catalog and routing APIs over a PostGIS/pgRouting graph.
- Includes notebook-based estimation hooks (`/routing/notebook-info`, `/routing/notebook-estimate`).
- Offers an offline-capable Windows desktop distribution.

## Architecture

### 1) Frontend (`planning-dashboard`)
- React 18 + Vite 5 + React-Leaflet.
- Loads local base data from `public/data`.
- Can call backend endpoints for DB routing and viewport road streaming.
- Falls back to an in-browser graph + Dijkstra route computation if backend route call fails.

### 2) Backend (`planning-service`)
- FastAPI service with routers for:
  - `health`
  - `catalog`
  - `routing`
  - `upload-batch` + async job status/result APIs
- Uses PostgreSQL + PostGIS + pgRouting (`docker-compose.yml` provided).
- Adds middleware for request context, payload limits, rate limits, and timeout handling.

### 3) Desktop (`desktop-app`)
- Electron shell that starts the bundled backend (`uvicorn main:app`) and loads built frontend.
- Performs backend health checks before opening UI.
- Produces Windows installers via `electron-builder`.

## Quick Start (Web + API)

### Prerequisites
- Node.js 18+
- Python 3.11+
- Docker Desktop (for Postgres + PostGIS + pgRouting)

### Steps

1. Start DB

```powershell
cd planning-service
docker compose up -d
```

2. Configure backend

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

3. Start API

```powershell
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

4. Start dashboard (new terminal)

```powershell
cd ..\planning-dashboard
npm install
npm run dev
```

Frontend default: `http://localhost:5173`
Backend default: `http://localhost:8000`

## Quick Start (Desktop)

```powershell
cd planning-dashboard
npm install
npm run build
cd ..\desktop-app
npm install
npm run prepare:assets
npm start
```

To build installer:

```powershell
npm run dist
```

## API Surface (Current)

Total route decorators in `planning-service`: **13**

Main endpoints include:
- `GET /health`
- `GET /catalog/summary`
- `GET /catalog/districts`
- `GET /catalog/franchises`
- `GET /catalog/roads`
- `POST /routing/compute`
- `POST /routing/compute-batch`
- `GET /routing/notebook-info`
- `POST /routing/notebook-estimate`
- `POST /upload-batch`
- `GET /job-status/{job_id}`
- `GET /job-result/{job_id}`
- `GET /jobs/metrics`

## Repository Metrics (Measured)

Measured on **2026-03-08** from this workspace snapshot.

### Source Metrics (core apps)
- `planning-dashboard`: 12 source files, 1,898 lines
- `planning-service`: 36 source files, 3,295 lines
- `desktop-app`: 38 source files, 3,437 lines
- Combined (core apps): **117 source files**
- Combined lines (filtered source set): **8,224**

### Data Metrics
- `planning-dashboard/public/data/roads.geojson`: 41.03 MB, 33,628 features
- `planning-dashboard/public/data/gp_boundary.geojson`: 5.56 MB, 32 features
- `planning-dashboard/public/data/infra_nodes.geojson`: 0.04 MB, 106 features
- `roads.geojson` (root): 2,632.96 MB
- `new_roads.geojson` (root): 512.79 MB
- `roads_chunks`: 100 files, 484.66 MB total

### Versioning/History Metrics
- Snapshot directories: **10**
- Available snapshots: `v3.0`, `v4.0`, `v4.0.1`, `v5.0`, `v6.0`, `v6.0.1`, `v6.0.2`, `v7.0`, `v7.0.1`, `v7.0.2`

### Runtime/Control Limits (from `.env.example`)
- Max batch coordinates: `50,000`
- Batch chunk size: `1,000`
- Max request body: `5,000,000` bytes
- Rate limit: `10` req / `60` sec (per IP)
- Request timeout: `30` sec
- Max active jobs: `5`

## Key Directories

- `planning-dashboard/` -> Web GIS UI
- `planning-service/` -> FastAPI + PostGIS/pgRouting backend
- `desktop-app/` -> Electron desktop packaging/runtime
- `data/` -> Core GeoJSON inputs
- `roads_chunks/` -> Chunked road datasets
- `v*/` -> Historical snapshots

## Notes

- This repo contains very large geospatial assets; cloning and indexing can be heavy.
- Desktop mode expects local Python + PostgreSQL availability unless fully provisioned in your environment.
- If backend is unavailable, parts of the UI can still route via local graph logic for loaded road data.
